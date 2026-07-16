"""ACP A1 / RV-H4 — the checkpoint (working_memory) repo is OWNER-SCOPED.

The tenancy fix: `session_working_memory` has `UNIQUE(session_id)` with `user_id` a
non-key column (the 'unique-without-a-scope-key' smell). A read/write scoped by
`session_id` alone was a cross-tenant footgun. This proves, against a real DB, that
both `get` and `update_state` filter by the owner — a cross-owner attempt sees NOTHING
and writes NOTHING.

Real-SQL: uses the `pool` fixture (skips if no KNOWLEDGE_DB_URL). Marked xdist_group('pg')
so it serializes onto one worker on the shared dev DB (CLAUDE.md test-parallelization rule).
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.working_memory import WorkingMemoryRepo

pytestmark = pytest.mark.xdist_group("pg")

_CHARTER = {"goal": "g", "phases": ["warmup"], "checklist": [], "language": "en"}


@pytest.mark.asyncio
async def test_get_and_update_state_are_owner_scoped(pool):
    repo = WorkingMemoryRepo(pool)
    session_id = uuid4()
    owner = uuid4()
    intruder = uuid4()

    await repo.init_charter(session_id, owner, _CHARTER)

    # READ is owner-scoped: the owner sees the block; an intruder sees None.
    assert await repo.get(session_id, owner) is not None
    assert await repo.get(session_id, intruder) is None

    # WRITE is owner-scoped: an intruder's update affects 0 rows (returns False)
    # and does NOT change the owner's state.
    assert await repo.update_state(session_id, intruder, {"phase": "HACKED", "covered": ["x"]}) is False
    owner_block = await repo.get(session_id, owner)
    assert owner_block["state"].get("phase") != "HACKED", "intruder must not mutate the owner's state"

    # The real owner CAN write.
    assert await repo.update_state(session_id, owner, {"phase": "warmup", "covered": ["a"]}) is True
    assert (await repo.get(session_id, owner))["state"]["covered"] == ["a"]

    # cleanup (conftest does not truncate session_working_memory)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM session_working_memory WHERE session_id = $1", session_id)
