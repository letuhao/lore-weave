#!/usr/bin/env bash
# L1.K.1 meta-write-discipline-lint.sh — I8 / S04 §12T.6
#
# Forbids direct INSERT/UPDATE/DELETE on meta tables OUTSIDE contracts/meta/.
# Services MUST go through MetaWrite() so the same-TX audit invariant holds.
# Exit 0 = clean; 1 = violations; 2 = misuse.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# Authoritative table list — derived from migrations/meta/*.up.sql filenames.
meta_tables=$(ls "$repo_root/migrations/meta/" 2>/dev/null | grep -E '^[0-9]+_.*\.up\.sql$' | sed -E 's/^[0-9]+_(.*)\.up\.sql$/\1/' || true)

if [[ -z "$meta_tables" ]]; then
  echo "[meta-write-discipline] no meta tables discovered; nothing to lint"
  exit 0
fi

scan_dirs=(
  "$repo_root/services"
  "$repo_root/crates"
  "$repo_root/frontend-game"
)

for table in $meta_tables; do
  # Match INSERT INTO <table>, UPDATE <table>, DELETE FROM <table>
  # in Go/Rust/SQL/TS files OUTSIDE contracts/meta.
  hits=$(grep -rniE "(INSERT[[:space:]]+INTO[[:space:]]+${table}|UPDATE[[:space:]]+${table}|DELETE[[:space:]]+FROM[[:space:]]+${table})" \
    --include='*.go' --include='*.rs' --include='*.sql' --include='*.ts' \
    "${scan_dirs[@]}" 2>/dev/null \
    | grep -vE '/contracts/meta/' \
    | grep -vE '/crates/meta-rs/' \
    | grep -vE 'migrations/meta/' \
    | grep -vE '_test\.(go|rs|ts)' \
    | grep -vE ':[[:space:]]*(//|--|#|\*|///)' || true)
  if [[ -n "$hits" ]]; then
    echo "[meta-write-discipline] FAIL — direct write on meta table $table outside contracts/meta:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[meta-write-discipline] FAIL — $violations table(s) with direct writes (I8 / S04 §12T.6)"
  exit 1
fi
echo "[meta-write-discipline] PASS"
exit 0
