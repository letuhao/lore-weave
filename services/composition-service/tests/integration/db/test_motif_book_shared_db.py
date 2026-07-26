"""D-MOTIF-ADOPT-BOOK-COLLAB-TIER (model B) — the SHARED book tier, real Postgres.

Gated on TEST_COMPOSITION_DB_URL (a THROWAWAY DB — the fixture drops the motif tables
on setup AND teardown). The DB IS the tenancy boundary, so these are DB-level guards:

  - the book_shared column + the motif_book_shared_shape CHECK (a shared row must carry a
    book + an owner + stay private; a public/orphan shared row is rejected).
  - per-BOOK dedup of the shared tier (uq_motif_book_shared) — two grantees adopting the same
    source into the same book → ONE shared row; a model-A label + a global of the same code
    coexist without a false collision.
  - the read scoping: list_in_book / get_in_book surface own + system + this book's shared tier;
    get_visible STILL hides a foreign shared row (the fail-closed invariant).
  - the write path: patch_shared / archive_shared key on (book_shared, book_id), not owner.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import MotifCreateArgs, MotifPatchArgs
from app.db.repositories.motif_repo import MotifRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # MANDATORY (CLAUDE.md test-parallelization): this file DROPs/re-migrates tables on the
    # shared dev PG. Without the group, xdist schedules it on a DIFFERENT worker than the
    # other real-DB files and they drop each other's tables mid-run — the counts then lie.
    pytest.mark.xdist_group("pg"),
]

_MOTIF_TABLES = [
    "consumed_tokens", "motif_application", "motif_link",
    "import_source", "arc_template", "motif",
]


async def _drop(p: asyncpg.Pool) -> None:
    async with p.acquire() as c:
        for t in _MOTIF_TABLES:
            await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        await _drop(p)
        await run_migrations(p)
        yield p
    finally:
        await _drop(p)
        await p.close()


async def _system_source(pool, *, code="src", language="en") -> uuid.UUID:
    """A public source motif any user can adopt."""
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO motif (owner_user_id, code, language, visibility, source, name) "
            "VALUES (NULL,$1,$2,'public','authored',$3) RETURNING id",
            code, language, f"src-{code}",
        )


async def test_book_shared_shape_check(pool):
    """The CHECK rejects book_shared with NULL book / NULL owner / non-private visibility."""
    u, b = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        # shared with no book → rejected
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO motif (owner_user_id, book_id, book_shared, code, visibility, name) "
                "VALUES ($1,NULL,true,'x','private','X')", u)
        # shared with no owner → rejected
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO motif (owner_user_id, book_id, book_shared, code, visibility, name) "
                "VALUES (NULL,$1,true,'x','private','X')", b)
        # shared but public → rejected (the orthogonality guard)
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO motif (owner_user_id, book_id, book_shared, code, visibility, name) "
                "VALUES ($1,$2,true,'x','public','X')", u, b)
        # a well-formed shared row IS accepted
        await c.execute(
            "INSERT INTO motif (owner_user_id, book_id, book_shared, code, visibility, name) "
            "VALUES ($1,$2,true,'ok','private','OK')", u, b)


async def test_shared_tier_dedups_per_book(pool):
    """Two grantees adopting the same source into the same book → ONE shared row (idempotent);
    a model-A private label + a global of the same code coexist (independent dedup)."""
    repo = MotifRepo(pool)
    u1, u2, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    src = await _system_source(pool, code="betrayal")

    m1, c1 = await repo.adopt(u1, src, book_id=book, book_shared=True)
    assert c1 is True and m1.book_shared is True and m1.book_id == book
    # u2 (another grantee) adopts the SAME source into the SAME book → the existing shared row.
    m2, c2 = await repo.adopt(u2, src, book_id=book, book_shared=True)
    assert c2 is False and m2.id == m1.id
    # u1 also keeps a private GLOBAL adopt + a model-A per-book LABEL of the same source — all
    # three coexist (shared / global / label dedup independently).
    g, gc = await repo.adopt(u1, src)
    lbl, lc = await repo.adopt(u1, src, book_id=book)   # model-A label (book_shared False)
    assert gc is True and lc is True
    ids = {m1.id, g.id, lbl.id}
    assert len(ids) == 3


async def test_list_and_get_in_book_scope(pool):
    """list_in_book / get_in_book surface own + system + THIS book's shared tier; a foreign
    user's globals + another book's shared rows are excluded; get_visible hides a foreign shared
    row (fail-closed)."""
    repo = MotifRepo(pool)
    u1, u2, u3, book, other_book = (uuid.uuid4() for _ in range(5))
    src = await _system_source(pool, code="rivalry")
    other_src = await _system_source(pool, code="ascension")

    # u2 adopts src into book's SHARED tier; u1 is also a grantee.
    shared, _ = await repo.adopt(u2, src, book_id=book, book_shared=True)
    # u1's own private global.
    own = await repo.create(u1, MotifCreateArgs(code="mine", name="Mine"))
    # u3 adopts other_src into ANOTHER book's shared tier (must NOT leak into `book`).
    other_shared, _ = await repo.adopt(u3, other_src, book_id=other_book, book_shared=True)

    rows = await repo.list_in_book(u1, book)
    got = {m.id for m in rows}
    assert shared.id in got            # the book's shared tier (owned by u2)
    assert own.id in got               # u1's own global
    assert other_shared.id not in got  # another book's shared row is excluded

    # get_in_book: u1 (a grantee) sees the shared row; get_visible still hides it (no book ctx).
    assert (await repo.get_in_book(u1, shared.id, book)) is not None
    assert (await repo.get_visible(u1, shared.id)) is None
    # another book's shared row is invisible even via get_in_book(book).
    assert (await repo.get_in_book(u1, other_shared.id, book)) is None


async def test_patch_and_archive_shared_by_any_grantee(pool):
    """patch_shared / archive_shared key on (book_shared, book_id), not owner — so a grantee who
    is NOT the creator may edit + archive. A wrong book → no-op (None / unchanged)."""
    repo = MotifRepo(pool)
    creator, editor, book, wrong_book = (uuid.uuid4() for _ in range(4))
    src = await _system_source(pool, code="sacrifice")
    shared, _ = await repo.adopt(creator, src, book_id=book, book_shared=True)

    # a different grantee (editor) edits the shared row — owner is NOT the gate.
    edited = await repo.patch_shared(
        editor, shared.id, book, MotifPatchArgs(name="Edited by collaborator"),
        expected_version=shared.version,
    )
    assert edited is not None and edited.name == "Edited by collaborator"

    # a WRONG book id never matches (None — the H13 surface).
    miss = await repo.patch_shared(
        editor, shared.id, wrong_book, MotifPatchArgs(name="nope"),
        expected_version=edited.version,
    )
    assert miss is None

    # archive_shared by the editor flips status; a wrong book is a no-op.
    await repo.archive_shared(editor, shared.id, wrong_book)
    async with pool.acquire() as c:
        st = await c.fetchval("SELECT status FROM motif WHERE id=$1", shared.id)
    assert st == "active"
    await repo.archive_shared(editor, shared.id, book)
    async with pool.acquire() as c:
        st = await c.fetchval("SELECT status FROM motif WHERE id=$1", shared.id)
    assert st == "archived"


# ── D-MOTIF-LINK-SHARED-TIER: the same-book-shared link tier ───────────────────


async def test_link_guard_allows_same_book_shared_rejects_cross_tier(pool):
    """The rewritten motif_link_guard: a link between two SHARED motifs of the SAME book is
    allowed (owners may differ); a shared↔private, shared↔system, or cross-book shared link is
    rejected at the DB (CheckViolation)."""
    import asyncpg as _pg
    repo = MotifRepo(pool)
    u1, u2, book, other_book = (uuid.uuid4() for _ in range(4))
    s1 = await _system_source(pool, code="a")
    s2 = await _system_source(pool, code="b")
    s3 = await _system_source(pool, code="c")
    s4 = await _system_source(pool, code="d")

    # two shared rows in `book` owned by DIFFERENT grantees
    shared_a, _ = await repo.adopt(u1, s1, book_id=book, book_shared=True)
    shared_b, _ = await repo.adopt(u2, s2, book_id=book, book_shared=True)
    # a private row (u1) and another book's shared row
    priv = await repo.create(u1, MotifCreateArgs(code="priv", name="Priv"))
    other_shared, _ = await repo.adopt(u1, s3, book_id=other_book, book_shared=True)

    async def _link(frm, to):
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO motif_link (from_motif_id, to_motif_id, kind) VALUES ($1,$2,'variant_of')",
                frm, to)

    # same-book shared, different owners → ALLOWED (the whole point of model B link sharing)
    await _link(shared_a.id, shared_b.id)
    # shared ↔ private (even same owner u1) → rejected (would leak a private motif as a neighbor)
    with pytest.raises(_pg.CheckViolationError):
        await _link(shared_a.id, priv.id)
    # cross-book shared → rejected
    with pytest.raises(_pg.CheckViolationError):
        await _link(shared_a.id, other_shared.id)
    # shared ↔ system → rejected
    with pytest.raises(_pg.CheckViolationError):
        await _link(shared_a.id, s4)


async def test_create_list_delete_link_shared_tier(pool):
    """The repo link methods with book_id: create between two shared rows of the book, list them
    as a grantee, delete one. A non-shared / wrong-book endpoint is refused."""
    repo = MotifRepo(pool)
    u1, u2, u3, book = (uuid.uuid4() for _ in range(4))
    s1 = await _system_source(pool, code="rise")
    s2 = await _system_source(pool, code="fall")
    a, _ = await repo.adopt(u1, s1, book_id=book, book_shared=True)
    b, _ = await repo.adopt(u2, s2, book_id=book, book_shared=True)

    # create_link(book_id) between the two shared rows (different owners) — allowed.
    link = await repo.create_link(u1, a.id, b.id, "precedes", book_id=book)
    assert link.from_motif_id == a.id and link.to_motif_id == b.id

    # a private endpoint is refused (LookupError), even for the creator.
    priv = await repo.create(u1, MotifCreateArgs(code="p", name="P"))
    with pytest.raises(LookupError):
        await repo.create_link(u1, a.id, priv.id, "variant_of", book_id=book)

    # u3 (a third grantee who created neither) can list the shared graph in the book context.
    links = await repo.list_links(u3, a.id, book_id=book, direction="out")
    assert any(l["neighbor"]["id"] == str(b.id) for l in links)
    # the non-book path hides the shared anchor entirely (fail-closed).
    assert await repo.list_links(u3, a.id, direction="out") == []

    # delete_link(book_id) removes the shared edge (any grantee, EDIT-gated at the tool).
    assert await repo.delete_link(u3, link.id, book_id=book) is True
    assert await repo.delete_link(u3, link.id, book_id=book) is False  # already gone
