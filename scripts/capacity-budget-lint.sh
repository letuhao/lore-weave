#!/usr/bin/env bash
# L1.K.7 capacity-budget-lint.sh — SR08 I17
#
# Every service in `services/<name>/` MUST appear in
# contracts/capacity/budgets.yaml with its per-replica CPU/mem budget +
# scaling policy class (web|llm-gateway|worker|cron).
#
# Exit 0 = clean; 1 = violations; 2 = misuse / selftest failure.
#
# RED-ABILITY PROOF (`GATE-TEETH`). Until 2026-08-12 this gate carried none: it
# was one of 43 CI-invoked gates asserting coverage that nobody had shown could
# fail. The membership test is now extracted into `has_entry` so `--selftest`
# can drive it directly, and the bare invocation runs the selftest BEFORE the
# lint, so the proof executes on every CI run rather than on request.
#
# The load-bearing case is the PREFIX one. `name: alpha-extra` must not satisfy
# a requirement for `alpha`; the only thing standing between those is the
# `[[:space:]]*$` anchor, and without a case a future edit could drop it and
# every service would appear "covered" by any row whose name it prefixes.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
budgets="$repo_root/contracts/capacity/budgets.yaml"

# THE PREDICATE, extracted so a case can drive it. $1 = service, $2 = registry.
has_entry() {
  grep -qE "^[[:space:]]*-[[:space:]]*name:[[:space:]]*\"?$1\"?[[:space:]]*\$" "$2"
}

run_lint() {
  if [[ ! -f "$budgets" ]]; then
    echo "[capacity-budget] FAIL — budgets.yaml missing at $budgets"
    exit 1
  fi

  local violations=0 checked=0 svc
  for svc_dir in "$repo_root"/services/*/; do
    svc=$(basename "$svc_dir")
    # Skip if directory is empty or only README
    if [[ -z "$(ls -A "$svc_dir" 2>/dev/null | grep -v README.md)" ]]; then
      continue
    fi
    checked=$((checked + 1))
    if ! has_entry "$svc" "$budgets"; then
      echo "[capacity-budget] FAIL — service $svc has no entry in budgets.yaml"
      violations=$((violations + 1))
    fi
  done

  # REACH FLOOR. A walk that reaches nothing and a clean tree are byte-identical
  # including exit 0, so "no violations" over zero services is not a pass — it is
  # a broken scan reporting success (`BDR-82`).
  if [[ $checked -lt 1 ]]; then
    echo "[capacity-budget] FAIL — scanned ZERO services; the walk reached nothing,"
    echo "                  which is indistinguishable from a clean tree"
    exit 2
  fi

  if [[ $violations -gt 0 ]]; then
    echo "[capacity-budget] FAIL — $violations service(s) missing capacity budget (SR08 I17)"
    exit 1
  fi
  echo "[capacity-budget] PASS — $checked service(s) checked against budgets.yaml"
  exit 0
}

selftest() {
  local tmp
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN

  printf 'services:\n  - name: alpha\n    cpu: 1\n  - name: "beta"\n    cpu: 2\n' > "$tmp"

  if ! has_entry alpha "$tmp"; then
    echo "[capacity-budget] SELFTEST FAIL — did NOT match a service that IS listed (cry-wolf)"; exit 2
  fi
  if ! has_entry beta "$tmp"; then
    echo "[capacity-budget] SELFTEST FAIL — did NOT match the QUOTED form \`- name: \"beta\"\`"; exit 2
  fi
  if has_entry gamma "$tmp"; then
    echo "[capacity-budget] SELFTEST FAIL — matched a service that is NOT listed (vacuous)"; exit 2
  fi

  # The anchor case. Without the trailing `[[:space:]]*$` this passes and every
  # service is "covered" by any longer row it happens to prefix.
  printf 'services:\n  - name: alpha-extra\n' > "$tmp"
  if has_entry alpha "$tmp"; then
    echo "[capacity-budget] SELFTEST FAIL — \`alpha\` matched the row \`alpha-extra\`;"
    echo "                  the name anchor is gone, so membership is a PREFIX test"; exit 2
  fi

  echo "[capacity-budget] SELFTEST PASS — matches a listed service (plain and quoted),"
  echo "                  refuses an unlisted one, and refuses a prefix match (non-vacuous)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
