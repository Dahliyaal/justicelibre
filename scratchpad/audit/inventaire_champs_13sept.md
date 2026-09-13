# Inventaire des champs de données, fonds par fonds

Objet : savoir ce qu'une page de lecture peut afficher À CÔTÉ du texte, honnêtement.
Date des mesures : 13 septembre 2026, entre 21 h 19 et 21 h 50 (heure locale).
Portée : lecture seule. Aucune écriture, aucune modification locale ou distante.

---

## MANIFESTE DE COUVERTURE

### 1. Fichiers lus (chemin absolu, lignes effectivement lues)

| Fichier | Lignes lues | Ce que j'y ai pris |
|---|---|---|
| `/home/dahl/justicelibre/search_api.py` | 1 à 1271 (intégralité) | tous les `_norm_*`, `fetch_decision`, `search_federated`, `JURI_DISPATCH` |
| `/home/dahl/justicelibre/sources/dila.py` | 1 à 730 (intégralité) | schéma servi du fonds judiciaire, `get_decision`, `note_texte_integral` |
| `/home/dahl/justicelibre/sources/european.py` | 1 à 265 (intégralité) | CEDH et CJUE, colonnes servies, ECLI CJUE fabriqués |
| `/home/dahl/justicelibre/sources/ariane.py` | 1 à 334 (intégralité) | `parse_header`, `_normalize_doc`, `fetch_full_text` |
| `/home/dahl/justicelibre/sources/juriadmin.py` | 1 à 217 (intégralité) | `_normalize_hit` (l. 105), `get_decision` (l. 190), `VALID_JURI` (l. 95) |
| `/home/dahl/justicelibre/sources/warehouse.py` | 1 à 419 (intégralité) | `search_fond` (l. 244), `get_decision_remote` (l. 269), `build_url` (l. 330) |
| `/home/dahl/justicelibre/sources/legi.py` | 1 à 264 (intégralité) | `SUPPORTED_CODES` (l. 17), `SUPPORTED_CODES_LEGITEXT` (l. 111) |
| `/home/dahl/justicelibre/sources/jade_remote.py` | 1 à 300 (intégralité) | `_normalize_hit` (l. 110), `_signaler_homonymes` (l. 73) |
| `/home/dahl/justicelibre/sources/jorf_remote.py` | 1 à 51 (intégralité) | champs servis JORF |
| `/home/dahl/justicelibre/sources/kali_remote.py` | 1 à 45 (intégralité) | champs servis KALI |
| `/home/dahl/justicelibre/sources/cnil_remote.py` | 1 à 39 (intégralité) | champs servis CNIL |
| `/home/dahl/justicelibre/sources/citations.py` | 1 à 159 (intégralité) | `detect_citations` (l. 64), `linkify` (l. 115) |
| `/home/dahl/justicelibre/sources/judilibre.py` | 1 à 190 (intégralité) | `_normalize_decision` (l. 85), `_normalize_full_decision` (l. 102) |
| `/home/dahl/justicelibre/warehouse/warehouse_server.py` | 260 à 420, 460 à 600, 604 à 660, 760 à 950 | `FONDS` (l. 267), `select_cols` de `fts_search` (l. 857 à 869), `get_decision` (l. 929), `law_at_date` (l. 460), `_law_row_to_dict` (l. 621), `_titre_section` (l. 604) |
| `/home/dahl/justicelibre/token_server.py` | 1 à 20, 175 à 260, 440 à 600 | liste des routes REST, `_handle_search`, `_handle_decision` |
| `/home/dahl/justicelibre/ssr.py` | 795 à 980, 391 à 416, 1579 à 1584 | `render_decision` et les lignes de sa table de métadonnées |
| `/home/dahl/justicelibre/server.py` | 119 à 400 (survol des noms), 1309 à 1365, 1818 à 1890, 1950 à 2010, 2116 à 2180, 2535 à 2740 | outils MCP doctrine, LEGI, annuaire, `build_source_url`, `search_decisions_citing` |
| `/home/dahl/justicelibre/query_intent.py` | 384 à 431 | `SOURCE_CAPABILITIES`, `sources_for_intent` |
| `/home/dahl/justicelibre/parse_dila_bulk.py` | 225 à 275, 460 à 500, 719 à 748, 805 à 860, 1065 à 1095, 1315 à 1345 | schémas bruts LEGI, JORF, KALI, CNIL, `{fund}_decisions`, `JURIS_ENRICH_COLS`, `JURIS_NEW_COLS` |
| `/home/dahl/justicelibre/index_dila.py` | 35 à 40, 180 à 215 | schéma de `decisions` (base judiciaire du site), `EXTRA_COLS` |
| `/home/dahl/justicelibre/download_opendata.py` | 95 à 130 | schéma `opendata_decisions` |
| `/home/dahl/justicelibre/ingest_cada.py` | 78, 180 à 200, 240 à 270 | colonnes de la table `docs` (fonds doctrine) |
| `/home/dahl/justicelibre/scrape_cedh.py` | 50 à 85 | schéma `cedh_decisions` |
| `/home/dahl/justicelibre/scrape_cjue.py` | 40 à 65 | schéma `cjue_decisions` |
| `/home/dahl/justicelibre/web/hub.html` | 380 à 400 | libellés des fonds annoncés, dont « Travaux préparatoires » |
| `/home/dahl/justicelibre/web/annuaire.html` | 6435 à 6445 | source de données de la page annuaire |

Recherches transversales faites (grep) : `travaux|préparatoire|dossier législatif|exposé des motifs` sur `*.py`, `*.html`, `*.md` du dépôt ; `CREATE TABLE` sur `*.py` ; `inca` sur `*.py` et `*.sh` ; `appno` sur `*.py`.

### 2. Appels d'API faits, avec requête et taille d'échantillon

Script de mesure : `/tmp/claude-1000/-home-dahl/748c09b7-716e-46e8-9843-1281859081b9/scratchpad/mesure.py`
(et `mesure_legi.py`, `mesure2.py` dans le même dossier). Sorties brutes conservées en `mesure.json`, `mesure_legi.json`, `mesure2.json`.

Recherches (`GET https://justicelibre.org/api/search`) :

| Étiquette | Requête exacte | Docs échantillonnés |
|---|---|---|
| dila_cass | `q=harcèlement moral&sources=dila&juridiction=cass&limit=50&timeout=45` | 33 rendus |
| dila_ca | `q=bail commercial&sources=dila&juridiction=ca&limit=30&timeout=45` | 30 |
| dila_tj | `q=expulsion&sources=dila&juridiction=tj&limit=30&timeout=45` | 30 |
| dila_tcom | `q=liquidation judiciaire&sources=dila&juridiction=tcom&limit=30&timeout=45` | 30 |
| dila_constit | `q=liberté&sources=dila&juridiction=constit&limit=30&timeout=45` | 30 |
| ariane | `q=éolienne&sources=ariane&juridiction=ce&limit=30&timeout=40` | 30 |
| admin_ta | `q=permis de construire&sources=admin&juridiction=ta&limit=30&timeout=40` | 30 |
| admin_caa | `q=permis de construire&sources=admin&juridiction=caa&limit=30&timeout=40` | 30 |
| admin_jade | `q=permis de construire&sources=admin&juridiction=caa&limit=20&date_min=2015-01-01&date_max=2016-12-31&timeout=40` | 18 |
| cedh | `q=procès équitable&sources=cedh&juridiction=cedh&limit=50&timeout=40` | 0, HTTP 504 |
| cedh (rejeu) | `q=procès équitable&sources=cedh&juridiction=cedh&limit=20&timeout=30` | 0, `sources_en_echec: ["cedh"]` |
| cedh (rejeu 2) | `q=torture&sources=cedh&juridiction=cedh&limit=10&timeout=25` | 0, `sources_en_echec: ["cedh"]` |
| cjue | `q=données personnelles&sources=cjue&juridiction=cjue&limit=50&timeout=40` | 50 |
| doctrine | `q=communication de documents&juridiction=doctrine&limit=50&timeout=40` | 50 |
| legi | `q=responsabilité&juridiction=legi&limit=50&timeout=40` | 50 |

Documents complets (`GET /api/decision?source=…&id=…`), 8 documents par fonds pris en tête de la liste de résultats ci-dessus, sauf mention :
dila_cass 8, dila_ca 8, dila_tj 8, dila_tcom 8, dila_constit 8, ariane 8, admin_ta 8 (identifiants open data), admin_caa 8 (open data), admin_jade 6 (identifiants CETATEXT), cjue 8, doctrine 8, legi 8. Total 94 documents.

Lois : `GET /api/law?code=…&num=…` sur 30 références réelles couvrant 30 codes différents (CC 1240, CC 9, CC 515-8, CP 121-3, CPC 700, CPP 85, CT L1152-1, CT L1235-3, CSP L1110-4, CJA L521-1, CJA R431-3, CGCT L2121-26, CRPA L311-1, CPI L122-4, CASF L241-6, CMF L511-1, C.com L145-1, C.cons L217-4, C.éduc L442-5, CU L421-1, C.env L110-1, CGI 1729, CESEDA L611-1, CSS L161-1, CCH R111-1, COJ L211-3, CGFP L131-1, CONST 61-1, LIL 2, CPCEx L111-1). Zéro erreur sur 30.
`GET /api/law/versions?code=CT&num=L1152-1` : 1 version.
`GET /api/law/resolve?numero=78-17`, `GET /api/recent` : 1 appel chacun.

