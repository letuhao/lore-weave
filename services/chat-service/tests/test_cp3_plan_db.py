"""CP-3.1 · the plan's STORAGE, against real Postgres. **Mocks cannot prove these three claims.**

`one live plan per session` is a partial unique index, `append-only` is a primary key, and `replay`
is a round-trip through jsonb. Each is a property of the DATABASE, and a mock would assert my model
of it — which is the mock-only-coverage failure this repository has recorded before.

Skipped when no Postgres is reachable, and the skip says so rather than passing quietly.
"""
from __future__ import annotations

import os
import uuid
from types import MappingProxyType as M

import asyncpg
import pytest

from app.agentruntime.plan import Binding, Event, Spec, State, Step, Termination, terminate
from app.db import plans as plan_db

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN",
                     "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")

UUID_VALUE = "019fafa2-7c3d-7a91-b0e2-4f1a2b3c4d5e"


def _spec(version: int = 1, gated: bool = True) -> Spec:
    return Spec(goal="list books and read the newest", version=version, steps=(
        Step(declaration="book_list", contract_version="1.0.0", emits=("book_id",)),
        Step(declaration="book_read", contract_version="1.0.0",
             accepts=M({"book_id": Binding(from_step=0, from_emit="book_id")}), gated=gated),
    ))


@pytest.fixture
async def conn():
    """One connection in a rolled-back transaction, so nothing survives the test."""
    try:
        c = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - no database is a SKIP, never a silent pass
        pytest.skip(f"no Postgres at {DSN}: {type(exc).__name__} — these three claims are "
                    f"properties of the database and cannot be checked without one")
    tx = c.transaction()
    await tx.start()
    try:
        yield c
    finally:
        await tx.rollback()
        await c.close()


async def _session(conn) -> str:
    sid = await conn.fetchval(
        "INSERT INTO chat_sessions (owner_user_id, model_source, model_ref) "
        "VALUES ($1, 'internal', $2) RETURNING session_id",
        uuid.uuid4(), uuid.uuid4())
    return sid


class TestOneLivePlanPerSession:
    async def test_A_SECOND_LIVE_PLAN_IS_UNREPRESENTABLE(self, conn):
        """🔴 The invariant is a partial unique INDEX, not application code.

        Two live plans in one session is the state where *"which plan does this message route
        into?"* has no answer, and enforcing it in Python would make it a race. This drives the
        constraint directly, bypassing `save_spec`, because what is being checked is the database.
        """
        sid = await _session(conn)
        await plan_db.save_spec(conn, sid, _spec())
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO chat_plans (session_id, version, spec_hash, gated_hash, spec, status) "
                "VALUES ($1, 99, 'h', 'g', '{}'::jsonb, 'live')", sid)

    async def test_A_REVISION_SUPERSEDES_RATHER_THAN_OVERWRITES(self, conn):
        """A revision is a new VERSION, so §0.8's approval-invalidation stays inspectable after the
        fact instead of being reconstructed from memory."""
        sid = await _session(conn)
        first = await plan_db.save_spec(conn, sid, _spec(version=1))
        second = await plan_db.save_spec(conn, sid, _spec(version=2))
        assert first != second
        rows = dict(await conn.fetch(
            "SELECT plan_id, status FROM chat_plans WHERE session_id = $1", sid))
        assert rows[uuid.UUID(first)] == "superseded"
        assert rows[uuid.UUID(second)] == "live"

    async def test_LIVE_PLAN_ID_ANSWERS_S3_M4(self, conn):
        """A second message during a live plan ROUTES INTO IT; a hard reject would be a ceiling."""
        sid = await _session(conn)
        assert await plan_db.live_plan_id(conn, sid) is None
        pid = await plan_db.save_spec(conn, sid, _spec())
        assert str(await plan_db.live_plan_id(conn, sid)) == pid


class TestStateIsAppendOnlyInTheDatabase:
    async def test_REWRITING_A_POSITION_IS_A_CONSTRAINT_VIOLATION(self, conn):
        """🔴 Append-only is the PRIMARY KEY. STATE is the record recovery replays, and a history
        that can be edited after the fact cannot be trusted to say what committed."""
        sid = await _session(conn)
        pid = await plan_db.save_spec(conn, sid, _spec())
        seq = await plan_db.append_event(
            conn, uuid.UUID(pid), Event(kind="step_started", step_index=0))
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO chat_plan_events (plan_id, seq, kind, step_index) "
                "VALUES ($1, $2, 'step_failed', 0)", uuid.UUID(pid), seq)

    async def test_A_DUCK_TYPED_EVENT_NEVER_REACHES_THE_TABLE(self, conn):
        sid = await _session(conn)
        pid = await plan_db.save_spec(conn, sid, _spec())
        with pytest.raises(TypeError, match="not an Event"):
            await plan_db.append_event(conn, uuid.UUID(pid),
                                       {"kind": "step_started", "step_index": 0})


