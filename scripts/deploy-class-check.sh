#!/usr/bin/env bash
# scripts/deploy-class-check.sh — L7.K.6 (RAID cycle 38)
#
# SR05 §12AH.2 deploy classification CI lint. Reads the PR's changed-file list
# + a few explicit signals and emits the deploy class (patch|minor|major|
# emergency). If a declared class (--declared) mismatches the detected class it
# fails the build (e.g. a migration file in a PR labelled `patch`).
#
# This is the shell sibling of services/canary-controller/internal/deployclass
# (one authoritative ruleset, two consumers). Classification rules:
#
#   emergency — `emergency` label AND (--incident-id OR --security-finding-id)
#   major     — >1 service touched OR any contracts/* change OR --contract-breaking
#               OR --schema-breaking
#   minor     — single service WITH a migration file OR config change
#               OR a contracts/api/* change
#   patch     — everything else
#
# Exit codes:
#   0 — class detected (printed to stdout); if --declared given, it matched
#   1 — declared/detected class mismatch (CI fail)
#   2 — usage error · empty changed-file list · MIRROR DRIFT · self-test failure
#
# Flags:
#   --files <file>          newline-delimited changed-file list (default: git diff)
#   --base <ref>            base ref for `git diff --name-only <base>...HEAD`
#   --declared <class>      assert the detected class equals this (else exit 1)
#   --emergency-label       PR carries the `emergency` label
#   --incident-id <id>      emergency justification
#   --security-finding-id <id>
#   --contract-breaking     upstream contract-diff lint flagged a break
#   --schema-breaking       upstream migration lint flagged a break
#   --self-test             prove every rule bites, then exit
#
# Environment:
#   LW_DEPLOY_FILES_FIXTURE  path to a changed-file fixture (test injection)
#
# ── GT7 · what this gate lacked ──────────────────────────────────────────────
# **"One authoritative ruleset, two consumers" with nothing comparing them.**
# The header says this file mirrors `internal/deployclass`, and a rule added to
# either side would have gone unnoticed — the Go side has a test table, the shell
# side had nothing, and neither knew about the other. A MIRROR CHECK now compares
# the decision ORDER (the four classes in the order they are returned) and the
# OPERAND COUNT of each branch against the Go source, so a fifth condition on one
# side reds. It is not a semantic equivalence proof; it is the drift that
# actually happens, made mechanical.
#
# An EMPTY changed-file list classified as `patch` and exited 0 — the reach floor
# was missing in the shape that matters here, because "the diff resolved to
# nothing" and "this PR is a small change" produced the same word.
#
# `--help` printed a FIXED line window (`sed -n '2,38p'`) into its own header —
# the brittle-window shape this repo has shipped three times. The window is now
# computed: comments from line 2 until the first non-comment line.

set -euo pipefail

SELF="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
GO_MIRROR="services/canary-controller/internal/deployclass/deployclass.go"

_help() {
    # Computed, not a hardcoded line range: print header comments from line 2
    # until the first line that is not a comment.
    awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$SELF"
}

