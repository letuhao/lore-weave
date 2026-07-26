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
async def test_erase_resolver_includes_archived_assistant_epochs(pool):
    """A1 (right-to-erasure) — a CLOSED employment epoch is an ARCHIVED assistant project. It must be
    EXCLUDED from the recall-exclude resolver (`list_assistant_project_ids`, D16 — a closed epoch stays
    out of default recall) but INCLUDED by the account-erase resolver (`list_all_assistant_project_ids`),
    because close-epoch archives without purging — the decryptable diary data still lives under it and
    right-to-erasure must reach it. Resolving erase with `NOT is_archived` (the old bug) stranded it."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    # A job change: the first (old) epoch is closed → archived; a fresh epoch becomes the active one.
    old, _ = await repo.get_or_create_assistant_project(user, uuid4())
    await repo.archive(user, old.project_id)
    new, created = await repo.get_or_create_assistant_project(user, uuid4())
    assert created and new.project_id != old.project_id  # the archived one didn't satisfy get-or-create

    recall_targets = set(await repo.list_assistant_project_ids(user))
    erase_targets = set(await repo.list_all_assistant_project_ids(user))

    assert recall_targets == {str(new.project_id)}  # archived epoch stays OUT of recall
    # A1 fix: erase reaches BOTH — the archived epoch is not stranded.
    assert erase_targets == {str(new.project_id), str(old.project_id)}
    assert str(old.project_id) in erase_targets and str(old.project_id) not in recall_targets


@pytest.mark.asyncio
async def test_erase_resolver_is_user_scoped(pool):
    """A1 — the archived-inclusive erase resolver is still tenant-scoped: user B's archived assistant
    epoch never appears in user A's erase targets."""
    repo = ProjectsRepo(pool)
    user_a, user_b = uuid4(), uuid4()
    b_old, _ = await repo.get_or_create_assistant_project(user_b, uuid4())
    await repo.archive(user_b, b_old.project_id)
    a_active, _ = await repo.get_or_create_assistant_project(user_a, uuid4())

    a_erase = set(await repo.list_all_assistant_project_ids(user_a))
    assert a_erase == {str(a_active.project_id)}
    assert str(b_old.project_id) not in a_erase


@pytest.mark.asyncio
async def test_list_filters_by_book_id(pool):
    """C5 (ARCH-1): the editor AI panel resolves a book's project via the
    book_id filter. Returns only the project linked to that book, scoped to
    the user; empty when the book has no project."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    book = uuid4()
    other_book = uuid4()
    linked = await repo.create(user, _mk("linked", book_id=book))
    await repo.create(user, _mk("other", book_id=other_book))
    await repo.create(user, _mk("unlinked"))  # no book

    matched = await repo.list(user, book_id=book)
    assert [p.project_id for p in matched] == [linked.project_id]

    # a book with no project → empty
    assert await repo.list(user, book_id=uuid4()) == []


# ── G4 (world-level project) — real-PG world_id binding ────────────────


@pytest.mark.asyncio
async def test_create_or_get_stamps_world_id_idempotently(pool):
    """G4: world-create provisions the world-level project via create_or_get
    with world_id. A re-provision for the same (user, bible book) returns the
    SAME project and stamps world_id if it wasn't carried yet — never dups."""
    repo = ProjectsRepo(pool)
    user, bible_book, world = uuid4(), uuid4(), uuid4()
    # first provision WITHOUT world_id (a pre-existing bible-book project)
    p1, c1 = await repo.create_or_get(
        user, ProjectCreate(name="World Bible", project_type="book", book_id=bible_book)
    )
    assert c1 is True and p1.world_id is None
    # re-provision WITH world_id → same project, now stamped (idempotent)
    p2, c2 = await repo.create_or_get(
        user,
        ProjectCreate(
            name="World Bible", project_type="book",
            book_id=bible_book, world_id=world,
        ),
    )
    assert c2 is False
    assert p2.project_id == p1.project_id
    assert p2.world_id == world
    # exactly one project for the bible book
    assert len(await repo.list(user, world_id=world)) == 1


