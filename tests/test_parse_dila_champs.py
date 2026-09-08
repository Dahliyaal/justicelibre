"""Les cinq pannes du parseur DILA, verrouillées par des tests OFFLINE.

Pourquoi ce fichier existe (8 septembre 2026). L'inventaire des champs a montré
que `parse_dila_bulk.py` ne lisait pas les balises que la source publie
réellement :

1. KALI cherchait META_TEXTE_KALI / META_CONVENTION_COLLECTIVE — **0 occurrence
   dans un tarball entier**. Le garde-fou `if meta_k is None: continue` faisait
   donc sauter 100 % des fichiers : le fonds n'ingérait plus rien depuis le
   29/08/2026, et ses 305 839 lignes n'avaient ni titre, ni IDCC, ni date.
2. `legi_articles.legitext` recevait `CONTEXTE/TEXTE@cid`, qui vaut un
   **JORFTEXT**, alors que `legi_textes.legitext` est un **LEGITEXT** : la
   jointure article ↔ texte trouvait 0 correspondance sur 8 000 articles.
3. Le corps des textes JORF est dans les fichiers `article/JORF/ARTI/…`, que le
   parseur ignorait : 99,9 % du stock et 58 % du flux récent sans corps.
4. Les colonnes sémantiques (SCT, ANA, CITATION_JP, TYPE_REC…) n'étaient
   remplies que par `enrich_dila.py`, sur le seul tarball global de 07/2025 ;
   et `AVOCAT_GENERAL` était interrogé à la place de `AVOCAT_GL`, balise qui
   n'existe dans aucun format DILA.
5. CNIL : `date` cherchée par un `.//` global au lieu de META_CNIL/DATE_TEXTE.

Les fragments XML ci-dessous sont des extraits RÉELS, réduits, des deltas
KALI/LEGI/JORF/CNIL/CASS du 7-8 septembre 2026 et du stock CONSTIT.

Run :
    python3 tests/test_parse_dila_champs.py
"""
import contextlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile

import lxml.etree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parse_dila_bulk import (  # noqa: E402
    JURIS_ENRICH_COLS,
    juris_enrich,
    legi_contexte,
    liens_json,
    parse_jorf_like,
    parse_kali,
    upsert_sql,
    xml_text,
)

# ── Fragments réels ───────────────────────────────────────────────────

LEGI_ARTI = """<ARTICLE>
<META><META_COMMUN><ID>LEGIARTI000006321037</ID><NATURE>Article</NATURE></META_COMMUN>
<META_SPEC><META_ARTICLE><NUM>17</NUM><ETAT>VIGUEUR</ETAT>
<DATE_DEBUT>2005-01-01</DATE_DEBUT><TYPE>AUTONOME</TYPE></META_ARTICLE></META_SPEC></META>
<CONTEXTE><TEXTE cid="JORFTEXT000000394028" nature="LOI_ORGANIQUE">
<TITRE_TXT c_titre_court="LOI organique n° 2001-692 du 1er août 2001"
           id_txt="JORFTEXT000000394028">LOI organique</TITRE_TXT>
<TITRE_TXT c_titre_court="Loi organique n° 2001-692 du 1 août 2001"
           id_txt="LEGITEXT000005631294">Loi organique relative aux lois de finances</TITRE_TXT>
<TM><TITRE_TM debut="2002-01-01" fin="2999-01-01" id="LEGISCTA000006084628">TITRE II : DES RESSOURCES</TITRE_TM>
<TM><TITRE_TM debut="2005-01-01" fin="2999-01-01" id="LEGISCTA000006114781">Chapitre III : Des affectations de recettes.</TITRE_TM></TM>
</TM></TEXTE></CONTEXTE>
<LIENS><LIEN cidtexte="JORFTEXT000000739021" naturetexte="DECRET" numtexte="98-15"
             sens="cible" typelien="CITATION">Décret n°98-15 du 7 janvier 1998 - art. 1 (V)</LIEN></LIENS>
</ARTICLE>"""

