"""Applique les nouvelles textes (id, texte) sur PROD judiciaire.db (table decisions, col text).

Usage : python3 apply_texte_judiciaire.py <tsv_file> [<tsv_file> ...]
"""
import sqlite3
import sys
import time
from pathlib import Path

DB = Path("/opt/justicelibre/dila/judiciaire.db")

def unescape_tsv(s: str) -> str:
    # Reverse of escape_tsv: \\n→newline, \\t→tab, \\\\→\
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i+1]
            if n == "n":
                out.append("\n"); i += 2; continue
            if n == "t":
                out.append("\t"); i += 2; continue
            if n == "\\":
                out.append("\\"); i += 2; continue
            if n == "r":
                out.append("\r"); i += 2; continue
        out.append(c)
        i += 1
    return "".join(out)


conn = sqlite3.connect(DB, timeout=300.0)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-524288")  # 512 MB
conn.execute("PRAGMA temp_store=MEMORY")

# Existence cache (one query, ~600k+7k+73k IDs)
print("Loading existing decision IDs from PROD…", flush=True)
t0 = time.time()
existing = {r[0] for r in conn.execute("SELECT id FROM decisions")}
print(f"  {len(existing)} ids loaded in {time.time()-t0:.1f}s", flush=True)

batch = []
n_total = 0
n_matched = 0
n_unmatched = 0
n_files = 0

UPDATE_SQL = "UPDATE decisions SET text=? WHERE id=?"

start = time.time()
for path in sys.argv[1:]:
    n_files += 1
    print(f"=== {path} ===", flush=True)
    n_file_matched = 0
    n_file_unmatched = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            n_total += 1
            line = line.rstrip("\n")
            if not line:
                continue
            tab = line.find("\t")
            if tab < 0:
                continue
            did = line[:tab]
            text_esc = line[tab+1:]
            if did not in existing:
                n_unmatched += 1
                n_file_unmatched += 1
                continue
            text = unescape_tsv(text_esc)
            batch.append((text, did))
            n_matched += 1
            n_file_matched += 1

            if len(batch) >= 1000:
                conn.executemany(UPDATE_SQL, batch)
                conn.commit()
                batch = []
                if n_matched % 50000 == 0:
                    elapsed = time.time() - start
                    rate = n_matched / elapsed
                    print(f"  [{n_matched:>8} updated / {n_unmatched} unmatched] {rate:.0f}/s ({elapsed/60:.1f}min)", flush=True)

    if batch:
        conn.executemany(UPDATE_SQL, batch)
        conn.commit()
        batch = []
    print(f"  [{path}] matched={n_file_matched} unmatched={n_file_unmatched}", flush=True)

    # Checkpoint WAL after each file to free disk space (PROD is tight)
    print("  Checkpoint(TRUNCATE)…", flush=True)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()

# Skip FTS5 rebuild — tokenization is whitespace-based, so newlines vs spaces
# produce the same tokens. The existing FTS5 index remains valid for search.
print("Skipping FTS5 rebuild (tokens unchanged — newlines == whitespace).", flush=True)

# Sample
sample = conn.execute(
    "SELECT id, length(text), instr(text, char(10)) FROM decisions WHERE id IN ('JURITEXT000050704069','CONSTEXT000017667265') LIMIT 5"
).fetchall()
for r in sample:
    print(f"  sample: id={r[0]} len={r[1]} first_newline_at={r[2]}", flush=True)

print(f"DONE: matched={n_matched} unmatched={n_unmatched} total_lines={n_total} files={n_files} time={time.time()-start:.0f}s", flush=True)
conn.close()
