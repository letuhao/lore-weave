#!/usr/bin/env bash
# Smoke-check single-port on-prem entry (nginx → BFF → services).
# Usage: infra/smoke-onprem.sh [BASE_URL]
#   BASE_URL defaults to http://localhost:${PUBLIC_HTTP_PORT:-5296}
set -euo pipefail

BASE="${1:-http://localhost:${PUBLIC_HTTP_PORT:-5296}}"
BASE="${BASE%/}"

fail=0
check() {
  local name="$1"
  local path="$2"
  local expect="${3:-}"
  local code
  code="$(curl -s -o /tmp/lw-smoke-body.txt -w '%{http_code}' "${BASE}${path}" || true)"
  if [[ "$code" == "000" ]]; then
    echo "FAIL $name — connection refused (${BASE}${path})"
    fail=1
    return
  fi
  if [[ -n "$expect" && "$code" != "$expect" ]]; then
    echo "FAIL $name — expected HTTP $expect, got $code (${path})"
    fail=1
    return
  fi
  echo "OK   $name — HTTP $code ${path}"
}

echo "Smoke base: $BASE"
echo ""

check "gateway health" "/health" "200"
check "book route (no token)" "/v1/books" "401"
check "catalog public" "/v1/catalog/books" "200"
check "llm gateway route exists" "/v1/llm/jobs/fake-id" "401"
check "languagetool upstream" "/languagetool/v2/languages" "200"
check "SPA index" "/" "200"

rm -f /tmp/lw-smoke-body.txt

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "Some checks failed. Is the stack healthy? docker compose ps"
  exit 1
fi

echo ""
echo "All smoke checks passed."
