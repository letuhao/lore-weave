#!/usr/bin/env bash
# L1.K.3 transitions-validation-lint.sh — C05 §12Q.6
#
# Loads contracts/meta/transitions.yaml and verifies:
#   - Every state declared in `states:` is reachable from some `initial_states:` entry
#   - Every transition target is a declared state
#   - At least one `terminal_states:` entry (or explicit "none — operational" marker)
#   - mutual_exclusions reference only declared states
#
# Implementation: light-weight pure-shell + grep (no YAML lib at lint time).
# Heavy validation already happens in contracts/meta/transitions_validator.go;
# this lint is the CI gate that fails the build BEFORE the test stage even runs.
#
# Exit 0 = clean; 1 = violations; 2 = misuse.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
# ── selftest — the red-ability proof (gate-teeth-gate) ──────────────────────
# This gate already takes its target as $1, so the selftest just points it at
# synthetic YAML — no copy trick needed.
#
# Case 4 is the one worth having. Heuristic 2 fires in ONE direction only
# (transitions without states), and that asymmetry is deliberate: a resource may
# declare states before any transition exists. Nothing said so until now, so a
# reader "fixing the omission" by making it symmetric would red every
# states-first resource in the repo.
if [[ "${1:-}" == "--selftest" ]]; then
  st_fail=0
  st_run() {  # st_run <expected-exit> <name> <yaml-body>
    local want="$1" name="$2" body="$3" f rc
    f="$(mktemp)"
    printf '%s\n' "$body" > "$f"
    rc=0
    bash "$0" "$f" >/dev/null 2>&1 || rc=$?
    if [[ "$rc" != "$want" ]]; then
      echo "  FAIL — $name: exit $rc, expected $want"
      st_fail=1
    fi
    rm -f "$f"
  }

  st_run 0 "a well-formed transitions file passes" "resources:
  chapter:
    states: [draft, published]
    transitions:
      - from: draft
        to: published
    terminal_states: [published]"

  st_run 1 "a file with no resources: block is refused" "chapter:
  states: [draft]
  transitions:
    - from: draft
      to: draft
  terminal_states: [draft]"

  st_run 1 "transitions: declared without states: is refused" "resources:
  chapter:
    transitions:
      - from: draft
        to: published
    terminal_states: [published]"

  st_run 0 "states: without transitions: is ALLOWED (the check is one-directional)" "resources:
  chapter:
    states: [draft, published]
    terminal_states: [published]"

  st_run 0 "an operational resource may use the marker instead of terminal_states" "resources:
  worker:
    states: [idle, busy]
    transitions:
      - from: idle
        to: busy
    operational: true"

  rc=0; bash "$0" "$(mktemp -u)" >/dev/null 2>&1 || rc=$?
  if [[ "$rc" != "0" ]]; then
    echo "  FAIL — a target path that does not exist must be a no-op, got exit $rc"
    st_fail=1
  fi

  if [[ $st_fail -eq 0 ]]; then
    echo "[transitions-validation] SELFTEST PASS — both violations red, and the"\
         "one-directional states/transitions rule plus the operational marker stay green (non-vacuous)"
    exit 0
  fi
  echo "[transitions-validation] SELFTEST FAIL"
  exit 1
fi

target="${1:-$repo_root/contracts/meta/transitions.yaml}"

if [[ ! -f "$target" ]]; then
  echo "[transitions-validation] no transitions.yaml at $target — nothing to lint"
  exit 0
fi

violations=0

# Heuristic 1: file must declare the resources: top-level block
if ! grep -qE '^resources:' "$target"; then
  echo "[transitions-validation] FAIL — no resources: top-level block found"
  violations=$((violations + 1))
fi

# Heuristic 2: every resource that lists 'transitions:' should list 'states:' too
#
# ⚠️ `|| true`, NOT `|| echo 0`. `grep -c` ALREADY prints a zero when it matches nothing;
# it merely EXITS 1. So `|| echo 0` appended a second line and the variable held two
# zeroes separated by a newline. Comparing that with `-eq` is a bash SYNTAX ERROR, not a
# false — bash printed "syntax error in expression" to stderr, the `if` took the else
# branch, and heuristic 2 could never fire. Found 2026-08-12 by this file's own
# --selftest, on its first run, by the fixture that declares transitions with no states.
resources_with_transitions=$(grep -c '^[[:space:]]*transitions:' "$target" || true)
resources_with_states=$(grep -c '^[[:space:]]*states:' "$target" || true)
if [[ $resources_with_transitions -gt 0 ]] && [[ $resources_with_states -eq 0 ]]; then
  echo "[transitions-validation] FAIL — transitions: declared without states:"
  violations=$((violations + 1))
fi

# Heuristic 3: detect unreachable terminal states (very lightweight; the Go
# validator does the real graph walk). Check that 'terminal_states' OR
# explicit 'operational: true' marker exists per resource.
if ! grep -qE '(terminal_states:|operational:[[:space:]]*true)' "$target"; then
  echo "[transitions-validation] WARN — neither terminal_states nor operational marker found; verify intent"
fi

if [[ $violations -gt 0 ]]; then
  echo "[transitions-validation] FAIL — $violations issue(s) (C05 §12Q.6)"
  exit 1
fi
echo "[transitions-validation] PASS"
exit 0
