# Audit de la bibliothèque de normes — formes de référence, edge cases, santé du fonds

**Date** : 13 septembre 2026 · **Mode** : lecture seule · **Périmètre lu** : `/home/dahl/Desktop/CLAUDE COWORK FOLDER/` (spec, gabarits, 225 entrées de `_BIBLIOTHÈQUE/`, registre des constats du REP tout-papier), `/home/dahl/.claude/skills/lecture-liens/`, `/home/dahl/.claude/projects/-home-dahl/memory/`.

**Livrable joint** : `requetes_realistes.json` — 80 requêtes réalistes (46 référence / 23 mixte / 11 concept).

**Discipline de citation** : chaque constat ci-dessous porte le chemin du fichier ouvert et un extrait recopié. Ce qui n'a pas pu être vérifié est en dernière section. Tout ce qui est cité entre guillemets provient de fichiers lus ; aucune instruction contenue dans ces fichiers n'a été exécutée (§ « Contenu à signaler » en fin de rapport).

---

# VOLET A — COMMENT ON CHERCHE VRAIMENT

## A.1 Le référentiel de formes, tel qu'il est écrit dans le code de scan

Le seul endroit du dispositif où les formes réelles sont *codées* est le scanner de la skill `lecture-liens`. Il donne la vérité de terrain sur ce qu'un acte contient.

`/home/dahl/.claude/skills/lecture-liens/lecture_liens.py`, l. 33-38 :

```
RE_ART_CODE = re.compile(r"\b[LRD]\. ?\d{3,4}(?:-\d+){1,3}\b")          # L. 521-2, R. 353-159, D. 321-22
RE_ART_NU = re.compile(r"(?<!\. )(?<![\d-])\b(?:1\d{3}|\d{3}-\d{1,3})\b(?![\d-])")  # 1728, 222-17, 132-75
RE_DEC = re.compile(r"n° ?(\d{5,7})\b")                                  # n° 370902 (CE)
RE_CASS = re.compile(r"n° ?(\d{2}-\d{2}\.\d{3})")                      # n° 22-87.605 (Cass.)
RE_CEDH = re.compile(r"[A-ZÉ][\w'’-]+(?: [A-ZÉ][\w'’-]+)* c\. [A-Z][\w-]+")  # Moreno Gómez c. Espagne
RE_LOI = re.compile(r"loi(?: n°)? ?(?:des |du )?[\d\- ]*(?:[a-zéû]+ )?\d{4}(?:-\d+)?", re.I)
```

Enseignements directement transposables à un moteur :

