"""Wrapper for ArianeWeb (Conseil d'État) via the Sinequa JSON xsearch API.

Endpoint: https://www.conseil-etat.fr/xsearch?type=json&SourceStr4=AW_DCE&...

Covers ~270 000 Conseil d'État decisions of jurisprudential interest.
Other SourceStr4 values (AW_TA, AW_CAA, etc.) return empty result sets.

The server returns **all** matching documents in a single response regardless
of pagination params — we slice client-side. Responses can be tens of megabytes
for broad queries; callers should supply specific queries or accept the cost.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

URL = "https://www.conseil-etat.fr/xsearch"
# Strip Sinequa highlight markers like {b}foo{nb} and numeric offsets.
_HIGHLIGHT_RE = re.compile(r"\{n?b\}")
_OFFSET_RE = re.compile(r";\d+,\d+")


_MOIS_FR = {
    "janvier": "01", "février": "02", "fevrier": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06", "juillet": "07",
    "août": "08", "aout": "08", "septembre": "09", "octobre": "10",
    "novembre": "11", "décembre": "12", "decembre": "12",
}
_ARIANE_NUM_RE = re.compile(r"N°\s*([\dA-Z]+)")
_ARIANE_ECLI_RE = re.compile(r"(ECLI:FR:[A-Z0-9:.]+)")
_ARIANE_ECLI_DATE_RE = re.compile(r"\.(\d{4})(\d{2})(\d{2})\b")
_ARIANE_LECTURE_RE = re.compile(
    r"[Ll]ecture d[ue]\s+(?:\w+\s+)?(\d{1,2})(?:er)?\s+([a-zéûôA-Z]+)\s+(\d{4})")


def parse_header(text: str) -> dict[str, str]:
    """Extrait n° de requête, ECLI et date ISO de l'en-tête d'un arrêt ArianeWeb.

    Le plugin Sinequa ne renvoie QUE du texte brut : ni le numéro, ni la date
    ne sont exposés en champ. Sans cette extraction, les enregistrements
    ArianeWeb arrivent avec `numero`/`date`/`ecli` vides alors que l'en-tête
    du texte les contient (« Conseil d'État  N° 454852
    ECLI:FR:CEORD:2021:454852.20210727 … Lecture du mardi 27 juillet 2021 »).

    Deux sources pour la date : l'ECLI (fiable, mais absent des arrêts
    anciens) puis la mention « Lecture du … » en toutes lettres.
    """
    out: dict[str, str] = {}
    if not text:
        return out
    m = _ARIANE_NUM_RE.search(text)
    if m:
        out["numero"] = m.group(1)
    m = _ARIANE_ECLI_RE.search(text)
    if m:
        ecli = m.group(1).rstrip(".")
        out["ecli"] = ecli
        dm = _ARIANE_ECLI_DATE_RE.search(ecli)
        if dm:
            out["date"] = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
    if not out.get("date"):
        lm = _ARIANE_LECTURE_RE.search(text)
        if lm:
            mois = _MOIS_FR.get(lm.group(2).lower())
            if mois:
                out["date"] = f"{lm.group(3)}-{mois}-{int(lm.group(1)):02d}"
    return out


def _clean_extract(raw: str) -> str:
    if not raw:
        return ""
    cleaned = _HIGHLIGHT_RE.sub("", raw)
    cleaned = _OFFSET_RE.sub("", cleaned)
    return cleaned.strip()


def _normalize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    extracts = _clean_extract(doc.get("Extracts", "") or "")
    return {
        "id": doc.get("Id"),
        "index": doc.get("Index"),
        "rank": doc.get("Rank"),
        "relevance": doc.get("Relevance"),
        "title": doc.get("Title"),
        "extracts": extracts,
    }


DOWNLOAD_URL = "https://www.conseil-etat.fr/plugin"


async def fetch_full_text(client: httpx.AsyncClient, ariane_id: str) -> str:
    """Récupère le texte intégral d'une décision ArianeWeb via le plugin
    Sinequa `downloadFilePagePlugin` (réponse HTML iso-8859-1).
    """
    if not ariane_id:
        return ""
    # L'API accepte l'id brut avec slashes et pipe (ne pas URL-encoder)
    params = {
        "plugin": "Service.downloadFilePagePlugin",
        "Index": "Ariane_Web",
        "Id": ariane_id,
    }
    r = await client.get(DOWNLOAD_URL, params=params, timeout=60)
    if r.status_code != 200:
        return ""
    # L'endpoint /plugin DÉCLARE charset=iso-8859-1 mais envoie en réalité
    # de l'UTF-8 valide (vérifié le 7 août 2026) : le croire produisait du
    # mojibake (« Conseil d'Ãtat », « prÃ©sident »). L'UTF-8 est
    # auto-validant — s'il décode strictement, c'est lui ; sinon on retombe
    # sur l'iso-8859-1 annoncé (qui, lui, décode toujours).
    try:
        html = r.content.decode("utf-8")
    except UnicodeDecodeError:
        html = r.content.decode("iso-8859-1")
    # Nettoyage HTML basique
    import re as _re
    text = _re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=_re.DOTALL)
    text = _re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=_re.DOTALL)
    text = _re.sub(r"<br\s*/?>", "\n", text)
    text = _re.sub(r"</p>", "\n\n", text)
    text = _re.sub(r"<[^>]+>", " ", text)
    import html as _html
    text = _html.unescape(text)
    text = _re.sub(r"[ \t]+", " ", text)
    text = _re.sub(r"\n[ \t]+", "\n", text)
    text = _re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def search(
    client: httpx.AsyncClient,
    query: str,
    limit: int = 20,
    skip: int = 0,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must be non-empty")
    params = {
        "type": "json",
        "SourceStr4": "AW_DCE",
        "text.add": query,
        "SkipCount": skip,
    }
    r = await client.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    total = data.get("TotalCount", 0)
    all_docs = data.get("Documents") or []
    # Sinequa ignore PageSize sur cet endpoint, on slice côté client
    start = max(0, int(skip))
    sliced = all_docs[start : start + max(0, int(limit))]
    return {
        "total": total,
        "returned": len(sliced),
        "decisions": [_normalize_doc(d) for d in sliced],
    }
