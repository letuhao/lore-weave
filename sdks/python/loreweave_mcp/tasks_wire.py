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

__all__ = [
    "register_task_endpoints",
    "enable_task_results",
    "open_gate",
    "gate_or_confirm",
    "client_supports_tasks",
    "TASKS_EXTENSION",
    "GATE_RESULT_TYPE",
]

# ext-tasks extension id + the per-request client-capability envelope keys (spec §4.2).
TASKS_EXTENSION = "io.modelcontextprotocol/tasks"
_CLIENT_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"


def _mget(obj: Any, key: str) -> Any:
    """Read ``key`` from a per-request _meta node that may be a plain dict OR a
    pydantic model carrying it as an extra field."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    me = getattr(obj, "model_extra", None)
    if isinstance(me, dict) and key in me:
        return me[key]
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:  # noqa: BLE001
            pass
    return getattr(obj, key, None)


def client_supports_tasks(ctx: Any) -> bool:
    """True iff THIS request's client declared the ext-tasks extension in per-request
    `_meta` (`params._meta['io.modelcontextprotocol/clientCapabilities'].extensions[
    'io.modelcontextprotocol/tasks']`). A KIND-C tool gates on this: task if True,
    else the confirm_token fallback (OQ3) — so flipping a tool to the durable gate
    NEVER strands a client that can't drive tasks (today's chat-service, the public
    edge, external agents). Fail-closed on any read error → falls back to confirm_token."""
    try:
        meta = getattr(getattr(ctx, "request_context", None), "meta", None)
    except Exception:  # noqa: BLE001
        return False
    exts = _mget(_mget(meta, _CLIENT_CAPS_KEY), "extensions")
    return _mget(exts, TASKS_EXTENSION) is not None

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


async def gate_or_confirm(
    ctx: Any,
    store: TaskStore,
    *,
    descriptor: str,
    executor: Callable[[dict[str, Any]], Awaitable[Any]],
    input_requests: Any,
    confirm_fallback: Callable[[], Any],
    ttl_ms: int | None = None,
) -> Any:
    """The capability-gated KIND-C gate — the ONE call a domain confirm tool makes.

    If the request's client declared ext-tasks support → open a durable TASK
    (`open_gate`). Otherwise → return ``confirm_fallback()`` (today's
    ``{confirm_token, descriptor, …}`` dict) so a non-tasks client (chat-service
    pre-driver, the public edge, external agents) is NEVER stranded with a task it
    can't drive. This is the safety-critical gating from spec §4.2 — a domain tool
    must go through this, never call ``open_gate`` unconditionally."""
    if client_supports_tasks(ctx):
        return await open_gate(
            store, descriptor=descriptor, executor=executor,
            input_requests=input_requests, ttl_ms=ttl_ms,
        )
    return confirm_fallback()


def _create_task_result(task: Task) -> t.CreateTaskResult:
    return t.CreateTaskResult(
        task=t.Task(
            taskId=task.task_id,
            status=task.status,
            createdAt=_dt(task.created_at),
            lastUpdatedAt=_dt(task.updated_at),
            ttl=task.ttl_ms,
            pollInterval=task.poll_interval_ms,
        )
    )


def _handle_of(call_tool_result: Any) -> dict[str, Any] | None:
    """Extract a gate HANDLE dict from a CallToolResult, or None if this tool
    result is not a gate. Reads structuredContent (FastMCP's dict return, possibly
    wrapped under a lone ``result`` key) or a single JSON text block."""
    import json

    sc = getattr(call_tool_result, "structuredContent", None)
    if isinstance(sc, dict):
        cand = sc["result"] if set(sc.keys()) == {"result"} else sc
        if isinstance(cand, dict) and cand.get("type") == GATE_RESULT_TYPE:
            return cand
    content = getattr(call_tool_result, "content", None) or []
    if content and getattr(content[0], "type", None) == "text":
        try:
            cand = json.loads(content[0].text)
        except (ValueError, TypeError):
            return None
        if isinstance(cand, dict) and cand.get("type") == GATE_RESULT_TYPE:
            return cand
    return None


def enable_task_results(fastmcp: Any, store: TaskStore) -> None:
    """Wrap the CallTool handler so a gate tool's HANDLE is emitted as a wire
    ``CreateTaskResult`` (``resultType:"task"``) — which a tasks-capable client
    auto-detects (no need to read the tool content to know it's a task). A normal
    tool result passes through unchanged. Call once, after the tools are registered.

    Non-gate tools are untouched; a gate tool whose handle can't be resolved back to
    a live task also passes through as-is (fail-open — never breaks a tool call)."""
    srv = fastmcp._mcp_server
    inner = srv.request_handlers.get(t.CallToolRequest)
    if inner is None:  # no tools registered yet — nothing to wrap
        return

    async def _wrapped(req: t.CallToolRequest) -> t.ServerResult:
        result = await inner(req)
        try:
            inner_result = result.root if isinstance(result, t.ServerResult) else result
            handle = _handle_of(inner_result)
            if handle and handle.get("taskId"):
                task = await store.get(handle["taskId"])
                return t.ServerResult(_create_task_result(task))
        except Exception:  # noqa: BLE001 — a wrap failure must never break tools/call
            pass
        return result

    srv.request_handlers[t.CallToolRequest] = _wrapped


def register_task_endpoints(fastmcp: Any, store: TaskStore, *, tool_prefix: str = "") -> None:
    """Register tasks/get + tasks/cancel handlers and the provide-input tool onto a
    FastMCP server. Call once per server at build time.

    ``tool_prefix`` names the input tool ``<prefix>_task_provide_input`` (e.g.
    ``composition_task_provide_input``). REQUIRED for any domain reached through the
    ai-gateway: the gateway catalog routes by tool NAME, so a bare ``task_provide_input``
    would COLLIDE across task-capable domains and the resume couldn't reach the provider
    that owns the task. Unprefixed (``""``) is only for in-process/kit-test servers."""
    srv = fastmcp._mcp_server
    provide_input_name = f"{tool_prefix}_task_provide_input" if tool_prefix else "task_provide_input"

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

    # CAT-4 visibility:legacy — a MECHANISM tool the client (chat-service's resume
    # driver) calls by NAME; the LLM must never discover it via find_tools. Legacy ⇒
    # excluded from the discoverable set on both surfaces (tool_discovery.py +
    # find-tools.ts), still registered + callable. Mirrors the Go kit's WithVisibility.
    @fastmcp.tool(name=provide_input_name, meta={"visibility": "legacy"})
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
