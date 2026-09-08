"""Parser DILA bulk tarballs → SQLite FTS5.

Ingère en streaming depuis les .tar.gz sans extraction complète (économie disque).
Un parseur par fond : LEGI, JORF, INCA, JADE, KALI, CNIL, CAPP, CONSTIT.

Usage :
    python3 parse_dila_bulk.py <fond>  # ex: legi, jorf, jade…
    python3 parse_dila_bulk.py <fond> --tarball /chemin/X.tar.gz --db /chemin/x.db

`--tarball` et `--db` servent aux bancs d'essai : sans eux, les chemins de
production (BULK_DIR / DB_DIR) sont utilisés, à l'identique de l'historique.
"""
import argparse
import html
import json
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


def first_elt(*elts):
    """Le premier élément « utilisable » de la liste.

    Remplace `root.find(a) or root.find(b)`, que lxml déprécie : la valeur de
    vérité d'un élément vaut `len(elt) > 0`, si bien qu'un élément SANS ENFANT
    est faux et fait passer au suivant. lxml émet un FutureWarning et annonce
    que ce comportement changera. On l'écrit donc explicitement, à l'identique,
    plutôt que de laisser une future version de lxml modifier l'ingestion en
    silence."""
    for e in elts:
        if e is not None and len(e) > 0:
            return e
    for e in elts:
        if e is not None:
            return e
    return None


def elt_html_text(elt) -> str:
    """Texte d'un sous-arbre en repassant par sa sérialisation (conserve les
    espaces induits par le balisage : <p>a</p><p>b</p> → « a b », pas « ab »)."""
    if elt is None:
        return ""
    return strip_html(ET.tostring(elt, encoding="unicode"))


