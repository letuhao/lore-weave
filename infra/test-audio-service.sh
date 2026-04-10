#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Audio Service Integration Test
#
# Tests the gateway audio proxy routes + mock audio service.
#
# Prerequisites:
#   docker compose --profile audio up -d
#   (or AUDIO_SERVICE_URL=http://localhost:8600 docker compose up -d)
#
# Usage: bash infra/test-audio-service.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
MOCK="http://localhost:8600"
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

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -q "$needle"; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected to contain: $needle)"; FAIL=$((FAIL+1))
  fi
}

# ── Check mock service is running ─────────────────────────────────────
header "Pre-flight: Mock Audio Service"

HEALTH=$(curl -s -w "\n%{http_code}" "$MOCK/health" 2>/dev/null || echo -e "\n000")
HEALTH_CODE=$(echo "$HEALTH" | tail -1)
if [ "$HEALTH_CODE" != "200" ]; then
  red "Mock audio service not running at $MOCK (HTTP $HEALTH_CODE)"
  echo "Start it with: docker compose --profile audio up -d"
  echo "Or: cd infra/mock-audio-service && pip install -r requirements.txt && uvicorn main:app --port 8600"
  exit 1
fi
green "Mock audio service running"

# ── Get auth token ────────────────────────────────────────────────────
header "Setup: Authenticate"

TOKEN=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"letuhao1994@gmail.com","password":"Ab.0914113903"}' \
  | python -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  red "Login failed"
  exit 1
fi
green "Logged in"

# ═══════════════════════════════════════════════════════════════════════
header "Section A: Direct Mock Service Tests"
# ═══════════════════════════════════════════════════════════════════════

# T01: Health check
RESP=$(curl -s -w "\n%{http_code}" "$MOCK/health")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_eq "T01: Health returns 200" "200" "$HTTP"
assert_contains "T02: Health body has status" "ok" "$BODY"

# T03: Models list
RESP=$(curl -s "$MOCK/v1/models" -H "Authorization: Bearer test")
assert_contains "T03: Models list has mock-tts-v1" "mock-tts-v1" "$RESP"
assert_contains "T04: Models list has mock-stt-v1" "mock-stt-v1" "$RESP"

# T05: Voices list
RESP=$(curl -s "$MOCK/v1/voices" -H "Authorization: Bearer test")
assert_contains "T05: Voices has alloy" "alloy" "$RESP"
assert_contains "T06: Voices has nova" "nova" "$RESP"

