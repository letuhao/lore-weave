"""book-service client (composition-service, M3 — prose-source + ownership).

Decision B: composition's prose-source proxies book-service's canonical chapter
DRAFT content + revisions. Contract-verified 2026-06-04 (book-service
server.go): the draft read/write are **PUBLIC JWT-only** (no internal variant),
so this client **forwards the caller's `Authorization: Bearer`** and book-service
enforces ownership inside its SQL (`JOIN books b ... owner_user_id`) — a
non-owner gets 404. So for the prose path the SEC2 ownership chokepoint is
book-service's own concern; composition just forwards.

`owns_book` (GET /v1/books/{id}, 404 for non-owner) is the SEC2 primitive the
M4 packer will call BEFORE issuing INTERNAL glossary/knowledge reads (those use
X-Internal-Token and do NOT check the user).

Errors: 2xx → parsed JSON; any non-2xx or transport failure → BookClientError
carrying the status + book-service error code so the prose router can map it
(404 → 404, 409 CHAPTER_DRAFT_CONFLICT → 409, else → 502).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

_client: "BookClient | None" = None


class BookClientError(Exception):
    """Non-2xx or transport failure from book-service. `status` is the HTTP
    status (502 for a transport error); `code` is book-service's error code
    string when present (e.g. CHAPTER_DRAFT_CONFLICT, CHAPTER_NOT_FOUND)."""

    def __init__(self, status: int, code: str | None, detail: str | None = None) -> None:
        super().__init__(f"book-service {status} {code or ''}".strip())
        self.status = status
        self.code = code
        self.detail = detail


def _auth_headers(bearer: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {bearer}"}
    tid = trace_id_var.get()
    if tid:
        headers["X-Trace-Id"] = tid
    return headers


class BookClient:
    def __init__(self, base_url: str, internal_token: str = "", timeout_s: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self, method: str, path: str, bearer: str, *,
        json: dict[str, Any] | None = None, params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            return await self._http.request(
                method, url, headers=_auth_headers(bearer), json=json, params=params,
            )
        except httpx.HTTPError as exc:
            logger.warning("book-service unreachable: %s %s err=%s", method, url, exc)
            raise BookClientError(502, "BOOK_SERVICE_UNAVAILABLE", str(exc)) from exc

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> dict[str, Any]:
        if 200 <= resp.status_code < 300:
            return resp.json()
        code: str | None = None
        detail: str | None = None
        try:
            body = resp.json()
            code = body.get("error") or body.get("code")
            detail = body.get("message") or body.get("detail")
        except (ValueError, AttributeError):
            pass
        raise BookClientError(resp.status_code, code, detail)

    async def owns_book(self, book_id: UUID, bearer: str) -> bool:
        """SEC2 primitive: does the JWT user own this book? 200 → True, 404 →
        False (book-service returns 404 for both missing and not-owned — no
        enumeration leak). Other statuses / transport → BookClientError."""
        resp = await self._request("GET", f"/v1/books/{book_id}", bearer)
        if resp.status_code == 404:
            return False
        self._raise_for_status(resp)
        return True

    async def get_book(self, book_id: UUID, bearer: str) -> dict[str, Any] | None:
        """The book object (title etc.) for the JWT user, or None if not owned /
        missing (404). Used by POST /work to name the knowledge project + as the
        ownership gate. Raises BookClientError on 5xx / transport."""
        resp = await self._request("GET", f"/v1/books/{book_id}", bearer)
        if resp.status_code == 404:
            return None
        return self._raise_for_status(resp)

    async def get_draft(
        self, book_id: UUID, chapter_id: UUID, bearer: str
    ) -> dict[str, Any]:
        """Current draft content + `draft_version` (the OI-2 concurrency token)."""
        resp = await self._request(
            "GET", f"/v1/books/{book_id}/chapters/{chapter_id}/draft", bearer,
        )
        return self._raise_for_status(resp)

    async def patch_draft(
        self, book_id: UUID, chapter_id: UUID, bearer: str, *,
        body: Any, expected_draft_version: int,
        body_format: str | None = None, commit_message: str | None = None,
    ) -> dict[str, Any]:
        """Write the DRAFT only (book-service emits chapter.saved, never
        chapter.published — canonization is the separate /publish call).
        `expected_draft_version` is REQUIRED here (the router enforces its
        presence) → book-service returns 409 CHAPTER_DRAFT_CONFLICT on a stale
        version (OI-2/PS2). Omitting it would be a blind clobber, which is why
        this signature makes it non-optional."""
        payload: dict[str, Any] = {"body": body, "expected_draft_version": expected_draft_version}
        if body_format is not None:
            payload["body_format"] = body_format
        if commit_message is not None:
            payload["commit_message"] = commit_message
        resp = await self._request(
            "PATCH", f"/v1/books/{book_id}/chapters/{chapter_id}/draft", bearer,
            json=payload,
        )
        return self._raise_for_status(resp)

    async def get_chapter_sort_orders(
        self, chapter_ids: list[UUID],
    ) -> dict[str, int]:
        """Map chapter_id → reading-order `sort_order` (the M4 packer's L4
        reading-position spoiler axis + the scene's cutoff). Uses the INTERNAL
        token (book-scoped, no user check) — the caller MUST have verified book
        ownership first (SEC2 owns_book chokepoint). Batched ≤200 per call;
        missing/inactive ids are silently absent from the map. Returns {} on any
        failure (the packer treats an absent position as conservative-drop)."""
        if not chapter_ids:
            return {}
        url = f"{self._base_url}/internal/chapters/sort-orders"
        headers = {"X-Internal-Token": self._internal_token}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        try:
            resp = await self._http.post(
                url, json={"chapter_ids": [str(c) for c in chapter_ids]}, headers=headers,
            )
            if resp.status_code != 200:
                logger.warning("book sort-orders → %d", resp.status_code)
                return {}
            return resp.json().get("sort_orders", {})
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("book sort-orders unavailable: %s", exc)
            return {}

    async def list_parts_mirror(self, book_id: UUID) -> list[dict[str, Any]]:
        """C-merge C2 — a book's ACTIVE parts for the structure_node mirror consumer. INTERNAL token
        (no user check — a trusted mirror reconcile, works for a Work-less book). RAISES BookClientError
        on transport/non-200 so the consumer RETRIES rather than reconciling-to-empty (which would blank
        a real book's part groupings — the scenes_linked BookSceneFetchError discipline)."""
        url = f"{self._base_url}/internal/books/{book_id}/parts-mirror"
        headers = {"X-Internal-Token": self._internal_token}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        try:
            resp = await self._http.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise BookClientError(502, "BOOK_SERVICE_UNAVAILABLE", str(exc)) from exc
        if resp.status_code != 200:
            raise BookClientError(resp.status_code, None, "parts-mirror failed")
        return resp.json().get("parts", [])

    async def canon_markers(
        self, book_id: UUID, chapter_ids: list[UUID],
    ) -> dict[str, dict[str, Any]]:
        """26 IX-9 — batch chapter canon/index markers for the conformance-staleness
        read: `{chapter_id: {published_revision_id, kg_indexed_revision_id, kg_exclude,
        last_parsed_revision_id, parse_version, editorial_status}}`
        (parse_version = the IX-4 chapter scalar).

        WS-0.7: `kg_indexed_revision_id` + `kg_exclude` are what make the post-WS-0.5
        staleness predicate expressible here at all. `_dirty_reasons` mirrors the
        book-service sweeper's WHERE clause in Python, and the sweeper now keys on the
        KG pointer — so without these two fields this service would keep evaluating the
        OLD predicate and render a permanently-stuck `index_stale` badge on any chapter
        that is published@A but indexed@B.
        Calls book-service's INTERNAL batch route
        `POST /internal/books/{book_id}/chapters/canon-markers` (B5, mirrors
        `/internal/chapters/sort-orders` — ≤200 ids, partial responses,
        missing/inactive ids silently absent). Uses the INTERNAL token (book-scoped,
        no user check); the CALLER MUST have gated the book first — the conformance
        status route's E0 VIEW gate is that SEC2 chokepoint (same discipline as
        `get_chapter_sort_orders`). Returns {} on ANY non-200 / transport failure: a
        degraded markers read renders conformance freshness conservatively (a snapshot
        reads `fresh`/`never_run`), never 500s the Hub."""
        if not chapter_ids:
            return {}
        url = f"{self._base_url}/internal/books/{book_id}/chapters/canon-markers"
        headers = {"X-Internal-Token": self._internal_token}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        try:
            resp = await self._http.post(
                url, json={"chapter_ids": [str(c) for c in chapter_ids]}, headers=headers,
            )
            if resp.status_code != 200:
                logger.warning("book canon-markers → %d", resp.status_code)
                return {}
            body = resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("book canon-markers unavailable: %s", exc)
            return {}
        # Contract (IX-9): the map rides under `markers` (mirrors sort-orders' named
        # field). Tolerate `canon_markers` + a bare {chapter_id: {...}} body so a benign
        # producer-side field-name choice degrades to a normalized read, never a crash.
        if isinstance(body, dict):
            for key in ("markers", "canon_markers"):
                inner = body.get(key)
                if isinstance(inner, dict):
                    return inner
            if body and all(isinstance(v, dict) for v in body.values()):
                return body
        return {}

    async def get_reader_language(self, book_id: UUID, user_id: UUID) -> str | None:
        """KG-ML M7 (C6) — the user's stored reader-language for this book (M3),
        via the INTERNAL resolver `GET /internal/books/{id}/reader-language?user_id=`
        (token-gated, book-scoped). Used by the packer to request grounding context
        in the author's language (per-language glossary aliases + vi-first lore).
        Best-effort: returns None when unset / on ANY failure — the pack just stays
        source-language (never 500s a generate)."""
        url = f"{self._base_url}/internal/books/{book_id}/reader-language"
        headers = {"X-Internal-Token": self._internal_token}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        try:
            resp = await self._http.get(
                url, params={"user_id": str(user_id)}, headers=headers,
            )
            if resp.status_code != 200:
                return None
            lang = resp.json().get("reader_language")
            return lang or None
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("book reader-language unavailable: %s", exc)
            return None

    async def create_chapter(
        self, book_id: UUID, bearer: str, *, title: str, original_language: str,
    ) -> dict[str, Any]:
        """Create a real Chapter row (PlanForge auto-bootstrap POC — see
        docs/specs/2026-07-06-planforge-auto-bootstrap.md §3.1 [A]).
        Deliberately never sends `sort_order`: book-service's handler
        (server.go:1467-1469) auto-assigns `MAX(sort_order)+1` for the book
        when it's omitted, so a non-empty book is safe by construction — no
        ordinal-collision logic needed on this side. Bearer-forwarded (public
        JWT route, same as `publish_chapter`/`patch_draft`); book-service
        enforces ownership in SQL. Raises BookClientError on any non-2xx."""
        resp = await self._request(
            "POST", f"/v1/books/{book_id}/chapters", bearer,
            json={"title": title, "original_language": original_language},
        )
        return self._raise_for_status(resp)

    async def publish_chapter(
        self, book_id: UUID, chapter_id: UUID, bearer: str,
    ) -> dict[str, Any]:
        """Canonize the chapter draft (Canon Model CM1: draft → published). POSTs
        to book-service's public `/publish` route (JWT-only — book-service enforces
        ownership in SQL on the JWT `sub`). Used by the S-COMPOSE Tier-W
        `composition_publish` confirm path. Raises BookClientError on any non-2xx /
        transport (e.g. 409 if there is no draft revision to pin)."""
        resp = await self._request(
            "POST", f"/v1/books/{book_id}/chapters/{chapter_id}/publish", bearer,
        )
        return self._raise_for_status(resp)

    async def list_revisions(
        self, book_id: UUID, chapter_id: UUID, bearer: str, *, limit: int = 1,
    ) -> dict[str, Any]:
        """Revisions newest-first (created_at DESC) → items[0].revision_id is the
        latest = the draft's base_revision_id (the draft read doesn't expose it)."""
        resp = await self._request(
            "GET", f"/v1/books/{book_id}/chapters/{chapter_id}/revisions", bearer,
            params={"limit": limit},
        )
        return self._raise_for_status(resp)

    async def restore_revision(
        self, book_id: UUID, chapter_id: UUID, revision_id: UUID, bearer: str,
    ) -> dict[str, Any]:
        """RAID D3 reject/Revert-All — roll the chapter draft back to a prior
        revision via book-service's public restore route (GrantEdit, JWT `sub`).
        Non-destructive on their side: book-service first snapshots the CURRENT
        draft as a new 'before restore' revision, then writes the target
        revision's body to the draft (draft_version+1, chapter.saved emitted).
        Same bearer discipline as the other public routes — the CALLER's bearer
        (the owner clicked reject). Raises BookClientError on any non-2xx /
        transport (the caller must NOT mark the unit rejected in that case)."""
        resp = await self._request(
            "POST",
            f"/v1/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/restore",
            bearer,
        )
        return self._raise_for_status(resp)

    async def reorder_chapters(
        self, book_id: UUID, chapter_id: UUID, after_chapter_id: UUID | None, bearer: str,
    ) -> dict[str, Any]:
        """24 PH20 Row-3 — move a chapter in the book's READING order (book-service owns it).

        Places `chapter_id` directly AFTER `after_chapter_id` (None ⇒ first). book-service does the
        whole renumber in one transaction — it is the only thing that can, because the partial
        UNIQUE slot index forbids writing a permutation row-by-row. Returns the new dense sequence.

        A 400/404/409 is book-service's own rule (unknown chapter, an after_id from another book, a
        non-active lifecycle) and is re-raised for the caller to relay verbatim, never flattened."""
        resp = await self._request(
            "POST", f"/v1/books/{book_id}/chapters/reorder", bearer,
            json={
                "chapter_id": str(chapter_id),
                "after_chapter_id": str(after_chapter_id) if after_chapter_id else None,
            },
        )
        return self._raise_for_status(resp)

    # book-service parseLimitOffset CLAMPS limit to 100 (server.go) — asking for
    # more silently returns 100, so a full listing must paginate by offset.
    _CHAPTERS_PAGE_LIMIT = 100

    async def list_chapters(
        self, book_id: UUID, bearer: str, *, limit: int = 2000,
        raise_on_404: bool = False,
    ) -> list[dict[str, Any]]:
        """The book's ACTIVE chapters in reading order (`sort_order,
        created_at`), each `{chapter_id, title, sort_order}` — the A3 planner's
        enumerate-then-map source AND the authoring-run gate's scope-membership
        truth. Paginates in 100-chapter pages (book-service clamps any larger
        page limit to 100 — a single request can NEVER see a >100-chapter book
        whole) until a short page or `limit` total rows.

        `limit` is a REAL CEILING, not a page size: a book with more chapters than
        `limit` comes back TRUNCATED, silently. Callers that must be exhaustive
        (the coverage diff, whose whole contract is an exact count) have to pass a
        limit above the book's size and check — see `coverage.py`.

        404 (book missing / not owned) → `[]` by default, because the original
        callers had already gated the Work and treat it as "no chapters". That
        default is DANGEROUS for anyone who reasons about ABSENCE: a 404 then reads
        as a confirmed-empty book. `raise_on_404=True` makes it a BookClientError
        so such a caller can degrade instead of reporting a green-looking zero.
        5xx / transport → BookClientError always. `title` may be null → ''."""
        out: list[dict[str, Any]] = []
        offset = 0
        while len(out) < limit:
            resp = await self._request(
                "GET", f"/v1/books/{book_id}/chapters", bearer,
                params={
                    "limit": self._CHAPTERS_PAGE_LIMIT,
                    "offset": offset,
                    "lifecycle_state": "active",
                },
            )
            if resp.status_code == 404:
                if raise_on_404:
                    raise BookClientError(404, "BOOK_NOT_FOUND")
                return []
            body = self._raise_for_status(resp)
            items = body.get("items", []) or []
            for it in items:
                out.append({
                    "chapter_id": it.get("chapter_id"),
                    "title": it.get("title") or "",
                    "sort_order": it.get("sort_order"),
                })
            if len(items) < self._CHAPTERS_PAGE_LIMIT:
                break
            offset += len(items)
        return out[:limit]


def init_book_client() -> BookClient:
    global _client
    if _client is None:
        _client = BookClient(settings.book_internal_url, settings.internal_service_token)
    return _client


def get_book_client() -> BookClient:
    return _client or init_book_client()


async def close_book_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
