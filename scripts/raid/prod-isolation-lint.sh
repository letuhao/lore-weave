#!/usr/bin/env bash
# prod-isolation-lint — B5 enforcement
# Per RAID_WORKFLOW.md §13.5
#
# Refuses any DPS commit / cycle commit that references existing LoreWeave
# prod hostname, prod IPs, or modifies infra/existing-prod/.
#
# Usage: prod-isolation-lint.sh [<commit-sha-or-range>]
#        With no arg, lints staged diff. With sha/range, lints that range.
#        --self-test  proves every rule bites, over synthetic diffs.
#
# Exit: 0 clean · 1 violation · 2 misuse (bad range, self-test failure)
#
# ── GT7 · what this gate lacked, and what it cannot have ─────────────────────
# **THE HOSTNAME LIST WAS ENUMERATED** — four literal names — so a fifth prod
# host was default-uncovered (`NV-3`). Replaced with the structural pattern
# `prod*.loreweave.*`, which subsumes all four and catches the next one. The four
# are kept in a comment as the set that motivated it, not as the rule.
#
# **This gate is DIFF-SCOPED, and that is deliberate, not an oversight.** It reads
# added lines only, so anything already committed is invisible to it — and it has
# to be: `infra/foundation-dev/docker-compose.yml` line 12 says *"Foundation
# cycles target THIS env, NEVER existing prod.loreweave.app"*, which is the rule
# being obeyed, written in the forbidden words. A whole-tree scan would red on the
# comment that documents the invariant. So the honest consequence is stated rather
# than hidden: **in `gate-wiring-gate --run-all` on a clean tree this gate has no
# subject and its green means nothing.** What gives it teeth is the self-test
# below, which drives the real predicate over synthetic diffs.
#
# **A bad range was swallowed.** `git diff -U0 "$RANGE" || true` turned an
# unresolvable ref into an empty diff and a clean pass — "I could not read that
# commit" and "that commit is fine" were the same exit code. Now exit 2.
#
# The audit-log path is a parameter so the self-test cannot append to the real
# `docs/audit/AUDIT_LOG.jsonl`; a gate's proof must not write to its own evidence.
#
# Guarded infra paths measured 2026-08-12: NEITHER `infra/existing-prod/` nor
# `infra/loreweave-novel-platform/` exists in this tree — and that is the B5
# invariant HOLDING, not a dead rule. The arm guards against their creation.
set -euo pipefail

SELF="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd "$(dirname "$SELF")/../.." && pwd)"
DEFAULT_AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"

# Structural, not enumerated. Subsumes the four names that motivated this rule —
# prod.loreweave.app, prod-postgres.loreweave, prod-redis.loreweave,
# prod-minio.loreweave — and catches prod-<anything>.loreweave.<anything>.
PROD_HOST_RE='(^|[^a-z0-9-])prod[a-z0-9-]*\.loreweave[a-z.]*'
PROD_PATH_RE='^infra/existing-prod/|^infra/loreweave-novel-platform/'

# The two files allowed to name the hosts this gate forbids, for the same reason:
# the gate itself produces both. Writing the rule — and writing cases that prove
# the rule bites — requires the literal strings, and the AUDIT LOG is where this
# gate RECORDS a violation, so every entry it writes quotes the offending line
# back. A gate that reds on its own output is a gate that reds once and then
# forever. Nothing else is exempt; the shrink arm below refuses to run if either
# path stops existing, so neither can outlive its subject (GT-F5).
#
# Found the hard way: the first run of this rewrite flagged its own source, and
# the SECOND flagged the audit record the first had just written.
SELF_EXEMPT_PATHS=(
  "scripts/raid/prod-isolation-lint.sh"   # the detector — must name its subject
  "docs/audit/AUDIT_LOG.jsonl"            # the gate's own output quotes the hit
)

# ── SHRINK ARM (GT-F5) on the exemptions. A path that is not a file exempts
# nothing today, and would exempt it again the day the name returns. A separate
# function so a case can drive it: an arm disabling a guard no probe reaches is
# an arm that proves nothing.
check_exemptions() {
    local e
    for e in "$@"; do
        if [[ ! -f "$REPO_ROOT/$e" ]]; then
            echo "[prod-isolation-lint] ERROR — exemption '$e' is not a file." >&2
            echo "  The only exemptions this gate has must name something real." >&2
            return 2
        fi
    done
    return 0
}

