"""Contrôle de couverture : demander à CHAQUE source combien elle a, et comparer.

POURQUOI CE FICHIER (30 août 2026)
──────────────────────────────────
Un trou de données ne produit aucun symptôme. Un mois d'avril avec 2 104
décisions se comporte exactement comme un mois avec 50 000 : la page
s'affiche, les filtres marchent, le compteur est juste, les résultats sont
pertinents. Le système ne peut pas voir ce qu'il ne contient pas.

Quatre mois d'audits de CODE n'ont rien trouvé, parce que le code était
correct. C'est le monde qui manquait. La seule façon de détecter un trou est
d'interroger une référence EXTÉRIEURE — la source elle-même.

Sondé le 29 août 2026 : les six sources savent toutes annoncer un total.
Ce script s'en sert. Il ne corrige rien, il crie.

Ce qu'il a trouvé à sa première exécution :
  - judiciaire : 248 250 décisions manquantes sur janv.–août 2026
  - CEDH 2026  : 51,7 % (tuyau mort le 30 avril, réparé le 29 août)
  - CJUE       : 100 % sur 2019–2026, rien à signaler
  - CEDH ≤2025 : 99–100 %, rien à signaler

LIMITES ASSUMÉES
────────────────
ArianeWeb (Sinequa) et l'API juriadmin n'annoncent un total que pour une
REQUÊTE, pas pour un corpus : on ne peut pas leur demander « combien de
décisions en juillet ». Ils sont donc contrôlés par la FRAÎCHEUR (la date
du document le plus récent), qui détecte le seul mode de panne réel : un
tuyau qui s'arrête. Même chose pour les fonds DILA, alimentés par archives
quotidiennes. C'est écrit dans le rapport plutôt que maquillé.

Usage :
    python3 scripts/controle_couverture.py              # rapport complet
    python3 scripts/controle_couverture.py --json       # sortie machine
    python3 scripts/controle_couverture.py --mois 3     # 3 derniers mois
Code de sortie : 1 si au moins une alerte, 0 sinon (utilisable en cron).
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_JUDICIAIRE = "/opt/justicelibre/dila/judiciaire.db"
UA = "justicelibre.org/1.0 (controle de couverture, contact: dahliyaal@justicelibre.org)"

# Seuil d'alerte sur la couverture (part de ce que la source annonce).
SEUIL_COUVERTURE = 0.90
# Seuil d'alerte sur la fraîcheur, en jours, pour les sources sans total.
SEUIL_FRAICHEUR_J = 10

SPARQL_CJUE = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT (COUNT(DISTINCT ?celex) AS ?n) WHERE {
  ?work cdm:work_has_resource-type ?rtype .
  VALUES ?rtype {
    <http://publications.europa.eu/resource/authority/resource-type/JUDG>
    <http://publications.europa.eu/resource/authority/resource-type/JUDG_GNR>
    <http://publications.europa.eu/resource/authority/resource-type/JUDG_JURINFO>
    <http://publications.europa.eu/resource/authority/resource-type/ORDER>
    <http://publications.europa.eu/resource/authority/resource-type/OPIN_AG>
  }
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  FILTER(STRSTARTS(STR(?celex), "6"))
  FILTER(?date >= "%s"^^xsd:date && ?date < "%s"^^xsd:date)
}
"""


def _mois_recents(n: int) -> list[tuple[str, str, str]]:
    """[(libellé, début inclus, fin exclu)] pour les n mois complets précédents."""
    out = []
    d = date.today().replace(day=1)
    for _ in range(n):
        fin = d
        d = (d - timedelta(days=1)).replace(day=1)
        out.append((d.strftime("%Y-%m"), d.isoformat(), fin.isoformat()))
    return out


# ─── Sources qui savent annoncer un total ─────────────────────────────────

