"""S1 — the publish gate counts a guard that verified NOTHING as unchecked.

`chapter_scene_gate` listed the unchecked states as ``('skipped_no_position','degraded')``.
`skipped_no_cast` — the ONE state in which the canon guard runs no check at all — was missing,
so it counted as a checked chapter. Measured 2026-08-01: an 8,116-word chapter, an invented
character in three of four scenes, `canon_unchecked_scenes = 0`, publish gate green.

The rule is now `COALESCE(guard_status, status) <> 'checked'` — fail-safe, and a status added
to the enum later is counted as unchecked until someone decides otherwise. This test lives in
integration because the rule is SQL: a unit test with a fake repo cannot see a WHERE clause.

No cleanup, nothing destructive — every row is created under a fresh random project_id.
"""
from __future__ import annotations

import json
import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo

pytestmark = pytest.mark.xdist_group("pg")

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")


@pytest.fixture
async def pool():
    if not _DSN:
        pytest.skip("set TEST_COMPOSITION_DB_URL to a throwaway DB to run")
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=2)
    try:
        await run_migrations(p)
        yield p
    finally:
        await p.close()


async def _scene_with_canon(pool, repo, project, user, book, chapter, canon: dict) -> uuid.UUID:
    """A DONE scene plus the completed generation job whose `result.canon` the gate reads.

    `book_id` is not optional: `generation_job_scope_shape` requires project_id and book_id to
    be present or absent TOGETHER. Omitting it made all four tests fail for a reason that had
    nothing to do with the gate — a reminder to take fixture columns from the schema, not from
    the list of columns the assertion happens to care about."""
    node = await repo.create_node(project, created_by=user, kind="scene",
                                  chapter_id=chapter, status="done")
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO generation_job
              (project_id, book_id, created_by, operation, outline_node_id, mode, status,
               input, result)
            VALUES ($1,$2,$3,'draft_scene',$4,'auto','completed','{}'::jsonb,$5::jsonb)
            """,
            project, book, user, node.id, json.dumps({"canon": canon}),
        )
    return node.id


async def test_a_scene_whose_guard_ran_NOTHING_counts_as_unchecked(pool):
    """The measured false-green. `resolved=True` + `violations=[]` + a guard that checked
    nothing must not read as a verified chapter."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    await _scene_with_canon(pool, repo, project, user, book, chapter, {
        "status": "skipped_no_cast", "guard_status": "no_subject",
        "resolved": True, "violations": [], "coverage": [],
    })

    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["canon_unchecked_scenes"] == 1
    # …and it is SURFACED, not blocking. `canon_blocked` keys on confirmed contradictions
    # only, by a written decision: false-blocking every un-positioned scene would make the
    # gate fire on almost every real book, which is the permanent-amber failure that trains an
    # author to ignore it. The first version of this test asserted `canon_blocked is True` —
    # that was my assumption about the design, not the design.
    assert gate["canon_blocked"] is False
    assert gate["can_publish"] is True


async def test_CONTROL_a_fully_checked_scene_is_not_counted(pool):
    """Without this the fix could be "count everything", which blocks every chapter forever —
    a gate that always fires is as useless as one that never does."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    await _scene_with_canon(pool, repo, project, user, book, chapter, {
        "status": "checked", "guard_status": "checked",
        "resolved": True, "violations": [], "coverage": ["canon_cast", "name_grounding"],
    })

    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["canon_unchecked_scenes"] == 0
    assert gate["canon_blocked"] is False and gate["can_publish"] is True


async def test_a_PRE_S1_row_with_no_guard_status_still_reads_its_legacy_scalar(pool):
    """Rows written before S1 carry only `status`. COALESCE must fall back to it rather than
    treating a NULL as 'checked' — which would silently un-gate the entire existing corpus."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    await _scene_with_canon(pool, repo, project, user, book, chapter, {
        "status": "degraded", "resolved": True, "violations": [],
    })

    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["canon_unchecked_scenes"] == 1


async def test_a_status_NOBODY_enumerated_is_counted_as_unchecked(pool):
    """Fail-safe. The old clause was a list of remembered states, so the one state nobody
    remembered was the one that shipped a defect. `<> 'checked'` means a future enum member is
    conservative by default."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    await _scene_with_canon(pool, repo, project, user, book, chapter, {
        "status": "checked", "guard_status": "some_status_invented_next_year",
        "resolved": True, "violations": [],
    })

    gate = await repo.chapter_scene_gate(project, chapter)
    assert gate["canon_unchecked_scenes"] == 1
