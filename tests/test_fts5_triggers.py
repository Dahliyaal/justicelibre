"""Test suite for FTS5 external-content integrity on re-import.

Verrouille le correctif du bug d'index FTS5 : sur une table external-content
(content='…'), un `INSERT OR REPLACE` réassigne un nouveau rowid et laissait
l'ancienne entrée FTS orpheline — recherche corrompue, voire crash
`fts5: missing row from content table`. Le correctif = triggers _ad/_au +
`PRAGMA recursive_triggers=ON` sur les connexions d'écriture.

Deux niveaux de test, tous OFFLINE (SQLite en mémoire, aucune base de prod) :
1. cohérence statique — tout trigger `_ai AFTER INSERT` d'un fichier source
   doit avoir ses `_ad AFTER DELETE` et `_au AFTER UPDATE` frères ;
2. comportemental — on rejoue le scénario de ré-importation sur les deux
   patterns réels (external-content à triggers, et contentless d'opendata) et
   on prouve l'absence d'orphelin.

Run :
    python3 -m pytest tests/test_fts5_triggers.py -v
ou :
    python3 tests/test_fts5_triggers.py
"""
import os
import re
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

# Fichiers qui créent des tables FTS5 external-content à triggers.
TRIGGER_FILES = [
    "scrape_cedh.py", "scrape_cjue.py", "scrape_ariane.py",
    "index_dila.py", "scrape_legifrance.py", "parse_dila_bulk.py",
]
# Writers dont les connexions doivent activer recursive_triggers.
WRITER_FILES = TRIGGER_FILES + [
    "scrape_cedh_gaps.py", "rescrape_cedh.py", "judilibre_sync.py",
]


