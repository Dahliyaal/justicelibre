"""justicelibre — MCP server exposing free access to French administrative
case law.

Two data sources, both zero-auth, legally redistributable under Licence
Ouverte 2.0:

  - opendata.justice-administrative.fr (hidden Elasticsearch) — covers
    Conseil d'État, 9 cours administratives d'appel, and 40 tribunaux
    administratifs including overseas. Roughly 1,050,000 decisions as of
    April 2026.

  - conseil-etat.fr/xsearch (ArianeWeb Sinequa) — richest index for Conseil
    d'État decisions of jurisprudential interest (~270k with highlights).

Phase A: stdio transport, run locally via `mcp dev server.py` or wire it
into Claude Desktop / Cursor / any MCP client.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from sources import ariane, dila, european, judilibre, juriadmin

mcp = FastMCP(
    "justicelibre",
    instructions="""Protocole d'accès libre à la jurisprudence française et européenne.

SIX SOURCES DISTINCTES, chacune assortie de contraintes propres :

1. ArianeWeb — outil : `search_conseil_etat`.
   ~270 000 décisions du Conseil d'État. Moteur sémantique Sinequa (scoring
   de pertinence + extraits en surbrillance). Identifiants retournés au
   format `/Ariane_Web/AW_DCE/|XXXXXX` — INOPÉRANTS pour les outils
   `get_decision_*`.

