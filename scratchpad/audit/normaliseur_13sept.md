# Le normaliseur — jl.css + jl.js — 13 septembre 2026

Exécution du mandat « un seul `jl.css`, un seul `jl.js`, une page de preuve ».
Cahier des charges : [`inventaire_composants_13sept.md`](inventaire_composants_13sept.md).

---

## 0. MANIFESTE DE COUVERTURE

| Fichier | Lignes | Lu jusqu'à | État |
|---|---|---|---|
| `scratchpad/audit/inventaire_composants_13sept.md` | 604 | 604 | **lu en entier**, en quatre passes (1-270, 271-450, 451-605) |
| `web/styles/tokens.css` | 163 | 163 | lu en entier |
| `web/styles/base.css` | 65 | 65 | lu en entier |
| `web/styles/components.css` | 175 | 175 | lu en entier |
| `web/topbar.js` | 243 | 243 | lu en entier |
| `web/maquettes/decision-03b.html` | 288 | 288 | lu en entier (la page de preuve) |
| `web/hub.html` | 1380 | l. 1-110, 220-330, 330-374, 625-669 | **NON LU EN ENTIER** — lecture ciblée sur ce que le rapport désigne comme gagnant : la palette et la structure (1-110), les composants (220-330), les helpers JS et `ICO` (330-374), `renderRail()` (625-669). Le reste (routage, recherche, flux, vérificateur de citations) est hors du périmètre d'un fichier de style et de composants ; les décisions le concernant sont reprises du rapport, qui l'a lu en entier. |
| `web/maquettes/carte-748.html` | 518 | l. 20-214 (tout le `<style>`) | **NON LU EN ENTIER** — le `<style>` est lu intégralement ; le `<script>` n'a été repris que par les citations du rapport (§4). |
| `web/maquettes/histo-02.html` | 636 | l. 224-258 | **NON LU EN ENTIER** — seul le bloc `.jl-h*` / `.jl-view` a été relu ; le reste est repris des citations du rapport. |
| `web/maquettes/histo-05.html` | 624 | 0 | **NON LU** — le rapport établit (manifeste, l. 30) que histo-05 ne diverge d'histo-02 que par 6 écarts, tous cités. Absorbé par ces citations. |
| `web/maquettes/decision-01.html` | 244 | 0 | **NON LU** — le rapport donne ses divergences exactes avec decision-03b (§2.7, §2.11, §4). Absorbé par ces citations. |
| `web/styles/annuaire.css` | 166 | 0 | **NON LU** — décision de la propriétaire : `annuaire.html` reste en l'état (rapport §7). Ses composants sont repris par les citations du rapport §7.5. |
| `ssr.py`, `web/index.html`, `web/search.html`, `web/annuaire.html` | — | 0 | **NON LUS** — interdits en écriture, et intégralement inventoriés par le rapport. |

**Produit** : `web/styles/jl.css` (821 l.), `web/jl.js` (618 l.), `web/maquettes/decision-jl.html` (129 l.), `web/maquettes/composants.html` (304 l.). Aucun fichier interdit n'a été modifié (vérifiable : les seules écritures sont ces quatre chemins).

---

## 1. LES CINQ PIÈGES DE FUSION, ET COMMENT jl.css LES ÉVITE

