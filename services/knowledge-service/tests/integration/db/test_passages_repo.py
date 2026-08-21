"""K18.3 integration tests — :Passage repository against live Neo4j.

Skipped when `TEST_NEO4J_URI` is unset. Each test cleans up via
DETACH DELETE in a fixture so parallel runs don't collide.

Acceptance criteria (K18.3 + KSA §3.4.B):
  - upsert_passage is idempotent (same chunk → same id → no dup)
  - embedding is written to the matching dim property only
  - find_passages_by_vector respects tenant scope
  - delete_passages_for_source removes only that source's chunks
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.vector_indexes import (
    ensure_passage_vector_index,
    passage_index_name,
)
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    delete_passages_for_source,
    find_passages_by_fulltext,
    find_passages_by_vector,
    passage_canonical_id,
    upsert_passage,
)


DIM = 1024  # bge-m3


def _vec(seed: float, *, dim: int = DIM) -> list[float]:
    """Deterministic unit-ish vector for similarity comparisons."""
    return [seed + i * 0.0001 for i in range(dim)]


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (p:Passage {user_id: $uid}) DETACH DELETE p",
                uid=user_id,
            )


@pytest.mark.asyncio
async def test_upsert_passage_creates_node(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        p = await upsert_passage(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="chap-1",
            chunk_index=0,
            text="Arthur draws Excalibur from the stone.",
            embedding=_vec(0.1),
            embedding_dim=DIM,
            embedding_model="bge-m3",
            chapter_index=1,
        )
    assert p.user_id == test_user
    assert p.project_id == "p-1"
    assert p.source_type == "chapter"
    assert p.source_id == "chap-1"
    assert p.chunk_index == 0
    assert p.text.startswith("Arthur draws")
    assert p.is_hub is False
    assert p.chapter_index == 1
    assert p.id == passage_canonical_id(
        user_id=test_user, project_id="p-1",
        source_type="chapter", source_id="chap-1", chunk_index=0,
    )


@pytest.mark.asyncio
async def test_upsert_passage_is_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        p1 = await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-1", chunk_index=0,
            text="first version", embedding=_vec(0.1), embedding_dim=DIM,
        )
        p2 = await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-1", chunk_index=0,
            text="edited version", embedding=_vec(0.1), embedding_dim=DIM,
        )
    # Same canonical id → update-in-place (not a duplicate row).
    assert p1.id == p2.id
    assert p2.text == "edited version"


@pytest.mark.asyncio
async def test_delete_passages_for_source(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        for i in range(3):
            await upsert_passage(
                session, user_id=test_user, project_id="p-1",
                source_type="chapter", source_id="chap-1", chunk_index=i,
                text=f"chunk {i}", embedding=_vec(0.1 + i * 0.01),
                embedding_dim=DIM,
            )
        # Different source — stays.
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-2", chunk_index=0,
            text="other chapter", embedding=_vec(0.2), embedding_dim=DIM,
        )

        deleted = await delete_passages_for_source(
            session, user_id=test_user,
            source_type="chapter", source_id="chap-1",
        )
    assert deleted == 3


@pytest.mark.asyncio
async def test_delete_passages_for_source_canon_scoping_keeps_both(
    neo4j_driver, test_user
):
    """D-R20 (P-3, keep-both) proven live — the reap's canon scoping is DATA-LOSS
    shaped: the ingester reaps with `canon=False` before writing a draft, and if
    that scoping is wrong the draft index silently DESTROYS the user's published
    passages. K27 (2026-07-24): this had only mock coverage (a unit test asserting
    the kwarg reaches a stubbed cypher), which cannot catch a wrong WHERE clause.

      canon=False → drops ONLY the draft; published + legacy(null) survive
      canon=None  → drops every bucket (the publish / chapter-delete path)

    The legacy node MUST live at the same `source_id` the reap targets. An earlier
    draft of this test parked it under its own source_id, so the "legacy survives"
    assertion passed vacuously — the reap never matched it on `source_id` in the
    first place, and a flipped `coalesce(p.canon, true)` sailed through. Mutation
    testing caught that; keep the legacy chunk inside the blast radius.
    """
    async def _seed():
        async with neo4j_driver.session() as session:
            await upsert_passage(
                session, user_id=test_user, project_id="p-1",
                source_type="chapter", source_id="keep-canon", chunk_index=0,
                text="keep-canon text", embedding=_vec(0.5), embedding_dim=DIM,
            )
            # Draft + published share ONE source_id — the exact keep-both case.
            for canon in (True, False):
                await upsert_passage(
                    session, user_id=test_user, project_id="p-1",
                    source_type="chapter", source_id="keep-both", chunk_index=0,
                    text=f"keep-both canon={canon}", embedding=_vec(0.5),
                    embedding_dim=DIM, canon=canon,
                )
            # A pre-flag (null-canon) chunk of the SAME source — inside the reap's
            # blast radius, so `coalesce(p.canon, true)` is what spares it.
            await upsert_passage(
                session, user_id=test_user, project_id="p-1",
                source_type="chapter", source_id="keep-both", chunk_index=1,
                text="keep-both legacy", embedding=_vec(0.5), embedding_dim=DIM,
            )
            await session.run(
                "MATCH (l:Passage {user_id: $uid, source_id: 'keep-both', chunk_index: 1}) "
                "REMOVE l.canon",
                uid=test_user,
            )

    async def _texts(source_id):
        async with neo4j_driver.session() as session:
            res = await session.run(
                "MATCH (p:Passage {user_id: $uid, source_id: $sid}) RETURN p.text AS t",
                uid=test_user, sid=source_id,
            )
            return {r["t"] async for r in res}

    await _seed()
    async with neo4j_driver.session() as session:
        dropped = await delete_passages_for_source(
            session, user_id=test_user,
            source_type="chapter", source_id="keep-both", canon=False,
        )
    # ONLY the draft bucket goes; the published twin AND the legacy null-canon
    # chunk survive at the very same source — a legacy node coalesces to
    # canon=True, so a canon=False reap must not touch it.
    assert dropped == 1
    assert await _texts("keep-both") == {"keep-both canon=True", "keep-both legacy"}

    # canon=None → both buckets, the publish / chapter-delete path.
    async with neo4j_driver.session() as session:
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="keep-both", chunk_index=0,
            text="keep-both canon=False", embedding=_vec(0.5),
            embedding_dim=DIM, canon=False,
        )
        dropped_all = await delete_passages_for_source(
            session, user_id=test_user,
            source_type="chapter", source_id="keep-both", canon=None,
        )
    assert dropped_all == 3
    assert await _texts("keep-both") == set()
    # Unrelated sources are untouched throughout.
    assert await _texts("keep-canon") == {"keep-canon text"}


@pytest.mark.asyncio
async def test_find_passages_by_vector_respects_tenant(neo4j_driver, test_user, passage_vector_index):
    other_user = f"u-other-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-1", chunk_index=0,
            text="mine", embedding=_vec(0.5), embedding_dim=DIM,
            embedding_model="bge-m3",
        )
        await upsert_passage(
            session, user_id=other_user, project_id="p-1",
            source_type="chapter", source_id="chap-1", chunk_index=0,
            text="not mine", embedding=_vec(0.5), embedding_dim=DIM,
            embedding_model="bge-m3",
        )

        hits = await find_passages_by_vector(
            session, user_id=test_user, project_id="p-1",
            query_vector=_vec(0.5), dim=DIM,
            embedding_model="bge-m3", limit=10,
        )
    texts = [h.passage.text for h in hits]
    assert "mine" in texts
    assert "not mine" not in texts  # tenant isolation

    # Cleanup the second user's node too.
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (p:Passage {user_id: $uid}) DETACH DELETE p",
            uid=other_user,
        )


@pytest.mark.asyncio
async def test_find_passages_by_vector_canon_filter(neo4j_driver, test_user, passage_vector_index):
    """D-RAWSEARCH-CANON-WIRING — the canon gate, proven against live Neo4j:
      - include_drafts=False (default) → canon + legacy(null-canon), NOT drafts
      - include_drafts=True → everything
    A cypher typo (wrong coalesce / = false) would only surface here."""
    async with neo4j_driver.session() as session:
        # Published (canon=True).
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-canon", chunk_index=0,
            text="published canon", embedding=_vec(0.5), embedding_dim=DIM,
            embedding_model="bge-m3", canon=True,
        )
        # Draft (canon=False).
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-draft", chunk_index=0,
            text="unpublished draft", embedding=_vec(0.5), embedding_dim=DIM,
            embedding_model="bge-m3", canon=False,
        )
        # Legacy node with NO canon property (predates the flag) — must read as canon.
        #
        # K27 (2026-07-24): this was originally built by cloning the draft node
        # (`CREATE (l:Passage) SET l = properties(p), l.id = 'legacy-null-canon', …`).
        # That can never work against a real graph: `SET l = properties(p)` copies
        # `p.id` first, which trips the `passage_id_unique` constraint immediately —
        # the later `l.id = …` in the same SET never gets to rescue it. The test
        # shipped with the feature (55b9eba25) and was never executed, so the flaw
        # sat unnoticed. Writing a genuine passage and REMOVEing its `canon` flag
        # models "predates the flag" more honestly anyway: a real node, a real id,
        # simply missing the property.
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-legacy", chunk_index=0,
            text="legacy no-flag", embedding=_vec(0.5), embedding_dim=DIM,
            embedding_model="bge-m3", canon=True,
        )
        await session.run(
            "MATCH (l:Passage {user_id: $uid, source_id: 'chap-legacy'}) REMOVE l.canon",
            uid=test_user,
        )

        canon_only = await find_passages_by_vector(
            session, user_id=test_user, project_id="p-1",
            query_vector=_vec(0.5), dim=DIM, embedding_model="bge-m3", limit=10,
        )
        all_surfaces = await find_passages_by_vector(
            session, user_id=test_user, project_id="p-1",
            query_vector=_vec(0.5), dim=DIM, embedding_model="bge-m3", limit=10,
            include_drafts=True,
        )
    canon_texts = {h.passage.text for h in canon_only}
    all_texts = {h.passage.text for h in all_surfaces}
    # default canon gate: published + legacy(null), NOT the draft.
    assert "published canon" in canon_texts
    assert "legacy no-flag" in canon_texts
    assert "unpublished draft" not in canon_texts
    # include_drafts → the draft also appears.
    assert "unpublished draft" in all_texts
    # canon flag round-trips onto the projection.
    assert all(h.passage.canon for h in canon_only)


@pytest.mark.asyncio
async def test_find_passages_by_fulltext_canon_filter(neo4j_driver, test_user):
    """K27 (2026-07-24) — the SAME canon gate lives in `find_passages_by_fulltext`
    (`$include_drafts OR coalesce(node.canon, true) = true`), but until now it had
    only MOCK wiring coverage: a unit test asserts the kwarg is forwarded, which a
    wrong `coalesce` default would sail straight through. The vector twin above is
    live-proven; this closes the gap on its sibling so a typo in either surfaces.

    Same three fixtures as the vector case: published / draft / legacy(no flag).
    """
    async with neo4j_driver.session() as session:
        for source_id, text, canon in (
            ("ft-canon", "zenith published canon", True),
            ("ft-draft", "zenith unpublished draft", False),
            ("ft-legacy", "zenith legacy no-flag", True),
        ):
            await upsert_passage(
                session, user_id=test_user, project_id="p-1",
                source_type="chapter", source_id=source_id, chunk_index=0,
                text=text, embedding=_vec(0.5), embedding_dim=DIM,
                embedding_model="bge-m3", canon=canon,
            )
        # Strip the flag from the legacy node — it must still read as canon.
        await session.run(
            "MATCH (l:Passage {user_id: $uid, source_id: 'ft-legacy'}) REMOVE l.canon",
            uid=test_user,
        )

        canon_only = await find_passages_by_fulltext(
            session, user_id=test_user, project_id="p-1", query="zenith", limit=10,
        )
        all_surfaces = await find_passages_by_fulltext(
            session, user_id=test_user, project_id="p-1", query="zenith", limit=10,
            include_drafts=True,
        )

    canon_texts = {h.passage.text for h in canon_only}
    all_texts = {h.passage.text for h in all_surfaces}
    # The query must actually match, else the assertions below pass vacuously.
    assert canon_texts, "fulltext returned nothing — the CJK index or query is broken"
    assert "zenith published canon" in canon_texts
    assert "zenith legacy no-flag" in canon_texts       # coalesce(canon, true)
    assert "zenith unpublished draft" not in canon_texts
    assert "zenith unpublished draft" in all_texts      # include_drafts opens the gate


@pytest.mark.asyncio
async def test_find_passages_by_vector_default_omits_vector(
    neo4j_driver, test_user, passage_vector_index,
):
    """P-K18.3-02: default call (include_vectors=False) keeps the
    existing projection — vector stays None so callers that don't
    opt in don't pay the list[float] transport cost."""
    async with neo4j_driver.session() as session:
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-1", chunk_index=0,
            text="default path", embedding=_vec(0.5), embedding_dim=DIM,
            embedding_model="bge-m3",
        )
        hits = await find_passages_by_vector(
            session, user_id=test_user, project_id="p-1",
            query_vector=_vec(0.5), dim=DIM,
            embedding_model="bge-m3", limit=5,
        )
    assert hits, "expected at least one hit"
    assert all(h.vector is None for h in hits)


