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
_ISO_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
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
    """Normalise un document Sinequa — métadonnées comprises.

    Sinequa expose le numéro, la date, l'ECLI et la formation dans des
    champs `Source*` que le code jetait : chaque résultat sortait donc avec
    `title = "Conseil d'État"` (identique pour tous), sans date ni numéro,
    et il fallait télécharger le texte intégral de chaque résultat pour
    savoir ce qu'on avait sous les yeux. Constaté le 23 août 2026.
    """
    extracts = _clean_extract(doc.get("Extracts", "") or "")
    # Affaires jointes : Sinequa colle les numéros (« 487762;487834;497966 »).
    numeros = [n for n in re.split(r"[;,\s]+",
               str(doc.get("SourceCsv1") or doc.get("SourceStr5") or "")) if n]
    numero = ", ".join(numeros)
    ecli = str(doc.get("SourceStr30") or "").strip()
    # SourceDateTime1 = date de lecture, « 2024-10-23 02:00:00 »
    raw_date = str(doc.get("SourceDateTime1") or "").strip()
    date = raw_date[:10] if _ISO_PREFIX_RE.match(raw_date) else ""
    if not date and ecli:
        m = _ARIANE_ECLI_DATE_RE.search(ecli)
        if m:
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    title = (doc.get("Title") or "").strip()
    # ArianeWeb intitule TOUT « Conseil d'État » : sans le numéro, une liste
    # de résultats est une liste de lignes identiques.
    if numeros and title in ("", "Conseil d'État", "Conseil dÉtat", "Conseil d'Etat"):
        autres = len(numeros) - 1
        suffixe = (f" (et {autres} affaire{'s' if autres > 1 else ''} "
                   f"jointe{'s' if autres > 1 else ''})") if autres else ""
        title = f"Conseil d'État, n° {numeros[0]}{suffixe}"
    return {
        "id": doc.get("Id"),
        "index": doc.get("Index"),
        "rank": doc.get("Rank"),
        "relevance": doc.get("Relevance"),
        "title": title,
        "numero": numero,
        "date": date,
        "ecli": ecli,
        "formation": str(doc.get("SourceStr7") or "").strip(),
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
    skip = max(0, int(skip))
    limit = max(0, int(limit))
    # ⚠️ `SkipCount` ne saute RIEN malgré son nom : c'est le NOMBRE de
    # documents que Sinequa consent à renvoyer (SkipCount=40 → les 40
    # premiers ; SkipCount=0 → la totalité). Vérifié le 23 août 2026 sur
    # « éolienne » : 0→434 docs, 20→20 docs, 40→40 docs, tous à partir du
    # premier. Le code le prenait pour un décalage ET re-tranchait ensuite
    # à la même profondeur : pour offset=20 il demandait les 20 premiers
    # puis en prenait la tranche [20:40] — vide. Toute page au-delà de la
    # première était donc inatteignable, alors que la réponse annonçait
    # `truncated: true` et invitait à boucler.
    # Corollaire : demander exactement `skip + limit` au lieu de 0 évite de
    # télécharger l'intégralité du jeu de résultats à chaque appel.
    want = max(1, skip + limit)
    params = {
        "type": "json",
        "SourceStr4": "AW_DCE",
        "text.add": query,
        "SkipCount": want,
    }
    r = await client.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    total = data.get("TotalCount", 0)
    all_docs = data.get("Documents") or []
    # Le découpage reste côté client : Sinequa sert toujours depuis le
    # premier document. L'ensemble des N premiers est stable d'un appel à
    # l'autre (vérifié), seul l'ordre interne à la page peut varier.
    sliced = all_docs[skip : skip + limit]
    return {
        "total": total,
        "returned": len(sliced),
        "decisions": [_normalize_doc(d) for d in sliced],
    }
