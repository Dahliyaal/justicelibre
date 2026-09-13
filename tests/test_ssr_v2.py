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
    python3 -m pytest tests/test_ssr_v2.py -v
ou :
    python3 tests/test_ssr_v2.py
"""
import html.parser
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import ssr_v2 as ssr  # noqa: E402

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


def test_render_law_uses_titre_texte():
    """Garde-fou : la page /loi/ doit afficher le NOM du code, pas le sigle.

    Régression réelle (23 août 2026) : le correctif `titre_section` (qui
    mentait et vaut désormais None) a laissé ssr.render_law lire l'ancien
    champ, et toutes les pages /loi/ sont passées à « Article R4126-37 -
    CSP » — dans le <title>, l'og:title, le JSON-LD et le fil d'Ariane.
    Aucun test ne l'a vu : la page se rendait parfaitement, elle était
    seulement moins bonne. C'est la même famille que titre_section
    lui-même — un défaut qui ne plante pas."""
    html_out = ssr.render_law("CSP", "R4126-37", {
        "num": "R4126-37", "code": "CSP",
        "titre_texte": "Code de la santé publique", "titre_section": None,
        "texte": "Le président de la chambre disciplinaire…",
        "etat": "VIGUEUR", "date_debut": "2007-08-03",
    })
    assert "Code de la santé publique" in html_out, \
        "render_law n'affiche plus le titre du texte (titre_texte ignoré ?)"
    assert "<title>Article R4126-37 -CSP -" not in html_out, \
        "render_law est retombé sur le sigle au lieu du nom du code"


def test_render_decision_title_carries_identifier():
    """La balise <title> doit porter un identifiant reconnaissable.

    Régression réelle (23 août 2026) : les 76 k pages CEDH s'intitulaient
    « Cour EDH, <date> » — la CEDH n'a pas de `numero` en base et le
    <title> ne retombait pas sur l'intitulé. Le H1, l'og:title et le
    JSON-LD, eux, portaient bien « AFFAIRE X c. Y » : le défaut était
    invisible à l'œil, visible seulement de Google."""
    cedh = ssr.render_decision("cedh", "001-249844", {
        "title": "AFFAIRE AZIMOVY c. RUSSIE", "juridiction": "Cour EDH",
        "date": "2026-04-30", "numero": "", "full_text": "THIRD SECTION…"})
    seo = re.search(r"<title>(.*?)</title>", cedh).group(1)
    assert "AZIMOVY" in seo, f"<title> sans identifiant : {seo!r}"

    # …sans casser les fonds qui ont un numéro (le titre reste le n°).
    dila = ssr.render_decision("dila", "6a7d", {
        "titre": "Cour de cassation, ch. crim.", "juridiction": "Cour de cassation",
        "date": "2026-08-12", "numero": "26-83.237", "full_text": "arrêt"})
    seo = re.search(r"<title>(.*?)</title>", dila).group(1)
    assert "26-83.237" in seo and "ch. crim" not in seo, \
        f"le n° doit primer sur l'intitulé quand il existe : {seo!r}"


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

