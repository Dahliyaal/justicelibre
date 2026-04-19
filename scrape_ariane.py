#!/usr/bin/env python3 -u
"""Scrape ArianeWeb (Conseil d'État) en aspirant les ~270k décisions
via le plugin Sinequa downloadFilePagePlugin.

Strategy : énumérer les IDs internes ArianeWeb /Ariane_Web/AW_DCE/|N
de 1 à START_MAX, fetch le texte pour chaque, skip ceux déjà en DB.

Circuit breaker : si N erreurs consécutives, on stoppe le script.
"""
import html as _html
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
DOWNLOAD_URL = "https://www.conseil-etat.fr/plugin"
USER_AGENT = "justicelibre.org/1.0 (open data, contact: dahliyaal@justicelibre.org)"
SLEEP_BETWEEN_REQUESTS = 0.30  # 3 req/s, polite
MAX_CONSECUTIVE_ERRORS = 30    # circuit breaker (erreurs réseau/500)
# Plage d'IDs actifs ArianeWeb observée par probing :
#   id=50000    → 404
#   id=100000   → 200
#   id=219809   → 200
#   id=250000   → 404
# On balaie 95000 → 235000 avec tolérance aux gros trous (5000 404 consécutifs)
START_ID = 95_000
END_ID = 235_000
MAX_CONSECUTIVE_404 = 5_000    # on tolère de gros trous dans la numérotation

CHECKPOINT_FILE = "/tmp/scrape_ariane.checkpoint"


def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ariane_decisions (
        ariane_id TEXT PRIMARY KEY,        -- /Ariane_Web/AW_DCE/|NNNNNN
        ariane_num INTEGER,                -- juste le NNNNNN
        text TEXT,
        fetched_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_ariane_num ON ariane_decisions(ariane_num);
    CREATE VIRTUAL TABLE IF NOT EXISTS ariane_fts USING fts5(
        ariane_id UNINDEXED, text,
        content='ariane_decisions', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS ariane_ai AFTER INSERT ON ariane_decisions BEGIN
        INSERT INTO ariane_fts(rowid, ariane_id, text)
        VALUES (new.rowid, new.ariane_id, new.text);
    END;
    """)
    conn.commit()


def clean_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_one(client, num: int) -> str | None:
    """Retourne texte si succès, None si 404, lève si erreur réseau."""
    aid = f"/Ariane_Web/AW_DCE/|{num}"
    r = client.get(DOWNLOAD_URL, params={
        "plugin": "Service.downloadFilePagePlugin",
        "Index": "Ariane_Web",
        "Id": aid,
    }, timeout=30)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    if "charset=iso-8859-1" in (r.headers.get("content-type") or "").lower():
        r.encoding = "iso-8859-1"
    text = clean_html(r.text)
    if len(text) < 200:
        return None
    return text


def load_checkpoint() -> int:
    try:
        return int(Path(CHECKPOINT_FILE).read_text().strip())
    except Exception:
        return START_ID


def save_checkpoint(n: int):
    try:
        Path(CHECKPOINT_FILE).write_text(str(n))
    except Exception:
        pass


def main():
    print(f"[ariane] start ; UA = {USER_AGENT}")
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA cache_size=-32000")
    ensure_schema(conn)

    existing = conn.execute("SELECT COUNT(*) FROM ariane_decisions").fetchone()[0]
    print(f"[ariane] DB existing : {existing}")

    start_at = load_checkpoint()
    print(f"[ariane] resume from id={start_at}")

    client = httpx.Client(headers={"User-Agent": USER_AGENT})
    consecutive_errors = 0
    consecutive_404 = 0
    consecutive_skipped = 0
    added_session = 0
    start_t = time.time()

    for num in range(start_at, END_ID + 1):
        # Skip si déjà en DB
        existing_row = conn.execute(
            "SELECT length(text) FROM ariane_decisions WHERE ariane_num=?", (num,)
        ).fetchone()
        if existing_row and existing_row[0] and existing_row[0] > 200:
            consecutive_skipped += 1
            if consecutive_skipped % 1000 == 0:
                print(f"  [skip x{consecutive_skipped}] at id={num}")
                save_checkpoint(num)
            continue
        consecutive_skipped = 0

        try:
            text = fetch_one(client, num)
        except Exception as e:
            consecutive_errors += 1
            print(f"  [err {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}] id={num}: {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"\n*** CIRCUIT BREAKER ***")
                print(f"  {MAX_CONSECUTIVE_ERRORS} erreurs consécutives, arrêt.")
                print(f"  Dernier id tenté : {num}")
                save_checkpoint(num)
                sys.exit(2)
            time.sleep(min(60, 5 * consecutive_errors))  # backoff
            continue
        consecutive_errors = 0

        if text is None:
            consecutive_404 += 1
            if consecutive_404 >= MAX_CONSECUTIVE_404:
                print(f"\n*** {MAX_CONSECUTIVE_404} x 404 consécutifs at id={num}, fin du corpus probable.")
                save_checkpoint(num)
                break
            continue
        consecutive_404 = 0

        # Insert
        try:
            conn.execute(
                "INSERT OR REPLACE INTO ariane_decisions (ariane_id, ariane_num, text, fetched_at) VALUES (?,?,?,datetime('now'))",
                (f"/Ariane_Web/AW_DCE/|{num}", num, text),
            )
            conn.commit()
            added_session += 1
        except Exception as e:
            print(f"  [DB err id={num}] {e}")

        if added_session % 50 == 0:
            elapsed = time.time() - start_t
            rate = added_session / elapsed if elapsed > 0 else 0
            print(f"  +{added_session} added (id={num}, {rate:.1f}/s)")
            save_checkpoint(num)

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    save_checkpoint(num)
    final = conn.execute("SELECT COUNT(*) FROM ariane_decisions").fetchone()[0]
    print(f"\nDONE. Total ariane : {final} (+{added_session} cette session)")
    conn.close()


if __name__ == "__main__":
    main()
