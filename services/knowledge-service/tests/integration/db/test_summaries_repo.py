from uuid import uuid4

import pytest

from app.db.repositories.summaries import SummariesRepo


@pytest.mark.asyncio
async def test_upsert_creates_then_updates(pool):
    repo = SummariesRepo(pool)
    user = uuid4()

    first = await repo.upsert(user, "global", None, "hello world")
    assert first.version == 1
    assert first.content == "hello world"
    assert first.token_count is not None and first.token_count >= 1

    second = await repo.upsert(user, "global", None, "hello again")
    assert second.summary_id == first.summary_id
    assert second.version == 2
    assert second.content == "hello again"
    assert second.updated_at >= first.updated_at


@pytest.mark.asyncio
async def test_get_null_scope_id(pool):
    repo = SummariesRepo(pool)
    user = uuid4()
    await repo.upsert(user, "global", None, "bio")
    got = await repo.get(user, "global", None)
    assert got is not None
    assert got.content == "bio"


@pytest.mark.asyncio
async def test_get_project_scope(pool):
    repo = SummariesRepo(pool)
    user = uuid4()
    proj = uuid4()
    await repo.upsert(user, "project", proj, "project bio")
    got = await repo.get(user, "project", proj)
    assert got is not None
    assert got.content == "project bio"
    # Different project id must not collide
    other = await repo.get(user, "project", uuid4())
    assert other is None


@pytest.mark.asyncio
async def test_delete(pool):
    repo = SummariesRepo(pool)
    user = uuid4()
    await repo.upsert(user, "global", None, "to be deleted")
    assert await repo.delete(user, "global", None) is True
    assert await repo.get(user, "global", None) is None
    assert await repo.delete(user, "global", None) is False


@pytest.mark.asyncio
async def test_cross_user_isolation(pool):
    repo = SummariesRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    await repo.upsert(user_a, "global", None, "a-secret")
    assert await repo.get(user_b, "global", None) is None
    # B upserting doesn't affect A
    await repo.upsert(user_b, "global", None, "b-secret")
    a_got = await repo.get(user_a, "global", None)
    assert a_got is not None and a_got.content == "a-secret"
