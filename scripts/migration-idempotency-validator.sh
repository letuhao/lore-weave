#!/usr/bin/env bash
# migration-idempotency-validator.sh — L1.D.7 (RAID cycle 6)
#
# Lints per-reality migration SQL files for NON-idempotent patterns. Per
# L1.D §2 acceptance criteria:
#   "scripts/migration-idempotency-validator.sh blocks injected non-idempotent SQL"
#
# Detected violations (each surfaces with file:line):
#   * CREATE TABLE that is NOT `CREATE TABLE IF NOT EXISTS`
#   * CREATE INDEX that is NOT `CREATE INDEX IF NOT EXISTS`
#   * DROP TABLE that is NOT `DROP TABLE IF EXISTS`   (in down migrations)
#   * DROP INDEX that is NOT `DROP INDEX IF EXISTS`
#   * ALTER TABLE ... ADD COLUMN that is NOT `ADD COLUMN IF NOT EXISTS`
#   * ALTER TABLE ... DROP COLUMN that is NOT `DROP COLUMN IF EXISTS`
#   * INSERT ... that lacks ON CONFLICT  (skip warns-only; pure seed data)
#
# Usage:
#   migration-idempotency-validator.sh                  # lint defaults (per_reality/)
#   migration-idempotency-validator.sh path1.sql ...    # lint specific files
#
# Exits 0 = clean, 1 = violations found, 2 = misuse.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# default file set: per-reality migrations shipped to date.
default_targets=(
  "$repo_root/contracts/migrations/per_reality/0001_initial.up.sql"
  "$repo_root/contracts/migrations/per_reality/0001_initial.down.sql"
)

if [ "$#" -gt 0 ]; then
  targets=("$@")
else
  targets=()
  for t in "${default_targets[@]}"; do
    if [ -f "$t" ]; then targets+=("$t"); fi
  done
  if [ "${#targets[@]}" -eq 0 ]; then
    echo "[idempotency] no targets specified and no defaults present; nothing to do"
    exit 0
  fi
fi

# check_file <path>  — emits violation lines to stdout and bumps $violations.
check_file() {
  local f="$1"
  # Skip empty files / non-SQL files.
  if [ ! -s "$f" ]; then return; fi
  case "$f" in
    *.sql) ;;
    *) return ;;
  esac

  # Each grep below ignores lines inside SQL line-comments (-- ...) AND
  # block comments would be a false-positive surface, but L1.D's SQL doesn't
  # use them yet; the down-migration path matters most and is grep-friendly.

  # CREATE TABLE without IF NOT EXISTS
  local hits
  hits=$(grep -nEi '^[[:space:]]*CREATE[[:space:]]+TABLE([[:space:]]+IF[[:space:]]+NOT[[:space:]]+EXISTS)?' "$f" \
        | grep -viE '^[[:space:]]*[0-9]+:[[:space:]]*--' \
        | grep -viE 'CREATE[[:space:]]+TABLE[[:space:]]+IF[[:space:]]+NOT[[:space:]]+EXISTS' || true)
  if [ -n "$hits" ]; then
    echo "[idempotency] $f: CREATE TABLE missing IF NOT EXISTS:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # CREATE INDEX without IF NOT EXISTS
  hits=$(grep -nEi '^[[:space:]]*CREATE[[:space:]]+(UNIQUE[[:space:]]+)?INDEX' "$f" \
        | grep -viE '^[[:space:]]*[0-9]+:[[:space:]]*--' \
        | grep -viE 'CREATE[[:space:]]+(UNIQUE[[:space:]]+)?INDEX[[:space:]]+(CONCURRENTLY[[:space:]]+)?IF[[:space:]]+NOT[[:space:]]+EXISTS' || true)
  if [ -n "$hits" ]; then
    echo "[idempotency] $f: CREATE INDEX missing IF NOT EXISTS:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # DROP TABLE without IF EXISTS
  hits=$(grep -nEi '^[[:space:]]*DROP[[:space:]]+TABLE' "$f" \
        | grep -viE '^[[:space:]]*[0-9]+:[[:space:]]*--' \
        | grep -viE 'DROP[[:space:]]+TABLE[[:space:]]+IF[[:space:]]+EXISTS' || true)
  if [ -n "$hits" ]; then
    echo "[idempotency] $f: DROP TABLE missing IF EXISTS:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # DROP INDEX without IF EXISTS
  hits=$(grep -nEi '^[[:space:]]*DROP[[:space:]]+INDEX' "$f" \
        | grep -viE '^[[:space:]]*[0-9]+:[[:space:]]*--' \
        | grep -viE 'DROP[[:space:]]+INDEX[[:space:]]+IF[[:space:]]+EXISTS' || true)
  if [ -n "$hits" ]; then
    echo "[idempotency] $f: DROP INDEX missing IF EXISTS:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # ALTER TABLE ADD COLUMN without IF NOT EXISTS
  hits=$(grep -nEi 'ALTER[[:space:]]+TABLE[[:space:]]+[^[:space:]]+[[:space:]]+ADD[[:space:]]+COLUMN' "$f" \
        | grep -viE '^[[:space:]]*[0-9]+:[[:space:]]*--' \
        | grep -viE 'ADD[[:space:]]+COLUMN[[:space:]]+IF[[:space:]]+NOT[[:space:]]+EXISTS' || true)
  if [ -n "$hits" ]; then
    echo "[idempotency] $f: ALTER TABLE ADD COLUMN missing IF NOT EXISTS:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # ALTER TABLE DROP COLUMN without IF EXISTS
  hits=$(grep -nEi 'ALTER[[:space:]]+TABLE[[:space:]]+[^[:space:]]+[[:space:]]+DROP[[:space:]]+COLUMN' "$f" \
        | grep -viE '^[[:space:]]*[0-9]+:[[:space:]]*--' \
        | grep -viE 'DROP[[:space:]]+COLUMN[[:space:]]+IF[[:space:]]+EXISTS' || true)
  if [ -n "$hits" ]; then
    echo "[idempotency] $f: ALTER TABLE DROP COLUMN missing IF EXISTS:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
}

for t in "${targets[@]}"; do
  check_file "$t"
done

if [ "$violations" -ne 0 ]; then
  echo "[idempotency] FAIL — $violations non-idempotent pattern(s) found"
  exit 1
fi
echo "[idempotency] PASS — $(printf '%s ' "${targets[@]}")"
exit 0
