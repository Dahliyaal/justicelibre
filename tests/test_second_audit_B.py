"""Tests hors ligne des correctifs « B » du second audit du 2 oct. 2026.

F5 : route /decision/ et sitemap CJUE (parenthèses des CELEX) : chaque <loc>
     publié est relu par la route et rend l'identifiant d'origine ; la
     canonique et le sitemap écrivent la même URL.
F3 : get_admin_decision sans juridiction : un numéro de CAA est cherché dans
     SA cour (26VE02318 → CAA78), et une panne du live n'est plus « introuvable ».
F4 : search_all (sources, sort), search_admin (sort), search_annuaire
     (category, source) refusent une valeur inconnue en listant les valeurs
     admises ; les appels valides passent.
P2 : search_cc met le filtre de juridiction DANS le MATCH FTS (sinon une
     lecture de ligne par décision contenant le mot : 13-15 min en prod).

Aucun réseau, aucune base de prod : doublures et bases temporaires.

    python3 tests/test_second_audit_B.py
"""
import asyncio
import os
import re
import sqlite3
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import server  # noqa: E402
import ssr  # noqa: E402
import token_server  # noqa: E402
from sources import dila, jade_remote, juriadmin, warehouse as wh  # noqa: E402


# ─── F5 : sitemap CJUE ↔ route ───────────────────────────────────────

CJUE_IDS = ["61959CC0033(01)", "62018CJ0311", "62019CO0123(02)", "61983CJ0294"]


def _route(path):
    p = getattr(token_server, "_parse_decision_path", None)
    if p is not None:
        return p(path)
    # Avant le correctif : la regex était en ligne dans do_GET.
    m = re.match(r"^/decision/([a-z]+)/([A-Za-z0-9_\-:.%|]{4,160})$", path)
    from urllib.parse import unquote
    return (m.group(1), unquote(m.group(2))) if m else None


def test_route_accepte_parentheses_brutes_et_encodees():
    assert _route("/decision/cjue/61959CC0033(01)") == ("cjue", "61959CC0033(01)")
    assert _route("/decision/cjue/61959CC0033%2801%29") == ("cjue", "61959CC0033(01)")
    # Anciennes formes inchangées
    assert _route("/decision/ariane/%2FAriane_Web%2FAW_DCE%2F%7C114750") == \
        ("ariane", "/Ariane_Web/AW_DCE/|114750")
    assert _route("/decision/admin/DTA_2409211_20260929") == ("admin", "DTA_2409211_20260929")
    assert _route("/decision/cedh/001-82735") == ("cedh", "001-82735")
    # Toujours refusés
    assert _route("/decision/cjue/a b c d") is None
    assert _route("/decision/cjue/<script>") is None
    assert _route("/decision/CJUE/61959CC0033") is None


def test_sitemap_cjue_chaque_loc_relue_par_la_route():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    c = sqlite3.connect(tmp.name)
    c.execute("CREATE TABLE cjue_decisions (celex TEXT, date TEXT)")
    c.executemany("INSERT INTO cjue_decisions VALUES (?, ?)",
                  [(i, "2020-01-0%d" % (n + 1)) for n, i in enumerate(CJUE_IDS)])
    c.commit()
    c.close()
    old = ssr.DILA_DB
    ssr.DILA_DB = tmp.name
    try:
        xml = ssr.render_sitemap_cjue(1)
    finally:
        ssr.DILA_DB = old
        os.unlink(tmp.name)
    import html
    locs = [html.unescape(x) for x in re.findall(r"<loc>([^<]+)</loc>", xml)]
    assert len(locs) == len(CJUE_IDS), xml
    relus = set()
    for loc in locs:
        assert "(" not in loc and ")" not in loc, f"parenthèse brute dans le sitemap : {loc}"
        path = loc.replace(ssr.BASE_URL, "")
        r = _route(path)
        assert r is not None, f"<loc> refusé par la route : {loc}"
        assert r[0] == "cjue"
        relus.add(r[1])
        assert loc == ssr._canonical("cjue", r[1]), f"sitemap ≠ canonique : {loc}"
    assert relus == set(CJUE_IDS)


# ─── F3 : get_admin_decision sans juridiction ────────────────────────

