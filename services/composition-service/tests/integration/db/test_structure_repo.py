"""23 A3 — StructureRepo round-trips against a real Postgres (throwaway test DB).

Gated on TEST_COMPOSITION_DB_URL (the fixture drops + rebuilds the composition
schema). Covers the keystone behaviours every Stage-2 sibling codes against:
saga→arc→sub-arc create with trigger-maintained depth; move() reparent that
recomputes the WHOLE subtree's depth; the DB depth/cycle/cross-book guard
surfacing as a clean StructureConflictError (a 4xx, never a 500); BA7 cascade
resolution (a sub-arc override shadows a saga track BY EFFECT); and the DERIVED
span / member_chapter_ids / open_promises rollups (BA6/BA15) over assigned
chapters.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.structure import StructureConflictError, StructureRepo
from app.db.repositories.works import WorksRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

# xdist_group("pg"): this file hits the shared dev/throwaway Postgres, so parallel
# workers must serialize onto one worker (CLAUDE.md Test Parallelization rule).
pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    pytest.mark.xdist_group("pg"),
]

# Dropped (CASCADE) on setup + teardown so run_migrations rebuilds a clean schema
# with every FK wired (structure_node ← outline_node/motif_application; arc_template
# ← structure_node). Order is irrelevant under CASCADE.
_TABLES = [
    "structure_node", "motif_application", "motif_link", "motif", "arc_template",
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "composition_daily_progress", "composition_progress_baseline",
    "style_profile", "voice_profile", "scene_grounding_pins", "reference_source",
    "decompose_commit", "outbox_events", "generation_correction", "generation_job",
    "narrative_thread", "canon_rule", "scene_link", "outline_node",
    "structure_template", "entity_override", "divergence_spec", "composition_work",
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


def _ids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()  # actor, project, book


async def _seed_work(pool, actor, project, book):
    """Seed the composition_work row outline_node INSERTs derive book_id from."""
    return await WorksRepo(pool).create(actor, project, book)


# ───────────────────────── create + depth ─────────────────────────

async def test_create_saga_arc_subarc_depth_ladder(pool):
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga", title="Ascension")
    arc = await repo.create_node(
        book, created_by=actor, kind="arc", title="Betrayal", parent_id=saga.id,
    )
    sub = await repo.create_node(
        book, created_by=actor, kind="arc", title="The Setup", parent_id=arc.id,
    )
    # depth is trigger-maintained 0..2 (saga→arc→sub-arc).
    assert (saga.depth, arc.depth, sub.depth) == (0, 1, 2)
    assert saga.parent_id is None and arc.parent_id == saga.id and sub.parent_id == arc.id
    # list_tree orders by depth then rank.
    tree = await repo.list_tree(book)
    assert [n.id for n in tree] == [saga.id, arc.id, sub.id]
    assert await repo.get_children(saga.id) == [n for n in tree if n.parent_id == saga.id]


async def test_create_fourth_level_rejected_4xx(pool):
    # A direct create that would land at depth 3 is rejected by the DB trigger as a
    # clean StructureConflictError (4xx), never a raw 500.
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga")
    arc = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id)
    sub = await repo.create_node(book, created_by=actor, kind="arc", parent_id=arc.id)
    with pytest.raises(StructureConflictError):
        await repo.create_node(book, created_by=actor, kind="arc", parent_id=sub.id)


async def test_saga_with_parent_rejected_4xx(pool):
    # structure_saga_is_root CHECK: a saga may never have a parent.
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga")
    with pytest.raises((StructureConflictError, asyncpg.exceptions.CheckViolationError)):
        await repo.create_node(book, created_by=actor, kind="saga", parent_id=saga.id)


# ───────────────────────── move / reparent ─────────────────────────

async def test_move_recomputes_whole_subtree_depth(pool):
    # saga → arc → sub; move arc to a root. arc: 1→0, sub: 2→1 (the subtree depth
    # is recomputed in the same tx, not left stale).
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga")
    arc = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id)
    sub = await repo.create_node(book, created_by=actor, kind="arc", parent_id=arc.id)

    moved = await repo.move(arc.id, new_parent_id=None)
    assert moved is not None and moved.parent_id is None and moved.depth == 0
    assert (await repo.get(sub.id)).depth == 1          # recomputed descendant
    assert (await repo.get(arc.id)).depth == 0


async def test_move_reorders_among_siblings(pool):
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga")
    a = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id, title="A")
    b = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id, title="B")
    c = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id, title="C")
    # place C right after A → order A, C, B
    await repo.move(c.id, new_parent_id=saga.id, after_id=a.id)
    order = [n.title for n in await repo.get_children(saga.id)]
    assert order == ["A", "C", "B"]


async def test_move_depth_three_via_descendant_rejected_4xx(pool):
    # saga → arcA → sub ; arcB under saga. Moving arcA under arcB puts arcA at
    # depth 2 (ok) but sub at depth 3 — caught during the subtree recompute as a
    # clean StructureConflictError (4xx), and the whole move rolls back.
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga")
    arc_a = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id)
    sub = await repo.create_node(book, created_by=actor, kind="arc", parent_id=arc_a.id)
    arc_b = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id)
    with pytest.raises(StructureConflictError):
        await repo.move(arc_a.id, new_parent_id=arc_b.id)
    # rolled back: arcA still under the saga, sub still depth 2
    assert (await repo.get(arc_a.id)).parent_id == saga.id
    assert (await repo.get(sub.id)).depth == 2


async def test_move_cycle_rejected_4xx(pool):
    # arcRoot (a root arc) → arcChild. Moving arcRoot under its own descendant is a
    # cycle — the trigger's ancestor walk rejects it (4xx).
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    root = await repo.create_node(book, created_by=actor, kind="arc", title="root")
    child = await repo.create_node(book, created_by=actor, kind="arc", parent_id=root.id)
    with pytest.raises(StructureConflictError):
        await repo.move(root.id, new_parent_id=child.id)
    assert (await repo.get(root.id)).parent_id is None   # unchanged


async def test_move_cross_book_reparent_rejected_4xx(pool):
    # A parent in another book is rejected by the guard (the H-5 scope-guard lesson).
    repo = StructureRepo(pool)
    actor, _, book_a = _ids()
    _, _, book_b = _ids()
    saga_a = await repo.create_node(book_a, created_by=actor, kind="saga")
    arc_a = await repo.create_node(book_a, created_by=actor, kind="arc", parent_id=saga_a.id)
    saga_b = await repo.create_node(book_b, created_by=actor, kind="saga")
    with pytest.raises(StructureConflictError):
        await repo.move(arc_a.id, new_parent_id=saga_b.id)
    assert (await repo.get(arc_a.id)).parent_id == saga_a.id


# ───────────────────────── update / OCC / archive ─────────────────────────

async def test_update_occ_and_version_mismatch(pool):
    from app.db.repositories import VersionMismatchError

    repo = StructureRepo(pool)
    actor, _, book = _ids()
    arc = await repo.create_node(book, created_by=actor, kind="arc", title="old")
    upd = await repo.update(arc.id, {"title": "new", "status": "drafting"}, expected_version=1)
    assert upd is not None and upd.title == "new" and upd.status == "drafting" and upd.version == 2
    # a stale expected_version raises VersionMismatchError carrying the current row
    with pytest.raises(VersionMismatchError):
        await repo.update(arc.id, {"title": "x"}, expected_version=1)
    # a missing node is a 404 (None), not an error
    assert await repo.update(uuid.uuid4(), {"title": "x"}, expected_version=1) is None


async def test_update_bad_status_enum_is_conflict(pool):
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    arc = await repo.create_node(book, created_by=actor, kind="arc")
    with pytest.raises(StructureConflictError):
        await repo.update(arc.id, {"status": "bogus"}, expected_version=None)


async def test_archive_restore_cascades_subtree(pool):
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga")
    arc = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id)
    sub = await repo.create_node(book, created_by=actor, kind="arc", parent_id=arc.id)

    await repo.archive(arc.id)
    assert (await repo.get(arc.id)).is_archived and (await repo.get(sub.id)).is_archived
    assert not (await repo.get(saga.id)).is_archived                 # ancestor untouched
    assert [n.id for n in await repo.list_tree(book)] == [saga.id]   # subtree hidden

    await repo.restore(sub.id)
    # restoring the leaf reconnects its archived ancestor chain
    assert not (await repo.get(sub.id)).is_archived
    assert not (await repo.get(arc.id)).is_archived


# ───────────────────────── resolution (BA7) ─────────────────────────

async def test_resolve_tracks_subarc_shadows_saga_by_effect(pool):
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(
        book, created_by=actor, kind="saga",
        tracks=[{"key": "main", "label": "Saga Main"},
                {"key": "romance", "label": "Saga Romance"}],
    )
    arc = await repo.create_node(
        book, created_by=actor, kind="arc", parent_id=saga.id,
        tracks=[{"key": "heist", "label": "Arc Heist"}],
    )
    sub = await repo.create_node(
        book, created_by=actor, kind="arc", parent_id=arc.id,
        tracks=[{"key": "romance", "label": "SubArc Romance Override"}],
    )
    merged = {t["key"]: t["label"] for t in await repo.resolve_tracks(sub.id)}
    # root→leaf, leaf wins: the sub-arc override shadows the saga's 'romance'.
    assert merged == {
        "main": "Saga Main",
        "romance": "SubArc Romance Override",
        "heist": "Arc Heist",
    }


async def test_resolve_roster_and_bindings_shadow(pool):
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    e_saga, e_sub = uuid.uuid4(), uuid.uuid4()
    saga = await repo.create_node(
        book, created_by=actor, kind="saga",
        roster=[{"key": "protagonist", "label": "Hero"}],
        roster_bindings={"protagonist": str(e_saga), "mentor": str(uuid.uuid4())},
    )
    sub = await repo.create_node(
        book, created_by=actor, kind="arc", parent_id=saga.id,
        roster=[{"key": "protagonist", "label": "Hero (arc voice)"}],
        roster_bindings={"protagonist": str(e_sub)},
    )
    roster = {r["key"]: r["label"] for r in await repo.resolve_roster(sub.id)}
    assert roster["protagonist"] == "Hero (arc voice)"          # leaf wins by key
    bindings = await repo.resolve_roster_bindings(sub.id)
    assert bindings["protagonist"] == str(e_sub)                # leaf wins by role_key
    assert "mentor" in bindings                                 # inherited from the saga


async def test_ancestor_chain_root_first(pool):
    repo = StructureRepo(pool)
    actor, _, book = _ids()
    saga = await repo.create_node(book, created_by=actor, kind="saga")
    arc = await repo.create_node(book, created_by=actor, kind="arc", parent_id=saga.id)
    sub = await repo.create_node(book, created_by=actor, kind="arc", parent_id=arc.id)
    assert [n.id for n in await repo.ancestor_chain(sub.id)] == [saga.id, arc.id, sub.id]


# ───────────────────────── derived: span / members / promises ─────────────────────────

async def _seed_chapters(pool, actor, project, book, arc_id, story_orders):
    """Create chapter-kind outline nodes with the given story_orders and assign
    them to `arc_id`. Returns the outline node ids in creation order."""
    outline = OutlineRepo(pool)
    struct = StructureRepo(pool)
    ids = []
    for so in story_orders:
        ch = await outline.create_node(
            project, created_by=actor, kind="chapter", chapter_id=uuid.uuid4(),
            title=f"Ch{so}", story_order=so, status="outline",
        )
        ids.append(ch.id)
    n = await struct.assign_chapters(book, arc_id, ids)
    assert n == len(ids)
    return ids


async def test_span_and_member_chapter_ids_over_assigned_chapters(pool):
    repo = StructureRepo(pool)
    actor, project, book = _ids()
    await _seed_work(pool, actor, project, book)
    arc = await repo.create_node(book, created_by=actor, kind="arc")
    ids = await _seed_chapters(pool, actor, project, book, arc.id, [0, 1, 2])

    span = await repo.span(arc.id)
    assert span == {
        "min_story_order": 0, "max_story_order": 2,
        "chapter_count": 3, "is_contiguous": True,
    }
    assert set(await repo.member_chapter_ids(arc.id)) == set(ids)


async def test_span_gap_is_not_contiguous_warn_only(pool):
    repo = StructureRepo(pool)
    actor, project, book = _ids()
    await _seed_work(pool, actor, project, book)
    arc = await repo.create_node(book, created_by=actor, kind="arc")
    await _seed_chapters(pool, actor, project, book, arc.id, [0, 1, 5])
    span = await repo.span(arc.id)
    assert span["chapter_count"] == 3 and span["is_contiguous"] is False


async def test_span_rolls_up_subarc_members(pool):
    # a sub-arc's chapters count toward its arc's span (subtree membership).
    repo = StructureRepo(pool)
    actor, project, book = _ids()
    await _seed_work(pool, actor, project, book)
    arc = await repo.create_node(book, created_by=actor, kind="arc")
    sub = await repo.create_node(book, created_by=actor, kind="arc", parent_id=arc.id)
    await _seed_chapters(pool, actor, project, book, arc.id, [0, 1])
    await _seed_chapters(pool, actor, project, book, sub.id, [2, 3])
    assert (await repo.span(arc.id))["chapter_count"] == 4        # arc sees the sub-arc's too
    assert (await repo.span(sub.id))["chapter_count"] == 2        # sub-arc sees only its own


async def test_open_promises_rollup(pool):
    repo = StructureRepo(pool)
    threads = NarrativeThreadRepo(pool)
    actor, project, book = _ids()
    await _seed_work(pool, actor, project, book)
    arc = await repo.create_node(book, created_by=actor, kind="arc")
    other = await repo.create_node(book, created_by=actor, kind="arc")
    member_ids = await _seed_chapters(pool, actor, project, book, arc.id, [0, 1])
    non_member = await _seed_chapters(pool, actor, project, book, other.id, [2])

    # an OPEN promise on a member chapter → rolled up
    t_open = await threads.open_thread(
        project, created_by=actor, kind="promise", summary="the vow",
        opened_at_node=member_ids[0], priority=90,
    )
    # a promise on a NON-member chapter → excluded
    await threads.open_thread(
        project, created_by=actor, kind="promise", summary="elsewhere",
        opened_at_node=non_member[0],
    )
    # a PAID promise on a member chapter → excluded (status resolved)
    t_paid = await threads.open_thread(
        project, created_by=actor, kind="promise", summary="settled",
        opened_at_node=member_ids[1],
    )
    await threads.update_status(project, t_paid.id, status="paid", payoff_node=member_ids[1])

    rolled = await repo.open_promises(arc.id, narrative_threads_repo=threads)
    assert [t.id for t in rolled] == [t_open.id]


# ───────────────────────── assign_chapters cross-book guard ─────────────────────────

async def test_assign_chapters_book_scoped_both_sides_by_effect(pool):
    """assign_chapters is book-scoped on BOTH sides in SQL: it updates only chapters
    with `o.book_id = $book` AND only when the target arc EXISTS in that same book
    (the EXISTS(structure_node WHERE id=$arc AND book_id=$book) guard). So a
    cross-book assign is a NO-OP — returns 0 and mutates nothing. Locks that guard by
    EFFECT against the real DB (a confirmed /review-impl coverage gap): a regression
    that dropped either book_id predicate would let one book's arc silently adopt
    another book's chapters (a tenancy defect)."""
    struct = StructureRepo(pool)
    outline = OutlineRepo(pool)
    actor, proj_b, book_b = _ids()
    _, proj_o, book_o = _ids()
    # Two independent books, each with its own Work so chapters can derive book_id.
    await _seed_work(pool, actor, proj_b, book_b)
    await _seed_work(pool, actor, proj_o, book_o)

    arc_b = await struct.create_node(book_b, created_by=actor, kind="arc", title="Arc B")
    arc_o = await struct.create_node(book_o, created_by=actor, kind="arc", title="Arc Other")

    ch_b = await outline.create_node(
        proj_b, created_by=actor, kind="chapter", chapter_id=uuid.uuid4(),
        title="Ch in B", story_order=0, status="outline",
    )
    ch_o = await outline.create_node(
        proj_o, created_by=actor, kind="chapter", chapter_id=uuid.uuid4(),
        title="Ch in Other", story_order=0, status="outline",
    )
    # Baseline: both chapters start unassigned (structure_node_id NULL).
    assert ch_b.structure_node_id is None and ch_o.structure_node_id is None
    assert ch_b.book_id == book_b and ch_o.book_id == book_o

    # 1) Foreign CHAPTER side — arc in B, chapter in the OTHER book → no-op. The
    #    `o.book_id = $book_b` predicate excludes the foreign chapter; it stays NULL.
    n = await struct.assign_chapters(book_b, arc_b.id, [ch_o.id])
    assert n == 0
    assert (await outline.get_node(ch_o.id)).structure_node_id is None   # untouched

    # 2) Foreign ARC side — arc in the OTHER book, chapter in B → no-op. The chapter
    #    matches book_b, but the EXISTS guard requires the arc to be in book_b too
    #    (it isn't), so the chapter in B is NOT adopted by a foreign arc.
    n = await struct.assign_chapters(book_b, arc_o.id, [ch_b.id])
    assert n == 0
    assert (await outline.get_node(ch_b.id)).structure_node_id is None   # untouched

    # 3) Happy path — arc + chapter both in B → exactly one row, bound to the arc.
    n = await struct.assign_chapters(book_b, arc_b.id, [ch_b.id])
    assert n == 1
    assert (await outline.get_node(ch_b.id)).structure_node_id == arc_b.id
