"""Détection de citations d'articles de loi dans le texte d'une décision.

Port Python du regex `highlightLawRefs` de `web/search.html`. Utilisé par :
- `ssr.render_decision()` pour insérer des liens internes `/loi/{code}/{num}`
  dans les pages décision (énorme gain de maillage interne pour les bots).
- `tests/test_citations.py` qui en garde une copie locale (à synchroniser).

Convention : retourne `[(code, num)]` *normalisé* (sans espaces ni points
dans `num`) pour pouvoir construire directement l'URL `/loi/{code}/{num}`
qui matchera le `num` côté warehouse (`legi_articles.num` est aussi sans
ponctuation : 'R772-8', pas 'R. 772-8').
"""
from __future__ import annotations

import re

# Codes français — alias possibles dans les jugements + code court canonique
ARTICLE_CODES = [
    ("CESEDA",  ["code de l['’]entrée et du séjour des étrangers et du droit d['’]asile", "CESEDA"]),
    ("CGCT",    ["code général des collectivités territoriales", "CGCT"]),
    ("CGI",     ["code général des impôts", "CGI"]),
    ("CRPA",    ["code des relations entre le public et l['’]administration", "CRPA"]),
    ("CCH",     ["code de la construction et de l['’]habitation", "CCH"]),
    ("CPI",     ["code de la propriété intellectuelle", "CPI"]),
    ("CASF",    ["code de l['’]action sociale et des familles", "CASF"]),
    ("CMF",     ["code monétaire et financier", "CMF"]),
    ("CSS",     ["code de la sécurité sociale", r"c\.\s*séc\.\s*soc\.", "CSS"]),
    ("CSP",     ["code de la santé publique", r"c\.\s*santé\s*publ\.", "CSP"]),
    ("CJA",     ["code de justice administrative", "CJA"]),
    ("CPC",     ["code de procédure civile", r"c\.\s*pr\.\s*civ\.", "CPC", "NCPC"]),
    ("CPP",     ["code de procédure pénale", r"c\.\s*pr\.\s*pén\.", "CPP"]),
    ("CT",      ["code du travail", r"c\.\s*trav\.", "CT"]),
    ("CC",      ["code civil", r"c\.\s*civ\.", "CC"]),
    ("CP",      ["code pénal", r"c\.\s*pén\.", "CP"]),
]

ART_NUM    = r"(?:premier|[LRDA]\b\.?\s*)?\d+(?:[-.\s]\d+)*(?:\s*§\s*\d+)?"
ART_PREFIX = r"(?:articles?|art\.?)"
ART_ALINEA = r"(?:\s*,?\s*(?:alinéas?|al\.)\s*\d+)?"
ART_FULL   = rf"{ART_PREFIX}\s+({ART_NUM}){ART_ALINEA}"
ART_LETTER = r"(?<![\w-])([LRDA]\b\.?\s*\d+(?:[-.\s]\d+)*(?:\s*§\s*\d+)?)"


def _normalize_num(raw: str) -> str:
    """Strip espaces + points pour matcher LEGI (`R. 772-8` → `R772-8`).

    Doit rester cohérent avec `warehouse_server._normalize_num`.
    """
    return raw.strip().replace(" ", "").replace(".", "")


CONVENTIONS = [
    ("CEDH",  ["Convention européenne des droits de l['’]homme", r"Conv\.\s*EDH", "CEDH"]),
    ("CONST", [r"Constitution(?:\s+française)?"]),
    ("DDHC",  ["Déclaration des droits de l['’]homme et du citoyen", "DDHC"]),
]

# Pattern qui capture une *liste* d'articles : "articles X, Y et Z du code A"
ART_LIST = rf"{ART_PREFIX}\s+({ART_NUM}{ART_ALINEA}(?:\s*(?:,|et|;)\s*{ART_NUM}{ART_ALINEA})*)"
# Pour itérer sur chaque numéro à l'intérieur de la liste
_NUM_ITER = re.compile(rf"({ART_NUM})", re.IGNORECASE)


def detect_citations(text: str) -> list[tuple[str, str, tuple[int, int]]]:
    """Retourne `[(code, num_normalized, (start, end))]` triés par position.

    Gère les énumérations : "articles L.262-8, L.262-4 du CASF" → 2 liens.
    `(start, end)` désigne la position du *numéro* dans le texte source.
    """
    if not text:
        return []
    raw_hits: list[tuple[str, str, int, int]] = []
    # 1) Énumérations préfixées par "article(s)" + (du) code X
    for code, patterns in ARTICLE_CODES + CONVENTIONS:
        alts = "|".join(patterns)
        re_full = re.compile(
            rf"{ART_LIST}\s+(?:du\s+|de\s+la\s+)?(?:{alts})\b",
            re.IGNORECASE,
        )
        for m in re_full.finditer(text):
            list_str = m.group(1)
            list_offset = m.start(1)
            # Itère sur chaque numéro dans la liste capturée
            for nm in _NUM_ITER.finditer(list_str):
                num_raw = nm.group(1)
                if not re.search(r"\d", num_raw):
                    continue
                s = list_offset + nm.start()
                e = list_offset + nm.end()
                raw_hits.append((code, num_raw, s, e))
    # 2) "L. X-Y code Y" sans préfixe "article"
    for code, patterns in ARTICLE_CODES:
        alts = "|".join(patterns)
        re_letter = re.compile(
            rf"(?<![\w-])([LRDA]\b\.?\s*\d+(?:[-.\s]\d+)*(?:\s*§\s*\d+)?)\s+(?:du\s+|de\s+la\s+)?(?:{alts})\b",
            re.IGNORECASE,
        )
        for m in re_letter.finditer(text):
            raw_hits.append((code, m.group(1), m.start(1), m.end(1)))
    # Dédoublonner par span (garder la 1ère occurrence non chevauchante)
    raw_hits.sort(key=lambda h: (h[2], -h[3]))
    out: list[tuple[str, str, tuple[int, int]]] = []
    last_end = -1
    for code, num_raw, s, e in raw_hits:
        if s < last_end:
            continue
        num_clean = _normalize_num(num_raw)
        if not num_clean or not re.search(r"\d", num_clean):
            continue
        out.append((code, num_clean, (s, e)))
        last_end = e
    return out


def linkify(text: str, esc) -> str:
    """Transforme `text` (str brut) en HTML avec liens internes vers /loi/{code}/{num}.

    `esc` = fonction d'échappement HTML (pour éviter d'échapper deux fois).
    Les portions hors citation sont escapées normalement.
    """
    if not text:
        return ""
    hits = detect_citations(text)
    if not hits:
        return esc(text)
    chunks: list[str] = []
    cursor = 0
    for code, num, (s, e) in hits:
        if s > cursor:
            chunks.append(esc(text[cursor:s]))
        raw = text[s:e]
        href = f"/loi/{code}/{num}"
        chunks.append(
            f'<a href="{esc(href)}" class="lawref" '
            f'title="{esc(code)} {esc(num)}">{esc(raw)}</a>'
        )
        cursor = e
    if cursor < len(text):
        chunks.append(esc(text[cursor:]))
    return "".join(chunks)