Outils MCP justicelibre (même code serveur, autre processus) :
`search_jorf(query="protection des données", limit=30)` → 30 ;
`search_kali(query="licenciement préavis", limit=30)` → 30 ;
`search_cnil(query="vidéosurveillance", limit=30)` → 30 ;
`search_doctrine(query="communication des documents administratifs", limit=40)` → 40 ;
`get_doctrine_document(doc_id="cada:20212413")` → 1 ;
`search_cedh(query="procès équitable", limit=25)` → 25 ;
`search_annuaire(query="tribunal administratif", limit=25)` → 25 ;
`get_law_article(code="CT", num="L1152-1")` → 1.

### 3. Ce qui n'a PAS pu être mesuré, et pourquoi

- **Bases locales**. `/opt/justicelibre` n'existe pas sur cette machine (`ls /opt/justicelibre` → « No such file or directory »). Aucun taux n'a donc pu être calculé sur la base ; tout ce qui suit est mesuré sur échantillon d'API. Les taux portent sur l'échantillon nommé, pas sur le fonds.
- **CEDH par l'API publique du site : NON MESURÉ.** Trois appels, trois échecs (`total: 0`, `sources_en_echec: ["cedh"]`, 43,9 s et 42,7 s ; un 504 nginx à 60 s). La panne est réelle et actuelle, elle n'est pas un artefact de mesure. Les champs CEDH ci-dessous sont donc mesurés **par le MCP** (`search_cedh`), qui répond, plus la lecture du code.
- **Documents CEDH complets (`/api/decision?source=cedh`) : NON MESURÉ**, faute d'identifiants issus d'une recherche du site. Les champs sont donnés d'après `search_api.fetch_decision` l. 1151 à 1158 et `european.get_cedh` l. 146 à 168, sans taux.
- **JORF, KALI, CNIL : taux mesurés sur le MCP seulement.** Ces trois fonds ne sont servis par AUCUNE route REST publique (`token_server.py` l. 175 à 260 : il n'existe que `/api/search`, `/api/expand`, `/api/decision`, `/api/law`, `/api/law/versions`, `/api/law/resolve`, `/api/recent`, `/api/token`, `/api/law/batch`). `search_api.JURI_DISPATCH` l. 303 à 326 ne connaît pas ces fonds ; `fetch_decision` l. 1096 refuse toute source hors `dila, cedh, cjue, admin, ariane, doctrine, legi` (le bloc `cnil` de la l. 1222 est **mort** : il est placé après un test d'appartenance qui exclut `cnil`).
- **Taux de remplissage de `hierarchie` (plan du code) sur le fonds LEGI entier : NON MESURÉ.** Mesuré seulement `titre_section` (dernier niveau) sur 30 articles.
- **Taux de `texte_integral` faux (texte = sommaire) sur l'ensemble de JADE : NON MESURÉ.** Sur les 6 CETATEXT échantillonnés, 6 sont à `texte_integral: true`. Le chiffre de 68 % pour l'avant-1990 figure dans les docstrings du dépôt et n'a pas été revérifié ici.
- **Judilibre PISTE** (`sources/judilibre.py`) : non mesuré, il faut des identifiants PISTE. Inventaire par lecture du code seulement.
- **Annuaire** : `total` et taux portent sur l'échantillon de 25 lignes rendu par une requête ; le fonds complet n'a pas été énuméré.

---

## FONDS 1. Judiciaire DILA (cass, capp, inca, constit, opendata tcom/tj)

### 1.1 D'où viennent les données

