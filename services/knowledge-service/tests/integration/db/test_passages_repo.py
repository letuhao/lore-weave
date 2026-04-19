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

from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    delete_passages_for_source,
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
async def test_find_passages_by_vector_respects_tenant(neo4j_driver, test_user):
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
async def test_find_passages_by_vector_default_omits_vector(
    neo4j_driver, test_user,
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
    neo4j_driver, test_user,
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
async def test_find_passages_by_vector_bad_dim_raises():
    # No session needed — raises at arg-validation before the query.
    from unittest.mock import MagicMock
    with pytest.raises(ValueError, match="unsupported vector dim"):
        await find_passages_by_vector(
            MagicMock(),
            user_id="u", project_id="p",
            query_vector=[0.1] * 100, dim=100,
        )


def test_supported_dims_match_schema_indexes():
    """Sanity: the dims the repo claims to support must each have a
    CREATE VECTOR INDEX line in the Cypher schema. Caught drift once
    during K11.5b; kept as a guard."""
    import pathlib
    schema = pathlib.Path("app/db/neo4j_schema.cypher").read_text(
        encoding="utf-8"
    )
    for dim in SUPPORTED_PASSAGE_DIMS:
        assert f"passage_embeddings_{dim}" in schema, (
            f"dim {dim} missing CREATE VECTOR INDEX in neo4j_schema.cypher"
        )
