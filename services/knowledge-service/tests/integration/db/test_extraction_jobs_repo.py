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
    # Three jobs on the same project. K16.3's
    # idx_extraction_jobs_one_active_per_project unique index only
    # permits ONE row with status in ('pending','running','paused')
    # per project at any instant, so the first two jobs must be
    # cycled to a terminal state before the next create.
    job1 = await repo.create(user, _job_payload(project_id))
    await repo.update_status(user, job1.job_id, "running")
    await repo.complete(user, job1.job_id)
    job2 = await repo.create(user, _job_payload(project_id))
    await repo.update_status(user, job2.job_id, "running")
    await repo.update_status(
        user, job2.job_id, "failed", error_message="stub",
    )
    job3 = await repo.create(user, _job_payload(project_id))  # stays pending
    jobs = await repo.list_for_project(user, project_id)
    assert len(jobs) == 3
    assert all(j.project_id == project_id for j in jobs)
    assert {j.job_id for j in jobs} == {job1.job_id, job2.job_id, job3.job_id}


@pytest.mark.asyncio
async def test_k10_4_list_active_filters_terminal_states(pool):
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    # list_active filters across ALL of the user's projects, so put
    # each job on its own project — K16.3's one-active-job-per-project
    # unique partial index would otherwise reject having both a
    # pending and a running job on the same project simultaneously,
    # which is exactly the end-state this test needs to assert.
    p_pending = await _make_project(pool, user)
    p_running = await _make_project(pool, user)
    p_complete = await _make_project(pool, user)
    p_failed = await _make_project(pool, user)
    p_cancelled = await _make_project(pool, user)

    j_pending = await repo.create(user, _job_payload(p_pending))
    j_running = await repo.create(user, _job_payload(p_running))
    j_complete = await repo.create(user, _job_payload(p_complete))
    j_failed = await repo.create(user, _job_payload(p_failed))
    j_cancelled = await repo.create(user, _job_payload(p_cancelled))

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
    # K10.4-I2: cursor advance only allowed on running/paused jobs.
    await repo.update_status(user, job.job_id, "running")
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


# ── K10.4 review-fix regressions ────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_4_i1_update_status_rejects_terminal_complete(pool):
    """K10.4-I1: a complete job cannot be transitioned back to running.
    The UPDATE matches 0 rows and the method returns None. Any
    `try_spend` against the still-complete job continues to return
    `not_running`."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    await repo.update_status(user, job.job_id, "running")
    await repo.complete(user, job.job_id)

    # Attempt resurrection: should return None.
    revived = await repo.update_status(user, job.job_id, "running")
    assert revived is None
    # Row unchanged.
    current = await repo.get(user, job.job_id)
    assert current is not None
    assert current.status == "complete"
    assert current.completed_at is not None

    # Defense-in-depth: try_spend on the still-complete job returns
    # not_running, no money leaked.
    result = await repo.try_spend(user, job.job_id, Decimal("0.10"))
    assert result.outcome == "not_running"
    current2 = await repo.get(user, job.job_id)
    assert current2 is not None
    assert current2.cost_spent_usd == Decimal("0")


@pytest.mark.asyncio
async def test_k10_4_i1_update_status_rejects_terminal_cancelled(pool):
    """K10.4-I1: cancelled jobs are likewise terminal."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    await repo.update_status(user, job.job_id, "running")
    await repo.cancel(user, job.job_id)

    for target in ("running", "paused", "pending", "complete"):
        revived = await repo.update_status(user, job.job_id, target)  # type: ignore[arg-type]
        assert revived is None, f"transition cancelled → {target} should be blocked"
    current = await repo.get(user, job.job_id)
    assert current is not None
    assert current.status == "cancelled"


