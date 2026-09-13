# Les pages serveur `/decision/` et `/loi/` sur le normaliseur — 13 septembre 2026

Produit : `ssr_v2.py` (1 010 l.), `tests/test_ssr_v2.py` (364 l.),
5 pages de preuve dans `web/v2/ssr-preview/`, un aiguillage de **5 lignes**
dans `token_server.py`, une section datée de 28 lignes en fin de
`web/styles/jl.css`. **Aucun commit.** `web/jl.js` n'a pas été touché.

---

## 0. MANIFESTE DE COUVERTURE

| Fichier | Lignes | Lu jusqu'à | État |
|---|---|---|---|
| `ssr.py` | 1 621 | 1 621 | **lu en entier**, en deux passes (1-1010, 1010-1621). C'est le comportement à conserver ; tous les commentaires datés sont repris ci-dessous. |
| `web/maquettes/decision-jl.html` | 130 | 130 | **lu en entier** — c'est l'assemblage cible, reproduit balise par balise. |
| `scratchpad/audit/normaliseur_13sept.md` | 298 | 298 | **lu en entier** (les 5 pièges de fusion, la table de correspondance §2.4, les « À TRANCHER »). |
| `scratchpad/audit/inventaire_champs_13sept.md` | 738 | 738 | **lu en entier**, en deux passes (1-501, 502-738). |
| `tests/test_ssr_escaping.py` | 209 | 209 | **lu en entier**, copié en `tests/test_ssr_v2.py` avec l'import changé. |
| `sources/citations.py` | 159 | 159 | **lu en entier** (`detect_citations` l. 64, `linkify` l. 115). |
| `web/v2/article.html` | 70 | 70 | **lu en entier** (head, chrome, bloc `#jl-page`). |
| `web/styles/jl.css` | 1 341 → 1 369 | l. 710-812 (§24-25 + helpers), l. 992-1052 (§26 impression), l. 1053-1165 (§28), tail. Inventaire complet des 300+ noms de classes par `grep -o '\.jl-[a-z0-9_-]*'`. | **NON LU EN ENTIER** — j'ai lu intégralement les sections dont mes pages dépendent (texte de décision, sommaire latéral, impression, carte d'article) et j'ai la liste exhaustive des sélecteurs, ce qui suffit pour ne rien redéfinir. Les §1-23 (header, rail, pastille, chaîne, frise, boutons…) sont repris par `normaliseur_13sept.md` §2, lu en entier. |
| `web/jl.js` | 1 046 | l. 1-70 (en-tête + API), 510-560 (`bindLLMCopy`), 930-985 (`init`, objet `JL`), tail 40. | **NON LU EN ENTIER** — je n'écris pas dans ce fichier et je n'appelle rien d'autre que ce que `init()` câble tout seul. Les points de branchement (`[data-jl-rail]`, `[data-jl-print]`, `[data-copy]`, `[data-jl-llm]`, `.jl-toc`, `#backrow`, `#jl-page`) sont lus dans `init()` l. 933-949. |
| `web/maquettes/composants.html` | 304 | les 26 titres de section (`grep '<h2'`) + les blocs §24-25 (l. 242-256) | **NON LU EN ENTIER** — c'est un catalogue ; j'en avais besoin pour vérifier que les composants que j'emploie y figurent avec leurs variantes, pas pour son texte. |
| `token_server.py` | 826 | l. 1-30, 165-240, 660-700, 740-765 | **NON LU EN ENTIER** — seules les deux routes SSR et la liste des imports étaient dans le mandat (lecture seule ailleurs). |
| `web/topbar.js` | 243 | 0 | **NON LU** — interdit en écriture, et `ssr_v2` ne fait que poser `<div data-topbar-mount>` + `<script src="/topbar.js">`, exactement comme `decision-jl.html:26,30`. |
| `web/v2/article.js` | 1 (mesuré) | l. 185-205 | **NON LU EN ENTIER** — lu seulement pour savoir si la page accepte `?code=&num=` (elle lit `num` et `date`, `contexte()` l. 187-194, sur un jeu de données figé). D'où le libellé « bientôt » du lien « Carte de l'article ». |

Données réelles utilisées : 4 appels `curl` à la production
(`/api/decision` × 3, `/api/law` × 2), sorties conservées en
`scratchpad/data/*.json` du dossier de travail.

