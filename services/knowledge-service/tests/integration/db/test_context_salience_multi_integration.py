"""D-MULTI-SALIENCE-WRITEBACK — LIVE Postgres proof.

The unit wiring test asserts the router CALLS record_accesses per project; this
drives the REAL /internal/context/build handler with a REAL EntityAccessRepo over
live Postgres and asserts the fire-and-forget task actually writes salience rows to
`entity_access_log` attributed to EACH source project (the bug: multi mode recorded
nothing because the write-back keyed on req.project_id, which is None in multi).

Skipped when no real KNOWLEDGE_DB_URL is set. Self-cleaning (unique user_id).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.context.modes.no_project import BuiltContext
from app.db.repositories.entity_access import EntityAccessRepo
from app.routers.context import ContextBuildRequest, build

pytestmark = pytest.mark.asyncio


async def test_multi_mode_writes_salience_per_source_project_live_db(pool):
    user_id, pa, pb = uuid4(), uuid4(), uuid4()
    repo = EntityAccessRepo(pool)
    built = BuiltContext(
        mode="multi", context="<memory/>", recent_message_count=20, token_count=1,
        surfaced_by_project={str(pa): ["ent-a1", "ent-a2"], str(pb): ["ent-b1"]},
    )
    req = ContextBuildRequest(
        user_id=user_id, project_id=None, project_ids=[pa, pb], message="hi",
    )
    try:
        with patch("app.routers.context.build_context", AsyncMock(return_value=built)):
            await build(
                req, summaries_repo=AsyncMock(), projects_repo=AsyncMock(),
                glossary_client=AsyncMock(), embedding_client=AsyncMock(),
                llm_client=AsyncMock(), working_memory_repo=AsyncMock(),
                entity_access_repo=repo,
            )
        # fire-and-forget → poll the real table until both projects' rows land
        rows = []
        for _ in range(100):
            await asyncio.sleep(0.02)
            rows = await pool.fetch(
                "SELECT project_id, entity_id, retrieval_count "
                "FROM entity_access_log WHERE user_id=$1",
                user_id,
            )
            if len(rows) >= 3:
                break
        got = {(str(r["project_id"]), r["entity_id"]) for r in rows}
        assert got == {
            (str(pa), "ent-a1"), (str(pa), "ent-a2"), (str(pb), "ent-b1"),
        }, f"expected per-project salience rows, got {got}"
        assert all(r["retrieval_count"] == 1 for r in rows)
    finally:
        await pool.execute("DELETE FROM entity_access_log WHERE user_id=$1", user_id)
