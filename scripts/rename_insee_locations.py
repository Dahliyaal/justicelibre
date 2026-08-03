#!/usr/bin/env python3
"""Retrofit : remplace les codes de juridiction par leurs noms officiels.

L'ingestion Judilibre historique stockait les tribunaux judiciaires sous
leur code INSEE ("Tribunal judiciaire de 02691") et les tribunaux de
commerce sous leur code greffe ("tcom de 9301") : illisible, et introuvable
par ville (le bonus ville de citation_search ne peut jamais matcher).
map_to_row() utilise désormais data/judilibre_locations.json (taxonomie
officielle Judilibre) pour les NOUVELLES décisions ; ce script corrige le
stock existant (~56 000 lignes TJ + tcom, + les "Cour d'appel de Chambery"
générés par title() au lieu du nom accentué officiel).

Met à jour `juridiction` ET `titre` (le titre embarque le nom : "Tribunal
judiciaire de 02691, 2026-07-02, n° 26/00038").

PRÉREQUIS : les triggers decisions_au/_ad doivent exister (scripts/
apply_fts_triggers.py) et l'index avoir été reconstruit (scripts/
rebuild_fts.py) — sinon les UPDATE ne se propagent pas à l'index FTS
(l'ancien nom resterait cherchable et le nouveau non). Le script REFUSE de
tourner sans eux.

Usage :
    python3 scripts/rename_insee_locations.py            # dry-run (défaut)
    python3 scripts/rename_insee_locations.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("JL_JUDICIAIRE_DB", "/opt/justicelibre/dila/judiciaire.db")
LOCATIONS_PATH = os.path.join(_HERE, "..", "data", "judilibre_locations.json")


def old_name_for(code: str, official: str) -> str | None:
    """Reconstruit le nom EXACT que l'ancienne ingestion générait pour ce
    code — on ne renomme que sur correspondance exacte, jamais à l'aveugle."""
    if code.startswith("tj") and code[2:].isdigit():
        return f"Tribunal judiciaire de {code[2:]}"          # code INSEE
    if code.startswith("tj"):                                # tj2a004 (Corse)
        return f"Tribunal judiciaire de {code[2:]}"
    if code.isdigit():
        return f"tcom de {code}"                             # code greffe
    if code.startswith("ca_"):
        return f"Cour d'appel de {code[3:].replace('_', ' ').title()}"
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--apply", action="store_true",
                   help="applique réellement (défaut : dry-run)")
    args = p.parse_args()

    with open(LOCATIONS_PATH, encoding="utf-8") as f:
        locations: dict[str, str] = json.load(f)

    conn = sqlite3.connect(DB, timeout=300.0)
    conn.row_factory = sqlite3.Row
    try:
        triggers = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        if not {"decisions_au", "decisions_ad"} <= triggers:
            print("✗ triggers decisions_au/_ad absents — lancer d'abord "
                  "scripts/apply_fts_triggers.py --apply puis rebuild_fts.py")
            return 1

        total, renamed_codes = 0, 0
        for code, official in sorted(locations.items()):
            old = old_name_for(code, official)
            if not old or old == official:
                continue
            n = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE juridiction = ?",
                (old,)).fetchone()[0]
            if not n:
                continue
            total += n
            renamed_codes += 1
            if args.apply:
                conn.execute(
                    """UPDATE decisions
                       SET juridiction = ?,
                           titre = replace(titre, ?, ?)
                       WHERE juridiction = ?""",
                    (official, old, official, old))
                conn.commit()
                print(f"  ✓ {old!r} → {official!r} ({n} lignes)")
            else:
                sample = conn.execute(
                    "SELECT titre FROM decisions WHERE juridiction = ? LIMIT 1",
                    (old,)).fetchone()[0]
                print(f"  · {old!r} → {official!r} ({n} lignes) | ex: {sample[:70]}")

        print(f"\n{'Renommé' if args.apply else 'À renommer'} : "
              f"{total} lignes sur {renamed_codes} juridictions.")
        if not args.apply:
            print("(dry-run — relancer avec --apply)")

        if args.apply:
            # Sanity post-run : plus aucun code résiduel connu.
            leftovers = conn.execute(
                """SELECT COUNT(*) FROM decisions
                   WHERE juridiction GLOB 'Tribunal judiciaire de [0-9]*'
                      OR juridiction LIKE 'tcom de %'""").fetchone()[0]
            print(f"Codes résiduels (hors taxonomie) : {leftovers}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
