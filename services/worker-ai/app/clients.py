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
from loreweave_internal_client import is_retryable_status, resolve_context_length, resolve_model_name

from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.event import LLMEventCandidate
from loreweave_extraction.extractors.fact import LLMFactCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate
from loreweave_extraction.schema_projection import ExtractionSchema

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
    "ChatClient",
    "ChatAssistantClient",
    "ChatAssistantUnavailable",
    "ProviderRegistryClient",
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
    # S3c-2b: the underlying LLM error code (e.g. LLM_CIRCUIT_OPEN), surfaced
    # from ExtractionError.last_error.code so the runner can emit a circuit-open
    # signal for campaign auto-pause. None when the failure carries no LLM code.
    error_code: str | None = None


@dataclass(frozen=True)
class ChapterInfo:
    """Minimal chapter metadata from book-service."""
    chapter_id: str
    title: str
    sort_order: int
    # Canon Model CM3b: set only for the 'chapters_pending' drain path —
    # revision_id pins the published revision to extract (vs the live draft);
    # pending_id is the extraction_pending row to mark processed after.
    # CM3c: on the manual 'chapters'/'all' path, list_chapters now ALSO sets
    # revision_id (from published_revision_id) so the manual rebuild reads the
    # pinned published revision via the same fetch branch; pending_id stays None
    # there (nothing to mark). editorial_status carries the canon state.
    revision_id: str | None = None
    pending_id: UUID | None = None
    editorial_status: str | None = None


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

    async def queue_diary_facts(
        self,
        *,
        user_id: str,
        book_id: str,
        entry_date: str,
        facts: list[dict],
    ) -> dict:
        """WS-2.3 — divert a distilled day's facts into knowledge-service's pending-facts INBOX. The
        entry is already written by the time this runs, so a failure here is BEST-EFFORT (the facts
        are a reviewable enrichment, not the diary entry) — the caller swallows it."""
        resp = await self._http.post(
            f"{self._base_url}/internal/admin/assistant/queue-facts",
            json={"user_id": user_id, "book_id": book_id, "entry_date": entry_date, "facts": facts},
        )
        resp.raise_for_status()
        return resp.json()

    async def invalidate_diary_day(
        self, *, user_id: str, book_id: str, entry_date: str,
    ) -> dict:
        """WS-2.6a leg 3 (D17) — soft-invalidate a corrected diary day's CONFIRMED :Facts (set
        `valid_until`), so the superseded facts vanish from recall and a rebuild can't resurrect them.
        Called by the re-extract path AFTER the corrected facts are queued. RAISES on a non-2xx /
        transport error so the re-extract job leaves the message un-acked and retries — leaving the OLD
        fact live is a correctness bug (recall would show both the wrong + corrected value), NOT a
        best-effort enrichment like queue_diary_facts."""
        resp = await self._http.post(
            f"{self._base_url}/internal/admin/assistant/invalidate-day",
            json={"user_id": user_id, "book_id": book_id, "entry_date": entry_date},
        )
        resp.raise_for_status()
        return resp.json()

    async def recall_facts_range(
        self, *, user_id: str, book_id: str, date_from: str, date_to: str, limit: int = 200,
    ) -> list[dict]:
        """WS-3.7 — read a date-range of the user's CONFIRMED diary facts (the WS-2.4 recall endpoint),
        the input to a weekly rollup's reduce. Returns the fact dicts (content/type/event_date/...). Best-
        effort: a transport/non-200 → [] (the rollup simply has nothing to summarize → no draft)."""
        try:
            resp = await self._http.post(
                f"{self._base_url}/internal/admin/assistant/recall-facts",
                json={"user_id": user_id, "book_id": book_id,
                      "event_date_from": date_from, "event_date_to": date_to, "limit": limit},
            )
            if resp.status_code != 200:
                return []
            return list(resp.json().get("facts") or [])
        except (httpx.HTTPError, ValueError, KeyError):
            return []

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
        # FD-4 (066 fix): chapter reading-order ordinal (sort_order), passed
        # SEPARATELY from hierarchy_paths so a flat book (no part) still gets a
        # dense event_order → status_effects/timeline aren't silently dropped.
        chapter_index: int | None = None,
        book_parts: list[tuple[str, str, str]] | None = None,
        is_last_chapter_of_book: bool = False,
        embedding_model_uuid: str | None = None,
        embedding_dimension: int | None = None,
        # B2 follow-up — per-project Pass2-writer Tier-B autocreate override.
        # None = caller didn't resolve it (endpoint falls back to the env
        # default); True/False = explicit per-project setting.
        writer_autocreate: bool | None = None,
        # E0-3 Phase 2a-2 — BYOK billing identity forwarded onto the SUMMARY
        # pipeline this persist enqueues (None ⇒ owner-triggered/legacy).
        billing_user_id: str | None = None,
        billing_llm_model: str | None = None,
        billing_embedding_model: str | None = None,
        # C12 — target-typed extraction. None ⇒ all passes (the endpoint
        # enqueues summaries as before). A concrete list gates the summary
        # enqueue on `summaries ∈ targets`.
        targets: list[str] | None = None,
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
        if chapter_index is not None:
            body["chapter_index"] = chapter_index
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
        # E0-3 2a-2 — only include billing when set (collaborator path); the
        # endpoint defaults to "" ⇒ owner-triggered. Storage tag stays project's.
        if billing_user_id:
            body["billing_user_id"] = billing_user_id
        if billing_llm_model:
            body["billing_llm_model"] = billing_llm_model
        if billing_embedding_model:
            body["billing_embedding_model"] = billing_embedding_model
        # C12 — only include when the caller resolved a concrete set (explicit
        # None check so a default-all job omits it ⇒ endpoint enqueues summaries
        # as before, back-compat).
        if targets is not None:
            body["targets"] = list(targets)

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
            retryable=is_retryable_status(resp.status_code),
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    async def resolve_extraction_schema(
        self, *, user_id: UUID, project_id: UUID | None,
    ) -> ExtractionSchema | None:
        """L7 (Milestone B) — fetch the project's ADVISORY extraction-schema
        projection, called ONCE per job at start. Threaded into
        ``extract_pass2(schema=...)`` so the LLM emits the project's vocab.

        Returns ``None`` for no project, a non-200, or any transport error →
        worker-ai uses the static prompt (fail-soft). The projection is advisory
        (``allow_free_edges`` forced True server-side) so the SDK injects vocab as
        a hint but never pre-drops — /persist-pass2 stays the authoritative
        enforce+park point regardless."""
        if project_id is None:
            return None
        url = f"{self._base_url}/internal/extraction/resolve-schema"
        try:
            resp = await self._http.post(
                url, json={"user_id": str(user_id), "project_id": str(project_id)},
            )
        except httpx.HTTPError as exc:
            logger.warning("resolve-schema HTTP error: %s — using static prompt", exc)
            return None
        if resp.status_code != 200:
            logger.warning(
                "resolve-schema status=%s — using static prompt", resp.status_code,
            )
            return None
        data = resp.json()
        if not data.get("has_schema"):
            return None
        return ExtractionSchema.from_resolved({
            "entity_kinds": data.get("entity_kinds", []),
            "edge_predicates": data.get("edge_predicates", []),
            "event_kinds": data.get("event_kinds", []),
            "fact_types": data.get("fact_types", []),
            "allow_free_edges": data.get("allow_free_edges", True),
            "label": data.get("label", ""),
            "schema_version": data.get("schema_version"),
        })

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
        # E0-3 Phase 2a-2 — BYOK billing identity forwarded from the redis
        # message ("" ⇒ owner-triggered/legacy).
        billing_user_id: str = "",
        billing_llm_model: str = "",
        billing_embedding_model: str = "",
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
            "billing_user_id": billing_user_id,
            "billing_llm_model": billing_llm_model,
            "billing_embedding_model": billing_embedding_model,
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
        retryable = is_retryable_status(resp.status_code)
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
            retryable=is_retryable_status(resp.status_code),
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )


