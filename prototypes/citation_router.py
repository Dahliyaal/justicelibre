#!/usr/bin/env python3
"""PROTOTYPE — parseur de citations juridiques + routeur de recherche.

Objectif : qu'un copier-coller de citation ("CAA Toulouse, 2e ch., 27 fév.
2024, n° 21TL04508") mette LA bonne décision en n°1, au lieu du bruit.

Méthode 100 % déterministe (zéro LLM) :
  1. parse_citation()  : extrait les entités DANS la phrase (numéros typés,
     date, juridiction+ville) par regex + lexique ;
  2. route()           : choisit la/les sources selon le type de numéro et
     interroge l'API publique (lecture seule) ;
  3. rescore()         : départage les homonymes par juridiction puis date.

Test : `python3 prototypes/citation_router.py` → PASS/FAIL sur les cas réels.
NE TOUCHE PAS À LA PROD — consomme l'API publique comme un client.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

API = "https://justicelibre.org/api/search"

# ─── Normalisation ───────────────────────────────────────────────

def fold(s: str) -> str:
    """minuscules + sans accents (İ turc compris)."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()

MOIS = {"janv": "01", "fevr": "02", "fev": "02", "mars": "03", "avr": "04",
        "mai": "05", "juin": "06", "juil": "07", "aout": "08", "sept": "09",
        "oct": "10", "nov": "11", "dec": "12"}

# ─── 1. Parseur d'entités ────────────────────────────────────────

# Numéros typés, par ordre de spécificité décroissante. Chaque type sait
# quelle(s) source(s) interroger.
NUM_PATTERNS = [
    ("ecli",     re.compile(r"\bECLI:[A-Z]+:[A-Z]+:\d{4}:[\w.]+\b", re.I)),
    ("celex",    re.compile(r"\b6\d{4}[A-Z]{2}\d{4}\b")),
    ("cjue",     re.compile(r"\b([CT])-(\d{1,4})/(\d{2})\b")),
    ("caa_ce",   re.compile(r"\b\d{2}[A-Z]{2}\d{5}\b")),          # 21TL04508
    ("pourvoi",  re.compile(r"\b\d{2}-\d{2}\.?\d{3}\b")),          # 21-19.841
    ("cedh",     re.compile(r"\b(\d{3,5})/(\d{2})\b")),            # 23065/12
    ("rg",       re.compile(r"\b(\d{2})/(\d{4,5})\b")),            # 07/00033
    ("dossier",  re.compile(r"\b(\d{6,7})\b")),                    # 2302331, 496947
]

DATE_RE = re.compile(
    r"\b(1er|\d{1,2})\s+(janv|f[ée]vr?|mars|avr|mai|juin|juil|ao[uû]t|sept|oct|nov|d[ée]c)\w*\.?\s+(\d{4})\b",
    re.I)

# Lexique juridictions : (regex, type, capture_ville). Ordre = spécificité.
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


