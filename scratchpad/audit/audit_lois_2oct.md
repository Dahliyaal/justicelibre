# Audit des articles de loi servis par justicelibre.org, 2 octobre 2026

Lecture seule. Aucune écriture, aucun redémarrage, aucune modification sur aucune machine. Entrepôt : `/v1/health` = `ok` au début (fd 10/1024) et à la fin (fd 6/1024), jamais `degraded`. Mon débit : appels séquentiels, environ 25 par minute, jamais deux simultanés.

## Source officielle utilisée

Légifrance (site web) est derrière une vérification anti-robot : `curl` reçoit 403 « Just a moment... », le navigateur intégré reste bloqué sur la page de vérification, et l'extension Chrome refuse le domaine (« Navigation to this domain is not allowed »). Je ne contourne pas un CAPTCHA. J'ai donc comparé à **l'API officielle Légifrance de la DILA via PISTE** (`POST https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/consult/getArticle`, identifiants `PISTE_CLIENT_ID` du `.env` du dépôt, appels en lecture). C'est le même moteur que le site Légifrance ; elle rend pour chaque LEGIARTI le texte, l'état, les dates et la liste officielle `articleVersions` (toutes les versions de l'article avec leurs dates), ce qui permet de savoir quelle version est en vigueur à une date donnée. Environ 90 appels PISTE. Les URL `legifrance.gouv.fr/...` servies par le site n'ont pas pu être ouvertes : **liens Légifrance INVÉRIFIABLES CONTRE LE SITE LÉGIFRANCE** (leur LEGIARTI et leur date ont été contrôlés contre l'API).

## Synthèse en cinq lignes

1. **FAUX servi, cause unique et systémique** : l'ingestion LEGI ignore toute mise à jour par la DILA d'une version déjà en base (état, date de fin, texte), et crée une ligne fantôme quand la DILA déplace une date d'entrée en vigueur. Résultat mesuré : 8 articles sur 60 testés « à aujourd'hui » sont servis faux : 7 dans une version qui n'est pas celle en vigueur (dont un article mort-né et un article qui n'entrera en vigueur qu'en 2029), 1 avec un texte périmé sous le bon identifiant.
2. **État périmé massif** : 9 025 versions en base portent encore `VIGUEUR_DIFF` alors que leur date d'entrée en vigueur est passée (dont CPC 145 et CJA R811-1, les deux articles du trou de juillet à décembre 2025) ; 11 articles sur 60 ont un état différent de Légifrance.
3. **Panne** : les pages `/loi/` sont inaccessibles (404) pour tout article dont le numéro contient une espace ou un astérisque (LPF L80 B, CGI 4 B, CSP R*…) et pour tout code à sigle accentué (CForêt, C.éduc, CPénit, CCiné), soit de l'ordre de 40 000 versions en vigueur ; le sitemap publie ces URL invalides.
4. **Lenteur** : chaque lecture d'article fait un balayage complet de la table (1,84 M lignes, 9,1 Go) faute d'index utilisable : 1,7 à 1,8 s par article, 8,5 s pour un article inexistant, 27 à 38 s pour `search_decisions_citing`.
5. Ce qui tient : la sélection par date est juste chaque fois que la base est juste (10/10 hors zone fantôme), les abrogés sont annoncés comme tels sur les trois canaux, MCP et REST identiques sur 71 appels appariés, page cohérente avec eux sur les 55 pages servies, aucune erreur 5xx sur les outils de lecture d'article en 48 h.

## MANIFESTE DE COUVERTURE

### Fichiers lus

| Fichier | Lignes lues |
|---|---|
| memory `justicelibre_audit_sept2026.md` | 60-130, 295-409 (sections pertinentes ; reste parcouru par grep) |
| memory `justicelibre_pannes_silencieuses_10sept.md` | 15-130 |
| memory `justicelibre_trous_donnees.md` | grep seulement (contrôle de couverture judiciaire, hors champ) |
| memory `justicelibre_deploy.md` | 31-40, 51-56 |
| `server.py` | 70-95, 1282-1310, 1820-1845, 1960-2125 |
| `sources/legi.py` | 1-264 (entier) |
| `sources/warehouse.py` | 46-240, 349-412 |
| `warehouse/warehouse_server.py` | 160-260, 399-692, 983-1060, 1244-1310 |
| `token_server.py` | 185-330, 633-665, 740-762 ; diff complet contre la prod |
| `ssr.py` | 1005-1135, 1537-1575 |
| `parse_dila_bulk.py` | 278-330 |
| schéma `legi_articles` (prod entrepôt, lecture seule) | `.schema`, `.indexes`, `EXPLAIN QUERY PLAN` |

Déploiement : `md5sum` identiques dépôt/prod pour `server.py`, `ssr.py`, `sources/legi.py`, `sources/warehouse.py`, `warehouse_server.py`. **`token_server.py` diffère** : la prod n'a pas l'aiguillage `JL_SSR_V2` (5 lignes, 690-692 et 759-760 du dépôt). Sans effet sur le rendu actuel (v1 servi), mais la prod n'est pas le dépôt.

### Appels NON TESTÉS ou incomplets

- Site Légifrance (URL servies) : NON TESTÉ, anti-robot (voir plus haut). Contrôle fait par l'API PISTE à la place.
- Paramètre `date=` des pages `/loi/` : NON TESTÉ, la route n'en accepte pas (`token_server.py:752`, `sync_get_law(code, num)` sans date).
- Charge concurrente (rafales) : NON TESTÉ volontairement (consigne de 2 requêtes simultanées au plus sur l'entrepôt fragile). La robustesse est mesurée sur mes appels séquentiels et sur les journaux.
- Statut HTTP par requête côté entrepôt : NON MESURABLE, le journal de `justicelibre-warehouse` n'écrit pas le code de retour ; mesuré côté appelants (prod).
- Précision de `search_decisions_citing` (part de faux positifs dans `total`) : NON MESURÉE ; seuls les 8 premiers résultats de 2 appels ont été lus (tous pertinents).
- Les 9 025 `VIGUEUR_DIFF` périmés et les 1 802 lignes fantômes sont comptés en base ; seuls ceux de l'échantillon ont été confrontés un à un à Légifrance.

### Articles testés (run principal : MCP `get_law_article` + REST `/api/law` + page `/loi/` quand pas de date)

« Officiel » = état et dates du LEGIARTI servi selon l'API Légifrance ; le verdict « mauvaise version » compare le LEGIARTI servi à celui que la liste officielle `articleVersions` donne en vigueur à la date demandée (aujourd'hui = 2026-10-02 quand aucune date).

