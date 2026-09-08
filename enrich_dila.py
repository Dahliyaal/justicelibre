"""Enrichit a posteriori les décisions DILA déjà en base : abstrats (SCT),
résumé (ANA), renvois (CITATION_JP), rapporteur, commissaire_gvt, type_rec,
publi_recueil, publi_bull, nature_qualifiee / saisines / loi_def (CONSTIT),
liens_textes.

⚠️ RÔLE RÉDUIT DEPUIS SEPTEMBRE 2026. `parse_dila_bulk.py` remplit désormais
ces colonnes LUI-MÊME, à l'ingestion, donc aussi sur les deltas quotidiens.
Ce script ne sert plus qu'à rattraper des lignes DÉJÀ en base sans les
ré-insérer (pas de churn FTS5 sur `texte`). Trois choses ont dû être corrigées
pour qu'il ne DÉGRADE pas ce que le parseur écrit maintenant :

 1. il extrayait les SCT SANS leur attribut @TYPE (PRINCIPAL / REFERENCE) ;
    on réutilise désormais `juris_enrich()` de `parse_dila_bulk.py`, une seule
    définition pour les deux chemins ;
 2. il écrivait les 12 colonnes SANS CONDITION : une valeur vide écrasait une
    valeur pleine. L'UPDATE ne remplace plus une valeur par du vide ;
 3. il refusait le fond `inca` (`choices=[…]`, sans inca), dont les 11
    colonnes sémantiques n'étaient donc alimentées par rien.

Il ne cherchait par ailleurs QUE le tarball global (`Freemium_<fond>_global_*`),
d'où : aucune décision postérieure au 13/07/2025 n'était jamais enrichie.
`--tarball` permet désormais de viser n'importe quelle archive.

Usage:
    python3 enrich_dila.py <fond>   # jade | capp | constit | cass | inca
    python3 enrich_dila.py <fond> --tarball /chemin/X.tar.gz --db /chemin/x.db
    python3 enrich_dila.py <fond> --tsv /tmp/cass_enrich.tsv   # export TSV
"""
import argparse
import os
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

import lxml.etree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parse_dila_bulk import (  # noqa: E402
    JURIS_ENRICH_COLS,
    first_elt,
    juris_enrich,
    xml_text,
)

sys.stdout.reconfigure(line_buffering=True)

BULK_DIR = Path("/opt/justicelibre/dila_bulk")
DB_DIR = Path("/opt/justicelibre/dila")

# Une SEULE définition des colonnes sémantiques, partagée avec le parseur :
# deux listes divergentes, c'était la porte ouverte à ce que l'un écrase
# l'autre. `rapporteur` s'y ajoute, car ce script sait aussi le rattraper.
NEW_COLS = list(JURIS_ENRICH_COLS) + [("rapporteur", "TEXT")]


