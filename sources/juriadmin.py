"""Wrapper for opendata.justice-administrative.fr hidden Elasticsearch API.

Discovered endpoints (reverse-engineered from the React bundle):
  - /recherche/api/model_search_juri/openData/{juri}/{query}/{limit}
      Full-text search. {juri} accepts the single codes "CE" and "CE-CAA"
      plus per-court codes: TA06…TA109 (40 tribunaux administratifs including
      overseas) and CAA13…CAA78 (9 cours administratives d'appel). A bare
      "TA" or "CAA" returns empty — the API wants the specific court code.

  - /recherche/api/elastic/decisions/{decision_id}/bm9TZWNvbmR2YWx1ZQ==
      Decision detail (includes full text in `_source.paragraph`, where
      `$$$` is the paragraph separator). The base64 suffix is literally
      "noSecondvalue" — the React front-end passes it when no secondary
      parameter is set.

Full coverage observed (April 2026):
  Conseil d'État + 9 CAA + 40 TAs = ~1,050,000 decisions.
"""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import httpx

BASE = "https://opendata.justice-administrative.fr/recherche/api"

# Literal base64 of "noSecondvalue" — sentinel the React app uses when the
# detail view has no secondary parameter (a related-decision lookup slot).
NO_SECOND_VALUE = "bm9TZWNvbmR2YWx1ZQ=="

# Canonical names probed from the API on April 2026. The key is the code the
# API accepts; the value is the name returned in Nom_Juridiction.
TRIBUNAUX_ADMIN: dict[str, str] = {
    "TA06": "Tribunal Administratif de Nice",
    "TA13": "Tribunal Administratif de Marseille",
    "TA14": "Tribunal Administratif de Caen",
    "TA20": "Tribunal Administratif de Bastia",
    "TA21": "Tribunal Administratif de Dijon",
    "TA25": "Tribunal Administratif de Besançon",
    "TA30": "Tribunal Administratif de Nîmes",
    "TA31": "Tribunal Administratif de Toulouse",
    "TA33": "Tribunal Administratif de Bordeaux",
    "TA34": "Tribunal Administratif de Montpellier",
    "TA35": "Tribunal Administratif de Rennes",
    "TA38": "Tribunal Administratif de Grenoble",
    "TA44": "Tribunal Administratif de Nantes",
    "TA45": "Tribunal Administratif d'Orléans",
    "TA51": "Tribunal Administratif de Châlons-en-Champagne",
    "TA54": "Tribunal Administratif de Nancy",
    "TA59": "Tribunal Administratif de Lille",
    "TA63": "Tribunal Administratif de Clermont-Ferrand",
    "TA64": "Tribunal Administratif de Pau",
    "TA67": "Tribunal Administratif de Strasbourg",
    "TA69": "Tribunal Administratif de Lyon",
    "TA75": "Tribunal Administratif de Paris",
    "TA76": "Tribunal Administratif de Rouen",
    "TA77": "Tribunal Administratif de Melun",
    "TA78": "Tribunal Administratif de Versailles",
    "TA80": "Tribunal Administratif d'Amiens",
    "TA83": "Tribunal Administratif de Toulon",
    "TA86": "Tribunal Administratif de Poitiers",
    "TA87": "Tribunal Administratif de Limoges",
    "TA93": "Tribunal Administratif de Montreuil",
    "TA95": "Tribunal Administratif de Cergy-Pontoise",
    "TA101": "Tribunal Administratif de La Réunion",
    "TA102": "Tribunal Administratif de la Martinique",
    "TA103": "Tribunal Administratif de la Polynésie française",
    "TA104": "Tribunal Administratif de Nouvelle-Calédonie",
    "TA105": "Tribunal Administratif de la Guadeloupe",
    "TA106": "Tribunal Administratif de la Guyane",
    "TA107": "Tribunal Administratif de Mayotte",
    "TA108": "Tribunal Administratif de St Martin",
    "TA109": "Tribunal Administratif de St Barthélemy",
}

COURS_ADMIN_APPEL: dict[str, str] = {
    "CAA13": "Cour administrative d'appel de Marseille",
    "CAA31": "Cour administrative d'appel de Toulouse",
    "CAA33": "Cour administrative d'appel de Bordeaux",
    "CAA44": "Cour administrative d'appel de Nantes",
    "CAA54": "Cour administrative d'appel de Nancy",
    "CAA59": "Cour administrative d'appel de Douai",
    "CAA69": "Cour administrative d'appel de Lyon",
    "CAA75": "Cour administrative d'appel de Paris",
    "CAA78": "Cour administrative d'appel de Versailles",
}

CONSEIL_ETAT: dict[str, str] = {
    "CE": "Conseil d'État",
    "CE-CAA": "Conseil d'État + cours administratives d'appel (jurisprudence citée)",
}