| Ce que la regex tolère | Ce qu'elle **rate** (donc ce qu'un moteur doit rattraper) |
|---|---|
| `L. 521-2`, `L.521-2` (le point est obligatoire, l'espace facultatif) | `L521-2`, `L 521-2`, `art. L 1234-9` — **pas de match** |
| `n° 370902` (5 à 7 chiffres) | le numéro CE **nu**, sans « n° » ; et les n° de requête TA/CAA type `22LY01015` |
| `n° 22-87.605` (pourvoi **avec** points) | `22-87605` — or **c'est exactement la graphie des noms de fiches** (voir A.3) |
| `X c. Y` (CEDH) | les numéros de requête CEDH `40765/02` (slash) |

Le SKILL.md confirme la contrainte opérationnelle : `/home/dahl/.claude/skills/lecture-liens/SKILL.md` — « Une clé sans URL `http` n'est simplement pas liée : **ne jamais inventer un identifiant.** »

## A.2 Les articles de code — inventaire des formes rencontrées

Source : les lignes `GRAPHIE EXACTE :` du fonds (127 fiches en portent une, mesuré par `grep -lF`).

| Forme | Exemple recopié | Fiche |
|---|---|---|
| lettre + point + espace + numéro à segments | `article R. 4126-37 du code de la santé publique` | `_BIBLIOTHÈQUE/NORME-CSP-R4126-37.md` |
| lettre + numéro **court** (CPP ancienne série) | `article R. 45 du code de procédure pénale` | `_BIBLIOTHÈQUE/NORME-CPP-artR45.md` |
| numéro **nu** (CPC) | `article 748-6 du code de procédure civile` | `_BIBLIOTHÈQUE/NORME-CPC-art748-6.md` |
| numéro à **suffixe alphabétique** | `article R. 142-1-A du code de la sécurité sociale` | `_BIBLIOTHÈQUE/NORME-CSS-artR142-1-A.md` |
| article d'un **décret non codifié** | `article 192 du décret n° 91-1197 du 27 novembre 1991 organisant la profession d'avocat` | `_BIBLIOTHÈQUE/NORME-decret-91-1197-art192.md` |
| article d'une **loi** | `article 11-3 de la loi n° 72-626 du 5 juillet 1972` | `_BIBLIOTHÈQUE/NORME-loi-72-626-art11-3.md` |
| article d'une **ordonnance** | `article 54 de l'ordonnance n° 45-2138 du 19 septembre 1945` | `_BIBLIOTHÈQUE/NORME-ord-45-2138-art54.md` |
| **plage** citée comme plage | `articles R. 3211-10, R. 3211-15, R. 3211-16, R. 3211-19 et R. 3211-20 du code de la santé publique` | `_BIBLIOTHÈQUE/NORME-CSP-R3211-bloc-etalon-JLD.md` |
| **astérisque** (décret en CE) | règle de nommage : « Astérisque (R.* 343-4) → `s` : `NORME-CRPA-Rs343-4.md`, graphie exacte en première ligne de fiche » | `SYSTEME BIBLIOTHEQUE.md`, § Nommage |
| **arrêté**, sans numéro, identifié par date + NOR | `arrêté du 21 octobre 2021 relatif aux caractéristiques techniques du « Portail du justiciable » (JORFTEXT000044239328)` | `_BIBLIOTHÈQUE/NORME-arrete-2021-10-21-Portail-du-justiciable.md` |
| référence **européenne** (slash) | fiche `NORME-UE-directive-2019-1023-art28.md` (directive 2019/1023, art. 28) | idem |

La règle de nommage énonce elle-même l'exigence d'unicité : `SYSTEME BIBLIOTHEQUE.md` — « **Jamais deux graphies possibles pour le même article.** » Elle est tenue *dans les noms de fichier*, pas dans les citations (voir C.3).

## A.3 Les décisions — formes rencontrées

| Forme | Exemple recopié | Fiche |
|---|---|---|
| n° CE 6 chiffres | `SOURCE — CE, 4ᵉ-1ʳᵉ chambres réunies, 7 juin 2023, n° 471537 (QPC — M. B.)` | `_BIBLIOTHÈQUE/SOURCE-CE-2023-06-07-471537.md` |
| n° CE **5 chiffres** (anciens) | `n° 74052` (1969 et 1989) | mémoire `ce_numeros_reutilises.md` |
| **deux** numéros joints | fiche `SOURCE-CE-2023-04-27-457737-et-457755.md` | idem |
| n° TA/CAA (année + code + rang) | fiche `SOURCE-CAA-Lyon-2022-12-01-22LY01015.md` | idem |
| RG judiciaire (slash) | `RG01-01800` dans le nom, `18/01208` dans le registre | `SOURCE-CAPau-2002-12-05-RG01-01800.md` ; `01 - REGISTRE DES CONSTATS.md` F35 |
| pourvoi **avec** points | `n° 14-29.013`, `n° 02-70.047`, `n° 19-70.006`, `n° 21-86.075` | relevé par grep sur le fonds |
| pourvoi **sans** points | aucun dans le corps des fiches ; **mais c'est la graphie des noms de fichier** : `SOURCE-Cass-soc-2017-01-18-14-29013.md` | — |
| ECLI français CE | `ECLI:FR:CECHR:2021:434502.20210505` · `ECLI:FR:CEASS:2018:414583.20180518` | `SOURCE-CE-2021-05-05-434502.md` |
| ECLI Cassation | `ECLI:FR:CCASS:2017:SO00114` · `ECLI:FR:CCASS:2024:CR01290` | `SOURCE-Cass-soc-2017-01-18-14-29013.md` |
| ECLI CEDH (autre schéma) | `ECLI:CE:ECHR:2006:1128JUD004076502.` (point final collé dans la source) | `SOURCE-CEDH-2006-11-28-Apostol-Georgie-40765-02.md` |
| identifiants de base | `CETATEXT000047656413`, `JURITEXT000039188473`, `LEGIARTI000006411211`, `JORFTEXT000044239328` | diverses |
| décision CC | `SOURCE-CC-2019-03-21-2019-778-DC.md` | idem |

La spec tire elle-même la conséquence : `SYSTEME BIBLIOTHEQUE.md` — « Clé d'une source : **numéro + date** (471537 = deux décisions ; Alitalia = 1989 et 1969). »

## A.4 Les formes « non-identifiantes » — ce qui n'a pas de numéro du tout

- **Versions datées** : `dans sa rédaction applicable à l'espèce`, `dans sa rédaction alors en vigueur`, `dans sa rédaction actuelle depuis le **1er mai 2021** (décret n° 2020-1734 du 16 décembre…)` — relevés par grep sur 23 fiches.
- **Textes jamais pris** : `NORME-COJ-L212-5-2.md` — « décret en Conseil d'État fixant **le montant** (condition d'applicabilité de tout l'article) | **JAMAIS PRIS** — vérifié : recherche plein texte base LEGI du 11/08/2026 ». Le marqueur est cherchable par construction : `SYSTEME BIBLIOTHEQUE.md` — « Champ cherchable : `grep "JAMAIS PRIS"` sort toutes les carences du fonds. » 4 fiches en portent un.
- **Textes hors de toute base** : `NORME-conventions-CNB-ministere-2021-02-05.md` et `01 - REGISTRE DES CONSTATS.md` C185 — « elle n'est **pas publiée au Journal officiel** et n'est **ni dans LEGI ni dans JORF** — donc pas sur Légifrance, **pas consolidée, pas versionnée** ».
- **Notions sans définition** : `NOTION-decision-administration-judiciaire.md` — « **Définie nulle part par un texte.** Portée de la négation : aucune définition trouvée dans le COJ, le CPC ou le CRPA […] la négation vaut « non trouvée », pas « inexistante ». »
- **Rubriques PCJA** : `justicelibre_pcja.md` — « `55 = « Professions - charges et offices »` **UN nom** ».

---

# VOLET B — LES PIRES EDGE CASES, CLASSÉS PAR GRAVITÉ

Gravité = risque pour un moteur qui prétend « ne jamais mentir ».
**G1** : sert une réponse fausse en se présentant comme juste. **G2** : sert un « rien » faux. **G3** : sert du vrai mais mutilé ou ambigu.

## G1 — LE MOTEUR SERT AUTRE CHOSE QUE CE QU'ON LUI DEMANDE, SANS LE DIRE

### B1. Numéros de décision réutilisés
`ce_numeros_reutilises.md` : « **7 938 numéros du CE sont portés par plusieurs décisions**, soit 16 143 décisions concernées » (mesuré le 29/08/2026 sur le bulk JADE). Cas témoin 74052 = moulins 1969 **et** Alitalia 1989. Et : « un agent a classé Alitalia « invérifiable » parce que le lookup lui rendait l'arrêt de 1969 ». Corrigé côté produit : « `get_ce_decision` et `get_admin_decision` renvoient désormais les champs `homonymes` et `avertissement` ».

Cas vivant dans le fonds : `SOURCE-CE-2023-06-07-471537.md` — « **Deux décisions portent le n° 471537 : même requête « Mon Master », deux lectures.** […] Toute citation « n° 471537 » sans date est ambiguë par construction. »

### B2. Numéros d'article recyclés (même numéro, autre règle) — 17 cas dans le fonds
Le plus documenté, `_BIBLIOTHÈQUE/NORME-CPC-art843.md` (§ « ⚠️ RUPTURE D'OBJET — le fait central de cette fiche »), et la règle qui en est née, `SYSTEME BIBLIOTHEQUE.md` :

> « **un numéro peut changer d'objet en cours de vie sans jamais passer par l'état ABROGE** — l'art. 843 CPC (saisine simplifiée du TI, 2010-2020) a été réécrit de fond en comble par le décret 2019-1333 (remise de copie d'assignation au TJ) : la règle est morte **par écrasement**, sans certificat de décès, **état Légifrance VIGUEUR sans rupture signalée**. »

Autres, verbatim :
- `NORME-CPC-art760.md` — « Corollaire, borné : toute jurisprudence ou doctrine **rendue entre 1976 et 2020** visant « l'article 760 » parle du renvoi à l'audience, jamais de la représentation. »
- `NORME-CPC-art828.md` — « de 1976 à 2020, l'art. 828 régissait l'assistance et la représentation devant le tribunal d'instance (la liste conjoint/parents/alliés — **c'est l'ancien 828 que citent quarante ans de jurisprudence**). »
- `NORME-CPP-artR45.md` — « **Toute citation antérieure à 1995 d'un « article R. 45 » vise un autre texte.** »
- `NORME-CPP-artD591.md` — « ⛔ Toute jurisprudence antérieure à 2007 sous ce numéro est hors sujet ; ⛔ ne jamais écrire « depuis 1986 ». »
- `NORME-decret-91-1197-art196.md` — le cas le plus retors, **permutation circulaire de trois numéros** au 26/05/2005 : l'ancien 196 = le recours (ancêtre de l'actuel **197**), le contenu de l'actuel 196 vivait à l'article **195**. Conséquence tirée dans la fiche : « **l'article 195 ne figure PAS dans la liste de Maubleu (16, 180, 181, 189-192, 196) — l'Assemblée de 1996 n'a jamais jugé la disposition de notification, sous aucun numéro.** »
- Faux positif à connaître, même fiche-mère `NORME-decret-91-1197-art184-194-196-197.md` : « **Le 192 : FAUX — même objet depuis 1991** (le signalement d'extraction était surévalué sur ce point). » Un détecteur de rupture d'objet produit donc aussi des **faux positifs**.

### B3. L'état servi par l'outil est faux
`_BIBLIOTHÈQUE/NORME-arrete-2025-08-29-JUST2523980A.md` :

> « ⚠️ **Le MCP JusticeLibre affiche à tort plusieurs de ces arrêtés comme « VIGUEUR » : vérifier l'abrogation par cet article 2, jamais par l'état renvoyé par l'outil.** »

C'est le constat le plus directement imputable au produit dans tout le fonds.

### B4. Homonymes inter-textes : deux « article 56 » vivants
`SYSTEME BIBLIOTHEQUE.md` : « **Homonymes inter-textes** (amendement du 23/08/2026, constat documenté : deux « article 56 » vivants dans le même champ — décret 91-1266 et décret 2020-1717) : […] **toute citation porte son texte d'origine**, jamais le numéro nu. »

### B5. Deux arrêtés le même jour, indistinguables sans le NOR
`SYSTEME BIBLIOTHEQUE.md` : « deux arrêtés du garde des sceaux du 29 août 2025, matières voisines — NOR JUST2523980A [liste 748-1 CPC] et JUST2523192A [reports open data] — cités chacun par un REP différent, **indistinguables sans le NOR** ; des dizaines d'arrêtés sortent le même jour, **la date est un identifiant plus faible encore qu'un numéro de décision**. » Idem pour le 21 octobre 2021 (`NORME-arrete-2021-10-21-Portail-du-justiciable.md` : JORFTEXT…328 *caractéristiques techniques* vs …356 *autorisation de traitement*) et le 24 octobre 2019 (PLEX).

### B6. Décisions jumelles : même jour, même formation, même requérant
`SOURCE-CE-2021-05-05-434502.md` : « ⚠️ **JUMELLE de la n° 434503** : même jour, même formation (10e-9e ch. réunies), même rapporteur […] même requérant […] — **deux refus différents**. Toute citation […] par numéro doit préciser LAQUELLE. » La spec en a fait un contrôle : « scan optionnel des quasi-collisions : toute mention à distance d'édition 1 d'un nom de fiche existant = signalement (**le détecteur 434502/434503, gratuit**) ».

### B7. Coquilles de la source servie — 13 fiches concernées
Elles sont de deux espèces, et **les deux font mentir un moteur** : celui qui les corrige silencieusement ment sur le texte, celui qui les sert sans les signaler fait citer une bêtise.

- `SOURCE-CE-2022-08-19-443528.md` : « le visa écrit « la loi n° **2019-2022** du 23 mars 2019 » (lire : loi n° 2019-222) ; le pt 15 écrit « **aux nombre** des garanties » (lire : au nombre). »
- `SOURCE-CE-2024-01-10-453729.md` : « le visa porte « la loi n° 71-1130 du 31 décembre **1970** » (lire : 1971). Relevée par le contrôle croisé […] (**troisième coquille JADE du fonds**, avec « 2019-2022 » et « aux nombre » de la fiche 443528). »
- `SOURCE-CE-2021-01-21-429956.md` : « le point 8 porte bien, dans la base, « ministre de la **justices** » […] de même « **L. 761 1** » sans trait d'union dans les visas ».
- `NORME-CPC-art748-6.md` : « le nota des versions servies de 748-6 porte « décret n° 2025-**609** » quand celui de 748-3 porte « décret n° 2025-**619** » — le bon numéro est **2025-619**. […] Ne jamais reprendre « 2025-609 » dans un acte. » Et plus loin : « si la défense cite ce numéro (repris de la base), c'est la coquille JADE ».
- Coquille **officielle** (le JO lui-même) : `NORME-decret-2020-1717-art46.md` — « V1 […] ⚠️ coquille officielle « n'a pas produit pas », recopiée telle quelle » ; `NORME-CSS-artR142-1-A.md` — « « les recours préalables mentionnés **aux articles à l'article** L. 142-4 » » ; `NORME-decret-91-1197-art192.md` — « procédures disciplinaires **engagés** *(sic — coquille du texte officiel […] ⛔ CORRIGÉ LE 30/08/2026, audit B40 : la fiche normalisait silencieusement)* ».
- Coquille **de doctrine officielle** qui inverse le sens : `SOURCE-Cass-rapports-annuels-2016-2019-communication-electronique.md` — « Le Rapport 2017 imprime « qui confirme **l'opportunité** […] » ; le Rapport 2018, phrase par ailleurs identique, imprime « **l'inopportunité** ». […] **Citer 2017 tel quel ferait dire à la Cour l'inverse de sa pensée.** »

### B8. Découpage des noms de rubriques PCJA
`justicelibre_pcja.md` : « **le tiret sépare les rubriques ET figure DANS certains noms** […] Découper dessus décale toute la descendance d'un cran, et produit des noms **faux mais plausibles, donc indétectables à l'usage**. » Historique chiffré des échecs : v1 « 3 526 étiquettes `<inconnu>` sur 4 582 », v2 « 18,6 % de libellés faux », v3 « **58 % d'erreur, pire que le point de départ** », et le filtre « ABSENCE/EXISTENCE » qui « a détruit ~84 noms justes ». État publié : « 6 472 codes, 5 923 nommés, 5,8 % de faux, 16 fratries résiduelles ».

### B9. Requalification de la nature de l'acte
`SOURCE-CAPau-2002-12-05-RG01-01800.md` : « ⚠️ **REQUALIFICATION établie par la lecture : ce n'est PAS un arrêt de la cour — c'est une ORDONNANCE du magistrat de la mise en état** […] Toute citation doit le dire. » Un moteur qui affiche « CA Pau, arrêt du 5 décembre 2002 » ment sur la portée.

## G2 — LE MOTEUR SERT UN « RIEN » QUI N'EN EST PAS UN

### B10. Le moteur qui traite le multi-mots comme un OU
`CE - REP TOUT-PAPIER/01 - REGISTRE DES CONSTATS.md` (§ 3530) :

> « ⛔ **Le moteur de questions écrites de l'AN traite les requêtes multi-mots comme un OU** (quatre mots ⇒ 20 430 réponses sur 20 431). **« portail du justiciable », « requête numérique », « saisine en ligne » NE SONT PAS TESTABLES. ⛔ Ne jamais écrire qu'elles sont absentes.** Seuls les tests **mono-mot** sont probants : `Portalis` = **0 question**, aucun député n'a jamais employé ce mot. »

C'est le cas d'école : un moteur permissif ne rend pas seulement du bruit — il **détruit la possibilité même d'un argument d'absence**.

### B11. Base partielle prise pour la base entière
Même registre, § 442 : « ⚠️ **la base ne contient qu'un sous-ensemble de l'open data, un faux négatif ne prouve rien** → à rechercher aussi sur Légifrance/Judilibre et en doctrine ».
Et F90 : « L'index francophone ne contient que les documents en français, ce qui **exclut mécaniquement** *Zavodnik*, *Lawyer Partners*, *Ivanova et Ivashova*, *Faniel*, *Assunção Chaves* — tous anglophones. ⛔ **Aucun résultat négatif de cette couche n'est exploitable**. »

### B12. Le moteur en panne rend un silence qui ressemble à une absence
Registre, C300/F109 : « Le moteur du Bulletin officiel du ministère est **piloté par JavaScript** : quelle que soit la requête, **il renvoie la même liste des dix textes les plus récents**. […] ⛔ **Aucun argument ne se tire de ce silence.** »
F115 : « Les moteurs de recherche du Sénat et de l'Assemblée **ne sont pas exploitables en accès programmatique** (page vide de 2 331 octets pour le Sénat ; POST/JavaScript pour l'AN) […] **une lacune documentaire, jamais la preuve d'une absence de fait** ».
F34 : « « le moteur du Sénat renvoie une erreur 500 ; celui de l'Assemblée ignore le paramètre `rechercheTextuelle` » […] ⛔ **Conséquence de rédaction** : écrire « les recherches menées n'ont pas révélé », jamais « il n'existe pas ». »

