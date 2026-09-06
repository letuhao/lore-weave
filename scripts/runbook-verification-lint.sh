#!/usr/bin/env bash
# scripts/runbook-verification-lint.sh — L7.B.17 (RAID cycle 35)
#
# A THIN WRAPPER around `runbook-verification-lint.py`, which holds the whole
# implementation and the `--self-test`. Same shape as
# `migration-idempotency-validator.sh` → its `.py`, and it stays the entry point
# because CI invokes it by name (foundation-ci.yml, lint.yml, and the
# gate-wiring runner).
#
# WHY THE LOGIC MOVED (2026-08-12, GT8d)
# --------------------------------------
# The checker was a `python3 - <<'PY'` heredoc inline here, which is exactly why
# it had no red-ability proof: a heredoc has no name, so there was nothing a case
# could call. It also meant `set -euo pipefail` was the only thing standing
# between a python exit-1 and the unconditional `exit 0` on the last line.
#
# Usage is unchanged:
#   runbook-verification-lint.sh              # full check
#   runbook-verification-lint.sh --self-test  # the proof alone
#
# Exit 0 = clean · 1 = violations · 2 = misuse / nothing scanned / self-test failure.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3
  elif command -v python >/dev/null 2>&1; then PY=python
  else
    echo "[runbook-verification-lint] MISUSE — no python3/python on PATH" >&2
    exit 2
  fi
fi

exec "$PY" "$repo_root/scripts/runbook-verification-lint.py" "$@"
