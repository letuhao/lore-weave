#!/usr/bin/env bash
# logging-discipline-lint.sh — RAID cycle 32 (L7.E.9).
#
# Detects bare `fmt.Println`, `log.Println`, `log.Printf`, `print`, `println`
# outside test/debug code. Production services MUST use the typed structured
# logger from `contracts/logging` (`logging.NewLogger` + `Emit`).
#
# Exit code 0 = no violations; non-zero = violations found.
#
# Scope (default): services/, contracts/, crates/.
# Exclude: *_test.go, *_test.rs, *_test.py, doc.go, scripts/, infra/.
#
# Cycle 32 starts in warn-mode (echo violations; exit 0). Flip to error-mode
# in cycle 33+ after foundation services migrate (mirrors cycle-7 lint flip
# discipline used by observability-inventory-lint).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../" && pwd)"
cd "$repo_root"

mode="${1:-warn}"
violations=0
violators=()

# Go: detect fmt.Print(ln/f) and bare log.Print(ln/f).
#
# Allow contracts/logging itself (it's the canonical impl).
# Allow files ending in _test.go (tests stay terse).
# Allow doc.go files (godoc examples may show Print).
# Allow scripts/ and infra/ (not service code).
go_targets=$(git ls-files 'services/**/*.go' 'contracts/**/*.go' 2>/dev/null | \
    grep -v '_test\.go$' | \
    grep -v '/doc\.go$' | \
    grep -v '^contracts/logging/' || true)

for f in $go_targets ; do
    if grep -nE '(^|[^a-zA-Z_])(fmt\.Println|fmt\.Printf|fmt\.Print|log\.Println|log\.Printf|log\.Print)\(' "$f" >/dev/null 2>&1; then
        echo "[logging-discipline-lint] WARN: $f uses fmt.Print*/log.Print* — use contracts/logging instead"
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
        echo "[logging-discipline-lint] WARN: $f uses bare print() — use contracts/logging adapter"
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

if [ "$violations" -eq 0 ] ; then
    echo "[logging-discipline-lint] clean (no bare log calls in service code)"
    exit 0
fi

if [ "$mode" = "error" ] ; then
    echo "[logging-discipline-lint] FAIL: $violations violations (error-mode)"
    exit 1
fi

echo "[logging-discipline-lint] $violations violations (warn-mode, exit 0)"
exit 0
