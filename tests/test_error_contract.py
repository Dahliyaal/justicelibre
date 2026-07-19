"""Test suite for the MCP error contract and tool schemas.

Locks down the anti-pattern fixes required by Anthropic's "writing
effective tools for agents" guidance and the Connectors Directory review :
structured, actionable errors (`_tool_error`), offline validation errors
(no DB touched), no credential parameters exposed in tool schemas,
FTS5 query sanitization, and pagination (`offset`) on CEDH/CJUE search.

All tests run OFFLINE — no local DB, no network.

Run :
    python3 -m pytest tests/test_error_contract.py -v
ou :
    python3 tests/test_error_contract.py
"""
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import server  # noqa: E402
from sources import dila  # noqa: E402


def _list_tools():
    return asyncio.run(server.mcp.list_tools())


def _tool_by_name(name):
    for t in _list_tools():
        if t.name == name:
            return t
    raise AssertionError(f"tool introuvable : {name}")


def test_tool_error_shape():
    err = server._tool_error("msg", category="validation", retryable=False, hint="x")
    assert isinstance(err, dict), f"_tool_error doit retourner un dict, pas {type(err)}"
    for key in ("error", "error_category", "retryable", "hint"):
        assert key in err, f"clé manquante dans _tool_error : {key}"
    assert isinstance(err["error"], str), "error doit être une str"
    assert err["error_category"] == "validation"
    assert err["retryable"] is False
    assert err["hint"] == "x"


def test_validation_errors_offline():
    # Aucun paramètre → erreur de validation, sans toucher aucune DB.
    res = asyncio.run(server.search_judiciaire_libre())
    assert isinstance(res, dict), f"attendu un dict, reçu {type(res)}"
    assert res.get("error_category") == "validation", \
        f"search_judiciaire_libre() sans paramètre : error_category={res.get('error_category')!r}"

    # Query composée uniquement d'espaces → erreur de validation.
    res = asyncio.run(server.search_cedh(query="  "))
    assert isinstance(res, dict), f"attendu un dict, reçu {type(res)}"
    assert res.get("error_category") == "validation", \
        f"search_cedh(query='  ') : error_category={res.get('error_category')!r}"


def test_no_credentials_params():
    # Aucun tool ne doit exposer un paramètre client_secret.
    leaking = [
        t.name for t in _list_tools()
        if "client_secret" in (t.inputSchema or {}).get("properties", {})
    ]
    assert not leaking, "tools exposant client_secret :\n  " + "\n  ".join(leaking)

    # search_judiciaire n'a plus de paramètre client_id.
    props = (_tool_by_name("search_judiciaire").inputSchema or {}).get("properties", {})
    assert "client_id" not in props, "search_judiciaire expose encore client_id"


def test_fts5_sanitizer():
    out = dila._sanitize_fts5("l'article 8 : (vie) *")
    assert "'" not in out, f"apostrophe non nettoyée : {out!r}"
    assert ":" not in out, f"deux-points non nettoyé : {out!r}"
    # Les parenthèses hors groupe booléen (`mot (précision)`) sont une
    # SyntaxError FTS5 → retirées. Elles ne survivent qu'avec AND/OR/NOT.
    assert "(" not in out, f"parenthèses décoratives conservées : {out!r}"
    boolean = dila._sanitize_fts5('("article 1240" OR "art 1240") AND "code civil"')
    assert "(" in boolean and ")" in boolean, \
        f"parenthèses de groupe booléen perdues : {boolean!r}"


def test_fts5_sanitizer_real_engine():
    # Verrou anti-régression : chaque query sanitizée doit passer MATCH sur
    # un vrai index FTS5 (le cas "79-105" plantait avant le quoting des
    # tokens à tiret).
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
    cases = [
        "79-105 DC",
        "garde-à-vue",
        "l'article 8 : (vie familiale)",
        'phrase "non fermée',
        "mot - isolé",
        "-negation",
        "préfixe* et * seul",
        '"phrase exacte" AND 79-105',
        "C-72/24",
        '("article 1240" OR "art 1240") AND ("code civil" OR "CC")',
        "harcèlement AND",
        'décision "79-105 DC"',
    ]
    failures = []
    for case in cases:
        sanitized = dila._sanitize_fts5(case)
        if not sanitized:
            continue  # query vide → gérée en amont par les sources
        try:
            conn.execute("SELECT count(*) FROM t WHERE t MATCH ?", (sanitized,))
        except sqlite3.OperationalError as e:
            failures.append(f"{case!r} -> {sanitized!r} : {e}")
    conn.close()
    assert not failures, "queries sanitizées rejetées par FTS5 :\n  " + \
        "\n  ".join(failures)


def test_pagination_params():
    for name in ("search_cedh", "search_cjue"):
        props = (_tool_by_name(name).inputSchema or {}).get("properties", {})
        assert "offset" in props, f"{name} n'expose pas de paramètre offset"


# ─── Runner sans pytest ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("_tool_error shape",           test_tool_error_shape),
        ("validation errors offline",   test_validation_errors_offline),
        ("no credentials params",       test_no_credentials_params),
        ("fts5 sanitizer",              test_fts5_sanitizer),
        ("fts5 sanitizer (moteur réel)", test_fts5_sanitizer_real_engine),
        ("pagination params",           test_pagination_params),
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
