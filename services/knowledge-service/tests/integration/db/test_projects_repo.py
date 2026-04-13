from uuid import UUID, uuid4

import pytest

from app.db.models import ProjectCreate, ProjectUpdate
from app.db.repositories.projects import ProjectsRepo


def _mk(name: str = "p", **kw) -> ProjectCreate:
    return ProjectCreate(name=name, project_type="general", **kw)


@pytest.mark.asyncio
async def test_create_and_get(pool):
    repo = ProjectsRepo(pool)
    user = uuid4()
    created = await repo.create(user, _mk("alpha", instructions="be concise"))
    assert created.name == "alpha"
    assert created.user_id == user
    assert created.extraction_enabled is False
    assert created.extraction_status == "disabled"

    got = await repo.get(user, created.project_id)
    assert got is not None
    assert got.project_id == created.project_id
    assert got.instructions == "be concise"


@pytest.mark.asyncio
async def test_list_excludes_archived_by_default(pool):
    repo = ProjectsRepo(pool)
    user = uuid4()
    a = await repo.create(user, _mk("a"))
    b = await repo.create(user, _mk("b"))
    await repo.archive(user, a.project_id)

    active = await repo.list(user)
    assert [p.project_id for p in active] == [b.project_id]

    allp = await repo.list(user, include_archived=True)
    ids = {p.project_id for p in allp}
    assert ids == {a.project_id, b.project_id}


@pytest.mark.asyncio
async def test_update_patches_fields(pool):
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("x"))
    updated = await repo.update(
        user, p.project_id, ProjectUpdate(name="y", instructions="new")
    )
    assert updated is not None
    assert updated.name == "y"
    assert updated.instructions == "new"
    assert updated.updated_at >= p.updated_at


@pytest.mark.asyncio
async def test_delete(pool):
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("z"))
    assert await repo.delete(user, p.project_id) is True
    assert await repo.get(user, p.project_id) is None
    assert await repo.delete(user, p.project_id) is False


@pytest.mark.asyncio
async def test_cross_user_isolation(pool):
    """User B must NOT be able to read/update/delete user A's project."""
    repo = ProjectsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    p = await repo.create(user_a, _mk("secret"))

    # Read
    assert await repo.get(user_b, p.project_id) is None
    # Not in listing
    assert await repo.list(user_b) == []
    # Update must not affect it
    assert await repo.update(user_b, p.project_id, ProjectUpdate(name="pwned")) is None
    still = await repo.get(user_a, p.project_id)
    assert still is not None and still.name == "secret"
    # Archive must not affect it
    assert await repo.archive(user_b, p.project_id) is False
    # Delete must not affect it
    assert await repo.delete(user_b, p.project_id) is False
    assert await repo.get(user_a, p.project_id) is not None


@pytest.mark.asyncio
async def test_update_empty_patch_returns_current(pool):
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("q"))
    unchanged = await repo.update(user, p.project_id, ProjectUpdate())
    assert unchanged is not None
    assert unchanged.project_id == p.project_id
    assert unchanged.name == "q"
