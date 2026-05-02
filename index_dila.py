"""Index DILA XML archives into SQLite FTS5 for full-text search.

Usage: python3 index_dila.py /opt/justicelibre/dila /opt/justicelibre/dila/judiciaire.db

Schéma enrichi (mai 2026) : extrait séparément les sections sémantiques du
XML DILA (SCT=abstrats, ANA=résumé, CITATION_JP/RAPPROCHEMENTS=renvois) +
métadonnées juridictionnelles utiles (rapporteur, type_rec, publi_recueil,
publi_bull, nature_qualifiee, saisines, loi_def, liens_textes).
"""
import os
import re
import sys
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_html(text: str) -> str:
    if not text:
        return ""
    t = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", t).strip()


def xml_text(elt) -> str:
    if elt is None:
        return ""
    return "".join(elt.itertext()).strip()


# Colonnes additionnelles ajoutées par enrich_dila puis ré-utilisées ici
EXTRA_COLS = [
    "sommaire", "abstrats", "resume", "renvois",
    "rapporteur", "commissaire_gvt",
    "type_rec", "publi_recueil", "publi_bull",
    "nature_qualifiee", "saisines", "loi_def", "liens_textes",
]


def parse_decision(xml_path: str) -> dict | None:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError):
        return None

    meta = root.find(".//META_COMMUN")
    juri = root.find(".//META_JURI")
    judi = root.find(".//META_JURI_JUDI")
    admin = root.find(".//META_JURI_ADMIN")
    constit = root.find(".//META_JURI_CONSTIT")
    contenu = root.find(".//CONTENU")

    if meta is None or juri is None:
        return None

    def get(parent, tag, default=""):
        el = parent.find(tag) if parent is not None else None
        return (el.text or "").strip() if el is not None else default

    text = clean_html(ET.tostring(contenu, encoding="unicode")) if contenu is not None else ""

    # ── Sections sémantiques (SCT / ANA / CITATION_JP / RAPPROCHEMENTS) ──
    sct = [xml_text(s) for s in root.iter("SCT") if xml_text(s)]
    abstrats = "\n".join(sct)
    ana = [xml_text(a) for a in root.iter("ANA") if xml_text(a)]
    resume = "\n\n".join(ana)
    renvois_parts = []
    for tag in ("RAPPROCHEMENTS", "CITATION_JP"):
        for el in root.iter(tag):
            content = el.find("CONTENU")
            txt = xml_text(content) if content is not None else xml_text(el)
            if txt:
                renvois_parts.append(txt)
    renvois = "\n".join(renvois_parts)
    # Sommaire concaténé legacy (kept pour rétro-compat fallback regex)
    sommaire_parts = sct + ana
    sommaire = "\n\n".join(sommaire_parts)

    # ── Méta juridiction admin (JADE) ───────────────────────
    rapporteur = ""
    commissaire_gvt = ""
    type_rec = ""
    publi_recueil = ""
    if admin is not None:
        rapporteur = xml_text(admin.find("RAPPORTEUR"))
        commissaire_gvt = xml_text(admin.find("COMMISSAIRE_GVT"))
        type_rec = xml_text(admin.find("TYPE_REC"))
        publi_recueil = xml_text(admin.find("PUBLI_RECUEIL"))

    # ── Méta jud (CASS, CAPP) ─────────────────────────────────
    publi_bull = ""
    if judi is not None:
        if not rapporteur:
            rapporteur = xml_text(judi.find("RAPPORTEUR"))
        pb = judi.find("PUBLI_BULL")
        if pb is not None:
            publi_bull = pb.get("publie", "") or xml_text(pb)

    # ── Méta CONSTIT ──────────────────────────────────────────
    nature_qualifiee = ""
    saisines = ""
    loi_def = ""
    if constit is not None:
        nature_qualifiee = xml_text(constit.find("NATURE_QUALIFIEE"))
        ld = constit.find("LOI_DEF")
        if ld is not None:
            num = ld.get("num", "")
            date = ld.get("date", "")
            titre_ld = xml_text(ld)
            parts = [p for p in (num, date, titre_ld) if p and p != "2999-01-01"]
            loi_def = " | ".join(parts)
        sais_parts = []
        for s in root.iter("SAISINE"):
            txt = clean_html(ET.tostring(s, encoding="unicode"))
            if txt:
                sais_parts.append(txt)
        if not sais_parts:
            for s in root.iter("SAISINES"):
                txt = clean_html(ET.tostring(s, encoding="unicode"))
                if txt:
                    sais_parts.append(txt)
                    break
        saisines = "\n\n".join(sais_parts)

    # ── LIENS (tous fonds) ────────────────────────────────────
    liens_parts = []
    for ln in root.iter("LIEN"):
        nature = ln.get("naturetexte", "")
        num = ln.get("num", "")
        sens = ln.get("sens", "")
        typ = ln.get("typelien", "")
        txt = xml_text(ln)
        meta_l = "|".join(p for p in (typ, sens, nature, num) if p)
        if txt or meta_l:
            liens_parts.append(f"{meta_l} :: {txt}" if meta_l else txt)
    liens_textes = "\n".join(liens_parts)

    return {
        "id": get(meta, "ID"),
        "nature": get(meta, "NATURE"),
        "titre": get(juri, "TITRE"),
        "date": get(juri, "DATE_DEC"),
        "juridiction": get(juri, "JURIDICTION"),
        "solution": get(juri, "SOLUTION"),
        "numero": get(judi, ".//NUMERO_AFFAIRE") if judi is not None else "",
        "formation": get(judi, "FORMATION") or (get(admin, "FORMATION") if admin is not None else ""),
        "ecli": get(judi, "ECLI") or (get(admin, "ECLI") if admin is not None else "") or (get(constit, "ECLI") if constit is not None else ""),
        "president": get(judi, "PRESIDENT") or (get(admin, "PRESIDENT") if admin is not None else ""),
        "avocats": get(judi, "AVOCATS") or (get(admin, "AVOCATS") if admin is not None else ""),
        "text": text,
        # Nouvelles colonnes sémantiques (peuvent être vides)
        "sommaire": sommaire,
        "abstrats": abstrats,
        "resume": resume,
        "renvois": renvois,
        "rapporteur": rapporteur,
        "commissaire_gvt": commissaire_gvt,
        "type_rec": type_rec,
        "publi_recueil": publi_recueil,
        "publi_bull": publi_bull,
        "nature_qualifiee": nature_qualifiee,
        "saisines": saisines,
        "loi_def": loi_def,
        "liens_textes": liens_textes,
    }


