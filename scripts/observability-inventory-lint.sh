#!/usr/bin/env bash
# L1.K.6 observability-inventory-lint.sh — SR12 I19
#
# Every `lw_*` metric emitted from code MUST have a matching entry in
# contracts/observability/inventory.yaml. This lint enforces by:
#   1. grep all `lw_*` literal symbol references in Go/Rust source
#   2. read the inventory yaml (key = metric name)
#   3. flag any code-emitted symbol not declared in inventory
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
inventory="$repo_root/contracts/observability/inventory.yaml"

if [[ ! -f "$inventory" ]]; then
  echo "[observability-inventory] WARN — no inventory.yaml; skipping"
  exit 0
fi

# Collect declared metric names (key under `metrics:` block)
declared=$(grep -E '^[[:space:]]*-[[:space:]]*name:[[:space:]]*"?lw_' "$inventory" 2>/dev/null \
  | sed -E 's/.*name:[[:space:]]*"?([a-zA-Z0-9_]+)"?.*/\1/' | sort -u || true)

# Collect emitted metric names from code.
# Pattern: prom metric names follow lw_<subsystem>_<verb>(_<unit>?) — at least
# 2 underscore-separated segments after `lw_`. Single-segment names like
# `lw_reality_000…` are typically DB-name format strings, not metrics.
emitted=$(grep -rhE '"lw_[a-z][a-z0-9]*_[a-z][a-z0-9_]+"' \
  --include='*.go' --include='*.rs' \
  "$repo_root/services" "$repo_root/crates" "$repo_root/contracts" 2>/dev/null \
  | grep -oE '"lw_[a-z][a-z0-9]*_[a-z][a-z0-9_]+"' \
  | tr -d '"' | sort -u || true)

# Filter out DB-name format strings (lw_reality_*) and other known non-metric
# patterns; these are matched by the broader regex but aren't metric names.
emitted=$(echo "$emitted" | grep -vE '^lw_reality_[0-9a-f]+$' | grep -vE '^lw_reality_$' || true)

violations=0
for sym in $emitted; do
  if ! echo "$declared" | grep -qx "$sym"; then
    echo "[observability-inventory] FAIL — $sym emitted from code but NOT declared in inventory.yaml"
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[observability-inventory] FAIL — $violations metric(s) missing inventory entry (SR12 I19)"
  exit 1
fi
echo "[observability-inventory] PASS"
exit 0
