#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

# Use custom PostgreSQL format for integrity checks and flexible restoration.
pg_dump --dbname="$DATABASE_URL" --format=custom --file="$BACKUP_DIR/trust_engine_${STAMP}.dump"

# Keep the working tree clean when this script is used in CI/local operations.
find "$BACKUP_DIR" -type f -name 'trust_engine_*.dump' -mtime +7 -delete
printf '%s\n' "$BACKUP_DIR/trust_engine_${STAMP}.dump"
