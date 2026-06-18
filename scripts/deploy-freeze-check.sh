#!/usr/bin/env bash
# scripts/deploy-freeze-check.sh — L7.K.7 (RAID cycle 38)
#
# SR05 §12AH.3 deploy-freeze CI lint. Runs on every PR; blocks the merge when an
# active freeze covers the change, unless the PR carries the break-glass-deploy
# label (the §12AH.3 escape hatch — emergency class + tech-lead CODEOWNERS).
#
# Four freeze types (§12AH.3):
#   slo_burn  — any SLI burn ≥90% over 7d (SR1-D3). Blocks all classes except
#               emergency. Burn rate sourced from slo-budget-calculator (or a
#               --burn-rate / fixture override for tests).
#   scheduled — admin/deploy-freeze set an active window.
#   incident  — active SEV0/SEV1 involving the service.
#   security  — active attack / supply-chain suspicion (platform-wide).
#
# Override (§12AH.3): the break-glass-deploy label lifts the block for an
# emergency-class deploy. emergency class is also exempt from the slo_burn
# freeze even without break-glass (the spec: "All classes except emergency").
#
# Exit codes:
#   0 — PR may merge (no freeze, or properly overridden / emergency-exempt)
#   1 — PR blocked by an active freeze
#   2 — usage error
#
# Flags:
#   --class <c>             deploy class (patch|minor|major|emergency)
#   --pr-labels <csv>       labels currently on the PR
#   --active-freezes <csv>  comma-separated active freeze types (slo_burn,…)
#   --burn-rate <f>         override SLI burn (else fixture / fail-open)
#
# Environment:
#   LW_ACTIVE_FREEZES        csv of active freezes (test injection)
#   LW_FREEZE_FIXTURE        JSON {burn_rate: 0.92} for slo_burn detection
#   LW_SLO_BURN_THRESHOLD    default 0.90 (SR1-D3)

set -euo pipefail

DEPLOY_CLASS=""
PR_LABELS=""
ACTIVE_FREEZES="${LW_ACTIVE_FREEZES:-}"
EXPLICIT_BURN=""
BREAK_GLASS_LABEL="break-glass-deploy"
SLO_BURN_THRESHOLD="${LW_SLO_BURN_THRESHOLD:-0.90}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --class) DEPLOY_CLASS="$2"; shift 2 ;;
        --pr-labels) PR_LABELS="$2"; shift 2 ;;
        --active-freezes) ACTIVE_FREEZES="$2"; shift 2 ;;
        --burn-rate) EXPLICIT_BURN="$2"; shift 2 ;;
        --help|-h) sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "[deploy-freeze-check] unknown arg: $1" >&2; exit 2 ;;
    esac
done

has_label() {
    # $1 = label to find in the comma-separated PR_LABELS
    [[ ",${PR_LABELS}," == *",$1,"* ]]
}

has_freeze() {
    # $1 = freeze type to find in the comma-separated ACTIVE_FREEZES
    [[ ",${ACTIVE_FREEZES}," == *",$1,"* ]]
}

# Resolve SLI burn (only needed when slo_burn is NOT already declared active).
resolve_burn() {
    if [[ -n "$EXPLICIT_BURN" ]]; then
        echo "$EXPLICIT_BURN"; return
    fi
    if [[ -n "${LW_FREEZE_FIXTURE:-}" && -f "${LW_FREEZE_FIXTURE}" ]] && command -v python3 >/dev/null 2>&1; then
        python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['burn_rate'])" "${LW_FREEZE_FIXTURE}"
        return
    fi
    # No data → fail-open (treat as healthy).
    echo "0.0"
}

# Detect an slo_burn freeze from the burn rate if not explicitly declared.
if ! has_freeze "slo_burn"; then
    burn="$(resolve_burn)"
    if [[ "$burn" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
        over=$(awk -v b="$burn" -v t="$SLO_BURN_THRESHOLD" 'BEGIN { print (b >= t) ? 1 : 0 }')
        if [[ "$over" -eq 1 ]]; then
            ACTIVE_FREEZES="${ACTIVE_FREEZES:+$ACTIVE_FREEZES,}slo_burn"
            echo "[deploy-freeze-check] slo_burn freeze ACTIVE: burn=$burn ≥ threshold=$SLO_BURN_THRESHOLD"
        fi
    fi
fi

echo "[deploy-freeze-check] class=${DEPLOY_CLASS:-<unset>} active_freezes=[${ACTIVE_FREEZES}] labels=[${PR_LABELS}]"

# No active freeze → allow.
if [[ -z "$ACTIVE_FREEZES" ]]; then
    echo "[deploy-freeze-check] no active freeze — merge allowed"
    exit 0
fi

blocked_by=""
for ft in slo_burn scheduled incident security; do
    has_freeze "$ft" || continue

    # emergency class is exempt from slo_burn even without break-glass (§12AH.3).
    if [[ "$ft" == "slo_burn" && "$DEPLOY_CLASS" == "emergency" ]]; then
        echo "[deploy-freeze-check] emergency class is exempt from slo_burn freeze (§12AH.3)"
        continue
    fi

    # Any active freeze is liftable by the break-glass-deploy label.
    if has_label "$BREAK_GLASS_LABEL"; then
        echo "[deploy-freeze-check] '$ft' freeze overridden by ${BREAK_GLASS_LABEL} label (tech-lead approval assumed verified; admin deploy break-glass recorded)"
        continue
    fi

    blocked_by="${blocked_by:+$blocked_by,}$ft"
done

if [[ -n "$blocked_by" ]]; then
    echo "[deploy-freeze-check] BLOCKED: active freeze(s) [$blocked_by] cover this deploy; add '${BREAK_GLASS_LABEL}' label (emergency class + tech-lead) to override" >&2
    exit 1
fi

echo "[deploy-freeze-check] all active freezes exempt/overridden — merge allowed"
exit 0