@pytest.mark.asyncio
async def test_k10_4_i1_update_status_rejects_terminal_failed(pool):
    """K10.4-I1: failed jobs are terminal — the retry use case is
    served by creating a new job, not resurrecting the old one."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    await repo.update_status(user, job.job_id, "running")
    await repo.update_status(user, job.job_id, "failed", error_message="llm refused")

    revived = await repo.update_status(user, job.job_id, "running")
    assert revived is None
    current = await repo.get(user, job.job_id)
    assert current is not None
    assert current.status == "failed"
    # K10.4-I3: the error_message set on the failed transition is
    # preserved across the failed call (it can't be cleared because
    # nothing can transition out of failed).
    assert current.error_message == "llm refused"


@pytest.mark.asyncio
async def test_k10_4_i3_error_message_cleared_on_non_failed_transition(pool):
    """K10.4-I3: error_message is only kept when the target state is
    `failed`. Every other (non-terminal) transition clears any prior
    error message. Combined with I1 (failed is terminal) this means
    error_message is write-once per job lifetime — set on the single
    `* → failed` transition and never touched again."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    # Hypothetical: a stale error_message somehow persisted on a
    # non-failed row. Simulate via direct SQL bypass since the API
    # path now clears it on every non-failed transition.
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE extraction_jobs SET error_message = $1 WHERE job_id = $2",
            "stale error",
            job.job_id,
        )

    # Any non-failed transition clears it.
    running = await repo.update_status(user, job.job_id, "running")
    assert running is not None
    assert running.error_message is None


@pytest.mark.asyncio
async def test_k10_4_i2_advance_cursor_rejects_terminal_states(pool):
    """K10.4-I2: advance_cursor only succeeds on running/paused jobs.
    Terminal jobs (complete/cancelled/failed) AND pending jobs (not
    yet dispatched) all return None.

    Each job lives on its own project because K16.3's
    idx_extraction_jobs_one_active_per_project unique partial index
    wouldn't allow a pending job to coexist with another pending /
    running / paused job on the same project."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()

    # Pending — not dispatched yet, can't advance cursor.
    pending_project = await _make_project(pool, user)
    pending_job = await repo.create(user, _job_payload(pending_project))
    result = await repo.advance_cursor(user, pending_job.job_id, {"x": 1})
    assert result is None

    # Complete — terminal.
    complete_project = await _make_project(pool, user)
    complete_job = await repo.create(user, _job_payload(complete_project))
    await repo.update_status(user, complete_job.job_id, "running")
    await repo.complete(user, complete_job.job_id)
    result = await repo.advance_cursor(user, complete_job.job_id, {"x": 1})
    assert result is None

    # Cancelled — terminal.
    cancelled_project = await _make_project(pool, user)
    cancelled_job = await repo.create(user, _job_payload(cancelled_project))
    await repo.update_status(user, cancelled_job.job_id, "running")
    await repo.cancel(user, cancelled_job.job_id)
    result = await repo.advance_cursor(user, cancelled_job.job_id, {"x": 1})
    assert result is None

    # Failed — terminal.
    failed_project = await _make_project(pool, user)
    failed_job = await repo.create(user, _job_payload(failed_project))
    await repo.update_status(user, failed_job.job_id, "running")
    await repo.update_status(user, failed_job.job_id, "failed", error_message="x")
    result = await repo.advance_cursor(user, failed_job.job_id, {"x": 1})
    assert result is None

    # Paused — allowed (worker may drain in-flight work before
    # fully stopping).
    paused_project = await _make_project(pool, user)
    paused_job = await repo.create(user, _job_payload(paused_project))
    await repo.update_status(user, paused_job.job_id, "running")
    await repo.update_status(user, paused_job.job_id, "paused")
    result = await repo.advance_cursor(user, paused_job.job_id, {"x": 1})
    assert result is not None
    assert result.items_processed == 1


@pytest.mark.asyncio
async def test_k10_4_i7_advance_cursor_rejects_negative_delta(pool):
    """K10.4-I7: `items_processed_delta` must be non-negative.
    Negative values would corrupt the progress counter."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    job = await repo.create(user, _job_payload(project_id))
    await repo.update_status(user, job.job_id, "running")

    with pytest.raises(ValueError, match="items_processed_delta"):
        await repo.advance_cursor(
            user, job.job_id, {"x": 1}, items_processed_delta=-1
        )

    # Zero is allowed (cursor-only update without an item advance).
    result = await repo.advance_cursor(
        user, job.job_id, {"x": 2}, items_processed_delta=0
    )
    assert result is not None
    assert result.items_processed == 0
    assert result.current_cursor == {"x": 2}


