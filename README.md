# justicelibre.org

> ⚠️ **Le code de ce dépôt n'est plus à jour.** Le développement se poursuit dans un dépôt privé, le temps de stabiliser la nouvelle version. Le code ici est l'archive de la première version (septembre 2026). Cette page, elle, décrit le service actuel.
>
> **Le service, lui, continue sur [justicelibre.org](https://justicelibre.org), et chaque résultat y renvoie à sa source officielle.**

L'accès libre à toute la jurisprudence et la loi françaises publiées en données ouvertes, pour Claude, ChatGPT et votre IA.

## Se connecter

Adresse du serveur MCP (HTTP « streamable ») :

```
https://justicelibre.org/mcp
```

Aucune installation : ajoutez cette adresse comme connecteur dans votre client (Claude, ChatGPT, Cursor, VS Code…). Les outils de recherche fonctionnent sans compte ; un compte justicelibre (connexion OAuth) ajoute les dossiers et références enregistrées.

Instructions détaillées : [justicelibre.org/#connect](https://justicelibre.org/#connect)

## Sources

Cour de cassation et juridictions judiciaires (Judilibre), Conseil d'État, cours administratives d'appel et tribunaux administratifs, Conseil constitutionnel, CEDH, CJUE, CNIL, CADA, Défenseur des droits, BOFiP ; codes et lois en vigueur et historiques (LEGI), Journal officiel (JORF), conventions collectives (KALI), travaux parlementaires.

Plus de 3,9 millions de décisions et 1,8 million d'articles de loi. Chiffres à jour chaque jour : [justicelibre.org](https://justicelibre.org).

## Outils (19)

**Sans compte (13)**

| Outil | Rôle |
|---|---|
| `search` | Recherche dans toutes les sources à la fois |
| `search_case_law` | Décisions d'une juridiction, par pertinence ou par date |
| `search_recent_admin_decisions` | Dernières décisions des juridictions administratives |
| `search_legislation` | Codes, lois, Journal officiel, conventions collectives |
| `search_doctrine` | CADA, Défenseur des droits, conclusions de rapporteurs publics, BOFiP… |
| `search_decisions_citing` | Décisions qui citent un article de loi |
| `search_directory` | Adresses et contacts publics (juridictions, greffes, mairies, préfectures…) |
| `get_decision` | Texte intégral d'une décision |
| `get_law_article` | Article de code ou de loi, en vigueur à une date donnée |
| `get_legislative_history` | Travaux préparatoires d'une loi |
| `resolve_reference` | Transforme une référence en identifiant et lien officiel |
| `check_citations` | Vérifie des citations contre le texte source |
| `about` | Couverture, volumes et fraîcheur des données |

**Avec un compte (6)**

| Outil | Rôle |
|---|---|
| `get_account_item` | Lire un dossier, une référence, une note… |
| `create_account_item` | Créer un dossier, un sous-dossier, une référence, une note |
| `update_account_item` | Modifier un élément existant |
| `delete_account_item` | Supprimer un élément |
| `open_ticket` | Signaler une erreur, une source manquante, un bug |
| `reply_ticket` | Répondre à un signalement |

## Données

Les données proviennent des jeux ouverts de l'État (DILA, Cour de cassation, Conseil d'État…) et restent sous [Licence Ouverte Etalab](https://www.etalab.gouv.fr/licence-ouverte-open-licence).

---

### English

⚠️ **The code in this repository is no longer up to date.** Development continues in a private repository while the new version stabilises. The code here archives the first version (September 2026); this page describes the current service. The live service is at [justicelibre.org](https://justicelibre.org) — MCP endpoint `https://justicelibre.org/mcp`, 19 tools (13 without an account).
