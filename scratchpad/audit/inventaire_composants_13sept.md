# Inventaire des éléments visuels réutilisables — 13 septembre 2026

Cible : un seul `jl.css` + un seul `jl.js`. Aucun code produit ici, aucun fichier du dépôt modifié.

---

## 0. MANIFESTE DE COUVERTURE

| Fichier | Lignes | Lu jusqu'à | État |
|---|---|---|---|
| `web/index.html` | 817 | 817 | lu en entier |
| `web/search.html` | 2674 | 2674 | lu en entier |
| `web/annuaire.html` | 6773 | 101, puis 6365→6773 | **NON LU EN ENTIER** — les lignes 102 à 6364 sont 6263 lignes `<tr>…</tr>` de données entre `<!-- STATIC_ROWS_START -->` (l. 101) et `<!-- STATIC_ROWS_END -->` (l. 6365) ; échantillons lus : l. 102-152 (juridictions), l. 792 (badge « manuel »), l. 793 (badge « api »), l. 4118-4119 (badge PRADA). Aucun autre balisage n'y figure (vérifié : `grep -c '^<tr' annuaire.html` = 6263 ; structure des cellules vérifiée exhaustivement, voir §7.1). |
| `https://justicelibre.org/annuaire.html` (prod en ligne) | 6773 | 6773 | Téléchargée le 13/09/2026 par `curl -s`, 2 376 978 octets. `diff` contre `web/annuaire.html` : **sortie vide, exit 0 — la copie locale est identique à la prod, octet pour octet.** |
| `web/ressources.html` | 464 | 464 | lu en entier |
| `web/stats.html` | 340 | 340 | lu en entier |
| `web/inedits.html` | 366 | 149, puis 230→366 | lignes 150-229 = 80 lignes `<tr data-cat=…>` de données, vérifiées homogènes (`grep -vc '^<tr data-cat'` = 0 sur cet intervalle) ; 2 lignes lues en échantillon (l. 148-149). Tout le balisage, le CSS et le JS sont lus. |
| `web/tutoriel-piste.html` | 299 | 299 | lu en entier |
| `web/mentions-legales.html` | 116 | 116 | lu en entier |
| `web/confidentialite.html` | 155 | 155 | lu en entier |
| `web/topbar.js` | 243 | 243 | lu en entier |
| `web/styles/tokens.css` | 163 | 163 | lu en entier |
| `web/styles/base.css` | 65 | 65 | lu en entier |
| `web/styles/components.css` | 175 | 175 | lu en entier |
| `web/styles/annuaire.css` | 166 | 166 | lu en entier |
| `ssr.py` | 1583 | 1583 | lu en entier |
| `web/hub.html` | 1380 | 1380 | lu en entier |
| `web/maquettes/carte-748.html` | 518 | 518 | lu en entier |
| `web/maquettes/histo-02.html` | 636 | 636 | lu en entier |
| `web/maquettes/histo-05.html` | 624 | 624 | lignes 509-624 lues directement ; lignes 1-508 couvertes par un `diff` intégral contre `histo-02.html` (sortie complète relevée, pas un échantillon) : 6 écarts seulement, tous cités plus bas. |
| `web/maquettes/decision-03b.html` | 259 | 259 | lu en entier |
| `web/maquettes/decision-01.html` | 244 | 244 | lu en entier |

Fichiers lus en plus du mandat, parce que les pages prod en dépendent : `web/topbar.js`, `web/styles/{tokens,base,components,annuaire}.css`.
Fichiers volontairement non lus (hors mandat) : les autres maquettes de `web/maquettes/`.

---

## 1. LE COMPOSANT DE RÉFÉRENCE : `topbar.js`

`web/topbar.js` est **le seul composant partagé qui existe déjà**. Son en-tête le dit : « Source unique du header » (topbar.js:3). Il injecte HTML + CSS au chargement (`inject()`, topbar.js:161-243).

### 1.1 Ce qu'il contient

- HTML : `const TOPBAR_HTML` (topbar.js:17-50) — `<header class="topbar">` avec `.logo-area` (img 44×44, `.name` « justicelibre » + `.tld` « .org », `.proto-badge` « bêta »), `nav.main-nav` à 5 liens + `.theme-toggle`, `.topbar-burger`, puis `.topbar-drawer` et `.topbar-overlay`.
- CSS : `const TOPBAR_CSS` (topbar.js:56-160).
- Comportements : publication de `--topbar-h` par mesure de `offsetHeight` (topbar.js:184-190), activation de `.active` par `location.pathname` (topbar.js:193-201), burger/drawer (topbar.js:204-219), theme-toggle sur la clé `jl-theme` (topbar.js:222-241).

### 1.2 Qui l'inclut

`web/search.html:685`, `web/annuaire.html:24`, `web/ressources.html:79`, `web/stats.html:11`, `web/inedits.html:68`, `web/tutoriel-piste.html:10`, `web/mentions-legales.html:10`, `web/confidentialite.html:10` — tous en `<script defer src="/topbar.js?v=5">` avec un point de montage `<div data-topbar-mount>`.

`ssr.py` en extrait le HTML **et** le CSS par expression régulière à chaque render : `_load_topbar_from_js()` (ssr.py:643-666) lit `/var/www/justicelibre/topbar.js` (ssr.py:640) et cherche `const TOPBAR_HTML = \`…\`.trim();` (ssr.py:650-651) et `const TOPBAR_CSS = \`…\`;` (ssr.py:654-655), avec cache 60 s (ssr.py:623).

### 1.3 Divergences exactes par rapport à `topbar.js`

**a) `ssr.py` : copie collée du CSS, en doublon de l'extraction.**
`ssr.py:441-473` redéclare intégralement le CSS de la topbar dans `SHARED_CSS`, sous le commentaire « Topbar (synchronisé avec /topbar.js — px absolus pour cohérence pixel) » (ssr.py:444) — et `get_topbar_css()` est **aussi** injecté, juste après, dans le même `<style>` (ssr.py:950-951, ssr.py:1140-1141, ssr.py:1196-1197). Le CSS topbar part donc en double sur chaque page SSR. Valeurs identiques (padding `13px 40px`, `font-size:15px`, logo `44px`, `.name` 17px, nav `gap:32px` / `12px` / `letter-spacing:1.5px`), sauf trois points :
- fond sombre : `rgba(30,30,28,.96)` (ssr.py:469 et ssr.py:472) contre `rgba(34,34,34,.96)` (topbar.js:70, topbar.js:71). Même écart dans `web/index.html:35` et `index.html:38` (`rgba(30,30,28,.96)`).
- bascule mobile : `@media(max-width:860px){.topbar nav.main-nav a:not(.active){display:none}}` (ssr.py:466) contre `.topbar nav.main-nav a{display:none}` + `.theme-toggle{display:flex}` + `.topbar-burger{display:flex}` (topbar.js:155-159). En SSR le burger n'est donc jamais affiché et le lien actif reste seul visible.
- `ssr.py` ne reprend ni `.topbar-burger`, ni `.topbar-drawer`, ni `.topbar-overlay` dans `SHARED_CSS` : ils n'arrivent que par `get_topbar_css()`. Le commentaire de `get_topbar_css()` le dit lui-même : « Sans ce CSS, le drawer mobile s'affiche en bloc sur desktop » (ssr.py:686).

**b) `ssr.py` : fallback HTML divergent.**
`_TOPBAR_FALLBACK` (ssr.py:625-637) n'a que **4** liens de nav — « Accueil », « Recherche », « MCP », « GitHub » — là où `topbar.js:26-31` en a **5** : « Accueil », « Recherche », « Ressources », « MCP », « GitHub ». Le fallback n'a ni `data-route`, ni `.theme-toggle`, ni burger, ni drawer, ni overlay, et son `title` de badge est `"Version bêta"` (ssr.py:629) contre `"Version bêta - moteur en rodage. Envoyer retour via GitHub ou Ko-fi."` (topbar.js:22).

**c) `web/index.html` : header entièrement réimplémenté, jamais `topbar.js`.**
index.html n'inclut pas `/topbar.js`. Son header est écrit à la main en HTML (index.html:402-436) et en CSS (index.html:42-184). Écarts mesurés :

| Propriété | topbar.js | index.html |
|---|---|---|
| padding de `.topbar` | `13px 40px` (topbar.js:61) | `1rem 2.5rem` (index.html:47) |
| logo `img` | `44px` × `44px` (topbar.js:76) | `60px` × `60px` (index.html:55) et `width="60" height="60"` (index.html:404) |
| `.name` | `17px` (topbar.js:79) | `1.25rem` (index.html:56) |
| nav `gap` | `32px` (topbar.js:85) | `2.2rem` (index.html:58) |
| lien de nav | `12px`, `letter-spacing:1.5px`, `padding-bottom:6px` (topbar.js:86-89) | `.82rem`, `letter-spacing:.12em`, `padding-bottom:.4rem` (index.html:60-61) |
| bascule mobile | tous les liens masqués + burger (topbar.js:155-159) | `a:not(.btn):not(.btn-search-nav){display:none}` (index.html:114), plus une seconde règle qui transforme `.btn-search-nav` en rond de 34px (index.html:116-126) |
| `.logo-area` | `<a href="/">` (topbar.js:19) | `<div>` non cliquable (index.html:403) |
| badge | `.proto-badge` « bêta » (topbar.js:23) | **absent** |
| liens | Accueil · Recherche · Ressources · MCP · GitHub (topbar.js:26-30) | « Se connecter », « Outils », « Ressources », « Légalité », « GitHub », « Soutenir », puis `.btn-search-nav` « Rechercher librement » (index.html:408-417) |
| lien actif | `.active` posé par `pathname` (topbar.js:193-201) | `.active` posé par scroll-spy sur les `section[id]` (index.html:736-755) |

Le burger, le drawer et l'overlay sont **redupliqués à l'identique** entre index.html:128-174 / index.html:427-436 / index.html:758-776 et topbar.js:118-160 / topbar.js:41-50 / topbar.js:204-219 : même largeur `280px`, même `max-width:85vw`, même `translateX(100%)`, même `box-shadow:-4px 0 24px rgba(0,0,0,.08)`, même `padding:80px 24px 24px`. Deux copies, pas une variante.

**d) `hub.html` et les maquettes : un autre header, appelé `.top`.**
`hub.html:316-319`, `carte-748.html:216-219`, `histo-02.html:257-260`, `decision-03b.html:137-141`, `decision-01.html:129-133`. Rien de commun avec `.topbar` sauf l'intention :

| | `.topbar` (topbar.js) | `.top` (hub + maquettes) |
|---|---|---|
| hauteur | `padding:13px 40px` (topbar.js:61) | `height:56px;padding:0 24px` (hub.html:28, carte-748.html:22, decision-03b.html:36) |
| logo | `<img src="/logo.svg">` 44px + `.name` | `.logo` texte pur, `font-size:20px`, serif, teal (hub.html:29-30) |
| `.tld` | `<span class="tld">` en teal (topbar.js:21) | `<span>` en `var(--muted)` (hub.html:30, hub.html:317) |
| nav | 5 liens + toggle + burger | 3 liens : « Recherche », « MCP », « GitHub » (hub.html:318) |
| libellés | « Accueil », « Recherche »… | « Recherche », « MCP », « GitHub » |
| cible des liens | `/search.html`, `/ressources.html` | `#/juris`, `https://justicelibre.org/mcp.html`, `https://github.com/justicelibre` (hub.html:318) — **compte GitHub différent** de celui du site prod, qui pointe partout ailleurs vers `https://github.com/Dahliyaal/justicelibre` (topbar.js:30, index.html:412, search.html:887) |
| theme-toggle | dans le header, clé `jl-theme` (topbar.js:222) | dans le **rail**, clé `hub-theme`, cycle à 3 états (hub.html:651-658) — sauf `decision-03b.html:140` et `decision-01.html:132` où il est remis dans `.nav`, toujours en `hub-theme` (decision-03b.html:225-227) |
| burger / drawer | oui | **aucun** |
| z-index | `100` (topbar.js:59) | `5` (hub.html:28), `20` (decision-03b.html:36) |

**Verdict : ce qui doit gagner.** `topbar.js` — c'est le seul qui existe déjà comme composant, le seul dont le SSR sait relire la source, et le seul qui a le drawer mobile. `.top` du hub est une seconde barre à absorber comme variante de densité (`--topbar-h: 56px`, logo textuel), pas comme composant distinct.

---

## 2. INVENTAIRE DES ÉLÉMENTS VISUELS

### 2.1 `header justicelibre.org`
Voir §1 en entier. Nom retenu : **header justicelibre.org** (vocabulaire propriétaire).
Variantes réelles : `.topbar` (topbar.js:18) · `.topbar` réimplémentée (index.html:42) · `.topbar` recopiée en Python (ssr.py:445) · `.top` (hub.html:28 et les 5 maquettes).
Ce qui gagne : `topbar.js`, parce qu'il est déjà la source unique pour 8 pages prod et pour le SSR, et qu'il est le seul à porter le drawer mobile.

### 2.2 `rail « Chercher dans »`
- Markup : `hub.html:321` (`<nav class="rail" id="rail">`), rempli par `renderRail()` hub.html:630-663 ; `carte-748.html:221` + `renderRail()` carte-748.html:267-280 ; `histo-02.html:262` + `renderRail()` histo-02.html:286-299 ; **en dur** dans `decision-03b.html:143-154` et `decision-01.html:135-146`.
- CSS : `hub.html:34-45` et `hub.html:85-91`, `carte-748.html:28-37`, `histo-02.html:29-38`, `decision-03b.html:41-45`, `decision-01.html:41-45`.
- Libellés, cités : `"Chercher dans"` (hub.html:632, carte-748.html:269, decision-03b.html:144) et `"Outils"` (hub.html:647, carte-748.html:271, decision-03b.html:150).
- Variantes mesurées :
  - largeur : `248px` (hub.html:34, carte-748.html:28, histo-02.html:29) contre `232px` (decision-03b.html:41, decision-01.html:41).
  - repli : `.rail.mini{width:60px}` (hub.html:35) et `52px` en dessous de 900px (hub.html:93) ; `carte-748.html:29` idem plus `.app{padding-left:52px}` (carte-748.html:39) que hub.html:93 n'a pas. Les maquettes décision **n'ont pas de mode mini** et masquent le rail : `@media (max-width:900px){.rail{display:none}}` (decision-03b.html:47, decision-01.html:47).
  - `.rail.mini` masque `.lbl,.n,.chev,.sub,.sec,.facets` (hub.html:36) contre seulement `.lbl,.n,.sec` (carte-748.html:30, histo-02.html:31).
  - `.ri:hover` : `{background:var(--cream)}` (hub.html:40) contre `{background:var(--cream);text-decoration:none}` (carte-748.html:34, decision-03b.html:44).
  - entrées : 5 scopes + « Vérifier mes citations » partout ; hub.html les rend en `<button>` désactivés pour les scopes « bientôt » (hub.html:636, `SOON` défini hub.html:629), les maquettes en `<a>` toujours actifs (carte-748.html:270, decision-03b.html:145-149).
  - compteurs affichés : `'4,3 M'`, `'3,4 M'`, `'109 k'`, `'75 k'` (hub.html:371-401 et carte-748.html:265, histo-02.html:284) ; les maquettes décision n'affichent **aucun** compteur (decision-03b.html:145-149).
