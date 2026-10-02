# Audit justicelibre.org : fonctionnement hors articles de loi, et trafic (2 octobre 2026)

Auditeur : agent Opus, lecture seule. Aucune écriture, aucun redémarrage, aucun kill, aucune modification de config sur aucune machine.

## 0. MANIFESTE DE COUVERTURE

**Journaux lus (copiés en local, scratchpad de session, puis analysés)**
- nginx prod `access.log` + `access.log.1` + `access.log.2.gz` à `.20.gz` : du 12/09/2026 00:00 au 02/10/2026 19:08 UTC, 1 745 092 lignes.
- nginx prod `error.log` + `.1` + `.2.gz` à `.10.gz` : du 22/09/2026 10:59 au 02/10/2026 17:10, 23 502 lignes.
- `journalctl -u justicelibre` (MCP) : extraits du 02/10 (le journal ne contient PAS le nom des outils appelés, seulement `POST /mcp 200`).
- `https://justicelibre.org/stats.json` (compteur par outil, par jour, par heure, fuseau codé en dur UTC+2).
- `/var/log/justicelibre/couverture_alertes.txt`, `couverture.log`, `scrape_increments.log` (62 Mo, lu par extraits ciblés du 08/09 au 02/10), crontab root prod.
- Entrepôt : `journalctl -u justicelibre-warehouse` 48 h, `/v1/health` (1 seule requête), `df`, `du`, `/proc/<pid>/limits`.

**Outils MCP appelés** (handshake manuel `initialize` -> en-tête `Mcp-Session-Id` -> `notifications/initialized` -> `tools/list` = 33 outils) : 26 outils appelés, 86 appels au total, séquentiels, sauvegardés dans le scratchpad (`mcp/p1.json`, `p2.json`, `p3.json`) :
about_justicelibre, list_juridictions, search_conseil_etat, search_admin, search_admin_recent, search_admin_recent_all_ta, search_admin_recent_all_caa, search_judiciaire_libre, search_judiciaire, get_decision_judiciaire, get_decision_judiciaire_libre, get_decision_text, get_cc_decision, get_ce_decision, get_admin_decision, search_cc, search_cedh, get_decision_cedh, search_cjue, get_decision_cjue, search_cnil, search_doctrine, get_doctrine_document, search_all, search_decisions_citing, search_annuaire.

**NON appelés, volontairement** (périmètre de l'autre agent, articles de loi) : get_law_article, get_law_versions, resolve_law_number, build_source_url, search_legi, search_jorf, search_kali. `/api/search?sources=legi` a seulement été vérifié comme répondant (pas sur l'exactitude).

**Site testé** : `/api/search` sur les 7 sources (requête courante, référence, offset 30) + 5 pièges ; `/api/decision` doctrine ; 13 pages `/decision/` (dila hex et JURITEXT, admin opendata et CETATEXT, ariane, cedh, cjue, cnil, doctrine, 4 identifiants inexistants) ; index des sitemaps + 15 sous-sitemaps (dila 1 et 53, jade 1 et 12, opendata 1 et 23, ariane 1 et 4, cedh 1 et 2, cjue, cnil, legi 1, static, dila-54 hors plage), 3 URL tirées au hasard dans chacun (39 URL) ; pages statiques `/`, index.html, search.html, annuaire.html, ressources.html, stats.html, robots.txt ; `cf-cache-status` sur 6 URL ; accès direct à l'origine sans Cloudflare.

**Ce qui n'a PAS pu être fait, et pourquoi**
- Ventiler le trafic MCP **par outil et par client** : impossible, le journal du service ne nomme pas l'outil et nginx ne voit pas le corps des POST. J'ai corrélé heure par heure les sessions de chaque user-agent (nginx) avec `stats.json.hours_tools` : c'est une inférence, signalée comme telle.
- Identifier l'**opérateur de BRANCO** : pas d'IP dans access.log (choix RGPD), et toutes ses requêtes passent par Cloudflare (IP de bord). Aucune trace dans le dépôt ni sur les deux serveurs.
- Prouver l'**injustice d'un 429 précis** envers un utilisateur précis : access.log n'a pas d'IP, je ne peux pas joindre un 429 à son compteur. J'ai pu le faire globalement via `error.log`, qui, lui, contient les IP (voir D7).
- Pendant l'audit, **quelqu'un d'autre a redéployé la prod** : le 02/10 à 19:51:37-39 UTC, `ssr.py`, `sources/legi.py`, `sources/warehouse.py`, `server.py` ont changé, puis `justicelibre-token` a été redémarré (ssh root depuis 85.253.178.63, sans doute l'autre agent). Mes sitemaps ariane/cedh/cjue/cnil/legi ont pris un 502 à ce moment ; je les ai retestés après, tous 200. Les mesures antérieures à 19:51 portent donc sur le code précédent.
- **Incident de mon fait** : une requête sqlite `-readonly` sur `judiciaire.db` (MAX et GROUP BY sur `ariane_decisions.fetched_at`, sans index) a tourné ~8 min vers 19:25 et a contribué à ~50 % d'iowait sur la prod. Je ne l'ai pas tuée (consigne « aucun kill »). Elle a pu ralentir le premier `search_cc` (891 s), mais le second (794 s), lancé après sa fin, prouve que la lenteur est propre à l'outil (D2).

