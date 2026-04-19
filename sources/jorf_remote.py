"""Wrapper MCP pour le Journal officiel de la République française (JORF).

Interroge le warehouse distant qui expose `jorf.db` (1,1 Go, textes JO
post-1990 : lois non codifiées, décrets, arrêtés, circulaires,
ordonnances — TOUT ce qui n'est pas un code consolidé).
"""
from __future__ import annotations

from typing import Any

from . import warehouse as wh


async def search(
    query: str,
    nature: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "relevance",
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    q = query
    if nature:
        q = f"({query}) AND \"{nature.upper()}\""
    data = await wh.search_fond(
        "jorf", q,
        limit=limit, offset=offset, sort=sort,
        date_min=date_min, date_max=date_max,
    )
    textes = []
    for h in data.get("results", []):
        textes.append({
            "id": h.get("id"),
            "titre": h.get("titre"),
            "nature": h.get("nature"),
            "date_publi": h.get("date"),
            "ministere": h.get("ministere"),
            "extract": h.get("extract"),
        })
    return {
        "total": data.get("total", 0),
        "returned": len(textes),
        "limit": limit, "offset": offset,
        "textes": textes,
    }


async def get_text(jorftext: str) -> dict[str, Any] | None:
    return await wh.get_decision_remote("jorf", jorftext)