# ── ChatClient ───────────────────────────────────────────────────────


class ChatClient:
    """FD-2 — calls chat-service's internal API to fetch a chat turn's text so the
    extraction worker can build chat→KG knowledge (the chat.turn_completed event
    carries only ids + lengths, not the prose)."""

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_turn_text(self, message_id: str | UUID) -> str | None:
        """GET /internal/chat/turns/{message_id}/text → the joined user+assistant
        turn text. Returns None on 404 / empty / transport failure (best-effort —
        the caller degrades to an empty no-op extraction). A transient miss simply
        skips this turn's extraction (documented LOW; transient-retry is a deferred
        improvement)."""
        url = f"{self._base_url}/internal/chat/turns/{message_id}/text"
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                logger.warning("chat-service turn-text %d for %s", resp.status_code, message_id)
                return None
            text = (resp.json().get("text") or "").strip()
            return text or None
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("chat-service turn-text failed: %s", exc)
            return None

    async def get_day_window(
        self, *, user_id: str | UUID, book_id: str | UUID, local_date: str, limit: int = 5000,
    ) -> tuple[list[dict[str, Any]], bool] | None:
        """WS-1.8 (spec 06 §Q10) — GET /internal/chat/messages/day-window → the distiller's input:
        one user's assistant-session messages for one local day (raw dicts + a `truncated` flag).
        Returns None on transport / non-200 (the job retries), else (messages, truncated). The
        assistant-only + window-cap filtering is enforced SERVER-side; this is a thin reader."""
        url = f"{self._base_url}/internal/chat/messages/day-window"
        params = {
            "user_id": str(user_id), "book_id": str(book_id),
            "local_date": local_date, "limit": str(limit),
        }
        try:
            resp = await self._http.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("chat-service day-window %d for %s/%s", resp.status_code, user_id, local_date)
                return None
            data = resp.json()
            return list(data.get("messages") or []), bool(data.get("truncated"))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("chat-service day-window failed: %s", exc)
            return None