## 1. DÉFAUTS, PAR GRAVITÉ

Ordre : faux servi > panne > utilisateurs refusés > lenteur > cosmétique.

### FAUX SERVI

**F1. Pages et API doctrine : des conclusions du rapporteur public présentées comme une « décision du Conseil d'État n° 4294 »**
- Reproduction : `GET https://justicelibre.org/decision/doctrine/ariane_crp:4294` -> 200, `<title>Conseil d'État, 4294 24 décembre 2019 -JusticeLibre</title>`, corps : « Décision rendue par Conseil d'État, le 24 décembre 2019. Juridiction Conseil d'État ... Numéro 4294 », puis le texte « CONCLUSIONS M. Raphaël Chambon, rapporteur public ... N° 412996 ». JSON-LD `"name": "n° 4294 · 24 décembre 2019"`.
- Même chose dans l'API : `GET /api/decision?source=doctrine&id=ariane_crp:4294` -> `"numero": "4294"`, alors que `title` dit « Conclusions 412996 » et `tags` dit `AFF:412996`.
- Danger : quelqu'un qui cite « CE, 24 déc. 2019, n° 4294 » cite une décision qui n'existe pas ; le vrai dossier est le 412996, et ce ne sont pas des motifs du juge.
- Cause : `search_api.py:597` (`_norm_doctrine`) : `"numero": raw.get("doc_id")` met l'identifiant interne dans `numero` ; `ssr.py:997` rend toute source avec « Décision rendue par {juridiction} ».
- Correctif suggéré : pour `ariane_crp`, `numero` = numéro d'affaire tiré de `tags` (`AFF:`) ou du titre ; pour les autres fonds doctrine, `numero` vide. Dans `ssr.py`, une ligne dédiée à la doctrine (« Conclusions du rapporteur public dans l'affaire n° 412996 », « Avis CADA », « BOFiP »), jamais « Décision rendue par ».

**F2. ArianeWeb : moisson morte depuis le 10/09, et le point de reprise s'éloigne de 5 000 identifiants par jour** (alerte « ariane : dernier moissonnage = 2026-09-10 »)
- Preuves : en base, `select max(ariane_num), max(fetched_at) from ariane_decisions` -> `325793 | 2026-09-10 15:32:42`. Journal de la tâche : « resume from id= » vaut 325793 (11/09), 330793, 335792 ... 425776 (01/10), 430775 (02/10) ; chaque jour « 5000 x 404 puis 6 sondes vides ... fin du corpus », « +0 cette session », et le cron écrit « ArianeWeb OK ».
- Le corpus, lui, continue : recherche ArianeWeb en direct `xsearch?type=json&SourceStr4=AW_DCE&text.add="septembre 2026"` renvoie les identifiants 326056 à 326088 ; « octobre 2026 » renvoie jusqu'à 326093 ; le téléchargement `plugin?...Id=/Ariane_Web/AW_DCE/|326056` -> 200, 19 961 octets. L'id 325793 est l'ordonnance CE n° 519395 du 9 septembre 2026. Toutes les décisions du CE publiées sur ArianeWeb depuis le 9/09 manquent, et le site répond « 0 » sans le dire (p. ex. `/api/search?q=436125&sources=ariane` -> total 0, sources_no_result vide).
- Cause : `scrape_ariane.py` l. 269-275 : à la « fin du corpus », `save_checkpoint(num)` enregistre l'identifiant ATTEINT (dernier vivant + 5 000), pas le dernier vivant ; l. 306 idem ; et `load_checkpoint` (l. 135-162) prend le PLUS GRAND du fichier et de la base, donc le fichier gagne. Le 11/09 la base était à jour, les ids 325794-330793 n'existaient pas encore : la tâche a sauté par-dessus, puis a recommencé chaque jour 5 000 plus loin. Effet secondaire : environ 30 min par jour de requêtes 404 vers conseil-etat.fr pour rien.
- Correctif suggéré : à la fin du corpus, enregistrer `MAX(ariane_num)` en base (ou le dernier id vivant), jamais `num` ; au chargement, si le fichier dépasse la base de plus de `MAX_CONSECUTIVE_404`, repartir de la base. Puis un balayage borné `ARIANE_DEPUIS=325793 ARIANE_JUSQUA=340000`. Que le cron écrive « ERREUR » quand une session finit à +0 plusieurs jours de suite.