| # | Piège (rapport §8) | Comment il est évité | Fichier:ligne |
|---|---|---|---|
| 1 | `.btn` = **plein teal** (hub.html:250) mais **ghost** (decision-03b.html:66). Une normalisation naïve inverserait l'apparence de tous les boutons des pages décision. | Le nom `.btn` n'existe nulle part dans jl.css : les 2 seules occurrences de `.btn` dans jl.css sont dans le commentaire du piège lui-même (jl.css:391-392). Le composant s'appelle `.jl-bouton`, **plein par défaut**, et le ghost est un modificateur **explicite** `.jl-bouton--ghost`. Aucune page ne peut hériter de la mauvaise apparence par accident, parce qu'aucune ne peut employer l'ancien nom. | `jl.css:391-423` (commentaire du piège en 391-393, composant en 394) |
| 2 | `nb` = formateur de nombres (hub.html:338) **et** accordeur de pluriel (histo-02.html:317). Même nom, signatures incompatibles. | Arbitrage écrit dans le code : `nb(n)` reste le formateur, l'accordeur s'appelle `plur(n, un, plusieurs)`. Le commentaire cite les deux origines pour qu'une reprise de code ne rebranche pas la mauvaise. | `jl.js:97-105` |
| 3 | Trois axes de couleur confondus : `--src-*` = **backend interrogé**, `--jud/--adm/--ce/--eu/--txt/--doc` = **famille juridictionnelle**, `.badge` de l'annuaire = **catégorie d'entité**. | Les trois jeux de jetons sont déclarés dans **trois blocs séparés et étiquetés** (« AXE 1 », « AXE 2 ») avec la mention ⛔ de non-fusion, et les trois composants de rendu sont distincts : `.jl-src-badge--*` (rectangle plein), `.jl-tag--*` (bordure et texte), `.jl-badge` (pastille teal-xl). Le catalogue les montre côte à côte dans un tableau à trois lignes. | jetons `jl.css:67-73` · composants `jl.css:672-691` (commentaire du piège en 672) |
| 4 | `.honest` (aveu éditorial) vs `.alert` (échec technique) ; `.how` (provenance, pointillé) vs `.warnp` (avertissement sur la donnée, bordure pleine colorée). | Quatre composants, quatre sections, deux commentaires de piège. `.jl-honnetete` = bordure gauche 3 px `--warn` sur `--warn-bg`, **jamais rouge** ; `.jl-alerte` = bordure **2 px `--bad`**. `.jl-provenance` = bordure **en pointillés** neutre + `cursor:help` ; `.jl-warnp` = bordure **pleine** `--warn`. | provenance `jl.css:425-439` (commentaire en 425-426) · honnêteté `jl.css:442-449` · alerte `jl.css:451-457` |
| 5 | `<em>` = **accent de titre** (serif italique teal, 14 titres de prod) **et** **surlignage du terme cherché** (droit, sur fond). Une règle `em{}` globale détruirait la seconde lecture. | **Aucune règle `em{}` globale** dans jl.css : le sélecteur est toujours porté par une classe de titre (`.jl-titre em`, `.jl-titre--h1 em`, `.jl-titre--nu em`, `.jl-titre--h3 em`). Le surlignage est un composant à part, `.jl-hl`, `font-style:normal` sur fond `--teal-xl`. La règle « capitales = droit » est un modificateur explicite, `.jl-titre--capitales em{font-style:normal}`, et non une exception silencieuse comme index.html:199. | `jl.css:544-551` (commentaire du piège en 544-545) |

Vérification : `grep -nE '^\s*em\s*\{|[^.a-z-]em\s*\{' web/styles/jl.css` ne retourne que les quatre sélecteurs préfixés par une classe de titre.

---

## 2. TABLE DE CORRESPONDANCE — ancienne classe → nouvelle classe

### 2.1 `web/hub.html`