def _stub_live(monkey_calls, hits_par_juri=None, raise_exc=None):
    async def fake_lookup(fond, num, juridiction=None):
        return []

    async def fake_search(client, query, juridiction="CE", limit=10, **kw):
        monkey_calls.append(juridiction)
        if raise_exc:
            raise raise_exc
        return {"decisions": (hits_par_juri or {}).get(juridiction, [])}
    return fake_lookup, fake_search


def _with_stubs(fake_lookup, fake_search, coro_factory):
    o1, o2 = wh.lookup_by_numero, juriadmin.search
    wh.lookup_by_numero, juriadmin.search = fake_lookup, fake_search
    try:
        return asyncio.run(coro_factory())
    finally:
        wh.lookup_by_numero, juriadmin.search = o1, o2


def test_get_admin_decision_caa_sans_juridiction():
    calls = []
    hit = {"id": "DCA_26VE02318_20260930", "numero_dossier": "26VE02318",
           "juridiction": "Cour administrative d'appel de Versailles"}
    fl, fs = _stub_live(calls, {"CAA78": [hit]})
    res = _with_stubs(fl, fs, lambda: server.get_admin_decision("26VE02318"))
    assert res.get("id") == "DCA_26VE02318_20260930", (res, calls)
    assert calls == ["CAA78"], calls
    calls.clear()
    hit2 = {"id": "ORCA_25DA02275_20260930", "numero_dossier": "25DA02275"}
    fl, fs = _stub_live(calls, {"CAA59": [hit2]})
    res = _with_stubs(fl, fs, lambda: server.get_admin_decision("25DA02275"))
    assert res.get("id") == "ORCA_25DA02275_20260930", (res, calls)


def test_get_admin_decision_ce_sans_juridiction_inchange():
    calls = []
    fl, fs = _stub_live(calls, {})
    res = _with_stubs(fl, fs, lambda: server.get_admin_decision("497566"))
    assert calls == ["CE-CAA"], calls
    assert res.get("error_category") == "not_found"


def test_get_admin_decision_juridiction_explicite_inchangee():
    calls = []
    fl, fs = _stub_live(calls, {})
    _with_stubs(fl, fs, lambda: server.get_admin_decision("2409211", "TA75"))
    assert calls == ["TA75"], calls


def test_get_admin_decision_panne_live_pas_introuvable():
    calls = []
    fl, fs = _stub_live(calls, raise_exc=RuntimeError("timeout"))
    res = _with_stubs(fl, fs, lambda: server.get_admin_decision("26VE02318"))
    assert res.get("error_category") == "upstream", res
    assert res.get("retryable") is True


# ─── F4 : filtres inconnus ───────────────────────────────────────────

def test_search_all_source_inconnue_refusee():
    res = asyncio.run(server.search_all(query="harcèlement", sources=["nimportequoi"]))
    assert res.get("error_category") == "validation", res
    assert "jade" in res.get("error", "")
    res = asyncio.run(server.search_all(query="harcèlement", sources=["jade", "nimportequoi"]))
    assert res.get("error_category") == "validation", res
    assert "nimportequoi" in res["error"]


def test_search_all_sort_inconnu_refuse():
    res = asyncio.run(server.search_all(query="harcèlement", sort="pertinence_bizarre"))
    assert res.get("error_category") == "validation", res


def test_search_all_source_valide_passe():
    async def fake_jade(**kw):
        return {"total": 1, "decisions": [{"id": "DCE_1_20200101", "titre": "t",
                                           "date": "2020-01-01", "juridiction": "CE"}]}
    old = jade_remote.search
    jade_remote.search = fake_jade
    try:
        res = asyncio.run(server.search_all(query="harcèlement", sources=["jade"],
                                            expand_synonyms=False))
    finally:
        jade_remote.search = old
    assert "error" not in res, res
    assert res["per_source_counts"].get("jade") == 1, res


def test_search_admin_sort_inconnu_refuse_et_valides_passent():
    res = asyncio.run(server.search_admin(query="permis de construire", sort="pertinence_bizarre"))
    assert res.get("error_category") == "validation", res
    assert "date_desc" in res["error"]

    async def fake_jade(**kw):
        return {"total": 0, "returned": 0, "decisions": []}

    async def fake_od(*a, **kw):
        return {"results": [], "total": 0}
    o1, o2 = jade_remote.search, wh.search_fond
    jade_remote.search, wh.search_fond = fake_jade, fake_od
    try:
        for s in ("relevance", "date_desc", "date_asc"):
            res = asyncio.run(server.search_admin(query="permis", sort=s))
            assert "error" not in res, (s, res)
    finally:
        jade_remote.search, wh.search_fond = o1, o2


