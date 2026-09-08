#!/usr/bin/env python3
"""Migration de schéma des bases DILA : ADD COLUMN, et rien d'autre.

Ce script prépare les bases existantes à recevoir le parseur réparé
(`parse_dila_bulk.py`, septembre 2026). Il **n'ajoute que des colonnes** :
aucun DROP, aucun RENAME, aucune modification de colonne existante, aucune
écriture de données, aucun rebuild d'index FTS5.

Pourquoi c'est sans danger pour le FTS5 : les triggers `_ai/_ad/_au` créés par
`parse_dila_bulk.py` nomment TOUTES leurs colonnes explicitement
(`INSERT INTO x_fts(rowid, id, …) VALUES (new.rowid, new.id, …)`). Un
`ALTER TABLE … ADD COLUMN` ne change donc ni leur définition, ni le nombre de
colonnes qu'ils écrivent. (Vérifié sur base de test : insert après migration →
la ligne est bien retrouvée par MATCH.)

Le script est **idempotent** (une colonne déjà présente est ignorée) et
**dry-run par défaut** : sans `--apply`, il n'ouvre les bases qu'en lecture et
se contente d'imprimer les ALTER qu'il exécuterait.

Usage :
    python3 scripts/migrate_schema_dila.py                     # dry-run, tous les fonds
    python3 scripts/migrate_schema_dila.py --fond kali         # dry-run, un fond
    python3 scripts/migrate_schema_dila.py --apply             # exécute
    python3 scripts/migrate_schema_dila.py --db-dir /chemin    # autre répertoire de bases
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parse_dila_bulk import (  # noqa: E402
    CNIL_NEW_COLS,
    JORF_NEW_COLS,
    JURIS_ENRICH_COLS,
    JURIS_NEW_COLS,
    KALI_NEW_COLS,
    LEGI_ART_NEW_COLS,
    LEGI_TXT_NEW_COLS,
)

DEFAULT_DB_DIR = Path("/opt/justicelibre/dila")

# fond → [(table, [(colonne, type), …]), …]
PLAN = {
    "legi": [("legi_articles", LEGI_ART_NEW_COLS),
             ("legi_textes", LEGI_TXT_NEW_COLS)],
    "jorf": [("jorf_textes", JORF_NEW_COLS)],
    "kali": [("kali_textes", KALI_NEW_COLS)],
    "cnil": [("cnil_deliberations", CNIL_NEW_COLS)],
    "jade": [("jade_decisions", JURIS_ENRICH_COLS + JURIS_NEW_COLS)],
    "cass": [("cass_decisions", JURIS_ENRICH_COLS + JURIS_NEW_COLS)],
    "capp": [("capp_decisions", JURIS_ENRICH_COLS + JURIS_NEW_COLS)],
    "inca": [("inca_decisions", JURIS_ENRICH_COLS + JURIS_NEW_COLS)],
    "constit": [("constit_decisions", JURIS_ENRICH_COLS + JURIS_NEW_COLS)],
}


def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def migrate(db_path: Path, tables, apply: bool):
    if not db_path.exists():
        print(f"  base absente : {db_path} — ignorée")
        return 0
    uri = f"file:{db_path}" + ("" if apply else "?mode=ro")
    conn = sqlite3.connect(uri, uri=True, timeout=120.0)
    n = 0
    try:
        for table, cols in tables:
            if not table_exists(conn, table):
                print(f"  table absente : {table} — ignorée")
                continue
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            manquantes = [(c, t) for c, t in cols if c not in existing]
            if not manquantes:
                print(f"  {table} : à jour ({len(existing)} colonnes)")
                continue
            for col, typ in manquantes:
                sql = f"ALTER TABLE {table} ADD COLUMN {col} {typ}"
                if apply:
                    conn.execute(sql)
                    print(f"  OK   {sql}")
                else:
                    print(f"  (dry-run) {sql}")
                n += 1
        if apply:
            conn.commit()
    finally:
        conn.close()
    return n


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="exécute réellement les ALTER (sans ce drapeau : dry-run)")
    p.add_argument("--fond", choices=sorted(PLAN), action="append",
                   help="limiter à un ou plusieurs fonds (défaut : tous)")
    p.add_argument("--db-dir", default=str(DEFAULT_DB_DIR),
                   help=f"répertoire des bases (défaut : {DEFAULT_DB_DIR})")
    args = p.parse_args()

    db_dir = Path(args.db_dir)
    fonds = args.fond or sorted(PLAN)
    mode = "APPLY" if args.apply else "DRY-RUN (aucune écriture)"
    print(f"migrate_schema_dila — {mode} — bases dans {db_dir}\n")
    total = 0
    for fond in fonds:
        print(f"[{fond}] {db_dir / (fond + '.db')}")
        total += migrate(db_dir / f"{fond}.db", PLAN[fond], args.apply)
    verbe = "ajoutée(s)" if args.apply else "à ajouter"
    print(f"\n{total} colonne(s) {verbe}.")
    if not args.apply and total:
        print("Relancer avec --apply pour exécuter.")


if __name__ == "__main__":
    main()
