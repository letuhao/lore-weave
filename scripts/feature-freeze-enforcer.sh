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
#   2  — usage error · invalid burn rate · LIVE MODE IS NOT WIRED · self-test failure
#
# Mode flags:
#   --dry-run         skip live HTTP; use $LW_FREEZE_FIXTURE
#   --burn-rate <f>   override the burn rate (for tests)
#   --pr-labels <csv> labels already on the PR (for compliance check)
#   --self-test       prove every rule bites, then exit
#
# Environment:
#   LW_SLO_CALC_URL       default http://slo-budget-calculator:8090
#   LW_FREEZE_FIXTURE     path to a JSON fixture {burn_rate: 0.78}
#   LW_FREEZE_BURN_RATE   numeric override (highest precedence)
#
# ── GT7 · what this gate lacked ──────────────────────────────────────────────
# **LIVE MODE COULD NOT PRODUCE A NON-ZERO BURN RATE.** Both branches of the live
# fetch assigned `burn_rate="0.0"` — the unreachable one as a documented
# fail-open, and the REACHABLE one under the comment *"Real burn-rate fetch will
# land in a follow-up cycle; for now we assume normal operation when the
# calculator is up."* So the `curl /healthz` probe was decoration: its two
# outcomes produced the same number, and every tier above `normal` was
# unreachable outside a `--burn-rate` or fixture injection. A four-tier freeze
# policy that cannot leave tier one is `NV-1` with a comment explaining itself.
#
# Live mode now returns **2 (CANNOT RUN)** rather than a fabricated reading.
# Inventing `0.0` and calling it healthy is strictly worse than admitting the
# calculator is not wired — this repo's own note two files over says why:
# "conflating [cannot-run] into 0 is the skip-reads-as-pass bug this repo has now
# shipped twice." CI invokes this with `--dry-run`, so nothing regresses.
#
# **`D-SLO-CALC-LIVE-WIRING` is a PROSE-ONLY deferral.** Measured 2026-08-12 it
# appears in exactly two places: one `cycle_done` line in `docs/audit/AUDIT_LOG.jsonl`
# dated 2026-05-30, and the comment in this file. It is in no Deferred Items
# table and no handoff line. The self-test case below ("live mode is CANNOT RUN")
# is the mechanism it never had: implement the fetch and that case must change,
# which is the only kind of reminder that survives.
#
# A comment claimed the ≥90% tier requires BOTH labels; the code requires only
# the override, and the code matches the policy table above. The comment was the
# wrong one — corrected, because a reader trusting it would believe in coverage
# that does not exist.
#
# `--help` printed a FIXED line window (`sed -n '2,30p'`) — the sixth occurrence
# of that shape in this repo. Computed now.

set -euo pipefail

SELF="${BASH_SOURCE[0]}"

_help() {
    awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$SELF"
}

