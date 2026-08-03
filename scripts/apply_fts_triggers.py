#!/usr/bin/env python3
"""Applique les triggers FTS5 manquants (AU/AD) sur judiciaire.db.

Constat du 3 août 2026 : la prod n'a QUE les triggers AFTER INSERT
(decisions_ai, cedh_ai, cjue_ai, ariane_ai). Les corrections de la PR #8
(triggers complets ai/ad/au) vivent dans index_dila.py / scrape_ariane.py,
qui ne s'exécutent qu'à la (re)construction d'une base — jamais refaite sur
la prod. Conséquence : chaque upsert du sync quotidien (DELETE + INSERT)
laisse dans l'index FTS l'entrée de l'ancien rowid — orphelins accumulés,
résultats fantômes.

Ce script DROP + recrée les trois triggers de chaque fonds avec la liste de
colonnes ALIGNÉE SUR LE SCHÉMA FTS RÉEL (decisions_fts inclut
numero_rg_norm depuis le rebuild one-shot — colonne absente du trigger _ai
historique, donc non indexée pour toute ligne upsertée depuis).

⚠️ APRÈS ce script, lancer OBLIGATOIREMENT :
    python3 scripts/rebuild_fts.py --db /opt/justicelibre/dila/judiciaire.db
Tant que le rebuild n'a pas eu lieu, l'index mélange des lignes indexées
avec et sans numero_rg_norm : la commande 'delete' des nouveaux triggers
doit retrouver EXACTEMENT les valeurs indexées, sinon FTS5 se corrompt.
Ne pas laisser tourner le sync entre les deux étapes (cron à 4h30 UTC).

Usage :
    python3 scripts/apply_fts_triggers.py            # dry-run (défaut)
    python3 scripts/apply_fts_triggers.py --apply
"""
from __future__ import annotations

import argparse
import os
import sqlite3

DB = os.environ.get("JL_JUDICIAIRE_DB", "/opt/justicelibre/dila/judiciaire.db")

# (table de contenu, table FTS, colonnes indexées — ordre du CREATE VIRTUAL TABLE)
FONDS = [
    ("decisions", "decisions_fts",
     ["id", "titre", "juridiction", "solution", "numero", "formation",
      "text", "numero_rg_norm"]),
    ("cedh_decisions", "cedh_fts",
     ["itemid", "docname", "article", "conclusion", "text", "appno_norm"]),
    ("cjue_decisions", "cjue_fts",
     ["celex", "ecli", "title", "text", "affaire_num_norm"]),
    ("ariane_decisions", "ariane_fts",
     ["ariane_id", "text"]),
]


def trigger_sql(content: str, fts: str, cols: list[str]) -> list[tuple[str, str]]:
    base = content.split("_")[0] if content != "decisions" else "decisions"
    collist = ", ".join(cols)
    news = ", ".join(f"new.{c}" for c in cols)
    olds = ", ".join(f"old.{c}" for c in cols)
    return [
        (f"{base}_ai", f"""
            CREATE TRIGGER {base}_ai AFTER INSERT ON {content} BEGIN
                INSERT INTO {fts}(rowid, {collist})
                VALUES (new.rowid, {news});
            END"""),
        (f"{base}_ad", f"""
            CREATE TRIGGER {base}_ad AFTER DELETE ON {content} BEGIN
                INSERT INTO {fts}({fts}, rowid, {collist})
                VALUES ('delete', old.rowid, {olds});
            END"""),
        (f"{base}_au", f"""
            CREATE TRIGGER {base}_au AFTER UPDATE ON {content} BEGIN
                INSERT INTO {fts}({fts}, rowid, {collist})
                VALUES ('delete', old.rowid, {olds});
                INSERT INTO {fts}(rowid, {collist})
                VALUES (new.rowid, {news});
            END"""),
    ]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--apply", action="store_true",
                   help="applique réellement (défaut : dry-run)")
    args = p.parse_args()

    conn = sqlite3.connect(DB, timeout=120.0)
    try:
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        for content, fts, cols in FONDS:
            # Sanity : les colonnes annoncées existent bien des deux côtés.
            content_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({content})")}
            missing = [c for c in cols if c not in content_cols]
            if missing:
                print(f"✗ {content} : colonnes absentes {missing} — SKIP (schéma inattendu)")
                continue
            for name, sql in trigger_sql(content, fts, cols):
                verb = "remplacé" if name in existing else "créé"
                if args.apply:
                    conn.execute(f"DROP TRIGGER IF EXISTS {name}")
                    conn.execute(sql)
                    print(f"  ✓ {name} {verb}")
                else:
                    print(f"  · {name} serait {verb}")
        if args.apply:
            conn.commit()
            print("\nTriggers appliqués. ⚠️ LANCER MAINTENANT :")
            print(f"  python3 scripts/rebuild_fts.py --db {DB}")
        else:
            print("\n(dry-run — relancer avec --apply)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
