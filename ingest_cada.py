#!/usr/bin/env python3
"""Ingest CADA depuis le CSV consolidé de data.gouv.fr.

Version corrigée du 8 septembre 2026 (rapport M § 14.a). Le script d'origine
vit sur al-uzza (`/opt/justicelibre/ingest_cada.py`) et présente trois défauts :

1. **L'URL est morte.** Elle est codée en dur sur un nom de fichier DATÉ
   (`…/20260409-143148/cada-2026-04-09.csv`) : chaque republication du jeu de
   données par la CADA change le chemin et l'ancien renvoie 404 (vérifié). Le
   script échouait donc en silence à chaque nouvelle version.
   ▸ Correctif : on passe par l'API data.gouv
   `https://www.data.gouv.fr/api/1/datasets/avis-et-conseils-de-la-cada/`,
   on y repère la ressource consolidée, et on télécharge par son PERMALIEN
   `https://www.data.gouv.fr/api/1/datasets/r/<id de ressource>` — un
   identifiant qui, lui, ne bouge pas d'une republication à l'autre.

2. **`Partie` n'était jamais lu.** C'est la partie du code des relations entre
   le public et l'administration sous laquelle l'avis est rendu (I à IV).
   Constaté sur le CSV d'août 2026 : rempli à 96,3 % (58 713 / 60 941).
   ▸ Correctif : nouvelle colonne `partie`.

3. **`Objet` était déclaré « toujours vide » sans revérification.** Le rapport M
   classait ce point INVÉRIFIABLE.
   ▸ Vérifié le 8/09/2026 sur `cada-2026-08-14.csv`, les 60 941 lignes :
     **Objet est vide 60 941 fois sur 60 941 — le constat du 10/05/2026 tient.**
     Le script le lit tout de même et bascule sur lui pour le `titre` le jour
     où la CADA le remplira ; l'option `--audit-objet` recompte et le dit.

Le `titre` reste fabriqué (« Avis CADA — administration — thème (date) »)
puisque la source n'en fournit aucun.

Sécurité d'écriture : `--dry-run` est le défaut, les colonnes sont créées par
ALTER TABLE ADD COLUMN idempotent, et un `INSERT OR REPLACE` sur une ligne
existante sauvegarde d'abord la ligne remplacée dans un CSV.gz.

Usage :
    # dry-run : montre 3 lignes et l'audit du champ Objet, n'écrit rien
    python3 ingest_cada.py --dry-run --montrer 3

    # depuis un CSV déjà téléchargé (aucun réseau)
    python3 ingest_cada.py --csv data-cada/cada-2026-08-14.csv --dry-run

    # ingestion réelle
    python3 ingest_cada.py --db /opt/justicelibre/dila/doctrine.db --apply

⚠️ `doctrine.db` est sur **al-uzza** (46.224.173.253), pas sur la prod : c'est
donc là que ce script tourne. Lancement par systemd-run (jamais nohup+&) :

    systemd-run --unit=jl-ingest-cada \\
      /usr/bin/python3 /opt/justicelibre/ingest_cada.py \\
      --db /opt/justicelibre/dila/doctrine.db --apply

    journalctl -u jl-ingest-cada -f
"""
from __future__ import annotations

import argparse
import csv
import gzip
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

DB_DEFAUT = "/opt/justicelibre/dila/doctrine.db"
DATASET = "avis-et-conseils-de-la-cada"
API_DATASET = f"https://www.data.gouv.fr/api/1/datasets/{DATASET}/"
# Permalien de la ressource « Ensemble consolidé des avis et conseils de la
# CADA ». Sert de repli si l'API est indisponible ou si son libellé change :
# l'identifiant de ressource, lui, survit aux republications.
RESSOURCE_CONSOLIDEE = "3a6d6fe3-8548-43ed-ad09-72052771447c"
PERMALIEN = "https://www.data.gouv.fr/api/1/datasets/r/%s"
USER_AGENT = "justicelibre/1.0 (+https://justicelibre.org)"

# Colonnes ajoutées à `docs` par ce script.
COLONNES_NEUVES = ("partie", "objet")


