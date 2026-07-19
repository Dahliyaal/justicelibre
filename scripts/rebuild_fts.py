#!/usr/bin/env python3
"""Reconstruit les index FTS5 pour purger les orphelins historiques.

À lancer UNE FOIS après déploiement du correctif « triggers FTS5 + PRAGMA
recursive_triggers ». Avant le correctif, chaque ré-importation (INSERT OR
REPLACE) laissait des entrées FTS orphelines pointant des rowids disparus —
recherche corrompue, voire crash `fts5: missing row from content table`. Le
correctif empêche l'accumulation future ; ce script nettoie l'existant.

Idempotent et sûr : `INSERT INTO <fts>(<fts>) VALUES('rebuild')` reconstruit
l'index depuis la table de contenu. Coûteux sur les gros fonds (legi, jade) —
prévoir plusieurs minutes, à lancer hors des heures de parse.

Usage :
    python3 scripts/rebuild_fts.py                 # tous les fonds
    python3 scripts/rebuild_fts.py --db /opt/justicelibre/dila/legi.db
    python3 scripts/rebuild_fts.py --dry-run       # liste sans reconstruire
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time

# (chemin de la base, tables FTS à reconstruire). Chemins par défaut de la
# prod al-uzza — surchargeables via --db / la variable JL_DILA_DIR.
DILA_DIR = os.environ.get("JL_DILA_DIR", "/opt/justicelibre/dila")

FONDS = {
    "legi.db":       ["legi_articles_fts"],
    "jorf.db":       ["jorf_fts"],
    "kali.db":       ["kali_fts"],
    "cnil.db":       ["cnil_fts"],
    "jade.db":       ["jade_fts"],
    "judiciaire.db": ["decisions_fts", "cedh_fts", "cjue_fts", "ariane_fts", "articles_fts"],
    "opendata.db":   ["opendata_fts"],
}


def _fts_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%USING fts5%'"
    ).fetchall()
    return {r[0] for r in rows}


def rebuild_db(path: str, wanted: list[str], dry_run: bool) -> int:
    if not os.path.exists(path):
        print(f"  – {path} : absent, skip")
        return 0
    conn = sqlite3.connect(path, timeout=300.0)
    try:
        present = _fts_tables(conn)
        done = 0
        for fts in wanted:
            if fts not in present:
                print(f"  – {os.path.basename(path)}:{fts} : table absente, skip")
                continue
            if dry_run:
                print(f"  · {os.path.basename(path)}:{fts} : serait reconstruit")
                continue
            t0 = time.monotonic()
            conn.execute(f"INSERT INTO {fts}({fts}) VALUES('rebuild')")
            conn.commit()
            # Vérifie l'intégrité après reconstruction.
            conn.execute(f"INSERT INTO {fts}({fts}) VALUES('integrity-check')")
            print(f"  ✓ {os.path.basename(path)}:{fts} "
                  f"reconstruit + intègre ({time.monotonic() - t0:.1f}s)")
            done += 1
        return done
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", help="reconstruire une seule base (chemin complet)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.db:
        name = os.path.basename(args.db)
        targets = {args.db: FONDS.get(name, [])}
        if not targets[args.db]:
            print(f"Base inconnue : {name}. Fonds connus : {', '.join(FONDS)}",
                  file=sys.stderr)
            return 2
    else:
        targets = {os.path.join(DILA_DIR, name): tabs for name, tabs in FONDS.items()}

    total = 0
    for path, tabs in targets.items():
        total += rebuild_db(path, tabs, args.dry_run)
    print(f"\n{'(dry-run) ' if args.dry_run else ''}{total} index reconstruit(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
