# La page de recherche de la refonte, `web/v2/recherche.html` (13 septembre 2026)

Mandat : construire la page de recherche sur le normaliseur (`web/styles/jl.css` + `web/jl.js` + `web/topbar.js`), à partir du prototype `web/hub.html` ET de la page de prod `web/search.html`.

Cahier des charges : [`inventaire_composants_13sept.md`](inventaire_composants_13sept.md) (§5.1) et [`normaliseur_13sept.md`](normaliseur_13sept.md).

---

## 0. MANIFESTE DE COUVERTURE

| Fichier | Lignes | Lu jusqu'à | État |
|---|---|---|---|
| `scratchpad/audit/inventaire_composants_13sept.md` | 605 | 605 | **lu en entier**, en deux passes (1-270, 271-470) ; §5.1 (l. 355-378) et §6 (l. 404-470) relus mot à mot |
| `scratchpad/audit/normaliseur_13sept.md` | 297 | 297 | **lu en entier**, y compris la table de correspondance (§2) et les 8 « À TRANCHER » (§6) |
| `web/styles/jl.css` | 824 (avant) | 824 | **lu en entier** |
| `web/jl.js` | 618 (avant) | 618 | **lu en entier** |
| `web/hub.html` | 1382 | 1382 | **lu en entier**, en cinq passes (1-371, 372-771, 772-951, 952-1111, 1112-1382) |
| `web/search.html` | 2674 | 2674 | **lu en entier**, en six passes (1-200, 200-699, 699-1158, 1159-1618, 1618-2077, 2078-2674) |
| `web/maquettes/decision-jl.html` | 129 | 129 | **lu en entier** (exemple d'assemblage) |
| `web/topbar.js` | 243 | 0 | **NON LU** : absorbé par les citations du rapport §1 (topbar.js:17-50, 56-160, 184-241). Le fichier est interdit en écriture et la page ne fait que poser `<div data-topbar-mount>` ; aucune décision de cette page n'en dépend. |
| `ssr.py`, `web/index.html`, `web/annuaire.html` | n/a | 0 | **NON LUS** : interdits en écriture et intégralement inventoriés par le rapport. |

**Fichiers écrits** (aucun autre) :
- `web/v2/recherche.html` : 213 lignes ;
- `web/v2/recherche.js` : 1003 lignes ;
- `web/styles/jl.css` : §27 ajoutée + §26 étendue ;
- `web/jl.js` : bloc « Droit / recherche » ajouté.

Aucun commit. Aucune page de production modifiée.

**Collision constatée.** Pendant ce travail, une autre session écrivait `web/v2/article.html`, `article.js`, `carte.js`, `histo.js`, `historique.html` et complétait elle aussi `jl.css` et `jl.js` (jl.js est passé de 618 à 1046 lignes, jl.css de 824 à 1336). Je n'ai touché à aucun de ces fichiers ; mes ajouts à `jl.css` et `jl.js` sont des blocs neufs, sans renommage. `node --check jl.js` et `node --check v2/recherche.js` passent sur l'état final du disque.

---

## 1. LES 20 POINTS DE §5.1, DANS L'ORDRE D'IMPORTANCE DU MANDAT

| # | Point (rapport §5.1) | État | Où |
|---|---|---|---|
| 1 | **Ne jamais dire « aucun résultat » quand une source n'a pas répondu** + bouton Relancer + relance automatique | **FAIT** | trois « vides » distincts : `v2/recherche.js:527` (en cours), `v2/recherche.js:529-535` (« Recherche incomplète », bouton Relancer), `v2/recherche.js:540-542` (« Aucun résultat », **seulement** quand toutes les sources ont répondu). Bandeau quand il y a des résultats mais un fonds muet : `v2/recherche.js:467-472`. Relance automatique à 60 s : `v2/recherche.js:394-405`, appelée `v2/recherche.js:332`. Règle en tête de fichier : `v2/recherche.js:15-17` |
| 2 | **Distinction refus 4xx / délai dépassé** | **FAIT** | interception du 4xx : `v2/recherche.js:358-361` ; refus renvoyé par le corps JSON : `v2/recherche.js:363` ; état `delai` : `v2/recherche.js:372`. Rendu séparé : alerte rouge pour le refus `v2/recherche.js:461-465`, honnêteté ambre pour le délai `v2/recherche.js:467`. Les refus **ne sont pas rejoués** : `v2/recherche.js:395-398` ne retient que `etat === 'delai'` |
| 3 | **Entrelacement des résultats par source en mode pertinence** | **FAIT** | `JL.entrelacer` dans `jl.js:762-790` (reprise de search.html:1467-1502, `ORDRE_SOURCES` inchangé : `dila, admin, ariane, legi, cedh, cjue, doctrine`) ; appel `v2/recherche.js:550` |
| 4 | **URL de page partageable en query string** (pas un hash) | **FAIT** | `syncUrl()` `v2/recherche.js:214-227` par `history.replaceState` sur `location.pathname + '?' + p` ; relecture au chargement `lireUrl()` `v2/recherche.js:229-249`. Paramètres : `q`, `juridiction`, `lieu`, `formation`, `date_min`, `date_max`, `sort`, `thes` |
| 5 | **Panneau latéral d'article de loi à la rédaction d'époque, cache localStorage** | **FAIT** | panneau `v2/recherche.html:170-188` ; ouverture `v2/recherche.js:727-737` ; résolution + cache `v2/recherche.js:741-752` ; cache 24 h + éviction LRU à 500 entrées dans `jl.js:855-883` (`cacheLoiGet` / `cacheLoiSet`, repris de search.html:1780-1813). La date d'époque est **lue sur la carte** (`data-date`), jamais devinée : `v2/recherche.js:986-989` |
| 6 | **Bottom sheet mobile** | **FAIT** | même panneau, CSS seul : `styles/jl.css` §27.7 (`@media (max-width:860px)` : `inset` bas, hauteur 88 vh, `translateY(100%)`, poignée). Vérifié à 390 px : `top` 101 px, largeur 390 px, hauteur 743 px |
| 7 | **`highlightLawRefs` repris tel quel dans jl.js sous le nom `JL.lierArticles`** | **FAIT** | `jl.js:569-677`. 22 codes, 6 conventions, règlements UE, directives, lois, décrets, ordonnances, marqueur `\x00LAWREF\x00`, classe `lawref` : tout est identique à search.html:1246-1414. Seule adaptation : `matchAll` (ES2020) réécrit en boucle `exec` pour rester ES2018 comme le reste de jl.js, et `split(/(?<=\.)\s+/)` de `decouperTexte` privé de son lookbehind. Appliqué aux extraits de résultats `v2/recherche.js:571` et au texte de l'article `v2/recherche.js:788` |
| 8 | **Garde-fou double envoi** | **FAIT** | `v2/recherche.js:272-289` (`S.enVol` + désactivation du bouton), plus l'acceptation de toutes les formes de la touche Entrée : `JL.estEntree` `jl.js:920`, branchée `v2/recherche.js:890` |
| 9 | **Filtre par lieu (`INSTANCES`)** | **FAIT** | table reprise telle quelle dans `jl.js:792-820` (41 TA, 9 CAA, 36 CA) ; champ conditionnel `v2/recherche.js:133-143`, libellés « Tous TA » / « Toutes CAA » / « Toutes CA » `v2/recherche.js:138` ; champ `v2/recherche.html:110-116` |
| 10 | **Menu de juridiction à deux niveaux** | **FAIT** | markup `v2/recherche.html:86-105` (`.jl-menu__group` = famille, `.jl-menu__item--sub` = fonds) ; un groupe sélectionne ses trois sous-entrées : `v2/recherche.js:900-911` ; synchronisation avec les cases du panneau : `majMenuJuri()` `v2/recherche.js:110-129` |
| 11 | **Pastilles de thésaurus retirables une à une** | **FAIT** | `v2/recherche.js:690-722` ; chaque pastille porte son `×` (`v2/recherche.js:702-704`) et son infobulle « Ajouté pour le terme « … » » ; `.jl-exp__pill.is-removed` (barré, opacité .4) dans `jl.css` §27.2 ; lien « chercher les mots exacts » `v2/recherche.js:712-718` |
| 12 | **Téléchargement `.txt`** | **FAIT** | `JL.telecharger` `jl.js:909-916` (repris de search.html:1744-1756) ; bouton « Télécharger .txt » du panneau d'article `v2/recherche.html:183`, câblé `v2/recherche.js:940-947` (l'en-tête du fichier porte la référence, la rédaction et la licence) |
| 13 | **Signalement : ticket GitHub pré-rempli, adresse assemblée au clic** | **FAIT** | `JL.urlSignalement` `jl.js:889-897` ; `JL.bindMailR` `jl.js:898-907` ; modale `v2/recherche.html:191-203` ; ouverture depuis chaque carte de résultat (`data-signal`, `v2/recherche.js:604-605`, `v2/recherche.js:931-934`) et depuis le panneau d'article (`v2/recherche.js:948-951`). **Vérifié** : `mailto:` absent du HTML source, présent seulement après le clic |
| 14 | **Bouton « source officielle » raisonné, refus explicite pour les TA/CAA** | **FAIT, et un défaut de prod relevé** | `JL.sourceOfficielle` `jl.js:734-760`, copie exacte de search.html:2092-2128 (refus `null` pour `DCE_/DCAA_/DTA_/ORTA_`, `jl.js:751`). **⚠ Constat** : les identifiants réellement servis par l'API sont en `DCA_` (ex. `DCA_22NC02724_…`), que le motif de search.html:2111 **ne couvre pas** : l'encadré honnête ne s'affichait donc jamais pour les CAA. Corrigé **à l'affichage seulement** (`v2/recherche.js:601-607` ajoute `DCA_`), la fonction reste la copie exacte. Vérifié au navigateur : la carte « CAA de Nancy : n° 22NC02724 » porte bien « pas de page officielle » avec son explication |
| 15 | **Découpage en paragraphes d'un texte concaténé** | **FAIT** | `JL.decouperTexte` `jl.js:679-732` (= `splitLegalBlock`, search.html:1151-1206 : les 14 marqueurs juridiques, les alinéas numérotés, le repli à 1500 caractères) ; appliqué au texte d'article quand il arrive en un seul bloc : `v2/recherche.js:782-786` |
| 16 | **Champs vides marqués** | **FAIT** | normalisation `isEmpty` (traite `"undefined"` et `"null"` comme vides) `v2/recherche.js:565` ; rendu `.jl-vide` pour juridiction, date, numéro et ECLI : `v2/recherche.js:582`, `584`, `591`, `593` ; style `jl.css` §27.3 |
| 17 | **Feuille d'impression complète, avec le point de rupture qui s'active sur A4** | **FAIT** | `jl.css` §26, bloc « Page de recherche » : masquage de l'interface, **neutralisation explicite des points de rupture 860 px ET 900 px** (A4 ≈ 794 px), résultats insécables, URL officielle écrite en toutes lettres, panneau d'article imprimé en bloc après la liste, pied de provenance. Plus un bloc `.jl-recap-impression` qui n'existe **que** sur le papier et porte la requête, les filtres et l'adresse (`v2/recherche.html:38`, rempli `v2/recherche.js:252-259`). Renommage du PDF par la requête : `v2/recherche.js:962-972` (transposition de search.html:2656-2671) |
| 18 | **Pagination « Charger la suite » avec état par source et totaux réels** | **FAIT** | offsets par source `v2/recherche.js:611-622` et `625-637` ; totaux `total` / `total_exact` lus `v2/recherche.js:379-382` et affichés (« sur 4 134 environ existants ») `v2/recherche.js:483-484`. **Vérifié** : 22 → 206 cartes après un clic, détail « CJUE : 60 / 122 · DILA : 60 / 3 949 » |
| 19 | **Compteur de filtres actifs** | **FAIT** | `nbFiltres()` `v2/recherche.js:172-175` (compte aussi le thésaurus coupé, comme hub.html:666) ; pastille `#advCount` `v2/recherche.html:76`, mise à jour `v2/recherche.js:195-197` |
| 20 | **Vue « toutes les versions » d'un article** (§5.1 n° 7) | **FAIT** | `v2/recherche.js:794-816`, bouton `v2/recherche.html:182` |

