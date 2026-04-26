"""Test suite for source_url construction (warehouse).

Locks down the URL patterns produced by `_build_source_url` so that
any change to the regex or the dispatch table is caught by CI.

Run :
    python3 -m pytest tests/test_source_url.py -v
ou :
    python3 tests/test_source_url.py
"""
import sys
import os
import tempfile
import importlib.util

# warehouse_server.py vérifie la présence d'une clé secrète à l'import.
# En CI/local, on fournit une fausse clé temporaire pour permettre le chargement.
_tmp_key = tempfile.NamedTemporaryFile(delete=False, suffix=".key", mode="w")
_tmp_key.write("a" * 64)  # 64 chars hex valide
_tmp_key.close()
os.chmod(_tmp_key.name, 0o600)
os.environ["JL_WAREHOUSE_KEY_FILE"] = _tmp_key.name

# Charger warehouse_server.py sans passer par un package
_HERE = os.path.dirname(os.path.abspath(__file__))
_WH_PATH = os.path.join(os.path.dirname(_HERE), "warehouse", "warehouse_server.py")
spec = importlib.util.spec_from_file_location("warehouse_server", _WH_PATH)
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


# ─── Cas : (identifier, legitext, at_date, expected_url_or_None) ──

URL_CASES = [
    # LEGIARTI sans legitext → /codes/ par défaut
    ("LEGIARTI000006419300", "", None,
     "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006419300"),

    # LEGIARTI + LEGITEXT (code) → /codes/
    ("LEGIARTI000006419300", "LEGITEXT000006070721", None,
     "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006419300"),

    # LEGIARTI + JORFTEXT (loi non codifiée) → /loda/
    ("LEGIARTI000006528059", "JORFTEXT000000886460", None,
     "https://www.legifrance.gouv.fr/loda/article_lc/LEGIARTI000006528059"),

    # Avec date → suffixe /YYYY-MM-DD
    ("LEGIARTI000006436219", "LEGITEXT000006070721", "1992-05-15",
     "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006436219/1992-05-15"),
    ("LEGIARTI000006528059", "JORFTEXT000000886460", "2010-06-01",
     "https://www.legifrance.gouv.fr/loda/article_lc/LEGIARTI000006528059/2010-06-01"),

    # Date invalide → ignorée (pas de suffixe)
    ("LEGIARTI000006419300", "", "not-a-date",
     "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006419300"),

    # LEGITEXT seul → page texte du code
    ("LEGITEXT000006070721", "", None,
     "https://www.legifrance.gouv.fr/codes/texte_lc/LEGITEXT000006070721"),

    # JORFTEXT seul → page LODA
    ("JORFTEXT000000886460", "", None,
     "https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000886460"),
    ("JORFTEXT000000886460", "", "2024-01-01",
     "https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000886460/2024-01-01"),

    # Décisions Légifrance
    ("JURITEXT000042579700", "", None,
     "https://www.legifrance.gouv.fr/juri/id/JURITEXT000042579700"),
    ("CONSTEXT000049574021", "", None,
     "https://www.legifrance.gouv.fr/juri/id/CONSTEXT000049574021"),
    ("CETATEXT000007572652", "", None,
     "https://www.legifrance.gouv.fr/ceta/id/CETATEXT000007572652"),

    # CELEX (CJUE) — format 6XXXXLLNNNN
    ("62024CJ0642", "", None,
     "https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:62024CJ0642"),

    # ECLI européen
    ("ECLI:EU:C:2024:642", "", None,
     "https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=ecli:ECLI:EU:C:2024:642"),

    # HUDOC itemid (CEDH)
    ("001-249914", "", None,
     "https://hudoc.echr.coe.int/fre?i=001-249914"),

    # ID inconnu → None
    ("foobar123", "", None, None),
    ("", "", None, None),
]


def test_build_source_url():
    errors = []
    for ident, legitext, at_date, expected in URL_CASES:
        got = ws._build_source_url(ident, legitext=legitext, at_date=at_date)
        if got != expected:
            errors.append(
                f"  ({ident!r}, legitext={legitext!r}, date={at_date!r})\n"
                f"      got      {got!r}\n      expected {expected!r}"
            )
    assert not errors, "URL construction mismatches:\n" + "\n".join(errors)


# ─── Code → LEGITEXT mapping (ne doit pas régresser) ─────────────

CODE_MAPPING_CASES = [
    ("CC", "LEGITEXT000006070721"),
    ("CP", "LEGITEXT000006070719"),
    ("CT", "LEGITEXT000006072050"),
    ("CONST", "JORFTEXT000000571356"),  # Constitution = JORFTEXT, pas LEGITEXT
    ("LIL", "JORFTEXT000000886460"),    # Loi 78-17
    ("LO58", "JORFTEXT000000705065"),   # Ordonnance 58-1067
]


def test_code_mapping():
    errors = []
    for code, expected in CODE_MAPPING_CASES:
        got = ws.CODE_TO_LEGITEXT.get(code)
        if got != expected:
            errors.append(f"  {code!r} → got {got!r}, expected {expected!r}")
    assert not errors, "CODE_TO_LEGITEXT mismatches:\n" + "\n".join(errors)


# ─── Runner sans pytest ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("source URL construction",  test_build_source_url),
        ("CODE → LEGITEXT mapping",  test_code_mapping),
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
