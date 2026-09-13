# v2 — page TEXTES (`web/v2/textes.html` + `textes.js`)

13 septembre 2026. Prototype local vérifié sur `http://localhost:8787`, données
réelles de `https://justicelibre.org/api`.

---

## 1. Manifeste de couverture

Ce qui était demandé, et où c'est.

| # | Demande | État | Où |
|---|---------|------|----|
| 1 | Barre de recherche réseau interrogeant `/api/search?sources=legi` | fait | `textes.js` §5 `chercher`, `interroger` |
| 1b | États de source, pastille loader, refus ≠ délai, relance 60 s | fait | `textes.js` §5-6 |
| 1c | « jamais aucun résultat si la source n'a pas répondu » (3 vides distincts, + un 4ᵉ) | fait | `textes.js` §7 `renderResults` |
| 1d | Pagination avec `total` / `total_exact` | fait | `textes.js` `interroger`, `boutonSuite` |
| 1e | Carte = un article : titre, état en pastille, date de début, extrait surligné | fait | `textes.js` `carteArticle` |
| 1f | Lien de lecture vers la page serveur `/loi/<sigle>/<num>` | fait | `carteArticle`, table `PAR_LEGITEXT` |
| 1g | Sigle non résolvable → Légifrance + provenance | fait | `carteArticle`, mention « pas de page interne · lien Légifrance » |
| 2 | Accès direct par référence (4 formes) | fait | `textes.js` §3 `analyserRef` |
| 2b | Article en tête : rédaction, état, `titre_section`, date, nota, Légifrance daté | fait | `rendreFiche` |
| 2c | « toutes les versions » (`/api/law/versions`) | fait | `toutesLesVersions` |
| 2d | Boutons « Carte de l'article » et « Historique » gris « bientôt » | fait | `rendreFiche`, `.jl-bouton--desactive` + `.jl-soonpill` |
| 3 | Codes classés par sujet, en colonnes | fait | `textes.js` §8, CSS `.jl-codes` |
| 3b | Textes hors code : ministère NOR › nature › année | fait | `textes.js` §9, `hub_horscode.json` |
| 3c | Code cliquable = recherche filtrée `code=<sigle>` | **partiel, mesuré** | voir §3 ci-dessous |
| 4 | Provenance sur chaque information (« LEGI · DILA ») | fait | cartes, fiche, fil hors code |
| 4b | État en couleur (vert / gris non résolu / rouge atténué) | fait | `pastilleEtat` |
| 4c | Aucun résumé | fait | le texte d'article est cité intégralement, jamais coupé |
| 4d | Titre « Chercher un <em>texte</em> » | fait | `textes.html:39` |
| 4e | Aucun style ni script inline hors head SEO | fait | seul script inline = résolveur de thème, `textes.html:22-24` |
| 4f | Résolveur de thème + `#jl-page` | fait | `textes.html:22-24`, `:117-137` |
| 4g | Pas de tirets cadratins dans les libellés nouveaux | fait | vérifié : aucun `—` dans un libellé créé ici |
| 4h | Lien GitHub Dahliyaal | fait | `textes.html:99` |
| 5 | Rail des autres pages v2 → `/v2/textes.html` | fait | 6 pages, une ligne chacune (voir §5) |
| 6 | `soon:true` sur Travaux préparatoires et Vérifier mes citations | fait | `textes.html:123`, `:128` |

---

## 2. Ce qui est repris, et d'où (fichier:ligne)

Rien n'a été inventé. Chaque mécanisme vient d'un fichier existant.

