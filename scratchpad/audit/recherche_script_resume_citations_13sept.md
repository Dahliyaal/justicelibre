# Recherche : le script « résumé LLM + textes cités avec position »

Mission en lecture seule, 13/09/2026. Aucune modification, aucun `rm`, aucun service touché.

**Réponse courte : le script existe, il s'appelle `worker_enrich.py`, il a tourné, et il a produit 4 392 décisions enrichies et 39 881 articles localisés dans `/opt/justicelibre/dila/enrichment.db` sur al-uzza.**

---

## 1. Candidat n° 1 — `worker_enrich.py` (LE script)

### Identité

| | |
|---|---|
| Chemin (local) | `/home/dahl/justicelibre/enrichment/worker_enrich.py` |
| Chemin (serveur al-uzza, 46.224.173.253) | `/opt/justicelibre/worker_enrich.py` |
| Date de modification | local : `Jul 20 04:07` — serveur : `Jul 20 02:08` |
| Taille | 17 035 octets, 358 lignes (les deux) |
| Identiques ? | Oui. `md5sum` = `0564006b27e0c3f69ebaa45e97a07907` sur les deux machines. |
| Modèle / API | **Gemini CLI**, modèle `gemini-2.5-flash`, appelé en `subprocess` (pas l'API Python `genai`) |

### À quoi ça sert (3 lignes)

Il prend les décisions de la Cour de cassation les plus récentes non encore traitées dans `cass.db`, les envoie une par une à Gemini avec un prompt qui demande un JSON strict, et stocke le résultat dans `enrichment.db`. Le JSON contient d'un côté **les articles cités** (code, numéro, alinéa, extrait verbatim), de l'autre **8 « chunks » de résumé** (faits, procédure, moyens, question juridique, motivation, solution, ratio decidendi, vulgarisation) plus 5 métadonnées (matière, type de parties, sens, qui gagne, enjeu financier). Après la réponse du modèle, le script **recalcule lui-même la position absolue en caractères** de chaque citation dans le texte de la décision.

### Le prompt, verbatim

Il est construit par `build_prompt()`, `worker_enrich.py:l. 66-108`. La nomenclature injectée à la ligne 70 vient de `CODES_LEGI` + `NORMES_INTL` + `DOCTRINE` (`l. 27-63`), aplatie en `CODES_BLOCK` (`l. 63`) :

> `worker_enrich.py:l. 63`
> ```python
> CODES_BLOCK = "\n".join(f"  {k:8s} = {v}" for k, v in {**CODES_LEGI, **NORMES_INTL, **DOCTRINE}.items())
> ```

Prompt complet, `worker_enrich.py:l. 66-108` :

```python
    66	def build_prompt(juri, formation, date, numero, solution, texte):
    67	    return f"""Tu es un assistant juridique français. Analyse cette décision et retourne UNIQUEMENT un JSON strict (pas de markdown, pas de texte avant/après).
    68	
    69	NOMENCLATURE :
    70	{CODES_BLOCK}
    71	
    72	Si tu ne reconnais pas le code, mets "code": "?". Si "le présent code" / "ce code" : déduis du contexte global (matière civile/pénale/etc.).
    73	
    74	JSON :
    75	{{
    76	  "articles_cites": [
    77	    {{
    78	      "match_exact": "TEXTE EXACT mot-pour-mot copié de la décision. RÈGLE STRICTE : doit OBLIGATOIREMENT contenir littéralement le numéro `num` que tu déclares dans cette entrée. Si pas de snippet contenant la ref complète, mets `match_exact: null` + confidence: 'low'. Pour articles groupés (ex: 'articles X et Y'), 1 entrée par article avec MÊME match_exact mais chaque entrée DOIT avoir son `num` mentionné.",
    79	      "paragraph_snippet": "phrase complète contenant la ref (50-200 chars), copiée EXACTEMENT.",
    80	      "code": "ABRÉVIATION (selon nomenclature ci-dessus)",
    81	      "num": "numéro article SANS alinéa (ex: 700, R4127-4, L1152-1, préliminaire)",
    82	      "alinea": "optionnel, ex: '3'. null sinon.",
    83	      "confidence": "high|medium|low"
    84	    }}
    85	  ],
    86	  "chunks": {{
    87	    "faits": "résumé des faits matériels",
    88	    "procedure": "historique procédural",
    89	    "moyens": "demandes et arguments des parties",
    90	    "question_juridique": "question de droit posée",
    91	    "motivation": "raisonnement de la cour avec visa des textes",
    92	    "solution": "dispositif (rejet/cassation/annulation/etc.)",
    93	    "motif_specifique": "LE pourquoi précis qui a tranché (ratio decidendi)",
    94	    "vulgarisation": "Style journaliste juridique (Le Monde, Mediapart) en 4-7 phrases. RÈGLES : (1) PRÉCIS sur le contexte (qui, quoi, où, comment), (2) ÉVITE les raccourcis comiques (ex: 'racket sur un marché' fait penser à attaque au couteau, préfère 'extorsion par les régisseurs des emplacements'), (3) Pas de jargon (subornation→pression témoin, JLD→juge des libertés et de la détention), (4) Pas de latin, (5) Pas d'abréviations sauf TFUE/CEDH, (6) Précis ET accessible, ni langage de bistrot ('le mec'), ni jargon avocat, (7) Toujours nommer juridiction, décision, motif. INTERDICTION ABSOLUE de nommer une personne physique (dire 'un couple', 'un salarié', jamais un nom).",
    95	    "matiere": "LE domaine juridique en 1-3 mots simples (ex: 'droit du travail', 'bail commercial', 'responsabilité voisinage', 'droit pénal', 'sécurité sociale', 'droit de la famille').",
    96	    "parties_type": "Nature GÉNÉRIQUE des parties, sans aucun nom propre (ex: 'salarié c/ employeur', 'locataire c/ bailleur', 'particulier c/ administration', 'consommateur c/ société', 'assuré c/ assureur').",
    97	    "sens_demandeur": "Qui a formé le pourvoi et l'issue POUR LUI, en clair. Valeurs : 'demandeur gagne' | 'demandeur perd' | 'partiel' | 'na'. Le 'demandeur' = celui qui a saisi la Cour de cassation. Ex: un salarié se pourvoit et obtient la cassation → 'demandeur gagne' ; un employeur se pourvoit et voit son pourvoi rejeté → 'demandeur perd'.",
    98	    "qui_gagne": "En une courte phrase concrète : quel TYPE de partie l'emporte au final (ex: 'le salarié licencié obtient réparation', 'le bailleur conserve son loyer', 'aucun, renvoi en appel'). Sans nom propre.",
    99	    "enjeu_financier": "Montant en euros en jeu s'il est mentionné (ex: '1765', '45000'). null si aucun montant chiffré."
   100	  }}
   101	}}
   102	
   103	DÉCISION (Cour de cassation, {formation}, {date}, n° {numero}, {solution}) :
   104	---
   105	{texte}
   106	---
   107	
   108	JUSTE le JSON, rien d'autre."""
```

### Sur la résolution des références relatives (« du même code »)

C'est le point du mandat sur lequel il faut être exacte : le prompt **ne contient pas** la formule « du même code ». Ce qu'il contient, verbatim, c'est `worker_enrich.py:l. 72` :

> « Si tu ne reconnais pas le code, mets "code": "?". Si "le présent code" / "ce code" : déduis du contexte global (matière civile/pénale/etc.). »

La résolution des références relatives est donc bien **demandée au modèle**, mais par les formules « le présent code » / « ce code », pas « le même code ». Et elle est faite **en sortie** : chaque entrée de `articles_cites` porte un champ `code` absolu (`l. 80`), rempli selon la nomenclature des 43 abréviations de `l. 27-62`. Il n'y a aucun code de résolution déterministe côté Python — c'est entièrement à la charge du LLM.

### Le modèle appelé

`worker_enrich.py:l. 202-207` :

```python
   202	    try:
   203	        # gemini-2.5-flash : modèle stable, capacité garantie (vs preview = rate-limit fréquent)
   204	        result = subprocess.run(
   205	            ["gemini", "-m", "gemini-2.5-flash", "-p", prompt],
   206	            capture_output=True, text=True, timeout=240,
   207	        )
```

C'est le **CLI `gemini`**, pas la bibliothèque `google-generativeai`. Le prompt passe en argument de ligne de commande — ce qui est précisément ce qui a fini par casser le script (voir § 1 « traces d'exécution »).

