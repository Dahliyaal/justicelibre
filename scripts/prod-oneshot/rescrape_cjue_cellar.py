#!/usr/bin/env python3
"""Re-scrape CJUE via Cellar (publications.europa.eu).

Bypass le WAF CloudFront d'EUR-Lex. Pour chaque celex avec text vide
(~18436), tente FR puis EN via content negotiation Cellar.

Lancement :
  nohup python3 /opt/justicelibre/rescrape_cjue_cellar.py \
      > /var/log/rescrape_cjue.log 2>&1 &
"""
import html
import re
import sqlite3
import sys
import time

import httpx

sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
CELLAR = "http://publications.europa.eu/resource/celex"


def ensure_columns(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(cjue_decisions)").fetchall()}
    if "text_lang" not in cols:
        conn.execute("ALTER TABLE cjue_decisions ADD COLUMN text_lang TEXT")
    conn.commit()


def fetch_cellar(client, celex, lang, accept):
    """Tente fetch d'un format pour une langue donnée."""
    try:
        r = client.get(
            f"{CELLAR}/{celex}",
            headers={"Accept": accept, "Accept-Language": lang},
            timeout=60,
        )
        if r.status_code == 200 and len(r.content) > 2000:
            return r.text
    except Exception as e:
        print(f"  [fetch err {celex} {lang}/{accept}]: {e}")
    return ""


def clean_html(t):
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


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=120000")
    ensure_columns(conn)

    rows = conn.execute(
        "SELECT celex FROM cjue_decisions "
        "WHERE (text IS NULL OR length(text) < 100) "
        "ORDER BY date DESC"
    ).fetchall()
    print(f"[rescrape-cjue] {len(rows)} celex à traiter")

    client = httpx.Client(
        headers={"User-Agent": "justicelibre.org/1.0 (cellar)"},
        follow_redirects=True,
        timeout=60,
    )
    filled = 0
    no_text = 0
    consecutive_errors = 0

    # Cellar accepte 2 mime selon le doc : text/html OU application/xhtml+xml
    ATTEMPTS = [
        ("fr", "text/html"),
        ("fr", "application/xhtml+xml"),
        ("en", "text/html"),
        ("en", "application/xhtml+xml"),
    ]

    for i, (celex,) in enumerate(rows, 1):
        if i % 100 == 0:
            print(f"  [{i}/{len(rows)}] filled={filled} no_text={no_text}", flush=True)

        text = ""
        used_lang = None
        for lang, accept in ATTEMPTS:
            raw = fetch_cellar(client, celex, lang, accept)
            if raw:
                text = clean_html(raw)
                if len(text) > 200:
                    used_lang = lang
                    break
            time.sleep(0.15)

        if text and used_lang:
            for attempt in range(5):
                try:
                    conn.execute(
                        "UPDATE cjue_decisions SET text=?, text_lang=? WHERE celex=?",
                        (text, used_lang, celex),
                    )
                    break
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower() and attempt < 4:
                        time.sleep(5 + attempt * 5)
                        continue
                    print(f"  [db err {celex}]: {e}")
                    break
            filled += 1
            consecutive_errors = 0
        else:
            no_text += 1
            conn.execute(
                "UPDATE cjue_decisions SET text_lang=? WHERE celex=?",
                ("none", celex),
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
