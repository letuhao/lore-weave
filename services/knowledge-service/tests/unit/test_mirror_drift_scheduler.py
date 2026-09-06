"""The scheduled mirror sweep (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).

A sweeper fails quietly by construction: it runs unattended, and every failure mode here
produces a sweep that finishes, logs a number, and is believed. The one that matters most
is a sweep that reports a clean mirror because it could not look.
"""
from __future__ import annotations

import pytest

import app.jobs.mirror_drift_scheduler as sched
from app.mirror.glossary_mirror import MirrorDrift


class _Conn:
    """Minimal asyncpg connection: an advisory lock and the project list."""

    def __init__(self, rows, locked=True):
        self._rows = rows
        self._locked = locked
        self.unlocked = False

    async def fetchval(self, sql, *a):
        return self._locked

    async def fetch(self, sql, cursor, cap):
        rows = [r for r in self._rows
                if cursor is None or r["project_id"] > str(cursor)]
        return rows[:cap]

    async def execute(self, sql, *a):
        self.unlocked = True


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        pool_conn = self._conn

        class _CM:
            async def __aenter__(self):
                return pool_conn

            async def __aexit__(self, *a):
                return False
        return _CM()


class _Session:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


class _Client:
    def __init__(self, reemit_result=None):
        self._reemit = reemit_result
        self.reemit_calls: list = []

    async def reemit_mirror(self, book_id, entity_ids):
        self.reemit_calls.append((str(book_id), list(entity_ids)))
        return self._reemit


def _row(n: int) -> dict:
    stub = f"{n:08d}-0000-0000-0000-000000000000"
    return {"project_id": stub, "book_id": stub, "user_id": stub}


def _drift(missing: int) -> MirrorDrift:
    d = MirrorDrift(project_id="p", book_id="b", truth_total=10, mirrorable=10,
                    mirrored=10 - missing)
    d.missing_ids = [f"missing-{i}" for i in range(missing)]
    return d


@pytest.fixture(autouse=True)
def _reset_gauges():
    sched.glossary_mirror_missing.set(0)
    sched.glossary_mirror_projects_diverged.set(0)


def _patch_detect(monkeypatch, per_project):
    """per_project: {project_id -> MirrorDrift | None | Exception}"""
    calls: list[str] = []

    async def _detect(*, session, glossary_client, project_id, book_id, user_id, **kw):
        calls.append(str(project_id))
        outcome = per_project(str(project_id))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(sched, "detect_mirror_drift", _detect)
    return calls


@pytest.mark.asyncio
async def test_sweep_aggregates_and_names_the_diverged_projects(monkeypatch):
    rows = [_row(1), _row(2), _row(3)]
    _patch_detect(monkeypatch, lambda p: _drift(2) if p.startswith("00000002") else _drift(0))
    conn = _Conn(rows)

    out = await sched.sweep_mirror_drift_once(_Pool(conn), _Session, _Client())

    assert out.projects_considered == 3
    assert out.projects_diverged == 1 and out.missing_total == 2
    assert out.diverged == [(rows[1]["project_id"], 2)]
    assert sched.glossary_mirror_missing._value.get() == 2
    assert conn.unlocked, "the advisory lock was not released"


@pytest.mark.asyncio
async def test_an_unreachable_glossary_is_an_ERROR_not_a_clean_project(monkeypatch):
    """detect returns None when the truth side is unreachable. Counting that as zero
    divergence is how an outage renders as the healthiest sweep on record."""
    _patch_detect(monkeypatch, lambda p: None)
    conn = _Conn([_row(1), _row(2)])

    out = await sched.sweep_mirror_drift_once(_Pool(conn), _Session, _Client())

    assert out.errored == 2
    assert out.projects_diverged == 0 and out.missing_total == 0


@pytest.mark.asyncio
async def test_one_bad_project_does_not_stop_the_sweep(monkeypatch):
    calls = _patch_detect(
        monkeypatch,
        lambda p: RuntimeError("boom") if p.startswith("00000002") else _drift(1),
    )
    conn = _Conn([_row(1), _row(2), _row(3)])

    out = await sched.sweep_mirror_drift_once(_Pool(conn), _Session, _Client())

    assert len(calls) == 3, "the sweep stopped at the failing project"
    assert out.errored == 1 and out.missing_total == 2


