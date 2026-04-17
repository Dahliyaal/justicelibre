"""Scrape HUDOC (Cour EDH) — ~76k documents en français.

API publique, pas d'auth.
- Liste: /app/query/results avec pagination start/length
- Texte: /app/conversion/docx/html/body?library=ECHR&id={itemid}

Stocke dans une table separate `cedh_decisions` dans la même DB.
"""
import html
import re
import sqlite3
import time
from urllib.parse import quote
import httpx

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
BASE = "https://hudoc.echr.coe.int"
BATCH = 100  # HUDOC caps somewhere below 500
USER_AGENT = "justicelibre.org/1.0 (open data scraper, contact: dahliyaal@justicelibre.org)"

QUERY_BASE = (
    'contentsitename=ECHR AND '
    '(NOT (doctype=PR OR doctype=HFCOMOLD OR doctype=HECOMOLD)) AND '
    '((languageisocode="FRE"))'
)
SELECT = "itemid,docname,ecli,kpdate,doctype,article,conclusion,importance,respondent,originatingbody_name"


def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cedh_decisions (
        itemid TEXT PRIMARY KEY,
        docname TEXT,
        ecli TEXT,
        date TEXT,
        doctype TEXT,
        article TEXT,
        conclusion TEXT,
        importance TEXT,
        respondent TEXT,
        originating_body TEXT,
        text TEXT
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS cedh_fts USING fts5(
        itemid UNINDEXED, docname, article, conclusion, text,
        content='cedh_decisions', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS cedh_ai AFTER INSERT ON cedh_decisions BEGIN
        INSERT INTO cedh_fts(rowid, itemid, docname, article, conclusion, text)
        VALUES (new.rowid, new.itemid, new.docname, new.article, new.conclusion, new.text);
    END;
    """)
    conn.commit()


def list_batch(client, query, start):
    # HUDOC requires sort= ; without it the endpoint returns 404
    q = quote(query, safe="")
    s = quote(SELECT, safe="")
    sort = quote("kpdate Descending", safe="")
    url = f"{BASE}/app/query/results?query={q}&select={s}&sort={sort}&start={start}&length={BATCH}"
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
        text = r.text
        # Strip HTML to plain text
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        print(f"  [text err {itemid}]: {e}")
        return ""


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA cache_size=-8000")
    ensure_schema(conn)

    existing = conn.execute("SELECT COUNT(*) FROM cedh_decisions").fetchone()[0]
    print(f"CEDH existing: {existing}")

    client = httpx.Client(headers={"User-Agent": USER_AGENT})

    # Peek overall total
    first = list_batch(client, QUERY_BASE, 0)
    total_all = first.get("resultcount", 0)
    print(f"Total CEDH FR (all years): {total_all}")

    # Partition by year to bypass 10k HUDOC cap
    from datetime import date as _d
    current_year = _d.today().year
    added = 0
    for year in range(current_year, 1958, -1):  # CEDH created 1959
        query = f'{QUERY_BASE} AND kpdate:[{year}-01-01T00:00:00.0Z TO {year}-12-31T23:59:59.0Z]'
        print(f"\n=== YEAR {year} ===")
        try:
            peek = list_batch(client, query, 0)
        except Exception as e:
            print(f"  [peek err year={year}]: {e}, skip")
            continue
        year_total = peek.get("resultcount", 0)
        print(f"  total for year={year}: {year_total}")
        if year_total == 0:
            continue

        start = 0
        data = peek
        while True:
            results = data.get("results", [])
            if not results:
                break
            print(f"  year={year} start={start} len={len(results)}")

            for item in results:
                c = item.get("columns", {})
                itemid = c.get("itemid", "")
                if not itemid:
                    continue
                existing_row = conn.execute(
                    "SELECT length(text) FROM cedh_decisions WHERE itemid=?", (itemid,)
                ).fetchone()
                if existing_row and existing_row[0] and existing_row[0] > 100:
                    continue

                text = fetch_text(client, itemid)
                row_data = (
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
                            row_data,
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
                    print(f"    +{added} indexed (year={year}, start={start})")
                time.sleep(0.25)

            conn.commit()
            start += BATCH
            if start >= year_total:
                break
            try:
                data = list_batch(client, query, start)
            except Exception as e:
                print(f"  [list err year={year} start={start}]: {e}, retry in 30s")
                time.sleep(30)
                try:
                    data = list_batch(client, query, start)
                except Exception as e2:
                    print(f"  [list err year={year} start={start}]: {e2}, skip rest of year")
                    break

    total_now = conn.execute("SELECT COUNT(*) FROM cedh_decisions").fetchone()[0]
    print(f"DONE. Total CEDH: {total_now} (+{added} this run)")
    conn.close()


if __name__ == "__main__":
    main()
