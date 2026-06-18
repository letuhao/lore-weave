"""M2 status-CAS + cost-write + M1 advisory-key SQL against a REAL Postgres
(review-impl LOW-2).

The unit tests use InMemoryProposalStore which MODELS the `only_if_status` CAS, but
nothing exercises the real `status = ANY($n::text[])` UPDATE, the status-preserving
`record_actual_cost`, or the `('x' || substr(...))::bit(64)::bigint` advisory-key
cast. This pins all three against Postgres so a future edit to those literals can't
pass unit and break live. Skips when no real DB is reachable (conftest)."""

from __future__ import annotations

import uuid

import pytest

from app.jobs.proposal_store import PgProposalStore
from app.worker.resume_consumer import _JOB_LOCK_KEY_SQL

pytestmark = pytest.mark.asyncio


async def _new_job(store: PgProposalStore, status: str) -> str:
    job_id = await store.create_job(
        user_id=str(uuid.uuid4()), project_id=str(uuid.uuid4()),
        technique="retrieval", entity_kind="location",
        max_spend=None, estimated_cost=0.0,
    )
    if status != "pending":
        await store.mark_job_status(job_id=job_id, status=status)
    return job_id


async def test_mark_job_status_cas_applies_and_noops(pool):
    """The guarded UPDATE no-ops (returns False, status unchanged) on a mismatch and
    applies (returns True) on a match — the real `status = ANY($n::text[])` SQL."""
    store = PgProposalStore(pool)
    job_id = await _new_job(store, "running")

    # mismatch → no row updated → False, status unchanged
    applied = await store.mark_job_status(
        job_id=job_id, status="completed", only_if_status=("paused",)
    )
    assert applied is False
    assert await store.read_job_status(job_id=job_id) == "running"

    # match → applies → True
    applied = await store.mark_job_status(
        job_id=job_id, status="completed", only_if_status=("running",)
    )
    assert applied is True
    assert await store.read_job_status(job_id=job_id) == "completed"


async def test_record_actual_cost_guarded_no_status_change(pool):
    """record_actual_cost writes actual_cost_usd WITHOUT changing status, guarded on
    only_if_status (the M2 interrupt path's cost-preservation, LOW-3)."""
    store = PgProposalStore(pool)
    job_id = await _new_job(store, "cancelled")

    await store.record_actual_cost(
        job_id=job_id, actual_cost=1.25, only_if_status=("cancelled",)
    )
    assert await store.read_job_status(job_id=job_id) == "cancelled"  # status untouched
    async with pool.acquire() as conn:
        cost = await conn.fetchval(
            "SELECT actual_cost_usd FROM enrichment_job WHERE job_id=$1", uuid.UUID(job_id)
        )
    assert float(cost) == pytest.approx(1.25)

    # guard mismatch → no write
    await store.record_actual_cost(
        job_id=job_id, actual_cost=9.99, only_if_status=("running",)
    )
    async with pool.acquire() as conn:
        cost = await conn.fetchval(
            "SELECT actual_cost_usd FROM enrichment_job WHERE job_id=$1", uuid.UUID(job_id)
        )
    assert float(cost) == pytest.approx(1.25)  # unchanged


async def test_advisory_lock_key_sql_valid_and_lockable(pool):
    """The M1 claim key derivation (`('x'||substr(...))::bit(64)::bigint`) is valid PG
    and the derived bigint is a usable advisory-lock key on the SAME session."""
    job_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        key = await conn.fetchval(_JOB_LOCK_KEY_SQL, job_id)
        assert isinstance(key, int)
        assert await conn.fetchval("SELECT pg_try_advisory_lock($1)", key) is True
        # same key, same session → owns it → unlock returns True (the production path)
        assert await conn.fetchval("SELECT pg_advisory_unlock($1)", key) is True