def resoudre_url(verbose: bool = True) -> str:
    """Trouve le permalien de la ressource consolidée via l'API data.gouv.

    On ne cherche PAS un nom de fichier : il est daté et change à chaque
    publication. On cherche la ressource dont le titre parle de l'ensemble
    consolidé ; à défaut, on retombe sur l'identifiant épinglé.
    """
    import json
    req = urllib.request.Request(API_DATASET, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:                    # réseau, JSON, 5xx
        if verbose:
            print(f"[avertissement] API data.gouv injoignable ({exc}) — "
                  f"repli sur le permalien épinglé")
        return PERMALIEN % RESSOURCE_CONSOLIDEE
    candidats = []
    for res in data.get("resources", []):
        titre = (res.get("title") or "").lower()
        if res.get("format") != "csv":
            continue
        if "consolid" in titre or res.get("id") == RESSOURCE_CONSOLIDEE:
            candidats.append(res)
    if not candidats:
        if verbose:
            print("[avertissement] aucune ressource « consolidée » trouvée — "
                  "repli sur le permalien épinglé")
        return PERMALIEN % RESSOURCE_CONSOLIDEE
    res = max(candidats, key=lambda r: r.get("filesize") or 0)
    if verbose:
        print(f"[data.gouv] ressource « {res.get('title')} » "
              f"({(res.get('filesize') or 0) / 1e6:.0f} Mo, "
              f"modifiée {res.get('last_modified')})")
        print(f"[data.gouv] fichier courant : {res.get('url')}")
    return PERMALIEN % res["id"]


def telecharger(url: str, vers: Path) -> Path:
    print(f"[dl] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(vers, "wb") as f:
        total = 0
        while True:
            morceau = r.read(1 << 20)
            if not morceau:
                break
            f.write(morceau)
            total += len(morceau)
    print(f"[dl] {total / 1e6:.1f} Mo → {vers}")
    return vers


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


def ligne_vers_doc(row: dict) -> tuple | None:
    doc_id = (row.get("Numéro de dossier") or "").strip()
    if not doc_id:
        return None
    admin = (row.get("Administration") or "").strip()
    theme_full = (row.get("Thème et sous thème") or "").strip()
    theme_court = theme_full.split("/")[0].strip()
    date = (row.get("Séance") or row.get("Année") or "").strip()
    type_avis = (row.get("Type") or "Avis").strip()
    objet = (row.get("Objet") or "").strip()
    partie = (row.get("Partie") or "").strip()
    # Le jour où la CADA remplira « Objet », c'est LUI le titre : un intitulé
    # réel vaut mieux qu'un intitulé fabriqué.
    if objet:
        titre = objet[:300]
    else:
        bits = [type_avis, "CADA"]
        if admin:
            bits += ["—", admin[:80]]
        if theme_court:
            bits += ["—", theme_court]
        if date:
            bits.append(f"({date})")
        titre = " ".join(bits)[:300]
    sujet = (theme_full + " | " + (row.get("Mots clés") or "")).strip(" |")
    contenu = ((row.get("Avis") or "") + "\n\n--- Sens et motivation ---\n" +
               (row.get("Sens et motivation") or "")).strip()
    tags = (row.get("Mots clés") or "").strip()
    url = f"https://www.cada.fr/avis/{doc_id}"
    return ("cada", doc_id, type_avis, titre, date[:10] if date else "",
            admin, sujet, contenu, tags, url, partie, objet)


COLONNES_INSERT = ("source_id", "doc_id", "type", "titre", "date",
                   "administration", "sujet", "contenu", "tags", "source_url",
                   "partie", "objet")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DB_DEFAUT)
    p.add_argument("--csv", default="", help="CSV local déjà téléchargé (aucun réseau)")
    p.add_argument("--apply", action="store_true", help="écrit réellement (défaut : dry-run)")
    p.add_argument("--dry-run", action="store_true", help="(défaut) n'écrit rien")
    p.add_argument("--montrer", type=int, default=3)
    p.add_argument("--limit", type=int, default=0, help="n'ingérer que N lignes (0 = tout)")
    p.add_argument("--audit-objet", action="store_true",
                   help="compte les lignes où Objet/Partie sont vides et s'arrête")
    p.add_argument("--tmp", default="/tmp/cada.csv")
    p.add_argument("--backup", default="",
                   help="CSV.gz des lignes `docs` remplacées "
                        "(défaut : <db>.cada.backup.csv.gz)")
    args = p.parse_args()

    if args.csv:
        chemin = Path(args.csv)
        if not chemin.exists():
            print(f"[erreur] CSV introuvable : {chemin}")
            return 2
        print(f"[csv] source locale : {chemin} ({chemin.stat().st_size / 1e6:.1f} Mo)")
    else:
        chemin = telecharger(resoudre_url(), Path(args.tmp))

    with open(chemin, encoding="utf-8", errors="replace", newline="") as f:
        entetes = next(csv.reader(f))
    print(f"[csv] colonnes : {entetes}")
    for attendu in ("Objet", "Partie", "Numéro de dossier"):
        if attendu not in entetes:
            print(f"[erreur] colonne « {attendu} » absente du CSV — schéma changé, "
                  f"on s'arrête plutôt que d'ingérer de travers.")
            return 3

    if args.audit_objet:
        n = vides_objet = vides_partie = 0
        with open(chemin, encoding="utf-8", errors="replace", newline="") as f:
            for row in csv.DictReader(f):
                n += 1
                if not (row.get("Objet") or "").strip():
                    vides_objet += 1
                if not (row.get("Partie") or "").strip():
                    vides_partie += 1
        print(f"\n[audit] {n} lignes")
        print(f"[audit] Objet  vide : {vides_objet} ({100 * vides_objet / max(n, 1):.1f} %)")
        print(f"[audit] Partie vide : {vides_partie} ({100 * vides_partie / max(n, 1):.1f} %)")
        return 0

    db = Path(args.db)
    ecrire = args.apply and not args.dry_run
    conn = None
    if db.exists():
        conn = sqlite3.connect(str(db), timeout=300.0)
        conn.execute("PRAGMA busy_timeout=300000")
        if ecrire:
            print(f"[schéma] colonnes créées : "
                  f"{ajouter_colonnes(conn, 'docs', COLONNES_NEUVES) or '(aucune)'}")
        else:
            existantes = {r[1] for r in conn.execute("PRAGMA table_info(docs)")}
            print(f"[dry-run] ALTER TABLE ADD COLUMN prévus : "
                  f"{[c for c in COLONNES_NEUVES if c not in existantes] or '(aucun)'}")
    elif ecrire:
        print(f"[erreur] base introuvable : {db}")
        return 2
    else:
        print(f"[dry-run] base absente ({db}) — lecture du CSV seule")

    backup_path = (Path(args.backup) if args.backup
                   else (db.with_suffix(db.suffix + ".cada.backup.csv.gz")
                         if db.exists() else Path("/tmp/cada.backup.csv.gz")))

    if ecrire:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "INSERT OR REPLACE INTO sources (source_id, name, organisme, url, "
            "license, last_sync) VALUES (?,?,?,?,?, datetime('now'))",
            ("cada", "Avis et conseils de la CADA",
             "Commission d'accès aux documents administratifs",
             "https://www.cada.fr", "Licence Ouverte 2.0 (Etalab)"))

    marques = ",".join("?" * len(COLONNES_INSERT))
    sql = (f"INSERT OR REPLACE INTO docs ({', '.join(COLONNES_INSERT)}) "
           f"VALUES ({marques})")

    n = montres = remplaces = 0
    vides_objet = vides_partie = 0
    lot: list[tuple] = []
    with open(chemin, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            doc = ligne_vers_doc(row)
            if doc is None:
                continue
            n += 1
            if not doc[-1]:
                vides_objet += 1
            if not doc[-2]:
                vides_partie += 1
            if montres < args.montrer:
                montres += 1
                print(f"\n  --- ligne {n}")
                for cle, val in zip(COLONNES_INSERT, doc):
                    affiche = (val or "∅")
                    print(f"      {cle:14s} = {affiche[:160]}"
                          f"{'…' if len(affiche) > 160 else ''}")
            if ecrire:
                ancienne = conn.execute(
                    "SELECT * FROM docs WHERE source_id='cada' AND doc_id=?",
                    (doc[1],)).fetchone()
                if ancienne is not None:
                    remplaces += 1
                    _sauver(backup_path, ancienne)
                lot.append(doc)
                if len(lot) >= 1000:
                    conn.executemany(sql, lot)
                    conn.commit()
                    lot = []
                    print(f"  {n} ingérés…")
            if args.limit and n >= args.limit:
                break
    if ecrire and lot:
        conn.executemany(sql, lot)
        conn.commit()

    print(f"\n=== {n} avis CADA lus")
    print(f"    Objet  vide : {vides_objet} ({100 * vides_objet / max(n, 1):.1f} %)")
    print(f"    Partie vide : {vides_partie} ({100 * vides_partie / max(n, 1):.1f} %)")
    if ecrire:
        print(f"    lignes remplacées (sauvegardées dans {backup_path}) : {remplaces}")
    else:
        print("DRY-RUN : aucune écriture. Ajouter --apply pour écrire.")
    if conn is not None:
        conn.close()
    return 0


def _sauver(chemin: Path, ligne) -> None:
    neuf = not chemin.exists()
    with gzip.open(chemin, "at", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if neuf:
            w.writerow(["ligne docs remplacée (ordre des colonnes de la table)"])
        w.writerow(list(ligne))


if __name__ == "__main__":
    sys.exit(main())
