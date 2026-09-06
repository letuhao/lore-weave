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
# EMERGENCY-class deploy. emergency class is also exempt from the slo_burn
# freeze even without break-glass (the spec: "All classes except emergency").
#
# Exit codes:
#   0 — PR may merge (no freeze, or properly overridden / emergency-exempt)
#   1 — PR blocked by an active freeze
#   2 — usage error · unknown deploy class · unparseable burn rate · self-test failure
#
# Flags:
#   --class <c>             deploy class (patch|minor|major|emergency)
#   --pr-labels <csv>       labels currently on the PR
#   --active-freezes <csv>  comma-separated active freeze types (slo_burn,…)
#   --burn-rate <f>         override SLI burn (else fixture / fail-open)
#   --self-test             prove every rule bites, then exit
#
# Environment:
#   LW_ACTIVE_FREEZES        csv of active freezes (test injection)
#   LW_FREEZE_FIXTURE        JSON {burn_rate: 0.92} for slo_burn detection
#   LW_SLO_BURN_THRESHOLD    default 0.90 (SR1-D3)
#
# ── GT7 · what this gate lacked ──────────────────────────────────────────────
# **The break-glass exemption was WIDER than its stated reason.** Both the header
# and the gate's own blocked message say the label lifts a freeze for an
# *emergency-class* deploy ("add 'break-glass-deploy' label (emergency class +
# tech-lead) to override") — and the code lifted it for ANY class, so a `patch`
# PR carrying the label walked through a security freeze. `GTD-18`'s shape, on
# the one control that stops a deploy during an active incident. Narrowed to
# match the sentence that justifies it.
#
# **"No burn data" and "burn = 0.0" were the same observable.** `resolve_burn`
# returns `0.0` when nothing is available, so a broken slo-budget-calculator
# reads as a perfectly healthy SLO and the slo_burn freeze silently stops
# existing. The fail-open is a deliberate operational choice and is kept — but it
# now SAYS so on every run, because a fail-open nobody can see is indistinguishable
# from a rule that works.
#
# **An unparseable `--burn-rate` was silently ignored** — the numeric guard just
# skipped the whole detection, so `--burn-rate abc` meant "no freeze". Now exit 2.
# An unknown `--class` was accepted the same way; it is now a closed set.
#
# `--help` printed a FIXED line window (`sed -n '2,40p'`) into its own header —
# the fifth occurrence of that shape in this repo. Computed now.

set -euo pipefail

SELF="${BASH_SOURCE[0]}"
BREAK_GLASS_LABEL="break-glass-deploy"
VALID_CLASSES="patch minor major emergency"
FREEZE_TYPES="slo_burn scheduled incident security"

_help() {
    # Computed, not a hardcoded line range.
    awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$SELF"
}

