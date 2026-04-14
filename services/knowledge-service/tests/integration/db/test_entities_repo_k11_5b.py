"""K11.5b integration tests — entities repository vector + linking slice.

Covers:
  - find_entities_by_vector (dim routing, archived exclusion,
    two-layer ranking)
  - link_to_glossary (promotion + rename-across-canonical path)
  - get_entity_by_glossary_id (rename-aware lookup)
  - unlink_from_glossary
  - recompute_anchor_score
  - find_gap_candidates

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id and DETACH DELETEs in finally.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.canonical import entity_canonical_id
from app.db.neo4j_repos.entities import (
    SUPPORTED_VECTOR_DIMS,
    archive_entity,
    find_entities_by_vector,
    find_gap_candidates,
    get_entity,
    get_entity_by_glossary_id,
    link_to_glossary,
    merge_entity,
    recompute_anchor_score,
    unlink_from_glossary,
    upsert_glossary_anchor,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e",
                user_id=user_id,
            )


def _stub_vec(dim: int, value: float = 0.1) -> list[float]:
    """Deterministic non-zero vector of the given dim. Same vector
    across calls so cosine similarity = 1.0 against itself."""
    return [value] * dim


# ── find_entities_by_vector ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5b_vector_validates_dim(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        with pytest.raises(ValueError, match="unsupported vector dim"):
            await find_entities_by_vector(
                session,
                user_id=test_user,
                project_id="p-1",
                query_vector=[0.1] * 512,
                dim=512,
            )


@pytest.mark.asyncio
async def test_k11_5b_vector_validates_length_matches_dim(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        with pytest.raises(ValueError, match="length"):
            await find_entities_by_vector(
                session,
                user_id=test_user,
                project_id="p-1",
                query_vector=[0.1] * 100,
                dim=384,
            )


@pytest.mark.asyncio
async def test_k11_5b_vector_validates_limit_positive(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        with pytest.raises(ValueError, match="limit"):
            await find_entities_by_vector(
                session,
                user_id=test_user,
                project_id="p-1",
                query_vector=_stub_vec(384),
                dim=384,
                limit=0,
            )


@pytest.mark.asyncio
async def test_k11_5b_vector_returns_empty_when_no_entities(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        hits = await find_entities_by_vector(
            session,
            user_id=test_user,
            project_id="p-1",
            query_vector=_stub_vec(1024),
            dim=1024,
        )
    assert hits == []


@pytest.mark.asyncio
async def test_k11_5b_vector_finds_anchored_entity(neo4j_driver, test_user):
    """Insert an anchored entity with an embedding, query with the
    same vector, expect it back ranked first with raw_score≈1.0."""
    vec = _stub_vec(1024, value=0.1)
    async with neo4j_driver.session() as session:
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-vec-1",
            name="Phoenix",
            kind="creature",
        )
        # Stamp the embedding directly — K11.5b doesn't write
        # embeddings yet, K17 will.
        await session.run(
            "MATCH (e:Entity {id: $id}) "
            "SET e.embedding_1024 = $vec, e.embedding_model = 'bge-m3'",
            id=anchored.id,
            vec=vec,
        )
        hits = await find_entities_by_vector(
            session,
            user_id=test_user,
            project_id="p-1",
            query_vector=vec,
            dim=1024,
            embedding_model="bge-m3",
        )
    assert len(hits) == 1
    assert hits[0].entity.id == anchored.id
    assert hits[0].raw_score == pytest.approx(1.0, abs=1e-3)
    # weighted = raw * anchor_score (1.0 for anchored)
    assert hits[0].weighted_score == pytest.approx(1.0, abs=1e-3)


@pytest.mark.asyncio
async def test_k11_5b_vector_excludes_archived_by_default(neo4j_driver, test_user):
    vec = _stub_vec(1024, value=0.2)
    async with neo4j_driver.session() as session:
        e = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-arch",
            name="Drake",
            kind="creature",
        )
        await session.run(
            "MATCH (e:Entity {id: $id}) "
            "SET e.embedding_1024 = $vec, e.embedding_model = 'bge-m3'",
            id=e.id,
            vec=vec,
        )
        await archive_entity(
            session,
            user_id=test_user,
            canonical_id=e.id,
            reason="glossary_deleted",
        )
        active = await find_entities_by_vector(
            session,
            user_id=test_user,
            project_id="p-1",
            query_vector=vec,
            dim=1024,
            embedding_model="bge-m3",
        )
        with_archived = await find_entities_by_vector(
            session,
            user_id=test_user,
            project_id="p-1",
            query_vector=vec,
            dim=1024,
            embedding_model="bge-m3",
            include_archived=True,
        )
    assert active == []
    assert len(with_archived) == 1
    # archive sets anchor_score to 0 → weighted_score is 0
    assert with_archived[0].weighted_score == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_k11_5b_vector_two_layer_ranking_anchored_above_discovered(
    neo4j_driver, test_user
):
    """Two entities with very similar embeddings; the anchored one
    must rank above the discovered one even though their raw
    similarities are nearly identical, because weighted_score
    multiplies by anchor_score."""
    vec_anchor = [0.10] * 1024
    vec_discovered = [0.11] * 1024  # slightly different → score < 1
    async with neo4j_driver.session() as session:
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-rank",
            name="Phoenix",
            kind="creature",
        )
        discovered = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Wyrm",  # different canonical so it's a separate node
            kind="creature",
            source_type="book_content",
            confidence=0.9,
        )
        # Discovered gets a slightly DIFFERENT vector and a
        # mid-tier anchor_score=0.5 (set directly here).
        await session.run(
            "MATCH (e:Entity {id: $id}) "
            "SET e.embedding_1024 = $vec, e.embedding_model = 'bge-m3', "
            "    e.anchor_score = 0.5",
            id=discovered.id,
            vec=vec_discovered,
        )
        await session.run(
            "MATCH (e:Entity {id: $id}) "
            "SET e.embedding_1024 = $vec, e.embedding_model = 'bge-m3'",
            id=anchored.id,
            vec=vec_anchor,
        )
        hits = await find_entities_by_vector(
            session,
            user_id=test_user,
            project_id="p-1",
            query_vector=vec_anchor,
            dim=1024,
            embedding_model="bge-m3",
            limit=10,
        )
    assert len(hits) == 2
    # Anchored ranks first because weighted = raw * 1.0 ≈ 1.0
    # Discovered weighted = ~0.999 * 0.5 ≈ 0.5
    assert hits[0].entity.id == anchored.id
    assert hits[1].entity.id == discovered.id
    assert hits[0].weighted_score > hits[1].weighted_score


@pytest.mark.asyncio
async def test_k11_5b_vector_does_not_cross_user_boundary(neo4j_driver):
    vec = _stub_vec(1024, value=0.3)
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            a_entity = await upsert_glossary_anchor(
                session,
                user_id=user_a,
                project_id="p-1",
                glossary_entity_id="gloss-cross",
                name="Sphinx",
                kind="creature",
            )
            await session.run(
                "MATCH (e:Entity {id: $id}) "
                "SET e.embedding_1024 = $vec, e.embedding_model = 'bge-m3'",
                id=a_entity.id,
                vec=vec,
            )
            from_b = await find_entities_by_vector(
                session,
                user_id=user_b,
                project_id="p-1",
                query_vector=vec,
                dim=1024,
                embedding_model="bge-m3",
            )
        assert from_b == []
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity) WHERE e.user_id IN [$ua, $ub] DETACH DELETE e",
                ua=user_a,
                ub=user_b,
            )


def test_k11_5b_supported_vector_dims_matches_schema():
    """K11.5b-R1/R5 drift guard. Parse `neo4j_schema.cypher` for
    every `entity_embeddings_<dim>` index name and assert the
    set equals `SUPPORTED_VECTOR_DIMS`. The schema file is the
    source of truth — if a future schema edit adds dim 768 and
    forgets to update the constant, this test fails loud.
    Previously the test compared two hardcoded sets, which
    defeated the point of having a guard.

    Sync (not async) and Neo4j-free — runs even when
    TEST_NEO4J_URI is unset.
    """
    import re

    from app.db.neo4j_schema import _SCHEMA_PATH

    raw = _SCHEMA_PATH.read_text(encoding="utf-8-sig")
    schema_dims = {
        int(m.group(1))
        for m in re.finditer(r"entity_embeddings_(\d+)", raw)
    }
    assert schema_dims, "no entity_embeddings_<dim> indexes found in schema"
    assert set(SUPPORTED_VECTOR_DIMS) == schema_dims, (
        f"SUPPORTED_VECTOR_DIMS {SUPPORTED_VECTOR_DIMS} does not match "
        f"schema vector indexes {sorted(schema_dims)}"
    )


# ── link_to_glossary / get_entity_by_glossary_id / unlink ────────────


@pytest.mark.asyncio
async def test_k11_5b_link_to_glossary_promotes_discovered_entity(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        discovered = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.7,
        )
        anchored = await link_to_glossary(
            session,
            user_id=test_user,
            canonical_id=discovered.id,
            glossary_entity_id="gloss-promoted-1",
            name="Kai",
            kind="character",
            aliases=["Kai", "Kai-shifu"],
        )
    assert anchored is not None
    assert anchored.id == discovered.id  # node identity preserved
    assert anchored.glossary_entity_id == "gloss-promoted-1"
    assert anchored.anchor_score == 1.0
    assert "Kai-shifu" in anchored.aliases


@pytest.mark.asyncio
async def test_k11_5b_link_to_glossary_handles_rename_across_canonical(
    neo4j_driver, test_user
):
    """K11.5a deferred fix. A glossary edit can rename "Kai" to
    "Phoenix Lord", canonicalizing differently. link_to_glossary
    looks up by canonical_id (the OLD one) and updates name in
    place, preserving the node id even though the new name no
    longer hashes to it. Lookup by glossary_entity_id finds the
    renamed entity."""
    async with neo4j_driver.session() as session:
        discovered = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        renamed = await link_to_glossary(
            session,
            user_id=test_user,
            canonical_id=discovered.id,
            glossary_entity_id="gloss-renamed",
            name="Phoenix Lord",  # canonicalizes to "phoenix lord", not "kai"
            kind="character",
            aliases=["Phoenix Lord"],
        )
        # Same node id, new name + canonical_name.
        assert renamed is not None
        assert renamed.id == discovered.id
        assert renamed.name == "Phoenix Lord"
        assert renamed.canonical_name == "phoenix lord"

        # The new name no longer hashes to the stored id.
        new_id = entity_canonical_id(
            user_id=test_user,
            project_id="p-1",
            name="Phoenix Lord",
            kind="character",
        )
        assert new_id != discovered.id

        # But lookup by glossary FK still finds it.
        looked_up = await get_entity_by_glossary_id(
            session,
            user_id=test_user,
            glossary_entity_id="gloss-renamed",
        )
        assert looked_up is not None
        assert looked_up.id == discovered.id


@pytest.mark.asyncio
async def test_k11_5b_link_to_glossary_returns_none_for_missing(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        result = await link_to_glossary(
            session,
            user_id=test_user,
            canonical_id="0" * 32,
            glossary_entity_id="gloss-missing",
            name="Ghost",
            kind="character",
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_5b_get_by_glossary_id_returns_none_when_missing(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        result = await get_entity_by_glossary_id(
            session,
            user_id=test_user,
            glossary_entity_id="gloss-nope",
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_5b_unlink_clears_link_without_archiving(neo4j_driver, test_user):
    """Single anchored entity, no peers in the project. After
    unlink there are no discovered peers to derive a max from, so
    the inline recompute returns 0.0 — but the entity is NOT
    archived and is still queryable."""
    async with neo4j_driver.session() as session:
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-unlink",
            name="Kai",
            kind="character",
        )
        unlinked = await unlink_from_glossary(
            session,
            user_id=test_user,
            canonical_id=anchored.id,
        )
    assert unlinked is not None
    assert unlinked.glossary_entity_id is None
    assert unlinked.anchor_score == 0.0  # no peers → max is NULL → 0
    # NOT archived — still active.
    assert unlinked.archived_at is None


@pytest.mark.asyncio
async def test_k11_5b_unlink_recomputes_score_inline_from_peers(
    neo4j_driver, test_user
):
    """K11.5b-R1/R3 fix. After unlink, the entity's score must be
    immediately set to its discovered-tier value (mention_count
    over the project's max), NOT 0. This is what makes "unlink"
    mean "lose the boost", not "vanish from search ranking".
    """
    async with neo4j_driver.session() as session:
        # Two discovered peers in the same project: max=200.
        peer_lo = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Alpha",
            kind="character",
            source_type="book_content",
        )
        peer_hi = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Beta",
            kind="character",
            source_type="book_content",
        )
        await session.run(
            "MATCH (e:Entity) WHERE e.id IN [$a, $b] "
            "WITH e, CASE e.id WHEN $a THEN 50 ELSE 200 END AS mc "
            "SET e.mention_count = mc",
            a=peer_lo.id,
            b=peer_hi.id,
        )
        # The anchored entity to unlink — give it mention_count=100.
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-recompute",
            name="Phoenix",
            kind="creature",
        )
        await session.run(
            "MATCH (e:Entity {id: $id}) SET e.mention_count = 100",
            id=anchored.id,
        )
        unlinked = await unlink_from_glossary(
            session,
            user_id=test_user,
            canonical_id=anchored.id,
        )
    assert unlinked is not None
    assert unlinked.glossary_entity_id is None
    # Discovered peers' max = 200; unlinked entity's count = 100.
    # Inline recompute: 100/200 = 0.5.
    assert unlinked.anchor_score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_k11_5b_unlink_returns_none_for_missing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await unlink_from_glossary(
            session,
            user_id=test_user,
            canonical_id="0" * 32,
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_5b_unlink_validates_canonical_id():
    # Fake session not needed — validation happens before any
    # driver interaction.
    with pytest.raises(ValueError, match="canonical_id"):
        await unlink_from_glossary(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            canonical_id="",
        )


@pytest.mark.asyncio
async def test_k11_5b_link_validates_inputs():
    """K11.5b-R1/R4 validation guard. link_to_glossary must reject
    empty inputs before touching the driver — empty strings would
    silently break downstream `IS NULL` checks (a `glossary_entity_id`
    of `""` is NOT NULL in Cypher, so find_gap_candidates would
    treat the entity as anchored even though no real glossary
    entry backs it).
    """
    for kwargs, match in (
        (
            dict(canonical_id="", glossary_entity_id="g", name="N", kind="k"),
            "canonical_id",
        ),
        (
            dict(canonical_id="a" * 32, glossary_entity_id="", name="N", kind="k"),
            "glossary_entity_id",
        ),
        (
            dict(canonical_id="a" * 32, glossary_entity_id="g", name="", kind="k"),
            "name",
        ),
        (
            dict(canonical_id="a" * 32, glossary_entity_id="g", name="N", kind=""),
            "kind",
        ),
        (
            dict(canonical_id="a" * 32, glossary_entity_id="g", name="!!!", kind="k"),
            "canonicalizes to empty",
        ),
    ):
        with pytest.raises(ValueError, match=match):
            await link_to_glossary(
                session=None,  # type: ignore[arg-type]
                user_id="u-1",
                **kwargs,
            )


@pytest.mark.asyncio
async def test_k11_5b_get_by_glossary_id_validates_input():
    with pytest.raises(ValueError, match="glossary_entity_id"):
        await get_entity_by_glossary_id(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            glossary_entity_id="",
        )


@pytest.mark.asyncio
async def test_k11_5b_glossary_id_uniqueness_enforced_by_schema(
    neo4j_driver, test_user
):
    """K11.5b-R1/R1: the schema constraint
    `entity_glossary_id_unique` must reject a second entity
    trying to take an already-claimed glossary FK. Verify by
    creating two entities with different canonical ids and trying
    to link both to the same glossary FK."""
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="EntityA",
            kind="character",
            source_type="book_content",
        )
        b = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="EntityB",
            kind="character",
            source_type="book_content",
        )
        # First link succeeds.
        await link_to_glossary(
            session,
            user_id=test_user,
            canonical_id=a.id,
            glossary_entity_id="gloss-shared",
            name="Shared",
            kind="character",
            aliases=["Shared"],
        )
        # Second link to the SAME FK should be rejected by the
        # uniqueness constraint. Neo4j raises a ConstraintError.
        from neo4j.exceptions import ConstraintError

        with pytest.raises(ConstraintError):
            await link_to_glossary(
                session,
                user_id=test_user,
                canonical_id=b.id,
                glossary_entity_id="gloss-shared",
                name="Shared",
                kind="character",
                aliases=["Shared"],
            )


# ── recompute_anchor_score ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5b_recompute_anchor_score_basic_formula(neo4j_driver, test_user):
    """Three discovered entities with mention_counts 10, 20, 40.
    Max is 40. anchor_scores should be 0.25, 0.5, 1.0."""
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Anya",
            kind="character",
            source_type="book_content",
        )
        b = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Boris",
            kind="character",
            source_type="book_content",
        )
        c = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Chen",
            kind="character",
            source_type="book_content",
        )
        await session.run(
            "MATCH (e:Entity) WHERE e.id IN [$a, $b, $c] "
            "WITH e, CASE e.id WHEN $a THEN 10 WHEN $b THEN 20 ELSE 40 END AS m "
            "SET e.mention_count = m",
            a=a.id,
            b=b.id,
            c=c.id,
        )
        updated, max_mentions = await recompute_anchor_score(
            session,
            user_id=test_user,
            project_id="p-1",
        )
    assert updated == 3
    assert max_mentions == 40
    async with neo4j_driver.session() as session:
        a_after = await get_entity(session, user_id=test_user, canonical_id=a.id)
        b_after = await get_entity(session, user_id=test_user, canonical_id=b.id)
        c_after = await get_entity(session, user_id=test_user, canonical_id=c.id)
    assert a_after.anchor_score == pytest.approx(0.25)
    assert b_after.anchor_score == pytest.approx(0.5)
    assert c_after.anchor_score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_k11_5b_recompute_skips_anchored_entities(neo4j_driver, test_user):
    """Anchored entities (anchor_score=1.0 fixed) must not be
    touched by the recompute pass."""
    async with neo4j_driver.session() as session:
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-skip",
            name="Phoenix",
            kind="creature",
        )
        discovered = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Wyrm",
            kind="creature",
            source_type="book_content",
        )
        await session.run(
            "MATCH (e:Entity {id: $id}) SET e.mention_count = 100",
            id=discovered.id,
        )
        await session.run(
            "MATCH (e:Entity {id: $id}) SET e.mention_count = 5",
            id=anchored.id,
        )
        updated, max_mentions = await recompute_anchor_score(
            session,
            user_id=test_user,
            project_id="p-1",
        )
    assert updated == 1  # only the discovered one
    assert max_mentions == 100
    async with neo4j_driver.session() as session:
        anchored_after = await get_entity(
            session, user_id=test_user, canonical_id=anchored.id
        )
        discovered_after = await get_entity(
            session, user_id=test_user, canonical_id=discovered.id
        )
    assert anchored_after.anchor_score == 1.0  # untouched
    assert discovered_after.anchor_score == 1.0  # 100/100 = 1.0


@pytest.mark.asyncio
async def test_k11_5b_recompute_returns_zero_when_empty(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        updated, max_mentions = await recompute_anchor_score(
            session,
            user_id=test_user,
            project_id="p-1",
        )
    assert updated == 0
    assert max_mentions == 0


@pytest.mark.asyncio
async def test_k11_5b_recompute_handles_all_zero_mentions(neo4j_driver, test_user):
    """Three entities, all with mention_count=0. max=0. The
    formula must return 0.0 (not divide-by-zero)."""
    async with neo4j_driver.session() as session:
        for name in ("X", "Y", "Z"):
            await merge_entity(
                session,
                user_id=test_user,
                project_id="p-1",
                name=name,
                kind="character",
                source_type="book_content",
            )
        updated, max_mentions = await recompute_anchor_score(
            session,
            user_id=test_user,
            project_id="p-1",
        )
    assert updated == 3
    assert max_mentions == 0
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:Entity {user_id: $user_id}) RETURN e.anchor_score AS s",
            user_id=test_user,
        )
        scores = [record["s"] async for record in result]
    assert all(s == 0.0 for s in scores)


# ── find_gap_candidates ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5b_gap_candidates_filter_by_min_mentions(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        low = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="LowMention",
            kind="character",
            source_type="book_content",
        )
        mid = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="MidMention",
            kind="character",
            source_type="book_content",
        )
        high = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="HighMention",
            kind="character",
            source_type="book_content",
        )
        await session.run(
            "MATCH (e:Entity) WHERE e.id IN [$l, $m, $h] "
            "WITH e, CASE e.id WHEN $l THEN 5 WHEN $m THEN 50 ELSE 200 END AS mc "
            "SET e.mention_count = mc",
            l=low.id,
            m=mid.id,
            h=high.id,
        )
        candidates = await find_gap_candidates(
            session,
            user_id=test_user,
            project_id="p-1",
            min_mentions=50,
        )
    # low (5) is excluded; mid (50) and high (200) are included
    assert len(candidates) == 2
    # Sorted by mention_count DESC
    assert candidates[0].name == "HighMention"
    assert candidates[1].name == "MidMention"


@pytest.mark.asyncio
async def test_k11_5b_gap_candidates_excludes_anchored(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-not-gap",
            name="Phoenix",
            kind="creature",
        )
        await session.run(
            "MATCH (e:Entity {id: $id}) SET e.mention_count = 500",
            id=anchored.id,
        )
        candidates = await find_gap_candidates(
            session,
            user_id=test_user,
            project_id="p-1",
            min_mentions=10,
        )
    assert candidates == []  # anchored excluded despite high mention_count


@pytest.mark.asyncio
async def test_k11_5b_gap_candidates_excludes_archived(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        e = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Ghost",
            kind="character",
            source_type="book_content",
        )
        await session.run(
            "MATCH (e:Entity {id: $id}) SET e.mention_count = 100",
            id=e.id,
        )
        await archive_entity(
            session,
            user_id=test_user,
            canonical_id=e.id,
            reason="glossary_deleted",
        )
        candidates = await find_gap_candidates(
            session,
            user_id=test_user,
            project_id="p-1",
            min_mentions=10,
        )
    assert candidates == []


@pytest.mark.asyncio
async def test_k11_5b_gap_candidates_validates_inputs(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        with pytest.raises(ValueError, match="min_mentions"):
            await find_gap_candidates(
                session,
                user_id=test_user,
                project_id="p-1",
                min_mentions=-1,
            )
        with pytest.raises(ValueError, match="limit"):
            await find_gap_candidates(
                session,
                user_id=test_user,
                project_id="p-1",
                limit=0,
            )
