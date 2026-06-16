#!/usr/bin/env bash
# RAID Post-RAID-Review gate (v1.7) — blocks PR-to-main until the mandatory
# Post-RAID Comprehensive Review has run AND its verdict is CLEAR.
#
# See docs/raid/POST_RAID_REVIEW_PROTOCOL.md §4. Portable: the findings doc
# path is derived from the active task's plan_dir (.raid/active-task.yaml).
#
# Exit 0 = CLEAR (ok to PR); 1 = BLOCKED (review missing / blocked / un-triaged);
# 2 = misuse (cannot resolve task config).
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"

plan_dir="$(python3 "$repo_root/scripts/raid/task_config.py" dump 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('plan_dir',''))" 2>/dev/null || true)"
if [[ -z "${plan_dir:-}" ]]; then
  echo "[post-raid-gate] FAIL — cannot read plan_dir from .raid/active-task.yaml (is a RAID task active?)"
  exit 2
fi

findings="$repo_root/$plan_dir/POST_RAID_REVIEW_FINDINGS.md"
if [[ ! -f "$findings" ]]; then
  echo "[post-raid-gate] BLOCKED — missing $plan_dir/POST_RAID_REVIEW_FINDINGS.md."
  echo "  Run the Post-RAID Comprehensive Review (docs/raid/POST_RAID_REVIEW_PROTOCOL.md) before opening a PR to main."
  exit 1
fi

if ! grep -q "Triage disposition" "$findings"; then
  echo "[post-raid-gate] BLOCKED — findings doc has no 'Triage disposition' section."
  echo "  Every finding must be fixed-and-committed OR routed to a DEFERRED.md row before PR."
  exit 1
fi

if grep -qE "^POST-RAID-REVIEW: BLOCKED" "$findings"; then
  echo "[post-raid-gate] BLOCKED — review verdict is BLOCKED:"
  grep -E "^POST-RAID-REVIEW:" "$findings" | head -1 | sed 's/^/  /'
  echo "  Resolve or defer-track the blocking findings, then re-stamp the verdict CLEAR."
  exit 1
fi

if ! grep -qE "^POST-RAID-REVIEW: CLEAR" "$findings"; then
  echo "[post-raid-gate] BLOCKED — no stamped verdict line."
  echo "  The findings doc MUST end with exactly one of:"
  echo "    POST-RAID-REVIEW: CLEAR (<reason>)   |   POST-RAID-REVIEW: BLOCKED (<reason>)"
  exit 1
fi

echo "[post-raid-gate] PASS — Post-RAID Comprehensive Review CLEAR; OK to open PR-to-main."
grep -E "^POST-RAID-REVIEW:" "$findings" | head -1 | sed 's/^/  verdict: /'
exit 0
