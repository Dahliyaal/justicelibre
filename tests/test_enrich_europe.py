"""Enrichissements CJUE + CEDH : tests hors ligne sur réponses enregistrées.

Pourquoi ce fichier existe (8 septembre 2026). Deux scripts d'enrichissement
tapent des sources européennes (SPARQL EUR-Lex, HUDOC). Trois choses peuvent
casser en silence, sans qu'aucune exception ne soit levée :

  1. **Le littéral SPARQL.** L'endpoint Virtuoso d'EUR-Lex stocke le CELEX en
     `"…"^^xsd:string` et distingue ce terme du littéral simple. Écrire
     `VALUES ?celex { "62019CJ0030" }` renvoie **zéro ligne, HTTP 200**. Un
     script qui perd le `^^xsd:string` n'enrichit plus rien et le dit
     « 0 sans_reponse ».
  2. **Le champ HUDOC.** `scrape_cedh.py` demande `originatingbody_name`, que
     HUDOC renvoie toujours vide ; le champ rempli est `originatingbody`. Un
     `select` amputé ne lève rien non plus.
  3. **L'ECLI.** C'est tout l'objet de la réparation : deux documents
     distincts (l'arrêt 62019CJ0030 et les conclusions 62019CC0030) portaient
     le MÊME ECLI fabriqué. Un test doit interdire le retour de ce doublon.

Les réponses sont enregistrées dans `tests/fixtures/` : aucun réseau ici.

Run :
    python3 tests/test_enrich_europe.py
"""
import importlib.util
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_FIX = os.path.join(_HERE, "fixtures")
sys.path.insert(0, _ROOT)


def _charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(_ROOT, chemin))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cjue = _charger("enrich_cjue_sparql", "scripts/enrich_cjue_sparql.py")
cedh = _charger("enrich_cedh_meta", "scripts/enrich_cedh_meta.py")


class ClientRejoue:
    """Rejoue les deux réponses SPARQL enregistrées, dans l'ordre d'appel."""

    def __init__(self, fichiers):
        self.fichiers = list(fichiers)
        self.requetes_vues = []
        self.requetes = 0
        self.secondes = 0.0

    def interroger(self, requete):
        self.requetes_vues.append(requete)
        self.requetes += 1
        with open(os.path.join(_FIX, self.fichiers.pop(0)), encoding="utf-8") as f:
            return json.load(f)["results"]["bindings"]


# --------------------------------------------------------------------- CJUE

def test_values_exige_xsd_string():
    """Sans `^^xsd:string`, EUR-Lex renvoie 0 ligne en HTTP 200 (silence total)."""
    v = cjue.values(["62019CJ0030", "62019CC0030"])
    assert v == '"62019CJ0030"^^xsd:string "62019CC0030"^^xsd:string', v
    for requete in (cjue.Q_META, cjue.Q_LIENS):
        assert "VALUES ?celex { %(values)s }" in requete


def test_pas_de_variable_en_position_de_predicat():
    """`VALUES ?rel { cdm:… }` renvoie zéro sur Virtuoso : il faut des UNION."""
    assert "VALUES ?rel" not in cjue.Q_LIENS
    assert cjue.Q_LIENS.count("UNION") == 2


def test_ecli_reel_et_distinct_pour_arret_et_conclusions():
    """Le cœur de la réparation : deux documents, deux ECLI.

    En base, les deux portaient `ECLI:EU:C:2019:30` — fabriqué depuis le CELEX.
    """
    cli = ClientRejoue(["cjue_sparql_meta.json", "cjue_sparql_liens.json"])
    meta = cjue.interroger_lot(cli, ["62019CJ0030", "62019CC0030", "62016CJ0414"])
    assert meta["62019CJ0030"]["ecli"] == "ECLI:EU:C:2021:269", meta["62019CJ0030"]["ecli"]
    assert meta["62019CC0030"]["ecli"] == "ECLI:EU:C:2020:374", meta["62019CC0030"]["ecli"]
    assert meta["62019CJ0030"]["ecli"] != meta["62019CC0030"]["ecli"], \
        "l'arrêt et ses conclusions ne peuvent pas partager un ECLI"
    faux = "ECLI:EU:C:2019:30"
    assert faux not in (meta["62019CJ0030"]["ecli"], meta["62019CC0030"]["ecli"])


