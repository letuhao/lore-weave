"""Plan T11 — the salience promotion read, after it moved out of the selector.

The move is not a tidy-up. `app/context/selectors/salience.py` called `session.run(...)`
DIRECTLY, so it never passed through `run_read` and its Cypher never carried `$user_id` —
the bypass `app/db/neo4j_repos/__init__.py` calls "the single highest-severity bug class in
this service". It matched on `project_id` alone, and `:Entity.project_id` is not a tenant
boundary: two users' entities can share a project id shape, and nothing in that query said
which owner's graph to read.

These tests pin the three things that make the move worth making, in order of how badly they
would fail silently:

  1. the Cypher satisfies the tenancy assertion (it would raise at CALL time otherwise, on
     a code path both weights default to 0.0 and nobody exercises),
  2. the owner and project filters actually reach the driver as BOUND parameters, and
  3. an archived entity gets no promotion signal.

The last one matters because a promotion boost is a re-ranking: an archived entity scoring
above a live one moves it up the context block, where budget-trim protects it.
"""

from __future__ import annotations

import pytest

from app.db.neo4j_helpers import assert_user_id_param
from app.db.neo4j_repos.entities import (
    _PROMOTION_SIGNALS_CYPHER,
    PromotionSignals,
    load_promotion_signals,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


class _FakeSession:
    """Records what actually reached the driver. The recorded params are the assertion —
    a query that filtered by owner in its TEXT but never bound the value would read every
    tenant's graph, and a test that only inspected the Cypher string would pass."""

    def __init__(self, rows=()):
        self.cypher = None
        self.params = None
        self._rows = list(rows)

    async def run(self, cypher, **params):
        self.cypher = cypher
        self.params = params
        return _FakeResult(self._rows)


def test_the_cypher_carries_the_tenant_filter():
    # run_read calls this before touching the driver, so a query that failed it would raise
    # CypherSafetyError at call time — on a path guarded by a weight that defaults to 0.0,
    # i.e. one nobody runs until they flip a flag in production.
    assert_user_id_param(_PROMOTION_SIGNALS_CYPHER)


def test_the_cypher_scopes_by_project_and_excludes_archived():
    cypher = _PROMOTION_SIGNALS_CYPHER
    assert "e.project_id = $project_id" in cypher
    assert "e.archived_at IS NULL" in cypher, (
        "an archived entity must not receive a promotion boost — the boost is a re-ranking, "
        "and ranking it above a live entity is exactly what budget-trim then protects"
    )


@pytest.mark.asyncio
async def test_owner_and_project_reach_the_driver_as_bound_parameters():
    session = _FakeSession()
    await load_promotion_signals(
        session, user_id="u-1", project_id="p-1", glossary_entity_ids=["g-1", "g-2"],
    )
    assert session.params["user_id"] == "u-1"
    assert session.params["project_id"] == "p-1"
    assert session.params["glossary_entity_ids"] == ["g-1", "g-2"]
    # Bound, never interpolated: the values must not appear in the query text at all.
    assert "u-1" not in session.cypher
    assert "p-1" not in session.cypher


@pytest.mark.asyncio
async def test_empty_input_does_no_io():
    session = _FakeSession()
    assert await load_promotion_signals(
        session, user_id="u-1", project_id="p-1", glossary_entity_ids=[],
    ) == {}
    assert session.cypher is None, (
        "the default configuration has both salience weights at 0.0 and must cost NO "
        "extra I/O; an empty candidate list is the same promise one level down"
    )


@pytest.mark.asyncio
async def test_rows_map_to_signals_and_a_bad_timestamp_costs_only_its_own_term():
    rows = [
        {"gid": "g-1", "ev": 7, "mn": 3, "up": "not-a-date"},
        {"gid": "g-2", "ev": 1, "mn": 0, "up": None},
    ]
    out = await load_promotion_signals(
        _FakeSession(rows), user_id="u", project_id="p", glossary_entity_ids=["g-1", "g-2"],
    )
    # An unparseable timestamp must NOT drop the entity — it loses its recency term and
    # keeps its evidence/mention terms. Legacy writes left string timestamps behind, and
    # discarding those entities would silently thin the signal set.
    assert out["g-1"] == PromotionSignals(evidence_count=7, mention_count=3, updated_at=None)
    assert out["g-2"].evidence_count == 1
    assert out["g-2"].updated_at is None


@pytest.mark.asyncio
async def test_naive_timestamps_are_made_aware():
    from datetime import datetime, timezone

    naive = datetime(2026, 1, 2, 3, 4, 5)
    out = await load_promotion_signals(
        _FakeSession([{"gid": "g", "ev": 0, "mn": 0, "up": naive}]),
        user_id="u", project_id="p", glossary_entity_ids=["g"],
    )
    # The scorer subtracts this from an aware `now`; a naive value raises TypeError and
    # takes the whole context build down a path that is supposed to be advisory-only.
    assert out["g"].updated_at == naive.replace(tzinfo=timezone.utc)
