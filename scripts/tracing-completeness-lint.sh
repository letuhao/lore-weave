#!/usr/bin/env bash
# tracing-completeness-lint.sh — RAID cycle 32 (L7.G.11).
#
# Heuristic CI lint: detect new HTTP/RPC handlers that DO NOT call
# tracer.StartSpan(...). Warn mode in cycle 32 (services have not migrated
# yet); flip to error mode in cycle 33+ after handler migration.
#
# Detection rules (Go):
#   - file declares `func ... ServeHTTP(...)` OR `func ... Handle*(...)`
#     OR `func (s *Server) RPC*(...)` etc.
#   - AND file does NOT import `contracts/tracing`
#
# Detection rules (Rust):
#   - file declares `pub async fn handle_*` OR `axum::Router` route registration
#   - AND file does NOT import `dp_kernel::tracing` or `crates::tracing`
#
# Exit code 0 = no violations (or warn-mode); non-zero = violations in
# error-mode.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../" && pwd)"
cd "$repo_root"

mode="${1:-warn}"
violations=0

# ── Go services ───────────────────────────────────────────────────────────
go_targets=$(git ls-files 'services/**/*.go' 2>/dev/null | \
    grep -v '_test\.go$' || true)

for f in $go_targets ; do
    # Heuristic: file declares an HTTP handler or RPC method.
    if grep -qE '(func.*ServeHTTP|func.*Handle[A-Z]|chi\.NewRouter|http\.Handle)' "$f" 2>/dev/null ; then
        if ! grep -qE '(loreweave/foundation/contracts/tracing|otel/.*trace)' "$f" 2>/dev/null ; then
            echo "[tracing-completeness-lint] WARN: $f declares HTTP handler but does not import contracts/tracing"
            violations=$((violations + 1))
        fi
    fi
done

# ── Rust services ─────────────────────────────────────────────────────────
rs_targets=$(git ls-files 'services/**/*.rs' 2>/dev/null | \
    grep -v '/tests/' || true)

for f in $rs_targets ; do
    if grep -qE '(axum::|tower::|pub async fn handle)' "$f" 2>/dev/null ; then
        if ! grep -qE '(dp_kernel::tracing|crate::tracing|use tracing)' "$f" 2>/dev/null ; then
            echo "[tracing-completeness-lint] WARN: $f declares axum/handler but does not import tracing"
            violations=$((violations + 1))
        fi
    fi
done

if [ "$violations" -eq 0 ] ; then
    echo "[tracing-completeness-lint] clean (no handlers missing tracing import)"
    exit 0
fi

if [ "$mode" = "error" ] ; then
    echo "[tracing-completeness-lint] FAIL: $violations violations (error-mode)"
    exit 1
fi

echo "[tracing-completeness-lint] $violations violations (warn-mode, exit 0)"
exit 0
