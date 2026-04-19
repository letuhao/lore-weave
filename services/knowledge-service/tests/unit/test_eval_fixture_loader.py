"""K17.9 — unit tests for `eval.fixture_loader.load_golden_set_as_passages`.

Verifies the loader calls `embedding_client.embed` + `upsert_passage`
once per entity with the right tags. Does NOT touch Neo4j or a real
provider — those are exercised by the integration test.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from eval.fixture_loader import BENCHMARK_SOURCE_TYPE, load_golden_set_as_passages
from eval.run_benchmark import GoldenSet


USER_ID = "user-1"
USER_UUID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = "project-1"


def _golden(entity_count: int = 3) -> GoldenSet:
    entities = tuple(
        {"id": f"ent-{i:03d}", "name": f"Entity {i}", "summary": f"Summary {i}"}
        for i in range(1, entity_count + 1)
    )
    return GoldenSet(entities=entities, queries=(), thresholds={})


def _embed_result(dim: int = 1024) -> EmbeddingResult:
    return EmbeddingResult(
        embeddings=[[0.1] * dim], dimension=dim, model="bge-m3",
    )


@pytest.mark.asyncio
async def test_loader_upserts_one_passage_per_entity(monkeypatch):
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    upsert = AsyncMock()
    monkeypatch.setattr("eval.fixture_loader.upsert_passage", upsert)

    count = await load_golden_set_as_passages(
        MagicMock(), client, _golden(3),
        user_id=USER_ID, project_id=PROJECT_ID,
        user_uuid=USER_UUID, model_source="user_model",
        embedding_model="bge-m3", embedding_dim=1024,
    )

    assert count == 3
    assert upsert.await_count == 3
    # First call's kwargs — the rest follow the same shape.
    kwargs = upsert.await_args_list[0].kwargs
    assert kwargs["source_type"] == BENCHMARK_SOURCE_TYPE
    assert kwargs["source_id"] == "ent-001"
    # Review-impl HIGH fix: indexed text must carry the name so
    # easy-band queries ("Who is Entity 1?") can match.
    assert kwargs["text"] == "Entity 1. Summary 1"
    assert kwargs["is_hub"] is False
    assert kwargs["chapter_index"] is None
    assert kwargs["embedding_model"] == "bge-m3"
    assert kwargs["embedding_dim"] == 1024


@pytest.mark.asyncio
async def test_loader_indexed_text_includes_name_and_summary(monkeypatch):
    """Review-impl HIGH: verify the name is embedded into the indexed
    text so proper-noun queries can hit the passage. A regression that
    went back to summary-only would pass the shape tests above but
    fail this one."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    upsert = AsyncMock()
    monkeypatch.setattr("eval.fixture_loader.upsert_passage", upsert)

    one_entity = GoldenSet(
        entities=(
            {"id": "ent-001", "name": "Kaelen Voss",
             "summary": "Exiled swordmaster of the northern duchy."},
        ),
        queries=(), thresholds={},
    )
    await load_golden_set_as_passages(
        MagicMock(), client, one_entity,
        user_id=USER_ID, project_id=PROJECT_ID,
        user_uuid=USER_UUID, model_source="user_model",
        embedding_model="bge-m3", embedding_dim=1024,
    )

    text = upsert.await_args.kwargs["text"]
    assert "Kaelen Voss" in text
    assert "Exiled swordmaster of the northern duchy." in text
    # The same text got sent to the embedder — not some transformed
    # version that diverges from what ends up in the node.
    embed_text = client.embed.await_args.kwargs["texts"][0]
    assert embed_text == text


def test_build_indexed_text_fallback_to_single_field():
    """When one field is blank, the non-blank one stands alone."""
    from eval.fixture_loader import _build_indexed_text
    assert _build_indexed_text("Alice", "") == "Alice"
    assert _build_indexed_text("", "Tale of Alice.") == "Tale of Alice."
    assert _build_indexed_text("", "") == ""
    # Edge case: summary already starts with the name → don't double.
    assert _build_indexed_text("Alice", "Alice is a swordsman.") == "Alice is a swordsman."


@pytest.mark.asyncio
async def test_loader_skips_entity_on_embedding_error(monkeypatch):
    """One transient embedding failure shouldn't abort the whole load
    — the harness will catch low coverage at score time."""
    client = MagicMock()
    client.embed = AsyncMock(side_effect=[
        _embed_result(),  # ent-001 ok
        EmbeddingError("provider down", retryable=True),  # ent-002 fails
        _embed_result(),  # ent-003 ok
    ])
    upsert = AsyncMock()
    monkeypatch.setattr("eval.fixture_loader.upsert_passage", upsert)

    count = await load_golden_set_as_passages(
        MagicMock(), client, _golden(3),
        user_id=USER_ID, project_id=PROJECT_ID,
        user_uuid=USER_UUID, model_source="user_model",
        embedding_model="bge-m3", embedding_dim=1024,
    )

    assert count == 2  # 2 out of 3 succeeded
    upserted_ids = {c.kwargs["source_id"] for c in upsert.await_args_list}
    assert upserted_ids == {"ent-001", "ent-003"}


@pytest.mark.asyncio
async def test_loader_skips_entity_with_no_indexable_text(monkeypatch):
    """Both name and summary blank → skip. Entities with just a name
    (no summary) still index, since the name alone is useful for
    exact-name queries."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    upsert = AsyncMock()
    monkeypatch.setattr("eval.fixture_loader.upsert_passage", upsert)

    golden = GoldenSet(
        entities=(
            {"id": "ent-001", "name": "ok", "summary": "Valid."},
            {"id": "ent-002", "name": "", "summary": "   "},       # both blank → skip
            {"id": "ent-003", "name": "", "summary": ""},          # both blank → skip
            {"id": "ent-004", "name": "NameOnly", "summary": ""},  # name alone → embedded
        ),
        queries=(), thresholds={},
    )
    count = await load_golden_set_as_passages(
        MagicMock(), client, golden,
        user_id=USER_ID, project_id=PROJECT_ID,
        user_uuid=USER_UUID, model_source="user_model",
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert count == 2  # ent-001 and ent-004
    # Two embed calls (skipped entities didn't hit the embedder).
    assert client.embed.await_count == 2


@pytest.mark.asyncio
async def test_loader_skips_entity_on_empty_embeddings_response(monkeypatch):
    """Provider returned empty list despite no error — skip."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[], dimension=1024, model="bge-m3",
    ))
    upsert = AsyncMock()
    monkeypatch.setattr("eval.fixture_loader.upsert_passage", upsert)

    count = await load_golden_set_as_passages(
        MagicMock(), client, _golden(2),
        user_id=USER_ID, project_id=PROJECT_ID,
        user_uuid=USER_UUID, model_source="user_model",
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert count == 0
    upsert.assert_not_called()
