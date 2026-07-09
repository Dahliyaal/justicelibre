#!/bin/bash
# Daily DILA delta updater — pulls yesterday's incremental tarballs for each
# fond and runs parse_dila_bulk.py to merge into existing SQLite DBs.
#
# Install : cron 0 4 * * *  /opt/justicelibre/scripts/dila_update_daily.sh
#
# DILA publie à des heures VARIABLES chaque jour (jamais 14:00 comme le disait
# l'ancienne version). On liste donc le répertoire HTTP et on prend TOUS les
# tarballs de la date visée. Idempotent : parse_dila_bulk.py fait
# INSERT OR IGNORE/REPLACE → ré-ingérer une décision déjà présente = no-op.
set -e
LOG=/var/log/justicelibre/dila_update.log
WORK=/opt/justicelibre/dila_bulk
mkdir -p "$WORK" /var/log/justicelibre

# Fonds à mettre à jour (skip CASS/CAPP/CONSTIT — vivent dans judiciaire.db)
FUNDS=(legi jorf jade kali cnil)

# Delta d'hier (DILA publie en soirée, cron à 04h → J-1)
YESTERDAY=$(date -u -d "yesterday" +%Y%m%d)

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] DILA daily update pour ${YESTERDAY}" >> "$LOG"

for fund in "${FUNDS[@]}"; do
  FUND_UP="${fund^^}"
  # Liste TOUS les tarballs de $YESTERDAY (heures variables : 002403, 140000,
  # 212647, etc). Il peut y en avoir plusieurs par jour → on les prend tous
  # en ordre chronologique.
  TARBALLS=$(curl -sS "https://echanges.dila.gouv.fr/OPENDATA/${FUND_UP}/" \
    | grep -oE "${FUND_UP}_${YESTERDAY}-[0-9]+\.tar\.gz" | sort -u)
  N=$(echo "$TARBALLS" | grep -c . || echo 0)
  if [ "$N" -eq 0 ]; then
    echo "[$(date -u '+%H:%M:%S')] $fund: aucun delta pour ${YESTERDAY}" >> "$LOG"
    continue
  fi
  echo "[$(date -u '+%H:%M:%S')] $fund: $N delta(s) à appliquer" >> "$LOG"

  for tb in $TARBALLS; do
    url="https://echanges.dila.gouv.fr/OPENDATA/${FUND_UP}/${tb}"
    out="$WORK/Freemium_${fund}.tar.gz"
    echo "[$(date -u '+%H:%M:%S')] $fund: fetch $tb" >> "$LOG"
    if ! curl -sf --max-time 600 "$url" -o "$out"; then
      echo "[$(date -u '+%H:%M:%S')] $fund: download FAILED" >> "$LOG"
      continue
    fi
    size=$(stat -c%s "$out")
    if [ "$size" -lt 200 ]; then
      echo "[$(date -u '+%H:%M:%S')] $fund: empty (${size}b), skip" >> "$LOG"
      rm -f "$out"
      continue
    fi
    cd /opt/justicelibre
    if timeout 900 python3 -u parse_dila_bulk.py "$fund" >> "$LOG" 2>&1; then
      echo "[$(date -u '+%H:%M:%S')] $fund: parse OK ($(du -h $out | cut -f1))" >> "$LOG"
    else
      echo "[$(date -u '+%H:%M:%S')] $fund: parse FAILED" >> "$LOG"
    fi
    rm -f "$out"
  done
done

echo "[$(date -u '+%H:%M:%S')] daily update done" >> "$LOG"
