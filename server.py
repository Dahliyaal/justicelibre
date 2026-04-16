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

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from sources import ariane, juriadmin

mcp = FastMCP("justicelibre")

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
async def list_juridictions() -> dict[str, Any]:
    """Liste tous les codes de juridiction acceptés par `search_juridiction`.

    Retourne les 51 juridictions couvertes : Conseil d'État, 9 CAA, 40 TA
    (dont 9 en outre-mer), avec leur nom canonique.

    Utilise cette liste pour connaître le code à passer à `search_juridiction`.
    """
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
async def search_conseil_etat(query: str, limit: int = 20) -> dict[str, Any]:
    """Recherche plein texte dans les décisions du Conseil d'État via ArianeWeb.

    Source la plus riche pour la jurisprudence du CE : ~270 000 décisions
    d'intérêt jurisprudentiel, avec extraits mis en surbrillance et scores
    de pertinence Sinequa.

    Args:
        query: mots-clés de recherche (ex: "référé liberté", "QPC 145")
        limit: nombre maximum de résultats (défaut 20)
    """
    async with _client() as client:
        return await ariane.search(client, query=query, limit=limit)


@mcp.tool()
async def search_juridiction(
    query: str,
    juridiction: str = "CE",
    limit: int = 20,
) -> dict[str, Any]:
    """Recherche plein texte dans une juridiction administrative précise.

    La base couvre le Conseil d'État, les 9 cours administratives d'appel et
    les 40 tribunaux administratifs français (dont 9 outre-mer).

    Args:
        query: mots-clés de recherche
        juridiction: code de la juridiction. Exemples :
            - "CE" — Conseil d'État
            - "CE-CAA" — Conseil d'État + cours administratives d'appel
            - "TA69" — Tribunal administratif de Lyon
            - "TA75" — Tribunal administratif de Paris
            - "CAA69" — Cour administrative d'appel de Lyon
            Appelle `list_juridictions` pour la liste complète.
        limit: nombre maximum de résultats (défaut 20)

    Returns:
        Dict avec `juridiction_name`, `total` (hits), `returned`, et
        `decisions` (liste d'objets avec id, ecli, formation, numero_dossier,
        date_lecture, etc.). L'`id` peut être passé à `get_decision_text`.
    """
    async with _client() as client:
        return await juriadmin.search(
            client, query=query, juridiction=juridiction, limit=limit
        )


@mcp.tool()
async def search_all_tribunaux_admin(
    query: str,
    limit_per_court: int = 5,
) -> dict[str, Any]:
    """Recherche une query dans TOUS les tribunaux administratifs en parallèle.

    Diffuse la même requête aux 40 TA et fusionne les résultats, triés par
    date de lecture décroissante. Utile pour repérer rapidement si une
    question a été tranchée différemment selon les tribunaux.

    Args:
        query: mots-clés de recherche
        limit_per_court: nombre de résultats par tribunal (défaut 5,
            donc jusqu'à 200 résultats totaux)

    Returns:
        Dict avec `per_court_totals` (nombre de hits par TA), `decisions`
        (liste fusionnée triée par date), et les éventuelles `errors`.
    """
    async with _client() as client:
        return await juriadmin.search_many(
            client,
            query=query,
            juridictions=list(juriadmin.TRIBUNAUX_ADMIN.keys()),
            limit_per_court=limit_per_court,
        )


@mcp.tool()
async def search_all_cours_appel(
    query: str,
    limit_per_court: int = 5,
) -> dict[str, Any]:
    """Recherche une query dans toutes les cours administratives d'appel.

    Diffuse aux 9 CAA en parallèle et fusionne les résultats triés par date.

    Args:
        query: mots-clés de recherche
        limit_per_court: résultats par cour (défaut 5)
    """
    async with _client() as client:
        return await juriadmin.search_many(
            client,
            query=query,
            juridictions=list(juriadmin.COURS_ADMIN_APPEL.keys()),
            limit_per_court=limit_per_court,
        )


@mcp.tool()
async def get_decision_text(decision_id: str) -> dict[str, Any] | None:
    """Récupère le texte intégral d'une décision à partir de son identifiant.

    L'identifiant est celui retourné par les outils de recherche dans le
    champ `id` (ex: "DCE_503506_20260409" pour le Conseil d'État,
    "DTA_2503332_20260331" pour un TA). Les décisions incluent les moyens,
    les visas, les considérants et le dispositif.

    Args:
        decision_id: identifiant de la décision (avec ou sans suffixe .xml)

    Returns:
        Dict avec les métadonnées complètes, `text_segments` (liste des
        paragraphes), et `full_text` (texte intégral joint), ou None si
        la décision n'existe pas.
    """
    async with _client() as client:
        return await juriadmin.get_decision(client, decision_id=decision_id)


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