### La position de la citation

C'est `locate()`, `worker_enrich.py:l. 122-141`, en trois passes de repli :

```python
   122	def locate(text, paragraph, match_exact, num=None):
   123	    if paragraph and match_exact:
   124	        p = text.find(paragraph)
   125	        if p != -1:
   126	            zone = text[p: p + max(len(paragraph), 300)]
   127	            r = zone.find(match_exact)
   128	            if r != -1:
   129	                return p + r
   130	    if match_exact:
   131	        p = text.find(match_exact)
   132	        if p != -1:
   133	            return p
   134	    if num:
   135	        num_norm = "".join(c for c in num if c.isalnum())
   136	        if num_norm:
   137	            pat = r"[.\s\-‑–]*".join([re.escape(c) for c in num_norm])
   138	            m = re.search(pat, text)
   139	            if m:
   140	                return m.start()
   141	    return None
```

Le résultat est stocké en `abs_position` (offset en caractères dans le texte de la décision), `worker_enrich.py:l. 271-280`.

### Où ça écrit

Deux bases, déclarées `worker_enrich.py:l. 20-21` :

```python
    20	CASS_DB = "/opt/justicelibre/dila/cass.db"
    21	ENR_DB = "/opt/justicelibre/dila/enrichment.db"
```

- lecture : `cass_decisions` (`l. 161-164`), filtre `WHERE length(texte) > 1000`, `ORDER BY date DESC` ;
- écriture n° 1 : table `enrichment`, `l. 247-262` (un enregistrement par décision, avec `raw_response` tronqué à 10 000 caractères et `gen=2` en dur) ;
- écriture n° 2 : table `enrichment_articles`, `l. 271-280` (une ligne par article cité) ;
- écriture n° 3 : table `enrichment_failures`, `l. 209-212` et `l. 234-237`.

