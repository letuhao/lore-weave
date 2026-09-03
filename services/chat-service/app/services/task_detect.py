"""ext-tasks client DETECTION — 🟢 LIVE. This is the PRIMARY confirm path.

When chat-service declares the ext-tasks extension in a tool call, a task-capable
domain (e.g. composition_create_derivative) may answer `tools/call` with a durable
task instead of a normal result — a wire `CreateTaskResult` (`resultType:"task"`,
carrying a `Task`), or, before the CreateTaskResult wrap, the gate HANDLE dict
(`type == GATE_RESULT_TYPE`) in the tool content. This module recognises either and
normalises it to a *task envelope* the tool loop suspends on — mirroring how a
frontend tool suspends today, but driven by the domain-owned durable task.

Pure + import-light so it unit-tests without a live transport.

🔴 THIS DOCSTRING USED TO SAY THE OPPOSITE, AND IT WAS READ AND BELIEVED. Until
2026-09-03 it read: "It is NOT wired into `mcp_execute_tool` yet and chat-service does
NOT yet declare tasks capability, so on the current stack a task never comes back and
this never fires (dormant-safe)." Every clause of that is false and had been since
2026-07-20:

    app/config.py:166               tasks_gate_enabled: bool = True
    app/client/knowledge_client.py  calls tasks_capability_meta() and passes it as the
                                    call's `_meta` — the ACTIVATION switch, thrown
    docs/standards/mcp-tool-io.md   GATE-1: "the durable ext-tasks gate is the PRIMARY
                                    path for high-impact (Tier-W / KIND-C) confirms"

The cost was not hypothetical. A 2026-09-03 audit of whether architecture v1 could be
retired had to establish from scratch which of the two confirm paths was live, because
the file implementing the replacement said the replacement was dormant — the exact
belief that makes a reader conclude the legacy path is the only one and reverse the
migration. See `docs/specs/2026-09-03-retire-architecture-v1.md` §6.

WHAT IS STILL TRUE: the `confirm_token` fallback is PERMANENT (GATE-2). A domain returns
a durable task only to a client that declared the capability; the public MCP edge and
external agents cannot drive tasks, so they still get a `confirm_token` card. Task-vs-
token is negotiated per call — never "the old way is gone".
"""
from __future__ import annotations

import json
from typing import Any

# Kept in sync with loreweave_mcp.tasks_wire.GATE_RESULT_TYPE (the gate handle marker).
GATE_RESULT_TYPE = "io.loreweave/task-handle"

# Phase 2 — the GATED propose_edit proposal directive marker, kept in sync with
# ai-gateway propose-edit-tool.ts PROPOSE_EDIT_DIRECTIVE_TYPE. Distinct from a durable
# task: propose_edit's effect is a CLIENT edit (no server executor), so it suspends and
# resumes exactly like the legacy frontend-tool propose_edit (the FE applies + submits
# the outcome) — no `task` marker, no provide-input drive.
PROPOSE_EDIT_DIRECTIVE_TYPE = "io.loreweave/propose-edit"

# V7 / DQ-V9 (2026-09-03) — the two markers the three KIND-C human-gate tools now return, once
# they moved out of chat-service into ai-gateway as DIRECTIVE tools (confirm-tools.ts). Kept in
# sync with that module's exported constants.
#
# Like propose_edit and UNLIKE a durable task: there is no server executor and no `task` marker.
# The client GATES on the human, then commits through the domain's own confirm route — which is
# exactly why these could not become domain MCP tools (a server executor would let the model
# confirm its own action). See docs/plans/2026-09-03-retire-v1-BUILD.md DQ-V9.
CONFIRM_DIRECTIVE_TYPE = "io.loreweave/confirm-action"
GLOSSARY_CONFIRM_DIRECTIVE_TYPE = "io.loreweave/glossary-confirm-action"
RECORD_EDIT_DIRECTIVE_TYPE = "io.loreweave/propose-record-edit"

#: marker -> the suspend `name` the FE already renders a card for. The suspend keeps the OLD tool
#: name on purpose: `ConfirmActionCard`, `GlossaryDiffCard` and the resume driver key on it, so the
#: browser half of this move is a no-op. The tool's HOME changed; its identity did not.
_GATED_DIRECTIVES = {
    CONFIRM_DIRECTIVE_TYPE: "confirm_action",
    # 🔴 A THIRD ENTRY, BECAUSE TWO TOOLS SHARING ONE MARKER SHARE ONE NAME. Until 2026-09-03
    # `glossary_confirm_action` emitted CONFIRM_DIRECTIVE_TYPE, so it suspended as
    # `confirm_action` — and cms-frontend's admin card, which gates on the exact string
    # `glossary_confirm_action` and has no auto-confirm fallback, silently stopped rendering.
    GLOSSARY_CONFIRM_DIRECTIVE_TYPE: "glossary_confirm_action",
    RECORD_EDIT_DIRECTIVE_TYPE: "glossary_propose_entity_edit",
}

# ext-tasks extension id + the per-request client-capability envelope keys — the
# SAME wire keys loreweave_mcp.tasks_wire.client_supports_tasks reads server-side.
_TASKS_EXTENSION = "io.modelcontextprotocol/tasks"
_CLIENT_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"

