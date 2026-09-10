# Audit total justicelibre.org — 10 septembre 2026

**Auditeur : agent indépendant, mandat adversarial, LECTURE SEULE.**
**Fenêtre de mesure : 10/09/2026, 08 h 35 → 11 h 05 UTC.**
**Règle appliquée : aucune conclusion sans commande exécutée et sortie brute recopiée.
Quand une mesure a surpris, elle a été refaite autrement AVANT de conclure — deux de mes
propres mesures ont été invalidées de cette façon (§ 2.0 et § 3.2) et sont rétractées ici.**

> ⚠️ **Avertissement de méthode.** Pendant l'audit, la propriétaire a déployé et relancé
> des services sur les deux serveurs : `justicelibre-warehouse` redémarré à 08 h 40 UTC ;
> `scrape_ariane.py` + un service `jl-ariane-plancher` lancés à 08 h 47 et **toujours en
> cours** ; la source `doctrine` a été branchée dans `/api/search` entre 10 h 15 et 11 h 30.
> Les chiffres ArianeWeb bougent donc d'une mesure à l'autre dans ce rapport (136 526 →
> 144 019 lignes en 45 min) et c'est normal. Chaque chiffre est daté.

---

## Résumé exécutif

**La réponse directe à la question posée — « pour la loi, tombe-t-on sur des abrogés qui se
présentent en “en vigueur” ? » — est OUI, systématiquement, et à très grande échelle.**

Toute page `https://justicelibre.org/loi/CODE/NUM` affiche, en sous-titre, sous le titre de
l'article, la phrase **« Article en vigueur depuis le … »** — quel que soit l'état réel de
l'article. Elle l'affiche pour l'article L. 321-1 du code du travail (licenciement
économique), abrogé le 1er mai 2008. Testé sur 26 articles abrogés : **26 sur 26 sont
annoncés « en vigueur »**. La cause est une seule ligne : `ssr.py:1101`.

**75 312 articles sur 231 772** (32,5 %) des 75 codes servis n'ont **aucune version en
vigueur aujourd'hui** : pour tous, c'est cette page-là qui est rendue.

Les autres découvertes majeures, toutes mesurées :

| # | Constat | Gravité |
|---|---|---|
| 1 | Toute page `/loi/` annonce « en vigueur » même pour un abrogé — 26/26 | CRITIQUE |
| 2 | La recherche du site rend **0 résultat sans erreur** quand une source dépasse 12 s (mesuré 16,0 s et 22,2 s à froid) ; le champ s'appelle `sources_no_result`, ce qui fait lire « ce fonds n'a rien » | CRITIQUE |
| 3 | Le scraper CEDH échoue **tous les jours depuis le 20 avril 2026** : 104 exécutions, **0 succès**. Trou total de mai, juin, juillet 2026 (0 arrêt) ; 463 arrêts manquants sur 2026 | CRITIQUE |
| 4 | **LEGI n'est pas cherchable** depuis le site : `sources_queried` ne contient jamais `legi`. Aucun article de loi ne remonte jamais dans une recherche | GRAVE |
| 5 | Les 985 996 décisions TA/CAA locales (`opendata.db`) sont **gelées au 27 avril 2026** alors que le cron dit « tout fini » chaque nuit | GRAVE |
| 6 | ArianeWeb gelé au **12 décembre 2025** (aucune décision 2026) | GRAVE |
| 7 | `search_decisions_citing` annonce `total: 12` là où `per_source` dit 19 404 | GRAVE |
| 8 | `about_justicelibre` (lu par tout LLM) sous-estime les TJ d'un facteur **10** (68 000 annoncés / 717 756 mesurés) et surestime ArianeWeb d'un facteur 1,9 | GRAVE |
| 9 | 22 340 arrêts CEDH (29,4 %) et 16 947 délibérations CNIL (63,1 %) **sans aucun texte** | GRAVE |
| 10 | `decisions.sommaire` toujours **hors de l'index FTS** (défaut signalé ce matin, non corrigé) | GRAVE |
| 11 | 198 940 lignes de `decisions` portent un ECLI en doublon (58,3 % des lignes qui ont un ECLI) | MOYEN |

**Ce qui tient**, mesuré : la fuite de descripteurs est réparée ; `/api/recent` répond 200 et
filtre correctement ; le plafond « moitié des résultats » est levé sur source unique ;
`total` n'est plus `len(results)` ; l'API JSON et le MCP disent honnêtement `etat: ABROGE`
(seule la page HTML ment) ; les versions futures ne sont jamais servies comme actuelles ;
les 10 derniers articles modifiés sont servis dans leur dernière version (12/12) ; les
deltas DILA sont appliqués à J-1 ; le contrôle de couverture quotidien détecte et signale
honnêtement le trou CEDH depuis 4 mois.

---

# POINT 1 — LOI : les « en vigueur » qui ne le sont pas

## 1.a — Distribution de `etat` et incohérences en base

### COMMANDE

```
ssh root@46.224.173.253 'timeout 300 sqlite3 -readonly /opt/justicelibre/dila/legi.db \
  "SELECT COALESCE(etat,\"<NULL>\"), COUNT(*) FROM legi_articles GROUP BY 1 ORDER BY 2 DESC;"'
```

### SORTIE BRUTE

```
VIGUEUR|718399
MODIFIE|440767
ABROGE|363947
|241389
PERIME|19792
VIGUEUR_DIFF|18936
TRANSFERE|15084
MODIFIE_MORT_NE|7956
ABROGE_DIFF|5795
ANNULE|1961
DISJOINT|84
DEPLACE|18
```

### COMMANDE (incohérences)

```
sqlite3 -readonly legi.db "SELECT COUNT(*) FROM legi_articles;"
sqlite3 -readonly legi.db "SELECT SUM(etat IS NULL), SUM(etat='') FROM legi_articles;"
sqlite3 -readonly legi.db "SELECT COUNT(*) FROM legi_articles WHERE etat='VIGUEUR' AND date_fin IS NOT NULL AND date_fin<>'' AND date_fin<>'2999-01-01' AND date_fin < date('now');"
sqlite3 -readonly legi.db "SELECT COUNT(*) FROM legi_articles WHERE etat='ABROGE' AND (date_fin IS NULL OR date_fin='' OR date_fin='2999-01-01');"
sqlite3 -readonly legi.db "SELECT CASE WHEN date_fin IS NULL THEN 'NULL' WHEN date_fin='' THEN 'vide' WHEN date_fin='2999-01-01' THEN '2999' WHEN date_fin<date('now') THEN 'passe' ELSE 'futur' END, COUNT(*) FROM legi_articles WHERE etat='VIGUEUR' GROUP BY 1;"
```

### SORTIE BRUTE

```
=== total ===
1834128
=== etat NULL vs vide ===
0|241389
=== VIGUEUR mais date_fin passee ===
17
=== ABROGE mais date_fin vide ou 2999 ===
73
=== distribution date_fin pour VIGUEUR ===
2999|718375
futur|7
passe|17
```

### Ce que sont les 241 389 `etat` vides

```
=== etat vide : date_fin ===
2999|241368
passe|21
=== etat vide : 3 exemples ===
LEGIARTI000006199771|LEGITEXT000006065141|1||2999-01-01|2999-01-01|a modifié les dispositions suivantes
LEGIARTI000006199772|LEGITEXT000006065141|2||2999-01-01|2999-01-01|a modifié les dispositions suivantes
LEGIARTI000006199773|LEGITEXT000006065141|3||2999-01-01|2999-01-01|a modifié les dispositions suivantes
```

Ce sont des articles *modificateurs* de lois de transposition (`date_debut = 2999-01-01`,
texte = « a modifié les dispositions suivantes »). Ils ne peuvent pas être servis par la
requête de date (leur `date_debut` est dans le futur). **Ce ne sont donc pas eux qui
produisent les faux « en vigueur ».**

### La vraie mesure : quel `etat` a la ligne que le serveur SERVIRAIT aujourd'hui

`warehouse_server.py:428-441` (stratégie 1) sélectionne par **date seulement**, sans
regarder `etat` :

```sql
WHERE {key} AND num IN (...)
  AND (date_debut IS NULL OR date_debut = '' OR date_debut <= ?)
  AND (date_fin   IS NULL OR date_fin   = '' OR date_fin   >= ?)
ORDER BY date_debut DESC LIMIT 1
```

### COMMANDE

```sql
WITH cand AS (
  SELECT legitext, num, etat, date_debut,
         ROW_NUMBER() OVER (PARTITION BY legitext, num ORDER BY date_debut DESC) rn
  FROM legi_articles
  WHERE (date_debut IS NULL OR date_debut='' OR date_debut<=date('now'))
    AND (date_fin IS NULL OR date_fin='' OR date_fin>=date('now'))
)
SELECT CASE WHEN etat='' THEN '<vide>' ELSE etat END, COUNT(*) FROM cand WHERE rn=1 GROUP BY 1 ORDER BY 2 DESC;
```

### SORTIE BRUTE

```
VIGUEUR|693293
VIGUEUR_DIFF|7746
ABROGE_DIFF|2274
<vide>|276
PERIME|132
ABROGE|69
ANNULE|30
MODIFIE|28
MODIFIE_MORT_NE|9
TRANSFERE|2
```

**VERDICT 1.a : `DÉFAUT TROUVÉ`** — les incohérences franches d'état sont rares (17 + 73), mais
la requête de service ignore complètement `etat` : 546 couples (legitext, num) sont servis
aujourd'hui à partir d'une ligne `ABROGE` / `PERIME` / `ANNULE` / `TRANSFERE` / `MODIFIE` /
`<vide>` que la fenêtre de dates n'exclut pas. Cas d'école mesuré : **CGI art. 302 J,
`etat=ABROGE`, `date_fin = 2222-02-22`** — une date sentinelle DILA qui fait passer un
article abrogé pour actuel.

---

## 1.b — 26 articles abrogés, 4 canaux : ce que chacun répond

### Choix des articles

Premier constat (à porter au crédit du projet) : les grands classiques du droit civil
**ne sont pas** des faux positifs. Les articles 1134, 1147, 1382, 1108, 1184 du code civil
existent toujours sous ces numéros avec un texte nouveau depuis l'ordonnance 2016-131 :

```
--- CC 1134 ---
LEGIARTI000006436298|1134|MODIFIE|1804-03-21|2016-10-01
LEGIARTI000032041008|1134|VIGUEUR|2016-10-01|2999-01-01
--- CC 1382 ---
LEGIARTI000006438819|1382|MODIFIE|1804-03-21|2016-10-01
LEGIARTI000032042379|1382|VIGUEUR|2016-10-01|2999-01-01
```

J'ai donc pris des articles **réellement abrogés sans successeur au même numéro** :
code du travail recodifié au 1er mai 2008, CESEDA recodifié au 1er mai 2021, CGI, et
20 articles du CPC tirés au sort (§ ci-dessous).

### COMMANDE (batterie 4 canaux)

```bash
for pair in "CT:L122-14" "CT:L120-1" "CT:L212-1" "CT:L321-1" "CESEDA:L313-11" "CESEDA:L741-4" "CGI:302J"; do
  curl -s -A "Mozilla/5.0" "https://justicelibre.org/api/law?code=$C&num=$N"                 # (i)
  curl -s -A "Mozilla/5.0" "https://justicelibre.org/api/law?code=$C&num=$N&date=2026-09-10" # (ii)
  curl -s -A "Mozilla/5.0" "https://justicelibre.org/loi/$C/$N"                              # (iii)
done
```

### SORTIE BRUTE (extraits significatifs)

```
########## CT L321-1
-- (i) API sans date
{'legiarti': 'LEGIARTI000006648602', 'num': 'L321-1', 'etat': 'ABROGE', 'date_debut': '2005-01-19',
 'date_fin': '2008-05-01', 'texte': "Constitue un licenciement pour motif économique le licenciement effectué par un employeur ",
 'note': 'Article non trouvé à la date demandée ; version la plus récente retournée.'}
-- (ii) API avec date=2026-09-10
{'legiarti': 'LEGIARTI000006648602', 'etat': 'ABROGE', 'date_debut': '2005-01-19', 'date_fin': '2008-05-01',
 'note': 'Article non trouvé à la date demandée ; version la plus récente retournée.'}
-- (iii) page /loi/CT/L321-1
 [HTTP:200]
  SUBLINE: Article en vigueur depuis le 19 janvier 2005.
  TITLE: Article L321-1 -Code du travail -JusticeLibre
  META-DESC: Constitue un licenciement pour motif économique le licenciement effectué par un employeur pour un ou plusieurs motifs non inhérents à la personne du salarié rés
  TABLE État : ABROGE
  TABLE Jusqu'au : 1 mai 2008
  TABLE En vigueur depuis : 19 janvier 2005
  JSONLD legalForce: PartiallyInForce
########## CESEDA L313-11
  SUBLINE: Article en vigueur depuis le 1 mars 2019.
  TABLE État : ABROGE
  TABLE Jusqu'au : 1 mai 2021
  JSONLD legalForce: PartiallyInForce
########## CGI 302J
  SUBLINE: Article en vigueur depuis le 1 avril 2010.
  TABLE État : ABROGE
  TABLE Jusqu'au : 22 février 2222
  JSONLD legalForce: PartiallyInForce
########## CESEDA L741-4   (temoin en vigueur)
  SUBLINE: Article en vigueur depuis le 1 mai 2021.
  TABLE État : VIGUEUR
  TABLE Jusqu'au : (absent)
  JSONLD legalForce: InForce
```

