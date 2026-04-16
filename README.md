# justicelibre

Serveur MCP open source donnant accès à environ 1 050 000 décisions de la justice administrative française. Conseil d'État, 9 cours administratives d'appel, 40 tribunaux administratifs (métropole et outre-mer).

**Endpoint public** : `https://justicelibre.org/mcp`

## Outils exposés

| Outil | Description |
|---|---|
| `list_juridictions` | Liste les 51 juridictions couvertes avec leur code et nom |
| `search_conseil_etat` | Recherche par mots-clés dans les ~270 000 décisions du CE (ArianeWeb) |
| `search_juridiction` | Recherche dans une juridiction précise (ex: `TA69` pour Lyon) |
| `search_all_tribunaux_admin` | Recherche parallèle sur les 40 TA |
| `search_all_cours_appel` | Recherche parallèle sur les 9 CAA |
| `get_decision_text` | Texte intégral d'une décision |

## Utilisation

Ajoutez l'URL `https://justicelibre.org/mcp` comme connecteur MCP personnalisé dans votre client (Claude, ChatGPT, Cursor, Zed, Continue, etc.).

Aucun compte, aucune clé API, aucune inscription.

## Auto-hébergement

```bash
pip install 'mcp[cli]' httpx
python3 server.py          # mode stdio (Claude Desktop, etc.)
python3 server.py http     # mode Streamable HTTP (port 8765)
```

## Sources de données

- [opendata.justice-administrative.fr](https://opendata.justice-administrative.fr/) (API Elasticsearch)
- [conseil-etat.fr](https://www.conseil-etat.fr/) (ArianeWeb, Sinequa xsearch)

Données sous [Licence Ouverte 2.0 (Etalab)](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).

## Licence

MIT