### Schéma réel de `enrichment.db` (al-uzza, `sqlite3 .schema`)

`/opt/justicelibre/dila/enrichment.db`, 97 726 464 octets, daté `Jul 20 02:08`.

```sql
CREATE TABLE enrichment (
    decision_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,            -- 'cass', 'capp', 'constit', etc.
    enriched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    model TEXT DEFAULT 'gemini-cli',
    duration_s REAL,
    status TEXT,                     -- 'success' | 'partial' | 'json_error' | 'skipped'
    -- 8 chunks
    faits TEXT, procedure TEXT, moyens TEXT, question_juridique TEXT,
    motivation TEXT, solution TEXT, motif_specifique TEXT, vulgarisation TEXT,
    raw_response TEXT
, gen INTEGER DEFAULT 1, matiere TEXT, parties_type TEXT, sens_demandeur TEXT, qui_gagne TEXT, enjeu_financier TEXT);

CREATE TABLE enrichment_articles (
    decision_id TEXT NOT NULL,
    code TEXT NOT NULL DEFAULT '?',
    num TEXT NOT NULL DEFAULT '',
    alinea TEXT NOT NULL DEFAULT '',
    match_exact TEXT,
    paragraph_snippet TEXT,
    abs_position INTEGER,
    confidence TEXT,
    validated_link TEXT,
    PRIMARY KEY (decision_id, code, num, alinea)
);
```

Plus `enrichment_failures`, trois index, et une table FTS5 `enrichment_fts` (content='enrichment') alimentée par trigger `enrichment_ai` sur les 8 chunks — donc **la recherche plein texte sur les résumés était prévue et branchée**. Le champ `validated_link` de `enrichment_articles` confirme l'intention « poser des liens ».

