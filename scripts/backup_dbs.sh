#!/bin/bash
# Backup hebdomadaire des SQLite DBs : al-uzza → PatrologiaLatina via SSH+zstd.
# Compress in-flight pour fit dans les 13 GB libres prod.
#
# A installer sur al-uzza :
#   chmod +x /opt/justicelibre/scripts/backup_dbs.sh
#   crontab -e :
#     0 3 * * 0   /opt/justicelibre/scripts/backup_dbs.sh   # dimanche 3h UTC
#
# Restore : ssh root@46.225.190.237 "cd /opt/justicelibre/backups && zstd -d <name>.zst"
#           puis rsync vers al-uzza.

set -e
LOG=/var/log/justicelibre/backup.log
mkdir -p /var/log/justicelibre

REMOTE_HOST="46.225.190.237"
REMOTE_DIR="/opt/justicelibre/backups"
LOCAL_DIR="/opt/justicelibre/dila"

DBS=(legi.db jade.db jorf.db kali.db cnil.db constit.db capp.db)
TS=$(date -u +%Y%m%d-%H%M)

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] backup start" >> $LOG

ssh -o StrictHostKeyChecking=no root@$REMOTE_HOST "mkdir -p $REMOTE_DIR && find $REMOTE_DIR -name '*.zst' -mtime +30 -delete" >> $LOG 2>&1

for db in "${DBS[@]}"; do
  src="$LOCAL_DIR/$db"
  if [ ! -f "$src" ]; then
    echo "[$(date -u '+%H:%M:%S')] $db missing, skip" >> $LOG
    continue
  fi
  size_mb=$(du -m "$src" | cut -f1)
  echo "[$(date -u '+%H:%M:%S')] $db (${size_mb}MB) → backup..." >> $LOG
  # Compress + transfer in one pipe to save local disk
  # SQLite WAL safety : .db can be hot-read (write-ahead log handled) but use
  # sqlite3 .dump to be 100% safe on large DBs. Pour vélocité on copie le fichier
  # en supposant pas d'écriture (OK : seul parse_dila_bulk.py écrit, et il tourne
  # en cron à 04h, ce backup est dimanche 03h).
  zstd -19 --long -T0 -c "$src" 2>>$LOG \
    | ssh -o StrictHostKeyChecking=no root@$REMOTE_HOST "cat > $REMOTE_DIR/${db}.${TS}.zst" \
    && echo "[$(date -u '+%H:%M:%S')] $db sent" >> $LOG \
    || echo "[$(date -u '+%H:%M:%S')] $db FAILED" >> $LOG
done

# Backup judiciaire.db de PROD : stream zstd direct vers le fichier compressé
# (PAS de .local intermediate qui bouffe 11 GB le temps de la compression).
ssh root@$REMOTE_HOST "zstd -19 --long -T0 -c /opt/justicelibre/dila/judiciaire.db > $REMOTE_DIR/judiciaire.${TS}.db.zst 2>>$LOG && echo 'judiciaire.db backed up'" >> $LOG 2>&1

echo "[$(date -u '+%H:%M:%S')] backup done. List:" >> $LOG
ssh root@$REMOTE_HOST "ls -lh $REMOTE_DIR/ | tail -10" >> $LOG 2>&1
