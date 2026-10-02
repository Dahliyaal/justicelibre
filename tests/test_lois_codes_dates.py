"""Tests hors ligne des correctifs « lois » du 2 oct. 2026 (audit F3, F4, F7, F10).

F3  : route /loi/ décodée avant la regex (espace, « * », sigles accentués),
      chemins dangereux refusés, URL /loi/ encodées dans le sitemap et la
      canonique, échappement HTML de la page.
F4  : /api/law et /api/law/batch refusent une date hors calendrier (400).
F7  : get_law_versions accepte LEGITEXT/JORFTEXT ; code inconnu = 400 « Code
      inconnu » côté REST ; les 29 sigles historiques de l'entrepôt sont
      acceptés par le MCP ; liste des sigles = CODE_TO_LEGITEXT de l'entrepôt.
F10 : la note « à la date demandée » de l'entrepôt est réécrite quand aucune
      date n'a été demandée.

Aucun réseau : l'entrepôt est remplacé par des doublures.

    python3 tests/test_lois_codes_dates.py
"""
import ast
import asyncio
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import token_server  # noqa: E402
import ssr  # noqa: E402
from sources import legi, warehouse as wh  # noqa: E402


# ─── F3 : route /loi/ ─────────────────────────────────────────────────

def test_loi_path_decode_espace_asterisque_accents():
    p = token_server._parse_loi_path
    assert p("/loi/LPF/L80%20B") == ("LPF", "L80 B")
    assert p("/loi/CGI/4%20B") == ("CGI", "4 B")
    assert p("/loi/CGI/1496%20ter") == ("CGI", "1496 ter")
    assert p("/loi/CSP/R*1435-28-2") == ("CSP", "R*1435-28-2")
    assert p("/loi/CSP/R%2A1435-28-2") == ("CSP", "R*1435-28-2")
    assert p("/loi/CFor%C3%AAt/L111-1") == ("CForêt", "L111-1")
    assert p("/loi/C.%C3%A9duc/L131-1") == ("C.éduc", "L131-1")
    assert p("/loi/CP%C3%A9nit/L1") == ("CPénit", "L1")
    assert p("/loi/CForêt-ancien/L1") == ("CForêt-ancien", "L1")


def test_loi_path_anciennes_url_inchangees():
    p = token_server._parse_loi_path
    assert p("/loi/CC/1128") == ("CC", "1128")
    assert p("/loi/LPF/L80B") == ("LPF", "L80B")
    assert p("/loi/CJA/R772-8") == ("CJA", "R772-8")
    assert p("/loi/C.com/L441-10") == ("C.com", "L441-10")
    assert p("/loi/LEGITEXT000025244092/L111-1") == ("LEGITEXT000025244092", "L111-1")
    assert p("/loi/78-17/1") == ("78-17", "1")
    assert p("/loi/CP1810/1") == ("CP1810", "1")


def test_loi_path_refuse_les_chemins_dangereux():
    p = token_server._parse_loi_path
    refuses = [
        "/loi/CC/..",                     # traversée
        "/loi/CC/%2E%2E",
        "/loi/../etc/passwd",
        "/loi/CC/a%2Fb",                  # « / » encodé dans le numéro
        "/loi/CC/..%2F..%2Fetc",
        "/loi/CC/1%3Cscript%3E",          # < >
        "/loi/CC/<script>",
        "/loi/CC/1%22onmouseover",        # guillemet double
        "/loi/CC/1%27x",                  # guillemet simple
        "/loi/CC/1%00",                   # NUL
        "/loi/CC/1%0Ax",                  # saut de ligne
        "/loi/CC/1%252F2",                # double encodage : « % » résiduel
        "/loi/CC/%20",                    # numéro vide
        "/loi/CC/%20123",                 # commence par une espace
        "/loi/CC/%FF",                    # UTF-8 invalide
        "/loi/CC/" + "1" * 41,            # trop long
        "/loi/" + "C" * 21 + "/1",
        "/loi/CC%20X/1",                  # espace dans le code
        "/loi/CC/1/2",
    ]
    for chemin in refuses:
        assert p(chemin) is None, chemin


def test_render_law_echappe_et_encode_la_canonique():
    data = {"texte": "<b>texte</b>", "etat": "VIGUEUR", "date_debut": "2020-01-01",
            "date_fin": "2999-01-01", "legiarti": "LEGIARTI000000000001",
            "titre_texte": "Code <x>"}
    page = ssr.render_law("CForêt", "L80 B", data)
    assert "<b>texte</b>" not in page and "&lt;b&gt;" in page
    assert "Code <x>" not in page
    assert "/loi/CFor%C3%AAt/L80%20B" in page
    assert "/loi/CForêt/L80 B" not in page
    page404 = ssr.render_law_404("CC", '"><script>')
    assert "<script>" not in page404


