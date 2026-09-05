#!/usr/bin/env bash
# L1.K.14 prompt-assembly-discipline-lint.sh — I2 / I10 / S09 §12Y
#
# Two rules:
#
#  1. Direct LLM SDK use (`openai`, `anthropic`, `litellm`) is FORBIDDEN outside
#     the sanctioned homes below. This is the Provider-gateway invariant in lint
#     form: every provider call goes through provider-registry-service.
#  2. Body-never-stored (S09 §12Y): the prompt_audit migration must not declare
#     a column holding prompt text.
#
# Exit 0 = clean; 1 = violations; 2 = self-test failure / nothing scanned.
#
# ── GT5 · what this gate lacked, and what it now has ─────────────────────────
# **Rule 2 COULD NOT FIRE.** It piped `grep -nvE '^\s*--' file` into
# `grep -niE '^\s*(body|…)\s+(TEXT|…)'` — and `grep -n` prefixes each line with
# `LINENO:`, so the second pattern's `^` anchor never reached the SQL. A
# migration declaring `body TEXT` was waved through. Demonstrated 2026-08-12 on
# a three-line fixture. That is `NV-1` shipped in production, guarding a privacy
# invariant, under a header calling itself *"defense-in-depth"* — the costume of
# evidence, worn for months. Comments are now stripped with `sed` (which
# preserves the line count, so `grep -n` still reports true line numbers).
#
# The migration's absence was a second silent pass: `if [[ -f … ]]` meant one
# `git mv` retired the rule permanently — the THIRD gate on this board with that
# exact line, after `transitions-validation` (`GTD-10`) and
# `observability-inventory` (`GTD-14`). Now exit 2.
#
# Rule 1 had no REACH FLOOR (`GT-F3`) and five exclusion rows, of which
# **all five exempted nothing** — measured 2026-08-12: zero raw matches across
# services/, contracts/ and crates/ before any filter, because this repo has no
# provider SDK dependency at all (provider-registry-service is Go and speaks raw
# HTTP). One row, `services/knowledge-service/`, **was never in the documented
# allowlist**: an exemption wider than its stated reason (`GTD-18`'s shape), and
# the only one that would have hidden a genuine invariant breach. Trimmed to the
# two homes the invariant actually sanctions, each with a shrink arm.
#
# Its detector also could not see the TypeScript idiom it claimed to cover. The
# pattern wanted the MODULE name right after `import`, which is the Python form;
# the ES-module form names the BINDING there. `import OpenAI from "openai"` was
# caught anyway — but only because the scan is case-insensitive and the binding
# happened to be spelled `OpenAI`. `import Foo from "openai"` was invisible.
# **That accident first showed up as a bite arm coming back GREEN**: deleting the
# new TypeScript alternative left the self-test passing, because the case had
# been written with the colliding name. The case was wrong, not the arm.
# `--include='*.rs'` likewise scanned Rust with patterns no Rust file can
# satisfy. Both idioms added, and the TS case now uses a non-colliding binding.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── The sanctioned homes. A POLICY allowlist, not an offender baseline: these
# pre-authorise, they do not track debt. Each row must name a real directory —
# a renamed one exempts nothing while still looking like coverage, and would
# re-exempt the day the name came back (`GT-F5`).
#
# `services/chat-service/` and `services/knowledge-service/` were removed here.
# The header claimed chat-service *"uses litellm"*; measured 2026-08-12 it has
# no SDK import of any kind, and knowledge-service was in the code with no
# documented reason at all.
SANCTIONED=(
  "contracts/prompt"                       # the prompt assembly library itself
  "services/provider-registry-service"     # the ONLY home of provider SDKs/keys
)

