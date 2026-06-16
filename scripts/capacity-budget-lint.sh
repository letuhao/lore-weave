#!/usr/bin/env bash
# L1.K.7 capacity-budget-lint.sh — SR08 I17
#
# Every service in `services/<name>/` MUST appear in
# contracts/capacity/budgets.yaml with its per-replica CPU/mem budget +
# scaling policy class (web|llm-gateway|worker|cron).
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
budgets="$repo_root/contracts/capacity/budgets.yaml"

if [[ ! -f "$budgets" ]]; then
  echo "[capacity-budget] FAIL — budgets.yaml missing at $budgets"
  exit 1
fi

violations=0
for svc_dir in "$repo_root"/services/*/; do
  svc=$(basename "$svc_dir")
  # Skip if directory is empty or only README
  if [[ -z "$(ls -A "$svc_dir" 2>/dev/null | grep -v README.md)" ]]; then
    continue
  fi
  if ! grep -qE "^[[:space:]]*-[[:space:]]*name:[[:space:]]*\"?${svc}\"?[[:space:]]*$" "$budgets"; then
    echo "[capacity-budget] FAIL — service $svc has no entry in budgets.yaml"
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[capacity-budget] FAIL — $violations service(s) missing capacity budget (SR08 I17)"
  exit 1
fi
echo "[capacity-budget] PASS"
exit 0
