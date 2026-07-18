"""POST /internal/context/build — builds a memory block for chat-service.

Sits under the /internal/* route prefix so the existing
require_internal_token dependency gates access. Trusts the caller's
user_id and project_id (chat-service validates JWT + project ownership
before issuing this call).

The endpoint is deliberately thin: request validation → repo + client
dependency injection → builder dispatch → response marshalling. All
the heavy lifting is in app.context.*.

Dependencies are supplied via FastAPI Depends so tests can override
them with `app.dependency_overrides[...]` instead of monkey-patching
module globals.
"""

import asyncio
import json
import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient, GlossaryEntityForContext
from app.clients.llm_client import LLMClient
from app.context.builder import ProjectNotFound, build_context
from app.context.selectors.glossary import select_glossary_semantic
from app.db.neo4j import neo4j_session
from app.db.repositories.entity_access import EntityAccessRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo
from app.db.repositories.working_memory import WorkingMemoryRepo
from app.deps import (
    get_embedding_client,
    get_entity_access_repo,
    get_glossary_client,
    get_llm_client,
    get_projects_repo,
    get_summaries_repo,
    get_working_memory_repo,
)
from app.metrics import context_build_duration_seconds
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

# Track 4 P0 — strong refs to in-flight fire-and-forget telemetry tasks. asyncio
# only keeps WEAK references to tasks, so a bare create_task() can be GC'd before it
# runs (sporadic salience-write loss under load). Hold the ref until the task is done.
_bg_tasks: set = set()

# Re-exported for back-compat with existing test dependency_overrides
# that reference `app.routers.context.get_*_repo`. The canonical home
# is `app.deps`.
__all__ = [
    "router",
    "get_summaries_repo",
    "get_projects_repo",
    "get_glossary_client",
]

