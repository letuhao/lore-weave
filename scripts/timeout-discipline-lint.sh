#!/usr/bin/env bash
# L1.K.9 timeout-discipline-lint.sh — SR06 I16 · PERF-1
#
# Standard: docs/standards/performance.md › Rules › PERF-1 (Timeouts
# everywhere, all languages). Outbound network/db calls MUST set an explicit
# timeout. We flag the most-common unguarded patterns:
#   * Go:   http.Get / http.Post / http.Do(req) without a context-bound or
#           client-with-Timeout pattern
#   * Go:   db.Query / db.Exec without QueryContext / ExecContext
#   * Rust: reqwest::get without builder().timeout(...)
#   * Python (PERF-1 extension — see the "Python" block below):
#       - httpx.AsyncClient( / httpx.Client( / aiohttp.ClientSession( with no
#         `timeout=` in the (possibly multiline) constructor
#       - requests.<method>( with no `timeout=`
#       - asyncpg.create_pool( / asyncpg.connect( with no statement timeout
#         (`command_timeout=` for a pool, `timeout=` for a connect) — the
#         asyncpg equivalent of "raw execute without a statement timeout"
#
# Heuristic — produces some false positives in tests; test/script/eval files
# are excluded, and a BASELINE of today's known Python offenders is carried so
# the lint passes clean now and flags only NEW violations (mirrors the
# allowlist pattern in scripts/ai-provider-gate.py). Refresh the baseline with:
#     PERF_LINT_BASELINE_REGEN=1 scripts/timeout-discipline-lint.sh
# (prints `relpath<TAB>snippet` fingerprints; paste into perf_py_baseline).
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# Go: http.Get / http.Post / http.Head — all bypass timeout. Bare http.Do
# without an explicit *http.Client{Timeout:...} is also flagged.
hits=$(grep -rnE '(\b|^)http\.(Get|Post|Head|PostForm)\(' \
  --include='*.go' "$repo_root/services" "$repo_root/contracts" 2>/dev/null \
  | grep -vE '_test\.go:' || true)
if [[ -n "$hits" ]]; then
  echo "[timeout-discipline] FAIL — http.{Get,Post,Head,PostForm} bypasses timeout:"
  echo "$hits" | sed 's/^/  /'
  violations=$((violations + 1))
fi

# Go: db.Query / db.Exec without Context (db.QueryContext / db.ExecContext are OK).
# Also accept pgx convention: tx.Exec(ctx, ...) or tx.Exec(r.Context(), ...)
# where the first arg evaluates to a context.Context. The non-acceptable
# pattern is a bare SQL string as first arg (no context):
#   tx.Exec("UPDATE ...", args)
#   tx.Exec(`SELECT ...`)
# Heuristic: flag only when first arg starts with `"` or backtick (SQL literal).
hits=$(grep -rnE '\b(db|tx)\.(Query|Exec)\(("|`)' \
  --include='*.go' "$repo_root/services" "$repo_root/contracts" 2>/dev/null \
  | grep -vE '_test\.go:' \
  || true)
if [[ -n "$hits" ]]; then
  echo "[timeout-discipline] FAIL — db.{Query,Exec} without Context (use QueryContext/ExecContext):"
  echo "$hits" | sed 's/^/  /'
  violations=$((violations + 1))
fi

# Rust: reqwest::get is the no-timeout shortcut
hits=$(grep -rnE 'reqwest::(get|Client::new\(\)\.get)' \
  --include='*.rs' "$repo_root/services" "$repo_root/crates" 2>/dev/null \
  | grep -vE 'mod tests' || true)
if [[ -n "$hits" ]]; then
  echo "[timeout-discipline] FAIL — reqwest::get bypasses timeout:"
  echo "$hits" | sed 's/^/  /'
  violations=$((violations + 1))
fi

# ── Python (PERF-1) ────────────────────────────────────────────────────
# BASELINE of today's known Python offenders (runtime code only; test/script/
# eval files are excluded up-front). Each line is `relpath<TAB>snippet`
# (line-number-free so it survives edits elsewhere in the file). Regenerate
# with PERF_LINT_BASELINE_REGEN=1. Keep sorted.
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
perf_py_awk='
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

# Candidate runtime .py files that reference a trigger token (test/script/eval
# excluded — those are dev tooling, not served request paths).
py_candidates=$(grep -rlE '(httpx\.(AsyncClient|Client)|aiohttp\.ClientSession|asyncpg\.(create_pool|connect)|requests\.(get|post|put|patch|delete|head|request))[ \t]*\(' \
  --include='*.py' "$repo_root/services" 2>/dev/null \
  | grep -vE '(/tests?/|/scripts/|/eval/|/benchmark/|/__mocks__/|/fixtures/|/poc|/test_|/live_|/smoke_|/conftest\.py)' \
  || true)

if [[ -n "$py_candidates" ]]; then
  py_hits=$(printf '%s\n' "$py_candidates" \
    | xargs awk -v root="$repo_root/" "$perf_py_awk" 2>/dev/null || true)

  if [[ "${PERF_LINT_BASELINE_REGEN:-}" == "1" ]]; then
    # Print current fingerprints (rel<TAB>snippet), sorted+unique, for pasting.
    printf '%s\n' "$py_hits" | awk -F'\t' 'NF>=3{print $1"\t"$3}' | sort -u
    exit 0
  fi

  py_new=""
  if [[ -n "$py_hits" ]]; then
    base_tmp="$(mktemp)"
    perf_py_baseline > "$base_tmp"
    while IFS=$'\t' read -r rel lno snip; do
      [[ -z "$rel" ]] && continue
      fp="$rel"$'\t'"$snip"
      if ! grep -qxF -- "$fp" "$base_tmp"; then
        py_new+="  $rel:$lno: $snip"$'\n'
      fi
    done < <(printf '%s\n' "$py_hits")
    rm -f "$base_tmp"
  fi

  if [[ -n "$py_new" ]]; then
    # ADVISORY (not blocking): the Python extension is new (PERF-1) and asyncpg
    # `command_timeout=` is a nuanced fix (too-low a value fails long queries), so
    # new-offender findings WARN but do not fail the gate — the Go/Rust legs above
    # stay blocking. Track these in the perf backlog; flip to blocking once the
    # asyncpg-timeout debt is addressed + the baseline is regenerated
    # (PERF_LINT_BASELINE_REGEN=1).
    echo "[timeout-discipline] WARN (advisory) — Python outbound call without a timeout (PERF-1):"
    echo "  → httpx.AsyncClient/Client & aiohttp.ClientSession need timeout=…;"
    echo "    requests.<m>() needs timeout=…; asyncpg pools need command_timeout=…"
    printf '%s' "$py_new"
  fi
elif [[ "${PERF_LINT_BASELINE_REGEN:-}" == "1" ]]; then
  exit 0
fi

if [[ $violations -gt 0 ]]; then
  echo "[timeout-discipline] FAIL — $violations unguarded call(s) (SR06 I16 · PERF-1)"
  exit 1
fi
echo "[timeout-discipline] PASS"
exit 0
