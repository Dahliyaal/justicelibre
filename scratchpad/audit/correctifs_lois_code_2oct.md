# Correctifs lois (F3, F4, F7, F10, paraphrases), 2 octobre 2026

Source : `scratchpad/audit/audit_lois_2oct.md`, lu en entier. Rien n'est commité, poussé ni déployé ; aucune machine distante touchée ; aucune requête à la prod (le comportement actuel est celui que l'audit a reproduit). `warehouse/warehouse_server.py` et `parse_dila_bulk.py` n'ont pas été modifiés par moi (le diff qu'ils montrent vient de l'autre session ; je n'ai fait que LIRE `CODE_TO_LEGITEXT`).

Tests : nouveau fichier `tests/test_lois_codes_dates.py` (15 tests, hors ligne, entrepôt remplacé par des doublures), ajouté à `tests/run_all.sh` (l. 34). `bash tests/run_all.sh --offline` : vert avant mes changements, vert après (« ✓ Tous les tests passent. »). `ast.parse` OK sur les 6 fichiers touchés et sur le test.

## F3 : pages /loi/ en 404 (espace, astérisque, sigles accentués)

- `token_server.py:112-173` (nouveau) : `_LOI_PATH_RE` et `_parse_loi_path()`. Le chemin est décodé (`urllib.parse.unquote(..., errors="strict")`, UTF-8 invalide refusé) AVANT la regex. Code : `[\w.\-]{1,20}` (`\w` Unicode, donc ê, é acceptés). Numéro : `[\w*][\w.\- *]{0,39}` (espace et `*` acceptés, pas en tête). Refusés : `/` (y compris `%2F`), `..`, `<`, `>`, guillemets, `%` résiduel (double encodage), NUL et sauts de ligne, longueurs excessives. Espaces finales retirées.
- `token_server.py:288-291` : la route `/loi/` utilise `_parse_loi_path`. Les URL déjà publiées sans encodage (`/loi/CC/1128`, `/loi/LPF/L80B`, `/loi/LEGITEXT…/…`, `/loi/78-17/1`) passent à l'identique.
- `ssr.py:1068-1076` (nouveau) : `_loi_path(code, num)`, chaque segment passé à `quote(..., safe="")` (les `/` structurels sont gardés, un `/` dans un segment serait encodé).
- `ssr.py:1576-1582` : le sitemap legi publie `/loi/LPF/L80%20B`, `/loi/CFor%C3%AAt/…`, `/loi/CSP/R%2A1435-28-2`.
- `ssr.py:1116-1118` : la canonique (`<link rel=canonical>`, `og:url`, JSON-LD `url`) est encodée de même.
- `render_law` : vérifié, `num`, `code_label`, `texte`, `nota`, `etat`, URL passent tous par `esc()` (`html.escape`, quote=True). `render_law_404` aussi.
- Tests : `test_loi_path_decode_espace_asterisque_accents`, `test_loi_path_anciennes_url_inchangees`, `test_loi_path_refuse_les_chemins_dangereux` (19 chemins), `test_render_law_echappe_et_encode_la_canonique`, `test_sitemap_legi_encode_les_url_loi` (chaque `<loc>` produit est relu par la route).

## F4 : date hors calendrier acceptée par /api/law et /api/law/batch

