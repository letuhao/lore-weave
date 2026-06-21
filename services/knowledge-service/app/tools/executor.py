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
    tool, a rate-limit rejection, or "no project in scope" are
    `tool_error`: caught here, returned as `success=False`. Anything
    unexpected (Neo4j down, etc.) is an `infra_error`: re-raised so the
    endpoint maps it to HTTP 503. A tool failure never crashes chat.
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
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import redis.asyncio as aioredis
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:  # deps used only as ToolContext type hints (lane LF)
    from app.clients.grant_client import GrantClient
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
)
from app.tools.graph_schema_tools import GRAPH_SCHEMA_HANDLERS
from app.tools.project_tools import PROJECT_TOOL_HANDLERS

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


# ── result / context types ────────────────────────────────────────────


@dataclass
class ToolResult:
    """Outcome of one tool call. `success=False` ⇒ `error` is set and
    `result` is None; `success=True` ⇒ `result` is the payload dict."""

    success: bool
    result: dict | None = None
    error: str | None = None


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
    exception, which propagates as an infra error."""


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


# ── handlers ──────────────────────────────────────────────────────────


async def _handle_memory_search(ctx: ToolContext, args: MemorySearchArgs) -> dict:
    if ctx.project_id is None:
        raise ToolExecutionError(
            "a project must be in scope to search passages"
        )
    project = await ctx.projects_repo.get(ctx.user_id, ctx.project_id)
    if project is None:
        raise ToolExecutionError("project not found")
    if project.embedding_model is None or project.embedding_dimension is None:
        return {"hits": [], "count": 0,
                "note": "this project has no indexed memory yet"}
    if project.embedding_dimension not in SUPPORTED_PASSAGE_DIMS:
        return {"hits": [], "count": 0,
                "note": "this project's embedding model is not supported"}

    try:
        embed = await ctx.embedding_client.embed(
            user_id=ctx.user_id,
            model_source="user_model",
            model_ref=project.embedding_model,
            texts=[args.query],
        )
    except EmbeddingError as exc:
        raise ToolExecutionError(
            f"memory search is temporarily unavailable: {exc}"
        )
    if not embed.embeddings or not embed.embeddings[0]:
        return {"hits": [], "count": 0}

    try:
        async with neo4j_session() as session:
            hits = await find_passages_by_vector(
                session,
                user_id=str(ctx.user_id),
                project_id=str(ctx.project_id),
                query_vector=embed.embeddings[0],
                dim=project.embedding_dimension,
                embedding_model=project.embedding_model,
                source_type=args.source_type,
                limit=args.limit,
            )
    except ValueError as exc:
        # query_vector length disagrees with the project's stored dim
        # — user changed embedding model out-of-band.
        raise ToolExecutionError(f"memory search failed: {exc}")

    items = [
        {
            "text": _truncate(h.passage.text),
            "source_type": h.passage.source_type,
            "score": round(h.raw_score, 4),
        }
        for h in hits[: args.limit]
    ]
    return {"hits": items, "count": len(items)}


async def _handle_memory_recall_entity(
    ctx: ToolContext, args: MemoryRecallEntityArgs
) -> dict:
    project_id = str(ctx.project_id) if ctx.project_id else None
    async with neo4j_session() as session:
        matches = await find_entities_by_name(
            session,
            user_id=str(ctx.user_id),
            project_id=project_id,
            name=args.entity_name,
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
    project_id = str(ctx.project_id) if ctx.project_id else None
    async with neo4j_session() as session:
        participant_candidates: list[str] | None = None
        if args.entity_name:
            matches = await find_entities_by_name(
                session,
                user_id=str(ctx.user_id),
                project_id=project_id,
                name=args.entity_name,
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
    return {"events": items, "count": len(items), "total_matching": total}


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
    async with neo4j_session() as session:
        fact = await invalidate_fact(
            session, user_id=str(ctx.user_id), fact_id=args.fact_id
        )
    if fact is None:
        return {"invalidated": False, "reason": "no matching fact found"}
    return {"invalidated": True, "fact_id": fact.id}


_HANDLERS = {
    "memory_search": _handle_memory_search,
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
            result_payload = await _HANDLERS[tool_name](ctx, args)
        except ToolExecutionError as exc:
            outcome = "tool_error"
            return ToolResult(success=False, error=str(exc))

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
