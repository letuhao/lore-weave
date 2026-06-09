#!/usr/bin/env bash
# Real integration test through the single public port (auth + API round-trip).
# Works for localhost:5296, ngrok URL, or any future domain — pass BASE_URL.
#
# Usage:
#   infra/realtest-onprem.sh [BASE_URL]
#   BASE_URL=https://xxx.ngrok-free.app infra/realtest-onprem.sh
#
# Optional env (required when ALLOW_PUBLIC_REGISTRATION=false in prod):
#   REALTEST_EMAIL REALTEST_PASSWORD
#   SEC_REVIEW_EMAIL_A SEC_REVIEW_PASSWORD_A (+ B) for infra/sec-review-idor.sh
set -euo pipefail

BASE="${1:-http://localhost:${PUBLIC_HTTP_PORT:-5296}}"
BASE="${BASE%/}"

PASS=0
FAIL=0
green() { printf "\033[32mOK  %s\033[0m\n" "$1"; PASS=$((PASS+1)); }
red()   { printf "\033[31mFAIL %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); }

curl_json() {
  curl -sS -H "Content-Type: application/json" "$@"
}

echo "Real test base: $BASE"
echo ""

# ── 1. Smoke prerequisites ───────────────────────────────────────────────────
code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/health" || echo 000)"
if [[ "$code" != "200" ]]; then
  echo "Stack not reachable at ${BASE}/health (HTTP $code). Start deploy first." >&2
  exit 1
fi
green "health reachable"

# ── 2. Auth: register or login ───────────────────────────────────────────────
if [[ -n "${REALTEST_EMAIL:-}" && -n "${REALTEST_PASSWORD:-}" ]]; then
  EMAIL="$REALTEST_EMAIL"
  PASSWORD="$REALTEST_PASSWORD"
  LOGIN_BODY="$(curl_json -X POST "${BASE}/v1/auth/login" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"
else
  TS="$(date +%s)"
  EMAIL="onprem-realtest-${TS}@loreweave.local"
  PASSWORD="OnPremTest2026!"
  NAME="OnPrem Realtest"

  REG_CODE="$(curl -s -o /tmp/lw-realtest-reg.json -w '%{http_code}' \
    -X POST "${BASE}/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\",\"name\":\"${NAME}\"}" || echo 000)"

  if [[ "$REG_CODE" == "201" || "$REG_CODE" == "200" ]]; then
    ACCESS="$(node -pe "try{JSON.parse(require('fs').readFileSync('/tmp/lw-realtest-reg.json','utf8')).access_token}catch(e){''}" 2>/dev/null || true)"
    REFRESH="$(node -pe "try{JSON.parse(require('fs').readFileSync('/tmp/lw-realtest-reg.json','utf8')).refresh_token}catch(e){''}" 2>/dev/null || true)"
    if [[ -n "$ACCESS" ]]; then
      green "register new user ($EMAIL)"
    else
      LOGIN_BODY="$(curl_json -X POST "${BASE}/v1/auth/login" \
        -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"
      ACCESS="$(node -pe "try{JSON.parse(process.argv[1]).access_token}catch(e){''}" "$LOGIN_BODY")"
      REFRESH="$(node -pe "try{JSON.parse(process.argv[1]).refresh_token}catch(e){''}" "$LOGIN_BODY")"
      if [[ -n "$ACCESS" ]]; then
        green "register + login new user ($EMAIL)"
      else
        red "register ok but login failed"
      fi
    fi
  else
    LOGIN_BODY="$(curl_json -X POST "${BASE}/v1/auth/login" \
      -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"
    ACCESS="$(node -pe "try{JSON.parse(process.argv[1]).access_token}catch(e){''}" "$LOGIN_BODY")"
    REFRESH="$(node -pe "try{JSON.parse(process.argv[1]).refresh_token}catch(e){''}" "$LOGIN_BODY")"
    if [[ -n "$ACCESS" ]]; then
      green "login after register conflict"
    elif [[ "$REG_CODE" == "403" ]]; then
      red "register disabled (HTTP 403) — set REALTEST_EMAIL and REALTEST_PASSWORD in infra/.env"
    else
      red "register/login failed (register HTTP $REG_CODE)"
    fi
  fi
fi

if [[ -z "${ACCESS:-}" && -n "${LOGIN_BODY:-}" ]]; then
  ACCESS="$(node -pe "try{JSON.parse(process.argv[1]).access_token}catch(e){''}" "$LOGIN_BODY" 2>/dev/null || true)"
fi
if [[ -z "$ACCESS" ]]; then
  red "no access_token from auth"
else
  green "obtained access_token"
fi

# ── 3. Authenticated API through same origin ─────────────────────────────────
if [[ -n "$ACCESS" ]]; then
  PROF_CODE="$(curl -s -o /tmp/lw-realtest-prof.json -w '%{http_code}' \
    -H "Authorization: Bearer ${ACCESS}" "${BASE}/v1/account/profile" || echo 000)"
  if [[ "$PROF_CODE" == "200" ]]; then
    green "GET /v1/account/profile"
  else
    red "GET /v1/account/profile (HTTP $PROF_CODE)"
  fi

  BOOKS_CODE="$(curl -s -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${ACCESS}" "${BASE}/v1/books" || echo 000)"
  if [[ "$BOOKS_CODE" == "200" ]]; then
    green "GET /v1/books (authenticated)"
  else
    red "GET /v1/books (HTTP $BOOKS_CODE)"
  fi

  NOTIF_CODE="$(curl -s -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${ACCESS}" "${BASE}/v1/notifications/unread-count" || echo 000)"
  if [[ "$NOTIF_CODE" == "200" ]]; then
    green "GET /v1/notifications/unread-count"
  else
    red "GET /v1/notifications/unread-count (HTTP $NOTIF_CODE)"
  fi
fi

# ── 4. Same-origin sanity (built JS must not hardcode :3123) ───────────────────
INDEX="$(curl -s "${BASE}/" || true)"
if echo "$INDEX" | grep -q 'localhost:3123'; then
  red "SPA bundle references localhost:3123 — rebuild frontend with VITE_API_BASE=\"\""
else
  green "SPA index has no localhost:3123 leak"
fi

# ── 5. Grammar path via nginx (not BFF) ──────────────────────────────────────
LT_CODE="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/languagetool/v2/languages" || echo 000)"
if [[ "$LT_CODE" == "200" ]]; then
  green "languagetool via nginx"
else
  red "languagetool (HTTP $LT_CODE)"
fi

rm -f /tmp/lw-realtest-reg.json /tmp/lw-realtest-prof.json

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi
echo "Real test passed."
