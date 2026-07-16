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
from app.db.repositories.plan_overlay import PlanOverlayRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.works import WorksRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # MANDATORY (CLAUDE.md test-parallelization): this file DROPs + re-migrates tables on
    # the shared dev PG. Without the group, xdist can schedule it on a different worker
    # concurrently with the other real-DB files and they interleave — the counts then lie.
    # It was missing; the other integration/db files (test_pack_arc_wired, test_c16_…) have it.
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "composition_daily_progress",
    "composition_progress_baseline",
    "style_profile",
    "voice_profile",
    "scene_grounding_pins",
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


def _ids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()  # user, project, book


async def _seed_work(pool, created_by, project_id, book_id=None):
    """Seed the composition_work row every re-keyed package INSERT derives its
    NOT-NULL book_id from (spec 25 M1/M2 — INSERT … SELECT w.book_id). Returns the
    created Work; book_id is a fresh id unless given (a distinct book per canonical
    Work avoids the one-canonical-Work-per-book partial unique
    uq_composition_work_book)."""
    return await WorksRepo(pool).create(created_by, project_id, book_id or uuid.uuid4())


# ───────────────────────── works ─────────────────────────

async def test_works_create_get_roundtrip(pool):
    repo = WorksRepo(pool)
    user, project, book = _ids()
    # 25 M3 / PM-5: the actor column is `created_by` (a plain stamp), NOT `user_id`;
    # reads key on project_id alone (no actor arg — access is the E0 book gate).
    w = await repo.create(user, project, book, settings={"voice": "wry"})
    assert w.project_id == project and w.created_by == user and w.book_id == book
    assert w.settings == {"voice": "wry"} and w.version == 1
    got = await repo.get(project)
    assert got is not None and got.settings == {"voice": "wry"}
    # cross-PROJECT isolation: a different project id resolves to None (the repo's
    # surviving scope is the Work partition; per-actor isolation moved to the gate).
    assert await repo.get(uuid.uuid4()) is None


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
    # findable via the backfill-seam read (keyed on book alone — PM-4)
    found = await repo.get_pending_for_book(book)
    assert found is not None and found.id == pend.id
    # cross-BOOK isolation: a different book has no pending row
    assert await repo.get_pending_for_book(uuid.uuid4()) is None
    # at most one pending per book — the partial-unique index rejects a 2nd
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await repo.create_pending(user, book)
    # backfill: stamp the project, clear the marker (idempotent — only still-pending).
    # `created_by` is the actor stamp (attribution only), keyword-only per the write law.
    new_pid = uuid.uuid4()
    bf = await repo.backfill_project(pend.id, new_pid, created_by=user)
    assert bf is not None and bf.project_id == new_pid
    assert bf.pending_project_backfill is False
    assert await repo.get_pending_for_book(book) is None  # no longer pending
    # second backfill no-ops (row no longer pending)
    assert await repo.backfill_project(pend.id, uuid.uuid4(), created_by=user) is None
    # the backfilled row is now a normal project-keyed Work
    got = await repo.get(new_pid)
    assert got is not None and got.id == pend.id


async def test_works_resolve_excludes_pending_until_backfilled(pool):
    # C16: a lazy null-project Work must NOT resolve as a finished `found` marked
    # Work — else a retry (knowledge recovered) returns the placeholder and never
    # backfills. resolve_by_book excludes pending rows; after backfill it appears.
    repo = WorksRepo(pool)
    user, _, book = _ids()
    pend = await repo.create_pending(user, book)
    assert await repo.resolve_by_book(book) == []  # excluded while pending
    new_pid = uuid.uuid4()
    await repo.backfill_project(pend.id, new_pid, created_by=user)
    marked = await repo.resolve_by_book(book)
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
    assert await repo.resolve_by_book(book) == []
    # found (1)
    p1 = uuid.uuid4()
    await repo.create(user, p1, book)
    res = await repo.resolve_by_book(book)
    assert len(res) == 1 and res[0].project_id == p1
    # candidates (2) — a derivative is N-per-book; a 2nd CANONICAL work would trip
    # uq_composition_work_book, so p2 is created as a derivative of p1's Work.
    p2 = uuid.uuid4()
    await repo.create_derivative(user, p2, book, res[0].id, branch_point=1)
    assert len(await repo.resolve_by_book(book)) == 2
    # archived work drops out of resolve
    await repo.update(p2, {"status": "archived"}, created_by=user)
    assert len(await repo.resolve_by_book(book)) == 1


async def test_works_ifmatch_bump_and_412(pool):
    repo = WorksRepo(pool)
    user, project, book = _ids()
    await repo.create(user, project, book)
    updated = await repo.update(project, {"settings": {"a": 1}}, created_by=user, expected_version=1)
    assert updated is not None and updated.version == 2 and updated.settings == {"a": 1}
    # stale version → 412 carrying current row
    with pytest.raises(VersionMismatchError) as ei:
        await repo.update(project, {"settings": {"a": 2}}, created_by=user, expected_version=1)
    assert ei.value.current.version == 2
    # missing row with expected_version → None (404), not 412
    assert await repo.update(uuid.uuid4(), {"settings": {}}, created_by=user, expected_version=1) is None


async def test_works_update_noop_preserves_version(pool):
    repo = WorksRepo(pool)
    user, project, book = _ids()
    await repo.create(user, project, book)
    # explicit None on a NOT-NULL field is skipped → empty effective patch
    same = await repo.update(project, {"status": None}, created_by=user)
    assert same is not None and same.version == 1


async def test_be18_settings_patch_shallow_merges_and_preserves_keys(pool):
    """BE-18: a partial settings PATCH must MERGE, not full-blob replace — a caller
    that sends only {scene_graph} must NOT wipe derivative_name (BE-13a) or any other
    key. Last-write-wins per top-level key."""
    repo = WorksRepo(pool)
    user, project, book = _ids()
    await repo.create(user, project, book, settings={"derivative_name": "Nếu Lam Vũ chết", "voice": "wry"})
    # a scene-graph drag sends ONLY {scene_graph}
    r1 = await repo.update(project, {"settings": {"scene_graph": {"positions": {"n1": {"x": 1, "y": 2}}}}}, created_by=user)
    assert r1 is not None
    assert r1.settings["derivative_name"] == "Nếu Lam Vũ chết"  # preserved, not wiped
    assert r1.settings["voice"] == "wry"                          # preserved
    assert r1.settings["scene_graph"] == {"positions": {"n1": {"x": 1, "y": 2}}}  # added
    # same top-level key on a later write REPLACES that key (last-write-wins), leaving siblings intact
    r2 = await repo.update(project, {"settings": {"voice": "dry"}}, created_by=user)
    assert r2 is not None and r2.settings["voice"] == "dry" and r2.settings["derivative_name"] == "Nếu Lam Vũ chết"


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
                "INSERT INTO composition_work (project_id, created_by, book_id, source_work_id) "
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
    fetched = await works.get_by_id(deriv.source_work_id)
    assert fetched is not None
    assert fetched.id == src.id
    assert fetched.project_id == src.project_id  # the BASE knowledge project
    # get_by_id is a bare-id read (no actor scope — access is gated before the repo);
    # a NONEXISTENT work id resolves to None.
    assert await works.get_by_id(uuid.uuid4()) is None


async def test_c23_divergence_spec_and_override_roundtrip(pool):
    """divergence_spec (canon_rule[] + pov_anchor) + entity_override (JSONB) persist
    and read back; the work_id FK + per-(work,target) unique hold."""
    works, drepo = WorksRepo(pool), DerivativesRepo(pool)
    user, _, book = _ids()
    src = await works.create(user, uuid.uuid4(), book)
    deriv = await works.create_derivative(user, uuid.uuid4(), book, src.id, branch_point=3)
    pov = uuid.uuid4()
    spec = await drepo.create_spec(DivergenceSpec(
        created_by=user, project_id=deriv.project_id, work_id=deriv.id,
        taxonomy="pov_shift", pov_anchor=pov, canon_rule=["The villain wins", "No magic"],
    ))
    assert spec.taxonomy == "pov_shift" and spec.pov_anchor == pov
    assert spec.canon_rule == ["The villain wins", "No magic"]
    got_spec = await drepo.get_spec_for_work(deriv.id)
    assert got_spec is not None and got_spec.id == spec.id

    target = uuid.uuid4()
    ov = await drepo.create_override(EntityOverride(
        created_by=user, project_id=deriv.project_id, work_id=deriv.id,
        target_entity_id=target, overridden_fields={"role": "antagonist", "alive": False},
    ))
    assert ov.overridden_fields == {"role": "antagonist", "alive": False}
    overrides = await drepo.list_overrides_for_work(deriv.id)
    assert len(overrides) == 1 and overrides[0].target_entity_id == target
    # bare work_id reads (access gated before the repo): a nonexistent work → empty
    assert await drepo.get_spec_for_work(uuid.uuid4()) is None
    assert await drepo.list_overrides_for_work(uuid.uuid4()) == []
    # per-(work,target) unique rejects a duplicate override
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await drepo.create_override(EntityOverride(
            created_by=user, project_id=deriv.project_id, work_id=deriv.id,
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
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    a = await repo.create_node(project, created_by=user, kind="arc", title="A")
    b = await repo.create_node(project, created_by=user, kind="arc", title="B")
    c = await repo.create_node(project, created_by=user, kind="arc", title="C")
    assert a.rank < b.rank < c.rank
    tree = await repo.list_tree(project)
    assert [n.title for n in tree] == ["A", "B", "C"]


async def test_outline_ifmatch_and_present_entities(pool):
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    node = await repo.create_node(
        project, created_by=user, kind="chapter", chapter_id=chapter,
        present_entity_ids=[uuid.uuid4()],
    )
    e2 = uuid.uuid4()
    upd = await repo.update_node(
        node.id, {"title": "T", "present_entity_ids": [e2]}, expected_version=1,
    )
    assert upd is not None and upd.version == 2 and upd.title == "T"
    assert upd.present_entity_ids == [e2]
    with pytest.raises(VersionMismatchError):
        await repo.update_node(node.id, {"title": "X"}, expected_version=1)


async def test_outline_archive_recurses_subtree(pool):
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await repo.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await repo.create_node(
        project, created_by=user, kind="chapter", parent_id=arc.id, chapter_id=chapter,
    )
    scene = await repo.create_node(
        project, created_by=user, kind="scene", parent_id=chap.id, chapter_id=chapter,
    )
    # a sibling arc (NOT under the archived one) must survive
    other = await repo.create_node(project, created_by=user, kind="arc", title="other")

    archived = await repo.archive_node(arc.id)
    assert archived is not None and archived.is_archived

    visible = {n.id for n in await repo.list_tree(project)}
    assert arc.id not in visible
    assert chap.id not in visible  # descendant archived too
    assert scene.id not in visible
    assert other.id in visible
    # archiving again → already archived → None
    assert await repo.archive_node(arc.id) is None


async def test_outline_restore_recurses_subtree(pool):
    """T1.1b restore = inverse of archive: un-archives the node + its archived
    descendants (the whole cascade comes back)."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await repo.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await repo.create_node(
        project, created_by=user, kind="chapter", parent_id=arc.id, chapter_id=chapter,
    )
    scene = await repo.create_node(
        project, created_by=user, kind="scene", parent_id=chap.id, chapter_id=chapter,
    )
    await repo.archive_node(arc.id)  # archives arc+chap+scene

    restored = await repo.restore_node(arc.id)
    assert restored is not None and restored.is_archived is False
    visible = {n.id for n in await repo.list_tree(project)}
    assert {arc.id, chap.id, scene.id} <= visible  # whole subtree back
    # restoring again → nothing archived → None
    assert await repo.restore_node(arc.id) is None


async def test_outline_reorder_within_siblings_renumbers_story_order(pool):
    """T1.1c: reordering a scene after a later sibling rewrites its rank AND renumbers the
    chapter's scene story_order to match (reading order).

    The positions stay on the ONE global axis — the chapter's slot plus the scene's index
    (chapter-major / scene-minor). They used to be renumbered to a chapter-LOCAL 0..n-1, which
    collided with every other chapter's scenes and destroyed the global order the packer's
    strictly-prior lenses and the canon windows key on."""
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE as S

    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await repo.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await repo.create_node(project, created_by=user, kind="chapter", parent_id=arc.id,
                                  chapter_id=chapter, story_order=4 * S)  # book chapter 4
    s1 = await repo.create_node(project, created_by=user, kind="scene", parent_id=chap.id, chapter_id=chapter, title="s1")
    s2 = await repo.create_node(project, created_by=user, kind="scene", parent_id=chap.id, chapter_id=chapter, title="s2")
    s3 = await repo.create_node(project, created_by=user, kind="scene", parent_id=chap.id, chapter_id=chapter, title="s3")

    # move s1 to AFTER s3 → new order s2, s3, s1
    moved = await repo.reorder_node(s1.id, new_parent_id=chap.id, after_id=s3.id)
    assert moved is not None
    scenes = await repo.scenes_for_chapter(project, chapter)  # ORDER BY story_order, rank
    assert [s.title for s in scenes] == ["s2", "s3", "s1"]
    # Chapter 4's band — NOT 0,1,2 (which would collide with every other chapter's scenes).
    assert [s.story_order for s in scenes] == [4 * S, 4 * S + 1, 4 * S + 2]


async def test_outline_reorder_reparents_scene_across_chapters(pool):
    """A scene dragged to another chapter inherits the new chapter's chapter_id and is renumbered
    into the DESTINATION chapter's band; the source chapter's remaining scenes re-densify inside
    ITS band. Both stay on the one global axis — the H5 Row-4 drag write path."""
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE as S

    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chA, chB = uuid.uuid4(), uuid.uuid4()
    arc = await repo.create_node(project, created_by=user, kind="arc", title="arc")
    cA = await repo.create_node(project, created_by=user, kind="chapter", parent_id=arc.id,
                                chapter_id=chA, story_order=1 * S)   # book chapter 1
    cB = await repo.create_node(project, created_by=user, kind="chapter", parent_id=arc.id,
                                chapter_id=chB, story_order=2 * S)   # book chapter 2
    a1 = await repo.create_node(project, created_by=user, kind="scene", parent_id=cA.id, chapter_id=chA, title="a1")
    a2 = await repo.create_node(project, created_by=user, kind="scene", parent_id=cA.id, chapter_id=chA, title="a2")
    b1 = await repo.create_node(project, created_by=user, kind="scene", parent_id=cB.id, chapter_id=chB, title="b1")

    moved = await repo.reorder_node(a1.id, new_parent_id=cB.id, after_id=b1.id)
    assert moved is not None
    assert moved.parent_id == cB.id and moved.chapter_id == chB  # inherited new chapter
    dest = await repo.scenes_for_chapter(project, chB)
    # The moved scene lands in chapter 2's band, after b1 — not on a chapter-local 0,1.
    assert [s.title for s in dest] == ["b1", "a1"]
    assert [s.story_order for s in dest] == [2 * S, 2 * S + 1]
    src = await repo.scenes_for_chapter(project, chA)
    assert [s.title for s in src] == ["a2"] and [s.story_order for s in src] == [1 * S]  # re-densified


async def test_outline_beat_role_allowed_on_scene_and_chapter_not_arc(pool):
    """T1.2 Beat Sheet migration: beat_role may live on a scene OR a chapter, but
    an arc (or beat) still violates outline_beatrole_kind."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await repo.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await repo.create_node(project, created_by=user, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    scene = await repo.create_node(project, created_by=user, kind="scene", parent_id=chap.id, chapter_id=chapter)

    s = await repo.update_node(scene.id, {"beat_role": "catalyst"})
    assert s is not None and s.beat_role == "catalyst"
    c = await repo.update_node(chap.id, {"beat_role": "opening_image"})  # NEW: chapter allowed
    assert c is not None and c.beat_role == "opening_image"
    # clearing works (nullable)
    cleared = await repo.update_node(chap.id, {"beat_role": None})
    assert cleared is not None and cleared.beat_role is None
    # an arc still cannot carry a beat_role
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await repo.update_node(arc.id, {"beat_role": "finale"})


async def test_outline_reorder_rejects_cycle(pool):
    """Reparenting a node under its own descendant is a 400 (ReferenceViolationError)
    — the same guard update_node uses, applied before any write."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await repo.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await repo.create_node(project, created_by=user, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    with pytest.raises(ReferenceViolationError):
        await repo.reorder_node(arc.id, new_parent_id=chap.id, after_id=None)


async def test_outline_restore_reconnects_archived_ancestors(pool):
    """Restoring a node whose ancestor is still archived must also un-archive the
    archived ancestor chain — else the restored node orphans out of the tree
    (its parent_id points at an archived, invisible row)."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await repo.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await repo.create_node(
        project, created_by=user, kind="chapter", parent_id=arc.id, chapter_id=chapter,
    )
    scene = await repo.create_node(
        project, created_by=user, kind="scene", parent_id=chap.id, chapter_id=chapter,
    )
    await repo.archive_node(arc.id)  # archives arc+chap+scene

    # restore only the SCENE → ancestor chain (chap, arc) restored too
    restored = await repo.restore_node(scene.id)
    assert restored is not None and restored.is_archived is False
    visible = {n.id for n in await repo.list_tree(project)}
    assert {arc.id, chap.id, scene.id} <= visible  # reconnected to a visible root


async def test_outline_archive_terminates_on_parent_cycle(pool):
    """FINDING-3 backstop: archive_node's recursive CTE must not loop forever on
    a stray parent cycle. The repo now BLOCKS reparent-cycles (see
    test_outline_reparent_cycle_blocked), so we forge the cycle via RAW SQL to
    still prove the UNION backstop. Without UNION this test hangs."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    a = await repo.create_node(project, created_by=user, kind="arc", title="a")
    b = await repo.create_node(project, created_by=user, kind="arc", parent_id=a.id, title="b")
    # forge a cycle a → b → a bypassing the repo guard
    async with pool.acquire() as c:
        await c.execute("UPDATE outline_node SET parent_id = $1 WHERE id = $2", b.id, a.id)
    archived = await repo.archive_node(a.id)
    assert archived is not None and archived.is_archived
    # both nodes in the cycle archived; query returned (did not hang)
    assert {n.id for n in await repo.list_tree(project)} == set()


def _chapters_payload(*chapter_ids, scenes_per=1):
    return [
        {"chapter_id": cid, "title": f"ch-{i}", "intent": "x",
         "scenes": [{"title": f"s{j}", "synopsis": "y"} for j in range(scenes_per)]}
        for i, cid in enumerate(chapter_ids)
    ]


async def _active_ids(pool, project, kind):
    # Package re-key: outline_node is project-partitioned; `created_by` is a plain
    # actor stamp, never a filter — so the read keys on project_id alone.
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT id FROM outline_node WHERE project_id=$1 "
            "AND kind=$2 AND NOT is_archived",
            project, kind,
        )
    return {r["id"] for r in rows}


async def _active_structure_arcs(pool, book):
    # 25 M4 lifted model: arcs are `structure_node` rows (kind='arc'), book-scoped —
    # NEVER `kind='arc'` outline_nodes anymore. Decompose/apply link chapters to them
    # via outline_node.structure_node_id.
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT id FROM structure_node WHERE book_id=$1 "
            "AND kind='arc' AND NOT is_archived",
            book,
        )
    return {r["id"] for r in rows}


async def test_decompose_creates_structure_node_arc_not_outline_arc(pool):
    """25 M4 legacy-close (the live 500): a decompose commit persists the arc as a
    `structure_node` (kind='arc'), NEVER a `kind='arc'` outline_node — the latter
    is CHECK-rejected on a lifted DB. Chapters LINK to the spec arc via
    `structure_node_id` with a NULL outline parent (so the arc lens resolves off
    that link, not an outline-arc container)."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chA = uuid.uuid4()
    r = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="Arc One",
        chapters=_chapters_payload(chA),
    )
    # NO outline_node arc was minted (the regression guard for the live bug).
    assert await _active_ids(pool, project, "arc") == set()
    # the arc is a structure_node, and result["arc_id"] is its id.
    assert await _active_structure_arcs(pool, book) == {uuid.UUID(r["arc_id"])}
    # the chapter links to the spec arc via structure_node_id, no outline parent.
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT parent_id, structure_node_id FROM outline_node WHERE id=$1",
            uuid.UUID(r["chapter_ids"][0]),
        )
    assert row["parent_id"] is None
    assert row["structure_node_id"] == uuid.UUID(r["arc_id"])