# Direct SDK import / module usage, per-language idiom:
#   python  `import openai` / `from openai import …`
#   node    `require('openai')` / `import OpenAI from "openai"`
#   rust    `use litellm::…`
#   any     `openai.Client` / `anthropic.Client` / `litellm.completion`
# The `.` standing in for a quote character follows this file's existing
# convention and keeps the pattern shell-quotable.
SDK_RE='(^[[:space:]]*import[[:space:]]+(openai|anthropic|litellm)'\
'|^[[:space:]]*from[[:space:]]+(openai|anthropic|litellm)'\
'|^[[:space:]]*use[[:space:]]+(openai|anthropic|litellm)'\
'|require\(.(openai|anthropic|litellm).\)'\
'|from[[:space:]]*.(openai|anthropic|litellm|@anthropic-ai/[a-z-]+).[[:space:];]'\
'|\bopenai\.(Client|Configuration|ChatCompletion)'\
'|\banthropic\.Client'\
'|\blitellm\.completion)'

FORBIDDEN_COLS='(body|prompt_text|assembled_text|full_prompt|raw_prompt)'

# Foreign trees. Measured 2026-08-12 BEFORE this list existed: 12358 of the
# 16459 files this gate walked — **75%** — were vendored third-party code, so it
# was judging other people's packages by this repo's invariant. Zero matched
# today, which is luck: one transitive dependency doing `require('openai')`
# produces a finding nobody in this repo can act on. `GTD-8`, second occurrence.
EXCLUDE_DIRS=(node_modules target .venv venv site-packages vendor __pycache__
              dist build coverage .next)
grep_excludes() {
  local d
  for d in "${EXCLUDE_DIRS[@]}"; do printf -- '--exclude-dir=%s\n' "$d"; done
}
find_prune_expr() {
  # emits: ( -name a -o -name b … ) -prune -o
  local first=1 d
  printf '(\n'
  for d in "${EXCLUDE_DIRS[@]}"; do
    [[ $first -eq 1 ]] || printf -- '-o\n'
    printf -- '-name\n%s\n' "$d"
    first=0
  done
  printf ')\n-prune\n-o\n'
}

