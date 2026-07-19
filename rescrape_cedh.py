"""Re-scrape CEDH empty texts with language fallback FR -> EN -> any.

Uses HUDOC search by appno (extracted from ECLI) to discover sibling
document IDs in other languages. Stores effective language in
`cedh_decisions.text_lang`.

Logs to /var/log/rescrape_cedh.log.
"""
import html
import re
import sqlite3
import sys
import time

import httpx

sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
BASE = "https://hudoc.echr.coe.int"
USER_AGENT = "justicelibre.org/1.0 (rescrape, contact: dahliyaal@justicelibre.org)"
LANG_PRIORITY = ["FRE", "ENG"]  # try FR first, then EN; otherwise first available
LANG_TO_CODE = {"FRE": "fr", "ENG": "en"}

SELECT_SIBLINGS = "itemid,docname,languageisocode,documentcollectionid"
SLEEP_BETWEEN = 0.6  # ~1.5 req/sec


def http_get(client, url, params=None, retries=3):
    last = None
    for attempt in range(retries):
        try:
            r = client.get(url, params=params, timeout=60)
            return r
        except Exception as e:
            last = e
            time.sleep(2 ** attempt + 1)
    raise last


def appno_from_ecli(ecli):
    """ECLI:CE:ECHR:YYYY:MMDDJUDXXXXXXXYY -> XXXXX/YY  (heuristic)."""
    if not ecli:
        return None
    m = re.search(r"ECLI:CE:ECHR:\d{4}:\d{4}([A-Z]{3})(\d{7})(\d{2})", ecli)
    if not m:
        return None
    _typ, num7, year2 = m.groups()
    num = int(num7)  # strip leading zeros
    return f"{num}/{year2}"


def list_siblings(client, appno):
    if not appno:
        return []
    q = f'appno="{appno}"'
    r = http_get(
        client,
        f"{BASE}/app/query/results",
        params={
            "query": q,
            "select": SELECT_SIBLINGS,
            "sort": "kpdate Descending",
            "start": 0,
            "length": 30,
        },
    )
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    out = []
    for row in data.get("results", []):
        c = row.get("columns", {})
        out.append({
            "itemid": c.get("itemid", ""),
            "lang": c.get("languageisocode", ""),
            "coll": c.get("documentcollectionid", "") or "",
            "docname": c.get("docname", ""),
        })
    return out


def fetch_body(client, itemid):
    r = http_get(
        client,
        f"{BASE}/app/conversion/docx/html/body",
        params={"library": "ECHR", "id": itemid, "filename": "x.docx", "logEvent": "False"},
    )
    if r.status_code != 200:
        return ""
    if not r.content or r.status_code == 204:
        return ""
    text = r.text
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Filter out non-judgment collections (we want CASELAW chambers/grand chamber)
def is_caselaw(coll):
    coll = (coll or "").upper()
    return "CASELAW" in coll and "PRESSRELEASE" not in coll


def find_text_with_fallback(client, itemid, ecli):
    """Returns (text, effective_lang_code) or ('', None)."""
    # 1) Try the original itemid first (in case the text was simply missing)
    body = fetch_body(client, itemid)
    if body and len(body) > 100:
        return body, "fr"  # original was queried as FRE

    # 2) Look up siblings via appno
    appno = appno_from_ecli(ecli)
    siblings = list_siblings(client, appno) if appno else []
    siblings = [s for s in siblings if s["itemid"] and is_caselaw(s["coll"])]

    if not siblings:
        return "", None

    # Try by language priority
    by_lang = {}
    for s in siblings:
        by_lang.setdefault(s["lang"], []).append(s)

    for lang in LANG_PRIORITY:
        for s in by_lang.get(lang, []):
            if s["itemid"] == itemid:
                continue  # already tried
            time.sleep(SLEEP_BETWEEN)
            body = fetch_body(client, s["itemid"])
            if body and len(body) > 100:
                return body, LANG_TO_CODE.get(lang, lang.lower()[:2])

    # 3) Fall back to any other language
    for lang, ss in by_lang.items():
        if lang in LANG_PRIORITY:
            continue
        for s in ss:
            time.sleep(SLEEP_BETWEEN)
            body = fetch_body(client, s["itemid"])
            if body and len(body) > 100:
                return body, lang.lower()[:2] if len(lang) >= 2 else lang.lower()
    return "", None


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA recursive_triggers=ON")  # INSERT OR REPLACE doit déclencher le trigger _ad du FTS5
    conn.execute("PRAGMA busy_timeout=120000")

    rows = conn.execute(
        "SELECT itemid, ecli FROM cedh_decisions WHERE length(text)=0 ORDER BY date DESC"
    ).fetchall()
    print(f"[rescrape] {len(rows)} CEDH rows to process", flush=True)

    client = httpx.Client(headers={"User-Agent": USER_AGENT})

    stats = {"fr": 0, "en": 0, "other": 0, "none": 0, "err": 0}
    processed = 0
    for itemid, ecli in rows:
        try:
            text, lang = find_text_with_fallback(client, itemid, ecli)
        except Exception as e:
            print(f"  [err {itemid}]: {e}", flush=True)
            stats["err"] += 1
            time.sleep(2)
            continue

        if text:
            conn.execute(
                "UPDATE cedh_decisions SET text=?, text_lang=? WHERE itemid=?",
                (text, lang, itemid),
            )
            if lang == "fr":
                stats["fr"] += 1
            elif lang == "en":
                stats["en"] += 1
            else:
                stats["other"] += 1
        else:
            stats["none"] += 1

        processed += 1
        if processed % 25 == 0:
            conn.commit()
            print(
                f"  [{processed}/{len(rows)}] fr={stats['fr']} en={stats['en']} "
                f"other={stats['other']} none={stats['none']} err={stats['err']}",
                flush=True,
            )
        time.sleep(SLEEP_BETWEEN)

    conn.commit()
    print(
        f"\nDONE. Processed {processed}: fr={stats['fr']} en={stats['en']} "
        f"other={stats['other']} none={stats['none']} err={stats['err']}",
        flush=True,
    )
    conn.close()


if __name__ == "__main__":
    main()
