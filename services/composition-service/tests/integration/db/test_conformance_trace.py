"""W5 — motif-conformance trace JOIN integration test (real Postgres).

Gated on TEST_COMPOSITION_DB_URL (a THROWAWAY DB — the fixture drops the touched
tables on setup AND teardown). Exercises the W5-owned ConformanceTraceReader
against the REAL schema — the seam W2 will populate (motif_application rows with
motif_id + beat_key-in-annotations) and the existing generation_job.critic.

Covered:
  - apps_by_nodes returns the bound motif per node, most-recent per node, and is
    TENANT-scoped (a foreign user's binding is NOT returned).
  - latest_completed_by_nodes returns the LATEST completed job per node + its
    critic.motif_conformance, projects has_text (not the prose blob), and ignores
    non-completed jobs.
  - the full read assembles planned│realized│conformance correctly end-to-end.
"""

from __future__ import annotations

import json
import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.routers.conformance import ConformanceTraceReader, _assemble_conformance

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

_TABLES = ["motif_application", "generation_job", "outline_node", "motif"]


async def _drop(p: asyncpg.Pool) -> None:
    async with p.acquire() as c:
        for t in _TABLES:
            await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        await _drop(p)
        await run_migrations(p)
        yield p
    finally:
        await _drop(p)
        await p.close()


# Package re-key (spec 25): outline_node / motif_application / generation_job
# carry `created_by` (the actor stamp — renamed from user_id) + `book_id NOT NULL`
# (the tenancy scope key). These raw INSERTs must supply both explicitly.
async def _scene(c, *, created_by, project_id, book_id, chapter_id, beat_role="bait", tension=72):
    return await c.fetchval(
        """
        INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, title,
                                  beat_role, status, chapter_id, tension)
        VALUES ($1,$2,$3,'scene','aaa','S',$4,'done',$5,$6) RETURNING id
        """,
        created_by, project_id, book_id, beat_role, chapter_id, tension,
    )


async def _bind(c, *, created_by, project_id, book_id, node_id, motif_id, beat_key="bait"):
    return await c.fetchval(
        """
        INSERT INTO motif_application (created_by, project_id, book_id, motif_id,
                                       motif_version, outline_node_id, role_bindings,
                                       annotations)
        VALUES ($1,$2,$3,$4,1,$5,$6::jsonb,$7::jsonb) RETURNING id
        """,
        created_by, project_id, book_id, motif_id, node_id,
        json.dumps({"schemer": str(uuid.uuid4())}),
        json.dumps({"beat_key": beat_key}),
    )


async def _job(c, *, created_by, project_id, book_id, node_id, status="completed",
               critic=None, text="prose"):
    return await c.fetchval(
        """
        INSERT INTO generation_job (created_by, project_id, book_id, outline_node_id,
                                    operation, status, result, critic)
        VALUES ($1,$2,$3,$4,'draft_scene',$5,$6::jsonb,$7::jsonb) RETURNING id
        """,
        created_by, project_id, book_id, node_id, status,
        json.dumps({"text": text}) if text is not None else None,
        json.dumps(critic) if critic is not None else None,
    )


async def _seed_motif(c) -> uuid.UUID:
    return await c.fetchval(
        "INSERT INTO motif (owner_user_id, code, language, visibility, name) "
        "VALUES ($1,'m','en','private','M') RETURNING id",
        uuid.uuid4(),
    )


