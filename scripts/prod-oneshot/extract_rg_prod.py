#!/usr/bin/env python3
"""Extrait n° RG sur PROD judiciaire.db (table decisions qui contient CASS+CAPP+CONSTIT).
Cible uniquement les arrêts CA (juridiction LIKE '%appel%') pour ne pas casser Cass."""
import re, sqlite3, sys
sys.stdout.reconfigure(line_buffering=True)

DB = "/opt/justicelibre/dila/judiciaire.db"
RG_PATTERNS = [
    re.compile(r"N[°o]\s*R\.?G\.?\s*:?\s*(\d{2,4})[/\-\s]+(\d{4,7})", re.IGNORECASE),
    re.compile(r"R[.\s]?G[.\s]?\s*n[°o]?\s*:?\s*(\d{2,4})[/\-\s]+(\d{4,7})", re.IGNORECASE),
]

def extract(text):
    if not text: return None
    for pat in RG_PATTERNS:
        m = pat.search(text)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None

def normalize(rg):
    if not rg or "/" not in rg: return ""
    a, b = rg.split("/", 1)
    return f"{a}/{b} {a}-{b} {a}{b}"

conn = sqlite3.connect(DB, timeout=300)
conn.execute("PRAGMA journal_mode=WAL")

try:
    conn.execute("ALTER TABLE decisions ADD COLUMN numero_rg_norm TEXT")
    print("Colonne numero_rg_norm ajoutée")
except sqlite3.OperationalError:
    pass

# Cible : CA + Cass+CC qui n'ont pas de numero rempli
rows = conn.execute(
    "SELECT id, text FROM decisions WHERE juridiction LIKE '%appel%' AND (numero_rg_norm IS NULL OR numero_rg_norm = '')"
).fetchall()
print(f"À traiter (CA seulement) : {len(rows)}")

n = 0
batch = []
for did, txt in rows:
    rg = extract(txt)
    if rg:
        batch.append((rg, normalize(rg), did))
        n += 1
    if len(batch) >= 500:
        conn.executemany(
            "UPDATE decisions SET numero = COALESCE(NULLIF(numero,''), ?), numero_rg_norm = ? WHERE id = ?",
            batch
        )
        conn.commit()
        print(f"  {n} extraits...")
        batch = []
if batch:
    conn.executemany(
        "UPDATE decisions SET numero = COALESCE(NULLIF(numero,''), ?), numero_rg_norm = ? WHERE id = ?",
        batch
    )
    conn.commit()

conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_numero ON decisions(numero)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_rg_norm ON decisions(numero_rg_norm)")
conn.commit()

# Rebuild FTS pour inclure numero_rg_norm
print("Rebuild FTS...")
conn.executescript("""
DROP TABLE IF EXISTS decisions_fts;
CREATE VIRTUAL TABLE decisions_fts USING fts5(
    id UNINDEXED, titre, juridiction, solution, numero, formation, text, numero_rg_norm,
    content='decisions', content_rowid='rowid'
);
INSERT INTO decisions_fts(rowid, id, titre, juridiction, solution, numero, formation, text, numero_rg_norm)
SELECT rowid, id, titre, juridiction, solution, numero, formation, text, numero_rg_norm FROM decisions;
""")
conn.commit()
print(f"[done] {n} RG extraits, FTS reconstruit")
conn.close()
