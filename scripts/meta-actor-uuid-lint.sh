#!/usr/bin/env bash
# meta-actor-uuid-lint.sh — W3.3 regression guard (mock fidelity).
#
# The lifecycle_transition_audit / reality_close_audit / admin_action_audit
# columns are `actor_id UUID NOT NULL` (migrations/meta/004,005,015). A test
# fixture whose Actor flows to those tables MUST carry a UUID — a service-name
# string like "world-service" would FAIL the ::uuid insert at runtime. That is
# the exact gap the live I9 metaprobe caught (D-META-FAKEDB-UUID-ACTOR); this
# lint is the cheap regression catch so a future string literal trips CI rather
# than only surfacing on a live stack-up.
#
# SCOPE — only the UUID-column-bound fixtures (contracts/meta/lifecycle_test.go).
# The metawrite / audit_l1a3 / fallback fixtures bind to meta_write_audit /
# meta_read_audit, whose actor_id is `TEXT` and where the actor.go contract is
# "service name for system actors" — there "world-service" is the FAITHFUL value,
# NOT a defect, so those files are deliberately out of scope. A blanket "all
# actor_id literals must be UUIDs" check would false-positive on every faithful
# metawrite fixture.
#
# Exit 0 = clean; 1 = a non-UUID quoted actor literal in a UUID-bound fixture;
# 2 = misuse / self-test failure.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
UUID_RE='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

# UUID-column-bound fixture files (Actor flows to a UUID actor_id column).
TARGETS=("contracts/meta/lifecycle_test.go")

# check_file FILE — prints "FILE:LINENO  <literal>" for every Actor{...} literal
# whose QUOTED ID is not a UUID. Const refs (ID: fxOwnerActorID — no quote) and
# UUID-shaped literals are clean. Returns 0 always; caller counts printed lines.
check_file() {
  local file="$1"
  # Lines where an Actor{...} literal carries a QUOTED id after `ID:`.
  # `|| true` so a no-match grep (exit 1) doesn't trip the caller's set -e.
  grep -nE 'Actor\{[^}]*ID:[[:space:]]*"[^"]*"' "$file" 2>/dev/null | while IFS= read -r line; do
    local lineno val
    lineno="${line%%:*}"
    val="$(printf '%s' "$line" | sed -E 's/.*Actor\{[^}]*ID:[[:space:]]*"([^"]*)".*/\1/')"
    if [[ ! "$val" =~ $UUID_RE ]]; then
      printf '%s:%s  %s\n' "$file" "$lineno" "$val"
    fi
  done || true
  return 0
}

run_lint() {
  local violations=0 t out
  for t in "${TARGETS[@]}"; do
    [[ -f "$repo_root/$t" ]] || { echo "[meta-actor-uuid] WARN target missing: $t"; continue; }
    out="$(check_file "$repo_root/$t")"
    if [[ -n "$out" ]]; then
      echo "[meta-actor-uuid] FAIL — non-UUID actor literal in a UUID-column-bound fixture:"
      echo "$out" | sed 's/^/  /'
      echo "  → use a UUID (e.g. the fxOwnerActorID / fxSystemActorID consts in fakes_test.go);"
      echo "    a service-name string fails the actor_id UUID column at runtime."
      violations=$((violations + 1))
    fi
  done
  if [[ $violations -gt 0 ]]; then exit 1; fi
  echo "[meta-actor-uuid] PASS — all UUID-bound actor fixtures carry UUIDs"
}

# --selftest is the non-vacuity BITE: feed the checker a known-bad and a
# known-good snippet and assert it flags the bad and passes the good. If the
# checker has gone vacuous (e.g. regex broke), this fails the build.
selftest() {
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  cat > "$tmp/bad.go" <<'EOF'
Actor: Actor{Type: ActorSystem, ID: "world-service"},
EOF
  cat > "$tmp/good.go" <<'EOF'
Actor: Actor{Type: ActorSystem, ID: "00000000-0000-0000-0000-0000000000a1"},
Actor: Actor{Type: ActorOwner, ID: fxOwnerActorID},
EOF
  local bad good
  bad="$(check_file "$tmp/bad.go")"
  good="$(check_file "$tmp/good.go")"
  if [[ -z "$bad" ]]; then
    echo "[meta-actor-uuid] SELFTEST FAIL — checker did NOT flag a non-UUID actor literal (vacuous)"; exit 2
  fi
  if [[ -n "$good" ]]; then
    echo "[meta-actor-uuid] SELFTEST FAIL — checker flagged a valid UUID/const fixture: $good"; exit 2
  fi
  echo "[meta-actor-uuid] SELFTEST PASS — flags non-UUID literal, passes UUID + const (non-vacuous)"
}

# Default (and the CI invocation) runs the BITE first, then the real lint — so a
# green CI run always proves the checker is non-vacuous before trusting its PASS.
case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
