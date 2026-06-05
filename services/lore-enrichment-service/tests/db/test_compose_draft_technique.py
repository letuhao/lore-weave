"""Compose slice 1 — the new ``compose_draft`` technique is persistable.

The runner persists ``technique=pipeline.technique_value()`` onto BOTH
``enrichment_job`` and ``enrichment_proposal``. Slice 1 adds a 5th technique
(``compose_draft``, tier P1) for mode-D draft expansion, so the schema-level
``technique`` CHECK on both tables MUST admit it — otherwise a compose_draft job
fails at create / persist. This pins the migration that widens both CHECKs
(the original 4-value vocabulary would reject the insert).

Skips when no real DB is reachable (verify supplies the compose Postgres).
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio

_PROJECT = uuid.uuid4()
_USER = uuid.uuid4()


async def test_compose_draft_job_and_proposal_insertable(pool):
    """A compose_draft job + proposal insert without violating the technique CHECK."""
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
               VALUES ($1,$2,'compose_draft','generic') RETURNING job_id""",
            _PROJECT, _USER,
        )
        assert job_id is not None

        pid = await conn.fetchval(
            """INSERT INTO enrichment_proposal
                 (job_id, project_id, user_id, entity_kind, canonical_name, content,
                  technique, confidence, provenance_json)
               VALUES ($1,$2,$3,'generic','新天地','概述：作者草稿扩写……',
                       'compose_draft', 0.30, '{"seed":"author_draft"}'::jsonb)
               RETURNING proposal_id""",
            job_id, _PROJECT, _USER,
        )
        row = await conn.fetchrow(
            "SELECT technique, origin, confidence FROM enrichment_proposal WHERE proposal_id=$1",
            pid,
        )
        assert row["technique"] == "compose_draft"
        assert row["origin"] == "enrichment"   # H0 unchanged — never canon
        assert row["confidence"] < 1.0


async def test_unknown_technique_still_rejected(pool):
    """The CHECK still bites a genuinely-unknown technique (it was widened, not dropped)."""
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(
                """INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
                   VALUES ($1,$2,'totally_made_up','generic')""",
                _PROJECT, _USER,
            )
