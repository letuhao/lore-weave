"""C2 — H0 lifecycle round-trip against a REAL Postgres (no mock-only pass).

H0 INVARIANT: enriched lore != canon. This test drives a proposal through
the full lifecycle and asserts every schema-level guard fires:

  * proposed → author_reviewing → approved → promoted retains origin marker
    and stamps promoted_from_proposal_id / original_technique / promoted_*;
  * a rejected terminal branch works;
  * illegal jumps (proposed → promoted) are blocked by the trigger;
  * confidence can never reach 1.0 (insert CHECK + update trigger);
  * origin is immutable (cannot be stripped or set to canon 'glossary');
  * promoted_* may only be populated at promote.

Skips when no real DB is reachable; verify-cycle-2.sh supplies it.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio

_PROJECT = uuid.uuid4()
_USER = uuid.uuid4()


async def _seed_job(conn) -> uuid.UUID:
    return await conn.fetchval(
        """
        INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
        VALUES ($1, $2, 'template', 'location')
        RETURNING job_id
        """,
        _PROJECT,
        _USER,
    )


async def _seed_proposal(conn, job_id: uuid.UUID) -> uuid.UUID:
    # 玉虛宮 = one of the LOCKED Fengshen demo places (CJK round-trip canary).
    return await conn.fetchval(
        """
        INSERT INTO enrichment_proposal
          (job_id, project_id, user_id, entity_kind, target_ref, content,
           technique, confidence, provenance_json)
        VALUES ($1,$2,$3,'location','玉虛宮','玉虛宮位於昆侖山……',
                'template', 0.72, '{"strategy":"template"}'::jsonb)
        RETURNING proposal_id
        """,
        job_id,
        _PROJECT,
        _USER,
    )


async def _advance(conn, pid: uuid.UUID, status: str) -> None:
    await conn.execute(
        "UPDATE enrichment_proposal SET review_status=$2 WHERE proposal_id=$1",
        pid,
        status,
    )


async def test_full_promote_path_retains_origin(pool):
    async with pool.acquire() as conn:
        job_id = await _seed_job(conn)
        pid = await _seed_proposal(conn, job_id)

        row = await conn.fetchrow(
            "SELECT origin, review_status, confidence FROM enrichment_proposal "
            "WHERE proposal_id=$1",
            pid,
        )
        assert row["origin"] == "enrichment"          # never canon by default
        assert row["review_status"] == "proposed"
        assert row["confidence"] < 1.0                # H0: never canon

        # proposed → author_reviewing → approved
        await _advance(conn, pid, "author_reviewing")
        await _advance(conn, pid, "approved")

        # approved → promoted (must carry the promotion record).
        entity_id = uuid.uuid4()
        promoter = uuid.uuid4()
        await conn.execute(
            """
            UPDATE enrichment_proposal
               SET review_status='promoted',
                   promoted_entity_id=$2,
                   promoted_by=$3,
                   promoted_at=now()
             WHERE proposal_id=$1
            """,
            pid,
            entity_id,
            promoter,
        )

        promoted = await conn.fetchrow(
            "SELECT * FROM enrichment_proposal WHERE proposal_id=$1", pid
        )
        # Permanent origin markers retained / stamped at promote (H0 lock).
        assert promoted["origin"] == "enrichment", "origin must survive promotion"
        assert promoted["review_status"] == "promoted"
        assert promoted["promoted_entity_id"] == entity_id
        assert promoted["promoted_by"] == promoter
        assert promoted["promoted_at"] is not None
        assert promoted["promoted_from_proposal_id"] == pid
        assert promoted["original_technique"] == "template"
        assert promoted["confidence"] < 1.0, "promotion must NOT bump confidence to canon"


async def test_reject_terminal_branch(pool):
    async with pool.acquire() as conn:
        job_id = await _seed_job(conn)
        pid = await _seed_proposal(conn, job_id)
        await _advance(conn, pid, "author_reviewing")
        await conn.execute(
            "UPDATE enrichment_proposal SET review_status='rejected', "
            "rejected_reason='anachronism' WHERE proposal_id=$1",
            pid,
        )
        row = await conn.fetchrow(
            "SELECT review_status, promoted_entity_id, origin FROM enrichment_proposal "
            "WHERE proposal_id=$1",
            pid,
        )
        assert row["review_status"] == "rejected"
        assert row["promoted_entity_id"] is None
        assert row["origin"] == "enrichment"


async def test_illegal_jump_blocked(pool):
    async with pool.acquire() as conn:
        job_id = await _seed_job(conn)
        pid = await _seed_proposal(conn, job_id)
        # proposed → promoted is not a legal edge.
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(
                "UPDATE enrichment_proposal SET review_status='promoted', "
                "promoted_entity_id=$2, promoted_by=$3, promoted_at=now() "
                "WHERE proposal_id=$1",
                pid,
                uuid.uuid4(),
                uuid.uuid4(),
            )


async def test_promote_requires_full_record(pool):
    async with pool.acquire() as conn:
        job_id = await _seed_job(conn)
        pid = await _seed_proposal(conn, job_id)
        await _advance(conn, pid, "author_reviewing")
        await _advance(conn, pid, "approved")
        # promoted without the promotion record must be rejected by the trigger.
        with pytest.raises(asyncpg.PostgresError):
            await _advance(conn, pid, "promoted")


async def test_promoted_columns_forbidden_pre_promote(pool):
    async with pool.acquire() as conn:
        job_id = await _seed_job(conn)
        pid = await _seed_proposal(conn, job_id)
        # Setting promoted_* while still 'proposed' must fail (promote-only).
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(
                "UPDATE enrichment_proposal SET promoted_entity_id=$2 "
                "WHERE proposal_id=$1",
                pid,
                uuid.uuid4(),
            )


async def test_origin_immutable(pool):
    async with pool.acquire() as conn:
        job_id = await _seed_job(conn)
        pid = await _seed_proposal(conn, job_id)
        # Cannot strip origin to look like authored canon.
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(
                "UPDATE enrichment_proposal SET origin='glossary' WHERE proposal_id=$1",
                pid,
            )


async def test_confidence_cannot_reach_canon_on_update(pool):
    async with pool.acquire() as conn:
        job_id = await _seed_job(conn)
        pid = await _seed_proposal(conn, job_id)
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(
                "UPDATE enrichment_proposal SET confidence=1.0 WHERE proposal_id=$1",
                pid,
            )
