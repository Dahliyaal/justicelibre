#!/bin/bash
# Enchaîne les rattrapages Judilibre UN PAR UN (SQLite n'a qu'un écrivain à la
# fois). Reprenable : chaque étape a son fichier d'état, relancer ce script
# saute ce qui est fini. Lancer via systemd-run, jamais nohup+& :
#   systemd-run --unit=jl-backfill-all /bin/bash /opt/justicelibre/scripts/judilibre_backfill_all.sh
# Suivi : tail -f /var/log/jl-backfill.log
set -u
cd /opt/justicelibre
LOG=/var/log/jl-backfill.log
run() {  # run <juri> <date_start> <date_end>
  echo "===== $(date '+%F %T') $1 $2 → $3" >> "$LOG"
  /usr/bin/python3 scripts/judilibre_backfill.py --jurisdiction "$1" --date-start "$2" --date-end "$3" --apply >> "$LOG" 2>&1
  rc=$?
  echo "===== $(date '+%F %T') fin $1 $2→$3 rc=$rc" >> "$LOG"
  [ $rc -eq 3 ] && { echo "DISQUE PLEIN — arrêt de la chaîne" >> "$LOG"; exit 3; }
}
# 1) Cours d'appel (2022 → 2025) — le plus gros trou
run ca 2022-01-01 2022-12-31
run ca 2023-01-01 2023-12-31
run ca 2024-01-01 2024-12-31
run ca 2025-01-01 2025-12-31
# 2) Tribunaux judiciaires (2023 → 2025)
run tj 2023-01-01 2023-12-31
run tj 2024-01-01 2024-12-31
run tj 2025-01-01 2025-12-31
# 3) Tribunaux de commerce
run tcom 2022-01-01 2025-12-31
# 4) 2026 : réenrichissement (champs manquants) de tout ce qui est déjà là
run ca 2026-01-01 2026-12-31
run tj 2026-01-01 2026-12-31
run tcom 2026-01-01 2026-12-31
run cc 2026-01-01 2026-12-31
echo "===== $(date '+%F %T') CHAÎNE TERMINÉE" >> "$LOG"
