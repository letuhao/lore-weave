"""plan_run + plan_artifact repository (PlanForge M3).

Tenancy: every method takes owner_user_id first and filters on owner_user_id +
book_id (or run_id scoped to owner). A foreign/missing id returns None — routers
map to 404 (no existence oracle).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import PlanArtifact, PlanArtifactKind, PlanRun, PlanRunMode, PlanRunStatus

_SELECT_RUN = """
  id, owner_user_id, book_id, work_id, status, mode, model_ref, source_checksum,
  source_markdown, active_job_id, error_detail, checkpoint_state, created_at, updated_at
"""

_SELECT_ARTIFACT = "id, run_id, owner_user_id, kind, content, created_at"


def _jsonb(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {})


def _row_run(row: asyncpg.Record) -> PlanRun:
    data = dict(row)
    cs = data.get("checkpoint_state")
    if isinstance(cs, str):
        data["checkpoint_state"] = json.loads(cs)
    return PlanRun.model_validate(data)


def _row_artifact(row: asyncpg.Record) -> PlanArtifact:
    data = dict(row)
    c = data.get("content")
    if isinstance(c, str):
        data["content"] = json.loads(c)
    return PlanArtifact.model_validate(data)


class PlanRunsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        *,
        mode: PlanRunMode,
        source_checksum: str,
        source_markdown: str,
        model_ref: UUID | None = None,
        status: PlanRunStatus = "pending",
    ) -> PlanRun:
        query = f"""
        INSERT INTO plan_run
          (owner_user_id, book_id, mode, model_ref, source_checksum, source_markdown, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING {_SELECT_RUN}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query,
                owner_user_id,
                book_id,
                mode,
                model_ref,
                source_checksum,
                source_markdown,
                status,
            )
        return _row_run(row)

    async def find_by_checksum(
        self, owner_user_id: UUID, book_id: UUID, source_checksum: str, mode: str,
    ) -> PlanRun | None:
        # `mode` is part of the identity of a propose request, not just the text --
        # a user re-Proposing identical markdown after switching Rules -> LLM must
        # get a FRESH run, never the stale other-mode result (D-PLANFORGE-MODE-DEDUPE).
        query = f"""
        SELECT {_SELECT_RUN} FROM plan_run
        WHERE owner_user_id = $1 AND book_id = $2 AND source_checksum = $3 AND mode = $4
        ORDER BY created_at DESC
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, owner_user_id, book_id, source_checksum, mode)
        return _row_run(row) if row else None

    async def get_for_owner(
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID,
    ) -> PlanRun | None:
        query = f"""
        SELECT {_SELECT_RUN} FROM plan_run
        WHERE id = $1 AND owner_user_id = $2 AND book_id = $3
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, owner_user_id, book_id)
        return _row_run(row) if row else None

    async def list_for_owner(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[PlanRun], str | None]:
        params: list[Any] = [owner_user_id, book_id]
        where = ["owner_user_id = $1", "book_id = $2"]
        if cursor:
            try:
                ts_str, id_str = cursor.split("|", 1)
                ts = datetime.fromisoformat(ts_str)
                cid = UUID(id_str)
            except (ValueError, TypeError):
                ts, cid = None, None
            if ts is not None and cid is not None:
                params.extend([ts, cid])
                where.append(
                    f"(created_at, id) < (${len(params) - 1}, ${len(params)})"
                )
        params.append(min(max(limit, 1), 50))
        query = f"""
        SELECT {_SELECT_RUN} FROM plan_run
        WHERE {" AND ".join(where)}
        ORDER BY created_at DESC, id DESC
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
        runs = [_row_run(r) for r in rows]
        next_cursor: str | None = None
        if len(runs) == params[-1] and runs:
            last = runs[-1]
            if last.created_at is not None:
                next_cursor = f"{last.created_at.isoformat()}|{last.id}"
        return runs, next_cursor

    async def update_run(
        self,
        owner_user_id: UUID,
        book_id: UUID,
        run_id: UUID,
        *,
        status: PlanRunStatus | None = None,
        active_job_id: UUID | None = ...,
        error_detail: str | None = ...,
        work_id: UUID | None = None,
        checkpoint_state: dict[str, Any] | None = None,
        clear_error: bool = False,
    ) -> PlanRun | None:
        sets: list[str] = ["updated_at = now()"]
        params: list[Any] = [run_id, owner_user_id, book_id]
        if status is not None:
            params.append(status)
            sets.append(f"status = ${len(params)}")
        if active_job_id is not ...:
            if active_job_id is None:
                sets.append("active_job_id = NULL")
            else:
                params.append(active_job_id)
                sets.append(f"active_job_id = ${len(params)}")
        if error_detail is not ...:
            if error_detail is None and not clear_error:
                pass
            elif error_detail is None:
                sets.append("error_detail = NULL")
            else:
                params.append(error_detail)
                sets.append(f"error_detail = ${len(params)}")
        elif clear_error:
            sets.append("error_detail = NULL")
        if work_id is not None:
            params.append(work_id)
            sets.append(f"work_id = ${len(params)}")
        if checkpoint_state is not None:
            params.append(_jsonb(checkpoint_state))
            sets.append(f"checkpoint_state = ${len(params)}::jsonb")
        query = f"""
        UPDATE plan_run SET {", ".join(sets)}
        WHERE id = $1 AND owner_user_id = $2 AND book_id = $3
        RETURNING {_SELECT_RUN}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        return _row_run(row) if row else None

    async def save_artifact(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        kind: PlanArtifactKind,
        content: dict[str, Any],
    ) -> PlanArtifact:
        query = f"""
        INSERT INTO plan_artifact (run_id, owner_user_id, kind, content)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING {_SELECT_ARTIFACT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, run_id, owner_user_id, kind, _jsonb(content),
            )
        return _row_artifact(row)

    async def latest_artifact(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        kind: PlanArtifactKind,
    ) -> PlanArtifact | None:
        query = f"""
        SELECT {_SELECT_ARTIFACT} FROM plan_artifact
        WHERE run_id = $1 AND owner_user_id = $2 AND kind = $3
        ORDER BY created_at DESC
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, owner_user_id, kind)
        return _row_artifact(row) if row else None

    async def list_artifact_refs(
        self, owner_user_id: UUID, run_id: UUID,
    ) -> list[dict[str, Any]]:
        query = """
        SELECT DISTINCT ON (kind) kind, id AS artifact_id
        FROM plan_artifact
        WHERE run_id = $1 AND owner_user_id = $2
        ORDER BY kind, created_at DESC
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, run_id, owner_user_id)
        return [{"kind": r["kind"], "artifact_id": r["artifact_id"]} for r in rows]
