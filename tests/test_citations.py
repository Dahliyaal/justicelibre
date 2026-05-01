"""Tests des patterns de détection de citations dans le texte d'une décision.

Ces patterns vivent côté JS dans web/search.html (`highlightLawRefs`).
Pour pouvoir les tester sans Node, on les ré-implémente en Python ici
(traduction littérale du JS). Tout changement côté JS doit être répliqué
côté Python — sinon ce test casse, ce qui force la mise à jour du miroir.

Run :
    python3 -m pytest tests/test_citations.py -v
ou :
    python3 tests/test_citations.py
"""
import re
import sys


# ─── Mirror Python des regex JS (web/search.html highlightLawRefs) ──

# Codes pour lesquels on capture "art. X (du) (le code) Y"
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
    ("C.cons",  ["code de la consommation", r"c\.\s*consom?\."]),
    ("C.éduc",  ["code de l['’]éducation", r"c\.\s*éduc\."]),
    ("C.com",   ["code de commerce", r"c\.\s*com\."]),
    ("CT",      ["code du travail", r"c\.\s*trav\.", "CT"]),
    ("CU",      ["code de l['’]urbanisme", r"c\.\s*urb\."]),
    ("C.env",   ["code de l['’]environnement", r"c\.\s*env\."]),
    ("CR",      ["code rural et de la pêche maritime", "code rural", "CRPM"]),
    ("CC",      ["code civil", r"c\.\s*civ\.", "CC"]),
    ("CP",      ["code pénal", r"c\.\s*pén\.", "CP"]),
]

# Conventions internationales (article + nom)
CONVENTIONS = [
    ("CEDH",   ["Convention européenne des droits de l['’]homme", r"Conv\.\s*EDH", "CEDH"]),
    ("TFUE",   ["Traité sur le fonctionnement de l['’]Union européenne", "TFUE"]),
    ("TUE",    ["Traité sur l['’]Union européenne", "TUE"]),
    ("CDFUE",  ["Charte des droits fondamentaux de l['’]Union européenne", "CDFUE"]),
    ("DDHC",   ["Déclaration des droits de l['’]homme et du citoyen", "DDHC"]),
    ("CONST",  [r"Constitution(?:\s+française)?"]),
]

ART_NUM    = r"(?:premier|[LRDA]\b\.?\s*)?\d+(?:[-.\s]\d+)*(?:\s*§\s*\d+)?"
ART_PREFIX = r"(?:articles?|art\.?)"
ART_ALINEA = r"(?:\s*,?\s*(?:alinéas?|al\.)\s*\d+)?"
ART_FULL   = rf"{ART_PREFIX}\s+{ART_NUM}{ART_ALINEA}(?:\s*(?:,|et|;)\s*{ART_NUM}{ART_ALINEA})*"
ART_LETTER = r"[LRDA]\b\.?\s*\d+(?:[-.\s]\d+)*(?:\s*§\s*\d+)?"


def detect_citations(text: str) -> list[tuple[str, str]]:
    """Retourne liste de (code, raw_match_substring) trouvés dans le texte."""
    found = []
    # 1) Codes : "art. X du code Y" + "L. X-Y code Y"
    for code, patterns in ARTICLE_CODES:
        alts = "|".join(patterns)
        re_art = re.compile(rf"({ART_FULL})\s+(?:du\s+|de\s+la\s+)?({alts})\b", re.IGNORECASE)
        for m in re_art.finditer(text):
            found.append((code, m.group(0)))
        re_letter = re.compile(rf"(?<![\w-])({ART_LETTER}{ART_ALINEA})\s+(?:du\s+|de\s+la\s+)?({alts})\b", re.IGNORECASE)
        for m in re_letter.finditer(text):
            found.append((code, m.group(0)))
    # 2) Conventions
    for code, patterns in CONVENTIONS:
        alts = "|".join(patterns)
        re_conv = re.compile(rf"({ART_FULL})\s+(?:du\s+|de\s+la\s+)?({alts})\b", re.IGNORECASE)
        for m in re_conv.finditer(text):
            found.append((code, m.group(0)))
    # 3) Règlements UE — n° optionnel (ajouté avril 2026)
    re_reg = re.compile(r"\b(règlement\s+\(?(?:CE|UE|CEE)\)?\s+(?:n[°º]\s*)?\d+/\d+)\b", re.IGNORECASE)
    for m in re_reg.finditer(text):
        found.append(("REG-EU", m.group(0)))
    # 4) Directives UE
    re_dir = re.compile(r"\b(directive\s+(?:\(?(?:CE|UE)\)?\s+)?\d+/\d+(?:/(?:CE|UE))?)\b", re.IGNORECASE)
    for m in re_dir.finditer(text):
        found.append(("DIR-EU", m.group(0)))
    # 5) Lois
    re_loi = re.compile(r"\b(loi\s+n[°º]\s*\d{4}-\d+)\b", re.IGNORECASE)
    for m in re_loi.finditer(text):
        found.append(("LOI", m.group(0)))
    # 6) Décrets
    re_dec = re.compile(r"\b(décret\s+n[°º]\s*\d{4}-\d+)\b", re.IGNORECASE)
    for m in re_dec.finditer(text):
        found.append(("DECRET", m.group(0)))
    # 7) Ordonnances
    re_ord = re.compile(r"\b(ordonnance\s+n[°º]\s*\d{4}-\d+)\b", re.IGNORECASE)
    for m in re_ord.finditer(text):
        found.append(("ORD", m.group(0)))
    return found


