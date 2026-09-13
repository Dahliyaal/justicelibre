# Contre-audit des maquettes « Historique » (histo-02 Couloirs / histo-05 Poupées russes)

Auditeur neutre, lecture seule. Date : 13 septembre 2026.
Méthode : lecture du code actuel + rendu hors navigateur (Node `vm`, `fetch` simulé lisant `/home/dahl/justicelibre/web/hub_paysage_748.json`, DOM minimal) aux dates `aujourd'hui = 2026-09-13` (sans paramètre), `?date=2020-01-01` et `?date=2000-01-01`. Les six HTML produits ont été comptés au grep/regex. Le modèle (`loadHisto`) reste **rigoureusement identique** dans les deux fichiers (`diff` des blocs 266-525 / 265-524 : ne diffèrent que `linkArts` ajouté dans histo-05, la ligne du bouton de vue et les CSS de vue).

## 1) Verdict en cinq lignes

Les six constats G1 sont traités : les comptes faux sont réparés (**25 textes, 10 en vigueur** au 13/09, **13** au 01/01/2020), les prédécesseurs suivent enfin la date lue, « sera abrogé » remplace le faux passé, les bouchons rouges sont sur les deux arrêtés de niveau 1 morts, et « A remplacé **11** » est accompagné du stub « déjà listé plus haut (pris pour lui) » dans les deux vues.
Le choix assumé sur les deux « Arrêté du 7 avril 2009 » tient la route : NOR `JUSC0907573A` affiché sur les deux lignes, et le premier porte « **réécrit le 1er janv. 2020** » (état `q`) au lieu d'« abrogé » — c'est honnête, même si le compteur « 25 textes » compte toujours un arrêté deux fois.
G2 est corrigé pour l'essentiel (compteurs avant/après la date lue, classe `fut` bleue, ordre antichronologique partout, axe démarrant en 2008, renvoi « aussi pris pour lui (plus haut) », bandeau réécrit), mais reste partiel sur trois points (G2-1 total figé à 36, G2-3 grisage toujours inégal entre les deux vues, G2-5 sans renvoi retour).
G3 est le parent pauvre : seuls G3-1, G3-4, G3-5, G3-7, G3-8, G3-10 sont réglés ; G3-2 (micro-typo, empilement d'opacités), G3-3 (accessibilité des `g2mark`/`g2cap`/`g2notch`) et G3-9 (expression fragile) sont inchangés.
Aucune erreur JS au rendu aux trois dates, aucun lien vide, aucun texte affiché deux fois par accident — mais quatre régressions ou scories subsistent, dont un pluriel faux (« 4 article ») et un arrêté nommé nulle part ailleurs que dans une infobulle.

## 2) Constat par constat

### G1

| # | Statut | Preuve |
|---|---|---|
| G1-1 « 15 en vigueur » | **CORRIGÉ** | `histo-02.html:455` : `vivants: textesU.filter(t => t.st.k === 'ok').length` — calculé sur `textesU` (dédupliqué), plus sur `H.textes`. Affichage `histo-02.html:481` / `histo-05.html:480` : `${H.counts.textes} textes, ${H.counts.vivants} en vigueur à la date lue`. Rendu : **« 25 textes, 10 en vigueur à la date lue »** au 13/09/2026, **« 25 textes, 13 »** au 01/01/2020, « 25 textes, 0 » au 01/01/2000 — identique dans les deux vues. Le libellé « à la date lue » lève en plus l'ambiguïté. |
| G1-2 prédécesseurs figés `dead` | **CORRIGÉ** | `histo-05.html:571` : `<div class="p5acc lvl2${p.st.k === 'ok' ? '' : p.st.k === 'fut' ? ' fut' : ' dead'}"` et `:572` `${p.st.k === 'ab' ? '<span class="p5ab">…' : '<span class="st …">' + p.st.label}`. Rendu au 01/01/2020 : `p5acc lvl2 dead` = **3** (contre 13 avant), `p5ab` = **1**, `class="p5acc lvl2 fut"` = 2. L'**arrêté du 30 mars 2011 s'affiche `[lvl2] … JUST1108798A · en vigueur · 3 retouches`**, sans « abrogé » à côté. Au 13/09/2026 : `p5acc lvl2 dead` = 14 (13 prédécesseurs + le stub), `p5ab` = 12. Au 01/01/2000 : 13 blocs en `fut`. |
| G1-3 « abrogé » au passé pour un futur | **CORRIGÉ** | `histo-05.html:570` : `${a.fin <= H.at ? 'abrogé' : 'sera abrogé'} ${fmtCourt(a.fin)}` ; `histo-02.html:571` et `:581` idem pour les bouchons. Rendu au 01/01/2020 : l'arrêté du 28 août 2012 porte **« sera abrogé le 1er sept. 2025 · remplacé par Arrêté du 29 août 2025 »** et sa ligne n'est plus `dead` (`[n1]`). Occurrences de « sera abrogé » : 0 au 13/09, 12 au 01/01/2020, 15 au 01/01/2000 (Couloirs). |
| G1-4 deux « 7 avril 2009 » | **ASSUMÉ, et correctement signalé** | `histo-02.html:311` : `if (e.startsWith('MODIFIE')) return {k:'q', label: 'réécrit le ' + fmtCourt(d1), why:'Légifrance a ouvert un nouvel identifiant pour ce texte à cette date (même NOR) : la suite est sous l'autre entrée'}`. Rendu 13/09 : deux lignes `Arrêté du 7 avril 2009 · JUSC0907573A`, l'une « abrogé le 1er sept. 2025 · 1 retouche », l'autre « **réécrit le 1er janv. 2020** ». NOR affiché sur les deux (`histo-05.html:572`, `histo-02.html:583`). Le titre long dans le corps distingue bien « devant les tribunaux de grande instance ». Réserve chiffrée : `counts.textes = 25` compte toujours cet arrêté deux fois (cf. régression R-1). |
| G1-5 « A remplacé 10 » | **CORRIGÉ** | `histo-02.html:410` : `if (niveau1.has(e.de)) { P.deja = true; … out.push(P); continue; }` — le prédécesseur est désormais **poussé** puis marqué, au lieu d'être supprimé. Rendu : « **A remplacé 11** » et « a remplacé 11 » dans histo-05 ; stub présent **dans les deux vues** : histo-05 → `Arrêté du 28 août 2012 · JUST1233182A · déjà listé plus haut (pris pour lui)` (`histo-05.html:571`) ; histo-02 → `remplacé par l'arrêté du 29 août 2025 · déjà listé plus haut (pris pour lui)` (`histo-02.html:580`). Une occurrence chacune, aux trois dates. |
| G1-6 bouchon rouge absent sur les n1 morts | **CORRIGÉ** | `histo-02.html:571` : `const capA = a.fin < '2999' ? '<div class="g2cap" …>' : ''`, inséré ligne 574. Rendu 13/09 : `g2cap` = **15** (13 prédécesseurs + 2 arrêtés de niveau 1). Par ligne : `[n1 dead] Arrêté du 12 mars 2013 → cap « abrogé le 26 janv. 2017 · remplacé par Arrêté du 20 janvier 2017 »` et `[n1 dead] Arrêté du 28 août 2012 → cap « abrogé le 1er sept. 2025 · remplacé par Arrêté du 29 août 2025 »`. Les deux `[n1]` vivants n'ont pas de bouchon, ce qui est juste. |

### G2

| # | Statut | Preuve |
|---|---|---|
| G2-1 compteurs indépendants de la date | **PARTIELLEMENT** | `histo-02.html:452-455` ajoute `avant`/`apres`, affichés `:480` : `${H.counts.avant} avant la date lue}, ${H.counts.apres} après`. Rendu : 13/09 → `avant 36, apres 0` (mention masquée car `isToday`) ; 01/01/2020 → **« 36 · 4 article · 6 arrêtés · 26 retouches et prédécesseurs · 14 avant la date lue, 22 après »** (conforme à la cible) ; 01/01/2000 → « 0 avant la date lue, 36 après ». Mais le **total reste 36 à toutes les dates** et `n0/n1/n2` = 4/6/26 partout : le gros chiffre en gras ne bouge toujours pas. |
| G2-2 futur rendu comme mort | **CORRIGÉ** | `histo-02.html:558` : `const clsOf = st => st.k === 'ok' ? '' : st.k === 'fut' ? ' fut' : ' dead'`, avec `.g2row.fut .g2name{color:var(--doc)}` et `.g2bar.fut{background:var(--doc)}` (`:543`). Rendu au 01/01/2020 : `g2row n1 fut` = **2** (29 août 2025, 9 mars 2020) et `g2row n1 dead` = 1 (12 mars 2013) ; au 01/01/2000 : `g2row n1 fut` = 4, `dead` = 0. En Poupées russes, `class="p5acc lvl2 fut"` = 2 au 01/01/2020 et 13 au 01/01/2000, avec `.p5acc.fut>.p5h .p5ttl{color:var(--doc)}` (`histo-05.html:534`). Les textes futurs sont bien en bleu. |
| G2-3 grisage « après la date lue » inégal | **PARTIELLEMENT** | La promesse est réécrite et désormais tenable : `histo-02.html:491` dit « ce qui n'existe pas encore à cette date est en bleu (« entre en vigueur le … ») et atténué » — et « entre en vigueur le » est bien présent dans le HTML produit. Mais le grisage `jl-hfutur` reste inégal entre les deux vues : au 01/01/2020, **7 dans Couloirs et 7 dans Poupées russes** (égalisé, c'était 7/6) ; au 01/01/2000, **13 dans Couloirs contre 15 dans Poupées russes** (histo-05 marque en plus les 4 segments de la frise de l'article et les 4 blocs de rédaction, `histo-05.html:560-561`). La mention littérale « après la date lue » n'apparaît toujours nulle part dans le corps. |
| G2-4 ordres opposés | **CORRIGÉ** | `histo-02.html:569` : `for (const a of H.arretes.slice().reverse())` — comme `histo-05.html:598` `H.arretes.slice().reverse().map(arr)`. Retouches : `histo-02.html:585` et `:588` `a.retouches.slice().reverse()`, `histo-05.html:577` idem. Prédécesseurs : tri commun `histo-02.html:412` `(y.debut||'').localeCompare(x.debut||'')`. Rendu Couloirs 13/09 : 29 août 2025 → 9 mars 2020 → 12 mars 2013 → 28 août 2012 ; même ordre dans Poupées russes. Antichronologique partout. |
| G2-5 le 29 août 2025 à deux places | **PARTIELLEMENT** | `histo-02.html:402` ajoute `R.aussiNiveau1 = niveau1.has(t.legitext)` et `:576` / `histo-05.html:578` affichent `${r.aussiNiveau1 ? ' · aussi pris pour lui (plus haut)' : ''}`. Rendu : la mention apparaît **1 fois** dans chaque vue, aux trois dates. Mais le renvoi est à sens unique : le bloc propre du 29 août 2025 affiche toujours `Arrêté du 29 août 2025 · aucune retouche · a remplacé 11 · en vigueur` puis « Jamais retouché. » (`histo-05.html:580`), sans dire qu'il figure aussi comme retouche du 9 mars 2020. |
| G2-6 décret modificateur inexpliqué | **CORRIGÉ** | `histo-02.html:490` / `histo-05.html:489` : « Un décret peut retoucher un arrêté (le décret 2019-966 a remplacé « tribunal de grande instance » par « tribunal judiciaire » dans des centaines de textes) : il apparaît alors comme « décret modificateur ». » Plus l'infobulle par ligne : `histo-02.html:576` / `histo-05.html:578` `title="${r.nature === 'DECRET' ? 'Un décret peut modifier un arrêté : il lui est supérieur.' : ''}"`. |
| G2-7 phrase cassée + article fermé | **CORRIGÉ** | `histo-05.html:591` et `:612`, verbatim identiques : « …chacun avec les siens (2025 › 2020 › 2010). **L'article et ses arrêtés sont ouverts ; les arrêtés remplacés se déplient à la demande.** » — plus de bout orphelin. Et `histo-05.html:594` : `<div class="p5acc lvl0 open" data-acc>` — rendu : `p5acc lvl0 open` = 1, le bloc de l'article est ouvert au chargement. (Les 4 sous-blocs de rédaction, `lvl1 p5red`, restent fermés : conforme à la phrase, qui ne les promet pas.) |
| G2-8 les 6 exclus « hors sujet » | **CORRIGÉ (rédactionnel)** | `histo-02.html:488-489` : « **6 arrêtés reliés par un lien sortant, hors sujet, non affichés** : … **Ces textes ne sont là que parce qu'un texte retenu les modifie au passage ; ils ne relèvent pas de l'article.** » La justification manquante est écrite. Le calcul est inchangé (`:430` `if (kept.has(e.vers) && !kept.has(e.de))`), `counts.exclus = 6` aux trois dates. |
| G2-9 axe à 2005 + écrasement des bornes | **PARTIELLEMENT** | `histo-02.html:555` : `const Y0 = 2008, Y1 = 2027` (plus de trois années vides ; la légende `:591` explique « L'axe commence à la première rédaction de l'article (2008) ; le décret qui l'a créé date du 28 décembre 2005 »). Mais le clamp est intact — `histo-02.html:557` `Math.min(Math.max(y, Y0), Y1)`. Le palliatif est la classe `inf` : `:574` `${a.fin >= '2999' ? ' inf' : ''}` avec `.g2bar.inf::after` en pointe (`:544`), qui distingue « sans limite » d'une fin en 2027. Le cas inverse (un texte né avant 2008) reste écrasé sans marque. |
| G2-10 page pleine à une date où l'article n'existe pas | **PARTIELLEMENT** | Rendu au 01/01/2000 : aucune exception, `H.cur = null`, « n'existe pas encore » présent 2 fois dans chaque vue, tous les textes en `fut` bleu, et « 0 avant la date lue, 36 après ». La cohérence est donc bien meilleure. Mais la page affiche toujours « **36** » en gros, « Rédactions **4** depuis 1er juil. 2008 » et « 25 textes » sous un badge « lu au 1er janv. 2000 ». |

### G3

| # | Statut | Preuve |
|---|---|---|
| G3-1 segments illisibles | **CORRIGÉ** | `histo-02.html:541` : `.g2seg{background:var(--ok-bg);color:var(--ok);opacity:1}` — fond vert clair, texte vert plein, opacité 1 par défaut ; le sélectionné passe à `background:var(--ok);color:#fff` + `outline` (`:542`). |
| G3-2 micro-typographie et opacités empilées | **NON CORRIGÉ** | `histo-02.html:534` `.g2name .s{…font-size:9.5px}` ; `:551` `.g2todayL{…font-size:9.5px}` ; `:116` `.how{…font-size:9.5px}` ; `:205` `.bt{…9.5px}` ; `histo-05.html:548` `.p5seg{…font-size:10px}` ; `histo-05.html:577` `${apres(H, r.date_texte) ? ';opacity:.35' : ''}` ; et `histo-02.html:236 = histo-05.html:236` `.jl-hfutur{opacity:.32;filter:grayscale(1)}`. Rien n'a bougé. |
| G3-3 accessibilité des éléments de survol | **PARTIELLEMENT** | `histo-02.html:567` ajoute `role="button" tabindex="0" aria-label="rédaction du …"` sur les `g2seg` (rendu : `role="button"` = 4, `tabindex` = 6). Mais `g2mark` (`:577`), `g2cap` (`:571`, `:581`) et `g2notch` (`:572`, `:582`) n'ont toujours ni `role`, ni `tabindex`, ni `aria-label` ; le panneau `#g2tip` reste alimenté par `onmouseenter` seul (`:608`). |
| G3-4 clic muet sur un segment déjà choisi | **CORRIGÉ (sauf cas limite)** | `histo-02.html:614` : `if (pick.includes(i)) { if (pick.length > 1) pick = pick.filter(x => x !== i); else return; }` — le clic déselectionne désormais. Il reste muet quand un seul segment est sélectionné. |
| G3-5 « signé le » sans garde | **CORRIGÉ** | `histo-02.html:607` : `${t.date_texte ? '<span>signé le ' + fmtCourt(t.date_texte) + '</span>' : ''}`. Rendu : aucune occurrence de « signé le » vide dans les six HTML. Reste non gardé le titre d'encoche `:572` `title="retouché par … (${fmtCourt(r.date_texte)})"` (aucun cas dans ce jeu de données). |
| G3-6 « abrogé sans limite » amorcé | **CORRIGÉ** | `histo-05.html:572` n'utilise plus `fmtCourt(p.fin)` mais l'étiquette d'état : `${p.st.k === 'ab' ? '<span class="p5ab">' + esc(p.st.label) + '</span>' : …}`, et `lifeAt` (`histo-02.html:308-313`) ne produit « abrogé le … » que si `d1 <= at`, donc jamais pour 2999. |
| G3-7 « 0 retouche » | **CORRIGÉ** | `histo-02.html:317` : `nb = (n, un, plus) => n === 0 ? 'aucun' + (un.endsWith('e') ? 'e' : '') + ' ' + un : …`, employé `histo-05.html:584`. Rendu : « 0 retouche » = 0 occurrence ; « aucune retouche » = 2 (arrêtés du 29 août 2025 et du 12 mars 2013). |
| G3-8 « Textes en jeu » sans infobulle | **CORRIGÉ** | `histo-02.html:481` / `histo-05.html:480` : `Textes en jeu <span class="help" tabindex="0" data-tip="Tous les textes affichés sur cette page, comptés une seule fois : l'article, les arrêtés pris pour lui, leurs retouches et leurs prédécesseurs. « En vigueur » s'entend à la date lue.">?</span>`. |
| G3-9 expression fragile de la frise | **NON CORRIGÉ** | `histo-05.html:560` toujours : `R === (H.cur && H.redactions.find(x => x.v === H.cur))`. Elle fonctionne : `p5seg art cur` = 1 au 13/09 et au 01/01/2020, 0 au 01/01/2000. À noter que la ligne voisine `:561` a, elle, été écrite proprement (`H.cur && R.v === H.cur`) : les deux formes cohabitent à une ligne d'écart. |
| G3-10 le 2 mai 2018 cité deux fois | **CORRIGÉ** | Rendu : « 2 mai 2018 » = **1 occurrence** dans chaque HTML (la liste des exclus). Le bandeau `histo-02.html:490` a remplacé l'exemple Télérecours par l'explication du décret 2019-966. |

