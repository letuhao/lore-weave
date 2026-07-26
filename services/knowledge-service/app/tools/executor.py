"""K21.2 — memory tool executor.

`execute_tool` validates an LLM-issued tool call against its arg model
(K21.1) and dispatches to a handler that calls the knowledge-service
repos. Design contract:

  * **Result envelope** — returns a `ToolResult(success, result, error)`.
    `success=True` carries a `result` dict; `success=False` carries an
    `error` string. A handler that ran fine but found nothing returns
    `success=True` with a `{found: false}`-style result — "nothing"
    is a valid answer, not an error.
  * **Tool error vs. infra error** (design D9) — bad args, an unknown
    tool, or a rate-limit rejection are `tool_error`: caught here,
    returned as `success=False`. Anything unexpected (Neo4j down, etc.)
    is an `infra_error`: re-raised so the endpoint maps it to HTTP 503.
    A tool failure never crashes chat. NOTE: "no project linked" is NOT
    a tool_error for the read-memory tools — like an empty result, it's
    a valid "nothing to search" answer (success with an empty/`found:false`
    body + a guiding note), so it doesn't surface as a scary "failed" step.
  * **Guardrails** (K21.7) — `memory_remember` writes facts at fixed
    low confidence + a distinguishing `source_type`, rate-limited per
    chat session. The limiter fails OPEN (design D5).
  * **Metrics** (K21.8) — every call records count + duration; a
    successful call also records result size.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import UUID

import redis.asyncio as aioredis
from loreweave_mcp import apply_response_contract
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:  # deps used only as ToolContext type hints (lane LF + story_search)
    from app.clients.book_client import BookClient
    from app.clients.grant_client import GrantClient
    from app.clients.reranker_client import RerankerClient
    from app.db.repositories.graph_schemas import GraphSchemasRepo
    from app.db.repositories.graph_views import GraphViewsRepo
    from app.db.repositories.ontology_mutations import OntologyMutationsRepo
    from app.db.repositories.triage import TriageRepo
    from app.ontology.resolver import OntologyResolver

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import (
    find_entities_by_name,
    get_entity_with_relations,
)
from app.db.neo4j_repos.events import list_events_filtered
from app.db.neo4j_repos.facts import invalidate_fact, merge_fact
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    find_passages_by_vector,
)
from app.db.repositories.pending_facts import PendingFactsRepo
from app.db.repositories.projects import ProjectsRepo
from app.extraction.injection_defense import neutralize_injection
from app.metrics import (
    memory_remember_rate_limited_total,
    tool_call_duration_seconds,
    tool_call_result_size_bytes,
    tool_calls_total,
)
from app.tools.definitions import (
    ARG_MODELS,
    MemoryForgetArgs,
    MemoryRecallEntityArgs,
    MemoryRememberArgs,
    MemorySearchArgs,
    MemoryTimelineArgs,
    StorySearchArgs,
)
from app.tools.build_tools import BUILD_TOOL_HANDLERS
from app.tools.graph_schema_tools import GRAPH_SCHEMA_HANDLERS
from app.tools.project_tools import PROJECT_TOOL_HANDLERS
# W11-M2: imported AFTER graph_schema_tools so reader_tools' `_resolve_project_owner`
# import resolves against an already-loaded module (no import cycle).
from app.tools.reader_tools import READER_TOOL_HANDLERS

logger = logging.getLogger(__name__)

__all__ = ["ToolResult", "ToolContext", "execute_tool", "get_tools_redis"]

# K21.7 — facts written by `memory_remember` are tagged + scored so
# they (a) never silently enter the L2 RAG loader (its default
# min_confidence is 0.8) and (b) are filterable in the Entities tab.
TOOL_FACT_CONFIDENCE = 0.7
TOOL_FACT_SOURCE_TYPE = "llm_tool_call"

# Rate-limit key shape + TTL — a chat session spans many turns, so the
# counter must outlive any single turn; 24h comfortably covers a
# session while keeping Redis tidy.
_REMEMBER_RL_PREFIX = "k21:remember:"
_REMEMBER_RL_TTL_S = 24 * 3600

# Result-size guards (design D7).
_SNIPPET_CHARS = 500
_OTHER_MATCHES_CAP = 5

# One-line preview cap for the L1 summary projection (§6b) — the compact snippet
# a `detail=summary` result keeps in place of the full body.
_PREVIEW_CHARS = 160

# ── L1/L2 reference-first ref-field sets (Context Budget Law §6b) ──────
# At detail="summary" `apply_response_contract` keeps ONLY these keys per item and
# drops the heavy bodies; at detail="full" the row is unchanged. Exported so the
# per-tool contract-guard tests can assert the ref set never re-admits a heavy
# field (mirrors composition's _OUTLINE_REF_FIELDS).
#
# story_search: keep the chapter reference + score/type + the jump location; DROP
# the full `snippet` passage text (the bloat) + `highlights` + `relevance`/
# `sourceLang`. Re-read a hit via book_get_chapter (named in the tool description).
STORY_SEARCH_REF_FIELDS = (
    "chapterId", "chapterTitle", "sortOrder", "surface", "matchType",
    "score", "location",
)
# memory_search: keep the 1-line `snippet` preview + source_type + score; DROP the
# full (≤500-char) `text` body. The preview is added additively in the handler so
# detail="full" still carries the full `text` (no behavior change).
MEMORY_SEARCH_REF_FIELDS = ("snippet", "source_type", "score")
# memory_timeline: keep the event's title/date/participants; DROP the (≤500-char)
# `summary` body at summary detail.
MEMORY_TIMELINE_REF_FIELDS = ("title", "event_date", "participants")


def _one_line(text: str | None, limit: int = _PREVIEW_CHARS) -> str:
    """Collapse whitespace to a single ≤`limit`-char preview line for the L1
    summary snippet — so a summary item carries a cheap gist, not the full body."""
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


# ── result / context types ────────────────────────────────────────────


@dataclass
class ToolResult:
    """Outcome of one tool call. `success=False` ⇒ `error` is set and
    `result` is None; `success=True` ⇒ `result` is the payload dict.

    `code`/`detail` (optional) carry a STABLE machine-readable error code and
    structured detail for a tool failure (e.g. `KG_ENDPOINT_NOT_NODE` +
    `{"missing": [...]}`), so a caller/workflow can branch on the code instead
    of parsing free text (contract C4/C5). None for a plain string error."""

    success: bool
    result: dict | None = None
    error: str | None = None
    code: str | None = None
    detail: dict | None = None


@dataclass
class ToolContext:
    """Per-call scope + dependencies. `user_id` / `project_id` /
    `session_id` come from the chat-service envelope — never from the
    LLM-supplied tool args (design D3).

    The KG-ontology tools (lane LF) need extra repos/clients (grant client,
    graph views/schemas/triage repos, the ontology resolver + mutations repo).
    They are optional with `None` defaults so the memory-tool call sites
    (and their tests) that build a ToolContext don't have to supply them —
    a KG handler that needs a missing dependency would fail clearly. The MCP
    server (`app/mcp/server.py`) populates them for the unified `/mcp`
    surface."""

    user_id: UUID
    project_id: UUID | None
    session_id: str
    projects_repo: ProjectsRepo
    pending_facts_repo: PendingFactsRepo
    embedding_client: EmbeddingClient
    redis: aioredis.Redis | None
    # Public MCP API key id (X-Mcp-Key-Id) when the call came via the public edge;
    # None for first-party traffic. Carrier for per-key spend attribution (H-C) and
    # the owned-resources-only default (OD-8 — see loreweave_mcp.is_owner_only).
    mcp_key_id: str | None = None
    # ── #12 story_search (universal manuscript search) — optional deps ─
    # run_hybrid_search needs the book-service lexical leg + the BYOK
    # reranker; same optional-with-None pattern as the lane-LF deps below.
    book_client: "BookClient | None" = None
    reranker_client: "RerankerClient | None" = None
    # ── lane LF (KG ontology MCP tools) — optional deps ───────────────
    grant_client: "GrantClient | None" = None
    graph_views_repo: "GraphViewsRepo | None" = None
    graph_schemas_repo: "GraphSchemasRepo | None" = None
    triage_repo: "TriageRepo | None" = None
    ontology_resolver: "OntologyResolver | None" = None
    ontology_mutations_repo: "OntologyMutationsRepo | None" = None


class ToolExecutionError(Exception):
    """A tool-level failure (bad input, rejection) — surfaced to the
    caller as `success=False`, NOT a 5xx. Distinct from an unexpected
    exception, which propagates as an infra error.

    Optional `code`/`detail` attach a STABLE machine-readable error code +
    structured detail (e.g. `KG_ENDPOINT_NOT_NODE` + `{"missing": [...]}`) so a
    caller can branch on the code, not the message (contract C4/C5). Omitting
    them keeps the legacy string-only behavior."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail


# ── Redis (rate limiter) ──────────────────────────────────────────────

_redis_singleton: aioredis.Redis | None = None


def get_tools_redis() -> aioredis.Redis | None:
    """Lazy process-singleton Redis handle for the `memory_remember`
    rate limiter. `from_url` connects lazily, so this rarely fails;
    a genuine outage surfaces at INCR time and fails open there."""
    global _redis_singleton
    if _redis_singleton is None:
        try:
            _redis_singleton = aioredis.from_url(
                settings.redis_url, decode_responses=True
            )
        except Exception as exc:  # pragma: no cover - construction rarely fails
            logger.warning(
                "K21: could not build Redis client; memory_remember "
                "rate limit will fail open: %s",
                exc,
            )
            return None
    return _redis_singleton


async def _check_remember_rate_limit(
    redis: aioredis.Redis | None, session_id: str
) -> bool:
    """True ⇒ a `memory_remember` call is allowed. Fails OPEN — a
    missing or erroring Redis must not break chat (design D5)."""
    if redis is None:
        return True
    key = f"{_REMEMBER_RL_PREFIX}{session_id}"
    limit = settings.tool_remember_limit_per_session
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _REMEMBER_RL_TTL_S)
        return count <= limit
    except Exception as exc:
        logger.warning(
            "K21: memory_remember rate-limit check failed, allowing "
            "(fail-open): %s",
            exc,
        )
        return True