| # | Code | Art. | Date demandée | Canaux | Servi (LEGIARTI, état, début→fin) | Officiel (API Légifrance) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | CC | 1128 | aucune | MCP, REST, page 200 | LEGIARTI000032040911, VIGUEUR, 2016-10-01→2999-01-01 | VIGUEUR, 2016-10-01→2999-01-01 | titre_section faux |
| 2 | CC | 1128 | 1992-06-15 | MCP, REST | LEGIARTI000006436219, MODIFIE, 1804-03-21→2016-10-01 | MODIFIE, 1804-03-21→2016-10-01 | titre_section faux |
| 3 | CC | 1134 | aucune | MCP, REST, page 200 | LEGIARTI000032041008, VIGUEUR, 2016-10-01→2999-01-01 | VIGUEUR, 2016-10-01→2999-01-01 | CONFORME |
| 4 | CC | 1134 | 2010-01-01 | MCP, REST | LEGIARTI000006436298, MODIFIE, 1804-03-21→2016-10-01 | MODIFIE, 1804-03-21→2016-10-01 | CONFORME |
| 5 | CC | 1240 | aucune | MCP, REST, page 200 | LEGIARTI000032041571, VIGUEUR, 2016-10-01→2999-01-01 | VIGUEUR, 2016-10-01→2999-01-01 | CONFORME |
| 6 | CC | 9 | aucune | MCP, REST, page 200 | LEGIARTI000006419288, VIGUEUR, 1970-07-19→2999-01-01 | VIGUEUR, 1970-07-19→2999-01-01 | CONFORME |
| 7 | CP | 222-33-2-2 | aucune | MCP, REST, page 200 | LEGIARTI000049312743, VIGUEUR, 2024-03-23→2999-01-01 | VIGUEUR, 2024-03-23→2999-01-01 | titre_section faux |
| 8 | CP | 222-33-2-2 | 2015-01-01 | MCP, REST | LEGIARTI000029334247, MODIFIE, 2014-08-06→2018-08-06 | MODIFIE, 2014-08-06→2018-08-06 | titre_section faux |
| 9 | CP | 121-3 | aucune | MCP, REST, page 200 | LEGIARTI000006417208, VIGUEUR, 2000-07-11→2999-01-01 | VIGUEUR, 2000-07-11→2999-01-01 | CONFORME |
| 10 | CPC | 145 | aucune | MCP, REST, page 200 | LEGIARTI000051869339, VIGUEUR_DIFF, 2025-09-01→2999-01-01 | VIGUEUR, 2025-09-01→2999-01-01 | état périmé (VIGUEUR_DIFF au lieu de VIGUEUR) |
| 11 | CPC | 145 | 2025-06-01 | MCP, REST | LEGIARTI000006410268, ABROGE_DIFF, 1976-01-01→2025-09-01 | MODIFIE, 1976-01-01→2025-09-01 | état périmé (ABROGE_DIFF au lieu de MODIFIE) |
| 12 | CPC | 750-1 | aucune | MCP, REST, page 200 | LEGIARTI000047539064, VIGUEUR, 2023-05-13→2999-01-01 | VIGUEUR, 2023-05-13→2999-01-01 | texte : espaces seulement; titre_section faux |
| 13 | CPC | 700 | aucune | MCP, REST, page 200 | LEGIARTI000045268436, VIGUEUR, 2022-02-27→2999-01-01 | VIGUEUR, 2022-02-27→2999-01-01 | CONFORME |
| 14 | CPC | 127 | aucune | MCP, REST, page 200 | LEGIARTI000051928718, VIGUEUR, 2025-09-01→2999-01-01 | VIGUEUR, 2025-09-01→2999-01-01 | titre_section faux |
| 15 | CPP | 85 | aucune | MCP, REST, page 200 | LEGIARTI000038312069, VIGUEUR, 2019-03-25→2999-01-01 | ABROGE_DIFF, 2019-03-25→2029-01-01 | texte : espaces seulement; état périmé (VIGUEUR au lieu de ABROGE_DIFF); dates périmées (officiel 2019-03-25→2029-01-01) |
| 16 | CPP | 40 | 2000-01-01 | MCP, REST | LEGIARTI000006574932, MODIFIE, 1998-06-18→2004-03-10 | MODIFIE, 1998-06-18→2004-03-10 | CONFORME |
| 17 | CT | L1152-1 | aucune | MCP, REST, page 200 | LEGIARTI000006900818, VIGUEUR, 2008-05-01→2999-01-01 | VIGUEUR, 2008-05-01→2999-01-01 | CONFORME |
| 18 | CT | L1235-3 | aucune | MCP, REST, page 200 | LEGIARTI000036762052, VIGUEUR, 2018-04-01→2999-01-01 | VIGUEUR, 2018-04-01→2999-01-01 | texte : espaces seulement |
| 19 | CT | L321-1 | aucune | MCP, REST, page 200 | LEGIARTI000006648602, ABROGE, 2005-01-19→2008-05-01 | ABROGE, 2005-01-19→2008-05-01 | CONFORME (abrogé annoncé comme tel, note) |
| 20 | CT | L1235-3 | 2017-01-01 | MCP, REST | LEGIARTI000006901142, MODIFIE, 2008-05-01→2017-09-24 | MODIFIE, 2008-05-01→2017-09-24 | texte : espaces seulement |
| 21 | CSP | L1111-7 | aucune | MCP, REST, page 200 | LEGIARTI000042685313, VIGUEUR, 2021-11-01→2999-01-01 | ABROGE_DIFF, 2021-11-01→2029-01-01 | texte : espaces seulement; état périmé (VIGUEUR au lieu de ABROGE_DIFF); dates périmées (officiel 2021-11-01→2029-01-01) |
| 22 | CSP | R*1435-28-2 | aucune | MCP, REST, page 404 | LEGIARTI000054494311, VIGUEUR_DIFF, 2026-07-24→2999-01-01 | VIGUEUR, 2026-07-24→2999-01-01 | texte : espaces seulement; état périmé (VIGUEUR_DIFF au lieu de VIGUEUR); page /loi/ 404 |
| 23 | CJA | R811-1 | aucune | MCP, REST, page 200 | LEGIARTI000052286884, VIGUEUR_DIFF, 2025-11-01→2999-01-01 | VIGUEUR, 2025-11-01→2999-01-01 | texte : espaces seulement; état périmé (VIGUEUR_DIFF au lieu de VIGUEUR) |
| 24 | CJA | L521-1 | aucune | MCP, REST, page 200 | LEGIARTI000006449326, VIGUEUR, 2001-01-01→2999-01-01 | VIGUEUR, 2001-01-01→2999-01-01 | CONFORME |
| 25 | CJA | R431-3 | aucune | MCP, REST, page 200 | LEGIARTI000050760054, VIGUEUR, 2025-01-01→2999-01-01 | VIGUEUR, 2025-01-01→2999-01-01 | texte : espaces seulement |
| 26 | CJA | L761-1 | aucune | MCP, REST, page 200 | LEGIARTI000044570095, VIGUEUR, 2021-12-24→2999-01-01 | VIGUEUR, 2021-12-24→2999-01-01 | CONFORME |
| 27 | CJA | R811-1 | 2020-01-01 | MCP, REST | LEGIARTI000038117576, MODIFIE, 2019-02-10→2022-07-02 | MODIFIE, 2019-02-10→2022-07-02 | texte : espaces seulement |
| 28 | CRPA | L311-6 | aucune | MCP, REST, page 200 | LEGIARTI000037269056, VIGUEUR, 2018-08-01→2999-01-01 | VIGUEUR, 2018-08-01→2999-01-01 | texte : espaces seulement |
| 29 | CRPA | L231-1 | aucune | MCP, REST, page 200 | LEGIARTI000031367611, VIGUEUR, 2016-01-01→2999-01-01 | VIGUEUR, 2016-01-01→2999-01-01 | CONFORME |
| 30 | CRPA | L411-2 | aucune | MCP, REST, page 200 | LEGIARTI000031367829, VIGUEUR, 2016-01-01→2999-01-01 | VIGUEUR, 2016-01-01→2999-01-01 | CONFORME |
| 31 | CGCT | L2212-2 | aucune | MCP, REST, page 200 | LEGIARTI000029946370, VIGUEUR, 2014-12-22→2999-01-01 | VIGUEUR, 2014-12-22→2999-01-01 | CONFORME |
| 32 | CGCT | L1612-21 | aucune | MCP, REST, page 200 | LEGIARTI000051731808, VIGUEUR_DIFF, 2026-01-01→2999-01-01 | VIGUEUR, 2026-01-01→2999-01-01 | état périmé (VIGUEUR_DIFF au lieu de VIGUEUR) |
| 33 | CESEDA | L611-1 | aucune | MCP, REST, page 200 | LEGIARTI000042775578, VIGUEUR, 2021-05-01→2999-01-01 | VIGUEUR, 2021-05-01→2999-01-01 | CONFORME |
| 34 | CESEDA | L435-1 | aucune | MCP, REST, page 200 | LEGIARTI000043982311, VIGUEUR, 2021-08-26→2999-01-01 | VIGUEUR, 2021-08-26→2999-01-01 | CONFORME |
| 35 | CSS | L114-17 | aucune | MCP, REST, page 200 | LEGIARTI000054331851, VIGUEUR, 2026-06-27→2999-01-01 | VIGUEUR, 2026-06-27→2999-01-01 | texte : espaces seulement |
| 36 | CSS | R752-18-1 | aucune | MCP, REST, page 200 | LEGIARTI000051829843, VIGUEUR_DIFF, 2025-10-01→2999-01-01 | VIGUEUR, 2025-10-01→2999-01-01 | état périmé (VIGUEUR_DIFF au lieu de VIGUEUR) |
| 37 | CSS | L434-10 | aucune | MCP, REST, page 200 | LEGIARTI000020123584, VIGUEUR, 2009-01-19→2999-01-01 | VIGUEUR, 2009-01-19→2999-01-01 | texte : espaces seulement |
| 38 | CASF | L262-8 | aucune | MCP, REST, page 200 | LEGIARTI000033813647, VIGUEUR, 2017-01-01→2999-01-01 | VIGUEUR, 2017-01-01→2999-01-01 | CONFORME |
| 39 | CASF | L345-2-2 | aucune | MCP, REST, page 200 | LEGIARTI000037670338, VIGUEUR, 2018-11-25→2999-01-01 | VIGUEUR, 2018-11-25→2999-01-01 | CONFORME |
| 40 | COJ | L141-1 | aucune | MCP, REST, page 200 | LEGIARTI000033458641, VIGUEUR, 2016-11-20→2999-01-01 | VIGUEUR, 2016-11-20→2999-01-01 | CONFORME |
| 41 | COJ | L111-3 | aucune | MCP, REST, page 200 | LEGIARTI000006572058, VIGUEUR, 2006-06-09→2999-01-01 | VIGUEUR, 2006-06-09→2999-01-01 | CONFORME |
| 42 | CU | L600-1-2 | aucune | MCP, REST, page 200 | LEGIARTI000037667999, VIGUEUR, 2019-01-01→2999-01-01 | VIGUEUR, 2019-01-01→2999-01-01 | CONFORME |
| 43 | CU | L421-1 | aucune | MCP, REST, page 200 | LEGIARTI000006815663, VIGUEUR, 2007-10-01→2999-01-01 | VIGUEUR, 2007-10-01→2999-01-01 | CONFORME |
| 44 | CGI | 1754 | aucune | MCP, REST, page 200 | LEGIARTI000053189001, VIGUEUR_DIFF, 2026-09-01→2999-01-01 | VIGUEUR_DIFF, 2027-01-01→2999-01-01 | FAUX : mauvaise version (attendu LEGIARTI000053881346); dates périmées (officiel 2027-01-01→2999-01-01) |
| 45 | CGI | 279 | aucune | MCP, REST, page 200 | LEGIARTI000048827223, VIGUEUR, 2023-12-31→2999-01-01 | MODIFIE, 2023-12-31→2026-02-21 | FAUX : mauvaise version (attendu LEGIARTI000053562872); état périmé (VIGUEUR au lieu de MODIFIE); dates périmées (officiel 2023-12-31→2026-02-21) |
| 46 | CGI | 4 B | aucune | MCP, REST, page 404 | LEGIARTI000051202565, VIGUEUR, 2025-02-16→2999-01-01 | VIGUEUR, 2025-02-16→2999-01-01 | page /loi/ 404 |
| 47 | CGI | 200 | aucune | MCP, REST, page 200 | LEGIARTI000053154489, VIGUEUR_DIFF, 2026-09-01→2999-01-01 | VIGUEUR_DIFF, 2027-01-01→2999-01-01 | FAUX : mauvaise version (attendu LEGIARTI000053543932); dates périmées (officiel 2027-01-01→2999-01-01) |
| 48 | C.com | L631-1 | aucune | MCP, REST, page 200 | LEGIARTI000045178110, VIGUEUR, 2022-05-15→2999-01-01 | VIGUEUR, 2022-05-15→2999-01-01 | texte : espaces seulement |
| 49 | C.com | L441-10 | aucune | MCP, REST, page 200 | LEGIARTI000053151445, VIGUEUR_DIFF, 2026-09-01→2999-01-01 | MODIFIE_MORT_NE, 2027-01-01→2026-07-29 | FAUX : mauvaise version (attendu LEGIARTI000038414392); état périmé (VIGUEUR_DIFF au lieu de MODIFIE_MORT_NE); dates périmées (officiel 2027-01-01→2026-07-29) |
| 50 | C.com | L625-2 | aucune | MCP, REST, page 200 | LEGIARTI000019984048, VIGUEUR, 2009-02-15→2999-01-01 | VIGUEUR, 2009-02-15→2999-01-01 | FAUX : texte différent sous le même LEGIARTI |
| 51 | CCH | L441-1 | aucune | MCP, REST, page 200 | LEGIARTI000054354341, VIGUEUR, 2026-07-01→2999-01-01 | VIGUEUR, 2026-07-01→2999-01-01 | texte : espaces seulement |
| 52 | CCH | L633-2 | aucune | MCP, REST, page 200 | LEGIARTI000028807441, VIGUEUR, 2014-03-27→2999-01-01 | VIGUEUR, 2014-03-27→2999-01-01 | CONFORME |
| 53 | LPF | L80 B | aucune | MCP, REST, page 404 | LEGIARTI000053189313, VIGUEUR_DIFF, 2026-09-01→2999-01-01 | MODIFIE_MORT_NE, 2027-01-01→2026-07-29 | FAUX : mauvaise version (attendu LEGIARTI000054674686); état périmé (VIGUEUR_DIFF au lieu de MODIFIE_MORT_NE); dates périmées (officiel 2027-01-01→2026-07-29); page /loi/ 404 |
| 54 | LPF | L16 B | aucune | MCP, REST, page 404 | LEGIARTI000053189711, VIGUEUR_DIFF, 2026-09-01→2029-01-01 | VIGUEUR_DIFF, 2027-01-01→2029-01-01 | FAUX : mauvaise version (attendu LEGIARTI000054337102); dates périmées (officiel 2027-01-01→2029-01-01); page /loi/ 404 |
| 55 | LPF | L169 | aucune | MCP, REST, page 200 | LEGIARTI000054358875, VIGUEUR, 2026-07-01→2999-01-01 | VIGUEUR, 2026-07-01→2999-01-01 | texte : espaces seulement |
| 56 | CPCEx | L111-3 | aucune | MCP, REST, page 200 | LEGIARTI000053936502, VIGUEUR, 2026-04-25→2999-01-01 | VIGUEUR, 2026-04-25→2999-01-01 | CONFORME |
| 57 | CG3P | L2111-1 | aucune | MCP, REST, page 200 | LEGIARTI000006361178, VIGUEUR, 2006-07-01→2999-01-01 | VIGUEUR, 2006-07-01→2999-01-01 | CONFORME |
| 58 | CForêt | L111-1 | aucune | MCP, REST, page 404 | LEGIARTI000025245722, VIGUEUR, 2012-07-01→2999-01-01 | VIGUEUR, 2012-07-01→2999-01-01 | page /loi/ 404 |
| 59 | CONST | 61-1 | aucune | MCP, REST, page 200 | LEGIARTI000019241077, VIGUEUR, 2008-07-25→2999-01-01 | VIGUEUR, 2008-07-25→2999-01-01 | CONFORME |
| 60 | LIL | 1 | aucune | MCP, REST, page 200 | LEGIARTI000037822962, VIGUEUR, 2019-06-01→2999-01-01 | VIGUEUR, 2019-06-01→2999-01-01 | CONFORME |
| 61 | LIL | 1 | 2010-01-01 | MCP, REST | LEGIARTI000006528059, MODIFIE, 1978-07-23→2016-10-09 | MODIFIE, 1978-07-23→2016-10-09 | CONFORME |
| 62 | CSI | L625-6 | aucune | MCP, REST, page 200 | LEGIARTI000047555835, VIGUEUR, 2025-03-01→2999-01-01 | VIGUEUR, 2025-03-01→2999-01-01 | texte : espaces seulement |
| 63 | CT | L1225-4-1 | aucune | MCP, REST, page 200 | LEGIARTI000033022611, VIGUEUR, 2016-08-10→2999-01-01 | VIGUEUR, 2016-08-10→2999-01-01 | CONFORME |
| 64 | CC | 515-14 | aucune | MCP, REST, page 200 | LEGIARTI000030250342, VIGUEUR, 2015-02-18→2999-01-01 | VIGUEUR, 2015-02-18→2999-01-01 | CONFORME |
| 65 | CP | 131-26-2 | aucune | MCP, REST, page 200 | LEGIARTI000051741809, VIGUEUR, 2025-06-15→2999-01-01 | ABROGE_DIFF, 2025-06-15→2029-01-01 | texte : espaces seulement; état périmé (VIGUEUR au lieu de ABROGE_DIFF); dates périmées (officiel 2025-06-15→2029-01-01) |
| 66 | CJA | R222-1 | aucune | MCP, REST, page 200 | LEGIARTI000048830877, VIGUEUR, 2023-12-31→2999-01-01 | VIGUEUR, 2023-12-31→2999-01-01 | CONFORME |
| 67 | CPC | 1528-3 | aucune | MCP, REST, page 200 | LEGIARTI000051930598, VIGUEUR, 2025-09-01→2999-01-01 | VIGUEUR, 2025-09-01→2999-01-01 | titre_section faux |
| 68 | CGI | 1496 ter | aucune | MCP, REST, page 404 | LEGIARTI000041403640, VIGUEUR_DIFF, 2026-01-01→2999-01-01 | VIGUEUR_DIFF, 2029-01-01→2999-01-01 | FAUX : article pas en vigueur avant 2029 servi comme version courante; dates périmées (officiel 2029-01-01→2999-01-01); page /loi/ 404 |
| 69 | CP1810 | 1 | aucune | MCP, REST, page 200, REST 200 | MCP : erreur « Code inconnu » | sans objet | PANNE de canal (REST et page servent, MCP refuse) |
| 70 | CPC | 145 | 2025-09-01 | MCP, REST | LEGIARTI000051869339, VIGUEUR_DIFF, 2025-09-01→2999-01-01 | VIGUEUR, 2025-09-01→2999-01-01 | état périmé (VIGUEUR_DIFF au lieu de VIGUEUR) |
| 71 | CPC | 145 | 2025-08-31 | MCP, REST | LEGIARTI000006410268, ABROGE_DIFF, 1976-01-01→2025-09-01 | MODIFIE, 1976-01-01→2025-09-01 | état périmé (ABROGE_DIFF au lieu de MODIFIE) |

