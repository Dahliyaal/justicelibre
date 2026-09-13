# Les dernières pages de la refonte v2 — accueil, à propos, doctrine, annuaire (13 septembre 2026)

Mandat : construire, sur le normaliseur (`web/styles/jl.css` + `web/jl.js` + `web/topbar.js`),
l'accueil allégé, la page « À propos » qui recueille tout ce qui en sort, la rubrique
« Avis & doctrine », et l'annuaire existant dans le cadre v2.

Cahier des charges : [`inventaire_composants_13sept.md`](inventaire_composants_13sept.md) (§2.13, §5, §6, §7),
[`normaliseur_13sept.md`](normaliseur_13sept.md), [`v2_recherche_13sept.md`](v2_recherche_13sept.md),
[`inventaire_champs_13sept.md`](inventaire_champs_13sept.md) (§10, §12, §13).

---

## 0. MANIFESTE DE COUVERTURE

| Fichier | Lignes | Lu jusqu'à | État |
|---|---|---|---|
| `scratchpad/audit/normaliseur_13sept.md` | 297 | 297 | **lu en entier** |
| `scratchpad/audit/v2_recherche_13sept.md` | 165 | 165 | **lu en entier** |
| `scratchpad/audit/inventaire_champs_13sept.md` | 737 | l. 506-630 (§10 doctrine, §11 CNIL, §12 travaux, §13 annuaire) + table des matières complète | **NON LU EN ENTIER** — lecture ciblée sur les trois fonds que ces pages servent. Les fonds 1 à 9 et 14 ne sont touchés par aucune de ces quatre pages. |
| `scratchpad/audit/inventaire_composants_13sept.md` | 604 | l. 229-263 (§2.13), l. 404-603 (§6, §7, §8) + table des matières complète | **NON LU EN ENTIER** — §1 à §5 avaient déjà été absorbés par le normaliseur et par la page de recherche, dont les deux rapports sont lus en entier ici. |
| `web/index.html` | 817 | l. 1-40 (head) + l. 380-817 (tout le corps) | **LU EN ENTIER pour ce qui est du contenu** : les l. 41-379 sont le `<style>` de la page, sans texte. Aucun paragraphe du corps n'a été sauté. |
| `web/ressources.html` | 464 | l. 80-464 (tout le corps) | corps **lu en entier** ; l. 1-79 = head + `<style>` |
| `web/annuaire.html` | 6773 | l. 1-101 et l. 6365-6773 | **NON LU EN ENTIER** — le milieu (l. 102-6364) est le bloc `STATIC_ROWS` injecté au build, c'est-à-dire de la donnée, comme le mandat le dit. Tout le JS et tout le markup d'interface sont lus. |
| `web/hub.html` | 1382 | l. 355-445, 565-600, 845-870, 975-1060, 1280-1315 | **NON LU EN ENTIER** — lecture ciblée : `SCOPES`, `TOTAL_TOUT`, `loadHD`/`showDocSrc`, le scope `avis`, `runSearch`/`fetchPlans`. Le reste était déjà inventorié par `v2_recherche_13sept.md`, lu en entier. |
| `web/hub_doctrine.json` | — | intégralement inspecté (clés, 5 sources, comptes, exemples) | lu |
| `web/v2/recherche.html` | 213 | 213 | **lu en entier** (le gabarit de page v2) |
| `web/v2/recherche.js` | 1003 | l. 1-60, 330-620, 860-1003 | **NON LU EN ENTIER** — lecture ciblée sur les mécanismes réutilisés (états de source, cartes, signalement, démarrage). |
| `web/styles/jl.css` | 1377 (avant) | l. 46-200, 355-400, 435-530, 548-712, 749-800, 855-1060, fin | **NON LU EN ENTIER** — toutes les sections dont ces pages se servent ont été lues ; la liste complète des 300+ noms de classe a été extraite par `grep` pour ne pas en réinventer un seul. |
| `web/jl.js` | 1046 | en-tête d'API, `renderRail`, `bindMenu`, `nb`, `urlSignalement`, `decouperTexte`, l'objet exporté, `init` | **NON LU EN ENTIER** — l'API exposée a été lue exhaustivement (l. 951-977), les fonctions employées ont été lues ligne à ligne. |
| `web/topbar.js` | 243 | 0 | **NON LU** — interdit en écriture ; les pages posent `<div data-topbar-mount>`, aucune décision n'en dépend. |
| `ssr*.py`, `server.py`, `search_api.py`, `token_server.py`, pages prod | — | 0 | **NON LUS** — interdits en écriture, et inventoriés par les rapports. |

**Fichiers écrits** (aucun autre) :

- `web/v2/index.html` — 116 l.
- `web/v2/apropos.html` — 360 l.
- `web/v2/doctrine.html` — 120 l.
- `web/v2/doctrine.js` — 542 l.
- `web/v2/annuaire.html` — 180 l.
- `web/v2/annuaire.js` — 382 l.
- `web/styles/jl.css` — **ajout en fin de fichier uniquement**, section datée « v2 accueil / doctrine / annuaire — 13 sept. 2026 ». Aucune règle antérieure réécrite.
- `web/jl.js` — **non modifié**. Rien n'a eu besoin d'y être ajouté : tout ce dont ces pages ont besoin y était déjà (`renderRail`, `bindMenu`, `bindMailR`, `nb`, `fmtDate`, `esc`, `clipExtract`, `decouperTexte`, `urlSignalement`, `GITHUB`, `estEntree`). C'est le meilleur résultat possible : un fichier interdit de réécriture qu'on n'a pas eu à toucher du tout.

