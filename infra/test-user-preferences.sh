#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — User Preferences Integration Test (BE-TH-01)
#
# Tests user_preferences CRUD through the gateway.
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-user-preferences.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PASS=0
FAIL=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected: $expected, got: $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_not_empty() {
  local label="$1" value="$2"
  if [ -n "$value" ] && [ "$value" != "null" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (was empty or null)"; FAIL=$((FAIL+1))
  fi
}

assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label (HTTP $actual)"; PASS=$((PASS+1))
  else
    red "$label (expected HTTP $expected, got $actual)"; FAIL=$((FAIL+1))
  fi
}

jget() {
  local path="$1"
  node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      try {
        const j=JSON.parse(d);
        const keys='${path}'.slice(1).split('.').filter(Boolean);
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        if(v===undefined||v===null) console.log('');
        else console.log(typeof v==='object'?JSON.stringify(v):v);
      } catch { console.log(''); }
    });
  " 2>/dev/null || echo ""
}

# ── Setup ────────────────────────────────────────────────────────────────────
header "Setup: Register + Login"

UNAME="prefs_integ_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null 2>&1 || true

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Setup: got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# ═══════════════════════════════════════════════════════════════════════════════
header "T01: GET preferences — new user returns empty"

T01=$(curl -s -H "$AUTH" "$GATEWAY/v1/me/preferences")
T01_PREFS=$(echo "$T01" | jget .prefs)
assert_eq "T01 new user prefs is empty object" "{}" "$T01_PREFS"

# ═══════════════════════════════════════════════════════════════════════════════
header "T02: PATCH preferences — set app_theme"

T02=$(curl -s -X PATCH "$GATEWAY/v1/me/preferences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"prefs":{"app_theme":"light"}}')
T02_THEME=$(echo "$T02" | jget .prefs.app_theme)
assert_eq "T02 app_theme set to light" "light" "$T02_THEME"

# ═══════════════════════════════════════════════════════════════════════════════
header "T03: PATCH merge — add reader_preset without losing app_theme"

T03=$(curl -s -X PATCH "$GATEWAY/v1/me/preferences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"prefs":{"reader_preset":"sepia","reader_font_size":18}}')
T03_THEME=$(echo "$T03" | jget .prefs.app_theme)
T03_PRESET=$(echo "$T03" | jget .prefs.reader_preset)
T03_SIZE=$(echo "$T03" | jget .prefs.reader_font_size)
assert_eq "T03 app_theme preserved" "light" "$T03_THEME"
assert_eq "T03 reader_preset set" "sepia" "$T03_PRESET"
assert_eq "T03 reader_font_size set" "18" "$T03_SIZE"

# ═══════════════════════════════════════════════════════════════════════════════
header "T04: GET preferences — reflects all patches"

T04=$(curl -s -H "$AUTH" "$GATEWAY/v1/me/preferences")
T04_THEME=$(echo "$T04" | jget .prefs.app_theme)
T04_PRESET=$(echo "$T04" | jget .prefs.reader_preset)
T04_SIZE=$(echo "$T04" | jget .prefs.reader_font_size)
assert_eq "T04 app_theme" "light" "$T04_THEME"
assert_eq "T04 reader_preset" "sepia" "$T04_PRESET"
assert_eq "T04 reader_font_size" "18" "$T04_SIZE"

# ═══════════════════════════════════════════════════════════════════════════════
header "T05: PATCH overwrite — change app_theme"

T05=$(curl -s -X PATCH "$GATEWAY/v1/me/preferences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"prefs":{"app_theme":"oled"}}')
T05_THEME=$(echo "$T05" | jget .prefs.app_theme)
T05_PRESET=$(echo "$T05" | jget .prefs.reader_preset)
assert_eq "T05 app_theme changed to oled" "oled" "$T05_THEME"
assert_eq "T05 reader_preset still sepia" "sepia" "$T05_PRESET"

# ═══════════════════════════════════════════════════════════════════════════════
header "T06: Auth required"

T06_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/me/preferences")
assert_status "T06 GET without auth returns 401" "401" "$T06_STATUS"

T06B_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/me/preferences" \
  -H "Content-Type: application/json" \
  -d '{"prefs":{"app_theme":"dark"}}')
assert_status "T06 PATCH without auth returns 401" "401" "$T06B_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
header "T07: PATCH validation — empty prefs"

T07_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/me/preferences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{}')
assert_status "T07 empty body returns 400" "400" "$T07_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
printf "\n\033[1m═══ Results ═══\033[0m\n"
printf "\033[32m  PASS: %d\033[0m\n" "$PASS"
if [ "$FAIL" -gt 0 ]; then
  printf "\033[31m  FAIL: %d\033[0m\n" "$FAIL"
  exit 1
else
  printf "\033[32m  FAIL: 0\033[0m\n"
  printf "\033[1;32m  All tests passed!\033[0m\n"
fi
