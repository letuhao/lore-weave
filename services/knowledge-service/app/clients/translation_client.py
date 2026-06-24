"""KG-ML M2 — HTTP client for translation-service internal API.

Thin async wrapper used by the `translation.published` event handler to fetch a
chapter's ACTIVE translated text so knowledge-service can dual-index it as vi
`:Passage` nodes. Follows the BookClient graceful-degradation contract: every
failure path returns None and logs a warning — the consumer treats None as
"nothing to index" (best-effort), never raising into the event loop.
"""
from __future__ import annotations

import logging
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

__all__ = [
    "TranslationClient",
    "init_translation_client",
    "get_translation_client",
]

logger = logging.getLogger(__name__)

_client: "TranslationClient | None" = None


class TranslationClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_active_translation_text(
        self, chapter_id: UUID, target_language: str
    ) -> str | None:
        """Return the ACTIVE translation's flat text for a chapter+language, or
        None when none exists / on any failure. Calls
        ``GET /internal/translation/chapters/{chapter_id}/active-text``."""
        url = f"{self._base_url}/internal/translation/chapters/{chapter_id}/active-text"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url,
                params={"target_language": target_language},
                headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning(
                    "translation-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return None
            body = resp.json()
            text = body.get("text")
            return text if isinstance(text, str) and text.strip() else None
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("translation-service unavailable: %s, trace_id=%s", exc, tid)
            return None


def init_translation_client() -> "TranslationClient":
    global _client
    _client = TranslationClient(
        base_url=settings.translation_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.translation_client_timeout_s,
    )
    return _client


def get_translation_client() -> "TranslationClient":
    if _client is None:
        return init_translation_client()
    return _client
