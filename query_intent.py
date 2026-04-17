"""Analyse la query utilisateur et détermine son intent : quel type de
lookup tenter sur quelles sources.

Un intent, c'est un objet avec :
  - `kind` : nom canonique (ce qu'on cherche)
  - `value` : valeur canonique extraite (ce avec quoi on le cherche)
  - `fts_query` : version normalisée pour FTS5 / moteurs plein-texte
  - `extra` : champs additionnels (ID candidates, etc.)

Les kinds possibles :
  - "ariane_id"      : n° interne ArianeWeb (6 chiffres)
  - "pourvoi"        : n° de pourvoi Cass format YY-NNNNN
  - "rg"             : n° RG format YY/NNNNN (Cour d'appel judiciaire)
  - "celex"          : identifiant CELEX européen (6xxxxCJyyyy)
  - "ecli"           : ECLI:EU:C:YYYY:N ou ECLI:FR:…
  - "dossier_admin"  : n° de dossier admin TA/CAA (7 chiffres commençant par 2)
  - "dce_id"         : DCE_XXX_YYYYMMDD (admin ES)
  - "itemid_hudoc"   : 001-XXXXXX (CEDH)
  - "juritext"       : JURITEXT000NNNN (DILA judiciaire)
  - "phrase"         : requête entre guillemets
  - "fts"            : requête plein-texte classique
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryIntent:
    kind: str
    value: str = ""
    fts_query: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ─── PATTERNS CANONIQUES ───────────────────────────────────────────

# n° interne ArianeWeb : 5-7 chiffres purs (typiquement 6)
_RE_ARIANE_ID = re.compile(r"^\d{5,7}$")
# n° de pourvoi Cass : 2 chiffres — 4 à 6 chiffres avec . optionnel (14-80854, 14-80.854)
_RE_POURVOI = re.compile(r"^\d{2}-\d{2,3}\.?\d{2,4}$")
# n° RG (Cour d'appel) : YY/NNNNN
_RE_RG = re.compile(r"^\d{2}/\d{5,6}$")
# CELEX européen : 6NNNNTTNNNN
_RE_CELEX = re.compile(r"^6\d{4}[A-Z]{2}\d{4}$")
# ECLI
_RE_ECLI = re.compile(r"^ECLI:[A-Z]{2}:[A-Z]+:\d{4}:\S+$", re.IGNORECASE)
# Dossier admin (TA/CAA) : 7 chiffres commençant par 2 (2XXXXXX)
_RE_DOSSIER_ADMIN = re.compile(r"^2\d{6}$")
# IDs déjà typés (préfixes)
_RE_DCE = re.compile(r"^D(CE|TA|CAA)_[A-Z0-9_]+$", re.IGNORECASE)
_RE_HUDOC = re.compile(r"^00[0-9]-\d{4,6}$")
_RE_JURITEXT = re.compile(r"^(JURI|CONST|ARRETS)\w*$", re.IGNORECASE)


def _strip_wrapping_quotes(q: str) -> tuple[str, bool]:
    q = q.strip()
    if len(q) >= 2 and q[0] == '"' and q[-1] == '"':
        return q[1:-1].strip(), True
    return q, False


def normalize_fts_query(q: str) -> str:
    """Convertit les opérateurs multi-syntaxe vers FTS5/ES canonique.

    Accepte : AND/ET/& · OR/OU/| · NOT/SAUF/-mot · "phrase" · mot*
    Les tokens composés (14-80854, ECLI:…, C-72/24) sont wrappés en phrase.
    """
    if not q:
        return ""
    q = q.strip()
    # Protéger les phrases exactes "..."
    phrases: list[str] = []
    def _protect(m):
        phrases.append(m.group(0))
        return f"\x00{len(phrases)-1}\x00"
    q = re.sub(r'"[^"]*"', _protect, q)
    # Symboles d'opérateur
    q = re.sub(r"\s*&\s*", " AND ", q)
    q = re.sub(r"\s*\|\s*", " OR ", q)
    # Exclusion (-mot en début ou après espace)
    q = re.sub(r"(^|\s)-(\w+\*?)", r"\1NOT \2", q)
    # Tokens composés : wrapper en phrase
    def _quote_compound(m):
        return '"' + re.sub(r"[-/:]+", " ", m.group(0)) + '"'
    q = re.sub(r"\b\w+(?:[-/:]\w+)+\b", _quote_compound, q)
    # Keywords français
    q = re.sub(r"\bET\b", "AND", q, flags=re.IGNORECASE)
    q = re.sub(r"\bOU\b", "OR", q, flags=re.IGNORECASE)
    q = re.sub(r"\bSAUF\b", "NOT", q, flags=re.IGNORECASE)
    # Espaces normalisés
    q = re.sub(r"\s+", " ", q).strip()
    # Rétablir phrases
    for i, p in enumerate(phrases):
        q = q.replace(f"\x00{i}\x00", p)
    return q


def detect_intent(q: str) -> QueryIntent:
    """Inspecte la query utilisateur et retourne le meilleur intent.

    Priorité : patterns stricts (IDs) > phrase exacte > FTS.
    """
    raw = (q or "").strip()
    if not raw:
        return QueryIntent(kind="empty")

    # Phrase exacte (guillemets encadrants)
    stripped, was_quoted = _strip_wrapping_quotes(raw)

    # Identifiants techniques (priorité haute, match exact)
    if _RE_DCE.match(raw):
        return QueryIntent(kind="dce_id", value=raw, fts_query=normalize_fts_query(raw))
    if _RE_HUDOC.match(raw):
        return QueryIntent(kind="itemid_hudoc", value=raw, fts_query=normalize_fts_query(raw))
    if _RE_JURITEXT.match(raw):
        return QueryIntent(kind="juritext", value=raw.upper(), fts_query=normalize_fts_query(raw))
    if _RE_ECLI.match(raw):
        return QueryIntent(kind="ecli", value=raw.upper(), fts_query=normalize_fts_query(raw))
    if _RE_CELEX.match(raw):
        return QueryIntent(kind="celex", value=raw.upper(), fts_query=normalize_fts_query(raw))
    if _RE_POURVOI.match(raw):
        # Normaliser : enlever le point éventuel pour matcher "14-80854" ou "14-80.854"
        canonical = raw.replace(".", "")
        return QueryIntent(
            kind="pourvoi", value=canonical,
            fts_query=normalize_fts_query(canonical),
            extra={"original": raw},
        )
    if _RE_RG.match(raw):
        return QueryIntent(kind="rg", value=raw, fts_query=normalize_fts_query(raw))
    if _RE_DOSSIER_ADMIN.match(raw):
        # 7 chiffres commençant par 2 → typiquement un n° de dossier admin
        # (TA/CAA). Peut aussi matcher un n° interne ArianeWeb si 6 chiffres.
        return QueryIntent(kind="dossier_admin", value=raw, fts_query=normalize_fts_query(raw))
    if _RE_ARIANE_ID.match(raw):
        # Numéro pur 5-7 chiffres : candidate pour ArianeWeb ID direct
        # ET aussi pour un n° de dossier CE (numero_dossier est dans admin ES)
        return QueryIntent(kind="ariane_id", value=raw, fts_query=normalize_fts_query(raw))

    # Phrase exacte encadrée par "..."
    if was_quoted and stripped:
        return QueryIntent(kind="phrase", value=stripped, fts_query=f'"{stripped}"')

    # Fallback : recherche FTS classique
    return QueryIntent(kind="fts", value=raw, fts_query=normalize_fts_query(raw))


# ─── CAPACITÉS PAR SOURCE ─────────────────────────────────────────
# Pour chaque source, quels intents peut-elle traiter utilement ?

SOURCE_CAPABILITIES = {
    "ariane": {
        "ariane_id",       # lookup direct par ID via plugin
        "dossier_admin",   # rare mais possible via plugin
        "phrase", "fts",
    },
    "admin": {
        "dce_id",          # -> get_decision direct
        "dossier_admin",   # dans text + numero_dossier
        "ariane_id",       # le vrai n° dossier CE peut être 6-7 chiffres
        "pourvoi",         # parfois cité dans le texte
        "ecli",
        "phrase", "fts",
    },
    "dila": {
        "juritext",        # lookup direct par ID
        "pourvoi",         # matche numero
        "rg",              # matche numero pour CA
        "ecli",
        "phrase", "fts",
    },
    "cedh": {
        "itemid_hudoc",    # lookup direct
        "ecli",
        "phrase", "fts",
    },
    "cjue": {
        "celex",           # lookup direct
        "ecli",
        "phrase", "fts",
    },
}


def sources_for_intent(intent: QueryIntent, allowed: list[str]) -> list[str]:
    """Quelles sources sont pertinentes pour cet intent ?"""
    caps = SOURCE_CAPABILITIES
    matching = [s for s in allowed if intent.kind in caps.get(s, set())]
    if matching:
        return matching
    # Fallback : FTS sur toutes les sources autorisées
    return [s for s in allowed if "fts" in caps.get(s, set())]
