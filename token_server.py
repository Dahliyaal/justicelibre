"""Tiny HTTP server for the PISTE credential exchange + public search API.

Endpoints :
  POST /api/token      — échange Client ID/Secret PISTE contre session token
  GET  /api/search     — recherche fédérée publique (sans auth)
  GET  /api/decision   — récupération du texte intégral

Runs on port 8766. Nginx routes /api/* here.
"""
import asyncio
import json
import re
import sys
import time
import urllib.parse
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

# Importer le moteur de recherche (search_api.py au même niveau)
sys.path.insert(0, "/opt/justicelibre")
from search_api import search_federated, fetch_decision

OAUTH_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"

# Shared session store (imported by server.py via file-based IPC)
SESSION_FILE = "/tmp/justicelibre_sessions.json"

import threading
_LOCK = threading.Lock()


def _load_sessions() -> dict:
    try:
        with open(SESSION_FILE) as f:
            sessions = json.load(f)
        # Cleanup expired
        now = time.time()
        sessions = {k: v for k, v in sessions.items() if v["expires"] > now}
        return sessions
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_sessions(sessions: dict):
    with open(SESSION_FILE, "w") as f:
        json.dump(sessions, f)


def _exchange_token(client_id: str, client_secret: str) -> str | None:
    """Synchronous OAuth2 token exchange."""
    try:
        r = httpx.post(
            OAUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "openid",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception:
        return None


class TokenHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/search":
            return self._handle_search(qs)
        if parsed.path == "/api/decision":
            return self._handle_decision(qs)
        if parsed.path in ("/api", "/api/"):
            return self._json_response(200, {
                "service": "justicelibre public REST API",
                "endpoints": {
                    "GET /api/search?q=&juridiction=&lieu=&limit=": "Recherche fédérée dans 5 sources",
                    "GET /api/decision?source=&id=": "Texte intégral d'une décision",
                    "POST /api/token": "Échange credentials PISTE → session token",
                },
                "docs": "https://justicelibre.org",
            })
        return self._json_response(404, {"error": f"Endpoint inconnu : {parsed.path}. Endpoints valides : /api/search, /api/decision, /api/token, /api."})

    def _handle_search(self, qs: dict):
        q = (qs.get("q", [""])[0] or "").strip()
        if not q:
            return self._json_response(400, {"error": "Paramètre `q` requis."})
        if len(q) < 3:
            return self._json_response(400, {"error": "Requête trop courte (min. 3 caractères) — risque de surcharge sur les APIs externes."})
        if len(q) > 500:
            return self._json_response(400, {"error": "Requête trop longue (max. 500 caractères)."})
        # Whitelist stricte sur juridiction et sources
        ALLOWED_JURI = {"", "admin", "ce", "caa", "ta", "judic", "cass", "ca", "constit", "europ", "cedh", "cjue"}
        juri = (qs.get("juridiction", [""])[0] or "").strip().lower()
        if juri not in ALLOWED_JURI:
            juri = ""
        lieu = (qs.get("lieu", [""])[0] or "").strip()[:40]
        # lieu : format attendu [A-Z0-9]+ (TA75, CAA69, etc.)
        if lieu and not re.match(r"^[A-Za-z0-9]{1,20}$", lieu):
            lieu = ""
        try:
            limit = int(qs.get("limit", ["20"])[0])
        except ValueError:
            limit = 20
        limit = max(1, min(limit, 100))
        try:
            offset = int(qs.get("offset", ["0"])[0])
        except ValueError:
            offset = 0
        offset = max(0, min(offset, 10000))
        sources_only = [s.strip() for s in (qs.get("sources", [""])[0] or "").split(",") if s.strip()]
        try:
            timeout_s = float(qs.get("timeout", ["12"])[0])
        except ValueError:
            timeout_s = 12.0
        timeout_s = max(2.0, min(timeout_s, 60.0))
        # Si on interroge une seule source, limit_per_source = limit entier
        lps = limit if sources_only and len(sources_only) == 1 else max(5, limit // 2)
        try:
            data = asyncio.run(search_federated(
                q=q, juridiction=juri, lieu=lieu, limit=limit,
                limit_per_source=lps,
                offset=offset,
                sources_only=sources_only or None,
                timeout_s=timeout_s,
            ))
            return self._json_response(200, data)
        except Exception as e:
            # Ne pas exposer stacktrace/chemin serveur au client
            import traceback
            traceback.print_exc()
            return self._json_response(500, {"error": "Erreur interne du serveur. Réessayez."})

    def _handle_decision(self, qs: dict):
        source = (qs.get("source", [""])[0] or "").strip()
        decision_id = (qs.get("id", [""])[0] or "").strip()
        if not source or not decision_id:
            return self._json_response(400, {"error": "Paramètres `source` et `id` requis."})
        try:
            data = asyncio.run(fetch_decision(source=source, decision_id=decision_id))
            if data is None:
                return self._json_response(404, {"error": "Décision introuvable."})
            return self._json_response(200, data)
        except Exception as e:
            # Ne pas exposer stacktrace/chemin serveur au client
            import traceback
            traceback.print_exc()
            return self._json_response(500, {"error": "Erreur interne du serveur. Réessayez."})

    def do_POST(self):
        if self.path != "/api/token":
            self.send_response(404)
            self.end_headers()
            return

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        try:
            data = json.loads(body)
            client_id = data.get("client_id", "").strip()
            client_secret = data.get("client_secret", "").strip()
        except (json.JSONDecodeError, AttributeError):
            self._json_response(400, {"error": "JSON invalide"})
            return

        if not client_id or not client_secret:
            self._json_response(400, {"error": "client_id et client_secret sont requis"})
            return

        # Exchange with PISTE
        bearer = _exchange_token(client_id, client_secret)
        if not bearer:
            self._json_response(401, {"error": "Identifiants PISTE invalides ou PISTE indisponible"})
            return

        # Create session
        session_token = str(uuid.uuid4())
        with _LOCK:
            sessions = _load_sessions()
            sessions[session_token] = {
                "bearer": bearer,
                "expires": time.time() + 3600,
                "client_prefix": client_id[:8],
            }
            _save_sessions(sessions)

        self._json_response(200, {
            "session_token": session_token,
            "expires_in": 3600,
            "message": "Token valide 1 heure. Utilisez-le dans le paramètre session_token des tools search_judiciaire et get_decision_judiciaire.",
        })

    def _json_response(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Silence logs


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8766), TokenHandler)
    print("API server on http://127.0.0.1:8766/api/{token,search,decision}")
    server.serve_forever()