async def test_decompose_replace_archives_prior_arc_and_chapter_nodes(pool):
    """FD-17/069: a replace re-plan must soft-archive the prior arc + chapter
    nodes, not ONLY their scenes — else orphan arc/chapter nodes accumulate on
    every re-plan. Post-25-M4 the arc is a `structure_node` (not an outline
    `kind='arc'` node); the emptied prior spec arc is archived there."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chA = uuid.uuid4()
    r1 = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="v1", chapters=_chapters_payload(chA),
    )
    r2 = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="v2", chapters=_chapters_payload(chA), replace=True,
    )
    arcs = await _active_structure_arcs(pool, book)
    chaps = await _active_ids(pool, project, "chapter")
    scenes = await _active_ids(pool, project, "scene")
    # no outline_node arc is EVER minted (the lifted model).
    assert await _active_ids(pool, project, "arc") == set()
    # exactly the v2 tree is active — no orphan v1 arc/chapter/scene survives.
    assert arcs == {uuid.UUID(r2["arc_id"])}
    assert uuid.UUID(r1["arc_id"]) not in arcs
    assert chaps == {uuid.UUID(x) for x in r2["chapter_ids"]}
    assert scenes == {uuid.UUID(x) for x in r2["scene_ids"]}


async def test_decompose_partial_replace_preserves_arc_with_active_out_of_target_chapter(pool):
    """The childless-arc sweep must NOT archive a spec arc that still spans an
    active chapter OUTSIDE the replaced set (a partial re-plan) — only fully-
    emptied arcs are reaped."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chA, chB = uuid.uuid4(), uuid.uuid4()
    r1 = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="v1", chapters=_chapters_payload(chA, chB),
    )
    r2 = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="v2-chA", chapters=_chapters_payload(chA), replace=True,
    )
    arcs = await _active_structure_arcs(pool, book)
    # v1 arc SURVIVES (chB child still links to it) AND the new v2 arc exists.
    assert uuid.UUID(r1["arc_id"]) in arcs
    assert uuid.UUID(r2["arc_id"]) in arcs
    assert len(arcs) == 2
    chaps = await _active_ids(pool, project, "chapter")
    assert uuid.UUID(r1["chapter_ids"][0]) not in chaps   # chA prior chapter archived
    assert uuid.UUID(r1["chapter_ids"][1]) in chaps        # chB chapter preserved
    assert uuid.UUID(r2["chapter_ids"][0]) in chaps        # chA new chapter active


async def test_decompose_replace_does_not_archive_unrelated_empty_arc(pool):
    """/review-impl HIGH: the childless-arc sweep must be SCOPED to the arc(s)
    this replace orphans — a freshly-created, not-yet-populated bystander
    `structure_node` arc (no chapters linked) must SURVIVE a decompose replace
    elsewhere in the book, not be archived as collateral by a book-wide 'any
    childless arc' sweep."""
    from app.db.repositories.structure import StructureRepo
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    bystander = await StructureRepo(pool).create_node(
        book, created_by=user, kind="arc", title="manual-empty")
    chA = uuid.uuid4()
    await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="v1", chapters=_chapters_payload(chA),
    )
    await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="v2", chapters=_chapters_payload(chA), replace=True,
    )
    arcs = await _active_structure_arcs(pool, book)
    assert bystander.id in arcs   # the unrelated empty arc is NOT archived


async def test_plan_hub_h1_read_surfaces_live_sql(pool):
    """24 Phase H1 read surfaces — the LIVE SQL executes against the real (renamed,
    lifted) schema. The parallel-build agents wrote MOCKED unit tests only; this is
    the by-effect proof (mocked-client-hides-server-filters) for every new query:
    the structure-axis keyset children (partial-index predicate), the scene-axis
    book-keyed children + its tenancy double-filter, book-keyed scene-links, and
    every PlanOverlayRepo aggregate."""
    outline = OutlineRepo(pool)
    overlay = PlanOverlayRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chA, chB = uuid.uuid4(), uuid.uuid4()
    # commit_decomposed_tree creates a structure_node arc + chapters linked via
    # structure_node_id (the 25-M4 decompose fix) — exactly the Hub's arc axis.
    r = await outline.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="Arc I",
        chapters=_chapters_payload(chA, chB, scenes_per=2),
    )
    arc_id = uuid.UUID(r["arc_id"])

    # ── children, ARC axis: the chapters attached to the structure_node arc ──
    chapters = await outline.list_children_by_structure(book, arc_id, limit=100)
    assert {c.chapter_id for c in chapters} == {chA, chB}
    assert all(c.kind == "chapter" and c.structure_node_id == arc_id for c in chapters)
    # a structure_node_id under ANOTHER book leaks nothing (tenancy double-filter)
    assert await outline.list_children_by_structure(uuid.uuid4(), arc_id, limit=100) == []

    # ── children, CHAPTER axis: the scene children of a chapter node, book-keyed ──
    chapter_node_id = chapters[0].id
    scenes = await outline.list_children_by_parent_book(book, chapter_node_id, limit=100)
    assert len(scenes) == 2 and all(s.kind == "scene" for s in scenes)
    # a parent_id under ANOTHER book returns nothing (the double-filter, not "omitted → all")
    assert await outline.list_children_by_parent_book(uuid.uuid4(), chapter_node_id) == []

    # ── book-keyed scene-links list executes (empty — none seeded) ──
    assert await SceneLinksRepo(pool).list_by_book(book) == []

    # ── every plan-overlay aggregate executes against the real schema ──
    for fetch in (overlay.fetch_canon_anchors, overlay.fetch_open_threads,
                  overlay.fetch_structure_parents, overlay.fetch_tension_rollup,
                  overlay.fetch_motif_chips):
        assert isinstance(await fetch(book), list)


def _plan_node_names(plan: dict):
    """Flatten an EXPLAIN (FORMAT JSON) plan tree into (node_type, index_name?) tuples."""
    out = [(plan.get("Node Type"), plan.get("Index Name"))]
    for child in plan.get("Plans", []) or []:
        out.extend(_plan_node_names(child))
    return out


async def test_plan_hub_structure_axis_uses_keyset_index_at_scale(pool):
    """24 H8.1 — the PERF DoD: the ARC-axis children window
    (`list_children_by_structure`) must ride `idx_outline_node_structure_keyset`
    (an Index Scan giving order + the partial predicate), NEVER degrade to a
    Seq Scan + Sort, at a book-sized chapter count. This is the by-effect proof
    that the query repeats `AND kind='chapter' AND NOT is_archived` VERBATIM so the
    PARTIAL index matches (Postgres won't infer it from the CHECK — regression guard
    for postgres-partial-index-on-conflict-predicate-must-match on the READ side)."""
    actor = uuid.uuid4()
    book = uuid.uuid4()
    project = uuid.uuid4()
    arc = uuid.uuid4()          # the target arc
    other_arc = uuid.uuid4()    # a sibling arc — noise so a Seq Scan would read irrelevant rows

    async with pool.acquire() as c:
        for a in (arc, other_arc):
            await c.execute(
                "INSERT INTO structure_node (id, book_id, kind, rank, title) "
                "VALUES ($1, $2, 'arc', '00000001', 'Arc')",
                a, book,
            )
        # 4000 live chapters under the target arc + 3000 under a sibling arc + 400 archived
        # under the target (excluded by the partial predicate) → a Seq Scan would touch ~7400
        # rows and sort; the index reads the first LIMIT+1 in order and stops.
        seed = """
            INSERT INTO outline_node
              (created_by, project_id, book_id, kind, rank, chapter_id, structure_node_id,
               is_archived, title, status)
            SELECT $1, $2, $3, 'chapter', lpad(g::text, 8, '0'), gen_random_uuid(), $4,
                   $5, 'Ch '||g, 'outline'
            FROM generate_series(1, $6) g
        """
        await c.execute(seed, actor, project, book, arc, False, 4000)
        await c.execute(seed, actor, project, book, other_arc, False, 3000)
        await c.execute(seed, actor, project, book, arc, True, 400)
        await c.execute("ANALYZE outline_node")

        # A hand-copy of the query SHAPE list_children_by_structure builds (kept in sync with
        # outline.py). EXPLAIN proves the partial index is USABLE for this shape at scale; the real
        # builder is exercised separately below so predicate drift can't hide behind the copy.
        explain = await c.fetchval(
            """
            EXPLAIN (FORMAT JSON)
            SELECT id FROM outline_node
            WHERE structure_node_id = $1 AND book_id = $2
              AND kind = 'chapter' AND NOT is_archived
            ORDER BY rank COLLATE "C", id
            LIMIT 101
            """,
            arc, book,
        )

    plan = (json.loads(explain) if isinstance(explain, str) else explain)[0]["Plan"]
    nodes = _plan_node_names(plan)
    node_types = [n for n, _ in nodes]
    index_names = [idx for _, idx in nodes if idx]

    # The keyset index is used …
    assert "idx_outline_node_structure_keyset" in index_names, (
        f"structure-axis query did NOT use the keyset index; plan={nodes}"
    )
    # … and the plan neither Seq-Scans outline_node nor sorts (the index supplies order).
    assert "Seq Scan" not in node_types, f"unexpected Seq Scan; plan={nodes}"
    assert "Sort" not in node_types, f"unexpected Sort (index should supply order); plan={nodes}"

    # Exercise the REAL builder against the seeded schema — not just the inlined EXPLAIN copy — so
    # a future drop of the `kind='chapter' AND NOT is_archived` predicate surfaces as a wrong result
    # here, not only as a silent plan change in the hand-copy. Returns the first keyset page
    # (limit+1) of the 4000 LIVE chapters under the arc; the 400 archived + 3000 sibling-arc rows
    # must be excluded by the very predicate the EXPLAIN depends on.
    page = await OutlineRepo(pool).list_children_by_structure(book, arc, limit=100)
    assert len(page) == 101, f"expected the keyset page (limit+1), got {len(page)}"
    assert all(n.kind == "chapter" and n.structure_node_id == arc and not n.is_archived for n in page)
    # keyset order is (rank COLLATE "C", id) — the first page starts at the smallest rank.
    assert page[0].rank == "00000001"