- Ce qui gagne : la version `renderRail()` de `hub.html:630-663`, parce que c'est la seule qui sait rendre l'état « bientôt » et mémoriser le repli (`jl.railMini`, hub.html:605 et hub.html:662).

### 2.3 `pastille` (point de statut / source) — et sa variante loader
Quatre implémentations qui portent toutes un rond de 7 à 9 px :
1. `.dot` — `hub.html:90-91` : `7px`, couleur par `var(--c)`, variante `.dot.soon` en anneau vide (`background:transparent;border:1px solid var(--muted)`). Utilisée hub.html:641 et hub.html:854.
2. `.src-state i` — `hub.html:279-281` : `8px`, `.ok` → `var(--ok)`, `.ko` → `var(--bad)`, `.run` → `var(--warn)`. Markup hub.html:1060.
3. `.st::before` — `carte-748.html:71-73`, `histo-02.html:72-74`, `decision-03b.html:56-58`, `decision-01.html:56-58` : pastille `7px` **intégrée à une gélule** (`border-radius:10px`, bordure `currentColor`), avec `.st.q::before` réduite à `5px` et évidée. C'est la forme la plus aboutie.
4. `.vrow .dot` / `.mem .dot` — `carte-748.html:121-122` et `carte-748.html:154-156` : `9px`, `var(--ok)` / `var(--muted)` / `var(--doc)` pour `.fut`.
   Plus `.legend i` (carte-748.html:160) et `.jl-hkey i` (histo-02.html:241), tous deux `9px`, qui sont la légende de ces pastilles.
- Variante **loader** : `.spin` — `hub.html:275-276`, `carte-748.html:68-69`, `histo-02.html:69-70` : `14px`, bordure `2px var(--line)`, `border-top-color:var(--teal)`, animation `sp .8s linear infinite`. Version réduite en pastille : `.src-state .spin.sd{width:8px;height:8px;border-width:1.5px}` (hub.html:280) — c'est exactement « la pastille en mode loader ». Deux autres loaders coexistent : `.dots` / `.dots-inline` (search.html:313-341, 4 points qui sautent, `dotPulse 1.4s`) et `.sk` (hub.html:72-76, squelettes de cartes, `pulse 1.2s`).
- Ce qui gagne : `.st` + `.st::before` des maquettes (carte-748.html:71-73), parce que c'est la seule forme qui porte à la fois le point, le libellé et l'explication (`title=…why`, via `pill()` carte-748.html:317), et parce que `.st.q` (non résolu) y est déjà distinguée visuellement du plein.
- **Ressemble mais n'est pas la même chose** : `.src-badge` de search.html:276-285 est un rectangle plein de 5 couleurs (`--src-ce`, `--src-admin`, `--src-jud`, `--src-cedh`, `--src-cjue`, tokens.css:38-42) qui nomme **le fonds d'où vient le résultat**. Ce n'est pas un point de statut : il ne dit rien de vivant/mort/en cours. Le fusionner avec la pastille effacerait la distinction source / état.

### 2.4 `ligne-texte` (une ligne « texte + date + état »)
- `.hc-list li a` — hub.html:188-194 : `.meta` (mono, 11px) + `.t` (serif 16px) + `.x` (12.5px muted). Usages : hub.html:438 (derniers documents doctrine), hub.html:485 (textes hors code), hub.html:847 (travaux préparatoires).
- `.it` — carte-748.html:107-114 et histo-02.html:108-115 : `.rel` (mono 10.5px teal majuscules) + `.t a` + `.d` (métadonnées) + `.x`, avec `.it.dead{opacity:.55}` (carte-748.html:113).
- `.jl-item` — carte-748.html:206-210 : `.jl-rel` + `.jl-t` + `.jl-long` + `.jl-meta` + `.jl-more`, c'est la même ligne mais dans l'arbre.
- `.vise` — decision-03b.html:89-90 / decision-01.html:89-90 : `.t` + `.d`, ligne « article visé + rédaction + provenance ».
- `.mem` — carte-748.html:152-158 : grille `20px 1fr`, pastille + `.t` + `.d`.
- Ce qui gagne : `.jl-item` de carte-748.html:206-210, parce que c'est la seule qui a les cinq registres (relation, titre, titre long, métadonnées, renvoi) et que `.it` s'y ramène par suppression.
- **Ressemble mais n'est pas la même chose** : `.rec` (hub.html:244-245) est une ligne à deux colonnes `date | contenu` de largeur fixe `96px`, faite pour un tableau clé/valeur (hub.html:794, hub.html:1287, hub.html:1308). Elle n'a pas de titre cliquable ni d'état. Et `.result-card` (search.html:265-307) est une **carte de résultat de recherche** : elle porte un extrait surligné et un état actif/sélectionné (`.result-card.active`, search.html:270) que la ligne-texte n'a pas.

### 2.5 `chaîne` (succession de textes)
- `.chain` — carte-748.html:140-158 : conteneur `.ch` (en-tête cliquable avec chevron), `.alive`, `.dead-tog`, `.members`, `.head`, et les `.mem`. Déclaré aussi dans histo-02.html:141-159 et histo-05.html (même bloc) **mais non utilisé** dans ces deux fichiers : le code d'histo-02 rend la succession en lignes de Gantt (`predRows()`, histo-02.html:581-590), celui d'histo-05 en accordéons `.p5acc` (histo-05.html:574-579).
- Modèle de données commun, identique dans les trois : `predsOf()` récursif (histo-02.html:405-412, carte-748.html:378-382) qui suit `{de, vers, type:'abroge'}`, et `retouchesOf()` qui suit `{de, vers, type:'modifie'}` (histo-02.html:397-402, carte-748.html:371-376).
- Trois rendus concurrents de la même chaîne : `.jl-tree` / `.jl-node` (carte-748.html:198-211, connecteurs en `::before`/`::after`), `.g2row` / `.g2bar` / `.g2cap` / `.g2notch` (histo-02.html:518-557, frise Gantt) et `.p5acc` / `.p5frise` (histo-05.html:530-559, poupées russes).
- Ce qui gagne : `.jl-tree` (carte-748.html:198-211) comme forme compacte par défaut, parce que c'est celle que la CARTE affiche sans interaction ; les deux autres sont des **vues** de la page Historique, pas des variantes du même composant.
- **Ressemble mais n'est pas la même chose** : `.p5frise` (histo-05.html:550-556) n'est pas la chaîne, c'est un **résumé horizontal** de la chaîne (pris → retouché → abrogé) placé en tête de l'accordéon. Elle ne porte aucun lien ni aucun état cliquable.

### 2.6 `point-frise`
Cinq dessins du même objet :
| Implémentation | Fichier:ligne | Forme |
|---|---|---|
| `.tl-item::before` | index.html:362-379 | `14px`, bordure `2px var(--teal)`, fond `--white` ; `.done` plein, `.next` avec `box-shadow:0 0 0 3px rgba(26,78,78,.25)`, `.pending` bordure `--line` |
| `.tl .ev::before` | hub.html:293-295 | `12px`, bordure `2px var(--teal)` ; `.bad` plein `--bad`, `.soon` bordure pointillée `--muted` |
| `.chrono li::after` | decision-03b.html:95-96, decision-01.html:95-96 | `9px`, fond `--line`, bordure `1px var(--muted)` ; `.cur` plein teal |
| `.p5seg i` | histo-05.html:552-554 | `9px`, `--ok` ; `.dead` `--muted` ; `.art` agrandi à `12px` en teal |
| `.g2mark` / `.g2cap` / `.g2notch` | histo-02.html:531-532, histo-02.html:550 | losange orange `12px` (retouche), bouchon rouge `3×16px` (abrogation), encoche `3×26px` |
Barres verticales associées : `.timeline::before` (index.html:354-359, `2px var(--line)`), `.tl` (hub.html:291, `border-left:2px solid var(--line)`), `.chrono li::before` (decision-03b.html:93, `1px var(--line)`).
- Ce qui gagne : `.tl .ev::before` de hub.html:293-295, parce que c'est le seul dont les trois états (normal / mort / à venir) sont déjà mappés sur la règle de couleur — teal actif, rouge atténué mort, pointillé gris à venir.
- **Ressemble mais n'est pas la même chose** : `.steps li::before` (index.html:285-290) est un **compteur** (`counter(st)`, chiffre blanc dans un disque teal de 1.4rem), pas un point d'état. Et `.g2mark` (histo-02.html:531) est un losange positionné en abscisse temporelle : il ne marque pas une étape dans une liste verticale, il marque une date sur un axe.

### 2.7 `bande-identité` (métadonnées en tête, sans boîte)
- `.idband` — carte-748.html:90-94 et histo-02.html:91-95 : `grid-template-columns:repeat(auto-fit,minmax(150px,1fr))`, `gap:0`, séparateurs par `border-left:1px solid var(--line)` sur chaque enfant, premier enfant sans bordure ni padding gauche. **Sans boîte** : ni fond, ni bordure extérieure. Contenu : `.k` (10px, majuscules, `letter-spacing:.1em`, `--muted`) + `.v` (13px).
- `.idband` — decision-01.html:112-114 : **même nom, boîte ajoutée** — `background:var(--white);border:1px solid var(--line);border-radius:8px;padding:10px 0`, `.k` à `10.5px`. C'est la variante encadrée.
- `.idband` — decision-03b.html:112-113 : **troisième forme**, `display:flex;flex-wrap:wrap;gap:6px 22px`, et le `.k` est en ligne (`margin-right:6px`) au lieu d'être au-dessus. Markup decision-03b.html:156 (`<div><span class="k">Juridiction</span>Cour de cassation</div>`) contre decision-01.html:148 (`<div><div class="k">Juridiction</div><div class="v">Cour de cassation</div></div>`).
- Équivalents encadrés ailleurs : `.meta-table` (ssr.py:498-505, tableau `<th>/<td>` à 30 % / 70 %), `.doc-meta` (search.html:392-397, flex `gap:1.2rem` avec `<strong>` en ligne), `.kv` (hub.html:286-287, grille `150px 1fr`).
- Libellés cités, communs à decision-01 et decision-03b : `"Juridiction"`, `"Formation"`, `"Date"`, `"Pourvoi"`, `"ECLI"`, `"Solution"`, `"Publication"`, `"Audience"` (decision-03b.html:156, decision-01.html:148). Ceux de carte-748 : `"État à la date lue"`, `"Rédactions"`, `"Objet"`, `"Identifiant"`, `"Source"` (carte-748.html:487-491). Ceux d'histo-02 : `"État à la date lue"`, `"Rédactions"`, `"Événements retenus"`, `"Textes en jeu"`, `"Objet"` (histo-02.html:480-484).
- Ce qui gagne : la version **sans boîte** de carte-748.html:90-94, qui est celle que la propriétaire a nommée ; la variante `decision-01.html:112` doit devenir un modificateur (`--encadree`) et non un second composant.

### 2.8 `bouton d'action teal` (Chercher / Historique)
Sept déclarations d'un bouton plein teal, majuscules, `letter-spacing`, `border-radius:4px` :

| Classe | Fichier:ligne | padding | font-size | letter-spacing | font-weight |
|---|---|---|---|---|---|
| `.btn` | index.html:78-85 | `.85rem 1.8rem` | `.78rem` | `.12em` | 700 |
| `.btn-search-nav` | index.html:87-97 | `.85rem 1.8rem` | `.78rem` | `.12em` | 700 |
| `.jl-btn` | components.css:18-28 | `var(--space-3) var(--space-5)` = `12px 20px` | `var(--text-sm)` = `.78rem` | `var(--ls-wider)` = `.12em` | 700 |
| `.sb-primary button.submit` | search.html:72-77 | `.75rem 1.8rem` | `.8rem` | `.1em` | 700 |
| `.btn` | annuaire.css:131-132 | `.85rem 1.8rem` | `.78rem` | `.12em` | 700 |
| `.cta` | ssr.py:551-553 | `.6rem 1.2rem` | `.85rem` | — (pas de majuscules) | — |
| `.cta` | carte-748.html:45-47, histo-02.html:46-48 | `.85rem 1.8rem` | `.78rem` | `.12em` | 700 |
| `.btn` | hub.html:250-252 | `9px 16px` | `12px` | `.08em` | 600 |
| `.btn` | carte-748.html:86-87, histo-02.html:87-88 | `8px 14px` | `12px` | `.08em` | 600 |
| `.cta` | decision-03b.html:64-65, decision-01.html:64-65 | `.7rem 1.3rem` | `12px` | `.1em` | 700 |
| `.sbar .go` | hub.html:101 | `0 22px` (hauteur du champ) | `12px` | `.1em` | 600 |

Libellés cités : `"Chercher"` (hub.html:684, search.html:721), `"Historique"` (carte-748.html:485), `"↺ Historique"` (carte-748.html:452), `"Rechercher librement"` (index.html:415), `"Accéder à l'endpoint MCP"` (index.html:443), `"Charger la suite"` (search.html:1630), `"Charger la suite"` (hub.html:1094), `"Générer mon token"` (tutoriel-piste.html:230).

