"""K14.4 — Unit tests for event gating."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.events.gating import should_extract, clear_cache


_USER = uuid4()
_PROJECT = uuid4()


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
async def test_enabled_project_returns_true():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "extraction_enabled": True,
        "extraction_status": "building",
    })
    assert await should_extract(pool, _PROJECT, _USER) is True


@pytest.mark.asyncio
async def test_disabled_project_returns_false():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "extraction_enabled": False,
        "extraction_status": "disabled",
    })
    assert await should_extract(pool, _PROJECT, _USER) is False


@pytest.mark.asyncio
async def test_enabled_but_wrong_status_returns_false():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "extraction_enabled": True,
        "extraction_status": "failed",
    })
    assert await should_extract(pool, _PROJECT, _USER) is False


@pytest.mark.asyncio
async def test_nonexistent_project_returns_false():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    assert await should_extract(pool, _PROJECT, _USER) is False


@pytest.mark.asyncio
async def test_result_is_cached():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "extraction_enabled": True,
        "extraction_status": "ready",
    })
    # First call hits DB
    await should_extract(pool, _PROJECT, _USER)
    # Second call should use cache (no new DB call)
    await should_extract(pool, _PROJECT, _USER)
    pool.fetchrow.assert_called_once()
