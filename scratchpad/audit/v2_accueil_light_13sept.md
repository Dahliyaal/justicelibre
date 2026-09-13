# v2 — accueil « version light » de la page d'accueil actuelle (13 sept. 2026)

## Manifeste

- **Demande** : `web/v2/index.html` ne devait plus être une page d'atterrissage inventée
  (hero + 2 boutons + 5 chiffres) mais **la même page que la prod `https://justicelibre.org/`,
  en plus court**.
- **Méthode** : `web/index.html` (817 lignes) lu en entier. Même ordre de sections, même ton,
  même hero avec son illustration `circuit.png` / `circuit-dark.png`, mêmes chiffres en bandeau.
  Chaque section longue est réduite à son noyau et renvoyée vers `web/v2/apropos.html`
  (qui contient déjà tout le texte intégral) par un lien « en savoir plus ».
- **Texte** : repris **mot pour mot** de `web/index.html`. Aucune réécriture ; seules des coupes.
  Les seuls libellés nouveaux sont les trois liens de renvoi et le lien de contact du pied ;
  aucun tiret cadratin dedans.
- **Fichiers écrits** : `web/v2/index.html` (réécrit) et un ajout daté **en fin** de
  `web/styles/jl.css` (bloc « v2 accueil light, 13 sept. », 20 lignes : grille du hero +
  bascule clair/sombre de l'illustration). `web/jl.js` non touché. Rien d'autre. Rien de commité.
- **Scripts / styles inline** : aucun, hors le `<head>` SEO (JSON-LD), le résolveur de thème
  (2 lignes) et le `#jl-page`.
- **Rail** : bloc `#jl-page` copié de `web/v2/recherche.html:189-211` avec `"actif":""`,
  `"soon":true` maintenu sur **Textes**, **Travaux préparatoires** et **Vérifier mes citations**
  (Avis & doctrine et Annuaire pointent vers leurs pages, comme sur `apropos.html:345-351`).

## Table section par section

| Prod (`web/index.html`) | v2 (`web/v2/index.html`) | Traitement |
|---|---|---|
| Hero, h1 « …jurisprudence *française.* » (441) | h1 identique, `<em>` serif italique teal | **gardé tel quel** |
| Chapô hero (442) | idem, mot pour mot | **gardé tel quel** |
| Bouton « Accéder à l'endpoint MCP » (443) | « Rechercher librement » → `/v2/recherche.html` + « À propos » → `/v2/apropos.html` | remplacé (demande explicite) |
| Illustration circuit (445-448) | `circuit.png` / `circuit-dark.png`, masquée < 860 px et à l'impression | **gardé tel quel** |
| 4 tuiles de stats (456-459) | 5 tuiles : 3 285 952 · 1,75 M+ · 107 273 · 71 142 · 0 €, chacune avec sa provenance en `title` | chiffres du rapport `v2_accueil_doctrine_annuaire_13sept.md` §1.3 |
| « Installation en *trois étapes* » (465-475) | h2 + phrase d'intro + endpoint en `<code>` + les 3 étapes | **condensé** (encadré prod → `jl-url` + `jl-etapes`) |
| « 30 outils, *toute la matière* juridique française » (480-481) | h2 et paragraphe repris mot pour mot | **gardé tel quel** |
| Encadré `get_law_article` / Dalloz (483-487) | absent | **renvoyé vers À propos** (`apropos.html:98-106`) |
| 26 fiches d'outils, 6 sous-titres (489-627) | **6 outils phares** : `search_all`, `search_admin`, `search_judiciaire_libre`, `get_law_article`, `get_law_versions`, `search_decisions_citing` + lien « Voir les 30 outils → » | **condensé + renvoyé** (`apropos.html:108-162`) |
| « Pourquoi c'est *gratuit* et *légal* » (632-634) | h2 + **3 phrases** : « C'est la loi », Licence Ouverte 2.0, « Nous rendons la jurisprudence à son propriétaire légal : le citoyen. » | **condensé** (fusion de 633 et 634) |
| Encadré Indépendance / Transparence / Sources (635-639) | lien « Indépendance, transparence, sources : en savoir plus → » | **renvoyé vers À propos** (`apropos.html:62-67`) |
| Bouton Ko-fi (640-645) | `jl-bouton jl-bouton--cta` vers ko-fi.com/justicelibre | **gardé tel quel** |
| « La France, *seul pays européen*… » (650) | h2 repris mot pour mot | **gardé tel quel** |
| 4 paragraphes du combat (652-658) | **1 paragraphe**, phrases extraites de 656 et 658 (verrou OAuth2 / PISTE, « aucun texte de loi », « entrave disproportionnée ») | **condensé + renvoyé** (`apropos.html:205-238`) |
| Encadré tutoriel PISTE 13 étapes (660-664) | absent, couvert par le lien de renvoi | **renvoyé vers À propos** (`apropos.html:240-245`) |
| Frise 5 jalons (666-702) | absente | **renvoyé vers À propos** (`apropos.html:247-283`) |
| Pied : sources + licence (709-713) | `jl-pied` : sources, Licence Ouverte 2.0, Licence MIT, mention « copie miroir indexée » | **condensé** |
| Pied : GitHub (717) | lien `https://github.com/Dahliyaal/justicelibre` | **gardé tel quel** |
| Pied : mentions légales / RGPD (728) | liens `/mentions-legales.html` et `/confidentialite.html` | **gardé tel quel** |
| Pied : contact anti-scrape (724) | `class="jl-mail-r" data-u/-d/-t`, assemblé au clic par `jl.js:901` | **gardé tel quel** (mécanisme v2) |
| Topbar prod + burger + drawer (402-436) | `topbar.js` (mêmes pages v2) | remplacé par le composant v2 |
| Badge « MàJ » lu dans `/version.json` (797-807) | absent | **à trancher** ci-dessous |

## Signature typographique conservée

- `index.html:441` → `v2/index.html` h1 : « …jurisprudence <em>française.</em> »
- `index.html:480` → « 30 outils, <em>toute la matière</em> juridique française »
- `index.html:632` → « Pourquoi c'est <em>gratuit</em> et <em>légal</em> »
- `index.html:650` → « La France, <em>seul pays européen</em>… »
Rendu par `jl.css:561` (`.jl-titre em` serif italique teal) et `jl.css:1393` (`.jl-acc__h1 em`).

## Vérifications faites

- `http://localhost:8787/v2/index.html` : **zéro erreur console**.
- 1280 px : débordement horizontal **0 px**, hero à deux colonnes, illustration chargée
  (`circuit.png`, 2048 px de large en natif).
- 390 px : débordement **0 px**, hero en une colonne, illustration masquée (< 860 px),
  chiffres empilés, rail en mode mini.
- Clair et sombre : bascule vérifiée ; `circuit.png` visible en clair, `circuit-dark.png` en
  sombre, l'autre `display:none` (mesuré).
- Impression : `.jl-acc__visuel` masqué, les règles print existantes de `jl.css` (bloc E)
  couvrent `.jl-acc`, `.jl-chiffres`, `.jl-grille-3`, `.jl-outil`.
- Comparaison visuelle avec `https://justicelibre.org/` : même h1, même chapô, même bandeau de
  chiffres, même enchaînement Installation → Outils → Légalité → Combat → pied.

## À TRANCHER

1. **Quatre ou cinq tuiles de chiffres.** Le mandat dit « les 4 tuiles » mais énumère cinq
   valeurs (3 285 952 ; 1,75 M+ ; 107 273 ; 71 142 ; 0 €). Les cinq sont en place. Si tu veux
   quatre tuiles comme la prod, dis laquelle saute (0 € ? 71 142 ?).
2. **Casse du h1.** La prod met le h1 en capitales (`index.html:197`) et son `<em>` en teal non
   italique. La v2 garde la casse normale et l'italique serif, qui est la signature v2 demandée.
   À confirmer.
3. **Choix des 6 outils phares.** Retenus : les 3 moteurs de recherche les plus larges + les 3
   outils « article de loi à une date », qui portent l'argument Dalloz. Aucun outil « bientôt ».
   Remplaçables sur simple demande.
4. **Badge « MàJ » de l'endpoint.** La prod affiche la date du dernier déploiement en lisant
   `/version.json` (`index.html:797-807`). Non repris, car cela demanderait un script inline.
   Si tu le veux, il faut l'ajouter dans `jl.js` (interdit en écriture ici).
5. **Ko-fi.** Le bouton est dans la section « gratuit et légal », comme en prod. La prod
   l'aligne à droite (`index.html:640`), la v2 le laisse dans le flux.
