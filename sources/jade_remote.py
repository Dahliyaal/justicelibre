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
import unicodedata
from typing import Any

from query_intent import match_admin_docket, normalize_numero

from . import warehouse as wh


def _fold(s: str) -> str:
    """Minuscules sans accents, pour comparer des noms de juridiction."""
    return "".join(
        c for c in unicodedata.normalize("NFD", (s or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def _juri_type(name: str) -> str:
    """Ordre de juridiction administrative : 'ce', 'caa', 'ta', 'tc' ou ''.

    La base écrit le même tribunal de dix façons (« CAA de LYON », « Cour
    Administrative d'Appel de Lyon », « TA69 »…), d'où un rapprochement par
    ville côté warehouse. Mais la ville seule ne distingue PAS le TA de la
    CAA de la même ville : demander le TA de Lyon renvoyait la CAA de Lyon,
    sans le signaler (constaté le 23 août 2026 sur 19LY02575). D'où ce
    contrôle d'ordre, qui doit être satisfait AVANT d'accepter une réponse.
    """
    n = _fold(name)
    if "conflit" in n:
        return "tc"
    if re.search(r"\bcaa\d*\b", n) or ("cour" in n and "appel" in n):
        return "caa"
    if re.search(r"\bta\d*\b", n) or ("tribunal" in n and "administratif" in n):
        return "ta"
    if ("conseil" in n and "etat" in n) or n.strip() == "ce":
        return "ce"
    return ""


def _filter_by_juridiction(results: list[dict], juridiction: str | None) -> list[dict]:
    """Ne garde que les décisions du même ordre que celui demandé.

    Une juridiction non typée (« Lyon » nu) ne filtre rien : l'utilisateur
    n'a pas exprimé d'ordre, on ne lui en impose pas."""
    if not results or not juridiction:
        return results
    want = _juri_type(juridiction)
    if not want:
        return results
    return [r for r in results if _juri_type(r.get("juridiction", "")) == want]


_CHAMPS_HOMONYME = ("id", "juridiction", "formation", "date", "numero", "titre")


def _signaler_homonymes(principal: dict, tous: list[dict]) -> dict:
    """Annonce les autres décisions portant le MÊME numéro.

    Le Conseil d'État a réutilisé ses numéros de pourvoi d'une époque à
    l'autre. Mesuré le 29 août 2026 sur le bulk JADE : **7 938 numéros du
    CE sont portés par plusieurs décisions**, soit 16 143 décisions
    concernées. Le n° 74052 désigne ainsi à la fois un arrêt du 29 octobre
    1969 (quotas d'écrasement d'un moulin) ET l'arrêt d'Assemblée du
    3 février 1989 « Compagnie Alitalia ».

    Le lookup rendait la première ligne venue — l'ordre des rowid, donc la
    plus ancienne — et jetait les autres sans un mot. Conséquence
    constatée : un agent a conclu qu'Alitalia n'existait pas dans la base
    et l'a classée « invérifiable », alors qu'elle y est. Un silence sur
    l'homonymie se lit comme une absence.

    On ne choisit donc pas à la place de l'appelant : on sert la même
    décision qu'avant (aucun changement de comportement) et on lui montre
    les autres, pour qu'il tranche sur la date et la formation.
    """
    autres = [d for d in tous if d.get("id") != principal.get("id")]
    if not autres:
        return principal
    out = dict(principal)
    out["homonymes"] = [
        {c: d.get(c) for c in _CHAMPS_HOMONYME if d.get(c)} for d in autres
    ]
    out["avertissement"] = (
        f"{len(autres) + 1} décisions portent le numéro "
        f"{principal.get('numero') or '?'} : les numéros anciens ont été "
        f"réutilisés. Celle servie ici est du {principal.get('date') or '?'}. "
        "Vérifier la date et la formation avant de citer — les autres sont "
        "dans le champ `homonymes`, aucune n'est absente de la base."
    )
    return out


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

    # Détection numéro de dossier admin → lookup SQL exact (bypass FTS5)
    num = match_admin_docket(query)
    if num:
        results = await wh.lookup_by_numero("jade", num, juridiction=juridiction)
        # Le rapprochement du warehouse se fait par ville : sans ce contrôle
        # d'ordre, une recherche « TA de Lyon » sert la CAA de Lyon.
        results = _filter_by_juridiction(results, juridiction)
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
    num_clean = normalize_numero(numero)

    # 1. Lookup SQL exact dans JADE bulk
    results = await wh.lookup_by_numero("jade", num_clean, juridiction=juridiction)
    # Les homonymes se signalent DANS l'ordre de juridiction demandé : on ne
    # ressuscite pas la confusion TA/CAA que `_filter_by_juridiction` écarte.
    kept = _filter_by_juridiction(results, juridiction)
    if kept:
        return _signaler_homonymes(kept[0], kept)

    # 2. Fallback sur API live (opendata.justice-administrative.fr)
    try:
        import httpx
        from . import juriadmin
        # Choisir la cible : accepter à la fois le code court (TA69, CAA75, CE)
        # ET le nom long ("Tribunal Administratif de Lyon", "Conseil d'Etat"...)
        # via mapping inversé. Sans match, fanout par défaut sur CE+CAA+TA.
        juri_code = "CE-CAA"
        if juridiction:
            juri_in = juridiction.strip()
            juri_up = juri_in.upper()
            if juri_up in juriadmin.VALID_JURI:
                juri_code = juri_up
            elif "ETAT" in juri_up or juri_up == "CE":
                juri_code = "CE"
            else:
                # Mapping nom long → code court (LIKE substring)
                juri_norm = juri_in.lower().replace("é", "e").replace("è", "e")
                for code, name in juriadmin.VALID_JURI.items():
                    name_norm = name.lower().replace("é", "e").replace("è", "e")
                    if juri_norm == name_norm or juri_norm in name_norm:
                        juri_code = code
                        break
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            data = await juriadmin.search(client, query=num_clean, juridiction=juri_code, limit=10)
        hits = data.get("decisions", [])
        # Match EXACT sur le numéro, et rien d'autre.
        for h in hits:
            if str(h.get("numero_dossier", "")).replace(" ", "") == num_clean:
                return h
        # ⚠️ Auparavant : `return hits[0]` — on servait le premier résultat de
        # la recherche même si son numéro ne correspondait pas. Un lookup par
        # numéro qui renvoie une décision au numéro DIFFÉRENT est un piège :
        # l'appelant croit tenir la décision demandée (bug de famille
        # identifié le 23 août 2026 sur get_cc_decision). On avoue.
        return None
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
    num_clean = normalize_numero(numero)

    # 1. Lookup SQL exact dans JADE
    results = await wh.lookup_by_numero("jade", num_clean, juridiction="Conseil d'Etat")
    if results:
        return _signaler_homonymes(results[0], results)

    # 2. Fallback ArianeWeb (Sinequa) — pour les décisions hors bulk JADE
    try:
        import httpx
        from . import ariane
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            data = await ariane.search(client, num_clean, limit=5)
        hits = data.get("decisions", [])
        # Match EXACT sur le numéro, et rien d'autre.
        for h in hits:
            if str(h.get("numero", "")).replace(" ", "") == num_clean:
                return h
        # ⚠️ Auparavant : `return hits[0]` — Sinequa filtre bien sur le CE,
        # mais rien ne garantit que le premier résultat porte LE numéro
        # demandé. Mieux vaut un not_found qu'un arrêt voisin servi comme
        # étant le bon.
        return None
    except Exception:
        return None