# Texte non consolidé : pas de TITRE_TXT en LEGITEXT → on retombe sur le cid.
LEGI_ARTI_SANS_LEGITEXT = """<ARTICLE><META><META_COMMUN><ID>LEGIARTI000000000001</ID></META_COMMUN></META>
<CONTEXTE><TEXTE cid="JORFTEXT000000000002">
<TITRE_TXT c_titre_court="Décret" id_txt="JORFTEXT000000000002">Décret</TITRE_TXT>
</TEXTE></CONTEXTE></ARTICLE>"""

KALI_CONT = """<IDCC><META><META_COMMUN><ID>KALICONT000005635109</ID><NATURE>IDCC</NATURE></META_COMMUN>
<META_SPEC><META_CONTENEUR><TITRE>Convention collective nationale des industries de la maroquinerie</TITRE>
<ETAT>VIGUEUR_ETEN</ETAT><NUM>2528</NUM><DATE_PUBLI>2005-09-09</DATE_PUBLI></META_CONTENEUR>
</META_SPEC></META>
<STRUCTURE_TXT><TM niv="1"><TITRE_TM>Texte de base</TITRE_TM>
<LIEN_TXT idtxt="KALITEXT000005672193" titretxt="Convention collective nationale du 9 septembre 2005"/>
</TM></STRUCTURE_TXT></IDCC>"""

KALI_ARTI = """<ARTICLE><META><META_COMMUN><ID>KALIARTI000054801844</ID><NATURE>Article</NATURE></META_COMMUN>
<META_SPEC><META_ARTICLE><NUM>1er</NUM><TITRE/><ETAT>VIGUEUR_ETEN</ETAT>
<DATE_DEBUT>2026-06-06</DATE_DEBUT><DATE_FIN>2999-01-01</DATE_FIN>
<DATE_DEB_EXT>2999-01-01</DATE_DEB_EXT><DATE_FIN_EXT>2999-01-01</DATE_FIN_EXT>
<TYPE>AUTONOME</TYPE></META_ARTICLE></META_SPEC></META>
<CONTEXTE><TEXTE cid="KALITEXT000054801841" date_signature="2026-04-02" nature="Accord" nor="ASET2650507M">
<TITRE_TXT c_titre_court="Plan d'épargne interentreprises facultatif" id_txt="KALITEXT000054801841"/></TEXTE>
<CONTENEUR cid="KALICONT000005635284" date_publi="1996-07-10" etat="VIGUEUR_ETEN" nature="IDCC"
           num="1938" titre="Convention collective nationale des industries de la transformation des volailles"/>
</CONTEXTE>
<BLOC_TEXTUEL><CONTENU><p>Le présent accord institue un plan d'épargne.</p></CONTENU></BLOC_TEXTUEL>
</ARTICLE>"""

KALI_SCTA = """<SECTION_TA><ID>KALISCTA000054801939</ID><TITRE_TA>Annexes</TITRE_TA>
<STRUCTURE_TA><LIEN_ART id="KALIARTI000054801940" num=""/>
<LIEN_ART id="KALIARTI000054801941" num=""/></STRUCTURE_TA></SECTION_TA>"""

