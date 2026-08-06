#!/bin/bash
# Nattlig snapshot av SQLite-databasen (körs via markrounding-backup.timer).
# Tar en konsistent kopia inifrån containern med sqlite3 .backup, gzippar
# till BACKUP_DIR och roterar bort snapshots äldre än 14 dagar.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/markrounding/backups}"
CONTAINER="${CONTAINER:-markrounding-web}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y-%m-%d)"
TARGET="$BACKUP_DIR/markrounding-$STAMP.sqlite"

# sqlite3 saknas i python:3.12-slim — kör backupen via Pythons sqlite3-modul.
docker exec "$CONTAINER" python3 -c "
import sqlite3
src = sqlite3.connect('/app/data/markrounding.sqlite')
dst = sqlite3.connect('/app/data/backup-tmp.sqlite')
src.backup(dst)
dst.close(); src.close()
"
docker cp "$CONTAINER:/app/data/backup-tmp.sqlite" "$TARGET"
docker exec "$CONTAINER" rm -f /app/data/backup-tmp.sqlite
gzip -f "$TARGET"

find "$BACKUP_DIR" -name 'markrounding-*.sqlite.gz' -mtime "+$KEEP_DAYS" -delete
echo "Backup klar: $TARGET.gz"