def as_json(obj) -> str:
    """JSON compact, chaîne vide si l'objet est vide — pour ne jamais écrire
    « [] » ou « {} » là où le reste du schéma utilise la chaîne vide."""
    if not obj:
        return ""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def ensure_columns(conn: sqlite3.Connection, table: str, cols) -> list:
    """ADD COLUMN idempotent. Ne MODIFIE jamais une colonne existante : les
    triggers FTS5 nomment leurs colonnes explicitement, un ADD COLUMN ne les
    casse donc pas. Renvoie la liste des colonnes réellement ajoutées."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    added = []
    for name, typ in cols:
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
            added.append(name)
    if added:
        conn.commit()
    return added


def liens_json(container) -> str:
    """<LIENS><LIEN …/></LIENS> → JSON. Tous les attributs (cidtexte, nortexte,
    numtexte, naturetexte, datesignatexte, sens, typelien…) + le libellé."""
    if container is None:
        return ""
    out = []
    for ln in container.iter("LIEN"):
        d = {k: v for k, v in ln.attrib.items() if v}
        t = xml_text(ln)
        if t:
            d["libelle"] = t
        if d:
            out.append(d)
    return as_json(out)


def upsert_sql(table: str, cols, pk: str, keep_non_empty: bool = False) -> str:
    """`INSERT … ON CONFLICT(pk) DO UPDATE SET …` sur les seules colonnes de
    `cols`.

    Pourquoi pas `INSERT OR REPLACE` : OR REPLACE **supprime la ligne** puis en
    insère une neuve, donc remet à NULL toute colonne que le parseur ne remplit
    pas. `capp_decisions.numero_rg_norm`, dérivée après coup par
    `scripts/prod-oneshot/extract_rg_prod.py`, est exactement dans ce cas : une
    ré-ingestion complète l'aurait effacée en silence. L'UPSERT conserve aussi
    le `rowid`, donc l'alignement de l'index FTS5 externe.

    `keep_non_empty=True` : ne remplace une valeur que par une valeur NON VIDE.
    Utile quand un même identifiant arrive deux fois dans la même archive avec
    des jeux de champs différents (LEGI/KALI : `texte/struct` puis
    `texte/version`, seul le second porte le titre).
    """
    placeholders = ",".join("?" * len(cols))
    if keep_non_empty:
        sets = ", ".join(
            f"{c}=CASE WHEN excluded.{c} IS NOT NULL AND excluded.{c} <> '' "
            f"THEN excluded.{c} ELSE {table}.{c} END"
            for c in cols if c != pk)
    else:
        sets = ", ".join(f"{c}=excluded.{c}" for c in cols if c != pk)
    return (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT({pk}) DO UPDATE SET {sets}")


def _open_db(path: Path, cache_mb: int = 128) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    # INSERT OR REPLACE doit déclencher le trigger _ad du FTS5
    conn.execute("PRAGMA recursive_triggers=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA cache_size=-{cache_mb * 1024}")
    return conn


# ─── LEGI : textes consolidés + articles avec versions historiques ───────

LEGI_ART_NEW_COLS = [
    ("jorftext", "TEXT"),      # CONTEXTE/TEXTE@cid — l'identifiant JORF du texte parent
    ("hierarchie", "TEXT"),    # CONTEXTE/TEXTE/TM/TITRE_TM — livre/titre/chapitre/section (JSON)
    ("liens", "TEXT"),         # LIENS/LIEN (JSON)
    ("ancien_id", "TEXT"),     # META_COMMUN/ANCIEN_ID
    ("type_article", "TEXT"),  # META_ARTICLE/TYPE
]

LEGI_TXT_NEW_COLS = [
    ("cid", "TEXT"),                    # META_TEXTE_CHRONICLE/CID
    ("date_texte", "TEXT"),             # META_TEXTE_CHRONICLE/DATE_TEXTE (signature)
    ("num_parution", "TEXT"),
    ("num_sequence", "TEXT"),
    ("origine_publi", "TEXT"),
    ("derniere_modification", "TEXT"),
    ("ministere", "TEXT"),              # META_TEXTE_VERSION/MINISTERE
    ("autorite", "TEXT"),               # META_TEXTE_VERSION/AUTORITE
    ("liens", "TEXT"),                  # LIENS/LIEN (JSON)
]


def legi_contexte(root):
    """Extrait de CONTEXTE/TEXTE : le LEGITEXT (joignable avec legi_textes), le
    JORFTEXT, le titre court et la hiérarchie TM.

    ⚠️ LE BUG HISTORIQUE. `CONTEXTE/TEXTE@cid` vaut un **JORFTEXT**
    (« JORFTEXT000000394028 ») alors que `legi_textes.legitext` est un
    **LEGITEXT** (META_COMMUN/ID). La jointure article ↔ texte ne trouvait donc
    RIEN — 0 correspondance sur 8 000 articles échantillonnés — et le back-fill
    de `titre_text`, qui joint dessus, ne s'exécutait jamais.
    Le vrai LEGITEXT est porté par le SECOND <TITRE_TXT>, attribut `id_txt` :
        <TITRE_TXT c_titre_court="…" id_txt="LEGITEXT000005631294">
    (vérifié sur LEGIARTI000006321037.xml, delta LEGI_20260907-214720).
    """
    contexte = root.find(".//CONTEXTE/TEXTE")
    if contexte is None:
        return "", "", "", ""
    jorftext = contexte.get("cid") or ""
    legitext = ""
    for tt in contexte.findall("TITRE_TXT"):
        idt = tt.get("id_txt") or ""
        if idt.startswith("LEGITEXT"):
            legitext = idt
            break
    if not legitext:
        legitext = jorftext          # textes non consolidés : pas de version LEGI
    # titre_text : inchangé (premier TITRE_TXT), colonne déjà correcte en base.
    tt0 = contexte.find("TITRE_TXT")
    titre_text = ""
    if tt0 is not None:
        titre_text = tt0.get("c_titre_court") or xml_text(tt0)
    # Hiérarchie : TM imbriqués, du plus général au plus précis.
    hier = []
    node = contexte.find("TM")
    while node is not None:
        t = node.find("TITRE_TM")
        if t is not None:
            hier.append({
                "id": t.get("id", ""),
                "titre": xml_text(t),
                "debut": t.get("debut", ""),
                "fin": t.get("fin", ""),
            })
        node = node.find("TM")
    return legitext, jorftext, titre_text, as_json(hier)


def parse_legi(tarball: Path = None, db: Path = None):
    db = Path(db) if db else DB_DIR / "legi.db"
    conn = _open_db(db)
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
    CREATE TRIGGER IF NOT EXISTS legi_art_ad AFTER DELETE ON legi_articles BEGIN
        INSERT INTO legi_articles_fts(legi_articles_fts, rowid, legiarti, titre_text, num, texte)
        VALUES ('delete', old.rowid, old.legiarti, old.titre_text, old.num, old.texte);
    END;
    CREATE TRIGGER IF NOT EXISTS legi_art_au AFTER UPDATE ON legi_articles BEGIN
        INSERT INTO legi_articles_fts(legi_articles_fts, rowid, legiarti, titre_text, num, texte)
        VALUES ('delete', old.rowid, old.legiarti, old.titre_text, old.num, old.texte);
        INSERT INTO legi_articles_fts(rowid, legiarti, titre_text, num, texte)
        VALUES (new.rowid, new.legiarti, new.titre_text, new.num, new.texte);
    END;
    """)
    conn.commit()
    ensure_columns(conn, "legi_articles", LEGI_ART_NEW_COLS)
    ensure_columns(conn, "legi_textes", LEGI_TXT_NEW_COLS)

    # Index des titres par legitext (rempli quand on rencontre un TEXTELR)
    # Les articles arrivent parfois avant leur TEXTELR parent → on remplira titre_text
    # dans une passe finale.
    existing_arts = conn.execute("SELECT COUNT(*) FROM legi_articles").fetchone()[0]
    print(f"[legi] existing articles: {existing_arts}")

    tarball = Path(tarball) if tarball else BULK_DIR / "Freemium_legi.tar.gz"
    n_articles = 0
    n_texts = 0
    n_errors = 0
    batch = []
    batch_txt = []

    # ⚠️ Pourquoi un UPSERT et non plus un INSERT OR IGNORE : les lignes déjà en
    # base portent un `legitext` FAUX (un JORFTEXT). Avec OR IGNORE, une
    # ré-ingestion les laissait telles quelles — le correctif n'aurait jamais
    # atteint le stock. On ne touche QUE les colonnes réparées ou nouvelles ;
    # texte, num, titre_text, etat et nota gardent leur valeur.
    ART_SQL = (
        "INSERT INTO legi_articles "
        "(legiarti, legitext, num, titre_text, etat, date_debut, date_fin, texte, nota,"
        " jorftext, hierarchie, liens, ancien_id, type_article) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(legiarti, date_debut) DO UPDATE SET "
        "legitext=excluded.legitext, jorftext=excluded.jorftext, "
        "hierarchie=excluded.hierarchie, liens=excluded.liens, "
        "ancien_id=excluded.ancien_id, type_article=excluded.type_article"
    )
    # Un même LEGITEXT arrive DEUX fois par tarball : texte/struct (TEXTELR, qui
    # ne porte PAS le titre) puis texte/version (TEXTE_VERSION, qui le porte).
    # Un INSERT OR REPLACE brut ferait donc dépendre le titre de l'ordre des
    # membres dans le tar. On ne remplace une valeur que par une valeur NON VIDE.
    TXT_COLS = ["legitext", "titre", "titre_long", "nature", "etat", "date_debut",
                "date_fin", "date_publi", "num_jorf", "nor"] + [c for c, _ in LEGI_TXT_NEW_COLS]
    TXT_SQL = upsert_sql("legi_textes", TXT_COLS, "legitext", keep_non_empty=True)

    def flush():
        nonlocal batch, batch_txt
        if batch:
            conn.executemany(ART_SQL, batch)
            batch = []
        if batch_txt:
            conn.executemany(TXT_SQL, batch_txt)
            batch_txt = []
        conn.commit()

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
                    meta = first_elt(root.find(".//META_COMMUN"), root.find("META/META_COMMUN"))
                    meta_art = first_elt(root.find(".//META_ARTICLE"),
                                         root.find("META/META_SPEC/META_ARTICLE"))
                    if meta is None or meta_art is None:
                        continue
                    legiarti = xml_text(meta.find("ID"))
                    num = xml_text(meta_art.find("NUM"))
                    etat = xml_text(meta_art.find("ETAT"))
                    date_debut = xml_text(meta_art.find("DATE_DEBUT"))
                    date_fin = xml_text(meta_art.find("DATE_FIN"))
                    # parent text id : LEGITEXT joignable, JORFTEXT conservé à part
                    legitext, jorftext, titre_text, hierarchie = legi_contexte(root)
                    texte = elt_html_text(root.find(".//BLOC_TEXTUEL/CONTENU"))
                    nota = elt_html_text(root.find(".//NOTA/CONTENU"))
                    liens = liens_json(root.find(".//LIENS"))
                    ancien_id = xml_text(meta.find("ANCIEN_ID"))
                    type_article = xml_text(meta_art.find("TYPE"))
                    batch.append((legiarti, legitext, num, titre_text, etat,
                                  date_debut, date_fin, texte, nota,
                                  jorftext, hierarchie, liens, ancien_id, type_article))
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
                    meta = first_elt(root.find(".//META_COMMUN"), root.find("META/META_COMMUN"))
                    meta_t = first_elt(root.find(".//META_TEXTE_CHRONICLE"),
                                       root.find("META/META_SPEC/META_TEXTE_CHRONICLE"))
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
                    cid = date_texte = num_parution = num_sequence = ""
                    origine_publi = derniere_modification = ""
                    ministere = autorite = liens = ""
                    if meta_t is not None:
                        titre = xml_text(meta_t.find("TITRE"))
                        titre_long = xml_text(meta_t.find("TITREFULL"))
                        num_jorf = xml_text(meta_t.find("NUM_JORF"))
                        nor = xml_text(meta_t.find("NOR"))
                        date_publi = xml_text(meta_t.find("DATE_PUBLI"))
                        cid = xml_text(meta_t.find("CID"))
                        date_texte = xml_text(meta_t.find("DATE_TEXTE"))
                        num_parution = xml_text(meta_t.find("NUM_PARUTION"))
                        num_sequence = xml_text(meta_t.find("NUM_SEQUENCE"))
                        origine_publi = xml_text(meta_t.find("ORIGINE_PUBLI"))
                        derniere_modification = xml_text(meta_t.find("DERNIERE_MODIFICATION"))
                    meta_v = first_elt(root.find(".//META_TEXTE_VERSION"),
                                       root.find("META/META_SPEC/META_TEXTE_VERSION"))
                    if meta_v is not None:
                        etat = xml_text(meta_v.find("ETAT"))
                        date_debut = xml_text(meta_v.find("DATE_DEBUT"))
                        date_fin = xml_text(meta_v.find("DATE_FIN"))
                        # Le titre du TEXTELR (texte/struct) est vide : seul le
                        # fichier texte/version porte META_TEXTE_VERSION/TITRE.
                        if not titre:
                            titre = xml_text(meta_v.find("TITRE"))
                        if not titre_long:
                            titre_long = xml_text(meta_v.find("TITREFULL"))
                        ministere = xml_text(meta_v.find("MINISTERE"))
                        autorite = xml_text(meta_v.find("AUTORITE"))
                        liens = liens_json(meta_v.find("LIENS"))
                    batch_txt.append((legitext, titre, titre_long, nature, etat,
                                      date_debut, date_fin, date_publi, num_jorf, nor,
                                      cid, date_texte, num_parution, num_sequence,
                                      origine_publi, derniere_modification,
                                      ministere, autorite, liens))
                    n_texts += 1
                    if len(batch_txt) >= 500:
                        flush()
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

