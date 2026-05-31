"""C1 — the embed seam meters the query (DEFERRED-052).

``/internal/embed`` returns no token usage, so the embed leg of the per-gap cost
is ESTIMATED from the query text via the platform char-convention. These tests
prove ``make_embed_query_fn`` records that estimate into the meter when one is
supplied, and is a no-op (vector unchanged) when none is.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.clients.knowledge import EmbedResult
from app.jobs.tokens import TokenUsage, UsageMeter, estimate_tokens
from app.retrieval.embedding import make_embed_query_fn
from app.strategies.base import StrategyContext


class _FakeKnowledgeClient:
    """Captures the embed call and returns a canned single vector."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def embed(self, *, user_id, model_source, model_ref, texts):
        self.calls.append({"texts": texts, "model_ref": model_ref})
        return EmbedResult(embeddings=[[0.1, 0.2, 0.3]], dimension=3, model="m")


def _ctx() -> StrategyContext:
    return StrategyContext(
        user_id=str(uuid4()), project_id=str(uuid4()), model_ref=str(uuid4())
    )


@pytest.mark.asyncio
async def test_embed_query_records_query_token_estimate_into_meter():
    client = _FakeKnowledgeClient()
    meter = UsageMeter()
    embed_query = make_embed_query_fn(client, user_id=uuid4(), meter=meter)  # type: ignore[arg-type]
    query = "昆侖山 历史 人物"
    vec = await embed_query(query, _ctx())
    assert vec == [0.1, 0.2, 0.3]  # vector contract unchanged
    # embed has no provider count → input-token estimate of the query text.
    assert meter.usage == TokenUsage(input_tokens=estimate_tokens(query))
    assert meter.total_tokens == estimate_tokens(query)


@pytest.mark.asyncio
async def test_embed_query_without_meter_is_noop():
    client = _FakeKnowledgeClient()
    embed_query = make_embed_query_fn(client, user_id=uuid4())  # type: ignore[arg-type]
    vec = await embed_query("昆侖山", _ctx())
    assert vec == [0.1, 0.2, 0.3]  # still returns the vector, no metering needed