def test_k10_4_i4_create_rejects_negative_max_spend():
    """K10.4-I4: ExtractionJobCreate Pydantic validation rejects
    negative max_spend_usd at construction time. Caller never gets
    to the SQL layer."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtractionJobCreate(
            project_id=uuid4(),
            scope="chapters",
            llm_model="test",
            embedding_model="test",
            max_spend_usd=Decimal("-0.01"),
        )


def test_k10_4_i4_create_rejects_empty_model_strings():
    """K10.4-I4: llm_model and embedding_model must be non-empty.
    The extraction worker would fail cryptically on '' so we catch
    it at the model boundary."""
    from pydantic import ValidationError
    for kwargs in (
        {"llm_model": "", "embedding_model": "ok"},
        {"llm_model": "ok", "embedding_model": ""},
    ):
        with pytest.raises(ValidationError):
            ExtractionJobCreate(
                project_id=uuid4(),
                scope="chapters",
                **kwargs,  # type: ignore[arg-type]
            )


def test_k10_4_i4_create_rejects_negative_items_total():
    """K10.4-I4: items_total is an optional non-negative int."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtractionJobCreate(
            project_id=uuid4(),
            scope="chapters",
            llm_model="ok",
            embedding_model="ok",
            items_total=-1,
        )


# ── K19b.1: list_all_for_user (user-scoped, grouped) ────────────────────


@pytest.mark.asyncio
async def test_k19b_1_list_all_active_filters_terminal_states(pool):
    """active group = pending/running/paused, excludes terminal states."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    p_pending = await _make_project(pool, user)
    p_running = await _make_project(pool, user)
    p_paused = await _make_project(pool, user)
    p_complete = await _make_project(pool, user)
    p_failed = await _make_project(pool, user)
    p_cancelled = await _make_project(pool, user)

    j_pending = await repo.create(user, _job_payload(p_pending))
    j_running = await repo.create(user, _job_payload(p_running))
    j_paused = await repo.create(user, _job_payload(p_paused))
    j_complete = await repo.create(user, _job_payload(p_complete))
    j_failed = await repo.create(user, _job_payload(p_failed))
    j_cancelled = await repo.create(user, _job_payload(p_cancelled))

    await repo.update_status(user, j_running.job_id, "running")
    await repo.update_status(user, j_paused.job_id, "running")
    await repo.update_status(user, j_paused.job_id, "paused")
    await repo.update_status(user, j_complete.job_id, "complete")
    await repo.update_status(user, j_failed.job_id, "failed")
    await repo.update_status(user, j_cancelled.job_id, "cancelled")

    rows, _ = await repo.list_all_for_user(user, status_group="active")
    ids = {j.job_id for j in rows}
    assert ids == {j_pending.job_id, j_running.job_id, j_paused.job_id}


@pytest.mark.asyncio
async def test_k19b_1_list_all_history_filters_active_states(pool):
    """history group = complete/failed/cancelled, excludes active states."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    p_pending = await _make_project(pool, user)
    p_running = await _make_project(pool, user)
    p_complete = await _make_project(pool, user)
    p_failed = await _make_project(pool, user)
    p_cancelled = await _make_project(pool, user)

    j_pending = await repo.create(user, _job_payload(p_pending))
    j_running = await repo.create(user, _job_payload(p_running))
    j_complete = await repo.create(user, _job_payload(p_complete))
    j_failed = await repo.create(user, _job_payload(p_failed))
    j_cancelled = await repo.create(user, _job_payload(p_cancelled))

    await repo.update_status(user, j_running.job_id, "running")
    await repo.update_status(user, j_complete.job_id, "complete")
    await repo.update_status(user, j_failed.job_id, "failed")
    await repo.update_status(user, j_cancelled.job_id, "cancelled")

    rows, _ = await repo.list_all_for_user(user, status_group="history")
    ids = {j.job_id for j in rows}
    assert ids == {j_complete.job_id, j_failed.job_id, j_cancelled.job_id}
    assert j_pending.job_id not in ids
    assert j_running.job_id not in ids