def test_les_seize_champs_jetes_reviennent():
    cli = ClientRejoue(["cjue_sparql_meta.json", "cjue_sparql_liens.json"])
    m = cjue.interroger_lot(cli, ["62019CJ0030", "62019CC0030", "62016CJ0414"])["62019CJ0030"]
    assert m["avocat_general"] == ["Saugmandsgaard Øe"], m["avocat_general"]
    assert m["juges"] == ["von Danwitz"], m["juges"]
    assert m["formation"] == ["CHAMB_GD_C"], m["formation"]
    assert m["procjur"] == ["REFER_PREL"], m["procjur"]
    assert m["type_procedure"] == ["PREJ"], m["type_procedure"]
    assert m["pays"] == ["SWE"], m["pays"]
    assert m["langue_procedure"] == ["SWE"], m["langue_procedure"]
    assert m["erecueil"] == "1", m["erecueil"]
    assert "PRIN" in m["matieres"], m["matieres"]
    assert m["date_sparql"] == "2021-04-15", m["date_sparql"]
    assert m["type_sparql"] == "JUDG", m["type_sparql"]


def test_titre_francais_recupere_par_sparql():
    """Le titre était vide 3 000 fois sur 3 000 : la regex `<title>` HTML ne
    rend plus rien. Le graphe, lui, porte le titre officiel français."""
    cli = ClientRejoue(["cjue_sparql_meta.json", "cjue_sparql_liens.json"])
    m = cjue.interroger_lot(cli, ["62019CJ0030", "62019CC0030", "62016CJ0414"])
    titre = m["62019CJ0030"]["title"]
    assert titre.startswith("Arrêt de la Cour (grande chambre) du 15 avril 2021"), titre
    assert "#" not in titre, "les séparateurs EUR-Lex doivent être normalisés"
    assert m["62019CC0030"]["title"].startswith("Conclusions de l'avocat général")


def test_graphe_de_citations_resolu_en_celex():
    cli = ClientRejoue(["cjue_sparql_meta.json", "cjue_sparql_liens.json"])
    m = cjue.interroger_lot(cli, ["62019CJ0030", "62019CC0030", "62016CJ0414"])
    cites = m["62019CJ0030"]["cite"]
    assert len(cites) >= 13, cites
    assert "32000L0043" in cites, "une directive citée doit apparaître"
    assert m["62019CJ0030"]["conclusions"] == ["62019CC0030"], \
        "le lien arrêt → conclusions doit être établi"
    assert m["62019CJ0030"]["interprete"], "les dispositions interprétées sont jetées"
    assert all(re.match(r"^[0-9A-Z()]+$", c) for c in cites), cites


def test_agregation_sur_les_deux_works_du_meme_celex():
    """Un CELEX porte souvent deux works Cellar (dont un `do_not_index`).
    Le GROUP BY doit rendre UNE ligne par CELEX, pas deux."""
    cli = ClientRejoue(["cjue_sparql_meta.json", "cjue_sparql_liens.json"])
    m = cjue.interroger_lot(cli, ["62019CJ0030", "62019CC0030", "62016CJ0414"])
    assert len(m) == 3, m.keys()
    assert "GROUP BY ?celex" in cjue.Q_META


def test_code_et_liste():
    assert cjue.code("http://…/authority/formjug/CHAMB_GD_C") == "CHAMB_GD_C"
    assert cjue.code("") == ""
    assert cjue.liste("http://a/X|http://b/Y") == ["X", "Y"]
    assert cjue.liste("") == []


# --------------------------------------------------------------------- CEDH

def test_select_hudoc_contient_les_champs_jetes():
    champs = set(cedh.SELECT.split(","))
    for attendu in ("appno", "extractedappno", "kpthesaurus", "scl", "violation",
                    "nonviolation", "separateopinion", "typedescription",
                    "judgementdate", "decisiondate", "introductiondate",
                    "representedby", "applicability", "rulesofcourt",
                    "externalsources", "publishedby", "languageisocode",
                    "doctypebranch", "documentcollectionid"):
        assert attendu in champs, f"{attendu} manque au select élargi"


def test_originatingbody_est_demande_en_plus_du_name():
    """`originatingbody_name` est toujours vide côté HUDOC ; c'est
    `originatingbody` qui porte l'information (mesuré sur 1 200 documents)."""
    champs = set(cedh.SELECT.split(","))
    assert "originatingbody" in champs
    assert "originatingbody_name" in champs
    src = open(os.path.join(_ROOT, "scripts/enrich_cedh_meta.py"), encoding="utf-8").read()
    assert 'col.get("originatingbody")' in src


