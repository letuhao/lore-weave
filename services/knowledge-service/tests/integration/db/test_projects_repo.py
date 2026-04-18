from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.db.models import ProjectCreate, ProjectUpdate
from app.db.repositories import VersionMismatchError
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
    # Archive must not affect it (K7b-I2: archive returns Project | None)
    assert await repo.archive(user_b, p.project_id) is None
    # Delete must not affect it
    assert await repo.delete(user_b, p.project_id) is False
    assert await repo.get(user_a, p.project_id) is not None


@pytest.mark.asyncio
async def test_d_k8_03_update_bumps_version_and_guards_on_expected_version(pool):
    """D-K8-03: when expected_version is provided, the UPDATE gates on
    it, bumps the column, and raises VersionMismatchError on conflict.
    Two-client scenario: A reads v1, B reads v1 and writes v2, A tries
    to write against v1 and gets VersionMismatchError with the fresh row."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("locktest"))
    assert p.version == 1

    # Client A has v1. Client B writes against v1 and succeeds.
    updated_b = await repo.update(
        user,
        p.project_id,
        ProjectUpdate(name="by-B"),
        expected_version=1,
    )
    assert updated_b is not None
    assert updated_b.version == 2
    assert updated_b.name == "by-B"

    # Client A still thinks the version is 1 — must be rejected.
    with pytest.raises(VersionMismatchError) as exc_info:
        await repo.update(
            user,
            p.project_id,
            ProjectUpdate(name="by-A"),
            expected_version=1,
        )
    # The exception carries the CURRENT row so the client can refresh.
    assert exc_info.value.current.version == 2
    assert exc_info.value.current.name == "by-B"

    # Defense-in-depth: no overwrite happened.
    current = await repo.get(user, p.project_id)
    assert current is not None
    assert current.name == "by-B"
    assert current.version == 2


@pytest.mark.asyncio
async def test_d_k8_03_empty_patch_is_noop_does_not_bump_version(pool):
    """D-K8-03: empty patches still honour the K7b no-op contract —
    no version bump, no updated_at change. Callers can safely retry
    empty patches without spuriously incrementing the counter."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("noop"))
    result = await repo.update(
        user, p.project_id, ProjectUpdate(), expected_version=1
    )
    assert result is not None
    assert result.version == 1  # unchanged
    assert result.updated_at == p.updated_at  # unchanged


@pytest.mark.asyncio
async def test_d_k8_03_update_without_expected_version_legacy_path(pool):
    """D-K8-03: when expected_version is None, update() behaves
    exactly as it did before this change — no version bump, no
    412. Preserves the legacy caller contract (internal callers
    that don't need optimistic concurrency)."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("legacy"))
    updated = await repo.update(
        user, p.project_id, ProjectUpdate(name="new")
    )
    assert updated is not None
    assert updated.name == "new"
    assert updated.version == 1  # NOT bumped — legacy path


@pytest.mark.asyncio
async def test_d_k8_03_cross_user_with_expected_version_returns_none(pool):
    """D-K8-03: the 404 (cross-user) case still returns None, not
    VersionMismatchError. The follow-up SELECT in the repo's zero-row
    path finds no row for this user_id and bails out cleanly."""
    repo = ProjectsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    p = await repo.create(user_a, _mk("their"))
    result = await repo.update(
        user_b, p.project_id, ProjectUpdate(name="hijacked"), expected_version=1
    )
    assert result is None


@pytest.mark.asyncio
async def test_restore_via_update_is_archived_false(pool):
    """K-CLEAN-3: PATCH is_archived=false on an archived row restores
    it. The default list endpoint (excludes archived) starts including
    it again. This is the only direction the PATCH endpoint allows;
    setting is_archived=true is rejected at the router."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("torestore"))
    archived = await repo.archive(user, p.project_id)
    assert archived is not None and archived.is_archived is True
    restored = await repo.update(
        user, p.project_id, ProjectUpdate(is_archived=False)
    )
    assert restored is not None
    assert restored.is_archived is False
    active_names = [r.name for r in await repo.list(user)]
    assert "torestore" in active_names


