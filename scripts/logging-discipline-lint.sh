#!/usr/bin/env bash
# logging-discipline-lint.sh — RAID cycle 32 (L7.E.9).
#
# Detects bare `fmt.Println`, `log.Println`, `log.Printf`, `print`, `println!`
# outside test/debug code (SOFT / ratcheted), AND `logging.basicConfig` in Python
# service runtime + bare `console.*` in backend TypeScript (HARD / blocking —
# P2·A2a, P2·A2b). Production services MUST use the shared structured logger:
# Go → `log/slog` wired via `github.com/loreweave/observability`
# (`observability.SetupLogging`, the A1 fleet idiom); Python →
# `loreweave_obs.setup_logging`; TS → the NestJS `Logger`.
#
# NOTE (P2·A2b): the old Go idiom `contracts/logging` (typed Field/Emit, 0 adopters)
# was RETIRED — the fleet standardized on slog + observability's span-reading handler.
#
# Two violation classes:
#   * SOFT (bare print / log.Print / println!) — the fleet carries a real backlog of
#     these (CLI drivers, Rust examples, *main.rs* binaries). Flipping them to blocking
#     is a migration, so they are RATCHETED instead: the count may not rise, and the
#     gate reds until the constant follows a drop. `error` mode flips them to blocking.
#   * HARD (`logging.basicConfig` in Python runtime; bare `console.*` in backend TS) —
#     ALWAYS blocking regardless of mode. Baseline 0; a NEW one fails CI. CLI
#     `__main__` drivers + script/benchmark/eval/migration dirs are exempt for Python;
#     tests + the game-server structured-logger sink are exempt for TS.
#
# Exit 0 = clean; 1 = violations; 2 = self-test failure / a list that reached nothing.
#
# Scope (default): services/, contracts/, crates/.
# Exclude: *_test.go, *_test.rs, *_test.py, doc.go, scripts/, infra/.
#
# ── GT5 · what this gate lacked, and what it now has ─────────────────────────
# **The Rust `#[cfg(test)]` exemption COULD NOT FIRE.** It read
# `grep -q '#[cfg(test)]' "$f" && ! grep -E 'println!' "$f" | grep -v 'cfg(test)'`
# — and the `grep -v` runs over the println! LINES, which never contain the string
# `cfg(test)`, so the pipeline always succeeded and the `!` always made the condition
# false. Measured 2026-08-12: **4 files carry both markers and the exemption fired for
# 0 of them**, while **2** have every `println!` below the marker and were being warned
# about anyway. Replaced with a position test that can actually distinguish the two,
# and both directions are bitten. This is the second rule in this batch that could not
# fire — see also `prompt-assembly`'s body-never-stored check.
#
# The SOFT leg was DISARMED (warn-mode, exit 0), so "it passed" and "87 bare log calls"
# were the same observable — `GTD-13`, third occurrence on this board. Its header also
# said *"~67"* while the tree held **87**: a number nothing measured. Now a RATCHET.
#
# No REACH FLOOR on any of the five target lists (`GT-F3`), and the two hardcoded
# exemption paths had no SHRINK ARM (`GT-F5`) — a rename would retire the exemption
# silently and re-grant it the day the name returned.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../" && pwd)"

# The SOFT backlog this tree is known to carry. A ratchet, not a target: it may
# only fall, and the gate reds until it does. Measured 2026-08-12: 85 (87 before
# the `#[cfg(test)]` exemption was repaired).
SOFT_BASELINE=85

# Hardcoded single-file exemptions. Each must name a real file — see the shrink
# arm in `run_lint`.
RS_LOGGER_EXEMPT="crates/dp-kernel/src/logging.rs"
TS_LOGGER_EXEMPT="services/game-server/src/log.ts"

_count() { local s="$1"; [[ -z "$s" ]] && { printf '0'; return; }; printf '%s\n' "$s" | wc -l | tr -d ' '; }

