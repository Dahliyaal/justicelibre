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
