"""Test suite for SSR HTML output escaping (anti-XSS + JSON-LD valide).

ssr.py génère le HTML de ~3M pages publiques depuis des données parsées
(DILA/HUDOC/curia) — donc potentiellement hostiles. Ce test injecte des
charges hostiles dans render_decision / render_law (qui prennent un
`data: dict`, donc OFFLINE, sans base) et vérifie :
  1. aucune donnée hostile ne ressort exécutable (pas de <script> non
     JSON-LD contenant la charge, pas d'attribut on*/javascript:) ;
  2. le JSON-LD reste du JSON PARSABLE (sur-échappement html.escape
     cassait la structured data sur les 3M pages) ;
  3. `_jsonld_embed` empêche le breakout `</script>`.

Run :
    python3 -m pytest tests/test_ssr_escaping.py -v
ou :
    python3 tests/test_ssr_escaping.py
"""
import html.parser
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import ssr  # noqa: E402

_XSS = "<script>alert(1)</script>"
_ATTR = '"><img src=x onerror=alert(1)>'


class _Sniffer(html.parser.HTMLParser):
    """Repère les <script> exécutables (hors JSON-LD) et les attributs
    événementiels — ce qui rendrait une charge hostile exécutable."""

    def __init__(self):
        super().__init__()
        self.exec_scripts, self.event_attrs = [], []
        self._in, self._buf = False, ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "script" and d.get("type") != "application/ld+json":
            self._in, self._buf = True, ""
        for k, v in attrs:
            if k.startswith("on") or (v and v.strip().lower().startswith("javascript:")):
                self.event_attrs.append((tag, k, v))

    def handle_endtag(self, tag):
        if tag == "script" and self._in:
            self._in = False
            if self._buf.strip():
                self.exec_scripts.append(self._buf)

    def handle_data(self, data):
        if self._in:
            self._buf += data


def _assert_no_xss(htmlout: str, label: str):
    s = _Sniffer()
    s.feed(htmlout)
    exe = [x for x in s.exec_scripts if "alert(1)" in x]
    assert not exe, f"{label}: {len(exe)} <script> exécutable(s) injecté(s)"
    assert not s.event_attrs, f"{label}: attribut événementiel injecté : {s.event_attrs[:3]}"
    # Le JSON-LD doit rester parsable.
    for block in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', htmlout, re.S
    ):
        json.loads(block)  # lève si invalide


def test_render_decision_no_xss():
    data = {
        "numero": _ATTR, "titre": _XSS, "juridiction": _ATTR, "ecli": _XSS,
        "date": "2023-05-04", "solution": _ATTR, "text": "corps " + _XSS,
        "abstrats": "", "sommaire": "",
        "text_lang": 'en"><script>alert(1)</script>',
        "source_url": 'http://evil"><script>alert(1)</script>.com',
    }
    _assert_no_xss(ssr.render_decision("cedh", "001-249914", data), "render_decision")


def test_render_law_no_xss():
    data = {
        "num": _ATTR, "code": "CC", "texte": "loi " + _XSS, "etat": "VIGUEUR",
        "nota": _XSS, "date_debut": '2016-10-01"><script>alert(1)</script>',
        "source_url": 'http://x"><script>alert(1)</script>',
    }
    _assert_no_xss(ssr.render_law("CC", "1128", data), "render_law")


def test_jsonld_embed_valid_and_no_breakout():
    embedded = ssr._jsonld_embed(
        {"name": "</script><script>alert(1)</script>", "x": "a < b & c > d"}
    )
    assert "</script>" not in embedded, "breakout </script> possible dans le JSON-LD"
    # json.loads décode les \\uXXXX → doit reparser à l'identique.
    assert json.loads(embedded)["name"] == "</script><script>alert(1)</script>"


def test_jsonld_not_html_over_escaped():
    """Garde-fou anti-régression : le JSON-LD ne doit PAS contenir d'entités
    HTML (&quot; etc.) qui casseraient JSON.parse côté Google."""
    embedded = ssr._jsonld_embed({"name": 'Décision "X" & autres'})
    assert "&quot;" not in embedded and "&amp;" not in embedded, \
        "sur-échappement html.escape réintroduit (structured data cassée)"
    json.loads(embedded)


# ─── Runner sans pytest ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("render_decision sans XSS",        test_render_decision_no_xss),
        ("render_law sans XSS",             test_render_law_no_xss),
        ("_jsonld_embed valide + no breakout", test_jsonld_embed_valid_and_no_breakout),
        ("JSON-LD pas sur-échappé",         test_jsonld_not_html_over_escaped),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            print(f"  ✗ {name}\n      {e}")
            failed += 1
    if failed:
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