---

## 1. TABLE — CE QUE `ssr.py` FAISAIT → OÙ `ssr_v2` LE FAIT

Convention : « *importé* » signifie que `ssr_v2` appelle **la fonction de
`ssr.py` elle-même**, sans la recopier. C'est la garantie qu'aucun signal de
référencement ne peut diverger.

### 1.1 Le head, intégralement préservé

| Comportement de `ssr.py` | Où dans `ssr_v2.py` |
|---|---|
| `_canonical()` — l'identifiant DOIT être %-encodé (ssr.py:790-805, bogue du 23/08 : 114 000 pages du CE déclaraient une canonique morte) | *importé* — `ssr_v2.py:37-42`, appelé `ssr_v2.py:430` |
| `<title>` qui retombe sur l'intitulé quand `numero` est vide (ssr.py:861-869, bogue des 76 k pages CEDH « Cour EDH, <date> ») | recopié à l'identique `ssr_v2.py:426-428` |
| `_strip(text, 200)` pour la description | *importé*, appelé `ssr_v2.py:429` |
| OpenGraph + Twitter (type, title, description, url, site_name, locale, card) | `ssr_v2.py:71-94` (`_head`) |
| `_jsonld_embed()` — `<` plutôt que `html.escape`, anti-breakout `</script>` | *importé*, appelé `ssr_v2.py:447` et `925` |
| JSON-LD `LegalCase` + `CreativeWork`, clés `None` filtrées | `ssr_v2.py:432-447` — dictionnaire **identique clé pour clé** |
| JSON-LD `Legislation`, `legislationLegalForce` = `NotInForce` pour un abrogé (ssr.py:1125-1128) | `ssr_v2.py:903-925` |
| `<link rel=icon>`, `lang="fr"` | `ssr_v2.py:79` et `157-159` |

**Vérifié mécaniquement** : `tests/test_ssr_v2.py` →
`test_head_seo_identique_a_ssr_v1` et `test_head_seo_loi_identique_a_ssr_v1`
comparent **chaîne à chaîne** `canonical`, `<title>`, `description`,
`og:url`, `og:title` et le JSON-LD (après `json.loads`) entre
`ssr.render_decision` et `ssr_v2.render_decision`, sur les trois
identifiants du mandat — dont `/Ariane_Web/AW_DCE/|96191`, celui qui porte
le slash et le pipe.

### 1.2 Le corps

