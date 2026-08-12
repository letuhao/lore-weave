#!/usr/bin/env bash
# L4.N dependency-registry-lint.sh — SR06 §12AI.2
#
# Every outbound dependency client (HTTP/DB/Redis) MUST be constructed
# via contracts/dependencies/ClientFactory. Raw http.Client{}, sql.Open,
# redis.NewClient calls outside the factory bypass the matrix.yaml
# governance and are blocked by this lint.
#
# The contracts/resilience/ + contracts/dependencies/ packages themselves
# are exempt (they ARE the factory). The factory in turn produces
# WrappedClientConfig which service code consumes.
#
# Heuristic — may produce false positives in tests; *_test.go is allowlisted.
#
# Cycle 18 ships this lint in WARN mode (exit 0) because services have
# not yet been refactored to route through the factory. Cycle 19+ flips
# to ERROR mode once all consumers are migrated. The flip is tracked as
# DEFERRED 082 (D-PUBLISHER-DEP-REGISTRY). Mode is NOT changed here.
#
# Exit 0 = clean OR warn-mode active; 1 = violations + error-mode active;
#          2 = misuse / selftest failure / the scan reached nothing.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12). This gate had none, and it is
# the case that most needed one: in its DEFAULT mode it prints violations and
# exits 0, so "it passed" and "it found 49 problems" are the same observable.
# A gate that is disarmed by default can still be proven to BITE — the mode is
# a policy decision (DEFERRED 082), the predicate is a rule, and it is the rule
# this proves.
#
# **It also reported the wrong number for months.** `violations` was incremented
# once per GREP BLOCK, so two categories reported "2 raw client construction(s)"
# against a real 49. Anyone reading that line would think the migration was two
# call-sites from done. Now counted per hit.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
mode="${DEPENDENCY_REGISTRY_LINT_MODE:-warn}"   # warn | error

# PREDICATE 1 — the forbidden Go shapes, in a blob of text.
go_shape() {
  printf '%s' "$1" | grep -E '\b(http\.Client\{|http\.NewRequest\b|sql\.Open\b|redis\.NewClient\b)'
}

# PREDICATE 2 — the forbidden Rust shapes.
rs_shape() {
  printf '%s' "$1" | grep -E '\b(reqwest::Client::new\b|sqlx::PgPool::connect\b)'
}

# PREDICATE 3 — paths that are exempt BY DESIGN (the factory itself, and tests).
# Extracted because an exemption is a rule too: widen it by accident and the
# gate goes quiet without anyone deleting a check.
go_exempt() {
  printf '%s' "$1" | grep -qE '_test\.go:|contracts/(resilience|dependencies)/'
}
rs_exempt() {
  printf '%s' "$1" | grep -qE 'mod tests|/tests/|_test\.rs:|crates/dp-kernel/'
}

run_lint() {
  local go_files rs_files go_hits rs_hits total=0

  # REACH FLOOR. This gate hunts for a shape; finding none is the GOAL state, so
  # "no hits" can never be evidence the scan worked. The only honest floor is on
  # what it walked — and a walk that reaches nothing is byte-identical to a clean
  # tree, exit code included (`BDR-82`).
  # `|| true` INSIDE the braces, and it is load-bearing. Under `set -euo
  # pipefail` a `find` on a missing directory fails, the command substitution
  # fails with it, and the script dies at THIS LINE with rc=1 — before the floor
  # below can say anything. Measured by the bite: pointing the walk at a
  # directory that does not exist produced a silent rc=1, so the floor was
  # unreachable in precisely the case it exists for.
  go_files=$( { find "$repo_root/services" -name '*.go' 2>/dev/null || true; } | wc -l)
  rs_files=$( { find "$repo_root/services" "$repo_root/crates" -name '*.rs' 2>/dev/null || true; } | wc -l)
  if [[ "$go_files" -lt 1 || "$rs_files" -lt 1 ]]; then
    echo "[dependency-registry] FAIL — the scan reached $go_files .go and $rs_files .rs file(s);"
    echo "                      a walk that reaches nothing looks exactly like a clean tree"
    exit 2
  fi

  go_hits=$(grep -rnE '\b(http\.Client\{|http\.NewRequest\b|sql\.Open\b|redis\.NewClient\b)' \
    --include='*.go' "$repo_root/services" 2>/dev/null \
    | grep -vE '_test\.go:' \
    | grep -vE 'contracts/(resilience|dependencies)/' \
    || true)
  if [[ -n "$go_hits" ]]; then
    echo "[dependency-registry] raw client constructors outside ClientFactory:"
    echo "$go_hits" | sed 's/^/  /'
    total=$((total + $(printf '%s\n' "$go_hits" | wc -l)))
  fi

  rs_hits=$(grep -rnE '\b(reqwest::Client::new\b|sqlx::PgPool::connect\b)' \
    --include='*.rs' "$repo_root/services" "$repo_root/crates" 2>/dev/null \
    | grep -vE 'mod tests' \
    | grep -vE '/tests/' \
    | grep -vE '_test\.rs:' \
    | grep -vE 'crates/dp-kernel/' \
    || true)
  if [[ -n "$rs_hits" ]]; then
    echo "[dependency-registry] raw Rust client constructors outside ClientFactory:"
    echo "$rs_hits" | sed 's/^/  /'
    total=$((total + $(printf '%s\n' "$rs_hits" | wc -l)))
  fi

  if [[ $total -gt 0 ]]; then
    if [[ "$mode" == "error" ]]; then
      echo "[dependency-registry] FAIL — $total raw client construction(s) (SR06 §12AI.2)"
      exit 1
    fi
    echo "[dependency-registry] WARN — $total raw client construction(s) across $go_files .go + $rs_files .rs file(s)"
    echo "                      (cycle-18 warn-mode; the flip to error-mode is DEFERRED 082)"
    exit 0
  fi
  echo "[dependency-registry] PASS — $go_files .go + $rs_files .rs file(s) scanned, no raw constructors"
  exit 0
}

