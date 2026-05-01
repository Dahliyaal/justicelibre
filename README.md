# JusticeLibre

> **L'accès libre à la jurisprudence française et européenne. Alternative open source à Doctrine, Lexis et Légifrance.**

[![MCP Server](https://img.shields.io/badge/MCP-Streamable_HTTP-1a4e4e)](https://justicelibre.org/mcp)
[![Décisions](https://img.shields.io/badge/Décisions-2_M%2B-1a4e4e)](https://justicelibre.org)
[![Articles de loi](https://img.shields.io/badge/Articles_de_loi-1.5_M%2B-1a4e4e)](https://justicelibre.org)
[![Licence](https://img.shields.io/badge/Licence-MIT-c79e3a)](LICENSE)

Serveur **Model Context Protocol** (MCP) qui expose **~2 M décisions de justice** + **~1,5 M articles de loi consolidés** de la France, de l'UE et du Conseil de l'Europe — gratuit, sans authentification, indexé sur Google.

**Endpoint public** : `https://justicelibre.org/mcp` (Streamable HTTP, sans clé)

**Site web** : [justicelibre.org](https://justicelibre.org)

---

## Pourquoi JusticeLibre

Les outils juridiques propriétaires (**Pappers Justice**, **Doctrine.fr**, **Lexis 360**, **Dalloz**) coûtent 50-200 €/mois et ferment l'accès au droit derrière un paywall. L'open data juridique français existe (loi 2016 République Numérique, loi 2019 réforme de la justice) mais reste techniquement inaccessible :

- Légifrance n'expose que ~25% de la jurisprudence en open data, fragmenté
- Judilibre nécessite OAuth2 PISTE (frictionnel, oublie ChatGPT/Claude classique)
- Les bulks DILA arrivent en ZIPs XML bruts de plusieurs Go, inutilisables sans pipeline ETL
- Les TAs ne sont diffusés que par une API Elasticsearch non documentée

**JusticeLibre** rend cette donnée immédiatement utilisable par tout LLM ou humain :

- ✅ **Aucune clé, aucun compte** : utilisable depuis Claude.ai, ChatGPT, Cursor, Zed, Continue immédiatement
- ✅ **Couverture unique** : Cour de cassation + Conseil d'État + Conseil constitutionnel + 9 CAA + 40 TA + **CEDH** + **CJUE** + délibérations CNIL
- ✅ **Articles de loi avec versions historiques** : "quel était l'article 1382 CC en 1992 ?" → texte napoléonien, pas la réforme 2016
- ✅ **Indexable Google** : ~3 M URLs SSR exposées (sitemap), pas un SPA bot-blind
- ✅ **Open source MIT** : auto-hébergeable

---

## Comparaison

| | JusticeLibre | Pappers Justice | OpenLegi | mcp-juridique.fr | Doctrine.fr |
|---|:-:|:-:|:-:|:-:|:-:|
| Gratuit | ✅ | ❌ payant | partiel | ❌ payant | ❌ 50€/mois |
| Sans inscription | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Cour EDH** | ✅ 76k décisions | ❌ | ❌ | ❌ | ⚠️ partiel |
| **CJUE** | ✅ 44k arrêts | ❌ | ❌ | ❌ | ⚠️ partiel |
| **Conseil constit.** | ✅ 7k décisions + tool dédié | ⚠️ | ❌ | ⚠️ | ✅ |
| **40 TA en parallèle** | ✅ fan-out | ⚠️ partiel | ❌ | ❌ | ✅ |
| **9 CAA en parallèle** | ✅ fan-out | ⚠️ | ❌ | ❌ | ✅ |
| **CNIL délibérations** | ✅ 26k | ❌ | ❌ | ⚠️ | ❌ |
| **Articles loi versionnés** | ✅ 1.5M | ⚠️ | ⚠️ Légifrance brut | ⚠️ | ✅ |
| **BM25 pertinence** | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| **Open source** | ✅ MIT | ❌ | ⚠️ | ❌ | ❌ |
| **MCP natif** | ✅ Streamable HTTP | ✅ | ✅ | ✅ | ❌ (REST seul) |
| **Indexable Google** | ✅ 3M SSR pages | ❌ SPA | ❌ | ❌ | ❌ |

---

## Outils MCP exposés (29)

### Recherche fédérée

| Outil | Description |
|---|---|
| `search_all` | Fan-out parallèle sur toutes les sources, ranking BM25 + bonus autorité (CE +20%, Cass +15%, CEDH +15%, CAA +10%) |
| `about_justicelibre` | Présentation des tools, hiérarchie d'autorité, workflow recommandé |

### Jurisprudence judiciaire (PISTE Judilibre + bulk DILA)

| Outil | Description |
|---|---|
| `search_judiciaire_libre` | 1.17M décisions (Cass + CA + Conseil constit.) - bulk DILA, sans auth |
| `get_decision_judiciaire_libre` | Texte intégral via JURITEXT/CONSTEXT id |
| `search_judiciaire` | Live PISTE Judilibre (besoin OAuth) |
| `get_decision_judiciaire` | Texte via PISTE |
| `search_cc` | Conseil constitutionnel dédié (7112 décisions, filtre par nature : QPC/DC/L/SEN/AN/PDR) |
| `get_cc_decision` | Décision CC par numéro (ex: "2023-1048 QPC") |

### Jurisprudence administrative (CE + 9 CAA + 40 TA)

| Outil | Description |
|---|---|
| `search_admin` | BM25 pondéré sur 552k décisions admin bulk JADE |
| `get_admin_decision` | Lookup par numéro de requête (avec désambiguïsation par juridiction) |
| `get_ce_decision` | CE spécifique avec fallback ArianeWeb |
| `search_conseil_etat` | ~270k CE via Sinequa (moteur sémantique natif) |
| `get_decision_text` | Texte intégral via DCE/DTA/DCAA id |
| `search_admin_recent` / `_all_caa` / `_all_ta` | Tri date desc pour l'actualité |
| `list_juridictions` | 51 codes juridiction (CE, CAA13...78, TA06...109) |

### Jurisprudence européenne

| Outil | Description |
|---|---|
| `search_cedh` | 76k décisions Cour EDH avec sémantique ECHR |
| `get_decision_cedh` | Texte via itemid (ex: "001-249914") |
| `search_cjue` | 44k arrêts CJUE + Tribunal UE |
| `get_decision_cjue` | Via CELEX ou ECLI |

### Articles de loi (killer feature)

| Outil | Description |
|---|---|
| `get_law_article` | Article à une date donnée. Ex: `("CC","1128","1992-05-15")` -> texte napoléonien ; `("CC","1128","2024-01-01")` -> texte post-réforme |
| `get_law_versions` | Timeline complète des versions d'un article |
| `search_legi` | BM25 sur 1.5M articles consolidés (22 codes + Constitution + lois non codifiées) |
| `search_decisions_citing` | Cross-référence inverse : "quelles décisions citent l'article X ?" |
| `resolve_law_number` | Numéro loi/ord/décret -> LEGITEXT/JORFTEXT |
| `build_source_url` | URL Légifrance canonique pour un identifier |

### Droit positif complémentaire

| Outil | Description |
|---|---|
| `search_jorf` | 1.24M textes JO (lois, décrets, arrêtés, circulaires depuis 1990) |
| `search_kali` | 335k conventions collectives + accords de branche |
| `search_cnil` | 26k délibérations CNIL (RGPD, données personnelles) |

---

## Quick start

### Claude Desktop / Claude.ai

Dans **Settings -> Connectors -> Add custom connector** :
```
URL : https://justicelibre.org/mcp
Auth : aucune
```

### ChatGPT / Cursor / Zed / Continue

Ajoute le serveur MCP `https://justicelibre.org/mcp` à ta config (cf doc de chaque client).

### Auto-hébergement

```bash
git clone https://github.com/Dahliyaal/justicelibre.git
cd justicelibre
pip install -r requirements.txt

# Mode stdio (Claude Desktop)
python3 server.py

# Mode Streamable HTTP (Claude.ai web, OpenAI connectors)
python3 server.py http   # listen 0.0.0.0:8765
```

---

## Exemples d'usage

### Contentieux QPC
```python
# Toutes les QPC sur l'article 8 DDHC ces 2 dernières années
search_cc(query="proportionnalité", nature="QPC",
          date_min="2024-01-01", date_max="2026-01-01")
```

### Recours CEDH
```python
# Décisions CEDH France sur la garde à vue
search_cedh(query="garde à vue France")
# Texte intégral
get_decision_cedh(itemid="001-249914")
```

### Recherche jurisprudence administrative ciblée
```python
# Tous les TA + CAA en parallèle sur "harcèlement institutionnel"
search_admin(query="harcèlement institutionnel université",
             sort="relevance", limit=30)
# TA Lyon spécifique
get_admin_decision(numero="2200433", juridiction="Tribunal Administratif de Lyon")
```

### Article de loi à une date précise
```python
# L. 262-8 CASF en vigueur au 1er janvier 2023
get_law_article(code="CASF", num="L262-8", date="2023-01-01")
# Toutes les versions historiques
get_law_versions(code="CC", num="1128")
```

---

## Architecture

```
                        +---------------------+
                        |   Client MCP        |
                        | (Claude/ChatGPT/.)  |
                        +----------+----------+
                                   | Streamable HTTP
                                   v
                  +--------------------------------+
                  |  justicelibre.org/mcp          |
                  |  (FastMCP + nginx + cloudflare)|
                  +--+-------+--------+--------+---+
                     |       |        |        |
        +------------+       |        |        +------------+
        v                    v        v                     v
  +--------------+  +--------------+ +--------------+  +--------------+
  | Bulks DILA   |  | ArianeWeb    | | HUDOC API    |  | InforCuria   |
  | (SQLite +    |  | (Sinequa CE) | | (CEDH)       |  | (CJUE)       |
  |  FTS5 BM25)  |  |              | |              |  |              |
  +--------------+  +--------------+ +--------------+  +--------------+
       ~2.4M            ~270k           76k                44k
```

- Bulks XML DILA téléchargés en local sur al-uzza (Hetzner) avec parsers Python
- Index FTS5 SQLite par fond (jade.db, legi.db, jorf.db, kali.db, cnil.db)
- Fallback live API pour la fraîcheur
- Indexation Google : 3M+ URLs SSR via sitemap (vs SPA bot-blind chez les concurrents)

---

## Sources de données

| Source | Volume | Auth | URL |
|---|---|---|---|
| DILA bulks (CASS/CAPP/CONSTIT/JADE/JORF/KALI/CNIL/LEGI) | ~6 M docs | Aucune | [echanges.dila.gouv.fr](https://echanges.dila.gouv.fr/OPENDATA/) |
| ArianeWeb Conseil d'État | ~270k | Aucune | [conseil-etat.fr](https://www.conseil-etat.fr/arianeweb/) |
| opendata.justice-administrative.fr | ~1.5M | Aucune | [opendata.justice-administrative.fr](https://opendata.justice-administrative.fr/) |
| HUDOC Cour EDH | 76k | Aucune | [hudoc.echr.coe.int](https://hudoc.echr.coe.int/) |
| InforCuria CJUE | 44k | Aucune | [curia.europa.eu](https://curia.europa.eu/) |
| PISTE Judilibre (optionnel) | toutes nouvelles décisions | OAuth2 | [piste.gouv.fr](https://piste.gouv.fr/) |

Données sous **Licence Ouverte 2.0 (Etalab)** - réutilisation libre avec mention de la source.

---

## Limites légales respectées

JusticeLibre respecte strictement :
- **Article 226-18, 226-24, 226-31 Code pénal** : interdiction de profiler les magistrats (jamais de stats par juge dans les outils exposés)
- **Loi 78-17 Informatique et Libertés** : pseudonymisation respectée (ne pas ré-identifier les personnes anonymisées par DILA)
- **Licence Ouverte 2.0** : mention de source et date sur chaque page

---

## Status & roadmap

- [x] V1 : 6 tools sur opendata.justice-administrative.fr (avril 2026)
- [x] V2 : +CEDH, CJUE, Légifrance/PISTE codes consolidés
- [x] V3 : Killer features articles loi + cross-référence décisions citant
- [x] V4 : Bulks DILA en MCP (BM25 admin, judiciaire libre, CC, CNIL, JORF, KALI)
- [x] V5 : Thésaurus FR (495 entrées) + search_all unifié + bonus autorité
- [x] V6 : SSR + sitemap (~3M URLs indexables Google), citations cliquables Légifrance dated, source attribution
- [ ] Crawl complet TAs opendata (~1,5M en cours)
- [ ] LLM extraction citations contextuelles ("même code", "présent code")
- [ ] Embeddings BGE-M3 sur tout le corpus pour recherche sémantique

---

## Communauté

- **Issues / suggestions** : [GitHub Issues](https://github.com/Dahliyaal/justicelibre/issues)
- **MCP Registry** : [PulseMCP](https://www.pulsemcp.com/servers/gh-dahliyaal-justice-libre)
- **Built by** : [@Dahliyaal](https://github.com/Dahliyaal) - projet né d'un usage personnel sur 8 fronts contentieux en parallèle (MDPH, RSA, Barreau, etc.). Outil né d'un besoin réel, pas d'un wrapper Légifrance pondu pour le SEO.

---

## Contribuer

Tout PR bienvenue : nouveaux scrapers, fixes, traductions, exemples d'usage, intégrations clients MCP.

```bash
git clone https://github.com/Dahliyaal/justicelibre.git
cd justicelibre
bash tests/run_all.sh   # tests
```

---

## Licence

MIT - Logiciel libre. Données sous Licence Ouverte 2.0 (Etalab).
