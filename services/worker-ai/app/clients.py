"""HTTP clients for worker-ai.

Three clients:
  - KnowledgeClient: calls POST /internal/extraction/persist-pass2
    (Phase 4b-γ — replaced /extract-item) and the glossary-sync
    endpoint
  - BookClient: calls GET /internal/books/{book_id}/chapters and
    GET /internal/books/{book_id}/chapters/{chapter_id}
  - GlossaryClient: paginated entity listing for scope='glossary_sync'

All use graceful degradation: return a result with `error` and
`retryable` set on failure, let the caller decide whether to retry
or fail the job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.event import LLMEventCandidate
from loreweave_extraction.extractors.fact import LLMFactCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate

__all__ = [
    "BookClient",
    "KnowledgeClient",
    "ExtractionResult",
    "ChapterInfo",
    "ChapterHierarchy",
    "HierarchyPart",
    "HierarchyScene",
    "GlossaryClient",
    "GlossaryEntity",
    "GlossaryPage",
    "GlossarySyncResult",
    "SummarizeMessageResult",
]

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


@dataclass(frozen=True)
class GlossaryEntity:
    """C12c-a — single entity from glossary-service's paginated listing.
    Shape mirrors the Go handler's `entitiesListItem`."""
    entity_id: str
    name: str
    kind_code: str
    aliases: tuple[str, ...]
    short_description: str | None


