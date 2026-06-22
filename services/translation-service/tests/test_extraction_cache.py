"""CACHE/M6 — the EXECUTE-ledger raw-output cache (architecture §8.1, §2.1).

`effort_band_for` is a pure unit test; the round-trip / idempotency / tenant-scope tests run
against real Postgres (skip when none reachable, point at TRANSLATION_TEST_PG_DSN)."""
import os
import uuid

import asyncpg
import pytest

from app.migrate import DDL
from app.workers.extraction_cache import (
    RawCacheKey,
    effort_band_for,
    get_cached_batch,
    put_batch,
)

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)


def test_effort_band_for():
    assert effort_band_for(False) == "none"
    assert effort_band_for(True) == "medium"
    # an explicit graded effort wins over the legacy bool.
    assert effort_band_for(False, "high") == "high"
    assert effort_band_for(True, "low") == "low"


async def _put(pool, key, **over):
    kw = dict(
        job_id=None, kinds_requested=["character"], model_source="user_model",
        model_ref=str(uuid.uuid4()), reasoning_effort="none", input_tokens=100, output_tokens=80,
        finish_reason="stop", raw_response="[{...}]", parsed_entities=[{"name": "X"}], parse_status="ok",
    )
    kw.update(over)
    await put_batch(pool, key, **kw)


class _ConnPool:
    """Minimal pool shim over one asyncpg connection: gives the .acquire() async-context the
    cache module expects, while the test drives a single connection inside a rolled-back tx."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _CM:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _CM()


@pytest.mark.asyncio
async def test_raw_cache_roundtrip_idempotency_and_tenant_scope():
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    owner = uuid.uuid4()
    try:
        await conn.execute(DDL)  # ensure the table exists (committed; idempotent boot DDL)
        pool = _ConnPool(conn)
        tx = conn.transaction()
        await tx.start()
        book, chap = uuid.uuid4(), uuid.uuid4()
        key = RawCacheKey(owner_user_id=str(owner), book_id=str(book), chapter_id=str(chap),
                          content_hash="h1", batch_idx=0, effort_band="none")

        # Miss before any write.
        assert await get_cached_batch(pool, key) is None

        # Put → hit, parsed_entities + finish_reason round-trip.
        await _put(pool, key)
        hit = await get_cached_batch(pool, key)
        assert hit is not None
        assert hit["parsed_entities"] == [{"name": "X"}]
        assert hit["finish_reason"] == "stop" and hit["parse_status"] == "ok"

        # Idempotent: a second put on the same key is a no-op (ON CONFLICT DO NOTHING).
        await _put(pool, key, parsed_entities=[{"name": "DIFFERENT"}], input_tokens=999)
        async with pool.acquire() as db:
            n = await db.fetchval(
                "SELECT count(*) FROM extraction_raw_outputs WHERE owner_user_id=$1", owner)
            first = await db.fetchval(
                "SELECT parsed_entities FROM extraction_raw_outputs WHERE owner_user_id=$1", owner)
        assert n == 1
        # the original row survived (the conflicting re-put did not overwrite).
        import json as _json
        assert _json.loads(first) == [{"name": "X"}]

        # Tenant isolation (INV-9): a DIFFERENT owner with the same chapter/content → miss.
        other = RawCacheKey(owner_user_id=str(uuid.uuid4()), book_id=str(book),
                            chapter_id=str(chap), content_hash="h1", batch_idx=0, effort_band="none")
        assert await get_cached_batch(pool, other) is None

        # Effort band participates in the key: a different band → miss (different output).
        high = RawCacheKey(owner_user_id=str(owner), book_id=str(book), chapter_id=str(chap),
                           content_hash="h1", batch_idx=0, effort_band="high")
        assert await get_cached_batch(pool, high) is None

        # Content drift → miss (a changed chapter is not a cache hit).
        drifted = RawCacheKey(owner_user_id=str(owner), book_id=str(book), chapter_id=str(chap),
                              content_hash="h2", batch_idx=0, effort_band="none")
        assert await get_cached_batch(pool, drifted) is None

        # Profile change → miss (the /review-impl HIGH fix): same chapter/effort/batch but a
        # different extraction profile must NOT reuse the old profile's parse.
        new_profile = RawCacheKey(owner_user_id=str(owner), book_id=str(book), chapter_id=str(chap),
                                  content_hash="h1", batch_idx=0, profile_hash="p2", effort_band="none")
        assert await get_cached_batch(pool, new_profile) is None
        await tx.rollback()  # nothing persists (clean test DB)
    finally:
        await conn.close()
