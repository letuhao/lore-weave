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
from app.db.repositories import VersionMismatchError
from app.db.repositories import outbox
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.works import WorksRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
)

_TABLES = [
    "outbox_events", "generation_job", "canon_rule", "scene_link",
    "outline_node", "structure_template", "composition_work",
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
    """FINDING-3: a parent_id cycle (reachable via update_node reparent, no
    cycle guard) must not make archive_node's recursive CTE loop forever. UNION
    dedups → the walk terminates. Without the fix this test hangs."""
    repo = OutlineRepo(pool)
    user, project, _ = _ids()
    a = await repo.create_node(user, project, kind="arc", title="a")
    b = await repo.create_node(user, project, kind="arc", parent_id=a.id, title="b")
    # forge a cycle: a → b → a
    await repo.update_node(user, a.id, {"parent_id": b.id})
    archived = await repo.archive_node(user, a.id)
    assert archived is not None and archived.is_archived
    # both nodes in the cycle archived; query returned (did not hang)
    assert {n.id for n in await repo.list_tree(user, project)} == set()


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
