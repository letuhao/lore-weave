"""W11-M2 — reader "ask the lore" MCP tools (spec §4.2).

The reader's chat agent calls these to explore a book's lore SPOILER-SAFELY. The
cutoff is SERVER-ENFORCED from the reader's OWN furthest-read chapter — never an
LLM-supplied argument. Every handler:

  1. grant-checks the caller (≥ VIEW) and resolves the project OWNER to read as
     (`_resolve_project_owner`, anti-oracle: a non-grantee gets "project not found");
  2. fetches the CALLER's reading position (`book_client.get_reading_position`);
  3. mints the two spoiler axes from that ONE position — the KG event ceiling
     (`resolve_before_order`) and the passage/chapter ceiling
     (`resolve_before_sort_order`), both `-1` (fail-closed) when the position can't
     be pinned;
  4. runs windowed glossary + KG + RAG reads AS THE OWNER.

FAIL-CLOSED is the whole point: a reader whose position is unknown (`before_* < 0`)
sees NOTHING past their frontier — never the whole book. All reads are Tier-R,
scope `project`. Evidence-only: `lore_ask` returns an evidence bundle the caller's
agent composes an answer from on its OWN BYOK model — no server-side LLM spend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.clients.glossary_client import (
    GlossaryAnchorMalformed,
    GlossaryAnchorUnavailable,
    get_glossary_client,
)
from app.clients.grant_client import GrantLevel
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import resolve_kg_entity_id_by_glossary_id
from app.db.neo4j_repos.entity_status import statuses_detail_at_order
from app.db.neo4j_repos.events import list_events_filtered
from app.db.neo4j_repos.facts import list_facts_for_entity
from app.search.retriever import run_hybrid_search
from app.spoiler_window import resolve_before_order, resolve_before_sort_order
from app.tools.argbase import ProjectScopedArgs
from app.tools.graph_schema_tools import _resolve_project_owner

if TYPE_CHECKING:
    from app.db.models import Project
    from app.tools.executor import ToolContext

logger = logging.getLogger(__name__)

_READER_LIMIT_MAX = 50
_READER_LIMIT_DEFAULT = 25


class _ReaderScope:
    """Resolved reader read-scope: the owner to read AS, the project, the book,
    and the two spoiler axes minted from the reader's OWN furthest-read position."""

    __slots__ = ("owner", "project", "project_id", "book_id",
                 "before_order", "before_sort_order", "position_pinned")

    def __init__(
        self, owner: UUID, project: "Project", project_id: str, book_id: UUID | None,
        before_order: int, before_sort_order: int, position_pinned: bool,
    ) -> None:
        self.owner = owner
        self.project = project
        self.project_id = project_id
        self.book_id = book_id
        self.before_order = before_order              # KG event axis (inclusive-through-N; -1 fail-closed)
        self.before_sort_order = before_sort_order    # passage/chapter axis (inclusive N; -1 fail-closed)
        self.position_pinned = position_pinned        # False ⇒ reader has no resolvable position


async def _resolve_reader(ctx: "ToolContext") -> _ReaderScope:
    """Grant-gate the reader (VIEW), resolve the owner to read as, and mint the
    spoiler axes from the CALLER's own reading position (fail-closed on any gap)."""
    from app.tools.executor import ToolExecutionError

    # The reader tools need the book-service client (reading position) + reranker
    # (lore_ask RAG). They're Optional on ToolContext; the live MCP surface always
    # wires them, but a ToolContext built without them (a test, a future in-process
    # caller) must get a clean tool error, not an AttributeError → infra 5xx. Mirrors
    # the story_search handler's guard.
    if ctx.book_client is None:
        raise ToolExecutionError("reader lore tools are not available on this surface")
    owner = await _resolve_project_owner(ctx, GrantLevel.VIEW)  # anti-oracle inside
    assert ctx.project_id is not None  # _resolve_project_owner raises when None
    project = await ctx.projects_repo.get(owner, ctx.project_id)
    if project is None:
        raise ToolExecutionError("project not found")
    book_id = project.book_id
    # A book-less project has no reading axis → fail-closed empty (before_* = -1).
    if book_id is None:
        return _ReaderScope(owner, project, str(ctx.project_id), None, -1, -1, False)
    # The reader's OWN position (ctx.user_id) — NEVER a tool argument. None on any gap.
    chapter_id = await ctx.book_client.get_reading_position(book_id, ctx.user_id)
    before_order, available = await resolve_before_order(ctx.book_client, chapter_id)
    before_sort_order, _ = await resolve_before_sort_order(ctx.book_client, chapter_id)
    return _ReaderScope(
        owner, project, str(ctx.project_id), book_id,
        before_order, before_sort_order, available,
    )


