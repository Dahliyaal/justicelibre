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

# --- En-tête « long » : juridiction, publication, formation, président,
# --- rapporteur. Ajoutés le 8 septembre 2026 (rapport M, § 13) : ces cinq
# --- mentions sont en clair dans les 200 premiers caractères de CHAQUE
# --- décision ArianeWeb et n'étaient extraites nulle part.
#
# La zone d'en-tête s'arrête à « REPUBLIQUE FRANCAISE » : au-delà commence le
# corps de l'arrêt, où « rapporteur » et « président » réapparaissent dans des
# phrases (« le rapporteur public a conclu … ») et donneraient des faux.
_ARIANE_FIN_ENTETE_RE = re.compile(
    r"R[EÉ]PUBLIQUE\s+FRAN[CÇ]AISE|AU\s+NOM\s+DU\s+PEUPLE", re.IGNORECASE)
_ARIANE_ENTETE_MAX = 1500

_ARIANE_JURIDICTION_RE = re.compile(
    r"(Conseil d['’]\s?[EÉ]tat"
    r"|Cour administrative d['’]appel de [A-ZÉÈ][\w'’\- ]{2,30}"
    r"|Tribunal administratif de [A-ZÉÈ][\w'’\- ]{2,30}"
    r"|Tribunal des conflits)")

# Le corpus contient une coquille de la source : « Mentionné AU tables ».
_ARIANE_PUBLICATION_RE = re.compile(
    r"(Publi[ée] au recueil Lebon"
    r"|Mentionn[ée] au[x]? tables du recueil Lebon"
    r"|In[ée]dit au recueil Lebon)", re.IGNORECASE)

# « M. Stirn, président » — on borne à ce qui précède sur la même ligne, sans
# virgule : sinon la capture remonte jusqu'au début de l'en-tête.
#
# ⚠️ Le féminin est écrit en toutes lettres depuis ~2020 (« présidente »,
# « rapporteure », « rapporteure publique ») : un `président\b` nu manque
# ces lignes-là en silence (20 rapporteures et 6 présidentes ratées sur
# 1 527 en-têtes lors du premier essai).
_ARIANE_PRESIDENT_RE = re.compile(r"([^\n,;]{2,60}?)\s*,\s*pr[ée]sidente?\b")
# « M. Brice Bohuon, rapporteur » — mais JAMAIS « …, rapporteur public », qui
# désigne une autre personne (l'ancien commissaire du gouvernement).
_ARIANE_RAPPORTEUR_RE = re.compile(
    r"([^\n,;]{2,60}?)\s*,\s*rapporteure?\b(?!\s*publi)")
_ARIANE_RAPPORTEUR_PUBLIC_RE = re.compile(
    r"([^\n,;]{2,60}?)\s*,\s*rapporteure?\s+publi(?:c|que)\b")

# Formations rencontrées dans le fonds (sondage du 8/09/2026 sur 2 027
# en-têtes réels) : « Section du Contentieux », « 6 SS », « 1 / 4 SSR »,
# « 3ème - 8ème chambres réunies », « 4ème chambre », « Juge des référés »,
# « PRESIDENT DE LA SECTION DU CONTENTIEUX », « Assemblée ».
_ARIANE_FORMATION_RE = re.compile(
    r"(Assembl[ée]e(?:\s+du\s+contentieux)?"
    r"|Section du Contentieux"
    r"|PRESIDENT DE LA SECTION DU CONTENTIEUX"
    r"|Juge des r[ée]f[ée]r[ée]s"
    r"|\d+\s*/\s*\d+\s*SSR?"
    r"|\d+\s*SSR?\b"
    r"|\d+\s*[a-zè]{0,3}\s*(?:-|et|/)\s*\d+\s*[a-zè]{0,3}\s*(?:chambres|sous-sections)"
    r"(?:\s+r[ée]unies)?"
    r"|\d+\s*[a-zè]{0,3}\s*(?:chambre|sous-section)"
    r"(?:\s+jugeant\s+seule)?)", re.IGNORECASE)

