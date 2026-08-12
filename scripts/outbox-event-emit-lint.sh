#!/usr/bin/env bash
# L1.K.12 outbox-event-emit-lint.sh — I13 outbox discipline
#
# Two rules:
#   1. Direct Redis Streams writes (`.XAdd(` / `.xadd(`) are FORBIDDEN outside
#      services/publisher/ and the sanctioned relays below. Services emit events
#      via the outbox table; the publisher is the only writer to Redis Streams.
#   2. contracts/meta/events_allowlist.yaml integrity — every `table:` it names
#      must have a migration, every `event_name` must be unique, every `op` must
#      be one of INSERT/UPDATE/DELETE.
#
# Exit 0 = clean; 1 = violations; 2 = self-test failure / nothing scanned.
#
# ── GT8 · what this gate lacked ──────────────────────────────────────────────
# **RULE 2 DID NOT EXIST.** The header claimed *"Also enforces the
# events_allowlist.yaml ↔ service-map cross-check at the YAML level (every
# emitted event MUST appear in allowlist)"* — and the file contained no
# reference to that YAML except that sentence. It is claimed on BOTH sides:
# `contracts/meta/events_allowlist.yaml`'s own header says *"The L1.K lint that
# cross-references this file with the service-map ships in cycle 11 (L1.K)."*
# The lint shipped; the cross-check did not. Two documents agreeing about a
# mechanism neither of them has.
#
# What is built here is the checkable part, described exactly rather than
# aspirationally. **The `owner:` field is NOT machine-checkable and no arm
# pretends otherwise**: measured 2026-08-12, 13 of its 18 distinct values are
# prose ("admin-cli (cycle 36)", "shard health agent (per-shard sidecar; cycle
# TBD L7)"), so an owner→service arm would cry wolf on documentation. The
# service-map derivation the two headers describe needs a machine-readable
# emits column that does not exist — that is `GT-OUTBOX-SERVICEMAP` in §4, not
# something to fake here.
#
# The XADD leg had **12 exclusion rows and no shrink arm**, and no reach floor:
# a renamed `services/` produced no hits and `PASS` in the same bytes as
# compliance (`BDR-82`).

set -euo pipefail

SELF="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"

# Sanctioned XADD sites. Each row must match at least one real call — the shrink
# arm below says so — because an exclusion that excuses nothing is a standing
# waiver for whatever appears under that path next.
#
#   publisher                     the outbox→Redis publisher itself
#   worker-infra outbox_relay     the existing novel-platform relay
#   meta-outbox-relay             P2/101 Option B, the meta-context drain
#   incident-bot redis_emitter    P2/108, GDPR Art.33 breach lifecycle
#   knowledge/chat/lore-enrich    AI-track services on their OWN service streams
#   provider-registry usage_relay S4b, the usage-stream relay
#   composition worker/events.py  the composition_jobs job-trigger stream
#   meta-worker metaworker-bench  a load bench, not a service
EXCLUDE_PATHS=(
  "services/publisher/"
  "services/worker-infra/internal/tasks/outbox_relay.go"
  "services/meta-outbox-relay/"
  "services/incident-bot/internal/breach/redis_emitter.go"
  "services/knowledge-service/"
  "services/chat-service/"
  "services/provider-registry-service/internal/jobs/usage_relay.go"
  "services/lore-enrichment-service/"
  "services/composition-service/app/worker/events.py"
  "services/meta-worker/cmd/metaworker-bench/"
)

XADD_RE='(\b[a-zA-Z_]+\.XAdd\(|\bredis\.xadd\(|\bclient\.xadd\(|\br\.xadd\()'

# Foreign trees. Without this the walk counted 16457 files, most of them vendored
# `node_modules` TypeScript — the `GTD-8` shape, third occurrence: judging other
# people's packages by this repo's outbox invariant.
EXCLUDE_DIRS=(node_modules target .venv venv site-packages vendor __pycache__
              dist build coverage .next)
grep_excludes() { local d; for d in "${EXCLUDE_DIRS[@]}"; do printf -- '--exclude-dir=%s\n' "$d"; done; }
find_prune() {
    local first=1 d
    printf '(\n'
    for d in "${EXCLUDE_DIRS[@]}"; do
        [[ $first -eq 1 ]] || printf -- '-o\n'
        printf -- '-name\n%s\n' "$d"; first=0
    done
    printf ')\n-prune\n-o\n'
}
ALLOWLIST_REL="contracts/meta/events_allowlist.yaml"