**Bilan : 15 CORRIGÉS · 6 PARTIELS · 4 NON CORRIGÉS (G3-2, G3-9, + G2-1 et G2-10 comptés partiels) · 1 ASSUMÉ (G1-4).**
Détail : corrigés = G1-1, G1-2, G1-3, G1-5, G1-6, G2-2, G2-4, G2-6, G2-7, G2-8, G3-1, G3-4, G3-5, G3-6, G3-7, G3-8, G3-10 (17 lignes, dont G3-4 et G3-5 avec un cas limite résiduel) ; partiels = G2-1, G2-3, G2-5, G2-9, G2-10, G3-3 ; non corrigés = G3-2, G3-9 ; assumé = G1-4.

## 3) Régressions et scories introduites ou laissées par les corrections

| # | Rang | Constat | Preuve |
|---|---|---|---|
| R-1 | G1 | **« 25 textes » compte un arrêté deux fois.** Le choix assumé (deux entrées pour le 7 avril 2009) n'a pas été répercuté sur le compteur : `histo-02.html:451` `textesU = [...new Map(textes.map(t => [t.id, t])).values()]` déduplique par `LEGITEXT`, pas par NOR/CID. Il y a donc **24 arrêtés réels affichés comme 25**, et le lecteur qui compte les lignes trouvera bien deux « Arrêté du 7 avril 2009 · JUSC0907573A ». Aucune note de bas de page n'en avertit. | Rendu 13/09 : `counts.textes = 25`, `H.textes` = 30 entrées / 25 ids ; deux blocs `lvl2` portant le même titre **et le même NOR**. |
| R-2 | G1 | **« Arrêté du 20 janvier 2017 » est nommé alors qu'il n'existe nulle part sur la page.** La correction G1-6 a fait apparaître, dans l'infobulle du nouveau bouchon du 12 mars 2013, un texte qui n'est ni dans les 25 textes en jeu, ni dans les 6 exclus (le calcul des exclus, `histo-02.html:430`, ne retient que `kept.has(e.vers) && !kept.has(e.de)`, or ici c'est `e.de` qui est retenu). Le lecteur ne peut ni le cliquer ni le retrouver. | Rendu : « 20 janvier 2017 » = **1 occurrence** dans chaque HTML, uniquement dans `title=` du `g2cap` ; absente de la liste des exclus et des lignes de texte. |
| R-3 | G2 | **Le grisage du futur diverge encore entre les deux vues, et davantage qu'avant à date ancienne.** Au 01/01/2020 les deux vues sont enfin à égalité (7 / 7), mais au 01/01/2000 Couloirs marque **13** éléments `jl-hfutur` et Poupées russes **15** — histo-05 marque en plus les 4 segments de la frise de l'article et les 4 blocs de rédaction (`histo-05.html:560` et `:561`), que Couloirs ne marque pas (ses segments `g2seg`, `histo-02.html:566-567`, n'ont aucune classe `jl-hfutur`). Deux vues, deux périmètres de grisage. | Comptes `jl-hfutur` : 0/0 au 13/09, 7/7 au 01/01/2020, **13/15** au 01/01/2000. |
| R-4 | G3 | **Pluriel faux dans le compteur d'événements : « 4 article ».** `histo-02.html:480` / `histo-05.html:479` écrivent `${H.counts.n0} article` en dur, sans passer par l'helper `nb()` qui vient pourtant d'être introduit pour G3-7. Affiché à toutes les dates, à côté de « 6 arrêtés » correctement accordé. | Rendu : « 4 article » = 1 occurrence dans chacun des 6 HTML ; verbatim « 36 · **4 article** · 6 arrêtés · 26 retouches et prédécesseurs ». |
| R-5 | G3 | **Le texte « réécrit le … » est rendu comme un texte mort.** `histo-05.html:571` traite tout état ≠ `ok`/`fut` comme ` dead` (grisé, `.p5acc.dead .p5h{opacity:.6}`), et `histo-02.html:558` `clsOf` fait de même (` dead`, barre `--muted`). L'entrée `JUSC0907573A` « réécrit le 1er janv. 2020 » est donc visuellement identique à un arrêté abrogé, alors que la correction assumée visait précisément à ne pas l'assimiler à une abrogation : la formulation a changé, pas le codage couleur. | Rendu 13/09 : `[lvl2 dead] Arrêté du 7 avril 2009 · JUSC0907573A · réécrit le 1er janv. 2020` — même classe que les 12 voisins réellement abrogés. |
| — | — | **Points contrôlés sans anomalie** : aucune erreur JS aux trois dates dans aucune des deux vues (le harnais capte `console.error` et l'exception de `loadHisto`) ; aucun lien `legifrance.gouv.fr/` de repli (0 occurrence) ; aucun texte dupliqué par accident (le seul doublon est le 7 avril 2009, assumé, et le stub « déjà listé plus haut », voulu) ; `p5seg art cur` = 1 aux dates où l'article existe, 0 au 01/01/2000 ; « aucune retouche » correctement accordé ; le stub apparaît une seule fois par vue. | — |

## 4) Comptes mesurés aux trois dates

Identiques dans les deux vues sauf mention contraire (le modèle est le même code).

| Grandeur | 2026-09-13 (sans paramètre) | 2020-01-01 | 2000-01-01 |
|---|---|---|---|
| `counts.total` | 36 | 36 | 36 |
| `n0` / `n1` / `n2` | 4 / 6 / 26 | 4 / 6 / 26 | 4 / 6 / 26 |
| `counts.avant` / `counts.apres` | 36 / 0 (masqué) | **14 / 22** | 0 / 36 |
| `counts.textes` (ids uniques) | 25 | 25 | 25 |
| entrées de `H.textes` | 30 | 30 | 30 |
| `counts.vivants` **affiché** | **10** | **13** | 0 |
| `counts.exclus` | 6 | 6 | 6 |
| `H.cur` | 2025-09-01 | 2019-05-05 | `null` (aucune exception) |
| phrase « Textes en jeu » | « 25 textes, 10 en vigueur à la date lue » | « 25 textes, 13 en vigueur à la date lue » | « 25 textes, 0 en vigueur à la date lue » |
| `g2cap` (Couloirs) | **15** | 15 | 15 |
| `g2row n1 dead` / `g2row n1 fut` (Couloirs) | 2 / 0 | **1 / 2** | 0 / 4 |
| « sera abrogé » (Couloirs) | 0 | 12 | 15 |
| `p5acc lvl2 dead` / `p5ab` (Poupées) | 14 / 12 | **3 / 1** | 1 / 0 |
| `p5acc lvl2 fut` (Poupées) | 0 | 2 | 13 |
| `jl-hfutur` (Couloirs / Poupées) | 0 / 0 | 7 / 7 | **13 / 15** |
| « A remplacé » / « a remplacé 11 » (Poupées) | 11, 2, 1 | idem | idem |
| « déjà listé plus haut (pris pour lui) » | 1 / 1 | 1 / 1 | 1 / 1 |
| « 2 mai 2018 » | 1 | 1 | 1 |
| « aussi pris pour lui (plus haut) » | 1 | 1 | 1 |
| « 4 article » | 1 | 1 | 1 |
| longueur du HTML produit (02 / 05) | 54 178 / 53 910 | 54 577 / 54 676 | 54 783 / 55 344 |

Contrôles ciblés demandés, tous vérifiés :
- « Textes en jeu : 25 textes, 10 en vigueur » au 13/09/2026 et **13** au 01/01/2020 → **OK**.
- « 14 avant la date lue, 22 après » au 01/01/2020 → **OK**, verbatim.
- Stub « déjà listé plus haut (pris pour lui) » pour le 28 août 2012 sous le 29 août 2025, **dans les deux vues**, et « A remplacé 11 » → **OK**.
- Arrêté du 30 mars 2011 « en vigueur » au 01/01/2020 dans les poupées russes, sans « abrogé » à côté → **OK** (`[lvl2] … JUST1108798A · en vigueur · 3 retouches`).
- Bouchons rouges sur les 2 arrêtés de niveau 1 morts dans les couloirs → **OK** (`g2cap` 13 → 15, ventilés ligne par ligne).
- Textes futurs en bleu (classe `fut`) et non gris → **OK** dans les deux vues.
- Ordre antichronologique partout → **OK** (arrêtés, retouches, prédécesseurs).
- Bloc de l'article ouvert au chargement → **OK** (`p5acc lvl0 open`).
- Phrase de présentation réparée → **OK** (verbatim identique lignes 591 et 612 de histo-05).
- Segments de rédaction lisibles (`ok-bg` / `ok`) → **OK** (`histo-02.html:541`).
- « sera abrogé le … » quand la date lue précède l'abrogation → **OK** (12 occurrences au 01/01/2020).

## 5) INVÉRIFIABLE

- **Le rendu visuel réel.** Toujours pas de navigateur : contraste effectif du couple `--ok-bg`/`--ok` (G3-1 déclaré corrigé sur la foi du CSS seul), lisibilité des 9,5 px, chevauchement des losanges proches sur l'axe, `position:sticky`, `overflow-x:auto`, effet cumulé de `.jl-hfutur{opacity:.32;filter:grayscale(1)}` sur une ligne déjà `--muted`. Le jugement « textes futurs en bleu » repose sur la présence de la classe `fut` et sur `.g2bar.fut{background:var(--doc)}`, non sur un pixel observé.
- **Les interactions.** `wireDate`, `WIRE`, le bouton « tout déplier », la bascule de date, le surlignage `[data-r].hl`, les `title=` et `.help::after` : le code est lu, aucun n'a été actionné (le harnais Node fournit un DOM minimal dont les `querySelectorAll` renvoient des listes vides). Une erreur de câblage purement DOM m'aurait échappé — en particulier pour G3-3 et G3-4, dont le verdict est tiré du seul code.
- **L'exactitude juridique des données LEGI.** Je n'ai vérifié que la cohérence page ↔ `hub_paysage_748.json`. L'identité « même CID, même NOR ⇒ même arrêté » pour les deux « 7 avril 2009 » reste une inférence issue du JSON, non une vérification sur Légifrance ; le choix assumé n'est donc validé que dans sa cohérence interne. De même, je ne peux pas dire si « Arrêté du 20 janvier 2017 » (R-2) abroge réellement celui du 12 mars 2013.
- **La cohérence avec `carte-748.html`** et avec les trois autres maquettes d'historique n'a pas été mesurée : une correction ici a pu désaligner un chiffre là-bas.
- **Le serveur `localhost:8787`** n'a pas été sollicité.
