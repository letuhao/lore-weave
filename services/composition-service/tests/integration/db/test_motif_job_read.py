"""W0-BE1 / BE-7c — a Work-LESS generation_job, CREATABLE then READABLE (real DB).

THE PAID-ACTION DEFECT this file exists to kill:
`_execute_motif_mine` enqueues with `project_id=None` (a book/corpus mine is genuinely not
Work-bound). `_enqueue_motif_job` (actions.py:552) then stamped a SYNTHETIC `uuid4()` pid.
`GenerationJobsRepo.create()` inserts via `INSERT … SELECT $1,$2,w.book_id,… FROM composition_work
WHERE w.project_id = $2` — because `generation_job.book_id` was `UUID NOT NULL` and is DERIVED from
the Work inside the statement. A synthetic pid matches NO row ⇒ zero rows inserted ⇒
`ReferenceViolationError("project … has no composition_work row")` ⇒ **`POST /actions/confirm` 500s**
— AFTER `_claim_or_replay` burnt the confirm token and `_precheck_or_402` reserved the billing hold.
The job row is never created. The user pays and gets nothing.

🔴 EVERY JOB ROW BELOW IS CREATED THROUGH THE PRODUCER (`create_unbound()` / `_enqueue_motif_job`),
never a raw INSERT. A fixture that raw-INSERTs the row seeds a shape the writer can never emit, and
the suite then goes green over a live-broken path
(memory: `fixtures-can-seed-a-field-the-writer-never-sets`). The ONE raw INSERT here is the
NEGATIVE test — it asserts the DB rejects a half-null row.

Gated on TEST_COMPOSITION_DB_URL (throwaway DB — drops tables).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import httpx
import pytest

from app.db.migrate import run_migrations
from app.db.repositories import ReferenceViolationError
from app.db.repositories.generation_jobs import GenerationJobsRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),  # MANDATORY — a real-DB test on a shared PG.
]

_TABLES = (
    "generation_correction", "generation_job", "decompose_commit", "scene_grounding_pins",
    "scene_link", "narrative_thread", "canon_rule", "style_profile", "voice_profile",
    "reference_source", "entity_override", "divergence_spec", "outline_node",
    "composition_work",
)

USER = uuid.uuid4()
OTHER = uuid.uuid4()


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


@pytest.fixture
async def client(pool):
    """The REAL route over the REAL repo bound to the throwaway pool. Only auth is stubbed.

    httpx ASGITransport, NOT TestClient: TestClient drives the app on its OWN event loop
    (a blocking portal), while the asyncpg pool above is created on pytest-asyncio's loop —
    asyncpg connections are loop-bound, so TestClient yields "attached to a different loop".
    ASGITransport runs the app in THIS loop, so the route touches the same live pool the
    producer wrote through. Lifespan is deliberately not run (nothing here needs it).
    """
    from app.main import app
    from app.deps import get_generation_jobs_repo, get_grant_client_dep, get_works_repo
    from app.db.repositories.works import WorksRepo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    class _StubGrant:
        """The E0 book-grant authority at OWNER. Deliberately PERMISSIVE: the old
        `GET /jobs/{id}` must still 404 on an unbound job even when the grant would
        say yes — proving the Work gate is refused for want of a Work, not for want
        of a grant."""
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER

        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_generation_jobs_repo] = lambda: GenerationJobsRepo(pool)
    app.dependency_overrides[get_works_repo] = lambda: WorksRepo(pool)
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


# ── the WRITER — the actual paid-action bug ──────────────────────────────────


async def test_an_unbound_job_can_be_CREATED_at_all(pool):
    """🔴 REDS AT HEAD. Today the only writer is `create()`, which derives book_id from
    composition_work and raises ReferenceViolationError for a Work-less job. THIS is the
    paid-action defect: no job row is ever written, so /actions/confirm 500s after the
    token is burnt and the billing hold reserved."""
    jobs = GenerationJobsRepo(pool)
    job = await jobs.create_unbound(created_by=USER, operation="mine_motifs",
                                    input={"worker_op": "mine_motifs", "scope": "corpus"})
    assert job.project_id is None, "an unbound job must carry NO Work partition key"
    assert job.book_id is None, "an unbound job must carry NO book key"
    assert job.created_by == USER, "created_by IS the scope key for these rows"
    assert job.status == "pending"


async def test_create_unbound_rejects_a_work_bound_operation(pool):
    """A Work-bound op arriving here would SILENTLY LOSE its tenancy keys. That is a
    tenancy defect, not a shortcut — the writer must refuse it."""
    jobs = GenerationJobsRepo(pool)
    with pytest.raises(ValueError):
        await jobs.create_unbound(created_by=USER, operation="draft_scene")


async def test_the_scope_shape_check_rejects_a_half_null_row(pool):
    """The tenancy-hole lock: a job is EITHER Work-scoped (both keys) or owner-scoped
    (neither). A book_id with no project (or vice versa) must be UNWRITABLE."""
    async with pool.acquire() as c:
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO generation_job (created_by, project_id, book_id, operation) "
                "VALUES ($1, $2, NULL, 'mine_motifs')",
                USER, uuid.uuid4(),
            )


async def test_the_confirm_path_no_longer_500s(pool, monkeypatch):
    """🔴 REDS AT HEAD (ReferenceViolationError). Drives the REAL producer
    `_enqueue_motif_job(project_id=None)` — the exact call `_execute_motif_mine` makes.
    This is the leg the FE poll (W0-S7) depends on: without a job_id there is nothing
    to poll, and the user has already been charged."""
    import app.db.pool as pool_mod
    import app.worker.events as events_mod
    from app.routers.actions import _enqueue_motif_job

    monkeypatch.setattr(pool_mod, "get_pool", lambda: pool)
    enqueued: list[dict] = []

    async def _fake_enqueue(redis_url, *, job_id, user_id, project_id):
        enqueued.append({"job_id": job_id, "user_id": user_id, "project_id": project_id})
        return True

    monkeypatch.setattr(events_mod, "enqueue_job", _fake_enqueue)

    job_id = await _enqueue_motif_job(
        envelope_user=USER, project_id=None, operation="mine_motifs",
        spec={"scope": "corpus", "min_support": 3},
    )
    assert uuid.UUID(job_id), "the confirm path must return a REAL job id, not raise"
    assert enqueued and enqueued[0]["job_id"] == job_id
    # The stream carries no project for an unbound job; run_job re-loads by id anyway.
    assert enqueued[0]["project_id"] == ""

    row = await GenerationJobsRepo(pool).get(uuid.UUID(job_id))
    assert row is not None and row.project_id is None and row.created_by == USER


async def test_the_work_bound_confirm_path_still_creates_a_bound_job(pool, monkeypatch):
    """Regression: the Work-BOUND branch (conformance_run) must still derive book_id
    from composition_work. `create()` is the hot path for every draft — do not touch it."""
    import app.db.pool as pool_mod
    import app.worker.events as events_mod
    from app.routers.actions import _enqueue_motif_job

    monkeypatch.setattr(pool_mod, "get_pool", lambda: pool)

    async def _fake_enqueue(redis_url, **kw):
        return True

    monkeypatch.setattr(events_mod, "enqueue_job", _fake_enqueue)

    project_id, book_id = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1, $2, $3)",
            project_id, USER, book_id,
        )
    job_id = await _enqueue_motif_job(
        envelope_user=USER, project_id=project_id, operation="conformance_run", spec={},
    )
    row = await GenerationJobsRepo(pool).get(uuid.UUID(job_id))
    assert row is not None and row.project_id == project_id and row.book_id == book_id


# ── the READER — the owner gate ──────────────────────────────────────────────


async def test_synthetic_project_job_is_readable_by_its_owner(pool, client):
    job = await GenerationJobsRepo(pool).create_unbound(
        created_by=USER, operation="mine_motifs")
    r = await client.get(f"/v1/composition/motif-jobs/{job.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["project_id"] is None and body["book_id"] is None


async def test_other_user_gets_404_not_403(pool, client):
    """⚠ NO ENUMERATION ORACLE (H13): a non-owner must be BYTE-IDENTICAL to a missing row.
    A 403 would confirm the job exists."""
    job = await GenerationJobsRepo(pool).create_unbound(
        created_by=OTHER, operation="mine_motifs")
    r = await client.get(f"/v1/composition/motif-jobs/{job.id}")
    assert r.status_code == 404
    assert r.json()["detail"] == "job not found"

    missing = await client.get(f"/v1/composition/motif-jobs/{uuid.uuid4()}")
    assert missing.status_code == 404
    # The whole point: denial and absence are indistinguishable, byte for byte.
    assert r.json() == missing.json()


async def test_missing_job_is_404(client):
    r = await client.get(f"/v1/composition/motif-jobs/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["detail"] == "job not found"


async def test_the_old_route_still_404s_on_an_unbound_job(pool, client):
    """Proves the new route is ADDITIVE, not a loosening of the Work-scoped gate.
    `GET /jobs/{id}` gates on the job's project→book grant; an unbound job has no
    project, so it must still 404 there."""
    job = await GenerationJobsRepo(pool).create_unbound(
        created_by=USER, operation="mine_motifs")
    r = await client.get(f"/v1/composition/jobs/{job.id}")
    assert r.status_code == 404
