#!/usr/bin/env bash
# =============================================================================
# Bookworm Database Backup Script
#
# Usage:
#   ./scripts/backup.sh
#
# Environment variables (set these or use a .env file):
#   DATABASE_URL    - PostgreSQL connection string (required)
#   BACKUP_DIR      - Local backup directory (default: ./backups)
#   BACKUP_RETAIN   - Days to keep local backups (default: 7)
#   S3_BUCKET       - S3-compatible bucket for offsite backup (optional)
#   S3_ENDPOINT     - Custom S3 endpoint for DigitalOcean/Backblaze (optional)
#
# Cron example (daily at 3 AM):
#   0 3 * * * cd /path/to/bookworm && ./scripts/backup.sh >> logs/backup.log 2>&1
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_RETAIN="${BACKUP_RETAIN:-7}"
FILENAME="bookworm_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

die() {
    log "ERROR: $1" >&2
    exit 1
}

# -----------------------------------------------------------------------------
# Preflight checks
# -----------------------------------------------------------------------------
if [ -z "${DATABASE_URL:-}" ]; then
    die "DATABASE_URL is not set. Export it or add to .env"
fi

command -v pg_dump >/dev/null 2>&1 || die "pg_dump not found. Install postgresql-client."
command -v gzip >/dev/null 2>&1 || die "gzip not found."

mkdir -p "${BACKUP_DIR}"

# -----------------------------------------------------------------------------
# Dump & compress
# -----------------------------------------------------------------------------
log "Starting backup → ${FILENAME}"

pg_dump "${DATABASE_URL}" \
    --no-owner \
    --no-privileges \
    --format=plain \
    --verbose 2>/dev/null \
    | gzip > "${FILEPATH}"

FILESIZE=$(du -h "${FILEPATH}" | cut -f1)
log "Backup complete: ${FILESIZE}"

# -----------------------------------------------------------------------------
# Upload to S3 (optional)
# -----------------------------------------------------------------------------
if [ -n "${S3_BUCKET:-}" ]; then
    command -v aws >/dev/null 2>&1 || die "aws CLI not found but S3_BUCKET is set."

    S3_PATH="s3://${S3_BUCKET}/bookworm-backups/${FILENAME}"
    S3_ARGS=""

    if [ -n "${S3_ENDPOINT:-}" ]; then
        S3_ARGS="--endpoint-url ${S3_ENDPOINT}"
    fi

    log "Uploading to ${S3_PATH}..."
    # shellcheck disable=SC2086
    aws s3 cp "${FILEPATH}" "${S3_PATH}" ${S3_ARGS} --quiet
    log "Upload complete."
fi

# -----------------------------------------------------------------------------
# Clean up old local backups
# -----------------------------------------------------------------------------
DELETED=$(find "${BACKUP_DIR}" -name "bookworm_*.sql.gz" -mtime +"${BACKUP_RETAIN}" -delete -print | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    log "Cleaned up ${DELETED} backup(s) older than ${BACKUP_RETAIN} days."
fi

log "Done."