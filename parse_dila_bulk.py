"""Parser DILA bulk tarballs → SQLite FTS5.

Ingère en streaming depuis les .tar.gz sans extraction complète (économie disque).
Un parseur par fond : LEGI, JORF, INCA, JADE, KALI, CNIL, CAPP, CONSTIT.

Usage :
    python3 parse_dila_bulk.py <fond>  # ex: legi, jorf, jade…
"""
import html
import os
import re
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

import lxml.etree as ET

sys.stdout.reconfigure(line_buffering=True)

BULK_DIR = Path("/opt/justicelibre/dila_bulk")
DB_DIR = Path("/opt/justicelibre/dila")
DB_DIR.mkdir(parents=True, exist_ok=True)


def strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    t = re.sub(r"<script[^>]*>.*?</script>", " ", html_text, flags=re.DOTALL)
    t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.DOTALL)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def xml_text(elt):
    if elt is None:
        return ""
    # Récupère le texte complet d'un sous-arbre (tous les textes + tail)
    return "".join(elt.itertext()).strip()


# ─── LEGI : textes consolidés + articles avec versions historiques ───────

def parse_legi():
    db = DB_DIR / "legi.db"
    conn = sqlite3.connect(db, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-131072")  # 128 MB
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS legi_textes (
        legitext TEXT PRIMARY KEY,
        titre TEXT,
        titre_long TEXT,
        nature TEXT,
        etat TEXT,
        date_debut TEXT,
        date_fin TEXT,
        date_publi TEXT,
        num_jorf TEXT,
        nor TEXT
    );
    CREATE TABLE IF NOT EXISTS legi_articles (
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        legiarti TEXT,
        legitext TEXT,
        num TEXT,
        titre_text TEXT,
        etat TEXT,
        date_debut TEXT,
        date_fin TEXT,
        texte TEXT,
        nota TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_art_legiarti ON legi_articles(legiarti);
    CREATE INDEX IF NOT EXISTS idx_art_num ON legi_articles(titre_text, num);
    CREATE INDEX IF NOT EXISTS idx_art_legitext ON legi_articles(legitext);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_art_version ON legi_articles(legiarti, date_debut);
    CREATE VIRTUAL TABLE IF NOT EXISTS legi_articles_fts USING fts5(
        legiarti UNINDEXED, titre_text, num, texte,
        content='legi_articles', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS legi_art_ai AFTER INSERT ON legi_articles BEGIN
        INSERT INTO legi_articles_fts(rowid, legiarti, titre_text, num, texte)
        VALUES (new.rowid, new.legiarti, new.titre_text, new.num, new.texte);
    END;
    """)
    conn.commit()

    # Index des titres par legitext (rempli quand on rencontre un TEXTELR)
    # Les articles arrivent parfois avant leur TEXTELR parent → on remplira titre_text
    # dans une passe finale.
    existing_arts = conn.execute("SELECT COUNT(*) FROM legi_articles").fetchone()[0]
    print(f"[legi] existing articles: {existing_arts}")

    tarball = BULK_DIR / "Freemium_legi.tar.gz"
    n_articles = 0
    n_texts = 0
    n_errors = 0
    batch = []

    def flush():
        nonlocal batch
        if not batch:
            return
        conn.executemany(
            "INSERT OR IGNORE INTO legi_articles (legiarti, legitext, num, titre_text, etat, date_debut, date_fin, texte, nota) VALUES (?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
        batch = []

    start = time.time()
    print(f"[legi] streaming {tarball.name}…")
    with tarfile.open(tarball, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = member.name
            if not name.endswith(".xml"):
                continue
            try:
                f = tar.extractfile(member)
                if f is None:
                    continue
                data = f.read()
                root = ET.fromstring(data)
            except (ET.XMLSyntaxError, OSError) as e:
                n_errors += 1
                continue

            tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

            if tag == "ARTICLE" or "/article/" in name:
                # Parse article
                try:
                    meta = root.find(".//META_COMMUN") or root.find("META/META_COMMUN")
                    meta_art = root.find(".//META_ARTICLE") or root.find("META/META_SPEC/META_ARTICLE")
                    if meta is None or meta_art is None:
                        continue
                    legiarti = xml_text(meta.find("ID"))
                    num = xml_text(meta_art.find("NUM"))
                    etat = xml_text(meta_art.find("ETAT"))
                    date_debut = xml_text(meta_art.find("DATE_DEBUT"))
                    date_fin = xml_text(meta_art.find("DATE_FIN"))
                    # parent text id
                    contexte = root.find(".//CONTEXTE/TEXTE")
                    legitext = contexte.get("cid") if contexte is not None else ""
                    titre_text = ""
                    if contexte is not None:
                        tt = contexte.find("TITRE_TXT")
                        if tt is not None:
                            titre_text = tt.get("c_titre_court") or xml_text(tt)
                    texte_elt = root.find(".//BLOC_TEXTUEL/CONTENU")
                    texte = strip_html(ET.tostring(texte_elt, encoding="unicode")) if texte_elt is not None else ""
                    nota_elt = root.find(".//NOTA/CONTENU")
                    nota = strip_html(ET.tostring(nota_elt, encoding="unicode")) if nota_elt is not None else ""
                    batch.append((legiarti, legitext, num, titre_text, etat, date_debut, date_fin, texte, nota))
                    n_articles += 1
                    if len(batch) >= 500:
                        flush()
                        if n_articles % 10000 == 0:
                            elapsed = time.time() - start
                            rate = n_articles / elapsed
                            print(f"  [{n_articles:>8} arts / {n_texts:>5} textes / {n_errors} err] {rate:.0f}/s  ({elapsed/60:.1f}min)")
                except Exception as e:
                    n_errors += 1

            elif tag == "TEXTELR" or "/texte/version/" in name or "/texte/struct/" in name:
                # Parse text metadata
                try:
                    meta = root.find(".//META_COMMUN") or root.find("META/META_COMMUN")
                    meta_t = root.find(".//META_TEXTE_CHRONICLE") or root.find("META/META_SPEC/META_TEXTE_CHRONICLE")
                    if meta is None:
                        continue
                    legitext = xml_text(meta.find("ID"))
                    titre = ""
                    titre_long = ""
                    nature = xml_text(meta.find("NATURE"))
                    etat = ""
                    date_debut = ""
                    date_fin = ""
                    date_publi = ""
                    num_jorf = ""
                    nor = ""
                    if meta_t is not None:
                        titre = xml_text(meta_t.find("TITRE"))
                        titre_long = xml_text(meta_t.find("TITREFULL"))
                        num_jorf = xml_text(meta_t.find("NUM_JORF"))
                        nor = xml_text(meta_t.find("NOR"))
                        date_publi = xml_text(meta_t.find("DATE_PUBLI"))
                    meta_v = root.find(".//META_TEXTE_VERSION") or root.find("META/META_SPEC/META_TEXTE_VERSION")
                    if meta_v is not None:
                        etat = xml_text(meta_v.find("ETAT"))
                        date_debut = xml_text(meta_v.find("DATE_DEBUT"))
                        date_fin = xml_text(meta_v.find("DATE_FIN"))
                    conn.execute(
                        "INSERT OR REPLACE INTO legi_textes VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (legitext, titre, titre_long, nature, etat, date_debut, date_fin, date_publi, num_jorf, nor),
                    )
                    n_texts += 1
                except Exception:
                    n_errors += 1

    flush()
    conn.commit()
    # Back-fill titre_text for articles that were parsed before their text
    print("[legi] back-filling titre_text…")
    conn.execute("""
        UPDATE legi_articles
        SET titre_text = (SELECT titre FROM legi_textes WHERE legitext = legi_articles.legitext)
        WHERE (titre_text IS NULL OR titre_text = '') AND legitext IS NOT NULL
    """)
    conn.commit()
    conn.close()
    print(f"[legi] DONE. articles={n_articles}, textes={n_texts}, errors={n_errors}, time={time.time()-start:.0f}s")


# ─── JORF / INCA : textes JO non codifiés ──────────────────────────────

def parse_jorf_like(fund: str):
    db = DB_DIR / f"{fund}.db"
    conn = sqlite3.connect(db, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-131072")
    conn.executescript(f"""
    CREATE TABLE IF NOT EXISTS {fund}_textes (
        jorftext TEXT PRIMARY KEY,
        titre TEXT,
        titre_long TEXT,
        nature TEXT,
        date_publi TEXT,
        date_signature TEXT,
        num_jorf TEXT,
        nor TEXT,
        ministere TEXT,
        texte TEXT,
        nota TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_{fund}_date ON {fund}_textes(date_publi);
    CREATE INDEX IF NOT EXISTS idx_{fund}_nor ON {fund}_textes(nor);
    CREATE VIRTUAL TABLE IF NOT EXISTS {fund}_fts USING fts5(
        jorftext UNINDEXED, titre, nature, ministere, texte, nota,
        content='{fund}_textes', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS {fund}_ai AFTER INSERT ON {fund}_textes BEGIN
        INSERT INTO {fund}_fts(rowid, jorftext, titre, nature, ministere, texte, nota)
        VALUES (new.rowid, new.jorftext, new.titre, new.nature, new.ministere, new.texte, new.nota);
    END;
    """)
    conn.commit()

    tarball = BULK_DIR / f"Freemium_{fund}.tar.gz"
    n = 0
    n_errors = 0
    batch = []
    start = time.time()

    def flush():
        nonlocal batch
        if not batch:
            return
        conn.executemany(
            f"INSERT OR REPLACE INTO {fund}_textes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
        batch = []

    print(f"[{fund}] streaming {tarball.name}…")
    with tarfile.open(tarball, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".xml"):
                continue
            try:
                f = tar.extractfile(member)
                if f is None:
                    continue
                data = f.read()
                root = ET.fromstring(data)
            except Exception:
                n_errors += 1
                continue

            # Cherche les JORFTEXT consolidés (texte+version)
            if "/texte/version/" not in member.name:
                continue
            try:
                meta = root.find(".//META_COMMUN")
                meta_t = root.find(".//META_TEXTE_CHRONICLE")
                meta_v = root.find(".//META_TEXTE_VERSION")
                if meta is None:
                    continue
                jorftext = xml_text(meta.find("ID"))
                nature = xml_text(meta.find("NATURE"))
                titre = titre_long = num_jorf = nor = date_publi = date_sig = ministere = ""
                if meta_t is not None:
                    titre = xml_text(meta_t.find("TITRE"))
                    titre_long = xml_text(meta_t.find("TITREFULL"))
                    num_jorf = xml_text(meta_t.find("NUM_JORF"))
                    nor = xml_text(meta_t.find("NOR"))
                    date_publi = xml_text(meta_t.find("DATE_PUBLI"))
                    date_sig = xml_text(meta_t.find("DATE_TEXTE"))
                if meta_v is not None:
                    min_elt = meta_v.find("MINISTERE")
                    ministere = xml_text(min_elt) if min_elt is not None else ""
                # Texte principal
                visa = root.find(".//VISAS")
                sign = root.find(".//SIGNATAIRES")
                content_parts = []
                for tag in ("VISAS", "CORPS", "SIGNATAIRES", "TM"):
                    for e in root.iter(tag):
                        content_parts.append(xml_text(e))
                        break
                texte = strip_html(" ".join(content_parts))
                nota_elt = root.find(".//NOTA/CONTENU")
                nota = strip_html(ET.tostring(nota_elt, encoding="unicode")) if nota_elt is not None else ""

                batch.append((jorftext, titre, titre_long, nature, date_publi, date_sig, num_jorf, nor, ministere, texte, nota))
                n += 1
                if len(batch) >= 500:
                    flush()
                    if n % 10000 == 0:
                        elapsed = time.time() - start
                        rate = n / elapsed
                        print(f"  [{n:>8} textes / {n_errors} err] {rate:.0f}/s ({elapsed/60:.1f}min)")
            except Exception:
                n_errors += 1

    flush()
    conn.close()
    print(f"[{fund}] DONE. textes={n}, errors={n_errors}, time={time.time()-start:.0f}s")


# ─── JADE / CAPP / CASS / CONSTIT : jurisprudence ────────────────────────

def parse_juris(fund: str):
    """JADE=admin (CE+CAA+TA), CAPP=CA, CASS=Cass, CONSTIT=CC.
    Schema commun : decisions_{fund}.
    """
    db = DB_DIR / f"{fund}.db"
    conn = sqlite3.connect(db, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-131072")
    conn.executescript(f"""
    CREATE TABLE IF NOT EXISTS {fund}_decisions (
        id TEXT PRIMARY KEY,
        ecli TEXT,
        juridiction TEXT,
        formation TEXT,
        date TEXT,
        numero TEXT,
        solution TEXT,
        nature TEXT,
        president TEXT,
        rapporteur TEXT,
        avocat_general TEXT,
        avocats TEXT,
        titre TEXT,
        sommaire TEXT,
        texte TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_{fund}_date ON {fund}_decisions(date);
    CREATE INDEX IF NOT EXISTS idx_{fund}_ecli ON {fund}_decisions(ecli);
    CREATE INDEX IF NOT EXISTS idx_{fund}_numero ON {fund}_decisions(numero);
    CREATE VIRTUAL TABLE IF NOT EXISTS {fund}_fts USING fts5(
        id UNINDEXED, juridiction, numero, titre, sommaire, texte,
        content='{fund}_decisions', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS {fund}_ai AFTER INSERT ON {fund}_decisions BEGIN
        INSERT INTO {fund}_fts(rowid, id, juridiction, numero, titre, sommaire, texte)
        VALUES (new.rowid, new.id, new.juridiction, new.numero, new.titre, new.sommaire, new.texte);
    END;
    """)
    conn.commit()

    tarball = BULK_DIR / f"Freemium_{fund}.tar.gz"
    if not tarball.exists():
        print(f"[{fund}] no tarball at {tarball}, skip")
        return
    n = 0
    n_errors = 0
    batch = []
    start = time.time()

    def flush():
        nonlocal batch
        if not batch:
            return
        conn.executemany(
            f"INSERT OR REPLACE INTO {fund}_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
        batch = []

    print(f"[{fund}] streaming {tarball.name}…")
    with tarfile.open(tarball, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".xml"):
                continue
            try:
                f = tar.extractfile(member)
                if f is None:
                    continue
                data = f.read()
                root = ET.fromstring(data)
            except Exception:
                n_errors += 1
                continue
            try:
                # Cherche META_COMMUN + META_JURI
                meta = root.find(".//META_COMMUN")
                meta_j = root.find(".//META_JURI")
                if meta is None:
                    continue
                did = xml_text(meta.find("ID"))
                nature = xml_text(meta.find("NATURE"))
                ecli = juridiction = formation = date = numero = solution = ""
                president = rapporteur = avocat_general = avocats = titre = sommaire = ""
                if meta_j is not None:
                    ecli = xml_text(meta_j.find("ECLI"))
                    juridiction = xml_text(meta_j.find("JURIDICTION"))
                    date = xml_text(meta_j.find("DATE_DEC"))
                    numero = xml_text(meta_j.find("NUMERO"))
                    solution = xml_text(meta_j.find("SOLUTION"))
                    formation = xml_text(meta_j.find("FORMATION"))
                    president = xml_text(meta_j.find("PRESIDENT"))
                    rapporteur = xml_text(meta_j.find("RAPPORTEUR"))
                    avocat_general = xml_text(meta_j.find("AVOCAT_GENERAL"))
                    avocats_elts = meta_j.findall(".//AVOCATS/AVOCAT")
                    avocats = " ; ".join(xml_text(a) for a in avocats_elts)
                    titre = xml_text(meta_j.find("TITRE"))
                # sommaire et texte
                somm_elt = root.find(".//SOMMAIRE/CONTENU") or root.find(".//SOMMAIRE")
                sommaire = strip_html(ET.tostring(somm_elt, encoding="unicode")) if somm_elt is not None else ""
                texte_elt = root.find(".//CONTENU") or root.find(".//TEXTE")
                texte = strip_html(ET.tostring(texte_elt, encoding="unicode")) if texte_elt is not None else ""
                if not texte:
                    # Fallback: prendre tout le texte sauf META
                    for m in root.iter("META"):
                        m.getparent().remove(m) if m.getparent() is not None else None
                    texte = strip_html(ET.tostring(root, encoding="unicode"))
                batch.append((did, ecli, juridiction, formation, date, numero, solution, nature, president, rapporteur, avocat_general, avocats, titre, sommaire, texte))
                n += 1
                if len(batch) >= 300:
                    flush()
                    if n % 5000 == 0:
                        elapsed = time.time() - start
                        rate = n / elapsed
                        print(f"  [{n:>8} decisions / {n_errors} err] {rate:.0f}/s ({elapsed/60:.1f}min)")
            except Exception:
                n_errors += 1

    flush()
    conn.close()
    print(f"[{fund}] DONE. decisions={n}, errors={n_errors}, time={time.time()-start:.0f}s")


# ─── KALI : conventions collectives ─────────────────────────────────────

def parse_kali():
    """KALI = conventions collectives, accords de branche, avenants."""
    db = DB_DIR / "kali.db"
    conn = sqlite3.connect(db, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS kali_textes (
        id TEXT PRIMARY KEY,
        idcc TEXT,               -- Identifiant de convention collective (4 chiffres)
        titre TEXT,
        nature TEXT,             -- CONVENTION, ACCORD, AVENANT
        etat TEXT,
        date_publi TEXT,
        date_debut TEXT,
        date_fin TEXT,
        texte TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_kali_idcc ON kali_textes(idcc);
    CREATE VIRTUAL TABLE IF NOT EXISTS kali_fts USING fts5(
        id UNINDEXED, idcc, titre, texte,
        content='kali_textes', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS kali_ai AFTER INSERT ON kali_textes BEGIN
        INSERT INTO kali_fts(rowid, id, idcc, titre, texte)
        VALUES (new.rowid, new.id, new.idcc, new.titre, new.texte);
    END;
    """)
    conn.commit()
    tarball = BULK_DIR / "Freemium_kali.tar.gz"
    if not tarball.exists():
        print("[kali] no tarball, skip")
        return
    n = 0
    n_errors = 0
    batch = []
    start = time.time()

    def flush():
        nonlocal batch
        if not batch:
            return
        conn.executemany(
            "INSERT OR REPLACE INTO kali_textes VALUES (?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
        batch = []

    print("[kali] streaming…")
    with tarfile.open(tarball, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".xml"):
                continue
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
                meta_k = root.find(".//META_TEXTE_KALI") or root.find(".//META_CONVENTION_COLLECTIVE")
                if meta is None:
                    continue
                kid = xml_text(meta.find("ID"))
                nature = xml_text(meta.find("NATURE"))
                idcc = titre = etat = date_publi = date_debut = date_fin = ""
                if meta_k is not None:
                    idcc = xml_text(meta_k.find("IDCC"))
                    titre = xml_text(meta_k.find("TITRE"))
                    etat = xml_text(meta_k.find("ETAT"))
                    date_publi = xml_text(meta_k.find("DATE_PUBLI"))
                    date_debut = xml_text(meta_k.find("DATE_DEBUT"))
                    date_fin = xml_text(meta_k.find("DATE_FIN"))
                content = root.find(".//BLOC_TEXTUEL/CONTENU") or root.find(".//CONTENU")
                texte = strip_html(ET.tostring(content, encoding="unicode")) if content is not None else ""
                batch.append((kid, idcc, titre, nature, etat, date_publi, date_debut, date_fin, texte))
                n += 1
                if len(batch) >= 300:
                    flush()
                    if n % 5000 == 0:
                        elapsed = time.time() - start
                        print(f"  [{n:>6} kali] {n/elapsed:.0f}/s ({elapsed/60:.1f}min)")
            except Exception:
                n_errors += 1
    flush()
    conn.close()
    print(f"[kali] DONE. textes={n}, errors={n_errors}")


# ─── CNIL : délibérations ──────────────────────────────────────────────

def parse_cnil():
    db = DB_DIR / "cnil.db"
    conn = sqlite3.connect(db, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cnil_deliberations (
        id TEXT PRIMARY KEY,
        numero TEXT,
        titre TEXT,
        date TEXT,
        formation TEXT,
        texte TEXT
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS cnil_fts USING fts5(
        id UNINDEXED, numero, titre, formation, texte,
        content='cnil_deliberations', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS cnil_ai AFTER INSERT ON cnil_deliberations BEGIN
        INSERT INTO cnil_fts(rowid, id, numero, titre, formation, texte)
        VALUES (new.rowid, new.id, new.numero, new.titre, new.formation, new.texte);
    END;
    """)
    conn.commit()
    tarball = BULK_DIR / "Freemium_cnil.tar.gz"
    if not tarball.exists():
        print("[cnil] no tarball, skip")
        return
    n = 0
    batch = []
    with tarfile.open(tarball, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".xml"):
                continue
            try:
                f = tar.extractfile(member)
                if f is None:
                    continue
                root = ET.fromstring(f.read())
            except Exception:
                continue
            try:
                meta = root.find(".//META_COMMUN")
                if meta is None:
                    continue
                did = xml_text(meta.find("ID"))
                numero = xml_text(root.find(".//NUMERO"))
                titre = xml_text(root.find(".//TITRE"))
                date = xml_text(root.find(".//DATE_DEC") or root.find(".//DATE"))
                formation = xml_text(root.find(".//FORMATION"))
                content = root.find(".//CONTENU") or root.find(".//TEXTE")
                texte = strip_html(ET.tostring(content, encoding="unicode")) if content is not None else ""
                batch.append((did, numero, titre, date, formation, texte))
                n += 1
                if len(batch) >= 200:
                    conn.executemany("INSERT OR REPLACE INTO cnil_deliberations VALUES (?,?,?,?,?,?)", batch)
                    conn.commit()
                    batch = []
            except Exception:
                continue
    if batch:
        conn.executemany("INSERT OR REPLACE INTO cnil_deliberations VALUES (?,?,?,?,?,?)", batch)
        conn.commit()
    conn.close()
    print(f"[cnil] DONE. deliberations={n}")


# ─── Main ────────────────────────────────────────────────────────────

PARSERS = {
    "legi":    parse_legi,
    "jorf":    lambda: parse_jorf_like("jorf"),
    "inca":    lambda: parse_jorf_like("inca"),
    "jade":    lambda: parse_juris("jade"),
    "capp":    lambda: parse_juris("capp"),
    "constit": lambda: parse_juris("constit"),
    "kali":    parse_kali,
    "cnil":    parse_cnil,
}


def main():
    if len(sys.argv) < 2:
        sys.exit(f"Usage: parse_dila_bulk.py <{'|'.join(PARSERS)}>")
    fund = sys.argv[1].lower()
    if fund not in PARSERS:
        sys.exit(f"Unknown fund: {fund}. Available: {list(PARSERS)}")
    PARSERS[fund]()


if __name__ == "__main__":
    main()
