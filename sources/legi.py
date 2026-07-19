"""Wrapper métier pour les articles de loi (codes consolidés).

Expose des fonctions async qui délèguent au warehouse HTTP (al-uzza) pour
récupérer un article à une date, toutes ses versions, ou un batch d'articles.

Les 22 codes supportés sont ceux reconnus par le regex `highlightLawRefs`
côté web (search.html) et mappés vers leurs LEGITEXT côté warehouse.
"""
from __future__ import annotations

from typing import Any

from . import warehouse as wh

# Codes supportés (miroir de CODE_TO_LEGITEXT côté warehouse)
# Utile pour validation rapide côté client (évite un round-trip si code bidon)
SUPPORTED_CODES: dict[str, str] = {
    # ─── 22 codes consolidés ─────────────────────────────────
    "CC":      "Code civil",
    "CP":      "Code pénal",
    "CPC":     "Code de procédure civile",
    "CPP":     "Code de procédure pénale",
    "CT":      "Code du travail",
    "CSP":     "Code de la santé publique",
    "CJA":     "Code de justice administrative",
    "CGCT":    "Code général des collectivités territoriales",
    "CRPA":    "Code des relations entre le public et l'administration",
    "CPI":     "Code de la propriété intellectuelle",
    "CASF":    "Code de l'action sociale et des familles",
    "CMF":     "Code monétaire et financier",
    "C.com":   "Code de commerce",
    "C.cons":  "Code de la consommation",
    "C.éduc":  "Code de l'éducation",
    "CU":      "Code de l'urbanisme",
    "C.env":   "Code de l'environnement",
    "CR":      "Code rural et de la pêche maritime",
    "CGI":     "Code général des impôts",
    "CESEDA":  "Code de l'entrée et du séjour des étrangers et du droit d'asile",
    "CSS":     "Code de la sécurité sociale",
    "CCH":     "Code de la construction et de l'habitation",
    "CPCEx":   "Code des procédures civiles d'exécution",
    "CGIANII":   "Code général des impôts, annexe II",
    "CGIANI":    "Code général des impôts, annexe I",
    "CGIANIII":  "Code général des impôts, annexe III",
    "CGIANIV":   "Code général des impôts, annexe IV",
    "CCom2":     "Code des communes (obsolète)",
    "CRurA":     "Code rural ancien (obsolète)",
    "CCNC":      "Code des communes de la Nouvelle-Calédonie",
    "CMinA":     "Code minier (ancien)",
    "CFAS":      "Code de la famille et de l aide sociale (obsolète)",
    "CDouMay":   "Code des douanes de Mayotte",
    "CDPFNav":   "Code du domaine public fluvial",
    "CTravM":    "Code du travail maritime",
    "CDPMM":     "Code disciplinaire pénal marine marchande",
    "CPRM":      "Code des pensions retraite marins",
    "CDEMay":    "Code du domaine Etat Mayotte",
    "CIMM":      "Code des instruments monétaires",
    "CDA":       "Code de déontologie des architectes",
    # ─── Constitution ────────────────────────────────────────
    "CONST":   "Constitution du 4 octobre 1958",
    # ─── Lois non codifiées fréquemment citées ──────────────
    "LIL":     "Loi Informatique et Libertés (loi n° 78-17)",
    "LO58":    "Ordonnance organique Conseil constitutionnel (ord. n° 58-1067)",
    "L2005-102": "Loi handicap (loi n° 2005-102)",
}


