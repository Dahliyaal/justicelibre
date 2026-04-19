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
from datetime import date as _date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

# ─── CODE → LEGITEXT MAPPING (22 codes supportés) ────────────────────

CODE_TO_LEGITEXT: dict[str, str] = {
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
}
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

def law_at_date(code: str, num: str, target_date: str | None) -> dict | None:
    """Return the article version in force at `target_date`, or current if None."""
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
        return _law_row_to_dict(row, code, legitext)
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
    """Return all historical versions of an article, ordered by date_debut asc."""
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


def _law_row_to_dict(row: sqlite3.Row, code: str, legitext: str) -> dict:
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
    }


def _normalize_num(num: str) -> str:
    return (num or "").strip().replace(" ", "")


# ─── FTS5 SEARCH (by fond) ───────────────────────────────────────────

def _fts_query(q: str) -> str:
    """Sanitize user query for FTS5 MATCH clause."""
    if not q:
        return ""
    # Strip characters FTS5 doesn't like outside quoted phrases
    # Simple strategy: keep alphanum + quotes + operators, drop the rest
    return re.sub(r"[^\w\s\"*():\-]", " ", q, flags=re.UNICODE).strip()


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


# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    server = ThreadingHTTPServer(BIND, WarehouseHandler)
    print(f"[warehouse] bind={BIND[0]}:{BIND[1]} db_dir={DB_DIR} fonds={list(FONDS.keys())} codes={len(CODE_TO_LEGITEXT)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[warehouse] stopped")


if __name__ == "__main__":
    main()
