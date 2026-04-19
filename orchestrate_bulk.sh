#!/bin/bash
# Orchestre l'ingestion bulk DILA : attend chaque download, parse, delete.
# Doit tourner en parallèle du download_all.sh qui remplit /opt/justicelibre/dila_bulk/.
set -e
cd /opt/justicelibre
BULK=/opt/justicelibre/dila_bulk
LOG=/var/log/orchestrate_bulk.log

# Ordre d'ingestion (CASS skippé car redondant avec DILA archives existantes)
FUNDS=(legi jorf inca jade kali constit capp cnil)

echo "[$(date)] orchestrate_bulk START" >> $LOG

for fund in "${FUNDS[@]}"; do
  TAR="$BULK/Freemium_${fund}.tar.gz"
  echo "[$(date)] waiting for $TAR…" >> $LOG
  # Poll jusqu'à ce que download_all.sh ait fini CE tarball (flag: "DONE $FUND_UPPER")
  FUND_UP=$(echo $fund | tr a-z A-Z)
  while ! grep -q "DONE $FUND_UP" /var/log/dila_bulk.log 2>/dev/null; do
    sleep 30
  done
  # Sécurité : vérifier que le fichier existe et est > 1 MB
  if [ ! -f "$TAR" ] || [ $(stat -c%s "$TAR") -lt 1000000 ]; then
    echo "[$(date)] SKIP $fund (tarball missing/too small)" >> $LOG
    continue
  fi
  echo "[$(date)] PARSING $fund…" >> $LOG
  python3 -u parse_dila_bulk.py $fund >> $LOG 2>&1 || echo "[$(date)] PARSE FAILED $fund (continue)" >> $LOG
  # Delete du tarball pour libérer le disque
  SIZE=$(du -h "$TAR" | cut -f1)
  rm -f "$TAR"
  echo "[$(date)] DELETED $TAR ($SIZE freed)" >> $LOG
done

echo "[$(date)] orchestrate_bulk ALL DONE" >> $LOG
