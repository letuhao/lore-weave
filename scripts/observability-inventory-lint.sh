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

# Collect declared metric names (key under `metrics:` block).
#
# `|| true` used to sit on the end of this pipeline, and it made the gate INVENT
# findings. grep exits 1 for "no matches" (legitimate) and >1 for a real read failure;
# `|| true` erased that distinction, so a truncated read under CI load yielded a PARTIAL
# or EMPTY declared-set and every metric missing from it was reported as undeclared —
# by name, against a file that declares it. Measured 2026-08-08: three consecutive
# all-gates runs on one commit, each naming a different innocent subject
# (lw_embedding_queue_depth, then lw_meta_outbox_retried_total), while the gate passed
# locally 3/3 on the same bytes. A gate that can fabricate a specific, confident, wrong
# finding costs more than one that dies loudly.
# `set -e` is on, and a bare assignment from a failing command aborts the script with no
# message — so the status is captured deliberately rather than inherited.
set +e
raw_declared=$(grep -E '^[[:space:]]*-[[:space:]]*name:[[:space:]]*"?lw_' "$inventory" 2>/dev/null)
rc=$?
set -e
if [[ $rc -gt 1 ]]; then
  echo "[observability-inventory] FAIL — could not read $inventory (grep exit $rc)."
  echo "  → this is a READ failure, not a finding. Nothing about the code is implied."
  exit 1
fi
declared=$(printf '%s\n' "$raw_declared" \
  | sed -E 's/.*name:[[:space:]]*"?([a-zA-Z0-9_]+)"?.*/\1/' | sort -u)

# An empty declared-set is never legitimate here: the inventory exists (checked above)
# and the repo has metrics. Comparing against it would report EVERY emitted metric as
# undeclared, which is precisely the false finding this gate produced.
if [[ -z "${declared//[[:space:]]/}" ]]; then
  echo "[observability-inventory] FAIL — $inventory yielded no lw_* declarations."
  echo "  → refusing to compare against an empty set; that would flag every emitted metric."
  exit 1
fi

# Collect emitted metric names from code.
# Pattern: prom metric names follow lw_<subsystem>_<verb>(_<unit>?) — at least
# 2 underscore-separated segments after `lw_`. Single-segment names like
# `lw_reality_000…` are typically DB-name format strings, not metrics.
#
# Cycle 19 (L4.H) refinement: exclude *_test.go and *_test.rs because test
# files legitimately reference fake/fixture metric names (e.g.,
# `lw_test_registered_total`, `lw_foo_bar_total`) for admission-control
# unit tests. The lint MUST only fire on REAL emission sites in non-test
# code.
set +e
raw_emitted=$(grep -rhE '"lw_[a-z][a-z0-9]*_[a-z][a-z0-9_]+"' \
  --include='*.go' --include='*.rs' \
  --exclude='*_test.go' --exclude='*_test.rs' \
  "$repo_root/services" "$repo_root/crates" "$repo_root/contracts" 2>/dev/null)
rc=$?
set -e
if [[ $rc -gt 1 ]]; then
  echo "[observability-inventory] FAIL — could not scan source for emitted metrics (grep exit $rc)."
  exit 1
fi
emitted=$(printf '%s\n' "$raw_emitted" \
  | grep -oE '"lw_[a-z][a-z0-9]*_[a-z][a-z0-9_]+"' \
  | tr -d '"' | sort -u || true)
# The mirror of the declared-set guard, and the more dangerous direction: an empty
# emitted-set makes the loop below iterate zero times and the gate report PASS having
# compared nothing. A truncated scan would therefore certify the tree as clean.
if [[ -z "${emitted//[[:space:]]/}" ]]; then
  echo "[observability-inventory] FAIL — found no lw_* metric emissions in services/crates/contracts."
  echo "  → this repo emits metrics; an empty scan means the read failed, not that the tree is clean."
  exit 1
fi

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
