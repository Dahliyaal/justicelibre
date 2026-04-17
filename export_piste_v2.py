#!/usr/bin/env python3 -u
"""Export PISTE avec partition par date (contourne la limite Elasticsearch 10k).

Strategy:
- Partition par mois de 1990-01 à aujourd'hui
- Si un mois a > 9000 résultats, subdivise en semaines
- Pagine chaque sous-partition (batch_size=1000, batch=0,1,2...)
"""
import json
import sys
import time
import sqlite3
import httpx
from datetime import date, timedelta

# Force line-buffered stdout so nohup logs flush as we go
sys.stdout.reconfigure(line_buffering=True)
print("[startup] module loaded", flush=True)

import os
from pathlib import Path as _P

def _load_env():
    f = _P(__file__).with_name(".env")
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
_load_env()
CLIENT_ID = os.environ.get("PISTE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("PISTE_CLIENT_SECRET", "")
if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("PISTE_CLIENT_ID / PISTE_CLIENT_SECRET manquants (voir .env)")
OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
BASE = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"
DB_PATH = "/opt/justicelibre/dila/judiciaire.db"

START_DATE = date(1960, 1, 1)  # avant 1960 PISTE retourne très peu
END_DATE = date.today()


def get_token():
    r = httpx.post(OAUTH_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid",
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def month_ranges(start, end):
    """Yield (first_day, last_day) tuples for each month from start to end."""
    y, m = start.year, start.month
    while True:
        first = date(y, m, 1)
        if first > end:
            break
        if m == 12:
            last = date(y, 12, 31)
            y, m = y + 1, 1
        else:
            last = date(y, m + 1, 1) - timedelta(days=1)
            m += 1
        yield first, last


def week_ranges(start, end):
    """Yield weekly ranges within a month."""
    cur = start
    while cur <= end:
        last = min(cur + timedelta(days=6), end)
        yield cur, last
        cur = last + timedelta(days=1)


class Exporter:
    def __init__(self):
        print("[init] getting OAuth token...")
        self.token = get_token()
        self.token_time = time.time()
        print("[init] connecting SQLite...")
        self.conn = sqlite3.connect(DB_PATH, timeout=120.0)
        self.conn.execute("PRAGMA busy_timeout=120000")
        self.conn.execute("PRAGMA mmap_size=0")
        self.conn.execute("PRAGMA cache_size=-8000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=FILE")
        self.conn.execute("PRAGMA journal_mode=WAL")
        print("[init] SQLite ready")
        self.total_new = 0
        self.total_skipped = 0

    def headers(self):
        if time.time() - self.token_time > 2700:
            print("  [token refresh]")
            self.token = get_token()
            self.token_time = time.time()
        return {"Authorization": f"Bearer {self.token}"}

    def fetch(self, params, max_retries=5):
        for attempt in range(max_retries):
            try:
                r = httpx.get(f"{BASE}/export", headers=self.headers(), params=params, timeout=120)
                if r.status_code == 429:
                    print(f"  [429] sleeping 60s...")
                    time.sleep(60)
                    continue
                if r.status_code == 416:
                    return None  # partition too big
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 416:
                    return None
                print(f"  [retry {attempt+1}] {e}")
                time.sleep(10)
            except Exception as e:
                print(f"  [retry {attempt+1}] {e}")
                time.sleep(10)
        return None

    def index_results(self, results):
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
                "",
                "",
                dec.get("text", ""),
            ))
        if not batch:
            return 0
        for attempt in range(5):
            try:
                self.conn.executemany(
                    "INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    batch,
                )
                self.conn.commit()
                new = self.conn.execute("SELECT changes()").fetchone()[0]
                self.total_new += new
                self.total_skipped += len(batch) - new
                return new
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 4:
                    time.sleep(5 + attempt * 10)
                    continue
                print(f"  DB error (attempt {attempt+1}): {e}")
                return 0
            except Exception as e:
                print(f"  DB error: {e}")
                return 0
        return 0

    def export_range(self, d_start, d_end, label, batch_size=100):
        """Export all decisions between d_start and d_end."""
        # Peek first to get total
        first = self.fetch({
            "batch_size": batch_size,
            "batch": 0,
            "date_start": d_start.isoformat(),
            "date_end": d_end.isoformat(),
        })
        if first is None:
            return False  # partition too big or error
        total = first.get("total", 0)
        if total == 0:
            return True
        # If total fits under 10k cap, paginate normally
        if total <= 9500:
            new = self.index_results(first.get("results", []))
            page = 1
            while page * batch_size < total:
                data = self.fetch({
                    "batch_size": batch_size,
                    "batch": page,
                    "date_start": d_start.isoformat(),
                    "date_end": d_end.isoformat(),
                })
                if not data or not data.get("results"):
                    break
                new += self.index_results(data["results"])
                page += 1
                time.sleep(0.3)
            print(f"  [{label}] total={total} new={new} cumulative={self.total_new}")
            return True
        else:
            # Subdivide weekly
            print(f"  [{label}] total={total} > 9500, subdividing by week")
            for ws, we in week_ranges(d_start, d_end):
                self.export_range(ws, we, f"{label} {ws}–{we}", batch_size=batch_size)
            return True

    def run(self):
        print("DB start: (skipped count to avoid full scan)\n")

        months = list(month_ranges(START_DATE, END_DATE))
        print(f"Processing {len(months)} months from {START_DATE} to {END_DATE}\n")

        for i, (first, last) in enumerate(months):
            label = first.strftime("%Y-%m")
            ok = self.export_range(first, last, label)
            if not ok:
                print(f"  [{label}] 416 at month level, subdividing weekly")
                for ws, we in week_ranges(first, last):
                    self.export_range(ws, we, f"{label} wk{ws}")

            if i % 12 == 0 and i > 0:
                print(f"\n=== After {first.year}: +{self.total_new} new this run (running total) ===\n")

        print(f"\n\nDONE. Added this run: {self.total_new} | Skipped: {self.total_skipped}")
        self.conn.close()


if __name__ == "__main__":
    Exporter().run()
