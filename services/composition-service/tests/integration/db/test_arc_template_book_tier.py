"""D-ARC-TEMPLATE-BOOK-TIER (34a) — the TENANCY proof for the book-shared arc-template tier
(mirrors motif model B). THIS is the critical-class test: a book-shared row is editable by an
EDIT-grantee who is NOT the owner, and INVISIBLE to a non-grantee. Real SQL, throwaway DB.

The repo does NOT gate — the ROUTE resolves the book grant and passes `book_id` only when the
caller is VIEW/EDIT-gated. These tests simulate that: passing `book_id` == "the route gated it";
omitting it == a non-grantee (or a caller with no book context)."""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import ArcTemplateCreateArgs, ArcTemplatePatchArgs
from app.db.repositories.arc_template_repo import ArcTemplateRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")
pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]
_TABLES = ["consumed_tokens", "motif_application", "motif_link", "import_source", "arc_template", "motif"]


@pytest.fixture
async def repo():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)

    async def _drop():
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    try:
        await _drop(); await run_migrations(p)
        yield ArcTemplateRepo(p), p
    finally:
        await _drop(); await p.close()


def _args(**kw) -> ArcTemplateCreateArgs:
    return ArcTemplateCreateArgs(**{"code": "revenge", "name": "Revenge Arc", **kw})


async def test_book_shared_visible_to_grantee_invisible_to_nongrantee(repo):
    r, _ = repo
    owner, grantee, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    arc = await r.create(owner, _args(), book_id=book, book_shared=True)
    assert arc.book_shared is True and arc.visibility == "private"

    # a NON-grantee (no book context) cannot see it — the tenancy assertion.
    assert await r.get_visible(grantee, arc.id) is None
    assert all(a.id != arc.id for a in await r.list_for_caller(grantee, scope="all"))

    # a grantee (the route VIEW-gated `book`) DOES see it — collaboration works.
    seen = await r.get_visible(grantee, arc.id, book_id=book)
    assert seen is not None and seen.id == arc.id
    assert any(a.id == arc.id for a in await r.list_for_caller(grantee, scope="all", book_id=book))


async def test_book_shared_editable_by_non_owner_grantee(repo):
    r, _ = repo
    owner, grantee, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    arc = await r.create(owner, _args(), book_id=book, book_shared=True)

    # a non-owner grantee (route EDIT-gated `book`) CAN edit the shared row.
    edited = await r.patch(grantee, arc.id, ArcTemplatePatchArgs(name="Co-edited"),
                           expected_version=None, book_id=book)
    assert edited is not None and edited.name == "Co-edited"

    # WITHOUT the gated book, the same non-owner is refused (owner-only path → None).
    refused = await r.patch(grantee, arc.id, ArcTemplatePatchArgs(name="Sneaky"), expected_version=None)
    assert refused is None


async def test_shape_check_rejects_shared_without_book(repo):
    r, _ = repo
    with pytest.raises(asyncpg.CheckViolationError):
        await r.create(uuid.uuid4(), _args(), book_id=None, book_shared=True)


async def test_two_books_hold_the_same_code_and_private_lib_coexists(repo):
    r, _ = repo
    owner, b1, b2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # per-book dedup: the SAME code in two different books is fine.
    await r.create(owner, _args(code="dup"), book_id=b1, book_shared=True)
    await r.create(owner, _args(code="dup"), book_id=b2, book_shared=True)
    # the _nobook amendment: a private-lib row + a book-shared clone of the same code coexist.
    await r.create(owner, _args(code="dup"))  # private lib (book_id NULL)
    async with r._pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM arc_template WHERE code='dup'")
    assert n == 3