# run_lint <tree_root>
run_lint() {
  local root="$1"
  local violations=0

  local roots=("$root/services" "$root/contracts" "$root/crates")

  # ── REACH FLOOR (GT-F3). A grep whose corpus is empty says PASS in exactly
  # the same bytes as a compliant tree, exit code included (BDR-82).
  local n_src=0 d
  mapfile -t _prune < <(find_prune_expr)
  for d in "${roots[@]}"; do
    [[ -d "$d" ]] || continue
    n_src=$(( n_src + $( { find "$d" "${_prune[@]}" -type f \( -name '*.go' -o -name '*.py' \
              -o -name '*.ts' -o -name '*.tsx' -o -name '*.rs' \) -print 2>/dev/null || true; } \
              | wc -l ) ))
  done
  if [[ "$n_src" -eq 0 ]]; then
    echo "[prompt-assembly] ERROR — 0 source file(s) under services/, contracts/, crates/." >&2
    echo "  A walk that reached nothing is not a clean tree (BDR-82)." >&2
    return 2
  fi

  # ── SHRINK ARM (GT-F5) — a sanctioned home that is not a real directory.
  local p
  for p in "${SANCTIONED[@]}"; do
    if [[ ! -d "$root/$p" ]]; then
      echo "[prompt-assembly] FAIL — sanctioned home '$p' is not a directory in this tree."
      echo "  It exempts nothing today and would re-exempt the day the name returns."
      violations=$((violations + 1))
    fi
  done

  # ── RULE 1 · direct SDK use outside the sanctioned homes.
  local all_hits exempt_re hits n_all=0 n_exempt=0
  mapfile -t _gx < <(grep_excludes)
  all_hits=$(grep -rniE "$SDK_RE" \
    --include='*.go' --include='*.py' --include='*.ts' --include='*.tsx' --include='*.rs' \
    "${_gx[@]}" "${roots[@]}" 2>/dev/null \
    | grep -vE '_test\.' \
    | grep -vE ':[[:space:]]*(//|#|\*|///)' || true)
  [[ -n "$all_hits" ]] && n_all=$(printf '%s\n' "$all_hits" | wc -l)

  exempt_re="$(printf '%s|' "${SANCTIONED[@]}")"
  exempt_re="${exempt_re%|}"
  hits="$all_hits"
  if [[ -n "$all_hits" && -n "$exempt_re" ]]; then
    hits=$(printf '%s\n' "$all_hits" | grep -vE "($exempt_re)/" || true)
    local n_kept=0
    [[ -n "$hits" ]] && n_kept=$(printf '%s\n' "$hits" | wc -l)
    n_exempt=$(( n_all - n_kept ))
  fi

  if [[ -n "$hits" ]]; then
    echo "[prompt-assembly] FAIL — direct LLM SDK use outside the sanctioned homes (I2/I10):"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # ── RULE 2 · body-never-stored. Strip SQL comments with `sed` rather than a
  # `grep -n` pipe: `sed` preserves the line COUNT, so `grep -n` downstream still
  # reports true line numbers, and — the part that matters — it does not put a
  # `LINENO:` prefix in front of the `^` anchor the pattern depends on.
  local audit_sql="$root/migrations/meta/017_prompt_audit.up.sql"
  if [[ ! -f "$audit_sql" ]]; then
    echo "[prompt-assembly] ERROR — $audit_sql is missing." >&2
    echo "  Rule 2 (S09 §12Y, body-never-stored) has no subject; a rename must not" >&2
    echo "  retire a privacy invariant silently (GTD-10 / GTD-14, third occurrence)." >&2
    return 2
  fi
  local bad
  bad=$(sed -E 's/--.*$//' "$audit_sql" \
        | grep -niE "^[[:space:]]*${FORBIDDEN_COLS}[[:space:]]+(TEXT|BYTEA|VARCHAR)" || true)
  if [[ -n "$bad" ]]; then
    echo "[prompt-assembly] FAIL — prompt_audit migration declares a prompt-body column (S09 §12Y):"
    echo "$bad" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  if [[ $violations -gt 0 ]]; then
    echo "[prompt-assembly] FAIL — $violations issue(s) (I2 / I10 / S09 §12Y)"
    return 1
  fi
  echo "[prompt-assembly] PASS — ${n_src} source file(s) scanned, ${n_all} SDK use(s) found," \
       "${n_exempt} inside the ${#SANCTIONED[@]} sanctioned home(s); prompt_audit declares no body column"
  return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
seed_tree() {
  local d="$1"
  mkdir -p "$d/services/svc" "$d/contracts/prompt" "$d/crates/k/src" \
           "$d/services/provider-registry-service" "$d/migrations/meta"
  printf 'package main\n' > "$d/services/svc/main.go"
  printf 'x = 1\n'        > "$d/services/svc/app.py"
  printf 'export const x = 1;\n' > "$d/services/svc/app.ts"
  printf 'pub fn ok() {}\n' > "$d/crates/k/src/lib.rs"
  printf 'CREATE TABLE prompt_audit (\n  id UUID PRIMARY KEY,\n  sha256 TEXT NOT NULL\n);\n' \
    > "$d/migrations/meta/017_prompt_audit.up.sql"
}

selftest() {
  local failures=0

  probe() {
    local name="$1" want="$2" setup="$3"
    local d got
    d="$(mktemp -d)"
    seed_tree "$d"
    "$setup" "$d"
    set +e
    run_lint "$d" >/dev/null 2>&1
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

  s_none()        { :; }
  s_py_import()   { printf 'import openai\n'            > "$1/services/svc/bad.py"; }
  s_py_from()     { printf 'from anthropic import C\n'  > "$1/services/svc/bad.py"; }
  s_py_litellm()  { printf 'r = litellm.completion(x)\n' > "$1/services/svc/bad.py"; }
  s_ts_require()  { printf "const o = require('openai');\n" > "$1/services/svc/bad.ts"; }
  # The binding name must NOT be `OpenAI`. The scan is case-insensitive, so
  # `import OpenAI …` is matched by the PYTHON alternative (`import` + the
  # module name) purely by coincidence of naming — and a probe satisfied by an
  # accident certifies the wrong rule. Measured: with this case written as
  # `import OpenAI`, deleting the TypeScript alternative left the self-test
  # green, which is the arm reporting coverage the rule does not have.
  s_ts_esm()      { printf 'import Foo from "openai";\n' > "$1/services/svc/bad.ts"; }
  s_rs_use()      { printf 'use litellm::Client;\n'     > "$1/crates/k/src/bad.rs"; }
  s_in_prompt()   { printf 'import openai\n'            > "$1/contracts/prompt/ok.py"; }
  s_in_registry() { printf 'import openai\n'            > "$1/services/provider-registry-service/ok.py"; }
  s_in_test()     { printf 'import openai\n'            > "$1/services/svc/bad_test.py"; }
  s_in_comment()  { printf '# r = litellm.completion(x)\n' > "$1/services/svc/ok.py"; }
  s_sql_body()    { printf 'CREATE TABLE prompt_audit (\n  id UUID,\n  body TEXT\n);\n' \
                      > "$1/migrations/meta/017_prompt_audit.up.sql"; }
  s_sql_raw()     { printf 'CREATE TABLE prompt_audit (\n  raw_prompt BYTEA\n);\n' \
                      > "$1/migrations/meta/017_prompt_audit.up.sql"; }
  s_sql_comment() { printf 'CREATE TABLE prompt_audit (\n  id UUID\n  -- body TEXT is forbidden\n);\n' \
                      > "$1/migrations/meta/017_prompt_audit.up.sql"; }
  s_sql_gone()    { rm -f "$1/migrations/meta/017_prompt_audit.up.sql"; }
  s_home_gone()   { rm -rf "$1/contracts/prompt"; }
  s_no_src()      { rm -rf "$1/services" "$1/crates"; rm -f "$1/contracts/prompt"/*; }
  # a vendored dependency that imports an LLM SDK is NOT this repo's violation —
  # and before the prune this gate walked 12358 such files looking for one
  s_vendored()    { mkdir -p "$1/services/svc/node_modules/pkg"
                    printf "const o = require('openai');\n" \
                      > "$1/services/svc/node_modules/pkg/index.ts"; }

  echo "prompt-assembly-discipline-lint --self-test"

  probe "a clean tree passes" 0 s_none

  # Rule 1 — one probe per language idiom
  probe "python 'import openai' fails" 1 s_py_import
  probe "python 'from anthropic import' fails" 1 s_py_from
  probe "a litellm.completion call fails" 1 s_py_litellm
  probe "node require('openai') fails" 1 s_ts_require
  probe "TS 'import Foo from \"openai\"' fails" 1 s_ts_esm
  probe "rust 'use litellm::' fails" 1 s_rs_use

  # …and the shapes that must NOT cry wolf
  probe "...but the same import in contracts/prompt/ does not" 0 s_in_prompt
  probe "...nor in provider-registry-service/" 0 s_in_registry
  probe "...nor in a _test. file" 0 s_in_test
  probe "...nor in a comment" 0 s_in_comment
  probe "...nor in a vendored node_modules package" 0 s_vendored

  # Rule 2 — the leg that could not fire
  probe "a 'body TEXT' column in prompt_audit fails" 1 s_sql_body
  probe "a 'raw_prompt BYTEA' column fails" 1 s_sql_raw
  probe "...but the same words in a SQL comment do not" 0 s_sql_comment
  probe "a MISSING prompt_audit migration is misuse, not a pass" 2 s_sql_gone

  # Shrink arm + reach floor
  probe "a sanctioned home that is not a directory fails" 1 s_home_gone
  probe "no source files at all is misuse, not a pass" 2 s_no_src

  if [[ $failures -gt 0 ]]; then
    echo "prompt-assembly-discipline-lint --self-test: $failures rule(s) did not behave"
    return 2
  fi
  echo "prompt-assembly-discipline-lint --self-test: every rule bites, and none cries wolf"
  return 0
}

case "${1:-}" in
  --self-test|--selftest) selftest ;;
  "")
    selftest || exit 2
    echo
    run_lint "$REPO_ROOT"
    ;;
  *)
    echo "usage: $0 [--self-test]" >&2
    exit 2
    ;;
esac