@pytest.mark.asyncio
async def test_auto_repair_off_measures_but_never_writes(monkeypatch):
    _patch_detect(monkeypatch, lambda p: _drift(3))
    client = _Client({"reemitted": 3})

    out = await sched.sweep_mirror_drift_once(_Pool(_Conn([_row(1)])), _Session, client)

    assert out.missing_total == 3 and out.repaired == 0
    assert client.reemit_calls == [], "auto_repair defaulted ON"


@pytest.mark.asyncio
async def test_auto_repair_on_counts_what_the_SSOT_REPORTS_not_what_it_asked(monkeypatch):
    """The emit path declines ids it will not emit for (soft-deleted, nameless, another
    book's). Counting `len(missing_ids)` as the repair total reports repairs that never
    happened, on the very metric that is supposed to prove convergence."""
    _patch_detect(monkeypatch, lambda p: _drift(5))
    client = _Client({"reemitted": 2, "skipped_ids": ["a", "b", "c"]})

    out = await sched.sweep_mirror_drift_once(
        _Pool(_Conn([_row(1)])), _Session, client, auto_repair=True,
    )

    assert out.repaired == 2, "reported the request size, not the result"
    assert len(client.reemit_calls[0][1]) == 5


@pytest.mark.asyncio
async def test_a_failed_reemit_counts_as_an_error(monkeypatch):
    """`reemit_mirror` returning None means nothing was written. Silently treating it as
    0 repairs would make a broken repair path indistinguishable from a clean mirror."""
    _patch_detect(monkeypatch, lambda p: _drift(2))
    client = _Client(None)

    out = await sched.sweep_mirror_drift_once(
        _Pool(_Conn([_row(1)])), _Session, client, auto_repair=True,
    )

    assert out.errored == 1 and out.repaired == 0


@pytest.mark.asyncio
async def test_the_lock_stops_a_second_worker(monkeypatch):
    _patch_detect(monkeypatch, lambda p: _drift(9))
    conn = _Conn([_row(1)], locked=False)

    out = await sched.sweep_mirror_drift_once(_Pool(conn), _Session, _Client())

    assert out.lock_skipped is True
    assert out.projects_considered == 0


class _Cursor:
    def __init__(self):
        self.value = None
        self.cleared = False

    async def read_cursor(self, name):
        return self.value

    async def upsert_cursor(self, name, project_id):
        self.value = project_id

    async def clear_cursor(self, name):
        self.cleared = True
        self.value = None


@pytest.mark.asyncio
async def test_a_capped_sweep_KEEPS_its_cursor(monkeypatch):
    """The cap is what makes a large database sweepable in slices. Clearing the cursor on
    a capped sweep restarts at the beginning every time, so the tail of the project list
    is never swept at all — a blind spot, not a slow spot."""
    _patch_detect(monkeypatch, lambda p: _drift(0))
    cursor = _Cursor()
    rows = [_row(i) for i in range(1, 6)]

    out = await sched.sweep_mirror_drift_once(
        _Pool(_Conn(rows)), _Session, _Client(),
        sweeper_state_repo=cursor, project_cap=3,
    )

    assert out.projects_capped is True
    assert cursor.cleared is False, "a capped sweep cleared its cursor"
    assert str(cursor.value) == rows[2]["project_id"]


@pytest.mark.asyncio
async def test_a_completed_sweep_clears_its_cursor_and_resumes_from_it(monkeypatch):
    calls = _patch_detect(monkeypatch, lambda p: _drift(0))
    cursor = _Cursor()
    rows = [_row(i) for i in range(1, 4)]
    cursor.value = rows[0]["project_id"]   # a previous sweep stopped after project 1

    out = await sched.sweep_mirror_drift_once(
        _Pool(_Conn(rows)), _Session, _Client(),
        sweeper_state_repo=cursor, project_cap=10,
    )

    assert calls == [rows[1]["project_id"], rows[2]["project_id"]], "did not resume"
    assert out.projects_capped is False
    assert cursor.cleared is True
