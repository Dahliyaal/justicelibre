#!/bin/bash
# Sync quotidien Judilibre /transactionalHistory : récupère toutes les
# créations/modifications/suppressions des dernières 24h et les applique sur
# judiciaire.db. Évite de se faire taper sur les doigts par la Cour de cassation
# (article V CGU : MAJ sous 72h).
#
# Install :
#   chmod +x /opt/justicelibre/scripts/judilibre_sync_daily.sh
#   crontab -e :
#     30 4 * * * /opt/justicelibre/scripts/judilibre_sync_daily.sh
# (4h30 UTC, juste avant scrape_increments_daily.sh à 5h pour cohérence.)

set -e
# Charge les credentials PISTE (judilibre_sync.py les lit via os.environ
# depuis le retrait des secrets hardcodés — 19 juillet 2026).
set -a; source /opt/justicelibre/.env; set +a
LOG=/var/log/justicelibre/judilibre_sync.log
mkdir -p /var/log/justicelibre

cd /opt/justicelibre

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] judilibre sync START" >> "$LOG"

# Marge de sécurité : 26h en arrière (cron quotidien + un peu de chevauchement
# pour absorber un retard ; l'upsert est idempotent).
timeout 3600 python3 -u judilibre_sync.py --history --since-hours 26 >> "$LOG" 2>&1 \
  && echo "[$(date -u '+%H:%M:%S')] judilibre sync OK" >> "$LOG" \
  || echo "[$(date -u '+%H:%M:%S')] judilibre sync timeout/error" >> "$LOG"

echo "[$(date -u '+%H:%M:%S')] judilibre sync DONE" >> "$LOG"