# Mapping code court → identifiant Légifrance (LEGITEXT/JORFTEXT).
# Doit rester synchronisé avec warehouse_server.CODE_TO_LEGITEXT.
# Utilisé par render_sitemap_legi pour faire le reverse mapping
# LEGITEXT → code court lors de la génération des URLs /loi/{code}/{num}.
SUPPORTED_CODES_LEGITEXT: dict[str, str] = {
    "CC":      "LEGITEXT000006070721",
    "CP":      "LEGITEXT000006070719",
    "CPC":     "LEGITEXT000006070716",
    "CPP":     "LEGITEXT000006071154",
    "CT":      "LEGITEXT000006072050",
    "CSP":     "LEGITEXT000006072665",
    "CJA":     "LEGITEXT000006070933",
    "CGCT":    "LEGITEXT000006070633",
    "CRPA":    "LEGITEXT000031366350",
    "CPI":     "LEGITEXT000006069414",
    "CASF":    "LEGITEXT000006074069",
    "CMF":     "LEGITEXT000006072026",
    "C.com":   "LEGITEXT000005634379",
    "C.cons":  "LEGITEXT000006069565",
    "C.éduc":  "LEGITEXT000006071191",
    "CU":      "LEGITEXT000006074075",
    "C.env":   "LEGITEXT000006074220",
    "CR":      "LEGITEXT000006071367",
    "CGI":     "LEGITEXT000006069577",  # principal
    "CESEDA":  "LEGITEXT000006070158",
    "CSS":     "LEGITEXT000006073189",
    "CCH":     "LEGITEXT000006074096",
    "CTransp":   "LEGITEXT000023086525",  # Code des transports
    "CAss":      "LEGITEXT000006073984",  # Code des assurances
    "CDef":      "LEGITEXT000006071307",  # Code de la défense
    "CSI":       "LEGITEXT000025503132",  # Code de la sécurité intérieure
    "CEner":     "LEGITEXT000023983208",  # Code de l'énergie
    "CCiné":     "LEGITEXT000020908868",  # Code du cinéma et de l'image animée
    "CSport":    "LEGITEXT000006071318",  # Code du sport
    "CJF":       "LEGITEXT000006070249",  # Code des juridictions financières
    "COJ":       "LEGITEXT000006071164",  # Code de l'organisation judiciaire
    "CPCE":      "LEGITEXT000006070987",  # Code des postes et des communications électroniques
    "CElec":     "LEGITEXT000006070239",  # Code électoral
    "CGFP":      "LEGITEXT000044416551",  # Code général de la fonction publique
    "LPF":       "LEGITEXT000006069583",  # Livre des procédures fiscales
    "CRoute":    "LEGITEXT000006074228",  # Code de la route
    "CPatr":     "LEGITEXT000006074236",  # Code du patrimoine
    "CMut":      "LEGITEXT000006074067",  # Code de la mutualité
    "CPénit":    "LEGITEXT000045476241",  # Code pénitentiaire
    "CCP":       "LEGITEXT000037701019",  # Code de la commande publique
    "CAvCiv":    "LEGITEXT000006074234",  # Code de l'aviation civile
    "CIBS":      "LEGITEXT000044595989",  # Code des impositions sur les biens et services
    "CDouanes":  "LEGITEXT000006071570",  # Code des douanes
    "CForêt":    "LEGITEXT000025244092",  # Code forestier (nouveau)
    "CTou":      "LEGITEXT000006074073",  # Code du tourisme
    "CG3P":      "LEGITEXT000006070299",  # Code général de la propriété des personnes publiques
    "CSN":       "LEGITEXT000006071335",  # Code du service national
    "CRech":     "LEGITEXT000006071190",  # Code de la recherche
    "CPortM":    "LEGITEXT000006074233",  # Code des ports maritimes
    "CDE":       "LEGITEXT000006070208",  # Code du domaine de l'Etat
    "CMin":      "LEGITEXT000023501962",  # Code minier (nouveau)
    "CJM":       "LEGITEXT000006071360",  # Code de justice militaire
    "CExpr":     "LEGITEXT000006074224",  # Code de l'expropriation pour cause d'utilité publique
    "CVoir":     "LEGITEXT000006070667",  # Code de la voirie routière
    "CJPM":      "LEGITEXT000039086952",  # Code de la justice pénale des mineurs
    "CArt":      "LEGITEXT000006075116",  # Code de l'artisanat
    "CPCMR":     "LEGITEXT000006070302",  # Code des pensions civiles et militaires de retraite,
    "CPCEx":   "LEGITEXT000025024948",
    "CGIANII":   "LEGITEXT000006069569",  # CGI annexe II (ancien CGI dans le dict, corrigé)
    "CGIANI":    "LEGITEXT000006069568",  # CGI annexe I
    "CGIANIII":  "LEGITEXT000006069574",  # CGI annexe III
    "CGIANIV":   "LEGITEXT000006069576",  # CGI annexe IV
    "CCom2":     "LEGITEXT000006070162",  # Code des communes (obsolète, remplacé par CGCT)
    "CRurA":     "LEGITEXT000006071366",  # Code rural ancien (obsolète, remplacé par CR)
    "CCNC":      "LEGITEXT000006070300",  # Code des communes de la Nouvelle-Calédonie
    "CMinA":     "LEGITEXT000006071785",  # Code minier (ancien, remplacé par CMin)
    "CFAS":      "LEGITEXT000006072637",  # Code de la famille et de l'aide sociale (remplacé par CASF)
    "CDouMay":   "LEGITEXT000006071645",  # Code des douanes de Mayotte
    "CDPFNav":   "LEGITEXT000006074237",  # Code du domaine public fluvial et navigation intérieure
    "CTravM":    "LEGITEXT000006072051",  # Code du travail maritime
    "CDPMM":     "LEGITEXT000006071188",  # Code disciplinaire et pénal de la marine marchande
    "CPRM":      "LEGITEXT000006074066",  # Code des pensions retraite marins (commerce/pêche/plaisance)
    "CDEMay":    "LEGITEXT000006074235",  # Code du domaine Etat Mayotte
    "CIMM":      "LEGITEXT000006070666",  # Code des instruments monétaires et des médailles
    "CDA":       "LEGITEXT000006074232",  # Code de déontologie des architectes
    "CONST":     "JORFTEXT000000571356",
    "LIL":       "JORFTEXT000000886460",
    "LO58":      "JORFTEXT000000705065",
    "L2005-102": "JORFTEXT000000809647",
}