CASS = """<TEXTE_JURI_JUDI>
<META><META_COMMUN><ID>JURITEXT000053345451</ID><NATURE>ARRET</NATURE></META_COMMUN>
<META_SPEC><META_JURI><TITRE>Cour de cassation, civile</TITRE><DATE_DEC>2026-01-07</DATE_DEC>
<JURIDICTION>Cour de cassation</JURIDICTION><NUMERO>12600011</NUMERO></META_JURI>
<META_JURI_JUDI><NUMEROS_AFFAIRES><NUMERO_AFFAIRE>24-18856</NUMERO_AFFAIRE>
<NUMERO_AFFAIRE>24-18857</NUMERO_AFFAIRE></NUMEROS_AFFAIRES>
<PUBLI_BULL publie="oui"/><FORMATION>CHAMBRE_CIVILE_1</FORMATION>
<FORM_DEC_ATT>Cour d'appel de Paris</FORM_DEC_ATT><DATE_DEC_ATT>2024-02-08</DATE_DEC_ATT>
<SIEGE_APPEL>VERSAILLES</SIEGE_APPEL><JURI_PREM>TGI</JURI_PREM><LIEU_PREM>NANTERRE</LIEU_PREM>
<DEMANDEUR>M. X</DEMANDEUR><DEFENDEUR>Société Y</DEFENDEUR>
<AVOCAT_GL>Mme Prada Bordenave (commissaire du gouvernement)</AVOCAT_GL>
<ECLI>ECLI:FR:CCASS:2026:C100011</ECLI></META_JURI_JUDI></META_SPEC></META>
<TEXTE><BLOC_TEXTUEL><CONTENU>LA COUR DE CASSATION</CONTENU></BLOC_TEXTUEL>
<SOMMAIRE><SCT ID="1" TYPE="PRINCIPAL">TOURISME</SCT>
<SCT ID="1" TYPE="REFERENCE">CONTRATS</SCT><ANA ID="1">Il résulte de…</ANA></SOMMAIRE>
<CITATION_JP><CONTENU>Dans le même sens que : T. confl., 22 mai 2006, n° 06-03.486</CONTENU></CITATION_JP>
</TEXTE>
<LIENS><LIEN cidtexte="JORFTEXT000000000009" naturetexte="CODE" typelien="CITATION">Code civil</LIEN></LIENS>
</TEXTE_JURI_JUDI>"""

CONSTIT = """<TEXTE_JURI_CONSTIT><META><META_COMMUN><ID>CONSTEXT000053623676</ID>
<NATURE>QPC</NATURE></META_COMMUN><META_SPEC>
<META_JURI><TITRE>Association des Bleuets</TITRE><DATE_DEC>2026-02-06</DATE_DEC>
<JURIDICTION>Conseil constitutionnel</JURIDICTION><NUMERO>2025-1180</NUMERO></META_JURI>
<META_JURI_CONSTIT><NOR>CSCX2603749S</NOR><NATURE_QUALIFIEE>QPC</NATURE_QUALIFIEE>
<LOI_DEF date="2999-01-01" nor="SUPPRIME" num=""/>
<TITRE_JO>JORF n°0032 du 7 février 2026, texte n° 66</TITRE_JO>
<URL_CC>https://www.conseil-constitutionnel.fr/decision/2026/20251180QPC.htm</URL_CC>
<ECLI>ECLI:FR:CC:2026:2025.1180.QPC</ECLI></META_JURI_CONSTIT></META_SPEC></META>
<TEXTE><BLOC_TEXTUEL><CONTENU>Décision</CONTENU></BLOC_TEXTUEL>
<SAISINES><CONTENU>Saisine du 3 novembre 2025</CONTENU></SAISINES>
<OBSERVATIONS><CONTENU>Observations du Gouvernement</CONTENU></OBSERVATIONS></TEXTE>
</TEXTE_JURI_CONSTIT>"""

CNIL = """<TEXTE_CNIL><META><META_COMMUN><ID>CNILTEXT000054790100</ID>
<NATURE>DELIBERATION</NATURE></META_COMMUN><META_SPEC><META_CNIL>
<TITRE>Délibération SAN-2026-009 du 21 juillet 2026</TITRE>
<TITREFULL>Délibération de la formation restreinte n°SAN-2026-009</TITREFULL>
<NUMERO>SAN-2026-009</NUMERO><NOR/><NATURE_DELIB>Sanction</NATURE_DELIB>
<DATE_TEXTE>2026-07-21</DATE_TEXTE><DATE_PUBLI>2026-09-03</DATE_PUBLI>
<ETAT_JURIDIQUE>VIGUEUR</ETAT_JURIDIQUE></META_CNIL></META_SPEC></META>
<BLOC_TEXTUEL><CONTENU><p>La Commission nationale de l'informatique et des libertés</p></CONTENU></BLOC_TEXTUEL>
</TEXTE_CNIL>"""


