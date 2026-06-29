"""M2 — repository round-trips against a real Postgres (throwaway test DB).

Gated on TEST_COMPOSITION_DB_URL (the fixture drops every composition table on
setup + teardown). Covers: works CRUD + resolve found/none/candidates + If-Match
412; outline auto-rank + recursive soft-archive; scene_link create/list/delete +
cross-user isolation; canon_rule active-listing + archive; generation_job
idempotency replay + COALESCE status update; txn-local outbox emit/rollback.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import asyncpg
import pytest

from app.db.migrate import C23_DOWN_SQL, run_migrations
from app.db.models import DivergenceSpec, EntityOverride
from app.db.repositories import ReferenceViolationError, VersionMismatchError
from app.db.repositories import outbox
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.daily_progress import DailyProgressRepo
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo
from app.db.repositories.generation_corrections import GenerationCorrectionsRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.works import WorksRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
)

_TABLES = [
    "composition_daily_progress",
    "composition_progress_baseline",
    "style_profile",
    "voice_profile",
    "scene_grounding_pins",
    "outbox_events", "generation_correction", "generation_job", "narrative_thread",
    "canon_rule", "scene_link", "outline_node", "structure_template",
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


def _ids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()  # user, project, book


# ───────────────────────── works ─────────────────────────

async def test_works_create_get_roundtrip(pool):
    repo = WorksRepo(pool)
    user, project, book = _ids()
    w = await repo.create(user, project, book, settings={"voice": "wry"})
    assert w.project_id == project and w.user_id == user and w.book_id == book
    assert w.settings == {"voice": "wry"} and w.version == 1
    got = await repo.get(user, project)
    assert got is not None and got.settings == {"voice": "wry"}
    # cross-user isolation
    assert await repo.get(uuid.uuid4(), project) is None


async def test_works_create_pending_null_project_and_backfill(pool):
    # C16 (WG-3): a lazy greenfield Work persists with a NULL project_id + the
    # backfill marker, is addressable by its surrogate id, and a later backfill
    # stamps the real project + clears the marker. Exercises the re-keyed schema
    # (surrogate id PK, nullable project_id, partial-unique pending index) on real PG.
    repo = WorksRepo(pool)
    user, _, book = _ids()
    pend = await repo.create_pending(user, book, settings={"voice": "dry"})
    assert pend.project_id is None
    assert pend.pending_project_backfill is True
    assert pend.id is not None and pend.settings == {"voice": "dry"}
    # findable via the backfill-seam read
    found = await repo.get_pending_for_book(user, book)
    assert found is not None and found.id == pend.id
    # cross-user isolation
    assert await repo.get_pending_for_book(uuid.uuid4(), book) is None
    # at most one pending per (user,book) — the partial-unique index rejects a 2nd
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await repo.create_pending(user, book)
    # backfill: stamp the project, clear the marker (idempotent — only still-pending)
    new_pid = uuid.uuid4()
    bf = await repo.backfill_project(user, pend.id, new_pid)
    assert bf is not None and bf.project_id == new_pid
    assert bf.pending_project_backfill is False
    assert await repo.get_pending_for_book(user, book) is None  # no longer pending
    # second backfill no-ops (row no longer pending)
    assert await repo.backfill_project(user, pend.id, uuid.uuid4()) is None
    # the backfilled row is now a normal project-keyed Work
    got = await repo.get(user, new_pid)
    assert got is not None and got.id == pend.id


async def test_works_resolve_excludes_pending_until_backfilled(pool):
    # C16: a lazy null-project Work must NOT resolve as a finished `found` marked
    # Work — else a retry (knowledge recovered) returns the placeholder and never
    # backfills. resolve_by_book excludes pending rows; after backfill it appears.
    repo = WorksRepo(pool)
    user, _, book = _ids()
    pend = await repo.create_pending(user, book)
    assert await repo.resolve_by_book(user, book) == []  # excluded while pending
    new_pid = uuid.uuid4()
    await repo.backfill_project(user, pend.id, new_pid)
    marked = await repo.resolve_by_book(user, book)
    assert len(marked) == 1 and marked[0].project_id == new_pid  # now a real marked Work


async def test_works_backed_and_null_coexist_unique_only_on_backed(pool):
    # The 1:1 work⇄project invariant is enforced ONLY for backed rows (partial-unique
    # WHERE project_id IS NOT NULL); a null-project Work is exempt and coexists.
    repo = WorksRepo(pool)
    user, project, book = _ids()
    await repo.create(user, project, book)  # backed
    other_book = uuid.uuid4()
    pend = await repo.create_pending(user, other_book)  # null-project, different book
    assert pend.project_id is None
    # a duplicate BACKED project still violates the partial-unique index
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await repo.create(user, project, uuid.uuid4())


async def test_works_resolve_found_none_candidates(pool):
    repo = WorksRepo(pool)
    user, _, book = _ids()
    # none
    assert await repo.resolve_by_book(user, book) == []
    # found (1)
    p1 = uuid.uuid4()
    await repo.create(user, p1, book)
    res = await repo.resolve_by_book(user, book)
    assert len(res) == 1 and res[0].project_id == p1
    # candidates (2)
    p2 = uuid.uuid4()
    await repo.create(user, p2, book)
    assert len(await repo.resolve_by_book(user, book)) == 2
    # archived work drops out of resolve
    await repo.update(user, p2, {"status": "archived"})
    assert len(await repo.resolve_by_book(user, book)) == 1


async def test_works_ifmatch_bump_and_412(pool):
    repo = WorksRepo(pool)
    user, project, book = _ids()
    await repo.create(user, project, book)
    updated = await repo.update(user, project, {"settings": {"a": 1}}, expected_version=1)
    assert updated is not None and updated.version == 2 and updated.settings == {"a": 1}
    # stale version → 412 carrying current row
    with pytest.raises(VersionMismatchError) as ei:
        await repo.update(user, project, {"settings": {"a": 2}}, expected_version=1)
    assert ei.value.current.version == 2
    # missing row with expected_version → None (404), not 412
    assert await repo.update(user, uuid.uuid4(), {"settings": {}}, expected_version=1) is None


async def test_works_update_noop_preserves_version(pool):
    repo = WorksRepo(pool)
    user, project, book = _ids()
    await repo.create(user, project, book)
    # explicit None on a NOT-NULL field is skipped → empty effective patch
    same = await repo.update(user, project, {"status": None})
    assert same is not None and same.version == 1


# ─────────────────────── C23 dị bản (derivative) ───────────────────────

async def test_c23_derivative_guard_rejects_null_project(pool):
    """The chk_derivative_project_required CHECK rejects a DERIVATIVE (source_work_id
    set) with a null project_id — the cross-project grounding-leak guard (G2)."""
    repo = WorksRepo(pool)
    user, _, book = _ids()
    src = await repo.create(user, uuid.uuid4(), book)  # a backed source Work
    async with pool.acquire() as c:
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await c.execute(
                "INSERT INTO composition_work (project_id, user_id, book_id, source_work_id) "
                "VALUES (NULL, $1, $2, $3)",
                user, book, src.id,
            )


async def test_c23_greenfield_null_still_allowed_after_migration(pool):
    """C16 greenfield null-path must NOT regress: a NON-derivative (source_work_id
    NULL) MAY still persist with a null project_id (the conditional guard exempts it)."""
    repo = WorksRepo(pool)
    user, _, book = _ids()
    pend = await repo.create_pending(user, book)  # null project, no source_work_id
    assert pend.project_id is None and pend.source_work_id is None
    assert pend.pending_project_backfill is True


async def test_c23_create_derivative_links_source_and_branch_point(pool):
    """create_derivative inserts a derivative with source_work_id + branch_point +
    a NOT-NULL project_id (its own, distinct from the source's)."""
    works = WorksRepo(pool)
    user, _, book = _ids()
    src = await works.create(user, uuid.uuid4(), book)
    deriv_pid = uuid.uuid4()
    deriv = await works.create_derivative(
        user, deriv_pid, book, src.id, branch_point=12, settings={"tone": "darker"}
    )
    assert deriv.source_work_id == src.id
    assert deriv.branch_point == 12
    assert deriv.project_id == deriv_pid and deriv.project_id != src.project_id
    assert deriv.settings == {"tone": "darker"}


async def test_c25_get_by_id_resolves_source_work_for_base_project(pool):
    """C25 — the packer resolves a derivative's BASE knowledge project from its
    `source_work_id` (the source's surrogate `id`) via get_by_id, NOT by reusing
    source_work_id as a project_id. Proves get_by_id returns the source row keyed by
    `id` and exposes its `project_id` (which may differ from `id`)."""
    works = WorksRepo(pool)
    user, _, book = _ids()
    src = await works.create(user, uuid.uuid4(), book)
    # A derivative links to the source by id; the packer looks the source up by id.
    deriv = await works.create_derivative(user, uuid.uuid4(), book, src.id, branch_point=2)
    fetched = await works.get_by_id(user, deriv.source_work_id)
    assert fetched is not None
    assert fetched.id == src.id
    assert fetched.project_id == src.project_id  # the BASE knowledge project
    # cross-user isolation: another user can't read it by id.
    assert await works.get_by_id(uuid.uuid4(), src.id) is None


async def test_c23_divergence_spec_and_override_roundtrip(pool):
    """divergence_spec (canon_rule[] + pov_anchor) + entity_override (JSONB) persist
    and read back; the work_id FK + per-(work,target) unique hold."""
    works, drepo = WorksRepo(pool), DerivativesRepo(pool)
    user, _, book = _ids()
    src = await works.create(user, uuid.uuid4(), book)
    deriv = await works.create_derivative(user, uuid.uuid4(), book, src.id, branch_point=3)
    pov = uuid.uuid4()
    spec = await drepo.create_spec(DivergenceSpec(
        user_id=user, project_id=deriv.project_id, work_id=deriv.id,
        taxonomy="pov_shift", pov_anchor=pov, canon_rule=["The villain wins", "No magic"],
    ))
    assert spec.taxonomy == "pov_shift" and spec.pov_anchor == pov
    assert spec.canon_rule == ["The villain wins", "No magic"]
    got_spec = await drepo.get_spec_for_work(user, deriv.id)
    assert got_spec is not None and got_spec.id == spec.id

    target = uuid.uuid4()
    ov = await drepo.create_override(EntityOverride(
        user_id=user, project_id=deriv.project_id, work_id=deriv.id,
        target_entity_id=target, overridden_fields={"role": "antagonist", "alive": False},
    ))
    assert ov.overridden_fields == {"role": "antagonist", "alive": False}
    overrides = await drepo.list_overrides_for_work(user, deriv.id)
    assert len(overrides) == 1 and overrides[0].target_entity_id == target
    # cross-user isolation
    assert await drepo.get_spec_for_work(uuid.uuid4(), deriv.id) is None
    assert await drepo.list_overrides_for_work(uuid.uuid4(), deriv.id) == []
    # per-(work,target) unique rejects a duplicate override
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await drepo.create_override(EntityOverride(
            user_id=user, project_id=deriv.project_id, work_id=deriv.id,
            target_entity_id=target, overridden_fields={"x": 1},
        ))


async def test_c23_migration_roundtrip_up_down_up_clean(pool):
    """Migration round-trip: the C23 substrate (2 columns + 2 tables + the guard) is
    present after up, GONE after the down SQL, and RESTORED clean on re-up with NO
    residue. The non-C23 schema (composition_work itself, the C16 re-key) survives."""
    async def _present(c) -> dict:
        return {
            "source_col": await c.fetchval(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name='composition_work' AND column_name='source_work_id'"
            ),
            "branch_col": await c.fetchval(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name='composition_work' AND column_name='branch_point'"
            ),
            "spec_tbl": await c.fetchval("SELECT to_regclass('divergence_spec') IS NOT NULL"),
            "override_tbl": await c.fetchval("SELECT to_regclass('entity_override') IS NOT NULL"),
            "guard": await c.fetchval(
                "SELECT count(*) FROM pg_constraint WHERE conname='chk_derivative_project_required'"
            ),
            "source_idx": await c.fetchval(
                "SELECT count(*) FROM pg_indexes WHERE indexname='idx_composition_work_source'"
            ),
        }

    # up already ran in the fixture
    async with pool.acquire() as c:
        after_up = await _present(c)
        assert after_up == {"source_col": 1, "branch_col": 1, "spec_tbl": True,
                            "override_tbl": True, "guard": 1, "source_idx": 1}
        # composition_work itself survives (this is a partial down, not a full drop)
        await c.execute(C23_DOWN_SQL)
        after_down = await _present(c)
        assert after_down == {"source_col": 0, "branch_col": 0, "spec_tbl": False,
                             "override_tbl": False, "guard": 0, "source_idx": 0}
        assert await c.fetchval("SELECT to_regclass('composition_work') IS NOT NULL")

    # re-up restores exactly, idempotently (twice)
    await run_migrations(pool)
    await run_migrations(pool)
    async with pool.acquire() as c:
        after_reup = await _present(c)
        assert after_reup == after_up  # no residue, full restoration


# ───────────────────────── outline ─────────────────────────

async def test_outline_autorank_appends_in_order(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    a = await repo.create_node(user, project, kind="arc", title="A")
    b = await repo.create_node(user, project, kind="arc", title="B")
    c = await repo.create_node(user, project, kind="arc", title="C")
    assert a.rank < b.rank < c.rank
    tree = await repo.list_tree(user, project)
    assert [n.title for n in tree] == ["A", "B", "C"]


async def test_outline_ifmatch_and_present_entities(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    node = await repo.create_node(
        user, project, kind="chapter", chapter_id=chapter,
        present_entity_ids=[uuid.uuid4()],
    )
    e2 = uuid.uuid4()
    upd = await repo.update_node(
        user, node.id, {"title": "T", "present_entity_ids": [e2]}, expected_version=1,
    )
    assert upd is not None and upd.version == 2 and upd.title == "T"
    assert upd.present_entity_ids == [e2]
    with pytest.raises(VersionMismatchError):
        await repo.update_node(user, node.id, {"title": "X"}, expected_version=1)


async def test_outline_archive_recurses_subtree(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await repo.create_node(user, project, kind="arc", title="arc")
    chap = await repo.create_node(
        user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter,
    )
    scene = await repo.create_node(
        user, project, kind="scene", parent_id=chap.id, chapter_id=chapter,
    )
    # a sibling arc (NOT under the archived one) must survive
    other = await repo.create_node(user, project, kind="arc", title="other")

    archived = await repo.archive_node(user, arc.id)
    assert archived is not None and archived.is_archived

    visible = {n.id for n in await repo.list_tree(user, project)}
    assert arc.id not in visible
    assert chap.id not in visible  # descendant archived too
    assert scene.id not in visible
    assert other.id in visible
    # archiving again → already archived → None
    assert await repo.archive_node(user, arc.id) is None


async def test_outline_restore_recurses_subtree(pool):
    """T1.1b restore = inverse of archive: un-archives the node + its archived
    descendants (the whole cascade comes back)."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await repo.create_node(user, project, kind="arc", title="arc")
    chap = await repo.create_node(
        user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter,
    )
    scene = await repo.create_node(
        user, project, kind="scene", parent_id=chap.id, chapter_id=chapter,
    )
    await repo.archive_node(user, arc.id)  # archives arc+chap+scene

    restored = await repo.restore_node(user, arc.id)
    assert restored is not None and restored.is_archived is False
    visible = {n.id for n in await repo.list_tree(user, project)}
    assert {arc.id, chap.id, scene.id} <= visible  # whole subtree back
    # restoring again → nothing archived → None
    assert await repo.restore_node(user, arc.id) is None


async def test_outline_reorder_within_siblings_renumbers_story_order(pool):
    """T1.1c: reordering a scene after a later sibling rewrites its rank AND
    dense-renumbers the chapter's scene story_order to match (reading order)."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await repo.create_node(user, project, kind="arc", title="arc")
    chap = await repo.create_node(user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    s1 = await repo.create_node(user, project, kind="scene", parent_id=chap.id, chapter_id=chapter, title="s1")
    s2 = await repo.create_node(user, project, kind="scene", parent_id=chap.id, chapter_id=chapter, title="s2")
    s3 = await repo.create_node(user, project, kind="scene", parent_id=chap.id, chapter_id=chapter, title="s3")

    # move s1 to AFTER s3 → new order s2, s3, s1
    moved = await repo.reorder_node(user, s1.id, new_parent_id=chap.id, after_id=s3.id)
    assert moved is not None
    scenes = await repo.scenes_for_chapter(user, project, chapter)  # ORDER BY story_order, rank
    assert [s.title for s in scenes] == ["s2", "s3", "s1"]
    assert [s.story_order for s in scenes] == [0, 1, 2]  # dense, matches rank order


async def test_outline_reorder_reparents_scene_across_chapters(pool):
    """A scene dragged to another chapter inherits the new chapter's chapter_id
    and is renumbered into the destination's reading order; the source chapter's
    remaining scenes re-densify."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chA, chB = uuid.uuid4(), uuid.uuid4()
    arc = await repo.create_node(user, project, kind="arc", title="arc")
    cA = await repo.create_node(user, project, kind="chapter", parent_id=arc.id, chapter_id=chA)
    cB = await repo.create_node(user, project, kind="chapter", parent_id=arc.id, chapter_id=chB)
    a1 = await repo.create_node(user, project, kind="scene", parent_id=cA.id, chapter_id=chA, title="a1")
    a2 = await repo.create_node(user, project, kind="scene", parent_id=cA.id, chapter_id=chA, title="a2")
    b1 = await repo.create_node(user, project, kind="scene", parent_id=cB.id, chapter_id=chB, title="b1")

    moved = await repo.reorder_node(user, a1.id, new_parent_id=cB.id, after_id=b1.id)
    assert moved is not None
    assert moved.parent_id == cB.id and moved.chapter_id == chB  # inherited new chapter
    dest = await repo.scenes_for_chapter(user, project, chB)
    assert [s.title for s in dest] == ["b1", "a1"] and [s.story_order for s in dest] == [0, 1]
    src = await repo.scenes_for_chapter(user, project, chA)
    assert [s.title for s in src] == ["a2"] and [s.story_order for s in src] == [0]  # re-densified


async def test_outline_beat_role_allowed_on_scene_and_chapter_not_arc(pool):
    """T1.2 Beat Sheet migration: beat_role may live on a scene OR a chapter, but
    an arc (or beat) still violates outline_beatrole_kind."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await repo.create_node(user, project, kind="arc", title="arc")
    chap = await repo.create_node(user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    scene = await repo.create_node(user, project, kind="scene", parent_id=chap.id, chapter_id=chapter)

    s = await repo.update_node(user, scene.id, {"beat_role": "catalyst"})
    assert s is not None and s.beat_role == "catalyst"
    c = await repo.update_node(user, chap.id, {"beat_role": "opening_image"})  # NEW: chapter allowed
    assert c is not None and c.beat_role == "opening_image"
    # clearing works (nullable)
    cleared = await repo.update_node(user, chap.id, {"beat_role": None})
    assert cleared is not None and cleared.beat_role is None
    # an arc still cannot carry a beat_role
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await repo.update_node(user, arc.id, {"beat_role": "finale"})


async def test_outline_reorder_rejects_cycle(pool):
    """Reparenting a node under its own descendant is a 400 (ReferenceViolationError)
    — the same guard update_node uses, applied before any write."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await repo.create_node(user, project, kind="arc", title="arc")
    chap = await repo.create_node(user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    with pytest.raises(ReferenceViolationError):
        await repo.reorder_node(user, arc.id, new_parent_id=chap.id, after_id=None)


async def test_outline_restore_reconnects_archived_ancestors(pool):
    """Restoring a node whose ancestor is still archived must also un-archive the
    archived ancestor chain — else the restored node orphans out of the tree
    (its parent_id points at an archived, invisible row)."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await repo.create_node(user, project, kind="arc", title="arc")
    chap = await repo.create_node(
        user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter,
    )
    scene = await repo.create_node(
        user, project, kind="scene", parent_id=chap.id, chapter_id=chapter,
    )
    await repo.archive_node(user, arc.id)  # archives arc+chap+scene

    # restore only the SCENE → ancestor chain (chap, arc) restored too
    restored = await repo.restore_node(user, scene.id)
    assert restored is not None and restored.is_archived is False
    visible = {n.id for n in await repo.list_tree(user, project)}
    assert {arc.id, chap.id, scene.id} <= visible  # reconnected to a visible root


async def test_outline_archive_terminates_on_parent_cycle(pool):
    """FINDING-3 backstop: archive_node's recursive CTE must not loop forever on
    a stray parent cycle. The repo now BLOCKS reparent-cycles (see
    test_outline_reparent_cycle_blocked), so we forge the cycle via RAW SQL to
    still prove the UNION backstop. Without UNION this test hangs."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    a = await repo.create_node(user, project, kind="arc", title="a")
    b = await repo.create_node(user, project, kind="arc", parent_id=a.id, title="b")
    # forge a cycle a → b → a bypassing the repo guard
    async with pool.acquire() as c:
        await c.execute("UPDATE outline_node SET parent_id = $1 WHERE id = $2", b.id, a.id)
    archived = await repo.archive_node(user, a.id)
    assert archived is not None and archived.is_archived
    # both nodes in the cycle archived; query returned (did not hang)
    assert {n.id for n in await repo.list_tree(user, project)} == set()


def _chapters_payload(*chapter_ids, scenes_per=1):
    return [
        {"chapter_id": cid, "title": f"ch-{i}", "intent": "x",
         "scenes": [{"title": f"s{j}", "synopsis": "y"} for j in range(scenes_per)]}
        for i, cid in enumerate(chapter_ids)
    ]


async def _active_ids(pool, user, project, kind):
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT id FROM outline_node WHERE user_id=$1 AND project_id=$2 "
            "AND kind=$3 AND NOT is_archived",
            user, project, kind,
        )
    return {r["id"] for r in rows}


async def test_decompose_replace_archives_prior_arc_and_chapter_nodes(pool):
    """FD-17/069: a replace re-plan must soft-archive the prior arc + chapter
    nodes, not ONLY their scenes — else orphan arc/chapter nodes accumulate on
    every re-plan (their scenes archived, a fresh arc/chapters created beside)."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chA = uuid.uuid4()
    r1 = await repo.commit_decomposed_tree(
        user, project, arc_title="v1", chapters=_chapters_payload(chA),
    )
    r2 = await repo.commit_decomposed_tree(
        user, project, arc_title="v2", chapters=_chapters_payload(chA), replace=True,
    )
    arcs = await _active_ids(pool, user, project, "arc")
    chaps = await _active_ids(pool, user, project, "chapter")
    scenes = await _active_ids(pool, user, project, "scene")
    # exactly the v2 tree is active — no orphan v1 arc/chapter/scene survives.
    assert arcs == {uuid.UUID(r2["arc_id"])}
    assert uuid.UUID(r1["arc_id"]) not in arcs
    assert chaps == {uuid.UUID(x) for x in r2["chapter_ids"]}
    assert scenes == {uuid.UUID(x) for x in r2["scene_ids"]}


async def test_decompose_partial_replace_preserves_arc_with_active_out_of_target_chapter(pool):
    """The childless-arc sweep must NOT archive an arc that still spans an active
    chapter OUTSIDE the replaced set (a partial re-plan) — only fully-emptied
    arcs are reaped."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chA, chB = uuid.uuid4(), uuid.uuid4()
    r1 = await repo.commit_decomposed_tree(
        user, project, arc_title="v1", chapters=_chapters_payload(chA, chB),
    )
    r2 = await repo.commit_decomposed_tree(
        user, project, arc_title="v2-chA", chapters=_chapters_payload(chA), replace=True,
    )
    arcs = await _active_ids(pool, user, project, "arc")
    # v1 arc SURVIVES (chB child still active) AND the new v2 arc exists.
    assert uuid.UUID(r1["arc_id"]) in arcs
    assert uuid.UUID(r2["arc_id"]) in arcs
    assert len(arcs) == 2
    chaps = await _active_ids(pool, user, project, "chapter")
    assert uuid.UUID(r1["chapter_ids"][0]) not in chaps   # chA prior chapter archived
    assert uuid.UUID(r1["chapter_ids"][1]) in chaps        # chB chapter preserved
    assert uuid.UUID(r2["chapter_ids"][0]) in chaps        # chA new chapter active


async def test_decompose_replace_does_not_archive_unrelated_empty_arc(pool):
    """/review-impl HIGH: the childless-arc sweep must be SCOPED to the arc(s)
    this replace orphans — a freshly-created, not-yet-populated bystander arc
    (no chapter children) must SURVIVE a decompose replace elsewhere in the
    project, not be archived as collateral by a project-wide 'any childless
    arc' sweep."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    bystander = await repo.create_node(user, project, kind="arc", title="manual-empty")
    chA = uuid.uuid4()
    await repo.commit_decomposed_tree(
        user, project, arc_title="v1", chapters=_chapters_payload(chA),
    )
    await repo.commit_decomposed_tree(
        user, project, arc_title="v2", chapters=_chapters_payload(chA), replace=True,
    )
    arcs = await _active_ids(pool, user, project, "arc")
    assert bystander.id in arcs   # the unrelated empty arc is NOT archived


async def test_outline_reparent_guards(pool):
    """D-COMP-M2-XREF-OWNERSHIP: update_node blocks self-parent, cross-user
    parent, and descendant (cycle) reparents; a valid reparent succeeds."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    a = await repo.create_node(user, project, kind="arc", title="a")
    b = await repo.create_node(user, project, kind="arc", parent_id=a.id, title="b")
    c_node = await repo.create_node(user, project, kind="arc", title="c")

    # self-parent
    with pytest.raises(ReferenceViolationError):
        await repo.update_node(user, a.id, {"parent_id": a.id})
    # cycle: parent a under its descendant b
    with pytest.raises(ReferenceViolationError):
        await repo.update_node(user, a.id, {"parent_id": b.id})
    # cross-user parent (another user's node)
    other_user, other_proj, _ = _ids()
    foreign = await repo.create_node(other_user, other_proj, kind="arc")
    with pytest.raises(ReferenceViolationError):
        await repo.update_node(user, c_node.id, {"parent_id": foreign.id})
    # valid reparent: move c under a (not a descendant of c)
    moved = await repo.update_node(user, c_node.id, {"parent_id": a.id})
    assert moved is not None and moved.parent_id == a.id
    # clearing the parent (→ top-level) is always allowed
    cleared = await repo.update_node(user, c_node.id, {"parent_id": None})
    assert cleared is not None and cleared.parent_id is None


async def test_outline_create_rejects_cross_scope_parent(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    other_user, other_proj, _ = _ids()
    foreign = await repo.create_node(other_user, other_proj, kind="arc")
    # parent owned by another user → rejected
    with pytest.raises(ReferenceViolationError):
        await repo.create_node(user, project, kind="arc", parent_id=foreign.id)
    # parent owned by us but in a DIFFERENT project → rejected
    mine_other_proj = await repo.create_node(user, uuid.uuid4(), kind="arc")
    with pytest.raises(ReferenceViolationError):
        await repo.create_node(user, project, kind="arc", parent_id=mine_other_proj.id)


async def test_outline_rank_orders_under_db_collation(pool):
    """FINDING-2: ranks must order by byte value even though the DB default
    collation is en_US.UTF-8. Insert many siblings and confirm list_tree
    (ORDER BY rank COLLATE "C") matches creation order."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    titles = [f"n{i:02d}" for i in range(20)]
    for t in titles:
        await repo.create_node(user, project, kind="arc", title=t)
    tree = await repo.list_tree(user, project)
    assert [n.title for n in tree] == titles
    # ranks are strictly ascending under byte (C) comparison
    ranks = [n.rank for n in tree]
    assert ranks == sorted(ranks)


async def test_outline_cross_user_isolation(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    node = await repo.create_node(user, project, kind="arc")
    assert await repo.get_node(uuid.uuid4(), node.id) is None
    assert await repo.archive_node(uuid.uuid4(), node.id) is None


# ───────────────────────── scene_links ─────────────────────────

async def test_scene_links_crud_and_isolation(pool):
    olr = OutlineRepo(pool)
    slr = SceneLinksRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    s1 = await olr.create_node(user, project, kind="scene", chapter_id=chapter)
    s2 = await olr.create_node(user, project, kind="scene", chapter_id=chapter)
    link = await slr.create(user, project, s1.id, s2.id, label="setup→payoff")
    assert link.from_node_id == s1.id and link.to_node_id == s2.id
    assert len(await slr.list_by_project(user, project)) == 1
    # cross-user delete is a no-op
    assert await slr.delete(uuid.uuid4(), link.id) is False
    assert await slr.delete(user, link.id) is True
    assert await slr.list_by_project(user, project) == []


async def test_scene_link_rejects_foreign_endpoint(pool):
    """D-COMP-M2-XREF-OWNERSHIP: a link endpoint that isn't the caller's node in
    this project is rejected (FK proves existence, not ownership)."""
    olr = OutlineRepo(pool)
    slr = SceneLinksRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    mine = await olr.create_node(user, project, kind="scene", chapter_id=chapter)
    other_user, other_proj, _ = _ids()
    foreign = await olr.create_node(other_user, other_proj, kind="scene", chapter_id=chapter)
    with pytest.raises(ReferenceViolationError):
        await slr.create(user, project, mine.id, foreign.id)
    # a node of ours but in another project is also rejected
    mine_other = await olr.create_node(user, uuid.uuid4(), kind="scene", chapter_id=chapter)
    with pytest.raises(ReferenceViolationError):
        await slr.create(user, project, mine.id, mine_other.id)


async def test_generation_job_rejects_foreign_node(pool):
    olr = OutlineRepo(pool)
    gjr = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    other_user, other_proj, _ = _ids()
    foreign = await olr.create_node(other_user, other_proj, kind="scene", chapter_id=uuid.uuid4())
    with pytest.raises(ReferenceViolationError):
        await gjr.create(user, project, operation="draft_scene", outline_node_id=foreign.id)


# ───────────────────────── canon_rules ─────────────────────────

async def test_canon_rules_active_listing_and_archive(pool):
    repo = CanonRulesRepo(pool)
    user, project, _ = _ids()
    r1 = await repo.create(user, project, "King is secretly dead", scope="reveal_gate")
    r2 = await repo.create(user, project, "Magic costs blood")
    # deactivate r2 → not in list_active, still in list_all
    await repo.update(user, r2.id, {"active": False})
    active = await repo.list_active(user, project)
    assert [r.id for r in active] == [r1.id]
    assert len(await repo.list_all(user, project)) == 2
    # archive r1 → out of both
    assert (await repo.archive(user, r1.id)) is not None
    assert await repo.list_active(user, project) == []
    assert len(await repo.list_all(user, project)) == 1
    assert await repo.archive(user, r1.id) is None  # already archived


async def test_canon_rules_ifmatch(pool):
    repo = CanonRulesRepo(pool)
    user, project, _ = _ids()
    r = await repo.create(user, project, "rule")
    upd = await repo.update(user, r.id, {"text": "rule v2"}, expected_version=1)
    assert upd is not None and upd.version == 2
    with pytest.raises(VersionMismatchError):
        await repo.update(user, r.id, {"text": "x"}, expected_version=1)


# ───────────────────────── grounding_pins (T3.4) ─────────────────────────

async def test_grounding_pins_upsert_flip_clear_and_tenancy(pool):
    repo = GroundingPinsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, _ = _ids()
    # outline_node_id is an in-DB FK (ON DELETE CASCADE) → create a real scene.
    scene = await olr.create_node(user, project, kind="scene", chapter_id=uuid.uuid4())
    # pin a lore source + exclude a cast entity
    p1 = await repo.set_action(user, project, scene.id, "lore", "src-1", "pin")
    assert p1.action == "pin" and p1.item_type == "lore" and p1.item_id == "src-1"
    await repo.set_action(user, project, scene.id, "present", "ent-1", "exclude")
    rows = await repo.list_for_scene(user, project, scene.id)
    assert {(r.item_type, r.item_id, r.action) for r in rows} == {
        ("lore", "src-1", "pin"), ("present", "ent-1", "exclude"),
    }
    # flip the lore pin → exclude IN PLACE (still one row for that item)
    flipped = await repo.set_action(user, project, scene.id, "lore", "src-1", "exclude")
    assert flipped.action == "exclude"
    rows = await repo.list_for_scene(user, project, scene.id)
    assert len(rows) == 2  # no duplicate row for src-1
    assert next(r for r in rows if r.item_id == "src-1").action == "exclude"
    # clear → row gone; a second clear is a no-op (False)
    assert await repo.clear(user, project, scene.id, "lore", "src-1") is True
    assert await repo.clear(user, project, scene.id, "lore", "src-1") is False
    assert len(await repo.list_for_scene(user, project, scene.id)) == 1
    # cross-user isolation — another user sees nothing for this scene
    assert await repo.list_for_scene(uuid.uuid4(), project, scene.id) == []


async def test_grounding_pins_cascade_on_scene_delete(pool):
    repo = GroundingPinsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, _ = _ids()
    scene = await olr.create_node(user, project, kind="scene", chapter_id=uuid.uuid4())
    await repo.set_action(user, project, scene.id, "canon", str(uuid.uuid4()), "pin")
    assert len(await repo.list_for_scene(user, project, scene.id)) == 1
    # deleting the scene CASCADE-drops its pins (no orphan rows)
    async with pool.acquire() as c:
        await c.execute("DELETE FROM outline_node WHERE id = $1", scene.id)
    assert await repo.list_for_scene(user, project, scene.id) == []


# ───────────────────────── generation_jobs ─────────────────────────

async def test_generation_job_idempotency_replay(pool):
    repo = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    job1, created1 = await repo.create(
        user, project, operation="draft_scene", idempotency_key="k1",
    )
    assert created1 is True
    job2, created2 = await repo.create(
        user, project, operation="draft_scene", idempotency_key="k1",
    )
    assert created2 is False and job2.id == job1.id  # replay returns same job
    # no key → always a fresh row
    j3, c3 = await repo.create(user, project, operation="continue")
    j4, c4 = await repo.create(user, project, operation="continue")
    assert c3 and c4 and j3.id != j4.id


async def test_generation_job_status_update_coalesces(pool):
    repo = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, _ = _ids()
    # outline_node_id is an in-DB FK → create a real node to point at.
    node = await olr.create_node(user, project, kind="scene", chapter_id=uuid.uuid4())
    node_id = node.id
    job, _ = await repo.create(
        user, project, operation="draft_scene", outline_node_id=node_id,
        input={"prompt": "hi"},
    )
    assert len(await repo.list_active_for_node(user, project, node_id)) == 1
    # set result + run
    await repo.update_status(user, job.id, "running", result={"text": "draft"})
    # later set critic WITHOUT clobbering result
    done = await repo.update_status(
        user, job.id, "completed", critic={"coherence": 4},
        target_revision_id=uuid.uuid4(),
    )
    assert done is not None
    assert done.result == {"text": "draft"} and done.critic == {"coherence": 4}
    assert done.status == "completed"
    assert await repo.list_active_for_node(user, project, node_id) == []


# ── M3 (WS-B3): promoted scene-prose synthetic-job store ──

async def test_promoted_scene_prose_persists_and_reads_back(pool):
    # A promoted scene's prose is written as a synthetic completed job and READS
    # BACK through chapter_scene_drafts / prior_scene_drafts (the existing readers),
    # with NO new table — the M3 contract's core requirement.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await olr.create_node(user, project, kind="arc", title="arc")
    chap = await olr.create_node(user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    s1 = await olr.create_node(user, project, kind="scene", parent_id=chap.id,
                               chapter_id=chapter, story_order=1, title="s1")
    s2 = await olr.create_node(user, project, kind="scene", parent_id=chap.id,
                               chapter_id=chapter, story_order=2, title="s2")
    job1, v1 = await gjr.upsert_promoted_scene_prose(user, project, s1.id, "scene one prose")
    job2, v2 = await gjr.upsert_promoted_scene_prose(user, project, s2.id, "scene two prose")
    assert v1 == 1 and v2 == 1
    assert job1.status == "completed" and job1.result == {"text": "scene one prose"}
    assert job1.input.get("kind") == "promoted_scene_prose"
    # chapter_scene_drafts reads EVERY scene's promoted prose in story_order
    drafts = await gjr.chapter_scene_drafts(user, project, chapter)
    assert drafts == ["scene one prose", "scene two prose"]
    # prior_scene_drafts is position-bounded (strictly before story_order=2 → only s1)
    prior = await gjr.prior_scene_drafts(user, project, chapter, 2)
    assert prior == ["scene one prose"]


async def test_promoted_scene_prose_idempotent_overwrite_never_duplicates(pool):
    # A re-promote / double-submit OVERWRITES the same scene's prose (one row), never
    # duplicates; the version increments and the read-back reflects the latest text.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    arc = await olr.create_node(user, project, kind="arc", title="arc")
    chap = await olr.create_node(user, project, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    scene = await olr.create_node(user, project, kind="scene", parent_id=chap.id,
                                  chapter_id=chapter, story_order=1, title="s1")
    _, v1 = await gjr.upsert_promoted_scene_prose(user, project, scene.id, "first take")
    _, v2 = await gjr.upsert_promoted_scene_prose(user, project, scene.id, "second take")
    assert v1 == 1 and v2 == 2
    # exactly ONE promoted-prose row for the node (overwrite, not duplicate)
    async with pool.acquire() as c:
        n = await c.fetchval(
            "SELECT count(*) FROM generation_job "
            "WHERE outline_node_id=$1 AND input->>'kind'='promoted_scene_prose'", scene.id)
    assert n == 1
    # read-back is the latest take
    drafts = await gjr.chapter_scene_drafts(user, project, chapter)
    assert drafts == ["second take"]


async def test_promoted_scene_prose_rejects_foreign_or_non_scene_node(pool):
    # Defense-in-depth: the node must be the caller's SCENE in this project.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, _ = _ids()
    other_user, other_proj, _ = _ids()
    # foreign scene (another user/project)
    foreign = await olr.create_node(other_user, other_proj, kind="scene", chapter_id=uuid.uuid4())
    with pytest.raises(ReferenceViolationError):
        await gjr.upsert_promoted_scene_prose(user, project, foreign.id, "x")
    # a non-scene node (a chapter) in this project is rejected too
    chap = await olr.create_node(user, project, kind="chapter", chapter_id=uuid.uuid4())
    with pytest.raises(ReferenceViolationError):
        await gjr.upsert_promoted_scene_prose(user, project, chap.id, "x")


async def test_promoted_scene_prose_scoped_per_project(pool):
    # Two derivatives (distinct project_ids) promoting the SAME node id keep separate
    # rows — the dedup unit is (project, node), so they never clobber each other.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, projA, _ = _ids()
    _, projB, _ = _ids()
    chapter = uuid.uuid4()
    sA = await olr.create_node(user, projA, kind="scene", chapter_id=chapter, story_order=1)
    sB = await olr.create_node(user, projB, kind="scene", chapter_id=chapter, story_order=1)
    await gjr.upsert_promoted_scene_prose(user, projA, sA.id, "A prose")
    await gjr.upsert_promoted_scene_prose(user, projB, sB.id, "B prose")
    assert await gjr.chapter_scene_drafts(user, projA, chapter) == ["A prose"]
    assert await gjr.chapter_scene_drafts(user, projB, chapter) == ["B prose"]


async def _insert_stale_job(pool, user, project, *, chapter_id=None) -> uuid.UUID:
    """Insert a `running` job created 1h ago (a crash-orphan). Optional chapter_id
    in input makes it a chapter-level node-less job for the opportunistic-reap test."""
    inp = {"chapter_id": str(chapter_id)} if chapter_id else {}
    async with pool.acquire() as c:
        return await c.fetchval(
            """INSERT INTO generation_job
                 (user_id, project_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,'draft_chapter','auto','running',$3::jsonb, now() - interval '1 hour')
               RETURNING id""",
            user, project, json.dumps(inp))


async def test_reap_stale_jobs_marks_stale_failed_leaves_fresh(pool):
    # D-COMP-CHAPTER-INFLIGHT-REAPER sweep: jobs orphaned in `running` past the
    # cutoff are marked failed; a fresh one is untouched.
    repo = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    stale = [await _insert_stale_job(pool, user, project) for _ in range(2)]
    fresh, _ = await repo.create(user, project, operation="draft_chapter", status="running")
    reaped = await repo.reap_stale_jobs(datetime.now(timezone.utc) - timedelta(minutes=30))
    assert reaped == 2  # clean test DB → exactly the two stale jobs
    async with pool.acquire() as c:
        for sid in stale:
            assert await c.fetchval("SELECT status FROM generation_job WHERE id=$1", sid) == "failed"
        assert await c.fetchval("SELECT status FROM generation_job WHERE id=$1", fresh.id) == "running"


async def test_reap_stale_jobs_excludes_worker_ops(pool):
    # D-M4-REAPER-WORKER-CONFLICT: with the worker on (exclude_operations passed),
    # a stale WORKER-OP job is left for the worker's own updated_at sweeper, while a
    # stale inline (non-worker) job is still reaped. Worker-ownership = operation in
    # SUPPORTED_OPERATIONS OR an input->>'worker_op'.
    from app.worker.operations import SUPPORTED_OPERATIONS

    repo = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    async with pool.acquire() as c:
        worker_by_op = await c.fetchval(
            """INSERT INTO generation_job (user_id, project_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,'stitch_chapter','auto','running','{}'::jsonb, now() - interval '1 hour')
               RETURNING id""", user, project)
        worker_by_input = await c.fetchval(
            """INSERT INTO generation_job (user_id, project_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,'draft_scene','auto','running',$3::jsonb, now() - interval '1 hour')
               RETURNING id""", user, project, json.dumps({"worker_op": "generate"}))
        inline = await c.fetchval(
            """INSERT INTO generation_job (user_id, project_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,'draft_chapter','auto','running','{}'::jsonb, now() - interval '1 hour')
               RETURNING id""", user, project)

    reaped = await repo.reap_stale_jobs(
        datetime.now(timezone.utc) - timedelta(minutes=30),
        exclude_operations=list(SUPPORTED_OPERATIONS),
    )
    assert reaped == 1  # only the inline job
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT status FROM generation_job WHERE id=$1", worker_by_op) == "running"
        assert await c.fetchval("SELECT status FROM generation_job WHERE id=$1", worker_by_input) == "running"
        assert await c.fetchval("SELECT status FROM generation_job WHERE id=$1", inline) == "failed"


async def test_create_chapter_job_guarded_opportunistic_reap(pool):
    # The guard marks THIS chapter's stale node-less jobs failed (opportunistic),
    # then creates a new one (the stale job is past the window, so it doesn't block).
    repo = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    stale = await _insert_stale_job(pool, user, project, chapter_id=chapter)
    job, created = await repo.create_chapter_job_guarded(
        user, project, chapter, operation="draft_chapter",
        input={"chapter_id": str(chapter)}, stale_secs=1800)
    assert created is True and job.status == "running"
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT status FROM generation_job WHERE id=$1", stale) == "failed"


# ───────────────────────── outbox (txn-local) ─────────────────────────

async def test_structure_templates_lists_builtins(pool):
    """M7: list_for_user returns the 6 seeded built-ins (owner NULL) + the user's
    own; another user's custom template is excluded."""
    repo = StructureTemplatesRepo(pool)
    user = uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO structure_template (owner_user_id, name, kind) VALUES ($1,'Mine','generic')", user)
        await c.execute(
            "INSERT INTO structure_template (owner_user_id, name, kind) VALUES ($1,'Theirs','generic')", uuid.uuid4())
    mine = await repo.list_for_user(user)
    names = {t.name for t in mine}
    assert "Mine" in names and "Theirs" not in names
    builtins = [t for t in mine if t.owner_user_id is None]
    assert len(builtins) == 6  # the 6 seeded structures
    assert builtins[0].beats  # beats jsonb round-trips


async def test_outbox_emit_is_transactional(pool):
    works = WorksRepo(pool)
    user, project, book = _ids()
    # commit path: work + event in one txn
    async with pool.acquire() as conn:
        async with conn.transaction():
            w = await works.create(user, project, book, conn=conn)
            await outbox.emit(
                conn, aggregate_id=w.project_id,
                event_type=outbox.WORK_CREATED, payload={"book_id": str(book)},
            )
    async with pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM outbox_events WHERE event_type=$1", outbox.WORK_CREATED)
    assert n == 1

    # rollback path: the event vanishes with the aborted txn
    p2 = uuid.uuid4()
    with pytest.raises(RuntimeError):
        async with pool.acquire() as conn:
            async with conn.transaction():
                await works.create(user, p2, book, conn=conn)
                await outbox.emit(conn, aggregate_id=p2, event_type="composition.rolled_back")
                raise RuntimeError("force rollback")
    async with pool.acquire() as c:
        gone = await c.fetchval("SELECT count(*) FROM outbox_events WHERE event_type=$1", "composition.rolled_back")
        no_work = await c.fetchval("SELECT count(*) FROM composition_work WHERE project_id=$1", p2)
    assert gone == 0 and no_work == 0  # atomic: both rolled back


# ───────────────────────── M9 chapter-gate + scene_committed ─────────────────────────

async def _scene_committed_count(pool, project) -> int:
    async with pool.acquire() as c:
        return await c.fetchval(
            "SELECT count(*) FROM outbox_events WHERE event_type=$1 AND aggregate_id=$2",
            outbox.SCENE_COMMITTED, project,
        )


async def test_scene_commit_emits_scene_committed_event(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    scene = await repo.create_node(user, project, kind="scene", chapter_id=chapter, title="S1")

    # drafting → done: exactly one scene_committed event, with the right payload
    done = await repo.update_node_commit_aware(user, scene.id, {"status": "done"})
    assert done is not None and done.status == "done"
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT aggregate_id, payload FROM outbox_events WHERE event_type=$1",
            outbox.SCENE_COMMITTED,
        )
    assert len(rows) == 1
    assert rows[0]["aggregate_id"] == project
    import json as _json
    payload = _json.loads(rows[0]["payload"])
    assert payload["scene_id"] == str(scene.id)
    assert payload["chapter_id"] == str(chapter)
    assert payload["project_id"] == str(project)

    # done → done: a no-op transition emits NO further event
    await repo.update_node_commit_aware(user, scene.id, {"status": "done"})
    assert await _scene_committed_count(pool, project) == 1


async def test_non_scene_done_emits_no_event(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = await repo.create_node(user, project, kind="chapter", chapter_id=uuid.uuid4())
    await repo.update_node_commit_aware(user, chapter.id, {"status": "done"})
    assert await _scene_committed_count(pool, project) == 0


async def test_scene_commit_rolls_back_event_on_version_conflict(pool):
    # a stale If-Match raises VersionMismatchError from inside the txn → the
    # status write AND any event roll back together (no orphan telemetry).
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    scene = await repo.create_node(user, project, kind="scene", chapter_id=uuid.uuid4())
    with pytest.raises(VersionMismatchError):
        await repo.update_node_commit_aware(user, scene.id, {"status": "done"}, expected_version=99)
    assert await _scene_committed_count(pool, project) == 0
    # the scene status was NOT advanced
    still = await repo.get_node(user, scene.id)
    assert still is not None and still.status != "done"


async def test_chapter_scene_gate_counts_and_can_publish(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    other_chapter = uuid.uuid4()
    s1 = await repo.create_node(user, project, kind="scene", chapter_id=chapter)
    s2 = await repo.create_node(user, project, kind="scene", chapter_id=chapter)
    # a scene in a DIFFERENT chapter must not count
    await repo.create_node(user, project, kind="scene", chapter_id=other_chapter, status="done")

    # zero done → blocked
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate == {"chapter_id": str(chapter), "scenes_total": 2, "scenes_done": 0,
                    "canon_blocked": False, "canon_unresolved_scenes": 0,
                    "canon_unchecked_scenes": 0, "can_publish": False}

    # one done → still blocked
    await repo.update_node_commit_aware(user, s1.id, {"status": "done"})
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["scenes_done"] == 1 and gate["can_publish"] is False

    # all done → publishable
    await repo.update_node_commit_aware(user, s2.id, {"status": "done"})
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["scenes_total"] == 2 and gate["scenes_done"] == 2 and gate["can_publish"] is True

    # an archived scene drops out of the count
    await repo.archive_node(user, s2.id)
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["scenes_total"] == 1 and gate["can_publish"] is True


async def test_chapter_scene_gate_zero_scenes_blocks(pool):
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    gate = await repo.chapter_scene_gate(user, project, uuid.uuid4())
    assert gate["scenes_total"] == 0 and gate["can_publish"] is False


async def test_chapter_scene_gate_blocks_on_unresolved_canon(pool):
    """D-A2S3B-PUBLISH-GATE — an all-scenes-done chapter is still blocked when a
    scene's LATEST completed auto job left a confirmed canon contradiction
    (result.canon.resolved == false); a newer resolved job supersedes it."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    s1 = await repo.create_node(user, project, kind="scene", chapter_id=chapter)
    await repo.update_node_commit_aware(user, s1.id, {"status": "done"})  # all done

    # baseline: no jobs → not canon-blocked → publishable.
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["can_publish"] is True and gate["canon_blocked"] is False

    # latest completed auto job left an UNRESOLVED canon contradiction → blocked.
    j1, _ = await jobs.create(user, project, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(user, j1.id, "completed",
                             result={"text": "x", "canon": {"resolved": False,
                                                            "violations": [{"entity_id": "e"}]}})
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["scenes_done"] == 1
    assert gate["canon_blocked"] is True and gate["canon_unresolved_scenes"] == 1
    assert gate["can_publish"] is False

    # a NEWER resolved job for the same scene supersedes (DISTINCT ON latest).
    j2, _ = await jobs.create(user, project, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(user, j2.id, "completed",
                             result={"text": "y", "canon": {"resolved": True}})
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["canon_blocked"] is False and gate["can_publish"] is True


async def test_chapter_scene_gate_synthetic_prose_job_does_not_mask_canon(pool):
    """D-M3-PROSEJOB-PUBLISHGATE — a synthetic `promoted_scene_prose` job (M3, no
    canon verdict) must NOT shadow an earlier auto-gen's CONFIRMED contradiction.
    It is NEWER than the contradicting job, but carries no canon-check, so treating
    it as 'latest' would silently un-block publish. The gate excludes it → still
    blocked (conservative-for-canon: only a real re-generation can clear the block)."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    s1 = await repo.create_node(user, project, kind="scene", chapter_id=chapter)
    await repo.update_node_commit_aware(user, s1.id, {"status": "done"})

    # auto job leaves an unresolved contradiction → blocked.
    j1, _ = await jobs.create(user, project, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(user, j1.id, "completed",
                             result={"text": "x", "canon": {"resolved": False,
                                                            "violations": [{"entity_id": "e"}]}})
    assert (await repo.chapter_scene_gate(user, project, chapter))["canon_blocked"] is True

    # a LATER synthetic prose-persist job (no canon key) must NOT mask the block.
    await jobs.upsert_promoted_scene_prose(user, project, s1.id, "author's edited take prose")
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["canon_blocked"] is True and gate["canon_unresolved_scenes"] == 1
    assert gate["can_publish"] is False


async def test_chapter_scene_gate_surfaces_unchecked_without_blocking(pool):
    """Dirty-data path: a scene whose latest auto job could NOT verify canon
    (status=skipped_no_position / degraded) is SURFACED via canon_unchecked_scenes
    but does NOT block publish (false-blocking every un-positioned scene is worse;
    the FE warns instead)."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    s1 = await repo.create_node(user, project, kind="scene", chapter_id=chapter)
    await repo.update_node_commit_aware(user, s1.id, {"status": "done"})
    j, _ = await jobs.create(user, project, operation="draft_scene",
                             outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(user, j.id, "completed",
                             result={"text": "x", "canon": {"resolved": True,
                                                            "status": "skipped_no_position"}})
    gate = await repo.chapter_scene_gate(user, project, chapter)
    assert gate["canon_unchecked_scenes"] == 1
    assert gate["canon_blocked"] is False
    assert gate["can_publish"] is True  # surfaced, NOT blocked


# ──────────────────── generation_correction (V1 flywheel slice 1) ────────────────────

import json as _json  # noqa: E402


async def _make_job(pool, user, project):
    gjr = GenerationJobsRepo(pool)
    job, _ = await gjr.create(user, project, operation="draft_scene",
                              status="completed", input={"model_ref": str(uuid.uuid4())})
    return job


async def test_correction_create_emits_relayable_event_atomically(pool):
    user, project, _ = _ids()
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    corr = await repo.create(
        user, project, job.id, kind="edit", changed_blocks=3, guidance="tighten",
    )
    assert corr.kind == "edit" and corr.changed_blocks == 3
    async with pool.acquire() as c:
        n_rows = await c.fetchval("SELECT count(*) FROM generation_correction WHERE id=$1", corr.id)
        ev = await c.fetchrow(
            "SELECT aggregate_id, payload FROM outbox_events WHERE event_type=$1",
            outbox.GENERATION_CORRECTED)
    assert n_rows == 1
    # the relayable event exists (the H1 fix means this row now actually ships)
    assert ev is not None and ev["aggregate_id"] == project
    payload = _json.loads(ev["payload"])
    assert payload["kind"] == "edit" and payload["changed_blocks"] == 3
    assert payload["job_id"] == str(job.id)
    # owner identity is on the wire (slice 2: the corrections store is user-scoped)
    assert payload["user_id"] == str(user)
    # redact-by-default: no verbatim prose / guidance text on the wire (§5)
    assert "guidance" not in payload and "raw_before" not in payload and "raw_after" not in payload
    assert payload["has_guidance"] is True and payload["has_raw_prose"] is False


async def test_correction_payload_carries_winner_and_k_for_reconstruction(pool):
    """LOW#4: a pick_different event must carry winner_index (i) + chosen (j) + k
    so slice-2 learning can reconstruct `j ≻ i` without reading composition's DB."""
    user, project, _ = _ids()
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    await repo.create(user, project, job.id, kind="pick_different",
                      chosen_candidate_index=1, winner_index=2, candidate_count=3)
    async with pool.acquire() as c:
        ev = await c.fetchval(
            "SELECT payload FROM outbox_events WHERE event_type=$1 ORDER BY created_at DESC LIMIT 1",
            outbox.GENERATION_CORRECTED)
    payload = _json.loads(ev)
    assert payload["winner_index"] == 2
    assert payload["chosen_candidate_index"] == 1
    assert payload["candidate_count"] == 3


async def test_correction_emit_failure_rolls_back_row(pool, monkeypatch):
    """The insert + outbox emit share ONE transaction: if the emit raises, the
    correction row must NOT persist (no capture without a relayable event)."""
    user, project, _ = _ids()
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)

    async def boom(*a, **k):
        raise RuntimeError("relay emit failed")

    monkeypatch.setattr("app.db.repositories.outbox.emit", boom)
    with pytest.raises(RuntimeError):
        await repo.create(user, project, job.id, kind="reject")
    async with pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM generation_correction WHERE job_id=$1", job.id)
    assert n == 0  # atomic: the row rolled back with the failed emit


async def test_correction_rejects_foreign_job(pool):
    user, project, _ = _ids()
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    # another user correcting our job → rejected, no row, no event
    other, _, _ = _ids()
    with pytest.raises(ReferenceViolationError):
        await repo.create(other, project, job.id, kind="reject")
    # wrong project for the right user → also rejected
    with pytest.raises(ReferenceViolationError):
        await repo.create(user, uuid.uuid4(), job.id, kind="reject")
    async with pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM generation_correction")
        ev = await c.fetchval("SELECT count(*) FROM outbox_events WHERE event_type=$1",
                              outbox.GENERATION_CORRECTED)
    assert n == 0 and ev == 0


async def test_correction_rejects_foreign_regenerated_to_job(pool):
    """/review-impl MED#2: the §8.3 chain target must also be the caller's job in
    this project — a foreign regenerated_to_job_id is rejected, nothing written."""
    user, project, _ = _ids()
    job = await _make_job(pool, user, project)
    # a job owned by another user (FK would pass — it exists — but ownership must not)
    other, other_proj, _ = _ids()
    foreign_job = await _make_job(pool, other, other_proj)
    repo = GenerationCorrectionsRepo(pool)
    with pytest.raises(ReferenceViolationError):
        await repo.create(user, project, job.id, kind="regenerate",
                          regenerated_to_job_id=foreign_job.id)
    async with pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM generation_correction")
        ev = await c.fetchval("SELECT count(*) FROM outbox_events WHERE event_type=$1",
                              outbox.GENERATION_CORRECTED)
    assert n == 0 and ev == 0
    # a chain target that IS the caller's own job in-project is accepted
    own2 = await _make_job(pool, user, project)
    ok = await repo.create(user, project, job.id, kind="regenerate",
                           regenerated_to_job_id=own2.id)
    assert ok.regenerated_to_job_id == own2.id


async def test_correction_pick_different_check_constraint(pool):
    """The DB CHECK forbids a pick_different without the candidate it points at."""
    user, project, _ = _ids()
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    with pytest.raises(asyncpg.CheckViolationError):
        await repo.create(user, project, job.id, kind="pick_different",
                          chosen_candidate_index=None)


async def test_correction_stores_raw_prose_and_lists(pool):
    user, project, _ = _ids()
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    await repo.create(user, project, job.id, kind="edit", changed_blocks=1,
                      raw_before="winner text", raw_after="edited text")
    listed = await repo.list_for_job(user, job.id)
    assert len(listed) == 1
    assert listed[0].raw_before == "winner text" and listed[0].raw_after == "edited text"
    # cross-user list is empty
    assert await repo.list_for_job(uuid.uuid4(), job.id) == []


async def test_correction_stats_rates_by_mode(pool):
    """slice 5 eval-gate: per-mode correction rates over real jobs + corrections.
    Denominator = COMPLETED generations; accept_rate is derived (H2-safe);
    avg_edit_magnitude reads changed_blocks; both modes always present."""
    gjr = GenerationJobsRepo(pool)
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    auto = []
    for _ in range(4):
        j, _ = await gjr.create(user, project, operation="draft_scene", mode="auto", status="completed")
        auto.append(j)
    cow = []
    for _ in range(2):
        j, _ = await gjr.create(user, project, operation="draft_scene", mode="cowrite", status="completed")
        cow.append(j)
    # a 'running' auto job must NOT count toward generations (denominator)
    await gjr.create(user, project, operation="draft_scene", mode="auto", status="running")
    # auto: one edit (magnitude 3) + one pick_different → 2 corrected of 4
    await cr.create(user, project, auto[0].id, kind="edit", changed_blocks=3)
    await cr.create(user, project, auto[1].id, kind="pick_different", chosen_candidate_index=1)
    # cowrite: one reject → 1 corrected of 2
    await cr.create(user, project, cow[0].id, kind="reject")

    stats = await cr.correction_stats(user, project)
    by = {m.mode: m for m in stats.by_mode}
    assert set(by) == {"auto", "cowrite"}  # both always present
    a = by["auto"]
    assert a.generations == 4 and a.corrected_jobs == 2  # the running job excluded
    assert a.edit_rate == 0.25 and a.pick_different_rate == 0.25
    assert a.regenerate_rate == 0.0 and a.reject_rate == 0.0
    assert a.accept_rate == 0.5 and a.avg_edit_magnitude == 3.0
    cw = by["cowrite"]
    assert cw.generations == 2 and cw.corrected_jobs == 1 and cw.reject_rate == 0.5
    assert cw.edit_rate == 0.0 and cw.avg_edit_magnitude is None
    # cross-user isolation → all zero
    other = await cr.correction_stats(uuid.uuid4(), project)
    assert all(m.generations == 0 and m.corrected_jobs == 0 for m in other.by_mode)


async def test_correction_stats_excludes_selection_edits(pool):
    """/review-impl: T3.2 selection edits run mode='cowrite' but are NOT part of the
    draft-correction flywheel (no correction captured) — they must NOT inflate the
    cowrite `generations` denominator, which would drag its correction rate down and
    corrupt the cowrite-vs-auto eval signal."""
    gjr = GenerationJobsRepo(pool)
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    # one real cowrite scene draft + two selection edits (also mode='cowrite').
    await gjr.create(user, project, operation="draft_scene", mode="cowrite", status="completed")
    await gjr.create(user, project, operation="rewrite", mode="cowrite", status="completed",
                     input={"selection_edit": True})
    await gjr.create(user, project, operation="expand", mode="cowrite", status="completed",
                     input={"selection_edit": True})
    stats = await cr.correction_stats(user, project)
    cw = next(m for m in stats.by_mode if m.mode == "cowrite")
    assert cw.generations == 1  # ONLY the real scene draft, not the 2 selection edits


async def test_correction_stats_distinct_job_and_completed_only(pool):
    """/review-impl slice-5 MED#1+#2: multiple corrections on ONE job count it
    ONCE (a rate can't exceed 1.0), and a correction on a NON-completed job is
    excluded so corrected_jobs ⊆ generations and accept_rate can't go negative."""
    gjr = GenerationJobsRepo(pool)
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    # one completed auto generation that gets TWO corrections (regenerate + edit)
    j, _ = await gjr.create(user, project, operation="draft_scene", mode="auto", status="completed")
    await cr.create(user, project, j.id, kind="regenerate", guidance="darker")
    await cr.create(user, project, j.id, kind="edit", changed_blocks=2)
    # a RUNNING auto job with a reject correction (creatable via the API) must NOT count
    run, _ = await gjr.create(user, project, operation="draft_scene", mode="auto", status="running")
    await cr.create(user, project, run.id, kind="reject")

    a = next(m for m in (await cr.correction_stats(user, project)).by_mode if m.mode == "auto")
    assert a.generations == 1          # only the completed job
    assert a.corrected_jobs == 1       # the one job, counted ONCE despite 2 corrections
    assert a.edit_rate == 1.0 and a.regenerate_rate == 1.0   # ≤ 1.0
    assert a.reject_rate == 0.0        # the running-job reject is excluded
    assert a.accept_rate == 0.0        # (1−1)/1 — never negative


async def test_correction_stats_cold_start_null_rates(pool):
    """No generations → rates are None (cold-start), not div-by-zero."""
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    stats = await cr.correction_stats(user, project)
    for m in stats.by_mode:
        assert m.generations == 0 and m.accept_rate is None and m.edit_rate is None


# ── narrative_thread ledger (cycle 14 §5.2/§10.2) ──────────────────────────────


async def _make_node(pool, user, project) -> uuid.UUID:
    """A minimal arc outline_node so the narrative_thread node FKs resolve."""
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO outline_node (user_id, project_id, kind, rank) "
            "VALUES ($1, $2, 'arc', 'a') RETURNING id",
            user, project,
        )


async def test_narrative_thread_open_pay_lifecycle(pool):
    """open → list_open shows it → pay (with payoff_node) → list_open drops it,
    list_for_project keeps it (paid). Tenant isolation: another user can't pay it."""
    repo = NarrativeThreadRepo(pool)
    user, project, _ = _ids()
    node = await _make_node(pool, user, project)
    payoff = await _make_node(pool, user, project)
    t = await repo.open_thread(
        user, project, kind="promise", summary="a sword is promised",
        opened_at_node=node, trigger="hand on the hilt", priority=80,
    )
    assert t.status == "open" and t.payoff_node is None and t.opened_at_node == node

    assert [x.id for x in await repo.list_open(user, project)] == [t.id]

    # tenant isolation: another user cannot transition it.
    other = uuid.uuid4()
    assert await repo.update_status(other, project, t.id, status="paid", payoff_node=payoff) is None

    paid = await repo.update_status(user, project, t.id, status="paid", payoff_node=payoff)
    assert paid is not None and paid.status == "paid" and paid.payoff_node == payoff and paid.version == 2

    # paid → out of the re-injectable open set; still in the full list.
    assert await repo.list_open(user, project) == []
    allt = await repo.list_for_project(user, project)
    assert len(allt) == 1 and allt[0].status == "paid"


async def test_narrative_thread_payoff_only_when_paid(pool):
    """A payoff_node on a non-paid transition is cleared by the repo, so the
    table CHECK (payoff_node IS NULL OR status='paid') never trips."""
    repo = NarrativeThreadRepo(pool)
    user, project, _ = _ids()
    node = await _make_node(pool, user, project)
    t = await repo.open_thread(user, project, kind="foreshadow", summary="a stranger watches")
    prog = await repo.update_status(user, project, t.id, status="progressing", payoff_node=node)
    assert prog is not None and prog.status == "progressing" and prog.payoff_node is None


async def test_narrative_thread_list_open_ordering(pool):
    """The F2 re-injection read order: highest priority first, then oldest-first."""
    repo = NarrativeThreadRepo(pool)
    user, project, _ = _ids()
    low = await repo.open_thread(user, project, kind="promise", summary="low", priority=10)
    high = await repo.open_thread(user, project, kind="promise", summary="high", priority=90)
    mid = await repo.open_thread(user, project, kind="promise", summary="mid", priority=50)
    assert [x.id for x in await repo.list_open(user, project)] == [high.id, mid.id, low.id]


async def test_narrative_thread_node_delete_sets_null(pool):
    """ON DELETE SET NULL: removing the anchored outline_node leaves the thread
    intact but un-anchored (no dangling ref)."""
    repo = NarrativeThreadRepo(pool)
    user, project, _ = _ids()
    node = await _make_node(pool, user, project)
    t = await repo.open_thread(user, project, kind="promise", summary="anchored", opened_at_node=node)
    async with pool.acquire() as c:
        await c.execute("DELETE FROM outline_node WHERE id = $1", node)
    after = (await repo.list_for_project(user, project))[0]
    assert after.id == t.id and after.opened_at_node is None


# ─────────────────────── daily_progress (T4.2) ───────────────────────

async def test_daily_progress_diff_streak_and_book_total(pool):
    """Snapshot-differencing model: the FIRST snapshot of a chapter is a baseline
    (0 authored), later snapshots count their positive delta, a deletion clamps to
    0, the book total is the sum of each chapter's latest snapshot, and a re-report
    the same (chapter, date) overwrites that day's snapshot (idempotent upsert)."""
    repo = DailyProgressRepo(pool)
    user, project, _ = _ids()
    chA, chB = uuid.uuid4(), uuid.uuid4()
    d20, d21, d22 = date(2026, 6, 20), date(2026, 6, 21), date(2026, 6, 22)

    # chapter A: baseline 500 (pre-existing) -> 800 (+300) -> 750 (deleted 50)
    await repo.report(user, project, chA, 500, d20)
    await repo.report(user, project, chA, 800, d21)
    await repo.report(user, project, chA, 750, d22)
    # chapter B: first appears on d21 at 100 (baseline, 0 authored) -> 250 (+150)
    await repo.report(user, project, chB, 100, d21)
    await repo.report(user, project, chB, 250, d22)

    agg = await repo.read_aggregate(user, project, d22)
    by_date = dict(agg.day_words)
    # d20: A baseline -> 0
    assert by_date[d20] == 0
    # d21: A +300, B baseline 0 -> 300
    assert by_date[d21] == 300
    # d22: A delta -50 clamps to 0, B +150 -> 150
    assert by_date[d22] == 150
    # book total = latest snapshot per chapter = A:750 + B:250
    assert agg.book_total == 1000


async def test_daily_progress_report_is_idempotent_per_date(pool):
    """Re-reporting the same (chapter, date) overwrites — never double-counts."""
    repo = DailyProgressRepo(pool)
    user, project, _ = _ids()
    ch = uuid.uuid4()
    d = date(2026, 6, 24)
    await repo.report(user, project, ch, 100, d)
    await repo.report(user, project, ch, 900, d)  # same day, corrected count
    agg = await repo.read_aggregate(user, project, d)
    # one baseline row for the day -> 0 authored, book total reflects the LATEST value
    assert dict(agg.day_words).get(d, 0) == 0
    assert agg.book_total == 900


async def test_daily_progress_anchor_excludes_future_dates_and_isolates_user(pool):
    """`on_or_before` clips future-dated snapshots (clock skew) and the read is
    per-user (another user's words never leak into the aggregate)."""
    repo = DailyProgressRepo(pool)
    user, project, _ = _ids()
    ch = uuid.uuid4()
    await repo.report(user, project, ch, 200, date(2026, 6, 20))
    await repo.report(user, project, ch, 400, date(2026, 6, 25))  # "future" vs anchor
    agg = await repo.read_aggregate(user, project, date(2026, 6, 22))
    assert agg.book_total == 200  # the 25th is excluded
    # cross-user isolation
    other = await repo.read_aggregate(uuid.uuid4(), project, date(2026, 6, 25))
    assert other.book_total == 0 and other.day_words == []


async def test_daily_progress_baseline_excludes_preexisting_counts_deltas(pool):
    """An EXISTING chapter baselined at its pre-existing count: its first daily
    snapshot counts only the NEW words (no enablement spike), book total is current."""
    repo = DailyProgressRepo(pool)
    user, project, _ = _ids()
    ch = uuid.uuid4()
    await repo.ensure_baseline(user, project, ch, 5000)   # pre-existing on open
    await repo.report(user, project, ch, 5200, date(2026, 6, 24))  # wrote 200 today
    agg = await repo.read_aggregate(user, project, date(2026, 6, 24))
    assert dict(agg.day_words)[date(2026, 6, 24)] == 200  # 5200-5000, NOT 5200
    assert agg.book_total == 5200


async def test_daily_progress_new_chapter_baselined_zero_counts_fully(pool):
    """A NEW chapter (opened at ~0 words → baseline 0): its first day counts FULLY."""
    repo = DailyProgressRepo(pool)
    user, project, _ = _ids()
    ch = uuid.uuid4()
    await repo.ensure_baseline(user, project, ch, 0)
    await repo.report(user, project, ch, 300, date(2026, 6, 24))
    agg = await repo.read_aggregate(user, project, date(2026, 6, 24))
    assert dict(agg.day_words)[date(2026, 6, 24)] == 300  # all 300 count
    assert agg.book_total == 300


async def test_daily_progress_baseline_is_insert_once(pool):
    """Re-opening a chapter must NOT reset the baseline (would erase progress)."""
    repo = DailyProgressRepo(pool)
    user, project, _ = _ids()
    ch = uuid.uuid4()
    await repo.ensure_baseline(user, project, ch, 1000)
    await repo.ensure_baseline(user, project, ch, 9999)  # later re-open — ignored
    await repo.report(user, project, ch, 1100, date(2026, 6, 24))
    agg = await repo.read_aggregate(user, project, date(2026, 6, 24))
    assert dict(agg.day_words)[date(2026, 6, 24)] == 100  # 1100-1000 (baseline stayed)


async def test_daily_progress_book_total_includes_unwritten_baseline(pool):
    """A chapter opened (baselined) but not yet written this window still counts
    toward the book total at its baseline value."""
    repo = DailyProgressRepo(pool)
    user, project, _ = _ids()
    ch_written, ch_opened = uuid.uuid4(), uuid.uuid4()
    await repo.ensure_baseline(user, project, ch_written, 2000)
    await repo.report(user, project, ch_written, 2100, date(2026, 6, 24))
    await repo.ensure_baseline(user, project, ch_opened, 500)  # opened, not written
    agg = await repo.read_aggregate(user, project, date(2026, 6, 24))
    assert agg.book_total == 2600  # 2100 (written latest) + 500 (opened baseline)


# ─────────────────────── style_profile / voice_profile (T3.5) ───────────────────────

async def test_style_profile_resolve_precedence(pool):
    """resolve() returns the MOST SPECIFIC scope: scene > chapter > work > None."""
    repo = StyleProfileRepo(pool)
    user, project, _ = _ids()
    scene, chapter = uuid.uuid4(), uuid.uuid4()
    await repo.upsert(user, project, "work", project, 50, 50)
    # only work set → resolve returns work
    r = await repo.resolve(user, project, scene, chapter)
    assert r is not None and r.scope_type == "work"
    # add chapter → chapter wins over work
    await repo.upsert(user, project, "chapter", chapter, 40, 60)
    r = await repo.resolve(user, project, scene, chapter)
    assert r.scope_type == "chapter" and r.density == 40
    # add scene → scene wins over chapter + work
    await repo.upsert(user, project, "scene", scene, 80, 20)
    r = await repo.resolve(user, project, scene, chapter)
    assert r.scope_type == "scene" and r.density == 80 and r.pace == 20
    # a DIFFERENT scene (no scene row) falls back to chapter
    other = await repo.resolve(user, project, uuid.uuid4(), chapter)
    assert other.scope_type == "chapter"


async def test_style_profile_upsert_replaces_and_delete_reverts(pool):
    repo = StyleProfileRepo(pool)
    user, project, _ = _ids()
    chapter = uuid.uuid4()
    await repo.upsert(user, project, "chapter", chapter, 30, 30)
    await repo.upsert(user, project, "chapter", chapter, 70, 70)  # replace in place
    rows = await repo.list_all(user, project)
    assert len(rows) == 1 and rows[0].density == 70
    assert await repo.delete(user, project, "chapter", chapter) is True
    assert await repo.list_all(user, project) == []
    # cross-user isolation
    assert await repo.resolve(uuid.uuid4(), project, None, chapter) is None


async def test_voice_profile_present_only_and_upsert(pool):
    """list_for_entities returns only the requested (present) entities; upsert replaces."""
    repo = VoiceProfileRepo(pool)
    user, project, _ = _ids()
    kael, mira, absent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await repo.upsert(user, project, kael, "Kael", ["terse", "understatement"])
    await repo.upsert(user, project, mira, "Mira", ["formal"])
    # only Kael present in the scene
    present = await repo.list_for_entities(user, project, [kael, absent])
    assert [v.entity_name for v in present] == ["Kael"]
    assert present[0].tags == ["terse", "understatement"]
    # upsert replaces tags in place (not a second row)
    await repo.upsert(user, project, kael, "Kael", ["wry"])
    again = await repo.list_for_entities(user, project, [kael])
    assert again[0].tags == ["wry"]
    # empty present set → no query, empty list
    assert await repo.list_for_entities(user, project, []) == []
    # cross-user isolation
    assert await repo.list_for_entities(uuid.uuid4(), project, [kael]) == []


async def test_voice_profile_list_all_and_delete(pool):
    repo = VoiceProfileRepo(pool)
    user, project, _ = _ids()
    e = uuid.uuid4()
    await repo.upsert(user, project, e, "Kael", ["terse"])
    assert len(await repo.list_all(user, project)) == 1
    assert await repo.delete(user, project, e) is True
    assert await repo.list_all(user, project) == []
