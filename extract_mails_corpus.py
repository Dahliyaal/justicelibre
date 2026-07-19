#!/usr/bin/env python3
"""
Extrait TOUS les emails des textes de décisions (jurisprudence) — pur regex,
zéro LLM, zéro réseau. Streame les bases SQLite ligne par ligne (RAM constante,
même sur jade.db = 7,8 Go).

LECTURE SEULE : ouvre chaque base en mode=ro, n'écrit QUE le fichier de sortie.
Ne touche jamais au corpus ni au service. Sans danger pour la prod.

Usage (sur le serveur qui héberge les bases) :
  # PROD :
  python3 extract_mails_corpus.py \
      /opt/justicelibre/dila/judiciaire.db /opt/justicelibre/dila/capp.db \
      /opt/justicelibre/dila/constit.db /opt/justicelibre/dila/opendata.db
  # WAREHOUSE :
  python3 extract_mails_corpus.py /opt/justicelibre/dila/jade.db

Sortie : mails_corpus.csv  (mail ; nb ; source_db ; source_id ; juridiction ; date ; numero)
         + résumé par domaine sur stdout.
On garde 1 exemple de source par mail (le 1er vu) — suffisant pour citer la
décision-preuve ; le tri fin (fonctionnel vs perso, dédup DILA) se fait après.
"""
import re, sqlite3, sys, csv
from collections import defaultdict, Counter
from pathlib import Path

MAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TEXT_COLS = ["texte_integral", "full_text", "text", "texte", "contenu", "content"]


def norm(m):
    return m.lower().strip().strip(".,;:").replace("\xa0", "")


def tables_avec_texte(conn):
    """Rend [(table, text_col, cols_meta)] pour chaque table ayant une colonne texte."""
    out = []
    tabs = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    # on saute les tables-fantômes FTS5 (shadow) : elles dupliqueraient le texte
    SKIP = ("fts", "_data", "_idx", "_content", "_docsize", "_config", "_segments",
            "_segdir", "sqlite_")
    for t in tabs:
        if any(s in t.lower() for s in SKIP):
            continue
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')")]
        low = {c.lower(): c for c in cols}
        tcol = next((low[c] for c in TEXT_COLS if c in low), None)
        if not tcol:
            continue
        meta = {k: low.get(k) for k in ("id", "juridiction", "date", "numero")}
        out.append((t, tcol, meta))
    return out


def main():
    dbs = sys.argv[1:]
    if not dbs:
        sys.exit("usage: extract_mails_corpus.py <db1> [db2 ...]")

    mails = defaultdict(lambda: {"n": 0, "src": None})
    lignes_scannees = 0

    for db in dbs:
        p = Path(db)
        if not p.exists():
            print(f"  ! {db} absent — ignoré", file=sys.stderr)
            continue
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        for table, tcol, meta in tables_avec_texte(conn):
            idc = meta["id"] or "rowid"
            sel = f"{idc} AS _id, {meta['juridiction'] or 'NULL'} AS _jur, " \
                  f"{meta['date'] or 'NULL'} AS _date, {meta['numero'] or 'NULL'} AS _num, " \
                  f"{tcol} AS _txt"
            cur = conn.execute(f"SELECT {sel} FROM '{table}'")
            n_tab = 0
            for row in cur:
                lignes_scannees += 1
                n_tab += 1
                txt = row[4]
                if not txt:
                    continue
                for m in MAIL_RE.findall(txt):
                    m = norm(m)
                    e = mails[m]
                    e["n"] += 1
                    if e["src"] is None:
                        e["src"] = (p.name, row[0], row[1], row[2], row[3])
            print(f"  {p.name}::{table} — {n_tab:,} lignes, "
                  f"{len(mails):,} mails cumulés", file=sys.stderr)
        conn.close()

    # écriture
    out = Path("mails_corpus.csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["mail", "nb", "source_db", "source_id", "juridiction", "date", "numero"])
        for m, e in sorted(mails.items(), key=lambda kv: -kv[1]["n"]):
            db, i, jur, dt, num = e["src"]
            w.writerow([m, e["n"], db, i, jur or "", dt or "", num or ""])

    print(f"\n=== {lignes_scannees:,} décisions scannées ===")
    print(f"emails UNIQUES : {len(mails):,}  -> {out.resolve()}")
    dom = Counter(m.split("@")[-1] for m in mails)
    print("\nTop 20 domaines :")
    for d, n in dom.most_common(20):
        print(f"  {n:>6,}  {d}")
    justice = sum(1 for m in mails if re.search(r"justice\.fr$|justice\.gouv\.fr$", m))
    print(f"\n@justice.fr / @justice.gouv.fr : {justice:,} adresses uniques")


if __name__ == "__main__":
    main()