def _root(s):
    return ET.fromstring(s.encode("utf-8"))


# ── 1. KALI : les vrais conteneurs ────────────────────────────────────

def test_kali_les_balises_cherchees_navaient_aucune_chance():
    """META_TEXTE_KALI et META_CONVENTION_COLLECTIVE n'existent nulle part."""
    for frag in (KALI_CONT, KALI_ARTI, KALI_SCTA):
        r = _root(frag)
        assert r.find(".//META_TEXTE_KALI") is None
        assert r.find(".//META_CONVENTION_COLLECTIVE") is None


def test_kali_conteneur_donne_idcc_et_titre():
    r = _root(KALI_CONT)
    mc = r.find(".//META_CONTENEUR")
    assert mc is not None
    assert xml_text(mc.find("NUM")) == "2528"          # NUM = IDCC
    assert xml_text(mc.find("TITRE")).startswith("Convention collective nationale")
    assert xml_text(mc.find("ETAT")) == "VIGUEUR_ETEN"
    liens = [(lt.get("idtxt"), lt.get("titretxt")) for lt in r.iter("LIEN_TXT")]
    assert ("KALITEXT000005672193",
            "Convention collective nationale du 9 septembre 2005") in liens


def test_kali_article_porte_idcc_titre_etat_et_dates():
    r = _root(KALI_ARTI)
    cont = r.find(".//CONTEXTE/CONTENEUR")
    assert cont.get("num") == "1938"                    # IDCC
    assert "transformation des volailles" in cont.get("titre")
    assert cont.get("etat") == "VIGUEUR_ETEN"
    ma = r.find(".//META_ARTICLE")
    assert xml_text(ma.find("DATE_DEBUT")) == "2026-06-06"
    assert xml_text(ma.find("DATE_FIN")) == "2999-01-01"
    assert xml_text(ma.find("DATE_DEB_EXT")) == "2999-01-01"   # dates d'extension
    txt = r.find(".//CONTEXTE/TEXTE")
    assert txt.get("cid") == "KALITEXT000054801841"
    assert txt.get("nor") == "ASET2650507M"


def test_kali_section_rattache_ses_articles():
    """KALISCTA n'a PAS de META_COMMUN : l'ancien parseur le jetait avant même
    son test META_TEXTE_KALI. Il porte pourtant le rattachement en section."""
    r = _root(KALI_SCTA)
    assert r.find(".//META_COMMUN") is None
    assert xml_text(r.find("TITRE_TA")) == "Annexes"
    ids = [la.get("id") for la in r.find("STRUCTURE_TA").iter("LIEN_ART")]
    assert ids == ["KALIARTI000054801940", "KALIARTI000054801941"]


# ── 2. LEGI : la jointure article ↔ texte ─────────────────────────────

def test_legi_legitext_est_bien_un_legitext():
    legitext, jorftext, titre_text, hier = legi_contexte(_root(LEGI_ARTI))
    assert legitext == "LEGITEXT000005631294", (
        "legitext doit être le LEGITEXT (joignable avec legi_textes), "
        "pas le @cid qui vaut un JORFTEXT")
    assert jorftext == "JORFTEXT000000394028"
    # titre_text : comportement inchangé (premier TITRE_TXT)
    assert titre_text == "LOI organique n° 2001-692 du 1er août 2001"


def test_legi_hierarchie_conserve_les_legiscta_dans_lordre():
    _, _, _, hier = legi_contexte(_root(LEGI_ARTI))
    h = json.loads(hier)
    assert [x["id"] for x in h] == ["LEGISCTA000006084628", "LEGISCTA000006114781"]
    assert h[1]["titre"].startswith("Chapitre III")
    assert h[0]["debut"] == "2002-01-01"