# ── THE MIRROR CHECK ─────────────────────────────────────────────────────────
# Compares this file's decision structure with the Go classifier's. Returns 0 on
# agreement, 2 on drift or on a missing/unreadable Go source (a mirror check with
# nothing to mirror is not a pass).
mirror_check() {
    local go_file="$1"
    # `self_file` is a parameter so a probe can hand in a REWORDED copy of this
    # script. Without it the zero-extraction guard below has no discriminating
    # case: a broken Go extraction alone leaves the shell side at 3, which the
    # ordinary comparison already catches. The case that needs the guard is BOTH
    # sides going quiet at once — and only a settable self can build it.
    local self_file="${2:-$SELF}"
    if [[ ! -f "$go_file" ]]; then
        # NOT independent detection — a missing file yields empty extractions, so
        # the zero guard below would catch it anyway. Kept for the MESSAGE, the
        # same call made for the checklist gate's needle check. Diagnostics.
        echo "[deploy-class-check] ERROR — the Go mirror is not at $go_file." >&2
        echo "  This file exists to mirror it; with the other side gone, agreement is vacuous." >&2
        return 2
    fi

    # The ORDER the four classes are decided in, on each side.
    local go_order sh_order
    go_order="$(grep -oE 'return (Emergency|Major|Minor|Patch)$' "$go_file" \
        | sed -E 's/return //' | tr 'A-Z' 'a-z' | paste -sd, -)"
    sh_order="$(grep -oE '^\s*(class="(emergency|major|minor|patch)")' "$self_file" \
        | sed -E 's/.*class="([a-z]+)"/\1/' | paste -sd, -)"

    # The number of OR-ed operands in the major branch, on each side. A fifth
    # condition added to one and not the other is the drift that happens.
    # The shell branches live INSIDE `classify()`, so these patterns must tolerate
    # leading whitespace. Anchoring them at `^` made both counts 0 and the check
    # red on its own file — which is how the extraction got verified at all.
    local go_major sh_major
    go_major="$(grep -oE '\|\|' <<< "$(grep -E 'if len\(services\) > 1' "$go_file")" | wc -l | tr -d ' ')"
    sh_major="$(grep -oE '\|\|' <<< "$(grep -E '^[[:space:]]*elif \[\[ "\$service_count" -gt 1' "$self_file")" | wc -l | tr -d ' ')"

    local go_minor sh_minor
    go_minor="$(grep -oE '\|\|' <<< "$(grep -E 'if hasMigration \|\| hasConfig' "$go_file")" | wc -l | tr -d ' ')"
    sh_minor="$(grep -oE '\|\|' <<< "$(grep -E '^[[:space:]]*elif \[\[ "\$has_migration" -eq 1' "$self_file")" | wc -l | tr -d ' ')"

    # A zero on EITHER side means the extraction stopped matching, not that the
    # branches agree — two failed greps compare equal, which is `GTD-9` exactly.
    if [[ "$go_major" -eq 0 || "$sh_major" -eq 0 || "$go_minor" -eq 0 || "$sh_minor" -eq 0 ]]; then
        echo "[deploy-class-check] MIRROR CHECK BROKEN — an extraction matched nothing" >&2
        echo "    major: go=$go_major shell=$sh_major · minor: go=$go_minor shell=$sh_minor" >&2
        echo "  Two empty results compare equal; that is agreement about nothing." >&2
        return 2
    fi

    local bad=0
    if [[ "$go_order" != "$sh_order" || -z "$go_order" ]]; then
        echo "[deploy-class-check] MIRROR DRIFT — decision order differs:" >&2
        echo "    go:    ${go_order:-<none found>}" >&2
        echo "    shell: ${sh_order:-<none found>}" >&2
        bad=1
    fi
    if [[ "$go_major" != "$sh_major" ]]; then
        echo "[deploy-class-check] MIRROR DRIFT — the MAJOR branch has $go_major OR-operand(s) in Go, $sh_major here." >&2
        bad=1
    fi
    if [[ "$go_minor" != "$sh_minor" ]]; then
        echo "[deploy-class-check] MIRROR DRIFT — the MINOR branch has $go_minor OR-operand(s) in Go, $sh_minor here." >&2
        bad=1
    fi
    if [[ "$bad" -eq 1 ]]; then
        echo "  One authoritative ruleset, two consumers — they must move together." >&2
        return 2
    fi
    return 0
}

