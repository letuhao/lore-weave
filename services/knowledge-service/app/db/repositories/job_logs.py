"""K19b.8 — Extraction job log repository.

Append-only event log for extraction jobs. The worker writes via an
inline SQL helper (same pattern as `_try_spend`), so this repo is
read-centric — only used by the public GET endpoint that powers the
JobLogsPanel.

SECURITY RULE: every read filters on BOTH user_id AND job_id. The
FK on job_id → extraction_jobs provides defence-in-depth, but the
explicit user_id predicate is the primary authorization gate.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ConfigDict

__all__ = ["JobLog", "JobLogLevel", "JobLogsRepo", "LOGS_MAX_LIMIT"]

JobLogLevel = Literal["info", "warning", "error"]

# Shared upper bound between the router's Query validator and the
# repo's LIMIT clamp. Same rationale as LIST_ALL_MAX_LIMIT on
# extraction_jobs (K19b.1 review-code): one source of truth prevents
# drift if the cap is raised.
LOGS_MAX_LIMIT = 200


class JobLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    job_id: UUID
    user_id: UUID
    level: JobLogLevel
    message: str
    context: dict[str, Any]
    created_at: datetime


class JobLogsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self,
        user_id: UUID,
        job_id: UUID,
        level: JobLogLevel,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> int:
        """Insert a log row and return the generated log_id.

        Worker doesn't use this path (it writes inline SQL to avoid an
        HTTP round-trip), but the knowledge-service orchestrator can
        call here when its richer pipeline logs land in a future
        cycle (D-K19b.8-02).
        """
        row = await self._pool.fetchrow(
            """
            INSERT INTO job_logs (job_id, user_id, level, message, context)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING log_id
            """,
            job_id,
            user_id,
            level,
            message,
            json.dumps(context or {}),
        )
        return row["log_id"]

    async def list(
        self,
        user_id: UUID,
        job_id: UUID,
        *,
        since_log_id: int = 0,
        limit: int = 50,
    ) -> list[JobLog]:
        """Cursor-paginated: rows with log_id > ``since_log_id``, ASC
        by log_id (so the FE renders in time order), clamped at
        ``LOGS_MAX_LIMIT``.
        """
        effective_limit = max(1, min(limit, LOGS_MAX_LIMIT))
        query = f"""
        SELECT log_id, job_id, user_id, level, message, context, created_at
        FROM job_logs
        WHERE user_id = $1
          AND job_id = $2
          AND log_id > $3
        ORDER BY log_id ASC
        LIMIT {effective_limit}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, job_id, since_log_id)
        out: list[JobLog] = []
        for r in rows:
            data = dict(r)
            ctx = data.get("context")
            if isinstance(ctx, str):
                data["context"] = json.loads(ctx)
            out.append(JobLog.model_validate(data))
        return out