def test_legi_sans_version_consolidee_on_retombe_sur_le_cid():
    legitext, jorftext, _, _ = legi_contexte(_root(LEGI_ARTI_SANS_LEGITEXT))
    assert legitext == jorftext == "JORFTEXT000000000002"


def test_legi_liens_en_json():
    liens = json.loads(liens_json(_root(LEGI_ARTI).find(".//LIENS")))
    assert liens[0]["cidtexte"] == "JORFTEXT000000739021"
    assert liens[0]["typelien"] == "CITATION"
    assert liens[0]["libelle"].startswith("Décret n°98-15")


# ── 4. Jurisprudence : ce que faisait enrich_dila.py, à l'ingestion ───

def test_cass_avocat_gl_et_non_avocat_general():
    r = _root(CASS)
    assert r.find(".//AVOCAT_GENERAL") is None, (
        "AVOCAT_GENERAL n'existe dans aucun format DILA — le code l'interrogeait")
    assert xml_text(r.find(".//AVOCAT_GL")).startswith("Mme Prada Bordenave")


def test_cass_champs_de_la_decision_attaquee_et_des_parties():
    ms = _root(CASS).find(".//META_JURI_JUDI")
    assert xml_text(ms.find("FORM_DEC_ATT")) == "Cour d'appel de Paris"
    assert xml_text(ms.find("DATE_DEC_ATT")) == "2024-02-08"
    assert xml_text(ms.find("SIEGE_APPEL")) == "VERSAILLES"
    assert xml_text(ms.find("JURI_PREM")) == "TGI"
    assert xml_text(ms.find("LIEU_PREM")) == "NANTERRE"
    assert xml_text(ms.find("DEMANDEUR")) == "M. X"
    assert xml_text(ms.find("DEFENDEUR")) == "Société Y"


def test_cass_tous_les_numeros_daffaires():
    nums = [xml_text(x) for x in _root(CASS).iter("NUMERO_AFFAIRE")]
    assert nums == ["24-18856", "24-18857"], (
        "les pourvois joints portent plusieurs numéros ; seul le premier "
        "était conservé")


def test_juris_enrich_remplit_les_colonnes_semantiques():
    r = _root(CASS)
    out = juris_enrich(r, r.find(".//META_JURI_JUDI"))
    assert "[PRINCIPAL] TOURISME" in out["abstrats"], (
        "l'attribut TYPE (PRINCIPAL/REFERENCE) était jeté")
    assert "[REFERENCE] CONTRATS" in out["abstrats"]
    assert out["resume"].startswith("Il résulte")
    assert "T. confl., 22 mai 2006" in out["renvois"]
    assert out["publi_bull"] == "oui"
    assert json.loads(out["liens_textes"])[0]["cidtexte"] == "JORFTEXT000000000009"
    # toutes les clés attendues sont présentes
    assert set(out) == {c for c, _ in JURIS_ENRICH_COLS}


def test_constit_a_son_propre_conteneur_de_metadonnees():
    """META_JURI_CONSTIT n'était dans aucune des deux branches du parseur :
    l'ECLI, pourtant présent, redevenait vide dans le flux courant."""
    r = _root(CONSTIT)
    assert r.find(".//META_JURI_JUDI") is None
    assert r.find(".//META_JURI_ADMIN") is None
    mc = r.find(".//META_JURI_CONSTIT")
    assert mc is not None
    assert xml_text(mc.find("ECLI")) == "ECLI:FR:CC:2026:2025.1180.QPC"
    assert xml_text(mc.find("NOR")) == "CSCX2603749S"
    assert xml_text(mc.find("TITRE_JO")).startswith("JORF n°0032")
    assert mc.find("URL_CC") is not None
    out = juris_enrich(r, mc)
    assert out["nature_qualifiee"] == "QPC"
    assert "Saisine du 3 novembre 2025" in out["saisines"]


# ── 5. CNIL : la date ─────────────────────────────────────────────────

