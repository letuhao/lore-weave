#!/usr/bin/env python3
"""AMAW `PreToolUse` risky-action guardrail gate.

Wired as a Claude Code `PreToolUse` hook with `matcher: "Bash"` (see
`.claude/settings.json`). For every Bash tool call it:

  1. Cheap LOCAL pre-check — match the command against a risky-action pattern
     table. No match → exit 0 immediately (allow; zero ContextHub cost — the
     overwhelming majority of Bash calls take this path).
  2. On a risky-pattern match → ask ContextHub `check_guardrails` whether a
     guardrail fires for this command.
  3. A fired guardrail → emit a `permissionDecision: "ask"` so the harness
     surfaces it to the user (the guardrails are confirmation-type — "proceed
     with explicit approval", not hard-forbidden). The user approving IS the
     "explicit user approval" the guardrail requires.

**Fail-OPEN, always.** If ContextHub is unreachable / errors / times out, or
anything else goes wrong, the gate ALLOWS the call (exit 0) and logs a warning
to stderr. A guardrail-infra outage must never block a tool call — a transient
ContextHub blip was observed during Phase 0b. The gate is a safety net, not a
single point of failure.

Hook I/O: a PreToolUse JSON object on stdin (`tool_name`, `tool_input`).
Output: exit 0 + no stdout = allow; exit 0 + the `hookSpecificOutput` JSON
below = ask. The script never exits non-zero (fail-open even on its own bugs).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

MCP_QUERY = Path(__file__).with_name("mcp-query.py")

# Cheap local pre-check. A match here only means "worth asking ContextHub" —
# false positives just cost one check_guardrails call, never a wrong decision.
# Mirrors the seeded guardrail set (see seed-amaw-guardrails.py).
RISKY_PATTERNS: tuple[str, ...] = (
    r"\bgit\s+push\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\brm\s+-[A-Za-z]*r",  # recursive rm
    r"\bdocker(?:\s+|-)compose\s+down\b.*-v",
    r"migrat(?:e|ion)",
)

# Hard cap on the ContextHub round-trip — a slow guardrail check must not stall
# every Bash call. On timeout the gate fails open.
CHECK_TIMEOUT_S = 8


def _allow() -> None:
    """Allow the tool call (the default — no output needed)."""
    sys.exit(0)


def _ask(reason: str) -> None:
    """Surface the action to the user for explicit approval."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _check_guardrails(command: str) -> dict | None:
    """Ask ContextHub whether a guardrail fires for `command`. Returns the
    parsed response, or `None` on ANY failure (→ caller fails open)."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(MCP_QUERY),
                "check_guardrails",
                command,
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    # Any unexpected failure → fail open. The gate must never be the reason a
    # session cannot run a command.
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        _allow()

    if payload.get("tool_name") != "Bash":
        _allow()

    command = str((payload.get("tool_input") or {}).get("command", ""))
    if not command.strip():
        _allow()

    # 1. Cheap local pre-check — no risky pattern → allow without touching ContextHub.
    if not any(re.search(p, command) for p in RISKY_PATTERNS):
        _allow()

    # 2. Risky command — consult ContextHub guardrails (fail-open).
    result = _check_guardrails(command)
    if result is None:
        print(
            "amaw-guardrail-gate: ContextHub unavailable — failing open "
            "(risky command NOT gated)",
            file=sys.stderr,
        )
        _allow()

    # 3. A fired guardrail → ask the user. `check_guardrails` returns
    # `pass: false` + a non-empty `matched_rules` when a guardrail triggers;
    # `prompt` is the human-readable "Guardrail triggered: …" string (use it —
    # `matched_rules[].title` can be null for some seeded rules).
    if result.get("pass") is False and result.get("matched_rules"):
        reason = result.get("prompt") or (
            "An AMAW guardrail matched this command — it needs explicit "
            "user approval before proceeding."
        )
        _ask(reason)

    _allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # _allow / _ask use sys.exit — that is the normal path
    except BaseException as exc:  # noqa: BLE001 — fail-open on ANY unexpected error
        print(
            f"amaw-guardrail-gate: internal error, failing open: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
