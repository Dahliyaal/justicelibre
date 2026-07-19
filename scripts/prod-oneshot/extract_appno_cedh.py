#!/usr/bin/env python3
"""Extrait n° de requête CEDH (appno) depuis le texte des arrêts.
Ajoute colonne `appno` + `appno_norm` (variantes 4143/02, 4143-02, 414302).
Reconstruit FTS pour permettre la recherche par appno."""
import re, sqlite3, sys
sys.stdout.reconfigure(line_buffering=True)

DB = "/opt/justicelibre/dila/judiciaire.db"

# Pattern : "Requête n° 4143/02" / "Requête n o 4143/02" / "Requêtes n°s 4143/02 et 5678/03" etc.
APPNO_PATTERNS = [
    re.compile(r"Requ[êe]tes?\s+n\s*[o°ºs]+\s*(\d{1,6}/\d{2,4})", re.IGNORECASE),
    re.compile(r"appn?o\s*[:=]?\s*(\d{1,6}/\d{2,4})", re.IGNORECASE),
    re.compile(r"Application\s+n\s*[o°]\s*(\d{1,6}/\d{2,4})", re.IGNORECASE),
]


def extract_appno(text):
    if not text:
        return None
    for pat in APPNO_PATTERNS:
        m = pat.search(text[:3000])  # cherche dans le début (header)
        if m:
            return m.group(1)
    return None


def normalize(appno):
    if not appno or "/" not in appno:
        return ""
    a, b = appno.split("/", 1)
    return f"{appno} {a}-{b} {a}{b}"


conn = sqlite3.connect(DB, timeout=300)
conn.execute("PRAGMA journal_mode=WAL")

# Add columns
for col in ["appno", "appno_norm"]:
    try:
        conn.execute(f"ALTER TABLE cedh_decisions ADD COLUMN {col} TEXT")
        print(f"Colonne {col} ajoutée")
    except sqlite3.OperationalError:
        pass

rows = conn.execute(
    "SELECT itemid, text FROM cedh_decisions WHERE text IS NOT NULL AND length(text) > 200 AND (appno IS NULL OR appno = '')"
).fetchall()
print(f"À traiter : {len(rows)}")

n = 0
batch = []
for itemid, text in rows:
    appno = extract_appno(text)
    if appno:
        batch.append((appno, normalize(appno), itemid))
        n += 1
    if len(batch) >= 500:
        conn.executemany(
            "UPDATE cedh_decisions SET appno = ?, appno_norm = ? WHERE itemid = ?",
            batch
        )
        conn.commit()
        print(f"  {n} appno extraits...")
        batch = []
if batch:
    conn.executemany(
        "UPDATE cedh_decisions SET appno = ?, appno_norm = ? WHERE itemid = ?",
        batch
    )
    conn.commit()

conn.execute("CREATE INDEX IF NOT EXISTS idx_cedh_appno ON cedh_decisions(appno)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_cedh_appno_norm ON cedh_decisions(appno_norm)")
conn.commit()

# Rebuild FTS pour inclure appno_norm
print("\nRebuild FTS...")
conn.executescript("""
DROP TABLE IF EXISTS cedh_fts;
CREATE VIRTUAL TABLE cedh_fts USING fts5(
    itemid UNINDEXED, docname, article, conclusion, text, appno_norm,
    content='cedh_decisions', content_rowid='rowid'
);
INSERT INTO cedh_fts(rowid, itemid, docname, article, conclusion, text, appno_norm)
SELECT rowid, itemid, docname, article, conclusion, text, appno_norm FROM cedh_decisions;
""")
conn.commit()
print(f"[done] {n} appno extraits, FTS reconstruit")

# Test
print("\n=== Test recherche 4143/02 ===")
r = conn.execute(
    "SELECT itemid, docname, date, appno FROM cedh_decisions WHERE appno_norm LIKE '%4143/02%'"
).fetchall()
for row in r:
    print(f"  {row[0]} | {row[1][:60]} | {row[2]} | appno={row[3]}")
conn.close()
