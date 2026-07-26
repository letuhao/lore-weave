"""Internal client for book-service (ownership verify + chapter enumeration).

Mirrors the worker-ai / knowledge-service BookClient: a single httpx client with
the shared `X-Internal-Token` header baked in at construction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx
from loreweave_internal_client import InternalClientError

logger = logging.getLogger(__name__)


class BookServiceError(InternalClientError):
    """book-service unreachable or returned an unexpected status.

    P3 SDK-first W2-tail: subclasses the shared InternalClientError so a caller can
    uniformly inspect `.status_code`/`.retryable` (429/502/503) — additive; the
    non-2xx raise sites thread `status_code`, transport errors leave it None."""


class BookNotFound(Exception):
    """The book does not exist."""


class BookIsDiary(Exception):
    """P-1 / D-R19 — the target is a kind='diary' book. A campaign (batch translation) must NEVER
    run on a private diary — it would ship the user's diary content to a translation provider. The
    caller maps this to a 403 (not a 502/404)."""


@dataclass(frozen=True)
class ChapterRef:
    chapter_id: str
    sort_order: int
    # S5a — raw chapter size, used by the cost estimate to size source tokens.
    # 0 when the book-service projection omits it (estimate falls back to a
    # configured per-chapter average).
    byte_size: int = 0


class BookClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_owner_user_id(self, book_id: UUID) -> str:
        """Return the book's owner_user_id. Raises BookNotFound (404) or
        BookServiceError (network / non-2xx)."""
        url = f"{self._base_url}/internal/books/{book_id}/projection"
        try:
            resp = await self._http.get(url)
        except httpx.RequestError as exc:
            raise BookServiceError(str(exc)) from exc
        if resp.status_code == 404:
            raise BookNotFound(str(book_id))
        if not resp.is_success:
            raise BookServiceError(
                f"projection {resp.status_code}", status_code=resp.status_code,
            )
        body = resp.json()
        owner = body.get("owner_user_id")
        if not owner:
            raise BookServiceError("projection missing owner_user_id")
        # P-1 / D-R19 — a campaign must NEVER run on a private diary (kind='diary'), which would
        # batch-translate the user's diary and ship it to a provider. The projection carries `kind`
        # (WS-1.2 egress-guard contract); this is the ONE resolution chokepoint both create+estimate
        # pass through, so the guard holds for both.
        if body.get("kind") == "diary":
            raise BookIsDiary(str(book_id))
        return str(owner)

    async def list_indexed_chapters(self, book_id: UUID) -> list[ChapterRef]:
        """P-1 / D-R19 — enumerate the book's KG-INDEXED chapters (was published-only; the human
        chose platform consistency with the WS-0.6 publish-independent KG work: a chapter is
        translatable once the user has INDEXED it, not only once published). Returns [] on an empty
        book; raises on failure. (Diaries are already refused at owner-resolution.)"""
        url = f"{self._base_url}/internal/books/{book_id}/chapters?limit=1000&kg_indexed=true"
        try:
            resp = await self._http.get(url)
        except httpx.RequestError as exc:
            raise BookServiceError(str(exc)) from exc
        if not resp.is_success:
            raise BookServiceError(
                f"chapters {resp.status_code}", status_code=resp.status_code,
            )
        items = resp.json().get("items", [])
        return [
            ChapterRef(
                chapter_id=str(it["chapter_id"]),
                sort_order=int(it.get("sort_order", 0)),
                byte_size=int(it.get("byte_size", 0) or 0),
            )
            for it in items
        ]
