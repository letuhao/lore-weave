"""K12.2 — Embedding client for provider-registry.

Calls POST /internal/embed on provider-registry to generate vector
embeddings via the user's BYOK credentials. Same graceful-degradation
pattern as BookClient/GlossaryClient.

Timeout is longer (30s) because first calls to cold local models
(LM Studio, Ollama) can be slow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx
from loreweave_internal_client import InternalClientError

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


class EmbeddingError(InternalClientError):
    """Raised when embedding fails (provider down, bad model, etc.).

    P3 SDK-first W2-tail: subclasses the shared InternalClientError so callers get
    one uniform `.retryable`/`.status_code` surface. `retryable` derives from a
    429/502/503 status (via the SDK's shared predicate) unless the raiser overrides
    it — transport errors pass `retryable=True` explicitly.
    """
    def __init__(
        self, message: str, retryable: bool | None = None, *, status_code: int | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, retryable=retryable)


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: list[list[float]]
    dimension: int
    model: str
    # D-K19e-γa-02 — upstream provider's reported input-token usage for the
    # embed call (provider-registry forwards OpenAI/LM Studio
    # `usage.prompt_tokens`). 0 when the provider omits it (e.g. Ollama) —
    # callers treat 0 as "unknown", not "free".
    prompt_tokens: int = 0


class EmbeddingClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def embed(
        self,
        *,
        user_id: UUID,
        model_source: str,
        model_ref: str,
        texts: list[str],
    ) -> EmbeddingResult:
        """Generate embeddings for a list of texts.

        Raises EmbeddingError on failure (with retryable flag).
        """
        url = f"{self._base_url}/internal/embed"
        tid = trace_id_var.get()
        body = {
            "model_source": model_source,
            "model_ref": model_ref,
            "texts": texts,
        }
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
                # provider-registry omits the field for backends that don't
                # report usage; default 0 → "unknown".
                prompt_tokens=int(data.get("prompt_tokens") or 0),
            )

        detail = resp.text[:200]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        # W2-tail: pass status_code and let the shared base derive `.retryable`
        # (429/502/503) — no local re-derivation of the transient-status set.
        raise EmbeddingError(
            f"embedding failed ({resp.status_code}): {detail}",
            status_code=resp.status_code,
        )


# ── Module-level singleton ───────────────────────────────────────────

_client: EmbeddingClient | None = None


def init_embedding_client() -> EmbeddingClient:
    global _client
    if _client is not None:
        return _client
    _client = EmbeddingClient(
        base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    return _client


async def close_embedding_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_embedding_client() -> EmbeddingClient:
    if _client is None:
        return init_embedding_client()
    return _client


async def probe_embedding_dimension(user_id: UUID, model_ref: str) -> int:
    """D-EMB-MODEL-REF-03 — determine an embedding model's vector
    dimension by embedding a short probe string and measuring the
    result.

    `model_ref` is a provider-registry `user_model` UUID. Used by the
    config flow (`change_embedding_model`, project PATCH) so the project
    stores `embedding_dimension` alongside `embedding_model` without the
    caller having to know the dimension. Raises `EmbeddingError` on any
    provider failure (unreachable, bad/non-embedding model, etc.).
    """
    result = await get_embedding_client().embed(
        user_id=user_id,
        model_source="user_model",
        model_ref=model_ref,
        texts=["dimension probe"],
    )
    if not result.embeddings or not result.embeddings[0]:
        raise EmbeddingError("embedding probe returned an empty vector")
    return len(result.embeddings[0])