### (iv) canal MCP — `get_law_article`

```json
{"legiarti":"LEGIARTI000006648602","num":"L321-1","code":"CT","etat":"ABROGE",
 "date_debut":"2005-01-19","date_fin":"2008-05-01",
 "note":"Article non trouvé à la date demandée ; version la plus récente retournée."}
```

### Vérification élargie : 20 articles du CPC tirés au sort

```
CPC  1574      base=MODIFIE_MORT_NE  api=MODIFIE_MORT_NE 2011-04-01 page='Article en vigueur depuis le 1 mai 2011.'
CPC  1164      base=ABROGE           api=ABROGE 2017-02-10      page='Article en vigueur depuis le 1 janvier 1982.'
CPC  525-2     base=ABROGE           api=ABROGE 2020-01-01      page='Article en vigueur depuis le 9 novembre 2014.'
CPC  92        base=TRANSFERE        api=TRANSFERE 2017-09-01   page='Article en vigueur depuis le 30 décembre 1976.'
CPC  1095      base=ABROGE           api=ABROGE 2005-01-01      page='Article en vigueur depuis le 1 janvier 1982.'
CPC  1112      base=ABROGE           api=ABROGE 2021-01-01      page='Article en vigueur depuis le 1 janvier 2005.'
CPC  826-7     base=ABROGE           api=ABROGE 2020-01-01      page='Article en vigueur depuis le 11 mai 2017.'
CPC  1146-1    base=ABROGE           api=ABROGE 2022-02-28      page='Article en vigueur depuis le 1 janvier 2021.'
CPC  365       base=TRANSFERE        api=TRANSFERE 2017-05-11   page='Article en vigueur depuis le 1 janvier 2007.'
CPC  832-9     base=ABROGE           api=ABROGE 2010-12-01      page='Article en vigueur depuis le 15 septembre 2003.'
CPC  1097      base=ABROGE           api=ABROGE 2005-01-01      page='Article en vigueur depuis le 1 janvier 1982.'
CPC  826-21    base=ABROGE           api=ABROGE 2020-01-01      page='Article en vigueur depuis le 11 mai 2017.'
CPC  1282      base=ABROGE           api=ABROGE 1994-02-01      page='Article en vigueur depuis le 1 janvier 1982.'
CPC  1080-1    base=ABROGE           api=ABROGE 2005-01-01      page='Article en vigueur depuis le 1 octobre 1984.'
CPC  1136-10   base=ABROGE           api=ABROGE 2025-01-17      page='Article en vigueur depuis le 29 mai 2020.'
CPC  768-1     base=ABROGE           api=ABROGE 2020-01-01      page='Article en vigueur depuis le 1 octobre 1984.'
CPC  688-10    base=ABROGE           api=ABROGE 2006-03-01      page='Article en vigueur depuis le 12 décembre 2002.'
CPC  1111      base=ABROGE           api=ABROGE 2021-01-01      page='Article en vigueur depuis le 1 janvier 2005.'
CPC  1424-16   base=ABROGE           api=ABROGE 2014-01-01      page='Article en vigueur depuis le 1 octobre 2011.'
CPC  1136-4    base=ABROGE           api=ABROGE 2020-05-29      page='Article en vigueur depuis le 1 janvier 2020.'
```

**20 sur 20.** Total avec la batterie précédente : **26 articles abrogés / transférés /
morts-nés testés, 26 annoncés « Article en vigueur depuis le … ».**

### La ligne fautive

`ssr.py:1101` :

```python
<p class="subline">Article{(' en vigueur depuis le ' + esc(_format_fr_date(date_debut))) if date_debut else ''}.</p>
```

`etat` n'entre pas dans cette phrase. Il n'apparaît que dans une ligne de tableau
(`ssr.py:1047`), en majuscules brutes (`ABROGE`), sous la phrase qui dit le contraire.
Le `note` renvoyé par l'API **n'est pas rendu du tout** dans la page :

```
note rendue dans la page ? -> 0 occurrence(s)
mot 'abrog' (minuscule) -> 0
ABROGE -> 1
```

Et le JSON-LD (`ssr.py:1041`) déclare `"legislationLegalForce": "PartiallyInForce"` pour un
article abrogé — la valeur schema.org correcte est `NotInForce`.

### Combien d'articles sont concernés

```
articles SANS aucune version couvrant aujourd'hui : 75312 / 231772 articles (codes servis)
  CT         LEGITEXT000006072050 10226
  CSP        LEGITEXT000006072665  9422
  CPP        LEGITEXT000006071154  5742
  CSS        LEGITEXT000006073189  4775
  CCom2      LEGITEXT000006070162  3442
  CCH        LEGITEXT000006074096  2987
  C.env      LEGITEXT000006074220  2417
  CU         LEGITEXT000006074075  2087
  CGI        LEGITEXT000006069577  2049
  CGCT       LEGITEXT000006070633  2041
  CMF        LEGITEXT000006072026  1636
  C.com      LEGITEXT000005634379  1596
  CAss       LEGITEXT000006073984  1563
  COJ        LEGITEXT000006071164  1446
  CRurA      LEGITEXT000006071366  1422
```

### Nuances à décharge (mesurées, à ne pas escamoter)

- L'**API JSON** (`/api/law`) est honnête : `etat`, `date_fin` et `note` sont tous renvoyés.
- Le **MCP** est honnête : mêmes champs.
- Le **panneau latéral de `search.html`** est honnête. `renderLawInto()` affiche
  « Version du … au … » et un badge coloré `law-etat-abroge`, et rend `data.note`.
- Les pages `/loi/` ne sont **ni** dans `sitemap.xml` (0 occurrence de `/loi/`) **ni** liées
  depuis `search.html`, `index.html`, `ressources.html` ou une page décision (0 occurrence).

**Mais** — et c'est ce qui referme la porte de sortie — `llms.txt`, le fichier que le site
publie à l'usage des assistants, donne cette URL comme LA citation d'un article de loi :

```
42:- Article de loi : `https://justicelibre.org/loi/{code}/{num}` (ex :
43:  https://justicelibre.org/loi/CC/1128)
```

et `indexnow_ping.py:138` pousse `https://justicelibre.org/loi/CASF/L262-8` aux moteurs.

**VERDICT 1.b : `DÉFAUT TROUVÉ` — CRITIQUE.** 26/26. Une requérante qui suit le lien que le
site lui-même publie pour citer un article lit « Article en vigueur depuis le 19 janvier 2005 »
au-dessus du texte de l'article L. 321-1 du code du travail, abrogé depuis dix-huit ans.

---

## 1.c — 12 articles en vigueur modifiés récemment : la dernière version est-elle servie ?

### COMMANDE

Sélection en base des articles `VIGUEUR` avec `date_debut >= 2024-01-01` dans 10 grands codes,
puis interrogation de `/api/law` sans date et comparaison du `legiarti` servi.

### SORTIE BRUTE

```
##### CJA R121-3 (attendu legiarti=LEGIARTI000054748261)
  servi: LEGIARTI000054748261 VIGUEUR 2026-08-27 -> 2999-01-01 note= None
##### CJA R123-6 (attendu legiarti=LEGIARTI000054748264)
  servi: LEGIARTI000054748264 VIGUEUR 2026-08-27 -> 2999-01-01 note= None
##### CSP L1110-5 (attendu legiarti=LEGIARTI000054711030)
  servi: LEGIARTI000054711030 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CSS L161-37 (attendu legiarti=LEGIARTI000054711116)
  servi: LEGIARTI000054711116 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CSS L160-14 (attendu legiarti=LEGIARTI000054711279)
  servi: LEGIARTI000054711279 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CP 222-33 (attendu legiarti=LEGIARTI000054724663)
  servi: LEGIARTI000054724663 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CP 311-4 (attendu legiarti=LEGIARTI000054716098)
  servi: LEGIARTI000054716098 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CP 433-5 (attendu legiarti=LEGIARTI000054716075)
  servi: LEGIARTI000054716075 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### C.cons L412-4-1 (attendu legiarti=LEGIARTI000054715648)
  servi: LEGIARTI000054715648 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CJA L77-16-1 (attendu legiarti=LEGIARTI000054716776)
  servi: LEGIARTI000054716776 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CSP L5126-6 (attendu legiarti=LEGIARTI000054711194)
  servi: LEGIARTI000054711194 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
##### CSP L1321-2 (attendu legiarti=LEGIARTI000054715836)
  servi: LEGIARTI000054715836 VIGUEUR 2026-08-20 -> 2999-01-01 note= None
```

**VERDICT 1.c : `CONFIRMÉ`** — 12/12. La version servie est bien la plus récente, et la base
LEGI descend jusqu'au 27 août 2026 (delta appliqué la nuit du 9 au 10). Aucun défaut ici.

---

## 1.d — Les versions futures sont-elles présentées comme actuelles ?

### COMMANDE

```
sqlite3 -readonly legi.db "SELECT date_debut, COUNT(*) FROM legi_articles WHERE date_debut>date('now') GROUP BY 1 ORDER BY 2 DESC LIMIT 12;"
```

### SORTIE BRUTE

```
2999-01-01|241206
2029-01-01|5482
2027-01-01|2524
2222-02-22|865
2026-10-01|382
2026-12-10|379
2028-01-01|274
2026-11-20|185
2027-09-01|118
2026-11-01|81
2028-07-01|67
2027-01-11|67
```

Cas concret : CGI art. 88, 99 et 1736 ont chacun une version `VIGUEUR_DIFF` au 1er janvier 2027.

```
=== API ===
-- CGI 88     LEGIARTI000030751924 ABROGE_DIFF 2016-02-01 2027-01-01 note= None
-- CGI 1736   LEGIARTI000054373979 ABROGE_DIFF 2026-07-01 2030-01-01 note= None
-- CGI 99     LEGIARTI000053546818 ABROGE_DIFF 2026-02-21 2027-01-01 note= None
=== page CGI 88 subline ===
<p class="subline">Article en vigueur depuis le 1 février 2016.
```

**VERDICT 1.d : `CONFIRMÉ` (pas de défaut).** La clause `date_debut <= aujourd'hui` exclut
bien les versions futures ; c'est la version applicable au 10/09/2026 qui est servie
(`ABROGE_DIFF` = en vigueur, abrogation programmée), et le tableau affiche « Jusqu'au
1 janvier 2027 ». C'est correct au fond. Le libellé `ABROGE_DIFF` reste jargonneux pour
une non-juriste.

---

## 1.e — Codes en base non atteignables par un raccourci ; lois hors code

### Première mesure, puis correction

Un simple « absent de `CODE_TO_LEGITEXT` » aurait donné une conclusion fausse : le serveur
cherche aussi dans la colonne `jorftext` (`warehouse_server.py:547-556`), si bien que
`CR → LEGITEXT000006071367` (0 article sous ce legitext) atteint quand même les 33 710
articles du code rural :

```
  legiarti = LEGIARTI000006583720
  legitext = LEGITEXT000022197698
  jorftext = LEGITEXT000006071367
       num = L411-1
```

J'ai donc recalculé l'atteignabilité **réelle** (legitext OU jorftext).

### COMMANDE

```python
reach = {legitext} atteints par les 79 raccourcis via (legitext IN … OR jorftext IN …)
puis, pour chaque CODE de legi_textes non atteint : COUNT(*) de ses articles
```

### SORTIE BRUTE

```
legitext ATTEINTS par les 79 raccourcis : 79
CODES en base : 111
CODES INATTEIGNABLES par un raccourci : 36
  LEGITEXT000006072052 | etat=ABROGE   |   5209 art. | Code du travail applicable à Mayotte.
  LEGITEXT000006074068 | etat=MODIFIE  |   3659 art. | Code des pensions militaires d'invalidité et des victimes de la guerre.
  LEGITEXT000006071514 | etat=ABROGE   |   3375 art. | Code forestier
  LEGITEXT000006074947 | etat=ABROGE   |    994 art. | Code de la route
  LEGITEXT000006069562 | etat=ABROGE   |    906 art. | Code des marchés publics
  LEGITEXT000006071029 | etat=ABROGE   |    771 art. | CODE PENAL
  LEGITEXT000031712069 | etat=VIGUEUR  |    731 art. | Code des pensions militaires d'invalidité et des victimes de guerre.
  LEGITEXT000006070884 | etat=ABROGE   |    729 art. | Code de justice militaire
  LEGITEXT000005627819 | etat=ABROGE   |    601 art. | Code des marchés publics
  LEGITEXT000006071344 | etat=ABROGE   |    499 art. | Code des tribunaux administratifs et des cours administratives d'appel
  LEGITEXT000006071556 | etat=ABROGE   |    469 art. | Code forestier de Mayotte
  LEGITEXT000006069441 | etat=ABROGE   |    442 art. | Code de commerce
  LEGITEXT000006071189 | etat=ABROGE   |    356 art. | Code de la nationalité française
  LEGITEXT000006071657 | etat=ABROGE   |    353 art. | Code du vin
  LEGITEXT000037673300 | etat=VIGUEUR  |    343 art. | Code de la Légion d'honneur, de la Médaille militaire et de l'ordre national du Mérite
  LEGITEXT000006075115 | etat=ABROGE   |    237 art. | Code des débits de boissons et des mesures contre l'alcoolisme
  LEGITEXT000006070680 | etat=ABROGE   |    210 art. | Code de procédure civile (1807)
  … (20 autres, détail complet dans la sortie de /tmp/reach.py)
```

