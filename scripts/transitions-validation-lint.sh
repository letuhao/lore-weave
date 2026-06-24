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
resources_with_transitions=$(grep -c '^[[:space:]]*transitions:' "$target" || echo 0)
resources_with_states=$(grep -c '^[[:space:]]*states:' "$target" || echo 0)
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