**F3. `get_admin_decision` sans juridiction : « introuvable » pour une décision de CAA qui existe**
- Reproduction : `get_admin_decision(numero="26VE02318")` -> `{"error": "Décision n° 26VE02318 introuvable dans JADE (bulk DILA)...", "error_category": "not_found"}` en 0,46 s. Or `get_decision_text("DCA_26VE02318_20260930")` rend le texte (CAA Versailles, 30/09/2026). Idem `25DA02275` sans juridiction -> introuvable ; avec `juridiction="CAA59"` -> trouvé (`ORCA_25DA02275_20260930`).
- Paraphrase confrontée : la docstring dit « Sans `juridiction`, le repli sur l'API live n'interroge que le Conseil d'État et les CAA : un numéro de TA peut alors ressortir introuvable ». Elle promet donc que les CAA sont couvertes. Ce n'est pas le cas.
- Cause : `sources/jade_remote.py` vers l. 227-264 : repli sur `juriadmin.search(..., juridiction="CE-CAA")` ; or `list_juridictions` décrit `CE-CAA` comme « Conseil d'État + cours administratives d'appel (jurisprudence citée) », pas le fonds des CAA. Et `except Exception: return None` (l. 263-264) transforme toute panne du live en « introuvable ».
- Correctif suggéré : sans juridiction, déduire la cour du suffixe du numéro (`VE`->CAA78, `DA`->CAA59, etc.) et interroger cette CAA ; à défaut fan-out sur les 9 CAA ; remplacer `except: return None` par une erreur `retryable` qui dit que le live n'a pas répondu.

**F4. `search_all` et `search_annuaire` : un filtre inconnu rend « 0 résultat » au lieu d'un refus** (défaut connu depuis le 5/09, rapport H, toujours là)
- `search_all(query="harcèlement", sources=["nimportequoi"])` -> `{"per_source_counts": {"nimportequoi": 0}, "total_returned": 0, "results": []}`, sans erreur. Avec `["jade","nimportequoi"]` -> jade répond, la source fautive est comptée « 0 », pas signalée.
- `search_annuaire(query="greffe", category="categorie_bidon")` -> `{"total": 0, "returned": 0, "results": []}`.
- `search_admin(query="permis de construire", sort="pertinence_bizarre")` -> accepté sans note (docstring : « "relevance" (défaut, BM25) ou "date_desc" / "date_asc" »).
- Comparaison : `search_judiciaire_libre`, `search_cc`, `search_doctrine` et les dates de tous les outils refusent proprement (`error_category: "validation"`). Ces trois-là sont les derniers à avaler.
- Correctif : liste blanche + `_tool_error(category="validation")` comme ailleurs.

**F5. Sitemap CJUE : 1 370 URL publiées renvoient 404**
- `sitemap-cjue-1.xml` contient 1 370 `<loc>` avec parenthèses brutes ; tirage : `https://justicelibre.org/decision/cjue/61959CC0033(01)` -> 404. La même URL encodée `%2801%29` -> 200, et `/api/decision?source=cjue&id=61959CC0033(01)` répond.
- Cause : `token_server.py:200`, regex `^/decision/([a-z]+)/([A-Za-z0-9_\-:.%|]{4,160})$` sans `(` ni `)`.
- Correctif : ajouter `()` à la classe, ou encoder les parenthèses dans le générateur de sitemap.

### PANNES

**P1. CEDH 2026 bloquée à 78 %** (alerte « cedh 2026 : 816/1048 (77.9 %) »)
- Journal du 02/10 : 242 identifiants distincts en « HTTP 204 - pas encore converti par HUDOC, on repassera » ; 203 d'entre eux étaient déjà en 204 le 11/09. Ce ne sont donc pas des arrêts « pas encore convertis » : HUDOC n'a pas de fichier pour eux. Vérifié en direct : `001-82735` (Malikowski c. Pologne, 16/10/2007, doctype HFJUD, FRE) -> 204 sur `/app/conversion/docx/html/body`, 204 sur `/app/conversion/pdf/`, 500 sur `/app/conversion/docx/`. En revanche `001-252867` (Témoins de Jéhovah c. Arménie, 01/10/2026) est vraiment récent.
- Effet : ces arrêts n'existent pas sur le site (`get_decision_cedh("001-252867")` -> not_found ; `/decision/cedh/001-252867` -> 404 « Décision introuvable »), et le contrôle quotidien sonnera tant que HUDOC ne les convertit pas.
- Cause : `scrape_cedh.py:116-128` ne distingue pas « récent » de « jamais convertible » ; la paraphrase du commentaire (« typiquement les arrêts publiés depuis quelques jours ») est fausse pour 203/242.
- Correctif suggéré : enregistrer la ligne avec ses métadonnées et `text=''` + un drapeau `sans_texte_hudoc` (titre, date, articles, conclusion sont exploitables et le lien HUDOC aussi), afficher « texte non diffusé par HUDOC » ; dans `controle_couverture.py`, compter à part les documents 204 depuis plus de 14 jours.