def _truncate(text: str | None, limit: int = _SNIPPET_CHARS) -> str:
    """Cap a snippet so tool output can't blow the LLM context."""
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "…"


def _resolve_project_scope(ctx: ToolContext, args: BaseModel) -> ToolContext:
    """H-I: adopt a tool's ``project_id`` arg as the call's scope WHEN the envelope
    carries none. The public MCP edge mints no ``X-Project-Id``, so a public agent
    has no other way to say which project a call targets; it supplies it as an arg.

    The trusted envelope WINS when present — a first-party chat session's project
    scope is authoritative, so an LLM cannot redirect a session to a different
    project (D3 preserved on that path). The arg only SUPPLIES scope when the
    envelope has none. Either way the per-handler owner gate
    (_require_project_owner_memory / _resolve_project_owner) validates it, so an
    LLM-supplied id can only ever address a project the caller already owns.
    """
    if ctx.project_id is not None:
        return ctx
    arg_pid = getattr(args, "project_id", None)
    if not arg_pid:
        return ctx
    try:
        pid = UUID(arg_pid)
    except (ValueError, TypeError):
        raise ToolExecutionError("project_id must be a valid id")
    return replace(ctx, project_id=pid)


async def _require_project_owner_memory(ctx: ToolContext) -> None:
    """Memory is per-user: a project's memory belongs to its OWNER alone — never to
    book collaborators (unlike the grant-aware kg_* tools). When a project is in
    scope, require the caller owns it BEFORE any project-scoped read/write (H-U).

    Each memory query is already scoped by ``user_id``, so a non-owner's query
    merely returned nothing — cross-tenant safe, but only *implicitly*. This makes
    the guarantee EXPLICIT (robust to a future query dropping the user_id filter)
    and enforces the owned-only default for a public MCP key (OD-8): whether or not
    ``mcp_key_id`` is set, memory never resolves a project the caller doesn't own.
    A no-project call (global personal memory) is inherently self-owned → no check.

    Anti-oracle (H13): a non-owned project and a missing one raise the SAME error,
    so a caller can't probe which project_ids exist.
    """
    if ctx.project_id is None:
        return
    meta = await ctx.projects_repo.project_meta(ctx.project_id)
    if meta is None or meta[0] != ctx.user_id:
        raise ToolExecutionError("project not found")


