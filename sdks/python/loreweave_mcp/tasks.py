"""ext-tasks durable-gate CORE — the task store + lifecycle (T1a).

The keystone of the MCP-Tasks durable human gate (spec
``docs/specs/2026-07-19-mcp-tasks-durable-gate.md``). This module is the pure,
transport-free heart: a durable task store + the ``input_required → completed |
cancelled | failed`` lifecycle. The FastMCP wire wiring (tasks/get, tasks/cancel,
the CallTool→CreateTaskResult override, the input-step tool) lives in a sibling
``tasks_wire`` module (T1b) that builds on this.

WHY hand-rolled (see spec §6.1): the mcp 1.28.1 experimental Tasks API is REMOVED
in mcp 2.0 (Tasks → the standalone ``ext-tasks`` extension). We implement the small
``ext-tasks`` wire lifecycle ourselves, over our own store, so we depend on nothing
experimental and stay aligned with the returning extension. This core is stdlib-only
so it is trivially unit-testable and reusable by any transport (FastMCP handlers now;
a Go-facade mirror later).

STATUS lifecycle (ext-tasks):
    created ──(gate)──> input_required ──(provide_input accept)──> completed
                                        ──(provide_input decline)─> cancelled
                                        ──(cancel)────────────────> cancelled
                                        ──(executor raises)───────> failed
    input_required/working may also lapse to ``failed`` on TTL expiry (like the
    confirm_token ``token_expired`` outcome), surfaced on the next ``get``.

The store is DURABLE-by-contract: this in-memory implementation is the reference +
test double; a persistent implementation (bound to the domain's confirm-token /
suspended-run store) subclasses/implements the same surface for production (T3).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

__all__ = [
    "TaskStatus",
    "WORKING",
    "INPUT_REQUIRED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TERMINAL",
    "Task",
    "TaskStore",
    "InMemoryTaskStore",
    "TaskNotFound",
    "TaskNotWaiting",
]

# ── status (ext-tasks wire values) ───────────────────────────────────────────
TaskStatus = str
WORKING: TaskStatus = "working"
INPUT_REQUIRED: TaskStatus = "input_required"
COMPLETED: TaskStatus = "completed"
FAILED: TaskStatus = "failed"
CANCELLED: TaskStatus = "cancelled"
TERMINAL: frozenset[str] = frozenset({COMPLETED, FAILED, CANCELLED})

# Default poll interval the server suggests to the client (ms). Small — the gate is
# human-paced; a snappy poll keeps the card responsive without hammering.
DEFAULT_POLL_INTERVAL_MS = 1000
DEFAULT_TTL_MS = 600_000  # 10 min — mirrors the confirm-token DEFAULT_TTL_S.


class TaskNotFound(KeyError):
    """No task with that id (never minted, or swept after a terminal TTL)."""


class TaskNotWaiting(RuntimeError):
    """provide_input / cancel on a task that is already terminal (idempotency +
    double-confirm guard: a second accept must NOT re-run the executor)."""


# The executor a gate binds: run the real domain write on accept; its return value
# becomes the task ``result`` (what the original tools/call would have returned).
# ``inputs`` carries the human's response payload (e.g. edited scalar fields).
Executor = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass
class Task:
    task_id: str
    status: TaskStatus
    descriptor: str  # the action descriptor, e.g. "book.publish" — for the card
    # The rich card payload the client renders as input_requests (title, preview,
    # the diff/confirm details). Opaque to the store.
    input_requests: Any = None
    result: Any = None  # set on completed — the real tool result
    error: Optional[str] = None  # set on failed
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl_ms: int = DEFAULT_TTL_MS
    poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS
    # The bound executor + captured context, never serialized to the client.
    _executor: Optional[Executor] = None

    def expired(self, *, now: Optional[float] = None) -> bool:
        t = time.time() if now is None else now
        return (t - self.created_at) * 1000.0 >= self.ttl_ms


class TaskStore:
    """The durable task-store surface. In-memory reference below; a persistent
    impl (bound to confirm-token/suspended-run storage) implements the same API."""

    async def create(
        self,
        *,
        descriptor: str,
        executor: Executor,
        input_requests: Any = None,
        ttl_ms: int = DEFAULT_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        task_id: Optional[str] = None,
    ) -> Task:
        raise NotImplementedError

    async def get(self, task_id: str, *, now: Optional[float] = None) -> Task:
        raise NotImplementedError

    async def provide_input(self, task_id: str, inputs: dict[str, Any]) -> Task:
        raise NotImplementedError

    async def cancel(self, task_id: str) -> Task:
        raise NotImplementedError


class InMemoryTaskStore(TaskStore):
    """Reference + test-double store. Durable-by-contract API; volatile storage.

    Concurrency: guarded so two ``provide_input`` calls for one task can't both run
    the executor (the double-confirm race — the exact class ``chat_suspended_runs``
    already handles). The winner runs; the loser sees the terminal state.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        # per-task in-flight flag so provide_input is single-winner without an
        # async lock dependency (the executor await must not block other tasks).
        self._resolving: set[str] = set()

    async def create(
        self,
        *,
        descriptor: str,
        executor: Executor,
        input_requests: Any = None,
        ttl_ms: int = DEFAULT_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        task_id: Optional[str] = None,
    ) -> Task:
        if not descriptor or not descriptor.strip():
            raise ValueError("task descriptor is required")
        tid = task_id or f"task_{uuid.uuid4().hex}"
        task = Task(
            task_id=tid,
            status=INPUT_REQUIRED,  # a confirm gate needs the human immediately
            descriptor=descriptor,
            input_requests=input_requests,
            ttl_ms=ttl_ms,
            poll_interval_ms=poll_interval_ms,
            _executor=executor,
        )
        self._tasks[tid] = task
        return task

    async def get(self, task_id: str, *, now: Optional[float] = None) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        # Lazy TTL: a non-terminal task past its TTL lapses to failed (token_expired
        # analogue) so the client stops polling and the model re-proposes.
        if task.status not in TERMINAL and task.expired(now=now):
            task.status = FAILED
            task.error = "task_expired"
            task.updated_at = time.time() if now is None else now
        return task

    async def provide_input(self, task_id: str, inputs: dict[str, Any]) -> Task:
        task = await self.get(task_id)
        if task.status in TERMINAL:
            raise TaskNotWaiting(f"task {task_id} is {task.status}")
        if task_id in self._resolving:
            raise TaskNotWaiting(f"task {task_id} is already resolving")

        # A decline/cancel signal in the inputs short-circuits to cancelled.
        if inputs.get("action") == "decline" or inputs.get("accepted") is False:
            task.status = CANCELLED
            task.updated_at = time.time()
            return task

        self._resolving.add(task_id)
        try:
            task.status = WORKING
            task.updated_at = time.time()
            try:
                result = await task._executor(inputs) if task._executor else None
                task.result = result
                task.status = COMPLETED
            except Exception as exc:  # noqa: BLE001 — the write failed → failed status
                task.status = FAILED
                task.error = str(exc) or exc.__class__.__name__
            task.updated_at = time.time()
            return task
        finally:
            self._resolving.discard(task_id)

    async def cancel(self, task_id: str) -> Task:
        task = await self.get(task_id)
        if task.status in TERMINAL:
            return task  # cancel is idempotent on a terminal task (cooperative)
        task.status = CANCELLED
        task.updated_at = time.time()
        return task
