"""Purge les étiquettes non résolues du thésaurus (« <inconnu 37-04-04-02> »).

POURQUOI (30 août 2026)
───────────────────────
`scripts/reconstruct_pcja.py` écrit `<inconnu {code}>` quand il ne sait pas
nommer un code de nomenclature. Ces chaînes ont été stockées dans
`thesaurus_labels` comme si c'étaient de vrais libellés, puis servies comme
SYNONYMES par le moteur d'expansion — et envoyées telles quelles dans les
requêtes FTS5 des utilisateurs.

Constaté sur un usage réel : la requête « … déni de justice responsabilité
État » était réécrite en

    (responsabilité OR "<inconnu 37-04-04-02>" OR dommage OR …)

Le site cherchait donc des décisions contenant « inconnu 37-04-04-02 ».

Mesuré le 30 août 2026 : **3 526 étiquettes sur 29 755 (11,8 %)**.

Ce script les supprime. Un concept qui n'aurait plus AUCUNE étiquette est
supprimé aussi — il n'est plus atteignable ni nommable.

Le moteur filtre également ces valeurs à la lecture
(`thesaurus_engine._EST_ETIQUETTE_INVALIDE`) : la purge nettoie la donnée,
le filtre garantit qu'une donnée douteuse ne peut plus atteindre une requête.
Les deux, pas l'un ou l'autre.

Usage :
    python3 scripts/purge_thesaurus_inconnus.py                 # simulation
    python3 scripts/purge_thesaurus_inconnus.py --apply         # purge
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

DB_DEFAUT = os.environ.get("THESAURUS_DB", "/opt/justicelibre/thesaurus/thesaurus.db")
MOTIF = "<%>"  # LIKE : commence par '<' et finit par '>'


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=DB_DEFAUT)
    p.add_argument("--apply", action="store_true",
                   help="supprime réellement (sans ce drapeau : simulation)")
    args = p.parse_args()

    if not os.path.exists(args.db):
        print(f"✗ base introuvable : {args.db}")
        return 2

    # Compte AVANT, en lecture seule — on regarde avant de toucher.
    ro = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    total = ro.execute("SELECT COUNT(*) FROM thesaurus_labels").fetchone()[0]
    vises = ro.execute(
        "SELECT COUNT(*) FROM thesaurus_labels WHERE label LIKE ?", (MOTIF,)
    ).fetchone()[0]
    exemples = [r[0] for r in ro.execute(
        "SELECT label FROM thesaurus_labels WHERE label LIKE ? LIMIT 5", (MOTIF,)
    ).fetchall()]
    ro.close()

    print(f"base       : {args.db}")
    print(f"étiquettes : {total}")
    print(f"à purger   : {vises} ({100.0 * vises / total:.1f} %)")
    for e in exemples:
        print(f"   ex. {e}")

    if not vises:
        print("\n✓ rien à purger.")
        return 0

    if not args.apply:
        print("\n⚠️  SIMULATION — rien n'a été supprimé. Relancer avec --apply.")
        return 0

    # Sauvegarde AVANT toute suppression, sans exception.
    horo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sauvegarde = f"{args.db}.bak_{horo}"
    shutil.copy2(args.db, sauvegarde)
    print(f"\nsauvegarde : {sauvegarde}")

    conn = sqlite3.connect(args.db, timeout=120.0)
    try:
        cur = conn.execute("DELETE FROM thesaurus_labels WHERE label LIKE ?", (MOTIF,))
        supprimes = cur.rowcount
        # Un concept sans plus aucune étiquette n'est ni nommable ni
        # atteignable : il ne peut plus que polluer les jointures.
        orphelins = conn.execute("""
            DELETE FROM thesaurus_concepts
            WHERE NOT EXISTS (
                SELECT 1 FROM thesaurus_labels l
                WHERE l.source = thesaurus_concepts.source
                  AND l.code = thesaurus_concepts.code)
        """).rowcount if _a_colonnes(conn) else 0
        conn.commit()
    finally:
        conn.close()

    print(f"étiquettes supprimées : {supprimes}")
    print(f"concepts orphelins    : {orphelins}")

    ro = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    reste = ro.execute(
        "SELECT COUNT(*) FROM thesaurus_labels WHERE label LIKE ?", (MOTIF,)
    ).fetchone()[0]
    neuf = ro.execute("SELECT COUNT(*) FROM thesaurus_labels").fetchone()[0]
    ro.close()
    print(f"contrôle              : {reste} restantes, {neuf} étiquettes au total")
    return 0 if reste == 0 else 1


def _a_colonnes(conn) -> bool:
    """`thesaurus_concepts` a-t-elle bien (source, code) ? On ne suppose pas."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(thesaurus_concepts)")}
    return {"source", "code"}.issubset(cols)


if __name__ == "__main__":
    sys.exit(main())
