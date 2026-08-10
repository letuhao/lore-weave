"""`DualWriteVectorStore` (plan T24).

The migration seam between T23's adapter and T25's cutover. What is worth testing here is
not that two calls happen — it is the ASYMMETRY, and every place the store is allowed to
swallow something:

  * a secondary write failure is swallowed **and counted**, because the count is the only
    evidence that survives to the cutover gate;
  * a primary failure is not swallowed at all;
  * a shadow read can never change or break the request it measures;
  * a shadow read that FAILED is not agreement — the distinction the metric exists for.

Two `FakeVectorStore`s make this deterministic: they compute real cosine similarity, so a
divergence in these tests is a divergence the same code would see in production.
"""

from __future__ import annotations

import inspect
import random

import pytest

from app.adapters.dual_write_vector_store import DualWriteVectorStore
from app.adapters.fake_vector_store import FakeVectorStore
from app.metrics import (
    vector_dual_write_total,
    vector_shadow_read_total,
)
from app.ports.vector_store import PassageVectorRecord, VectorStore

_USER = "dw-user"
_PROJECT = "dw-project"


def _passage(source_id: str, embedding: list[float], **kw) -> PassageVectorRecord:
    return PassageVectorRecord(
        user_id=kw.pop("user_id", _USER),
        project_id=kw.pop("project_id", _PROJECT),
        source_type=kw.pop("source_type", "chapter"),
        source_id=source_id,
        chunk_index=kw.pop("chunk_index", 0),
        text=kw.pop("text", f"text for {source_id}"),
        embedding=embedding,
        embedding_dim=kw.pop("embedding_dim", len(embedding)),
        **kw,
    )


class _Exploding:
    """A store where exactly one named method raises. Everything else delegates, so a test
    exercises one failure at a time instead of a store that is broken all over."""

    def __init__(self, inner, failing: str) -> None:
        self._inner, self._failing = inner, failing

    def __getattr__(self, name):
        if name == self._failing:
            async def _boom(*a, **kw):
                raise RuntimeError(f"{name} is down")
            return _boom
        return getattr(self._inner, name)


def _count(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


# ── writes ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_write_reaches_both_stores():
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    store = DualWriteVectorStore(primary, secondary)
    assert await store.upsert(_passage("ch1", [1.0, 0.0])) is True
    assert primary.record_count("passage") == 1
    assert secondary.record_count("passage") == 1


@pytest.mark.asyncio
async def test_a_secondary_failure_is_swallowed_but_counted():
    """The count IS the cutover gate. T25 drops the primary's indexes, and a swallowed
    failure is invisible by construction — the caller got its success — so a series that
    reads zero is the only thing that distinguishes "nothing failed" from "we never
    looked"."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    store = DualWriteVectorStore(primary, _Exploding(secondary, "upsert"))
    before = _count(vector_dual_write_total, scope="passage", outcome="secondary_failed")

    assert await store.upsert(_passage("ch1", [1.0, 0.0])) is True  # the caller is unharmed
    assert primary.record_count("passage") == 1
    assert secondary.record_count("passage") == 0

    after = _count(vector_dual_write_total, scope="passage", outcome="secondary_failed")
    assert after == before + 1, "a swallowed failure that is not counted leaves no evidence"


@pytest.mark.asyncio
async def test_a_backfill_can_ask_for_fail_closed_instead():
    """A backfill has no user request to protect, and a missing row is the only thing that
    matters to it — so the same store flips to fail-closed rather than needing a second."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    store = DualWriteVectorStore(
        primary, _Exploding(secondary, "upsert"), raise_on_secondary_failure=True,
    )
    with pytest.raises(RuntimeError, match="upsert is down"):
        await store.upsert(_passage("ch1", [1.0, 0.0]))