@pytest.mark.asyncio
async def test_find_passages_by_vector_include_vectors_projects_embedding(
    neo4j_driver, test_user, passage_vector_index,
):
    """P-K18.3-02: include_vectors=True projects the stored embedding
    onto PassageSearchHit.vector so MMR can use real cosine distance."""
    stored = _vec(0.5)
    async with neo4j_driver.session() as session:
        await upsert_passage(
            session, user_id=test_user, project_id="p-1",
            source_type="chapter", source_id="chap-1", chunk_index=0,
            text="with vector", embedding=stored, embedding_dim=DIM,
            embedding_model="bge-m3",
        )
        hits = await find_passages_by_vector(
            session, user_id=test_user, project_id="p-1",
            query_vector=stored, dim=DIM,
            embedding_model="bge-m3", limit=5,
            include_vectors=True,
        )
    assert hits, "expected at least one hit"
    hit = next(h for h in hits if h.passage.text == "with vector")
    assert hit.vector is not None
    assert len(hit.vector) == DIM
    # Neo4j round-trip should preserve float values to machine precision.
    assert hit.vector[0] == pytest.approx(stored[0], abs=1e-6)
    assert hit.vector[-1] == pytest.approx(stored[-1], abs=1e-6)


@pytest.mark.asyncio
async def test_find_passages_by_vector_bad_dim_raises(passage_vector_index):
    # No session needed — raises at arg-validation before the query.
    from unittest.mock import MagicMock
    with pytest.raises(ValueError, match="unsupported vector dim"):
        await find_passages_by_vector(
            MagicMock(),
            user_id="u", project_id="p",
            query_vector=[0.1] * 100, dim=100,
        )


def test_supported_dims_match_schema_indexes():
    """Every supported dim must have an index SOMETHING can create.

    ⚠️ INVERTED 2026-08-22 (T65). It used to require a `CREATE VECTOR INDEX` line in
    `neo4j_schema.cypher`; T25 ③ deleted those, because §3.3 moved passage vectors to
    Postgres and no production reader is left. The drift it guards against is real and did
    not go away — it moved: `ensure_passage_vector_index` is now the only definition of
    these names, so THAT is what must cover every dim the repo claims to support.
    """
    for dim in SUPPORTED_PASSAGE_DIMS:
        assert passage_index_name(dim) == f"passage_embeddings_{dim}", (
            f"dim {dim} does not map to the index name the readers query"
        )
    # The dimension GUARD lives on `ensure_passage_vector_index`, not on the name helper —
    # `passage_index_name` is pure string-building. Its refusal is pinned in
    # tests/unit/test_passage_vector_index.py, which runs without a database; asserting it
    # here too would be a second reader of one rule.
