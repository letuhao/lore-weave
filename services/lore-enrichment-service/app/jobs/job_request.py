"""Job-request persistence + done-gap lookup for the resume worker (F-C14-1/051).

Standalone pool-based helpers (mirroring ``load_spent_so_far``) so the create
path can persist the request and the background resume worker can rebuild the
runner + skip already-done gaps. NO store-interface changes — the in-memory test
store stays untouched; these query Postgres directly.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

__all__ = ["save_job_request", "load_job_request", "existing_gap_refs"]


async def save_job_request(
    *, pool: asyncpg.Pool, job_id: UUID, request: dict[str, Any]
) -> None:
    """Persist the request payload needed to re-drive the job on resume. One row
    per job (idempotent upsert). Stores ONLY the request shape — targets +
    provider-registry model_ref UUIDs + technique/params — never enriched content."""
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO enrichment_job_request(job_id, request_json)
               VALUES ($1, $2::jsonb)
               ON CONFLICT (job_id) DO UPDATE SET request_json = EXCLUDED.request_json""",
            job_id, json.dumps(request),
        )


async def load_job_request(
    *, pool: asyncpg.Pool, job_id: UUID
) -> dict[str, Any] | None:
    """Read the persisted request for a job, or None if absent (an older job
    created before this table → resume cannot re-drive it)."""
    async with pool.acquire() as conn:
        raw = await conn.fetchval(
            "SELECT request_json FROM enrichment_job_request WHERE job_id=$1", job_id
        )
    if raw is None:
        return None
    # asyncpg returns jsonb as str unless a codec is registered — handle both.
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


async def existing_gap_refs(*, pool: asyncpg.Pool, job_id: UUID) -> set[str]:
    """The gap_refs already turned into a persisted proposal for this job. The
    resume worker passes these to run_job(skip_gap_refs=...) so an already-done
    gap costs neither budget nor an LLM call (the token-safe convergence fix)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT gap_ref FROM enrichment_proposal WHERE job_id=$1 AND gap_ref IS NOT NULL",
            job_id,
        )
    return {r["gap_ref"] for r in rows}
