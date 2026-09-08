"""ArianeWeb (en-tête) + CADA : tests hors ligne sur pièces réelles.

Pourquoi ce fichier existe (8 septembre 2026).

**ArianeWeb.** Sept métadonnées sont en clair dans les 200 premiers caractères
de chaque `text` et aucune n'était extraite (rapport M § 13). Les en-têtes de
`tests/fixtures/ariane_entetes.json` sont des en-têtes RÉELS tirés de la prod,
choisis pour couvrir les neuf cas qui font échouer une regex naïve :

  * le féminin en toutes lettres (« rapporteure », « présidente ») — c'est le
    piège n° 1 : `rapporteur\\b` ne matche PAS « rapporteure », et 20 lignes
    sur 1 527 étaient perdues en silence au premier essai ;
  * « …, rapporteur public », qui désigne une AUTRE personne que le rapporteur
    et ne doit jamais atterrir dans la colonne `rapporteur` ;
  * les décisions sans formation, sans président, sans ECLI (référés anciens) :
    l'absence doit rester une absence, jamais une valeur inventée ;
  * les trois mentions de publication, dont la coquille de la source
    « Mentionné AU tables du recueil Lebon » ;
  * les formations « 1 / 4 SSR », « 3ème - 8ème chambres réunies ».

**CADA.** Le script d'ingestion pointait sur un nom de fichier DATÉ,
aujourd'hui en 404. Un test interdit le retour d'une URL datée.

Aucun réseau, aucune base : `tests/fixtures/` suffit.

Run :
    python3 tests/test_enrich_ariane_cada.py
"""
import csv
import importlib.util
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_FIX = os.path.join(_HERE, "fixtures")
sys.path.insert(0, _ROOT)

from sources import ariane  # noqa: E402


def _charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(_ROOT, chemin))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cada = _charger("ingest_cada", "ingest_cada.py")

with open(os.path.join(_FIX, "ariane_entetes.json"), encoding="utf-8") as _f:
    ENTETES = {c["cas"]: c for c in json.load(_f)}


# ----------------------------------------------------------------- ArianeWeb

def test_le_script_ne_duplique_pas_le_parseur():
    """Garde-fou anti-divergence : c'était le bug du 23 août 2026 — deux
    extractions du même en-tête, dont une vide (cf. test_ariane_header.py)."""
    src = open(os.path.join(_ROOT, "scripts/extract_ariane_header.py"),
               encoding="utf-8").read()
    assert "from sources import ariane" in src
    assert "ariane.parse_header" in src
    assert "re.compile" not in src, \
        "le script réécrit ses propres regex au lieu d'utiliser sources.ariane"


def test_feminin_rapporteure():
    """« rapporteure » : un `rapporteur\\b` nu la manque, sans rien signaler."""
    h = ariane.parse_header(ENTETES["feminin"]["entete"])
    assert h.get("rapporteur"), h
    assert not h["rapporteur"].lower().startswith("m. florian"), \
        "le rapporteur public a été pris pour le rapporteur"


def test_feminin_presidente():
    h = ariane.parse_header(ENTETES["presidente"]["entete"])
    assert h.get("president"), h
    assert "," not in h["president"], h["president"]


def test_rapporteur_public_ne_pollue_pas_rapporteur():
    """Deux magistrats distincts : les confondre, c'est attribuer à l'un ce
    qu'a fait l'autre."""
    for cas in ENTETES.values():
        h = ariane.parse_header(cas["entete"])
        if "rapporteur" in h and "rapporteur_public" in h:
            assert h["rapporteur"] != h["rapporteur_public"], cas["ariane_id"]
        if "rapporteur" in h:
            assert "public" not in h["rapporteur"].lower(), cas


def test_absence_reste_une_absence():
    """Sans formation / sans président / sans ECLI dans la source, la clé doit
    manquer — jamais une valeur devinée."""
    assert "formation" not in ariane.parse_header(ENTETES["sans_formation"]["entete"])
    assert "president" not in ariane.parse_header(ENTETES["sans_president"]["entete"])
    assert "ecli" not in ariane.parse_header(ENTETES["sans_ecli"]["entete"])
    # …mais le numéro, lui, est toujours là.
    for cas in ("sans_formation", "sans_president", "sans_ecli"):
        assert ariane.parse_header(ENTETES[cas]["entete"]).get("numero"), cas


def test_les_trois_mentions_de_publication_et_la_coquille():
    assert ariane.parse_header(ENTETES["publie"]["entete"])["publication"] \
        == "Publié au recueil Lebon"
    mention = ariane.parse_header(ENTETES["mentionne"]["entete"])["publication"]
    assert mention.startswith("Mentionné au"), mention
    # La source écrit parfois « Mentionné AU tables » : la regex doit l'accepter.
    assert ariane.parse_header(
        "N° 1 \nMentionné au tables du recueil Lebon\n4ème chambre"
    )["publication"] == "Mentionné au tables du recueil Lebon"


def test_formations_exotiques():
    for cas in ("ssr", "chambres_reunies"):
        f = ariane.parse_header(ENTETES[cas]["entete"]).get("formation", "")
        assert f, cas
        assert len(f) <= 80, f


