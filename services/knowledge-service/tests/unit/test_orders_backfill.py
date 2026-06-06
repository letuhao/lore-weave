"""CM4 — unit tests for the dual-order backfill helper (run_orders_backfill).

Covers: event_order = sort_order×1e6 + within-chapter index; passage
chapter_index stamped per chapter; chronological rerank invoked; chapters
with an unresolved sort_order are skipped (event_order left NULL, counted);
idempotent SET semantics.

Mirrors the C18 backfill fake-session pattern (test_event_date_backfill).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.db.migrations.backfill_orders import run_orders_backfill

_USER = "11111111-1111-1111-1111-111111111111"
_PROJECT = "22222222-2222-2222-2222-222222222222"
_CH1 = "33333333-3333-3333-3333-333333333333"
_CH2 = "44444444-4444-4444-4444-444444444444"


def _event_rec(event_id: str, chapter_id: str) -> MagicMock:
    rec = MagicMock()
    data = {"id": event_id, "chapter_id": chapter_id}
    rec.__getitem__.side_effect = lambda k: data[k]
    return rec


def _async_iter(records):
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


class _CountResult:
    """A fake Cypher result whose .single() yields a count record."""
    def __init__(self, key: str, value: int):
        self._key = key
        self._value = value
    async def single(self):
        rec = MagicMock()
        rec.__getitem__.side_effect = lambda k: {self._key: self._value}[k]
        return rec


class _FakeSession:
    def __init__(self, event_records, passage_counts: dict[str, int]):
        self._events = event_records
        self._passage_counts = passage_counts  # chapter_id -> passages updated
        self.event_order_sets: list[dict] = []
        self.passage_sets: list[dict] = []
        self.chrono_nulled = False
        self.chrono_ranked = False

    async def run(self, cypher: str, **kwargs):
        if "RETURN e.id AS id, e.chapter_id AS chapter_id" in cypher:
            return _async_iter(self._events)
        if "SET e.event_order" in cypher:
            self.event_order_sets.append(kwargs)
            return MagicMock()  # unconditional one-time SET (no RETURN)
        if "SET p.chapter_index" in cypher:
            self.passage_sets.append(kwargs)
            n = self._passage_counts.get(kwargs.get("chapter_id"), 0)
            return _CountResult("updated", n)
        if "SET e.chronological_order = NULL" in cypher:
            self.chrono_nulled = True
            return MagicMock()
        if "i + 1 AS rank" in cypher:  # CHRONO_RANK_DATED
            self.chrono_ranked = True
            return _CountResult("ranked", 2)
        raise AssertionError(f"unexpected cypher: {cypher}")


def _book_client(sort_orders: dict[UUID, int]) -> MagicMock:
    bc = MagicMock()
    bc.get_chapter_sort_orders = AsyncMock(return_value=sort_orders)
    return bc


@pytest.mark.asyncio
async def test_backfill_stamps_event_order_passages_and_chrono():
    # ch1 (sort_order 5) has 2 events; ch2 (sort_order 8) has 1 event.
    session = _FakeSession(
        event_records=[
            _event_rec("evB", _CH1),  # out of id-order on purpose
            _event_rec("evA", _CH1),
            _event_rec("evZ", _CH2),
        ],
        passage_counts={_CH1: 3, _CH2: 2},
    )
    bc = _book_client({UUID(_CH1): 5, UUID(_CH2): 8})

    result = await run_orders_backfill(
        session, bc, user_id=_USER, project_id=_PROJECT,
    )

    # event_order = sort_order×1e6 + within-chapter index (events sorted by id).
    got = {s["id"]: s["event_order"] for s in session.event_order_sets}
    assert got == {
        "evA": 5_000_000 + 0,   # ch1, id 'evA' sorts first
        "evB": 5_000_000 + 1,
        "evZ": 8_000_000 + 0,   # ch2
    }
    assert result.events_ordered == 3
    assert result.events_skipped_no_sort == 0
    # passage chapter_index stamped per chapter from sort_order.
    pass_set = {s["chapter_id"]: s["chapter_index"] for s in session.passage_sets}
    assert pass_set == {_CH1: 5, _CH2: 8}
    assert result.passages_indexed == 3 + 2
    # chronological rerank ran (both passes).
    assert session.chrono_nulled and session.chrono_ranked
    assert result.chrono_ranked == 2


@pytest.mark.asyncio
async def test_backfill_skips_events_when_sort_order_unresolved():
    """A chapter whose sort_order book-service can't resolve (deleted/missing)
    leaves its events' event_order NULL — counted, not fabricated."""
    session = _FakeSession(
        event_records=[_event_rec("ev1", _CH1), _event_rec("ev2", _CH2)],
        passage_counts={_CH2: 1},
    )
    # Only ch2 resolves; ch1 is missing from the map.
    bc = _book_client({UUID(_CH2): 8})

    result = await run_orders_backfill(
        session, bc, user_id=_USER, project_id=_PROJECT,
    )

    set_ids = {s["id"] for s in session.event_order_sets}
    assert set_ids == {"ev2"}            # ch1 event NOT stamped
    assert result.events_ordered == 1
    assert result.events_skipped_no_sort == 1
    # ch1 passages also not touched (no sort_order).
    assert {s["chapter_id"] for s in session.passage_sets} == {_CH2}


@pytest.mark.asyncio
async def test_backfill_empty_project_is_noop():
    session = _FakeSession(event_records=[], passage_counts={})
    bc = _book_client({})
    result = await run_orders_backfill(
        session, bc, user_id=_USER, project_id=_PROJECT,
    )
    assert result.events_ordered == 0
    assert result.passages_indexed == 0
    # rerank still runs (cheap; keeps undated NULL + ranks any dated).
    assert session.chrono_nulled and session.chrono_ranked
    # no chapters → book-service not queried.
    bc.get_chapter_sort_orders.assert_not_awaited()
