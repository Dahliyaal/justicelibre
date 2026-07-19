#!/usr/bin/env python3
"""Fix newlines pour JURITEXT* PROD via async PISTE Judilibre.

Stratégie speed-up :
- Async httpx + asyncio
- Semaphore 16 workers concurrents
- Pas de search, on lookup direct par numero (économise 1 req/arrêt)
- Batch UPDATE en SQL chunks
"""
import os, sys, time, sqlite3, asyncio
import httpx

PISTE_CLIENT_ID = os.environ["PISTE_CLIENT_ID"]
PISTE_CLIENT_SECRET = os.environ["PISTE_CLIENT_SECRET"]
DB = "/opt/justicelibre/dila/judiciaire.db"
CONCURRENCY = 16

sys.stdout.reconfigure(line_buffering=True)


def get_token():
    return httpx.post("https://oauth.piste.gouv.fr/api/oauth/token",
        data={"grant_type": "client_credentials",
              "client_id": PISTE_CLIENT_ID,
              "client_secret": PISTE_CLIENT_SECRET,
              "scope": "openid"}, timeout=20).json()["access_token"]


async def search_then_detail(client, sem, numero, date):
    """Search par numero puis fetch detail. Retourne text avec newlines, ou None."""
    async with sem:
        try:
            r = await client.get(
                "https://api.piste.gouv.fr/cassation/judilibre/v1.0/search",
                params={"query": numero, "page_size": 5},
            )
            if r.status_code != 200:
                return None
            hits = r.json().get("results", []) or []
            num_clean = numero.replace(".", "").replace("-", "") if numero else ""
            best = None
            for h in hits:
                hn = (h.get("number") or "").replace(".", "").replace("-", "")
                if hn == num_clean:
                    if not date or (h.get("decision_date") or "").startswith(date[:10]):
                        best = h
                        break
            if not best and hits:
                best = hits[0]
            if not best:
                return None
            r2 = await client.get(
                "https://api.piste.gouv.fr/cassation/judilibre/v1.0/decision",
                params={"id": best["id"]},
            )
            if r2.status_code != 200:
                return None
            text = (r2.json().get("text") or "").strip()
            if text and "\n" in text:
                return text
        except Exception:
            return None
    return None


async def main():
    conn = sqlite3.connect(DB, timeout=300)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    rows = conn.execute("""
        SELECT id, numero, date FROM decisions
        WHERE id LIKE 'JURITEXT%'
          AND length(text) > 200
          AND length(text) - length(replace(text, char(10), '')) = 0
          AND numero IS NOT NULL AND numero != ''
    """).fetchall()
    print(f"[fix-async] {len(rows)} JURITEXT* à fixer", flush=True)

    tok = get_token()
    H = {"Authorization": f"Bearer {tok}", "KeyId": PISTE_CLIENT_ID}
    sem = asyncio.Semaphore(CONCURRENCY)

    n_done = 0
    n_fixed = 0
    n_notfound = 0
    n_err = 0
    t0 = time.time()
    cur = conn.cursor()

    async with httpx.AsyncClient(headers=H, timeout=30, 
                                  limits=httpx.Limits(max_connections=CONCURRENCY*2)) as client:
        # Process en chunks de CHUNK pour limiter mémoire et committer régulièrement
        CHUNK = 200
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i+CHUNK]
            tasks = [search_then_detail(client, sem, num, dt)
                     for (_, num, dt) in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (did, num, dt), text in zip(chunk, results):
                n_done += 1
                if isinstance(text, Exception):
                    n_err += 1
                elif text is None:
                    n_notfound += 1
                elif text:
                    cur.execute("UPDATE decisions SET text = ? WHERE id = ?", (text, did))
                    n_fixed += 1
            conn.commit()
            elapsed = time.time() - t0
            rate = n_done / elapsed if elapsed > 0 else 0
            eta_min = (len(rows) - n_done) / rate / 60 if rate > 0 else 0
            print(f"  [{n_done}/{len(rows)}] fixed={n_fixed} notfound={n_notfound} err={n_err} {rate:.1f} req/s ETA={eta_min:.0f}min", flush=True)
            # Si trop d'erreurs auth, refresh token
            if n_err > 0 and n_done % 1000 == 0:
                tok = get_token()
                client.headers["Authorization"] = f"Bearer {tok}"
    print(f"[done] processed={n_done} fixed={n_fixed} notfound={n_notfound} err={n_err} elapsed={time.time()-t0:.0f}s")
    if n_fixed > 0:
        print("[fts] rebuild...")
        conn.execute("INSERT INTO decisions_fts(decisions_fts) VALUES('rebuild')")
        conn.commit()
        print("[fts] done")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
