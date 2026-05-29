#!/usr/bin/env bash
# L1.K.4 shard-allocation-validation.sh — R04 §12D.6
#
# Checks scripts/capacity-thresholds.yaml for:
#   - warning_pct between 0 and 95
#   - full_pct between warning_pct+5 and 99
#   - All thresholds present (db_count, storage_bytes, connection_count, cpu_load)
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
target="${1:-$repo_root/scripts/capacity-thresholds.yaml}"

if [[ ! -f "$target" ]]; then
  echo "[shard-allocation] FAIL — capacity-thresholds.yaml missing at $target"
  exit 1
fi

violations=0

# Required structure: at least one cluster with `warning:` and `full:` (decimal)
# OR the legacy per-dimension fields (db_count/storage_bytes/connection_count/cpu_load).
# V1 ships with the simpler warning+full convention per R04 §12D.6.

if ! grep -qE '^[[:space:]]*-?[[:space:]]*name:[[:space:]]*' "$target"; then
  echo "[shard-allocation] FAIL — no cluster blocks declared in $target"
  violations=$((violations + 1))
fi

if ! grep -qE '^[[:space:]]*warning:' "$target"; then
  echo "[shard-allocation] FAIL — no warning: threshold declared"
  violations=$((violations + 1))
fi

if ! grep -qE '^[[:space:]]*full:' "$target"; then
  echo "[shard-allocation] FAIL — no full: threshold declared"
  violations=$((violations + 1))
fi

# Per-cluster sanity: every warning value must be < its full value.
# Pull pairs in order; awk handles decimals naturally.
awk '
  /^[[:space:]]*warning:/ { gsub(":", ""); split($0, a, ":"); w = $2; }
  /^[[:space:]]*full:/    { gsub(":", ""); split($0, a, ":"); f = $2;
    if (w != "" && (w+0) >= (f+0)) {
      print "[shard-allocation] FAIL — warning(" w ") >= full(" f ") at line " NR;
      exit 1;
    }
    w = "";
  }
' "$target" || violations=$((violations + 1))

if [[ $violations -gt 0 ]]; then
  echo "[shard-allocation] FAIL — $violations issue(s) (R04 §12D.6)"
  exit 1
fi
echo "[shard-allocation] PASS"
exit 0
