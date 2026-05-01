#!/usr/bin/env python3 -u
"""Téléchargement progressif de tout le contenu opendata.justice-administrative.fr.

Le bulk DILA JADE qu'on a déjà ne contient que CE + 9 CAA. Les 40 Tribunaux
Administratifs (~1.5 M décisions) et beaucoup de CAA récents ne sont diffusés
QUE via cette API live. Personne ne les indexe (Dalloz, Lexis, Doctrine
n'ont que des bouts via partenariats). Si on les télécharge en bulk → c'est
nous qui les rendons indexables Google en premier.

API hidden Elasticsearch reverse-engineered (cf sources/juriadmin.py) :
  GET /recherche/api/model_search_juri/openData/{juri}/{query}/{limit}
  GET /recherche/api/elastic/decisions/{decision_id}/bm9TZWNvbmR2YWx1ZQ==

Limite : `limit` max = 10 000 hits par appel (ES default). Pour les juridictions
avec plus de 10k décisions (TA75 = 98k, TA69 = 38k, etc.) on partitionne
par année car le filename contient YYYYMMDD.

Usage :
  # 1. Lance en background sur al-uzza (ou n'importe où avec Internet)
  nohup python3 download_opendata.py > /var/log/dl_opendata.log 2>&1 &
  # 2. Suit la progression :
  tail -f /var/log/dl_opendata.log

Resumable : un état est sauvé dans `dl_opendata.state.json`. Si tu kill et
relances, ça repart où ça s'était arrêté.

Sortie : /opt/justicelibre/dila/opendata.db (SQLite). Une fois le DL fini,
faut ajouter "opendata" à FONDS dans warehouse_server.py + un /v1/enumerate
+ un /sitemap-opendata-N.xml côté token_server. Mais ça c'est pour après.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx

sys.stdout.reconfigure(line_buffering=True)

# Configuration
DB_PATH = Path("/opt/justicelibre/dila/opendata.db")
STATE_PATH = Path(__file__).with_name("dl_opendata.state.json")
LOG_EVERY_N = 100  # log every N decisions
RATE_LIMIT_SLEEP = 0.4  # seconds between API calls (≈ 2.5 req/s, poli)
LIMIT_PER_CALL = 10000  # max ES allows
TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# Toutes les juridictions (cf sources/juriadmin.py)
ALL_JURI = [
    # Conseil d'État
    "CE",
    # 9 Cours administratives d'appel
    "CAA13", "CAA31", "CAA33", "CAA44", "CAA54",
    "CAA59", "CAA69", "CAA75", "CAA78",
    # 40 Tribunaux administratifs
    "TA06", "TA13", "TA14", "TA20", "TA21", "TA25", "TA30", "TA31",
    "TA33", "TA34", "TA35", "TA38", "TA44", "TA45", "TA51", "TA54",
    "TA59", "TA63", "TA64", "TA67", "TA69", "TA75", "TA76", "TA77",
    "TA78", "TA80", "TA83", "TA86", "TA87", "TA93", "TA95",
    "TA101", "TA102", "TA103", "TA104", "TA105", "TA106", "TA107",
    "TA108", "TA109",
]

API_BASE = "https://opendata.justice-administrative.fr/recherche/api"
NO_SECOND = "bm9TZWNvbmR2YWx1ZQ=="
# Endpoint avec date filter natif découvert via reverse-engineering du
# frontend opendata.justice-administrative.fr (panel DevTools > Network).
# Format : /model_search_date_juri/openData/Date_Lecture/{q}/{juri}/{d_start}/{d_end}/{limit}
# Date format YYYY-MM-DD. Q="*" pour wildcard match-all.
DATE_API = f"{API_BASE}/model_search_date_juri/openData/Date_Lecture"

# Range d'années à crawler (l'opendata commence ~2009, on couvre large)
YEARS = list(range(2008, datetime.now().year + 2))


# ─── State persistence ──────────────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"done_partitions": [], "stats": {}}


def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ─── DB schema ──────────────────────────────────────────────────────

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH), timeout=120.0) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS opendata_decisions (
                id TEXT PRIMARY KEY,
                juridiction_code TEXT,
                juridiction_name TEXT,
                date TEXT,
                numero_dossier TEXT,
                ecli TEXT,
                formation TEXT,
                type_decision TEXT,
                publication_code TEXT,
                last_modified TEXT,
                texte TEXT,
                fetched_at TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_od_date ON opendata_decisions(date DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_od_juri ON opendata_decisions(juridiction_code)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_od_numero ON opendata_decisions(numero_dossier)")
        # FTS5 pour cohérence avec les autres bulks
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS opendata_fts USING fts5(
                id UNINDEXED, juridiction, numero_dossier, texte,
                content=''
            )
        """)
    print(f"[init] db ready: {DB_PATH}")


