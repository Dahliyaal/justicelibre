"""Scrape CJUE via EUR-Lex SPARQL + publications.europa.eu resource endpoints.

~40k+ décisions CJUE en français, API publique sans auth.
- Liste: SPARQL endpoint publications.europa.eu/webapi/rdf/sparql
- Texte: publications.europa.eu/resource/celex/{CELEX} avec Accept-Language: fra
"""
import html
import re
import sqlite3
import time
import httpx

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
RESOURCE_BASE = "http://publications.europa.eu/resource/celex"
USER_AGENT = "justicelibre.org/1.0 (open data scraper, contact: dahliyaal@justicelibre.org)"

SPARQL_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?celex ?date ?type WHERE {
  ?work cdm:work_has_resource-type ?rtype .
  VALUES ?rtype {
    <http://publications.europa.eu/resource/authority/resource-type/JUDG>
    <http://publications.europa.eu/resource/authority/resource-type/JUDG_GNR>
    <http://publications.europa.eu/resource/authority/resource-type/JUDG_JURINFO>
    <http://publications.europa.eu/resource/authority/resource-type/ORDER>
    <http://publications.europa.eu/resource/authority/resource-type/OPIN_AG>
  }
  ?work cdm:resource_legal_id_celex ?celex .
  ?work cdm:work_date_document ?date .
  FILTER(STRSTARTS(STR(?celex), "6"))
  FILTER(?date >= "%(date_start)s"^^xsd:date && ?date < "%(date_end)s"^^xsd:date)
  BIND(?rtype AS ?type)
}
ORDER BY DESC(?date)
LIMIT %(limit)d OFFSET %(offset)d
"""


def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cjue_decisions (
        celex TEXT PRIMARY KEY,
        ecli TEXT,
        date TEXT,
        type TEXT,
        title TEXT,
        text TEXT
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS cjue_fts USING fts5(
        celex UNINDEXED, ecli, title, text,
        content='cjue_decisions', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS cjue_ai AFTER INSERT ON cjue_decisions BEGIN
        INSERT INTO cjue_fts(rowid, celex, ecli, title, text)
        VALUES (new.rowid, new.celex, new.ecli, new.title, new.text);
    END;
    """)
    conn.commit()


def sparql_batch(client, date_start, date_end, offset, limit=1000):
    q = SPARQL_QUERY % {
        "date_start": date_start, "date_end": date_end,
        "limit": limit, "offset": offset,
    }
    r = client.get(
        SPARQL,
        params={"query": q, "format": "application/sparql-results+json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def fetch_celex_html(client, celex):
    try:
        r = client.get(
            f"{RESOURCE_BASE}/{celex}",
            headers={"Accept-Language": "fra", "Accept": "text/html"},
            follow_redirects=True,
            timeout=60,
        )
        if r.status_code != 200:
            return "", ""
        text = r.text
        # Try extract <title>
        title_m = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
        title = html.unescape(title_m.group(1).strip()) if title_m else ""
        # Strip to plain
        body = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.DOTALL)
        body = re.sub(r"<[^>]+>", " ", body)
        body = html.unescape(body)
        body = re.sub(r"\s+", " ", body).strip()
        return title, body
    except Exception as e:
        print(f"  [text err {celex}]: {e}")
        return "", ""


def celex_to_ecli(celex):
    """Best-effort ECLI mapping. Not all CELEX have clean ECLI mappable."""
    # Format: YYYYTTNNNN where T is 1-2 chars type (CJ=Judgment, CO=Order, CC=AG Opinion, TJ=General Court)
    m = re.match(r"^6(\d{4})([A-Z]{2})(\d{4})$", celex)
    if not m:
        return ""
    year, typ, num = m.groups()
    court_map = {"CJ": "C", "CO": "C", "CC": "C", "TJ": "T", "TO": "T", "FC": "F"}
    court = court_map.get(typ, "")
    if not court:
        return ""
    return f"ECLI:EU:{court}:{year}:{int(num)}"


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA cache_size=-8000")
    ensure_schema(conn)

    existing = conn.execute("SELECT COUNT(*) FROM cjue_decisions").fetchone()[0]
    print(f"CJUE existing: {existing}")

    client = httpx.Client(headers={"User-Agent": USER_AGENT})

    batch_limit = 1000
    added = 0
    # Partition by year to bypass 10k OFFSET cap on SPARQL endpoint.
    # CJUE starts ~1954 (first Coal & Steel Court ruling). Iterate most
    # recent first (priority for active law).
    from datetime import date as _d
    current_year = _d.today().year
    for year in range(current_year, 1953, -1):
        ds, de = f"{year}-01-01", f"{year + 1}-01-01"
        offset = 0
        while True:
            print(f"  SPARQL year={year} offset={offset}")
            try:
                rows = sparql_batch(client, ds, de, offset, batch_limit)
            except Exception as e:
                print(f"  [sparql err year={year}]: {e}, retry in 30s")
                time.sleep(30)
                try:
                    rows = sparql_batch(client, ds, de, offset, batch_limit)
                except Exception as e2:
                    print(f"  [sparql err year={year}] still failing: {e2}, skip year")
                    break

            if not rows:
                break

            for row in rows:
                celex = row.get("celex", {}).get("value", "")
                if not celex:
                    continue
                date = row.get("date", {}).get("value", "")[:10]
                rtype = row.get("type", {}).get("value", "").rsplit("/", 1)[-1]

                existing_row = conn.execute(
                    "SELECT length(text) FROM cjue_decisions WHERE celex=?", (celex,)
                ).fetchone()
                if existing_row and existing_row[0] and existing_row[0] > 100:
                    continue

                title, text = fetch_celex_html(client, celex)
                ecli = celex_to_ecli(celex)
                for attempt in range(5):
                    try:
                        conn.execute(
                            "INSERT OR REPLACE INTO cjue_decisions VALUES (?,?,?,?,?,?)",
                            (celex, ecli, date, rtype, title, text),
                        )
                        break
                    except sqlite3.OperationalError as e:
                        if "locked" in str(e).lower() and attempt < 4:
                            time.sleep(5 + attempt * 10)
                            continue
                        print(f"  [db err {celex}]: {e}")
                        break
                added += 1
                if added % 50 == 0:
                    conn.commit()
                    print(f"    +{added} indexed (year={year}, offset={offset})")
                time.sleep(0.3)

            conn.commit()
            offset += batch_limit
            if len(rows) < batch_limit:
                break
            if offset >= 9000:
                print(f"  [year={year}] approaching 10k cap, moving to next year")
                break

    total_now = conn.execute("SELECT COUNT(*) FROM cjue_decisions").fetchone()[0]
    print(f"DONE. Total CJUE: {total_now} (+{added} this run)")
    conn.close()


if __name__ == "__main__":
    main()
