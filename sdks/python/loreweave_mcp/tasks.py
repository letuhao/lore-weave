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
    "Resolver",
    "ResolverRegistry",
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


# A resolver runs the real domain write on accept, RECONSTRUCTED on any replica from
# persisted data (NOT a closure over per-request state). Registered once per descriptor
# at startup; receives the durable inputs — the proposing user (owner_user_id), the
# serializable ``payload`` captured at propose-time, and the human's response
# (``inputs``). Its return becomes the task ``result``. This shape is what makes a
# DB-backed store possible: the persistent store stores {descriptor, owner_user_id,
# payload} and looks the resolver up by descriptor, so one interface serves single-
# process and multi-replica.
Resolver = Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[Any]]
ResolverRegistry = dict[str, Resolver]


@dataclass
class Task:
    task_id: str
    status: TaskStatus
    descriptor: str  # the action descriptor, e.g. "book.publish" — also the resolver key
    owner_user_id: str = ""  # the proposing user (tenancy scope key; passed to the resolver)
    payload: dict[str, Any] = field(default_factory=dict)  # serializable action data captured at propose-time
    # The rich card payload the client renders as input_requests (title, preview,
    # the diff/confirm details). Opaque to the store.
    input_requests: Any = None
    result: Any = None  # set on completed — the real tool result
    error: Optional[str] = None  # set on failed
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl_ms: int = DEFAULT_TTL_MS
    poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS

    def expired(self, *, now: Optional[float] = None) -> bool:
        t = time.time() if now is None else now
        return (t - self.created_at) * 1000.0 >= self.ttl_ms


class TaskStore:
    """The durable task-store surface. In-memory reference below; a persistent
    impl (bound to confirm-token/suspended-run storage) implements the same API.
    Both are constructed with a resolver registry — never a closure."""

    async def create(
        self,
        *,
        descriptor: str,
        owner_user_id: str,
        payload: dict[str, Any],
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

    def __init__(self, resolvers: Optional[ResolverRegistry] = None) -> None:
        self._tasks: dict[str, Task] = {}
        # per-task in-flight flag so provide_input is single-winner without an
        # async lock dependency (the resolver await must not block other tasks).
        self._resolving: set[str] = set()
        # descriptor → resolver (the write to run on accept). The store holds NO
        # closure; a task whose descriptor has no resolver fails on accept.
        self._resolvers: ResolverRegistry = dict(resolvers or {})

    async def create(
        self,
        *,
        descriptor: str,
        owner_user_id: str,
        payload: dict[str, Any],
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
            owner_user_id=owner_user_id,
            payload=dict(payload or {}),
            input_requests=input_requests,
            ttl_ms=ttl_ms,
            poll_interval_ms=poll_interval_ms,
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
            # Look the resolver up by descriptor from the startup registry —
            # reconstructed on any replica from {descriptor, owner_user_id, payload},
            # never a closure. A missing resolver is a wiring bug → fail with a clear
            # error (never a silent no-op).
            resolver = self._resolvers.get(task.descriptor)
            try:
                if resolver is None:
                    raise RuntimeError(f"no resolver registered for descriptor {task.descriptor!r}")
                result = await resolver(task.owner_user_id, task.payload, inputs)
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