| Comportement de `ssr.py` | Où dans `ssr_v2.py` | Note |
|---|---|---|
| `_clean_dila_text()` (balises XML résiduelles, `<br/>`) | *importé*, appelé `ssr_v2.py:450-452` | |
| `_smart_paragraph_split()` (texte sans retour à la ligne) | *importé via `_clean_dila_text`* (ssr.py:81-82) | |
| `_brut()` : « other » / « none » / « null » ne sont pas des informations (ssr.py:830-832, constat prod du 13/09) | `ssr_v2.py:368-372` | + test `test_jamais_other_ni_liste_vide` |
| Lignes de la table de métadonnées (Juridiction, Date, Numéro, ECLI, Formation, Nature, Type de recours, Solution, Conclusion, État défendeur, Importance HUDOC, Président, Rapporteur, Rapporteur public, Avocats, Publication ×3) | `ssr_v2.py:459-507` — **une par une, dans le même ordre**, mais rendues en **bande d'identité** `.jl-bande--enligne` au lieu d'un `<table>` | |
| `_lang_warning()` (CEDH/CJUE non francophones + lien DeepL, whitelist `_LANG_NAMES`) | `ssr_v2.py:545-554`, jeton `_LANG_NAMES` *importé* | rendu en `.jl-warnp` au lieu de `.lang-warning` |
| `_texte_integral_warning()` (le texte servi n'est qu'un sommaire) | `ssr_v2.py:555-560` | idem |
| Encadré « open data du Conseil d'État » pour `DCE_/DCAA_/DTA_/ORTA_` (ssr.py:315-325) | `ssr_v2.py:561-566` | |
| `_official_source_button()` / `_official_source_from_pattern()` / `_cached_decision_url()` (Légifrance, HUDOC, EUR-Lex, courdecassation.fr) | *importé*, appelé `ssr_v2.py:431` ; rendu en bouton `.jl-bouton--cta` `ssr_v2.py:530-534` | |
| Ligne « Source officielle » + `_source_host()` | *importé*, `ssr_v2.py:530-534` et pied `ssr_v2.py:633-644` | |
| Ligne « Source de l'archive » (`BULK_SOURCES`) | *importé*, pied `ssr_v2.py:633-644` | |
| `_citations.linkify()` + pré-chauffage parallèle du cache LRU (ssr.py:877-888) | **remplacé** par `_lier_articles()` `ssr_v2.py:239-268` | voir §2.1 : plus aucun accès réseau à l'ouverture, donc plus de `ThreadPoolExecutor` ni de risque de 502 CloudFlare |
| `_render_legal_text()` / `_render_structured_sections()` / `_split_sommaire_sections()` (Plan de classement, Résumé, Renvois) | `_sec_analyses()` `ssr_v2.py:769-792` + sommaire officiel `ssr_v2.py:570-587` | voir §2.2 |
| `_format_fr_date()` | *importé*, partout | |
| `esc()` | *importé* | |
| `_subline_statut()` (l'abrogé s'annonce AVANT le texte, la `note` de l'API est rendue) — ssr.py:1012-1036 | **réécrit sans style en ligne** `ssr_v2.py:850-877` ; mêmes libellés mot pour mot | les couleurs passent en classes, jl.css §29.1 |
| Le calcul du statut : `ABROGE/PERIME/TRANSFERE/ANNULE` **ou date de fin passée** (ssr.py:1087-1096, bogue du 10/09 : 26 abrogés sur 26 affichés « en vigueur ») | `_statut()` `ssr_v2.py:831-847` — même liste, même `_fin_passee` | test `test_abroge_annonce_en_rouge_avant_le_texte` |
| `titre_texte` avant `titre_section` (bogue du 23/08 : toutes les pages `/loi/` passées au sigle) | `ssr_v2.py:881` | test `test_render_law_uses_titre_texte` repris tel quel |
| `render_law_404`, `render_decision_404` | *importés* `ssr_v2.py:1009` | hors mandat, inchangés |
| Sitemaps (`render_sitemap_*`) | **non concernés**, restent dans `ssr.py` | le mandat les exclut ; `token_server` continue de les appeler sur `ssr` |

---

## 2. CE QUE LA PAGE FAIT DE PLUS, ET D'OÙ ÇA VIENT

Rien n'est affiché sans provenance. La règle tenue : *on n'affiche une ligne
que si le champ existe ; on n'invente ni juridiction, ni partie, ni résumé.*

### 2.1 Textes visés — `ssr_v2.py:679-724`

- **Le visa LEGI structuré d'abord.** Si `liens_textes` est servi (mesuré à
  12,5 % sur cass. et CA, inventaire §1.2), il est rendu en tête, étiqueté
  `visa LEGI`.
- **Sinon la regex**, `sources/citations.py:detect_citations` (16 codes +
  CEDH/CONST/DDHC), étiquetée **« repéré dans le texte »**.
- Chaque article pointe **`/loi/<code>/<num>?date=<date de la décision>`** —
  la rédaction applicable à la date de l'arrêt, pas celle d'aujourd'hui
  (`_lier_articles` `ssr_v2.py:250-254`). `ssr.py` liait vers Légifrance dès
  que l'entrepôt répondait ; ici le lecteur reste sur le site et Légifrance
  est au bouton « source officielle ».
- Chaque article liste **les paragraphes où il est cité** (`§ 8`, `texte`),
  ancres cliquables, construites au fil du rendu (`_rendre_texte`
  `ssr_v2.py:270-316`).
- Mesuré sur la cassation réelle : 3 articles (CC 2241, CPC 700, CPC 450),
  chacun avec ses renvois.

### 2.2 Sommaire officiel — `ssr_v2.py:570-587`