### Tests complémentaires (dates ciblées, autres outils, erreurs)

| Requête | Canal | Résultat | Verdict |
|---|---|---|---|
| LPF L80 B, date 2026-09-15 | MCP | 053189313 VIGUEUR_DIFF 2026-09-01 | FAUX (attendu 054674686, en vigueur depuis 2026-07-29) |
| LPF L80 B, date 2026-03-15 | MCP | 053544570 | conforme (dates de la ligne périmées : base 2026-02-21, officiel 2026-01-01) |
| CGI 279, date 2026-02-25 | MCP | 053562872 | FAUX (attendu 053574745) |
| CGI 279, date 2026-05-01 | MCP | 053562872 | conforme (état périmé) |
| CGI 1754, date 2026-09-15 | MCP | 053189001 | FAUX (attendu 053881346) |
| C.com L441-10, date 2026-09-15 | MCP | 053151445 | FAUX (attendu 038414392) |
| CGI 200, date 2027-06-01 | MCP | 053154489 2027-01-01 | conforme |
| CRPA L311-6, date 1990-01-01 | MCP | version 2018 + note « Aucune version en vigueur à 1990-01-01. Version courante affichée. » | conforme (le CRPA n'existait pas) |
| loi 91-647 art. 7, 2 ; 7 au 2015-01-01 (LEGITEXT000006077779) | MCP + REST + page `/loi/91-647/7` | 041473317 / 006491176 / 006491193 | conformes, texte identique, lien `/loda/` |
| loi 2000-321 art. 1, 21 ; 21 au 2005-01-01 (LEGITEXT000005629288) | MCP + REST + page `/loi/2000-321/21` | 006529184 / 028183968 ABROGE + bandeau rouge / 006529211 | conformes |
| loi 78-17 (LIL) art. 1 ; 1 au 2010-01-01 | MCP + REST + page | 037822962 / 006528059 | conformes |
| `get_law_versions` CPC 145, LPF L80 B, CGI 279, C.com L625-2, CC 1134, CJA R811-1 | MCP + REST | identiques entre canaux ; fantômes présents (L80 B : 053189313 trois fois ; CGI 279 : 053562872 deux fois, 048827223 ouverte jusqu'en 2999) | FAUX dans la frise |
| `get_law_versions` code = JORFTEXT000000886460 | MCP | « Code inconnu » | PANNE (le même identifiant est accepté par `get_law_article`) |
| `/api/law/versions?code=ZZZ&num=1` | REST | 200 `{"versions": []}` | erreur silencieuse |
| `get_law_article` ZZZ / cc (minuscules) | MCP | « Code inconnu » explicite | conforme |
| `/api/law?code=ZZZ` / `code=cc` | REST | 404 « Article introuvable » | message trompeur (accuse le numéro, pas le code) |
| `get_law_article` CC 99999 | MCP | erreur « introuvable » en 8,46 s | conforme, lent |
| `get_law_article` CJA « R. 811-1 » | MCP + REST | R811-1 servi | conforme |
| `get_law_article` CC 1128 date 2016-13-45 | MCP | refus explicite | conforme |
| `/api/law?code=CC&num=1128&date=2016-13-45` | REST | **200, version courante, aucune note** | FAUX possible (défaut corrigé au MCP le 4/09, pas au REST) |
| `/api/law` date 15/06/1992 | REST | 400 | conforme |
| `/api/law/batch` date 2016-13-45 | REST | 200, version courante, aucune note | même défaut |
| `/api/law/batch` CPC 145 + ZZZ + LPF L80 B + CP1810, date 2025-06-01 | REST | 145 = 006410268 (juste, état ABROGE_DIFF au lieu de MODIFIE) ; ZZZ `found:false` ; L80 B = 051215760 (juste) ; CP1810 servi | conforme hors état |
| `get_law_article` CP1810 1 | MCP | « Code inconnu » | PANNE de canal : REST et page `/loi/CP1810/1` le servent (29 sigles historiques de l'entrepôt absents de `SUPPORTED_CODES`) |
| `resolve_law_number` 91-647, 2000-321, 78-17, 2016-1547, 68-1250, 79-587, 2005-102, 99-9999 | MCP + REST | LEGITEXT corrects, titres corrects ; 99-9999 erreur explicite | conformes, 3,2 à 3,5 s chacun |
| `search_legi` « mesures d'instruction motif légitime avant tout procès » | MCP | 1er résultat = CPC 145 **version 1976** (006410268, ABROGE_DIFF) ; la version en vigueur n'est pas dans les 5 premiers | trompeur |
| `/api/search?sources=legi` même requête | REST | idem, 1er = 006410268 | trompeur |
| `search_legi` code=CForet | MCP | erreur explicite | conforme |
| `search_legi` code=COJ « déni de justice » | MCP | L141-3 COJ | conforme |
| `search_legi` « règlement (UE) 2023/988 » code=C.cons | MCP | « Error executing tool search_legi: entrepôt de données en erreur (code HTTP 500) » | PANNE (52 fois en 48 h dans les journaux) |
| `search_decisions_citing` CPC 145 / CJA L521-1 / ZZZ | MCP | 71 882 / 10 081 résultats en **38,2 s / 27,5 s** ; ZZZ erreur explicite | lenteur |
| Pages `/loi/LPF/L80%20B`, `/loi/CGI/4%20B`, `/loi/CSP/R*1435-28-2`, `/loi/CFor%C3%AAt/L111-1`, `/loi/C.%C3%A9duc/L131-1`, `/loi/CP%C3%A9nit/L1` | page | 404 | PANNE |
| `/loi/LPF/L80B`, `/loi/CGI/4B`, `/loi/LEGITEXT000025244092/L111-1` | page | 200 | contournements qui marchent |
| `/loi/CC/99999` | page | 404 en 8,7 s | lent |

---

## DÉFAUTS, par gravité

### F1. FAUX SERVI : versions fantômes et mises à jour DILA jetées à l'ingestion (CRITIQUE)

**Cause dans le code** : `parse_dila_bulk.py:296-305`. L'UPSERT des articles LEGI est `ON CONFLICT(legiarti, date_debut) DO UPDATE SET legitext, jorftext, hierarchie, liens, ancien_id, type_article`. Le commentaire l. 296 le dit : « texte, num, titre_text, etat et nota gardent leur valeur ». Deux conséquences :

1. Quand la DILA republie une version existante avec un nouvel état, une nouvelle date de fin ou un texte corrigé, **rien n'est mis à jour** : `etat`, `date_fin`, `texte`, `nota` restent ceux de la première ingestion.
2. Quand la DILA **déplace la date d'entrée en vigueur** d'une version (report par une loi ultérieure), la clé `(legiarti, date_debut)` change : une **nouvelle ligne** est insérée et l'ancienne reste. Mesuré en base : **2 764 LEGIARTI ont plusieurs lignes (5 650 lignes)** ; **1 802 lignes fantômes couvrent la date du jour** (CGI 63, LPF 33, CIBS 60, plus de 100 dans certains textes non codifiés).

Puis `warehouse_server.py:483-497` (« Strategy 1 ») choisit, parmi les lignes dont l'intervalle couvre la date, celle de `date_debut` la plus récente, sans regarder l'état ni l'existence d'un doublon du même LEGIARTI : la ligne fantôme gagne.

**Reproductions** (toutes identiques sur MCP, REST et page) :

a) `get_law_article(code="LPF", num="L80 B")` (rescrit fiscal, garantie contre les changements de doctrine).
Obtenu : LEGIARTI000053189313, `etat: VIGUEUR_DIFF`, `date_debut: 2026-09-01`, sans note.
Attendu (API Légifrance, `articleVersions`) : LEGIARTI000054674686, VIGUEUR depuis le 2026-07-29 ; le 053189313 est `MODIFIE_MORT_NE` (il n'est jamais entré en vigueur). Le texte servi rétablit des cas de garantie que la version en vigueur a abrogés. Servi : « 11° Pour les impositions dont le contrôle est régi par les procédures des contributions indirectes, lorsque, dans le cadre d'un contrôle ou d'une enquête effectués par l'administration et sur demande écrite du redevable présentée conformément au 1°, avant la notification de l'information ou de la proposition de taxation mentionnées à l'article L. 80 M, l'administration a formellement pris position sur un point qu'elle a examiné au cours du contrôle ou de l'enquête ; » `LU AU TEXTE` (réponse justicelibre). Officiel : « 11° (Abrogé) ; » `LU AU TEXTE` (API Légifrance). NB : c'est un item d'énumération, l'article entier forme une seule phrase ; je cite l'item complet de son numéro à son point-virgule, sans coupe.

b) `get_law_article(code="CGI", num="279")` (TVA à taux intermédiaire).
Obtenu : LEGIARTI000048827223, `VIGUEUR`, `2023-12-31 → 2999-01-01`. Attendu : LEGIARTI000053562872 (en vigueur du 2026-03-01 au 2027-01-01) ; l'officiel donne 048827223 `MODIFIE` avec fin au 2026-02-21. En base, les deux lignes de 053562872 finissent au 2026-09-01 (date périmée ; officiel 2027-01-01), d'où le retour à la version 2023. Servi : « b septies. S'ils sont réalisés jusqu'au 31 décembre 2025, les travaux sylvicoles et d'exploitation forestière réalisés au profit d'exploitants agricoles, y compris les travaux d'entretien des sentiers forestiers, ainsi que les travaux de prévention des incendies de forêt menés par des associations syndicales autorisées ayant pour objet la réalisation de ces travaux ; » `LU AU TEXTE`. Officiel : « b septies. S'ils sont réalisés jusqu'au 31 décembre 2028, les travaux sylvicoles et d'exploitation forestière réalisés au profit d'exploitants agricoles, y compris les travaux d'entretien des sentiers forestiers, ainsi que les travaux de prévention des incendies de forêt menés par des associations syndicales autorisées ayant pour objet la réalisation de ces travaux ; » `LU AU TEXTE`. Le servi contient aussi un « h. » (déchets ménagers) que l'officiel donne « h. (Abrogé) ; ».

c) `get_law_article(code="C.com", num="L441-10")` (délais de paiement). Obtenu : 053151445 `VIGUEUR_DIFF` du 2026-09-01. Attendu : 038414392 (en vigueur, `ABROGE_DIFF` au 2027-01-01) ; 053151445 est officiellement `MODIFIE_MORT_NE`. Le texte servi renvoie à « l'article L. 216-42 du code des impositions… » au lieu de « au sens du 3 du I de l'article 289 du code général des impôts » (rapprochement par différence, `LU AU TEXTE` des deux côtés, extraits trop longs pour une citation en phrase entière ici : voir reproduction).

d) `get_law_article(code="CGI", num="1754")`, `(CGI, 200)`, `(LPF, L16 B)` : même mécanisme, version « 2026-09-01 » servie alors que la DILA a reporté son entrée en vigueur au 2027-01-01 ; attendus respectivement 053881346, 053543932, 054337102. CGI 200 (réduction d'impôt pour dons) : le servi renvoie aux soins « mentionnés au 3° de l'article L. 213-96 », l'officiel aux soins « mentionnés au 1° du 4 de l'article 261 » ; CGI 1754 : le servi vise les « taxes sur les biens et services », l'officiel les « taxes sur le chiffre d'affaires ».

e) `get_law_article(code="CGI", num="1496 ter")` sans date : servi 041403640 `VIGUEUR_DIFF` « depuis le 2026-01-01 », sans note. Officiel : une seule version, qui n'entre en vigueur que le **2029-01-01**. Un article qui n'est pas encore en vigueur est servi comme droit courant. (La bonne ligne 2029 est en base, à côté de la fantôme.)

