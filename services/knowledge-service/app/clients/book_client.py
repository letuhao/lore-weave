"""K16.2 — HTTP client for book-service internal API.

Thin async wrapper for chapter-count lookups used by extraction cost
estimation. Follows the same graceful-degradation contract as
GlossaryClient: every failure path returns a safe default and logs a
warning — the caller never sees an exception.

Unlike GlossaryClient this client is NOT on the chat hot path, so no
circuit breaker. Cost estimation is a user-initiated action that can
tolerate slightly higher latency.
"""

import logging
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

__all__ = ["BookClient", "init_book_client", "get_book_client"]

logger = logging.getLogger(__name__)

_client: "BookClient | None" = None


class BookClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def count_chapters(self, book_id: UUID) -> int | None:
        """Return the number of active chapters for a book.

        Returns None on any failure (timeout, connection error, bad
        response) — the caller decides how to handle missing data.
        """
        url = f"{self._base_url}/internal/books/{book_id}/chapters?limit=1"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url, headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return None
            data = resp.json()
            return int(data.get("total", 0))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable: %s, trace_id=%s",
                exc, tid,
            )
            return None

    async def get_chapter_text(
        self, book_id: UUID, chapter_id: UUID,
    ) -> str | None:
        """Fetch the aggregated plain text of a chapter.

        Calls `/internal/books/{book_id}/chapters/{chapter_id}` which
        returns a JSON body with `text_content` — a string built from
        the chapter_blocks denormalized rows joined on double newline.

        Returns None on any failure (book or chapter missing, network
        error, empty text_content). Used by K18.3 passage ingestion
        (D-K18.3-01). The caller's degradation policy treats None as
        "skip this chapter's passages" — Mode 3 still works without
        passages for that chapter.
        """
        url = f"{self._base_url}/internal/books/{book_id}/chapters/{chapter_id}"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url, headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return None
            data = resp.json()
            text = data.get("text_content")
            if not isinstance(text, str) or not text.strip():
                return None
            return text
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable fetching chapter text: %s trace_id=%s",
                exc, tid,
            )
            return None


def init_book_client() -> "BookClient":
    global _client
    if _client is not None:
        return _client
    _client = BookClient(
        base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.book_client_timeout_s,
    )
    return _client


async def close_book_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_book_client() -> "BookClient":
    if _client is None:
        return init_book_client()
    return _client