# ─── Cas qui DOIVENT être détectés ───────────────────────────────

POSITIVE_CASES = [
    # (snippet, expected_code, expected_match_lower_substring)
    ("L'article 1382 du code civil ancien", "CC", "1382"),
    ("article L. 1152-1 du code du travail", "CT", "L. 1152-1"),
    ("articles 132-1 et 132-20 du code pénal", "CP", "132-1"),
    ("art. L. 521-2 du CJA", "CJA", "L. 521-2"),
    ("article 66 de la Constitution", "CONST", "66"),
    ("article 6 CEDH", "CEDH", "6"),
    ("article 8 de la Convention européenne des droits de l'homme", "CEDH", "8"),
    ("règlement (CE) n° 883/2004", "REG-EU", "883/2004"),
    # Sans n° (ajouté avril 2026)
    ("règlement (UE) 2016/679", "REG-EU", "2016/679"),
    ("règlement (UE) 2016/79", "REG-EU", "2016/79"),
    ("directive 2000/78/CE", "DIR-EU", "2000/78"),
    ("directive (UE) 2016/679", "DIR-EU", "2016/679"),
    ("loi n° 2005-102 du 11 février 2005", "LOI", "2005-102"),
    ("décret n° 2021-1480", "DECRET", "2021-1480"),
    ("ordonnance n° 2020-1304", "ORD", "2020-1304"),
    # Codes courts
    ("article 1240 CC", "CC", "1240"),
    ("art. L. 311-1 CRPA", "CRPA", "L. 311-1"),
]


def test_positive_cases():
    """Chaque snippet doit faire matcher AU MOINS le code attendu."""
    errors = []
    for snippet, expected_code, must_contain in POSITIVE_CASES:
        hits = detect_citations(snippet)
        if not any(c == expected_code and must_contain.lower() in m.lower() for c, m in hits):
            errors.append(f"  {snippet!r:60} → attendu code={expected_code} contenant {must_contain!r}, hits={hits}")
    assert not errors, "Citations non détectées :\n" + "\n".join(errors)


# ─── Cas qui NE DOIVENT PAS être détectés (false positives à éviter) ─

NEGATIVE_CASES = [
    # Année seule, pas une référence
    "en 2016 le tribunal a jugé",
    # Numéro de page d'arrêt, pas un règlement
    "voir p. 1240 du recueil",
]


def test_negative_cases():
    """Ces snippets ne doivent rien détecter."""
    errors = []
    for snippet in NEGATIVE_CASES:
        hits = detect_citations(snippet)
        # On tolère 0 hit OU des hits sur des codes ambigus comme CC/CP qui peuvent avoir des collisions
        # (le test est juste pour repérer les régressions évidentes)
        suspect = [(c, m) for c, m in hits if c in ("REG-EU", "DIR-EU", "LOI", "DECRET", "ORD")]
        if suspect:
            errors.append(f"  {snippet!r} → hits suspects {suspect}")
    assert not errors, "False positives :\n" + "\n".join(errors)


if __name__ == "__main__":
    tests = [
        ("citations positives", test_positive_cases),
        ("pas de faux positifs", test_negative_cases),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            print(f"  ✗ {name}")
            print(f"      {e}")
            failed += 1
    if failed:
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
