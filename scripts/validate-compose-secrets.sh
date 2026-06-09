#!/usr/bin/env bash
# CI/deploy guard: reject weak INTERNAL_SERVICE_TOKEN in prod overlay.
set -euo pipefail

if [[ "${INTERNAL_SERVICE_TOKEN:-}" == "dev_internal_token" ]]; then
  echo "INTERNAL_SERVICE_TOKEN must not be dev_internal_token in prod" >&2
  exit 1
fi
if [[ -n "${INTERNAL_SERVICE_TOKEN:-}" && ${#INTERNAL_SERVICE_TOKEN} -lt 32 ]]; then
  echo "INTERNAL_SERVICE_TOKEN must be >= 32 characters" >&2
  exit 1
fi
if [[ -n "${JWT_SECRET:-}" && -n "${INTERNAL_SERVICE_TOKEN:-}" && "$JWT_SECRET" == "$INTERNAL_SERVICE_TOKEN" ]]; then
  echo "JWT_SECRET and INTERNAL_SERVICE_TOKEN must be different" >&2
  exit 1
fi
echo "compose secrets OK"