Point à noter : `enrichment_articles` a pour clé primaire `(decision_id, code, num, alinea)`. Une même décision citant deux fois le même article à deux endroits ne garde donc **qu'une seule position**.

### A-t-il tourné ? Oui — chiffres mesurés

Comptages faits le 13/09/2026 sur al-uzza :

| Table | Lignes |
|---|---|
| `enrichment` | **4 392** |
| `enrichment_articles` | **39 881** |
| dont `abs_position IS NOT NULL` | **39 743** (99,65 %) |
| `enrichment_failures` | **779** |

Répartition des échecs (`select error_type,count(*),min(failed_at),max(failed_at) group by error_type`) :

```
json_error|707|2026-05-06 02:58:01|2026-07-20 02:08:38
timeout|72|2026-05-06 21:01:05|2026-05-10 08:34:16
```

Période d'exécution (`select gen,count(*),min(enriched_at),max(enriched_at) group by gen`) :

```
1|4392|2026-05-06 02:36:01|2026-05-10 20:14:36
```

**Conclusion importante : les 4 392 lignes sont toutes en `gen=1`.** Or la version du script datée du 20 juillet écrit `gen=2` en dur (`worker_enrich.py:l. 253`, `VALUES (?,'cass',?,?,2,…)`). Donc les données en base ont été produites par une **version antérieure** du script, entre le 6 et le 10 mai 2026. La version du 20 juillet — celle que tu as sous la main — **n'a jamais produit une seule ligne**.

Trois lignes d'exemple :

```
JURITEXT000051856699|cass|2026-05-06 02:36:01|gemini-cli|success|1
JURITEXT000051856697|cass|2026-05-06 02:36:23|gemini-cli|success|1
JURITEXT000051856695|cass|2026-05-06 02:36:58|gemini-cli|success|1
```

Cinq articles localisés, pour montrer que la partie « textes cités + position » fonctionne réellement :

```
JURITEXT000051856699|COJ|R. 431-5||1633|high
JURITEXT000051856699|CCH|L. 521-1||3351|high
JURITEXT000051856699|CPC|834||4056|high
JURITEXT000051856699|CCH|L. 521-2|I|4261|high
JURITEXT000051856699|CPC|624||6256|high
```

### Pourquoi ça s'est arrêté

`/var/log/enrich_gemini.log` sur al-uzza (1 834 447 octets, dernière écriture `May 12 13:20`), tail :

```
  [5/1400] JURITEXT000045388367 💥 [Errno 7] Argument list too long: 'gemini'
  [6/1400] JURITEXT000044220350 💥 [Errno 7] Argument list too long: 'gemini'
  [7/1400] JURITEXT000043883582 💥 [Errno 7] Argument list too long: 'gemini'
  [8/1400] JURITEXT000043489867 💥 [Errno 7] Argument list too long: 'gemini'

🛑 8 fails consécutifs → STOP

[done] 0 OK, 8 fails, total 11s
```

C'est le défaut de conception de `l. 205` : le texte entier de la décision passe **en argument de ligne de commande** (`-p prompt`). Au-delà de ~128 Ko d'arguments, Linux refuse (`E2BIG`). Les décisions plus anciennes et plus longues font systématiquement planter l'appel. Le circuit breaker `MAX_CONSECUTIVE_FAILS = 8` (`l. 296`) arrête alors le run, et le wrapper le relance en boucle à vide — `/var/log/enrich_wrapper.log` (2 025 688 octets) se termine sur :

```
[wrapper] Worker fini. Reset + relance dans 60s.
[wrapper] Worker fini. Reset + relance dans 60s.
```

Le correctif évident, si tu veux le relancer : passer le prompt par `stdin` (`input=prompt`) au lieu de `-p`.

### Cron / service ?

