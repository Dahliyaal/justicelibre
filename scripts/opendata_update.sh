#!/bin/bash
# Reprise/mise à jour opendata.justice-administrative.fr : le scraper est
# resumable (state.json) et idempotent (INSERT OR REPLACE). Ce wrapper
# relance juste le process s'il n'est pas déjà en cours.
#
# À installer via cron (quotidien, ne bloque rien s'il tourne déjà) :
#   0 5 * * * /opt/justicelibre/scripts/opendata_update.sh
set -e
LOG=/var/log/justicelibre/opendata.log
mkdir -p /var/log/justicelibre

if pgrep -f "python3.*download_opendata.py" >/dev/null; then
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] opendata: déjà en cours, skip" >> "$LOG"
  exit 0
fi
echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] opendata: (re)démarrage" >> "$LOG"
cd /opt/justicelibre
nohup python3 -u download_opendata.py >> "$LOG" 2>&1 &
echo "[$(date -u '+%H:%M:%S')] opendata: PID=$!" >> "$LOG"
