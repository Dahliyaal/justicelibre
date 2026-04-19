"""Fill-in-gaps pour CEDH : re-liste chaque année, compare à la DB,
fetch uniquement les itemids manquants.

Complète le scraping initial (74 678 → ~76 060).
"""
import html
import re
import sqlite3
import sys
import time
from urllib.parse import quote

import httpx

sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
BASE = "https://hudoc.echr.coe.int"
BATCH = 500  # list-only batch, pas de fetch_text dans la boucle de listing
USER_AGENT = "justicelibre.org/1.0 (gap-filler)"
QUERY_BASE = (
    'contentsitename=ECHR AND '
    '(NOT (doctype=PR OR doctype=HFCOMOLD OR doctype=HECOMOLD)) AND '
    '((languageisocode="FRE"))'
)
SELECT = "itemid,docname,ecli,kpdate,doctype,article,conclusion,importance,respondent,originatingbody_name"
MAX_CONSECUTIVE_ERRORS = 20


def list_batch(client, query, start, length=BATCH):
    q = quote(query, safe="")
    s = quote(SELECT, safe="")
    sort = quote("kpdate Descending", safe="")
    url = f"{BASE}/app/query/results?query={q}&select={s}&sort={sort}&start={start}&length={length}"
    r = client.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_text(client, itemid):
    try:
        r = client.get(
            f"{BASE}/app/conversion/docx/html/body",
            params={"library": "ECHR", "id": itemid, "filename": "x.docx", "logEvent": "False"},
            timeout=60,
        )
        if r.status_code != 200:
            return ""
        t = r.text
        t = re.sub(r"<script[^>]*>.*?</script>", " ", t, flags=re.DOTALL)
        t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.DOTALL)
        t = re.sub(r"<[^>]+>", " ", t)
        t = html.unescape(t)
        t = re.sub(r"\s+", " ", t).strip()
        return t
    except Exception as e:
        print(f"  [text err {itemid}]: {e}")
        return ""


def list_all_itemids_for_year(client, year):
    """Paginate jusqu'à épuisement, retourne tous les itemids + metadata."""
    query = f'{QUERY_BASE} AND kpdate:[{year}-01-01T00:00:00.0Z TO {year}-12-31T23:59:59.0Z]'
    results = []
    start = 0
    while True:
        try:
            d = list_batch(client, query, start)
        except Exception as e:
            print(f"  [list err year={year} start={start}]: {e} — retry 30s")
            time.sleep(30)
            try:
                d = list_batch(client, query, start)
            except Exception as e2:
                print(f"  [list retry failed]: {e2}")
                return results
        total = d.get("resultcount", 0)
        batch = d.get("results", [])
        if not batch:
            break
        results.extend(batch)
        start += BATCH
        if start >= total:
            break
        time.sleep(0.3)
    return results


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=120000")

    existing = conn.execute("SELECT COUNT(*) FROM cedh_decisions").fetchone()[0]
    print(f"[gaps] CEDH existing: {existing}")

    client = httpx.Client(headers={"User-Agent": USER_AGENT})
    added = 0
    consecutive_errors = 0

    # Inverse chronologique pour voir les années récentes d'abord
    from datetime import date as _d
    for year in range(_d.today().year, 1958, -1):
        print(f"\n=== YEAR {year} ===", flush=True)
        items = list_all_itemids_for_year(client, year)
        print(f"  listed {len(items)} itemids from HUDOC")
        if not items:
            continue

        # Sélection des itemids manquants ou avec texte vide
        itemids = [i.get("columns", {}).get("itemid", "") for i in items]
        itemids = [x for x in itemids if x]
        placeholders = ",".join("?" * len(itemids))
        have = set()
        if itemids:
            rows = conn.execute(
                f"SELECT itemid FROM cedh_decisions WHERE itemid IN ({placeholders}) AND length(text) > 100",
                itemids,
            ).fetchall()
            have = {r[0] for r in rows}
        missing_items = [i for i in items if i.get("columns", {}).get("itemid", "") not in have]
        print(f"  missing: {len(missing_items)}")
        if not missing_items:
            continue

        for item in missing_items:
            c = item.get("columns", {})
            itemid = c.get("itemid", "")
            if not itemid:
                continue
            try:
                text = fetch_text(client, itemid)
            except Exception as e:
                consecutive_errors += 1
                print(f"  [err fetch {itemid}]: {e}")
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print("\n*** CIRCUIT BREAKER ***")
                    sys.exit(2)
                time.sleep(min(60, 5 * consecutive_errors))
                continue
            consecutive_errors = 0

            row = (
                itemid,
                c.get("docname", ""),
                c.get("ecli", "") or "",
                (c.get("kpdate", "") or "")[:10],
                c.get("doctype", ""),
                c.get("article", "") or "",
                c.get("conclusion", "") or "",
                c.get("importance", "") or "",
                c.get("respondent", "") or "",
                c.get("originatingbody_name", "") or "",
                text,
            )
            for attempt in range(5):
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO cedh_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        row,
                    )
                    break
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower() and attempt < 4:
                        time.sleep(5 + attempt * 10)
                        continue
                    print(f"  [db err {itemid}]: {e}")
                    break
            added += 1
            if added % 50 == 0:
                conn.commit()
                print(f"    +{added} gaps filled")
            time.sleep(0.25)
        conn.commit()

    final = conn.execute("SELECT COUNT(*) FROM cedh_decisions").fetchone()[0]
    print(f"\nDONE. Total CEDH: {final} (+{added} this run)")
    conn.close()


if __name__ == "__main__":
    main()
