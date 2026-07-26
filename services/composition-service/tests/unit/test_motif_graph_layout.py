"""Wave-4 (D-MOTIF-GRAPH-CANVAS) — MotifGraphLayoutRepo unit tests (no DB, no network).

Proves the SQL SHAPE + tenancy scope + OCC-None handling with a fake pool that records the
statement + args. The real merge/OCC BEHAVIOUR (positions || moves keeps both nodes; a version
mismatch 412s) is proven live against the dev DB in the B7 cross-service smoke.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.repositories.motif_graph_layout import MotifGraphLayoutRepo

pytestmark = pytest.mark.asyncio


class _FakeConn:
    def __init__(self, row):
        self._row = row
        self.calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return self._row

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return []

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return 1


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, row):
        self.conn = _FakeConn(row)

    def acquire(self):
        return _FakeAcquire(self.conn)


async def test_get_returns_empty_version_zero_when_no_row():
    repo = MotifGraphLayoutRepo(_FakePool(None))
    positions, version = await repo.get(uuid.uuid4(), uuid.uuid4())
    assert positions == {} and version == 0


async def test_get_parses_a_json_string_positions():
    repo = MotifGraphLayoutRepo(_FakePool({"positions": '{"m1": {"x": 1, "y": 2}}', "version": 5}))
    positions, version = await repo.get(uuid.uuid4(), uuid.uuid4())
    assert positions == {"m1": {"x": 1, "y": 2}} and version == 5


async def test_merge_issues_owner_scoped_occ_upsert_with_json_moves():
    owner, book = uuid.uuid4(), uuid.uuid4()
    repo = MotifGraphLayoutRepo(_FakePool({"positions": {"m1": {"x": 3, "y": 4}}, "version": 2}))
    moves = {"m1": {"x": 3, "y": 4}}
    out = await repo.merge(owner, book, moves, if_version=1)
    assert out == ({"m1": {"x": 3, "y": 4}}, 2)
    sql, args = repo._pool.conn.calls[0]
    # server-side MERGE (not overwrite), version bump, and the OCC guard on the stored version
    assert "positions  = motif_graph_layout.positions || EXCLUDED.positions" in sql
    assert "version    = motif_graph_layout.version + 1" in sql
    assert "WHERE motif_graph_layout.version = $4" in sql
    # tenancy: owner_user_id is $1 (a caller can only write their OWN row) + the moves are JSON
    assert args[0] == owner and args[1] == book and args[3] == 1
    assert json.loads(args[2]) == moves


async def test_merge_returns_none_on_occ_conflict():
    """An existing row whose version != if_version → the upsert updates nothing → 0 rows → None
    (the route maps None → 412 + a reseed). None is NOT ({}, 0) — a conflict is distinct."""
    repo = MotifGraphLayoutRepo(_FakePool(None))
    out = await repo.merge(uuid.uuid4(), uuid.uuid4(), {"m1": {"x": 1, "y": 1}}, if_version=9)
    assert out is None


async def test_merge_with_no_moves_is_a_read():
    repo = MotifGraphLayoutRepo(_FakePool(None))
    out = await repo.merge(uuid.uuid4(), uuid.uuid4(), {}, if_version=3)
    assert out == ({}, 0)  # empty moves → get() → ({},0), never a wasted write


async def test_nodes_and_visibility_share_the_bound_in_book_predicate():
    """D-MOTIF-GRAPH-BOOK-SCOPING (Option B): both the node list and the position-write check
    gate on a motif_application binding (bound-in-book), via the SAME shared fragment — so a
    shown node is always position-able and a non-node is always rejected."""
    repo = MotifGraphLayoutRepo(_FakePool(None))
    await repo.nodes_for_book(uuid.uuid4(), uuid.uuid4(), 10)
    await repo.motif_visible_in_book(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    nodes_sql, vis_sql = repo._pool.conn.calls[0][0], repo._pool.conn.calls[1][0]
    for sql in (nodes_sql, vis_sql):
        assert "motif_application ma" in sql          # the bound-in-book join
        assert "ma.book_id = $2 AND ma.motif_id = motif.id" in sql
        assert "book_shared AND book_id = $2" in sql   # the shared tier is shown unconditionally
        assert "owner_user_id IS NULL" not in sql      # system stays excluded (islands)
