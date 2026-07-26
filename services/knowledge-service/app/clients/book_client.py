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
from loreweave_internal_client import build_internal_client

from app.config import settings
from app.logging_config import trace_id_var

__all__ = [
    "BookClient",
    "init_book_client",
    "get_book_client",
    "WorldNotFound",
    "BookServiceUnavailable",
]

logger = logging.getLogger(__name__)


class WorldNotFound(Exception):
    """The world does not exist or is not owned by the requesting user
    (book-service returned 404). The world-rollup endpoint maps this to a
    uniform 404 — no existence oracle."""


class BookServiceUnavailable(Exception):
    """book-service was unreachable or errored resolving world membership
    (transport error / 5xx). The world-rollup endpoint maps this to 503 —
    distinct from 404 so the FE can tell "no such world" from "try later"."""

_client: "BookClient | None" = None


class BookClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # W3: shared factory bakes X-Internal-Token + JSON + per-request X-Trace-Id
        # (trace_id_var). The local `tid` reads remain for the log lines.
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_book_kind(self, book_id: UUID, user_id: UUID) -> str | None:
        """WS-1.4 — the book's ``kind`` ('novel'|'document'|'lore'|'diary'), or None on any
        failure. Reads book-service's grant-gated ``GET /internal/books/{id}/access?user_id=``
        (``kind`` rides that response behind a grant, WS-1.2 D16). Used to enforce that the
        assistant knowledge project binds ONLY to a diary — anchoring it to a shareable novel
        would let a collaborator read the assistant's private memory. Returns None (fail-safe)
        when the book is unreachable/not visible; the caller must treat None as 'not a diary'
        and refuse."""
        url = f"{self._base_url}/internal/books/{book_id}/access"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(url, params={"user_id": str(user_id)})
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d (kind unknown → treat as non-diary), trace_id=%s",
                    url, resp.status_code, tid,
                )
                return None
            kind = resp.json().get("kind")
            return kind if isinstance(kind, str) else None
        except (httpx.HTTPError, ValueError, KeyError):
            logger.warning("book-service kind fetch failed (→ non-diary), trace_id=%s", tid)
            return None

    async def count_chapters(
        self,
        book_id: UUID,
        *,
        from_sort: int | None = None,
        to_sort: int | None = None,
        editorial_status: str | None = None,
        kg_indexed: bool = False,
    ) -> int | None:
        """Return the number of active chapters for a book.

        Optional ``from_sort`` / ``to_sort`` scope the count to an
        inclusive range of ``sort_order`` values. Passing ``None`` for
        either leaves that end unbounded. D-K16.2-02 — used by the
        extraction estimate endpoint so users previewing "chapters
        10–20 only" see the range count rather than the whole book.

        WS-0.6 — the extraction cost-estimate passes ``kg_indexed=True`` so the
        preview count matches what the re-keyed whole-book rebuild actually
        extracts. The SAME server-side filter backs the worker enumeration
        (worker-ai ``list_chapters(kg_indexed=True)``), so estimate and
        enumeration cannot diverge (R1-BLOCK#1, restated against the new gate).

        This replaces the old CM3c ``editorial_status='published'`` gate:
        publishing no longer decides KG membership, so a preview keyed on it
        would report "0 chapters" for a user who indexed 50 drafts.

        ``editorial_status`` is kept for the callers that legitimately still ask
        the publish question.

        Returns None on any failure (timeout, connection error, bad
        response) — the caller decides how to handle missing data.
        """
        params: dict[str, str] = {"limit": "1"}
        if from_sort is not None:
            params["from_sort"] = str(from_sort)
        if to_sort is not None:
            params["to_sort"] = str(to_sort)
        if editorial_status is not None:
            params["editorial_status"] = editorial_status
        if kg_indexed:
            params["kg_indexed"] = "true"
        url = f"{self._base_url}/internal/books/{book_id}/chapters"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url,
                params=params,
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

    # book-service clamps page size to 100 (chapter-list-limit100 fix), so we
    # paginate. The cap bounds a runaway loop / pathological book; a book at the
    # cap is logged rather than silently truncated.
    _LIST_CHAPTERS_PAGE = 100
    _LIST_CHAPTERS_MAX = 5000

    async def list_chapters(
        self,
        book_id: UUID,
        *,
        editorial_status: str | None = None,
        kg_indexed: bool = False,
    ) -> list[dict] | None:
        """D-RAWSEARCH-CANON-WIRING — list ALL a book's chapters (id + sort_order +
        editorial_status + kg_indexed_revision_id + kg_exclude) via
        ``GET /internal/books/{book_id}/chapters``, paging past book-service's 100-row
        clamp so a >100-chapter book isn't silently truncated.

        ``editorial_status='draft'`` scopes to unpublished chapters (what the on-demand
        draft-indexing endpoint enumerates).

        WS-0.6: ``kg_indexed=True`` scopes to the chapters that are IN the knowledge
        graph (``kg_indexed_revision_id IS NOT NULL AND NOT kg_exclude``) — the gate the
        passage backfill/ingester enumerate on. It is a DIFFERENT question from
        ``editorial_status``: publishing no longer decides KG membership.

        Returns the full item list, or None on any failure (caller decides)."""
        url = f"{self._base_url}/internal/books/{book_id}/chapters"
        tid = trace_id_var.get()
        collected: list[dict] = []
        offset = 0
        try:
            while True:
                params: dict[str, str] = {
                    "limit": str(self._LIST_CHAPTERS_PAGE),
                    "offset": str(offset),
                }
                if editorial_status is not None:
                    params["editorial_status"] = editorial_status
                if kg_indexed:
                    params["kg_indexed"] = "true"
                resp = await self._http.get(
                    url,
                    params=params,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "book-service %s returned %d, trace_id=%s",
                        url, resp.status_code, tid,
                    )
                    return None
                body = resp.json()
                items = body.get("items", [])
                if not isinstance(items, list):
                    return None
                collected.extend(items)
                total = int(body.get("total", len(collected)))
                offset += self._LIST_CHAPTERS_PAGE
                if len(collected) >= total or not items:
                    break
                if len(collected) >= self._LIST_CHAPTERS_MAX:
                    logger.warning(
                        "list_chapters: book=%s hit the %d-chapter cap (total=%s) "
                        "— remaining chapters not enumerated",
                        book_id, self._LIST_CHAPTERS_MAX, total,
                    )
                    break
            return collected
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable: %s, trace_id=%s",
                exc, tid,
            )
            return None

    async def list_world_books(
        self, world_id: UUID, user_id: UUID
    ) -> list[dict]:
        """G4 (W2) — the member books of a world, for the world-rollup subgraph.

        Calls book-service ``GET /internal/worlds/{world_id}/books?user_id=``
        (X-Internal-Token; book-service owner-scopes by the user_id param, so a
        world the user does not own yields 404). Returns the member-book dicts
        (``book_id`` is the only field the rollup needs; ``is_bible`` is already
        excluded server-side).

        Unlike the cost-estimate calls this does NOT degrade-to-None: membership
        is load-bearing for the rollup, and a silent empty list would mask "no
        such world" as "empty graph". Raises ``WorldNotFound`` on 404 and
        ``BookServiceUnavailable`` on transport/5xx so the endpoint maps them to
        a uniform 404 vs a 503.
        """
        url = f"{self._base_url}/internal/worlds/{world_id}/books"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url,
                params={"user_id": str(user_id)},
            )
        except httpx.HTTPError as exc:
            logger.warning("book-service world-books unreachable: %s, trace_id=%s", exc, tid)
            raise BookServiceUnavailable(str(exc)) from exc
        if resp.status_code == 404:
            raise WorldNotFound(str(world_id))
        if resp.status_code != 200:
            logger.warning(
                "book-service %s returned %d, trace_id=%s", url, resp.status_code, tid,
            )
            raise BookServiceUnavailable(f"status {resp.status_code}")
        try:
            items = resp.json().get("items", [])
        except ValueError as exc:
            raise BookServiceUnavailable("malformed response") from exc
        # A 200 whose `items` isn't a list is a contract drift — raise rather than
        # silently degrade to an empty membership (which would mask a broken seam
        # as an "empty world" and drop every member book from the rollup).
        if not isinstance(items, list):
            raise BookServiceUnavailable("malformed response: items is not a list")
        return items

    async def lexical_search(
        self, book_id: UUID, q: str, *, limit: int = 20,
        granularity: str = "chapter", surface: str = "canon",
    ) -> list[dict] | None:
        """Raw-search Phase 2 — lexical leg. Calls book-service
        GET /internal/books/{book_id}/lexical-search and returns the list
        of hit dicts. Returns None on ANY failure so the hybrid
        orchestrator degrades to semantic-only (never 500s the search).

        E5 — `granularity` ("chapter" = best block per chapter for max
        distinct-chapter recall / navigate; "block" = every matching block
        for exhaustive mining) is forwarded to book-service verbatim.

        D-RAWSEARCH-CANON-WIRING — `surface` ("canon" = published-revision
        text only, the default; "all" = canon + live draft, merged) is
        forwarded so the lexical leg honours the same canon gate as the
        semantic leg. Previously unset → book-service defaulted to "draft",
        leaking unpublished text into a nominally-canon search."""
        url = f"{self._base_url}/internal/books/{book_id}/lexical-search"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url,
                params={
                    "q": q, "limit": str(limit),
                    "granularity": granularity, "surface": surface,
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return None
            results = resp.json().get("results", [])
            return results if isinstance(results, list) else None
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service lexical-search unavailable: %s, trace_id=%s",
                exc, tid,
            )
            return None

    async def get_reader_language(
        self, book_id: UUID, user_id: UUID,
    ) -> str | None:
        """KG-ML M4 (DD3) — resolve a user's stored reader-language for a book.

        Calls book-service GET /internal/books/{book_id}/reader-language?user_id=
        (the M3 resolver source). Returns the stored tag (e.g. "vi") or None when
        unset / on ANY failure — language-aware ranking then falls back to the
        next resolver tier (detected query language) and never 500s the search.
        """
        url = f"{self._base_url}/internal/books/{book_id}/reader-language"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url,
                params={"user_id": str(user_id)},
            )
            if resp.status_code != 200:
                return None
            lang = resp.json().get("reader_language")
            return lang if isinstance(lang, str) and lang.strip() else None
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service reader-language unavailable: %s, trace_id=%s", exc, tid,
            )
            return None

    async def get_reading_position(
        self, book_id: UUID, user_id: UUID,
    ) -> UUID | None:
        """W11-M2 (spec §4.2) — resolve a reader's FURTHEST-read chapter for a book,
        so the reader facade can server-enforce a spoiler cutoff from the reader's
        OWN position (never an LLM-supplied arg).

        Calls book-service GET /internal/books/{book_id}/reading-position?user_id=
        (W11-M1). Returns the furthest-read chapter_id, or **None** — the fail-closed
        signal — when the reader has no active read chapter OR on ANY failure. Note
        the route returns HTTP 200 with ``furthest_chapter_id: null`` for "no
        position" (not a 404), so BOTH the 200-null case and a transport failure
        collapse to None here; the facade then windows to nothing (a reader whose
        position can't be pinned sees no future lore, never all of it).
        """
        url = f"{self._base_url}/internal/books/{book_id}/reading-position"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(url, params={"user_id": str(user_id)})
            if resp.status_code != 200:
                return None
            body = resp.json()
            raw = body.get("furthest_chapter_id") if isinstance(body, dict) else None
            if not raw:
                return None  # 200 with null furthest_chapter_id = no position (fail-closed)
            return UUID(str(raw))
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # ValueError also covers a malformed chapter_id (UUID() raises) → None, so a
            # garbled book-service response fails CLOSED rather than 500-ing a reader tool.
            logger.warning(
                "book-service reading-position unavailable: %s, trace_id=%s", exc, tid,
            )
            return None

    async def get_chapter_titles(
        self, chapter_ids: list[UUID], language: str | None = None,
    ) -> dict[UUID, str]:
        """C6 (D-K19b.3-01 + D-K19e-β-01) — batch-resolve chapter titles.

        Fires one POST to ``/internal/chapters/titles`` and returns a
        dict mapping ``UUID → "Chapter N — Title"``. Used by the
        knowledge-service Timeline + Jobs responses to denormalize
        chapter titles inline so the FE can render
        "Chapter 12 — The Bridge Duel" instead of ``…last8chars``.

        KG-TL M1 — ``language`` (optional reader-language subtag) forwards
        to book-service so the heading resolves to the SIBLING-language
        chapter when one exists, else the source heading. Omit / None →
        legacy behavior (the requested chapter's own-language heading).
        This is what removes the Timeline's "vi heading beside zh event"
        mix: with a reader language the heading either matches the reader
        OR honestly shows source — never the book's arbitrary display
        language out of a language-blind join.

        Graceful on every failure path: returns ``{}`` so callers
        render the UUID-suffix fallback via the existing
        ``chapterShort()`` helper. Empty input short-circuits without
        a network call.
        """
        if not chapter_ids:
            return {}
        url = f"{self._base_url}/internal/chapters/titles"
        tid = trace_id_var.get()
        payload: dict[str, object] = {
            "chapter_ids": [str(cid) for cid in chapter_ids]
        }
        if language:
            payload["language"] = language
        try:
            resp = await self._http.post(
                url,
                json=payload,
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

    async def is_chapter_kg_excluded(self, book_id: UUID, chapter_id: UUID) -> bool:
        """review-impl — is this chapter CURRENTLY excluded from the knowledge graph?

        The event payload carries `kg_exclude` as of EMIT time, which is not enough: our
        bus is at-least-once, so a `chapter.kg_indexed` / `chapter.published` message can
        be redelivered and reclaimed AFTER the user excluded the chapter. Acting on the
        stale payload would RESURRECT a chapter the user asked us to forget — facts,
        passages and a re-armed extraction, permanently, with no further event to undo it.

        So the KG-write handlers re-check the live state. Uses the existing batch
        canon-markers route (book-scoped; the internal token authenticates us).

        FAILS CLOSED. If book-service is unreachable, or the chapter is absent from the
        response, we return True = "treat as excluded" and skip the write. Rationale: a
        skipped index is recoverable (the user clicks again, or the sweeper heals it); an
        un-retractable resurrection of forgotten prose is not. Do NOT "helpfully" default
        to False here.
        """
        url = f"{self._base_url}/internal/books/{book_id}/chapters/canon-markers"
        tid = trace_id_var.get()
        try:
            resp = await self._http.post(url, json={"chapter_ids": [str(chapter_id)]})
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d — treating chapter %s as kg-EXCLUDED "
                    "(fail-closed), trace_id=%s",
                    url, resp.status_code, chapter_id, tid,
                )
                return True
            marker = (resp.json().get("markers") or {}).get(str(chapter_id))
            if marker is None:
                logger.warning(
                    "chapter %s absent from canon-markers (deleted/trashed?) — treating as "
                    "kg-EXCLUDED (fail-closed), trace_id=%s",
                    chapter_id, tid,
                )
                return True
            return bool(marker.get("kg_exclude"))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable checking kg_exclude for chapter %s: %s — "
                "treating as EXCLUDED (fail-closed), trace_id=%s",
                chapter_id, exc, tid,
            )
            return True

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
            resp = await self._http.get(url)
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

    async def get_chapter_text_and_blocks(
        self, book_id: UUID, chapter_id: UUID,
    ) -> tuple[str | None, list[int]]:
        """P3-C — like get_chapter_text but also returns `block_indices`, the
        ORDERED chapter_blocks.block_index list `text_content` was joined from.
        Lets passage ingestion map a chunk's paragraph position → its real
        block_index for precise jump-to-source. Returns (None, []) on failure
        (caller falls back to no-block-mapping)."""
        url = f"{self._base_url}/internal/books/{book_id}/chapters/{chapter_id}"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                return None, []
            data = resp.json()
            text = data.get("text_content")
            if not isinstance(text, str) or not text.strip():
                return None, []
            raw = data.get("block_indices") or []
            blocks = [int(b) for b in raw] if isinstance(raw, list) else []
            return text, blocks
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "book-service unavailable fetching chapter text+blocks: %s trace_id=%s",
                exc, tid,
            )
            return None, []

    async def get_chapter_revision_text(
        self, book_id: UUID, chapter_id: UUID, revision_id: str,
    ) -> str | None:
        """CM3c — fetch a chapter's PINNED published revision text.

        Calls the CM3a internal route
        ``/internal/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/text``
        which returns ``text_content`` for exactly the published revision
        (vs the live draft). Used by passage-ingest on ``chapter.published``
        so the semantic index canonizes only author-published content.

        Returns None on any failure — the caller (passage ingester, with
        ``delete_stale_on_missing=False``) treats None as "keep existing
        passages" so a transient fetch failure does NOT wipe canon.
        """
        url = (
            f"{self._base_url}/internal/books/{book_id}/chapters/{chapter_id}"
            f"/revisions/{revision_id}/text"
        )
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(url)
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
                "book-service unavailable fetching revision text: %s trace_id=%s",
                exc, tid,
            )
            return None


    # ── P2 (hierarchical extraction T3) — D8 fallback contract ─────────

    async def list_scenes_by_chapter(
        self, book_id: UUID, chapter_id: UUID,
    ) -> list[dict] | None:
        """GET /internal/books/{book_id}/chapters/{chapter_id}/scenes.

        Returns the active scenes for one chapter (P1-decomposed).
        Empty list means legacy chapter (NULL structural_path) — caller
        MUST fall back to get_chapter_draft_text (D8 fallback contract).

        Returns None on transport failure (caller treats as transient).
        """
        url = f"{self._base_url}/internal/books/{book_id}/chapters/{chapter_id}/scenes"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return None
            data = resp.json()
            scenes = data.get("scenes") if isinstance(data, dict) else None
            if not isinstance(scenes, list):
                return None
            return scenes
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable fetching scenes: %s trace_id=%s",
                exc, tid,
            )
            return None

    async def get_chapter_draft_text(
        self, book_id: UUID, chapter_id: UUID,
    ) -> str | None:
        """GET /internal/books/{book_id}/chapters/{chapter_id}/draft-text.

        Returns the plain-text projection of chapter_drafts.body (Tiptap
        JSON → text via book-service-side walker). Used as the P2 legacy
        fallback per D8: when list_scenes_by_chapter returns empty, the
        orchestrator wraps this text in one virtual scene.

        Returns None on transport failure or when text is empty/whitespace.
        """
        url = f"{self._base_url}/internal/books/{book_id}/chapters/{chapter_id}/draft-text"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                logger.warning(
                    "book-service %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return None
            data = resp.json()
            text = data.get("text") if isinstance(data, dict) else None
            if not isinstance(text, str) or not text.strip():
                return None
            return text
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "book-service unavailable fetching chapter draft text: %s trace_id=%s",
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