async def _windowed_canon(scope: _ReaderScope, *, kind: str | None, limit: int) -> list[dict]:
    """The reader's spoiler-windowed CANON cast (authored glossary entities). Uses
    glossary's first-appearance window: pass `before_sort_order + 1` because glossary
    is EXCLUSIVE (`chapter_index < before_chapter_index`) while the axis is inclusive-
    through-N — so a reader AT chapter N sees N's canon, not N+1's. FAIL-CLOSED: an
    unpinned position (`before_sort_order < 0`) returns [] (never the full cast).
    Glossary outage degrades to [] — never leak, never raise."""
    if scope.book_id is None or scope.before_sort_order < 0:
        return []
    try:
        rows = await get_glossary_client().list_known_entities_for_chapter(
            scope.book_id,
            before_chapter_index=scope.before_sort_order + 1,
            # recency_window=0 → NO recency filter (the glossary default 100 is for the
            # extraction anchor's "recent context", and would silently drop an entity
            # the reader met but hasn't seen in ~100 chapters). A reader's "who have I
            # met" cast wants EVERYONE introduced by their chapter, bounded only by the
            # before_chapter_index spoiler cutoff.
            recency_window=0,
            min_frequency=1,
            limit=limit,
        )
    except (GlossaryAnchorUnavailable, GlossaryAnchorMalformed) as exc:
        logger.warning("reader canon window unavailable (degrading to empty): %s", exc)
        return []
    if kind:
        # The glossary known-entities row serializes the kind as `kind_code`
        # (extraction_handler.go getKnownEntities); `kind`/`entity_kind` are NOT
        # present, so filtering on them would drop EVERY row.
        want = kind.strip().lower()
        rows = [
            r for r in rows
            if str(r.get("kind_code") or r.get("kind") or "").lower() == want
        ]
    return rows


# ── lore_ask ─────────────────────────────────────────────────────────────────
class LoreAskArgs(ProjectScopedArgs):
    """`lore_ask` — the composite ask-the-lore read. Returns a spoiler-windowed
    EVIDENCE BUNDLE (canon entities + manuscript passages); YOU compose the answer
    from it on your own model."""

    query: str = Field(
        min_length=1, max_length=1000,
        description="What the reader is asking about — a name, a relationship, or "
        "'what has happened so far'. In natural language.",
    )
    limit: int = Field(
        default=_READER_LIMIT_DEFAULT, ge=1, le=_READER_LIMIT_MAX,
        description=f"Max passages + canon entities each (default {_READER_LIMIT_DEFAULT}).",
    )


async def _handle_lore_ask(ctx: "ToolContext", args: LoreAskArgs) -> dict:
    scope = await _resolve_reader(ctx)
    passages: list[dict[str, Any]] = []
    if scope.book_id is not None:
        # RAG is spoiler-windowed on the passage axis (M1); -1 fail-closes to [].
        result = await run_hybrid_search(
            user_id=scope.owner, book_id=scope.book_id, query=args.query,
            project=scope.project, book_client=ctx.book_client,
            embedding_client=ctx.embedding_client, reranker_client=ctx.reranker_client,
            limit=args.limit, before_sort_order=scope.before_sort_order,
        )
        passages = result.hits
    canon = await _windowed_canon(scope, kind=None, limit=args.limit)
    return {
        "query": args.query,
        "entities": canon,          # authored canon, windowed to the reader's chapter
        "passages": passages,       # manuscript snippets, windowed
        "window_available": scope.position_pinned,
        "note": "Spoiler-windowed to the reader's furthest-read chapter. Compose the "
                "answer from this evidence only; if window_available is false the "
                "reader's position could not be pinned, so nothing is shown.",
    }


# ── lore_browse_entities ─────────────────────────────────────────────────────
class LoreBrowseEntitiesArgs(ProjectScopedArgs):
    """`lore_browse_entities` — the spoiler-windowed CANON cast (characters, places,
    factions the reader has met so far)."""

    kind: str | None = Field(
        default=None,
        description="Optional — restrict to one entity kind (e.g. 'character', "
        "'location'). Omit for the whole windowed cast.",
    )
    limit: int = Field(
        default=_READER_LIMIT_MAX, ge=1, le=_READER_LIMIT_MAX,
        description=f"Max entities (default/max {_READER_LIMIT_MAX}).",
    )


