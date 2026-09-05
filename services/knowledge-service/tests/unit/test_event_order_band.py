"""`max_event_order_in_band` — the read that stopped `event_order` colliding across jobs.

The bug it exists for, measured on the iso store 2026-08-30: `pass2_writer` assigned
`event_order = chapter_base + idx` with `idx` restarting at 0 on every call, while
`chapter_base` depends only on the chapter. 封神演義 ch.1 had been extracted by three jobs
and carried **7 duplicate `event_order` values across 20 events**, every collision cross-job
and none within a job. `event_order` is the reading axis — the spoiler cutoff, the timeline,
`list_events_in_order`, the causal pass's forward-only guard — so duplicates make every
consumer's ordering fall through to the store's row order and the axis quietly stops being
an order.

⚠️ **These tests cover the UNWRAP, not the query.** A fake session proves only that this
module reads its own result correctly; it cannot prove AGE accepts the Cypher. That was
verified against the live `g_shared` graph instead (empty band → SQL NULL; the
`$project_id IS NULL` branch genuinely widens the scan; a wrong `user_id` sees nothing).

The one case worth a test in isolation is the empty band, because the failure is silent:
if "no events here" came back as `0` instead of `None`, the writer would compute
`idx = 0 - chapter_base + 1` — a large negative — and write event_orders *below* the
chapter's own band, into the previous chapter's. A zero that means "nothing found" read as
a measurement is this repo's most-repeated defect.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.graph_repos.events import max_event_order_in_band


class _Result:
    """The async-iterable of records a driver hands back."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self):
        async def gen():
            for r in self._records:
                yield r
        return gen()


def _session(records: list[dict[str, Any]]) -> Any:
    session = MagicMock()
    session.run = AsyncMock(return_value=_Result(records))
    return session


@pytest.mark.asyncio
async def test_empty_band_is_none_and_never_zero():
    """An aggregate over no rows returns a row whose value is NULL. It must surface as
    `None` — `0` would send the writer below the chapter's own band."""
    got = await max_event_order_in_band(
        _session([{"mx": None}]),
        user_id="u", project_id="p", lo=3_000_000, hi=4_000_000,
    )
    assert got is None
    assert got != 0


@pytest.mark.asyncio
async def test_a_band_with_events_returns_its_highest_slot():
    got = await max_event_order_in_band(
        _session([{"mx": 3_000_017}]),
        user_id="u", project_id="p", lo=3_000_000, hi=4_000_000,
    )
    assert got == 3_000_017


@pytest.mark.asyncio
async def test_a_driver_that_returns_no_row_at_all_is_also_none():
    """Not the same shape as `[{"mx": None}]` — some drivers elide the row entirely for an
    empty aggregate. Both mean "nothing here", so both must answer None rather than raise."""
    got = await max_event_order_in_band(
        _session([]), user_id="u", project_id="p", lo=0, hi=1,
    )
    assert got is None


@pytest.mark.asyncio
async def test_the_bounds_and_the_tenant_reach_the_driver_as_parameters():
    """The band is the chapter. If `lo`/`hi` were interpolated or dropped, the read would
    span the whole project and the writer would number every chapter after the busiest one."""
    session = _session([{"mx": None}])
    await max_event_order_in_band(
        session, user_id="u-1", project_id="p-1", lo=3_000_000, hi=4_000_000,
    )
    kwargs = session.run.await_args.kwargs
    assert kwargs["user_id"] == "u-1"
    assert kwargs["project_id"] == "p-1"
    assert kwargs["lo"] == 3_000_000
    assert kwargs["hi"] == 4_000_000
    cypher = session.run.await_args.args[0]
    assert "$lo" in cypher and "$hi" in cypher, "bounds must be bound, never interpolated"
    assert "3000000" not in cypher and "4000000" not in cypher
