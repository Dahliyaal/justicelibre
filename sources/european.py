"""Query local SQLite FTS5 for CJUE (EUR-Lex) and CEDH (HUDOC) decisions.

Populated by scrape_cjue.py and scrape_cedh.py. Zero auth, zero network.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("/opt/justicelibre/dila/judiciaire.db")

# Sanitizer + filet FTS5 partagés avec dila.py : FTS5 lève SyntaxError sur
# certains caractères spéciaux (`:`, `\`, apostrophes…) — même moteur,
# mêmes règles.
from .dila import _fts_syntax_error_result, _sanitize_fts5

def _empty_query_result() -> dict[str, Any]:
    """Retour structuré quand la query est vide (avant ou après nettoyage FTS5) :
    plus actionnable pour un agent qu'une exception opaque. Fonction (et non
    constante) pour retourner une liste fraîche à chaque appel."""
    return {
        "total": 0,
        "returned": 0,
        "decisions": [],
        "note": "Query vide après nettoyage FTS5 (caractères spéciaux retirés). "
                "Reformuler en mots-clés simples.",
    }


def _conn():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def search_cedh(query: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Search CEDH (Cour EDH) via local HUDOC index. limit clampé à [1, 50]."""
    if not query.strip():
        return _empty_query_result()
    # Nettoie les caractères qui font planter FTS5 (préserve ", *, (), - et
    # les opérateurs AND/OR/NOT — les queries construites par search_par_article
    # passent intactes).
    query = _sanitize_fts5(query)
    if not query:
        return _empty_query_result()
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    conn = _conn()
    try:
        # WHERE : exclut les docs sans texte exploitable (notes 002-* vides chez nous).
        # ORDER BY :
        # 1) Préférer arrêts judiciaires complets (HFJUD, HEJUD) aux notes résumées (CLINF).
        # 2) Puis BM25 rank (pertinence query).
        # 3) Puis length(text) DESC (entre arrêts du même rank, le plus complet d'abord).
        try:
            rows = conn.execute(
                """SELECT d.itemid, d.docname, d.ecli, d.date, d.doctype,
                          d.article, d.conclusion, d.importance, d.respondent,
                          snippet(cedh_fts, -1, '<em>', '</em>', '…', 28) AS snip
                   FROM cedh_fts f JOIN cedh_decisions d ON d.rowid = f.rowid
                   WHERE cedh_fts MATCH ?
                     AND length(COALESCE(d.text, '')) > 200
                   ORDER BY
                     CASE WHEN d.doctype IN ('HFJUD', 'HEJUD') THEN 0 ELSE 1 END,
                     rank,
                     COALESCE(length(d.text), 0) DESC
                   LIMIT ? OFFSET ?""",
                (query.strip(), int(limit), int(offset)),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM cedh_fts WHERE cedh_fts MATCH ?", (query.strip(),)
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            return _fts_syntax_error_result(e)
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
    """Search CJUE via local EUR-Lex index. limit clampé à [1, 50].

    Si la query matche un pattern n° d'affaire CJUE (`C-395/21`, `T-260/22`...),
    on boost l'arrêt dont c'est exactement le numéro pour qu'il remonte avant
    tous ceux qui le citent. Sinon BM25 standard."""
    if not query.strip():
        return _empty_query_result()
    import re as _re
    # Détecte un n° d'affaire dans la query (peut être seul ou inclus dans phrase).
    # IMPORTANT : détection sur la query BRUTE, car _sanitize_fts5 retire `/` et `.`
    # dont ce pattern a besoin.
    m = _re.search(r"\b([CTF])[-\s.]*(\d{1,4})[/\-\s]+(\d{2,4})\b", query, _re.IGNORECASE)
    affaire_exact = None
    if m:
        letter, num, year = m.group(1).upper(), int(m.group(2)), m.group(3)
        # Tronque l'année à 2 chiffres si donnée en 4
        if len(year) == 4:
            year = year[2:]
        affaire_exact = f"{letter}-{num}/{year}"
    # Nettoie les caractères qui font planter FTS5 (après la détection ci-dessus).
    query = _sanitize_fts5(query)
    if not query:
        return _empty_query_result()
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    conn = _conn()
    try:
        try:
            if affaire_exact:
                # Boost massif : l'arrêt avec ce affaire_num exact passe en premier,
                # puis BM25 sur les arrêts qui le citent.
                rows = conn.execute(
                    """SELECT d.celex, d.ecli, d.date, d.type, d.title,
                              snippet(cjue_fts, -1, '<em>', '</em>', '…', 28) AS snip
                       FROM cjue_fts f JOIN cjue_decisions d ON d.rowid = f.rowid
                       WHERE cjue_fts MATCH ?
                       ORDER BY (CASE WHEN d.affaire_num = ? THEN 0 ELSE 1 END), rank
                       LIMIT ? OFFSET ?""",
                    (query.strip(), affaire_exact, int(limit), int(offset)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT d.celex, d.ecli, d.date, d.type, d.title,
                              snippet(cjue_fts, -1, '<em>', '</em>', '…', 28) AS snip
                       FROM cjue_fts f JOIN cjue_decisions d ON d.rowid = f.rowid
                       WHERE cjue_fts MATCH ? ORDER BY rank LIMIT ? OFFSET ?""",
                    (query.strip(), int(limit), int(offset)),
                ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM cjue_fts WHERE cjue_fts MATCH ?", (query.strip(),)
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            return _fts_syntax_error_result(e)
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
