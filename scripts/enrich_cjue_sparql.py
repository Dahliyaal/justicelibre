#!/usr/bin/env python3
"""CJUE : réparer l'ECLI et récupérer les 16 métadonnées jetées, par SPARQL.

Pourquoi ce script existe (8 septembre 2026, rapport M § 12).

1. **L'ECLI en base est FAUX.** `scrape_cjue.py` le fabriquait à partir du
   CELEX (`ECLI:EU:C:<année du CELEX>:<n° d'affaire>`). Le dernier segment
   d'un ECLI est un numéro d'enregistrement séquentiel de la Cour, sans
   rapport avec le numéro d'affaire. Mesuré en prod : 2 996 ECLI non vides
   sur 3 000 lignes, « quasiment tous faux », et deux documents distincts
   portant le même identifiant. Le correctif de `scrape_cjue.py:113-130`
   n'a neutralisé que les écritures futures ; le stock est resté faux.

   Preuve refaite le 8/09/2026 contre EUR-Lex (vérifiable en rejouant
   `--only 62019CJ0030 --only 62019CC0030`) :

       CELEX          ECLI en base (faux)   ECLI réel (cdm:case-law_ecli)
       62019CJ0030    ECLI:EU:C:2019:30     ECLI:EU:C:2021:269
       62019CC0030    ECLI:EU:C:2019:30     ECLI:EU:C:2020:374

   Les deux documents — l'arrêt et les conclusions de l'avocat général —
   partageaient bien le MÊME faux ECLI ; ils en reçoivent deux différents.

2. **Le titre est vide** (0 / 3 000 lignes) : la regex `<title>` de
   `scrape_cjue.py:99` ne rend plus rien sur les pages actuelles d'EUR-Lex.
   Le titre officiel français est dans le graphe (`cdm:expression_title` de
   l'expression FRA) — pas besoin de re-scraper le HTML.

3. **Seize champs sont jetés** : graphe de citations, avocat général, juge
   rapporteur, formation, nature du renvoi, matières, pays d'origine, langue
   de procédure, dispositions interprétées, lien arrêt↔conclusions, recueil.

Toutes ces données viennent d'UNE source, l'endpoint SPARQL public d'EUR-Lex,
en deux requêtes par lot de CELEX (métadonnées + liens). Mesuré : 100 CELEX
par requête en 0,4 s.

⚠️ Piège Virtuoso : le CELEX est stocké en `"…"^^xsd:string` et l'endpoint
distingue ce terme du littéral simple `"…"`. Un `VALUES ?celex { "62019CJ0030" }`
sans le `^^xsd:string` renvoie ZÉRO ligne, sans erreur. De même,
`VALUES ?rel { cdm:work_cites_work … }` (variable en position de prédicat)
renvoie zéro : les trois relations sont donc récupérées par UNION.

Sécurité d'écriture (règle du projet : jamais d'écrasement sans sauvegarde) :
  * `ecli` et `title` sont copiés dans `ecli_avant` / `title_avant` ET dans
    un CSV.gz avant toute modification ;
  * un ECLI n'est écrasé QUE si EUR-Lex en fournit un ;
  * `--dry-run` est le défaut.

Usage :
    # preuve sur les deux CELEX du rapport, sans rien écrire
    python3 scripts/enrich_cjue_sparql.py --db … --only 62019CJ0030 --only 62019CC0030

    # dry-run sur 200 lignes
    python3 scripts/enrich_cjue_sparql.py --db … --limit 200

    # écriture réelle, reprenable
    python3 scripts/enrich_cjue_sparql.py --db … --apply

Lancement en prod, depuis /opt/justicelibre, par systemd-run (jamais nohup+&) :

    systemd-run --unit=jl-enrich-cjue \\
      /usr/bin/python3 /opt/justicelibre/scripts/enrich_cjue_sparql.py \\
      --db /opt/justicelibre/dila/judiciaire.db --limit 0 --batch 50 --apply

    journalctl -u jl-enrich-cjue -f
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx

DB_DEFAUT = "/opt/justicelibre/dila/judiciaire.db"
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
USER_AGENT = "justicelibre/1.0 (+https://justicelibre.org)"
LANGUE_TITRE = "http://publications.europa.eu/resource/authority/language/FRA"

PREFIXES = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# Requête 1 — les métadonnées scalaires et les petits ensembles.
# GROUP BY ?celex : un même CELEX porte souvent DEUX works dans Cellar (le
# `evolutive_work`, riche, et un membre marqué `do_not_index`). Agréger sur le
# CELEX prend le meilleur des deux sans avoir à choisir.
Q_META = PREFIXES + """SELECT ?celex
 (SAMPLE(?xecli) AS ?ecli) (SAMPLE(?xdate) AS ?date) (SAMPLE(?xtype) AS ?rtype)
 (SAMPLE(?xtitle) AS ?title) (SAMPLE(?xerec) AS ?erecueil)
 (GROUP_CONCAT(DISTINCT ?xag; separator="|") AS ?avocat_general)
 (GROUP_CONCAT(DISTINCT ?xjuge; separator="|") AS ?juges)
 (GROUP_CONCAT(DISTINCT ?xform; separator="|") AS ?formation)
 (GROUP_CONCAT(DISTINCT ?xprocjur; separator="|") AS ?procjur)
 (GROUP_CONCAT(DISTINCT ?xtypeproc; separator="|") AS ?type_procedure)
 (GROUP_CONCAT(DISTINCT ?xsubj; separator="|") AS ?matieres)
 (GROUP_CONCAT(DISTINCT ?xsubj2; separator="|") AS ?matieres_legal)
 (GROUP_CONCAT(DISTINCT ?xpays; separator="|") AS ?pays)
 (GROUP_CONCAT(DISTINCT ?xlangproc; separator="|") AS ?langue_procedure)
