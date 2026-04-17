#!/bin/bash
# Weekly DILA update script - downloads latest increments and re-indexes
# Run via cron: 0 4 * * 1  /opt/justicelibre/update_dila.sh >> /var/log/justicelibre-update.log 2>&1

set -e
DILA_DIR="/opt/justicelibre/dila"
DB_PATH="$DILA_DIR/judiciaire.db"
INCREMENTS_DIR="$DILA_DIR/increments"

mkdir -p "$INCREMENTS_DIR"

echo "$(date) - Starting DILA update"

# Download latest CASS increment
LATEST_CASS=$(curl -s "https://echanges.dila.gouv.fr/OPENDATA/CASS/" | grep -oP 'CASS_[0-9]{8}-[0-9]+\.tar\.gz' | sort -u | tail -1)
if [ -n "$LATEST_CASS" ] && [ ! -f "$INCREMENTS_DIR/$LATEST_CASS" ]; then
    echo "Downloading $LATEST_CASS..."
    curl -L -s -o "$INCREMENTS_DIR/$LATEST_CASS" "https://echanges.dila.gouv.fr/OPENDATA/CASS/$LATEST_CASS"
    mkdir -p "$DILA_DIR/new_cass"
    tar xzf "$INCREMENTS_DIR/$LATEST_CASS" -C "$DILA_DIR/new_cass"
    echo "Extracted $(find $DILA_DIR/new_cass -name '*.xml' | wc -l) CASS XML files"
    # Index new files
    python3 /opt/justicelibre/index_dila.py "$DILA_DIR/new_cass" "$DB_PATH"
    rm -rf "$DILA_DIR/new_cass"
else
    echo "No new CASS increment"
fi

# Download latest CAPP increment
LATEST_CAPP=$(curl -s "https://echanges.dila.gouv.fr/OPENDATA/CAPP/" | grep -oP 'CAPP_[0-9]{8}-[0-9]+\.tar\.gz' | sort -u | tail -1)
if [ -n "$LATEST_CAPP" ] && [ ! -f "$INCREMENTS_DIR/$LATEST_CAPP" ]; then
    echo "Downloading $LATEST_CAPP..."
    curl -L -s -o "$INCREMENTS_DIR/$LATEST_CAPP" "https://echanges.dila.gouv.fr/OPENDATA/CAPP/$LATEST_CAPP"
    mkdir -p "$DILA_DIR/new_capp"
    tar xzf "$INCREMENTS_DIR/$LATEST_CAPP" -C "$DILA_DIR/new_capp"
    echo "Extracted $(find $DILA_DIR/new_capp -name '*.xml' | wc -l) CAPP XML files"
    python3 /opt/justicelibre/index_dila.py "$DILA_DIR/new_capp" "$DB_PATH"
    rm -rf "$DILA_DIR/new_capp"
else
    echo "No new CAPP increment"
fi

# Download latest INCA increment
LATEST_INCA=$(curl -s "https://echanges.dila.gouv.fr/OPENDATA/INCA/" | grep -oP 'INCA_[0-9]{8}-[0-9]+\.tar\.gz' | sort -u | tail -1)
if [ -n "$LATEST_INCA" ] && [ ! -f "$INCREMENTS_DIR/$LATEST_INCA" ]; then
    echo "Downloading $LATEST_INCA..."
    curl -L -s -o "$INCREMENTS_DIR/$LATEST_INCA" "https://echanges.dila.gouv.fr/OPENDATA/INCA/$LATEST_INCA"
    mkdir -p "$DILA_DIR/new_inca"
    tar xzf "$INCREMENTS_DIR/$LATEST_INCA" -C "$DILA_DIR/new_inca"
    echo "Extracted $(find $DILA_DIR/new_inca -name '*.xml' | wc -l) INCA XML files"
    python3 /opt/justicelibre/index_dila.py "$DILA_DIR/new_inca" "$DB_PATH"
    rm -rf "$DILA_DIR/new_inca"
else
    echo "No new INCA increment"
fi

TOTAL=$(python3 -c "import sqlite3; print(sqlite3.connect('$DB_PATH').execute('SELECT COUNT(*) FROM decisions').fetchone()[0])")
echo "$(date) - Update complete. Total decisions: $TOTAL"