async def _seed_derived_block_book(pool, orders: dict[str, list[int]]):
    """saga{arc1, arc2} + a top-level arc3, with each arc's chapters at the given story_orders.
    Returns (book, saga, arc1, arc2, arc3)."""
    from uuid import uuid4 as _u
    book, project = _u(), _u()
    saga, arc1, arc2, arc3 = _u(), _u(), _u(), _u()
    async with pool.acquire() as c:
        await c.execute("INSERT INTO structure_node (id, book_id, kind, rank, title) "
                        "VALUES ($1,$2,'saga','m','Saga')", saga, book)
        for a, r in ((arc1, 'a'), (arc2, 'b')):
            await c.execute("INSERT INTO structure_node (id, book_id, parent_id, kind, rank, title) "
                            "VALUES ($1,$2,$3,'arc',$4,'Arc')", a, book, saga, r)
        await c.execute("INSERT INTO structure_node (id, book_id, kind, rank, title) "
                        "VALUES ($1,$2,'arc','z','Arc3')", arc3, book)
        for key, arc in (("arc1", arc1), ("arc2", arc2), ("arc3", arc3)):
            for i, so in enumerate(orders[key]):
                await c.execute(
                    "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, "
                    "chapter_id, structure_node_id, story_order) "
                    "VALUES ($1,$2,$3,'chapter',$4,gen_random_uuid(),$5,$6)",
                    uuid.uuid4(), project, book, f"{i:04d}", arc, so,
                )
    return book, saga, arc1, arc2, arc3


async def test_structure_derived_blocks_rollup_and_contiguity(pool):
    """24 PH9/OQ-2/BA6 — StructureRepo.derived_blocks returns, per node in ONE query, the span +
    chapter_count + is_contiguous rolled up over the node's SUBTREE. Read surface #1 (the Hub arc
    shell). A live smoke caught the missing derived block (the route shipped raw structure_node
    rows), so this locks the shape by effect.

    BA6 non-contiguity means ANOTHER ARC'S CHAPTERS INTERLEAVE — a hole in the lane — not merely a
    gap in the raw numbers. So the block reports POSITIONS in the book's reading order (1..N), and
    a lane is contiguous iff its chapters occupy a consecutive run of those positions.

    Fixture: arc1 = book chapters 1,2 · arc3 = 3 · arc2 = 4,5. arc3's chapter splits the saga.
    """
    from app.db.repositories.structure import StructureRepo

    book, saga, arc1, arc2, arc3 = await _seed_derived_block_book(
        pool, {"arc1": [1, 2], "arc3": [3], "arc2": [4, 5]},
    )
    blocks = await StructureRepo(pool).derived_blocks(book)

    # On a DENSE fixture the reading POSITION and the RAW order coincide, so first_story_order
    # equals the span start. The strided test below is what pulls the two units apart.
    assert blocks[arc1] == {"span": {"from_order": 1, "to_order": 2}, "first_story_order": 1,
                            "is_contiguous": True, "chapter_count": 2}
    assert blocks[arc2] == {"span": {"from_order": 4, "to_order": 5}, "first_story_order": 4,
                            "is_contiguous": True, "chapter_count": 2}
    assert blocks[arc3] == {"span": {"from_order": 3, "to_order": 3}, "first_story_order": 3,
                            "is_contiguous": True, "chapter_count": 1}
    # The saga rolls up arc1+arc2 = positions 1,2,4,5 — arc3's chapter 3 sits INSIDE that span but
    # outside the saga ⇒ a real hole in the saga's lane ⇒ non-contiguous.
    assert blocks[saga] == {"span": {"from_order": 1, "to_order": 5}, "first_story_order": 1,
                            "is_contiguous": False, "chapter_count": 4}


async def test_structure_derived_blocks_are_axis_agnostic_on_the_strided_reading_order(pool):
    """The SAME book, on the STRIDED axis production actually writes (`chapter_sort * 1000`, the
    packer axis a chapter shares with its scenes and with the canon-rule windows).

    Raw min/max arithmetic would read arc1's two chapters as spanning 1000..2000 and conclude
    `max-min+1 (1001) != count (2)` ⇒ non-contiguous — i.e. EVERY arc of every real book would carry
    the BA6 warn chip, and every lane would render segmented. Reporting POSITIONS instead makes the
    block identical to the dense fixture above, for any monotonic axis.
    """
    from app.db.repositories.structure import StructureRepo
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE as S

    book, saga, arc1, arc2, arc3 = await _seed_derived_block_book(
        pool, {"arc1": [1 * S, 2 * S], "arc3": [3 * S], "arc2": [4 * S, 5 * S]},
    )
    blocks = await StructureRepo(pool).derived_blocks(book)

    # The SPAN is byte-for-byte the same as the dense fixture — it reads as the ORDINAL a human means
    # ("chapters 1–2"), never the raw strided number. But `first_story_order` stays on the RAW axis:
    # it is the SORT key the client places a collapsed arc's rollup by, and it has to be in the same
    # units as the chapter rows it interleaves with. Two units ⇒ two fields.
    assert blocks[arc1] == {"span": {"from_order": 1, "to_order": 2}, "first_story_order": 1 * S,
                            "is_contiguous": True, "chapter_count": 2}
    assert blocks[arc2] == {"span": {"from_order": 4, "to_order": 5}, "first_story_order": 4 * S,
                            "is_contiguous": True, "chapter_count": 2}
    assert blocks[saga] == {"span": {"from_order": 1, "to_order": 5}, "first_story_order": 1 * S,
                            "is_contiguous": False, "chapter_count": 4}


async def test_structure_derived_blocks_unordered_chapter_blocks_contiguity(pool):
    """A member chapter with NO story_order (position unknown) ⇒ contiguity is UNPROVABLE, so it
    reports False rather than quietly assuming the chapter sits at the end (absent ≠ zero)."""
    from app.db.repositories.structure import StructureRepo

    book, _saga, arc1, _arc2, _arc3 = await _seed_derived_block_book(
        pool, {"arc1": [1, 2], "arc3": [3], "arc2": [4, 5]},
    )
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, chapter_id, "
            "structure_node_id, story_order) "
            "VALUES ($1,$2,$3,'chapter','zzz',gen_random_uuid(),$4,NULL)",
            uuid.uuid4(), uuid.uuid4(), book, arc1,
        )
    blocks = await StructureRepo(pool).derived_blocks(book)
    assert blocks[arc1]["chapter_count"] == 3          # it IS a member
    assert blocks[arc1]["is_contiguous"] is False      # but its position is unknown
    assert blocks[arc1]["span"] == {"from_order": 1, "to_order": 2}  # span over what IS known


async def test_outline_reparent_guards(pool):
    """D-COMP-M2-XREF-OWNERSHIP: update_node blocks self-parent, cross-PROJECT
    parent, and descendant (cycle) reparents; a valid reparent succeeds."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    a = await repo.create_node(project, created_by=user, kind="arc", title="a")
    b = await repo.create_node(project, created_by=user, kind="arc", parent_id=a.id, title="b")
    c_node = await repo.create_node(project, created_by=user, kind="arc", title="c")

    # self-parent
    with pytest.raises(ReferenceViolationError):
        await repo.update_node(a.id, {"parent_id": a.id})
    # cycle: parent a under its descendant b
    with pytest.raises(ReferenceViolationError):
        await repo.update_node(a.id, {"parent_id": b.id})
    # cross-PROJECT parent (a node in a different Work partition) — the scope guard
    # rejects it (the parent exists but is in another project).
    other_user, other_proj, _ = _ids()
    await _seed_work(pool, other_user, other_proj)
    foreign = await repo.create_node(other_proj, created_by=other_user, kind="arc")
    with pytest.raises(ReferenceViolationError):
        await repo.update_node(c_node.id, {"parent_id": foreign.id})
    # valid reparent: move c under a (not a descendant of c)
    moved = await repo.update_node(c_node.id, {"parent_id": a.id})
    assert moved is not None and moved.parent_id == a.id
    # clearing the parent (→ top-level) is always allowed
    cleared = await repo.update_node(c_node.id, {"parent_id": None})
    assert cleared is not None and cleared.parent_id is None


async def test_outline_create_rejects_cross_scope_parent(pool):
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    other_user, other_proj, _ = _ids()
    await _seed_work(pool, other_user, other_proj)
    foreign = await repo.create_node(other_proj, created_by=other_user, kind="arc")
    # parent in a different project (Work partition) → rejected
    with pytest.raises(ReferenceViolationError):
        await repo.create_node(project, created_by=user, kind="arc", parent_id=foreign.id)
    # parent stamped by the same actor but in a DIFFERENT project → rejected
    mine_other_project = uuid.uuid4()
    await _seed_work(pool, user, mine_other_project)
    mine_other = await repo.create_node(mine_other_project, created_by=user, kind="arc")
    with pytest.raises(ReferenceViolationError):
        await repo.create_node(project, created_by=user, kind="arc", parent_id=mine_other.id)


async def test_outline_rank_orders_under_db_collation(pool):
    """FINDING-2: ranks must order by byte value even though the DB default
    collation is en_US.UTF-8. Insert many siblings and confirm list_tree
    (ORDER BY rank COLLATE "C") matches creation order."""
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    titles = [f"n{i:02d}" for i in range(20)]
    for t in titles:
        await repo.create_node(project, created_by=user, kind="arc", title=t)
    tree = await repo.list_tree(project)
    assert [n.title for n in tree] == titles
    # ranks are strictly ascending under byte (C) comparison
    ranks = [n.rank for n in tree]
    assert ranks == sorted(ranks)


async def test_outline_missing_node_returns_none(pool):
    # NEW-LAW rewrite of the old per-actor isolation test: get_node / archive_node
    # are bare-id reads (no actor scope — access is decided at the E0 book gate
    # BEFORE the repo), so a NONEXISTENT node id resolves to None / no-op.
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    await repo.create_node(project, created_by=user, kind="arc")
    assert await repo.get_node(uuid.uuid4()) is None
    assert await repo.archive_node(uuid.uuid4()) is None


# ───────────────────────── scene_links ─────────────────────────

async def test_scene_links_crud_and_isolation(pool):
    olr = OutlineRepo(pool)
    slr = SceneLinksRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    s1 = await olr.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    s2 = await olr.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    link = await slr.create(project, s1.id, s2.id, created_by=user, label="setup→payoff")
    assert link.from_node_id == s1.id and link.to_node_id == s2.id
    assert len(await slr.list_by_project(project)) == 1
    # cross-PROJECT delete is a no-op (an edge in another Work can't be deleted here)
    assert await slr.delete(uuid.uuid4(), link.id) is False
    assert await slr.delete(project, link.id) is True
    assert await slr.list_by_project(project) == []


async def test_scene_link_rejects_foreign_endpoint(pool):
    """D-COMP-M2-XREF-OWNERSHIP: a link endpoint that isn't the caller's node in
    this project is rejected (FK proves existence, not ownership)."""
    olr = OutlineRepo(pool)
    slr = SceneLinksRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    mine = await olr.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    other_user, other_proj, _ = _ids()
    await _seed_work(pool, other_user, other_proj)
    foreign = await olr.create_node(other_proj, created_by=other_user, kind="scene", chapter_id=chapter)
    with pytest.raises(ReferenceViolationError):
        await slr.create(project, mine.id, foreign.id, created_by=user)
    # a node in another project is also rejected (endpoint scope guard)
    mine_other_project = uuid.uuid4()
    await _seed_work(pool, user, mine_other_project)
    mine_other = await olr.create_node(mine_other_project, created_by=user, kind="scene", chapter_id=chapter)
    with pytest.raises(ReferenceViolationError):
        await slr.create(project, mine.id, mine_other.id, created_by=user)


async def test_generation_job_rejects_foreign_node(pool):
    olr = OutlineRepo(pool)
    gjr = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    other_user, other_proj, _ = _ids()
    await _seed_work(pool, other_user, other_proj)
    foreign = await olr.create_node(other_proj, created_by=other_user, kind="scene", chapter_id=uuid.uuid4())
    with pytest.raises(ReferenceViolationError):
        await gjr.create(project, created_by=user, operation="draft_scene", outline_node_id=foreign.id)


async def test_scene_drafts_detailed_returns_node_id_and_order(pool):
    """S5-B4 — scene_drafts_detailed carries node_id + story_order (so a caller can
    correspond scenes across a dị bản vs its source), latest draft per node, ordered."""
    olr = OutlineRepo(pool)
    gjr = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    s1 = await olr.create_node(project, created_by=user, kind="scene", chapter_id=chapter, title="s1", story_order=0)
    s2 = await olr.create_node(project, created_by=user, kind="scene", chapter_id=chapter, title="s2", story_order=1)
    await gjr.upsert_promoted_scene_prose(project, s1.id, "prose one", created_by=user)
    await gjr.upsert_promoted_scene_prose(project, s2.id, "prose two", created_by=user)
    # a re-promote overwrites (latest per node, not a duplicate)
    await gjr.upsert_promoted_scene_prose(project, s1.id, "prose one v2", created_by=user)
    out = await gjr.scene_drafts_detailed(project, chapter)
    assert [(o["node_id"], o["title"], o["text"]) for o in out] == [
        (str(s1.id), "s1", "prose one v2"),
        (str(s2.id), "s2", "prose two"),
    ]
    assert all(isinstance(o["story_order"], int) for o in out)
    # scoped to the chapter — a different chapter sees nothing
    assert await gjr.scene_drafts_detailed(project, uuid.uuid4()) == []


# ───────────────────────── canon_rules ─────────────────────────

async def test_canon_rules_active_listing_and_archive(pool):
    repo = CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r1 = await repo.create(project, "King is secretly dead", created_by=user, scope="reveal_gate")
    r2 = await repo.create(project, "Magic costs blood", created_by=user)
    # deactivate r2 → not in list_active, still in list_all
    await repo.update(project, r2.id, {"active": False})
    active = await repo.list_active(project)
    assert [r.id for r in active] == [r1.id]
    assert len(await repo.list_all(project)) == 2
    # archive r1 → out of both
    assert (await repo.archive(project, r1.id)) is not None
    assert await repo.list_active(project) == []
    assert len(await repo.list_all(project)) == 1
    assert await repo.archive(project, r1.id) is None  # already archived


async def test_canon_rule_restore_roundtrip(pool):
    """BE-11 — restore is archive()'s inverse: the rule comes back into list_all."""
    repo = CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r = await repo.create(project, "Magic costs blood", created_by=user)

    assert (await repo.archive(project, r.id)) is not None
    assert len(await repo.list_all(project)) == 0  # archived ⇒ unlistable

    restored = await repo.restore(project, r.id)
    assert restored is not None and restored.id == r.id
    assert [x.id for x in await repo.list_all(project)] == [r.id]

    # A second restore is a no-op miss (it is no longer archived) — not an error, not a lie.
    assert await repo.restore(project, r.id) is None
    # And a rule that was never archived cannot be "restored".
    other = await repo.create(project, "never deleted", created_by=user)
    assert await repo.restore(project, other.id) is None