def test_render_decision_affiche_les_champs_servis_depuis_le_13_sept():
    """Les champs en base et jusqu'ici jetés par fetch_decision doivent
    apparaître, et un texte réduit au sommaire doit être annoncé.

    Inventaire des champs du 13 septembre 2026 : « le code de lecture ne lit
    pas la donnée, il relit un résumé ». ssr.render_decision réservait les
    lignes Solution / Nature depuis des mois sans jamais recevoir les clés."""
    dila = ssr.render_decision("dila", "X1", {
        "title": "t", "juridiction": "Cour de cassation", "date": "2026-09-10",
        "numero": "23-20.368", "full_text": "sommaire bref", "sommaire": "sommaire bref",
        "solution": "Cassation partielle", "nature": "ARRET", "president": "Mme Martinel",
        "avocats": "SCP Lyon-Caen", "texte_integral": False,
        "note_texte": "Le texte servi est le sommaire officiel."})
    for attendu in ("Solution", "Cassation partielle", "Nature", "Président",
                    "Mme Martinel", "Avocats", "Texte intégral : non",
                    "sommaire officiel"):
        assert attendu in dila, f"{attendu!r} absent de la page dila"
    cedh = ssr.render_decision("cedh", "001-1", {
        "title": "AFFAIRE X c. Y", "juridiction": "Cour EDH", "date": "2014-04-17",
        "numero": "9154/10", "full_text": "x" * 300, "conclusion": "Violation de l'article 6",
        "importance": "1", "respondent": "DEU"})
    for attendu in ("Conclusion", "Violation de l", "État défendeur", "DEU", "arrêt de principe"):
        assert attendu in cedh, f"{attendu!r} absent de la page CEDH"
    # Un texte complet ne doit PAS porter l'avertissement.
    complet = ssr.render_decision("dila", "X2", {
        "title": "t", "juridiction": "Cour de cassation", "date": "2026-09-10",
        "numero": "1", "full_text": "arrêt entier", "texte_integral": True})
    assert "Texte intégral : non" not in complet


import ssr as ssr_v1  # noqa: E402

_CAS = [
    ("dila", "6aa272fd195da062e0fa6eaf",
     {"juridiction": "Cour de cassation", "date": "2026-09-10",
      "numero": "23-20.368", "ecli": "ECLI:FR:CCASS:2026:C200818",
      "full_text": "Faits et procédure\n\n1. Vu l'article 2241 du code civil.",
      "sommaire": "Si, en principe…"}),
    ("cedh", "001-212971",
     {"title": "AFFAIRE D.I. c. BULGARIE", "juridiction": "Cour EDH",
      "date": "2021-12-14", "numero": "32006/20", "full_text": "QUATRIÈME SECTION"}),
    ("ariane", "/Ariane_Web/AW_DCE/|96191",
     {"title": "Conseil d'État, n° 320227", "juridiction": "Conseil d'État",
      "date": "2009-01-21", "numero": "320227", "full_text": "Vu la requête…"}),
]


def _tag(h, pat):
    m = re.search(pat, h, re.S)
    return m.group(1) if m else None


def test_head_seo_identique_a_ssr_v1():
    """La bascule v2 ne doit RIEN changer au référencement.

    canonical, <title> et la description sont calculés par les fonctions de
    ssr.py elles-mêmes : on le vérifie chaîne à chaîne, y compris sur l'id
    ArianeWeb qui contient un slash et un pipe (ssr._canonical, ssr.py:790)."""
    for source, did, data in _CAS:
        a = ssr_v1.render_decision(source, did, data)
        b = ssr.render_decision(source, did, data)
        for champ, pat in (
            ("canonical", r'<link rel="canonical" href="([^"]*)"'),
            ("title", r"<title>(.*?)</title>"),
            ("description", r'<meta name="description" content="([^"]*)"'),
            ("og:url", r'<meta property="og:url" content="([^"]*)"'),
            ("og:title", r'<meta property="og:title" content="([^"]*)"'),
        ):
            assert _tag(a, pat) == _tag(b, pat), \
                f"{source}/{did} : {champ} diverge\n  v1={_tag(a, pat)!r}\n  v2={_tag(b, pat)!r}"
        ja = json.loads(_tag(a, r'<script type="application/ld\+json">(.*?)</script>'))
        jb = json.loads(_tag(b, r'<script type="application/ld\+json">(.*?)</script>'))
        assert ja == jb, f"{source}/{did} : JSON-LD diverge"


