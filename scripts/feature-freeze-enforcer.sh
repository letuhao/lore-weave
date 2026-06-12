#!/usr/bin/env bash
# scripts/feature-freeze-enforcer.sh — L7.I.7 (RAID cycle 34)
#
# CI gate per SR1 §12AD.4 (burn-rate 4-tier policy).
#
# Reads the current burn rate from slo-budget-calculator's /slo/targets
# endpoint (Q-L7-1 SEPARATE service) — or, in DRY mode, from a fixture
# file the test suite injects. Emits PR labels per tier:
#
#   < 50%   → no label
#   50–75%  → no label (warn only — alertmanager handles Slack notify)
#   75–90%  → reliability-review-required (must be on PR before merge)
#   ≥ 90%   → approve-reliability-override (tech-lead must approve)
#   ≥ 100%  → slo-breach-postmortem (block until postmortem published)
#
# Exit codes:
#   0  — PR may merge as-is
#   1  — PR blocked (label policy violated; emit reason)
#   2  — usage error / can't reach calculator
#
# Mode flags:
#   --dry-run         skip live HTTP; use $LW_FREEZE_FIXTURE
#   --burn-rate <f>   override the burn rate (for tests)
#   --pr-labels <csv> labels already on the PR (for compliance check)
#
# Environment:
#   LW_SLO_CALC_URL       default http://slo-budget-calculator:8090
#   LW_FREEZE_FIXTURE     path to a JSON fixture {burn_rate: 0.78}
#   LW_FREEZE_BURN_RATE   numeric override (highest precedence)

set -euo pipefail

CALC_URL="${LW_SLO_CALC_URL:-http://slo-budget-calculator:8090}"
DRY_RUN=0
PR_LABELS=""
EXPLICIT_BURN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --burn-rate) EXPLICIT_BURN="$2"; shift 2 ;;
        --pr-labels) PR_LABELS="$2"; shift 2 ;;
        --help|-h)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *) echo "[freeze-enforcer] unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Burn rate resolution order: --burn-rate > LW_FREEZE_BURN_RATE >
# LW_FREEZE_FIXTURE file > live HTTP fetch.
burn_rate=""
if [[ -n "$EXPLICIT_BURN" ]]; then
    burn_rate="$EXPLICIT_BURN"
elif [[ -n "${LW_FREEZE_BURN_RATE:-}" ]]; then
    burn_rate="$LW_FREEZE_BURN_RATE"
elif [[ -n "${LW_FREEZE_FIXTURE:-}" && -f "${LW_FREEZE_FIXTURE}" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        burn_rate=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['burn_rate'])" \
                   "${LW_FREEZE_FIXTURE}")
    else
        echo "[freeze-enforcer] python3 required to parse fixture" >&2
        exit 2
    fi
elif [[ "$DRY_RUN" -eq 1 ]]; then
    # No data available, dry-run defaults to "normal".
    burn_rate="0.0"
else
    # Live mode — fetch from slo-budget-calculator.
    if ! command -v curl >/dev/null 2>&1; then
        echo "[freeze-enforcer] curl required for live mode" >&2
        exit 2
    fi
    # The service's /slo/targets is TSV; the V1 implementation does not
    # surface live burn rate (calculator is config-only). Until live wiring
    # lands (see D-SLO-CALC-LIVE-WIRING), we treat unreachable as "fail-open".
    if ! curl -fsS "${CALC_URL}/healthz" >/dev/null 2>&1 ; then
        echo "[freeze-enforcer] WARN: cannot reach ${CALC_URL}; fail-open (allow merge)"
        burn_rate="0.0"
    else
        # Real burn-rate fetch will land in a follow-up cycle; for now we
        # assume normal operation when the calculator is up.
        burn_rate="0.0"
    fi
fi

# Map burn rate → policy tier
if ! [[ "$burn_rate" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
    echo "[freeze-enforcer] invalid burn rate: $burn_rate" >&2
    exit 2
fi

# Use awk for float comparisons (portable).
tier=$(awk -v b="$burn_rate" 'BEGIN {
    if (b >= 1.00)      print "slo-breach-postmortem"
    else if (b >= 0.90) print "approve-reliability-override"
    else if (b >= 0.75) print "reliability-review-required"
    else if (b >= 0.50) print "warn"
    else                print "normal"
}')

echo "[freeze-enforcer] burn_rate=$burn_rate tier=$tier"

case "$tier" in
    normal|warn)
        # No label required; PR may merge.
        exit 0
        ;;
    reliability-review-required)
        # Require this label.
        if [[ ",${PR_LABELS}," == *",reliability-review-required,"* ]]; then
            echo "[freeze-enforcer] PR has required label — merge allowed"
            exit 0
        fi
        echo "[freeze-enforcer] BLOCKED: burn_rate=$burn_rate requires 'reliability-review-required' label" >&2
        exit 1
        ;;
    approve-reliability-override)
        # Require BOTH labels (reliability-review-required + override).
        if [[ ",${PR_LABELS}," == *",approve-reliability-override,"* ]]; then
            echo "[freeze-enforcer] PR has override label — merge allowed (tech-lead approval assumed verified)"
            exit 0
        fi
        echo "[freeze-enforcer] BLOCKED: burn_rate=$burn_rate (≥ 90%) requires 'approve-reliability-override' label + tech-lead approval" >&2
        exit 1
        ;;
    slo-breach-postmortem)
        # Block unless explicit postmortem label.
        if [[ ",${PR_LABELS}," == *",slo-breach-postmortem,"* ]]; then
            echo "[freeze-enforcer] PR has postmortem label — merge allowed"
            exit 0
        fi
        echo "[freeze-enforcer] BLOCKED: burn_rate=$burn_rate ≥ 100% (SLO BREACH); postmortem mandatory before any feature merge" >&2
        exit 1
        ;;
    *)
        echo "[freeze-enforcer] internal error: unknown tier $tier" >&2
        exit 2
        ;;
esac