@pytest.mark.asyncio
async def test_create_or_get_refuses_world_id_rebind(pool):
    """G4 (review #3): a bible book belongs to exactly one world and never moves.
    create_or_get stamps world_id only when currently NULL — a re-provision with
    a DIFFERENT world_id is refused (the binding stays put), and a re-provision
    with the SAME world_id is a no-op."""
    repo = ProjectsRepo(pool)
    user, bible_book, world_a, world_b = uuid4(), uuid4(), uuid4(), uuid4()
    p1, _ = await repo.create_or_get(
        user,
        ProjectCreate(name="wb", project_type="book", book_id=bible_book, world_id=world_a),
    )
    assert p1.world_id == world_a
    # re-provision with a DIFFERENT world → binding unchanged (no silent rebind)
    p2, created2 = await repo.create_or_get(
        user,
        ProjectCreate(name="wb", project_type="book", book_id=bible_book, world_id=world_b),
    )
    assert created2 is False
    assert p2.project_id == p1.project_id
    assert p2.world_id == world_a  # NOT world_b
    # re-provision with the SAME world → no-op, still bound to world_a
    p3, _ = await repo.create_or_get(
        user,
        ProjectCreate(name="wb", project_type="book", book_id=bible_book, world_id=world_a),
    )
    assert p3.world_id == world_a


@pytest.mark.asyncio
async def test_world_level_project_hidden_from_home_but_book_id_resolves(pool):
    """G4: a world-level project (world_id set) is excluded from the HOME
    browse, returned by ?world_id, and STILL resolvable by ?book_id (the
    useWorldProject graph resolver)."""
    repo = ProjectsRepo(pool)
    user, bible_book, world = uuid4(), uuid4(), uuid4()
    await repo.create(user, _mk("normal-1"))
    wp, _ = await repo.create_or_get(
        user,
        ProjectCreate(
            name="World Bible", project_type="book",
            book_id=bible_book, world_id=world,
        ),
    )
    # HOME browse excludes the world project, keeps the normal one
    home = await repo.list(user)
    assert wp.project_id not in {p.project_id for p in home}
    assert "normal-1" in {p.name for p in home}
    # ?world_id returns it
    by_world = await repo.list(user, world_id=world)
    assert [p.project_id for p in by_world] == [wp.project_id]
    # ?book_id (the bible book) still resolves it — exempt from the HOME hide
    by_book = await repo.list(user, book_id=bible_book)
    assert [p.project_id for p in by_book] == [wp.project_id]


@pytest.mark.asyncio
async def test_patch_clears_world_id(pool):
    """G4: PATCH world_id=None detaches a project from its world."""
    repo = ProjectsRepo(pool)
    user, book, world = uuid4(), uuid4(), uuid4()
    p, _ = await repo.create_or_get(
        user,
        ProjectCreate(name="wb", project_type="book", book_id=book, world_id=world),
    )
    assert p.world_id == world
    cleared = await repo.update(user, p.project_id, ProjectUpdate(world_id=None))
    assert cleared is not None and cleared.world_id is None


@pytest.mark.asyncio
async def test_list_by_book_id_is_user_scoped(pool):
    """The book filter must not leak another user's project for the same book."""
    repo = ProjectsRepo(pool)
    user_a, user_b = uuid4(), uuid4()
    book = uuid4()
    await repo.create(user_a, _mk("theirs", book_id=book))
    # user_b asking for the same book sees nothing
    assert await repo.list(user_b, book_id=book) == []


def _mk_book(name: str = "bk", *, book_id: UUID) -> ProjectCreate:
    return ProjectCreate(name=name, project_type="book", book_id=book_id)


@pytest.mark.asyncio
async def test_create_or_get_book_is_idempotent(pool):
    """D-COMP-POST-WORK-RACE: a repeat book-project create_or_get for the same
    (user, book) returns the EXISTING project, not a duplicate."""
    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    first, created1 = await repo.create_or_get(user, _mk_book("a", book_id=book))
    assert created1 is True
    second, created2 = await repo.create_or_get(user, _mk_book("b", book_id=book))
    assert created2 is False
    assert second.project_id == first.project_id  # same project, no dup
    # exactly one book project exists for the book
    assert len(await repo.list(user, book_id=book)) == 1


