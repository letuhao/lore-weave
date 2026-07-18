"""WS-2.6c (D17 forget-a-person) — the pending-inbox tombstone leg, against real Postgres.

`PendingFactsRepo.tombstone_by_subject` deletes every PENDING fact about the forgotten person AND writes
a `knowledge_rejected_facts` tombstone on each dedup_key, so a later re-distill can't re-propose them
(no resurrection). Case-insensitive subject match; owner+project scoped; a different subject survives.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.repositories.pending_facts import PendingFactsRepo

pytestmark = pytest.mark.xdist_group("pg")


async def _seed_pending(conn, *, user_id, project_id, subject, dedup_key):
    await conn.execute(
        """
        INSERT INTO knowledge_pending_facts
          (user_id, project_id, session_id, fact_type, fact_text, dedup_key, subject, provenance)
        VALUES ($1, $2, NULL, 'statement', $3, $4, $5, 'user')
        """,
        user_id, project_id, f"[person] {subject} did a thing", dedup_key, subject,
    )


@pytest_asyncio.fixture
async def _ids(pool):
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    yield user_id, project_id
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM knowledge_pending_facts WHERE user_id=$1", user_id)
        await conn.execute("DELETE FROM knowledge_rejected_facts WHERE user_id=$1", user_id)


@pytest.mark.asyncio
async def test_ws26c_tombstone_by_subject_removes_and_tombstones(pool, _ids):
    user_id, project_id = _ids
    async with pool.acquire() as conn:
        await _seed_pending(conn, user_id=user_id, project_id=project_id, subject="Minh", dedup_key="k-minh-1")
        await _seed_pending(conn, user_id=user_id, project_id=project_id, subject="minh", dedup_key="k-minh-2")
        await _seed_pending(conn, user_id=user_id, project_id=project_id, subject="Alice", dedup_key="k-alice")

    removed = await PendingFactsRepo(pool).tombstone_by_subject(user_id, project_id, "Minh")
    assert removed == 2  # both "Minh" and "minh" (case-insensitive)

    async with pool.acquire() as conn:
        # The two Minh rows are gone; Alice survives.
        remaining = await conn.fetch(
            "SELECT subject FROM knowledge_pending_facts WHERE user_id=$1", user_id)
        assert {r["subject"] for r in remaining} == {"Alice"}
        # Tombstones exist on both Minh dedup_keys → a re-distill can't re-propose them.
        tombs = await conn.fetch(
            "SELECT dedup_key FROM knowledge_rejected_facts WHERE user_id=$1", user_id)
        assert {t["dedup_key"] for t in tombs} == {"k-minh-1", "k-minh-2"}


@pytest.mark.asyncio
async def test_ws26c_tombstone_by_subject_is_idempotent_and_empty_name_noops(pool, _ids):
    user_id, project_id = _ids
    async with pool.acquire() as conn:
        await _seed_pending(conn, user_id=user_id, project_id=project_id, subject="Minh", dedup_key="k1")
    repo = PendingFactsRepo(pool)
    assert await repo.tombstone_by_subject(user_id, project_id, "  ") == 0  # empty name no-ops
    assert await repo.tombstone_by_subject(user_id, project_id, "Minh") == 1
    assert await repo.tombstone_by_subject(user_id, project_id, "Minh") == 0  # idempotent re-run
