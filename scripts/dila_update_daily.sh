#!/bin/bash
# Daily DILA delta updater — pulls today's incremental tarball for each fond
# and runs parse_dila_bulk.py to merge into existing SQLite DBs.
#
# To install on al-uzza:
#   1. Copy this script to /opt/justicelibre/scripts/
#   2. chmod +x
#   3. Add cron : 0 4 * * * /opt/justicelibre/scripts/dila_update_daily.sh
#
# DILA publishes deltas at:
#   https://echanges.dila.gouv.fr/OPENDATA/{FOND}/{FOND}_YYYYMMDD-HHMMSS.tar.gz
# Naming: {FOND}_{YYYYMMDD}-140000.tar.gz published daily at 14:00 UTC

set -e
LOG=/var/log/justicelibre/dila_update.log
WORK=/opt/justicelibre/dila_bulk
mkdir -p $WORK /var/log/justicelibre

# Funds to update (skip CASS/CAPP/CONSTIT — overlap with judiciaire.db)
FUNDS=(legi jorf jade kali cnil)

# Yesterday's delta (DILA publishes at 14h UTC, so cron at 04h checks J-1)
YESTERDAY=$(date -u -d "yesterday" +%Y%m%d)

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] DILA daily update for ${YESTERDAY}" >> $LOG

for fund in "${FUNDS[@]}"; do
  url="https://echanges.dila.gouv.fr/OPENDATA/${fund^^}/${fund^^}_${YESTERDAY}-140000.tar.gz"
  out="$WORK/delta_${fund}_${YESTERDAY}.tar.gz"
  echo "[$(date -u '+%H:%M:%S')] $fund: fetching $url" >> $LOG

  if curl -sf --max-time 600 "$url" -o "$out"; then
    size=$(stat -c%s "$out")
    if [ "$size" -lt 200 ]; then
      echo "[$(date -u '+%H:%M:%S')] $fund: empty delta (${size}b), skip" >> $LOG
      rm -f "$out"
      continue
    fi
    echo "[$(date -u '+%H:%M:%S')] $fund: parsing delta ($(du -h $out | cut -f1))" >> $LOG
    # parse_dila_bulk.py attend un nom Freemium_{fund}.tar.gz dans BULK_DIR.
    # On rename pour réutiliser le parser tel quel. INSERT OR IGNORE/REPLACE
    # garantit l'idempotence : ré-ingérer une décision déjà présente est no-op.
    cp "$out" "$WORK/Freemium_${fund}.tar.gz"
    cd /opt/justicelibre
    python3 -u parse_dila_bulk.py "$fund" >> $LOG 2>&1 \
      && echo "[$(date -u '+%H:%M:%S')] $fund: parse OK" >> $LOG \
      || echo "[$(date -u '+%H:%M:%S')] $fund: parse FAILED" >> $LOG
    rm -f "$out" "$WORK/Freemium_${fund}.tar.gz"
  else
    echo "[$(date -u '+%H:%M:%S')] $fund: no delta available (404 or timeout)" >> $LOG
  fi
done

echo "[$(date -u '+%H:%M:%S')] daily update done" >> $LOG