Variantes secondaires : `.btn.ghost` (hub.html:251, carte-748.html:87 : transparent, `1px solid var(--teal)`), `.jl-btn--ghost` (components.css:38-42, identique), `.btn` de decision-03b.html:66-67 (**déjà en ghost par défaut** : fond `--white`, bordure teal, texte teal — même nom de classe, apparence opposée à hub.html:250), `.btn-secondary` (annuaire.css:134-135), `.load-more` (search.html:368-377 : ghost qui s'inverse au hover), `.jl-btn--secondary` (components.css:32-36 : fond `--teal-xl`, **sans majuscules**), `.kofi-btn` (index.html:67-77 : teal mais `.85rem`, `font-weight:600`, sans majuscules).

- Ce qui gagne : `.jl-btn` de components.css:18-53, parce qu'il est déjà tokenisé (`--space-*`, `--text-sm`, `--ls-wider`, `--radius-md`) et qu'il a déjà les cinq modificateurs (`--primary`, `--secondary`, `--ghost`, `--pill`, `--sm`) et l'état `[disabled]`.
- **Piège à ne pas fusionner** : `.btn` vaut **plein teal** dans hub.html:250 et **ghost** dans decision-03b.html:66. Une normalisation naïve inverserait l'apparence de tous les boutons des maquettes décision.
- **Ressemble mais n'est pas la même chose** : `.chip` (hub.html:140-144) et `.pill` (hub.html:224-226) ont la même couleur à l'état `.on` (fond teal, texte blanc) mais ce sont des **filtres à bascule**, pas des actions : `.chip.on` dit « ce filtre est actif », `.btn` dit « clique ici ». Idem `.preset.on` (hub.html:161) et `.jl-hfil.on` (histo-02.html:231).

### 2.9 `note de provenance`
- `.how` — carte-748.html:115, histo-02.html:116, decision-03b.html:59, decision-01.html:59 : mono, `9.5px` (carte-748, histo-02) ou `10.5px` (decision-03b, decision-01), **bordure en pointillés** `1px dashed var(--line)`, `cursor:help`. Le pointillé est le signal : provenance, pas état.
- Libellés cités, tels quels : `"visa"`, `"lien LEGI"`, `"succession"` (dictionnaire `HOWTIP`, carte-748.html:436-440 et histo-02.html:333-337) ; `"repéré dans le texte"` (decision-03b.html:156, decision-03b.html:216 — 5 occurrences), `"repéré dans le texte (en-tête)"` (decision-03b.html:156), `"repéré dans le texte, § 6"` (decision-03b.html:216), `"repéré dans le texte (en-tête et § 1)"` (decision-03b.html:216), `"métadonnées DILA + texte"` (decision-03b.html:216), `"sommaire officiel · DILA"` (decision-03b.html:163), `"abstrats · DILA"` (decision-03b.html:163), `"recherche lexicale"` (decision-03b.html:216), `"texte"` (decision-03b.html:156).
- Fonction de rendu : `metaHTML()` carte-748.html:441 et `howHTML()` histo-02.html:338 — deux écritures du même une-ligne.
- Autres marqueurs de provenance, forme différente : `.src` (carte-748.html:74, decision-03b.html:61 — mono, majuscules, bordure **pleine**, ex. `"LEGI"`, `"Judilibre · DILA"`), `.off` (hub.html:265 — `"sommaire officiel"`, teal, sans bordure), `.warnp` (hub.html:266, carte-748.html:65 — bordure `--warn`, ex. `"aperçu"`, `"maquette"`, `"numéro recyclé"`, `"pas d'extrait renvoyé"`).
- Ce qui gagne : `.how` (carte-748.html:115), avec sa bordure en pointillés — c'est le seul signe qui distingue visuellement « d'où je le sais » de « ce que c'est ».
- **Ressemble mais n'est pas la même chose** : `.warnp` (hub.html:266) a la même taille et la même forme que `.how` mais il porte un **avertissement sur la donnée** (« maquette », « numéro recyclé ») et non la provenance d'un lien. Sa bordure est pleine et colorée `--warn` ; celle de `.how` est en pointillés et neutre `--line`. Les fusionner rendrait indistinguable « je sais ceci par un visa » de « attention, ce numéro a été recyclé ».

### 2.10 `bloc honnêteté` (« ce que la page ne sait pas »)
- `.honest` — carte-748.html:78-79, histo-02.html:79-80, decision-03b.html:62-63, decision-01.html:62-63 : `12.5px`, `--muted`, `border-left:3px solid var(--warn)`, fond `var(--warn-bg)`, `border-radius:0 6px 6px 0`, `b{color:var(--ink)}`. Identique aux quatre endroits.
- Variante **sans fond** : `.carte .honest` (hub.html:1181, injecté à chaud dans `showCarte()`) : `border-left:2px solid var(--line)`, aucun fond.
- Autre variante : `.jl-hhonest` (histo-02.html:226) qui n'ajoute que `margin:22px 0 0;line-height:1.55` à `.honest`.
- Autres encadrés d'aveu : `.note` (hub.html:246 : fond `--warn-bg`, bordure `1px solid var(--line)`), `.alert` (hub.html:247-248, carte-748.html:63-64 : fond `--bad-bg`, **bordure 2px** `--bad`), `.infobox` (ressources.html:70-72 et annuaire.css:91-94 : fond `--teal-xl`, `border-left:4px solid var(--teal)`, variante `.infobox.warn` fond `#fef9e8` bordure `--gold`), `.jl-callout` (components.css:117-133), `.lang-warning__inner` (ssr.py:519-522 : fond `#fff8e6`, `border-left:4px solid var(--gold)`), `.source-warning` (search.html:357-362 : `rgba(184,147,43,.08)`).
- Titres cités : `"Ce que cette page ne sait pas"` (decision-01.html:157), `"Ce que cette page montre, et ce qu'elle laisse dehors."` (histo-02.html:488), `"Ce que nous n'avons pas"` (hub.html:1304), `"Ce que la page ne fait jamais"` (hub.html:1309), `"Ce qu'on ne fait pas"` (hub.html:1287), `"Champs absents (8)"` (decision-01.html:157).
- Ce qui gagne : `.honest` tel qu'écrit en carte-748.html:78-79 — bordure gauche `3px --warn` sur fond `--warn-bg` : quatre fichiers l'ont déjà à l'identique, c'est la seule règle qui n'a jamais dérivé.
- **Ressemble mais n'est pas la même chose** : `.alert` (hub.html:247) est un **échec**, pas un aveu : bordure `2px --bad`, il est monté par `showDecision()` quand le fetch échoue (hub.html:1141) ou qu'un fonds n'existe pas (hub.html:434). `.honest`, lui, est du contenu éditorial permanent. Confondre les deux ferait clignoter en rouge d'erreur des phrases qui sont de la méthode.

### 2.11 `onglets`
- `.tabs` — decision-03b.html:115-122 : onglets en **CSS pur**, via `<input type="radio" class="tab">` (decision-03b.html:119-121, markup decision-03b.html:160-161) et sélecteurs frères `#t-texte:checked ~ .tabs label[for=t-texte]` (decision-03b.html:121-122). Sticky sous le header : `top:56px;z-index:10` (decision-03b.html:115). Libellés cités : `"Texte"`, `"Dossier"` (decision-03b.html:161). Le JS ne fait que synchroniser l'ancre (decision-03b.html:243-251).
- `.seg` — hub.html:256-257 : segmented control, `border-radius:4px`, `overflow:hidden`, `button.on{background:var(--teal);color:#fff}`. Libellés cités : `"Sommaire"`, `"Extrait"`, `"Pertinence"`, `"Récent"`, `"Ancien"` (hub.html:1088).
- `.jl-view` — histo-02.html:249-252 : même dessin que `.seg` mais en `<a>` et `border-radius:6px`, majuscules `11.5px`. Libellés cités : `"Couloirs"`, `"Poupées russes"` (histo-02.html:468).
- `.range-bar button` — stats.html:50-53 : boutons séparés (pas de groupe soudé), `.active{background:var(--teal)}`. Libellés cités : `"Aujourd'hui"`, `"7 jours"`, `"30 jours"`, `"365 jours"` (stats.html:122-125).
- `.toc a.on` — decision-03b.html:78-81 : sommaire latéral collant, `border-left:2px`, activé par IntersectionObserver (decision-03b.html:235-240) — c'est une navigation intra-page, pas des onglets.
- `decision-01.html` **n'a pas d'onglets** : les deux panneaux sont côte à côte en grille `.grid{grid-template-columns:minmax(280px,340px) minmax(0,1fr)}` (decision-01.html:115).
- Ce qui gagne : `.jl-view` (histo-02.html:249-252) pour la navigation entre vues et `.seg` (hub.html:256) pour les bascules d'affichage — ce sont le **même dessin** à `border-radius` près (4px vs 6px) et à la taille près (12px vs 11.5px), donc un seul composant à deux tailles. `.tabs` de decision-03b reste à part : il commute des panneaux entiers, pas une option.

### 2.12 `popover de date`
- `.datepop` — carte-748.html:52-62, histo-02.html:53-63 : ouvert par `.calbtn` (carte-748.html:49-51), classe `.open`, `min-width:280px`, `box-shadow:0 8px 24px rgba(0,0,0,.12)`. Trois entrées : champ texte `jj/mm/aaaa` + bouton, `<input type="date">`, puces de rédactions. Libellés cités : `"Saisir une date"`, `"Ou choisir dans le calendrier"`, `"Ou sauter à une rédaction"`, `"Lire"`, `"aujourd'hui"` (carte-748.html:481-483), message d'erreur `"Date illisible : attendu jj/mm/aaaa"` (carte-748.html:509, histo-02.html:503).
- `.cal` — hub.html:205-217 : **calendrier complet fabriqué en JS** (`openCal()`, hub.html:719-744) : grille 7 colonnes, sélecteurs mois/année, navigation `‹ ›`, et raccourcis `"Toute l'année ${y}"` / `"Tout ${mois}"` / `"Effacer"` (hub.html:732). `width:248px`, `box-shadow:0 8px 24px rgba(0,0,0,.18)`.
- Champs de date natifs ailleurs : `input type="date"` dans search.html:791 et search.html:796 (libellés `"Date (à partir de)"` / `"Date (jusqu'au)"`), hub.html:816 (`"au"`), hub.html:1204 (`"· changer"`), hub.html:1246 (`"· changer la date"`), hub.html:1285 (`"à la date du litige"`).
- Ce qui gagne : `.datepop` (carte-748.html:52-62) comme enveloppe, avec le calendrier `.cal` de hub.html:205-217 **à l'intérieur** en remplacement de l'`input type=date` natif — c'est la seule combinaison qui offre les trois entrées (saisie, calendrier, saut à une rédaction) sans dépendre du rendu natif du navigateur.
- **Ressemble mais n'est pas la même chose** : `.cs-panel` (components.css:171, search.html:182-189, annuaire.css:144) est un panneau flottant de mêmes dimensions et même ombre (`0 6px 20px rgba(0,0,0,.12)`), mais c'est un **menu déroulant de sélection** : il se ferme au choix d'une valeur (search.html:1023) et se pilote à la molette (stats.html:318-332). Le popover de date, lui, garde plusieurs champs actifs simultanément.

### 2.13 Autres éléments récurrents non nommés par la propriétaire

**`jl-titre-section`** — le titre noir de section de contenu.
`.jl-section__title` (components.css:137-144 : serif, `--text-2xl`, `--ink`, `border-bottom:2px solid var(--teal-xl)`), `section.block > h2` (annuaire.css:23-24 et ressources.html:42-43 : **exactement les mêmes valeurs**, `1.8rem`, même bordure), `h2.sec` (decision-03b.html:53 : serif 20px, sans bordure), `.juris h2` (carte-748.html:163-164 : serif 20px), `.feed-h` (hub.html:56-57 : serif 22px, `border-top:1px solid var(--line)` au lieu de `border-bottom`), `h2` (stats.html:70-73 : `border-top`), `.h5` (hub.html:25, carte-748.html:21, decision-03b.html:35 : 10 ou 10.5px, majuscules, `--muted` — c'est le **sur-titre**, pas le titre), `.h-k` (decision-03b.html:55 : identique au `.h5` mais en flex), `.jl-h2` (histo-02.html:234 : 10px majuscules mais en `--ink`).
Ce qui gagne : `.jl-section__title` de components.css:137-144, déjà tokenisé, avec `.h5` comme sur-titre séparé.
**Ressemble mais n'est pas la même chose** : `.h5` (10px, majuscules, muted) et `.jl-h2` (histo-02.html:234, 10px, majuscules, **`--ink` et gras**) ont la même métrique mais des rôles opposés : le premier étiquette une zone secondaire, le second titre une section. La règle de couleur de la propriétaire tranche : noir = titre de section, gris = inactif.

**`jl-tuile`** — la carte cliquable.
`.tile` (hub.html:228-232), `.jl-card` (components.css:56-77 avec `--hoverable`, `--highlight`, `--coming`), `.card` (ressources.html:48-67 avec `.card.coming::after{content:"bientôt"}` ressources.html:66), `.cat-card` (annuaire.css:98-103), `.cat-grid a` (inedits.html:59-62), `.stat-card` (index.html:236-244 et stats.html:56-67), `.stat` (annuaire.css:28-31), `.inedits-stats .tile` (inedits.html:55-57), `.tool-card` (index.html:297-306), `.jc` (carte-748.html:166-172), `.bottom .card` (carte-748.html:174), `.card` (decision-03b.html:68).
Écarts mesurés sur le même objet : `border-radius` `6px` (hub.html:228, ressources.html:48, annuaire.css:98) contre `8px` (carte-748.html:166, decision-03b.html:68) contre `4px` (inedits.html:55, inedits.html:59) ; hover `border-color:var(--teal)` partout, plus `transform:translateY(-1px)` dans annuaire.css:100 et inedits.html:60, plus `box-shadow:0 2px 12px rgba(26,78,78,.08)` dans index.html:301 (= `--shadow`, tokens.css:95).
Ce qui gagne : `.jl-card` (components.css:56-77), seule version avec les trois modificateurs déjà écrits, dont `--coming` qui porte le libellé `"bientot"` (components.css:74 — **sans accent**, alors que ressources.html:66 écrit `"bientôt"`).

**`jl-menu` (dropdown custom `.cs-*`)** — **déjà triplé à l'identique**.
CSS : components.css:165-175, search.html:170-220, annuaire.css:138-148. Les trois blocs sont identiques à deux valeurs près : `max-width:420px` (search.html:184) contre `460px` (components.css:171, annuaire.css:144) ; `min-width:260px` (components.css:165, annuaire.css:138) contre `width:100%` (search.html:170). search.html ajoute seul `.cs-group` (search.html:198-218) et `.cs-item.cs-sub` (search.html:219-220).
JS : `bindCs()` écrit **quatre fois** — search.html:999-1026, annuaire.html:6528-6551, stats.html:295-333, inedits.html (l. 246-275 environ, dans le bloc `<script>` ouvert l. 244). Celui de stats.html est le seul à gérer la molette (stats.html:318-332) ; celui d'annuaire.html est le seul avec un garde-fou `dataset.bound` (annuaire.html:6530-6531) ; celui de search.html est le seul à ne pas poser lui-même les fermetures globales (elles sont hors fonction, search.html:1028-1035).
Ce qui gagne : la fusion `bindCs` de stats.html:295-333 (molette) + le garde `dataset.bound` d'annuaire.html:6530 + les groupes `.cs-group` de search.html:198-218.

**`jl-barre-recherche`** — `.sbar` (hub.html:98-103 : `border:1.5px solid var(--teal)`, un seul bloc soudé avec `.go`, `.dt`, `.advt`) contre `.sb-primary` (search.html:43-87 : grille `1fr 200px 190px auto auto` de cinq contrôles distincts). Deux mises en page, un seul rôle.
Ce qui gagne : `.sbar` du hub, parce qu'elle porte le panneau avancé (`.adv`, hub.html:118) en continuité visuelle (`border-top:0;border-radius:0 0 8px 8px`) alors que `.sb-advanced` de search.html:90-104 est un bloc détaché piloté par `max-height`.

**`jl-tableau`** — `table.data` (annuaire.css:53-78, réutilisé par inedits.html), `table.tb` (hub.html:308-310), `.coverage` (annuaire.css:33-42), `.meta-table` (ssr.py:498-505), `.tool-row` (stats.html:76-84, grille et non `<table>`), `table` (confidentialite.html:46-48). Six dessins de tableau ; seul `table.data` a le tri au clic (`th.sortable`, inedits.html:49-52 et annuaire.css:54-59) et les en-têtes collants (`position:sticky;top:0`, annuaire.css:54).

**`jl-modale`** — `.jl-modal-overlay` / `.jl-modal` (annuaire.css:151-166), construite en JS dans annuaire.html:6630-6643 et **réécrite** dans inedits.html (bloc l. 336-352 environ, chaîne `'<div class="jl-modal" role="dialog" aria-modal="true" style="max-width:640px">'`). Le modal de feedback de search.html:874-884 est du **style inline pur** (`style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.55)…"`) : même objet, zéro classe partagée.

**`jl-pied`** — `footer.foot` (annuaire.css:112-114, repris par annuaire.html:6412, inedits.html:238 environ, ressources.html:440), `.footer-min` (search.html:559-564), `footer` (index.html:318-347, trois colonnes), `footer.page-footer` (ssr.py:547-549). Quatre pieds, quatre listes de liens différentes.

**`jl-impression`** — trois feuilles `@media print` très proches : search.html:573-683, ssr.py:561-614, decision-03b.html:109 (une ligne). Les deux premières partagent la même intention et jusqu'aux mêmes valeurs (`@page{margin:18mm 16mm}` search.html:574 = ssr.py:562 ; `font-size:10.5pt;line-height:1.45` search.html:628 = ssr.py:588 ; `orphans:3;widows:3` search.html:630 = ssr.py:590) et la même phrase de pied, à 20 caractères près :
- search.html:679 : `"Imprimé depuis justicelibre.org — base de jurisprudence en accès libre"`
- ssr.py:610 : `"Imprimé depuis justicelibre.org — base de jurisprudence en accès libre, Licence Ouverte 2.0"`

---

## 3. VARIABLES CSS RÉELLEMENT UTILISÉES, PAR PAGE

### 3.1 Les deux palettes

**Palette A — `styles/tokens.css`** (chargée par index.html:29, search.html:15, ressources.html:19, stats.html:17, annuaire.html:20, inedits.html:18, et par ssr.py:433) :
`--teal:#1a4e4e` · `--teal-l:#2a6b6b` · `--teal-xl:#e8f0f0` · `--ink:#1a1a1a` · `--body:#3a3a3a` · `--muted:#6b6b6b` · `--light:#f5f5f3` · `--white:#ffffff` · `--line:#e0ddd6` · `--gold:#b8932b` · `--red:#8a1f1f` · `--green:#1a7a3e` · `--cream:#fdfcf8` · `--src-ce:#1a4e4e` · `--src-admin:#2a6b6b` · `--src-jud:#5c3317` · `--src-cedh:#6b3d8a` · `--src-cjue:#8a5c2b` (tokens.css:17-42).
Sombre (tokens.css:112-135, dupliqué tel quel en tokens.css:138-163) : `--teal:#4ea0a0` · `--teal-l:#66baba` · `--teal-xl:#1e3a3a` · `--ink:#e8e6df` · `--body:#c8c5bc` · `--muted:#8a867d` · `--light:#141413` · `--white:#1e1e1c` · `--line:#2a2a27` · `--gold:#d4b050` · `--red:#c85c5c` · `--green:#5cc88a` · `--cream:#1a1a1a`.

**Palette B — hub + maquettes** (hub.html:10-11, carte-748.html:9-10, histo-02.html:10-11, histo-05.html:10-11, decision-03b.html:24, decision-01.html:24) :
`--teal` · `--teal-l` · `--teal-xl` · `--ink` · `--muted` · `--white` · `--line` · `--cream` **mêmes valeurs que A**, plus 12 variables qui n'existent pas dans A :
`--warn-bg:#fbf1dc` · `--warn:#8a5a12` · `--bad-bg:#fbe3e0` · `--bad:#8a2a1f` · `--ok:#1f6f4a` · `--ok-bg:#dff0e3` · `--jud:#2f5d8a` · `--adm:#7a5c1e` · `--ce:#1f6f4a` · `--eu:#6d3e8c` · `--txt:#8a4a1f` · `--doc:#4e5a8c`.
Sombre : `--warn-bg:#3a2e14` · `--warn:#e0b060` · `--bad-bg:#3d1c18` · `--bad:#f0a090` · `--ok:#6fc29a` · `--ok-bg:#1d3a28` · `--jud:#7fa6d6` · `--adm:#c9a55c` · `--ce:#6fc29a` · `--eu:#b98ad6` · `--txt:#d6905c` · `--doc:#93a0d6`.
La palette B **n'a ni `--body`, ni `--light`, ni `--gold`, ni `--red`, ni `--green`** : le corps de texte y est `--ink` directement (hub.html:18).

### 3.2 Tableau par page

| Page | Source des variables | Divergences relevées |
|---|---|---|
| `index.html` | tokens.css:29 + `<style>` local index.html:31-397 | ne redéfinit aucune variable ; mais écrit `rgba(30,30,28,.96)` en dur (index.html:35) et `#1a1a1a` / `#f0f0e8` en dur (index.html:271) et `#0a0a0a` (index.html:275) |
| `search.html` | tokens.css:15, base.css:16, components.css:17 | aucune redéfinition ; couleurs en dur : `rgba(212,176,80,.2)` (search.html:30), `rgba(184,147,43,.25)` (search.html:300), `#1a7a3e` et `rgba(26,122,62,.4)` (search.html:420-421), `#5cc88a` (search.html:430) — ces deux dernières **dupliquent** `--green` (tokens.css:32 clair, tokens.css:132 sombre) |
| `annuaire.html` | tokens.css:20, base.css:21, components.css:22, annuaire.css:23 | annuaire.css:119-123 écrit `#7a1e2f` / `#5c1523` / `#b8932b` en dur — le dernier est `--gold` ; annuaire.css:38 et annuaire.html:6508 écrivent `#c1440e` (rouge d'échec) qui n'existe dans aucun token |
| `ressources.html` | tokens.css:19, base.css:20, components.css:21 | ressources.html:55 écrit `#fef9e8` en dur (= fond de `.jl-badge--gold`, components.css:97) |
| `stats.html` | tokens.css:17, base.css:18, components.css:19 | aucune couleur en dur |
| `inedits.html` | tokens.css:18, base.css:19, components.css:20, annuaire.css:21 | `#7a1e2f` (inedits.html:24, inedits.html:61), `#fef9e8` + `#b8932b` (inedits.html:48) |
| `tutoriel-piste.html` | **redéfinit tout en local** (tutoriel-piste.html:27-49) : ne charge aucun fichier de `styles/` | palette partielle : `--teal --teal-l --teal-xl --ink --body --muted --light --white --line --gold --red` + `--display --sans --mono`. **`--red:#8a1f1f` en clair mais `--red:#d26a6a` en sombre** (tutoriel-piste.html:40) contre `--red:#c85c5c` dans tokens.css:126 — **valeur divergente** |
| `mentions-legales.html` | **redéfinit en local** (mentions-legales.html:28-34), aucun `styles/` | palette réduite : `--teal --teal-l --teal-xl --ink --body --muted --light --white --line` + `--display --sans`. **Pas de `--teal-l` en sombre** (mentions-legales.html:31) |
| `confidentialite.html` | **redéfinit en local** (confidentialite.html:28-34), aucun `styles/` | identique à mentions-legales, même manque de `--teal-l` en sombre |
| `ssr.py` | tokens.css + base.css + components.css **en v=20260501** (ssr.py:433-435) alors que les pages HTML chargent base.css en `v=20260720` et components.css en `v=20260719b`/`20260720` | plus `SHARED_CSS` (ssr.py:441-615) qui écrit `#a33` (ssr.py:988), `#fff8e6` (ssr.py:519), `rgba(30,30,28,.96)` (ssr.py:469), `rgba(26,78,78,.3)` (ssr.py:538) |
| `hub.html` | palette B locale (hub.html:10-15) | ajoute à chaud, dans `showCarte()`, des couleurs en dur : `#2a7d4f` / `#8fcaa6` / `#a33` / `#e0a0a0` (hub.html:1176) et `#dff0e3` (hub.html:304) et `#1d3a28` (hub.html:305-306) — ces deux derniers sont exactement `--ok-bg` de la palette B, non déclaré dans hub.html |
| `carte-748.html` | palette B locale (carte-748.html:9-12), **avec `--ok-bg`** | `#fff` en dur dans `.cta` (carte-748.html:45), `.btn` (carte-748.html:86), `.jl-branch>.bt .c` (carte-748.html:205) |
| `histo-02.html` / `histo-05.html` | palette B locale (histo-02.html:10-13) | histo-02.html:567 déclare `const COL = ['#1a4e4e','#2f5d8a','#7a5c1e','#6d3e8c']` — **réécriture littérale de `--teal`, `--jud`, `--adm`, `--eu`** ; variable `COL` déclarée et jamais utilisée dans la suite de `VIEW()` |
| `decision-03b.html` / `decision-01.html` | palette B locale (decision-03b.html:24-26) | **`--muted:#5f5f5f`** et **`--line:#2e2e2b`** en sombre — divergent de `--muted:#6b6b6b` / `--line:#2a2a27` de hub.html:10 et de tokens.css:24/27. Palette amputée de `--jud` mis à part : ni `--adm`, ni `--ce`, ni `--eu` |

### 3.3 Doublons de variables à trancher

| Doublon | Où | Verdict |
|---|---|---|
| `--display` / `--sans` / `--mono` **vs** `--font-serif` / `--font-sans` / `--font-mono` | tokens.css:45-51 déclare les deux, les premiers comme alias : « Aliases historiques (pour compatibilite avec le CSS existant - a deprecer plus tard) » (tokens.css:48) | garder `--font-*`, les alias sont déjà marqués à déprécier par le fichier lui-même |
| `--red` (tokens.css:31) **vs** `--bad` (hub.html:10) | `#8a1f1f` contre `#8a2a1f` — **valeurs différentes de 11 sur le canal vert** ; en sombre `#c85c5c` (tokens.css:126) contre `#f0a090` (hub.html:14) | `--bad` + `--bad-bg` (la paire fond/texte existe, `--red` est seul) |
| `--red` sombre : `#c85c5c` (tokens.css:126) **vs** `#d26a6a` (tutoriel-piste.html:40) | deux valeurs pour la même variable | `#c85c5c`, valeur du fichier de tokens |
| `--green` (tokens.css:32, `#1a7a3e`) **vs** `--ok` (hub.html:10, `#1f6f4a`) | deux verts « en vigueur / correspond à » | `--ok` + `--ok-bg` |
| `--gold` (tokens.css:30, `#b8932b`) **vs** `--warn` (hub.html:10, `#8a5a12`) | le premier sert de fond d'avertissement (`.card.coming::after` ressources.html:67, `.jl-badge--proto` components.css:93), le second de bordure d'avertissement (`.warnp` hub.html:266, `.honest` carte-748.html:78) | `--warn` + `--warn-bg`, et `--gold` devient un alias |
| `--light` (tokens.css:25, `#f5f5f3`) **vs** `--cream` (tokens.css:35, `#fdfcf8`) | deux surfaces alternatives ; search.html:21 met `--light` en fond de page, annuaire.css:4 et hub.html:18 mettent `--cream` | à trancher par la propriétaire : trois pages prod utilisent l'une, le prototype entier utilise l'autre |
| `--body` (tokens.css:23) absent de la palette B | hub.html:18 met `--ink` sur le body | ajouter `--body` à la palette unifiée, sinon le corps de texte du hub est plus noir que celui du site prod |
| `--src-ce/--src-admin/--src-jud/--src-cedh/--src-cjue` (tokens.css:38-42) **vs** `--jud/--adm/--ce/--eu/--txt/--doc` (hub.html:11) | deux jeux de couleurs par fonds, valeurs **toutes différentes** : `--src-jud:#5c3317` contre `--jud:#2f5d8a` ; `--src-cedh:#6b3d8a` contre `--eu:#6d3e8c` ; `--src-ce:#1a4e4e` contre `--ce:#1f6f4a` | le jeu du hub, qui couvre 6 familles (dont `--txt` et `--doc`) contre 5 ; mais les deux nomenclatures désignent des découpages différents (`--src-*` = backend interrogé, `--jud/--adm/…` = famille juridictionnelle) — voir §5, ce sont deux axes, pas deux versions |
| `--topbar-h` | posé par JS dans topbar.js:186-188 **et** dans ssr.py:722-732 (même code en double), consommé par components.css:157, ssr.py:482, tutoriel-piste.html:21, mentions-legales.html:21, confidentialite.html:21 | une seule mesure, dans `jl.js` |

Typographie : `--text-xs:.72rem` · `--text-sm:.78rem` · `--text-base:.88rem` · `--text-md:.95rem` · `--text-lg:1.05rem` · `--text-xl:1.25rem` · `--text-2xl:1.7rem` · `--text-3xl:2.2rem` (tokens.css:54-61). **Aucun** de ces jetons n'est utilisé par hub.html ni par les maquettes, qui écrivent des pixels absolus non alignés sur l'échelle : `9.5px`, `10px`, `10.5px`, `11px`, `11.5px`, `12px`, `12.5px`, `13px`, `13.5px`, `14px`, `14.5px`, `15px`, `15.5px`, `16px`, `18px`, `19px`, `20px`, `22px`, `26px`, `30px`, `36px`. Douze pas de taille sous 16 px, là où l'échelle en prévoit cinq.
Espacements `--space-1..10` (tokens.css:75-84) : utilisés **uniquement** par components.css. Zéro usage dans les pages.
Rayons `--radius-sm:2px` / `--radius:3px` / `--radius-md:4px` / `--radius-lg:6px` / `--radius-pill:999px` (tokens.css:87-91) : utilisés uniquement par components.css. Les pages écrivent `2px`, `3px`, `4px`, `5px`, `6px`, `8px`, `9px`, `10px`, `11px`, `12px`, `14px`, `20px`, `50%`.
Ombres `--shadow-sm/--shadow/--shadow-md/--shadow-lg` (tokens.css:94-97) : utilisées uniquement par components.css:66. Les pages écrivent `0 6px 20px rgba(0,0,0,.12)` (search.html:186, components.css:171, annuaire.css:144), `0 8px 24px rgba(0,0,0,.12)` (carte-748.html:52), `0 8px 24px rgba(0,0,0,.18)` (hub.html:205, carte-748.html:96), `0 2px 12px rgba(26,78,78,.08)` (index.html:301), `2px 0 12px rgba(0,0,0,.08)` (hub.html:93), `-4px 0 24px rgba(0,0,0,.08)` (topbar.js:126, index.html:147), `0 8px 32px rgba(0,0,0,.3)` (search.html:875), `0 20px 60px rgba(0,0,0,.4)` (annuaire.css:153).
Transitions `--t-fast:.12s` / `--t:.2s` / `--t-slow:.25s` (tokens.css:100-102) : uniquement components.css. Les pages écrivent `.12s`, `.15s`, `.18s`, `.2s`, `.22s`, `.25s`, `.28s`, `.6s`, `.8s`.

---

## 4. HELPERS JS RÉPÉTÉS

| Helper | Occurrences (fichier:ligne) | Écarts entre copies |
|---|---|---|
| `esc` / `escapeHtml` / `escapeHTML` | hub.html:335 · carte-748.html:255 · histo-02.html:274 · histo-05.html:275 environ · search.html:1226-1230 (`escapeHtml`) · annuaire.html:6653 (`escapeHTML`) | les quatre du prototype échappent `& < > "` ; search.html et annuaire.html échappent en plus `'` en `&#39;`. **Le prototype n'échappe pas l'apostrophe** |
| `fmtDate` | hub.html:337 · carte-748.html:258 · histo-02.html:277 · search.html:1432-1451 · annuaire.html:6432-6436 · ssr.py:1002-1016 (`_format_fr_date`) | hub.html:337 rend `1 janvier 2020` ; carte-748.html:258 et histo-02.html:277 rendent `1er janvier 2020` (test `+m[3] === 1 ? '1er' : +m[3]`) ; search.html:1432 accepte en plus `YYYYMMDD` et `YYYY-MM-DDTHH:mm:ss` et a un mode `{short:true}` ; annuaire.html:6432 délègue à `toLocaleDateString('fr-FR')` ; ssr.py:1002 est la version Python. **Cinq implémentations, deux conventions du 1er du mois** |
| `fmtCourt` | carte-748.html:259 · histo-02.html:278 · histo-05.html:279 environ | identiques ; absent de hub.html, qui n'a pas de mois abrégés |
| `formatLawDate` | search.html:1867-1873 | sixième formateur de date, mois abrégés, doublon exact de `fmtCourt` |
| `nb` | hub.html:338 (`Number(n).toLocaleString('fr-FR')`) · histo-02.html:317 (`nb(n, un, plus)` — **même nom, signature et rôle totalement différents** : accord singulier/pluriel d'un substantif) | collision de nom à trancher avant la fusion |
| `fmtN` | hub.html:593 | abrège en `M` / `k` ; unique |
| `parseFr` (date jj/mm/aaaa) | carte-748.html:507-508 · histo-02.html:501-502 · histo-05.html:513-514 | trois copies mot pour mot |
| `parseDateLoose` | hub.html:706-714 | accepte `aaaa`, `mm/aaaa`, `jj/mm/aaaa`, `aaaa-mm-jj` ; superset de `parseFr`, jamais réutilisé par les maquettes |
| `frDate` (ISO → jj/mm/aaaa) | hub.html:705 | unique |
| `jaccard` + `words` | hub.html:1145-1146 · carte-748.html:294-295 · histo-02.html:319-320 · histo-05.html:321-322 environ | quatre copies mot pour mot |
| `diffWords` | hub.html:1147-1155 · histo-02.html:323-331 · histo-05.html:325-333 environ | trois copies ; histo-02.html:322 le dit : « copié de hub.html (showArticle) » |
| copie presse-papier | search.html:1733-1742 (`.action-copy-link`) · search.html:1996-2004 (**recopié dans `popSheet()`**) · hub.html:1140 (`#copyRef`) · decision-03b.html:229-233 (`[data-copy]`) · decision-01.html:229-233 (identique) | quatre écritures ; seules decision-03b/01 ont un repli `getSelection().selectAllChildren` quand `navigator.clipboard` manque |
| `bindCs` (dropdown) | search.html:999-1026 · annuaire.html:6528-6551 · stats.html:295-333 · inedits.html:246-275 environ | voir §2.13 |
| bascule de thème | topbar.js:222-241 · index.html:779-795 · search.html:891-904 · annuaire.html:6420-6427 · ressources.html:446-461 · inedits.html:354-361 environ · mentions-legales.html:100-105 · confidentialite.html:139-144 · tutoriel-piste.html:249-264 · ssr.py:703-721 · hub.html:653-658 · carte-748.html:276-278 · histo-02.html:295-297 · decision-03b.html:225-227 · decision-01.html:225-227 | **quinze copies**. Trois comportements distincts : bascule binaire clair/sombre sur clé `jl-theme` (topbar.js, index, search, annuaire, ressources, inedits, ssr) ; cycle à trois états clair → sombre → système sur `jl-theme` (mentions-legales:102-104, confidentialite:141-143, tutoriel-piste:255-262) ; cycle à trois états sur clé **`hub-theme`** (hub.html:654, carte-748.html:276 dans l'ordre `dark→system→light`, decision-03b.html:226 dans l'ordre `dark→system→light`). **Deux clés de localStorage pour la même préférence** |
| mesure `--topbar-h` | topbar.js:184-190 · ssr.py:722-732 | deux copies |
| anti-scrape `.mail-r` | index.html:810-814 · tutoriel-piste.html:292-296 · mentions-legales.html:109-113 · confidentialite.html:148-152 · search.html:2080-2084 | cinq copies mot pour mot |
| `legifrance(id, nature)` | carte-748.html:284-288 · histo-02.html:303-307 · histo-05.html:305-309 environ | trois copies ; côté prod, l'équivalent est `officialSourceFromId()` search.html:2092-2128 et `_official_source_from_pattern()` ssr.py:327-369 — search.html:2089 dit lui-même « Doit rester en sync avec ssr.py » |
| `lifeAt(t, at)` | carte-748.html:289-293 · histo-02.html:308-313 | **divergentes** : histo-02.html:311 ajoute un cas `MODIFIE` → `{k:'q', label:'réécrit le …'}` que carte-748.html n'a pas |
| `pill(st)` | carte-748.html:317 · histo-02.html:315 | identiques |
| `clean` / `minus` / `titreArr` | carte-748.html:319-321 · histo-02.html:314, histo-02.html:316, histo-02.html:318 | `minus` **diverge** : carte-748.html:321 fait `Arrêté → arrêté` ; histo-02.html:314 fait `Arrêté → l'arrêté` et `Décret → le décret` |
| `linkArts` / `CODE_SIGLE` | carte-748.html:298, carte-748.html:309-316 · histo-05.html:317-324 | deux copies ; carte-748 a en plus `linkArtsLEGI` (carte-748.html:300-308) que histo-05 n'a pas |
| `ICO` + `ico(k)` | hub.html:355-366 (13 icônes) · carte-748.html:260-263 (7 icônes) · histo-02.html:279-282 (7) · histo-05.html (7) | le sous-ensemble des maquettes est exactement `menu, scale, book, chat, hall, people, check, plug` |
| `FORMATION` / `FORMATION_LABELS` | hub.html:571 · search.html:2191-2204 | hub abrège (`'ch. soc.'`, `'1ʳᵉ civ.'`), search développe (`'Chambre sociale'`, `'1re chambre civile'`) ; search a en plus `ORDONNANCE_PREMIER_PRESIDENT`, `HFCOMOLD`, `OPIN_AG` |
| `SRC` / `SOURCE_NAMES` / `SOURCE_LABELS` | hub.html:572 · search.html:2211-2219 · carte-748.html:464 · ssr.py:391-398 | **quatre tables pour les mêmes clés**, avec quatre libellés par clé. Pour `dila` : `'judiciaire (DILA)'` (hub.html:572) · `'DILA'` (search.html:2212) · `'Judilibre · DILA'` (carte-748.html:464) · `'Justice judiciaire'` (ssr.py:392) |
| `FAM(r)` / `FAMLABEL` | hub.html:573-574 · carte-748.html:465 | hub a 6 familles (`jud adm ce eu doc txt`), carte-748 en a 3 (`jud adm eu`) et les écrit en minuscules (`'judiciaire'`) contre majuscule initiale chez hub (`'Judiciaire'`) |
| `clipExtract` | hub.html:342-353 | unique ; l'équivalent prod est `highlightExtract` search.html:1415-1431, qui coupe à 320 caractères au lieu d'une fenêtre centrée |
| `splitLegalBlock` | search.html:1151-1206 | équivalent Python : `_smart_paragraph_split` ssr.py:86-119 et `_clean_dila_text` ssr.py:55-83. Deux listes de marqueurs juridiques, **différentes** : search.html:1169-1174 liste `'PAR CES MOTIFS','CASSE ET ANNULE','LA COUR','REJETTE','RENVOIE','Faits et procédure','Examen des moyens','Examen du moyen','Énoncé du moyen','Enoncé du moyen','Réponse de la Cour','Portée et conséquences','EN FAIT','EN DROIT'` ; ssr.py:94-114 liste `Sur le … moyen`, `Mais sur le`, `Et sur le`, `Considérant que`, `Vu la/le/les`, `Attendu que`, `PAR CES MOTIFS`, `EN CONSÉQUENCE`, `DÉCIDE`, `ARTICLE n`, `Le moyen pris`, `La cour`, `Le tribunal`, `DÉCISION DE`, `R É P U B L I Q U E` |
| `highlightLawRefs` | search.html:1246-1414 | 169 lignes, 22 codes + 6 conventions ; sans équivalent dans le prototype, qui pose ses liens depuis les données LEGI (`linkArtsLEGI` carte-748.html:300) |
| `$` (sélecteur) | hub.html:334 · carte-748.html:254 · histo-02.html:273 · histo-05.html:274 environ | quatre copies mot pour mot |
| `MOIS` / `MOISC` | hub.html:336 · carte-748.html:256-257 · histo-02.html:275-276 · search.html:1444-1445 · search.html:1871 · ssr.py:1006-1007 | six copies du tableau des mois français |

---

## 5. CE QUI EST PROPRE AU SITE PROD ET ABSENT DU PROTOTYPE

### 5.1 `search.html` → `hub.html`, point par point

1. **Pagination par « Charger la suite » avec état par source et retry.** hub.html:1106-1116 recharge par offset et affiche « source : offset / total » (hub.html:1094). search.html va plus loin : relance automatique en arrière-plan des sources qui ont dépassé le délai, avec un second délai de 60 s (`retryTimedOutSources()` search.html:2535-2547, appelée search.html:2470), et affiche l'état de cette relance dans le bandeau (search.html:1509-1517). **Absent du hub** : le hub marque simplement `'ko:pas de réponse'` (hub.html:1036) et n'y revient jamais.
2. **Distinction refus déterministe / délai dépassé.** search.html:2496-2502 intercepte les codes 4xx et les stocke dans `lastSearchState.erreurs`, rendus tels quels (search.html:1521-1524), avec ce commentaire : « Avant, il passait pour “n'a pas répondu (12 s puis 60 s)” et déclenchait 5 nouvelles requêtes vouées au même refus » (search.html:2497-2499). Le hub ne fait pas ce tri : tout échec devient `'ko:'+e.message` (hub.html:1054).
3. **Refus de dire « aucun résultat » quand une source n'a pas répondu.** search.html:1537-1548, avec le motif écrit dans le code : « ⛔ Ne JAMAIS dire “aucun résultat” quand une source n'a pas répondu : c'est un faux négatif, et sur un site de droit ça fait conclure qu'un précédent n'existe pas » (search.html:1538-1540), plus un bouton `"Relancer"` (search.html:1547). Le hub affiche `'Rien pour cette requête dans les sources interrogées.'` (hub.html:1093) sans distinguer le cas.
4. **Entrelacement des résultats en mode Pertinence.** search.html:1467-1502 : les scores BM25 de fonds différents n'étant pas comparables, search.html prend le 1er de chaque source, puis le 2e, selon `ORDRE_SOURCES = ['dila','admin','ariane','legi','cedh','cjue','doctrine']` (search.html:1483), pour rendre l'ordre stable. Le hub trie simplement par rang de source (`ORDER`, hub.html:1050-1051) : tous les résultats DILA d'abord, puis tous les ArianeWeb.
5. **Détection des citations d'articles dans le texte d'une décision.** `highlightLawRefs()` search.html:1246-1414 : 22 codes avec alias (`CESEDA`, `CGCT`, `CGI`, `CRPA`, `CCH`, `CPI`, `CASF`, `CMF`, `CSS`, `CSP`, `CJA`, `CPC`, `CPP`, `C.cons`, `C.éduc`, `C.com`, `CT`, `CU`, `C.env`, `CR`, `CC`, `CP` — search.html:1250-1273), 6 conventions (`CEDH`, `TFUE`, `TUE`, `CDFUE`, `DDHC`, `CONST` — search.html:1275-1282), règlements UE, directives, lois, décrets, ordonnances (search.html:1366-1410). **Absent du hub** : le hub n'affiche le texte qu'en `<pre>` échappé (hub.html:1138).
6. **Panneau latéral d'article de loi, à la rédaction d'époque.** `openLawInSidebar()` search.html:1924-1944, avec cache localStorage 24 h et éviction LRU à 500 entrées (search.html:1780-1813), préchargement en lot des articles cités (`/api/law/batch`, search.html:1834-1838), et affichage de l'état (`law-etat-vigueur` / `law-etat-abroge` / `law-etat-modifie`, search.html:1891-1892). Le hub a une page article (`showArticle()`, hub.html:1229) mais **pas de panneau latéral** ni de cache, et ne précharge rien.
7. **Vue « toutes les versions » d'un article.** `showLawVersions()` search.html:2023-2043, libellé `"Voir toutes les versions"` (search.html:867). Le hub a la comparaison deux à deux (hub.html:1253-1255) mais pas la liste complète.
8. **Adaptation mobile en bottom sheet avec pile de navigation.** `openLawInSheet()` search.html:1954-1986 et `popSheet()` search.html:1988-2021, avec `window.sheetStack` et ré-attachement des écouteurs après restauration (search.html:1993-2019). CSS : search.html:521-556. **Absent du hub**, dont la seule adaptation mobile est un rail en position fixe (hub.html:93).
9. **Feuille d'impression.** search.html:573-683, 110 lignes, avec la remarque décisive : « Une page A4 fait ~794 px : le point de rupture 860 px s'active donc À L'IMPRESSION, et c'est la mise en page MOBILE qui partait sur le papier » (search.html:585-588). Plus le renommage du PDF par le titre de la décision ouverte (search.html:2660-2671). **Le hub n'a aucun `@media print`**, ni aucune maquette sauf decision-03b.html:109 et decision-01.html:109 (une ligne chacune).
10. **URL qui suit la recherche.** `syncUrl()` search.html:2361-2373 pousse `q`, `juridiction`, `lieu`, `formation`, `date_min`, `date_max`, `sort` dans l'adresse par `history.replaceState`. Relecture au chargement : `handleQueryParam()` search.html:2624-2652 et `handleDeepLink()` search.html:2611-2619 (`?id=…&source=…`). Le hub route par `location.hash` (hub.html:607-624) : ses adresses ne sont pas des URL de page mais des ancres, donc non indexables et non partageables hors JS.
11. **Filtre « Lieu géographique ».** `INSTANCES` search.html:958-996 : 41 tribunaux administratifs, 9 cours administratives d'appel, 36 cours d'appel, avec codes (`TA59` → Lille, `CAA59` → Douai). Affichage conditionnel search.html:2580-2594, libellés `"Tous TA"` / `"Toutes CAA"` / `"Toutes CA"` (search.html:2588). **Rien d'équivalent dans le hub**, dont le filtre le plus fin est le fonds (`FAMILLES`, hub.html:584-589).
12. **Menu de juridiction à deux niveaux avec groupes cliquables.** search.html:729-767 : `.cs-group` sélectionnable (« Administratif » sélectionne les trois sous-entrées) avec indice au survol (`.cs-group .hint`, search.html:213-218), plus la synchronisation entre le sélecteur grossier de la barre et le fin du panneau (`PARENT_OF` search.html:1053-1059, `FINE_LABELS_WHEN_COARSE` search.html:1066-1071, écouteurs search.html:1082-1101). Le hub a des cases à cocher par fonds (hub.html:682) sans hiérarchie de menu.
13. **Pastilles de termes ajoutés par le thésaurus, retirables une à une.** `fetchExpansion()` search.html:2266-2309 : chaque synonyme devient une `.exp-pill` avec un bouton `×` qui la barre (`.exp-pill.removed{opacity:.4;text-decoration:line-through}`, search.html:160), et le survol dit d'où vient le terme (`"Ajouté pour le terme « … »"`, search.html:2289). Le hub affiche les mêmes termes (`showExpansion()` hub.html:957-974) mais en pastilles **non retirables** : le seul geste offert est `"chercher les mots exacts"` (hub.html:968), tout ou rien.
14. **Téléchargement du texte en `.txt`.** search.html:1744-1756, `Blob` + `<a download>` avec nom de fichier assaini. **Absent du hub.**
15. **Formulaire de signalement contextuel.** `openFeedback()` search.html:2056-2066 : pré-remplit un ticket GitHub avec l'élément concerné et l'adresse de la page ; câblé depuis trois endroits — panneau décision (search.html:1757-1768), panneau article (search.html:2070-2076), version mobile (search.html:1972). **Absent du hub**, qui n'a aucun bouton de signalement.
16. **Bouton « Voir sur la source officielle » raisonné.** `officialSourceFromId()` search.html:2092-2128 : sept familles d'identifiants, et surtout le refus explicite d'un bouton pour `DCE_/DCAA_/DTA_/ORTA_` avec ce motif — « la majorité des TAs ne sont JAMAIS sur Légifrance (uniquement les Lebon, ~5 %). On retourne null → pas de bouton mensonger » (search.html:2108-2109) — remplacé par un encadré honnête (search.html:1701-1709). Le hub ne propose qu'un lien vers l'ancien site : `"Page actuelle du site"` (hub.html:1139).
17. **Découpage en paragraphes d'un texte concaténé.** `splitLegalBlock()` search.html:1151-1206, appelé quand le texte n'a aucun saut de ligne (search.html:1680-1686). Le hub affiche `<pre>${esc(txt)}</pre>` brut (hub.html:1138).
18. **Garde-fou contre le double envoi.** search.html:2341-2352 (`searchInFlight`), avec le motif daté : « Double-clic sur “Chercher” (ou Entrée répétée) : la même recherche partait deux fois et doublait les cartes (8 septembre 2026) » (search.html:2344-2345). Plus l'acceptation de toutes les formes de la touche Entrée (`_estEntree` search.html:2574-2576). Le hub n'a ni l'un ni l'autre (hub.html:782).
19. **Compteur de filtres actifs sur le bouton.** `updateAdvCount()` search.html:2354-2359 et `.adv-count` search.html:142-143. Le hub a l'équivalent (`advCount()` hub.html:666, `.advCount` hub.html:220) — **présent des deux côtés**, seule différence : search compte 5 champs, le hub compte aussi le thésaurus coupé (hub.html:666).
20. **Distinction visuelle des champs vides.** `.field-empty` search.html:294, et la normalisation `isEmpty` qui traite `"undefined"` et `"null"` comme vides (search.html:1561). Le hub omet simplement le champ (hub.html:1101).

À l'inverse, **le hub a ce que search.html n'a pas** : le flux « Nouveautés » à défilement infini (hub.html:888-950), les squelettes de chargement (hub.html:72-76), le vérificateur de citations (hub.html:1282-1288 et hub.html:1314-1375), la carte d'un article (hub.html:1166-1228), la frise de rédactions avec alerte de numéro recyclé (hub.html:1247), le curseur d'années à deux poignées (hub.html:148-155), les facettes calculées sur les résultats chargés (hub.html:1065-1078), l'état par source en cours de recherche (`.src-state`, hub.html:277-281).

### 5.2 `annuaire.html` → `hub.html`, point par point

1. **Rendu progressif d'un très grand tableau.** `PAGE_SIZE = 1000` (annuaire.html:6673), `appendPage()` annuaire.html:6699-6710, avec ce motif : « ça évite d'injecter 71 000 tr d'un coup (freeze de plusieurs secondes sur desktop, crash sur mobile) » (annuaire.html:6670-6671). Deux boutons : `"Afficher {n} de plus"` et `"all"` (annuaire.html:6694-6695). **Absent du hub**, dont l'annuaire est un simple écran d'attente (hub.html:861-865) avec ce message : `"l'annuaire n'est pas encore exposé par l'API du site."` (hub.html:865).
2. **Tri par colonne au clic, avec indicateur.** `renderHeader()` annuaire.html:6677-6683 (flèches `▲ ▼ ▲▼`), écouteur annuaire.html:6738-6744, CSS `table.data th.sorted .arr{opacity:1}` (annuaire.css:59). Version indépendante dans inedits.html (`sortBy()`, l. 302-325 environ). Le hub n'a **aucun tableau triable** : sa seule table est `table.tb` (hub.html:308-310), statique.
3. **Colonnes déclaratives.** `COLS` annuaire.html:6655-6666 : chaque colonne porte sa clé, son libellé, sa classe et sa fonction de rendu. Le hub écrit ses tableaux en gabarit littéral (hub.html:1306).
4. **Filtres combinés avec compteur.** Catégorie + texte libre + case `"Sans mail uniquement"` (annuaire.html:86), `currentRows()` annuaire.html:6559-6574 qui cherche jusque dans `JSON.stringify(r.contact)` (annuaire.html:6570), compteur `"{n} / {total} fiches"` (annuaire.html:6721), saisie temporisée à 150 ms (annuaire.html:6735). **Absent du hub.**
5. **Fusion de deux jeux de données hétérogènes en un seul modèle.** `loadAll()` annuaire.html:6438-6482 : trois fetch en parallèle (juridictions, PRADA, métadonnées) normalisés vers `{kind, category, category_label, nom, sub, mails, contact, id, source}`. **Absent du hub**, qui n'appelle aucune source annuaire.
6. **Tableau de complétude avec barres.** `renderCoverage()` annuaire.html:6492-6511 : quatre tuiles de comptage plus un tableau taux par catégorie, seuils à 30 % et 70 % (annuaire.html:6507) et couleurs `#c1440e` / `#b8932b` / `#1a4e4e` (annuaire.html:6508). **Absent du hub.** Le hub a un objet voisin — le contrôle de couverture nocturne (hub.html:795, hub.html:1305-1306) — mais en tableau figé, sans barres ni taux calculés.
7. **Métadonnées de fraîcheur en tête de page.** `renderMeta()` annuaire.html:6484-6490, libellé cité : `"Bulk DILA capturé le … · Annuaire CADA capturé le … · Dernière génération : …"` (annuaire.html:6489). **Absent du hub**, qui écrit ses dates en dur (hub.html:795 : `"Contrôle de la nuit contre Judilibre (8 sept., 18 h 43)"`).
8. **Anti-aspiration des adresses.** `fmtSignal()` annuaire.html:6597-6603 et `openSignalModal()` annuaire.html:6615-6651 : aucun `mailto:` dans le HTML, l'adresse est recomposée au clic par `'contact' + String.fromCharCode(64) + 'justicelibre.org'` (annuaire.html:6616). Le motif est écrit : « Un scraper naïf qui cherche mailto: dans le HTML/JS ne trouve rien » (annuaire.html:6596). Même dispositif dans inedits.html (l. 328 environ) et, sous une autre forme, le `.mail-r` d'index.html:810. **Absent du hub.**
9. **Modale de signalement avec fondement juridique.** annuaire.html:6632-6643 ; dans inedits.html, la même modale porte en plus le droit d'opposition RGPD et les avis CADA cités (bloc l. 338-341 environ : `"L. 311-6 du CRPA"`, `"avis 2007-3348, 2010-2445, 2019-4471"`, `"RGPD article 21"`). **Absent du hub.**
10. **Téléchargements bruts.** `.download-row` annuaire.html:68-74 : quatre fichiers (CSV juridictions, CSV PRADA, JSON juridictions, JSON PRADA) avec la mention `"Réutilisable, Licence Ouverte 2.0 (Etalab)"` (annuaire.html:73). **Absent du hub.**
11. **Grille de sous-pages par catégorie.** annuaire.html:6375-6398, 20 cartes `.cat-card` avec compteurs. Mécanisme jumeau dans inedits.html:103-109. Ces sous-pages sont déclarées au sitemap (ssr.py:1252-1277). **Absent du hub**, qui n'a aucune notion de sous-page.
12. **Rendu en dur pour l'indexation.** Le bloc `<!-- STATIC_ROWS_START -->` (annuaire.html:101) à `<!-- STATIC_ROWS_END -->` (annuaire.html:6365) contient 6263 lignes injectées au build, remplacées par le JS au chargement interactif (commentaire annuaire.html:101). Même intention dans annuaire.css:80-82 : « le HTML est là pour Google, mais display:none évite le coût de layout ». **Le hub ne produit aucun HTML indexable** : tout son contenu est écrit par `innerHTML` après exécution.
13. **Bouton flottant de signalement.** `.fab-signal` inedits.html:63-66, disque teal fixe en bas à droite. **Absent du hub** (dont le `.proto` hub.html:311 occupe la même position, mais comme étiquette non cliquable).
14. **Fil d'ariane collant.** `.page-subbar` annuaire.html:30-32, inedits.html:73-75, stats.html:93-95, tutoriel-piste.html:123-125, mentions-legales.html:60-62, confidentialite.html:62-64, ssr.py:955-957 et ssr.py:1145-1147 ; CSS unifié dans components.css:155-162 et recopié dans ssr.py:479-489, tutoriel-piste.html:19-26, mentions-legales.html:19-26, confidentialite.html:19-26. **Absent du hub et de toutes les maquettes** : leur seul retour est un `.back` texte (hub.html:288, carte-748.html:67).

### 5.3 Le SSR, absent des deux

`ssr.py` produit les pages `/decision/{source}/{id}` (ssr.py:795-972) et `/loi/{code}/{num}` (ssr.py:1031-1160) que ni le hub ni search.html ne savent rendre côté serveur : `<title>` par document (ssr.py:841), `canonical` %-encodé (ssr.py:775-790, avec l'explication du bug de 2026 sur 114 000 pages), OpenGraph et Twitter (ssr.py:938-946), JSON-LD `LegalCase` (ssr.py:876-891) et `Legislation` (ssr.py:1074-1093), et les sitemaps (ssr.py:1284-1574). Seule `decision-03b.html:6-19` et `decision-01.html:6-19` reproduisent cette couche dans le prototype, en dur.
Deux choses que le SSR sait dire et que le prototype ne sait pas : le bandeau de langue quand la version française n'existe pas (`_lang_warning()` ssr.py:264-290, avec 34 langues nommées ssr.py:251-261) et le statut réel d'un article de loi (`_subline_statut()` ssr.py:975-999, avec l'aveu du bug daté : « 26 abrogés testés, 26 affichés en vigueur », ssr.py:1044-1049).

---

## 6. `jl-mot-accentue` — LA SIGNATURE TYPOGRAPHIQUE

Le mot mis en relief dans un titre, en `<em>`, teal, dans l'italique de la serif. C'est la marque visuelle du site. **Elle doit survivre au normaliseur** : aucune des six pages validées du prototype ne la porte (§6.3).

### 6.1 Toutes les occurrences en prod

**Règles CSS.** Toutes appliquent `color:var(--teal)` ; elles se séparent sur `font-style`.

| Règle | Fichier:ligne | `font-style` | `color` | Police et graisse héritées du titre |
|---|---|---|---|---|
| `.hero-text h1 em` | index.html:199 | **`normal`** | `var(--teal)` | `var(--display)` = `"DM Serif Display", Georgia, serif` (index.html:193), `clamp(2.4rem,5.5vw,4rem)` (index.html:194), `text-transform:uppercase` (index.html:197) |
| `.section h2 em` | index.html:256 | `italic` | `var(--teal)` | `var(--display)`, `2rem` (index.html:253) |
| `.hero h1 em` | annuaire.css:12 | `italic` | `var(--teal)` | `var(--display)`, `clamp(2.2rem,5vw,3.6rem)`, `font-weight:400` (annuaire.css:11) |
| `.hero h1 em` | ressources.html:36 | `italic` | `var(--teal)` | `var(--display)`, `clamp(2.2rem,5vw,3.6rem)`, `font-weight:400` (ressources.html:35) |
| `.hero h1 em` | inedits.html:24 | *(hérité `italic` d'annuaire.css:12)* | **`#7a1e2f`** (bordeaux, en dur) | idem annuaire.css:11 |
| `h1 em` | stats.html:27 | `italic` | `var(--teal)` | `var(--display)`, `2.4rem` (stats.html:26) |
| `h2 em` | stats.html:74 | `italic` | `var(--teal)` | `var(--display)`, `1.4rem` (stats.html:71) |
| `h1 em` | tutoriel-piste.html:74 | `italic` | `var(--teal)` | `var(--display)`, `2.2rem` (tutoriel-piste.html:73) |
| `h1 em` | ssr.py:495 | `italic` | `var(--teal)` | `var(--display)`, `2.2rem`, `font-weight:400` (ssr.py:493-494) |
| `.jl-section__title em` | components.css:145 | `italic` | `var(--teal)` | `var(--font-serif)`, `var(--text-2xl)` (components.css:138-139) |

Aucune règle ne touche à `font-weight` : le `<em>` reste au poids du titre (`400` partout où il est déclaré). Aucune ne touche à la police : c'est l'italique **de la DM Serif Display**, chargée en `ital@0;1` par index.html:28, ressources.html:18, annuaire.html:19, stats.html:16, inedits.html:17, tutoriel-piste.html:16, ssr.py:427. Les pages qui chargent la police **sans** l'axe italique cassent la signature : `mentions-legales.html:16` et `confidentialite.html:16` demandent bien `DM+Serif+Display:ital@0;1`, donc l'italique est disponible — mais elles n'ont aucun `<em>` dans leurs titres.

**Occurrences dans le contenu, citées telles quelles.**

| Titre | Fichier:ligne |
|---|---|
| `L'accès libre et gratuit à toute la jurisprudence <em>française.</em>` | index.html:441 |
| `Installation en <em>trois étapes</em>` | index.html:465 |
| `30 outils, <em>toute la matière</em> juridique française` | index.html:480 |
| `Pourquoi c'est <em>gratuit</em> et <em>légal</em>` | index.html:632 — **deux `<em>` dans un même titre** |
| `La France, <em>seul pays européen</em> à bloquer l'accès à sa jurisprudence judiciaire` | index.html:650 |
| `Annuaire des <em>juridictions</em> et PRADA.` | annuaire.html:36 |
| `Ressources et sources <em>de données</em>.` | ressources.html:87 |
| `Adresses <em>inédites</em> - PDF gouvernementaux.` | inedits.html:78 |
| `Statistiques <em>d'utilisation</em>` | stats.html:98 |
| `Requêtes <em>dans le temps</em>` | stats.html:120 |
| `Outils <em>les plus utilisés</em>` | stats.html:137 |
| `Accéder à la jurisprudence <em>judiciaire</em> via PISTE` | tutoriel-piste.html:131 |
| `<h1>Article <em>{num}</em></h1>` (page de loi SSR) | ssr.py:1150 |
| `{main_id_html} <em>· {date}</em>` (page de décision SSR) | ssr.py:831 |

Soit **14 titres** en prod. Le mot accentué est toujours **un fragment nominal court** (1 à 4 mots), jamais le titre entier, et jamais le premier mot sauf dans `Annuaire des <em>juridictions</em>` (annuaire.html:36) où il l'est en deuxième position.

### 6.2 Les deux variantes réelles

1. **Variante hero (accueil)** : `font-style:normal` (index.html:199). Le hero d'index.html est en capitales (`text-transform:uppercase`, index.html:197) : l'italique y serait illisible, donc seule la couleur teal distingue le mot. **C'est la seule occurrence non italique du site.**
2. **Variante section et hero de page interne** : `font-style:italic` partout ailleurs (9 règles sur 10). Le hero d'annuaire.html:36, de ressources.html:87 et d'inedits.html:78 est en bas de casse et porte bien l'italique, malgré son nom de classe `.hero` : ce n'est donc pas « hero = normal, section = italique », c'est **« capitales = normal, bas de casse = italique »**.
3. Variante de couleur **hors charte** : inedits.html:24 remplace `var(--teal)` par `#7a1e2f` en dur, assorti au bouton `.btn-inedits` (annuaire.css:119). C'est le seul endroit du site où le mot accentué n'est pas teal.

### 6.3 Où elle est ABSENTE dans le prototype validé, alors qu'un titre s'y prêtait

**Aucune** des six pages validées ne contient un seul `<em>` de titre. Les seuls `<em>` du prototype sont des surlignages de résultats de recherche : `.card2 .res em` (hub.html:69) et `.item .sum em` (hub.html:263), tous deux `font-style:normal` avec fond `var(--teal-xl)` — **un rôle opposé** (marquer le terme cherché dans un extrait, pas accentuer un titre).

Cause structurelle : dans le prototype le titre de page n'est pas un `<h1>` mais `<p class="hero">` (hub.html:96, carte-748.html:40, histo-02.html:41), sans règle `em`. Et dans les deux maquettes décision, l'accent est porté par `<span class="num">` — mono, teal, 22px (decision-03b.html:52, decision-01.html:52) — au lieu de `<em>` serif italique : c'est une **troisième mise en relief**, à réconcilier.

Titres concernés, cités tels qu'ils sont dans le code :

| Fichier:ligne | Titre, tel quel | Mot qui appelait l'accent |
|---|---|---|
| hub.html:801 et hub.html:808 | `Chercher une décision` | « décision » |
| hub.html:815 | `Textes` | *(un mot : pas d'accent possible)* |
| hub.html:843 | `Travaux préparatoires` | « préparatoires » |
| hub.html:852 | `Avis &amp; doctrine` | « doctrine » |
| hub.html:862 | `Annuaire` | *(un mot)* — à noter : la page prod correspondante écrit `Annuaire des <em>juridictions</em> et PRADA.` (annuaire.html:36) |
| hub.html:1283 | `Vérifier mes citations` | « citations » |
| hub.html:1291 | `Un article, son histoire` | « son histoire » |
| hub.html:1298 | `Suivre une recherche` | « recherche » |
| hub.html:1304 | `Ce que nous n'avons pas` | « n'avons pas » |
| hub.html:818 | `Codes` (`.feed-h`) | *(un mot)* |
| hub.html:821 | `Textes hors code` (`.feed-h`) | « hors code » |
| hub.html:810 | `Nouveautés` (`.feed-h`) | *(un mot)* |
| carte-748.html:477 et hub.html:1203 | `Art. ${num} · ${cname}` | le numéro d'article — c'est exactement ce que ssr.py:1150 met en `<em>` (`<h1>Article <em>{num}</em></h1>`) |
| carte-748.html:469 | `Jurisprudence qui le cite` (`.juris h2`, serif 20px) | « qui le cite » |
| histo-02.html:470 et histo-05.html:482 | `Art. ${num} · ${cname} <span class="jl-hkicker">historique</span>` | idem, plus « historique » rendu en gélule mono au lieu d'`<em>` |
| decision-03b.html:156 et decision-01.html:148 | `10 septembre 2026, pourvoi <span class="num">n° 23-20.368</span>` | le numéro de pourvoi, rendu en **mono teal** (`h1 .num`, decision-03b.html:52) et non en serif italique teal |

Trois autres titres serif du prototype sans accent : `carte-748.html:243` `Cadre normatif actuel`, `carte-748.html:495` `Texte en vigueur`, `carte-748.html:497` `Références croisées` — mais ceux-là sont des `.col h2` à 10px en majuscules (carte-748.html:103) : ce sont des sur-titres, la signature n'y a pas sa place.

### 6.4 Ce qui doit gagner

`.jl-section__title em{color:var(--teal);font-style:italic}` (components.css:145) : c'est la seule écriture tokenisée, et la règle est exactement celle des 9 occurrences italiques. **Mais `.jl-section__title` n'est utilisé par aucune page** (vérifié : `grep -rn 'jl-section' --include=*.html web/` ne retourne rien) — le composant existe et n'a jamais été branché.
La variante `font-style:normal` d'index.html:199 doit devenir un modificateur explicite lié aux capitales, pas une exception silencieuse. Et `#7a1e2f` d'inedits.html:24 doit devenir un jeton (`--accent-inedits`) ou disparaître.

**Ressemble mais n'est pas la même chose** : `.card2 .res em` / `.item .sum em` (hub.html:69, hub.html:263) et `.result-card .extract em` (search.html:300) sont des **surlignages de terme cherché** — `font-style:normal` avec fond (`var(--teal-xl)` dans le hub, `rgba(184,147,43,.25)` dans search.html). Le normaliseur ne doit pas leur appliquer la règle de titre : ils redeviendraient italiques et teal, et on ne distinguerait plus « voici le mot que vous cherchiez » de « voici le mot qui porte le sens du titre ». Même remarque pour `.sb-help em` (search.html:228, note en italique gris) et `.hero-text h1 em` dont l'italique est justement retiré.

---

## 7. LA PAGE ANNUAIRE, PAGE DE RÉFÉRENCE CONSERVÉE

Décision de la propriétaire : `annuaire.html` reste en l'état. Elle est donc inventoriée pour elle-même, et non comme un candidat à la réécriture. La copie locale `web/annuaire.html` est **identique à la prod** (diff vide, voir manifeste).

### 7.1 Anatomie complète

| Élément | Markup | CSS | Notes |
|---|---|---|---|
| résolveur de thème anti-flash | annuaire.html:6-9 | — | inline avant les `<link>`, clé `jl-theme` |
| header | annuaire.html:29 (`<div data-topbar-mount>`) + annuaire.html:24 (`topbar.js?v=5`) | topbar.js:56-160 | composant partagé |
| fil d'ariane collant | annuaire.html:30-32 | components.css:155-162 | `"Accueil › Annuaire"` |
| hero | annuaire.html:35-49 | annuaire.css:10-19 | `<h1>` avec la signature `<em>` (§6), `<p>`, `<p class="sources">` |
| bouton « Inédits » | annuaire.html:43-47 | annuaire.css:119-124 | bordeaux `#7a1e2f`, badge `"Nouveau"`, flèche animée ; compteur injecté au build entre `<!-- INEDITS_COUNT_START -->` et `<!-- INEDITS_COUNT_END -->` (annuaire.html:45) |
| date de fraîcheur | annuaire.html:40 (`<span id="meta-date">`) | — | valeur d'attente `"Chargement des métadonnées…"`, remplie par `renderMeta()` annuaire.html:6484-6490 |
| tuiles de comptage | annuaire.html:56 (`<div id="coverage-tiles" class="stats">`) | annuaire.css:27-31 | 4 tuiles, `renderCoverage()` annuaire.html:6496-6502 |
| tableau de complétude | annuaire.html:57 | annuaire.css:33-42 | barre `--w` en pourcentage, seuils 30 / 70 (annuaire.html:6507) |
| encadré d'avertissement | annuaire.html:58-61 | annuaire.css:91-94 (`.infobox.warn`) | contenu éditorial sur les adresses non publiées |
| ligne de téléchargements | annuaire.html:68-74 | annuaire.css:84-89 | 4 fichiers + mention de licence |
| **barre de recherche + filtres** | annuaire.html:76-88 | annuaire.css:44-49 | voir §7.3 |
| menu de catégories | annuaire.html:77-84 | annuaire.css:138-148 | rempli à chaud par `populateCategoryFilter()` annuaire.html:6513-6525 |
| case « Sans mail uniquement » | annuaire.html:86 | annuaire.css:127-128 (`.chk-toggle`) | `accent-color:var(--teal)` |
| compteur de résultats | annuaire.html:87 (`<span class="count" id="count">`) | annuaire.css:49 | `"{n} / {total} fiches"` (annuaire.html:6721) |
| tableau | annuaire.html:90-99 (en-tête) + 101-6365 (corps) | annuaire.css:51-78 | en-têtes collants, tri au clic |
| grille de sous-pages | annuaire.html:6375-6398 | annuaire.css:97-103 | 20 cartes entre `<!-- CATEGORY_CARDS_START -->` et `<!-- CATEGORY_CARDS_END -->` |
| méthodologie | annuaire.html:6401-6408 | annuaire.css:91-93 (`.infobox`) | trois paragraphes |
| pied | annuaire.html:6412-6414 | annuaire.css:112-114 | |
| modale de signalement | construite en JS, annuaire.html:6630-6643 | annuaire.css:151-166 | |

### 7.2 Structure exacte d'une ligne de résultat

Cinq cellules, dans cet ordre. Rendu JS : `COLS` annuaire.html:6655-6666 et `rowHTML()` annuaire.html:6685-6687.

1. **`td.type`** — `<span class="badge">{catégorie}</span>` (annuaire.css:62), plus un second badge de source : `manuel` sur fond `#fef9e8` texte `#b8932b`, `title="Source non officielle, documentée"` (annuaire.html:6658), ou `api` sur fond `#e6f0f5` texte `#1e5568`, `title="Source : api-lannuaire.service-public.fr"` (annuaire.html:6659). Le badge PRADA prend une couleur propre : `.badge.prada{background:#fef9e8;color:var(--gold)}` (annuaire.css:63). Exemples relevés : annuaire.html:792 (manuel), annuaire.html:793 (api), annuaire.html:4118 (prada).
2. **`td.nom`** — nom, plus `<div class="sub">` pour la personne physique désignée dans le cas PRADA (annuaire.css:65 ; exemple annuaire.html:4118 : `<div class="sub">Martine GAECKLER</div>`).
3. **`td.mail`** — mono, `word-break:break-all` (annuaire.css:66) ; un ou plusieurs `mailto:` séparés par `<br>` (`fmtMails()` annuaire.html:6588-6591) ; état vide : `<span class="no-mail">non publié</span>` (annuaire.html:6589), en `#c1440e` italique (annuaire.css:69). **730 occurrences** de `no-mail` dans le HTML statique.
4. **`td.contact`** — composé par `fmtContact()` annuaire.html:6576-6586, dans cet ordre : `.tel` (mono), lien `"site"`, hiérarchie en 0.72rem muted, adresse postale (les `" | "` deviennent des `<br>`), extra, puis lien de provenance `"source : {label}"` en `#b8932b` (annuaire.html:6584). `max-width:280px` (annuaire.css:70).
5. **`td.action`** — `<button class="signal">Signaler</button>` (annuaire.html:6602), **uniquement si la fiche a au moins un mail** (annuaire.html:6598). Bouton fantôme : bordure `--line`, texte muted, hover teal (annuaire.css:75-78).

**Divergence statique / interactif à connaître.** Dans les 6263 lignes injectées au build, `td.contact` et `td.action` sont **systématiquement vides** : `grep -c '<td class="contact"></td>'` = 6263 et `grep -c '<td class="action"></td>'` = 6263. Le HTML servi à Google n'a donc ni téléphone, ni adresse postale, ni bouton de signalement ; ces trois choses n'apparaissent qu'après le `renderTable()` du JS (annuaire.html:6712-6731), qui vide le `<tbody>` (annuaire.html:6725) et le reconstruit depuis les JSON. **Il n'existe aucune page de fiche individuelle par tribunal** : l'unité d'affichage est la ligne de tableau, jamais une page dédiée, et aucune URL ne désigne une juridiction.

### 7.3 Sa barre de recherche comparée à `search.html` et `hub.html`

| | annuaire.html | search.html | hub.html |
|---|---|---|---|
| conteneur | `.filters` — flex, fond `--white`, bordure `--line`, `border-radius:6px`, `padding:.8rem 1rem` (annuaire.css:44) | `.sb-primary` — grille `1fr 200px 190px auto auto` (search.html:44) | `.sbar` — bloc soudé, `border:1.5px solid var(--teal)` (hub.html:98) |
| champ texte | `.filters input[type=text]` — fond **`var(--cream)`**, bordure `--line`, `border-radius:4px`, `.9rem`, `flex:1;min-width:220px` (annuaire.css:45-46) | fond `var(--white)`, `border-radius:3px`, `.95rem`, `padding:.75rem 1rem` (search.html:60-66) | fond transparent, **aucune bordure**, `padding:12px 16px`, `font-size:16px` (hub.html:99) |
| placeholder, cité | `"Rechercher : nom, ville, mail, organisme, PRADA…"` (annuaire.html:85) | `"Mots-clés, n° de décision, ECLI…"` (search.html:698) | `"trouble anormal de voisinage · 04-10.362 · 380374 · 14852/18"` (hub.html:809) |
| bouton d'envoi | **aucun** — la recherche se déclenche à la frappe, temporisée à 150 ms (annuaire.html:6735) | `.submit` « Chercher » (search.html:721), plus Entrée (search.html:2575-2576) | `.go` « Chercher » (hub.html:684), soudé dans la barre |
| focus | **aucune règle de focus** | `:focus{outline:none;border-color:var(--teal)}` (search.html:67-68) | `outline:0` sur l'input (hub.html:99), la bordure teal est portée par `.sbar` en permanence |
| filtres | 1 menu + 1 case, toujours visibles (annuaire.html:76-88) | 1 menu grossier + 1 tri dans la barre, 6 champs dans un panneau repliable (search.html:725-822) | cases à cocher par fonds, chambre, frise d'années, presets, thésaurus, dans `.adv` (hub.html:685-703) |
| compteur | `"{n} / {total} fiches"` en permanence (annuaire.html:87) | `"{n}+ résultats · {k} sources"` (search.html:2555-2561) | `"{n} résultats chargés sur {m} existants"` (hub.html:1088) |
| état vide | `"Aucun résultat pour ces filtres."` (annuaire.html:6727) | trois états distincts selon la cause (search.html:1528-1551) | `"Rien pour cette requête dans les sources interrogées."` (hub.html:1093) |
| état de chargement | **aucun** — le tableau est déjà peuplé en HTML avant le JS | en-tête avec points sautants (search.html:2444) et `.loader-box` (search.html:310) | squelettes `.sk` (hub.html:72-76) et `.spin` |
| état d'erreur | `"Erreur au chargement des données : {message}"` dans `<tr class="empty">` (annuaire.html:6767) | bandeau `.source-warning` par source (search.html:1508-1527) | `.alert` (hub.html:1141) et `.src-state` par source (hub.html:1060) |

**Lecture.** L'annuaire cherche **dans un jeu déjà chargé** — d'où : pas de bouton, pas de loader, filtrage à la frappe, compteur toujours juste. search.html et hub.html cherchent **sur le réseau, en plusieurs sources parallèles** — d'où : bouton, loaders, états par source, compteurs approximatifs. Ce sont deux barres différentes pour deux problèmes différents ; les unifier en un composant unique ferait perdre soit l'immédiateté de l'une, soit l'honnêteté des états de l'autre. **Ce qu'elles peuvent partager** : le champ texte lui-même (une seule règle, avec la question du fond à trancher — `--cream` chez l'annuaire contre `--white` ailleurs) et le compteur de résultats.

### 7.4 Ses pastilles comparées à celles de `search.html` et `hub.html`

L'annuaire n'a **aucun point rond**. Sa pastille est un **badge rectangulaire** : `td.type .badge{background:var(--teal-xl);color:var(--teal);padding:.1rem .4rem;border-radius:3px;font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;font-weight:600}` (annuaire.css:62).

| | annuaire.html | search.html | hub.html / maquettes |
|---|---|---|---|
| forme | rectangle `border-radius:3px` (annuaire.css:62) | rectangle `border-radius:2px` (search.html:277) | rond `7px` (`.dot`, hub.html:90) ou gélule `border-radius:10px` avec point intégré (`.st`, carte-748.html:71-72) |
| couleur | **une seule** : `--teal-xl` sur `--teal`, plus `#fef9e8`/`--gold` pour PRADA (annuaire.css:63), `#fef9e8`/`#b8932b` pour « manuel » et `#e6f0f5`/`#1e5568` pour « api » (annuaire.html:6658-6659) | **cinq**, plein, texte blanc : `--src-ce`, `--src-admin`, `--src-jud`, `--src-cedh`, `--src-cjue` (search.html:281-285) | `--jud --adm --ce --eu --txt --doc` en bordure et texte, fond transparent (`.tag`, hub.html:227) |
| ce qu'elle dit | **la catégorie d'entité** (« Tribunal judiciaire », « Cour d'appel », « PRADA »), plus la provenance de la donnée en second badge | **le backend interrogé** | **la famille juridictionnelle** (`.tag`) ou **l'état** (`.st`, `.dot`) |
| taille | `.7rem` majuscules | `.66rem` majuscules (search.html:278) | `10px` majuscules (hub.html:227) |

**Trois axes, pas trois versions du même badge.** Catégorie d'entité (annuaire) · backend (search) · famille juridictionnelle et état (hub). Le second badge de l'annuaire — `manuel` / `api` — est en revanche **exactement une note de provenance** (§2.9) : même rôle que `.how` (carte-748.html:115) et même contenu de `title`, mais dessiné comme un badge plein au lieu d'une étiquette à bordure pointillée. C'est le seul élément de l'annuaire qui devrait adopter le composant `.how`.

### 7.5 Ce qui, dans l'annuaire, doit devenir partagé

1. **`.download-row`** (annuaire.css:84-89) — ligne de téléchargements avec mention de licence. Déjà réutilisée par inedits.html:115-118. Aucun équivalent ailleurs ; `ressources.html` fait la même chose en `.card .actions` (ressources.html:57).
2. **`.jl-modal-overlay` / `.jl-modal`** (annuaire.css:151-166) — seule modale du site qui soit dans une feuille de style. À faire adopter par le modal de feedback de search.html:874-884, aujourd'hui en style inline pur, et par la modale d'inedits.html (bloc l. 336-352 environ), aujourd'hui redéclarée en JS.
3. **`.chk-toggle`** (annuaire.css:127-128) — case à cocher teal sans boîte. search.html:116-127 réimplémente la même chose sous `.thes-toggle`, avec le même `accent-color:var(--teal)`.
4. **`.btn` / `.btn-small` / `.btn-secondary`** (annuaire.css:131-135) — le commentaire du fichier le dit : « aligne sur .btn de index.html + variante small/secondary » (annuaire.css:130). C'est déjà un aveu de duplication de components.css:18-53.
5. **`table.data`** (annuaire.css:53-78) avec en-têtes collants et tri — seul tableau du site qui sache faire ça ; à généraliser aux tableaux de hub.html:308-310 et ssr.py:498-505.
6. **`.infobox` / `.infobox.warn`** (annuaire.css:91-94) — doublon exact de `.jl-callout` / `.jl-callout--gold` (components.css:117-129) et de `.infobox` de ressources.html:70-72. Trois écritures, une seule à garder.
7. **`.cat-card`** (annuaire.css:98-103) — carte de navigation vers une sous-page, reprise par inedits.html:59-62 sous un autre nom (`.cat-grid a`). À rapprocher de `.jl-card--hoverable` (components.css:64-67).
8. **`.coverage`** (annuaire.css:33-42) — tableau taux + barre en `--w`. C'est le dessin dont la page « Ce que nous n'avons pas » du prototype a besoin (hub.html:1305-1306, aujourd'hui en `table.tb` sans barres).
9. **Le dispositif anti-aspiration** (`fmtSignal()` annuaire.html:6597-6603, `openSignalModal()` annuaire.html:6615-6651) — recomposition de l'adresse au clic. Il existe sous trois formes incompatibles : celle-ci, le `.mail-r` avec `data-u/data-d/data-t` (index.html:810-814 et quatre autres pages), et celle d'inedits.html (l. 328 environ). Une seule à garder.
10. **La bascule de thème et le résolveur anti-flash** (annuaire.html:6-9 et annuaire.html:6420-6427) — quinzième copie, cf. §4.

### 7.6 Ce qui lui est propre et ne doit pas être généralisé

1. **Le rendu en dur pour l'indexation** — bloc `STATIC_ROWS` annuaire.html:101-6365, injecté par `annuaire/build_annuaire.py` (commentaire annuaire.html:101) et remplacé par le JS au chargement. Ce compromis n'a de sens que pour une page dont le contenu entier est le référencement cible (« qu'une recherche Google sur un de ces mails tombe ici », ssr.py:1249-1250). Le corollaire `table.data tr.jl-paged{display:none}` (annuaire.css:82-83) — « le HTML est là pour Google, mais display:none évite le coût de layout » — est propre aux sous-pages.
2. **La pagination à 1000 lignes avec bouton « all »** (annuaire.html:6673, annuaire.html:6689-6710) — calibrée sur un volume que rien d'autre n'atteint : « ~2 000 rows OK partout, 5 000 marginal » (annuaire.html:6672).
3. **La normalisation de deux jeux hétérogènes** (`loadAll()` annuaire.html:6438-6482) — spécifique au couple juridictions / PRADA.
4. **Le bouton « Inédits » bordeaux** (annuaire.css:119-124, annuaire.html:43-47) — couleur volontairement hors charte (`#7a1e2f`), le commentaire le dit : « bordeaux sombre, contraste avec le teal du site » (annuaire.css:118). À conserver comme exception assumée, pas à tokeniser en couleur d'accent générale.
5. **Les badges `manuel` et `api`** avec leurs couleurs en dur (annuaire.html:6658-6659) — sauf pour leur rôle, qui relève de la note de provenance (§7.4).
6. **La grille des 20 sous-pages** (annuaire.html:6375-6398) et leur déclaration au sitemap (ssr.py:1252-1271) — dispositif propre à l'annuaire et à `inedits`.
7. **Le tableau de complétude alimenté par `annuaire_meta.json`** — structure de données propre (`coverage_by_type`, `counts.juridictions_total`, `counts.api_centraux_total`, `counts.prada_total`, `counts.grand_total`, annuaire.html:6493-6500).

### 7.7 Ses liens sortants et ses sources

- Sources en tête de page : `lecomarquage.service-public.gouv.fr/donnees_locales_v4/all_latest.tar.bz2`, `api-lannuaire.service-public.fr` (en `<code>`, non lié), `cada.fr/particulier/personnes-responsables-resultatss` — annuaire.html:39.
- Téléchargements internes : `/data/annuaire_juridictions.csv`, `/data/annuaire_prada.csv`, `/data/annuaire_juridictions.json`, `/data/annuaire_prada.json` — annuaire.html:69-72.
- API appelée au chargement : les trois mêmes chemins plus `/data/annuaire_meta.json`, en `fetch` parallèle avec `{cache:'default'}` — annuaire.html:6440-6442.
- Liens sortants par ligne : `mailto:` (annuaire.html:6590), site de l'organisme en `target="_blank" rel="noopener"` (annuaire.html:6580), source documentaire en `target="_blank" rel="noopener"` (annuaire.html:6584).
- Signalement : ticket GitHub pré-rempli sur `Dahliyaal/justicelibre` (annuaire.html:6628), et adresse recomposée au clic (annuaire.html:6616).
- Pied : Accueil, Recherche, Ressources, GitHub (annuaire.html:6413) — **liste différente** de celle de search.html:887 (Accueil, GitHub) et de celle d'inedits.html:238 environ (Accueil, Annuaire principal, Inédits, Recherche, GitHub).

---

## 8. LES QUATRE PIÈGES DE FUSION, RÉSUMÉS

1. **`.btn`** vaut plein teal dans hub.html:250 et ghost dans decision-03b.html:66. Même nom, apparences opposées.
2. **`nb`** est un formateur de nombres dans hub.html:338 et un accordeur de pluriel dans histo-02.html:317. Même nom, signatures incompatibles.
3. **`--src-*`** (tokens.css:38-42) code le **backend interrogé**, **`--jud/--adm/--ce/--eu/--txt/--doc`** (hub.html:11) code la **famille juridictionnelle**, et le `.badge` de l'annuaire (annuaire.css:62) code la **catégorie d'entité**. Un résultat du Conseil constitutionnel arrive par `dila` (donc `--src-jud`, brun) mais appartient à la famille constitutionnelle (donc `--ce`, vert) — search.html:1577 le contourne déjà par un cas particulier (`r.juridiction === 'Conseil constitutionnel' ? 'CONSTIT' : r.source_label`). Trois axes, pas trois versions.
4. **`.honest`** (aveu éditorial, carte-748.html:78) et **`.alert`** (échec technique, hub.html:247) partagent la forme mais pas le rôle ; **`.how`** (provenance, carte-748.html:115, bordure en pointillés) et **`.warnp`** (avertissement sur la donnée, hub.html:266, bordure pleine colorée) aussi.
5. **`<em>`** vaut **accent de titre** (serif italique teal, index.html:256) dans 14 titres de prod et **surlignage du terme cherché** (droit, sur fond) dans hub.html:69, hub.html:263 et search.html:300. Une règle `em{}` globale détruirait la seconde lecture.

/home/dahl/justicelibre/scratchpad/audit/inventaire_composants_13sept.md
