#!/bin/bash
# Lance tous les tests de régression locaux (sans live API).
# Usage : tests/run_all.sh
# Pour inclure les tests live : tests/run_all.sh --live
set -e
cd "$(dirname "$0")/.."

INCLUDE_LIVE=0
[[ "$1" == "--live" ]] && INCLUDE_LIVE=1

run() {
    echo "=== $1 ==="
    python3 "$1" || { echo "FAILED: $1"; exit 1; }
    echo
}

run tests/test_search.py
run tests/test_v2.py
run tests/test_source_url.py
run tests/test_citations.py

if [[ $INCLUDE_LIVE -eq 1 ]]; then
    echo "(les tests live sont déjà inclus dans test_search.py et test_v2.py)"
fi

echo "✓ Tous les tests passent."