| Ancien | Nouveau | Note |
|---|---|---|
| `.top` (hub.html:28) | `topbar.js` + `html.jl-dense` | variante de densité, pas un composant |
| `.logo` / `.logo span` (29-30) | porté par `html.jl-dense .topbar .logo-area` | |
| `.nav` / `.nav a.on` (31-32) | `topbar.js` `nav.main-nav` / `.active` | |
| `.app` (33) | `.jl-app` | |
| `.rail` / `.rail.mini` (34-35) | `.jl-rail` / `.jl-rail--mini` | |
| `.rail .hd` (37) | `.jl-rail__hd` | |
| `.rail .sec` (38) | `.jl-rail__sec` | |
| `.ri` / `.ri:hover` / `.ri.on` (39-41) | `.jl-ri` / `.jl-ri:hover` / `.jl-ri.is-on` | |
| `.ri .n` (43) | `.jl-ri__n` | |
| `.ri.soon` (hub.html, fin du style) | `.jl-ri.is-soon` | gris inactif, jamais rouge |
| `.body` (92) | `.jl-body` | |
| `.dot` / `.dot.soon` (90-91) | `.jl-point` / `.jl-point--soon` | |
| `.spin` (fin) | `.jl-spin` | |
| `.src-state` / `i.ok .ko .run` / `.spin.sd` (277-281) | `.jl-sources` + `.jl-pastille--ok/--morte/--loader` | la pastille loader **est** `.spin.sd` |
| `.sk` (72-76) | `.jl-sk` | |
| `.feed-h` (56) | `.jl-titre` | noir, serif |
| `.h5` (25) | `.jl-surtitre` | |
| `.btn` (250) **plein** | `.jl-bouton` | piège n° 1 |
| `.btn.ghost` (251) | `.jl-bouton--ghost` | |
| `.btn:disabled` | `.jl-bouton[disabled]` | |
| `.chip` (140-144) / `.pill` (224-226) / `.preset.on` | `.jl-filtre` / `.jl-filtre.is-on` | **filtres**, pas des boutons |
| `.tag` (227) | `.jl-tag--*` | axe 2 |
| `.tile` / `.tt` / `.ts` / `.tn` (228-232) | `.jl-tuile` / `__t` / `__s` / `__n` | |
| `.seg` / `.seg button.on` (256-257) | `.jl-vue--sm` / `.is-on` | |
| `.note` (246) | `.jl-note` | |
| `.alert` (247-248) | `.jl-alerte` | piège n° 4 |
| `.warnp` (266) | `.jl-warnp` | piège n° 4 |
| `.off` (265) | `.jl-off` | |
| `.tl` / `.tl .ev::before` / `.bad` / `.soon` (291-295) | `.jl-frise` / `.jl-frise__ev` / `--morte` / `--bientot` | **gagnant** du point-frise |
| `.sbar` / `.sbar .go` (98-101) | `.jl-barre-reseau` / `__go` | |
| `table.tb` (308-310) | `.jl-tableau` | gagne en plus les th collants et le tri |
| `.proto` (311) | `.jl-proto` | |
| `.card2 .res em` / `.item .sum em` (69, 263) | `.jl-hl` | piège n° 5 |
| `.kv` (286-287) | `.jl-dl` | |
| `.cal` (205-217) | `.jl-datepop` (enveloppe) | voir §4, non absorbé en entier |
| `.rec` (244-245) | *(non absorbé)* | voir §4 |

### 2.2 `web/maquettes/carte-748.html`

| Ancien | Nouveau |
|---|---|
| `.cta` (45-47) | `.jl-bouton--cta` |
| `.calbtn` (49-51) | `.jl-calbtn` |
| `.datepop` / `.open` / `.k` / `.row` / `.chip` / `.err` (52-62) | `.jl-datepop` / `.is-open` / `__k` / `__row` / `.jl-chip` / `__err` |
| `.alert` (63-64) | `.jl-alerte` |
| `.warnp` (65) | `.jl-warnp` |
| `.tag` (66) | `.jl-tag--*` |
| `.st` / `::before` / `.ok .ab .q .fut` (71-73) | `.jl-pastille` / `--ok --morte --q --future` — **gagnant** de la pastille |
| `.src` (74) | `.jl-src` |
| `.honest` (78-79) | `.jl-honnetete` — **gagnant** du bloc honnêteté |
| `.btn` / `.btn.ghost` (86-87) | `.jl-bouton` / `--ghost` |
| `.idband` / `>div` / `.k` / `.v` (90-94) | `.jl-bande` / `__k` / `__v` — **gagnant**, sans boîte |
| `.it` / `.rel .t .d .x` / `.it.dead` (107-114) | `.jl-lt` / `__rel __t __meta __long` / `--morte` |
| `.how` (115) | `.jl-provenance` — **gagnant** de la note de provenance |
| `.chain` / `.ch` / `.members` / `.mem` (140-158) | `.jl-chaine` / `__tete` / `__membres` / `.jl-membre` |
| `.mem.dead` / `.mem.fut` (155-156) | `.jl-membre--morte` / `--future` |
| `.legend` / `.legend i` (159-160) | `.jl-legende` / `.jl-point` |
| `.juris h2` (163-164) | `.jl-titre--nu` |
| `.jc` / `.bottom .card` (166-174) | `.jl-tuile` / `.jl-carte` |
| `.jl-rel .jl-meta .jl-t .jl-long .jl-more` (188-196) | `.jl-lt__rel __meta __t __long __more` — **gagnant** de la ligne-texte |
| `.jl-tree` / `.jl-node` / `.last` (198-202) | `.jl-arbre` / `.jl-noeud` / `--last` |
| `.jl-item` (206) | `.jl-lt` |
| `.artlink` (212) | `.jl-artlink` |
| `.help` / `.help::after` (95-97) | *(non absorbé)* — voir §4 |