# T07: TTS — generates audio
RESP=$(curl -s -w "\n%{http_code}" -o /tmp/lw-test-tts.wav \
  -X POST "$MOCK/v1/audio/speech" \
  -H "Authorization: Bearer test" \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-tts-v1","voice":"alloy","input":"Hello world test","response_format":"wav"}')
HTTP=$(echo "$RESP" | tail -1)
assert_eq "T07: TTS returns 200" "200" "$HTTP"
SIZE=$(stat -c%s /tmp/lw-test-tts.wav 2>/dev/null || stat -f%z /tmp/lw-test-tts.wav 2>/dev/null || echo "0")
if [ "$SIZE" -gt 100 ]; then
  green "T08: TTS audio file has content ($SIZE bytes)"
  PASS=$((PASS+1))
else
  red "T08: TTS audio file too small ($SIZE bytes)"
  FAIL=$((FAIL+1))
fi

# T09: TTS — 401 without auth
RESP=$(curl -s -w "\n%{http_code}" -X POST "$MOCK/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-tts-v1","voice":"alloy","input":"test"}')
HTTP=$(echo "$RESP" | tail -1)
assert_eq "T09: TTS without auth returns 401" "401" "$HTTP"

# T10: STT — transcription
RESP=$(curl -s "$MOCK/v1/audio/transcriptions" \
  -H "Authorization: Bearer test" \
  -F "file=@/tmp/lw-test-tts.wav" \
  -F "model=mock-stt-v1" \
  -F "language=en")
assert_contains "T10: STT returns text field" "Mock transcription" "$RESP"

# T11: STT verbose_json
RESP=$(curl -s "$MOCK/v1/audio/transcriptions" \
  -H "Authorization: Bearer test" \
  -F "file=@/tmp/lw-test-tts.wav" \
  -F "model=mock-stt-v1" \
  -F "response_format=verbose_json")
assert_contains "T11: Verbose JSON has segments" "segments" "$RESP"
assert_contains "T12: Verbose JSON has duration" "duration" "$RESP"

# ═══════════════════════════════════════════════════════════════════════
header "Section B: Gateway Proxy Tests"
# ═══════════════════════════════════════════════════════════════════════

# T13: Gateway proxies TTS
RESP=$(curl -s -w "\n%{http_code}" -o /tmp/lw-test-gw-tts.wav \
  -X POST "$GATEWAY/v1/audio/speech" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-tts-v1","voice":"alloy","input":"Gateway proxy test","response_format":"wav"}')
HTTP=$(echo "$RESP" | tail -1)
if [ "$HTTP" = "200" ]; then
  green "T13: Gateway TTS proxy returns 200"
  PASS=$((PASS+1))
elif [ "$HTTP" = "503" ]; then
  red "T13: Gateway returns 503 — AUDIO_SERVICE_URL not configured in gateway"
  FAIL=$((FAIL+1))
  echo "  Set AUDIO_SERVICE_URL=http://mock-audio-service:8600 in gateway env"
else
  red "T13: Gateway TTS proxy returned $HTTP"
  FAIL=$((FAIL+1))
fi

# T14: Gateway proxies STT
RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$GATEWAY/v1/audio/transcriptions" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/lw-test-tts.wav" \
  -F "model=mock-stt-v1" \
  -F "language=en")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP" = "200" ]; then
  green "T14: Gateway STT proxy returns 200"
  PASS=$((PASS+1))
  assert_contains "T15: Gateway STT has transcription" "Mock transcription" "$BODY"
elif [ "$HTTP" = "503" ]; then
  red "T14: Gateway returns 503 — AUDIO_SERVICE_URL not configured"
  FAIL=$((FAIL+1))
  red "T15: Skipped (gateway not configured)"
  FAIL=$((FAIL+1))
else
  red "T14: Gateway STT proxy returned $HTTP"
  FAIL=$((FAIL+1))
  red "T15: Skipped"
  FAIL=$((FAIL+1))
fi

# T16: Gateway proxies voices
RESP=$(curl -s -w "\n%{http_code}" "$GATEWAY/v1/audio/voices" -H "Authorization: Bearer $TOKEN")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$HTTP" = "200" ]; then
  green "T16: Gateway voices proxy returns 200"
  PASS=$((PASS+1))
  assert_contains "T17: Gateway voices has alloy" "alloy" "$BODY"
elif [ "$HTTP" = "503" ]; then
  red "T16: Gateway returns 503"
  FAIL=$((FAIL+1))
  red "T17: Skipped"
  FAIL=$((FAIL+1))
else
  red "T16: Gateway voices returned $HTTP"
  FAIL=$((FAIL+1))
  red "T17: Skipped"
  FAIL=$((FAIL+1))
fi

# ═══════════════════════════════════════════════════════════════════════
header "Section C: Error Handling"
# ═══════════════════════════════════════════════════════════════════════

# T18: TTS with empty input
RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$MOCK/v1/audio/speech" \
  -H "Authorization: Bearer test" \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-tts-v1","voice":"alloy","input":""}')
HTTP=$(echo "$RESP" | tail -1)
assert_eq "T18: TTS empty input returns 400" "400" "$HTTP"

# T19: TTS with too-long input
LONG_INPUT=$(python -c "print('a' * 5000)")
RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$MOCK/v1/audio/speech" \
  -H "Authorization: Bearer test" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"mock-tts-v1\",\"voice\":\"alloy\",\"input\":\"$LONG_INPUT\"}")
HTTP=$(echo "$RESP" | tail -1)
assert_eq "T19: TTS >4096 chars returns 400" "400" "$HTTP"

# Cleanup
rm -f /tmp/lw-test-tts.wav /tmp/lw-test-gw-tts.wav

# ═══════════════════════════════════════════════════════════════════════
header "RESULTS"
# ═══════════════════════════════════════════════════════════════════════

TOTAL=$((PASS + FAIL))
printf "\n\033[1m%d tests: \033[32m%d passed\033[0m" "$TOTAL" "$PASS"
if [ "$FAIL" -gt 0 ]; then printf ", \033[31m%d failed\033[0m" "$FAIL"; fi
printf "\n\n"

if [ "$FAIL" -gt 0 ]; then exit 1; fi
exit 0