**Non.** `crontab -l` sur al-uzza ne contient aucune ligne d'enrichissement (6 lignes, toutes DILA / indexnow / constit / contrôles). `ls /etc/systemd/system/*.service` sur al-uzza : `al-uzza-web`, `justicelibre-warehouse`, `legal-tracker`, `ollama` + services système — aucun service d'enrichissement. Le lancement était donc **manuel**, via `run_enrich_loop.sh`.

---

## 2. Candidat n° 2 — `run_enrich_loop.sh` (le wrapper de lancement)

- **Chemin** : `/opt/justicelibre/run_enrich_loop.sh` (al-uzza uniquement — **absent en local**)
- **Date / taille** : `May 7 21:14`, 1 471 octets, exécutable (`-rwxr-xr-x`)
- **Rôle** : relance `worker_enrich.py` en boucle avec backoff progressif quand Gemini renvoie un quota dépassé. Ce n'est pas lui qui appelle le LLM ; c'est le harnais de relance.

`run_enrich_loop.sh:l. 8` et `l. 17-26`, verbatim :

```bash
     8	WAIT_TIMES=(900 1800 3600 7200 7200)  # 15min, 30min, 1h, 2h, 2h
...
    17	    echo "[wrapper] Lance worker (tentative $((attempt+1)))" | tee -a /var/log/enrich_wrapper.log
    18	    python3 worker_enrich.py 2>&1 | tee -a /var/log/enrich_gemini.log
    19	    exit_code=${PIPESTATUS[0]}
    20	
    21	    # Code 3 = RateLimitHit (sys.exit(3) dans worker)
    22	    if [ $exit_code -eq 3 ]; then
    23	        wait_s=${WAIT_TIMES[$attempt]}
    24	        echo "[wrapper] Rate-limit. Wait ${wait_s}s avant retry..." | tee -a /var/log/enrich_wrapper.log
```

C'est la commande à relancer (`bash /opt/justicelibre/run_enrich_loop.sh`) si tu reprends le chantier — après correction du bug `-p`.

---

## 3. Candidat n° 3 — `setup_enrichment.py` (création du schéma)

- **Chemin** : `/opt/justicelibre/setup_enrichment.py` (al-uzza — **absent en local**)
- **Date / taille** : `May 6 02:35`, 2 464 octets — soit **1 minute avant** le tout premier enrichissement (`2026-05-06 02:36:01`). La chronologie est cohérente.
- **Rôle** : crée `enrichment.db` et ses tables. Aucun appel LLM.

`setup_enrichment.py:l. 1-6`, verbatim :

```python
     1	#!/usr/bin/env python3
     2	"""Init la DB enrichment.db sur al-uzza."""
     3	import sqlite3
     4	from pathlib import Path
     5	
     6	DB = Path("/opt/justicelibre/dila/enrichment.db")
```

---

## 4. Faux amis écartés (à ne pas confondre)

### `enrich_dila.py` — ne fait AUCUN appel LLM

- `/home/dahl/justicelibre/enrich_dila.py` (9 818 o, `Sep 8 19:21`) et `/opt/justicelibre/enrich_dila.py` (9 818 o, `Sep 8 17:21`), plus `/opt/justicelibre/scripts/enrich_dila.py`.
- Il extrait des champs du **XML DILA** (balises `SCT`, `ANA`, `CITATION_JP`), pas d'un modèle. `enrich_dila.py:l. 1-4`, verbatim :

> « Enrichit a posteriori les décisions DILA déjà en base : abstrats (SCT), résumé (ANA), renvois (CITATION_JP), rapporteur, commissaire_gvt, type_rec, publi_recueil, publi_bull, nature_qualifiee / saisines / loi_def (CONSTIT), liens_textes. »

Le mot « résumé » y désigne le résumé **fourni par la DILA** (balise ANA), pas un résumé généré. C'est le piège de vocabulaire principal de cette recherche.

### `/var/log/enrich_capp.log` et `/var/log/enrich_jade.log` — logs de `enrich_dila.py`, pas de Gemini

`enrich_capp.log:l. 1-2`, verbatim :

