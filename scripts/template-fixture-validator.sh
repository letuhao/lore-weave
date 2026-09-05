#!/usr/bin/env bash
# template-fixture-validator.sh — cycle 31 L6.K.6 CI lint.
#
# Blocks PRs that bump a template version without also adding the
# matching fixture directory. Per Q-L6K-1 LOCKED: foundation ships
# EMPTY templates but the structural shape is load-bearing — the
# fixture directory must exist (even if .gitkeep-only) so downstream
# replay tooling has a canonical path to write into.
#
# Rules enforced:
#   1. For every intent in contracts/prompt/templates/registry.yaml, the
#      registry's OWN `active_version: N` must have <intent>/vN.tmpl +
#      <intent>/vN.meta.yaml + <intent>/vN.fixtures/ on disk.
#   2. The registry's intent set must equal the Intent enum in
#      contracts/prompt/intent.go — one authoritative list, two consumers.
#   3. Meta.yaml must declare matching intent + version.
#
# Exit 0 on pass · 1 on any rule failure · 2 on misuse / self-test failure.
#
# ── GT8 · what this gate lacked ──────────────────────────────────────────────
# **IT COULD NOT DO THE JOB ITS FIRST SENTENCE DESCRIBES.** The header says it
# "blocks PRs that bump a template version without also adding the matching
# fixture directory" — and it hardcoded `v1` everywhere, under the comment
# "Pick active_version (default 1 for skeleton)". Bump `active_version` to 2 and
# the gate goes on checking v1, which still exists, and passes. The registry's
# own schema comment states the contract it was not enforcing: "`active_version`
# MUST match a v<N>.tmpl + v<N>.meta.yaml pair on disk." Now read from the
# registry, per intent.
#
# **The 7-intent list was a hardcoded MIRROR of `AllIntents()` with no drift
# check** — the header even says "matches AllIntents() in contracts/prompt/
# intent.go". An eighth intent added to the Go enum would have been invisible
# here, and rule 2 ("registry MUST list all 7 intents") would have gone on
# checking the old seven. The set is now DERIVED from the Go constants and
# compared with the registry, so a change on either side reds. The count `7` is
# gone from the logic; it survives only in prose.
#
#
# THREE OF ITS GUARDS ARE MESSAGE REFINEMENTS, NOT DETECTION, and are marked as
# such below: a missing `intent.go`, a non-numeric `active_version`, and a
# missing intent directory are each caught anyway by the check downstream (the
# zero-set guard, the tmpl/meta presence check, the tmpl/meta presence check).
# Bite arms for all three came back GREEN. They stay because "intent.go is
# missing" and "an extraction matched nothing" send a reader to different
# places — but nothing here should be read as an independent rule.
#
# Its reach was sound before this pass — a hardcoded expected list cannot pass
# over nothing, and a missing registry already exited non-zero. That is two
# gates out of thirty on this board that did not need a floor.

set -euo pipefail

SELF="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"

TEMPLATES_REL="contracts/prompt/templates"
INTENT_GO_REL="contracts/prompt/intent.go"

# Intent string constants declared in the Go enum: `IntentFoo Intent = "foo"`.
go_intents() {
    local go_file="$1"
    grep -oE 'Intent[A-Za-z]+ +Intent += +"[a-z_]+"' "$go_file" 2>/dev/null \
        | sed -E 's/.*"([a-z_]+)"/\1/' | sort -u || true
}

# Intents declared in the registry: two-space-indented `name:` under `intents:`.
registry_intents() {
    local reg="$1"
    awk '/^intents:/ {inb=1; next} inb && /^[a-z]/ {inb=0} inb && /^  [a-z_]+:/ {
        gsub(/[: ]/, "", $1); print $1 }' "$reg" 2>/dev/null | sort -u || true
}

# The registry's own active_version for one intent.
active_version() {
    local reg="$1" intent="$2"
    awk -v want="$intent" '
        /^  [a-z_]+:/ { cur = $1; gsub(/[: ]/, "", cur) }
        cur == want && /^[[:space:]]+active_version:/ { print $2; exit }
    ' "$reg" 2>/dev/null || true
}