async def test_canon_rule_restore_does_not_bump_version_and_does_not_flip_active(pool):
    """🔴 THE TWO SILENT-CORRUPTION BUGS. Restore un-archives ONLY.

    · Bumping `version` would silently invalidate a client's held If-Match.
    · Flipping `active` would silently RE-ARM a rule the author deliberately disabled —
      it would start constraining generation again without anyone asking."""
    repo = CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r = await repo.create(project, "Magic costs blood", created_by=user)
    # deactivate, THEN delete — the rule was inactive at the moment of deletion.
    await repo.update(project, r.id, {"active": False})
    before = await repo.get(project, r.id)
    assert before.active is False

    await repo.archive(project, r.id)
    restored = await repo.restore(project, r.id)

    assert restored.active is False, "restore must NOT re-arm a deliberately disabled rule"
    assert restored.version == before.version, "restore must NOT bump version"
    assert restored.is_archived is False


async def test_canon_rules_ifmatch(pool):
    repo = CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r = await repo.create(project, "rule", created_by=user)
    upd = await repo.update(project, r.id, {"text": "rule v2"}, expected_version=1)
    assert upd is not None and upd.version == 2
    with pytest.raises(VersionMismatchError):
        await repo.update(project, r.id, {"text": "x"}, expected_version=1)


# ───────────────────────── grounding_pins (T3.4) ─────────────────────────

async def test_grounding_pins_upsert_flip_clear_and_tenancy(pool):
    repo = GroundingPinsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    # outline_node_id is an in-DB FK (ON DELETE CASCADE) → create a real scene.
    scene = await olr.create_node(project, created_by=user, kind="scene", chapter_id=uuid.uuid4())
    # pin a lore source + exclude a cast entity
    p1 = await repo.set_action(project, scene.id, "lore", "src-1", "pin", created_by=user)
    assert p1.action == "pin" and p1.item_type == "lore" and p1.item_id == "src-1"
    await repo.set_action(project, scene.id, "present", "ent-1", "exclude", created_by=user)
    rows = await repo.list_for_scene(project, scene.id)
    assert {(r.item_type, r.item_id, r.action) for r in rows} == {
        ("lore", "src-1", "pin"), ("present", "ent-1", "exclude"),
    }
    # flip the lore pin → exclude IN PLACE (still one row for that item)
    flipped = await repo.set_action(project, scene.id, "lore", "src-1", "exclude", created_by=user)
    assert flipped.action == "exclude"
    rows = await repo.list_for_scene(project, scene.id)
    assert len(rows) == 2  # no duplicate row for src-1
    assert next(r for r in rows if r.item_id == "src-1").action == "exclude"
    # clear → row gone; a second clear is a no-op (False)
    assert await repo.clear(project, scene.id, "lore", "src-1") is True
    assert await repo.clear(project, scene.id, "lore", "src-1") is False
    assert len(await repo.list_for_scene(project, scene.id)) == 1
    # cross-PROJECT scoping — a different project sees nothing for this scene
    assert await repo.list_for_scene(uuid.uuid4(), scene.id) == []


async def test_grounding_pins_cascade_on_scene_delete(pool):
    repo = GroundingPinsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    scene = await olr.create_node(project, created_by=user, kind="scene", chapter_id=uuid.uuid4())
    await repo.set_action(project, scene.id, "canon", str(uuid.uuid4()), "pin", created_by=user)
    assert len(await repo.list_for_scene(project, scene.id)) == 1
    # deleting the scene CASCADE-drops its pins (no orphan rows)
    async with pool.acquire() as c:
        await c.execute("DELETE FROM outline_node WHERE id = $1", scene.id)
    assert await repo.list_for_scene(project, scene.id) == []


# ───────────────────────── generation_jobs ─────────────────────────

async def test_generation_job_idempotency_replay(pool):
    repo = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    job1, created1 = await repo.create(
        project, created_by=user, operation="draft_scene", idempotency_key="k1",
    )
    assert created1 is True
    job2, created2 = await repo.create(
        project, created_by=user, operation="draft_scene", idempotency_key="k1",
    )
    assert created2 is False and job2.id == job1.id  # replay returns same job
    # no key → always a fresh row
    j3, c3 = await repo.create(project, created_by=user, operation="continue")
    j4, c4 = await repo.create(project, created_by=user, operation="continue")
    assert c3 and c4 and j3.id != j4.id


async def test_generation_job_status_update_coalesces(pool):
    repo = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    # outline_node_id is an in-DB FK → create a real node to point at.
    node = await olr.create_node(project, created_by=user, kind="scene", chapter_id=uuid.uuid4())
    node_id = node.id
    job, _ = await repo.create(
        project, created_by=user, operation="draft_scene", outline_node_id=node_id,
        input={"prompt": "hi"},
    )
    assert len(await repo.list_active_for_node(project, node_id)) == 1
    # set result + run
    await repo.update_status(job.id, "running", result={"text": "draft"})
    # later set critic WITHOUT clobbering result
    done = await repo.update_status(
        job.id, "completed", critic={"coherence": 4},
        target_revision_id=uuid.uuid4(),
    )
    assert done is not None
    assert done.result == {"text": "draft"} and done.critic == {"coherence": 4}
    assert done.status == "completed"
    assert await repo.list_active_for_node(project, node_id) == []


# ── M3 (WS-B3): promoted scene-prose synthetic-job store ──

async def test_promoted_scene_prose_persists_and_reads_back(pool):
    # A promoted scene's prose is written as a synthetic completed job and READS
    # BACK through chapter_scene_drafts / prior_scene_drafts (the existing readers),
    # with NO new table — the M3 contract's core requirement.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await olr.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await olr.create_node(project, created_by=user, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    s1 = await olr.create_node(project, created_by=user, kind="scene", parent_id=chap.id,
                               chapter_id=chapter, story_order=1, title="s1")
    s2 = await olr.create_node(project, created_by=user, kind="scene", parent_id=chap.id,
                               chapter_id=chapter, story_order=2, title="s2")
    job1, v1 = await gjr.upsert_promoted_scene_prose(project, s1.id, "scene one prose", created_by=user)
    job2, v2 = await gjr.upsert_promoted_scene_prose(project, s2.id, "scene two prose", created_by=user)
    assert v1 == 1 and v2 == 1
    assert job1.status == "completed" and job1.result == {"text": "scene one prose"}
    assert job1.input.get("kind") == "promoted_scene_prose"
    # chapter_scene_drafts reads EVERY scene's promoted prose in story_order
    # (F4: as {title, text} rows so the stitch can prepend scene headings)
    drafts = await gjr.chapter_scene_drafts(project, chapter)
    assert drafts == [{"title": "s1", "text": "scene one prose"},
                      {"title": "s2", "text": "scene two prose"}]
    # prior_scene_drafts is position-bounded (strictly before story_order=2 → only s1)
    prior = await gjr.prior_scene_drafts(project, chapter, 2)
    assert prior == ["scene one prose"]


async def test_promoted_scene_prose_idempotent_overwrite_never_duplicates(pool):
    # A re-promote / double-submit OVERWRITES the same scene's prose (one row), never
    # duplicates; the version increments and the read-back reflects the latest text.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    arc = await olr.create_node(project, created_by=user, kind="arc", title="arc")
    chap = await olr.create_node(project, created_by=user, kind="chapter", parent_id=arc.id, chapter_id=chapter)
    scene = await olr.create_node(project, created_by=user, kind="scene", parent_id=chap.id,
                                  chapter_id=chapter, story_order=1, title="s1")
    _, v1 = await gjr.upsert_promoted_scene_prose(project, scene.id, "first take", created_by=user)
    _, v2 = await gjr.upsert_promoted_scene_prose(project, scene.id, "second take", created_by=user)
    assert v1 == 1 and v2 == 2
    # exactly ONE promoted-prose row for the node (overwrite, not duplicate)
    async with pool.acquire() as c:
        n = await c.fetchval(
            "SELECT count(*) FROM generation_job "
            "WHERE outline_node_id=$1 AND input->>'kind'='promoted_scene_prose'", scene.id)
    assert n == 1
    # read-back is the latest take
    drafts = await gjr.chapter_scene_drafts(project, chapter)
    assert drafts == [{"title": "s1", "text": "second take"}]


async def test_promoted_scene_prose_rejects_foreign_or_non_scene_node(pool):
    # Defense-in-depth: the node must be the caller's SCENE in this project.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    other_user, other_proj, _ = _ids()
    await _seed_work(pool, other_user, other_proj)
    # foreign scene (another project)
    foreign = await olr.create_node(other_proj, created_by=other_user, kind="scene", chapter_id=uuid.uuid4())
    with pytest.raises(ReferenceViolationError):
        await gjr.upsert_promoted_scene_prose(project, foreign.id, "x", created_by=user)
    # a non-scene node (a chapter) in this project is rejected too
    chap = await olr.create_node(project, created_by=user, kind="chapter", chapter_id=uuid.uuid4())
    with pytest.raises(ReferenceViolationError):
        await gjr.upsert_promoted_scene_prose(project, chap.id, "x", created_by=user)


async def test_promoted_scene_prose_scoped_per_project(pool):
    # Two derivatives (distinct project_ids) promoting the SAME node id keep separate
    # rows — the dedup unit is (project, node), so they never clobber each other.
    gjr = GenerationJobsRepo(pool)
    olr = OutlineRepo(pool)
    user, projA, _ = _ids()
    _, projB, _ = _ids()
    await _seed_work(pool, user, projA)
    await _seed_work(pool, user, projB)
    chapter = uuid.uuid4()
    sA = await olr.create_node(projA, created_by=user, kind="scene", chapter_id=chapter, story_order=1)
    sB = await olr.create_node(projB, created_by=user, kind="scene", chapter_id=chapter, story_order=1)
    await gjr.upsert_promoted_scene_prose(projA, sA.id, "A prose", created_by=user)
    await gjr.upsert_promoted_scene_prose(projB, sB.id, "B prose", created_by=user)
    # an untitled scene coalesces to title:"" (the stitch skips the heading for it)
    assert await gjr.chapter_scene_drafts(projA, chapter) == [{"title": "", "text": "A prose"}]
    assert await gjr.chapter_scene_drafts(projB, chapter) == [{"title": "", "text": "B prose"}]


async def _insert_stale_job(pool, created_by, project, book, *, chapter_id=None) -> uuid.UUID:
    """Insert a `running` job created 1h ago (a crash-orphan). Optional chapter_id
    in input makes it a chapter-level node-less job for the opportunistic-reap test.
    Package re-key: the actor column is `created_by`; book_id is NOT NULL (no FK — a
    plain id supplied here, mirroring the in-SQL derivation the repo does)."""
    inp = {"chapter_id": str(chapter_id)} if chapter_id else {}
    async with pool.acquire() as c:
        return await c.fetchval(
            """INSERT INTO generation_job
                 (created_by, project_id, book_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,$3,'draft_chapter','auto','running',$4::jsonb, now() - interval '1 hour')
               RETURNING id""",
            created_by, project, book, json.dumps(inp))


async def test_reap_stale_jobs_marks_stale_failed_leaves_fresh(pool):
    # D-COMP-CHAPTER-INFLIGHT-REAPER sweep: jobs orphaned in `running` past the
    # cutoff are marked failed; a fresh one is untouched.
    repo = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    stale = [await _insert_stale_job(pool, user, project, book) for _ in range(2)]
    fresh, _ = await repo.create(project, created_by=user, operation="draft_chapter", status="running")
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
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    async with pool.acquire() as c:
        worker_by_op = await c.fetchval(
            """INSERT INTO generation_job (created_by, project_id, book_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,$3,'stitch_chapter','auto','running','{}'::jsonb, now() - interval '1 hour')
               RETURNING id""", user, project, book)
        worker_by_input = await c.fetchval(
            """INSERT INTO generation_job (created_by, project_id, book_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,$3,'draft_scene','auto','running',$4::jsonb, now() - interval '1 hour')
               RETURNING id""", user, project, book, json.dumps({"worker_op": "generate"}))
        inline = await c.fetchval(
            """INSERT INTO generation_job (created_by, project_id, book_id, operation, mode, status, input, created_at)
               VALUES ($1,$2,$3,'draft_chapter','auto','running','{}'::jsonb, now() - interval '1 hour')
               RETURNING id""", user, project, book)

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
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    stale = await _insert_stale_job(pool, user, project, book, chapter_id=chapter)
    job, created = await repo.create_chapter_job_guarded(
        project, chapter, created_by=user, operation="draft_chapter",
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

    # rollback path: the event vanishes with the aborted txn. A DISTINCT book — the
    # one-canonical-Work-per-book partial unique (uq_composition_work_book) rejects a
    # second active canonical Work under `book`, so p2 gets its own book.
    p2, book2 = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(RuntimeError):
        async with pool.acquire() as conn:
            async with conn.transaction():
                await works.create(user, p2, book2, conn=conn)
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
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    scene = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter, title="S1")

    # drafting → done: exactly one scene_committed event, with the right payload
    done = await repo.update_node_commit_aware(scene.id, {"status": "done"})
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
    await repo.update_node_commit_aware(scene.id, {"status": "done"})
    assert await _scene_committed_count(pool, project) == 1