# ── handlers ──────────────────────────────────────────────────────────


async def _handle_story_search(ctx: ToolContext, args: StorySearchArgs) -> dict:
    """#12 — the universal manuscript search: one tool over the raw-search hybrid
    engine (lexical FTS/trigram + CJK fulltext + semantic vectors + RRF +
    cross-encoder rerank). Zero required location args: the project comes from the
    ambient ToolContext (or the optional ownership-checked project_id), the book
    from the project's link. Degraded legs surface in `degraded`, never an error."""
    if ctx.project_id is None:
        return {"hits": [], "count": 0,
                "note": "no knowledge project is linked to this chat — link one in "
                        "session settings to enable story search"}
    project = await ctx.projects_repo.get(ctx.user_id, ctx.project_id)
    if project is None:
        raise ToolExecutionError("project not found")
    if project.book_id is None:
        return {"hits": [], "count": 0,
                "note": "this project has no linked book to search"}
    if ctx.book_client is None or ctx.reranker_client is None:
        raise ToolExecutionError("story search is not available on this surface")

    # Late import — retriever pulls heavy search deps; keep executor import light.
    from app.search.retriever import run_hybrid_search

    # D-1 spoiler cutoff — mirror raw_search.py: resolve the optional before_chapter_id to a
    # passage-axis sort-order ONLY when supplied (an omitted cutoff means the full manuscript,
    # NOT the fail-closed -1). An unresolvable id resolves to -1 → windows out everything, so a
    # bad/hostile id can never leak the whole corpus past a reader's position.
    before_sort_order: int | None = None
    if args.before_chapter_id is not None:
        from uuid import UUID

        from app.spoiler_window import resolve_before_sort_order
        try:
            _cut_id = UUID(str(args.before_chapter_id))
        except (ValueError, AttributeError, TypeError):
            _cut_id = None
        before_sort_order, _ = await resolve_before_sort_order(ctx.book_client, _cut_id)

    mode = "lexical" if args.mode == "exact" else args.mode
    result = await run_hybrid_search(
        user_id=ctx.user_id,
        book_id=project.book_id,
        query=args.query,
        project=project,
        book_client=ctx.book_client,
        embedding_client=ctx.embedding_client,
        reranker_client=ctx.reranker_client,
        mode=mode,  # type: ignore[arg-type]
        granularity=args.granularity,
        limit=args.limit,
        before_sort_order=before_sort_order,
    )
    hits = result.hits[: args.limit]
    # L1/L2 reference-first (§6b): at detail="summary" drop the heavy passage
    # `snippet` (+ highlights/relevance) and keep only the chapter ref + score +
    # jump location; `count` stays = returned for back-compat, `meta` reports
    # total/returned/truncated so a cap is never a silent drop.
    projected, meta = apply_response_contract(
        hits, ref_fields=STORY_SEARCH_REF_FIELDS, detail=args.detail,
    )
    out: dict = {"hits": projected, "count": len(projected), **meta}
    if result.degraded:
        out["degraded"] = result.degraded
    if not projected:
        out["note"] = (
            "no matches — try mode='semantic' for ideas described in your own "
            "words, or a shorter exact phrase"
        )
    return out


