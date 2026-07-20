"""Détection et résolution des références jurisprudentielles.

Quand un utilisateur colle une référence ("CAA Toulouse, 27 fév. 2024,
n° 21TL04508", "13 novembre 2023, n° 466958", "cass 22-87.145"…), ce module
la détecte, extrait ses entités (numéros typés, date, juridiction) et route
vers la bonne source — au lieu de laisser la référence se faire déchiqueter
par le FTS et le thésaurus.

Principes (validés par prototypes/citation_router.py, 45/47 cas réels) :
  - chaque entité est un INDICE, jamais une exigence : le numéro est roi,
    la juridiction départage les homonymes, la date booste et détecte les
    contradictions ;
  - le nom d'une juridiction est un FILTRE, jamais un concept à élargir ;
  - si la référence est introuvable, on l'AVOUE (results=[] + note) au lieu
    de renvoyer du bruit.

Point d'entrée : `try_citation_search(q, limit)` (async).
Retourne un dict au format search_federated + "citation_match": True,
ou None si la query ne ressemble pas à une référence (→ pipeline normal).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


MOIS = {"janv": "01", "fevr": "02", "fev": "02", "mars": "03", "avr": "04",
        "mai": "05", "juin": "06", "juil": "07", "aout": "08", "sept": "09",
        "oct": "10", "nov": "11", "dec": "12"}

NUM_PATTERNS = [
    ("ecli",     re.compile(r"\bECLI:[A-Z]+:[A-Z]+:\d{4}:[\w.]+\b", re.I)),
    ("celex",    re.compile(r"\b6\d{4}[A-Z]{2}\d{4}\b")),
    ("cjue",     re.compile(r"\b([CT])-(\d{1,4})/(\d{2})\b")),
    ("caa_ce",   re.compile(r"\b\d{2}[A-Z]{2}\d{5}\b")),
    ("pourvoi",  re.compile(r"\b\d{2}-\d{2}\.?\d{3}\b")),
    ("cedh",     re.compile(r"\b(\d{3,5})/(\d{2})\b")),
    ("rg",       re.compile(r"\b(\d{2})/(\d{4,5})\b")),
    ("dossier",  re.compile(r"\b(\d{6,7})\b")),
]

DATE_TXT_RE = re.compile(
    r"\b(1er|\d{1,2})\s+(janv|f[ée]vr?|mars|avr|mai|juin|juil|ao[uû]t|sept|oct|nov|d[ée]c)\w*\.?\s+(\d{4})\b",
    re.I)

JURI_PATTERNS = [
    (re.compile(r"\bCJUE\b|\bCJCE\b|cour de justice de l'union", re.I), "cjue", False),
    (re.compile(r"\bCEDH\b|cour ?edh|cour europ[ée]enne des droits", re.I), "cedh", False),
    (re.compile(r"tribunal sup[ée]rieur d'appel\s+(?:de\s+|d'|du\s+)?([A-ZÉÈÎ][\w'’-]+)", re.I), "tsa", True),
    (re.compile(r"(?:cour administrative d'appel|C\.?A\.?A\.?)\s*(?:de\s+|d'|du\s+)?([A-ZÉÈÎ][\w'’-]+)?", re.I), "caa", True),
    (re.compile(r"(?:tribunal administratif|\bT\.?A\.?\b)\s*(?:de\s+|d'|du\s+)?([A-ZÉÈÎ][\w'’-]+)?", re.I), "ta", True),
    (re.compile(r"conseil d'[ée]tat|\bC\.?E\.?\b(?=[\s,.;]|$)", re.I), "ce", False),
    (re.compile(r"cour de cassation|\bcass\.?\b", re.I), "cass", False),
    (re.compile(r"\b(?:1[èr]?re|[23]e)\s+civ\.?\b|\bch\.?\s+mixte\b|\bcrim\.\b|\bsoc\.\b|\bcom\.\b", re.I), "cass", False),
    (re.compile(r"cour d'appel\s+(?:de\s+|d'|du\s+)?([A-ZÉÈÎ][\w'’-]+)", re.I), "ca", True),
    (re.compile(r"conseil de prud'hommes\s+(?:de\s+|d'|du\s+)?([A-ZÉÈÎ][\w'’-]+)?", re.I), "cph", True),
    (re.compile(r"tribunal judiciaire\s+(?:de\s+|d'|du\s+)?([A-ZÉÈÎ][\w'’-]+)", re.I), "tj", True),
]

ROUTES = {"cjue": ["cjue"], "celex": ["cjue"], "cedh": ["cedh"],
          "caa_ce": ["admin"], "dossier": ["admin", "ariane"],
          "pourvoi": ["dila"], "rg": ["dila"],
          "ecli": ["admin", "dila", "cjue"]}
JURI_SOURCES = {"cjue": ["cjue"], "cedh": ["cedh"], "ta": ["admin"],
                "caa": ["admin"], "ce": ["admin", "ariane"],
                "ca": ["dila"], "cass": ["dila"], "cph": ["dila"],
                "tj": ["dila"], "tsa": ["dila"]}
JURI_DAY_QUERY = {"cass": "cassation", "ce": "conseil état",
                  "cjue": "cour justice", "cedh": "cour",
                  "ta": "tribunal administratif", "caa": "cour administrative appel",
                  "ca": "cour appel", "tj": "tribunal judiciaire",
                  "cph": "prud'hommes", "tsa": "tribunal supérieur appel"}
ADMIN_ID_PREFIXES = {"ta": ["DTA", "ORTA"], "caa": ["DCAA", "ORCA"],
                     "ce": ["DCE", "ORCE"],
                     "": ["DTA", "DCAA", "DCE", "ORTA", "ORCA", "ORCE"]}


def parse_citation(q: str) -> dict:
    """Extrait numéros typés, date ISO, juridiction (type+ville), texte restant."""
    rest = q
    out = {"numeros": [], "date": "", "juri_type": "", "juri_ville": "", "text": ""}

    for rx, jtype, has_ville in JURI_PATTERNS:
        m = rx.search(rest)
        if m:
            out["juri_type"] = jtype
            if has_ville and m.groups() and m.group(1):
                out["juri_ville"] = m.group(1).strip("'’-")
            rest = rest[:m.start()] + " " + rest[m.end():]
            break

    # Dates : ISO yyyy-mm-dd, puis dd-mm-yyyy, puis toutes lettres —
    # extraites AVANT les numéros (sinon "13-11-2026" simule un pourvoi).
    m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", rest)
    if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31 \
         and 1799 < int(m.group(1)) < 2100:
        out["date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        rest = rest[:m.start()] + " " + rest[m.end():]
    if not out["date"]:
        m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", rest)
        if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31:
            out["date"] = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
            rest = rest[:m.start()] + " " + rest[m.end():]
    if not out["date"]:
        m = DATE_TXT_RE.search(rest)
        if m:
            jour = "01" if m.group(1) == "1er" else f"{int(m.group(1)):02d}"
            mois = MOIS.get(_fold(m.group(2))[:4].rstrip(".")) or MOIS.get(_fold(m.group(2))[:3], "")
            if mois:
                out["date"] = f"{m.group(3)}-{mois}-{jour}"
            rest = rest[:m.start()] + " " + rest[m.end():]

    seen: list[tuple[int, int]] = []
    for kind, rx in NUM_PATTERNS:
        m = rx.search(rest)
        if m and not any(s <= m.start() < e for s, e in seen):
            out["numeros"].append((kind, m.group(0)))
            seen.append((m.start(), m.end()))

    # Désambiguïsation cedh/rg (formes miroir) par la juridiction
    if out["juri_type"] in {"ca", "cph", "tj", "tsa"}:
        out["numeros"] = [(("rg", v) if k == "cedh" else (k, v)) for k, v in out["numeros"]]
    if out["juri_type"] == "cedh":
        out["numeros"] = [(("cedh", v) if k == "rg" else (k, v)) for k, v in out["numeros"]]

    for _, v in out["numeros"]:
        rest = rest.replace(v, " ")
    rest = re.sub(r"\bn[°o]\s*", " ", rest, flags=re.I)
    rest = re.sub(r"\b\d?\w{0,2}[eè](?:me|re)?\s+ch(?:ambre|\.)?\b", " ", rest, flags=re.I)
    rest = re.sub(r"[(),;·§]|\bdu\b|\bde\b|\bc\.\b|\bord\.\b|\br[ée]f\.\b|\brappr\.\b", " ", rest, flags=re.I)
    out["text"] = re.sub(r"\s+", " ", rest).strip()
    return out


def is_reference(parsed: dict) -> bool:
    """Une query est une référence si elle porte un numéro, ou juridiction+date."""
    return bool(parsed["numeros"]) or bool(parsed["juri_type"] and parsed["date"])


def _celex_from_cjue(val: str) -> str:
    m = re.match(r"([CT])-(\d{1,4})/(\d{2})", val)
    if not m:
        return ""
    lettre, num, yy = m.groups()
    year = ("19" if int(yy) > 50 else "20") + yy
    return f"6{year}{'CJ' if lettre == 'C' else 'TJ'}{int(num):04d}"


def _row_from_decision(d: dict, rid: str, source: str) -> dict:
    """Normalise un retour fetch_decision en row de résultat de recherche."""
    juri = d.get("juridiction") or d.get("juridiction_name") or ""
    numero = d.get("numero") or d.get("numero_dossier") or d.get("number") or ""
    return {
        "id": d.get("id") or rid,
        "source": source,
        "source_label": {"admin": "Justice administrative", "cjue": "CJUE",
                         "cedh": "Cour EDH", "dila": "Justice judiciaire",
                         "ariane": "Conseil d'État"}.get(source, source),
        "title": d.get("titre") or d.get("title") or (f"{juri} — n° {numero}" if numero else juri),
        "juridiction": juri,
        "date": (d.get("date") or "")[:10],
        "formation": d.get("formation", ""),
        "numero": numero,
        "ecli": d.get("ecli") or "",
        "extract": "",
        "relevance": 100,
    }


def _rescore(rows: list[dict], parsed: dict) -> list[dict]:
    ville = _fold(parsed["juri_ville"])
    date = parsed["date"]
    toks = [t for t in _fold(parsed["text"]).split() if len(t) > 3]

    def score(r: dict) -> float:
        s = float(r.get("relevance") or 0) / 100.0
        juri = _fold((r.get("juridiction") or "") + " " + (r.get("title") or r.get("titre") or ""))
        if ville and ville in juri:
            s += 10
        if date and (r.get("date") or "")[:10] == date:
            s += 8
        elif date and (r.get("date") or "")[:4] == date[:4]:
            s += 2
        s += sum(1.5 for t in toks if t in juri)
        return s

    dedup: dict[str, dict] = {}
    for r in rows:
        rid = r.get("id") or repr(sorted(r.items()))[:60]
        if rid not in dedup:
            dedup[rid] = r
    return sorted(dedup.values(), key=score, reverse=True)


async def try_citation_search(q: str, limit: int = 20) -> dict[str, Any] | None:
    """Si `q` est une référence, la résout et retourne un résultat fédéré-like.
    Sinon retourne None (le pipeline normal prend la main).
    Toute exception ici doit être rattrapée par l'appelant (fallback pipeline)."""
    parsed = parse_citation(q)
    if not is_reference(parsed):
        return None

    # imports tardifs : évite tout cycle, et ne coûte rien si non-référence
    from search_api import search_federated, fetch_decision

    rows: list[dict] = []
    probes_done: list[str] = []

    async def fed(fq: str, sources: list[str], **kw) -> list[dict]:
        d = await search_federated(q=fq, sources_only=sources or None,
                                   limit=limit, limit_per_source=limit, **kw)
        return d.get("results", [])

    for kind, val in parsed["numeros"]:
        sources = ROUTES.get(kind, [])
        if parsed["juri_type"] in JURI_SOURCES:
            inter = [s for s in sources if s in JURI_SOURCES[parsed["juri_type"]]]
            sources = inter or sources

        # a) sondes d'identifiants exacts (déterministe)
        if kind in ("dossier", "caa_ce") and parsed["date"] and "admin" in sources:
            ymd = parsed["date"].replace("-", "")
            for prefix in ADMIN_ID_PREFIXES.get(parsed["juri_type"], ADMIN_ID_PREFIXES[""]):
                rid = f"{prefix}_{val}_{ymd}"
                probes_done.append(rid)
                d = await fetch_decision(source="admin", decision_id=rid)
                if d:
                    rows.append(_row_from_decision(d, rid, "admin"))
            if rows:
                break
        if kind == "cjue":
            celex = _celex_from_cjue(val)
            if celex:
                d = await fetch_decision(source="cjue", decision_id=celex)
                if d:
                    rows.append(_row_from_decision(d, celex, "cjue"))
                    break

        # b) recherche par numéro dans les sources routées
        rows += await fed(val, sources)
        if rows:
            break

    # c) noms de parties restants
    if not rows and parsed["text"] and len(parsed["text"]) > 3:
        srcs = JURI_SOURCES.get(parsed["juri_type"], [])
        rows = await fed(parsed["text"], srcs,
                         date_min=parsed["date"] or None,
                         date_max=parsed["date"] or None)
        if not rows and parsed["date"]:
            rows = await fed(parsed["text"], srcs)

    # d) juridiction + date seules (référence de rappel "Cass. crim. 21 janv. 2025")
    if not rows and parsed["juri_type"] and parsed["date"]:
        rows = await fed(JURI_DAY_QUERY.get(parsed["juri_type"], parsed["juri_type"]),
                         JURI_SOURCES.get(parsed["juri_type"], []),
                         date_min=parsed["date"], date_max=parsed["date"])

    rows = _rescore(rows, parsed)[:limit]

    note = ""
    if not rows:
        bits = [f"n° {v}" for _, v in parsed["numeros"]]
        if parsed["date"]:
            bits.append(f"du {parsed['date']}")
        note = ("Référence détectée (" + ", ".join(bits) +
                ") mais introuvable dans nos fonds. La décision n'est "
                "peut-être pas (encore) dans les données ouvertes.")

    per_source: dict[str, int] = {}
    for r in rows:
        per_source[r.get("source", "?")] = per_source.get(r.get("source", "?"), 0) + 1

    return {
        "total": len(rows),
        "returned": len(rows),
        "results": rows,
        "per_source": per_source,
        "sources_queried": list(per_source),
        "sources_no_result": [],
        "citation_match": True,
        "citation_parsed": {"numeros": [f"{k}:{v}" for k, v in parsed["numeros"]],
                            "date": parsed["date"],
                            "juridiction": f"{parsed['juri_type']} {parsed['juri_ville']}".strip()},
        **({"note": note} if note else {}),
    }
