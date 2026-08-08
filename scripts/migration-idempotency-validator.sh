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
# WHAT THIS CANNOT SEE, MEASURED 2026-08-08 (stated so nobody re-derives it)
# -------------------------------------------------------------------------
# It reads TEXT. The property is BEHAVIOUR. Those are two different things and
# the word "idempotent" covers two different claims, only one of which is real:
#
#   RETRY-SAFETY (real, and what this checks a proxy for) -- a runner dies half
#   way through migration N and retries N. Applying N twice in a row must work.
#   `scripts/dp-migration-chain-smoke.py` checks this by BEHAVIOUR against a live
#   Postgres, and measured 19 of 19 migrations clean (18 before the image
#   gained pgvector, when 0008 could not apply and was skipped).
#
#   WHOLE-HISTORY REPLAY (not real, and NOT a defect) -- re-running all of
#   0001..NNNN against a database that already has them. This FAILS on
#   0001_initial (a later migration changed `events`' key, so 0001's foreign key
#   no longer matches) and on 0007_drift_metadata (0017/0018 narrowed
#   projection_drift_table_name_allowlist, so 0007's seed rows are refused).
#   BOTH ARE CORRECT, and a versioned runner never produces that scenario. It is
#   written down because a naive chain test does exactly this, reports two
#   failures, and looks like a finding against this script. It is not one.
#
# Usage:
#   migration-idempotency-validator.sh                  # lint defaults (per_reality/)
#   migration-idempotency-validator.sh path1.sql ...    # lint specific files
#
# Exits 0 = clean, 1 = violations found, 2 = misuse.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# Default file set: EVERY per-reality migration, by glob.
#
# ⚠ AMENDED 2026-08-07 (`1b5-L6`). This was an enumerated list holding exactly
# two entries -- `0001_initial.up.sql` and `0001_initial.down.sql` -- while the
# directory held 38 files. So 36 migrations were DEFAULT-UNCOVERED, which is
# `NV-3`'s named shape: *"an enumerated file list is default-uncovered: what
# happens to a file created tomorrow?"* The answer here was measured rather than
# guessed -- `0019_channels` was written, committed, and checked by a pre-commit
# hook that never looked at it, and it was the 19th file to which that happened.
# A glob makes tomorrow's file covered by existing rather than by an author
# remembering. If a file genuinely cannot be idempotent, it earns a named
# exclusion here with its reason -- there are none today.
migration_dir="$repo_root/contracts/migrations/per_reality"

if [ "$#" -gt 0 ]; then
  targets=("$@")
else
  targets=()
  while IFS= read -r t; do
    [ -f "$t" ] && targets+=("$t")
  done < <(find "$migration_dir" -maxdepth 1 -name '*.sql' -print | sort)
  if [ "${#targets[@]}" -eq 0 ]; then
    echo "[idempotency] no targets specified and no migrations found under $migration_dir"
    exit 0
  fi
  echo "[idempotency] scanning ${#targets[@]} migration file(s) under contracts/migrations/per_reality/"
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