def test_sitemap_legi_encode_les_url_loi():
    rows = [
        {"legitext": "LEGITEXT000006069583", "num": "L80 B", "date": "2026-01-01"},
        {"legitext": "LEGITEXT000025244092", "num": "L111-1", "date": "2026-01-01"},
        {"legitext": "LEGITEXT000006072665", "num": "R*1435-28-2", "date": "2026-01-01"},
        {"legitext": "LEGITEXT000006070721", "num": "1128", "date": "2026-01-01"},
    ]
    orig = ssr._wh.sync_enumerate_fond
    ssr._wh.sync_enumerate_fond = lambda *a, **k: rows
    try:
        xml = ssr.render_sitemap_legi(1)
    finally:
        ssr._wh.sync_enumerate_fond = orig
    assert "/loi/LPF/L80%20B<" in xml, xml
    assert "/loi/CFor%C3%AAt/L111-1<" in xml, xml
    assert "/loi/CSP/R%2A1435-28-2<" in xml, xml
    assert "/loi/CC/1128<" in xml, xml
    assert " B<" not in xml and "ê" not in xml
    # Toute URL publiée doit être relue par la route à l'identique.
    for loc in xml.split("<loc>")[1:]:
        url = loc.split("</loc>")[0]
        chemin = url[len(ssr.BASE_URL):]
        assert token_server._parse_loi_path(chemin), chemin


# ─── Doublure de handler REST ─────────────────────────────────────────

class _FauxHandler(token_server.TokenHandler):
    def __init__(self, body: bytes = b""):  # pas de socket
        self.reponses = []
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)

    def _json_response(self, code, payload, cache_seconds=0):
        self.reponses.append((code, payload))


def _rest(methode, qs=None, body=None):
    h = _FauxHandler(json.dumps(body).encode() if body is not None else b"")
    if qs is not None:
        getattr(h, methode)({k: [v] for k, v in qs.items()})
    else:
        getattr(h, methode)()
    return h.reponses[-1]


class _EntrepotInterdit:
    """Toute sortie vers l'entrepôt fait échouer le test."""
    def __enter__(self):
        self.sauve = {n: getattr(wh, n) for n in
                      ("sync_get_law", "sync_get_law_versions", "sync_get_laws_batch")}
        def boom(*a, **k):
            raise AssertionError("l'entrepôt ne devait pas être appelé")
        for n in self.sauve:
            setattr(wh, n, boom)
        return self

    def __exit__(self, *exc):
        for n, f in self.sauve.items():
            setattr(wh, n, f)


# ─── F4 : dates hors calendrier au REST ───────────────────────────────

def test_api_law_date_hors_calendrier_400():
    with _EntrepotInterdit():
        for d in ("2016-13-45", "2016-02-30", "2025-00-10", "15/06/1992"):
            code, payload = _rest("_handle_law", {"code": "CC", "num": "1128", "date": d})
            assert code == 400, (d, code, payload)
            assert "calendrier" in payload["error"], payload


def test_api_law_batch_date_hors_calendrier_400():
    with _EntrepotInterdit():
        code, payload = _rest("_handle_law_batch", body={
            "refs": [{"code": "CC", "num": "1128"}], "date": "2016-13-45"})
    assert code == 400 and "calendrier" in payload["error"], payload


def test_api_law_date_valide_passe():
    vu = {}
    orig = wh.sync_get_law
    wh.sync_get_law = lambda c, n, d=None: vu.setdefault("args", (c, n, d)) and {"num": n}
    try:
        code, _ = _rest("_handle_law", {"code": "CC", "num": "1128", "date": "2016-02-29"})
    finally:
        wh.sync_get_law = orig
    assert code == 200 and vu["args"] == ("CC", "1128", "2016-02-29")


# ─── F7 : codes ───────────────────────────────────────────────────────

def test_api_law_code_inconnu_400():
    with _EntrepotInterdit():
        for c in ("ZZZ", "cc"):
            code, payload = _rest("_handle_law", {"code": c, "num": "1"})
            assert code == 400, payload
            assert "Code inconnu" in payload["error"], payload
            assert "Article introuvable" not in payload["error"]


