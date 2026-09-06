"""The `VectorStore` port contract (plan T14).

The fake is about to carry the ~561 tests that currently skip without a live Neo4j (T20).
If it drifts from the real adapter, every one of those becomes a lie — and a lie is worse
than the skip it replaced, because a skip is visible in the output. So this file tests two
different things:

1. **The contract**, exercised against the fake. Ranking, tenant scoping, dim routing,
   the `False`-on-missing-entity return, index-name validation. These are the RULES, not
   the signatures.
2. **Structural conformance** of both implementations, by comparing method signatures
   against the Protocol. `isinstance(x, VectorStore)` passes on a `runtime_checkable`
   Protocol as soon as the METHOD NAMES exist — an adapter whose `search` took different
   keywords would satisfy it and fail at the call site. QC-2 diffs the two on a live stack;
   this is what holds between those runs.
"""

from __future__ import annotations

import inspect

import pytest

from app.adapters.fake_vector_store import FakeVectorStore
from app.adapters.neo4j_vector_store import Neo4jVectorStore
from app.adapters.pg_vector_store import (
    PgVectorStore,
    entity_table,
    index_name,
    parse_vector_index_name,
    passage_table,
)
from app.db.graph_repos.passages import SUPPORTED_PASSAGE_DIMS
from app.db.graph_repos.vector_indexes import parse_summary_index_name
from app.ports.vector_store import (
    EntityVectorRecord,
    PassageVectorRecord,
    VectorFilter,
    VectorStore,
)

_USER = "user-1"
_OTHER_USER = "user-2"
_PROJECT = "proj-1"


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


# ── the contract ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_results_are_ordered_by_similarity_not_by_insertion():
    """The one thing a vector store is FOR. A fake that returned insertion order would let
    every ranking bug through, so it computes real cosine similarity — and this test would
    catch it if that were ever stubbed out, because the closest match is inserted LAST."""
    store = FakeVectorStore()
    await store.upsert(_passage("far", [0.0, 1.0]))
    await store.upsert(_passage("mid", [0.7, 0.7]))
    await store.upsert(_passage("near", [1.0, 0.0]))

    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=3)
    assert [h.record_id.split(":")[-2] for h in hits] == ["near", "mid", "far"]
    assert hits[0].score > hits[1].score > hits[2].score


@pytest.mark.asyncio
async def test_k_truncates_after_ranking_not_before():
    store = FakeVectorStore()
    await store.upsert(_passage("far", [0.0, 1.0]))
    await store.upsert(_passage("near", [1.0, 0.0]))
    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=1)
    # If k were applied before sorting, the FIRST inserted ("far") would survive instead.
    assert len(hits) == 1 and "near" in hits[0].record_id


@pytest.mark.asyncio
async def test_another_users_vectors_are_never_returned():
    store = FakeVectorStore()
    await store.upsert(_passage("mine", [1.0, 0.0]))
    await store.upsert(_passage("theirs", [1.0, 0.0], user_id=_OTHER_USER))
    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(hits) == 1 and "mine" in hits[0].record_id


@pytest.mark.asyncio
async def test_a_query_does_not_match_a_different_dim_family():
    """`dim` selects the index family in every real backend. A fake that ignored it would
    let a model-change bug pass every test and fail on the first real search."""
    store = FakeVectorStore()
    await store.upsert(_passage("d2", [1.0, 0.0], embedding_dim=2))
    await store.upsert(_passage("d3", [1.0, 0.0, 0.0], embedding_dim=3))
    hits = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(hits) == 1 and "d2" in hits[0].record_id


@pytest.mark.asyncio
async def test_project_filter_and_its_absence_mean_different_things():
    """`project_id=None` is "every project this user owns" — the multi-project context mode
    depends on it — and is NOT the same as filtering on a project."""
    store = FakeVectorStore()
    await store.upsert(_passage("p1", [1.0, 0.0], project_id="proj-1"))
    await store.upsert(_passage("p2", [1.0, 0.0], project_id="proj-2"))

    scoped = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2,
                                k=10, filter=VectorFilter(project_id="proj-1"))
    unscoped = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(scoped) == 1
    assert len(unscoped) == 2


@pytest.mark.asyncio
async def test_drafts_are_excluded_unless_asked_for():
    store = FakeVectorStore()
    await store.upsert(_passage("published", [1.0, 0.0], canon=True))
    await store.upsert(_passage("draft", [1.0, 0.0], canon=False))

    default = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2, k=10)
    assert len(default) == 1 and "published" in default[0].record_id

    with_drafts = await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=2,
                                     k=10, filter=VectorFilter(include_drafts=True))
    assert len(with_drafts) == 2