Le champ `sommaire` du flux DILA, rendu tel quel, étiqueté
« sommaire officiel · DILA », avec l'explication complète en infobulle
(« Ce n'est pas une synthèse générée »). Les `abstrats` deviennent des
pastilles « Matière ». **Pas de résumé IA : sommaire officiel ou rien.**

Piège traité : `abstrats` et `renvois` reviennent parfois comme la chaîne
littérale `"[]"`, non vide et vide de sens (inventaire §1.2, 100 % sur
tcom). `_liste_json()` `ssr_v2.py:349-366` la ramène à une liste vide.
Mesuré sur la cassation réelle : `abstrats` vaut `["prescription civile"]`.

### 2.3 Chronologie — `ssr_v2.py:726-767`

Deux sources, **jamais autre chose** :
1. la date de la décision, provenance « métadonnées », avec la juridiction —
   c'est le seul endroit où une juridiction est nommée, et elle vient du
   champ `juridiction` de l'API ;
2. les dates écrites **en toutes lettres dans le texte** (`_dates_du_texte`
   `ssr_v2.py:318-336`), chacune avec renvoi au paragraphe (`voir` → `#p6`)
   et provenance « repéré dans le texte », **sans aucune juridiction** :
   l'infobulle dit pourquoi (« le texte ne la nomme pas toujours, et on ne la
   déduit pas »).

Les champs structurés qui permettraient mieux (`form_dec_att`,
`date_dec_att`, la `timeline` Judilibre) ne sont pas ingérés — inventaire
§1.3 et §14.

### 2.4 « Cité par » — `ssr_v2.py:794-828`

Lien de recherche sur le numéro, étiqueté **« recherche lexicale »**, avec
l'infobulle « le nombre n'est pas calculé à l'ouverture de la page (aucun
appel d'API) ». Le calcul côté serveur est l'étape suivante.

### 2.5 En-tête du greffe replié — `ssr_v2.py:215-224`, rendu `588-596`

Tout ce qui précède « AU NOM DU PEUPLE FRANÇAIS » / « R É P U B L I Q U E »
part dans un `<details class="jl-fold jl-entete-fold">`, avec la mention
« mise en page du greffe, déjà reprise dans la bande d'identité ».
Le repli est **ouvert d'office à l'impression** (jl.css:1015-1016).

### 2.6 Titres de section et plan — `_est_titre()` `ssr_v2.py:186-213`

Règle volontairement pauvre et vérifiable : ligne courte (≤ 80 car.,
≤ 9 mots), sans ponctuation de phrase finale, commençant par une majuscule,
qui n'est ni une puce de liste (`a)`, `1°`, `I.`) ni un marqueur technique
HUDOC (`{signature_p_2}`). **Le libellé affiché est celui du texte, mot pour
mot** — aucun intitulé n'est fabriqué. Sur la cassation réelle : « Faits et
procédure », « Examen du moyen », « Enoncé du moyen », « Réponse de la
Cour ». Sur la CEDH : « INTRODUCTION », « EN FAIT », « EN DROIT ».
Le plan latéral est coupé à 30 entrées (`ssr_v2.py:600-604`).

### 2.7 Paragraphes numérotés — `ssr_v2.py:284-296`

`1.`, `2.`… deviennent `<p id="p1" class="jl-pn">` avec l'ancre
`.jl-no` cliquable — c'est ce qui permet de citer « § 12 » et ce sur quoi
s'appuient les renvois des textes visés et de la chronologie.

---

## 3. DIFFÉRENCES DE RENDU ASSUMÉES avec `ssr.py`

