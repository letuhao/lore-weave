#!/usr/bin/env bash
# migration-idempotency-validator.sh — L1.D.7 (RAID cycle 6)
#
# A THIN WRAPPER around `migration-idempotency-validator.py`, which holds the
# whole implementation. Same shape as `workflow-gate.sh` → `workflow-gate.py`,
# and it stays the entry point because two CI legs invoke it by name:
# `.github/workflows/foundation-ci.yml` and the `lint-foundation` matrix.
#
# WHY THE LOGIC MOVED (2026-08-10, `META-DOWN-UNCOVERED`)
# --------------------------------------------------------
# The shell version defaulted to `contracts/migrations/per_reality` only, so
# `migrations/meta` — 78 files, including the ownership migrations 036/037 —
# was walked by nothing. `NV-3`, and the SECOND time this script has had it.
#
# Widening it was not enough on its own. Every check was a `grep -E` anchored to
# a single LINE, and the meta tree writes multi-clause `ALTER TABLE`s across
# several lines — measured, **8 of 13 `ALTER TABLE … COLUMN` statements are
# multi-line**, four of them in the tree the lint already walked. A line-anchored
# grep pointed at a second tree walks it and sees almost nothing, which reports
# as coverage. Statement-aware matching needs comment, string and
# dollar-quoted-body handling, and that is not what bash is for (§0.6: heredocs
# eat backslashes, and this file is nothing but escaped regexes).
#
# Usage is unchanged:
#   migration-idempotency-validator.sh                  # both trees
#   migration-idempotency-validator.sh path1.sql ...    # specific files
#   migration-idempotency-validator.sh --self-test
#
# Exits 0 = clean, 1 = violations found, 2 = misuse (including a tree that
# yields (almost) no files — a walk that finds nothing must never exit 0).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3
  elif command -v python >/dev/null 2>&1; then PY=python
  else
    echo "[idempotency] MISUSE — no python3/python on PATH; this validator needs one" >&2
    exit 2
  fi
fi

exec "$PY" "$repo_root/scripts/migration-idempotency-validator.py" "$@"
