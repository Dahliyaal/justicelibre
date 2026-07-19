"""Tâches d'évaluation du serveur MCP JusticeLibre.

Chaque tâche est une question juridique réaliste nécessitant un ou
plusieurs appels de tools, avec un vérificateur programmatique. Les
attendus ont été vérifiés contre le endpoint live (justicelibre.org/mcp)
le 2026-07-11 — si la base évolue, préférer des vérifications
structurelles (un identifiant, un mot du texte) aux comptages exacts,
qui dérivent avec les mises à jour DILA.

Format d'une tâche :
    id                : slug unique (filtrable via --tasks)
    prompt            : la question posée au modèle
    verify            : dict de critères sur la RÉPONSE FINALE
        all_substrings : toutes doivent apparaître (insensible casse/accents)
        any_substrings : au moins une doit apparaître
        regex          : re.search (insensible à la casse)
    expect_tool_any   : au moins un de ces tools doit avoir été appelé
    max_turns         : plafond de tours agentiques (défaut : 8)
"""

TASKS = [
    # ── Killer feature : articles de loi versionnés ─────────────────
    {
        "id": "loi-version-historique",
        "prompt": (
            "Quel était le texte exact de l'article 1382 du Code civil "
            "en vigueur en 1995 ? Cite le texte intégralement."
        ),
        "verify": {"all_substrings": ["tout fait quelconque de l'homme"]},
        "expect_tool_any": ["get_law_article"],
    },
    {
        "id": "loi-version-courante",
        "prompt": (
            "La règle « tout fait quelconque de l'homme qui cause à autrui "
            "un dommage » est-elle encore à l'article 1382 du Code civil "
            "aujourd'hui ? Si non, quel article la porte désormais ?"
        ),
        "verify": {"all_substrings": ["1240"]},
        "expect_tool_any": ["get_law_article", "get_law_versions", "search_legi", "search_all"],
    },
    {
        "id": "loi-timeline",
        "prompt": (
            "Combien de versions historiques l'article 1128 du Code civil "
            "a-t-il connues, et quand la version actuelle est-elle entrée "
            "en vigueur ?"
        ),
        "verify": {
            "all_substrings": ["2016"],
            "any_substrings": ["2 versions", "deux versions"],
        },
        "expect_tool_any": ["get_law_versions"],
    },
    {
        "id": "loi-non-codifiee",
        "prompt": (
            "Trouve l'identifiant Légifrance de la loi n° 2000-321 et "
            "donne sa date exacte."
        ),
        "verify": {
            "all_substrings": ["JORFTEXT000000215117"],
            "any_substrings": ["12 avril 2000", "2000-04-12", "2000-04-13"],
        },
        "expect_tool_any": ["resolve_law_number"],
    },
    # ── Lookups par identifiant (routage inter-tools) ───────────────
    {
        "id": "cc-qpc-lookup",
        "prompt": (
            "De quoi traite la décision n° 2023-1048 QPC du Conseil "
            "constitutionnel, et à quelle date a-t-elle été rendue ?"
        ),
        "verify": {"all_substrings": ["résident", "2023"]},
        "expect_tool_any": ["get_cc_decision", "search_cc"],
    },
    {
        "id": "cedh-lookup",
        "prompt": (
            "Récupère la décision CEDH portant l'itemid 001-249914 : "
            "quel est le nom de l'affaire, l'État défendeur et la "
            "conclusion ?"
        ),
        "verify": {
            "all_substrings": ["monaco"],
            "any_substrings": ["radiation"],
        },
        "expect_tool_any": ["get_decision_cedh"],
    },
    {
        "id": "ce-lookup",
        "prompt": (
            "Quelle est la date de lecture de la décision du Conseil "
            "d'État n° 473286, et quel est son identifiant interne "
            "JusticeLibre ?"
        ),
        "verify": {
            "all_substrings": ["473286"],
            "any_substrings": ["2023-11-23", "23 novembre 2023", "DCE_473286"],
        },
        "expect_tool_any": ["get_admin_decision", "get_ce_decision"],
    },
    # ── Workflows multi-appels ──────────────────────────────────────
    {
        "id": "citations-inverses",
        "prompt": (
            "Quelles décisions de justice citent explicitement l'article "
            "L1152-1 du Code du travail (harcèlement moral) ? Donne "
            "l'identifiant d'une décision judiciaire qui le cite."
        ),
        "verify": {"any_substrings": ["JURITEXT"]},
        "expect_tool_any": ["search_decisions_citing"],
    },
    {
        "id": "recherche-federee",
        "prompt": (
            "Fais un panorama des sources de jurisprudence disponibles "
            "sur le harcèlement moral : combien de résultats par source ?"
        ),
        "verify": {"any_substrings": ["dila", "jade", "cedh", "cjue", "judiciaire", "administrat"]},
        "expect_tool_any": ["search_all"],
    },
    {
        "id": "chainage-snippet-texte",
        "prompt": (
            "Trouve un arrêt de la Cour de cassation portant sur la garde "
            "à vue et cite un passage de son TEXTE INTÉGRAL (pas "
            "seulement l'extrait de recherche)."
        ),
        # Le point testé : enchaîner search → get (la règle impérative des
        # instructions du serveur) au lieu de conclure depuis le snippet.
        "verify": {"all_substrings": ["garde à vue"]},
        "expect_tool_any": ["get_decision_judiciaire_libre"],
    },
    # ── Robustesse ──────────────────────────────────────────────────
    {
        "id": "honnetete-introuvable",
        "prompt": (
            "Récupère la décision CEDH portant l'itemid 001-9999999 et "
            "résume son contenu."
        ),
        # L'itemid n'existe pas : le modèle doit le dire, pas inventer un
        # résumé. (Verrouille l'anti-hallucination sur résultat vide.)
        "verify": {
            "any_substrings": [
                "introuvable", "pas trouvé", "n'existe pas", "aucune décision",
                "pas de décision", "ne correspond", "invalide", "n'a pas été trouvée",
                "ne semble pas exister", "impossible de récupérer", "n'ai pas pu",
            ],
        },
        "expect_tool_any": ["get_decision_cedh"],
    },
    {
        "id": "robustesse-fts5",
        "prompt": (
            "Trouve l'arrêt de la CJUE dans l'affaire C-131/12 (Google "
            "Spain, droit au déréférencement) et donne son identifiant "
            "CELEX ou ECLI."
        ),
        # La query brute « C-131/12 » fait planter FTS5 sur le serveur
        # pré-correctif (syntax error near "/") : la tâche mesure si
        # l'agent se rétablit (reformulation) ou si le serveur nettoie
        # la query. Attendu en hausse après le fix sanitization FTS5.
        "verify": {"any_substrings": ["62012", "celex", "ecli", "google"]},
        "expect_tool_any": ["search_cjue", "get_decision_cjue"],
        "max_turns": 10,
    },
]
