"""Test suite for MCP prompts and resources.

Locks down the prompts (workflows invocables par l'utilisateur) and
resources (catalogues) exposed by the FastMCP server : registration,
rendering with/without optional arguments, JSON validity of the
resources, and — surtout — cohérence : chaque tool référencé par la
matrice justicelibre://formats-identifiants doit exister sur le serveur,
et les catalogues doivent refléter les sources uniques (legi.py,
juriadmin.py), jamais des copies.

Run :
    python3 -m pytest tests/test_prompts_resources.py -v
ou :
    python3 tests/test_prompts_resources.py
"""
import asyncio
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import server  # noqa: E402
from sources import juriadmin, legi  # noqa: E402

EXPECTED_PROMPTS = {"verifier_citation", "droit_applicable", "dossier_jurisprudence"}
EXPECTED_RESOURCES = {
    "justicelibre://codes-supportes",
    "justicelibre://juridictions",
    "justicelibre://formats-identifiants",
}


def _read_resource(uri: str):
    contents = list(asyncio.run(server.mcp.read_resource(uri)))
    assert contents, f"resource vide : {uri}"
    return json.loads(contents[0].content)


def _render(name: str, arguments: dict) -> str:
    result = asyncio.run(server.mcp.get_prompt(name, arguments))
    assert result.messages, f"prompt {name} : aucun message rendu"
    return "\n".join(
        m.content.text for m in result.messages if hasattr(m.content, "text")
    )


def test_prompts_registered():
    prompts = {p.name: p for p in asyncio.run(server.mcp.list_prompts())}
    missing = EXPECTED_PROMPTS - set(prompts)
    assert not missing, f"prompts manquants : {missing}"
    for name in EXPECTED_PROMPTS:
        assert (prompts[name].description or "").strip(), f"{name} sans description"
    # verifier_citation : reference obligatoire, citation optionnelle
    args = {a.name: a for a in prompts["verifier_citation"].arguments or []}
    assert args["reference"].required is True
    assert args["citation"].required is False


def test_prompts_render():
    txt = _render("verifier_citation", {"reference": "CE n° 473286"})
    assert "CE n° 473286" in txt, "la référence n'est pas injectée"
    assert "texte intégral" in txt.lower(), "la règle snippet→texte manque"
    assert "build_source_url" in txt, "le lien source officiel manque"

    txt = _render("verifier_citation", {
        "reference": "article 1382 du Code civil",
        "citation": "la faute présumée du gardien",
    })
    assert "la faute présumée du gardien" in txt, "la citation n'est pas injectée"

    txt = _render("droit_applicable", {
        "code": "CC", "article": "1382", "date_des_faits": "1995-06-15",
    })
    assert "1995-06-15" in txt and "get_law_versions" in txt
    assert "date" in txt.lower(), "l'exigence de version datée manque"

    txt = _render("dossier_jurisprudence", {"sujet": "harcèlement moral"})
    assert "harcèlement moral" in txt
    assert "search_all" in txt and "hiérarchie" in txt.lower()


def test_resources_registered():
    resources = {str(r.uri) for r in asyncio.run(server.mcp.list_resources())}
    missing = EXPECTED_RESOURCES - resources
    assert not missing, f"resources manquantes : {missing}"


def test_resource_codes_supportes():
    data = _read_resource("justicelibre://codes-supportes")
    assert len(data) == len(legi.SUPPORTED_CODES), \
        f"catalogue désynchronisé de legi.SUPPORTED_CODES : {len(data)}"
    sans_legitext = [d["code"] for d in data if not d.get("legitext")]
    assert not sans_legitext, f"codes sans LEGITEXT : {sans_legitext}"


def test_resource_juridictions():
    data = _read_resource("justicelibre://juridictions")
    assert len(data["tribunaux_administratifs"]) == len(juriadmin.TRIBUNAUX_ADMIN)
    assert len(data["cours_administratives_appel"]) == len(juriadmin.COURS_ADMIN_APPEL)
    assert "CE" in data["conseil_etat"]


def test_formats_matrix_tools_exist():
    # Verrou de cohérence : la matrice de routage ne doit jamais pointer
    # vers un tool renommé ou supprimé.
    tool_names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    data = _read_resource("justicelibre://formats-identifiants")
    unknown = sorted({d["tool"] for d in data} - tool_names)
    assert not unknown, f"la matrice référence des tools inexistants : {unknown}"
    for entry in data:
        for key in ("format", "exemple", "signification", "tool"):
            assert entry.get(key), f"entrée incomplète ({key}) : {entry}"


# ─── Runner sans pytest ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("prompts registered",            test_prompts_registered),
        ("prompts render",                test_prompts_render),
        ("resources registered",          test_resources_registered),
        ("resource codes supportés",      test_resource_codes_supportes),
        ("resource juridictions",         test_resource_juridictions),
        ("matrice formats → tools réels", test_formats_matrix_tools_exist),
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
