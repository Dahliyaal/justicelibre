"""Traduction « ce que l'appelant demande » → « ce qui est écrit en base ».

Pourquoi ce module existe (8 septembre 2026) : le champ `juridiction` des
bulks DILA écrit la même cour de plusieurs façons — 113 écritures pour 45
juridictions dans JADE (« CAA de LYON », « COUR ADMINISTRATIVE D'APPEL DE
LYON », « Cour administrative d'appel de Lyon »…), et la Cour de cassation
est « cc » sur 556 422 lignes contre « Cour de cassation » sur 536 473 dans
le fonds judiciaire. Un filtre écrit contre UNE de ces formes rate les
autres en silence, et un code de juridiction (« TA69 ») ne trouve rien.

Le choix : NE PAS réécrire la base (28 Go sur un disque à 11 Go libres,
et une réécriture est irréversible sans sauvegarde). On traduit à la
lecture : toute forme reconnue → la liste EXACTE des écritures stockées →
`juridiction IN (...)`, qui utilise l'index. La correspondance vit dans
`data/juridictions_map.json`, versionnée ; marche arrière = git revert.

Une valeur NON reconnue renvoie None : l'appelant garde son comportement
d'avant. Ce module ne peut donc que réparer, jamais amputer.

Sans dépendance : importable par le serveur MCP (prod) ET par le warehouse
(al-uzza), qui n'a pas le paquet `sources`.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent
MAP_PATH = Path(os.environ.get("JL_JURIDICTIONS_MAP", _HERE / "data" / "juridictions_map.json"))

# Préfixes qui désignent le TYPE de juridiction ; ce qui reste après est la
# ville-siège (« lyon ») — c'est elle qui identifie la cour dans une demande
# courte comme « TA Lyon » ou « CAA de Lyon ».
_TYPES = {
    "ta": ("ta", "t.a.", "tribunal administratif", "trib. adm.", "trib adm"),
    "caa": ("caa", "c.a.a.", "cour administrative d'appel", "cour administrative d appel"),
}
_TYPE_RE = re.compile(r"^(?:tribunal administratif|cour administrative d'appel|caa|ta)\s*")
_ARTICLE_RE = re.compile(r"^(?:de\s+la|de\s+l'|de|d'|du|des)\s*")


def normaliser(s: str) -> str:
    """Minuscules, sans accents, apostrophes droites, espaces réduits."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", s).strip(" .")


def _reste_et_ville(n: str) -> tuple[str, str]:
    """« tribunal administratif de la reunion » → (« de la reunion », « reunion »)."""
    reste = _TYPE_RE.sub("", n).strip()
    return reste, _ARTICLE_RE.sub("", reste).strip()


