"""T17 A18 — the summary blend logs a capability GAP differently from a failure."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


def _project():
    return SimpleNamespace(project_id=uuid4(), embedding_model="bge-m3")


class _NoopSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False


async def _run(side_effect, caplog):
    from app.context.modes import full

    with patch.object(full, "neo4j_session", new=lambda: _NoopSession()), \
         patch.object(full, "is_abstract_query", return_value=True), \
         patch("app.context.selectors.summary_blend.select_summary_blend",
               new=AsyncMock(side_effect=side_effect)):
        embed = SimpleNamespace(embed=AsyncMock(return_value=[[0.1] * 8]))
        with patch.object(full, "embed_query_cached", new=AsyncMock(return_value=[0.1] * 8),
                          create=True):
            with caplog.at_level(logging.INFO, logger=full.logger.name):
                return await full._safe_summary_blend(
                    embed, user_id=uuid4(), project=_project(),
                    message="what is this book about", glossary_entities=[],
                )


@pytest.mark.asyncio
async def test_an_engine_GAP_is_not_logged_as_a_failure(caplog):
    """A permanent gap logged as WARNING+traceback on EVERY request trains readers to
    ignore the warning that means something.

    `query_summary_index` reaches `CALL db.index.vector.queryNodes`, Neo4j-only, and this
    runs on a backend-following session — so on the default AGE backend the old
    `except Exception` fired on every Mode 3 abstract query with a full stack trace.
    """
    from app.context.modes import full

    hits = await _run(NotImplementedError("vector index search is a Neo4j-only capability"),
                      caplog)
    assert hits == []
    recs = [r for r in caplog.records if r.name == full.logger.name]
    assert recs, "the gap must still be visible — silence is its own defect"
    assert all(r.levelno <= logging.INFO for r in recs), (
        f"a permanent capability gap must not log at WARNING: "
        f"{[(r.levelname, r.getMessage()[:60]) for r in recs]}"
    )
    assert all(r.exc_info is None for r in recs), "no stack trace for an expected steady state"
    assert any("unavailable on this engine" in r.getMessage() for r in recs)


@pytest.mark.asyncio
async def test_a_REAL_failure_still_warns_with_its_traceback(caplog):
    """The control arm: quieting the gap must not quiet a genuine fault."""
    from app.context.modes import full

    hits = await _run(RuntimeError("neo4j: connection refused"), caplog)
    assert hits == []
    recs = [r for r in caplog.records if r.name == full.logger.name]
    assert any(r.levelno >= logging.WARNING for r in recs), (
        "a real blend failure must still be a WARNING — the narrow catch exists so this "
        "one keeps its volume"
    )
    assert any(r.exc_info is not None for r in recs), "a real failure keeps its traceback"