JORF_NEW_COLS = [
    ("id_eli", "TEXT"),         # META_COMMUN/ID_ELI — URL ELI pérenne
    ("liens", "TEXT"),          # META_TEXTE_VERSION/LIENS/LIEN (textes visés), JSON
    ("origine_publi", "TEXT"),  # « JORF n°0208 du 6 septembre 2026 »
    ("autorite", "TEXT"),       # META_TEXTE_VERSION/AUTORITE
]


def parse_jorf_like(fund: str, tarball: Path = None, db: Path = None):
    db = Path(db) if db else DB_DIR / f"{fund}.db"
    conn = _open_db(db)
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
    CREATE TRIGGER IF NOT EXISTS {fund}_ad AFTER DELETE ON {fund}_textes BEGIN
        INSERT INTO {fund}_fts({fund}_fts, rowid, jorftext, titre, nature, ministere, texte, nota)
        VALUES ('delete', old.rowid, old.jorftext, old.titre, old.nature, old.ministere, old.texte, old.nota);
    END;
    CREATE TRIGGER IF NOT EXISTS {fund}_au AFTER UPDATE ON {fund}_textes BEGIN
        INSERT INTO {fund}_fts({fund}_fts, rowid, jorftext, titre, nature, ministere, texte, nota)
        VALUES ('delete', old.rowid, old.jorftext, old.titre, old.nature, old.ministere, old.texte, old.nota);
        INSERT INTO {fund}_fts(rowid, jorftext, titre, nature, ministere, texte, nota)
        VALUES (new.rowid, new.jorftext, new.titre, new.nature, new.ministere, new.texte, new.nota);
    END;
    """)
    conn.commit()
    ensure_columns(conn, f"{fund}_textes", JORF_NEW_COLS)

    # Tables TEMP (durée de vie = la connexion, jamais écrites dans le fichier
    # de base) pour rassembler le corps des textes sans tenir le tarball en RAM.
    # temp_store=FILE explicitement : sur le tarball GLOBAL, _arts contient le
    # corps de plusieurs millions d'articles. En MEMORY, la machine tombe.
    conn.execute("PRAGMA temp_store=FILE")
    conn.executescript("""
    CREATE TEMP TABLE _arts (art_id TEXT, cid TEXT, num TEXT, corps TEXT);
    CREATE TEMP TABLE _ordre (art_id TEXT PRIMARY KEY, cid TEXT, rang INTEGER);
    CREATE TEMP TABLE _touched (cid TEXT PRIMARY KEY);
    CREATE INDEX _arts_cid ON _arts(cid);
    """)

    tarball = Path(tarball) if tarball else BULK_DIR / f"Freemium_{fund}.tar.gz"
    n = 0
    n_arts = 0
    n_errors = 0
    batch = []
    batch_art = []
    batch_ord = []
    start = time.time()

    COLS = ["jorftext", "titre", "titre_long", "nature", "date_publi",
            "date_signature", "num_jorf", "nor", "ministere", "texte",
            "nota"] + [c for c, _ in JORF_NEW_COLS]
    # UPSERT plutôt qu'INSERT OR REPLACE : on ne touche que les colonnes qu'on
    # remplit (une colonne dérivée ajoutée plus tard ne serait pas effacée) et
    # le rowid reste stable, donc l'index FTS aussi.
    INS_SQL = upsert_sql(f"{fund}_textes", COLS, "jorftext")

    def flush():
        nonlocal batch, batch_art, batch_ord
        if batch:
            conn.executemany(INS_SQL, batch)
            conn.executemany("INSERT OR IGNORE INTO _touched VALUES (?)",
                             [(b[0],) for b in batch])
            batch = []
        if batch_art:
            conn.executemany("INSERT INTO _arts VALUES (?,?,?,?)", batch_art)
            batch_art = []
        if batch_ord:
            conn.executemany("INSERT OR REPLACE INTO _ordre VALUES (?,?,?)", batch_ord)
            batch_ord = []
        conn.commit()

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

            # ⚠️ LE CORPS DU TEXTE N'EST PAS DANS LE FICHIER version.
            # Le fichier texte/version ne contient que VISAS, SIGNATAIRES,
            # NOTICE, TP, ABRO, RECT — jamais CORPS. Le dispositif est réparti
            # dans les fichiers article/JORF/ARTI/…, sous BLOC_TEXTUEL/CONTENU
            # (vérifié sur JORFARTI000054797714.xml, delta JORF_20260907-214720).
            # Le parseur les ignorait : 99,9 % du stock ancien et 58 % du flux
            # récent n'avaient AUCUN corps de texte.
            # On collecte donc ici les articles (temp _arts) et leur rang dans
            # le plan du texte (STRUCT/LIEN_ART du fichier texte/struct, temp
            # _ordre), puis on recompose les corps après la passe.
            if "/article/" in member.name:
                try:
                    meta = root.find(".//META_COMMUN")
                    ctx = root.find(".//CONTEXTE/TEXTE")
                    if meta is None or ctx is None:
                        continue
                    art_id = xml_text(meta.find("ID"))
                    cid = ctx.get("cid") or ""
                    ma = root.find(".//META_ARTICLE")
                    anum = xml_text(ma.find("NUM")) if ma is not None else ""
                    corps = elt_html_text(root.find(".//BLOC_TEXTUEL/CONTENU"))
                    if cid and corps:
                        batch_art.append((art_id, cid, anum, corps))
                        n_arts += 1
                        if len(batch_art) >= 500:
                            flush()
                except Exception:
                    n_errors += 1
                continue

            if "/texte/struct/" in member.name:
                try:
                    meta = root.find(".//META_COMMUN")
                    struct = root.find(".//STRUCT")
                    if meta is None or struct is None:
                        continue
                    cid = xml_text(meta.find("ID"))
                    for rang, la in enumerate(struct.findall("LIEN_ART")):
                        aid = la.get("id") or ""
                        if aid:
                            batch_ord.append((aid, cid, rang))
                    if len(batch_ord) >= 500:
                        flush()
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
                autorite = liens = ""
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
                    # ⚠️ Dans le format des MISES À JOUR quotidiennes, le titre
                    # n'est PAS dans META_TEXTE_CHRONICLE (qui n'y porte que
                    # CID, NUM, NOR et les dates) mais dans
                    # META_TEXTE_VERSION. Ne le chercher qu'au premier endroit
                    # produisait des textes SANS TITRE : 100 % des textes JORF
                    # ingérés depuis avril 2026 et 51,6 % de ceux de 2025,
                    # contre ~3 % les années issues du stock initial. Un texte
                    # sans titre reste introuvable par son intitulé et
                    # s'affiche nu sur le site. Vérifié le 29 août 2026 sur
                    # JORF_20250830-002214 : <META_TEXTE_VERSION><TITRE> =
                    # « Décret n°2025-859 du 28 août 2025 ».
                    if not titre:
                        titre = xml_text(meta_v.find("TITRE"))
                    if not titre_long:
                        titre_long = xml_text(meta_v.find("TITREFULL"))
                    autorite = xml_text(meta_v.find("AUTORITE"))
                    liens = liens_json(meta_v.find("LIENS"))
                id_eli = xml_text(meta.find("ID_ELI"))
                origine_publi = xml_text(meta_t.find("ORIGINE_PUBLI")) if meta_t is not None else ""
                # Texte principal : l'enveloppe (visas, notice, signataires).
                # Le dispositif est ajouté après la passe, depuis _arts.
                content_parts = []
                for tag in ("NOTICE", "VISAS", "CORPS", "SIGNATAIRES", "TM"):
                    for e in root.iter(tag):
                        content_parts.append(elt_html_text(e))
                        break
                texte = strip_html(" ".join(p for p in content_parts if p))
                nota = elt_html_text(root.find(".//NOTA/CONTENU"))

                batch.append((jorftext, titre, titre_long, nature, date_publi,
                              date_sig, num_jorf, nor, ministere, texte, nota,
                              id_eli, liens, origine_publi, autorite))
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

    # ── Recomposition des corps ────────────────────────────────────────
    # On n'écrit QUE sur les textes insérés pendant CETTE passe (_touched) :
    # un article isolé dans un delta ne doit pas s'ajouter une seconde fois au
    # corps d'un texte déjà complet en base.
    n_bodies = 0
    rows = conn.execute("""
        SELECT a.cid, a.corps
          FROM _arts a
          JOIN _touched t ON t.cid = a.cid
          LEFT JOIN _ordre o ON o.art_id = a.art_id
         ORDER BY a.cid, COALESCE(o.rang, 999999), a.rowid
    """)
    cur_cid, parts = None, []

    def _write_body(cid, parts):
        nonlocal n_bodies
        if not cid or not parts:
            return
        corps = " ".join(parts)
        conn.execute(
            f"UPDATE {fund}_textes SET texte = TRIM(COALESCE(texte,'') || ' ' || ?) "
            f"WHERE jorftext = ?", (corps, cid))
        n_bodies += 1

    for cid, corps in rows:
        if cid != cur_cid:
            _write_body(cur_cid, parts)
            cur_cid, parts = cid, []
        parts.append(corps)
    _write_body(cur_cid, parts)
    conn.commit()
    conn.close()
    print(f"[{fund}] DONE. textes={n}, articles={n_arts}, corps recomposés={n_bodies}, "
          f"errors={n_errors}, time={time.time()-start:.0f}s")


# ─── JADE / CAPP / CASS / CONSTIT : jurisprudence ────────────────────────

# Colonnes « sémantiques » que seul enrich_dila.py remplissait, sur le SEUL
# tarball global de juillet 2025 (enrich_dila.py:188) et par UPDATE sur des id
# déjà présents (:252-254) : aucune décision postérieure au 13/07/2025 n'était
# donc jamais enrichie. Sur 10 727 décisions JADE de 2026 : 0 abstrat,
# 0 type de recours. Le parseur des deltas les remplit désormais lui-même.
JURIS_ENRICH_COLS = [
    ("abstrats", "TEXT"),          # SOMMAIRE/SCT, avec @TYPE (PRINCIPAL/REFERENCE)
    ("resume", "TEXT"),            # SOMMAIRE/ANA
    ("renvois", "TEXT"),           # CITATION_JP / RAPPROCHEMENTS
    ("commissaire_gvt", "TEXT"),   # META_JURI_ADMIN/COMMISSAIRE_GVT
    ("type_rec", "TEXT"),          # META_JURI_ADMIN/TYPE_REC
    ("publi_recueil", "TEXT"),     # META_JURI_ADMIN/PUBLI_RECUEIL (A/B/C)
    ("publi_bull", "TEXT"),        # META_JURI_JUDI/PUBLI_BULL@publie
    ("nature_qualifiee", "TEXT"),  # META_JURI_CONSTIT/NATURE_QUALIFIEE
    ("saisines", "TEXT"),          # TEXTE/SAISINES
    ("loi_def", "TEXT"),           # META_JURI_CONSTIT/LOI_DEF
    ("liens_textes", "TEXT"),      # LIENS/LIEN (JSON)
]

# Champs que la source donne et qu'aucune colonne n'accueillait.
JURIS_NEW_COLS = [
    ("demandeur", "TEXT"),
    ("defendeur", "TEXT"),
    ("form_dec_att", "TEXT"),      # juridiction de la décision attaquée
    ("date_dec_att", "TEXT"),
    ("siege_appel", "TEXT"),
    ("juri_prem", "TEXT"),         # juridiction de 1re instance
    ("lieu_prem", "TEXT"),
    ("numeros_affaires", "TEXT"),  # TOUS les NUMERO_AFFAIRE (JSON) — `numero` n'en garde qu'un
    ("observations", "TEXT"),      # CONSTIT : observations du Gouvernement
    ("url_cc", "TEXT"),            # CONSTIT
    ("titre_jo", "TEXT"),          # CONSTIT
    ("nor", "TEXT"),               # CONSTIT
    ("ancien_id", "TEXT"),
]


def juris_enrich(root, meta_spec) -> dict:
    """Ce que `enrich_dila.py` faisait a posteriori sur le stock, fait
    directement à l'ingestion — donc y compris sur les deltas quotidiens."""
    out = {c: "" for c, _ in JURIS_ENRICH_COLS}

    # SCT : on conserve @TYPE (PRINCIPAL / REFERENCE), que l'aplatissement
    # de `sommaire` et l'ancien enrich_dila.py jetaient tous les deux.
    sct = []
    for e in root.iter("SCT"):
        t = xml_text(e)
        if not t:
            continue
        typ = e.get("TYPE", "")
        sct.append(f"[{typ}] {t}" if typ else t)
    out["abstrats"] = "\n".join(sct)
    out["resume"] = "\n\n".join(t for t in (xml_text(e) for e in root.iter("ANA")) if t)

    renvois = []
    for tag in ("RAPPROCHEMENTS", "CITATION_JP"):
        for el in root.iter(tag):
            c = el.find("CONTENU")
            t = xml_text(c) if c is not None else xml_text(el)
            if t:
                renvois.append(t)
    out["renvois"] = "\n".join(renvois)
    out["liens_textes"] = liens_json(root.find(".//LIENS"))

    if meta_spec is not None:
        for tag, col in (("COMMISSAIRE_GVT", "commissaire_gvt"),
                         ("TYPE_REC", "type_rec"),
                         ("PUBLI_RECUEIL", "publi_recueil"),
                         ("NATURE_QUALIFIEE", "nature_qualifiee")):
            out[col] = xml_text(meta_spec.find(tag))
        pb = meta_spec.find("PUBLI_BULL")
        if pb is not None:
            out["publi_bull"] = pb.get("publie", "") or xml_text(pb)
        ld = meta_spec.find("LOI_DEF")
        if ld is not None:
            parts = [p for p in (ld.get("num", ""), ld.get("date", ""), xml_text(ld))
                     if p and p != "2999-01-01"]
            out["loi_def"] = " | ".join(parts)

    sais = [t for t in (elt_html_text(s) for s in root.iter("SAISINE")) if t]
    if not sais:
        for s in root.iter("SAISINES"):
            t = elt_html_text(s)
            if t:
                sais.append(t)
            break
    out["saisines"] = "\n\n".join(sais)
    return out