f) **Texte périmé sous le bon identifiant** : `get_law_article(code="C.com", num="L625-2")` → 019984048, juste en identifiant, état et dates, mais servi : « Il est tenu à l'obligation de discrétion mentionnée à l'article L. 432-7 du code du travail. » `LU AU TEXTE`. Officiel : « Il est tenu à l'obligation de discrétion mentionnée aux articles L. 2325-5 et L. 2143-21 du code du travail . » `LU AU TEXTE` (espace avant le point telle que dans la source). L'article L. 432-7 visé n'existe plus depuis la recodification de 2008. Ce cas est invisible pour tout contrôle d'identifiant ou de date : seul le texte diffère.

g) Dates demandées dans la zone fantôme : `get_law_article(LPF, L80 B, date=2026-09-15)`, `(CGI, 1754, 2026-09-15)`, `(C.com, L441-10, 2026-09-15)`, `(CGI, 279, 2026-02-25)` : 4 FAUX sur 6 appels datés ciblés.

**Le lien « Source officielle »** pointe vers le LEGIARTI fantôme avec sa date fantôme (ex. `https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000053151445/2026-09-01`) : l'utilisateur qui vérifie ne tombe pas sur la même rédaction que celle servie (lien non ouvert : INVÉRIFIABLE CONTRE LÉGIFRANCE).

