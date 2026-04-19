"""Query the local DILA SQLite FTS5 index for judicial decisions.

Zero auth, zero API, zero network latency. The database is populated
weekly from the DILA bulk XML archives (echanges.dila.gouv.fr/OPENDATA/).

Covers: Cour de cassation (~144k decisions) + cours d'appel (~73k decisions).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("/opt/justicelibre/dila/judiciaire.db")


def _sanitize_fts5(q: str) -> str:
    """Nettoie une query utilisateur pour FTS5 MATCH.

    FTS5 plante en SyntaxError sur certains caractères spéciaux mal placés
    (`:`, `\\`, points en début de mot…). On strip ce qui n'est pas dans
    le set sûr pour préserver les opérateurs FTS5 valides (AND, OR, NOT,
    "phrase", mot*, parenthèses) sans permettre d'injection sémantique.
    """
    if not q:
        return ""
    # Caractères autorisés : alphanum, espaces, ", *, (, ), -, accents (\w + unicode)
    return re.sub(r"[^\w\s\"*()\-]", " ", q, flags=re.UNICODE).strip()

JURIDICTIONS = {
    "cassation": "Cour de cassation",
    "appel": "Cour d'appel",
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def search(
    query: str,
    juridiction: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must be non-empty")

    conn = _get_conn()
    try:
        # Build FTS5 query — sanitize to avoid SQLite SyntaxError on user input
        fts_query = _sanitize_fts5(query)
        if not fts_query:
            return {"total": 0, "decisions": []}

        # snippet() : extrait autour du match, ~28 tokens, highlights <em>…</em>
        SNIPPET_SQL = "snippet(decisions_fts, -1, '<em>', '</em>', '…', 28)"
        if juridiction and juridiction in JURIDICTIONS:
            juri_name = JURIDICTIONS[juridiction]
            rows = conn.execute(
                f"""SELECT d.id, d.titre, d.date, d.juridiction, d.solution,
                          d.numero, d.formation, d.ecli, d.nature,
                          {SNIPPET_SQL} AS snip
                   FROM decisions_fts f
                   JOIN decisions d ON d.rowid = f.rowid
                   WHERE decisions_fts MATCH ?
                   AND d.juridiction LIKE ?
                   ORDER BY d.date DESC
                   LIMIT ? OFFSET ?""",
                (fts_query, f"%{juri_name}%", int(limit), int(offset)),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT d.id, d.titre, d.date, d.juridiction, d.solution,
                          d.numero, d.formation, d.ecli, d.nature,
                          {SNIPPET_SQL} AS snip
                   FROM decisions_fts f
                   JOIN decisions d ON d.rowid = f.rowid
                   WHERE decisions_fts MATCH ?
                   ORDER BY d.date DESC
                   LIMIT ? OFFSET ?""",
                (fts_query, int(limit), int(offset)),
            ).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) FROM decisions_fts WHERE decisions_fts MATCH ?",
            (fts_query,),
        ).fetchone()[0]

        decisions = [
            {
                "id": r["id"],
                "titre": r["titre"],
                "date": r["date"],
                "juridiction": r["juridiction"],
                "solution": r["solution"],
                "numero": r["numero"],
                "formation": r["formation"],
                "ecli": r["ecli"],
                "nature": r["nature"],
                "snippet": r["snip"] or "",
            }
            for r in rows
        ]

        return {
            "total": total,
            "returned": len(decisions),
            "source": "DILA (archives publiques, sans authentification)",
            "decisions": decisions,
        }
    finally:
        conn.close()


def lookup_by_field(field: str, value: str, limit: int = 5) -> list[dict[str, Any]]:
    """Lookup direct par colonne indexée (numero, ecli) sans FTS5.

    Permet de retrouver une décision quand le champ cherché n'est pas
    dans le full-text (typiquement ECLI qui n'est pas dans le trigger FTS5).

    Args:
        field: nom de colonne ("numero", "ecli", "id")
        value: valeur exacte à matcher
        limit: cap résultats (défaut 5)
    """
    if field not in {"numero", "ecli", "id"}:
        raise ValueError(f"field {field!r} non autorisé pour lookup_by_field")
    conn = _get_conn()
    try:
        rows = conn.execute(
            f"""SELECT id, titre, date, juridiction, solution,
                       numero, formation, ecli, nature
                FROM decisions
                WHERE {field} = ?
                LIMIT ?""",
            (value, int(limit)),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "titre": r["titre"],
                "date": r["date"],
                "juridiction": r["juridiction"],
                "solution": r["solution"],
                "numero": r["numero"],
                "formation": r["formation"],
                "ecli": r["ecli"],
                "nature": r["nature"],
                "snippet": "",
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_decision(decision_id: str) -> dict[str, Any] | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "titre": row["titre"],
            "date": row["date"],
            "juridiction": row["juridiction"],
            "solution": row["solution"],
            "numero": row["numero"],
            "formation": row["formation"],
            "ecli": row["ecli"],
            "nature": row["nature"],
            "president": row["president"],
            "avocats": row["avocats"],
            "full_text": row["text"],
            "source": "DILA (archives publiques, sans authentification)",
        }
    finally:
        conn.close()


def stats() -> dict[str, Any]:
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        by_juri = conn.execute(
            "SELECT juridiction, COUNT(*) as n FROM decisions GROUP BY juridiction ORDER BY n DESC"
        ).fetchall()
        return {
            "total_decisions": total,
            "par_juridiction": {r[0]: r[1] for r in by_juri},
        }
    finally:
        conn.close()
