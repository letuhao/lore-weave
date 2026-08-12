#!/usr/bin/env bash
# admin-command-registry-lint.sh — R13 §12L.5 CI gate.
#
# Blocks ad-hoc SQL or HTTP admin endpoints that sit OUTSIDE the
# contracts/admin/registry framework. Every admin-class action MUST be
# declared in a registry/*.yaml so it gets:
#   * audited via admin_action_audit (framework hook)
#   * tier-classified for dry-run + double-approval gating
#   * surfaced in `admin --help` for SRE discoverability
#
# Heuristic (V1):
#   * grep services/ for `// ADMIN-SQL:` or `// ADMIN-RPC:` markers — these
#     MUST appear in contracts/admin/registry/*.yaml as command handlers.
#   * grep services/ for `func (h *AdminHandler) ` style admin route
#     handlers — every such handler name MUST be referenced as a `handler:`
#     in some registry yaml file.
#
# Soft heuristic — false positives are possible. Add `// admin-registry-lint:exempt`
# next to the offending line to suppress.
#
# Exit codes:
#   0  pass
#   1  one or more admin-class entry points outside the registry
#   2  CLI usage error / selftest failure
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12) — and read the next paragraph
# before trusting a green from this gate.
#
# ⚠️ **MEASURED 2026-08-12: THIS GATE HAS ZERO SUBJECTS.** `// ADMIN-SQL:` and
# `// ADMIN-RPC:` occur **0** times across all of `services/`, and
# `func (… *AdminHandler)` occurs **0** times. Both scans walk the tree and
# match nothing, so the line it prints — *"no orphan ADMIN-SQL/RPC markers"* —
# is true the way "no unicorns escaped" is true. The convention it polices is
# not one this repo writes; the real admin surface is the 10 registry YAMLs and
# the Go dispatcher. Tracked as `GT-ADMIN-NO-SUBJECT`.
#
# That is a COVERAGE finding, and it is deliberately NOT resolved by making the
# gate red: zero markers is the true state of the tree, and a gate that fails on
# the truth is cry-wolf. What `--selftest` proves is the other thing — that the
# rule BITES when a subject exists. Both facts are now visible instead of one
# being implied by the other.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

REG_DIR="contracts/admin/registry"

# Build/vendor trees are excluded from BOTH scans below. An admin marker is a thing an author
# wrote in this repo's source; it is never inside a dependency or a compiler output, so this
# narrows nothing real. It is a LATENCY fix, and the latency was not cosmetic: the two bare
# `grep -R services/` calls walked every `services/*/node_modules` and every Rust
# `services/*/target`, which on a developer machine took this gate from 5s to 134s after the
# 2026-08-02 merge added four Rust services — and once to a 900s TIMEOUT under
# `gate-wiring-gate --run-all`, i.e. a red gate for a reason that has nothing to do with what
# it checks. CI never saw it because a fresh checkout has neither directory.
SKIP=(--exclude-dir=node_modules --exclude-dir=target --exclude-dir=dist
      --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.pytest_cache)

# --- PREDICATES, extracted so cases can drive them --------------------------

# The handler named by an ADMIN-SQL/ADMIN-RPC marker line, or "".
marker_ref() {
  printf '%s' "$1" | sed -nE 's|.*//\s*ADMIN-(SQL\|RPC):\s*([A-Za-z0-9_]+).*|\2|p'
}

# The method named by an AdminHandler receiver line, or "".
method_name() {
  printf '%s' "$1" | sed -nE 's|.*func\s+\(\w+\s+\*AdminHandler\)\s+([A-Za-z0-9_]+).*|\1|p'
}

# The suppression pragma.
is_exempt() {
  printf '%s' "$1" | grep -qE '//\s*admin-registry-lint:exempt'
}

# Is $1 among the handler names in $2..? Exported names also match lower-camel.
handler_known() {
  local ref="$1" lc h
  shift
  lc="$(printf '%s' "${ref:0:1}" | tr 'A-Z' 'a-z')${ref:1}"
  for h in "$@"; do
    if [[ "$h" == "$ref" || "$h" == "$lc" ]]; then return 0; fi
  done
  return 1
}