WHERE {
 VALUES ?celex { %(values)s }
 ?w cdm:resource_legal_id_celex ?celex .
 OPTIONAL { ?w cdm:case-law_ecli ?xecli }
 OPTIONAL { ?w cdm:work_date_document ?xdate }
 OPTIONAL { ?w cdm:work_has_resource-type ?xtype }
 OPTIONAL { ?w cdm:case-law_published_in_erecueil ?xerec }
 OPTIONAL { ?w cdm:case-law_delivered_by_advocate-general ?agU .
            OPTIONAL { ?agU cdm:agent_name ?xag } }
 OPTIONAL { ?w cdm:case-law_delivered_by_judge ?juU .
            OPTIONAL { ?juU cdm:agent_name ?xjuge } }
 OPTIONAL { ?w cdm:case-law_delivered_by_court-formation ?xform }
 OPTIONAL { ?w cdm:case-law_has_procjur ?xprocjur }
 OPTIONAL { ?w cdm:case-law_has_type_procedure_concept_type_procedure ?xtypeproc }
 OPTIONAL { ?w cdm:case-law_is-about_case-law-subject-matter ?xsubj }
 OPTIONAL { ?w cdm:resource_legal_is_about_subject-matter ?xsubj2 }
 OPTIONAL { ?w cdm:case-law_originates_in_country ?xpays }
 OPTIONAL { ?w cdm:case-law_uses_procedure_language ?xlangproc }
 OPTIONAL { ?e cdm:expression_belongs_to_work ?w ;
              cdm:expression_uses_language <%(langue)s> ;
              cdm:expression_title ?xtitle }
}
GROUP BY ?celex"""

# Requête 2 — les trois relations entre documents, résolues en CELEX.
Q_LIENS = PREFIXES + """SELECT ?celex ?rel ?cible WHERE {
 VALUES ?celex { %(values)s }
 ?w cdm:resource_legal_id_celex ?celex .
 { ?w cdm:work_cites_work ?t . BIND("cite" AS ?rel) }
 UNION { ?w cdm:case-law_interpretes_resource_legal ?t . BIND("interprete" AS ?rel) }
 UNION { ?w cdm:case-law_has_conclusions_opinion_advocate-general ?t .
         BIND("conclusions" AS ?rel) }
 ?t cdm:resource_legal_id_celex ?cible .
}"""

# Champs de `cjue_meta` alimentés par Q_META (hors ecli/title, qui ont leur
# propre colonne).
CHAMPS_META = ("date_sparql", "type_sparql", "erecueil", "avocat_general", "juges",
               "formation", "procjur", "type_procedure", "matieres",
               "matieres_legal", "pays", "langue_procedure")


def code(uri: str) -> str:
    """Dernier segment d'une URI d'autorité (CHAMB_GD_C, REFER_PREL, SWE…)."""
    return uri.rsplit("/", 1)[-1] if uri else ""


def liste(valeur: str) -> list[str]:
    """Découpe un GROUP_CONCAT, en gardant les codes d'autorité seulement."""
    if not valeur:
        return []
    return [code(v) for v in valeur.split("|") if v]