# ── THE CLASSIFIER ───────────────────────────────────────────────────────────
# classify <changed-file-text> <emergency_label> <incident_id> <security_id>
#          <contract_breaking> <schema_breaking>
# Echoes the class. Sets the globals the caller reports.
classify() {
    local changed="$1" emergency_label="$2" incident_id="$3" security_id="$4"
    local contract_breaking="$5" schema_breaking="$6"

    changed="$(printf '%s\n' "$changed" | tr '\\' '/' | tr -d '\r' | sed '/^$/d')"

    local services
    services="$(printf '%s\n' "$changed" \
        | grep -E '^services/[^/]+/' \
        | sed -E 's#^services/([^/]+)/.*#\1#' \
        | sort -u || true)"
    service_count=0
    [[ -n "$services" ]] && service_count="$(printf '%s\n' "$services" | sed '/^$/d' | wc -l | tr -d ' ')"

    # contracts/api/* is an endpoint change (→ minor if non-breaking); any other
    # contracts/* is an internal wire-shape change (→ major). Mirrors deployclass.
    has_contract_api=0
    printf '%s\n' "$changed" | grep -qE '^contracts/api/' && has_contract_api=1
    has_contract_nonapi=0
    printf '%s\n' "$changed" | grep -E '^contracts/' | grep -qvE '^contracts/api/' && has_contract_nonapi=1
    has_migration=0
    printf '%s\n' "$changed" | grep -qE '^migrations/.*\.sql$' && has_migration=1
    has_config=0
    printf '%s\n' "$changed" | grep -qE '(^config/|/config/)' && has_config=1

    local class="patch"
    if [[ "$emergency_label" -eq 1 && ( -n "$incident_id" || -n "$security_id" ) ]]; then
        class="emergency"
    elif [[ "$service_count" -gt 1 || "$contract_breaking" -eq 1 || "$schema_breaking" -eq 1 || "$has_contract_nonapi" -eq 1 ]]; then
        class="major"
    elif [[ "$has_migration" -eq 1 || "$has_config" -eq 1 || "$has_contract_api" -eq 1 ]]; then
        class="minor"
    else
        class="patch"
    fi
    # Emit the derived facts WITH the class. `classify` runs in a command
    # substitution, so anything it assigns to a global dies with that subshell —
    # the caller's report line hit `set -u` on `service_count` until this
    # returned them explicitly.
    printf '%s %s %s %s %s %s' "$class" "$service_count" "$has_contract_api" \
           "$has_contract_nonapi" "$has_migration" "$has_config"
}

run_main() {
    local FILES_SRC="" BASE_REF="" DECLARED=""
    local EMERGENCY_LABEL=0 INCIDENT_ID="" SECURITY_FINDING_ID=""
    local CONTRACT_BREAKING=0 SCHEMA_BREAKING=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --files) FILES_SRC="$2"; shift 2 ;;
            --base) BASE_REF="$2"; shift 2 ;;
            --declared) DECLARED="$2"; shift 2 ;;
            --emergency-label) EMERGENCY_LABEL=1; shift ;;
            --incident-id) INCIDENT_ID="$2"; shift 2 ;;
            --security-finding-id) SECURITY_FINDING_ID="$2"; shift 2 ;;
            --contract-breaking) CONTRACT_BREAKING=1; shift ;;
            --schema-breaking) SCHEMA_BREAKING=1; shift ;;
            --help|-h) _help; return 0 ;;
            *) echo "[deploy-class-check] unknown arg: $1" >&2; return 2 ;;
        esac
    done

    # ── THE MIRROR CHECK runs on every invocation: drift is not something you
    # remember to look for.
    mirror_check "$REPO_ROOT/$GO_MIRROR" || return 2

    local changed
    if [[ -n "${LW_DEPLOY_FILES_FIXTURE:-}" && -f "${LW_DEPLOY_FILES_FIXTURE}" ]]; then
        changed="$(cat "${LW_DEPLOY_FILES_FIXTURE}")"
    elif [[ -n "$FILES_SRC" && -f "$FILES_SRC" ]]; then
        changed="$(cat "$FILES_SRC")"
    elif [[ -n "$BASE_REF" ]]; then
        changed="$(git -C "$REPO_ROOT" diff --name-only "${BASE_REF}...HEAD")"
    else
        changed="$(git -C "$REPO_ROOT" diff --name-only HEAD 2>/dev/null || true)"
    fi

    # ── REACH FLOOR (GT-F3). An empty list classified as `patch` and exited 0,
    # so "the diff resolved to nothing" and "this is a small change" were the
    # same word. They are not the same thing, and only one of them is a fact.
    local n_files=0
    changed="$(printf '%s\n' "$changed" | tr -d '\r' | sed '/^$/d')"
    [[ -n "$changed" ]] && n_files="$(printf '%s\n' "$changed" | wc -l | tr -d ' ')"
    if [[ "$n_files" -eq 0 ]]; then
        echo "[deploy-class-check] ERROR — the changed-file list is EMPTY; there is nothing to" >&2
        echo "  classify. That is a diff that failed to resolve, not a patch (BDR-82)." >&2
        return 2
    fi

    local class n_svc c_api c_int mig cfg
    read -r class n_svc c_api c_int mig cfg <<< "$(classify "$changed" \
        "$EMERGENCY_LABEL" "$INCIDENT_ID" "$SECURITY_FINDING_ID" \
        "$CONTRACT_BREAKING" "$SCHEMA_BREAKING")"

    echo "[deploy-class-check] files=$n_files services_touched=$n_svc contract_api=$c_api contract_internal=$c_int migration=$mig config=$cfg → class=$class"

    if [[ -n "$DECLARED" ]]; then
        if [[ "$DECLARED" != "$class" ]]; then
            echo "[deploy-class-check] BLOCKED: PR declared class '$DECLARED' but detected '$class' (§12AH.2 mismatch)" >&2
            return 1
        fi
        echo "[deploy-class-check] declared class '$DECLARED' matches detected"
    fi

    echo "$class"
    return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