# ── ChatAssistantClient ──────────────────────────────────────────────


class ChatAssistantUnavailable(Exception):
    """C2 (cold-review MED-1) — a TRANSPORT / non-200 failure fetching the safety-feeding
    reflection_notes. RAISED (not swallowed) because those notes feed the fail-CLOSED Gate-3 safety
    screen (X-2 SEALED): a transient chat-service outage must make the reflection RETRY, never
    silently write a reflection that skipped screening note-borne distress. An empty 200 ('no notes
    this week') is NOT this — it returns []."""


class ChatAssistantClient:
    """C2 (SD-C2) — reads the ASSISTANT-domain reflection substrate from chat-service so the
    weekly-reflection worker can fire the co-occurrence detector (needs the week's reflection_notes)
    and honour the user's tombstoned patterns (needs the dismissed pattern_keys). Separate from
    ChatClient (which reads chat turns / the distiller day-window) — this is the reflection substrate,
    a distinct concern. Both methods are BEST-EFFORT: a transport/non-200 degrades to empty, so a
    transiently-down chat-service yields a reflection with fewer detectors, never a crash or a lost
    job. Internal-token boundary."""

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def list_reflection_notes(
        self, *, user_id: str | UUID, date_from: str, date_to: str,
    ) -> list[dict]:
        """GET /internal/chat/assistant/reflection-notes → the week's end-of-day notes
        ([{entry_date, went_well, to_improve}]).

        NOT best-effort (cold-review MED-1): these notes feed the fail-CLOSED Gate-3 safety screen
        (reflect_week screens facts AND notes before surfacing anything), so a TRANSPORT/non-200
        failure RAISES `ChatAssistantUnavailable` — the consumer un-ACKs and retries rather than
        silently writing a reflection that skipped screening note-borne distress. An empty 200 ('no
        notes this week') is a valid result → returns []."""
        url = f"{self._base_url}/internal/chat/assistant/reflection-notes"
        params = {"user_id": str(user_id), "date_from": date_from, "date_to": date_to}
        try:
            resp = await self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            logger.warning("chat reflection-notes transport error for %s: %s", user_id, exc)
            raise ChatAssistantUnavailable(f"reflection-notes transport error: {exc}") from exc
        if resp.status_code != 200:
            logger.warning("chat reflection-notes %d for %s [%s..%s]",
                           resp.status_code, user_id, date_from, date_to)
            raise ChatAssistantUnavailable(f"reflection-notes HTTP {resp.status_code}")
        try:
            return list(resp.json().get("notes") or [])
        except (ValueError, KeyError) as exc:
            # a malformed 200 body is as opaque as a transport failure for the safety screen → retry
            logger.warning("chat reflection-notes bad body for %s: %s", user_id, exc)
            raise ChatAssistantUnavailable(f"reflection-notes bad body: {exc}") from exc

    async def list_dismissed_pattern_keys(self, *, user_id: str | UUID) -> frozenset[str]:
        """GET /internal/chat/assistant/reflection-dismissals → the user's tombstoned pattern_keys.
        Best-effort: any transport/non-200 → empty set. NOTE the fail-open here is SAFE — an empty
        set means a previously-dismissed pattern could momentarily reappear (annoying, recoverable),
        never that a live pattern is wrongly hidden; correctness-over-cost the other way would risk
        hiding a real observation on a blip."""
        url = f"{self._base_url}/internal/chat/assistant/reflection-dismissals"
        try:
            resp = await self._http.get(url, params={"user_id": str(user_id)})
            if resp.status_code != 200:
                logger.warning("chat reflection-dismissals %d for %s", resp.status_code, user_id)
                return frozenset()
            return frozenset(resp.json().get("pattern_keys") or [])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("chat reflection-dismissals failed: %s", exc)
            return frozenset()


