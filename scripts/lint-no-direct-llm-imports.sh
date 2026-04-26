#!/usr/bin/env sh
# Phase 1e (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Enforces P3 + P4 of
# the refactor plan: services MUST NOT call provider SDKs (litellm,
# openai, anthropic) directly. All LLM operations go through
# provider-registry's /v1/llm/{stream,jobs} via the loreweave_llm SDK.
#
# Allowlist (paths where direct SDK imports are LEGITIMATE):
#   services/provider-registry-service/  — gateway internals, the only
#                                           place provider-SDK calls
#                                           are sanctioned. (Note: the
#                                           gateway today implements
#                                           providers via HTTP directly
#                                           in adapters.go, so this
#                                           allowlist is precautionary.)
#   sdks/python/                          — the SDK itself uses httpx,
#                                           but reserved for future use.
#
# Run manually:
#   sh scripts/lint-no-direct-llm-imports.sh
#
# CI: invoke from any test workflow. Non-zero exit on violation.

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Anchored regex matches:
#   from <pkg>           (with or without trailing import-as / submodule)
#   import <pkg>         (top-level package)
# but NOT:
#   from app.openai_helpers ...
#   import some.openai_thing
PATTERN='^(import|from)[[:space:]]+(litellm|openai|anthropic)([[:space:]]|$|\.)'

# Search areas that need policing.
SEARCH_PATHS="services frontend"

# Allowlist of directory prefixes (relative to repo root) where direct
# SDK imports are sanctioned. Each entry is matched as a path prefix.
ALLOWLIST="services/provider-registry-service/ sdks/python/"

# Exclude directories from the search to keep grep fast and avoid
# vendored / build artefacts triggering false hits.
EXCLUDES="--exclude-dir=node_modules \
          --exclude-dir=__pycache__ \
          --exclude-dir=.pytest_cache \
          --exclude-dir=.venv \
          --exclude-dir=venv \
          --exclude-dir=dist \
          --exclude-dir=build \
          --exclude-dir=.next"

set +e
HITS=$(grep -r -E -n $EXCLUDES \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" \
  "$PATTERN" $SEARCH_PATHS 2>/dev/null)
set -e

if [ -z "$HITS" ]; then
  echo "lint-no-direct-llm-imports: OK (no forbidden imports)"
  exit 0
fi

# Filter out allowlisted paths.
VIOLATIONS=""
echo "$HITS" | while IFS= read -r line; do
  # Format: <path>:<lineno>:<match>
  path="${line%%:*}"
  allowed=0
  for prefix in $ALLOWLIST; do
    case "$path" in
      "$prefix"*) allowed=1; break ;;
    esac
  done
  if [ $allowed -eq 0 ]; then
    echo "$line"
  fi
done > /tmp/lint-llm-violations 2>/dev/null

VIOLATIONS=$(cat /tmp/lint-llm-violations 2>/dev/null || true)
rm -f /tmp/lint-llm-violations

if [ -z "$VIOLATIONS" ]; then
  echo "lint-no-direct-llm-imports: OK (allowlisted hits only)"
  exit 0
fi

echo "lint-no-direct-llm-imports: FAIL"
echo ""
echo "Direct provider-SDK imports are forbidden outside the gateway."
echo "Use the loreweave_llm SDK instead — see"
echo "  contracts/api/llm-gateway/v1/openapi.yaml"
echo "  sdks/python/README.md"
echo "  docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md"
echo ""
echo "Offenders:"
echo "$VIOLATIONS"
echo ""
exit 1
