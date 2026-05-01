"""Warehouse HTTP read-only server for justicelibre.

Exposes the DILA bulk SQLite databases (legi, jade, jorf, kali, cnil) stored
on al-uzza to the frontend/MCP running on PatrologiaLatina, via a private
HTTP bridge.

Architecture:
- Binds on port 8001, Hetzner Cloud Firewall whitelists only PatrologiaLatina
- Auth: shared secret in `X-Warehouse-Key` header (hmac.compare_digest)
- Read-only SQLite connections (`uri=True&mode=ro`)
- ThreadingHTTPServer (stdlib, consistent with token_server.py)
- Endpoints:
    GET  /v1/health
    GET  /v1/law?code=CC&num=1382&date=1992-05-15
    GET  /v1/law/versions?code=CC&num=1382
    POST /v1/law/batch          body: {"date": "...", "refs": [{"code", "num"}]}
    GET  /v1/search/{fond}?q=...&limit=&offset=&sort=&date_min=&date_max=
    GET  /v1/decision/{fond}/{id}
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import date as _date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.stdout.reconfigure(line_buffering=True)

# ─── CONFIG ──────────────────────────────────────────────────────────

DB_DIR = Path(os.environ.get("JL_WAREHOUSE_DB_DIR", "/opt/justicelibre/dila"))
KEY_FILE = Path(os.environ.get("JL_WAREHOUSE_KEY_FILE", "/etc/justicelibre/warehouse.key"))
BIND = (os.environ.get("JL_WAREHOUSE_HOST", "0.0.0.0"), int(os.environ.get("JL_WAREHOUSE_PORT", "8001")))

try:
    WAREHOUSE_KEY = KEY_FILE.read_text().strip()
except FileNotFoundError:
    sys.exit(f"warehouse key file missing: {KEY_FILE}. Run: openssl rand -hex 32 > {KEY_FILE}")
if len(WAREHOUSE_KEY) < 32:
    sys.exit(f"warehouse key is too short (< 32 chars)")

# Sécurité : refuser de démarrer si la clé est lisible par d'autres utilisateurs
_KEY_MODE = KEY_FILE.stat().st_mode & 0o777
if _KEY_MODE & 0o077:
    sys.exit(
        f"warehouse key {KEY_FILE} has insecure permissions ({oct(_KEY_MODE)}). "
        f"Run: chmod 600 {KEY_FILE}"
    )

# ─── CODE → LEGITEXT MAPPING (22 codes supportés) ────────────────────

CODE_TO_LEGITEXT: dict[str, str] = {
    # ─── 22 codes consolidés (LEGITEXT stables) ─────────────────
    "CC":      "LEGITEXT000006070721",  # Code civil
    "CP":      "LEGITEXT000006070719",  # Code pénal
    "CPC":     "LEGITEXT000006070716",  # Code de procédure civile
    "CPP":     "LEGITEXT000006071154",  # Code de procédure pénale
    "CT":      "LEGITEXT000006072050",  # Code du travail
    "CSP":     "LEGITEXT000006072665",  # Code de la santé publique
    "CJA":     "LEGITEXT000006070933",  # Code de justice administrative
    "CGCT":    "LEGITEXT000006070633",  # Code général des collectivités territoriales
    "CRPA":    "LEGITEXT000031366350",  # Code des relations entre le public et l'administration
    "CPI":     "LEGITEXT000006069414",  # Code de la propriété intellectuelle
    "CASF":    "LEGITEXT000006074069",  # Code de l'action sociale et des familles
    "CMF":     "LEGITEXT000006072026",  # Code monétaire et financier
    "C.com":   "LEGITEXT000005634379",  # Code de commerce
    "C.cons":  "LEGITEXT000006069565",  # Code de la consommation
    "C.éduc":  "LEGITEXT000006071191",  # Code de l'éducation
    "CU":      "LEGITEXT000006074075",  # Code de l'urbanisme
    "C.env":   "LEGITEXT000006074220",  # Code de l'environnement
    "CR":      "LEGITEXT000006071367",  # Code rural et de la pêche maritime
    "CGI":     "LEGITEXT000006069569",  # Code général des impôts (annexe II)
    "CESEDA":  "LEGITEXT000006070158",  # Code de l'entrée et du séjour des étrangers
    "CSS":     "LEGITEXT000006073189",  # Code de la sécurité sociale
    "CCH":     "LEGITEXT000006074096",  # Code de la construction et de l'habitation
    # ─── Constitution ───────────────────────────────────────────
    # La Constitution du 4 octobre 1958 est indexée en LEGI via JORFTEXT
    # (publication au JO, pas un code consolidé). Articles numérotés "1", "66"…
    "CONST":     "JORFTEXT000000571356",  # Constitution du 4 octobre 1958 (89 articles)
    # ─── Lois non codifiées fréquemment citées ─────────────────
    # DILA les indexe via JORFTEXT (pas LEGITEXT) car ce sont des publications
    # au JO, pas des codes consolidés. L'URL Légifrance utilise `/loda/` au
    # lieu de `/codes/` pour ces textes.
    "LIL":       "JORFTEXT000000886460",  # Loi 78-17 Informatique et Libertés (474 articles)
    "LO58":      "JORFTEXT000000705065",  # Ordonnance 58-1067 organique Conseil constit. (95 art.)
    "L2005-102": "JORFTEXT000000809647",  # Loi 2005-102 handicap (123 articles)
}


def _is_codified(legitext: str) -> bool:
    """Un texte 'codifié' commence par LEGITEXT (code) vs JORFTEXT (loi non codifiée)."""
    return legitext.startswith("LEGITEXT")


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _build_source_url(identifier: str, legitext: str = "", at_date: str | None = None) -> str | None:
    """Reconstruit l'URL canonique d'un document à partir de son ID.

    Règles basées sur les conventions stables Légifrance / Conseil Constitutionnel /
    Conseil d'État / EUR-Lex / HUDOC.

    `at_date` (YYYY-MM-DD) est appendé aux URLs Légifrance qui supportent le routing
    versionné (/codes/article_lc, /loda/article_lc, /codes/texte_lc, /loda/id) pour
    que le lien affiche la version en vigueur à cette date précise.
    """
    if not identifier:
        return None
    idp = identifier.strip()
    date_suffix = f"/{at_date}" if at_date and _DATE_RE.match(at_date) else ""
    # LEGIARTI (article de code ou de loi consolidée)
    if idp.startswith("LEGIARTI"):
        # Si on connait le parent LEGITEXT et qu'il est LEGITEXT (code), utiliser /codes/
        # sinon /loda/ pour les lois non codifiées (JORFTEXT*). Par défaut /codes/ (Légifrance redirige)
        if legitext and legitext.startswith("JORFTEXT"):
            return f"https://www.legifrance.gouv.fr/loda/article_lc/{idp}{date_suffix}"
        return f"https://www.legifrance.gouv.fr/codes/article_lc/{idp}{date_suffix}"
    if idp.startswith("LEGITEXT"):
        return f"https://www.legifrance.gouv.fr/codes/texte_lc/{idp}{date_suffix}"
    if idp.startswith("JORFTEXT"):
        return f"https://www.legifrance.gouv.fr/loda/id/{idp}{date_suffix}"
    if idp.startswith("JURITEXT"):
        return f"https://www.legifrance.gouv.fr/juri/id/{idp}"
    if idp.startswith("CONSTEXT"):
        return f"https://www.legifrance.gouv.fr/juri/id/{idp}"
    if idp.startswith("CETATEXT"):
        return f"https://www.legifrance.gouv.fr/ceta/id/{idp}"
    # CELEX (CJUE) : 6XXXXCJXXXX ou 6XXXXCC0XXX
    if re.match(r"^6\d{4}[A-Z]{2}\d{4}$", idp):
        return f"https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:{idp}"
    # ECLI
    if idp.upper().startswith("ECLI:"):
        return f"https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=ecli:{idp}"
    # HUDOC itemid (001-XXXXXX)
    if re.match(r"^\d{3}-\d+$", idp):
        return f"https://hudoc.echr.coe.int/fre?i={idp}"
    # ArianeWeb /Ariane_Web/AW_DCE/|XXXXXX : deeplinks existent
    if idp.startswith("/Ariane_Web/"):
        return f"https://www.conseil-etat.fr/arianeweb/#/view-document/{urllib.parse.quote(idp)}"
    return None
LEGITEXT_TO_CODE = {v: k for k, v in CODE_TO_LEGITEXT.items()}

# Supported fonds and their DB files / main search tables
FONDS: dict[str, dict] = {
    "legi": {
        "db": "legi.db",
        "fts": "legi_articles_fts",
        "decision_table": "legi_articles",
        "id_col": "legiarti",
    },
    "jade": {
        "db": "jade.db",
        "fts": "jade_fts",
        "decision_table": "jade_decisions",
        "id_col": "id",
    },
    "jorf": {
        "db": "jorf.db",
        "fts": "jorf_fts",
        "decision_table": "jorf_textes",
        "id_col": "jorftext",
    },
    "kali": {
        "db": "kali.db",
        "fts": "kali_fts",
        "decision_table": "kali_textes",
        "id_col": "id",
    },
    "cnil": {
        "db": "cnil.db",
        "fts": "cnil_fts",
        "decision_table": "cnil_deliberations",
        "id_col": "id",
    },
}

# ─── SQLITE CONNECTION POOL (thread-local, read-only) ────────────────

_tls = threading.local()


def _conn(fond: str) -> sqlite3.Connection:
    """Return a thread-local read-only SQLite connection for the given fond."""
    if fond not in FONDS:
        raise ValueError(f"unknown fond: {fond}")
    pool = getattr(_tls, "pool", None)
    if pool is None:
        pool = {}
        _tls.pool = pool
    conn = pool.get(fond)
    if conn is None:
        db_path = DB_DIR / FONDS[fond]["db"]
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        pool[fond] = conn
    return conn


# ─── LAW (article version at date) ───────────────────────────────────

def resolve_law_number(numero: str) -> dict | None:
    """Résout un numéro de loi/ordonnance/décret (ex: '68-1250', '79-587')
    vers son legitext/jorftext parent.

    Heuristique : cherche dans legi_articles le JORFTEXT qui apparaît le plus
    fréquemment pour les articles dont le texte contient 'n° NUMERO' ou
    'numéro NUMERO'. Retourne le plus probable + nombre d'articles + titre.
    """
    if not numero or not re.match(r"^\d{2,4}-\d+$", numero):
        return None
    c = _conn("legi")
    # Pattern 1: cherche le legitext le plus représenté parmi les articles
    # dont le titre_text contient le numéro (cas où DILA a bien parsé le titre)
    rows = c.execute(
        """
        SELECT legitext, COUNT(*) as nb,
               MAX(titre_text) as titre_sec,
               MIN(date_debut) as date_debut
        FROM legi_articles
        WHERE titre_text LIKE ? OR titre_text LIKE ?
        GROUP BY legitext
        ORDER BY nb DESC
        LIMIT 5
        """,
        (f"%n° {numero}%", f"%n°{numero}%"),
    ).fetchall()
    # Pattern 2 (fallback): cherche dans le texte des articles (cas lois
    # non codifiées où titre_text est vide). On prend le legitext qui a le
    # plus d'articles dont le texte n'est qu'un article 1er type "Loi ... du ...
    # N° X-Y". Plus approximatif mais dépanne.
    if not rows:
        rows = c.execute(
            """
            SELECT legitext, COUNT(*) as nb, '' as titre_sec,
                   MIN(date_debut) as date_debut
            FROM legi_articles
            WHERE num = '1' AND texte LIKE ?
            GROUP BY legitext
            ORDER BY nb DESC
            LIMIT 3
            """,
            (f"%loi n° {numero}%",),
        ).fetchall()
    if not rows:
        return None
    r = rows[0]
    legitext = r["legitext"]
    # Count total articles of this text
    total = c.execute(
        "SELECT COUNT(*) FROM legi_articles WHERE legitext = ?",
        (legitext,),
    ).fetchone()[0]
    return {
        "numero": numero,
        "legitext": legitext,
        "titre_section": r["titre_sec"],
        "date_debut": r["date_debut"],
        "articles_count": total,
        "source_url": _build_source_url(legitext),
    }


def law_at_date(code: str, num: str, target_date: str | None) -> dict | None:
    """Return the article version in force at `target_date`, or current if None.

    `code` peut être : un code court (CC, CP, LIL, LO58…), OU un LEGITEXT /
    JORFTEXT direct (ex: 'JORFTEXT000000878035' pour la loi 68-1250).
    """
    # Si c'est un identifiant Légifrance direct, on l'utilise tel quel
    if code.startswith("LEGITEXT") or code.startswith("JORFTEXT"):
        legitext = code
    else:
        legitext = CODE_TO_LEGITEXT.get(code)
        if not legitext:
            return None
    target = target_date or _date.today().isoformat()
    # Normalize num: drop spaces, keep structure
    num_clean = _normalize_num(num)
    c = _conn("legi")
    # Strategy 1: exact legitext match + num + date in range
    row = c.execute(
        """
        SELECT legiarti, num, titre_text, etat, date_debut, date_fin, texte, nota
        FROM legi_articles
        WHERE legitext = ? AND num = ?
          AND (date_debut IS NULL OR date_debut = '' OR date_debut <= ?)
          AND (date_fin IS NULL OR date_fin = '' OR date_fin >= ?)
        ORDER BY date_debut DESC
        LIMIT 1
        """,
        (legitext, num_clean, target, target),
    ).fetchone()
    if row:
        return _law_row_to_dict(row, code, legitext, at_date=target_date)
    # Strategy 2: if no match at date, return current version
    row = c.execute(
        """
        SELECT legiarti, num, titre_text, etat, date_debut, date_fin, texte, nota
        FROM legi_articles
        WHERE legitext = ? AND num = ? AND etat = 'VIGUEUR'
        ORDER BY date_debut DESC
        LIMIT 1
        """,
        (legitext, num_clean),
    ).fetchone()
    if row:
        d = _law_row_to_dict(row, code, legitext)
        d["note"] = f"Aucune version en vigueur à {target}. Version courante affichée."
        return d
    # Strategy 3: look for any version (abrogated, etc.)
    row = c.execute(
        """
        SELECT legiarti, num, titre_text, etat, date_debut, date_fin, texte, nota
        FROM legi_articles
        WHERE legitext = ? AND num = ?
        ORDER BY date_debut DESC
        LIMIT 1
        """,
        (legitext, num_clean),
    ).fetchone()
    if row:
        d = _law_row_to_dict(row, code, legitext)
        d["note"] = "Article non trouvé à la date demandée ; version la plus récente retournée."
        return d
    return None


def law_versions(code: str, num: str) -> list[dict]:
    """Return all historical versions of an article, ordered by date_debut asc.

    `code` accepte soit un code court (CC, LIL…), soit un LEGITEXT/JORFTEXT direct.
    """
    if code.startswith("LEGITEXT") or code.startswith("JORFTEXT"):
        legitext = code
    else:
        legitext = CODE_TO_LEGITEXT.get(code)
        if not legitext:
            return []
    num_clean = _normalize_num(num)
    c = _conn("legi")
    rows = c.execute(
        """
        SELECT legiarti, num, titre_text, etat, date_debut, date_fin, texte, nota
        FROM legi_articles
        WHERE legitext = ? AND num = ?
        ORDER BY date_debut ASC
        """,
        (legitext, num_clean),
    ).fetchall()
    return [_law_row_to_dict(r, code, legitext) for r in rows]


def law_batch(refs: list[dict], target_date: str | None) -> list[dict]:
    """Resolve multiple articles in one round-trip. Returns items with `found=False`
    for missing refs so the caller can keep track."""
    out = []
    for ref in refs:
        code = ref.get("code", "")
        num = ref.get("num", "")
        if not code or not num:
            out.append({"code": code, "num": num, "found": False, "error": "missing code or num"})
            continue
        d = law_at_date(code, num, target_date)
        if d:
            d["found"] = True
            d["code"] = code
            d["num"] = num
            out.append(d)
        else:
            out.append({"code": code, "num": num, "found": False})
    return out


def _law_row_to_dict(row: sqlite3.Row, code: str, legitext: str, at_date: str | None = None) -> dict:
    # Si on n'a pas de date explicite, on utilise la date_debut de la version
    # retournée pour que Légifrance affiche bien cette version-là (et pas la
    # version par défaut, qui peut être une autre).
    effective_date = at_date or (row["date_debut"] or None)
    return {
        "legiarti": row["legiarti"],
        "num": row["num"],
        "code": code,
        "legitext": legitext,
        "titre_section": row["titre_text"],
        "etat": row["etat"],
        "date_debut": row["date_debut"] or None,
        "date_fin": row["date_fin"] or None,
        "texte": row["texte"],
        "nota": row["nota"] or None,
        "source_url": _build_source_url(row["legiarti"], legitext=legitext, at_date=effective_date),
    }


def _normalize_num(num: str) -> str:
    """Normalise un numéro d'article pour le matching DB.

    LEGI stocke les numéros sans points ni espaces (ex: 'R772-8', pas
    'R. 772-8' ou 'R.772-8'). Les citations détectées dans les jugements
    arrivent souvent avec ponctuation libre. On enlève espaces + points
    pour matcher de manière stable.
    """
    return (num or "").strip().replace(" ", "").replace(".", "")


# ─── FTS5 SEARCH (by fond) ───────────────────────────────────────────

def _fts_query(q: str) -> str:
    """Sanitize user query for FTS5 MATCH clause.

    Points durs :
    - Les tokens composés (14-80854, L1152-1, 23-3, C-72/24, ECLI:…) sont
      interprétés par FTS5 comme `X NOT Y` (où `-` = NOT) → erreur SQL
      "no such column: Y". On les wrappe en phrase.
    - Les autres caractères spéciaux sont strippés.
    """
    if not q:
        return ""
    # 1. Protéger les phrases utilisateur "..."
    phrases: list[str] = []
    def _protect(m):
        phrases.append(m.group(0))
        return f"\x01{len(phrases)-1}\x01"
    q = re.sub(r'"[^"]*"', _protect, q)
    # 2. Wrapper les tokens composés en phrase pour neutraliser `-`, `/`, `:`
    def _quote_compound(m):
        # Remplace séparateurs par espaces et enveloppe en phrase
        return '"' + re.sub(r"[-/:]+", " ", m.group(0)) + '"'
    q = re.sub(r"\b\w+(?:[-/:]\w+)+\b", _quote_compound, q)
    # 3. Strip chars restants que FTS5 n'aime pas
    q = re.sub(r"[^\w\s\"*()]", " ", q, flags=re.UNICODE)
    # 4. Restaurer les phrases utilisateur
    for i, p in enumerate(phrases):
        q = q.replace(f"\x01{i}\x01", p)
    return q.strip()


def fts_search(fond: str, q: str, limit: int, offset: int, sort: str,
               date_min: str | None, date_max: str | None,
               filter_legitext: str | None = None) -> dict:
    if fond not in FONDS:
        raise ValueError(f"unknown fond: {fond}")
    q_clean = _fts_query(q)
    if not q_clean:
        return {"fond": fond, "total": 0, "results": []}
    c = _conn(fond)
    cfg = FONDS[fond]
    fts_table = cfg["fts"]
    main_table = cfg["decision_table"]
    id_col = cfg["id_col"]

    # Build the MATCH condition
    params: list = [q_clean]

    # Date field varies by fond
    date_col = {
        "legi": "date_debut",
        "jade": "date",
        "jorf": "date_publi",
        "kali": "date_publi",
        "cnil": "date",
    }[fond]

    where = [f"{fts_table} MATCH ?"]
    if date_min:
        where.append(f"m.{date_col} >= ?")
        params.append(date_min)
    if date_max:
        where.append(f"m.{date_col} <= ?")
        params.append(date_max)
    if filter_legitext and fond == "legi":
        where.append("m.legitext = ?")
        params.append(filter_legitext)

    # Sort: relevance (BM25) by default, chronological fallback
    order = "bm25(" + fts_table + ") ASC"
    if sort == "date_desc":
        order = f"m.{date_col} DESC"
    elif sort == "date_asc":
        order = f"m.{date_col} ASC"

    # Count
    sql_count = f"SELECT COUNT(*) FROM {fts_table} JOIN {main_table} m ON m.rowid = {fts_table}.rowid WHERE " + " AND ".join(where)
    total = c.execute(sql_count, params).fetchone()[0]

    # Columns to select per fond
    select_cols = {
        "legi": f"m.legiarti AS id, m.num, m.titre_text AS titre, m.legitext, m.etat, m.date_debut AS date, snippet({fts_table}, -1, '<em>', '</em>', '…', 28) AS extract",
        "jade": f"m.id, m.juridiction, m.numero, m.date, m.titre, snippet({fts_table}, -1, '<em>', '</em>', '…', 28) AS extract",
        "jorf": f"m.jorftext AS id, m.titre, m.nature, m.date_publi AS date, m.ministere, snippet({fts_table}, -1, '<em>', '</em>', '…', 28) AS extract",
        "kali": f"m.id, m.idcc, m.titre, m.nature, m.date_publi AS date, snippet({fts_table}, -1, '<em>', '</em>', '…', 28) AS extract",
        "cnil": f"m.id, m.numero, m.titre, m.date, m.formation, snippet({fts_table}, -1, '<em>', '</em>', '…', 28) AS extract",
    }[fond]

    # LEGI : dédup par legitext parent (évite 8 versions d'une annexe arrêté).
    # On over-fetche x3 puis on dédup en Python pour garder les meilleurs scores
    # par texte-parent distinct, dans l'ordre BM25.
    if fond == "legi":
        params_paged = list(params) + [limit * 5, offset]  # over-fetch
        sql = (f"SELECT {select_cols} FROM {fts_table} JOIN {main_table} m ON m.rowid = {fts_table}.rowid "
               f"WHERE " + " AND ".join(where) + f" ORDER BY {order} LIMIT ? OFFSET ?")
        all_rows = c.execute(sql, params_paged).fetchall()
        seen_legitexts: set[str] = set()
        deduped: list[dict] = []
        for row in all_rows:
            r = dict(row)
            lt = r.get("legitext") or ""
            if lt in seen_legitexts:
                continue
            seen_legitexts.add(lt)
            deduped.append(r)
            if len(deduped) >= limit:
                break
        return {
            "fond": fond,
            "total": total,
            "returned": len(deduped),
            "limit": limit,
            "offset": offset,
            "deduplicated_by": "legitext",
            "results": deduped,
        }

    params_paged = list(params) + [limit, offset]
    sql = (f"SELECT {select_cols} FROM {fts_table} JOIN {main_table} m ON m.rowid = {fts_table}.rowid "
           f"WHERE " + " AND ".join(where) + f" ORDER BY {order} LIMIT ? OFFSET ?")
    rows = c.execute(sql, params_paged).fetchall()
    return {
        "fond": fond,
        "total": total,
        "returned": len(rows),
        "limit": limit,
        "offset": offset,
        "results": [dict(r) for r in rows],
    }


def get_decision(fond: str, decision_id: str) -> dict | None:
    if fond not in FONDS:
        raise ValueError(f"unknown fond: {fond}")
    cfg = FONDS[fond]
    c = _conn(fond)
    row = c.execute(
        f"SELECT * FROM {cfg['decision_table']} WHERE {cfg['id_col']} = ? LIMIT 1",
        (decision_id,),
    ).fetchone()
    return dict(row) if row else None


# ─── HTTP HANDLER ────────────────────────────────────────────────────

class WarehouseHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args):
        # Minimal logging: method, path, status
        sys.stdout.write(f"[{self.log_date_time_string()}] {self.command} {self.path}\n")

    def _json(self, status: int, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        # /v1/health is open (no auth, for monitoring)
        if self.path.rstrip("/").endswith("/v1/health"):
            return True
        key = self.headers.get("X-Warehouse-Key", "")
        return bool(key) and hmac.compare_digest(key, WAREHOUSE_KEY)

    def do_GET(self):
        if not self._check_auth():
            return self._json(401, {"error": "invalid or missing X-Warehouse-Key"})
        try:
            self._route_get()
        except Exception as e:
            self._json(500, {"error": str(e)})

    def do_POST(self):
        if not self._check_auth():
            return self._json(401, {"error": "invalid or missing X-Warehouse-Key"})
        try:
            self._route_post()
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _route_get(self):
        u = urlparse(self.path)
        path = u.path.rstrip("/")
        q = parse_qs(u.query)

        if path == "/v1/health":
            return self._json(200, {"status": "ok", "fonds": list(FONDS.keys()), "codes": list(CODE_TO_LEGITEXT.keys())})

        if path == "/v1/url":
            # Build source URL from an arbitrary identifier
            ident = _q(q, "id")
            legitext = _q(q, "legitext") or ""
            at_date = _q(q, "date") or None
            if not ident:
                return self._json(400, {"error": "id required"})
            url = _build_source_url(ident, legitext=legitext, at_date=at_date)
            if not url:
                return self._json(404, {"error": f"identifier type not recognized: {ident!r}"})
            return self._json(200, {"id": ident, "source_url": url})

        if path == "/v1/law":
            code = _q(q, "code")
            num = _q(q, "num")
            date = _q(q, "date")
            if not code or not num:
                return self._json(400, {"error": "code and num are required"})
            d = law_at_date(code, num, date)
            if not d:
                return self._json(404, {"error": f"no article found for {code} {num}"})
            return self._json(200, d)

        if path == "/v1/law/versions":
            code = _q(q, "code")
            num = _q(q, "num")
            if not code or not num:
                return self._json(400, {"error": "code and num are required"})
            versions = law_versions(code, num)
            return self._json(200, {"code": code, "num": num, "versions": versions})

        if path == "/v1/law/resolve":
            numero = _q(q, "numero")
            if not numero:
                return self._json(400, {"error": "numero required (ex: 68-1250)"})
            d = resolve_law_number(numero)
            if not d:
                return self._json(404, {"error": f"pas de loi/décret trouvé avec le numéro {numero!r}"})
            return self._json(200, d)

        # /v1/search/{fond}
        m = re.match(r"^/v1/search/(\w+)$", path)
        if m:
            fond = m.group(1)
            query = _q(q, "q")
            limit = min(int(_q(q, "limit") or 20), 100)
            offset = int(_q(q, "offset") or 0)
            sort = _q(q, "sort") or "relevance"
            date_min = _q(q, "date_min")
            date_max = _q(q, "date_max")
            filter_code = _q(q, "code")
            filter_legitext = CODE_TO_LEGITEXT.get(filter_code) if filter_code else None
            try:
                result = fts_search(fond, query, limit, offset, sort, date_min, date_max, filter_legitext)
                return self._json(200, result)
            except ValueError as e:
                return self._json(400, {"error": str(e)})

        # /v1/decision/{fond}/{id}
        m = re.match(r"^/v1/decision/(\w+)/(.+)$", path)
        if m:
            fond, did = m.group(1), m.group(2)
            d = get_decision(fond, did)
            if not d:
                return self._json(404, {"error": f"decision {did!r} not found in {fond}"})
            return self._json(200, d)

        # /v1/lookup/{fond}?numero=X&juridiction=Y
        # Exact lookup par numero + filtre juridiction optionnel (évite FTS5 noyé)
        m = re.match(r"^/v1/lookup/(\w+)$", path)
        if m:
            fond = m.group(1)
            if fond not in FONDS:
                return self._json(400, {"error": f"unknown fond: {fond}"})
            numero = _q(q, "numero")
            juridiction = _q(q, "juridiction")
            if not numero:
                return self._json(400, {"error": "numero required"})
            cfg = FONDS[fond]
            c = _conn(fond)
            sql = f"SELECT * FROM {cfg['decision_table']} WHERE numero = ?"
            params = [numero]
            if juridiction:
                # Match juridiction avec tolérance sur les accents (Conseil d'Etat vs d'État)
                sql += " AND (juridiction = ? OR juridiction LIKE ?)"
                params.extend([juridiction, f"%{juridiction.replace('État', 'Etat')}%"])
            sql += " LIMIT 5"
            rows = c.execute(sql, params).fetchall()
            if not rows:
                return self._json(404, {"error": f"no match for numero {numero!r} in {fond}"})
            return self._json(200, {"count": len(rows), "results": [dict(r) for r in rows]})

        # /v1/count/{fond} → total rows. Sert au sitemap-index pour calculer
        # combien de sub-sitemaps annoncer.
        m = re.match(r"^/v1/count/(\w+)$", path)
        if m:
            fond = m.group(1)
            if fond not in FONDS:
                return self._json(400, {"error": f"unknown fond: {fond}"})
            cfg = FONDS[fond]
            c = _conn(fond)
            try:
                # Pour LEGI on ne compte que les articles en vigueur (les seuls
                # qu'on met dans le sitemap, les versions historiques étant
                # accessibles via lien interne depuis leur article courant).
                if fond == "legi":
                    total = c.execute(
                        f"SELECT COUNT(*) FROM {cfg['decision_table']} WHERE etat = 'VIGUEUR'"
                    ).fetchone()[0]
                else:
                    total = c.execute(f"SELECT COUNT(*) FROM {cfg['decision_table']}").fetchone()[0]
            except sqlite3.Error as e:
                return self._json(500, {"error": f"count failed: {e}"})
            return self._json(200, {"fond": fond, "total": total})

        # /v1/enumerate/{fond}?offset=&limit= → liste paginée d'IDs pour
        # construire les sub-sitemaps Google. Renvoie le minimum nécessaire
        # à la génération du <url><loc>...</loc><lastmod>...</lastmod></url>.
        m = re.match(r"^/v1/enumerate/(\w+)$", path)
        if m:
            fond = m.group(1)
            if fond not in FONDS:
                return self._json(400, {"error": f"unknown fond: {fond}"})
            try:
                offset = max(0, int(_q(q, "offset") or "0"))
                limit = min(50000, max(1, int(_q(q, "limit") or "1000")))
            except ValueError:
                return self._json(400, {"error": "offset/limit must be int"})
            cfg = FONDS[fond]
            c = _conn(fond)
            try:
                if fond == "jade":
                    sql = "SELECT id, date FROM jade_decisions ORDER BY date DESC LIMIT ? OFFSET ?"
                    rows = c.execute(sql, (limit, offset)).fetchall()
                    out = [{"id": r["id"], "date": r["date"]} for r in rows]
                elif fond == "legi":
                    # On ne sitemap que les articles en vigueur, triés par
                    # legiarti pour garantir un ordre stable + cohérent avec
                    # l'index idx_legi_etat_legiarti. Renvoie aussi (legitext,
                    # num) pour pouvoir construire l'URL /loi/{code}/{num}.
                    sql = ("SELECT legiarti, legitext, num, date_debut "
                           "FROM legi_articles WHERE etat = 'VIGUEUR' "
                           "ORDER BY legiarti LIMIT ? OFFSET ?")
                    rows = c.execute(sql, (limit, offset)).fetchall()
                    out = [{
                        "id": r["legiarti"], "legitext": r["legitext"],
                        "num": r["num"], "date": r["date_debut"],
                    } for r in rows]
                else:
                    # Fallback générique : on suppose colonnes id + date
                    sql = (f"SELECT {cfg['id_col']} AS id, date "
                           f"FROM {cfg['decision_table']} "
                           f"ORDER BY date DESC LIMIT ? OFFSET ?")
                    rows = c.execute(sql, (limit, offset)).fetchall()
                    out = [{"id": r["id"], "date": r["date"]} for r in rows]
            except sqlite3.Error as e:
                return self._json(500, {"error": f"enumerate failed: {e}"})
            return self._json(200, {"fond": fond, "offset": offset, "limit": limit,
                                     "count": len(out), "results": out})

        return self._json(404, {"error": f"endpoint not found: {path}"})

    def _route_post(self):
        u = urlparse(self.path)
        path = u.path.rstrip("/")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError) as e:
            return self._json(400, {"error": f"invalid JSON body: {e}"})

        if path == "/v1/law/batch":
            refs = body.get("refs", [])
            target_date = body.get("date")
            if not isinstance(refs, list):
                return self._json(400, {"error": "refs must be a list of {code, num}"})
            if len(refs) > 200:
                return self._json(400, {"error": "max 200 refs per batch"})
            items = law_batch(refs, target_date)
            return self._json(200, {"date": target_date, "count": len(items), "items": items})

        return self._json(404, {"error": f"endpoint not found: {path}"})


def _q(qs: dict, name: str) -> str | None:
    v = qs.get(name, [])
    return v[0] if v else None


# ─── STARTUP : créer les index nécessaires si absents ─────────────────

# Indexes critiques pour la perf des sitemaps (`/v1/enumerate/{fond}`).
# Sans ces indexes, ORDER BY ... LIMIT 50000 = full scan = timeout
# Cloudflare (60s). Avec : ~1-2s.
_BOOTSTRAP_INDEXES = {
    "jade": [
        ("idx_jade_date", "CREATE INDEX IF NOT EXISTS idx_jade_date ON jade_decisions(date DESC)"),
    ],
    "legi": [
        # Couvre la query SELECT WHERE etat='VIGUEUR' ORDER BY legiarti
        ("idx_legi_etat_legiarti", "CREATE INDEX IF NOT EXISTS idx_legi_etat_legiarti ON legi_articles(etat, legiarti)"),
    ],
}


def _ensure_indexes():
    """Crée les indexes manquants au démarrage (read-write éphémère)."""
    for fond, idxs in _BOOTSTRAP_INDEXES.items():
        if fond not in FONDS:
            continue
        db_path = DB_DIR / FONDS[fond]["db"]
        if not db_path.exists():
            print(f"[warehouse] skip indexes {fond}: {db_path} absent")
            continue
        try:
            with sqlite3.connect(str(db_path), timeout=120.0) as c:
                for name, sql in idxs:
                    t0 = time.time()
                    c.execute(sql)
                    elapsed = time.time() - t0
                    if elapsed > 0.5:
                        print(f"[warehouse] created {name} on {fond} in {elapsed:.1f}s")
        except sqlite3.Error as e:
            print(f"[warehouse] index bootstrap {fond} failed: {e}")


# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    _ensure_indexes()
    server = ThreadingHTTPServer(BIND, WarehouseHandler)
    print(f"[warehouse] bind={BIND[0]}:{BIND[1]} db_dir={DB_DIR} fonds={list(FONDS.keys())} codes={len(CODE_TO_LEGITEXT)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[warehouse] stopped")


if __name__ == "__main__":
    main()
