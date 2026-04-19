"""K17.9 — integration tests for `eval.fixture_loader` against live
Neo4j. Skipped when TEST_NEO4J_URI is unset."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients.embedding_client import EmbeddingResult
from app.db.neo4j_repos.passages import find_passages_by_vector
from eval.fixture_loader import BENCHMARK_SOURCE_TYPE, load_golden_set_as_passages
from eval.run_benchmark import GoldenSet


DIM = 1024


def _golden(entity_count: int) -> GoldenSet:
    entities = tuple(
        {"id": f"ent-{i:03d}", "name": f"Entity {i}", "summary": f"Summary {i}"}
        for i in range(1, entity_count + 1)
    )
    return GoldenSet(entities=entities, queries=(), thresholds={})


def _vec(seed: float, *, dim: int = DIM) -> list[float]:
    return [seed + i * 0.0001 for i in range(dim)]


@pytest.mark.asyncio
async def test_loader_writes_tagged_passages_to_neo4j(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:8]}"
    project_id = "p-test"
    client = MagicMock()
    client.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[_vec(0.5)], dimension=DIM, model="bge-m3",
    ))

    try:
        async with neo4j_driver.session() as session:
            count = await load_golden_set_as_passages(
                session, client, _golden(3),
                user_id=user_id, project_id=project_id,
                user_uuid=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                model_source="user_model",
                embedding_model="bge-m3", embedding_dim=DIM,
            )
            assert count == 3

            # Each entity got a :Passage node with source_type=benchmark_entity.
            hits = await find_passages_by_vector(
                session, user_id=user_id, project_id=project_id,
                query_vector=_vec(0.5), dim=DIM,
                embedding_model="bge-m3", limit=10,
            )
            source_ids = {h.passage.source_id for h in hits}
            assert source_ids == {"ent-001", "ent-002", "ent-003"}
            # All tagged with the benchmark source_type.
            assert all(
                h.passage.source_type == BENCHMARK_SOURCE_TYPE for h in hits
            )
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (p:Passage {user_id: $uid}) DETACH DELETE p",
                uid=user_id,
            )


@pytest.mark.asyncio
async def test_loader_is_idempotent(neo4j_driver):
    """Running the loader twice on the same golden set overwrites
    the passages in place — canonical-id hashing keeps the same
    node and ON MATCH SET updates the embedding."""
    user_id = f"u-idem-{uuid.uuid4().hex[:8]}"
    project_id = "p-idem"
    client = MagicMock()
    client.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[_vec(0.5)], dimension=DIM, model="bge-m3",
    ))

    try:
        async with neo4j_driver.session() as session:
            await load_golden_set_as_passages(
                session, client, _golden(2),
                user_id=user_id, project_id=project_id,
                user_uuid=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                model_source="user_model",
                embedding_model="bge-m3", embedding_dim=DIM,
            )
            await load_golden_set_as_passages(
                session, client, _golden(2),
                user_id=user_id, project_id=project_id,
                user_uuid=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                model_source="user_model",
                embedding_model="bge-m3", embedding_dim=DIM,
            )
            # Still only 2 passages — upserts hit the same canonical ids.
            result = await session.run(
                "MATCH (p:Passage {user_id: $uid}) RETURN count(p) AS n",
                uid=user_id,
            )
            record = await result.single()
            assert record["n"] == 2
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (p:Passage {user_id: $uid}) DETACH DELETE p",
                uid=user_id,
            )