router = APIRouter(
    prefix="/internal/context",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


# ── request / response models ──────────────────────────────────────────────


class ContextBuildRequest(BaseModel):
    user_id: UUID
    session_id: UUID | None = None
    project_id: UUID | None = None
    # Track B B1(2) — multi-KG: a SET of projects to UNION into one context (shared
    # budget, cross-project dedup + rank). Takes precedence over project_id; the
    # single field stays for back-compat + salience attribution.
    project_ids: list[UUID] | None = Field(default=None, max_length=16)
    # User's current message — used as the glossary FTS query in Mode 2.
    # 4k char cap fits legitimate chat turns without giving callers a
    # silent DoS knob.
    message: str = Field(default="", max_length=4000)
    # S6 (optional): the display/target language for entity aliases shown in context.
    # Omitted → source-language aliases only (back-compat).
    language: str | None = Field(default=None, max_length=35)
    # T5 (Context Budget Law D2): the entity-presence intent gate's decision. False
    # ⇒ the turn references no book lore, so skip the EXPENSIVE retrieval (passages +
    # semantic glossary + LLM) and serve the light static path. Default True keeps
    # every existing caller's behavior byte-identical (a versioned opt-in).
    grounding: bool = True
    # M1b (2026-07-06): the chapter the editor `<Chat>` panel is open on. When
    # present (editor turns only), the Mode-3 L3 ranker boosts passages near this
    # chapter (working-scope boost). Omitted on every non-editor turn → boost inert.
    # Additive/optional so an older chat-service that never sends it is byte-identical.
    current_chapter_id: UUID | None = None
    # The session model's real resolved context window, so Mode 3's flat
    # `mode3_token_budget` can scale up for a genuinely larger window instead of
    # every model being capped at the same number. Additive/optional so an older
    # chat-service that never sends it keeps the flat default (byte-identical).
    context_length: int | None = None


class ContextBuildResponse(BaseModel):
    # from_attributes=True lets model_validate read fields off the builder's
    # BuiltContext dataclass directly, so the router never has to hand-copy
    # fields from one shape to the other.
    model_config = ConfigDict(from_attributes=True)

    mode: str
    context: str
    recent_message_count: int
    token_count: int
    # K18.9 — cacheable prefix + per-message suffix. Invariant:
    # context == stable_context + volatile_context. Default to "" so
    # older chat-service clients that read only `context` keep working.
    stable_context: str = ""
    volatile_context: str = ""
    # K21.12-BE (design D9) — per-project tool-calling toggle. Read off
    # BuiltContext via from_attributes. Default True so an older
    # chat-service that doesn't read this field still behaves as before
    # (tools offered) and a degraded build stays tool-enabled.
    tool_calling_enabled: bool = True
    # WS-4C Half A — per-project canon auto-capture toggle. Read off BuiltContext
    # via from_attributes. Defaults FALSE (unlike tool_calling_enabled): capture
    # spends the user's tokens, so an unset/degraded value must fail CLOSED.
    canon_capture_enabled: bool = False
    # Interview-roleplay — the rendered working_memory anchor text (charter +
    # state). chat-service pins this into the system block AND tail-injects it
    # (depth-0). Default "" so a session with no working_memory block, and an
    # older builder that doesn't set it, both stay backward-compatible. Populated
    # by the working_memory selector (M4). See contracts/interview/README.md.
    working_memory: str = ""
    # Chat Quality Wave W1 — per-section token split of `context` (e.g.
    # {"glossary_entities": .., "facts": .., "passages": .., "summaries": ..,
    # "instructions": ..}), read off BuiltContext.sections. ADDITIVE: default {}
    # so an older builder / degraded path stays backward-compatible; chat-service
    # nests it under the contextBudget frame's memory_knowledge category.
    sections: dict[str, int] = {}


class ProjectBookResponse(BaseModel):
    book_id: str | None = None


@router.get("/project-book/{project_id}", response_model=ProjectBookResponse)
async def project_book(
    project_id: UUID,
    user_id: UUID,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> ProjectBookResponse:
    """T5 (audit) — resolve a knowledge project's linked `book_id` for the chat
    entity-presence gate. The gate needs the BOOK id (glossary known-entities is
    book-scoped) but a chat session carries the KNOWLEDGE project id; this is the
    project→book bridge, resolvable on turn 1 (owner-scoped via projects_repo.get).
    `book_id=None` for a Mode-1 (no-book) project or a stale/foreign id — the gate
    then stays open (bias-to-include)."""
    project = await projects_repo.get(user_id, project_id)
    book_id = str(project.book_id) if project and project.book_id else None
    return ProjectBookResponse(book_id=book_id)


@router.post("/build", response_model=ContextBuildResponse)
async def build(
    req: ContextBuildRequest,
    summaries_repo: SummariesRepo = Depends(get_summaries_repo),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    llm_client: LLMClient = Depends(get_llm_client),
    working_memory_repo: WorkingMemoryRepo = Depends(get_working_memory_repo),
    entity_access_repo: EntityAccessRepo = Depends(get_entity_access_repo),
) -> ContextBuildResponse:
    # K6.5: observe end-to-end build duration. Label distinguishes
    # successful modes (no_project/static/full) from each error path
    # so dashboards can separate "user sent a stale project_id"
    # (routine 404) from "builder crashed" (alert-worthy 500).
    _t0 = time.monotonic()
    _mode_label = "error"
    try:
        built = await build_context(
            summaries_repo,
            projects_repo,
            glossary_client,
            user_id=req.user_id,
            project_id=req.project_id,
            message=req.message,
            embedding_client=embedding_client,
            llm_client=llm_client,
            language=req.language,
            entity_access_repo=entity_access_repo,
            project_ids=req.project_ids,
            grounding=req.grounding,
            current_chapter_id=req.current_chapter_id,
            context_length=req.context_length,
        )
        _mode_label = built.mode
    except ProjectNotFound:
        _mode_label = "not_found"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    except Exception as exc:
        logger.exception("context build failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="context build failed",
        )
    finally:
        context_build_duration_seconds.labels(mode=_mode_label).observe(
            time.monotonic() - _t0
        )
    # Track 4 P0 — record which entities were surfaced, fire-and-forget so the
    # salience telemetry write is off the request latency path and can never fail
    # the build. Only when a project is scoped and something was surfaced.
    #
    # Track B B1(2) (D-MULTI-SALIENCE-WRITEBACK): in MULTI mode `req.project_id` is
    # None (we deliberately don't send a single anchor, to avoid misattributing the
    # union's entities to one project), so the single-project branch skips. Instead
    # record PER SOURCE PROJECT from `surfaced_by_project` — correct attribution, so
    # multi-KG sessions LEARN salience too.
    def _record(project_id, entity_ids):
        task = asyncio.create_task(
            entity_access_repo.record_accesses(
                req.user_id, project_id, entity_ids,
                session_id=req.session_id,  # P3b — feedback attribution stamp
            )
        )
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)

    if built.surfaced_by_project:  # multi mode → attribute per source project
        for pid, eids in built.surfaced_by_project.items():
            if eids:
                _record(UUID(pid), eids)
    elif req.project_id is not None and built.surfaced_entity_ids:
        _record(req.project_id, built.surfaced_entity_ids)

    resp = ContextBuildResponse.model_validate(built)
    # Interview-roleplay (M4): attach the session's working_memory block (charter
    # + state) as JSON so chat-service can pin + tail-anchor it. Best-effort —
    # a lookup failure must never fail the context build (chat-service falls back
    # to its own seed, EC-4). Only when the session has a block.
    if req.session_id is not None:
        try:
            block = await working_memory_repo.get(req.session_id, req.user_id)
            if block is not None:
                resp.working_memory = json.dumps(block)
        except Exception:
            logger.warning("working_memory lookup failed for session %s", req.session_id,
                           exc_info=True)
    return resp


# ── mui #4 — semantic glossary selection (architecture B) ───────────────────


class GlossarySemanticRequest(BaseModel):
    user_id: UUID
    project_id: UUID
    query: str = Field(default="", max_length=4000)
    max_entities: int = 20
    max_tokens: int = 800


class GlossarySemanticResponse(BaseModel):
    items: list[GlossaryEntityForContext]


@router.post("/glossary-semantic", response_model=GlossarySemanticResponse)
async def glossary_semantic(
    req: GlossarySemanticRequest,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
) -> GlossarySemanticResponse:
    """Semantic glossary entities for a query, ranked by entity-embedding
    similarity. Used by composition's packer (and available to any caller that
    wants vector ranking). Best-effort: returns `{items: []}` on a missing
    project / no embedding model / any failure, so the caller falls back to
    glossary's FTS select-for-context. Never 500s on the degraded paths.
    """
    project = await projects_repo.get(req.user_id, req.project_id)
    if project is None or project.book_id is None or not project.embedding_model:
        return GlossarySemanticResponse(items=[])

    async with neo4j_session() as session:
        items = await select_glossary_semantic(
            session=session,
            embedding_client=embedding_client,
            glossary_client=glossary_client,
            user_id=req.user_id,
            project_id=req.project_id,
            book_id=project.book_id,
            embedding_model=project.embedding_model,
            embedding_dimension=project.embedding_dimension,
            query=req.query,
            max_entities=req.max_entities,
            max_tokens=req.max_tokens,
        )
    return GlossarySemanticResponse(items=items)
