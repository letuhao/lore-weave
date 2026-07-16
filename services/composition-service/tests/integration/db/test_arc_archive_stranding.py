"""D-ARC-ARCHIVE-CHAPTER-STRANDING + BE-A3 (spec 32a §B) — archiving an arc RETURNS its
member chapters to the unplanned pool (not stranded), restore RE-ATTACHES exactly those
(unless re-homed meanwhile), and assign_chapters(None) unassigns. Real SQL, throwaway DB."""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.structure import StructureRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "outbox_events", "generation_correction", "generation_job", "narrative_thread",
    "canon_rule", "scene_link", "outline_node", "structure_node", "structure_template",
    "entity_override", "divergence_spec", "composition_work",
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


async def _chapter(pool, book, user, project, order) -> uuid.UUID:
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, story_order) "
            "VALUES ($1,$2,$3,'chapter',$4,$5) RETURNING id",
            user, project, book, f"m{order:03d}", order * 1000,
        )


async def _structure_of(pool, chapter_id):
    async with pool.acquire() as c:
        return await c.fetchrow(
            "SELECT structure_node_id, archived_from_structure_node_id FROM outline_node WHERE id=$1",
            chapter_id,
        )


async def _setup_arc_with_two_chapters(pool):
    book, user, project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo = StructureRepo(pool)
    arc = await repo.create_node(book, created_by=user, kind="arc", title="Arc")
    ch1 = await _chapter(pool, book, user, project, 1)
    ch2 = await _chapter(pool, book, user, project, 2)
    assigned = await repo.assign_chapters(book, arc.id, [ch1, ch2])
    assert assigned == 2
    return repo, book, arc, ch1, ch2


async def test_archive_returns_chapters_to_pool_and_restore_reattaches(pool):
    repo, book, arc, ch1, ch2 = await _setup_arc_with_two_chapters(pool)

    await repo.archive(arc.id)
    # both chapters are back in the pool (structure_node_id NULL) — NOT stranded — and remember
    # which arc they came from.
    for ch in (ch1, ch2):
        row = await _structure_of(pool, ch)
        assert row["structure_node_id"] is None
        assert row["archived_from_structure_node_id"] == arc.id

    await repo.restore(arc.id)
    for ch in (ch1, ch2):
        row = await _structure_of(pool, ch)
        assert row["structure_node_id"] == arc.id
        assert row["archived_from_structure_node_id"] is None


async def test_restore_does_not_clobber_a_chapter_rehomed_while_archived(pool):
    repo, book, arc, ch1, ch2 = await _setup_arc_with_two_chapters(pool)
    other = await repo.create_node(book, created_by=uuid.uuid4(), kind="arc", title="Other")

    await repo.archive(arc.id)
    # while archived, the user re-homes ch1 to another arc (BE-A3 assign clears archived_from).
    await repo.assign_chapters(book, other.id, [ch1])

    await repo.restore(arc.id)
    # ch1 keeps its new home; only ch2 (still unassigned) is reattached.
    assert (await _structure_of(pool, ch1))["structure_node_id"] == other.id
    assert (await _structure_of(pool, ch2))["structure_node_id"] == arc.id


async def test_assign_chapters_none_unassigns_and_clears_recovery(pool):
    repo, book, arc, ch1, ch2 = await _setup_arc_with_two_chapters(pool)

    n = await repo.assign_chapters(book, None, [ch1])
    assert n == 1
    row = await _structure_of(pool, ch1)
    assert row["structure_node_id"] is None
    assert row["archived_from_structure_node_id"] is None
    # ch2 untouched
    assert (await _structure_of(pool, ch2))["structure_node_id"] == arc.id


async def test_span_keeps_its_raw_strided_keys_for_the_packer(pool):
    # BE-A1 GUARD: span() is the PACKER's input (lenses.py) — RAW strided story_order, keyed
    # min_story_order/max_story_order. The two DETAIL doors were switched to derived_blocks
    # (dense-ranked ordinals), leaving span() untouched. This pins span()'s raw contract so a
    # future "just dense-rank span() too" cleanup REDS here instead of silently corrupting
    # every generation prompt.
    repo, book, arc, ch1, ch2 = await _setup_arc_with_two_chapters(pool)
    span = await repo.span(arc.id)
    assert set(span) >= {"min_story_order", "max_story_order", "chapter_count", "is_contiguous"}
    # chapters were seeded at story_order 1000 and 2000 (strided) — span reports the RAW axis.
    assert span["min_story_order"] == 1000
    assert span["max_story_order"] == 2000


async def test_archive_saga_returns_all_sub_arc_members(pool):
    book, user, project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo = StructureRepo(pool)
    saga = await repo.create_node(book, created_by=user, kind="saga", title="Saga")
    sub = await repo.create_node(book, created_by=user, kind="arc", title="Sub", parent_id=saga.id)
    ch = await _chapter(pool, book, user, project, 1)
    await repo.assign_chapters(book, sub.id, [ch])

    await repo.archive(saga.id)  # cascades to sub
    row = await _structure_of(pool, ch)
    assert row["structure_node_id"] is None
    assert row["archived_from_structure_node_id"] == sub.id
