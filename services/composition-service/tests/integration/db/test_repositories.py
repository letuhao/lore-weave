"""M2 — repository round-trips against a real Postgres (throwaway test DB).

Gated on TEST_COMPOSITION_DB_URL (the fixture drops every composition table on
setup + teardown). Covers: works CRUD + resolve found/none/candidates + If-Match
412; outline auto-rank + recursive soft-archive; scene_link create/list/delete +
cross-user isolation; canon_rule active-listing + archive; generation_job
idempotency replay + COALESCE status update; txn-local outbox emit/rollback.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories import ReferenceViolationError, VersionMismatchError
from app.db.repositories import outbox
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_corrections import GenerationCorrectionsRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.works import WorksRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
)

_TABLES = [
    "outbox_events", "generation_correction", "generation_job", "canon_rule",
    "scene_link", "outline_node", "structure_template", "composition_work",
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
    assert gate == {"chapter_id": str(chapter), "scenes_total": 2, "scenes_done": 0, "can_publish": False}

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