async def _handle_memory_search(ctx: ToolContext, args: MemorySearchArgs) -> dict:
    """Engine-unified project search (see docs/plans/2026-07-05-search-tool-unification.md).

    Two legs, merged, so the tool is NEVER empty when the raw chapter text matches —
    the fix for the "agent picks memory_search, gets nothing, punts" failure:
      • MANUSCRIPT leg (chapter source) → the SAME lexical-inclusive hybrid engine
        `story_search` uses (`run_hybrid_search`). Its lexical FTS leg needs NO
        embeddings/passages, so chapter-body recall works on a bare book.
      • PASSAGE leg (chat/glossary source) → the existing semantic vector search over
        ingested passages; skipped cleanly when no embedding model / no passages.
    A `source_type` filter runs only the relevant leg(s). Response shape unchanged
    (`{snippet, text, source_type, score}`), so every existing caller is back-compat —
    a previously-EMPTY result just becomes a real one (strictly better)."""
    if ctx.project_id is None:
        # No knowledge project linked to this chat → there is simply nothing to search.
        # Return a clean EMPTY result (as memory_recall_entity / memory_timeline already
        # do for no-project) instead of a hard tool_error, so "no memory linked" doesn't
        # surface to the user as an alarming red "failed" step. The note guides both the
        # agent (fall back to other tools) and the user (link a project to enable memory).
        return {"hits": [], "count": 0,
                "note": "no knowledge project is linked to this chat — pass the optional "
                        "`project_id` argument (list your projects with kg_project_list), "
                        "or link one in session settings to enable memory search"}
    # H-U: projects_repo.get is OWNER-keyed (user_id + project_id), so this IS the
    # owner check for memory_search — a project the caller doesn't own returns None
    # → "project not found" (anti-oracle), same as the explicit
    # _require_project_owner_memory used by the other memory tools.
    project = await ctx.projects_repo.get(ctx.user_id, ctx.project_id)
    if project is None:
        # A project_id WAS supplied but doesn't resolve (deleted / wrong / not owned)
        # — a genuine error worth surfacing, distinct from "no project linked" above.
        raise ToolExecutionError("project not found")

    items: list[dict] = []
    degraded: list | None = None
    seen: set[str] = set()

    # ── MANUSCRIPT leg: lexical-inclusive hybrid over the linked book's chapters.
    # Runs whenever the caller wants the chapter source AND the manuscript engine is
    # wired on this surface (book + reranker clients). Needs NO embeddings for its
    # lexical leg — this is what makes chapter-body recall work with 0 passages.
    if (
        ctx.book_client is not None
        and ctx.reranker_client is not None
        and args.source_type in (None, "chapter")
        and getattr(project, "book_id", None) is not None
    ):
        from app.search.retriever import run_hybrid_search  # heavy deps — late import

        result = await run_hybrid_search(
            user_id=ctx.user_id, book_id=project.book_id, query=args.query,
            project=project, book_client=ctx.book_client,
            embedding_client=ctx.embedding_client, reranker_client=ctx.reranker_client,
            mode="hybrid", granularity="block", limit=args.limit,
        )
        for h in result.hits[: args.limit]:
            snip = h.get("snippet") or ""
            key = _one_line(snip)
            if not key or key in seen:
                continue
            seen.add(key)
            items.append({
                "snippet": key,
                "text": _truncate(snip),
                "source_type": "chapter",
                "score": round(float(h.get("score") or 0.0), 4),
            })
        if result.degraded:
            degraded = result.degraded

    # ── PASSAGE leg: semantic vector search over ingested chat/glossary passages (and
    # chapter passages, when present). The manuscript leg above already covers chapters
    # better (lexical), so restrict this leg to chat/glossary unless the caller asked
    # for a specific non-chapter source. Skipped cleanly when no embedding model.
    _passage_source = args.source_type if args.source_type in ("chat", "glossary") else None
    if (
        args.source_type in (None, "chat", "glossary")
        and project.embedding_model is not None
        and project.embedding_dimension is not None
        and project.embedding_dimension in SUPPORTED_PASSAGE_DIMS
    ):
        embed = None
        try:
            embed = await ctx.embedding_client.embed(
                user_id=ctx.user_id, model_source="user_model",
                model_ref=project.embedding_model, texts=[args.query],
            )
        except EmbeddingError as exc:
            # Only a hard failure if we have nothing from the manuscript leg either.
            if not items:
                raise ToolExecutionError(
                    f"memory search is temporarily unavailable: {exc}"
                )
        if embed and embed.embeddings and embed.embeddings[0]:
            try:
                async with neo4j_session() as session:
                    hits = await find_passages_by_vector(
                        session, user_id=str(ctx.user_id), project_id=str(ctx.project_id),
                        query_vector=embed.embeddings[0], dim=project.embedding_dimension,
                        embedding_model=project.embedding_model,
                        source_type=_passage_source, limit=args.limit,
                    )
            except ValueError as exc:
                # query_vector length disagrees with the stored dim (model changed
                # out-of-band) — only fatal if the manuscript leg found nothing.
                if not items:
                    raise ToolExecutionError(f"memory search failed: {exc}")
                hits = []
            for h in hits[: args.limit]:
                key = _one_line(h.passage.text)
                if not key or key in seen:
                    continue
                seen.add(key)
                items.append({
                    "snippet": key,
                    "text": _truncate(h.passage.text),
                    "source_type": h.passage.source_type,
                    "score": round(h.raw_score, 4),
                })

    items = items[: args.limit]
    projected, meta = apply_response_contract(
        items, ref_fields=MEMORY_SEARCH_REF_FIELDS, detail=args.detail,
    )
    out: dict = {"hits": projected, "count": len(projected), **meta}
    if degraded:
        out["degraded"] = degraded
    if not projected:
        out["note"] = "this project has no indexed memory yet"
    return out


