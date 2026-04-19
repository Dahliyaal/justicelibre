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


# ─── ALIAS DE JURIDICTIONS (réformes / variations historiques) ────
# Quand l'utilisateur tape un alias court (TJ, TGI, etc.), on étend la
# requête FTS à toutes les variantes textuelles équivalentes pour ne pas
# rater les décisions qui utilisent l'ancienne nomenclature.
#
# Réforme du 1er janvier 2020 (loi 23 mars 2019) :
#   TGI + TI → TJ (tribunal judiciaire)
#   TASS → pôle social du TJ
JURIDICTION_ALIASES = {
    "TJ":   ["Tribunal judiciaire", "Tribunal de grande instance",
             "Tribunal d'instance", "TGI", "TI"],
    "TGI":  ["Tribunal de grande instance", "Tribunal judiciaire", "TJ"],
    "TI":   ["Tribunal d'instance", "Tribunal judiciaire", "TJ"],
    "TASS": ["Tribunal des affaires de sécurité sociale", "pôle social",
             "Tribunal judiciaire"],
    "CPH":  ["Conseil de prud'hommes", "conseil prud'hommes"],
    "CAA":  ["Cour administrative d'appel"],
    "CEDH": ["Cour européenne des droits de l'homme", "Cour EDH"],
    "CJUE": ["Cour de justice de l'Union européenne",
             "Cour de justice de l'Union", "CJCE"],
    "CJCE": ["Cour de justice des Communautés européennes",
             "Cour de justice de l'Union européenne", "CJUE"],
}

# On limite l'expansion aux alias non-ambigus (ignore CC/CE/CA/TC qui
# pourraient matcher des mots français courants ou d'autres entités)
SAFE_ALIASES = ["TJ", "TGI", "TI", "TASS", "CPH", "CAA", "CEDH", "CJUE", "CJCE"]
_RE_ALIAS = re.compile(r"\b(" + "|".join(SAFE_ALIASES) + r")\b")


def expand_juridiction_aliases(q: str) -> str:
    """Si la query contient un alias court de juridiction (ex: "TJ Lyon"),
    remplace ce mot par une expression OR couvrant toutes les variantes
    historiques équivalentes ("Tribunal judiciaire" OR "Tribunal de grande
    instance" OR ...). Permet de retrouver les décisions PRE-réforme 2020.
    """
    if not q:
        return q
    def _replace(m):
        upper = m.group(0).upper()
        aliases = JURIDICTION_ALIASES.get(upper)
        if not aliases:
            return m.group(0)
        parts = []
        seen = set()
        for v in [m.group(0)] + aliases:
            v_clean = v.strip()
            if v_clean.lower() in seen:
                continue
            seen.add(v_clean.lower())
            if " " in v_clean or "'" in v_clean:
                parts.append(f'"{v_clean}"')
            else:
                parts.append(v_clean)
        return "(" + " OR ".join(parts) + ")"
    return _RE_ALIAS.sub(_replace, q)


# ─── THÉSAURUS JURIDIQUE (synonymes métier) ────────────────────────

_THESAURUS: dict[str, list[str]] | None = None


def _load_thesaurus() -> dict[str, list[str]]:
    global _THESAURUS
    if _THESAURUS is None:
        import json
        from pathlib import Path
        path = Path(__file__).with_name("thesaurus_fr.json")
        try:
            data = json.loads(path.read_text())
            # Virer les clés techniques (_comment)
            _THESAURUS = {k.lower(): v for k, v in data.items() if not k.startswith("_")}
        except (FileNotFoundError, json.JSONDecodeError):
            _THESAURUS = {}
    return _THESAURUS


def expand_synonyms(q: str) -> str:
    """Étend une query FTS5 en ajoutant les synonymes issus du thésaurus.

    Pour chaque expression du thésaurus trouvée dans la query hors phrases
    "...", remplace par `(expr OR syn1 OR syn2 ...)`. Les phrases explicites
    entre guillemets sont préservées telles quelles.

    Exemple : `harcèlement moral` → `(harcèlement moral OR "intimidation morale"
    OR "vexation morale" OR "agissement répété" OR ...)`
    """
    if not q:
        return q
    th = _load_thesaurus()
    if not th:
        return q
    # Protéger les phrases "..." (on ne les étend PAS — l'utilisateur a été explicite)
    phrases: list[str] = []

    def _protect(m):
        phrases.append(m.group(0))
        return f"\x01{len(phrases) - 1}\x01"

    q2 = re.sub(r'"[^"]*"', _protect, q)
    # Trier les clés par longueur descendante pour matcher les plus longues d'abord
    # ("harcèlement moral" avant "harcèlement")
    keys = sorted(th.keys(), key=len, reverse=True)
    # Chaque clé remplacée une fois max (éviter matchs imbriqués)
    replaced_spans: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        for s, e in replaced_spans:
            if start < e and end > s:
                return True
        return False

    # On construit la nouvelle string en splice
    result_parts: list[tuple[int, int, str]] = []  # (start, end, replacement)
    for key in keys:
        pattern = r"\b" + re.escape(key) + r"\b"
        for m in re.finditer(pattern, q2, flags=re.IGNORECASE):
            if _overlaps(m.start(), m.end()):
                continue
            syns = th[key]
            # Quote multi-word synonyms for FTS5
            quoted = [f'"{s}"' if " " in s else s for s in syns]
            original = m.group(0)
            # Si original multi-mot aussi, le wrapper en phrase
            if " " in original:
                original_for_or = f'"{original}"'
            else:
                original_for_or = original
            replacement = "(" + original_for_or + " OR " + " OR ".join(quoted) + ")"
            result_parts.append((m.start(), m.end(), replacement))
            replaced_spans.append((m.start(), m.end()))
    # Apply replacements right-to-left to preserve offsets
    result_parts.sort(key=lambda x: -x[0])
    for start, end, rep in result_parts:
        q2 = q2[:start] + rep + q2[end:]
    # Restaurer phrases
    for i, p in enumerate(phrases):
        q2 = q2.replace(f"\x01{i}\x01", p)
    return q2


def normalize_fts_query(q: str, expand: bool = False) -> str:
    """Convertit les opérateurs multi-syntaxe vers FTS5/ES canonique.

    Accepte : AND/ET/& · OR/OU/| · NOT/SAUF/-mot · "phrase" · mot*
    Les tokens composés (14-80854, ECLI:…, C-72/24) sont wrappés en phrase.
    Les alias courts de juridictions (TJ, TGI, CAA…) sont étendus en OR.

    Args:
        q: la query utilisateur brute
        expand: si True, applique expand_synonyms() avant normalisation
            (élargit la recherche aux termes équivalents du thésaurus FR).
            Par défaut False — les tools MCP passent True explicitement.
    """
    if not q:
        return ""
    q = q.strip()
    # Expansion des synonymes (thésaurus) avant les opérateurs
    if expand:
        q = expand_synonyms(q)
    # Expansion des alias de juridictions (TJ → "(TJ OR TGI OR ...)")
    q = expand_juridiction_aliases(q)
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
