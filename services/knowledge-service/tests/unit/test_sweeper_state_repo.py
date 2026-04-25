"""C14b — unit tests for SweeperStateRepo.

Covers the repo contract matrix:
  - read_cursor returns None when no row
  - upsert + read round-trips last_user_id
  - clear deletes the row (subsequent read → None)
  - upsert same sweeper_name updates atomically (ON CONFLICT)
  - multiple sweeper_name values are isolated
  - read_cursor_full returns (uuid, scope) tuple + handles JSON parse
  - upsert with last_scope writes the JSON body
  - upsert without last_scope preserves existing scope on UPDATE path
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.db.repositories.sweeper_state import SweeperStateRepo


class FakeConn:
    """Minimal asyncpg connection stub: tracks executed SQL + canned
    fetchrow results keyed by the query's sweeper_name arg."""

    def __init__(self, store: dict[str, dict] | None = None):
        self.store = store if store is not None else {}
        self.executed: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql: str, *args):
        self.executed.append((sql.strip()[:40], args))
        sweeper_name = args[0]
        row = self.store.get(sweeper_name)
        if row is None:
            return None
        # Return only the columns the SQL requested.
        if "last_user_id, last_scope" in sql:
            return {
                "last_user_id": row["last_user_id"],
                "last_scope": row["last_scope"],
            }
        return {"last_user_id": row["last_user_id"]}

    async def execute(self, sql: str, *args) -> str:
        self.executed.append((sql.strip()[:40], args))
        if "INSERT INTO sweeper_state" in sql:
            # 3 args = no scope; 4 args = with scope.
            sweeper_name = args[0]
            last_user_id = args[1]
            if len(args) >= 3:
                last_scope_raw = args[2] if "last_scope" in sql else None
            else:
                last_scope_raw = None
            existing = self.store.get(sweeper_name, {})
            self.store[sweeper_name] = {
                "last_user_id": last_user_id,
                # Preserve existing scope when caller didn't pass one.
                "last_scope": (
                    last_scope_raw if last_scope_raw is not None
                    else existing.get("last_scope", "{}")
                ),
            }
            return "INSERT 0 1"
        if "DELETE FROM sweeper_state" in sql:
            self.store.pop(args[0], None)
            return "DELETE 1"
        raise AssertionError(f"unexpected execute: {sql}")


class FakePool:
    def __init__(self, conn: FakeConn):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


@pytest.fixture
def repo_and_conn():
    conn = FakeConn()
    pool = FakePool(conn)
    return SweeperStateRepo(pool), conn  # type: ignore[arg-type]


# ── read_cursor ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_cursor_returns_none_when_no_row(repo_and_conn):
    repo, _ = repo_and_conn
    assert await repo.read_cursor("reconcile_evidence_count") is None


@pytest.mark.asyncio
async def test_upsert_then_read_roundtrips(repo_and_conn):
    repo, _ = repo_and_conn
    uid = uuid4()
    await repo.upsert_cursor("reconcile_evidence_count", uid)
    read_back = await repo.read_cursor("reconcile_evidence_count")
    assert read_back == uid


@pytest.mark.asyncio
async def test_clear_deletes_row(repo_and_conn):
    repo, _ = repo_and_conn
    uid = uuid4()
    await repo.upsert_cursor("reconcile_evidence_count", uid)
    await repo.clear_cursor("reconcile_evidence_count")
    assert await repo.read_cursor("reconcile_evidence_count") is None


@pytest.mark.asyncio
async def test_upsert_same_sweeper_name_updates(repo_and_conn):
    repo, _ = repo_and_conn
    uid1 = uuid4()
    uid2 = uuid4()
    await repo.upsert_cursor("reconcile_evidence_count", uid1)
    await repo.upsert_cursor("reconcile_evidence_count", uid2)
    assert await repo.read_cursor("reconcile_evidence_count") == uid2


@pytest.mark.asyncio
async def test_multiple_sweeper_names_isolated(repo_and_conn):
    """Two sweepers write under their own PK — no cross-contamination."""
    repo, _ = repo_and_conn
    uid_a = uuid4()
    uid_b = uuid4()
    await repo.upsert_cursor("sweeper_a", uid_a)
    await repo.upsert_cursor("sweeper_b", uid_b)

    assert await repo.read_cursor("sweeper_a") == uid_a
    assert await repo.read_cursor("sweeper_b") == uid_b

    await repo.clear_cursor("sweeper_a")
    assert await repo.read_cursor("sweeper_a") is None
    assert await repo.read_cursor("sweeper_b") == uid_b


# ── read_cursor_full ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_cursor_full_returns_tuple(repo_and_conn):
    repo, _ = repo_and_conn
    uid = uuid4()
    scope = {"stage": "phase_1", "processed": 42}
    await repo.upsert_cursor("reconcile_evidence_count", uid, scope)

    got = await repo.read_cursor_full("reconcile_evidence_count")
    assert got is not None
    got_uid, got_scope = got
    assert got_uid == uid
    assert got_scope == scope


@pytest.mark.asyncio
async def test_read_cursor_full_returns_none_when_no_row(repo_and_conn):
    repo, _ = repo_and_conn
    assert await repo.read_cursor_full("nonexistent") is None


@pytest.mark.asyncio
async def test_read_cursor_full_handles_string_jsonb(repo_and_conn):
    """asyncpg may deliver JSONB as str (driver version dependent).
    Repo must json.loads it into a dict."""
    repo, conn = repo_and_conn
    uid = uuid4()
    # Seed the store with a string-encoded JSON body (simulates the
    # asyncpg-returns-str path).
    conn.store["reconcile_evidence_count"] = {
        "last_user_id": uid,
        "last_scope": json.dumps({"stage": "str_encoded"}),
    }

    got = await repo.read_cursor_full("reconcile_evidence_count")
    assert got is not None
    _, scope = got
    assert scope == {"stage": "str_encoded"}


# ── upsert variants ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_without_scope_does_not_overwrite_existing_scope(repo_and_conn):
    """C14b — when caller passes last_scope=None on update, the
    UPDATE SET clause should NOT touch last_scope. The SQL branch
    omits it (see SweeperStateRepo.upsert_cursor). Regression lock."""
    repo, _ = repo_and_conn
    uid1 = uuid4()
    uid2 = uuid4()

    # Initial insert with scope.
    await repo.upsert_cursor(
        "reconcile_evidence_count", uid1, {"stage": "initial"},
    )
    # Update user_id without passing scope.
    await repo.upsert_cursor("reconcile_evidence_count", uid2)

    got = await repo.read_cursor_full("reconcile_evidence_count")
    assert got is not None
    got_uid, got_scope = got
    assert got_uid == uid2
    # Scope preserved — NOT overwritten to empty dict.
    assert got_scope == {"stage": "initial"}


@pytest.mark.asyncio
async def test_upsert_with_scope_overwrites_existing(repo_and_conn):
    repo, _ = repo_and_conn
    uid = uuid4()
    await repo.upsert_cursor(
        "reconcile_evidence_count", uid, {"stage": "initial"},
    )
    await repo.upsert_cursor(
        "reconcile_evidence_count", uid, {"stage": "updated"},
    )
    got = await repo.read_cursor_full("reconcile_evidence_count")
    assert got is not None
    _, scope = got
    assert scope == {"stage": "updated"}
