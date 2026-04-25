"""C18 — unit tests for the event_date_iso backfill helper.

Covers ``run_backfill`` contract:
  - happy path: parses time_cue, writes event_date_iso
  - skips rows with unparseable time_cue
  - idempotent re-run (the SELECT filter excludes already-populated rows)
  - per-row UPDATE failure swallowed (counted as errored, sweep continues)
  - empty event list returns zero counters

CLI shim deliberately not unit-tested — it constructs real
Neo4j session; coverage lives in run_backfill.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.db.migrations.backfill_event_date import run_backfill


def _record(event_id: str, time_cue: str) -> MagicMock:
    """Mock Neo4j record with subscript access to id + time_cue."""
    rec = MagicMock()
    data = {"id": event_id, "time_cue": time_cue}
    rec.__getitem__.side_effect = lambda k: data[k]
    return rec


class _FakeSession:
    """Mocks the Neo4j async session protocol (.run returns an async-
    iterable result). Records UPDATE calls + emulates UPDATE failure
    via ``raise_on_update_for`` set."""

    def __init__(
        self,
        records: list[MagicMock],
        raise_on_update_for: set[str] | None = None,
    ):
        self._records = records
        self._raise = raise_on_update_for or set()
        self.updates: list[dict] = []

    async def run(self, cypher: str, **kwargs):
        if "RETURN e.id AS id" in cypher:
            # SELECT — return the records as an async iterator.
            return _async_iter(self._records)
        if "SET e.event_date_iso" in cypher:
            event_id = kwargs["id"]
            if event_id in self._raise:
                raise RuntimeError(f"UPDATE failed for {event_id}")
            self.updates.append(kwargs)
            return MagicMock()
        raise AssertionError(f"unexpected cypher: {cypher}")


def _async_iter(records):
    """Build an async iterable from a Python list. Sync function
    returning an async-iterable instance so ``await session.run(...)``
    yields the iterable directly (not a coroutine wrapper)."""
    class _It:
        def __init__(self, recs):
            self._recs = list(recs)
            self._i = 0
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self._i >= len(self._recs):
                raise StopAsyncIteration
            r = self._recs[self._i]
            self._i += 1
            return r
    return _It(records)


@pytest.mark.asyncio
async def test_run_backfill_parses_and_writes():
    session = _FakeSession([
        _record("ev1", "summer 1880"),
        _record("ev2", "June 15, 1880"),
        _record("ev3", "1882"),
    ])
    result = await run_backfill(session)  # type: ignore[arg-type]

    assert result.scanned == 3
    assert result.parsed == 3
    assert result.skipped_unparseable == 0
    assert result.errored == 0

    written = {(u["id"], u["event_date_iso"]) for u in session.updates}
    assert written == {
        ("ev1", "1880-06"),
        ("ev2", "1880-06-15"),
        ("ev3", "1882"),
    }


@pytest.mark.asyncio
async def test_run_backfill_skips_unparseable_time_cue():
    """Vague phrases ('the next morning', 'in his youth') don't yield
    a date — counted as skipped_unparseable; no UPDATE issued."""
    session = _FakeSession([
        _record("ev1", "the next morning"),
        _record("ev2", "in his youth"),
        _record("ev3", "spring 1880"),  # parseable
    ])
    result = await run_backfill(session)  # type: ignore[arg-type]

    assert result.scanned == 3
    assert result.parsed == 1
    assert result.skipped_unparseable == 2
    assert len(session.updates) == 1
    assert session.updates[0]["event_date_iso"] == "1880-03"


@pytest.mark.asyncio
async def test_run_backfill_empty_event_list_returns_zero_counters():
    """No events to scan → all counters zero. Smoke-test the no-op
    path so a fresh-deploy or post-archive run doesn't hang."""
    session = _FakeSession([])
    result = await run_backfill(session)  # type: ignore[arg-type]

    assert result.scanned == 0
    assert result.parsed == 0
    assert result.skipped_unparseable == 0
    assert result.errored == 0


@pytest.mark.asyncio
async def test_run_backfill_per_row_update_failure_swallowed():
    """Best-effort: a transient Neo4j failure on one UPDATE doesn't
    abort the sweep. Failed row is counted as errored; subsequent rows
    still process."""
    session = _FakeSession(
        records=[
            _record("ev_bad", "summer 1880"),
            _record("ev_good", "June 1881"),
        ],
        raise_on_update_for={"ev_bad"},
    )
    result = await run_backfill(session)  # type: ignore[arg-type]

    assert result.scanned == 2
    assert result.parsed == 1  # only ev_good landed
    assert result.errored == 1
    # The good event still got its update.
    assert any(u["id"] == "ev_good" for u in session.updates)


@pytest.mark.asyncio
async def test_run_backfill_idempotent_via_select_filter():
    """The SELECT Cypher already filters
    ``event_date_iso IS NULL`` so a second sweep over the same DB
    finds no rows. We can't directly emulate that filter in the
    fake (no real DB), but we can prove the sweep handles an
    already-empty SELECT gracefully — which is the same code path."""
    # First sweep — one row.
    session1 = _FakeSession([_record("ev1", "summer 1880")])
    result1 = await run_backfill(session1)  # type: ignore[arg-type]
    assert result1.parsed == 1

    # Second sweep — empty (real DB filter would exclude the
    # already-populated row).
    session2 = _FakeSession([])
    result2 = await run_backfill(session2)  # type: ignore[arg-type]
    assert result2.scanned == 0
    assert result2.parsed == 0