- Base SQLite locale unique : `sources/dila.py` l. 17, `DB_PATH = /opt/justicelibre/dila/judiciaire.db`, table `decisions` + index FTS5 `decisions_fts`.
- Alimentation : `index_dila.py` l. 185 à 215 (création de `decisions`), lancé par `update_dila.sh` l. 44 à 52 pour les tarballs DILA CASS, CAPP, CONSTIT et **INCA**. INCA n'est pas un fonds distinct côté API : ses décisions atterrissent dans la même table `decisions`.
- Les décisions de tribunaux judiciaires et de tribunaux de commerce / activités économiques arrivent par Judilibre (`judilibre_sync.py`, identifiants hexadécimaux de 24 caractères, visibles dans l'échantillon `dila_tcom` : `69e9868bcdc6046d47347a21`).
- Chemin de lecture : `search_api._dispatch_dila_sync` l. 714 à 778 → `dila.search` l. 161 ou `dila.lookup_by_field` l. 566 ; document complet `search_api.fetch_decision` l. 1131 à 1150 → `dila.get_decision` l. 670.

### 1.2 Champs rendus par l'API

**Résultat de recherche** (`_norm_dila`, `search_api.py` l. 75 à 89), 10 champs :

| Champ | Type | Exemple réel | Taux non vide (échantillon) |
|---|---|---|---|
| `id` | str | `JURITEXT000022858720` ; `69e9868bcdc6046d47347a21` ; `CONSTEXT000017667025` | 100 % (n=153, tous filtres) |
| `source` | str | `dila` | 100 % |
| `source_label` | str | `JUDICIAIRE` | 100 % |
| `title` | str | `Cour de cassation, civile, Chambre sociale, 22 septembre 2010, 09-40.952, Inédit` | 100 % |
| `juridiction` | str | `Cour de cassation` ; `Tribunal d'instance de Courbevoie` | 100 % |
| `date` | str ISO | `2010-09-22` | 100 % |
| `formation` | str | `CHAMBRE_SOCIALE` ; `Pôle 4- Chambre 1` ; `CT0279` ; `9ème chambre` | cass 100 % (n=33), CA 93,3 % (n=30), TJ 100 % (n=30), tcom 100 % (n=30), **constit 0 % (n=30)** |
| `numero` | str | `09-40952` ; `2002/04462` ; `93-1381` | cass 100 %, CA 93,3 %, TJ 96,7 %, tcom 100 %, constit 100 % |
| `ecli` | str | `ECLI:FR:CCASS:2016:SO00001` | **cass 78,8 % (n=33) ; CA 0 % (n=30) ; TJ 0 % (n=30) ; tcom 0 % (n=30) ; constit 0 % (n=30)** |
| `extract` | str HTML (`<em>`) | `…en matière de <em>harcèlement</em> <em>moral</em>…` | 100 % en recherche, **0 % en document complet** |

**Document complet** (`fetch_decision` l. 1131 à 1150) : les 10 champs ci-dessus plus 13 autres.

| Champ | Type | Exemple | Taux (n=8 par filtre) |
|---|---|---|---|
| `full_text` | str | `LA COUR DE CASSATION, CHAMBRE SOCIALE, a rendu l'arrêt suivant :…` | 100 % partout (cass, CA, TJ, tcom, constit) |
| `sommaire` | str | `CONTRAT DE TRAVAIL, RUPTURE - Licenciement - Nullité…` | cass 12,5 %, CA 37,5 %, TJ 12,5 %, tcom 0 %, constit 0 % |
| `abstrats` | str | `[1 PRINCIPAL] CONTRAT DE TRAVAIL, RUPTURE…` | cass 12,5 %, CA 62,5 %, TJ 12,5 %, tcom 100 % mais valeur `[]`, constit 0 % |
| `resume` | str | `[1] L'octroi de dommages-intérêts pour licenciement nul…` | cass 12,5 %, CA 37,5 %, TJ 0 %, tcom 0 %, constit 0 % |
| `renvois` | str | `[]` | CA 37,5 % (valeur `[]`), tcom 100 % (valeur `[]`), sinon 0 % |
| `rapporteur` | str | néant sur l'échantillon | **0 % partout (n=40)** |
| `publi_bull` | str | `non` | cass 100 %, CA 62,5 %, TJ 100 %, tcom 0 %, constit 0 % |
| `publi_recueil` | str | néant | 0 % partout |
| `nature_qualifiee` | str | `AN` | **constit 100 %**, 0 % ailleurs |
| `saisines` | str | `Monsieur le Président du Conseil constitutionnel, J'ai l'honneur…` | constit 12,5 %, 0 % ailleurs |
| `loi_def` | str | `77-1285 \| 1977-11-25 \| Loi complémentaire à la loi n° 59-1557…` | constit 12,5 %, 0 % ailleurs |
| `liens_textes` | str | `[typelien=CITATION sens=source] Articles L. 1152-1, L. 1152-3 et L. 1235-3…` | cass 12,5 %, CA 12,5 %, 0 % ailleurs |
| `extract` | str | vide | 0 % |

Attention aux valeurs `[]` : `abstrats` et `renvois` reviennent parfois avec la chaîne littérale `"[]"`, qui compte comme non vide mais ne porte rien. Sur tcom, `abstrats` est à 100 % « rempli » et à 100 % vide de sens.

### 1.3 Champs présents à la source mais NON rendus par l'API

`dila.get_decision` (l. 670 à 714) lit toute la ligne et retourne ces champs, que `fetch_decision` **jette** en ne reprenant que la sortie de `_norm_dila` plus sa liste explicite :

- `solution` (lu l. 688, présent aussi dans chaque ligne de `dila.search` l. 413) : **jamais servi**, ni en recherche ni en document.
- `nature` (l. 692, présent dans `dila.search`) : **jamais servi** hors du détour `nature_qualifiee`.
- `president` (l. 693) : **jamais servi**.
- `avocats` (l. 694) : **jamais servi**.
- `commissaire_gvt` (l. 704), `type_rec` (l. 705) : lus par `dila.get_decision`, absents de la liste de `fetch_decision` l. 1136 à 1149. Servis pour JADE (l. 1201 et 1202), pas pour le judiciaire.
- `texte_integral` et `note_texte` (calculés l. 697 par `note_texte_integral`) : **jetés** pour le fonds judiciaire, alors qu'ils sont servis pour JADE (l. 1194). Conséquence : le site peut servir un sommaire dans `full_text` sans l'avertissement que le MCP, lui, affiche.

Colonnes existant au schéma brut DILA et jamais ingérées dans la base du site (`parse_dila_bulk.JURIS_NEW_COLS`, l. 734 à 748, appliquées aux bases de l'entrepôt, mais absentes de `index_dila.EXTRA_COLS` l. 35 à 40) : `demandeur`, `defendeur`, `form_dec_att` (juridiction de la décision attaquée), `date_dec_att`, `siege_appel`, `juri_prem`, `lieu_prem`, `numeros_affaires` (tous les numéros de pourvois joints ; `numero` n'en garde qu'un), `observations`, `url_cc`, `titre_jo`, `nor`, `ancien_id`.

### 1.4 Identifiants et liens sortants

- `id` : JURITEXT / CONSTEXT (Légifrance), ou identifiant Judilibre hexadécimal de 24 caractères.
- `ecli` : présent seulement pour une partie de la Cour de cassation (78,8 % sur l'échantillon), nul ailleurs.
- `numero` : pourvoi, RG, ou numéro Conseil constitutionnel (`93-1381`).
- URL officielle : construite côté SSR par `ssr._cached_decision_url` l. 373 → `warehouse.sync_build_url` l. 185 ; un identifiant hexadécimal de 24 caractères devient `https://www.courdecassation.fr/decision/<id>` en local (`warehouse._judilibre_url` l. 320) ; les JURITEXT et CONSTEXT passent par `/v1/url` de l'entrepôt. **`/api/decision` ne renvoie PAS `source_url`** : seule la page SSR le calcule.
- Liens sortants vers les textes cités : `sources/citations.py` `detect_citations` l. 64 et `linkify` l. 115, appliqués dans `ssr.render_decision` l. 851 à 870. Couvre 16 codes (l. 11 à 27 du même fichier) plus CEDH, CONST, DDHC. Un article d'un code hors de cette liste n'est pas lié.

### 1.5 Ce qu'une fiche peut afficher, et ce qu'elle ne peut pas

Peut afficher, mesuré : juridiction, date, numéro, formation (sauf Conseil constitutionnel), ECLI pour une partie de la Cour de cassation, texte intégral, et pour une minorité de décisions le sommaire, les abstrats et le résumé. Pour le Conseil constitutionnel : la nature qualifiée (QPC, DC, AN…), à 100 % sur l'échantillon.

Ne peut pas afficher aujourd'hui, alors que la donnée EXISTE en base : la **solution** (cassation, rejet, annulation), la **nature** de la décision, le **président**, les **avocats**. `ssr.render_decision` prévoit pourtant des lignes « Solution » (l. 903) et « Nature » (l. 902) : elles sont mortes pour ce fonds, puisque `fetch_decision` ne fournit jamais ces clés.

Ne peut pas afficher, faute de donnée : rapporteur (0 % sur 40 documents), publication au recueil, parties, décision attaquée, historique de procédure.

---

## FONDS 2. Conseil d'État, ArianeWeb

### 2.1 D'où viennent les données

API Sinequa publique du Conseil d'État, `sources/ariane.py` l. 19 (`https://www.conseil-etat.fr/xsearch`, `SourceStr4=AW_DCE`), normalisation `_normalize_doc` l. 207 à 248. Texte intégral par le plugin `Service.downloadFilePagePlugin`, `fetch_full_text` l. 254 à 290, puis parsing de l'en-tête par `parse_header` l. 111 à 170. Dispatch : `search_api._dispatch_ariane` l. 364 à 426.

### 2.2 Champs rendus

**Recherche** (`_norm_ariane` l. 119 à 150), 11 champs. Échantillon : `q=éolienne`, 30 résultats.

| Champ | Type | Exemple | Taux |
|---|---|---|---|
| `id` | str | `/Ariane_Web/AW_DCE/\|96191` | 100 % |
| `source` / `source_label` | str | `ariane` / `CE` | 100 % |
| `title` | str | `Conseil d'État, n° 320227 (et 3 affaires jointes)` | 100 % |
| `juridiction` | str | `Conseil d'État` (constante) | 100 % |
| `date` | str ISO | `2009-01-21` | 100 % |
| `formation` | str | `6ème CHS` | 100 % |
| `numero` | str | `320227, 320228, 320292, 320293` | 100 % |
| `ecli` | str | `ECLI:FR:CESJS:2009:320227.20090121` | 100 % |
| `extract` | str | `1°) d'annuler l'ordonnance du 13 août 2008…` | 100 % |
| `relevance` | int | `95` | 100 % (seule source à porter un score) |

**Document complet** (`fetch_decision` l. 1240 à 1268), 9 champs, n=8 :
`id`, `source`, `source_label`, `title` (`Conseil d'État, n° 320227`), `juridiction`, `date` 100 %, `numero` 100 %, `ecli` 100 %, `full_text` 100 %, **`formation` 0 %**.

### 2.3 Champs présents à la source, non rendus

Deux pertes distinctes, toutes deux documentées dans le code.

1. `_normalize_doc` l. 237 à 248 produit `index` et `rank` (Sinequa) que `_norm_ariane` jette.
2. Surtout : `ariane.parse_header` l. 111 à 170 sait extraire **neuf** clés de l'en-tête (`numero`, `ecli`, `date`, `juridiction`, `publication`, `formation`, `president`, `rapporteur`, `rapporteur_public`). `fetch_decision` l. 1254 à 1267 n'en reprend que **trois** : `numero`, `date`, `ecli`. Sont donc extraits puis jetés, sur CHAQUE décision du Conseil d'État : la **publication** (« Publié au recueil Lebon », « Mentionné aux tables », « Inédit »), la **formation**, le **président**, le **rapporteur** et le **rapporteur public**. C'est exactement ce qu'une fiche de lecture d'arrêt du Conseil d'État doit montrer, et le parseur existe déjà.

### 2.4 Identifiants et liens sortants

`id` ArianeWeb (`/Ariane_Web/AW_DCE/|96191`), numéro de requête, ECLI complet à 100 %. URL officielle : `warehouse_server` l. 260 à 262 construit `https://www.conseil-etat.fr/arianeweb/#/view-document/<id>`. `build_source_url` (server.py l. 1311) accepte ce format.

### 2.5 Ce qu'une fiche peut afficher

Peut : juridiction, date de lecture, numéro (et affaires jointes), ECLI, formation en recherche, texte intégral, score de pertinence.
Ne peut pas aujourd'hui, alors que le parseur le sait faire : publication au Lebon, formation sur la page de document, président, rapporteur, rapporteur public.
Ne peut pas du tout : sommaire, abstrats, solution, parties, visas structurés.

---

## FONDS 3. Justice administrative (JADE bulk, open data TA/CAA, API live)

Trois provenances derrière une seule `source: "admin"`. La distinction n'est visible que par la forme de l'identifiant.

### 3.1 D'où viennent les données

- **Open data local** (préfixes `DTA_`, `DCA_`, `ORCA_`, `DCE_`) : `search_api._opendata_fts` l. 675 à 699 → `warehouse.search_fond("opendata")` l. 244 → `warehouse_server` fonds `opendata` l. 298 à 303, table `opendata_decisions` (schéma `download_opendata.py` l. 99 à 112). Document : `fetch_decision` l. 1167 à 1182.
- **Bulk JADE** (préfixe `CETATEXT`) : `sources/jade_remote.py` l. 121, fonds `jade` l. 272 à 277 de `warehouse_server.py`, table `jade_decisions` (schéma `parse_dila_bulk.py` l. 811 à 827 plus `JURIS_ENRICH_COLS` l. 719). Document : `fetch_decision` l. 1183 à 1206. Utilisé quand la requête porte des bornes de date (`_dispatch_admin` l. 511 à 519).
- **API live opendata.justice-administrative.fr** : `sources/juriadmin.py`, `_normalize_hit` l. 105 à 118, `get_decision` l. 190 à 215.

### 3.2 Champs rendus

**Recherche, voie open data** (`_norm_opendata` l. 595 à 618). Échantillons : `admin_ta` n=30, `admin_caa` n=30.

| Champ | Exemple | Taux TA (n=30) | Taux CAA (n=30) |
|---|---|---|---|
| `id` | `DTA_2303388_20251204` | 100 % | 100 % |
| `title` | `Tribunal Administratif de Poitiers — n° 2303388` | 100 % | 100 % |
| `juridiction` | `Tribunal Administratif de Poitiers` | 100 % | 100 % |
| `date` | `2025-12-04` | 100 % | 100 % |
| `formation` | `2ème chambre` | 80 % | 100 % |
| `numero` | `2303388` | 100 % | 100 % |
| `ecli` | néant | **0 %** | **0 %** |
| `extract` | extrait FTS5 | 90 % | **10 %** |

**Recherche, voie JADE** (`_norm_jade_bulk` l. 241 à 256), n=18, requête bornée 2015 à 2016 :
`id` `CETATEXT000030787488` 100 % ; `title` `CAA de MARSEILLE, Chambres réunies, 24/06/2015, 13MA02542, Inédit au recueil Lebon` 100 % ; `juridiction` `CAA de MARSEILLE` 100 % ; `date` 100 % ; `numero` `13MA02542` 100 % ; **`formation` 0 %** ; **`ecli` 0 %** ; **`extract` 0 %**.
Le `formation` vide vient de `jade_remote._normalize_hit` l. 110 à 118, qui ne sélectionne pas ce champ ; il est pourtant en base, puisqu'il revient à 100 % sur le document complet.

**Document complet, voie JADE** (`fetch_decision` l. 1183 à 1206), n=6, tous CETATEXT :

| Champ | Exemple | Taux |
|---|---|---|
| `full_text` | `Vu, I, la requête enregistrée le 26 juin 2013…` (30 114 caractères) | 100 % |
| `texte_integral` | `true` | 100 % |
| `sommaire` | `68-03-03-01-05 Urbanisme et aménagement du territoire. Permis de construire…` | 100 % |
| `abstrats` | `[PRINCIPAL] 68-03-03-01-05 Urbanisme…` | 100 % |
| `formation` | `Chambres réunies` | 100 % |
| `rapporteur` | `M. Philippe  PORTAIL` | 100 % |
| `commissaire_gvt` | `M. ROUX` | 100 % |
| `type_rec` | `excès de pouvoir` | 100 % |
| `publi_recueil` | `C` | 100 % |
| `resume` | néant | 0 % |
| `renvois` | néant | 0 % |
| `liens_textes` | néant | 0 % |
| `ecli` | néant | 0 % |
| `text_segments` | `[]` | 0 % |

**Document complet, voie open data** (`fetch_decision` l. 1167 à 1182), n=16 (TA + CAA) : `full_text` 100 %, `formation` 87,5 % à 100 %, `text_segments` 0 % pour les TA et 50 % pour les CAA (le champ est renseigné `[]` par le code l. 1179, donc toujours vide ; les 50 % viennent des documents servis par l'API live, `juriadmin.get_decision` l. 209). `ecli` 0 %, `sommaire`, `abstrats`, `rapporteur`, `type_rec` : **absents de la réponse** pour cette voie.

### 3.3 Champs présents à la source, non rendus

- Voie open data : `download_opendata.py` l. 99 à 112 stocke `type_decision`, `publication_code`, `last_modified`, `fetched_at`. `warehouse_server` l. 866 ne les sélectionne pas en recherche, et `_norm_opendata` ne les rend pas. `warehouse_server.get_decision` l. 929 fait pourtant `SELECT *`, donc le document brut les contient : c'est `fetch_decision` l. 1175 à 1180 qui les jette.
- Voie open data, document : `sommaire`, `abstrats`, `resume`, `rapporteur`, `type_rec`, `publi_recueil` ne sont **pas** servis, alors qu'ils le sont pour JADE. Deux décisions administratives voisines n'offrent donc pas la même fiche selon la voie par laquelle on est arrivé.
- Voie JADE : `jade_decisions` porte au schéma (`parse_dila_bulk.py` l. 811 à 827) `solution`, `nature`, `president`, `avocat_general`, `avocats`, jamais servis. Plus les colonnes `JURIS_NEW_COLS` l. 734 à 748 : `demandeur`, `defendeur`, `form_dec_att`, `date_dec_att`, `juri_prem`, `lieu_prem`, `numeros_affaires`.
- API live : `juriadmin._normalize_hit` l. 105 à 118 expose `type`, `publication_code`, `last_modified` que `_norm_admin` (l. 224 à 239) jette.
- `jade_remote.get_admin_decision` l. 200 sait produire `homonymes` et `avertissement` (l. 73 à 107 : 7 938 numéros du Conseil d'État portés par plusieurs décisions). Ce signal **n'existe pas** dans le chemin du site : ni `_dispatch_admin` ni `fetch_decision` ne l'appellent.

### 3.4 Identifiants et liens sortants

`id` CETATEXT (Légifrance) ou `DTA_/DCA_/ORCA_/DCE_` (open data). Numéro de requête à 100 %. **ECLI à 0 % sur les trois voies** dans tous les échantillons. URL officielle par `build_source_url` pour les CETATEXT ; pour les identifiants open data l'URL est celle d'opendata.justice-administrative.fr, construite par l'entrepôt.

### 3.5 Ce qu'une fiche peut afficher

Sur une décision CETATEXT : juridiction, date, numéro, formation, rapporteur, rapporteur public, type de recours, publication au Lebon (A/B/C), sommaire et abstrats, texte intégral avec le drapeau `texte_integral`. C'est de loin la fiche la plus riche du site.
Sur une décision open data (donc toutes les récentes) : juridiction, date, numéro, formation, texte. Rien d'autre.
Aucune des trois voies ne permet d'afficher l'ECLI, la solution, les parties, ni de signaler qu'un numéro est porté par plusieurs décisions.

---

## FONDS 4. CEDH

### 4.1 D'où viennent les données

Base SQLite locale `judiciaire.db`, table `cedh_decisions` et index `cedh_fts` (`sources/european.py` l. 12, `search_cedh` l. 72 à 143, `get_cedh` l. 146 à 168). Schéma : `scrape_cedh.py` l. 56 à 68, plus une colonne `appno` ajoutée après coup (utilisée `european.py` l. 103 et 136 ; `scripts/apply_fts_triggers.py` l. 42 mentionne `appno_norm`).

### 4.2 Champs rendus

⚠️ **Par l'API publique du site : NON MESURÉ.** Trois requêtes, trois échecs (`sources_en_echec: ["cedh"]`, 42 à 44 s ; un 504). Le fonds ne répond pas aujourd'hui.

**Par le MCP** `search_cedh(query="procès équitable", limit=25)`, n=25, 11 champs, tous à 100 % :

| Champ | Type | Exemple |
|---|---|---|
| `id` (itemid HUDOC) | str | `001-142729` |
| `docname` | str | `AFFAIRE SCHATSCHASCHWILI c. ALLEMAGNE` |
| `ecli` | str | `ECLI:CE:ECHR:2014:0417JUD000915410` |
| `date` | str ISO | `2014-04-17` |
| `doctype` | str | `HFJUD` |
| `article` | str | `6;6+6-3-d;6-1;6-3;6-3-d;35` |
| `conclusion` | str | `Partiellement irrecevable;Non-violation de l'article 6+6-3-d…` |
| `importance` | str | `3` (échelle HUDOC 1 à 4) |
| `respondent` | str | `DEU` |
| `appno` | str | `9154/10` ; `29522/95;30056/96;30574/96` |
| `snippet` | str HTML | extrait avec `<em>` |

**Ce que le site en garde** (`_norm_cedh`, `search_api.py` l. 264 à 279) : `id`, `title` (= `docname`), `juridiction` constante `Cour EDH`, `date`, `formation` (= `doctype`, donc un code technique affiché comme une formation), `numero` **recalculé depuis l'ECLI** par `_cedh_numero` l. 258 à 261, `ecli`, `extract`, `article`.

### 4.3 Champs présents à la source, non rendus par le site

- `appno` : le vrai numéro de requête est en base et exposé par le MCP ; `_norm_cedh` l. 275 préfère le **re-dériver de l'ECLI**. Quand l'ECLI manque ou que l'affaire est jointe (`29522/95;30056/96;30574/96`), le numéro servi est vide ou tronqué à une seule requête.
- `conclusion` (violation / non-violation, article par article) : **jeté**. C'est l'information la plus utile d'un arrêt de la Cour.
- `importance` (1 à 4, l'arrêt de principe se repère là) : **jeté**.
- `respondent` (État défendeur) : **jeté**.
- `originating_body` : colonne du schéma (`scrape_cedh.py` l. 65), lue nulle part, ni par `search_cedh` ni par `get_cedh`.
- Document complet (`fetch_decision` l. 1151 à 1158) : `_norm_cedh` plus `full_text`. Donc conclusion, importance, respondent, appno restent absents de la page de lecture.

### 4.4 Identifiants et liens sortants

itemid HUDOC (`001-142729`) et ECLI complet à 100 % sur l'échantillon MCP. `build_source_url` reconnaît les itemid `001-*`.

### 4.5 Ce qu'une fiche peut afficher

Peut, si le fonds répond : nom d'affaire, date, ECLI, type de document, articles de la Convention en cause, texte.
Ne peut pas, alors que la donnée est là : le sens de l'arrêt (violation ou non), le niveau d'importance, l'État défendeur, le numéro de requête exact. Une fiche CEDH sans « violation de l'article 6 » et sans le pays n'est pas une fiche.
Et aujourd'hui, sur le site, elle ne peut rien afficher du tout : le fonds est en échec.

---

## FONDS 5. CJUE

### 5.1 D'où viennent les données

Même base locale, table `cjue_decisions`, index `cjue_fts` (`sources/european.py` l. 171 à 243 et 246 à 265). Schéma `scrape_cjue.py` l. 43 à 50 : `celex`, `ecli`, `date`, `type`, `title`, `text`. Une colonne `affaire_num` existe en plus (utilisée `european.py` l. 208), absente du `CREATE TABLE` d'origine.

### 5.2 Champs rendus

**Recherche** (`_norm_cjue` l. 281 à 297), n=50, `q=données personnelles` :

| Champ | Exemple | Taux |
|---|---|---|
| `id` / `numero` | `62013CJ0101` (CELEX) | 100 % / 100 % |
| `title` | `Arrêt de la Cour (quatrième chambre) du 2 octobre 2014. — U contre Stadt Karlsruhe. —…` | 100 % |
| `juridiction` | `CJUE` (constante) | 100 % |
| `date` | `2014-10-02` | 100 % |
| `formation` | `JUDG` (= le champ `type`, code technique) | 100 % |
| `ecli` | `ECLI:EU:C:2014:2249` | 100 % |
| `extract` | extrait FTS5 | 100 % |

**Document complet** (`fetch_decision` l. 1159 à 1166), n=8 : les mêmes plus `full_text` 100 %.

### 5.3 Champs présents à la source, non rendus

- `affaire_num` (`C-101/13`, la forme sous laquelle un juriste cite un arrêt de la Cour) : en base, utilisée pour le classement l. 208, **jamais rendue**. Le champ `numero` sert le CELEX à la place.
- Le titre contient le nom des parties, la date, le type de renvoi, séparés par des tirets ; aucun découpage n'est fait.
- Note de fiabilité : `european._is_forged_ecli` l. 30 à 41 vide l'ECLI quand il a été fabriqué par l'ancien script. Sur l'échantillon, `ecli` est à 100 % non vide, donc les 50 ECLI rendus sont des ECLI réels.

### 5.4 Identifiants et liens sortants

CELEX 100 %, ECLI 100 %. `build_source_url` couvre CELEX `6XXXXCJXXXX` et `ECLI:*` vers EUR-Lex.

### 5.5 Ce qu'une fiche peut afficher

Peut : CELEX, ECLI, date, type de décision, titre complet, texte.
Ne peut pas : le numéro d'affaire au format `C-101/13`, les parties isolées, la juridiction de renvoi, le dispositif, les conclusions de l'avocat général rattachées (elles existent en base comme documents distincts, type `CC`, mais rien ne les relie à l'arrêt).

---

## FONDS 6. Conseil constitutionnel

Pas un fonds séparé : il vit dans la base judiciaire, `juridiction = 'Conseil constitutionnel'`, filtre `juridiction=constit` (`search_api.JURI_DISPATCH` l. 322, `_dispatch_dila_sync` l. 724). Outils dédiés : `dila.search_cc` l. 434 et `dila.get_cc_decision` l. 504.

Mesuré (`q=liberté&juridiction=constit`, n=30 en recherche, n=8 en document) :
`id` `CONSTEXT000017667025` 100 % ; `numero` `93-1381` 100 % ; `date` 100 % ; `juridiction` 100 % ; `title` `A.N.` 100 % mais souvent réduit à la nature ; **`formation` 0 %** ; **`ecli` 0 %** ; `full_text` 100 % ; `nature_qualifiee` `AN` **100 %** ; `saisines` 12,5 % ; `loi_def` 12,5 % ; `sommaire`, `abstrats`, `resume`, `renvois`, `publi_bull`, `liens_textes` **0 %**.

Non rendu alors que présent : `nature` brute (QPC, DC, L, SEN, AN, PDR, ORGA, REF, ELEC, I ; la liste est à `dila.py` l. 141), `solution`, `observations` du Gouvernement, `url_cc`, `titre_jo`, `nor` (colonnes déclarées `JURIS_NEW_COLS` l. 743 à 746, non ingérées par `index_dila.py`).
Piège documenté : un même numéro existe en plusieurs natures (2019-778 DC et 2019-778 QPC). `dila.get_cc_decision` l. 545 renvoie `_ambiguous` dans ce cas, mais ce chemin n'est **pas** celui du site.

Une fiche peut afficher : numéro, date, nature qualifiée, texte, et pour une minorité la saisine et la loi déférée. Elle ne peut pas afficher la solution (conformité, non conformité, réserve), ni les visas, ni le commentaire officiel.

---

## FONDS 7. LEGI (articles de code et de loi)

### 7.1 D'où viennent les données

Entrepôt distant, fonds `legi`, table `legi_articles`, index `legi_articles_fts` (`warehouse_server.py` l. 268 à 273 ; schéma `parse_dila_bulk.py` l. 240 à 252, plus les colonnes `jorftext` et `hierarchie` ajoutées par la migration du 8 septembre 2026, détectées à l'exécution par `_legi_cols` l. 578).
Deux routes distinctes :
- recherche plein texte : `search_api._dispatch_legi` l. 643 à 656 → `warehouse.search_fond("legi")`, rendu par `_norm_legi` l. 621 à 640 ;
- article par référence : `/api/law` → `warehouse.sync_get_law` l. 207 → `warehouse_server.law_at_date` l. 460 → `_law_row_to_dict` l. 621 à 646.

### 7.2 Champs rendus

**Recherche** (`_norm_legi`), n=50, `q=responsabilité&juridiction=legi`, 12 champs, tous à 100 % sauf `ecli` à 0 % (constante vide) :
`id` `LEGIARTI000022357525`, `title` `Article 1655 sexies — Code général des impôts, CGI.`, `juridiction` = titre du texte parent, `formation` = état traduit (`modifié`), `etat` `MODIFIE`, `date` = `date_debut` `2010-12-11`, `numero` `1655 sexies`, `legitext` `LEGITEXT000006069577`, `extract`.

**Article par référence** (`GET /api/law`), n=30 articles sur 30 codes, 12 champs :

| Champ | Exemple | Taux |
|---|---|---|
| `legiarti` | `LEGIARTI000032041571` | 100 % |
| `num` | `1240` | 100 % |
| `code` | `CC` | 100 % |
| `legitext` | `LEGITEXT000006070721` | 100 % |
| `titre_texte` | `Code civil` | 100 % |
| `titre_section` | `Chapitre Ier : La responsabilité extracontractuelle en général` | **100 % (30/30)** |
| `etat` | `VIGUEUR` | 100 % |
| `date_debut` | `2016-10-01` | 100 % |
| `date_fin` | `2999-01-01` | 100 % |
| `texte` | texte de l'article | 100 % |
| `nota` | `Conformément à l'article 6 du décret n° 2022-245…` | **43,3 % (13/30)** |
| `source_url` | `https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000032041571/2016-10-01` | 100 % |

Correction à porter : la docstring de `search_legi` (`server.py` l. 1833 à 1838) et celle de `get_law_article` affirment que la hiérarchie des sections n'est pas ingérée et que `titre_section` est faux. **C'est périmé.** Mesuré le 13 septembre 2026 : `titre_section` est rempli et juste sur 30 articles sur 30, alimenté par `_titre_section` (`warehouse_server.py` l. 604 à 618) à partir de la colonne `hierarchie`.

**Document complet** (`/api/decision?source=legi`, `fetch_decision` l. 1098 à 1114), n=8 : les champs de `_norm_legi` plus `full_text` 100 %, `date_fin` 100 %, `nota` 37,5 %, `text_segments` toujours `[]`.

**Versions** (`/api/law/versions`) : même dictionnaire que `/api/law`, par version, triées par `date_debut` croissante (`warehouse_server.law_versions` l. 531 à 557).

### 7.3 Champs présents à la source, non rendus

- **`hierarchie`** : la colonne contient la liste JSON complète des niveaux (partie, livre, titre, chapitre, section). `_titre_section` l. 616 n'en rend **que le dernier**. Le fil d'Ariane complet, qui est précisément ce qu'une page de lecture d'article doit montrer, existe et n'est pas servi.
- **`jorftext`** : lu pour choisir `/codes/` contre `/loda/` dans l'URL (l. 645), jamais rendu.
- `legi_textes` (table parallèle, `parse_dila_bulk.py` l. 228 à 239) porte `titre_long`, `nature`, `etat`, `date_publi`, `num_jorf`, `nor` du texte parent. **Aucune route ne joint cette table** : une page d'article ne peut pas dire de quelle loi ou de quel décret vient la version qu'elle affiche.
- En recherche, `_norm_legi` ne rend ni `date_fin` ni `nota` ; il faut un second appel.
- `/api/law` ne rend pas le nombre de versions ni les dates des versions voisines : il faut `/api/law/versions`.

### 7.4 Identifiants et liens sortants

LEGIARTI, LEGITEXT, `source_url` Légifrance **daté** à 100 % (forme `/article_lc/<LEGIARTI>/<date>`), ce qui est le lien le plus solide de tout le site. `resolve_law_number` (`/api/law/resolve`) traduit un numéro de loi en LEGITEXT ou JORFTEXT. `search_decisions_citing` (server.py l. 2118) fait le lien inverse, article vers jurisprudence, mais **uniquement en MCP** : aucune route REST.

### 7.5 Ce qu'une fiche peut afficher

Peut, et c'est solide : numéro, code, chapitre ou section de rattachement, état (vigueur, modifié, abrogé), date d'entrée en vigueur, date de fin, nota pour 43 % des articles, lien Légifrance daté, historique complet des versions.
Ne peut pas : le plan complet du code au-dessus de l'article, l'article précédent et l'article suivant, le texte modificateur (quelle loi a créé cette version), les décisions qui citent l'article (existe en MCP, pas en REST).

---

## FONDS 8. JORF

### 8.1 D'où viennent les données

Entrepôt, fonds `jorf`, table `jorf_textes` (`warehouse_server.py` l. 274 à 279 ; schéma `parse_dila_bulk.py` l. 466 à 477). Servi par `sources/jorf_remote.py` l. 14 à 47, exposé **uniquement** par l'outil MCP `search_jorf` (`server.py` l. 1889).

### 8.2 Champs rendus

`search_jorf(query="protection des données", limit=30)`, n=30, 6 champs :

| Champ | Exemple | Taux |
|---|---|---|
| `id` (jorftext) | `JORFTEXT000039002295` | 100 % |
| `titre` | `Délibération n°2023-062 du 13 avril 2023` | 100 % |
| `nature` | `AVIS`, `DELIBERATION`, `ARRETE`, `DECRET` | 100 % |
| `date_publi` | `2019-08-31` | 100 % |
| `ministere` | `Ministère de la justice` | **43,3 % (13/30)** |
| `extract` | extrait FTS5 | 100 % |

### 8.3 Champs présents à la source, non rendus

`jorf_textes` porte aussi `titre_long`, `date_signature`, `num_jorf`, `nor`, `texte`, `nota` (`parse_dila_bulk.py` l. 467 à 476). `jorf_remote.search` l. 34 à 41 n'en reprend aucun. Le **NOR**, qui est l'identifiant de référence d'un texte réglementaire et la clé pour tout recours pour excès de pouvoir, est en base et n'est servi nulle part. La **date de signature**, distincte de la date de publication, non plus. `jorf_remote.get_text` l. 50 renvoie la ligne brute (donc tout), mais **aucun outil MCP ni aucune route REST ne l'appelle** : la fonction est morte.

### 8.4 Identifiants et liens sortants

JORFTEXT. `build_source_url` le reconnaît. Pas de NOR servi, donc pas de lien par NOR.

### 8.5 Ce qu'une fiche peut afficher

Peut : titre, nature, date de publication, ministère pour 43 % des textes, extrait.
Ne peut pas : le texte lui-même (aucune route de lecture branchée), le NOR, la date de signature, le numéro de JO, le nota.
**Il n'existe aujourd'hui aucune page de lecture possible pour un texte du Journal officiel.**

---

## FONDS 9. KALI (conventions collectives)

Entrepôt, fonds `kali`, table `kali_textes` (`warehouse_server.py` l. 280 à 285 ; schéma `parse_dila_bulk.py` l. 1069 à 1078). Servi par `sources/kali_remote.py` l. 13 à 41, exposé uniquement par MCP `search_kali` (`server.py` l. 1925).

`search_kali(query="licenciement préavis", limit=30)`, n=30, 6 champs :

| Champ | Exemple | Taux |
|---|---|---|
| `id` | `KALIARTI000005840302` | 100 % |
| `idcc` | `1483` | **83,3 % (25/30)** |
| `titre` | `Convention collective nationale du commerce de détail de l'habillement… du 25 novembre 1987` | 100 % |
| `nature` | `Article` (valeur unique sur tout l'échantillon) | 100 % |
| `date_publi` | `2005-01-01` | 100 % |
| `extract` | extrait FTS5 | 100 % |

Non rendus alors que présents au schéma : `etat`, `date_debut`, `date_fin`, `texte`, et la colonne `texte_id` (indexée `parse_dila_bulk.py` l. 1088). `kali_remote.get_text` l. 44 existe et **n'est appelée par rien**.
Le champ `nature` annonce `CONVENTION, ACCORD, AVENANT` au schéma (l. 1072) mais vaut `Article` sur 30 lignes sur 30 : ce que l'on indexe, ce sont les articles, pas les conventions.

Une fiche peut afficher : IDCC pour 83 % des lignes, titre de la convention, date. Elle ne peut pas afficher le texte de l'article, son état (en vigueur ou dénoncé), ni ses dates d'effet. Une convention collective dont on ne sait pas si elle est en vigueur ne sert à rien.

---

## FONDS 10. Avis et doctrine (CADA, Défenseur des droits, rapporteurs publics, BOFiP, Code du travail numérique)

### 10.1 D'où viennent les données

Entrepôt, fonds `doctrine`, table `docs`, index `docs_fts` (`warehouse_server.py` l. 308 à 314). Clé primaire composite exposée comme `source_id:doc_id` (l. 313). Colonnes alimentées par `ingest_cada.py` l. 180 à 182 : `source_id`, `doc_id`, `type`, `titre`, `date`, `administration`, `sujet`, `contenu`, `tags`, `source_url`, `partie`, `objet`, plus `fetched_at`.
Sous-fonds : `cada`, `ddd`, `ariane_crp`, `bofip`, `ctn` (`search_api._DOCTRINE_SOURCES` l. 558 à 561).
Chemin site : `_dispatch_doctrine` l. 659 à 672, rendu par `_norm_doctrine` l. 564 à 592 ; document `fetch_decision` l. 1115 à 1130.

### 10.2 Champs rendus

**Recherche via le site** (`juridiction=doctrine`), n=50, `q=communication de documents`, 12 champs :

| Champ | Exemple | Taux |
|---|---|---|
| `id` | `ariane_crp:4960`, `cada:20212413` | 100 % |
| `title` | `Conclusions 427460 (2020-07-22)` | 100 % |
| `juridiction` | `Conseil d'État` (= le champ `administration`) | 100 % |
| `organisme` | `Rapporteur public` | 100 % |
| `date` | `2020-07-22` | 100 % |
| `formation` | `Conclusion` (= le champ `type`) | 100 % |
| `numero` | `4960` (= `doc_id`) | 100 % |
| `source_url` | `https://www.conseil-etat.fr/fr/arianeweb/CRP/conclusion/2020-07-22/427460` | **100 %** |
| `ecli` | vide par construction | 0 % |
| `extract` | extrait FTS5 | 100 % |

**Recherche via le MCP** `search_doctrine`, n=40 : mêmes lignes brutes, avec en plus `source_id`, `doc_id` et `sujet` (`sujet` non vide sur 37 sur 40 ; les 3 vides sont des `ariane_crp`).

**Document complet** (`/api/decision?source=doctrine`), n=8 : les 12 champs plus `full_text` 100 %, `sujet` 87,5 %, `tags` 100 % (`4ème CHS,AFF:427460`), `text_segments` toujours `[]`.
`get_doctrine_document` en MCP renvoie la ligne brute entière, donc aussi `partie` (`I`), `objet` (vide sur le document testé), `fetched_at` (`2026-09-08 18:08:04`).

### 10.3 Champs présents à la source, non rendus par le site

`_norm_doctrine` ne rend ni `source_id`, ni `doc_id` séparés, ni `partie`, ni `objet`, ni `fetched_at`. `partie` est l'indication de la partie de l'avis CADA concernée, utile pour citer.
Le `sujet` de la CADA est une taxonomie hiérarchique complète (`Economie, Industrie, Agriculture/Marchés Et Contrats Publics | Contrats administratifs, Marché public`) servie comme une chaîne brute, jamais découpée en thème et mots-clés.

### 10.4 Défauts mesurés qui touchent l'affichage

- **Dates hétérogènes.** La CADA date en `jj/mm/aaaa` (`08/07/2021`) ; `ddd` et `ariane_crp` en ISO. `_norm_doctrine` l. 575 à 578 corrige au passage pour le site, mais le MCP et l'entrepôt servent la forme brute, et `warehouse_server.py` l. 793 le dit lui-même : tri et bornes de date « peu fiables sur ce sous-fonds ».
- **Titres dégénérés.** Mesuré : `ariane_crp:2511` a pour titre `N°` et `ariane_crp:4730` a pour titre `N° 417465` alors que sa `source_url` pointe l'affaire 438152. Sur les conclusions de rapporteurs publics, le titre n'est pas fiable comme identifiant d'affaire.

### 10.5 Ce qu'une fiche peut afficher

Peut, et c'est le fonds le mieux outillé pour le lien : organisme, type de document (avis, conseil, conclusion), administration concernée, date, sujet, texte intégral, **et l'URL officielle à 100 %**.
Ne peut pas : le numéro d'affaire du Conseil d'État derrière une conclusion de rapporteur public (il est dans `tags`, sous la forme `AFF:427460`, jamais extrait), le sens de l'avis autrement qu'en lisant le texte (la CADA le met en fin de contenu, `--- Sens et motivation ---\nFavorable`, jamais en champ), le lien vers la décision juridictionnelle qui a suivi.

---

## FONDS 11. CNIL

Entrepôt, fonds `cnil`, table `cnil_deliberations` (`warehouse_server.py` l. 286 à 291 ; schéma `parse_dila_bulk.py` l. 1320 à 1327 : `id`, `numero`, `titre`, `date`, `formation`, `texte`). Servi par `sources/cnil_remote.py`, exposé uniquement par MCP `search_cnil` (`server.py` l. 2009).

`search_cnil(query="vidéosurveillance", limit=30)`, n=30 :
`id` `CNILTEXT000027435334` 100 % ; `numero` `2012-022`, `MED-2018-024`, `SAN-2019-006` 100 % ; `titre` 100 % ; `date` 100 % ; **`formation` 0 % (0/30)** ; `extract` 100 %.

Le champ `texte` n'est pas servi en recherche. `cnil_remote.get_deliberation` l. 38 existe et n'est appelée par aucun outil.
Le bloc `if source == "cnil"` de `search_api.fetch_decision` (l. 1222 à 1239) est **mort** : la garde de la l. 1096 refuse `cnil` avant d'y arriver. `ssr.py` déclare pourtant un `SOURCE_LABELS["cnil"]` (l. 397) et un `BULK_SOURCES["cnil"]` (l. 414), et `render_sitemap_cnil` (l. 1483) publie des URL de décisions CNIL au sitemap. **Ces URL mènent à une page qui ne peut pas se construire.** À vérifier en priorité.

Une fiche peut afficher : numéro, titre, date, texte (si la route était branchée). Elle ne peut pas afficher la formation (0 %), la nature de la délibération (sanction, mise en demeure, avis, autorisation : c'est déductible du préfixe du numéro, jamais mis en champ), le montant d'une sanction, l'organisme visé.

---

## FONDS 12. Travaux préparatoires

**Aucun fonds n'existe.** Vérifié par recherche sur tout le dépôt (`travaux`, `préparatoire`, `dossier législatif`, `exposé des motifs`, sur `*.py`, `*.html`, `*.md`).

Les seules occurrences sont des libellés d'interface :
- `web/hub.html` l. 389 à 393 déclare une rubrique « Travaux préparatoires » avec quatre sous-entrées, toutes marquées `soon: 'à venir'` : `dole` (dossiers législatifs), `debats` (débats AN et Sénat), `questions` (questions au gouvernement), `rapports` (rapports, avis du Conseil d'État). Aucune ne porte de compte.
- Les maquettes de `web/maquettes/` reprennent le même libellé, sans donnée.

Il n'y a ni base, ni table, ni fonds déclaré dans `warehouse_server.FONDS` (l. 267 à 317), ni parseur dans `parse_dila_bulk.py` (les fonds traités y sont `legi`, `jorf`, `jade`, `kali`, `cnil`, `cass`, `capp`, `constit`, `inca`, l. 1414 et voisines). Le bulk DILA DOLE, qui porterait les dossiers législatifs, n'est ni téléchargé (`orchestrate_bulk.sh` l. 10 : `FUNDS=(legi jorf inca jade kali constit capp cnil)`) ni parsé.

Une fiche ne peut donc **rien** afficher au titre des travaux préparatoires. L'intitulé existe dans le hub ; la donnée n'existe pas.

---

## FONDS 13. Annuaire

### 13.1 D'où viennent les données

Trois fichiers statiques, agrégés en RAM par `server._load_annuaire` (l. 2535 à 2624) :
- `annuaire_juridictions.json` (dump DILA plus API `api-lannuaire.service-public.fr`),
- `annuaire_prada.json` (personnes responsables de l'accès aux documents administratifs),
- `pdf_findings.csv` (adresses extraites de PDF gouvernementaux, séparateur `;`).

La page `web/annuaire.html` l. 6440 à 6442 lit directement `/data/annuaire_juridictions.json`, `/data/annuaire_prada.json` et `/data/annuaire_meta.json` en fetch client. **Il n'existe aucune route REST d'annuaire** : le seul accès programmatique est l'outil MCP `search_annuaire` (`server.py` l. 2630).

### 13.2 Champs rendus

`search_annuaire(query="tribunal administratif", limit=25)`, n=25, source `api` :

| Champ | Exemple | Taux (n=25) |
|---|---|---|
| `mail` | `greffe.ta-lille@juradm.fr` | 100 % |
| `organisme` | `Tribunal administratif - Lille` | 100 % |
| `service` | vide | **0 %** |
| `categorie` | `Tribunal administratif` | 100 % |
| `categorie_slug` | `ta` | 100 % |
| `source` | `api` | 100 % |
| `tel` | `03 59 54 23 42` | 100 % |
| `site` | `https://lille.tribunal-administratif.fr/` | 100 % |
| `adresse` | `5 rue Geoffroy Saint-Hilaire, 59000 Lille \| 5 rue Geoffroy Saint-Hilaire, CS 62039, 59014 Lille Cedex` | 100 % |
| `date_source` | vide | **0 %** |
| `url_page` | `https://justicelibre.org/annuaire.html` | 100 % |

Les lignes de source `pdf` portent en plus `role`, `source_url`, `source_label`, `source_page` et `preuve_url` (copie archivée), d'après `_load_annuaire` l. 2598 à 2617. **Non mesuré** : aucune ligne `pdf` dans l'échantillon tiré.

### 13.3 Champs présents à la source, non rendus

`_load_annuaire` l. 2549 à 2561 ne reprend de `annuaire_juridictions.json` que `nom`, `type`, `source`, `tel`, `site`, `adresse_postale` et la liste `mails`. Les autres clés du dump DILA (horaires, coordonnées géographiques, identifiant SIRET ou code service, le cas échéant) ne sont ni lues ni servies. Le champ `adresse` agrège deux adresses distinctes dans une seule chaîne séparée par `|`, ce qui interdit d'afficher séparément l'adresse de visite et l'adresse postale.

### 13.4 Ce qu'une fiche peut afficher

Peut : nom de l'organisme, catégorie, courriel, téléphone, site, adresse, et pour les lignes issues de PDF la traçabilité complète jusqu'à une copie archivée du document d'origine.
Ne peut pas : la date à laquelle l'adresse a été vue (0 % sur les lignes `api`), le service précis (0 %), la distinction adresse de visite contre adresse postale.

---

## FONDS 14. Judilibre par PISTE (voie authentifiée)

`sources/judilibre.py`, `_normalize_decision` l. 85 à 99 et `_normalize_full_decision` l. 102 à 121. Accessible seulement avec des identifiants PISTE de l'utilisateur, donc **NON MESURÉ**.

Par lecture du code, cette voie est la plus riche du site pour le judiciaire et sert des champs qu'aucun autre chemin n'apporte : `solution`, `publication`, `summary`, `highlights` en recherche ; `zones`, `numbers`, `visa`, `themes`, `timeline` (chronologie de la procédure), `rapprochements` (jurisprudence voisine), `titles_and_summaries`, `contested`, `forward`, `nac`, `portalis`, `update_date` en document.
Aucune de ces données n'est recopiée dans la base locale ni servie par `/api/decision` : une décision lue sans identifiants PISTE n'en verra rien.

---

## TABLEAU RÉCAPITULATIF FONDS × CHAMPS

Légende : ✅ servi et mesuré rempli ; ⚠️ servi mais partiellement ou trompeusement rempli ; ❌ non servi ; ∅ inexistant à la source ; NM non mesuré.
Les pourcentages entre parenthèses sont ceux de l'échantillon décrit au manifeste.

| Champ | dila cass | dila CA | dila TJ/tcom | constit | ariane CE | admin JADE | admin open data | CEDH | CJUE | LEGI | JORF | KALI | doctrine | CNIL | annuaire |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| identifiant | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ∅ |
| juridiction / organisme | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ constante | ⚠️ constante | ✅ texte parent | ∅ | ∅ | ✅ | ∅ | ✅ |
| date | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ 2 formats | ✅ | ❌ (0 %) |
| numéro | ✅ | ⚠️ (93 %) | ⚠️ (97 à 100 %) | ✅ | ✅ | ✅ | ✅ | ⚠️ re-dérivé de l'ECLI | ⚠️ CELEX, pas `C-101/13` | ✅ | ∅ | ∅ | ✅ doc_id | ✅ | ∅ |
| formation / chambre | ✅ | ⚠️ (93 %) | ✅ | ❌ (0 %) | ⚠️ recherche seule | ⚠️ doc seul | ⚠️ (80 à 100 %) | ⚠️ = doctype | ⚠️ = type | ∅ | ∅ | ∅ | ⚠️ = type | ❌ (0 %) | ∅ |
| ECLI | ⚠️ (78,8 %) | ❌ (0 %) | ❌ (0 %) | ❌ (0 %) | ✅ | ❌ (0 %) | ❌ (0 %) | ✅ | ✅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| texte intégral | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | NM | ✅ | ✅ | ❌ route absente | ❌ route absente | ✅ | ❌ route morte | ∅ |
| drapeau texte = sommaire | ❌ calculé puis jeté | ❌ | ❌ | ❌ | ∅ | ✅ (100 %) | ❌ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| sommaire / abstrats | ⚠️ (12,5 %) | ⚠️ (37 à 62 %) | ⚠️ (0 à 12,5 %) | ❌ (0 %) | ❌ jeté | ✅ (100 %) | ❌ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| solution / sens | ❌ en base | ❌ en base | ❌ en base | ❌ en base | ∅ | ❌ en base | ∅ | ❌ `conclusion` en base | ∅ | ∅ | ∅ | ∅ | ❌ en fin de texte | ∅ | ∅ |
| rapporteur | ❌ (0 %) | ❌ (0 %) | ❌ (0 %) | ❌ | ❌ parsé puis jeté | ✅ (100 %) | ❌ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| rapporteur public | ∅ | ∅ | ∅ | ∅ | ❌ parsé puis jeté | ✅ (100 %) | ❌ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| publication (Lebon, Bulletin) | ⚠️ `publi_bull` = `non` | ⚠️ (62,5 %) | ⚠️ | ❌ | ❌ parsé puis jeté | ✅ `C` (100 %) | ❌ | ⚠️ `importance` jeté | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| type de recours | ∅ | ∅ | ∅ | ∅ | ∅ | ✅ (100 %) | ❌ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| parties | ❌ non ingéré | ❌ | ❌ | ❌ | ∅ | ❌ non ingéré | ∅ | ⚠️ dans `docname`, `respondent` jeté | ⚠️ dans `title` | ∅ | ∅ | ∅ | ✅ `administration` | ∅ | ✅ |
| liens vers textes cités | ⚠️ (12,5 %) | ⚠️ (12,5 %) | ❌ (0 %) | ❌ | ∅ | ❌ (0 %) | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| URL officielle dans l'API | ❌ SSR seul | ❌ SSR seul | ❌ SSR seul | ❌ SSR seul | ❌ SSR seul | ❌ SSR seul | ❌ SSR seul | ❌ SSR seul | ❌ SSR seul | ✅ (100 %) | ❌ | ❌ | ✅ (100 %) | ❌ | ✅ `url_page` |
| état / vigueur | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ✅ (100 %) | ❌ en base | ❌ en base | ∅ | ∅ | ∅ |
| rattachement (section, code, IDCC, ministère) | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ✅ `titre_section` (100 %) | ⚠️ `ministere` (43,3 %) | ⚠️ `idcc` (83,3 %) | ✅ `sujet` | ∅ | ✅ `categorie` |
| extrait de recherche | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ (0 %) | ⚠️ (10 à 90 %) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ∅ |

---

## MANQUES QUI BLOQUENT UNE PAGE DE LECTURE, PAR FONDS

### Judiciaire DILA (cass, capp, inca, TJ, tcom)
1. **`solution` et `nature` sont en base et jetés par `fetch_decision`** (`search_api.py` l. 1136 à 1149 contre `dila.get_decision` l. 688 et 692). `ssr.render_decision` l. 902 et 903 réserve déjà les lignes « Nature » et « Solution » : elles ne s'afficheront jamais. Correctif d'une ligne, gain immédiat sur 2,6 millions de décisions.
2. **`texte_integral` et `note_texte` calculés puis jetés** (`dila.py` l. 697, non repris l. 1136). Le site peut donc servir un sommaire comme s'il était l'arrêt, sans l'avertissement que le MCP donne.
3. **`president` et `avocats` en base, jamais servis.** Le nom de l'avocat est une information de fiche.
4. **ECLI absent hors Cour de cassation** (0 % sur 120 décisions de CA, TJ, tcom et Conseil constitutionnel). Impossible de proposer un identifiant européen citable.
5. **Parties, décision attaquée, juridiction de première instance : non ingérées** (`JURIS_NEW_COLS` absentes de `index_dila.EXTRA_COLS`). Pas de fil de procédure possible.

### Conseil d'État ArianeWeb
1. **Cinq métadonnées extraites par `parse_header` (l. 111 à 170) et jetées par `fetch_decision` (l. 1254)** : publication au Lebon, formation, président, rapporteur, rapporteur public. Le parseur existe, il tourne déjà, sa sortie est ignorée. C'est le correctif au meilleur rapport pour ce fonds.
2. Aucun sommaire ni abstrat : ArianeWeb ne les expose pas. Une fiche ne peut pas résumer.

### Justice administrative
1. **Fiche à deux vitesses selon l'identifiant.** Une décision CETATEXT sort avec rapporteur, rapporteur public, type de recours, publication, sommaire et abstrats (100 % sur 6). La même décision par la voie open data, c'est-à-dire toutes les décisions récentes, sort avec juridiction, date, numéro, formation et rien d'autre. La page de lecture sera riche sur 2015 et pauvre sur 2026.
2. **ECLI à 0 % sur les trois voies.**
3. **`formation` perdu en recherche sur la voie JADE** (`jade_remote._normalize_hit` l. 110 ne le sélectionne pas) alors qu'il est à 100 % sur le document.
4. **Aucun signalement d'homonymie de numéro** dans le chemin du site, alors que `_signaler_homonymes` (l. 73 à 107) existe et que 7 938 numéros du Conseil d'État sont partagés. Une fiche peut afficher la mauvaise décision sans le dire.
5. `type_decision` et `publication_code` de l'open data sont en base et jetés par `fetch_decision` l. 1175.

### CEDH
1. **Le fonds ne répond plus sur l'API publique.** Trois essais, trois `sources_en_echec: ["cedh"]`, 42 à 44 secondes. À traiter avant toute question d'affichage.
2. **`conclusion`, `importance`, `respondent`, `appno` sont en base, exposés par le MCP, et jetés par `_norm_cedh`** (l. 264 à 279). Sans le sens de l'arrêt, sans le pays et sans le numéro de requête, la fiche ne dit pas de quoi il s'agit.
3. `originating_body` au schéma, lu nulle part.

### CJUE
1. **`affaire_num` (`C-101/13`) en base, jamais rendu.** Le champ `numero` sert le CELEX, que personne ne cite dans un mémoire.
2. Pas de dispositif, pas de juridiction de renvoi, pas de lien entre un arrêt et les conclusions de l'avocat général qui lui correspondent, alors que les deux documents sont dans la même table.

### Conseil constitutionnel
1. `formation` à 0 %, `ecli` à 0 %, `sommaire` à 0 % : il ne reste que le numéro, la date, la nature qualifiée et le texte.
2. **Pas de solution** (conformité, non conformité, réserve d'interprétation), alors que c'est le seul renseignement qui compte sur une décision du Conseil.
3. `observations`, `url_cc`, `titre_jo`, `nor` déclarés au schéma DILA, non ingérés par `index_dila.py`.

### LEGI
1. **Le fil d'Ariane complet du plan du code existe** dans la colonne `hierarchie` et **seul le dernier niveau est servi** (`_titre_section` l. 616). Une page d'article ne peut pas montrer où l'article se situe.
2. **La table `legi_textes` n'est jointe nulle part** : impossible de dire par quelle loi ou quel décret la version affichée a été créée, ni de donner le NOR du texte parent.
3. Pas d'article précédent ni suivant, pas de liste de décisions citantes en REST (`search_decisions_citing` est MCP seulement).
4. À corriger par ailleurs : deux docstrings (`server.py` l. 1833 et la description de `get_law_article`) affirment encore que `titre_section` est indisponible ou faux. Mesuré à 100 % juste sur 30 articles. La documentation décourage d'utiliser un champ qui marche.

### JORF
1. **Aucune route de lecture.** `jorf_remote.get_text` (l. 50) n'est appelée par rien. Il n'y a pas de page possible pour un texte du Journal officiel.
2. **Le NOR est en base et n'est servi nulle part.** C'est l'identifiant par lequel on attaque un arrêté.
3. `date_signature`, `num_jorf`, `titre_long`, `nota` en base, non servis. `ministere` rempli à 43,3 % seulement.

### KALI
1. **Aucune route de lecture** (`kali_remote.get_text` l. 44 morte) : le texte de l'article de convention n'est pas affichable.
2. **Ni `etat`, ni `date_debut`, ni `date_fin` servis.** On ne peut pas dire si la convention est en vigueur, ce qui est la première question.
3. `idcc` manquant sur 16,7 % des lignes de l'échantillon : ces articles ne sont rattachables à aucune convention.

### Doctrine et avis
1. **Le sens de l'avis CADA n'est pas un champ** : il est en fin de `contenu`, après `--- Sens et motivation ---`. Une fiche ne peut pas afficher « Favorable » sans parser le texte.
2. **Le numéro d'affaire derrière une conclusion de rapporteur public est enfoui dans `tags`** (`AFF:427460`) et les titres sont parfois dégénérés (`N°`) ou contredisent la `source_url`. Pas de lien fiable conclusion vers arrêt.
3. Dates en deux formats selon le sous-fonds, tri et bornes non fiables de l'aveu du code (`warehouse_server.py` l. 793).
4. `partie` et `objet` non servis par le site.

### CNIL
1. **Le fonds n'est servi par aucune route REST**, et le bloc prévu pour lui dans `fetch_decision` (l. 1222 à 1239) est inatteignable à cause de la garde de la l. 1096. Or `ssr.render_sitemap_cnil` (l. 1483) publie des URL de décisions CNIL au sitemap : **ces URL ne peuvent pas se construire**. À vérifier en premier.
2. `formation` à 0 % sur 30.
3. Pas de nature (sanction, mise en demeure, avis), pas de montant, pas d'organisme visé.

### Travaux préparatoires
1. **Le fonds n'existe pas.** Ni base, ni table, ni parseur, ni téléchargement du bulk DOLE. Le hub l'annonce en quatre lignes marquées « à venir » (`web/hub.html` l. 389 à 393). Une page de lecture ne peut rien y rattacher : ni exposé des motifs, ni étude d'impact, ni avis du Conseil d'État sur un projet de loi, ni débats.

### Annuaire
1. **Aucune route REST** : l'annuaire n'est accessible qu'en MCP ou en fetch client de fichiers JSON statiques. Une page de lecture de décision ne peut pas afficher le greffe compétent sans recharger tout le fichier côté navigateur.
2. `date_source` à 0 % sur les lignes issues de l'API : impossible de dire de quand date l'adresse affichée.
3. `service` à 0 % sur ces mêmes lignes, et `adresse` agrège deux adresses dans une chaîne unique.

---

## Trois remarques transversales

1. **`/api/decision` ne renvoie jamais d'URL officielle.** Seul le rendu SSR la calcule (`ssr._cached_decision_url` l. 373). Toute page de lecture construite côté client devra refaire ce travail ou ajouter le champ à la réponse. Les deux seuls fonds qui servent `source_url` dans l'API sont LEGI et doctrine, à 100 % tous les deux.
2. **Le même normaliseur sert la carte de résultat et la page de document.** `fetch_decision` part systématiquement d'un `_norm_*` conçu pour une liste, puis ajoute quelques champs. Tout ce que le normaliseur de liste écarte est perdu pour la page de lecture, même quand la source l'a. C'est la cause commune de la majorité des manques ci-dessus : le code de lecture ne lit pas la donnée, il relit un résumé.
3. **Trois fonds sur quatorze n'ont aucune route de lecture** (JORF, KALI, CNIL) et un quatrième n'existe pas (travaux préparatoires), alors que le hub et les sitemaps les annoncent. Avant d'enrichir les fiches, il faut décider si ces fonds sont servis ou retirés de l'affichage.
