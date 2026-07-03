"""CACHE/M6 raw-output offload (D-RAWCACHE-MINIO-OFFLOAD) — cold-archive the bulky
raw_response to object storage, NULL the DB column, fetch it back transparently, and let
retention delete orphaned blobs. Round-trips against real Postgres (skip when none) with an
in-memory blob store (no MinIO needed)."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.migrate import DDL
from app.workers.extraction_blobstore import InMemoryBlobStore
from app.workers.extraction_cache import (
    fetch_raw_response,
    offload_raw_responses,
    purge_stale_raw_outputs,
)

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)

# These tests do table-wide sweeps against the shared dev Postgres — serialize
# them onto one xdist worker (`-n auto --dist loadgroup`) or concurrent workers
# interleave their sweeps and the counts lie.
pytestmark = pytest.mark.xdist_group("pg")


class _ConnPool:
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


async def _seed_row(conn, *, owner, book, chap, content_hash, raw, created_at, batch_idx=0):
    return await conn.fetchval(
        """INSERT INTO extraction_raw_outputs
           (owner_user_id, book_id, chapter_id, chapter_content_hash, batch_idx,
            raw_response, parsed_entities, parse_status, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,'[]','ok',$7) RETURNING id""",
        owner, book, chap, content_hash, batch_idx, raw, created_at,
    )


async def _with_pg(fn):
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    try:
        await conn.execute(DDL)
        # Hermetic shadow: a TEMP table shadows public.extraction_raw_outputs in
        # this connection's search_path, so the table-wide sweeps under test see
        # ONLY the rows this test seeds — naturally-aged rows in the shared dev
        # DB must not leak into the offload/purge counts.
        await conn.execute(
            "CREATE TEMP TABLE extraction_raw_outputs "
            "(LIKE extraction_raw_outputs INCLUDING ALL)"
        )
        tx = conn.transaction()
        await tx.start()
        try:
            await fn(conn, _ConnPool(conn))
        finally:
            await tx.rollback()
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_offload_archives_old_bodies_and_nulls_column():
    async def body(conn, pool):
        store = InMemoryBlobStore()
        owner, book, chap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        old = datetime.now(timezone.utc) - timedelta(days=30)
        fresh = datetime.now(timezone.utc)
        old_id = await _seed_row(conn, owner=owner, book=book, chap=chap,
                                 content_hash="h1", raw="VERBATIM-OLD", created_at=old)
        fresh_id = await _seed_row(conn, owner=owner, book=book, chap=chap,
                                   content_hash="h2", raw="VERBATIM-FRESH", created_at=fresh,
                                   batch_idx=1)

        res = await offload_raw_responses(pool, store, older_than_days=7)
        assert res["offloaded"] == 1 and res["bytes"] == len(b"VERBATIM-OLD")

        # Old row: body NULLed, uri set, blob archived under a tenant-prefixed key.
        row = await conn.fetchrow(
            "SELECT raw_response, raw_response_uri FROM extraction_raw_outputs WHERE id=$1", old_id)
        assert row["raw_response"] == "" and row["raw_response_uri"] == f"raw/{owner}/{old_id}"
        assert await store.get(row["raw_response_uri"]) == b"VERBATIM-OLD"

        # Fresh row (inside the hot window): untouched.
        fr = await conn.fetchrow(
            "SELECT raw_response, raw_response_uri FROM extraction_raw_outputs WHERE id=$1", fresh_id)
        assert fr["raw_response"] == "VERBATIM-FRESH" and fr["raw_response_uri"] is None

        # Idempotent: a second sweep finds nothing new (uri now set).
        assert (await offload_raw_responses(pool, store, older_than_days=7))["offloaded"] == 0
    await _with_pg(body)


@pytest.mark.asyncio
async def test_fetch_raw_response_transparent_after_offload():
    async def body(conn, pool):
        store = InMemoryBlobStore()
        owner, book, chap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        rid = await _seed_row(conn, owner=owner, book=book, chap=chap, content_hash="h1",
                              raw="THE-BODY", created_at=datetime.now(timezone.utc) - timedelta(days=30))
        # Inline before offload.
        assert await fetch_raw_response(pool, store, str(rid)) == "THE-BODY"
        await offload_raw_responses(pool, store, older_than_days=7)
        # After offload the column is empty but fetch transparently reads the archive.
        assert await fetch_raw_response(pool, store, str(rid)) == "THE-BODY"
    await _with_pg(body)


@pytest.mark.asyncio
async def test_offload_disabled_when_store_none():
    async def body(conn, pool):
        owner, book, chap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await _seed_row(conn, owner=owner, book=book, chap=chap, content_hash="h1",
                        raw="X", created_at=datetime.now(timezone.utc) - timedelta(days=30))
        res = await offload_raw_responses(pool, None, older_than_days=7)
        assert res["offloaded"] == 0 and res.get("disabled") is True
    await _with_pg(body)


@pytest.mark.asyncio
async def test_offload_owner_scope():
    async def body(conn, pool):
        store = InMemoryBlobStore()
        a, b, book, chap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        old = datetime.now(timezone.utc) - timedelta(days=30)
        await _seed_row(conn, owner=a, book=book, chap=chap, content_hash="h1", raw="A", created_at=old)
        await _seed_row(conn, owner=b, book=book, chap=chap, content_hash="h1", raw="B", created_at=old)
        res = await offload_raw_responses(pool, store, older_than_days=7, owner_user_id=str(a))
        assert res["offloaded"] == 1  # only owner A's row swept
        brow = await conn.fetchrow(
            "SELECT raw_response FROM extraction_raw_outputs WHERE owner_user_id=$1", b)
        assert brow["raw_response"] == "B"  # B untouched
    await _with_pg(body)


class _DeleteCountingStore(InMemoryBlobStore):
    """Records delete calls — offload must NEVER delete (deterministic keys mean a re-upload
    is the same object; deleting could orphan a concurrent winner's live pointer)."""

    def __init__(self):
        super().__init__()
        self.deletes = 0

    async def delete(self, uri):
        self.deletes += 1
        await super().delete(uri)


@pytest.mark.asyncio
async def test_offload_never_deletes_blobs():
    async def body(conn, pool):
        store = _DeleteCountingStore()
        owner, book, chap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        old = datetime.now(timezone.utc) - timedelta(days=30)
        await _seed_row(conn, owner=owner, book=book, chap=chap, content_hash="h1",
                        raw="BODY", created_at=old)
        await offload_raw_responses(pool, store, older_than_days=7)
        await offload_raw_responses(pool, store, older_than_days=7)  # re-run hits no rows
        assert store.deletes == 0  # offload is delete-free; only retention deletes blobs
        assert any(v == b"BODY" for v in store._blobs.values())  # archive intact
    await _with_pg(body)


@pytest.mark.asyncio
async def test_purge_deletes_offloaded_blob_no_orphan():
    async def body(conn, pool):
        store = InMemoryBlobStore()
        owner, book, chap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        # Two generations (h1 older, h2 newer); offload h1's body, then purge keep=1 → h1 dropped.
        await _seed_row(conn, owner=owner, book=book, chap=chap, content_hash="h1",
                        raw="OLDGEN", created_at=base)
        await _seed_row(conn, owner=owner, book=book, chap=chap, content_hash="h2",
                        raw="NEWGEN", created_at=base + timedelta(hours=1))
        await offload_raw_responses(pool, store, older_than_days=0)  # archive both bodies
        # The h1 blob exists in the store…
        key_h1 = next(k for k in store._blobs if store._blobs[k] == b"OLDGEN")
        assert key_h1 in store._blobs
        deleted = await purge_stale_raw_outputs(pool, keep=1, store=store)
        assert deleted == 1  # h1 generation purged
        # …and its orphaned blob was cleaned up; the kept gen's blob survives.
        assert key_h1 not in store._blobs
        assert any(v == b"NEWGEN" for v in store._blobs.values())
    await _with_pg(body)
