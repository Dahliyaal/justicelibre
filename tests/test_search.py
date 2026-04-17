"""Test suite de régression pour la recherche fédérée.

Chaque test = (query, ce qu'on s'attend à trouver). Si un test casse
après une modif, on sait que la régression a eu lieu.

Usage :
    python3 -m pytest tests/test_search.py -v
ou sans pytest :
    python3 tests/test_search.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from query_intent import detect_intent, normalize_fts_query, sources_for_intent


# ─── Tests intent detection ───────────────────────────────────────

INTENT_CASES = [
    # (query, expected_kind)
    ("102948",                            "ariane_id"),
    ("14-80854",                          "pourvoi"),
    ("14-80.854",                         "pourvoi"),
    ("2205872",                           "dossier_admin"),
    ("23/00854",                          "rg"),
    ("62024CJ0642",                       "celex"),
    ("ECLI:EU:C:2024:642",                "ecli"),
    ("ECLI:FR:CCASS:2020:SO00283",        "ecli"),
    ("DCE_503506_20260409",               "dce_id"),
    ("001-249914",                        "itemid_hudoc"),
    ("JURITEXT000042579700",              "juritext"),
    ("CONSTEXT000049574021",              "juritext"),
    ('"atteinte à la liberté"',           "phrase"),
    ("liberté académique",                "fts"),
    ("licenciement AND harcèlement",      "fts"),
    ("",                                   "empty"),
]


def test_intent_detection():
    errors = []
    for q, expected in INTENT_CASES:
        intent = detect_intent(q)
        if intent.kind != expected:
            errors.append(f"  {q!r:50} → got {intent.kind}, expected {expected}")
    assert not errors, "Intent mismatches:\n" + "\n".join(errors)


# ─── Tests normalize_fts_query ─────────────────────────────────────

NORMALIZE_CASES = [
    ("liberté signalement",               "liberté signalement"),
    ("liberté AND signalement",           "liberté AND signalement"),
    ("liberté ET signalement",            "liberté AND signalement"),
    ("liberté & signalement",             "liberté AND signalement"),
    ("liberté&signalement",               "liberté AND signalement"),
    ("liberté OU travail",                "liberté OR travail"),
    ("liberté | travail",                 "liberté OR travail"),
    ("licenciement NOT harcèlement",      "licenciement NOT harcèlement"),
    ("licenciement SAUF harcèlement",     "licenciement NOT harcèlement"),
    ("licenciement -harcèlement",         "licenciement NOT harcèlement"),
    ("14-80854",                          '"14 80854"'),
    ("C-72/24",                           '"C 72 24"'),
    ("ECLI:EU:C:2024:642",                '"ECLI EU C 2024 642"'),
    ('"atteinte à la liberté"',           '"atteinte à la liberté"'),
    ("signal*",                           "signal*"),
]


def test_normalize():
    errors = []
    for q, expected in NORMALIZE_CASES:
        got = normalize_fts_query(q)
        if got != expected:
            errors.append(f"  {q!r:40} → got {got!r}, expected {expected!r}")
    assert not errors, "Normalize mismatches:\n" + "\n".join(errors)


# ─── Tests routage par source (intent → sources pertinentes) ─────

ROUTING_CASES = [
    # (intent_kind, allowed_sources, must_include)
    ("ariane_id",      ["ariane", "admin", "dila", "cedh", "cjue"],  {"ariane", "admin"}),
    ("pourvoi",        ["ariane", "admin", "dila", "cedh", "cjue"],  {"dila"}),
    ("rg",             ["ariane", "admin", "dila", "cedh", "cjue"],  {"dila"}),
    ("celex",          ["ariane", "admin", "dila", "cedh", "cjue"],  {"cjue"}),
    ("itemid_hudoc",   ["ariane", "admin", "dila", "cedh", "cjue"],  {"cedh"}),
    ("juritext",       ["ariane", "admin", "dila", "cedh", "cjue"],  {"dila"}),
    ("dce_id",         ["ariane", "admin", "dila", "cedh", "cjue"],  {"admin"}),
    ("fts",            ["ariane", "admin", "dila", "cedh", "cjue"],  {"ariane", "admin", "dila", "cedh", "cjue"}),
]


def test_routing():
    from query_intent import QueryIntent
    errors = []
    for kind, allowed, required in ROUTING_CASES:
        got = set(sources_for_intent(QueryIntent(kind=kind), allowed))
        missing = required - got
        if missing:
            errors.append(f"  kind={kind}: missing {missing} in {got}")
    assert not errors, "Routing mismatches:\n" + "\n".join(errors)


# ─── Tests live API (optionnel, nécessite serveur up) ─────────────

LIVE_CASES = [
    # (query, source_expected_to_have_hit, must_contain_in_any_result)
    # Régressions connues, chacune avec une attente vérifiable :
    ("102948",         "ariane", "102948"),          # ArianeWeb ID lookup direct
    ("14-80854",       "dila",   "14-80854"),        # Cass crim 16/12/2014 (racisme anti-Blancs)
    ("liberté académique", "ariane", "liberté"),     # FTS sémantique ArianeWeb
    ("licenciement",   "cedh",   ""),                # Juste vérifier non-vide (FTS5 CEDH)
    # TODO : ECLI direct lookup nécessite d'ajouter le champ `ecli` au FTS5
    # index (ou un lookup par colonne direct). Régression à corriger :
    # ("ECLI:FR:CCASS:2020:SO00283", "dila", "SO00283"),
]


def test_live():
    """Appels HTTP contre la prod. Skip si pas internet/serveur indispo."""
    try:
        import urllib.request, json
    except ImportError:
        print("[SKIP live] pas d'urllib")
        return
    errors = []
    for q, src_expected, must_contain in LIVE_CASES:
        url = f"https://justicelibre.org/api/search?q={urllib.request.quote(q)}&sources={src_expected}&limit=10&timeout=30"
        req = urllib.request.Request(url, headers={"User-Agent": "justicelibre-test/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read())
        except Exception as e:
            errors.append(f"  {q!r} → fetch error: {e}")
            continue
        results = data.get("results", [])
        if not results:
            errors.append(f"  {q!r} → 0 résultats sur source={src_expected}")
            continue
        found = any(
            must_contain in (
                r.get("title", "") + r.get("extract", "") + r.get("id", "")
                + r.get("numero", "") + r.get("juridiction", "")
            )
            for r in results
        )
        if not found:
            errors.append(f"  {q!r} → aucun résultat ne contient {must_contain!r}")
    if errors:
        raise AssertionError("Live API mismatches:\n" + "\n".join(errors))


# ─── Runner minimaliste sans pytest ───────────────────────────────

if __name__ == "__main__":
    tests = [
        ("intent detection",  test_intent_detection),
        ("normalize fts",     test_normalize),
        ("source routing",    test_routing),
        ("live API",          test_live),
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
        except Exception as e:
            print(f"  ! {name} (erreur runtime) : {e}")
            failed += 1
    if failed:
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
