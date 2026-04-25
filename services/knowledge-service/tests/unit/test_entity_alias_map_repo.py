"""C17 — unit tests for EntityAliasMapRepo (D-K19d-γb-03 closer).

Mirrors the test shape of test_summary_spending_repo.py (FakeConn +
FakePool stubs that emulate ON CONFLICT semantics in Python so we
don't need a live Postgres). Constraint enforcement (PK uniqueness,
CHECK reason) is covered by integration tests gated on
TEST_DATABASE_URL — the FakeConn doesn't enforce constraints.

Contract matrix:
  - lookup() miss returns None
  - lookup() hit returns target_entity_id
  - lookup() empty alias defensive None
  - record_merge() inserts row
  - record_merge() ON CONFLICT DO NOTHING (no overwrite of existing target)
  - list_for_entity() reverse lookup ordered by created_at DESC
  - bulk_backfill() inserts new rows with reason='backfill', skips dups
  - scope isolation: same alias different project_scope = different rows
  - kind isolation: same alias different kind = different rows
  - repoint_target() chain re-point (REVIEW-DESIGN catch)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.db.repositories.entity_alias_map import EntityAliasMapRepo


class FakeConn:
    """Emulates entity_alias_map storage in a Python dict keyed on the
    composite PK. Records executed SQL prefixes for debug + records
    UPDATE rowcount as the asyncpg-style status string."""

    def __init__(
        self,
        store: dict[tuple, dict] | None = None,
    ):
        # Key: (user_id, project_scope, kind, canonical_alias) → row dict
        self.store = store if store is not None else {}
        self.executed: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql: str, *args):
        self.executed.append((sql.strip()[:40], args))
        if "FROM entity_alias_map" in sql and "WHERE user_id" in sql:
            user_id, project_scope, kind, canonical_alias = args
            row = self.store.get((user_id, project_scope, kind, canonical_alias))
            return {"target_entity_id": row["target_entity_id"]} if row else None
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetch(self, sql: str, *args):
        self.executed.append((sql.strip()[:40], args))
        if "WHERE target_entity_id" in sql:
            target_id = args[0]
            matches = [
                {**row, "user_id": key[0], "project_scope": key[1],
                 "kind": key[2], "canonical_alias": key[3]}
                for key, row in self.store.items()
                if row["target_entity_id"] == target_id
            ]
            # Sort by created_at DESC.
            matches.sort(key=lambda r: r["created_at"], reverse=True)
            return matches
        raise AssertionError(f"unexpected fetch: {sql}")

    async def execute(self, sql: str, *args) -> str:
        self.executed.append((sql.strip()[:40], args))
        if "INSERT INTO entity_alias_map" in sql:
            user_id, project_scope, kind, canonical_alias = args[:4]
            target_entity_id = args[4]
            source_entity_id = args[5]
            reason = args[6] if len(args) >= 7 else "merge"
            key = (user_id, project_scope, kind, canonical_alias)
            if key in self.store:
                # ON CONFLICT DO NOTHING — emulate by signalling 0 rows.
                return "INSERT 0 0"
            self.store[key] = {
                "target_entity_id": target_entity_id,
                "source_entity_id": source_entity_id,
                "reason": reason,
                "created_at": datetime.now(timezone.utc),
            }
            return "INSERT 0 1"
        if "UPDATE entity_alias_map" in sql:
            new_target, user_id, old_target = args
            count = 0
            for key, row in self.store.items():
                if key[0] == user_id and row["target_entity_id"] == old_target:
                    row["target_entity_id"] = new_target
                    count += 1
            return f"UPDATE {count}"
        raise AssertionError(f"unexpected execute: {sql}")


class FakePool:
    def __init__(self, conn: FakeConn):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn

    async def execute(self, sql: str, *args) -> str:
        return await self._conn.execute(sql, *args)

    async def fetchrow(self, sql: str, *args):
        return await self._conn.fetchrow(sql, *args)

    async def fetch(self, sql: str, *args):
        return await self._conn.fetch(sql, *args)


@pytest.fixture
def repo_and_conn():
    conn = FakeConn()
    pool = FakePool(conn)
    return EntityAliasMapRepo(pool), conn  # type: ignore[arg-type]


# ── lookup ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lookup_miss_returns_none(repo_and_conn):
    repo, _ = repo_and_conn
    result = await repo.lookup(uuid4(), "global", "person", "kai")
    assert result is None


@pytest.mark.asyncio
async def test_lookup_hit_returns_target_entity_id(repo_and_conn):
    repo, _ = repo_and_conn
    user_id = uuid4()
    target_id = "a3f2cafe" * 4  # 32 hex
    await repo.record_merge(
        user_id, "global", "person", "alice", target_id, "src1234",
    )
    result = await repo.lookup(user_id, "global", "person", "alice")
    assert result == target_id


@pytest.mark.asyncio
async def test_lookup_empty_alias_returns_none_defensive(repo_and_conn):
    """canonicalize_entity_name CAN produce empty for purely-honorific
    inputs (e.g. ``master ``) — defensive guard so the SQL doesn't
    receive an empty string and 500."""
    repo, _ = repo_and_conn
    result = await repo.lookup(uuid4(), "global", "person", "")
    assert result is None


# ── record_merge ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_merge_inserts_row(repo_and_conn):
    repo, conn = repo_and_conn
    user_id = uuid4()
    await repo.record_merge(
        user_id, "global", "person", "alice", "tgt1", "src1",
    )
    assert (user_id, "global", "person", "alice") in conn.store
    row = conn.store[(user_id, "global", "person", "alice")]
    assert row["target_entity_id"] == "tgt1"
    assert row["source_entity_id"] == "src1"
    assert row["reason"] == "merge"


@pytest.mark.asyncio
async def test_record_merge_on_conflict_does_not_overwrite(repo_and_conn):
    """First merge wins. A second merge attempt for the same
    (user, scope, kind, alias) must NOT silently re-target — that's
    what repoint_target is for."""
    repo, conn = repo_and_conn
    user_id = uuid4()
    await repo.record_merge(
        user_id, "global", "person", "alice", "tgt_first", "src1",
    )
    await repo.record_merge(
        user_id, "global", "person", "alice", "tgt_second", "src2",
    )
    row = conn.store[(user_id, "global", "person", "alice")]
    assert row["target_entity_id"] == "tgt_first"  # not overwritten


# ── list_for_entity ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_for_entity_reverse_lookup(repo_and_conn):
    repo, _ = repo_and_conn
    user_id = uuid4()
    target = "tgt1"
    await repo.record_merge(user_id, "global", "person", "alice", target, "s1")
    await repo.record_merge(user_id, "global", "person", "lex", target, "s1")
    await repo.record_merge(user_id, "global", "person", "alex", "tgt2", "s3")

    rows = await repo.list_for_entity(target)
    aliases = {r["canonical_alias"] for r in rows}
    assert aliases == {"alice", "lex"}
    # tgt2's alias not included.
    assert "alex" not in aliases


# ── bulk_backfill ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_backfill_inserts_new_rows_with_backfill_reason(
    repo_and_conn,
):
    repo, conn = repo_and_conn
    user_id = uuid4()
    rows = [
        (user_id, "global", "person", "alice", "tgt1"),
        (user_id, "global", "person", "lex", "tgt1"),
        (user_id, "proj1", "place", "phoenix", "tgt2"),
    ]
    inserted = await repo.bulk_backfill(rows)
    assert inserted == 3
    # All rows have reason='backfill' + source_entity_id NULL.
    for key in [
        (user_id, "global", "person", "alice"),
        (user_id, "global", "person", "lex"),
        (user_id, "proj1", "place", "phoenix"),
    ]:
        assert conn.store[key]["reason"] == "backfill"
        assert conn.store[key]["source_entity_id"] is None


@pytest.mark.asyncio
async def test_bulk_backfill_idempotent_skip_existing(repo_and_conn):
    """Re-running the backfill on an already-populated table is a
    no-op for existing keys — supports interrupted-and-restarted
    backfill runs."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    # First populate via merge.
    await repo.record_merge(
        user_id, "global", "person", "alice", "tgt_merge", "src1",
    )
    # Now backfill the same key with a different (wrong) target.
    inserted = await repo.bulk_backfill([
        (user_id, "global", "person", "alice", "tgt_backfill"),
    ])
    assert inserted == 0  # ON CONFLICT DO NOTHING
    # Existing row preserved with reason='merge'.
    assert (await repo.lookup(
        user_id, "global", "person", "alice",
    )) == "tgt_merge"


