"""M1 (audit) — the P3.2 read-side gate: composition's structure reads MUST exclude a book whose
`book_lifecycle` the BookLifecycleConsumer set non-active. This is the regression guard the audit found
missing — without it, a future edit dropping the `book_lifecycle = 'active'` predicate from `list_tree` or
`resolve_by_book` would silently render a trashed book's structure again, and only a live e2e would notice.
Real SQL, throwaway DB."""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.structure import StructureRepo
from app.db.repositories.works import WorksRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "plan_bootstrap_proposal", "plan_artifact", "plan_run", "outbox_events",
    "generation_correction", "generation_job", "narrative_thread", "canon_rule", "scene_link",
    "outline_node", "structure_node", "structure_template", "entity_override", "divergence_spec",
    "composition_work",
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


@pytest.mark.asyncio
async def test_list_tree_excludes_a_non_active_book_lifecycle(pool):
    """A part of an ACTIVE book is listed; once the book is trashed (book_lifecycle flipped by the
    consumer) the SAME part must vanish from list_tree — the manuscript-rail read gate."""
    book = uuid.uuid4()
    async with pool.acquire() as c:
        part = await c.fetchval(
            "INSERT INTO structure_node (book_id, kind, rank, title, book_lifecycle) "
            "VALUES ($1,'part','a','P1','active') RETURNING id", book)
    repo = StructureRepo(pool)

    nodes = await repo.list_tree(book, kinds=("part",))
    assert [n.id for n in nodes] == [part], "an active part must be listed"

    async with pool.acquire() as c:
        await c.execute("UPDATE structure_node SET book_lifecycle='trashed' WHERE id=$1", part)
    nodes = await repo.list_tree(book, kinds=("part",))
    assert nodes == [], "a trashed book's part MUST be excluded (P3.2 list_tree gate)"


@pytest.mark.asyncio
async def test_resolve_by_book_excludes_a_non_active_book_lifecycle(pool):
    """An active Work resolves; once its book is trashed the Work must NOT resolve — the plan-hub
    chokepoint gate that covers the deep project-scoped reads."""
    book, user = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (created_by, book_id, project_id, status, book_lifecycle) "
            "VALUES ($1,$2,$3,'active','active')", user, book, uuid.uuid4())
    repo = WorksRepo(pool)

    works = await repo.resolve_by_book(book)
    assert len(works) == 1, "an active Work must resolve"

    async with pool.acquire() as c:
        await c.execute("UPDATE composition_work SET book_lifecycle='trashed' WHERE book_id=$1", book)
    works = await repo.resolve_by_book(book)
    assert works == [], "a trashed book's Work MUST NOT resolve (P3.2 resolve_by_book gate)"


@pytest.mark.asyncio
async def test_consumer_apply_stamps_book_lifecycle_on_BOTH_anchors(pool):
    """The BookLifecycleConsumer._apply must actually STAMP the column on structure_node AND
    composition_work — the SQL a mock-based unit test cannot prove ("a mock encodes your assumption; it
    cannot contradict it"). Trash flips both; restore flips both back (symmetric)."""
    from unittest.mock import AsyncMock

    from app.events.book_lifecycle_consumer import BookLifecycleConsumer

    book, user = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO structure_node (book_id, kind, rank, book_lifecycle) VALUES ($1,'part','a','active')", book)
        await c.execute(
            "INSERT INTO composition_work (created_by, book_id, status, book_lifecycle) "
            "VALUES ($1,$2,'active','active')", user, book)

    consumer = BookLifecycleConsumer("redis://x", pool, book_client=AsyncMock())

    async def _both():
        async with pool.acquire() as c:
            sn = await c.fetchval("SELECT book_lifecycle FROM structure_node WHERE book_id=$1", book)
            cw = await c.fetchval("SELECT book_lifecycle FROM composition_work WHERE book_id=$1", book)
        return sn, cw

    await consumer._apply(book, "trashed")
    assert await _both() == ("trashed", "trashed"), "trash must stamp BOTH anchors"

    await consumer._apply(book, "active")
    assert await _both() == ("active", "active"), "restore must flip BOTH anchors back (symmetric)"
