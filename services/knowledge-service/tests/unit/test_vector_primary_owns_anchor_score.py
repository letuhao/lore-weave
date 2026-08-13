"""D-T25B-PG-ANCHOR-SCORE — the guard on the entity read path.

WHAT THIS IS PROTECTING
-----------------------
Entity retrieval is two-layer: consumers rank by `weighted_score = raw_score * anchor_score`
(`context/selectors/glossary.py`, `routers/public/entities.py`). `PgVectorStore` cannot supply
`anchor_score`, and — importantly — that is NOT a gap to fill in the adapter.

`recompute_anchor_score` computes `mention_count / max(mention_count)` across a **bucket**. The
value therefore changes when a DIFFERENT entity's mention count moves, without the entity
itself being touched at all. A copy on the vector row would need rewriting for every row in the
bucket on every recompute — a mirror that drifts by construction, which is the exact failure
T27, T28 and T29 each spent a task closing. Writing it through would be the wrong fix, not a
smaller one.

So the boundary stands: the store that OWNS `anchor_score` serves the entity read path. Today
that is satisfied for free, because dual-write reads the primary and the primary is Neo4j.

WHY A TEST AND NOT A COMMENT
----------------------------
The risk is not in today's code — it is in the change that makes Postgres primary. Nobody
reads a note in a file they are not editing, and the plan's own history says so: T27 shipped
handlers that could never run, and what finally caught it was a live run, not the reasoning
written beside them. This test fails the moment the primary changes, and says why.
"""

from __future__ import annotations

import pytest
from unittest import mock

from app.adapters.dual_write_vector_store import DualWriteVectorStore


class _RecordingStore:
    """Answers `search` and records that it was asked. Stands in for either backend."""

    def __init__(self, name):
        self.name = name
        self.searched: list[str] = []

    async def search(self, *, scope, user_id, embedding, dim, k=10, filter=None,
                     include_vectors=False):
        # T24b — the flag is accepted rather than dropped. A double whose signature is
        # NARROWER than the port's fails at the call, which is how this one caught the
        # parameter being added; keeping it narrow would just move the break later.
        self.include_vectors_seen = include_vectors
        self.searched.append(scope)
        return []

    async def upsert(self, record):
        return True


@pytest.mark.asyncio
async def test_entity_reads_go_to_the_store_that_owns_anchor_score():
    """Dual-write reads the PRIMARY. Entity retrieval ranks by anchor_score, which lives on
    the graph — so the primary is the only store that can answer it correctly."""
    primary, secondary = _RecordingStore("neo4j"), _RecordingStore("pg")
    store = DualWriteVectorStore(primary, secondary)

    await store.search(scope="entity", user_id="u", embedding=[0.1], dim=1, k=5)

    assert primary.searched == ["entity"]
    assert secondary.searched == [], (
        "an entity search reached the SECONDARY. If that is deliberate, "
        "D-T25B-PG-ANCHOR-SCORE must be closed first: PgVectorStore hits carry no "
        "anchor_score, so two-layer ranking would silently collapse to raw cosine."
    )


@pytest.mark.asyncio
async def test_the_provider_keeps_neo4j_as_primary():
    """The tripwire, and **it fired.** It was written at T25b to red the day somebody swapped
    the dual-write arguments to begin the cutover, and on 2026-08-13 that is exactly what it
    did — before the change shipped.

    So the invariant it guards is now the DESIGN rather than a veto: the cutover is
    per-scope. Passages move to Postgres; **entity reads stay on Neo4j**, because
    `PgVectorStore` omits `anchor_score` (D-T25B-PG-ANCHOR-SCORE) and entity reads rank by
    it.

    Rewritten to assert BEHAVIOUR rather than the source text it used to grep. The old form
    pinned the literal `DualWriteVectorStore(primary, secondary`, which a correct per-scope
    cutover cannot satisfy and an incorrect one could fake with a rename. Which store answers
    an entity search is the thing that matters, so that is what is asked.
    """
    from app.adapters.dual_write_vector_store import DualWriteVectorStore

    neo4j = _RecordingStore("neo4j")
    pg = _RecordingStore("pg")
    # Composed exactly as `get_vector_store` composes it AFTER the cutover: pg first,
    # passages only.
    store = DualWriteVectorStore(pg, neo4j, primary_read_scopes=frozenset({"passage"}))

    await store.search(scope="entity", user_id="u", embedding=[0.1], dim=1, k=5)
    assert neo4j.searched == ["entity"], (
        "post-cutover, an ENTITY search must still be answered by Neo4j — pg hits carry no "
        "anchor_score, so two-layer ranking would silently collapse to raw cosine")
    assert pg.searched == [], "an entity search reached the pgvector store"

    await store.search(scope="passage", user_id="u", embedding=[0.1], dim=1, k=5)
    assert pg.searched == ["passage"], (
        "post-cutover, a PASSAGE search must be answered by Postgres — otherwise the switch "
        "is set, the logs say cut over, and nothing changed")


