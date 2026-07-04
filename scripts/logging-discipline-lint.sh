#!/usr/bin/env bash
# logging-discipline-lint.sh — RAID cycle 32 (L7.E.9).
#
# Detects bare `fmt.Println`, `log.Println`, `log.Printf`, `print`, `println`
# outside test/debug code (SOFT / advisory), AND `logging.basicConfig` in Python
# service runtime (HARD / blocking — P2·A2a). Production services MUST use the
# shared structured logger: Go → `log/slog` wired via
# `github.com/loreweave/observability` (`observability.SetupLogging`, the A1 fleet
# idiom); Python → `loreweave_obs.setup_logging`.
#
# NOTE (P2·A2b): the old Go idiom `contracts/logging` (typed Field/Emit, 0 adopters)
# was RETIRED — the fleet standardized on slog + observability's span-reading handler.
# The allowlist entry below is gone with it.
#
# Two violation classes:
#   * SOFT (bare print / log.Print / println!) — advisory (warn-mode default). The
#     fleet still has ~67 legitimate ones (CLI drivers, Rust examples, *main.rs*
#     binaries), so these stay warn until a dedicated sweep; `error` mode flips them.
#   * HARD (`logging.basicConfig` in Python runtime) — ALWAYS blocking regardless of
#     mode. The runtime basicConfig sites were all migrated to setup_logging (P2·A2a),
#     so the baseline is 0; a NEW one fails CI. CLI `__main__` drivers + script/
#     benchmark/eval/migration dirs are exempt (plain logging is fine there).
#
# Exit code 0 = no HARD violations (and no SOFT ones in error-mode); non-zero otherwise.
#
# Scope (default): services/, contracts/, crates/.
# Exclude: *_test.go, *_test.rs, *_test.py, doc.go, scripts/, infra/.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../" && pwd)"
cd "$repo_root"

mode="${1:-warn}"
violations=0        # SOFT (bare print / log.Print / println!) — advisory
hard_violations=0   # HARD (Python runtime logging.basicConfig) — always blocking
violators=()

# Go: detect fmt.Print(ln/f) and bare log.Print(ln/f).
#
# Allow files ending in _test.go (tests stay terse).
# Allow doc.go files (godoc examples may show Print).
# Allow scripts/ and infra/ (not service code).
# (P2·A2b: the contracts/logging allowlist is gone — that module was retired.)
go_targets=$(git ls-files 'services/**/*.go' 'contracts/**/*.go' 2>/dev/null | \
    grep -v '_test\.go$' | \
    grep -v '/doc\.go$' || true)

for f in $go_targets ; do
    if grep -nE '(^|[^a-zA-Z_])(fmt\.Println|fmt\.Printf|fmt\.Print|log\.Println|log\.Printf|log\.Print)\(' "$f" >/dev/null 2>&1; then
        echo "[logging-discipline-lint] WARN: $f uses fmt.Print*/log.Print* — use log/slog via observability.SetupLogging instead"
        violations=$((violations + 1))
        violators+=("$f")
    fi
done

# Python: detect bare print(...) outside test/scripts.
py_targets=$(git ls-files 'services/**/*.py' 2>/dev/null | \
    grep -v '_test\.py$' | \
    grep -v '/tests/' | \
    grep -v '/test_' || true)

for f in $py_targets ; do
    # Strict pattern: ^\s*print\( — top-of-line print only (avoid matching
    # `breakpoint().print(...)` debugger calls etc.).
    if grep -nE '^[[:space:]]*print\(' "$f" >/dev/null 2>&1; then
        echo "[logging-discipline-lint] WARN: $f uses bare print() — use loreweave_obs.setup_logging"
        violations=$((violations + 1))
        violators+=("$f")
    fi
done

# Rust: detect println! and eprintln! outside crates/dp-kernel/src/logging.rs
# itself + tests.
rs_targets=$(git ls-files 'crates/**/*.rs' 'services/**/*.rs' 2>/dev/null | \
    grep -v '/tests/' | \
    grep -v '^crates/dp-kernel/src/logging\.rs$' || true)

for f in $rs_targets ; do
    if grep -nE '(println!|eprintln!)' "$f" >/dev/null 2>&1; then
        # Allow tests inside #[cfg(test)] block — basic heuristic only.
        if grep -q '#\[cfg(test)\]' "$f" && ! grep -nE '(println!|eprintln!)' "$f" | grep -v 'cfg(test)' >/dev/null ; then
            continue
        fi
        echo "[logging-discipline-lint] WARN: $f uses println!/eprintln! — use crates/dp-kernel::logging instead"
        violations=$((violations + 1))
        violators+=("$f")
    fi
done

# Python HARD: `logging.basicConfig` in service RUNTIME → use loreweave_obs.setup_logging.
# Exempt: tests, scripts/, benchmark/, eval/, migrations/ (+ db/migrations), poc, and a
# CLI `__main__` driver (basicConfig line AFTER an `if __name__ == "__main__"` guard —
# plain logging is the right output for a hand-run tool). Baseline is 0 (P2·A2a migrated
# every runtime site), so this catches a NEW regression.
bc_targets=$(git ls-files 'services/**/*.py' 2>/dev/null | \
    grep -v '_test\.py$' | \
    grep -v '/tests/' | \
    grep -v '/scripts/' | \
    grep -v '/benchmark/' | \
    grep -v '/eval/' | \
    grep -v '/migrations/' | \
    grep -v '/poc' || true)

for f in $bc_targets ; do
    # `|| true` — grep exits 1 on no-match; under `set -euo pipefail` a failed
    # command substitution in an assignment would kill the script.
    bc_line=$(grep -nE 'logging\.basicConfig\(' "$f" 2>/dev/null | head -1 | cut -d: -f1 || true)
    [ -z "$bc_line" ] && continue
    main_line=$(grep -nE '^if __name__[[:space:]]*==' "$f" 2>/dev/null | head -1 | cut -d: -f1 || true)
    if [ -n "$main_line" ] && [ "$bc_line" -gt "$main_line" ] ; then
        continue  # CLI __main__ driver — plain logging is fine for a hand-run tool
    fi
    echo "[logging-discipline-lint] ERROR: $f uses logging.basicConfig — use loreweave_obs.setup_logging"
    hard_violations=$((hard_violations + 1))
    violators+=("$f")
done

# HARD violations always block (a cleaned rule with a ready replacement), regardless of mode.
if [ "$hard_violations" -gt 0 ] ; then
    echo "[logging-discipline-lint] FAIL: $hard_violations basicConfig violation(s) — blocking (use loreweave_obs.setup_logging)"
    exit 1
fi

if [ "$violations" -eq 0 ] ; then
    echo "[logging-discipline-lint] clean (no basicConfig; no bare log calls in service code)"
    exit 0
fi

if [ "$mode" = "error" ] ; then
    echo "[logging-discipline-lint] FAIL: $violations soft violations (error-mode)"
    exit 1
fi

echo "[logging-discipline-lint] $violations soft violations (warn-mode, exit 0); 0 hard (basicConfig)"
exit 0