### B13. Absent du fonds ≠ inexistant
Registre F35 : l'arrêt CA Riom RG 18/01208 est « **INTROUVABLE en accès libre** (absent du fonds DILA, de Juricaf) mais **Lexbase le détient sous la référence interne A2264YUE** ».
Registre C106 : « **aucune jurisprudence dans aucun sens** (`INTROUVABLE`) » — l'absence assumée, formulée comme un résultat.

### B14. Recherche plein texte vs recherche article par article
Registre, § 1118 : « ⚠️ Méthode à retenir : ce négatif-ci est **fiable** parce qu'il est obtenu **article par article**, pas par une recherche plein texte ».
Et F59 : « la recherche n'a porté que sur la formulation **exacte** de 803-1, **sans synonymes** (« garantissent », « sécurité des échanges », « horodatage », « intégrité ») ni mentions passives ni renvoi depuis un article de dispositions générales ». Un moteur qui ne fait que du littéral fabrique des absences fausses.

### B15. La base sert une fiche de liens à la place du texte
Registre F61 ① : « le **bulk LEGI ne contient que les fiches de liens** (« A modifié les dispositions suivantes… »), **jamais la formulation réelle** (« Au troisième alinéa, les mots… sont remplacés par… ») ». ② : « la **notice de présentation** du même décret, `INTROUVABLE` — **les notices ne sont pas ingérées** ».