@lru_cache(maxsize=1)
def charger() -> dict:
    with open(MAP_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _index_admin() -> dict[str, str]:
    """Toute forme normalisée → code. Construit une fois."""
    idx: dict[str, str] = {}
    carte = charger()
    # Les écritures anormales (« CAA de Montpellier » = une décision de
    # Marseille mal étiquetée) servent à RETROUVER leurs lignes, jamais à
    # fabriquer un raccourci : sinon demander « CAA de Montpellier »
    # servirait Marseille sans le dire.
    anormales = {normaliser(e) for e in carte.get("ecritures_anormales", {})}
    for code, entry in carte["admin"].items():
        kind = "caa" if code.startswith("CAA") else "ta" if code.startswith("TA") else None
        formes = {code, entry["nom"], *entry["ecritures"]}
        for f in list(formes):
            n = normaliser(f)
            idx[n] = code
            if kind and n not in anormales:
                reste, v = _reste_et_ville(n)
                if v and reste != n:
                    for t in _TYPES[kind]:
                        idx[f"{t} {reste}"] = code      # « ta de la reunion »
                        idx[f"{t} {v}"] = code          # « ta reunion »
                        idx[f"{t} de {v}"] = code
                        idx[f"{t} d'{v}"] = code
                        idx[f"{t} du {v}"] = code
                        idx[f"{t} de la {v}"] = code
    # Formes courtes du Conseil d'État et du Tribunal des conflits.
    idx.update({"ce": "CE", "conseil d'etat": "CE", "c.e": "CE",
                "tc": "TC", "tdc": "TC", "conflits": "TC", "tribunal des conflits": "TC"})
    return idx


def resoudre_admin(valeur: str | None) -> dict | None:
    """Code, nom et écritures stockées pour une demande — ou None si inconnue.

    Reconnaît : le code (« TA69 », « caa59 »), le nom canonique, n'importe
    quelle écriture présente en base, et les formes courtes « TA Lyon »,
    « TA de Lyon », « CAA Douai ». Une ville nue (« Lyon ») reste None : elle
    ne dit pas si c'est le tribunal ou la cour d'appel de cette ville.
    """
    if not valeur or not valeur.strip():
        return None
    code = _index_admin().get(normaliser(valeur))
    if not code:
        return None
    entry = charger()["admin"][code]
    return {"code": code, "nom": entry["nom"], "ecritures": list(entry["ecritures"])}


def where_admin(valeur: str | None, col: str = "juridiction") -> tuple[str, list[str]] | None:
    """Clause SQL `col IN (?, ?, …)` + paramètres, ou None si valeur inconnue."""
    r = resoudre_admin(valeur)
    if not r:
        return None
    ph = ", ".join("?" * len(r["ecritures"]))
    return f"{col} IN ({ph})", r["ecritures"]


def familles_judiciaires() -> dict[str, str]:
    """{clé de filtre: nom lisible} pour le fonds judiciaire."""
    return {k: v["nom"] for k, v in charger()["judiciaire"].items()}


def where_judiciaire(famille: str, col: str = "juridiction") -> tuple[str, list[str]] | None:
    """Clause SQL pour une famille judiciaire (cassation, appel, tj, tcom, constit).

    Les familles à préfixe (« Cour d'appel de … ») sont exprimées en
    intervalle `col >= 'Cour d''appel ' AND col < 'Cour d''appel \\uffff'`
    plutôt qu'en LIKE : l'intervalle utilise l'index, et une juridiction
    NOUVELLE (un tribunal créé demain) y entre d'elle-même — là où une liste
    fermée l'aurait exclue en silence.
    """
    entry = charger()["judiciaire"].get((famille or "").strip().lower())
    if not entry:
        return None
    clauses: list[str] = []
    params: list[str] = []
    if entry.get("exact"):
        clauses.append(f"{col} IN ({', '.join('?' * len(entry['exact']))})")
        params.extend(entry["exact"])
    for p in entry.get("prefixes", []):
        clauses.append(f"({col} >= ? AND {col} < ?)")
        params.extend([p, p + "\uffff"])
    return "(" + " OR ".join(clauses) + ")", params


def fts_judiciaire(famille: str, col: str = "juridiction") -> str | None:
    """Filtre de famille exprimé DANS la requête FTS5 : `juridiction:("cc" OR "Cour de cassation")`.

    Pourquoi ce n'est pas un WHERE (mesuré le 8 septembre 2026 sur la prod,
    28 Go) : avec `d.juridiction IN (...)` et son index, SQLite attaquait par
    l'index de la colonne (1,09 M de lignes pour la Cour de cassation) puis
    sondait l'index plein texte ligne à ligne — plus de dix minutes. La
    colonne `juridiction` est déjà indexée dans `decisions_fts` : filtrer
    là-dedans coûte le prix d'un mot de plus dans la requête. Une phrase
    FTS5 (« Tribunal judiciaire ») joue le rôle du préfixe et couvre une
    juridiction nouvelle comme l'intervalle de `where_judiciaire`.
    """
    entry = charger()["judiciaire"].get((famille or "").strip().lower())
    if not entry:
        return None
    termes = [*entry.get("exact", []), *(p.strip() for p in entry.get("prefixes", []))]
    phrases = " OR ".join('"' + t.replace('"', '') + '"' for t in termes)
    return f"{col}:({phrases})"


def libelle_affiche(valeur: str | None) -> str | None:
    """Ce qu'on montre à l'appelant pour une écriture brute (« cc » → « Cour de cassation »)."""
    if valeur is None:
        return None
    return charger()["libelles_affiches"].get(valeur, valeur)


def ecritures_admin_connues() -> set[str]:
    return {e for entry in charger()["admin"].values() for e in entry["ecritures"]}


def ecritures_judiciaires_reconnues(valeur: str) -> bool:
    """Vrai si une écriture du fonds judiciaire tombe dans une famille."""
    for entry in charger()["judiciaire"].values():
        if valeur in entry.get("exact", []):
            return True
        if any(valeur.startswith(p) for p in entry.get("prefixes", [])):
            return True
    return False
