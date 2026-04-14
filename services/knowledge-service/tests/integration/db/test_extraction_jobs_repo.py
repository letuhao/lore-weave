"""K10.4 extraction_jobs repository integration tests.

The headline test is the **atomic-spend concurrency race**: 10
parallel workers each try to reserve the same $0.15 budget slice
against a $1.00 cap, and the test asserts that:

  1. The total `cost_spent_usd` never exceeds `max_spend_usd` by
     more than one item's reservation (worst-case one-item
     overshoot per KSA §5.5).
  2. Exactly the correct count of workers succeeds and the rest
     get `not_running`.
  3. After the dust settles, `status = 'paused'` on the job row.

All other tests cover the 8 non-atomic repo methods plus the
NULL-budget unlimited path.

Tests use the `pool` fixture from conftest.py (module-local; wires
to the live compose postgres). They TRUNCATE between tests.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.db.models import ProjectCreate
from app.db.repositories.extraction_jobs import (
    ExtractionJobCreate,
    ExtractionJobsRepo,
    TrySpendResult,
)
from app.db.repositories.projects import ProjectsRepo


# ── helpers ─────────────────────────────────────────────────────────────


async def _make_project(pool, user_id: UUID) -> UUID:
    """Seed a knowledge_projects row so the extraction_jobs FK can
    point to it. Returns the project_id."""
    repo = ProjectsRepo(pool)
    proj = await repo.create(
        user_id,
        ProjectCreate(name="K10.4 test", project_type="general"),
    )
    return proj.project_id


def _job_payload(
    project_id: UUID,
    *,
    max_spend_usd: Decimal | None = Decimal("1.00"),
    scope: str = "chapters",
) -> ExtractionJobCreate:
    return ExtractionJobCreate(
        project_id=project_id,
        scope=scope,  # type: ignore[arg-type]
        llm_model="test-llm",
        embedding_model="test-embed",
        max_spend_usd=max_spend_usd,
    )


# ── basic CRUD ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_4_create_defaults(pool):
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    job = await repo.create(user, _job_payload(project_id))
    assert job.user_id == user
    assert job.project_id == project_id
    assert job.scope == "chapters"
    assert job.status == "pending"
    assert job.items_processed == 0
    assert job.cost_spent_usd == Decimal("0")
    assert job.llm_model == "test-llm"
    assert job.embedding_model == "test-embed"
    assert job.max_spend_usd == Decimal("1.0000")
    assert job.started_at is None
    assert job.paused_at is None
    assert job.completed_at is None
    assert job.error_message is None


@pytest.mark.asyncio
async def test_k10_4_get_cross_user_isolation(pool):
    repo = ExtractionJobsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    job = await repo.create(user_a, _job_payload(project_a))

    # Same job_id, different user → None.
    assert await repo.get(user_b, job.job_id) is None
    # Correct user → full row.
    got = await repo.get(user_a, job.job_id)
    assert got is not None and got.job_id == job.job_id


@pytest.mark.asyncio
async def test_k10_4_list_for_project(pool):
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    # Three jobs, all for the same project.
    for _ in range(3):
        await repo.create(user, _job_payload(project_id))
    jobs = await repo.list_for_project(user, project_id)
    assert len(jobs) == 3
    assert all(j.project_id == project_id for j in jobs)


@pytest.mark.asyncio
async def test_k10_4_list_active_filters_terminal_states(pool):
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    j_pending = await repo.create(user, _job_payload(project_id))
    j_running = await repo.create(user, _job_payload(project_id))
    j_complete = await repo.create(user, _job_payload(project_id))
    j_failed = await repo.create(user, _job_payload(project_id))
    j_cancelled = await repo.create(user, _job_payload(project_id))

    await repo.update_status(user, j_running.job_id, "running")
    await repo.update_status(user, j_complete.job_id, "complete")
    await repo.update_status(user, j_failed.job_id, "failed")
    await repo.update_status(user, j_cancelled.job_id, "cancelled")

    active = await repo.list_active(user)
    active_ids = {j.job_id for j in active}
    assert j_pending.job_id in active_ids
    assert j_running.job_id in active_ids
    assert j_complete.job_id not in active_ids
    assert j_failed.job_id not in active_ids
    assert j_cancelled.job_id not in active_ids


@pytest.mark.asyncio
async def test_k10_4_update_status_sets_started_at_once(pool):
    """`started_at` should only be set the first time the job
    transitions to `running` — not clobbered on a subsequent
    running → paused → running cycle."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))

    running1 = await repo.update_status(user, job.job_id, "running")
    assert running1 is not None and running1.started_at is not None
    first_start = running1.started_at

    await repo.update_status(user, job.job_id, "paused")
    running2 = await repo.update_status(user, job.job_id, "running")
    assert running2 is not None and running2.started_at == first_start


