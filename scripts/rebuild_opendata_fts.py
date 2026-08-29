#!/usr/bin/env python3
"""Reconstruit l'index plein texte du fonds opendata (TA/CAA).

CONTEXTE (29 août 2026) — `opendata_fts` était déclaré CONTENTLESS
(`content=''`) et VIDE : 985 996 décisions de tribunaux administratifs et de
cours administratives d'appel dans la table de contenu, **zéro** ligne dans
l'index, aucun trigger. Toute recherche plein texte sur ce fonds renvoyait
donc 0 résultat — silencieusement, puisqu'un index vide répond « aucun
résultat » exactement comme une requête sans correspondance.

Un FTS5 contentless ne peut pas être reconstruit (`'rebuild'` est refusé) :
il faut le recréer en mode CONTENU EXTERNE, adossé à `opendata_decisions`,
puis le remplir et poser les trois triggers (_ai/_ad/_au) pour qu'il suive
les écritures futures — l'absence de _ad/_au est la cause de la dérive
constatée sur les autres fonds de l'entrepôt.

⚠️ ÉCRIT EN BASE. Sauvegarde obligatoire avant (voir --help).
    --dry-run (défaut) : diagnostic seul
    --apply            : recrée, remplit, pose les triggers
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

DB = Path("/opt/justicelibre/dila/opendata.db")
CONTENU = "opendata_decisions"
FTS = "opendata_fts"
# ⚠️ En contenu externe, les colonnes de l'index doivent porter EXACTEMENT
# le nom qu'elles ont dans la table source : SQLite construit lui-même le
# `SELECT <colonnes> FROM <contenu>` du remplissage. La déclaration d'origine
# nommait la colonne `juridiction` alors que la table porte
# `juridiction_name` — d'où l'échec « no such column: T.juridiction ».
# Aucune requête du warehouse ne filtre par nom de colonne (pas de syntaxe
# `juridiction:…`), le renommage est donc sans effet de bord.
COLS = ["id", "juridiction_name", "numero_dossier", "texte"]
SOURCE = {k: k for k in COLS}


def diagnostic(c: sqlite3.Connection) -> tuple[int, int]:
    n = c.execute(f"SELECT COUNT(*) FROM {CONTENU}").fetchone()[0]
    try:
        f = c.execute(f"SELECT COUNT(*) FROM {FTS}").fetchone()[0]
    except sqlite3.OperationalError:
        f = -1
    decl = c.execute(
        "SELECT sql FROM sqlite_master WHERE name=?", (FTS,)).fetchone()
    trg = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'")]
    print(f"  décisions          : {n}")
    print(f"  lignes indexées    : {'(table absente)' if f < 0 else f}")
    sans_contenu = bool(decl) and "content=''" in decl[0]
    print(f"  contentless        : {'oui' if sans_contenu else 'non'}")
    print(f"  triggers           : {trg or 'AUCUN'}")
    return n, f


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not DB.exists():
        print(f"⛔ base absente : {DB} (à lancer sur l'entrepôt)")
        return 2

    c = sqlite3.connect(str(DB), timeout=600.0)
    try:
        print("État avant :")
        n, _ = diagnostic(c)
        if not a.apply:
            print("\nDRY RUN — rien écrit. Relancer avec --apply.")
            return 0

        cols = ", ".join(COLS)
        news = ", ".join(f"new.{SOURCE[k]}" for k in COLS)
        olds = ", ".join(f"old.{SOURCE[k]}" for k in COLS)
        select = ", ".join(SOURCE[k] for k in COLS)

        print("\nRecréation de l'index en contenu externe…")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA cache_size=-262144")
        c.executescript(f"""
        DROP TRIGGER IF EXISTS opendata_ai;
        DROP TRIGGER IF EXISTS opendata_ad;
        DROP TRIGGER IF EXISTS opendata_au;
        DROP TABLE IF EXISTS {FTS};
        CREATE VIRTUAL TABLE {FTS} USING fts5(
            id UNINDEXED, juridiction_name, numero_dossier, texte,
            content='{CONTENU}', content_rowid='rowid'
        );
        """)
        c.commit()

        t0 = time.time()
        print("Remplissage (peut prendre plusieurs dizaines de minutes)…")
        c.execute(f"INSERT INTO {FTS}({FTS}) VALUES('rebuild')")
        c.commit()
        print(f"  rempli en {time.time() - t0:.0f}s")

        print("Pose des trois triggers…")
        c.executescript(f"""
        CREATE TRIGGER opendata_ai AFTER INSERT ON {CONTENU} BEGIN
            INSERT INTO {FTS}(rowid, {cols}) VALUES (new.rowid, {news});
        END;
        CREATE TRIGGER opendata_ad AFTER DELETE ON {CONTENU} BEGIN
            INSERT INTO {FTS}({FTS}, rowid, {cols})
            VALUES ('delete', old.rowid, {olds});
        END;
        CREATE TRIGGER opendata_au AFTER UPDATE ON {CONTENU} BEGIN
            INSERT INTO {FTS}({FTS}, rowid, {cols})
            VALUES ('delete', old.rowid, {olds});
            INSERT INTO {FTS}(rowid, {cols}) VALUES (new.rowid, {news});
        END;
        """)
        c.commit()

        print("\nÉtat après :")
        n2, f2 = diagnostic(c)
        essai = c.execute(
            f"SELECT COUNT(*) FROM {FTS} WHERE {FTS} MATCH 'urbanisme'"
        ).fetchone()[0]
        print(f"\n  contrôle : « urbanisme » → {essai} décisions")
        return 0 if (f2 == n2 and essai > 0) else 3
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