async def _diary_exclusion(ctx: ToolContext) -> list[str]:
    """D16 (spec 07 §Q4) — the project ids a project-less memory read must EXCLUDE. With an explicit
    project the scope is already correct (nothing to exclude); with none, the all-projects fallback would
    surface the user's ASSISTANT (work-diary) entities into e.g. a novel-writing session, so we exclude
    the user's assistant projects. Empty list when there is no assistant project or a project is scoped."""
    if ctx.project_id is not None:
        return []
    return await ctx.projects_repo.list_assistant_project_ids(ctx.user_id)


async def _handle_memory_recall_entity(
    ctx: ToolContext, args: MemoryRecallEntityArgs
) -> dict:
    # @small_return: a SINGLE entity (name/kind/aliases/confidence) + its relations
    # (already capped in-repo, with `relations_truncated`) + a ≤5 other_matches name
    # list. This IS the get-by-id sibling the SET tools' summaries defer to — no heavy
    # body to shed, so no `detail` lever (spec §6b small/single-object exemption).
    await _require_project_owner_memory(ctx)  # H-U: owner-only project gate
    project_id = str(ctx.project_id) if ctx.project_id else None
    exclude = await _diary_exclusion(ctx)  # D16 — no diary leak into a non-assistant session
    async with neo4j_session() as session:
        matches = await find_entities_by_name(
            session,
            user_id=str(ctx.user_id),
            project_id=project_id,
            name=args.entity_name,
            exclude_project_ids=exclude,
        )
        if not matches:
            return {"found": False, "entity_name": args.entity_name}
        top = matches[0]
        detail = await get_entity_with_relations(
            session, user_id=str(ctx.user_id), entity_id=top.id
        )
    if detail is None:
        return {"found": False, "entity_name": args.entity_name}

    relations = [
        {
            "subject": r.subject_name,
            "predicate": r.predicate,
            "object": r.object_name,
        }
        for r in detail.relations
    ]
    return {
        "found": True,
        "entity": {
            "name": detail.entity.name,
            "kind": detail.entity.kind,
            "aliases": detail.entity.aliases,
            "confidence": detail.entity.confidence,
        },
        "relations": relations,
        "relations_truncated": detail.relations_truncated,
        "other_matches": [e.name for e in matches[1 : 1 + _OTHER_MATCHES_CAP]],
    }


async def _handle_memory_timeline(
    ctx: ToolContext, args: MemoryTimelineArgs
) -> dict:
    await _require_project_owner_memory(ctx)  # H-U: owner-only project gate
    project_id = str(ctx.project_id) if ctx.project_id else None
    exclude = await _diary_exclusion(ctx)  # D16 — no diary leak into a non-assistant session
    async with neo4j_session() as session:
        participant_candidates: list[str] | None = None
        if args.entity_name:
            matches = await find_entities_by_name(
                session,
                user_id=str(ctx.user_id),
                project_id=project_id,
                name=args.entity_name,
                exclude_project_ids=exclude,
            )
            if not matches:
                # Entity not found ⇒ empty candidate list ⇒ zero events
                # (mirrors the C10 timeline router; avoids leaking
                # "this entity does not exist").
                participant_candidates = []
            else:
                e = matches[0]
                participant_candidates = sorted(
                    {c for c in {e.name, e.canonical_name, *e.aliases} if c}
                )
        events, total = await list_events_filtered(
            session,
            user_id=str(ctx.user_id),
            project_id=project_id,
            after_order=None,
            before_order=None,
            event_date_from=args.from_date,
            event_date_to=args.to_date,
            participant_candidates=participant_candidates,
            limit=args.limit,
            offset=0,
            exclude_project_ids=exclude,  # D16 — the timeline must also drop diary events (audit HIGH-1)
        )

    items = [
        {
            "title": ev.title,
            # /review-impl LOW#4 — cap the per-event summary so a
            # 50-event page can't blow the LLM context (design D7).
            "summary": _truncate(ev.summary) if ev.summary else None,
            "event_date": ev.event_date_iso,
            "participants": ev.participants,
        }
        for ev in events
    ]
    # L1/L2 reference-first (§6b): at detail="summary" drop the per-event
    # `summary` body, keeping title/date/participants. `total_matching` is the
    # DB-side match count (independent of the page); `meta` reports page
    # total/returned/truncated.
    projected, meta = apply_response_contract(
        items, ref_fields=MEMORY_TIMELINE_REF_FIELDS, detail=args.detail,
    )
    return {
        "events": projected, "count": len(projected),
        "total_matching": total, **meta,
    }