### Ce que le hub faisait déjà, et qui est là

| Fonctionnalité du hub | Où |
|---|---|
| rail « Chercher dans » (Jurisprudence actif, 4 scopes grisés « bientôt », outil « Vérifier mes citations ») | `JL.renderRail` piloté par le bloc de données `v2/recherche.html:180-202` (`#jl-page`) ; l'outil pointe vers la page existante `/hub.html#/citations` |
| barre de recherche réseau + panneau avancé (fonds, chambre, dates, thésaurus) | `v2/recherche.html:44-160` ; grille des fonds `v2/recherche.js:66-105` |
| éclaireur de référence `citation_only=1` | `v2/recherche.js:300-322` |
| pagination par source, totaux réels | voir point 18 |
| pastilles de source avec loader | `renderSources()` `v2/recherche.js:409-427`, sur `.jl-pastille--loader` de jl.css §3 |
| extraits compactés et coupés | `v2/recherche.js:567-570` (compactage des retours à la ligne bruts) puis `JL.clipExtract(…, 420)` |
| facettes calculées sur les résultats chargés, avec l'aveu | `v2/recherche.js:640-673` ; l'aveu « ces compteurs portent sur les résultats chargés » est en `.jl-honnetete` |
| tri (pertinence / récent / ancien) et mode (sommaire / extrait) | `v2/recherche.js:492-498` sur `.jl-vue--sm` |
| flux « Nouveautés » à défilement infini | `v2/recherche.js:822-860` + observateur `v2/recherche.js:978-981` |

