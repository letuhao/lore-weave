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
    purge_stale_raw_outputs,
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
        # D-CACHE-MODEL-KEY: the producing model round-trips (for the bust-on-model-change check).
        assert hit["model_ref"]  # _put wrote a model_ref

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


@pytest.mark.asyncio
async def test_put_overwrite_refreshes_on_model_bust():
    # D-CACHE-MODEL-KEY: a plain put can't refresh a busted row (model isn't in the key, so
    # ON CONFLICT DO NOTHING keeps the old parse); put_batch(overwrite=True) DOES, so a
    # model-change bust re-extracts AND updates the cache (no perpetual re-bust).
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    owner = uuid.uuid4()
    model_a, model_b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        await conn.execute(DDL)
        pool = _ConnPool(conn)
        tx = conn.transaction()
        await tx.start()
        book, chap = uuid.uuid4(), uuid.uuid4()
        key = RawCacheKey(owner_user_id=str(owner), book_id=str(book), chapter_id=str(chap),
                          content_hash="h1", batch_idx=0, effort_band="none")
        await _put(pool, key, model_ref=model_a, parsed_entities=[{"name": "A"}])
        # plain re-put with model B → DO NOTHING, model A's parse survives.
        await _put(pool, key, model_ref=model_b, parsed_entities=[{"name": "B"}])
        hit = await get_cached_batch(pool, key)
        assert hit["parsed_entities"] == [{"name": "A"}] and hit["model_ref"] == model_a
        # overwrite put → refreshes to model B's parse.
        await _put(pool, key, model_ref=model_b, parsed_entities=[{"name": "B"}], overwrite=True)
        hit2 = await get_cached_batch(pool, key)
        assert hit2["parsed_entities"] == [{"name": "B"}] and hit2["model_ref"] == model_b
        await tx.rollback()
    finally:
        await conn.close()


async def _seed_generation(conn, *, owner, book, chapter, content_hash, created_at,
                           batches=(0, 1), effort_band="none", profile_hash=""):
    """Insert one content-hash GENERATION (one row per batch_idx) for a chapter at a
    controlled `created_at`, so the retention ranking is deterministic (put_batch would
    stamp now() for every row)."""
    for b in batches:
        await conn.execute(
            """INSERT INTO extraction_raw_outputs
               (owner_user_id, book_id, chapter_id, chapter_content_hash, chapter_chunk_idx,
                batch_idx, profile_hash, effort_band, parsed_entities, parse_status, created_at)
               VALUES ($1,$2,$3,$4,0,$5,$6,$7,'[]','ok',$8)""",
            owner, book, chapter, content_hash, b, profile_hash, effort_band, created_at,
        )


@pytest.mark.asyncio
async def test_retention_keeps_latest_k_generations_per_chapter():
    """CACHE/M6 retention: keep the latest K content-hash generations per (owner, book,
    chapter); purge older ones. Tenant-isolated; scope filters narrow the sweep."""
    from datetime import datetime, timedelta, timezone
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    owner, other = uuid.uuid4(), uuid.uuid4()
    book, chap, chap2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    try:
        await conn.execute(DDL)
        pool = _ConnPool(conn)
        tx = conn.transaction()
        await tx.start()

        async def _hashes(owner_id=owner, chapter=chap):
            rows = await conn.fetch(
                "SELECT DISTINCT chapter_content_hash FROM extraction_raw_outputs "
                "WHERE owner_user_id=$1 AND chapter_id=$2 ORDER BY 1", owner_id, chapter)
            return {r["chapter_content_hash"] for r in rows}

        # 4 generations of one chapter (h1 oldest … h4 newest), 2 batches each = 8 rows.
        for i, h in enumerate(["h1", "h2", "h3", "h4"]):
            await _seed_generation(conn, owner=owner, book=book, chapter=chap,
                                   content_hash=h, created_at=base + timedelta(hours=i))
        # A second chapter (its own generations must NOT count against chap's keep window).
        await _seed_generation(conn, owner=owner, book=book, chapter=chap2,
                               content_hash="c2", created_at=base)
        # A DIFFERENT tenant, same book/chapter — INV-9: never purged by owner's sweep.
        await _seed_generation(conn, owner=other, book=book, chapter=chap,
                               content_hash="o1", created_at=base)

        # keep=2 → drop h1,h2 (rank 3,4), keep h3,h4. 4 rows deleted (2 gens × 2 batches).
        deleted = await purge_stale_raw_outputs(pool, keep=2)
        assert deleted == 4
        assert await _hashes() == {"h3", "h4"}
        # second chapter untouched (separate partition), other tenant untouched (INV-9).
        assert await _hashes(chapter=chap2) == {"c2"}
        assert await _hashes(owner_id=other) == {"o1"}

        # Idempotent: a re-run with nothing newly stale deletes 0.
        assert await purge_stale_raw_outputs(pool, keep=2) == 0

        # keep floored to 1: keep only the newest (h4). Scoped to this chapter only.
        deleted2 = await purge_stale_raw_outputs(
            pool, keep=0, owner_user_id=str(owner), book_id=str(book), chapter_id=str(chap))
        assert deleted2 == 2  # h3's 2 rows
        assert await _hashes() == {"h4"}

        await tx.rollback()
    finally:
        await conn.close()
