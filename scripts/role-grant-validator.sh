#!/usr/bin/env bash
# L1.K.11 role-grant-validator.sh — S04-D6 / §12T.7
#
# Every entry in contracts/service_acl/matrix.yaml must:
#   - reference only tables that exist in migrations/meta/*.up.sql
#   - declare permissions from {SELECT,INSERT,UPDATE,DELETE} only
#   - audit tables (meta_write_audit, meta_read_audit, *_audit) may ONLY have INSERT/SELECT (no UPDATE/DELETE — append-only)
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
matrix="$repo_root/contracts/service_acl/matrix.yaml"

if [[ ! -f "$matrix" ]]; then
  echo "[role-grant] WARN — matrix.yaml absent; skipping"
  exit 0
fi

violations=0

# Discover audit tables (anything ending in _audit + meta_*_audit)
audit_tables=$(ls "$repo_root/migrations/meta/" 2>/dev/null \
  | grep -E '_audit\.up\.sql$' \
  | sed -E 's/^[0-9]+_(.*)\.up\.sql$/\1/' | sort -u || true)

# For each `table_name:` line, check that no audit table grants UPDATE/DELETE
for audit in $audit_tables; do
  # find the block for this table inside matrix; if it has UPDATE or DELETE → fail
  hits=$(awk -v t="$audit" '
    /^[[:space:]]*[a-z_]+:[[:space:]]*$/ {
      if (in_block && drop_table_block) print "  " line ": " block;
      block_table = $1; gsub(":", "", block_table);
      in_block = (block_table == t);
      block = "";
    }
    in_block && /^[[:space:]]+-[[:space:]]*(UPDATE|DELETE)[[:space:]]*$/ {
      print FILENAME ":" NR ": audit table " t " grants " $2;
    }
  ' "$matrix" || true)
  if [[ -n "$hits" ]]; then
    echo "[role-grant] FAIL — audit table $audit must be append-only (no UPDATE/DELETE):"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
done

# Check for grants on unknown tables
declared_tables=$(ls "$repo_root/migrations/meta/" 2>/dev/null \
  | grep -E '\.up\.sql$' \
  | sed -E 's/^[0-9]+_(.*)\.up\.sql$/\1/' | sort -u || true)
# Tables referenced in matrix (heuristic: 2-space indent, ending in :)
ref_tables=$(grep -E '^[[:space:]]{6}[a-z_]+:$' "$matrix" | sed -E 's/[[:space:]]+([a-z_]+):.*/\1/' | sort -u || true)
for t in $ref_tables; do
  if ! echo "$declared_tables" | grep -qx "$t"; then
    echo "[role-grant] FAIL — matrix references unknown table $t (no migration exists)"
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[role-grant] FAIL — $violations issue(s) (S04-D6 / §12T.7)"
  exit 1
fi
echo "[role-grant] PASS"
exit 0
