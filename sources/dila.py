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
CONSTIT_DB = Path("/opt/justicelibre/dila/constit.db")


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
    q = re.sub(r"[^\w\s\"*()\-]", " ", q, flags=re.UNICODE)
    # Guillemets non appariés : FTS5 lève SyntaxError sur une phrase non
    # fermée — on retire alors tous les guillemets plutôt que de deviner
    # où la phrase devait s'arrêter.
    if q.count('"') % 2:
        q = q.replace('"', " ")
    # Parenthèses : FTS5 ne les accepte que dans des groupes booléens
    # explicites (`(a OR b) AND c`) — un simple `mot (précision)` est une
    # SyntaxError. On ne les conserve donc que si la query utilise des
    # opérateurs booléens ET qu'elles sont équilibrées.
    if not re.search(r"\b(AND|OR|NOT)\b", q) or q.count("(") != q.count(")"):
        q = q.replace("(", " ").replace(")", " ")
    # Hors phrase quotée, FTS5 parse `a-b` comme filtre de colonne et lève
    # SyntaxError ("79-105", "garde-à-vue"). On quote donc les tokens à
    # tiret, on retire les tirets isolés et les * non collés à un mot.
    parts = q.split('"')
    for i in range(0, len(parts), 2):  # segments hors guillemets uniquement
        seg = re.sub(
            r"(\w+(?:-\w+)+)(\*?)",
            lambda m: f'"{m.group(1)}"{m.group(2)}',
            parts[i], flags=re.UNICODE,
        )
        seg = re.sub(r"(?<!\w)-|-(?!\w)", " ", seg)
        seg = re.sub(r'(?<![\w"])\*', " ", seg)
        parts[i] = seg
    out = '"'.join(parts).strip()
    # Opérateur booléen orphelin en tête ou en queue ("harcèlement AND") :
    # SyntaxError FTS5 — on le retire.
    return re.sub(
        r"^(?:\s*(?:AND|OR|NOT)\b)+|(?:\b(?:AND|OR|NOT)\s*)+$", " ", out
    ).strip()

def _fts_syntax_error_result(e: Exception) -> dict[str, Any]:
    """Filet de sécurité : malgré _sanitize_fts5, FTS5 peut encore rejeter
    une combinaison d'opérateurs (parenthèses déséquilibrées, NOT en tête…).
    Retour 0-résultat actionnable plutôt qu'une exception opaque au modèle."""
    return {
        "total": 0,
        "returned": 0,
        "decisions": [],
        "note": f"Syntaxe de recherche invalide pour FTS5 ({e}). Reformuler "
                "en mots-clés simples, sans opérateurs ni ponctuation.",
    }


JURIDICTIONS = {
    "cassation": "Cour de cassation",
    "appel": "Cour d'appel",
    "constit": "Conseil constitutionnel",
}

# Natures des décisions du Conseil constitutionnel :
# QPC = Question Prioritaire de Constitutionnalité (contrôle a posteriori)
# DC  = Décision sur loi ordinaire / organique (contrôle a priori)
# L   = Lois (divers, délégalisation)
# SEN = Sénat (élections sénatoriales, inéligibilités)
# AN  = Assemblée nationale (élections législatives)
# PDR = Élection Président de la République
# ORGA= Organisation (règlement intérieur, composition)
# REF = Référendum
# ELEC= Autres élections
# I   = Incompétence
CC_NATURES = {"QPC", "DC", "L", "SEN", "AN", "PDR", "ORGA", "REF", "ELEC", "I"}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_rg(rg: str) -> str:
    """21/05835 → '21/05835', '21-05835' ou '2105835' acceptés en entrée.
    Retourne format canonique '21/05835'."""
    rg = rg.strip()
    m = re.match(r"^(\d{2,4})[/\-\s]?(\d{4,7})$", rg)
    if not m:
        return rg
    return f"{m.group(1)}/{m.group(2)}"


