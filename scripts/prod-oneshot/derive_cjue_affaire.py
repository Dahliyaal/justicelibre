#!/usr/bin/env python3
"""Dérive numéro d'affaire CJUE (C-395/21) depuis le CELEX (62021CJ0395).
Ajoute colonne affaire_num + affaire_num_norm. Reconstruit FTS."""
import re, sqlite3, sys
sys.stdout.reconfigure(line_buffering=True)

DB = "/opt/justicelibre/dila/judiciaire.db"
TYPE_LETTER = {"CJ":"C", "TJ":"T", "FJ":"F", "CO":"C", "TO":"T", "CC":"C", "CB":"C"}


def derive_affaire(celex):
    if not celex:
        return None
    m = re.match(r"^6(\d{4})([A-Z]{2})(\d{4})", celex)
    if not m:
        return None
    year, typ, num = m.groups()
    type_letter = TYPE_LETTER.get(typ, typ[0])
    return f"{type_letter}-{int(num)}/{year[2:]}"


def normalize(affaire):
    """C-395/21 → 'C-395/21 C-395-21 C39521 C 395 21'"""
    if not affaire:
        return ""
    m = re.match(r"^([A-Z])-(\d+)/(\d+)$", affaire)
    if not m:
        return affaire
    letter, num, year = m.groups()
    return f"{letter}-{num}/{year} {letter}-{num}-{year} {letter}{num}{year} {letter} {num} {year}"


conn = sqlite3.connect(DB, timeout=300)
conn.execute("PRAGMA journal_mode=WAL")

for col in ["affaire_num", "affaire_num_norm"]:
    try:
        conn.execute(f"ALTER TABLE cjue_decisions ADD COLUMN {col} TEXT")
        print(f"Colonne {col} ajoutée")
    except sqlite3.OperationalError:
        pass

rows = conn.execute("SELECT celex FROM cjue_decisions WHERE affaire_num IS NULL OR affaire_num = ''").fetchall()
print(f"À traiter : {len(rows)}")

n = 0
batch = []
for (celex,) in rows:
    affaire = derive_affaire(celex)
    if affaire:
        batch.append((affaire, normalize(affaire), celex))
        n += 1
    if len(batch) >= 1000:
        conn.executemany(
            "UPDATE cjue_decisions SET affaire_num = ?, affaire_num_norm = ? WHERE celex = ?",
            batch
        )
        conn.commit()
        print(f"  {n} dérivés...")
        batch = []
if batch:
    conn.executemany(
        "UPDATE cjue_decisions SET affaire_num = ?, affaire_num_norm = ? WHERE celex = ?",
        batch
    )
    conn.commit()

conn.execute("CREATE INDEX IF NOT EXISTS idx_cjue_affaire ON cjue_decisions(affaire_num)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_cjue_affaire_norm ON cjue_decisions(affaire_num_norm)")

print("\nRebuild FTS...")
conn.executescript("""
DROP TABLE IF EXISTS cjue_fts;
CREATE VIRTUAL TABLE cjue_fts USING fts5(
    celex UNINDEXED, ecli, title, text, affaire_num_norm,
    content='cjue_decisions', content_rowid='rowid'
);
INSERT INTO cjue_fts(rowid, celex, ecli, title, text, affaire_num_norm)
SELECT rowid, celex, ecli, title, text, affaire_num_norm FROM cjue_decisions;
""")
conn.commit()
print(f"[done] {n} affaires dérivées, FTS reconstruit")

# Test
print("\nTest C-395/21 :")
for r in conn.execute("SELECT celex, title, date, affaire_num FROM cjue_decisions WHERE affaire_num_norm LIKE '%C-395/21%'").fetchall():
    print(f"  {r[0]} | {(r[1] or '')[:60]} | {r[2]} | {r[3]}")
conn.close()
