"""K21-C (design D5) — unit tests for PendingFactsRepo.

The pending-facts queue round-trip: queue (insert), list_for_user
(all + per-session), get, delete — all user-scoped. The FakeConn /
FakePool stubs emulate asyncpg's pool-connection surface in memory,
mirroring `test_summary_spending_repo.py`. The live-DB contract
(CHECK constraints, uuidv7 PK) is exercised by the integration suite.

SECURITY: every query filters on user_id — the fake store keys on
(user_id, pending_fact_id) so cross-user isolation is enforced by
construction, the same way `test_public_projects.py`'s FakeProjectsRepo
does.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.db.models import PendingFact
from app.db.repositories.pending_facts import PendingFactsRepo


class FakeConn:
    """Minimal pool-connection stub emulating the four SQL statements
    PendingFactsRepo issues: INSERT … RETURNING, the SELECT list (with
    an optional session_id predicate), the single-row SELECT, and
    DELETE. Keyed by pending_fact_id; user_id is matched in every
    query so a cross-user call sees nothing."""

    def __init__(self) -> None:
        # pending_fact_id → row dict
        self.store: dict[UUID, dict] = {}
        self._clock = datetime(2026, 5, 17, tzinfo=timezone.utc)

    def _next_created_at(self) -> datetime:
        # Strictly increasing so ORDER BY created_at is deterministic.
        self._clock += timedelta(seconds=1)
        return self._clock

    async def fetchrow(self, sql: str, *args):
        s = sql.strip()
        if s.startswith("INSERT INTO knowledge_pending_facts"):
            user_id, project_id, session_id, fact_type, fact_text = args
            pfid = uuid4()
            row = {
                "pending_fact_id": pfid,
                "user_id": user_id,
                "project_id": project_id,
                "session_id": session_id,
                "fact_type": fact_type,
                "fact_text": fact_text,
                "created_at": self._next_created_at(),
            }
            self.store[pfid] = row
            return dict(row)
        if s.startswith("SELECT") and "WHERE user_id = $1 AND pending_fact_id" in s:
            user_id, pfid = args
            row = self.store.get(pfid)
            if row is None or row["user_id"] != user_id:
                return None
            return dict(row)
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetch(self, sql: str, *args):
        s = sql.strip()
        if s.startswith("SELECT") and "FROM knowledge_pending_facts" in s:
            user_id = args[0]
            session_id = args[1] if len(args) > 1 else None
            # WS-2.5 — the diary_only path emits an "AND session_id IS NULL" predicate with NO bind param;
            # detect it from the SQL so this fake reflects the real filter (else the mock hides it).
            diary_only = "session_id IS NULL" in s
            rows = [
                r for r in self.store.values()
                if r["user_id"] == user_id
                and (session_id is None or r["session_id"] == session_id)
                and (not diary_only or r["session_id"] is None)
            ]
            rows.sort(key=lambda r: (r["created_at"], r["pending_fact_id"]))
            return [dict(r) for r in rows]
        raise AssertionError(f"unexpected fetch: {sql}")

    async def execute(self, sql: str, *args) -> str:
        s = sql.strip()
        if s.startswith("DELETE FROM knowledge_pending_facts"):
            user_id, pfid = args
            row = self.store.get(pfid)
            if row is not None and row["user_id"] == user_id:
                del self.store[pfid]
                return "DELETE 1"
            return "DELETE 0"
        raise AssertionError(f"unexpected execute: {sql}")


class FakePool:
    """Stub mimicking asyncpg.Pool's `acquire()` context manager —
    PendingFactsRepo always goes through `async with pool.acquire()`."""

    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


@pytest.fixture
def repo_and_conn():
    conn = FakeConn()
    pool = FakePool(conn)
    return PendingFactsRepo(pool), conn  # type: ignore[arg-type]


# ── queue ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_queue_inserts_and_returns_pending_fact(repo_and_conn):
    repo, conn = repo_and_conn
    user_id = uuid4()
    project_id = uuid4()
    pf = await repo.queue(
        user_id,
        project_id=project_id,
        session_id="sess-1",
        fact_type="preference",
        fact_text="Kai prefers fire magic",
    )
    assert isinstance(pf, PendingFact)
    assert pf.user_id == user_id
    assert pf.project_id == project_id
    assert pf.fact_type == "preference"
    assert pf.fact_text == "Kai prefers fire magic"
    # Persisted.
    assert pf.pending_fact_id in conn.store


@pytest.mark.asyncio
async def test_queue_accepts_null_project_id(repo_and_conn):
    """A no-project chat can still queue a fact — project_id nullable."""
    repo, _ = repo_and_conn
    pf = await repo.queue(
        uuid4(),
        project_id=None,
        session_id="sess-1",
        fact_type="decision",
        fact_text="a global fact",
    )
    assert pf.project_id is None


# ── list_for_user ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_for_user_returns_only_callers_rows(repo_and_conn):
    """Cross-user isolation — user B never sees user A's pending facts."""
    repo, _ = repo_and_conn
    user_a = uuid4()
    user_b = uuid4()
    await repo.queue(user_a, project_id=None, session_id="s",
                     fact_type="decision", fact_text="A's fact")
    await repo.queue(user_b, project_id=None, session_id="s",
                     fact_type="decision", fact_text="B's fact")

    a_rows = await repo.list_for_user(user_a)
    assert len(a_rows) == 1
    assert a_rows[0].fact_text == "A's fact"

    b_rows = await repo.list_for_user(user_b)
    assert len(b_rows) == 1
    assert b_rows[0].fact_text == "B's fact"


