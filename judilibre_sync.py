#!/usr/bin/env python3
"""Synchronisation Judilibre (PISTE) → judiciaire.db.

Deux modes :
- `--rgs RG1,RG2,...` : refetch ponctuel d'une liste de numéros RG (ex après
  réception d'un mail de notification de ré-anonymisation).
- `--history --since-hours N` : pagine /transactionalhistory depuis N heures
  en arrière et refetch chaque id ayant subi une création/modification.

Pour chaque décision récupérée via /decision?id=<hex> :
- si une ligne existe (matche RG ou même id) → UPDATE en place (conserve l'id
  JURITEXT historique pour ne pas casser les URLs publiques) + refresh FTS via
  DELETE + INSERT sous le même id.
- sinon INSERT avec l'id hex Judilibre.

Identifiants Judilibre = hex 24-char ; DILA bulk = JURITEXT*. Les deux
cohabitent dans la même table `decisions`.

Crédentiels PISTE PROD lus depuis enrich_piste_meta.py (même client).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

# Réutilise les crédentiels PROD du worker enrich_piste_meta.py
PISTE_CLIENT_ID = os.environ["PISTE_CLIENT_ID"]
PISTE_CLIENT_SECRET = os.environ["PISTE_CLIENT_SECRET"]
OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
JUDILIBRE_URL = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"
DB = "/opt/justicelibre/dila/judiciaire.db"

sys.stdout.reconfigure(line_buffering=True)


def get_token() -> str:
    r = httpx.post(
        OAUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": PISTE_CLIENT_ID,
            "client_secret": PISTE_CLIENT_SECRET,
            "scope": "openid",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def piste_get(client: httpx.Client, path: str, **params) -> dict:
    """GET PISTE avec 1 retry sur erreur transitoire."""
    last = None
    for attempt in range(2):
        try:
            r = client.get(f"{JUDILIBRE_URL}{path}", params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError,) as e:
            last = e
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise


def search_rg_to_ids(
    client: httpx.Client,
    rg: str,
    jurisdictions: tuple[str, ...] = ("cc", "ca", "tj"),
) -> list[str]:
    """Cherche un RG sur Judilibre /search dans cc, ca, tj et renvoie la
    liste de TOUS les ids hex dont le `number` correspond EXACTEMENT (ou
    figure dans `numbers`). Un même RG peut désigner plusieurs décisions
    (différentes CA/TJ partagent le numérotage)."""
    ids: list[str] = []
    seen: set[str] = set()
    for juri in jurisdictions:
        try:
            data = piste_get(client, "/search", query=rg, jurisdiction=juri, page_size=50)
        except Exception:
            continue
        for r in data.get("results") or []:
            if (r.get("number") == rg or rg in (r.get("numbers") or [])):
                jid = r.get("id")
                if jid and jid not in seen:
                    seen.add(jid)
                    ids.append(jid)
    return ids


def fetch_decision(client: httpx.Client, decision_id: str) -> dict | None:
    try:
        return piste_get(client, "/decision", id=decision_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise


def map_to_row(d: dict, conn: sqlite3.Connection, force_id: str | None = None) -> tuple[str, dict]:
    """Mappe la réponse PISTE /decision vers le format de la table `decisions`.

    Si `force_id` est fourni, on l'utilise comme PK (pour préserver l'id
    JURITEXT historique). Sinon on prend l'id hex Judilibre renvoyé.
    """
    new_id = force_id or d.get("id")
    text = "\n\n".join(d.get("text_html", "") and [d["text_html"]] or [d.get("text", "")]).strip()
    if not text:
        text = d.get("text", "") or ""
    # juridiction lisible (cc=Cour de cassation, ca=Cour d'appel, tj=TJ)
    juri_map = {"cc": "Cour de cassation", "ca": "Cour d'appel", "tj": "Tribunal judiciaire"}
    juri_base = juri_map.get(d.get("jurisdiction", ""), d.get("jurisdiction", ""))
    location = d.get("location", "") or ""
    # Nettoyage des codes location Judilibre : "ca_bordeaux" -> "Bordeaux",
    # "tj75056" -> "75056" (INSEE, pas idéal mais lisible).
    loc_display = location
    if location.startswith(("ca_", "tj_", "cc_")):
        loc_display = location[3:].replace("_", " ").title()
    elif location.startswith("tj") and location[2:].isdigit():
        loc_display = location[2:]  # INSEE
    juridiction = f"{juri_base} de {loc_display}" if loc_display and juri_base else juri_base or loc_display
    numero = d.get("number") or d.get("numbers", [""])[0] if d.get("numbers") else d.get("number", "")
    date = d.get("decision_date") or ""
    titre = f"{juridiction}, {date}, n° {numero}"
    rg_norm = ""
    if numero and "/" in numero:
        flat = numero.replace("/", "")
        dash = numero.replace("/", "-")
        rg_norm = f"{numero} {dash} {flat}"
    row = {
        "id": new_id,
        "nature": d.get("type") or "",
        "titre": titre,
        "date": date,
        "juridiction": juridiction,
        "solution": d.get("solution") or "",
        "numero": numero,
        "formation": d.get("chamber") or d.get("formation") or "",
        "ecli": d.get("ecli") or "",
        "president": d.get("president") or "",
        "avocats": "",
        "text": text,
        "sommaire": d.get("summary") or "",
        "abstrats": json.dumps(d.get("themes") or [], ensure_ascii=False),
        "resume": d.get("resume") or "",
        "renvois": json.dumps(d.get("rapprochements") or [], ensure_ascii=False),
        "rapporteur": d.get("rapporteur") or "",
        "commissaire_gvt": "",
        "type_rec": d.get("type") or "",
        "publi_recueil": "",
        "publi_bull": "oui" if d.get("publication") else "",
        "nature_qualifiee": d.get("nature") or "",
        "saisines": "",
        "loi_def": "",
        "liens_textes": "",
        "numero_rg_norm": rg_norm,
    }
    return new_id, row


def upsert(conn: sqlite3.Connection, row: dict) -> str:
    """DELETE + INSERT pour que le trigger AFTER INSERT refresh le FTS5.
    Renvoie 'updated' ou 'inserted'."""
    existing = conn.execute("SELECT 1 FROM decisions WHERE id = ?", (row["id"],)).fetchone()
    if existing:
        conn.execute("DELETE FROM decisions WHERE id = ?", (row["id"],))
        action = "updated"
    else:
        action = "inserted"
    cols = list(row.keys())
    conn.execute(
        f"INSERT INTO decisions ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
        [row[k] for k in cols],
    )
    conn.commit()
    return action


def find_existing_id_by_rg(conn: sqlite3.Connection, rg: str) -> str | None:
    """Cherche l'id existant pour un RG (pour préserver JURITEXT* si déjà ingéré)."""
    r = conn.execute(
        "SELECT id FROM decisions WHERE numero = ? OR numero_rg_norm LIKE ? LIMIT 1",
        (rg, f"%{rg}%"),
    ).fetchone()
    return r[0] if r else None


