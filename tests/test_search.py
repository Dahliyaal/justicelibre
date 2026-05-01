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
    ("2116343",                           "dossier_admin"),  # TA Paris 2021
    # Format CAA/TA codifié YY+CC+NNNN (ajouté avril 2026 — non-régression)
    ("03NC01126",                         "dossier_admin"),  # CAA Nancy 2003
    ("23DA00671",                         "dossier_admin"),  # CAA Douai 2023
    ("22PA05407",                         "dossier_admin"),  # CAA Paris 2022
    ("18NT01234",                         "dossier_admin"),  # CAA Nantes 2018
    ("89BX01126",                         "dossier_admin"),  # CAA Bordeaux 1989
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


# ─── Tests helpers : match_admin_docket / normalize_numero ────────

DOCKET_CASES = [
    # (input, expected_match) — None = ne doit PAS matcher
    ("03NC01126",       "03NC01126"),
    ("23DA00671",       "23DA00671"),
    ("22PA05407",       "22PA05407"),
    ("2116343",         "2116343"),
    ("497566",          "497566"),
    ("n° 03NC01126",    "03NC01126"),  # préfixe nettoyé
    ("  497566  ",      "497566"),     # whitespace
    ("liberté",         None),         # pas un numéro
    ("",                None),
    ("LEGIARTI000006", None),         # alphanumérique mais pas docket admin
]


def test_match_admin_docket():
    from query_intent import match_admin_docket
    errors = []
    for q, expected in DOCKET_CASES:
        got = match_admin_docket(q)
        if got != expected:
            errors.append(f"  {q!r:25} → got {got!r}, expected {expected!r}")
    assert not errors, "match_admin_docket mismatches:\n" + "\n".join(errors)


# ─── Tests filtre par date helper ────────────────────────────────

def test_date_in_range():
    from search_api import _date_in_range
    cases = [
        # (date_str, date_min, date_max, expected)
        ("2024-06-15", "2024-01-01", "2024-12-31", True),   # dans range
        ("2023-06-15", "2024-01-01", "2024-12-31", False),  # avant min
        ("2025-06-15", "2024-01-01", "2024-12-31", False),  # après max
        ("2024-06-15", "2024-06-15", "2024-06-15", True),   # bornes incluses
        ("2024-06-15", None, None, True),                   # pas de filtre
        ("2024-06-15", "2024-01-01", None, True),           # min seul
        ("2024-06-15", None, "2024-12-31", True),           # max seul
        ("",            "2024-01-01", "2024-12-31", True),  # date vide → laisse passer
    ]
    errors = []
    for d, dmin, dmax, expected in cases:
        got = _date_in_range(d, dmin, dmax)
        if got != expected:
            errors.append(f"  ({d!r}, {dmin!r}, {dmax!r}) → got {got}, expected {expected}")
    assert not errors, "_date_in_range mismatches:\n" + "\n".join(errors)


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


# ─── Tests d'expansion des alias de juridictions ────────────────

ALIAS_CASES = [
    # (input, doit contenir ces tokens dans le résultat)
    ("TJ Lyon",   ['"Tribunal judiciaire"', '"Tribunal de grande instance"', "TGI", "Lyon"]),
    ("TGI Paris", ['"Tribunal de grande instance"', '"Tribunal judiciaire"', "Paris"]),
    ("CAA Lyon",  ['"Cour administrative d\'appel"', "Lyon"]),
    ("CEDH 2020", ['"Cour européenne des droits de l\'homme"', "2020"]),
    ("CJUE 2023", ['"Cour de justice de l\'Union européenne"', "CJCE", "2023"]),
    # Cas négatifs : alias ambigus doivent NE PAS être étendus
    ("CC 2020",   ["CC", "2020"]),  # CC ambigu (Code civil aussi) → pas d'expansion
    ("CE 2024",   ["CE", "2024"]),  # CE ambigu (pronoun ce capitalisé) → pas d'expansion
]


def test_alias_expansion():
    from query_intent import expand_juridiction_aliases
    errors = []
    for q, must_contain in ALIAS_CASES:
        result = expand_juridiction_aliases(q)
        for token in must_contain:
            if token not in result:
                errors.append(f"  {q!r} → {result!r} (manque : {token!r})")
    assert not errors, "Alias expansion mismatches:\n" + "\n".join(errors)


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
    ("licenciement",   "cedh",   ""),                    # FTS5 CEDH (non-vide)
    ("ECLI:FR:CCASS:2020:SO00283", "dila", "SO00283"),  # ECLI → direct lookup (non-FTS)
    ("62024CJ0642",    "cjue",   "62024CJ0642"),         # CELEX → direct lookup CJUE
]


def test_live():
    """Appels HTTP contre la prod. Skip si pas internet/serveur indispo.

    Distingue les vraies régressions (logique cassée → AssertionError) des
    erreurs réseau (timeout, fetch error → warning seulement, le runner
    n'échoue pas car ce ne sont pas des bugs de code).
    """
    try:
        import urllib.request, json
    except ImportError:
        print("[SKIP live] pas d'urllib")
        return
    logic_errors = []
    fetch_errors = []
    for q, src_expected, must_contain in LIVE_CASES:
        url = f"https://justicelibre.org/api/search?q={urllib.request.quote(q)}&sources={src_expected}&limit=10&timeout=30"
        req = urllib.request.Request(url, headers={"User-Agent": "justicelibre-test/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read())
        except Exception as e:
            fetch_errors.append(f"  {q!r} → fetch error: {e}")
            continue
        results = data.get("results", [])
        if not results:
            logic_errors.append(f"  {q!r} → 0 résultats sur source={src_expected}")
            continue
        found = any(
            must_contain in (
                r.get("title", "") + r.get("extract", "") + r.get("id", "")
                + r.get("numero", "") + r.get("juridiction", "") + r.get("ecli", "")
            )
            for r in results
        )
        if not found:
            logic_errors.append(f"  {q!r} → aucun résultat ne contient {must_contain!r}")
    if fetch_errors:
        print("[WARN] erreurs réseau (pas une régression de code) :")
        for e in fetch_errors:
            print(e)
    if logic_errors:
        raise AssertionError("Live API logic regressions:\n" + "\n".join(logic_errors))


# ─── Runner minimaliste sans pytest ───────────────────────────────

if __name__ == "__main__":
    tests = [
        ("intent detection",     test_intent_detection),
        ("match_admin_docket",   test_match_admin_docket),
        ("date_in_range",        test_date_in_range),
        ("normalize fts",        test_normalize),
        ("alias expansion",      test_alias_expansion),
        ("source routing",       test_routing),
        ("live API",             test_live),
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
