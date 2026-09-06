#!/usr/bin/env bash
# L1.K.3 transitions-validation-lint.sh — C05 §12Q.6
#
# Loads contracts/meta/transitions.yaml and verifies:
#   - the `resources:` top-level block exists
#   - no resource declares `transitions:` without `states:`
#   - a terminal marker (`terminal_states:` or `operational: true`) is present
#
# Implementation: light-weight pure-shell + grep (no YAML lib at lint time).
# Heavy validation already happens in contracts/meta/transitions_validator.go;
# this lint is the CI gate that fails the build BEFORE the test stage even runs.
#
# Exit 0 = clean; 1 = violations; 2 = misuse / selftest failure / no subject.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12).
#
# ⚠️ **A MISSING SUBJECT USED TO BE A PASS.** The first thing this gate did was
#     if [[ ! -f "$target" ]]; then echo "nothing to lint"; exit 0; fi
# so renaming or moving `contracts/meta/transitions.yaml` would have turned it
# green forever, silently, with a cheerful message. The file exists today, which
# is the only reason that never bit — the gate was one `git mv` from being
# permanently vacuous. A subject that has vanished is a finding, not a pass; it
# now exits 2 and says which path it looked at.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# --- PREDICATES over the FILE TEXT, so cases can drive them -----------------

has_resources_block() {
  printf '%s' "$1" | grep -qE '^resources:'
}

# transitions: declared with no states: anywhere.
transitions_without_states() {
  local t="$1" n_tr n_st
  n_tr=$(printf '%s' "$t" | grep -c '^[[:space:]]*transitions:' || true)
  n_st=$(printf '%s' "$t" | grep -c '^[[:space:]]*states:' || true)
  [[ "$n_tr" -gt 0 && "$n_st" -eq 0 ]]
}

has_terminal_marker() {
  printf '%s' "$1" | grep -qE '(terminal_states:|operational:[[:space:]]*true)'
}

run_lint() {
  local target="${1:-$repo_root/contracts/meta/transitions.yaml}"
  local violations=0 text lines

  # A subject that is not there is a FINDING. See the header: this used to be
  # `exit 0`, which made the gate one rename away from permanently green.
  if [[ ! -f "$target" ]]; then
    echo "[transitions-validation] FAIL — no transitions.yaml at $target."
    echo "  This gate has no subject, which is not the same as having nothing to report."
    exit 2
  fi

  text="$(cat "$target")"
  lines=$(printf '%s\n' "$text" | grep -c . || true)

  # REACH FLOOR: an empty (or truncated-to-nothing) contract parses cleanly
  # against all three heuristics below and prints PASS.
  if [[ "$lines" -lt 2 ]]; then
    echo "[transitions-validation] FAIL — $target holds $lines non-blank line(s);"
    echo "  every heuristic below is trivially satisfied by an empty file"
    exit 2
  fi

  if ! has_resources_block "$text"; then
    echo "[transitions-validation] FAIL — no resources: top-level block found"
    violations=$((violations + 1))
  fi

  if transitions_without_states "$text"; then
    echo "[transitions-validation] FAIL — transitions: declared without states:"
    violations=$((violations + 1))
  fi

  # Lightweight; the Go validator does the real graph walk.
  if ! has_terminal_marker "$text"; then
    echo "[transitions-validation] WARN — neither terminal_states nor operational marker found; verify intent"
  fi

  if [[ $violations -gt 0 ]]; then
    echo "[transitions-validation] FAIL — $violations issue(s) (C05 §12Q.6)"
    exit 1
  fi
  echo "[transitions-validation] PASS — $lines line(s) checked in $(basename "$target")"
  exit 0
}

_probe() {  # $1 = yaml text (empty string = do not create the file)
  local f rc=0 d
  d="$(mktemp -d)"; f="$d/transitions.yaml"
  [[ -n "$1" ]] && printf '%s' "$1" > "$f"
  ( run_lint "$f" ) >/dev/null 2>&1 || rc=$?
  rm -rf "$d"
  printf '%s' "$rc"
}

selftest() {
  local rc
  local good=$'resources:\n  reality:\n    states: [active, frozen]\n    transitions:\n      - from: active\n        to: frozen\n    terminal_states: [frozen]\n'

  has_resources_block "$good" || { echo "[transitions-validation] SELFTEST FAIL — resources: block not detected"; exit 2; }
  if has_resources_block $'  resources:\n'; then
    echo "[transitions-validation] SELFTEST FAIL — an INDENTED resources: key counted as the top-level block"; exit 2
  fi

  if ! transitions_without_states $'resources:\n  x:\n    transitions:\n      - a\n'; then
    echo "[transitions-validation] SELFTEST FAIL — transitions: without states: not caught (vacuous)"; exit 2
  fi
  if transitions_without_states "$good"; then
    echo "[transitions-validation] SELFTEST FAIL — a resource WITH states: was reported (cry-wolf)"; exit 2
  fi

  has_terminal_marker "$good" || { echo "[transitions-validation] SELFTEST FAIL — terminal_states: not detected"; exit 2; }
  has_terminal_marker $'resources:\n  x:\n    operational: true\n' \
    || { echo "[transitions-validation] SELFTEST FAIL — the operational: true marker not detected"; exit 2; }
  if has_terminal_marker $'resources:\n  x:\n    states: [a]\n'; then
    echo "[transitions-validation] SELFTEST FAIL — a contract with NEITHER marker was accepted"; exit 2
  fi

  # END TO END through the real run_lint.
  rc=$(_probe "$good")
  [[ "$rc" == "0" ]] || { echo "[transitions-validation] SELFTEST FAIL — a valid contract did not pass (rc=$rc)"; exit 2; }

  rc=$(_probe $'other:\n  x:\n    transitions:\n      - a\n    states: [a]\n')
  [[ "$rc" == "1" ]] || { echo "[transitions-validation] SELFTEST FAIL — a contract with no resources: block did not fail (rc=$rc)"; exit 2; }

  # THE TWO REACH CASES, which are the reason this gate was worth touching.
  rc=$(_probe "")
  [[ "$rc" == "2" ]] || { echo "[transitions-validation] SELFTEST FAIL — a MISSING contract file did not fail (rc=$rc);"; echo "  the gate is one rename away from permanently green"; exit 2; }

  rc=$(_probe $'\n')
  [[ "$rc" == "2" ]] || { echo "[transitions-validation] SELFTEST FAIL — an EMPTY contract satisfied every heuristic and passed (rc=$rc)"; exit 2; }

  echo "[transitions-validation] SELFTEST PASS — all three heuristics bite and none cries wolf;"
  echo "  end-to-end a valid contract passes and a resources-less one fails; and the two ways"
  echo "  to have no subject — a MISSING file and an EMPTY one — are both refused rather than"
  echo "  reported as nothing to lint"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint "${2:-}" ;;
  "")         selftest; run_lint ;;
  *)          run_lint "$1" ;;   # back-compat: a bare argument is the target path
esac