**P2. `search_cc` avec filtre de date : 13 à 15 minutes, et la prod en iowait pendant ce temps**
- `search_cc(query="loi", date_min="2026-01-01", limit=3)` : 891,37 s (19:24), puis 794,44 s au retest ; réponse juste (60 décisions). Pendant le retest, `vmstat` sur la prod : 90 % d'iowait. Sans date, `search_cc("liberté d'expression", nature="QPC")` : 14,4 s.
- Le 4/09, `search_cc(date_min="2026-01-01")` avait été validé (« 0 -> 51 ») ; la lenteur n'avait pas été notée.
- Cause probable : `sources/dila.py:463-480` : `decisions_fts MATCH ? AND d.juridiction = 'Conseil constitutionnel' AND d.date >= ? ... ORDER BY d.date DESC` sur la table de 28 Go ; SQLite part de l'index de date (toutes les décisions 2026, tous ordres confondus) ou du MATCH sur un mot très courant, puis lit chaque ligne. Puis un `COUNT(*)` qui refait tout.
- Correctif suggéré : filtre de juridiction DANS la requête FTS (`juridiction:"Conseil constitutionnel"`, procédé déjà retenu le 8/09 pour le judiciaire), ou table `constit` dédiée (7 400 lignes) ; `statement timeout` (progress handler) à 20 s avec une erreur explicite.

**P3. Coupure de 90 s chaque fois que unattended-upgrades redémarre les services**
- 02/10 06:49:14 : `apt-daily-upgrade` relance systemd, qui arrête nginx, MCP, token. MCP revenu à 06:50:44. access.log : 274 `POST /mcp 502` dans l'heure 06 ; `error.log` : 279 « connect() failed (111: Connection refused) ».
- Correctif : `Needrestart`/`Unattended-Upgrade::Automatic-Reboot` en mode liste, ou fenêtre de maintenance à 03:00 UTC (creux : ~1 000 req/h contre 6 000 à 10 h).

**P4. Sous-sitemaps trop lents : Google prend des 504**
- `sitemap-ariane-1.xml` : 504 à 60,06 s (avant le redéploiement de 19:51), puis 200 en 32,95 s ; `sitemap-cedh-1.xml` 56,25 s ; `sitemap-cjue-1.xml` 31,71 s ; `sitemap-dila-53.xml` 30,38 s ; `sitemap-dila-1.xml` 27,05 s. `error.log` : 5 « upstream timed out » sur `GET /sitemap-ariane-1.xml` (+1 sur ariane-3) depuis le 22/09. Tous en `cf-cache-status: DYNAMIC` malgré `cache-control: public, max-age=86400`.
- Correctif : générer les sitemaps la nuit sur disque (fichiers statiques servis par nginx), ou étendre la règle de cache Cloudflare à `/sitemap*`.

### UTILISATEURS REFUSÉS

**R1. Le limiteur nginx compte par IP de Cloudflare, et l'origine est joignable en direct**
- Config exacte (prod, identique à `ops/nginx/justicelibre.conf`) : `/etc/nginx/conf.d/rate_limit.conf` : `limit_req_zone $binary_remote_addr zone=justicelibre_rl:10m rate=10r/s;` et `limit_conn_zone $binary_remote_addr zone=justicelibre_conn:10m;` ; vhost l. 8-11 : `limit_conn justicelibre_conn 50; limit_req zone=justicelibre_rl burst=20 nodelay;`. Aucune directive `set_real_ip_from` / `real_ip_header CF-Connecting-IP` dans `/etc/nginx` (grep vide), alors que le module `http_realip_module` est compilé.
- Preuve que nginx voit Cloudflare : `ss` sur :443 de la prod, pairs = 172.68.x, 162.159.x, 172.70.x, 104.23.x (plages Cloudflare). Le journal du MCP logge aussi des IP Cloudflare (`104.23.229.60:0 - "POST /mcp"`).
- Donc tous les visiteurs qui passent par le même nœud Cloudflare partagent 10 req/s. Dans `error.log` (22/09-02/10), 3 128 refus visent des IP Cloudflare (69 nœuds distincts), dont : 102 `/api/decision` le 29/09 à 14:40 (un client Mac sur `search.html?q="téléassistance" ET "SDIS"...`, ~140 appels en 2 s ; `loadDecision` de `search.html` n'est appelée qu'au clic, l. 1641 et 2618 : ce n'est pas la page, c'est une extension ou un script) ; 100 `/mcp` (BRANCO surtout, 1 `node`). Les 19 558 autres refus visent des IP NON Cloudflare : des scanners qui attaquent l'origine **en direct** (`94.154.46.242-250`, `93.152.209.6`...).
- Vérifié : `curl --resolve justicelibre.org:443:46.225.190.237 https://justicelibre.org/index.html` -> 200. L'origine n'est pas restreinte à Cloudflare : le cache, le WAF et le blocage d'IP de Cloudflare sont contournables.
- Correctif suggéré : `set_real_ip_from` sur les plages Cloudflare + `real_ip_header CF-Connecting-IP;` (le limiteur comptera alors par visiteur), et n'accepter sur 443 que les plages Cloudflare (ou Authenticated Origin Pulls). Effet de bord RGPD à noter : `error.log` contient déjà des IP en clair (`client: ...`, 23 502 lignes), ce qui contredit la promesse « journaux sans IP » ; avec real_ip ce seront les IP réelles des visiteurs : prévoir `error_log` en niveau `crit` ou une durée de rétention courte.

