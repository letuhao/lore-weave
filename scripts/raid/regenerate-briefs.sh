#!/usr/bin/env bash
# regenerate-briefs — B4 wrapper: re-runs brief-generator after CYCLE_DECOMPOSITION
# or OPEN_QUESTIONS_LOCKED changes; then validates all briefs.
#
# Usage: regenerate-briefs.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "[regenerate] running brief-generator (drift-checked)"
python3 "$REPO_ROOT/scripts/raid/brief-generator.py"

echo "[regenerate] validating all briefs"
bash "$REPO_ROOT/scripts/raid/brief-structure-validator.sh" --all

echo "[regenerate] done"
