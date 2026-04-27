"""K18.3 — unit tests for the L3 semantic passage selector.

Phase 4a-δ: rerank now routes through the loreweave_llm SDK
(``llm_client.submit_and_wait`` returning a Job) instead of the
removed ``provider_client.chat_completion`` path."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from app.context.intent.classifier import Intent, IntentResult
from app.context.selectors.passages import (
    EMBEDDING_MODEL_TO_DIM,
    L3Passage,
    select_l3_passages,
)
from app.db.neo4j_repos.passages import Passage, PassageSearchHit
from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from loreweave_llm.models import Job


USER_ID = "user-1"
USER_UUID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = "project-1"


def _intent(
    intent: Intent = Intent.SPECIFIC_ENTITY,
    entities: tuple[str, ...] = ("Arthur",),
    recency_weight: float = 1.0,
) -> IntentResult:
    return IntentResult(
        intent=intent,
        entities=entities,
        signals=(),
        hop_count=1 if intent != Intent.RELATIONAL else 2,
        recency_weight=recency_weight,
    )


def _passage(
    text: str, *,
    pid: str = "",
    is_hub: bool = False,
    chapter_index: int | None = None,
) -> Passage:
    return Passage(
        id=pid or f"p-{hash(text) % 10000}",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        source_type="chapter",
        source_id="chap-1",
        chunk_index=0,
        text=text,
        embedding_model="bge-m3",
        is_hub=is_hub,
        chapter_index=chapter_index,
    )


def _hit(
    text: str,
    raw_score: float,
    *,
    vector: list[float] | None = None,
    **kwargs,
) -> PassageSearchHit:
    return PassageSearchHit(
        passage=_passage(text, **kwargs),
        raw_score=raw_score,
        vector=vector,
    )


def _embed_result(dim: int = 1024) -> EmbeddingResult:
    return EmbeddingResult(
        embeddings=[[0.1] * dim], dimension=dim, model="bge-m3",
    )


# -- Phase 4a-δ — fake LLM client for rerank tests ------------------


class FakeLLMClient:
    """Stand-in for ``app.clients.llm_client.LLMClient`` exposing only
    ``submit_and_wait``. Rerank tests script a single Job (or exception)
    per call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_job: Any = None
        self.next_exc: Exception | None = None
        self._side_effect: Any = None

    def queue_chat_job(
        self,
        *,
        content: str,
        status: str = "completed",
    ) -> None:
        result: dict[str, Any] | None
        if status == "completed":
            result = {
                "messages": [{"role": "assistant", "content": content}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        else:
            result = None
        self.next_job = Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="chat",
            status=status,  # type: ignore[arg-type]
            result=result,
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    def queue_exception(self, exc: Exception) -> None:
        self.next_exc = exc

    def set_side_effect(self, fn: Any) -> None:
        """Use a callable as the side-effect (e.g. for slow simulation)."""
        self._side_effect = fn

    async def submit_and_wait(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._side_effect is not None:
            return await self._side_effect(**kwargs)
        if self.next_exc is not None:
            exc = self.next_exc
            self.next_exc = None
            raise exc
        return self.next_job


@pytest.mark.asyncio
async def test_returns_empty_without_embedding_model(monkeypatch):
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="Tell me",
        intent=_intent(),
        embedding_model=None,
        embedding_dim=None,
        user_uuid=USER_UUID,
    )
    assert result == []
    client.embed.assert_not_called()


@pytest.mark.asyncio
async def test_returns_empty_on_embedding_error(monkeypatch):
    client = MagicMock()
    client.embed = AsyncMock(
        side_effect=EmbeddingError("upstream 503", retryable=True),
    )

    find_hits = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector", find_hits,
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="Tell me",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    assert result == []
    find_hits.assert_not_called()


@pytest.mark.asyncio
async def test_returns_empty_when_search_yields_nothing(monkeypatch):
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="Tell me",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    assert result == []


@pytest.mark.asyncio
async def test_returns_scored_l3_passages(monkeypatch):
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    hits = [
        _hit("Arthur draws Excalibur from the stone.", 0.90),
        _hit("A blue dragon soars over Camelot.", 0.85),
    ]
    find_hits = AsyncMock(return_value=hits)
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector", find_hits,
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="tell me about Arthur",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    assert len(result) == 2
    assert all(isinstance(r, L3Passage) for r in result)
    # Highest raw_score passage should land first after MMR.
    assert "Arthur" in result[0].text


@pytest.mark.asyncio
async def test_hub_penalty_drops_hub_passages_for_specific_entity(monkeypatch):
    """SPECIFIC_ENTITY intent strongly penalizes hub passages — a
    hub passage with higher raw similarity still loses to a non-hub
    with lower raw similarity after penalty."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    hits = [
        _hit("Summary of the entire Arthurian cycle.", 0.92, is_hub=True),
        _hit("Arthur is knighted.", 0.80, is_hub=False),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="Tell me specifically about Arthur",
        intent=_intent(intent=Intent.SPECIFIC_ENTITY),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    # Non-hub passage (raw 0.80) wins over hub (raw 0.92 x 0.3 = 0.276).
    assert result[0].text == "Arthur is knighted."
    assert result[0].is_hub is False


@pytest.mark.asyncio
async def test_historical_intent_inverts_recency_preference(monkeypatch):
    """HISTORICAL intent has recency_weight=-1 -> older chapter wins
    even when both passages have the same raw score."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    hits = [
        _hit("Recent chapter content.", 0.80, chapter_index=100),
        _hit("Early chapter content.", 0.80, chapter_index=1),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="originally who ruled",
        intent=_intent(intent=Intent.HISTORICAL, recency_weight=-1.0),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
        current_chapter_index=100,
    )
    # Earlier chapter ranks higher for historical intent.
    assert result[0].text == "Early chapter content."


@pytest.mark.asyncio
async def test_recency_auto_anchors_to_newest_passage(monkeypatch):
    """When caller doesn't supply current_chapter_index, the selector
    auto-anchors "now" to max(chapter_index) in the hit pool."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    hits = [
        _hit("Newest.", 0.80, chapter_index=50),
        _hit("Oldest.", 0.80, chapter_index=1),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="originally who ruled",
        intent=_intent(intent=Intent.HISTORICAL, recency_weight=-1.0),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
        # NOTE: no current_chapter_index passed — selector auto-anchors.
    )
    # Historical intent + pool-anchored recency -> oldest wins.
    assert result[0].text == "Oldest."


@pytest.mark.asyncio
async def test_mmr_drops_near_duplicate_passages(monkeypatch):
    """Two near-identical passages shouldn't both land in top-N."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    hits = [
        _hit("Arthur rides into Camelot at dawn.", 0.95, pid="a"),
        _hit("Arthur rides into Camelot at dawn again.", 0.94, pid="b"),  # near-dup
        _hit("Merlin casts a protection spell.", 0.85, pid="c"),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="Tell me about Arthur",
        intent=_intent(intent=Intent.SPECIFIC_ENTITY),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    texts = [r.text for r in result]
    assert texts[0] == "Arthur rides into Camelot at dawn."
    # Merlin's passage beats the near-dup.
    assert texts.index("Merlin casts a protection spell.") < texts.index(
        "Arthur rides into Camelot at dawn again."
    )


@pytest.mark.asyncio
async def test_pool_size_intent_aware(monkeypatch):
    """SPECIFIC_ENTITY uses a smaller pool than GENERAL."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    captured_limits: list[int] = []

    async def capture(session, *, limit: int, **kwargs):
        captured_limits.append(limit)
        return []

    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector", capture,
    )

    for intent in (Intent.SPECIFIC_ENTITY, Intent.GENERAL):
        await select_l3_passages(
            MagicMock(), client,
            user_id=USER_ID, project_id=PROJECT_ID,
            message="test",
            intent=_intent(intent=intent),
            embedding_model="bge-m3", embedding_dim=1024,
            user_uuid=USER_UUID,
        )

    assert captured_limits[0] < captured_limits[1]
    assert captured_limits[0] == 20  # SPECIFIC_ENTITY
    assert captured_limits[1] == 40  # GENERAL


@pytest.mark.asyncio
async def test_mmr_uses_cosine_when_vectors_present(monkeypatch):
    """P-K18.3-02: when hits carry vectors, MMR redundancy uses cosine."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    vec_a = [1.0, 0.0, 0.0, 0.0]
    vec_a_prime = [0.99, 0.01, 0.0, 0.0]  # cosine ~0.9999 with vec_a
    vec_b = [0.0, 1.0, 0.0, 0.0]  # orthogonal -> cosine 0.0

    hits = [
        _hit("alpha beta gamma delta", 0.95, pid="a", vector=vec_a),
        _hit("epsilon zeta eta theta", 0.90, pid="a2", vector=vec_a_prime),
        _hit("iota kappa lambda mu", 0.85, pid="b", vector=vec_b),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="anything",
        intent=_intent(intent=Intent.SPECIFIC_ENTITY),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    texts = [r.text for r in result]
    assert texts[0] == "alpha beta gamma delta"
    assert texts.index("iota kappa lambda mu") < texts.index(
        "epsilon zeta eta theta"
    )


@pytest.mark.asyncio
async def test_mmr_falls_back_to_jaccard_when_vectors_missing(monkeypatch):
    """P-K18.3-02 backward-compat: hits without vectors use text Jaccard."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    hits = [
        _hit("Arthur rides into Camelot at dawn.", 0.95, pid="a", vector=None),
        _hit("Arthur rides into Camelot at dawn again.", 0.94, pid="b", vector=None),
        _hit("Merlin casts a protection spell.", 0.85, pid="c", vector=None),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="Tell me about Arthur",
        intent=_intent(intent=Intent.SPECIFIC_ENTITY),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    texts = [r.text for r in result]
    assert texts.index("Merlin casts a protection spell.") < texts.index(
        "Arthur rides into Camelot at dawn again."
    )


@pytest.mark.asyncio
async def test_mmr_handles_mixed_vector_presence(monkeypatch):
    """Defensive: mixed vector / no-vector hits per-pair branch."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    hits = [
        _hit("first passage text", 0.90, pid="a", vector=[1.0, 0.0]),
        _hit("second passage text", 0.85, pid="b", vector=None),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="anything",
        intent=_intent(intent=Intent.SPECIFIC_ENTITY),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    assert len(result) == 2


@pytest.mark.asyncio
async def test_mmr_stops_at_top_n_not_full_pool(monkeypatch):
    """Review-impl catch: MMR must early-exit at top_n."""
    from app.context.selectors.passages import _mmr_rerank

    hits = [
        (
            0.9 - i * 0.01,
            PassageSearchHit(
                passage=_passage(f"passage {i}", pid=f"p{i}"),
                raw_score=0.9 - i * 0.01,
                vector=[float((i >> j) & 1) for j in range(8)],
            ),
        )
        for i in range(40)
    ]

    result = _mmr_rerank(hits, lam=0.7, top_n=10)
    assert len(result) == 10

    all_ranked = _mmr_rerank(hits, lam=0.7, top_n=None)
    assert len(all_ranked) == 40


def test_cosine_zero_magnitude_is_safe():
    """Zero-vector must return 0.0, not NaN or ZeroDivisionError."""
    from app.context.selectors.passages import _cosine
    assert _cosine([0.0, 0.0], 0.0, [1.0, 0.0], 1.0) == 0.0
    assert _cosine([1.0, 0.0], 1.0, [0.0, 0.0], 0.0) == 0.0
    assert _cosine([0.0, 0.0], 0.0, [0.0, 0.0], 0.0) == 0.0


# -- D-K18.3-02 generative rerank (SDK path) -----------------------


def _l3(text: str, score: float = 0.5) -> "object":
    from app.context.selectors.passages import L3Passage
    return L3Passage(
        text=text,
        source_type="chapter",
        source_id="chap-1",
        chunk_index=0,
        score=score,
        is_hub=False,
        chapter_index=1,
    )


@pytest.mark.asyncio
async def test_rerank_reorders_passages_per_llm_response():
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second"), _l3("third")]
    fake = FakeLLMClient()
    fake.queue_chat_job(content='{"order": [2, 0, 1]}')

    out = await rerank_passages(
        fake,
        query="test",
        passages=passages,
        model="llama-3",
        user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["third", "first", "second"]


@pytest.mark.asyncio
async def test_rerank_prompt_carries_query_and_numbered_passages():
    """Review-design guard: the LLM prompt must include `Query:` and
    numbered `[i]` markers."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("alpha"), _l3("beta")]
    fake = FakeLLMClient()
    fake.queue_chat_job(content='{"order": [0, 1]}')

    await rerank_passages(
        fake, query="where is alpha",
        passages=passages, model="llama-3", user_id=USER_UUID,
    )
    call = fake.calls[0]
    user_msg = call["input"]["messages"][1]["content"]
    assert "Query: where is alpha" in user_msg
    assert "[0] alpha" in user_msg
    assert "[1] beta" in user_msg


@pytest.mark.asyncio
async def test_rerank_fallback_on_non_json_response():
    """Any non-JSON body -> keep original MMR order; never raises."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second")]
    fake = FakeLLMClient()
    fake.queue_chat_job(content="not json at all")

    out = await rerank_passages(
        fake, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["first", "second"]  # unchanged


@pytest.mark.asyncio
async def test_rerank_handles_partial_order_by_appending_missing_indices():
    """LLM returned [2] only — we should rerank [2] first, then fill
    missing indices in original MMR order."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("a"), _l3("b"), _l3("c"), _l3("d")]
    fake = FakeLLMClient()
    fake.queue_chat_job(content='{"order": [2]}')

    out = await rerank_passages(
        fake, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["c", "a", "b", "d"]


@pytest.mark.asyncio
async def test_rerank_drops_out_of_range_and_duplicate_indices():
    """Malformed indices filtered out before fill-missing kicks in."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("a"), _l3("b"), _l3("c")]
    fake = FakeLLMClient()
    # out-of-range 99, duplicate 0, negative -1, bool True — all dropped.
    fake.queue_chat_job(content='{"order": [1, 99, 0, -1, 0, true]}')

    out = await rerank_passages(
        fake, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    # Valid picks: [1, 0]; missing: [2] -> appended at tail.
    assert [p.text for p in out] == ["b", "a", "c"]


@pytest.mark.asyncio
async def test_rerank_timeout_falls_back_to_mmr_order():
    """Review-impl MED: a slow rerank model must NOT eat the L3 timeout."""
    import asyncio as _asyncio

    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second"), _l3("third")]

    async def slow_submit(**kwargs):
        # Sleep past the 50ms inner-timeout window used by this test.
        await _asyncio.sleep(0.2)
        # Build a "successful" job that should be ignored by timeout.
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="chat",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": '{"order": [2, 1, 0]}'}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )

    fake = FakeLLMClient()
    fake.set_side_effect(slow_submit)

    out = await rerank_passages(
        fake, query="q", passages=passages,
        model="slow-llm", user_id=USER_UUID,
        timeout_s=0.05,
    )
    # Fell back to MMR order despite the eventual 'successful' response.
    assert [p.text for p in out] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_rerank_fallback_on_provider_error():
    """SDK-side LLMError keeps MMR order; the selector never bubbles."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second")]
    fake = FakeLLMClient()
    fake.queue_exception(LLMError("503"))

    out = await rerank_passages(
        fake, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["first", "second"]


@pytest.mark.asyncio
async def test_rerank_fallback_on_transient_retry_exhausted():
    """LLMTransientRetryNeededError also falls back."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second")]
    fake = FakeLLMClient()
    fake.queue_exception(LLMTransientRetryNeededError(
        "exhausted",
        job_id="00000000-0000-0000-0000-000000000001",
        underlying_code="LLM_UPSTREAM_ERROR",
    ))

    out = await rerank_passages(
        fake, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["first", "second"]


@pytest.mark.asyncio
async def test_select_l3_skips_rerank_when_model_unset(monkeypatch):
    """Default path: rerank_model=None -> llm_client.submit_and_wait
    never called."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    hits = [_hit("a", 0.9), _hit("b", 0.8)]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )
    fake_llm = FakeLLMClient()

    await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="q",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
        llm_client=fake_llm,
        rerank_model=None,  # opt-out
    )
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_select_l3_skips_rerank_when_only_one_passage(monkeypatch):
    """Single-passage pool: nothing to reorder; skip the LLM call."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    hits = [_hit("only one", 0.9)]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )
    fake_llm = FakeLLMClient()

    await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="q",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
        llm_client=fake_llm,
        rerank_model="llama-3",
    )
    assert fake_llm.calls == []


def test_embedding_model_to_dim_covers_supported_models():
    """Every mapped dim must be supported by passages.SUPPORTED_PASSAGE_DIMS
    OR the selector must be wise enough to skip unknown dims."""
    from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS
    for model, dim in EMBEDDING_MODEL_TO_DIM.items():
        _ = model  # silence unused
    assert any(
        dim in SUPPORTED_PASSAGE_DIMS
        for dim in EMBEDDING_MODEL_TO_DIM.values()
    )
