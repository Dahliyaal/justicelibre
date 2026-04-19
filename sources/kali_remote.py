"""Wrapper MCP pour les conventions collectives (KALI).

kali.db contient ~les conventions collectives, accords de branche, et
avenants (identifiés par leur IDCC — identifiant à 4 chiffres).
"""
from __future__ import annotations

from typing import Any

from . import warehouse as wh


async def search(
    query: str,
    idcc: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "relevance",
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    q = query
    if idcc:
        q = f"({query}) AND \"{idcc}\""
    data = await wh.search_fond(
        "kali", q, limit=limit, offset=offset, sort=sort,
    )
    textes = []
    for h in data.get("results", []):
        textes.append({
            "id": h.get("id"),
            "idcc": h.get("idcc"),
            "titre": h.get("titre"),
            "nature": h.get("nature"),
            "date_publi": h.get("date"),
            "extract": h.get("extract"),
        })
    return {
        "total": data.get("total", 0),
        "returned": len(textes),
        "textes": textes,
    }


async def get_text(kali_id: str) -> dict[str, Any] | None:
    return await wh.get_decision_remote("kali", kali_id)