# run_lint <tree_root> [exclude-path...]
run_lint() {
    local root="$1"; shift
    local excludes=("$@")
    [[ ${#excludes[@]} -eq 0 ]] && excludes=("${EXCLUDE_PATHS[@]}")
    local violations=0

    local roots=("$root/services" "$root/contracts" "$root/crates")

    # ── REACH FLOOR (GT-F3).
    local n_src=0 d
    mapfile -t _prune < <(find_prune)
    for d in "${roots[@]}"; do
        [[ -d "$d" ]] || continue
        n_src=$(( n_src + $( { find "$d" "${_prune[@]}" -type f \( -name '*.go' \
                  -o -name '*.rs' -o -name '*.ts' -o -name '*.py' \) -print 2>/dev/null \
                  || true; } | wc -l ) ))
    done
    if [[ "$n_src" -eq 0 ]]; then
        echo "[outbox-emit] ERROR — 0 source file(s) under services/, contracts/, crates/." >&2
        echo "  A walk that reached nothing is not a clean tree (BDR-82)." >&2
        return 2
    fi

    # ── RULE 1 · direct XADD outside the sanctioned sites.
    local raw
    mapfile -t _gx < <(grep_excludes)
    raw=$(grep -rnE "$XADD_RE" \
        --include='*.go' --include='*.rs' --include='*.ts' --include='*.py' \
        "${_gx[@]}" "${roots[@]}" 2>/dev/null \
        | sed "s#^$root/##" \
        | grep -vE '_test\.go|_test\.rs|_test\.py|test_.*\.py' \
        | grep -vE ':[[:space:]]*(//|#|"""|\*|///)' || true)

    local hits="$raw" p
    for p in "${excludes[@]}"; do
        [[ -z "$p" ]] && continue
        hits="$(printf '%s\n' "$hits" | grep -vF "$p" || true)"
    done

    if [[ -n "$hits" ]]; then
        echo "[outbox-emit] FAIL — direct Redis XADD outside services/publisher (I13):"
        echo "$hits" | sed 's/^/  /'
        violations=$((violations + 1))
    fi

    # ── SHRINK ARM (GT-F5). A sanctioned path that excuses no actual call today
    # is either renamed or finished, and either way it silently re-sanctions that
    # path the day something appears under it.
    for p in "${excludes[@]}"; do
        [[ -z "$p" ]] && continue
        if ! printf '%s\n' "$raw" | grep -qF "$p"; then
            echo "[outbox-emit] FAIL — sanctioned path '$p' excuses no XADD call in this tree."
            echo "  Delete the row, or fix the path; an exemption for nothing is a waiver in waiting."
            violations=$((violations + 1))
        fi
    done

    # ── RULE 2 · events_allowlist.yaml integrity (the leg the header promised).
    local allowlist="$root/$ALLOWLIST_REL"
    # NOT independent detection — the checker below returns 2 on an unreadable
    # path anyway, so this only improves the message. A bite arm disabling it
    # came back green, on the sibling. Diagnostics, not a rule.
    if [[ ! -f "$allowlist" ]]; then
        echo "[outbox-emit] ERROR — $ALLOWLIST_REL is missing; rule 2 has no subject." >&2
        return 2
    fi
    local al_out al_rc
    set +e
    al_out="$(python3 "$SELF.allowlist.py" "$allowlist" "$root" 2>&1)"
    al_rc=$?
    set -e
    if [[ "$al_rc" -eq 2 ]]; then
        echo "[outbox-emit] ERROR — allowlist check could not run:" >&2
        printf '%s\n' "$al_out" >&2
        return 2
    fi
    if [[ "$al_rc" -ne 0 ]]; then
        printf '%s\n' "$al_out"
        violations=$((violations + 1))
    else
        printf '%s\n' "$al_out"
    fi

    if [[ $violations -gt 0 ]]; then
        echo "[outbox-emit] FAIL — $violations violation(s) (I13)"
        return 1
    fi
    local n_raw=0
    [[ -n "$raw" ]] && n_raw="$(printf '%s\n' "$raw" | wc -l | tr -d ' ')"
    echo "[outbox-emit] PASS — ${n_src} source file(s) scanned, ${n_raw} XADD call(s) found," \
         "all under the ${#excludes[@]} sanctioned path(s)"
    return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
ALLOWLIST_FIXTURE='version: 1
entries:
  - table: reality_registry
    owner: world-service
    events:
      - op: INSERT
        event_name: reality.created
'

seed_tree() {
    local d="$1"
    mkdir -p "$d/services/publisher" "$d/services/svc" "$d/crates/k/src" \
             "$d/contracts/x" "$d/contracts/meta" "$d/migrations/meta"
    printf 'package main\nfunc main(){}\n'   > "$d/services/svc/main.go"
    printf 'pub fn ok() {}\n'                > "$d/crates/k/src/lib.rs"
    printf 'package x\n'                     > "$d/contracts/x/y.go"
    # the one sanctioned path this fixture keeps alive
    printf 'package publisher\nfunc P(){ rdb.XAdd(args) }\n' > "$d/services/publisher/p.go"
    printf 'CREATE TABLE reality_registry (id UUID);\n' > "$d/migrations/meta/001_reality_registry.up.sql"
    printf '%s' "$ALLOWLIST_FIXTURE" > "$d/contracts/meta/events_allowlist.yaml"
}

selftest() {
    local failures=0

    # probe <name> <want-rc> <setup-fn>
    probe() {
        local name="$1" want="$2" setup="$3"
        local d got
        d="$(mktemp -d)"
        seed_tree "$d"
        "$setup" "$d"
        set +e
        ( run_lint "$d" "services/publisher/" ) >/dev/null 2>&1
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

    s_none()      { :; }
    s_go_xadd()   { printf 'package a\nfunc f(){ rdb.XAdd(args) }\n' > "$1/services/svc/bad.go"; }
    s_py_xadd()   { printf 'r.xadd("s", {})\n'                      > "$1/services/svc/bad.py"; }
    s_client()    { printf 'client.xadd("s", {})\n'                 > "$1/services/svc/bad.py"; }
    s_in_test()   { printf 'package a\nfunc f(){ rdb.XAdd(args) }\n' > "$1/services/svc/bad_test.go"; }
    s_in_comment(){ printf 'package a\n// rdb.XAdd(args)\n'          > "$1/services/svc/ok.go"; }
    s_vendored()  { mkdir -p "$1/services/svc/node_modules/pkg"
                    printf 'r.xadd("s", {})\n' > "$1/services/svc/node_modules/pkg/x.py"; }
    s_no_src()    { rm -rf "$1/services" "$1/crates"; rm -f "$1/contracts/x/y.go"; }
    s_pub_gone()  { rm -f "$1/services/publisher/p.go"; }
    s_al_gone()   { rm -f "$1/contracts/meta/events_allowlist.yaml"; }
    s_al_badtbl() { printf '%s' "${ALLOWLIST_FIXTURE/reality_registry/ghost_table}" \
                        > "$1/contracts/meta/events_allowlist.yaml"; }
    s_al_badop()  { printf '%s' "${ALLOWLIST_FIXTURE/op: INSERT/op: UPSERT}" \
                        > "$1/contracts/meta/events_allowlist.yaml"; }
    s_al_dupev()  { printf '%sentries2: []\n' "${ALLOWLIST_FIXTURE}  - table: reality_registry2
    owner: x
    events:
      - op: INSERT
        event_name: reality.created
" > "$1/contracts/meta/events_allowlist.yaml"
                    printf 'CREATE TABLE reality_registry2 (id UUID);\n' \
                        >> "$1/migrations/meta/001_reality_registry.up.sql"; }
    s_al_broken() { printf 'entries: [oops\n' > "$1/contracts/meta/events_allowlist.yaml"; }
    # a VALID yaml with an EMPTY entries list — permits nothing while satisfying
    # every downstream rule, which is the vacuous pass the guard exists for
    s_al_empty()  { printf 'version: 1\nentries: []\n' > "$1/contracts/meta/events_allowlist.yaml"; }
    # migrations gone: the table check would compare every name against an empty
    # set. That is not a violation, it is an inability to check (GTD-9)
    s_no_migs()   { rm -rf "$1/migrations"; }

    echo "outbox-event-emit-lint --self-test"

    probe "a clean tree passes" 0 s_none

    # RULE 1
    probe "a Go .XAdd( outside the sanctioned paths fails" 1 s_go_xadd
    probe "a python r.xadd( fails" 1 s_py_xadd
    probe "a python client.xadd( fails" 1 s_client
    probe "...but one in a _test.go does not" 0 s_in_test
    probe "...nor one in a comment" 0 s_in_comment
    probe "...nor one in a vendored node_modules package" 0 s_vendored

    # the shrink arm
    probe "a sanctioned path that excuses nothing fails" 1 s_pub_gone

    # RULE 2 — the leg the header promised and never had
    probe "an allowlist table with no migration fails" 1 s_al_badtbl
    probe "an allowlist op outside INSERT/UPDATE/DELETE fails" 1 s_al_badop
    probe "a duplicate event_name fails" 1 s_al_dupev
    probe "a MISSING allowlist is misuse, not a pass" 2 s_al_gone
    probe "an unparseable allowlist is misuse, not a pass" 2 s_al_broken
    probe "an EMPTY allowlist is misuse, not a pass" 2 s_al_empty
    probe "zero declared tables is misuse, not a violation" 2 s_no_migs

    # reach floor
    probe "no source files at all is misuse, not a pass" 2 s_no_src

    if [[ $failures -gt 0 ]]; then
        echo "outbox-event-emit-lint --self-test: $failures rule(s) did not behave"
        return 2
    fi
    echo "outbox-event-emit-lint --self-test: every rule bites, and none cries wolf"
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
