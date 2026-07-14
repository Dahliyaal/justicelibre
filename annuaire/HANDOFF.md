# Annuaire des administrations — données collectées le 14 juillet 2026

Objectif : publier sur JusticeLibre un annuaire des adresses mail fonctionnelles
des juridictions + des PRADA (personnes responsables de l'accès aux documents
administratifs), et **chiffrer les trous** de l'annuaire officiel de l'État.

Tout est déjà collecté. Ne pas re-scraper sans raison.

---

## Fichiers

### `prada_full.csv` — 2 247 lignes, `;` séparateur
Annuaire **complet** des PRADA, scrapé depuis le formulaire de la CADA.
Colonnes : `organisme;prada;courriel;adresse`
- `prada` = nom de la personne physique désignée
- `adresse` = adresse postale, lignes séparées par ` | ` (civilité / service / rue / CP-ville)
- 2 206 ont un courriel, **41 n'en ont aucun**

C'est la seule version exploitable qui existe : la CADA ne publie cette liste
que sous forme de **formulaire web**, sans export. L'association Ouvre-boîte a
deux datasets « Liste des PRADA » sur data.gouv.fr — **tous les deux vides**
(0 ressource). Donc ce CSV n'existe nulle part ailleurs en accès libre.

Entrées clés :
| Organisme | PRADA | Courriel |
|---|---|---|
| Ministère de la Justice | Alexandre TREMOLIÈRE | `cada.sdajgc-sem-sg@justice.gouv.fr` |
| Conseil d'État | — | `SG-Secretariat@conseil-etat.fr` |
| Ministère de l'Intérieur | — | `prada@interieur.gouv.fr` |
| Premier ministre | — | `prada.spm@sgg.pm.gouv.fr` |

### `justice_mails.csv` — 1 711 lignes, `;` séparateur
Juridictions et organismes de justice extraits du dump DILA.
Colonnes : `type;nom;mails;tel;site;id`
- `type` = code pivot DILA (`tgi`, `ti`, `cour_appel`, `ta`, `caa`, `prudhommes`,
  `te`, `tribunal_commerce`, `tae`, `cdad`, `mjd`, `spip`, `ordre_avocats`,
  `vif_tj`, `vif_ca`, `bav`)
- `mails` = plusieurs adresses possibles, séparées par ` ; `
- `id` = UUID stable du service dans l'annuaire (jointure possible avec l'API)
- 1 022 / 1 711 ont un mail

### `dila_annuaire_local.json` — 260 Mo
Dump brut DILA, 86 009 services (toutes administrations locales, pas que la justice).
Structure : `{"service": [ {...}, ... ]}`. Champs utiles : `nom`, `pivot`
(liste de `{type_service_local, code_insee_commune}`), `adresse_courriel` (liste),
`telephone`, `site_internet`, `sve`, `formulaire_contact`, `id`.

### `scrape_prada.py`
Le scraper CADA. Réexécutable tel quel (250 pages, ~1 min, 6 threads).
Régénère `prada_full.csv`.

---

## Sources (pour régénérer / mettre à jour)

**Dump DILA** (base locale, mise à jour quotidienne) :
```
https://lecomarquage.service-public.gouv.fr/donnees_locales_v4/all_latest.tar.bz2
```
348 Mo compressés. Contient un `.zip` (communes) + le `.json` (services locaux).

**API annuaire** (contient les services NATIONAUX, absents du dump — important) :
```
https://api-lannuaire.service-public.fr/api/explore/v2.1/catalog/datasets/api-lannuaire-administration/records
  ?where=search(nom,"cassation")&limit=20&select=id,nom,adresse_courriel,telephone,sve
```
API Opendatasoft classique : `where=`, `select=`, `limit=`, `offset=`,
plus un endpoint `/exports/json` pour tout aspirer.

**Formulaire PRADA CADA** (pas d'API, pagination `?p=N`, 9 résultats/page) :
```
https://www.cada.fr/particulier/personnes-responsables-resultatss?p=1
```
Le filtre plein-texte du site est **cassé** (il renvoie la page 1 quels que soient
les paramètres) — d'où le scraping intégral des 250 pages.

---

## Chiffres établis (vérifiés, réutilisables tels quels)

Base API : **93 925 services**, dont **26 743 sans aucune adresse mail** (28 %).
Dump local : 86 009 services.

Complétude des mails par type de juridiction :

| Type | Total | Avec mail | Taux |
|---|---|---|---|
| Tribunal de proximité | 125 | 125 | 100 % |
| Conseil de prud'hommes | 216 | 212 | 98 % |
| Tribunal administratif | 40 | 39 | 98 % |
| Cour administrative d'appel | 9 | 9 | 100 % |
| Tribunal judiciaire | 168 | 163 | 97 % |
| **Cour d'appel** | **37** | **10** | **27 %** |
| **Tribunal de commerce** | **122** | **16** | **13 %** |
| **SPIP** | **43** | **11** | **26 %** |
| **Tribunal pour enfants** | **156** | **9** | **6 %** |

Services nationaux (API uniquement — **absents du dump téléchargeable**) :
- **Cour de cassation** → `adresse_courriel: null`
- **Greffe de la Cour de cassation** → `adresse_courriel: null`
- Première présidence de la Cour de cassation → `sg.pp.courdecassation@justice.fr`
- Parquet général de la Cour de cassation → `sec.pg.courdecassation@justice.fr`
- **Secrétariat général du ministère de la Justice** → `null`
  (c'est-à-dire : l'entité qui **détient** l'annuaire interne des greffes
  n'a elle-même aucune adresse publiée)

**Le point le plus fort pour un grief** : les 10 cours d'appel qui ont un mail
n'ont **aucun pattern commun** — `ca-caen@`, `accueil.ca-limoges@`,
`accueil-besancon@`, `ca-douai@`, `ca-bourges@`, `accueil-chambery@`…
Donc une adresse non publiée est **indevinable**. La non-publication n'est pas
une coquetterie : c'est une barrière d'accès effective au service public de la justice.

---

## Ce qu'il reste à faire

1. **Publier** les deux CSV sur JusticeLibre sous forme de tableau filtrable
   (par type de juridiction / département / présence ou absence de mail).
2. Une **vue « les trous »** : la liste des juridictions sans mail publié.
   C'est le produit d'appel, et c'est la pièce d'un futur recours.
3. **Demande CADA** au ministère de la Justice (PRADA ci-dessus) :
   communication de la liste des adresses fonctionnelles des greffes de l'ordre
   judiciaire, appuyée sur les chiffres ci-dessus.
   Base : L.300-2 + L.311-1 CRPA (communicable), L.312-1-1 (publication en ligne
   après communication), L.114-2 (transmission d'office si mauvais guichet).
   Silence 1 mois → saisine CADA → TA.

## ⚠️ Point à trancher avant publication

`prada_full.csv` contient **2 247 noms de personnes physiques**. Ce sont des
données professionnelles, déjà publiées officiellement par la CADA en exécution
de son obligation légale de publier cette liste — la republication est donc
légitime. Mais c'est une décision à prendre **délibérément**, pas par défaut :
option (a) publier tel quel, option (b) publier organisme + courriel + adresse
et masquer la colonne `prada`. Le courriel fonctionnel suffit à l'usage visé.