class TestReplayReturnsTheIdentifierExactly:
    async def test_THE_UUID_SURVIVES_THE_ROUND_TRIP(self, conn):
        """The whole reason this table exists: the conversation evicts identifiers, and the plan
        must not. Byte-exact, through jsonb, after a reload."""
        sid = await _session(conn)
        pid = await plan_db.save_spec(conn, sid, _spec())
        await plan_db.append_event(conn, uuid.UUID(pid), Event(
            kind="step_emitted", step_index=0, values=M({"book_id": UUID_VALUE})))

        loaded = await plan_db.load_live(conn, sid)
        assert loaded is not None
        got_id, spec, state = loaded
        assert got_id == pid
        assert state.emitted() == {0: {"book_id": UUID_VALUE}}

        from app.agentruntime.plan import resolve_arguments
        assert resolve_arguments(spec, state, 1) == {"book_id": UUID_VALUE}

    async def test_THE_STORED_HASH_IS_USED_NOT_A_FRESH_ONE(self, conn):
        """🔴 An approval bound to the STORED hash. Recomputing on read would silently re-bind it to
        whatever the code says today — §0.8's laundering with an extra step."""
        sid = await _session(conn)
        pid = await plan_db.save_spec(conn, sid, _spec())
        await conn.execute("UPDATE chat_plans SET spec_hash = 'stamped-at-approval-time' "
                           "WHERE plan_id = $1", uuid.UUID(pid))
        _, _, state = await plan_db.load_live(conn, sid)
        assert state.spec_hash == "stamped-at-approval-time", (
            "load_live recomputed the hash instead of reading the stored one, so a plan whose hash "
            "has moved would silently present as still-approved"
        )

    async def test_A_SPEC_EDITED_IN_THE_DATABASE_IS_REFUSED_ON_THE_WAY_OUT(self, conn):
        """Rebuilding through the real constructors re-runs `check_bindings`, so a row edited in the
        database is refused exactly as a hand-typed manifest row is. Serialising the object graph
        would have skipped every clause."""
        from app.agentruntime.plan import BindingError

        sid = await _session(conn)
        pid = await plan_db.save_spec(conn, sid, _spec())
        await conn.execute(
            "UPDATE chat_plans SET spec = jsonb_set(spec, "
            "'{steps,1,accepts,book_id,from_emit}', '\"no_such_name\"') WHERE plan_id = $1",
            uuid.UUID(pid))
        with pytest.raises(BindingError, match="does not declare it"):
            await plan_db.load_live(conn, sid)

    async def test_NO_LIVE_PLAN_READS_AS_NONE_NOT_AS_AN_EMPTY_PLAN(self, conn):
        """A missing plan must mean *there is no plan*, never *here is an empty one* — the fail-open
        direction every previous 'invisibility' leaked through."""
        sid = await _session(conn)
        assert await plan_db.load_live(conn, sid) is None


class TestTerminationIsQueryable:
    async def test_THE_SCOPE_AND_THE_HANDOFF_ARE_COLUMNS(self, conn):
        """Exits #2 and #4 went silent by recording a status somewhere nobody looked."""
        sid = await _session(conn)
        pid = await plan_db.save_spec(conn, sid, _spec())
        st = State("h")
        st.append(Event(kind="effect_committed", step_index=1,
                        undo_hint=f"book_restore({UUID_VALUE})", committed=True))
        term = terminate(st, "escalate_to_human", 1,
                         hand_to_human="a write committed; confirm or undo before replanning")
        await plan_db.record_termination(conn, uuid.UUID(pid), term)

        row = await conn.fetchrow(
            "SELECT status, terminal_scope, hand_to_human FROM chat_plans WHERE plan_id = $1",
            uuid.UUID(pid))
        assert row["status"] == "terminated"
        assert row["terminal_scope"] == "escalate_to_human"
        assert "confirm or undo" in row["hand_to_human"]
        # ...and the session is free for a new plan, which is what makes the queue drain.
        assert await plan_db.live_plan_id(conn, sid) is None

    async def test_A_DUCK_TYPED_TERMINATION_IS_REFUSED(self, conn):
        sid = await _session(conn)
        pid = await plan_db.save_spec(conn, sid, _spec())
        with pytest.raises(TypeError, match="not a Termination"):
            await plan_db.record_termination(conn, uuid.UUID(pid), {"scope": "done_when"})