def parse_juris(fund: str, tarball: Path = None, db: Path = None):
    """JADE=admin (CE+CAA+TA), CAPP=CA, CASS=Cass, CONSTIT=CC.
    Schema commun : decisions_{fund}.
    """
    db = Path(db) if db else DB_DIR / f"{fund}.db"
    conn = _open_db(db)
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
    CREATE TRIGGER IF NOT EXISTS {fund}_ad AFTER DELETE ON {fund}_decisions BEGIN
        INSERT INTO {fund}_fts({fund}_fts, rowid, id, juridiction, numero, titre, sommaire, texte)
        VALUES ('delete', old.rowid, old.id, old.juridiction, old.numero, old.titre, old.sommaire, old.texte);
    END;
    CREATE TRIGGER IF NOT EXISTS {fund}_au AFTER UPDATE ON {fund}_decisions BEGIN
        INSERT INTO {fund}_fts({fund}_fts, rowid, id, juridiction, numero, titre, sommaire, texte)
        VALUES ('delete', old.rowid, old.id, old.juridiction, old.numero, old.titre, old.sommaire, old.texte);
        INSERT INTO {fund}_fts(rowid, id, juridiction, numero, titre, sommaire, texte)
        VALUES (new.rowid, new.id, new.juridiction, new.numero, new.titre, new.sommaire, new.texte);
    END;
    """)
    conn.commit()
    ensure_columns(conn, f"{fund}_decisions", JURIS_ENRICH_COLS + JURIS_NEW_COLS)

    tarball = Path(tarball) if tarball else BULK_DIR / f"Freemium_{fund}.tar.gz"
    if not tarball.exists():
        print(f"[{fund}] no tarball at {tarball}, skip")
        return
    n = 0
    n_errors = 0
    batch = []
    start = time.time()

    # Colonnes nommées explicitement : les tables *_decisions ont été
    # étendues avec abstrats/resume/renvois/commissaire_gvt/type_rec/
    # publi_recueil/publi_bull/nature_qualifiee/saisines/loi_def/
    # liens_textes après création. Un VALUES(?×15) sur une table à 26
    # colonnes fait planter SQLite silencieusement (l'exception est
    # rattrapée par le try du membre → n_errors++ mais batch pas vidé,
    # donc s'accumule sans jamais insérer).
    BASE_COLS = ["id", "ecli", "juridiction", "formation", "date", "numero",
                 "solution", "nature", "president", "rapporteur",
                 "avocat_general", "avocats", "titre", "sommaire", "texte"]
    ALL_COLS = (BASE_COLS + [c for c, _ in JURIS_ENRICH_COLS]
                + [c for c, _ in JURIS_NEW_COLS])
    # ⚠️ UPSERT et non INSERT OR REPLACE. OR REPLACE SUPPRIME la ligne puis en
    # insère une neuve : toute colonne que le parseur ne remplit pas est perdue.
    # `capp_decisions.numero_rg_norm` est exactement dans ce cas — elle est
    # dérivée après coup par scripts/prod-oneshot/extract_rg_prod.py, et une
    # ré-ingestion complète du fonds CAPP l'aurait effacée sur les 73 050
    # lignes concernées, sans le moindre message. L'UPSERT ne touche que les
    # colonnes nommées, et conserve le rowid (donc l'index FTS reste aligné).
    INS_SQL = upsert_sql(f"{fund}_decisions", ALL_COLS, "id")

    def flush():
        nonlocal batch
        if not batch:
            return
        conn.executemany(INS_SQL, batch)
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
                numeros = []   # défini hors du bloc : il est relu plus bas
                # ⚠️ Les métadonnées sont réparties sur DEUX conteneurs, et le
                # parseur ne lisait que le premier. Vérifié sur l'archive
                # réelle CASS_20260824 :
                #   META_JURI       → TITRE, DATE_DEC, JURIDICTION, SOLUTION,
                #                     et un NUMERO **interne** (« 22600719 ») ;
                #   META_JURI_JUDI  → ECLI, FORMATION, PRESIDENT, RAPPORTEUR,
                #                     AVOCATS, et NUMEROS_AFFAIRES, qui porte
                #                     le VRAI n° de pourvoi (« 23-18085 »).
                # Conséquence : ECLI, formation, magistrats et avocats
                # arrivaient vides, et le numéro stocké n'était pas celui par
                # lequel on cite un arrêt — donc introuvable par recherche de
                # pourvoi. Les lignes déjà en base, issues du stock initial,
                # portent bien « 25-86842 » : le prochain delta les aurait
                # ÉCRASÉES (INSERT OR REPLACE) par la mauvaise valeur.
                # Le conteneur s'appelle META_JURI_ADMIN pour l'ordre
                # administratif — on essaie les deux.
                # ⚠️ CONSTIT : le conteneur s'appelle META_JURI_CONSTIT. Il
                # n'était dans aucune des deux branches → l'ECLI (et NOR,
                # TITRE_JO, URL_CC, NATURE_QUALIFIEE) redevenait introuvable
                # dans le flux courant, alors qu'une version antérieure du
                # parseur le trouvait par root.find(".//ECLI").
                meta_spec = first_elt(root.find(".//META_JURI_JUDI"),
                                      root.find(".//META_JURI_ADMIN"),
                                      root.find(".//META_JURI_CONSTIT"))

                def _champ(tag: str) -> str:
                    for src in (meta_j, meta_spec):
                        if src is not None:
                            v = xml_text(src.find(tag))
                            if v:
                                return v
                    return ""

                if meta_j is not None or meta_spec is not None:
                    ecli = _champ("ECLI")
                    juridiction = _champ("JURIDICTION")
                    date = _champ("DATE_DEC")
                    solution = _champ("SOLUTION")
                    formation = _champ("FORMATION")
                    president = _champ("PRESIDENT")
                    rapporteur = _champ("RAPPORTEUR")
                    # ⚠️ La balise s'appelle AVOCAT_GL, pas AVOCAT_GENERAL —
                    # laquelle n'existe dans AUCUN format DILA. Mesuré avant
                    # correctif : avocat_general non vide = 0 sur 6 000 lignes
                    # CASS, anciennes comme récentes.
                    avocat_general = _champ("AVOCAT_GL") or _champ("AVOCAT_GENERAL")
                    titre = _champ("TITRE")
                    # Numéro : le pourvoi d'abord, le n° interne en dernier
                    # recours (c'est ce dernier que le code servait).
                    numeros = [xml_text(x) for x in root.iter("NUMERO_AFFAIRE")]
                    numeros = [x for x in numeros if x]
                    numero = numeros[0] if numeros else _champ("NUMERO")
                    # AVOCATS est tantôt une liste <AVOCAT>, tantôt un simple
                    # texte (« SCP Delamarre et Jehannin, SELAS Froger… »).
                    avocats_elts = [x for x in root.iter("AVOCAT") if xml_text(x)]
                    avocats = (" ; ".join(xml_text(a) for a in avocats_elts)
                               if avocats_elts else _champ("AVOCATS"))
                # sommaire et texte
                somm_elt = first_elt(root.find(".//SOMMAIRE/CONTENU"), root.find(".//SOMMAIRE"))
                sommaire = strip_html(ET.tostring(somm_elt, encoding="unicode")) if somm_elt is not None else ""
                texte_elt = first_elt(root.find(".//CONTENU"), root.find(".//TEXTE"))
                texte = strip_html(ET.tostring(texte_elt, encoding="unicode")) if texte_elt is not None else ""
                if not texte:
                    # Fallback: prendre tout le texte sauf META
                    for m in root.iter("META"):
                        m.getparent().remove(m) if m.getparent() is not None else None
                    texte = strip_html(ET.tostring(root, encoding="unicode"))

                enr = juris_enrich(root, meta_spec)
                obs_elt = root.find(".//OBSERVATIONS")
                extra = {
                    "demandeur": _champ("DEMANDEUR"),
                    "defendeur": _champ("DEFENDEUR"),
                    "form_dec_att": _champ("FORM_DEC_ATT"),
                    "date_dec_att": _champ("DATE_DEC_ATT"),
                    "siege_appel": _champ("SIEGE_APPEL"),
                    "juri_prem": _champ("JURI_PREM"),
                    "lieu_prem": _champ("LIEU_PREM"),
                    # `numero` ne garde que le premier : les pourvois joints en
                    # portent plusieurs, et les suivants étaient jetés.
                    "numeros_affaires": as_json(numeros) if len(numeros) > 1 else "",
                    "observations": elt_html_text(obs_elt),
                    "url_cc": _champ("URL_CC"),
                    "titre_jo": _champ("TITRE_JO"),
                    "nor": _champ("NOR"),
                    "ancien_id": xml_text(meta.find("ANCIEN_ID")),
                }
                batch.append(
                    (did, ecli, juridiction, formation, date, numero, solution,
                     nature, president, rapporteur, avocat_general, avocats,
                     titre, sommaire, texte)
                    + tuple(enr[c] for c, _ in JURIS_ENRICH_COLS)
                    + tuple(extra[c] for c, _ in JURIS_NEW_COLS))
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

KALI_NEW_COLS = [
    ("conteneur_id", "TEXT"),    # KALICONT du texte (la convention collective)
    ("texte_id", "TEXT"),        # KALITEXT parent (l'accord / l'avenant)
    ("texte_titre", "TEXT"),     # titre propre de l'accord (TITRE_TXT)
    ("article_num", "TEXT"),     # META_ARTICLE/NUM
    ("article_titre", "TEXT"),   # META_ARTICLE/TITRE
    ("date_deb_ext", "TEXT"),    # dates d'EXTENSION (arrêté d'extension)
    ("date_fin_ext", "TEXT"),
    ("nor", "TEXT"),
    ("date_texte", "TEXT"),      # date de signature
    ("origine_publi", "TEXT"),   # « BO n°2026-19 »
    ("section_id", "TEXT"),      # KALISCTA de rattachement
    ("section_titre", "TEXT"),   # SECTION_TA/TITRE_TA
    ("liens", "TEXT"),           # LIENS/LIEN (JSON)
]


def parse_kali(tarball: Path = None, db: Path = None):
    """KALI = conventions collectives, accords de branche, avenants.

    ⚠️ LE BUG RACINE (réparé ici). Le parseur cherchait META_TEXTE_KALI ou
    META_CONVENTION_COLLECTIVE. **Ces deux balises n'existent dans aucun
    fichier KALI** : sur le tarball entier KALI_20260907-214720,
    `grep -c "META_TEXTE_KALI\\|META_CONVENTION_COLLECTIVE"` → 0.
    Le garde-fou `if meta_k is None: continue` (ajouté le 29/08/2026) faisait
    donc SAUTER 100 % des fichiers : le fonds n'ingérait plus rien, et les
    305 839 lignes déjà en base n'avaient ni titre, ni IDCC, ni date.

    Les vrais conteneurs, vérifiés sur le delta du 07/09/2026 :
      KALICONT (racine <IDCC>)      → META_SPEC/META_CONTENEUR/{TITRE,ETAT,NUM,DATE_PUBLI}
                                       où **NUM est l'IDCC** ; STRUCTURE_TXT/TM/LIEN_TXT
                                       rattache les KALITEXT à la convention.
      KALITEXT (racine <TEXTEKALI>  → META_TEXTE_CHRONICLE/{NOR,DATE_TEXTE,DATE_PUBLI,…}
                ou <TEXTE_VERSION>)   et, en version, META_TEXTE_VERSION/{TITRE,ETAT,
                                       DATE_DEBUT,DATE_FIN}.
      KALIARTI (racine <ARTICLE>)   → META_ARTICLE/{NUM,TITRE,ETAT,DATE_DEBUT,DATE_FIN,
                                       DATE_DEB_EXT,DATE_FIN_EXT} et CONTEXTE/CONTENEUR
                                       @num (IDCC) @titre @etat @date_publi.
      KALISCTA (racine <SECTION_TA>)→ pas de META_COMMUN ; TITRE_TA + STRUCTURE_TA/LIEN_ART.
    """
    db = Path(db) if db else DB_DIR / "kali.db"
    conn = _open_db(db)
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
    CREATE TRIGGER IF NOT EXISTS kali_ad AFTER DELETE ON kali_textes BEGIN
        INSERT INTO kali_fts(kali_fts, rowid, id, idcc, titre, texte)
        VALUES ('delete', old.rowid, old.id, old.idcc, old.titre, old.texte);
    END;
    CREATE TRIGGER IF NOT EXISTS kali_au AFTER UPDATE ON kali_textes BEGIN
        INSERT INTO kali_fts(kali_fts, rowid, id, idcc, titre, texte)
        VALUES ('delete', old.rowid, old.id, old.idcc, old.titre, old.texte);
        INSERT INTO kali_fts(rowid, id, idcc, titre, texte)
        VALUES (new.rowid, new.id, new.idcc, new.titre, new.texte);
    END;
    """)
    conn.commit()
    ensure_columns(conn, "kali_textes", KALI_NEW_COLS)
    conn.execute("PRAGMA temp_store=FILE")
    conn.executescript("""
    CREATE TEMP TABLE _sect (art_id TEXT PRIMARY KEY, sect_id TEXT, sect_titre TEXT);
    CREATE TEMP TABLE _cont (txt_id TEXT PRIMARY KEY, cont_id TEXT, idcc TEXT,
                             cont_titre TEXT, txt_titre TEXT);
    """)
    tarball = Path(tarball) if tarball else BULK_DIR / "Freemium_kali.tar.gz"
    if not tarball.exists():
        print("[kali] no tarball, skip")
        return
    n = 0
    n_errors = 0
    batch = []
    batch_sect = []
    batch_cont = []
    start = time.time()

    COLS = ["id", "idcc", "titre", "nature", "etat", "date_publi", "date_debut",
            "date_fin", "texte"] + [c for c, _ in KALI_NEW_COLS]
    # Un KALITEXT arrive deux fois (texte/struct puis texte/version) et seul le
    # second porte le titre : on ne remplace jamais une valeur par du vide.
    INS_SQL = upsert_sql("kali_textes", COLS, "id", keep_non_empty=True)

    def flush():
        nonlocal batch, batch_sect, batch_cont
        if batch:
            conn.executemany(INS_SQL, batch)
            batch = []
        if batch_sect:
            conn.executemany("INSERT OR REPLACE INTO _sect VALUES (?,?,?)", batch_sect)
            batch_sect = []
        if batch_cont:
            conn.executemany("INSERT OR REPLACE INTO _cont VALUES (?,?,?,?,?)", batch_cont)
            batch_cont = []
        conn.commit()

    print(f"[kali] streaming {tarball.name}…")
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
                tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

                # ── KALISCTA : sections. Pas de META_COMMUN, donc l'ancien
                # parseur les jetait avant même le test META_TEXTE_KALI. On les
                # garde pour RATTACHER les articles à leur section.
                if tag == "SECTION_TA":
                    sid = xml_text(root.find("ID"))
                    stit = xml_text(root.find("TITRE_TA"))
                    st = root.find("STRUCTURE_TA")
                    if st is not None:
                        for la in st.iter("LIEN_ART"):
                            aid = la.get("id") or ""
                            if aid:
                                batch_sect.append((aid, sid, stit))
                    if len(batch_sect) >= 300:
                        flush()
                    continue

                meta = root.find(".//META_COMMUN")
                if meta is None:
                    continue
                kid = xml_text(meta.find("ID"))
                nature = xml_text(meta.find("NATURE"))
                idcc = titre = etat = date_publi = date_debut = date_fin = ""
                conteneur_id = texte_id = texte_titre = ""
                article_num = article_titre = ""
                date_deb_ext = date_fin_ext = nor = date_texte = origine_publi = ""
                texte = ""
                liens = liens_json(root.find(".//LIENS"))

                meta_cont = root.find(".//META_CONTENEUR")
                meta_art = root.find(".//META_ARTICLE")
                meta_chr = root.find(".//META_TEXTE_CHRONICLE")
                meta_ver = root.find(".//META_TEXTE_VERSION")

                if meta_cont is not None:
                    # KALICONT : la convention collective elle-même.
                    conteneur_id = kid
                    idcc = xml_text(meta_cont.find("NUM"))
                    titre = xml_text(meta_cont.find("TITRE"))
                    etat = xml_text(meta_cont.find("ETAT"))
                    date_publi = xml_text(meta_cont.find("DATE_PUBLI"))
                    texte = elt_html_text(root.find(".//DESCRIPTION_FUSION/CONTENU"))
                    # Rattachement des accords/avenants de cette convention.
                    for lt in root.iter("LIEN_TXT"):
                        tid = lt.get("idtxt") or ""
                        if tid:
                            batch_cont.append((tid, kid, idcc, titre,
                                               lt.get("titretxt", "")))
                else:
                    ctx_txt = root.find(".//CONTEXTE/TEXTE")
                    ctx_cont = root.find(".//CONTEXTE/CONTENEUR")
                    if ctx_cont is not None:
                        # KALIARTI / KALISCTA : tout est en attributs.
                        conteneur_id = ctx_cont.get("cid", "")
                        idcc = ctx_cont.get("num", "")
                        titre = ctx_cont.get("titre", "")
                        etat = ctx_cont.get("etat", "")
                        date_publi = ctx_cont.get("date_publi", "")
                    if ctx_txt is not None:
                        texte_id = ctx_txt.get("cid", "")
                        nor = ctx_txt.get("nor", "")
                        date_texte = ctx_txt.get("date_signature", "")
                        tt = ctx_txt.find("TITRE_TXT")
                        if tt is not None:
                            texte_titre = tt.get("c_titre_court") or xml_text(tt)
                    if meta_art is not None:
                        article_num = xml_text(meta_art.find("NUM"))
                        article_titre = xml_text(meta_art.find("TITRE"))
                        etat = xml_text(meta_art.find("ETAT")) or etat
                        date_debut = xml_text(meta_art.find("DATE_DEBUT"))
                        date_fin = xml_text(meta_art.find("DATE_FIN"))
                        date_deb_ext = xml_text(meta_art.find("DATE_DEB_EXT"))
                        date_fin_ext = xml_text(meta_art.find("DATE_FIN_EXT"))
                    if meta_chr is not None:
                        # KALITEXT (accord / avenant) : struct ou version.
                        texte_id = texte_id or xml_text(meta_chr.find("CID")) or kid
                        nor = nor or xml_text(meta_chr.find("NOR"))
                        date_texte = date_texte or xml_text(meta_chr.find("DATE_TEXTE"))
                        date_publi = date_publi or xml_text(meta_chr.find("DATE_PUBLI"))
                        origine_publi = xml_text(meta_chr.find("ORIGINE_PUBLI"))
                    if meta_ver is not None:
                        texte_titre = texte_titre or xml_text(meta_ver.find("TITREFULL")) \
                            or xml_text(meta_ver.find("TITRE"))
                        etat = xml_text(meta_ver.find("ETAT")) or etat
                        date_debut = date_debut or xml_text(meta_ver.find("DATE_DEBUT"))
                        date_fin = date_fin or xml_text(meta_ver.find("DATE_FIN"))
                    content = root.find(".//BLOC_TEXTUEL/CONTENU")
                    texte = elt_html_text(content)

                batch.append((kid, idcc, titre, nature, etat, date_publi,
                              date_debut, date_fin, texte,
                              conteneur_id, texte_id, texte_titre, article_num,
                              article_titre, date_deb_ext, date_fin_ext, nor,
                              date_texte, origine_publi, "", "", liens))
                n += 1
                if len(batch) >= 300:
                    flush()
                    if n % 5000 == 0:
                        elapsed = time.time() - start
                        print(f"  [{n:>6} kali] {n/elapsed:.0f}/s ({elapsed/60:.1f}min)")
            except Exception:
                n_errors += 1
    flush()

    # ── Rattachements différés ────────────────────────────────────────
    # 1. article → section (KALISCTA)
    n_sect = conn.execute("""
        UPDATE kali_textes SET
            section_id    = (SELECT sect_id    FROM _sect WHERE art_id = kali_textes.id),
            section_titre = (SELECT sect_titre FROM _sect WHERE art_id = kali_textes.id)
         WHERE id IN (SELECT art_id FROM _sect)
    """).rowcount
    # 2. KALITEXT → sa convention, via le plan du KALICONT
    n_cont = conn.execute("""
        UPDATE kali_textes SET
            conteneur_id = (SELECT cont_id    FROM _cont WHERE txt_id = kali_textes.id),
            idcc         = (SELECT idcc       FROM _cont WHERE txt_id = kali_textes.id),
            titre        = (SELECT cont_titre FROM _cont WHERE txt_id = kali_textes.id)
         WHERE id IN (SELECT txt_id FROM _cont)
           AND (idcc IS NULL OR idcc = '')
    """).rowcount
    # 3. KALITEXT absent du plan (le KALICONT n'est pas dans ce delta) :
    #    on prend l'IDCC de l'un de ses propres articles, qui le porte.
    n_back = conn.execute("""
        UPDATE kali_textes SET
            conteneur_id = (SELECT a.conteneur_id FROM kali_textes a
                             WHERE a.texte_id = kali_textes.id AND a.idcc <> '' LIMIT 1),
            idcc         = (SELECT a.idcc  FROM kali_textes a
                             WHERE a.texte_id = kali_textes.id AND a.idcc <> '' LIMIT 1),
            titre        = (SELECT a.titre FROM kali_textes a
                             WHERE a.texte_id = kali_textes.id AND a.idcc <> '' LIMIT 1)
         WHERE (idcc IS NULL OR idcc = '')
           AND EXISTS (SELECT 1 FROM kali_textes a
                        WHERE a.texte_id = kali_textes.id AND a.idcc <> '')
    """).rowcount
    conn.commit()
    print(f"[kali] rattachements : sections={n_sect}, conteneurs={n_cont}, "
          f"repli par article={n_back}")
    conn.close()
    print(f"[kali] DONE. textes={n}, errors={n_errors}")