def is_supported(code: str) -> bool:
    return code in SUPPORTED_CODES


async def get_article(code: str, num: str, date: str | None = None) -> dict[str, Any]:
    """Récupère un article à une date donnée (ou version actuelle si None).

    `code` accepte :
    - un code court parmi SUPPORTED_CODES (CC, CP, LIL, LO58…)
    - un identifiant LEGITEXT/JORFTEXT direct pour les textes non listés
      (ex: 'JORFTEXT000000878035' pour la loi 68-1250).
      → Utiliser `resolve_law_number()` pour trouver l'id à partir d'un
        numéro de loi.

    Retourne un dict structuré, ou {"error": "..."} si introuvable / code inconnu.
    """
    # Accepter LEGITEXT / JORFTEXT direct comme code
    if code.startswith("LEGITEXT") or code.startswith("JORFTEXT"):
        data = await wh.get_law(code, num, date)
    elif is_supported(code):
        data = await wh.get_law(code, num, date)
    else:
        return {
            "error": f"Code inconnu: {code!r}. Codes supportés: {list(SUPPORTED_CODES.keys())}. "
                     f"Pour les autres lois/décrets, passer un LEGITEXT/JORFTEXT direct "
                     f"(utiliser resolve_law_number() pour le trouver depuis un numéro).",
        }
    if data is None:
        return {
            "error": f"Article {code} {num} introuvable",
            "code": code, "num": num, "date": date,
        }
    return data


async def resolve_number(numero: str) -> dict[str, Any]:
    """Résout un numéro de loi/ordonnance/décret ('68-1250', '79-587') vers
    son LEGITEXT/JORFTEXT + métadonnées."""
    data = await wh.resolve_law_number(numero)
    if data is None:
        return {"error": f"Pas de loi/décret trouvé avec le numéro {numero!r}"}
    return data


async def get_versions(code: str, num: str) -> dict[str, Any]:
    """Toutes les versions historiques d'un article, triées par date_debut asc."""
    if not is_supported(code):
        return {
            "error": f"Code inconnu: {code!r}",
            "supported_codes": list(SUPPORTED_CODES.keys()),
        }
    versions = await wh.get_law_versions(code, num)
    return {
        "code": code,
        "code_long": SUPPORTED_CODES[code],
        "num": num,
        "count": len(versions),
        "versions": versions,
    }


async def get_batch(refs: list[dict], date: str | None = None) -> list[dict]:
    """Batch : plusieurs articles en une seule round-trip warehouse."""
    # Filtrer les codes inconnus localement (optimisation)
    valid_refs = [r for r in refs if is_supported(r.get("code", ""))]
    if not valid_refs:
        return []
    return await wh.get_laws_batch(valid_refs, date)
