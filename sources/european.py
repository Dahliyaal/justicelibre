"""Query local SQLite FTS5 for CJUE (EUR-Lex) and CEDH (HUDOC) decisions.

Populated by scrape_cjue.py and scrape_cedh.py. Zero auth, zero network.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("/opt/justicelibre/dila/judiciaire.db")


def _conn():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def search_cedh(query: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Search CEDH (Cour EDH) via local HUDOC index."""
    if not query.strip():
        raise ValueError("query must be non-empty")
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT d.itemid, d.docname, d.ecli, d.date, d.doctype,
                      d.article, d.conclusion, d.importance, d.respondent,
                      snippet(cedh_fts, -1, '<em>', '</em>', '…', 28) AS snip
               FROM cedh_fts f JOIN cedh_decisions d ON d.rowid = f.rowid
               WHERE cedh_fts MATCH ? ORDER BY d.date DESC LIMIT ? OFFSET ?""",
            (query.strip(), int(limit), int(offset)),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM cedh_fts WHERE cedh_fts MATCH ?", (query.strip(),)
        ).fetchone()[0]
        return {
            "total": total,
            "returned": len(rows),
            "source": "HUDOC (Cour européenne des droits de l'homme)",
            "decisions": [
                {
                    "id": r["itemid"],
                    "docname": r["docname"],
                    "ecli": r["ecli"],
                    "date": r["date"],
                    "doctype": r["doctype"],
                    "article": r["article"],
                    "conclusion": r["conclusion"],
                    "importance": r["importance"],
                    "respondent": r["respondent"],
                    "snippet": r["snip"] or "",
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


def get_cedh(itemid: str) -> dict[str, Any] | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM cedh_decisions WHERE itemid=?", (itemid,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["itemid"],
            "docname": row["docname"],
            "ecli": row["ecli"],
            "date": row["date"],
            "doctype": row["doctype"],
            "article": row["article"],
            "conclusion": row["conclusion"],
            "importance": row["importance"],
            "respondent": row["respondent"],
            "full_text": row["text"],
            "source": "HUDOC (Cour européenne des droits de l'homme)",
        }
    finally:
        conn.close()


def search_cjue(query: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Search CJUE via local EUR-Lex index."""
    if not query.strip():
        raise ValueError("query must be non-empty")
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT d.celex, d.ecli, d.date, d.type, d.title,
                      snippet(cjue_fts, -1, '<em>', '</em>', '…', 28) AS snip
               FROM cjue_fts f JOIN cjue_decisions d ON d.rowid = f.rowid
               WHERE cjue_fts MATCH ? ORDER BY d.date DESC LIMIT ? OFFSET ?""",
            (query.strip(), int(limit), int(offset)),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM cjue_fts WHERE cjue_fts MATCH ?", (query.strip(),)
        ).fetchone()[0]
        return {
            "total": total,
            "returned": len(rows),
            "source": "EUR-Lex (Cour de justice de l'Union européenne)",
            "decisions": [
                {
                    "id": r["celex"],
                    "celex": r["celex"],
                    "ecli": r["ecli"],
                    "date": r["date"],
                    "type": r["type"],
                    "title": r["title"],
                    "snippet": r["snip"] or "",
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


def get_cjue(celex: str) -> dict[str, Any] | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM cjue_decisions WHERE celex=?", (celex,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["celex"],
            "celex": row["celex"],
            "ecli": row["ecli"],
            "date": row["date"],
            "type": row["type"],
            "title": row["title"],
            "full_text": row["text"],
            "source": "EUR-Lex (Cour de justice de l'Union européenne)",
        }
    finally:
        conn.close()
