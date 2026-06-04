#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/stocktake}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/stocktake-backup-$STAMP.tar.gz"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$BACKUP_DIR"

if [ ! -d "$APP_DIR/backend/data" ]; then
  echo "No data directory found at $APP_DIR/backend/data" >&2
  exit 1
fi

mkdir -p "$TMP_DIR/backend"
cp -a "$APP_DIR/backend/data" "$TMP_DIR/backend/data"

if command -v sqlite3 >/dev/null 2>&1 && [ -f "$APP_DIR/backend/data/stocktake.db" ]; then
  sqlite3 "$APP_DIR/backend/data/stocktake.db" ".backup '$TMP_DIR/backend/data/stocktake.db.backup'"
fi

cat > "$TMP_DIR/RESTORE.txt" <<EOF
StockTake backup created at $STAMP UTC.

Restore:
  sudo systemctl stop stocktake
  tar -xzf $OUT -C /tmp/stocktake-restore
  cp -a /tmp/stocktake-restore/backend/data /opt/stocktake/backend/
  sudo chown -R www-data:www-data /opt/stocktake/backend/data
  sudo systemctl start stocktake

If stocktake.db.backup exists, it was created with sqlite3 .backup and can be copied
over stocktake.db before restarting the service.
EOF

tar -czf "$OUT" -C "$TMP_DIR" .
chmod 0600 "$OUT"

echo "$OUT"
