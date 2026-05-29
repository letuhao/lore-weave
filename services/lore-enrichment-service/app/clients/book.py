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

from app.clients.sanitize import neutralize_injection

__all__ = [
    "ChapterHierarchy",
    "BookServiceError",
    "BookClient",
]


class BookServiceError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


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
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_chapter_hierarchy(
        self, *, book_id: UUID, chapter_id: UUID
    ) -> ChapterHierarchy:
        url = f"{self._base}/internal/books/{book_id}/chapters/{chapter_id}/hierarchy"
        try:
            resp = await self._http.get(
                url, headers={"X-Internal-Token": self._internal_token}
            )
        except httpx.TimeoutException as exc:
            raise BookServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise BookServiceError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code != 200:
            retryable = resp.status_code in (502, 503, 429)
            raise BookServiceError(
                f"GET {url} failed ({resp.status_code})",
                retryable=retryable,
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