# run_lint <tree_root>
run_lint() {
    local root="$1"
    local templates_dir="$root/$TEMPLATES_REL"
    local registry="$templates_dir/registry.yaml"
    local go_file="$root/$INTENT_GO_REL"
    local errors=0

    if [[ ! -f "$registry" ]]; then
        echo "[template-fixture-validator] FAIL: registry.yaml missing at $registry" >&2
        return 1
    fi
    # message refinement, not detection — see the header note
    if [[ ! -f "$go_file" ]]; then
        echo "[template-fixture-validator] ERROR: $INTENT_GO_REL missing — the intent set has" >&2
        echo "  no authority to be compared against, so agreement would be vacuous." >&2
        return 2
    fi

    local go_set reg_set
    go_set="$(go_intents "$go_file")"
    reg_set="$(registry_intents "$registry")"

    # ── Two empty sets compare equal (GTD-9). Either extraction going quiet is a
    # broken parser, not agreement.
    if [[ -z "$go_set" || -z "$reg_set" ]]; then
        echo "[template-fixture-validator] ERROR: an intent extraction matched NOTHING" >&2
        echo "    intent.go: $(printf '%s' "$go_set" | grep -c . || true) · registry: $(printf '%s' "$reg_set" | grep -c . || true)" >&2
        echo "  Two empty sets are equal; that is agreement about nothing." >&2
        return 2
    fi

    # ── RULE 2 · the mirror. One authoritative list, two consumers.
    if [[ "$go_set" != "$reg_set" ]]; then
        echo "[template-fixture-validator] FAIL: registry.yaml and $INTENT_GO_REL disagree:" >&2
        comm -3 <(printf '%s\n' "$go_set") <(printf '%s\n' "$reg_set") \
            | sed 's/^\t/  only in registry: /; s/^\([a-z]\)/  only in intent.go: \1/' >&2
        errors=$((errors + 1))
    fi

    local n_intents=0 n_checked=0 intent
    while IFS= read -r intent; do
        [[ -z "$intent" ]] && continue
        n_intents=$((n_intents + 1))
        local intent_dir="$templates_dir/$intent"
        # message refinement, not detection — the presence check below catches it
        if [[ ! -d "$intent_dir" ]]; then
            echo "[template-fixture-validator] FAIL: ${intent_dir}/ missing" >&2
            errors=$((errors + 1))
            continue
        fi

        # ── RULE 1 · the ACTIVE version, read from the registry rather than
        # assumed to be 1. This is the rule the gate's first sentence promises.
        local v
        v="$(active_version "$registry" "$intent")"
        # message refinement, not detection — a bogus version yields missing files
        if [[ ! "$v" =~ ^[0-9]+$ ]]; then
            echo "[template-fixture-validator] FAIL: ${intent} has no numeric active_version in registry.yaml (got '${v}')" >&2
            errors=$((errors + 1))
            continue
        fi
        n_checked=$((n_checked + 1))

        local required
        for required in "v${v}.tmpl" "v${v}.meta.yaml"; do
            if [[ ! -f "${intent_dir}/${required}" ]]; then
                echo "[template-fixture-validator] FAIL: ${intent_dir}/${required} missing (active_version=${v})" >&2
                errors=$((errors + 1))
            fi
        done
        if [[ ! -d "${intent_dir}/v${v}.fixtures" ]]; then
            echo "[template-fixture-validator] FAIL: ${intent_dir}/v${v}.fixtures/ missing (active_version=${v})" >&2
            errors=$((errors + 1))
        fi

        # ── RULE 3 · meta.yaml declares the matching intent + version.
        if [[ -f "${intent_dir}/v${v}.meta.yaml" ]]; then
            if ! grep -q "^intent: ${intent}\$" "${intent_dir}/v${v}.meta.yaml"; then
                echo "[template-fixture-validator] FAIL: ${intent_dir}/v${v}.meta.yaml does not declare intent: ${intent}" >&2
                errors=$((errors + 1))
            fi
            if ! grep -q "^version: ${v}\$" "${intent_dir}/v${v}.meta.yaml"; then
                echo "[template-fixture-validator] FAIL: ${intent_dir}/v${v}.meta.yaml does not declare version: ${v}" >&2
                errors=$((errors + 1))
            fi
        fi
    done <<< "$reg_set"

    if [[ $errors -gt 0 ]]; then
        echo "[template-fixture-validator] FAIL: ${errors} error(s)" >&2
        return 1
    fi
    echo "[template-fixture-validator] OK: ${n_intents} intent(s) agree with ${INTENT_GO_REL};" \
         "${n_checked} active version(s) have tmpl + meta + fixtures"
    return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
seed_tree() {
    local d="$1" i
    mkdir -p "$d/$TEMPLATES_REL" "$d/contracts/prompt"
    {
        printf 'package prompt\n\nconst (\n'
        for i in alpha beta; do
            printf '\tIntent%s Intent = "%s"\n' "${i^}" "$i"
        done
        printf ')\n'
    } > "$d/$INTENT_GO_REL"
    {
        printf 'intents:\n'
        for i in alpha beta; do
            printf '  %s:\n    active_version: 1\n    deprecated_versions: []\n' "$i"
        done
    } > "$d/$TEMPLATES_REL/registry.yaml"
    for i in alpha beta; do
        mkdir -p "$d/$TEMPLATES_REL/$i/v1.fixtures"
        printf '' > "$d/$TEMPLATES_REL/$i/v1.tmpl"
        printf 'intent: %s\nversion: 1\n' "$i" > "$d/$TEMPLATES_REL/$i/v1.meta.yaml"
    done
}

selftest() {
    local failures=0

    probe() {
        local name="$1" want="$2" setup="$3"
        local d got
        d="$(mktemp -d)"
        seed_tree "$d"
        "$setup" "$d"
        set +e
        ( run_lint "$d" ) >/dev/null 2>&1
        got=$?
        set -e
        rm -rf "$d"
        if [[ "$got" == "$want" ]]; then
            echo "  ok   $name: rc=$got"
        else
            echo "  FAIL $name: rc=$got (want $want)"
            failures=$((failures + 1))
        fi
    }

    T="$TEMPLATES_REL"
    s_none()       { :; }
    s_no_tmpl()    { rm -f "$1/$T/alpha/v1.tmpl"; }
    s_no_meta()    { rm -f "$1/$T/alpha/v1.meta.yaml"; }
    s_no_fixtures(){ rm -rf "$1/$T/alpha/v1.fixtures"; }
    s_no_dir()     { rm -rf "$1/$T/alpha"; }
    s_bad_intent() { printf 'intent: wrong\nversion: 1\n' > "$1/$T/alpha/v1.meta.yaml"; }
    s_bad_version(){ printf 'intent: alpha\nversion: 9\n' > "$1/$T/alpha/v1.meta.yaml"; }
    # THE RULE THE GATE PROMISED: bump the active version without shipping v2.
    s_bump()       { sed -i '0,/active_version: 1/s//active_version: 2/' "$1/$T/registry.yaml"; }
    # …and shipping v2 properly must pass
    s_bump_ok()    { sed -i '0,/active_version: 1/s//active_version: 2/' "$1/$T/registry.yaml"
                     mkdir -p "$1/$T/alpha/v2.fixtures"
                     printf '' > "$1/$T/alpha/v2.tmpl"
                     printf 'intent: alpha\nversion: 2\n' > "$1/$T/alpha/v2.meta.yaml"; }
    s_no_active()  { sed -i 's/active_version: 1/active_version: latest/' "$1/$T/registry.yaml"; }
    # THE MIRROR
    s_go_extra()   { printf '\tIntentGamma Intent = "gamma"\n' >> "$1/$INTENT_GO_REL"; }
    s_reg_extra()  { printf '  gamma:\n    active_version: 1\n' >> "$1/$T/registry.yaml"; }
    s_go_gone()    { rm -f "$1/$INTENT_GO_REL"; }
    s_go_reworded(){ sed -i 's/Intent = /IntentKind = /' "$1/$INTENT_GO_REL"; }
    s_reg_gone()   { rm -f "$1/$T/registry.yaml"; }

    echo "template-fixture-validator --self-test"

    probe "a complete skeleton passes" 0 s_none

    # rule 1 — at the ACTIVE version
    probe "a missing .tmpl fails" 1 s_no_tmpl
    probe "a missing .meta.yaml fails" 1 s_no_meta
    probe "a missing .fixtures/ dir fails" 1 s_no_fixtures
    probe "a missing intent dir fails" 1 s_no_dir
    probe "BUMPING active_version without shipping v2 fails" 1 s_bump
    probe "...and shipping v2 properly passes" 0 s_bump_ok
    probe "a non-numeric active_version fails" 1 s_no_active

    # rule 3
    probe "a meta.yaml declaring the wrong intent fails" 1 s_bad_intent
    probe "a meta.yaml declaring the wrong version fails" 1 s_bad_version

    # rule 2 — the mirror
    probe "an intent in intent.go but not the registry fails" 1 s_go_extra
    probe "an intent in the registry but not intent.go fails" 1 s_reg_extra
    probe "a MISSING intent.go is misuse, not agreement" 2 s_go_gone
    probe "a REWORDED enum (extraction matches nothing) is misuse" 2 s_go_reworded
    probe "a MISSING registry fails" 1 s_reg_gone

    if [[ $failures -gt 0 ]]; then
        echo "template-fixture-validator --self-test: $failures rule(s) did not behave"
        return 2
    fi
    echo "template-fixture-validator --self-test: every rule bites, and none cries wolf"
    return 0
}

case "${1:-}" in
    --self-test|--selftest) selftest ;;
    "")
        selftest || exit 2
        echo
        run_lint "$REPO_ROOT"
        ;;
    *)
        echo "usage: $0 [--self-test]" >&2
        exit 2
        ;;
esac
