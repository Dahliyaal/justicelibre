# Audit adversarial du « rattrapage » justicelibre.org

**Date de l'audit : 10 septembre 2026**
**Auditeur : agent indépendant, mandat adversarial, lecture seule**
**Règle appliquée : aucune conclusion sans commande exécutée et sortie brute recopiée.**

---

## Résumé exécutif (à lire en premier)

Les mesures de **volumétrie** sont, dans l'ensemble, honnêtes : les chiffres annoncés
sont exacts ou très proches du réel. Le filtre `juridiction` fonctionne et est pur.

Mais l'affirmation centrale — « on a rattrapé les bases **ET leur accessibilité** » —
est **fausse au moment de l'audit**, et pas d'un peu :

1. **L'entrepôt (`justicelibre-warehouse`) est en panne totale.** Tous les
   endpoints `/v1/*` renvoient `500 {"error": "unable to open database file"}`.
   Cause racine trouvée : **fuite de descripteurs de fichiers** — 1 023 fd ouverts
   pour une limite de 1 024, dont 510 sur `legi.db` et 494 sur `legi.db-wal`.
2. **Conséquence utilisateur, vérifiée sur le site public** : toutes les pages
   `https://justicelibre.org/loi/...` renvoient **HTTP 404 « Article introuvable »**.
   `CJA L521-1` (le référé-suspension) est inaccessible. **Aucun article de loi
   n'est servi.**
3. **`/api/recent` est cassé par un bug de code distinct** :
   `NameError: name '_debut_lisible' is not defined`, à la ligne 388 de
   `token_server.py` — dans le bloc modifié le 9 septembre, c'est-à-dire dans le
   correctif même qui est censé faire l'objet de cette campagne.
4. **Les champs « réparés » du point C ne sont accessibles à personne.** Ils vivent
   dans `cass.db`, `capp.db`, `inca.db`, `constit.db` sur al-uzza ; or ces quatre
   fonds ne figurent **pas** dans la table `FONDS` de l'entrepôt, et la table
   `decisions` de la prod **n'a aucune de ces colonnes**.
5. **`decisions.sommaire` n'est pas indexé** dans `decisions_fts`. Sur un
   échantillon, **69 % des sommaires** contiennent de la matière absente du texte,
   donc introuvable par la recherche.
6. **~40 000 identifiants ArianeWeb vivants ne sont jamais moissonnés** :
   `START_ID = 95_000`, alors que les identifiants 55 000–94 999 répondent
   HTTP 200 avec de vraies décisions du Conseil d'État.

En une phrase : **« rattrapé » veut dire ici « présent dans un fichier .db »,
pas « atteignable par un humain sur le site ».**

---

## A — « Les tribunaux de commerce sont filtrables de bout en bout, 174 418 décisions »

### A.1 — Le filtre est-il appliqué, ou avalé en silence ?