run_enforcer() {
    local CALC_URL="${LW_SLO_CALC_URL:-http://slo-budget-calculator:8090}"
    local DRY_RUN=0 PR_LABELS="" EXPLICIT_BURN=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) DRY_RUN=1; shift ;;
            --burn-rate) EXPLICIT_BURN="$2"; shift 2 ;;
            --pr-labels) PR_LABELS="$2"; shift 2 ;;
            --help|-h) _help; return 0 ;;
            *) echo "[freeze-enforcer] unknown arg: $1" >&2; return 2 ;;
        esac
    done

    # Burn rate resolution order: --burn-rate > LW_FREEZE_BURN_RATE >
    # LW_FREEZE_FIXTURE file > (dry-run: no data) > live fetch.
    local burn_rate="" burn_source=""
    if [[ -n "$EXPLICIT_BURN" ]]; then
        burn_rate="$EXPLICIT_BURN"; burn_source="--burn-rate"
    elif [[ -n "${LW_FREEZE_BURN_RATE:-}" ]]; then
        burn_rate="$LW_FREEZE_BURN_RATE"; burn_source="LW_FREEZE_BURN_RATE"
    elif [[ -n "${LW_FREEZE_FIXTURE:-}" && -f "${LW_FREEZE_FIXTURE}" ]]; then
        if command -v python3 >/dev/null 2>&1; then
            burn_rate=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['burn_rate'])" \
                       "${LW_FREEZE_FIXTURE}")
            burn_source="fixture"
        else
            echo "[freeze-enforcer] python3 required to parse fixture" >&2
            return 2
        fi
    elif [[ "$DRY_RUN" -eq 1 ]]; then
        burn_rate="0.0"; burn_source="none"
        echo "[freeze-enforcer] NOTE — dry-run with no fixture and no override: no burn data."
        echo "  Treating burn as 0.0; this run cannot detect any freeze tier."
    else
        # ── LIVE MODE IS NOT WIRED (D-SLO-CALC-LIVE-WIRING, open since
        # 2026-05-30). The previous code returned 0.0 here whether or not the
        # calculator answered, so the healthz probe decided nothing and every
        # tier above `normal` was unreachable in production. Refusing is honest;
        # a manufactured "healthy" reading is not.
        echo "[freeze-enforcer] CANNOT RUN — live burn-rate fetch is not implemented" >&2
        echo "  (D-SLO-CALC-LIVE-WIRING). ${CALC_URL}/slo/targets is config-only; there is no" >&2
        echo "  burn rate to read. Use --dry-run, --burn-rate, or LW_FREEZE_FIXTURE." >&2
        echo "  This used to return 0.0 = 'normal', which is a reading nobody took." >&2
        return 2
    fi

    if ! [[ "$burn_rate" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
        echo "[freeze-enforcer] invalid burn rate: $burn_rate" >&2
        return 2
    fi

    # Use awk for float comparisons (portable).
    local tier
    tier=$(awk -v b="$burn_rate" 'BEGIN {
        if (b >= 1.00)      print "slo-breach-postmortem"
        else if (b >= 0.90) print "approve-reliability-override"
        else if (b >= 0.75) print "reliability-review-required"
        else if (b >= 0.50) print "warn"
        else                print "normal"
    }')

    echo "[freeze-enforcer] burn_rate=$burn_rate (${burn_source}) tier=$tier"

    has_label() { [[ ",${PR_LABELS}," == *",$1,"* ]]; }

    case "$tier" in
        normal|warn)
            # No label required; PR may merge.
            return 0
            ;;
        reliability-review-required)
            if has_label reliability-review-required; then
                echo "[freeze-enforcer] PR has required label — merge allowed"
                return 0
            fi
            echo "[freeze-enforcer] BLOCKED: burn_rate=$burn_rate requires 'reliability-review-required' label" >&2
            return 1
            ;;
        approve-reliability-override)
            # The policy table above requires THIS label (tech-lead approval),
            # not both. A comment here used to claim both were needed, which
            # would have had a reader believing in a check that does not exist.
            if has_label approve-reliability-override; then
                echo "[freeze-enforcer] PR has override label — merge allowed (tech-lead approval assumed verified)"
                return 0
            fi
            echo "[freeze-enforcer] BLOCKED: burn_rate=$burn_rate (≥ 90%) requires 'approve-reliability-override' label + tech-lead approval" >&2
            return 1
            ;;
        slo-breach-postmortem)
            if has_label slo-breach-postmortem; then
                echo "[freeze-enforcer] PR has postmortem label — merge allowed"
                return 0
            fi
            echo "[freeze-enforcer] BLOCKED: burn_rate=$burn_rate ≥ 100% (SLO BREACH); postmortem mandatory before any feature merge" >&2
            return 1
            ;;
        *)
            echo "[freeze-enforcer] internal error: unknown tier $tier" >&2
            return 2
            ;;
    esac
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
selftest() {
    local failures=0 tmp
    tmp="$(mktemp -d)"

    # p <name> <want-rc> <want-substring> -- <args…>
    p() {
        local name="$1" want="$2" want_str="$3"; shift 3
        [[ "${1:-}" == "--" ]] && shift
        local out got
        set +e
        out="$( LW_FREEZE_BURN_RATE="" LW_FREEZE_FIXTURE="" run_enforcer "$@" 2>&1 )"
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

    echo "feature-freeze-enforcer --self-test"

    # the tier table — every boundary, in both directions
    p "below 50% is normal" 0 "tier=normal" -- --burn-rate 0.40
    p "50% is warn, and warn needs no label" 0 "tier=warn" -- --burn-rate 0.50
    p "just under 75% is still warn" 0 "tier=warn" -- --burn-rate 0.7499
    p "75% requires the review label" 1 "requires 'reliability-review-required'" -- --burn-rate 0.75
    p "...and passes when the PR carries it" 0 "has required label" \
        -- --burn-rate 0.80 --pr-labels reliability-review-required
    p "90% requires the OVERRIDE label" 1 "requires 'approve-reliability-override'" -- --burn-rate 0.90
    p "...and the review label alone is not enough" 1 "approve-reliability-override" \
        -- --burn-rate 0.95 --pr-labels reliability-review-required
    p "...but the override label is" 0 "has override label" \
        -- --burn-rate 0.95 --pr-labels approve-reliability-override
    p "100% is an SLO BREACH and needs the postmortem label" 1 "SLO BREACH" -- --burn-rate 1.00
    p "...and the override label does NOT satisfy a breach" 1 "SLO BREACH" \
        -- --burn-rate 1.00 --pr-labels approve-reliability-override
    p "...only the postmortem label does" 0 "has postmortem label" \
        -- --burn-rate 1.00 --pr-labels slo-breach-postmortem

    # the label boundary — an exact ,name, match, not a substring
    p "a label merely CONTAINING the name does not satisfy the tier" 1 "BLOCKED" \
        -- --burn-rate 0.80 --pr-labels needs-reliability-review-required-soon

    # LIVE MODE IS NOT WIRED — this case is the mechanism D-SLO-CALC-LIVE-WIRING
    # never had. Implement the fetch and it must change.
    p "live mode is CANNOT RUN, not a manufactured 0.0" 2 "live burn-rate fetch is not implemented" --

    # dry-run with no data says so rather than looking like a reading
    p "dry-run with no data announces that it has none" 0 "no burn data" -- --dry-run

    # the fixture path
    printf '{"burn_rate": 0.93}\n' > "$tmp/burn.json"
    local out got
    set +e
    out="$( LW_FREEZE_BURN_RATE="" LW_FREEZE_FIXTURE="$tmp/burn.json" run_enforcer 2>&1 )"
    got=$?
    set -e
    if [[ "$got" -eq 1 && "$out" == *"approve-reliability-override"* ]]; then
        echo "  ok   a fixture burn rate reaches its tier: rc=$got"
    else
        echo "  FAIL a fixture burn rate reaches its tier: rc=$got"
        failures=$((failures + 1))
    fi

    # misuse
    p "an invalid burn rate is misuse" 2 "invalid burn rate" -- --burn-rate high
    p "an unknown arg is misuse" 2 "unknown arg" -- --dry-run --bogus

    rm -rf "$tmp"
    if [[ $failures -gt 0 ]]; then
        echo "feature-freeze-enforcer --self-test: $failures rule(s) did not behave"
        return 2
    fi
    echo "feature-freeze-enforcer --self-test: every rule bites, and none cries wolf"
    return 0
}

case "${1:-}" in
    --self-test|--selftest) selftest ;;
    *)
        selftest || exit 2
        echo
        run_enforcer "$@"
        ;;
esac