@pytest.mark.asyncio
async def test_k19b_1_list_all_is_user_isolated(pool):
    """Cross-user leak probe: user A's jobs must not appear in user B's list."""
    repo = ExtractionJobsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    p_a = await _make_project(pool, user_a)
    p_b = await _make_project(pool, user_b)

    j_a = await repo.create(user_a, _job_payload(p_a))
    j_b = await repo.create(user_b, _job_payload(p_b))

    a_rows, _ = await repo.list_all_for_user(user_a, status_group="active")
    b_rows, _ = await repo.list_all_for_user(user_b, status_group="active")

    assert {j.job_id for j in a_rows} == {j_a.job_id}
    assert {j.job_id for j in b_rows} == {j_b.job_id}


@pytest.mark.asyncio
async def test_k19b_1_list_all_limit_is_clamped(pool):
    """limit < 1 is clamped to 1; limit > 200 is clamped to 200."""
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    # Seed 3 active jobs on 3 projects.
    for _ in range(3):
        p = await _make_project(pool, user)
        await repo.create(user, _job_payload(p))

    rows_zero, _ = await repo.list_all_for_user(user, status_group="active", limit=0)
    assert len(rows_zero) == 1  # clamped up to 1
    rows_two, _ = await repo.list_all_for_user(user, status_group="active", limit=2)
    assert len(rows_two) == 2
    rows_huge, _ = await repo.list_all_for_user(user, status_group="active", limit=10_000)
    assert len(rows_huge) == 3  # clamped down to 200 but only 3 rows exist


@pytest.mark.asyncio
async def test_k19b_2_list_all_populates_project_name(pool):
    """K19b.2 Q2(c): rows carry project_name via LEFT JOIN."""
    repo = ExtractionJobsRepo(pool)
    projects_repo = ProjectsRepo(pool)
    user = uuid4()
    proj_alpha = await projects_repo.create(
        user, ProjectCreate(name="Alpha Book", project_type="book"),
    )
    proj_beta = await projects_repo.create(
        user, ProjectCreate(name="Beta Translation", project_type="translation"),
    )
    await repo.create(user, _job_payload(proj_alpha.project_id))
    await repo.create(user, _job_payload(proj_beta.project_id))

    rows, _ = await repo.list_all_for_user(user, status_group="active")
    names = {j.project_id: j.project_name for j in rows}
    assert names[proj_alpha.project_id] == "Alpha Book"
    assert names[proj_beta.project_id] == "Beta Translation"


@pytest.mark.asyncio
async def test_k19b_2_list_all_project_name_null_when_join_misses(pool):
    """Defence: if the FK cascade is ever bypassed (test fixtures,
    partial migrations, etc.) the LEFT JOIN returns NULL rather than
    dropping the row.

    We can't trigger this through the repo API because `create`
    requires a real project row, so we simulate it by (a) seeding
    through the normal repo path, then (b) forcibly DELETING the
    knowledge_projects row with replication-role replica so the FK
    CASCADE doesn't also drop the extraction_jobs row. This keeps
    the schema intact regardless of whether the assertions below
    fail — unlike ALTER TABLE DROP/ADD, which can brick the DB if
    the test is interrupted between the drop and the restore.
    """
    repo = ExtractionJobsRepo(pool)
    projects_repo = ProjectsRepo(pool)
    user = uuid4()
    proj = await projects_repo.create(
        user, ProjectCreate(name="Orphan-target", project_type="book"),
    )
    job = await repo.create(user, _job_payload(proj.project_id))

    async with pool.acquire() as conn:
        # `replication_role=replica` makes the session skip FK triggers
        # (and other user triggers). Scoped to this single connection's
        # transaction only; no schema change, no lasting side effects.
        async with conn.transaction():
            await conn.execute("SET LOCAL session_replication_role = 'replica'")
            await conn.execute(
                "DELETE FROM knowledge_projects WHERE project_id = $1",
                proj.project_id,
            )

    rows, _ = await repo.list_all_for_user(user, status_group="active")

    assert len(rows) == 1
    assert rows[0].job_id == job.job_id
    assert rows[0].project_name is None


