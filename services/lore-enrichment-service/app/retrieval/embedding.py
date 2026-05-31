"""Embedding seam — binds the C1 KnowledgeClient to the C10 retrieval callables.

The store (``store.py``) and strategy (``strategy.py``) take embedding as an
INJECTED async callable so they never import an HTTP/LLM client and never know a
model name. This module is the ONE place that wires the real call: it REUSES the
C1 ``KnowledgeClient.embed`` → knowledge-service/provider-registry
``/internal/embed`` with ``model_source='user_model'`` and a provider-registry
``model_ref`` (a ``user_model`` UUID). No model NAME is ever passed — only the
ref. NO new framework, NO heavy dep.

Factory functions return closures matching the seams:
  * :func:`make_embed_fn`        → ``EmbedFn`` (batch: list[str] → list[vector])
    used by ``SourceCorpusStore.ingest_corpus`` to embed chunks.
  * :func:`make_embed_query_fn`  → ``EmbedQueryFn`` (str, ctx → vector) used by
    ``RetrievalStrategy.run`` to embed a single gap query (model_ref read from
    the per-run ``StrategyContext``).
"""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app import metrics
from app.clients.knowledge import KnowledgeClient
from app.jobs.tokens import TokenUsage, UsageMeter, estimate_tokens
from app.retrieval.store import EmbedFn
from app.strategies.base import StrategyContext

__all__ = ["MODEL_SOURCE", "make_embed_fn", "make_embed_query_fn"]

#: The provider-registry model source. ``user_model`` means "resolve a BYOK
#: user_model row by its UUID" — the only source /internal/embed accepts. This is
#: a SOURCE selector, NOT a model name (no embedding model id appears here).
MODEL_SOURCE: str = "user_model"


def make_embed_fn(
    client: KnowledgeClient, *, user_id: UUID, model_ref: str
) -> EmbedFn:
    """Bind a batch ``EmbedFn`` for ingest: embeds many chunk texts in one call
    via the C1 client under ``model_ref`` (a provider-registry user_model id)."""

    async def _embed(texts: Sequence[str]) -> list[list[float]]:
        result = await client.embed(
            user_id=user_id,
            model_source=MODEL_SOURCE,
            model_ref=model_ref,
            texts=list(texts),
        )
        return result.embeddings

    return _embed


def make_embed_query_fn(
    client: KnowledgeClient, *, user_id: UUID, meter: UsageMeter | None = None
):
    """Bind an ``EmbedQueryFn`` for search: embeds ONE query string, reading the
    ``model_ref`` from the per-run :class:`StrategyContext` (so each run uses its
    project's configured embedding model). Returns a single vector.

    ``meter`` (C1 / DEFERRED-052): ``/internal/embed`` returns no token usage, so
    when a meter is supplied the embed leg of the per-gap cost is ESTIMATED from
    the query text via the platform char-convention (``estimate_tokens``) and
    recorded as input tokens. The vector return is unchanged — metering is a side
    effect, not a contract change. (Follow-up: real embed usage requires a
    provider-registry change — out of scope on this branch; see DEFERRED-052.)
    """

    async def _embed_query(query: str, context: StrategyContext) -> list[float]:
        if not context.model_ref:
            raise ValueError(
                "StrategyContext.model_ref is required for retrieval embedding "
                "(resolve the project's embedding model via provider-registry)"
            )
        # C18 — count the real embed call by outcome (NO model name in the label;
        # the model is resolved by model_ref at runtime).
        try:
            result = await client.embed(
                user_id=user_id,
                model_source=MODEL_SOURCE,
                model_ref=context.model_ref,
                texts=[query],
            )
        except Exception:
            metrics.embed_calls_total.labels(outcome="error").inc()
            raise
        metrics.embed_calls_total.labels(outcome="ok").inc()
        if not result.embeddings:
            raise ValueError("embed returned no vector for the query")
        if meter is not None:
            # Estimate-only: no provider token count for embeddings (DEFERRED-052).
            meter.add(TokenUsage(input_tokens=estimate_tokens(query)))
        return result.embeddings[0]

    return _embed_query
