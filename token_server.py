"""Tiny HTTP server for the PISTE credential exchange + public search API.

Endpoints :
  POST   /api/token       — échange Client ID/Secret PISTE contre session token
  DELETE /api/token       — invalide un session token (logout)
  GET    /api/search      — recherche fédérée publique (sans auth)
  GET    /api/decision    — récupération du texte intégral
  GET    /api/law         — article de loi à une date donnée
  GET    /api/law/versions — toutes les versions d'un article
  POST   /api/law/batch   — plusieurs articles en une requête
  POST   /api/feedback    — signalement utilisateur (RGPD-safe, pas de logging d'IP)

Runs on port 8766. Nginx routes /api/* here.
"""
import asyncio
import json
import logging
import os
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

# Logger dédié (remplace les traceback.print_exc sauvages)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("justicelibre.token_server")

OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"

# Session store — moved off world-readable /tmp. Created with 0600 perms.
SESSION_DIR = "/run/justicelibre"
SESSION_FILE = f"{SESSION_DIR}/sessions.json"
# Legacy fallback for backward compat (à nettoyer plus tard)
_LEGACY_SESSION_FILE = "/tmp/justicelibre_sessions.json"

import threading
_LOCK = threading.Lock()


def _ensure_session_dir():
    try:
        os.makedirs(SESSION_DIR, exist_ok=True)
        os.chmod(SESSION_DIR, 0o700)
    except PermissionError:
        logger.warning("cannot create %s, fallback to /tmp (less secure)", SESSION_DIR)


