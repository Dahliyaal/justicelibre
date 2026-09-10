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
# --text : sans lui, les décisions entraient SANS texte, donc introuvables en
# recherche (96 804 lignes de mai à sept. 2026, constaté le 10/09/2026). Le
# coût ne porte que sur les décisions nouvelles (le texte déjà en base est gardé).
nohup python3 -u download_opendata.py --text >> "$LOG" 2>&1 &
echo "[$(date -u '+%H:%M:%S')] opendata: PID=$!" >> "$LOG"