def alter_table(conn: sqlite3.Connection, table: str):
    """Ajoute les colonnes manquantes (idempotent)."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    added = []
    for col, typ in NEW_COLS:
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            added.append(col)
    conn.commit()
    print(f"[{table}] added cols: {added or '(none, already up to date)'}")


def extract_fields(root, fond: str) -> dict:
    """Extrait toutes les nouvelles colonnes depuis un XML root.

    L'extraction elle-même vit dans `parse_dila_bulk.juris_enrich()` : le
    parseur et ce script doivent produire EXACTEMENT la même chose, sinon
    celui qui passe en second dégrade le travail du premier (c'était le cas
    pour `abstrats`, dont l'attribut @TYPE n'était conservé que d'un côté)."""
    meta_spec = first_elt(root.find(".//META_JURI_JUDI"),
                          root.find(".//META_JURI_ADMIN"),
                          root.find(".//META_JURI_CONSTIT"))
    out = juris_enrich(root, meta_spec)
    out["rapporteur"] = xml_text(meta_spec.find("RAPPORTEUR")) if meta_spec is not None else ""
    return out


def has_any_value(fields: dict) -> bool:
    return any(v for v in fields.values())


def enrich(fond: str, dry_run: bool = False, tsv_path: str | None = None,
           limit: int | None = None, tarball: str | None = None,
           db: str | None = None):
    table = f"{fond}_decisions"
    db_path = Path(db) if db else DB_DIR / f"{fond}.db"

    if not db_path.exists() or db_path.stat().st_size < 100_000:
        print(f"[{fond}] DB missing or empty: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-262144")  # 256 MB
    conn.execute("PRAGMA temp_store=MEMORY")

    if not dry_run:
        alter_table(conn, table)

    # ⚠️ Sans --tarball, on ne voit QUE l'archive globale (juillet 2025) :
    # aucune décision postérieure n'était donc jamais enrichie.
    if tarball:
        tarball = Path(tarball)
    else:
        candidates = sorted(BULK_DIR.glob(f"Freemium_{fond}_global_*.tar.gz"))
        if not candidates:
            candidates = sorted(BULK_DIR.glob(f"Freemium_{fond}.tar.gz"))
        if not candidates:
            print(f"[{fond}] no Freemium tarball found in {BULK_DIR}", file=sys.stderr)
            sys.exit(1)
        tarball = candidates[-1]
    print(f"[{fond}] using bulk: {tarball.name} ({tarball.stat().st_size / 2**20:.0f} MB)")

    # Existing IDs (pour ne UPDATE que ce qui existe déjà)
    print(f"[{fond}] loading existing IDs…")
    existing_ids = set(r[0] for r in conn.execute(f"SELECT id FROM {table}"))
    print(f"[{fond}] {len(existing_ids)} existing rows in {table}")

    update_cols = [c for c, _ in NEW_COLS]
    # ⚠️ NE JAMAIS REMPLACER UNE VALEUR PAR DU VIDE. L'ancien UPDATE écrivait
    # les 12 colonnes sans condition : passé APRÈS le parseur réparé (qui les
    # remplit désormais à l'ingestion), il effaçait tout ce que ce dernier
    # avait trouvé et que lui ne sait pas extraire pour ce fond.
    set_clause = ", ".join(
        f"{c}=CASE WHEN ? <> '' THEN ? ELSE {c} END" for c in update_cols)
    update_sql = f"UPDATE {table} SET {set_clause} WHERE id=?"

    tsv_f = open(tsv_path, "w", encoding="utf-8") if tsv_path else None
    if tsv_f:
        tsv_f.write("id\t" + "\t".join(update_cols) + "\n")

    n_seen = 0
    n_matched = 0
    n_with_data = 0
    n_errors = 0
    n_updated = 0
    batch = []
    BATCH_SIZE = 500
    start = time.time()

    def flush():
        nonlocal batch, n_updated
        if not batch or dry_run:
            batch = []
            return
        conn.executemany(update_sql, batch)
        conn.commit()
        n_updated += len(batch)
        batch = []

    print(f"[{fond}] streaming XML…")
    with tarfile.open(tarball, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".xml"):
                continue
            n_seen += 1
            if limit and n_seen > limit:
                break
            try:
                f = tar.extractfile(member)
                if f is None:
                    continue
                root = ET.fromstring(f.read())
            except Exception:
                n_errors += 1
                continue
            try:
                meta = root.find(".//META_COMMUN")
                if meta is None:
                    continue
                did = xml_text(meta.find("ID"))
                if not did:
                    continue
                if did not in existing_ids:
                    # Ne pas créer de nouvelles lignes dans cette passe
                    continue
                n_matched += 1
                fields = extract_fields(root, fond)
                if has_any_value(fields):
                    n_with_data += 1
                # Chaque colonne est liée DEUX fois : le CASE WHEN ? <> ''
                # THEN ? du SET ci-dessus.
                values = tuple(v for c in update_cols
                               for v in (fields[c], fields[c])) + (did,)
                batch.append(values)
                if tsv_f:
                    row = [did] + [fields[c].replace("\t", " ").replace("\n", " ⏎ ")
                                   for c in update_cols]
                    tsv_f.write("\t".join(row) + "\n")
                if len(batch) >= BATCH_SIZE:
                    flush()
                    if n_matched % 5000 == 0:
                        elapsed = time.time() - start
                        rate = n_matched / elapsed
                        print(f"  [{n_matched:>7} matched / {n_with_data:>7} with-data / {n_errors} err] "
                              f"{rate:.0f}/s ({elapsed/60:.1f}min)")
            except Exception as e:
                n_errors += 1

    flush()
    if tsv_f:
        tsv_f.close()

    elapsed = time.time() - start
    print(f"[{fond}] DONE. seen={n_seen} matched={n_matched} with_data={n_with_data} "
          f"updated={n_updated} errors={n_errors} time={elapsed/60:.1f}min")

    # Quick verify
    if not dry_run:
        for col in ("abstrats", "resume", "renvois"):
            if col in {c for c, _ in NEW_COLS}:
                non_empty = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"
                ).fetchone()[0]
                print(f"  [{fond}] {col}: {non_empty} non-empty / {len(existing_ids)} total")

    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    # « inca » manquait : ses 11 colonnes sémantiques existaient au schéma mais
    # n'étaient alimentées par RIEN.
    p.add_argument("fond", choices=["jade", "cass", "capp", "constit", "inca"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--tsv", help="Export en TSV en plus du UPDATE")
    p.add_argument("--limit", type=int)
    p.add_argument("--tarball", help="archive à lire (défaut : le global du fond)")
    p.add_argument("--db", help="base à enrichir (défaut : DB_DIR/<fond>.db)")
    args = p.parse_args()
    enrich(args.fond, dry_run=args.dry_run, tsv_path=args.tsv, limit=args.limit,
           tarball=args.tarball, db=args.db)