run_check() {
    local DEPLOY_CLASS="" PR_LABELS="" EXPLICIT_BURN=""
    local ACTIVE_FREEZES="${LW_ACTIVE_FREEZES:-}"
    local SLO_BURN_THRESHOLD="${LW_SLO_BURN_THRESHOLD:-0.90}"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --class) DEPLOY_CLASS="$2"; shift 2 ;;
            --pr-labels) PR_LABELS="$2"; shift 2 ;;
            --active-freezes) ACTIVE_FREEZES="$2"; shift 2 ;;
            --burn-rate) EXPLICIT_BURN="$2"; shift 2 ;;
            --help|-h) _help; return 0 ;;
            *) echo "[deploy-freeze-check] unknown arg: $1" >&2; return 2 ;;
        esac
    done

    # ── CLOSED SET on the class. An unrecognised value used to sail through and
    # be compared against "emergency" forever after — a silent no-match, which is
    # how a typo turns an exemption off without anyone noticing.
    if [[ -n "$DEPLOY_CLASS" ]]; then
        local ok=0 c
        for c in $VALID_CLASSES; do [[ "$DEPLOY_CLASS" == "$c" ]] && ok=1; done
        if [[ "$ok" -eq 0 ]]; then
            echo "[deploy-freeze-check] ERROR — unknown deploy class '$DEPLOY_CLASS' (want one of: $VALID_CLASSES)." >&2
            return 2
        fi
    fi

    has_label() { [[ ",${PR_LABELS}," == *",$1,"* ]]; }
    has_freeze() { [[ ",${ACTIVE_FREEZES}," == *",$1,"* ]]; }

    # Resolve SLI burn (only needed when slo_burn is NOT already declared active).
    # `burn_source` exists so the fail-open can be SEEN.
    local burn burn_source
    if [[ -n "$EXPLICIT_BURN" ]]; then
        burn="$EXPLICIT_BURN"; burn_source="--burn-rate"
    elif [[ -n "${LW_FREEZE_FIXTURE:-}" && -f "${LW_FREEZE_FIXTURE}" ]] && command -v python3 >/dev/null 2>&1; then
        burn="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['burn_rate'])" "${LW_FREEZE_FIXTURE}")"
        burn_source="fixture"
    else
        burn="0.0"; burn_source="none"
    fi

    if ! has_freeze "slo_burn"; then
        if [[ ! "$burn" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
            # Previously this just skipped the detection, so a malformed burn rate
            # meant "no slo_burn freeze" — the input that cannot be understood
            # silently became the input that means everything is fine.
            echo "[deploy-freeze-check] ERROR — burn rate '$burn' (from $burn_source) is not a number;" >&2
            echo "  refusing to treat an unparseable SLO reading as a healthy one." >&2
            return 2
        fi
        if [[ "$burn_source" == "none" ]]; then
            # THE FAIL-OPEN, SAID OUT LOUD. Keeping it is the operational call the
            # spec makes; hiding it is what made "the calculator is broken" and
            # "the SLO is healthy" the same line of output.
            echo "[deploy-freeze-check] NOTE — no SLI burn data available (no --burn-rate, no LW_FREEZE_FIXTURE)."
            echo "  Failing OPEN: the slo_burn freeze cannot be detected on this run."
        fi
        local over
        over=$(awk -v b="$burn" -v t="$SLO_BURN_THRESHOLD" 'BEGIN { print (b >= t) ? 1 : 0 }')
        if [[ "$over" -eq 1 ]]; then
            ACTIVE_FREEZES="${ACTIVE_FREEZES:+$ACTIVE_FREEZES,}slo_burn"
            echo "[deploy-freeze-check] slo_burn freeze ACTIVE: burn=$burn ≥ threshold=$SLO_BURN_THRESHOLD"
        fi
    fi

    echo "[deploy-freeze-check] class=${DEPLOY_CLASS:-<unset>} active_freezes=[${ACTIVE_FREEZES}] labels=[${PR_LABELS}] burn=${burn}(${burn_source})"

    if [[ -z "$ACTIVE_FREEZES" ]]; then
        echo "[deploy-freeze-check] no active freeze — merge allowed"
        return 0
    fi

    local blocked_by="" ft
    for ft in $FREEZE_TYPES; do
        has_freeze "$ft" || continue

        # emergency class is exempt from slo_burn even without break-glass (§12AH.3).
        if [[ "$ft" == "slo_burn" && "$DEPLOY_CLASS" == "emergency" ]]; then
            echo "[deploy-freeze-check] emergency class is exempt from slo_burn freeze (§12AH.3)"
            continue
        fi

        # ── THE ESCAPE HATCH, NARROWED TO ITS STATED REASON. §12AH.3 grants
        # break-glass to an EMERGENCY-class deploy with tech-lead approval; the
        # code used to accept the label from any class, so a `patch` PR could
        # walk through a security freeze by adding a label.
        if has_label "$BREAK_GLASS_LABEL"; then
            if [[ "$DEPLOY_CLASS" == "emergency" ]]; then
                echo "[deploy-freeze-check] '$ft' freeze overridden by ${BREAK_GLASS_LABEL} on an emergency-class deploy (tech-lead approval assumed verified; admin deploy break-glass recorded)"
                continue
            fi
            echo "[deploy-freeze-check] ${BREAK_GLASS_LABEL} present but class is '${DEPLOY_CLASS:-<unset>}', not emergency — §12AH.3 grants break-glass to emergency deploys only" >&2
        fi

        blocked_by="${blocked_by:+$blocked_by,}$ft"
    done

    if [[ -n "$blocked_by" ]]; then
        echo "[deploy-freeze-check] BLOCKED: active freeze(s) [$blocked_by] cover this deploy; add '${BREAK_GLASS_LABEL}' label (emergency class + tech-lead) to override" >&2
        return 1
    fi

    echo "[deploy-freeze-check] all active freezes exempt/overridden — merge allowed"
    return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
selftest() {
    local failures=0 tmp
    tmp="$(mktemp -d)"

    # p <name> <want-rc> [<want-substring>] -- <args…>
    p() {
        local name="$1" want="$2" want_str="$3"; shift 3
        [[ "${1:-}" == "--" ]] && shift
        local out got
        set +e
        out="$( LW_ACTIVE_FREEZES="" LW_FREEZE_FIXTURE="" run_check "$@" 2>&1 )"
        got=$?
        set -e
        local ok=1
        [[ "$got" == "$want" ]] || ok=0
        [[ -z "$want_str" || "$out" == *"$want_str"* ]] || ok=0
        if [[ "$ok" -eq 1 ]]; then
            echo "  ok   $name: rc=$got"
        else
            echo "  FAIL $name: rc=$got (want $want)${want_str:+ / missing ${want_str@Q}}"
            failures=$((failures + 1))
        fi
    }

    echo "deploy-freeze-check --self-test"

    p "no freeze at all allows the merge" 0 "no active freeze" -- --class patch
    p "a scheduled freeze blocks a patch" 1 "BLOCKED" -- --class patch --active-freezes scheduled
    p "an incident freeze blocks a major" 1 "BLOCKED" -- --class major --active-freezes incident
    p "a security freeze blocks an emergency without the label" 1 "BLOCKED" \
        -- --class emergency --active-freezes security

    # the spec's own exemption
    p "emergency is exempt from slo_burn without any label" 0 "exempt from slo_burn" \
        -- --class emergency --active-freezes slo_burn
    p "...but a patch is not" 1 "BLOCKED" -- --class patch --active-freezes slo_burn

    # THE ESCAPE HATCH, and the narrowing
    p "break-glass lifts a freeze for an EMERGENCY deploy" 0 "overridden by break-glass-deploy" \
        -- --class emergency --active-freezes security --pr-labels break-glass-deploy
    p "...but NOT for a patch (the exemption's stated reason)" 1 "not emergency" \
        -- --class patch --active-freezes security --pr-labels break-glass-deploy
    p "...nor for a major" 1 "not emergency" \
        -- --class major --active-freezes scheduled --pr-labels break-glass-deploy
    p "an unrelated label does not lift anything" 1 "BLOCKED" \
        -- --class emergency --active-freezes security --pr-labels docs-only
    # The case that isolates the ,exact, boundary. An unrelated label like
    # `docs-only` reds whether the match is exact or a substring, so it certifies
    # the wrong rule; a label CONTAINING the break-glass name separates them.
    p "...nor a label that merely CONTAINS the break-glass name" 1 "BLOCKED" \
        -- --class emergency --active-freezes security \
           --pr-labels needs-break-glass-deploy-approval

    # burn-rate detection
    p "a burn rate over the threshold raises slo_burn" 1 "slo_burn freeze ACTIVE" \
        -- --class patch --burn-rate 0.95
    p "...and one under it does not" 0 "no active freeze" -- --class patch --burn-rate 0.10
    p "...and exactly at the threshold DOES (>=, not >)" 1 "slo_burn freeze ACTIVE" \
        -- --class patch --burn-rate 0.90
    p "an UNPARSEABLE burn rate is misuse, not health" 2 "not a number" \
        -- --class patch --burn-rate not-a-number

    # the fail-open, now visible
    p "no burn data at all SAYS it is failing open" 0 "Failing OPEN" -- --class patch

    # the fixture path
    printf '{"burn_rate": 0.99}\n' > "$tmp/burn.json"
    local out got
    set +e
    out="$( LW_ACTIVE_FREEZES="" LW_FREEZE_FIXTURE="$tmp/burn.json" run_check --class patch 2>&1 )"
    got=$?
    set -e
    if [[ "$got" -eq 1 && "$out" == *"slo_burn freeze ACTIVE"* ]]; then
        echo "  ok   a fixture burn rate is read and raises the freeze: rc=$got"
    else
        echo "  FAIL a fixture burn rate is read and raises the freeze: rc=$got"
        failures=$((failures + 1))
    fi

    # closed sets + misuse
    p "an unknown deploy class is misuse" 2 "unknown deploy class" -- --class urgent
    p "an unknown arg is misuse" 2 "unknown arg" -- --class patch --bogus

    rm -rf "$tmp"
    if [[ $failures -gt 0 ]]; then
        echo "deploy-freeze-check --self-test: $failures rule(s) did not behave"
        return 2
    fi
    echo "deploy-freeze-check --self-test: every rule bites, and none cries wolf"
    return 0
}

case "${1:-}" in
    --self-test|--selftest) selftest ;;
    *)
        selftest || exit 2
        echo
        run_check "$@"
        ;;
esac