@pytest.mark.asyncio
async def test_list_for_user_filters_by_session_id(repo_and_conn):
    """The optional session_id narrows the list to one chat session."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.queue(user_id, project_id=None, session_id="sess-1",
                     fact_type="decision", fact_text="in session 1")
    await repo.queue(user_id, project_id=None, session_id="sess-2",
                     fact_type="decision", fact_text="in session 2")

    # No filter → both.
    assert len(await repo.list_for_user(user_id)) == 2
    # Filtered → just the one.
    one = await repo.list_for_user(user_id, session_id="sess-1")
    assert len(one) == 1
    assert one[0].fact_text == "in session 1"


@pytest.mark.asyncio
async def test_list_for_user_diary_only_returns_session_less_facts(repo_and_conn):
    """WS-2.5 (audit MED): diary_only=True narrows to the SESSION-LESS diary facts, so chat-memory
    facts (which carry a session_id) don't leak into the diary fact inbox."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.queue(user_id, project_id=None, session_id="chat-sess",
                     fact_type="decision", fact_text="a chat-memory fact")
    await repo.queue(user_id, project_id=None, session_id=None,
                     fact_type="statement", fact_text="a diary fact")

    # No filter → BOTH (the old, over-listing behavior).
    assert len(await repo.list_for_user(user_id)) == 2
    # diary_only → ONLY the session-less diary fact.
    diary = await repo.list_for_user(user_id, diary_only=True)
    assert len(diary) == 1
    assert diary[0].fact_text == "a diary fact"
    assert diary[0].session_id is None


@pytest.mark.asyncio
async def test_list_for_user_oldest_first(repo_and_conn):
    """Rows come back created_at ASC so the FE renders them in order."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.queue(user_id, project_id=None, session_id="s",
                     fact_type="decision", fact_text="first")
    await repo.queue(user_id, project_id=None, session_id="s",
                     fact_type="decision", fact_text="second")
    rows = await repo.list_for_user(user_id)
    assert [r.fact_text for r in rows] == ["first", "second"]


@pytest.mark.asyncio
async def test_list_for_user_empty_when_none(repo_and_conn):
    repo, _ = repo_and_conn
    assert await repo.list_for_user(uuid4()) == []


# ── get ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_the_row(repo_and_conn):
    repo, _ = repo_and_conn
    user_id = uuid4()
    pf = await repo.queue(user_id, project_id=None, session_id="s",
                          fact_type="milestone", fact_text="a milestone")
    got = await repo.get(user_id, pf.pending_fact_id)
    assert got is not None
    assert got.pending_fact_id == pf.pending_fact_id
    assert got.fact_text == "a milestone"


@pytest.mark.asyncio
async def test_get_cross_user_returns_none(repo_and_conn):
    """A different user's id must not resolve someone else's row."""
    repo, _ = repo_and_conn
    owner = uuid4()
    pf = await repo.queue(owner, project_id=None, session_id="s",
                          fact_type="decision", fact_text="owner's fact")
    assert await repo.get(uuid4(), pf.pending_fact_id) is None


@pytest.mark.asyncio
async def test_get_missing_returns_none(repo_and_conn):
    repo, _ = repo_and_conn
    assert await repo.get(uuid4(), uuid4()) is None


# ── delete ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_removes_the_row(repo_and_conn):
    repo, conn = repo_and_conn
    user_id = uuid4()
    pf = await repo.queue(user_id, project_id=None, session_id="s",
                          fact_type="decision", fact_text="to delete")
    assert await repo.delete(user_id, pf.pending_fact_id) is True
    assert pf.pending_fact_id not in conn.store
    # Now gone.
    assert await repo.get(user_id, pf.pending_fact_id) is None


@pytest.mark.asyncio
async def test_delete_cross_user_is_noop(repo_and_conn):
    """A cross-user delete returns False and leaves the row intact."""
    repo, conn = repo_and_conn
    owner = uuid4()
    pf = await repo.queue(owner, project_id=None, session_id="s",
                          fact_type="decision", fact_text="owner's fact")
    assert await repo.delete(uuid4(), pf.pending_fact_id) is False
    # Still there for the real owner.
    assert pf.pending_fact_id in conn.store


@pytest.mark.asyncio
async def test_delete_missing_returns_false(repo_and_conn):
    repo, _ = repo_and_conn
    assert await repo.delete(uuid4(), uuid4()) is False