def parse_citation(q: str) -> dict:
    """Extrait numéros typés, date ISO, juridiction (type+ville), texte restant."""
    rest = q
    out = {"numeros": [], "date": "", "juri_type": "", "juri_ville": "", "text": ""}

    # Juridiction d'abord (avant de manger les numéros)
    for rx, jtype, has_ville in JURI_PATTERNS:
        m = rx.search(rest)
        if m:
            out["juri_type"] = jtype
            if has_ville and m.groups() and m.group(1):
                out["juri_ville"] = m.group(1).strip("'’-")
            rest = rest[:m.start()] + " " + rest[m.end():]
            break

    # Date ISO yyyy-mm-dd d'abord (la plus spécifique : l'année devant)
    m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", rest)
    if m:
        an, mo, j = m.group(1), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= j <= 31 and 1799 < int(an) < 2100:
            out["date"] = f"{an}-{mo:02d}-{j:02d}"
            rest = rest[:m.start()] + " " + rest[m.end():]

    # Date numérique dd-mm-yyyy — AVANT les numéros, sinon
    # "13-11-2026" serait pris pour un n° de pourvoi.
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", rest)
    if m and not out["date"]:
        j, mo, an = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mo <= 12 and 1 <= j <= 31:
            out["date"] = f"{an}-{mo:02d}-{j:02d}"
            rest = rest[:m.start()] + " " + rest[m.end():]

    # Date en toutes lettres
    m = DATE_RE.search(rest)
    if m and not out["date"]:
        jour = "01" if m.group(1) == "1er" else f"{int(m.group(1)):02d}"
        mois_key = fold(m.group(2))[:4].rstrip(".")
        mois = MOIS.get(mois_key) or MOIS.get(mois_key[:3], "")
        if mois:
            out["date"] = f"{m.group(3)}-{mois}-{jour}"
        rest = rest[:m.start()] + " " + rest[m.end():]

    # Numéros (le premier de chaque type ; le plus spécifique gagne le routage)
    seen_spans: list[tuple[int, int]] = []
    for kind, rx in NUM_PATTERNS:
        m = rx.search(rest)
        if m and not any(s <= m.start() < e for s, e in seen_spans):
            out["numeros"].append((kind, m.group(0)))
            seen_spans.append((m.start(), m.end()))

    # Désambiguïsation cedh/rg (même forme NNNN/NN vs NN/NNNNN)
    # cedh = 3-5 chiffres / 2 ; rg = 2 chiffres / 4-5. Un match "07/00033"
    # peut être pris par cedh à tort si 5/2 ↔ 2/5 : on tranche par la juridiction.
    if out["juri_type"] in {"ca", "cph", "tj", "tsa"}:
        out["numeros"] = [(("rg", v) if k == "cedh" else (k, v)) for k, v in out["numeros"]]
    if out["juri_type"] == "cedh":
        out["numeros"] = [(("cedh", v) if k == "rg" else (k, v)) for k, v in out["numeros"]]

    # Texte restant (mots signifiants, sans le bruit de citation)
    for _, v in out["numeros"]:
        rest = rest.replace(v, " ")
    rest = re.sub(r"\bn[°o]\s*", " ", rest)
    rest = re.sub(r"\b\d?\w{0,2}[eè](?:me|re)?\s+ch(?:ambre|\.)?\b", " ", rest, flags=re.I)
    rest = re.sub(r"[(),;·§]|\bdu\b|\bde\b|\bc\.\b", " ", rest, flags=re.I)
    out["text"] = re.sub(r"\s+", " ", rest).strip()
    return out


# ─── 2. Routage ──────────────────────────────────────────────────

# type de numéro → sources à interroger, dans l'ordre
ROUTES = {
    "cjue":    ["cjue"],
    "celex":   ["cjue"],
    "cedh":    ["cedh"],
    "caa_ce":  ["admin"],
    "dossier": ["admin", "ariane"],
    "pourvoi": ["dila"],
    "rg":      ["dila"],
    "ecli":    ["admin", "dila", "cjue"],
}
# juridiction → restreint encore
JURI_SOURCES = {"cjue": ["cjue"], "cedh": ["cedh"], "ta": ["admin"],
                "caa": ["admin"], "ce": ["admin", "ariane"],
                "ca": ["dila"], "cass": ["dila"], "cph": ["dila"],
                "tj": ["dila"], "tsa": ["dila"]}


def api_search(q: str, sources: str = "", limit: int = 20,
               date_min: str = "", date_max: str = "") -> list[dict]:
    params = {"q": q, "limit": str(limit)}
    if sources:
        params["sources"] = sources
    if date_min:
        params["date_min"] = date_min
    if date_max:
        params["date_max"] = date_max
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "justicelibre-citation-router-prototype/0.1 (dev interne)"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r).get("results", [])
    except Exception as e:
        print(f"    (api err {sources}: {e})", file=sys.stderr)
        return []


def celex_from_cjue(kind_val: str) -> str:
    """'C-312/11' → '62011CJ0312' (arrêt). Le greffe CJUE numérote AAAA + type + NNNN."""
    m = re.match(r"([CT])-(\d{1,4})/(\d{2})", kind_val)
    if not m:
        return ""
    lettre, num, yy = m.groups()
    year = ("19" if int(yy) > 50 else "20") + yy
    code = "CJ" if lettre == "C" else "TJ"
    return f"6{year}{code}{int(num):04d}"