# ─── Modes ────────────────────────────────────────────────────────

def mode_rgs(conn: sqlite3.Connection, client: httpx.Client, rgs: list[str]) -> None:
    for rg in rgs:
        rg = rg.strip()
        if not rg:
            continue
        existing_id = find_existing_id_by_rg(conn, rg)
        # 1) chercher TOUS les ids Judilibre pour ce RG (plusieurs cours peuvent
        # partager un même numérotage : CA Bordeaux 21/05835 et CA Versailles
        # 21/05835 sont 2 décisions distinctes).
        try:
            jids = search_rg_to_ids(client, rg)
        except Exception as e:
            print(f"  [RG {rg}] search err: {e}")
            continue
        if not jids:
            print(f"  [RG {rg}] introuvable sur Judilibre")
            continue
        for i, jid in enumerate(jids):
            try:
                d = fetch_decision(client, jid)
            except Exception as e:
                print(f"  [RG {rg} #{i+1}/{len(jids)}] fetch err: {e}")
                continue
            if not d:
                continue
            # On ne réutilise existing_id QUE pour le 1er match (cas où on
            # rafraîchit une décision déjà ingérée). Les autres prennent leur id
            # hex Judilibre. Évite d'écraser un existing avec un autre arrêt.
            force_id = existing_id if i == 0 else None
            _, row = map_to_row(d, conn, force_id=force_id)
            action = upsert(conn, row)
            juri = row.get("juridiction", "?")
            print(f"  [RG {rg} #{i+1}/{len(jids)}] {action} ({juri}, {row.get('date','')}, len={len(row['text'])})")


def mode_history(conn: sqlite3.Connection, client: httpx.Client, since_hours: int) -> int:
    """Retourne 0 si succès, 1 si l'appel à /transactionalhistory échoue.
    Permet au wrapper shell de logger correctement OK vs error."""
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    print(f"[history] depuis {since}")
    params = {"date": since}
    seen, ok, fail = 0, 0, 0
    while True:
        try:
            data = piste_get(client, "/transactionalhistory", **params)
        except Exception as e:
            print(f"[history] err: {e}")
            return 1
        txs = data.get("transactions") or []
        for tx in txs:
            seen += 1
            decision_id = tx.get("id")
            op = tx.get("operation") or tx.get("type") or "?"
            if op == "delete":
                # suppression : on retire de notre base
                conn.execute("DELETE FROM decisions WHERE id = ?", (decision_id,))
                conn.commit()
                print(f"  [del] {decision_id}")
                ok += 1
                continue
            try:
                d = fetch_decision(client, decision_id)
            except Exception as e:
                print(f"  [err {decision_id}] {e}")
                fail += 1
                continue
            if not d:
                fail += 1
                continue
            existing = conn.execute("SELECT id FROM decisions WHERE id = ?", (decision_id,)).fetchone()
            _, row = map_to_row(d, conn, force_id=existing[0] if existing else None)
            upsert(conn, row)
            ok += 1
        next_page = data.get("next_page")
        if not next_page:
            break
        # next_page est une query string complète — la parser et l'utiliser
        from urllib.parse import parse_qs
        params = {k: v[0] for k, v in parse_qs(next_page.lstrip("?")).items()}
    print(f"[history] {seen} tx, {ok} ok, {fail} err")
    return 1 if fail and not ok else 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rgs", help="RG list (comma-separated)")
    p.add_argument("--history", action="store_true")
    p.add_argument("--since-hours", type=int, default=24)
    args = p.parse_args()
    if not args.rgs and not args.history:
        p.error("--rgs ou --history requis")
    conn = sqlite3.connect(DB, timeout=300)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA recursive_triggers=ON")  # INSERT OR REPLACE doit déclencher le trigger _ad du FTS5
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    rc = 0
    with httpx.Client(headers=headers) as client:
        if args.rgs:
            mode_rgs(conn, client, args.rgs.split(","))
        if args.history:
            rc = mode_history(conn, client, args.since_hours) or 0
    return rc


if __name__ == "__main__":
    sys.exit(main())