@pytest.mark.asyncio
async def test_k10_4_update_status_sets_completed_at(pool):
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    await repo.update_status(user, job.job_id, "running")
    completed = await repo.complete(user, job.job_id)
    assert completed is not None
    assert completed.status == "complete"
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_k10_4_update_status_records_error_message(pool):
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    failed = await repo.update_status(
        user, job.job_id, "failed", error_message="llm refused"
    )
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_message == "llm refused"
    assert failed.completed_at is not None


@pytest.mark.asyncio
async def test_k10_4_advance_cursor(pool):
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    advanced = await repo.advance_cursor(
        user, job.job_id, {"chapter_index": 5}, items_processed_delta=3
    )
    assert advanced is not None
    assert advanced.current_cursor == {"chapter_index": 5}
    assert advanced.items_processed == 3
    # Second advance accumulates.
    advanced2 = await repo.advance_cursor(
        user, job.job_id, {"chapter_index": 7}
    )
    assert advanced2 is not None
    assert advanced2.items_processed == 4
    assert advanced2.current_cursor == {"chapter_index": 7}


# ── try_spend: pre-conditions ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_4_try_spend_pending_job_returns_not_running(pool):
    """A pending job has not been started yet — try_spend must
    refuse to reserve budget."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    result = await repo.try_spend(user, job.job_id, Decimal("0.10"))
    assert result.outcome == "not_running"
    # Defense-in-depth: cost_spent_usd unchanged.
    current = await repo.get(user, job.job_id)
    assert current is not None and current.cost_spent_usd == Decimal("0")


@pytest.mark.asyncio
async def test_k10_4_try_spend_cross_user_returns_not_running(pool):
    """User B cannot reserve budget on User A's job even with a
    valid job_id. Same security boundary as every other repo
    method."""
    repo = ExtractionJobsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    job = await repo.create(user_a, _job_payload(project_a))
    await repo.update_status(user_a, job.job_id, "running")

    result = await repo.try_spend(user_b, job.job_id, Decimal("0.10"))
    assert result.outcome == "not_running"
    # A's row unchanged.
    a_view = await repo.get(user_a, job.job_id)
    assert a_view is not None and a_view.cost_spent_usd == Decimal("0")


@pytest.mark.asyncio
async def test_k10_4_try_spend_null_budget_is_unlimited(pool):
    """max_spend_usd IS NULL means unlimited. Every try_spend
    returns `reserved` regardless of cumulative cost."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id, max_spend_usd=None))
    await repo.update_status(user, job.job_id, "running")

    for _ in range(5):
        result = await repo.try_spend(user, job.job_id, Decimal("100.00"))
        assert result.outcome == "reserved"
    current = await repo.get(user, job.job_id)
    assert current is not None
    assert current.cost_spent_usd == Decimal("500.0000")
    assert current.status == "running"