class ClientSparql:
    """Client SPARQL poli : ≤ `max_par_sec` requêtes/s, réessai borné."""

    def __init__(self, max_par_sec: float = 2.0, essais: int = 3, timeout: float = 180.0):
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout)
        self.intervalle = 1.0 / max_par_sec if max_par_sec > 0 else 0.0
        self.essais = essais
        self._dernier = 0.0
        self.requetes = 0
        self.secondes = 0.0

    def interroger(self, requete: str) -> list[dict]:
        attente = self.intervalle - (time.time() - self._dernier)
        if attente > 0:
            time.sleep(attente)
        derniere_erreur = None
        for essai in range(self.essais):
            t0 = time.time()
            try:
                r = self.client.get(
                    SPARQL,
                    params={"query": requete,
                            "format": "application/sparql-results+json"})
                self._dernier = time.time()
                self.requetes += 1
                self.secondes += self._dernier - t0
                if r.status_code == 200:
                    return r.json()["results"]["bindings"]
                derniere_erreur = f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as exc:                      # réseau, JSON, timeout
                self._dernier = time.time()
                derniere_erreur = f"{type(exc).__name__}: {exc}"
            time.sleep(2 ** essai * 3)
        raise RuntimeError(f"SPARQL en échec après {self.essais} essais — {derniere_erreur}")

    def close(self) -> None:
        self.client.close()


def values(celexes) -> str:
    """⚠️ `^^xsd:string` obligatoire (cf. en-tête du fichier)."""
    return " ".join('"%s"^^xsd:string' % c.replace('"', '') for c in celexes)


def interroger_lot(cli: ClientSparql, celexes: list[str]) -> dict[str, dict]:
    v = values(celexes)
    meta: dict[str, dict] = {}
    for b in cli.interroger(Q_META % {"values": v, "langue": LANGUE_TITRE}):
        d = {k: b[k]["value"] for k in b}
        celex = d.get("celex", "")
        if not celex:
            continue
        meta[celex] = {
            "ecli": d.get("ecli", ""),
            "title": (d.get("title", "") or "").replace("#", " — ").strip(),
            "date_sparql": (d.get("date", "") or "")[:10],
            "type_sparql": code(d.get("rtype", "")),
            "erecueil": d.get("erecueil", ""),
            "avocat_general": [x for x in (d.get("avocat_general", "") or "").split("|") if x],
            "juges": [x for x in (d.get("juges", "") or "").split("|") if x],
            "formation": liste(d.get("formation", "")),
            "procjur": liste(d.get("procjur", "")),
            "type_procedure": liste(d.get("type_procedure", "")),
            "matieres": liste(d.get("matieres", "")),
            "matieres_legal": liste(d.get("matieres_legal", "")),
            "pays": liste(d.get("pays", "")),
            "langue_procedure": liste(d.get("langue_procedure", "")),
            "cite": [], "interprete": [], "conclusions": [],
        }
    for b in cli.interroger(Q_LIENS % {"values": v}):
        celex = b.get("celex", {}).get("value", "")
        rel = b.get("rel", {}).get("value", "")
        cible = b.get("cible", {}).get("value", "")
        if celex in meta and rel in ("cite", "interprete", "conclusions") and cible:
            if cible not in meta[celex][rel]:
                meta[celex][rel].append(cible)
    return meta


def ajouter_colonnes(conn: sqlite3.Connection, table: str, colonnes) -> list[str]:
    existantes = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    creees = []
    for col in colonnes:
        if col in existantes:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        creees.append(col)
    if creees:
        conn.commit()
    return creees


def charger_etat(chemin: Path) -> dict:
    if chemin.exists():
        try:
            return json.loads(chemin.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"dernier_celex": "", "traites": 0}


def ecrire_etat(chemin: Path, etat: dict) -> None:
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, chemin)


