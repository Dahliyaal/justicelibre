# v2 — CARTE D'UN ARTICLE et HISTORIQUE sur le normaliseur — 13 septembre 2026

Reconstruction de `web/v2/article.html` (page « maintenant ») et `web/v2/historique.html`
(vues Couloirs et Poupées russes, avec bascule) à partir des maquettes validées
`carte-748.html`, `histo-02.html`, `histo-05.html`, sur `jl.css` + `jl.js`.

---

## 0. MANIFESTE DE COUVERTURE

| Fichier | Lignes | Lu jusqu'à | État |
|---|---|---|---|
| `scratchpad/audit/inventaire_composants_13sept.md` | 604 | §2.4, §2.5, §2.6, §2.7, §2.12, §4 intégralement + la table des titres de §2.13 | **lecture ciblée assumée** : les six sections imposées par le mandat, lues mot à mot ; §1, §3, §5, §6, §7, §8 non relus, parce que `normaliseur_13sept.md` en donne les arbitrages déjà appliqués dans `jl.css`, que je n'avais pas à refaire |
| `scratchpad/audit/normaliseur_13sept.md` | 297 | 297 | **lu en entier** (table §2.2, §2.3, §4, §6) |
| `scratchpad/audit/audit_historique_13sept.md` | 85 | 85 | **lu en entier** (G1-1→G1-6, G2-1→G2-10, G3-1→G3-10, comptes §3) |
| `scratchpad/audit/contre_audit_historique_13sept.md` | 118 | 118 | **lu en entier** (statut des 26 constats, régressions R-1→R-5, comptes aux 3 dates) |
| `web/styles/jl.css` | 824 au moment de la lecture, 1323 après (l'autre agent a ajouté §27) | 824 | **lu en entier**, puis relu (tail + grep des sélecteurs de §27) juste avant chacun de mes deux ajouts |
| `web/jl.js` | 618 au moment de la lecture, 984 après | 618 puis 615-984 | **lu en entier** dans ses deux états successifs |
| `web/maquettes/carte-748.html` | 518 | 518 | **lu en entier** |
| `web/maquettes/histo-02.html` | 636 | 636 | **lu en entier** (en deux passes, 1-452 puis 453-637) |
| `web/maquettes/histo-05.html` | 624 | l. 505-624 + `diff` mécanique des l. 266-506 contre histo-02 | **NON LU EN ENTIER** — le `diff` établit que les l. 1-265 (style) et le modèle sont identiques à histo-02 à trois écarts près (`linkArts`/`CODE_SIGLE` ajoutés, la ligne du bouton de vue, l'étiquette `.proto`) ; seul le bloc propre à la vue (VCSS, `VIEW`, `WIRE`) a été lu ligne à ligne |
| `web/maquettes/decision-jl.html` | 129 | 129 | **lu en entier** (exemple d'assemblage : head, `#jl-page`, `data-jl-print`, `data-jl-llm`) |
| `web/hub_paysage_748.json` | 17 867 | clés de tête seulement | **NON LU** — sondé en Python (clés, cardinalités : 9 articles, 220 arêtes de succession, 44 arrêtés, 14 décrets, 109 résolus). Le contenu est validé par la comparaison des comptes rendus, pas par lecture |
| `web/hub_cite_748.json` | 23 | 23 | sondé (5 clés, 15 décisions brutes, `total_lexical` 121) |
| `ssr.py`, `server.py`, `search_api.py`, pages de prod | — | 0 | **NON LUS** — interdits en écriture, et hors du périmètre |

**Écrit** : `web/v2/article.html` (70 l.), `web/v2/historique.html` (65 l.),
`web/v2/article.js` (636 l.), `web/v2/carte.js` (313 l.), `web/v2/histo.js` (525 l.),
plus trois ajouts en fin de `web/styles/jl.css` (§28, §28.10, §28.11, l. 1043-1323)
et un en fin de `web/jl.js` (l. 986-1046).
**Aucun autre fichier touché. Aucun commit.**

---

## 1. LES DEUX DIVERGENCES TRANCHÉES

Le mandat impose de trancher en faveur d'histo-02 et de le dire. C'est fait, et c'est écrit
dans le code lui-même (`web/v2/article.js:11-16`).

| Helper | carte-748 | histo-02 | Retenu |
|---|---|---|---|
| `lifeAt` | `carte-748.html:289-293` — un texte dont `date_fin <= at` est toujours « abrogé le … » (ou « périmé » si `etat` commence par `PERIM`) | `histo-02.html:308-313` — un texte dont `etat` commence par `MODIFIE` devient `{k:'q', label:'réécrit le …'}` avec l'explication « Légifrance a ouvert un nouvel identifiant pour ce texte à cette date (même NOR) : la suite est sous l'autre entrée » | **histo-02**, `web/v2/article.js:67-82` |
| `minus` | `carte-748.html:321` — `Arrêté → arrêté`, sans article défini | `histo-02.html:314` — `Arrêté → l'arrêté`, `Décret → le décret` | **histo-02**, `web/v2/article.js:84-86` |

**Conséquence de fond de l'arbitrage `lifeAt`, à connaître** : sur la CARTE, l'arrêté du
7 avril 2009 sous identifiant `LEGITEXT000020507643` (`etat: MODIFIE`) n'est plus annoncé
« abrogé le 1er janv. 2020 ». C'était une erreur de droit sur écran (G1-4 de
`audit_historique_13sept.md:22`) : il n'a pas été abrogé, il a été renommé TGI → TJ et
Légifrance lui a ouvert un second identifiant sous le même NOR `JUSC0907573A`. Sur la CARTE
ce texte n'est de toute façon pas affiché (il n'est ni en vigueur, ni dans les étages), donc
la correction ne change **aucun compte** de la carte : elle prépare seulement la cohérence
entre les deux pages, qui affichaient jusqu'ici deux vérités différentes du même texte.

**Conséquence rédactionnelle de l'arbitrage `minus`** : `carte-748.html:444` écrivait
`remplace <a>l’${minus(titre)}</a>`, c'est-à-dire un `l’` en dur DEVANT un `minus` qui n'en
produisait pas. Avec le `minus` d'histo-02, ce `l’` en dur produirait « l'l'arrêté ». Il est
donc supprimé (`web/v2/carte.js:25-36`, commentaire à l'appui). Le rendu est identique.

---

## 2. TABLE DES COMPTES — MAQUETTE vs v2

Mesures prises dans le navigateur (`http://localhost:8787`), sur les deux jeux de pages,
au même instant, par exécution de JS dans la page. **Aucun écart.**

### 2.1 CARTE — `carte-748.html` vs `v2/article.html`, au 13 septembre 2026

| Grandeur | maquette | v2 | |
|---|---|---|---|
| rédactions (`versions`) | 4 | 4 | = |
| étage 1 « La rédaction en vigueur » (bulle) | 1 | 1 | = |
| étage 2 « Arrêtés en vigueur pris pour lui » (bulle) | 2 | 2 | = |
| Arrêté du 29 août 2025 — retouches / remplacés | 0 / 11 | 0 / 11 | = |
| Arrêté du 9 mars 2020 — retouches / remplacés | 3 / 0 | 3 / 0 | = |
| « Références croisées » (`citantsList`) | 7 | 7 | = |
| exclus — auteurs / arrêtés vivants / arrêtés morts | 4 / 2 / 2 | 4 / 2 / 2 | = |
| jurisprudence — décisions / doublons fusionnés | 11 / 4 | 11 / 4 | = |
| `recycled` | false | false | = |

### 2.2 CARTE au 1er janvier 2020 (`?date=2020-01-01`)

| Grandeur | maquette | v2 | |
|---|---|---|---|
| rédaction lue (`cur.date_debut`) | 2019-05-05 | 2019-05-05 | = |
| étage 1 / étage 2 | 1 / 1 | 1 / 1 | = |
| l'arrêté retenu | Arrêté du 28 août 2012, 1 retouche, 0 remplacé | idem | = |
| citants / jurisprudence | 7 / 11 | 7 / 11 | = |

### 2.3 HISTORIQUE — modèle (`H.counts`), identique aux deux vues

| Grandeur | histo-02 / histo-05 | v2 | | v2 au 01/01/2020 | histo-02 au 01/01/2020 |
|---|---|---|---|---|---|
| `total` | 36 | 36 | = | 36 | 36 |
| `n0` / `n1` / `n2` | 4 / 6 / 26 | 4 / 6 / 26 | = | 4 / 6 / 26 | 4 / 6 / 26 |
| `avant` / `apres` | 36 / 0 | 36 / 0 | = | **14 / 22** | **14 / 22** |
| `textes` / `distincts` | 25 / 24 | 25 / 24 | = | 25 / 24 | 25 / 24 |
| `vivants` | 10 | 10 | = | **13** | **13** |
| `exclus` | 7 | 7 | = | 7 | 7 |
| `redactions` / `arretes` | 4 / 4 | 4 / 4 | = | 4 / 4 | 4 / 4 |

Arbre obtenu, identique : 28 août 2012 [2 retouches, 0 préd.] · 12 mars 2013 [0, 0] ·
9 mars 2020 [3, 0] · 29 août 2025 [0, **11**].
Exclus, identiques et dans le même ordre : 13 avril 1993 · 23 juillet 2003 ·
4 septembre 2007 · 23 décembre 2010 · 22 février 2011 · 20 janvier 2017 · 2 mai 2018.

> Note : `exclus = 7`, pas 6. Le contre-audit relevait en R-2 que « l'arrêté du 20 janvier
> 2017 » était nommé dans une infobulle sans figurer nulle part ; la maquette a depuis été
> corrigée et le compte est passé à 7. **Les deux pages mesurent bien 7 aujourd'hui** : ce
> n'est pas un écart que j'introduis.

### 2.4 HISTORIQUE — vue Couloirs, éléments rendus au 13/09/2026

| Grandeur | histo-02 | v2 | |
|---|---|---|---|
| lignes (`g2row` / `jl-cl__row`) | 32 | 32 | = |
| bouchons rouges d'abrogation (`g2cap` / `jl-cl__cap`) | **15** | **15** | = |
| encoches de retouche (`g2notch`) | 13 | 13 | = |
| losanges de retouche (`g2mark`) | 13 | 13 | = |
| segments de rédaction (`g2seg`) | 4 | 4 | = |
| lignes de niveau 1 mortes / futures | 2 / 0 | 2 / 0 | = |
| éléments « réécrit » (`.mod` / `.is-mod`) | 2 | 2 | = |
| stub « déjà listé plus haut » (dans le DOM) | 1 | 1 | = |

### 2.5 HISTORIQUE — vue Couloirs au 1er janvier 2020

| Grandeur | histo-02 | v2 | |
|---|---|---|---|
| lignes n1 mortes / futures | 1 / 2 | 1 / 2 | = |
| éléments atténués (`jl-hfutur`) | 8 | 8 | = |
| occurrences de « sera abrogé » | 12 (+2 dans le `<script>` inline) | 12 titres + 12 `aria-label` | voir §4 |

### 2.6 HISTORIQUE — vue Poupées russes au 13/09/2026

| Grandeur | histo-05 | v2 | |
|---|---|---|---|
| accordéons (`p5acc` / `jl-pr__acc`) | 23 | 23 | = |
| accordéons de niveau 2 | 14 | 14 | = |
| … dont morts / futurs / « réécrit » | 13 / 0 / 1 | 13 / 0 / 1 | = |
| mentions d'abrogation (`p5ab` / `jl-pr__ab`) | 12 | 12 | = |
| ouverts au chargement | 5 | 5 | = |
| lignes de retouche (`p5ret` / `jl-pr__ret`) | 13 | 13 | = |
| segments de frise (`p5seg` / `jl-pr__seg`) | 17 | 17 | = |
| stub « déjà listé plus haut » (DOM) | 1 | 1 | = |
| « aussi pris pour lui (plus haut) » (DOM) | 1 | 1 | = |
| « tout déplier » → accordéons ouverts | 22 / 23 | 22 / 23 | = |

La liste des 14 blocs de niveau 2 a été comparée **ligne à ligne** : mêmes textes, mêmes NOR,
mêmes libellés d'état, même ordre antichronologique, y compris les deux « Arrêté du 7 avril
2009 · JUSC0907573A » dont l'un porte « abrogé le 1er sept. 2025 » et l'autre
« **réécrit le 1er janv. 2020** ».

### 2.7 HISTORIQUE — vue Poupées russes au 1er janvier 2020

| Grandeur | histo-05 | v2 | |
|---|---|---|---|
| accordéons | 23 | 23 | = |
| niveau 2 morts / futurs | 2 / 2 | 2 / 2 | = |
| mentions d'abrogation | 1 | 1 | = |
| éléments atténués | **7 classe + 7 `style="opacity:.35"`** = 14 | **14, tous par la classe** | voir §4 |

---

## 3. COMPOSANTS AJOUTÉS

Tous ajoutés **en fin de fichier**, dans une section datée et nommée, sans renommer ni
redéfinir une seule règle existante.

### 3.1 `web/styles/jl.css` — section 28, l. 1043-1323

| Sous-section | Composants | Origine |
|---|---|---|
| 28.1 Chrome de page | `.jl-titrepage` `.jl-leadrow` `.jl-lead` `.jl-when` (+`--passe`) `.jl-kicker--pilule` `.jl-aide` `.jl-datepop__chips` `.jl-nor` | `carte-748.html:40-44, 182-184` · `histo-02.html:215` · l'infobulle `?` de `carte-748.html:95-97` |
| 28.2 Trois colonnes | `.jl-cols` `.jl-col` (+`--mid`) `.jl-coltete` `.jl-sub` `.jl-empty` `.jl-colfoot` | `carte-748.html:100-106, 180-187` |
| 28.3 Bandeau d'étage | **`.jl-etage__t`** (teal, majuscules) + **`.jl-etage__c`** (bulle teal, chiffre seul) `.jl-racine` `.jl-kids` | `carte-748.html:204-210` |
| 28.4 Texte de l'article | `.jl-alin` `.jl-al` `.jl-nota` | `carte-748.html:82-86` |
| 28.5 Jurisprudence | `.jl-juris` `.jl-jgrid` `.jl-jc` (+`__m __t __x __ap`, `--ancienne`) `.jl-rd` (+`--ancienne`) | `carte-748.html:162-175` |
| 28.6 Chrome historique | `.jl-hbar` `.jl-hcount` `.jl-h2` `.jl-hsel` `.jl-hfutur` `.jl-htext` `.jl-hdiff ins/del` `.jl-hhonest` | `histo-02.html:226-247` |
| 28.7 Vue **Couloirs** | `.jl-cl` `__in __head __lbl __axis __yr __row __name __role __lane __grid __bar __seg __mark __cap __notch __today __todayl __after __tip` + `.is-dead .is-fut .is-mod .is-inf .is-sel .is-cur` | `histo-02.html:518-557` (`.g2*`) |
| 28.8 Vue **Poupées russes** | `.jl-pr` `__acc __h __ttl __cnt __chev __body __in __frise __seg __lnk __red __ret __ab __foot` + modificateurs | `histo-05.html:530-560` (`.p5*`) |
| 28.9 Impression | règles propres aux deux pages (voir §5) | neuf |
| 28.10 | `.jl-bande__v .jl-mono{overflow-wrap:anywhere}` | correctif mobile, voir §6 |
| 28.11 | `.jl-sub--enligne .jl-poids-normal .jl-fil--barre .jl-point--art .jl-pr__dt .jl-pr__h--inerte .jl-jc--jud/adm/ce/eu/txt/doc` | remplacent des `style=""` en ligne |

**Réutilisé sans rien ajouter** (c'était l'objet du normaliseur) : `.jl-bande` et `.jl-bande__k/__v`
(bande d'identité **sans boîte**), `.jl-pastille--ok/--morte/--q/--future`, `.jl-provenance`,
`.jl-honnetete`, `.jl-alerte--icone`, `.jl-bouton` / `--cta` / `--ghost` / `--icone` / `--sm`,
`.jl-vue`, `.jl-filtre`, `.jl-datew` / `.jl-calbtn` / `.jl-datepop`, `.jl-lt` et ses cinq
registres, `.jl-arbre` / `.jl-noeud`, `.jl-point`, `.jl-titre--h1` et son `em`, `.jl-surtitre`,
`.jl-chip`, `.jl-tag--*`, `.jl-src`, `.jl-warnp`, `.jl-carte`, `.jl-artlink`, `.jl-mono`,
`.jl-muted`, `.jl-rail`, `.jl-app`, `.jl-body`, `.jl-pied`, `.jl-proto`, `.jl-fil`,
`[data-align="fin"]`, `[data-espace="haut"]`.

### 3.2 `web/jl.js` — l. 986-1046, **IIFE séparée**

Un seul composant : **`JL.bindDatePop(onPick, root)`** (`web/jl.js:1001`), le popover de date
de `inventaire_composants_13sept.md` §2.12 — saisie `jj/mm/aaaa` avec le message d'erreur
du prototype au mot près (« Date illisible : attendu jj/mm/aaaa »), calendrier natif, puces
« sauter à une rédaction », fermeture au clic extérieur et à `Échap`, `aria-expanded`.

Il est écrit dans une **IIFE indépendante ajoutée après** `})(window);`, c'est-à-dire qu'il ne
modifie **aucune ligne** de ce qui précède — ni l'objet `JL`, ni `init()`, ni la section 27
que l'autre agent a ajoutée entre-temps à l'intérieur de l'IIFE principale. `node --check` : OK.

### 3.3 `web/v2/article.js` — le modèle partagé, 636 l.

Comme demandé : **un seul fichier de modèle pour les deux pages**, sans dupliquer les helpers
de `jl.js`. Il prend sur `window.JL` : `esc`, `fmtDate`, `fmtCourt`, `parseFr`, `$`, `$$`,
`nb`, `plur`, `pastille`, `noteProvenance`, `copy`. Il ne réimplémente que le **domaine** :

- `legifrance`, `lifeAt` (l. 67), `minus` (l. 84), `clean`, `titreArr`, `acc` (l. 95),
  `words`/`jaccard`, `diffWords`, `pill`, `howHTML`, `linkArtsLEGI`, `linkArts` ;
- `loadModel` (l. 201) → étages 1/2/3, citants, exclus, jurisprudence fusionnée ;
- `loadHisto` (l. 404) → `redactions`, `arretes`, `retouchesOf` (l. 460),
  `predsOf` **récursif** (l. 475), `flatPreds`/`flatRet`, `exclus` **avec raison**, `ev`, `counts` ;
- le chrome commun : `whenBadge`, `datePopHTML` (l. 593), `bandeHTML`, `aide`.

`acc(n, un, plus)` est l'accordeur de pluriel d'`histo-02.html:317`, avec sa forme
« aucune retouche ». Il est **volontairement local** et ne s'appelle pas `nb` : le piège n° 2
du normaliseur (`jl.js:97-105`) réserve `nb` au formateur de nombres et `plur` à l'accord
sans forme « aucun ». Les deux coexistent sans collision.

---

## 4. ÉCARTS ASSUMÉS AVEC LES MAQUETTES

Quatre, tous dans le sens de la règle, tous mesurés.

| # | Écart | Pourquoi |
|---|---|---|
| 1 | **Accessibilité des marqueurs de la frise.** `g2mark`, `g2cap` et `g2notch` n'avaient ni `role`, ni `tabindex`, ni `aria-label` (G3-3, resté « PARTIELLEMENT » au contre-audit). Les miens en ont tous. L'infobulle se remplit aussi au `focus`, pas seulement au `mouseenter`. | L'information était **inatteignable au clavier et au tactile**. Effet de bord mesuré : les chaînes « sera abrogé » passent de 12 à 24 occurrences dans le HTML (12 `title` + 12 `aria-label`). Le nombre de bouchons, lui, est identique (15). |
| 2 | **`opacity:.35` en ligne remplacé par la classe `.jl-hfutur`.** `histo-05.html:580` atténuait les retouches futures par un `style=""` calculé. | Le mandat interdit le style en ligne. Total d'éléments atténués **identique** (14 au 01/01/2020) ; simplement 14 par la classe au lieu de 7 + 7. Au passage `.jl-hfutur` passe de `opacity:.32;filter:grayscale(1)` à `opacity:.45` : G3-2 signalait l'empilement d'opacités sur une ligne déjà `--muted` comme illisible. |
| 3 | **La bascule Couloirs / Poupées russes ne recharge plus la page.** Les maquettes sont deux fichiers reliés par deux `<a href>`. Ici c'est une seule page, deux boutons `role="tab"`, `history.replaceState` et un nouveau rendu. | Une seule page, un seul modèle chargé une seule fois. La **date lue est conservée** (vérifié : `?date=2020-01-01` → clic → `?date=2020-01-01&vue=poupees`, badge « lu au 1er janv. 2020 » inchangé). |
| 4 | **Renvoi retour dans Poupées russes.** G2-5 était « PARTIELLEMENT » corrigé : l'arrêté du 29 août 2025 est signalé comme « aussi pris pour lui (plus haut) » quand il apparaît en retouche, mais son propre bloc ne disait pas qu'il figure ailleurs comme retouche. Le bloc l'écrit désormais : « Il retouche aussi l'arrêté du 9 mars 2020 : il figure alors plus bas comme "arrêté modificateur". » | Le renvoi était à sens unique. Le compte de « aussi pris pour lui (plus haut) » reste 1. |

---

## 5. VÉRIFICATIONS FAITES DANS LE NAVIGATEUR

`http://localhost:8787/v2/article.html` et `/v2/historique.html`, onglet dédié (l'autre agent
pilotait l'onglet partagé).

| Contrôle | Résultat |
|---|---|
| Erreurs console, `article.html` (aujourd'hui, `?date=2020-01-01`) | **aucune** |
| Erreurs console, `historique.html` (Couloirs, Poupées, aux deux dates, après bascule) | **aucune** |
| Comptes vs maquettes | **identiques**, chiffre par chiffre — voir §2, 7 tableaux |
| Bascule Couloirs ↔ Poupées russes | OK, sans rechargement, URL mise à jour, **date lue conservée** |
| Popover de date — ouverture | OK (après correction, voir §6) |
| Popover — puce « 27 déc. 2018 » | → `?date=2018-12-27&num=748-6&vue=couloirs`, badge « lu au 27 déc. 2018 » |
| Popover — saisie `01/01/2020` + « Lire » | → `?date=2020-01-01&num=748-6`, `cur = 2019-05-05`, étage 2 = 1 arrêté |
| Popover — fermeture au clic extérieur et à `Échap` | câblées (`jl.js:1036-1045`) |
| Accordéons Poupées — un par un | ouvre puis referme |
| « tout déplier » / « tout replier » | 22 accordéons sur 23 (le 23ᵉ est le stub, qui n'a pas de corps — **comme la maquette**) |
| Segments de rédaction cliquables → diff mot à mot | OK, sélection à deux segments, désélection au reclic |
| Ancres | `#historique` et `#jurisprudence` présents sur `article.html` |
| « ← Résultats » | masqué sans référent de recherche (`#backrow[hidden]`), comportement attendu |
| 1280 px, clair | conforme ; capture prise |
| 1280 px, sombre | conforme ; capture prise (bandeaux d'étage, bulles, pastilles, barres de la frise et accordéons tiennent tous en sombre) |
| 390 px (émulation 375) | **débordement horizontal = 0 px** sur les trois pages/vues ; rail masqué, burger de `topbar.js` présent ; colonnes empilées ; la frise Gantt défile **dans son propre conteneur** (1116 px de contenu pour 341 px de large), le corps de page ne défile pas |
| Impression (règles `@media print` injectées comme feuille d'écran) | header, rail, actions, popover, bascule de vue, sélecteurs masqués ; colonnes et grille de jurisprudence remises en blocs ; fond blanc ; **mise en page desktop sur le papier**, pas la mobile ; **les 22 accordéons ouverts** (22/22) ; captures prises |
| Styles en ligne dans le corps rendu | `historique.html` : **zéro**. `article.html` : trois, dont **aucun n'est de moi** (`--topbar-h` posé par `jl.js`, et deux `style="color:var(--muted)…"` posés par `JL.renderRail()`). Les seuls `style=""` que mes scripts émettent sont les `left:%` / `width:%` de la frise, qui sont de la **donnée** (positions temporelles), pas de la mise en forme |
| `node --check` | `jl.js`, `article.js`, `carte.js`, `histo.js` : OK |
| `decision-jl.html` après mes ajouts | rendu conforme, **aucune erreur console** ; capture prise |
| `composants.html` après mes ajouts | rendu conforme, **aucune erreur console** ; capture prise |
| « Copier pour un LLM » | bloc de 5,4 k caractères vérifié en entier : référence, rédaction datée (« en vigueur au 13 septembre 2026, applicable du 1er septembre 2025 (toujours en vigueur) »), identifiant + URL LEGI, les 5 alinéas, le cadre normatif complet (auteur, 2 arrêtés, leurs 3 retouches, les 11 remplacés nommés, chacun avec son NOR et son lien LEGI), les 7 textes qui le mentionnent, la provenance et les consignes |

**La bizarrerie connue est toujours là** : dans l'outil de prévisualisation, toute capture
prise après un défilement revient vide. C'est le même défaut que `normaliseur_13sept.md` §5,
il n'est pas propre à mes pages. Les captures ont donc été prises en haut de page.

---

## 6. UN VRAI BOGUE TROUVÉ ET CORRIGÉ EN COURS DE ROUTE

Le popover de date **ne s'ouvrait pas**, sans aucune erreur console, sur les deux pages.

Cause : j'avais placé `<span class="jl-datew">…<div class="jl-datepop">` à l'intérieur d'un
`<p class="jl-lead">`. Le parseur HTML ferme d'office un `<p>` dès qu'il rencontre un `<div>` :
le popover était donc **extrait du `.jl-datew`**, `bindDatePop` ne le trouvait plus
(`w.querySelector('[data-jl-datepop]')` → `null`), posait quand même `data-bound="1"` et
n'attachait aucun écouteur. Le bouton était inerte et muet.

Correction : `<div class="jl-lead">` au lieu de `<p>`, dans les deux pages
(`web/v2/carte.js:250-253`, `web/v2/histo.js:426-428`), avec le commentaire qui dit pourquoi.
C'est d'ailleurs ce que faisaient les maquettes (`carte-748.html:478` : `<div class="lead">`).

Deux autres correctifs mineurs pris au passage :
- un identifiant `LEGIARTI…` est plus long qu'une colonne de 375 px et se faisait tronquer
  sans point de coupure → `.jl-bande__v .jl-mono{overflow-wrap:anywhere}` (`jl.css:1306-1308`) ;
- neuf `style=""` en ligne que j'avais écrits par facilité sont devenus neuf classes
  (`jl.css:1310-1323`).

---

## 7. CE QUI N'A PAS PU ÊTRE PORTÉ, ET POURQUOI

| Élément | Pourquoi |
|---|---|
| **Le calendrier fabriqué en JS** (`.cal` de `hub.html:205-217`, `openCal()` 719-744) | `inventaire_composants_13sept.md` §2.12 le veut **dans** le popover, à la place de l'`input type=date` natif. `normaliseur_13sept.md` §4 l'avait déjà laissé dehors pour la même raison : c'est ~200 lignes de rendu JS qui vivent dans `hub.html`, fichier que je ne peux ni lire en entier dans mon budget ni tester. Le contenant est fait et les trois entrées sont là ; le contenu du milieu reste l'`input type=date` natif. **Deuxième passe.** |
| **Le compteur global d'événements ne bouge toujours pas avec la date lue** (G2-1, « PARTIELLEMENT ») | `total = 36` et `n0/n1/n2 = 4/6/26` à toutes les dates, comme dans les maquettes. La mention « X avant la date lue, Y après » est bien là et bouge (14/22 au 01/01/2020). Faire bouger le gros chiffre est une **décision de sens** — « événements retenus » veut-il dire « tout ce que je sais » ou « tout ce qui a déjà eu lieu » ? — que je ne prends pas seul. Voir §8. |
| **« 25 textes » compte un arrêté deux fois** (R-1) | Le nombre affiché est maintenant accompagné de « (24 distincts) » avec l'infobulle qui explique le double identifiant sous un même NOR. La déduplication par NOR/CID **n'est pas faite** : elle changerait la liste affichée, pas seulement le compte. Voir §8. |
| **Le clamp de l'axe pour un texte né avant 2008** (G2-9, « PARTIELLEMENT ») | `Math.min(Math.max(y, Y0), Y1)` est repris tel quel. La pointe `.is-inf` distingue « sans limite » d'une fin en 2027 ; le cas inverse (né avant 2008) reste écrasé sans marque. Aucun texte du jeu n'est dans ce cas. |
| **`.jl-cl__seg` sous 10 px** (G3-2) | Le millésime dans un segment est en `--text-3xs` (10 px), comme la maquette. Le contraste est réglé (fond `--ok-bg`, texte `--ok`, opacité 1), la taille non : au-dessus, le millésime ne tient plus dans les segments courts. |
| **`diffWords` reste dans `article.js`** et n'est pas mis en commun avec `hub.html` | `hub.html` est en lecture seule pour moi, et `normaliseur_13sept.md` §4 avait déjà laissé les trois copies à fusionner. Mon exemplaire est le quatrième — mais c'est celui de la v2, et il est **partagé par les deux pages** au lieu d'être dupliqué entre elles. |
| **Le lien Légifrance d'un CODE** | `legifrance()` envoie tout `LEGITEXT` vers `/loda/id/`, y compris « Code de justice administrative » qui devrait aller vers `/codes/id/`. C'est le comportement de `carte-748.html:287`, repris **tel quel** pour ne pas créer d'écart non demandé. Voir §8. |
| **`jaccard` / `words`** | Quatre copies dans le prototype ; la mienne est dans `article.js` et sert les deux pages. Leur montée dans `jl.js` est une fusion de domaine, hors mandat. |

---

## 8. « À TRANCHER »

1. **Le gros chiffre « Événements retenus ».** Il vaut 36 à toutes les dates. Deux lectures
   possibles : (a) 36 = tout ce que la page sait de cet article, et la ventilation
   « 14 avant / 22 après » dit le reste — c'est l'état actuel, et c'est défendable ; (b) le
   gros chiffre devrait valoir 14 au 1er janvier 2020, puisque la page prétend se lire à
   cette date. **Ma proposition** : (a), mais en renommant le libellé « Événements connus »
   pour que le mot cesse de promettre une lecture à la date. Je n'ai rien renommé.

2. **« 25 textes (24 distincts) ».** Le second « Arrêté du 7 avril 2009 » est le même arrêté
   sous un second identifiant Légifrance. Faut-il (a) le garder affiché deux fois, comme
   aujourd'hui, avec la mention « 24 distincts » et l'étiquette « réécrit le 1er janv. 2020 »
   — c'est honnête et ça montre ce que contient la base ; ou (b) fusionner les deux entrées
   par NOR + CID en une seule ligne à deux périodes ? **Ma proposition** : (a) tant que la
   règle « deux LEGITEXT même NOR non fusionnés » tient — elle est dans tes règles de fond,
   donc je n'y ai pas touché — mais il faudra (b) le jour où un texte aura trois identifiants.

3. **Le lien d'un CODE vers Légifrance.** Aujourd'hui `legifrance()` envoie
   `LEGITEXT000006070933` (code de justice administrative) vers `/loda/id/…`, qui n'est pas
   le bon fonds pour un code. Le nom de la règle est « citation = lien », et là le lien tombe
   à côté. **Ma proposition** : ajouter une branche « si `nature === 'CODE'` → `/codes/id/` ».
   Je ne l'ai **pas** faite, parce qu'elle ferait diverger la v2 de la maquette sur un point
   que tu n'as pas arbitré, et que le mandat impose l'égalité des comptes et des rendus.

4. **Le résolveur de thème en tête de page.** Les deux pages portent le même `<script>` inline
   de deux lignes que `decision-jl.html`, avant les feuilles, pour éviter le flash blanc en
   thème sombre. C'est le point 1 de « À TRANCHER » de `normaliseur_13sept.md` §6, resté
   ouvert. J'ai suivi le précédent de `decision-jl.html`. **Si tu le refuses**, il faut le
   retirer des deux pages **et** de `decision-jl.html`, et accepter le clignotement.

5. **`.jl-hfutur` est passé de `opacity:.32 + grayscale(1)` à `opacity:.45`.** C'est un
   changement visuel volontaire (G3-2 : l'empilement avec `--muted` rendait le texte
   illisible). **Signalé parce que ça se voit** : ce qui est postérieur à la date lue est un
   peu plus lisible qu'avant.

6. **`.jl-h2` en noir.** `histo-02.html:234` le déclarait en 10 px majuscules mais en `--ink`
   et gras — métrique de sur-titre, couleur de titre. J'ai appliqué ta règle « noir = titre de
   section » et gardé `--ink`. C'est le point 5 de « À TRANCHER » du normaliseur, toujours
   ouvert : si tu le voulais en sur-titre gris, il faut le dire pour les deux pages d'un coup.

7. **Deux bascules de thème coexistent toujours** (celle de `topbar.js`, binaire, et celle du
   rail, à trois états). Inchangé, et hors mandat : `topbar.js` est interdit en écriture.
   C'est le point 2 de « À TRANCHER » du normaliseur.

---

## 9. FICHIERS PRODUITS

- `web/v2/article.html` — 70 l., page « maintenant ». Aucun style ni script inline hors
  head SEO, JSON-LD, résolveur de thème (§8.4) et bloc de données `#jl-page`.
- `web/v2/historique.html` — 65 l., idem.
- `web/v2/article.js` — 636 l., **le modèle partagé** (`window.ART`).
- `web/v2/carte.js` — 313 l., rendu de la page « maintenant ».
- `web/v2/histo.js` — 525 l., rendu des deux vues et de la bascule.
- `web/styles/jl.css` — section **28** ajoutée en fin de fichier (l. 1043-1323).
- `web/jl.js` — **IIFE séparée** ajoutée en fin de fichier (l. 986-1046), `JL.bindDatePop`.

Aucun fichier hors de ce périmètre n'a été écrit. Aucun commit.
