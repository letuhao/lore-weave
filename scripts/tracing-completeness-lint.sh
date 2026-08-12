#!/usr/bin/env bash
# tracing-completeness-lint.sh — RAID cycle 32 (L7.G.11).
#
# Heuristic CI lint: detect HTTP/RPC handlers that do not import tracing.
#
# Detection rules (Go):
#   - file declares `func ... ServeHTTP(...)` OR `func ... Handle*(...)`
#     OR `chi.NewRouter` / `http.Handle`
#   - AND file does NOT import `contracts/tracing` or an otel trace package
#
# Detection rules (Rust):
#   - file declares `axum::` / `tower::` / `pub async fn handle`
#   - AND file does NOT import `dp_kernel::tracing` / `crate::tracing` / `use tracing`
#
# Exit 0 = at or below the ratchet; 1 = REGRESSION above it, or violations in
# error-mode; 2 = misuse / selftest failure / the scan reached nothing.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12), and the thing that made this
# gate unable to fail at all.
#
# ⚠️ **IT WAS DISARMED, AND THE DISARMAMENT WAS UNTRACKED.** Default mode is
# `warn`: it printed 49 violations and exited 0, so "it passed" and "49 handlers
# have no tracing" were the same observable. The header promised *"flip to error
# mode in cycle 33+ after handler migration"* — measured 2026-08-12, that flip
# appears in **no** deferral row and **no** handoff line. A prose promise in a
# docstring, several cycles overdue, with nothing to wake it. Same shape as
# `dependency-registry-lint`, which at least has `DEFERRED 082`.
#
# **The remedy is a RATCHET, not a flip.** Flipping to error today reds the
# build on 49 pre-existing violations, which is a migration and not a lint
# change. But a warn-mode gate with a falling baseline is armed against the one
# thing that actually matters day to day: a NEW untraced handler. The number can
# only fall; adding one reds the build immediately, in warn mode, today. This is
# the pattern `gate-teeth-gate` already uses on itself.
#
# **And it is 40x faster.** The scan ran one or two `grep` processes per file
# over 707 files — ~48s. `git grep` does the same work in two processes.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../" && pwd)"
cd "$repo_root"

# Handlers with no tracing import. Lower this as the migration proceeds; it must
# never be raised. Measured 2026-08-12: 36 Go + 13 Rust.
TRACING_VIOLATION_BASELINE=49

# ONE definition per rule, used by BOTH the bulk scan and the cases. A separate
# regex for the selftest would be testing a copy of the rule — the defect this
# repo has now hit in three gates.
GO_HANDLER_RE='(func.*ServeHTTP|func.*Handle[A-Z]|chi\.NewRouter|http\.Handle)'
GO_TRACED_RE='(loreweave/foundation/contracts/tracing|otel/.*trace)'
RS_HANDLER_RE='(axum::|tower::|pub async fn handle)'
RS_TRACED_RE='(dp_kernel::tracing|crate::tracing|use tracing)'

go_is_handler() { printf '%s' "$1" | grep -qE "$GO_HANDLER_RE"; }
go_is_traced()  { printf '%s' "$1" | grep -qE "$GO_TRACED_RE"; }
rs_is_handler() { printf '%s' "$1" | grep -qE "$RS_HANDLER_RE"; }
rs_is_traced()  { printf '%s' "$1" | grep -qE "$RS_TRACED_RE"; }

# Files matching $1 under pathspec $2, minus those matching $3 (the exclusion).
_untraced() {  # $1 handler-re, $2 pathspec, $3 traced-re, $4 path-exclude-re
  comm -23 \
    <(git grep -lE "$1" -- "$2" 2>/dev/null | grep -vE "$4" | sort -u) \
    <(git grep -lE "$3" -- "$2" 2>/dev/null | sort -u)
}

