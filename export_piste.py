"""Bulk export all decisions from Judilibre PROD via /export endpoint.

Usage: python3 export_piste.py
Paginates through the entire corpus and indexes into SQLite.
"""
import json
import os
import time
import sqlite3
from pathlib import Path as _P
import httpx

_f = _P(__file__).with_name(".env")
if _f.exists():
    for _line in _f.read_text().splitlines():
        if "=" in _line and not _line.strip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
CLIENT_ID = os.environ.get("PISTE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("PISTE_CLIENT_SECRET", "")
if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("PISTE_CLIENT_ID / PISTE_CLIENT_SECRET manquants (voir .env)")
OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
BASE = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"
DB_PATH = "/opt/justicelibre/dila/judiciaire.db"

def get_token():
    r = httpx.post(OAUTH_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid",
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    return r.json()["access_token"]

def export_all():
    token = get_token()
    token_time = time.time()
    headers = {"Authorization": f"Bearer {token}"}

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    # Check existing count
    existing = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    print(f"Existing decisions in DB: {existing}")

    batch_size = 100
    total_new = 0
    total_skipped = 0
    page = 0
    consecutive_empty = 0

    while True:
        # Refresh token every 45 minutes
        if time.time() - token_time > 2700:
            print("  Refreshing token...")
            token = get_token()
            token_time = time.time()
            headers = {"Authorization": f"Bearer {token}"}

        try:
            r = httpx.get(
                f"{BASE}/export",
                headers=headers,
                params={"batch_size": batch_size, "batch": page},
                timeout=60,
            )
            if r.status_code == 429:
                print(f"  Rate limited at page {page}, sleeping 60s...")
                time.sleep(60)
                continue
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  Error at page {page}: {e}, sleeping 30s...")
            time.sleep(30)
            continue

        results = data.get("results", [])
        if not results:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                print(f"3 consecutive empty pages, done.")
                break
            page += 1
            continue

        consecutive_empty = 0
        batch = []
        for dec in results:
            did = dec.get("id", "")
            if not did:
                continue
            batch.append((
                did,
                dec.get("type", ""),
                dec.get("themes", [""])[0] if dec.get("themes") else "",
                dec.get("decision_date", ""),
                dec.get("jurisdiction", ""),
                dec.get("solution", ""),
                dec.get("number", ""),
                dec.get("chamber", ""),
                dec.get("ecli", ""),
                "",  # president
                "",  # avocats
                dec.get("text", ""),
            ))

        try:
            conn.executemany(
                "INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
        except Exception as e:
            print(f"  DB error: {e}")

        new_in_batch = conn.execute(f"SELECT changes()").fetchone()[0]
        total_new += new_in_batch
        total_skipped += len(batch) - new_in_batch
        page += 1

        if page % 10 == 0:
            total_now = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            print(f"  Page {page}: {total_new} new, {total_skipped} skipped, {total_now} total in DB")

        # Small delay to be polite
        time.sleep(0.5)

    total_final = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    print(f"\nDone. {total_new} new decisions added. Total in DB: {total_final}")
    conn.close()

if __name__ == "__main__":
    export_all()
