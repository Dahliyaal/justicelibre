"""Tests OFFLINE du parseur de références (citation_search.parse_citation).

Couvre en particulier la classe de requêtes découverte le 3 août 2026 —
« mode clochard » sur le fonds judiciaire — qui n'avait jamais été testée
(le banc de juillet ne contenait que des juridictions à numéros nationaux
uniques : CE/CAA/TA/Cass/CJUE/CEDH) :
  - "RG 26/00038 le tribunal judiciaire de Saint-Quentin"  (ordonnance
    réelle du 2 juil. 2026, TJ Saint-Quentin — cas Pièce n° 13) ;
  - "9 juillet 2026 bobigny tj"  (type abrégé en minuscules, ordre libre) ;
  - tcom, villes en minuscules, articles à ne pas prendre pour des villes.

Run :
    python3 -m pytest tests/test_citation_parse.py -v
ou :
    python3 tests/test_citation_parse.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from citation_search import parse_citation, is_reference, _fold  # noqa: E402


def _p(q):
    return parse_citation(q)


def test_rg_tj_ville_canonique():
    # Le cas fondateur du 3 août (requête telle que tapée dans la barre).
    p = _p("RG 26/00038 le tribunal judiciaire de Saint-Quentin")
    assert ("rg", "26/00038") in p["numeros"], p
    assert p["juri_type"] == "tj", p
    assert _fold(p["juri_ville"]) == "saint-quentin", p
    assert is_reference(p)


def test_phrase_complete_avec_date():
    p = _p("Par ordonnance de référé du 2 juillet 2026 (n° RG 26/00038), "
           "le tribunal judiciaire de Saint-Quentin a statué")
    assert ("rg", "26/00038") in p["numeros"], p
    assert p["juri_type"] == "tj", p
    assert _fold(p["juri_ville"]) == "saint-quentin", p
    assert p["date"] == "2026-07-02", p


def test_flemmard_ville_puis_tj():
    p = _p("9 juillet 2026 bobigny tj")
    assert p["juri_type"] == "tj", p
    assert _fold(p["juri_ville"]) == "bobigny", p
    assert p["date"] == "2026-07-09", p
    assert is_reference(p)  # juridiction + date suffisent


def test_flemmard_tj_puis_ville():
    p = _p("tj bobigny 9 juillet 2026")
    assert p["juri_type"] == "tj", p
    assert _fold(p["juri_ville"]) == "bobigny", p
    assert p["date"] == "2026-07-09", p


def test_ville_minuscules_forme_canonique():
    p = _p("tribunal judiciaire de saint-quentin RG 26/00038")
    assert p["juri_type"] == "tj", p
    assert _fold(p["juri_ville"]) == "saint-quentin", p


def test_tcom():
    p = _p("tcom bobigny 21 juillet 2026")
    assert p["juri_type"] == "tcom", p
    assert _fold(p["juri_ville"]) == "bobigny", p
    p2 = _p("tribunal de commerce de Bobigny, 21 juillet 2026")
    assert p2["juri_type"] == "tcom", p2
    assert _fold(p2["juri_ville"]) == "bobigny", p2


def test_rg_avec_tiret_devant_un_tribunal_du_fond():
    # "26-00038" a la forme d'un pourvoi Cass, mais avec un TJ c'est un RG.
    p = _p("26-00038 tj saint-quentin")
    assert ("rg", "26-00038") in p["numeros"], p
    assert p["juri_type"] == "tj", p
    # …et sans juridiction du fond, la lecture pourvoi reste inchangée.
    p2 = _p("cass 22-87.145")
    assert ("pourvoi", "22-87.145") in p2["numeros"], p2


def test_tribunal_des_conflits():
    # Numéro TC nu (cas réel : C3830 = TdC 2 avr. 2012, Proyart, publié).
    p = _p("C3830")
    assert ("tdc", "C3830") in p["numeros"], p
    assert is_reference(p)
    # Citation complète + casse libre.
    p2 = _p("Tribunal des conflits, 2 avril 2012, n° c3830")
    assert p2["juri_type"] == "tdc", p2
    assert any(k == "tdc" for k, _ in p2["numeros"]), p2
    assert p2["date"] == "2012-04-02", p2
    # Un CELEX C-312/11 ne doit PAS devenir un numéro TdC.
    p3 = _p("CJUE, C-312/11")
    assert not any(k == "tdc" for k, _ in p3["numeros"]), p3


def test_article_nest_pas_une_ville():
    # "le tribunal judiciaire de ladite commune" : le TYPE reste, la
    # pseudo-ville est écartée (VILLE_STOP).
    p = _p("le tribunal judiciaire de ladite commune, 2 juillet 2026")
    assert p["juri_type"] == "tj", p
    assert p["juri_ville"] == "", p


def test_annee_nest_pas_une_ville():
    # "2026 tj" : un nombre ne doit jamais être capturé comme ville.
    p = _p("référé 2026 tj")
    assert p["juri_type"] == "tj", p
    assert p["juri_ville"] == "", p


def test_tj_nu_sans_date_nest_pas_une_reference():
    # "tj" seul sans date ni numéro → pipeline normal, pas la route citation.
    p = _p("tj")
    assert not is_reference(p), p


def test_formes_canoniques_intactes():
    # Non-régression : les formes du banc de juillet parsent toujours pareil.
    p = _p("CAA Toulouse, 2e ch., 27 fév. 2024, n° 21TL04508")
    assert p["juri_type"] == "caa" and ("caa_ce", "21TL04508") in p["numeros"] \
        and p["date"] == "2024-02-27", p
    p = _p("cass 22-87.145")
    assert p["juri_type"] == "cass" and ("pourvoi", "22-87.145") in p["numeros"], p
    p = _p("Cour d'appel de Douai, 15 janv. 2025")
    assert p["juri_type"] == "ca" and _fold(p["juri_ville"]) == "douai" \
        and p["date"] == "2025-01-15", p


# ─── Runner sans pytest ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
    if failed:
        sys.exit(f"{failed} test(s) en échec.")
    print(f"\nAll {len(tests)} tests passed.")
