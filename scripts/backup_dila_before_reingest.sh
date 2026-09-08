#!/bin/bash
# Sauvegarde des 9 bases DILA d'al-uzza vers la prod, compressées à la volée
# (zstd), AVANT la ré-ingestion du 8 septembre 2026. Prend le verrou
# d'ingestion pour figer les bases (checkpoint WAL avant copie).
#   systemd-run --unit=jl-backup-dila /bin/bash /opt/justicelibre/scripts/backup_dila_before_reingest.sh
set -u
LOG=/var/log/justicelibre/backup_reingest.log
REMOTE=root@46.225.190.237
RDIR=/opt/justicelibre/backups/dila-avant-reingestion-$(date -u +%Y%m%d)
mkdir -p /var/log/justicelibre
exec 9>/opt/justicelibre/dila_bulk/.ingest.lock
flock 9
ssh -o StrictHostKeyChecking=no $REMOTE "mkdir -p $RDIR" || exit 1
for db in constit cnil kali capp cass inca jade legi jorf; do
  src=/opt/justicelibre/dila/$db.db
  sqlite3 "$src" "PRAGMA wal_checkpoint(TRUNCATE)" >/dev/null 2>&1
  echo "[$(date -u '+%F %T')] $db ($(du -h "$src" | cut -f1)) → prod" >> $LOG
  if zstd -T4 -3 -c "$src" | ssh $REMOTE "cat > $RDIR/$db.db.zst"; then
    echo "[$(date -u '+%F %T')] $db OK : $(ssh $REMOTE "du -h $RDIR/$db.db.zst | cut -f1")" >> $LOG
  else
    echo "[$(date -u '+%F %T')] ⛔ $db ÉCHEC" >> $LOG; exit 2
  fi
done
echo "[$(date -u '+%F %T')] SAUVEGARDE TERMINÉE dans $REMOTE:$RDIR" >> $LOG
ssh $REMOTE "ls -la $RDIR; df -h / | tail -1" >> $LOG
