#!/usr/bin/env python3
"""
Construit la base SQLite unifiée des 4 thésaurus juridiques :
  - PCJA reconstruit depuis JADE (admin)
  - EuroVoc 4.x SKOS-RDF (UE multilingue, on garde FR)
  - Judilibre Cass + CA + TJ (judiciaire)
  - vie-publique DILA SKOS (politique publique FR)

Schema :
  thesaurus_concepts(source, code, label, parent_code, depth, scope, freq)
  thesaurus_labels(source, code, label, label_normalized, label_type)
  thesaurus_relations(source, src_code, dst_code, rel_type)  -- broader/narrower/related

Lookup principal : par label_normalized (unidecode + upper).
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

from unidecode import unidecode
from lxml import etree

THES_DIR = Path("/opt/justicelibre/thesaurus")
DB_PATH = THES_DIR / "thesaurus.db"

NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}


def normalize(s: str) -> str:
    return unidecode(s).upper().strip()


def init_db(conn):
    conn.executescript("""
    DROP TABLE IF EXISTS thesaurus_concepts;
    DROP TABLE IF EXISTS thesaurus_labels;
    DROP TABLE IF EXISTS thesaurus_relations;
    CREATE TABLE thesaurus_concepts (
        source TEXT NOT NULL,
        code TEXT NOT NULL,
        label TEXT NOT NULL,
        parent_code TEXT,
        depth INTEGER DEFAULT 1,
        scope TEXT NOT NULL,
        freq INTEGER DEFAULT 0,
        PRIMARY KEY (source, code)
    );
    CREATE TABLE thesaurus_labels (
        source TEXT NOT NULL,
        code TEXT NOT NULL,
        label TEXT NOT NULL,
        label_normalized TEXT NOT NULL,
        label_type TEXT NOT NULL,
        PRIMARY KEY (source, code, label_normalized, label_type)
    );
    CREATE TABLE thesaurus_relations (
        source TEXT NOT NULL,
        src_code TEXT NOT NULL,
        dst_code TEXT NOT NULL,
        rel_type TEXT NOT NULL,
        PRIMARY KEY (source, src_code, dst_code, rel_type)
    );
    CREATE INDEX idx_thes_norm ON thesaurus_labels(label_normalized);
    CREATE INDEX idx_thes_scope ON thesaurus_concepts(scope);
    CREATE INDEX idx_thes_parent ON thesaurus_concepts(parent_code);
    CREATE INDEX idx_thes_rel_src ON thesaurus_relations(source, src_code);
    """)


def insert_concept(conn, source, code, label, parent_code, depth, scope, freq=0):
    conn.execute(
        "INSERT OR REPLACE INTO thesaurus_concepts(source, code, label, parent_code, depth, scope, freq) VALUES (?,?,?,?,?,?,?)",
        (source, code, label, parent_code, depth, scope, freq),
    )


def insert_label(conn, source, code, label, label_type):
    if not label or not label.strip():
        return
    norm = normalize(label)
    if not norm:
        return
    conn.execute(
        "INSERT OR IGNORE INTO thesaurus_labels(source, code, label, label_normalized, label_type) VALUES (?,?,?,?,?)",
        (source, code, label, norm, label_type),
    )


def insert_rel(conn, source, src, dst, rel):
    if src and dst:
        conn.execute(
            "INSERT OR IGNORE INTO thesaurus_relations(source, src_code, dst_code, rel_type) VALUES (?,?,?,?)",
            (source, src, dst, rel),
        )


def load_pcja(conn):
    print("[pcja] loading", flush=True)
    p = THES_DIR / "pcja_reconstructed.json"
    data = json.loads(p.read_text())
    n = 0
    for code, c in data.items():
        insert_concept(conn, "pcja", code, c["label"], c["parent"], c["depth"], "admin", c["freq_cumulative"])
        insert_label(conn, "pcja", code, c["label"], "pref")
        # variants observées
        for variant in c.get("label_variants", {}):
            if variant != c["label"]:
                insert_label(conn, "pcja", code, variant, "alt")
        if c["parent"]:
            insert_rel(conn, "pcja", code, c["parent"], "broader")
        n += 1
    print(f"[pcja] {n} concepts inserted", flush=True)


def load_judilibre_flat(conn, path: Path, source: str):
    """theme.js Cass : liste plate de strings."""
    print(f"[{source}] loading flat list", flush=True)
    txt = path.read_text(encoding="utf-8")
    # Extrait toutes les strings entre quotes simples ou doubles
    items = re.findall(r"['\"]([^'\"]{2,200})['\"]", txt)
    n = 0
    for i, label in enumerate(items, 1):
        label = label.strip()
        if not label:
            continue
        code = f"jc{i:04d}"  # code synthétique
        insert_concept(conn, source, code, label, None, 1, "judiciaire", 0)
        insert_label(conn, source, code, label, "pref")
        n += 1
    print(f"[{source}] {n} concepts", flush=True)


def load_judilibre_nac(conn, path: Path, source: str):
    """ca/theme.js et tj/theme.js : taxonomie NAC hiérarchique. Utilise node pour parser."""
    print(f"[{source}] loading NAC via node", flush=True)
    import subprocess
    # Exécute le JS qui exporte taxon en JSON sur stdout
    proc = subprocess.run(
        ["node", "-e", f"const m = require('{path}'); console.log(JSON.stringify(taxon));"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        # Essai alternatif : eval direct du fichier puis JSON.stringify
        js_code = path.read_text(encoding="utf-8")
        # Vire les commentaires de ligne (// ...)
        js_code = re.sub(r"//[^\n]*", "", js_code)
        # Ajoute le print final
        js_code += "\nprocess.stdout.write(JSON.stringify(taxon));"
        proc = subprocess.run(
            ["node", "-e", js_code],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            print(f"[{source}] node failed: {proc.stderr[:200]}", flush=True)
            return
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"[{source}] JSON parse error: {e}", flush=True)
        return
    n = 0
    for top_code, top_v in data.items():
        if isinstance(top_v, dict):
            top_label = top_v.get("label", str(top_code))
        else:
            top_label = str(top_v)
        insert_concept(conn, source, str(top_code), top_label, None, 1, "judiciaire", 0)
        insert_label(conn, source, str(top_code), top_label, "pref")
        n += 1
        if isinstance(top_v, dict) and "subs" in top_v:
            for sub_code, sub_label in top_v["subs"].items():
                insert_concept(conn, source, str(sub_code), str(sub_label), str(top_code), 2, "judiciaire", 0)
                insert_label(conn, source, str(sub_code), str(sub_label), "pref")
                insert_rel(conn, source, str(sub_code), str(top_code), "broader")
                n += 1
    print(f"[{source}] {n} concepts", flush=True)


def load_skos_streaming(conn, path: Path, source: str, scope: str, lang: str = "fr"):
    """Parse un SKOS-RDF/XML en streaming, garde uniquement labels @lang.

    Supporte deux structures :
      (a) <skos:Concept rdf:about="..."> (vie-publique)
      (b) <rdf:Description rdf:about="..."><rdf:type rdf:resource="...skos/core#Concept"/> (EuroVoc)
    """
    print(f"[{source}] streaming parse {path}", flush=True)
    SKOS = "{http://www.w3.org/2004/02/skos/core#}"
    RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
    XML = "{http://www.w3.org/XML/1998/namespace}"
    CONCEPT_URI = "http://www.w3.org/2004/02/skos/core#Concept"

    n_concepts = 0
    n_skipped = 0
    relations = []  # (src_uri, rel, dst_uri)

    # On itère sur tous les éléments potentiels (Concept ET Description)
    context = etree.iterparse(str(path), events=("end",), huge_tree=True)
    for _, elem in context:
        # Filtre : skos:Concept direct OU rdf:Description avec rdf:type=skos:Concept
        is_concept = False
        if elem.tag == SKOS + "Concept":
            is_concept = True
        elif elem.tag == RDF + "Description":
            for child in elem:
                if child.tag == RDF + "type" and child.get(RDF + "resource") == CONCEPT_URI:
                    is_concept = True
                    break
        if not is_concept:
            # Garbage collect si pas pertinent
            if elem.tag in (SKOS + "Concept", RDF + "Description"):
                elem.clear()
            continue
        uri = elem.get(RDF + "about")
        if not uri:
            elem.clear()
            continue
        pref = None
        alts = []
        broader = []
        narrower = []
        related = []
        for child in elem:
            tag = child.tag
            if tag == SKOS + "prefLabel":
                if child.get(XML + "lang") == lang:
                    if not pref:
                        pref = (child.text or "").strip()
            elif tag == SKOS + "altLabel":
                if child.get(XML + "lang") == lang:
                    a = (child.text or "").strip()
                    if a:
                        alts.append(a)
            elif tag == SKOS + "broader":
                r = child.get(RDF + "resource")
                if r:
                    broader.append(r)
            elif tag == SKOS + "narrower":
                r = child.get(RDF + "resource")
                if r:
                    narrower.append(r)
            elif tag == SKOS + "related":
                r = child.get(RDF + "resource")
                if r:
                    related.append(r)
        if pref:
            n_concepts += 1
            insert_concept(conn, source, uri, pref, broader[0] if broader else None, 0, scope, 0)
            insert_label(conn, source, uri, pref, "pref")
            for a in alts:
                insert_label(conn, source, uri, a, "alt")
            for b in broader:
                relations.append((uri, "broader", b))
            for nr in narrower:
                relations.append((uri, "narrower", nr))
            for rl in related:
                relations.append((uri, "related", rl))
        # Free memory
        elem.clear()
        # Also clear preceding siblings to avoid memory bloat
        while elem.getprevious() is not None:
            del elem.getparent()[0]
        if n_concepts and n_concepts % 5000 == 0:
            print(f"[{source}] {n_concepts} concepts...", flush=True)

    for src, rel, dst in relations:
        insert_rel(conn, source, src, dst, rel)
    print(f"[{source}] DONE: {n_concepts} concepts, {len(relations)} relations", flush=True)


def main():
    DB_PATH.unlink(missing_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    init_db(conn)

    load_pcja(conn)
    conn.commit()

    # Judilibre Cass : liste plate
    load_judilibre_flat(conn, THES_DIR / "judilibre_theme.js", "judilibre_cass")
    conn.commit()

    # Judilibre CA + TJ : NAC hiérarchique
    load_judilibre_nac(conn, THES_DIR / "judilibre_ca_theme.js", "judilibre_ca")
    conn.commit()
    load_judilibre_nac(conn, THES_DIR / "judilibre_tj_theme.js", "judilibre_tj")
    conn.commit()

    # vie-publique
    load_skos_streaming(conn, THES_DIR / "vp-thesaurus-skos.rdf", "vie_publique", "public_policy")
    conn.commit()

    # EuroVoc (gros : ~7000 concepts en FR seul)
    load_skos_streaming(conn, THES_DIR / "eurovoc-skos-ap-eu.rdf", "eurovoc", "europeen")
    conn.commit()

    # Stats finales
    cur = conn.execute("SELECT source, COUNT(*) FROM thesaurus_concepts GROUP BY source ORDER BY COUNT(*) DESC")
    print("\n=== STATS PAR SOURCE ===")
    for row in cur:
        print(f"  {row[0]:20s} {row[1]:>7}")
    cur = conn.execute("SELECT scope, COUNT(*) FROM thesaurus_concepts GROUP BY scope ORDER BY COUNT(*) DESC")
    print("\n=== STATS PAR SCOPE ===")
    for row in cur:
        print(f"  {row[0]:20s} {row[1]:>7}")
    cur = conn.execute("SELECT label_type, COUNT(*) FROM thesaurus_labels GROUP BY label_type")
    print("\n=== STATS LABELS ===")
    for row in cur:
        print(f"  {row[0]:20s} {row[1]:>7}")
    print(f"\nTotal concepts: {conn.execute('SELECT COUNT(*) FROM thesaurus_concepts').fetchone()[0]}")
    print(f"Total labels:   {conn.execute('SELECT COUNT(*) FROM thesaurus_labels').fetchone()[0]}")
    print(f"Total relations: {conn.execute('SELECT COUNT(*) FROM thesaurus_relations').fetchone()[0]}")

    conn.close()
    print(f"\nDB written: {DB_PATH} ({DB_PATH.stat().st_size / 1e6:.1f} Mo)")


if __name__ == "__main__":
    main()