@pytest.mark.asyncio
async def test_k19b_1_list_all_history_orders_by_completed_at(pool):
    """History ordered by completed_at DESC NULLS LAST, then created_at DESC.

    Seed 3 jobs completing in a known order; expect list to come back
    in reverse-completion order. A 4th job with NULL completed_at
    (hypothetical legacy row: status set to 'failed' without the
    update_status path clearing error / timestamp bookkeeping) falls
    to the end via NULLS LAST. We can't create that shape through the
    repo API cleanly, so the test asserts the happy path only; the
    NULLS LAST guarantee is covered by the SQL itself.
    """
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    p1 = await _make_project(pool, user)
    p2 = await _make_project(pool, user)
    p3 = await _make_project(pool, user)
    j1 = await repo.create(user, _job_payload(p1))
    j2 = await repo.create(user, _job_payload(p2))
    j3 = await repo.create(user, _job_payload(p3))

    # Complete j1 first, then j3, then j2 — reverse order by completed_at
    # should therefore be j2, j3, j1.
    await repo.update_status(user, j1.job_id, "complete")
    await asyncio.sleep(0.02)
    await repo.update_status(user, j3.job_id, "complete")
    await asyncio.sleep(0.02)
    await repo.update_status(user, j2.job_id, "complete")

    rows, _ = await repo.list_all_for_user(user, status_group="history")
    assert [j.job_id for j in rows] == [j2.job_id, j3.job_id, j1.job_id]


# ── C11 — cursor pagination ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c11_cursor_pagination_walks_full_history_without_duplicates(pool):
    """C11 (D-K19b.1-01 + D-K19b.2-01) regression lock for the SQL
    cursor predicate.

    Seeds 7 complete jobs, pages through with limit=3, and asserts:
    (a) every job appears exactly once across all pages (no
    duplicates from a broken row-value compare), (b) pages concat to
    the same order as a single unpaginated fetch (the cursor predicate
    matches the ORDER BY), (c) ``next_cursor`` is null on the final
    page. Without this test the novel 4-branch NULLS-LAST OR is only
    exercised by mocked unit tests.
    """
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    projects = [await _make_project(pool, user) for _ in range(7)]
    jobs = [await repo.create(user, _job_payload(p)) for p in projects]
    for j in jobs:
        await repo.update_status(user, j.job_id, "complete")
        # Tiny sleep so completed_at distinguishes each job — uuidv7
        # still tiebreaks on same-microsecond collisions but distinct
        # timestamps make the expectation easy to write.
        await asyncio.sleep(0.02)

    # Single unpaginated fetch establishes the expected order.
    all_rows, last_cursor_single = await repo.list_all_for_user(
        user, status_group="history", limit=100,
    )
    assert last_cursor_single is None  # 7 rows < 100 limit → final page
    expected_order = [j.job_id for j in all_rows]
    assert len(expected_order) == 7

    # Walk the same data in pages of 3 via cursor.
    collected: list = []
    cursor = None
    iterations = 0
    while True:
        iterations += 1
        assert iterations <= 5, "guard against runaway pagination loop"
        page, next_cursor = await repo.list_all_for_user(
            user, status_group="history", limit=3, cursor=cursor,
        )
        collected.extend(j.job_id for j in page)
        if next_cursor is None:
            break
        cursor = next_cursor

    # Pagination must visit every job exactly once in the same order
    # as the single-shot fetch.
    assert collected == expected_order