def test_head_seo_loi_identique_a_ssr_v1():
    data = {"num": "748-6", "code": "CPC", "titre_texte": "Code de procédure civile",
            "texte": "Les dispositifs…", "etat": "VIGUEUR_DIFF",
            "date_debut": "2025-09-01", "date_fin": "2999-01-01",
            "legiarti": "LEGIARTI000051869308"}
    a, b = ssr_v1.render_law("CPC", "748-6", data), ssr.render_law("CPC", "748-6", data)
    for pat in (r'<link rel="canonical" href="([^"]*)"', r"<title>(.*?)</title>",
                r'<meta name="description" content="([^"]*)"'):
        assert _tag(a, pat) == _tag(b, pat), f"diverge : {_tag(a, pat)!r} / {_tag(b, pat)!r}"
    assert json.loads(_tag(a, r'<script type="application/ld\+json">(.*?)</script>')) == \
           json.loads(_tag(b, r'<script type="application/ld\+json">(.*?)</script>'))


def test_pas_de_style_en_ligne_ni_de_css_embarque():
    """Règle du normaliseur : aucun style en ligne, aucun <style> embarqué."""
    for source, did, data in _CAS:
        h = ssr.render_decision(source, did, data)
        assert 'style="' not in h, f"{source} : style en ligne dans la page décision"
        assert "<style" not in h, f"{source} : <style> embarqué"
    h = ssr.render_law("CT", "L321-1", {
        "num": "L321-1", "titre_texte": "Code du travail", "texte": "x",
        "etat": "ABROGE", "date_debut": "2005-01-19", "date_fin": "2008-05-01"})
    assert 'style="' not in h and "<style" not in h


def test_trois_scripts_seulement():
    """JSON-LD + résolveur de thème + bloc de données. Le reste en src=."""
    h = ssr.render_decision(*_CAS[0][:2], _CAS[0][2])
    inlines = re.findall(r"<script(?![^>]*\ssrc=)[^>]*>", h)
    assert len(inlines) == 3, f"{len(inlines)} <script> en ligne : {inlines}"
    assert h.count('src="/jl.js?v=') == 1 and h.count('src="/topbar.js?v=') == 1
    assert 'href="/styles/jl.css?v=' in h


def test_abroge_annonce_en_rouge_avant_le_texte():
    """Un abrogé s'annonce comme tel AVANT son texte (ssr.py:1012)."""
    h = ssr.render_law("CT", "L321-1", {
        "num": "L321-1", "titre_texte": "Code du travail",
        "texte": "Constitue un licenciement pour motif économique…",
        "etat": "ABROGE", "date_debut": "2005-01-19", "date_fin": "2008-05-01"})
    assert "Article abrogé" in h and "ne s'applique plus" in h
    corps = h[h.index("<body"):]
    assert corps.index("jl-statut--abroge") < corps.index('class="jl-alin"'), \
        "l'avertissement d'abrogation passe après le texte"
    assert '"legislationLegalForce": "NotInForce"' in h
    # Un VIGUEUR_DIFF reste en vigueur aujourd'hui.
    v = ssr.render_law("CPC", "748-6", {
        "num": "748-6", "titre_texte": "Code de procédure civile", "texte": "x",
        "etat": "VIGUEUR_DIFF", "date_debut": "2025-09-01", "date_fin": "2999-01-01"})
    assert "Article abrogé" not in v and "Article en vigueur" in v


def test_jamais_other_ni_liste_vide():
    """« other » de Judilibre et la chaîne littérale « [] » ne sont pas des
    informations (inventaire des champs du 13 sept., §1.2)."""
    h = ssr.render_decision("dila", "X", {
        "juridiction": "Cour de cassation", "date": "2026-09-10", "numero": "1",
        "full_text": "texte", "nature": "other", "type_rec": "other",
        "abstrats": "[]", "renvois": "[]"})
    assert ">other<" not in h and "other</" not in h
    assert "Type de recours" not in h and ">[]<" not in h
    # …mais une liste JSON réelle devient des pastilles de matière.
    h2 = ssr.render_decision("dila", "X", {
        "juridiction": "Cour de cassation", "date": "2026-09-10", "numero": "1",
        "full_text": "texte", "sommaire": "s", "abstrats": '["prescription civile"]'})
    assert "prescription civile" in h2


