#!/usr/bin/env bash
# Nightly database backup (spec §18). Add to cron: 0 2 * * * /path/deploy/backup.sh
set -euo pipefail

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$OUT_DIR"

docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-tradebot}" \
  "${POSTGRES_DB:-tradebot}" | gzip > "$OUT_DIR/tradebot_$STAMP.sql.gz"

# Retain last 14 days
find "$OUT_DIR" -name "tradebot_*.sql.gz" -mtime +14 -delete
echo "Backup written to $OUT_DIR/tradebot_$STAMP.sql.gz"
