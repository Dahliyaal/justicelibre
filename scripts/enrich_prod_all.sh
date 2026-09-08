#!/bin/bash
# Enchaîne, UN PAR UN, les trois enrichissements de judiciaire.db sur la prod
# (8 sept. 2026) : en-têtes ArianeWeb (2 min, sans réseau), ECLI/titres/méta
# CJUE (SPARQL EUR-Lex, ~30 min), n° de requête officiels + méta CEDH (HUDOC,
# ~40 min). Chaque script sauvegarde toute valeur écrasée (colonnes _avant +
# CSV.gz) et est reprenable. À lancer APRÈS la fin du rattrapage Judilibre
# (un seul écrivain à la fois).
#   systemd-run --unit=jl-enrich-prod /bin/bash /opt/justicelibre/scripts/enrich_prod_all.sh
#   tail -f /var/log/jl-enrich-prod.log
set -u
cd /opt/justicelibre
LOG=/var/log/jl-enrich-prod.log
DB=/opt/justicelibre/dila/judiciaire.db
run() { echo "===== $(date '+%F %T') $*" >> "$LOG"; "$@" >> "$LOG" 2>&1; echo "===== $(date '+%F %T') rc=$?" >> "$LOG"; }
# Attendre la fin d'un éventuel rattrapage Judilibre encore actif.
while systemctl is-active --quiet jl-backfill-all; do sleep 60; done
run /usr/bin/python3 scripts/extract_ariane_header.py --db "$DB" --limit 500
run /usr/bin/python3 scripts/extract_ariane_header.py --db "$DB" --limit 0 --apply
run /usr/bin/python3 scripts/enrich_cjue_sparql.py --db "$DB" --limit 200 --batch 50
run /usr/bin/python3 scripts/enrich_cjue_sparql.py --db "$DB" --limit 0 --batch 50 --apply
run /usr/bin/python3 scripts/enrich_cedh_meta.py --db "$DB" --limit 1000 --batch 20
run /usr/bin/python3 scripts/enrich_cedh_meta.py --db "$DB" --limit 0 --batch 20 --apply
echo "===== $(date '+%F %T') ENRICHISSEMENTS PROD TERMINÉS" >> "$LOG"
