#!/usr/bin/env bash
# Pre-merge / post-deploy review runner for on-prem single-port work.
# Layer 0: unit tests + compose config (no running stack)
# Layer 1: smoke-onprem (needs stack)
# Layer 2: realtest-onprem (needs stack + auth)
#
# Usage:
#   infra/review-onprem.sh                    # offline checks only
#   infra/review-onprem.sh http://localhost:5296
#   infra/review-onprem.sh https://xxx.ngrok-free.app
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-}"

echo "=== Layer 0: offline (no Docker required) ==="
echo ""

echo "-- BFF unit tests --"
(cd "$repo_root/services/api-gateway-bff" && npm test)

echo ""
echo "-- compose secrets validation --"
bash "$repo_root/scripts/validate-compose-secrets.sh"

echo ""
echo "-- prod compose config --"
if [[ ! -f "$repo_root/infra/.env" ]]; then
  export JWT_SECRET="${JWT_SECRET:-loreweave_local_dev_jwt_secret_change_me_32chars}"
else
  # shellcheck disable=SC1091
  source "$repo_root/infra/.env"
fi
(cd "$repo_root/infra" && docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet)
echo "compose config OK"

if [[ -z "$BASE" ]]; then
  echo ""
  echo "Layer 1/2 skipped (no BASE_URL)."
  echo "After deploy, re-run:"
  echo "  infra/review-onprem.sh http://localhost:\${PUBLIC_HTTP_PORT:-5296}"
  echo "  infra/review-onprem.sh https://your-ngrok-url.ngrok-free.app"
  exit 0
fi

echo ""
echo "=== Layer 1: smoke ($BASE) ==="
bash "$repo_root/infra/smoke-onprem.sh" "$BASE"

echo ""
echo "=== Layer 2: real test ($BASE) ==="
bash "$repo_root/infra/realtest-onprem.sh" "$BASE"

echo ""
if command -v python >/dev/null 2>&1 && [[ -f "$repo_root/scripts/check_stack_freshness.py" ]]; then
  echo "=== Layer 2b: image freshness (optional) ==="
  python "$repo_root/scripts/check_stack_freshness.py" || echo "WARN stack images may be stale — run deploy-onprem with --build"
  echo ""
fi

echo "=== Layer 3: security ($BASE) ==="
bash "$repo_root/infra/sec-review-onprem.sh" "$BASE"
bash "$repo_root/infra/sec-review-idor.sh" "$BASE" || {
  idor_exit=$?
  if [[ "$idor_exit" == "2" ]]; then
    echo "SKIP sec-review-idor (registration disabled — set SEC_REVIEW_* creds in infra/.env)"
  else
    exit "$idor_exit"
  fi
}

echo ""
echo "=== Manual browser checks (see ON_PREM_DEPLOY.md) ==="
echo "  - DevTools Network: /v1/* same origin as page (no :3123)"
echo "  - Private media loads via /v1/books/.../media/object?stream_token=..."
echo "  - Notification bell / WS connects"
