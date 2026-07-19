# Architecture des données — JusticeLibre

Ce document décrit ce qu'un contributeur ne peut pas deviner en lisant le code :
où vivent les données, leurs volumes réels, et qui écrit quoi. Comptages au
20 juillet 2026.

Volontairement absent d'ici : tout ce qui relève du déploiement (adresses des
serveurs, chemins précis, secrets, topologie réseau). Si une PR dépend d'une
hypothèse de ce type, la marquer « à vérifier côté mainteneur ».

## Vue d'ensemble

Deux machines, deux rôles :

1. **Le serveur public** — héberge le site (nginx), le serveur MCP
   (`server.py`, FastMCP), le serveur token/API/SSR (`token_server.py`) et les
   bases interrogées en direct à chaque requête utilisateur.
2. **L'entrepôt** (« warehouse ») — héberge les bases volumineuses interrogées
   via un service HTTP interne (`warehouse_server.py`, endpoints `/v1/*`),
   accessible uniquement depuis le serveur public. C'est lui que
   `sources/jade_remote.py`, `sources/legi.py` (partie warehouse) et
   `sources/cnil_remote.py` appellent.

Règle de fond : **git est la source de vérité unique du code**. Aucune
modification directe en prod ; tout passe par commit + déploiement.

## Bases du serveur public (interrogées en local par server.py / token_server.py)

### `judiciaire.db` (~21 Go) — la base principale

| Table | Lignes | Contenu | Alimentée par |
|---|---:|---|---|
| `decisions` | 1 213 903 | Cass + cours d'appel + Conseil constit (bulk DILA CASS/CAPP/INCA/CONSTIT) | `parse_dila_bulk.py`, `index_dila.py` (cron quotidien) |
| `decisions_meta_piste` | 606 265 | métadonnées enrichies via PISTE Judilibre (chambre, solution, thèmes) | `judilibre_sync.py` (cron quotidien) |
| `ariane_decisions` | 114 165 | Conseil d'État via ArianeWeb | `scrape_ariane.py` |
| `cedh_decisions` | 76 051 | Cour EDH (HUDOC) | `scrape_cedh.py`, `scrape_cedh_gaps.py` |
| `cjue_decisions` | 44 270 | CJUE + Tribunal UE (EUR-Lex/Cellar) | `scrape_cjue.py` |

Index FTS5 associés : `decisions_fts`, `ariane_fts`, `cedh_fts`, `cjue_fts`
(external content, voir section FTS plus bas).

### Note
Les données JADE (justice administrative) ne sont pas sur le serveur public :
elles vivent sur l'entrepôt et s'interrogent via son service HTTP interne.

## Bases de l'entrepôt (interrogées via warehouse_server.py)

| Base | Taille | Table principale | Lignes | Contenu |
|---|---:|---|---:|---|
| `jade.db` | 14 Go | `jade_decisions` | 570 063 | justice administrative (CE + 9 CAA + 40 TA), bulk JADE |
| `opendata.db` | 9,6 Go | `opendata_decisions` | 985 996 | open data judiciaire complémentaire |
| `legi.db` | 3,8 Go | `legi_articles`, `legi_textes` | 1 780 693 | codes consolidés + lois, **avec versions historiques datées** (la killer feature `get_law_article(date)`) |
| `jorf.db` | 2,3 Go | `jorf_textes` | 1 257 034 | Journal officiel post-1990 |
| `kali.db` | 1,3 Go | `kali_textes` | 305 839 | conventions collectives |
| `cnil.db` | 147 Mo | `cnil_deliberations` | 26 663 | délibérations CNIL |
| `inca.db`, `cass.db`, `capp.db`, `doctrine.db` | ~11 Go | — | — | fonds bruts intermédiaires du pipeline d'import |

Chaque fond a son index FTS5 (`jade_fts`, `legi_articles_fts`, `jorf_fts`,
`kali_fts`, `cnil_fts`, `opendata_fts`).

## Recherche plein texte (FTS5)

- Tables FTS5 **external content** adossées aux tables de contenu ; depuis la
  PR #8, les triggers `_ai`/`_ad`/`_au` + `PRAGMA recursive_triggers` gardent
  l'index synchrone à travers les `INSERT OR REPLACE` des ré-imports.
- `scripts/rebuild_fts.py` reconstruit et vérifie l'intégrité des index
  (à lancer après un incident, idempotent).
- Particularité : `articles_fts` (créée par `scrape_legifrance.py`) est
  déclarée pour `judiciaire.db` mais peut être absente selon l'environnement —
  le rebuild la skippe proprement.

## Cadence des écritures

| Quand | Quoi | Écrit dans |
|---|---|---|
| chaque nuit | sync Judilibre `/transactionalHistory` (obligation CGU : répercuter sous 72 h) | `decisions_meta_piste`, `decisions` |
| chaque nuit | incréments DILA (CASS/CAPP/INCA) | `decisions` |
| régulièrement | mises à jour des fonds entrepôt (JADE, LEGI, JORF…) | bases entrepôt |
| 1×/mois (cible) | régénération annuaire (`annuaire/refresh_annuaire.sh`, sanity gates) | données annuaire du site |

Tout le reste (CEDH, CJUE, ArianeWeb) est rescrapé ponctuellement.

## Chemins de lecture

- **MCP** (`server.py`) : lit `judiciaire.db` en local + appelle l'entrepôt
  pour JADE/LEGI/JORF/KALI/CNIL/opendata. L'annuaire (`search_annuaire`) lit
  des JSON/CSV statiques régénérés par le pipeline `annuaire/`.
- **API REST + SSR** (`token_server.py` → `search_api.py`, `ssr.py`) : mêmes
  sources ; les ~3 M de pages `/decision/*` et `/loi/*` sont rendues à la
  volée (rien de pré-généré), avec cache HTTP.
- **Site statique** : pages générées par `annuaire/build_annuaire.py` et
  `annuaire/build_inedits.py` (fils d'ariane inclus dans les templates des
  générateurs — ne pas les patcher dans les pages produites).

## Pipeline annuaire (indépendant du reste)

Sources : dump quotidien DILA des services locaux + API annuaire
service-public (services centraux) + scrape du formulaire CADA (PRADA) +
`pdf_findings.csv` (adresses extraites de PDF officiels, avec copie archivée
sous `/preuves/`). Chaîne : `extract_justice_mails.py` →
`fetch_api_annuaire.py` → `scrape_prada.py` → `build_annuaire.py` /
`build_inedits.py`, orchestrée par `annuaire/refresh_annuaire.sh` (dry-run par
défaut, sanity gates avant tout déploiement).
