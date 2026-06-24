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


# ── ASGI factory ──────────────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``.

    ``FastMCP.streamable_http_app()`` returns a Starlette app whose own lifespan
    runs the StreamableHTTP session manager. Under FastAPI a *mounted* sub-app's
    lifespan is NOT auto-run, so ``main.py`` runs the session manager directly
    inside its own lifespan (``mcp_server.session_manager.run()``)."""
    return mcp_server.streamable_http_app()
