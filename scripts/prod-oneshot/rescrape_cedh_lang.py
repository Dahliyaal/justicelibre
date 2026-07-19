#!/usr/bin/env python3
"""Re-scrape CEDH avec fallback langue.

Pour chaque itemid CEDH avec text vide (~17282) :
  1) Query HUDOC par ECLI → trouve les siblings linguistiques
  2) Tente FRE → ENG → première autre langue
  3) Stocke text + text_lang + text_itemid (l'itemid réellement utilisé)

Itemids sans ECLI (3 cas) → fallback query par appno.

Lancement :
  nohup python3 /opt/justicelibre/rescrape_cedh_lang.py \
      > /var/log/rescrape_cedh.log 2>&1 &
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
USER_AGENT = "justicelibre.org/1.0 (lang-fallback rescrape)"
SELECT = "itemid,docname,languageisocode,doctype,ecli,appno"

LANG_PRIORITY = ["FRE", "ENG", "ITA", "DEU", "SPA", "RUS", "TUR", "POL", "POR"]


def ensure_columns(conn):
    """Ajoute colonnes text_lang, text_itemid si absentes."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(cedh_decisions)").fetchall()}
    if "text_lang" not in cols:
        conn.execute("ALTER TABLE cedh_decisions ADD COLUMN text_lang TEXT")
    if "text_itemid" not in cols:
        conn.execute("ALTER TABLE cedh_decisions ADD COLUMN text_itemid TEXT")
    conn.commit()


def query_siblings(client, ecli=None, appno=None):
    """Retourne [(itemid, lang)] pour toutes versions d'une affaire."""
    if ecli:
        q_str = f'contentsitename=ECHR AND ecli:"{ecli}"'
    elif appno:
        q_str = f'contentsitename=ECHR AND appno:"{appno}"'
    else:
        return []
    q = quote(q_str, safe="")
    s = quote(SELECT, safe="")
    sort = quote("kpdate Descending", safe="")
    url = f"{BASE}/app/query/results?query={q}&select={s}&sort={sort}&start=0&length=20"
    try:
        r = client.get(url, timeout=60)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/json"):
            return []
        data = r.json()
        out = []
        for it in data.get("results", []):
            c = it.get("columns", {})
            iid = c.get("itemid", "")
            lang = c.get("languageisocode", "")
            if iid:
                out.append((iid, lang))
        return out
    except Exception as e:
        print(f"  [siblings err]: {e}")
        return []


def fetch_text(client, itemid):
    try:
        r = client.get(
            f"{BASE}/app/conversion/docx/html/body",
            params={"library": "ECHR", "id": itemid, "filename": "x.docx", "logEvent": "False"},
            timeout=60,
        )
        if r.status_code != 200 or not r.text:
            return ""
        t = r.text
        t = re.sub(r"<script[^>]*>.*?</script>", " ", t, flags=re.DOTALL)
        t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.DOTALL)
        # Préserve <br/> en \n et </p>...<p> en \n\n AVANT de stripper les autres tags
        t = re.sub(r"<\s*br\s*/?\s*>", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<\s*/p\s*>\s*<\s*p[^>]*>", "\n\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<\s*p[^>]*>", "", t, flags=re.IGNORECASE)
        t = re.sub(r"<\s*/p\s*>", "\n\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<[^>]+>", " ", t)
        t = html.unescape(t)
        # Collapse spaces dans une ligne mais préserve les retours
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        t = re.sub(r"^[ \t]+|[ \t]+$", "", t, flags=re.MULTILINE)
        return t.strip()
    except Exception as e:
        print(f"  [fetch err {itemid}]: {e}")
        return ""


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=120000")
    ensure_columns(conn)

    rows = conn.execute(
        "SELECT itemid, ecli FROM cedh_decisions "
        "WHERE (text IS NULL OR length(text) < 100) "
        "ORDER BY date DESC"
    ).fetchall()
    print(f"[rescrape-cedh] {len(rows)} itemids à traiter")

    client = httpx.Client(headers={"User-Agent": USER_AGENT})
    filled = 0
    no_text = 0
    consecutive_errors = 0

    for i, (iid, ecli) in enumerate(rows, 1):
        if i % 100 == 0:
            print(f"  [{i}/{len(rows)}] filled={filled} no_text={no_text}", flush=True)

        siblings = query_siblings(client, ecli=ecli) if ecli else []
        if not siblings:
            # Pas d'ECLI ou aucun sibling → tag 'no_source' et next
            no_text += 1
            conn.execute(
                "UPDATE cedh_decisions SET text_lang=? WHERE itemid=?",
                ("none", iid),
            )
            if i % 50 == 0:
                conn.commit()
            continue

        # Trier siblings par priorité de langue
        siblings.sort(key=lambda s: LANG_PRIORITY.index(s[1]) if s[1] in LANG_PRIORITY else 99)

        text = ""
        used_iid = None
        used_lang = None
        for sib_iid, sib_lang in siblings:
            text = fetch_text(client, sib_iid)
            time.sleep(0.25)
            if text and len(text) > 100:
                used_iid = sib_iid
                used_lang = sib_lang
                break

        if text and used_iid:
            for attempt in range(5):
                try:
                    conn.execute(
                        "UPDATE cedh_decisions SET text=?, text_lang=?, text_itemid=? WHERE itemid=?",
                        (text, used_lang.lower() if used_lang else None, used_iid, iid),
                    )
                    break
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower() and attempt < 4:
                        time.sleep(5 + attempt * 5)
                        continue
                    print(f"  [db err {iid}]: {e}")
                    break
            filled += 1
            consecutive_errors = 0
        else:
            no_text += 1
            conn.execute(
                "UPDATE cedh_decisions SET text_lang=? WHERE itemid=?",
                ("none", iid),
            )
            consecutive_errors += 1
            if consecutive_errors >= 30:
                print("  *** 30 consecutive failures — sleeping 60s ***")
                time.sleep(60)
                consecutive_errors = 0

        if i % 50 == 0:
            conn.commit()

    conn.commit()
    print(f"\n[done] filled={filled} no_text={no_text} total={len(rows)}")
    conn.close()


if __name__ == "__main__":
    main()