def search(
    query: str = "",
    juridiction: str | None = None,
    numero_rg: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    # Lookup direct par numero_rg si fourni : court-circuite FTS
    if numero_rg:
        canonical = _normalize_rg(numero_rg)
        # Match toutes les variantes via numero_rg_norm qui contient "21/05835 21-05835 2105835"
        # ET fallback sur numero (au cas où)
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT id, titre, date, juridiction, solution, numero,
                          formation, ecli, nature
                   FROM decisions
                   WHERE numero_rg_norm LIKE ? OR numero = ?
                   ORDER BY date DESC LIMIT ?""",
                (f"%{canonical}%", canonical, int(limit))
            ).fetchall()
            total = len(rows)
            return {
                "total": total,
                "returned": total,
                "source": "DILA (lookup par n° RG)",
                "decisions": [
                    {
                        "id": r["id"], "titre": r["titre"], "date": r["date"],
                        "juridiction": r["juridiction"], "solution": r["solution"],
                        "numero": r["numero"], "formation": r["formation"],
                        "ecli": r["ecli"], "nature": r["nature"], "snippet": "",
                    }
                    for r in rows
                ],
                "note": (
                    "Lookup direct par n° RG (variantes 21/05835, 21-05835, 2105835). "
                    "Si 0 résultat : l'arrêt n'est pas dans le bulk DILA libre "
                    "(couverture partielle des CA). Tenter via PISTE (search_judiciaire) "
                    "ou Légifrance directement." if total == 0 else None
                ),
            }
        finally:
            conn.close()

    if not query or not query.strip():
        raise ValueError("query ou numero_rg doit être fourni")

    conn = _get_conn()
    try:
        # Détection pattern Constit "YYYY-NNN DC|QPC|L|..." : on extrait la nature
        # comme filtre SQL séparé (la colonne `nature` n'est pas dans l'index FTS5).
        # Accepte les formes possibles :
        #   - brute : 2008-562 DC
        #   - guillemets englobants : "2008-562 DC"
        #   - normalisée par query_intent : "2008 562" DC
        #   - mixte : "2008 562 DC" / 2008 562 DC
        cc_nature_filter = None
        # Strip les guillemets englobants si présents (l'utilisateur protège tout)
        cleaned = query.strip()
        if cleaned.startswith('"') and cleaned.endswith('"') and cleaned.count('"') == 2:
            cleaned = cleaned[1:-1].strip()
        cc_match = re.match(
            r'^\s*"?(\d{4})[\s-]+(\d{1,4})"?\s+(QPC|DC|L|SEN|AN|PDR|ORGA|REF|ELEC|I)\s*$',
            cleaned, re.IGNORECASE,
        )
        if cc_match:
            # Reconstruit la query FTS comme phrase exacte du numéro
            query = f'"{cc_match.group(1)} {cc_match.group(2)}"'
            cc_nature_filter = cc_match.group(3).upper()
        # Build FTS5 query : on délègue au normalizer central (query_intent)
        # qui wrap les tokens à tirets ("2008-562" → "2008 562" en phrase)
        # car FTS5 par défaut interprète "-" comme NOT (exclusion).
        try:
            from query_intent import normalize_fts_query
            fts_query = normalize_fts_query(query, expand=False)
        except Exception:
            fts_query = query
        # normalize_fts_query quote les tokens composés mais ne retire PAS les
        # caractères qui font planter FTS5 en SyntaxError (`:`, `;`, apostrophes,
        # points isolés…) — on passe donc systématiquement par _sanitize_fts5
        # avant le MATCH, y compris sur le chemin normal.
        fts_query = _sanitize_fts5(fts_query)
        if not fts_query:
            return {
                "total": 0,
                "returned": 0,
                "decisions": [],
                "note": "Query vide après nettoyage FTS5 (caractères spéciaux "
                        "retirés). Reformuler en mots-clés simples.",
            }

        # snippet() : extrait autour du match, ~28 tokens, highlights <em>…</em>
        SNIPPET_SQL = "snippet(decisions_fts, -1, '<em>', '</em>', '…', 28)"
        where = ["decisions_fts MATCH ?"]
        params: list = [fts_query]
        if juridiction and juridiction in JURIDICTIONS:
            where.append("d.juridiction LIKE ?")
            params.append(f"%{JURIDICTIONS[juridiction]}%")
        if date_min:
            where.append("d.date >= ?")
            params.append(date_min)
        if date_max:
            where.append("d.date <= ?")
            params.append(date_max)
        if cc_nature_filter:
            where.append("d.nature = ?")
            params.append(cc_nature_filter)
        where_sql = " AND ".join(where)

        # ORDER BY rank (BM25) quand on a une query — sinon date DESC
        # (rank est négatif, ASC = best score first)
        try:
            rows = conn.execute(
                f"""SELECT d.id, d.titre, d.date, d.juridiction, d.solution,
                           d.numero, d.formation, d.ecli, d.nature,
                           {SNIPPET_SQL} AS snip
                    FROM decisions_fts f
                    JOIN decisions d ON d.rowid = f.rowid
                    WHERE {where_sql}
                    ORDER BY rank
                    LIMIT ? OFFSET ?""",
                params + [int(limit), int(offset)],
            ).fetchall()

            total = conn.execute(
                f"SELECT COUNT(*) FROM decisions_fts f JOIN decisions d ON d.rowid = f.rowid WHERE {where_sql}",
                params,
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            return _fts_syntax_error_result(e)

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


def search_cc(
    query: str,
    nature: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche dédiée au Conseil constitutionnel (7 112 décisions).

    Wrapper au-dessus de search() qui force juridiction='Conseil constitutionnel'
    et permet le filtrage par nature (QPC, DC, L, etc.).
    """
    if not query.strip():
        raise ValueError("query must be non-empty")
    fts_query = _sanitize_fts5(query)
    if not fts_query:
        return {
            "total": 0,
            "returned": 0,
            "decisions": [],
            "note": "Query vide après nettoyage FTS5 (caractères spéciaux "
                    "retirés). Reformuler en mots-clés simples.",
        }
    limit = max(1, min(int(limit), 50))
    conn = _get_conn()
    try:
        SNIPPET = "snippet(decisions_fts, -1, '<em>', '</em>', '…', 28)"
        base_where = "decisions_fts MATCH ? AND d.juridiction = 'Conseil constitutionnel'"
        params: list = [fts_query]
        if nature and nature.upper() in CC_NATURES:
            base_where += " AND d.nature = ?"
            params.append(nature.upper())
        if date_min:
            base_where += " AND d.date >= ?"
            params.append(date_min)
        if date_max:
            base_where += " AND d.date <= ?"
            params.append(date_max)
        sql = (f"SELECT d.id, d.titre, d.date, d.juridiction, d.solution, "
               f"d.numero, d.formation, d.ecli, d.nature, {SNIPPET} AS snip "
               f"FROM decisions_fts f JOIN decisions d ON d.rowid = f.rowid "
               f"WHERE {base_where} ORDER BY d.date DESC LIMIT ? OFFSET ?")
        try:
            rows = conn.execute(sql, params + [int(limit), int(offset)]).fetchall()
            total = conn.execute(
                f"SELECT COUNT(*) FROM decisions_fts f JOIN decisions d ON d.rowid = f.rowid WHERE {base_where}",
                params,
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            return _fts_syntax_error_result(e)
        decisions = [{
            "id": r["id"], "titre": r["titre"], "date": r["date"],
            "juridiction": r["juridiction"], "solution": r["solution"],
            "numero": r["numero"], "nature": r["nature"], "ecli": r["ecli"],
            "snippet": r["snip"] or "",
        } for r in rows]
        return {
            "total": total,
            "returned": len(decisions),
            "nature_filter": nature.upper() if nature else None,
            "decisions": decisions,
        }
    finally:
        conn.close()


def get_cc_decision(numero: str, nature: str | None = None) -> dict[str, Any] | None:
    """Récupère une décision du Conseil constitutionnel par son numéro.

    Le numéro de décision CC suit le format `AA-NNN NATURE` (ex : "79-105 DC",
    "2020-800 DC", "2023-1048 QPC"). On cherche via FTS5 sur le pattern
    pour retrouver l'entrée dans judiciaire.db.
    """
    if not numero.strip():
        return None
    # Un guillemet dans le numéro casserait la phrase FTS5 ci-dessous.
    num_clean = numero.strip().replace('"', " ").replace(" ", " ")
    # FTS5 phrase match sur le numéro
    fts_q = f'"{num_clean}"'
    conn = _get_conn()
    try:
        base = ("SELECT d.id, d.titre, d.date, d.juridiction, d.nature, d.ecli, d.text "
                "FROM decisions_fts f JOIN decisions d ON d.rowid = f.rowid "
                "WHERE decisions_fts MATCH ? AND d.juridiction = 'Conseil constitutionnel'")
        params = [fts_q]
        if nature and nature.upper() in CC_NATURES:
            base += " AND d.nature = ?"
            params.append(nature.upper())
        base += " ORDER BY d.date DESC LIMIT 1"
        row = conn.execute(base, params).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "titre": row["titre"], "date": row["date"],
            "juridiction": row["juridiction"], "nature": row["nature"],
            "ecli": row["ecli"], "text": row["text"],
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
        # `numero` est parfois un champ multi-valeur (ex: "22-83263 24-80053" pour
        # une décision rendue sur plusieurs pourvois joints). On match :
        # 1. exact (cas standard, utilise l'index sur numero)
        # 2. en première position : GLOB "VALUE *" (utilise l'index, ~ms)
        # ⚠ LIKE est case-insensitive en SQLite par défaut → full scan, 60s+.
        # GLOB est case-sensitive → SQLite peut le réduire à un range scan.
        # On ignore le cas "% VALUE" car wildcard initial = full scan inévitable.
        # En pratique, le numéro principal est toujours en première position.
        if field == "numero":
            sql = """SELECT id, titre, date, juridiction, solution,
                            numero, formation, ecli, nature
                     FROM decisions
                     WHERE numero = ?
                     UNION ALL
                     SELECT id, titre, date, juridiction, solution,
                            numero, formation, ecli, nature
                     FROM decisions
                     WHERE numero GLOB ?
                     LIMIT ?"""
            params = (value, f"{value} *", int(limit))
        else:
            sql = f"""SELECT id, titre, date, juridiction, solution,
                              numero, formation, ecli, nature
                       FROM decisions
                       WHERE {field} = ?
                       LIMIT ?"""
            params = (value, int(limit))
        rows = conn.execute(sql, params).fetchall()
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
        # Colonnes optionnelles ajoutées par enrich_dila (ALTER TABLE) :
        # peuvent être absentes sur d'anciennes copies — `keys()` permet de
        # rester compatible.
        cols = set(row.keys()) if hasattr(row, "keys") else set()
        def opt(name):
            return (row[name] or "") if name in cols else ""
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
            # Nouvelles sections sémantiques (DILA XML SCT/ANA/CITATION_JP)
            "sommaire": opt("sommaire"),
            "abstrats": opt("abstrats"),
            "resume": opt("resume"),
            "renvois": opt("renvois"),
            "rapporteur": opt("rapporteur"),
            "commissaire_gvt": opt("commissaire_gvt"),
            "type_rec": opt("type_rec"),
            "publi_recueil": opt("publi_recueil"),
            "publi_bull": opt("publi_bull"),
            "nature_qualifiee": opt("nature_qualifiee"),
            "saisines": opt("saisines"),
            "loi_def": opt("loi_def"),
            "liens_textes": opt("liens_textes"),
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