async def test_non_scene_done_emits_no_event(pool):
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = await repo.create_node(project, created_by=user, kind="chapter", chapter_id=uuid.uuid4())
    await repo.update_node_commit_aware(chapter.id, {"status": "done"})
    assert await _scene_committed_count(pool, project) == 0


async def test_scene_commit_rolls_back_event_on_version_conflict(pool):
    # a stale If-Match raises VersionMismatchError from inside the txn → the
    # status write AND any event roll back together (no orphan telemetry).
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    scene = await repo.create_node(project, created_by=user, kind="scene", chapter_id=uuid.uuid4())
    with pytest.raises(VersionMismatchError):
        await repo.update_node_commit_aware(scene.id, {"status": "done"}, expected_version=99)
    assert await _scene_committed_count(pool, project) == 0
    # the scene status was NOT advanced
    still = await repo.get_node(scene.id)
    assert still is not None and still.status != "done"


async def test_chapter_scene_gate_counts_and_can_publish(pool):
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    other_chapter = uuid.uuid4()
    s1 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    s2 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    # a scene in a DIFFERENT chapter must not count
    await repo.create_node(project, created_by=user, kind="scene", chapter_id=other_chapter, status="done")

    # zero done → blocked
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate == {"chapter_id": str(chapter), "scenes_total": 2, "scenes_done": 0,
                    "canon_blocked": False, "canon_unresolved_scenes": 0,
                    "canon_unchecked_scenes": 0, "can_publish": False}

    # one done → still blocked
    await repo.update_node_commit_aware(s1.id, {"status": "done"})
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["scenes_done"] == 1 and gate["can_publish"] is False

    # all done → publishable
    await repo.update_node_commit_aware(s2.id, {"status": "done"})
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["scenes_total"] == 2 and gate["scenes_done"] == 2 and gate["can_publish"] is True

    # an archived scene drops out of the count
    await repo.archive_node(s2.id)
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["scenes_total"] == 1 and gate["can_publish"] is True


async def test_chapter_scene_gate_zero_scenes_blocks(pool):
    repo = OutlineRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    gate = await repo.chapter_scene_gate(project, uuid.uuid4())
    assert gate["scenes_total"] == 0 and gate["can_publish"] is False


async def test_chapter_scene_gate_blocks_on_unresolved_canon(pool):
    """D-A2S3B-PUBLISH-GATE — an all-scenes-done chapter is still blocked when a
    scene's LATEST completed auto job left a confirmed canon contradiction
    (result.canon.resolved == false); a newer resolved job supersedes it."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    s1 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    await repo.update_node_commit_aware(s1.id, {"status": "done"})  # all done

    # baseline: no jobs → not canon-blocked → publishable.
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["can_publish"] is True and gate["canon_blocked"] is False

    # latest completed auto job left an UNRESOLVED canon contradiction → blocked.
    j1, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j1.id, "completed",
                             result={"text": "x", "canon": {"resolved": False,
                                                            "violations": [{"entity_id": "e"}]}})
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["scenes_done"] == 1
    assert gate["canon_blocked"] is True and gate["canon_unresolved_scenes"] == 1
    assert gate["can_publish"] is False

    # a NEWER resolved job for the same scene supersedes (DISTINCT ON latest).
    j2, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j2.id, "completed",
                             result={"text": "y", "canon": {"resolved": True}})
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["canon_blocked"] is False and gate["can_publish"] is True


async def test_chapter_scene_gate_synthetic_prose_job_does_not_mask_canon(pool):
    """D-M3-PROSEJOB-PUBLISHGATE — a synthetic `promoted_scene_prose` job (M3, no
    canon verdict) must NOT shadow an earlier auto-gen's CONFIRMED contradiction.
    It is NEWER than the contradicting job, but carries no canon-check, so treating
    it as 'latest' would silently un-block publish. The gate excludes it → still
    blocked (conservative-for-canon: only a real re-generation can clear the block)."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    s1 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    await repo.update_node_commit_aware(s1.id, {"status": "done"})

    # auto job leaves an unresolved contradiction → blocked.
    j1, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j1.id, "completed",
                             result={"text": "x", "canon": {"resolved": False,
                                                            "violations": [{"entity_id": "e"}]}})
    assert (await repo.chapter_scene_gate(project, chapter))["canon_blocked"] is True

    # a LATER synthetic prose-persist job (no canon key) must NOT mask the block.
    await jobs.upsert_promoted_scene_prose(project, s1.id, "author's edited take prose", created_by=user)
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["canon_blocked"] is True and gate["canon_unresolved_scenes"] == 1
    assert gate["can_publish"] is False


async def test_chapter_scene_gate_surfaces_unchecked_without_blocking(pool):
    """Dirty-data path: a scene whose latest auto job could NOT verify canon
    (status=skipped_no_position / degraded) is SURFACED via canon_unchecked_scenes
    but does NOT block publish (false-blocking every un-positioned scene is worse;
    the FE warns instead)."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    s1 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    await repo.update_node_commit_aware(s1.id, {"status": "done"})
    j, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                             outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j.id, "completed",
                             result={"text": "x", "canon": {"resolved": True,
                                                            "status": "skipped_no_position"}})
    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["canon_unchecked_scenes"] == 1
    assert gate["canon_blocked"] is False
    assert gate["can_publish"] is True  # surfaced, NOT blocked


async def test_canon_issues_empty_book_returns_empty_list(pool):
    repo = OutlineRepo(pool)
    # a project with no generation jobs → no canon issues (canon_issues keys on
    # project_id alone now — no actor arg).
    assert await repo.canon_issues(uuid.uuid4()) == []


async def test_canon_issues_lists_unresolved_scenes_itemized(pool):
    """Studio Quality tab (`quality-canon`): book-wide, itemized — not the
    publish-gate's per-chapter COUNT. Two scenes in two different chapters each
    with an unresolved contradiction must both appear, each carrying its own
    violations payload and chapter_id (no title — composition doesn't own that)."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    ch1, ch2 = uuid.uuid4(), uuid.uuid4()
    s1 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=ch1, title="Scene A")
    s2 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=ch2, title="Scene B")

    j1, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j1.id, "completed",
                             result={"text": "x", "canon": {"resolved": False, "status": "checked",
                                                            "violations": [{"entity_id": "e1", "name": "Old Man Wu"}]}})
    j2, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s2.id, mode="auto", status="running", input={})
    await jobs.update_status(j2.id, "completed",
                             result={"text": "y", "canon": {"resolved": False, "status": "checked",
                                                            "violations": [{"entity_id": "e2", "name": "Su Han"}]}})

    issues = await repo.canon_issues(project)
    assert len(issues) == 2
    by_scene = {i["scene_id"]: i for i in issues}
    assert by_scene[str(s1.id)]["chapter_id"] == str(ch1)
    assert by_scene[str(s1.id)]["scene_title"] == "Scene A"
    assert by_scene[str(s1.id)]["violations"][0]["name"] == "Old Man Wu"
    assert by_scene[str(s2.id)]["chapter_id"] == str(ch2)
    assert by_scene[str(s2.id)]["violations"][0]["name"] == "Su Han"


async def test_canon_issues_resolved_scene_absent_and_newer_job_supersedes(pool):
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    s1 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter)

    # a resolved job never appears.
    j1, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j1.id, "completed", result={"text": "x", "canon": {"resolved": True}})
    assert await repo.canon_issues(project) == []

    # an unresolved job appears...
    j2, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j2.id, "completed",
                             result={"text": "y", "canon": {"resolved": False, "violations": []}})
    issues = await repo.canon_issues(project)
    assert len(issues) == 1 and issues[0]["job_id"] == str(j2.id)

    # ...until a NEWER resolved job supersedes it (DISTINCT ON latest, same as chapter_scene_gate).
    j3, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j3.id, "completed", result={"text": "z", "canon": {"resolved": True}})
    assert await repo.canon_issues(project) == []


async def test_canon_issues_synthetic_prose_job_does_not_mask(pool):
    """D-M3-PROSEJOB-PUBLISHGATE parity: a synthetic promoted_scene_prose job (no
    canon verdict) must not shadow an earlier confirmed contradiction here either —
    same exclusion as chapter_scene_gate, itemized list must stay conservative-for-canon."""
    repo = OutlineRepo(pool)
    jobs = GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    s1 = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter)
    j1, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s1.id, mode="auto", status="running", input={})
    await jobs.update_status(j1.id, "completed",
                             result={"text": "x", "canon": {"resolved": False, "violations": [{"entity_id": "e"}]}})
    await jobs.upsert_promoted_scene_prose(project, s1.id, "author's edited take prose", created_by=user)
    issues = await repo.canon_issues(project)
    assert len(issues) == 1 and issues[0]["job_id"] == str(j1.id)


# ──────────── rule_violations — the RULE lane (24 PH18 / RUN-STATE D-04 option B) ────────────
# The sibling of canon_issues, and the point of the whole decision: `critic.violations[]` carries a
# `rule_id`, `result.canon.violations[]` does not. Only this lane can answer "show me violations of
# rule X", which is what the Plan Hub's canon badge deep-links on.


async def _scene_with_critic(pool, repo, jobs, project, user, chapter, critic, *, title="Scene A"):
    """Seed one scene whose latest completed job carries the given critic verdict."""
    s = await repo.create_node(project, created_by=user, kind="scene", chapter_id=chapter, title=title)
    j, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                             outline_node_id=s.id, mode="auto", status="running", input={})
    await jobs.update_status(j.id, "completed", result={"text": "x"}, critic=critic)
    return s, j


async def test_rule_violations_joins_the_rule_text_and_is_flat_per_violation(pool):
    """One scene breaking TWO rules yields TWO rows — flat, because a deep-link targets a RULE."""
    repo, jobs, rules = OutlineRepo(pool), GenerationJobsRepo(pool), CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r1 = await rules.create(project, "Magic always costs HP", created_by=user)
    r2 = await rules.create(project, "Nobody crosses the Wall alive", created_by=user)
    chapter = uuid.uuid4()
    await _scene_with_critic(pool, repo, jobs, project, user, chapter, {
        "coherence": 4,
        "violations": [
            {"rule_id": str(r1.id), "violated": True, "span": "she cast it freely", "why": "no cost paid"},
            {"rule_id": str(r2.id), "violated": True, "span": "he walked through", "why": "crossed the Wall"},
        ],
    })

    res = await repo.rule_violations(project)
    items = res["items"]
    assert len(items) == 2 and res["count"] == 2 and res["capped"] is False
    by_rule = {i["rule_id"]: i for i in items}
    assert by_rule[str(r1.id)]["rule_text"] == "Magic always costs HP"
    assert by_rule[str(r1.id)]["why"] == "no cost paid"
    assert by_rule[str(r2.id)]["rule_text"] == "Nobody crosses the Wall alive"
    assert by_rule[str(r1.id)]["chapter_id"] == str(chapter)
    assert by_rule[str(r1.id)]["scene_title"] == "Scene A"


async def test_rule_violations_excludes_dismissed_and_not_violated(pool):
    """`dismissed` is set by POST /jobs/{id}/dismiss-violation — its whole job is to silence a
    finding, so a dismissed row must not come back. `violated: false` is the judge itself saying
    no. Everything else stands: an ABSENT `violated` still counts (default-open — a malformed
    verdict must not quietly clear the book)."""
    repo, jobs, rules = OutlineRepo(pool), GenerationJobsRepo(pool), CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r = await rules.create(project, "Magic costs HP", created_by=user)
    await _scene_with_critic(pool, repo, jobs, project, user, uuid.uuid4(), {
        "violations": [
            {"rule_id": str(r.id), "violated": True, "dismissed": True, "why": "dismissed by the author"},
            {"rule_id": str(r.id), "violated": False, "why": "judge said no"},
            {"rule_id": str(r.id), "why": "no `violated` key at all"},  # default-open
        ],
    })

    res = await repo.rule_violations(project)
    assert [i["why"] for i in res["items"]] == ["no `violated` key at all"]
    assert res["count"] == 1, "the EXACT count must match the filtered list"


async def test_rule_violations_keeps_an_unattributable_finding_rather_than_dropping_it(pool):
    """A rule_id is LLM output. It may be paraphrased into nonsense, or name a rule the author has
    since archived. Either way the FINDING is real: the judge saw a contradiction. Dropping the row
    would render the panel clean over a book that isn't — so it comes back with rule_text=None.

    It also proves the query does not cast that untrusted string to uuid: 'not-a-uuid' would blow
    the whole statement up, taking every OTHER violation in the book with it."""
    repo, jobs, rules = OutlineRepo(pool), GenerationJobsRepo(pool), CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    archived = await rules.create(project, "A rule the author retired", created_by=user)
    await rules.archive(project, archived.id)
    live = await rules.create(project, "A live rule", created_by=user)

    await _scene_with_critic(pool, repo, jobs, project, user, uuid.uuid4(), {
        "violations": [
            {"rule_id": "not-a-uuid", "violated": True, "why": "the judge invented an id"},
            {"rule_id": str(uuid.uuid4()), "violated": True, "why": "a well-formed id for no rule"},
            {"rule_id": str(archived.id), "violated": True, "why": "breaks a retired rule"},
            {"rule_id": str(live.id), "violated": True, "why": "breaks a live rule"},
        ],
    })

    res = await repo.rule_violations(project)
    items = res["items"]
    assert len(items) == 4, "an unattributable violation is still a real finding"
    resolved = {i["why"]: i["rule_text"] for i in items}
    assert resolved["breaks a live rule"] == "A live rule"
    assert resolved["the judge invented an id"] is None
    assert resolved["a well-formed id for no rule"] is None
    assert resolved["breaks a retired rule"] is None, "an archived rule no longer resolves"