__all__ = [
    "GATE_RESULT_TYPE",
    "PROPOSE_EDIT_DIRECTIVE_TYPE",
    "GLOSSARY_CONFIRM_DIRECTIVE_TYPE",
    "task_envelope_from_result",
    "task_envelope_from_content",
    "propose_edit_suspend_args_from_result",
    "gated_directive_suspend_args",
    "tasks_capability_meta",
]


def propose_edit_suspend_args_from_result(payload: Any) -> dict[str, Any] | None:
    """A propose_edit GATED proposal directive (`{type: PROPOSE_EDIT_DIRECTIVE_TYPE,
    operation, text, rationale?}`) — from a tool result's structuredContent (already a
    dict by the time mcp_execute_tool returns) — → the suspend `args` the frontend-tool
    propose_edit suspend used to carry (`{operation, text, rationale?}`), so the FE's
    ProposeEditCard renders unchanged. Anything else → None (a normal tool result)."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if not isinstance(payload, dict) or payload.get("type") != PROPOSE_EDIT_DIRECTIVE_TYPE:
        return None
    op = payload.get("operation")
    text = payload.get("text")
    if not op or text is None:
        return None
    args: dict[str, Any] = {"operation": op, "text": text}
    if isinstance(payload.get("rationale"), str) and payload["rationale"]:
        args["rationale"] = payload["rationale"]
    return args


def tasks_capability_meta() -> dict[str, Any]:
    """The per-request `_meta` fragment chat-service merges into a tool call to
    DECLARE it can drive ext-tasks (the domain's `client_supports_tasks` reads
    exactly this to decide task-vs-confirm_token). Attaching this is the ACTIVATION
    switch — done only once the detect + suspend + drive path is wired end to end,
    so a declared-but-undriven task can never strand.

    🔴 THE SWITCH IS THROWN. This trailed "Until then this is defined but unused
    (dormant)" until 2026-09-03, while `knowledge_client.py` had been calling it under
    `settings.tasks_gate_enabled` (default True) since the gate went primary. Verify with
    the caller, not with this sentence:

        git grep -n tasks_capability_meta -- services/chat-service/app
    """
    return {_CLIENT_CAPS_KEY: {"extensions": {_TASKS_EXTENSION: {}}}}


def gated_directive_suspend_args(payload: Any) -> tuple[str, dict[str, Any]] | None:
    """A gated CONFIRM or RECORD-EDIT directive → `(suspend_name, args)`, else None.

    The args are the directive MINUS its `type` marker, which reproduces byte-for-byte the shape
    chat-service's own v1 intercept used to freeze into the suspended run — so `ConfirmActionCard`,
    `GlossaryDiffCard`, the admin card and the resume driver all keep working with no FE change.

    🔴 `domain` IS NOT DERIVED HERE. It rides the directive, and for `glossary_confirm_action`
    ai-gateway pins it to "glossary" regardless of what the model passed. Re-deriving it on this
    side would reintroduce the one-name-two-behaviours surface the move exists to remove.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if not isinstance(payload, dict):
        return None
    name = _GATED_DIRECTIVES.get(payload.get("type"))
    if name is None:
        return None
    args = {k: v for k, v in payload.items() if k != "type"}
    if not args:
        return None
    return name, args


def _task_envelope(task_id: str, status: str, input_requests: Any = None,
                   poll_interval_ms: int | None = None) -> dict[str, Any]:
    """The normalised durable-task envelope the tool loop suspends on."""
    env: dict[str, Any] = {
        "success": True,
        "error": None,
        "result": None,
        "task": {"taskId": task_id, "status": status, "inputRequests": input_requests},
    }
    if poll_interval_ms is not None:
        env["task"]["pollIntervalMs"] = poll_interval_ms
    return env


def task_envelope_from_result(result: Any) -> dict[str, Any] | None:
    """A wire `CreateTaskResult` → a task envelope; anything else → None.

    Duck-typed on `.task` (a `Task` with `.taskId`/`.status`) so it works whether the
    SDK handed back a parsed `CreateTaskResult` or a compatible object; robust to the
    `Task` types moving when ext-tasks stabilises."""
    task = getattr(result, "task", None)
    if task is None:
        return None
    task_id = getattr(task, "taskId", None)
    status = getattr(task, "status", None)
    if not task_id or not status:
        return None
    return _task_envelope(str(task_id), str(status),
                          poll_interval_ms=getattr(task, "pollInterval", None))


def task_envelope_from_content(payload: Any) -> dict[str, Any] | None:
    """A gate HANDLE (`{type: GATE_RESULT_TYPE, taskId, status, inputRequests}`) —
    from a tool result's structuredContent or a JSON text block — → a task envelope;
    else None. Covers a domain that returns the handle-in-content form (no
    CreateTaskResult wrap)."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if not isinstance(payload, dict) or payload.get("type") != GATE_RESULT_TYPE:
        return None
    task_id = payload.get("taskId")
    status = payload.get("status")
    if not task_id or not status:
        return None
    return _task_envelope(str(task_id), str(status),
                          input_requests=payload.get("inputRequests"),
                          poll_interval_ms=payload.get("pollIntervalMs"))
