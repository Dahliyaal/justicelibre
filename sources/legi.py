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
    # ─── Constitution ────────────────────────────────────────
    "CONST":   "Constitution du 4 octobre 1958",
    # ─── Lois non codifiées fréquemment citées ──────────────
    "LIL":     "Loi Informatique et Libertés (loi n° 78-17)",
    "LO58":    "Ordonnance organique Conseil constitutionnel (ord. n° 58-1067)",
    "L2005-102": "Loi handicap (loi n° 2005-102)",
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