async def _handle_lore_browse_entities(ctx: "ToolContext", args: LoreBrowseEntitiesArgs) -> dict:
    scope = await _resolve_reader(ctx)
    canon = await _windowed_canon(scope, kind=args.kind, limit=args.limit)
    return {"entities": canon, "window_available": scope.position_pinned}


# ── lore_entity ──────────────────────────────────────────────────────────────
class LoreEntityArgs(ProjectScopedArgs):
    """`lore_entity` — one entity's spoiler-windowed status + known facts."""

    entity_id: str = Field(
        min_length=1, max_length=200,
        description="The entity id returned by lore_browse_entities / lore_ask "
        "(the canon glossary entity id).",
    )


async def _handle_lore_entity(ctx: "ToolContext", args: LoreEntityArgs) -> dict:
    scope = await _resolve_reader(ctx)
    async with neo4j_session() as session:
        # The reader holds a GLOSSARY entity id (from the canon cast). Resolve it to
        # the anchored KG :Entity.id — SCOPED to the reader's project — before reading
        # KG facts/status. This (a) fixes the glossary-id≠KG-id mismatch that made
        # every lore_entity read empty, and (b) confines the read to the reader's
        # granted book: a glossary id from another of the owner's projects → None.
        kg_id = await resolve_kg_entity_id_by_glossary_id(
            session, user_id=str(scope.owner), project_id=scope.project_id,
            glossary_entity_id=args.entity_id,
        )
        if kg_id is None:
            # Canon entity with no KG anchor (or an id outside this project) → no KG
            # data, honestly reported (not a silent wrong "active/empty").
            return {
                "entity_id": args.entity_id, "kg_entity_id": None,
                "status": None, "facts": [],
                "window_available": scope.position_pinned,
                "note": "This entity has no derived knowledge-graph record in this book.",
            }
        # before_order is the resolved event ceiling; ALWAYS an int (-1 when the
        # reader's position is unknown) — NEVER None (which would mean "no window" and
        # leak every fact). facts filter from_order <= before_order; -1 → no facts.
        # project_id scopes the fact read to the reader's granted book (tenant-safe).
        facts = await list_facts_for_entity(
            session, user_id=str(scope.owner), entity_id=kg_id,
            before_order=scope.before_order, project_id=scope.project_id,
        )
        statuses = await statuses_detail_at_order(
            session, user_id=str(scope.owner), project_id=scope.project_id,
            entity_ids=[kg_id], at_order=scope.before_order,
        )
    st = statuses.get(kg_id) or {"status": "active", "from_order": None}
    return {
        "entity_id": args.entity_id,
        "kg_entity_id": kg_id,
        "status": st["status"],
        "facts": [f.model_dump(mode="json") for f in facts],
        "window_available": scope.position_pinned,
    }


# ── lore_timeline ────────────────────────────────────────────────────────────
class LoreTimelineArgs(ProjectScopedArgs):
    """`lore_timeline` — the spoiler-windowed sequence of events up to the reader's
    position."""

    limit: int = Field(
        default=_READER_LIMIT_MAX, ge=1, le=_READER_LIMIT_MAX,
        description=f"Max events (default/max {_READER_LIMIT_MAX}).",
    )


async def _handle_lore_timeline(ctx: "ToolContext", args: LoreTimelineArgs) -> dict:
    scope = await _resolve_reader(ctx)
    # Belt-and-suspenders fail-closed: an unpinned position skips the query entirely,
    # rather than relying on the repo's before_order=-1 semantics to return nothing.
    if scope.before_order < 0:
        return {"events": [], "total": 0, "window_available": scope.position_pinned}
    async with neo4j_session() as session:
        events, total = await list_events_filtered(
            session, user_id=str(scope.owner), project_id=scope.project_id,
            after_order=None, before_order=scope.before_order,
            limit=args.limit, offset=0,
        )
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "total": total,
        "window_available": scope.position_pinned,
    }


READER_TOOL_ARG_MODELS: dict[str, type[BaseModel]] = {
    "lore_ask": LoreAskArgs,
    "lore_browse_entities": LoreBrowseEntitiesArgs,
    "lore_entity": LoreEntityArgs,
    "lore_timeline": LoreTimelineArgs,
}

READER_TOOL_HANDLERS = {
    "lore_ask": _handle_lore_ask,
    "lore_browse_entities": _handle_lore_browse_entities,
    "lore_entity": _handle_lore_entity,
    "lore_timeline": _handle_lore_timeline,
}