Commande (13 valeurs testées sur l'API publique) :

```
for j in "" tcom cass ca tj constit ce caa ta cedh cjue admin judic; do
  curl -s -A "Mozilla/5.0" "https://justicelibre.org/api/search?q=bail&juridiction=$j&limit=8"
done
```

Puis contrôle de **pureté** à plus fort volume :

```
for j in tcom ca tj cass constit; do
  curl -s -A "Mozilla/5.0" "https://justicelibre.org/api/search?q=societe&juridiction=$j&limit=60"
done
```

Sortie brute (comptage des juridictions rendues) :

```
=== tcom purity (limit 60) ===
n= 30
    17 Tribunal des activités économiques d'Avignon
    11 Tribunal des activités économiques de Nanterre
    2 Tribunal des activités économiques de Lyon
=== ca purity (limit 60) ===
n= 30
    8 Cour d'appel d'Aix-en-Provence
    6 Cour d'appel d'Amiens
    6 Cour d'appel de Lyon
    5 Cour d'appel de Versailles
    1 Cour d'appel de Paris
    1 Cour d'appel de Douai
    1 Cour d'appel d'Angers
    1 Cour d'appel de Basse-Terre
    1 Cour d'appel de Reims
=== tj purity (limit 60) ===
n= 30
    3 Tribunal d'instance d'Angers
    3 Tribunal d'instance de Marseille
    3 Tribunal d'instance d'Auch
    3 Tribunal de grande instance de Paris
    3 Tribunal d'instance de Cholet
    1 Tribunal d'instance de Baugé
    1 Tribunal d'instance d'Illkirch-Graffenstaden
    1 Tribunal d'instance de Mayenne
    1 Tribunal d'instance de Courbevoie
    1 Tribunal d'instance de Paris 1er
    1 Tribunal d'instance d'Avignon
    1 Tribunal d'instance d'Aix-en-Provence
=== cass purity (limit 60) ===
n= 30
    30 Cour de cassation
=== constit purity (limit 60) ===
n= 30
    30 Conseil constitutionnel
```

Contrôle complémentaire sur `tj` (le fonds « Tribunal judiciaire » représente
716 k lignes ; l'échantillon ci-dessus n'en montrait aucune, j'ai donc re-testé) :

```
=== tj q=expulsion ===      n= 20 {'Tribunal': 10, 'Tribunal judiciaire': 10}
=== tj q=divorce ===        n= 20 {'Tribunal': 20}
=== tj q=surendettement === n= 20 {'Tribunal': 20}
=== tj q=bail commercial === n= 20 {'Tribunal': 5, 'Tribunal judiciaire': 15}
```

Et sur `tcom` avec des requêtes jamais posées auparavant :

```
--- q='clause resolutoire' j=tcom ---
n= 5 per_source= {'ariane': 0, 'admin': 0, 'dila': 5, ...}
    Tribunal des activités économiques d'Avignon
    Tribunal des activités économiques de Marseille
    Tribunal des activités économiques de Paris
--- q='nantissement' j=tcom ---
    Tribunal des activités économiques de Paris
    Tribunal de commerce de Bayonne
    Tribunal de commerce d'Amiens
```

**Aucune valeur acceptée n'est ignorée.** `sources_queried` change bien selon la
valeur (`["dila"]` pour tcom/ca/tj/cass/constit, `["cedh"]` pour cedh, `["admin"]`
pour ta/caa…), et la composition des résultats est **100 % pure** dans les cinq
familles judiciaires testées. Une valeur inconnue est explicitement signalée dans
`filtres_ignores` (lu dans `token_server.py` l. 416-419), et non avalée.

### A.2 — Le volume réel

Commande (sur la prod, en lecture seule) :

```
sqlite3 -readonly /mnt/digesta/judiciaire.db  (via python, bornes d'index)
```

Sortie brute :

```
tcom   'Tribunal de commerce '                       129371
tcom   'Tribunal des activités économiques '         45781
tcom   TOTAL = 175152
tj     'Tribunal judiciaire '                        715986
tj     'Tribunal de grande instance '                1585
tj     "Tribunal d'instance "                        180
tj     TOTAL = 717751
ca     "Cour d'appel "                               601960
ca     TOTAL = 601960
cass  cc+Cour de cassation = 1092908
constit = 7388
TOTAL decisions = 2596246
```

Annoncé : 174 418. Mesuré : **175 152** (+734, soit +0,42 %). L'écart s'explique
par la croissance du fonds depuis la mesure d'origine ; le chiffre annoncé est
donc légèrement **sous-estimé**, jamais gonflé.

### VERDICT A : `CONFIRMÉ`

Le filtre `tcom` est réellement appliqué, la famille est pure (commerce + activités
économiques), le volume réel est de 175 152 — le chiffre annoncé était même un peu
en dessous du vrai. Aucune des 13 valeurs testées n'est acceptée puis ignorée.

**Réserve (non signalée par l'auteur, voir F-3)** : la promesse « de bout en bout »
tient pour le filtrage, mais l'API tronque silencieusement le nombre de résultats
de moitié.

---

## B — « La ré-ingestion DILA a traversé les 9 fonds avec zéro échec »

### B.1 — Les 9 fonds

Commande :

```
grep -n -- "-----" /var/log/justicelibre/reingest.log
grep -oE "^\[[a-z]+\]" /var/log/justicelibre/reingest.log | sort | uniq -c
```

Sortie brute :

```
118:[2026-09-08 18:05:49] ----- constit : AVANT
166:[2026-09-08 18:06:09] ----- constit : APRÈS (0 échec(s) sur 21 deltas)
168:[2026-09-08 18:06:09] ----- cnil : AVANT
300:[2026-09-08 18:07:03] ----- cnil : APRÈS (0 échec(s) sur 124 deltas)
302:[2026-09-08 18:07:04] ----- kali : AVANT
341:[2026-09-09 15:27:26] ----- constit : AVANT
345:[2026-09-09 15:27:28] ----- constit : APRÈS (0 échec(s) sur 21 deltas)
347:[2026-09-09 15:27:28] ----- cnil : AVANT
352:[2026-09-09 15:27:31] ----- cnil : APRÈS (0 échec(s) sur 125 deltas)
354:[2026-09-09 15:27:31] ----- kali : AVANT
1061:[2026-09-09 15:32:30] ----- kali : APRÈS (0 échec(s) sur 235 deltas)
1063:[2026-09-09 15:32:36] ----- capp : AVANT
1111:[2026-09-09 15:36:43] ----- capp : APRÈS (0 échec(s) sur 19 deltas)
1113:[2026-09-09 15:36:43] ----- cass : AVANT
1233:[2026-09-09 15:41:59] ----- cass : APRÈS (0 échec(s) sur 52 deltas)
1235:[2026-09-09 15:42:16] ----- inca : AVANT
1378:[2026-09-09 16:00:30] ----- inca : APRÈS (0 échec(s) sur 55 deltas)
1380:[2026-09-09 16:00:37] ----- jade : AVANT
2062:[2026-09-09 16:33:09] ----- jade : APRÈS (0 échec(s) sur 317 deltas)
2064:[2026-09-09 16:36:04] ----- legi : AVANT
3961:[2026-09-09 17:48:42] ----- legi : APRÈS (0 échec(s) sur 424 deltas)
3963:[2026-09-09 17:48:48] ----- jorf : AVANT
5661:[2026-09-09 19:20:54] ----- jorf : APRÈS (0 échec(s) sur 776 deltas)
```

```
=== fonds vus ===
     42 [capp]
    108 [cass]
    128 [cnil]
     46 [constit]
    114 [inca]
    638 [jade]
   1556 [jorf]
    711 [kali]
   1702 [legi]
```

Les 9 fonds sont bien présents et tous ont un « APRÈS » **dans la passe du
9 septembre**. Somme des deltas rejoués : 21+125+235+19+52+55+317+424+776 = **2 024**.

### B.2 — Ce que la formule « zéro échec » cache

**Point n° 1 — la première passe a été interrompue, en silence.**
Ligne 302 : `[2026-09-08 18:07:04] ----- kali : AVANT`. Il n'y a **jamais** de
`----- kali : APRÈS` pour cette passe. Le journal reprend directement à la ligne
341 par `[2026-09-09 15:27:25] ===== RÉ-INGESTION DILA — début`. La passe du
8 septembre est morte au milieu de kali :

```
[2026-09-09 01:31:40]   234 deltas à rejouer
[kali] streaming KALI_20250715-205701.tar.gz…
[kali] DONE. textes=90, errors=0
[kali] streaming KALI_20250716-211907.tar.gz…
[kali] DONE. textes=60, errors=0
[kali] streaming KALI_20250717-220632.tar.gz…
[2026-09-09 15:27:25] ===== RÉ-INGESTION DILA — début ; disque libre 61 Go
```

Sur 234 deltas annoncés, **3 ont été joués** avant l'arrêt. Aucune ligne d'erreur,
aucun `⛔`, aucun `ÉCHOUÉ` : l'interruption ne laisse **aucune trace explicite**.
Un lecteur qui grep `échec` ne la voit pas. Le 2ᵉ passage a bien tout rejoué,
donc le résultat final est correct — mais « la ré-ingestion a traversé les 9 fonds »
décrit **la seconde tentative**, pas la campagne.

**Point n° 2 — « zéro échec » ne compte pas les erreurs d'enregistrement.**
Le compteur « 0 échec(s) sur N deltas » compte les **archives** qui ont planté,
pas les **enregistrements** perdus. Commande :

```
grep -oE "errors=[0-9]+" /var/log/justicelibre/reingest.log | sort | uniq -c
```

Sortie brute :

```
   1891 errors=0
     10 errors=1
      2 errors=3
      2 errors=6
      2 errors=95
```

Détail :

```
2246:[legi] DONE. articles=1750418, textes=289102, errors=95, time=1920s
2287:[legi] DONE. articles=1527, textes=540, errors=1, time=4s
2295:[legi] DONE. articles=5006, textes=928, errors=6, time=10s
2335:[legi] DONE. articles=2971, textes=772, errors=1, time=8s
2881:[legi] DONE. articles=2774, textes=824, errors=1, time=7s
3394:[legi] DONE. articles=3993, textes=488, errors=1, time=6s
3406:[legi] DONE. articles=3599, textes=670, errors=1, time=8s
3825:[legi] DONE. articles=3321, textes=358, errors=3, time=6s
4092:[jorf] DONE. textes=1240915, articles=2679940, corps recomposés=929227, errors=95, time=2592s
4129:[jorf] DONE. textes=315, articles=7642, corps recomposés=301, errors=1, time=6s
4137:[jorf] DONE. textes=441, articles=10454, corps recomposés=323, errors=6, time=9s
4173:[jorf] DONE. textes=295, articles=7031, corps recomposés=275, errors=1, time=6s
4684:[jorf] DONE. textes=412, articles=10336, corps recomposés=386, errors=1, time=8s
5153:[jorf] DONE. textes=213, articles=4929, corps recomposés=199, errors=1, time=4s
5163:[jorf] DONE. textes=221, articles=5038, corps recomposés=205, errors=1, time=5s
5539:[jorf] DONE. textes=150, articles=4504, corps recomposés=142, errors=3, time=4s
```

Total : **108 erreurs côté LEGI + 108 côté JORF = 216 enregistrements en erreur**,
dont **190 dans les deux parses GLOBAUX** (95 + 95), c'est-à-dire dans le cœur du
corpus, pas dans un delta marginal. Le journal ne dit **nulle part** quels
enregistrements ont échoué ni pourquoi : ils sont perdus sans identifiant.

**Détail troublant** : dans le parse global LEGI, le compteur de progression
affiche `0 err` jusqu'au bout, puis `DONE ... errors=95`.

```
  [ 1740000 arts / 289092 textes / 0 err] 923/s  (31.4min)
  [ 1750000 arts / 289102 textes / 0 err] 923/s  (31.6min)
[legi] back-filling titre_text…
[legi] DONE. articles=1750418, textes=289102, errors=95, time=1920s
```

Les 95 erreurs n'apparaissent qu'à la toute fin — un lecteur qui suit la
progression en direct croit à un sans-faute jusqu'à la dernière ligne.

### VERDICT B : `EXAGÉRÉ`

Les 9 fonds ont bien été traversés **lors de la passe du 9 septembre**, et le
compteur de deltas affiche réellement 0 échec sur 2 024 deltas. Mais « zéro échec »
est une **paraphrase trompeuse** du compteur de deltas : 216 enregistrements ont
échoué (dont 190 dans les parses globaux LEGI et JORF), et la première passe du
8 septembre s'est interrompue au milieu de kali sans laisser la moindre trace
d'erreur dans le journal.

---

## C — Les champs « réparés », re-mesurés directement en base

### C.1 — Les comptes

Commande (al-uzza, ouverture en `mode=ro`, existence des fichiers vérifiée par
`ls -l` au préalable) :

```python
print("legi_articles:", q("legi.db","SELECT COUNT(*), SUM(hierarchie IS NOT NULL AND hierarchie!=''), SUM(liens IS NOT NULL AND liens!='') FROM legi_articles"))
print("jorf_textes:",   q("jorf.db","SELECT COUNT(*), SUM(texte...), SUM(id_eli...), SUM(liens...) FROM jorf_textes"))
print("kali_textes:",   q("kali.db","SELECT COUNT(*), SUM(idcc...), SUM(titre...), SUM(date_debut...) FROM kali_textes"))
print("cass_decisions:",q("cass.db","SELECT COUNT(*), SUM(avocat_general...), SUM(form_dec_att...) FROM cass_decisions"))
print("inca_decisions:",q("inca.db","SELECT COUNT(*), SUM(form_dec_att...) FROM inca_decisions"))
print("capp_decisions:",q("capp.db","SELECT COUNT(*), SUM(siege_appel...) FROM capp_decisions"))
print("constit_decisions:",q("constit.db","SELECT COUNT(*), SUM(url_cc...) FROM constit_decisions"))
```

Sortie brute :

```
legi_articles: (1834128, 1084289, 1458938)
jorf_textes: (1273923, 993199, 271544, 446010)
kali_textes: (351279, 300800, 351269, 349888)
cass_decisions: (145347, 100980, 113351)
inca_decisions: (387640, 386062)
capp_decisions: (73050, 69652)
constit_decisions: (7388, 7388)
```

Confrontation avec l'annonce :

| Champ | Annoncé | Mesuré | Écart |
|---|---|---|---|
| `legi_articles` total | 1 834 024 | **1 834 128** | +104 |
| `legi_articles.hierarchie` | 1 084 254 | **1 084 289** | +35 |
| `legi_articles.liens` | 1 458 889 | **1 458 938** | +49 |
| `jorf_textes` total | 1 273 923 | **1 273 923** | **0** |
| `jorf_textes.texte` | 993 199 | **993 199** | **0** |
| `jorf_textes.id_eli` | 271 544 | **271 544** | **0** |
| `jorf_textes.liens` | 446 006 | **446 010** | +4 |
| `kali_textes` total | ~351 279 | **351 279** | **0** |
| `kali_textes.idcc` | 300 800 | **300 800** | **0** |
| `kali_textes.titre` | 351 269 | **351 269** | **0** |
| `kali_textes.date_debut` | 349 888 | **349 888** | **0** |
| `cass.avocat_general` | 100 980 | **100 980** | **0** |
| `cass.form_dec_att` | 113 351 | **113 351** | **0** |
| `inca.form_dec_att` | 386 062 | **386 062** | **0** |
| `capp.siege_appel` | 69 652 | **69 652** | **0** |
| `constit.url_cc` | 7 388 | **7 388** | **0** |

**16 chiffres sur 16 sont exacts ou supérieurs au chiffre annoncé.** Les écarts
positifs sur LEGI et JORF correspondent aux deltas quotidiens joués depuis
(les bases ont été réécrites le 10/09 à 04:00, cf. `ls -l`).

### C.2 — Le contenu est-il exploitable, ou du remplissage ?

C'était la partie du mandat la plus susceptible de retourner un faux succès.
Elle n'en retourne pas. Sortie brute :

```
########## legi_articles.hierarchie / liens ##########
ID LEGIARTI000006850357
  hierarchie: [{"id":"LEGISCTA000006109057","titre":"TITRE Ier : Dispositions relatives aux organismes génétiquement modifiés autres que les plantes, les semences, les plants et les animaux destinés à l'alimentation humaine","debut":"1994-01-19","fin":"2007-03-20"},{"id":"LEGISCTA000006129313","titre":"Chapitre I
  liens     : [{"cidtexte":"JORFTEXT000000161523","datesignatexte":"1992-07-13","id":"JORFTEXT000000161523","naturetexte":"LOI","nortexte":"RESX9100142L","numtexte":"92-654","sens":"source","typelien":"CITATION","libelle":"Loi 92-654 1992-07-13 art. 11"},...
ID LEGIARTI000006850359
  liens     : ... "libelle":"Loi 92-654 1992-07-13 art. 22"...
ID LEGIARTI000006850361
  liens     : ... "libelle":"Décret n°94-46 du 5 janvier 1994 - art. 11 (Ab)"...
-- distribution des valeurs de liens (echantillon 20000) --
{'contenu': 17962, 'vide': 2038}
-- distribution hierarchie (echantillon 20000) --
{'contenu': 10845, 'vide': 9155}
```

Test spécifique du faux succès « `[]` partout » :

```
legi_liens_JSON_vide|0
legi_hier_JSON_vide|0
liens_JSON_vide|0
id_eli_non_url|0
```

**Zéro ligne** — ni dans LEGI ni dans JORF — ne porte un JSON vide `[]` ou `{}`, et
**0 ligne** de JORF n'a un `id_eli` qui ne soit pas une vraie URL. Le scénario du
faux succès (« champ rempli avec `[]` partout ») est donc explicitement écarté,
mesure à l'appui. Les valeurs sont réelles :

```
########## jorf_textes.id_eli / liens ##########
  ('JORFTEXT000000870911', 'https://www.legifrance.gouv.fr/eli/arrete/1989/12/20/ECOC8900137A/jo/texte', '[{"cidtexte":"JORFTEXT000000879161",...,"naturetexte":"DIRECTIVE_EURO",...,"typelien":"APPLICATION",...')
  ('JORFTEXT000000870507', 'https://www.legifrance.gouv.fr/eli/arrete/1999/1/4/ECOX9850062A/jo/texte', '[{"cidtexte":"JORFTEXT000000886460",...,"naturetexte":"LOI","numtexte":"78-17",...')
  ('JORFTEXT000000877795', 'https://www.legifrance.gouv.fr/eli/decret/1998/9/18/MEAC9800088D/jo/texte', '[...')
```

Les autres champs :

```
########## kali_textes ##########
  ('KALICONT000005635097', '2075', 'Convention collective nationale des centres immatriculés de conditionnement...', '')
  ('KALICONT000005635179', '1001', 'Convention collective nationale des médecins spécialistes qualifiés...', '')
  ('KALICONT000005635186', '207', "Convention collective nationale de travail de l'industrie des cuirs et peaux du 6 juin 201", '')
 idcc distincts: (421,)
 date_debut min/max: ('0003-09-01', '5489-12-30')

########## cass avocat_general / form_dec_att ##########
  ('JURITEXT000019425557', 'Mme Prada Bordenave (commissaire du gouvernement)', 'Cour de cassation')
  ('JURITEXT000019425560', 'Mme Prada Bordenave (commissaire du gouvernement)', 'Cour de cassation')
  ('JURITEXT000019425563', 'Mme Prada Bordenave (commissaire du gouvernement)', 'Cour de cassation')
  ('JURITEXT000019025171', 'M. Aldigé', "Conseil de prud'hommes d'Angers")
 avocat_general distincts: (1652,)
 form_dec_att distincts: (73204,)
 top form_dec_att: [("Cour d'appel de Paris", 5231), ("Cour d'appel d'Aix-en-Provence", 2029), ("Cour d'appel de Versailles", 1857), ("Cour d'appel de Rennes", 1012), ("Cour d'appel de Lyon", 944)]

########## inca form_dec_att ##########
 top: [("Cour d'appel de Paris", 22844), ("Cour d'appel d'Aix-en-Provence", 11655), ("Cour d'appel de Versailles", 8484), ("Cour d'appel de Lyon", 4784), ("Cour d'appel de Douai", 4661)]

########## capp siege_appel ##########
 top: [('PARIS', 9268), ('VERSAILLES', 5425), ('LYON', 5302), ('ANGERS', 3830), ('LIMOGES', 3774), ('BASTIA', 3657)]

########## constit url_cc ##########
  ('CONSTEXT000017667265', 'http://www.conseil-constitutionnel.fr/decision/1993/931615an.htm')
  ('CONSTEXT000017667266', 'http://www.conseil-constitutionnel.fr/decision/1993/931616an.htm')
  ('CONSTEXT000017667267', 'http://www.conseil-constitutionnel.fr/decision/1993/931566an.htm')
 url_cc distincts: (7354,)
```

Les `url_cc` du Conseil constitutionnel ne sont pas des liens morts — testés :

```
http://www.conseil-constitutionnel.fr/decision/1993/931615an.htm  final=200 url=https://www.conseil-constitutionnel.fr/decision/1993/931615an.htm
http://www.conseil-constitutionnel.fr/decision/1993/931616an.htm  final=200 url=https://www.conseil-constitutionnel.fr/decision/1993/931616an.htm
```

Aucun champ n'est du remplissage : 1 652 avocats généraux distincts, 73 204 valeurs
distinctes de `form_dec_att`, 7 354 URL distinctes pour 7 388 décisions, des JSON
LEGI/JORF structurés et non vides.

### C.3 — Deux défauts de contenu que personne n'avait signalés

**(a) `kali_textes.date_debut` contient des dates impossibles.**
Min = `0003-09-01`, max = `5489-12-30`. Quantification :

```
=== kali dates aberrantes (hors 1900-2030) ===
35
=== kali date_debut vides ===
1391
=== top valeurs ===
2022-01-01|5292
2016-01-01|5217
2025-01-01|4219
2024-01-01|4210
2019-01-01|3855
```

35 lignes sur 349 888, soit 0,01 % : **marginal, mais réel**. Le compte
« 349 888 date_debut non vides » est donc littéralement exact mais compte
35 valeurs inutilisables. Ce n'est pas une faute grave ; c'est une illustration
du fait que « non vide » ≠ « exploitable », et le mandat demandait de le vérifier.

**(b) `form_dec_att` ne contient pas ce que son nom annonce.**
Le nom signifie « formation de la décision attaquée ». Le contenu mesuré est le
**nom de la juridiction** attaquée (« Cour d'appel de Paris », « Conseil de
prud'hommes d'Angers »), pas une formation (chambre, section). Un usager qui
filtrerait sur « formation » à partir de ce champ serait induit en erreur. À
signaler dans la documentation, pas à corriger en base.

Plus troublant, l'échantillon `cass_decisions` fait apparaître trois lignes où
`avocat_general` vaut `'Mme Prada Bordenave (commissaire du gouvernement)'` et
`form_dec_att` vaut `'Cour de cassation'`. Le « commissaire du gouvernement » est
une fonction de la **juridiction administrative**, pas de la Cour de cassation, et
une décision de la Cour de cassation ne peut pas avoir la Cour de cassation pour
juridiction attaquée. Ces lignes sont vraisemblablement des décisions du **Tribunal
des conflits** rangées dans `cass.db`. **Je n'ai pas mesuré combien** de lignes sont
dans ce cas : sur ce point précis, `INVÉRIFIABLE` en l'état.

### VERDICT C : `CONFIRMÉ`

Les 16 comptes annoncés sont exacts ou légèrement dépassés — aucun n'est gonflé.
Le contenu est réel et exploitable (JSON structurés, 0 `[]` dans JORF, milliers de
valeurs distinctes) : ce n'est pas du remplissage. Deux réserves mineures et non
signalées : 35 dates impossibles dans `kali.date_debut`, et `form_dec_att` qui
contient une juridiction et non une formation.

**Mais voir le point E : ces champs ne sont servis à personne.**

---

## D — « ArianeWeb : 126 345 → 128 592, soit +2 247, corpus allé jusqu'à son sommet réel »

### D.1 — Le compte et le delta

```
sqlite3 -readonly /mnt/digesta/judiciaire.db "SELECT COUNT(*) FROM ariane_decisions;"
total ariane: (128595,)
```

Répartition par jour de moisson :

```
2026-09-10|3
2026-09-09|2247
2026-09-05|2591
2026-09-04|2349
2026-09-03|2908
2026-09-02|4317
2026-09-01|2
2026-08-30|10
```

**Le +2 247 est exact au décimal près** : 2 247 lignes portent `fetched_at` du
9 septembre. Le total est de 128 595 et non 128 592 parce que 3 décisions de plus
sont entrées le 10 au matin. `128 592 − 2 247 = 126 345` : la valeur de départ
annoncée est cohérente.

### D.2 — Les nouvelles décisions ont-elles un vrai texte ?

C'était le piège à vérifier : 2 247 lignes vides compteraient pareil.

```
SELECT COUNT(*), SUM(text IS NULL OR text=''), SUM(length(text)<400), MIN(length(text))
FROM ariane_decisions WHERE fetched_at>='2026-09-08';

2250|0|0|2001
```

**Zéro texte vide, zéro texte court, le plus petit fait 2 001 caractères.** Les
2 247 (+3) nouvelles décisions ont toutes un texte réel.

### D.3 — Le corpus est-il vraiment allé jusqu'à son sommet ?

Le plus haut identifiant réellement stocké :

```
sqlite3 -readonly ... "SELECT ariane_num FROM ariane_decisions ORDER BY CAST(ariane_num AS INT) DESC LIMIT 6;"
325793
325792
325791
325749
325722
325721
--- bas ---
95000
95001
95002
```

J'ai sondé ArianeWeb moi-même (≤ 2 req/s, User-Agent du projet). **Contrôle de
validité de la sonde d'abord** — des identifiants connus comme présents en base :

```
id=325793  http=200 bytes=9395
id=325792  http=200 bytes=37035
id=325721  http=200 bytes=8355
id=200000  http=200 bytes=9104
id=150000  http=200 bytes=3663
```

La sonde est donc fiable. Au-dessus du sommet stocké :

```
id=325794  http=404      id=327000  http=404
id=325800  http=404      id=327500  http=404
id=325850  http=404      id=329500  http=404
id=325900  http=404      id=330200  http=404
id=326000  http=404      id=330600  http=404
id=326200  http=404      id=330748  http=404
id=326500  http=404      id=330749  http=404
```

Et bien au-delà :

```
id=331000 http=404   id=332000 http=404   id=335000 http=404
id=340000 http=404   id=350000 http=404   id=360000 http=404
id=380000 http=404   id=400000 http=404
```

**Le plafond haut est bien atteint.** 325 793 est le dernier identifiant vivant ;
rien n'a été laissé au-dessus.

Nuance de vocabulaire, cependant : **330 749 n'est pas un « sommet »**, c'est
l'identifiant où le balayage s'est arrêté après 5 000 vides consécutifs. Le vrai
sommet du corpus est 325 793. Dire « le corpus est allé jusqu'à son sommet réel
(~330 749) » confond le plafond de balayage et le contenu.

### D.4 — Ce que l'affirmation ne dit pas : le PLANCHER n'a jamais été exploré

`scrape_ariane.py` fixe :

```python
START_ID = 95_000
```

Et le commentaire qui le justifie :

```
#   id=50000    → 404
#   id=100000   → 200
```

Le raisonnement saute de 50 000 à 100 000 sans rien tester entre les deux. J'ai
testé. Sortie brute :

```
id=94999   http=200 bytes=4204
id=94000   http=200 bytes=6496
id=90000   http=200 bytes=11400
id=80000   http=200 bytes=5486
id=70000   http=200 bytes=4110
id=60000   http=200 bytes=5382
id=50000   http=404 bytes=28
id=30000   http=404 bytes=28
id=10000   http=404 bytes=28
```

Affinage du plancher :

```
id=51000   http=404      id=55000   http=200 bytes=3047
id=53000   http=404      id=57000   http=200 bytes=2798
                         id=59000   http=200 bytes=11021
```

Le corpus vivant commence donc vers **54 000**, pas 95 000. Et le contenu est réel
— je suis allé chercher l'identifiant 70 000 :

```
Conseil d'État N° 43282 ECLI:FR:CESSR:1983:43282.19830506 Mentionné au tables du
recueil Lebon Section du Contentieux de Bresson, président M. Chéramy, rapporteur
M. Dutheillet de Lamothe, commissaire du gouvernement Lecture du 6 mai 1983
REPUBLIQUE FRANCAISE AU NOM DU PEUPLE FRANCAIS VU LA REQUETE SOMMAIRE, ENREGISTREE
AU SECRETARIAT DU CONTENTIEUX DU CONSEIL D'ETAT LE 18 JUIN 1982...
```

Ce n'est pas un déchet : c'est un arrêt de **Section du contentieux**, **mentionné
aux tables du recueil Lebon**, du 6 mai 1983 — exactement le type de décision qu'on
cite. Il n'est pas en base et ne le sera jamais tant que `START_ID` vaut 95 000.

**Environ 40 000 identifiants (≈ 54 000 → 94 999) ne sont jamais interrogés.**
Le même défaut que celui réparé en haut (le checkpoint bloqué dans un trou) existe,
inaperçu, en bas — et il est de la même famille : une borne codée en dur, justifiée
par une sonde trop grossière.

### D.5 — Complément non demandé : le corpus ArianeWeb est figé au 12 décembre 2025

```
MAXDATE|2025-12-12
apres2026|0
```

```
---TOP-DATES---
2025-12-12|5
2025-12-11|16
2025-12-10|20
2025-12-09|6
2025-12-08|3
2025-12-05|15
```

**Zéro décision de 2026** dans `ariane_decisions`, sur 128 595 lignes. La plus
récente date du 12 décembre 2025, soit **9 mois avant l'audit**.

Il faut être juste sur l'imputation : ce n'est **pas** une défaillance de la
moisson. J'ai vérifié en D.3 que 325 793 est le dernier identifiant vivant chez
ArianeWeb et que tout ce qui est au-dessus répond 404 jusqu'à 400 000. C'est
**ArianeWeb lui-même** qui n'a rien publié depuis décembre 2025. Les 2 247
décisions entrées le 9 septembre sont donc du **rattrapage de trous anciens**, pas
des décisions nouvelles — nuance que l'affirmation d'origine n'énonce pas.

Point de vocabulaire à corriger : le site étiquette `"source": "ariane"` des
résultats qui ne viennent pas de cette table. Exemple mesuré — une recherche
`juridiction=ce` a rendu un résultat `ariane | 2026-05-22 | 515399` ; or :

```
SELECT ariane_num, date FROM ariane_decisions WHERE numero='515399';
(aucune ligne)
```

Ce résultat ne sort pas du corpus ArianeWeb local. L'étiquette de source est donc
inexacte, ce qui rend impossible, pour un usager, de savoir d'où vient ce qu'il lit.

### VERDICT D : `EXAGÉRÉ`

Le delta (+2 247) est exact, les 2 247 nouvelles décisions ont bien un texte réel
(0 vide, minimum 2 001 caractères), et le plafond haut est réellement atteint —
325 793 est le dernier identifiant vivant, rien au-dessus jusqu'à 400 000.

Mais « le corpus est allé jusqu'à son sommet réel » ne vaut que pour le **haut**.
Le **bas** n'a jamais été exploré : `START_ID = 95_000` laisse dehors ~40 000
identifiants dont j'ai vérifié qu'au moins une partie répond 200 avec de vraies
décisions du Conseil d'État (dont un arrêt de Section mentionné aux tables). Et
« 330 749 » désigne le plafond de balayage, pas un sommet de corpus. Enfin, les
2 247 décisions gagnées sont du rattrapage de trous anciens : le corpus ne contient
**aucune décision de 2026** (D.5).

---

## E — L'accessibilité réelle : « rattrapé » veut-il dire « atteignable » ?

C'est ici que l'affirmation s'effondre.

### E.1 — L'entrepôt est en panne totale, en ce moment même

Test depuis la **prod**, avec l'URL et la clé réellement utilisées par le service
(`Environment=JL_WAREHOUSE_URL=http://10.8.0.2:8001`, lu dans `systemctl cat
justicelibre-token`) :

```
JL_WAREHOUSE_URL=http://10.8.0.2:8001 python3 -c "... httpx.get(.../v1/law?code=CPC&num=145) ..."
```

Sortie brute :

```
URL= http://10.8.0.2:8001
500 {"error": "unable to open database file"}
```

Balayage de tous les fonds :

```
/v1/law?code=CJA&num=L521-1              500 {"error": "unable to open database file"}
/v1/law?code=CESEDA&num=L611-1           500 {"error": "unable to open database file"}
/v1/count/legi                           500 {"error": "unable to open database file"}
/v1/count/jade                           500 {"error": "unable to open database file"}
/v1/count/jorf                           500 {"error": "unable to open database file"}
/v1/count/kali                           500 {"error": "unable to open database file"}
/v1/count/cass                           400 {"error": "unknown fond: cass"}
```

**Tous les fonds servis sont morts.** (Le `400` sur `cass` est un autre problème,
voir E.4.)

### E.2 — La cause racine : fuite de descripteurs de fichiers

Le processus tourne depuis le 8 septembre 18:06 :

```
    PID                  STARTED     ELAPSED CMD
 874068 Tue Sep  8 18:06:42 2026  1-13:44:59 /usr/bin/python3 -u /opt/justicelibre/warehouse/warehouse_server.py
```

Comptage des descripteurs et de la limite :

```
=== nb fd ===
1023
=== limites ===
Max open files            1024                 524288               files
=== repartition ===
    510 /opt/justicelibre/dila/legi.db
    494 /opt/justicelibre/dila/legi.db-wal
     12 /opt/justicelibre/dila/jade.db
      2 socket:[1295911]
      1 socket:[1295912]
      1 /opt/justicelibre/dila/legi.db-shm
      1 /opt/justicelibre/dila/jade.db-wal
      1 /opt/justicelibre/dila/jade.db-shm
      1 /dev/null
```

**1 023 fd sur une limite de 1 024.** Le processus est saturé : toute nouvelle
tentative d'ouverture échoue, ce que SQLite rapporte exactement comme
`unable to open database file`.

Le mécanisme est lisible dans le code (`warehouse_server.py`, l. 275-291) :

```python
def _conn(fond: str) -> sqlite3.Connection:
    """Return a thread-local read-only SQLite connection for the given fond."""
    ...
    pool = getattr(_tls, "pool", None)
    if pool is None:
        pool = {}
        _tls.pool = pool
    conn = pool.get(fond)
    if conn is None:
        db_path = DB_DIR / FONDS[fond]["db"]
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0, check_same_thread=False)
```

Le « pool » est **thread-local**. Le serveur HTTP crée un thread par requête ; à la
mort du thread, la connexion SQLite n'est **jamais fermée**. Chaque requête sur un
fond nouveau pour ce thread ouvre donc 2 fd de plus (le `.db` et le `-wal`), qui ne
sont jamais rendus. Le compteur monte jusqu'à 1 024 et le service meurt — sans
alarme, sans redémarrage, sans que rien dans le journal de ré-ingestion ne le dise.

Le nom `pool` dans le code est trompeur : ce n'est pas un pool, c'est une fuite.

### E.3 — Conséquence vérifiée sur le site public

Le `hierarchie` / `liens` de LEGI **n'est servi par aucune route**, parce
qu'aucune route de loi ne répond. Test sur le site public :

```
curl -s -A "Mozilla/5.0" "https://justicelibre.org/api/law?code=CPC&num=145"
{"error": "Erreur interne — entrepôt indisponible."}
```

```
curl -s "https://justicelibre.org/loi/CJA/L521-1"
[http=404]
Article CJA L521-1 introuvable -JusticeLibre Article introuvable L'article L521-1
du CJA n'a pas été trouvé. Vérifie le code (CC, CT, CJA, CASF…) et le numéro
(sans points : R772-8 , pas R.772-8 ). Recherche libre
```

Étendue de la panne :

```
/loi/CJA/L521-2            http=404
/loi/CC/1240               http=404
/loi/CPC/145               http=404
/loi/CESEDA/L611-1         http=404
/loi/CT/L1132-1            http=404
=== /api/recent (temoin) ===
http=500
```

Le message d'erreur affiché à l'usager est **mensonger** : il dit « Vérifie le code
et le numéro », c'est-à-dire il impute la faute à l'usager, alors que le service
est en panne. `CJA L521-1` (le référé-suspension) et `CC 1240` (la responsabilité
civile) ne sont pas des articles exotiques.

Le journal de la prod confirme la cascade :

```
Sep 10 08:01:24 PatrologiaLatina python3[1489749]: [INFO] httpx: HTTP Request: GET http://10.8.0.2:8001/v1/law?code=CJA&num=L761-1&date=2023-04-07 "HTTP/1.0 500 Internal Server Error"
Sep 10 08:01:24 PatrologiaLatina python3[1489749]: [ERROR] justicelibre.token_server: ssr law failed
Sep 10 08:01:24 PatrologiaLatina python3[1489749]: Traceback (most recent call last):
Sep 10 08:01:24 PatrologiaLatina python3[1489749]:   File "/opt/justicelibre/sources/warehouse.py", line 379, in sync_get_law
Sep 10 08:01:24 PatrologiaLatina python3[1489749]:     raise HTTPStatusError(message, request=request, response=self)
Sep 10 08:01:24 PatrologiaLatina python3[1489749]: httpx.HTTPStatusError: Server error '500 Internal Server Error' for url 'http://10.8.0.2:8001/v1/law?code=JORFTEXT000000877960&num=1'
```

**Réponse à la question du mandat** : non, le nouveau `hierarchie` / `liens` de
LEGI n'est servi par aucune route de l'API du site. Il n'est servi à personne.

### E.4 — Les champs « réparés » du point C ne sont exposés nulle part

Inventaire des fonds réellement servis par l'entrepôt, contre les bases présentes :

```
=== FONDS servis par le warehouse vs bases presentes ===
 servis  : ['cnil', 'jade', 'jorf', 'kali', 'legi', 'opendata']
 en base : ['capp', 'cass', 'cnil', 'constit', 'doctrine', 'enrichment',
            'external_codes', 'inca', 'jade', 'jorf', 'judiciaire', 'kali',
            'legi', 'opendata']
 EN BASE MAIS JAMAIS SERVIS : ['capp', 'cass', 'constit', 'doctrine',
            'enrichment', 'external_codes', 'inca', 'judiciaire']

=== tailles + comptes des bases NON servies ===
  cass.db          2.64 Go  table=cass_decisions lignes=145347
  capp.db          2.44 Go  table=capp_decisions lignes=73050
  inca.db          7.15 Go  table=inca_decisions lignes=387640
  constit.db       0.17 Go  table=constit_decisions lignes=7388
  doctrine.db      1.44 Go  table=sources lignes=2
```

**Quatre des neuf fonds ré-ingérés (capp, cass, constit, inca) ne figurent pas
dans `FONDS`.** L'entrepôt refuse explicitement de les servir — c'est le
`400 {"error": "unknown fond: cass"}` obtenu en E.1.

Reste la voie de la prod. Schéma réel de la table `decisions` :

```
=== colonnes de prod decisions ===
id nature titre date juridiction solution numero formation ecli president avocats
text sommaire abstrats resume renvois rapporteur commissaire_gvt type_rec
publi_recueil publi_bull nature_qualifiee saisines loi_def liens_textes
numero_rg_norm judilibre_meta
```

Il n'y a **ni `avocat_general`, ni `form_dec_att`, ni `siege_appel`, ni `url_cc`,
ni `demandeur`, ni `defendeur`**. Autrement dit : les 100 980 avocats généraux,
les 113 351 + 386 062 `form_dec_att`, les 69 652 `siege_appel` et les 7 388
`url_cc` « réparés » au point C **n'existent que dans des fichiers .db que rien
n'expose**. Zéro utilisateur peut les atteindre, aujourd'hui ou après réparation
de la fuite de fd.

### E.5 — Les 985 996 décisions d'open data TA/CAA sont-elles cherchables ?

Le compte est exact :

```
sqlite3 -readonly /opt/justicelibre/dila/opendata.db "SELECT COUNT(*) FROM opendata_decisions;"
985996
```

Mais le fond `opendata` passe par l'entrepôt, qui est mort (E.1). Test concret :
j'ai pris une décision réelle en base et cherché une de ses phrases sur le site.

Décision témoin :

```
DTA_1900434_20220630 | Tribunal Administratif de Nice | 2022-06-30 |
  ... 0, 152 boulevard des Jardiniers et 27-29, avenue Auguste Vérola, a été
  calculée en tant qu'entrepôt sans tenir compte de son changement d'affectation
  en parkings ; ...
```

Recherche de `"boulevard des Jardiniers"` sur l'API publique :

```
per_source {'ariane': 1, 'admin': 2, 'dila': 3, 'cedh': 0, 'cjue': 0}
   ariane | Conseil d'État | 360483 | 2013-07-17
   admin | Tribunal Administratif de Nice | 2500792 | 2025-07-02
   admin | Cour administrative d'appel de Marseille | 24MA01982 | 2024-08-29
   dila | Cour de cassation | 14-16633 | 2016-06-28
   ...
```

**La décision témoin ne remonte pas.** Elle est en revanche atteignable par son
identifiant :

```
curl ".../api/search?q=DTA_1900434_20220630"
{"intent": "dce_id", "per_source": {"admin": 1, ...},
 "results": [{"id": "DTA_1900434_20220630", "source": "admin", ...,
              "juridiction": "Tribunal Administratif de Nice", "date": "2022-06-30"}]}
```

Noter la source : `"admin"`. Elle est servie par **l'API live du Conseil d'État**,
pas par la copie locale `opendata.db`. La réponse honnête à la question du mandat
est donc :

- **Oui**, une décision TA/CAA d'open data est atteignable — mais uniquement via
  une API tierce, pas via les 14 Go moissonnés localement.
- **Non**, le plein texte des 985 996 décisions locales n'est pas cherchable : la
  seule voie (`opendata_fts` par l'entrepôt) renvoie 500.

Le corpus local est donc, aujourd'hui, un **doublon inerte** : il ne sert ni de
recherche ni de repli si l'API du Conseil d'État tombe.

### E.6 — Les sommaires sont-ils indexés dans la recherche plein texte ?

**Non.** Preuve par le schéma de l'index :

```sql
CREATE VIRTUAL TABLE decisions_fts USING fts5(
    id UNINDEXED, titre, juridiction, solution, numero, formation, text, numero_rg_norm,
    content='decisions', content_rowid='rowid'
)
```

La colonne `sommaire` de `decisions` **ne figure pas** dans la liste des colonnes
indexées. (La table `decisions` a bien un champ `sommaire`, cf. E.4.)

Conformément à la règle « un argument tiré d'une absence se teste », j'ai vérifié
que cette absence a un effet réel, et non pas nul parce que le sommaire serait
déjà recopié dans `text`. Mesure sur 400 décisions à sommaire long :

```
fragments de sommaire PRESENTS dans text : 125
fragments de sommaire ABSENTS de text   : 275
   ABSENT: JURITEXT000042579710 | En conséquence, une cour d'appel, qui prononce la caducité de la décla
   ABSENT: JURITEXT000042579777 | 23, d'effectuer un repérage des matériaux et produits contenant de l'a
   ABSENT: JURITEXT000042579785 | 4 du code de la sécurité sociale, dans sa rédaction applicable au liti
   ABSENT: JURITEXT000042579712 | 1360 du 1er septembre 1948 ne peut se prévaloir d'une atteinte disprop
```

**69 % des sommaires** portent de la matière absente du texte de la décision.

Test décisif : pour chaque décision, prendre un fragment présent dans le sommaire
et **absent du texte**, puis demander à FTS5 si elle le retrouve.

```
[JURITEXT000042579700] « CONVENTION EUROPEENNE DES DROITS DE L'HOMME »
    -> retrouve par FTS ? 0
[JURITEXT000042579710] « EXPROPRIATION POUR CAUSE D'UTILITE PUBLIQUE »
    -> retrouve par FTS ? 1
[JURITEXT000042579777] « L'obligation, imposée par l'article R. 1334 »
    -> retrouve par FTS ? 0
[JURITEXT000042579785] « 8 du code de la sécurité sociale, ce dernier dans sa rédaction applicable au litige »
    -> retrouve par FTS ? 0
[JURITEXT000042579712] « CONVENTION DE SAUVEGARDE DES DROITS DE L'HOMME ET DES LIBERTES FONDAMENTALES »
    -> retrouve par FTS ? 1
```

**3 fragments sur 5 sont introuvables.** Les 2 qui remontent le font par la colonne
`titre`, qui est indexée, non par le sommaire. La doctrine du sommaire — c'est-à-dire
la partie de l'arrêt que la Cour de cassation écrit **exprès** pour être citée — est
donc hors de portée de la recherche.

### E.7 — Combien de codes sont réellement servis ?

Servis par le site :

```
python3 -c "from sources.legi import SUPPORTED_CODES_LEGITEXT as S; print(len(S))"
79 codes servis
LEGITEXT servis: 79
```

Présents en base :

```
sqlite3 -readonly /opt/justicelibre/dila/legi.db "SELECT nature, COUNT(*) FROM legi_textes GROUP BY nature ORDER BY 2 DESC LIMIT 10;"
ARRETE|91138
DECRET|56806
LOI|3697
ORDONNANCE|1490
LOI_ORGANIQUE|112
CODE|111
DELIBERATION|58
DECRET_LOI|33
DECISION|32
ACCORD_FONCTION_PUBLIQUE|32
```

**79 sigles servis pour 111 codes en base** — soit **32 codes (29 %) sans raccourci**.
Ils restent théoriquement atteignables par leur `LEGITEXT…`, mais la page publique
propose les sigles, pas les identifiants internes, et le paramètre `code` est borné
à 20 caractères (`token_server.py` l. 279-280), ce qui est *exactement* la longueur
d'un LEGITEXT : la marge est nulle.

Point secondaire : le nombre 111 vaut aujourd'hui zéro, puisque **aucun** code n'est
servi tant que l'entrepôt est mort.

### VERDICT E : `FAUX`

« Rattrapé les bases ET leur accessibilité » est faux. Les bases sont rattrapées
(points A, C, D le confirment). L'accessibilité, non :

- l'entrepôt renvoie 500 sur **tous** ses fonds, par fuite de fd (1 023/1 024) ;
- **toutes** les pages `/loi/...` du site public renvoient 404, avec un message
  qui accuse l'usager ;
- 4 des 9 fonds ré-ingérés ne sont exposés par aucune route, et la table `decisions`
  de la prod n'a aucune des colonnes réparées ;
- les 985 996 décisions d'open data locales ne sont pas cherchables en plein texte ;
- les sommaires ne sont pas indexés ;
- 79 codes servis sur 111 — et zéro en pratique aujourd'hui.

---

## F — Ce que personne n'avait regardé

### F-1 (CRITIQUE) — Fuite de descripteurs de fichiers : l'entrepôt est mort

Détaillé en E.1–E.3. Résumé : `_conn()` garde ses connexions SQLite dans un pool
**thread-local**, le serveur crée un thread par requête, les connexions ne sont
jamais fermées. 1 023 fd sur 1 024. Tout `/v1/*` renvoie 500. Toutes les pages
`/loi/...` du site renvoient 404.

Le fait aggravant : **rien ne l'a signalé**. Ni le journal de ré-ingestion, ni une
sonde, ni une alerte. La campagne du 9 septembre s'est terminée sur
`===== RÉ-INGESTION DILA — fin ; disque libre 43 Go` — un succès — alors que le
service qui sert ces données était déjà en train de mourir.

Un redémarrage du service remet le compteur à zéro et **remasque le défaut** sans
le corriger : il repartira à 1 024. Le correctif est dans le code (fermer la
connexion en fin de requête, ou utiliser un vrai pool borné partagé), pas dans un
`systemctl restart`.

### F-2 (CRITIQUE) — `/api/recent` est cassé par une faute de frappe

```
Sep 10 08:01:28 PatrologiaLatina python3[1489749]: [ERROR] justicelibre.token_server: handler failed
Sep 10 08:01:28 PatrologiaLatina python3[1489749]: Traceback (most recent call last):
Sep 10 08:01:28 PatrologiaLatina python3[1489749]: NameError: name '_debut_lisible' is not defined. Did you mean: 'self._debut_lisible'?
```

Localisation :

```
grep -n "_debut_lisible" /opt/justicelibre/token_server.py
307:    def _debut_lisible(txt: str | None, n: int = 300) -> str:
388:                    "debut": _debut_lisible(d.get("debut")), "extract": "",
```

Ligne 388 : appel **nu** d'une méthode statique depuis une autre méthode de la
classe. Il manque `self.`. Le handler lève à tous les coups :

```
curl "https://justicelibre.org/api/recent"   →  http=500
{"error": "Erreur interne."}
```

**Ce que cela rend inutile** : la ligne 388 fait partie du même bloc (l. 350-388)
que le filtre `juridictions.where_judiciaire(juri)` de la ligne 363 — c'est-à-dire
que **le filtre par juridiction ajouté à `/api/recent` n'a jamais pu fonctionner
une seule fois**. Le correctif a été livré mort-né et personne ne l'a appelé après
l'avoir écrit. `token_server.py` est daté du 9 septembre 12:23.

Gravité pratique : c'est le flux « dernières décisions » de la page d'accueil.

### F-3 (GRAVE) — L'API rend la moitié des résultats demandés, sans le dire

```
=== limite demandee vs rendue (source unique tcom) ===
limit=40   rendus= 20  total_affiche= 20
limit=60   rendus= 30  total_affiche= 30
limit=100  rendus= 50  total_affiche= 50
```

Le code, `token_server.py` l. 501 :

```python
lps = limit if sources_only and len(sources_only) == 1 else max(5, limit // 2)
```

La division par deux ne s'annule que si l'appelant a passé `sources=` explicitement.
Or **le filtre `juridiction=tcom` ne réduit qu'à une seule source** (`JURI_DISPATCH`
donne `["dila"]`), ce que le code ignore : il continue de diviser par deux comme
s'il fédérait cinq sources. Un usager qui demande 100 décisions de tribunal de
commerce en reçoit 50.

Aggravant : le champ `total` de la réponse **n'est pas un total**, c'est
`len(results)`. Une recherche « bail » en tribunal de commerce annonce
`"total": 5` alors que le fonds en compte 175 152. Un usager qui lit « 5 résultats »
conclut raisonnablement que la base est vide sur ce point.

### F-4 (GRAVE) — Une recherche « à froid » renvoie 0 résultat sans erreur

C'est ce qui m'a fait croire, à ma première mesure du point A, que le filtre
`tcom` ne rendait rien. Reproduction contrôlée — **même requête, trois appels
successifs, paramètres identiques** :

```
=== q='clause penale manifestement' (juridiction=tcom, limit=20) ===
  appel 1 : rendus= 0  no_result= ['dila'] |http=200|t=6.438596
  appel 2 : rendus= 10 no_result= []       |http=200|t=1.446294
  appel 3 : rendus= 10 no_result= []       |http=200|t=1.467218
```

Et un cas où le corps de la réponse est carrément **vide** :

```
limit=10   json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
limit=20   rendus= 0  total_affiche= 0
limit=40   rendus= 20
```

Le premier appel sur une expression pas encore en cache renvoie **HTTP 200 avec
zéro résultat**. L'usager voit « aucun résultat » pour une requête qui en a des
milliers ; s'il relance, il les obtient. Le budget global est pourtant de 12 s
(`token_server.py` l. 442-445) et l'appel n'a duré que 6,4 s : **je n'établis pas
le mécanisme exact**, seulement le fait, qui est reproductible.

C'est le pire genre de défaut pour un usage juridique : il produit un faux négatif
silencieux. Quelqu'un qui cherche un précédent et lit « aucun résultat » ne relance
pas, et conclut que la jurisprudence n'existe pas.

### F-5 (GRAVE) — 4 fonds ré-ingérés + la doctrine ne sont exposés nulle part

```
 EN BASE MAIS JAMAIS SERVIS : ['capp', 'cass', 'constit', 'doctrine',
            'enrichment', 'external_codes', 'inca', 'judiciaire']
  cass.db          2.64 Go  lignes=145347
  capp.db          2.44 Go  lignes=73050
  inca.db          7.15 Go  lignes=387640
  constit.db       0.17 Go  lignes=7388
  doctrine.db      1.44 Go  table=sources lignes=2
```

`doctrine.db` mérite un mot : la table `sources` ne contient que 2 lignes, mais
la table `docs` en contient **107 273** :

```
sources                   2
docs                      107273
docs_fts                  107273
```

**107 273 documents de doctrine, indexés en plein texte, que rien ne sert.**
Ils n'apparaissent ni dans `FONDS`, ni dans `JURI_DISPATCH`, ni dans aucune route.
1,44 Go de travail fait et invisible.

### F-6 (MOYEN) — 96,4 % des décisions d'open data n'ont pas d'ECLI

```
sqlite3 -readonly opendata.db "SELECT COUNT(*), SUM(texte IS NULL OR texte=''), SUM(ecli IS NULL OR ecli=''), MIN(date), MAX(date) FROM opendata_decisions;"
985996|0|950541|2021-09-03|2026-04-27
```

- **0 texte vide** — très bon point, le corpus n'est pas creux.
- **950 541 lignes sur 985 996 sans ECLI**, soit 96,4 %. L'ECLI est la clé de
  citation normalisée ; sans elle, le rapprochement avec d'autres bases (et le
  vérificateur de citations prévu à la feuille de route) est impossible sur la
  quasi-totalité du fonds.
- Le fonds s'arrête au **27 avril 2026**, soit 4 mois et demi de retard sur le jour
  de l'audit. Le crawl n'est pas à jour.

### F-7 (MINEUR) — Dates impossibles

Fonds judiciaire de la prod, 2 596 246 décisions :

```
dates aberrantes (hors 1790-2027): [(6,)]
exemples: [('JURITEXT000024913398', "Cour d'appel de Bastia", '0201-11-23'),
           ('JURITEXT000024534242', "Cour d'appel de Bastia", '0201-08-24'),
           ('JURITEXT000024304117', "Cour d'appel d'Angers", '0201-06-28'),
           ('JURITEXT000023873863', "Cour d'appel de Douai", '0201-04-07'),
           ('JURITEXT000023841526', "Cour d'appel de Pau", '0201-04-04'),
           ('JURITEXT000034094706', "Cour d'appel de Paris", '0201-02-24')]
dates vides: [(0,)]
```

6 lignes sur 2,6 M — toutes en `0201-..`, une troncature manifeste de `2011`/`2013`.
Et **zéro date vide**, ce qui est un vrai bon point. Plus 35 dates impossibles dans
`kali.date_debut` (cf. C.3.a).

### F-8 (MOYEN, méthodologique) — Le journal ne peut pas servir de preuve

Trois défauts du journal `reingest.log`, tous constatés ci-dessus :

1. Une passe interrompue ne laisse **aucune trace d'erreur** (B.2, point 1) — on ne
   la voit qu'en remarquant l'absence d'un « APRÈS ».
2. Le compteur de progression affiche `0 err` jusqu'à la dernière ligne, qui
   annonce `errors=95` (B.2, point 2).
3. Les 216 enregistrements en erreur ne sont **jamais identifiés** : ni id, ni
   fichier, ni motif. Ils sont irrécupérables.

Conséquence : la formule « 0 échec » du journal ne peut pas fonder l'affirmation
« zéro échec ». C'est exactement la règle du manifeste de couverture — le journal
dit ce qu'on a **joué**, pas ce qu'on a **obtenu**.

---

## Tableau récapitulatif des verdicts

| # | Affirmation auditée | Verdict | En une phrase |
|---|---|---|---|
| **A** | Tribunaux de commerce filtrables de bout en bout, 174 418 décisions | `CONFIRMÉ` | Filtre réellement appliqué et **100 % pur** sur 5 familles ; volume réel **175 152**, donc l'annonce était même en dessous ; aucune des 13 valeurs testées n'est acceptée puis ignorée. |
| **B** | Ré-ingestion DILA : 9 fonds, zéro échec | `EXAGÉRÉ` | Les 9 fonds sont passés et le compteur affiche bien 0 échec sur 2 024 deltas, mais « zéro échec » paraphrase le compteur de *deltas* : **216 enregistrements ont échoué** (190 dans les parses globaux LEGI/JORF), et la passe du 8/09 s'est interrompue au milieu de kali **sans laisser d'erreur**. |
| **C** | Les 16 champs réparés (volumes) | `CONFIRMÉ` | **16 chiffres sur 16 exacts ou dépassés**, aucun gonflé ; contenu réel et structuré, **0 JSON vide `[]`** dans LEGI comme dans JORF. Réserves mineures : 35 dates impossibles dans `kali.date_debut`, `form_dec_att` mal nommé. |
| **D** | ArianeWeb +2 247, corpus à son sommet réel | `EXAGÉRÉ` | Le **+2 247 est exact au chiffre près**, les nouvelles décisions ont toutes un vrai texte (0 vide, min. 2 001 car.), et le plafond haut est réellement atteint (325 793, rien jusqu'à 400 000). Mais le **plancher n'a jamais été exploré** : ~40 000 identifiants vivants sous `START_ID = 95_000`, et « 330 749 » désigne le plafond de balayage, pas un sommet. |
| **E** | « Rattrapé les bases **et leur accessibilité** » | `FAUX` | L'entrepôt renvoie **500 sur tous ses fonds** (fuite de fd, 1 023/1 024) ; **toutes** les pages `/loi/...` du site sont en 404 ; 4 des 9 fonds ré-ingérés ne sont exposés nulle part ; les 985 996 décisions locales ne sont pas cherchables ; les sommaires ne sont pas indexés. |
| **F** | — (recherche libre de défauts) | 8 problèmes trouvés | Voir ci-dessous. |

### Sous-verdicts du point E

| Question du mandat | Verdict | Mesure |
|---|---|---|
| Le `hierarchie`/`liens` de LEGI est-il servi par l'API ? | `FAUX` | `/api/law` → `{"error": "Erreur interne — entrepôt indisponible."}` ; `/loi/*` → 404. |
| Les 985 996 décisions TA/CAA sont-elles cherchables ? | `FAUX` | Compte exact (985 996) mais `opendata` passe par l'entrepôt : 500. La décision témoin ne remonte pas en plein texte ; elle n'est atteignable que par l'**API tierce** du Conseil d'État. |
| Les sommaires sont-ils indexés en plein texte ? | `FAUX` | `sommaire` absent du `CREATE VIRTUAL TABLE decisions_fts` ; 69 % des sommaires portent de la matière absente du texte ; **3 fragments testés sur 5 sont introuvables**. |
| Combien de codes servis vs en base ? | 79 / 111 | 29 % des codes sans raccourci — et **zéro servi en pratique** tant que l'entrepôt est mort. |

---

## Problèmes que J'AI trouvés et que personne n'avait signalés

Classés par gravité.

### CRITIQUE — à traiter aujourd'hui

**1. Fuite de descripteurs de fichiers dans `warehouse_server.py` → panne totale de l'entrepôt.**
1 023 fd sur une limite de 1 024, dont 510 sur `legi.db` et 494 sur `legi.db-wal`.
Cause : `_conn()` (l. 275-291) garde les connexions SQLite dans un pool
**thread-local** que rien ne ferme, alors que le serveur crée un thread par requête.
Effet : `500 {"error": "unable to open database file"}` sur **tous** les fonds.
⛔ **Un `systemctl restart` remet le compteur à zéro et remasque le défaut** — il
repartira à 1 024. Le correctif est dans le code.

**2. Toutes les pages de loi du site public sont en 404, avec un message qui accuse l'usager.**
`/loi/CJA/L521-1`, `/loi/CJA/L521-2`, `/loi/CC/1240`, `/loi/CPC/145`,
`/loi/CESEDA/L611-1`, `/loi/CT/L1132-1` → toutes 404. Le message affiché est
« Vérifie le code et le numéro », alors que le service est en panne. Le référé-
suspension et la responsabilité civile ne sont pas des articles exotiques : c'est
une panne de première ligne pour l'usage réel de ce site.

**3. `/api/recent` lève `NameError` à chaque appel — et emporte avec lui le correctif du 9 septembre.**
`token_server.py` l. 388 : `_debut_lisible(...)` appelé sans `self.`. Le handler
renvoie 500 systématiquement. Le filtre `where_judiciaire` ajouté à la ligne 363,
dans le **même bloc**, n'a donc **jamais pu s'exécuter une seule fois**. Un
correctif livré sans être appelé une seule fois après écriture.

### GRAVE

**4. Faux négatif silencieux : la première recherche sur une expression renvoie 0 résultat.**
Même requête, trois appels : `0` puis `10` puis `10`. Parfois le corps de la
réponse est carrément vide. HTTP 200 dans tous les cas. Pour un usage juridique
c'est le pire défaut possible : quelqu'un qui cherche un précédent lit « aucun
résultat » et conclut que la jurisprudence n'existe pas. **C'est ce qui m'a
moi-même trompé à ma première mesure du point A.**

**5. L'API rend la moitié des résultats demandés et appelle `total` ce qui n'en est pas un.**
`limit=100` → 50 résultats ; `limit=60` → 30. La division `limit // 2`
(`token_server.py` l. 501) ne s'annule que si l'appelant passe `sources=`, alors
que `juridiction=tcom` réduit déjà à une source unique. Et `"total": 5` sur un
fonds de 175 152 décisions, parce que `total` vaut `len(results)`.

**6. 107 273 documents de doctrine, indexés, que rien ne sert.**
`doctrine.db`, 1,44 Go, table `docs` = 107 273 lignes avec un index plein texte
`docs_fts` complet. Le fonds n'est ni dans `FONDS`, ni dans `JURI_DISPATCH`, ni
dans aucune route. Du travail entièrement fait et entièrement invisible.

**7. 4 des 9 fonds ré-ingérés ne sont exposés par aucune route, et la prod n'a pas les colonnes.**
`capp`, `cass`, `constit`, `inca` (12,4 Go, 613 425 décisions) absents de `FONDS`.
Et la table `decisions` de la prod n'a **ni `avocat_general`, ni `form_dec_att`,
ni `siege_appel`, ni `url_cc`**. Les « réparations » du point C sont donc
inatteignables par les deux voies possibles, même une fois l'entrepôt réparé.

### MOYEN

**8. ~40 000 identifiants ArianeWeb vivants ne sont jamais moissonnés.**
`START_ID = 95_000`, justifié par un commentaire qui saute de `id=50000 → 404` à
`id=100000 → 200` sans rien tester entre les deux. J'ai testé : 55 000, 57 000,
59 000, 60 000, 70 000, 80 000, 90 000, 94 000, 94 999 répondent **tous 200**.
L'identifiant 70 000 est un arrêt de **Section du contentieux mentionné aux tables
du recueil Lebon** (CE, 6 mai 1983, n° 43282). C'est le même défaut que celui
réparé en haut (borne codée en dur + sonde trop grossière), inaperçu en bas.

**9. Le corpus ArianeWeb est figé au 12 décembre 2025 — zéro décision de 2026.**
Imputation honnête : ce n'est **pas** la faute de la moisson, ArianeWeb lui-même
n'a rien publié depuis. Mais la conséquence pratique doit être écrite quelque part :
les 2 247 décisions entrées le 9 septembre sont du rattrapage de trous anciens,
**pas** des décisions nouvelles.

**10. 96,4 % des décisions d'open data n'ont pas d'ECLI, et le fonds a 4 mois de retard.**
950 541 lignes sans ECLI sur 985 996 ; date maximale **2026-04-27**. Sans ECLI, le
vérificateur de citations prévu à la feuille de route ne pourra pas travailler sur
la quasi-totalité de ce fonds.

**11. Le journal de ré-ingestion ne peut pas servir de preuve.**
Une passe interrompue ne laisse aucune trace d'erreur ; le compteur de progression
affiche `0 err` jusqu'à la ligne finale qui annonce `errors=95` ; et les 216
enregistrements en erreur ne sont jamais identifiés (ni id, ni fichier, ni motif) —
ils sont irrécupérables. Le journal dit ce qu'on a **joué**, pas ce qu'on a **obtenu**.

**12. L'étiquette `"source"` des résultats est inexacte.**
Un résultat rendu comme `"source": "ariane"` (n° 515399, 22/05/2026) n'existe pas
dans `ariane_decisions`. L'usager ne peut pas savoir d'où vient ce qu'il lit.

### MINEUR

**13. Dates impossibles.** 6 décisions en `0201-..` sur 2 596 246 (troncature de
2011/2013), et 35 `kali.date_debut` hors de `1900-2030` (min `0003-09-01`, max
`5489-12-30`). Négligeable en volume, mais rappelle que « non vide » ≠ « exploitable ».

**14. `form_dec_att` ne contient pas une formation mais une juridiction.**
Contenu réel : « Cour d'appel de Paris », « Conseil de prud'hommes d'Angers ».
À documenter, pas à corriger en base.

**15. Anomalie de rangement dans `cass.db` (non quantifiée).** Des lignes portent
`avocat_general = 'Mme Prada Bordenave (commissaire du gouvernement)'` et
`form_dec_att = 'Cour de cassation'` — un commissaire du gouvernement est une
fonction de la juridiction administrative, et la Cour de cassation ne peut pas être
sa propre juridiction attaquée. Vraisemblablement des décisions du Tribunal des
conflits. **Volume `INVÉRIFIABLE`** : je n'ai pas mesuré combien de lignes sont
dans ce cas.

---

## Ce que je n'ai PAS pu vérifier

- **La date de début de la panne de l'entrepôt.** `journalctl -u justicelibre-warehouse`
  ne journalise que les lignes d'accès, pas les codes de réponse ni les corps
  d'erreur. Le processus tourne depuis le 8/09 18:06:42 et le compteur de fd est
  aujourd'hui à 1 023 ; l'instant exact du franchissement est `INVÉRIFIABLE`.
- **Le mécanisme du faux négatif à froid (problème n° 4).** Le fait est
  reproductible, la cause ne l'est pas : le budget global est de 12 s et l'appel
  fautif n'a duré que 6,4 s. `INVÉRIFIABLE` en l'état.
- **Le volume de l'anomalie de rangement dans `cass.db`** (problème n° 15).
- **Le taux de doublons du fonds judiciaire de la prod.** La requête
  `GROUP BY juridiction, numero, date HAVING COUNT(*)>1` sur 2 596 246 lignes n'a
  pas abouti dans le temps de l'audit (analyse séquentielle de 28 Go sur disque
  partagé). `INVÉRIFIABLE` ici ; à relancer hors charge. La requête tournait encore
  au moment où j'ai rendu ce rapport : son résultat s'écrira dans
  `/tmp/f2.out` sur la prod (`ssh root@46.225.190.237 'cat /tmp/f2.out'`), lignes
  `doublons (juridiction,numero,date) top:` et `nb groupes dupliques:`.

---

## Note de méthode

Deux fois pendant cet audit, une première mesure m'a donné un résultat faux :

1. Les filtres `tcom`, `ca`, `tj`, `cedh` m'ont d'abord rendu **0 résultat**, ce
   qui aurait conduit au verdict « le correctif A ne marche pas ». C'était le
   problème n° 4 (faux négatif à froid), pas un filtre cassé. Je ne l'ai vu qu'en
   re-testant.
2. J'ai conclu trop vite que l'entrepôt était injoignable, parce que mon test
   utilisait l'URL publique par défaut au lieu de `JL_WAREHOUSE_URL=http://10.8.0.2:8001`
   fixée dans l'unité systemd. La vraie panne est ailleurs (fuite de fd) et je ne
   l'ai trouvée qu'en relisant l'unité.

Dans les deux cas, la **lecture la moins charitable était la mauvaise**. Les
verdicts ci-dessus sont ceux de la seconde mesure, pas de la première.

J'ai par ailleurs arrêté deux de mes propres requêtes de lecture sur la prod
(PID 1772257 et 1769416/1769417) : cinq balayages complets de la base de 28 Go
tournaient en concurrence et dégradaient un site en production. Aucune donnée n'a
été modifiée, aucun service redémarré.
