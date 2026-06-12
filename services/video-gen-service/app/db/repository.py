"""video_gen_jobs repository (LLM re-arch Phase 3 M5).

Thin asyncpg data layer for the decoupled video-gen job row. Mirrors the M1
judge repo / composition generation_jobs repo shape: create on submit, look up
by (user, id) for the poll endpoint, by provider_job_id for the terminal-event
consumer, and a CAS terminal transition so an at-least-once redelivery (or the
sweeper racing the consumer) marks the row done exactly once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

_ACTIVE = ("pending", "running")


@dataclass(frozen=True)
class VideoGenJob:
    id: UUID
    user_id: UUID
    provider_job_id: UUID | None
    status: str
    request_json: dict[str, Any]
    video_url: str | None
    size_bytes: int | None
    content_type: str | None
    error_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


def _row(r: asyncpg.Record | None) -> VideoGenJob | None:
    if r is None:
        return None
    return VideoGenJob(
        id=r["id"],
        user_id=r["user_id"],
        provider_job_id=r["provider_job_id"],
        status=r["status"],
        request_json=_json(r["request_json"]),
        video_url=r["video_url"],
        size_bytes=r["size_bytes"],
        content_type=r["content_type"],
        error_json=_json(r["error_json"]) if r["error_json"] is not None else None,
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _json(v: Any) -> dict[str, Any]:
    if v is None:
        return {}
    return v if isinstance(v, dict) else json.loads(v)


_COLS = (
    "id, user_id, provider_job_id, status, request_json, video_url, "
    "size_bytes, content_type, error_json, created_at, updated_at"
)


class VideoGenJobsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        *,
        user_id: UUID,
        provider_job_id: UUID,
        request_json: dict[str, Any],
    ) -> VideoGenJob:
        """INSERT a pending row with the gateway job id already set (M5 submits
        first, so there is no submit→persist gap on the create path)."""
        row = await self._pool.fetchrow(
            f"""
            INSERT INTO video_gen_jobs (user_id, provider_job_id, status, request_json)
            VALUES ($1, $2, 'pending', $3::jsonb)
            RETURNING {_COLS}
            """,
            user_id, provider_job_id, json.dumps(request_json),
        )
        job = _row(row)
        assert job is not None
        return job

    async def get(self, user_id: UUID, job_id: UUID) -> VideoGenJob | None:
        """The poll endpoint's read — scoped to the owner (404 cross-user)."""
        row = await self._pool.fetchrow(
            f"SELECT {_COLS} FROM video_gen_jobs WHERE id = $1 AND user_id = $2",
            job_id, user_id,
        )
        return _row(row)

    async def get_by_provider_job_id(self, provider_job_id: UUID) -> VideoGenJob | None:
        """The consumer's match — is this terminal event one of OUR jobs?"""
        row = await self._pool.fetchrow(
            f"SELECT {_COLS} FROM video_gen_jobs WHERE provider_job_id = $1",
            provider_job_id,
        )
        return _row(row)

    async def mark_running(self, job_id: UUID) -> None:
        await self._pool.execute(
            "UPDATE video_gen_jobs SET status = 'running', updated_at = now() "
            "WHERE id = $1 AND status = 'pending'",
            job_id,
        )

    async def complete(
        self,
        job_id: UUID,
        *,
        video_url: str,
        size_bytes: int,
        content_type: str,
    ) -> bool:
        """CAS the row to completed (only from an active state). Returns True if
        THIS call won the transition — the caller bills only on a True so an
        at-least-once redelivery / sweeper race never double-bills."""
        won = await self._pool.fetchval(
            """
            UPDATE video_gen_jobs
               SET status = 'completed', video_url = $2, size_bytes = $3,
                   content_type = $4, error_json = NULL, updated_at = now()
             WHERE id = $1 AND status = ANY($5::text[])
            RETURNING id
            """,
            job_id, video_url, size_bytes, content_type, list(_ACTIVE),
        )
        return won is not None

    async def fail(
        self, job_id: UUID, *, status: str, error: dict[str, Any] | None
    ) -> bool:
        """CAS the row to a terminal failed/cancelled (only from an active
        state). Returns True if THIS call won the transition."""
        won = await self._pool.fetchval(
            """
            UPDATE video_gen_jobs
               SET status = $2, error_json = $3::jsonb, updated_at = now()
             WHERE id = $1 AND status = ANY($4::text[])
            RETURNING id
            """,
            job_id, status, json.dumps(error) if error is not None else None,
            list(_ACTIVE),
        )
        return won is not None

    async def list_stuck(self, *, timeout_secs: int, batch: int) -> list[VideoGenJob]:
        """Active rows idle past the timeout — the sweeper's re-drive set."""
        rows = await self._pool.fetch(
            f"""
            SELECT {_COLS} FROM video_gen_jobs
             WHERE status = ANY($1::text[])
               AND updated_at < now() - make_interval(secs => $2::int)
             ORDER BY updated_at ASC
             LIMIT $3::int
            """,
            list(_ACTIVE), timeout_secs, batch,
        )
        return [j for j in (_row(r) for r in rows) if j is not None]