# run_lint <diff-text> <files-text> <audit-log-path> [exempt-path...]
run_lint() {
    local diff_text="$1" files_text="$2" audit_log="$3"
    local exempt=("${@:4}")
    [[ $# -lt 4 ]] && exempt=("${SELF_EXEMPT_PATHS[@]}")
    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    local n_added=0 n_files=0
    [[ -n "$files_text" ]] && n_files="$(printf '%s\n' "$files_text" | sed '/^$/d' | wc -l | tr -d ' ')"

    # Added lines ATTRIBUTED to their file, by tracking `+++ b/<path>` headers.
    # The previous version flattened the diff, so it could not tell whose line it
    # was reading — which is also why it had no way to exempt anything narrowly.
    local added cur_file="" line
    added=""
    while IFS= read -r line; do
        case "$line" in
            "+++ b/"*) cur_file="${line#+++ b/}"; continue ;;
            "+++ "*)   cur_file="${line#+++ }";   continue ;;
            "--- "*)   continue ;;
        esac
        [[ "$line" == +* && "$line" != "++"* ]] || continue
        n_added=$((n_added + 1))
        local skip=0 e
        for e in ${exempt+"${exempt[@]}"}; do
            [[ -n "$e" && "$cur_file" == "$e" ]] && skip=1
        done
        [[ "$skip" -eq 1 ]] && continue
        added+="${cur_file}: ${line}"$'\n'
    done <<< "$diff_text"

    local violations=()

    local prod_hits
    prod_hits="$(printf '%s' "$added" | grep -iE "$PROD_HOST_RE" || true)"
    if [[ -n "$prod_hits" ]]; then
        violations+=("prod hostname reference in diff:")
        while IFS= read -r line; do
            violations+=("    $line")
        done <<< "$prod_hits"
    fi

    local existing_prod_files
    existing_prod_files="$(printf '%s\n' "$files_text" | grep -E "$PROD_PATH_RE" || true)"
    if [[ -n "$existing_prod_files" ]]; then
        violations+=("touched existing-prod infra paths:")
        while IFS= read -r f; do
            violations+=("    $f")
        done <<< "$existing_prod_files"
    fi

    if [[ "${#violations[@]}" -gt 0 ]]; then
        echo "[prod-isolation-lint] VIOLATIONS detected:" >&2
        local v
        for v in "${violations[@]}"; do
            echo "  $v" >&2
        done
        mkdir -p "$(dirname "$audit_log")"
        local esc
        esc="$(printf '%s' "${violations[*]}" | tr '\n' ' ' | sed 's/"/\\"/g')"
        echo "{\"ts\":\"$now\",\"event\":\"prod_isolation_violation\",\"detail\":\"$esc\"}" >> "$audit_log"
        return 1
    fi
    echo "[prod-isolation-lint] ok: no prod references — examined $n_added added line(s) across $n_files changed file(s)"
    return 0
}

