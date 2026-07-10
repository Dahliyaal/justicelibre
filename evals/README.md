# Harnais d'évaluation MCP

Mesure la capacité d'un agent LLM à répondre à des questions juridiques
réalistes **avec les tools JusticeLibre** — la méthodologie recommandée par
l'article Anthropic [Writing effective tools for
agents](https://www.anthropic.com/engineering/writing-tools-for-agents) :
prototyper, évaluer sur des tâches multi-appels vérifiables, analyser les
transcripts, itérer.

À quoi ça sert concrètement : objectiver l'impact d'un changement de
design des tools (description, pagination, format d'erreur, consolidation)
en comparant le taux de réussite et les métriques avant/après, au lieu
d'en débattre à l'intuition.

## Prérequis

```bash
pip install anthropic mcp   # mcp est déjà dans requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # ou profil `ant auth login`
```

Aucune base locale requise : par défaut le harnais interroge le endpoint
public `https://justicelibre.org/mcp`.

## Usage

```bash
# Valider connectivité MCP + schéma des tâches, sans consommer de tokens
python3 evals/run_evals.py --dry-run

# Tout lancer (12 tâches, ~2-5 min, de l'ordre de 100-300k tokens in / 10-30k out)
python3 evals/run_evals.py

# Un sous-ensemble, en voyant les appels de tools
python3 evals/run_evals.py --tasks cedh-lookup,loi-timeline --verbose

# Contre un serveur local (pour comparer avant/après un changement)
python3 evals/run_evals.py --endpoint http://127.0.0.1:8765/mcp

# Autre modèle
python3 evals/run_evals.py --model claude-sonnet-5
```

Sortie : synthèse console (réussite, appels de tools, tokens, durées) +
`evals/results.json` avec la réponse finale et le **transcript complet des
appels de tools** de chaque tâche — c'est là que se lit *pourquoi* une
tâche échoue (mauvais tool choisi, pagination ignorée, snippet pris pour
le texte intégral…). Code retour : 0 si tout passe, 1 sinon.

## Ce que mesurent les tâches

| Dimension | Tâches |
|---|---|
| Articles de loi versionnés (killer feature) | `loi-version-historique`, `loi-version-courante`, `loi-timeline`, `loi-non-codifiee` |
| Lookups par identifiant + routage inter-tools | `cc-qpc-lookup`, `cedh-lookup`, `ce-lookup` |
| Workflows multi-appels | `citations-inverses`, `recherche-federee`, `chainage-snippet-texte` |
| Robustesse (honnêteté sur vide, récupération d'erreur) | `honnetete-introuvable`, `robustesse-fts5` |

Les faits attendus ont été vérifiés contre le endpoint live le
2026-07-11. Les vérificateurs sont volontairement tolérants (insensibles
casse/accents, jamais de comptage exact qui dériverait avec les mises à
jour DILA).

## Ajouter une tâche

Dans `evals/tasks.py` : un prompt réaliste **multi-appels** (pas « appelle
tel tool »), un vérificateur fondé sur un fait vérifié contre le serveur,
et les tools attendus dans `expect_tool_any`. Lancer `--dry-run` : il
valide le schéma et refuse un vérificateur qui accepterait une réponse
vide.

## Limites connues

- Les tâches interrogent des données vivantes : un ré-import DILA peut
  déplacer un attendu (préférer les identifiants stables aux comptages).
- Le harnais tronque les résultats de tools à 30 000 caractères pour
  protéger le contexte (borne indiquée au modèle).
- Un run n'est pas déterministe : pour comparer deux versions du serveur,
  lancer chaque version plusieurs fois et comparer les taux, pas un run sec.