async def test_rule_violations_newer_job_supersedes_and_synthetic_prose_does_not_mask(pool):
    """Same two predicates as canon_issues: DISTINCT ON the node's LATEST completed job, and a
    synthetic promoted_scene_prose job (which runs no critic) must never shadow a real verdict."""
    repo, jobs, rules = OutlineRepo(pool), GenerationJobsRepo(pool), CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r = await rules.create(project, "Magic costs HP", created_by=user)
    s, _ = await _scene_with_critic(pool, repo, jobs, project, user, uuid.uuid4(), {
        "violations": [{"rule_id": str(r.id), "violated": True, "why": "first pass"}],
    })
    assert [i["why"] for i in (await repo.rule_violations(project))["items"]] == ["first pass"]

    # the author's own prose overwrite carries no critic — the finding must SURVIVE it.
    await jobs.upsert_promoted_scene_prose(project, s.id, "the author's take", created_by=user)
    assert [i["why"] for i in (await repo.rule_violations(project))["items"]] == ["first pass"]

    # ...but a genuine re-draft that comes back clean DOES clear it.
    j2, _ = await jobs.create(project, created_by=user, operation="draft_scene",
                              outline_node_id=s.id, mode="auto", status="running", input={})
    await jobs.update_status(j2.id, "completed", result={"text": "y"}, critic={"violations": []})
    assert (await repo.rule_violations(project))["items"] == []


async def test_rule_violations_caps_the_list_but_the_count_stays_exact(pool):
    """Rows are FLAT per (scene x violation) and each carries the rule's full text, so a long book
    multiplies out. The list is capped — but `count` is EXACT and `capped` is True, so the reader
    can SEE the truncation. A silent truncation reads as completeness, which is the lie."""
    repo, jobs, rules = OutlineRepo(pool), GenerationJobsRepo(pool), CanonRulesRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    r = await rules.create(project, "Magic costs HP", created_by=user)
    await _scene_with_critic(pool, repo, jobs, project, user, uuid.uuid4(), {
        "violations": [
            {"rule_id": str(r.id), "violated": True, "why": f"v{i}"} for i in range(10)
        ],
    })

    res = await repo.rule_violations(project, limit=4)
    assert len(res["items"]) == 4, "the list obeys the cap"
    assert res["count"] == 10, "the count is EXACT, not the capped length"
    assert res["capped"] is True

    full = await repo.rule_violations(project, limit=50)
    assert len(full["items"]) == 10 and full["count"] == 10 and full["capped"] is False


async def test_rule_violations_empty_book_and_null_critic_return_empty(pool):
    """A job with NO critic at all (critic column NULL) must yield nothing, not explode on the
    jsonb_array_elements — the COALESCE is load-bearing."""
    repo, jobs = OutlineRepo(pool), GenerationJobsRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    assert (await repo.rule_violations(uuid.uuid4()))["items"] == []
    await _scene_with_critic(pool, repo, jobs, project, user, uuid.uuid4(), None)
    assert (await repo.rule_violations(project))["items"] == []


# ──────────────────── generation_correction (V1 flywheel slice 1) ────────────────────

import json as _json  # noqa: E402


async def _make_job(pool, created_by, project):
    # Caller must have seeded the project's composition_work first (the INSERT derives
    # book_id from it). `created_by` is the actor stamp, keyword-only on the repo.
    gjr = GenerationJobsRepo(pool)
    job, _ = await gjr.create(project, created_by=created_by, operation="draft_scene",
                              status="completed", input={"model_ref": str(uuid.uuid4())})
    return job


async def test_correction_create_emits_relayable_event_atomically(pool):
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    corr = await repo.create(
        project, job.id, created_by=user, kind="edit", changed_blocks=3, guidance="tighten",
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
    await _seed_work(pool, user, project)
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    await repo.create(project, job.id, created_by=user, kind="pick_different",
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
    await _seed_work(pool, user, project)
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)

    async def boom(*a, **k):
        raise RuntimeError("relay emit failed")

    monkeypatch.setattr("app.db.repositories.outbox.emit", boom)
    with pytest.raises(RuntimeError):
        await repo.create(project, job.id, created_by=user, kind="reject")
    async with pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM generation_correction WHERE job_id=$1", job.id)
    assert n == 0  # atomic: the row rolled back with the failed emit


async def test_correction_rejects_foreign_job(pool):
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    # NEW LAW (spec 25 PM-5): the actor (created_by) is a plain stamp — a book grantee
    # may correct — so per-actor refusal moved to the E0 gate. The repo's surviving
    # guard is that the job must live in the GIVEN project: a wrong project id can't
    # resolve the job → rejected, and NOTHING is written (no row, no event). A
    # different actor stamp on the SAME wrong project is refused for the same reason.
    other, _, _ = _ids()
    with pytest.raises(ReferenceViolationError):
        await repo.create(uuid.uuid4(), job.id, created_by=user, kind="reject")
    with pytest.raises(ReferenceViolationError):
        await repo.create(uuid.uuid4(), job.id, created_by=other, kind="reject")
    async with pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM generation_correction")
        ev = await c.fetchval("SELECT count(*) FROM outbox_events WHERE event_type=$1",
                              outbox.GENERATION_CORRECTED)
    assert n == 0 and ev == 0


async def test_correction_rejects_foreign_regenerated_to_job(pool):
    """/review-impl MED#2: the §8.3 chain target must also be the caller's job in
    this project — a foreign regenerated_to_job_id is rejected, nothing written."""
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    job = await _make_job(pool, user, project)
    # a job in another project (FK would pass — it exists — but scope must not)
    other, other_proj, _ = _ids()
    await _seed_work(pool, other, other_proj)
    foreign_job = await _make_job(pool, other, other_proj)
    repo = GenerationCorrectionsRepo(pool)
    with pytest.raises(ReferenceViolationError):
        await repo.create(project, job.id, created_by=user, kind="regenerate",
                          regenerated_to_job_id=foreign_job.id)
    async with pool.acquire() as c:
        n = await c.fetchval("SELECT count(*) FROM generation_correction")
        ev = await c.fetchval("SELECT count(*) FROM outbox_events WHERE event_type=$1",
                              outbox.GENERATION_CORRECTED)
    assert n == 0 and ev == 0
    # a chain target that IS a job in the SAME project is accepted
    own2 = await _make_job(pool, user, project)
    ok = await repo.create(project, job.id, created_by=user, kind="regenerate",
                           regenerated_to_job_id=own2.id)
    assert ok.regenerated_to_job_id == own2.id


async def test_correction_pick_different_check_constraint(pool):
    """The DB CHECK forbids a pick_different without the candidate it points at."""
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    with pytest.raises(asyncpg.CheckViolationError):
        await repo.create(project, job.id, created_by=user, kind="pick_different",
                          chosen_candidate_index=None)


async def test_correction_stores_raw_prose_and_lists(pool):
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    job = await _make_job(pool, user, project)
    repo = GenerationCorrectionsRepo(pool)
    await repo.create(project, job.id, created_by=user, kind="edit", changed_blocks=1,
                      raw_before="winner text", raw_after="edited text")
    listed = await repo.list_for_job(project, job.id)
    assert len(listed) == 1
    assert listed[0].raw_before == "winner text" and listed[0].raw_after == "edited text"
    # cross-PROJECT list is empty (list_for_job keys on project_id + job_id)
    assert await repo.list_for_job(uuid.uuid4(), job.id) == []


async def test_correction_stats_rates_by_mode(pool):
    """slice 5 eval-gate: per-mode correction rates over real jobs + corrections.
    Denominator = COMPLETED generations; accept_rate is derived (H2-safe);
    avg_edit_magnitude reads changed_blocks; both modes always present."""
    gjr = GenerationJobsRepo(pool)
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    auto = []
    for _ in range(4):
        j, _ = await gjr.create(project, created_by=user, operation="draft_scene", mode="auto", status="completed")
        auto.append(j)
    cow = []
    for _ in range(2):
        j, _ = await gjr.create(project, created_by=user, operation="draft_scene", mode="cowrite", status="completed")
        cow.append(j)
    # a 'running' auto job must NOT count toward generations (denominator)
    await gjr.create(project, created_by=user, operation="draft_scene", mode="auto", status="running")
    # auto: one edit (magnitude 3) + one pick_different → 2 corrected of 4
    await cr.create(project, auto[0].id, created_by=user, kind="edit", changed_blocks=3)
    await cr.create(project, auto[1].id, created_by=user, kind="pick_different", chosen_candidate_index=1)
    # cowrite: one reject → 1 corrected of 2
    await cr.create(project, cow[0].id, created_by=user, kind="reject")

    stats = await cr.correction_stats(project)
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
    # cross-PROJECT isolation → all zero (stats key on project_id)
    other = await cr.correction_stats(uuid.uuid4())
    assert all(m.generations == 0 and m.corrected_jobs == 0 for m in other.by_mode)


async def test_correction_stats_excludes_selection_edits(pool):
    """/review-impl: T3.2 selection edits run mode='cowrite' but are NOT part of the
    draft-correction flywheel (no correction captured) — they must NOT inflate the
    cowrite `generations` denominator, which would drag its correction rate down and
    corrupt the cowrite-vs-auto eval signal."""
    gjr = GenerationJobsRepo(pool)
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    # one real cowrite scene draft + two selection edits (also mode='cowrite').
    await gjr.create(project, created_by=user, operation="draft_scene", mode="cowrite", status="completed")
    await gjr.create(project, created_by=user, operation="rewrite", mode="cowrite", status="completed",
                     input={"selection_edit": True})
    await gjr.create(project, created_by=user, operation="expand", mode="cowrite", status="completed",
                     input={"selection_edit": True})
    stats = await cr.correction_stats(project)
    cw = next(m for m in stats.by_mode if m.mode == "cowrite")
    assert cw.generations == 1  # ONLY the real scene draft, not the 2 selection edits


async def test_correction_stats_excludes_non_draft_operations(pool):
    """BE-9c (F-Q3a): the denominator counts ONLY correctable-draft ops. mode='auto' is ALSO the
    default for plan passes / quality reports / self-heal / coverage / conformance / decompose — none
    a draft a human accepts/edits/rejects — so grouping by mode over EVERY job inflates the 'auto'
    denominator and accept_rate reads a lie. Only draft_scene/draft_chapter/stitch_chapter count."""
    gjr = GenerationJobsRepo(pool)
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    # one real auto draft …
    await gjr.create(project, created_by=user, operation="draft_scene", mode="auto", status="completed")
    # … and a spread of non-correctable auto jobs that must NOT inflate the denominator.
    for op in ("plan_forge_refine", "quality_report", "self_heal_propose", "promise_coverage",
               "conformance_run", "decompose_preview", "plan_pipeline"):
        await gjr.create(project, created_by=user, operation=op, mode="auto", status="completed")
    a = next(m for m in (await cr.correction_stats(project)).by_mode if m.mode == "auto")
    assert a.generations == 1  # ONLY the draft_scene, not the 7 non-draft auto jobs

    # the other two correctable ops count too (draft_chapter, stitch_chapter).
    await gjr.create(project, created_by=user, operation="draft_chapter", mode="auto", status="completed")
    await gjr.create(project, created_by=user, operation="stitch_chapter", mode="auto", status="completed")
    a2 = next(m for m in (await cr.correction_stats(project)).by_mode if m.mode == "auto")
    assert a2.generations == 3


async def test_correction_stats_distinct_job_and_completed_only(pool):
    """/review-impl slice-5 MED#1+#2: multiple corrections on ONE job count it
    ONCE (a rate can't exceed 1.0), and a correction on a NON-completed job is
    excluded so corrected_jobs ⊆ generations and accept_rate can't go negative."""
    gjr = GenerationJobsRepo(pool)
    cr = GenerationCorrectionsRepo(pool)
    user, project, _ = _ids()
    await _seed_work(pool, user, project)
    # one completed auto generation that gets TWO corrections (regenerate + edit)
    j, _ = await gjr.create(project, created_by=user, operation="draft_scene", mode="auto", status="completed")
    await cr.create(project, j.id, created_by=user, kind="regenerate", guidance="darker")
    await cr.create(project, j.id, created_by=user, kind="edit", changed_blocks=2)
    # a RUNNING auto job with a reject correction (creatable via the API) must NOT count
    run, _ = await gjr.create(project, created_by=user, operation="draft_scene", mode="auto", status="running")
    await cr.create(project, run.id, created_by=user, kind="reject")

    a = next(m for m in (await cr.correction_stats(project)).by_mode if m.mode == "auto")
    assert a.generations == 1          # only the completed job
    assert a.corrected_jobs == 1       # the one job, counted ONCE despite 2 corrections
    assert a.edit_rate == 1.0 and a.regenerate_rate == 1.0   # ≤ 1.0
    assert a.reject_rate == 0.0        # the running-job reject is excluded
    assert a.accept_rate == 0.0        # (1−1)/1 — never negative


async def test_correction_stats_cold_start_null_rates(pool):
    """No generations → rates are None (cold-start), not div-by-zero."""
    cr = GenerationCorrectionsRepo(pool)
    _, project, _ = _ids()
    stats = await cr.correction_stats(project)
    for m in stats.by_mode:
        assert m.generations == 0 and m.accept_rate is None and m.edit_rate is None


# ── narrative_thread ledger (cycle 14 §5.2/§10.2) ──────────────────────────────


async def _make_node(pool, created_by, project, book) -> uuid.UUID:
    """A minimal arc outline_node so the narrative_thread node FKs resolve. Package
    re-key: the actor column is `created_by`; book_id is NOT NULL (no FK — a plain
    id supplied here)."""
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank) "
            "VALUES ($1, $2, $3, 'arc', 'a') RETURNING id",
            created_by, project, book,
        )


async def test_narrative_thread_open_pay_lifecycle(pool):
    """open → list_open shows it → pay (with payoff_node) → list_open drops it,
    list_for_project keeps it (paid). Tenant isolation: another user can't pay it."""
    repo = NarrativeThreadRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    node = await _make_node(pool, user, project, book)
    payoff = await _make_node(pool, user, project, book)
    t = await repo.open_thread(
        project, created_by=user, kind="promise", summary="a sword is promised",
        opened_at_node=node, trigger="hand on the hilt", priority=80,
    )
    assert t.status == "open" and t.payoff_node is None and t.opened_at_node == node

    assert [x.id for x in await repo.list_open(project)] == [t.id]

    # scoping (NEW LAW): the thread is keyed on its project partition — a WRONG project
    # id can't transition it (per-actor refusal moved to the E0 book gate).
    assert await repo.update_status(uuid.uuid4(), t.id, status="paid", payoff_node=payoff) is None

    paid = await repo.update_status(project, t.id, status="paid", payoff_node=payoff)
    assert paid is not None and paid.status == "paid" and paid.payoff_node == payoff and paid.version == 2

    # paid → out of the re-injectable open set; still in the full list.
    assert await repo.list_open(project) == []
    allt = await repo.list_for_project(project)
    assert len(allt) == 1 and allt[0].status == "paid"


