# Correctifs « B » du second audit (2 oct. 2026) — EN LOCAL, non déployés

Agent Opus. Aucun ssh d'écriture, aucun déploiement, commit, push ni kill. La prod (46.225.190.237) n'a été lue qu'en lecture seule (`sqlite3 -readonly`, `journalctl`, `systemctl cat/show`, `grep`). Je n'ai pas touché à l'entrepôt.

Source : `scratchpad/audit/audit_site_trafic_2oct.md`, lu en entier (197 lignes). Défauts traités : F5, F3, F4, P2, P3.

## 0. MANIFESTE DE COUVERTURE

**Lu**
- `audit_site_trafic_2oct.md` en entier.
- `token_server.py` l. 115-160 (route /loi/) et l. 185-300 (do_GET, route /decision/).
- `ssr.py` l. 795-810 (`_canonical`) et l. 1395-1600 (tous les sous-sitemaps).
- `sources/jade_remote.py` l. 196-300 ; `sources/juriadmin.py` (codes CAA, l. 79-92) ; `citation_search.py` l. 275-305 (autre appelant de `get_admin_decision`).
- `server.py` : `_tool_error` (l. 302-312), `get_admin_decision`, `search_admin`, `search_all` (jusqu'à `_search_one`), `search_annuaire`, `_load_annuaire`.
- `sources/dila.py` l. 144-300 et `search_cc` en entier ; `index_dila.py` l. 195-225 (schéma FTS).
- `tests/run_all.sh`, `tests/test_lois_codes_dates.py` (en-tête), `tests/test_error_contract.py` (en-tête).
- Prod, lecture seule : index de `decisions`, schéma de `decisions_fts`, plans de requête, journaux du 02/10 06:48-06:51 (apt, dpkg, unattended-upgrades, systemd, justicelibre), config apt/needrestart/timer, unité `justicelibre.service`, types de l'annuaire.

**Non vérifié / hors périmètre**
- `search_api.py` et `scrape_ariane.py` : pas modifiés (périmètre de l'autre agent). Je constate que `search_api.py`, `ssr.py` (l. 867-1021, doctrine F1) et `server.py` (`_doctrine_identite`, l. ~2017-2056) ont été modifiés **par l'autre agent pendant ma session** ; ces hunks ne sont pas les miens et sont exclus du diff ci-dessous.
- La redirection `/search.html?id=…&source=…` (`token_server.py` l. ~258) refuse toujours les parenthèses : non corrigée (aucune URL publiée ne l'utilise).
- Mesure « avant » de `search_cc` daté : je ne l'ai **pas** rejouée (13-15 min de 90 % d'iowait sur la prod) ; je reprends les 891 s / 794 s de l'audit.
- Pas de sonde en conditions réelles : le code n'est pas déployé.

## 1. Les correctifs

### 1.1 Sitemap CJUE (F5)
- Route : `token_server.py:151` `_DECISION_PATH_RE = re.compile(r"^/decision/([a-z]+)/([A-Za-z0-9_\-:.%|()]{4,160})$")` (parenthèses ajoutées), extraite en fonction testable `_parse_decision_path` (`token_server.py:154`), appelée à `token_server.py:280`. Accepte les parenthèses brutes (anciennes URL déjà crawlées) et encodées.
- Sitemaps : `ssr.py:1469` (cedh), `ssr.py:1493` (cjue), `ssr.py:1562` (cnil) écrivent désormais `_canonical(source, id)` (`ssr.py:790`, `quote(id, safe='')`). Sitemap et canonique produisent donc **la même chaîne** ; le test relit chaque `<loc>` par la route et retrouve l'identifiant d'origine.

### 1.2 get_admin_decision sans juridiction (F3)
- `sources/jade_remote.py:201-210` : table lettres → cour (`MA`→CAA13, `TL`→CAA31, `BX`→CAA33, `NT`→CAA44, `NC`→CAA54, `DA`→CAA59, `LY`→CAA69, `PA`→CAA75, `VE`→CAA78) et `_caa_depuis_numero`. `jade_remote.py:254` : sans juridiction, un numéro `AA`+2 lettres+chiffres interroge sa cour ; les autres gardent `CE-CAA` (inchangé).
- `jade_remote.py:285-293` : `except Exception: return None` remplacé par une erreur `error_category: "upstream"`, `retryable: True`. `server.py:1541` la renvoie telle quelle au lieu de « introuvable ». `citation_search.py:287-295` lisait déjà `d.get("error")` : compatible.
- Docstring corrigée (`server.py`, bloc « Sans `juridiction` »).

### 1.3 Filtres inconnus (F4)
- `server.py:317-330` : `_SORTS_ADMIS = ("relevance", "date_desc", "date_asc")`, `_SOURCES_SEARCH_ALL`, `_check_enum` (erreur `validation` + `valeurs_admises`).
- `search_admin` : `server.py:1815`. `search_all` : `server.py:2423` (sort) et `2426-2437` (sources ; normalisation minuscules/espaces, une chaîne seule acceptée comme liste). Les trois tris passés tels quels à l'entrepôt sont ceux qu'il connaît (`warehouse/warehouse_server.py:922-924`).
- `search_annuaire` : `server.py:2770-2782`. Les valeurs admises sont lues dans les données, avec la même règle que le filtre existant (catégorie = sous-chaîne du slug ou du libellé, source exacte), donc aucun appel valide n'est refusé. Si l'annuaire n'est pas chargé (`rows` vide), pas de refus. En prod : 39 types et les sources `dila`, `api`, `manuel` (+ `prada`, `pdf` ajoutés par `_load_annuaire`) — commande : `python3 -c "…len({r.get('type') for r in d['rows']})…"` → `39 {'dila', 'api', 'manuel'}`.

### 1.4 search_cc daté : 13-15 min (P2)
**Cause** (prod, lecture seule) :
```
$ sqlite3 -readonly judiciaire.db "EXPLAIN QUERY PLAN SELECT d.id FROM decisions_fts f JOIN decisions d ON d.rowid = f.rowid WHERE decisions_fts MATCH 'loi' AND d.juridiction = 'Conseil constitutionnel' AND d.date >= '2026-01-01' ORDER BY d.date DESC LIMIT 3"
|--SCAN f VIRTUAL TABLE INDEX 0:M8
|--SEARCH d USING INTEGER PRIMARY KEY (rowid=?)
`--USE TEMP B-TREE FOR ORDER BY
```
Plan identique sans la date. SQLite parcourt TOUTES les décisions contenant « loi » (plus d'un million) et lit chaque ligne de `decisions` (28 Go) pour tester juridiction et date : lectures aléatoires, iowait. Ce n'est donc pas la date, mais un mot fréquent ; la date n'y change rien. **Aucun index ne manque** (`.indexes decisions` → `idx_decisions_date`, `idx_decisions_juridiction`, `idx_decisions_numero`, `idx_decisions_ecli`, `idx_decisions_rg_norm`) ; un index ne peut pas aider une jointure pilotée par FTS. **Aucun index à créer en prod.**

**Correctif** : `sources/dila.py:475` `params = [f'({fts_query}) AND juridiction:"conseil constitutionnel"']` : la colonne `juridiction` est indexée par FTS5 (schéma prod : `fts5(id UNINDEXED, titre, juridiction, solution, numero, formation, text, numero_rg_norm, …)`), donc FTS croise les listes avant toute lecture de ligne. Le filtre SQL exact reste en garde-fou.

**Mesures** (prod, `sqlite3 -readonly`, lecture seule) :
- Couverture du filtre FTS : `SELECT (SELECT count(*) FROM decisions WHERE juridiction='Conseil constitutionnel'), (SELECT count(*) … MATCH 'juridiction:"conseil constitutionnel"' AND d.juridiction='Conseil constitutionnel')` → `7388|7388` (aucune décision perdue).
- Après : COUNT de la requête de l'audit (`loi`, `date >= 2026-01-01`) → `60` en `real 0m3.327s` ; les 3 premières lignes en `real 0m1.736s` (`CONSTEXT000054617301|2026-07-31` …). Avant (audit) : 891,37 s et 794,44 s, total 60. **Même total, ~250 fois plus rapide.** Le délai réel côté outil sera un peu plus long (snippet).
- Non fait : le délai de garde (progress handler à 20 s) suggéré par l'audit ; à décider.

### 1.5 unattended-upgrades (P3) — fichiers dans `ops/maintenance-nocturne/`, rien d'appliqué
Constat (prod, `journalctl`) : la coupure de 90 s n'est pas le temps de redémarrage, c'est le délai d'arrêt du MCP :
```
06:49:14 Stopping justicelibre.service …
06:49:14 INFO: Waiting for connections to close. (CTRL+C to force quit)
06:50:44 justicelibre.service: State 'stop-sigterm' timed out. Killing.
06:50:44 Started justicelibre.service …
06:50:46 INFO: Started server process [1879381]
```
`systemctl show justicelibre -p TimeoutStopUSec` → `TimeoutStopUSec=1min 30s`. nginx et token étaient revenus à 06:49:15. Déclencheur : mise à jour `openssl`/`libssl3t64` (`dpkg.log` 06:49:11), puis needrestart (`$nrconf{restart}` commenté, l. 40 de `needrestart.conf`) relance les services. Timer : `OnCalendar=*-*-* 6:00`, `RandomizedDelaySec=60m`.

Fichiers proposés :
- `justicelibre.service.d/arret-rapide.conf` : `TimeoutStopSec=8s` (**le correctif principal** ; vaut aussi pour chaque déploiement).
- `apt-daily-upgrade.timer.d/override.conf` : 02:30 UTC + 0-20 min.
- `needrestart-conf.d/90-justicelibre.conf` (optionnel) : `override_rc` à 0 pour `justicelibre*` et `nginx`.
- `README.md` : constat, application, contrôle du lendemain, **retour arrière** (suppression des trois fichiers + `daemon-reload`), risque (requête longue coupée au redémarrage).

## 2. Diff (mes hunks seulement ; pas de git dans ce dossier, `diff -u` contre des copies prises avant mes modifications)

```
token_server.py        +20  -4
ssr.py                 +3   -3
server.py              +59  -4
sources/jade_remote.py +31  -2
sources/dila.py        +11  -1
tests/run_all.sh       +1
tests/test_second_audit_B.py              (nouveau, 320 l.)
ops/maintenance-nocturne/ (README.md 58 l. + 3 fichiers de conf)
```
Copies d'origine et diffs complets : `/tmp/claude-1000/-home-dahl/748c09b7-716e-46e8-9843-1281859081b9/scratchpad/*.orig`, `*.diff` (les diffs `ssr.py` et `server.py` contiennent aussi les hunks doctrine de l'autre agent, l. 867-1021 et ~2017-2056).

## 3. Tests

`tests/test_second_audit_B.py` (13 tests, ajouté à `tests/run_all.sh:35`).

**Avant** (même test lancé contre une copie du dépôt dont les 5 fichiers sont les originaux) : **9/13 échouent** :
- `test_route_accepte_parentheses_brutes_et_encodees` ; `test_sitemap_cjue_chaque_loc_relue_par_la_route` (« parenthèse brute dans le sitemap : …/decision/cjue/62019CO0123(02) ») ;
- `test_get_admin_decision_caa_sans_juridiction` (`not_found`, appel live sur `['CE-CAA']`) ; `test_get_admin_decision_panne_live_pas_introuvable` (`not_found` au lieu de `upstream`) ;
- `test_search_all_source_inconnue_refusee` (`per_source_counts: {'nimportequoi': 0}`) ; `test_search_all_sort_inconnu_refuse` ; `test_search_admin_sort_inconnu_refuse_et_valides_passent` ; `test_search_annuaire_filtres_inconnus_refuses` (`{'total': 0, 'returned': 0, 'results': []}`) ;
- `test_search_cc_filtre_juridiction_dans_le_match` (« filtre de juridiction absent du MATCH FTS : 'loi' »).
Les 4 qui passaient déjà sont les tests de non-régression (CE sans juridiction, juridiction explicite, source/filtres valides).

**Après** : 13/13.

**Suite complète `bash tests/run_all.sh --offline`** : avant mes modifications, rc=0 ; après, rc=0, tout passe, dont `test_parse_dila_champs.py` (20/20) et `test_lois_codes_dates.py` (15/15). Relancée une dernière fois après les modifications concurrentes de l'autre agent : toujours verte.

## 4. Sondes à faire après déploiement (par l'opératrice ; non faites, rien n'est déployé)

1. `curl -sI https://justicelibre.org/decision/cjue/61959CC0033%2801%29` et `…/61959CC0033(01)` → 200 tous deux ; `curl -s https://justicelibre.org/sitemap-cjue-1.xml | grep -c '(' ` → 0 ; tirer 10 `<loc>` et vérifier 200.
2. MCP `get_admin_decision(numero="26VE02318")` → `DCA_26VE02318_20260930` ; `get_admin_decision("25DA02275")` → trouvé ; `get_admin_decision("473286")` → inchangé.
3. `search_all(query="harcèlement", sources=["nimportequoi"])`, `search_annuaire(query="greffe", category="categorie_bidon")`, `search_admin(query="permis", sort="pertinence_bizarre")` → `error_category: "validation"` avec la liste ; `search_annuaire(query="greffe", category="mairie")` → résultats comme avant.
4. `search_cc(query="loi", date_min="2026-01-01", limit=3)` → total 60, en quelques secondes ; surveiller `vmstat 1` pendant l'appel (plus d'iowait à 90 %).
5. Après pose des fichiers `ops/maintenance-nocturne/` : `systemctl show justicelibre -p TimeoutStopUSec` → 8s ; `systemctl list-timers apt-daily-upgrade.timer` → vers 02:30 UTC ; le lendemain, compter les `POST /mcp 502`.

Rappel déploiement : `token_server.py` local diffère déjà de la prod (`JL_SSR_V2`, audit C8) ; le rsync emportera aussi les modifications de l'autre agent dans `ssr.py`, `server.py`, `search_api.py`.
