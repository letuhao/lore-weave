"""Declarative hook engine (P4 REG-P4-03) — PURE evaluation, no I/O.

Hooks are declarative config resolved from agent-registry (/internal/hooks). The
chat-turn loop evaluates them at fixed seams:
  * pre_tool_call  → deny (block the call, surface result.error) | require_approval
                     (route to the existing HITL approval gate)
  * pre_turn / post_turn → inject_text (a steering-style block into the prompt)
  * post_tool_call → annotate (advisory note)

There is NO code-execution action kind — hooks are data the loop interprets, so the
26%-vuln / reverse-shell class is designed out (agent-registry rejects any other kind).
"""

from __future__ import annotations

import fnmatch

__all__ = ["tool_matches", "decide_pre_tool_call", "collect_injections", "collect_annotations"]


def tool_matches(match: dict | None, tool_name: str) -> bool:
    """A hook matches a tool when its match has no tool filter (matches all) or the
    tool name glob-matches `tool_pattern` (or the alias `tool`)."""
    m = match or {}
    pat = m.get("tool_pattern") or m.get("tool")
    if not pat:
        return True
    return fnmatch.fnmatch(tool_name, str(pat))


def _action(h: dict) -> dict:
    a = h.get("action")
    return a if isinstance(a, dict) else {}


def decide_pre_tool_call(hooks: list[dict], tool_name: str) -> tuple[str, str]:
    """Return (decision, message) for a tool about to run.
    Precedence: deny > require_approval > allow (deny short-circuits)."""
    decision = ("allow", "")
    for h in hooks:
        if h.get("on_event") != "pre_tool_call":
            continue
        if not tool_matches(h.get("match"), tool_name):
            continue
        act = _action(h)
        kind = act.get("kind")
        msg = str(act.get("message") or act.get("text") or "")
        if kind == "deny":
            return ("deny", msg or f"Tool '{tool_name}' is blocked by a hook.")
        if kind == "require_approval" and decision[0] == "allow":
            decision = ("require_approval", msg)
    return decision


def collect_injections(hooks: list[dict], event: str) -> list[str]:
    """The inject_text texts for a pre_turn/post_turn seam, in hook order (the
    resolver already sorts by priority DESC)."""
    out: list[str] = []
    for h in hooks:
        if h.get("on_event") != event:
            continue
        act = _action(h)
        if act.get("kind") == "inject_text" and act.get("text"):
            out.append(str(act["text"]))
    return out


def collect_annotations(hooks: list[dict], tool_name: str) -> list[str]:
    """post_tool_call annotate texts whose match applies to `tool_name`."""
    out: list[str] = []
    for h in hooks:
        if h.get("on_event") != "post_tool_call":
            continue
        if not tool_matches(h.get("match"), tool_name):
            continue
        act = _action(h)
        if act.get("kind") == "annotate" and act.get("text"):
            out.append(str(act["text"]))
    return out
