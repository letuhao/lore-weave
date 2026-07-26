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
from loreweave_internal_client import build_internal_client

from app.config import settings
from app.logging_config import trace_id_var

__all__ = ["RerankerClient", "init_reranker_client", "get_reranker_client"]

logger = logging.getLogger(__name__)

_client: "RerankerClient | None" = None


class RerankerClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        # W3: shared factory bakes X-Internal-Token + JSON + per-request X-Trace-Id.
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, connect_timeout_s=5.0,
            trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_default_rerank(self, user_id: str) -> str | None:
        """Resolve the user's DEFAULT rerank model (a provider-registry user_model
        UUID), or None. Fallback when a project has no per-project rerank model —
        restores the default-reranker UX the removed .env config gave (BYOK). Any
        failure (no default set → 404, service down) returns None → no rerank."""
        url = f"{self._base_url}/internal/default-models/rerank"
        try:
            resp = await self._http.get(url, params={"user_id": user_id})
            if resp.status_code != 200:
                return None
            return resp.json().get("user_model_id")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("default-rerank resolve unavailable: %s", exc)
            return None

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        user_id: str,
        model_source: str,
        model_ref: str,
    ) -> list[dict] | None:
        """Return [{"index": i, "relevance_score": s}, …] sorted desc, or None.

        ``index`` refers to the input ``documents`` list. None on ANY failure
        (service down, model-not-found, cold-load timeout, parse error) → caller
        keeps the fusion order. D-RERANK-NOT-BYOK: the rerank model is the user's
        BYOK ``model_ref`` (a provider-registry user_model UUID), resolved
        per-user by provider-registry — no hardcoded model name."""
        if not documents:
            return []
        url = f"{self._base_url}/internal/rerank"
        tid = trace_id_var.get()
        try:
            resp = await self._http.post(
                url,
                params={"user_id": user_id},
                json={
                    "model_source": model_source,
                    "model_ref": model_ref,
                    "query": query,
                    "documents": documents,
                },
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
