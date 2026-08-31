"""K16.14 — Unit tests for stats cache updater."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.adapters.fake_graph_store import FakeGraphStore
from app.domain.graph_models import Event
from app.jobs.stats_updater import increment_stats, reconcile_project_stats

_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()


@pytest.mark.asyncio
async def test_increment_stats():
    pool = AsyncMock()
    pool.execute = AsyncMock()

    await increment_stats(
        pool, _TEST_USER, _TEST_PROJECT,
        entities=5, facts=3, events=2,
    )

    pool.execute.assert_called_once()
    call_args = pool.execute.call_args
    assert _TEST_USER in call_args.args
    assert _TEST_PROJECT in call_args.args


@pytest.mark.asyncio
async def test_reconcile_project_stats():
    """T17 A10 — reconciles through `GraphStore`, driven by the FAKE rather than a mock.

    🔴 **The version this replaces could not tell the three counts apart.** It handed the job
    a mocked session whose every `run()` returned `{"c": 10}`, then asserted all three columns
    were 10 — so a reconciler that wrote the entity count into all three columns passed, and
    so did one that ignored the label entirely. The numbers here are deliberately DISTINCT
    (2 entities, 3 facts, 1 event) because the only bug worth catching in this function is a
    column mix-up, and identical fixtures make that bug invisible.
    """
    pool = AsyncMock()
    pool.execute = AsyncMock()

    store = FakeGraphStore()
    for name in ("Kai", "Mira"):
        await store.resolve_or_merge_entity(
            user_id=str(_TEST_USER), project_id=str(_TEST_PROJECT),
            name=name, kind="character", source_type="chapter",
        )
    for i in range(3):
        await store.merge_fact(
            user_id=str(_TEST_USER), project_id=str(_TEST_PROJECT),
            type="trait", content=f"fact {i}",
        )
    store.add_event(Event(
        id="e0", user_id=str(_TEST_USER), project_id=str(_TEST_PROJECT),
        title="the duel", canonical_title="the duel",
    ))

    counts = await reconcile_project_stats(
        pool, store, _TEST_USER, _TEST_PROJECT,
    )

    assert counts["stat_entity_count"] == 2
    assert counts["stat_fact_count"] == 3
    assert counts["stat_event_count"] == 1
    pool.execute.assert_called_once()
    # The three counts reach the UPDATE in the order the columns are declared. Asserting the
    # ARGUMENTS, not just the return value: the function's job is the write, and a return
    # value nobody checks against the query is where a column swap hides.
    assert pool.execute.call_args.args[3:6] == (2, 3, 1)


@pytest.mark.asyncio
async def test_reconcile_counts_only_THIS_project():
    """A stats card that counted the neighbouring project would read as a working recount and
    be wrong on every dashboard tile — and the port takes `project_id`, so a store that
    ignored it would pass every other rule here."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    other = uuid4()

    store = FakeGraphStore()
    await store.resolve_or_merge_entity(
        user_id=str(_TEST_USER), project_id=str(_TEST_PROJECT),
        name="Kai", kind="character", source_type="chapter")
    await store.resolve_or_merge_entity(
        user_id=str(_TEST_USER), project_id=str(other),
        name="Mira", kind="character", source_type="chapter")

    counts = await reconcile_project_stats(pool, store, _TEST_USER, _TEST_PROJECT)
    assert counts["stat_entity_count"] == 1
