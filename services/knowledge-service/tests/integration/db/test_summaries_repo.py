from uuid import uuid4

import pytest

from app.db.repositories import VersionMismatchError
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


@pytest.mark.asyncio
async def test_d_k8_03_global_upsert_guards_on_expected_version(pool):
    """D-K8-03: two clients racing to upsert the same global bio.
    Client A reads v1, Client B writes and advances to v2, Client A
    tries to write against v1 and gets VersionMismatchError with the
    current row."""
    repo = SummariesRepo(pool)
    user = uuid4()
    first = await repo.upsert(user, "global", None, "v1")
    assert first.version == 1

    # Client B advances the row to v2.
    second = await repo.upsert(
        user, "global", None, "v2", expected_version=1
    )
    assert second.version == 2

    # Client A still thinks the version is 1 — must raise.
    with pytest.raises(VersionMismatchError) as exc_info:
        await repo.upsert(
            user, "global", None, "v1-stale", expected_version=1
        )
    assert exc_info.value.current.version == 2
    assert exc_info.value.current.content == "v2"

    # Defense-in-depth: row unchanged.
    current = await repo.get(user, "global", None)
    assert current is not None
    assert current.content == "v2"


@pytest.mark.asyncio
async def test_d_k8_03_global_insert_ignores_expected_version(pool):
    """D-K8-03: first save (no prior row) goes through the INSERT
    path and always succeeds regardless of expected_version — the
    client couldn't have obtained an ETag before the row existed."""
    repo = SummariesRepo(pool)
    user = uuid4()
    # Pass a nonsensical expected_version; it should be ignored on
    # the INSERT path.
    result = await repo.upsert(
        user, "global", None, "first", expected_version=99
    )
    assert result.version == 1
    assert result.content == "first"


@pytest.mark.asyncio
async def test_d_k8_03_project_scoped_ownership_vs_version_mismatch(pool):
    """D-K8-03: the project-scoped path can fail with 0 rows for
    TWO reasons — (a) the user doesn't own the project, or (b) the
    version didn't match. The repo's follow-up SELECT must
    distinguish them: ownership failure → None (404), version
    mismatch → raise."""
    repo = SummariesRepo(pool)
    user_a = uuid4()
    user_b = uuid4()

    # Seed a project for user_a via the projects repo.
    async with pool.acquire() as conn:
        proj_row = await conn.fetchrow(
            """
            INSERT INTO knowledge_projects (user_id, name, project_type)
            VALUES ($1, 'p', 'general')
            RETURNING project_id
            """,
            user_a,
        )
        project_id = proj_row["project_id"]

    # First save by user_a (INSERT path, no expected_version needed).
    first = await repo.upsert_project_scoped(user_a, project_id, "v1")
    assert first is not None and first.version == 1

    # user_b tries to write the same project_id → ownership failure
    # (the CTE's EXISTS filter finds no matching row for user_b),
    # even with a legit-looking expected_version.
    result = await repo.upsert_project_scoped(
        user_b, project_id, "leak", expected_version=1
    )
    assert result is None  # 404, not raise

    # user_a with stale expected_version → version mismatch.
    await repo.upsert_project_scoped(
        user_a, project_id, "v2", expected_version=1
    )
    with pytest.raises(VersionMismatchError) as exc_info:
        await repo.upsert_project_scoped(
            user_a, project_id, "stale", expected_version=1
        )
    assert exc_info.value.current.version == 2
    assert exc_info.value.current.content == "v2"
