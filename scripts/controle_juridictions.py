#!/usr/bin/env python3
"""Contrôle de nuit : une écriture de juridiction NOUVELLE en base est signalée.

Pourquoi (8 septembre 2026) : les filtres traduisent une demande en écritures
EXACTES (data/juridictions_map.json). Si la DILA livre demain une 114ᵉ façon
d'écrire « CAA de Lyon », les décisions concernées restent cherchables sans
filtre, mais le filtre CAA69 ne les verrait plus — en silence. Ce script
compte, chaque nuit, les écritures que la carte ne connaît pas.

Lecture seule. Sortie : une ligne par écriture inconnue, et un code retour
non nul s'il y en a (pour que le log soit lisible d'un coup d'œil).

Usage :
    python3 scripts/controle_juridictions.py --fond jade --db /opt/justicelibre/dila/jade.db
    python3 scripts/controle_juridictions.py --fond judiciaire --db /opt/justicelibre/dila/judiciaire.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import juridictions  # noqa: E402

TABLES = {"jade": "jade_decisions", "judiciaire": "decisions"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fond", choices=TABLES, required=True)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT juridiction, COUNT(*) FROM {TABLES[args.fond]} "
            "GROUP BY juridiction ORDER BY 2 DESC"
        ).fetchall()
    finally:
        conn.close()

    if args.fond == "jade":
        connues = juridictions.ecritures_admin_connues()
        inconnues = [(j, n) for j, n in rows if j not in connues]
    else:
        # Judiciaire : seules les familles filtrables comptent (cassation, appel,
        # tj, tcom, constit). Prud'hommes, TASS, proximité… n'ont pas de filtre
        # et ne sont donc pas « à signaler » : on ne rapporte que les écritures
        # qui RESSEMBLENT à une famille sans y tomber (une casse ou un accent
        # nouveau sur « Cour d'appel », par exemple).
        familles = juridictions.charger()["judiciaire"]
        prefixes = [p for e in familles.values() for p in e.get("prefixes", [])]
        exacts = {x for e in familles.values() for x in e.get("exact", [])}
        def suspecte(j: str) -> bool:
            nj = juridictions.normaliser(j)
            return (nj in {juridictions.normaliser(x) for x in exacts}
                    or any(nj.startswith(juridictions.normaliser(p)) for p in prefixes))
        inconnues = [(j, n) for j, n in rows
                     if (j or "") not in exacts
                     and not juridictions.ecritures_judiciaires_reconnues(j or "")
                     and suspecte(j or "")]

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not inconnues:
        print(f"{stamp} {args.fond}: {len(rows)} écritures, toutes connues de la carte ✅")
        return 0
    print(f"{stamp} {args.fond}: ⚠️ {len(inconnues)} écriture(s) INCONNUE(S) de la carte "
          f"— à ajouter dans data/juridictions_map.json :")
    for j, n in inconnues:
        print(f"    {n:>8}  {j!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
