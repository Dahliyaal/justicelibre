"""Doctrine : jamais présentée comme une décision, jamais sous son n° interne.

Audit du 2 oct. 2026, F1 : /decision/doctrine/ariane_crp:4294 affichait
« Décision rendue par Conseil d'État … Numéro 4294 » ; c'étaient les
conclusions du rapporteur public dans l'affaire n° 412996. Même faux dans
/api/decision (« numero »: "4294") et dans les outils MCP (doc_id seul).

Hors ligne : enregistrement brut de l'entrepôt reproduit ci-dessous (tel que
servi par la prod le 2/10/2026), réseau neutralisé.
"""
import asyncio
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import search_api  # noqa: E402
import ssr  # noqa: E402

# Ce que l'entrepôt renvoie pour ariane_crp:4294 (champs utiles).
RAW_CRP = {
    "id": "ariane_crp:4294", "source_id": "ariane_crp", "doc_id": "4294",
    "type": "Conclusion", "titre": "Conclusions 412996 (2019-12-24)",
    "date": "2019-12-24", "administration": "Conseil d'État",
    "source_url": "https://www.conseil-etat.fr/fr/arianeweb/CRP/conclusion/2019-12-24/412996",
    "tags": "4ème CHS,AFF:412996",
    "contenu": "N° 412996\nMme K…\nSéance du 13 décembre 2019\nCONCLUSIONS\nM. Raphaël Chambon, rapporteur public",
}
# Hit de recherche : pas de tags, titre non parlant -> repli sur l'URL.
RAW_CRP_HIT = {
    "id": "ariane_crp:1005", "source_id": "ariane_crp", "doc_id": "1005",
    "titre": "Cette affaire a été affectée à la 2ème sous-section",
    "date": "2015-06-19", "administration": "Conseil d'État",
    "source_url": "https://www.conseil-etat.fr/fr/arianeweb/CRP/conclusion/2015-06-19/386716",
}


def _norm_api(raw):
    """Chemin de /api/decision?source=doctrine (search_api.fetch_decision)."""
    async def fake(fond, did):
        return dict(raw)
    from sources import warehouse as wh
    old = wh.get_decision_remote
    wh.get_decision_remote = fake
    try:
        return asyncio.run(search_api.fetch_decision("doctrine", raw["id"]))
    finally:
        wh.get_decision_remote = old


def test_api_numero_affaire():
    d = _norm_api(RAW_CRP)
    assert d["numero"] == "412996", d["numero"]
    assert d.get("nature_document") == "Conclusions du rapporteur public", d.get("nature_document")


def test_hit_numero_depuis_url():
    d = search_api._norm_doctrine(RAW_CRP_HIT)
    assert d["numero"] == "386716", d["numero"]


def test_autres_fonds():
    assert search_api._norm_doctrine({"id": "cada:20143607", "source_id": "cada", "doc_id": "20143607",
                                       "type": "Avis"})["numero"] == "20143607"
    # ddd : doc_id = n° de notice du catalogue, pas une référence citable
    assert search_api._norm_doctrine({"id": "ddd:1037", "source_id": "ddd", "doc_id": "1037"})["numero"] == ""


def test_ssr_page():
    ssr._wh.sync_build_url = lambda *a, **k: None   # pas de réseau
    d = _norm_api(RAW_CRP)
    html = ssr.render_decision("doctrine", "ariane_crp:4294", d)
    assert "Décision rendue" not in html, "la doctrine est encore présentée comme une décision"
    assert not re.search(r"n°\s*4294\b", html), "le n° interne 4294 est encore affiché"
    assert ">4294<" not in html
    assert "Conclusions du rapporteur public" in html
    assert "412996" in html
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert "LegalCase" not in json.dumps(ld["@type"]), ld["@type"]
    assert "4294" not in ld["name"] and "4294" not in str(ld.get("identifier", "")), ld
    t = re.search(r"<title>(.*?)</title>", html).group(1)
    assert "4294" not in t and "412996" in t, t


def test_mcp_tools():
    import server
    out = server._doctrine_identite(dict(RAW_CRP))
    assert out["numero"] == "412996" and out["nature"].startswith("Conclusions"), out
    assert "avertissement" in out


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
    print("All doctrine tests passed.")
