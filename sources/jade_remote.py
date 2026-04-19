"""Wrapper MCP pour la jurisprudence administrative (bulk JADE).

Interroge le warehouse distant (al-uzza) qui expose `jade.db` (7.8 Go,
~4M décisions CE + 9 CAA + 40 TA avec full text).

Différence critique avec `juriadmin.py` (API live date-sorted) :
- Ranking BM25 (vraie pertinence)
- Filtrage par date range
- Pagination offset
- Snippets automatiques

Remplace la plupart des usages de `search_juridiction`, qui devient
`search_admin_recent` pour les consultations chronologiques.
"""
from __future__ import annotations

from typing import Any

from . import warehouse as wh


async def search(
    query: str,
    juridiction: str | None = None,
    sort: str = "relevance",
    date_min: str | None = None,
    date_max: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Full-text search sur jade.db via BM25 ranking.

    `juridiction` : code court (CE, CAA75, TA75...) — pas encore filtré
    server-side dans warehouse (à ajouter si besoin). Pour l'instant on
    passe la query brute.
    """
    limit = max(1, min(int(limit), 50))
    q = query
    # Si juridiction fournie, enrichir la query
    if juridiction:
        q = f"({query}) AND \"{juridiction}\""
    data = await wh.search_fond(
        "jade", q,
        limit=limit, offset=offset, sort=sort,
        date_min=date_min, date_max=date_max,
    )
    # Normalize output
    decisions = []
    for h in data.get("results", []):
        decisions.append({
            "id": h.get("id"),
            "juridiction": h.get("juridiction"),
            "numero": h.get("numero"),
            "date": h.get("date"),
            "titre": h.get("titre"),
            "extract": h.get("extract"),
        })
    return {
        "total": data.get("total", 0),
        "returned": len(decisions),
        "limit": limit,
        "offset": offset,
        "decisions": decisions,
    }


async def get_decision(decision_id: str) -> dict[str, Any] | None:
    return await wh.get_decision_remote("jade", decision_id)