```
[capp_decisions] added cols: ['abstrats', 'resume', 'renvois', 'commissaire_gvt', 'type_rec', 'publi_recueil', 'publi_bull', 'nature_qualifiee', 'saisines', 'loi_def', 'liens_textes']
[capp] using bulk: Freemium_capp_global_20250713-140000.tar.gz (279 MB)
```

### Sur PatrologiaLatina (46.225.190.237)

`enrich_piste_meta.py`, `enrich_cedh_meta.py`, `enrich_cjue_sparql.py`, `sync_enrich_to_prod.py` : enrichissement par **API PISTE / SPARQL / métadonnées**, pas par LLM. Le `grep -rIl -iE "gemini|articles_cites|generativeai" /opt /root` sur cette machine ne ramène **aucun script** : uniquement des caches (`/root/.npm/_cacache`, `/root/.cache/pip`), `/root/.gemini/` (config du CLI) et `/root/pl_ocr/` (OCR de la Patrologie latine, sans rapport). **Le script cherché n'est pas sur PatrologiaLatina.**

### Sur al-uzza, `/home/dahl/al-uzza-web/scripts/enrich_*.py`

Une quarantaine de fichiers (`enrich_hadith_grades.py`, `enrich_scholars.py`…) : projet Al-Uzza, corpus islamique, hors sujet.

### En local, `openai`/`anthropic`

`grep -rIl -iE 'openai|anthropic|generativeai'` sur `/home/dahl/justicelibre`, `/home/dahl/legal-tracker`, `/home/dahl/annuaire` ramène : `justicelibre/README.md`, `justicelibre/evals/run_evals.py`, `justicelibre/evals/README.md`, `justicelibre/tests/test_error_contract.py`, `justicelibre/tests/test_annotations.py`, `justicelibre/web/inedits/autres.html`, `annuaire/web/pdf_findings.csv`. Ce sont les **évals du MCP** et des tests, pas un pipeline de résumé de décisions.

---

## 5. Tableau récapitulatif

