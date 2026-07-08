"""Embedding client for provider-registry-service (chat-service's FIRST
embedding-provider call site — 2026-07-08, design item 1 (embeddings sub-item)
of docs/plans/2026-07-07-mcp-discovery-and-reliability-hardening.md).

Calls POST /internal/embed on provider-registry-service to generate vector
embeddings via the user's BYOK credentials — the Provider Gateway invariant
(CLAUDE.md): chat-service never imports a provider SDK or calls a provider
directly, everything routes through provider-registry-service.

Ported from knowledge-service's `app/clients/embedding_client.py` (the
canonical pattern other services already mirror — composition-service has its
own near-identical copy). Two chat-service-specific adaptations, both
intentional, not oversights:
  - `user_id` is a plain `str` here (chat-service passes user ids as strings
    everywhere — stream_service.py, knowledge_client.py, etc. — never a `UUID`
    object), instead of knowledge-service's `UUID` param type.
  - Trace-id propagation reads `app.middleware.trace_id.trace_id_var`
    (chat-service's own contextvar module), NOT knowledge-service's
    `app.logging_config.trace_id_var` — that module doesn't exist here;
    `app/client/provider_client.py` already establishes this exact import for
    chat-service's other internal clients.

Timeout is generous (30s, matching every other embedding-client port in the
repo) because a first call to a cold local model (LM Studio, Ollama) can be
slow.

Consumer: `app/services/tool_discovery.py`'s embeddings-backed
`search_catalog_semantic()` — embeds each catalog tool's name+description+
synonyms ONCE per tool-catalog refresh, and the user's `intent` string fresh
per `find_tools` call. MANDATORY fallback discipline lives in the CALLER
(tool_discovery.py): any exception from this client's `embed()` must fall
back to the existing token-overlap scorer unconditionally — this module
itself only raises `EmbeddingError`, it never swallows/hides a failure, so
the caller can catch it precisely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from loreweave_internal_client import InternalClientError, build_internal_client

from app.config import settings
from app.middleware.trace_id import trace_id_var

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
    """Raised when embedding fails (provider down, bad/non-embedding model, etc.).

    Subclasses the shared `InternalClientError` so callers get one uniform
    `.retryable`/`.status_code` surface. `retryable` derives from a 429/502/503
    status (via the SDK's shared predicate) unless the raiser overrides it —
    transport errors pass `retryable=True` explicitly.
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
    # provider-registry forwards the upstream provider's reported input-token
    # usage; 0 when the backend omits it (e.g. Ollama) — callers treat 0 as
    # "unknown", not "free".
    prompt_tokens: int = 0


class EmbeddingClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # W3: shared factory bakes X-Internal-Token + JSON + per-request X-Trace-Id.
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, connect_timeout_s=5.0,
            trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def embed(
        self,
        *,
        user_id: str,
        model_source: str,
        model_ref: str,
        texts: list[str],
    ) -> EmbeddingResult:
        """Generate embeddings for a list of texts.

        Raises EmbeddingError on failure (with a `retryable` flag). Never
        swallows a failure — the mandatory graceful-degradation contract for
        chat-service's embeddings-backed tool search lives in the CALLER
        (tool_discovery.py), which must catch this and fall back to the
        token-overlap scorer.
        """
        url = f"{self._base_url}/internal/embed"
        body = {
            "model_source": model_source,
            "model_ref": model_ref,
            "texts": texts,
        }
        params = {"user_id": str(user_id)}

        try:
            resp = await self._http.post(url, json=body, params=params)
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

        detail = resp.text[:200]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001 — best-effort detail extraction
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
