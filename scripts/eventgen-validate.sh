#!/usr/bin/env bash
# scripts/eventgen-validate.sh — L2.G CI gate (RAID cycle 8).
#
# Regenerate every eventgen target into contracts/events/generated/ and fail
# if the working tree shows any drift. This catches:
#   - hand-edited generated files (developer ignored DO NOT EDIT)
#   - stale generation (forgot to re-run after _registry.yaml change)
#   - codegen non-determinism (would surface as spurious diff)
#
# Exit 0 = no drift. Non-zero = drift; CI fails.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

out_dir="contracts/events/generated"

echo "[eventgen-validate] building eventgen tool…"
(cd tools/eventgen && go build -o eventgen .) \
  || { echo "[eventgen-validate] FAIL — eventgen build error"; exit 1; }

echo "[eventgen-validate] regenerating $out_dir…"
./tools/eventgen/eventgen \
  --registry contracts/events/_registry.yaml \
  --events-dir contracts/events \
  --out-dir   "$out_dir" \
  --target    all >/dev/null \
  || { echo "[eventgen-validate] FAIL — eventgen run error"; exit 1; }

# clean up local binary so it doesn't pollute the working tree
rm -f tools/eventgen/eventgen tools/eventgen/eventgen.exe

# git diff --exit-code returns non-zero if anything changed.
if ! git diff --exit-code "$out_dir" >/dev/null 2>&1; then
  echo "[eventgen-validate] FAIL — generated files are out of sync."
  echo "    Run: make eventgen     # then commit the regenerated files"
  echo "    Drift:"
  git diff --stat "$out_dir" || true
  exit 1
fi

echo "[eventgen-validate] PASS — generated files match _registry.yaml"
exit 0