@pytest.mark.asyncio
async def test_re_embedding_the_same_chunk_replaces_it():
    """Identity is (user, source, chunk). Re-embedding after an edit must REPLACE — a
    fake that appended would hide a duplicate-vector bug and quietly double recall."""
    store = FakeVectorStore()
    await store.upsert(_passage("ch1", [1.0, 0.0], text="before"))
    await store.upsert(_passage("ch1", [0.0, 1.0], text="after"))
    assert store.record_count("passage") == 1
    hits = await store.search(scope="passage", user_id=_USER, embedding=[0.0, 1.0], dim=2, k=10)
    assert hits[0].attributes["text"] == "after"


@pytest.mark.asyncio
async def test_entity_upsert_reports_a_missing_target_rather_than_raising():
    """An entity deleted between embedding and write is normal, not exceptional — the port
    says so, and a backend that raised would turn a routine race into a job failure."""
    store = FakeVectorStore()
    store.register_entities(["e-live"])
    rec = EntityVectorRecord(user_id=_USER, entity_id="e-gone", embedding=[1.0, 0.0],
                             embedding_dim=2, embedding_model="m", embedding_version=1)
    assert await store.upsert(rec) is False
    assert store.record_count("entity") == 0

    live = EntityVectorRecord(user_id=_USER, entity_id="e-live", embedding=[1.0, 0.0],
                              embedding_dim=2, embedding_model="m", embedding_version=1)
    assert await store.upsert(live) is True


@pytest.mark.asyncio
async def test_drop_index_refuses_a_name_it_did_not_mint():
    """Cypher cannot parameterise an index name, so validating it IS the injection
    barrier. A fake that dropped anything would let a test prove the admin prune path safe
    when it is not."""
    store = FakeVectorStore()
    with pytest.raises(ValueError):
        await store.drop_index(name="entity_embeddings_1024")  # a SHARED index, not ours


@pytest.mark.asyncio
async def test_ensure_index_is_idempotent_and_names_match_the_real_scheme():
    store = FakeVectorStore()
    proj, model = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    first = await store.ensure_index(project_id=proj, embedding_model_uuid=model,
                                     embedding_dimension=1024)
    second = await store.ensure_index(project_id=proj, embedding_model_uuid=model,
                                      embedding_dimension=1024)
    assert first == second
    assert set(first) == {"chapter", "part", "book"}
    assert len(await store.list_indexes()) == 3
    # The fake reuses the REAL name builder, so a name it minted must survive the real
    # parser — otherwise the prune-orphans tests would agree with nothing in production.
    from app.db.graph_repos.vector_indexes import parse_summary_index_name
    assert parse_summary_index_name(first["chapter"]) is not None
    await store.drop_index(name=first["chapter"])
    assert len(await store.list_indexes()) == 2


# ── structural conformance ───────────────────────────────────────────────────


@pytest.mark.parametrize("impl", [FakeVectorStore, Neo4jVectorStore, PgVectorStore])
def test_implementations_match_the_port_signatures(impl):
    """`isinstance(x, VectorStore)` passes as soon as the method NAMES exist — a
    `runtime_checkable` Protocol checks nothing else. An adapter whose `search` took
    `top_k` instead of `k` would satisfy it and blow up at the call site, which is exactly
    the drift that makes a fake dangerous."""
    for name in ("search", "upsert", "ensure_index", "drop_index", "list_indexes"):
        port_sig = inspect.signature(getattr(VectorStore, name))
        impl_sig = inspect.signature(getattr(impl, name))
        assert list(impl_sig.parameters) == list(port_sig.parameters), (
            f"{impl.__name__}.{name} parameters {list(impl_sig.parameters)} "
            f"!= port {list(port_sig.parameters)}"
        )
        for pname, pparam in port_sig.parameters.items():
            iparam = impl_sig.parameters[pname]
            assert iparam.kind == pparam.kind, (
                f"{impl.__name__}.{name}({pname}) is {iparam.kind}, port says {pparam.kind} — "
                "a positional/keyword mismatch fails only at the call site"
            )
            assert iparam.default == pparam.default, (
                f"{impl.__name__}.{name}({pname}) defaults to {iparam.default!r}, "
                f"port says {pparam.default!r} — a differing default makes the two "
                "backends behave differently for a caller that omits it"
            )


