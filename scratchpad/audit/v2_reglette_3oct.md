# Réglette « Rendues entre » dans la recherche v2 (3/10/2026)

Local seulement. Rien de déployé, rien de commité.

## Fichiers touchés
- `web/v2/recherche.html` : les deux champs de date (anciennes l. 98-105) remplacés par le bloc `.jl-quand` (l. 105-126) : libellés d'années, deux `input type=range`, graduations, presets, puis `<details>` « Dates précises » qui contient les deux mêmes `#dateMin` / `#dateMax`. Passage à `jl.css?v=30` et `recherche.js?v=2`.
- `web/v2/recherche.js` : constantes l. 56-73, résumé l. 194-212, réglette l. 214-295, appel dans `majAvance` l. 299, liaison dans `demarrer` l. 995.
- `web/styles/jl.css` : bloc ajouté en fin de fichier (l. 1750-1778), commentaire daté du 3/10/2026.
- `web/v2/{article,annuaire,apropos,doctrine,textes,historique}.html` : `jl.css?v=29` passé à `v=30`.

## Ce qui est repris de hub.html
- PRESETS hub.html:599, AN_MAX :600, AN_DEBUT :604-605, anMin :606, isoAgo :750, ticks :720.
- Détection du preset actif :688. Balisage :695-698. CSS : .quand-bloc :137, .range/.track/.fill/.ticks :148-155, .presets/.preset :156-161, .rlab :218.
- JS : refresh :767 (recalcul de la borne gauche), paint :775, syncFromRange :776, presets :781, effacement :783.
- Format du résumé en année seule pour AAAA-01-01 / AAAA-12-31 : fmtAdv `fd`, hub.html:677.

## Points d'accroche dans recherche.js (inchangés)
- `syncUrl` l. 322 écrit `date_min` / `date_max` dans la query string. `lireUrl` l. 337 les relit.
- `interroger` l. 455-456 les envoie à l'API.
- La réglette ne fait qu'écrire `S.dateMin = AAAA-01-01` et `S.dateMax = AAAA-12-31`, ou `''` quand la poignée est en butée. Les presets « 12 mois » et « 5 ans » posent `isoAgo(...)` et laissent `date_max` vide.
- `majQuand` (l. 243) place les curseurs à partir de S. Il est appelé par `majAvance`. Les chips ✕ (l. ~621), « Tout effacer » (l. 1019) et les champs de date (l. 1031) restent donc synchronisés sans autre changement.

## Choix et écarts à relire
1. **Relance des résultats.** Lâcher une poignée (`change`) ou cliquer un preset relance la recherche si une requête est saisie. Aujourd'hui, les champs de date ne relancent pas, et c'est conservé tel quel pour eux. `relancerSiRequete` (l. 278) remet `S.enVol = false` pour contourner le garde-fou anti-double-clic : sans cela, la relance était ignorée quand une recherche était encore en vol (constaté au test). `S.seq` écarte les réponses périmées.
2. **Borne gauche.** Si la `date_min` venue de l'URL est antérieure à AN_MIN, le curseur est seulement *affiché* en butée. S n'est pas modifié, pour ne pas changer la requête.
3. **Dépliage automatique.** « Dates précises » se déplie quand une date n'est ni un 1er janvier ni un 31 décembre et ne correspond pas à un preset.
4. **Résumé.** Les bornes d'année s'affichent « 2010 → 2018 » ou « depuis 2015 ». Les dates précises restent au format `fmtCourt` (« depuis le 15 mars 2019 »).
5. **Chips `#advSum`.** Elles ne se redessinent que dans `renderResults` (comportement existant). Pendant qu'on fait glisser une poignée, elles restent en retard jusqu'à la relance.

## Vérifié (navigateur intégré, http://localhost:8787)
- `node -e "new Function(...)"` sur recherche.js : OK.
- Affichage : bornes 1805 → 2026 sans filtre ; graduations 1805 … 2026.
- Poignée gauche à 2015 : URL `?q=astreinte&date_min=2015-01-01`, résumé « depuis 2015 ».
- Preset « depuis 2020 » : `date_min=2020-01-01`, bouton marqué actif. « tout » : dates retirées de l'URL. « 12 derniers mois » : `date_min=2025-10-03`.
- Conseil d'État coché seul : borne gauche 1875, graduations recalculées.
- Résultats : chargement direct de `juridiction=ce&date_min=2010-01-01&date_max=2018-12-31`, dates 2010-2018. Poignée gauche passée à 2016 : nouvel appel API avec `date_min=2016-01-01`, résultats tous 2016-2018.
- Champ de date précise 15/03/2019 : URL `date_min=2019-03-15`, curseur sur 2019, `<details>` ouvert.
- Mobile 375 px : pas de défilement horizontal (scrollWidth = 375). Les graduations sont serrées mais lisibles.
- Console : aucune exception JS. Seuls des « 404 » de ressources apparaissent, et aucune ressource locale n'est en 404 (toutes en 200 dans le relevé réseau). Origine non identifiée : probablement des appels distants ou des pages précédentes du même onglet.

## Non vérifié
- Clavier : les `input range` natifs sont focusables, avec `aria-label`, `aria-valuetext` et un anneau de focus. Le fonctionnement aux flèches n'a pas été testé.
- Firefox (`::-moz-range-thumb`) et Safari ne sont pas testés. Seul le moteur Chromium du panneau l'a été.
- Pendant un test, trois relances rapprochées ont fini sur « Aucun résultat » alors que l'API, appelée à part avec les mêmes paramètres, en renvoyait 15. Ce n'est pas reproduit avec une seule relance. Cause possible : charge de la prod sous des appels concurrents (délai de 20 s, une seule des deux sources muette, donc compté comme « a répondu, 0 »). Non établi. Ce chemin existe aussi avec le tri.