selftest() {
  # Shape detection, both directions, one case per alternative — because
  # blanking a whole alternation reds on the first case and certifies nothing
  # about the rest.
  local s
  for s in 'c := http.Client{}' 'req, _ := http.NewRequest("GET", u, nil)' \
           'db, _ := sql.Open("postgres", dsn)' 'r := redis.NewClient(&redis.Options{})'; do
    if [[ -z "$(go_shape "$s" || true)" ]]; then
      echo "[dependency-registry] SELFTEST FAIL — Go shape not detected: $s"; exit 2
    fi
  done
  if [[ -n "$(go_shape 'client := factory.For("auth").HTTP()' || true)" ]]; then
    echo "[dependency-registry] SELFTEST FAIL — flagged a factory-routed Go client (cry-wolf)"; exit 2
  fi

  for s in 'let c = reqwest::Client::new();' 'let p = sqlx::PgPool::connect(&dsn).await?;'; do
    if [[ -z "$(rs_shape "$s" || true)" ]]; then
      echo "[dependency-registry] SELFTEST FAIL — Rust shape not detected: $s"; exit 2
    fi
  done
  if [[ -n "$(rs_shape 'let c = factory.http_client();' || true)" ]]; then
    echo "[dependency-registry] SELFTEST FAIL — flagged a factory-routed Rust client (cry-wolf)"; exit 2
  fi

  # The EXEMPTIONS are rules too. Widen one by accident and the gate goes quiet
  # with no check deleted — the shape this repo calls an adjacent decision
  # defeating a guard.
  if ! go_exempt 'services/x/foo_test.go:12: http.Client{}'; then
    echo "[dependency-registry] SELFTEST FAIL — a *_test.go path is not exempt"; exit 2
  fi
  if ! go_exempt 'contracts/dependencies/factory.go:9: http.Client{}'; then
    echo "[dependency-registry] SELFTEST FAIL — the factory itself is not exempt"; exit 2
  fi
  if go_exempt 'services/x/main.go:12: http.Client{}'; then
    echo "[dependency-registry] SELFTEST FAIL — ordinary service code is being EXEMPTED (vacuous)"; exit 2
  fi
  if ! rs_exempt 'crates/dp-kernel/src/x.rs:3: reqwest::Client::new()'; then
    echo "[dependency-registry] SELFTEST FAIL — dp-kernel is not exempt"; exit 2
  fi
  if rs_exempt 'services/world-service/src/state.rs:33: reqwest::Client::new()'; then
    echo "[dependency-registry] SELFTEST FAIL — ordinary Rust service code is being EXEMPTED (vacuous)"; exit 2
  fi

  echo "[dependency-registry] SELFTEST PASS — all 4 Go and 2 Rust shapes detected, factory-routed"
  echo "                      code not flagged, and the four exemptions cover what they claim"
  echo "                      without swallowing ordinary service code (non-vacuous both ways)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