| Mécanisme | Origine | Repris dans |
|---|---|---|
| Barre réseau, panneau `jl-sbox`, hint `jl-kb` | `web/v2/recherche.html:45-53, 131` | `textes.html:47-55, 61` |
| Cadre centré `jl-body jl-body--centre`, rail depuis `#jl-page` | `web/v2/recherche.html:33-35, 189-211` | `textes.html:32-34, 117-137` |
| Résolveur de thème avant premier rendu | `web/v2/recherche.html:21-24` | `textes.html:22-24` |
| Garde-fou double envoi (`S.enVol`) | `web/v2/recherche.js:273-275` | `textes.js` `lancer` |
| Refus 4xx ≠ délai, pas de rejeu d'un refus | `web/v2/recherche.js:357-369` | `textes.js` `interroger` |
| Relance automatique des délais à 60 s | `web/v2/recherche.js:394-405` | `textes.js` `chercher` (fin) |
| Pastilles de source (5 états, loader compris) | `web/v2/recherche.js:409-426` | `textes.js` `renderSources` |
| Trois vides distincts, « ce rien ne veut pas dire rien » | `web/v2/recherche.js:523-541` | `textes.js` `renderResults` |
| Pagination par offset avec `total` / `total_exact` | `web/v2/recherche.js:376-382, 611-622` | `textes.js` `interroger`, `boutonSuite` |
| Compactage d'extrait + `JL.surlignerExtrait` + `JL.lierArticles` | `web/v2/recherche.js:563-571` | `textes.js` `carteArticle` |
| Fiche d'article : plage de rédaction, état, nota, `.txt`, Légifrance | `web/v2/recherche.js:753-793` | `textes.js` `rendreFiche` |
| Toutes les rédactions | `web/v2/recherche.js:795-817` | `textes.js` `toutesLesVersions` |
| Cache local d'article (`JL.cacheLoiGet/Set`) | `web/jl.js` | `textes.js` `resoudreArticle` |
| Récap d'impression + titre de PDF portant la requête | `web/v2/recherche.js:247-253, 962-972` | `textes.js` §10-11 |
| Modale de signalement GitHub | `web/v2/recherche.html:175-185` | `textes.html:104-114` |
| Table des 75 codes (LEGITEXT, libellé, abréviations) | `web/hub.html:497-573` | `textes.js` `CODES` |
| Sigles ↔ LEGITEXT | `sources/legi.py:17-104`, `:111-191` | `textes.js` `CODES` (colonne 1) |
| Tri par SUJET du code (`cleTri`) | `web/hub.html:414-415` | `textes.js` `cleTri` |
| Abréviation la plus courte (`abrev`) | `web/hub.html:575` | `textes.js` `abrev` |
| Analyse d'une référence d'article (`parseArticle`) | `web/hub.html:874-882` | `textes.js` `analyserRef` (b) et (c) |
| Loi par son numéro → `/api/law/resolve` | `web/hub.html:829-836` | `textes.js` `resoudreNumero` |
| Un code cliqué prépare « art. ␣␣<abrév> », curseur en 5 | `web/hub.html:840` | `textes.js` `preparerReference` |
| Hors code : ministère › nature › année, `titreParts`, `nomMin` | `web/hub.html:447-538` | `textes.js` §9 |
| Champs `/api/law` (`titre_section` OK, `nota` 43 %, `source_url` 100 %) | `scratchpad/audit/inventaire_champs_13sept.md` §7 | exploités tels quels |

---

## 3. Ce que l'API permet et ne permet pas — **mesuré le 13/09/2026**

Chaque ligne a été appelée en direct sur `https://justicelibre.org`.

### Ce qui marche

| Appel | Résultat mesuré |
|---|---|
| `GET /api/search?q=responsabilité&sources=legi&limit=3` | `total: 33889`, `total_exact: true`, 3 articles, chacun avec `id` (LEGIARTI), `title`, `etat`, `date`, `numero`, `legitext`, `extract` surligné `<em>` |
| `GET /api/law?code=CC&num=1240` | `legiarti`, `legitext`, `titre_texte`, **`titre_section` = « Chapitre Ier : La responsabilité extracontractuelle en général »**, `etat: VIGUEUR`, `date_debut`, `date_fin`, `texte`, `nota: null`, **`source_url` daté** `…/article_lc/LEGIARTI000032041571/2016-10-01` |
| `GET /api/law?code=CPC&num=748-6` | idem, `etat: VIGUEUR_DIFF`, `titre_section` = « Titre XXI : La communication par voie électronique. », `nota` non nul |
| `GET /api/law/versions?code=CPC&num=748-6` | liste de rédactions, chacune avec `date_debut`, `date_fin`, `etat`, `texte`, `nota` |
| `GET /api/law/resolve?numero=78-17` | `legitext: LEGITEXT000006068624`, `titre_texte`, `date_debut`, `articles_count: 484`, `source_url` |

### Ce qui ne marche pas

