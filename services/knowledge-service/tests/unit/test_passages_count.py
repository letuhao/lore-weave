"""C8 — unit tests for count_passages_by_source_type.

Patches ``run_read`` directly so we can inspect the helper's padding
and drift-handling without a live Neo4j. Live integration coverage is
separate at ``tests/integration/db/test_passages_repo.py``.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.neo4j_repos.passages import (
    KNOWN_SOURCE_TYPES,
    count_passages_by_source_type,
)


def _make_result_stub(records: list[dict] | None = None):
    stub = MagicMock()

    async def _aiter():
        for record in records or []:
            yield record

    stub.__aiter__ = lambda self=stub: _aiter()
    return stub


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.passages.run_read", new_callable=AsyncMock)
async def test_count_pads_missing_keys_to_zero(mock_run_read):
    """Neo4j returns only the keys that exist; helper MUST pad the
    rest with 0 so the FE pill row stays layout-stable."""
    mock_run_read.return_value = _make_result_stub(
        records=[{"source_type": "chapter", "n": 42}],
    )
    counts = await count_passages_by_source_type(
        session=MagicMock(),
        user_id="u-1",
        project_id="p-1",
    )
    # Every known key present.
    assert set(counts.keys()) == KNOWN_SOURCE_TYPES
    assert counts["chapter"] == 42
    assert counts["chat"] == 0
    assert counts["glossary"] == 0


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.passages.run_read", new_callable=AsyncMock)
async def test_count_drops_unknown_source_type_with_warning(
    mock_run_read, caplog,
):
    """/review-impl [LOW#4]: data drift — a future code path inserts
    :Passage with a source_type before KNOWN_SOURCE_TYPES is updated.
    Helper drops the unknown row + logs a warning so the drift is
    visible in logs without crashing the search endpoint."""
    mock_run_read.return_value = _make_result_stub(
        records=[
            {"source_type": "chapter", "n": 10},
            {"source_type": "lore_doc", "n": 5},  # ← drift
        ],
    )
    with caplog.at_level(logging.WARNING, logger="app.db.neo4j_repos.passages"):
        counts = await count_passages_by_source_type(
            session=MagicMock(),
            user_id="u-1",
            project_id="p-1",
        )
    # Known types counted; unknown dropped.
    assert counts == {"chapter": 10, "chat": 0, "glossary": 0}
    # Drift visible in logs.
    assert any(
        "unknown source_type" in rec.message and "lore_doc" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.passages.run_read", new_callable=AsyncMock)
async def test_count_empty_result_returns_all_zeros(mock_run_read):
    """Newly-created project with no passages yet → every key at 0."""
    mock_run_read.return_value = _make_result_stub(records=[])
    counts = await count_passages_by_source_type(
        session=MagicMock(),
        user_id="u-1",
        project_id="p-new",
    )
    assert counts == {st: 0 for st in KNOWN_SOURCE_TYPES}


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.passages.run_read", new_callable=AsyncMock)
async def test_count_forwards_embedding_model_to_cypher(mock_run_read):
    """Router passes project.embedding_model so counts reflect what
    the vector search can actually reach. Regression lock: dropping
    this kwarg would silently count stale-model passages."""
    mock_run_read.return_value = _make_result_stub(records=[])
    await count_passages_by_source_type(
        session=MagicMock(),
        user_id="u-1",
        project_id="p-1",
        embedding_model="bge-m3",
    )
    call = mock_run_read.await_args
    assert call.kwargs["embedding_model"] == "bge-m3"
    assert call.kwargs["user_id"] == "u-1"
    assert call.kwargs["project_id"] == "p-1"