# ─── HTTP fetch ─────────────────────────────────────────────────────

def fetch_search(client: httpx.Client, juri: str, query: str, limit: int = LIMIT_PER_CALL,
                 date_start: str | None = None, date_end: str | None = None) -> dict | None:
    """Search par juri + query (+ optional date range).

    Si date_start/date_end fournis, utilise l'endpoint model_search_date_juri
    (date filter natif découvert via reverse-engineering frontend).
    Sinon, utilise model_search_juri (capacity limited à 10k sans pagination).
    """
    safe_q = quote(query, safe="")
    if date_start and date_end:
        url = f"{DATE_API}/{safe_q}/{juri}/{date_start}/{date_end}/{int(limit)}"
    else:
        url = f"{API_BASE}/model_search_juri/openData/{juri}/{safe_q}/{int(limit)}"
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.json().get("decisions", {}).get("body", {}).get("hits", {})
    except Exception as e:
        print(f"  [fetch_search err] {juri}/{query} ({date_start}..{date_end}): {e}")
        return None


def fetch_full_text(client: httpx.Client, decision_id: str) -> str | None:
    """Récupère le texte intégral d'une décision via l'endpoint detail."""
    url = f"{API_BASE}/elastic/decisions/{decision_id}/{NO_SECOND}"
    try:
        r = client.get(url)
        if r.status_code != 200:
            return None
        body = r.json().get("_source", {})
        # paragraph contient le texte avec $$$ comme séparateur
        return (body.get("paragraph") or "").replace("$$$", "\n\n")
    except Exception:
        return None


# ─── Ingest ─────────────────────────────────────────────────────────

