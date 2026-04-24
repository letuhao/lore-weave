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

    async def count_chapters(
        self,
        book_id: UUID,
        *,
        from_sort: int | None = None,
        to_sort: int | None = None,
    ) -> int | None:
        """Return the number of active chapters for a book.

        Optional ``from_sort`` / ``to_sort`` scope the count to an
        inclusive range of ``sort_order`` values. Passing ``None`` for
        either leaves that end unbounded. D-K16.2-02 — used by the
        extraction estimate endpoint so users previewing "chapters
        10–20 only" see the range count rather than the whole book.

        Returns None on any failure (timeout, connection error, bad
        response) — the caller decides how to handle missing data.
        """
        params: dict[str, str] = {"limit": "1"}
        if from_sort is not None:
            params["from_sort"] = str(from_sort)
        if to_sort is not None:
            params["to_sort"] = str(to_sort)
        url = f"{self._base_url}/internal/books/{book_id}/chapters"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url,
                params=params,
                headers={"X-Trace-Id": tid} if tid else None,
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

    async def get_chapter_titles(
        self, chapter_ids: list[UUID],
    ) -> dict[UUID, str]:
        """C6 (D-K19b.3-01 + D-K19e-β-01) — batch-resolve chapter titles.

        Fires one POST to ``/internal/chapters/titles`` and returns a
        dict mapping ``UUID → "Chapter N — Title"``. Used by the
        knowledge-service Timeline + Jobs responses to denormalize
        chapter titles inline so the FE can render
        "Chapter 12 — The Bridge Duel" instead of ``…last8chars``.

        Graceful on every failure path: returns ``{}`` so callers
        render the UUID-suffix fallback via the existing
        ``chapterShort()`` helper. Empty input short-circuits without
        a network call.
        """
        if not chapter_ids:
            return {}
        url = f"{self._base_url}/internal/chapters/titles"
        tid = trace_id_var.get()
        try:
            resp = await self._http.post(
                url,
                json={"chapter_ids": [str(cid) for cid in chapter_ids]},
                headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return {}
            data = resp.json()
            titles = data.get("titles") or {}
            result: dict[UUID, str] = {}
            for k, v in titles.items():
                try:
                    result[UUID(k)] = str(v)
                except (ValueError, TypeError):
                    # Skip any key that isn't a valid UUID — defensive
                    # against a future BE drift. The caller falls back
                    # to the UUID short for that event.
                    continue
            return result
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable fetching chapter titles: %s trace_id=%s",
                exc, tid,
            )
            return {}

    async def get_chapter_sort_orders(
        self, chapter_ids: list[UUID],
    ) -> dict[UUID, int]:
        """C12a (D-K16.2-02b) — batch-resolve chapter sort_orders.

        Fires one POST to ``/internal/chapters/sort-orders`` and returns
        a dict mapping ``UUID → sort_order``. Used by the knowledge-
        service chapter.saved event handler to honour running jobs'
        ``scope_range.chapter_range`` filter — if the chapter's
        sort_order is outside every active job's range, the handler
        skips ingestion.

        Graceful on every failure path: returns ``{}`` so the caller
        over-ingests defensively (we don't want to silently skip valid
        chapters because book-service was briefly unavailable).
        Empty input short-circuits without a network call.
        """
        if not chapter_ids:
            return {}
        url = f"{self._base_url}/internal/chapters/sort-orders"
        tid = trace_id_var.get()
        try:
            resp = await self._http.post(
                url,
                json={"chapter_ids": [str(cid) for cid in chapter_ids]},
                headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return {}
            data = resp.json()
            sort_orders = data.get("sort_orders") or {}
            result: dict[UUID, int] = {}
            for k, v in sort_orders.items():
                try:
                    result[UUID(k)] = int(v)
                except (ValueError, TypeError):
                    # Skip any non-UUID key or non-int value — defensive
                    # against BE drift; caller over-ingests for missing.
                    continue
            return result
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable fetching chapter sort orders: %s trace_id=%s",
                exc, tid,
            )
            return {}

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
