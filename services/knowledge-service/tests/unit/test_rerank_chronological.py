"""CM4 — unit coverage for rerank_chronological_order's two-pass contract.

The actual rank ordering is Cypher (verified by the Neo4j integration suite /
live-smoke). Here we lock the orchestration: pass 1 NULLs undated events, pass 2
ranks dated events and the function returns the ranked count.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.db.neo4j_repos.events import rerank_chronological_order

_USER = "11111111-1111-1111-1111-111111111111"
_PROJECT = "22222222-2222-2222-2222-222222222222"


class _CountResult:
    def __init__(self, value: int):
        self._value = value

    async def single(self):
        rec = MagicMock()
        rec.__getitem__.side_effect = lambda k: {"ranked": self._value}[k]
        return rec


class _FakeSession:
    def __init__(self, ranked: int):
        self._ranked = ranked
        self.null_pass = False
        self.rank_pass = False
        self.user_ids: list[str] = []

    async def run(self, cypher: str, **kwargs):
        # run_write injects user_id; assert it always carries the tenant scope.
        self.user_ids.append(kwargs.get("user_id"))
        if "SET e.chronological_order = NULL" in cypher:
            self.null_pass = True
            return MagicMock()
        if "i + 1 AS rank" in cypher:
            self.rank_pass = True
            return _CountResult(self._ranked)
        raise AssertionError(f"unexpected cypher: {cypher}")


@pytest.mark.asyncio
async def test_rerank_runs_both_passes_and_returns_count():
    session = _FakeSession(ranked=4)
    ranked = await rerank_chronological_order(
        session, user_id=_USER, project_id=_PROJECT,  # type: ignore[arg-type]
    )
    assert ranked == 4
    assert session.null_pass and session.rank_pass  # undated→NULL THEN rank dated
    # both passes are tenant-scoped (run_write asserts $user_id).
    assert session.user_ids == [_USER, _USER]


@pytest.mark.asyncio
async def test_rerank_zero_dated_returns_zero():
    """A project with no dated events still NULLs undated and returns 0."""
    session = _FakeSession(ranked=0)
    ranked = await rerank_chronological_order(
        session, user_id=_USER, project_id=_PROJECT,  # type: ignore[arg-type]
    )
    assert ranked == 0
    assert session.null_pass and session.rank_pass
