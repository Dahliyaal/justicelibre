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

import re
from typing import Any

from . import warehouse as wh

# Numéro de requête administrative :
# - CE : pur numérique 5-7 chiffres (ex: "497566", "358109")
# - CAA/TA : format alphanumérique YY+CC+NNNN(N) (ex: "03NC01126" Nancy,
#   "22PA05407" Paris, "23DA00671" Douai, "08VE01126" Versailles…)
# Préfixe "n°" optionnel.
_NUMERO_RE = re.compile(
    r'^(?:n[°o]?\s*)?(\d{5,7}|\d{2}[A-Z]{2}\d{4,6})$',
    re.IGNORECASE,
)


def _normalize_hit(h: dict) -> dict:
    return {
        "id": h.get("id"),
        "juridiction": h.get("juridiction"),
        "numero": h.get("numero"),
        "date": h.get("date"),
        "titre": h.get("titre"),
        "extract": h.get("extract"),
    }


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

    Détecte automatiquement si la query est un numéro de requête (5-7 chiffres)
    et fait un lookup SQL exact plutôt que FTS5 — évite le cas où FTS5 ne matche
    pas les champs de métadonnées et retourne 0 résultat alors que la décision existe.
    """
    limit = max(1, min(int(limit), 50))

    # Détection numéro pur → lookup SQL exact
    m = _NUMERO_RE.match(query.strip())
    if m:
        num = m.group(1)
        results = await wh.lookup_by_numero("jade", num, juridiction=juridiction)
        if results:
            return {
                "total": len(results),
                "returned": len(results),
                "limit": limit,
                "offset": offset,
                "lookup_by_numero": True,
                "decisions": [_normalize_hit(r) for r in results],
            }
        # Fallback FTS5 si le lookup exact ne trouve rien (numéro cité dans le texte ?)

    q = query
    if juridiction:
        q = f"({query}) AND \"{juridiction}\""
    data = await wh.search_fond(
        "jade", q,
        limit=limit, offset=offset, sort=sort,
        date_min=date_min, date_max=date_max,
    )
    return {
        "total": data.get("total", 0),
        "returned": len(data.get("results", [])),
        "limit": limit,
        "offset": offset,
        "decisions": [_normalize_hit(h) for h in data.get("results", [])],
    }


async def get_decision(decision_id: str) -> dict[str, Any] | None:
    return await wh.get_decision_remote("jade", decision_id)


async def get_admin_decision(numero: str, juridiction: str | None = None) -> dict[str, Any] | None:
    """Récupère une décision administrative par son numéro de requête exact.

    Essaie d'abord le bulk JADE DILA (lookup SQL exact), puis si introuvable
    tente l'API live opendata.justice-administrative.fr — les deux sources ont
    des couvertures différentes (JADE : anciennes + complètes ; live : récentes).

    Args:
        numero: numéro de requête (ex: "2116343", "358109", "497566")
        juridiction: filtre optionnel sur la juridiction (nom complet ou code court
            ex: "Conseil d'Etat", "Tribunal Administratif de Paris", "TA75")

    Returns:
        La décision ou None si introuvable dans les deux sources.
    """
    if not numero.strip():
        return None
    num_clean = numero.strip().replace(" ", "").lstrip("n°oN° \t")

    # 1. Lookup SQL exact dans JADE bulk
    results = await wh.lookup_by_numero("jade", num_clean, juridiction=juridiction)
    if results:
        return results[0]

    # 2. Fallback sur API live (opendata.justice-administrative.fr)
    try:
        import httpx
        from . import juriadmin
        # Choisir la cible : si juridiction fournie et ressemble à un code court connu, l'utiliser
        juri_code = "CE-CAA"  # couvre CE + 9 CAA + 40 TA par défaut
        if juridiction:
            juri_up = juridiction.upper()
            if juri_up in juriadmin.VALID_JURI:
                juri_code = juri_up
            elif "ETAT" in juri_up or juri_up == "CE":
                juri_code = "CE"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            data = await juriadmin.search(client, query=num_clean, juridiction=juri_code, limit=10)
        hits = data.get("decisions", [])
        # Chercher un match exact sur numero_dossier
        for h in hits:
            if str(h.get("numero_dossier", "")).replace(" ", "") == num_clean:
                return h
        # Sinon le premier résultat si query est le numéro seul
        return hits[0] if hits else None
    except Exception:
        return None


async def get_ce_decision(numero: str) -> dict[str, Any] | None:
    """Récupère une décision du Conseil d'État par son numéro (ex: "497566").

    Essaie d'abord le bulk JADE (lookup SQL exact), puis si introuvable
    tente ArianeWeb Sinequa (qui couvre des décisions plus récentes ou
    non présentes dans le bulk JADE).
    """
    if not numero.strip():
        return None
    num_clean = numero.strip().replace(" ", "").lstrip("n°oN° \t")

    # 1. Lookup SQL exact dans JADE
    results = await wh.lookup_by_numero("jade", num_clean, juridiction="Conseil d'Etat")
    if results:
        return results[0]

    # 2. Fallback ArianeWeb (Sinequa) — pour les décisions hors bulk JADE
    try:
        import httpx
        from . import ariane
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            data = await ariane.search(client, num_clean, limit=5)
        hits = data.get("decisions", [])
        # Cherche un match exact sur le numéro dans les résultats
        for h in hits:
            if str(h.get("numero", "")).replace(" ", "") == num_clean:
                return h
        # Sinon retourner le premier hit si pertinent (Sinequa filtre déjà sur CE)
        return hits[0] if hits else None
    except Exception:
        return None
