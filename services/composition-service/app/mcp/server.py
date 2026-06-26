"""S-COMPOSE — MCP server facade for composition-service (MCP fan-out 2026-06-20).

Mounts at ``/mcp`` on the existing FastAPI app (``app/main.py``) and exposes the
§4 S-COMPOSE catalog (compose / outline / prose / canon) as MCP tools via the
shared Python kit ``loreweave_mcp`` (C-KIT-PY). Dual-run: the bespoke
``/v1/composition`` REST API is NOT removed.

DESIGN (mirrors the proven jobs-service / knowledge-service `/mcp` facades + the
fan-out plan §3 C-TOOL / §4 S-COMPOSE):

- **Identity from the envelope ONLY** (`build_tool_context`: X-Internal-Token
  constant-time check, then X-User-Id from headers) — NEVER a tool argument. Arg
  models extend `ForbidExtra` (`extra="forbid"`) so the LLM cannot smuggle a
  user_id/project ownership id past the envelope.
- **Scope = book** (C-TOOL `scope="book"`). Composition's own rows are keyed by
  `project_id` (= the knowledge project id) and the repos ALREADY filter
  `user_id = caller` (per-user isolation). On top of that per-user predicate, every
  tool gates the call through `require_book_owner` on the Work's `book_id` — the
  SAME E0-4c chokepoint the HTTP routers use (`_gate_book`): VIEW for reads, EDIT
  for writes. A non-owner / under-tier caller gets the H13 uniform
  "not found or not accessible" (no enumeration oracle).
- **Tiers**: R (reads), A (auto-write + Undo `_meta.undo_hint`), W (publish →
  confirm-token via `/v1/composition/actions/*`).
- Every tool carries validated `_meta` (`require_meta`) with tier + scope +
  synonyms feeding `find_tools` recall (H6).

PROSE TOOLS — the one honest cross-service seam. `composition_get_prose` /
`composition_write_prose` proxy book-service's **public JWT-only** draft routes;
the MCP envelope has no JWT, so we mint a short-lived service bearer for the
envelope user (see `service_bearer.py`). book-service still enforces ownership in
SQL on the JWT `sub`. **COMPOSE B integrator note:** if book-service later grows
an internal (X-Internal-Token) draft read/write + publish route, replace the
service-bearer seam with a direct internal call.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal
from uuid import UUID

import asyncpg
from mcp.server.fastmcp import Context as MCPContext

from loreweave_mcp import (
    ForbidExtra,
    GrantResolver,
    ToolContext,
    build_tool_context,
    make_stateless_fastmcp,
    mint_confirm_token,
    require_book_owner,
    require_meta,
    require_user_scope,
    uniform_not_accessible,
)

from app.clients.book_client import BookClient, BookClientError, get_book_client
from app.config import settings
from app.db.pool import get_pool
from app.db.repositories import (
    ReferenceViolationError,
    VersionMismatchError,
)
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.works import WorksRepo
from app.grant_client import GrantLevel, get_grant_client
from app.mcp.service_bearer import mint_service_bearer

logger = logging.getLogger(__name__)

__all__ = ["mcp_server", "build_mcp_app"]

mcp_server = make_stateless_fastmcp("composition")

# Confirm descriptors for the Tier-W actions (C-CONFIRM domain map → composition).
_PUBLISH_DESCRIPTOR = "composition.publish"
# Cost-gated grounded generation (the cowrite ENGINE — distinct from write_prose,
# which only SAVES prose the LLM wrote itself). Mints a confirm token; the actual
# spend happens in the confirm-route effect (app/routers/actions.py).
_GENERATE_DESCRIPTOR = "composition.generate"

# ── W4 motif-library Tier-W confirm descriptors (R2.8 / audit H-6). adopt is a
# tenancy/quota-bearing cross-tier clone (confirm-token, NOT auto-write — the
# glossary class-C adopt precedent); mine/import/conformance are LLM-spend jobs
# (confirm-token + a real usage-billing precheck + a 202+poll worker enqueue).
_MOTIF_ADOPT_DESCRIPTOR = "composition.motif_adopt"
_MOTIF_MINE_DESCRIPTOR = "composition.motif_mine"
_ARC_IMPORT_DESCRIPTOR = "composition.arc_import"
_CONFORMANCE_RUN_DESCRIPTOR = "composition.conformance_run"

# The motif kinds + the closed enums the LLM may pass (R1.4 schema). Defined here so
# the arg models below and the tests share one source.
_MotifKind = Literal["sequence", "situation", "hook", "emotion_arc", "trope", "pattern", "scheme"]


# ── shared helpers ────────────────────────────────────────────────────────────


def _ctx(ctx: MCPContext) -> ToolContext:
    """Validate the internal token + lift the envelope identity. A bad token /
    missing header surfaces as a tool error (success=False), not a 5xx."""
    return build_tool_context(ctx, settings.internal_service_token)


def _grant_resolver() -> GrantResolver:
    """Adapt composition's GrantClient to the kit's GrantResolver shape
    (`(book_id, user_id) -> int`). The client is fail-closed (a book-service
    outage → NONE), so the kit guard denies on any backend error."""
    client = get_grant_client()

    async def resolve(book_id: UUID, user_id: UUID) -> int:
        return int(await client.resolve_grant(book_id, user_id))

    return resolve


async def _work_or_deny(works: WorksRepo, tc: ToolContext, project_id: UUID):
    """Resolve the caller's Work (user-scoped) or raise the H13 uniform error.
    A None is indistinguishable from "not yours" (the repo filters on user_id)."""
    work = await works.get(tc.user_id, project_id)
    if work is None:
        raise uniform_not_accessible()
    return work


async def _gate(tc: ToolContext, book_id: UUID, level: GrantLevel) -> None:
    """Run the book-ownership guard at the operation's tier (VIEW read / EDIT
    write). Raises the H13 uniform error on denial. A fresh guard per call keeps
    the ~60s positive cache process-local + simple (matches the per-request HTTP
    gate)."""
    guard = require_book_owner(_grant_resolver(), int(level))
    await guard(tc, book_id)


def _undo(tool: str, **args: Any) -> dict[str, Any]:
    """Build the C-ACTIVITY `_meta.undo_hint` a Tier-A result carries so the FE
    activity strip can offer Undo via a verified reverse op."""
    return {"tool": tool, "args": args}


# ── W4 motif helpers ──────────────────────────────────────────────────────────

# The fields a NON-owner (a public/system motif the caller previewed but does not
# own) may see — the W1 catalog allow-list (audit B-3). NEVER the embedding vector,
# the raw source_ref lineage, the copied examples[], or owner_user_id. The owner of
# a row gets the full Motif.model_dump via _get; everyone else gets this projection.
_MOTIF_PUBLIC_FIELDS = (
    "id", "code", "language", "visibility", "kind", "category", "name", "summary",
    "genre_tags", "roles", "beats", "preconditions", "effects", "info_asymmetry",
    "tension_target", "emotion_target", "abstraction_confidence", "source",
    "status", "version", "created_at", "updated_at",
)


def _motif_public_projection(motif: Any) -> dict[str, Any]:
    """Project a Motif to the non-owner allow-list (B-3): drops embedding/raw
    source_ref/examples/owner_user_id. `motif` is a pydantic Motif row."""
    full = motif.model_dump(mode="json")
    return {k: full[k] for k in _MOTIF_PUBLIC_FIELDS if k in full}


def _motif_view(motif: Any, caller_id: UUID) -> dict[str, Any]:
    """Full dump for the owner; the allow-list projection for a system/public-not-
    owned row (so an adopter previewing a public motif sees roles/beats/conditions
    but not embedding/raw source_ref/copied examples — audit B-3)."""
    if motif.owner_user_id is not None and motif.owner_user_id == caller_id:
        return motif.model_dump(mode="json")
    return _motif_public_projection(motif)


def _motif_owner_resolver(repo: MotifRepo):
    """`require_user_scope` owner-of for a motif: returns motif.owner_user_id so the
    guard asserts owner == caller. A system row (owner NULL) or a row the caller
    cannot see resolves to a deny (the kit's nil/missing -> uniform_not_accessible).
    Used by the user-tier WRITE tools (_archive) where a system/public-not-owned
    motif is read-only to a regular user (glossary system-kind-lock parity §11)."""

    async def owner_of(tc: ToolContext, motif_id: UUID) -> UUID:
        motif = await repo.get_visible(tc.user_id, motif_id)
        if motif is None or motif.owner_user_id is None:
            # missing / foreign-private / system -> the kit maps the raise to deny.
            raise uniform_not_accessible()
        return motif.owner_user_id

    return owner_of


async def _import_source_owner(tc: ToolContext, import_source_id: UUID) -> UUID:
    """`require_user_scope` owner-of for an import_source row (§12.6/B-3 — per-user,
    structurally un-shareable: NO visibility column). Returns owner_user_id so the
    guard asserts owner == caller. The W9 import_source repo does not exist yet at
    W4 build time, so this reads the owner column directly via the pool (the row
    shape is FROZEN by F0's migrate.py)."""
    pool = get_pool()
    owner = await pool.fetchval(
        "SELECT owner_user_id FROM import_source WHERE id = $1", import_source_id
    )
    if owner is None:
        raise uniform_not_accessible()
    return owner


def _mine_estimate(*, scope: str) -> dict[str, Any]:
    """Coarse $ estimate for the confirm card + the billing precheck (W4 §3.3). Not
    exact — it gates the obvious over-quota case and drives the card's display. A
    corpus mine is pricier than a single book; an import/conformance is per-chapter.
    The real per-token cost lands when the W8/W9/W5 worker compute runs."""
    est = 0.50 if scope == "book" else 2.00
    return {"estimated_usd": est, "currency": "USD", "basis": scope}


# ── Tier R — reads ────────────────────────────────────────────────────────────


@mcp_server.tool(
    name="composition_get_work",
    description=(
        "Get the composition Work for a book/project (its status, active template, "
        "and authoring settings). The Work is the per-user authoring context layered "
        "over a book. Owner/grant-filtered — VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["composition work", "writing project", "authoring context", "get work", "compose"],
        tool_name="composition_get_work",
    ),
)
async def composition_get_work(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id (= the knowledge project id, the Work PK)."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _work_or_deny(works, tc, UUID(project_id))
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    return work.model_dump(mode="json")


@mcp_server.tool(
    name="composition_list_outline",
    description=(
        "List the outline/scene-graph of a Work — the Arc→Chapter→Scene→Beat tree "
        "plus its scene-links (setup/payoff edges). Use to see the planned structure "
        "before generating or editing. Owner/grant-filtered (VIEW)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["outline", "scene graph", "story structure", "chapters", "beats", "list outline"],
        tool_name="composition_list_outline",
    ),
)
async def composition_list_outline(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    include_archived: Annotated[bool, "Include soft-archived nodes."] = False,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _work_or_deny(works, tc, UUID(project_id))
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    outline = OutlineRepo(get_pool())
    scene_links = SceneLinksRepo(get_pool())
    pid = UUID(project_id)
    nodes = await outline.list_tree(tc.user_id, pid, include_archived=include_archived)
    links = await scene_links.list_by_project(tc.user_id, pid)
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "scene_links": [l.model_dump(mode="json") for l in links],
    }


@mcp_server.tool(
    name="composition_get_prose",
    description=(
        "Get the current DRAFT prose of a chapter (the editable body + its "
        "`draft_version` — the concurrency token you MUST pass back to write_prose). "
        "Owner/grant-filtered (VIEW)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["prose", "chapter text", "draft", "get prose", "read chapter"],
        tool_name="composition_get_prose",
    ),
)
async def composition_get_prose(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    chapter_id: Annotated[str, "The chapter's id."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _work_or_deny(works, tc, UUID(project_id))
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    book: BookClient = get_book_client()
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    try:
        draft = await book.get_draft(work.book_id, UUID(chapter_id), bearer)
        revisions = await book.list_revisions(work.book_id, UUID(chapter_id), bearer, limit=1)
    except BookClientError as exc:
        return _book_error_result(exc)
    items = revisions.get("items") or []
    draft["base_revision_id"] = items[0].get("revision_id") if items else None
    return draft


@mcp_server.tool(
    name="composition_list_canon_rules",
    description=(
        "List the author-declared canon rules (invariants the critic enforces) for a "
        "Work — e.g. 'magic always costs HP'. Owner/grant-filtered (VIEW)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["canon rules", "invariants", "lore rules", "constraints", "list canon"],
        tool_name="composition_list_canon_rules",
    ),
)
async def composition_list_canon_rules(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    active_only: Annotated[bool, "Only enforceable (active, non-archived) rules."] = False,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _work_or_deny(works, tc, UUID(project_id))
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    canon = CanonRulesRepo(get_pool())
    pid = UUID(project_id)
    rules = await (canon.list_active(tc.user_id, pid) if active_only
                   else canon.list_all(tc.user_id, pid))
    return {"rules": [r.model_dump(mode="json") for r in rules]}


@mcp_server.tool(
    name="composition_get_generation_job",
    description=(
        "Poll an async composition GENERATION job — the cowrite-engine job that a "
        "confirmed composition_generate returns when the background worker is enabled "
        "(it returns a `pending` job rather than inline prose). Returns the job's "
        "status, its generated `result` once complete, and cost. Use to wait for a "
        "generate to finish. Owner/grant-filtered (VIEW)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["generation job", "poll generation", "generate status", "job status",
                  "cowrite job", "writing job", "is the chapter done"],
        tool_name="composition_get_generation_job",
    ),
)
async def composition_get_generation_job(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    job_id: Annotated[str, "The generation job id returned by composition_generate."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    jobs = GenerationJobsRepo(get_pool())
    job = await jobs.get(tc.user_id, UUID(job_id))
    # The repo already filters on user_id; also confirm the job belongs to THIS
    # project so a job_id from another of the caller's Works can't be read through
    # this one. A miss is the uniform "not accessible" (never an existence oracle).
    if job is None or job.project_id != pid:
        raise uniform_not_accessible()
    return job.model_dump(mode="json")


# ── Tier A — auto-write + Undo ────────────────────────────────────────────────


@mcp_server.tool(
    name="composition_create_work",
    description=(
        "Create (or get, idempotently) the composition Work for a book — the "
        "authoring context you compose in. Returns the Work. EDIT on the book "
        "required (auto-applied)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["create work", "start composing", "new writing project", "begin authoring"],
        tool_name="composition_create_work",
    ),
)
async def composition_create_work(
    ctx: MCPContext,
    project_id: Annotated[str, "The knowledge project id to bind the Work to (its PK)."],
    book_id: Annotated[str, "The book the Work composes."],
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    # Idempotent get-or-create (mirrors the HTTP POST /work tail; the MCP path
    # takes an already-resolved project_id rather than driving knowledge create).
    existing = await works.get(tc.user_id, pid)
    if existing is not None:
        out = existing.model_dump(mode="json")
        out["_meta"] = {"undo_hint": None}  # idempotent get → nothing to undo
        return out
    try:
        work = await works.create(tc.user_id, pid, bid)
    except asyncpg.UniqueViolationError as exc:
        # A concurrent same-project create won the PK race → re-get (atomic
        # get-or-create), mirroring the HTTP POST /work tail.
        racey = await works.get(tc.user_id, pid)
        if racey is None:
            raise uniform_not_accessible(exc) from exc
        out = racey.model_dump(mode="json")
        out["_meta"] = {"undo_hint": None}
        return out
    out = work.model_dump(mode="json")
    # No reverse op exists for a Work create today (no delete-work tool); honest about it.
    out["_meta"] = {"undo_hint": None}
    return out


class _NodeCreateArgs(ForbidExtra):
    project_id: str
    kind: str
    parent_id: str | None = None
    title: str = ""
    goal: str = ""
    synopsis: str = ""
    status: str = "empty"
    chapter_id: str | None = None


@mcp_server.tool(
    name="composition_outline_node_create",
    description=(
        "Add a node to the outline tree (an arc / chapter / scene / beat) under an "
        "optional parent. Returns the created node. EDIT required (auto-applied; "
        "Undo deletes the node)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["add scene", "add chapter", "create outline node", "new beat", "add arc"],
        tool_name="composition_outline_node_create",
    ),
)
async def composition_outline_node_create(ctx: MCPContext, args: _NodeCreateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    try:
        node = await outline.create_node(
            tc.user_id, pid, kind=args.kind, parent_id=UUID(args.parent_id) if args.parent_id else None,
            title=args.title, goal=args.goal, synopsis=args.synopsis, status=args.status,
            chapter_id=UUID(args.chapter_id) if args.chapter_id else None,
        )
    except ReferenceViolationError as exc:
        raise uniform_not_accessible(exc) from exc
    out = node.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo(
        "composition_outline_node_delete", project_id=args.project_id, node_id=str(node.id),
    )}
    return out


class _NodeUpdateArgs(ForbidExtra):
    project_id: str
    node_id: str
    expected_version: int
    title: str | None = None
    goal: str | None = None
    synopsis: str | None = None
    status: str | None = None


@mcp_server.tool(
    name="composition_outline_node_update",
    description=(
        "Edit an outline node's fields (title/goal/synopsis/status). Requires "
        "`expected_version` (optimistic concurrency — a stale version is rejected, "
        "no blind clobber). EDIT required (auto-applied; Undo restores the prior "
        "values via a follow-up update)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit scene", "update node", "rename chapter", "set status", "edit beat"],
        tool_name="composition_outline_node_update",
    ),
)
async def composition_outline_node_update(ctx: MCPContext, args: _NodeUpdateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    node_id = UUID(args.node_id)
    # Capture prior values for a precise Undo hint (only the fields we changed).
    prior = await outline.get_node(tc.user_id, node_id)
    # Project-scope the target: the Work gate above checked work.book_id, but the
    # node repo filters on (user_id, id) only — so a same-user caller could pass a
    # project_id from Work-A with a node_id from their own Work-B, gating the WRONG
    # book. Assert the node belongs to the resolved Work's project before mutating.
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    patch = {
        k: v for k, v in {
            "title": args.title, "goal": args.goal,
            "synopsis": args.synopsis, "status": args.status,
        }.items() if v is not None
    }
    try:
        if patch.get("status") == "done":
            node = await outline.update_node_commit_aware(
                tc.user_id, node_id, patch, expected_version=args.expected_version,
            )
        else:
            node = await outline.update_node(
                tc.user_id, node_id, patch, expected_version=args.expected_version,
            )
    except VersionMismatchError as exc:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "stale expected_version — refetch and retry",
            "current_version": exc.current.version,
        }
    except ReferenceViolationError as exc:
        raise uniform_not_accessible(exc) from exc
    if node is None:
        raise uniform_not_accessible()
    out = node.model_dump(mode="json")
    undo_fields = {f: getattr(prior, f) for f in patch}
    out["_meta"] = {"undo_hint": _undo(
        "composition_outline_node_update",
        project_id=args.project_id, node_id=args.node_id,
        expected_version=node.version, **undo_fields,
    )}
    return out


@mcp_server.tool(
    name="composition_outline_node_delete",
    description=(
        "Soft-archive an outline node and its descendants (reversible). Returns the "
        "archived node. EDIT required (auto-applied; Undo restores it)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["delete scene", "remove node", "archive chapter", "delete beat"],
        tool_name="composition_outline_node_delete",
    ),
)
async def composition_outline_node_delete(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    node_id: Annotated[str, "The node to archive."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    # Project-scope BEFORE mutating: archive_node filters on (user_id, id) only, so
    # confirm the node is in the resolved Work's project (else a same-user node from
    # another Work would be archived under THIS book's gate). See node_update note.
    target = await outline.get_node(tc.user_id, UUID(node_id))
    if target is None or target.project_id != pid:
        raise uniform_not_accessible()
    node = await outline.archive_node(tc.user_id, UUID(node_id))
    if node is None:
        raise uniform_not_accessible()
    out = node.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo(
        "composition_outline_node_restore", project_id=project_id, node_id=node_id,
    )}
    return out


@mcp_server.tool(
    name="composition_outline_node_restore",
    description=(
        "Un-archive a previously deleted outline node (the inverse of delete). EDIT "
        "required (auto-applied; Undo re-deletes it)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["restore scene", "undelete node", "unarchive chapter"],
        tool_name="composition_outline_node_restore",
    ),
)
async def composition_outline_node_restore(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    node_id: Annotated[str, "The node to restore."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    # Project-scope BEFORE mutating: restore_node filters on (user_id, id) only.
    # get_node returns archived rows too, so it confirms the (archived) target is in
    # the resolved Work's project before the un-archive. See node_update note.
    target = await outline.get_node(tc.user_id, UUID(node_id))
    if target is None or target.project_id != pid:
        raise uniform_not_accessible()
    node = await outline.restore_node(tc.user_id, UUID(node_id))
    if node is None:
        raise uniform_not_accessible()
    out = node.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo(
        "composition_outline_node_delete", project_id=project_id, node_id=node_id,
    )}
    return out


class _SceneLinkCreateArgs(ForbidExtra):
    project_id: str
    from_node_id: str
    to_node_id: str
    kind: str = "setup_payoff"
    label: str = ""


@mcp_server.tool(
    name="composition_scene_link_create",
    description=(
        "Create a scene-link edge between two scenes (e.g. a setup→payoff). Returns "
        "the edge. EDIT required (auto-applied; Undo deletes the edge)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["link scenes", "setup payoff", "connect scenes", "add scene link"],
        tool_name="composition_scene_link_create",
    ),
)
async def composition_scene_link_create(ctx: MCPContext, args: _SceneLinkCreateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    scene_links = SceneLinksRepo(get_pool())
    try:
        link = await scene_links.create(
            tc.user_id, pid, UUID(args.from_node_id), UUID(args.to_node_id),
            kind=args.kind, label=args.label,
        )
    except ReferenceViolationError as exc:
        raise uniform_not_accessible(exc) from exc
    out = link.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo(
        "composition_scene_link_delete", project_id=args.project_id, link_id=str(link.id),
    )}
    return out


@mcp_server.tool(
    name="composition_scene_link_delete",
    description=(
        "Delete a scene-link edge (hard delete — edges have no children). EDIT "
        "required (auto-applied)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["unlink scenes", "remove scene link", "delete edge"],
        tool_name="composition_scene_link_delete",
    ),
)
async def composition_scene_link_delete(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    link_id: Annotated[str, "The scene-link edge id."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    scene_links = SceneLinksRepo(get_pool())
    # Project-scope the delete: constrain the repo WHERE clause by the resolved
    # Work's project so a same-user edge from another Work (gated on a different
    # book) cannot be deleted under THIS book's gate. See node_update note.
    deleted = await scene_links.delete(tc.user_id, UUID(link_id), project_id=pid)
    if not deleted:
        raise uniform_not_accessible()
    # A hard delete has no verified reverse op (the row is gone) → undo unavailable.
    return {"deleted": True, "link_id": link_id, "_meta": {"undo_hint": None}}


class _CanonRuleCreateArgs(ForbidExtra):
    project_id: str
    text: str
    scope: str = "world"
    entity_id: str | None = None
    from_order: int | None = None
    until_order: int | None = None
    kind: str | None = None


@mcp_server.tool(
    name="composition_canon_rule_create",
    description=(
        "Add a canon rule (an invariant the critic enforces) to a Work. Returns the "
        "rule. EDIT required (auto-applied; Undo deletes the rule)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["add canon rule", "new invariant", "add constraint", "declare lore rule"],
        tool_name="composition_canon_rule_create",
    ),
)
async def composition_canon_rule_create(ctx: MCPContext, args: _CanonRuleCreateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    if args.from_order is not None and args.until_order is not None and args.from_order > args.until_order:
        return {"success": False, "error": "from_order must not exceed until_order"}
    canon = CanonRulesRepo(get_pool())
    rule = await canon.create(
        tc.user_id, pid, args.text, scope=args.scope,
        entity_id=UUID(args.entity_id) if args.entity_id else None,
        from_order=args.from_order, until_order=args.until_order, kind=args.kind,
    )
    out = rule.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo(
        "composition_canon_rule_delete", project_id=args.project_id, rule_id=str(rule.id),
    )}
    return out


class _CanonRuleUpdateArgs(ForbidExtra):
    project_id: str
    rule_id: str
    expected_version: int
    text: str | None = None
    active: bool | None = None


@mcp_server.tool(
    name="composition_canon_rule_update",
    description=(
        "Edit a canon rule's text or enabled state. Requires `expected_version` "
        "(optimistic concurrency). EDIT required (auto-applied; Undo restores the "
        "prior values)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit canon rule", "update invariant", "toggle canon rule", "disable rule"],
        tool_name="composition_canon_rule_update",
    ),
)
async def composition_canon_rule_update(ctx: MCPContext, args: _CanonRuleUpdateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    canon = CanonRulesRepo(get_pool())
    rule_id = UUID(args.rule_id)
    prior = await canon.get(tc.user_id, rule_id)
    # Project-scope the target: canon.get filters on (user_id, id) only, so confirm
    # the rule is in the resolved Work's project before mutating (else a same-user
    # rule from another Work would be edited under THIS book's gate). See node_update.
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    patch = {k: v for k, v in {"text": args.text, "active": args.active}.items() if v is not None}
    try:
        rule = await canon.update(tc.user_id, rule_id, patch, expected_version=args.expected_version)
    except VersionMismatchError as exc:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "stale expected_version — refetch and retry",
            "current_version": exc.current.version,
        }
    if rule is None:
        raise uniform_not_accessible()
    out = rule.model_dump(mode="json")
    undo_fields = {f: getattr(prior, f) for f in patch}
    out["_meta"] = {"undo_hint": _undo(
        "composition_canon_rule_update",
        project_id=args.project_id, rule_id=args.rule_id,
        expected_version=rule.version, **undo_fields,
    )}
    return out


@mcp_server.tool(
    name="composition_canon_rule_delete",
    description=(
        "Soft-archive a canon rule (reversible — the rule's critic-calibration "
        "history survives). EDIT required (auto-applied)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["delete canon rule", "remove invariant", "archive rule"],
        tool_name="composition_canon_rule_delete",
    ),
)
async def composition_canon_rule_delete(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    rule_id: Annotated[str, "The canon rule id."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    canon = CanonRulesRepo(get_pool())
    # Project-scope BEFORE mutating: canon.archive filters on (user_id, id) only, so
    # confirm the rule is in the resolved Work's project first (else a same-user rule
    # from another Work would be archived under THIS book's gate). See node_update.
    prior = await canon.get(tc.user_id, UUID(rule_id))
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    rule = await canon.archive(tc.user_id, UUID(rule_id))
    if rule is None:
        raise uniform_not_accessible()
    out = rule.model_dump(mode="json")
    # archive() only flips a NOT-archived row; there is no un-archive repo method,
    # so there is no verified reverse op to surface. Honest: undo unavailable.
    out["_meta"] = {"undo_hint": None}
    return out


class _WriteProseArgs(ForbidExtra):
    project_id: str
    chapter_id: str
    # A TipTap/ProseMirror doc is ALWAYS a JSON object. Required.
    body: dict[str, Any]
    # MANDATORY (server already mandates it — prose.py): omitting it would be a
    # blind clobber. The tool surfaces it as a required arg → reversible.
    expected_draft_version: int
    commit_message: str | None = None


@mcp_server.tool(
    name="composition_write_prose",
    description=(
        "Write the DRAFT prose of a chapter (NOT publish — that is composition_publish). "
        "You MUST pass `expected_draft_version` from composition_get_prose; a stale "
        "version is rejected (no blind clobber → reversible). EDIT required "
        "(auto-applied; Undo restores the prior draft)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["write prose", "save draft", "edit chapter text", "update prose"],
        tool_name="composition_write_prose",
    ),
)
async def composition_write_prose(ctx: MCPContext, args: _WriteProseArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    book: BookClient = get_book_client()
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    chap = UUID(args.chapter_id)
    # Capture the prior draft for a precise Undo (restore the body at its new version).
    try:
        prior = await book.get_draft(work.book_id, chap, bearer)
    except BookClientError as exc:
        return _book_error_result(exc)
    try:
        updated = await book.patch_draft(
            work.book_id, chap, bearer,
            body=args.body, expected_draft_version=args.expected_draft_version,
            commit_message=args.commit_message,
        )
    except BookClientError as exc:
        return _book_error_result(exc)
    out = dict(updated)
    new_version = out.get("draft_version")
    undo_hint = None
    prior_body = prior.get("body")
    if new_version is not None and isinstance(prior_body, dict):
        undo_hint = _undo(
            "composition_write_prose",
            project_id=args.project_id, chapter_id=args.chapter_id,
            body=prior_body, expected_draft_version=new_version,
        )
    out["_meta"] = {"undo_hint": undo_hint}
    return out


def _book_error_result(exc: BookClientError) -> dict:
    """Surface a book-service client error as a structured tool failure (not a
    raised 5xx). A 404/409 is a clean tool refusal; the H13 message is used for
    not-found so a missing/foreign chapter is indistinguishable."""
    if exc.status == 409:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "stale draft version — refetch with composition_get_prose and retry",
        }
    if exc.status == 404:
        return {"success": False, "error": "not found or not accessible"}
    return {"success": False, "error": "book-service unavailable", "status": exc.status}


# ── Tier W — publish (canonization) via confirm-token ─────────────────────────


@mcp_server.tool(
    name="composition_publish",
    description=(
        "PROPOSE publishing (canonizing) a chapter — turning its reviewed draft into "
        "the canon revision (Canon Model CM1). This is a destructive, human-confirmed "
        "action: it returns a `confirm_token` + descriptor; nothing is published until "
        "the user confirms via confirm_action. The chapter must be publishable (all "
        "its composition scenes done, no unresolved canon contradiction). EDIT required."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["publish chapter", "canonize", "make canon", "finalize chapter", "publish"],
        tool_name="composition_publish",
    ),
)
async def composition_publish(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    chapter_id: Annotated[str, "The chapter to publish (canonize)."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    # Publishing is an authoring (write) action → EDIT.
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    # Surface the publish-gate up front so the LLM/user sees WHY if it isn't
    # publishable (the confirm route re-checks it at execute time).
    outline = OutlineRepo(get_pool())
    chap = UUID(chapter_id)
    gate = await outline.chapter_scene_gate(tc.user_id, pid, chap)
    if not gate.get("can_publish"):
        return {
            "success": False,
            "error": "chapter is not publishable yet",
            "gate": gate,
        }
    # Mint a confirm token binding (user, resource=chapter, descriptor, payload).
    # The payload captures the exact target so confirm executes what was proposed.
    payload = {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "book_id": str(work.book_id),
    }
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, chap, _PUBLISH_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _PUBLISH_DESCRIPTOR,
        "title": "Publish chapter (canonize the reviewed draft)",
        "domain": "composition",
    }


class _GenerateArgs(ForbidExtra):
    project_id: str
    # XOR target: a SCENE (outline_node_id, mode=auto) OR a whole CHAPTER
    # (chapter_id, single-pass → persisted to the book draft). Exactly one.
    outline_node_id: str | None = None
    chapter_id: str | None = None
    # Literals mirror the engine's GenerateBody so a bad value is a clean refusal at
    # propose (not a pydantic 500 when the confirm effect rebuilds the engine body).
    model_source: Literal["user_model", "platform_model"]
    model_ref: str
    # The free-form prose op; defaults per target (draft_scene / draft_chapter).
    operation: str | None = None
    guide: str = ""
    max_output_tokens: int | None = None
    # Author reasoning preference, forwarded to the engine's capability-aware
    # resolver (auto = let the model/scorer decide).
    reasoning: Literal["off", "auto", "low", "medium", "high"] = "auto"


@mcp_server.tool(
    name="composition_generate",
    description=(
        "PROPOSE running the grounded cowrite ENGINE to generate prose — a SCENE "
        "(pass outline_node_id) or a whole CHAPTER (pass chapter_id; persisted to the "
        "book draft). This is DISTINCT from composition_write_prose, which only SAVES "
        "text you wrote yourself: this invokes the canon-grounded drafter+critic engine "
        "and SPENDS LLM tokens, so it is cost-gated — it returns a `confirm_token` + "
        "descriptor and generates NOTHING until the user confirms via confirm_action. "
        "Pass EXACTLY ONE of outline_node_id / chapter_id. EDIT on the book required. "
        "For a chapter, first build its outline (a chapter node + at least one scene "
        "node) with the composition_outline_node_create tool."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["generate prose", "write scene", "write chapter", "draft scene",
                  "draft chapter", "cowrite", "co-write", "ai write", "generate draft"],
        tool_name="composition_generate",
    ),
)
async def composition_generate(ctx: MCPContext, args: _GenerateArgs) -> dict:
    tc = _ctx(ctx)
    # XOR — exactly one target. A bad shape is a clean tool refusal (not a 5xx).
    has_scene = bool(args.outline_node_id)
    has_chapter = bool(args.chapter_id)
    if has_scene == has_chapter:
        return {
            "success": False,
            "error": "pass EXACTLY ONE of outline_node_id (a scene) or chapter_id (a whole chapter)",
        }
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    # Generation is a write/spend → EDIT (mirrors the engine's E0-4c pack tier).
    await _gate(tc, work.book_id, GrantLevel.EDIT)

    target_kind = "scene" if has_scene else "chapter"
    target_id = args.outline_node_id if has_scene else args.chapter_id
    # Light propose-time validation for the SCENE target: the node must exist + be in
    # the resolved Work's project (the same project-scope guard the other by-id
    # handlers apply). The CHAPTER target is validated at confirm by the engine
    # (it needs book-service to resolve the chapter sort/plan).
    if has_scene:
        outline = OutlineRepo(get_pool())
        node = await outline.get_node(tc.user_id, UUID(target_id))
        if node is None or node.project_id != pid:
            raise uniform_not_accessible()

    payload = {
        "project_id": args.project_id,
        "book_id": str(work.book_id),
        "target_kind": target_kind,
        "target_id": target_id,
        "model_source": args.model_source,
        "model_ref": args.model_ref,
        "operation": args.operation,
        "guide": args.guide,
        "max_output_tokens": args.max_output_tokens,
        "reasoning": args.reasoning,
    }
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, UUID(target_id), _GENERATE_DESCRIPTOR, payload,
    )
    summary = (f"generate a {target_kind} with the cowrite engine "
               f"(model {args.model_source}/{args.model_ref})")
    return {
        "confirm_token": confirm_token,
        "descriptor": _GENERATE_DESCRIPTOR,
        "title": summary,
        "domain": "composition",
        "requires": "human confirmation via the review surface — this spends LLM "
                    "tokens; nothing is generated until confirmed",
    }


# ══════════════════════════════════════════════════════════════════════════════
# W4 — NARRATIVE MOTIF LIBRARY MCP TOOLS (spec §R2.8 / §13 · domain owns its tools;
# ai-gateway federates the `composition_` prefix). 4 R · 4 A · 4 W-confirm · 1 R
# poll. Identity from the envelope ONLY; ForbidExtra on every arg model; the closed
# Literal enums make a system/both-NULL/public-at-create row UNCONSTRUCTIBLE by the
# LLM. Motif is a USER-tier resource (no book_id) → user-scope reads use the repo
# read predicate (system | public | owner); book-scoped ops (suggest/bind/mine/
# conformance) keep the existing book-owner gate.
# ══════════════════════════════════════════════════════════════════════════════


# ── Tier R — motif reads ──────────────────────────────────────────────────────


class _MotifSearchArgs(ForbidExtra):
    genre: str | None = None
    kind: _MotifKind | None = None
    q: str | None = None
    scope: Literal["mine", "public", "system", "all"] = "all"
    status: Literal["draft", "active", "archived"] | None = None
    language: str | None = None
    limit: int = 20


@mcp_server.tool(
    name="composition_motif_search",
    description=(
        "Search the narrative motif library — reusable plot patterns, tropes, "
        "situations, hooks, emotion arcs, schemes (e.g. 套路 / 爽点 / 打脸). Filter by "
        "genre, kind, free text (q), language, or status. `scope` narrows the tier: "
        "'mine' (your motifs), 'public' (shared), 'system' (the seeded library), 'all'. "
        "Returns a list projection (no private internals). Use composition_motif_get for "
        "a single motif's full detail."
    ),
    meta=require_meta(
        "R", "user",
        synonyms=["motif", "trope", "pattern", "plot beat", "cliché", "套路", "爽点",
                  "打脸", "find motif", "browse motifs", "narrative device"],
        tool_name="composition_motif_search",
    ),
)
async def composition_motif_search(ctx: MCPContext, args: _MotifSearchArgs) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    # No book gate — motif is user/system-tier. The repo SELECT carries the R1.1
    # read predicate (system | public | owner); `scope` is a filter, never a
    # privilege escalation (a 'system'/'public'/'all' scope can NOT surface a foreign
    # private row). Map the MCP scope vocab to the repo's predicate vocab.
    repo_scope = "user" if args.scope == "mine" else args.scope
    motifs = await repo.list_for_caller(
        tc.user_id, scope=repo_scope, genre=args.genre, kind=args.kind,
        status=args.status, q=args.q, language=args.language, limit=args.limit,
    )
    # MD-1: uniform allow-list projection in search (owner reads full via _get) — no
    # per-row branch, no embedding/examples leak in a list view.
    return {
        "motifs": [_motif_public_projection(m) for m in motifs],
        "count": len(motifs),
    }


@mcp_server.tool(
    name="composition_motif_get",
    description=(
        "Get one motif's full detail — its roles, beats, preconditions, effects, and "
        "(for your own motifs) all authoring fields. A system/public motif you don't own "
        "returns the shareable projection (no private internals). A motif you cannot see "
        "is indistinguishable from one that doesn't exist."
    ),
    meta=require_meta(
        "R", "user",
        synonyms=["motif detail", "trope detail", "get motif", "show pattern",
                  "motif roles", "motif beats"],
        tool_name="composition_motif_get",
    ),
)
async def composition_motif_get(
    ctx: MCPContext,
    motif_id: Annotated[str, "The motif's id."],
) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    # get_visible IS the IDOR guard for a non-book resource: it enforces R1.1
    # (system | public | owner), so a foreign PRIVATE id is indistinguishable from a
    # missing one (H13) — no enumeration oracle.
    motif = await repo.get_visible(tc.user_id, UUID(motif_id))
    if motif is None:
        raise uniform_not_accessible()
    return _motif_view(motif, tc.user_id)


@mcp_server.tool(
    name="composition_motif_suggest_for_chapter",
    description=(
        "Suggest motifs that fit a specific chapter — ranked candidates with a 'why "
        "this motif' breakdown (tension/genre/precondition/semantic match), so you can "
        "pick a plot pattern grounded in the Work. VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["suggest motif", "which motif", "motif for this chapter", "why this motif",
                  "recommend trope", "fit a pattern", "plot beat for scene"],
        tool_name="composition_motif_suggest_for_chapter",
    ),
)
async def composition_motif_suggest_for_chapter(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    node_id: Annotated[str, "The chapter outline node to rank motifs against."],
    limit: Annotated[int, "Max candidates."] = 5,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    outline = OutlineRepo(get_pool())
    node = await outline.get_node(tc.user_id, UUID(node_id))
    # Per-tool IDOR: the node must be in the resolved Work's project (a same-user
    # node from another Work would otherwise be ranked under THIS book's gate).
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    retriever = MotifRetriever(get_pool())
    candidates = await retriever.retrieve(
        tc.user_id, book_id=work.book_id, project_id=pid,
        genre_tags=list(getattr(work, "genre_tags", []) or []),
        language=getattr(work, "language", None) or "en",
        beat_role=None, tension=getattr(node, "tension_target", None), limit=limit,
    )
    return {
        "candidates": [
            {
                "motif": _motif_view(c.motif, tc.user_id),
                "score": c.score,
                "match_reason": c.match_reason,
            }
            for c in candidates
        ]
    }


@mcp_server.tool(
    name="composition_arc_suggest",
    description=(
        "Suggest multi-chapter ARC templates that fit a Work's premise/genre — the "
        "large-scale structures (parallel threads × motifs over a chapter span). Returns "
        "ranked candidates with a match breakdown. VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["suggest arc", "arc template", "story arc", "multi-chapter structure",
                  "arc for premise", "arc structure"],
        tool_name="composition_arc_suggest",
    ),
)
async def composition_arc_suggest(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    premise: Annotated[str | None, "Optional premise text to seed the rank."] = None,
    genre: Annotated[str | None, "Optional genre filter."] = None,
    limit: Annotated[int, "Max candidates."] = 5,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    retriever = MotifRetriever(get_pool())
    # Arc retrieval ranks the caller-visible arc_template set under the read
    # predicate (no target id beyond the Work gate). The arc retriever method is
    # owned by W3 (F0 froze only the motif `retrieve`); until W3 lands, the tool is
    # registered (wire-tested) and returns a clean "not yet available" rather than a
    # 500. Seam note: W3 supplies `retrieve_arcs(caller, *, book_id, project_id,
    # premise, genre, limit) -> list[ArcCandidate{arc_template, score, match_reason}]`.
    retrieve_arcs = getattr(retriever, "retrieve_arcs", None)
    if retrieve_arcs is None:
        return {"success": False, "error": "arc retrieval not yet available",
                "reason": "pending_w3", "candidates": []}
    candidates = await retrieve_arcs(
        tc.user_id, book_id=work.book_id, project_id=pid,
        premise=premise, genre=genre, limit=limit,
    )
    return {
        "candidates": [
            {
                "arc_template": (
                    c.arc_template.model_dump(mode="json")
                    if getattr(c.arc_template, "owner_user_id", None) == tc.user_id
                    else _arc_public_projection(c.arc_template)
                ),
                "score": c.score,
                "match_reason": c.match_reason,
            }
            for c in candidates
        ]
    }


def _arc_public_projection(arc: Any) -> dict[str, Any]:
    """Allow-list projection for a non-owned arc_template (parallels the motif one):
    drops embedding/raw source_ref/owner. Mirrors the motif B-3 discipline."""
    full = arc.model_dump(mode="json")
    drop = {"embedding", "embedding_model", "embedding_dim", "source_ref",
            "owner_user_id", "source_version"}
    return {k: v for k, v in full.items() if k not in drop}


# ── Tier A — motif auto-write + Undo ──────────────────────────────────────────


class _MotifCreateArgs(ForbidExtra):
    # target='user' ONLY (R2.8): the Book tier is gone (R1.1) and a system/both-NULL
    # row is migrate/seed-only — the closed Literal makes them UNCONSTRUCTIBLE here.
    target: Literal["user"] = "user"
    code: str
    name: str
    language: str = "en"
    kind: _MotifKind = "sequence"
    summary: str = ""
    genre_tags: list[str] = []
    roles: list[dict[str, Any]] = []
    beats: list[dict[str, Any]] = []
    preconditions: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    tension_target: int | None = None
    emotion_target: str | None = None
    examples: list[dict[str, Any]] = []
    # 'public' is EXCLUDED at create — publishing is the separate W1 visibility-flip
    # path, not a create-time arg (a public-at-birth row would skip the publish gate).
    visibility: Literal["private", "unlisted"] = "private"


@mcp_server.tool(
    name="composition_motif_create",
    description=(
        "Create a motif in YOUR library — a reusable plot pattern (sequence/situation/"
        "hook/emotion_arc/trope/pattern/scheme) with roles, beats, preconditions, and "
        "effects. The motif is owned by you and private by default. To publish it later, "
        "use the library's publish flow."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["create motif", "new trope", "author a motif", "define pattern",
                  "add motif to my library", "make a beat"],
        tool_name="composition_motif_create",
    ),
)
async def composition_motif_create(ctx: MCPContext, args: _MotifCreateArgs) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    # Owner-stamp: MotifRepo.create stamps owner_user_id = tc.user_id unconditionally
    # (there is NO owner arg) and the DB motif_user_owned CHECK rejects a both-NULL
    # write — the envelope user is the owner, no arg can override it (audit B-2/S2).
    from app.db.models import MotifCreateArgs as _RepoCreateArgs
    try:
        create_args = _RepoCreateArgs(
            code=args.code, name=args.name, language=args.language, kind=args.kind,
            summary=args.summary, genre_tags=args.genre_tags, roles=args.roles,
            beats=args.beats, preconditions=args.preconditions, effects=args.effects,
            tension_target=args.tension_target, emotion_target=args.emotion_target,
            examples=args.examples, visibility=args.visibility,
        )
    except (ValueError, TypeError) as exc:  # pydantic ValidationError ⊂ ValueError
        return {"success": False, "error": "invalid motif fields", "detail": str(exc)[:300]}
    try:
        motif = await repo.create(tc.user_id, create_args)
    except asyncpg.UniqueViolationError:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "a motif with this code + language already exists in your library",
        }
    out = motif.model_dump(mode="json")
    # MD-2: create carries an honest undo via the reverse-op _archive tool (soft,
    # reversible). The activity strip can call it to undo the create.
    out["_meta"] = {"undo_hint": _undo("composition_motif_archive", motif_id=str(motif.id))}
    return out


@mcp_server.tool(
    name="composition_motif_archive",
    description=(
        "Soft-archive one of YOUR motifs (reversible — un-archive from the library). "
        "A system or public-not-owned motif is read-only to you and cannot be archived "
        "here. Used as the verified reverse op for create."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["archive motif", "delete motif", "retire trope", "remove from library"],
        tool_name="composition_motif_archive",
    ),
)
async def composition_motif_archive(
    ctx: MCPContext,
    motif_id: Annotated[str, "The motif to archive (must be yours)."],
) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    mid = UUID(motif_id)
    # USER scope: you may only archive YOUR OWN motif. The owner-resolver raises the
    # uniform deny for a missing/foreign/system row before any write.
    guard = require_user_scope(_motif_owner_resolver(repo))
    await guard(tc, mid)
    await repo.archive(tc.user_id, mid)
    # archive() flips status='archived'; there is no MCP un-archive tool today (the
    # W1 patch is the FE un-archive surface), so the MCP undo is honest None — matches
    # composition_canon_rule_delete.
    return {"motif_id": motif_id, "archived": True, "_meta": {"undo_hint": None}}


class _MotifBindArgs(ForbidExtra):
    project_id: str
    node_id: str
    motif_id: str
    role_bindings: dict[str, str] = {}
    derive_scenes: bool = True


@mcp_server.tool(
    name="composition_motif_bind",
    description=(
        "Bind a motif to a chapter — instantiate its beats as scene nodes and map its "
        "roles to glossary entities (role_bindings: {role_key: entity_id}). Re-binding "
        "over a prior motif ARCHIVES (never deletes) the affected scenes, so the change "
        "is reversible. EDIT on the book required (auto-applied; Undo restores the prior "
        "binding or unbinds)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["bind motif", "apply motif", "use this trope", "attach pattern to chapter",
                  "swap motif", "set chapter motif"],
        tool_name="composition_motif_bind",
    ),
)
async def composition_motif_bind(ctx: MCPContext, args: _MotifBindArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    node_id = UUID(args.node_id)
    # IDOR #1: the chapter node is in the resolved Work's project.
    node = await outline.get_node(tc.user_id, node_id)
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    # IDOR #2: the motif is caller-visible (you can only bind a motif you can see).
    repo = MotifRepo(get_pool())
    motif = await repo.get_visible(tc.user_id, UUID(args.motif_id))
    if motif is None:
        raise uniform_not_accessible()
    # The bind/swap/undo ENGINE is owned by W2 (engine/motif_select.py) — W4 imports
    # it, never re-implements (the one-engine-two-entries seam, RECONCILE §2). It
    # writes the motif_application row (book_id pinned, motif_version pinned per
    # edge-F3) and, on a swap, ARCHIVES (not deletes) the prior scenes so the undo is
    # a verified reverse op (R2.6 / MCP-R2). Until W2 lands, this import fails — the
    # tool is registered (find_tools/wire-tested) and returns a clean "not yet
    # available" rather than a 500.
    try:
        from app.engine.motif_select import bind_motif  # type: ignore
    except ImportError:
        return {
            "success": False,
            "error": "motif binding engine not yet available",
            "reason": "pending_w2",
        }
    result = await bind_motif(
        tc.user_id, project_id=pid, book_id=work.book_id, node_id=node_id,
        motif=motif, role_bindings=args.role_bindings, derive_scenes=args.derive_scenes,
    )
    application = result.get("application")
    prior = result.get("prior")  # the prior binding the engine archived, if any
    derived_scene_ids = result.get("derived_scene_ids", [])
    # Honest verified undo (MCP-R2): a re-bind restores the PRIOR motif + its archived
    # scenes; a FIRST bind has no prior, so the reverse op is _unbind.
    if prior:
        undo = _undo(
            "composition_motif_bind",
            project_id=args.project_id, node_id=args.node_id,
            motif_id=str(prior.get("motif_id")),
            role_bindings=prior.get("role_bindings", {}),
        )
    else:
        undo = _undo(
            "composition_motif_unbind",
            project_id=args.project_id, node_id=args.node_id,
            application_id=str(application.get("id")) if application else None,
        )
    return {
        "application": application,
        "derived_scene_ids": [str(s) for s in derived_scene_ids],
        "_meta": {"undo_hint": undo},
    }


@mcp_server.tool(
    name="composition_motif_unbind",
    description=(
        "Unbind a motif from a chapter — archive the binding and its derived scenes "
        "(reversible). The verified reverse op for a first bind. EDIT on the book "
        "required (auto-applied)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["unbind motif", "remove motif", "clear chapter motif", "detach pattern"],
        tool_name="composition_motif_unbind",
    ),
)
async def composition_motif_unbind(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    node_id: Annotated[str, "The chapter node the motif is bound to."],
    application_id: Annotated[str, "The motif_application id to unbind."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    try:
        from app.engine.motif_select import unbind_motif  # type: ignore
    except ImportError:
        return {
            "success": False,
            "error": "motif binding engine not yet available",
            "reason": "pending_w2",
        }
    # The engine's unbind asserts the application's project_id == pid AND book_id ==
    # work.book_id (the per-tool IDOR for the application target) before archiving.
    ok = await unbind_motif(
        tc.user_id, project_id=pid, book_id=work.book_id,
        node_id=UUID(node_id), application_id=UUID(application_id),
    )
    if not ok:
        raise uniform_not_accessible()
    return {"unbound": True, "application_id": application_id, "_meta": {"undo_hint": None}}


# ── Tier W — motif confirm-token ops (cost/tenancy-gated) ─────────────────────


class _MotifAdoptArgs(ForbidExtra):
    motif_id: str
    target: Literal["user"] = "user"
    retag_genres: list[str] | None = None


@mcp_server.tool(
    name="composition_motif_adopt",
    description=(
        "PROPOSE adopting a public/system motif into YOUR library (a clone you can then "
        "customize), optionally retagging it to different genres. This crosses the "
        "tenancy boundary and counts against your library quota, so it is human-"
        "confirmed: it returns a confirm_token + a preview; nothing is cloned until you "
        "confirm via confirm_action."
    ),
    meta=require_meta(
        "W", "user",
        synonyms=["adopt motif", "clone motif", "copy trope to my library",
                  "import public motif", "reuse a pattern", "clone and retag"],
        tool_name="composition_motif_adopt",
    ),
)
async def composition_motif_adopt(ctx: MCPContext, args: _MotifAdoptArgs) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    mid = UUID(args.motif_id)
    # READPRED: you may adopt only a motif you can see (public/system/own). A foreign
    # private id is the uniform deny (H13) — no oracle.
    motif = await repo.get_visible(tc.user_id, mid)
    if motif is None:
        raise uniform_not_accessible()
    payload = {
        "motif_id": args.motif_id,
        "retag_genres": args.retag_genres,
    }
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, mid, _MOTIF_ADOPT_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _MOTIF_ADOPT_DESCRIPTOR,
        "title": "Adopt motif into your library",
        "domain": "composition",
        "preview": {
            "source_name": motif.name,
            "will_clone": True,
            "retag_to": args.retag_genres or list(motif.genre_tags),
        },
    }


class _MotifMineArgs(ForbidExtra):
    scope: Literal["book", "corpus"]
    book_id: str | None = None
    min_support: int = 2
    promote_to: Literal["draft"] = "draft"
    language: str = "en"


@mcp_server.tool(
    name="composition_motif_mine",
    description=(
        "PROPOSE mining motifs from a book or your whole corpus — abstract the recurring "
        "plot patterns into draft motifs for your library. This spends LLM tokens, so it "
        "is cost-gated: it returns a confirm_token + a $ estimate; nothing runs until you "
        "confirm via confirm_action, then it runs as a background job you poll with "
        "composition_get_mine_job."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["mine motifs", "extract patterns", "discover tropes",
                  "find motifs in my books", "analyze my corpus", "套路 mining"],
        tool_name="composition_motif_mine",
    ),
)
async def composition_motif_mine(ctx: MCPContext, args: _MotifMineArgs) -> dict:
    tc = _ctx(ctx)
    if args.scope == "book":
        if not args.book_id:
            return {"success": False, "error": "book_id is required when scope='book'"}
        # BOOK(EDIT) gate on the named book (mining writes draft motifs informed by it).
        await _gate(tc, UUID(args.book_id), GrantLevel.EDIT)
    # MD-4: corpus mining has no single resource id → gated by envelope identity only;
    # the worker filters every read on user_id=caller + re-checks each book's grant.
    estimate = _mine_estimate(scope=args.scope)
    payload = {
        "scope": args.scope,
        "book_id": args.book_id,
        "min_support": args.min_support,
        "promote_to": args.promote_to,
        "language": args.language,
        "estimate_usd": estimate["estimated_usd"],
    }
    # resource_id binds the token: the named book for scope='book', else the user.
    resource_id = UUID(args.book_id) if args.scope == "book" and args.book_id else tc.user_id
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, resource_id, _MOTIF_MINE_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _MOTIF_MINE_DESCRIPTOR,
        "title": f"Mine motifs from {args.scope}",
        "domain": "composition",
        "requires": "human confirmation — this spends LLM tokens",
        "estimate": estimate,
    }


class _ArcImportArgs(ForbidExtra):
    import_source_id: str
    use_web: bool = False
    arc_hint: str | None = None


@mcp_server.tool(
    name="composition_arc_import_analyze",
    description=(
        "PROPOSE deconstructing an imported reference work (拆文) into an abstract arc "
        "template — reverse-engineer its structure WITHOUT copying its prose. The raw "
        "import stays private; only the derived abstract template is shareable. Spends "
        "LLM tokens → returns a confirm_token + a $ estimate; runs as a background job."
    ),
    meta=require_meta(
        "W", "user",
        synonyms=["import arc", "deconstruct", "analyze a work", "拆文",
                  "reverse-engineer arc", "extract arc template", "analyze reference"],
        tool_name="composition_arc_import_analyze",
    ),
)
async def composition_arc_import_analyze(ctx: MCPContext, args: _ArcImportArgs) -> dict:
    tc = _ctx(ctx)
    isid = UUID(args.import_source_id)
    # USER scope on the import_source row (§12.6/B-3 — structurally un-shareable):
    # owner == caller, else uniform deny.
    guard = require_user_scope(_import_source_owner)
    await guard(tc, isid)
    estimate = _mine_estimate(scope="corpus")
    payload = {
        "import_source_id": args.import_source_id,
        "use_web": args.use_web,
        "arc_hint": args.arc_hint,
        "estimate_usd": estimate["estimated_usd"],
    }
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, isid, _ARC_IMPORT_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _ARC_IMPORT_DESCRIPTOR,
        "title": "Analyze a reference work into an arc template",
        "domain": "composition",
        "requires": "human confirmation — this spends LLM tokens",
        "estimate": estimate,
    }


class _ConformanceRunArgs(ForbidExtra):
    project_id: str
    scope: Literal["chapter", "arc"]
    chapter_id: str | None = None


@mcp_server.tool(
    name="composition_conformance_run",
    description=(
        "PROPOSE a conformance check — did the generated prose actually realize the "
        "bound motifs/arc (beats hit, reversals landed)? Arc-scope re-extracts and "
        "spends LLM tokens, so it is cost-gated: returns a confirm_token; runs as a "
        "background job you poll with composition_get_mine_job. EDIT on the book required."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["check conformance", "did the AI follow the arc", "verify against plan",
                  "arc conformance", "beat realized", "drift check"],
        tool_name="composition_conformance_run",
    ),
)
async def composition_conformance_run(ctx: MCPContext, args: _ConformanceRunArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.EDIT)
    if args.scope == "chapter":
        if not args.chapter_id:
            return {"success": False, "error": "chapter_id is required when scope='chapter'"}
        outline = OutlineRepo(get_pool())
        node = await outline.get_node(tc.user_id, UUID(args.chapter_id))
        # IDOR: the chapter is in the resolved Work's project.
        if node is None or node.project_id != pid:
            raise uniform_not_accessible()
    estimate = _mine_estimate(scope="book")
    payload = {
        "project_id": args.project_id,
        "book_id": str(work.book_id),
        "scope": args.scope,
        "chapter_id": args.chapter_id,
        "estimate_usd": estimate["estimated_usd"],
    }
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, pid, _CONFORMANCE_RUN_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _CONFORMANCE_RUN_DESCRIPTOR,
        "title": f"Run {args.scope} conformance check",
        "domain": "composition",
        "requires": "human confirmation — this spends LLM tokens",
        "estimate": estimate,
    }


# ── R poll — the one tool for all three W-async motif jobs ─────────────────────


@mcp_server.tool(
    name="composition_get_mine_job",
    description=(
        "Poll an async motif job — the mining / arc-import / conformance job a confirmed "
        "Tier-W motif action returns. Returns the job's status, its result once complete, "
        "and cost. Use to wait for a mine/import/conformance to finish. VIEW on the book "
        "required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["mining job", "import job", "conformance job", "poll mining",
                  "is mining done", "motif job status"],
        tool_name="composition_get_mine_job",
    ),
)
async def composition_get_mine_job(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    job_id: Annotated[str, "The motif job id returned by a confirmed Tier-W motif action."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    work = await _work_or_deny(works, tc, pid)
    await _gate(tc, work.book_id, GrantLevel.VIEW)
    jobs = GenerationJobsRepo(get_pool())
    job = await jobs.get(tc.user_id, UUID(job_id))
    # Cross-Work IDOR (exact clone of composition_get_generation_job): the repo
    # filters user_id; also confirm the job is in THIS project (a job_id from another
    # of the caller's Works can't be read through this one). A miss is uniform.
    if job is None or job.project_id != pid:
        raise uniform_not_accessible()
    return job.model_dump(mode="json")


# ── ASGI factory ──────────────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``.

    ``FastMCP.streamable_http_app()`` returns a Starlette app whose own lifespan
    runs the StreamableHTTP session manager. Under FastAPI a *mounted* sub-app's
    lifespan is NOT auto-run, so ``main.py`` runs the session manager directly
    inside its own lifespan (``mcp_server.session_manager.run()``)."""
    return mcp_server.streamable_http_app()
