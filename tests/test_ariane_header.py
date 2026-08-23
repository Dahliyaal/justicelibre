"""En-tête ArianeWeb : le n° de requête et la date doivent être extraits.

Pourquoi ce fichier existe (23 août 2026) : le plugin Sinequa du Conseil
d'État ne renvoie QUE du texte brut — ni numéro, ni date, ni ECLI en
champ. Le MCP parsait cet en-tête ; le site, lui, écrivait
`numero=""`, `date=""`, `ecli=""` EN DUR dans `search_api.fetch_decision`.
Conséquence : les ~114 000 pages `/decision/ariane/` sortaient toutes avec
le même titre, « Conseil d'État, Décision du Conseil d'État », sans date
ni numéro — alors que le texte juste en dessous affichait « N° 454852 …
Lecture du mardi 27 juillet 2021 ». Personne ne pouvait le voir : la page
se rendait parfaitement.

Les deux chemins partagent désormais `sources.ariane.parse_header`.

Run :
    python3 tests/test_ariane_header.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from sources import ariane  # noqa: E402


def test_ecli_moderne():
    """Cas courant : l'ECLI porte la date, en plus du numéro."""
    got = ariane.parse_header(
        "Conseil d'État   N° 454852  ECLI:FR:CEORD:2021:454852.20210727  "
        "Inédit au recueil Lebon  Lecture du mardi 27 juillet 2021")
    assert got["numero"] == "454852", got
    assert got["date"] == "2021-07-27", got
    assert got["ecli"] == "ECLI:FR:CEORD:2021:454852.20210727", got


def test_arret_ancien_sans_ecli():
    """Avant l'ECLI, seule la mention « Lecture du … » donne la date.

    Le parseur d'origine (MCP) ne lisait QUE l'ECLI : toutes les décisions
    antérieures à sa généralisation restaient sans date."""
    got = ariane.parse_header(
        "Conseil d'État  N° 61958  Publié au recueil Lebon  "
        "Lecture du vendredi 3 février 1989")
    assert got["numero"] == "61958", got
    assert got["date"] == "1989-02-03", got
    assert "ecli" not in got, got


def test_premier_du_mois_et_mois_accentues():
    """« 1er décembre », « août » : les pièges classiques des dates FR."""
    assert ariane.parse_header(
        "N° 12345  Lecture du lundi 1er décembre 1975")["date"] == "1975-12-01"
    assert ariane.parse_header(
        "N° 99999  Lecture du jeudi 12 août 2021")["date"] == "2021-08-12"


def test_rien_a_extraire_ne_ment_pas():
    """Sans en-tête exploitable, on renvoie vide — jamais une date inventée."""
    assert ariane.parse_header("texte sans en-tête") == {}
    assert ariane.parse_header("") == {}


def test_le_mcp_partage_le_meme_parseur():
    """Garde-fou anti-divergence : c'était précisément la cause du bug —
    deux extractions du même en-tête, une par chemin, dont une vide."""
    src = open(os.path.join(os.path.dirname(_HERE), "search_api.py")).read()
    assert "ariane.parse_header" in src, \
        "search_api.fetch_decision n'utilise plus le parseur commun"
    assert '"numero": "",\n                    "ecli": "",' not in src, \
        "les champs ArianeWeb sont de nouveau écrits vides en dur"


if __name__ == "__main__":
    tests = [
        ("ECLI moderne",                    test_ecli_moderne),
        ("arrêt ancien sans ECLI",          test_arret_ancien_sans_ecli),
        ("1er du mois + mois accentués",    test_premier_du_mois_et_mois_accentues),
        ("rien à extraire → vide",          test_rien_a_extraire_ne_ment_pas),
        ("MCP et site : même parseur",      test_le_mcp_partage_le_meme_parseur),
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