# run_lint <tree_root> [mode] [soft_expected]
#
# `$2`/`$3` use `${N+x}` (set) rather than `-n` (non-empty), so a probe passing an
# explicit empty value is not silently handed the production default (`GTD-17`).
run_lint() {
  local root="$1"
  local mode="warn"; if [[ "${2+x}" == "x" && -n "$2" ]]; then mode="$2"; fi
  local soft_expected="$SOFT_BASELINE"; if [[ "${3+x}" == "x" ]]; then soft_expected="$3"; fi

  local violations=0 hard_violations=0

  local ls="git -C $root ls-files"

  # ── target lists ──────────────────────────────────────────────────────────
  local go_targets py_targets rs_targets ts_targets bc_targets
  go_targets=$($ls 'services/**/*.go' 'contracts/**/*.go' 2>/dev/null \
      | grep -v '_test\.go$' | grep -v '/doc\.go$' || true)
  py_targets=$($ls 'services/**/*.py' 2>/dev/null \
      | grep -v '_test\.py$' | grep -v '/tests/' | grep -v '/test_' || true)
  rs_targets=$($ls 'crates/**/*.rs' 'services/**/*.rs' 2>/dev/null \
      | grep -v '/tests/' | grep -v "^${RS_LOGGER_EXEMPT}\$" || true)
  ts_targets=$($ls 'services/**/*.ts' 2>/dev/null \
      | grep -vE '\.(spec|test)\.ts$' | grep -v '/__tests__/' | grep -v '/tests/' \
      | grep -v "^${TS_LOGGER_EXEMPT}\$" || true)
  bc_targets=$($ls 'services/**/*.py' 2>/dev/null \
      | grep -v '_test\.py$' | grep -v '/tests/' | grep -v '/scripts/' \
      | grep -v '/benchmark/' | grep -v '/eval/' | grep -v '/migrations/' \
      | grep -v '/poc' || true)

  local n_go n_py n_rs n_ts n_bc
  n_go=$(_count "$go_targets"); n_py=$(_count "$py_targets")
  n_rs=$(_count "$rs_targets"); n_ts=$(_count "$ts_targets")
  n_bc=$(_count "$bc_targets")

  # ── REACH FLOORS (GT-F3). Four languages, four lists; any one of them can go
  # empty on its own (a renamed tree, a changed glob, a file left untracked by
  # git), and an empty list produces `clean` in exactly the bytes compliance
  # does, exit code included (BDR-82).
  if [[ "$n_go" -eq 0 || "$n_py" -eq 0 || "$n_rs" -eq 0 || "$n_ts" -eq 0 ]]; then
    echo "[logging-discipline-lint] ERROR — a target list is EMPTY, so its silence means nothing:" >&2
    echo "  go=$n_go py=$n_py rs=$n_rs ts=$n_ts (basicConfig subset=$n_bc)" >&2
    echo "  these come from \`git ls-files\`, so an untracked or renamed tree reads as clean." >&2
    return 2
  fi

  # ── SHRINK ARMS (GT-F5) on the two single-file exemptions. A path that is not
  # a file exempts nothing today and re-exempts it the day the name comes back.
  local p
  for p in "$RS_LOGGER_EXEMPT" "$TS_LOGGER_EXEMPT"; do
    if [[ ! -f "$root/$p" ]]; then
      echo "[logging-discipline-lint] ERROR — exemption path '$p' is not a file in this tree." >&2
      echo "  It exempts nothing, and would exempt that path again the day it returns." >&2
      return 2
    fi
  done

  # ── SOFT · Go: fmt.Print* / bare log.Print*.
  local f
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if grep -nE '(^|[^a-zA-Z_])(fmt\.Println|fmt\.Printf|fmt\.Print|log\.Println|log\.Printf|log\.Print)\(' "$root/$f" >/dev/null 2>&1; then
      echo "[logging-discipline-lint] WARN: $f uses fmt.Print*/log.Print* — use log/slog via observability.SetupLogging instead"
      violations=$((violations + 1))
    fi
  done <<< "$go_targets"

  # ── SOFT · Python: bare top-of-line print(.
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if grep -nE '^[[:space:]]*print\(' "$root/$f" >/dev/null 2>&1; then
      echo "[logging-discipline-lint] WARN: $f uses bare print() — use loreweave_obs.setup_logging"
      violations=$((violations + 1))
    fi
  done <<< "$py_targets"

  # ── SOFT · Rust: println!/eprintln!, except inside the trailing `#[cfg(test)]`
  # module. THE POSITION TEST: a test module is conventionally the last thing in
  # the file, so "every macro call sits below the first `#[cfg(test)]` marker" is
  # the distinguishing signal. The previous heuristic grepped the macro LINES for
  # the string `cfg(test)`, which they never contain, so it exempted nothing.
  local first_cfg first_macro
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    grep -qE '(println!|eprintln!)' "$root/$f" 2>/dev/null || continue
    first_cfg=$(grep -n '#\[cfg(test)\]' "$root/$f" 2>/dev/null | head -1 | cut -d: -f1 || true)
    if [[ -n "$first_cfg" ]]; then
      first_macro=$(grep -nE '(println!|eprintln!)' "$root/$f" | head -1 | cut -d: -f1)
      if [[ "$first_macro" -gt "$first_cfg" ]]; then
        continue  # every macro call is inside the trailing test module
      fi
    fi
    echo "[logging-discipline-lint] WARN: $f uses println!/eprintln! — use crates/dp-kernel::logging instead"
    violations=$((violations + 1))
  done <<< "$rs_targets"

  # ── HARD · Python `logging.basicConfig` in service RUNTIME.
  local bc_line main_line
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    # `|| true` — grep exits 1 on no-match; under `set -euo pipefail` a failed
    # command substitution in an assignment would kill the script.
    bc_line=$(grep -nE 'logging\.basicConfig\(' "$root/$f" 2>/dev/null | head -1 | cut -d: -f1 || true)
    [[ -z "$bc_line" ]] && continue
    main_line=$(grep -nE '^if __name__[[:space:]]*==' "$root/$f" 2>/dev/null | head -1 | cut -d: -f1 || true)
    if [[ -n "$main_line" && "$bc_line" -gt "$main_line" ]]; then
      continue  # CLI __main__ driver — plain logging is fine for a hand-run tool
    fi
    echo "[logging-discipline-lint] ERROR: $f uses logging.basicConfig — use loreweave_obs.setup_logging"
    hard_violations=$((hard_violations + 1))
  done <<< "$bc_targets"

  # ── HARD · TypeScript bare `console.*` in backend service runtime.
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if grep -nE 'console\.(log|error|warn|info|debug)\(' "$root/$f" >/dev/null 2>&1; then
      echo "[logging-discipline-lint] ERROR: $f uses console.* — use the NestJS Logger or a structured logger (P2·A2b)"
      hard_violations=$((hard_violations + 1))
    fi
  done <<< "$ts_targets"

  # HARD violations always block, regardless of mode.
  if [[ "$hard_violations" -gt 0 ]]; then
    echo "[logging-discipline-lint] FAIL: $hard_violations hard violation(s) — blocking (basicConfig / console.*)"
    return 1
  fi

  # ── THE SOFT RATCHET. Flipping the whole backlog to blocking is a migration;
  # a ratchet reds on the NEXT bare log call, which is the part that can regress
  # today. Both directions bite — a ratchet that only rises never falls.
  if [[ "$violations" -gt "$soft_expected" ]]; then
    echo "[logging-discipline-lint] FAIL: $violations soft violation(s), ratchet is $soft_expected."
    echo "  Use the structured logger, or move SOFT_BASELINE up only with a reason."
    return 1
  fi
  if [[ "$violations" -lt "$soft_expected" ]]; then
    echo "[logging-discipline-lint] FAIL: $violations soft violation(s), but the ratchet still says $soft_expected."
    echo "  A ratchet that never falls stops being one. Set SOFT_BASELINE=$violations."
    return 1
  fi

  if [[ "$mode" == "error" && "$violations" -gt 0 ]]; then
    echo "[logging-discipline-lint] FAIL: $violations soft violations (error-mode)"
    return 1
  fi

  echo "[logging-discipline-lint] PASS — $violations soft (ratchet $soft_expected), 0 hard;" \
       "scanned go=$n_go py=$n_py rs=$n_rs ts=$n_ts (basicConfig subset=$n_bc)"
  return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
# Each probe builds a REAL git repo, because `git ls-files` is the gate's own
# file discovery and a self-test that substituted `find` would be exercising a
# code path production never runs.
seed_tree() {
  local d="$1"
  mkdir -p "$d/services/svc/internal" "$d/services/svc/app" "$d/services/svc/src" \
           "$d/contracts/x" "$d/crates/dp-kernel/src" "$d/services/game-server/src"
  printf 'package api\n\nfunc H() {}\n'            > "$d/services/svc/internal/h.go"
  printf 'package x\n'                             > "$d/contracts/x/y.go"
  printf 'import logging\nlog = logging.getLogger(__name__)\n' > "$d/services/svc/app/m.py"
  printf 'pub fn ok() {}\n'                        > "$d/services/svc/src/lib.rs"
  printf 'export const x = 1;\n'                   > "$d/services/svc/src/app.ts"
  # the two exemption paths must EXIST or their shrink arms fire in every probe
  printf 'pub fn log_line(s: &str) { println!("{}", s); }\n' > "$d/crates/dp-kernel/src/logging.rs"
  printf 'export function log(m: string) { console.log(m); }\n' > "$d/services/game-server/src/log.ts"
}

git_add() {
  git -C "$1" -c init.defaultBranch=main init -q
  git -C "$1" -c core.autocrlf=false add -A -f >/dev/null 2>&1
}

selftest() {
  local failures=0

  # probe <name> <want_rc> <setup-fn> [mode] [soft_expected]
  probe() {
    local name="$1" want="$2" setup="$3"; shift 3
    local d got
    d="$(mktemp -d)"
    seed_tree "$d"
    "$setup" "$d"
    git_add "$d"
    set +e
    run_lint "$d" "$@" >/dev/null 2>&1
    got=$?
    set -e
    rm -rf "$d"
    if [[ "$got" == "$want" ]]; then
      echo "  ok   $name: rc=$got"
    else
      echo "  FAIL $name: rc=$got (want $want)"
      failures=$((failures + 1))
    fi
  }

  s_none()      { :; }
  s_go_print()  { printf 'package api\nfunc H() { fmt.Println("x") }\n' > "$1/services/svc/internal/bad.go"; }
  s_go_test()   { printf 'package api\nfunc H() { fmt.Println("x") }\n' > "$1/services/svc/internal/bad_test.go"; }
  s_go_doc()    { printf 'package api\nfunc H() { fmt.Println("x") }\n' > "$1/services/svc/internal/doc.go"; }
  s_py_print()  { printf 'print("x")\n'                     > "$1/services/svc/app/bad.py"; }
  s_py_intest() { mkdir -p "$1/services/svc/tests"; printf 'print("x")\n' > "$1/services/svc/tests/bad.py"; }
  # every macro call sits BELOW the trailing test module — the exemption's real case
  s_rs_testonly() { printf 'pub fn f() {}\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn t() { println!("x"); }\n}\n' > "$1/services/svc/src/b.rs"; }
  # a macro call ABOVE the marker — the same file must NOT be exempt
  s_rs_above()  { printf 'pub fn f() { println!("x"); }\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn t() {}\n}\n' > "$1/services/svc/src/b.rs"; }
  s_rs_plain()  { printf 'pub fn f() { println!("x"); }\n' > "$1/services/svc/src/b.rs"; }
  s_py_bc()     { printf 'import logging\nlogging.basicConfig()\n' > "$1/services/svc/app/bad.py"; }
  s_py_bc_main() { printf 'import logging\nif __name__ == "__main__":\n    logging.basicConfig()\n' > "$1/services/svc/app/cli.py"; }
  s_py_bc_scripts() { mkdir -p "$1/services/svc/scripts"; printf 'import logging\nlogging.basicConfig()\n' > "$1/services/svc/scripts/tool.py"; }
  s_ts_console() { printf 'console.log("x");\n'            > "$1/services/svc/src/bad.ts"; }
  s_ts_spec()   { printf 'console.log("x");\n'             > "$1/services/svc/src/bad.spec.ts"; }
  # Remove ONLY the non-exempt .ts. Deleting the exemption file too made the
  # SHRINK ARM fire instead of the floor, so the probe passed for the wrong
  # rule and the floor stayed uncovered — two rules sharing one fixture, which
  # is `GTD-17` in miniature. Found by a bite arm reding without its message.
  s_no_ts()     { rm -f "$1/services/svc/src/app.ts"; }
  s_no_go()     { rm -f "$1/services/svc/internal/h.go" "$1/contracts/x/y.go"; }
  s_rs_exempt_gone() { rm -f "$1/crates/dp-kernel/src/logging.rs"; }
  s_ts_exempt_gone() { rm -f "$1/services/game-server/src/log.ts"; }

  echo "logging-discipline-lint --self-test"

  probe "a clean tree passes" 0 s_none warn 0

  # SOFT · Go
  probe "fmt.Println is a soft violation" 1 s_go_print warn 0
  probe "...and passes when the ratchet expects it" 0 s_go_print warn 1
  probe "...but a _test.go is excluded" 0 s_go_test warn 0
  probe "...and so is doc.go" 0 s_go_doc warn 0

  # SOFT · Python
  probe "a bare print() is a soft violation" 1 s_py_print warn 0
  probe "...but one under tests/ is excluded" 0 s_py_intest warn 0

  # SOFT · Rust + the exemption that could not fire
  probe "a bare println! is a soft violation" 1 s_rs_plain warn 0
  probe "...but one inside the trailing #[cfg(test)] module is NOT" 0 s_rs_testonly warn 0
  probe "...while one ABOVE the marker still is" 1 s_rs_above warn 0

  # HARD
  probe "logging.basicConfig at module level is HARD" 1 s_py_bc warn 0
  probe "...but one after an if __name__ guard is not" 0 s_py_bc_main warn 0
  probe "...nor one under scripts/" 0 s_py_bc_scripts warn 0
  probe "a bare console.* in backend TS is HARD" 1 s_ts_console warn 0
  probe "...but one in a .spec.ts is not" 0 s_ts_spec warn 0

  # the ratchet, both directions + error mode
  probe "the ratchet reds when the count FALLS below it" 1 s_none warn 1
  probe "error mode blocks a soft violation the ratchet allows" 1 s_go_print error 1

  # shrink arms + reach floors
  probe "a missing Rust exemption path is misuse, not a pass" 2 s_rs_exempt_gone warn 0
  probe "a missing TS exemption path is misuse, not a pass" 2 s_ts_exempt_gone warn 0
  probe "an EMPTY TypeScript list is misuse, not a pass" 2 s_no_ts warn 0
  probe "an EMPTY Go list is misuse, not a pass" 2 s_no_go warn 0

  if [[ $failures -gt 0 ]]; then
    echo "logging-discipline-lint --self-test: $failures rule(s) did not behave"
    return 2
  fi
  echo "logging-discipline-lint --self-test: every rule bites, and none cries wolf"
  return 0
}

case "${1:-}" in
  --self-test|--selftest) selftest ;;
  ""|warn|error)
    selftest || exit 2
    echo
    run_lint "$REPO_ROOT" "${1:-warn}"
    ;;
  *)
    echo "usage: $0 [warn|error|--self-test]" >&2
    exit 2
    ;;
esac