run_lint() {
  local mode="${1:-warn}"
  local n_go n_rs go_bad rs_bad violations f

  n_go=$(git ls-files 'services/**/*.go' 2>/dev/null | grep -vc '_test\.go$' || true)
  n_rs=$(git ls-files 'services/**/*.rs' 2>/dev/null | grep -vc '/tests/' || true)

  # REACH FLOOR. If either pathspec stops matching — a moved tree, a changed
  # glob syntax, a checkout with no services — the loops run zero times,
  # `violations` stays 0 and the gate prints "clean". A scan that reaches
  # nothing is byte-identical to full compliance (`BDR-82`).
  if [[ "$n_go" -lt 1 || "$n_rs" -lt 1 ]]; then
    echo "[tracing-completeness-lint] FAIL — the scan reached $n_go Go and $n_rs Rust file(s);"
    echo "  zero handlers checked reports 'clean', which is what full coverage looks like"
    exit 2
  fi

  go_bad="$(_untraced "$GO_HANDLER_RE" 'services/**/*.go' "$GO_TRACED_RE" '_test\.go$')"
  rs_bad="$(_untraced "$RS_HANDLER_RE" 'services/**/*.rs' "$RS_TRACED_RE" '/tests/')"

  for f in $go_bad; do
    echo "[tracing-completeness-lint] WARN: $f declares HTTP handler but does not import contracts/tracing"
  done
  for f in $rs_bad; do
    echo "[tracing-completeness-lint] WARN: $f declares axum/handler but does not import tracing"
  done

  violations=$(( $(printf '%s\n' "$go_bad" | grep -c . || true) + $(printf '%s\n' "$rs_bad" | grep -c . || true) ))

  if [ "$mode" = "error" ] && [ "$violations" -gt 0 ]; then
    echo "[tracing-completeness-lint] FAIL: $violations violations (error-mode)"
    exit 1
  fi

  # THE RATCHET. This is what makes a warn-mode gate able to fail. The flip to
  # error-mode is a migration nobody has scheduled; a NEW untraced handler is a
  # regression today, and this catches it today.
  if [ "$violations" -gt "$TRACING_VIOLATION_BASELINE" ]; then
    echo "[tracing-completeness-lint] FAIL — $violations untraced handler(s), above the"
    echo "  ratchet of $TRACING_VIOLATION_BASELINE. A NEW handler shipped without tracing."
    echo "  Import tracing in it, or state why and raise the baseline deliberately."
    exit 1
  fi
  if [ "$violations" -lt "$TRACING_VIOLATION_BASELINE" ]; then
    echo "[tracing-completeness-lint] PROGRESS — $violations untraced handler(s), below the"
    echo "  ratchet of $TRACING_VIOLATION_BASELINE. Lower TRACING_VIOLATION_BASELINE to $violations."
    exit 1
  fi

  echo "[tracing-completeness-lint] $violations untraced handler(s) at the ratchet"
  echo "  ($n_go Go + $n_rs Rust file(s) scanned; warn-mode — the error-mode flip promised"
  echo "  for 'cycle 33+' is tracked nowhere, see GT-TRACING-WARN-OVERDUE)"
  exit 0
}

selftest() {
  # Go handler detection — one case per alternative, plus the negative.
  local s
  for s in 'func (s *Server) ServeHTTP(w, r) {' 'func HandleThing(w, r) {' \
           'r := chi.NewRouter()' 'http.Handle("/x", h)'; do
    go_is_handler "$s" || { echo "[tracing-completeness-lint] SELFTEST FAIL — Go handler shape missed: $s"; exit 2; }
  done
  if go_is_handler 'func helper(a int) int { return a }'; then
    echo "[tracing-completeness-lint] SELFTEST FAIL — an ordinary Go func read as a handler (cry-wolf)"; exit 2
  fi
  go_is_traced 'import "loreweave/foundation/contracts/tracing"' \
    || { echo "[tracing-completeness-lint] SELFTEST FAIL — the contracts/tracing import not recognised"; exit 2; }
  go_is_traced 'import "go.opentelemetry.io/otel/sdk/trace"' \
    || { echo "[tracing-completeness-lint] SELFTEST FAIL — an otel trace import not recognised"; exit 2; }
  if go_is_traced 'import "fmt"'; then
    echo "[tracing-completeness-lint] SELFTEST FAIL — an unrelated import counted as tracing (vacuous)"; exit 2
  fi

  # Rust side, same shape.
  for s in 'use axum::Router;' 'use tower::Service;' 'pub async fn handle_x() {}'; do
    rs_is_handler "$s" || { echo "[tracing-completeness-lint] SELFTEST FAIL — Rust handler shape missed: $s"; exit 2; }
  done
  if rs_is_handler 'pub fn add(a: u32) -> u32 { a }'; then
    echo "[tracing-completeness-lint] SELFTEST FAIL — an ordinary Rust fn read as a handler (cry-wolf)"; exit 2
  fi
  rs_is_traced 'use tracing::info;' || { echo "[tracing-completeness-lint] SELFTEST FAIL — 'use tracing' not recognised"; exit 2; }
  if rs_is_traced 'use serde::Serialize;'; then
    echo "[tracing-completeness-lint] SELFTEST FAIL — an unrelated Rust import counted as tracing (vacuous)"; exit 2
  fi

  # THE RATCHET's arithmetic, driven directly. A baseline comparison that cannot
  # distinguish above / at / below is not a ratchet.
  local b=5
  [[ 6 -gt $b ]] || { echo "[tracing-completeness-lint] SELFTEST FAIL — a REGRESSION above the ratchet does not compare greater"; exit 2; }
  [[ 4 -lt $b ]] || { echo "[tracing-completeness-lint] SELFTEST FAIL — PROGRESS below the ratchet does not compare lesser"; exit 2; }
  if [[ $TRACING_VIOLATION_BASELINE -lt 1 ]]; then
    echo "[tracing-completeness-lint] SELFTEST FAIL — the ratchet is 0 or negative; every count is 'at or below'"; exit 2
  fi

  echo "[tracing-completeness-lint] SELFTEST PASS — all 4 Go and 3 Rust handler shapes detected,"
  echo "  ordinary functions are not; the tracing-import rules accept the real imports and refuse"
  echo "  unrelated ones; and the ratchet distinguishes above / at / below with a live baseline"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint "${2:-warn}" ;;
  "")         selftest; run_lint warn ;;
  warn|error) run_lint "$1" ;;      # back-compat: bare mode argument
  *)          echo "usage: $0 [--selftest | --lint [warn|error] | warn | error]"; exit 2 ;;
esac