# ── scope + kind isolation ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_scope_isolation_global_vs_project(repo_and_conn):
    """Same alias in different project_scope = independent rows."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.record_merge(
        user_id, "global", "person", "phoenix", "tgt_global", "s1",
    )
    await repo.record_merge(
        user_id, "proj1", "person", "phoenix", "tgt_proj", "s2",
    )
    assert (await repo.lookup(
        user_id, "global", "person", "phoenix",
    )) == "tgt_global"
    assert (await repo.lookup(
        user_id, "proj1", "person", "phoenix",
    )) == "tgt_proj"


@pytest.mark.asyncio
async def test_kind_isolation_person_vs_place(repo_and_conn):
    """'Phoenix the person' and 'Phoenix the place' must never
    cross-redirect."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.record_merge(
        user_id, "global", "person", "phoenix", "person_target", "s1",
    )
    await repo.record_merge(
        user_id, "global", "place", "phoenix", "place_target", "s2",
    )
    assert (await repo.lookup(
        user_id, "global", "person", "phoenix",
    )) == "person_target"
    assert (await repo.lookup(
        user_id, "global", "place", "phoenix",
    )) == "place_target"


# ── repoint_target (REVIEW-DESIGN chain re-point) ──────────────────


@pytest.mark.asyncio
async def test_repoint_target_chain_merge(repo_and_conn):
    """A→B today, then B→C tomorrow. After repoint_target(B→C), the
    A row points at C — not the deleted B."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    # Day 1: merge A into B.
    await repo.record_merge(
        user_id, "global", "person", "alice", "B_id", "A_id",
    )
    # Day 2: merge B into C — this would normally just write B's
    # aliases as new redirect rows, but we ALSO need A's existing row
    # (alice → B) to follow.
    count = await repo.repoint_target(user_id, "B_id", "C_id")
    assert count == 1
    assert (await repo.lookup(
        user_id, "global", "person", "alice",
    )) == "C_id"


@pytest.mark.asyncio
async def test_repoint_target_no_op_when_old_equals_new(repo_and_conn):
    """Defensive: repoint(X, X) shouldn't UPDATE anything."""
    repo, _ = repo_and_conn
    user_id = uuid4()
    await repo.record_merge(
        user_id, "global", "person", "alice", "X_id", "src1",
    )
    count = await repo.repoint_target(user_id, "X_id", "X_id")
    assert count == 0
    # Still points at X.
    assert (await repo.lookup(
        user_id, "global", "person", "alice",
    )) == "X_id"


@pytest.mark.asyncio
async def test_repoint_target_scoped_per_user(repo_and_conn):
    """Repoint must NOT affect rows owned by other users — multi-tenant
    safety."""
    repo, _ = repo_and_conn
    user_a = uuid4()
    user_b = uuid4()
    await repo.record_merge(user_a, "global", "person", "alice", "B_id", "s")
    await repo.record_merge(user_b, "global", "person", "alice", "B_id", "s")

    # Only user_a merges B into C.
    count = await repo.repoint_target(user_a, "B_id", "C_id")
    assert count == 1
    assert (await repo.lookup(
        user_a, "global", "person", "alice",
    )) == "C_id"
    # user_b's row untouched.
    assert (await repo.lookup(
        user_b, "global", "person", "alice",
    )) == "B_id"
