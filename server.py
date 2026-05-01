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

from sources import (
    ariane, dila, european, judilibre, juriadmin, legi,
    jade_remote, jorf_remote, kali_remote, cnil_remote,
)

mcp = FastMCP(
    "justicelibre",
    instructions="""Protocole d'accès libre à la jurisprudence et au droit positif français + européen (24 tools).

TOOL D'ENTRÉE : `search_all` — recherche fédérée fan-out avec ranking BM25
+ thésaurus juridique FR automatique (ex : "harcèlement" → aussi
"intimidation", "vexation morale"). À UTILISER EN PRIORITÉ pour toute
requête floue ou multi-source.

SOURCES DE JURISPRUDENCE (pertinence BM25) :
• `search_admin` — 4 M+ décisions JADE (CE + 9 CAA + 40 TA) full text
• `search_judiciaire_libre` — 620 k+ Cass + 36 CA + Conseil constitutionnel
• `search_conseil_etat` — 270 k+ CE via Sinequa (moteur sémantique natif)
• `search_cedh` — 76 k décisions Cour EDH
• `search_cjue` — 44 k arrêts CJUE + Tribunal UE

EXTRACTION TEXTE INTÉGRAL : `get_decision_text` (admin DCE_*/DTA_*/DCAA_*),
`get_decision_judiciaire_libre` (JURITEXT*/CONSTEXT*), `get_decision_cedh`
(001-*), `get_decision_cjue` (CELEX/ECLI).

ARTICLES DE LOI (killer feature unique à justicelibre) :
• `get_law_article(code, num, date)` — version en vigueur À LA DATE donnée.
  Ex : art. 1128 CC en 1992 → texte napoléonien, pas la réforme 2016.
• `get_law_versions(code, num)` — timeline complète historique.
• `search_legi` — 1,5 M articles des 22 codes consolidés.
• `search_decisions_citing(code, num)` — cross-référence inverse.

DROIT POSITIF COMPLÉMENTAIRE :
• `search_jorf` — JO post-1990 (lois, décrets, arrêtés, circulaires)
• `search_kali` — conventions collectives + accords de branche
• `search_cnil` — délibérations CNIL (RGPD, données personnelles)

SECONDAIRES (tri date-desc, pour l'actualité d'une juridiction) :
`search_admin_recent`, `search_admin_recent_all_ta`,
`search_admin_recent_all_caa` — À éviter pour la recherche de jurisprudence
pertinente (utiliser `search_admin` qui a BM25).

PISTE JUDILIBRE (auth OAuth2) :
`search_judiciaire` + `get_decision_judiciaire` — pour les décisions
judiciaires récentes non encore archivées. Token obtenable sur
justicelibre.org/tutoriel-piste.html.

PROTOCOLE D'USAGE : pour tout doute, commencer par `about_justicelibre`
qui détaille la cartographie. Sinon : `search_all(query)` couvre 90% des
besoins. Pour les 22 codes de loi consolidés : CC, CP, CPC, CPP, CT, CSP,
CJA, CGCT, CRPA, CPI, CASF, CMF, C.com, C.cons, C.éduc, CU, C.env, CR,
CGI, CESEDA, CSS, CCH.
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
    # Check file-based store (from token_server.py). Try secure /run first,
    # fallback to legacy /tmp for backward compat during transition.
    for session_path in ("/run/justicelibre/sessions.json", "/tmp/justicelibre_sessions.json"):
        try:
            with open(session_path) as f:
                file_sessions = json.load(f)
            sess = file_sessions.get(session_token)
            if sess and time.time() < sess.get("expires", 0):
                return sess["bearer"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            continue
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
            "0_unified": {
                "tools": ["search_all"],
                "strengths": "Tool one-stop : fan-out sur DILA + JADE + LEGI + CEDH + CJUE en parallèle, tri par pertinence BM25 avec bonus d'autorité (CE/Cass/CEDH > CAA > TA/CA). Utilise le thésaurus juridique FR (expand_synonyms=True par défaut). **À utiliser en priorité** quand on ne sait pas d'avance où chercher.",
            },
            "1_arianeweb": {
                "tools": ["search_conseil_etat"],
                "volume": "~270 000 décisions du Conseil d'État",
                "strengths": "Moteur sémantique Sinequa natif (pertinence). Complémentaire à `search_admin` pour CE seulement.",
                "id_format": "/Ariane_Web/AW_DCE/|XXXXXX",
                "id_compatible_with": "(pas de get_decision_*)",
            },
            "2_admin_pertinence": {
                "tools": ["search_admin", "list_juridictions"],
                "volume": "~4M décisions JADE : CE + 9 CAA + 40 TA full text",
                "strengths": "Ranking BM25 (vraie pertinence) + snippets + date range. REMPLACE les tools date-sorted pour trouver la jurisprudence pertinente.",
                "id_format": "DCE_*, DTA_*, DCAA_*",
                "id_compatible_with": "get_decision_text",
            },
            "2b_admin_recent": {
                "tools": ["search_admin_recent", "search_admin_recent_all_ta", "search_admin_recent_all_caa", "get_decision_text"],
                "strengths": "API live opendata.justice-administrative.fr, tri chronologique. Pour voir les décisions les plus récentes (actu), pas pour trouver du pertinent — utiliser `search_admin` à la place.",
            },
            "3_dila_judiciaire": {
                "tools": ["search_judiciaire_libre", "get_decision_judiciaire_libre"],
                "volume": "~620 000 décisions : Cour de cassation + 36 Cours d'appel + Conseil constitutionnel (archives DILA locales)",
                "strengths": "Index local FTS5, aucune auth. Opérateurs FTS5 (phrase exacte, AND, OR, préfixe*).",
                "id_format": "JURITEXT*, CONSTEXT*, JURI*",
                "id_compatible_with": "get_decision_judiciaire_libre",
            },
            "4_piste_judilibre": {
                "tools": ["search_judiciaire", "get_decision_judiciaire"],
                "volume": "Corpus Judilibre live (décisions récentes non encore archivées par DILA)",
                "strengths": "Fraîcheur, mais auth OAuth2 PISTE requise (token temporaire obtenable sur justicelibre.org/tutoriel-piste.html).",
                "id_format": "variables Judilibre",
                "id_compatible_with": "get_decision_judiciaire",
            },
            "5_cedh": {
                "tools": ["search_cedh", "get_decision_cedh"],
                "volume": "~76 000 documents HUDOC FR",
                "strengths": "Cour européenne des droits de l'homme. Libre d'accès.",
                "id_format": "001-XXXXXX",
                "id_compatible_with": "get_decision_cedh",
            },
            "6_cjue": {
                "tools": ["search_cjue", "get_decision_cjue"],
                "volume": "~44 000 arrêts CJUE + Tribunal UE + conclusions AG",
                "strengths": "Libre d'accès.",
                "id_format": "6XXXXCJXXXX (CELEX) / ECLI",
                "id_compatible_with": "get_decision_cjue",
            },
            "7_articles_loi": {
                "tools": ["get_law_article", "get_law_versions", "search_legi", "search_decisions_citing"],
                "volume": "~3,6 Go bulk LEGI : 22 codes consolidés (CC, CP, CT, etc.) AVEC toutes les versions historiques",
                "strengths": "**Killer feature** : récupérer un article à sa version en vigueur à une date précise. Ex: art. 1128 CC en 1992 → texte napoléonien ; en 2024 → texte réforme 2016. Ce que Dalloz facture 200€/mois.",
                "id_format": "LEGIARTI*",
                "id_compatible_with": "get_law_article / get_law_versions",
            },
            "8_jorf": {
                "tools": ["search_jorf"],
                "volume": "~1,1 Go JO post-1990 : lois non codifiées, décrets, arrêtés, circulaires, ordonnances",
                "strengths": "Textes publiés au Journal Officiel en dehors des codes consolidés.",
                "id_format": "JORFTEXT*",
            },
            "9_kali": {
                "tools": ["search_kali"],
                "volume": "Conventions collectives + accords de branche (745 Mo)",
                "strengths": "Droit du travail sectoriel. Filtrable par IDCC.",
            },
            "10_cnil": {
                "tools": ["search_cnil"],
                "volume": "~26 000 délibérations CNIL",
                "strengths": "Droit des données personnelles (RGPD).",
            },
        },
        "hiérarchie_autorité": {
            "principe": "En cas de divergence ou d'arbitrage, classer les décisions selon leur autorité jurisprudentielle.",
            "ordre": [
                "CJUE (primauté du droit UE)",
                "Conseil constitutionnel (constitutionnalité)",
                "Cour EDH (conventionnalité)",
                "Cour de cassation (judiciaire national)",
                "Conseil d'État (administratif national)",
                "Cours d'appel / Cours administratives d'appel (appel)",
                "Tribunaux de première instance (TA, TJ, etc.)",
            ],
            "note": "`search_all` applique automatiquement un bonus d'autorité lors du tri.",
        },
        "workflow_recommande": [
            "1. **Query floue, on ne sait pas où** → `search_all(query)` : fan-out + pertinence + thésaurus FR.",
            "2. **Query précise sur un type de source** → `search_admin` (admin BM25), `search_judiciaire_libre` (Cass/CA archives), `search_cedh`, `search_cjue`, `search_legi` (articles de loi).",
            "3. **Article de loi cité dans une décision** → `get_law_article(code, num, date)` avec la date de la décision pour la version d'époque.",
            "4. **Timeline d'un article** → `get_law_versions(code, num)`.",
            "5. **Cross-référencement article ↔ décisions** → `search_decisions_citing(code, num)`.",
            "6. **Texte intégral d'une décision identifiée** → `get_decision_*` selon format ID.",
            "7. **Actualité récente d'une juridiction** → `search_admin_recent*` (tri date).",
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
    fournir à l'outil `search_admin`.
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
    via `search_admin` (paramètre `juridiction="CE"` et un extrait de
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
async def search_admin_recent(
    query: str,
    juridiction: str = "CE",
    limit: int = 20,
) -> dict[str, Any]:
    """Décisions admin **récentes** triées chronologiquement (API live).

    Priorité au récent : tri par date de lecture décroissante, pas par
    pertinence. Utile pour "actualité d'une juridiction" mais PAS pour
    trouver la jurisprudence pertinente sur un sujet — pour cela, utiliser
    `search_admin` (bulk JADE avec BM25 ranking).

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
    _record_call("search_admin_recent")
    async with _client() as client:
        return await juriadmin.search(
            client, query=query, juridiction=juridiction, limit=limit
        )


@mcp.tool()
async def search_admin_recent_all_ta(
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
    _record_call("search_admin_recent_all_ta")
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
async def search_admin_recent_all_caa(
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
    _record_call("search_admin_recent_all_caa")
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
      ré-indexation via `search_admin` pour obtenir un identifiant
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
            "exploitable par cet outil. Procéder à une ré-indexation via `search_admin` "
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
            return {
                "error": "Jeton de session expiré ou invalide.",
                "fallback": "Si la décision recherchée a plus de ~2 ans, utiliser `search_judiciaire_libre` (base DILA locale, sans authentification) avant de tenter de régénérer un token.",
                "regenerate_token_url": "https://justicelibre.org/tutoriel-piste.html",
            }
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
            return {
                "error": "Jeton de session expiré ou invalide.",
                "fallback": "Tenter `get_decision_judiciaire_libre` avec le même ID si la décision existe dans les archives DILA.",
                "regenerate_token_url": "https://justicelibre.org/tutoriel-piste.html",
            }
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
async def resolve_law_number(numero: str) -> dict[str, Any]:
    """Résout un numéro de loi/ordonnance/décret vers son identifiant LEGITEXT
    ou JORFTEXT Légifrance.

    Utile pour les textes non codifiés (lois, ordonnances, décrets) qui ne
    sont pas dans la whitelist des 25 codes courts (CC, CP, LIL, LO58, etc.).
    Une fois le LEGITEXT/JORFTEXT résolu, on peut l'utiliser avec
    `get_law_article(code=<LEGITEXT>, num=<N>)` pour récupérer un article
    spécifique.

    Exemples :
    - `resolve_law_number("68-1250")` → loi prescription quadriennale des
      créances publiques (JORFTEXT000000878035)
    - `resolve_law_number("79-587")` → loi motivation des actes admin
    - `resolve_law_number("2000-321")` → loi droits citoyens face à l'admin

    Args:
        numero: format "YY-NNNN" ou "YYYY-NNNN" (ex: "68-1250", "2000-321")

    Returns:
        `{numero, legitext, titre_section, date_debut, articles_count, source_url}`
        ou `{error}` si introuvable.
    """
    _record_call("resolve_law_number")
    return await legi.resolve_number(numero)


@mcp.tool()
async def build_source_url(identifier: str, legitext: str = "", date: str = "") -> dict[str, Any]:
    """Construit l'URL canonique d'un document à partir de son identifiant.

    Utile pour vérifier les sources à la main sur le site officiel (Légifrance,
    Conseil constitutionnel, EUR-Lex, HUDOC, etc.) ou pour inclure un lien
    cliquable dans un courrier.

    Identifiants reconnus :
    - `LEGIARTI*` → Légifrance article (passer `legitext` du texte parent
      pour distinguer code (/codes/) vs loi non codifiée (/loda/)
    - `LEGITEXT*` / `JORFTEXT*` → texte entier Légifrance
    - `JURITEXT*` / `CONSTEXT*` / `CETATEXT*` → décisions Légifrance
    - CELEX (`6XXXXCJXXXX`) → EUR-Lex (CJUE)
    - `ECLI:*` → EUR-Lex deeplink
    - itemid HUDOC (`001-XXXXXX`) → Cour EDH
    - ArianeWeb (`/Ariane_Web/AW_DCE/|XXXXXX`) → conseil-etat.fr

    Args:
        identifier: l'ID à convertir
        legitext: (optionnel) LEGITEXT du texte parent si `identifier` est un
            LEGIARTI — améliore la précision de l'URL (codes/ vs loda/)
        date: (optionnel, YYYY-MM-DD) — appendé à l'URL Légifrance pour pointer
            vers la version de l'article en vigueur à cette date
            (ex: `/loda/article_lc/LEGIARTI.../2023-01-01`). Indispensable pour
            vérifier l'état du droit à une date historique, sinon Légifrance
            affiche la version courante même si l'article a été abrogé depuis.

    Returns:
        `{"id", "source_url"}` ou `{"error"}` si format non reconnu.
    """
    _record_call("build_source_url")
    if not identifier.strip():
        return {"error": "identifier requis"}
    from sources import warehouse as wh
    url = await wh.build_url(identifier, legitext or None, date or None)
    if not url:
        return {"error": f"format d'identifiant non reconnu : {identifier!r}"}
    return {"id": identifier, "source_url": url}


@mcp.tool()
async def get_cc_decision(numero: str, nature: str = "") -> dict[str, Any] | None:
    """Récupère une décision du Conseil constitutionnel par son numéro.

    Format attendu : "AA-NNN NATURE" ou juste "AA-NNN" (ex : "79-105 DC",
    "2020-800 DC", "2023-1048 QPC"). Recherche full-text sur le numéro
    + filtre juridiction="Conseil constitutionnel" dans judiciaire.db.

    Args:
        numero: numéro de décision CC (ex : "79-105 DC")
        nature: filtre optionnel (QPC, DC, L, etc.) — cf search_cc

    Returns:
        `{id, titre, date, juridiction, nature, ecli, text}` ou None.
    """
    _record_call("get_cc_decision")
    return dila.get_cc_decision(numero, nature or None)


@mcp.tool()
async def get_ce_decision(numero: str) -> dict[str, Any] | None:
    """Récupère une décision du Conseil d'État par son numéro de pourvoi.

    Essaie d'abord le bulk JADE DILA (lookup SQL exact), puis si introuvable
    tente ArianeWeb Sinequa — les deux bases ont des couvertures complémentaires.

    Pour retrouver une décision via identifiant DCE_*, utiliser
    `get_decision_text` à la place.

    Args:
        numero: numéro de pourvoi (ex : "497566", "358109")

    Returns:
        Décision avec métadonnées, ou None si introuvable dans les deux bases.
    """
    _record_call("get_ce_decision")
    return await jade_remote.get_ce_decision(numero)


@mcp.tool()
async def get_admin_decision(numero: str, juridiction: str = "") -> dict[str, Any]:
    """Récupère une décision administrative par son **numéro de requête exact**.

    Couvre toutes les juridictions : Conseil d'État, cours administratives
    d'appel (CAA), tribunaux administratifs (TA). Utilise un lookup SQL exact
    sur le champ `numero` — pas de FTS5, pas de faux positifs.

    ⚠️ **Désambiguïsation indispensable** : un même numéro à 7 chiffres
    (ex: 2200433) est partagé par 24+ tribunaux administratifs différents
    (chaque TA a sa propre série annuelle qui repart à 1). Sans `juridiction`,
    tu obtiens un homonyme au hasard parmi 24 — souvent pas le bon. **Si tu
    sais quelle juridiction a rendu la décision, passe-la TOUJOURS.**

    Args:
        numero: numéro de requête (ex : "2200433", "2116343", "497566")
        juridiction: identifiant de la juridiction. **Recommandé pour tout
            numéro à 7 chiffres** (TA/CAA codifié). Deux formats acceptés
            (mapping bidirectionnel automatique) :
            - **Code court** (recommandé pour les LLMs) : "TA69" (Lyon),
              "TA75" (Paris), "CAA69", "CE", "CE-CAA"
            - **Nom long** : "Tribunal Administratif de Lyon", "Conseil d'Etat"
              (avec ou sans accent), match insensible à la casse
            Note : "Lyon" seul est ambigu (TA Lyon ou CAA Lyon) — préférer
            le code court ou le nom complet pour éviter la collision.

    Returns:
        Décision avec métadonnées (id, juridiction, numero, date, titre),
        ou `{"error": "introuvable"}` si aucun résultat dans JADE.

    Exemples :
        get_admin_decision("2200433", juridiction="Tribunal Administratif de Lyon")
            → DTA_2200433_20230214 (TA Lyon, 14 fév 2023, RSA dérogatoire)
        get_admin_decision("473286")  # CE n'a pas de doublon, juridiction inutile
            → DCE_473286_20231123 (CE, non-admission du pourvoi sur la précédente)
    """
    _record_call("get_admin_decision")
    result = await jade_remote.get_admin_decision(numero, juridiction or None)
    if result is None:
        return {"error": f"Décision n° {numero} introuvable dans JADE (bulk DILA). "
                         f"Si la décision est récente (< 3 mois), essayer `search_admin_recent`."}
    return result


@mcp.tool()
async def search_cc(
    query: str,
    nature: str = "",
    date_min: str = "",
    date_max: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche dédiée au **Conseil constitutionnel** (7 112 décisions).

    Quatrième pouvoir juridictionnel français aux côtés de la Cour de cassation,
    du Conseil d'État et de la Cour de justice de la République. Contrôle la
    constitutionnalité des lois (contrôle *a priori* via DC, *a posteriori* via
    QPC) et les élections nationales.

    Args:
        query: mots-clés (opérateurs FTS5)
        nature: filtre optionnel par type de décision :
            - "QPC" : Question Prioritaire de Constitutionnalité
              (contrôle a posteriori, saisine par justiciable via CE/Cass)
            - "DC"  : Décision sur conformité de loi ordinaire ou organique
              (contrôle a priori avant promulgation)
            - "L"   : Lois diverses, délégalisation
            - "AN"  : Élections législatives, inéligibilités
            - "SEN" : Élections sénatoriales
            - "PDR" : Élection présidentielle
            - "ORGA": Organisation (règlement intérieur, composition)
            - "REF" : Référendum
            - "ELEC": Autres élections
            - "I"   : Incompétence
            (si vide, toutes natures confondues)
        date_min, date_max: ISO YYYY-MM-DD
        limit: max 50 (défaut 20)
        offset: pagination

    Returns:
        `{"total", "returned", "nature_filter", "decisions": [...]}`
    """
    _record_call("search_cc")
    return dila.search_cc(
        query=query,
        nature=nature or None,
        date_min=date_min or None,
        date_max=date_max or None,
        limit=limit, offset=offset,
    )


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


# ─── BULKS DILA — RECHERCHE BM25 SUR ARCHIVES COMPLÈTES ────────────
# Ces outils exploitent les bulks DILA ingérés en local sur al-uzza :
# jade (4M décisions admin), legi (codes+lois consolidés), jorf (JO
# post-1990), kali (conventions collectives), cnil (délibérations).
# Tous avec ranking BM25 (vraie pertinence) + snippet + date range.
# Différence-clé avec les tools `*_recent` : tri par pertinence, pas
# par date. Préférer ces outils pour trouver la jurisprudence
# pertinente sur un sujet.

@mcp.tool()
async def search_admin(
    query: str,
    juridiction: str = "",
    sort: str = "relevance",
    date_min: str = "",
    date_max: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche pondérée par pertinence BM25 sur la jurisprudence
    administrative complète (Conseil d'État + 9 CAA + 40 TA).

    Source : bulk JADE DILA (~4M décisions full text). Contrairement aux
    outils `search_admin_recent*` qui trient par date, celui-ci classe par
    pertinence sémantique des mots-clés. Indispensable pour trouver LES
    bonnes décisions sur un sujet sans dépendre de l'ancienneté.

    ⚠️ **Si tu cherches par numéro de requête (7 chiffres ex: 2200433)**,
    utilise plutôt `get_admin_decision(numero, juridiction=...)` qui fait
    un lookup SQL exact. La recherche FTS5 d'un numéro court ne le trouve
    que dans les décisions qui le **citent** dans leur texte (ex: décision
    de cassation), pas la décision identifiée par ce numéro.

    Args:
        query: mots-clés (opérateurs FTS5 : AND/OR/NOT, "phrase exacte", mot*)
        juridiction: filtre par fragment de nom de juridiction. Ex :
            "Lyon" → toutes les décisions Lyon (TA + CAA), "Tribunal
            Administratif de Lyon" → uniquement TA Lyon. Combiné en
            FTS5 AND avec la query principale.
        sort: "relevance" (défaut, BM25) ou "date_desc" / "date_asc"
        date_min: limite inférieure ISO YYYY-MM-DD (optionnel)
        date_max: limite supérieure ISO YYYY-MM-DD (optionnel)
        limit: nombre de résultats (défaut 20, max 50)
        offset: pagination

    Returns:
        {"total", "returned", "decisions": [...]} avec extracts BM25.
    """
    _record_call("search_admin")
    return await jade_remote.search(
        query=query, juridiction=juridiction or None, sort=sort,
        date_min=date_min or None, date_max=date_max or None,
        limit=limit, offset=offset,
    )


@mcp.tool()
async def search_legi(
    query: str,
    code: str = "",
    date_min: str = "",
    date_max: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche pondérée dans les codes et lois consolidés français.

    Source : bulk LEGI DILA (3,6 Go avec versions historiques). Trouve
    les articles dont le texte ou le titre contient les mots-clés.

    Args:
        query: mots-clés FTS5
        code: filtre optionnel sur un code spécifique (CC, CT, CSP...)
        date_min/date_max: filtre par date_debut de version (ISO)
        limit: max 50
        offset: pagination

    Returns:
        {"total", "returned", "articles": [...]}
    """
    _record_call("search_legi")
    from sources import warehouse as wh
    data = await wh.search_fond(
        "legi", query, limit=limit, offset=offset, sort="relevance",
        date_min=date_min or None, date_max=date_max or None,
        code=code or None,
    )
    return {
        "total": data.get("total", 0),
        "returned": data.get("returned", 0),
        "limit": limit, "offset": offset,
        "articles": [
            {
                "legiarti": h.get("id"),
                "num": h.get("num"),
                "titre_section": h.get("titre"),
                "legitext": h.get("legitext"),
                "etat": h.get("etat"),
                "date_debut": h.get("date"),
                "extract": h.get("extract"),
            }
            for h in data.get("results", [])
        ],
    }


@mcp.tool()
async def search_jorf(
    query: str,
    nature: str = "",
    date_min: str = "",
    date_max: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche dans le Journal officiel (JORF post-1990).

    Source : bulk JORF DILA (1,1 Go). Contient les textes publiés au JO
    non codifiés : lois, décrets, arrêtés, circulaires, ordonnances.

    Args:
        query: mots-clés FTS5
        nature: filtre optionnel ("LOI", "DECRET", "ARRETE", "CIRCULAIRE"...)
        date_min/date_max: fourchette de publication (ISO)
        limit: max 50

    Returns:
        {"total", "returned", "textes": [...]}
    """
    _record_call("search_jorf")
    return await jorf_remote.search(
        query=query, nature=nature or None,
        date_min=date_min or None, date_max=date_max or None,
        limit=limit, offset=offset,
    )


@mcp.tool()
async def search_kali(
    query: str,
    idcc: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche dans les conventions collectives et accords de branche (KALI).

    Source : bulk KALI DILA (745 Mo). Couvre les conventions collectives
    nationales, accords de branche, avenants, identifiés par leur IDCC.

    Args:
        query: mots-clés
        idcc: filtre optionnel par IDCC (4 chiffres, ex "1486" pour bureaux
              d'études techniques)
        limit: max 50
    """
    _record_call("search_kali")
    return await kali_remote.search(
        query=query, idcc=idcc or None,
        limit=limit, offset=offset,
    )


@mcp.tool()
async def search_cnil(
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche dans les délibérations de la CNIL.

    Source : bulk CNIL (109 Mo, ~26k délibérations). Utile pour le droit
    des données personnelles, RGPD, traitements algorithmiques.
    """
    _record_call("search_cnil")
    return await cnil_remote.search(query=query, limit=limit, offset=offset)


# ─── ARTICLES DE LOI (codes consolidés, versions historiques) ───────
# Ces outils exploitent le bulk LEGI DILA (3,6 Go, versions historiques
# complètes). Spécificité justicelibre : on peut retourner la version
# d'un article telle qu'elle existait à une date précise (ex: art. 1128
# du Code civil en 1992 = texte napoléonien, pas la réforme 2016).
# C'est le "killer feature" que Dalloz vend 200€/mois, exposé ici gratis.

@mcp.tool()
async def get_law_article(code: str, num: str, date: str = "") -> dict[str, Any]:
    """Renvoie le texte d'un article de loi à une date donnée (ou version
    actuelle si `date` vide).

    Particularité justicelibre : quand une décision de 1992 cite
    l'article 1128 du Code civil, l'article a été totalement réécrit en
    2016. Avec ce tool on récupère le texte **tel qu'il existait en 1992**
    (l'ancienne version napoléonienne), pas le texte actuel.

    Codes supportés (22) : CC, CP, CPC, CPP, CT, CSP, CJA, CGCT, CRPA,
    CPI, CASF, CMF, C.com, C.cons, C.éduc, CU, C.env, CR, CGI, CESEDA,
    CSS, CCH.

    Args:
        code: code court (ex : "CC" pour Code civil, "CT" pour Code du travail)
        num: numéro de l'article (ex : "1128", "L1152-1", "132-1")
        date: date ISO YYYY-MM-DD (optionnel — si absent, version en vigueur).
              Utiliser la date de la décision citante pour obtenir la
              version contemporaine de la citation.

    Returns:
        dict avec `legiarti`, `num`, `code`, `texte`, `etat`
        (VIGUEUR/MODIFIE/ABROGE), `date_debut`, `date_fin`, `nota`. Plus
        un champ `note` si la version retournée n'est pas celle demandée.
    """
    _record_call("get_law_article")
    return await legi.get_article(code, num, date or None)


@mcp.tool()
async def get_law_versions(code: str, num: str) -> dict[str, Any]:
    """Renvoie toutes les versions historiques d'un article de loi, du plus
    ancien au plus récent.

    Utile pour construire une "timeline" de l'article et comprendre son
    évolution (ex : un article modifié en 1964, 1994, 2016 aura 3-4 lignes
    avec `date_debut`, `date_fin`, `etat`, `texte` distincts).

    Args:
        code: code court (voir get_law_article pour la liste des 22 codes)
        num: numéro de l'article

    Returns:
        dict avec `code`, `code_long`, `num`, `count`, `versions`
        (liste ordonnée par `date_debut` ascendante).
    """
    _record_call("get_law_versions")
    return await legi.get_versions(code, num)


@mcp.tool()
async def search_decisions_citing(
    code: str,
    num: str,
    sources: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Cherche les décisions qui citent EXPLICITEMENT un article de loi donné.

    Exploite l'index FTS5 sur les sources jurisprudence disponibles pour
    matcher les formulations courantes de citation (`"article 1382 du code
    civil"`, `"art. L. 1152-1 du Code du travail"`, etc.). Cross-référencement
    inverse : partant d'un article, on trouve la jurisprudence pertinente.

    **LIMITATION CONNUE** : ce tool trouve UNIQUEMENT les citations explicites
    du numéro d'article. Il ne capte PAS :
    - les références indirectes ("conformément aux dispositions du Code civil
      relatives à la responsabilité délictuelle…")
    - les renvois à une section entière sans numéro précis
    - les citations du code par abréviation seule sans article ("en vertu du CT")
    Pour une recherche conceptuelle plus large, préférer `search_all` avec
    l'expansion thésaurus (ex: "harcèlement" → inclut "intimidation" etc.).

    Args:
        code: code court de l'article (ex : "CT", "CC")
        num: numéro de l'article (ex : "L1152-1", "1240")
        sources: liste optionnelle de sources à interroger parmi
                 ["dila", "jade", "cedh", "cjue"]. Par défaut : toutes.
        limit: nombre de décisions par source (défaut 20, max 50)

    Returns:
        dict `{"code", "num", "total", "per_source": {source: count},
        "decisions": [{source, id, juridiction, date, title, extract}]}`
    """
    _record_call("search_decisions_citing")
    if not legi.is_supported(code):
        return {"error": f"Code inconnu: {code!r}",
                "supported_codes": list(legi.SUPPORTED_CODES.keys())}
    code_long = legi.SUPPORTED_CODES[code]
    limit = max(1, min(int(limit), 50))
    # Construire une query FTS5 couvrant les formulations habituelles.
    # On enrobe en phrases pour éviter les faux positifs.
    variants = [
        f'"article {num}"',
        f'"art. {num}"',
        f'"art {num}"',
    ]
    # Code nom complet + code court
    query = f'({" OR ".join(variants)}) AND ("{code_long}" OR "{code}")'
    allowed = set(sources) if sources else {"dila", "jade", "cedh", "cjue"}
    results = []
    per_source: dict[str, int] = {}
    # DILA (local FTS5)
    if "dila" in allowed:
        try:
            d = dila.search(query=query, juridiction="", limit=limit)
            for h in d.get("decisions", []):
                results.append({
                    "source": "dila", "id": h.get("id"),
                    "juridiction": h.get("juridiction"),
                    "date": h.get("date"), "title": h.get("title"),
                    "extract": h.get("extract"),
                })
            per_source["dila"] = d.get("total", 0)
        except Exception as e:
            per_source["dila"] = f"error: {e}"
    # JADE (via warehouse)
    if "jade" in allowed:
        try:
            from sources import warehouse as wh
            d = await wh.search_fond("jade", query, limit=limit, sort="relevance")
            for h in d.get("results", []):
                results.append({
                    "source": "jade", "id": h.get("id"),
                    "juridiction": h.get("juridiction"),
                    "date": h.get("date"), "title": h.get("titre"),
                    "extract": h.get("extract"),
                })
            per_source["jade"] = d.get("total", 0)
        except Exception as e:
            per_source["jade"] = f"error: {e}"
    # CEDH
    if "cedh" in allowed:
        try:
            d = european.search_cedh(query=query, limit=limit)
            for h in d.get("decisions", []):
                results.append({
                    "source": "cedh", "id": h.get("id"),
                    "juridiction": "Cour EDH",
                    "date": h.get("date"), "title": h.get("title"),
                    "extract": h.get("extract"),
                })
            per_source["cedh"] = d.get("total", 0)
        except Exception as e:
            per_source["cedh"] = f"error: {e}"
    # CJUE
    if "cjue" in allowed:
        try:
            d = european.search_cjue(query=query, limit=limit)
            for h in d.get("decisions", []):
                results.append({
                    "source": "cjue", "id": h.get("id"),
                    "juridiction": "CJUE",
                    "date": h.get("date"), "title": h.get("title"),
                    "extract": h.get("extract"),
                })
            per_source["cjue"] = d.get("total", 0)
        except Exception as e:
            per_source["cjue"] = f"error: {e}"
    return {
        "code": code, "num": num,
        "query_built": query,
        "total": len(results),
        "per_source": per_source,
        "decisions": results[:limit * len(allowed)],
    }


# ─── TOOL UNIFIÉ : search_all ──────────────────────────────────────

@mcp.tool()
async def search_all(
    query: str,
    sources: list[str] | None = None,
    sort: str = "relevance",
    date_min: str = "",
    date_max: str = "",
    limit: int = 30,
    expand_synonyms: bool = True,
) -> dict[str, Any]:
    """Recherche fédérée pondérée par pertinence sur toutes les sources.

    Tool ONE-STOP quand on ne sait pas où chercher : interroge en parallèle
    les sources locales (DILA judic, JADE admin, LEGI, CEDH, CJUE) et
    retourne une liste fusionnée triée par score BM25 avec un bonus
    d'autorité (CE/Cass/CEDH > CAA > TA/CA).

    Args:
        query: mots-clés (ou phrase). Si `expand_synonyms=True` (défaut),
            les termes du thésaurus juridique FR sont automatiquement
            étendus à leurs équivalents (ex: "harcèlement" → aussi
            "intimidation", "vexation morale", etc.)
        sources: liste optionnelle parmi ["dila", "jade", "legi", "cedh",
            "cjue"]. None = toutes.
        sort: "relevance" (défaut) ou "date_desc"
        date_min, date_max: ISO YYYY-MM-DD
        limit: nombre de résultats fusionnés (défaut 30, max 100)
        expand_synonyms: active le thésaurus (défaut True)

    Returns:
        dict {"query_expanded", "per_source_counts", "results": [...]}
    """
    _record_call("search_all")
    limit = max(1, min(int(limit), 100))
    allowed = set(sources) if sources else {"dila", "jade", "legi", "cedh", "cjue"}
    # Expansion thésaurus
    from query_intent import expand_synonyms as _expand, detect_intent
    intent = detect_intent(query)
    if expand_synonyms and intent.kind in ("fts", "phrase"):
        q_expanded = _expand(query)
    else:
        q_expanded = query

    # Bonus d'autorité par source (multiplicateur score)
    AUTHORITY = {
        "cjue": 1.20, "cedh": 1.20,
        "jade": 1.10,  # admin (CE dedans)
        "dila": 1.15,  # Cass dominante
        "legi": 0.80,  # articles de loi (pertinents mais on veut des décisions)
    }

    async def _search_one(src: str):
        try:
            if src == "dila":
                d = dila.search(query=q_expanded, juridiction="", limit=limit)
                hits = [{"source": "dila", "id": h.get("id"),
                         "juridiction": h.get("juridiction"),
                         "date": h.get("date"), "title": h.get("title"),
                         "extract": h.get("extract"),
                         "score": 1.0} for h in d.get("decisions", [])]
                return src, d.get("total", 0), hits
            if src == "jade":
                d = await jade_remote.search(query=q_expanded, sort=sort,
                    date_min=date_min or None, date_max=date_max or None, limit=limit)
                hits = [{"source": "jade", "id": h.get("id"),
                         "juridiction": h.get("juridiction"),
                         "date": h.get("date"), "title": h.get("titre"),
                         "extract": h.get("extract"),
                         "score": 1.0} for h in d.get("decisions", [])]
                return src, d.get("total", 0), hits
            if src == "legi":
                from sources import warehouse as wh
                d = await wh.search_fond("legi", q_expanded, limit=limit,
                    sort=sort, date_min=date_min or None, date_max=date_max or None)
                hits = [{"source": "legi", "id": h.get("id"),
                         "juridiction": "Articles de loi",
                         "date": h.get("date"), "title": f"Article {h.get('num')} — {h.get('titre')}",
                         "extract": h.get("extract"),
                         "score": 1.0} for h in d.get("results", [])]
                return src, d.get("total", 0), hits
            if src == "cedh":
                d = european.search_cedh(query=q_expanded, limit=limit)
                hits = [{"source": "cedh", "id": h.get("id"),
                         "juridiction": "Cour EDH",
                         "date": h.get("date"), "title": h.get("title"),
                         "extract": h.get("extract"),
                         "score": 1.0} for h in d.get("decisions", [])]
                return src, d.get("total", 0), hits
            if src == "cjue":
                d = european.search_cjue(query=q_expanded, limit=limit)
                hits = [{"source": "cjue", "id": h.get("id"),
                         "juridiction": "CJUE",
                         "date": h.get("date"), "title": h.get("title"),
                         "extract": h.get("extract"),
                         "score": 1.0} for h in d.get("decisions", [])]
                return src, d.get("total", 0), hits
        except Exception as e:
            return src, 0, [{"source": src, "error": str(e)}]
        return src, 0, []

    import asyncio
    tasks = [_search_one(s) for s in allowed]
    results_raw = await asyncio.gather(*tasks)
    per_source = {}
    merged = []
    for src, total, hits in results_raw:
        per_source[src] = total
        boost = AUTHORITY.get(src, 1.0)
        for h in hits:
            if "error" in h:
                continue
            h["score"] = h.get("score", 1.0) * boost
            merged.append(h)
    # Tri global par score desc (BM25 côté chaque source déjà appliqué,
    # le boost d'autorité discrimine entre sources de même pertinence)
    merged.sort(key=lambda h: h.get("score", 0), reverse=True)
    return {
        "query": query,
        "query_expanded": q_expanded if q_expanded != query else None,
        "per_source_counts": per_source,
        "total_returned": len(merged[:limit]),
        "results": merged[:limit],
    }


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