@pytest.mark.asyncio
async def test_a_primary_failure_propagates_and_the_secondary_is_left_alone():
    """The primary is still the system of record. Writing the secondary after the primary
    refused would put a row in the store we are about to promote that the authoritative
    store does not have."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    store = DualWriteVectorStore(_Exploding(primary, "upsert"), secondary)
    before = _count(vector_dual_write_total, scope="passage", outcome="primary_failed")

    with pytest.raises(RuntimeError, match="upsert is down"):
        await store.upsert(_passage("ch1", [1.0, 0.0]))

    assert secondary.record_count("passage") == 0
    assert _count(vector_dual_write_total, scope="passage", outcome="primary_failed") == before + 1


@pytest.mark.asyncio
async def test_a_target_the_primary_refused_is_not_written_to_the_secondary():
    """`False` means the entity was deleted between embedding and write. Seeding the
    secondary with it anyway would resurrect, at cutover, a row the primary rejected."""
    from app.ports.vector_store import EntityVectorRecord

    primary, secondary = FakeVectorStore(), FakeVectorStore()
    primary.register_entities([])           # nothing exists
    secondary.register_entities(["e-1"])    # ... but it would accept the write
    store = DualWriteVectorStore(primary, secondary)

    rec = EntityVectorRecord(user_id=_USER, entity_id="e-1", embedding=[1.0, 0.0],
                             embedding_dim=2, embedding_model="m", embedding_version=1)
    assert await store.upsert(rec) is False
    assert secondary.record_count("entity") == 0


# ── reads ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reads_come_from_the_primary_even_when_the_secondary_disagrees():
    """The stores are seeded with DIFFERENT data on purpose: a read served from a
    half-populated secondary would be a correctness regression bought for nothing, so this
    has to fail if the read ever switches sides."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    await primary.upsert(_passage("from-primary", [1.0, 0.0]))
    await secondary.upsert(_passage("from-secondary", [1.0, 0.0]))

    store = DualWriteVectorStore(primary, secondary)
    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(hits) == 1 and "from-primary" in hits[0].record_id


@pytest.mark.asyncio
async def test_the_shadow_read_measures_divergence_without_changing_the_answer():
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    for sid in ("a", "b"):
        await primary.upsert(_passage(sid, [1.0, 0.0]))
    await secondary.upsert(_passage("a", [1.0, 0.0]))  # secondary is missing "b"

    store = DualWriteVectorStore(primary, secondary, shadow_read_rate=1.0)
    before = _count(vector_shadow_read_total, outcome="compared")

    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(hits) == 2, "the shadow read must not touch the response"
    assert _count(vector_shadow_read_total, outcome="compared") == before + 1


@pytest.mark.asyncio
async def test_a_broken_secondary_neither_breaks_the_request_nor_counts_as_agreement():
    """A monitoring tool that causes the outage it reports is worse than no monitoring —
    and one that scores its own failure as `overlap=1.0` is worse still, because the
    dashboard then says the two backends agree perfectly while one of them is down."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    await primary.upsert(_passage("a", [1.0, 0.0]))

    store = DualWriteVectorStore(
        primary, _Exploding(secondary, "search"), shadow_read_rate=1.0,
    )
    before_failed = _count(vector_shadow_read_total, outcome="failed")
    before_compared = _count(vector_shadow_read_total, outcome="compared")

    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(hits) == 1
    assert _count(vector_shadow_read_total, outcome="failed") == before_failed + 1
    assert _count(vector_shadow_read_total, outcome="compared") == before_compared


@pytest.mark.asyncio
async def test_sampling_skips_the_shadow_read_and_says_so():
    """Pinned RNG, and a rate strictly between 0 and 1 — rate 1.0 is the one setting that
    never exercises the sampling branch at all."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    await primary.upsert(_passage("a", [1.0, 0.0]))

    rng = random.Random()
    rng.random = lambda: 0.99  # above the rate → skip
    store = DualWriteVectorStore(
        primary, _Exploding(secondary, "search"), shadow_read_rate=0.5, rng=rng,
    )
    before_skipped = _count(vector_shadow_read_total, outcome="skipped_sampling")
    before_failed = _count(vector_shadow_read_total, outcome="failed")

    # The secondary would RAISE if it were consulted, so this also proves the skip is real
    # rather than a swallowed failure that merely looks like one.
    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(hits) == 1
    assert _count(vector_shadow_read_total, outcome="skipped_sampling") == before_skipped + 1
    assert _count(vector_shadow_read_total, outcome="failed") == before_failed, (
        "the secondary was consulted and swallowed, which is not the same as skipped"
    )


