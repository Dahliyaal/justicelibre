# Correctifs du second audit, lot A (2 octobre 2026) : F1 doctrine, F2 ArianeWeb, R3 pagination Cour de cassation

Tout est fait EN LOCAL. Rien n'a été écrit en ssh, rien n'a été déployé, il n'y a eu ni commit ni push, et aucun processus n'a été tué. Les seuls accès à la prod sont des lectures, citées plus bas.

⚠️ **Un autre agent travaillait dans le même dépôt pendant ce lot** (lot B : `server.py` F4, `sources/dila.py` P2, `sources/jade_remote.py`, `token_server.py`, `tests/test_second_audit_B.py`). Ses changements ne sont pas les miens. Le `git diff --stat` global les mélange : la ventilation ci-dessous ne compte que les miens, mesurés contre les copies prises avant mes modifications (`/tmp/claude-1000/-home-dahl/748c09b7-716e-46e8-9843-1281859081b9/scratchpad/{search_api,ssr,server,scrape_ariane}.py`, `search.html`).

## 0. Manifeste de couverture

**Lu en entier** : `scratchpad/audit/audit_site_trafic_2oct.md` (197 lignes) et `scrape_ariane.py` (314 lignes avant correctif).

**Lu par extraits ciblés** :
- `search_api.py` : `_dedupe_ecli`, `_norm_doctrine`, `_Hits`, `_dispatch_dila_sync`, `search_federated` en entier, `fetch_decision` (branches legi, doctrine, dila) ;
- `ssr.py` : `render_decision` en entier (l. 810-1040), `_cached_decision_url` ;
- `ssr_v2.py` : bloc titre, référence et JSON-LD ;
- `server.py` : `search_doctrine`, `get_doctrine_document` ;
- `token_server.py` : `_handle_ssr_decision`, les routes des sitemaps, `/api/search` (l. 600-660) ;
- `sources/dila.py` : `search` (plafond 100, `COUNT` avec ou sans jointure) ;
- `scripts/scrape_increments_daily.sh` ;
- `web/search.html` : `fetchOneSource`, `_runSearchInner`, `retryTimedOutSources`, `updateHeader`, `canLoadMore`.

**Sondes en lecture sur la prod** (citées en § 1 et § 2) : `/api/decision` doctrine, `/api/search` doctrine (5 fonds), md5 des scripts, checkpoint, `MAX(ariane_num)`.

