"""HTTP client for glossary-service's /internal/books/{id}/select-for-context.

Graceful degradation is the contract: every failure path (timeout,
5xx, 4xx, connection error, decode error) returns an empty list and
logs a warning. The caller never sees an exception — chat should keep
working with a smaller context when glossary-service is unavailable.

The async client is long-lived and created in the knowledge-service
lifespan so it can pool connections. Tests substitute a fake via
FastAPI dependency_overrides rather than hitting the real URL.
"""

import logging
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings

__all__ = ["GlossaryClient", "GlossaryEntityForContext"]

logger = logging.getLogger(__name__)


class GlossaryEntityForContext(BaseModel):
    """Mirror of glossary-service's selectForContext row (K2b)."""

    model_config = ConfigDict(extra="ignore")

    entity_id: str
    cached_name: str | None = None
    cached_aliases: list[str] = Field(default_factory=list)
    short_description: str | None = None
    kind_code: str
    is_pinned: bool = False
    tier: str = ""
    rank_score: float = 0.0


class GlossaryClient:
    """Thin async wrapper around httpx.AsyncClient.

    One instance per knowledge-service process, shared across requests.
    Close via `await client.aclose()` on shutdown.
    """

    def __init__(self, base_url: str, internal_token: str, timeout_s: float, retries: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = internal_token
        self._retries = max(0, retries)
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def select_for_context(
        self,
        *,
        user_id: UUID,
        book_id: UUID,
        query: str,
        max_entities: int = 20,
        max_tokens: int = 800,
        exclude_ids: list[str] | None = None,
    ) -> list[GlossaryEntityForContext]:
        """POST /internal/books/{book_id}/select-for-context.

        Returns an empty list on any failure — never raises. The caller
        treats missing glossary as "degrade silently".
        """
        url = f"{self._base_url}/internal/books/{book_id}/select-for-context"
        body = {
            "user_id": str(user_id),
            "query": query or "",
            "max_entities": int(max_entities),
            "max_tokens": int(max_tokens),
            "exclude_ids": exclude_ids or [],
        }

        attempts = self._retries + 1
        last_err: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = await self._http.post(url, json=body)
            except httpx.TimeoutException as exc:
                last_err = exc
                logger.warning(
                    "glossary client timeout (attempt %d/%d) url=%s",
                    attempt + 1, attempts, url,
                )
                continue
            except httpx.HTTPError as exc:
                last_err = exc
                logger.warning(
                    "glossary client transport error (attempt %d/%d): %s",
                    attempt + 1, attempts, exc,
                )
                continue

            if resp.status_code >= 500:
                last_err = RuntimeError(f"glossary 5xx: {resp.status_code}")
                logger.warning(
                    "glossary client %d (attempt %d/%d)",
                    resp.status_code, attempt + 1, attempts,
                )
                continue

            if resp.status_code >= 400:
                # 4xx is not retried — it's a stable request problem.
                logger.warning(
                    "glossary client %d (no retry) body=%s",
                    resp.status_code, resp.text[:200],
                )
                return []

            try:
                data = resp.json()
            except Exception as exc:
                logger.warning("glossary client decode failure: %s", exc)
                return []

            entities_raw = data.get("entities") if isinstance(data, dict) else None
            if not isinstance(entities_raw, list):
                logger.warning("glossary client unexpected payload shape")
                return []

            parsed: list[GlossaryEntityForContext] = []
            for row in entities_raw:
                try:
                    parsed.append(GlossaryEntityForContext.model_validate(row))
                except Exception as exc:
                    logger.warning("glossary client row validate skip: %s", exc)
            return parsed

        # All attempts exhausted.
        logger.warning(
            "glossary client exhausted retries: %s",
            last_err if last_err else "unknown",
        )
        return []


# ── module-level singleton managed by lifespan ─────────────────────────────

_client: GlossaryClient | None = None


def init_glossary_client() -> GlossaryClient:
    """Instantiate the shared client from settings. Called from lifespan."""
    global _client
    _client = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.glossary_client_timeout_s,
        retries=settings.glossary_client_retries,
    )
    return _client


async def close_glossary_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_glossary_client() -> GlossaryClient:
    if _client is None:
        raise RuntimeError("glossary client not initialised")
    return _client