| Rang | Candidat | Machine | Date | LLM ? | A tourné ? | Probabilité d'être « le » script |
|---|---|---|---|---|---|---|
| 1 | `worker_enrich.py` | local + al-uzza (identiques, md5 `0564006b…`) | 20/07/2026 | **Oui — `gemini-2.5-flash` via CLI** | Une version antérieure oui (4 392 lignes, 6-10 mai) ; **cette version-ci, non** (elle écrit `gen=2`, la base n'a que `gen=1`) | **Certain** — c'est lui |
| 2 | `run_enrich_loop.sh` | al-uzza seul | 07/05/2026 | Non (wrapper) | Oui (`enrich_wrapper.log`, 2 Mo, jusqu'au 12/05) | Élevée comme **pièce du dispositif**, pas comme le script |
| 3 | `setup_enrichment.py` | al-uzza seul | 06/05/2026 | Non (DDL) | Oui (la base existe avec ce schéma) | Élevée comme pièce du dispositif |
| 4 | `enrich_dila.py` | local + al-uzza (×3) | 08/09/2026 | **Non** — XML DILA | Oui | **Nulle** — faux ami (« résumé » = balise ANA) |
| 5 | `enrich_cedh_meta.py`, `enrich_cjue_sparql.py`, `enrich_piste_meta.py` | PatrologiaLatina | 08/09/2026 | Non — API/SPARQL | Oui | Nulle |
| 6 | `evals/run_evals.py` | local | — | Oui (Anthropic) | — | Nulle — évals du MCP |
| 7 | `al-uzza-web/scripts/enrich_*.py` (~40) | al-uzza | — | Non | — | Nulle — autre projet |

---

## 6. Ce qui a été cherché et NON trouvé

Pour que tu saches où ne plus chercher.

- **Pas de version v1 du worker sur disque.** Celle qui a produit les 4 392 lignes (`gen=1`, mai 2026) n'existe nulle part : `find /opt /root /home -maxdepth 4 -iname "*enrich*"` sur al-uzza ne ramène qu'un seul `worker_enrich.py`, daté du 20 juillet. Pas de `.bak`, pas de `worker_enrich_v1.py`. Le dépôt local `/home/dahl/justicelibre` est un git, mais `git log -- enrichment/` ne ramène qu'un commit (`27cda62`) : pas d'historique exploitable sur ce fichier.
- **Aucun usage de l'API Python `google-generativeai` / `genai`.** `grep -rIl -iE 'genai|generativeai|GEMINI_API|gemini-'` sur `/home/dahl` (`.py`, `.md`, `.json`, `.sql`, `.sh`) ne ramène, hors `worker_enrich.py`, que des sessions de chat du CLI Gemini dans `/home/dahl/.gemini/tmp/{al-uzza,jeffery-ocr}/chats/` (mars 2026). Tout passe par le binaire `gemini`.
- **Pas de cron, pas de service systemd** pour l'enrichissement, sur aucune des deux machines (crontabs des deux serveurs lues intégralement ; `ls /etc/systemd/system/*.service` sur les deux).
- **Rien sur PatrologiaLatina** (voir § 4).
- **Pas d'embeddings branchés sur `enrichment.db`.** Rien dans les scripts lus ne calcule ni ne stocke de vecteur à partir de ces résumés. La seule structure de recherche présente est la table FTS5 `enrichment_fts` (lexicale, pas sémantique).
- **La formule « du même code » n'apparaît nulle part** dans les scripts : le prompt dit « le présent code » / « ce code » (`worker_enrich.py:l. 72`).
- **`/home/dahl/Desktop`** : non fouillé spécifiquement, mais couvert par le `grep -rIl` récursif sur `/home/dahl` (aucun résultat hors `.gemini/tmp`).
- `/root/jl_test_enrich` sur al-uzza : ne contient qu'un `sample.db` de 8,9 Mo daté du 8 septembre, aucun script.

---

## 7. INVÉRIFIABLE

- **Le prompt réellement utilisé en mai 2026.** Je peux citer verbatim le prompt de la version du 20 juillet, la seule sur disque. Les 4 392 lignes en base ont été produites par une version antérieure dont je n'ai aucune copie. Le schéma de `setup_enrichment.py` ne parle que de « 8 chunks », alors que la version de juillet en produit 13 (les 5 colonnes `matiere`, `parties_type`, `sens_demandeur`, `qui_gagne`, `enjeu_financier` ont été ajoutées par `ALTER TABLE` — elles sont en fin de `CREATE TABLE` dans le `.schema`). **Il est donc probable, mais non vérifié, que le prompt de mai était plus court** (8 chunks, sans matière/parties/sens/qui-gagne/enjeu). Pour trancher, il faudrait lire la colonne `raw_response` d'une ligne de mai — je ne l'ai pas fait.
- **Le contenu exact de `matiere`, `parties_type`, `sens_demandeur`, `qui_gagne`, `enjeu_financier` en base** : non interrogé. Si ces colonnes sont vides sur les 4 392 lignes, cela confirmerait le point ci-dessus.
- **Les 707 `json_error`** : je n'ai pas échantillonné leur `raw_response`, donc je ne sais pas si c'est du markdown mal fermé, des réponses tronquées, ou des refus du modèle.
- **La qualité juridique des résultats** : je n'ai relu aucun résumé ni vérifié aucune résolution de « ce code » contre la décision d'origine. 99,65 % de positions trouvées mesure la **localisation**, pas l'**exactitude** de l'attribution du code.
- **Le lien avec un projet d'embeddings** : rien trouvé qui le matérialise. L'hypothèse « but = recherche sémantique » reste une hypothèse.
- **Les 4 392 décisions couvertes rapportées au fonds `cass.db`** : je n'ai pas compté les lignes de `cass_decisions` (2,6 Go), donc je ne peux pas te donner le taux de couverture. À vue de nez c'est une fraction infime, le script ayant traité les décisions par date décroissante sur 4 jours seulement.