def test_cnil_date_vient_de_meta_cnil():
    mc = _root(CNIL).find(".//META_CNIL")
    assert mc is not None
    assert xml_text(mc.find("DATE_TEXTE")) == "2026-07-21"
    assert xml_text(mc.find("DATE_PUBLI")) == "2026-09-03"
    assert xml_text(mc.find("NATURE_DELIB")) == "Sanction"
    assert xml_text(mc.find("ETAT_JURIDIQUE")) == "VIGUEUR"
    assert xml_text(mc.find("TITREFULL")).startswith("Délibération de la formation")
    # Pas de FORMATION dans le format CNIL : la colonne n'a aucune source.
    assert _root(CNIL).find(".//FORMATION") is None


# ── 3. JORF de bout en bout : mini-archive, corps recomposé ───────────

_JORF_TXT = """<TEXTE_VERSION><META><META_COMMUN><ID>JORFTEXT000000000001</ID>
<ID_ELI>https://www.legifrance.gouv.fr/eli/arrete/2026/9/4/X/jo/texte</ID_ELI>
<NATURE>ARRETE</NATURE></META_COMMUN><META_SPEC>
<META_TEXTE_CHRONICLE><NOR>ABC123</NOR><DATE_PUBLI>2026-09-06</DATE_PUBLI>
<DATE_TEXTE>2026-09-04</DATE_TEXTE><ORIGINE_PUBLI>JORF n°0208</ORIGINE_PUBLI>
</META_TEXTE_CHRONICLE><META_TEXTE_VERSION><TITRE>Arrete du 4 septembre 2026</TITRE>
<TITREFULL>Arrete complet</TITREFULL><MINISTERE>Interieur</MINISTERE>
<LIENS><LIEN cidtexte="JORFTEXT000000000009" typelien="CITATION">Decret</LIEN></LIENS>
</META_TEXTE_VERSION></META_SPEC></META>
<VISAS><CONTENU><p>Vu le code</p></CONTENU></VISAS>
<SIGNATAIRES><CONTENU><p>Fait le 4 septembre 2026</p></CONTENU></SIGNATAIRES></TEXTE_VERSION>"""

_JORF_STRUCT = """<TEXTELR><META><META_COMMUN><ID>JORFTEXT000000000001</ID></META_COMMUN></META>
<STRUCT><LIEN_ART id="JORFARTI000000000011" num="1"/>
<LIEN_ART id="JORFARTI000000000012" num="2"/></STRUCT></TEXTELR>"""


def _jorf_arti(aid, num, corps):
    return (f"<ARTICLE><META><META_COMMUN><ID>{aid}</ID></META_COMMUN>"
            f"<META_SPEC><META_ARTICLE><NUM>{num}</NUM></META_ARTICLE></META_SPEC></META>"
            f'<CONTEXTE><TEXTE cid="JORFTEXT000000000001"/></CONTEXTE>'
            f"<BLOC_TEXTUEL><CONTENU><p>{corps}</p></CONTENU></BLOC_TEXTUEL></ARTICLE>")


def _mini_tarball(path, membres):
    with tarfile.open(path, "w:gz") as t:
        for name, contenu in membres:
            b = contenu.encode("utf-8")
            ti = tarfile.TarInfo(name)
            ti.size = len(b)
            t.addfile(ti, io.BytesIO(b))


