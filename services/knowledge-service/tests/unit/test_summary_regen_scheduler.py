"""K20.3 — unit tests for the project summary regen scheduler.

Covers ``sweep_projects_once`` contract matrix:
  - advisory-lock skip
  - empty project list returns 0/0/0
  - missing ``llm_model`` → ``no_model`` counter
  - regen status mapping (regenerated / no_op_* / user_edit_lock /
    concurrent_edit / exception)
  - per-project error isolation
  - model_resolution query failure per project

The loop wrapper's timing behaviour is tested separately via a fake
sleep + CancelledError assertion.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest

from app.jobs.regenerate_summaries import RegenerationResult
from app.jobs.summary_regen_scheduler import (
    DEFAULT_GLOBAL_INTERVAL_S,
    DEFAULT_GLOBAL_STARTUP_DELAY_S,
    DEFAULT_INTERVAL_S,
    DEFAULT_STARTUP_DELAY_S,
    run_global_regen_loop,
    run_project_regen_loop,
    sweep_global_once,
    sweep_projects_once,
)


# ── fakes ───────────────────────────────────────────────────────────


class FakeConn:
    """Minimal async-pool-connection stand-in. Records executed SQL +
    returns canned results from a scripted sequence.

    Supports BOTH schedulers:
      - Project loop: ``projects`` list + project-scoped model_lookup
        keyed on ``(user_id, project_id)``
      - Global loop: ``users`` list + user-wide user_model_lookup
        keyed on ``user_id`` alone
    """

    def __init__(
        self,
        *,
        try_lock: bool = True,
        projects: list[dict] | None = None,
        users: list[dict] | None = None,
        model_lookup: dict[tuple[str, str], str | None] | None = None,
        user_model_lookup: dict[str, str | None] | None = None,
        model_lookup_raises: set[tuple[str, str]] | None = None,
        user_model_lookup_raises: set[str] | None = None,
    ):
        self._try_lock = try_lock
        self._projects = projects or []
        self._users = users or []
        self._model_lookup = model_lookup or {}
        self._user_model_lookup = user_model_lookup or {}
        self._model_lookup_raises = model_lookup_raises or set()
        self._user_model_lookup_raises = user_model_lookup_raises or set()
        self.executed: list[str] = []

    async def fetchval(self, sql: str, *args):
        self.executed.append(sql.strip()[:40])
        if "pg_try_advisory_lock" in sql:
            return self._try_lock
        if "FROM extraction_jobs" in sql:
            # Review-impl C3: route by SQL WHERE-clause text rather
            # than ``len(args)``. A future test that accidentally
            # passes 1 arg to the project-scoped lookup (or 2 to the
            # user-wide one) would silently hit the wrong branch under
            # arg-count routing. SQL-text matching ties the fake to
            # the exact production code paths.
            if "project_id = $2" in sql:
                # _LATEST_LLM_MODEL_SQL — project-scoped lookup.
                key = (str(args[0]), str(args[1]))
                if key in self._model_lookup_raises:
                    raise RuntimeError("boom from fetchval")
                return self._model_lookup.get(key)
            # _LATEST_USER_LLM_MODEL_SQL — user-wide lookup (no
            # project_id predicate).
            key_user = str(args[0])
            if key_user in self._user_model_lookup_raises:
                raise RuntimeError("boom from fetchval (user-wide)")
            return self._user_model_lookup.get(key_user)
        return None

    async def fetch(self, sql: str):
        self.executed.append(sql.strip()[:40])
        # Global eligibility query returns one-column rows keyed
        # ``user_id`` — distinguish from project-list by SQL text.
        if "FROM knowledge_summaries" in sql:
            return [dict(r) for r in self._users]
        return [dict(r) for r in self._projects]

    async def execute(self, sql: str, *args):
        self.executed.append(sql.strip()[:40])


class FakePool:
    def __init__(self, conn: FakeConn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        @asynccontextmanager
        async def _cm():
            yield conn

        return _cm()


def _project(user_id: str, project_id: str) -> dict:
    return {"user_id": user_id, "project_id": project_id}


def _regen_result(status: str) -> RegenerationResult:
    """Build a RegenerationResult stub that the scheduler can inspect.

    We use ``model_construct`` (Pydantic's validation-skipping
    factory) rather than the normal constructor for two reasons:

    1. The ``test_sweep_unknown_regen_status_counts_as_errored_with_warning``
       test NEEDS to pass a status value outside the
       ``RegenerationStatus`` Literal union — the scheduler has a
       defensive ``else`` branch for forward-compat when a new status
       is added to the regen helper but not yet to the scheduler.
       Pydantic's normal constructor would reject the unknown string
       and the defensive branch would be unreachable-in-tests (dead
       code at the assertion layer).
    2. The scheduler only reads ``.status`` — a half-initialised
       ``summary=None`` on the happy-path stubs doesn't exercise any
       scheduler code path. Using the same factory for all stubs
       keeps the test fixtures uniform.

    Risk: if the regen helper grows a ``@model_validator`` that
    derives fields (e.g. ``skipped_reason`` from ``status``) and the
    scheduler starts reading those, these stubs won't exercise the
    derivation. That's a β concern — wire it up once the scheduler
    actually consumes the derived fields.
    """
    return RegenerationResult.model_construct(status=status, summary=None)


# ── sweep_projects_once ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sweep_lock_skipped_returns_zeroed():
    conn = FakeConn(try_lock=False)
    pool = FakePool(conn)
    result = await sweep_projects_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.lock_skipped is True
    assert result.projects_considered == 0
    assert result.regenerated == 0
    # Advisory unlock NOT called when lock wasn't acquired.
    assert not any("pg_advisory_unlock" in sql for sql in conn.executed)


@pytest.mark.asyncio
async def test_sweep_empty_project_list_returns_zero_counters_and_releases_lock():
    conn = FakeConn(try_lock=True, projects=[])
    pool = FakePool(conn)
    result = await sweep_projects_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.lock_skipped is False
    assert result.projects_considered == 0
    # Lock released even on empty-list path.
    assert any("pg_advisory_unlock" in sql for sql in conn.executed)


@pytest.mark.asyncio
async def test_sweep_no_prior_extraction_job_skips_as_no_model(monkeypatch):
    user_id = str(uuid4())
    project_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        projects=[_project(user_id, project_id)],
        model_lookup={(user_id, project_id): None},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock()
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        regen_mock,
    )
    result = await sweep_projects_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 1
    assert result.no_model == 1
    assert result.regenerated == 0
    # Regen helper NOT called when llm_model resolution came back None.
    regen_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected_counter",
    [
        ("regenerated", "regenerated"),
        ("no_op_similarity", "no_op"),
        ("no_op_empty_source", "no_op"),
        ("no_op_guardrail", "no_op"),
        ("user_edit_lock", "skipped"),
        ("regen_concurrent_edit", "skipped"),
    ],
)
async def test_sweep_maps_regen_status_to_counter(
    monkeypatch, status, expected_counter,
):
    user_id = str(uuid4())
    project_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        projects=[_project(user_id, project_id)],
        model_lookup={(user_id, project_id): "gpt-4o-mini"},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock(return_value=_regen_result(status))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        regen_mock,
    )
    result = await sweep_projects_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 1
    assert getattr(result, expected_counter) == 1
    # Regen helper called with model from extraction_jobs lookup.
    regen_mock.assert_awaited_once()
    kwargs = regen_mock.await_args.kwargs
    assert kwargs["model_source"] == "user_model"
    assert kwargs["model_ref"] == "gpt-4o-mini"
    assert kwargs["user_id"] == UUID(user_id)
    assert kwargs["project_id"] == UUID(project_id)
    # C2: scheduler forwards trigger='scheduled' so the metric series
    # can split scheduled from manual regens. A regression dropping
    # the kwarg (or flipping it to 'manual') would silently conflate
    # the two in the counter output — lock it here.
    assert kwargs["trigger"] == "scheduled"


@pytest.mark.asyncio
async def test_sweep_unknown_regen_status_counts_as_errored_with_warning(
    monkeypatch, caplog,
):
    """Defensive: a future regen helper adding a new status value
    lands in the ``errored`` bucket + emits a warning so we notice
    rather than silently double-counting."""
    import logging
    user_id = str(uuid4())
    project_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        projects=[_project(user_id, project_id)],
        model_lookup={(user_id, project_id): "gpt-4o-mini"},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock(
        return_value=_regen_result("novel_future_status"),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        regen_mock,
    )
    with caplog.at_level(logging.WARNING):
        result = await sweep_projects_once(
            pool=pool,  # type: ignore[arg-type]
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
        )
    assert result.errored == 1
    assert any("unrecognized regen status" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_sweep_per_project_regen_exception_is_isolated(monkeypatch):
    """One failing project shouldn't stop the sweep — the next
    project still runs + gets counted correctly."""
    user_id = str(uuid4())
    good = str(uuid4())
    bad = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        # Sort order matters — SQL orders by project_id. Use stable
        # fixed UUIDs so the bad one comes first and the good one
        # second (or vice versa) deterministically.
        projects=[_project(user_id, bad), _project(user_id, good)],
        model_lookup={
            (user_id, bad): "gpt-4o-mini",
            (user_id, good): "gpt-4o-mini",
        },
    )
    pool = FakePool(conn)

    async def regen_impl(**kwargs):
        if str(kwargs["project_id"]) == bad:
            raise RuntimeError("project regen exploded")
        return _regen_result("regenerated")

    regen_mock = AsyncMock(side_effect=regen_impl)
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        regen_mock,
    )
    result = await sweep_projects_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 2
    assert result.regenerated == 1
    assert result.errored == 1
    # Both projects were attempted (regen called twice).
    assert regen_mock.await_count == 2


@pytest.mark.asyncio
async def test_sweep_model_lookup_error_counts_as_errored(monkeypatch):
    """Even the model-lookup subquery failing shouldn't kill the
    sweep — that project gets ``errored``, next one continues."""
    user_id = str(uuid4())
    bad = str(uuid4())
    good = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        projects=[_project(user_id, bad), _project(user_id, good)],
        model_lookup={(user_id, good): "gpt-4o-mini"},
        model_lookup_raises={(user_id, bad)},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock(return_value=_regen_result("regenerated"))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        regen_mock,
    )
    result = await sweep_projects_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 2
    assert result.errored == 1  # bad project
    assert result.regenerated == 1  # good project
    # Only called for the good project (bad project exited early at
    # model lookup, never reached the regen call).
    assert regen_mock.await_count == 1


@pytest.mark.asyncio
async def test_sweep_lock_released_on_mid_sweep_exception(monkeypatch):
    """Safety: if the sweep body raises unexpectedly (e.g. fetch()
    blows up), the advisory lock must still be released so the next
    run can pick up. Tests the ``try: ... finally: unlock`` contract."""
    class ExplodingConn(FakeConn):
        async def fetch(self, sql):
            self.executed.append(sql.strip()[:40])
            raise RuntimeError("fetch exploded")

    conn = ExplodingConn(try_lock=True)
    pool = FakePool(conn)
    with pytest.raises(RuntimeError, match="fetch exploded"):
        await sweep_projects_once(
            pool=pool,  # type: ignore[arg-type]
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
        )
    # Lock was released even though the sweep raised.
    assert any("pg_advisory_unlock" in sql for sql in conn.executed)


# ── run_project_regen_loop ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_loop_cancellation_during_startup_delay(monkeypatch):
    """CancelledError during the startup delay should propagate
    cleanly (lifespan teardown path)."""

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await run_project_regen_loop(
            pool=MagicMock(),
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
            startup_delay_s=1,
        )


@pytest.mark.asyncio
async def test_loop_runs_one_sweep_then_cancels_during_interval_sleep(
    monkeypatch,
):
    """Startup delay returns immediately (call #1), then sweep runs
    once, then CancelledError fires inside the post-sweep interval
    sleep (call #2). Verifies the happy cadence without waiting 24h.

    Note: the loop body's `if startup_delay_s > 0` guard means we
    MUST pass a non-zero value to exercise the startup-sleep path,
    so the fake_sleep call count aligns with the sweep count."""
    sweep_mock = AsyncMock()
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.sweep_projects_once", sweep_mock,
    )

    call_count = {"n": 0}

    async def fake_sleep(_seconds):
        call_count["n"] += 1
        # First call: startup delay — return immediately.
        # Second call: post-sweep interval — cancel to exit loop.
        if call_count["n"] >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await run_project_regen_loop(
            pool=MagicMock(),
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
            startup_delay_s=1,
            interval_s=100,
        )
    sweep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_loop_continues_when_sweep_raises_non_cancel(monkeypatch):
    """A non-Cancel exception in sweep shouldn't kill the loop — it
    should log + sleep for the next cycle. Ends test via
    CancelledError on the second sleep."""
    call_count = {"sweep": 0}

    async def raising_sweep(*_args, **_kwargs):
        # sweep_projects_once is called positionally with
        # (pool, session_factory, llm_client, summaries_repo);
        # accept *_args so the stub absorbs any call shape.
        call_count["sweep"] += 1
        if call_count["sweep"] == 1:
            raise RuntimeError("first sweep blew up")
        # Second sweep succeeds, returns nothing useful.
        return MagicMock()

    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.sweep_projects_once",
        raising_sweep,
    )

    sleep_count = {"n": 0}

    async def fake_sleep(_seconds):
        sleep_count["n"] += 1
        # Pass startup_delay_s=1 so startup sleep counts:
        # startup(1) + post-sweep-1(2) + post-sweep-2(3) = 3 sleeps.
        # Cancel on 3rd → 2 sweeps ran (sweep-1 crashed, sweep-2
        # succeeded).
        if sleep_count["n"] >= 3:
            raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await run_project_regen_loop(
            pool=MagicMock(),
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
            startup_delay_s=1,
            interval_s=100,
        )
    # Two sweeps attempted — proof the exception didn't kill the loop.
    assert call_count["sweep"] == 2


def test_defaults_are_24h_and_10min():
    """Lock in the cadence defaults. Tweaking these silently would
    change production behaviour without review; this test forces the
    author to update the assertion deliberately."""
    assert DEFAULT_INTERVAL_S == 24 * 60 * 60
    assert DEFAULT_STARTUP_DELAY_S == 600


# ═══════════════════════════════════════════════════════════════
# K20.3 Cycle β — sweep_global_once
# ═══════════════════════════════════════════════════════════════


def _user(user_id: str) -> dict:
    """Global eligibility returns rows with just ``user_id``."""
    return {"user_id": user_id}


@pytest.mark.asyncio
async def test_sweep_global_lock_skipped_returns_zeroed():
    conn = FakeConn(try_lock=False)
    pool = FakePool(conn)
    result = await sweep_global_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.lock_skipped is True
    assert result.projects_considered == 0
    # Lock unlock NOT called when lock wasn't acquired.
    assert not any("pg_advisory_unlock" in sql for sql in conn.executed)


@pytest.mark.asyncio
async def test_sweep_global_empty_eligibility_releases_lock():
    conn = FakeConn(try_lock=True, users=[])
    pool = FakePool(conn)
    result = await sweep_global_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.lock_skipped is False
    assert result.projects_considered == 0
    assert any("pg_advisory_unlock" in sql for sql in conn.executed)


@pytest.mark.asyncio
async def test_sweep_global_no_extraction_anywhere_skips_as_no_model(
    monkeypatch,
):
    """User with an eligibility entry but NO prior extraction job in
    any of their projects has no llm_model to borrow — counted as
    ``no_model`` and skipped without touching the regen helper."""
    user_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        users=[_user(user_id)],
        user_model_lookup={user_id: None},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock()
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_global_summary",
        regen_mock,
    )
    result = await sweep_global_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 1
    assert result.no_model == 1
    assert result.regenerated == 0
    regen_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected_counter",
    [
        ("regenerated", "regenerated"),
        ("no_op_similarity", "no_op"),
        ("no_op_empty_source", "no_op"),
        ("no_op_guardrail", "no_op"),
        ("user_edit_lock", "skipped"),
        ("regen_concurrent_edit", "skipped"),
    ],
)
async def test_sweep_global_maps_regen_status_to_counter(
    monkeypatch, status, expected_counter,
):
    """Mirror the project sweep's status-mapping test for the global
    loop — same 6-to-4 collapse."""
    user_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        users=[_user(user_id)],
        user_model_lookup={user_id: "gpt-4o-mini"},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock(return_value=_regen_result(status))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_global_summary",
        regen_mock,
    )
    result = await sweep_global_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 1
    assert getattr(result, expected_counter) == 1
    regen_mock.assert_awaited_once()
    kwargs = regen_mock.await_args.kwargs
    assert kwargs["model_source"] == "user_model"
    assert kwargs["model_ref"] == "gpt-4o-mini"
    assert kwargs["user_id"] == UUID(user_id)
    # No project_id on global regen — it's an L0 scope.
    assert "project_id" not in kwargs
    # C2: same trigger='scheduled' contract as the project sweep.
    assert kwargs["trigger"] == "scheduled"


@pytest.mark.asyncio
async def test_sweep_global_per_user_regen_exception_isolated(monkeypatch):
    good = str(uuid4())
    bad = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        users=[_user(bad), _user(good)],
        user_model_lookup={bad: "gpt-4o-mini", good: "gpt-4o-mini"},
    )
    pool = FakePool(conn)

    async def regen_impl(**kwargs):
        if str(kwargs["user_id"]) == bad:
            raise RuntimeError("user regen exploded")
        return _regen_result("regenerated")

    regen_mock = AsyncMock(side_effect=regen_impl)
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_global_summary",
        regen_mock,
    )
    result = await sweep_global_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 2
    assert result.regenerated == 1
    assert result.errored == 1
    # Both users were attempted.
    assert regen_mock.await_count == 2


@pytest.mark.asyncio
async def test_sweep_global_user_model_lookup_error_counts_as_errored(
    monkeypatch,
):
    bad = str(uuid4())
    good = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        users=[_user(bad), _user(good)],
        user_model_lookup={good: "gpt-4o-mini"},
        user_model_lookup_raises={bad},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock(return_value=_regen_result("regenerated"))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_global_summary",
        regen_mock,
    )
    result = await sweep_global_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert result.projects_considered == 2
    assert result.errored == 1
    assert result.regenerated == 1
    # Regen only called for good user; bad user exited at model lookup.
    assert regen_mock.await_count == 1


@pytest.mark.asyncio
async def test_sweep_global_emits_completion_log_with_counter_breakdown(
    monkeypatch, caplog,
):
    """Mirror α's C3 regression lock on the global sweep as well.
    Log format must contain all 6 counter names so operator dashboards
    can scrape counts without parsing each line by hand."""
    import logging
    user_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        users=[_user(user_id)],
        user_model_lookup={user_id: "gpt-4o-mini"},
    )
    pool = FakePool(conn)
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_global_summary",
        AsyncMock(return_value=_regen_result("regenerated")),
    )
    with caplog.at_level(logging.INFO):
        await sweep_global_once(
            pool=pool,  # type: ignore[arg-type]
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
        )
    completion_logs = [
        r for r in caplog.records
        if r.levelno == logging.INFO
        and "global regen sweep complete" in r.message
    ]
    assert len(completion_logs) == 1
    msg = completion_logs[0].getMessage()
    for counter_name in (
        "considered=", "regenerated=", "no_op=",
        "skipped=", "no_model=", "errored=",
    ):
        assert counter_name in msg


@pytest.mark.asyncio
async def test_global_loop_cancellation_during_startup_delay(monkeypatch):
    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await run_global_regen_loop(
            pool=MagicMock(),
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
            startup_delay_s=1,
        )


def test_global_defaults_are_7d_and_15min():
    """Lock the weekly cadence + 15-min startup delay per plan."""
    assert DEFAULT_GLOBAL_INTERVAL_S == 7 * 24 * 60 * 60
    assert DEFAULT_GLOBAL_STARTUP_DELAY_S == 900


@pytest.mark.asyncio
async def test_sweep_emits_completion_log_with_counter_breakdown(
    monkeypatch, caplog,
):
    """Review-impl C3 regression lock — sweep must emit an INFO log
    summarising the 5 outcome counters so operators tailing the
    service log can see what the scheduler did each cycle. A
    regression that dropped this log would silently remove ops
    visibility without breaking functional tests."""
    import logging
    user_id = str(uuid4())
    proj_regen = str(uuid4())
    proj_no_model = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        projects=[
            _project(user_id, proj_regen),
            _project(user_id, proj_no_model),
        ],
        model_lookup={
            (user_id, proj_regen): "gpt-4o-mini",
            (user_id, proj_no_model): None,
        },
    )
    pool = FakePool(conn)
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        AsyncMock(return_value=_regen_result("regenerated")),
    )
    with caplog.at_level(logging.INFO):
        await sweep_projects_once(
            pool=pool,  # type: ignore[arg-type]
            session_factory=lambda: MagicMock(),
            llm_client=MagicMock(),
            summaries_repo=MagicMock(),
        )
    # One INFO log line per sweep with the 5-counter breakdown.
    completion_logs = [
        r for r in caplog.records
        if r.levelno == logging.INFO
        and "project regen sweep complete" in r.message
    ]
    assert len(completion_logs) == 1, (
        f"expected exactly one sweep-complete INFO log, got {completion_logs}"
    )
    msg = completion_logs[0].getMessage()
    # All 5 counter names appear in the structured log so regex
    # tailers can scrape them. If any is dropped from the format
    # string, this assertion fails and the regression is caught.
    for counter_name in (
        "considered=", "regenerated=", "no_op=",
        "skipped=", "no_model=", "errored=",
    ):
        assert counter_name in msg, f"log missing {counter_name!r}: {msg}"


# ═══════════════════════════════════════════════════════════════
# C16-BUILD — summary_spending_repo wire-through
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sweep_projects_forwards_summary_spending_repo(monkeypatch):
    """C16-BUILD: project sweep must thread the SummarySpendingRepo
    kwarg into ``regenerate_project_summary``. Without this, the
    regen helper's spending recorder branch sees ``None`` and silently
    skips recording — global-scope budget enforcement would degrade
    to project-only and regress the C16 ADR contract.
    """
    user_id = str(uuid4())
    project_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        projects=[_project(user_id, project_id)],
        model_lookup={(user_id, project_id): "gpt-4o-mini"},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock(return_value=_regen_result("regenerated"))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        regen_mock,
    )
    sentinel_repo = MagicMock(name="SummarySpendingRepo")
    await sweep_projects_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
        summary_spending_repo=sentinel_repo,
    )
    regen_mock.assert_awaited_once()
    kwargs = regen_mock.await_args.kwargs
    assert kwargs["summary_spending_repo"] is sentinel_repo


@pytest.mark.asyncio
async def test_sweep_global_forwards_summary_spending_repo(monkeypatch):
    """C16-BUILD: same wire-through contract for the global sweep.
    Global scope is the *primary* consumer of the new repo (project
    spend already lands in ``knowledge_projects.current_month_spent``
    via K16.11) so a regression here would silently break the entire
    feature."""
    user_id = str(uuid4())
    conn = FakeConn(
        try_lock=True,
        users=[_user(user_id)],
        user_model_lookup={user_id: "gpt-4o-mini"},
    )
    pool = FakePool(conn)
    regen_mock = AsyncMock(return_value=_regen_result("regenerated"))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_global_summary",
        regen_mock,
    )
    sentinel_repo = MagicMock(name="SummarySpendingRepo")
    await sweep_global_once(
        pool=pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
        summary_spending_repo=sentinel_repo,
    )
    regen_mock.assert_awaited_once()
    kwargs = regen_mock.await_args.kwargs
    assert kwargs["summary_spending_repo"] is sentinel_repo


@pytest.mark.asyncio
async def test_sweeps_default_summary_spending_repo_to_none(monkeypatch):
    """C16-BUILD: default ``None`` propagates to both regen helpers
    when caller omits the kwarg. Locks the DI-consistent gating —
    regen helpers' pre-check + recorder must be no-ops when the repo
    isn't wired (legacy tests, dev environments without the migration
    applied yet)."""
    user_id = str(uuid4())
    project_id = str(uuid4())

    # Project sweep — None default.
    proj_conn = FakeConn(
        try_lock=True,
        projects=[_project(user_id, project_id)],
        model_lookup={(user_id, project_id): "gpt-4o-mini"},
    )
    proj_pool = FakePool(proj_conn)
    proj_regen_mock = AsyncMock(return_value=_regen_result("regenerated"))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_project_summary",
        proj_regen_mock,
    )
    await sweep_projects_once(
        pool=proj_pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert proj_regen_mock.await_args.kwargs["summary_spending_repo"] is None

    # Global sweep — None default.
    glob_conn = FakeConn(
        try_lock=True,
        users=[_user(user_id)],
        user_model_lookup={user_id: "gpt-4o-mini"},
    )
    glob_pool = FakePool(glob_conn)
    glob_regen_mock = AsyncMock(return_value=_regen_result("regenerated"))
    monkeypatch.setattr(
        "app.jobs.summary_regen_scheduler.regenerate_global_summary",
        glob_regen_mock,
    )
    await sweep_global_once(
        pool=glob_pool,  # type: ignore[arg-type]
        session_factory=lambda: MagicMock(),
        llm_client=MagicMock(),
        summaries_repo=MagicMock(),
    )
    assert glob_regen_mock.await_args.kwargs["summary_spending_repo"] is None
