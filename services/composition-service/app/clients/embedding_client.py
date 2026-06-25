"""Embedding client for provider-registry (composition-service, LOOM T3.6).

Calls POST /internal/embed on provider-registry to vectorise reference passages
(and per-scene queries) via the user's BYOK credentials. This is the ONLY way
composition reaches an embedding model — the provider-gateway invariant is
satisfied by hitting provider-registry directly (no provider SDK here, no routing
through knowledge-service). Mirrors knowledge-service's embedding_client + the
graceful-degradation posture of the other composition clients.

Timeout is generous (30s) because the first call to a cold local model (LM Studio,
Ollama) can be slow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

__all__ = [
    "EmbeddingClient",
    "EmbeddingResult",
    "EmbeddingError",
    "init_embedding_client",
    "get_embedding_client",
    "close_embedding_client",
]

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding fails (provider down, bad/non-embedding model, etc.).
    `retryable` is True for transient failures (timeout / 502 / 503 / 429)."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: list[list[float]]
    dimension: int
    model: str
    # provider-registry forwards the upstream provider's input-token usage; 0 when
    # the backend omits it (e.g. Ollama) — callers treat 0 as "unknown", not "free".
    prompt_tokens: int = 0


class EmbeddingClient:
    def __init__(
        self, base_url: str, internal_token: str, timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def embed(
        self, *, user_id: UUID, model_source: str, model_ref: str, texts: list[str],
    ) -> EmbeddingResult:
        """Embed `texts` with the user's BYOK model. Raises EmbeddingError on
        failure (with a `retryable` flag)."""
        url = f"{self._base_url}/internal/embed"
        tid = trace_id_var.get()
        body = {"model_source": model_source, "model_ref": model_ref, "texts": texts}
        params = {"user_id": str(user_id)}
        try:
            resp = await self._http.post(
                url, json=body, params=params,
                headers={"X-Trace-Id": tid} if tid else None,
            )
        except httpx.TimeoutException as exc:
            raise EmbeddingError(f"timeout: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"connection error: {exc}", retryable=True)

        if resp.status_code == 200:
            data = resp.json()
            return EmbeddingResult(
                embeddings=data["embeddings"],
                dimension=data["dimension"],
                model=data["model"],
                prompt_tokens=int(data.get("prompt_tokens") or 0),
            )

        retryable = resp.status_code in (502, 503, 429)
        detail = resp.text[:200]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001 — best-effort detail extraction
            pass
        raise EmbeddingError(
            f"embedding failed ({resp.status_code}): {detail}", retryable=retryable,
        )


# ── Module-level singleton ───────────────────────────────────────────

_client: EmbeddingClient | None = None


def init_embedding_client() -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient(
            base_url=settings.llm_gateway_internal_url,
            internal_token=settings.internal_service_token,
        )
    return _client


def get_embedding_client() -> EmbeddingClient:
    return _client or init_embedding_client()


async def close_embedding_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