async def test_narrative_thread_payoff_only_when_paid(pool):
    """A payoff_node on a non-paid transition is cleared by the repo, so the
    table CHECK (payoff_node IS NULL OR status='paid') never trips."""
    repo = NarrativeThreadRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    node = await _make_node(pool, user, project, book)
    t = await repo.open_thread(project, created_by=user, kind="foreshadow", summary="a stranger watches")
    prog = await repo.update_status(project, t.id, status="progressing", payoff_node=node)
    assert prog is not None and prog.status == "progressing" and prog.payoff_node is None


async def test_narrative_thread_list_open_ordering(pool):
    """The F2 re-injection read order: highest priority first, then oldest-first."""
    repo = NarrativeThreadRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    low = await repo.open_thread(project, created_by=user, kind="promise", summary="low", priority=10)
    high = await repo.open_thread(project, created_by=user, kind="promise", summary="high", priority=90)
    mid = await repo.open_thread(project, created_by=user, kind="promise", summary="mid", priority=50)
    assert [x.id for x in await repo.list_open(project)] == [high.id, mid.id, low.id]


async def test_narrative_thread_node_delete_sets_null(pool):
    """ON DELETE SET NULL: removing the anchored outline_node leaves the thread
    intact but un-anchored (no dangling ref)."""
    repo = NarrativeThreadRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    node = await _make_node(pool, user, project, book)
    t = await repo.open_thread(project, created_by=user, kind="promise", summary="anchored", opened_at_node=node)
    async with pool.acquire() as c:
        await c.execute("DELETE FROM outline_node WHERE id = $1", node)
    after = (await repo.list_for_project(project))[0]
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


async def test_progress_goal_is_per_user(pool):
    """BE-P2 — the daily goal is PER-USER: Alice's goal never becomes Bob's (the tenancy fix for
    the shared work.settings.daily_goal). Set/get round-trips; 0 clears the row; unset → None."""
    repo = DailyProgressRepo(pool)
    alice, project, _ = _ids()
    bob = uuid.uuid4()
    assert await repo.get_goal(alice, project) is None      # unset → None
    await repo.set_goal(alice, project, 2000)
    assert await repo.get_goal(alice, project) == 2000       # Alice's own
    assert await repo.get_goal(bob, project) is None         # NOT Bob's (isolation)
    await repo.set_goal(alice, project, 0)                   # 0 clears
    assert await repo.get_goal(alice, project) is None


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
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    scene, chapter = uuid.uuid4(), uuid.uuid4()
    await repo.upsert(project, "work", project, 50, 50, created_by=user)
    # only work set → resolve returns work
    r = await repo.resolve(project, scene, chapter)
    assert r is not None and r.scope_type == "work"
    # add chapter → chapter wins over work
    await repo.upsert(project, "chapter", chapter, 40, 60, created_by=user)
    r = await repo.resolve(project, scene, chapter)
    assert r.scope_type == "chapter" and r.density == 40
    # add scene → scene wins over chapter + work
    await repo.upsert(project, "scene", scene, 80, 20, created_by=user)
    r = await repo.resolve(project, scene, chapter)
    assert r.scope_type == "scene" and r.density == 80 and r.pace == 20
    # a DIFFERENT scene (no scene row) falls back to chapter
    other = await repo.resolve(project, uuid.uuid4(), chapter)
    assert other.scope_type == "chapter"


async def test_style_profile_upsert_replaces_and_delete_reverts(pool):
    repo = StyleProfileRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    chapter = uuid.uuid4()
    await repo.upsert(project, "chapter", chapter, 30, 30, created_by=user)
    await repo.upsert(project, "chapter", chapter, 70, 70, created_by=user)  # replace in place
    rows = await repo.list_all(project)
    assert len(rows) == 1 and rows[0].density == 70
    assert await repo.delete(project, "chapter", chapter) is True
    assert await repo.list_all(project) == []
    # cross-PROJECT scoping — a different project resolves to nothing
    assert await repo.resolve(uuid.uuid4(), None, chapter) is None


async def test_voice_profile_present_only_and_upsert(pool):
    """list_for_entities returns only the requested (present) entities; upsert replaces."""
    repo = VoiceProfileRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    kael, mira, absent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await repo.upsert(project, kael, "Kael", ["terse", "understatement"], created_by=user)
    await repo.upsert(project, mira, "Mira", ["formal"], created_by=user)
    # only Kael present in the scene
    present = await repo.list_for_entities(project, [kael, absent])
    assert [v.entity_name for v in present] == ["Kael"]
    assert present[0].tags == ["terse", "understatement"]
    # upsert replaces tags in place (ON CONFLICT on the (project_id, entity_id) PK —
    # NOT the actor — so a re-edit updates the shared row, never a second row)
    await repo.upsert(project, kael, "Kael", ["wry"], created_by=user)
    again = await repo.list_for_entities(project, [kael])
    assert again[0].tags == ["wry"]
    # empty present set → no query, empty list
    assert await repo.list_for_entities(project, []) == []
    # cross-PROJECT scoping — a different project sees nothing
    assert await repo.list_for_entities(uuid.uuid4(), [kael]) == []


async def test_voice_profile_list_all_and_delete(pool):
    repo = VoiceProfileRepo(pool)
    user, project, book = _ids()
    await _seed_work(pool, user, project, book)
    e = uuid.uuid4()
    await repo.upsert(project, e, "Kael", ["terse"], created_by=user)
    assert len(await repo.list_all(project)) == 1
    assert await repo.delete(project, e) is True
    assert await repo.list_all(project) == []


# ───────────────────────── plan_run (PlanForge M3) ─────────────────────────

async def test_plan_runs_roundtrip_and_tenancy(pool):
    from app.db.repositories.plan_runs import PlanRunsRepo

    repo = PlanRunsRepo(pool)
    user, _project, book = _ids()
    other_book = uuid.uuid4()
    run = await repo.create(
        user, book, mode="rules", source_checksum="chk1",
        source_markdown="# plan", status="pending",
    )
    # 25 M3 (OQ-3): the actor column is `created_by`; reads are BOOK-scoped (no owner
    # filter — access is the E0 book gate).
    assert run.created_by == user
    got = await repo.get_for_book(book, run.id)
    assert got is not None and got.id == run.id
    # NEW LAW: the OLD owner-scoped read is now book-scoped — a grantee reading the
    # book succeeds; a DIFFERENT book resolves to None (was: a different user → None).
    assert await repo.get_for_book(other_book, run.id) is None

    art = await repo.save_artifact(user, run.id, "spec", {"events": []})
    latest = await repo.latest_artifact(book, run.id, "spec")
    assert latest is not None and latest.id == art.id
    refs = await repo.list_artifact_refs(book, run.id)
    assert refs[0]["kind"] == "spec"

    updated = await repo.update_run(book, run.id, status="proposed", clear_error=True)
    assert updated is not None and updated.status == "proposed"

    runs, cursor = await repo.list_for_book(book, limit=10)
    assert len(runs) == 1
    assert cursor is None

    dup = await repo.find_by_checksum(book, "chk1", "rules")
    assert dup is not None and dup.id == run.id
    # D-PLANFORGE-MODE-DEDUPE: same checksum, different mode -> no reuse.
    assert await repo.find_by_checksum(book, "chk1", "llm") is None


# ───────── plan_state_for_book — the per-chat-turn "has an arc plan?" probe ─────────
# Real SQL (the route tests mock the repo, so THESE are what prove the query).

async def test_plan_state_for_book_with_runs_and_spec(pool):
    """(a) runs + a `spec` artifact -> has a plan AND has the spec; run_count and
    latest_status reflect the newest run by created_at."""
    from app.db.repositories.plan_runs import PlanRunsRepo

    repo = PlanRunsRepo(pool)
    user, _project, book = _ids()
    first = await repo.create(
        user, book, mode="rules", source_checksum="c1", source_markdown="# a",
        status="failed",
    )
    second = await repo.create(
        user, book, mode="llm", source_checksum="c2", source_markdown="# b",
        status="compiled",
    )
    # the spec hangs off the FIRST run — has_spec must be an EXISTS over ALL the
    # book's runs (through the plan_run join), not just the latest one.
    await repo.save_artifact(user, first.id, "spec", {"arcs": [{"id": "a1"}]})

    state = await repo.plan_state_for_book(book)
    assert state == {"run_count": 2, "latest_status": "compiled", "has_spec": True}
    assert second.status == "compiled"  # the latest run by created_at


async def test_plan_state_for_book_with_no_plan_is_zeros_not_error(pool):
    """(b) a brand-new book has no runs -> zeros, NOT an error/None. The route maps
    this to a 200 (`has_plan=false`), never a 404."""
    from app.db.repositories.plan_runs import PlanRunsRepo

    state = await PlanRunsRepo(pool).plan_state_for_book(uuid.uuid4())
    assert state == {"run_count": 0, "latest_status": None, "has_spec": False}


async def test_plan_state_for_book_runs_without_spec_has_no_plan_spec(pool):
    """(c) THE distinction: a run exists but emitted no `spec` artifact (still
    pending, or failed) -> run_count>0 while has_spec is FALSE. A non-spec artifact
    on that run must NOT be mistaken for the plan spec, and another book's spec must
    NOT leak in (the artifact EXISTS is book-scoped through its run's join)."""
    from app.db.repositories.plan_runs import PlanRunsRepo

    repo = PlanRunsRepo(pool)
    user, _project, book = _ids()
    run = await repo.create(
        user, book, mode="rules", source_checksum="c1", source_markdown="# a",
        status="pending",
    )
    await repo.save_artifact(user, run.id, "analyze", {"noise": True})  # NOT a spec

    # a DIFFERENT book that does have a spec — must not bleed across the book scope.
    other_book = uuid.uuid4()
    other_run = await repo.create(
        user, other_book, mode="rules", source_checksum="c9", source_markdown="# z",
        status="compiled",
    )
    await repo.save_artifact(user, other_run.id, "spec", {"arcs": []})

    state = await repo.plan_state_for_book(book)
    assert state == {"run_count": 1, "latest_status": "pending", "has_spec": False}
    # sanity: the other book DOES read as having a spec (the probe isn't just always-false)
    other = await repo.plan_state_for_book(other_book)
    assert other == {"run_count": 1, "latest_status": "compiled", "has_spec": True}


# ── linked_structure_state — the governance effect-probe (Phase G · G0) ──
# Real SQL for the D2/D3 distinction the route tests mock away: only plan_run_id-stamped
# rows count (compile-attributed), and the fresh count is scoped to the latest run.

async def _insert_linked_arc(pool, book, run_id, arc_id):
    """A structure_node as the COMPILE writes it — plan_run_id + plan_arc_id stamped
    (mirrors plan_link_service's _UPSERT_ARC)."""
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO structure_node (book_id, kind, rank, title, plan_run_id, plan_arc_id) "
            "VALUES ($1, 'arc', $2, $3, $4, $5)",
            book, arc_id, f"arc {arc_id}", run_id, arc_id,
        )


async def test_linked_structure_state_compile_attributed_and_fresh(pool):
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.db.repositories.structure import StructureRepo

    plans = PlanRunsRepo(pool)
    structure = StructureRepo(pool)
    user, _project, book = _ids()

    # D3 — a bare arc_create (create_node leaves plan_run_id NULL) is NOT compile-attributed.
    await structure.create_node(book, created_by=user, kind="arc", title="hand-made")
    state = await structure.linked_structure_state(book)
    assert state["linked_count"] == 0            # a plain insert can't fabricate the effect
    assert state["latest_run_id"] is None
    assert state["latest_run_linked_count"] == 0

    # run #1 compiles two arcs (plan_run_id stamped).
    run1 = await plans.create(
        user, book, mode="llm", source_checksum="c1", source_markdown="# a", status="compiled",
    )
    await _insert_linked_arc(pool, book, run1.id, "arc-1a")
    await _insert_linked_arc(pool, book, run1.id, "arc-1b")
    state = await structure.linked_structure_state(book)
    assert state["linked_count"] == 2            # compile-attributed rows count (ensure-EXISTS)
    assert str(state["latest_run_id"]) == str(run1.id)
    assert state["latest_run_linked_count"] == 2  # run #1 IS the latest and it compiled

    # D2 — run #2 (a re-plan) becomes the latest with NO compile yet: fresh count is 0
    # even though the book still HAS a compiled plan from run #1.
    run2 = await plans.create(
        user, book, mode="llm", source_checksum="c2", source_markdown="# b", status="pending",
    )
    state = await structure.linked_structure_state(book)
    assert state["linked_count"] == 2            # ensure-EXISTS: the book has a compiled plan
    assert str(state["latest_run_id"]) == str(run2.id)
    assert state["latest_run_linked_count"] == 0  # produce-NEW: THIS attempt is born-fresh, NOT done

    # compiling run #2 raises BOTH counts; the fresh count tracks run #2 only.
    await _insert_linked_arc(pool, book, run2.id, "arc-2a")
    state = await structure.linked_structure_state(book)
    assert state["linked_count"] == 3
    assert state["latest_run_linked_count"] == 1

    # an archived compiled row drops out of both counts (tombstones don't inflate the effect).
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE structure_node SET is_archived = true "
            "WHERE book_id = $1 AND plan_run_id = $2 AND plan_arc_id = 'arc-2a'",
            book, run2.id,
        )
    state = await structure.linked_structure_state(book)
    assert state["linked_count"] == 2
    assert state["latest_run_linked_count"] == 0


async def test_get_run_detail_surfaces_arcs_for_a_picker(pool):
    """D-PLANFORGE-ARC-PICKER: Compile's arc_id was a bare text input — the
    spec already HAS a picker-worthy {id, title} list, it just was never
    surfaced (get_run_detail only ever returned artifact REFS, not content).
    No spec yet -> [] (not an error, not a crash)."""
    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.db.repositories.works import WorksRepo
    from app.services.plan_forge_service import PlanForgeService

    user, _project, book = _ids()
    runs = PlanRunsRepo(pool)
    svc = PlanForgeService(runs, GenerationJobsRepo(pool), WorksRepo(pool))

    run = await runs.create(
        user, book, mode="rules", source_checksum="chk-arcs",
        source_markdown="# plan", status="pending",
    )

    empty_detail = await svc.get_run_detail(user, book, run.id)
    assert empty_detail is not None and empty_detail["arcs"] == []

    await runs.save_artifact(user, run.id, "spec", {
        "arcs": [
            {"id": "arc_1", "title": "Origins"},
            {"id": "arc_2", "title": "Bước Lên Tiên Lộ"},
            {"id": "arc_3"},  # no title -> falls back to the id itself, never blank
        ],
    })
    detail = await svc.get_run_detail(user, book, run.id)
    assert detail is not None
    assert detail["arcs"] == [
        {"id": "arc_1", "title": "Origins"},
        {"id": "arc_2", "title": "Bước Lên Tiên Lộ"},
        {"id": "arc_3", "title": "arc_3"},
    ]


