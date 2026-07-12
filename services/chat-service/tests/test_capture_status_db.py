"""WS-1.6 (spec 05 §Q7) — the capture-decision data path, against REAL Postgres.

The point: the per-turn capture decision must be PERSISTED and READABLE via the session read
path, so the assistant home strip can show capture visibly ON/OFF *with a reason*. A status
that is computed-but-not-surfaced is the silent-no-op "collecting" chip this repo shipped
twice — so this is a consumed-by-EFFECT test (persist → read back through _row_to_session),
not an assertion that persist_capture_status was merely called.

Marked xdist_group("pg") (CLAUDE.md — shared dev DB, serialized). Skips cleanly when the dev
DB is unreachable. The fixture adds the column idempotently so the test genuinely runs even if
chat-service hasn't re-migrated yet (never a silent skip that lets the green suite lie).
"""
import os
import uuid

import asyncpg
import pytest

from app.routers.sessions import _row_to_session
from app.services.canon_capture import CaptureDecision, persist_capture_status

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool_and_session():
    try:
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    uid = uuid.uuid4()
    async with pool.acquire() as c:
        # Ensure the WS-1.6 column exists (idempotent — matches the migration) so this test
        # exercises the real behavior regardless of whether the service has re-migrated.
        await c.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS capture_status JSONB")
        sid = await c.fetchval(
            "INSERT INTO chat_sessions (owner_user_id, model_source, model_ref) "
            "VALUES ($1, 'user_model', $2) RETURNING session_id",
            uid, uuid.uuid4(),
        )
    try:
        yield pool, sid
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM chat_sessions WHERE session_id = $1", sid)
        await pool.close()


async def _read_capture_status(pool, sid):
    async with pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM chat_sessions WHERE session_id = $1", sid)
    return _row_to_session(row).capture_status


async def test_a_gated_turn_persists_fire_false_with_its_reason(pool_and_session):
    pool, sid = pool_and_session
    # A gated turn: capture did NOT fire, and the reason names exactly what a user would change.
    await persist_capture_status(pool, sid, CaptureDecision(False, "off_cadence"))
    got = await _read_capture_status(pool, sid)
    assert got == {"fire": False, "reason": "off_cadence"}, (
        "the home strip must be able to READ that capture is OFF this turn AND why — a "
        "decision computed but not surfaced is the silent 'collecting' chip bug"
    )


async def test_a_firing_turn_persists_fire_true(pool_and_session):
    pool, sid = pool_and_session
    await persist_capture_status(pool, sid, CaptureDecision(True, "fire"))
    assert await _read_capture_status(pool, sid) == {"fire": True, "reason": "fire"}


async def test_the_latest_decision_overwrites_the_previous(pool_and_session):
    # The status reflects the LAST turn (the home strip shows the current state, not a history).
    pool, sid = pool_and_session
    await persist_capture_status(pool, sid, CaptureDecision(True, "fire"))
    await persist_capture_status(pool, sid, CaptureDecision(False, "exchange_too_short"))
    assert await _read_capture_status(pool, sid) == {"fire": False, "reason": "exchange_too_short"}


async def test_unset_capture_status_reads_as_none(pool_and_session):
    # A brand-new session has never captured; the home strip shows a neutral state, not a crash.
    pool, sid = pool_and_session
    assert await _read_capture_status(pool, sid) is None