def test_provenance_sur_chaque_derivation():
    """Textes visés, chronologie et « cité par » disent d'où ils viennent."""
    h = ssr.render_decision("dila", "X", {
        "juridiction": "Cour de cassation", "date": "2026-09-10",
        "numero": "23-20.368",
        "full_text": "1. La cour a violé l'article 2241 du code civil le "
                     "26 juin 2023.\n\n2. PAR CES MOTIFS"})
    assert "repéré dans le texte" in h, "provenance des textes visés absente"
    assert "recherche lexicale" in h, "« cité par » non étiqueté"
    assert 'href="/loi/CC/2241?date=2026-09-10"' in h, "lien daté vers l'article absent"
    assert "26 juin 2023" in h and 'class="jl-chrono"' in h
    # Le visa LEGI structuré prime quand il existe.
    h2 = ssr.render_decision("dila", "X", {
        "juridiction": "Cour de cassation", "date": "2026-09-10", "numero": "1",
        "full_text": "texte", "liens_textes": "[typelien=CITATION] Article L. 1152-1"})
    assert "visa LEGI" in h2
    assert h2.index("visa LEGI") < (h2.index("repéré dans le texte")
                                    if "repéré dans le texte" in h2 else len(h2))


def test_entete_du_greffe_replie_et_paragraphes_ancres():
    h = ssr.render_decision("dila", "X", {
        "juridiction": "Cour de cassation", "date": "2026-09-10", "numero": "1",
        "full_text": "CIV. 2\n\nCOUR DE CASSATION\n\nAU NOM DU PEUPLE FRANÇAIS\n\n"
                     "Faits et procédure\n\n1. Premier paragraphe.\n\n"
                     "2. Second paragraphe."})
    assert 'class="jl-fold jl-entete-fold"' in h and "AU NOM DU PEUPLE" in h
    assert 'id="p1"' in h and 'id="p2"' in h and 'href="#p1"' in h
    assert 'id="s-faits-et-procedure"' in h, "le titre du texte n'est pas ancré"
    assert 'class="jl-toc"' in h
    # Le titre affiché est CELUI DU TEXTE, mot pour mot.
    assert ">Faits et procédure</h2>" in h


if __name__ == "__main__":
    tests = [
        ("render_decision sans XSS",        test_render_decision_no_xss),
        ("render_law sans XSS",             test_render_law_no_xss),
        ("render_law affiche le nom du code", test_render_law_uses_titre_texte),
        ("<title> porte un identifiant",     test_render_decision_title_carries_identifier),
        ("_jsonld_embed valide + no breakout", test_jsonld_embed_valid_and_no_breakout),
        ("JSON-LD pas sur-échappé",         test_jsonld_not_html_over_escaped),
        ("champs servis depuis le 13/09 + avertissement sommaire", test_render_decision_affiche_les_champs_servis_depuis_le_13_sept),
        ("head SEO identique à ssr.py (décision)", test_head_seo_identique_a_ssr_v1),
        ("head SEO identique à ssr.py (loi)",      test_head_seo_loi_identique_a_ssr_v1),
        ("aucun style en ligne, aucun <style>",    test_pas_de_style_en_ligne_ni_de_css_embarque),
        ("trois <script> en ligne seulement",      test_trois_scripts_seulement),
        ("abrogé annoncé en rouge avant le texte", test_abroge_annonce_en_rouge_avant_le_texte),
        ("jamais « other » ni « [] »",             test_jamais_other_ni_liste_vide),
        ("provenance sur chaque dérivation",       test_provenance_sur_chaque_derivation),
        ("en-tête replié + paragraphes ancrés",    test_entete_du_greffe_replie_et_paragraphes_ancres),
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