def test_jorf_corps_recompose_dans_lordre_et_sans_doublon():
    """Le corps d'un texte JORF vit dans les fichiers article/JORF/ARTI/…, que
    le parseur ignorait (`if "/texte/version/" not in member.name: continue`) :
    99,9 % du stock et 58 % du flux récent n'avaient AUCUN corps.
    On vérifie ici les trois propriétés qui comptent : le corps est là, il est
    dans l'ordre de STRUCTURE_TXT (les articles sont volontairement placés à
    l'envers dans l'archive), et une ré-ingestion ne le duplique pas."""
    d = tempfile.mkdtemp()
    tb = os.path.join(d, "t.tar.gz")
    _mini_tarball(tb, [
        # article 2 AVANT article 1 dans l'archive
        ("x/jorf/global/article/JORF/ARTI/a2.xml",
         _jorf_arti("JORFARTI000000000012", "2", "DEUXIEME ARTICLE")),
        ("x/jorf/global/article/JORF/ARTI/a1.xml",
         _jorf_arti("JORFARTI000000000011", "1", "PREMIER ARTICLE")),
        ("x/jorf/global/texte/struct/JORF/TEXT/s.xml", _JORF_STRUCT),
        ("x/jorf/global/texte/version/JORF/TEXT/v.xml", _JORF_TXT),
    ])
    db = os.path.join(d, "jorf.db")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        parse_jorf_like("jorf", tarball=tb, db=db)
    c = sqlite3.connect(db)
    titre, texte, id_eli, origine, liens = c.execute(
        "SELECT titre, texte, id_eli, origine_publi, liens FROM jorf_textes"
    ).fetchone()
    assert titre == "Arrete du 4 septembre 2026"
    assert "PREMIER ARTICLE" in texte and "DEUXIEME ARTICLE" in texte
    assert texte.index("PREMIER ARTICLE") < texte.index("DEUXIEME ARTICLE"), (
        "les articles doivent suivre l'ordre de STRUCT/LIEN_ART, pas celui du tar")
    assert "Vu le code" in texte and "Fait le 4 septembre" in texte, (
        "l'enveloppe (visas, signataires) doit être conservée")
    assert id_eli.startswith("https://www.legifrance.gouv.fr/eli/")
    assert origine == "JORF n°0208"
    assert json.loads(liens)[0]["cidtexte"] == "JORFTEXT000000000009"

    # Ré-ingestion de la MÊME archive : le corps ne doit pas être ajouté deux fois.
    with contextlib.redirect_stdout(buf):
        parse_jorf_like("jorf", tarball=tb, db=db)
    assert c.execute("SELECT texte FROM jorf_textes").fetchone()[0] == texte

    # …et l'index FTS5 retrouve bien le corps recomposé.
    n = c.execute("SELECT COUNT(*) FROM jorf_fts WHERE jorf_fts MATCH 'DEUXIEME'"
                  ).fetchone()[0]
    assert n == 1, "le corps recomposé doit être indexé par le FTS"
    c.close()
    shutil.rmtree(d, ignore_errors=True)


# ── 1. KALI de bout en bout : d'une table vide à des lignes remplies ──

def test_kali_de_bout_en_bout():
    """Avec le code d'avant, cette archive produisait ZÉRO ligne."""
    d = tempfile.mkdtemp()
    tb = os.path.join(d, "k.tar.gz")
    _mini_tarball(tb, [
        ("x/kali/global/conteneur/KALI/CONT/c.xml", KALI_CONT),
        ("x/kali/global/article/KALI/ARTI/a.xml", KALI_ARTI),
        ("x/kali/global/section_ta/KALI/SCTA/s.xml",
         KALI_SCTA.replace("KALIARTI000054801940", "KALIARTI000054801844")),
    ])
    db = os.path.join(d, "kali.db")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        parse_kali(tarball=tb, db=db)
    c = sqlite3.connect(db)
    total = c.execute("SELECT COUNT(*) FROM kali_textes").fetchone()[0]
    assert total == 2, f"1 conteneur + 1 article attendus, {total} obtenus"
    art = c.execute(
        "SELECT idcc, titre, etat, date_debut, date_fin, date_deb_ext, nor, "
        "article_num, section_titre, texte_id FROM kali_textes "
        "WHERE id='KALIARTI000054801844'").fetchone()
    assert art[0] == "1938", "l'IDCC vient de CONTEXTE/CONTENEUR@num"
    assert "transformation des volailles" in art[1]
    assert art[2] == "VIGUEUR_ETEN"
    assert art[3] == "2026-06-06" and art[4] == "2999-01-01"
    assert art[5] == "2999-01-01"              # date d'extension
    assert art[6] == "ASET2650507M"
    assert art[7] == "1er"
    assert art[8] == "Annexes", "l'article doit être rattaché à sa section KALISCTA"
    assert art[9] == "KALITEXT000054801841"
    cont = c.execute("SELECT idcc, titre FROM kali_textes "
                     "WHERE id='KALICONT000005635109'").fetchone()
    assert cont[0] == "2528" and cont[1].startswith("Convention collective")
    c.close()
    shutil.rmtree(d, ignore_errors=True)


