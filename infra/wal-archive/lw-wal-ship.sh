#!/usr/bin/env bash
# infra/wal-archive/lw-wal-ship.sh
#
# L1.E.7 — WAL ship script invoked by Postgres archive_command every 60s
# (per archive_timeout in infra/postgres/postgresql.conf).
#
# Usage (called by Postgres, not directly):
#   lw-wal-ship.sh <WAL_PATH> <WAL_FILENAME>
#
# Behavior:
#   - Validates WAL file exists locally
#   - Uploads to MinIO/S3 bucket `lw-meta-wal-archive` under prefix
#     <YYYY>/<MM>/<DD>/<WAL_FILENAME>
#   - Returns 0 on success (Postgres marks segment archived) or non-zero on
#     failure (Postgres retries on next checkpoint)
#
# Per OPEN_QUESTIONS_LOCKED.md Q-L1H-1: bucket is pre-provisioned by foundation
# infra/minio/lw-db-backups-bucket.tf (L1.H.3, ships in later cycle); for V1
# staging this script tolerates missing bucket by exiting non-zero so Postgres
# retries — this is the documented behaviour, NOT a silent failure.

set -euo pipefail

WAL_PATH="${1:-}"
WAL_FILENAME="${2:-}"

if [ -z "$WAL_PATH" ] || [ -z "$WAL_FILENAME" ]; then
  echo "[lw-wal-ship] usage: lw-wal-ship.sh <wal_path> <wal_filename>" >&2
  exit 64
fi

if [ ! -f "$WAL_PATH" ]; then
  echo "[lw-wal-ship] ERROR: WAL file missing: $WAL_PATH" >&2
  exit 65
fi

# Bucket + endpoint resolved from env (set by docker-compose.meta-ha.yml or systemd unit)
: "${WAL_ARCHIVE_BUCKET:=lw-meta-wal-archive}"
: "${WAL_ARCHIVE_ENDPOINT:=http://minio:9000}"
: "${WAL_ARCHIVE_ACCESS_KEY:?WAL_ARCHIVE_ACCESS_KEY required}"
: "${WAL_ARCHIVE_SECRET_KEY:?WAL_ARCHIVE_SECRET_KEY required}"

# Date-partition prefix for restore tooling readability
YYYY="$(date -u +%Y)"
MM="$(date -u +%m)"
DD="$(date -u +%d)"
OBJECT_KEY="${YYYY}/${MM}/${DD}/${WAL_FILENAME}"

# Use mc (MinIO client) if available; fallback to aws-cli (S3-compatible)
if command -v mc >/dev/null 2>&1; then
  mc alias set wal-archive "$WAL_ARCHIVE_ENDPOINT" "$WAL_ARCHIVE_ACCESS_KEY" "$WAL_ARCHIVE_SECRET_KEY" --quiet
  mc cp --quiet "$WAL_PATH" "wal-archive/${WAL_ARCHIVE_BUCKET}/${OBJECT_KEY}" >&2
elif command -v aws >/dev/null 2>&1; then
  AWS_ACCESS_KEY_ID="$WAL_ARCHIVE_ACCESS_KEY" \
  AWS_SECRET_ACCESS_KEY="$WAL_ARCHIVE_SECRET_KEY" \
    aws --endpoint-url "$WAL_ARCHIVE_ENDPOINT" \
        s3 cp "$WAL_PATH" "s3://${WAL_ARCHIVE_BUCKET}/${OBJECT_KEY}" \
        --no-progress >&2
else
  echo "[lw-wal-ship] ERROR: neither mc nor aws CLI found" >&2
  exit 66
fi

echo "[lw-wal-ship] shipped ${WAL_FILENAME} -> ${WAL_ARCHIVE_BUCKET}/${OBJECT_KEY}" >&2
exit 0