def test_api_law_versions_code_inconnu_400():
    with _EntrepotInterdit():
        code, payload = _rest("_handle_law_versions", {"code": "ZZZ", "num": "1"})
    assert code == 400 and "Code inconnu" in payload["error"], payload


def test_api_law_versions_code_connu_passe():
    orig = wh.sync_get_law_versions
    wh.sync_get_law_versions = lambda c, n: [{"legiarti": "X"}]
    try:
        for c in ("CP1810", "CForêt", "JORFTEXT000000886460"):
            code, payload = _rest("_handle_law_versions", {"code": c, "num": "1"})
            assert code == 200 and payload["versions"], (c, payload)
    finally:
        wh.sync_get_law_versions = orig


def _codes_entrepot():
    src = open(os.path.join(_ROOT, "warehouse", "warehouse_server.py"), encoding="utf-8").read()
    for n in ast.parse(src).body:
        cible = (n.targets[0] if isinstance(n, ast.Assign) else
                 n.target if isinstance(n, ast.AnnAssign) else None)
        if getattr(cible, "id", None) == "CODE_TO_LEGITEXT":
            return ast.literal_eval(n.value)
    raise AssertionError("CODE_TO_LEGITEXT introuvable dans warehouse_server.py")


def test_sigles_identiques_a_l_entrepot():
    entrepot = _codes_entrepot()
    assert legi.SUPPORTED_CODES_LEGITEXT == entrepot, (
        set(entrepot) ^ set(legi.SUPPORTED_CODES_LEGITEXT))
    assert set(legi.SUPPORTED_CODES) == set(entrepot)
    for s in ("CP1810", "CPC1807", "CTACAA", "CNat", "CForêt-ancien"):
        assert legi.is_supported(s), s


def test_mcp_get_law_versions_accepte_identifiant_direct():
    import server
    vu = []

    async def faux_versions(code, num):
        vu.append((code, num))
        return [{"legiarti": "LEGIARTI000000000001"}]

    async def faux_fraicheur(fond):
        return None

    o1, o2 = wh.get_law_versions, wh.get_freshness
    wh.get_law_versions, wh.get_freshness = faux_versions, faux_fraicheur
    try:
        r = asyncio.run(server.get_law_versions("JORFTEXT000000886460", "1"))
        assert "error" not in r and r["count"] == 1 and r["code_long"] is None, r
        r = asyncio.run(server.get_law_versions("CP1810", "1"))
        assert "error" not in r and r["code_long"], r
        r = asyncio.run(server.get_law_versions("ZZZ", "1"))
        assert "Code inconnu" in str(r.get("error", "")), r
    finally:
        wh.get_law_versions, wh.get_freshness = o1, o2
    assert vu == [("JORFTEXT000000886460", "1"), ("CP1810", "1")]


def test_mcp_get_law_article_sigle_historique():
    import server

    async def faux_law(code, num, date=None):
        return {"code": code, "num": num, "texte": "t"}

    async def faux_fraicheur(fond):
        return None

    o1, o2 = wh.get_law, wh.get_freshness
    wh.get_law, wh.get_freshness = faux_law, faux_fraicheur
    try:
        r = asyncio.run(server.get_law_article("CP1810", "1"))
        assert "error" not in r, r
        r = asyncio.run(server.get_law_article("CC", "1128", "2016-13-45"))
        assert "error" in r or r.get("isError") or "calendrier" in json.dumps(r, ensure_ascii=False), r
    finally:
        wh.get_law, wh.get_freshness = o1, o2


# ─── F10 : note « à la date demandée » sans date ──────────────────────

def test_note_sans_date_reecrite():
    n = wh._NOTE_ENTREPOT_SANS_VERSION
    d = wh._corriger_note_sans_date({"note": n}, None)
    assert d["note"] == wh._NOTE_SANS_DATE and "demandée" not in d["note"]
    # Avec une date demandée, la note de l'entrepôt est juste : intacte.
    assert wh._corriger_note_sans_date({"note": n}, "2010-01-01")["note"] == n
    # Toute autre note passe telle quelle.
    autre = "Aucune version en vigueur à 2026-10-02. Version courante affichée."
    assert wh._corriger_note_sans_date({"note": autre}, None)["note"] == autre
    assert wh._corriger_note_sans_date(None, None) is None
    items = wh._corriger_notes_batch([{"note": n}, {"found": False}], None)
    assert items[0]["note"] == wh._NOTE_SANS_DATE


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for nom, f in tests:
        f()
        print(f"  ✓ {nom}")
    print(f"\nAll {len(tests)} tests passed.")