**Pourquoi le correctif du 29/08 (rattrapage du trou juillet-décembre 2025) ne l'a pas vu** : il a rejoué les deltas, donc inséré les versions nouvelles, mais les deltas qui MODIFIENT une version déjà connue sont passés par le même UPSERT qui les jette.

### F2. FAUX (état et dates) : états et fins de validité figés à la première ingestion (GRAVE)

Même cause (F1, `parse_dila_bulk.py:296-305`). Mesuré en base :
- **9 025 versions `VIGUEUR_DIFF` dont la date d'entrée en vigueur est passée** (CDouanes 1 439, CGFP 548, CIBS 507, CGCT 321, CSS 213…), dont CPC 145 (« depuis le 1er septembre 2025 ») et CJA R811-1, les deux articles du trou 2025 que la mémoire signalait. Le texte servi pour ces deux-là est le bon (`texte` identique à l'officiel), mais l'état `VIGUEUR_DIFF` dit « entrée en vigueur différée » à un client qui le lit.
- 17 versions `VIGUEUR` dont la date de fin est passée ; 37 `VIGUEUR` dont le début est futur.
- Échantillon : 11 articles sur 60 ont un état différent de l'officiel et 10 des dates différentes. Exemples : CPP 85 (plainte avec constitution de partie civile), CSP L1111-7 (accès au dossier médical), CP 131-26-2 servis `VIGUEUR … → 2999-01-01` alors que l'officiel les donne `ABROGE_DIFF` au **2029-01-01**. Un client qui demande « cet article est-il appelé à disparaître ? » reçoit « non ».
- CPC 145 au 2025-06-01 : servi `ABROGE_DIFF`, officiel `MODIFIE` (l'ancienne rédaction a été modifiée, pas abrogée).

Reproduction : `GET https://justicelibre.org/api/law?code=CPC&num=145` → `"etat": "VIGUEUR_DIFF"` ; attendu `VIGUEUR` (API Légifrance, LEGIARTI000051869339).

Sur la page `/loi/`, la phrase d'en-tête est juste (« Article en vigueur depuis le 1 septembre 2025. », `ssr.py:1093` range `VIGUEUR_DIFF` avec `vigueur`) mais le tableau affiche en dessous « État : VIGUEUR_DIFF » brut (`ssr.py:1134`) : la page se contredit.

### F3. PANNE : pages `/loi/` en 404 pour les numéros à espace ou astérisque et les sigles accentués (GRAVE)

Reproduction : `GET https://justicelibre.org/loi/LPF/L80%20B` → 404 ; idem `/loi/CGI/4%20B`, `/loi/CSP/R*1435-28-2`, `/loi/CFor%C3%AAt/L111-1`, `/loi/C.%C3%A9duc/L131-1`, `/loi/CP%C3%A9nit/L1`. Attendu : la page de l'article (MCP et REST le servent).
Cause : `token_server.py:225`, `re.match(r"^/loi/([\w.\-]{1,20})/([A-Z]?[\w.\-]{1,40})$", parsed.path)` appliqué au chemin **non décodé** : `%`, l'espace et `*` ne sont pas dans la classe. Le sitemap (`ssr.py:1565`) publie pourtant `/loi/{code}/{num}` brut, espaces et accents compris. Ampleur en base : 28 664 versions en vigueur ou différées à numéro avec espace ou `*`, 11 308 dans les 4 codes à sigle accentué. Contournement constaté : `/loi/LPF/L80B` et `/loi/CGI/4B` répondent 200. Le défaut « articles à espace » de la mémoire (corrigé côté entrepôt le 23/08) persiste donc côté pages.

### F4. FAUX possible : `/api/law` et `/api/law/batch` acceptent une date hors calendrier (MOYEN)

Reproduction : `GET https://justicelibre.org/api/law?code=CC&num=1128&date=2016-13-45` → 200, version 2016, **aucune note**. Même chose en `POST /api/law/batch` avec `"date": "2016-13-45"`. Attendu : 400, comme le MCP (`get_law_article` répond « date='2016-13-45' n'est pas une date du calendrier au format ISO… »). Cause : `token_server.py:301` et `:651` ne vérifient que le gabarit `^\d{4}-\d{2}-\d{2}$`, pas le calendrier ; le correctif du 4/09 (`_check_dates`, `date.fromisoformat`) n'a été porté qu'au MCP.

### F5. Recherche : l'ancienne rédaction remonte en tête (MOYEN)

Reproduction : `search_legi(query="mesures d'instruction motif légitime avant tout procès", limit=5)` et `GET /api/search?q=motif légitime mesures d'instruction&sources=legi` → 1er résultat CPC 145 **LEGIARTI000006410268, rédaction de 1976**, `etat: ABROGE_DIFF` ; la rédaction en vigueur depuis le 1er septembre 2025 (051869339) n'apparaît pas dans les 5 premiers. Avec `code=`, des doublons de versions sortent (« R*114 A-4 » deux fois pour LPF, « 1599 quinquies » deux fois pour CGI). Un client qui cite l'extrait cite le texte de 1976. Cause probable : `fts_search` (`warehouse_server.py:760` et suiv.) indexe toutes les versions sans privilégier celle en vigueur, et la dédup par texte-parent garde « le mieux classé » quelle que soit sa version (non lu en détail : INVÉRIFIABLE dans ce rapport).

### F6. PANNE : `search_legi` en 500 sur des requêtes avec parenthèses ou groupes OR (MOYEN)

Journaux prod 48 h : **52 réponses 500** de `/v1/search/legi` (sur environ 1 150, 4,5 %), plus 60 sur `/v1/search/jade` et 8 sur `/v1/search/jorf`. Reproduction : `search_legi(query="règlement (UE) 2023/988", code="C.cons")` → « Error executing tool search_legi: entrepôt de données en erreur (code HTTP 500) sur /v1/search/legi ». Requêtes réelles en échec : « rétention administratif (risque OR "risque couvert") de torture article 3 CESEDA », « prescription loyers échus échéance (bail OR "droit de reprise" OR … ». Cause probable : `_fts_query` (`warehouse_server.py:693-758`) laisse passer une syntaxe FTS5 invalide (parenthèse dans un mot comme « (UE) », ou mélange de groupes du thésaurus) ; non lu ligne à ligne.

### F7. Incohérences de canal sur les codes (FAIBLE à MOYEN)

- `get_law_versions` (MCP) refuse un LEGITEXT/JORFTEXT (« Code inconnu: 'JORFTEXT000000886460' ») alors que `get_law_article` l'accepte et que la doc de `resolve_law_number` invite à s'en servir. Cause : `sources/legi.py:243` (`is_supported` seul, sans la branche LEGITEXT/JORFTEXT de `get_article`).
- `GET /api/law/versions?code=ZZZ&num=1` → **200 `{"versions": []}`** : code inconnu converti en « aucune version », exactement le faux négatif silencieux que le défaut L80 B du 23/08 avait produit. Cause : l'entrepôt répond 200 vide (`warehouse_server.py:1047-1053`) et `sources/warehouse.py:394-409` ne bascule qu'en cas de 404.
- `/api/law?code=ZZZ` ou `code=cc` → 404 « Article introuvable : ZZZ 1. » : le message accuse le numéro alors que c'est le sigle (le MCP, lui, dit « Code inconnu »).
- 29 sigles historiques (CP1810, CPC1807, CTACAA, CNat…) servis par REST et par les pages mais refusés par le MCP (« Code inconnu: 'CP1810' ») : `CODE_TO_LEGITEXT` de l'entrepôt en a 108, `SUPPORTED_CODES` 79 (`sources/legi.py:16-111`).

### F8. LENTEUR : balayage complet de la table à chaque article (MOYEN, risque de saturation)

`EXPLAIN QUERY PLAN` de la requête de `law_at_date` : `SCAN legi_articles` + `USE TEMP B-TREE FOR ORDER BY`. En direct sur l'entrepôt : 1,55 s pour CC 1240. Cause : `_legi_key` (`warehouse_server.py:593-600`) produit `(legitext = ? OR jorftext = ?)` ; `jorftext` n'a pas d'index et `num` n'est indexé qu'en second dans `idx_art_num(titre_text, num)` : aucun index n'est utilisable. Conséquences mesurées (mes 259 appels) :
- `get_law_article` médiane 1,77 s, p90 1,91 s, max 8,46 s (article inexistant : 3 stratégies × 2 essais = 6 balayages, `sources/warehouse.py:158-170` réessaie avec le LEGITEXT).
- `/api/law` médiane 1,73 s, max 7,10 s ; page `/loi/` médiane 1,83 s, max 4,44 s ; `/api/law/batch` 3,3 à 7,4 s pour 2 à 4 articles.
- `resolve_law_number` 3,2 à 3,5 s ; pages `/loi/<numéro de loi>/<art>` 5,1 s.
- `search_decisions_citing` **38,2 s** (CPC 145) et **27,5 s** (CJA L521-1).
Chaque page `/decision/` préchauffe jusqu'à 16 articles (mémoire du 17/09) : 16 balayages de 9 Go par page. C'est le scénario de saturation du 17/09. Journaux 48 h : 17 069 appels `/v1/law` depuis le site et 11 617 depuis le MCP ; un robot lit en continu `/v1/law?code=JORFTEXT000036339197&num=41, 42, 43…` toutes les 2 à 3 s.

### F9. `titre_section` faux sur 7 articles sur 60 (FAIBLE, mais contredit la documentation)

Exemples : CC 1128 servi « Section 2 : De la capacité des parties contractantes. » (intitulé d'avant 2016), officiel « Section 2 : La validité du contrat » ; CC 1128 au 1992-06-15 servi « Section 3 : De l'objet et de la matière des contrats. », officiel « Section 3 : La forme du contrat » (l'API renvoie la section de la version courante, comparaison à nuancer pour les dates passées) ; CP 222-33-2-2 « Section 3 bis » contre « Section 5 » ; CPC 127 « Titre VI : La conciliation. » contre « Titre VI : LES CONVENTIONS RELATIVES À LA MISE EN ÉTAT » ; CPC 750-1 ; CPC 1528-3. Cause non établie : la colonne `hierarchie` est bien réécrite par l'UPSERT (`parse_dila_bulk.py:302-304`), mais certaines lignes portent une hiérarchie antérieure à la réforme du texte.

### F10. Cosmétique

- Note fausse quand aucune date n'est demandée : CT L321-1 sans date → « Article non trouvé à la date demandée ; version la plus récente retournée. » (`warehouse_server.py:526`). Le bandeau rouge « Article abrogé » est, lui, juste.
- `resolve_law_number` rend `source_url` en `/codes/texte_lc/LEGITEXT…` pour des lois non codifiées (91-647, 2000-321, 78-17) ; les articles des mêmes lois sont liés en `/loda/`. INVÉRIFIABLE CONTRE LÉGIFRANCE (redirection possible).
- Texte : sur 22 articles, des espaces manquent par rapport à Légifrance aux jonctions d'alinéas (aucun mot changé) ; pas une erreur de fond.
- Dérive de déploiement `token_server.py` (voir plus haut).

---

## PARAPHRASES relevées dans les réponses du site

| Où | Phrase du site (sans guillemets de source) | Confrontation |
|---|---|---|
| docstring `get_law_article` (`server.py:2062`) et `search_legi` (`server.py:1836-1838`) | `titre_section` « mesuré juste sur 30 articles de 30 codes le 13 septembre 2026 » | Mesuré ici : 7 faux sur 60. L'affirmation n'est plus vraie. |
| docstring `get_law_article` | « Plus un champ `note` si la version retournée n'est pas celle demandée. » | Faux pour les fantômes (F1) : mauvaise version, aucune note. |
| docstring `get_law_article` | `etat` « (VIGUEUR/MODIFIE/ABROGE) » | Le service rend aussi `VIGUEUR_DIFF`, `ABROGE_DIFF`, `MODIFIE_MORT_NE`, etc., sans les définir. |
| instructions MCP (`server.py:77`) | « version en vigueur À LA DATE donnée » | Vrai seulement hors zone fantôme (4 FAUX sur 6 dates ciblées). |
| docstring `resolve_law_number` (`server.py:1293-1294`) | « `resolve_law_number("68-1250")` → … (JORFTEXT000000878035) » | Le service rend LEGITEXT000006068317 (titre « Loi n°68-1250 du 31 décembre 1968 ») ; l'exemple annonce un autre identifiant. |
| docstring `resolve_law_number` | « `resolve_law_number("2000-321")` → loi droits citoyens face à l'admin » | Juste (LEGITEXT000005629288, « LOI n° 2000-321 du 12 avril 2000 »). |
| docstring `get_law_versions` | « code : code court (voir get_law_article …) » | `get_law_article` accepte aussi LEGITEXT/JORFTEXT ; `get_law_versions` les refuse (F7). |
| `sources/legi.py:6` (interne) | « Les 22 codes supportés… » | 79 sigles. Interne, non servi. |
| note de l'entrepôt (`warehouse_server.py:526`) | « Article non trouvé à la date demandée » | Rendue même sans date demandée (F10). |
| docstring `search_legi` | « Source : bulk LEGI DILA (3,6 Go avec versions historiques) » | La base fait 9,1 Go aujourd'hui. Sans conséquence juridique. |

Aucune citation de texte de loi n'a été trouvée dans ces descriptions (pas de contenu normatif attribué à un article sans guillemets), hormis les exemples d'articles ci-dessus, qui sont exacts sur leur objet (CC 1128 en 1992 : version napoléonienne servie, vérifié).

---

## CE QUI MARCHE (mesuré)

- **Sélection par date** : 10 appels datés hors zone fantôme, 10 versions conformes à `articleVersions` officiel (CC 1128 en 1992, CC 1134 en 2010, CP 222-33-2-2 en 2015, CPP 40 en 2000, CT L1235-3 en 2017, CJA R811-1 en 2020, LIL 1 en 2010, CPC 145 la veille et le jour de la bascule du 1er septembre 2025, loi 91-647 art. 7 en 2015, loi 2000-321 art. 21 en 2005). Bascule au jour près juste.
- **Texte** : sur les 63 appels où la version servie est la bonne, 62 textes identiques à l'officiel aux espaces près ; 1 périmé (C.com L625-2, F1 f).
- **Abrogés** : CT L321-1 et loi 2000-321 art. 21 annoncés « ABROGE » au MCP et au REST, et en rouge sur la page (« ⚠ Article abrogé — version en vigueur du … au …. Ce texte ne s'applique plus. »). Le défaut du 10/09 (abrogés affichés « en vigueur ») ne s'est pas reproduit.
- **Cohérence des canaux** : MCP et REST identiques (LEGIARTI, texte, état, dates, note) sur 71 appels appariés ; page cohérente avec eux sur les 55 pages servies (même LEGIARTI dans le lien, en-tête conforme à l'état).
- **Numéros recyclés** : CC 1134 (2016 contre 1804) correctement distingués par date.
- **Suffixes** : CT L1225-4-1, CC 515-14, CP 131-26-2, CPC 1528-3, CASF L345-2-2, CU L600-1-2 servis ; « R. 811-1 » normalisé ; LPF L80 B et L16 B trouvés par MCP/REST (mais version fausse, F1) ; CSP R*1435-28-2 servi (état périmé).
- **Sigles rares** : COJ, CG3P, CForêt, CPCEx, CONST, LIL servis au MCP et au REST ; mapping sigle → LEGITEXT des 79 sigles vérifié en base, 79/79 justes.
- **Codes inconnus au MCP** : erreur explicite pour `get_law_article`, `get_law_versions`, `search_legi`, `search_decisions_citing`.
- **Lois hors code** : `resolve_law_number` juste sur 7/7 numéros réels, erreur explicite sur un numéro inexistant ; pages `/loi/91-647/7`, `/loi/2000-321/21`, `/loi/78-17/1` servies.
- **Robustesse** : 0 réponse 5xx sur mes 259 appels ; journaux prod 48 h : `/v1/law` 11 262 réponses 200 et 355 404 côté MCP, 17 069 / 1 737 côté site, **aucun** ReadTimeout, ConnectTimeout, « unable to open database file » ni « Too many open files » ; 29 BrokenPipeError (clients partis). Entrepôt redémarré le 2/10 à 06:52 UTC (`NRestarts=0`, donc redémarrage volontaire, origine non établie), `fd_ouverts` 6 à 10 sur 1 024, charge 1,0 sur 16 cœurs.
- Base LEGI à jour du jour (mtime 2026-10-02 04:00 UTC).

## Ordre de correction suggéré (rien n'a été corrigé)

1. F1 et F2 : faire mettre à jour `etat`, `date_fin`, `texte`, `nota` par l'UPSERT ; purger les lignes fantômes (même LEGIARTI, ancienne `date_debut`) en s'appuyant sur la dernière publication DILA ; puis rejouer les deltas depuis le 13/07/2025. Contrôle de non-régression : la liste des 8 FAUX ci-dessus contre l'API PISTE.
2. F8 : index sur `(legitext, num)` et `(jorftext, num)`, ou deux requêtes au lieu du OR (écriture en base : son arbitrage).
3. F3 : décoder le chemin avant la regex `/loi/` et élargir la classe (espace, `*`, lettres accentuées) ; encoder les URL du sitemap.
4. F4, F7 : porter `_check_dates` au REST ; harmoniser la gestion des codes entre les trois canaux.
5. F5, F6, F9, F10, paraphrases.