def insert_decision(c: sqlite3.Connection, hit: dict, full_text: str | None):
    src = hit.get("_source", {})
    decision_id = src.get("Identification", "").removesuffix(".xml")
    if not decision_id:
        return False
    # last_modified est plus fiable que Date_Lecture pour le tri/lastmod sitemap
    date_for_sitemap = src.get("Date_Lecture") or src.get("lastModified", "")[:10]
    c.execute("""
        INSERT OR REPLACE INTO opendata_decisions
        (id, juridiction_code, juridiction_name, date, numero_dossier, ecli,
         formation, type_decision, publication_code, last_modified, texte, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        decision_id,
        src.get("Code_Juridiction"),
        src.get("Nom_Juridiction"),
        date_for_sitemap,
        src.get("Numero_Dossier"),
        src.get("Numero_ECLI") if src.get("Numero_ECLI") != "undefined" else None,
        src.get("Formation_Jugement"),
        src.get("Type_Decision"),
        src.get("Code_Publication"),
        src.get("lastModified"),
        full_text or "",
        datetime.utcnow().isoformat() + "Z",
    ))
    if full_text:
        c.execute("""
            INSERT OR REPLACE INTO opendata_fts(rowid, id, juridiction, numero_dossier, texte)
            VALUES ((SELECT rowid FROM opendata_decisions WHERE id = ?), ?, ?, ?, ?)
        """, (decision_id, decision_id, src.get("Nom_Juridiction") or "",
              src.get("Numero_Dossier") or "", full_text))
    return True


def crawl_partition(client: httpx.Client, juri: str, query: str, fetch_text: bool = True,
                    date_start: str | None = None, date_end: str | None = None) -> int:
    """Crawl une partition (juri + query/year + optional date range). Renvoie n.
    Si total > LIMIT_PER_CALL et qu'on a des dates, on récursivement
    sous-partitionne par moitié de la fenêtre temporelle (binary split).
    """
    hits_data = fetch_search(client, juri, query, date_start=date_start, date_end=date_end)
    if not hits_data:
        return 0
    hits = hits_data.get("hits", [])
    total = hits_data.get("total", {}).get("value", 0)
    if total > LIMIT_PER_CALL:
        if date_start and date_end and date_start != date_end:
            # Binary split : divise la fenêtre date en deux
            from datetime import date as _d
            try:
                ds = _d.fromisoformat(date_start); de = _d.fromisoformat(date_end)
                mid_days = (de - ds).days // 2
                mid = ds.fromordinal(ds.toordinal() + mid_days)
                mid_next = ds.fromordinal(ds.toordinal() + mid_days + 1)
                print(f"  ↻ {juri}/{date_start}..{date_end}: {total} > {LIMIT_PER_CALL}, split sur {mid}")
                n1 = crawl_partition(client, juri, query, fetch_text, str(ds), str(mid))
                time.sleep(RATE_LIMIT_SLEEP)
                n2 = crawl_partition(client, juri, query, fetch_text, str(mid_next), str(de))
                return n1 + n2
            except Exception as e:
                print(f"  [split err] {e}")
                return -total
        else:
            print(f"  ⚠ {juri}/{query}: {total} > {LIMIT_PER_CALL}, pas de date range pour split")
            return -total
    n = 0
    with sqlite3.connect(str(DB_PATH), timeout=120.0) as c:
        for hit in hits:
            src = hit.get("_source", {})
            decision_id = src.get("Identification", "").removesuffix(".xml")
            if not decision_id:
                continue
            text = None
            if fetch_text:
                text = fetch_full_text(client, decision_id)
                time.sleep(RATE_LIMIT_SLEEP)
            if insert_decision(c, hit, text):
                n += 1
            if n % LOG_EVERY_N == 0:
                c.commit()
                print(f"    {juri}/{query}/{date_start}: {n}/{len(hits)} ingestés")
        c.commit()
    return n


def main(fetch_text: bool = True):
    """Orchestrateur principal v2.

    Utilise le date filter natif (model_search_date_juri) découvert
    par reverse-engineering du frontend. Partitionne par mois → chaque
    partition < 10k presque toujours. Si dépassement → binary split
    automatique sur la fenêtre date (récursif).

    Couverture théorique : ~100% des décisions opendata exposées.
    """
    init_db()
    state = load_state()
    done = set(state["done_partitions"])
    print(f"[start] resume: {len(done)} partitions déjà faites")
    print(f"[start] fetch_text={fetch_text}")
    months = []
    for y in YEARS:
        for m in range(1, 13):
            months.append((y, m))
    print(f"[start] target: {len(ALL_JURI)} juridictions × {len(months)} mois = ~{len(ALL_JURI)*len(months)} partitions max")

    from calendar import monthrange
    with httpx.Client(timeout=TIMEOUT,
                      headers={"User-Agent": "justicelibre-crawler/1.0 (+https://justicelibre.org)"}) as client:
        for juri in ALL_JURI:
            for y, m in months:
                last_day = monthrange(y, m)[1]
                d_start = f"{y}-{m:02d}-01"
                d_end = f"{y}-{m:02d}-{last_day:02d}"
                pk = f"{juri}/{y}-{m:02d}"
                if pk in done:
                    continue
                time.sleep(RATE_LIMIT_SLEEP)
                n = crawl_partition(client, juri, "*", fetch_text=fetch_text,
                                    date_start=d_start, date_end=d_end)
                state["stats"][pk] = max(0, n)
                state["done_partitions"].append(pk)
                save_state(state)
                if n != 0:
                    print(f"  [{pk}] DONE: {n} décisions")
    print("\n[end] tout fini.")
    print(f"[end] total ingéré: {sum(v for v in state['stats'].values() if v > 0)} décisions")


if __name__ == "__main__":
    # Par défaut on télécharge JUSTE les métadonnées (rapide ~2-3 jours).
    # Pour récupérer aussi le texte intégral : python3 download_opendata.py --text
    fetch_text = "--text" in sys.argv
    main(fetch_text=fetch_text)
