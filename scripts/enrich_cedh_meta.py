#!/usr/bin/env python3
"""CEDH : récupérer les 18 champs jetés par l'endpoint de LISTE de HUDOC.

Pourquoi ce script existe (8 septembre 2026, rapport M § 11).

`scrape_cedh.py:51` ne demande que dix champs à HUDOC :
`itemid,docname,ecli,kpdate,doctype,article,conclusion,importance,respondent,
originatingbody_name`. Or le même endpoint, avec le même coût, en renvoie
beaucoup plus. Trois conséquences mesurées :

1. **`appno` est DEVINÉ.** Le numéro de requête en base n'a pas été moissonné :
   il est extrait du texte par trois regex
   (`scripts/prod-oneshot/extract_appno_cedh.py:10-26`) qui ne prennent que
   le PREMIER numéro trouvé dans les 3 000 premiers caractères. HUDOC donne
   `appno` officiel, propre, et multiple (« 68273/14;68271/14 »), plus
   `extractedappno` (les requêtes jointes). Ce script mesure et corrige.
2. **`originating_body` est vide en base — et la cause n'est pas chez nous.**
   `scrape_cedh.py:51` demande `originatingbody_name`. Mesuré le 8/09/2026 sur
   1 200 documents répartis de 1998 à 2023 : HUDOC renvoie ce champ VIDE dans
   100 % des cas. Le champ réellement rempli s'appelle `originatingbody`, et
   c'est un CODE NUMÉRIQUE (69 % de remplissage) :

       code 8  → 6/6 GRANDCHAMBER          code 17 → 236 EXECUTION + 88 MERITS
       codes 4,5,6,7,23 → CHAMBER/ADMISSIBILITY (sections)
       codes 25-29 → COMMITTEE/ADMISSIBILITYCOM      codes 3,21 → REPORTS

   Ce script écrit le CODE BRUT dans `originating_body` et garde les deux
   champs dans `cedh_meta`. ⚠️ La table de correspondance code → libellé
   officiel n'a PAS été trouvée publiée : la traduire serait de la devinette.
   Voir la section INVÉRIFIABLE du rapport O.
3. Treize champs ne sont jamais demandés : `kpthesaurus` (mots-clés du
   thésaurus HUDOC), `violation`, `nonviolation`, `scl` (jurisprudence citée,
   en clair, avec les paragraphes), `separateopinion`, `typedescription`,
   `judgementdate`, `decisiondate`, `introductiondate`, `representedby`,
   `applicability`, `rulesofcourt`, `externalsources`, `publishedby`,
   `doctypebranch`, `documentcollectionid`, `languageisocode`.

⚠️ Ce script NE RETÉLÉCHARGE AUCUN TEXTE. Il n'appelle jamais
`/app/conversion/docx/html/body` — l'endpoint qui est tombé le 29 août 2026 et
qui a mangé toute la fenêtre de moisson. Seul l'endpoint de liste est
sollicité, à raison d'une requête pour 20 à 100 documents.

Deux modes :
  * `--mode itemid` (défaut) : interroge HUDOC par lots d'`itemid` tirés de la
    base. Reprenable, idempotent, et c'est le seul mode qui garantit qu'on
    couvre exactement le stock existant.
  * `--mode dates` : balaye des tranches de dates (`kpdate`) — utile pour
    découvrir des documents ABSENTS de la base, pas seulement pour enrichir.

Sécurité d'écriture (règle du projet : jamais d'écrasement sans sauvegarde) :
  * `appno`/`appno_norm` deviné est copié dans `appno_avant` ET dans un CSV.gz
    avant d'être remplacé par la valeur officielle ;
  * `originating_body` n'est écrit que s'il est vide en base ;
  * `--dry-run` est le défaut.

Usage :
    # mesure : combien d'appno devinés diffèrent de l'officiel, sur 500 lignes
    python3 scripts/enrich_cedh_meta.py --db … --limit 500

    # écriture réelle, reprenable
    python3 scripts/enrich_cedh_meta.py --db … --apply

Lancement en prod, depuis /opt/justicelibre, par systemd-run (jamais nohup+&) :

    systemd-run --unit=jl-enrich-cedh \\
      /usr/bin/python3 /opt/justicelibre/scripts/enrich_cedh_meta.py \\
      --db /opt/justicelibre/dila/judiciaire.db --limit 0 --batch 20 --apply

    journalctl -u jl-enrich-cedh -f
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
from urllib.parse import quote

import httpx

DB_DEFAUT = "/opt/justicelibre/dila/judiciaire.db"
BASE = "https://hudoc.echr.coe.int"
USER_AGENT = "justicelibre/1.0 (+https://justicelibre.org)"

# Le `select` élargi. `itemid` en tête : c'est la clé de jointure.
SELECT = (
    "itemid,appno,extractedappno,kpthesaurus,doctypebranch,documentcollectionid,"
    "languageisocode,violation,nonviolation,scl,separateopinion,typedescription,"
    "judgementdate,decisiondate,introductiondate,representedby,applicability,"
    "rulesofcourt,externalsources,publishedby,originatingbody,originatingbody_name,"
    "docname,ecli,kpdate,doctype,article,conclusion,importance,respondent"
)

# Champs rangés dans `cedh_meta` (JSON). `appno` et `originatingbody` ont leur
# propre colonne ; `docname`/`ecli`/`kpdate`/… sont déjà en base.
CHAMPS_META = (
    "extractedappno", "kpthesaurus", "doctypebranch", "documentcollectionid",
    "languageisocode", "violation", "nonviolation", "scl", "separateopinion",
    "typedescription", "judgementdate", "decisiondate", "introductiondate",
    "representedby", "applicability", "rulesofcourt", "externalsources",
    "publishedby", "originatingbody", "originatingbody_name",
)

QUERY_BASE = ('contentsitename=ECHR AND '
              '(NOT (doctype=PR OR doctype=HFCOMOLD OR doctype=HECOMOLD)) AND '
              '((languageisocode="FRE"))')


def normalise_appno(appno: str) -> str:
    """Mêmes variantes que `extract_appno_cedh.py` : « 4143/02 4143-02 414302 ».

    HUDOC renvoie parfois plusieurs numéros séparés par « ; » — on normalise
    chacun, sinon la recherche par numéro rate toutes les affaires jointes.
    """
    if not appno:
        return ""
    morceaux = []
    for un in str(appno).split(";"):
        un = un.strip()
        if not un or "/" not in un:
            continue
        a, b = un.split("/", 1)
        morceaux += [un, f"{a}-{b}", f"{a}{b}"]
    return " ".join(dict.fromkeys(morceaux))


class ClientHudoc:
    """Client HUDOC poli : ≤ `max_par_sec` requêtes/s, réessai borné."""

    def __init__(self, max_par_sec: float = 2.0, essais: int = 3, timeout: float = 60.0):
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout)
        self.intervalle = 1.0 / max_par_sec if max_par_sec > 0 else 0.0
        self.essais = essais
        self._dernier = 0.0
        self.requetes = 0
        self.secondes = 0.0

    def liste(self, query: str, start: int = 0, length: int = 100) -> dict:
        attente = self.intervalle - (time.time() - self._dernier)
        if attente > 0:
            time.sleep(attente)
        url = (f"{BASE}/app/query/results?query={quote(query, safe='')}"
               f"&select={quote(SELECT, safe='')}"
               f"&sort={quote('itemid Ascending', safe='')}"
               f"&start={start}&length={length}")
        derniere = None
        for essai in range(self.essais):
            t0 = time.time()
            try:
                r = self.client.get(url)
                self._dernier = time.time()
                self.requetes += 1
                self.secondes += self._dernier - t0
                if r.status_code == 200:
                    return r.json()
                derniere = f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as exc:
                self._dernier = time.time()
                derniere = f"{type(exc).__name__}: {exc}"
            time.sleep(2 ** essai * 3)
        raise RuntimeError(f"HUDOC en échec après {self.essais} essais — {derniere}")

    def close(self) -> None:
        self.client.close()


def par_itemid(cli: ClientHudoc, itemids: list[str]) -> dict[str, dict]:
    """Un lot d'itemid → une requête. Les colonnes vides sont omises par HUDOC."""
    q = QUERY_BASE + " AND (" + " OR ".join('itemid="%s"' % i for i in itemids) + ")"
    data = cli.liste(q, start=0, length=max(len(itemids), 1))
    out = {}
    for res in data.get("results", []):
        col = res.get("columns", {})
        iid = col.get("itemid")
        if iid:
            out[iid] = col
    return out


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
    return {"dernier_itemid": "", "traites": 0}


