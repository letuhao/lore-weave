#!/usr/bin/env python3
"""Seed the canonical AMAW guardrail set into ContextHub — idempotent.

Part of the "improve AMAW ContextHub integration" task (D4). The AMAW
`PreToolUse` risky-action gate (`amaw-guardrail-gate.py`) passes a raw Bash
command to `check_guardrails`; ContextHub matches the command against each
guardrail's `trigger`. For that to work the corpus must actually contain
guardrails for the risky actions — this script ensures it does.

Two gotchas (captured in a prior ContextHub lesson, 2026-05-15):

  1. ContextHub `matchTrigger` does EXACT string match for a plain trigger
     (`trimmed === action`); regex matching ONLY for the `/pattern/` delimited
     form. So every trigger here is `/regex/` — a plain `git push` would never
     match `git push -f origin`.
  2. Git Bash MSYS path-conversion mangles a leading-slash `/regex/` passed as
     a CLI arg. This script calls `mcp-query.py` via `subprocess` in LIST form
     (no shell) — argv elements are passed verbatim, so MSYS never sees them.

Idempotent: before seeding a guardrail it probes `check_guardrails` with a
representative action; if a rule already matches, it skips. Safe to re-run, and
safe to run against a fresh ContextHub to rebuild the corpus.

Usage:  python scripts/seed-amaw-guardrails.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

MCP_QUERY = Path(__file__).with_name("mcp-query.py")

# ── Canonical AMAW guardrail set ──────────────────────────────────────
#
# Each entry: the guardrail metadata + a `probe` action string used only for
# the idempotency check (it must be a string the entry's own regex matches).
# `trigger` is ALWAYS `/regex/` form (gotcha 1).
GUARDRAILS: list[dict[str, str]] = [
    {
        "title": "Push only with explicit user approval",
        "trigger": r"/git\s+push/",
        "requirement": "Do not `git push` unless the user has explicitly asked "
        "for it in this session (CLAUDE.md Phase 11 / COMMIT).",
        "probe": "git push origin main",
    },
    {
        "title": "Never force-push without explicit, scoped approval",
        "trigger": r"/git\s+push\s+.*(--force|-f|--force-with-lease)/",
        "requirement": "Force-push rewrites published history — require explicit "
        "user approval naming the branch; never as a convenience.",
        "probe": "git push --force origin feature",
    },
    {
        "title": "Database migrations need review",
        "trigger": r"/migrat(e|ion)/",
        "requirement": "A schema migration is hard to reverse — confirm intent, "
        "back up / verify rollback before running.",
        "probe": "run database migration",
    },
    {
        "title": "Recursive delete is destructive — confirm the target",
        "trigger": r"/rm\s+-[A-Za-z]*r/",
        "requirement": "`rm -r` / `rm -rf` permanently deletes a tree — verify "
        "the path is intended and not a parent/glob mistake before running.",
        "probe": "rm -rf ./build",
    },
    {
        "title": "git reset --hard discards uncommitted work",
        "trigger": r"/git\s+reset\s+--hard/",
        "requirement": "`git reset --hard` silently destroys uncommitted changes "
        "— confirm there is nothing unsaved worth keeping first.",
        "probe": "git reset --hard HEAD~1",
    },
    {
        "title": "docker compose down -v destroys volumes",
        "trigger": r"/docker(\s+|-)compose\s+down\s+.*-v/",
        "requirement": "`down -v` deletes named volumes (databases, MinIO data) "
        "— confirm the data is disposable before running.",
        "probe": "docker compose down -v",
    },
]


def _mcp(args: list[str]) -> dict:
    """Run mcp-query.py with JSON output; return the parsed object.

    LIST-form subprocess — no shell — so a `/regex/` trigger arg reaches the
    program verbatim (MSYS path-conversion never applies).
    """
    proc = subprocess.run(
        [sys.executable, str(MCP_QUERY), *args, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"mcp-query.py {args[0]} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"mcp-query.py {args[0]} non-JSON output: {exc}") from exc


def _contexthub_reachable() -> bool:
    """True if `mcp-query.py ping` succeeds. `ping` prints plain `OK` (not
    JSON), so it cannot go through `_mcp`."""
    proc = subprocess.run(
        [sys.executable, str(MCP_QUERY), "ping"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and "OK" in proc.stdout


def _already_guarded(probe: str) -> bool:
    """True if ContextHub already has a guardrail matching `probe`."""
    result = _mcp(["check_guardrails", probe])
    # check_guardrails returns pass=false + a non-empty matched_rules when a
    # guardrail fires for the action.
    return result.get("pass") is False and bool(result.get("matched_rules"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed canonical AMAW guardrails.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be seeded without writing.",
    )
    args = parser.parse_args()

    # Fail fast if ContextHub is unreachable — seeding needs it live.
    if not _contexthub_reachable():
        print("ContextHub not reachable — cannot seed guardrails.", file=sys.stderr)
        return 1

    seeded, skipped = 0, 0
    for g in GUARDRAILS:
        if _already_guarded(g["probe"]):
            print(f"  skip (already present): {g['title']}")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  would seed: {g['title']}  trigger={g['trigger']}")
            seeded += 1
            continue
        _mcp(
            [
                "add_lesson",
                "--type",
                "guardrail",
                "--title",
                g["title"],
                "--content",
                g["requirement"],
                "--tags",
                "amaw,guardrail,risky-action",
                "--guardrail-trigger",
                g["trigger"],
                "--guardrail-requirement",
                g["requirement"],
                "--guardrail-verification",
                "user_confirmation",
            ]
        )
        print(f"  seeded: {g['title']}  trigger={g['trigger']}")
        seeded += 1

    verb = "would seed" if args.dry_run else "seeded"
    print(f"\nDone — {verb} {seeded}, skipped {skipped} (of {len(GUARDRAILS)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
