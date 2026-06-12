#!/usr/bin/env sh
# SUPERSEDED by scripts/ai-provider-gate.py (cross-platform; broader coverage:
# Python + JS/TS + Go provider SDKs, AND hardcoded model names, with an
# allowlist + DEFERRED tracking). Kept as a stable entrypoint for any CI that
# already calls this name — it now delegates to the Python gate.
#
# Run manually:   sh scripts/lint-no-direct-llm-imports.sh
PY=python
command -v python >/dev/null 2>&1 || PY=python3
exec "$PY" "$(cd "$(dirname "$0")" && pwd)/ai-provider-gate.py" "$@"