**R2. Les 6 941 réponses 429 : ce sont des scanners, pas des utilisateurs**
- Sur les 50 000 dernières lignes (02/10 07:57 -> 19:08) : 6 724 réponses 429. Par user-agent : « Googlebot/2.1 » 6 671 (faux Googlebot : il demande `/.env`, `/token.txt`, `/ansible/vars/secrets.yml`, `/.claude/settings.json`), « Windows Chrome » 51 (même scanner, `/.env*`, `/.aws/*`), BRANCO 2. Par chemin : statique 6 694, `/api/.env*` 28, `/mcp` 2. Rafales : 3 155 refus dans la seule minute 11:22, 1 892 à 10:11.
- Sur toute la période (12/09-02/10) : 39 154 réponses 429, dont 38 554 sur des chemins statiques inexistants ; sur de vrais chemins : `/mcp` 112 (BRANCO 111), `/api/decision` 102 (le client du 29/09), reste = scanners sur `/api/.env*`. Aucun 429 sur `Claude-User`, `codex-mcp-client`, `claude-code`.
- Conclusion : le limiteur fait surtout le travail d'un pare-feu, et il le fait par chance (les scanners frappent l'origine en direct). Les vrais refusés sont BRANCO et un client navigateur trop rapide.

**R3. `/api/search` limité au judiciaire : 19 résultats et jamais de bouton « Charger la suite »**
- `GET /api/search?q=licenciement+faute+grave&limit=30&offset=0&sources=dila&timeout=12&juridiction=cass` (ce que `search.html` envoie, `fetchOneSource` l. 2474, `PAGE_SIZE = 30`) -> `total 33596, total_rendus 19`. Avec `limit=10` -> 6, `limit=20` -> 11, `limit=50` -> 27.
- `search.html` l. 1628 : `canLoadMore = ... lastChunkSize >= PAGE_SIZE` ; 19 < 30, donc le bouton n'apparaît pas. Un usager qui filtre « Cour de cassation » voit 19 arrêts sur 33 596, sans suite possible.
- Cause : `search_api.py:1016` `dila_r = _dedupe_ecli(dila_r)` retire les jumeaux (JURITEXT / Judilibre) APRÈS le `LIMIT` SQL ; le nombre rendu tombe sous `limit`.
- Correctif : demander `limit*2` à dila puis couper à `limit` après dédoublonnage ; côté page, décider « suite » sur `total > offset + rendus` plutôt que sur la taille du lot.

### LENTEUR

**L1. `search_admin` avec juridiction en forme courte : 32 à 45 s, et l'open data saute**
- `search_admin("refus de titre de séjour", juridiction="TA Lille", limit=3)` : 45,33 s, `"note_opendata": "open data TA/CAA indisponible : RuntimeError: entrepôt de données injoignable sur /v1/search/opendata - ReadTimeout: délai dépassé (> 15s)"`, `"total": 9` (JADE seul). Retest : 32,03 s, cette fois `total_opendata: 9030`. Même requête avec `juridiction="TA59"` : 2,38 s.
- Le refus est dit (`note_opendata`), donc pas un faux ; mais le champ `total: 9` reste le premier lu. Suggestion : `total` = somme quand l'open data a répondu, et `total_incomplet: true` sinon.
- Aussi : `limit=3` rend 6 décisions (3 JADE + 3 open data), contre la docstring « limit: nombre de résultats (défaut 20, max 50) ». Même motif pour `search_decisions_citing(limit=3)` -> 9 (mais là la docstring dit bien « par source »).

