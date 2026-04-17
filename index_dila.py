"""Index DILA XML archives into SQLite FTS5 for full-text search.

Usage: python3 index_dila.py /opt/justicelibre/dila /opt/justicelibre/dila/judiciaire.db
"""
import os
import re
import sys
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")


def clean_html(text: str) -> str:
    return TAG_RE.sub(" ", text).replace("\n", " ").strip()


def parse_decision(xml_path: str) -> dict | None:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError):
        return None

    meta = root.find(".//META_COMMUN")
    juri = root.find(".//META_JURI")
    judi = root.find(".//META_JURI_JUDI")
    contenu = root.find(".//CONTENU")

    if meta is None or juri is None:
        return None

    def get(parent, tag, default=""):
        el = parent.find(tag) if parent is not None else None
        return (el.text or "").strip() if el is not None else default

    text = clean_html(ET.tostring(contenu, encoding="unicode")) if contenu is not None else ""

    return {
        "id": get(meta, "ID"),
        "nature": get(meta, "NATURE"),
        "titre": get(juri, "TITRE"),
        "date": get(juri, "DATE_DEC"),
        "juridiction": get(juri, "JURIDICTION"),
        "solution": get(juri, "SOLUTION"),
        "numero": get(judi, ".//NUMERO_AFFAIRE") if judi is not None else "",
        "formation": get(judi, "FORMATION"),
        "ecli": get(judi, "ECLI"),
        "president": get(judi, "PRESIDENT"),
        "avocats": get(judi, "AVOCATS"),
        "text": text,
    }


def create_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            nature TEXT,
            titre TEXT,
            date TEXT,
            juridiction TEXT,
            solution TEXT,
            numero TEXT,
            formation TEXT,
            ecli TEXT,
            president TEXT,
            avocats TEXT,
            text TEXT
        )
    """)

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5(
            id UNINDEXED,
            titre,
            juridiction,
            solution,
            numero,
            formation,
            text,
            content='decisions',
            content_rowid='rowid'
        )
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN
            INSERT INTO decisions_fts(rowid, id, titre, juridiction, solution, numero, formation, text)
            VALUES (new.rowid, new.id, new.titre, new.juridiction, new.solution, new.numero, new.formation, new.text);
        END
    """)

    conn.commit()
    return conn


def index_directory(dila_dir: str, db_path: str):
    conn = create_db(db_path)
    cursor = conn.cursor()

    xml_files = list(Path(dila_dir).rglob("*.xml"))
    total = len(xml_files)
    print(f"Found {total} XML files to index")

    inserted = 0
    errors = 0
    batch = []

    for i, xml_path in enumerate(xml_files):
        decision = parse_decision(str(xml_path))
        if decision is None:
            errors += 1
            continue

        batch.append((
            decision["id"], decision["nature"], decision["titre"],
            decision["date"], decision["juridiction"], decision["solution"],
            decision["numero"], decision["formation"], decision["ecli"],
            decision["president"], decision["avocats"], decision["text"],
        ))

        if len(batch) >= 1000:
            cursor.executemany(
                "INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
            inserted += len(batch)
            batch = []
            if (i + 1) % 10000 == 0:
                print(f"  {i+1}/{total} processed ({inserted} inserted, {errors} errors)")

    if batch:
        cursor.executemany(
            "INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
        inserted += len(batch)

    print(f"\nDone: {inserted} decisions indexed, {errors} errors")
    print(f"Database: {db_path} ({os.path.getsize(db_path) / 1048576:.1f} MB)")

    # Verify
    count = cursor.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    print(f"Total in DB: {count}")

    # Test search
    results = cursor.execute(
        "SELECT id, titre, date FROM decisions_fts WHERE decisions_fts MATCH ? LIMIT 3",
        ("licenciement",)
    ).fetchall()
    print(f"\nTest search 'licenciement': {len(results)} results")
    for r in results:
        print(f"  {r[0]} | {r[2]} | {r[1][:80]}")

    conn.close()


if __name__ == "__main__":
    dila_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/justicelibre/dila"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/justicelibre/dila/judiciaire.db"
    index_directory(dila_dir, db_path)