1. **`/api/search` ignore le paramètre `code`.**
   Vérifié : `?q=harcèlement&sources=legi&code=CT` renvoie un décret
   (`LEGITEXT000048374743`), pas un article du code du travail.
   Cause lue dans le code : `sources/warehouse.py:243-265` `search_fond`
   **accepte** un `code`, mais `search_api.py:652-665` `_dispatch_legi` ne le
   transmet pas, et `token_server.py` `_handle_search` ne le lit pas.
   → Conséquence dans la page : le filtre par code porte **sur les articles
   déjà chargés**, et la page le dit deux fois (bandeau `noteFiltreCode`,
   et message dédié quand le filtre vide la liste). Rien ne laisse croire à un
   filtrage du fonds.

2. **L'éclaireur de citation ne connaît pas les articles de loi.**
   Vérifié : `?q=art. 1240 C. civ.&citation_only=1` → `citation_match: false`.
   `sources/citations.py` ne reconnaît que les citations de **décisions**
   (pourvoi, ECLI, juridiction + date).
   → Conséquence : l'analyse d'une référence d'article se fait côté page
   (`analyserRef`), puis la résolution passe par `/api/law`. C'est exactement
   ce que fait déjà `hub.html:874-882` ; aucune invention.

3. **Aucun compte d'articles par code n'est servi.** La grille affiche donc le
   nombre de **codes** (75), jamais un nombre d'articles par code, qu'il
   faudrait fabriquer.

4. **Pas de filtre de juridiction pour LEGI** : `_dispatch_legi` ne prend ni
   `juridiction` ni `lieu`. Le paramètre `juridiction=legi` est envoyé par
   cohérence avec `hub.html:984`, mais il est sans effet côté serveur.

5. **`web/hub_horscode.json` est un échantillon** : 24 ministères, comptes
   complets, mais titres embarqués seulement pour les 10 premiers ministères
   et les 3 dernières années. La page nomme ce vide comme un vide
   d'échantillon, jamais comme un vide du Journal officiel.

---

## 4. Composants ajoutés

Tous en **fin** de `web/styles/jl.css`, section datée « v2 textes, 13 sept. ».
Aucune règle antérieure n'a été réécrite. `web/jl.js` n'a **pas** été touché :
la page n'a eu besoin d'aucune fonction nouvelle du normaliseur.

| Classe | Rôle |
|---|---|
| `.jl-codes` / `.jl-code` / `.jl-code__n` / `.jl-code__s` | grille des codes, 3 colonnes ≥ 900 px, 2 ≥ 620 px, 1 en dessous |
| `.jl-fart` + `__meta __t __code __sect __pied __prov` | fiche de l'article en tête, filet teal à gauche |
| `.jl-hc` / `.jl-hcfam` / `.jl-hcscroll` | trois colonnes de filtres du hors code (ministère, nature, année) |
| `.jl-soonpill` | mention « bientôt » dans un bouton désactivé |
| `@media print` | la grille des codes, les filtres hors code et le pied de fiche
  disparaissent (ce sont des commandes) ; la fiche d'article sort en entier |

⚠ `.jl-tag--txt` **existait déjà** (`jl.css:702`, `--c:var(--txt)`, avec sa
variante sombre ligne 132). Une première version de cette section la
redéfinissait : la redéfinition a été retirée avant livraison, elle aurait
cassé la couleur en thème sombre. C'est le piège n° 3 du normaliseur, croisé
une fois de plus.

---

## 5. Fichiers touchés

Créés :
- `web/v2/textes.html`
- `web/v2/textes.js`

Modifiés en ajout de fin :
- `web/styles/jl.css` (section « v2 textes, 13 sept. », après la section
  « v2 accueil light »). Sauvegarde de l'état antérieur : `/tmp/jl.css.bak`.

Modifiés d'**une seule ligne** (le rail) :
- `web/v2/recherche.html:197`, `doctrine.html:107`, `annuaire.html:167`,
  `apropos.html:348`, `article.html:54`, `historique.html:49`
  → `{"k":"textes", …, "href":"/v2/textes.html", "n":"1,8 M"}`.
  (`recherche`, `doctrine`, `annuaire`, `apropos` portaient `"soon":true` ;
  `article` et `historique` pointaient vers `/hub.html#/textes`.)