@pytest.mark.asyncio
async def test_the_cutover_switch_REFUSES_a_configuration_it_cannot_honour(monkeypatch):
    """`read_primary='postgres'` with no DSN would serve Neo4j and look identical to a
    correctly pre-cutover deployment. The operator would read "cutover complete" off a
    system that never cut over, which is the failure mode this whole plan keeps finding.

    A typo is the same class: anything that is not one of the two known values must not
    quietly mean "neo4j".
    """
    from app.adapters import vector_store_provider as provider

    monkeypatch.setattr(provider.settings, "knowledge_vector_db_url", "", raising=False)
    monkeypatch.setattr(provider.settings, "knowledge_vector_read_primary", "postgres",
                        raising=False)
    with pytest.raises(ValueError, match="requires KNOWLEDGE_VECTOR_DB_URL"):
        await provider.get_vector_store(mock.MagicMock())

    monkeypatch.setattr(provider.settings, "knowledge_vector_read_primary", "postgress",
                        raising=False)
    with pytest.raises(ValueError, match="must be 'neo4j' or 'postgres'"):
        await provider.get_vector_store(mock.MagicMock())


@pytest.mark.asyncio
async def test_a_pg_entity_hit_is_honest_about_what_it_omits():
    """The other half: the adapter must not invent the score it cannot know.

    Omitted from the dict rather than set to None, so a consumer that ranks by it raises
    KeyError instead of multiplying every score by nothing and quietly returning cosine order.
    """
    # The class-level promise, asserted without a database: the entity attribute tuple is the
    # exhaustive list of what a pg entity hit carries.
    from app.adapters.pg_vector_store import _ENTITY_ATTRS

    assert "anchor_score" not in _ENTITY_ATTRS
    assert set(_ENTITY_ATTRS) == {"project_id", "archived"}, (
        f"the pg entity hit shape changed to {_ENTITY_ATTRS}. If anchor_score was added, "
        "D-T25B-PG-ANCHOR-SCORE needs revisiting — a stored copy of a bucket-relative score "
        "goes stale whenever any OTHER entity in the bucket changes."
    )


def test_the_deferral_is_recorded_where_the_next_reader_will_look():
    """A tracked deferral that exists only in a commit message is not tracked. The plan is
    the artifact the next session reads first."""
    from pathlib import Path

    plan = Path(__file__).resolve().parents[4] / "docs/plans/2026-08-09-knowledge-architecture-refactor.md"
    if not plan.exists():  # the suite must run outside a full checkout
        pytest.skip("plan not present in this checkout")
    assert "D-T25B-PG-ANCHOR-SCORE" in plan.read_text(encoding="utf-8"), (
        "the deferral vanished from the plan while the code still depends on it"
    )


# ── the secondary must never be able to fail the primary write (OD-2, 2026-08-12) ──


@pytest.mark.asyncio
async def test_an_unreachable_secondary_degrades_to_primary_only_instead_of_raising():
    """🔴 REGRESSION. Found by the OD-2 live run on the first day the secondary was on.

    `DualWriteVectorStore.upsert` swallows a secondary exception — but only once the store
    EXISTS. Building it was the hole: `_vector_pool()` opens the pool lazily inside
    `get_vector_store`, so with the DSN set and the secondary unreachable the composition
    root RAISED, and passage ingestion failed outright. The primary is the system of record
    and it never got written; an optional secondary took down the required path.

        socket.gaierror: [Errno -3] Temporary failure in name resolution

    Asserting on the RETURNED store, not on a log line: the defect is what the caller gets
    back, and a test that only checked the error message would pass against a version that
    still raised.
    """
    from app.adapters import vector_store_provider as provider
    from app.adapters.neo4j_vector_store import Neo4jVectorStore

    async def boom():
        raise OSError("secondary is down")

    with mock.patch.object(provider, "_vector_pool", boom), \
         mock.patch.object(provider.settings, "knowledge_vector_db_url",
                           "postgresql://x/y", create=True):
        store = await provider.get_vector_store(mock.MagicMock())

    assert isinstance(store, Neo4jVectorStore), (
        f"got {type(store).__name__}: an unreachable secondary must degrade to the "
        "primary-only store, never propagate out of the composition root"
    )


@pytest.mark.asyncio
async def test_the_degrade_is_counted_so_a_zero_still_means_nothing_failed():
    """The other half, and the reason this is not just a `try/except: pass`.

    `D-T25B-SOAK` exists because a counter reading zero when nothing is wired is
    indistinguishable from one reading zero when nothing failed. A silent degrade would
    rebuild that exact trap one layer up — writes would flow to Neo4j alone, the operator
    would see `secondary_failed == 0`, and the cutover would be authorised against a store
    missing every row written during the outage.
    """
    from app.adapters import vector_store_provider as provider
    from app.metrics import vector_dual_write_total

    def _count() -> float:
        total = 0.0
        for metric in vector_dual_write_total.collect():
            for s in metric.samples:
                if s.name.endswith("_total") and s.labels.get("outcome") == "secondary_failed":
                    total += s.value
        return total

    async def boom():
        raise OSError("secondary is down")

    before = _count()
    with mock.patch.object(provider, "_vector_pool", boom), \
         mock.patch.object(provider.settings, "knowledge_vector_db_url",
                           "postgresql://x/y", create=True):
        await provider.get_vector_store(mock.MagicMock())

    assert _count() > before, (
        "an unreachable secondary was not counted — the soak gate would read zero and "
        "authorise a cutover onto a store that is missing rows"
    )