# ── ProviderRegistryClient ───────────────────────────────────────────


class ProviderRegistryClient:
    """FD-27 — fetches a model's provider_model_name (NO secrets) so the
    extraction worker can run a best-effort reasoning-model advisory. A
    reasoning model (qwen3.x-thinking, deepseek-r1, o-series, …) with thinking
    enabled silently burns its budget on reasoning tokens and emits empty JSON
    → 0 entities/events, with no error. Best-effort: None on any failure (the
    advisory simply doesn't fire; extraction proceeds)."""

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token
        self._timeout_s = timeout_s

    async def aclose(self) -> None:
        # P3 SDK-first (W4): no persistent client — resolve_model_name opens a
        # short-lived client per call (a best-effort ~once-per-job advisory).
        return None

    async def get_model_name(self, model_source: str, model_ref: str | UUID) -> str | None:
        """Resolve a model's provider_model_name (advisory; None on any failure).

        P3 SDK-first (W4): delegates to loreweave_internal_client.resolve_model_name
        — the single owner of the provider-registry model-info read — so the last
        standalone copy of that GET is gone (was worker-ai's baselined variant)."""
        return await resolve_model_name(
            self._base_url, model_source, str(model_ref),
            internal_token=self._internal_token, timeout_s=self._timeout_s,
        )

    async def get_context_length(self, model_source: str, model_ref: str | UUID) -> int | None:
        """Resolve a model's real context window (tokens), or None when the registry
        can't determine it. Delegates to loreweave_internal_client.resolve_context_length
        — never fabricates a guessed number; the extraction pipeline's own ContextBudget
        supplies the conservative default for the genuinely-unknown case."""
        return await resolve_context_length(
            self._base_url, model_source, str(model_ref),
            internal_token=self._internal_token, timeout_s=self._timeout_s,
        )


# ── BookClient ───────────────────────────────────────────────────────