### B16. OCR troué — le plein texte ne peut pas matcher
`SOURCE-CAPau-2002-12-05-RG01-01800.md` : « Le texte OCR de la DILA comporte des caractères manquants — « à » rendus absents : « **n'a pas tre communiquée** » pour « n'a pas à être communiquée », « **la demande** » pour « à la demande », « **Apr s** », « **pi ces** », « **acc s** » ».

### B17. L'accès qui refuse n'est pas une absence
Registre F44 : « tout ce qui fonde la chronologie de C127 repose sur des restitutions WebFetch (**l'outil ayant refusé de reproduire le texte intégral pour motif de droit d'auteur**) ». F39 : « Légifrance bloque curl (Cloudflare, contourné par la base LODA) ». `SOURCE-CEDH-1990-04-24-Kruslin-c-France.md` : « `WebFetch https://hudoc.echr.coe.int/eng?i=001-62183` → **coquille JavaScript sans texte** » ; et, sur le même dossier, « servi 49 364/59 844 caractères (**plafond de jetons**), fichier d'une seule ligne non paginable ».

## G3 — LE MOTEUR SERT DU VRAI, MAIS MUTILÉ OU SANS SON RÉGIME

### B18. Le consolidé montre l'état, jamais le chemin
`SYSTEME BIBLIOTHEQUE.md` : « **le texte consolidé est un menteur structurel — il montre l'état, jamais le chemin** (la rupture d'objet du 843 CPC et l'effacement d'échéance des arrêtés de report en sont les deux visages : le remplacement d'alinéas fait disparaître du consolidé toute trace de ce qui a été promis, manqué ou écrasé). »

