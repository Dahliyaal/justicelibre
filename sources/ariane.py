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
    # Le serveur renvoie souvent iso-8859-1 — forcer le décodage propre
    if "charset=iso-8859-1" in (r.headers.get("content-type") or "").lower():
        r.encoding = "iso-8859-1"
    html = r.text
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
