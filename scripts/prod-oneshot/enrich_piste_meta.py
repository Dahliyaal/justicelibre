#!/usr/bin/env python3
"""Pour chaque arrêt Cass moderne PROD (ID hex Judilibre), fetch /decision
et stocke summary/themes/visa/rapprochements/titlesAndSummaries/files/publication
dans une nouvelle table decisions_meta_piste.

Resume-safe : skippe les rows déjà enrichies.
"""
import os, sys, time, sqlite3, json, httpx

PISTE_CLIENT_ID = os.environ["PISTE_CLIENT_ID"]
PISTE_CLIENT_SECRET = os.environ["PISTE_CLIENT_SECRET"]
DB = "/opt/justicelibre/dila/judiciaire.db"

sys.stdout.reconfigure(line_buffering=True)


def get_token():
    return httpx.post("https://oauth.piste.gouv.fr/api/oauth/token",
        data={"grant_type": "client_credentials",
              "client_id": PISTE_CLIENT_ID,
              "client_secret": PISTE_CLIENT_SECRET,
              "scope": "openid"}, timeout=20).json()["access_token"]


def main():
    conn = sqlite3.connect(DB, timeout=300)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS decisions_meta_piste (
        decision_id TEXT PRIMARY KEY,
        summary TEXT,
        themes_json TEXT,
        visa_json TEXT,
        rapprochements_json TEXT,
        titles_summaries_json TEXT,
        files_json TEXT,
        publication TEXT,
        particular_interest INTEGER,
        zones_json TEXT,
        nac TEXT,
        partial INTEGER,
        update_date TEXT,
        fetched_at TEXT
    )""")
    conn.commit()
    # IDs Cass Judilibre moderne (hex) non encore enrichis
    rows = conn.execute("""
        SELECT id FROM decisions
        WHERE id NOT LIKE 'JURITEXT%'
          AND id NOT LIKE 'CETATEXT%'
          AND id NOT LIKE 'CONSTEXT%'
          AND id NOT IN (SELECT decision_id FROM decisions_meta_piste)
        ORDER BY date DESC
    """).fetchall()
    print(f"[piste-enrich] {len(rows)} arrêts à enrichir")

    tok = get_token()
    H = {"Authorization": f"Bearer {tok}", "KeyId": PISTE_CLIENT_ID}
    client = httpx.Client(headers=H, timeout=30)
    URL = "https://api.piste.gouv.fr/cassation/judilibre/v1.0/decision"

    n = 0
    n_errors = 0
    t0 = time.time()
    batch = []
    for (did,) in rows:
        try:
            r = client.get(URL, params={"id": did})
            if r.status_code == 401:
                # Token expired, refresh
                tok = get_token()
                client.headers["Authorization"] = f"Bearer {tok}"
                r = client.get(URL, params={"id": did})
            if r.status_code != 200:
                n_errors += 1
                if n_errors > 100:
                    print(f"[error] trop d'erreurs (100), arrêt")
                    break
                time.sleep(2)
                continue
            d = r.json()
            batch.append((
                did,
                d.get("summary") or "",
                json.dumps(d.get("themes") or [], ensure_ascii=False),
                json.dumps(d.get("visa") or [], ensure_ascii=False),
                json.dumps(d.get("rapprochements") or [], ensure_ascii=False),
                json.dumps(d.get("titlesAndSummaries") or [], ensure_ascii=False),
                json.dumps(d.get("files") or [], ensure_ascii=False),
                json.dumps(d.get("publication") or [], ensure_ascii=False),
                1 if d.get("particularInterest") else 0,
                json.dumps(d.get("zones") or {}, ensure_ascii=False),
                d.get("nac") or "",
                1 if d.get("partial") else 0,
                d.get("update_date") or "",
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ))
            n += 1
            if len(batch) >= 100:
                conn.executemany("""INSERT OR REPLACE INTO decisions_meta_piste
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", batch)
                conn.commit()
                batch = []
                elapsed = time.time() - t0
                rate = n / elapsed
                eta_min = (len(rows) - n) / rate / 60 if rate > 0 else 0
                print(f"  [{n}/{len(rows)}] {rate:.1f} req/s, ETA {eta_min:.0f}min, errors={n_errors}", flush=True)
            # Rate limit doux : 5 req/s ≈ 200ms
            time.sleep(0.15)
        except Exception as e:
            n_errors += 1
            if n_errors > 100:
                print(f"[error] trop d'erreurs, arrêt: {e}")
                break
            time.sleep(2)
    if batch:
        conn.executemany("""INSERT OR REPLACE INTO decisions_meta_piste
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", batch)
        conn.commit()
    print(f"[done] n={n} enrichis, errors={n_errors}, time={time.time()-t0:.0f}s")
    conn.close()


if __name__ == "__main__":
    main()
