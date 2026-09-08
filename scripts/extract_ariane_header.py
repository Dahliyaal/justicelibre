#!/usr/bin/env python3
"""ArianeWeb : extraire l'en-tête déjà présent dans `text` vers des colonnes.

Pourquoi ce script existe (8 septembre 2026, rapport M § 13). La table
`ariane_decisions` (121 405 lignes en prod) n'a que quatre colonnes :
`ariane_id`, `ariane_num`, `text`, `fetched_at`. Or les sept premières lignes
de CHAQUE `text` contiennent, en clair, la juridiction, le numéro de requête,
l'ECLI, la mention de publication au recueil Lebon, la formation, le président
et le rapporteur :

    Conseil d'État
    N° 327211
    ECLI:FR:CESSR:2009:327211.20090703
    Inédit au recueil Lebon
    Section du Contentieux
    M. Stirn, président
    M. Brice Bohuon, rapporteur

Rien n'est extrait : impossible de filtrer par date, de trouver un arrêt par
son numéro, ou de distinguer un « Publié au recueil Lebon » d'un inédit.

AUCUN RÉSEAU. La matière est déjà en base ; ce script ne fait que la ranger.

Le parseur n'est pas ici : il est dans `sources/ariane.py::parse_header`, celui
qu'utilisent déjà le MCP (`server.py:708`) et le site (`search_api.py:974`).
Le dupliquer, c'était exactement le bug du 23 août 2026 — deux extractions du
même en-tête, dont une vide (cf. `tests/test_ariane_header.py`).

Sécurité d'écriture (règle du projet : jamais d'écrasement sans sauvegarde) :
  * les colonnes sont créées par ALTER TABLE ADD COLUMN idempotent ;
  * une valeur existante NON VIDE et DIFFÉRENTE n'est jamais écrasée sans
    avoir été copiée dans `<colonne>_avant` ET dans un CSV.gz ;
  * `--dry-run` est le défaut, `--apply` est explicite.

Usage :
    # dry-run (défaut) sur 20 lignes, avec le détail
    python3 scripts/extract_ariane_header.py --db /chemin/base.db --limit 20

    # mesure du taux d'extraction sur 500 lignes, sans rien écrire
    python3 scripts/extract_ariane_header.py --db … --limit 500 --stats-only

    # écriture réelle, reprenable
    python3 scripts/extract_ariane_header.py --db … --apply

Lancement en prod, depuis /opt/justicelibre, par systemd-run (jamais nohup+&) :

    systemd-run --unit=jl-ariane-entetes \\
      /usr/bin/python3 /opt/justicelibre/scripts/extract_ariane_header.py \\
      --db /opt/justicelibre/dila/judiciaire.db --limit 0 --apply

    journalctl -u jl-ariane-entetes -f
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

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from sources import ariane  # noqa: E402

DB_DEFAUT = "/opt/justicelibre/dila/judiciaire.db"

# Colonnes cibles → clé renvoyée par parse_header.
# `juridiction` et `rapporteur_public` s'ajoutent aux sept colonnes demandées :
# la première parce que la juridiction fait partie de l'en-tête extrait, la
# seconde parce que sans elle « M. X, rapporteur public » finirait dans
# `rapporteur` — c'est-à-dire une autre personne dans la colonne du magistrat
# rapporteur.
COLONNES = {
    "numero": "numero",
    "ecli": "ecli",
    "date": "date",
    "formation": "formation",
    "publication": "publication",
    "president": "president",
    "rapporteur": "rapporteur",
    "juridiction": "juridiction",
    "rapporteur_public": "rapporteur_public",
}


def ajouter_colonnes(conn: sqlite3.Connection, table: str, colonnes) -> list[str]:
    """ALTER TABLE ADD COLUMN idempotent. Renvoie les colonnes créées."""
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
    return {"dernier_num": -1, "lus": 0, "ecrits": 0}


def ecrire_etat(chemin: Path, etat: dict) -> None:
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, chemin)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DB_DEFAUT)
    p.add_argument("--table", default="ariane_decisions")
    p.add_argument("--apply", action="store_true",
                   help="écrit réellement (défaut : dry-run)")
    p.add_argument("--limit", type=int, default=20,
                   help="nombre de lignes à traiter (0 = tout)")
    p.add_argument("--montrer", type=int, default=5,
                   help="nombre de lignes détaillées affichées en dry-run")
    p.add_argument("--stats-only", action="store_true",
                   help="n'affiche que le tableau des taux d'extraction")
    p.add_argument("--force", action="store_true",
                   help="retraite les lignes déjà renseignées")
    p.add_argument("--state", default="",
                   help="fichier d'état pour la reprise (défaut : <db>.ariane_header.state.json)")
    p.add_argument("--backup", default="",
                   help="CSV.gz de sauvegarde des valeurs écrasées "
                        "(défaut : <db>.ariane_header.backup.csv.gz)")
    p.add_argument("--commit-every", type=int, default=2000)
    args = p.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[erreur] base introuvable : {db}")
        return 2
    etat_path = Path(args.state) if args.state else db.with_suffix(db.suffix + ".ariane_header.state.json")
    backup_path = Path(args.backup) if args.backup else db.with_suffix(db.suffix + ".ariane_header.backup.csv.gz")

    conn = sqlite3.connect(str(db), timeout=300.0)
    conn.execute("PRAGMA busy_timeout=300000")

    cibles = list(COLONNES)
    if args.apply:
        conn.execute("PRAGMA journal_mode=WAL")
        creees = ajouter_colonnes(conn, args.table, cibles + [c + "_avant" for c in cibles])
        print(f"[schéma] colonnes créées : {creees or '(aucune, déjà présentes)'}")
    else:
        existantes = {r[1] for r in conn.execute(f"PRAGMA table_info({args.table})")}
        manquantes = [c for c in cibles if c not in existantes]
        print(f"[dry-run] ALTER TABLE ADD COLUMN prévus : {manquantes or '(aucun)'}")
        print(f"[dry-run] + colonnes de sauvegarde : {[c + '_avant' for c in manquantes]}")

    existantes = {r[1] for r in conn.execute(f"PRAGMA table_info({args.table})")}
    lisibles = [c for c in cibles if c in existantes]

    etat = charger_etat(etat_path)
    depuis = etat.get("dernier_num", -1) if not args.force else -1

    select_cols = ", ".join(["ariane_id", "ariane_num", "text"] + lisibles)
    filtre = ""
    if lisibles and not args.force:
        # Idempotence : on ne repasse pas sur une ligne déjà renseignée.
        filtre = " AND (numero IS NULL OR numero = '')" if "numero" in lisibles else ""
    sql = (f"SELECT {select_cols} FROM {args.table} "
           f"WHERE ariane_num > ?{filtre} ORDER BY ariane_num")
    params: list = [depuis]
    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)

    t0 = time.time()
    lus = 0
    ecrits = 0
    ecrases = 0
    taux = {c: 0 for c in cibles}
    lot: list[tuple] = []
    sauvegardes: list[list] = []
    montres = 0
    dernier_num = depuis

    set_clause = ", ".join(f"{c} = ?" for c in cibles)
    # `<col>_avant` ne se remplit qu'une fois : COALESCE garde la toute
    # première valeur connue, même si le script repasse plusieurs fois.
    set_avant = ", ".join(f"{c}_avant = COALESCE({c}_avant, ?)" for c in cibles)
    sql_update = (f"UPDATE {args.table} SET {set_clause}, {set_avant} "
                  f"WHERE ariane_id = ?")

    for row in conn.execute(sql, params):
        aid, anum, text = row[0], row[1], row[2]
        anciennes = dict(zip(lisibles, row[3:]))
        lus += 1
        dernier_num = anum
        h = ariane.parse_header(text or "")
        for cle in h:
            if cle in taux:
                taux[cle] += 1
        valeurs = [h.get(c, "") for c in cibles]
        # Sauvegarde : toute valeur existante non vide et différente.
        avant = []
        ligne_ecrasee = False
        for c in cibles:
            vieux = (anciennes.get(c) or "")
            # NULL et non "" : `<col>_avant` doit dire « il n'y avait rien »,
            # pas « il y avait du vide » — sinon on ne sait plus, en relisant
            # la sauvegarde, ce qui a réellement été écrasé.
            avant.append(vieux or None)
            if vieux and vieux != h.get(c, ""):
                ligne_ecrasee = True
        if ligne_ecrasee:
            ecrases += 1
            sauvegardes.append([aid] + avant)
        if montres < args.montrer and not args.stats_only:
            montres += 1
            print(f"\n  --- {aid}  (ariane_num={anum})")
            print(f"      en-tête source : {ariane.entete(text or '')[:200]!r}")
            for c in cibles:
                print(f"      {c:18s} = {h.get(c, '') or '∅'}")
        if args.apply:
            lot.append(tuple(valeurs) + tuple(avant) + (aid,))
            if len(lot) >= args.commit_every:
                conn.executemany(sql_update, lot)
                if sauvegardes:
                    _sauver(backup_path, cibles, sauvegardes)
                    sauvegardes = []
                conn.commit()
                ecrits += len(lot)
                lot = []
                etat.update({"dernier_num": dernier_num, "lus": etat.get("lus", 0) + args.commit_every})
                ecrire_etat(etat_path, etat)
                print(f"    +{ecrits} écrits ({lus / max(time.time() - t0, 0.001):.0f} l/s)")

    if args.apply and lot:
        conn.executemany(sql_update, lot)
        if sauvegardes:
            _sauver(backup_path, cibles, sauvegardes)
        conn.commit()
        ecrits += len(lot)
        etat.update({"dernier_num": dernier_num, "lus": etat.get("lus", 0) + lus,
                     "ecrits": etat.get("ecrits", 0) + ecrits})
        ecrire_etat(etat_path, etat)

    dt = max(time.time() - t0, 0.001)
    print(f"\n=== {lus} lignes lues en {dt:.1f}s ({lus / dt:.0f} lignes/s)")
    if lus:
        print(f"{'champ':20s} {'extraits':>8s} {'taux':>7s}")
        for c in cibles:
            print(f"{c:20s} {taux[c]:8d} {100 * taux[c] / lus:6.1f}%")
    print(f"valeurs préexistantes qui auraient été écrasées : {ecrases} "
          f"(sauvegardées dans {backup_path} et dans les colonnes <col>_avant)")
    if args.apply:
        print(f"écrits : {ecrits} — état : {etat_path}")
    else:
        print("DRY-RUN : aucune écriture. Ajouter --apply pour écrire.")
    conn.close()
    return 0


def _sauver(chemin: Path, cibles, lignes) -> None:
    """Ajoute les valeurs écrasées à un CSV.gz (en-tête écrit une seule fois)."""
    neuf = not chemin.exists()
    with gzip.open(chemin, "at", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if neuf:
            w.writerow(["ariane_id"] + list(cibles))
        w.writerows(lignes)


if __name__ == "__main__":
    sys.exit(main())