async def _handle_memory_remember(
    ctx: ToolContext, args: MemoryRememberArgs
) -> dict:
    # K21.7 guardrail — rate limit BEFORE everything else so a chatty
    # LLM can't pollute memory beyond the per-session cap. A *queued*
    # fact still consumes a slot (K21-C design D6): the cap bounds how
    # often the tool fires, not how often a write commits.
    if not await _check_remember_rate_limit(ctx.redis, ctx.session_id):
        memory_remember_rate_limited_total.inc()
        raise ToolExecutionError(
            "the assistant has reached its memory_remember limit "
            f"({settings.tool_remember_limit_per_session}) for this "
            "chat session"
        )
    # H-U: a write must target a project the caller OWNS — gate before the
    # queue-vs-write branch so the direct-write path (which would otherwise merge a
    # fact tagged with someone else's project_id) can't bypass it.
    await _require_project_owner_memory(ctx)
    project_id = str(ctx.project_id) if ctx.project_id else None
    # /review-impl MED#2 — neutralize injection patterns in the
    # LLM-supplied text, matching the extraction write path
    # (KSA §5.1.5). `neutralize_injection` is idempotent + safe on
    # any string; the hit count is for the shared metric only.
    #
    # K21-C design D6 / REVIEW-DESIGN R1: this runs BEFORE the
    # queue-vs-write branch so BOTH paths inherit the defense — the
    # confirm endpoint writes the queued text as-is, so it must be
    # neutralized at queue time, not at write time.
    sanitized_text, _ = neutralize_injection(args.fact_text, project_id=project_id)

    # K21-C design D4/D6 — queue-vs-write decision. A project with
    # `memory_remember_confirm` on holds the fact in
    # knowledge_pending_facts for explicit user confirmation instead
    # of writing it straight to the graph. A no-project chat has no
    # project setting to read, so it always writes directly.
    if ctx.project_id is not None:
        project = await ctx.projects_repo.get(ctx.user_id, ctx.project_id)
        if project is not None and project.memory_remember_confirm:
            pending = await ctx.pending_facts_repo.queue(
                ctx.user_id,
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                fact_type=args.fact_type,
                fact_text=sanitized_text,
            )
            # The LLM sees `queued` and tells the user the fact is
            # awaiting their confirmation (design D6).
            return {
                "queued": True,
                "pending_fact_id": str(pending.pending_fact_id),
                "fact_text": pending.fact_text,
                "fact_type": pending.fact_type,
            }

    async with neo4j_session() as session:
        fact = await merge_fact(
            session,
            user_id=str(ctx.user_id),
            project_id=project_id,
            type=args.fact_type,
            content=sanitized_text,
            confidence=TOOL_FACT_CONFIDENCE,
            pending_validation=False,
            source_type=TOOL_FACT_SOURCE_TYPE,
        )
    return {
        "remembered": True,
        "fact_id": fact.id,
        "fact_type": fact.type,
        "confidence": fact.confidence,
    }


