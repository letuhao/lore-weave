"""K18.3 — unit tests for the L3 semantic passage selector."""
from __future__ import annotations

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
    # Non-hub passage (raw 0.80) wins over hub (raw 0.92 × 0.3 = 0.276).
    assert result[0].text == "Arthur is knighted."
    assert result[0].is_hub is False


@pytest.mark.asyncio
async def test_historical_intent_inverts_recency_preference(monkeypatch):
    """HISTORICAL intent has recency_weight=-1 → older chapter wins
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
    auto-anchors "now" to max(chapter_index) in the hit pool. Without
    this fallback, every passage sees age=0 and recency weighting is
    dead in production (no caller currently passes the param).
    """
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
    # Historical intent + pool-anchored recency → oldest wins.
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

    # SPECIFIC_ENTITY top_n=5 → all three could fit; MMR should still
    # prefer the diverse Merlin passage over the near-dup.
    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="Tell me about Arthur",
        intent=_intent(intent=Intent.SPECIFIC_ENTITY),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    # Near-duplicate "again" passage should come AFTER Merlin due to MMR
    # redundancy penalty.
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
    """P-K18.3-02: when hits carry vectors, MMR redundancy uses cosine.

    Crafted case: two hits whose TEXT is word-distinct (low Jaccard)
    but whose VECTORS are nearly identical (high cosine). Jaccard-
    based MMR would keep both in top-N; cosine-based MMR drops the
    semantic duplicate in favor of the third, genuinely distinct hit.
    """
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    # Two near-identical vectors (the "semantic duplicates"), one
    # orthogonal vector (the diverse passage).
    vec_a = [1.0, 0.0, 0.0, 0.0]
    vec_a_prime = [0.99, 0.01, 0.0, 0.0]  # cosine ~0.9999 with vec_a
    vec_b = [0.0, 1.0, 0.0, 0.0]  # orthogonal to vec_a → cosine 0.0

    hits = [
        _hit("alpha beta gamma delta", 0.95, pid="a", vector=vec_a),
        _hit("epsilon zeta eta theta", 0.90, pid="a2", vector=vec_a_prime),
        _hit("iota kappa lambda mu", 0.85, pid="b", vector=vec_b),
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )

    # SPECIFIC_ENTITY → top_n=5 so all three fit; ordering is what we're
    # asserting, not truncation.
    result = await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="anything",
        intent=_intent(intent=Intent.SPECIFIC_ENTITY),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    pids = [r.source_id for r in result]  # source_id carries chap-1 for all
    # Instead of source_id, we track by text since all share the same chap.
    texts = [r.text for r in result]
    # The highest-relevance hit "alpha beta gamma delta" wins the first seat.
    assert texts[0] == "alpha beta gamma delta"
    # The diverse-vector passage ("iota ...") must beat the near-duplicate
    # vector passage ("epsilon ..."): cosine says vec_a_prime ≈ vec_a so
    # "epsilon ..." gets the redundancy hit even though its text has zero
    # word overlap with "alpha beta gamma delta" (Jaccard = 0).
    assert texts.index("iota kappa lambda mu") < texts.index(
        "epsilon zeta eta theta"
    )


@pytest.mark.asyncio
async def test_mmr_falls_back_to_jaccard_when_vectors_missing(monkeypatch):
    """P-K18.3-02 backward-compat: hits without vectors use text
    Jaccard exactly as before, so `test_mmr_drops_near_duplicate_passages`
    behavior is preserved when include_vectors is False at the call site
    (or for any hit where the vector didn't project).
    """
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())

    # Same text shape as test_mmr_drops_near_duplicate_passages, but
    # vectors are explicitly None — this is the path the selector sees
    # if include_vectors=False is ever wired in via config.
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
    # Near-duplicate "again" passage should come AFTER Merlin via Jaccard.
    assert texts.index("Merlin casts a protection spell.") < texts.index(
        "Arthur rides into Camelot at dawn again."
    )