# book-service clamps chapter-list page size to 100 (parseLimitOffset). Asking for more
# does not get more — it silently gets 100. So we page. The cap bounds a runaway loop on a
# pathological book; hitting it is logged as an ERROR, never a silent truncation.
_LIST_CHAPTERS_PAGE = 100
_LIST_CHAPTERS_MAX = 5000


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

    async def list_chapters(
        self, book_id: UUID, editorial_status: str | None = None,
        kg_indexed: bool | None = None,
    ) -> list[ChapterInfo] | None:
        """GET /internal/books/{book_id}/chapters — returns chapters.

        WS-0.6 (spec 2026-07-11-publish-independent-kg-indexing §3.5, red-team P0-2):
        the knowledge-graph enumeration gate is now ``kg_indexed=True``, NOT
        ``editorial_status='published'``.

        Publishing no longer gates the graph. Pass ``kg_indexed=True`` to server-filter
        the list AND its count to the chapters the user actually put in their knowledge
        graph (``kg_indexed_revision_id IS NOT NULL AND NOT kg_exclude`` — the same
        predicate the reparse sweeper uses, so enumerate and heal cannot disagree).
        Filtering on ``editorial_status='published'`` instead would enumerate ZERO of a
        user's 50 explicitly-indexed DRAFT chapters, and the rebuild would report success
        having extracted nothing.

        ``ChapterInfo.revision_id`` is mapped from ``kg_indexed_revision_id`` — the
        revision the knowledge layer reflects (possibly a draft) — falling back to
        ``published_revision_id`` so a caller that still asks the publish question keeps
        the old pinning behavior.

        ``editorial_status`` is retained for the non-KG callers that legitimately ask the
        publish question.

        ⚠️ PAGINATES (review-impl P1). This used to issue a single GET with `?limit=1000`
        and no offset loop. book-service CLAMPS page size to 100 (parseLimitOffset), so
        the whole-book rebuild silently enumerated only the FIRST 100 kg-indexed chapters
        of a large book and reported SUCCESS — chapters 101+ never reached the graph, with
        no error and no warning. A book at the hard cap is logged, never silently truncated.

        Returns None on failure.
        """
        base = f"{self._base_url}/internal/books/{book_id}/chapters"
        out: list[ChapterInfo] = []
        offset = 0
        try:
            while True:
                url = f"{base}?limit={_LIST_CHAPTERS_PAGE}&offset={offset}"
                if editorial_status:
                    url += f"&editorial_status={editorial_status}"
                if kg_indexed:
                    url += "&kg_indexed=true"
                resp = await self._http.get(url)
                if resp.status_code != 200:
                    logger.warning("book-service chapters %d for %s", resp.status_code, book_id)
                    return None
                data = resp.json()
                items = data.get("items") or []
                out.extend(
                    ChapterInfo(
                        chapter_id=item["chapter_id"],
                        title=item.get("title") or "",
                        sort_order=item.get("sort_order", 0),
                        # The revision the KG reflects. The fallback keeps publish-question
                        # callers pinning the published revision exactly as before.
                        revision_id=(
                            item.get("kg_indexed_revision_id")
                            or item.get("published_revision_id")
                        ),
                        editorial_status=item.get("editorial_status"),
                    )
                    for item in items
                )
                if len(items) < _LIST_CHAPTERS_PAGE:
                    break  # last page
                offset += _LIST_CHAPTERS_PAGE
                if offset >= _LIST_CHAPTERS_MAX:
                    # Bound a runaway loop / pathological book — but SAY SO. A silent
                    # truncation here is the exact bug this pagination fixes.
                    logger.error(
                        "book-service chapters: book=%s hit the %d-chapter enumeration cap "
                        "— the rebuild will be INCOMPLETE (chapters beyond the cap are not "
                        "extracted)",
                        book_id, _LIST_CHAPTERS_MAX,
                    )
                    break
            return out
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("book-service chapters failed: %s", exc)
            return None

    async def diary_day_kept(self, *, book_id: str | UUID, owner_user_id: str | UUID, entry_date: str) -> bool:
        """WS-3.3 M1 — a cheap pre-LLM gate: is (book, entry_date)'s primary entry already KEPT? The
        catch-up sweep skips the map-reduce for a kept day (the write seam only 409s AFTER the LLM).
        Best-effort: any transport/non-200 → False (proceed with the distill; correctness over cost)."""
        url = f"{self._base_url}/internal/books/{book_id}/diary/day-kept"
        try:
            resp = await self._http.get(url, params={"owner_user_id": str(owner_user_id), "entry_date": entry_date})
            if resp.status_code != 200:
                return False
            return bool(resp.json().get("kept"))
        except (httpx.HTTPError, ValueError, KeyError):
            return False

    async def write_diary_entry(
        self,
        *,
        book_id: str | UUID,
        owner_user_id: str | UUID,
        entry_date: str,
        entry_zone: str,
        body: str,
        title: str | None = None,
        journal_kind: str = "primary",
        language: str = "en",
    ) -> dict[str, Any] | None:
        """WS-1.8 (spec 06 §Q10) — POST /internal/books/{id}/diary/entry, the distiller's write
        seam. Returns the parsed body on 200/201 (created or replaced). A 409 DIARY_ENTRY_KEPT is
        surfaced as {'kept': True} so the caller can re-run as a supplement; any other non-2xx /
        transport error → {'error': ...} (the job logs + retries). Never raises."""
        url = f"{self._base_url}/internal/books/{book_id}/diary/entry"
        payload = {
            "owner_user_id": str(owner_user_id),
            "entry_date": entry_date,
            "entry_zone": entry_zone,
            "body": body,
            "title": title or "",
            "journal_kind": journal_kind,
            "language": language,
        }
        try:
            resp = await self._http.post(url, json=payload)
        except httpx.HTTPError as exc:
            logger.warning("book-service diary-entry HTTP error: %s", exc)
            return {"error": f"HTTP error: {exc}", "retryable": True}
        if resp.status_code in (200, 201):
            try:
                return resp.json()
            except ValueError:
                return {"error": "bad json"}
        if resp.status_code == 409 and "DIARY_ENTRY_KEPT" in resp.text:
            return {"kept": True}
        logger.warning("book-service diary-entry %d: %s", resp.status_code, resp.text[:200])
        return {"error": f"HTTP {resp.status_code}", "retryable": is_retryable_status(resp.status_code)}

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

    async def get_chapter_revision_text(
        self, book_id: UUID, chapter_id: str, revision_id: str,
    ) -> str | None:
        """GET /internal/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/text (CM3a).

        Returns the PINNED published revision's plain text (vs the live draft),
        so canon=published graph extraction reads exactly what the author
        published.

        Returns None ONLY when the revision is PERMANENTLY GONE — a 404 (deleted
        chapter/revision, or IDOR-guarded miss). On a TRANSIENT failure (network
        error / 5xx) it RAISES so the caller fails+retries the job instead of
        treating a blip as 'gone'. This distinction is load-bearing: the
        chapters_pending drain marks the pending row processed on a None (so a
        dead revision stops re-arming the drain every poll — D-CM3B-DEAD-REVISION-
        LOOP); marking on a transient blip would silently drop canon.
        """
        url = (
            f"{self._base_url}/internal/books/{book_id}/chapters/{chapter_id}"
            f"/revisions/{revision_id}/text"
        )
        resp = await self._http.get(url)  # network errors propagate → job retries
        if resp.status_code == 404:
            logger.warning(
                "book-service revision %s/%s: 404 (revision gone)",
                chapter_id, revision_id,
            )
            return None
        resp.raise_for_status()  # 5xx / other non-2xx → raise → job fails + retries
        data = resp.json()
        return data.get("text_content") or None


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

    async def fetch_entities_by_ids(
        self,
        book_id: UUID,
        entity_ids: list[str],
    ) -> list[str]:
        """C13 — batch-fetch glossary entity NAMES by id for pinning.

        POSTs to the SAME internal endpoint the knowledge-service semantic
        selector uses (``/internal/books/{book_id}/entities/by-ids``), reusing
        the existing ``X-Internal-Token`` baked into this client's headers — NO
        new secret / URL / token env. The runner force-injects the returned
        names into every extraction window's ``known_entities`` so pinned
        entities stay anchored even in chapters that never mention them.

        Returns the entity names (``cached_name`` from the select-for-context
        row shape). Best-effort: empty input → ``[]``; any HTTP / decode failure
        → ``[]`` (the runner degrades to no-pins, never blocks the job).
        """
        if not entity_ids:
            return []
        url = f"{self._base_url}/internal/books/{book_id}/entities/by-ids"
        try:
            resp = await self._http.post(url, json={"entity_ids": entity_ids})
            if resp.status_code != 200:
                logger.warning(
                    "glossary entities/by-ids %d for %s", resp.status_code, book_id,
                )
                return []
            data = resp.json()
            names: list[str] = []
            for item in data.get("items", []):
                name = (item.get("cached_name") or "").strip()
                if name:
                    names.append(name)
            return names
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("glossary entities/by-ids failed: %s", exc)
            return []


class UsageBillingClient:
    """WS-2.8 — reads a user's spend guardrail so the distiller can degrade the BACKGROUND memory path
    when the daily cap is exhausted. Internal-token. Every method FAILS OPEN (returns the not-exhausted
    answer) on any transport/parse error — the provider-gateway reserves against the SAME guardrail and
    is the hard backstop, so a transiently-down usage-billing must never silently pause a user's memory."""

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def daily_cap_exhausted(self, *, user_id: str) -> bool:
        """True iff the user has a positive daily limit AND no daily budget left (available <= 0). The
        distiller pauses the day when this is True. False on any error (fail-open)."""
        try:
            resp = await self._http.get(
                f"{self._base_url}/internal/billing/guardrail/status",
                params={"owner_user_id": user_id},
            )
            resp.raise_for_status()
            body = resp.json()
            daily_limit = float(body.get("daily_limit_usd") or 0.0)
            daily_available = float(body.get("daily_available_usd") or 0.0)
            # A zero/absent daily limit means "no cap" → never pause. Otherwise pause once the day's
            # budget (limit − spent − reserved) is gone.
            return daily_limit > 0.0 and daily_available <= 0.0
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("usage-billing guardrail status failed (fail-open, memory proceeds): %s", exc)
            return False