def _load_sessions() -> dict:
    """Load sessions from secure location, fallback to legacy /tmp for backward compat."""
    for path in (SESSION_FILE, _LEGACY_SESSION_FILE):
        try:
            with open(path) as f:
                sessions = json.load(f)
            now = time.time()
            return {k: v for k, v in sessions.items() if v.get("expires", 0) > now}
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def _save_sessions(sessions: dict):
    _ensure_session_dir()
    target = SESSION_FILE
    try:
        # Atomic write with strict permissions (0600 = owner only)
        tmp = target + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(sessions, f)
        os.replace(tmp, target)
    except PermissionError:
        # Fallback legacy path if /run not writable
        with open(_LEGACY_SESSION_FILE, "w") as f:
            json.dump(sessions, f)
        try:
            os.chmod(_LEGACY_SESSION_FILE, 0o600)
        except OSError:
            pass


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
    # Sécurité : CORS restreint sur les endpoints sensibles (exchange OAuth2)
    _CORS_RESTRICTED_PATHS = {"/api/token"}
    _ALLOWED_ORIGIN = "https://justicelibre.org"
    _MAX_BODY_SIZE = 100_000  # 100 KB — plus gros = refusé

    def log_message(self, format, *args):
        # Ne pas logger les IP / user-agents en clair. Version silencieuse pour
        # réduire l'empreinte RGPD. Les erreurs passent par `logger` dédié.
        pass

    def _cors_origin(self) -> str:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in self._CORS_RESTRICTED_PATHS:
            return self._ALLOWED_ORIGIN
        return "*"

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._cors_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_DELETE(self):
        """Invalidation d'un session token (logout)."""
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path != "/api/token":
            return self._json_response(404, {"error": "Endpoint inconnu."})
        token = (qs.get("session_token", [""])[0] or "").strip()
        if not token:
            return self._json_response(400, {"error": "session_token requis"})
        with _LOCK:
            sessions = _load_sessions()
            removed = sessions.pop(token, None)
            if removed:
                _save_sessions(sessions)
        return self._json_response(200, {"ok": True, "invalidated": bool(removed)})

    def do_HEAD(self):
        """HEAD = GET sans le body. Googlebot et certains crawlers l'utilisent
        pour vérifier l'existence/validité d'une URL avant de la fetch.
        Sans cette méthode, BaseHTTPRequestHandler renvoie 501 -> Google
        considère l'URL comme non disponible. Solution : on délègue à do_GET
        et on tronque le body via un buffer wrapper.
        """
        # Wrappe wfile pour ne pas écrire le body (juste les headers)
        original_wfile = self.wfile
        class _NullWriter:
            def write(self, *a, **kw): pass
            def flush(self, *a, **kw): pass
        self.wfile = _NullWriter()  # pragma: no cover
        try:
            self.do_GET()
        finally:
            self.wfile = original_wfile

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/search":
            return self._handle_search(qs)
        if parsed.path == "/api/expand":
            return self._handle_expand(qs)
        if parsed.path == "/api/decision":
            return self._handle_decision(qs)
        if parsed.path == "/api/law":
            return self._handle_law(qs)
        if parsed.path == "/api/law/versions":
            return self._handle_law_versions(qs)
        # SSR routes pour Google + LLM (HTML indexable)
        m = re.match(r"^/decision/([a-z]+)/([A-Za-z0-9_\-:.]{4,128})$", parsed.path)
        if m:
            return self._handle_ssr_decision(m.group(1), m.group(2))
        if parsed.path == "/sitemap.xml":
            return self._handle_sitemap_index()
        if parsed.path == "/sitemap-static.xml":
            return self._handle_sitemap_static()
        m = re.match(r"^/sitemap-dila-(\d+)\.xml$", parsed.path)
        if m:
            return self._handle_sitemap_dila(int(m.group(1)))
        m = re.match(r"^/sitemap-jade-(\d+)\.xml$", parsed.path)
        if m:
            return self._handle_sitemap_jade(int(m.group(1)))
        m = re.match(r"^/sitemap-legi-(\d+)\.xml$", parsed.path)
        if m:
            return self._handle_sitemap_legi(int(m.group(1)))
        m = re.match(r"^/sitemap-(cedh|cjue|ariane|cnil|opendata)-(\d+)\.xml$", parsed.path)
        if m:
            return self._handle_sitemap_extra(m.group(1), int(m.group(2)))
        # Article de loi : /loi/CASF/L262-8 ou /loi/CJA/R772-8
        # Code: 1-15 caractères (CC, CASF, C.cons, L2005-102…)
        # Num : commence par lettre (LRDA) ou chiffre, puis chiffres + tirets
        m = re.match(r"^/loi/([\w.\-]{1,15})/([A-Z]?[\w.\-]{1,40})$", parsed.path)
        if m:
            return self._handle_ssr_law(m.group(1), m.group(2))
        if parsed.path in ("/api", "/api/"):
            return self._json_response(200, {
                "service": "justicelibre public REST API",
                "endpoints": {
                    "GET /api/search?q=&juridiction=&lieu=&limit=": "Recherche fédérée dans 5 sources",
                    "GET /api/decision?source=&id=": "Texte intégral d'une décision",
                    "GET /api/law?code=&num=&date=": "Article de loi (version à une date)",
                    "GET /api/law/versions?code=&num=": "Toutes les versions historiques d'un article",
                    "POST /api/law/batch": "Batch de plusieurs articles en une requête",
                    "POST /api/token": "Échange credentials PISTE → session token",
                },
                "docs": "https://justicelibre.org",
            })
        return self._json_response(404, {"error": f"Endpoint inconnu : {parsed.path}."})

    def _handle_expand(self, qs: dict):
        """Endpoint léger : retourne les termes étendus pour une query.

        GET /api/expand?q=harcèlement+moral&scope=judiciaire
        → {"q_original": ..., "q_expanded": ..., "trace": [{"original", "synonyms", "scope"}]}

        L'UI utilise ça pour afficher les pills "termes ajoutés" sous la barre.
        """
        q = (qs.get("q", [""])[0] or "").strip()
        scope = (qs.get("scope", ["toutes"])[0] or "toutes").strip().lower()
        if scope not in {"admin", "judiciaire", "europeen", "lois", "toutes"}:
            scope = "toutes"
        if not q:
            return self._json_response(400, {"error": "Paramètre `q` requis."})
        if len(q) > 500:
            return self._json_response(400, {"error": "Requête trop longue (max 500)."})
        try:
            from thesaurus_engine import get_engine
            engine = get_engine()
            expanded, trace = engine.expand_query(q, scope=scope)
            return self._json_response(200, {
                "q_original": q,
                "q_expanded": expanded,
                "scope": scope,
                "trace": trace,
            }, cache_seconds=300)
        except Exception:
            logger.exception("expand failed")
            return self._json_response(500, {"error": "Erreur interne moteur thésaurus."})

    def _handle_law(self, qs: dict):
        code = (qs.get("code", [""])[0] or "").strip()
        num = (qs.get("num", [""])[0] or "").strip()
        date = (qs.get("date", [""])[0] or "").strip()
        if not code or not num:
            return self._json_response(400, {"error": "Paramètres `code` et `num` requis."})
        if len(code) > 20 or len(num) > 30:
            return self._json_response(400, {"error": "Paramètres trop longs."})
        if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return self._json_response(400, {"error": "Format date invalide (attendu YYYY-MM-DD)."})
        try:
            from sources import warehouse as wh
            data = wh.sync_get_law(code, num, date or None)
            if data is None:
                return self._json_response(404, {"error": f"Article introuvable : {code} {num}."})
            return self._json_response(200, data)
        except Exception:
            logger.exception('handler failed')
            return self._json_response(500, {"error": "Erreur interne — entrepôt indisponible."})

    def _handle_law_versions(self, qs: dict):
        code = (qs.get("code", [""])[0] or "").strip()
        num = (qs.get("num", [""])[0] or "").strip()
        if not code or not num:
            return self._json_response(400, {"error": "Paramètres `code` et `num` requis."})
        try:
            from sources import warehouse as wh
            versions = wh.sync_get_law_versions(code, num)
            return self._json_response(200, {"code": code, "num": num, "versions": versions})
        except Exception:
            logger.exception('handler failed')
            return self._json_response(500, {"error": "Erreur interne."})

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
        # Dates : format ISO YYYY-MM-DD attendu, sinon ignoré silencieusement
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        date_min_raw = (qs.get("date_min", [""])[0] or "").strip()
        date_max_raw = (qs.get("date_max", [""])[0] or "").strip()
        date_min = date_min_raw if date_re.match(date_min_raw) else None
        date_max = date_max_raw if date_re.match(date_max_raw) else None
        # Si on interroge une seule source, limit_per_source = limit entier
        lps = limit if sources_only and len(sources_only) == 1 else max(5, limit // 2)
        try:
            data = asyncio.run(search_federated(
                q=q, juridiction=juri, lieu=lieu, limit=limit,
                limit_per_source=lps,
                offset=offset,
                sources_only=sources_only or None,
                timeout_s=timeout_s,
                date_min=date_min, date_max=date_max,
            ))
            return self._json_response(200, data)
        except Exception as e:
            # Ne pas exposer stacktrace/chemin serveur au client
            logger.exception('handler failed')
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
            logger.exception('handler failed')
            return self._json_response(500, {"error": "Erreur interne du serveur. Réessayez."})

    def do_POST(self):
        if self.path == "/api/law/batch":
            return self._handle_law_batch()
        if self.path == "/api/feedback":
            return self._handle_feedback()
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

    def _handle_feedback(self):
        """Endpoint append-only pour signalements utilisateur."""
        try:
            content_len = int(self.headers.get("Content-Length", "0"))
        except (ValueError, TypeError):
            return self._json_response(400, {"error": "Content-Length invalide"})
        if content_len <= 0 or content_len > 10000:
            return self._json_response(400, {"error": "Taille de message invalide."})
        raw = self.rfile.read(content_len)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._json_response(400, {"error": "JSON invalide"})
        msg = (body.get("message") or "").strip()[:3000]
        email = (body.get("email") or "").strip()[:120]
        context_raw = body.get("context") or {}
        ua = (body.get("ua") or "").strip()[:150]
        if len(msg) < 5:
            return self._json_response(400, {"error": "Message trop court."})
        # Whitelist des clés de contexte (évite log injection / pollution arbitraire)
        ALLOWED_CONTEXT_KEYS = {"source", "id", "url", "title"}
        context = {}
        if isinstance(context_raw, dict):
            for k in ALLOWED_CONTEXT_KEYS:
                v = context_raw.get(k)
                if v is not None:
                    context[k] = str(v)[:300]
        # RGPD : on NE stocke PAS l'IP (donnée à caractère personnel sans base
        # légale + sans info au point de collecte). Email optionnel, fourni
        # volontairement par l'utilisateur. UA tronqué (debug browser/OS).
        entry = {
            "ts": time.time(),
            "message": msg,
            "email": email,
            "context": context,
            "ua": ua,
        }
        try:
            os.makedirs("/var/log/justicelibre", exist_ok=True)
            with open("/var/log/justicelibre/feedback.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return self._json_response(200, {"ok": True})
        except Exception:
            logger.exception('handler failed')
            return self._json_response(500, {"error": "Erreur d'écriture"})

    def _handle_law_batch(self):
        try:
            content_len = int(self.headers.get("Content-Length", "0"))
        except (ValueError, TypeError):
            return self._json_response(400, {"error": "Content-Length invalide"})
        if content_len <= 0 or content_len > 50000:  # 50 KB max = ~500 refs
            return self._json_response(400, {"error": "Body trop gros."})
        raw = self.rfile.read(content_len)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._json_response(400, {"error": "JSON invalide"})
        refs = body.get("refs", [])
        date = (body.get("date") or "").strip() or None
        if not isinstance(refs, list) or not refs:
            return self._json_response(400, {"error": "`refs` doit être une liste non vide de {code, num}"})
        if len(refs) > 200:
            return self._json_response(400, {"error": "Max 200 refs par batch."})
        if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return self._json_response(400, {"error": "Format date invalide (YYYY-MM-DD)."})
        # Sanitize refs
        clean_refs = []
        for r in refs[:200]:
            if not isinstance(r, dict):
                continue
            code = str(r.get("code", ""))[:20]
            num = str(r.get("num", ""))[:30]
            if code and num:
                clean_refs.append({"code": code, "num": num})
        try:
            from sources import warehouse as wh
            items = wh.sync_get_laws_batch(clean_refs, date)
            return self._json_response(200, {"date": date, "count": len(items), "items": items})
        except Exception:
            logger.exception('handler failed')
            return self._json_response(500, {"error": "Erreur entrepôt."})

    def _handle_ssr_decision(self, source: str, decision_id: str):
        """Render HTML SSR d'une décision (indexable par Google + LLM)."""
        from ssr import render_decision, render_decision_404, fetch_decision_sync
        if source not in {"admin", "dila", "cedh", "cjue", "ariane", "cnil"}:
            return self._html_response(404, render_decision_404(source, decision_id))
        try:
            data = fetch_decision_sync(source, decision_id)
        except Exception:
            logger.exception('ssr decision failed')
            data = None
        if not data:
            return self._html_response(404, render_decision_404(source, decision_id))
        html = render_decision(source, decision_id, data)
        return self._html_response(200, html, cache_seconds=86400)

    def _handle_sitemap_index(self):
        from ssr import render_sitemap_index
        return self._xml_response(200, render_sitemap_index(), cache_seconds=3600)

    def _handle_sitemap_static(self):
        from ssr import render_sitemap_static
        return self._xml_response(200, render_sitemap_static(), cache_seconds=86400)

    def _handle_sitemap_dila(self, page: int):
        from ssr import render_sitemap_dila
        return self._xml_response(200, render_sitemap_dila(page), cache_seconds=86400)

    def _handle_sitemap_jade(self, page: int):
        from ssr import render_sitemap_jade
        return self._xml_response(200, render_sitemap_jade(page), cache_seconds=86400)

    def _handle_sitemap_legi(self, page: int):
        from ssr import render_sitemap_legi
        return self._xml_response(200, render_sitemap_legi(page), cache_seconds=86400)

    def _handle_sitemap_extra(self, kind: str, page: int):
        """Sub-sitemaps (cedh/cjue/ariane/cnil/opendata).
        Opendata cache court (1h) car le DL est en cours et la liste grandit.
        """
        from ssr import (render_sitemap_cedh, render_sitemap_cjue,
                         render_sitemap_ariane, render_sitemap_cnil,
                         render_sitemap_opendata)
        renderers = {
            "cedh": render_sitemap_cedh, "cjue": render_sitemap_cjue,
            "ariane": render_sitemap_ariane, "cnil": render_sitemap_cnil,
            "opendata": render_sitemap_opendata,
        }
        fn = renderers.get(kind)
        if not fn:
            return self._xml_response(404, "<error>unknown</error>", cache_seconds=60)
        cache = 3600 if kind == "opendata" else 86400
        return self._xml_response(200, fn(page), cache_seconds=cache)

    def _handle_ssr_law(self, code: str, num: str):
        """Render HTML SSR d'un article de loi."""
        from ssr import render_law, render_law_404
        from sources.warehouse import sync_get_law
        try:
            data = sync_get_law(code, num)
        except Exception:
            logger.exception('ssr law failed')
            data = None
        if not data:
            return self._html_response(404, render_law_404(code, num))
        return self._html_response(200, render_law(code, num, data), cache_seconds=86400)

    def _html_response(self, code: int, html: str, cache_seconds: int = 0):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cache_seconds > 0:
            self.send_header("Cache-Control", f"public, max-age={cache_seconds}")
        self.end_headers()
        self.wfile.write(body)

    def _xml_response(self, code: int, xml: str, cache_seconds: int = 3600):
        body = xml.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", f"public, max-age={cache_seconds}")
        self.end_headers()
        self.wfile.write(body)

    def _json_response(self, code: int, data: dict, cache_seconds: int = 0):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        if cache_seconds > 0:
            self.send_header("Cache-Control", f"public, max-age={cache_seconds}")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Silence logs


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8766), TokenHandler)
    print("API server on http://127.0.0.1:8766/api/{token,search,decision}")
    server.serve_forever()
