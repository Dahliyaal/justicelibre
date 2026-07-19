#!/usr/bin/env python3
"""Apply patch sur PROD : pour chaque (id, texte) du TSV, UPDATE decisions
SET text=? WHERE id=? AND (text IS NULL OR length(text)<100 OR instr(text, char(10))=0).

Le AND filtre safe : ne touche QUE les IDs actuellement no_lf ou vides
(n'écrase pas du PISTE déjà clean)."""
import gzip
import sqlite3
import sys

sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
TSV = "/tmp/decisions_patch.tsv.gz"

conn = sqlite3.connect(DB_PATH, timeout=120.0)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=120000")

read = 0
updated = 0
skipped = 0
batch = []

with gzip.open(TSV, "rt", encoding="utf-8") as f:
    for line in f:
        read += 1
        try:
            did, texte = line.rstrip("\n").split("\t", 1)
        except ValueError:
            continue
        # Restaure les caractères échappés
        texte = texte.replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")
        batch.append((texte, did))
        if len(batch) >= 1000:
            cur = conn.cursor()
            for txt, d in batch:
                cur.execute(
                    "UPDATE decisions SET text=? WHERE id=? "
                    "AND (text IS NULL OR length(text)<100 OR instr(text, char(10))=0)",
                    (txt, d),
                )
                if cur.rowcount > 0:
                    updated += 1
                else:
                    skipped += 1
            conn.commit()
            batch = []
        if read % 10000 == 0:
            print(f"  read={read} updated={updated} skipped={skipped}", flush=True)

# Flush last batch
if batch:
    cur = conn.cursor()
    for txt, d in batch:
        cur.execute(
            "UPDATE decisions SET text=? WHERE id=? "
            "AND (text IS NULL OR length(text)<100 OR instr(text, char(10))=0)",
            (txt, d),
        )
        if cur.rowcount > 0:
            updated += 1
        else:
            skipped += 1
    conn.commit()

print(f"\nDONE. read={read} updated={updated} skipped={skipped}")
conn.close()