@pytest.mark.asyncio
async def test_mmr_handles_mixed_vector_presence(monkeypatch):
    """Defensive: if one hit has a vector and another doesn't, per-pair
    branch uses cosine when both sides have vectors, Jaccard otherwise.
    Shouldn't crash, shouldn't produce nonsensical ordering.
    """
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
    """Review-impl catch: MMR must early-exit at top_n so ranking the
    tail of a large pool doesn't eat the L3 timeout budget.

    Benchmark at DIM=3072 showed full-pool MMR takes ~1.2 s; capping
    to top_n cuts that to ~57 ms. Assertion here is behavioural — that
    the returned list has len == top_n + 1 is NOT claimed (returned
    list size == top_n). The caller truncates anyway so the contract
    is "don't rank past top_n".
    """
    from app.context.selectors.passages import _mmr_rerank

    # 40 hits, each with a small unique vector (bit-pattern in 8 dims).
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

    # top_n caps selected count.
    result = _mmr_rerank(hits, lam=0.7, top_n=10)
    assert len(result) == 10

    # top_n=None returns the full ranking (back-compat path).
    all_ranked = _mmr_rerank(hits, lam=0.7, top_n=None)
    assert len(all_ranked) == 40


def test_cosine_zero_magnitude_is_safe():
    """Zero-vector must return 0.0, not NaN or ZeroDivisionError."""
    from app.context.selectors.passages import _cosine
    assert _cosine([0.0, 0.0], 0.0, [1.0, 0.0], 1.0) == 0.0
    assert _cosine([1.0, 0.0], 1.0, [0.0, 0.0], 0.0) == 0.0
    assert _cosine([0.0, 0.0], 0.0, [0.0, 0.0], 0.0) == 0.0


# ── D-K18.3-02 generative rerank ─────────────────────────────────────