**36 codes, non 32.** Total ≈ 20 234 articles. Deux d'entre eux sont **en vigueur** :
le code des pensions militaires d'invalidité (731 art.) et le code de la Légion d'honneur
(343 art.). Les autres sont des codes abrogés d'un intérêt contentieux réel (code de la
route ancien, code des marchés publics — abondamment cité, code des TA et CAA, CPC de 1807).

### Sont-ils atteignables autrement ?

```
=== API avec LEGITEXT direct (code des marchés publics ancien) ===
{"legiarti": "LEGIARTI000006290614", "num": "1", "code": "LEGITEXT000006069562", "legitext": "LEGITEXT000006069562",
 "titre_texte": "Code des marchés publics", "titre_section": "Livre I : Dispositions générales applicables aux marchés publics.",
 "etat": "ABROGE", "date_debut": "1964-07-21", "date_fin": "2001-09-09", ...}
=== page /loi/LEGITEXT000006069562/1 ===
 [HTTP:200]
<p class="subline">Article en vigueur depuis le 21 juillet 1964.
```

**Oui, si et seulement si on connaît le LEGITEXT.** Aucune page du site ne liste les codes
disponibles ni leurs identifiants ; la seule liste publique des sigles est la ressource MCP
`justicelibre://codes-supportes`. Et pour un usager du site, il n'existe aucun endpoint de
résolution :

```
law/resolve?numero=78-17         {"error": "Endpoint inconnu : /api/law/resolve."} [404]
resolve?numero=78-17             {"error": "Endpoint inconnu : /api/resolve."} [404]
```

alors que l'entrepôt expose bien `/v1/law/resolve` (`warehouse_server.py:945`) et que le MCP
l'expose sous `resolve_law_number` (testé : `78-17 → LEGITEXT000006068624, 484 articles`).

### Les lois / ordonnances hors code

```
=== textes non-CODE ayant des articles ===
ARRETE|88829
DECRET|55108
LOI|3643
ORDONNANCE|1458
LOI_ORGANIQUE|112
DELIBERATION|58
DECRET_LOI|33
DECISION|32
```

Soit **5 213 lois / lois organiques / ordonnances / décrets-lois** (3 643 + 112 + 1 458)
— l'ordre de grandeur « 5 206 » du mandat est confirmé. Elles sont atteignables par
LEGITEXT direct (test loi 78-17, art. 2 → `HTTP 200`, `etat: VIGUEUR`), mais **pas par leur
numéro** depuis le site, faute de route `resolve`.

**VERDICT 1.e : `EXAGÉRÉ` dans un sens et `DÉFAUT TROUVÉ` dans l'autre.** « 32 codes
inatteignables » est faux par défaut — il y en a **36** ; mais « inatteignables » est trop
fort : ils le sont par LEGITEXT. Le défaut réel est ailleurs : **il n'existe aucune page ni
route publique permettant de découvrir un code ou de résoudre un numéro de loi**, et
`/api/law/resolve` n'est pas proxyfié alors qu'il existe en amont.

### Défaut annexe : les numéros à espace sont inatteignables par URL

```
/loi/CGI/302%20J           404
/loi/CGI/302+J             404
/loi/LPF/L80%20B           404
/loi/LPF/L80B              200
```

Cause : `token_server.py:225`, `r"^/loi/([\w.\-]{1,20})/([A-Z]?[\w.\-]{1,40})$"` — `\w`
n'accepte pas l'espace. Le message d'erreur est de surcroît trompeur (« Endpoint inconnu »
au lieu de « article introuvable »). Concerne tous les articles CGI/LPF de la forme
« 302 J », « L80 B », « 1609 tertricies », etc.

---

# POINT 2 — Les colonnes sont-elles « full » ?

## 2.0 — RÉTRACTATION MÉTHODOLOGIQUE (à lire avant les chiffres)

J'ai d'abord échantillonné les grandes tables (> 500 000 lignes) par **3 blocs de 20 000
lignes consécutives** placés au début, au tiers et aux deux tiers de la plage de `rowid`.
Une valeur m'a surpris (`jorf_textes.texte` à 34 %), je l'ai donc re-mesurée exactement :

```
timeout 900 sqlite3 -readonly jorf.db "SELECT COUNT(*), SUM(texte IS NOT NULL), SUM(texte IS NOT NULL AND TRIM(texte)<>''), SUM(num_jorf IS NOT NULL AND num_jorf<>'') FROM jorf_textes;"
→ 1273923|1273923|993199|0
```

**77,96 % réels contre 34,19 % échantillonnés.** L'échantillonnage par blocs est donc
**invalide** sur ces tables : elles sont ordonnées par lot d'ingestion, chaque bloc tombe
dans une strate homogène. Signature du biais : des valeurs à exactement `33,33 % (20000/60000)`,
c'est-à-dire « un bloc sur trois ».

**Conséquence.** Tous les taux marqués `[échantillon]` ci-dessous sont **indicatifs et
probablement faux**. Les taux marqués `[exact]` ont été recomptés sur la table entière et
font seuls foi. Trois comparaisons montrent l'ampleur du biais :

| colonne | échantillon | exact | écart |
|---|---|---|---|
| `jade_decisions.solution` | 39,23 % | **15,49 %** | ×2,5 |
| `jade_decisions.ecli` | 2,39 % | **7,30 %** | ×3 |
| `opendata_decisions.ecli` | 33,33 % | **3,60 %** | ×9 |
| `decisions.ecli` | 36,98 % | **13,15 %** | ×2,8 |
| `jorf_textes.texte` | 34,19 % | **77,96 %** | ×2,3 |

## 2.1 — Tables mesurées EXACTEMENT (table entière)

### `decisions` (prod, 2 596 246 lignes)

```
SELECT COUNT(*) FROM decisions WHERE ecli IS NOT NULL AND ecli<>'';   →  341337
```
**`ecli` = 341 337 / 2 596 246 = 13,15 %** `[exact]`. **86,85 % des décisions judiciaires
n'ont pas d'ECLI.**

Le reste des colonnes de `decisions` n'a **pas** pu être compté exactement : la requête
d'agrégat sur les 11 colonnes a dépassé 3 000 s (table de 54 Go, colonnes non indexées).
Voir « ce que je n'ai pas pu mesurer ».

### `jade_decisions` (JADE — CE + TC + 9 CAA + 40 TA — 570 890 lignes) `[exact]`

```
570890|41683|88443|370908|338965|561
(total | ecli | solution | avocats | sommaire | texte<200car)
```

| colonne | taux | lecture |
|---|---|---|
| `ecli` | **7,30 %** | 529 207 décisions administratives sans ECLI |
| `solution` | **15,49 %** | on ne sait pas si la requête a été rejetée ou accueillie dans 84,5 % des cas |
| `avocats` | 64,97 % | |
| `sommaire` | 59,38 % | |
| texte < 200 car. | 561 (0,1 %) | sain |

### `opendata_decisions` (TA/CAA, 985 996 lignes) `[exact]`

