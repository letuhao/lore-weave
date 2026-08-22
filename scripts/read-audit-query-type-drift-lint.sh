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
# Exit 0 = in sync; 1 = drift; 2 = misuse / selftest failure / parsed nothing.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12), and it closed a hole that made
# the gate's central comparison capable of passing over nothing.
#
# ⚠️ **`empty == empty` WAS A PASS.** The whole gate is one string comparison
# between two grep outputs. If either pattern stopped matching — a renamed
# constraint, a reformatted YAML, a migration that quotes ids differently — both
# sides collapse to "" , the equality holds, and it printed
# *"PASS — CHECK == YAML SSOT (0 ids)"*. A drift detector that reports agreement
# because it parsed nothing is the purest form of the defect it exists to catch,
# and the `(0 ids)` in its own success line was the tell nobody read.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# --- PREDICATES, extracted so cases can drive them --------------------------

# The SSOT ids: the `- id: <value>` entries.
yaml_ids() {
  grep -E '^[[:space:]]*-[[:space:]]*id:' "$1" \
    | sed -E 's/^[[:space:]]*-[[:space:]]*id:[[:space:]]*//' \
    | tr -d "\"'" \
    | sort -u
}

# CHECK ids = single-quoted tokens in that migration. It is a FOCUSED ALTER
# (only the query_type CHECK), so every single-quoted [a-z_] token is an id;
# the constraint name is unquoted and comments reference ids in `backticks`.
check_ids() {
  grep -oE "'[a-z_]+'" "$1" | tr -d "'" | sort -u
}

# The latest migration that (re)defines the query_type CHECK constraint.
latest_check_migration() {
  grep -lE 'meta_read_audit_query_type_enum[[:space:]]+CHECK' "$1"/*.up.sql 2>/dev/null \
    | sort -V | tail -1
}

run_lint() {
  local yaml="${1:-$repo_root/contracts/meta/meta-sensitive-read-paths.yml}"
  local mig_dir="${2:-$repo_root/migrations/meta}"
  local latest_mig y c ny nc

  if [[ ! -f "$yaml" ]]; then
    echo "[read-audit-drift] MISUSE — contract YAML not found: $yaml" >&2
    exit 2
  fi

  latest_mig="$(latest_check_migration "$mig_dir")"
  if [[ -z "$latest_mig" ]]; then
    echo "[read-audit-drift] MISUSE — no migration defines meta_read_audit_query_type_enum" >&2
    exit 2
  fi

  y="$(yaml_ids "$yaml")"
  c="$(check_ids "$latest_mig")"
  ny="$(printf '%s\n' "$y" | grep -c . || true)"
  nc="$(printf '%s\n' "$c" | grep -c . || true)"

  # **REACH FLOOR, and it is the whole point.** Both sides must have parsed
  # SOMETHING before their equality means anything: two empty sets are equal,
  # and that equality was reported as agreement for as long as this gate has
  # existed. Checked BEFORE the comparison, because after it the answer is
  # already wrong.
  if [[ "$ny" -lt 1 || "$nc" -lt 1 ]]; then
    echo "[read-audit-drift] FAIL — parsed $ny id(s) from the YAML and $nc from" >&2
    echo "  $(basename "$latest_mig"). An empty side makes the comparison vacuous:" >&2
    echo "  two empty sets are equal, and this gate would call that agreement." >&2
    exit 2
  fi

  if [[ "$y" == "$c" ]]; then
    echo "[read-audit-drift] PASS — meta_read_audit query_type CHECK == YAML SSOT ($ny ids, $(basename "$latest_mig"))"
    exit 0
  fi

  echo "[read-audit-drift] FAIL — meta_read_audit query_type CHECK ($(basename "$latest_mig")) drifted from $(basename "$yaml")"
  echo "  only in YAML:  $(comm -23 <(printf '%s\n' "$y") <(printf '%s\n' "$c") | tr '\n' ' ')"
  echo "  only in CHECK: $(comm -13 <(printf '%s\n' "$y") <(printf '%s\n' "$c") | tr '\n' ' ')"
  exit 1
}

# Drive the REAL run_lint over a synthetic pair and print its exit code.
_probe() {  # $1 = yaml text, $2 = migration text
  local d rc=0
  d="$(mktemp -d)"
  printf '%s' "$1" > "$d/paths.yml"
  mkdir -p "$d/migs"
  printf '%s' "$2" > "$d/migs/001_x.up.sql"
  ( run_lint "$d/paths.yml" "$d/migs" ) >/dev/null 2>&1 || rc=$?
  rm -rf "$d"
  printf '%s' "$rc"
}

selftest() {
  local rc
  local ok_yaml=$'paths:\n  - id: bulk_pii_read\n    why: x\n  - id: bulk_meta_query\n'
  local ok_mig=$'ALTER TABLE meta_read_audit ADD CONSTRAINT meta_read_audit_query_type_enum CHECK (\n  query_type IN (\'bulk_meta_query\', \'bulk_pii_read\')\n);\n'

  # In sync -> 0.
  rc=$(_probe "$ok_yaml" "$ok_mig")
  [[ "$rc" == "0" ]] || { echo "[read-audit-drift] SELFTEST FAIL — an IN-SYNC pair did not pass (rc=$rc, cry-wolf)"; exit 2; }

  # An id only in the CHECK -> drift.
  rc=$(_probe "$ok_yaml" $'ALTER TABLE x ADD CONSTRAINT meta_read_audit_query_type_enum CHECK (\n  query_type IN (\'bulk_meta_query\', \'bulk_pii_read\', \'unbounded_select\')\n);\n')
  [[ "$rc" == "1" ]] || { echo "[read-audit-drift] SELFTEST FAIL — an id present ONLY in the CHECK was not reported (rc=$rc, vacuous)"; exit 2; }

  # An id only in the YAML -> drift. Both directions, because `comm` reports
  # them separately and a one-sided comparison would pass half the time.
  rc=$(_probe $'paths:\n  - id: bulk_pii_read\n  - id: bulk_meta_query\n  - id: ghost_id\n' "$ok_mig")
  [[ "$rc" == "1" ]] || { echo "[read-audit-drift] SELFTEST FAIL — an id present ONLY in the YAML was not reported (rc=$rc, vacuous)"; exit 2; }

  # THE FLOOR — the hole this gate shipped with. Both sides empty are EQUAL.
  rc=$(_probe $'paths: []\n' $'-- meta_read_audit_query_type_enum CHECK, no quoted ids at all\n')
  [[ "$rc" == "2" ]] || { echo "[read-audit-drift] SELFTEST FAIL — TWO EMPTY SETS compared equal and were called agreement (rc=$rc)"; exit 2; }

  # ...and one empty side alone must not read as drift-free either.
  rc=$(_probe $'paths: []\n' "$ok_mig")
  [[ "$rc" == "2" ]] || { echo "[read-audit-drift] SELFTEST FAIL — an EMPTY YAML side did not trip the floor (rc=$rc)"; exit 2; }

  # No migration defines the constraint at all -> misuse, not a pass.
  rc=$(_probe "$ok_yaml" $'SELECT 1;\n')
  [[ "$rc" == "2" ]] || { echo "[read-audit-drift] SELFTEST FAIL — a migration set defining NO constraint did not report misuse (rc=$rc)"; exit 2; }

  echo "[read-audit-drift] SELFTEST PASS — an in-sync pair passes; drift is reported from BOTH"
  echo "  directions (id only in the CHECK, id only in the YAML); two empty sets are refused"
  echo "  rather than called agreement; and a migration set defining no constraint is misuse"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