Aucun commit. Aucune page de production modifiée. Les cinq pages v2 existantes et les deux maquettes sont intactes (§5).

---

## 1. L'ACCUEIL : CE QUI RESTE, CE QUI PART, OÙ ÇA VA

`web/v2/index.html` tient en un écran : header, hero, deux boutons, une ligne de chiffres, un pied.
Il n'y a **aucune** tuile d'outil, **aucun** exposé, **aucune** frise.

### 1.1 Ce qui reste

| Élément | Origine | Composant |
|---|---|---|
| Le titre, **mot pour mot** : `L'accès libre et gratuit à toute la jurisprudence <em>française.</em>` | `web/index.html:441` | `.jl-acc__h1` + `<em>` serif italique teal |
| Bouton « Rechercher librement » → `/v2/recherche.html` | libellé de `web/index.html:415` (`aria-label` du bouton de la barre de navigation), cible changée vers la page v2 | `.jl-bouton--cta` |
| Bouton « À propos » → `/v2/apropos.html` | nouveau, demandé par le mandat | `.jl-bouton--ghost`, **sous le hero** |
| Ligne de chiffres réels | voir §1.3 | `.jl-chiffres` / `.jl-chiffre` |
| Rail « Chercher dans » | `JL.renderRail()` depuis `#jl-page` | `.jl-rail` |

**La signature typographique est en italique**, pas en droit. `index.html:199` mettait
`font-style:normal` parce que son hero est en capitales (`text-transform:uppercase`,
`index.html:197`) ; le rapport §6.2 a tranché : « capitales = droit, bas de casse = italique ».
Ce hero-ci est en bas de casse, donc italique. C'est un **écart visuel volontaire** avec la prod,
conforme à la règle écrite.

### 1.2 Ce qui part de l'accueil, et où

| Section coupée | Fichier:ligne d'origine | Destination |
|---|---|---|
| Paragraphe « Standardisation de l'accès programmatique au Droit… » | `index.html:442` | `apropos.html` § « Ce que c'est », **tel quel** |
| Bouton « Accéder à l'endpoint MCP » | `index.html:443` | supprimé ; l'endpoint est dans `apropos.html`, en `<code class="jl-url">` |
| Illustration `circuit.png` / `circuit-dark.png` | `index.html:445-448` | **supprimée**, non reprise |
| Les 4 tuiles de statistiques | `index.html:456-459` | refondues en `.jl-chiffres`, voir §1.3 |
| « Installation en **trois étapes** » + endpoint + les 3 `<li>` | `index.html:465-475` | `apropos.html`, **texte inchangé** |
| « 30 outils, **toute la matière** juridique française » + l'encadré `get_law_article` + les 5 grilles d'outils (26 cartes) | `index.html:480-627` | `apropos.html`, **texte inchangé** ; 2 cartes **ajoutées** (`search_doctrine`, `search_annuaire`) parce que ces deux fonds ont désormais une page sur le site |
| « Pourquoi c'est **gratuit** et **légal** » + l'encadré Indépendance/Transparence/Sources | `index.html:632-639` | `apropos.html`, **texte inchangé** |
| Bouton Ko-fi | `index.html:640-645` | `apropos.html` § « Soutenir » |
| « La France, **seul pays européen**… » : les 4 paragraphes | `index.html:650-658` | `apropos.html`, **texte inchangé** |
| Encadré « Accéder à la jurisprudence judiciaire » + tutoriel PISTE | `index.html:660-664` | `apropos.html`, sur `.jl-carte` |
| La frise en 5 jalons | `index.html:666-702` | `apropos.html`, sur `.jl-frise` (les 2 jalons faits = point teal plein, les 3 à venir = point en pointillés **gris**, jamais rouge) |
| Pied à 3 colonnes (sources, projet, contact) | `index.html:706-733` | éclaté : sources → `apropos.html` § « Sources et licences » ; contact et code → `apropos.html` § « Soutenir, contribuer, nous joindre » ; mentions → liens vers `/mentions-legales.html` et `/confidentialite.html` |
| Phrase « Propulsé par la loi, pas par vos frais de licence. » | `index.html:731` | **coupée**. Signalée en §7. |
| Les 4 scripts inline (scrollspy, burger, thème, badge MàJ, anti-scrape) | `index.html:735-815` | remplacés : burger et thème par `topbar.js` + `jl.js`, anti-scrape par `JL.bindMailR`. Le badge « MàJ » qui lit `/version.json` n'est **pas** repris, voir §7. |

### 1.3 Les chiffres affichés, et d'où ils sortent

