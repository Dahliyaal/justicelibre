"""Wrapper MCP pour les délibérations CNIL.

cnil.db contient les 26k+ délibérations de la Commission nationale de
l'informatique et des libertés (droit RGPD, données personnelles).
"""
from __future__ import annotations

from typing import Any

from . import warehouse as wh


async def search(
    query: str,
    limit: int = 20,
    offset: int = 0,
    sort: str = "relevance",
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    data = await wh.search_fond("cnil", query, limit=limit, offset=offset, sort=sort)
    delibs = []
    for h in data.get("results", []):
        delibs.append({
            "id": h.get("id"),
            "numero": h.get("numero"),
            "titre": h.get("titre"),
            "date": h.get("date"),
            "formation": h.get("formation"),
            "extract": h.get("extract"),
        })
    return {
        "total": data.get("total", 0),
        "returned": len(delibs),
        "deliberations": delibs,
    }


async def get_deliberation(delib_id: str) -> dict[str, Any] | None:
    return await wh.get_decision_remote("cnil", delib_id)