collect_and_run() {
    local range="${1:-}"
    local diff_text files_text

    check_exemptions "${SELF_EXEMPT_PATHS[@]}" || return 2
    if [[ -z "$range" ]]; then
        diff_text="$(git -C "$REPO_ROOT" diff --cached -U0 2>/dev/null || true)"
        if [[ -z "$diff_text" ]]; then
            diff_text="$(git -C "$REPO_ROOT" diff -U0 2>/dev/null || true)"
        fi
        files_text="$(git -C "$REPO_ROOT" diff --cached --name-only 2>/dev/null; git -C "$REPO_ROOT" diff --name-only 2>/dev/null)"
    else
        # A range that does not resolve used to become an empty diff and a clean
        # pass: "I could not read that commit" and "that commit is fine" were the
        # same exit code.
        if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$range" >/dev/null 2>&1 \
           && ! git -C "$REPO_ROOT" diff --name-only "$range" >/dev/null 2>&1; then
            echo "[prod-isolation-lint] ERROR — cannot resolve '$range' to a commit or range." >&2
            echo "  An unreadable range is not a clean one." >&2
            return 2
        fi
        diff_text="$(git -C "$REPO_ROOT" diff -U0 "$range" 2>/dev/null || true)"
        files_text="$(git -C "$REPO_ROOT" diff --name-only "$range" 2>/dev/null || true)"
    fi
    run_lint "$diff_text" "$files_text" "$DEFAULT_AUDIT_LOG"
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
selftest() {
    local failures=0 tmp got
    tmp="$(mktemp -d)"
    local log="$tmp/audit.jsonl"

    # p <name> <want-rc> <added-line> <files-text> [attributed-file] [exempt]
    # The added line is wrapped in a `+++ b/<file>` header so the attribution the
    # exemption depends on is exercised by every probe, not just the ones about it.
    p() {
        local name="$1" want="$2" d="$3" f="$4"
        local attrib="${5:-a.txt}" exempt="${6-${SELF_EXEMPT_PATHS[0]}}"
        local got
        set +e
        ( run_lint "+++ b/${attrib}
${d}" "$f" "$log" "$exempt" ) >/dev/null 2>&1
        got=$?
        set -e
        if [[ "$got" == "$want" ]]; then
            echo "  ok   $name: rc=$got"
        else
            echo "  FAIL $name: rc=$got (want $want)"
            failures=$((failures + 1))
        fi
    }

    echo "prod-isolation-lint --self-test"

    p "a clean diff passes" 0 "+some ordinary line" "services/a/main.go"

    # the hostname arm
    p "an ADDED prod hostname fails" 1 "+url = https://prod.loreweave.app/v1" "a.txt"
    p "...and a prod-postgres host fails" 1 "+host: prod-postgres.loreweave.internal" "a.txt"
    # THE NV-3 FIX: a host the old enumerated list had never heard of
    p "...and a NEW prod host the old list never knew fails" 1 \
        "+broker: prod-kafka.loreweave.app" "a.txt"
    p "...case-insensitively" 1 "+URL = HTTPS://PROD.LOREWEAVE.APP" "a.txt"

    # …and the shapes that must NOT cry wolf
    p "a REMOVED prod hostname does not fail" 0 "-url = https://prod.loreweave.app/v1" "a.txt"
    p "a CONTEXT line mentioning it does not fail" 0 " url = https://prod.loreweave.app/v1" "a.txt"
    p "the +++ file header does not fail" 0 "+++ b/infra/prod.loreweave.app.yml" "a.txt"
    p "a non-prod loreweave host does not fail" 0 "+host: dev.loreweave.app" "a.txt"
    p "a word merely ENDING in prod does not fail" 0 "+host: notprod.loreweave.app" "a.txt"

    # THE ONE EXEMPTION, and its narrowness
    p "the detector's own source may name what it detects" 0 \
        "+url = https://prod.loreweave.app/v1" "a.txt" "${SELF_EXEMPT_PATHS[0]}"
    p "...but a SIBLING script may not" 1 \
        "+url = https://prod.loreweave.app/v1" "a.txt" "scripts/raid/other-lint.sh"
    p "...and with the exemption empty, even the detector reds" 1 \
        "+url = https://prod.loreweave.app/v1" "a.txt" "${SELF_EXEMPT_PATHS[0]}" ""

    # the path arm
    p "touching infra/existing-prod/ fails" 1 "+x" "infra/existing-prod/main.tf"
    p "touching infra/loreweave-novel-platform/ fails" 1 "+x" "infra/loreweave-novel-platform/a.tf"
    p "...but a sibling infra path does not" 0 "+x" "infra/foundation-dev/docker-compose.yml"

    # the audit trail, and that it went to the FIXTURE log
    if [[ -s "$log" ]] && grep -q "prod_isolation_violation" "$log"; then
        echo "  ok   a violation is appended to the audit log"
    else
        echo "  FAIL a violation is appended to the audit log"
        failures=$((failures + 1))
    fi
    if [[ "$log" != "$DEFAULT_AUDIT_LOG" ]]; then
        echo "  ok   the self-test wrote to its OWN log, not the repo's evidence"
    else
        echo "  FAIL the self-test wrote to the repo's audit log"
        failures=$((failures + 1))
    fi

    # the exemption shrink arm, both directions
    set +e
    ( check_exemptions "${SELF_EXEMPT_PATHS[@]}" ) >/dev/null 2>&1; got=$?
    set -e
    [[ "$got" -eq 0 ]] && echo "  ok   the real exemption paths all exist: rc=$got"         || { echo "  FAIL the real exemption paths all exist: rc=$got"; failures=$((failures + 1)); }
    set +e
    ( check_exemptions "scripts/raid/gone-lint.sh" ) >/dev/null 2>&1; got=$?
    set -e
    [[ "$got" -eq 2 ]] && echo "  ok   an exemption naming a missing file is misuse: rc=$got"         || { echo "  FAIL an exemption naming a missing file is misuse: rc=$got"; failures=$((failures + 1)); }

    # a bad range is misuse
    local got
    set +e
    ( collect_and_run "definitely-not-a-ref-xyz" ) >/dev/null 2>&1
    got=$?
    set -e
    if [[ "$got" -eq 2 ]]; then
        echo "  ok   an unresolvable range is misuse, not a clean pass: rc=$got"
    else
        echo "  FAIL an unresolvable range is misuse, not a clean pass: rc=$got"
        failures=$((failures + 1))
    fi

    rm -rf "$tmp"
    if [[ $failures -gt 0 ]]; then
        echo "prod-isolation-lint --self-test: $failures rule(s) did not behave"
        return 2
    fi
    echo "prod-isolation-lint --self-test: every rule bites, and none cries wolf"
    return 0
}

case "${1:-}" in
    --self-test|--selftest) selftest ;;
    *)
        selftest || exit 2
        echo
        collect_and_run "${1:-}"
        ;;
esac