def test_aucun_appel_a_l_endpoint_de_conversion():
    """La panne du 29/08/2026 venait de `/app/conversion` : ce script ne doit
    JAMAIS l'appeler — il n'a pas besoin des textes."""
    import ast
    chemin = os.path.join(_ROOT, "scripts/enrich_cedh_meta.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())
    # On regarde les chaînes du CODE, pas la documentation : le docstring du
    # module explique justement pourquoi cet endpoint est banni.
    corps = arbre.body[1:] if (arbre.body and isinstance(arbre.body[0], ast.Expr)
                               and isinstance(arbre.body[0].value, ast.Constant)
                               and isinstance(arbre.body[0].value.value, str)) else arbre.body
    litteraux = [n.value for stmt in corps for n in ast.walk(stmt)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    appels = [s for s in litteraux if "app/conversion" in s]
    assert not appels, appels


def test_normalise_appno_gere_les_affaires_jointes():
    """La colonne `appno_norm` sert la recherche par numéro : si elle ne
    contient que le premier numéro, les affaires jointes sont introuvables."""
    got = cedh.normalise_appno("68273/14;68271/14")
    assert "68273/14" in got and "68271/14" in got, got
    assert "68273-14" in got and "6827314" in got, got
    assert cedh.normalise_appno("") == ""
    assert cedh.normalise_appno("sans slash") == ""
    # Idempotent sur un numéro simple, et pas de doublon.
    simple = cedh.normalise_appno("4143/02")
    assert simple.split() == ["4143/02", "4143-02", "414302"], simple


def test_lecture_de_la_reponse_hudoc_enregistree():
    with open(os.path.join(_FIX, "hudoc_results.json"), encoding="utf-8") as f:
        data = json.load(f)
    par_id = {r["columns"]["itemid"]: r["columns"] for r in data["results"]}
    jointe = par_id["001-159730"]
    assert jointe["appno"] == "37194/08;37260/08", jointe["appno"]
    # C'est exactement le cas que la regex tronque : elle ne garde que le 1er.
    assert jointe["appno"].split(";")[0] == "37194/08"
    assert jointe["scl"], "la jurisprudence citée (scl) est un champ jeté"
    assert par_id["001-236130"]["kpthesaurus"], "les mots-clés sont un champ jeté"
    assert (par_id["001-236130"].get("originatingbody_name") or "") == "", \
        "si HUDOC se met à remplir originatingbody_name, revoir le script"
    assert par_id["001-236130"]["originatingbody"], "le code de formation est rempli"


def test_champs_meta_couvrent_le_rapport_M():
    """Le rapport M § 11 liste 18 champs jetés : aucun ne doit être oublié."""
    for attendu in ("extractedappno", "kpthesaurus", "doctypebranch",
                    "documentcollectionid", "languageisocode", "violation",
                    "nonviolation", "scl", "separateopinion", "typedescription",
                    "judgementdate", "decisiondate", "introductiondate",
                    "representedby", "applicability", "rulesofcourt",
                    "externalsources", "publishedby"):
        assert attendu in cedh.CHAMPS_META, attendu


# ------------------------------------------------------- garde-fous d'écriture

def test_dry_run_par_defaut_et_sauvegarde_avant_ecrasement():
    for chemin in ("scripts/enrich_cjue_sparql.py", "scripts/enrich_cedh_meta.py",
                   "scripts/extract_ariane_header.py", "ingest_cada.py"):
        src = open(os.path.join(_ROOT, chemin), encoding="utf-8").read()
        assert '"--apply", action="store_true"' in src, f"{chemin} : --apply absent"
        assert "DRY-RUN : aucune écriture" in src, f"{chemin} : pas de dry-run"
        assert "gzip.open" in src, f"{chemin} : pas de sauvegarde CSV.gz"
        assert "ADD COLUMN" in src, f"{chemin} : pas d'ALTER TABLE ADD COLUMN"


def test_colonnes_avant_sur_toute_colonne_ecrasee():
    """Règle du projet : jamais d'UPDATE d'une colonne existante sans copie."""
    src = open(os.path.join(_ROOT, "scripts/enrich_cjue_sparql.py"), encoding="utf-8").read()
    assert "ecli_avant = COALESCE(ecli_avant, ?)" in src
    assert "title_avant = COALESCE(title_avant, ?)" in src
    src = open(os.path.join(_ROOT, "scripts/enrich_cedh_meta.py"), encoding="utf-8").read()
    assert "appno_avant = COALESCE(appno_avant, ?)" in src
    assert "appno_norm_avant = COALESCE(appno_norm_avant, ?)" in src


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