| Chiffre | Valeur | Source citée |
|---|---|---|
| décisions de justice cherchables | **3 285 952** | `hub.html:592` (`const TOTAL_TOUT = 3285952`), commenté `hub.html:590-591` : judiciaire 2 594 344 + JADE 570 881 + CEDH 76 062 + CJUE 44 665. Repris aussi par `v2/recherche.js:43`. **L'open data TA/CAA (985 996) n'y est pas** : en base, pas cherchable. Dit dans l'infobulle. |
| articles de loi, avec versions | **1,75 M+** | `index.html:457` (tuile « Articles de loi (avec versions) ») et `index.html:533` (`search_legi` : « 1,75 M+ articles de 72 codes ») |
| avis et documents de doctrine | **107 273** | somme des 5 fonds de `web/hub_doctrine.json` : CADA 60 941 + DDD 15 864 + rapporteurs publics 9 138 + BOFiP 6 301 + Code du travail numérique 15 029. `hub.html:854` affiche 107 273 ; `hub.html:395` affiche « 109 k », qui inclut la CNIL — non retenu, la CNIL n'est pas servie par le site. |
| adresses de juridictions et de PRADA | **71 142** | `annuaire_meta.json`, clé `counts.grand_total`, relevé en direct sur la prod. **Pas** le « 75 k » de `hub.html:401`, qui est une vignette de rail arrondie du même genre que le « 4,3 M » que le rapport de rattrapage a établi comme faux. |
| coût d'accès | **0 €** | `index.html:459` |

Chaque chiffre porte une `.jl-provenance` avec l'infobulle qui dit la mesure et sa date.

---

## 2. `apropos.html` : LE SURPLUS, RÉORGANISÉ

Sept sections, dans cet ordre : ce que c'est · pourquoi c'est gratuit et légal · installation en trois
étapes · les 30 outils · sources et licences · la France seul pays européen · soutenir, contribuer, nous joindre.

**Le texte est repris tel quel.** Les seules interventions sont des coupes (§1.2, dernière ligne) et
trois ajouts explicitement signalés : les deux cartes d'outils `search_doctrine` / `search_annuaire`,
et le tableau des sources.

Le tableau « Sources et licences » (composant `.jl-tableau`) condense en 6 lignes les cartes de
`web/ressources.html` : bulks DILA (l. 190-200), opendata.justice-administrative.fr (l. 202-212),
HUDOC (l. 214-224), EUR-Lex (l. 226-236), PISTE (l. 238-250), et les 4 thésaurus + le PCJA reconstruit
(l. 95-160). Les chiffres (20 968 concepts, 335 597 décisions JADE) sont ceux de `ressources.html`.
La page renvoie ensuite à `/ressources.html` pour le détail : elle ne la remplace pas.

**Contact** : aucun `mailto:` n'est écrit dans le HTML. Le lien porte `class="jl-mail-r"` avec
`data-u`/`data-d`/`data-t`, et `JL.bindMailR` (appelé par `jl.js` au démarrage) recompose l'adresse au
clic. **Vérifié au navigateur** : `contact@justicelibre` est absent du DOM avant le clic, présent après.

**Liens GitHub** : `https://github.com/Dahliyaal/justicelibre` et
`https://github.com/Dahliyaal/justicelibre/issues`, nulle part ailleurs.

---

## 3. `doctrine.html` + `doctrine.js` : AVIS & DOCTRINE

### 3.1 Ce qui est repris du hub

| Fonctionnalité | Origine | Où maintenant |
|---|---|---|
| Une tuile = un fonds, avec son compte et sa phrase | `hub.html:856` | `renderTuiles()`, `doctrine.js:110-150` ; données `web/hub_doctrine.json` |
| Le clic sur une tuile restreint la recherche au fonds et affiche ses 12 derniers documents | `hub.html:421-441` (`loadHD`, `showDocSrc`) | `renderDerniers()`, `doctrine.js:170-200` |
| Les types du fonds en gélules avec leurs comptes | `hub.html:435` | `.jl-chip`, `renderDerniers()` |
| La recherche `sources=doctrine&juridiction=doctrine` | `hub.html:983` | `lancer()`, `doctrine.js:210-270` |
| La pastille d'état de source avec loader | `hub.html:1060` / `v2/recherche.js:409-427` | `renderSources()` |
| Le CNIL grisé « MCP seulement » | `hub.html:856` (`tile-src soon`) | `.jl-tuile--bientot`, **gris**, non cliquable |
| La phrase « Ces textes ne sont pas des jugements » | `hub.html:858` | `.jl-honnetete`, en bas de page |

### 3.2 Trois corrections par rapport au hub, signalées

1. **La restriction au fonds ne filtre plus sur `organisme`.** `hub.html:1051` compare
   `r.organisme === HD.sources[src].nom` : cela **rate les conclusions de rapporteurs publics**, parce
   que `hub_doctrine.json` écrit « Rapporteurs publics » et l'API répond `organisme: "Rapporteur public"`
   (mesuré : `/api/search?juridiction=doctrine&q=communication de documents` rend bien
   `"organisme": "Rapporteur public"`). Le filtre porte donc sur le **préfixe de l'identifiant**
   (`cada:`, `ariane_crp:`, `ddd:`, `bofip:`, `ctn:`), qui est la clé réelle du sous-fonds
   (inventaire des champs §10.1). `doctrine.js`, fonction `duFonds`.