@dataclass(frozen=True)
class GlossaryPage:
    """C12c-a — one page of glossary entities + cursor for the next."""
    items: tuple[GlossaryEntity, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class HierarchyPart:
    """P3 — one part-row from book-service's hierarchy endpoint."""
    id: str
    path: str
    index: int
    title: str | None = None


@dataclass(frozen=True)
class HierarchyScene:
    id: str
    path: str
    index: int


@dataclass(frozen=True)
class ChapterHierarchy:
    """P3 D-P3-EXTRACTION-CALLER-WIRE-UP — parsed response from
    `GET /internal/books/{book_id}/chapters/{chapter_id}/hierarchy`.

    `part is None` indicates a legacy chapter (pre-P1, NULL part_id);
    worker-ai treats that as opt-out of P3 summary enqueue."""
    book_id: str
    book_path: str  # always "book" today
    book_title: str | None
    part: HierarchyPart | None
    chapter_id: str
    chapter_path: str | None
    chapter_index: int
    chapter_title: str | None
    scenes: tuple[HierarchyScene, ...]
    book_parts: tuple[HierarchyPart, ...]


@dataclass(frozen=True)
class SummarizeMessageResult:
    """P3 D-P3-WORKER-AI-CONSUMER-WIRING — parsed response from
    knowledge-service's `/internal/extraction/summarize-message` endpoint.
    Mirrors `SummaryProcessResult` on the server side."""
    level: str
    node_id: str
    cache_hit: bool
    race_winner: bool
    re_enqueued: bool
    skipped_retry_exhausted: bool
    summary_id: str | None
    retryable: bool = False
    error: str | None = None


@dataclass(frozen=True)
class GlossarySyncResult:
    """C12c-a — parsed response from knowledge-service's
    POST /internal/extraction/glossary-sync-entity endpoint."""
    glossary_entity_id: str
    action: str  # "created" | "updated"
    canonical_name: str
    retryable: bool = False
    error: str | None = None


# ── KnowledgeClient ──────────────────────────────────────────────────


class KnowledgeClient:
    """Calls knowledge-service's internal extraction endpoint."""

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float,
        *,
        summarize_message_timeout_s: float | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )
        # P3: summarize-message can run minutes on a cold local LLM; use
        # a dedicated longer-timeout client so the default persist-pass2
        # timeout (30s) doesn't truncate a legitimately-slow summary.
        # Memory anchor `feedback_polling_sdk_http_client_timeout_trap`
        # — separate the I/O budgets per logical operation.
        if summarize_message_timeout_s is not None:
            self._summarize_http = httpx.AsyncClient(
                timeout=httpx.Timeout(summarize_message_timeout_s),
                headers={"X-Internal-Token": internal_token},
            )
        else:
            self._summarize_http = self._http

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._summarize_http is not self._http:
            await self._summarize_http.aclose()

    async def persist_pass2(
        self,
        *,
        user_id: UUID,
        project_id: UUID | None,
        source_type: str,
        source_id: str,
        job_id: UUID,
        extraction_model: str,
        entities: list[LLMEntityCandidate],
        relations: list[LLMRelationCandidate],
        events: list[LLMEventCandidate],
        facts: list[LLMFactCandidate],
        # P3 D-P3-EXTRACTION-CALLER-WIRE-UP — all optional. When all
        # 3 (hierarchy_paths + embedding_model_uuid + embedding_dimension)
        # are supplied, the endpoint MERGEs the hierarchy in the same Tx
        # and enqueues `summary.chapter` (+ part/book on last chapter).
        hierarchy_paths: dict | None = None,
        book_parts: list[tuple[str, str, str]] | None = None,
        is_last_chapter_of_book: bool = False,
        embedding_model_uuid: str | None = None,
        embedding_dimension: int | None = None,
        # B2 follow-up — per-project Pass2-writer Tier-B autocreate override.
        # None = caller didn't resolve it (endpoint falls back to the env
        # default); True/False = explicit per-project setting.
        writer_autocreate: bool | None = None,
    ) -> ExtractionResult:
        """Phase 4b-γ — POST /internal/extraction/persist-pass2.

        Replaces the legacy `extract_item` flow. Worker-ai now runs
        the Pass 2 LLM stage itself via
        ``loreweave_extraction.extract_pass2(llm_client, ...)`` and
        sends the resulting candidate lists here for Neo4j persistence.
        That eliminates the 120s `extract_item_timeout_s` HTTP block
        — this endpoint is bounded by Neo4j write time (seconds).

        Returns an ExtractionResult. On HTTP error, returns a result
        with error set and retryable flag based on status code.
        """
        url = f"{self._base_url}/internal/extraction/persist-pass2"
        body: dict[str, Any] = {
            "user_id": str(user_id),
            "project_id": str(project_id) if project_id else None,
            "source_type": source_type,
            "source_id": source_id,
            "job_id": str(job_id),
            "extraction_model": extraction_model,
            # Pydantic models -> dicts for JSON serialization. The
            # server-side schema imports the same library models so
            # round-trip is field-for-field identical.
            "entities": [c.model_dump(mode="json") for c in entities],
            "relations": [c.model_dump(mode="json") for c in relations],
            "events": [c.model_dump(mode="json") for c in events],
            "facts": [c.model_dump(mode="json") for c in facts],
        }
        # P3 — only include the fields when the caller wired them.
        # Per `feedback_sdk_default_arg_dropped_from_wire` we explicitly
        # check None (not falsy) so an empty book_parts on a single-part
        # book still rides through correctly.
        if hierarchy_paths is not None:
            body["hierarchy_paths"] = hierarchy_paths
        if book_parts is not None:
            body["book_parts"] = book_parts
        if is_last_chapter_of_book:
            body["is_last_chapter_of_book"] = True
        if embedding_model_uuid is not None:
            body["embedding_model_uuid"] = embedding_model_uuid
        if embedding_dimension is not None:
            body["embedding_dimension"] = embedding_dimension
        # B2 follow-up — only include when the caller resolved it (explicit
        # None check per feedback_sdk_default_arg_dropped_from_wire) so the
        # endpoint can distinguish "use env default" from an explicit toggle.
        if writer_autocreate is not None:
            body["writer_autocreate"] = writer_autocreate

        try:
            resp = await self._http.post(url, json=body)
        except httpx.HTTPError as exc:
            logger.warning("persist-pass2 HTTP error: %s", exc)
            return ExtractionResult(
                source_id=source_id,
                entities_merged=0, relations_created=0,
                events_merged=0, facts_merged=0,
                retryable=True,
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

        return ExtractionResult(
            source_id=source_id,
            entities_merged=0, relations_created=0,
            events_merged=0, facts_merged=0,
            retryable=resp.status_code in (502, 503, 429),
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    async def process_summarize_message(
        self,
        *,
        level: str,
        node_path: str,
        node_id: str,
        book_id: str,
        user_id: str,
        project_id: str,
        job_id: str,
        model_ref: str,
        embedding_model_uuid: str,
        embedding_dimension: int,
        retry_at_epoch: float = 0.0,
        retried_n: int = 0,
    ) -> SummarizeMessageResult:
        """P3 D-P3-WORKER-AI-CONSUMER-WIRING — POST one extraction.summarize
        message to knowledge-service for processing.

        Worker-ai's Redis Stream consumer calls this after XREADGROUP;
        on a non-error response the consumer XACKs the stream message.
        Transient failures (HTTP timeout, 502/503/429) return
        `retryable=True` so the consumer can leave the message NACKed
        (no XACK) and let it surface on the next XREADGROUP via the
        pending-entries-list mechanism.
        """
        url = f"{self._base_url}/internal/extraction/summarize-message"
        body: dict[str, Any] = {
            "level": level,
            "node_path": node_path,
            "node_id": node_id,
            "book_id": book_id,
            "user_id": user_id,
            "project_id": project_id,
            "job_id": job_id,
            "model_ref": model_ref,
            "embedding_model_uuid": embedding_model_uuid,
            "embedding_dimension": embedding_dimension,
            "retry_at_epoch": retry_at_epoch,
            "retried_n": retried_n,
        }
        try:
            resp = await self._summarize_http.post(url, json=body)
        except httpx.HTTPError as exc:
            logger.warning("summarize-message HTTP error: %s", exc)
            return SummarizeMessageResult(
                level=level, node_id=node_id,
                cache_hit=False, race_winner=False,
                re_enqueued=False, skipped_retry_exhausted=False,
                summary_id=None,
                retryable=True, error=f"HTTP error: {exc}",
            )

        if resp.status_code == 200:
            data = resp.json()
            return SummarizeMessageResult(
                level=data.get("level", level),
                node_id=data.get("node_id", node_id),
                cache_hit=bool(data.get("cache_hit", False)),
                race_winner=bool(data.get("race_winner", False)),
                re_enqueued=bool(data.get("re_enqueued", False)),
                skipped_retry_exhausted=bool(
                    data.get("skipped_retry_exhausted", False),
                ),
                summary_id=data.get("summary_id"),
            )

        # 422 = validation failure — message is malformed; not retryable
        # (re-XREAD would just re-fail). Bigger transients are retryable.
        retryable = resp.status_code in (502, 503, 429)
        return SummarizeMessageResult(
            level=level, node_id=node_id,
            cache_hit=False, race_winner=False,
            re_enqueued=False, skipped_retry_exhausted=False,
            summary_id=None,
            retryable=retryable,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    async def glossary_sync_entity(
        self,
        *,
        user_id: UUID,
        project_id: UUID | None,
        glossary_entity_id: str,
        name: str,
        kind: str,
        aliases: list[str] | tuple[str, ...],
        short_description: str | None,
    ) -> GlossarySyncResult:
        """C12c-a — POST /internal/extraction/glossary-sync-entity.

        Wraps knowledge-service's thin handler around the K15.11
        `sync_glossary_entity_to_neo4j` helper. Returns a result with
        `action='created'|'updated'` on success; on HTTP error returns
        a result with `error` populated and `retryable` set on
        transient upstream failures (502/503/429, timeouts).
        """
        url = f"{self._base_url}/internal/extraction/glossary-sync-entity"
        body = {
            "user_id": str(user_id),
            "project_id": str(project_id) if project_id else None,
            "glossary_entity_id": glossary_entity_id,
            "name": name,
            "kind": kind,
            "aliases": list(aliases),
            "short_description": short_description,
        }
        try:
            resp = await self._http.post(url, json=body)
        except httpx.HTTPError as exc:
            logger.warning("glossary-sync-entity HTTP error: %s", exc)
            return GlossarySyncResult(
                glossary_entity_id=glossary_entity_id,
                action="",
                canonical_name="",
                retryable=True,
                error=f"HTTP error: {exc}",
            )

        if resp.status_code == 200:
            data = resp.json()
            return GlossarySyncResult(
                glossary_entity_id=data.get("glossary_entity_id", glossary_entity_id),
                action=data.get("action", ""),
                canonical_name=data.get("canonical_name", ""),
            )
        return GlossarySyncResult(
            glossary_entity_id=glossary_entity_id,
            action="",
            canonical_name="",
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

    async def get_chapter_hierarchy(
        self, book_id: UUID, chapter_id: str,
    ) -> ChapterHierarchy | None:
        """P3 D-P3-EXTRACTION-CALLER-WIRE-UP — GET hierarchy info worker-ai
        needs to forward P3 fields to /persist-pass2.

        Returns None on HTTP error / shape drift / 404 — runner treats
        that as "no hierarchy data; skip P3 enqueue for this chapter".
        Returns a ChapterHierarchy with `part is None` for legacy
        chapters (pre-P1 imports with NULL part_id).
        """
        url = (
            f"{self._base_url}/internal/books/{book_id}"
            f"/chapters/{chapter_id}/hierarchy"
        )
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                logger.warning(
                    "book-service hierarchy %d for chapter %s",
                    resp.status_code, chapter_id,
                )
                return None
            data = resp.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("book-service hierarchy failed: %s", exc)
            return None

        try:
            book = data.get("book") or {}
            chapter = data.get("chapter") or {}
            part_raw = data.get("part")
            part = None
            if part_raw:
                part = HierarchyPart(
                    id=part_raw["id"], path=part_raw["path"],
                    index=int(part_raw["index"]),
                    title=part_raw.get("title"),
                )
            scenes = tuple(
                HierarchyScene(
                    id=s["id"], path=s["path"], index=int(s["index"]),
                )
                for s in (data.get("scenes") or [])
            )
            book_parts = tuple(
                HierarchyPart(
                    id=bp["id"], path=bp["path"],
                    index=int(bp["index"]), title=bp.get("title"),
                )
                for bp in (data.get("book_parts") or [])
            )
            return ChapterHierarchy(
                book_id=book["id"],
                book_path=book.get("path") or "book",
                book_title=book.get("title"),
                part=part,
                chapter_id=chapter["id"],
                chapter_path=chapter.get("path"),
                chapter_index=int(chapter.get("index") or 0),
                chapter_title=chapter.get("title"),
                scenes=scenes,
                book_parts=book_parts,
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("book-service hierarchy shape drift: %s", exc)
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


# ── GlossaryClient ───────────────────────────────────────────────────


class GlossaryClient:
    """C12c-a — calls glossary-service's internal API to paginate
    through a book's glossary entities. Used by worker-ai's
    `scope='glossary_sync'` job branch (and the tail of `scope='all'`).
    Mirrors BookClient's graceful-degrade pattern: returns None on any
    failure, letting the runner treat it as "no entities to sync".
    """

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def list_book_entities(
        self,
        book_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> GlossaryPage | None:
        """GET /internal/books/{book_id}/entities — one page of entities.

        Returns a `GlossaryPage` on success (possibly empty).
        Returns `None` on HTTP error, decode failure, or shape drift —
        caller should treat this as "stop iteration; rely on what's
        been synced so far".
        """
        url = f"{self._base_url}/internal/books/{book_id}/entities"
        params: dict[str, str] = {"limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = await self._http.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(
                    "glossary-service entities %d for %s (cursor=%s)",
                    resp.status_code, book_id, cursor,
                )
                return None
            data = resp.json()
            raw_items = data.get("items", [])
            items = tuple(
                GlossaryEntity(
                    entity_id=item["entity_id"],
                    name=item.get("name") or "",
                    kind_code=item.get("kind_code") or "",
                    aliases=tuple(item.get("aliases") or []),
                    short_description=item.get("short_description"),
                )
                for item in raw_items
                if item.get("entity_id")
            )
            return GlossaryPage(
                items=items,
                next_cursor=data.get("next_cursor"),
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("glossary-service entities failed: %s", exc)
            return None
