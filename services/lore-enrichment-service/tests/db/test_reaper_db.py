"""Reaper ephemeral-corpus garbage collection against a REAL Postgres
(D-COMPOSE-CONTEXT-CORPUS-SCOPE, review-impl #5).

The unit tests in tests/test_reaper.py use a FakePool, so they assert the SQL
*shape* but never execute the `provenance_json->>'compose_ephemeral'='true'`
predicate. This pins the genuine round-trip: a corpus ingested through the SAME
`ingest_corpus(provenance_json=...)` seam compose uses is actually MATCHED + reaped
by `reap_ephemeral_corpora`, its chunks cascade, and an untagged (curated) corpus
is left untouched. Catches a future tag-key / JSON-shape drift the FakePool can't.

Skips when no real DB is reachable (conftest._dsn); verify supplies the Postgres.
"""

from __future__ import annotations

import uuid

import pytest

from app.retrieval.store import SourceCorpusStore

pytestmark = pytest.mark.asyncio


async def _embed(texts):
    # Deterministic 3-dim stub — the reaper doesn't care about vectors, but
    # ingest_corpus embeds every chunk, so return one vector per chunk.
    return [[0.1, 0.2, 0.3] for _ in texts]


async def test_reap_ephemeral_corpora_roundtrip(pool):
    store = SourceCorpusStore(pool)
    uid = uuid.uuid4()
    pid = uuid.uuid4()

    # (1) ephemeral compose corpus — tagged exactly as _ingest_context does.
    eph = await store.ingest_corpus(
        user_id=uid, project_id=pid, name="reaper-eph", kind="other",
        license="public_domain", text="蓬萊乃東海之上的仙山。" * 3,
        embed_fn=_embed, model_ref="m",
        provenance_json={"compose_ephemeral": True, "source": "compose", "book_id": str(uuid.uuid4())},
    )
    # (2) a curated reference corpus — NO ephemeral tag → must survive.
    curated = await store.ingest_corpus(
        user_id=uid, project_id=pid, name="reaper-curated", kind="history",
        license="public-domain", text="史料記載之事。" * 3,
        embed_fn=_embed, model_ref="m",
    )

    # Backdate both past the TTL so age isn't the discriminator (the TAG is).
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE source_corpus SET created_at = now() - interval '40 days' WHERE corpus_id = ANY($1)",
            [eph.corpus_id, curated.corpus_id],
        )

    deleted = await store.reap_ephemeral_corpora(ttl_seconds=30 * 24 * 3600)

    assert eph.corpus_id in deleted, "ephemeral corpus written by ingest was NOT matched by the reaper predicate"
    assert curated.corpus_id not in deleted, "curated (untagged) corpus must NOT be reaped"

    async with pool.acquire() as conn:
        eph_rows = await conn.fetchval("SELECT count(*) FROM source_corpus WHERE corpus_id=$1", eph.corpus_id)
        eph_chunks = await conn.fetchval("SELECT count(*) FROM source_corpus_chunk WHERE corpus_id=$1", eph.corpus_id)
        cur_rows = await conn.fetchval("SELECT count(*) FROM source_corpus WHERE corpus_id=$1", curated.corpus_id)
    assert eph_rows == 0, "reaped corpus row still present"
    assert eph_chunks == 0, "reaped corpus chunks did not cascade-delete"
    assert cur_rows == 1, "curated corpus was wrongly deleted"


async def test_reap_ephemeral_corpora_respects_ttl_and_noop(pool):
    store = SourceCorpusStore(pool)
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    eph = await store.ingest_corpus(
        user_id=uid, project_id=pid, name="reaper-fresh", kind="other",
        license="public_domain", text="新近貼上的內容。" * 3,
        embed_fn=_embed, model_ref="m",
        provenance_json={"compose_ephemeral": True},
    )
    # Fresh (created_at = now) → NOT past a 30d TTL → not reaped.
    assert eph.corpus_id not in await store.reap_ephemeral_corpora(ttl_seconds=30 * 24 * 3600)
    # ttl<=0 → no-op (never purges live data even when rows match the tag).
    assert await store.reap_ephemeral_corpora(ttl_seconds=0) == []
    async with pool.acquire() as conn:
        still = await conn.fetchval("SELECT count(*) FROM source_corpus WHERE corpus_id=$1", eph.corpus_id)
    assert still == 1
