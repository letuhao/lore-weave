"""The dual-write actually reaches Postgres (plan T25a).

**This is the test the whole of Phase 3 was missing.** T22 built the image, T23 the adapter,
T24 the dual-write store — and nothing constructed any of them, so
`vector_dual_write_total{outcome="secondary_failed"}` sat at zero because no write reached
it. Zero-because-nothing-is-wired and zero-because-nothing-failed look identical on a
dashboard, and only the first one is a lie.

The unit tests around the write sites patch `get_vector_store`, which proves the call site
calls a store. It cannot prove a row lands in another database — that is this file's job,
and it is why the assertions here are `SELECT`s against a real Postgres rather than mock
call counts.

Requires TEST_VECTOR_DB_URL (see the `vector_pool` fixture); skipped without it.
"""

from __future__ import annotations

import pytest

from app.adapters.dual_write_vector_store import DualWriteVectorStore
from app.adapters.fake_vector_store import FakeVectorStore
from app.adapters.pg_vector_store import PgVectorStore, ensure_vector_schema, passage_table
from app.metrics import vector_dual_write_total
from app.ports.vector_store import PassageVectorRecord

pytestmark = pytest.mark.asyncio

_DIM = 384
_USER = "dw-live-user"


def _count(**labels) -> float:
    return vector_dual_write_total.labels(**labels)._value.get()


def _passage(source_id: str) -> PassageVectorRecord:
    vec = [0.0] * _DIM
    vec[0] = 1.0
    return PassageVectorRecord(
        user_id=_USER, project_id="dw-live-project", source_type="chapter",
        source_id=source_id, chunk_index=0, text=f"text {source_id}",
        embedding=vec, embedding_dim=_DIM, embedding_model="model-a",
    )


@pytest.fixture
async def dual(vector_pool):
    await ensure_vector_schema(vector_pool, dims=(_DIM,))
    primary = FakeVectorStore()
    return DualWriteVectorStore(primary, PgVectorStore(vector_pool)), primary


async def test_a_write_through_the_seam_lands_a_row_in_postgres(dual, vector_pool):
    """The claim T25a exists to make true. Mock-green is not evidence here: the whole
    failure mode is that the secondary is never reached, and only the secondary's own
    database can testify to that."""
    store, primary = dual
    before = _count(scope="passage", outcome="both")

    assert await store.upsert(_passage("live-1")) is True

    async with vector_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT source_id, text, embedding_model FROM {passage_table(_DIM)} "
            f"WHERE user_id = $1 AND source_id = $2", _USER, "live-1",
        )
    assert row is not None, "the write never reached Postgres — the seam is decorative"
    assert row["text"] == "text live-1"
    assert row["embedding_model"] == "model-a"
    assert primary.record_count("passage") == 1, "the primary must still receive the write"
    assert _count(scope="passage", outcome="both") == before + 1


async def test_the_cutover_gate_can_actually_move(dual, vector_pool):
    """`secondary_failed` is the gate that authorises the T25 cutover. A counter that
    cannot be made to move is not a gate — so this makes it move, on purpose.

    The secondary is given a record whose dim is outside the closed set, which
    `PgVectorStore` refuses before any SQL. The user request still succeeds (the secondary
    is not authoritative during a migration) and the failure is recorded.
    """
    store, primary = dual
    before_failed = _count(scope="passage", outcome="secondary_failed")

    bad = PassageVectorRecord(
        user_id=_USER, project_id="p", source_type="chapter", source_id="unsupported-dim",
        chunk_index=0, text="t", embedding=[0.1, 0.2], embedding_dim=2,
        embedding_model="m",
    )
    # The FAKE primary accepts any dim; only the Postgres secondary has a closed set. That
    # asymmetry is the point — it reproduces "the primary succeeded, the secondary did not"
    # without needing to break a connection.
    assert await store.upsert(bad) is True
    assert primary.record_count("passage") == 1

    assert _count(scope="passage", outcome="secondary_failed") == before_failed + 1, (
        "the gate did not move for a write the secondary rejected — it would read zero at "
        "cutover for exactly the wrong reason"
    )


async def test_the_secondary_is_never_read_from(dual, vector_pool):
    """Write both, read the primary. A read served from a half-populated secondary would be
    a correctness regression bought for nothing, so the stores are seeded with DIFFERENT
    data and the answer must come from the primary."""
    store, primary = dual
    await store.upsert(_passage("in-both"))
    # Postgres-only row, invisible to the primary.
    secondary_only = _passage("secondary-only")
    await PgVectorStore(vector_pool).upsert(secondary_only)

    probe = [0.0] * _DIM
    probe[0] = 1.0
    hits = await store.search(scope="passage", user_id=_USER, embedding=probe, dim=_DIM, k=10)
    ids = {h.record_id for h in hits}
    assert any("in-both" in i for i in ids)
    assert not any("secondary-only" in i for i in ids), (
        "a row only the secondary has came back from a read — reads have silently cut over"
    )