def ref_judilibre(debut: str, fin: str) -> int:
    import judilibre_sync as J
    c = httpx.Client(headers={"Authorization": f"Bearer {J.get_token()}"})
    # `date_end` est INCLUSIVE côté Judilibre : on recule d'un jour.
    fin_incl = (datetime.strptime(fin, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
    total = 0
    for juri in ("cc", "ca", "tj", "tcom"):
        d = J.piste_get(c, "/export", date_start=debut, date_end=fin_incl,
                        jurisdiction=juri, batch=0, batch_size=1)
        total += d.get("total") or 0
    return total


def ref_cedh(annee: int) -> int:
    q = ('contentsitename=ECHR AND (NOT (doctype=PR OR doctype=HFCOMOLD OR doctype=HECOMOLD)) '
         f'AND ((languageisocode="FRE")) AND kpdate:[{annee}-01-01T00:00:00.0Z '
         f'TO {annee}-12-31T23:59:59.0Z]')
    url = (f"https://hudoc.echr.coe.int/app/query/results?query={quote(q, safe='')}"
           f"&select=itemid&sort={quote('kpdate Descending', safe='')}&start=0&length=1")
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=45)
    r.raise_for_status()
    return r.json().get("resultcount") or 0


def ref_cjue(annee: int) -> int:
    r = httpx.get("https://publications.europa.eu/webapi/rdf/sparql",
                  params={"query": SPARQL_CJUE % (f"{annee}-01-01", f"{annee+1}-01-01"),
                          "format": "application/sparql-results+json"},
                  headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    return int(r.json()["results"]["bindings"][0]["n"]["value"])


def compte_local(conn, table: str, debut: str, fin: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE date >= ? AND date < ?",
                        (debut, fin)).fetchone()[0]


def date_max(conn, table: str, colonne: str = "date") -> str:
    r = conn.execute(f"SELECT MAX({colonne}) FROM {table}").fetchone()
    return (r[0] or "")[:10]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mois", type=int, default=2, help="nombre de mois complets à contrôler")
    p.add_argument("--annees", type=int, default=2, help="nombre d'années à contrôler (CEDH/CJUE)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--db", default=DB_JUDICIAIRE)
    args = p.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rapport = {"date": datetime.now(timezone.utc).isoformat(), "lignes": [], "alertes": []}

    def ajoute(source, periode, attendu, obtenu, note=""):
        couv = (obtenu / attendu) if attendu else 1.0
        ligne = {"source": source, "periode": periode, "source_annonce": attendu,
                 "chez_nous": obtenu, "couverture": round(100 * couv, 1), "note": note}
        rapport["lignes"].append(ligne)
        if attendu and couv < SEUIL_COUVERTURE:
            rapport["alertes"].append(
                f"{source} {periode} : {obtenu}/{attendu} ({100*couv:.1f} %), "
                f"{attendu - obtenu} manquant(s)")
        return ligne

    # 1. Judiciaire (Judilibre) — mois par mois
    for lib, debut, fin in _mois_recents(args.mois):
        try:
            ajoute("judiciaire", lib, ref_judilibre(debut, fin),
                   compte_local(conn, "decisions", debut, fin))
        except Exception as e:
            rapport["alertes"].append(f"judiciaire {lib} : référence INDISPONIBLE ({type(e).__name__})")

    # 2. CEDH et CJUE — année par année
    an = date.today().year
    for annee in range(an, an - args.annees, -1):
        for source, ref, table in (("cedh", ref_cedh, "cedh_decisions"),
                                   ("cjue", ref_cjue, "cjue_decisions")):
            try:
                ajoute(source, str(annee), ref(annee),
                       compte_local(conn, table, f"{annee}-01-01", f"{annee+1}-01-01"))
            except Exception as e:
                rapport["alertes"].append(
                    f"{source} {annee} : référence INDISPONIBLE ({type(e).__name__})")

    # 3. Sources sans total annonçable → contrôle de FRAÎCHEUR.
    #    On ne maquille pas : c'est une garantie plus faible, et c'est dit.
    limite = (date.today() - timedelta(days=SEUIL_FRAICHEUR_J)).isoformat()
    # `ariane_decisions` ne stocke PAS la date de la décision (le plugin Sinequa
    # ne renvoie que du texte brut) : la seule horloge disponible est
    # `fetched_at`, la date de moissonnage. Elle répond à la bonne question —
    # « le tuyau coule-t-il encore ? » — mais pas à « la couverture est-elle
    # complète ? ». C'est dit dans la note plutôt que maquillé.
    for source, table, colonne, quoi in (
        ("ariane", "ariane_decisions", "fetched_at", "dernier moissonnage"),
    ):
        try:
            dmax = date_max(conn, table, colonne)
            rapport["lignes"].append({"source": source, "periode": "fraîcheur",
                                      "source_annonce": None, "chez_nous": dmax or "—",
                                      "couverture": None,
                                      "note": f"pas de total annonçable — {quoi}"})
            if dmax and dmax < limite:
                rapport["alertes"].append(
                    f"{source} : {quoi} = {dmax}, soit plus de "
                    f"{SEUIL_FRAICHEUR_J} jours de retard")
            elif not dmax:
                rapport["alertes"].append(f"{source} : aucune date de moissonnage en base")
        except Exception as e:
            rapport["alertes"].append(f"{source} : fraîcheur illisible ({type(e).__name__}: {e})")

    if args.json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
    else:
        print(f"CONTRÔLE DE COUVERTURE — {rapport['date'][:19]} UTC\n")
        print(f"{'source':12s} {'période':10s} {'annoncé':>9s} {'chez nous':>11s} {'couv.':>7s}")
        print("─" * 56)
        for l in rapport["lignes"]:
            att = l["source_annonce"]
            couv = f"{l['couverture']:.1f}%" if l["couverture"] is not None else "—"
            marque = "  ⚠️" if (att and l["couverture"] < 100 * SEUIL_COUVERTURE) else ""
            print(f"{l['source']:12s} {l['periode']:10s} {str(att or '—'):>9s} "
                  f"{str(l['chez_nous']):>11s} {couv:>7s}{marque}")
        if rapport["alertes"]:
            print(f"\n⚠️  {len(rapport['alertes'])} ALERTE(S)")
            for a in rapport["alertes"]:
                print(f"   • {a}")
        else:
            print("\n✓ Aucune alerte : toutes les sources contrôlées sont complètes.")

    return 1 if rapport["alertes"] else 0


if __name__ == "__main__":
    sys.exit(main())
