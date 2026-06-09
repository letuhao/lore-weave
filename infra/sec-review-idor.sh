#!/usr/bin/env bash
# IDOR / authz smoke — user B must not access user A's book resources.
# Usage: infra/sec-review-idor.sh [BASE_URL]
set -euo pipefail

BASE="${1:-http://localhost:${PUBLIC_HTTP_PORT:-5296}}"
BASE="${BASE%/}"

fail=0
pass=0

jget() {
  node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);const k='${1}'.slice(1).split('.').filter(Boolean);let v=j;for(const x of k){if(v==null)break;v=v[x]}if(v===undefined||v===null)console.log('');else console.log(typeof v==='object'?JSON.stringify(v):v)}catch{console.log('')}})" 2>/dev/null || echo ""
}

assert_forbidden() {
  local label="$1" code="$2"
  if [[ "$code" == "403" || "$code" == "404" ]]; then
    echo "PASS $label → HTTP $code"
    pass=$((pass + 1))
  else
    echo "FAIL $label → HTTP $code (expected 403 or 404)"
    fail=$((fail + 1))
  fi
}

echo "=== sec-review-idor ==="
echo "BASE=$BASE"
echo ""

login_token() {
  curl -s -X POST "$BASE/v1/auth/login" -H "Content-Type: application/json" \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" | jget .access_token
}

if [[ -n "${SEC_REVIEW_EMAIL_A:-}" && -n "${SEC_REVIEW_PASSWORD_A:-}" ]]; then
  EMAIL_A="$SEC_REVIEW_EMAIL_A"
  EMAIL_B="${SEC_REVIEW_EMAIL_B:-}"
  PASS_A="$SEC_REVIEW_PASSWORD_A"
  PASS_B="${SEC_REVIEW_PASSWORD_B:-}"
  TOKEN_A="$(login_token "$EMAIL_A" "$PASS_A")"
  if [[ -n "$EMAIL_B" && -n "$PASS_B" ]]; then
    TOKEN_B="$(login_token "$EMAIL_B" "$PASS_B")"
  else
    TS="$(date +%s)"
    EMAIL_B="secidor_b_${TS}@test.com"
    REG_B="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/v1/auth/register" -H "Content-Type: application/json" \
      -d "{\"email\":\"$EMAIL_B\",\"password\":\"Test1234!\",\"display_name\":\"Sec B\"}")"
    if [[ "$REG_B" == "403" ]]; then
      echo "FAIL setup — SEC_REVIEW_EMAIL_B/PASSWORD_B required when public registration is disabled" >&2
      exit 1
    fi
    TOKEN_B="$(login_token "$EMAIL_B" "Test1234!")"
  fi
  echo "PASS setup — users A and B via SEC_REVIEW_* credentials"
else
  TS="$(date +%s)"
  EMAIL_A="secidor_a_${TS}@test.com"
  EMAIL_B="secidor_b_${TS}@test.com"
  REG_A="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/v1/auth/register" -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL_A\",\"password\":\"Test1234!\",\"display_name\":\"Sec A\"}")"
  if [[ "$REG_A" == "403" ]]; then
    echo "SKIP IDOR review — public registration disabled. Set SEC_REVIEW_EMAIL_A, SEC_REVIEW_PASSWORD_A," >&2
    echo "  SEC_REVIEW_EMAIL_B, SEC_REVIEW_PASSWORD_B in infra/.env (pre-seeded test users)." >&2
    exit 2
  fi
  curl -s -X POST "$BASE/v1/auth/register" -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL_A\",\"password\":\"Test1234!\",\"display_name\":\"Sec A\"}" >/dev/null
  TOKEN_A="$(login_token "$EMAIL_A" "Test1234!")"
  curl -s -X POST "$BASE/v1/auth/register" -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL_B\",\"password\":\"Test1234!\",\"display_name\":\"Sec B\"}" >/dev/null
  TOKEN_B="$(login_token "$EMAIL_B" "Test1234!")"
  echo "PASS setup — users A and B registered"