**`web/v2/index.html` n'a pas été modifié** : c'est la page d'accueil, elle
n'a pas de bloc `#jl-page` ni de rail. Il n'y avait donc pas de ligne à
changer. À signaler, parce que le mandat la listait.

Rien d'autre n'a été touché. Aucun commit.

---

## 6. Vérification au navigateur

`http://localhost:8787/v2/textes.html`, console vide (les erreurs CORS
`data/annuaire_*.json` observées viennent d'`annuaire.js` qui appelle la prod
depuis `localhost` : elles préexistent et ne concernent pas cette page).

| Test | Résultat |
|---|---|
| `responsabilité` | 30 articles chargés **sur 33 889 existants**, plusieurs codes (CGI, CGI annexe III), un décret de 1949, états « modifié » et « abrogé » en couleur |
| `art. 1240 C. civ.` | fiche en tête : « en vigueur », « Rédaction du 1er octobre 2016, toujours applicable », section « Chapitre Ier : La responsabilité extracontractuelle en général », texte intégral, Légifrance daté |
| `CPC 748-6` | fiche : « en vigueur (différé) », « Titre XXI : La communication par voie électronique. », nota présent |
| `L. 1152-1 du code du travail` | fiche : « Chapitre II : Harcèlement moral. », + 3 articles en plein texte |
| `loi n° 78-17` | fiche de texte : « LOI n° 78-17 du 6 janvier 1978 », 484 articles en base, bouton « Ouvrir l'article 1er » ; puis 30 articles sur 3 952 en plein texte |
| « Toutes les versions » sur 1240 | « Toutes les rédactions · 2 », chacune datée et pastillée |
| Code cliqué (`?q=harcèlement&code=CT`) | puce retirable « Code du travail ✕ », bandeau « Filtre local » qui dit pourquoi, 1 article sur 30 chargés |
| État non résolu | pastille **grise** « état non résolu » (vue sur un article sans `etat`), jamais verte |
| 1280 px, 390 px | grille 3 colonnes → 1 colonne ; filtres hors code empilés |
| Clair et sombre | les deux rendus vérifiés, pastilles et filet teal lisibles |
| Autres pages v2 | `recherche`, `doctrine`, `annuaire`, `article`, `historique`, `apropos` s'ouvrent, rail → `/v2/textes.html` |

---

## 7. À TRANCHER

1. **Le filtre par code doit-il rester local ?** Le correctif serveur tient en
   deux lignes (`_dispatch_legi` passe `code` à `search_fond`, `_handle_search`
   le lit), mais `search_api.py` et `token_server.py` sont en lecture seule
   pour ce chantier. Tant que ce n'est pas fait, un code cliqué ne restreint
   pas le fonds. Faut-il **retirer** le filtre plutôt que de l'expliquer ?

2. **Accès à un article d'un texte hors code.** La barre sait lire « loi
   n° 78-17 » mais pas « loi n° 78-17 art. 12 » : il faudrait accepter un
   LEGITEXT/JORFTEXT comme « code » dans l'analyseur. Facile, mais c'est une
   règle de lecture supplémentaire : à valider avant de l'ajouter.

3. **Comptes par code.** La grille n'affiche aucun nombre d'articles par code.
   Les fabriquer demanderait 75 appels, ou un fichier écrit la nuit, comme
   pour les volumes de jurisprudence. Chantier séparé ?

4. **« Carte de l'article » et « Historique » restent gris.** Ils le resteront
   tant que `web/v2/article.html` et `historique.html` ne tournent que sur
   CPC 748-6. Faut-il quand même ouvrir le bouton **pour 748-6 seulement** ?
   Position retenue ici : non. Un bouton qui marche une fois sur des milliers
   ment plus qu'un bouton gris.

5. **La section « Codes » sur mobile.** Le surtitre `.jl-surtitre--flex` passe
   mal à 390 px (le texte long s'enroule à côté du mot « CODES »). Cosmétique,
   mais visible.

6. **Textes hors code servi par un fichier.** `hub_horscode.json` reste un
   échantillon figé. La version servie doit interroger l'entrepôt ; sinon la
   page dira toujours « ce vide est celui de l'échantillon ».

---

scratchpad/audit/v2_textes_13sept.md