### La lecture d'une décision

`v2/recherche.js:573` et `v2/recherche.js:853` : le lien d'une carte va vers **`/decision/<source>/<id>`**, la page serveur que Google indexe, jamais vers une vue JS. En local, `DECISION_BASE` pointe sur `https://justicelibre.org/decision` (`v2/recherche.js:25`).

---

## 2. CE QUI A ÉTÉ AJOUTÉ À `jl.css` ET `jl.js`

Aucun renommage, aucune suppression : uniquement des blocs neufs.

### `web/styles/jl.css`

| Ajout | Contenu |
|---|---|
| **§27, « PAGE DE RECHERCHE »** | 27.1 panneau avancé (`.jl-adv`, `.jl-fam__h`, `.jl-fam__all`, `.jl-fch`, `.jl-thes`, `.jl-advcount`, `.jl-advsum`) · 27.2 pastilles de thésaurus (`.jl-exp`, `.jl-exp__pill`) · 27.3 résultats (`.jl-resultat`, `.jl-vide`, `.lawref`, `.jl-plus`) · 27.4 facettes (`.jl-facettes`, `.jl-frow`, `.jl-hist`) · 27.5 flux (`.jl-flux__carte`) · 27.6 panneau d'article (`.jl-loi`, `.jl-voile`) · 27.7 bottom sheet mobile · 27.8 modale de signalement (`.jl-mail-r`) · 27.9 mise en page (`.jl-hero`, `.jl-lead`, `.jl-hint`, `.jl-kb`, `.jl-compte`, `.jl-petit`, `.jl-teal`) |
| **§26 étendue** | bloc « Page de recherche » : neutralisation des points de rupture sur A4, `.jl-recap-impression`, résultats insécables, URL écrites, panneau d'article en page suivante, pied de provenance |
| **§2 corrigée** | sous 900 px le rail devient une colonne d'icônes de 52 px **et le corps réserve la place** (`.jl-rail+.jl-body{padding-left:64px}`). Avant, le titre passait **sous** le rail en position fixe : défaut hérité de hub.html:93, constaté au navigateur à 390 px. `.jl-rail--cache+.jl-body` garde son padding normal, donc `decision-jl.html` n'est pas touchée |