run_lint() {
  if [[ ! -d "$REG_DIR" ]]; then
      echo "[admin-registry-lint] FAIL: $REG_DIR not found — run from repo root" >&2
      exit 2
  fi

  # Collect handler names from registry YAMLs.
  local handlers
  mapfile -t handlers < <(grep -hE '^\s*handler:\s*' "$REG_DIR"/*.yaml 2>/dev/null \
      | sed -E 's/^\s*handler:\s*//' \
      | tr -d '"' \
      | sort -u)

  if [[ ${#handlers[@]} -eq 0 ]]; then
      echo "[admin-registry-lint] FAIL: no handler: keys found in $REG_DIR" >&2
      exit 1
  fi

  echo "[admin-registry-lint] info: registry declares ${#handlers[@]} handlers"

  local marker_hits admin_handlers n_markers=0 n_methods=0 fail=0 line ref method

  # Scan for ADMIN-SQL / ADMIN-RPC markers.
  marker_hits=$(grep -RnE "${SKIP[@]}" '//\s*ADMIN-(SQL|RPC):' services/ 2>/dev/null \
      | grep -vE '//\s*admin-registry-lint:exempt' \
      || true)
  if [[ -n "$marker_hits" ]]; then
      while IFS= read -r line; do
          ref="$(marker_ref "$line")"
          if [[ -z "$ref" ]]; then continue; fi
          n_markers=$((n_markers + 1))
          if ! handler_known "$ref" "${handlers[@]}"; then
              echo "[admin-registry-lint] FAIL: $line"
              echo "    handler $ref not in $REG_DIR — register it or add // admin-registry-lint:exempt"
              fail=1
          fi
      done <<< "$marker_hits"
      if [[ $fail -ne 0 ]]; then
          exit 1
      fi
  fi

  # Scan for AdminHandler-style methods.
  admin_handlers=$(grep -RnE "${SKIP[@]}" 'func\s+\(\w+\s+\*AdminHandler\)\s+\w+' services/ 2>/dev/null \
      | grep -vE '//\s*admin-registry-lint:exempt' \
      || true)
  if [[ -n "$admin_handlers" ]]; then
      while IFS= read -r line; do
          method="$(method_name "$line")"
          if [[ -z "$method" ]]; then continue; fi
          n_methods=$((n_methods + 1))
          if ! handler_known "$method" "${handlers[@]}"; then
              echo "[admin-registry-lint] WARN: AdminHandler method $method not in registry"
              echo "    location: $line"
              # WARN, not fail — false positives common for shared HTTP plumbing.
          fi
      done <<< "$admin_handlers"
  fi

  # **SUBJECT COUNT, printed rather than implied.** With both scans at zero this
  # gate compares nothing, and the old message ("no orphan markers") read as a
  # verified fact. Say the number instead, so a green states what it covered.
  if [[ $n_markers -eq 0 && $n_methods -eq 0 ]]; then
      echo "[admin-registry-lint] PASS — ${#handlers[@]} registry handlers, and ZERO subjects:"
      echo "    no ADMIN-SQL/ADMIN-RPC marker and no *AdminHandler method exists in services/."
      echo "    Nothing was compared. This gate is a guard for a convention the tree does not"
      echo "    currently use (GT-ADMIN-NO-SUBJECT) — do not read this as admin coverage."
      exit 0
  fi
  echo "[admin-registry-lint] PASS: ${#handlers[@]} registry handlers; $n_markers marker(s) and $n_methods AdminHandler method(s) checked"
  exit 0
}

selftest() {
  local hs=(purgeUser rebuildProjection)

  # marker_ref, both spellings and the negative.
  if [[ "$(marker_ref 'services/x/y.go:12: // ADMIN-SQL: purgeUser')" != "purgeUser" ]]; then
    echo "[admin-registry-lint] SELFTEST FAIL — ADMIN-SQL marker not parsed"; exit 2
  fi
  if [[ "$(marker_ref 'services/x/y.go:12: // ADMIN-RPC: rebuildProjection')" != "rebuildProjection" ]]; then
    echo "[admin-registry-lint] SELFTEST FAIL — ADMIN-RPC marker not parsed"; exit 2
  fi
  if [[ -n "$(marker_ref 'services/x/y.go:12: // just a comment')" ]]; then
    echo "[admin-registry-lint] SELFTEST FAIL — parsed a handler out of an ordinary comment"; exit 2
  fi

  # method_name, and its lower-camel mapping through handler_known.
  if [[ "$(method_name 'func (h *AdminHandler) PurgeUser(w, r) {')" != "PurgeUser" ]]; then
    echo "[admin-registry-lint] SELFTEST FAIL — AdminHandler method not parsed"; exit 2
  fi
  if [[ -n "$(method_name 'func (h *UserHandler) PurgeUser(w, r) {')" ]]; then
    echo "[admin-registry-lint] SELFTEST FAIL — matched a NON-AdminHandler receiver (cry-wolf)"; exit 2
  fi

  # handler_known — the membership rule, both directions, plus the case fold
  # that is the only reason an exported Go method ever matches a yaml handler.
  if ! handler_known purgeUser "${hs[@]}"; then
    echo "[admin-registry-lint] SELFTEST FAIL — a REGISTERED handler was not found"; exit 2
  fi
  if ! handler_known PurgeUser "${hs[@]}"; then
    echo "[admin-registry-lint] SELFTEST FAIL — the exported->lower-camel fold is gone;"
    echo "    every AdminHandler method would be reported unregistered"; exit 2
  fi
  if handler_known deleteEverything "${hs[@]}"; then
    echo "[admin-registry-lint] SELFTEST FAIL — an UNREGISTERED handler was accepted (vacuous)"; exit 2
  fi

  # The exemption pragma is a rule too.
  if ! is_exempt 'x := 1 // admin-registry-lint:exempt'; then
    echo "[admin-registry-lint] SELFTEST FAIL — the exempt pragma is not recognised"; exit 2
  fi
  if is_exempt 'x := 1 // ordinary comment'; then
    echo "[admin-registry-lint] SELFTEST FAIL — an ordinary comment is being treated as exempt"; exit 2
  fi

  echo "[admin-registry-lint] SELFTEST PASS — both marker spellings parse, a non-AdminHandler"
  echo "    receiver is ignored, membership accepts a registered handler (and the"
  echo "    exported->lower-camel fold) while refusing an unregistered one, and the exempt"
  echo "    pragma matches only itself (non-vacuous both ways)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
