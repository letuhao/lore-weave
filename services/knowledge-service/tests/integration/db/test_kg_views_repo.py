"""Lane LD — live-PG integration tests for GraphViewsRepo.

Requires a real Postgres (TEST_KNOWLEDGE_DB_URL); skips otherwise via the
shared `pool` fixture. The `pool` fixture does NOT truncate kg_views, so each
test resets it itself. Covers CRUD, upsert (create vs update), the
owner-scoped UNIQUE(project_id,user_id,code), and the owner-scoped deny
(user B cannot see / delete user A's view).
"""

from __future__ import annotations

from uuid import uuid4

import asyncpg
import pytest

from app.db.repositories.graph_views import GraphViewsRepo

pytestmark = pytest.mark.asyncio


async def _reset(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_views RESTART IDENTITY CASCADE")


async def test_create_get_list(pool):
    await _reset(pool)
    repo = GraphViewsRepo(pool)
    user = uuid4()
    pid = f"proj-{uuid4()}"
    v = await repo.create(user, pid, code="drives", name="Drive Map", edge_type_codes=["PURSUES"])
    assert v.code == "drives" and v.user_id == user and v.edge_type_codes == ["PURSUES"]
    got = await repo.get(user, pid, "drives")
    assert got is not None and got.view_id == v.view_id
    listed = await repo.list(user, pid)
    assert [x.code for x in listed] == ["drives"]


async def test_create_duplicate_code_raises_unique(pool):
    await _reset(pool)
    repo = GraphViewsRepo(pool)
    user = uuid4()
    pid = f"proj-{uuid4()}"
    await repo.create(user, pid, code="lens", name="L")
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.create(user, pid, code="lens", name="L2")


async def test_same_code_distinct_users_no_conflict(pool):
    """UNIQUE(project_id, user_id, code) — two users may each own 'lens' in the
    SAME project (the per-user tenancy key)."""
    await _reset(pool)
    repo = GraphViewsRepo(pool)
    a, b = uuid4(), uuid4()
    pid = f"proj-{uuid4()}"
    va = await repo.create(a, pid, code="lens", name="A")
    vb = await repo.create(b, pid, code="lens", name="B")
    assert va.view_id != vb.view_id


async def test_upsert_create_then_update(pool):
    await _reset(pool)
    repo = GraphViewsRepo(pool)
    user = uuid4()
    pid = f"proj-{uuid4()}"
    v1, created1 = await repo.upsert(user, pid, code="lens", name="v1")
    assert created1 is True
    v2, created2 = await repo.upsert(user, pid, code="lens", name="v2", node_kind_codes=["character"])
    assert created2 is False
    assert v2.name == "v2" and v2.node_kind_codes == ["character"]
    assert v2.view_id == v1.view_id           # same row updated
    assert v2.created_at == v1.created_at      # created_at preserved
    assert v2.updated_at >= v1.updated_at      # updated_at bumped


async def test_delete_returns_bool(pool):
    await _reset(pool)
    repo = GraphViewsRepo(pool)
    user = uuid4()
    pid = f"proj-{uuid4()}"
    await repo.create(user, pid, code="lens", name="L")
    assert await repo.delete(user, pid, "lens") is True
    assert await repo.delete(user, pid, "lens") is False  # already gone


async def test_owner_scoped_deny(pool):
    """User B cannot see, fetch, or delete user A's view (owner scoping)."""
    await _reset(pool)
    repo = GraphViewsRepo(pool)
    a, b = uuid4(), uuid4()
    pid = f"proj-{uuid4()}"
    await repo.create(a, pid, code="alens", name="A lens")
    # B's reads see nothing of A's
    assert await repo.get(b, pid, "alens") is None
    assert await repo.list(b, pid) == []
    # B's delete of A's code is a no-op (cannot touch A's row)
    assert await repo.delete(b, pid, "alens") is False
    # A's row is intact
    assert await repo.get(a, pid, "alens") is not None