### `web/jl.js`

| Ajout | Origine |
|---|---|
| `JL.lierArticles` | `highlightLawRefs`, search.html:1246-1414, **repris tel quel** |
| `JL.decouperTexte` | `splitLegalBlock`, search.html:1151-1206 |
| `JL.surlignerExtrait` | `highlightExtract`, search.html:1415-1431 (le surlignage sort en `<em class="jl-hl">`, le composant du normaliseur, au lieu d'un `em` nu) |
| `JL.sourceOfficielle` | `officialSourceFromId`, search.html:2092-2128 |
| `JL.entrelacer` + `JL.ORDRE_SOURCES` | search.html:1467-1502 |
| `JL.INSTANCES` | search.html:958-996 |
| `JL.FORMATIONS_FILTRABLES` | search.html:923-929 (seule la Cour de cassation est réellement filtrable) |
| `JL.FORMATION_LABELS`, `JL.fmtFormation` | search.html:2191-2204 (la version qui **développe**, contre l'abrégée de hub.html:571) |
| `JL.SOURCE_NAMES`, `JL.SRC_BADGES` | search.html:2211-2219, search.html:1141-1144 |
| `JL.FAM`, `JL.FAMLABEL` | hub.html:573-574 (6 familles) |
| `JL.cacheLoiGet` / `cacheLoiSet` | search.html:1780-1813 |
| `JL.urlSignalement`, `JL.bindMailR`, `JL.GITHUB` | search.html:2056-2066 et search.html:2080-2084 |
| `JL.telecharger` | search.html:1744-1756 |
| `JL.estEntree` | search.html:2574-2576 |

`init()` appelle en plus `bindMailR(document)` (`jl.js`, bloc de démarrage) : c'est idempotent et sans effet sur les pages qui n'ont aucun `.jl-mail-r`.

**Arbitrage repris du normaliseur, et tenu** : la classe posée par `lierArticles` reste `lawref` (et non `jl-artlink`). `jl-artlink` est un lien **déjà résolu** vers une rédaction connue (page décision) ; `lawref` est une citation **repérée par expression régulière**, dont la résolution peut échouer. Les confondre ferait passer une supposition pour un fait.

---

## 3. VÉRIFICATIONS FAITES DANS LE NAVIGATEUR

Toutes sur `http://localhost:8787/v2/recherche.html`, panneau de prévisualisation.

| Contrôle demandé | Résultat |
|---|---|
| **Aucune erreur console** | **aucune**, sur les 12 chargements testés (`read_console_messages onlyErrors` vide à chaque fois) |
| **« Cass. 2e civ., 10 sept. 2026, n° 23-20.368 » trouve l'arrêt par l'éclaireur** | **oui** : 1 résultat, bandeau « mode **référence** · numéro reconnu, le reste de la requête est ignoré », encadré « Référence reconnue : **23-20.368** · 10 septembre 2026 », et les quatre autres fonds marqués « non interrogée (référence reconnue) » et non « rien trouvé » |
| **« elephant » rend plusieurs sources ; « charger la suite » fonctionne** | **oui** : 88 résultats sur 4 104 existants, entrelacés DILA / ArianeWeb / HUDOC / EUR-Lex ; après un clic sur « Charger la suite », **206 cartes**, détail par source « CJUE : 60 / 122 · DILA : 60 / 3 949 » |
| **Requête vide** | « Saisissez une requête pour lancer une recherche. », l'URL est nettoyée, le flux « Nouveautés » revient (18 cartes) |
| **Requête à zéro résultat** (`xyzzyplughquux`) | « **Aucun résultat.** Toutes les sources interrogées ont répondu : il n'y a rien pour cette requête. » : la phrase n'est employée que dans ce cas |
| **Source en délai → « recherche incomplète », pas « aucun résultat »** | **oui**. `timeout=1` a été ajouté comme paramètre d'adresse (`v2/recherche.js:344-347`) pour forcer le délai envoyé à l'API. **Mais l'API répond quand même** dès que son index est chaud : `timeout=1` sur `sources=admin` ne rend `sources_no_result` que sur une requête froide (vérifié en `curl` : `q=grue cendree` → `['admin']`, `q=elephant` → `[]`). L'état a donc été **forcé au navigateur** en remplaçant `window.fetch` le temps du test, pour éprouver le vrai chemin de rendu : <br>· une source muette + des résultats → pastille « justice administrative · délai » et bandeau « **Recherche incomplète.** justice administrative n'a pas répondu : les résultats ci-dessous ne couvrent pas ce fonds. **Relancer** » <br>· **toutes** les sources muettes → « **Recherche incomplète.** Les fonds … n'ont pas répondu à temps : ce « rien » ne veut pas dire qu'il n'y a rien. Aucune conclusion ne peut être tirée de cette absence. **Relancer** » : et **jamais** « aucun résultat » <br>· refus 4xx sur DILA → pastille « DILA · refus » et alerte « DILA a refusé la requête : requête trop longue (limite 512 caractères). Ce n'est pas un délai dépassé : rejouer la même requête donnerait le même refus. » <br>· la relance automatique à 60 s a par ailleurs été **observée en conditions réelles** sur `"article 1240 du code civil"` filtré Cassation : pastille « seconde tentative, 60 s » |
| **1280 px** | conforme, capture prise (résultats, pastilles, facettes, panneau d'article ouvert à droite) |
| **390 px** | conforme, capture prise ; rail replié en colonne d'icônes, **débordement horizontal = 0 px**, bottom sheet vérifié (`top` 101 px, 390 × 743 px, poignée visible) |
| **Clair et sombre** | conformes, captures prises ; en sombre, pastilles, badges de fonds, surlignage, panneau d'article et facettes tiennent tous |
| **Impression** | vérifiée en injectant les 41 règles du bloc `@media print` comme feuille d'écran : rail, barre, pastilles, facettes, flux, boutons et bouton « signaler » masqués ; le **récapitulatif papier** s'affiche (requête, filtres, adresse) ; la **mise en page desktop** part sur le papier ; chaque résultat porte son URL officielle en toutes lettres ; le `<title>` devient « Recherche « grue cendree » · justicelibre.org » |
| **Panneau d'article à la rédaction d'époque** | clic sur `article 1240 du code civil` dans un extrait → « Article 1240 Code civil », « Rédaction du 21 mars 1804 au 1er oct. 2016 », pastille **MODIFIE**, mention « à la date du 29 juil. 1994 » (la date de la décision), entrée `law:CC:1240:1994-07-29` écrite dans `localStorage` |
| **Signalement** | modale ouverte depuis une carte, ticket GitHub pré-rempli avec l'élément et l'adresse ; le lien courriel vaut `#` dans le HTML et ne devient `mailto:contact@justicelibre.org` **qu'au clic** |
| **`web/maquettes/decision-jl.html`** | **intacte**, aucune erreur console, rendu conforme (capture) |
| **`web/maquettes/composants.html`** | **intacte**, aucune erreur console, 425 éléments `.jl-*` rendus (capture) |
| **Syntaxe** | `node --check jl.js` : OK · `node --check v2/recherche.js` : OK |
| **Styles en ligne** | **zéro** dans `recherche.html` ; dans `recherche.js`, il ne reste que les quatre `style="width:…%"` des barres d'histogramme et des squelettes, qui sont de la **donnée** et non du style (les sept styles statiques ont été sortis en classes `.jl-compte`, `.jl-petit`, `.jl-teal`) |
| **Scripts en ligne** | un seul, le résolveur de thème de 3 lignes en tête de `<head>` : voir « À trancher » n° 1 |

**Une bizarrerie à connaître, qui n'est pas une régression** : quand l'onglet du panneau de prévisualisation passe en arrière-plan, les **transitions CSS ne s'exécutent plus** et `getComputedStyle` rend la valeur figée à mi-chemin. Le panneau d'article paraissait alors mal positionné (`translateY(742)` au lieu de `translateY(0)`). En désactivant la transition le temps d'une mesure, la géométrie est exacte (`top` 101 px à 390 px, `left` 1270 px replié à 1280 px). Aucun changement de code n'a été fait pour cela.

---

## 4. « À TRANCHER » : ce que je n'ai pas décidé en silence

1. **Le script de thème en tête de page.** `recherche.html:23-25` porte, comme `decision-jl.html:23-25` et les 8 pages prod (`annuaire.html:6-9`), un `<script>` en ligne de 3 lignes qui pose `data-theme` avant les feuilles. Le mandat n'autorise en ligne que le head SEO et les données. **Proposition** : le garder : sans lui, la page clignote en blanc à chaque chargement en thème sombre. C'est le même arbitrage que le point 1 du normaliseur, non tranché depuis.

2. **`?timeout=N` dans l'adresse.** Ajouté (`v2/recherche.js:344-347`) pour pouvoir **provoquer** l'état « source en délai », comme le mandat le demande. C'est un cran de mise au point, pas une fonctionnalité : il force le délai envoyé à l'API **y compris pour la relance à 60 s**, qui ne peut donc pas aboutir tant qu'il est posé. **À dire** si tu veux qu'il disparaisse en production, ou qu'il n'agisse que sur la première passe.

3. **Le compteur du rail dit « 3,3 M », le hub disait « 4,3 M ».** J'ai repris le chiffre de `hub.html:592` (`TOTAL_TOUT = 3 285 952`, « tout ce qu'une recherche sans filtre atteint réellement »), pas celui des vignettes du rail (`hub.html:371`), parce que le rapport `justicelibre_rattrapage_sept2026` dit que le « 4,3 M » était faux. Les 986 000 décisions de l'open data TA/CAA restent affichées « bientôt », jamais comptées.

4. **Le badge de source dit le BACKEND, pas la famille.** `search.html:1577` affichait `source_label`, ce qui donnait « JUDICIAIRE » à côté du tag de famille « Judiciaire » : deux fois la même chose, et l'axe 1 effacé. J'ai mis les noms courts des backends (`DILA`, `ArianeWeb`, `JADE`, `HUDOC`, `EUR-Lex`, `v2/recherche.js:51-54`). C'est un **changement visible** par rapport à la prod, fait pour tenir le piège n° 3 du normaliseur.

5. **`lierArticles` produit parfois des `<span class="lawref">` imbriqués** (cas « article L. 521-1 du code de justice administrative » : la seconde passe sans préfixe remord dans le résultat de la première). Le défaut existe tel quel dans `search.html:1341-1348` et le mandat demandait la fonction **telle quelle** : je ne l'ai pas corrigé. Sans conséquence à l'usage (l'écouteur emploie `closest`), mais à corriger un jour **dans jl.js**, donc partout à la fois.

6. **Le texte intégral d'une décision n'est pas dans cette page.** La lecture ouvre `/decision/<source>/<id>`, comme demandé. `JL.lierArticles` et `JL.decouperTexte` y sont donc appliqués aux **extraits** et au **texte des articles de loi**, pas au texte d'un arrêt. C'est le seul endroit où la parité avec `search.html` change de support, parce que le mandat l'impose.

7. **Le filtre « chambre » est proposé dès que la Cour de cassation est cochée**, même parmi d'autres fonds (`v2/recherche.js:145`) ; il n'est envoyé qu'au plan `cass` (`v2/recherche.js:352`). `search.html:2427` le réservait au cas où la Cassation est **seule** sélectionnée. Ma version est plus permissive et reste honnête (le filtre n'est jamais appliqué à un fonds qui ne sait pas le traiter), mais c'est un écart.

8. **Le champ de date reste l'`input type=date` natif.** Le popover `.jl-datepop` du normaliseur existe, mais son calendrier (les 200 lignes d'`openCal()`, hub.html:719-744) n'a toujours pas été absorbé dans jl.js : c'est le point 1 du §4 du normaliseur, resté ouvert. La page affiche donc `mm/dd/yyyy` sur un navigateur en anglais.

---

/home/dahl/justicelibre/scratchpad/audit/v2_recherche_13sept.md
