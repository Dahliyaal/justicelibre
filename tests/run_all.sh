#!/bin/bash
# Lance les tests de régression locaux.
# Usage :
#   tests/run_all.sh            # tout (offline + tests qui tapent la prod live)
#   tests/run_all.sh --offline  # uniquement les tests sans réseau (utilisé par la CI)
set -e
cd "$(dirname "$0")/.."

OFFLINE_ONLY=0
[[ "$1" == "--offline" ]] && OFFLINE_ONLY=1

run() {
    echo "=== $1 ==="
    python3 "$1" || { echo "FAILED: $1"; exit 1; }
    echo
}

# Tests SANS réseau ni base de prod (déterministes → gate de CI).
run tests/test_source_url.py
run tests/test_citations.py
run tests/test_ssr_escaping.py
run tests/test_annotations.py
run tests/test_fts5_triggers.py
run tests/test_prompts_resources.py
run tests/test_error_contract.py

# Tests qui interrogent la prod live (justicelibre.org) : à ne pas lancer en
# CI (flaky + charge le serveur). Skippés avec --offline.
if [[ $OFFLINE_ONLY -eq 0 ]]; then
    run tests/test_search.py
    run tests/test_v2.py
else
    echo "(--offline : test_search.py et test_v2.py skippés — ils tapent la prod live)"
fi

echo "✓ Tous les tests passent."
