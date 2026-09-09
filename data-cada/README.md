# Base des avis et conseils de la CADA — note d'intégration

Écrit le 26 août 2026 pour le Claude qui travaille sur le site. Tout ce qui suit a été vérifié le jour
même sur le fichier et sur le réseau, pas déduit.

## La source

Jeu de données data.gouv **« Avis et conseils de la CADA »**, slug `avis-et-conseils-de-la-cada`.
Ressource utilisée, l'ensemble consolidé (198 Mo, CSV, UTF-8, séparateur `,`, guillemets doubles) :

```
https://static.data.gouv.fr/resources/avis-et-conseils-de-la-cada/20260814-172417/cada-2026-08-14.csv
```

⚠️ Cette URL porte un horodatage de version : elle change à chaque republication. Pour un pipeline,
passer par l'API catalogue et prendre la ressource dont le titre est « Ensemble consolidé des avis et
conseils de la CADA » :

```
https://www.data.gouv.fr/api/1/datasets/avis-et-conseils-de-la-cada/
```

Copie locale : `~/justicelibre/data-cada/cada-2026-08-14.csv`. Pas de WAF, téléchargement direct en
curl — contrairement aux xlsx gouv.

## Le contenu

**60 941 lignes**, numéro de dossier unique (bonne clé primaire). 57 385 avis, 3 553 conseils,
3 sanctions.