@pytest.mark.asyncio
async def test_shadow_reading_is_off_by_default():
    """Default-off matters: this store is composed into a live read path, and a default
    that doubled every search's backend calls would be a performance change nobody asked
    for."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    await primary.upsert(_passage("a", [1.0, 0.0]))
    store = DualWriteVectorStore(primary, _Exploding(secondary, "search"))
    assert len(await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0],
                                  dim=2, k=10)) == 1


@pytest.mark.parametrize("rate", [-0.1, 1.5])
def test_an_impossible_sample_rate_is_refused(rate):
    with pytest.raises(ValueError, match="shadow_read_rate"):
        DualWriteVectorStore(FakeVectorStore(), FakeVectorStore(), shadow_read_rate=rate)


# ── index lifecycle ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_index_reaches_both_and_does_not_swallow():
    """Unlike a row write: a missing index makes every subsequent write to that store
    unindexed, which is systematic rather than one lost row — and it is discovered at one
    call per job start instead of at cutover."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    proj = "11111111-1111-1111-1111-111111111111"
    model = "22222222-2222-2222-2222-222222222222"

    store = DualWriteVectorStore(primary, secondary)
    names = await store.ensure_index(project_id=proj, embedding_model_uuid=model,
                                     embedding_dimension=1024)
    assert set(names) == {"chapter", "part", "book"}
    assert len(await secondary.list_indexes()) == 3

    broken = DualWriteVectorStore(primary, _Exploding(secondary, "ensure_index"))
    with pytest.raises(RuntimeError, match="ensure_index is down"):
        await broken.ensure_index(project_id=proj, embedding_model_uuid=model,
                                  embedding_dimension=1024)


@pytest.mark.asyncio
async def test_drop_and_list_stay_on_the_primary():
    """The two stores name their indexes in different namespaces — T23's Postgres names are
    deliberately unparseable as Neo4j summary names — so forwarding a name across would
    either raise or match something unintended, and merging the lists would hand the
    prune-orphans path names it cannot attribute to a store before dropping them."""
    primary, secondary = FakeVectorStore(), FakeVectorStore()
    proj = "11111111-1111-1111-1111-111111111111"
    model = "22222222-2222-2222-2222-222222222222"
    names = await primary.ensure_index(project_id=proj, embedding_model_uuid=model,
                                       embedding_dimension=1024)
    await secondary.ensure_index(project_id=proj, embedding_model_uuid=model,
                                 embedding_dimension=1024)

    store = DualWriteVectorStore(primary, secondary)
    assert len(await store.list_indexes()) == 3
    await store.drop_index(name=names["chapter"])
    assert len(await primary.list_indexes()) == 2
    assert len(await secondary.list_indexes()) == 3


def test_it_matches_the_port_signatures():
    """Same structural check the other adapters get: `isinstance` against a
    `runtime_checkable` Protocol passes as soon as the method NAMES exist."""
    for name in ("search", "upsert", "ensure_index", "drop_index", "list_indexes"):
        port_sig = inspect.signature(getattr(VectorStore, name))
        impl_sig = inspect.signature(getattr(DualWriteVectorStore, name))
        assert list(impl_sig.parameters) == list(port_sig.parameters), (
            f"DualWriteVectorStore.{name} {list(impl_sig.parameters)} != "
            f"port {list(port_sig.parameters)}"
        )
