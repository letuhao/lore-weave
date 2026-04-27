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
    "GlossaryClient",
    "GlossaryEntity",
    "GlossaryPage",
    "GlossarySyncResult",
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

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

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
