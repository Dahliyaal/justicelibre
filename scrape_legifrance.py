#!/usr/bin/env python3 -u
"""Scrape les codes consolidés français via l'API PISTE Legifrance.

Requiert : app PISTE souscrite à l'API Legifrance (en plus de Judilibre).
Strategy :
  1. Lister tous les codes en vigueur (/list/code)
  2. Pour chaque code, fetch la structure complète (/consult/code)
  3. Pour chaque article (feuille de l'arbre), fetch le texte (/consult/getArticle)
  4. Stocker dans articles_loi

Circuit breaker : N erreurs consécutives → stop.
"""
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

# ─── Secrets via .env ─────────────────────────────────────────
_env = Path(__file__).with_name(".env")
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

CLIENT_ID = os.environ.get("PISTE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("PISTE_CLIENT_SECRET", "")
if not CLIENT_ID or not CLIENT_SECRET:
    sys.exit("PISTE creds manquants (voir .env)")

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

SLEEP_BETWEEN = 0.2
MAX_CONSECUTIVE_ERRORS = 15


def get_token():
    r = httpx.post(OAUTH_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS codes (
        cid TEXT PRIMARY KEY,
        titre TEXT,
        titre_court TEXT,
        fetched_at TEXT
    );
    CREATE TABLE IF NOT EXISTS articles_loi (
        article_id TEXT PRIMARY KEY,          -- LEGIARTI000NNNNN
        code_cid TEXT,                        -- LEGITEXT000NNNNN
        code_titre_court TEXT,                -- "Code civil"
        num TEXT,                             -- "1240", "L.132-1", "R.222-1"
        titre TEXT,
        texte TEXT,
        etat TEXT,                            -- VIGUEUR, ABROGE, ...
        date_debut TEXT,
        date_fin TEXT,
        fetched_at TEXT,
        FOREIGN KEY(code_cid) REFERENCES codes(cid)
    );
    CREATE INDEX IF NOT EXISTS idx_art_code ON articles_loi(code_cid);
    CREATE INDEX IF NOT EXISTS idx_art_num ON articles_loi(code_titre_court, num);
    CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
        article_id UNINDEXED, code_titre_court, num, titre, texte,
        content='articles_loi', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS art_ai AFTER INSERT ON articles_loi BEGIN
        INSERT INTO articles_fts(rowid, article_id, code_titre_court, num, titre, texte)
        VALUES (new.rowid, new.article_id, new.code_titre_court, new.num, new.titre, new.texte);
    END;
    """)
    conn.commit()


def list_codes(client, headers):
    # Pagination pour récupérer tous les codes (~76 au total)
    all_codes = []
    page = 1
    while True:
        body = {"pageSize": 50, "pageNumber": page, "states": ["VIGUEUR"]}
        r = client.post(f"{BASE}/list/code", json=body, headers=headers, timeout=30)
        r.raise_for_status()
        d = r.json()
        batch = d.get("results", [])
        if not batch:
            break
        all_codes.extend(batch)
        if len(batch) < 50:
            break
        page += 1
    return all_codes


def consult_code(client, headers, cid):
    # /consult/code renvoie 500 "Exception non gérée" côté PISTE (bug serveur).
    # On utilise /consult/legi/tableMatieres qui retourne la même structure hiérarchique.
    from datetime import date as _d
    today = _d.today().isoformat()
    r = client.post(
        f"{BASE}/consult/legi/tableMatieres",
        json={"textId": cid, "date": today, "nature": "CODE"},
        headers=headers, timeout=60,
    )
    if r.status_code != 200:
        return None
    return r.json()


def walk_sections(node, articles_out):
    """DFS dans l'arbre code pour collecter tous les articles (feuilles)."""
    # Un nœud peut avoir sections[] et articles[]
    for art in node.get("articles", []) or []:
        articles_out.append(art)
    for sub in node.get("sections", []) or []:
        walk_sections(sub, articles_out)


def fetch_article(client, headers, article_id):
    r = client.post(f"{BASE}/consult/getArticle", json={"id": article_id}, headers=headers, timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get("article")


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=120000")
    ensure_schema(conn)

    existing = conn.execute("SELECT COUNT(*) FROM articles_loi").fetchone()[0]
    print(f"[legifrance] DB existing : {existing} articles")

    token = get_token()
    token_t = time.time()
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    client = httpx.Client()

    print("[legifrance] listing codes en vigueur…")
    codes = list_codes(client, headers)
    print(f"  → {len(codes)} codes récupérés")

    total_articles = 0
    consecutive_errors = 0

    for code in codes:
        cid = code.get("cid", "")
        titre = code.get("titre", "")
        titre_court = code.get("titreCourt", titre)
        print(f"\n=== {cid} · {titre_court} ===")
        conn.execute(
            "INSERT OR REPLACE INTO codes VALUES (?,?,?,datetime('now'))",
            (cid, titre, titre_court),
        )
        conn.commit()

        # Refresh token if needed
        if time.time() - token_t > 2700:
            token = get_token()
            token_t = time.time()
            headers["Authorization"] = f"Bearer {token}"

        try:
            code_data = consult_code(client, headers, cid)
        except Exception as e:
            consecutive_errors += 1
            print(f"  [err consult_code {cid}]: {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"\n*** CIRCUIT BREAKER ({MAX_CONSECUTIVE_ERRORS} errs) ***")
                sys.exit(2)
            time.sleep(min(60, 5 * consecutive_errors))
            continue
        consecutive_errors = 0
        if not code_data:
            continue

        # Collecter tous les articles du code (récursif)
        arts = []
        walk_sections(code_data, arts)
        print(f"  {len(arts)} articles à fetcher")

        for i, art_stub in enumerate(arts):
            art_id = art_stub.get("id")
            if not art_id:
                continue
            # Skip si déjà en DB avec texte
            existing_row = conn.execute(
                "SELECT length(texte) FROM articles_loi WHERE article_id=?", (art_id,)
            ).fetchone()
            if existing_row and existing_row[0] and existing_row[0] > 20:
                continue

            if time.time() - token_t > 2700:
                token = get_token()
                token_t = time.time()
                headers["Authorization"] = f"Bearer {token}"

            try:
                art = fetch_article(client, headers, art_id)
            except Exception as e:
                consecutive_errors += 1
                print(f"    [err art {art_id}]: {e}")
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n*** CIRCUIT BREAKER ***")
                    sys.exit(2)
                time.sleep(min(60, 5 * consecutive_errors))
                continue
            consecutive_errors = 0
            if not art:
                continue

            texte_html = art.get("texte") or art.get("texteHtml") or ""
            # Strip HTML simple
            texte = re.sub(r"<[^>]+>", " ", texte_html)
            texte = re.sub(r"\s+", " ", texte).strip()

            try:
                conn.execute(
                    "INSERT OR REPLACE INTO articles_loi VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
                    (
                        art_id, cid, titre_court,
                        art.get("num", ""),
                        art.get("titre", ""),
                        texte,
                        art.get("etat", ""),
                        str(art.get("dateDebut", "")),
                        str(art.get("dateFin", "")),
                    ),
                )
                total_articles += 1
                if total_articles % 100 == 0:
                    conn.commit()
                    print(f"    +{total_articles} articles indexés (code {cid})")
            except Exception as e:
                print(f"    [DB err] {e}")
            time.sleep(SLEEP_BETWEEN)

        conn.commit()

    final = conn.execute("SELECT COUNT(*) FROM articles_loi").fetchone()[0]
    print(f"\nDONE. Total articles : {final} (+{total_articles} cette session)")
    conn.close()


if __name__ == "__main__":
    main()
