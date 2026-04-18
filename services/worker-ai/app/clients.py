"""HTTP clients for worker-ai.

Two clients:
  - KnowledgeClient: calls POST /internal/extraction/extract-item
  - BookClient: calls GET /internal/books/{book_id}/chapters and
    GET /internal/books/{book_id}/chapters/{chapter_id}

Both use graceful degradation: return None on failure, let the caller
decide whether to retry or fail the job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

__all__ = ["BookClient", "KnowledgeClient", "ExtractionResult", "ChapterInfo"]

logger = logging.getLogger(__name__)


# ── Data types ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtractionResult:
    """Parsed response from POST /internal/extraction/extract-item."""
    source_id: str
    entities_merged: int
    relations_created: int
    events_merged: int
    facts_merged: int
    retryable: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ChapterInfo:
    """Minimal chapter metadata from book-service."""
    chapter_id: str
    title: str
    sort_order: int


# ── KnowledgeClient ──────────────────────────────────────────────────


class KnowledgeClient:
    """Calls knowledge-service's internal extraction endpoint."""

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def extract_item(
        self,
        *,
        user_id: UUID,
        project_id: UUID | None,
        item_type: str,
        source_type: str,
        source_id: str,
        job_id: UUID,
        model_source: str,
        model_ref: str,
        chapter_text: str | None = None,
        user_message: str | None = None,
        assistant_message: str | None = None,
        known_entities: list[str] | None = None,
    ) -> ExtractionResult:
        """Call POST /internal/extraction/extract-item.

        Returns an ExtractionResult. On HTTP error, returns a result
        with error set and retryable flag based on status code.
        """
        url = f"{self._base_url}/internal/extraction/extract-item"
        body: dict = {
            "user_id": str(user_id),
            "project_id": str(project_id) if project_id else None,
            "item_type": item_type,
            "source_type": source_type,
            "source_id": source_id,
            "job_id": str(job_id),
            "model_source": model_source,
            "model_ref": model_ref,
            "known_entities": known_entities or [],
        }
        if chapter_text is not None:
            body["chapter_text"] = chapter_text
        if user_message is not None:
            body["user_message"] = user_message
        if assistant_message is not None:
            body["assistant_message"] = assistant_message

        try:
            resp = await self._http.post(url, json=body)
        except httpx.HTTPError as exc:
            logger.warning("extract-item HTTP error: %s", exc)
            return ExtractionResult(
                source_id=source_id, retryable=True,
                error=f"HTTP error: {exc}",
            )

        if resp.status_code == 200:
            data = resp.json()
            return ExtractionResult(
                source_id=data.get("source_id", source_id),
                entities_merged=data.get("entities_merged", 0),
                relations_created=data.get("relations_created", 0),
                events_merged=data.get("events_merged", 0),
                facts_merged=data.get("facts_merged", 0),
            )

        # Structured error from K16.6a
        try:
            detail = resp.json().get("detail", {})
            if isinstance(detail, dict):
                return ExtractionResult(
                    source_id=source_id,
                    retryable=detail.get("retryable", resp.status_code == 502),
                    error=detail.get("error", f"HTTP {resp.status_code}"),
                )
        except Exception:
            pass

        return ExtractionResult(
            source_id=source_id,
            retryable=resp.status_code in (502, 503, 429),
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )


# ── BookClient ───────────────────────────────────────────────────────


class BookClient:
    """Calls book-service's internal API for chapter data."""

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def list_chapters(self, book_id: UUID) -> list[ChapterInfo] | None:
        """GET /internal/books/{book_id}/chapters — returns all chapters.

        Returns None on failure.
        """
        url = f"{self._base_url}/internal/books/{book_id}/chapters?limit=1000"
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                logger.warning("book-service chapters %d for %s", resp.status_code, book_id)
                return None
            data = resp.json()
            return [
                ChapterInfo(
                    chapter_id=item["chapter_id"],
                    title=item.get("title") or "",
                    sort_order=item.get("sort_order", 0),
                )
                for item in data.get("items", [])
            ]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("book-service chapters failed: %s", exc)
            return None

    async def get_chapter_text(self, book_id: UUID, chapter_id: str) -> str | None:
        """GET /internal/books/{book_id}/chapters/{chapter_id} — returns chapter with text.

        Returns the plain text content or None on failure.
        """
        url = f"{self._base_url}/internal/books/{book_id}/chapters/{chapter_id}"
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                logger.warning("book-service chapter %s: %d", chapter_id, resp.status_code)
                return None
            data = resp.json()
            # Book-service returns aggregated plain text in text_content
            # (from chapter_blocks). body is the JSON draft format.
            return data.get("text_content") or None
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("book-service chapter text failed: %s", exc)
            return None
