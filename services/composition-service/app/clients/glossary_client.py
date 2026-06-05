"""glossary-service client (composition-service, M3 — packer L0 lens).

Contract-verified 2026-06-04 (glossary server.go): both surfaces below are
**INTERNAL** (`X-Internal-Token`) and book-scoped only — they do NOT re-check the
user. So composition MUST verify book ownership (BookClient.owns_book) BEFORE
calling these (SEC2 chokepoint); the M4 packer is responsible for that gate.

Graceful degradation (the packer `_safe_*` pattern, §2.5/F1): every method
returns [] / None on any failure and never raises — a glossary outage degrades
the pack (thinner context), it does not 500 a generate. We cache the STABLE
glossary `entity_id` (never knowledge's rename-sensitive canonical_id, §13 DI3).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

_client: "GlossaryClient | None" = None


class GlossaryClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str] | None:
        tid = trace_id_var.get()
        return {"X-Trace-Id": tid} if tid else None

    async def select_for_context(
        self, book_id: UUID, user_id: UUID, query: str, *,
        max_entities: int = 20, max_tokens: int = 1000,
        exclude_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """L0/L1 glossary entities most relevant to `query` for this book.
        Returns the entities list (each carries the stable `entity_id`,
        `cached_name`, `cached_aliases`, `short_description`, `kind_code`,
        `tier`), or [] on any failure."""
        url = f"{self._base_url}/internal/books/{book_id}/select-for-context"
        payload: dict[str, Any] = {
            "user_id": str(user_id), "query": query,
            "max_entities": max_entities, "max_tokens": max_tokens,
        }
        if exclude_ids:
            payload["exclude_ids"] = exclude_ids
        try:
            resp = await self._http.post(url, json=payload, headers=self._headers())
            if resp.status_code != 200:
                logger.warning("glossary select-for-context → %d", resp.status_code)
                return []
            return resp.json().get("entities", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("glossary select-for-context unavailable: %s", exc)
            return []

    async def list_entities(
        self, book_id: UUID, *, limit: int = 100, cursor: str | None = None,
    ) -> dict[str, Any] | None:
        """Internal cursor-paginated entity list (carries `aliases`). Returns
        `{items, next_cursor}` or None on failure."""
        url = f"{self._base_url}/internal/books/{book_id}/entities"
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = await self._http.get(url, params=params, headers=self._headers())
            if resp.status_code != 200:
                logger.warning("glossary list-entities → %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("glossary list-entities unavailable: %s", exc)
            return None


def init_glossary_client() -> GlossaryClient:
    global _client
    if _client is None:
        _client = GlossaryClient(settings.glossary_internal_url, settings.internal_service_token)
    return _client


def get_glossary_client() -> GlossaryClient:
    return _client or init_glossary_client()


async def close_glossary_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
