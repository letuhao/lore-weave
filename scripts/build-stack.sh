#!/usr/bin/env bash
# Build the compose stack with the git SHA + build time stamped into image labels
# (F-LIVE-1 stale-image guard). scripts/check_stack_freshness.py reads the
# org.loreweave.git_sha label to detect a running container that is behind HEAD.
#
# Usage:
#   scripts/build-stack.sh                      # build everything
#   scripts/build-stack.sh knowledge-service    # build one (or more) service(s)
#
# A plain `docker compose build` (without this wrapper) leaves the labels
# 'unknown'; the guard then falls back to its image-timestamp proxy.
set -euo pipefail

GIT_SHA="$(git rev-parse HEAD)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export GIT_SHA BUILD_TIME

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
echo "[build-stack] GIT_SHA=$GIT_SHA  BUILD_TIME=$BUILD_TIME"
cd "$repo_root/infra"
exec docker compose build "$@"