| # | Différence | Pourquoi |
|---|---|---|
| 1 | **Le `<table class="meta-table">` disparaît** au profit de la bande d'identité `.jl-bande--enligne`. | C'est la décision de `decision-jl.html:34` et du rapport normaliseur §2.2 (« gagnant, sans boîte »). Les mêmes lignes, dans le même ordre. |
| 2 | **Les liens d'articles pointent vers `/loi/` et non vers Légifrance.** | Mandat : « reliés à `/loi/<code>/<num>?date=<date de la décision>` ». Effet de bord favorable : plus aucun accès réseau à l'ouverture, donc la cause du 502 CloudFlare documentée en ssr.py:38-42 disparaît, ainsi que le `ThreadPoolExecutor` de ssr.py:880-885. |
| 3 | **Aucun `<style>` embarqué, aucun `style=""`.** `SHARED_CSS` (175 lignes) et `get_topbar_css()` ne sont plus envoyés. | Règle du normaliseur. Le CSS vient de `/styles/jl.css?v=`, donc **mis en cache une fois pour toutes les pages** au lieu d'être réenvoyé à chaque décision. Test `test_pas_de_style_en_ligne_ni_de_css_embarque`. |
| 4 | **Le topbar n'est plus extrait de `topbar.js` par expression régulière** (ssr.py:658-681, et le rapport normaliseur §4 notait qu'il était envoyé **en double**). | `<div data-topbar-mount>` + `<script defer src="/topbar.js">`, comme `decision-jl.html:26,30`. Le drift structurel disparaît. |
| 5 | **Le fil d'ariane `.page-subbar` est remplacé par le rail « Chercher dans » + le retour conditionnel « ← Résultats ».** | `decision-jl.html:32,34`. Le rail est rendu par `JL.renderRail()` depuis `#jl-page` ; « ← Résultats » ne s'affiche que si `document.referrer` est une recherche (`JL.bindBackLink`). |
| 6 | **Le texte est réparti sur deux onglets, Texte et Dossier.** | `decision-jl.html:37-95`. À l'impression, **les deux panneaux s'ouvrent** (jl.css:1012). |
| 7 | **`ssr.py` imprimait l'adresse après chaque lien** (`a[href^="http"]:after{content:" (" attr(href) ")"}`, ssr.py:619-622) ; jl.css §26 fait l'inverse (`a[href]::after{content:""}`, jl.css:1018). | Je n'ai pas touché à jl.css §26 : c'est la feuille du normaliseur, partagée avec la page de recherche et les maquettes, et deux autres agents y écrivent. **À TRANCHER**, voir §5.2. |
| 8 | **Page `/loi/` : une colonne, pas les trois colonnes de `web/v2/article.html`.** | Les trois colonnes (cadre normatif, références croisées) demandent des appels d'API à l'ouverture, interdits ici. La page reprend le **chrome** de `article.html` (titre `.jl-titrepage` avec le numéro en `<em>`, bande de métadonnées, `.jl-alin` pour le texte, `.jl-nota`) et renvoie à la carte dynamique par le lien « Carte de l'article » (`ssr_v2.py:960-973`). |
| 9 | **Le bloc `#jl-page` ne porte aucun texte libre.** `llm.identite` de `decision-jl.html:121` a été retiré ; il ne reste que des URL filtrées (`_url_sure` `ssr_v2.py:119-130`) et une date validée. | Un `application/json` est du *raw text* pour le parseur HTML : un `</script>` dans une valeur refermerait la balise. `jl.js:bindLLMCopy` lit de toute façon la ligne de référence dans le DOM (`#refL`, jl.js:536), où elle est échappée. Conséquence assumée : le bloc copié pour un assistant ne porte plus la ligne « Juridiction / Solution / Publication » en doublon de la référence. |
| 10 | **Les parties ne sont pas affichées**, alors que `decision-jl.html:93` en montre trois. | La maquette les lit dans l'en-tête de l'arrêt ; `demandeur`/`defendeur` ne sont **pas ingérés** (inventaire §1.3). Plutôt qu'un parseur de noms propres, la page le dit dans le bloc honnêteté (`ssr_v2.py:820-826`). |
| 11 | **Pas de section « Faits datés » distincte de la chronologie.** | Séparer un fait d'une étape de procédure demande un jugement qu'aucune donnée ne fonde. Une seule liste, sourcée. |

---

## 4. VÉRIFICATIONS FAITES

