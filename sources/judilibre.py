"""Wrapper for the Judilibre API (Cour de cassation) via PISTE OAuth2.

Covers judicial courts: Cour de cassation, cours d'appel, tribunaux
judiciaires, tribunaux de commerce.

Requires OAuth2 Client Credentials (client_id + client_secret) from PISTE.
Users get them for free at https://piste.gouv.fr/registration.

The token exchange happens server-side: credentials in, Bearer token out,
credentials forgotten. Tokens are cached for 50 minutes (PISTE tokens
expire after 60 min). Session data is purged after 1 hour of inactivity
(RGPD compliance).
"""
from __future__ import annotations

import time
import threading
from typing import Any

import httpx

BASE = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"
OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"

JURIDICTIONS = {
    "cc": "Cour de cassation",
    "ca": "Cours d'appel",
    "tj": "Tribunaux judiciaires",
    "tcom": "Tribunaux de commerce",
}

# Session token cache: {session_key: {"token": str, "expires": float}}
_TOKEN_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_TOKEN_TTL = 3000  # 50 minutes (PISTE tokens last 60 min)


def _cache_key(client_id: str) -> str:
    return client_id[:8]


def _cleanup_expired():
    now = time.time()
    with _CACHE_LOCK:
        expired = [k for k, v in _TOKEN_CACHE.items() if now > v["expires"]]
        for k in expired:
            del _TOKEN_CACHE[k]


async def _get_token(
    client: httpx.AsyncClient,
    client_id: str,
    client_secret: str,
) -> str:
    key = _cache_key(client_id)
    _cleanup_expired()

    with _CACHE_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if cached and time.time() < cached["expires"]:
            return cached["token"]

    r = await client.post(
        OAUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "openid",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    data = r.json()
    token = data["access_token"]

    with _CACHE_LOCK:
        _TOKEN_CACHE[key] = {
            "token": token,
            "expires": time.time() + _TOKEN_TTL,
        }
    return token


def _normalize_decision(doc: dict[str, Any]) -> dict[str, Any]:
    """Forme allégée, pour une LIGNE DE RÉSULTAT de recherche."""
    return {
        "id": doc.get("id"),
        "jurisdiction": doc.get("jurisdiction"),
        "chamber": doc.get("chamber"),
        "number": doc.get("number"),
        "ecli": doc.get("ecli"),
        "date": doc.get("decision_date"),
        "solution": doc.get("solution"),
        "type": doc.get("type"),
        "publication": doc.get("publication"),
        "summary": doc.get("summary"),
        "highlights": doc.get("highlights"),
    }


def _normalize_full_decision(doc: dict[str, Any]) -> dict[str, Any]:
    """Décision COMPLÈTE, pour une récupération par identifiant.

    ⚠️ `get_decision_judiciaire` réutilisait la forme allégée ci-dessus —
    celle des lignes de résultat — et renvoyait donc tout SAUF le texte,
    alors que c'est sa raison d'être. Vérifié le 23 août 2026 en
    interrogeant PISTE directement : l'endpoint `/decision` renvoie bien
    `text` (11 742 caractères sur l'arrêt testé), plus les visas, les
    rapprochements de jurisprudence et la timeline de procédure —
    intégralement jetés. Le tool répondait « OK » avec un texte vide.
    """
    out = _normalize_decision(doc)
    out.update({
        "text": doc.get("text") or "",
        "full_text": doc.get("text") or "",   # alias : nom utilisé ailleurs
        "zones": doc.get("zones"),
        "numbers": doc.get("numbers"),
        "visa": doc.get("visa"),
        "themes": doc.get("themes"),
        "timeline": doc.get("timeline"),
        "rapprochements": doc.get("rapprochements"),
        "titles_and_summaries": doc.get("titlesAndSummaries"),
        "contested": doc.get("contested"),
        "forward": doc.get("forward"),
        "nac": doc.get("nac"),
        "portalis": doc.get("portalis"),
        "source": doc.get("source"),
        "update_date": doc.get("update_date"),
    })
    return out


async def search(
    client: httpx.AsyncClient,
    client_id: str,
    client_secret: str,
    query: str,
    juridiction: str | None = None,
    limit: int = 20,
    page: int = 0,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must be non-empty")

    token = await _get_token(client, client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, Any] = {
        "query": query,
        "page_size": min(int(limit), 50),
        "page": page,
    }
    if juridiction and juridiction in JURIDICTIONS:
        params["jurisdiction"] = juridiction

    r = await client.get(f"{BASE}/search", headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    return {
        # ⚠️ Judilibre renvoie `total`, pas `total_results` : le champ lu
        # n'a jamais existé, donc `search_judiciaire` annonçait
        # invariablement « total: 0 » tout en servant des résultats — un
        # client raisonnable en conclut qu'il n'y a rien et s'arrête là.
        # Vérifié le 23 août 2026 en interrogeant PISTE directement :
        # « licenciement » → total = 76 041.
        "total": data.get("total", data.get("total_results", 0)),
        "returned": len(results),
        "page": page,
        "decisions": [_normalize_decision(d) for d in results],
    }


async def get_decision(
    client: httpx.AsyncClient,
    client_id: str,
    client_secret: str,
    decision_id: str,
) -> dict[str, Any] | None:
    token = await _get_token(client, client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.get(f"{BASE}/decision", headers=headers, params={"id": decision_id})
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    # Même normaliseur que le chemin par jeton de session : c'est la
    # divergence entre les deux qui avait produit un tool renvoyant tout
    # sauf le texte (23 août 2026).
    return _normalize_full_decision(data)