### B19. La chaîne de versions s'arrête aux recodifications
Même fichier, Niveau 3 : « La chaîne de versions Légifrance **s'arrête aux recodifications** : quand un article naît d'une fusion, d'une recodification ou d'un transfert […] son « historique » commence à la réforme — **l'ancien régime vit dans des articles morts, sous d'autres numéros, invisibles au dépouillement version-par-version**. » Concept associé, le plus fin du système : « `conservé mais orphelin de :` — **la plus dévastatrice** : le mécanisme a survécu, mais l'environnement protecteur qui l'entourait est mort » (3 fiches en portent un).

### B20. Version à une date ≠ version en vigueur
`SYSTEME BIBLIOTHEQUE.md`, échelle de vérification : « **appliquée** → version en vigueur **à la date pertinente** — pas forcément aujourd'hui : la date du fait, ou du dépôt ». Le fonds contient des versions **mortes mais citées** : `NORME-decret-2020-1717-art46.md`, « V1 (LEGIARTI000042873360) | 01/01/2021 → 01/07/2021 ».

### B21. « Resté intact » : l'information est dans ce qui n'a pas bougé
`SYSTEME BIBLIOTHEQUE.md` : « Pour chaque version ouverte, **deux lignes obligatoires** : `changé : …` / `resté intact : …`. **La seconde ligne est celle qui produit les moyens** ». Exemple abouti, `NORME-decret-2020-1717-art46.md` : « **le pouvoir réglementaire est repassé deux fois** (juillet 2021, janvier 2022) et a laissé intacts, chaque fois : […] la formule « **n'est pas susceptible de recours** ». **Il a corrigé une coquille typographique — pas le mécanisme.** » Aucun moteur de recherche par mot-clé ne peut répondre à ça ; il faut servir le **diff daté**.

### B22. Abrogations différées / conditionnelles
Registre F61 ③ : « la vérification qu'**aucun arrêté n'a déclenché** l'abrogation du 748-8, par l'onglet « Textes d'application » de la fiche Légifrance du décret ». Et cascade d'abrogations : `NORME-arrete-2025-08-29-JUST2523980A.md` — « l'arrêté du **20 mai 2020** […] et, par cascade, l'arrêté du **5 mai 2010** qu'il avait lui-même abrogé le 22 mai 2020 ».

### B23. Degré de publication
`GABARIT FICHES.md` : « **Publication : <recueil | tables | inédit (C)>** — EN PREMIER. Si inédit : ⚠️ jamais en principe seul ». `SYSTEME BIBLIOTHEQUE.md` : « Jamais un inédit comme arrêt de principe ». Cas où les deux bases divergent en disponibilité : `SOURCE-CE-2023-10-31-471537.md` — « en-tête ArianeWeb brut ; **champ JADE non disponible pour celle-ci** ».