BASE_COLS = ["id", "nature", "titre", "date", "juridiction", "solution",
             "numero", "formation", "ecli", "president", "avocats", "text"]
ALL_COLS = BASE_COLS + EXTRA_COLS


def create_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Table de base avec les 12 colonnes historiques
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            nature TEXT,
            titre TEXT,
            date TEXT,
            juridiction TEXT,
            solution TEXT,
            numero TEXT,
            formation TEXT,
            ecli TEXT,
            president TEXT,
            avocats TEXT,
            text TEXT
        )
    """)

    # Ajout idempotent des nouvelles colonnes
    existing = {row[1] for row in conn.execute("PRAGMA table_info(decisions)")}
    for col in EXTRA_COLS:
        if col not in existing:
            conn.execute(f"ALTER TABLE decisions ADD COLUMN {col} TEXT")

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5(
            id UNINDEXED,
            titre,
            juridiction,
            solution,
            numero,
            formation,
            text,
            content='decisions',
            content_rowid='rowid'
        )
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN
            INSERT INTO decisions_fts(rowid, id, titre, juridiction, solution, numero, formation, text)
            VALUES (new.rowid, new.id, new.titre, new.juridiction, new.solution, new.numero, new.formation, new.text);
        END
    """)

    conn.commit()
    return conn


def index_directory(dila_dir: str, db_path: str):
    conn = create_db(db_path)
    cursor = conn.cursor()

    xml_files = list(Path(dila_dir).rglob("*.xml"))
    total = len(xml_files)
    print(f"Found {total} XML files to index")

    inserted = 0
    errors = 0
    batch = []
    placeholders = ",".join("?" * len(ALL_COLS))
    insert_sql = f"INSERT OR IGNORE INTO decisions ({','.join(ALL_COLS)}) VALUES ({placeholders})"

    for i, xml_path in enumerate(xml_files):
        decision = parse_decision(str(xml_path))
        if decision is None:
            errors += 1
            continue

        batch.append(tuple(decision.get(c, "") for c in ALL_COLS))

        if len(batch) >= 1000:
            cursor.executemany(insert_sql, batch)
            conn.commit()
            inserted += len(batch)
            batch = []
            if (i + 1) % 10000 == 0:
                print(f"  {i+1}/{total} processed ({inserted} inserted, {errors} errors)")

    if batch:
        cursor.executemany(insert_sql, batch)
        conn.commit()
        inserted += len(batch)

    print(f"\nDone: {inserted} decisions indexed, {errors} errors")
    print(f"Database: {db_path} ({os.path.getsize(db_path) / 1048576:.1f} MB)")

    # Verify
    count = cursor.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    print(f"Total in DB: {count}")

    # Test search
    results = cursor.execute(
        "SELECT id, titre, date FROM decisions_fts WHERE decisions_fts MATCH ? LIMIT 3",
        ("licenciement",)
    ).fetchall()
    print(f"\nTest search 'licenciement': {len(results)} results")
    for r in results:
        print(f"  {r[0]} | {r[2]} | {r[1][:80]}")

    conn.close()


if __name__ == "__main__":
    dila_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/justicelibre/dila"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/justicelibre/dila/judiciaire.db"
    index_directory(dila_dir, db_path)
