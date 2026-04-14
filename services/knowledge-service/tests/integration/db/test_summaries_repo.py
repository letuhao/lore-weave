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
async def test_d_k8_01_update_writes_history_row(pool):
    """D-K8-01: every successful summary update writes the PRE-update
    state to knowledge_summary_versions. The INSERT path (first save)
    writes nothing — v1 is the original, no prior state to archive."""
    repo = SummariesRepo(pool)
    user = uuid4()

    await repo.upsert(user, "global", None, "v1")
    # First save — history should still be empty.
    versions = await repo.list_versions(user, "global", None)
    assert versions == []

    await repo.upsert(user, "global", None, "v2", expected_version=1)
    versions = await repo.list_versions(user, "global", None)
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].content == "v1"
    assert versions[0].edit_source == "manual"

    await repo.upsert(user, "global", None, "v3", expected_version=2)
    versions = await repo.list_versions(user, "global", None)
    assert len(versions) == 2
    # Newest first.
    assert [v.version for v in versions] == [2, 1]
    assert [v.content for v in versions] == ["v2", "v1"]


@pytest.mark.asyncio
async def test_d_k8_01_history_is_cross_user_isolated(pool):
    """D-K8-01: the version-history row filter is user_id on the
    denormalised column, so cross-user reads return empty."""
    repo = SummariesRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    await repo.upsert(user_a, "global", None, "a-v1")
    await repo.upsert(user_a, "global", None, "a-v2", expected_version=1)
    await repo.upsert(user_b, "global", None, "b-v1")
    # user_a has one history row, user_b has none.
    a_hist = await repo.list_versions(user_a, "global", None)
    b_hist = await repo.list_versions(user_b, "global", None)
    assert len(a_hist) == 1
    assert a_hist[0].content == "a-v1"
    assert b_hist == []


@pytest.mark.asyncio
async def test_d_k8_01_rollback_creates_new_version_not_rewind(pool):
    """D-K8-01: rollback to a historical version creates a NEW row
    (current + 1) with the target's content. History gains a new
    entry for the displaced pre-rollback state with edit_source='rollback'.
    The version counter is monotonic — never rewound."""
    repo = SummariesRepo(pool)
    user = uuid4()

    await repo.upsert(user, "global", None, "alpha")
    await repo.upsert(user, "global", None, "beta", expected_version=1)
    await repo.upsert(user, "global", None, "gamma", expected_version=2)
    # State: live row version=3 content="gamma", history=[v1 alpha, v2 beta]

    rolled = await repo.rollback_to(
        user, "global", None,
        target_version=1,
        expected_version=3,
    )
    # NEW version is 4 (monotonic), content is alpha.
    assert rolled.version == 4
    assert rolled.content == "alpha"

    # History now has 3 rows: v1 manual, v2 manual, v3 rollback.
    history = await repo.list_versions(user, "global", None)
    assert len(history) == 3
    by_version = {h.version: h for h in history}
    assert by_version[1].edit_source == "manual"
    assert by_version[1].content == "alpha"
    assert by_version[2].edit_source == "manual"
    assert by_version[2].content == "beta"
    assert by_version[3].edit_source == "rollback"
    assert by_version[3].content == "gamma"


@pytest.mark.asyncio
async def test_d_k8_01_rollback_requires_matching_expected_version(pool):
    """D-K8-01: rollback honours If-Match. A stale History panel
    can't accidentally roll forward over a concurrent edit."""
    repo = SummariesRepo(pool)
    user = uuid4()
    await repo.upsert(user, "global", None, "v1")
    await repo.upsert(user, "global", None, "v2", expected_version=1)
    # Current version is 2; try rollback with expected_version=1.
    with pytest.raises(VersionMismatchError) as exc_info:
        await repo.rollback_to(
            user, "global", None, target_version=1, expected_version=1
        )
    assert exc_info.value.current.version == 2
    # Row unchanged.
    current = await repo.get(user, "global", None)
    assert current is not None
    assert current.content == "v2"
    assert current.version == 2


@pytest.mark.asyncio
async def test_d_k8_01_rollback_target_missing_raises_lookup(pool):
    """D-K8-01: rolling back to a version that was never archived
    raises LookupError (router maps to 404)."""
    repo = SummariesRepo(pool)
    user = uuid4()
    await repo.upsert(user, "global", None, "only")
    with pytest.raises(LookupError):
        await repo.rollback_to(
            user, "global", None, target_version=99, expected_version=1
        )


@pytest.mark.asyncio
async def test_d_k8_01_cascade_delete_removes_history(pool):
    """D-K8-01: deleting the parent summary row must cascade to
    history (ON DELETE CASCADE on the FK). K7d /user-data delete
    relies on this to clean up completely."""
    repo = SummariesRepo(pool)
    user = uuid4()
    await repo.upsert(user, "global", None, "v1")
    await repo.upsert(user, "global", None, "v2", expected_version=1)
    assert len(await repo.list_versions(user, "global", None)) == 1
    # Delete the parent row.
    deleted = await repo.delete(user, "global", None)
    assert deleted is True
    # History for this scope should be gone too.
    assert await repo.list_versions(user, "global", None) == []


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
