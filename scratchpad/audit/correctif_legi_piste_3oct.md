# Correctif ciblé de `legi_articles` d'après l'API Légifrance (PISTE), 3 octobre 2026

**Rien n'a été écrit sur l'entrepôt ni sur la prod. Aucun redémarrage, aucun kill de service, aucun commit.** Lectures entrepôt en `sqlite3 -readonly` / `mode=ro`. Le seul processus arrêté est mon propre script de collecte (`fetch.py`), relancé ensuite.

Dossier de travail : `/home/dahl/justicelibre/scratchpad/audit/legi_piste_3oct/`
**Patch : `/home/dahl/justicelibre/scratchpad/audit/legi_piste_3oct/patch_legi_piste_3oct.sql`** (58 947 146 octets, sha256 `0b497c14724ea46f1ece225b7a73dbbe6c91f8ea6811aae206aada4afb22630c`).

## Résultat en cinq lignes

1. Cible : **11 266 LEGIARTI** (14 152 lignes), tous appelés ; 11 203 réponses exploitables, **63 « article: null »** (inconnus de l'API, laissés intacts).
2. Patch : **11 042 LEGIARTI corrigés**, 2 881 lignes fantômes supprimées, 8 541 états, 759 dates de fin, 241 textes, 128 notas, 22 numéros mis aux valeurs officielles ; 161 déjà conformes (aucune instruction).
3. Essai à blanc : LEGIARTI à plusieurs lignes 2 764 → **5** (les 5 sont parmi les 63 inconnus de l'API) ; `VIGUEUR_DIFF` passés 9 025 → 63 (59 inconnus de l'API + 4 que l'API elle-même donne `VIGUEUR_DIFF`).
4. Les 8 articles faux de l'audit, 3 dates chacun (aujourd'hui, 2026-09-15, 2026-02-25), via le vrai `law_at_date` du dépôt : **21/21 conformes à l'API** (LEGIARTI, état, dates, texte) ; **CGI 1496 ter (3 cas)** : l'API n'a aucune version en vigueur à ces dates, le service rend désormais la version 2029 avec la note « Aucune version en vigueur… », ce qui est juste.
5. Témoins hors cible : **200/200 identiques** (hash de ligne avant/après) ; patch idempotent (2ᵉ passe : base identique au hash près) ; `integrity-check` FTS5 OK.

## MANIFESTE DE COUVERTURE

### Lu
| Source | Portée |
|---|---|
| `scratchpad/audit/audit_lois_2oct.md` | 1-297, entier |
| `parse_dila_bulk.py` | 1-499 (helpers 32-151, schéma 227-286, ART_SQL 317-330, PURGE_SQL 339, flush 348-363, extraction article 386-418) |
| `warehouse/warehouse_server.py` | 455-694 (`law_at_date` 462-536, `_legi_key` 601-609, `_law_row_to_dict` 629-658, `_etat_effectif` 661-680), `_conn` 356-370, 46-62 (clé) |
| Schéma prod `legi_articles` | `.schema legi_articles`, `.schema legi_articles_fts`, `sqlite_master` (sortie dans `schema.json`) |

### Non vérifié
- Le `warehouse_server.py` de la PROD n'a pas été comparé au dépôt aujourd'hui (l'essai utilise celui du dépôt, qui contient le filtre `MORT_NE` l. 493).
- Site Légifrance : non ouvert (anti-robot, cf. audit du 2/10) ; seule l'API PISTE fait foi ici.
- `hierarchie` / `titre_section` (F9) : non comparés, non touchés.
- Les 241 changements de texte n'ont pas été relus un à un ; 38 ont été inspectés par la position de la première différence (voir « Texte »).
- Le patch n'a été essayé que sur la copie réduite (14 352 lignes) ; durée et verrouillage sur la base de 9 Go non mesurés.

## 1. Liste cible (lecture seule)

Script `extract_remote.py`, exécuté sur l'entrepôt par `ssh root@46.224.173.253 'nice python3 -' < extract_remote.py`, connexion `file:/opt/justicelibre/dila/legi.db?mode=ro`. Critères : `GROUP BY legiarti HAVING COUNT(*)>1` ; `etat='VIGUEUR_DIFF' AND date_debut<='2026-10-03'` ; les 8 LEGIARTI servis faux par l'audit + **toutes les versions du même (legitext, num)** (pour pouvoir rejouer `law_at_date`). Plus 200 témoins hors cible (tirage déterministe par rowid).

Contrôle préalable sur l'entrepôt :
```
SELECT COUNT(*) FROM (SELECT legiarti FROM legi_articles GROUP BY legiarti HAVING COUNT(*)>1);  → 2764
SELECT COUNT(*), COUNT(DISTINCT legiarti) FROM legi_articles WHERE etat="VIGUEUR_DIFF" AND date_debut<="2026-10-03"; → 9025|8991
```
Sortie de l'extraction : `14352 extract.jsonl` ; répartition `Counter({('vdiff',): 8329, ('multi',): 4229, ('multi','vdiff'): 1403, ('temoin',): 200, ('audit_frere',): 170, ('audit','audit_frere','multi','vdiff'): 14, ('audit','audit_frere'): 2, ('audit_frere','multi'): 2, ('audit_frere','multi','vdiff'): 2, ('audit_frere','vdiff'): 1})` ; `legiarti distincts cible 11266`.

État de la base lue : `legi.db` mtime `Oct 2 04:00` (`ls -la`). NB : il existe aussi sur l'entrepôt `legi.db.avant-fix-fantomes-20261002` (19:44, même taille) — sauvegarde faite par quelqu'un d'autre le 2/10, non touchée.

## 2. Appels API

`piste.py` (OAuth client_credentials, secrets lus dans `.env`, jamais affichés), `fetch.py` : ≤ 2,5 req/s (pause 0,4 s ; débit réel ~1,65/s), arrêt sur 429 ou quota, arrêt après 20 erreurs consécutives, **reprise** : saute les LEGIARTI déjà dans `officiel.jsonl` ; mode ciblé `fetch.py liste.txt` (la dernière ligne d'un identifiant fait foi).

| | Nombre | Source |
|---|---|---|
| Ciblés | 11 266 | `fetch.log` : « cible 11266 » |
| Appelés | 11 266 (+ 381 + 24 rappels) | `officiel.jsonl` 11 647+24 lignes |
| Réponse exploitable | 11 203 | `Counter({(200, True): 11203, (200, False): 63})` |
| « article: null » (HTTP 200) | 63 | ex. `LEGIARTI000051787735` → `{'executionTime': 0, 'dereferenced': False, 'article': None}` ; en base : `1060734|…|LEGITEXT000037034491|3|VIGUEUR_DIFF|2026-01-01|2999-01-01|5177` |
| 401 | 24, tous rappelés avec succès | expiration du jeton en fin de collecte ; `refetch2.txt` |
| 429 / quota | 0 | — |

Les 381 rappels : j'ai corrigé la normalisation du texte en cours de route (ci-dessous) ; les réponses déjà reçues dont le texte ou la nota différait de la base ont été redemandées pour garder le HTML brut (`refetch.txt`).

### Normalisation du texte (`norm.py`)
Le parseur stocke `strip_html(ET.tostring(CONTENU))` (`parse_dila_bulk.py:401`, `:68-73`, `:32-40`). Je réutilise **la même fonction `strip_html` importée de `parse_dila_bulk.py`**, appliquée à `texteHtml`, avec deux ajustements constatés :
- l'API habille de `<a>` des renvois qui sont du texte nu dans le XML : retrait de la balise **sans espace** (sinon « l' article L. 229-6 du code de l'environnement , », 5 écarts sur 40 témoins) ;
- l'API laisse des `<` littéraux que le XML échappe (`Tétrachloroazobenzène< 1 ppm`, `dép<CB>t`, constatés dans `texteHtml`) : tout `<` qui n'ouvre pas une balise HTML connue est échappé avant `strip_html`.

Mesure sur 40 témoins sains (avant le 2ᵉ ajustement) : `exact 39 cle 40 /40` ; `etat`, `date_debut`, `date_fin`, `num`, `nota` : 40/40.
**Règle de prudence** : le texte (et la nota) de la base n'est remplacé que si son contenu diffère de l'officiel **hors blancs** (`cle()` = suppression des blancs). Un écart d'espaces seul ne réécrit rien ; un texte officiel vide ne remplace jamais (comme `ART_SQL`, l. 327).

Dates : millisecondes epoch → `YYYY-MM-DD` UTC ; `32472144000000` → `2999-01-01`, format identique à la base (témoins 40/40).

## 3. Le patch

`build_patch.py` → `patch_legi_piste_3oct.sql`, `BEGIN IMMEDIATE; … COMMIT;`. Pour chaque LEGIARTI à corriger, deux instructions :
```sql
DELETE FROM legi_articles WHERE legiarti='X' AND rowid <> COALESCE(
  (SELECT rowid FROM legi_articles WHERE legiarti='X' AND date_debut='<début officiel>'),
  (SELECT MAX(rowid) FROM legi_articles WHERE legiarti='X'));
UPDATE legi_articles SET date_debut=…, etat=…, date_fin=…, num=…, texte=…, nota=…
 WHERE legiarti='X' AND (date_debut IS NOT … OR etat IS NOT … OR …);
```
- Ligne gardée : celle à la date de début officielle (ou, à défaut, la plus récemment ingérée) ; mesuré : **0 cas** sans ligne à la date officielle (aucun `chg_date_debut` dans les compteurs).
- `legitext`, `jorftext`, `hierarchie`, `liens`, `ancien_id`, `type_article`, `titre_text` : **jamais dans le SET**, donc conservés de la ligne gardée.
- Idempotent : le DELETE ne trouve plus rien, l'UPDATE est gardé par `IS NOT` (aucune écriture ni trigger à la 2ᵉ passe).
- FTS : `legi_articles_fts` est un FTS5 à contenu externe (`content='legi_articles'`), tenu par les triggers `legi_art_ad` (AFTER DELETE) et `legi_art_au` (AFTER UPDATE) présents en prod (`.schema`, cf. aussi `parse_dila_bulk.py:264-273`). Aucun `INSERT OR REPLACE` dans le patch, donc pas besoin de `recursive_triggers`. **Pas de reconstruction nécessaire** ; contrôle : `INSERT INTO legi_articles_fts(legi_articles_fts) VALUES('integrity-check')`.
- Contrôle de portée : `11042 True` = les 11 042 identifiants du patch sont tous dans la cible (regex sur le fichier).

Compteurs (`python3 build_patch.py`) : `{'corrige': 11042, 'lignes_supprimees': 2881, 'deja_conforme': 161, 'chg_texte': 241, 'chg_etat': 8541, 'chg_date_fin': 759, 'chg_nota': 128, 'chg_num': 22, 'erreur_api': 63}`. Détail ligne par ligne (avant/après tronqués à 160 car.) : `journal_patch.jsonl`.

### Texte : nature des 241 remplacements
Échantillon des 38 premiers inspectés à la première différence : majoritairement de vraies modifications (L625-2 « l'article L. 432-7 » → « articles L. 2325-5 et L. 2143-21 » ; CGI montants de taxes ; textes de 2022 réécrits par décret 2025). Écarts de **forme** à connaître : entités restées littérales en base (`&laquo;`, `&#171`) remplacées par « » (amélioration) ; pour quelques annexes (`LEGIARTI000046888849`, `…47928954/56/58`) l'intitulé « ANNEXE I… » quitte le texte et passe dans `num` (l'API le met là) ; `LEGIARTI000023347425` perd la phrase finale « La présente loi entrera en vigueur… » que l'API ne porte pas dans ce texte. À relire avant application si l'on veut être strict (`journal_patch.jsonl`, filtre `"texte" in change`).

## 4. Essai à blanc

`dryrun.py` : base temporaire `…/scratchpad/legi_dry/legi.db` créée avec **le schéma exact de prod** (`schema.json` : table, FTS5, 5 index dont `idx_art_version` unique, 3 triggers), chargée des 14 352 lignes extraites (FTS rempli par `legi_art_ai`), patch appliqué deux fois par `executescript`, puis **`law_at_date` réel du dépôt importé** (`JL_WAREHOUSE_DB_DIR` sur la base temporaire, clé factice pour l'import).

Sortie :
```
AVANT : lignes 14352 | LEGIARTI multi 2764 | VIGUEUR_DIFF passés 9025
APRES passe 1 : lignes 11471 | LEGIARTI multi 5 | VIGUEUR_DIFF passés 63
APRES passe 2 : lignes 11471 | LEGIARTI multi 5 | VIGUEUR_DIFF passés 63
idempotence (base identique après 2e passe) : True
FTS integrity-check : OK
FTS integrity-check contenu (rank=1) : OK
témoins inchangés : 200 / 200
```
Multi restants : `['LEGIARTI000051287319', 'LEGIARTI000051830457', 'LEGIARTI000051922527', 'LEGIARTI000053150791', 'LEGIARTI000053150890']`, tous « article: null » à l'API (`[False]*5`). `VIGUEUR_DIFF` passés restants : 63, `dont API nulle 59` ; les 4 autres (`…053592986`, `…054173807`, `…054355651`, `…054355653`) sont `VIGUEUR_DIFF` **selon l'API elle-même** (le service les affiche « VIGUEUR » via `_etat_effectif`, `warehouse_server.py:678`).

« Aucun article sain modifié » : par construction, le patch ne nomme que des LEGIARTI cibles (contrôle de portée ci-dessus) ; mesuré sur 200 témoins hors cible : 200/200 hash identiques.

### Les 8 articles de l'audit (attendu = version de `articleVersions` officiel couvrant la date, hors `MORT_NE`)

| Article | Date | Avant (base actuelle) | Après patch | API | Verdict |
|---|---|---|---|---|---|
| CGI 1754 | aujourd'hui | 053189001 VIGUEUR_DIFF 2026-09-01→2999 | 053881346 ABROGE_DIFF 2026-05-01→2027-01-01 | 053881346 idem | conforme |
| CGI 1754 | 2026-09-15 | 053189001 | 053881346 | 053881346 | conforme |
| CGI 1754 | 2026-02-25 | 046872803 VIGUEUR →2999 | 046872803 MODIFIE →2026-05-01 | idem | conforme |
| CGI 279 | aujourd'hui | 048827223 VIGUEUR 2023-12-31→2999 | 053562872 ABROGE_DIFF 2026-03-01→2027-01-01 | idem | conforme |
| CGI 279 | 2026-09-15 | 048827223 | 053562872 | 053562872 | conforme |
| CGI 279 | 2026-02-25 | 053562872 VIGUEUR 2026-02-21→2026-09-01 | 053574745 MODIFIE 2026-02-21→2026-03-01 | idem | conforme |
| CGI 200 | aujourd'hui | 053154489 VIGUEUR_DIFF 2026-09-01 | 053543932 ABROGE_DIFF 2026-02-21→2027-01-01 | idem | conforme |
| CGI 200 | 2026-09-15 | 053154489 | 053543932 | 053543932 | conforme |
| CGI 200 | 2026-02-25 | 053543932 ABROGE_DIFF →2026-09-01 | 053543932 →2027-01-01 | idem | conforme |
| C.com L441-10 | aujourd'hui | 053151445 VIGUEUR_DIFF 2026-09-01 | 038414392 ABROGE_DIFF 2019-04-26→2027-01-01 | idem | conforme |
| C.com L441-10 | 2026-09-15 | 053151445 | 038414392 | 038414392 | conforme |
| C.com L441-10 | 2026-02-25 | 038414392 VIGUEUR →2999 | 038414392 ABROGE_DIFF →2027-01-01 | idem | conforme |
| C.com L625-2 | les 3 | 019984048 VIGUEUR, **texte périmé** | 019984048 VIGUEUR, texte officiel | idem | conforme |
| LPF L80 B | aujourd'hui | 053189313 VIGUEUR_DIFF 2026-09-01 | 054674686 VIGUEUR 2026-07-29→2999 | idem | conforme |
| LPF L80 B | 2026-09-15 | 053189313 | 054674686 | 054674686 | conforme |
| LPF L80 B | 2026-02-25 | 053544570 ABROGE_DIFF 2026-02-21→2026-09-01 | 053544570 MODIFIE 2026-01-01→2026-07-29 | idem | conforme |
| LPF L16 B | aujourd'hui | 053189711 VIGUEUR_DIFF 2026-09-01→2029 | 054337102 ABROGE_DIFF 2026-06-27→2027-01-01 | idem | conforme |
| LPF L16 B | 2026-09-15 | 053189711 | 054337102 | 054337102 | conforme |
| LPF L16 B | 2026-02-25 | 048834116 VIGUEUR →2999 | 048834116 MODIFIE →2026-06-27 | idem | conforme |
| CGI 1496 ter | les 3 | 041403640 VIGUEUR_DIFF **2026-01-01** | 041403640 VIGUEUR_DIFF **2029-01-01** + note « Aucune version en vigueur aujourd'hui ; version la plus récente retournée. » (resp. « …à la date demandée… ») | aucune version en vigueur à ces dates | conforme (plus servi comme droit courant) |

(Identifiants abrégés : préfixe `LEGIARTI000`.) Texte comparé sur le texte complet : `texte_ok` vrai pour les 21 cas datés (`dryrun_8.json`). Exemples d'extraits après/avant (texte servi par `law_at_date` sur la base d'essai) :
- C.com L625-2 : avant « Il est tenu à l'obligation de discrétion mentionnée à l'article L. 432-7 du code du travail. » ; après « …mentionnée aux articles L. 2325-5 et L. 2143-21 du code du travail. »
- CGI 279 : avant « b septies. S'ils sont réalisés jusqu'au 31 décembre 2025 » ; après « …jusqu'au 31 décembre 2028 ».
- CGI 1754 : avant contient « biens et services », après « chiffre d'affaires » ; C.com L441-10 : avant « L. 216-42 », après « 289 du code général des impôts » (tests de présence de chaîne).

NB : sur plusieurs de ces articles l'API d'aujourd'hui diffère de ce que l'audit du 2/10 notait (ex. CGI 1754 attendu au 2/10 « 053881346 VIGUEUR_DIFF 2027-01-01 » ; aujourd'hui 053881346 ABROGE_DIFF 2026-05-01→2027-01-01). Le patch suit l'API du 3/10.

## 5. Procédure d'application proposée (son arbitrage — rien n'a été fait)

1. Vérifier que la base n'a pas bougé depuis l'extraction : `stat -c '%y %s' /opt/justicelibre/dila/legi.db` (attendu mtime 2026-10-02 04:00, 9147002880 octets) et rejouer les deux `COUNT` du § 1 (2764 ; 9025|8991). Si une ingestion DILA a eu lieu entre-temps : **refaire extraction + build_patch** (le patch reste sûr — il ne nomme que des LEGIARTI et ne supprime que les lignes non officielles — mais ses textes ont été choisis contre les lignes du 2/10).
2. Sauvegarde : `sqlite3 /opt/justicelibre/dila/legi.db ".backup /opt/justicelibre/dila/legi.db.avant-piste-20261003"` (≈ 9,2 Go ; vérifier l'espace disque avant). La sauvegarde `legi.db.avant-fix-fantomes-20261002` existe déjà mais n'est pas de moi.
3. Copier `patch_legi_piste_3oct.sql` sur l'entrepôt, vérifier le sha256 ci-dessus.
4. Appliquer hors pointe, en une transaction (le fichier contient `BEGIN IMMEDIATE`/`COMMIT`) : `sqlite3 /opt/justicelibre/dila/legi.db < patch_legi_piste_3oct.sql`. Le serveur ouvre la base en lecture seule (`warehouse_server.py:365-366`) : en WAL les lectures continuent pendant l'écriture ; pas de redémarrage nécessaire.
5. Contrôles :
   - `SELECT COUNT(*) FROM (SELECT legiarti FROM legi_articles GROUP BY legiarti HAVING COUNT(*)>1);` → attendu 5 ;
   - `SELECT COUNT(*) FROM legi_articles WHERE etat='VIGUEUR_DIFF' AND date_debut<='2026-10-03';` → attendu 63 ;
   - `INSERT INTO legi_articles_fts(legi_articles_fts) VALUES('integrity-check');` → aucune erreur ;
   - rejouer en direct `get_law_article` sur les 8 articles × 3 dates et comparer au tableau ci-dessus.
6. Retour arrière : arrêter rien d'autre que les écritures ; `cp legi.db.avant-piste-20261003 legi.db` n'est sûr qu'entrepôt arrêté (ou via `sqlite3 legi.db ".restore legi.db.avant-piste-20261003"`) — à décider par elle, car cela implique de toucher au service.

## 6. Limites — ce que ce correctif ne répare PAS

- **Textes périmés hors cible** : un LEGIARTI à une seule ligne, non `VIGUEUR_DIFF`, dont la DILA a corrigé le texte, l'état ou la date de fin (type C.com L625-2, CPP 85, CSP L1111-7, CP 131-26-2 servis « VIGUEUR → 2999 » au lieu d'« ABROGE_DIFF → 2029 ») n'est pas dans la cible, sauf s'il est un « frère » des 8. Ampleur inconnue ; seule une ré-ingestion DILA complète (ou un balayage PISTE de ~1,8 M LEGIARTI, ~13 jours à 1,65 req/s) le couvre.
- **Versions absentes de la base** : si `articleVersions` officiel contient une version que `legi.db` n'a pas, le patch ne la crée pas (il ne fait qu'UPDATE/DELETE). Non mesuré hors des 8 articles (où tout était présent).
- **63 LEGIARTI inconnus de l'API** (dont 5 encore en double et 59 `VIGUEUR_DIFF` passés) : laissés tels quels ; à trancher à la ré-ingestion.
- `hierarchie` / `titre_section` (F9), `titre_text`, `liens` : non touchés.
- `legi_textes` : non touché.
- Le code d'ingestion corrigé (`parse_dila_bulk.py:317-339`) refera de toute façon ces corrections à la prochaine ré-ingestion ; ce patch est un pont en attendant que echanges.dila.gouv.fr réponde (pas retesté aujourd'hui).
- F3 à F8 de l'audit (404 `/loi/`, dates hors calendrier, recherche, lenteur) : hors champ.

## Fichiers
- `scratchpad/audit/legi_piste_3oct/extract_remote.py`, `extract.jsonl` (lignes actuelles complètes), `schema.json`
- `piste.py`, `fetch.py`, `norm.py`, `officiel.jsonl` (réponses normalisées + HTML brut pour la plupart), `fetch.log`, `fetch2.log`, `refetch.txt`, `refetch2.txt`
- `build_patch.py`, **`patch_legi_piste_3oct.sql`**, `journal_patch.jsonl`
- `dryrun.py`, `dryrun_8.json` ; base d'essai `/tmp/claude-1000/-home-dahl/748c09b7-716e-46e8-9843-1281859081b9/scratchpad/legi_dry/legi.db`