# ── the Postgres adapter's name grammar (plan T23) ───────────────────────────
#
# No database needed: these are the checks that run BEFORE any SQL, and they are the ones
# that decide whether a shared index can be dropped or a relation name can be injected.


def test_no_name_this_store_mints_looks_project_scoped_to_the_prune_path():
    """The load-bearing safety property of the Postgres index model.

    The prune-orphans admin endpoint decides what to drop by parsing a project id out of an
    index name. A Postgres index here serves EVERY tenant, so if one of these names parsed,
    the endpoint would offer to drop an index the whole install depends on. The names are
    built so it cannot.
    """
    for dim in SUPPORTED_PASSAGE_DIMS:
        for scope in ("passage", "entity"):
            for kind in ("emb", "tenant"):
                name = index_name(scope, dim, kind)
                assert parse_summary_index_name(name) is None, (
                    f"{name} parses as a per-project summary index — the prune endpoint "
                    "would treat a shared index as one project's orphan"
                )
                assert parse_vector_index_name(name) is not None


def test_that_check_is_not_vacuous():
    """Positive control. `parse_summary_index_name` returning None for EVERYTHING would
    make the test above pass while proving nothing, so a real summary name must parse."""
    from app.db.graph_repos.vector_indexes import summary_index_name

    real = summary_index_name("1" * 32, "2" * 32, "chapter")
    assert parse_summary_index_name(real) is not None
    assert parse_vector_index_name(real) is None


@pytest.mark.parametrize("bad_dim", [0, -1, 512, 4096, 1537])
def test_a_dim_outside_the_closed_set_never_reaches_a_relation_name(bad_dim):
    """SQL cannot parameterise a relation name, so the closed dim set IS the injection
    barrier — the same role it already plays for the Cypher property name in passages.py."""
    for build in (passage_table, entity_table):
        with pytest.raises(ValueError, match="unsupported embedding dim"):
            build(bad_dim)


def test_parse_rejects_a_dim_that_is_not_in_the_closed_set():
    """A well-formed name for an unsupported dim must still fail to parse — otherwise
    `drop_index` would accept `passage_vectors_9999_emb` on grammar alone."""
    assert parse_vector_index_name("passage_vectors_9999_emb") is None
    assert parse_vector_index_name("passage_vectors_1536_emb") is not None


@pytest.mark.asyncio
async def test_drop_index_refuses_a_name_it_did_not_mint_before_touching_the_pool():
    """`pool=None` is the point: if the refusal ever moved after the first `acquire()`,
    this test would fail with AttributeError instead of passing, which is how it stays a
    barrier rather than a formality."""
    store = PgVectorStore(pool=None)
    for foreign in ("pg_class_oid_index", "entity_embeddings_1024", "passage_vectors_1536"):
        with pytest.raises(ValueError, match="does not own"):
            await store.drop_index(name=foreign)


@pytest.mark.asyncio
async def test_entity_upsert_refuses_to_guess_when_it_has_no_existence_oracle():
    """The port's False return means "the entity was deleted between embedding and write".
    A vector-only Postgres cannot observe that — the embedding row is the only object and
    an INSERT always succeeds. Returning True would satisfy the signature while dropping
    the guarantee, so it raises instead."""
    store = PgVectorStore(pool=None)
    rec = EntityVectorRecord(user_id=_USER, entity_id="e-1", embedding=[1.0, 0.0],
                             embedding_dim=2, embedding_model="m", embedding_version=1)
    with pytest.raises(NotImplementedError, match="entity_exists"):
        await store.upsert(rec)


@pytest.mark.asyncio
async def test_with_an_oracle_a_missing_entity_is_reported_not_raised():
    async def absent(user_id: str, entity_id: str) -> bool:
        return False

    store = PgVectorStore(pool=None, entity_exists=absent)
    rec = EntityVectorRecord(user_id=_USER, entity_id="e-gone", embedding=[1.0, 0.0],
                             embedding_dim=2, embedding_model="m", embedding_version=1)
    assert await store.upsert(rec) is False


def test_the_signature_check_can_actually_fail():
    """Positive control. A comparison that silently looked at nothing — a typo'd attribute,
    an empty method list — would pass forever and certify drift as conformance."""
    class Drifted:
        async def search(self, *, scope, user_id, embedding, dim, top_k=10, filter=None): ...

    port_sig = inspect.signature(VectorStore.search)
    drift_sig = inspect.signature(Drifted.search)
    assert list(drift_sig.parameters) != list(port_sig.parameters)
