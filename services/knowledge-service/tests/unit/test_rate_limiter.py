"""K17.12 — Unit tests for token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.clients.provider_client import _TokenBucket


@pytest.mark.asyncio
async def test_bucket_allows_burst_up_to_max_rate():
    """First N calls (up to max_rate) should not block."""
    bucket = _TokenBucket(max_rate=5.0)
    start = time.monotonic()
    for _ in range(5):
        await bucket.acquire("user1")
    elapsed = time.monotonic() - start
    # 5 calls should complete nearly instantly (burst)
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_bucket_throttles_beyond_max_rate():
    """Calls beyond burst should be delayed."""
    bucket = _TokenBucket(max_rate=5.0)
    # Exhaust the burst
    for _ in range(5):
        await bucket.acquire("user1")
    # Next call should wait ~0.2s (1/5)
    start = time.monotonic()
    await bucket.acquire("user1")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.1  # at least some wait


@pytest.mark.asyncio
async def test_bucket_per_user_isolation():
    """Different users have independent buckets."""
    bucket = _TokenBucket(max_rate=2.0)
    # Exhaust user1
    for _ in range(2):
        await bucket.acquire("user1")
    # user2 should still have tokens
    start = time.monotonic()
    await bucket.acquire("user2")
    elapsed = time.monotonic() - start
    assert elapsed < 0.1  # instant
