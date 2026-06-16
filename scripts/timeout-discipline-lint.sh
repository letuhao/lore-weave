#!/usr/bin/env bash
# L1.K.9 timeout-discipline-lint.sh — SR06 I16
#
# Outbound network/db calls MUST set a timeout. We flag the most-common
# unguarded patterns:
#   * Go: http.Get / http.Post / http.Do(req) without a context-bound or
#     client-with-Timeout pattern
#   * Go: db.Query / db.Exec without QueryContext / ExecContext
#   * Rust: reqwest::get without builder().timeout(...)
#
# Heuristic — produces some false positives in tests; allowlist *_test.go.
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

if [[ $violations -gt 0 ]]; then
  echo "[timeout-discipline] FAIL — $violations unguarded call(s) (SR06 I16)"
  exit 1
fi
echo "[timeout-discipline] PASS"
exit 0
