"""E5B — HTTP client for the cross-encoder rerank service.

Calls provider-registry `POST /internal/rerank` (which proxies the platform
rerank service). Same graceful-degradation contract as EmbeddingClient /
BookClient: any failure returns ``None`` so the raw-search orchestrator
degrades to the pre-rerank fusion order — search never 500s because rerank
is down, loading, or slow.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

__all__ = ["RerankerClient", "init_reranker_client", "get_reranker_client"]

logger = logging.getLogger(__name__)

_client: "RerankerClient | None" = None


class RerankerClient:
    def __init__(self, base_url: str, internal_token: str, model: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def rerank(self, query: str, documents: list[str]) -> list[dict] | None:
        """Return [{"index": i, "relevance_score": s}, …] sorted desc, or None.

        ``index`` refers to the input ``documents`` list. None on ANY failure
        (service down, 503 not-configured, cold-load timeout, parse error) →
        caller keeps the fusion order."""
        if not documents:
            return []
        url = f"{self._base_url}/internal/rerank"
        tid = trace_id_var.get()
        try:
            resp = await self._http.post(
                url,
                json={"model": self._model, "query": query, "documents": documents},
                headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning("rerank %s returned %d, trace_id=%s", url, resp.status_code, tid)
                return None
            results = resp.json().get("results", [])
            return results if isinstance(results, list) else None
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("rerank service unavailable: %s, trace_id=%s", exc, tid)
            return None


def init_reranker_client() -> RerankerClient:
    global _client
    if _client is not None:
        return _client
    _client = RerankerClient(
        base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
        model=settings.rerank_model,
        timeout_s=settings.rerank_timeout_s,
    )
    return _client


async def close_reranker_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_reranker_client() -> RerankerClient:
    return _client if _client is not None else init_reranker_client()