def _src(name: str) -> str:
    with open(os.path.join(_ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_every_ai_trigger_has_ad_and_au():
    """Pour chaque `CREATE TRIGGER … <stem>_ai AFTER INSERT ON <base>`, les
    triggers `<stem>_ad AFTER DELETE ON <base>` et `<stem>_au AFTER UPDATE ON
    <base>` doivent exister dans le même fichier."""
    problems = []
    ai_re = re.compile(
        r"CREATE TRIGGER IF NOT EXISTS\s+(\S+?)_ai\s+AFTER INSERT ON\s+(\S+)",
        re.IGNORECASE,
    )
    for name in TRIGGER_FILES:
        src = _src(name)
        for stem, base in ai_re.findall(src):
            for suffix, action in (("_ad", "AFTER DELETE"), ("_au", "AFTER UPDATE")):
                pat = re.compile(
                    rf"CREATE TRIGGER IF NOT EXISTS\s+{re.escape(stem)}{suffix}\s+"
                    rf"{action} ON\s+{re.escape(base)}",
                    re.IGNORECASE,
                )
                if not pat.search(src):
                    problems.append(f"{name}: {stem}_ai sur {base} sans {stem}{suffix}")
    assert not problems, "triggers FTS incomplets :\n  " + "\n  ".join(problems)


def test_writers_enable_recursive_triggers():
    """Chaque writer FTS doit activer recursive_triggers (sinon le DELETE
    implicite d'un INSERT OR REPLACE ne déclenche pas le trigger _ad)."""
    missing = [
        name for name in WRITER_FILES
        if "PRAGMA recursive_triggers=ON" not in _src(name)
    ]
    assert not missing, "writers sans recursive_triggers :\n  " + "\n  ".join(missing)


# ─── Comportemental : pattern external-content à triggers (cedh) ──────

_CEDH_SCHEMA = """
CREATE TABLE cedh_decisions(
    itemid TEXT PRIMARY KEY, docname, ecli, date, doctype,
    article, conclusion, importance, respondent, text
);
CREATE VIRTUAL TABLE cedh_fts USING fts5(
    itemid UNINDEXED, docname, article, conclusion, text,
    content='cedh_decisions', content_rowid='rowid'
);
CREATE TRIGGER cedh_ai AFTER INSERT ON cedh_decisions BEGIN
    INSERT INTO cedh_fts(rowid, itemid, docname, article, conclusion, text)
    VALUES (new.rowid, new.itemid, new.docname, new.article, new.conclusion, new.text);
END;
CREATE TRIGGER cedh_ad AFTER DELETE ON cedh_decisions BEGIN
    INSERT INTO cedh_fts(cedh_fts, rowid, itemid, docname, article, conclusion, text)
    VALUES ('delete', old.rowid, old.itemid, old.docname, old.article, old.conclusion, old.text);
END;
CREATE TRIGGER cedh_au AFTER UPDATE ON cedh_decisions BEGIN
    INSERT INTO cedh_fts(cedh_fts, rowid, itemid, docname, article, conclusion, text)
    VALUES ('delete', old.rowid, old.itemid, old.docname, old.article, old.conclusion, old.text);
    INSERT INTO cedh_fts(rowid, itemid, docname, article, conclusion, text)
    VALUES (new.rowid, new.itemid, new.docname, new.article, new.conclusion, new.text);
END;
"""


def test_external_content_no_orphan_on_replace_and_update():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA recursive_triggers=ON")  # indispensable (cf. writers)
    conn.executescript(_CEDH_SCHEMA)
    # même itemid ré-importé (INSERT OR REPLACE) puis mis à jour (UPDATE).
    for t in ("texte_alpha", "texte_beta", "texte_gamma"):
        conn.execute(
            "INSERT OR REPLACE INTO cedh_decisions(itemid, docname, article, "
            "conclusion, text) VALUES('X1','n','a','c',?)", (t,))
    conn.execute("UPDATE cedh_decisions SET text='texte_delta' WHERE itemid='X1'")

    for stale in ("texte_alpha", "texte_beta", "texte_gamma"):
        n = conn.execute("SELECT count(*) FROM cedh_fts WHERE cedh_fts MATCH ?",
                         (stale,)).fetchone()[0]
        assert n == 0, f"orphelin FTS sur terme périmé {stale!r} : {n} hit(s)"
    # une recherche qui LIT les colonnes ne doit pas crasher (missing row).
    rows = conn.execute(
        "SELECT itemid, text FROM cedh_fts WHERE cedh_fts MATCH 'texte_delta'"
    ).fetchall()
    assert rows == [("X1", "texte_delta")], rows
    # integrity-check natif FTS5.
    conn.execute("INSERT INTO cedh_fts(cedh_fts) VALUES('integrity-check')")


def test_external_content_orphans_without_recursive_triggers():
    """Contre-preuve : sans le PRAGMA, les orphelins réapparaissent — c'est ce
    qui rend le PRAGMA indispensable (et pas seulement les triggers)."""
    conn = sqlite3.connect(":memory:")  # recursive_triggers=OFF (défaut)
    conn.executescript(_CEDH_SCHEMA)
    for t in ("alpha", "beta"):
        conn.execute(
            "INSERT OR REPLACE INTO cedh_decisions(itemid, docname, article, "
            "conclusion, text) VALUES('X1','n','a','c',?)", (t,))
    orphan = conn.execute(
        "SELECT count(*) FROM cedh_fts WHERE cedh_fts MATCH 'alpha'").fetchone()[0]
    assert orphan == 1, "le PRAGMA serait inutile — revérifier l'hypothèse du fix"


# ─── Comportemental : pattern contentless maintenu à la main (opendata) ──

def test_opendata_contentless_no_orphan_on_reimport():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE opendata_decisions(id TEXT PRIMARY KEY, juridiction_name,
            numero_dossier, texte);
        CREATE VIRTUAL TABLE opendata_fts USING fts5(
            id UNINDEXED, juridiction, numero_dossier, texte, content='');
    """)

    def upsert(texte):  # réplique la logique corrigée de download_opendata
        old = conn.execute(
            "SELECT rowid, id, juridiction_name, numero_dossier, texte "
            "FROM opendata_decisions WHERE id = ?", ("D1",)).fetchone()
        if old and old[4]:
            conn.execute(
                "INSERT INTO opendata_fts(opendata_fts, rowid, id, juridiction, "
                "numero_dossier, texte) VALUES ('delete', ?, ?, ?, ?, ?)", old)
        conn.execute("INSERT OR REPLACE INTO opendata_decisions"
                     "(id, juridiction_name, numero_dossier, texte) "
                     "VALUES('D1','CE','123',?)", (texte,))
        conn.execute("INSERT OR REPLACE INTO opendata_fts(rowid, id, juridiction, "
                     "numero_dossier, texte) VALUES "
                     "((SELECT rowid FROM opendata_decisions WHERE id='D1'),"
                     "'D1','CE','123',?)", (texte,))

    for t in ("alpha", "beta", "gamma"):
        upsert(t)
    for stale in ("alpha", "beta"):
        n = conn.execute("SELECT count(*) FROM opendata_fts WHERE opendata_fts MATCH ?",
                         (stale,)).fetchone()[0]
        assert n == 0, f"orphelin FTS opendata sur {stale!r} : {n}"
    n = conn.execute("SELECT count(*) FROM opendata_fts WHERE opendata_fts MATCH 'gamma'").fetchone()[0]
    assert n == 1, n


# ─── Runner sans pytest ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("chaque _ai a _ad + _au",                 test_every_ai_trigger_has_ad_and_au),
        ("writers activent recursive_triggers",    test_writers_enable_recursive_triggers),
        ("external-content sans orphelin",         test_external_content_no_orphan_on_replace_and_update),
        ("contre-preuve sans le PRAGMA",           test_external_content_orphans_without_recursive_triggers),
        ("opendata contentless sans orphelin",     test_opendata_contentless_no_orphan_on_reimport),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            print(f"  ✗ {name}")
            print(f"      {e}")
            failed += 1
    if failed:
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