def api_get_decision(source: str, rid: str) -> dict | None:
    url = ("https://justicelibre.org/api/decision?"
           + urllib.parse.urlencode({"source": source, "id": rid}))
    req = urllib.request.Request(url, headers={
        "User-Agent": "justicelibre-citation-router-prototype/0.1 (dev interne)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
            if d and not d.get("error") and (d.get("text") or d.get("titre") or d.get("juridiction")):
                d.setdefault("id", rid)
                return d
    except Exception:
        pass
    return None


# Préfixes d'IDs admin, ordre de probabilité (décision, ordonnance × TA/CAA/CE)
ADMIN_ID_PREFIXES = {"ta": ["DTA", "ORTA"], "caa": ["DCAA", "ORCA"],
                     "ce": ["DCE", "ORCE"],
                     "": ["DTA", "DCAA", "DCE", "ORTA", "ORCA", "ORCE"]}


def probe_admin_ids(parsed: dict) -> list[dict]:
    """dossier + date connus → construit les IDs admin candidats et sonde
    leur existence. Déterministe : si ça matche, c'est LA décision."""
    num = next((v for k, v in parsed["numeros"] if k in ("dossier", "caa_ce")), "")
    if not (num and parsed["date"]):
        return []
    ymd = parsed["date"].replace("-", "")
    hits = []
    for prefix in ADMIN_ID_PREFIXES.get(parsed["juri_type"], ADMIN_ID_PREFIXES[""]):
        d = api_get_decision("admin", f"{prefix}_{num}_{ymd}")
        if d:
            d["relevance"] = 100  # match exact construit : score maximal
            hits.append(d)
    return hits


def route_and_search(parsed: dict) -> list[dict]:
    """Interroge les bonnes sources selon les entités trouvées."""
    # 0. Sonde d'ID exact (admin) : numéro + date → identifiant déterministe
    if parsed["juri_type"] in ("ta", "caa", "ce", ""):
        exact = probe_admin_ids(parsed)
        if exact:
            return exact
    candidates: list[dict] = []
    for kind, val in parsed["numeros"]:
        sources = ROUTES.get(kind, [])
        # restreint par juridiction si connue et compatible
        if parsed["juri_type"] in JURI_SOURCES:
            juri_srcs = JURI_SOURCES[parsed["juri_type"]]
            inter = [s for s in sources if s in juri_srcs]
            sources = inter or sources
        q = val
        if kind == "cjue":
            # essaie le CELEX exact d'abord (déterministe)
            celex = celex_from_cjue(val)
            if celex:
                candidates += api_search(celex, ",".join(sources))
        for src in sources:
            candidates += api_search(q, src)
        if candidates:
            break  # le numéro le plus spécifique a suffi
    if not candidates and parsed["text"]:
        # Texte restant (noms de parties…) : cherche dans les sources de la
        # juridiction si connue, sinon fédéré ; la date resserre si présente.
        srcs = ",".join(JURI_SOURCES.get(parsed["juri_type"], []))
        candidates = api_search(parsed["text"], srcs,
                                date_min=parsed["date"], date_max=parsed["date"])
        if not candidates and parsed["date"]:
            candidates = api_search(parsed["text"], srcs)
    if not candidates and parsed["juri_type"] and parsed["date"]:
        # Référence de rappel type "Cass. crim. 21 janv. 2025, § 41" : ni
        # numéro ni nom — on liste les décisions de cette juridiction ce
        # jour-là (peu nombreuses) et le re-scoring fera le reste.
        JURI_QUERY = {"cass": "cassation", "ce": "conseil état", "cjue": "cour justice",
                      "cedh": "cour", "ta": "tribunal administratif",
                      "caa": "cour administrative appel", "ca": "cour appel",
                      "tj": "tribunal judiciaire", "cph": "prud'hommes",
                      "tsa": "tribunal supérieur appel"}
        srcs = ",".join(JURI_SOURCES.get(parsed["juri_type"], []))
        candidates = api_search(JURI_QUERY.get(parsed["juri_type"], parsed["juri_type"]),
                                srcs, limit=30,
                                date_min=parsed["date"], date_max=parsed["date"])
    return candidates


# ─── 3. Re-scoring des homonymes ─────────────────────────────────

def rescore(candidates: list[dict], parsed: dict) -> list[dict]:
    ville = fold(parsed["juri_ville"])
    date = parsed["date"]
    text_tokens = [t for t in fold(parsed["text"]).split() if len(t) > 3]

    def score(r: dict) -> float:
        s = float(r.get("relevance", 0)) / 100.0
        juri = fold(r.get("juridiction", "") + " " + r.get("titre", r.get("title", "")))
        if ville and ville in juri:
            s += 10
        if date and r.get("date", "") == date:
            s += 8
        elif date and (r.get("date", "") or "")[:4] == date[:4]:
            s += 2
        s += sum(1.5 for t in text_tokens if t in juri)
        return s

    dedup: dict[str, dict] = {}
    for r in candidates:
        rid = r.get("id", "") or json.dumps(r, sort_keys=True)[:60]
        if rid not in dedup:
            dedup[rid] = r
    return sorted(dedup.values(), key=score, reverse=True)


def search_citation(q: str) -> list[dict]:
    parsed = parse_citation(q)
    return rescore(route_and_search(parsed), parsed), parsed


def _norm_num(s: str) -> str:
    return re.sub(r"[.\-/\s]", "", s or "")


def make_check(num: str = "", date: str = "", juri_frag: str = ""):
    """Réussite = le n°1 porte le bon numéro (insensible à la ponctuation),
    ou à défaut la bonne date + un fragment de juridiction."""
    def check(r: dict) -> bool:
        rnum = _norm_num(str(r.get("numero", r.get("number", ""))))
        rid = _norm_num(r.get("id", ""))
        if num and (_norm_num(num) == rnum or _norm_num(num) in rid):
            return True
        if date and r.get("date", "") == date:
            jf = fold(juri_frag)
            return (not jf) or jf in fold(r.get("juridiction", "") + r.get("titre", r.get("title", "")))
        return False
    return check


# ─── Banc de test (cas réels fournis par la mainteneuse) ─────────

TESTS = [
    # ── les 5 cas fondateurs ──
    ("Tribunal supérieur d'appel de Mamoudzou n° 07/00033 · 6 novembre 2007",
     lambda r: r.get("id") == "JURITEXT000019394773"),
    ("l'ordonnance du tribunal administratif de Melun du 20 juillet 2023 (n° 2302331)",
     lambda r: r.get("id") == "DTA_2302331_20230720"),
    ("CAA Toulouse, 2e ch., 27 fév. 2024, n° 21TL04508",
     lambda r: r.get("id") == "CETATEXT000049217822"),
    ("CJUE, 4 juillet 2013, Commission c. Italie, C-312/11",
     lambda r: r.get("id") == "62011CJ0312"),
    ("CEDH, 30 janvier 2018, Enver Şahin c. Turquie, n° 23065/12, § 72",
     lambda r: "enver" in fold(r.get("titre", r.get("title", ""))) or r.get("date") == "2018-01-30"),
    # ── les 22 références distinctes du mémoire (verbatim) ──
    ("CAA Nancy, 24 mai 2006, n° 03NC01126", make_check("03NC01126", "2006-05-24", "nancy")),
    ("CAA Nantes, 3ème ch., 21 juillet 2023, n° 22NT01294", make_check("22NT01294", "2023-07-21", "nantes")),
    ("CE, 27 juillet 2001, n° 212050", make_check("212050", "2001-07-27", "tat")),
    ("CE, Ass., 26 octobre 2001, Ternon, n° 197018", make_check("197018", "2001-10-26", "tat")),
    ("CE, 6 mars 2009, Coulibaly, n° 306084", make_check("306084", "2009-03-06", "tat")),
    ("CJUE, 11 avril 2013, HK Danmark, C-335/11", make_check("", "2013-04-11", "cjue")),
    ("CE, Ass., 22 octobre 2010, Bleitrach, n° 301572, publié au Recueil Lebon",
     make_check("301572", "2010-10-22", "tat")),
    ("CE, 23 juin 2023, Société Combronde Logistique, n° 454844", make_check("454844", "2023-06-23", "tat")),
    ("Cass. crim., 21 janvier 2025, France Télécom, n° 22-87.145, publié au bulletin",
     make_check("22-87.145", "2025-01-21", "cassation")),
    ("Cass. crim., 11 mars 2025, Centre hospitalier universitaire de La Réunion, n° 22-83.263",
     make_check("22-83.263", "2025-03-11", "cassation")),
    ("CE, Sect., 11 juillet 2011, n° 321225", make_check("321225", "2011-07-11", "tat")),
    ("CAA Nantes, 1ère ch., 18 novembre 2025, n° 25NT00556", make_check("25NT00556", "2025-11-18", "nantes")),
    # ABSENTE de la base (couverture TA partielle) : la bonne réponse est
    # "rien" ou un résultat daté du même jour au même TA — pas du bruit.
    ("TA Lille, 2 juin 2020, Welkamp c/ MDPH du Nord",
     lambda r: (not r) or (r.get("date") == "2020-06-02" and "lille" in fold(r.get("juridiction", "")))),
    ("CE, 5e-6e ch. réunies, 24 juillet 2019, n° 421189", make_check("421189", "2019-07-24", "tat")),
    ("CE, 5e-6e ch. réunies, 23 octobre 2019, n° 422023", make_check("422023", "2019-10-23", "tat")),
    ("CE, 5e-4e ch. réunies, 16 décembre 2016, n° 383111", make_check("383111", "2016-12-16", "tat")),
    ("CAA Douai, 15 janv. 2025, n° 21DA02143", make_check("21DA02143", "2025-01-15", "douai")),
    ("CE, 7 juin 2010, n° 312909, Lebon T.", make_check("312909", "2010-06-07", "tat")),
    # ABSENTE de la base (1947, antérieure à la couverture JADE) : la bonne
    # réponse est "rien" — surtout pas des référés de 2026.
    ("CE, Ass., 21 mars 1947, Aubry, n° 80338",
     lambda r: (not r) or _norm_num(r.get("numero", "")) == "80338"),
    ("CAA Lyon, 31 janv. 2025, n° 23LY00926", make_check("23LY00926", "2025-01-31", "lyon")),
    ("CE, Ass., 22 oct. 2010, Bleitrach, n° 301572", make_check("301572", "2010-10-22", "tat")),
    # Référence de rappel sans numéro sur le fonds judiciaire : limite v1
    # assumée (repli-jour trop lourd sur dila) → aveu immédiat accepté.
    ("Cass. crim. 21 janv. 2025, § 41",
     lambda r: (not r) or ((r.get("date") == "2025-01-21") and "cassation" in fold(r.get("juridiction", "")))),
    # ── mode flemmard : références partielles, sales, minuscules ──
    ("CE n°422023", make_check("422023", "2019-10-23", "")),
    ("CE 422023", make_check("422023", "2019-10-23", "")),
    # nom seul, sans date : les DEUX arrêts CE Bleitrach (2007 et 2010) sont
    # des réponses légitimes en n°1
    ("ce, bleitrach", lambda r: _norm_num(r.get("numero", "")) == "301572"
     or "114818" in (r.get("id") or "")),
    ("Conseil d'État a jugé (13 novembre 2023, n° 466958)", make_check("466958", "2023-11-13", "")),
    ("13 novembre 2023, n° 466958", make_check("466958", "2023-11-13", "")),
    ("caa douai 21DA02143", make_check("21DA02143", "2025-01-15", "douai")),
    ("cass 22-87.145", make_check("22-87.145", "2025-01-21", "")),
    ("21TL04508", make_check("21TL04508", "2024-02-27", "toulouse")),
    # ── 2e mémoire (TA Rectorat) : ord. réf., tables Lebon, chambres nues ──
    ("Cass. 2e civ., 13 mars 2003, n° 01-17.418", make_check("01-17.418", "2003-03-13", "cassation")),
    ("2e civ., 13 mars 2003, n° 01-17.418, publié au bulletin", make_check("01-17.418", "2003-03-13", "cassation")),
    ("rappr. CE, 13 novembre 2023, n° 466958, jugeant la juridiction administrative "
     "incompétente pour connaître d'un litige relatif à une décision de la direction diocésaine",
     make_check("466958", "2023-11-13", "")),
    ("CE, ord. réf., 14 avril 2023, n° 472611", make_check("472611", "2023-04-14", "")),
    ("CE, ord. réf., 14 avril 2023, Association Juristes pour l'enfance, n° 472611, "
     "mentionné aux tables du recueil Lebon", make_check("472611", "2023-04-14", "")),
    ("CE, ord. réf., 4 avril 2020, n° 439816, point 6", make_check("439816", "2020-04-04", "")),
    ("CE, 22 février 2012, n° 343052, mentionné aux tables du recueil Lebon",
     make_check("343052", "2012-02-22", "")),
    ("CE, ord. réf., 15 décembre 2010, n° 344729", make_check("344729", "2010-12-15", "")),
    ("l'affaire n° 344729", make_check("344729", "2010-12-15", "")),
    ("décision n° 344729", make_check("344729", "2010-12-15", "")),
    ("CE, 1er juillet 2022, n° 463162", make_check("463162", "2022-07-01", "")),
    # 1965 : peut-être absente de la base — absence honnête acceptée
    ("CE, 7 juillet 1965, n° 61958, publié au recueil Lebon",
     lambda r: (not r) or _norm_num(r.get("numero", "")) == "61958"),
]

if __name__ == "__main__":
    ok = 0
    for q, check in TESTS:
        results, parsed = search_citation(q)
        top = results[0] if results else {}
        hit = check(top) if results else bool(check({}))
        ok += hit
        status = "✅ PASS" if hit else "❌ FAIL"
        print(f"{status}  {q[:70]}")
        print(f"        parsé: nums={parsed['numeros']} date={parsed['date']} "
              f"juri={parsed['juri_type']}/{parsed['juri_ville']}")
        if results:
            print(f"        n°1 → {top.get('id','?')} | {top.get('juridiction','')[:40]} | {top.get('date','')}")
        else:
            print("        n°1 → (aucun résultat)")
        print()
    print(f"── {ok}/{len(TESTS)} ──")
    sys.exit(0 if ok == len(TESTS) else 1)