```
985996|35455|613842|563666|0
(total | ecli | formation | publication_code | texte<200car)
```
`ecli` = **3,60 %**. `formation` = 62,25 %. Aucun texte court. *(Confirme et affine le
« 96,4 % sans ECLI » du premier audit : c'est 96,4 %.)*

### `legi_articles` (1 834 128 lignes) `[exact]`

```
1834128|1084289|152466|1458938|501956|29420
(total | hierarchie | nota | liens | texte<200car | num vide)
```
`hierarchie` 59,12 % · `nota` 8,31 % · `liens` 79,54 % · **`texte` < 200 car. 501 956 (27,4 %)**
· `num` vide 29 420.

Contrôle du contenu des textes courts :

```
=== legi : texte vide / tres court ===
1225|500731
=== 5 exemples de texte court ===
LEGIARTI000006850356|21||a modifié les dispositions suivantes
LEGIARTI000006604873|1||a modifié les dispositions suivantes
```
→ ce sont majoritairement des articles modificateurs légitimes (500 731 courts pour
1 225 réellement vides). **Attendu**, pas un champ jeté.

### `jorf_textes` (1 273 923 lignes) `[exact]`

`texte` non vide = **993 199 (77,96 %)**. **`num_jorf` = 0 ligne remplie (0,00 %)**, alors
que `parse_dila_bulk.py:328` lit bien `META_TEXTE_CHRONICLE/NUM_JORF`. Champ lu et jamais
peuplé → **défaut de parseur**.

### `cedh_decisions` (76 062) `[exact — table entière]`

```
ecli 70,66 % · article 97,89 % · conclusion 97,89 % · importance 100 % · respondent 99,99 %
text 70,63 %  ← 22 340 arrêts SANS AUCUN TEXTE
text_itemid 70,61 % · appno 99,95 % · appno_avant 45,00 %
texte vide=22340  <200 car=0
```

### `cjue_decisions` (44 689) `[exact]`

```
ecli 91,72 % · title 91,64 % · text 91,70 % (3 709 sans texte) · title_avant 27,55 %
```

### `cass_decisions` (145 347) `[exact]`

```
ecli 12,18 % · numero 81,76 % · rapporteur 70,70 % · avocat_general 69,48 % · renvois 44,11 %
sommaire 99,42 % · abstrats 99,41 % · resume 98,56 % · form_dec_att 77,99 % · siege_appel 0,00 %
numeros_affaires 2,55 %
```

### `capp_decisions` (73 050) `[exact]`

```
ecli 0,01 % (6 lignes !) · president 3,71 % · rapporteur 0,01 % · avocats 0,00 % (2 lignes)
solution 47,37 % · sommaire 26,19 % · resume 25,87 % · renvois 0,11 % · liens_textes 10,26 %
siege_appel 95,35 % · numero_rg_norm 0,00 %
```

### `inca_decisions` (387 640) `[exact]`

```
ecli 23,84 % · rapporteur 0,42 % · avocat_general 0,42 % · avocats 34,04 %
sommaire 20,52 % · resume 0,35 % · renvois 0,10 % · liens_textes 19,82 %
form_dec_att 99,59 % · date_dec_att 98,94 %
```

### `constit_decisions` (7 388) `[exact]`

```
ecli 100 % · solution 95,83 % · texte 100 % · url_cc 100 % · titre_jo 99,62 % · nor 83,88 %
sommaire 0,00 % · abstrats 0,00 % · saisines 3,55 % · loi_def 10,88 % · ancien_id 47,52 %
```

### `cnil_deliberations` (26 852) `[exact]`

```
numero 99,96 % · titre 100 % · date 100 % · nature_delib 99,94 % · etat_juridique 100 %
texte 36,89 %   ← 16 947 délibérations SANS TEXTE (63,1 %)
formation 0,00 % · nor 4,29 % · origine_publi 0,00 %
```

### `kali_textes` (351 279) `[exact]`

```
idcc 85,63 % · titre 100 % · texte 88,90 % · article_num 71,85 % · article_titre 44,40 %
section_id 49,66 % · section_titre 49,65 % · origine_publi 6,08 % · liens 56,25 %
```

### `legi_textes` (153 566) `[exact]`

```
num_jorf 32,94 % · nor 91,42 % · num_parution 63,15 % · origine_publi 59,34 %
ministere 0,00 % · autorite 0,00 %
```

### `doctrine.docs` (107 273) `[exact]`

```
titre 100 % · administration 100 % · contenu 97,80 % · source_url 100 %
date 85,27 % · sujet 77,28 % · tags 78,78 % · partie 54,73 % · objet 0,00 %
```

### `ariane_decisions` (137 605 lignes au moment de la mesure — **en cours de moisson**)

```
ariane_id 100 % · text 100 % · numero 91,82 % · ecli 90,65 % · date 91,82 %
juridiction 91,82 % · president 24,35 % · rapporteur_public 27,25 %
toutes les colonnes *_avant : 0,00 %
```

Soit **10 633 lignes (7,8 %) sans date, sans juridiction, sans numéro** — invisibles à tout
filtre. Exemples :

```
/Ariane_Web/AW_DCE/|325793|325793|||
/Ariane_Web/AW_DCE/|325792|325792|||
```

Les 9 colonnes `*_avant` sont à 0,00 % : reliquat d'une campagne d'enrichissement.

## 2.2 — Champs jetés en dur par le parseur

### COMMANDE

```
grep -nE ":\s*\"\"|=\s*\"\"" /opt/justicelibre/judilibre_sync.py
```

### SORTIE BRUTE

```
172:    rg_norm = ""
188:        "avocats": "",
195:        "commissaire_gvt": "",
197:        "publi_recueil": "",
200:        "saisines": "",
201:        "loi_def": "",
202:        "liens_textes": "",
```

`judilibre_sync.py:188-202` — pour toute décision entrée par Judilibre (le flux quotidien,
donc **toutes les décisions récentes**), `avocats`, `commissaire_gvt`, `publi_recueil`,
`saisines`, `loi_def` et **`liens_textes`** sont écrits vides en dur. `liens_textes` est le
champ « textes visés » : c'est lui qui permettrait de répondre « quelles décisions visent
l'article X ». Judilibre le fournit (champ `visa`), il est conservé dans `judilibre_meta`
mais **pas** recopié dans la colonne exploitée.

À décharge : dans `parse_dila_bulk.py`, les lignes 200, 323 et 486 que l'on pourrait prendre
pour des mises à vide en dur sont de simples **initialisations** avant lecture du XML — j'ai
lu le contexte, ce ne sont pas des champs jetés. Ne pas les compter.

Les colonnes à 0,00 % dans `jade`/`cass`/`capp`/`inca`/`constit` (`demandeur`, `defendeur`,
`juri_prem`, `lieu_prem`, `observations`, `url_cc`, `titre_jo`, `nor`…) sont l'effet d'un
**schéma unique partagé** entre fonds de nature différente : `url_cc` est à 100 % dans
`constit` et 0 % ailleurs, `siege_appel` à 95,35 % dans `capp` et 0 % ailleurs. C'est
**attendu**, pas un champ jeté — mais rien ne le documente.

## 2.3 — Contrôle du contenu (pas de `[]`, `{}`, `null`, valeur constante)

Le script de remplissage comptait déjà `[]`, `{}`, `null`, `None`, `NULL` comme vides.
Contrôles ciblés :

- `legi_articles.hierarchie` : JSON réel, désérialisé et exploité par `_titre_section()`
  (`warehouse_server.py:550`) — vérifié en sortie d'API : `"titre_section": "8° : Dispositions
  applicables aux personnes morales de droit public"` (CGI 302 J) et `"Chapitre Ier :
  Licenciement pour motif économique."` (CT L321-1). **Contenu réel, pas de remplissage.**
- `decisions.judilibre_meta` : présent uniquement sur les lignes Judilibre, contenu JSON
  documenté (`zones`, `visa`, `nac`, `themes`, `timeline`…).
- `doctrine.docs.date` : **valeurs non ISO à 57 %** — voir § 6.5.
- `decisions.juridiction` : valeur `cc` (code brut) sur 556 422 lignes — voir § 6.6.

**VERDICT POINT 2 : `DÉFAUT TROUVÉ`.** Les colonnes ne sont pas « full » et l'écart est
massif sur les champs qui servent à **citer** (ECLI 13,15 % en judiciaire, 7,30 % en
administratif, 3,60 % en open data TA/CAA) et à **lire** (29,4 % des arrêts CEDH et 63,1 %
des délibérations CNIL n'ont aucun texte).

---

# POINT 3 — La jurisprudence est-elle à jour ?

## 3.1 — MAX(date) par fonds

### SORTIE BRUTE

```
=== MAX date par famille (table decisions) ===
cass|2026-09-09
ca|2026-08-31
tj|2026-09-04
tcom|2026-09-01
constit|2026-07-31
=== ariane / cedh / cjue ===
ariane|2025-12-12|325793      ← MAX(date) | MAX(ariane_num)
cedh|2026-09-03
cjue|2026-09-09
=== opendata (al-uzza) ===
985996|2026-04-27|2021-09-03  ← COUNT | MAX(date) | MIN(date)
```

## 3.2 — RÉTRACTATION : le « trou cassation 2025 » n'existe pas

Première mesure, sur `juridiction LIKE 'Cour de cassation%'` :

```
2025-06|690   2025-07|50   2025-08|4   2025-09|122  2025-10|103  2025-11|143  2025-12|91
2026-01|1624  2026-02|1352 2026-03|1884
```

J'allais conclure à un trou de six mois. **Re-mesure obligatoire** (règle du mandat) :

```
=== juridictions contenant "cass" ===
cc|556422
Cour de cassation|536486
=== par mois, juridiction='cc' ===
2025-07|766  2025-08|72  2025-09|1538  2025-10|1618  2025-11|1862  2025-12|1369
```

**La Cour de cassation est écrite de DEUX façons dans la même colonne : `cc` (556 422 lignes,
un code brut) et `Cour de cassation` (536 486 lignes).** En additionnant, aucun trou.
**Ma première mesure était fausse ; je la rétracte.** Confirmé par le contrôle indépendant
du serveur (`/var/log/jl-couverture-judilibre.log`) :

```
     cc   2025 : Judilibre=  16274  nous=  16220  manque=     54 (0.3 %)
     ca   2025 : Judilibre= 129963  nous= 129373  manque=    590 (0.5 %)
     tj   2025 : Judilibre= 320794  nous= 317410  manque=   3384 (1.1 %)
     tcom 2025 : Judilibre= 109955  nous= 108819  manque=   1136 (1.0 %)
✅ couverture Judilibre : toutes les années dans la marge
```

**VERDICT 3.2 : `CONFIRMÉ`** — le fonds judiciaire est à jour (retard maximal 1,1 % sur 2025),
mesuré contre Judilibre. Le mois d'août est structurellement creux (vacation judiciaire :
2024-08 = 19 arrêts cass., 2025-08 = 72). Rien à signaler.

## 3.3 — CEDH : trou de trois mois, et un scraper mort depuis 144 jours

### COMMANDE

```
sqlite3 -readonly judiciaire.db "SELECT substr(date,1,7),COUNT(*) FROM cedh_decisions WHERE date>='2025-07-01' GROUP BY 1 ORDER BY 1;"
```

### SORTIE BRUTE

```
2025-07|137
2025-08|33
2025-09|204
2025-10|223
2025-11|157
2025-12|233
2026-01|110
2026-02|123
2026-03|124
2026-04|108
2026-08|7
2026-09|4
```

**Mai, juin et juillet 2026 : absents de la sortie, c'est-à-dire ZÉRO ligne.** Contre-mesure
(règle de l'argument tiré d'une absence) :

```
SELECT COUNT(*) FROM cedh_decisions WHERE date>='2026-05-01' AND date<'2026-08-01';  → 0
SELECT COUNT(*), SUM(date IS NULL OR date=''), SUM(length(date)<>10) FROM cedh_decisions;  → 76062|0|0
```

Aucune date mal formée qui expliquerait le trou. Août 2026 = 7, septembre = 4.

### Cause racine

```
grep -c "CEDH OK" /var/log/justicelibre/scrape_increments.log            → 0
grep -c "CEDH timeout/error" /var/log/justicelibre/scrape_increments.log → 104
head -3 /var/log/justicelibre/scrape_increments.log
  [2026-04-20 05:00:01] daily incremental START
```

**Zéro succès en 104 exécutions depuis le 20 avril 2026.** Le message d'erreur, en clair :

```
[05:00:01] CEDH...
CEDH existing: 76062
Total CEDH FR (all years): 76614

=== YEAR 2026 ===
  total for year=2026: 939
  year=2026 start=0 len=100
  [text 001-252409]: HTTP 204
  [text 001-252451]: HTTP 204
  [text 001-252452]: HTTP 204
  … (10 fois)

*** COUPE-CIRCUIT : 10 échecs d'affilée — l'endpoint de conversion HUDOC ne répond plus.
Arrêt pour laisser la fenêtre aux autres sources ; reprise au prochain passage. (+0 cette exécution)
[05:01:37] CEDH timeout/error (non-fatal)
```

L'endpoint de conversion de HUDOC renvoie `HTTP 204` ; le coupe-circuit s'arme ; le script
sort avec « **+0 cette exécution** » ; le shell l'étiquette « **(non-fatal)** » ; et le job
global conclut « daily incremental DONE ». **C'est exactement le piège « OK, +0 » que le
mandat demandait de chercher, sous un autre libellé.** Le script sait même combien il manque :
`76 614` disponibles chez HUDOC contre `76 062` en base.

### À décharge : le contrôle de couverture, lui, ne ment pas

```
=== couverture_alertes.txt ===
Dernier contrôle : 2026-09-10 06:03:20 UTC

⚠️  1 ALERTE(S)
   • cedh 2026 : 476/939 (50.7 %), 463 manquant(s)
```

et dans `couverture.log`, la même alerte les 8, 9 et 10 septembre. **Le système d'alerte
fonctionne parfaitement.** Le défaut est qu'il écrit dans un fichier sur le serveur et que
personne ne le lit : l'alerte est identique depuis quatre mois.

**VERDICT 3.3 : `DÉFAUT TROUVÉ` — CRITIQUE.** 463 arrêts CEDH de 2026 manquants (49,3 % de
l'année), trois mois entiers à zéro, scraper en échec quotidien depuis 144 jours,
échec masqué par le mot « non-fatal ».

## 3.4 — CJUE

```
2025-07|149  2025-08|55  2025-09|177  2025-10|158  2025-11|115  2025-12|130
2026-01|107  2026-02|122 2026-03|177  2026-04|124  2026-05|73   2026-06|134
2026-07|123  2026-08|8   2026-09|78
```

Contrôle indépendant : `cjue 2026 : 947 annoncé / 946 chez nous (99.9 %)`.
**VERDICT 3.4 : `CONFIRMÉ`.** À jour (MAX 2026-09-09). Le CJUE a toutefois échoué les 9 et
10 septembre (`CJUE timeout/error`) après avoir réussi les jours précédents — à surveiller.

## 3.5 — ArianeWeb : gelé au 12 décembre 2025

```
=== ariane par mois 14 mois ===
2025-07|453
2025-08|84
2025-09|92
2025-10|248
2025-11|258
2025-12|109
```

**Aucune décision datée de 2026.** Neuf mois de Conseil d'État absents de ce fonds.
Le journal du 10/09 :

```
[ariane] start ; UA = justicelibre.org/1.0 (open data, contact: dahliyaal@justicelibre.org)
[ariane] DB existing : 128592
[ariane] resume from id=243481
[06:01:37] ArianeWeb timeout/error (non-fatal)
```

Le scraper reprend à l'id 243 481 alors que `MAX(ariane_num)` vaut 325 793 : il balaie une
zone déjà couverte. Et `couverture.log` affiche `ariane fraîcheur — 2026-09-09` : cette
ligne mesure la **date de moisson**, pas la date des décisions — **paraphrase trompeuse**,
elle donne un fonds « frais » alors que rien n'est entré depuis décembre 2025.

*Réserve honnête :* le mandat demandait de sonder 20 identifiants au-dessus de MAX.
**Je ne l'ai pas fait** : un `scrape_ariane.py` et un service `jl-ariane-plancher` tournaient
déjà pendant l'audit (lancés à 08 h 47) et ajoutaient ~7 000 lignes en 45 minutes ; sonder
en parallèle aurait doublé la charge sur le Conseil d'État sans rien apprendre. Je note en
revanche que `MIN(ariane_num) = 55 000` alors que `scrape_ariane.py:39` porte
`START_ID = 95_000` : **le « plancher jamais exploré » signalé ce matin est en cours de
correction, et déjà descendu à 55 000.**

**VERDICT 3.5 : `DÉFAUT TROUVÉ` — GRAVE.** Zéro décision ArianeWeb en 2026 ; l'indicateur de
fraîcheur mesure la mauvaise chose.

## 3.6 — Open data TA/CAA : gelé au 27 avril 2026, cron qui dit « tout fini »

```
ls -l /opt/justicelibre/dila/opendata.db
-rw-r--r-- 1 root root 14312185856 Aug 29 19:53 /opt/justicelibre/dila/opendata.db

SELECT COUNT(*), MAX(date), MIN(date) FROM opendata_decisions;
985996|2026-04-27|2021-09-03
```

Le fichier n'a pas été modifié depuis le 29 août. Le cron (`0 5 * * *`) tourne pourtant
chaque nuit :

```
[2026-09-09 05:00:01] opendata: (re)démarrage
[start] resume: 12000 partitions déjà faites
[start] fetch_text=False
[start] target: 50 juridictions × 240 mois = ~12000 partitions max
[end] tout fini.
[end] total ingéré: 993422 décisions
[2026-09-10 05:00:01] opendata: (re)démarrage
[start] resume: 12000 partitions déjà faites
[end] tout fini.
[end] total ingéré: 993422 décisions
```

**Le même chiffre, tous les jours, sans jamais rien ajouter.** Le découpage est figé
(« 50 juridictions × 240 mois »), toutes les partitions sont marquées faites, la reprise
n'en rouvre aucune. En prime, `total ingéré: 993422` ne correspond pas au contenu réel de
la table (`985 996`) : **7 426 d'écart, non expliqué**.

**VERDICT 3.6 : `DÉFAUT TROUVÉ` — GRAVE.** Le piège du mandat, mot pour mot : un journal qui
dit « tout fini » alors que rien n'entre depuis 4 mois et demi.

## 3.7 — Deltas DILA : appliqués à J-1

```
jade     applied=JADE_20260909-214416.tar.gz     source=JADE_20260909-214416.tar.gz    ✔ à jour
legi     applied=LEGI_20260909-214416.tar.gz     source=LEGI_20260909-214416.tar.gz    ✔ à jour
kali     applied=KALI_20260909-214416.tar.gz     source=KALI_20260909-214416.tar.gz    ✔ à jour
jorf     applied=JORF_20260909-214416.tar.gz     source=JORF_20260910-002824.tar.gz    ← 1 delta de retard
cass     applied=CASS_20260907-214720.tar.gz     source=CASS_20260907-214720.tar.gz    ✔ à jour
capp     applied=CAPP_20260612-215918.tar.gz     source=CAPP_20260612-215918.tar.gz    ✔ (DILA n'en publie plus)
inca     applied=INCA_20260907-214720.tar.gz     source=INCA_20260907-214720.tar.gz    ✔ à jour
constit  applied=CONSTIT_20260804-220219.tar.gz  source=CONSTIT_20260804-220219.tar.gz ✔ à jour
cnil     applied=CNIL_20260908-213244.tar.gz     source=CNIL_20260908-213244.tar.gz    ✔ à jour
```

**VERDICT 3.7 : `CONFIRMÉ`.** Les 9 fonds DILA sont à J-1 au pire. Le retard JORF d'un delta
se rattrape à la prochaine exécution. `capp` s'arrête au 12/06/2026 parce que DILA ne publie
plus de delta CAPP depuis cette date — vérifié sur le listing amont, ce n'est pas une panne
locale.

## 3.8 — Les tâches planifiées tournent-elles ?

```
### PROD (46.225.190.237)
0 5 * * * /opt/justicelibre/scripts/scrape_increments_daily.sh          → tourne, CEDH KO tous les jours
30 4 * * * /opt/justicelibre/scripts/judilibre_sync_daily.sh            → tourne (log 04:33 aujourd'hui)
0 6 * * * /opt/justicelibre/scripts/controle_couverture_daily.sh        → tourne (06:03 aujourd'hui)
40 4 * * * controle_juridictions.py --fond judiciaire                   → tourne (04:40 aujourd'hui)
0 5 * * * controle_judilibre.py                                         → tourne (05:15 aujourd'hui)
### AL-UZZA (46.224.173.253)
0 4 * * * /opt/justicelibre/scripts/dila_update_daily.sh                → tourne (04:00 aujourd'hui)
0 3 * * 0 backup_dbs.sh · 0 4 * * * indexnow_ping.py
0 5 * * * /opt/justicelibre/scripts/opendata_update.sh                  → tourne, +0 depuis 4 mois
20 4 * * * sync_constit.py --apply                                      → « Rien à faire : la base servie est à jour »
30 4 * * * controle_juridictions.py --fond jade
```

**VERDICT 3.8 : `DÉFAUT TROUVÉ` — MOYEN.** Toutes les tâches tournent. Deux mentent par
omission : `scrape_increments_daily.sh` classe l'échec CEDH « non-fatal » et conclut « DONE » ;
`opendata_update.sh` conclut « tout fini ». Aucun de ces deux échecs ne produit de code de
sortie non nul, donc aucune supervision ne peut les voir.

---

# POINT 4 — Accessibilité de bout en bout

## 4.1 — Ce que `/api/search` interroge réellement

### COMMANDE

```
curl -s -A "Mozilla/5.0" --get --data-urlencode 'q=doute serieux quant a la legalite' "https://justicelibre.org/api/search"
```

### SORTIE BRUTE (11 h 32 UTC, après le déploiement `doctrine`)

```
'sources_queried': ['dila', 'ariane', 'admin', 'cedh', 'cjue', 'doctrine']
```

**`legi`, `jorf`, `kali`, `cnil`, `opendata`, `cass`, `capp`, `inca`, `constit`, `annuaire`
ne sont interrogés par aucune recherche du site.**

Contre-épreuve avec une phrase littérale d'un article en base :

```
### phrase exacte tirée de CT L321-1
{'total': 0, 'per_source': {'ariane': 0, 'admin': 0, 'dila': 0, 'cedh': 0, 'cjue': 0},
 'sources_queried': ['dila', 'ariane', 'admin', 'cedh', 'cjue'], 'sources_no_result': ['dila']}
### q="CJA L521-1"          → 5 résultats, 0 article de loi
### q="article 1240 du code civil" → 20 résultats, 0 article de loi
### q="code du travail L1152-1"    → 5 résultats, 0 article de loi
```

Le front-end est pourtant **prêt** à afficher la source : `search.html` contient
`const ORDRE_SOURCES = ['dila', 'admin', 'ariane', 'legi', 'cedh', 'cjue'];`. La branche
`legi` n'est jamais alimentée.

`/api/law` n'est utilisé que pour enrichir les références détectées **à l'intérieur** d'une
décision affichée (fonction `resolveLaw` + `POST /api/law/batch`), pas pour chercher.

**VERDICT 4.1 : `DÉFAUT TROUVÉ` — GRAVE.** Le site s'annonce comme un moteur de
« jurisprudence + lois » (`llms.txt` l. 70 : « Recherche jurisprudence + lois ») ; on ne
peut pas y chercher une loi. On ne peut que la demander par son numéro exact.

## 4.2 — Pourquoi LEGI est aussi absent de `search_all` (MCP)

Le MCP, lui, interroge bien `legi` — mais il échoue :

```json
"source_errors": {"legi": {"error": "Source legi en échec : entrepôt de données injoignable sur
 /v1/search/legi — ReadTimeout: délai dépassé (> 15s)", "error_category": "upstream", "retryable": true}},
"warning": "1 source(s) en échec — résultats potentiellement incomplets"
```

Diagnostic (le réseau et l'entrepôt sont hors de cause) :

```
=== entrepot en local ===
legi q=harcelement              HTTP=200 t=0.096903s  total= 532
legi q=formation adaptation     HTTP=200 t=0.412004s  total= 5218
legi q=refere suspension        HTTP=200 t=0.054540s  total= 314
=== depuis la PROD via wireguard ===
prod->wh legi : HTTP=200 t=0.054547s
prod->wh legi : HTTP=200 t=0.039072s
prod->wh health : HTTP=200 t=0.007376s
=== requete en langage naturel ===
requete nue "tous les efforts de formation et d adaptation" : HTTP=200 t=19.482448s
=== requete elargie par le thesaurus ===
HTTP=500 {"error": "OperationalError: fts5: syntax error near \"OR\""}
```

**Deux défauts distincts, tous deux mesurés :**
1. Une requête en langage naturel avec mots vides (`tous`, `les`, `de`, `et`) prend **19,5 s**
   sur `legi_articles_fts` → dépasse le délai de 15 s → LEGI disparaît silencieusement.
2. La requête élargie par le thésaurus produit une syntaxe FTS5 invalide et **HTTP 500**
   (`fts5: syntax error near "OR"`), non gérée côté entrepôt.

**VERDICT 4.2 : `DÉFAUT TROUVÉ` — GRAVE.**

## 4.3 — Fonds servis par l'entrepôt

```
{"status": "ok", "fonds": ["legi", "jade", "jorf", "kali", "cnil", "opendata"], …}
```

`cass`, `capp`, `inca`, `constit`, `doctrine`, `enrichment`, `external_codes` restent
**hors de `FONDS`** — le constat n° 4 du premier audit **n'est pas corrigé**.
Latences mesurées (toutes saines) :

```
jade      HTTP=200 t=1.001143s
jorf      HTTP=200 t=0.403399s
kali      HTTP=200 t=0.300654s
cnil      HTTP=200 t=0.014925s
opendata  HTTP=200 t=0.795164s
```

Les 985 996 décisions TA/CAA locales sont donc **techniquement cherchables en 0,8 s** — mais
par personne, puisque ni le site ni le MCP n'interrogent ce fond. Test de bout en bout :

```
=== texte témoin en base (opendata.db) ===
DCE_504479_20260420|Section du Contentieux|2026-04-20|…23, 25 et 25 bis avenue de Matignon…
=== entrepôt, fond opendata ===
{"fond": "opendata", "total": 2, "returned": 2, … "id": "DCE_504479_20260420" …}   ✔
=== site /api/search ===
 total= 9 {'ariane': 2, 'admin': 2, 'dila': 3, 'cedh': 2, 'cjue': 0, 'doctrine': 0}
    admin DCE_504479_20260420 Conseil d'État 2026-04-20
```

La décision remonte — mais par la source `admin`, qui est l'**API live du Conseil d'État**,
pas la copie locale. La copie locale de 14 Go reste un doublon inerte.

## 4.4 — Doctrine : branchée pendant l'audit

À 10 h 15 UTC, `per_source` ne mentionnait pas `doctrine`. À 11 h 32 :

```
### q="avis CADA communication documents administratifs"
 total= 32 {'ariane': 5, 'admin': 10, 'dila': 4, 'cedh': 5, 'cjue': 3, 'doctrine': 5}
 queried= ['dila', 'ariane', 'admin', 'cedh', 'cjue', 'doctrine']
### q="Défenseur des droits discrimination handicap scolarisation"
 total= 15 {'ariane': 0, 'admin': 8, 'dila': 0, 'cedh': 2, 'cjue': 0, 'doctrine': 5}
```

Contenu réel de `doctrine.db` :

```
=== source_id ===
ariane_crp|9138      (conclusions des rapporteurs publics)
bofip|6301           (BOFiP — DGFiP)
cada|60941           (avis CADA)
ctn|15029            (code du travail numérique)
ddd|15864            (Défenseur des droits)
```

**Bonne nouvelle mesurée** : CADA, DDD, BOFiP et rapporteurs publics sont désormais
cherchables depuis le site. **Réserves** : (a) aucun outil MCP ne les atteint — il n'existe
aucun `search_doctrine` / `search_cada` / `search_ddd` dans les 31 outils exposés ;
(b) la table `sources` ne documente que 2 des 5 sources (`ctn`, `cada`) — BOFiP, DDD et
rapporteurs publics n'ont ni licence, ni URL, ni date de synchronisation déclarées ;
(c) 57 % des dates sont non ISO (§ 6.5).

## 4.5 — Sommaires : toujours pas indexés

```
CREATE VIRTUAL TABLE decisions_fts USING fts5(
    id UNINDEXED, titre, juridiction, solution, numero, formation, text, numero_rg_norm,
    content='decisions', content_rowid='rowid'
)
```

`sommaire` n'y est pas. Test réel, décision `JURITEXT000042579779` :

```
=== sommaire ===
ASSURANCE RESPONSABILITE - Garantie - Conditions - Déclaration préalable de chaque mission - Omission - Portée
=== le texte contient-il « ASSURANCE RESPONSABILITE » ? ===
SELECT instr(text,'ASSURANCE RESPONSABILITE') → 0
=== recherche site ===
{"query_normalized": "\"ASSURANCE RESPONSABILITE Garantie Conditions\"", "total": 0,
 "per_source": {"dila": 0, …}, "sources_queried": ["dila"]}
```

**VERDICT 4.5 : `CONFIRMÉ` (défaut du matin non corrigé) — GRAVE.** Le sommaire, c'est-à-dire
la partie de l'arrêt que la Cour de cassation rédige **exprès** pour être citée, reste
introuvable par la recherche.

## 4.6 — Couverture de l'index FTS (aucune ligne manquante)

```
SELECT COUNT(*) FROM decisions_fts_docsize;   → 2596246
SELECT COUNT(*) FROM decisions;               → 2596246
(ariane_fts_docsize, ariane_decisions, cedh_fts_docsize, cedh_decisions, cjue_fts_docsize, cjue_decisions)
→ 144019|144019|76062|76062|44689|44689
```

**VERDICT 4.6 : `CONFIRMÉ`.** Zéro rowid manquant dans les 4 index FTS de la prod. Aucune
décision « introuvable pour cause de rowid absent ».

## 4.7 — Routes publiques réellement exposées

```
184:        if parsed.path == "/api/search":
186:        if parsed.path == "/api/expand":
188:        if parsed.path == "/api/decision":
190:        if parsed.path == "/api/law":
192:        if parsed.path == "/api/law/versions":
194:        if parsed.path == "/api/recent":
567:        if self.path == "/api/law/batch":
```

et l'index public :

```
{"service": "justicelibre public REST API", "endpoints": {
 "GET /api/search?q=&juridiction=&lieu=&limit=": "Recherche fédérée dans 5 sources",
 "GET /api/decision?source=&id=", "GET /api/law?code=&num=&date=",
 "GET /api/law/versions?code=&num=", "POST /api/law/batch", "POST /api/token"}}
```

**`/api/recent` et `/api/expand` existent et ne sont pas documentés.** « Recherche fédérée
dans 5 sources » est en outre périmé depuis le branchement de `doctrine` (6 sources).

```
=== endpoints testés ===
kali 404 · jorf 404 · cnil 404 · legi 404 · opendata 404 · doctrine 404 · annuaire 404 · stats 404 · recent 200
```

---

# POINT 5 — Les correctifs de ce matin tiennent-ils ?

## 5.a — Fuite de descripteurs de l'entrepôt : `CONFIRMÉ` (corrigée)

```
=== 100 requêtes /v1/law séquentielles ===
AVANT: 25 0
APRES: 6 0
APRES search 6 fonds: 6 0
lsof: 4
=== 240 requêtes /v1/search en parallèle (6 fonds × 40 vagues) ===
T0 fd= 28 conn= 0
T1 (240 req paralleles) fd= 21 conn= 0
fd reels: 19
```

Aucune croissance ; on redescend même. **Réserve honnête :** le service a été redémarré à
08 h 40 UTC (`ActiveEnterTimestamp = Thu 2026-09-10 08:40:05 UTC`, `NRestarts = 0`), donc
mon test porte sur un processus jeune de 10 minutes. Une fuite lente ne serait pas visible
sur cette fenêtre. **Verdict : le correctif tient sur 340 requêtes ; à re-tester dans 48 h.**

## 5.b — `/api/recent` : `CONFIRMÉ` (corrigé) avec un défaut annexe

```
=== /api/recent?limit=5 ===
{"results": [{"id": "6aa13877195da062e0d12fd4", "source": "dila", "title": "Cour de cassation,
 2026-09-09, n° 24-22.624", "juridiction": "Cour de cassation", "date": "2026-09-09", …}]}
=== juridiction=tcom ===
n= 20 Counter({'Tribunal de commerce de Créteil': 19, 'Tribunal de commerce de Bordeaux': 1})
=== juridiction=zzzz ===
{"error": "juridiction inconnue : zzzz (attendu : appel, cassation, constit, tcom, tj)"}
```

HTTP 200, filtre appliqué, filtre pur, valeur inconnue rejetée explicitement. **Corrigé.**

**Défaut annexe trouvé — deux vocabulaires incompatibles pour le même filtre :**

```
=== /api/search ===
cass       ok n= 3
cassation  filtres_ignores= [{'valeur': 'cassation', 'raison': 'valeur inconnue (attendu : admin, ca,
           caa, cass, ce, cedh, cjue, constit, europ, judic, ta, tcom, tj) ; filtre NON appliqué'}]
appel      filtres_ignores= [… 'valeur inconnue' …]
=== /api/recent ===
appel      ok n=3
cassation  → 504 après 60 s
ce/caa/ta/cedh/cjue → ERREUR (juridiction inconnue)
```

`/api/search` veut `cass` et `ca` ; `/api/recent` veut `cassation` et `appel`. Le même mot
est valide ici et invalide là. Pire : `/api/search?juridiction=cassation` **rend quand même
des résultats** (`n=3`) en signalant seulement dans `filtres_ignores` que le filtre n'a pas
été appliqué — une usagère qui ne lit pas ce champ croit avoir filtré.

## 5.c — `limit=100` : `CONFIRMÉ` (corrigé), et le plafond de 50 localisé

```
=== limit=100 juridiction=tcom ===
total= 105646 total_exact= True total_rendus= 100 len(results)= 100
per_source= {'ariane': 0, 'admin': 0, 'dila': 100, 'cedh': 0, 'cjue': 0}
```

**100 résultats rendus pour `limit=100`.** La division par deux est levée sur source unique
(`token_server.py:513` : `lps = limit if len(srcs_effectives)==1 else max(5, limit//2)`).

**Le plafond de 50 est à `token_server.py:343`** :

```
343:            limit = max(1, min(int(qs.get("limit", ["24"])[0]), 50))   ← /api/recent
433:        limit = max(1, min(limit, 100))                                ← /api/search
```

Vérification :

```
=== /api/recent limit=100 ===
len= 50 champ limit= 50
```

**Il n'est documenté nulle part** — `/api/recent` n'apparaît même pas dans l'index
`/api/`. À décharge, la réponse renvoie `"limit": 50`, donc le plafond est au moins visible
dans le corps.

**Défaut annexe : le mur des 60 s.** Sur 5-6 sources, `limit=100` met **54,9 à 58,1 s**,
et `nginx` coupe à 60 s :

```
=== limit=100 (5 sources) === [HTTP:200 58.147055s]
=== limit=200 (5 sources) === [HTTP:200 55.508403s]
=== rejeu limit=100 (chaud) === [200 54.903034s]
   total= 190 exact= False rendus= 100 len= 100 {'ariane': 50, 'admin': 50, 'dila': 40, 'cedh': 0, 'cjue': 50}
=== /api/recent?juridiction=cassation === error code: 504 [HTTP:504 60.193002s]
```

## 5.d — Recherche à froid : `EXAGÉRÉ` — le correctif est insuffisant

Le correctif de ce matin (commentaire dans `search_api.py:785-789`) a donné aux sources
locales le budget entier de 12 s, en constatant « 1er appel 6,4 s → timeout ». **Le budget
reste dépassé.** Mesure, requêtes jamais posées, mesurées à froid :

```
### juridiction=tj, q=contrat
{"total": 0, "total_exact": false, "total_rendus": 0,
 "per_source": {"dila": 0, …}, "sources_queried": ["dila"], "sources_no_result": ["dila"], "results": []}
[HTTP:200 time:15.966923]

### juridiction=tcom, q=contrat
{"total": 0, … "sources_no_result": ["dila"], "results": []}
[HTTP:200 time:22.158700]
```

Puis, les mêmes requêtes une fois l'index en cache :

```
run1 tj    total= 294239 rendus= 3 no_result= [] [200 7.505012s]
run1 tcom  total=  32375 rendus= 3 no_result= [] [200 8.984282s]
run2 tj    total= 294239 rendus= 3 no_result= [] [200 3.752478s]
run3 tcom  total=  32375 rendus= 3 no_result= [] [200 2.268869s]
```

**Une recherche « contrat » dans les 717 756 tribunaux judiciaires rend zéro résultat, sans
erreur, en HTTP 200, si elle est la première du jour.** 294 239 décisions correspondent.

Le phénomène n'est pas limité au premier appel. Même requête, quatre passages consécutifs :

```
run 1 37 {'ariane': 10, 'admin': 10, 'dila': 7, 'cedh':  0, 'cjue': 10} ['cedh']
run 2 40 {'ariane': 10, 'admin': 10, 'dila': 0, 'cedh': 10, 'cjue': 10} ['dila']
run 3 40 {'ariane': 10, 'admin': 10, 'dila': 0, 'cedh': 10, 'cjue': 10} ['dila']
run 4 47 {'ariane': 10, 'admin': 10, 'dila': 7, 'cedh': 10, 'cjue': 10} []
```

**37, 40, 40, 47 résultats pour une requête identique.** Et un troisième cas, spontané :

```
=== filtre cass, q=pourvoi, limit=40 ===
(à froid)  n= 0 Counter()
run 1 total= 914866 n= 40 {'Cour de cassation': 40} no_result= []
```

### Le champ `sources_no_result` est mal nommé

```
search_api.py:887:        "sources_no_result": slow_sources,
search_api.py:805:    slow_sources = [s for s in sources_to_query if s in timed_out]
```

Le code interne l'appelle `slow_sources` et le commentaire dit clairement
« Sources qui ont timeout ou erreur (DISTINCT des sources qui ont juste rien trouvé) ».
Mais le nom exporté au public est `sources_no_result`. **Une usagère — ou un LLM — qui lit
`sources_no_result: ["dila"]` conclut « le fonds judiciaire ne contient rien sur ce sujet ».
C'est l'inverse : il en contenait 294 239 et n'a pas eu le temps de répondre.**
Réponse à la question du mandat : oui, le champ est renseigné ; non, il ne dit pas ce que
son nom annonce.

**VERDICT 5.d : `DÉFAUT TROUVÉ` — CRITIQUE.** Pour une requérante sans avocat qui cherche un
précédent, un zéro silencieux est le pire défaut possible, et c'est celui qui reste.

## 5.e — Le champ `total` : `CONFIRMÉ` (corrigé), mais reste ambigu

```
=== source unique (dila) ===
total= 105646 total_exact= True total_rendus= 100 len(results)= 100
=== 5 sources ===
total= 190 total_exact= False total_rendus= 100 len(results)= 100
```

`total` n'est plus `len(results)` : sur source unique c'est le vrai total en base
(`total_exact: true`) ; sur plusieurs sources c'est `len(merged)`, drapeau `total_exact:
false`, et `total_rendus` donne le nombre réellement rendu. **Le correctif tient.**

**Réserve :** `total = 190` pour une requête qui a des centaines de milliers de
correspondances reste une demi-vérité pour qui ne lit pas `total_exact`. Et le MCP emploie
la convention **inverse** — voir § 6.8.

---

# POINT 6 — Ce que personne n'a regardé

## 6.1 — Doublons

| table | ECLI en double | lignes | numéro+date en double | lignes |
|---|---|---|---|---|
| `decisions` (prod) | **99 336** | **198 940** | non mesuré (trop long) | — |
| `jade_decisions` | 0 | 0 | 1 393 | 2 786 |
| `cass_decisions` | 10 | 20 | 160 | 334 |
| `capp_decisions` | 0 | 0 | 508 | 1 038 |
| `inca_decisions` | 4 | 8 | 570 | 1 179 |
| `constit_decisions` | 0 | 0 | 65 | 130 |
| `opendata_decisions` | 1 | 2 | 6 188 | 12 376 |
| `cedh_decisions` | 45 | 90 | 5 785 | 11 590 |
| `cjue_decisions` | 28 | 56 | 5 | 10 |

```
SELECT COUNT(*), SUM(k) FROM (SELECT COUNT(*) k FROM decisions WHERE ecli IS NOT NULL AND ecli<>'' GROUP BY ecli HAVING k>1);
→ 99336|198940
```

**198 940 lignes de `decisions` portent un ECLI partagé — soit 58,3 % des 341 337 lignes qui
ont un ECLI.** C'est la double entrée Judilibre (id hexadécimal) / JURITEXT connue, et le
code la connaît (`search_api.py:800`, `_dedupe_ecli`). Mais la déduplication est faite
**après** le tirage des `limit_per_source` résultats :

```
=== limit=100, 5 sources ===
per_source= {'ariane': 50, 'admin': 50, 'dila': 40, 'cedh': 0, 'cjue': 50}
```

`dila` rend 40 au lieu de 50 : 10 ont été supprimés après coup. Conséquence pratique :
`per_source` sous-déclare, `total` sur-déclare, et la pagination par `offset` saute ou
répète des décisions d'une page à l'autre.

**Doublon dans une seule réponse** (mesuré) :

```
q="25 bis avenue de Matignon", limit=20
n= 9  ids distincts= 8  doublons= {'DCE_504479_20260420': 2}
```

La même décision `DCE_504479_20260420` apparaît deux fois, toutes deux étiquetées `admin`.
La déduplication ne couvre pas la source `admin`.

## 6.2 — Dates impossibles

```
capp_decisions : dates <1800 = 6
     <1800: '0201-02-24' x1
     <1800: '0201-04-04' x1
     <1800: '0201-04-07' x1
     <1800: '0201-06-28' x1
     <1800: '0201-08-24' x1
jade_decisions : dates >aujourd'hui = 1  →  2999-01-01
cass / inca / constit / opendata / cedh / cjue : 0 date impossible, 0 date vide
legi_articles : date_debut <1800 = 657 ; date_debut future hors sentinelle = 10 075
```

Les `0201-xx-xx` de CAPP sont des `2001` amputés d'un chiffre : ces 6 arrêts sont
inaccessibles à tout filtre de date. Les 10 075 `date_debut` futures de LEGI (hors
sentinelles `2999-01-01` et `2222-02-22`) correspondent à des entrées en vigueur
programmées réelles (2027-2029) — **attendu**, pas un défaut.

## 6.3 — Textes vides ou très courts

| table | texte vide | texte < 200 car. | % vide |
|---|---|---|---|
| `cedh_decisions` | **22 340** | 0 | **29,4 %** |
| `cnil_deliberations` | **16 947** | 1 292 | **63,1 %** |
| `cjue_decisions` | **3 709** | 4 | 8,3 % |
| `legi_articles` | 1 225 | 500 731 | 0,07 % |
| `jade_decisions` | 181 | 380 | 0,03 % |
| `capp_decisions` | 47 | 42 | 0,06 % |
| `cass_decisions` | 1 | 6 | ~0 % |
| `inca` / `constit` / `opendata` | 0 | 0 | 0 % |

CEDH et CNIL sont les deux fonds où « la décision est en base » ne veut pas dire « on peut
la lire ». Pour CEDH, c'est le même endpoint HUDOC en panne qui est en cause (§ 3.3).

## 6.4 — Encodage

```
legi_articles      : 0
jade_decisions     : 0
cass_decisions     : 0
capp_decisions     : 0
constit_decisions  : 0
opendata_decisions : 0
cnil_deliberations : 0
inca_decisions     : 1
cedh_decisions     : 1
cjue_decisions     : 1
```

(motifs testés : `Ã©`, `Ã¨`, `â€`, `Ã `)

**VERDICT 6.4 : `CONFIRMÉ` — rien à signaler.** 3 lignes sur 4,5 millions. L'encodage est sain.

## 6.5 — Dates non ISO dans `doctrine.db`

```
=== formats de date ===
ISO|30073
autre|61404
vide|15796
=== 5 dates « autres » ===
01/04/1999
01/04/2004
01/06/2023
01/07/1999
01/12/1994
```

**57,2 % des 107 273 documents de doctrine portent une date au format `JJ/MM/AAAA`**, donc
non triable ni filtrable par date (un `MIN/MAX` lexicographique donne `01/04/1999` →
`9/07/2021`, ce qui ne veut rien dire). 15 796 n'ont pas de date du tout. Le fonds vient
d'être branché dans la recherche : ce défaut est désormais visible par les usagers.

Défaut connexe : la table `sources` ne décrit que 2 des 5 sources réellement présentes.

```
ctn|Code du travail numérique|Ministère du Travail (SocialGouv)|https://code.travail.gouv.fr|MIT (open source)|2026-05-10 17:04:57
cada|Avis et conseils de la CADA|Commission d'accès aux documents administratifs|https://www.cada.fr|Licence Ouverte 2.0 (Etalab)|2026-09-08 18:07:24
```

BOFiP (6 301 docs), DDD (15 864) et conclusions des rapporteurs publics (9 138) n'ont ni
licence déclarée, ni URL source, ni date de synchronisation.

## 6.6 — Écritures anormales de juridiction

`data/juridictions_map.json` est daté du 8 septembre 2026, construit sur 113 écritures JADE
et 333 écritures judiciaires, et **contre-vérifié à l'aveugle**. Il est bon. Contenu :

```
ecritures_anormales: {
 "Cour administrative d'appel": "sans ville ; 639 décisions de 2013, toutes 09BX/12BX = Bordeaux (CAA33)",
 "CAA de VERSAILLESS": "faute de frappe ; 16 décisions 17VE = Versailles (CAA78)",
 "Cour administrative d'appel de Montpellier": "cour inexistante ; n° 99MA01704 = Marseille (CAA13).
   Ne JAMAIS en dériver un alias « CAA de Montpellier »",
 "Section du Contentieux": "formation du Conseil d'État, pas une juridiction (CE)",
 "Tribunal administratif Montpellier ordonnance du president": "type de décision accolé ; TA de Montpellier (TA34)"}
libelles_affiches: {"cc": "Cour de cassation",
 "Tribunal judiciaire de tj2b033": "Tribunal judiciaire de Bastia",
 "Tribunal judiciaire de tj2a004": "Tribunal judiciaire d'Ajaccio"}
```

Ces écritures échappent-elles aux filtres ? **Non**, test réel :

```
=== filtre juridiction=cass, q=pourvoi, limit=40 ===
total= 914866 n= 40 {'Cour de cassation': 40}
=== une ligne dont la colonne vaut littéralement 'cc' ===
69455d3375782d5f06bb012f|cc|2025-12-19|25-21.540
=== la même via /api/decision ===
{'id': '69455d3375782d5f06bb012f', 'juridiction': 'Cour de cassation', 'date': '2025-12-19', 'numero': '25-21.540'}
```

Le code `cc` est bien traduit à l'affichage et couvert par le filtre. Le contrôle quotidien
est en place et vert :

```
2026-09-09 04:40 judiciaire: 570 écritures, toutes connues de la carte ✅
2026-09-10 04:40 judiciaire: 570 écritures, toutes connues de la carte ✅
```

**VERDICT 6.6 : `CONFIRMÉ`** — c'est le point le mieux tenu du système. **Réserve** :
`Section du Contentieux` est documenté comme « formation du CE, 2 décisions » côté JADE,
alors que dans `opendata.db` **c'est la valeur de `juridiction_name` de décisions du CE**
(`DCE_504479_20260420|Section du Contentieux|2026-04-20`). La carte ne couvre pas `opendata`.

## 6.7 — `/api/decision` : une source rend 200 sur un identifiant bidon

```
dila 404 · admin 404 · cedh 404 · cjue 404 · legi 404 · kali 404 · jorf 404 · cnil 404
ariane 200
### corps
{"error": "Texte intégral indisponible pour cette décision ArianeWeb."}
```

Le corps est un objet `error` correct, mais le code HTTP est 200 : incohérent avec les 8
autres sources, et un client qui teste le statut croit avoir réussi.

## 6.8 — Paraphrases et demi-vérités dans la documentation lue par les LLM

`about_justicelibre()` est l'outil que tout assistant appelle en premier. Ses chiffres :

| affirmation de `about_justicelibre` | mesuré ce jour | écart |
|---|---|---|
| « ~1,3 M décisions » (fonds DILA judiciaire) | **2 596 246** | ÷ 2 |
| « tribunaux judiciaires (~68 000, surtout depuis 2023) » | **717 756** | **× 10,5** |
| « tribunaux de commerce (~40 000) » | **175 152** | **× 4,4** |
| « ~270 000 décisions du Conseil d'État » (ArianeWeb) | **144 019** | ÷ 1,9 |
| « ~146 000 textes » (LEGI) | **153 566** | ÷ 1,05 |
| « ~570 000 décisions JADE » | **570 890** | exact |
| « ~76 000 documents HUDOC FR » | **76 062** | exact |
| « ~44 000 arrêts CJUE » | **44 689** | exact |

La ligne la plus dangereuse est « tribunaux judiciaires (~68 000, surtout depuis 2023) » :
un assistant qui lit cela déconseille au justiciable de chercher un jugement de TJ, alors
que la base en contient **717 756**.

**Contradiction interne** — `about_justicelibre` dit de `search_all` :

> « fan-out … tri par pertinence BM25 avec bonus d'autorité (CE/Cass/CEDH > CAA > TA/CA) »

et, dans `hiérarchie_autorité` : « `search_all` applique automatiquement un bonus d'autorité
lors du tri ». Or la docstring de `search_all` elle-même dit :

> « **Il n'y a pas de score global, et c'est délibéré.** … Les résultats sont donc
> ENTRELACÉS … Un champ `score` valant 1.0 était renvoyé pour tous les résultats : il ne
> mesurait rien … Supprimé le 30 août 2026. »

**Les deux documentations se contredisent frontalement.** Le correctif du 30 août n'a pas
été répercuté dans `about_justicelibre`.

**Omissions** : `about_justicelibre` ne dit nulle part qu'ArianeWeb est gelé depuis
décembre 2025, que 49,3 % des arrêts CEDH de 2026 manquent, que 29,4 % des arrêts CEDH n'ont
pas de texte, que l'open data TA/CAA local est gelé au 27 avril, ni que KALI / JORF / CNIL /
opendata / doctrine sont hors de `search_all`.

### `search_decisions_citing` : `total` ne veut pas dire total

```json
{"code":"CT","num":"L1152-1","total":12,
 "per_source":{"dila":19303,"jade":99,"cedh":2,"cjue":0},
 "decisions":[ …12 entrées… ]}
```

`total: 12` = nombre **rendu**. `per_source` = nombre **existant**. 12 ≠ 19 404.
Dans un outil dont la seule fonction est de compter les décisions qui citent un article,
c'est la définition même de la demi-vérité : littéralement, `total` est le total de la liste
renvoyée ; en lecture, il dit « douze décisions citent l'article L. 1152-1 du code du travail ».

Et la convention est **inversée** par rapport à l'API REST du site, où `per_source` compte
les résultats rendus et `total`/`total_exact` le stock en base. Deux conventions opposées
pour deux champs du même nom, dans le même produit.

## 6.9 — Le fichier fantôme

```
ls -l /opt/justicelibre/*.db
-rw-r--r-- 1 root root 0 Apr 25 09:22 /opt/justicelibre/jade.db
```

Un `jade.db` de **0 octet** à la racine, à côté du vrai `/opt/justicelibre/dila/jade.db`
(16,7 Go). C'est la signature exacte du piège que le mandat signale : un `sqlite3` lancé sur
un chemin inexistant crée un fichier vide. Tout script qui se tromperait de chemin lirait
« 0 décision » sans erreur. À supprimer (après sauvegarde), pas par moi : je suis en lecture
seule.

---

# (i) TABLEAU FONDS × CANAL

Mesuré le 10/09/2026 entre 09 h et 11 h 40 UTC.
✅ = mesuré et fonctionnel · ⚠️ = fonctionnel avec réserve mesurée · ❌ = mesuré non fonctionnel · — = sans objet

| Fonds | Volume mesuré | Fraîcheur (MAX date) | (a) cherchable sur le site | (b) filtrable | (c) texte intégral | (d) MCP |
|---|---|---|---|---|---|---|
| `decisions` — cass. | 1 092 908 | 2026-09-09 | ✅ | ✅ `cass` | ✅ | ✅ `search_judiciaire_libre` |
| `decisions` — cours d'appel | 601 960 | 2026-08-31 | ✅ | ✅ `ca` | ✅ | ✅ |
| `decisions` — TJ / TGI / TI | 717 756 | 2026-09-04 | ⚠️ 0 résultat à froid (16 s) | ✅ `tj` | ✅ | ✅ |
| `decisions` — T. com. / TAE | 175 152 | 2026-09-01 | ⚠️ 0 résultat à froid (22 s) | ✅ `tcom` | ✅ | ✅ |
| `decisions` — Cons. constit. | 7 388 | 2026-07-31 | ✅ | ✅ `constit` | ✅ | ✅ `search_cc` |
| `decisions.sommaire` | 33 % des lignes | — | ❌ **hors index FTS** | — | ✅ (lisible) | ❌ |
| `ariane_decisions` | 144 019 | **2025-12-12** | ✅ | ✅ `ce` | ⚠️ 200 sur id bidon | ✅ `search_conseil_etat` |
| `jade_decisions` | 570 890 | (delta J-1) | ✅ via `admin` | ✅ `ta`/`caa`/`ce` | ✅ | ✅ `search_admin` |
| `cedh_decisions` | 76 062 | 2026-09-03 (**trou mai-juil.**) | ⚠️ timeout aléatoire | ✅ `cedh` | ⚠️ 29,4 % sans texte | ✅ `search_cedh` |
| `cjue_decisions` | 44 689 | 2026-09-09 | ✅ | ✅ `cjue` | ⚠️ 8,3 % sans texte | ✅ `search_cjue` |
| `legi_articles` | 1 834 128 | 2026-08-27 | ❌ **jamais interrogé** | ❌ | ⚠️ `/loi/` ment sur l'état | ⚠️ `search_legi` timeout > 15 s |
| `legi_textes` | 153 566 | — | ❌ | ❌ | ⚠️ LEGITEXT direct uniquement | ✅ `resolve_law_number` |
| `jorf_textes` | 1 273 923 | (delta J-1) | ❌ | ❌ | ⚠️ 22 % sans corps | ✅ `search_jorf` |
| `kali_textes` | 351 279 | (delta J-1) | ❌ | ❌ | ⚠️ 11,1 % sans texte | ✅ `search_kali` |
| `cnil_deliberations` | 26 852 | (delta J-2) | ❌ | ❌ | ❌ **63,1 % sans texte** | ✅ `search_cnil` |
| `opendata_decisions` (TA/CAA local) | 985 996 | **2026-04-27** | ❌ (l'API live y supplée) | — | ✅ (entrepôt seul) | ❌ |
| `cass_decisions` (al-uzza) | 145 347 | (delta J-3) | ❌ **hors `FONDS`** | ❌ | ❌ | ❌ |
| `capp_decisions` | 73 050 | 2026-06-12 (amont) | ❌ **hors `FONDS`** | ❌ | ❌ | ❌ |
| `inca_decisions` | 387 640 | (delta J-3) | ❌ **hors `FONDS`** | ❌ | ❌ | ❌ |
| `constit_decisions` (al-uzza) | 7 388 | 2026-08-04 | ❌ hors `FONDS` (mais recopié en prod) | — | — | ✅ via la prod |
| `doctrine.docs` — CADA | 60 941 | ~08/09/2026 | ✅ **depuis ce jour** | ❌ | ✅ | ❌ aucun outil |
| `doctrine.docs` — DDD | 15 864 | non déclarée | ✅ **depuis ce jour** | ❌ | ✅ | ❌ aucun outil |
| `doctrine.docs` — BOFiP | 6 301 | non déclarée | ✅ **depuis ce jour** | ❌ | ✅ | ❌ aucun outil |
| `doctrine.docs` — rapporteurs publics | 9 138 | non déclarée | ✅ **depuis ce jour** | ❌ | ✅ | ❌ aucun outil |
| `doctrine.docs` — code trav. numérique | 15 029 | 2026-05-10 | ✅ **depuis ce jour** | ❌ | ✅ | ❌ aucun outil |
| Annuaire (~75 000 adresses) | 2,37 Mo statique | — | ✅ `annuaire.html` (client) | ✅ (client) | ✅ | ✅ `search_annuaire` |

---

# (ii) DÉFAUTS CLASSÉS

## CRITIQUE

**C-1 — Toute page `/loi/` annonce « en vigueur » un article abrogé.**
`ssr.py:1101`. 26 articles abrogés/transférés/morts-nés testés, 26 annoncés « Article en
vigueur depuis le … ». 75 312 articles sur 231 772 (32,5 %) des codes servis n'ont aucune
version en vigueur et rendent cette page. Aggravants : `ssr.py:1041` déclare
`legislationLegalForce: "PartiallyInForce"` au lieu de `NotInForce` ; le `note` renvoyé par
l'API n'est pas rendu (`ssr.py` ne l'utilise nulle part) ; `llms.txt` l. 42-43 publie cette
URL comme LA citation d'un article de loi. *Correctif minimal : conditionner la phrase à
`etat == 'VIGUEUR'` et afficher « Article ABROGÉ le {date_fin} » sinon.*

**C-2 — La recherche rend 0 résultat, en HTTP 200, sans erreur, quand une source dépasse 12 s.**
`search_api.py:766-793` (budget), `search_api.py:887` (`sources_no_result`).
Mesuré : `q=contrat&juridiction=tj` → 16,0 s → `total: 0` alors que 294 239 décisions
correspondent ; `juridiction=tcom` → 22,2 s → `total: 0` ; même requête rejouée 4 fois →
37 / 40 / 40 / 47 résultats. Le correctif de ce matin (budget porté à 12 s) est insuffisant.
Aggravant : le champ exporté s'appelle `sources_no_result` alors que la variable interne
s'appelle `slow_sources` — il fait lire « ce fonds n'a rien » là où il faut lire « ce fonds
n'a pas répondu ».

**C-3 — Le scraper CEDH échoue tous les jours depuis le 20 avril 2026 ; trois mois de 2026 à zéro.**
`scripts/scrape_increments_daily.sh` (étiquette « non-fatal ») et le coupe-circuit de
`scrape_cedh.py`. 104 exécutions, 0 succès. Mai, juin, juillet 2026 : 0 arrêt. Août : 7.
Septembre : 4. 463 arrêts manquants sur 939. Cause amont : l'endpoint de conversion HUDOC
renvoie `HTTP 204`. L'alerte existe et est correcte (`couverture_alertes.txt`) mais n'est
lue par personne depuis quatre mois.

## GRAVE

**G-1 — LEGI n'est cherchable par aucun canal utilisable.**
Côté site : `sources_queried` ne contient jamais `legi` ; aucun article de loi ne remonte
jamais, même pour `q="article 1240 du code civil"`. Côté MCP : `search_legi` échoue en
`ReadTimeout > 15 s` — mesuré, une requête en langage naturel prend **19,5 s** sur
`legi_articles_fts` (le réseau et l'entrepôt sont hors de cause : 33-55 ms, 0,02-0,4 s).
`search.html` contient pourtant déjà `ORDRE_SOURCES = [… 'legi' …]`.

**G-2 — L'entrepôt renvoie HTTP 500 sur une requête élargie par le thésaurus.**
`{"error": "OperationalError: fts5: syntax error near \"OR\""}` — l'exception SQL remonte
brute au client au lieu d'un 400 explicite.

**G-3 — Open data TA/CAA local gelé au 27 avril 2026, avec un journal qui dit « tout fini ».**
`scripts/opendata_update.sh`. Le fichier `opendata.db` n'a pas bougé depuis le 29 août.
Le découpage « 50 juridictions × 240 mois » est figé et toutes les partitions sont marquées
faites. Le journal annonce en outre `993422` décisions là où la table en compte `985996`.

**G-4 — ArianeWeb gelé au 12 décembre 2025 ; l'indicateur de fraîcheur mesure la mauvaise chose.**
Zéro décision de 2026. `couverture.log` affiche `ariane fraîcheur — 2026-09-09`, qui est la
date de moisson et non la date des décisions. `scrape_ariane.py` reprend à l'id 243 481 alors
que `MAX(ariane_num) = 325 793`. *(Le plancher, lui, est en cours de correction : `MIN` déjà
descendu de 95 000 à 55 000.)*

**G-5 — `decisions.sommaire` toujours hors de l'index FTS.**
Défaut signalé ce matin, non corrigé. Vérifié une seconde fois de façon indépendante :
`instr(text, 'ASSURANCE RESPONSABILITE') = 0` et la recherche du site rend 0.

**G-6 — `search_decisions_citing` annonce `total: 12` là où `per_source` dit 19 404.**
Convention inverse de celle de l'API REST du même produit.

**G-7 — `about_justicelibre` sous-estime les TJ d'un facteur 10 et se contredit sur le tri.**
« tribunaux judiciaires ~68 000 » contre **717 756** mesurés ; « tribunaux de commerce
~40 000 » contre **175 152** ; « ArianeWeb ~270 000 » contre **144 019**. Et « tri par
pertinence BM25 avec bonus d'autorité » est démenti par la docstring de `search_all`
elle-même (« il n'y a pas de score global, et c'est délibéré », correctif du 30 août 2026).

**G-8 — 22 340 arrêts CEDH (29,4 %) et 16 947 délibérations CNIL (63,1 %) sans aucun texte.**
« En base » n'y veut pas dire « lisible ».

**G-9 — Quatre fonds ré-ingérés restent hors de `FONDS`.**
`cass` (145 347), `capp` (73 050), `inca` (387 640), `constit` (7 388) sur al-uzza :
`{"fonds": ["legi","jade","jorf","kali","cnil","opendata"]}`. Défaut n° 4 du premier audit,
non corrigé.

**G-10 — Chiffres de citation à l'état brut : ECLI absent dans 86,85 % de `decisions`,
92,70 % de `jade`, 96,40 % de `opendata`, 99,99 % de `capp`.**
L'ECLI est l'identifiant pérenne d'une décision ; sans lui, une citation n'est pas
vérifiable automatiquement.

## MOYEN

**M-1 — 198 940 lignes de `decisions` à ECLI dupliqué (58,3 % des lignes qui en ont un).**
La déduplication (`search_api.py:800`) intervient après le tirage : `per_source` sous-déclare
(40 rendus pour 50 demandés), `total` sur-déclare, et la pagination par `offset` saute ou
répète des décisions. Un doublon a même survécu dans une réponse unique
(`DCE_504479_20260420` × 2, source `admin` non couverte par la dédup).

**M-2 — Deux vocabulaires incompatibles pour le filtre `juridiction`.**
`/api/search` attend `cass`, `ca` ; `/api/recent` attend `cassation`, `appel`. Et
`/api/search?juridiction=cassation` rend quand même des résultats non filtrés, en ne le
signalant que dans `filtres_ignores`.

**M-3 — `/api/recent` et `/api/expand` ne sont pas documentés** dans l'index `/api/`, qui
annonce par ailleurs « Recherche fédérée dans 5 sources » alors qu'il y en a 6 depuis
aujourd'hui. Le plafond de 50 de `/api/recent` (`token_server.py:343`) n'est documenté
nulle part (il figure seulement dans le corps de la réponse, champ `limit`).

**M-4 — Le mur des 60 s.** `limit=100` sur 5-6 sources met 54,9 à 58,1 s ; nginx coupe à 60 s.
`/api/recent?juridiction=cassation` renvoie **504 après 60,2 s**.

**M-5 — 36 codes (≈ 20 234 articles) sans raccourci, dont 2 en vigueur, et aucune route de
résolution publique.** `/api/law/resolve` n'est pas proxyfié (`404 Endpoint inconnu`) alors
que l'entrepôt l'expose (`warehouse_server.py:945`) et que le MCP s'en sert
(`resolve_law_number`). Aucune page du site ne liste les codes disponibles.

**M-6 — `judilibre_sync.py:188-202` jette 6 champs en dur** — `avocats`, `commissaire_gvt`,
`publi_recueil`, `saisines`, `loi_def` et surtout **`liens_textes`** — pour toutes les
décisions du flux quotidien. Judilibre fournit pourtant les textes visés (champ `visa`,
conservé dans `judilibre_meta` mais non recopié).

**M-7 — `jorf_textes.num_jorf` : 0 ligne sur 1 273 923.** Le champ est lu par
`parse_dila_bulk.py:328` (`META_TEXTE_CHRONICLE/NUM_JORF`) et n'est jamais peuplé.

**M-8 — 57,2 % des dates de `doctrine.db` ne sont pas ISO** (`JJ/MM/AAAA`), 14,7 % sont
absentes. Le fonds vient d'être exposé aux usagers : les dates y sont ininterprétables.
La table `sources` ne documente que 2 des 5 sources (BOFiP, DDD, rapporteurs publics sans
licence, URL ni date de synchronisation).

**M-9 — Deux tâches masquent leur échec.** `scrape_increments_daily.sh` étiquette « (non-fatal) »
et conclut « DONE » ; `opendata_update.sh` conclut « tout fini ». Aucune ne sort en code non
nul : aucune supervision extérieure ne peut les voir.

## MINEUR

**m-1 — Les numéros d'article à espace sont inatteignables par URL.**
`token_server.py:225` : `r"^/loi/([\w.\-]{1,20})/([A-Z]?[\w.\-]{1,40})$"` — `\w` n'accepte pas
l'espace. `/loi/CGI/302%20J` → 404 ; `/loi/LPF/L80%20B` → 404. Message trompeur
(« Endpoint inconnu » au lieu de « article introuvable »).

**m-2 — `/api/decision?source=ariane&id=<bidon>` renvoie HTTP 200** avec un corps `error`,
là où les 8 autres sources renvoient 404.

**m-3 — 6 arrêts de `capp_decisions` datés `0201-xx-xx`** (2001 amputé d'un chiffre) :
inaccessibles à tout filtre de date.

**m-4 — Un `jade.db` de 0 octet** traîne dans `/opt/justicelibre/` à côté du vrai
`/opt/justicelibre/dila/jade.db` (16,7 Go). Piège classique : tout script se trompant de
chemin lirait « 0 décision » sans erreur.

**m-5 — 9 colonnes `*_avant` à 0,00 %** dans `ariane_decisions` (137 605 lignes) : reliquat
d'une campagne d'enrichissement, jamais nettoyé.

**m-6 — 10 633 lignes ArianeWeb (7,8 %) sans date, sans juridiction, sans numéro** —
invisibles à tout filtre. Mesure prise pendant une moisson active, à re-mesurer à froid.

**m-7 — `Section du Contentieux`** est traité comme une anomalie côté JADE
(`juridictions_map.json`) mais c'est la valeur normale de `juridiction_name` pour les
décisions du CE dans `opendata.db`. La carte des juridictions ne couvre pas `opendata`.

**m-8 — Écart de 7 426 entre le journal `opendata` (`993422`) et la table (`985996`).**

---

# (iii) CE QUE JE N'AI PAS PU MESURER

1. **Taux de remplissage exacts de `decisions` (prod), hors `ecli`.** `INVÉRIFIABLE` dans ma
   fenêtre : la requête d'agrégat sur 11 colonnes non indexées d'une table de 54 Go a dépassé
   3 000 s. Seul `ecli` a pu être compté exactement (13,15 %), grâce à `idx_decisions_ecli`
   qui est couvrant. Les taux `[échantillon]` que j'ai obtenus pour `titre`, `sommaire`,
   `president`, `rapporteur`, `resume`, `liens_textes` sont **rétractés** (§ 2.0) : la méthode
   par blocs s'est révélée fausse d'un facteur 2,3 à 9 sur les tables comparables.
2. **Doublons `numero + date` dans `decisions`.** `INVÉRIFIABLE` : même raison.
3. **Sonde ArianeWeb de 20 identifiants au-dessus de `MAX(ariane_num)`.** Non exécutée
   délibérément : deux moissons ArianeWeb tournaient sur la prod pendant l'audit (lancées à
   08 h 47, ajoutant ~7 000 lignes en 45 min). Sonder en parallèle aurait doublé la charge
   sur le Conseil d'État sans rien apprendre de neuf.
4. **Comparaison avec Judilibre par l'API PISTE.** `INVÉRIFIABLE` sans clé : aucune variable
   `PISTE_CLIENT_ID` / `PISTE_CLIENT_SECRET` lisible en lecture seule. **Mais** le contrôle
   quotidien du serveur (`controle_judilibre.py`) le fait déjà et j'ai recopié sa sortie —
   c'est une source de second rang, que je n'ai pas pu contre-vérifier.
5. **Comparaison avec HUDOC directement.** `INVÉRIFIABLE` de ma position : je n'ai pas
   interrogé HUDOC. Le chiffre « 939 arrêts FR annoncés pour 2026 » vient du script du
   serveur, pas de ma propre mesure. La conclusion « trou de 3 mois » repose en revanche sur
   ma mesure directe en base (0 ligne mai-juillet 2026), qui est solide.
6. **Comparaison avec curia (CJUE) et la liste des deltas JADE.** Les deltas JADE ont bien
   été vérifiés contre `https://echanges.dila.gouv.fr/OPENDATA/JADE/` ; curia n'a pas été
   interrogé — je me repose sur le contrôle interne (`cjue 2026 : 947/946`), donc source de
   second rang.
7. **Stabilité de la correction de fuite de descripteurs sur la durée.** Le service a été
   redémarré 10 minutes avant mon test. 340 requêtes sans croissance, c'est un bon signe,
   pas une preuve. À re-tester dans 48 h.
8. **Volumes ArianeWeb définitifs.** Les chiffres ont bougé pendant l'audit (136 526 →
   144 019). Tous datés dans le rapport ; aucun ne doit être repris sans sa date.
9. **Effet réel des 546 articles servis avec un `etat` non-VIGUEUR par la stratégie 1.**
   J'ai vérifié CGI 302 J en direct ; je n'ai pas testé les 545 autres un par un.
10. **`enrichment.db` et `external_codes.db`** (97 Mo et 4,8 Mo sur al-uzza) : hors mandat
    explicite, non ouverts.

---

## Note finale

Deux de mes propres mesures se sont révélées fausses à la première tentative — le « trou
cassation 2025 » (§ 3.2) et l'échantillonnage par blocs (§ 2.0). Les deux ont été attrapées
en appliquant la règle « quand une mesure surprend, refaire autrement avant de conclure ».
Je les laisse dans le rapport avec leur rétractation, parce qu'une méthode d'audit qui cache
ses propres erreurs ne vaut pas mieux qu'un journal qui écrit « (non-fatal) ».

Rien dans ce rapport n'a été écrit, modifié, supprimé ou redémarré sur les serveurs.
Toutes les requêtes SQL ont été passées en `mode=ro` ou `sqlite3 -readonly`.
