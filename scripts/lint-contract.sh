#!/usr/bin/env sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/contracts/api/identity/v1"
exec npx --yes @stoplight/spectral-cli lint openapi.yaml
