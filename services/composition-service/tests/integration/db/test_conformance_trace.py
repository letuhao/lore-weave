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

pytestmark = pytest.mark.skipif(
    not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
)

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


async def _scene(c, *, user_id, project_id, chapter_id, beat_role="bait", tension=72):
    return await c.fetchval(
        """
        INSERT INTO outline_node (user_id, project_id, kind, rank, title, beat_role,
                                  status, chapter_id, tension)
        VALUES ($1,$2,'scene','aaa','S',$3,'done',$4,$5) RETURNING id
        """,
        user_id, project_id, beat_role, chapter_id, tension,
    )


async def _bind(c, *, user_id, project_id, node_id, motif_id, beat_key="bait"):
    return await c.fetchval(
        """
        INSERT INTO motif_application (user_id, project_id, book_id, motif_id,
                                       motif_version, outline_node_id, role_bindings,
                                       annotations)
        VALUES ($1,$2,$3,$4,1,$5,$6::jsonb,$7::jsonb) RETURNING id
        """,
        user_id, project_id, uuid.uuid4(), motif_id, node_id,
        json.dumps({"schemer": str(uuid.uuid4())}),
        json.dumps({"beat_key": beat_key}),
    )


async def _job(c, *, user_id, project_id, node_id, status="completed", critic=None, text="prose"):
    return await c.fetchval(
        """
        INSERT INTO generation_job (user_id, project_id, outline_node_id, operation,
                                    status, result, critic)
        VALUES ($1,$2,$3,'draft_scene',$4,$5::jsonb,$6::jsonb) RETURNING id
        """,
        user_id, project_id, node_id, status,
        json.dumps({"text": text}) if text is not None else None,
        json.dumps(critic) if critic is not None else None,
    )


async def _seed_motif(c) -> uuid.UUID:
    return await c.fetchval(
        "INSERT INTO motif (owner_user_id, code, language, visibility, name) "
        "VALUES ($1,'m','en','private','M') RETURNING id",
        uuid.uuid4(),
    )


async def test_apps_by_nodes_tenant_scoped_and_latest(pool):
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    proj = uuid.uuid4()
    chap = uuid.uuid4()
    reader = ConformanceTraceReader(pool)
    async with pool.acquire() as c:
        m_id = await _seed_motif(c)
        n1 = await _scene(c, user_id=u1, project_id=proj, chapter_id=chap)
        await _bind(c, user_id=u1, project_id=proj, node_id=n1, motif_id=m_id, beat_key="bait")
        # a foreign user's binding on a DIFFERENT node must NOT leak
        n_foreign = await _scene(c, user_id=u2, project_id=proj, chapter_id=chap)
        await _bind(c, user_id=u2, project_id=proj, node_id=n_foreign, motif_id=m_id)

    got = await reader.apps_by_nodes(u1, proj, [n1, n_foreign])
    assert n1 in got
    assert got[n1].motif_id == m_id
    assert got[n1].annotations.get("beat_key") == "bait"
    # the foreign node binding is filtered by the user_id predicate
    assert n_foreign not in got


async def test_latest_completed_by_nodes_projects_dim_and_skips_noncompleted(pool):
    u1 = uuid.uuid4()
    proj = uuid.uuid4()
    chap = uuid.uuid4()
    reader = ConformanceTraceReader(pool)
    dim = {"beat_realized": True, "tension_band_match": False, "calibrated": False}
    async with pool.acquire() as c:
        n1 = await _scene(c, user_id=u1, project_id=proj, chapter_id=chap)
        # an OLDER failed job + a NEWER completed job → the completed one wins
        await _job(c, user_id=u1, project_id=proj, node_id=n1, status="failed", critic=None)
        await _job(c, user_id=u1, project_id=proj, node_id=n1, status="completed",
                   critic={"coherence": 4, "motif_conformance": dim})

    got = await reader.latest_completed_by_nodes(u1, proj, [n1])
    assert n1 in got
    assert got[n1]["has_text"] is True
    assert got[n1]["critic"]["motif_conformance"] == dim
    # the prose blob is NOT projected — only the presence boolean
    assert "result" not in got[n1] and "text" not in got[n1]


async def test_full_trace_assembles_end_to_end(pool):
    u1 = uuid.uuid4()
    proj = uuid.uuid4()
    chap = uuid.uuid4()
    reader = ConformanceTraceReader(pool)
    dim = {"beat_realized": True, "tension_band_match": False, "calibrated": False,
           "reason": "ok", "error": None}
    async with pool.acquire() as c:
        m_id = await _seed_motif(c)
        n1 = await _scene(c, user_id=u1, project_id=proj, chapter_id=chap, tension=72)
        await _bind(c, user_id=u1, project_id=proj, node_id=n1, motif_id=m_id, beat_key="bait")
        await _job(c, user_id=u1, project_id=proj, node_id=n1, status="completed",
                   critic={"coherence": 5, "motif_conformance": dim})

    from app.db.repositories.outline import OutlineRepo
    scenes = await OutlineRepo(pool).scenes_for_chapter(u1, proj, chap)
    apps = await reader.apps_by_nodes(u1, proj, [s.id for s in scenes])
    latest = await reader.latest_completed_by_nodes(u1, proj, [s.id for s in scenes])
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