@pytest.mark.asyncio
async def test_create_or_get_general_always_inserts(pool):
    """Non-book (or book-typed-without-book_id) creates are NOT deduped — the
    general-project create UX is unchanged."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    a, ca = await repo.create_or_get(user, _mk("g1"))
    b, cb = await repo.create_or_get(user, _mk("g2"))
    assert ca is True and cb is True
    assert a.project_id != b.project_id


@pytest.mark.asyncio
async def test_create_or_get_book_concurrent_one_wins(pool):
    """Two concurrent book-project create_or_get for the same (user, book) →
    exactly one INSERT, both return the same project (advisory lock serialises)."""
    import asyncio

    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    r1, r2 = await asyncio.gather(
        repo.create_or_get(user, _mk_book("x", book_id=book)),
        repo.create_or_get(user, _mk_book("y", book_id=book)),
    )
    created_flags = [r1[1], r2[1]]
    assert created_flags.count(True) == 1 and created_flags.count(False) == 1
    assert r1[0].project_id == r2[0].project_id
    assert len(await repo.list(user, book_id=book)) == 1


@pytest.mark.asyncio
async def test_create_or_get_book_without_book_id_always_inserts(pool):
    """A book-typed project with NO book_id can't be deduped (nothing to key on)
    → always inserts."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    a, ca = await repo.create_or_get(user, ProjectCreate(name="nb1", project_type="book"))
    b, cb = await repo.create_or_get(user, ProjectCreate(name="nb2", project_type="book"))
    assert ca is True and cb is True
    assert a.project_id != b.project_id


def _mk_derivative(name: str, *, book_id: UUID) -> ProjectCreate:
    return ProjectCreate(
        name=name, project_type="book", book_id=book_id, force_new=True
    )


@pytest.mark.asyncio
async def test_force_new_book_projects_get_distinct_ids(pool):
    """C23 derivative fix: two derive-style creates for the SAME (user, book)
    with force_new=True yield DISTINCT project_ids (each derivative gets its OWN
    fresh partition — G2). They must NOT dedupe back to a single project."""
    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    a, ca = await repo.create_or_get(user, _mk_derivative("d1", book_id=book))
    b, cb = await repo.create_or_get(user, _mk_derivative("d2", book_id=book))
    assert ca is True and cb is True
    assert a.project_id != b.project_id
    assert a.is_derivative is True and b.is_derivative is True


@pytest.mark.asyncio
async def test_force_new_does_not_break_back_compat_dedup(pool):
    """A NORMAL book project create_or_get (force_new default False) still
    dedupes per (user, book) — back-compat unchanged."""
    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    first, c1 = await repo.create_or_get(user, _mk_book("a", book_id=book))
    second, c2 = await repo.create_or_get(user, _mk_book("b", book_id=book))
    assert c1 is True and c2 is False
    assert second.project_id == first.project_id
    assert first.is_derivative is False


@pytest.mark.asyncio
async def test_create_or_get_never_returns_a_derivative_for_source_book(pool):
    """A derivative project for a book must NEVER be handed back by the source
    book's create_or_get / get_by_book. First mint a derivative, THEN the source
    book's first create_or_get must INSERT a fresh source project (created=True),
    not return the derivative."""
    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    # A derivative exists for this book (e.g. an earlier derive ran first).
    deriv, _ = await repo.create_or_get(user, _mk_derivative("deriv", book_id=book))
    # The source book's get-or-create must NOT return the derivative.
    source, created = await repo.create_or_get(user, _mk_book("source", book_id=book))
    assert created is True
    assert source.project_id != deriv.project_id
    assert source.is_derivative is False
    # get_by_book (book-scoped raw-search resolution) must also skip derivatives.
    by_book = await repo.get_by_book(book)
    assert by_book is not None
    assert by_book.project_id == source.project_id
    assert by_book.is_derivative is False


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
async def test_update_embedding_model_and_dimension(pool):
    """D-EMB-MODEL-REF-01: embedding_model (a provider user_model UUID)
    and embedding_dimension are set together by the caller — the
    dimension is no longer auto-derived from a logical-name map.
    Clearing the model (None) still clears the dimension."""
    repo = ProjectsRepo(pool)
    user = uuid4()
    p = await repo.create(user, _mk("s"))
    assert p.embedding_model is None
    assert p.embedding_dimension is None

    # Set a model UUID + its dimension together.
    model_a = str(uuid4())
    out = await repo.update(
        user, p.project_id,
        ProjectUpdate(embedding_model=model_a, embedding_dimension=1024),
    )
    assert out is not None
    assert out.embedding_model == model_a
    assert out.embedding_dimension == 1024

    # Switch to another model + dimension.
    model_b = str(uuid4())
    out = await repo.update(
        user, p.project_id,
        ProjectUpdate(embedding_model=model_b, embedding_dimension=1536),
    )
    assert out is not None
    assert out.embedding_model == model_b
    assert out.embedding_dimension == 1536

    # Clear the model → dimension also cleared (the kept invariant).
    out = await repo.update(
        user, p.project_id, ProjectUpdate(embedding_model=None),
    )
    assert out is not None
    assert out.embedding_model is None
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
