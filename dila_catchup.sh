#!/bin/bash
# Catch-up DILA : télécharge et applique TOUS les tarballs manquants
# depuis une date de départ. Utilise le listing HTTP (regex) au lieu de
# deviner les heures. Idempotent : parse_dila_bulk.py fait INSERT OR
# IGNORE/REPLACE selon le fond → ré-appliquer un tarball déjà ingéré est
# no-op.
#
# Usage : ./dila_catchup.sh <fond> <YYYYMMDD_since>
#   ex : ./dila_catchup.sh legi 20260101
#
# Fond supportés : legi, jorf, jade, kali, cnil
set -e
FUND="${1:?fund required (legi/jorf/jade/kali/cnil)}"
SINCE="${2:?since date YYYYMMDD required}"
FUND_UP="${FUND^^}"
LOG="/var/log/justicelibre/dila_catchup_${FUND}.log"
WORK="/opt/justicelibre/dila_bulk"
mkdir -p "$WORK" /var/log/justicelibre
cd /opt/justicelibre

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] catchup $FUND since $SINCE" | tee -a "$LOG"

# Liste TOUS les tarballs du fond >= SINCE, triés chrono
TARBALLS=$(curl -sS "https://echanges.dila.gouv.fr/OPENDATA/${FUND_UP}/" \
  | grep -oE "${FUND_UP}_[0-9]{8}-[0-9]+\.tar\.gz" | sort -u \
  | awk -v since="$SINCE" -F_ '{ split($2, a, "-"); if (a[1] >= since) print }')

TOTAL=$(echo "$TARBALLS" | grep -c . || echo 0)
echo "[catchup] $TOTAL tarballs à appliquer" | tee -a "$LOG"
i=0
for tb in $TARBALLS; do
  i=$((i+1))
  url="https://echanges.dila.gouv.fr/OPENDATA/${FUND_UP}/${tb}"
  echo "[$(date -u '+%H:%M:%S')] [$i/$TOTAL] $tb" | tee -a "$LOG"
  if ! curl -sf --max-time 300 "$url" -o "$WORK/Freemium_${FUND}.tar.gz"; then
    echo "  → download FAILED, skip" | tee -a "$LOG"
    continue
  fi
  size=$(stat -c%s "$WORK/Freemium_${FUND}.tar.gz")
  if [ "$size" -lt 200 ]; then
    echo "  → empty (${size}b), skip" | tee -a "$LOG"
    rm -f "$WORK/Freemium_${FUND}.tar.gz"
    continue
  fi
  # parse (parse_dila_bulk.py réutilise le nom Freemium_${fund}.tar.gz)
  if timeout 600 python3 -u parse_dila_bulk.py "$FUND" >> "$LOG" 2>&1; then
    echo "  → parse OK" | tee -a "$LOG"
  else
    echo "  → parse FAILED" | tee -a "$LOG"
  fi
  rm -f "$WORK/Freemium_${FUND}.tar.gz"
done
echo "[$(date -u '+%H:%M:%S')] catchup $FUND done" | tee -a "$LOG"