_ARIANE_ROLE_LIGNE_RE = re.compile(
    r",\s*(?:pr[ée]sidente?|rapporteure?(?:\s+publi(?:c|que))?|avocats?)\s*$",
    re.IGNORECASE)


def entete(text: str) -> str:
    """Renvoie la seule zone d'en-tête d'une décision ArianeWeb.

    Tout ce qui suit « REPUBLIQUE FRANCAISE » est le corps de l'arrêt : y
    chercher « président » ou « rapporteur » ramène des phrases, pas des noms.
    """
    if not text:
        return ""
    zone = text[:_ARIANE_ENTETE_MAX]
    fin = _ARIANE_FIN_ENTETE_RE.search(zone)
    return zone[: fin.start()] if fin else zone


def parse_header(text: str) -> dict[str, str]:
    """Extrait les métadonnées de l'en-tête d'un arrêt ArianeWeb.

    Le plugin Sinequa ne renvoie QUE du texte brut : ni le numéro, ni la date
    ne sont exposés en champ. Sans cette extraction, les enregistrements
    ArianeWeb arrivent avec `numero`/`date`/`ecli` vides alors que l'en-tête
    du texte les contient (« Conseil d'État  N° 454852
    ECLI:FR:CEORD:2021:454852.20210727 … Lecture du mardi 27 juillet 2021 »).

    Deux sources pour la date : l'ECLI (fiable, mais absent des arrêts
    anciens) puis la mention « Lecture du … » en toutes lettres.

    Clés renvoyées (toutes facultatives — une clé absente signifie
    « introuvable », jamais « vide ») : `numero`, `ecli`, `date`,
    `juridiction`, `publication`, `formation`, `president`, `rapporteur`,
    `rapporteur_public`.

    ⚠️ `numero`, `ecli` et `date` sont cherchés dans TOUT le texte (comportement
    d'origine, préservé) ; les cinq mentions ajoutées le 8/09/2026 sont
    cherchées dans la seule zone d'en-tête (cf. `entete`).
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

    zone = entete(text)
    m = _ARIANE_JURIDICTION_RE.search(zone)
    if m:
        out["juridiction"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = _ARIANE_PUBLICATION_RE.search(zone)
    if m:
        out["publication"] = re.sub(r"\s+", " ", m.group(1)).strip()
    for cle, motif in (("president", _ARIANE_PRESIDENT_RE),
                       ("rapporteur", _ARIANE_RAPPORTEUR_RE),
                       ("rapporteur_public", _ARIANE_RAPPORTEUR_PUBLIC_RE)):
        pm = motif.search(zone)
        if pm:
            nom = re.sub(r"\s+", " ", pm.group(1)).strip()
            if nom:
                out[cle] = nom
    formation = _formation(zone, out.get("publication", ""))
    if formation:
        out["formation"] = formation
    return out


def _formation(zone: str, publication: str) -> str:
    """La formation est la ligne qui SUIT la mention de publication.

    C'est la règle de mise en page d'ArianeWeb, et elle attrape les libellés
    hors catalogue (« 7ème sous-section jugeant seule »). Repli sur un
    catalogue de motifs quand l'en-tête arrive sur une seule ligne (cas des
    textes déjà ré-espacés) ou quand la publication manque.
    """
    lignes = [ligne.strip() for ligne in zone.split("\n")]
    lignes = [ligne for ligne in lignes if ligne]
    if publication:
        for i, ligne in enumerate(lignes[:-1]):
            if publication.lower() not in ligne.lower():
                continue
            suivante = lignes[i + 1]
            # La ligne suivante est parfois déjà un rôle (« M. X, président »)
            # quand la formation manque : ne pas la prendre pour une formation.
            if _ARIANE_ROLE_LIGNE_RE.search(suivante):
                break
            if len(suivante) <= 80 and not suivante.lower().startswith("lecture"):
                return re.sub(r"\s+", " ", suivante)
            break
    m = _ARIANE_FORMATION_RE.search(zone)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


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