def sauver(chemin: Path, lignes) -> None:
    neuf = not chemin.exists()
    with gzip.open(chemin, "at", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if neuf:
            w.writerow(["celex", "ecli_avant", "title_avant", "ecli_apres", "title_apres"])
        w.writerows(lignes)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DB_DEFAUT)
    p.add_argument("--table", default="cjue_decisions")
    p.add_argument("--apply", action="store_true", help="écrit réellement (défaut : dry-run)")
    p.add_argument("--limit", type=int, default=100, help="nombre de CELEX à traiter (0 = tout)")
    # 50 et non 100 : mesuré le 8/09/2026, la requête de LIENS (trois UNION)
    # passe de 0,42 s à 6,9 s entre 50 et 100 CELEX — le débit total tombe de
    # 28,5 à 6,8 CELEX/s. Doubler le lot divise le débit par quatre.
    p.add_argument("--batch", type=int, default=50, help="CELEX par requête SPARQL")
    p.add_argument("--only", action="append", default=[],
                   help="ne traiter que ce CELEX (répétable) — pour la preuve")
    p.add_argument("--montrer", type=int, default=5)
    p.add_argument("--force", action="store_true", help="retraite les lignes déjà enrichies")
    p.add_argument("--effacer-ecli-inconnu", action="store_true",
                   help="vide l'ECLI fabriqué quand EUR-Lex n'en fournit aucun "
                        "(l'ancien reste dans ecli_avant et dans le CSV.gz)")
    p.add_argument("--max-par-sec", type=float, default=2.0)
    p.add_argument("--state", default="")
    p.add_argument("--backup", default="")
    args = p.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[erreur] base introuvable : {db}")
        return 2
    etat_path = Path(args.state) if args.state else db.with_suffix(db.suffix + ".cjue_enrich.state.json")
    backup_path = Path(args.backup) if args.backup else db.with_suffix(db.suffix + ".cjue_enrich.backup.csv.gz")

    conn = sqlite3.connect(str(db), timeout=300.0)
    conn.execute("PRAGMA busy_timeout=300000")
    cibles = ["ecli_avant", "title_avant", "cjue_meta"]
    if args.apply:
        conn.execute("PRAGMA journal_mode=WAL")
        print(f"[schéma] colonnes créées : "
              f"{ajouter_colonnes(conn, args.table, cibles) or '(aucune, déjà présentes)'}")
    else:
        existantes = {r[1] for r in conn.execute(f"PRAGMA table_info({args.table})")}
        print(f"[dry-run] ALTER TABLE ADD COLUMN prévus : "
              f"{[c for c in cibles if c not in existantes] or '(aucun)'}")

    existantes = {r[1] for r in conn.execute(f"PRAGMA table_info({args.table})")}
    a_meta = "cjue_meta" in existantes

    etat = charger_etat(etat_path)
    if args.only:
        marques = ",".join("?" * len(args.only))
        sql = f"SELECT celex, ecli, title FROM {args.table} WHERE celex IN ({marques})"
        params: list = list(args.only)
        lignes = list(conn.execute(sql, params))
        # `--only` doit prouver quelque chose même sur un CELEX absent de la
        # base : on interroge quand même EUR-Lex, sans rien écrire.
        presents = {r[0] for r in lignes}
        lignes += [(c, None, None) for c in args.only if c not in presents]
    else:
        depuis = "" if args.force else etat.get("dernier_celex", "")
        filtre = ""
        if a_meta and not args.force:
            filtre = " AND (cjue_meta IS NULL OR cjue_meta = '')"
        sql = (f"SELECT celex, ecli, title FROM {args.table} "
               f"WHERE celex > ?{filtre} ORDER BY celex")
        params = [depuis]
        if args.limit:
            sql += " LIMIT ?"
            params.append(args.limit)
        lignes = list(conn.execute(sql, params))

    if not lignes:
        print("Rien à traiter (tout est déjà enrichi, ou --limit 0 sur une base vide).")
        conn.close()
        return 0

    cli = ClientSparql(max_par_sec=args.max_par_sec)
    t0 = time.time()
    montres = 0
    ecrits = 0
    stats = {"sparql_ecli": 0, "ecli_change": 0, "ecli_absent_sparql": 0,
             "titre_recupere": 0, "avec_citations": 0, "sans_reponse": 0}
    lot_update: list[tuple] = []
    sauvegardes: list[list] = []
    dernier = etat.get("dernier_celex", "")

    for debut in range(0, len(lignes), args.batch):
        tranche = lignes[debut:debut + args.batch]
        celexes = [r[0] for r in tranche]
        try:
            meta = interroger_lot(cli, celexes)
        except RuntimeError as exc:
            print(f"[abandon] {exc}")
            break
        for celex, ecli_base, titre_base in tranche:
            dernier = max(dernier, celex)
            m = meta.get(celex)
            if not m:
                stats["sans_reponse"] += 1
                continue
            ecli_neuf = m["ecli"]
            titre_neuf = m["title"]
            if ecli_neuf:
                stats["sparql_ecli"] += 1
                if (ecli_base or "") != ecli_neuf:
                    stats["ecli_change"] += 1
            else:
                stats["ecli_absent_sparql"] += 1
            if titre_neuf and not (titre_base or ""):
                stats["titre_recupere"] += 1
            if m["cite"]:
                stats["avec_citations"] += 1

            meta_json = json.dumps(
                {k: m[k] for k in CHAMPS_META} |
                {"cite": m["cite"], "interprete": m["interprete"],
                 "conclusions": m["conclusions"],
                 "ecli_source": "cdm:case-law_ecli" if ecli_neuf else "absent",
                 "moissonne_le": time.strftime("%Y-%m-%d")},
                ensure_ascii=False, separators=(",", ":"))

            if ecli_neuf:
                ecli_ecrit = ecli_neuf
            elif args.effacer_ecli_inconnu:
                ecli_ecrit = ""
            else:
                ecli_ecrit = ecli_base or ""
            titre_ecrit = titre_neuf or (titre_base or "")

            if (ecli_base or "") and (ecli_base or "") != ecli_ecrit:
                sauvegardes.append([celex, ecli_base, titre_base, ecli_ecrit, titre_ecrit])
            elif (titre_base or "") and (titre_base or "") != titre_ecrit:
                sauvegardes.append([celex, ecli_base, titre_base, ecli_ecrit, titre_ecrit])

            if montres < args.montrer:
                montres += 1
                print(f"\n  --- {celex}")
                print(f"      ecli   base : {ecli_base or '∅'}")
                print(f"      ecli EUR-Lex: {ecli_neuf or '∅'}"
                      f"{'   ❗ DIFFÉRENT' if ecli_neuf and ecli_neuf != (ecli_base or '') else ''}")
                print(f"      titre  base : {(titre_base or '∅')[:70]}")
                print(f"      titre SPARQL: {(titre_neuf or '∅')[:70]}")
                print(f"      cjue_meta   : {meta_json[:400]}")

            if args.apply:
                lot_update.append((ecli_ecrit, titre_ecrit,
                                   ecli_base or None, titre_base or None,
                                   meta_json, celex))

        if args.apply and lot_update:
            conn.executemany(
                f"UPDATE {args.table} SET ecli = ?, title = ?, "
                f"ecli_avant = COALESCE(ecli_avant, ?), "
                f"title_avant = COALESCE(title_avant, ?), cjue_meta = ? "
                f"WHERE celex = ?", lot_update)
            if sauvegardes:
                sauver(backup_path, sauvegardes)
                sauvegardes = []
            conn.commit()
            ecrits += len(lot_update)
            lot_update = []
            etat.update({"dernier_celex": dernier,
                         "traites": etat.get("traites", 0) + len(tranche)})
            ecrire_etat(etat_path, etat)
            print(f"    +{ecrits} écrits")

    dt = max(time.time() - t0, 0.001)
    n = len(lignes)
    print(f"\n=== {n} CELEX en {dt:.1f}s — {cli.requetes} requêtes SPARQL "
          f"({cli.secondes / max(cli.requetes, 1):.2f}s/requête, "
          f"{n / dt:.1f} CELEX/s)")
    for k, v in stats.items():
        print(f"    {k:22s} {v}")
    if args.apply:
        print(f"écrits : {ecrits} — état : {etat_path} — sauvegarde : {backup_path}")
    else:
        print("DRY-RUN : aucune écriture. Ajouter --apply pour écrire.")
    cli.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