fi

if [[ -z "$TOKEN_A" || -z "$TOKEN_B" ]]; then
  echo "FAIL setup — could not obtain tokens (is stack up?)"
  exit 1
fi
pass=$((pass + 1))

BOOK_ID="$(curl -s -X POST "$BASE/v1/books" -H "Authorization: Bearer $TOKEN_A" -H "Content-Type: application/json" \
  -d '{"title":"IDOR Test Book","original_language":"en"}' | jget .book_id)"
if [[ -z "$BOOK_ID" ]]; then
  echo "FAIL setup — user A could not create book"
  exit 1
fi
echo "PASS setup — book_id=$BOOK_ID"
pass=$((pass + 1))

code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN_B" "$BASE/v1/books/$BOOK_ID")"
assert_forbidden "GET /v1/books/{id}" "$code"

code="$(curl -s -o /dev/null -w '%{http_code}' -X PATCH -H "Authorization: Bearer $TOKEN_B" \
  -H "Content-Type: application/json" -d '{"visibility":"public"}' \
  "$BASE/v1/sharing/books/$BOOK_ID")"
assert_forbidden "PATCH /v1/sharing/books/{id}" "$code"

code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN_B" \
  "$BASE/v1/glossary/books/$BOOK_ID/entities")"
assert_forbidden "GET /v1/glossary/books/{id}/entities" "$code"

code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN_B" \
  "$BASE/v1/knowledge/projects?book_id=$BOOK_ID")"
if [[ "$code" == "403" || "$code" == "404" ]]; then
  echo "PASS GET /v1/knowledge/projects?book_id= → HTTP $code"
  pass=$((pass + 1))
elif [[ "$code" == "200" ]]; then
  body="$(curl -s -H "Authorization: Bearer $TOKEN_B" "$BASE/v1/knowledge/projects?book_id=$BOOK_ID")"
  count="$(echo "$body" | jget .items | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);console.log(Array.isArray(j)?j.length:0)}catch{console.log(0)}})" 2>/dev/null || echo 0)"
  if [[ "$count" == "0" ]]; then
    echo "PASS GET /v1/knowledge/projects?book_id= → 200 empty"
    pass=$((pass + 1))
  else
    echo "FAIL GET /v1/knowledge/projects?book_id= → 200 with $count items"
    fail=$((fail + 1))
  fi
else
  echo "FAIL GET /v1/knowledge/projects?book_id= → HTTP $code"
  fail=$((fail + 1))
fi

# Cross-book media object IDOR: B uses own book_id but victim object key
BOOK_B="$(curl -s -X POST "$BASE/v1/books" -H "Authorization: Bearer $TOKEN_B" -H "Content-Type: application/json" \
  -d '{"title":"IDOR B Book","original_language":"en"}' | jget .book_id)"
if [[ -n "$BOOK_B" ]]; then
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN_B" \
    "$BASE/v1/books/$BOOK_B/media/object?key=books/$BOOK_ID/chapters/00000000-0000-0000-0000-000000000001/x.png")"
  if [[ "$code" == "403" || "$code" == "404" ]]; then
    echo "PASS GET media/object cross-book key → HTTP $code"
    pass=$((pass + 1))
  else
    echo "FAIL GET media/object cross-book key → HTTP $code (expected 403/404)"
    fail=$((fail + 1))
  fi
else
  echo "SKIP media/object IDOR (user B book setup failed)"
fi

code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/v1/catalog/books")"
if [[ "$code" == "200" ]]; then
  echo "PASS GET /v1/catalog/books (public) → 200"
  pass=$((pass + 1))
else
  echo "FAIL GET /v1/catalog/books → HTTP $code"
  fail=$((fail + 1))
fi

echo ""
echo "Results: $pass passed, $fail failed"
if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "IDOR review PASSED."
