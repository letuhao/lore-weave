#!/usr/bin/env bash
# On-prem / ngrok-first deploy: full stack, single public port (default :5296).
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
infra_dir="$repo_root/infra"
env_file="$infra_dir/.env"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file — copy from infra/.env.example and set JWT_SECRET (>= 32 chars)." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$env_file"

if [[ -z "${JWT_SECRET:-}" ]]; then
  echo "JWT_SECRET must be set in infra/.env (>= 32 characters)." >&2
  exit 1
fi
if [[ ${#JWT_SECRET} -lt 32 ]]; then
  echo "JWT_SECRET must be at least 32 characters." >&2
  exit 1
fi

if [[ -z "${INTERNAL_SERVICE_TOKEN:-}" ]]; then
  echo "INTERNAL_SERVICE_TOKEN must be set in infra/.env (>= 32 characters, different from JWT_SECRET)." >&2
  exit 1
fi
if [[ ${#INTERNAL_SERVICE_TOKEN} -lt 32 ]]; then
  echo "INTERNAL_SERVICE_TOKEN must be at least 32 characters." >&2
  exit 1
fi
if [[ "$INTERNAL_SERVICE_TOKEN" == "dev_internal_token" ]]; then
  echo "INTERNAL_SERVICE_TOKEN must not be the dev default (dev_internal_token)." >&2
  exit 1
fi
if [[ "$JWT_SECRET" == "$INTERNAL_SERVICE_TOKEN" ]]; then
  echo "JWT_SECRET and INTERNAL_SERVICE_TOKEN must be different." >&2
  exit 1
fi

PUBLIC_HTTP_PORT="${PUBLIC_HTTP_PORT:-5296}"
export PUBLIC_HTTP_PORT

bash "$repo_root/scripts/validate-compose-secrets.sh"

echo "[deploy-onprem] Building stack (git SHA labels)..."
"$repo_root/scripts/build-stack.sh"

echo "[deploy-onprem] Starting prod overlay on host port $PUBLIC_HTTP_PORT..."
cd "$infra_dir"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo ""
echo "Stack is up. Public entry: http://localhost:${PUBLIC_HTTP_PORT}"
echo ""
echo "Next steps (ngrok):"
echo "  1. ngrok http ${PUBLIC_HTTP_PORT}"
echo "  2. Copy the HTTPS URL into infra/.env as PUBLIC_APP_URL=..."
echo "  3. Re-run: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
echo "     (recreates services that embed PUBLIC_APP_URL / MINIO_EXTERNAL_URL)"
echo ""
echo "Smoke: infra/smoke-onprem.sh http://localhost:${PUBLIC_HTTP_PORT}"
echo "Docs:  infra/ON_PREM_DEPLOY.md"
