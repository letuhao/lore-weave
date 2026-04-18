"""D-K11.9-02 — unit tests for orphan ExtractionSource cleanup.

Integration-level deletion against real Neo4j lives in
tests/integration/db/ (skipped without TEST_NEO4J_URI). These unit
tests cover argument validation + the RETURN row shape.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.orphan_extraction_source_cleanup import (
    delete_orphan_extraction_sources,
)


@pytest.mark.asyncio
async def test_empty_user_id_rejected():
    with pytest.raises(ValueError, match="user_id is required"):
        await delete_orphan_extraction_sources(MagicMock(), user_id="")


@pytest.mark.asyncio
async def test_zero_limit_rejected():
    with pytest.raises(ValueError, match="limit must be positive"):
        await delete_orphan_extraction_sources(
            MagicMock(), user_id="u1", limit=0,
        )


@pytest.mark.asyncio
async def test_negative_limit_rejected():
    with pytest.raises(ValueError, match="limit must be positive"):
        await delete_orphan_extraction_sources(
            MagicMock(), user_id="u1", limit=-5,
        )


@pytest.mark.asyncio
async def test_returns_deletion_count(monkeypatch):
    """Happy path: repo returns a row with `deleted`; we surface the int."""
    result = MagicMock()
    result.single = AsyncMock(return_value={"deleted": 7})

    async def fake_run_write(session, cypher, **kwargs):
        # Verify the expected parameters are wired correctly.
        assert kwargs["user_id"] == "u-1"
        assert kwargs["project_id"] == "p-1"
        assert kwargs["limit"] == 10
        return result

    monkeypatch.setattr(
        "app.jobs.orphan_extraction_source_cleanup.run_write", fake_run_write,
    )

    n = await delete_orphan_extraction_sources(
        MagicMock(), user_id="u-1", project_id="p-1", limit=10,
    )
    assert n == 7


@pytest.mark.asyncio
async def test_zero_deletion_count_is_valid(monkeypatch):
    """Clean run (no orphans) returns 0, not None."""
    result = MagicMock()
    result.single = AsyncMock(return_value={"deleted": 0})

    async def fake_run_write(session, cypher, **kwargs):
        return result

    monkeypatch.setattr(
        "app.jobs.orphan_extraction_source_cleanup.run_write", fake_run_write,
    )

    n = await delete_orphan_extraction_sources(MagicMock(), user_id="u-1")
    assert n == 0


@pytest.mark.asyncio
async def test_none_record_raises_anomaly(monkeypatch):
    """If RETURN count(*) somehow returns no row, raise loudly —
    same anomaly-guard as K11.9 reconciler."""
    result = MagicMock()
    result.single = AsyncMock(return_value=None)

    async def fake_run_write(session, cypher, **kwargs):
        return result

    monkeypatch.setattr(
        "app.jobs.orphan_extraction_source_cleanup.run_write", fake_run_write,
    )

    with pytest.raises(RuntimeError, match="driver or session anomaly"):
        await delete_orphan_extraction_sources(MagicMock(), user_id="u-1")


@pytest.mark.asyncio
async def test_none_limit_forwards_through(monkeypatch):
    """limit=None is a valid "no cap" and threads through to run_write."""
    captured = {}

    async def fake_run_write(session, cypher, **kwargs):
        captured.update(kwargs)
        r = MagicMock()
        r.single = AsyncMock(return_value={"deleted": 0})
        return r

    monkeypatch.setattr(
        "app.jobs.orphan_extraction_source_cleanup.run_write", fake_run_write,
    )

    await delete_orphan_extraction_sources(MagicMock(), user_id="u-1")
    assert captured["limit"] is None