def test_le_corps_de_l_arret_n_est_pas_lu():
    """`entete` coupe à REPUBLIQUE FRANCAISE : au-delà, « rapporteur »
    réapparaît dans des phrases et donnerait des noms fantômes."""
    texte = ("Conseil d'État \nN° 123456 \nInédit au recueil Lebon\n"
             "3ème chambre \nM. Vrai Nom, rapporteur\n\n"
             "Lecture du lundi 3 mars 2025 REPUBLIQUE FRANCAISE\n"
             "AU NOM DU PEUPLE FRANCAIS\nVu la requête ; M. Faux Nom, rapporteur "
             "public, a conclu au rejet ;")
    zone = ariane.entete(texte)
    assert "REPUBLIQUE" not in zone and "Faux Nom" not in zone, zone
    h = ariane.parse_header(texte)
    assert h["rapporteur"] == "M. Vrai Nom", h
    assert "rapporteur_public" not in h, h


def test_juridiction_extraite():
    for cas in ENTETES.values():
        h = ariane.parse_header(cas["entete"])
        assert h.get("juridiction") == "Conseil d'État", cas["ariane_id"]


def test_date_depuis_ecli_ou_lecture():
    """Deux sources, dans cet ordre : l'ECLI porte la date en `.AAAAMMJJ` ;
    à défaut, « Lecture du … » en toutes lettres."""
    for cas in ENTETES.values():
        h = ariane.parse_header(cas["entete"])
        if "date" in h:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", h["date"]), h
            if "ecli" in h and "." in h["ecli"]:
                assert h["date"].replace("-", "") in h["ecli"], h


# ---------------------------------------------------------------------- CADA

def test_url_cada_n_est_plus_un_nom_de_fichier_date():
    """La cause de la panne : `…/20260409-143148/cada-2026-04-09.csv` en dur.
    Chaque republication change le chemin ; l'ancien renvoie 404."""
    src = open(os.path.join(_ROOT, "ingest_cada.py"), encoding="utf-8").read()
    for ligne in src.splitlines():
        if ligne.strip().startswith("#") or "cada-2026-04-09" in ligne:
            continue
        assert not re.search(r'"https://static\.data\.gouv\.fr/resources/[^"]*\.csv"',
                             ligne), ligne
    assert cada.API_DATASET.startswith("https://www.data.gouv.fr/api/1/datasets/")
    assert "%s" in cada.PERMALIEN and "/datasets/r/" in cada.PERMALIEN
    assert re.match(r"^[0-9a-f-]{36}$", cada.RESSOURCE_CONSOLIDEE)


def test_objet_et_partie_sont_lus():
    """Les deux champs jetés du rapport M § 14.a."""
    assert "partie" in cada.COLONNES_INSERT
    assert "objet" in cada.COLONNES_INSERT
    assert set(cada.COLONNES_NEUVES) == {"partie", "objet"}


def test_ligne_vers_doc_sur_le_csv_reel():
    with open(os.path.join(_FIX, "cada_extrait.csv"), encoding="utf-8", newline="") as f:
        lignes = list(csv.DictReader(f))
    assert lignes, "extrait CADA vide"
    docs = [cada.ligne_vers_doc(r) for r in lignes]
    assert all(d is not None for d in docs)
    par_nom = dict(zip(cada.COLONNES_INSERT, docs[0]))
    assert par_nom["source_id"] == "cada"
    assert par_nom["doc_id"] == "19840002", par_nom["doc_id"]
    assert par_nom["partie"] == "III", par_nom["partie"]
    assert par_nom["source_url"] == "https://www.cada.fr/avis/19840002"
    assert par_nom["contenu"].startswith("La commission d'accès")
    # `Objet` est vide dans TOUT le CSV (60 941/60 941, vérifié le 8/09/2026) :
    # le titre reste donc fabriqué.
    assert par_nom["objet"] == ""
    assert par_nom["titre"].startswith("Avis CADA — ministre de la défense"), par_nom["titre"]


def test_objet_devient_le_titre_le_jour_ou_la_cada_le_remplit():
    ligne = {"Numéro de dossier": "20260001", "Administration": "préfecture",
             "Type": "Conseil", "Séance": "01/09/2026",
             "Objet": "Communication du registre des délibérations",
             "Thème et sous thème": "Collectivités/Communes", "Mots clés": "registre",
             "Sens et motivation": "Favorable", "Partie": "II", "Avis": "…"}
    doc = dict(zip(cada.COLONNES_INSERT, cada.ligne_vers_doc(ligne)))
    assert doc["titre"] == "Communication du registre des délibérations"
    assert doc["objet"] == "Communication du registre des délibérations"
    assert doc["partie"] == "II"


def test_ligne_sans_numero_de_dossier_est_ignoree():
    assert cada.ligne_vers_doc({"Numéro de dossier": "  "}) is None


if __name__ == "__main__":
    tests = [(nom, fn) for nom, fn in sorted(globals().items())
             if nom.startswith("test_") and callable(fn)]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
        except AssertionError as exc:
            print(f"  ✗ {nom}\n      {exc}")
            echecs += 1
    if echecs:
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