VALID_JURI: dict[str, str] = {**CONSEIL_ETAT, **COURS_ADMIN_APPEL, **TRIBUNAUX_ADMIN}


def _clean(value: Any) -> Any:
    # The API stores missing ECLIs as the literal string "undefined".
    if value == "undefined":
        return None
    return value


def _normalize_hit(hit: dict[str, Any]) -> dict[str, Any]:
    src = hit.get("_source", {})
    return {
        "id": src.get("Identification", "").removesuffix(".xml"),
        "ecli": _clean(src.get("Numero_ECLI")),
        "juridiction_code": src.get("Code_Juridiction"),
        "juridiction_name": src.get("Nom_Juridiction"),
        "formation": src.get("Formation_Jugement"),
        "numero_dossier": src.get("Numero_Dossier"),
        "type": src.get("Type_Decision"),
        "date_lecture": src.get("Date_Lecture"),
        "publication_code": src.get("Code_Publication"),
        "last_modified": src.get("lastModified"),
    }


async def search(
    client: httpx.AsyncClient,
    query: str,
    juridiction: str = "CE",
    limit: int = 20,
) -> dict[str, Any]:
    if juridiction not in VALID_JURI:
        raise ValueError(
            f"unknown juridiction code: {juridiction!r}. "
            f"Valid codes: CE, CE-CAA, any TAxx ({len(TRIBUNAUX_ADMIN)} courts), "
            f"any CAAxx ({len(COURS_ADMIN_APPEL)} courts)."
        )
    if not query.strip():
        raise ValueError("query must be non-empty")
    safe_query = quote(query, safe="")
    url = f"{BASE}/model_search_juri/openData/{juridiction}/{safe_query}/{int(limit)}"
    r = await client.get(url)
    r.raise_for_status()
    body = r.json()["decisions"]["body"]["hits"]
    return {
        "juridiction_code": juridiction,
        "juridiction_name": VALID_JURI[juridiction],
        "total": body["total"]["value"],
        "returned": len(body["hits"]),
        "decisions": [_normalize_hit(h) for h in body["hits"]],
    }


async def search_many(
    client: httpx.AsyncClient,
    query: str,
    juridictions: list[str],
    limit_per_court: int = 5,
) -> dict[str, Any]:
    """Fan out a single query across multiple courts in parallel.

    Useful for "find me all decisions about X across all TAs", returning a
    flat merged list sorted by date (most recent first).
    """
    async def _one(juri: str) -> dict[str, Any] | None:
        try:
            return await search(client, query=query, juridiction=juri, limit=limit_per_court)
        except Exception as exc:
            return {"juridiction_code": juri, "error": str(exc)}

    results = await asyncio.gather(*(_one(j) for j in juridictions))
    merged: list[dict[str, Any]] = []
    per_court_totals: dict[str, int] = {}
    errors: dict[str, str] = {}
    for res in results:
        if res is None:
            continue
        if "error" in res:
            errors[res["juridiction_code"]] = res["error"]
            continue
        per_court_totals[res["juridiction_code"]] = res["total"]
        merged.extend(res["decisions"])
    # Sort by date_lecture desc (missing dates go last)
    merged.sort(key=lambda d: d.get("date_lecture") or "", reverse=True)
    return {
        "query": query,
        "courts_queried": len(juridictions),
        "per_court_totals": per_court_totals,
        "total_returned": len(merged),
        "decisions": merged,
        "errors": errors or None,
    }


async def get_decision(
    client: httpx.AsyncClient,
    decision_id: str,
) -> dict[str, Any] | None:
    decision_id = decision_id.removesuffix(".xml")
    url = f"{BASE}/elastic/decisions/{decision_id}/{NO_SECOND_VALUE}"
    r = await client.get(url)
    r.raise_for_status()
    hits = r.json()["decisions"]["body"]["hits"]["hits"]
    if not hits:
        return None
    src = hits[0]["_source"]
    paragraph = src.get("paragraph", "")
    segments = [p.strip() for p in paragraph.split("$$$") if p.strip()]
    return {
        "id": src.get("Identification", "").removesuffix(".xml"),
        "ecli": _clean(src.get("Numero_ECLI")),
        "juridiction_code": src.get("Code_Juridiction"),
        "juridiction_name": src.get("Nom_Juridiction"),
        "formation": src.get("Formation_Jugement"),
        "numero_dossier": src.get("Numero_Dossier"),
        "type": src.get("Type_Decision"),
        "date_lecture": src.get("Date_Lecture"),
        "publication_code": src.get("Code_Publication"),
        "last_modified": src.get("lastModified"),
        "text_segments": segments,
        "full_text": "\n\n".join(segments),
    }