# ─── CNIL : délibérations ──────────────────────────────────────────────

CNIL_NEW_COLS = [
    ("nature", "TEXT"),          # META_COMMUN/NATURE (DELIBERATION…)
    ("nature_delib", "TEXT"),    # META_CNIL/NATURE_DELIB (Sanction, Avis, Autorisation…)
    ("etat_juridique", "TEXT"),  # META_CNIL/ETAT_JURIDIQUE
    ("nor", "TEXT"),
    ("titre_long", "TEXT"),      # META_CNIL/TITREFULL
    ("date_publi", "TEXT"),      # META_CNIL/DATE_PUBLI, distincte de la date de délibération
    ("origine_publi", "TEXT"),
]


def parse_cnil(tarball: Path = None, db: Path = None):
    db = Path(db) if db else DB_DIR / "cnil.db"
    conn = _open_db(db)
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
    CREATE TRIGGER IF NOT EXISTS cnil_ad AFTER DELETE ON cnil_deliberations BEGIN
        INSERT INTO cnil_fts(cnil_fts, rowid, id, numero, titre, formation, texte)
        VALUES ('delete', old.rowid, old.id, old.numero, old.titre, old.formation, old.texte);
    END;
    CREATE TRIGGER IF NOT EXISTS cnil_au AFTER UPDATE ON cnil_deliberations BEGIN
        INSERT INTO cnil_fts(cnil_fts, rowid, id, numero, titre, formation, texte)
        VALUES ('delete', old.rowid, old.id, old.numero, old.titre, old.formation, old.texte);
        INSERT INTO cnil_fts(rowid, id, numero, titre, formation, texte)
        VALUES (new.rowid, new.id, new.numero, new.titre, new.formation, new.texte);
    END;
    """)
    conn.commit()
    ensure_columns(conn, "cnil_deliberations", CNIL_NEW_COLS)
    tarball = Path(tarball) if tarball else BULK_DIR / "Freemium_cnil.tar.gz"
    if not tarball.exists():
        print("[cnil] no tarball, skip")
        return
    n = 0
    batch = []
    COLS = ["id", "numero", "titre", "date", "formation",
            "texte"] + [c for c, _ in CNIL_NEW_COLS]
    INS_SQL = upsert_sql("cnil_deliberations", COLS, "id")
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
                # Tout est dans META_CNIL — on l'interroge NOMMÉMENT plutôt que
                # par un `.//` global : `.//TITRE` attrapait au passage
                # n'importe quel <TITRE> du corps, et la cascade de dates
                # pouvait tomber sur un DATE_PUBLI d'un LIEN.
                mc = root.find(".//META_CNIL")
                def _c(tag: str) -> str:
                    return xml_text(mc.find(tag)) if mc is not None else ""
                numero = _c("NUMERO") or xml_text(root.find(".//NUMERO"))
                titre = _c("TITRE") or xml_text(root.find(".//TITRE"))
                # DATE_TEXTE = date de la délibération ; DATE_PUBLI = date de
                # publication au JO. Mesuré avant correctif : 0 date sur
                # 4 000 lignes, alors que DATE_TEXTE est bien dans la source.
                date = _c("DATE_TEXTE") or _c("DATE_PUBLI") or xml_text(root.find(".//DATE_DEC"))
                formation = xml_text(root.find(".//FORMATION"))
                content = first_elt(root.find(".//BLOC_TEXTUEL/CONTENU"),
                                    root.find(".//CONTENU"))
                texte = elt_html_text(content)
                batch.append((did, numero, titre, date, formation, texte,
                              xml_text(meta.find("NATURE")), _c("NATURE_DELIB"),
                              _c("ETAT_JURIDIQUE"), _c("NOR"), _c("TITREFULL"),
                              _c("DATE_PUBLI"), _c("ORIGINE_PUBLI")))
                n += 1
                if len(batch) >= 200:
                    conn.executemany(INS_SQL, batch)
                    conn.commit()
                    batch = []
            except Exception:
                continue
    if batch:
        conn.executemany(INS_SQL, batch)
        conn.commit()
    conn.close()
    print(f"[cnil] DONE. deliberations={n}")


# ─── Main ────────────────────────────────────────────────────────────

PARSERS = {
    "legi":    parse_legi,
    "jorf":    lambda **kw: parse_jorf_like("jorf", **kw),
    "inca":    lambda **kw: parse_juris("inca", **kw),
    "jade":    lambda **kw: parse_juris("jade", **kw),
    "capp":    lambda **kw: parse_juris("capp", **kw),
    "constit": lambda **kw: parse_juris("constit", **kw),
    "cass":    lambda **kw: parse_juris("cass", **kw),
    "kali":    parse_kali,
    "cnil":    parse_cnil,
}


def main():
    p = argparse.ArgumentParser(description="Parseur des bulks DILA → SQLite FTS5")
    p.add_argument("fond", choices=sorted(PARSERS))
    p.add_argument("--tarball", help="chemin du .tar.gz (défaut : "
                                     "BULK_DIR/Freemium_<fond>.tar.gz)")
    p.add_argument("--db", help="chemin de la base SQLite (défaut : DB_DIR/<fond>.db)")
    args = p.parse_args()
    PARSERS[args.fond](tarball=args.tarball, db=args.db)


if __name__ == "__main__":
    main()