# ── Ré-ingestion : ne pas détruire les colonnes dérivées ──────────────

def _mini_table(sql_ins):
    """Table façon capp_decisions : 3 colonnes écrites par le parseur + une
    colonne DÉRIVÉE, remplie par un script tiers, qu'aucun parseur ne connaît."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE capp_decisions (id TEXT PRIMARY KEY, titre TEXT, "
              "texte TEXT, numero_rg_norm TEXT)")
    c.execute("INSERT INTO capp_decisions VALUES ('X1','t1','tx1','RG-DERIVE')")
    rowid_avant = c.execute("SELECT rowid FROM capp_decisions").fetchone()[0]
    c.execute(sql_ins, ("X1", "t1", "tx1"))
    row = c.execute("SELECT numero_rg_norm, rowid FROM capp_decisions").fetchone()
    c.close()
    return row[0], rowid_avant, row[1]


def test_reingestion_preserve_les_colonnes_derivees():
    """`capp_decisions.numero_rg_norm` est produite par
    scripts/prod-oneshot/extract_rg_prod.py, jamais par un parseur. Avec
    INSERT OR REPLACE, une ré-ingestion complète l'effaçait sans un mot."""
    cols = ["id", "titre", "texte"]
    val, rid_avant, rid_apres = _mini_table(
        upsert_sql("capp_decisions", cols, "id"))
    assert val == "RG-DERIVE", "l'UPSERT doit préserver la colonne dérivée"
    assert rid_avant == rid_apres, (
        "l'UPSERT doit garder le même rowid — l'index FTS5 externe y est indexé")

    # Contre-preuve : l'ancienne écriture détruit les deux.
    val2, rid2_avant, rid2_apres = _mini_table(
        "INSERT OR REPLACE INTO capp_decisions (id, titre, texte) VALUES (?,?,?)")
    assert val2 is None, "contre-preuve attendue : OR REPLACE efface la colonne"
    assert rid2_avant != rid2_apres, "contre-preuve : OR REPLACE change le rowid"


def test_upsert_ne_remplace_pas_par_du_vide_quand_demande():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE legi_textes (legitext TEXT PRIMARY KEY, titre TEXT)")
    sql = upsert_sql("legi_textes", ["legitext", "titre"], "legitext",
                     keep_non_empty=True)
    c.execute(sql, ("L1", "Code civil"))     # fichier texte/version : titre
    c.execute(sql, ("L1", ""))               # fichier texte/struct : sans titre
    assert c.execute("SELECT titre FROM legi_textes").fetchone()[0] == "Code civil"
    c.close()


# ── Schéma : ADD COLUMN seulement ─────────────────────────────────────

def test_migration_est_add_column_seulement():
    """Le script de migration ne doit contenir aucun DROP/RENAME/UPDATE."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "scripts", "migrate_schema_dila.py")
    src = open(path, encoding="utf-8").read().upper()
    for interdit in ("DROP TABLE", "DROP COLUMN", "RENAME TO", "RENAME COLUMN",
                     "DELETE FROM"):
        assert interdit not in src, f"{interdit} interdit dans la migration"
    assert "ADD COLUMN" in src


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            fails += 1
            print(f"  ✗ {name} — {e}")
    print()
    if fails:
        print(f"{fails} test(s) en échec sur {len(tests)}.")
        sys.exit(1)
    print(f"All {len(tests)} tests passed.")