def ecrire_etat(chemin: Path, etat: dict) -> None:
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, chemin)


def sauver(chemin: Path, lignes) -> None:
    neuf = not chemin.exists()
    with gzip.open(chemin, "at", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if neuf:
            w.writerow(["itemid", "appno_avant", "appno_norm_avant",
                        "appno_officiel", "originating_body_avant"])
        w.writerows(lignes)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DB_DEFAUT)
    p.add_argument("--table", default="cedh_decisions")
    p.add_argument("--apply", action="store_true", help="écrit réellement (défaut : dry-run)")
    p.add_argument("--mode", choices=["itemid", "dates"], default="itemid")
    p.add_argument("--limit", type=int, default=500, help="documents à traiter (0 = tout)")
    p.add_argument("--batch", type=int, default=20, help="itemid par requête HUDOC")
    p.add_argument("--annee-debut", type=int, default=1960, help="--mode dates")
    p.add_argument("--annee-fin", type=int, default=0, help="--mode dates (0 = année courante)")
    p.add_argument("--montrer", type=int, default=5)
    p.add_argument("--force", action="store_true")
    p.add_argument("--max-par-sec", type=float, default=2.0)
    p.add_argument("--state", default="")
    p.add_argument("--backup", default="")
    args = p.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[erreur] base introuvable : {db}")
        return 2
    etat_path = Path(args.state) if args.state else db.with_suffix(db.suffix + ".cedh_enrich.state.json")
    backup_path = Path(args.backup) if args.backup else db.with_suffix(db.suffix + ".cedh_enrich.backup.csv.gz")

    conn = sqlite3.connect(str(db), timeout=300.0)
    conn.execute("PRAGMA busy_timeout=300000")
    cibles = ["appno_avant", "appno_norm_avant", "cedh_meta"]
    if args.apply:
        conn.execute("PRAGMA journal_mode=WAL")
        print(f"[schéma] colonnes créées : "
              f"{ajouter_colonnes(conn, args.table, cibles) or '(aucune, déjà présentes)'}")
    else:
        existantes = {r[1] for r in conn.execute(f"PRAGMA table_info({args.table})")}
        print(f"[dry-run] ALTER TABLE ADD COLUMN prévus : "
              f"{[c for c in cibles if c not in existantes] or '(aucun)'}")

    existantes = {r[1] for r in conn.execute(f"PRAGMA table_info({args.table})")}
    a_meta = "cedh_meta" in existantes

    etat = charger_etat(etat_path)
    depuis = "" if args.force else etat.get("dernier_itemid", "")
    filtre = "" if (args.force or not a_meta) else " AND (cedh_meta IS NULL OR cedh_meta = '')"
    sql = (f"SELECT itemid, appno, appno_norm, originating_body FROM {args.table} "
           f"WHERE itemid > ?{filtre} ORDER BY itemid")
    params: list = [depuis]
    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)
    lignes = list(conn.execute(sql, params))
    if not lignes:
        print("Rien à traiter.")
        conn.close()
        return 0

    if args.mode == "dates":
        print("[info] --mode dates : le balayage par tranches de dates sert à "
              "DÉCOUVRIR des documents absents de la base ; l'enrichissement du "
              "stock existant passe par --mode itemid. Balayage :")
        cli = ClientHudoc(max_par_sec=args.max_par_sec)
        fin = args.annee_fin or time.localtime().tm_year
        for annee in range(args.annee_debut, fin + 1):
            q = (QUERY_BASE + f' AND (kpdate>="{annee}-01-01" AND kpdate<="{annee}-12-31")')
            data = cli.liste(q, start=0, length=1)
            print(f"    {annee} : resultcount={data.get('resultcount')}")
        cli.close()
        conn.close()
        return 0

    cli = ClientHudoc(max_par_sec=args.max_par_sec)
    t0 = time.time()
    montres = 0
    ecrits = 0
    stats = {"vus": 0, "hudoc_appno": 0, "appno_identique": 0, "appno_different": 0,
             "appno_tronque_1er_ok": 0, "appno_faux": 0,
             "appno_absent_base": 0, "appno_absent_hudoc": 0, "multi_appno": 0,
             "originating_body_recu": 0, "sans_reponse": 0}
    remplissage = {c: 0 for c in CHAMPS_META}
    lot: list[tuple] = []
    sauvegardes: list[list] = []
    dernier = depuis

    for debut in range(0, len(lignes), args.batch):
        tranche = lignes[debut:debut + args.batch]
        try:
            reponses = par_itemid(cli, [r[0] for r in tranche])
        except RuntimeError as exc:
            print(f"[abandon] {exc}")
            break
        for itemid, appno_base, appno_norm_base, orig_base in tranche:
            dernier = max(dernier, itemid)
            col = reponses.get(itemid)
            if not col:
                stats["sans_reponse"] += 1
                continue
            stats["vus"] += 1
            appno_off = (col.get("appno") or "").strip()
            # `originatingbody_name` est toujours vide côté HUDOC ; le champ
            # rempli est le code numérique `originatingbody` (cf. en-tête).
            orig_off = ((col.get("originatingbody") or "").strip()
                        or (col.get("originatingbody_name") or "").strip())
            for c in CHAMPS_META:
                if (col.get(c) or "").strip():
                    remplissage[c] += 1
            if appno_off:
                stats["hudoc_appno"] += 1
                if ";" in appno_off:
                    stats["multi_appno"] += 1
                if not (appno_base or "").strip():
                    stats["appno_absent_base"] += 1
                elif appno_base.strip() == appno_off:
                    stats["appno_identique"] += 1
                else:
                    stats["appno_different"] += 1
                    # Caractériser l'écart : la regex ne prend que le PREMIER
                    # numéro. Si le deviné est bien le premier de la liste
                    # officielle, la base est incomplète (affaires jointes
                    # perdues) ; sinon elle est carrément fausse.
                    if appno_base.strip() == appno_off.split(";")[0].strip():
                        stats["appno_tronque_1er_ok"] += 1
                    else:
                        stats["appno_faux"] += 1
            else:
                stats["appno_absent_hudoc"] += 1
            if orig_off and not (orig_base or "").strip():
                stats["originating_body_recu"] += 1

            meta_json = json.dumps(
                {c: (col.get(c) or "") for c in CHAMPS_META} |
                {"moissonne_le": time.strftime("%Y-%m-%d")},
                ensure_ascii=False, separators=(",", ":"))

            appno_ecrit = appno_off or (appno_base or "")
            norm_ecrit = normalise_appno(appno_off) if appno_off else (appno_norm_base or "")
            orig_ecrit = orig_base or orig_off

            if (appno_base or "").strip() and appno_base.strip() != appno_ecrit:
                sauvegardes.append([itemid, appno_base, appno_norm_base,
                                    appno_ecrit, orig_base])

            if montres < args.montrer:
                montres += 1
                marque = ("  ❗ DIFFÉRENT" if appno_off and (appno_base or "").strip()
                          and appno_base.strip() != appno_off else "")
                print(f"\n  --- {itemid}  {col.get('docname', '')[:60]}")
                print(f"      appno  base (regex) : {appno_base or '∅'}")
                print(f"      appno HUDOC officiel: {appno_off or '∅'}{marque}")
                print(f"      originating_body    : base={orig_base or '∅'} "
                      f"| hudoc={orig_off or '∅'}")
                print(f"      cedh_meta           : {meta_json[:400]}")

            if args.apply:
                lot.append((appno_ecrit, norm_ecrit, orig_ecrit,
                            appno_base or None, appno_norm_base or None,
                            meta_json, itemid))

        if args.apply and lot:
            conn.executemany(
                f"UPDATE {args.table} SET appno = ?, appno_norm = ?, "
                f"originating_body = ?, appno_avant = COALESCE(appno_avant, ?), "
                f"appno_norm_avant = COALESCE(appno_norm_avant, ?), cedh_meta = ? "
                f"WHERE itemid = ?", lot)
            if sauvegardes:
                sauver(backup_path, sauvegardes)
                sauvegardes = []
            conn.commit()
            ecrits += len(lot)
            lot = []
            etat.update({"dernier_itemid": dernier,
                         "traites": etat.get("traites", 0) + len(tranche)})
            ecrire_etat(etat_path, etat)
            print(f"    +{ecrits} écrits")

    dt = max(time.time() - t0, 0.001)
    n = len(lignes)
    print(f"\n=== {n} itemid en {dt:.1f}s — {cli.requetes} requêtes HUDOC "
          f"({cli.secondes / max(cli.requetes, 1):.2f}s/requête, {n / dt:.1f} doc/s)")
    for k, v in stats.items():
        print(f"    {k:24s} {v}")
    if stats["vus"]:
        print(f"\n  remplissage des {len(CHAMPS_META)} champs jetés "
              f"(sur {stats['vus']} documents reçus) :")
        for c in CHAMPS_META:
            print(f"    {c:22s} {remplissage[c]:5d}  {100 * remplissage[c] / stats['vus']:5.1f}%")
    if args.apply:
        print(f"écrits : {ecrits} — état : {etat_path} — sauvegarde : {backup_path}")
    else:
        print("DRY-RUN : aucune écriture. Ajouter --apply pour écrire.")
    cli.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