selftest() {
    local failures=0 tmp
    tmp="$(mktemp -d)"

    # cls <name> <want-class> <files…> — drives the REAL classifier
    cls() {
        local name="$1" want="$2"; shift 2
        local f="$tmp/files.txt"
        printf '%s\n' "$@" > "$f"
        local got
        got="$(classify "$(cat "$f")" 0 "" "" 0 0)"; got="${got%% *}"
        if [[ "$got" == "$want" ]]; then
            echo "  ok   $name: $got"
        else
            echo "  FAIL $name: $got (want $want)"
            failures=$((failures + 1))
        fi
    }

    # rc <name> <want-rc> <args…> — drives the REAL entry point
    rc() {
        local name="$1" want="$2"; shift 2
        local got
        set +e
        ( run_main "$@" ) >/dev/null 2>&1
        got=$?
        set -e
        if [[ "$got" == "$want" ]]; then
            echo "  ok   $name: rc=$got"
        else
            echo "  FAIL $name: rc=$got (want $want)"
            failures=$((failures + 1))
        fi
    }

    echo "deploy-class-check --self-test"

    # the classification table — every branch, in both directions
    cls "a single service is patch" patch "services/a/main.go"
    cls "TWO services is major" major "services/a/main.go" "services/b/main.go"
    cls "a non-api contracts change is major" major "contracts/events/x.json"
    cls "an api contracts change is MINOR, not major" minor "contracts/api/x.yaml"
    cls "a migration is minor" minor "migrations/0001_x.up.sql"
    cls "a non-.sql file under migrations is NOT" patch "migrations/README.md"
    cls "a top-level config change is minor" minor "config/app.yaml"
    cls "a nested /config/ change is minor" minor "services/a/config/x.yaml"
    cls "backslash paths normalise" major "services\\a\\main.go" "services\\b\\main.go"
    cls "a bare file outside every signal is patch" patch "README.md"

    # the explicit signals
    local f="$tmp/one.txt"; printf '%s\n' "services/a/main.go" > "$f"
    local got
    got="$(classify "$(cat "$f")" 0 "" "" 1 0)"; got="${got%% *}"
    [[ "$got" == "major" ]] && echo "  ok   --contract-breaking forces major: $got" \
        || { echo "  FAIL --contract-breaking forces major: $got"; failures=$((failures + 1)); }
    got="$(classify "$(cat "$f")" 0 "" "" 0 1)"; got="${got%% *}"
    [[ "$got" == "major" ]] && echo "  ok   --schema-breaking forces major: $got" \
        || { echo "  FAIL --schema-breaking forces major: $got"; failures=$((failures + 1)); }
    got="$(classify "$(cat "$f")" 1 "INC-1" "" 0 0)"; got="${got%% *}"
    [[ "$got" == "emergency" ]] && echo "  ok   label + incident id is emergency: $got" \
        || { echo "  FAIL label + incident id is emergency: $got"; failures=$((failures + 1)); }
    got="$(classify "$(cat "$f")" 1 "" "SEC-1" 0 0)"; got="${got%% *}"
    [[ "$got" == "emergency" ]] && echo "  ok   label + security finding is emergency: $got" \
        || { echo "  FAIL label + security finding is emergency: $got"; failures=$((failures + 1)); }
    # the label ALONE must not fast-track — an emergency needs a justification
    got="$(classify "$(cat "$f")" 1 "" "" 0 0)"; got="${got%% *}"
    [[ "$got" == "patch" ]] && echo "  ok   the label ALONE is not emergency: $got" \
        || { echo "  FAIL the label ALONE is not emergency: $got"; failures=$((failures + 1)); }

    # end-to-end exit codes
    printf '%s\n' "migrations/0001_x.up.sql" > "$tmp/mig.txt"
    rc "a matching --declared passes" 0 --files "$tmp/mig.txt" --declared minor
    rc "a MISMATCHED --declared is blocked" 1 --files "$tmp/mig.txt" --declared patch
    rc "an unknown arg is misuse" 2 --files "$tmp/mig.txt" --bogus
    : > "$tmp/empty.txt"
    rc "an EMPTY changed-file list is misuse, not a patch" 2 --files "$tmp/empty.txt"

    # the mirror check
    set +e
    ( mirror_check "$REPO_ROOT/$GO_MIRROR" ) >/dev/null 2>&1; got=$?
    set -e
    [[ "$got" -eq 0 ]] && echo "  ok   the shell and Go classifiers agree: rc=$got" \
        || { echo "  FAIL the shell and Go classifiers agree: rc=$got"; failures=$((failures + 1)); }
    set +e
    ( mirror_check "$tmp/no-such-file.go" ) >/dev/null 2>&1; got=$?
    set -e
    [[ "$got" -eq 2 ]] && echo "  ok   a MISSING Go mirror is misuse, not agreement: rc=$got" \
        || { echo "  FAIL a MISSING Go mirror is misuse, not agreement: rc=$got"; failures=$((failures + 1)); }
    # a Go source whose MAJOR branch grew a condition must red
    sed -E 's/if len\(services\) > 1 \|\|/if len(services) > 1 || s.Extra ||/' \
        "$REPO_ROOT/$GO_MIRROR" > "$tmp/drift.go"
    set +e
    ( mirror_check "$tmp/drift.go" ) >/dev/null 2>&1; got=$?
    set -e
    [[ "$got" -eq 2 ]] && echo "  ok   a Go MAJOR branch that grew a condition is DRIFT: rc=$got" \
        || { echo "  FAIL a Go MAJOR branch that grew a condition is DRIFT: rc=$got"; failures=$((failures + 1)); }

    # a Go source that lost a class from the decision ORDER must red — the
    # operand counts still agree, so only the order comparison can catch it
    sed -E 's/^\treturn Patch$/\treturn Minor/' "$REPO_ROOT/$GO_MIRROR" > "$tmp/order.go"
    set +e
    ( mirror_check "$tmp/order.go" ) >/dev/null 2>&1; got=$?
    set -e
    [[ "$got" -eq 2 ]] && echo "  ok   a Go decision ORDER that lost a class is DRIFT: rc=$got" \
        || { echo "  FAIL a Go decision ORDER that lost a class is DRIFT: rc=$got"; failures=$((failures + 1)); }

    # BOTH extractions reworded at once — the counts then agree (0 == 0) and the
    # order still matches, so the ordinary comparisons are silent and ONLY the
    # zero guard can speak. Rewording just the Go side is not this case: the shell
    # stays at 3 and the operand comparison catches it, which is why the arm for
    # this guard came back green until the probe was built properly.
    sed -E 's/if len\(services\) > 1/if serviceCount > 1/; s/if hasMigration \|\| hasConfig/if migrated || configured/' \
        "$REPO_ROOT/$GO_MIRROR" > "$tmp/miss.go"
    sed -E 's/elif \[\[ "\$service_count" -gt 1/elif [[ "$svc_n" -gt 1/; s/elif \[\[ "\$has_migration" -eq 1/elif [[ "$mig" -eq 1/' \
        "$SELF" > "$tmp/miss.sh"
    set +e
    ( mirror_check "$tmp/miss.go" "$tmp/miss.sh" ) >/dev/null 2>&1; got=$?
    set -e
    [[ "$got" -eq 2 ]] && echo "  ok   an extraction that matches NOTHING is not agreement: rc=$got" \
        || { echo "  FAIL an extraction that matches NOTHING is not agreement: rc=$got"; failures=$((failures + 1)); }

    rm -rf "$tmp"
    if [[ $failures -gt 0 ]]; then
        echo "deploy-class-check --self-test: $failures rule(s) did not behave"
        return 2
    fi
    echo "deploy-class-check --self-test: every rule bites, and none cries wolf"
    return 0
}

case "${1:-}" in
    --self-test|--selftest) selftest ;;
    *)
        selftest || exit 2
        echo
        run_main "$@"
        ;;
esac
