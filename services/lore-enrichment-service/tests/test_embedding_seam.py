"""C1/LE-059b — the embed seam meters the query.

provider-registry now surfaces the provider's REAL ``prompt_tokens`` (OpenAI/LM
Studio ``usage``), so the embed leg is metered on that real count when present and
falls back to the platform char-estimate only when the provider reports none.
These tests prove both paths + the no-meter no-op (vector unchanged).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.clients.knowledge import EmbedResult
from app.jobs.tokens import TokenUsage, UsageMeter, estimate_tokens
from app.retrieval.embedding import make_embed_query_fn
from app.strategies.base import StrategyContext


class _FakeKnowledgeClient:
    """Captures the embed call and returns a canned single vector. ``prompt_tokens``
    simulates whether the provider reported a real usage count (LE-059b)."""

    def __init__(self, prompt_tokens: int = 0) -> None:
        self.calls: list[dict] = []
        self._prompt_tokens = prompt_tokens

    async def embed(self, *, user_id, model_source, model_ref, texts):
        self.calls.append({"texts": texts, "model_ref": model_ref})
        return EmbedResult(
            embeddings=[[0.1, 0.2, 0.3]], dimension=3, model="m",
            prompt_tokens=self._prompt_tokens,
        )


def _ctx() -> StrategyContext:
    return StrategyContext(
        user_id=str(uuid4()), project_id=str(uuid4()), model_ref=str(uuid4())
    )


@pytest.mark.asyncio
async def test_embed_query_falls_back_to_estimate_when_provider_reports_no_usage():
    client = _FakeKnowledgeClient(prompt_tokens=0)  # provider omitted usage
    meter = UsageMeter()
    embed_query = make_embed_query_fn(client, user_id=uuid4(), meter=meter)  # type: ignore[arg-type]
    query = "昆侖山 历史 人物"
    vec = await embed_query(query, _ctx())
    assert vec == [0.1, 0.2, 0.3]  # vector contract unchanged
    # no provider count → input-token estimate of the query text.
    assert meter.usage == TokenUsage(input_tokens=estimate_tokens(query))
    assert meter.total_tokens == estimate_tokens(query)


@pytest.mark.asyncio
async def test_embed_query_meters_real_prompt_tokens_when_present():
    # LE-059b: provider reported usage.prompt_tokens → meter on the REAL count,
    # NOT the char-estimate.
    client = _FakeKnowledgeClient(prompt_tokens=37)
    meter = UsageMeter()
    embed_query = make_embed_query_fn(client, user_id=uuid4(), meter=meter)  # type: ignore[arg-type]
    query = "昆侖山 历史 人物"
    await embed_query(query, _ctx())
    assert meter.usage == TokenUsage(input_tokens=37)
    assert meter.total_tokens == 37
    assert 37 != estimate_tokens(query)  # the real count is distinct from the estimate


@pytest.mark.asyncio
async def test_embed_query_without_meter_is_noop():
    client = _FakeKnowledgeClient()
    embed_query = make_embed_query_fn(client, user_id=uuid4())  # type: ignore[arg-type]
    vec = await embed_query("昆侖山", _ctx())
    assert vec == [0.1, 0.2, 0.3]  # still returns the vector, no metering needed