async def test_ground_llm_source_grounds_the_proposer_in_existing_arcs_O1(pool, monkeypatch):
    """O-1 (21-G2): a mid-book LLM propose is GROUNDED in the book's existing arcs (CONTINUE, not
    restart); a cold-start book is untouched; a degraded read FAILS CLOSED (refuse, never blind)."""
    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.db.repositories.structure import StructureRepo
    from app.db.repositories.works import WorksRepo
    from app.services.plan_forge_service import PlanForgeService

    user, _project, book = _ids()
    svc = PlanForgeService(PlanRunsRepo(pool), GenerationJobsRepo(pool), WorksRepo(pool))

    # mid-book: an arc already exists → the grounded source CONTAINS its title + a continue directive.
    await StructureRepo(pool).create_node(
        book, created_by=user, kind="arc", title="The Iron Court",
        summary="she returns for the ninth time",
    )
    grounded = await svc._ground_llm_source(book, "a braindump about her next life")
    assert "The Iron Court" in grounded                        # the proposer SEES the existing arc
    assert "CONTINUE" in grounded and "do NOT restart" in grounded
    assert "a braindump about her next life" in grounded        # the author's own input is preserved

    # cold start: a fresh book with no arcs → source returned UNCHANGED (scenario 1 keeps working).
    _u2, _p2, fresh = _ids()
    assert await svc._ground_llm_source(fresh, "blank-book braindump") == "blank-book braindump"

    # FAIL-CLOSED: a degraded book-state read must REFUSE, never propose blind.
    async def _boom(self, *a, **k):
        raise RuntimeError("book-state read down")
    monkeypatch.setattr(StructureRepo, "list_tree", _boom)
    with pytest.raises(RuntimeError):
        await svc._ground_llm_source(book, "braindump")


async def test_compile_run_pipeline_shapes_chapters_and_persists_job_id(pool, monkeypatch):
    """D-PLANFORGE-PIPELINE-CHAPTERPLAN-FIX (§6 M3): before this fix,
    compile(run_pipeline=true) passed raw package.chapters[]
    ({title, ordinal, event_id}) straight through as job input; the worker's
    `ChapterPlan(**c)` then raised TypeError on every real invocation
    (confirmed never exercised successfully in production). This proves the
    fix — job input chapters are ChapterPlan-shaped with chapter_id=event_id
    — and that pipeline_job_id is now persisted onto the run's
    checkpoint_state (previously returned once in the response body and
    never queryable again)."""
    from pathlib import Path

    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.db.repositories.works import WorksRepo
    from app.engine.plan_forge.ingest import ingest_file
    from app.engine.plan_forge.propose import propose_spec
    from app.services import plan_forge_service as pfs_module
    from app.services.plan_forge_service import PlanForgeService

    captured: dict[str, Any] = {}

    async def _fake_enqueue_job(redis_url, *, job_id, user_id, project_id):
        captured["job_id"] = job_id
        return True

    monkeypatch.setattr(pfs_module, "enqueue_job", _fake_enqueue_job)
    monkeypatch.setattr(pfs_module.settings, "composition_worker_enabled", True)

    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "plan-forge" / "story-plan-v1.md"
    spec = propose_spec(ingest_file(fixture))

    user, project, book = _ids()
    runs = PlanRunsRepo(pool)
    jobs = GenerationJobsRepo(pool)
    # Seed the book's canonical Work so compile's pipeline job can derive its
    # NOT-NULL book_id from composition_work (via _ensure_work → resolve_by_book).
    # Without a backed Work, _ensure_work mints a project-less pending row and the
    # generation_job INSERT … SELECT w.book_id would find no home (ReferenceViolationError).
    await _seed_work(pool, user, project, book)
    svc = PlanForgeService(runs, jobs, WorksRepo(pool))

    run = await runs.create(
        user, book, mode="rules", source_checksum="chk-pipeline",
        source_markdown="# plan", status="pending",
    )
    await runs.save_artifact(user, run.id, "spec", spec)

    mode, body = await svc.compile(
        user, book, run.id, arc_id="arc_2", run_pipeline=True, model_ref=uuid.uuid4(),
    )
    assert mode == "async"
    assert body["pipeline_job_id"] == str(captured["job_id"])

    job = await jobs.get(captured["job_id"])
    assert job is not None
    chapters_in = job.input["chapters"]
    assert chapters_in, "compile() must produce at least one chapter for arc_2"
    from app.engine.plan import ChapterPlan  # the exact constructor that used to TypeError

    for c in chapters_in:
        assert set(c.keys()) == {"chapter_id", "title", "sort_order", "beat_role", "intent"}
        assert c["chapter_id"].startswith("arc_2_event_")  # correlates back to PlanForge's event_id
        ChapterPlan(**c)  # must not raise — this is the exact call site that used to crash

    updated_run = await runs.get_for_book(book, run.id)
    assert updated_run is not None
    assert updated_run.checkpoint_state.get("pipeline_job_id") == str(captured["job_id"])


# ─────────── plan_bootstrap_proposal (PlanForge auto-bootstrap gate POC) ───────────

async def _make_run(pool, user, book):
    from app.db.repositories.plan_runs import PlanRunsRepo

    return await PlanRunsRepo(pool).create(
        user, book, mode="rules", source_checksum="chk-bootstrap",
        source_markdown="# plan", status="compiled",
    )


async def test_bootstrap_proposal_roundtrip_and_tenancy(pool):
    from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo

    repo = PlanBootstrapProposalsRepo(pool)
    user, _project, book = _ids()
    other_book = uuid.uuid4()
    run = await _make_run(pool, user, book)

    rec = await repo.create(
        user, book, run.id, diff={"new_chapters": [{"event_id": "e1", "title": "Ch 1"}]},
    )
    assert rec.status == "pending"
    # NEW LAW (OQ-3): reads are book-scoped — a grantee reading the book resolves the
    # record; a DIFFERENT book resolves to None (was: a different user → None).
    assert await repo.get_for_book(book, rec.id) is not None
    assert await repo.get_for_book(other_book, rec.id) is None


async def test_bootstrap_proposal_approve_reject_are_guarded_transitions(pool):
    from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo

    repo = PlanBootstrapProposalsRepo(pool)
    user, _project, book = _ids()
    run = await _make_run(pool, user, book)
    rec = await repo.create(user, book, run.id, diff={"new_chapters": []})

    # A second approve on an already-approved record is a no-op miss, not an error.
    approved = await repo.mark_approved(book, rec.id)
    assert approved is not None and approved.status == "approved"
    assert await repo.mark_approved(book, rec.id) is None

    # Rejecting an approved (not-yet-applied) record is allowed and kept for audit.
    rejected = await repo.mark_rejected(book, rec.id)
    assert rejected is not None and rejected.status == "rejected"
    still_there = await repo.get_for_book(book, rec.id)
    assert still_there is not None and still_there.status == "rejected"


async def test_bootstrap_proposal_claim_for_apply_is_atomic(pool):
    from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo

    repo = PlanBootstrapProposalsRepo(pool)
    user, _project, book = _ids()
    run = await _make_run(pool, user, book)
    rec = await repo.create(user, book, run.id, diff={"new_chapters": []})

    # Can't claim a pending (not yet approved) record.
    assert await repo.claim_for_apply(book, rec.id) is None

    await repo.mark_approved(book, rec.id)
    claimed = await repo.claim_for_apply(book, rec.id)
    assert claimed is not None and claimed.status == "applying"

    # A second concurrent/retried claim on the same (now 'applying') record misses.
    assert await repo.claim_for_apply(book, rec.id) is None

    await repo.mark_item_applied(
        book, rec.id, item_key="e1", result={"chapter_id": "c1", "title": "Ch 1"},
    )
    applied = await repo.mark_applied(book, rec.id)
    assert applied is not None
    assert applied.status == "applied"
    assert applied.applied_results == {"e1": {"chapter_id": "c1", "title": "Ch 1"}}

    # Fully-applied record can never be re-claimed (safe no-op at the service layer).
    assert await repo.claim_for_apply(book, rec.id) is None


async def test_bootstrap_proposal_failed_apply_is_resumable(pool):
    from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo

    repo = PlanBootstrapProposalsRepo(pool)
    user, _project, book = _ids()
    run = await _make_run(pool, user, book)
    rec = await repo.create(user, book, run.id, diff={"new_chapters": []})
    await repo.mark_approved(book, rec.id)
    await repo.claim_for_apply(book, rec.id)

    failed = await repo.mark_failed(book, rec.id, error_detail="book-service 502")
    assert failed is not None and failed.status == "failed" and failed.error_detail == "book-service 502"

    # A 'failed' record CAN be re-claimed (resume), unlike 'applied'.
    reclaimed = await repo.claim_for_apply(book, rec.id)
    assert reclaimed is not None and reclaimed.status == "applying"

    done = await repo.mark_applied(book, rec.id)
    assert done is not None and done.status == "applied" and done.error_detail is None


async def test_bootstrap_proposal_list_active_for_book_scopes_by_book_and_excludes_rejected(pool):
    from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo

    repo = PlanBootstrapProposalsRepo(pool)
    user, _project, book = _ids()
    other_book = uuid.uuid4()
    run = await _make_run(pool, user, book)

    applied_rec = await repo.create(user, book, run.id, diff={"new_chapters": []})
    await repo.mark_approved(book, applied_rec.id)
    await repo.claim_for_apply(book, applied_rec.id)
    await repo.mark_item_applied(
        book, applied_rec.id, item_key="e1", result={"chapter_id": "c1", "title": "Ch 1"},
    )
    await repo.mark_applied(book, applied_rec.id)

    pending_rec = await repo.create(user, book, run.id, diff={"new_chapters": []})
    rejected_rec = await repo.create(user, book, run.id, diff={"new_chapters": []})
    await repo.mark_rejected(book, rejected_rec.id)

    active = await repo.list_active_for_book(book)
    active_ids = {r.id for r in active}
    assert active_ids == {applied_rec.id, pending_rec.id}
    assert rejected_rec.id not in active_ids
    assert await repo.list_active_for_book(other_book) == []


async def test_chapter_story_order_backfill_recovers_position_from_scenes(pool):
    """24 — the backfill for chapter nodes written before the writer set `story_order`.

    Every chapter node ever persisted carried story_order NULL (the writer passed it for scenes but
    not for their chapter). Its position IS recoverable: the scenes carry it on the strided axis
    (`chapter_sort * STRIDE + scene_idx`), so flooring a chapter's minimum scene order to its stride
    boundary yields the chapter's own slot. A chapter with NO scenes stays NULL — its position is
    genuinely unknown, and a guess of 0 would claim it is the book's first chapter.
    """
    from app.db.migrate import _backfill_chapter_story_order
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE as S

    book, project = uuid.uuid4(), uuid.uuid4()
    arc = uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute("INSERT INTO structure_node (id, book_id, kind, rank, title) "
                        "VALUES ($1,$2,'arc','m','Arc')", arc, book)

        async def chapter(rank):
            return await c.fetchval(
                "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, chapter_id, "
                "structure_node_id, story_order) "
                "VALUES ($1,$2,$3,'chapter',$4,gen_random_uuid(),$5,NULL) RETURNING id",
                uuid.uuid4(), project, book, rank, arc,
            )

        async def scene(parent, rank, so):
            await c.execute(
                "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, chapter_id, "
                "parent_id, story_order) VALUES ($1,$2,$3,'scene',$4,gen_random_uuid(),$5,$6)",
                uuid.uuid4(), project, book, rank, parent, so,
            )

        ch2 = await chapter("b")   # book chapter 2 → its scenes live at 2000, 2001, 2002
        ch5 = await chapter("e")   # book chapter 5 → scenes at 5000..
        ch_bare = await chapter("z")  # no scenes at all → position unknowable
        for i in range(3):
            await scene(ch2, f"s{i}", 2 * S + i)
        # Deliberately out of insertion order: the floor must come from the MINIMUM scene order.
        await scene(ch5, "s1", 5 * S + 1)
        await scene(ch5, "s0", 5 * S + 0)

        await _backfill_chapter_story_order(c)

        got = {r["id"]: r["story_order"] for r in await c.fetch(
            "SELECT id, story_order FROM outline_node WHERE kind='chapter' AND book_id=$1", book)}
        assert got[ch2] == 2 * S      # the chapter sits exactly at its own scene 0
        assert got[ch5] == 5 * S
        assert got[ch_bare] is None   # unknown stays unknown — never guessed as 0

        # Idempotent: a second run touches nothing (it only fills NULLs), and must not move ch2.
        await _backfill_chapter_story_order(c)
        assert await c.fetchval(
            "SELECT story_order FROM outline_node WHERE id=$1", ch2) == 2 * S


async def test_commit_decomposed_tree_persists_the_chapter_on_the_reading_axis(pool):
    """24 — the WRITER. `_insert_decomposed_tree` passed `story_order` for the scenes but not for
    their chapter, so every chapter node ever persisted carried NULL — the root cause of a dead
    canon-anchor join, an unresolvable BA6 span, and a Plan Hub x-axis that fell back to the id
    tiebreak. The chapter must land at its own slot (`chapter_sort * STRIDE` = its scene 0)."""
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE as S

    repo = OutlineRepo(pool)
    project, book, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, book_id, created_by) VALUES ($1,$2,$3)",
            project, book, user,
        )

    # The spec shape the plan router builds: chapter 2 of the book, with two scenes.
    res = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="Arc",
        chapters=[{
            "chapter_id": uuid.uuid4(), "title": "Ch Two", "intent": "",
            "story_order": 2 * S,
            "scenes": [{"title": "s0", "synopsis": "", "story_order": 2 * S + 0},
                       {"title": "s1", "synopsis": "", "story_order": 2 * S + 1}],
        }],
    )

    ch_id = res["chapter_ids"][0]
    async with pool.acquire() as c:
        chapter = await c.fetchrow("SELECT kind, story_order FROM outline_node WHERE id=$1", ch_id)
        scenes = await c.fetch(
            "SELECT story_order FROM outline_node WHERE parent_id=$1 ORDER BY story_order", ch_id)

    assert chapter["kind"] == "chapter"
    assert chapter["story_order"] == 2 * S, "the chapter must carry its reading position, not NULL"
    assert [s["story_order"] for s in scenes] == [2 * S, 2 * S + 1]
    # The chapter shares its slot with its own scene 0 — that identity is what makes the canon-rule
    # window (`from_order` on the strided axis) resolve to the same node the overlay anchors on.
    assert chapter["story_order"] == scenes[0]["story_order"]
