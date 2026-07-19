#!/usr/bin/env python3
"""Fix newlines pour les arrêts JURITEXT* avec 0 newline en DB PROD.

Stratégie :
1. SELECT JURITEXT* avec 0 newline et len > 100 (skip texts vides)
2. Pour chaque, recherche par numéro via API PISTE Judilibre
3. Si trouvé, UPDATE text avec la version qui a les newlines

Idempotent : ne re-traite pas les rows déjà fixées.
Resume-safe : check newlines au début de chaque iteration.
Run en background, log dans /tmp/fix_newlines.log.
"""
import os, sys, time, sqlite3, httpx

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
    cur = conn.cursor()
    # Sélection : JURITEXT avec 0 newline et texte non-vide
    rows = cur.execute("""
        SELECT id, numero, date FROM decisions
        WHERE id LIKE 'JURITEXT%'
          AND length(text) > 200
          AND length(text) - length(replace(text, char(10), '')) = 0
    """).fetchall()
    print(f"[fix] {len(rows)} arrêts JURITEXT à fixer (0 newline)")

    tok = get_token()
    H = {"Authorization": f"Bearer {tok}", "KeyId": PISTE_CLIENT_ID}
    client = httpx.Client(headers=H, timeout=30)
    SEARCH = "https://api.piste.gouv.fr/cassation/judilibre/v1.0/search"
    DETAIL = "https://api.piste.gouv.fr/cassation/judilibre/v1.0/decision"

    n_fixed = n_notfound = n_errors = 0
    t0 = time.time()
    for i, (did, numero, date) in enumerate(rows, 1):
        if not numero:
            n_notfound += 1
            continue
        try:
            # Search par numéro pourvoi
            r = client.get(SEARCH, params={"query": numero, "page_size": 5})
            if r.status_code == 401:
                tok = get_token()
                client.headers["Authorization"] = f"Bearer {tok}"
                r = client.get(SEARCH, params={"query": numero, "page_size": 5})
            if r.status_code != 200:
                n_errors += 1
                if n_errors > 100: break
                continue
            hits = r.json().get("results", [])
            # Match exact par numero ET date (si fourni)
            best = None
            for h in hits:
                if (h.get("number") or "").replace(".", "").replace("-", "") == numero.replace(".", "").replace("-", ""):
                    if not date or (h.get("decision_date") or "").startswith(date[:10]):
                        best = h
                        break
            if not best and hits:
                best = hits[0]
            if not best:
                n_notfound += 1
                continue
            # Fetch detail
            d = client.get(DETAIL, params={"id": best["id"]}).json()
            text = (d.get("text") or "").strip()
            if text and text.count("\n") > 0:
                cur.execute("UPDATE decisions SET text = ? WHERE id = ?", (text, did))
                n_fixed += 1
                if n_fixed % 50 == 0:
                    conn.commit()
            time.sleep(0.15)  # 5-7 req/s, polite
        except Exception as e:
            n_errors += 1
            if n_errors > 100:
                print(f"[abort] trop d'erreurs: {e}")
                break
            time.sleep(2)
        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta_min = (len(rows) - i) / rate / 60 if rate > 0 else 0
            print(f"  [{i}/{len(rows)}] fixed={n_fixed} notfound={n_notfound} err={n_errors} {rate:.1f} req/s ETA={eta_min:.0f}min")
    conn.commit()
    print(f"[done] fixed={n_fixed} notfound={n_notfound} err={n_errors} elapsed={time.time()-t0:.0f}s")
    # Rebuild FTS pour les rows updated
    if n_fixed > 0:
        print("[fts] rebuild...")
        conn.execute("INSERT INTO decisions_fts(decisions_fts) VALUES('rebuild')")
        conn.commit()
        print("[fts] done")
    conn.close()


if __name__ == "__main__":
    main()