async def _handle_memory_forget(
    ctx: ToolContext, args: MemoryForgetArgs
) -> dict:
    # H-U: no project gate needed — forget operates on a single fact addressed by
    # id and invalidate_fact is OWNER-keyed (user_id scoped), so a fact belonging to
    # another user simply doesn't match (→ "no matching fact"). The owner boundary
    # here is the user_id, not a project.
    async with neo4j_session() as session:
        fact = await invalidate_fact(
            session, user_id=str(ctx.user_id), fact_id=args.fact_id
        )
    if fact is None:
        return {"invalidated": False, "reason": "no matching fact found"}
    return {"invalidated": True, "fact_id": fact.id}


_HANDLERS = {
    "memory_search": _handle_memory_search,
    "story_search": _handle_story_search,
    "memory_recall_entity": _handle_memory_recall_entity,
    "memory_timeline": _handle_memory_timeline,
    "memory_remember": _handle_memory_remember,
    "memory_forget": _handle_memory_forget,
    # Lane LF — KG ontology MCP tools (R + reversible W). Registered here so
    # the executor dispatches them through the SAME validate→dispatch→metrics
    # path as the memory tools; their ARG_MODELS are appended in definitions.py.
    **GRAPH_SCHEMA_HANDLERS,
    # Knowledge-project lifecycle (kg_project_create) — the book↔KG bootstrap the
    # schema/extraction/wiki tools depend on (D-KG-LF-PROJECT-CREATE-MCP).
    **PROJECT_TOOL_HANDLERS,
    # Cost-gated job triggers (kg_build_graph) — mint a confirm-token; the human
    # confirms + the job starts in the confirm route (D-KG-LF-BUILDKG-MCP).
    **BUILD_TOOL_HANDLERS,
    # W11-M2 reader "ask the lore" tools — spoiler-windowed reads, cutoff server-
    # enforced from the reader's own position (lore_ask/browse/entity/timeline).
    **READER_TOOL_HANDLERS,
}


# ── dispatch + metrics wrapper ────────────────────────────────────────


def _fmt_validation_error(exc: ValidationError) -> str:
    """Compact human/LLM-readable arg-validation message."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts)


async def execute_tool(ctx: ToolContext, tool_name: str, tool_args: dict) -> ToolResult:
    """Validate + dispatch one LLM tool call. Returns a `ToolResult`
    for ok / tool-error outcomes; re-raises on an infrastructure
    failure so the endpoint can answer 503."""
    start = time.monotonic()
    metric_tool = tool_name if tool_name in ARG_MODELS else "unknown"
    outcome = "infra_error"
    result_payload: dict | None = None
    try:
        arg_model = ARG_MODELS.get(tool_name)
        if arg_model is None:
            outcome = "tool_error"
            return ToolResult(
                success=False, error=f"unknown tool: {tool_name!r}"
            )
        try:
            args: BaseModel = arg_model.model_validate(tool_args)
        except ValidationError as exc:
            outcome = "tool_error"
            return ToolResult(
                success=False,
                error=f"invalid arguments: {_fmt_validation_error(exc)}",
            )

        try:
            # H-I: resolve the effective project scope (envelope wins; else the
            # project_id arg) BEFORE dispatch, so every project-scoped handler sees
            # the same ctx.project_id and its owner gate validates it.
            ctx = _resolve_project_scope(ctx, args)
            result_payload = await _HANDLERS[tool_name](ctx, args)
        except ToolExecutionError as exc:
            outcome = "tool_error"
            return ToolResult(
                success=False, error=str(exc), code=exc.code, detail=exc.detail,
            )

        outcome = "ok"
        return ToolResult(success=True, result=result_payload)
    except Exception:
        # Unexpected — Neo4j down, a repo bug, etc. Re-raise so the
        # endpoint maps it to 503; never let it masquerade as a tool
        # result.
        outcome = "infra_error"
        logger.exception("K21: tool %r failed with an infrastructure error",
                          tool_name)
        raise
    finally:
        tool_calls_total.labels(tool_name=metric_tool, outcome=outcome).inc()
        tool_call_duration_seconds.labels(tool_name=metric_tool).observe(
            time.monotonic() - start
        )
        if outcome == "ok" and result_payload is not None:
            tool_call_result_size_bytes.labels(tool_name=metric_tool).observe(
                len(json.dumps(result_payload, default=str))
            )
