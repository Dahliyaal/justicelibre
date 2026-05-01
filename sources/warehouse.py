"""HTTP client for the warehouse service on al-uzza.

Connects to the private HTTP bridge that exposes the bulk DILA SQLite DBs
(legi, jade, jorf, kali, cnil) living on al-uzza. Used by sources/legi.py
and the future remote search modules.

Caching : LRU in-memory (per-process) on article lookups. Articles are
immutable per (code, num, date) so this is safe.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

WAREHOUSE_URL = os.environ.get("JL_WAREHOUSE_URL", "http://46.224.173.253:8001")
KEY_FILE = Path(os.environ.get("JL_WAREHOUSE_KEY_FILE", "/etc/justicelibre/warehouse.key"))

try:
    _KEY = KEY_FILE.read_text().strip()
except FileNotFoundError:
    _KEY = ""

_HEADERS = {"X-Warehouse-Key": _KEY, "Accept": "application/json"}
_TIMEOUT = httpx.Timeout(15.0, connect=3.0)


def _raise_if_no_key():
    if not _KEY:
        raise RuntimeError(f"warehouse key missing ({KEY_FILE}). Cannot reach warehouse.")


# ─── Async client (used by token_server.py async handlers) ────────────

async def _aget(path: str, **params) -> dict | None:
    _raise_if_no_key()
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = await client.get(f"{WAREHOUSE_URL}{path}", params=params)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


async def _apost(path: str, body: dict) -> dict:
    _raise_if_no_key()
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = await client.post(f"{WAREHOUSE_URL}{path}", json=body)
        r.raise_for_status()
        return r.json()


async def get_law(code: str, num: str, date: str | None = None) -> dict | None:
    """Fetch an article at a given date. Returns None if not found."""
    params = {"code": code, "num": num}
    if date:
        params["date"] = date
    return await _aget("/v1/law", **params)


async def get_law_versions(code: str, num: str) -> list[dict]:
    data = await _aget("/v1/law/versions", code=code, num=num)
    return (data or {}).get("versions", [])


def sync_get_law(code: str, num: str, date: str | None = None) -> dict | None:
    """Variant sync de get_law pour les handlers HTTPServer (SSR /loi/...)."""
    if not _KEY:
        return None
    try:
        params = {"code": code, "num": num}
        if date:
            params["date"] = date
        r = httpx.get(f"{WAREHOUSE_URL}/v1/law", params=params,
                      headers=_HEADERS, timeout=10.0)
        if r.status_code == 404 or r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


async def get_laws_batch(refs: list[dict], date: str | None = None) -> list[dict]:
    """Bulk resolve articles in a single round-trip."""
    body = {"refs": refs}
    if date:
        body["date"] = date
    data = await _apost("/v1/law/batch", body)
    return data.get("items", [])


async def search_fond(
    fond: str,
    query: str,
    limit: int = 20,
    offset: int = 0,
    sort: str = "relevance",
    date_min: str | None = None,
    date_max: str | None = None,
    code: str | None = None,
) -> dict:
    """Full-text search on a specific fond."""
    params = {"q": query, "limit": limit, "offset": offset, "sort": sort}
    if date_min:
        params["date_min"] = date_min
    if date_max:
        params["date_max"] = date_max
    if code:
        params["code"] = code
    data = await _aget(f"/v1/search/{fond}", **params)
    return data or {"fond": fond, "total": 0, "results": []}


async def get_decision_remote(fond: str, decision_id: str) -> dict | None:
    return await _aget(f"/v1/decision/{fond}/{decision_id}")


async def count_fond(fond: str) -> int:
    """Total rows dans un fond (avec filtre VIGUEUR pour LEGI)."""
    data = await _aget(f"/v1/count/{fond}")
    return int((data or {}).get("total", 0)) if data else 0


def sync_count_fond(fond: str) -> int:
    """Variant sync pour les handlers HTTPServer."""
    import httpx as _httpx
    try:
        r = _httpx.get(f"{WAREHOUSE_URL}/v1/count/{fond}",
                       headers=_HEADERS, timeout=10.0)
        if r.status_code != 200:
            return 0
        return int(r.json().get("total", 0))
    except Exception:
        return 0


async def enumerate_fond(fond: str, offset: int = 0, limit: int = 1000) -> list[dict]:
    """Liste paginée d'IDs (+ date / num) pour générer les sub-sitemaps."""
    data = await _aget(f"/v1/enumerate/{fond}", offset=offset, limit=limit)
    return (data or {}).get("results", []) if data else []


def sync_enumerate_fond(fond: str, offset: int = 0, limit: int = 1000) -> list[dict]:
    import httpx as _httpx
    try:
        r = _httpx.get(f"{WAREHOUSE_URL}/v1/enumerate/{fond}",
                       params={"offset": offset, "limit": limit},
                       headers=_HEADERS, timeout=15.0)
        if r.status_code != 200:
            return []
        return r.json().get("results", [])
    except Exception:
        return []


async def lookup_by_numero(fond: str, numero: str, juridiction: str | None = None) -> list[dict]:
    """Exact numero lookup (SQL =), évite FTS5 noyé sur numéros courts."""
    params = {"numero": numero}
    if juridiction:
        params["juridiction"] = juridiction
    data = await _aget(f"/v1/lookup/{fond}", **params)
    return (data or {}).get("results", []) if data else []


async def build_url(identifier: str, legitext: str | None = None, date: str | None = None) -> str | None:
    """Construit l'URL canonique (source officielle) d'un document à partir
    de son identifiant. Délègue au warehouse qui connaît tous les patterns.

    `date` (YYYY-MM-DD) — si fourni, pointe vers la version de l'article
    en vigueur à cette date (URLs Légifrance versionnées).
    """
    params = {"id": identifier}
    if legitext:
        params["legitext"] = legitext
    if date:
        params["date"] = date
    data = await _aget("/v1/url", **params)
    return (data or {}).get("source_url") if data else None


async def resolve_law_number(numero: str) -> dict | None:
    """Résout un numéro de loi/ordonnance/décret (ex: '68-1250', '79-587')
    vers son LEGITEXT/JORFTEXT + infos (titre, date, nombre d'articles).
    """
    data = await _aget("/v1/law/resolve", numero=numero)
    return data if data else None


# ─── Sync wrappers for non-async callers (like token_server handlers) ──

def sync_get_law(code: str, num: str, date: str | None = None) -> dict | None:
    _raise_if_no_key()
    params = {"code": code, "num": num}
    if date:
        params["date"] = date
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = client.get(f"{WAREHOUSE_URL}/v1/law", params=params)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


def sync_get_laws_batch(refs: list[dict], date: str | None = None) -> list[dict]:
    _raise_if_no_key()
    body = {"refs": refs}
    if date:
        body["date"] = date
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = client.post(f"{WAREHOUSE_URL}/v1/law/batch", json=body)
        r.raise_for_status()
        return r.json().get("items", [])


def sync_get_law_versions(code: str, num: str) -> list[dict]:
    _raise_if_no_key()
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        r = client.get(f"{WAREHOUSE_URL}/v1/law/versions", params={"code": code, "num": num})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json().get("versions", [])


# ─── Health check utility ────────────────────────────────────────────

def sync_health() -> dict | None:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{WAREHOUSE_URL}/v1/health")
            r.raise_for_status()
            return r.json()
    except Exception:
        return None
