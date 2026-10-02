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

# ArianeWeb : checkpoint dans /opt/justicelibre/scrape_ariane.checkpoint (PLUS dans
# /tmp : `fs.protected_regular = 2` y interdisait l'écriture, en silence, et /tmp
# est vidé au redémarrage). La reprise se fait de toute façon sur le plus grand
# de ce fichier et de MAX(ariane_num) en base : la base fait autorité.
echo "[$(date -u '+%H:%M:%S')] ArianeWeb..." >> $LOG
# Code de sortie : 0 = OK (le journal dit « 0 nouvelle décision » s'il y a lieu),
# 3 = aucune décision nouvelle au sommet depuis plus de ARIANE_ALERTE_JOURS jours
# (moisson morte : du 11/09 au 2/10/2026 ce cron écrivait « OK » chaque jour
# pour +0, audit du 2 oct. 2026, F2), 124 = timeout, autre = erreur.
ariane_rc=0
timeout 1800 sudo -u justicelibre python3 -u scrape_ariane.py >> $LOG 2>&1 || ariane_rc=$?
case $ariane_rc in
  0)   echo "[$(date -u '+%H:%M:%S')] ArianeWeb OK" >> $LOG ;;
  3)   echo "[$(date -u '+%H:%M:%S')] ArianeWeb ERREUR : moisson morte (0 décision nouvelle depuis plusieurs jours)" >> $LOG
       echo "$(date -u '+%Y-%m-%d %H:%M') ariane : ERREUR moisson morte (scrape_ariane.py code 3), voir $LOG" \
         >> /var/log/justicelibre/couverture_alertes.txt 2>/dev/null || true ;;
  124) echo "[$(date -u '+%H:%M:%S')] ArianeWeb timeout (non-fatal)" >> $LOG ;;
  *)   echo "[$(date -u '+%H:%M:%S')] ArianeWeb ERREUR code $ariane_rc (non-fatal)" >> $LOG ;;
esac

echo "[$(date -u '+%H:%M:%S')] daily incremental DONE" >> $LOG