- `token_server.py:147-166` (nouveau) : `_date_calendaire_ok()` (gabarit puis `date.fromisoformat`), message `_ERREUR_DATE`.
- `token_server.py:365-366` (`_handle_law`) et `:725-726` (`_handle_law_batch`) : 400 « Date invalide : '2016-13-45' n'est pas une date du calendrier au format AAAA-MM-JJ ».
- Tests : `test_api_law_date_hors_calendrier_400` (2016-13-45, 2016-02-30, 2025-00-10, 15/06/1992), `test_api_law_batch_date_hors_calendrier_400`, `test_api_law_date_valide_passe` (2016-02-29 transmis à l'entrepôt).

## F7 : incohérences de canal sur les codes

- `sources/legi.py:196-237` : `HISTORICAL_CODES`, les 29 sigles historiques de `CODE_TO_LEGITEXT` (CTM, CP1810, CPC1807, CTACAA, CNat, CForêt-ancien…), ajoutés à `SUPPORTED_CODES` et `SUPPORTED_CODES_LEGITEXT` (108 sigles, identiques à l'entrepôt). Effet de bord voulu : la ressource `justicelibre://codes-supportes`, `search_decisions_citing` et le sitemap (qui publiera le sigle au lieu du LEGITEXT pour ces codes ; les anciennes URL LEGITEXT restent valides) les connaissent aussi.
- `sources/legi.py:242-256` : `is_direct_id()`, `is_known_code()`.
- `sources/legi.py:301-317` : `get_versions` accepte LEGITEXT/JORFTEXT (`code_long` = null pour un identifiant direct).
- `token_server.py:367-371` : `/api/law?code=ZZZ` ou `code=cc` → 400 « Code inconnu : 'ZZZ'… sensibles à la casse » au lieu de 404 « Article introuvable ». `token_server.py:387-391` : `/api/law/versions?code=ZZZ` → 400 au lieu de 200 `{"versions": []}`. Contrôle fait avant tout appel à l'entrepôt (plus de balayage pour un sigle bidon).
- Tests : `test_api_law_code_inconnu_400`, `test_api_law_versions_code_inconnu_400`, `test_api_law_versions_code_connu_passe`, `test_mcp_get_law_versions_accepte_identifiant_direct` (JORFTEXT000000886460, CP1810, ZZZ), `test_mcp_get_law_article_sigle_historique`, `test_sigles_identiques_a_l_entrepot` (lit `CODE_TO_LEGITEXT` par `ast` et exige l'égalité : toute dérive future casse le test).
- Non fait : `/api/law/batch` garde `found:false` pour un code inconnu dans la liste (comportement par article, non signalé comme défaut).

## F10 : note « à la date demandée » sans date demandée

- `sources/warehouse.py:138-167` (nouveau) : `_corriger_note_sans_date()` réécrit EXACTEMENT la phrase de l'entrepôt en « Aucune version de cet article n'est en vigueur aujourd'hui ; version la plus récente retournée. », seulement si aucune date n'a été demandée. Appliqué dans `get_law` (l. 200), les deux `sync_get_law` (l. 258-259 et 408-410 ; le second écrase le premier au chargement du module, les deux corrigés), `get_laws_batch` (l. 270) et `sync_get_laws_batch` (l. 421).
- Test : `test_note_sans_date_reecrite` (réécrite sans date, intacte avec date, autres notes intactes, batch).
- À savoir : l'autre session corrige la même note À LA SOURCE dans `warehouse_server.py` (diff non commité, l. 530-534). Une fois cela déployé, ma réécriture ne trouvera plus la phrase et deviendra sans effet ; elle est inoffensive et peut être retirée ensuite.

## Paraphrases (server.py, docstrings seulement)

- `server.py:77-78` (instructions MCP) : « version en vigueur À LA DATE donnée » complété par « selon la base (qui peut retarder sur Légifrance : voir sa description) ».
- `server.py:102`, `:1288`, `:2049-2052` : « ~80 sigles » → « ~110 », mention des 29 codes historiques.
- `server.py:472` (`about_justicelibre`, volume) et `:1832`, `:2032` : « 3,6 Go » retiré (« base LEGI ~9 Go (2 oct. 2026) » dans `about`, sans chiffre ailleurs).
- `server.py:1294-1296` : exemple `resolve_law_number("68-1250")` → LEGITEXT000006068317 (valeur que rend le service selon l'audit), intitulé de la loi corrigé.
- `server.py:1839-1843` (`search_legi`) et `:2091-2093` (`get_law_article`) : « mesuré juste sur 30 articles… » remplacé par : peut être périmé, 7 sur 60 faux au contrôle du 2 oct. 2026, à vérifier avant de citer.
- `server.py:2066-2084` : `note` décrite pour ce qu'elle fait (absence de note ≠ garantie) ; liste des 9 valeurs d'`etat` avec leur sens en une ligne, et avertissement que l'état en base peut retarder sur Légifrance.
- `server.py:2129-2133` : `get_law_versions` documente l'identifiant direct et `code_long` null.
- `sources/legi.py:6-9` : « Les 22 codes supportés » → 108 sigles, miroir testé de l'entrepôt.
- Non fait : le commentaire de section « 22 codes consolidés » à l'intérieur du dict (`sources/legi.py:20`) est interne et resté tel quel.

## Ce que je n'ai pas fait

- Aucune vérification en direct après correctif : rien n'est déployé (consigne). Les sondes à jouer après déploiement : `/loi/LPF/L80%20B`, `/loi/CFor%C3%AAt/L111-1`, `/loi/CSP/R*1435-28-2` en 200 ; `/api/law?code=CC&num=1128&date=2016-13-45` en 400 ; `/api/law/versions?code=ZZZ&num=1` en 400 ; MCP `get_law_versions(code="JORFTEXT000000886460", num="1")` et `get_law_article(code="CP1810", num="1")` servis.
- Rappel de l'audit : `token_server.py` de la prod diffère déjà du dépôt (aiguillage `JL_SSR_V2`) ; le déploiement de ce fichier embarquera aussi cet aiguillage.

## git diff --stat (dépôt entier, au moment du rapport)

```
 parse_dila_bulk.py              | 48 ++++++++++++++++++++--   (autre session)
 server.py                       | 65 ++++++++++++++++++++++---------
 sources/legi.py                 | 83 ++++++++++++++++++++++++++++++++++----
 sources/warehouse.py            | 44 +++++++++++++++++----
 ssr.py                          | 21 +++++++++-
 tests/run_all.sh                |  1 +
 tests/test_parse_dila_champs.py | 56 ++++++++++++++++++++++++++   (autre session)
 token_server.py                 | 88 +++++++++++++++++++++++++++++++++++++----
 warehouse/warehouse_server.py   | 81 +++++++++++++++++++++++++++++++++++--   (autre session)
 + tests/test_lois_codes_dates.py (nouveau, non suivi)
```
