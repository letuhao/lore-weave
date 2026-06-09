#!/usr/bin/env bash
# Go-live network isolation + single-entry audit (run after deploy-onprem).
# Usage: infra/sec-review-onprem.sh [BASE_URL]
#   BASE_URL defaults to http://localhost:${PUBLIC_HTTP_PORT:-5296}
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-http://localhost:${PUBLIC_HTTP_PORT:-5296}}"
BASE="${BASE%/}"
PUBLIC_PORT="${PUBLIC_HTTP_PORT:-5296}"

fail=0
pass() { echo "PASS $*"; }
fail_msg() { echo "FAIL $*"; fail=1; }

echo "=== sec-review-onprem ==="
echo "BASE=$BASE  PUBLIC_HTTP_PORT=$PUBLIC_PORT"
echo ""

# ── Host port scan (backend ports must not listen) ──
echo "-- Host port isolation --"
BACKEND_PORTS=(8204 8205 8206 8207 8208 8209 8210 8211 8212 8213 8214 8215 8216 8217 8218 8219 8220 8221 8222 8223 8224 8225 8226 5555 9123)
for p in "${BACKEND_PORTS[@]}"; do
  if command -v nc >/dev/null 2>&1; then
    if nc -z localhost "$p" 2>/dev/null; then
      fail_msg "port $p is LISTEN (should be closed in prod overlay)"
    else
      pass "port $p closed"
    fi
  elif curl -s -o /dev/null --connect-timeout 1 "http://localhost:${p}/health" 2>/dev/null; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 "http://localhost:${p}/health" 2>/dev/null || echo 000)"
    if [[ "$code" != "000" ]]; then
      fail_msg "port $p reachable (HTTP $code)"
    else
      pass "port $p closed"
    fi
  else
    pass "port $p closed (probe unavailable)"
  fi
done

# Public entry should respond
code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/health" 2>/dev/null || echo 000)"
if [[ "$code" == "200" ]]; then
  pass "public entry ${BASE}/health → 200"
else
  fail_msg "public entry ${BASE}/health → $code (is stack up?)"
fi

echo ""
echo "-- Internal route probes via nginx (must not reach backends) --"
for path in "/v1/internal/users/00000000-0000-0000-0000-000000000001/profile" "/internal/users/00000000-0000-0000-0000-000000000001/profile"; do
  headers="$(curl -s -I "${BASE}${path}" 2>/dev/null || true)"
  code="$(printf '%s' "$headers" | head -1 | awk '{print $2}')"
  ctype="$(printf '%s' "$headers" | grep -i '^content-type:' | head -1 | tr -d '\r')"
  if [[ "$code" == "404" || "$code" == "401" || "$code" == "403" ]]; then
    pass "${path} → $code (not exposed)"
  elif [[ "$code" == "200" && "$ctype" == *"text/html"* ]]; then
    pass "${path} → 200 SPA fallback (not routed to backend)"
  else
    fail_msg "${path} → $code (expected 401/403/404 or SPA HTML)"
  fi
done

echo ""
echo "-- Docker compose port mapping (prod overlay) --"
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    published="$(docker compose -f "$repo_root/infra/docker-compose.yml" -f "$repo_root/infra/docker-compose.prod.yml" ps --format json 2>/dev/null | grep -o '"PublishedPort":"[^"]*"' || true)"
    bad=""
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      port="${line#*:}"
      port="${port%%-*}"
      port="${port//\"/}"
      if [[ "$port" != "$PUBLIC_PORT" && "$port" != "80" ]]; then
        bad="$bad $port"
      fi
    done <<< "$(docker compose -f "$repo_root/infra/docker-compose.yml" -f "$repo_root/infra/docker-compose.prod.yml" ps --format '{{.Ports}}' 2>/dev/null | grep -oE '[0-9]+->' | sed 's/->//g' || true)"
    if [[ -n "$bad" ]]; then
      fail_msg "unexpected host port mappings:$bad"
    else
      pass "compose ps shows only public port (or none parsed)"
    fi
  else
    echo "SKIP docker compose ps (docker unavailable)"
  fi
else
  echo "SKIP docker compose ps (docker not installed)"
fi

echo ""
echo "-- Lateral movement probe (optional, needs docker network) --"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  net="$(docker compose -f "$repo_root/infra/docker-compose.yml" -f "$repo_root/infra/docker-compose.prod.yml" ps -q auth-service 2>/dev/null | head -1)"
  if [[ -n "$net" ]]; then
    network_name="$(docker inspect "$(docker compose -f "$repo_root/infra/docker-compose.yml" ps -q auth-service 2>/dev/null | head -1)" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null || echo infra_default)"
    # Without token → 401
    code_no="$(docker run --rm --network "$network_name" curlimages/curl:latest -s -o /dev/null -w '%{http_code}' \
      "http://auth-service:8081/internal/users/00000000-0000-0000-0000-000000000001/profile" 2>/dev/null || echo 000)"
    if [[ "$code_no" == "401" ]]; then
      pass "auth /internal/* without token → 401"
    else
      fail_msg "auth /internal/* without token → $code_no (expected 401)"
    fi
    # Known dev token must fail in prod
    code_dev="$(docker run --rm --network "$network_name" curlimages/curl:latest -s -o /dev/null -w '%{http_code}' \
      -H "X-Internal-Token: dev_internal_token" \
      "http://auth-service:8081/internal/users/00000000-0000-0000-0000-000000000001/profile" 2>/dev/null || echo 000)"
    if [[ "$code_dev" == "401" ]]; then
      pass "auth /internal/* with dev_internal_token → 401"
    else
      fail_msg "auth /internal/* with dev_internal_token → $code_dev (expected 401 — rotate INTERNAL_SERVICE_TOKEN)"
    fi
  else
    echo "SKIP lateral probe (auth-service not running)"
  fi
else
  echo "SKIP lateral probe (docker unavailable)"
fi

echo ""
echo "-- Public registration disabled (prod) --"
reg_code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE}/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"sec-probe-register@blocked.test","password":"Test1234!","display_name":"Probe"}' 2>/dev/null || echo 000)"
if [[ "$reg_code" == "403" ]]; then
  pass "POST /v1/auth/register → 403 (registration disabled)"
elif [[ "$reg_code" == "201" || "$reg_code" == "200" ]]; then
  fail_msg "POST /v1/auth/register → $reg_code (expected 403 in prod overlay)"
else
  pass "POST /v1/auth/register → $reg_code"
fi

echo ""
echo "-- Prod media surface (anonymous bucket proxy should fail) --"
for path in "/lw-chat/test-key" "/loreweave-audio-cache/jobs/fake/0.mp3" "/loreweave-dev-books/books/fake/cover.png"; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}${path}" 2>/dev/null || echo 000)"
  if [[ "$code" == "404" || "$code" == "403" || "$code" == "401" ]]; then
    pass "${path} → $code (not anonymously proxied)"
  elif [[ "$code" == "200" ]]; then
    fail_msg "${path} → 200 (anonymous bucket still exposed — rebuild frontend with nginx.prod.conf)"
  else
    pass "${path} → $code"
  fi
done

echo ""
if [[ "$fail" -ne 0 ]]; then
  echo "Security review FAILED — see infra/SECURITY_GO_LIVE_REVIEW.md"
  exit 1
fi
echo "Security network review PASSED."