2. Open Data Justice administrative — outils : `search_juridiction`,
   `search_all_tribunaux_admin`, `search_all_cours_appel`,
   `get_decision_text`, `list_juridictions`.
   Décisions du CE + 9 CAA + 40 TA (incluant l'outre-mer) depuis ~2022.
   Recherche Elasticsearch, résultats triés chronologiquement.
   Identifiants `DCE_*`, `DTA_*`, `DCAA_*` — compatibles avec
   `get_decision_text`.

3. DILA judiciaire (archives libres) — outils : `search_judiciaire_libre`,
   `get_decision_judiciaire_libre`. Index local SQLite FTS5 des archives
   DILA : ~620 000 décisions (Cour de cassation + 36 Cours d'appel +
   Conseil constitutionnel). Aucune authentification requise.

4. PISTE Judilibre — outils : `search_judiciaire`, `get_decision_judiciaire`.
   Couvre les décisions les plus récentes non encore archivées par la DILA.
   Nécessite des identifiants OAuth2 PISTE (gratuits).

5. HUDOC (Cour EDH) — outils : `search_cedh`, `get_decision_cedh`.
   Index local des ~76 000 documents HUDOC en français. Libre d'accès.

6. EUR-Lex (CJUE) — outils : `search_cjue`, `get_decision_cjue`.
   Index local des décisions de la CJUE, du Tribunal UE et des conclusions
   d'avocats généraux. Libre d'accès.

PROTOCOLE D'USAGE : initier toute session par la consultation de
`about_justicelibre` pour récupérer la cartographie complète. Privilégier
systématiquement les bases libres (DILA, HUDOC, EUR-Lex, Open Data admin) ;
ne recourir à l'API PISTE qu'en dernière instance, pour les décisions
judiciaires récentes absentes de la base libre. Consulter
`list_juridictions` en amont de tout filtrage par cour administrative
précise.
""",
)

# Stats counter
_STATS_PATH = Path("/var/www/justicelibre/stats.json")
_STATS_LOCK = threading.Lock()
_STATS = {"total": 0, "today": 0, "today_date": "", "per_tool": {}, "last_call": None}
_START_TIME = time.monotonic()


def _load_stats():
    global _STATS
    try:
        if _STATS_PATH.exists():
            with open(_STATS_PATH) as f:
                saved = json.load(f)
            _STATS["total"] = saved.get("total", 0)
            _STATS["today"] = saved.get("today", 0)
            _STATS["today_date"] = saved.get("today_date", "")
            _STATS["per_tool"] = saved.get("per_tool", {})
            _STATS["last_call"] = saved.get("last_call")
    except Exception:
        pass


def _save_stats():
    try:
        paris = timezone(timedelta(hours=2))
        now = datetime.now(paris)
        elapsed = int(time.monotonic() - _START_TIME)
        hours, rem = divmod(elapsed, 3600)
        mins = rem // 60
        data = {
            "total": _STATS["total"],
            "today": _STATS["today"],
            "today_date": _STATS["today_date"],
            "per_tool": _STATS["per_tool"],
            "last_call": _STATS["last_call"],
            "server_status": "active",
            "uptime": f"{hours}h {mins:02d}m",
        }
        _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATS_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _record_call(tool_name: str):
    paris = timezone(timedelta(hours=2))
    now = datetime.now(paris)
    today_str = now.strftime("%Y-%m-%d")
    with _STATS_LOCK:
        if _STATS["today_date"] != today_str:
            _STATS["today"] = 0
            _STATS["today_date"] = today_str
        _STATS["total"] += 1
        _STATS["today"] += 1
        _STATS["per_tool"][tool_name] = _STATS["per_tool"].get(tool_name, 0) + 1
        _STATS["last_call"] = now.strftime("%Y-%m-%d %H:%M:%S")
        _save_stats()


_load_stats()

# ─── SESSION TOKEN STORE (vestiaire) ─────────────────────────────
# Users exchange PISTE credentials on the website for a temporary
# justicelibre session token. The token resolves to a cached PISTE
# Bearer token server-side. Credentials never touch the LLM chat.
# Tokens auto-expire after 1 hour (RGPD).

import uuid as _uuid

_SESSION_STORE: dict[str, dict[str, Any]] = {}
_SESSION_LOCK = threading.Lock()
_SESSION_TTL = 3600  # 1 hour


def _cleanup_sessions():
    now = time.time()
    with _SESSION_LOCK:
        expired = [k for k, v in _SESSION_STORE.items() if now > v["expires"]]
        for k in expired:
            del _SESSION_STORE[k]


def _create_session(piste_bearer: str, client_id_prefix: str) -> str:
    _cleanup_sessions()
    token = str(_uuid.uuid4())
    with _SESSION_LOCK:
        _SESSION_STORE[token] = {
            "bearer": piste_bearer,
            "created": time.time(),
            "expires": time.time() + _SESSION_TTL,
            "client_prefix": client_id_prefix[:8],
        }
    return token


def _resolve_session(session_token: str) -> str | None:
    # Check in-memory first
    _cleanup_sessions()
    with _SESSION_LOCK:
        session = _SESSION_STORE.get(session_token)
        if session and time.time() < session["expires"]:
            return session["bearer"]
    # Check file-based store (from token_server.py)
    try:
        with open("/tmp/justicelibre_sessions.json") as f:
            file_sessions = json.load(f)
        sess = file_sessions.get(session_token)
        if sess and time.time() < sess["expires"]:
            return sess["bearer"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_HEADERS = {
    "User-Agent": "justicelibre/0.1 (+https://justicelibre.org)",
    "Accept": "application/json",
}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True
    )


@mcp.tool()
async def about_justicelibre() -> dict[str, Any]:
    """Vue d'ensemble du protocole JusticeLibre : cartographie des sources
    et règles d'acheminement.

    Appeler cet outil en priorité pour appréhender la matrice de
    compatibilité des identifiants, les périmètres de recherche de chaque
    juridiction, et les spécificités des bases de données exploitées.
    """
    _record_call("about_justicelibre")
    return {
        "mission": (
            "Accès gratuit à la jurisprudence française et européenne, "
            "pour contourner les paywalls des outils juridiques commerciaux "
            "(Dalloz, Doctrine, Lexis, Pappers Justice)."
        ),
        "sources": {
            "1_arianeweb": {
                "tools": ["search_conseil_etat"],
                "volume": "~270 000 décisions du Conseil d'État",
                "strengths": "Moteur sémantique Sinequa (scoring de pertinence, extraits en surbrillance). Seul outil disposant d'un véritable algorithme de pertinence — à privilégier pour le droit public.",
                "id_format": "/Ariane_Web/AW_DCE/|XXXXXX",
                "id_compatible_with": "(aucun get_decision_* — procéder à une ré-indexation via search_juridiction, cf. docstring)",
            },
            "2_opendata_admin": {
                "tools": ["search_juridiction", "search_all_tribunaux_admin", "search_all_cours_appel", "get_decision_text", "list_juridictions"],
                "volume": "~1 050 000 décisions : Conseil d'État + 9 CAA + 40 TA (incluant l'outre-mer)",
                "strengths": "Recherche Elasticsearch, tri chronologique (et non par pertinence). Outil optimal lorsque la cour et la période sont préalablement identifiées.",
                "id_format": "DCE_XXX_YYYYMMDD, DTA_XXX_YYYYMMDD, DCAA_XXX_YYYYMMDD",
                "id_compatible_with": "get_decision_text",
            },
            "3_dila_judiciaire": {
                "tools": ["search_judiciaire_libre", "get_decision_judiciaire_libre"],
                "volume": "~620 000 décisions : Cour de cassation + 36 Cours d'appel + Conseil constitutionnel",
                "strengths": "Index local SQLite FTS5 — aucune authentification requise. Support des opérateurs FTS5 (phrase exacte, AND, OR, préfixe*).",
                "id_format": "JURITEXT*, CONSTEXT*, JURI*",
                "id_compatible_with": "get_decision_judiciaire_libre",
            },
            "4_piste_judilibre": {
                "tools": ["search_judiciaire", "get_decision_judiciaire"],
                "volume": "Intégralité du corpus Judilibre (inclut les décisions récentes non encore archivées par la DILA)",
                "strengths": "Fraîcheur temporelle, mais soumise à authentification OAuth2 PISTE (gratuite — inscription environ 15 min).",
                "id_format": "variables (selon Judilibre)",
                "id_compatible_with": "get_decision_judiciaire",
            },
            "5_cedh": {
                "tools": ["search_cedh", "get_decision_cedh"],
                "volume": "~76 000 documents HUDOC en français (arrêts, décisions, rapports de Chambre, Grande Chambre, Comité)",
                "strengths": "Cour européenne des droits de l'homme. Libre d'accès.",
                "id_format": "001-XXXXXX (itemid HUDOC)",
                "id_compatible_with": "get_decision_cedh",
            },
            "6_cjue": {
                "tools": ["search_cjue", "get_decision_cjue"],
                "volume": "~40 000+ arrêts CJUE, Tribunal UE et conclusions d'avocats généraux en français",
                "strengths": "Cour de justice de l'Union européenne. Libre d'accès.",
                "id_format": "6XXXXCJXXXX (CELEX) ou ECLI",
                "id_compatible_with": "get_decision_cjue",
            },
        },
        "workflow_recommande": [
            "1. Initier toute recherche par `search_conseil_etat` (droit public) ou `search_judiciaire_libre` (droit privé), seuls moteurs dotés d'un scoring sémantique.",
            "2. En cas de filtrage par cour administrative : consulter `list_juridictions` pour récupérer les codes normés, puis invoquer `search_juridiction`.",
            "3. Pour l'extraction du texte intégral : invoquer le `get_decision_*` correspondant au format de l'identifiant retourné (voir matrice supra).",
            "4. Pour le droit de l'Union et les droits fondamentaux : compléter par `search_cjue` et `search_cedh`.",
        ],
        "licence": "Licence Ouverte 2.0 (Etalab). Redistribution libre avec mention source + date.",
        "github": "https://github.com/Dahliyaal/justicelibre",
        "site": "https://justicelibre.org",
    }


@mcp.tool()
async def list_juridictions() -> dict[str, Any]:
    """Référentiel exhaustif des codes juridictionnels.

    Restitue les 51 instances couvertes (Conseil d'État, 9 CAA, 40 TA,
    incluant les juridictions d'outre-mer) accompagnées de leur nomenclature
    canonique.

    Consulter impérativement cette liste pour déterminer le code exact à
    fournir à l'outil `search_juridiction`.
    """
    _record_call("list_juridictions")
    return {
        "conseil_etat": juriadmin.CONSEIL_ETAT,
        "cours_administratives_appel": juriadmin.COURS_ADMIN_APPEL,
        "tribunaux_administratifs": juriadmin.TRIBUNAUX_ADMIN,
        "total_courts": (
            len(juriadmin.CONSEIL_ETAT)
            + len(juriadmin.COURS_ADMIN_APPEL)
            + len(juriadmin.TRIBUNAUX_ADMIN)
        ),
    }


@mcp.tool()
async def search_conseil_etat(query: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Recherche sémantique ciblée sur la jurisprudence du Conseil d'État
    (base ArianeWeb, ~270 000 décisions).

    Moteur exclusif disposant d'un véritable algorithme de pertinence
    (Sinequa) avec extraction de contexte. À privilégier systématiquement
    pour le droit public.

    ATTENTION : les identifiants retournés (format
    `/Ariane_Web/AW_DCE/|XXXXXX`) sont inopérants pour l'extraction de
    texte. Pour récupérer l'intégralité d'un arrêt, ré-indexer la recherche
    via `search_juridiction` (paramètre `juridiction="CE"` et un extrait de
    la requête) afin d'obtenir un identifiant compatible
    (`DCE_XXX_YYYYMMDD`).

    Consigne de recherche : limiter les requêtes à 2-5 mots-clés
    distinctifs ; les requêtes en phrase complète retournent généralement
    zéro résultat.

    Args:
        query: mots-clés de recherche (ex : "référé liberté", "QPC 145")
        limit: nombre maximum de résultats (défaut 20)
        offset: décalage pour paginer (défaut 0). Réitérer avec offset=20,
            offset=40, etc. pour obtenir les pages suivantes.
    """
    _record_call("search_conseil_etat")
    async with _client() as client:
        return await ariane.search(client, query=query, limit=limit, skip=offset)


@mcp.tool()
async def search_juridiction(
    query: str,
    juridiction: str = "CE",
    limit: int = 20,
) -> dict[str, Any]:
    """Recherche textuelle exhaustive au sein d'une juridiction
    administrative ciblée (API opendata.justice-administrative.fr).

    À noter : le tri s'effectue par ordre chronologique décroissant et non
    par pertinence sémantique. Outil optimal lorsque la cour et la période
    de la décision sont préalablement identifiées. Pour une recherche
    pondérée par la pertinence sémantique, recourir à `search_conseil_etat`
    (moteur Sinequa).

    Périmètre : CE + 9 CAA + 40 TA (incluant l'outre-mer), depuis ~2022.

    Les identifiants générés (formats `DCE_*`, `DTA_*`, `DCAA_*`) sont
    nativement compatibles avec l'outil `get_decision_text`.

    Args:
        query: mots-clés de recherche
        juridiction: code de la juridiction. Exemples :
            - "CE" — Conseil d'État
            - "CE-CAA" — Conseil d'État + cours administratives d'appel
            - "TA69" — Tribunal administratif de Lyon
            - "TA75" — Tribunal administratif de Paris
            - "CAA69" — Cour administrative d'appel de Lyon
            Les codes "TA" ou "CAA" isolés retournent un résultat vide —
            un code spécifique est requis. Consulter `list_juridictions`
            pour la nomenclature complète.
        limit: nombre maximum de résultats (défaut 20)
    """
    _record_call("search_juridiction")
    async with _client() as client:
        return await juriadmin.search(
            client, query=query, juridiction=juridiction, limit=limit
        )


@mcp.tool()
async def search_all_tribunaux_admin(
    query: str,
    limit_per_court: int = 5,
    total_limit: int = 0,
) -> dict[str, Any]:
    """Requête simultanée de l'ensemble des 40 Tribunaux Administratifs.

    Fusionne et trie chronologiquement (date de lecture décroissante) les
    résultats issus du territoire national. Pertinent pour cartographier
    rapidement les éventuelles divergences d'appréciation territoriale sur
    une même question de droit.

    Args:
        query: mots-clés de recherche
        limit_per_court: nombre de résultats par tribunal (défaut 5, soit
            jusqu'à 200 résultats totaux en l'absence de `total_limit`)
        total_limit: plafond global après fusion (0 = aucun plafond). Si
            positif, tronque la liste fusionnée aux N entrées les plus
            récentes.

    Returns:
        Dict comportant `per_court_totals` (nombre de hits par TA),
        `decisions` (liste fusionnée triée chronologiquement) et les
        éventuelles `errors`.
    """
    _record_call("search_all_tribunaux_admin")
    async with _client() as client:
        result = await juriadmin.search_many(
            client,
            query=query,
            juridictions=list(juriadmin.TRIBUNAUX_ADMIN.keys()),
            limit_per_court=limit_per_court,
        )
    if total_limit and total_limit > 0:
        result["decisions"] = result["decisions"][:total_limit]
        result["total_returned"] = len(result["decisions"])
    return result


@mcp.tool()
async def search_all_cours_appel(
    query: str,
    limit_per_court: int = 5,
    total_limit: int = 0,
) -> dict[str, Any]:
    """Requête simultanée de l'ensemble des 9 Cours Administratives d'Appel.

    Fusion et tri chronologique des résultats par date de lecture.

    Args:
        query: mots-clés de recherche
        limit_per_court: résultats par cour (défaut 5, soit jusqu'à 45
            résultats au total)
        total_limit: plafond global après fusion (0 = aucun plafond).
    """
    _record_call("search_all_cours_appel")
    async with _client() as client:
        result = await juriadmin.search_many(
            client,
            query=query,
            juridictions=list(juriadmin.COURS_ADMIN_APPEL.keys()),
            limit_per_court=limit_per_court,
        )
    if total_limit and total_limit > 0:
        result["decisions"] = result["decisions"][:total_limit]
        result["total_returned"] = len(result["decisions"])
    return result


@mcp.tool()
async def get_decision_text(decision_id: str) -> dict[str, Any] | None:
    """Extraction du texte intégral d'une décision relevant de l'ordre
    administratif (Conseil d'État, TA, CAA).

    Usage strictement réservé aux identifiants normés issus des recherches
    administratives : `DCE_XXX_YYYYMMDD` (Conseil d'État),
    `DTA_XXX_YYYYMMDD` (TA), `DCAA_XXX_YYYYMMDD` (CAA).

    INCOMPATIBILITÉS MAJEURES :
    - Identifiants ArianeWeb `/Ariane_Web/AW_DCE/|XXXXXX` — procéder à une
      ré-indexation via `search_juridiction` pour obtenir un identifiant
      compatible.
    - Identifiants JURITEXT — rediriger vers `get_decision_judiciaire_libre`
      ou `get_decision_judiciaire`.
    - Identifiants CELEX `6XXXXCJXXXX` — rediriger vers `get_decision_cjue`.
    - Identifiants HUDOC `001-XXXXXX` — rediriger vers `get_decision_cedh`.

    Args:
        decision_id: identifiant de la décision (avec ou sans suffixe .xml)

    Returns:
        Dict comportant les métadonnées complètes, `text_segments` (liste
        des paragraphes) et `full_text` (texte intégral joint), ou None si
        la décision est introuvable.
    """
    _record_call("get_decision_text")
    # Detect wrong-format IDs and redirect
    if decision_id.startswith("/Ariane_Web/") or decision_id.startswith("|"):
        return {"error": (
            f"L'identifiant fourni ({decision_id!r}) relève du format ArianeWeb et n'est pas "
            "exploitable par cet outil. Procéder à une ré-indexation via `search_juridiction` "
            "(juridiction=\"CE\") assortie de mots-clés distinctifs ; un identifiant "
            "compatible au format `DCE_XXX_YYYYMMDD` sera alors disponible."
        )}
    if decision_id.startswith("JURITEXT") or decision_id.startswith("JURI"):
        return {"error": (
            f"L'identifiant fourni ({decision_id!r}) relève du format JURITEXT (ordre judiciaire). "
            "Recourir à `get_decision_judiciaire_libre(decision_id)` en remplacement."
        )}
    if decision_id.startswith(("6", "7", "8", "9")) and any(x in decision_id for x in ("CJ", "TJ", "CO", "CC")):
        return {"error": (
            f"L'identifiant fourni ({decision_id!r}) correspond à un CELEX européen. "
            "Recourir à `get_decision_cjue(decision_id)` en remplacement."
        )}
    if decision_id.startswith("001-") or decision_id.startswith("002-") or decision_id.startswith("003-"):
        return {"error": (
            f"L'identifiant fourni ({decision_id!r}) correspond à un itemid HUDOC (Cour EDH). "
            "Recourir à `get_decision_cedh(decision_id)` en remplacement."
        )}
    async with _client() as client:
        return await juriadmin.get_decision(client, decision_id=decision_id)


# ─── JUSTICE JUDICIAIRE - DILA (sans auth, index local) ──────────

@mcp.tool()
async def search_judiciaire_libre(
    query: str,
    juridiction: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Recherche plein texte dans la jurisprudence judiciaire, exécutée
    localement et affranchie de toute obligation d'authentification
    gouvernementale.

    Exploite l'index FTS5 des archives publiques DILA (~620 000 décisions :
    Cour de cassation, 36 cours d'appel, Conseil constitutionnel). Scoring
    BM25 disponible mais tri appliqué par ordre chronologique décroissant.
    Pour cibler une jurisprudence spécifique plutôt que récente, restreindre
    `limit` et privilégier des mots-clés distinctifs.

    Les identifiants retournés (format `JURITEXT*` pour Cass / cours
    d'appel, `CONSTEXT*` pour Conseil constitutionnel) sont compatibles
    avec `get_decision_judiciaire_libre`.

    Args:
        query: mots-clés (ex : "licenciement abusif", "garde enfant"). FTS5
            supporte les opérateurs : `"phrase exacte"`, `mot1 AND mot2`,
            `mot1 OR mot2`, `mot*` (préfixe).
        juridiction: filtre optionnel : "cassation" (Cour de cassation) ou
            "appel" (cours d'appel). Vide = toutes juridictions.
        limit: nombre maximum de résultats (défaut 20)
    """
    _record_call("search_judiciaire_libre")
    return dila.search(
        query=query,
        juridiction=juridiction or None,
        limit=limit,
    )


@mcp.tool()
async def get_decision_judiciaire_libre(
    decision_id: str,
) -> dict[str, Any] | None:
    """Extraction du texte intégral d'une décision judiciaire depuis l'index
    indépendant (sans authentification).

    Accepte exclusivement les identifiants judiciaires libres (formats
    `JURITEXT*`, `CONSTEXT*`, `JURI*`), tels que retournés par
    `search_judiciaire_libre` (exemples : `"JURITEXT000042579700"`,
    `"CONSTEXT000049574021"`).

    Outil formellement inopérant pour les décisions relevant de l'ordre
    administratif (formats `DCE_*`, `DTA_*`, `DCAA_*`, `/Ariane_Web/...`).

    Args:
        decision_id: identifiant JURITEXT/JURI/CONSTEXT de la décision
    """
    _record_call("get_decision_judiciaire_libre")
    if decision_id.startswith(("DCE_", "DTA_", "DCAA_")) or decision_id.startswith("/Ariane_Web/"):
        return {"error": (
            f"L'identifiant fourni ({decision_id!r}) relève de l'ordre administratif. "
            "Recourir à `get_decision_text(decision_id)` en remplacement."
        )}
    return dila.get_decision(decision_id)


# ─── JUSTICE JUDICIAIRE - BYOK PISTE OAuth2 ──────────────────────

_NO_CREDS_MSG = (
    "L'accès via PISTE requiert des identifiants OAuth2 (gratuits). "
    "Dans la majorité des cas, privilégier `search_judiciaire_libre` ou "
    "`get_decision_judiciaire_libre`, qui interrogent l'archive locale "
    "DILA (~620 000 décisions, sans authentification). Ne recourir à "
    "l'API PISTE qu'en cas de besoin avéré des toutes dernières décisions "
    "non encore archivées. Obtenir un Client ID et un Client Secret PISTE "
    "via https://justicelibre.org/tutoriel-piste.html, puis les transmettre "
    "en paramètres."
)


@mcp.tool()
async def search_judiciaire(
    query: str,
    session_token: str = "",
    client_id: str = "",
    client_secret: str = "",
    juridiction: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Recherche dans la jurisprudence judiciaire via l'API officielle PISTE
    (authentification OAuth2 requise).

    Périmètre : Cour de cassation, cours d'appel, tribunaux judiciaires,
    tribunaux de commerce. À n'utiliser qu'en dernier recours ou pour des
    décisions récentes absentes de la base libre DILA, compte tenu de
    l'entrave technique imposée par la Cour de cassation.

    Deux méthodes d'authentification disponibles :
    1. `session_token` : jeton temporaire obtenu sur
       justicelibre.org/tutoriel-piste.html (procédé recommandé, préserve
       la confidentialité des identifiants).
    2. `client_id` + `client_secret` : identifiants PISTE directs
       (transmission en chat déconseillée).

    Args:
        query: mots-clés de recherche
        session_token: jeton justicelibre temporaire (obtenu via le
            formulaire du site)
        client_id: Client ID PISTE (alternative au session_token)
        client_secret: Client Secret PISTE (alternative au session_token)
        juridiction: filtre optionnel — "cc" (Cour de cassation), "ca"
            (cours d'appel), "tj" (tribunaux judiciaires), "tcom"
            (tribunaux de commerce). Vide = toutes juridictions.
        limit: nombre maximum de résultats (défaut 20, maximum 50)
    """
    # Method 1: session token (safe, recommended)
    if session_token:
        bearer = _resolve_session(session_token)
        if not bearer:
            return {"error": "Jeton de session expiré ou invalide. En générer un nouveau sur https://justicelibre.org/tutoriel-piste.html"}
        _record_call("search_judiciaire")
        async with _client() as client:
            headers = {"Authorization": f"Bearer {bearer}"}
            params: dict[str, Any] = {"query": query, "page_size": min(int(limit), 50)}
            if juridiction and juridiction in judilibre.JURIDICTIONS:
                params["jurisdiction"] = juridiction
            r = await client.get(f"{judilibre.BASE}/search", headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            return {
                "total": data.get("total_results", 0),
                "returned": len(results),
                "decisions": [judilibre._normalize_decision(d) for d in results],
            }

    # Method 2: direct credentials (fallback)
    cid = client_id or os.environ.get("PISTE_CLIENT_ID", "")
    csec = client_secret or os.environ.get("PISTE_CLIENT_SECRET", "")
    if not cid or not csec:
        return {"error": _NO_CREDS_MSG}
    _record_call("search_judiciaire")
    async with _client() as client:
        return await judilibre.search(
            client, client_id=cid, client_secret=csec, query=query,
            juridiction=juridiction or None, limit=limit,
        )


@mcp.tool()
async def get_decision_judiciaire(
    decision_id: str,
    session_token: str = "",
    client_id: str = "",
    client_secret: str = "",
) -> dict[str, Any] | None:
    """Extraction du texte intégral d'une décision judiciaire via l'API
    restreinte PISTE (authentification OAuth2 requise).

    À substituer systématiquement par `get_decision_judiciaire_libre`
    lorsque la décision figure dans les archives ouvertes de la DILA.

    Outil formellement inopérant pour les décisions relevant de l'ordre
    administratif (formats `DCE_*`, `DTA_*`, `DCAA_*`, `/Ariane_Web/...`).

    Args:
        decision_id: identifiant Judilibre de la décision
        session_token: jeton justicelibre temporaire (recommandé)
        client_id: Client ID PISTE (alternative)
        client_secret: Client Secret PISTE (alternative)
    """
    if decision_id.startswith(("DCE_", "DTA_", "DCAA_")) or decision_id.startswith("/Ariane_Web/"):
        return {"error": (
            f"L'identifiant fourni ({decision_id!r}) relève de l'ordre administratif. "
            "Recourir à `get_decision_text(decision_id)` en remplacement."
        )}
    # Method 1: session token
    if session_token:
        bearer = _resolve_session(session_token)
        if not bearer:
            return {"error": "Jeton de session expiré ou invalide."}
        _record_call("get_decision_judiciaire")
        async with _client() as client:
            headers = {"Authorization": f"Bearer {bearer}"}
            r = await client.get(f"{judilibre.BASE}/decision", headers=headers, params={"id": decision_id})
            r.raise_for_status()
            data = r.json()
            if not data:
                return None
            return judilibre._normalize_decision(data)

    # Method 2: direct credentials
    cid = client_id or os.environ.get("PISTE_CLIENT_ID", "")
    csec = client_secret or os.environ.get("PISTE_CLIENT_SECRET", "")
    if not cid or not csec:
        return {"error": _NO_CREDS_MSG}
    _record_call("get_decision_judiciaire")
    async with _client() as client:
        return await judilibre.get_decision(client, client_id=cid, client_secret=csec, decision_id=decision_id)


# ─── COURS EUROPÉENNES (CJUE + CEDH) — index local, sans auth ────

@mcp.tool()
async def search_cedh(query: str, limit: int = 20) -> dict[str, Any]:
    """Recherche textuelle dans la jurisprudence de la Cour européenne des
    droits de l'homme.

    Exploitation de l'index localisé regroupant les ~76 000 documents
    HUDOC francophones (arrêts, décisions, rapports de Chambre, Grande
    Chambre, Comité). Libre d'accès.

    Args:
        query: mots-clés (ex : "article 8 vie familiale", "garde à vue")
        limit: nombre maximum de résultats (défaut 20)
    """
    _record_call("search_cedh")
    return european.search_cedh(query=query, limit=limit)


@mcp.tool()
async def get_decision_cedh(decision_id: str) -> dict[str, Any] | None:
    """Extraction du texte intégral d'une décision de la Cour européenne des
    droits de l'homme sur la base de son identifiant système (itemid HUDOC).

    Args:
        decision_id: itemid HUDOC (ex : "001-249914")
    """
    _record_call("get_decision_cedh")
    return european.get_cedh(decision_id)


@mcp.tool()
async def search_cjue(query: str, limit: int = 20) -> dict[str, Any]:
    """Recherche textuelle dans la jurisprudence de la Cour de justice de
    l'Union européenne.

    Exploitation de l'index localisé des décisions de la CJUE, du Tribunal
    de l'UE, des ordonnances et des conclusions des avocats généraux
    (données EUR-Lex). Libre d'accès.

    Args:
        query: mots-clés (ex : "libre circulation capitaux", "CJUE C-72/24")
        limit: nombre maximum de résultats (défaut 20)
    """
    _record_call("search_cjue")
    return european.search_cjue(query=query, limit=limit)


@mcp.tool()
async def get_decision_cjue(decision_id: str) -> dict[str, Any] | None:
    """Extraction du texte intégral d'une décision de la Cour de justice de
    l'Union européenne sur la base de son identifiant normalisé (CELEX).

    Args:
        decision_id: identifiant CELEX (ex : "62024CJ0072") ou ECLI
    """
    _record_call("get_decision_cjue")
    return european.get_cjue(decision_id)


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if mode in ("http", "streamable-http"):
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = 8765
        # Relax DNS rebinding protection so reverse proxies / dev tunnels
        # (cloudflared, ngrok, later nginx on justicelibre.org) can forward
        # requests. For production we'll pin allowed_hosts to the real domain.
        mcp.settings.transport_security.enable_dns_rebinding_protection = False
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