ANNUAIRE = [
    {"mail": "greffe.ta-lille@juradm.fr", "organisme": "Tribunal administratif - Lille",
     "service": "", "categorie": "Tribunal administratif", "categorie_slug": "ta",
     "source": "dila"},
    {"mail": "prada@culture.gouv.fr", "organisme": "Ministère de la culture",
     "service": "", "categorie": "PRADA", "categorie_slug": "prada", "source": "prada"},
]


def _annuaire(**kw):
    old = server._annuaire_rows
    server._annuaire_rows = ANNUAIRE
    try:
        return asyncio.run(server.search_annuaire(**kw))
    finally:
        server._annuaire_rows = old


def test_search_annuaire_filtres_inconnus_refuses():
    res = _annuaire(query="greffe", category="categorie_bidon")
    assert res.get("error_category") == "validation", res
    assert "prada" in res["error"] and "ta" in res.get("valeurs_admises", [])
    res = _annuaire(query="greffe", source="sourcebidon")
    assert res.get("error_category") == "validation", res


def test_search_annuaire_filtres_valides_passent():
    assert _annuaire(query="greffe", category="ta")["total"] == 1
    assert _annuaire(query="greffe", category="Tribunal")["total"] == 1  # sous-chaîne du libellé
    assert _annuaire(query="prada", source="prada")["total"] == 1
    assert _annuaire(query="greffe")["total"] == 1
    # Catégorie connue mais sans résultat pour la requête : 0, pas une erreur
    assert _annuaire(query="greffe", category="prada")["total"] == 0


# ─── P2 : search_cc, filtre de juridiction dans le MATCH ─────────────

def _db_cc():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    c = sqlite3.connect(tmp.name)
    c.executescript("""
        CREATE TABLE decisions (id TEXT, titre TEXT, date TEXT, juridiction TEXT,
            solution TEXT, numero TEXT, formation TEXT, ecli TEXT, nature TEXT,
            text TEXT, numero_rg_norm TEXT);
        CREATE VIRTUAL TABLE decisions_fts USING fts5(id UNINDEXED, titre,
            juridiction, solution, numero, formation, text, numero_rg_norm,
            content='decisions', content_rowid='rowid');
    """)
    rows = [
        ("CC1", "Décision 2026-1 QPC", "2026-03-01", "Conseil constitutionnel", "QPC", "loi conforme"),
        ("CC2", "Décision 2025-9 DC", "2025-06-01", "Conseil constitutionnel", "DC", "loi"),
        ("CA1", "Arrêt", "2026-04-01", "Cour d'appel de Paris", None, "loi conseil constitutionnel"),
        ("CC3", "Décision 2026-2 QPC", "2026-05-01", "Conseil constitutionnel", "QPC", "autre sujet"),
    ]
    for i, (id_, t, d, j, nat, txt) in enumerate(rows, 1):
        c.execute("INSERT INTO decisions(rowid,id,titre,date,juridiction,nature,text) "
                  "VALUES (?,?,?,?,?,?,?)", (i, id_, t, d, j, nat, txt))
        c.execute("INSERT INTO decisions_fts(rowid,id,titre,juridiction,text) VALUES (?,?,?,?,?)",
                  (i, id_, t, j, txt))
    c.commit()
    c.close()
    return tmp.name


def test_search_cc_filtre_juridiction_dans_le_match():
    path = _db_cc()
    vus = []
    orig = dila._get_conn

    class Proxy:
        def __init__(self, c):
            self._c = c

        def execute(self, sql, params=()):
            if "MATCH" in sql:
                vus.append(list(params))
            return self._c.execute(sql, params)

        def close(self):
            self._c.close()

    def fake_conn():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        return Proxy(c)
    dila._get_conn = fake_conn
    try:
        res = dila.search_cc("loi", date_min="2026-01-01")
    finally:
        dila._get_conn = orig
        os.unlink(path)
    assert [d["id"] for d in res["decisions"]] == ["CC1"], res
    assert res["total"] == 1
    assert vus, "aucune requête MATCH"
    for p in vus:
        assert 'juridiction:"conseil constitutionnel"' in p[0], \
            f"filtre de juridiction absent du MATCH FTS : {p[0]!r}"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {name} : {type(e).__name__}: {e}")
    if failed:
        print(f"\n{failed}/{len(tests)} tests FAILED.")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
