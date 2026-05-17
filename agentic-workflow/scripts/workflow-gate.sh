#!/usr/bin/env bash
# workflow-gate.sh — Thin wrapper around workflow-gate.py
#
# The actual state-machine logic lives in workflow-gate.py (cross-platform,
# no bash escaping). This wrapper exists so existing CLAUDE.md / hooks /
# docs that invoke `./scripts/workflow-gate.sh` keep working.
#
# Why a wrapper instead of the previous all-bash implementation:
# - Prior all-bash impl embedded multi-line `python -c` calls. On Windows
#   pyenv-win, `python3.bat` corrupts multi-line `-c` args, producing
#   spurious "|| goto :error" IndentationErrors. Plain `python` routes
#   through a different shim that preserves newlines correctly.
# - Even with the python-vs-python3 fix, escaping JSON-bearing strings
#   through bash-->python -c was fragile. Native .py removes that class
#   of bug entirely.
#
# Usage: identical to workflow-gate.py — see that file for full CLI.
#   ./scripts/workflow-gate.sh phase build
#   ./scripts/workflow-gate.sh complete build "tests pass"
#   ./scripts/workflow-gate.sh status

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/workflow-gate.py"

if [[ ! -f "$PY_SCRIPT" ]]; then
  echo "ERROR: workflow-gate.py not found at $PY_SCRIPT"
  echo "       The .sh wrapper requires the .py implementation in the same directory."
  exit 1
fi

# Prefer `python` over `python3` because some Windows shims (e.g. pyenv-win's
# python3.bat) corrupt arg passing. Plain `python` routes through a different
# shim that works correctly.
if command -v python &>/dev/null; then
  PYTHON_CMD="python"
elif command -v python3 &>/dev/null; then
  PYTHON_CMD="python3"
else
  echo "ERROR: python or python3 not found. Install Python 3.x."
  exit 1
fi

exec "$PYTHON_CMD" "$PY_SCRIPT" "$@"