@pytest.mark.asyncio
async def test_k10_4_try_spend_auto_pauses_on_cap(pool):
    """When the reservation would push cost_spent_usd >= cap, the
    same UPDATE both reserves AND transitions to paused. The last
    worker "wins" their reservation but subsequent calls see
    not_running."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    # Cap = $0.30, each reservation $0.15 → exactly 2 succeed, the
    # 2nd trips the pause.
    job = await repo.create(
        user, _job_payload(project_id, max_spend_usd=Decimal("0.30"))
    )
    await repo.update_status(user, job.job_id, "running")

    r1 = await repo.try_spend(user, job.job_id, Decimal("0.15"))
    assert r1.outcome == "reserved"
    assert r1.new_cost_spent_usd == Decimal("0.1500")

    r2 = await repo.try_spend(user, job.job_id, Decimal("0.15"))
    assert r2.outcome == "auto_paused"
    assert r2.new_cost_spent_usd == Decimal("0.3000")
    assert r2.new_status == "paused"

    r3 = await repo.try_spend(user, job.job_id, Decimal("0.15"))
    assert r3.outcome == "not_running"

    # Post-conditions on the row.
    job_row = await repo.get(user, job.job_id)
    assert job_row is not None
    assert job_row.status == "paused"
    assert job_row.cost_spent_usd == Decimal("0.3000")
    assert job_row.paused_at is not None


# ── try_spend: the concurrency race ─────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_4_try_spend_concurrency_race(pool):
    """**The headline test.** 10 parallel workers, $0.15 reservation
    each, $1.00 cap. Total attempted = $1.50 but only $1.00 should
    fit, with worst-case one-item overshoot ($0.15) allowed per
    KSA §5.5. The test asserts:

      - exactly the right count of workers report `reserved` or
        `auto_paused` (budget reservation succeeded)
      - the rest report `not_running` (refused cleanly)
      - the final row's `cost_spent_usd` equals succeeded-count *
        estimate
      - cost_spent_usd <= max + estimate (one-item overshoot rule)
      - exactly ONE worker reports auto_paused (the boundary trip)
      - status is paused at the end
    """
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(
        user, _job_payload(project_id, max_spend_usd=Decimal("1.00"))
    )
    await repo.update_status(user, job.job_id, "running")

    estimated = Decimal("0.15")
    n_workers = 10

    async def worker() -> TrySpendResult:
        return await repo.try_spend(user, job.job_id, estimated)

    results = await asyncio.gather(*(worker() for _ in range(n_workers)))

    outcomes = [r.outcome for r in results]
    reserved_count = outcomes.count("reserved")
    paused_count = outcomes.count("auto_paused")
    refused_count = outcomes.count("not_running")

    succeeded = reserved_count + paused_count
    # 0.15 * 7 = 1.05 >= 1.00 → 7th call trips the pause
    # so exactly 7 successful reservations + 3 refusals expected.
    assert succeeded == 7, f"expected 7 successes, got {outcomes}"
    assert refused_count == 3, f"expected 3 refusals, got {outcomes}"
    # Exactly one worker sees the pause transition — the one whose
    # reservation pushed cumulative cost over the cap.
    assert paused_count == 1, (
        f"expected exactly 1 auto_paused, got {paused_count} "
        f"(outcomes={outcomes})"
    )

    # Post-conditions on the DB row.
    job_row = await repo.get(user, job.job_id)
    assert job_row is not None
    assert job_row.status == "paused"
    # cost_spent_usd = successes * estimate
    assert job_row.cost_spent_usd == estimated * succeeded
    # Overshoot is bounded by one item's estimate per KSA §5.5.
    assert job_row.cost_spent_usd <= Decimal("1.00") + estimated
    assert job_row.paused_at is not None


@pytest.mark.asyncio
async def test_k10_4_try_spend_concurrency_race_with_small_estimates(pool):
    """Second concurrency test with a finer-grained estimate to
    flush out any off-by-one in the boundary condition. 20 workers,
    $0.05 each, $0.50 cap → exactly 10 succeed."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(
        user, _job_payload(project_id, max_spend_usd=Decimal("0.50"))
    )
    await repo.update_status(user, job.job_id, "running")

    estimated = Decimal("0.05")
    n_workers = 20

    results = await asyncio.gather(
        *(repo.try_spend(user, job.job_id, estimated) for _ in range(n_workers))
    )
    outcomes = [r.outcome for r in results]
    succeeded = outcomes.count("reserved") + outcomes.count("auto_paused")
    # 0.05 * 10 = 0.50 >= 0.50 → 10th call trips pause → 10 succeed.
    assert succeeded == 10, f"expected 10 successes, got {outcomes}"

    job_row = await repo.get(user, job.job_id)
    assert job_row is not None
    assert job_row.status == "paused"
    assert job_row.cost_spent_usd == Decimal("0.5000")
