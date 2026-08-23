#!/usr/bin/env python3
"""Renomme les juridictions restées en code brut dans judiciaire.db.

CONTEXTE (23 août 2026) — l'ingestion Judilibre écrit le libellé lisible
(« Cour de cassation ») quand l'API renvoie le champ `jurisdiction` ET que
la taxonomie `data/judilibre_locations.json` connaît la `location`. Quand
ni l'un ni l'autre, elle laisse passer le CODE BRUT. Résultat mesuré sur la
prod : 560 492 lignes portent `juridiction = 'cc'`, contre le libellé
complet pour les lignes venues du bulk DILA.

Conséquence : le filtre `juridiction="cassation"` compare en
`LIKE '%Cour de cassation%'` et rate donc toutes les lignes « cc » — soit,
pour les seules décisions depuis 2024, 36 619 arrêts masqués contre 12 849
servis (74 %). Les plus récents, précisément.

Le code a été rendu tolérant aux deux écritures le 23 août (correctif
immédiat, sans écriture en base), et `judilibre_sync.py` a reçu un filet
pour ne plus en produire. Ce script s'attaque à la cause : remettre le bon
libellé sur les lignes existantes.

⚠️ ÉCRITURE EN BASE DE PRODUCTION. Par défaut ce script ne fait RIEN :
    --dry-run (défaut)  compte, échantillonne, n'écrit pas
    --backup-only       écrit uniquement la sauvegarde CSV.gz
    --apply             sauvegarde PUIS applique (refuse sans sauvegarde)

Les triggers FTS5 (ai/ad/au) posés le 5 août propagent l'UPDATE à
`decisions_fts` : aucune reconstruction d'index n'est nécessaire, mais un
UPDATE de 560 k lignes reste long — le lancer via
`systemd-run --unit=jl-backfill-cc` plutôt que dans un tuyau ssh.

Usage :
    python3 scripts/backfill_juridiction_cc.py --dry-run
    python3 scripts/backfill_juridiction_cc.py --apply
"""
from __future__ import annotations

import argparse
import csv
import gzip
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/opt/justicelibre/dila/judiciaire.db")
BACKUP_DIR = Path("/root/backups/justicelibre-prod")

# Codes bruts Judilibre → libellé attendu. Volontairement restreint : on ne
# renomme que ce qui est un code de juridiction NU, jamais un nom composé
# (« Cour d'appel de Paris » n'est pas concerné).
RENAMES = {
    "cc": "Cour de cassation",
    "ca": "Cour d'appel",
    "tj": "Tribunal judiciaire",
    "tcom": "Tribunal de commerce",
    "cph": "Conseil de prud'hommes",
}


def _connect(readonly: bool) -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode={'ro' if readonly else 'rw'}"
    conn = sqlite3.connect(uri, uri=True, timeout=120.0)
    conn.row_factory = sqlite3.Row
    return conn


def compter(conn) -> dict[str, int]:
    out = {}
    for code in RENAMES:
        n = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE juridiction = ?", (code,)
        ).fetchone()[0]
        if n:
            out[code] = n
    return out


def echantillon(conn, code: str, n: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, juridiction, date, numero, titre FROM decisions "
        "WHERE juridiction = ? LIMIT ?", (code, n)
    ).fetchall()


def sauvegarder(conn, codes: list[str]) -> Path:
    """Sauvegarde (id, juridiction) de chaque ligne touchée — permet un
    retour arrière exact, ligne par ligne, sans dumper 13 Go."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = BACKUP_DIR / f"juridictions_avant_backfill_{stamp}.csv.gz"
    ph = ", ".join("?" * len(codes))
    n = 0
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "juridiction_avant"])
        for row in conn.execute(
            f"SELECT id, juridiction FROM decisions WHERE juridiction IN ({ph})",
            codes,
        ):
            w.writerow([row["id"], row["juridiction"]])
            n += 1
    print(f"  sauvegarde : {path}  ({n} lignes)")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--backup-only", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"⛔ base introuvable : {DB_PATH} (à lancer sur la PROD)")
        return 2

    ecriture = args.apply or args.backup_only
    conn = _connect(readonly=not ecriture)
    try:
        compte = compter(conn)
        if not compte:
            print("✅ aucun code brut en base — rien à faire.")
            return 0

        print("Lignes portant un code de juridiction NU :")
        total = 0
        for code, n in sorted(compte.items(), key=lambda kv: -kv[1]):
            print(f"  {code!r:8} → {n:>8} lignes  (deviendrait {RENAMES[code]!r})")
            total += n
        print(f"  TOTAL : {total} lignes\n")

        for code in compte:
            print(f"Échantillon {code!r} :")
            for r in echantillon(conn, code):
                print(f"    {r['id']}  {r['date']}  n° {r['numero']}  {str(r['titre'])[:60]}")
            print()

        if args.dry_run and not ecriture:
            print("DRY RUN — rien n'a été écrit. Relancer avec --apply pour appliquer.")
            return 0

        chemin = sauvegarder(conn, list(compte))
        if args.backup_only:
            print("--backup-only : sauvegarde faite, aucune modification.")
            return 0

        if not chemin.exists() or chemin.stat().st_size == 0:
            print("⛔ sauvegarde absente ou vide — on n'écrit pas.")
            return 3

        print("\nApplication…")
        for code, attendu in RENAMES.items():
            if code not in compte:
                continue
            cur = conn.execute(
                "UPDATE decisions SET juridiction = ? WHERE juridiction = ?",
                (attendu, code),
            )
            print(f"  {code!r} → {attendu!r} : {cur.rowcount} lignes")
        conn.commit()

        restant = compter(conn)
        print(f"\nContrôle après écriture — codes bruts restants : {restant or 'aucun'}")
        return 0 if not restant else 4
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
