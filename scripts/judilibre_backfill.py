#!/usr/bin/env python3
"""Rattrapage Judilibre par lots (/export) : décisions manquantes ET champs manquants.

Pourquoi (8 septembre 2026) : la synchro quotidienne n'a jamais rattrapé ce
qui précède janvier 2026. Mesuré contre les totaux de Judilibre lui-même :
CA 630 313 / nous 138 252 ; TJ 718 530 / nous 230 916 ; tcom 175 351 /
100 798 — un million de décisions absentes. Et les lignes ingérées depuis
janvier n'ont pas les champs zones/visa/nac/titrage (colonne judilibre_meta,
ajoutée le même jour).

Ce script parcourt `/export` (lots de 1 000, décisions complètes avec texte)
sur une juridiction et une plage de dates de décision, et UPSERT chaque
décision via la même `map_to_row` que la synchro (DELETE + INSERT, les
triggers FTS5 suivent). Il est :
  - REPRENABLE : l'état (prochain lot) est écrit dans un fichier JSON après
    chaque lot ; relancer la même commande reprend là où on s'est arrêté ;
  - PRUDENT : refuse de continuer sous 4 Go de disque libre ; s'arrête sur
    429 en respectant Retry-After ; ré-authentifie sur 401 ;
  - SILENCIEUX SUR RIEN : compte inséré / mis à jour / inchangé, et compare à
    la fin le total Judilibre de la plage au nombre de lignes en base.

Dry-run par défaut. Écriture = --apply. Lancer sur la PROD, depuis
/opt/justicelibre, via systemd-run (jamais nohup+&) :

    systemd-run --unit=jl-backfill-ca-2023 --setenv=JL_ENV=prod \\
      /usr/bin/python3 /opt/justicelibre/scripts/judilibre_backfill.py \\
      --jurisdiction ca --date-start 2023-01-01 --date-end 2023-12-31 --apply

Journal : journalctl -u jl-backfill-ca-2023 -f
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/opt/justicelibre")
os.chdir("/opt/justicelibre")
for _line in Path("/opt/justicelibre/.env").read_text().splitlines():
    if "=" in _line and not _line.strip().startswith("#"):
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

import httpx  # noqa: E402

import judilibre_sync as JS  # noqa: E402  (get_token, map_to_row, JUDILIBRE_URL)

DB = "/opt/justicelibre/dila/judiciaire.db"
STATE_DIR = Path("/var/lib/justicelibre/backfill")
MIN_FREE_GO = 4.0
BATCH_SIZE = 1000


def libre_go(path: str = "/mnt/digesta") -> float:
    return shutil.disk_usage(path).free / 1024 ** 3


def export_batch(client: httpx.Client, batch: int, juri: str, d1: str, d2: str, size: int) -> dict:
    """Un lot /export, avec ré-authentification sur 401 et attente sur 429."""
    for attempt in range(4):
        r = client.get(f"{JS.JUDILIBRE_URL}/export", params={
            "batch": batch, "batch_size": size, "jurisdiction": juri,
            "date_start": d1, "date_end": d2}, timeout=180)
        if r.status_code == 401 and attempt == 0:
            client.headers["Authorization"] = f"Bearer {JS.get_token()}"
            continue
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "30"))
            print(f"  429, attente {wait}s", flush=True)
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"export batch {batch} : échec après 4 tentatives")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", required=True, choices=["cc", "ca", "tj", "tcom"])
    ap.add_argument("--date-start", required=True)
    ap.add_argument("--date-end", required=True)
    ap.add_argument("--apply", action="store_true", help="écrit en base (défaut : essai à blanc)")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--max-batches", type=int, default=0, help="0 = tout ; utile pour un essai")
    args = ap.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(headers={"Authorization": f"Bearer {JS.get_token()}"})
    conn = sqlite3.connect(DB, timeout=600)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA recursive_triggers=ON")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Judilibre plafonne /export à 10 000 décisions par requête (lot 10 → 416,
    # constaté le 8 septembre 2026 sur ca 2022 : 75 268 annoncées). On coupe
    # donc la plage en deux, récursivement, jusqu'à passer sous le plafond.
    plages = decouper(client, args.jurisdiction, args.date_start, args.date_end, args.batch_size)
    if len(plages) > 1:
        print(f"plage découpée en {len(plages)} sous-plages (plafond 10 000/requête) : "
              f"{plages[0][0]}→{plages[0][1]} … {plages[-1][0]}→{plages[-1][1]}", flush=True)
    rc = 0
    for (d1, d2) in plages:
        rc = traiter(args, client, conn, d1, d2)
        if rc:
            break
    conn.close()
    return rc


PLAFOND = 9500


def total_plage(client, juri, d1, d2) -> int:
    return int(export_batch(client, 0, juri, d1, d2, 1).get("total") or 0)


def decouper(client, juri, d1, d2, size) -> list[tuple[str, str]]:
    from datetime import date as _date, timedelta as _td
    t = total_plage(client, juri, d1, d2)
    if t <= PLAFOND or d1 >= d2:
        return [(d1, d2)]
    a, b = _date.fromisoformat(d1), _date.fromisoformat(d2)
    m = a + (b - a) / 2
    m1, m2 = m.isoformat(), (m + _td(days=1)).isoformat()
    return decouper(client, juri, d1, m1, size) + decouper(client, juri, m2, d2, size)


def traiter(args, client, conn, d1, d2) -> int:
    state_path = STATE_DIR / f"{args.jurisdiction}_{d1}_{d2}.json"
    state = json.loads(state_path.read_text()) if (state_path.exists() and args.apply) else {}
    if state.get("done"):
        print(f"  {d1}→{d2} déjà terminé ({state['stats']}), sauté", flush=True)
        return 0
    batch = int(state.get("next_batch", 0))
    stats = state.get("stats", {"inserted": 0, "updated": 0, "unchanged": 0, "errors": 0})
    first = export_batch(client, batch, args.jurisdiction, d1, d2, args.batch_size)
    total = int(first.get("total") or 0)
    nb_batches = (total + args.batch_size - 1) // args.batch_size
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"{stamp} {args.jurisdiction} {d1}→{d2} : Judilibre annonce {total} décisions "
          f"({nb_batches} lots de {args.batch_size}) ; reprise au lot {batch} ; "
          f"{'ÉCRITURE' if args.apply else 'ESSAI À BLANC'} ; disque libre {libre_go():.1f} Go", flush=True)
    if not args.apply:
        res = first.get("results") or []
        ids = [d.get("id") for d in res]
        deja = 0
        if ids:
            ph = ",".join("?" * len(ids))
            deja = conn.execute(f"SELECT COUNT(*) FROM decisions WHERE id IN ({ph})", ids).fetchone()[0]
        print(f"  1er lot : {len(res)} décisions, dont {deja} déjà en base (seraient mises à jour), "
              f"{len(res) - deja} nouvelles (seraient insérées).")
        for d in res[:3]:
            _, row = JS.map_to_row(d, conn)
            print(f"    ex. {row['id']} {row['juridiction']} {row['date']} n°{row['numero']} "
                  f"texte {len(row['text']) // 1024} Ko meta {len(row['judilibre_meta'])} o")
        print("  DRY RUN — rien n'a été écrit. Relancer avec --apply.")
        return 0

    data = first
    done_batches = 0
    t0 = time.time()
    while True:
        res = data.get("results") or []
        if not res:
            break
        if libre_go() < MIN_FREE_GO:
            print(f"⛔ disque libre < {MIN_FREE_GO} Go — arrêt propre au lot {batch} (reprenable)", flush=True)
            state_path.write_text(json.dumps({"next_batch": batch, "stats": stats, "total": total}))
            return 3
        try:
            for d in res:
                try:
                    new_id, row = JS.map_to_row(d, conn)
                    ex = conn.execute("SELECT judilibre_meta, length(text) FROM decisions WHERE id = ?", (new_id,)).fetchone()
                    if ex and ex[0] == row["judilibre_meta"] and ex[1] == len(row["text"]):
                        stats["unchanged"] += 1
                        continue
                    if ex:
                        conn.execute("DELETE FROM decisions WHERE id = ?", (new_id,))
                        stats["updated"] += 1
                    else:
                        stats["inserted"] += 1
                    cols = list(row.keys())
                    conn.execute(f"INSERT INTO decisions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                                 [row[k] for k in cols])
                except Exception as e:  # une décision cassée ne doit pas tuer le lot
                    stats["errors"] += 1
                    print(f"  ! {d.get('id')} : {type(e).__name__}: {e}", flush=True)
            conn.commit()
        except sqlite3.OperationalError as e:
            conn.rollback()
            print(f"⛔ base : {e} — arrêt au lot {batch} (reprenable)", flush=True)
            state_path.write_text(json.dumps({"next_batch": batch, "stats": stats, "total": total}))
            return 4
        batch += 1
        done_batches += 1
        state_path.write_text(json.dumps({"next_batch": batch, "stats": stats, "total": total}))
        if done_batches % 5 == 0 or batch >= nb_batches:
            el = time.time() - t0
            print(f"  lot {batch}/{nb_batches}  +{stats['inserted']} ins, {stats['updated']} maj, "
                  f"{stats['unchanged']} inchangées, {stats['errors']} err  "
                  f"({el / 60:.1f} min, {done_batches * args.batch_size / max(el, 1):.0f} déc/s, "
                  f"disque {libre_go():.1f} Go)", flush=True)
        if args.max_batches and done_batches >= args.max_batches:
            print(f"  --max-batches atteint, arrêt au lot {batch} (reprenable)")
            break
        if not data.get("next_batch") or batch >= nb_batches:
            break
        data = export_batch(client, batch, args.jurisdiction, d1, d2, args.batch_size)

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    state_path.write_text(json.dumps({"next_batch": batch, "stats": stats, "total": total, "done": True}))
    print(f"TERMINÉ {args.jurisdiction} {d1}→{d2} : "
          f"{stats['inserted']} insérées, {stats['updated']} mises à jour, "
          f"{stats['unchanged']} inchangées, {stats['errors']} erreurs — "
          f"Judilibre annonçait {total}.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
