#!/usr/bin/env bash
# L1.K.9 timeout-discipline-lint.sh — SR06 I16 · PERF-1
#
# Standard: docs/standards/performance.md › Rules › PERF-1 (Timeouts
# everywhere, all languages). Outbound network/db calls MUST set an explicit
# timeout. We flag the most-common unguarded patterns:
#   * Go:   http.Get / http.Post / http.Head / http.PostForm — all bypass timeout
#   * Go:   db.Query / db.Exec with a bare SQL literal (no context)
#   * Rust: reqwest::get / Client::new().get — the no-timeout shortcut
#   * Python (PERF-1 extension):
#       - httpx.AsyncClient( / httpx.Client( / aiohttp.ClientSession( with no
#         `timeout=` in the (possibly multiline) constructor
#       - requests.<method>( with no `timeout=`
#       - asyncpg.create_pool( / asyncpg.connect( with no statement timeout
#
# Heuristic — produces some false positives in tests; test/script/eval files
# are excluded, and a BASELINE of known Python offenders is carried so the lint
# flags only NEW violations. Refresh with:
#     PERF_LINT_BASELINE_REGEN=1 scripts/timeout-discipline-lint.sh
#
# ── GT5 · what this gate lacked, and what it now has ─────────────────────────
# It had no way to say what it SCANNED. Every leg is a `grep -r` whose empty
# result is byte-identical to compliance, and the greps swallowed stderr, so a
# renamed `services/` printed `PASS` forever (`BDR-82`). Three REACH FLOORS
# (`GT-F3`), one per walk, now print their counts and exit 2 on zero.
#
# Its Python leg was DISARMED: it printed offenders and exited 0, so "it passed"
# and "3 unguarded calls" were the same observable — the `GTD-13` shape, and its
# header promised a flip to blocking that lived in no deferral row. Flipping it
# outright is a migration; it is now armed by a RATCHET on the new-beyond-
# baseline count, which reds on a NEW offender today and reds again when the
# count falls without `PY_NEW_BASELINE` following it.
#
# Its baseline had no SHRINK ARM (`GT-F5`). A row dies two ways — its file
# disappears, or the call it names gets a timeout — and either way the row stops
# exempting anything while still looking like coverage, and silently re-exempts
# the offender the day it comes back. Both deaths now red. Measured 2026-08-12:
# all 10 rows live, 0 dead.
#
# `run_lint` is parameterised on the tree root (+ baseline file + ratchet), so
# `--self-test` drives the REAL checker over a synthetic tree rather than
# re-implementing its rules.
#
# Exit 0 = clean; 1 = violations; 2 = self-test failure / nothing scanned.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# The number of Python offenders NOT in the baseline that this tree is known to
# carry. A ratchet, not a target: it may only fall, and the gate reds until it
# does. Measured 2026-08-12: 3.
PY_NEW_BASELINE=3

# BASELINE of known Python offenders (runtime code only; test/script/eval files
# are excluded up-front). Each line is `relpath<TAB>snippet` (line-number-free
# so it survives edits elsewhere in the file). Keep sorted.
perf_py_baseline() {
  cat <<'PERF_PY_BASELINE'
services/campaign-service/app/database.py	_pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
services/chat-service/app/client/book_steering_client.py	self._http = httpx.AsyncClient(**client_kwargs)
services/chat-service/app/client/knowledge_client.py	self._http = httpx.AsyncClient(**client_kwargs)
services/chat-service/app/client/known_entities_client.py	self._http = httpx.AsyncClient(**client_kwargs)
services/chat-service/app/client/user_skills_client.py	self._http = httpx.AsyncClient(**kwargs)
services/chat-service/app/db/pool.py	_pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
services/jobs-service/app/database.py	_pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
services/learning-service/app/db/pool.py	_pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
services/lore-enrichment-service/app/db/pool.py	_pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
services/translation-service/app/database.py	_pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
PERF_PY_BASELINE
}

