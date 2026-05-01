#!/usr/bin/env python3
"""IndexNow ping pour Bing / Yandex / Naver / DuckDuckGo / ChatGPT search.

IndexNow = protocole standard supporté par tout le monde sauf Google.
Permet d'indexer un site sur Bing en heures au lieu de semaines, ce qui
amorce ensuite la diffusion via Copilot, Perplexity, ChatGPT search, DDG.

Usage :
  # Mode batch : tous les nouveaux decision_id depuis 24h
  python3 indexnow_ping.py --recent 24

  # Mode liste : URLs custom passées en stdin
  echo "https://justicelibre.org/decision/admin/DTA_xxx" | python3 indexnow_ping.py

  # Mode bulk initial : énumère le sitemap-index et soumet par batch
  python3 indexnow_ping.py --bulk-from-sitemap

Limites IndexNow :
  - 10 000 URLs par requête HTTP max
  - 10 000 URLs / jour / domaine (en pratique, certains moteurs sont plus laxistes)
  - Les URLs doivent être du même hôte que la clé

Cron suggéré (déploie sur al-uzza ou PROD) :
  0 4 * * * cd /opt/justicelibre && python3 indexnow_ping.py --recent 24 >> /var/log/indexnow.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

KEY = "de89e95d58e40fb34f43173833d19fa009155003fd4a573a68a1f1cea6add92f"
HOST = "justicelibre.org"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"

# Endpoint IndexNow : on peut aller sur api.indexnow.org (qui dispatche vers
# tous les moteurs partenaires) OU sur un moteur spécifique. api.indexnow.org
# fait le travail de propagation.
INDEXNOW_ENDPOINT = "https://api.indexnow.org/IndexNow"

# Optionnel : aussi ping Bing direct (parfois plus rapide)
BING_ENDPOINT = "https://www.bing.com/IndexNow"

DB_PATHS = {
    "opendata": Path("/opt/justicelibre/dila/opendata.db"),  # al-uzza
    "judiciaire": Path("/opt/justicelibre/dila/judiciaire.db"),  # PROD
}


def submit_batch(urls: list[str], endpoint: str = INDEXNOW_ENDPOINT) -> tuple[int, str]:
    """Submit jusqu'à 10000 URLs en un appel. Renvoie (status_code, body)."""
    if not urls:
        return 0, "no urls"
    if len(urls) > 10000:
        urls = urls[:10000]
    # Filtre : toutes les URLs doivent être sur le même hôte
    urls = [u for u in urls if urlparse(u).hostname == HOST]
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }
    try:
        r = httpx.post(endpoint, json=payload, timeout=30.0,
                       headers={"Content-Type": "application/json; charset=utf-8"})
        return r.status_code, r.text[:200]
    except Exception as e:
        return -1, str(e)


def get_recent_decisions(hours: int = 24) -> list[str]:
    """Renvoie les URLs SSR des décisions récemment ajoutées dans les bulks."""
    cutoff = time.time() - hours * 3600
    cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff))
    urls = []

    # Opendata (al-uzza) : table opendata_decisions, fetched_at
    if DB_PATHS["opendata"].exists():
        try:
            with sqlite3.connect(f"file:{DB_PATHS['opendata']}?mode=ro", uri=True) as c:
                rows = c.execute(
                    "SELECT id FROM opendata_decisions WHERE fetched_at >= ? LIMIT 50000",
                    (cutoff_iso,),
                ).fetchall()
                urls.extend(f"https://{HOST}/decision/admin/{r[0]}" for r in rows)
        except Exception as e:
            print(f"[opendata] err: {e}")

    return urls


def bulk_from_sitemap() -> int:
    """Itère sur tout le sitemap-index et soumet par batches de 10k.

    Attention : limite de ~10k/jour observée. Ce mode envoie tout d'un coup,
    Bing va probablement ignorer le surplus mais conserver la trace.
    """
    sitemap_index = httpx.get(f"https://{HOST}/sitemap.xml", timeout=30.0).text
    import re
    sub_urls = re.findall(r'<loc>([^<]+)</loc>', sitemap_index)
    print(f"[bulk] {len(sub_urls)} sub-sitemaps à parcourir")
    submitted = 0
    for sub_url in sub_urls:
        try:
            sub_xml = httpx.get(sub_url, timeout=60.0).text
            page_urls = re.findall(r'<loc>([^<]+)</loc>', sub_xml)
            print(f"  {sub_url}: {len(page_urls)} URLs")
            for i in range(0, len(page_urls), 10000):
                batch = page_urls[i:i+10000]
                code, body = submit_batch(batch)
                print(f"    batch[{i}:{i+len(batch)}] -> HTTP {code}")
                submitted += len(batch)
                time.sleep(2)
        except Exception as e:
            print(f"  [err] {sub_url}: {e}")
    return submitted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, metavar="H",
                    help="Submit decisions added in last H hours")
    ap.add_argument("--bulk-from-sitemap", action="store_true",
                    help="Submit all URLs from sitemap-index (one-shot, ~hours)")
    ap.add_argument("--test", action="store_true",
                    help="Submit just the TA Lyon test URL")
    args = ap.parse_args()

    if args.test:
        urls = [f"https://{HOST}/decision/admin/DTA_2200433_20230214",
                f"https://{HOST}/loi/CASF/L262-8"]
        code, body = submit_batch(urls)
        print(f"test submit: HTTP {code} | {body}")
        return

    if args.bulk_from_sitemap:
        n = bulk_from_sitemap()
        print(f"\n[done] {n} URLs submitted")
        return

    if args.recent:
        urls = get_recent_decisions(args.recent)
        print(f"[recent {args.recent}h] {len(urls)} URLs trouvées")
        for i in range(0, len(urls), 10000):
            batch = urls[i:i+10000]
            code, body = submit_batch(batch)
            print(f"  batch[{i}:{i+len(batch)}] -> HTTP {code} | {body[:100]}")
        return

    # Stdin mode
    urls = [line.strip() for line in sys.stdin if line.strip().startswith("http")]
    if not urls:
        ap.print_help()
        return
    code, body = submit_batch(urls)
    print(f"submit {len(urls)} URLs -> HTTP {code} | {body[:200]}")


if __name__ == "__main__":
    main()