@pytest.mark.asyncio
async def test_update_empty_patch_is_noop(pool):
    """Empty patch must return the current row AND not touch updated_at."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("q"))
    unchanged = await repo.update(user, p.project_id, ProjectUpdate())
    assert unchanged is not None
    assert unchanged.project_id == p.project_id
    assert unchanged.name == "q"
    # No-op contract: updated_at must NOT be bumped.
    assert unchanged.updated_at == p.updated_at


@pytest.mark.asyncio
async def test_update_none_on_not_null_column_is_skipped(pool):
    """Setting description=None (a NOT-NULL column) must be skipped,
    not raise a DB violation. The row must stay unchanged."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("r", description="original"))
    result = await repo.update(
        user, p.project_id, ProjectUpdate(description=None, instructions=None, name=None)
    )
    assert result is not None
    assert result.description == "original"
    assert result.instructions == ""
    assert result.name == "r"
    # All fields were None → entire patch is a no-op.
    assert result.updated_at == p.updated_at


@pytest.mark.asyncio
async def test_update_clears_book_id(pool):
    """book_id is nullable. Setting it to None explicitly must clear
    the link; omitting it must leave it alone."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    book = uuid4()
    p = await repo.create(user, _mk("s", book_id=book))
    assert p.book_id == book

    # Explicit clear
    cleared = await repo.update(user, p.project_id, ProjectUpdate(book_id=None))
    assert cleared is not None
    assert cleared.book_id is None
    assert cleared.updated_at > p.updated_at

    # Re-set
    new_book = uuid4()
    reset = await repo.update(user, p.project_id, ProjectUpdate(book_id=new_book))
    assert reset is not None
    assert reset.book_id == new_book

    # Omitting book_id in a different patch must not affect it
    omitted = await repo.update(user, p.project_id, ProjectUpdate(name="s2"))
    assert omitted is not None
    assert omitted.book_id == new_book
    assert omitted.name == "s2"


@pytest.mark.asyncio
async def test_k12_4_update_embedding_model_auto_derives_dimension(pool):
    """K12.4: PATCH embedding_model also sets embedding_dimension via
    the EMBEDDING_MODEL_TO_DIM map. Clearing the model (None) clears
    the dim. Unknown models yield dim=None so the downstream L3
    pipeline skips cleanly."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("s"))
    assert p.embedding_model is None
    assert p.embedding_dimension is None

    # Set a known model → dim auto-derived.
    out = await repo.update(
        user, p.project_id, ProjectUpdate(embedding_model="bge-m3"),
    )
    assert out is not None
    assert out.embedding_model == "bge-m3"
    assert out.embedding_dimension == 1024

    # Switch to another known model → dim updates.
    out = await repo.update(
        user, p.project_id,
        ProjectUpdate(embedding_model="text-embedding-3-small"),
    )
    assert out is not None
    assert out.embedding_dimension == 1536

    # Clear the model → dim also cleared.
    out = await repo.update(
        user, p.project_id, ProjectUpdate(embedding_model=None),
    )
    assert out is not None
    assert out.embedding_model is None
    assert out.embedding_dimension is None

    # Unknown model → dim stays None (downstream L3 skips cleanly).
    out = await repo.update(
        user, p.project_id,
        ProjectUpdate(embedding_model="some-unsupported-model"),
    )
    assert out is not None
    assert out.embedding_model == "some-unsupported-model"
    assert out.embedding_dimension is None


@pytest.mark.asyncio
async def test_create_rejects_whitespace_only_name():
    with pytest.raises(ValidationError):
        ProjectCreate(name="   ", project_type="general")
    # Leading/trailing whitespace is stripped and the result must still
    # have at least one non-whitespace character.
    stripped = ProjectCreate(name="  alpha  ", project_type="general")
    assert stripped.name == "alpha"


@pytest.mark.asyncio
async def test_update_rejects_whitespace_only_name():
    with pytest.raises(ValidationError):
        ProjectUpdate(name="   ")
