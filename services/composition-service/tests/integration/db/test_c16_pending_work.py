"""C16 degrade path × the 25 re-key — package writes against a LAZY (pending) Work.

THE BUG THIS PINS (found 2026-07-10, during Stage 1's real-Postgres verification):

C16 (WG-3) exists so that a knowledge-service outage never wall-blocks authoring:
`POST /books/{id}/work` degrades to a **lazy Work** with `project_id = NULL` and
`pending_project_backfill = true`. Callers then address that Work by its surrogate `id`
(`plan_forge_service._work_project_id`: *"knowledge project or surrogate work.id"*).

The re-key made `book_id NOT NULL` on all 13 package tables and derives it inside each
write via a join back to `composition_work`. Every one of those joins was written as
`WHERE w.project_id = $n` — which can NEVER match a pending Work. So every package write
on a lazy Work raised `ReferenceViolationError`, and PlanForge on a greenfield book during
a knowledge outage hard-failed instead of degrading. The mocks could not see it (no SQL),
and the DB-suite heal masked it by seeding a backed Work.

The joins now resolve the Work by the SAME identity its callers use:
    project_id = $n  OR  (project_id IS NULL AND id = $n)

Two properties must hold together, and the second is the one a careless fix breaks:
  1. a pending Work's writes SUCCEED and stamp the right book_id;
  2. a genuinely dangling project_id still RAISES — the orphan guard (PM-7: never
     silently insert a row with no book home) must not be weakened into permissiveness.

Gated on TEST_COMPOSITION_DB_URL (a throwaway DB — this drops tables).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories import ReferenceViolationError
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.references import ReferencesRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    pytest.mark.xdist_group("pg"),
]

_TABLES = (
    "generation_correction", "generation_job", "decompose_commit", "scene_grounding_pins",
    "scene_link", "narrative_thread", "canon_rule", "style_profile", "voice_profile",
    "reference_source", "entity_override", "divergence_spec", "outline_node",
    "composition_work",
)


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


async def _pending_work(pool) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """The C16 degrade shape: knowledge-service was down, so project_id is NULL and the
    Work is addressed by its surrogate id. Returns (work_id, book_id, actor)."""
    actor, book = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        work_id = await c.fetchval(
            "INSERT INTO composition_work (project_id, created_by, book_id, "
            "pending_project_backfill) VALUES (NULL,$1,$2,true) RETURNING id",
            actor, book,
        )
    return work_id, book, actor


_WRITTEN_TABLES = (
    "outline_node", "generation_job", "canon_rule", "scene_link",
    "reference_source", "narrative_thread", "style_profile", "voice_profile",
    "scene_grounding_pins",
)


async def test_every_package_write_works_on_a_pending_work(pool):
    """The whole derive-join surface, driven by the surrogate id. Each write must land
    and carry the Work's book_id — the C16 guarantee, now enforced by effect.

    book_id is asserted against the DB rather than the row models: only OutlineNode and
    GenerationJob project it (their repos' _SELECT_COLS do); the others derive it in-SQL
    without reading it back. The column is what must be right."""
    work_id, book, actor = await _pending_work(pool)
    chapter = uuid.uuid4()

    outline = OutlineRepo(pool)
    chap = await outline.create_node(work_id, created_by=actor, kind="chapter",
                                     chapter_id=chapter, title="ch1")
    assert chap.book_id == book, "outline_node.book_id not derived from the pending Work"
    scene = await outline.create_node(work_id, created_by=actor, kind="scene",
                                      parent_id=chap.id, chapter_id=chapter, title="s1")

    job, created = await GenerationJobsRepo(pool).create(
        work_id, created_by=actor, operation="draft_scene",
        outline_node_id=scene.id, model_name="test-model",
    )
    assert created and job.book_id == book, "generation_job.book_id not derived (C16)"

    await CanonRulesRepo(pool).create(work_id, "The king is dead", created_by=actor)
    await SceneLinksRepo(pool).create(work_id, scene.id, chap.id, created_by=actor)
    await ReferencesRepo(pool).create(work_id, created_by=actor, content="a passage",
                                      embedding=[0.1, 0.2, 0.3])
    await NarrativeThreadRepo(pool).open_thread(work_id, created_by=actor, kind="promise",
                                                summary="a debt")
    await StyleProfileRepo(pool).upsert(work_id, "work", work_id, 50, 50, created_by=actor)
    await VoiceProfileRepo(pool).upsert(work_id, uuid.uuid4(), "Mai", [], created_by=actor)
    await GroundingPinsRepo(pool).set_action(work_id, scene.id, "canon", str(uuid.uuid4()),
                                             "pin", created_by=actor)

    async with pool.acquire() as c:
        for t in _WRITTEN_TABLES:
            rows = await c.fetchval(f"SELECT count(*) FROM {t}")
            assert rows > 0, f"{t}: the C16 write never landed"
            wrong = await c.fetchval(
                f"SELECT count(*) FROM {t} WHERE book_id IS DISTINCT FROM $1", book,
            )
            assert wrong == 0, f"{t}: {wrong} row(s) carry the wrong book_id on a pending Work"


async def test_a_truly_dangling_project_still_raises(pool):
    """The orphan guard must survive the fix. A project_id matching NO Work — neither by
    project_id nor by surrogate id — has no recoverable book home, so the write must FAIL
    LOUDLY rather than insert a row with a guessed/NULL scope (PM-7,
    `silent-success-is-a-bug-not-environment`)."""
    _work_id, _book, actor = await _pending_work(pool)
    orphan = uuid.uuid4()  # belongs to nothing

    with pytest.raises(ReferenceViolationError):
        await OutlineRepo(pool).create_node(orphan, created_by=actor, kind="chapter",
                                            chapter_id=uuid.uuid4(), title="nowhere")
    with pytest.raises(ReferenceViolationError):
        await CanonRulesRepo(pool).create(orphan, "nowhere", created_by=actor)
    with pytest.raises(ReferenceViolationError):
        await GenerationJobsRepo(pool).create(orphan, created_by=actor, operation="draft_scene",
                                              model_name="test-model")

    async with pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM outline_node WHERE project_id = $1", orphan) == 0
        assert await c.fetchval("SELECT count(*) FROM canon_rule WHERE project_id = $1", orphan) == 0
        assert await c.fetchval("SELECT count(*) FROM generation_job WHERE project_id = $1", orphan) == 0


async def test_a_backed_work_still_resolves_by_project_id(pool):
    """The disjunct must not shadow the normal path: a BACKED Work is still matched by its
    knowledge project_id, and a pending Work on another book cannot capture that write."""
    actor, book_a, book_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    project = uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
            project, actor, book_a,
        )
        # a lazy Work on a DIFFERENT book, sitting in the same table
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id, "
            "pending_project_backfill) VALUES (NULL,$1,$2,true)",
            actor, book_b,
        )
    node = await OutlineRepo(pool).create_node(project, created_by=actor, kind="chapter",
                                              chapter_id=uuid.uuid4(), title="ch1")
    assert node.book_id == book_a, "a backed Work's write resolved to the wrong book"
