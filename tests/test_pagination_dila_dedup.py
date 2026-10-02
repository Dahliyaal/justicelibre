"""Recherche judiciaire filtrée : pages pleines et « Charger la suite ».

Audit du 2 oct. 2026, R3 : /api/search?...&sources=dila&juridiction=cass&limit=30
rendait `total 33596, total_rendus 19` : le dédoublonnage JURITEXT/Judilibre
(_dedupe_ecli) passait APRÈS le LIMIT SQL ; search.html ne proposait la suite
que sur une page pleine (19 < 30) : l'usager restait bloqué à 19 arrêts.

Hors ligne : `dila.search` simulé (corpus où un arrêt sur deux a un jumeau),
aucune base, aucun réseau. Le front est vérifié avec node s'il est installé.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import search_api  # noqa: E402
from sources import dila  # noqa: E402

# 200 arrêts distincts ; les pairs ont un jumeau (même ECLI) juste derrière :
# 300 lignes en base, comme JURITEXT + Judilibre.
CORPUS = []
for i in range(200):
    row = {"id": f"JURITEXT{i:06d}", "titre": f"Arrêt {i}", "date": "2020-01-01",
           "juridiction": "Cour de cassation", "numero": f"19-{i:05d}",
           "ecli": f"ECLI:FR:CCASS:2020:SO{i:05d}", "formation": "", "snippet": ""}
    CORPUS.append(row)
    if i % 2 == 0:
        CORPUS.append({**row, "id": f"{i:024x}"})


def fake_search(query="", juridiction=None, date_min=None, date_max=None,
                limit=20, offset=0, formation=None, **k):
    limit = max(1, min(int(limit), 100))
    return {"total": len(CORPUS), "decisions": CORPUS[offset:offset + limit]}


dila.search = fake_search


def _page(offset):
    return asyncio.run(search_api.search_federated(
        "licenciement faute grave", juridiction="cass", limit=30,
        limit_per_source=30, offset=offset, sources_only=["dila"]))


def test_page_pleine_et_suite():
    r = _page(0)
    assert r["total_rendus"] == 30, f"{r['total_rendus']} rendus sur 30 demandés"
    assert r.get("has_more") is True, r.get("has_more")
    assert isinstance(r.get("next_offset"), int) and r["next_offset"] > 30, r.get("next_offset")


def test_parcours_complet_sans_perte_ni_doublon():
    vus, offset, pages = [], 0, 0
    while True:
        r = _page(offset)
        vus += [x["ecli"] for x in r["results"]]
        pages += 1
        assert pages < 20, "pagination sans fin"
        if not r.get("has_more"):
            break
        offset = r["next_offset"]
    assert len(vus) == len(set(vus)), "un arrêt rendu deux fois"
    assert len(set(vus)) == 200, f"{len(set(vus))} arrêts atteints sur 200"


def test_total_dit_ce_quil_compte():
    r = _page(0)
    assert "total_note" in r and "deux fois" in r["total_note"], r.get("total_note")


def _js_fn(src, name):
    m = re.search(r"function " + name + r"\(\) \{.*?\n\}", src, re.S)
    return m.group(0) if m else None


def test_front_charger_la_suite():
    html = open(os.path.join(_ROOT, "web", "search.html"), encoding="utf-8").read()
    fn = _js_fn(html, "aEncoreUneSuite")
    assert fn, "search.html : pas de fonction aEncoreUneSuite (bouton décidé sur la seule taille du lot)"
    assert "next_offset" in html and "has_more" in html, "search.html ignore next_offset / has_more"
    m = re.search(r"const canLoadMore = (.*?);", html)
    assert m and "aEncoreUneSuite()" in m.group(1), m and m.group(1)
    node = shutil.which("node")
    if not node:
        print("    (node absent : vérification statique seulement)")
        return
    prog = ("const PAGE_SIZE = 30; let lastSearchState;\n" + fn + "\n"
            "const out = [];\n"
            "lastSearchState = {lastChunkSize: 19, perSource: {dila: 19}, srcHasMore: {dila: true}}; out.push(aEncoreUneSuite());\n"
            "lastSearchState = {lastChunkSize: 30, perSource: {dila: 30}, srcHasMore: {dila: false}}; out.push(aEncoreUneSuite());\n"
            "lastSearchState = {lastChunkSize: 30, perSource: {admin: 30}}; out.push(aEncoreUneSuite());\n"
            "console.log(JSON.stringify(out));")
    res = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [True, False, True], res.stdout


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except Exception as e:
                fails += 1
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
    if fails:
        sys.exit(1)
    print("All dila pagination tests passed.")