| Colonne | Remarque |
|---|---|
| `Numéro de dossier` | 8 chiffres, `AAAANNNN`. Unique. |
| `Administration` | 17 080 valeurs distinctes, saisie libre, non normalisée (« ministre de la justice » et « Ministère de la Justice » coexistent). |
| `Type` | `Avis` / `Conseil` / `Sanction`. |
| `Année`, `Séance` | `Séance` au format `JJ/MM/AAAA` — c'est la vraie date de l'avis. |
| `Objet` | ⚠️ **vide sur les 60 941 lignes**. Ne pas l'indexer, ne pas l'afficher. |
| `Thème et sous thème` | hiérarchie `Thème/Sous-thème`, séparateur `/`. |
| `Mots clés` | multi-valué. |
| `Sens et motivation` | multi-valué séparé par `, ` — 6 735 combinaisons distinctes, mais un vocabulaire fermé une fois éclaté (`Favorable`, `Défavorable/Vie privée`, `Incompétence/Juridictionnel`, `Sans objet/Inexistant`, `Irrecevable/…`). **À normaliser en table de liaison**, c'est le champ à facettes le plus utile. |
| `Partie` | I à IV (partie du rapport d'activité). Peu d'intérêt. |
| `Avis` | le texte intégral. Médiane 2 034 caractères, maximum 37 462, **une seule ligne vide** sur 60 941. |

## ⚠️ Piège majeur : les dates affichées par data.gouv sont fausses une fois sur trois

Le CSV est en **JJ/MM/AAAA** — établi sans ambiguïté : 41 188 lignes ont un jour supérieur à 12 en
première position, et **aucune** n'en a en seconde. Mais l'interface `data.gouv.fr/explore/cada/` parse
en MM/JJ quand la date est ambiguë :

| Numéro | CSV | Affiché par data.gouv |
|---|---|---|
| 20090119 | 15/01/2009 | 15 janvier 2009 ✅ |
| 20155645 | 17/12/2015 | 17 décembre 2015 ✅ |
| **20204479** | **07/01/2021** | **« 1 juillet 2021 » ❌** |

Signature d'un parser qui tente le format américain d'abord et ne bascule que lorsque le mois dépasse 12.
**Toutes les séances dont le jour est ≤ 12 sont donc affichées à l'envers sur data.gouv**, soit environ
un tiers du corpus. Faire foi au CSV, jamais à la page. Et si le site affiche une date d'avis, la
calculer depuis le CSV — sinon on publie des dates fausses, et une date fausse dans un acte juridique se
paie cher.

## Couverture : ce que chaque canal contient vraiment

Répartition par année de séance : quasi rien avant 2012, pleine de 2013 à 2023 (3 600 à 7 100 par an),
1 046 pour 2024, **rien après le 18 avril 2024**.

Il faut être exact là-dessus, les deux formules courantes sont fausses :

- **data.gouv** — le producteur écrit « //À partir de fin 2012, l'intégralité des avis et conseils est
  disponible// ». Donc **pas** de sélection éditoriale sur 2013-2024. Mais les métadonnées déclarent
  `temporal_coverage: start 1984-03-03, end 2024-04-30` et `frequency: punctual`.
- **cada.fr/rechercher-un-avis** — « //Dans cette base de données, une **sélection** d'avis et de
  conseils […] est mise à disposition du public// », filtrée par actualité du droit et pertinence.
- **avant fin 2012** — « //un panel représentatif// », environ 4 000 avis.

⛔ Ne pas écrire « la CADA ne publie qu'une sélection » (faux pour data.gouv 2013-2024) ni « la CADA a
tout publié » (faux après avril 2024). La formule exacte : intégralité de fin 2012 à avril 2024 en open
data, sélection sur le site de la commission, et **aucun canal ne diffuse l'intégralité des avis
postérieurs au 30 avril 2024**.

## ⭐ Deuxième source, ignorée de tous : la liste des avis favorables

L'article **L. 342-3 du CRPA** oblige le président de la CADA à publier « //régulièrement la liste des
avis favorables// », précisant l'administration, la référence du document, « //les suites données, le cas
échéant, par l'administration à cet avis// » et « //l'issue du recours contentieux// ». Cette liste
existe, et elle n'est **pas** sur data.gouv :

```
https://www.cada.fr/lacada/liste-des-avis-favorables      (CSV + PDF, une paire par année)
https://www.cada.fr/sites/default/files/Liste%20avis%20favorables%202023.csv
```

UTF-8 BOM, séparateur virgule, champs multi-lignes. Colonnes : `Numéro de dossier`, `Administration`,
`Séance`, **`Objet`**, **`Avis suivi`**, `Issue du recours 1/2`, `Date du jugement 1/2`,
`Juridiction concernée 1/2`, `Date de notification`.

**Deux apports que l'export principal n'a pas :**

1. **`Objet` est rempli à 100 %** ici, alors qu'il est vide à 100 % dans le consolidé. Jointure sur
   `Numéro de dossier` → on récupère l'objet des avis favorables.
2. **`Avis suivi`** = la seule donnée publique sur ce que les administrations font de leurs avis. Sur
   les 1 560 avis favorables de 2023 : `Oui` 44,7 %, **vide 36,8 %**, `Fin` 10,5 %, `Non` 5,4 %,
   `Par` 2,6 %. ⚠️ `Fin` et `Par` sont des codes **non documentés** — ne pas les interpréter, les
   afficher tels quels ou les regrouper en « autre ».

⚠️ **Deux limites à signaler si on publie ces chiffres :**

- La dernière année disponible est **2023**, alors que le rapport d'activité 2025 est en ligne.
- **`Issue du recours 1` est vide sur les 1 560 lignes de 2023** — la colonne prévue par la loi existe
  mais n'est jamais renseignée. Ne pas construire de statistique contentieuse là-dessus.

Un taux de suivi par administration est calculable et n'existe nulle part ailleurs. C'est probablement
la donnée la plus intéressante des deux fichiers pour le site.

## Lien canonique vers un avis — le point important

**Utiliser data.gouv, pas cada.fr :**

```
https://www.data.gouv.fr/explore/cada/<numéro à 8 chiffres>/
```

Testé le 26 août 2026 sur 20204479, 20090119, 20155645, 20163021, 20111493, 20061864 : **6/6 résolvent**.
Les mêmes numéros sur `cada.fr/<numéro>` : **5 échecs sur 6** (seul 20130447 répond). Le site de la CADA
n'expose qu'une sélection, et `cada.fr/recherche` renvoie une 404 — il n'y a pas de moteur exploitable
de ce côté.

⚠️ **Ne pas tester la validité d'un lien sur le code HTTP** : data.gouv renvoie 200 dans les deux cas.
Le discriminant est le corps — 166 octets sans `<title>` pour un numéro inexistant, ~57 Ko avec
`<title>Avis CADA 20204479</title>` pour un vrai.

⚠️ **Piège de numérotation, déjà payé deux fois.** `cada.fr` affiche l'avis 20130447 sous une forme
interne à 9 chiffres, `201300447`. Ça donne l'impression que le numéro cité par la CADA elle-même
comporte une coquille : **c'est faux**, les deux formes désignent le même avis. Ne jamais « corriger »
un numéro à 8 chiffres.

## Ce qui existe déjà côté infra

D'après l'état du projet de juillet 2026, le WAREHOUSE Hetzner héberge un `doctrine.db` décrit comme
contenant « CADA 60k avis + DDD + BOFiP + Ariane ». Le compte colle exactement à cet export.
**À vérifier avant toute réingestion** : `SELECT COUNT(*)` et la séance la plus récente. Si le contenu
est le même, il n'y a rien à charger, seulement à exposer — le MCP JusticeLibre n'a aujourd'hui aucun
tool `search_cada` (il y a `search_cnil`, pas d'équivalent CADA), alors que la doctrine CADA est
exactement ce dont on a besoin dans les dossiers d'accès aux documents.

## Reco d'intégration

1. Table `cada(numero PK, type, seance DATE, administration, theme, sous_theme, mots_cles, texte)` +
   table de liaison `cada_sens(numero, sens)` issue de l'éclatement de `Sens et motivation`.
2. Index FTS5 sur `texte` **et** `mots_cles` uniquement — `Objet` est vide, l'indexer ne fait que gonfler
   l'index.
3. Facettes : sens, année, type, thème. La recherche par sens (« tous les Incompétence/Juridictionnel »)
   est ce qui a permis de trancher la compétence de la CADA sur les juridictions en dix minutes.
4. Lien sortant vers `data.gouv.fr/explore/cada/<numero>/`, jamais vers cada.fr.
5. Rafraîchissement : le jeu a été republié le 14 août 2026 avec des données arrêtées à avril 2024. Un
   contrôle mensuel de la ressource consolidée suffit largement.

## À quoi ça sert, concrètement

Les trois saisines CADA du 26 août 2026 (`CLAUDE COWORK FOLDER/CADA/Annuaire des juridictions
(Justice Libre)/`) ont été entièrement sourcées sur ce fichier, par simple regex sur
`Avis + Mots clés` : cinq avis cités, dont le précédent décisif de 2009 sur l'annuaire de la
magistrature. Sans ce fichier, aucun de ces avis n'était trouvable — ni par JusticeLibre, ni par
cada.fr.
