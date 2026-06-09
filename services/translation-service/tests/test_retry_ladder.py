"""S3b (G6) — transient-retry backoff ladder selection.

The worker routes a transient chapter retry through a fixed-TTL rung instead of
republishing immediately. These lock the rung-selection logic (the load-bearing
decision); the live dead-letter routing rides D-S3B-BACKOFF-LIVE-SMOKE.
"""

from app.broker import (
    CHAPTER_RETRY_DELAYS_MS,
    chapter_retry_queue_name,
    chapter_retry_queue_for_attempt,
)
from worker import _MAX_TRANSIENT_RETRIES


def test_ladder_matches_retry_budget():
    # Enforce the coupling (not just len==3): one rung per transient retry. If
    # someone bumps _MAX_TRANSIENT_RETRIES without growing the ladder, the extra
    # attempts would silently clamp to the last rung — breaking the "exponential"
    # promise unannounced. This locks them together.
    assert len(CHAPTER_RETRY_DELAYS_MS) == _MAX_TRANSIENT_RETRIES


def test_ladder_is_exponential():
    assert CHAPTER_RETRY_DELAYS_MS == (1000, 2000, 4000)


def test_queue_name_format():
    assert chapter_retry_queue_name(2000) == "translation.chapters.retry.2000"


def test_attempt_maps_to_increasing_delay():
    assert chapter_retry_queue_for_attempt(0) == "translation.chapters.retry.1000"
    assert chapter_retry_queue_for_attempt(1) == "translation.chapters.retry.2000"
    assert chapter_retry_queue_for_attempt(2) == "translation.chapters.retry.4000"


def test_attempt_beyond_ladder_clamps_to_last_rung():
    # A retry_count past the ladder still gets the max delay (never an IndexError).
    assert chapter_retry_queue_for_attempt(5) == "translation.chapters.retry.4000"
    assert chapter_retry_queue_for_attempt(99) == "translation.chapters.retry.4000"