### 2.3 `web/maquettes/histo-02.html` et `histo-05.html`

| Ancien | Nouveau |
|---|---|
| `.jl-view` / `a.on` (249-252) | `.jl-vue` / `.is-on` — **gagnant** de la bascule de vue |
| `.jl-hfil` / `.on` (229-231) | `.jl-filtre` / `.is-on` |
| `.jl-hhonest` (226) | `.jl-honnetete` (les 22 px de marge deviennent une marge locale) |
| `.jl-h2` (234) | `.jl-surtitre` **mais en `--ink`** → arbitré : c'est un titre, donc `.jl-titre--nu` ; la règle de couleur tranche (noir = titre, gris = sur-titre) |
| `.jl-hpanel` (227) | `.jl-carte` |
| `.jl-hnota` (240-241) | `.jl-note` |
| `.jl-hmark` (243) | `.jl-warnp` (même sens : avertissement sur la donnée) |
| `.jl-hkey` / `i` (238-239) | `.jl-legende` / `.jl-point` |
| `.jl-hdead` / `.jl-hfutur` (235-236) | `.jl-lt--morte` / `.jl-membre--future` |
| `.jl-hdiff ins/del` (237) | *(non absorbé)* — voir §4 |
| `.g2row .g2bar .g2cap .g2notch .g2mark` (518-557) | *(non absorbé)* — **vue** de la page Historique, pas un composant (rapport §2.5) |
| `.p5acc .p5frise .p5seg` (histo-05:530-559) | *(non absorbé)* — idem |

### 2.4 `web/maquettes/decision-03b.html` → `decision-jl.html`

C'est la reconstruction complète. Correspondance intégrale :