# awk multiline scanner: for each trigger (httpx/aiohttp/asyncpg/requests
# constructor|call), balance-capture the call across lines and flag it when
# the captured text contains no `timeout` token. Emits `rel<TAB>line<TAB>snippet`.
PERF_PY_AWK='
function evalbuf(   rel) {
  if (buf !~ /timeout/) {
    rel = startfile
    if (substr(rel,1,length(root))==root) rel = substr(rel,length(root)+1)
    print rel "\t" startfnr "\t" snippet
  }
}
FNR==1 { if (capturing) { evalbuf(); capturing=0 } }
{
  if (!capturing) {
    if (match($0, /(httpx\.(AsyncClient|Client)|aiohttp\.ClientSession|asyncpg\.(create_pool|connect)|requests\.(get|post|put|patch|delete|head|request))[ \t]*\(/)) {
      startfile=FILENAME; startfnr=FNR
      snippet=$0; sub(/^[ \t]+/,"",snippet)
      buf=substr($0, RSTART)
      rest=substr($0, RSTART+RLENGTH)
      depth=1
      n=length(rest)
      for(i=1;i<=n;i++){c=substr(rest,i,1); if(c=="(")depth++; else if(c==")"){depth--; if(depth==0)break}}
      if (depth==0) evalbuf(); else capturing=1
    }
  } else {
    buf=buf "\n" $0
    n=length($0)
    for(i=1;i<=n;i++){c=substr($0,i,1); if(c=="(")depth++; else if(c==")"){depth--; if(depth==0)break}}
    if (depth==0){ evalbuf(); capturing=0 }
  }
}
END { if (capturing) evalbuf() }
'

# Count files of one extension across the given roots. Missing roots contribute
# zero rather than killing the script — `set -e` turning a missing directory
# into an abort is exactly how `GTD-5`'s reach floor became unreachable in the
# case it was written for.
count_ext() {
  local ext="$1"; shift
  local n=0 d
  for d in "$@"; do
    [[ -d "$d" ]] || continue
    n=$(( n + $( { find "$d" -type f -name "*.${ext}" 2>/dev/null || true; } | wc -l ) ))
  done
  printf '%s' "$n"
}

# run_lint <tree_root> [baseline_file] [py_new_expected]
#
# `$2`/`$3` are tested with `${N+x}` (set) rather than `-n` (non-empty): a probe
# asserting "an EMPTY baseline exempts nothing" must not be silently handed the
# production list, which is `GTD-17` in one line.
run_lint() {
  local root="$1"
  local baseline_file_set="" baseline_file=""
  if [[ "${2+x}" == "x" ]]; then baseline_file_set=x; baseline_file="$2"; fi
  local py_expected="$PY_NEW_BASELINE"
  if [[ "${3+x}" == "x" ]]; then py_expected="$3"; fi

  local services="$root/services" crates="$root/crates" contracts="$root/contracts"
  local violations=0 hits

  # ── REACH FLOORS (GT-F3) — one per walk, BEFORE any verdict. A leg that
  # scanned nothing has not found nothing; it has not looked.
  local n_go n_rs n_py
  n_go=$(count_ext go "$services" "$contracts")
  n_rs=$(count_ext rs "$services" "$crates")
  n_py=$(count_ext py "$services")
  if [[ "$n_go" -eq 0 || "$n_rs" -eq 0 || "$n_py" -eq 0 ]]; then
    echo "[timeout-discipline] ERROR — a leg scanned NOTHING, so its silence means nothing:" >&2
    echo "  go=$n_go (services+contracts)  rs=$n_rs (services+crates)  py=$n_py (services)" >&2
    echo "  a zero here is a moved/renamed tree, not compliance (BDR-82)." >&2
    return 2
  fi

  # Go: http.Get / http.Post / http.Head / http.PostForm — all bypass timeout.
  hits=$(grep -rnE '(\b|^)http\.(Get|Post|Head|PostForm)\(' \
    --include='*.go' "$services" "$contracts" 2>/dev/null \
    | grep -vE '_test\.go:' || true)
  if [[ -n "$hits" ]]; then
    echo "[timeout-discipline] FAIL — http.{Get,Post,Head,PostForm} bypasses timeout:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # Go: db.Query / db.Exec without Context (db.QueryContext / db.ExecContext are OK).
  # Also accept pgx convention: tx.Exec(ctx, ...) where the first arg is a
  # context. Heuristic: flag only when the first arg starts with `"` or a
  # backtick (a SQL literal).
  hits=$(grep -rnE '\b(db|tx)\.(Query|Exec)\(("|`)' \
    --include='*.go' "$services" "$contracts" 2>/dev/null \
    | grep -vE '_test\.go:' || true)
  if [[ -n "$hits" ]]; then
    echo "[timeout-discipline] FAIL — db.{Query,Exec} without Context (use QueryContext/ExecContext):"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # Rust: reqwest::get is the no-timeout shortcut
  hits=$(grep -rnE 'reqwest::(get|Client::new\(\)\.get)' \
    --include='*.rs' "$services" "$crates" 2>/dev/null \
    | grep -vE 'mod tests' || true)
  if [[ -n "$hits" ]]; then
    echo "[timeout-discipline] FAIL — reqwest::get bypasses timeout:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi

  # ── Python (PERF-1) ────────────────────────────────────────────────────
  local py_candidates py_hits base_tmp py_new n_cand=0 n_hits=0 n_new=0
  py_candidates=$(grep -rlE '(httpx\.(AsyncClient|Client)|aiohttp\.ClientSession|asyncpg\.(create_pool|connect)|requests\.(get|post|put|patch|delete|head|request))[ \t]*\(' \
    --include='*.py' "$services" 2>/dev/null \
    | grep -vE '(/tests?/|/scripts/|/eval/|/benchmark/|/__mocks__/|/fixtures/|/poc|/test_|/live_|/smoke_|/conftest\.py)' \
    || true)
  [[ -n "$py_candidates" ]] && n_cand=$(printf '%s\n' "$py_candidates" | wc -l)

  py_hits=""
  if [[ -n "$py_candidates" ]]; then
    py_hits=$(printf '%s\n' "$py_candidates" \
      | xargs awk -v root="$root/" "$PERF_PY_AWK" 2>/dev/null || true)
  fi
  [[ -n "$py_hits" ]] && n_hits=$(printf '%s\n' "$py_hits" | wc -l)

  if [[ "${PERF_LINT_BASELINE_REGEN:-}" == "1" ]]; then
    printf '%s\n' "$py_hits" | awk -F'\t' 'NF>=3{print $1"\t"$3}' | sort -u
    return 0
  fi

  base_tmp="$(mktemp)"
  if [[ -n "$baseline_file_set" ]]; then
    cat "$baseline_file" > "$base_tmp"
  else
    perf_py_baseline > "$base_tmp"
  fi

  py_new=""
  if [[ -n "$py_hits" ]]; then
    while IFS=$'\t' read -r rel lno snip; do
      [[ -z "$rel" ]] && continue
      fp="$rel"$'\t'"$snip"
      if ! grep -qxF -- "$fp" "$base_tmp"; then
        py_new+="  $rel:$lno: $snip"$'\n'
        n_new=$((n_new + 1))
      fi
    done < <(printf '%s\n' "$py_hits")
  fi

  # ── SHRINK ARM (GT-F5). A baseline row exempts an offender. It dies two ways
  # — the file it names disappears, or the call gets a timeout — and in BOTH the
  # row stops matching any hit this run. Left in place it is not merely dead
  # weight: it silently re-exempts the offender the day the name comes back,
  # waiving PERF-1 without anyone deciding to (the `GTD-16` failure, one gate on).
  local cur_fps dead_rows=""
  cur_fps="$(mktemp)"
  printf '%s\n' "$py_hits" | awk -F'\t' 'NF>=3{print $1"\t"$3}' | sort -u > "$cur_fps"
  while IFS= read -r row; do
    [[ -z "$row" ]] && continue
    if ! grep -qxF -- "$row" "$cur_fps"; then
      dead_rows+="  ${row%%$'\t'*}"$'\n'
    fi
  done < "$base_tmp"
  rm -f "$base_tmp" "$cur_fps"

  if [[ -n "$dead_rows" ]]; then
    echo "[timeout-discipline] FAIL — baseline row(s) matching NO current hit:"
    printf '%s' "$dead_rows"
    echo "  Each exempts nothing today and re-exempts its call the day it returns."
    echo "  Delete the row, or fix the name (PERF_LINT_BASELINE_REGEN=1 reprints the live set)."
    violations=$((violations + 1))
  fi

  # ── RATCHET on the Python leg. Flipping to blocking on the whole backlog is a
  # migration; a ratchet reds on the NEW offender today, which is the part that
  # can regress. Both directions bite: up is a regression, down is a stale
  # constant that would re-admit an offender for free.
  if [[ -n "$py_new" ]]; then
    echo "[timeout-discipline] Python outbound call without a timeout (PERF-1):"
    echo "  → httpx.AsyncClient/Client & aiohttp.ClientSession need timeout=…;"
    echo "    requests.<m>() needs timeout=…; asyncpg pools need command_timeout=…"
    printf '%s' "$py_new"
  fi
  if [[ "$n_new" -gt "$py_expected" ]]; then
    echo "[timeout-discipline] FAIL — $n_new Python offender(s) outside the baseline, ratchet is $py_expected."
    echo "  Add the timeout, or baseline it deliberately (PERF_LINT_BASELINE_REGEN=1)."
    violations=$((violations + 1))
  elif [[ "$n_new" -lt "$py_expected" ]]; then
    echo "[timeout-discipline] FAIL — $n_new Python offender(s) outside the baseline, but the ratchet still says $py_expected."
    echo "  A ratchet that never falls stops being one. Set PY_NEW_BASELINE=$n_new."
    violations=$((violations + 1))
  fi

  if [[ $violations -gt 0 ]]; then
    echo "[timeout-discipline] FAIL — $violations finding(s) (SR06 I16 · PERF-1)"
    return 1
  fi
  echo "[timeout-discipline] PASS — scanned ${n_go} .go, ${n_rs} .rs, ${n_py} .py " \
       "(${n_cand} python candidate file(s), ${n_hits} untimed call(s), ${n_new} outside the baseline)"
  return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
# Drives the REAL `run_lint` over synthetic trees. Every seeded tree carries one
# clean file of EACH language, so the three reach floors stay quiet and a probe
# tests exactly one rule — omitting them made every probe red on the floor,
# which is an arm firing for the right reason in the wrong case.
seed_tree() {
  local d="$1"
  mkdir -p "$d/services/svc/app" "$d/crates/k/src" "$d/contracts/x"
  printf 'package main\n\nfunc main() {}\n' > "$d/services/svc/main.go"
  printf 'pub fn ok() {}\n' > "$d/crates/k/src/lib.rs"
  printf 'package x\n' > "$d/contracts/x/y.go"
  # a python candidate WITH a timeout: the leg has a subject and must stay quiet
  printf 'import httpx\n_c = httpx.AsyncClient(timeout=5)\n' > "$d/services/svc/app/client.py"
}

selftest() {
  local failures=0

  # probe <name> <want_rc> <setup-fn> [baseline_file_arg...] — setup receives the
  # tree root; extra args after the setup name are passed to run_lint.
  probe() {
    local name="$1" want="$2" setup="$3"; shift 3
    local d got
    d="$(mktemp -d)"
    seed_tree "$d"
    "$setup" "$d"
    set +e
    if [[ $# -eq 0 ]]; then
      run_lint "$d" >/dev/null 2>&1
    else
      run_lint "$d" "$@" >/dev/null 2>&1
    fi
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

  s_none() { :; }
  s_go_httpget()   { printf 'package a\nfunc f(){ http.Get("http://x") }\n' > "$1/services/svc/a.go"; }
  s_go_httpget_t() { printf 'package a\nfunc f(){ http.Get("http://x") }\n' > "$1/services/svc/a_test.go"; }
  s_go_dbexec()    { printf 'package a\nfunc f(){ db.Exec("UPDATE t SET x=1") }\n' > "$1/services/svc/a.go"; }
  s_go_dbexec_ctx() { printf 'package a\nfunc f(){ db.ExecContext(ctx, "UPDATE t SET x=1") }\n' > "$1/services/svc/a.go"; }
  s_rs_reqwest()   { printf 'pub async fn f(){ let _ = reqwest::get("http://x").await; }\n' > "$1/crates/k/src/b.rs"; }
  s_rs_builder()   { printf 'pub fn f(){ let _ = reqwest::Client::builder().timeout(d).build(); }\n' > "$1/crates/k/src/b.rs"; }
  s_py_untimed()   { printf 'import httpx\n_c = httpx.AsyncClient()\n' > "$1/services/svc/app/bad.py"; }
  s_py_multiline() { printf 'import httpx\n_c = httpx.AsyncClient(\n    base_url="http://x",\n    headers={},\n)\n' > "$1/services/svc/app/bad.py"; }
  s_py_multiline_t() { printf 'import httpx\n_c = httpx.AsyncClient(\n    base_url="http://x",\n    timeout=5,\n)\n' > "$1/services/svc/app/bad.py"; }
  s_py_in_tests()  { mkdir -p "$1/services/svc/tests"; printf 'import httpx\n_c = httpx.AsyncClient()\n' > "$1/services/svc/tests/bad.py"; }
  # the file the baseline row names still EXISTS — the call in it got a timeout,
  # so the row's reason expired rather than its subject vanishing
  s_py_fixed()     { printf 'import httpx\n_c = httpx.AsyncClient(timeout=5)\n' > "$1/services/svc/app/bad.py"; }
  s_no_services()  { rm -rf "$1/services"; }
  s_no_rust()      { rm -rf "$1/crates"; }
  s_no_go()        { rm -f "$1/services/svc/main.go" "$1/contracts/x/y.go"; }

  # An empty baseline file: `${2+x}` must see it as SET, or the probe silently
  # runs against the production list (GTD-17).
  local empty_base live_base ghost_base
  empty_base="$(mktemp)"; : > "$empty_base"
  live_base="$(mktemp)"
  printf 'services/svc/app/bad.py\t_c = httpx.AsyncClient()\n' > "$live_base"
  ghost_base="$(mktemp)"
  printf 'services/svc/app/vanished.py\t_c = httpx.AsyncClient()\n' > "$ghost_base"

  echo "timeout-discipline-lint --self-test"

  probe "a clean tree passes" 0 s_none "$empty_base" 0

  # Go leg
  probe "http.Get fails" 1 s_go_httpget "$empty_base" 0
  probe "...but http.Get in a _test.go does not" 0 s_go_httpget_t "$empty_base" 0
  probe "db.Exec with a SQL literal fails" 1 s_go_dbexec "$empty_base" 0
  probe "...but db.ExecContext does not" 0 s_go_dbexec_ctx "$empty_base" 0

  # Rust leg
  probe "reqwest::get fails" 1 s_rs_reqwest "$empty_base" 0
  probe "...but Client::builder().timeout() does not" 0 s_rs_builder "$empty_base" 0

  # Python leg + the ratchet
  probe "an untimed httpx client is a new offender" 1 s_py_untimed "$empty_base" 0
  probe "...and passes when the ratchet expects it" 0 s_py_untimed "$empty_base" 1
  probe "...and passes when the BASELINE holds it" 0 s_py_untimed "$live_base" 0
  probe "a MULTILINE untimed constructor is caught" 1 s_py_multiline "$empty_base" 0
  probe "...but not when a later line sets timeout=" 0 s_py_multiline_t "$empty_base" 0
  probe "an untimed client under tests/ is excluded" 0 s_py_in_tests "$empty_base" 0
  probe "the ratchet reds when the count FALLS below it" 1 s_none "$empty_base" 1

  # Shrink arm — a row dies two ways, and both must red.
  probe "a baseline row whose FILE is gone fails" 1 s_none "$ghost_base" 0
  probe "a baseline row whose call was FIXED fails" 1 s_py_fixed "$live_base" 0

  # Reach floors — one per walk.
  probe "no services/ tree is misuse, not a pass" 2 s_no_services "$empty_base" 0
  probe "no rust anywhere is misuse, not a pass" 2 s_no_rust "$empty_base" 0
  probe "no go anywhere is misuse, not a pass" 2 s_no_go "$empty_base" 0

  rm -f "$empty_base" "$live_base" "$ghost_base"

  if [[ $failures -gt 0 ]]; then
    echo "timeout-discipline-lint --self-test: $failures rule(s) did not behave"
    return 2
  fi
  echo "timeout-discipline-lint --self-test: every rule bites, and none cries wolf"
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
