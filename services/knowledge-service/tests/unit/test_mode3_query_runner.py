"""K17.9 — unit tests for `eval.mode3_query_runner.Mode3QueryRunner`.

Everything is mocked — embedding_client.embed and
find_passages_by_vector. The runner is a pure adapter: query →
vector → passages → `ScoredResult` list. These tests prove it
does that adaptation correctly without touching Neo4j or a real
provider.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.clients.embedding_client import EmbeddingResult
from app.db.neo4j_repos.passages import Passage, PassageSearchHit
from eval.mode3_query_runner import Mode3QueryRunner


USER_ID = "user-1"
USER_UUID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = "project-1"


def _hit(entity_id: str, score: float) -> PassageSearchHit:
    return PassageSearchHit(
        passage=Passage(
            id=f"p-{entity_id}",
            user_id=USER_ID,
            project_id=PROJECT_ID,
            source_type="benchmark_entity",
            source_id=entity_id,
            chunk_index=0,
            text=f"summary of {entity_id}",
            embedding_model="bge-m3",
            is_hub=False,
            chapter_index=None,
        ),
        raw_score=score,
    )


def _embed_result(dim: int = 1024) -> EmbeddingResult:
    return EmbeddingResult(
        embeddings=[[0.1] * dim], dimension=dim, model="bge-m3",
    )


def _runner(monkeypatch, find_hits: AsyncMock, *, dim: int = 1024) -> Mode3QueryRunner:
    monkeypatch.setattr(
        "eval.mode3_query_runner.find_passages_by_vector", find_hits,
    )
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result(dim))
    return Mode3QueryRunner(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        user_uuid=USER_UUID, model_source="user_model",
        embedding_model="bge-m3", embedding_dim=dim,
    )


@pytest.mark.asyncio
async def test_run_maps_passages_to_scored_results(monkeypatch):
    find_hits = AsyncMock(return_value=[
        _hit("ent-001", 0.92),
        _hit("ent-002", 0.78),
        _hit("ent-005", 0.65),
    ])
    runner = _runner(monkeypatch, find_hits)

    results = list(await runner.run("who is Kaelen Voss?"))

    assert [(r.entity_id, r.score) for r in results] == [
        ("ent-001", 0.92),
        ("ent-002", 0.78),
        ("ent-005", 0.65),
    ]


@pytest.mark.asyncio
async def test_run_passes_embedding_model_to_search(monkeypatch):
    find_hits = AsyncMock(return_value=[])
    runner = _runner(monkeypatch, find_hits)

    await runner.run("anything")

    kwargs = find_hits.call_args.kwargs
    assert kwargs["embedding_model"] == "bge-m3"
    assert kwargs["dim"] == 1024
    assert kwargs["user_id"] == USER_ID
    assert kwargs["project_id"] == PROJECT_ID


@pytest.mark.asyncio
async def test_run_returns_empty_on_empty_embedding(monkeypatch):
    """Provider returned an empty list — don't invoke search."""
    find_hits = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "eval.mode3_query_runner.find_passages_by_vector", find_hits,
    )
    client = MagicMock()
    client.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[], dimension=1024, model="bge-m3",
    ))
    runner = Mode3QueryRunner(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        user_uuid=USER_UUID, model_source="user_model",
        embedding_model="bge-m3", embedding_dim=1024,
    )
    results = list(await runner.run("anything"))
    assert results == []
    find_hits.assert_not_called()


def test_construct_rejects_unsupported_dim():
    with pytest.raises(ValueError, match="not in"):
        Mode3QueryRunner(
            MagicMock(), MagicMock(),
            user_id=USER_ID, project_id=PROJECT_ID,
            user_uuid=USER_UUID, model_source="user_model",
            embedding_model="nomic-embed-text", embedding_dim=768,
        )


@pytest.mark.asyncio
async def test_run_limit_generous_enough_for_mrr_tail(monkeypatch):
    """Default limit=10 gives MRR a chance to catch hits at rank 4+,
    even though `recall_at_3` only looks at the top-3. Hard-coded
    limits caused ContextHub's benchmarks to under-report MRR when
    the expected target sat at rank 5."""
    find_hits = AsyncMock(return_value=[])
    runner = _runner(monkeypatch, find_hits)
    await runner.run("anything")
    assert find_hits.call_args.kwargs["limit"] == 10