2. **Un fonds vide n'est plus un cul-de-sac.** Quand la restriction à un fonds ne rend rien mais que
   les autres fonds ont des résultats, la page le dit et propose de retirer la restriction, au lieu
   d'écrire « aucun résultat ».
3. **Le chargement des tuiles est en chemin relatif** (`/hub_doctrine.json`), pas sur le domaine de
   prod : sinon le serveur local se heurte au CORS. Et s'il échoue, une alerte le **dit**, en
   précisant que la recherche, elle, continue de fonctionner sur tout le fonds.

### 3.3 La fiche : rien que les six champs mesurés

La fiche à droite du texte affiche **exactement** ce que l'inventaire des champs §10.5 donne pour
disponible, et rien d'autre :

| Ligne de fiche | Champ de l'API | Taux mesuré | Provenance affichée |
|---|---|---|---|
| Organisme | `organisme` | 100 % | « Champ `organisme` servi par /api/decision. 100 % sur ce fonds. » |
| Type de document | `formation` (= `type` de l'entrepôt) | 100 % | dit que le nom du champ diffère de son contenu |
| Administration concernée | `juridiction` (= `administration`) | 100 % | idem |
| Date | `date` | 100 % | voir §3.4 |
| Sujet | `sujet` | 87,5 % sur les documents complets | dit que la taxonomie CADA est servie **comme une chaîne brute**, jamais découpée (§10.3) |
| Source officielle | `source_url` | **100 %** | « c'est le fonds le mieux outillé du site pour le lien officiel » |
| Sens | *aucun champ* | — | voir §3.5 |

Un bloc `.jl-honnetete` dit ce que la fiche **ne peut pas** dire, en reprenant §10.5 mot pour mot :
le numéro d'affaire du Conseil d'État derrière une conclusion de rapporteur public (il est dans `tags`
sous la forme `AFF:427460`, jamais extrait), et le lien vers la décision juridictionnelle qui a suivi.

Aucun résumé produit par un modèle n'apparaît nulle part.

### 3.4 Les dates CADA

L'inventaire §10.4 le mesure : **la CADA date en `jj/mm/aaaa`** (`08/07/2021`) tandis que `ddd` et
`ariane_crp` datent en ISO ; `_norm_doctrine` (l. 575-578) corrige au passage pour le site, mais le MCP
et l'entrepôt servent la forme brute, et `warehouse_server.py` l. 793 dit lui-même que le tri et les
bornes de date sont « peu fiables sur ce sous-fonds ».

La page fait trois choses :
- elle affiche la date en toutes lettres (`8 juillet 2021`) via `JL.fmtDate` ;
- **sur un document CADA, elle affiche en plus la forme `jj/mm/aaaa` à côté**, en note de provenance,
  pour que la date lue sur le site corresponde à celle qu'on lira sur `cada.fr` ;
- l'infobulle dit : « Date servie en ISO par /api/search (2021-07-08). La CADA l'écrit 08/07/2021 à la
  source : c'est la même date, écrite jj/mm/aaaa. »
- si l'API renvoyait un jour la forme brute `jj/mm/aaaa`, `dateLisible()` la sert telle quelle au lieu
  de la casser.

### 3.5 Le sens de l'avis

§10.5 : « le sens de l'avis autrement qu'en lisant le texte (la CADA le met en fin de contenu,
`--- Sens et motivation ---\nFavorable`, jamais en champ) ».

**Vérifié en direct** sur `/api/decision?source=doctrine&id=cada:20212413` : le `full_text` se termine
bien par `\n\n--- Sens et motivation ---\nFavorable`.

`extraireSens()` coupe le texte au marqueur, prend la **première ligne** qui suit comme sens, le reste
comme motivation. Le sens s'affiche à deux endroits — en tête du document (`.jl-note`) et dans la fiche
— toujours suivi de la note de provenance **« lu en fin de texte »**, dont l'infobulle précise que ce
n'est un champ d'aucune API. La motivation, si elle existe, est rendue sous un titre à part, pour
qu'elle ne passe pas pour un paragraphe de l'avis.

**Vérifié au navigateur** : `?id=cada:20212413` affiche le titre, la bande d'identité, le texte
découpé en paragraphes, la fiche complète, et **« Sens : Favorable · lu en fin de texte »**.

---

## 4. `annuaire.html` + `annuaire.js` : L'ANNUAIRE DANS LE CADRE v2

`web/annuaire.html` (prod) n'est pas touchée : décision de la propriétaire, rappelée par le rapport §7.
Cette page charge **les mêmes trois fichiers** et rend **le même tableau**.

### 4.1 Correspondance, fonction par fonction

| Ce que fait la page v2 | Origine dans `web/annuaire.html` |
|---|---|
| `loadAll()` : 3 `fetch` parallèles, normalisation juri + PRADA en un seul tableau | annuaire.html:6438-6482 |
| `renderMeta()` : dates de capture DILA / CADA / génération | annuaire.html:6484-6490 |
| `renderCoverage()` : 4 tuiles de comptage + tableau de complétude, seuils **30 / 70** | annuaire.html:6492-6511 (seuil annuaire.html:6507) |
| `populateCategoryFilter()` : ordre `juriOrder` puis `prada`, comptes par catégorie | annuaire.html:6513-6525 |
| `currentRows()` : filtre catégorie + « sans mail » + texte sur nom, sub, mails, contact, catégorie | annuaire.html:6553-6570 |
| `fmtContact()` : tel · site · hiérarchie · adresse (les `\|` deviennent des `<br>`) · extra · source | annuaire.html:6576-6586 |
| `fmtMails()` : un ou plusieurs `mailto:` séparés par `<br>` ; vide → « non publié » | annuaire.html:6588-6591 |
| `fmtSignal()` + modale : ticket GitHub pré-rempli, adresse de contact **jamais en clair** | annuaire.html:6597-6651 |
| `COLS` / `rowHTML()` : les 5 mêmes colonnes, dans le même ordre | annuaire.html:6655-6687 |
| Pagination à **1000**, « Afficher X de plus », « tout afficher » | annuaire.html:6672-6710 |
| Tri au clic sur l'en-tête, avec inversion | annuaire.html:6740-6746 |
| Le texte de la méthodologie, des avertissements et du bandeau « Cour de cassation… » | annuaire.html:57-61, 6401-6408 |

### 4.2 Ce qui passe sur les composants jl

| Ancien | Nouveau | Note |
|---|---|---|
| `.filters` (annuaire.css:44-49) | **`.jl-barre-filtre`** (jl.css §22) | ⛔ C'est la barre **locale**, pas `.jl-barre-reseau` (§21). Le jeu est déjà chargé : pas de bouton, pas de loader, filtrage à la frappe temporisé à 150 ms, compteur toujours juste. Rapport §7.3. |
| `.cs-wrap`/`.cs-panel` + `bindCs()` | `.jl-menu` + `JL.bindMenu` (événement `jl:pick`) | la quatrième copie de `bindCs` disparaît |
| `table.data` (annuaire.css:53-78) | `.jl-tableau` (jl.css §17) | en-têtes collants et tri déjà dedans |
| `td.type .badge` | `.jl-badge` / `.jl-badge--prada` (jl.css §23, **axe 3**) | la catégorie d'entité, ni backend ni famille |
| badges `manuel` / `api` (annuaire.html:6658-6659, couleurs en dur) | **`.jl-provenance`** | c'est le seul point où le rapport §7.4 demandait explicitement un changement : ces deux badges « sont exactement une note de provenance ». Fait. Les couleurs en dur `#fef9e8` / `#e6f0f5` disparaissent. |
| lien « source : … » en `#b8932b` (annuaire.html:6584) | `.jl-provenance` | idem |
| `.download-row` (annuaire.css:84-89) | `.jl-dlrow` (nouveau, §D de l'ajout CSS) | |
| `.chk-toggle` (annuaire.css:127-128) | `.jl-chk` (nouveau) | même `accent-color:var(--teal)` |
| `.stat` / `.coverage` (annuaire.css:27-42) | `.jl-stat` / `.jl-taux` + `.jl-barre` | seuils inchangés ; rouge = mauvais, doré = avertissement, teal = bon |
| `.jl-modal-overlay` construite en JS | `.jl-modale-overlay` **déjà dans le HTML** | plus de markup fabriqué à la volée |
| `.no-mail` en `#c1440e` (annuaire.css:69) | `.jl-nomail` sur `var(--bad)` | rouge atténué, jeton |

### 4.3 Les JSON, et l'échec de chargement

En local, `/data/*.json` n'est pas servi. `DATA` vaut donc `https://justicelibre.org` hors production
(même règle que `API` dans `v2/recherche.js:22`), et les quatre liens de téléchargement sont réécrits
au démarrage vers le même domaine.

**L'échec est traité comme une panne, jamais comme un vide.** `panne()` affiche une `.jl-alerte` qui dit :
« Les données de l'annuaire n'ont pas pu été chargées. […] Le tableau ci-dessous est vide parce que le
chargement a échoué, **pas** parce qu'il n'y a rien : aucune conclusion ne peut être tirée de ce vide »,
avec le chemin exact essayé et un bouton **Réessayer**. Le corps du tableau dit « Données non chargées :
voir l'avertissement ci-dessus » et le compteur affiche `—`, jamais `0`.

Symétriquement, quand les données **sont** chargées et que le filtre ne rend rien, la phrase est
différente et honnête : « Aucun résultat pour ces filtres. Les 67 777 fiches sont bien chargées : c'est
le filtre qui ne rend rien. »

---

## 5. LE RAIL « CHERCHER DANS »

Identique sur les quatre pages, piloté par le bloc `#jl-page` :

| Entrée | État | Pourquoi |
|---|---|---|
| Jurisprudence | actif, « 3,3 M » → `/v2/recherche.html` | |
| Textes | **grisé « bientôt »** | inchangé |
| Travaux préparatoires | **grisé « bientôt »** | inventaire des champs §12 : « **Aucun fonds n'existe** », vérifié sur tout le dépôt. Ni base, ni table, ni parseur, ni téléchargement (`orchestrate_bulk.sh` l. 10 ne liste pas DOLE). L'intitulé existe dans le hub ; la donnée n'existe pas. |
| **Avis & doctrine** | **actif**, « 107 k » → `/v2/doctrine.html` | nouveau |
| **Annuaire** | **actif**, « 71 k » → `/v2/annuaire.html` | nouveau |
| Outil « Vérifier mes citations » | actif → `/hub.html#/citations` | comme `v2/recherche.html` |

Le gris des entrées « bientôt » vient de `.jl-ri.is-soon` (jl.css §2) : gris inactif, jamais rouge.

---

## 6. CE QUI A ÉTÉ AJOUTÉ À `jl.css`

Une seule section, **en fin de fichier**, titrée « v2 accueil / doctrine / annuaire — 13 sept. 2026 »,
avec le renvoi à ce rapport. Aucune règle existante réécrite, aucun renommage.

| Bloc | Classes |
|---|---|
| A. Accueil | `.jl-acc`, `.jl-acc__h1` (+ `em`), `.jl-acc__lead`, `.jl-acc__actions`, `.jl-chiffres`, `.jl-chiffre`, `.jl-chiffre__n`, `.jl-chiffre__l` |
| B. À propos | `.jl-prose`, `.jl-sect`, `.jl-url`, `.jl-etapes`, `.jl-grille-3`, `.jl-outil`, `.jl-outil--second`, `.jl-liens` |
| C. Doctrine | `.jl-doc-grid`, `.jl-doclec`, `.jl-fiche`, `.jl-sens` |
| D. Annuaire | `.jl-dlrow`, `.jl-chk`, `.jl-stats`, `.jl-stat`, `.jl-stat__n`, `.jl-stat__l`, `.jl-taux(--ok/--warn/--bad)`, `.jl-barre`, `.jl-tbl-scroll`, `.jl-td-mail`, `.jl-td-contact`, `.jl-nomail`, `tr.jl-more`, `tr.jl-vide-tr` |
| E. Impression | masquage des actions, de la barre de filtre, de la ligne de téléchargement, des tuiles et de la ligne « afficher plus » ; le `.jl-tbl-scroll` cesse d'être une fenêtre de 70 vh ; les `<th>` cessent d'être collants ; les lignes deviennent insécables ; `.jl-doclec` et `.jl-grille-3` repassent en blocs |

Une seule exception locale à un composant, et elle est commentée dans le fichier :
`.jl-chiffre .jl-provenance{white-space:normal}` — la note de provenance est `nowrap` par défaut (§9),
ce qui la faisait déborder sur la colonne voisine dans la ligne de chiffres. Le composant n'est pas
touché ; seule cette portée le relâche.

`.jl-barre` porte la largeur en variable `--w`, posée en attribut `style` par le JS. C'est **de la
donnée** (un taux mesuré), au même titre que les `style="width:…%"` des histogrammes de
`v2/recherche.js`, pas un style de présentation. Aucun autre style n'est écrit en ligne.

---

## 7. VÉRIFICATIONS FAITES DANS LE NAVIGATEUR

Toutes sur `http://localhost:8787/`, panneau de prévisualisation.

| Contrôle demandé | Résultat |
|---|---|
| **Zéro erreur console, accueil** | **aucune** (onglet neuf, `read_console_messages onlyErrors` vide) |
| **Zéro erreur console, à propos** | **aucune** |
| **Zéro erreur console, doctrine** (avec recherche) | **aucune** |
| **Zéro erreur console, annuaire** | **3 erreurs CORS inévitables en local** : le navigateur journalise un `ERR_FAILED` par `fetch` bloqué vers `https://justicelibre.org/data/*.json`. Ce n'est pas une erreur de la page — c'est le refus du navigateur, que la page **intercepte et affiche**. En production, les trois fichiers sont servis en même origine et il n'y a aucune erreur. Aucune autre erreur. |
| **Accueil à 1280 px, clair** | conforme, capture prise |
| **Accueil à 1280 px, sombre** | conforme, capture prise (hero, `<em>` teal, chiffres, notes de provenance et boutons tiennent tous) |
| **Accueil à 390 px** | conforme, capture prise ; **débordement horizontal = 0 px** (mesuré : `scrollWidth - clientWidth === 0`) ; rail replié en colonne d'icônes |
| **Doctrine : « communication de documents »** | **30 résultats chargés sur 56 987 existants**, cartes avec badge de fonds, famille « Avis & doctrine », organisme, date, extrait surligné, identifiant, lien « source officielle ↗ », bouton « signaler » |
| **Doctrine : lecture de `cada:20212413`** | **oui** : titre « Conseil CADA — Conseil départemental du Puy-de-Dôme — Modalités D'Accès (08/07/2021) », bande d'identité (identifiant, numéro, date `8 juillet 2021`), texte intégral découpé en paragraphes, fiche à droite, et **« Sens : Favorable · lu en fin de texte »** |
| **Doctrine : les tuiles** | 5 fonds rendus depuis `hub_doctrine.json` (CADA 60 941, Défenseur des droits 15 864, Rapporteurs publics 9 138, BOFiP 6 301, Code du travail numérique 15 029) + CNIL **grisée** « MCP seulement (search_cnil) » |
| **Annuaire : chargement des JSON** | **oui**, vérifié en dérivant les trois `fetch` vers une copie locale des fichiers de prod servie avec en-tête CORS (le CORS est le seul obstacle en local, pas le code) : 1 711 juridictions locales, 3 395 services centraux, 2 247 PRADA, **71 142** total ; dates « Bulk DILA capturé le 14 juillet 2026 · Annuaire CADA capturé le 14 juillet 2026 » ; tableau de complétude trié par taux croissant, barres rouges sous 30 % |
| **Annuaire : échec de chargement** | **oui**, c'est l'état par défaut en local : alerte « Les données de l'annuaire n'ont pas pu être chargées… le tableau est vide parce que le chargement a échoué, pas parce qu'il n'y a rien », bouton **Réessayer** fonctionnel |
| **Annuaire : filtre « lille »** | **245 / 67 777 fiches**, 245 lignes rendues |
| **Annuaire : tri par colonne** | **oui** : clic sur « Adresse électronique » trie, les « non publié » remontent en tête ; second clic inverse |
| **Annuaire : « Afficher 1000 de plus »** | **oui** : 1 001 lignes (1 000 + la ligne « plus ») → 2 001 après un clic |
| **Annuaire : signalement** | **oui** : modale ouverte, fiche rappelée (nom, catégorie, adresses), lien GitHub pré-rempli `.../issues/new?title=Signalement%20annuaire%20:%20…` ; **`contact@justicelibre` absent du DOM**, et présent seulement après le clic sur « afficher l'adresse » |
| **Impression, accueil** | vérifiée en injectant les règles `@media print` comme feuille d'écran : rail masqué, boutons masqués, étiquette de prototype masquée, les **5 chiffres** restent |
| **Impression, annuaire** | idem : rail masqué, barre de filtre masquée, ligne de téléchargement masquée, ligne « afficher plus » masquée, **récapitulatif papier visible** et rempli (« justicelibre.org · Annuaire des juridictions et PRADA · 67 777 / 67 777 fiches · <adresse> ») |
| **`web/v2/recherche.html`** | **intacte**, zéro erreur console, flux « Nouveautés » rendu (capture) |
| **`web/v2/article.html`** | **intacte**, zéro erreur console, article 748-6 CPC complet (capture) |
| **`web/v2/historique.html`** | **intacte**, zéro erreur console, vue « Couloirs » rendue (capture) |
| **`web/maquettes/decision-jl.html`** | **intacte** (capture) |
| **`web/maquettes/composants.html`** | **intacte** (capture) |
| **`web/v2/ssr-preview/*`** | les 5 fichiers répondent 200, non modifiés (horodatage inchangé) |
| **Syntaxe JS** | `node --check` : OK sur `v2/doctrine.js`, `v2/annuaire.js`, `jl.js`, `v2/recherche.js` |
| **Styles en ligne** | **zéro** dans les quatre pages HTML. Dans le JS, un seul : `style="--w:…%"` sur la barre de taux, qui est une donnée mesurée (§6). |
| **Scripts en ligne** | un seul par page, le résolveur de thème de 2 lignes en tête de `<head>` (voir « À trancher » n° 1), plus le bloc de données `#jl-page`. |

**La bizarrerie de capture signalée par les deux rapports précédents est toujours là** : une capture
prise après un défilement revient blanche. Elle touche aussi les pages non modifiées. Les contrôles
concernés (modale de signalement, simulation d'impression) ont donc été faits par mesure
(`getComputedStyle`, lecture du DOM) et non par capture.

---

## 8. CE QUI N'A PAS PU ÊTRE FAIT, ET POURQUOI

| Élément | Pourquoi |
|---|---|
| **Vérifier l'annuaire en conditions réelles depuis le serveur local** | `/data/*.json` n'est pas servi en local et la prod ne renvoie pas d'en-tête `Access-Control-Allow-Origin`. Le chargement a donc été prouvé en dérivant les trois `fetch` vers une copie locale des mêmes fichiers de prod : le code de chargement, de normalisation, de rendu, de tri, de filtrage et de pagination est celui de la page, inchangé. Ce qui reste **non prouvé en local** : que la prod servira bien ces fichiers en même origine — mais c'est le cas pour `web/annuaire.html` aujourd'hui, avec exactement les mêmes chemins. |
| **Le badge « MàJ » de l'endpoint MCP** (`index.html:797-807`, lit `/version.json`) | non repris sur `apropos.html` : c'est un 5ᵉ script inline, et `jl.js` n'expose rien pour cela. L'ajouter voudrait dire écrire dans `jl.js`, que je n'ai pas eu besoin de toucher. **À faire si la date compte** ; elle est aujourd'hui absente de la page À propos. |
| **La phrase « Propulsé par la loi, pas par vos frais de licence. »** (`index.html:731`) | coupée. C'est une signature de marque, pas une information ; l'accueil allégé n'a plus de pied éditorial. **Elle n'est reprise nulle part** : à réinstaller si elle compte. |
| **Le tableau de complétude de l'annuaire n'a pas de barre à l'impression** | `.jl-barre::before` emploie `currentColor` ; les navigateurs n'impriment pas les fonds sans `print-color-adjust`, que je n'ai pas posé (il aurait fallu décider si tous les aplats du site partent sur le papier). Le taux en chiffres, lui, s'imprime. |
| **Le calendrier fabriqué en JS** (`.cal`, hub.html:205-217) | toujours pas absorbé — point 1 du §4 du normaliseur, resté ouvert. Sans conséquence ici : aucune de ces quatre pages n'a de champ de date. |
| **La grille des 20 sous-pages d'annuaire** (`annuaire.html:6375-6398`) et le bouton « Inédits » bordeaux | non repris. Ce sont des dispositifs **propres à la page de prod** que le rapport §7.6 classe explicitement comme « à ne pas généraliser », et la page de prod les garde. Si la v2 doit un jour les remplacer, il faudra les reprendre : **signalé**, pas oublié. |
| **Le rendu statique pour l'indexation** (`STATIC_ROWS`, 6 263 lignes) | non repris, et c'est volontaire : le rapport §7.6 dit que ce compromis n'a de sens que pour la page dont le référencement est le contenu entier. La page v2 est un cadre, pas la page indexée. **Conséquence à connaître** : si la v2 remplaçait la prod telle quelle, le site perdrait les 6 263 lignes servies à Google. |

---

## 9. « À TRANCHER » — ce que je n'ai pas décidé en silence

1. **Le script de thème en tête de page.** Les quatre pages portent, comme `v2/recherche.html:21-24`,
   `decision-jl.html:23-25` et les 8 pages prod (`annuaire.html:6-9`), un `<script>` inline de 2 lignes
   qui pose `data-theme` avant les feuilles. Le mandat n'autorise en ligne que le head SEO et les
   données. **Proposition** : le garder ; sans lui la page clignote en blanc en thème sombre. C'est le
   même arbitrage que le point 1 du normaliseur et le point 1 de la page de recherche, toujours non
   tranché.

2. **Le total de l'annuaire est double, et les deux chiffres sont justes.** `annuaire_meta.json` dit
   `grand_total: 71 142` ; la somme réelle des lignes chargées est **67 777**. L'écart (3 365) vient de
   ce que `meta` compte `api_total: 67 182` alors que `annuaire_juridictions.json` n'en sert pas autant.
   **Le défaut existe tel quel en production** (annuaire.html:6721 affiche « n / 67 777 » sous un
   bandeau qui annonce 71 142). J'ai repris les deux tels quels : l'accueil affiche `grand_total`, le
   compteur affiche les lignes chargées. **À trancher** : lequel des deux est le bon chiffre public.
   Tant que ce n'est pas tranché, l'accueil annonce 71 142 et la page d'annuaire en montre 67 777.

3. **Le sens d'un avis est affiché deux fois** : en tête du document et dans la fiche. C'est
   délibéré — on lit le sens avant le texte, et on le retrouve dans la fiche quand on a déroulé — mais
   c'est une redondance. **À dire** s'il ne doit rester qu'à un endroit.

4. **La date CADA est écrite deux fois sur un document CADA** (`8 juillet 2021` + `08/07/2021` en note).
   C'est ma lecture de l'avertissement du mandat : ne pas laisser croire qu'une date normalisée par le
   site est la date écrite par la CADA. **Si tu voulais simplement que les dates CADA soient affichées
   en `jj/mm/aaaa`**, c'est une ligne à changer (`dateLisible`) — mais alors la page datera les avis
   CADA autrement que le reste du site, ce que je n'ai pas voulu faire sans ton accord.

5. **Le Code du travail numérique (`ctn`, 15 029 documents) est affiché comme un fonds de doctrine.**
   Il est dans `hub_doctrine.json` et dans `_DOCTRINE_SOURCES`, mais `hub.html:856` ne le montre **pas**
   dans les 5 tuiles du prototype (le hub montre CNIL à la place). Ce ne sont pas tout à fait des avis :
   ce sont des articles vulgarisés et des fiches. **Proposition** : le garder, parce qu'il est
   réellement cherchable et que le cacher ferait disparaître 15 029 documents servis ; mais c'est un
   écart avec le prototype, et le chiffre de 107 273 de l'accueil l'inclut.

6. **`search_doctrine` et `search_annuaire` ont été ajoutés à la liste des 30 outils** de la page
   À propos, avec un lien vers leur page. Le titre dit toujours « 30 outils » et la liste en compte
   désormais 28 affichés (la page d'accueil actuelle n'en listait que 26 sous ce même titre).
   **À trancher** : soit le titre devient un chiffre exact, soit il reste rond. Je ne l'ai pas changé.

7. **Le pied de l'accueil porte encore 4 liens** (À propos, GitHub, Mentions légales, Confidentialité)
   plus la phrase de sources et de licence. C'est le strict minimum légal (LCEN) plus la mention de
   source qu'impose la Licence Ouverte. **Si « à mort » veut dire zéro pied**, les mentions légales
   doivent aller quelque part d'atteignable en un clic : dis-moi où.

8. **`web/jl.js` n'a pas été modifié du tout.** Trois choses auraient pu y aller et n'y sont pas,
   parce qu'elles ne servent aujourd'hui qu'à une page : `extraireSens` (doctrine), la pagination
   « afficher N de plus » (annuaire), et le tri de tableau au clic (annuaire). **Proposition** : les y
   monter le jour où une deuxième page en a besoin, pas avant.

---

/home/dahl/justicelibre/scratchpad/audit/v2_accueil_doctrine_annuaire_13sept.md
