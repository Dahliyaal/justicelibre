"""La traduction demande → écritures stockées ne doit ni perdre ni confondre.

Pourquoi ce fichier existe (8 septembre 2026) : 113 écritures pour 45
juridictions dans JADE, et « cc » / « Cour de cassation » côté judiciaire.
Un filtre écrit contre une seule forme ratait les autres en silence, et
`get_admin_decision("…", juridiction="TA69")` répondait « introuvable ».

Ces tests tournent sans réseau ni base : ils lisent data/juridictions_map.json.

Run :
    python3 tests/test_juridictions.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import juridictions as J  # noqa: E402


def test_carte_complete():
    """45 codes, 113 écritures, aucune écriture rangée deux fois."""
    carte = J.charger()["admin"]
    assert len(carte) == 45, len(carte)
    toutes = [e for v in carte.values() for e in v["ecritures"]]
    assert len(toutes) == 113, len(toutes)
    assert len(set(toutes)) == 113, "une écriture apparaît sous deux codes"


def test_code_direct():
    r = J.resoudre_admin("TA59")
    assert r and r["code"] == "TA59"
    assert "Tribunal administratif de Lille" in r["ecritures"]
    assert "Tribunal administratif Lille" in r["ecritures"]
    assert len(r["ecritures"]) == 3
    assert J.resoudre_admin("caa59")["code"] == "CAA59", "le code en minuscules doit passer"


def test_formes_courtes_et_longues():
    for forme in ("TA Lille", "TA de Lille", "tribunal administratif de lille",
                  "Tribunal Administratif de Lille"):
        assert J.resoudre_admin(forme)["code"] == "TA59", forme
    for forme in ("CAA Douai", "CAA de DOUAI", "Cour administrative d'appel de Douai",
                  "cour administrative d’appel de douai"):
        assert J.resoudre_admin(forme)["code"] == "CAA59", forme
    for forme in ("CE", "Conseil d'Etat", "Conseil d'État", "conseil d'etat"):
        assert J.resoudre_admin(forme)["code"] == "CE", forme
    assert J.resoudre_admin("Tribunal des Conflits")["code"] == "TC"


def test_ta_et_caa_de_la_meme_ville_ne_se_confondent_pas():
    """Le bug du 23 août 2026 : demander le TA de Lyon servait la CAA de Lyon."""
    assert J.resoudre_admin("TA de Lyon")["code"] == "TA69"
    assert J.resoudre_admin("CAA de Lyon")["code"] == "CAA69"
    assert set(J.resoudre_admin("TA de Lyon")["ecritures"]).isdisjoint(
        J.resoudre_admin("CAA de Lyon")["ecritures"])


def test_ville_nue_et_inconnu_restent_none():
    """Une valeur non reconnue → None : l'appelant garde son ancien comportement."""
    assert J.resoudre_admin("Lyon") is None
    assert J.resoudre_admin("") is None
    assert J.resoudre_admin(None) is None
    assert J.resoudre_admin("Cour de cassation") is None, "ordre judiciaire, pas admin"
    assert J.where_admin("n'importe quoi") is None


def test_cas_tranches_par_le_numero():
    """Les 5 écritures anormales, rangées là où le numéro de dossier les met."""
    assert "Cour administrative d'appel" in J.resoudre_admin("CAA33")["ecritures"]
    assert "CAA de VERSAILLESS" in J.resoudre_admin("CAA78")["ecritures"]
    assert "Cour administrative d'appel de Montpellier" in J.resoudre_admin("CAA13")["ecritures"]
    assert "Section du Contentieux" in J.resoudre_admin("CE")["ecritures"]
    assert "Tribunal administratif Montpellier ordonnance du president" in J.resoudre_admin("TA34")["ecritures"]
    assert J.resoudre_admin("CAA de Montpellier") is None, (
        "cette cour n'existe pas : ne pas l'inventer comme alias de Marseille")


def test_chalons_et_outre_mer():
    assert J.resoudre_admin("TA de Châlons-sur-Marne")["code"] == "TA51"
    assert J.resoudre_admin("TA de Châlons-en-Champagne")["code"] == "TA51"
    assert J.resoudre_admin("TA de La Réunion")["code"] == "TA101"
    assert J.resoudre_admin("Tribunal administratif de Saint-Denis de la Réunion")["code"] == "TA101"
    assert J.resoudre_admin("TA Papeete")["code"] == "TA103"


def test_where_admin_sql():
    sql, params = J.where_admin("TA69", col="m.juridiction")
    assert sql == "m.juridiction IN (?, ?)", sql
    assert sorted(params) == ["Tribunal administratif Lyon", "Tribunal administratif de Lyon"]


def test_where_judiciaire():
    sql, params = J.where_judiciaire("cassation", col="d.juridiction")
    assert params == ["cc", "Cour de cassation"], params
    assert "IN (?, ?)" in sql
    sql, params = J.where_judiciaire("tj", col="d.juridiction")
    assert params[0] == "Tribunal judiciaire "
    assert params[1] == "Tribunal judiciaire \uffff"
    assert "Tribunal de grande instance " in params, "les TGI sont des TJ d'avant 2020"
    assert J.where_judiciaire("inconnue") is None
    assert J.where_judiciaire("CASSATION") is not None, "la clé est insensible à la casse"


def test_intervalle_prefixe_couvre_bien():
    """Le test de l'intervalle, en pur Python : ce qu'il inclut et exclut."""
    _, p = J.where_judiciaire("appel")
    lo, hi = p[0], p[1]
    assert lo <= "Cour d'appel de Douai" < hi
    assert lo <= "Cour d'appel d'Aix-en-Provence" < hi
    assert not (lo <= "Cour de cassation" < hi)
    assert not (lo <= "Cour administrative d'appel de Douai" < hi)


def test_libelle_affiche():
    assert J.libelle_affiche("cc") == "Cour de cassation"
    assert J.libelle_affiche("Tribunal judiciaire de tj2b033") == "Tribunal judiciaire de Bastia"
    assert J.libelle_affiche("Cour d'appel de Douai") == "Cour d'appel de Douai"
    assert J.libelle_affiche(None) is None


def test_reconnaissance_judiciaire():
    assert J.ecritures_judiciaires_reconnues("cc")
    assert J.ecritures_judiciaires_reconnues("Tribunal judiciaire de Lille")
    assert J.ecritures_judiciaires_reconnues("Tribunal des activités économiques de Paris")
    assert not J.ecritures_judiciaires_reconnues("Conseil de prud'hommes de Calais"), (
        "les prud'hommes n'ont pas de famille de filtre : ils restent trouvables sans filtre")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(fns)} tests OK")