| Ancien | Nouveau |
|---|---|
| `.top` + `.nav` + `#themeBtn` (144-148) | `topbar.js` (`<div data-topbar-mount>`) + `html.jl-dense` |
| `.rail` en dur (150-161) | `.jl-rail` vide + `JL.renderRail()` alimenté par `#jl-page` |
| `.app` / `.body` (149, 162) | `.jl-app` / `.jl-body` |
| `.crumb` / `#backrow` (163) | `.jl-fil` + `JL.bindBackLink()` |
| `.kicker` (163) | `.jl-kicker` |
| `.titlerow` / `h1` / `h1 em` (163) | `.jl-titrerow` / `.jl-titre--h1` / `.jl-titre--h1 em` (serif italique teal — le n° de pourvoi est bien la signature) |
| `.tacts` (163) | `.jl-actions` |
| `.ibtn#btnPrint` | `.jl-bouton--icone[data-jl-print]` |
| `.btn#btnLLM` (**ghost**) | `.jl-bouton--ghost[data-jl-llm]` — piège n° 1 résolu par le nom |
| `.idband` (119-120) | `.jl-bande--enligne` + `.jl-bande__k` |
| `.st.ok` | `.jl-pastille--ok` |
| `.how` | `.jl-provenance` |
| `.mono` / `.muted` | `.jl-mono` / `.jl-muted` |
| `.refbar` (121) | `.jl-refbar` |
| `.btn[data-copy]` | `.jl-bouton--ghost.jl-bouton--sm[data-copy]` + `JL.bindCopy()` |
| `.copyok#copyok` | `.jl-copyok[data-copy-ok]` |
| `.cta` (71) | `.jl-bouton--cta` |
| `input.tab` / `.tabs` / `.panes` / `.pane-texte` / `.pane-fiche` (122-129) | `input.jl-tab` / `.jl-onglets` / `.jl-panes` / `.jl-pane--texte` / `.jl-pane--fiche` |
| `.pane-texte .wrap` (131) | `.jl-lecture` |
| `.toc` / `a.l3` / `a.on` (84-88) | `.jl-toc` / `a.l3` / `a.is-on` + `JL.bindToc()` |
| `.somm` / `.somm-t` / `.somm-m` (133-135) | `.jl-somm` / `__t` / `__m` |
| `.h-k` (62) | `.jl-surtitre--flex` |
| `.h5` (35) | `.jl-surtitre` |
| `.chip` (92) | `.jl-chip` |
| `.fold` / `.entete-fold` (110-113) | `.jl-fold` / `.jl-entete-fold` |
| `.entete` (82-83) | `.jl-entete` |
| `h2.sec` / `h3.sec` (60-61) | `.jl-titre--nu` / `.jl-titre--h3` |
| `.txt p` / `.pn` / `.no` / `p:target` (77-81) | `.jl-txt p` / `.jl-pn` / `.jl-no` / `.jl-txt p:target` |
| `.artlink` (76) | `.jl-artlink` |
| `.dgrid` (130) | `.jl-grille-2` |
| `.vise` / `.t` / `.d` (96-97) | `.jl-vise--encadre` / `__t` / `__d` |
| `.part` / `.role` / `.nom` / `.cons` (93-95) | `.jl-partie` / `__role` / `__nom` / `__cons` |
| `.chrono` / `li.cur` / `.d .j .w` (98-105) | `.jl-chrono` / `li.is-cur` / `__d __j __w` |
| `.honest` (69-70) | `.jl-honnetete` |
| `footer.prov` (225) | `.jl-pied` |
| `.proto` (109) | `.jl-proto` |
| `@media print` (116, 139) | §26 de jl.css, considérablement étendue |
| script thème `hub-theme` (231-233) | `JL.cycleTheme()` sur `jl-theme`, une seule clé |
| script copie (235-239) | `JL.bindCopy()` (le repli `getSelection()` est conservé) |
| script sommaire collant (241-246) | `JL.bindToc()` |
| script onglets (249-257) | `JL.bindTabs()` |
| script « ← Résultats » (260-262) | `JL.bindBackLink()` |
| script impression + LLM (264-285) | `JL.bindPrint()` + `JL.bindLLMCopy()` |

**Contrôle d'identité du texte** : après suppression des balises, des `<script>`, des `<style>` et du `<head>`, `decision-jl.html` et `decision-03b.html` ont **exactement le même texte**, aux seules exceptions du chrome désormais injecté par JS (libellés du header et du rail, absents du HTML statique) et de l'étiquette du prototype. Aucun mot du sommaire officiel, de l'en-tête, des 15 paragraphes numérotés, du dispositif, des textes visés, de la chronologie, des parties ou de la note de provenance n'a bougé.

### 2.5 `web/maquettes/decision-01.html`

Absorbée par citations du rapport, sans relecture du fichier : `.idband` encadré (decision-01.html:112-114) devient **le modificateur** `.jl-bande--encadree` et non un second composant ; tout le reste est identique à decision-03b (le rapport le dit : palette, `.st`, `.how`, `.honest`, `.chrono`, copie presse-papier). Sa grille à deux panneaux côte à côte (`.grid`, decision-01.html:115) est couverte par `.jl-grille-2`.

---

## 3. LES JETONS : CE QUI A ÉTÉ TRANCHÉ

### 3.1 Palette

| Décision | Application |
|---|---|
| Fond de page = `--light` | `body{background:var(--light)}` (`jl.css:167`) ; `--cream` réservé aux surfaces secondaires : survol du rail (`.jl-ri:hover`), champs du popover de date, fond des onglets, code copiable |
| `--bad` remplace `--red` | `--red:var(--bad)` en alias (`jl.css:80`) |
| `--ok` remplace `--green` | `--green:var(--ok)` en alias |
| `--warn` remplace `--gold` | `--gold:var(--warn)` en alias |
| `--body` ajouté à la palette du hub | `jl.css:56` |
| Bordeaux « Inédits » | jeton dédié `--accent-inedits` (`jl.css:77`), employé **uniquement** par `.jl-bouton--inedits`. Ce n'est pas un accent général. |
| Une seule clé localStorage | `jl-theme` (`jl.js:159`) ; `hub-theme` est **migré une fois puis effacé** (`jl.js:186-193`) pour que personne ne perde sa préférence |
| Un seul cycle | clair → sombre → système (`THEME_CYCLE`, `jl.js:160`) |

