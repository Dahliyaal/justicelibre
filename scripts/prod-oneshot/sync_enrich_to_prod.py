"""Synchronise un TSV (id, abstrats, resume, renvois, ...) vers la table
`decisions` de PROD judiciaire.db.

Utilise UPDATE en transactions de 5000 lignes avec checkpoint WAL régulier
pour ne pas gonfler le -wal au-delà de 500MB.

Schéma TSV attendu (header obligatoire) :
    id <TAB> abstrats <TAB> resume <TAB> renvois <TAB> publi_bull <TAB> rapporteur <TAB> liens_textes
ou la version étendue (CONSTIT/CAPP) :
    id <TAB> abstrats <TAB> resume <TAB> renvois <TAB> rapporteur <TAB> commissaire_gvt
        <TAB> type_rec <TAB> publi_recueil <TAB> publi_bull <TAB> nature_qualifiee
        <TAB> saisines <TAB> loi_def <TAB> liens_textes

Usage : python3 sync_enrich_to_prod.py <tsv_path> [--db /opt/justicelibre/dila/judiciaire.db]
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

ALL_EXTRA_COLS = [
    "sommaire", "abstrats", "resume", "renvois",
    "rapporteur", "commissaire_gvt",
    "type_rec", "publi_recueil", "publi_bull",
    "nature_qualifiee", "saisines", "loi_def", "liens_textes",
]


def ensure_columns(conn):
    cur = conn.execute("PRAGMA table_info(decisions)")
    existing = {row[1] for row in cur.fetchall()}
    added = []
    for col in ALL_EXTRA_COLS:
        if col not in existing:
            conn.execute(f"ALTER TABLE decisions ADD COLUMN {col} TEXT")
            added.append(col)
    if added:
        conn.commit()
        print(f"Added columns: {added}")
    else:
        print("Schema already has all columns.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tsv")
    p.add_argument("--db", default="/opt/justicelibre/dila/judiciaire.db")
    p.add_argument("--batch", type=int, default=5000)
    p.add_argument("--checkpoint-every", type=int, default=20000)
    args = p.parse_args()

    tsv_path = Path(args.tsv)
    if not tsv_path.exists():
        print(f"ERROR: {tsv_path} missing", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")  # 64 MB only - PROD has tight RAM
    conn.execute("PRAGMA temp_store=MEMORY")

    ensure_columns(conn)

    # Lire le header pour mapper les colonnes du TSV vers SQL
    with open(tsv_path, "r", encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")

    if header[0] != "id":
        print(f"ERROR: first column must be 'id', got {header[0]}", file=sys.stderr)
        sys.exit(1)

    cols_to_update = header[1:]
    for c in cols_to_update:
        if c not in ALL_EXTRA_COLS:
            print(f"WARN: column {c} not in known schema, skipping for safety")

    # Filtrer aux colonnes connues
    indexed_cols = [(i, c) for i, c in enumerate(cols_to_update) if c in ALL_EXTRA_COLS]
    if not indexed_cols:
        print("ERROR: no recognized columns to update", file=sys.stderr)
        sys.exit(1)

    set_clause = ", ".join(f"{c}=?" for _, c in indexed_cols)
    update_sql = f"UPDATE decisions SET {set_clause} WHERE id=?"

    print(f"UPDATE sql: SET {set_clause} WHERE id=?")
    print(f"Reading {tsv_path} ({tsv_path.stat().st_size / 2**20:.0f} MB)…")

    start = time.time()
    n_total = 0
    n_updated = 0
    n_missing = 0
    batch = []

    def flush():
        nonlocal batch, n_updated
        if not batch:
            return
        cur = conn.executemany(update_sql, batch)
        conn.commit()
        # SQLite executemany returns the cursor; rowcount = total touched (sum)
        # but in many builds it's -1 ; on s'en fiche, on compte côté Python
        n_updated += len(batch)
        batch = []

    with open(tsv_path, "r", encoding="utf-8") as f:
        next(f)  # skip header
        for line in f:
            row = line.rstrip("\n").split("\t")
            if len(row) < 2:
                continue
            did = row[0]
            if not did:
                continue
            try:
                vals = [(row[i+1] if i+1 < len(row) else "") for i, _ in indexed_cols]
            except IndexError:
                n_missing += 1
                continue
            # Restaurer les newlines depuis le marqueur ⏎ utilisé par enrich_dila
            vals = [v.replace(" ⏎ ", "\n") for v in vals]
            batch.append(tuple(vals) + (did,))
            n_total += 1
            if len(batch) >= args.batch:
                flush()
                if n_total % args.checkpoint_every == 0:
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    elapsed = time.time() - start
                    rate = n_total / elapsed
                    print(f"  [{n_total} rows / {rate:.0f}/s / {elapsed/60:.1f}min]")
        flush()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    elapsed = time.time() - start
    print(f"DONE. tsv_rows={n_total} db_updates={n_updated} missing={n_missing} time={elapsed/60:.1f}min")

    # Stats
    print("\nVerification:")
    for col in ("abstrats", "resume", "renvois"):
        if col in ALL_EXTRA_COLS:
            try:
                non_empty = conn.execute(
                    f"SELECT COUNT(*) FROM decisions WHERE {col} IS NOT NULL AND {col} != ''"
                ).fetchone()[0]
                print(f"  {col}: {non_empty} non-empty")
            except sqlite3.OperationalError:
                pass
    conn.close()


if __name__ == "__main__":
    main()