**L2. Pages `/decision/` à froid : 8 à 14 s**
- `/decision/admin/DTA_2409211_20260929` 9,64 s ; `/decision/doctrine/ariane_crp:4294` 8,68 s ; `ORTA_2603724_20260721` 13,66 s ; `/decision/admin/DCE_427999_20211007` 8,63 s. `error.log` : 7 « upstream timed out » sur `/decision/admin/ORTA_*` et `DCA_*` (504) en 48 h.
- Cause probable : le préchauffage des articles cités (`ssr.py`, ThreadPoolExecutor, jusqu'à 16 `/v1/law` par page, visible dans le journal du token à 19:50 : 5 appels `/v1/law` pour une seule page), plus l'appel live à `opendata.justice-administrative.fr` pour les `ORTA_`. Le remède noté le 17/09 (« ssr.py sans préchauffage ») n'est pas fait.

### COSMÉTIQUE / DOC QUI NE DIT PAS VRAI

- C1. `search_cc` docstring : « (7 112 décisions) » ; la base en compte plus de 7 379 depuis le 4/09. `sources/dila.py:441` idem.
- C2. `search_admin_recent` refuse « TA Lille » (`unknown juridiction code: 'TA Lille'`) alors que `search_admin` l'accepte : deux outils voisins, deux grammaires.
- C3. `get_admin_decision` par le chemin open data rend des métadonnées sans `full_text` (`DTA_2409211_20260929` : 333 octets), par le chemin JADE il rend le texte (`23MA01338` : 15 420 octets). La docstring annonce « métadonnées » ; l'écart n'est pas dit.
- C4. `/api/search` fédéré : `total` vaut 38 pour « licenciement faute grave » toutes sources, et 70 614 avec `sources=dila` ; pour `permis de construire`, `sources=admin`, `total` passe de 20 (offset 0) à 10 (offset 30). `total_exact: false` le signale, mais un total qui baisse en tournant les pages déroute.
- C5. `sitemap-dila-54.xml` (hors plage) -> 200 avec 0 URL ; un 404 serait plus propre.
- C6. `stats.json` : fuseau codé en dur (`server.py:195`, `timezone(timedelta(hours=2))`) ; faux d'une heure à partir du 25/10.
- C7. `/v1/health` de l'entrepôt annonce `"fd_plafond": 1024` : c'est bien la limite molle du processus (`Max open files 1024 / 524288`), alors que l'unité systemd déclare 524288 ; la limite molle n'est pas relevée.
- C8. Prod et dépôt local : `token_server.py` diffère (le local a l'aiguillage `JL_SSR_V2`, l. 690-692 et 759-760, non déployé) ; à garder en tête avant le prochain rsync.

### CE QUI MARCHE (comparaison avec l'audit du 4/09)

- Les 5 correctifs du 4-5/09 tiennent : dates validées au calendrier sur tous les outils testés (`2025-02-30`, `2026-13-01`, `2024-02-30` -> `error_category: "validation"`) ; `search_judiciaire_libre` refuse « cour lunaire » ; `search_cc` refuse `nature="XYZ"` ; `search_doctrine` refuse une source inconnue.
- Tous les `get_*` refusent proprement un identifiant inexistant (`not_found`, jamais de voisin) : CETATEXT, DTA, ArianeWeb, JURITEXT, hex, CC `2026-9999`, CC numéro juste + nature fausse, CE `999998`, HUDOC `001-999999`, CELEX, doctrine. `get_admin_decision("2409211", "TA75")` rend bien la décision du TA de Paris portant ce numéro, pas celle de Marseille.
- `/api/search` : pièges `date_min=2026-02-30`, `juridiction=lune`, `sources=xyz` -> `filtres_ignores` explicite ; `q=ab` -> 400. Références : pourvoi `12-11.527` -> l'arrêt ; `001-171528` -> l'arrêt ; `ECLI:EU:C:2020:559` -> Schrems II ; `C-311/18` -> l'arrêt et les conclusions ; `ECLI:FR:CEORD:2026:512506.20260218` -> trouvé.
- Temps : la plupart des outils répondent entre 0,07 s et 2 s (search_conseil_etat 0,36 s, search_cedh 1,9 s, search_cjue 0,17 s, get_* < 0,5 s). Lents : search_cc avec date (P2), search_admin forme courte (L1), search_cc sans date 14,4 s, search_decisions_citing 12,9 s, search_judiciaire_libre cass 6,8 s, search_all 6,7 s.
- Pages statiques toutes 200 (annuaire.html 2,4 Mo en 0,9 s). Sitemaps : 97 sous-sitemaps listés, 36 URL tirées sur 39 en 200, 1 en 404 (F5), 0 en erreur après le redéploiement.
- Entrepôt : `status ok`, 17 descripteurs ouverts, 0 connexion pendante, jamais vu `degraded`. Les 34 lignes « error/exception » du journal 48 h sont des faux positifs (mots de requêtes : « exception d'illégalité »).
- CJUE : la tâche quotidienne finit en timeout (30 min) un jour sur deux depuis le 09/09, mais la couverture reste 100 % (2025 et 2026) : elle relit toutes les années, récentes d'abord. Gaspillage, pas une panne.

## 2. RESSOURCES

- **Entrepôt (46.224.173.253)** : `/` 301 Go, 256 Go utilisés, 33 Go libres (89 %). Gisements sans toucher aux bases servies : `/root/backups/justicelibre-prod` 24 Go, `/opt/justicelibre/dila/legi.db.bak_20260709` 3,7 Go, `/root/backups/doctrine-avant-cada-20260908.db` 1,3 Go, `/root/PL1` 10 Go, dumps neo4j 1,5 Go ; `/home/dahl` 44 Go, `/var/lib` 67 Go. RAM 31 Go, 13,8 Go disponibles, pas de swap. Warehouse redémarré le 02/10 06:52 (unattended-upgrades), 0 redémarrage anormal.
- **Prod (46.225.190.237)** : `/` 67 % (13 Go libres), `/mnt/digesta` 79 % (14 Go libres). RAM 3,8 Go, 139 Mo libres, 2,6 Go disponibles, swap 498 Mo utilisés ; MCP RSS 614 Mo, 92 fd / 1 024 ; token 200 Mo (pic 1,2 Go et 158 Mo de swap avant le redéploiement de 19:51). Load 0,2 au repos, 2,8 avec iowait 50-90 % pendant `search_cc` daté (P2). 361 connexions TCP.
- **5xx sur 48 h** (30/09-02/10) : 274 + 5 `502 /mcp` (02/10 06h, P3), 7 `500 /api/law/batch` (30/09 09-16h, domaine loi, signalé à l'autre agent), 6 `504 /decision/admin/ORTA_*` ou `DCA_*` (L2), 2 `502` isolés à 06h. Plus le 502 du redéploiement de 19:51 (pas dans les journaux copiés).

## 3. PORTRAIT DU TRAFIC

### Volume
Requêtes nginx par jour (toutes) et appels d'outils MCP (`stats.json`, jour de Paris) :

| jour | nginx | dont /mcp | /decision/ | 429 | appels d'outils |
|---|---|---|---|---|---|
| 12/09 | 149 311 | 19 179 | 117 571 | 1 056 | 3 104 |
| 15/09 | 209 183 | 24 988 | 162 684 | 386 | 6 336 |
| 17/09 (blocage SEO) | 109 910 | 26 918 | 74 948 | 109 | 5 312 |
| 18/09 | 44 768 | 29 461 | 3 005 | 5 022 | 5 575 |
| 21/09 | 51 436 | 31 883 | 9 953 | 4 225 | 6 359 |
| 28/09 | 56 667 | 44 263 | 2 842 | 3 371 | 14 124 |
| 29/09 | 47 465 | 35 848 | 5 359 | 311 | 6 326 |
| **30/09** | **79 972** | **62 232** | 8 558 | 515 | **18 574** |
| 01/10 | 68 268 | 51 759 | 4 313 | 228 | 11 719 |
| 02/10 (jusqu'à 19h) | 66 940 | 50 213 | 3 662 | 7 481 | 12 379 |

Le « 18 574 le 30/09 » est le compteur d'**appels d'outils** de `stats.json`, pas un nombre de requêtes HTTP (79 972 ce jour-là). C'est le record du compteur ; le précédent pic était 14 124 le 28/09. Avant le 17/09, le trafic HTTP était plus gros mais c'était AhrefsBot.

30/09 par heure UTC (toutes / /mcp) : creux 01h (953 / 668), montée dès 05h, plateau 07h-17h entre 3 300 et 6 050 requêtes/h, pic 10h (6 051 / 4 634). Appels d'outils : pic 17h UTC (2 484), deuxième pic 22h (1 912, surtout `get_decision_text` 806 et `get_decision_judiciaire_libre` 552).

Outils les plus appelés (cumul depuis juillet) : get_law_article 123 266, search_judiciaire_libre 68 769, get_decision_judiciaire_libre 44 829, search_admin 22 708, get_decision_text 22 496, search_legi 19 666. Le 30/09 : get_law_article 8 370 (45 % du jour), get_decision_text 2 575, search_judiciaire_libre 1 726, search_admin 1 354.

### Qui (26/09 -> 02/10, requêtes nginx)
- `Claude-User` 122 915 (dont 122 069 sur /mcp) : le connecteur de claude.ai, donc des personnes qui posent des questions à Claude. C'est le cœur du trafic réel.
- `python-httpx/0.28.1` 54 138 : un sondeur. La nuit du 30/09 à 01h, 363 POST /mcp : `initialize` + `tools/list` (56 938 octets) toutes les ~16 s, sans appel d'outil. Registre ou surveillance.
- `BRANCO/0.7 (+https://justicelibre.org)` 38 041 (voir ci-dessous).
- `codex-mcp-client` 33 325, `node` 16 286, `undici` 8 726, `claude-code` 13 326 (desktop, sdk-cli, cli), `Cursor` 2 094, `MistralAI-MCPClient`, `mcpbeat` 3 092 et `SentinelOracle` 2 323 (sondes de vivacité).
- Moteurs : bingbot 17 089, Googlebot (vrai et faux) 11 362, YandexBot 3 648, SERankingBacklinksBot 4 809 (aspirateur SEO non bloqué, même famille que ceux du 17/09), DataForSeoBot passe encore (21 hits `/decision/` le 02/10, mais 403 : il est dans la liste).

### a. Les 429 : voir R1 et R2
Le limiteur est indexé sur l'IP vue par nginx, qui est celle du nœud Cloudflare pour le trafic normal (aucun `real_ip`). 98 % des 429 frappent des scanners qui contournent Cloudflare en attaquant l'origine en direct ; les 2 % restants touchent BRANCO et un client navigateur emballé, à travers des compteurs partagés par nœud Cloudflare.

### b. BRANCO/0.7
- 47 065 requêtes du 12/09 au 02/10, toutes sur `/mcp` (31 331 `POST 200`, 15 339 `POST 202`, 268 `GET /mcp` SSE, 111 `429`, 8 `HEAD /`). Referer vide. Démarré le 12/09 à 10:08 ; 52 requêtes ce jour-là, 4 391 le 20/09, puis 15 082 le 30/09, 7 619 le 01/10, 11 527 le 02/10.
- Rythme : une session neuve par appel (`initialize` 3 506 octets, `notifications/initialized` 202, un appel), jamais de réutilisation ni de `DELETE`. Pointe à 330 requêtes/min (02/10 15:38), soit ~110 appels/min ; c'est ce qui le fait buter sur 10 req/s par nœud Cloudflare.
- Ce qu'il demande (inférence par corrélation horaire) : le 30/09 à 02h UTC, BRANCO ouvre 45 sessions et `stats.json` compte 45 appels, dont 42 `get_law_article` ; à 07h, 473 sessions et 366 `get_law_article` ; à 09h, 679 sessions et 684 `get_law_article`. Ses réponses : médiane 3 506 octets (l'`initialize`), p90 5 317, max 1,9 Mo. **BRANCO est très probablement un client qui moissonne des articles de loi un par un**, et il explique l'essentiel de la hausse des `get_law_article` (4 981 le 28/09, 8 370 le 30/09). Il pèse donc sur l'entrepôt (chaque appel = un `/v1/law`).
- Se fait-il passer pour le site ? Il ne vise que justicelibre.org ; la mention `(+https://justicelibre.org)` est l'endroit où un robot met SA page d'information : il se présente donc comme un robot de justicelibre. Notre propre moissonneur s'annonce autrement : `justicelibre.org/1.0 (open data, contact: dahliyaal@justicelibre.org)` (`scrape_ariane.py`). Aucune occurrence de « BRANCO » dans `/home/dahl` (fichiers .py/.js/.ts/.json/.md/.sh/.toml), ni dans `/opt` et `/root` des deux serveurs. Ce n'est pas le projet. Identité inconnue (pas d'IP, voir manifeste).
- Suggestion : ne rien bloquer ; publier dans `about_justicelibre` un point d'accès en masse (dump LEGI, ou `/api/law/batch` documenté) et une règle « une session pour plusieurs appels ».

### c. Robots
- AhrefsBot/SemrushBot/MJ12bot/DotBot/DataForSeoBot : 105 000 à 149 000 requêtes/jour en 200 du 12 au 16/09 ; depuis le 18/09, 27 à 187 requêtes/jour, toutes en 403. Le blocage tient.
- L'aspirateur « Chrome à versions tournantes » (Referer vide, Mac 10_15_7 et Windows, `Chrome/99` à `Chrome/136`, 18 à 24 versions par jour) : 30 340 pages `/decision/` le 15/09 (212/min au pic), 27 596 le 17/09, revenu le 20/09 (8 266, 105/min) et le 21/09 (7 328, 87/min). Depuis le 29/09 il tourne bas : 1 209 (30/09), 1 320 (01/10), 1 126 (02/10), au plus 14/min. Il reste, à 1/15 de son débit d'origine.
- Cache Cloudflare : il marche sur les pages HTML. `/decision/ariane/%2FAriane_Web%2FAW_DCE%2F%7C114750` et `/loi/CSP/R6113-30` : 1er appel `cf-cache-status: MISS`, 2e `HIT`, `cache-control: public, max-age=86400`. Les 404 ne sont pas cachés (`/decision/cedh/001-200000` MISS deux fois). Restent `DYNAMIC` : `/sitemap*.xml`, `/index.html`, `/search.html`, `/api/*`. Effet : `/decision/` à l'origine tombe de 117 000-160 000/jour à 2 500-8 500/jour ; mais l'origine reste joignable en direct (R1), donc un aspirateur qui la découvre contourne le cache.

## 4. LES DEUX ALERTES DU CONTRÔLE QUOTIDIEN : RÉPONSES

- « ariane : dernier moissonnage = 2026-09-10 » : vraie alerte. Point de reprise enregistré au-delà du dernier identifiant vivant, qui avance de 5 000 par jour (F2). Le cron dit « OK » chaque jour. Aucune unité systemd : c'est la ligne `0 5 * * * /bin/bash /opt/justicelibre/scripts/scrape_increments_daily.sh` de la crontab root.
- « cedh 2026 : 816/1048 (77.9 %) » : à 85 % des documents que HUDOC ne sait pas convertir (204 persistant depuis au moins trois semaines), à 15 % des arrêts vraiment récents (P1). Le scraper tourne et ajoute 3 à 9 arrêts par jour.

/home/dahl/justicelibre/scratchpad/audit/audit_site_trafic_2oct.md
