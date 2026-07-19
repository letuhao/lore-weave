"""ext-tasks client DETECTION (T1c(3), dormant until caps are declared).

When chat-service declares the ext-tasks extension in a tool call, a task-capable
domain (e.g. composition_create_derivative) may answer `tools/call` with a durable
task instead of a normal result — a wire `CreateTaskResult` (`resultType:"task"`,
carrying a `Task`), or, before the CreateTaskResult wrap, the gate HANDLE dict
(`type == GATE_RESULT_TYPE`) in the tool content. This module recognises either and
normalises it to a *task envelope* the tool loop suspends on — mirroring how a
frontend tool suspends today, but driven by the domain-owned durable task.

Pure + import-light so it unit-tests without a live transport. It is NOT wired into
`mcp_execute_tool` yet and chat-service does NOT yet declare tasks capability, so on
the current stack a task never comes back and this never fires (dormant-safe). The
wiring + the capability declaration (the activation switch) land with the gateway
forwarding (T2) as one coordinated, live-E2E'd slice.
"""
from __future__ import annotations

import json
from typing import Any

# Kept in sync with loreweave_mcp.tasks_wire.GATE_RESULT_TYPE (the gate handle marker).
GATE_RESULT_TYPE = "io.loreweave/task-handle"

# ext-tasks extension id + the per-request client-capability envelope keys — the
# SAME wire keys loreweave_mcp.tasks_wire.client_supports_tasks reads server-side.
_TASKS_EXTENSION = "io.modelcontextprotocol/tasks"
_CLIENT_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"

__all__ = [
    "GATE_RESULT_TYPE",
    "task_envelope_from_result",
    "task_envelope_from_content",
    "tasks_capability_meta",
]


def tasks_capability_meta() -> dict[str, Any]:
    """The per-request `_meta` fragment chat-service merges into a tool call to
    DECLARE it can drive ext-tasks (the domain's `client_supports_tasks` reads
    exactly this to decide task-vs-confirm_token). Attaching this is the ACTIVATION
    switch — done only once the detect + suspend + drive path is wired end to end,
    so a declared-but-undriven task can never strand. Until then this is defined but
    unused (dormant)."""
    return {_CLIENT_CAPS_KEY: {"extensions": {_TASKS_EXTENSION: {}}}}


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