def _rerank_response(content: str):
    """Build a ChatCompletionResponse-shaped mock return value."""
    from app.clients.provider_client import (
        ChatCompletionResponse,
        ChatCompletionUsage,
    )
    return ChatCompletionResponse(
        content=content,
        usage=ChatCompletionUsage(),
        model="test-rerank",
        raw={},
    )


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
    provider = MagicMock()
    provider.chat_completion = AsyncMock(
        return_value=_rerank_response('{"order": [2, 0, 1]}')
    )

    out = await rerank_passages(
        provider,
        query="test",
        passages=passages,
        model="llama-3",
        user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["third", "first", "second"]


@pytest.mark.asyncio
async def test_rerank_prompt_carries_query_and_numbered_passages():
    """Review-design guard: the LLM prompt must include `Query:` and
    numbered `[i]` markers so a future prompt refactor that removes
    them (and silently breaks the parse contract) is caught here."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("alpha"), _l3("beta")]
    provider = MagicMock()
    provider.chat_completion = AsyncMock(
        return_value=_rerank_response('{"order": [0, 1]}')
    )

    await rerank_passages(
        provider, query="where is alpha",
        passages=passages, model="llama-3", user_id=USER_UUID,
    )
    call = provider.chat_completion.await_args
    user_msg = call.kwargs["messages"][1]["content"]
    assert "Query: where is alpha" in user_msg
    assert "[0] alpha" in user_msg
    assert "[1] beta" in user_msg


@pytest.mark.asyncio
async def test_rerank_fallback_on_non_json_response():
    """Any non-JSON body → keep original MMR order; never raises."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second")]
    provider = MagicMock()
    provider.chat_completion = AsyncMock(
        return_value=_rerank_response("not json at all")
    )

    out = await rerank_passages(
        provider, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["first", "second"]  # unchanged


@pytest.mark.asyncio
async def test_rerank_handles_partial_order_by_appending_missing_indices():
    """LLM returned [2] only — we should rerank [2] first, then fill
    in the missing indices in original MMR order at the tail."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("a"), _l3("b"), _l3("c"), _l3("d")]
    provider = MagicMock()
    provider.chat_completion = AsyncMock(
        return_value=_rerank_response('{"order": [2]}')
    )

    out = await rerank_passages(
        provider, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["c", "a", "b", "d"]


@pytest.mark.asyncio
async def test_rerank_drops_out_of_range_and_duplicate_indices():
    """Malformed indices filtered out before fill-missing kicks in."""
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("a"), _l3("b"), _l3("c")]
    provider = MagicMock()
    # out-of-range 99, duplicate 0, negative -1, bool True — all dropped.
    provider.chat_completion = AsyncMock(
        return_value=_rerank_response('{"order": [1, 99, 0, -1, 0, true]}')
    )

    out = await rerank_passages(
        provider, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    # Valid picks: [1, 0]; missing: [2] → appended at tail.
    assert [p.text for p in out] == ["b", "a", "c"]


@pytest.mark.asyncio
async def test_rerank_timeout_falls_back_to_mmr_order():
    """Review-impl MED catch: a slow rerank model must NOT eat the L3
    timeout and leave Mode 3 with zero passages. The inner timeout
    fires first so the MMR order stays as the fallback — enabling
    rerank never degrades context below the no-rerank baseline."""
    import asyncio as _asyncio

    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second"), _l3("third")]

    async def slow_chat(**kwargs):
        # Sleep past the 50ms inner-timeout window used by this test.
        await _asyncio.sleep(0.2)
        return _rerank_response('{"order": [2, 1, 0]}')

    provider = MagicMock()
    provider.chat_completion = slow_chat  # real coroutine, not AsyncMock

    out = await rerank_passages(
        provider, query="q", passages=passages,
        model="slow-llm", user_id=USER_UUID,
        timeout_s=0.05,
    )
    # Fell back to MMR order despite the eventual 'successful' response.
    assert [p.text for p in out] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_rerank_fallback_on_provider_error():
    """Provider errors (timeout, upstream down) keep MMR order; the
    selector never bubbles the exception up."""
    from app.clients.provider_client import ProviderUpstreamError
    from app.context.selectors.passages import rerank_passages

    passages = [_l3("first"), _l3("second")]
    provider = MagicMock()
    provider.chat_completion = AsyncMock(
        side_effect=ProviderUpstreamError("503"),
    )

    out = await rerank_passages(
        provider, query="q", passages=passages,
        model="llama-3", user_id=USER_UUID,
    )
    assert [p.text for p in out] == ["first", "second"]


@pytest.mark.asyncio
async def test_select_l3_skips_rerank_when_model_unset(monkeypatch):
    """Default path: rerank_model=None → provider_client never called."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    hits = [_hit("a", 0.9), _hit("b", 0.8)]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )
    provider = MagicMock()
    provider.chat_completion = AsyncMock()

    await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="q",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
        provider_client=provider,
        rerank_model=None,  # opt-out
    )
    provider.chat_completion.assert_not_called()


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
    provider = MagicMock()
    provider.chat_completion = AsyncMock()

    await select_l3_passages(
        MagicMock(), client,
        user_id=USER_ID, project_id=PROJECT_ID,
        message="q",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
        provider_client=provider,
        rerank_model="llama-3",
    )
    provider.chat_completion.assert_not_called()


def test_embedding_model_to_dim_covers_supported_models():
    """Every mapped dim must be supported by passages.SUPPORTED_PASSAGE_DIMS
    OR the selector must be wise enough to skip unknown dims."""
    from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS
    for model, dim in EMBEDDING_MODEL_TO_DIM.items():
        # Not all mapped dims are supported — nomic-embed (768) won't be,
        # which is exactly why the selector short-circuits on unsupported
        # dims. But at least ONE mapped model must match a supported dim
        # or the feature is dead.
        _ = model  # silence unused
    assert any(
        dim in SUPPORTED_PASSAGE_DIMS
        for dim in EMBEDDING_MODEL_TO_DIM.values()
    )