async def test_apps_by_nodes_project_scoped_not_actor_scoped(pool):
    # NEW LAW (spec 25 PM-8, re-keyed from the old per-user isolation): the trace
    # reads are PROJECT-scoped, not user-scoped. Access is decided at the E0
    # book-grant gate BEFORE this reader; `created_by` is a plain actor stamp,
    # never filtered on. So a co-author's binding in the SAME project is visible
    # (created_by is not a filter), while a DIFFERENT project's binding never
    # leaks — the `WHERE project_id = $1` predicate is the isolation dimension
    # (the kinds-bug rule). This replaces the old assertion that a foreign USER's
    # binding was hidden by a user_id predicate, which is no longer the law.
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    proj, proj_foreign = uuid.uuid4(), uuid.uuid4()
    book, book_foreign = uuid.uuid4(), uuid.uuid4()
    chap = uuid.uuid4()
    reader = ConformanceTraceReader(pool)
    async with pool.acquire() as c:
        m_id = await _seed_motif(c)
        n1 = await _scene(c, created_by=u1, project_id=proj, book_id=book, chapter_id=chap)
        await _bind(c, created_by=u1, project_id=proj, book_id=book, node_id=n1,
                    motif_id=m_id, beat_key="bait")
        # a co-author (different actor) binding in the SAME project → still visible
        n_coauthor = await _scene(c, created_by=u2, project_id=proj, book_id=book, chapter_id=chap)
        await _bind(c, created_by=u2, project_id=proj, book_id=book, node_id=n_coauthor,
                    motif_id=m_id, beat_key="turn")
        # a DIFFERENT project's binding must NOT leak into this project's trace
        n_foreign = await _scene(c, created_by=u1, project_id=proj_foreign,
                                 book_id=book_foreign, chapter_id=chap)
        await _bind(c, created_by=u1, project_id=proj_foreign, book_id=book_foreign,
                    node_id=n_foreign, motif_id=m_id)

    got = await reader.apps_by_nodes(proj, [n1, n_coauthor, n_foreign])
    assert n1 in got
    assert got[n1].motif_id == m_id
    assert got[n1].annotations.get("beat_key") == "bait"
    # co-author binding in the same project IS returned (created_by is not a filter)
    assert n_coauthor in got
    # the foreign PROJECT's binding is filtered out by the project_id predicate
    assert n_foreign not in got


async def test_latest_completed_by_nodes_projects_dim_and_skips_noncompleted(pool):
    u1 = uuid.uuid4()
    proj = uuid.uuid4()
    book = uuid.uuid4()
    chap = uuid.uuid4()
    reader = ConformanceTraceReader(pool)
    dim = {"beat_realized": True, "tension_band_match": False, "calibrated": False}
    async with pool.acquire() as c:
        n1 = await _scene(c, created_by=u1, project_id=proj, book_id=book, chapter_id=chap)
        # an OLDER failed job + a NEWER completed job → the completed one wins
        await _job(c, created_by=u1, project_id=proj, book_id=book, node_id=n1,
                   status="failed", critic=None)
        await _job(c, created_by=u1, project_id=proj, book_id=book, node_id=n1,
                   status="completed", critic={"coherence": 4, "motif_conformance": dim})

    got = await reader.latest_completed_by_nodes(proj, [n1])
    assert n1 in got
    assert got[n1]["has_text"] is True
    assert got[n1]["critic"]["motif_conformance"] == dim
    # the prose blob is NOT projected — only the presence boolean
    assert "result" not in got[n1] and "text" not in got[n1]


async def test_full_trace_assembles_end_to_end(pool):
    u1 = uuid.uuid4()
    proj = uuid.uuid4()
    book = uuid.uuid4()
    chap = uuid.uuid4()
    reader = ConformanceTraceReader(pool)
    dim = {"beat_realized": True, "tension_band_match": False, "calibrated": False,
           "reason": "ok", "error": None}
    async with pool.acquire() as c:
        m_id = await _seed_motif(c)
        n1 = await _scene(c, created_by=u1, project_id=proj, book_id=book, chapter_id=chap, tension=72)
        await _bind(c, created_by=u1, project_id=proj, book_id=book, node_id=n1,
                    motif_id=m_id, beat_key="bait")
        await _job(c, created_by=u1, project_id=proj, book_id=book, node_id=n1,
                   status="completed", critic={"coherence": 5, "motif_conformance": dim})

    from app.db.repositories.outline import OutlineRepo
    scenes = await OutlineRepo(pool).scenes_for_chapter(proj, chap)
    apps = await reader.apps_by_nodes(proj, [s.id for s in scenes])
    latest = await reader.latest_completed_by_nodes(proj, [s.id for s in scenes])
    out = _assemble_conformance(
        chapter_id=chap, calibrated=False, scenes=scenes,
        apps_by_node=apps, latest_by_node=latest,
    )
    assert len(out["scenes"]) == 1
    s = out["scenes"][0]
    assert s["planned"]["motif_id"] == str(m_id)
    assert s["planned"]["beat_key"] == "bait"
    assert s["planned"]["tension"] == 72
    assert s["realized"]["has_prose"] is True
    assert s["conformance"]["beat_realized"] is True
    assert s["conformance"]["tension_band_match"] is False
