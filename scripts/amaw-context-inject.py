#!/usr/bin/env python3
"""AMAW `SessionStart` context-injection hook.

Wired as a Claude Code `SessionStart` hook (see `.claude/settings.json`). It
queries ContextHub once per session and injects a compact block into context:

  - the **active guardrails** — probed via `check_guardrails` for the canonical
    risky actions, so the agent sees them up front (not search-on-demand);
  - the **most recent lessons** — titles only, as lightweight steering.

This is the "Kiro steering file" pattern done dynamically: the captured rules
are put *in front of* the agent instead of relying on the agent choosing to go
look. It complements the `PreToolUse` guardrail gate (which hard-enforces) —
this one makes the agent *aware* so it self-restricts before even trying.

**Fail-OPEN, silent.** ContextHub unreachable / any error → emit an empty
`additionalContext` and exit 0. A steering hook must never disrupt a session.

Hook I/O: a `SessionStart` JSON object on stdin (unused). Output: a
`hookSpecificOutput.additionalContext` JSON object on stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MCP_QUERY = Path(__file__).with_name("mcp-query.py")
QUERY_TIMEOUT_S = 10

# Representative action per seeded guardrail (mirrors seed-amaw-guardrails.py).
# Each must be a string the guardrail's regex trigger matches.
PROBE_ACTIONS: tuple[str, ...] = (
    "git push origin main",
    "git push --force origin feature",
    "run a database migration",
    "rm -rf ./build",
    "git reset --hard HEAD~1",
    "docker compose down -v",
)
RECENT_LESSON_COUNT = 8


def _emit(context: str) -> None:
    """Emit the additionalContext payload and exit. Empty string = inject
    nothing (the fail-open / nothing-to-say path)."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )
    sys.exit(0)


def _mcp_json(args: list[str]) -> object | None:
    """Run mcp-query.py with JSON output; return parsed object or None on any
    failure (→ caller treats it as 'ContextHub unavailable')."""
    try:
        proc = subprocess.run(
            [sys.executable, str(MCP_QUERY), *args, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _active_guardrails() -> list[str]:
    """Probe each canonical risky action; collect the human-readable prompt of
    every guardrail that fires. De-duplicated, order-stable."""
    seen: set[str] = set()
    out: list[str] = []
    for action in PROBE_ACTIONS:
        result = _mcp_json(["check_guardrails", action])
        if not isinstance(result, dict):
            continue
        if result.get("pass") is False:
            prompt = (result.get("prompt") or "").strip()
            if prompt and prompt not in seen:
                seen.add(prompt)
                out.append(prompt)
    return out


def _recent_lessons() -> list[str]:
    """Titles of the most recent lessons (lightweight steering)."""
    data = _mcp_json(["list_lessons"])
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("results") or data.get("lessons") or data.get("items") or []
    titles: list[str] = []
    for it in items[:RECENT_LESSON_COUNT]:
        if isinstance(it, dict):
            t = (it.get("title") or "").strip()
            if t:
                titles.append(t)
    return titles


def main() -> None:
    # stdin is the SessionStart payload — not needed; drain it so the pipe closes.
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass

    guardrails = _active_guardrails()
    lessons = _recent_lessons()

    if not guardrails and not lessons:
        # ContextHub down or empty — inject nothing (fail-open).
        _emit("")

    parts: list[str] = ["# AMAW ContextHub steering (auto-injected at session start)"]
    if guardrails:
        parts.append(
            "\n## Active guardrails — these actions need explicit user approval"
        )
        parts.append(
            "The `PreToolUse` gate enforces these; do not attempt them without "
            "the user asking:"
        )
        parts.extend(f"- {g}" for g in guardrails)
    if lessons:
        parts.append("\n## Recent captured lessons (consult before similar work)")
        parts.extend(f"- {t}" for t in lessons)

    _emit("\n".join(parts))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — fail-open on ANY error
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": "",
                    }
                }
            )
        )
        print(f"amaw-context-inject: failing open: {exc}", file=sys.stderr)
        sys.exit(0)
