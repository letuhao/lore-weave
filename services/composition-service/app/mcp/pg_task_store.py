"""ext-tasks durable-gate PERSISTENT store — asyncpg (M1c).

The Python mirror of book-service's Go PgTaskStore (D-MCPTASKS-GO-STORE): a Postgres-
backed lwmcp.TaskStore so a propose on one replica and its accept on another (or after a
restart/deploy) resolve the SAME task exactly once. It persists only DATA
({descriptor, owner_user_id, payload}); the write to run on accept is the resolver
registered for the descriptor (reconstructed on any replica — no closure). The accept is
an ATOMIC single-winner UPDATE (input_required→working), so two concurrent accepts can't
both run the resolver (the double-confirm guard).

Constructed with a pool GETTER (not a pool): the store is built at module import, before
the asyncpg pool exists — the getter is called lazily per operation.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

import asyncpg

from loreweave_mcp.tasks import (
    CANCELLED,
    COMPLETED,
    DEFAULT_POLL_INTERVAL_MS,
    DEFAULT_TTL_MS,
    FAILED,
    INPUT_REQUIRED,
    ResolverRegistry,
    Task,
    TaskNotFound,
    TaskNotWaiting,
    TaskStore,
    TERMINAL,
)

_COLS = (
    "task_id, status, descriptor, owner_user_id, payload, input_requests, "
    "result, error, ttl_ms, poll_interval_ms, created_at, updated_at"
)


def _as_uuid(v: Any) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))


def _is_decline(inputs: dict[str, Any]) -> bool:
    return bool(inputs) and (inputs.get("action") == "decline" or inputs.get("accepted") is False)


class PgTaskStore(TaskStore):
    def __init__(
        self,
        pool_getter: Callable[[], asyncpg.Pool],
        resolvers: Optional[ResolverRegistry] = None,
    ) -> None:
        self._pool_getter = pool_getter
        self._resolvers: ResolverRegistry = dict(resolvers or {})

    def _row_to_task(self, row: asyncpg.Record) -> Task:
        return Task(
            task_id=row["task_id"],
            status=row["status"],
            descriptor=row["descriptor"],
            owner_user_id=str(row["owner_user_id"]),
            payload=json.loads(row["payload"]) if row["payload"] else {},
            input_requests=json.loads(row["input_requests"]) if row["input_requests"] else None,
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            ttl_ms=row["ttl_ms"],
            poll_interval_ms=row["poll_interval_ms"],
            created_at=row["created_at"].timestamp(),
            updated_at=row["updated_at"].timestamp(),
        )

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
        row = await self._pool_getter().fetchrow(
            f"""
            INSERT INTO mcp_gate_tasks
                (task_id, status, descriptor, owner_user_id, payload, input_requests, ttl_ms, poll_interval_ms)
            VALUES ($1, 'input_required', $2, $3, $4::jsonb, $5::jsonb, $6, $7)
            RETURNING {_COLS}
            """,
            tid, descriptor, _as_uuid(owner_user_id),
            json.dumps(payload or {}), json.dumps(input_requests) if input_requests is not None else None,
            ttl_ms, poll_interval_ms,
        )
        return self._row_to_task(row)

    async def get(self, task_id: str, *, now: Optional[float] = None) -> Task:
        pool = self._pool_getter()
        row = await pool.fetchrow(f"SELECT {_COLS} FROM mcp_gate_tasks WHERE task_id=$1", task_id)
        if row is None:
            raise TaskNotFound(task_id)
        task = self._row_to_task(row)
        # Lazy TTL lapse: a non-terminal task past its TTL becomes failed/task_expired
        # (the token_expired analogue) so the client stops polling and re-proposes.
        if task.status not in TERMINAL and task.expired(now=now):
            lapsed = await pool.fetchrow(
                f"""
                UPDATE mcp_gate_tasks SET status='failed', error='task_expired', updated_at=now()
                WHERE task_id=$1 AND status NOT IN ('completed','failed','cancelled')
                RETURNING {_COLS}
                """,
                task_id,
            )
            if lapsed is not None:
                return self._row_to_task(lapsed)
        return task

    async def provide_input(self, task_id: str, inputs: dict[str, Any]) -> Task:
        pool = self._pool_getter()
        # A decline short-circuits to cancelled WITHOUT running the resolver — atomically,
        # only while still awaiting input.
        if _is_decline(inputs):
            row = await pool.fetchrow(
                f"""
                UPDATE mcp_gate_tasks SET status='cancelled', updated_at=now()
                WHERE task_id=$1 AND status='input_required'
                RETURNING {_COLS}
                """,
                task_id,
            )
            if row is not None:
                return self._row_to_task(row)
            return await self._not_waiting_or_not_found(pool, task_id)

        # CLAIM: input_required → working, single-winner across replicas (excludes expired).
        claimed = await pool.fetchrow(
            f"""
            UPDATE mcp_gate_tasks SET status='working', updated_at=now()
            WHERE task_id=$1 AND status='input_required'
              AND (EXTRACT(EPOCH FROM (now()-created_at)) * 1000) < ttl_ms
            RETURNING {_COLS}
            """,
            task_id,
        )
        if claimed is None:
            return await self._not_waiting_or_not_found(pool, task_id)
        task = self._row_to_task(claimed)

        # Run the resolver OUTSIDE any transaction, reconstructed from the persisted
        # {descriptor, owner, payload} (never a closure). A missing resolver is a wiring
        # bug → fail with a clear message (never a silent no-op).
        resolver = self._resolvers.get(task.descriptor)
        result: Any = None
        err: Optional[str] = None
        try:
            if resolver is None:
                raise RuntimeError(f"no resolver registered for descriptor {task.descriptor!r}")
            result = await resolver(task.owner_user_id, task.payload, inputs)
        except Exception as exc:  # noqa: BLE001 — the write failed → failed status
            err = str(exc) or exc.__class__.__name__

        # Write the terminal outcome. We own the 'working' claim (cancel only touches
        # input_required), so no status guard is needed.
        status = FAILED if err is not None else COMPLETED
        row = await pool.fetchrow(
            f"""
            UPDATE mcp_gate_tasks SET status=$2, result=$3::jsonb, error=$4, updated_at=now()
            WHERE task_id=$1
            RETURNING {_COLS}
            """,
            task_id, status,
            json.dumps(result) if result is not None else None, err,
        )
        return self._row_to_task(row)

    async def cancel(self, task_id: str) -> Task:
        pool = self._pool_getter()
        # Cancel only a task still awaiting input — a 'working' task is mid-resolve and
        # must reach its real outcome (cooperative cancel, per the ext-tasks spec).
        row = await pool.fetchrow(
            f"""
            UPDATE mcp_gate_tasks SET status='cancelled', updated_at=now()
            WHERE task_id=$1 AND status='input_required'
            RETURNING {_COLS}
            """,
            task_id,
        )
        if row is not None:
            return self._row_to_task(row)
        cur = await pool.fetchrow(f"SELECT {_COLS} FROM mcp_gate_tasks WHERE task_id=$1", task_id)
        if cur is None:
            raise TaskNotFound(task_id)
        return self._row_to_task(cur)  # terminal → idempotent; working → cooperative (unchanged)

    async def _not_waiting_or_not_found(self, pool: asyncpg.Pool, task_id: str) -> Task:
        """Distinguish a missing task (TaskNotFound) from one no longer awaiting input
        (terminal / already-claimed / expired → TaskNotWaiting), lazily lapsing an expired
        task to failed first (parity with get)."""
        cur = await pool.fetchrow(f"SELECT {_COLS} FROM mcp_gate_tasks WHERE task_id=$1", task_id)
        if cur is None:
            raise TaskNotFound(task_id)
        task = self._row_to_task(cur)
        if task.status not in TERMINAL and task.expired():
            await pool.execute(
                """
                UPDATE mcp_gate_tasks SET status='failed', error='task_expired', updated_at=now()
                WHERE task_id=$1 AND status NOT IN ('completed','failed','cancelled')
                """,
                task_id,
            )
        raise TaskNotWaiting(f"task {task_id} is {task.status}")
