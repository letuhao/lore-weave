#!/usr/bin/env bash
# prod-isolation-lint — B5 enforcement
# Per RAID_WORKFLOW.md §13.5
#
# Refuses any DPS commit / cycle commit that references existing LoreWeave
# prod hostname, prod IPs, or modifies infra/existing-prod/.
#
# Usage: prod-isolation-lint.sh [<commit-sha-or-range>]
#        With no arg, lints staged diff. With sha/range, lints that range.
set -euo pipefail
RANGE="${1:-}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cd "$REPO_ROOT"

# Get the diff content
if [ -z "$RANGE" ]; then
  DIFF="$(git diff --cached -U0 2>/dev/null || true)"
  if [ -z "$DIFF" ]; then
    DIFF="$(git diff -U0 2>/dev/null || true)"
  fi
  FILES="$(git diff --cached --name-only 2>/dev/null; git diff --name-only 2>/dev/null)"
else
  DIFF="$(git diff -U0 "$RANGE" 2>/dev/null || true)"
  FILES="$(git diff --name-only "$RANGE" 2>/dev/null || true)"
fi

VIOLATIONS=()

# (a) Prod hostname mentions in added lines only (lines start with `+` not `+++`)
PROD_HITS="$(printf '%s\n' "$DIFF" | grep -E '^\+[^+]' | grep -iE 'prod\.loreweave\.app|prod-postgres\.loreweave|prod-redis\.loreweave|prod-minio\.loreweave' || true)"
if [ -n "$PROD_HITS" ]; then
  VIOLATIONS+=("prod hostname reference in diff:")
  while IFS= read -r line; do
    VIOLATIONS+=("    $line")
  done <<< "$PROD_HITS"
fi

# (b) Touched existing-prod paths
EXISTING_PROD_FILES="$(printf '%s\n' "$FILES" | grep -E '^infra/existing-prod/|^infra/loreweave-novel-platform/' || true)"
if [ -n "$EXISTING_PROD_FILES" ]; then
  VIOLATIONS+=("touched existing-prod infra paths:")
  while IFS= read -r f; do
    VIOLATIONS+=("    $f")
  done <<< "$EXISTING_PROD_FILES"
fi

if [ "${#VIOLATIONS[@]}" -gt 0 ]; then
  echo "[prod-isolation-lint] VIOLATIONS detected:" >&2
  for v in "${VIOLATIONS[@]}"; do
    echo "  $v" >&2
  done
  mkdir -p "$(dirname "$AUDIT_LOG")"
  esc="$(printf '%s' "${VIOLATIONS[*]}" | tr '\n' ' ' | sed 's/"/\\"/g')"
  echo "{\"ts\":\"$NOW\",\"event\":\"prod_isolation_violation\",\"detail\":\"$esc\"}" >> "$AUDIT_LOG"
  exit 1
fi
echo "[prod-isolation-lint] ok: no prod references"
exit 0
