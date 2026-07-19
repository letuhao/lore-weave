"""ext-tasks durable-gate WIRE (T1b) — bind the task store onto a FastMCP server.

Wires the transport-free lifecycle (``tasks.py``) onto a real MCP server so a
client drives the gate over the standard protocol:

  * ``tasks/get(taskId)``   → routed to our handler (``GetTaskRequest`` is in the
    SDK's ``ClientRequest`` union), returns the current status; the card payload
    (``inputRequests``) and, on completion, the ``result`` ride in ``_meta``.
  * ``tasks/cancel(taskId)`` → cooperative cancel.
  * ``task_provide_input(taskId, accepted, inputs)`` → the input step. (The
    ``ext-tasks`` ``tasks/update`` method has no request type in mcp 1.28.1, so the
    input step is an INTERIM TOOL; swap to the ``tasks/update`` method once a
    stable SDK ships its type — the store + lifecycle are unchanged.)

Integration seam: FastMCP exposes the lowlevel ``Server`` at ``fastmcp._mcp_server``;
we register typed request handlers on its ``request_handlers`` map. The wire TYPES
(``GetTaskRequest``/``GetTaskResult``/…) are the SDK's — necessary because the Server
routes by known request type — and are the only SDK surface here that changes when
Tasks moves to the standalone ``ext-tasks`` extension; the durable-gate LOGIC
(``tasks.py``) depends on nothing experimental.

The gate itself: a KIND-C tool calls ``open_gate(...)`` to durably create the task
and returns the handle. (Emitting a wire ``CreateTaskResult`` with ``resultType:
"task"`` — so a client auto-detects the task without reading the tool content — is a
Phase-T1c refinement via a CallTool wrap; the handle-in-content form here already
drives the full loop.)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import mcp.types as t

from .tasks import COMPLETED, FAILED, Task, TaskStore

__all__ = ["register_task_endpoints", "open_gate", "GATE_RESULT_TYPE"]

# A marker in the gate tool's result content so a client (and our own resolver)
# recognises "this is a durable task handle, poll tasks/get".
GATE_RESULT_TYPE = "io.loreweave/task-handle"


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _get_result(task: Task) -> t.GetTaskResult:
    """tasks/get carries STATUS + timing (the poll contract). The card payload
    (``inputRequests``) reaches the client on the gate HANDLE, and the final
    ``result`` on the ``task_provide_input`` response — so tasks/get needs neither.
    (mcp 1.28.1's ``GetTaskResult`` has no ``inputRequests`` field and its ``_meta``
    passthrough doesn't round-trip; delivering the result via tasks/get for a
    crash-resumed client — with a proper ``tasks/result`` — is a T1c refinement.
    ``statusMessage`` carries a short human/agent hint.)"""
    msg = None
    if task.status == FAILED and task.error:
        msg = task.error
    return t.GetTaskResult(
        taskId=task.task_id,
        status=task.status,
        statusMessage=msg,
        createdAt=_dt(task.created_at),
        lastUpdatedAt=_dt(task.updated_at),
        ttl=task.ttl_ms,
        pollInterval=task.poll_interval_ms,
    )


async def open_gate(
    store: TaskStore,
    *,
    descriptor: str,
    executor: Callable[[dict[str, Any]], Awaitable[Any]],
    input_requests: Any = None,
    ttl_ms: int | None = None,
) -> dict[str, Any]:
    """A KIND-C tool calls this to durably open the human gate. Returns a task
    HANDLE the tool returns as its result; the client then polls tasks/get and,
    when it has the human's decision, calls task_provide_input(taskId)."""
    kwargs: dict[str, Any] = dict(descriptor=descriptor, executor=executor,
                                  input_requests=input_requests)
    if ttl_ms is not None:
        kwargs["ttl_ms"] = ttl_ms
    task = await store.create(**kwargs)
    return {
        "type": GATE_RESULT_TYPE,
        "taskId": task.task_id,
        "status": task.status,
        "pollIntervalMs": task.poll_interval_ms,
        "inputRequests": input_requests,
    }


def register_task_endpoints(fastmcp: Any, store: TaskStore) -> None:
    """Register tasks/get + tasks/cancel handlers and the task_provide_input tool
    onto a FastMCP server. Idempotent-safe to call once per server at build time."""
    srv = fastmcp._mcp_server

    async def _get(req: t.GetTaskRequest) -> t.ServerResult:
        task_id = req.params.taskId or getattr(req.params, "task", None)
        task = await store.get(task_id)
        return t.ServerResult(_get_result(task))

    async def _cancel(req: t.CancelTaskRequest) -> t.ServerResult:
        task_id = req.params.taskId or getattr(req.params, "task", None)
        task = await store.cancel(task_id)
        return t.ServerResult(
            t.CancelTaskResult(
                taskId=task.task_id, status=task.status,
                createdAt=_dt(task.created_at), lastUpdatedAt=_dt(task.updated_at),
                ttl=task.ttl_ms, pollInterval=task.poll_interval_ms,
            )
        )

    srv.request_handlers[t.GetTaskRequest] = _get
    srv.request_handlers[t.CancelTaskRequest] = _cancel

    @fastmcp.tool(name="task_provide_input")
    async def task_provide_input(  # noqa: D401 — the input step (interim for tasks/update)
        task_id: str, accepted: bool = True, inputs: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = dict(inputs or {})
        payload["accepted"] = accepted
        task = await store.provide_input(task_id, payload)
        out: dict[str, Any] = {"taskId": task.task_id, "status": task.status}
        if task.status == COMPLETED:
            out["result"] = task.result
        if task.status == FAILED and task.error:
            out["error"] = task.error
        return out