**NON vérifié** :
- Le comportement réel de la page `search.html` dans un navigateur. Seule la fonction `aEncoreUneSuite` a été exécutée sous node, et le reste a été relu. Après déploiement, à tester à la main (§ 5).
- **Les jumeaux NON adjacents dans le classement BM25.** Le dédoublonnage se fait par page. Si la ligne JURITEXT est en page 1 et sa jumelle Judilibre en page 2, l'arrêt réapparaîtra en page 2. Le front ne dédoublonne que par `id`. Mon test simule des jumeaux adjacents. La fréquence réelle n'a pas été mesurée.
- **Le `total` (33 596)** compte toujours les lignes en base, doublons compris. Un `COUNT(DISTINCT …)` exigerait la jointure, mesurée à 81 s (`sources/dila.py:386-387`, commentaire). Je ne le corrige donc pas : je le dis. Le champ `total_note` (`search_api.py:1207`) annonce que le nombre d'arrêts distincts est inférieur, et il donne le nombre de doublons retirés de la page. Faute d'une table dédoublonnée, aucun total distinct n'est calculé.
- **Les sitemaps** : aucun sitemap ne publie la doctrine. Les routes de `token_server.py:267-282` ne connaissent que `dila|jade|legi|cedh|cjue|ariane|cnil|opendata|static`, et `grep -n doctrine ssr.py` ne trouvait, avant correctif, aucun générateur de sitemap. `sitemap-ariane` publie des décisions ArianeWeb (de vraies décisions), il n'est donc pas concerné.
- **Constatation incidente, non corrigée (hors lot)** : sur `/api/search?sources=doctrine`, le filtre `juridiction=cada|ddd|bofip|ctn` est ignoré. Les quatre requêtes ont rendu les mêmes `ariane_crp:5545`, `ariane_crp:1005` (sortie en § 1). Il n'y a pas de `filtres_ignores`.
- **Alerte écrite par le cron** : le contrôle quotidien réécrit `couverture_alertes.txt` (« ne contient QUE l'état courant », `scripts/controle_couverture_daily.sh`, vu sur la prod). La ligne « ERREUR moisson morte » que j'y ajoute peut donc être effacée au contrôle suivant. Elle reste dans `scrape_increments.log`. L'alerte « ariane : dernier moissonnage » du contrôle, elle, existe déjà.
- La vitesse réelle de `dila.search(limit=60)` contre `limit=30` sur la prod n'a pas été mesurée.

## 1. F1 : doctrine présentée comme « Décision … n° 4294 »

**Constat sur la prod, avant correctif** :
```
curl -s "https://justicelibre.org/api/decision?source=doctrine&id=ariane_crp:4294"
-> 'title': 'Conclusions 412996 (2019-12-24)', 'juridiction': "Conseil d'État", 'numero': '4294',
   'tags': '4ème CHS,AFF:412996', 'source_url': '.../CRP/conclusion/2019-12-24/412996'
curl -s "https://justicelibre.org/api/search?q=412996&sources=doctrine&limit=3"
-> ariane_crp:4294 numero '4294' (pas de champ tags dans les résultats de recherche)
```

Par fonds (`/api/search?q=…&sources=doctrine`, résultats lus) :
- `cada:20143607` : numero 20143607, et l'URL officielle est `cada.fr/avis/20143607`. C'est le vrai n° d'avis.
- `bofip:BOI-TVA-LIQ-10-20250514` : c'est le vrai identifiant BOI.
- `ddd:1037` : l'URL est `…notice_display&id=1037`. C'est le n° de notice du catalogue, pas une référence citable.
- `ariane_crp:1005` : le titre « Cette affaire a été affectée… » ne porte pas le numéro. L'URL se termine par `/386716`.

**Correctif** :
- `search_api.py:594` `doctrine_nature()` et `search_api.py:603` `doctrine_numero()`. Pour `ariane_crp`, le numéro d'affaire est pris dans `AFF:` (tags), sinon dans le titre « Conclusions N », sinon à la fin de l'URL officielle, et sinon il reste vide. Pour `cada` et `bofip`, c'est `doc_id` (référence officielle). Pour `ddd` et `ctn`, le champ reste vide. `search_api.py:653` remplit `numero` et le nouveau champ `nature_document`.
- `ssr.py:874-892` : pour la doctrine, le H1, le `<title>` et la ligne sous le titre disent la nature réelle, par exemple « Conclusions du rapporteur public dans l'affaire n° 412996, Conseil d'État, décision lue le 24 décembre 2019. Ce n'est pas une décision de justice… ». Il n'y a plus jamais « Décision rendue par » (`ssr.py:1021`). Le tableau porte une ligne « Nature » et une ligne « N° d'affaire ».
- JSON-LD : `@type` vaut `CreativeWork`, sans `LegalCase` (`ssr.py:929`), et `identifier` ne retombe plus sur `ariane_crp:4294`.
- `ssr_v2.py` (non déployé, aiguillage `JL_SSR_V2`) : le surtitre et les références copiables sont préfixés par la nature, et `@type` vaut `CreativeWork`.
- MCP : `server.py:2025` `_doctrine_identite()` ajoute `nature`, `numero` et, pour `ariane_crp`, un `avertissement` (« doc_id est interne, à ne jamais citer »). Elle est appliquée dans `search_doctrine` (`server.py:2021`) et `get_doctrine_document` (`server.py:2056`).
- Canaux : le SSR, `/api/decision`, `/api/search`, les deux outils MCP et le JSON-LD sont corrigés. Il n'y a pas de sitemap doctrine (voir manifeste).

**Test** : `tests/test_doctrine_identite.py` (5 cas, hors ligne, enregistrement brut de la prod rejoué).

## 2. F2 : le point de reprise ArianeWeb avance de 5 000 par jour

**Constat en lecture sur la prod** (commande, puis sortie) :
```
ssh root@46.225.190.237 'md5sum /opt/justicelibre/scrape_ariane.py /opt/justicelibre/scripts/scrape_increments_daily.sh;
  cat /opt/justicelibre/scrape_ariane.checkpoint; sqlite3 -readonly …/judiciaire.db
  "select max(ariane_num) …; select ariane_num, fetched_at … order by ariane_num desc limit 1;"'
fb6f726107bf03af4288d46f0ad8c233  /opt/justicelibre/scrape_ariane.py        (= copie locale d'avant correctif)
23898227e23441a4457315fec434eb2a  /opt/justicelibre/scripts/scrape_increments_daily.sh (= git HEAD)
435774
325793
325793|2026-09-10 07:41:54
```
Le maximum réel en base est donc **325793** (reconfirmé). Le checkpoint a encore avancé depuis l'audit : 430775 avant, **435774** maintenant.

**Correctif** (`scrape_ariane.py`) :
- Le checkpoint n'enregistre plus que `dernier_vivant` : le dernier identifiant récupéré ou déjà en base (`scrape_ariane.py:301`, `:352`, fermeture `ckpt()` l. 270). Cela vaut pour tous les cas : saut de zone déjà moissonnée, insertion, fin du corpus, coupe-circuit et fin de session.
- `load_checkpoint` : un fichier AU-DELÀ du sommet en base est ignoré, et la reprise se fait au sommet réel (`scrape_ariane.py:161-170`). Au premier passage après déploiement, la tâche repartira donc d'elle-même de 325793, sans toucher au fichier.
- Un balayage borné (`ARIANE_DEPUIS`) n'écrit plus le checkpoint. C'est ce que promettait déjà le commentaire, que le code ne respectait pas.
- Le journal le dit franchement : « [ariane] 0 nouvelle décision cette session (dernière décision du sommet moissonnée il y a X j) » (`bilan`, l. 205).
- Code de sortie **3** si la session rapporte 0 et que la décision du sommet date de plus de `ARIANE_ALERTE_JOURS` jours (3 par défaut) : `jours_depuis_sommet`, l. 189. L'âge est lu par `ORDER BY ariane_num DESC LIMIT 1` (index), jamais par `MAX(fetched_at)`, qui prenait ~8 min selon l'audit. Point d'entrée : `sys.exit(main())`, l. 374.
- `scripts/scrape_increments_daily.sh:41-50` : le cron distingue maintenant OK (0), « ERREUR : moisson morte » (3, ligne aussi ajoutée à `couverture_alertes.txt`), timeout (124) et autre code. Avant, il écrivait « ArianeWeb OK » pour +0. `bash -n` passe.

**Rattrapage, à ne lancer qu'APRÈS déploiement du nouveau `scrape_ariane.py`** (NON exécuté) :
```
ssh root@46.225.190.237 'cd /opt/justicelibre && sudo -u justicelibre env ARIANE_DEPUIS=325794 ARIANE_JUSQUA=332000 \
  timeout 4h python3 -u scrape_ariane.py >> /var/log/justicelibre/ariane_rattrapage_2oct.log 2>&1'
```
- La borne 332000 laisse de la marge au-dessus de 326093, le plus haut identifiant vivant vu par l'audit. Je ne l'ai pas re-sondé.
- Au rythme de 0,3 s par requête, ~6 200 identifiants prennent ~31 min.
- En mode borné, le checkpoint n'est pas touché. Ensuite, la tâche quotidienne repart du nouveau `MAX(ariane_num)`.
- Ce rattrapage manuel n'est pas indispensable : le cron suivant repartira seul de 325793. Il est quand même plus sûr, parce que 300 décisions puis 5 000 « 404 » à 0,3 s font ~27 min, au ras du `timeout 1800` du cron.
- ⛔ Avec l'ANCIEN code, ne pas le lancer : il écrirait 332000 dans le checkpoint.

**Test** : `tests/test_ariane_checkpoint.py` (5 cas, base SQLite temporaire, `fetch_one` simulé, ids à 200 000 + comme sur la prod).

## 3. R3 : Cour de cassation, 19 résultats sur 33 596 sans « Charger la suite »

**Cause confirmée à la lecture.** Dans `search_federated`, `dila_r = _dedupe_ecli(dila_r)` s'appliquait après `dila.search(limit=30, offset=…)`, et `search.html` ne montrait le bouton que si `lastChunkSize >= PAGE_SIZE`.

**Correctif serveur** (`search_api.py`) :
- `_dispatch_dila_sync` dédoublonne lui-même. Il lit une seule requête sur-dimensionnée (`_DILA_SURLECTURE = 2`, l. 789, plafonnée à 100 comme `dila.search`) et prend les `limit` premiers arrêts distincts.
- Il rend `next_offset`, l'offset de base réellement consommé, et `has_more`.
- Une seule requête par page, et non une boucle : chaque `dila.search` refait un `COUNT` avec jointure dès qu'un filtre de juridiction est posé.
- Clés d'identité partagées : `_cles_doublon`, l. 152, mêmes règles que `_dedupe_ecli`.
- `search_federated` expose `next_offset` et `has_more` quand dila est la seule source (l. 1204), ainsi que `total_note` (l. 1207).

**Correctif front** (`web/search.html`) :
- `aEncoreUneSuite()` (l. 2193) affiche le bouton si une source dit `has_more`. Il ne se fie plus à la taille du lot que pour les sources qui ne le disent pas.
- `offsetPour(src)` (l. 2206) envoie `next_offset` à la page suivante.
- Une source qui a répondu `has_more: false` n'est pas relancée.
- La re-tentative rejoue l'offset réellement demandé (`srcUsed`).
- L'en-tête « N+ résultats » utilise la même règle.

**Test** : `tests/test_pagination_dila_dedup.py`. Le corpus simulé compte 300 lignes pour 200 arrêts. Le test vérifie qu'une page rend 30 résultats avec `has_more`, que le parcours complet ne perd aucun arrêt et n'en rend aucun deux fois, et que `total_note` est présent. `aEncoreUneSuite` est exécutée sous node sur 3 cas.

## 4. Preuve : les nouveaux tests échouent sur l'ancien code et passent sur le nouveau

Méthode : une copie de l'arbre est faite dans le scratchpad, les fichiers d'avant correctif y sont remis, puis chaque test y est rejoué.

| Test | Ancien code | Nouveau code |
|---|---|---|
| test_doctrine_identite | 5 FAIL (`AssertionError: 4294` ; `1005` ; « la doctrine est encore présentée comme une décision » ; `module 'server' has no attribute '_doctrine_identite'`), rc 1 | 5 ok, rc 0 |
| test_ariane_checkpoint | 5 FAIL (`checkpoint=200105 (doit rester au dernier vivant 100)` ; reprise depuis le fichier ; `décisions 101/103 non récupérées : [200098, 200099, 200100]` ; pas de « 0 nouvelle décision »), rc 1 | 5 ok, rc 0 |
| test_pagination_dila_dedup | 4 FAIL (`20 rendus sur 30 demandés` ; `20 arrêts atteints sur 200` ; `total_note` None ; `pas de fonction aEncoreUneSuite`), rc 1 | 4 ok, rc 0 |

Les trois tests sont ajoutés à `tests/run_all.sh`, avant `test_no_dead_code.py`. L'autre agent y a aussi ajouté `test_second_audit_B.py`.

## 5. `bash tests/run_all.sh --offline` avant et après

- Avant (`…/scratchpad/tests_avant.txt`) : rc 0, « ✓ Tous les tests passent. », 136 lignes ✓/ok.
- Après (`…/scratchpad/tests_apres.txt`) : rc 0, « ✓ Tous les tests passent. », 163 lignes ✓/ok. Les 3 nouveaux tests et `test_second_audit_B.py` (de l'autre agent) passent.
- Les deux tests sur les lois sont inchangés : `test_parse_dila_champs.py` « All 20 tests passed », avant comme après, et `test_lois_codes_dates.py` « All 15 tests passed », avant comme après.
- Hors `run_all` : `tests/test_ssr_v2.py` donne « All 15 tests passed » après correctif.

## 6. Diff (mes changements seuls)

```
search_api.py                       +129  -7
ssr.py                               +28  -4
ssr_v2.py                             +7  -3
server.py                            +21  -1   (le reste du diff de server.py est le lot B)
scrape_ariane.py                     +69  -9
scripts/scrape_increments_daily.sh   +14  -3
web/search.html                      +41  -4
tests/run_all.sh                      +3        (+1 ligne du lot B)
tests/test_doctrine_identite.py      107 (nouveau)
tests/test_ariane_checkpoint.py      109 (nouveau)
tests/test_pagination_dila_dedup.py  118 (nouveau)
```

## 7. Sondes à jouer après déploiement

1. `curl -s 'https://justicelibre.org/decision/doctrine/ariane_crp:4294' | grep -c 'Décision rendue'` : attendu 0. `grep -o '<title>[^<]*'` doit contenir « Conclusions du rapporteur public — affaire n° 412996 » et pas 4294. Purger Cloudflare pour `/decision/doctrine/*` (cache de 24 h).
2. `curl -s 'https://justicelibre.org/api/decision?source=doctrine&id=ariane_crp:4294' | jq '.numero,.nature_document'` : attendu `"412996"`, `"Conclusions du rapporteur public"`.
3. `curl -s 'https://justicelibre.org/api/search?q=412996&sources=doctrine' | jq '.results[0].numero'` : attendu `"412996"`. Et `ddd:1037` doit rendre `numero ""`.
4. MCP `get_doctrine_document("ariane_crp:4294")` doit contenir `numero: "412996"`, `nature` et `avertissement`. `search_doctrine("412996")` doit contenir les mêmes champs.
5. `curl -s 'https://justicelibre.org/api/search?q=licenciement+faute+grave&limit=30&offset=0&sources=dila&timeout=12&juridiction=cass' | jq '.total_rendus,.has_more,.next_offset,.total_note'` : attendu 30, true, un nombre > 30 et la note. Rejouer avec `offset=<next_offset>` : il ne doit y avoir aucun ECLI déjà vu en page 1 (pour évaluer les jumeaux non adjacents, voir manifeste). Mesurer la durée par rapport à avant (limit 60 côté SQL).
6. Navigateur, `search.html`, filtre « Cour de cassation », « licenciement faute grave » : 30 cartes, « 30+ résultats », bouton « Charger la suite », puis 60 cartes.
7. ArianeWeb : `sudo -u justicelibre python3 -c "import sqlite3,sys; sys.path.insert(0,'/opt/justicelibre'); import scrape_ariane as s; print(s.load_checkpoint(sqlite3.connect('file:'+s.DB_PATH+'?mode=ro', uri=True)))"` doit afficher 325793 et le message « AU-DELÀ du sommet ». Après le rattrapage (§ 2) : `sqlite3 -readonly …/judiciaire.db "select max(ariane_num) from ariane_decisions"` doit être > 325793 (≈ 326093). Ensuite, `/api/search?q=436125&sources=ariane` ne doit plus rendre total 0. Le lendemain, `grep -E 'ArianeWeb (OK|ERREUR)|0 nouvelle décision' /var/log/justicelibre/scrape_increments.log | tail`.
8. Le déploiement doit aussi copier `scripts/scrape_increments_daily.sh`. Le fichier de la prod est identique à `git HEAD` (md5 23898227…), il n'y a donc pas de divergence à fusionner.