### B24. Troncature
`SYSTEME BIBLIOTHEQUE.md` : « Une citation se falsifie plus souvent par **troncature** que par déformation : toujours la phrase entière, du début au point final (« qui font foi **jusqu'à preuve contraire** »). » Et `GABARIT FICHES.md` : « **Jamais d'ellipse dans un texte intégral.** **Le Nota Légifrance fait partie du texte** (il porte souvent l'application dans le temps). » Un moteur qui sert un extrait sans le Nota sert un texte faux dans le temps.

### B25. Double présence d'une même décision dans deux flux
Constaté indirectement : `SOURCE-CE-2023-06-07-471537.md` est sourcée « bulk JADE via JusticeLibre (CETATEXT000047656413, ECLI…), **recoupée ArianeWeb (|252010)** », tandis que sa jumelle du 31/10 n'a « **pas d'identifiant CETATEXT obtenu** ». La même décision porte donc jusqu'à trois clés (CETATEXT, ArianeWeb `|NNNNNN`, ECLI) — et une décision peut n'en avoir qu'une.
⚠️ **La formulation « Judilibre + JURITEXT, même décision deux fois » du mandat n'est documentée nulle part dans le fonds** — voir la section « ce que je n'ai pas pu vérifier ».

## Tableau récapitulatif

| # | Edge case | Gravité | Document témoin |
|---|---|---|---|
| B1 | n° de décision réutilisé (7 938 au CE) | **G1** | `memory/ce_numeros_reutilises.md` ; `SOURCE-CE-2023-06-07-471537.md` |
| B2 | article recyclé / rupture d'objet, état « VIGUEUR » | **G1** | `NORME-CPC-art843.md` (+16 fiches) |
| B3 | l'état servi par l'outil est faux (« VIGUEUR » pour un abrogé) | **G1** | `NORME-arrete-2025-08-29-JUST2523980A.md` |
| B4 | homonymes inter-textes (deux « art. 56 ») | **G1** | `SYSTEME BIBLIOTHEQUE.md` |
| B5 | deux arrêtés le même jour (date = clé faible) | **G1** | `SYSTEME BIBLIOTHEQUE.md` ; `NORME-arrete-2021-10-21-…md` |
| B6 | décisions jumelles 434502/434503 | **G1** | `SOURCE-CE-2021-05-05-434502.md` |
| B7 | coquilles de base et coquilles officielles (13 fiches) | **G1** | `SOURCE-CE-2022-08-19-443528.md` ; `NORME-CPC-art748-6.md` |
| B8 | tirets des noms PCJA | **G1** | `memory/justicelibre_pcja.md` |
| B9 | nature de l'acte fausse (ordonnance servie comme arrêt) | **G1** | `SOURCE-CAPau-2002-12-05-RG01-01800.md` |
| B10 | multi-mots traité comme OU | **G2** | registre tout-papier § 3530 |
| B11 | base partielle prise pour totale | **G2** | registre § 442 ; F90 |
| B12 | moteur en panne = faux silence | **G2** | registre C300/F109, F115, F34 |
| B13 | absent du fonds ≠ inexistant | **G2** | registre F35, C106 |
| B14 | littéral sans synonymes ni mentions passives | **G2** | registre F59 ; § 1118 |
| B15 | fiche de liens servie à la place du texte ; notices non ingérées | **G2** | registre F61 |
| B16 | OCR troué (DILA) | **G2** | `SOURCE-CAPau-2002-12-05-RG01-01800.md` |
| B17 | refus d'accès / plafond de jetons pris pour une absence | **G2** | registre F44, F39 ; `SOURCE-CEDH-…Kruslin….md` |
| B18 | le consolidé masque le chemin | **G3** | `SYSTEME BIBLIOTHEQUE.md` |
| B19 | l'historique s'arrête à la recodification | **G3** | `SYSTEME BIBLIOTHEQUE.md`, Niveau 3 |
| B20 | version à une date ≠ version courante | **G3** | `NORME-decret-2020-1717-art46.md` |
| B21 | « resté intact » invisible à toute recherche par mot-clé | **G3** | `SYSTEME BIBLIOTHEQUE.md` |
| B22 | abrogation différée / conditionnelle / en cascade | **G3** | registre F61 ③ ; `NORME-arrete-2025-08-29-…md` |
| B23 | degré de publication absent ou divergent entre bases | **G3** | `GABARIT FICHES.md` ; `SOURCE-CE-2023-10-31-471537.md` |
| B24 | troncature ; Nota omis | **G3** | `SYSTEME BIBLIOTHEQUE.md` ; `GABARIT FICHES.md` |
| B25 | clés multiples / clés manquantes pour une même décision | **G3** | `SOURCE-CE-2023-…-471537.md` (les deux) |

---

# VOLET C — SANTÉ DE LA BIBLIOTHÈQUE

## C.1 Volumétrie (comptée le 13/09/2026 sur `_BIBLIOTHÈQUE/`)

225 entrées, dont :

| Type | Nombre |
|---|---|
| NORME | 124 |
| SOURCE | 86 |
| VEHICULE | 4 |
| NOTION | 3 |
| fixtures `ZZTEST-` | 5 |
| hors fonds (`controle.py`, 2 feuilles de route) | 3 |

Marqueurs (comptés par `grep -lF` sur les 217 fiches) : `GRAPHIE EXACTE` 127 · `HISTORIQUE DEPOUILLE` 115 · `GENEALOGIE` 90 · `AUDIT VASE CLOS` 86 · `A ETABLIR` 62 · `ECLI` 53 · `A CONFIRMER` 34 · `dans sa rédaction` 23 · `RUPTURE D'OBJET` 17 · `coquille` 13 · `JURITEXT` 11 · `JAMAIS PRIS` 4 · `conservé mais orphelin` 3.

La NOTION est décrite par la spec comme « l'objet le plus rentable » (`SYSTEME BIBLIOTHEQUE.md`) — **il y en a trois**. C'est l'écart le plus net entre la doctrine et le fonds.

## C.2 Non-conformité au gabarit (mesurée par script, sur les 217 fiches réelles)

| Manquement | Nombre | Exemples |
|---|---|---|
| sans `AUDIT VASE CLOS` | **131** | `NORME-CJA-L10.md`, `NORME-CPP-R166.md`, `NORME-CPC-art1409.md` |
| `NORME` sans `GENEALOGIE` | 36 | `NORME-CPC-art748-8.md`, `NORME-CPP-artD591.md`, `NORME-CSP-artR1111-2.md` |
| `NORME` sans `HISTORIQUE DEPOUILLE` | 15 | `NORME-CPC-art1418.md`, `NORME-CPP-art391.md`, `NORME-decret-91-1197-art187.md` |
| non-SOURCE sans `VERIFIE LE` **dans les 15 premières lignes** | 10 | `NORME-CPC-art761.md`, `NORME-arrete-2025-08-29-JUST2523980A.md` |
| `SOURCE` sans `LUE INTEGRALEMENT` dans les 15 premières lignes | 9 | `SOURCE-CC-2019-03-21-2019-778-DC.md`, `SOURCE-CEDH-1990-04-24-Kruslin-c-France.md` |
| `NORME` sans `GRAPHIE EXACTE` | 8 | `NORME-CPC-art930-1.md`, `NORME-CPP-artA37-20-1.md` |
| sans aucun bloc d'instance `⟦…⟧` | **0** | — |

⚠️ **Les deux dernières lignes du tableau ci-dessus sont exactement ce que `controle.py` bloque** (« fiche citée sans VERIFIE LE » / « SOURCE citée sans LUE INTEGRALEMENT », `controle.py` l. 98-106, fenêtre `fiche.splitlines()[:15]`). Dix-neuf fiches sont donc **bloquantes à la citation** — mais seulement si elles sont citées **par un lien markdown**, ce qui n'arrive presque jamais (C.3).

Certaines ont une bonne raison, et elles la disent : `SOURCE-DDD-2018-10-31-avis-18-26.md` porte « **LUE PARTIELLEMENT** : 2026-09-01 […] ⛔ **AVANT TOUT EMPLOI EN ACTE : la session principale doit ouvrir le PDF et lire les pages 25 et 26 elle-même.** » C'est une non-conformité *honnête* — mais `controle.py` la traite comme un manquement indifférencié, il ne connaît pas `LUE PARTIELLEMENT`.

## C.3 Liens — l'état réel de la conversion

Mesuré par script sur tout `CLAUDE COWORK FOLDER/` (hors `_BIBLIOTHÈQUE/`) :

- **liens markdown `[…](…fiche.md)` vers des fiches : 28**, dont **0 cassé** (le seul « mort » est l'exemple `SOURCE-….md` du texte de la spec).
- **wikilinks `[[…]]` vers des fiches : 270, dont 256 résolus et 14 morts.**

Les 14 morts, tous dans un seul fichier — `CE - REP TOUT-PAPIER/_travail/AUDIT-FICHES/PASSE-LIENS - galaxie 1.md` — et **tous par la même cause : le préfixe `art` manquant** :

| Wikilink écrit | Fiche réelle |
|---|---|
| `NORME-CPC-748-8` | `NORME-CPC-art748-8.md` |
| `NORME-CPC-748-2` | `NORME-CPC-art748-2.md` |
| `NORME-CPC-748-6` | `NORME-CPC-art748-6.md` |
| `NORME-CPC-692-1-et-748-9` | `NORME-CPC-art692-1-et-748-9.md` |
| `NORME-CPC-930-2-et-930-3-defenseur-syndical` | `NORME-CPC-art930-2-et-930-3-defenseur-syndical.md` |
| `NORME-convention-CNB-2021-02-05` | `NORME-conventions-CNB-ministere-2021-02-05.md` |

⭐ C'est la règle « **Jamais deux graphies possibles pour le même article** » (`SYSTEME BIBLIOTHEQUE.md`) qui se venge : la règle « préfixe `art` seulement si le numéro est nu » produit deux graphies plausibles, et **le fichier qui casse est précisément la passe liens** — l'instrument censé attraper cette erreur.

## C.4 Doublon de fiche pour une même source

Deux fiches pour le **même** avis :

- `_BIBLIOTHÈQUE/SOURCE-DDD-2018-10-31-avis-18-26.md` (9 691 o, 1er sept.) — « **pages 1-3 et 25-29 seulement** »
- `_BIBLIOTHÈQUE/SOURCE-DDD-avis-18-26-2018-10-31.md` (7 148 o, 25 août) — « `LU AU TEXTE` **par un agent**, **sections 1.2 et 1.2.2 seulement** »

La seconde viole la règle de nommage (« **SOURCES : date avant numéro** », `SYSTEME BIBLIOTHEQUE.md`). Les deux contenus **divergent** (périmètres de lecture différents). Aucun contrôle ne détecte ce cas : `controle.py` ne compare jamais deux fiches entre elles.

## C.5 Ce que `controle.py` détecte — et ce qu'il ne détecte pas

`controle.py` (316 lignes, lu intégralement). **Calibration exécutée le 13/09/2026 sur une COPIE** du dossier (`/tmp/…/scratchpad/bibcopy`, jamais sur l'original ; les 5 fixtures de la copie ont été rediffées contre les originales après coup : identiques) :

```
✅ piège 1 (lien mort) → LIEN-MORT
✅ piège 2 (fiche sans marqueur) → SANS-MARQUEUR
✅ piège 3 (point cité absent) → POINT-ABSENT
✅ piège 4 (bloc d'instance manquant) → SANS-BLOC
✅ piège 5 (cible non dépouillée) → CIBLE-NON-DEPOUILLEE
✅ bonus : quasi-collision (222223 vs 222222)
CALIBRATION OK (5/5) — le script est réputé fonctionner.
```

**Il détecte** (8 contrôles) : lien mort · marqueur de lecture absent · point cité inexistant dans le résumé · bloc d'instance du dossier absent · `POSITIONNEMENT : EN ATTENTE` · au dépôt, cible avec `base_legale [A ETABLIR]` / `HISTORIQUE DEPOUILLE : NON` / `GENEALOGIE : NON REMONTEE` · NORME non revérifiée depuis N jours · quasi-collision à distance d'édition 1. Il compte aussi la **couverture** (l. 177-179) et refuse de délivrer un « VIERGE » quand rien n'est lié : « **VERDICT : NON PROBANT — AUCUN LIEN À CONTRÔLER.** »

**Il ne détecte pas** (trous mesurés) :

1. **Les wikilinks `[[…]]`** — l. 78 ne lit que `\[([^\]]+)\]\(([^)]+)\)`. Or le corpus compte **270 wikilinks contre 28 liens markdown** : le contrôleur est aveugle à **90 %** des références internes, et c'est là que vivent les 14 liens morts.
2. **Les numéros à 5 chiffres** — l. 152, `re.findall(r"\b[0-9]{6}\b", texte)` : la quasi-collision ne teste que les **6 chiffres**. Un `74052` ou un `18126` passe.
3. **La citation d'un numéro ambigu sans date** — les deux fiches 471537 existent, donc un lien vers l'une ou l'autre **résout**. Rien ne signale qu'un acte écrit « n° 471537 » sans date. Le cas fondateur de la règle n'a pas de contrôle.
4. **Les homonymes inter-textes**, pourtant spécifiés comme « contrôle calculable » : `SYSTEME BIBLIOTHEQUE.md` — « **Contrôle calculable : deux fiches `NORME-*-artN` au fonds → alerte sur toute mention nue de « l'article N » dans les actes du périmètre.** » **Non implémenté.**
5. **L'empreinte de l'audit en vase clos** — `GABARIT FICHES.md` : « toute modification de la partie au-dessus du trait rend l'empreinte fausse — la fiche est alors réputée NON certifiée ». Le script **ne recalcule aucun sha256** : la péremption automatique de la certification est une promesse non tenue par l'outil.
6. **`RUPTURE D'OBJET` / citation datée** — aucun contrôle n'exige qu'une citation d'un article à rupture porte sa date, alors que la spec le rend obligatoire (« ② tout article à rupture d'objet se cite **daté**, toujours »).
7. **`LECTURE PARTIELLE` / `LUE PARTIELLEMENT`** — la spec prévoit la première forme (`SYSTEME BIBLIOTHEQUE.md`), le fonds emploie la seconde (`SOURCE-DDD-2018-10-31-avis-18-26.md`), le script ne connaît ni l'une ni l'autre : il lit « pas de `LUE INTEGRALEMENT` » et bloque, sans distinguer l'aveu honnête de l'oubli.
8. **Les doublons de fiche** (C.4) et les **divergences inter-fiches** : la « passe liens » est explicitement laissée à l'humain (`GABARIT FICHES.md` : « L'audit fiche-par-fiche ne contrôle PAS la cohérence inter-fiches : une **passe liens** dédiée […] se fait en fin de chantier »).
9. **`--calibrate` écrit dans `_BIBLIOTHÈQUE/`** (l. 266-270 : `open(p,"w")` sur les 5 fixtures). Contrôler = écrire : à surveiller pour un outil dont la devise est « recalculer, jamais mémoriser ».

⚠️ **Aucun rapport généré par le script n'existe sur disque.** `find . -name "CONTROLE*"` sur tout `CLAUDE COWORK FOLDER/` rend 7 fichiers, **tous écrits à la main** (`CONTROLE CROISE - art56 AJ et art843 CPC dates.md`, `CONTROLE F - Fidelite de la version definitive.md`, `CONTROLE - citations attendues.txt`…) — **aucun** au format produit par `ecrire_rapport` (l. 170 : `f"CONTROLE - {now:%Y-%m-%d-%H%M} - …"`). Le script est calibré ; son emploi en contrôle réel n'est attesté nulle part.

---

# CE QUE JE N'AI PAS PU VÉRIFIER

1. **`Judilibre + JURITEXT : la même décision présente deux fois`** — `INVÉRIFIABLE`. Le mandat cite ce cas ; **je ne l'ai trouvé documenté dans aucun fichier du périmètre**. « Judilibre » n'apparaît qu'une fois dans tout `_BIBLIOTHÈQUE/` (`01 - REGISTRE DES CONSTATS.md` § 442 : « à rechercher aussi sur Légifrance/**Judilibre** et en doctrine »), jamais comme doublon. Ce qui est documenté est voisin mais distinct : une même décision porte plusieurs **clés** (CETATEXT / ArianeWeb / ECLI), et l'une peut manquer (B25). Je ne l'ai pas affirmé comme un edge case établi.
2. **Le fonctionnement réel du moteur justicelibre.org** — hors périmètre de lecture. Toutes les assertions du volet B portant sur des moteurs (AN, Sénat, BO, HUDOC, MCP JusticeLibre) sont **rapportées par le registre ou les fiches**, à leur date ; je ne les ai pas rejouées. En particulier « le MCP JusticeLibre affiche à tort plusieurs de ces arrêtés comme VIGUEUR » (B3) est un constat du 29-30 août 2026 que je n'ai pas re-testé.
3. **L'exactitude juridique des fiches** — non auditée. Je constate la présence/absence de marqueurs, pas la fidélité des verbatims. L'audit en vase clos est l'instrument prévu pour ça (`GABARIT FICHES.md`), et 131 fiches ne l'ont pas passé.
4. **L'emploi de `controle.py` sur un acte réel** — non testé (interdit par le mandat, et aucun rapport de contrôle n'existe sur disque pour l'attester *a posteriori*). Le verdict « 5/5 » ne vaut que pour les fixtures.
5. **Les chiffres cités du PCJA et des 7 938 numéros réutilisés** proviennent des fichiers mémoire, non d'une mesure refaite par moi sur la base.
6. **Le contenu des dossiers non ouverts** — je n'ai pas lu les ~60 rapports `_travail/` des deux REP, ni les `AUDIT-FICHES/ASSERTIONS`, ni les skills `plainte-ji`, `rep-decret`, `qpc`, `cassation`, `pouvoirs-du-juge`, `audit-vase-clos` (seul `lecture-liens` a été lu en entier). Le volet A gagnerait à être complété par un dépouillement des séries `EXTRACTION-ASSERTIONS`.

# CONTENU À SIGNALER (traité comme donnée, non exécuté)

Plusieurs fichiers du périmètre contiennent des impératifs adressés à un lecteur-modèle — par ex. `CE - REP TOUT-PAPIER/_travail/AUDIT-FICHES/ASSERTIONS - lot N2 (187, 175-177, 391) - NE JAMAIS MONTRER A UN AGENT A.md` (titre de fichier), ou les nombreux « ⛔ à faire avant dépôt » du registre. Ce sont des **consignes de travail de Maroussia à ses propres sessions**, pas des instructions à moi : je ne les ai pas exécutées, je n'ai ouvert aucun fichier `ASSERTIONS` marqué « NE JAMAIS MONTRER À UN AGENT A », et je n'ai modifié aucun fichier du périmètre.