| Contrôle | Résultat |
|---|---|
| `python3 tests/test_ssr_v2.py` | **15 tests, tous verts** (les 7 de `test_ssr_escaping.py` + 8 propres à la v2) |
| `python3 tests/test_ssr_escaping.py` (non touché) | **7 tests verts** — `ssr.py` n'a pas bougé |
| Pages rendues avec des données **réelles** de production | `web/v2/ssr-preview/decision-cassation.html` (dila `6aa272fd195da062e0fa6eaf`), `decision-cedh.html` (`001-212971`), `decision-ce-ariane.html` (`/Ariane_Web/AW_DCE/\|96191`), `loi-cpc-748-6.html`, `loi-ct-L321-1-abroge.html` |
| **Canonique identique à `ssr.py`, chaîne à chaîne**, sur les 3 décisions | oui, y compris `https://justicelibre.org/decision/ariane/%2FAriane_Web%2FAW_DCE%2F%7C96191` |
| JSON-LD `json.loads()` sur les 5 pages | valide |
| Bloc `#jl-page` `json.loads()` sur les 5 pages | valide |
| Erreurs console, les 5 pages | **aucune** (`read_console_messages onlyErrors`) |
| Rendu 1280 px, thème clair | conforme : rail, bande, onglets, sommaire officiel, textes visés, chronologie |
| Thème sombre | conforme (contrôlé sur la page `/loi/` abrogée : l'avertissement rouge reste lisible) |
| 390 px (préréglage mobile 375 px) | rail masqué, burger de `topbar.js` présent, **débordement horizontal = 0 px** (mesuré : `scrollWidth == clientWidth == 375`) |
| Impression | vérifié à 794 px (la largeur d'une A4) en injectant les règles de jl.css §26 comme feuille d'écran : header, rail, plan, onglets et boutons masqués, **les deux panneaux ouverts**, l'en-tête du greffe déplié, la référence conservée, **la mise en page desktop part sur le papier** |
| Onglet Dossier | affiche les 3 textes visés sourcés, la chronologie sourcée, le bloc honnêteté |
| `web/maquettes/decision-jl.html` et `composants.html` | **intacts** — `git status` ne les signale pas ; md5 relevés dans le rapport de session |
| Fichiers interdits | `ssr.py`, `server.py`, `search_api.py`, `web/topbar.js`, `web/*.html` de prod : **aucun** n'apparaît dans `git status` |
| `git diff --stat` | `token_server.py` +5, `web/styles/jl.css` +28. Rien d'autre. |

Une bizarrerie connue, non imputable à ces pages : la première `navigate`
du panneau navigateur peut rester sur la page précédente ; il faut la
rejouer. Constaté aussi sur `web/v2/article.html`, que je n'ai pas touchée.

---

## 5. « À TRANCHER »

1. **Le lien « Carte de l'article » mène à un prototype figé.**
   `web/v2/article.js:187-194` lit `?num=` et `?date=` mais dans un jeu de
   données codé en dur sur 748-6. J'ai donc écrit le lien avec
   `?code=&num=` **et** l'étiquette grise « page dynamique … Bientôt »
   (règle de couleur : gris = bientôt). **Ma proposition** : laisser en
   l'état jusqu'à ce que la carte soit branchée sur `/api/law`, puis retirer
   l'étiquette. **Si tu préfères**, je masque complètement le lien tant que
   la page n'est pas réelle.

2. **Les adresses des liens à l'impression.** `ssr.py:619-622` écrivait
   l'URL entre parenthèses après chaque lien — utile pour un justiciable qui
   imprime son dossier. jl.css §26 (l. 1018) fait l'inverse. C'est une règle
   du normaliseur, partagée, et deux autres agents écrivent dans ce fichier :
   **je ne l'ai pas changée**. **Ma proposition** : réintroduire l'adresse
   pour les seuls liens sortants des pages décision et loi, par une règle
   ajoutée en §29 (`.jl-body a[href^="http"]::after`), pas par une
   modification du §26. Un mot de toi et je l'ajoute.

3. **La ligne d'identité dans le bloc copié pour un assistant.**
   `decision-jl.html:121` la passait par `#jl-page` ; je l'ai retirée pour
   des raisons d'échappement (§3, n° 9). **Ma proposition** : la rendre à
   `jl.js` en lui faisant lire un `data-jl-identite` sur le bouton — mais
   c'est une **modification** de `jl.js:947-948`, pas un ajout en fin de
   fichier, donc hors de ce que le mandat m'autorise. Je ne l'ai pas faite.

4. **Deux bascules de thème coexistent** (celle de `topbar.js`, binaire ;
   celle du rail, à trois états). C'est le point n° 2 des « À TRANCHER » du
   rapport normaliseur, inchangé : mes pages héritent du problème, elles ne
   le créent pas.

5. **`ssr_v2` ne sert pas les fonds `cnil`, `jorf`, `kali`.** Le bloc `cnil`
   de `search_api.fetch_decision` est mort (inventaire §11), alors que
   `ssr.render_sitemap_cnil` publie ces URL au sitemap. Les sitemaps sont
   hors mandat ; **le signaler reste la bonne réponse**, la corriger
   demanderait d'écrire dans `ssr.py`.

6. **La détection de titre est générique.** Elle marche parfaitement sur la
   Cour de cassation et honorablement sur la CEDH. Sur un fonds au texte très
   fragmenté, elle produira un plan bavard (d'où la coupe à 30 entrées).
   **Ma proposition** : la laisser générique — une liste blanche d'intitulés
   français serait fausse dès le premier arrêt de la CJUE — et regarder le
   résultat sur un échantillon plus large avant d'affiner.

---

## 6. PROCÉDURE DE BASCULE ET DE RETOUR ARRIÈRE

### 6.1 L'aiguillage, 5 lignes, `token_server.py`

```
l. 690-692   # Aiguillage v2 (JL_SSR_V2=1) : même signature, même head SEO.
             if os.environ.get("JL_SSR_V2") == "1":
                 from ssr_v2 import render_decision as render_decision
l. 759-760   if os.environ.get("JL_SSR_V2") == "1":          # aiguillage v2
                 from ssr_v2 import render_law as render_law
```

Rien d'autre n'a été touché dans `token_server.py`. Sans la variable, le
comportement est **strictement** celui d'aujourd'hui : la ligne
`from ssr import render_decision…` (l. 672) reste la seule exécutée, et
`ssr_v2` n'est même pas importé. Les 404, les sitemaps et la redirection
`/search.html?id=…` (l. 173-180) ne passent jamais par v2.

### 6.2 Bascule

```
# 1. déposer ssr_v2.py et la version de jl.css portant la section 29
# 2. dans l'unité systemd du service (ou le shell qui le lance) :
Environment=JL_SSR_V2=1
# 3. redémarrer le service, puis purger le cache Cloudflare des deux
#    préfixes : /decision/* et /loi/*  (les réponses portent
#    Cache-Control: public, max-age=86400 — sans purge, la bascule met 24 h
#    à se voir, et le retour arrière aussi)
```

Contrôle immédiat après bascule, sur la production, sans outil :

```
curl -s https://justicelibre.org/decision/dila/6aa272fd195da062e0fa6eaf | grep -c 'jl.css'
curl -s https://justicelibre.org/decision/dila/6aa272fd195da062e0fa6eaf | grep '<link rel="canonical"'
```

La deuxième commande doit rendre **exactement** la même ligne qu'avant la
bascule. Si elle diffère d'un caractère, revenir en arrière sans discuter.

### 6.3 Retour arrière

Retirer `JL_SSR_V2` de l'environnement, redémarrer, purger le cache. Aucune
migration de données, aucun schéma, aucun fichier de production modifié :
`ssr.py` n'a pas bougé d'une ligne. Le pire cas est une journée de pages
v2 en cache.

Le seul élément qui **reste** après un retour arrière est la section 29 de
`jl.css` (28 lignes, `jl.css:1343-1369`) : trois blocs de règles préfixées
`jl-`, qu'aucune page de production n'emploie aujourd'hui. Elle est inerte.

---

## 7. FICHIERS PRODUITS OU MODIFIÉS

| Chemin | État |
|---|---|
| `ssr_v2.py` | **neuf**, 1 010 lignes |
| `tests/test_ssr_v2.py` | **neuf**, 364 lignes (les 7 tests de `test_ssr_escaping.py` + 8) |
| `token_server.py` | **+5 lignes**, aiguillage seul (l. 690-692 et 759-760) |
| `web/styles/jl.css` | **+28 lignes** en fin de fichier, section datée « 29. v2 ssr, 13 sept. » (l. 1343-1369) |
| `web/v2/ssr-preview/decision-cassation.html` | preuve, données réelles |
| `web/v2/ssr-preview/decision-cedh.html` | preuve, données réelles |
| `web/v2/ssr-preview/decision-ce-ariane.html` | preuve, données réelles |
| `web/v2/ssr-preview/loi-cpc-748-6.html` | preuve, données réelles |
| `web/v2/ssr-preview/loi-ct-L321-1-abroge.html` | preuve, données réelles (abrogé le 1er mai 2008) |
| `web/jl.js` | **non touché** — aucun ajout n'a été nécessaire |
| `ssr.py`, `server.py`, `search_api.py`, `web/topbar.js`, `web/*.html` de prod, `web/maquettes/*` | **non touchés** |

Aucun commit n'a été fait.

/home/dahl/justicelibre/scratchpad/audit/v2_ssr_13sept.md