### 3.2 Les 21 tailles du prototype ramenées sur l'échelle

Deux crans ont été **ajoutés**, comme le mandat l'autorise, et documentés dans le fichier (`jl.css:88-101`) :
- `--text-3xs: .625rem` (10 px) — les sur-titres et les gélules mono, qui existaient en 9,5 / 10 / 10,5 px ;
- `--text-hero: 1.9rem` (30 px) — le `h1` des maquettes, qui n'avait aucun cran entre `--text-2xl` (27) et `--text-3xl` (35).

| Pixels du prototype | Cran retenu |
|---|---|
| 9,5 · 10 · 10,5 | `--text-3xs` (10) |
| 11 · 11,5 | `--text-xs` (11,5) |
| 12 · 12,5 | `--text-sm` (12,5) |
| 13 · 13,5 · 14 | `--text-base` (14) |
| 14,5 · 15 · 15,5 | `--text-md` (15) |
| 16 · 16,5 · 17 | `--text-lg` (17) |
| 18 · 19 · 20 | `--text-xl` (20) |
| 22 · 26 | `--text-2xl` (27) |
| 30 | `--text-hero` (30) |
| 36 | `--text-3xl` (35) |

21 valeurs → 10 crans. Idem pour les espacements (`--space-*`), les rayons (`--radius-sm/md/lg/xl/pill`, un cran `xl` de 8 px ajouté parce que toutes les cartes des maquettes l'emploient), les ombres (`--shadow-pop` ajouté pour les popovers), les transitions.

---

## 4. CE QUE JE N'AI **PAS** PU ABSORBER, ET POURQUOI

| Élément | Où | Pourquoi il reste dehors |
|---|---|---|
| **Le calendrier fabriqué en JS** (`.cal`, hub.html:205-217, `openCal()` 719-744) | hub | Le rapport veut `.datepop` comme enveloppe **avec `.cal` dedans** (§2.12). L'enveloppe est faite (`.jl-datepop`) ; le calendrier lui-même est **200 lignes de JS de rendu** qui n'existent nulle part ailleurs et que je ne pouvais ni tester ni brancher sur une page décision. jl.css pose le contenant ; le contenu reste l'`input type=date` natif. **À faire dans une seconde passe.** |
| **Le diff mot à mot** (`diffWords`, hub.html:1147-1155 ; `.jl-hdiff ins/del`, histo-02.html:237-238) | hub, histo | C'est un algorithme, pas un composant, et il n'a aucun usage dans la page de preuve. Les trois copies restent à fusionner. |
| **`jaccard` + `words`** (4 copies) | hub, carte-748, histo-02/05 | Idem : mesure de similarité, sans usage dans la page de preuve. |
| **`lifeAt`, `pill`, `clean`, `minus`, `titreArr`, `legifrance`, `linkArts`, `CODE_SIGLE`** | carte-748, histo-02/05 | Ce sont des fonctions **de domaine** (droit de la vie des textes), pas des composants d'interface. Les mettre dans jl.js aurait dépassé le mandat, et deux d'entre elles **divergent** entre les copies (`lifeAt` : histo-02.html:311 a un cas `MODIFIE` que carte-748 n'a pas ; `minus` : « arrêté » contre « l'arrêté »). **Trancher ces deux divergences est un préalable à leur fusion**, et c'est un arbitrage de fond, pas de style. |
| **Les deux vues de la page Historique** (`.g2*` Gantt, `.p5*` poupées russes) | histo-02/05 | Le rapport le dit lui-même (§2.5) : ce sont des **vues**, pas des variantes du composant chaîne. Les absorber aurait fabriqué un faux composant. |
| **`.help` / `.help::after`** (carte-748.html:95-97) | carte-748 | Infobulle maison de 300 px. Non nommée par la propriétaire, et en concurrence directe avec l'attribut `title` natif qu'emploient `.jl-provenance` et `.jl-pastille`. Deux mécanismes d'explication, un seul à garder → **À TRANCHER**, voir §6. |
| **`.rec`** (hub.html:244-245) | hub | Ligne à deux colonnes `date | contenu` de 96 px. Le rapport dit (§2.4) qu'elle **n'est pas** une ligne-texte. Elle n'a pas de nom dans le vocabulaire de la propriétaire et aucun usage dans la page de preuve. |
| **Le dispositif anti-aspiration des adresses** (3 formes incompatibles) | annuaire, index, inedits | Décision de la propriétaire : `annuaire.html` reste en l'état, et il est interdit en écriture. Le choix entre les trois formes ne peut pas être fait sans toucher à l'annuaire. |
| **Le `.page-subbar` (fil d'ariane collant)** | components.css:155-162 | Conservé tel quel dans components.css ; jl.css fournit `.jl-fil` (le fil de la page décision, non collant). Les deux coexistent parce que **8 pages prod interdites en écriture** dépendent de `.page-subbar`. |
| **La réconciliation `.num` mono teal / `<em>` serif italique** (rapport §6.3) | decision-03b:52 | **Absorbée** : `decision-jl.html` rend le numéro de pourvoi en `<em>` serif italique teal, conformément à la décision de la propriétaire. C'est le seul écart visuel volontaire avec decision-03b. |
| **`ssr.py`** | — | Interdit en écriture. Il extrait le HTML et le CSS de `topbar.js` par expression régulière ; jl.css ne touche pas à `topbar.js`, donc le SSR n'est pas cassé. Mais il continue d'envoyer le CSS topbar **en double** (rapport §1.3a) : non corrigé, hors mandat. |

---

## 5. VÉRIFICATIONS FAITES DANS LE NAVIGATEUR

| Contrôle | Résultat |
|---|---|
| Erreurs console, `decision-jl.html` | **aucune** (`read_console_messages onlyErrors`) |
| Erreurs console, `composants.html` | **aucune** |
| Rendu 1280 px, thème clair | conforme ; capture prise |
| Rendu 1280 px, thème sombre | conforme ; capture prise (rail, pastilles, provenance, sommaire officiel et les trois axes tiennent tous en sombre) |
| Rendu 390 px | rail masqué (`display:none`), burger de `topbar.js` présent, **débordement horizontal = 0 px** |
| Impression (`@media print`) | vérifié en injectant les 16 règles du bloc `print` comme feuille d'écran : header, rail, sommaire, onglets et tous les boutons masqués ; les **deux** panneaux ouverts ; grilles remises en blocs ; **la mise en page desktop part sur le papier**, pas la mobile (c'était le piège de search.html:585-588) |
| Onglets | `#t-fiche` ouvre le panneau Dossier et ferme Texte |
| Rail | 8 entrées rendues par `JL.renderRail()` depuis `#jl-page` |
| Copie | 2 boutons `[data-copy]` câblés, bouton LLM câblé |
| « ← Résultats » | masqué sans référent de recherche (comportement attendu) |
| `--topbar-h` | publié à 56 px par la mesure réelle |
| Syntaxe JS | `node --check jl.js` : OK |
| Styles en ligne dans `decision-jl.html` | **zéro** (assertion dans le script de génération) |

**Une bizarrerie à connaître, qui n'est pas une régression** : dans l'outil de prévisualisation, **toute capture prise après un défilement revient vide** — y compris sur `decision-03b.html` non modifiée, que je n'ai pas touchée. C'est un défaut de capture du panneau navigateur (`backdrop-filter` sur un en-tête collant), pas un défaut de la page : `elementFromPoint` renvoie bien le contenu attendu aux mêmes coordonnées. Les captures ci-dessus ont donc été prises en haut de page, en masquant temporairement les sections précédentes pour atteindre les suivantes.

---

## 6. « À TRANCHER » — choix non couverts par les décisions, signalés et non décidés en silence

1. **Le script de thème en tête de page.** `decision-jl.html` porte **un** `<script>` inline de 2 lignes, avant les feuilles, qui pose `data-theme` depuis `localStorage` pour éviter le flash blanc. Le mandat n'autorise inline que le JSON-LD, le head SEO et les données. **Ma proposition** : le garder, parce que c'est exactement le dispositif des 8 pages prod (annuaire.html:6-9) et qu'il relève du rendu, comme le head ; sans lui, la page clignote en blanc à chaque chargement en thème sombre. **Si tu refuses**, la parade est de charger `jl.css` avec un attribut `media` commuté par `jl.js`, ce qui retarde le premier rendu — je ne l'ai pas fait sans ton accord.

2. **Deux bascules de thème coexistent sur la page.** Celle de `topbar.js` est **binaire** (clair ↔ sombre) ; celle du rail, rendue par `jl.js`, fait le **cycle à trois états** décidé. Les deux écrivent la même clé `jl-theme`, donc rien ne se contredit, mais l'utilisateur a deux gestes pour un réglage. **Ma proposition** : faire passer `topbar.js` au cycle à trois états en appelant `JL.cycleTheme()` quand `JL` existe — c'est une modification de `topbar.js`, que je n'ai pas faite (fichier interdit).

3. **`.help` (infobulle maison, 300 px) contre `title=""` natif.** Le prototype emploie les deux. **Ma proposition** : garder `title` pour les étiquettes courtes (provenance, pastille), et ne réintroduire `.help` que pour les explications longues qui ne tiennent pas dans une infobulle système — mais alors sous un nom du vocabulaire, `.jl-explication`, et pas comme un second mécanisme concurrent.

4. **Le libellé « bientôt » de `.jl-tuile--bientot` est en gris, pas en doré.** components.css:74 le mettait en `--gold` (devenu `--warn`) et écrivait `"bientot"` sans accent ; ressources.html:66 écrivait `"bientôt"`. **Ma proposition, appliquée** : accent rétabli, et couleur passée au **gris** `--muted`, parce que la règle de couleur que tu as fixée dit « gris = inactif, bientôt ». Le doré est désormais réservé à l'avertissement. **Signalé parce que c'est un changement visuel** par rapport à components.css.

5. **`.jl-h2` d'histo-02.html:234** (10 px, majuscules, **`--ink` et gras**) a la métrique d'un sur-titre et la couleur d'un titre. J'ai tranché par ta règle (noir = titre de section) et l'ai envoyé sur `.jl-titre--nu`. **À confirmer** : si tu le voulais comme sur-titre insistant, il faudrait un `.jl-surtitre--fort`.

6. **`--topbar-h` est mesuré deux fois** : par `topbar.js:182-186` et par `JL.measureTopbar()`. Les deux écrivent la même valeur au même endroit, donc c'est inoffensif, mais c'est encore une duplication. **Ma proposition** : retirer la mesure de `topbar.js` une fois que `jl.js` sera chargé partout — modification d'un fichier interdit, non faite.

7. **`--cream` en fond des onglets.** `.jl-onglets` garde le fond `--cream` de decision-03b.html:122, alors que le fond de page est maintenant `--light`. Les deux sont très proches en clair (#fdfcf8 contre #f5f5f3) et identiques en sombre. **Ma proposition** : le laisser, la nuance sépare visuellement la barre d'onglets collante du corps. À dire si tu préfères `--light`.

8. **La feuille d'impression de `search.html` (110 lignes) n'a pas été absorbée en entier.** J'ai repris son enseignement décisif (le point de rupture qui s'active sur le papier) et ses valeurs de base (`@page`, `orphans/widows`, taille en points), mais pas le renommage du PDF par le titre de la décision (search.html:2660-2671) ni ses règles propres aux cartes de résultats. **À faire** quand la page de recherche passera au normaliseur.

---

## 7. FICHIERS PRODUITS

- `web/styles/jl.css` — 821 lignes, 26 sections, en-tête listant tous les composants et renvoyant au rapport.
- `web/jl.js` — 618 lignes, en-tête listant l'API exposée sur `window.JL`.
- `web/maquettes/decision-jl.html` — 129 lignes, **aucun style ni script inline** hors JSON-LD, head SEO, résolveur de thème (§6.1) et bloc de données `#jl-page`.
- `web/maquettes/composants.html` — 304 lignes, catalogue de tous les composants avec variantes, états et noms de classe.

Aucun commit n'a été fait. Aucune page de production n'a été modifiée.

/home/dahl/justicelibre/scratchpad/audit/normaliseur_13sept.md
