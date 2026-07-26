"""C1 DPS-B — read-only book-service client.

Reads source hierarchy via GET /internal/books/{book_id}/chapters/{chapter_id}/
hierarchy (X-Internal-Token). WRITES NOTHING. Chapter/scene titles are
CJK-safe and passed through `neutralize_injection` (M4) since they originate
from author-supplied source text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
from loreweave_internal_client import InternalClientError, build_internal_client

from app.clients.sanitize import neutralize_injection
from app.logging_config import trace_id_var

__all__ = [
    "BookProjection",
    "ChapterMeta",
    "ChapterHierarchy",
    "BookServiceError",
    "BookClient",
]


# P3 SDK-first: subclass the shared InternalClientError so `.retryable` is derived
# uniformly from `.status_code` (429/502/503) instead of re-computed per raise site.
# Name kept so `except BookServiceError` call sites are unchanged.
class BookServiceError(InternalClientError):
    pass


@dataclass(frozen=True)
class BookProjection:
    """Book metadata seed for AI-suggest (C3). The author-supplied prose
    (title/description/summary) is injection-neutralized (M4)."""

    book_id: UUID
    owner_user_id: UUID | None = None
    title: str = ""
    original_language: str = ""
    description: str = ""
    summary_excerpt: str = ""
    genre_tags: list[str] = field(default_factory=list)
    chapter_count: int = 0


@dataclass(frozen=True)
class ChapterMeta:
    """One chapter row for the selection picker / suggest sampling (C3)."""

    chapter_id: UUID
    title: str = ""
    sort_order: int = 0
    original_language: str = ""
    word_count_estimate: int = 0


@dataclass(frozen=True)
class ChapterHierarchy:
    book_id: UUID
    chapter_id: UUID
    chapter_title: str = ""
    part_title: str | None = None
    scene_titles: list[str] = field(default_factory=list)


class BookClient:
    def __init__(self, *, base_url: str, internal_token: str, timeout_s: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        # W3 trace-uniformity: the shared factory bakes X-Internal-Token + JSON and
        # injects X-Trace-Id per request (this client had NO trace before).
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, connect_timeout_s=5.0,
            trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_projection(self, *, book_id: UUID) -> BookProjection:
        """Book metadata for AI-suggest (C3). Reads GET /internal/books/{id}/
        projection (owner + title/language/description/summary/genre_tags/count).
        Author-prose fields are injection-neutralized (M4). 404 → typed not-found."""
        url = f"{self._base}/internal/books/{book_id}/projection"
        try:
            resp = await self._http.get(url)
        except httpx.TimeoutException as exc:
            raise BookServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise BookServiceError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code != 200:
            raise BookServiceError(
                f"GET {url} failed ({resp.status_code})",
                status_code=resp.status_code,
            )
        data = resp.json()
        tags = data.get("genre_tags") or []
        owner = data.get("owner_user_id")
        return BookProjection(
            book_id=book_id,
            owner_user_id=UUID(str(owner)) if owner else None,
            title=neutralize_injection(data.get("title")),
            original_language=str(data.get("original_language") or ""),
            description=neutralize_injection(data.get("description")),
            summary_excerpt=neutralize_injection(data.get("summary_excerpt")),
            genre_tags=[neutralize_injection(t) for t in tags if isinstance(t, str)],
            chapter_count=int(data.get("chapter_count") or 0),
        )

    async def list_chapters(
        self, *, book_id: UUID, limit: int = 200, offset: int = 0
    ) -> tuple[list[ChapterMeta], int]:
        """The book's chapter list for the selection picker + suggest sampling.
        Reads GET /internal/books/{id}/chapters. Titles are injection-neutralized
        (M4). Returns (items, total). 404 → typed not-found."""
        url = f"{self._base}/internal/books/{book_id}/chapters"
        try:
            resp = await self._http.get(url, params={"limit": limit, "offset": offset})
        except httpx.TimeoutException as exc:
            raise BookServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise BookServiceError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code != 200:
            raise BookServiceError(
                f"GET {url} failed ({resp.status_code})",
                status_code=resp.status_code,
            )
        data = resp.json()
        items: list[ChapterMeta] = []
        for row in data.get("items") or []:
            if not isinstance(row, dict) or not row.get("chapter_id"):
                continue
            items.append(ChapterMeta(
                chapter_id=UUID(str(row["chapter_id"])),
                title=neutralize_injection(row.get("title")),
                sort_order=int(row.get("sort_order") or 0),
                original_language=str(row.get("original_language") or ""),
                word_count_estimate=int(row.get("word_count_estimate") or 0),
            ))
        return items, int(data.get("total") or 0)

    async def get_chapter_text(self, *, book_id: UUID, chapter_id: UUID) -> str:
        """The chapter's draft text (de-bias C2 T6 — author-selected grounding).

        Reads GET /internal/books/{book_id}/chapters/{chapter_id}/draft-text. The
        text is author-supplied source → injection-neutralized (M4). Returns '' for
        an empty/missing chapter (the caller skips it)."""
        url = f"{self._base}/internal/books/{book_id}/chapters/{chapter_id}/draft-text"
        try:
            resp = await self._http.get(url)
        except httpx.TimeoutException as exc:
            raise BookServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise BookServiceError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code == 404:
            return ""
        if resp.status_code != 200:
            raise BookServiceError(
                f"GET {url} failed ({resp.status_code})",
                status_code=resp.status_code,
            )
        data = resp.json()
        raw = data.get("text") or data.get("content") or data.get("draft") or ""
        return neutralize_injection(raw)

    async def get_chapter_hierarchy(
        self, *, book_id: UUID, chapter_id: UUID
    ) -> ChapterHierarchy:
        url = f"{self._base}/internal/books/{book_id}/chapters/{chapter_id}/hierarchy"
        try:
            resp = await self._http.get(url)
        except httpx.TimeoutException as exc:
            raise BookServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise BookServiceError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code != 200:
            raise BookServiceError(
                f"GET {url} failed ({resp.status_code})",
                status_code=resp.status_code,
            )
        data = resp.json()
        chapter = data.get("chapter") or {}
        part = data.get("part")
        scenes = data.get("scenes") or []
        return ChapterHierarchy(
            book_id=book_id,
            chapter_id=chapter_id,
            chapter_title=neutralize_injection(chapter.get("title")),
            part_title=neutralize_injection(part.get("title")) if isinstance(part, dict) else None,
            scene_titles=[
                neutralize_injection(s.get("title"))
                for s in scenes
                if isinstance(s, dict)
            ],
        )
