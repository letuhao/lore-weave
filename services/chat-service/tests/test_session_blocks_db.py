"""T4 — chat_session_blocks persistence against REAL Postgres (the CASE-based
no-op-refresh + OCC compare-and-set SQL a mock can't validate).

Marked xdist_group("pg") (CLAUDE.md — a test touching the shared dev DB is
serialized onto one worker). Skips cleanly when the dev DB is unreachable.
"""

import os
import uuid

import asyncpg
import pytest

from app.db.session_blocks import (
    cas_update_block,
    get_block,
    project_story_state,
    refresh_block,
)
from app.services.story_state import distill_story_state, render_story_state_block

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")
OWNER = uuid.UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")  # claude-test


@pytest.fixture
async def pool_and_session():
    try:
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    # a throwaway session owned by the test user
    sid = uuid.uuid4()
    async with pool.acquire() as c:
        has_table = await c.fetchval(
            "SELECT to_regclass('public.chat_session_blocks') IS NOT NULL")
        if not has_table:
            await pool.close()
            pytest.skip("chat_session_blocks not migrated on dev DB")
        await c.execute(
            "INSERT INTO chat_sessions (session_id, owner_user_id, model_source, model_ref) "
            "VALUES ($1, $2, 'user_model', $3)",
            sid, OWNER, uuid.uuid4(),
        )
    try:
        yield pool, sid
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM chat_sessions WHERE session_id = $1", sid)  # cascades blocks
        await pool.close()


async def test_refresh_insert_then_get(pool_and_session):
    pool, sid = pool_and_session
    v = await refresh_block(
        pool, session_id=sid, owner_user_id=OWNER, label="story_state",
        value="entities: Lâm Uyển", token_estimate=7, refreshed_turn=1, source_hash="h1")
    assert v == 1
    block = await get_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state")
    assert block is not None
    assert block.value == "entities: Lâm Uyển"
    assert block.token_estimate == 7
    assert block.version == 1


async def test_refresh_same_hash_is_noop_no_version_bump(pool_and_session):
    pool, sid = pool_and_session
    await refresh_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state",
                        value="v1", token_estimate=1, refreshed_turn=1, source_hash="h1")
    # same hash, later turn → value/version unchanged, only refreshed_turn advances
    v = await refresh_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state",
                            value="v1-changed-but-same-hash", token_estimate=9,
                            refreshed_turn=6, source_hash="h1")
    assert v == 1  # no bump
    block = await get_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state")
    assert block.value == "v1"            # NOT overwritten (hash unchanged)
    assert block.refreshed_turn == 6      # cadence marker still advanced
    assert block.version == 1


async def test_refresh_changed_hash_bumps_version_and_value(pool_and_session):
    pool, sid = pool_and_session
    await refresh_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state",
                        value="v1", token_estimate=1, refreshed_turn=1, source_hash="h1")
    v = await refresh_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state",
                            value="v2", token_estimate=2, refreshed_turn=2, source_hash="h2")
    assert v == 2
    block = await get_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state")
    assert block.value == "v2"
    assert block.version == 2


async def test_cas_stale_version_rejected(pool_and_session):
    pool, sid = pool_and_session
    # seed a CAS-managed (agent-writable) 'focus' row directly — refresh_block is
    # guarded to the story_state label only (LOW-2), so it can't seed 'focus'.
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO chat_session_blocks (session_id, owner_user_id, label, value, "
            "token_estimate, refreshed_turn, source_hash) VALUES ($1,$2,'focus','f1',1,1,'h1')",
            sid, OWNER,
        )
    # correct version → applies
    v = await cas_update_block(pool, session_id=sid, owner_user_id=OWNER, label="focus",
                               value="f2", token_estimate=2, refreshed_turn=2,
                               source_hash="h2", expected_version=1)
    assert v == 2
    # stale version → rejected (self-correcting, not a silent clobber)
    v2 = await cas_update_block(pool, session_id=sid, owner_user_id=OWNER, label="focus",
                                value="f3", token_estimate=3, refreshed_turn=3,
                                source_hash="h3", expected_version=1)
    assert v2 is None
    block = await get_block(pool, session_id=sid, owner_user_id=OWNER, label="focus")
    assert block.value == "f2"  # unchanged by the rejected write


async def test_refresh_block_rejects_non_story_state_label(pool_and_session):
    """LOW-2 (T4 review): refresh_block is the story_state cache path only — using it
    on a CAS-managed (agent-writable) label would clobber the OCC token silently."""
    pool, sid = pool_and_session
    with pytest.raises(ValueError, match="cas_update_block"):
        await refresh_block(pool, session_id=sid, owner_user_id=OWNER, label="focus",
                            value="x", token_estimate=1, refreshed_turn=1, source_hash="h")


async def test_tenancy_other_owner_cannot_read(pool_and_session):
    pool, sid = pool_and_session
    await refresh_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state",
                        value="secret", token_estimate=1, refreshed_turn=1, source_hash="h1")
    other = uuid.uuid4()
    assert await get_block(pool, session_id=sid, owner_user_id=other, label="story_state") is None


async def test_project_story_state_maintain_then_degraded_projects(pool_and_session):
    """End-to-end against real SQL (the orchestrator over real get/refresh): a materialized
    turn seeds the cache and projects nothing (live prefix present); a later degraded turn
    (no live grounding) projects the cached bible — the D4 safety net."""
    pool, sid = pool_and_session
    bible = "Lâm Uyển — the betrayed heiress.\nĐại Việt is the setting."
    # turn 1 — grounding materialized: refresh the cache, project nothing (live is in-prompt)
    out1 = await project_story_state(
        pool, session_id=sid, owner_user_id=OWNER,
        stable_context=bible, full_context=bible, current_turn=1)
    assert out1 == ""
    block = await get_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state")
    assert block is not None and block.value == distill_story_state(bible)[0]
    assert block.refreshed_turn == 1 and block.version == 1
    # turn 2 — degraded (no live grounding): project the cached bible, no version churn
    out2 = await project_story_state(
        pool, session_id=sid, owner_user_id=OWNER,
        stable_context="", full_context="", current_turn=2)
    assert out2 == render_story_state_block(distill_story_state(bible)[0])
    block2 = await get_block(pool, session_id=sid, owner_user_id=OWNER, label="story_state")
    assert block2.version == 1  # projection alone never writes
