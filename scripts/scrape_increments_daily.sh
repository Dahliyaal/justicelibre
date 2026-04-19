#!/bin/bash
# Scrape incremental quotidien des 3 sources non-bulk : CEDH, CJUE, ArianeWeb.
# Tourne sur PatrologiaLatina (où vit judiciaire.db avec ces 3 tables).
# Les scrapers sont idempotents (INSERT OR IGNORE sur PK), donc une re-exécution
# quotidienne n'ajoute que ce qui est nouveau.
#
# Install :
#   chmod +x /opt/justicelibre/scripts/scrape_increments_daily.sh
#   crontab -e :
#     0 5 * * * /opt/justicelibre/scripts/scrape_increments_daily.sh

set -e
LOG=/var/log/justicelibre/scrape_increments.log
mkdir -p /var/log/justicelibre

cd /opt/justicelibre

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] daily incremental START" >> $LOG

# CEDH : ~5-10 min (re-list années récentes, INSERT OR IGNORE sur 76k existants)
echo "[$(date -u '+%H:%M:%S')] CEDH..." >> $LOG
timeout 1800 sudo -u justicelibre python3 -u scrape_cedh.py >> $LOG 2>&1 \
  && echo "[$(date -u '+%H:%M:%S')] CEDH OK" >> $LOG \
  || echo "[$(date -u '+%H:%M:%S')] CEDH timeout/error (non-fatal)" >> $LOG

# CJUE : ~3-5 min
echo "[$(date -u '+%H:%M:%S')] CJUE..." >> $LOG
timeout 1800 sudo -u justicelibre python3 -u scrape_cjue.py >> $LOG 2>&1 \
  && echo "[$(date -u '+%H:%M:%S')] CJUE OK" >> $LOG \
  || echo "[$(date -u '+%H:%M:%S')] CJUE timeout/error (non-fatal)" >> $LOG

# ArianeWeb : checkpoint dans /tmp/scrape_ariane.checkpoint, reprend là où ça s'était arrêté
echo "[$(date -u '+%H:%M:%S')] ArianeWeb..." >> $LOG
timeout 1800 sudo -u justicelibre python3 -u scrape_ariane.py >> $LOG 2>&1 \
  && echo "[$(date -u '+%H:%M:%S')] ArianeWeb OK" >> $LOG \
  || echo "[$(date -u '+%H:%M:%S')] ArianeWeb timeout/error (non-fatal)" >> $LOG

echo "[$(date -u '+%H:%M:%S')] daily incremental DONE" >> $LOG