@pytest.mark.asyncio
async def test_c11_cursor_pagination_stable_across_tied_completed_at(pool):
    """C11: even when two jobs share completed_at to the microsecond,
    the (created_at, job_id) tiebreak in the cursor predicate keeps
    them in a deterministic order and doesn't skip or duplicate rows.

    We can't easily seed identical completed_at through the repo API
    (update_status uses clock_timestamp() or similar), so this test
    is a lighter check than the one above — it just confirms that
    paginating over a small set with limit=1 visits every row exactly
    once, which covers the tiebreak branches of the WHERE predicate
    indirectly.
    """
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    projects = [await _make_project(pool, user) for _ in range(3)]
    jobs = [await repo.create(user, _job_payload(p)) for p in projects]
    for j in jobs:
        await repo.update_status(user, j.job_id, "complete")

    seen: list = []
    cursor = None
    for _ in range(5):
        page, next_cursor = await repo.list_all_for_user(
            user, status_group="history", limit=1, cursor=cursor,
        )
        seen.extend(j.job_id for j in page)
        if next_cursor is None:
            break
        cursor = next_cursor

    assert len(seen) == 3
    assert len(set(seen)) == 3  # no duplicates


# ── C12a — list_active_for_project ─────────────────────────────────────


@pytest.mark.asyncio
async def test_c12a_list_active_for_project_filters_to_active_statuses(pool):
    """C12a (D-K16.2-02b) — ``list_active_for_project`` must return
    pending/running/paused jobs and drop complete/failed/cancelled.

    The handler gate depends on this filter being correct; a silent
    regression that expanded the filter to include completed jobs
    would keep stale jobs' ``scope_range`` influencing live event
    ingestion.
    """
    repo = ExtractionJobsRepo(pool)
    user = uuid4()
    project = await _make_project(pool, user)

    j_pending = await repo.create(user, _job_payload(project))
    j_running = await repo.create(user, _job_payload(project))
    j_paused = await repo.create(user, _job_payload(project))
    j_complete = await repo.create(user, _job_payload(project))
    j_failed = await repo.create(user, _job_payload(project))
    j_cancelled = await repo.create(user, _job_payload(project))

    await repo.update_status(user, j_running.job_id, "running")
    await repo.update_status(user, j_paused.job_id, "paused")
    await repo.update_status(user, j_complete.job_id, "complete")
    await repo.update_status(user, j_failed.job_id, "failed")
    await repo.update_status(user, j_cancelled.job_id, "cancelled")
    # j_pending stays in 'pending'

    active = await repo.list_active_for_project(user, project)
    ids = {j.job_id for j in active}
    assert ids == {j_pending.job_id, j_running.job_id, j_paused.job_id}
    # Terminal statuses excluded.
    assert j_complete.job_id not in ids
    assert j_failed.job_id not in ids
    assert j_cancelled.job_id not in ids


@pytest.mark.asyncio
async def test_c12a_list_active_for_project_is_user_isolated(pool):
    """C12a — cross-user isolation. User A's active job on their own
    project must not appear in a call scoped to user B, even when
    querying the SAME project_id (unlikely in practice because
    project_id is user-scoped, but the repo doesn't rely on that —
    it filters on user_id AND project_id)."""
    repo = ExtractionJobsRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    project_b = await _make_project(pool, user_b)

    j_a = await repo.create(user_a, _job_payload(project_a))
    await repo.update_status(user_a, j_a.job_id, "running")
    j_b = await repo.create(user_b, _job_payload(project_b))
    await repo.update_status(user_b, j_b.job_id, "running")

    # User A sees their job on their project.
    a_active = await repo.list_active_for_project(user_a, project_a)
    assert {j.job_id for j in a_active} == {j_a.job_id}
    # User A sees NOTHING on user B's project (user_id filter rejects).
    a_on_b = await repo.list_active_for_project(user_a, project_b)
    assert a_on_b == []
    # User B mirror.
    b_active = await repo.list_active_for_project(user_b, project_b)
    assert {j.job_id for j in b_active} == {j_b.job_id}
