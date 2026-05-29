#!/usr/bin/env bash
# L1.K.15 meta-sensitive-read-bypass-lint.sh — S04 §12T.6
#
# Reads on enumerated sensitive paths (contracts/meta/meta-sensitive-read-paths.yml)
# MUST flow through contracts/meta/read_audit.go — bare SELECTs from outside
# the audit wrapper bypass the meta_read_audit row.
#
# Heuristic: forbid `SELECT * FROM player_character_index ... WHERE user_ref_id != ...`
# (non-owner queries) outside contracts/meta. Tighten in future cycles.
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
sensitive="$repo_root/contracts/meta/meta-sensitive-read-paths.yml"

if [[ ! -f "$sensitive" ]]; then
  echo "[meta-sensitive-read] WARN — meta-sensitive-read-paths.yml absent; skipping"
  exit 0
fi

violations=0

# Pull table names from sensitive paths YAML (heuristic: lines `table:` or
# `id: player_index_cross_user` pairs with the player_character_index table).
sensitive_tables=$(grep -oE 'table:[[:space:]]*[a-z_]+' "$sensitive" 2>/dev/null \
  | sed -E 's/.*:[[:space:]]*//' | sort -u || true)
# Always include player_character_index (cycle 2 canonical example)
if ! echo "$sensitive_tables" | grep -qx "player_character_index"; then
  sensitive_tables="$sensitive_tables player_character_index"
fi

for table in $sensitive_tables; do
  hits=$(grep -rniE "SELECT.*FROM[[:space:]]+${table}" \
    --include='*.go' --include='*.rs' --include='*.ts' \
    "$repo_root/services" "$repo_root/contracts" "$repo_root/crates" 2>/dev/null \
    | grep -vE '/contracts/meta/' \
    | grep -vE '_test\.go|_test\.rs' || true)
  if [[ -n "$hits" ]]; then
    echo "[meta-sensitive-read] FAIL — bare SELECT on sensitive table $table outside contracts/meta:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[meta-sensitive-read] FAIL — $violations bypass(es) (S04 §12T.6)"
  exit 1
fi
echo "[meta-sensitive-read] PASS"
exit 0
