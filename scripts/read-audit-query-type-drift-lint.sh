#!/usr/bin/env bash
# read-audit-query-type-drift-lint.sh — D-READAUDIT-ENUM-DRIFT gate.
#
# Asserts the meta_read_audit.query_type CHECK enum (as defined by the LATEST
# migration that (re)defines meta_read_audit_query_type_enum) lists EXACTLY the
# id set in the SSOT contracts/meta/meta-sensitive-read-paths.yml. This prevents
# the DB CHECK and the contract from silently drifting — the exact bug that let
# migration 014 ship `unbounded_select`/`consent_audit_export` (never in the
# contract, never written) while the contract's `bulk_meta_query` was absent
# from the CHECK, and `bulk_pii_read` (written by the contracts/pii SDK) was
# absent from the contract.
#
# Exit 0 = in sync; 1 = drift; 2 = misuse.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
yaml="$repo_root/contracts/meta/meta-sensitive-read-paths.yml"
mig_dir="$repo_root/migrations/meta"

if [[ ! -f "$yaml" ]]; then
  echo "[read-audit-drift] MISUSE — contract YAML not found: $yaml" >&2
  exit 2
fi

# 1. YAML SSOT ids: the `- id: <value>` entries.
yaml_ids="$(grep -E '^[[:space:]]*-[[:space:]]*id:' "$yaml" \
  | sed -E 's/^[[:space:]]*-[[:space:]]*id:[[:space:]]*//' \
  | tr -d "\"'" \
  | sort -u)"

# 2. Latest migration that (re)defines the query_type CHECK constraint.
latest_mig="$(grep -lE 'meta_read_audit_query_type_enum[[:space:]]+CHECK' "$mig_dir"/*.up.sql \
  | sort -V | tail -1)"
if [[ -z "$latest_mig" ]]; then
  echo "[read-audit-drift] MISUSE — no migration defines meta_read_audit_query_type_enum" >&2
  exit 2
fi

# 3. CHECK ids = single-quoted tokens in that migration. It is a FOCUSED ALTER
#    (only the query_type CHECK), so every single-quoted [a-z_] token is an id;
#    the constraint name is unquoted and comments reference ids in `backticks`.
check_ids="$(grep -oE "'[a-z_]+'" "$latest_mig" | tr -d "'" | sort -u)"

if [[ "$yaml_ids" == "$check_ids" ]]; then
  count="$(printf '%s\n' "$yaml_ids" | grep -c .)"
  echo "[read-audit-drift] PASS — meta_read_audit query_type CHECK == YAML SSOT ($count ids, $(basename "$latest_mig"))"
  exit 0
fi

echo "[read-audit-drift] FAIL — meta_read_audit query_type CHECK ($(basename "$latest_mig")) drifted from contracts/meta/meta-sensitive-read-paths.yml"
echo "  only in YAML:  $(comm -23 <(printf '%s\n' "$yaml_ids") <(printf '%s\n' "$check_ids") | tr '\n' ' ')"
echo "  only in CHECK: $(comm -13 <(printf '%s\n' "$yaml_ids") <(printf '%s\n' "$check_ids") | tr '\n' ' ')"
exit 1
