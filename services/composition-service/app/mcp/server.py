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
  `project_id` (= the knowledge project id, the Work PARTITION key) and access is
  decided BEFORE the repo, at the gate: every project-keyed tool resolves the
  ids-only scope (`WorksRepo.scope_meta` — un-user-scoped, PM-8's anti-oracle
  shape) and gates the caller's E0 grant on the row's `book_id` through the SAME
  chokepoint the HTTP routers use (`_gate_book`): VIEW for reads, EDIT for
  writes. The repos are un-user-scoped (BPS-1/2/8, spec 25 §Repo/service layer):
  reads key on `project_id`/`book_id` only; writes stamp `created_by` as a plain
  actor — STORED, never filtered on. A non-grantee / under-tier caller gets the
  H13 uniform "not found or not accessible" (no enumeration oracle).
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
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

import asyncpg
from mcp.server.fastmcp import Context as MCPContext
from pydantic import Field

from loreweave_mcp import (
    ForbidExtra,
    GrantResolver,
    ToolContext,
    TolerantArgs,
    apply_response_contract,
    build_tool_context,
    make_stateless_fastmcp,
    mint_confirm_token,
    require_book_owner,
    require_meta,
    require_user_scope,
    uniform_not_accessible,
)

from app.clients.book_client import BookClient, BookClientError, get_book_client
from app.clients.knowledge_client import (
    KnowledgeClient,
    KnowledgeContractError,
    get_knowledge_client,
)
from app.config import settings
from app.db.models import LinkKind, PlanPassId, SceneExitState
from app.services.agent_native import ReferenceSource, resolve_scope
from app.services.plan_pass_service import UpstreamStale
from app.db.pool import get_pool
from app.db.repositories import (
    ReferenceViolationError,
    VersionMismatchError,
)
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.db.repositories.entity_references import EntityReferencesRepo
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.structure import StructureConflictError, StructureRepo
from app.db.repositories.works import WorksRepo
from app.deps import get_authoring_run_service
from app.grant_client import GrantLevel, get_grant_client
from app.mcp.service_bearer import mint_service_bearer
from app.services.authoring_run_service import ALLOWLISTABLE_TOOLS
from app.work_resolution import resolve_work

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

# ── D-AGENT-MODE §20 — authoring-run confirm descriptors (D5/D6). Book-scoped
# (payload carries book_id, not project_id); the confirm route
# (app/routers/actions.py) dispatches these BEFORE its Work-resolution branch,
# mirroring the motif_adopt per-book gate.
_AUTHORING_RUN_CREATE_DESCRIPTOR = "composition.authoring_run_create"
_AUTHORING_RUN_GATE_DESCRIPTOR = "composition.authoring_run_gate"
_AUTHORING_RUN_START_DESCRIPTOR = "composition.authoring_run_start"
_AUTHORING_RUN_RESUME_DESCRIPTOR = "composition.authoring_run_resume"
_AUTHORING_RUN_REVERT_ALL_DESCRIPTOR = "composition.authoring_run_revert_all"

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


async def _book_or_deny(works: WorksRepo, tc: ToolContext, project_id: UUID, level: GrantLevel):
    """PM-8 (BPS-8): resolve the Work's ids-only scope (book_id/work_id/
    project_id — `scope_meta`, an un-user-scoped anti-oracle read) and gate the
    caller's E0 grant on the row's `book_id` at the operation's tier. The
    ordering inversion is the whole fix over the old `_work_or_deny`: the grant
    is first-class; row ownership is never consulted for ACCESS. A missing
    project raises the SAME H13 uniform error as a denied grant — no
    enumeration oracle. Returns the ids-only meta (use `meta.book_id`; fetch
    the full Work separately when a tool needs more than ids)."""
    meta = await works.scope_meta(project_id)
    if meta is None:
        raise uniform_not_accessible()
    await _gate(tc, meta.book_id, level)
    return meta


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


# L1/L2 reference-first projection for motif SET tools (Context Budget Law §6b). At
# `detail=summary` a motif collapses to these ref fields — the heavy structural lists
# (roles/beats/preconditions/effects and examples) are dropped; fetch one motif's full
# body via composition_motif_get. Keep the ≤1-line `summary`, the concurrency token
# (`version`), and the fields the model needs to recognise/pick a pattern (code/kind/
# name/genre/language/visibility/status).
_MOTIF_REF_FIELDS = (
    "id", "code", "name", "kind", "summary", "genre_tags",
    "language", "visibility", "status", "version",
)
# The book-library variant additionally keeps the shared-tier badge fields (present on
# owner full-dumps and stamped onto non-owner shared rows by _motif_book_view) so the
# summary still tells the model which rows are the book's SHARED tier.
_MOTIF_BOOK_REF_FIELDS = _MOTIF_REF_FIELDS + ("book_id", "book_shared")
# Arc-template ref set (parallels the motif one): drop the heavy structure
# (threads/layout/pacing/arc_roster) + embedding; keep id/name/≤1-line/version + the
# navigational fields. Fetch the full arc structure via the owner's full dump / a get.
_ARC_REF_FIELDS = (
    "id", "code", "name", "summary", "genre_tags", "language",
    "chapter_span", "visibility", "status", "version",
)


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
        "[Authoring workspace] Get the composition Work for a book/project (its status, active template, "
        "and authoring settings). The Work is the book's shared authoring context "
        "(the package manifest). Pass project_id when you know it; otherwise pass "
        "book_id — the book's Work is resolved, which is ALSO how you discover the "
        "project_id every other composition_* tool requires (a book_id is NOT a "
        "project_id). Grant-gated — VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=[
            "composition work", "authoring context", "get work",
            "resolve project id", "the book's authoring workspace",
        ],
        tool_name="composition_get_work",
    ),
)
async def composition_get_work(
    ctx: MCPContext,
    project_id: Annotated[str | None, "The Work's project_id (= the knowledge project id, the Work PK)."] = None,
    book_id: Annotated[str | None, "Alternative lookup: resolve the book's Work by book_id (use when you only know the book)."] = None,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    if project_id:
        pid = UUID(project_id)
        await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
        work = await works.get(pid)
        if work is None:
            raise uniform_not_accessible()
    elif book_id:
        # book→Work resolution (M-E live-caught): the agent naturally knows the book_id
        # (studio context) but every composition tool keys on project_id, and no tool
        # bridged the two — the model retried book_id AS project_id and dead-ended.
        # Gate FIRST (PM-8 — book_id given directly, no lookup needed), then resolve
        # the book's marked Works; 0 → the H13 uniform deny.
        bid = UUID(book_id)
        await _gate(tc, bid, GrantLevel.VIEW)
        marked = await works.resolve_by_book(bid)
        if not marked:
            raise uniform_not_accessible()
        if len(marked) > 1:
            # The book's marked Works (the grant already passed) — return them so
            # the model can pick (e.g. canonical vs a derivative).
            return {"candidates": [w.model_dump(mode="json") for w in marked]}
        work = marked[0]
    else:
        raise ValueError("pass project_id or book_id")
    return work.model_dump(mode="json")


# L1/L2 reference-first projection for outline nodes (Context Budget Law §6b). At
# `detail=summary` a node collapses to these ref fields — the heavy `goal`/`synopsis`
# prose (the 146K-case bloat) is dropped; fetch one node's full body via
# composition_get_outline_node. Keep the structural fields the model needs to
# navigate the tree (kind/parent/order/status/version).
# NOTE (T1 review LOW-2): `child_count` is NOT selected by list_tree (only
# list_children computes it), so it's intentionally omitted here — listing a dead
# ref field would falsely imply the summary carries a leaf/parent indicator.
_OUTLINE_REF_FIELDS = (
    "id", "kind", "parent_id", "title", "status", "version",
    "story_order", "chapter_id",
)


@mcp_server.tool(
    name="composition_list_outline",
    description=(
        "List the outline/scene-graph of a Work — the Arc→Chapter→Scene→Beat tree "
        "plus its scene-links (setup/payoff edges). Use to see the planned structure "
        "before generating or editing. Pass `detail=summary` (default `full`) for a "
        "lightweight ref list ({id,kind,title,status,version,...} — no goal/synopsis "
        "prose) and `limit` to bound large outlines; fetch one node's full body via "
        "composition_get_outline_node. Owner/grant-filtered (VIEW)."
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
    detail: Annotated[
        Literal["summary", "full"],
        "summary = refs only (id/kind/title/status/version, no prose); full = every field.",
    ] = "full",
    limit: Annotated[
        int | None,
        "Coarse cap on nodes returned (a flat prefix of the tree — may drop later "
        "arcs' scenes; `truncated` reports how many). To read ONE node use "
        "composition_get_outline_node, not pagination.",
    ] = None,
    include_archived: Annotated[bool, "Include soft-archived nodes."] = False,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    outline = OutlineRepo(get_pool())
    scene_links = SceneLinksRepo(get_pool())
    nodes = await outline.list_tree(pid, include_archived=include_archived)
    links = await scene_links.list_by_project(pid)
    node_dicts = [n.model_dump(mode="json") for n in nodes]
    projected, meta = apply_response_contract(
        node_dicts, ref_fields=_OUTLINE_REF_FIELDS, detail=detail, limit=limit,
    )
    return {
        "nodes": projected,
        "scene_links": [l.model_dump(mode="json") for l in links],
        **meta,
    }


@mcp_server.tool(
    name="composition_get_outline_node",
    description=(
        "Read ONE outline node by id — its fields plus `version`, the concurrency "
        "token you pass back to composition_outline_node_update. Use this instead of "
        "listing the whole outline when you only need one node's current state or "
        "version (e.g. before a status/title edit). Owner/grant-filtered (VIEW)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["get node", "node version", "read scene", "read chapter node",
                  "outline node", "get scene", "node status"],
        tool_name="composition_get_outline_node",
    ),
)
async def composition_get_outline_node(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    node_id: Annotated[str, "The outline node's id."],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    outline = OutlineRepo(get_pool())
    node = await outline.get_node(UUID(node_id))
    # get_node fetches by id only — project-scope the target so a node_id from
    # another Work (a different book/gate) can't be read through this project
    # (same H13 discipline as composition_get_generation_job / node_update).
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    return node.model_dump(mode="json")


# T1/L2 (Context Budget Law §6b/D2) — the heavy field a get_prose SUMMARY drops. A full
# chapter body (Tiptap JSON) is routinely many thousands of tokens; an agent that only
# needs the `draft_version` concurrency token (e.g. to prep a write, or to check whether a
# chapter has content) should not have to pull the whole chapter.
_PROSE_BODY_KEY = "body"


def _project_prose(draft: dict, detail: str) -> dict:
    """At detail=summary, drop the heavy `body` but KEEP the metadata + the `draft_version`
    concurrency token. Never a silent drop — signal `body_omitted` + the `detail` so the
    model knows the body exists and re-fetches with detail=full to get it."""
    if detail != "summary":
        return draft
    summary = {k: v for k, v in draft.items() if k != _PROSE_BODY_KEY}
    summary["body_omitted"] = True
    summary["detail"] = "summary"
    return summary


@mcp_server.tool(
    name="composition_get_prose",
    description=(
        "[Authoring workspace] Get the current DRAFT prose of a chapter (the editable body + its "
        "`draft_version` — the concurrency token you MUST pass back to write_prose). "
        "`detail=summary` returns just the metadata + `draft_version` (drops the chapter "
        "`body` — use it when you only need the version to prep a write); `detail=full` "
        "(default) returns the whole body. Owner/grant-filtered (VIEW)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["prose", "chapter text", "draft", "get prose", "read chapter"],
        # Deprecated: a thin proxy over book_get_chapter (same loreweave_book.chapter_drafts
        # row). Kept callable for the authoring toolset; hidden from agent discovery so the
        # catalog has ONE chapter-read tool, not two identical ones.
        visibility="legacy", superseded_by="book_get_chapter",
        tool_name="composition_get_prose",
    ),
)
async def composition_get_prose(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id."],
    chapter_id: Annotated[str, "The chapter's id."],
    detail: Annotated[
        Literal["summary", "full"],
        "summary = metadata + draft_version only (drops the chapter body); full = the body too.",
    ] = "full",
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    meta = await _book_or_deny(works, tc, UUID(project_id), GrantLevel.VIEW)
    book: BookClient = get_book_client()
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    try:
        draft = await book.get_draft(meta.book_id, UUID(chapter_id), bearer)
        revisions = await book.list_revisions(meta.book_id, UUID(chapter_id), bearer, limit=1)
    except BookClientError as exc:
        return _book_error_result(exc)
    items = revisions.get("items") or []
    draft["base_revision_id"] = items[0].get("revision_id") if items else None
    return _project_prose(draft, detail)


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
    pid = UUID(project_id)
    await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    canon = CanonRulesRepo(get_pool())
    rules = await (canon.list_active(pid) if active_only
                   else canon.list_all(pid))
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
    await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    jobs = GenerationJobsRepo(get_pool())
    job = await jobs.get(UUID(job_id))
    # The repo fetches by id only — confirm the job belongs to THIS project so a
    # job_id from another Work (a different book/gate) can't be read through this
    # one. A miss is the uniform "not accessible" (never an existence oracle).
    if job is None or job.project_id != pid:
        raise uniform_not_accessible()
    return job.model_dump(mode="json")


# ── Tier A — auto-write + Undo ────────────────────────────────────────────────


async def _resolve_or_create_default_project(
    tc: ToolContext, book_id: UUID, works: WorksRepo,
) -> UUID | None:
    """OQ2 (2026-07-07 discovery-hardening spec): resolve, or create idempotently,
    the DEFAULT per-book knowledge project when composition_create_work's caller
    omits `project_id`. Before this fix, `find_tools`/`invoke_tool` gave a caller
    no discoverable way to obtain a project_id for a book that doesn't already
    have one (`kg_project_list` returns empty for a fresh book) — the external
    audit's #7 finding. This mirrors the HTTP POST /work tail
    (`app/routers/works.py::create_work_for_book`) via the SAME §6.2 resolver
    (`app/work_resolution.resolve_work`) and the SAME knowledge-service client
    every other composition↔knowledge interaction already uses
    (`app/clients/knowledge_client.py`), reached via a minted service bearer —
    the established MCP→JWT-only-route seam (`app/mcp/service_bearer.py`, the
    same pattern `composition_get_prose`/`composition_write_prose` already use
    to reach book-service).

    Returns the resolved/created project_id, or None on a knowledge-service
    OUTAGE (down/timeout/5xx) so the caller can degrade to a lazy pending Work —
    exactly like the HTTP path (C16/WG-3). `KnowledgeContractError` (a 4xx — our
    bug, not an outage) and `BookClientError` propagate to the caller so a real
    defect surfaces instead of silently degrading."""
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    knowledge: KnowledgeClient = get_knowledge_client()
    res = await resolve_work(
        book_id, bearer=bearer, works_repo=works, knowledge_client=knowledge,
    )
    if res.status == "unavailable":
        return None
    if res.status == "found":
        return res.work.project_id  # type: ignore[union-attr]
    if res.status == "candidates":
        return res.works[0].project_id
    if res.status == "unmarked_single":
        return res.book_project_id
    if res.status == "unmarked_candidates":
        return res.book_project_ids[0]
    # status == "none" — no book-typed knowledge project exists yet; create one.
    book: BookClient = get_book_client()
    book_obj = await book.get_book(book_id, bearer)
    name = (book_obj or {}).get("title") or f"Book {book_id}"
    created = await knowledge.create_project(book_id, name, bearer)
    if created is None or not created.get("project_id"):
        return None  # knowledge OUTAGE during create → degrade like the HTTP path
    new_project_id = UUID(str(created["project_id"]))

    # HIGH-1 fix (mirrors app/routers/works.py::create_work_for_book lines
    # ~227-234): a PRIOR knowledge-service outage may have left a lazy pending
    # Work (project_id=NULL, pending_project_backfill=true) for this book —
    # created by the degrade branches above / `_ensure_pending_work` (one per
    # book, PM-4; whoever created it, PM-9's caller-independent resolution
    # backfills THE row). Now that knowledge has recovered and minted a fresh
    # project, backfill THAT row instead of letting the caller mint a brand-new
    # composition_work row (which would orphan the pending row forever +
    # duplicate the knowledge project's Work binding). backfill_project no-ops
    # (returns None) if the row already got backfilled concurrently or has
    # since vanished — either way new_project_id is still the right id to bind
    # to; the caller's own `existing = await works.get(...)` idempotent-get
    # (below, in composition_create_work) will find the (now backfilled) row
    # instead of creating a second one.
    pending = await works.get_pending_for_book(book_id)
    if pending is not None and pending.id is not None:
        await works.backfill_project(pending.id, new_project_id, created_by=tc.user_id)
    return new_project_id


async def _ensure_pending_work(works: WorksRepo, created_by: UUID, book_id: UUID):
    """C16 (WG-3) greenfield degrade for the MCP path — mirrors
    `app/routers/works.py::_ensure_pending_work`: return the (at-most-one) lazy
    null-project Work for this book, creating it if absent (`created_by` is a
    plain actor stamp, never a scope key). Idempotent + race-safe (the
    partial-unique `(book_id) WHERE pending_project_backfill` index — PM-4 —
    caps it at one, so a concurrent loser re-gets the existing row)."""
    existing = await works.get_pending_for_book(book_id)
    if existing is not None:
        return existing
    try:
        return await works.create_pending(created_by, book_id)
    except asyncpg.UniqueViolationError:
        racey = await works.get_pending_for_book(book_id)
        if racey is None:
            raise ValueError("work create conflict — retry") from None
        return racey


@mcp_server.tool(
    name="composition_create_work",
    description=(
        "[Authoring workspace] Create (or get, idempotently) the composition Work for a book — the "
        "authoring context you compose in. `project_id` is OPTIONAL: pass it if "
        "you already know the book's knowledge project id (e.g. from "
        "composition_get_work); omit it and a default per-book knowledge project "
        "is resolved or created for you automatically — no separate kg_* setup "
        "step needed. Returns the Work. EDIT on the book required (auto-applied)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=[
            "create work", "start composing", "new writing project", "begin authoring",
            "bootstrap project",
        ],
        tool_name="composition_create_work",
    ),
)
async def composition_create_work(
    ctx: MCPContext,
    book_id: Annotated[str, "The book the Work composes."],
    project_id: Annotated[
        str | None,
        "The knowledge project id to bind the Work to (its PK). Optional — omit "
        "it to auto-resolve or auto-create (idempotently) the book's default "
        "knowledge project.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    works = WorksRepo(get_pool())

    if project_id:
        pid = UUID(project_id)
    else:
        try:
            pid = await _resolve_or_create_default_project(tc, bid, works)
        except KnowledgeContractError as exc:
            if exc.status_code == 404:
                # MED-1: knowledge-service's project-create route 404s for a
                # non-owner EDIT-grantee (auto-provisioning a fresh knowledge
                # project is OWNER-only) — the caller can't fix this by retrying
                # the same call, so say so concretely + point at the fix.
                return {
                    "success": False,
                    "error": (
                        "only the book owner can auto-provision the knowledge "
                        "project — pass project_id explicitly, or ask the book "
                        "owner to run composition_create_work once (see "
                        "composition_get_work to check if one already exists)"
                    ),
                }
            return {
                "success": False,
                "error": f"knowledge-service rejected the auto-create (status {exc.status_code})",
            }
        except BookClientError as exc:
            return _book_error_result(exc)
        if pid is None:
            # Knowledge-service OUTAGE — degrade to a lazy null-project Work
            # (mirrors the HTTP POST /work WG-3 path) so authoring keeps working;
            # a later call (once knowledge recovers, or with a real project_id)
            # resolves the pending marker.
            pending = await _ensure_pending_work(works, tc.user_id, bid)
            out = pending.model_dump(mode="json")
            out["_meta"] = {"undo_hint": None}
            return out

    # Idempotent get-or-create (mirrors the HTTP POST /work tail). The create
    # keys `created_by` as a plain actor stamp (PM-9) — access stayed with the
    # EDIT gate above, never with the row's creator.
    existing = await works.get(pid)
    if existing is not None:
        out = existing.model_dump(mode="json")
        out["_meta"] = {"undo_hint": None}  # idempotent get → nothing to undo
        return out
    try:
        work = await works.create(tc.user_id, pid, bid)
    except asyncpg.UniqueViolationError as exc:
        # A concurrent same-project create won the PK race → re-get (atomic
        # get-or-create), mirroring the HTTP POST /work tail.
        racey = await works.get(pid)
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
    # BPS-4 (F6): outline_node is now CHAPTER/SCENE only — arcs live on
    # structure_node (composition_arc_create), beats are verified-dead. A closed
    # Literal turns a mid-tier model's `kind:"Arc"` into a clean 422 at the schema
    # instead of a DB CheckViolation 5xx (mcp-tool-io IN-2, the panel_id bug class).
    kind: Literal["chapter", "scene"]
    parent_id: str | None = None
    title: str = ""
    goal: str = ""
    synopsis: str = ""
    status: Literal["empty", "outline", "drafting", "done"] = "empty"
    chapter_id: str | None = None
    # 22 SC4/SC8 (B3) — the authored scene INTENT (the eight fields), validated AT
    # THE SCHEMA so a bad range/enum is a clean 422 here, never a DB CHECK 5xx
    # (mcp-tool-io IN-2). value_shift is the scene's net charge (-100..100, distinct
    # from `tension`); target_words must be >0; exit_state is the SC12 {v:1,…}
    # envelope (SceneExitState, extra='forbid' — an unversioned key 422s too).
    location_entity_id: str | None = None
    story_time: str | None = None
    conflict: str = ""
    outcome: str = ""
    value_shift: int | None = Field(default=None, ge=-100, le=100)
    stakes: str = ""
    target_words: int | None = Field(default=None, gt=0)
    exit_state: SceneExitState | None = None


@mcp_server.tool(
    name="composition_outline_node_create",
    description=(
        "Add a CHAPTER or SCENE node to the outline tree under an optional parent "
        "(arcs are the durable spec layer — use composition_arc_create; beats are "
        "gone). Returns the created node. EDIT required (auto-applied; Undo deletes "
        "the node)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["add scene", "add chapter", "create outline node", "add outline chapter"],
        tool_name="composition_outline_node_create",
    ),
)
async def composition_outline_node_create(ctx: MCPContext, args: _NodeCreateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    try:
        node = await outline.create_node(
            pid, kind=args.kind, parent_id=UUID(args.parent_id) if args.parent_id else None,
            title=args.title, goal=args.goal, synopsis=args.synopsis, status=args.status,
            chapter_id=UUID(args.chapter_id) if args.chapter_id else None,
            # 22 SC4/SC8 — the authored intent (schema-validated above).
            location_entity_id=UUID(args.location_entity_id) if args.location_entity_id else None,
            story_time=args.story_time, conflict=args.conflict, outcome=args.outcome,
            value_shift=args.value_shift, stakes=args.stakes, target_words=args.target_words,
            exit_state=args.exit_state.model_dump(mode="json") if args.exit_state is not None else None,
            created_by=tc.user_id,
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
    # BPS-4/F6 closed set — a bad status is a clean 422, never a DB CheckViolation.
    status: Literal["empty", "outline", "drafting", "done"] | None = None
    # 22 SC4/SC8 (B3) — the same authored-intent fields, editable. None = leave
    # unchanged (the tool's sparse-patch convention — clearing a nullable field to
    # NULL is not expressible here, matching the existing status/title fields).
    # Ranges + the exit_state envelope are validated AT THE SCHEMA (see create).
    location_entity_id: str | None = None
    story_time: str | None = None
    conflict: str | None = None
    outcome: str | None = None
    value_shift: int | None = Field(default=None, ge=-100, le=100)
    stakes: str | None = None
    target_words: int | None = Field(default=None, gt=0)
    exit_state: SceneExitState | None = None


@mcp_server.tool(
    name="composition_outline_node_update",
    description=(
        "Edit an outline node's fields (title/goal/synopsis/status). Requires "
        "`expected_version` (optimistic concurrency — a stale version is rejected, "
        "no blind clobber); read the current version cheaply via "
        "composition_get_outline_node (no need to list the whole outline). EDIT "
        "required (auto-applied; Undo restores the prior values via a follow-up update)."
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    node_id = UUID(args.node_id)
    # Capture prior values for a precise Undo hint (only the fields we changed).
    prior = await outline.get_node(node_id)
    # Project-scope the target: the gate above checked the resolved Work's book,
    # but the node repo fetches by id only — so a caller could pass a project_id
    # from Work-A with a node_id from Work-B, gating the WRONG book. Assert the
    # node belongs to the gated Work's project before mutating.
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    patch = {
        k: v for k, v in {
            "title": args.title, "goal": args.goal,
            "synopsis": args.synopsis, "status": args.status,
            # 22 SC4/SC8 — authored intent (schema-validated). None = leave unchanged.
            "story_time": args.story_time, "conflict": args.conflict,
            "outcome": args.outcome, "value_shift": args.value_shift,
            "stakes": args.stakes, "target_words": args.target_words,
        }.items() if v is not None
    }
    # location_entity_id is a UUID column (str arg → UUID); exit_state is the SC12
    # envelope (model → plain dict, ::jsonb serialized by update_node's B2 path).
    if args.location_entity_id is not None:
        patch["location_entity_id"] = UUID(args.location_entity_id)
    if args.exit_state is not None:
        patch["exit_state"] = args.exit_state.model_dump(mode="json")
    try:
        if patch.get("status") == "done":
            node = await outline.update_node_commit_aware(
                node_id, patch, expected_version=args.expected_version,
            )
        else:
            node = await outline.update_node(
                node_id, patch, expected_version=args.expected_version,
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
    # The undo hint restores the changed fields to their PRIOR values via a reverse
    # composition_outline_node_update. That tool's patch is sparse — None means "leave
    # unchanged" (there is no clear verb) — so a field whose PRIOR was None (only the
    # nullable SC4 fields: value_shift, target_words, location_entity_id, story_time,
    # exit_state) cannot be faithfully reversed: emitting `field: null` would silently
    # no-op while the strip claims the undo applied. When any changed field is in that
    # state there is no faithful single-op reverse, so emit NO undo_hint rather than a
    # lying one (no-silent-no-op). The pre-SC4 fields are all NOT NULL — their prior is
    # never None — so the common edit stays fully reversible.
    undo_fields = {f: getattr(prior, f) for f in patch}
    unrestorable = any(v is None for v in undo_fields.values())
    undo_hint = None if unrestorable else _undo(
        "composition_outline_node_update",
        project_id=args.project_id, node_id=args.node_id,
        expected_version=node.version, **undo_fields,
    )
    out["_meta"] = {"undo_hint": undo_hint}
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    # Project-scope BEFORE mutating: archive_node targets by id only, so confirm
    # the node is in the gated Work's project (else a node from another Work
    # would be archived under THIS book's gate). See node_update note.
    target = await outline.get_node(UUID(node_id))
    if target is None or target.project_id != pid:
        raise uniform_not_accessible()
    node = await outline.archive_node(UUID(node_id))
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    # Project-scope BEFORE mutating: restore_node targets by id only. get_node
    # returns archived rows too, so it confirms the (archived) target is in the
    # gated Work's project before the un-archive. See node_update note.
    target = await outline.get_node(UUID(node_id))
    if target is None or target.project_id != pid:
        raise uniform_not_accessible()
    node = await outline.restore_node(UUID(node_id))
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
    # Closed set (mcp-tool-io IN-2): a Literal makes a mid-tier model's bad `kind` a clean 422 at the
    # schema, not a 500 CheckViolation at the DB — same guard the REST mirror (outline.py) already has.
    kind: LinkKind = "setup_payoff"
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    scene_links = SceneLinksRepo(get_pool())
    try:
        link = await scene_links.create(
            pid, UUID(args.from_node_id), UUID(args.to_node_id),
            kind=args.kind, label=args.label, created_by=tc.user_id,
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    scene_links = SceneLinksRepo(get_pool())
    # Project-scope the delete: constrain the repo WHERE clause by the gated
    # Work's project so an edge from another Work (gated on a different book)
    # cannot be deleted under THIS book's gate. See node_update note.
    deleted = await scene_links.delete(pid, UUID(link_id))
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    if args.from_order is not None and args.until_order is not None and args.from_order > args.until_order:
        return {"success": False, "error": "from_order must not exceed until_order"}
    canon = CanonRulesRepo(get_pool())
    rule = await canon.create(
        pid, args.text, scope=args.scope,
        entity_id=UUID(args.entity_id) if args.entity_id else None,
        from_order=args.from_order, until_order=args.until_order, kind=args.kind,
        created_by=tc.user_id,
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    canon = CanonRulesRepo(get_pool())
    rule_id = UUID(args.rule_id)
    prior = await canon.get(pid, rule_id)
    # Project-scope the target: canon.get fetches by id only, so confirm the
    # rule is in the gated Work's project before mutating (else a rule from
    # another Work would be edited under THIS book's gate). See node_update.
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    patch = {k: v for k, v in {"text": args.text, "active": args.active}.items() if v is not None}
    try:
        rule = await canon.update(pid, rule_id, patch, expected_version=args.expected_version)
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
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    canon = CanonRulesRepo(get_pool())
    # Project-scope BEFORE mutating: canon.archive targets by id only, so
    # confirm the rule is in the gated Work's project first (else a rule from
    # another Work would be archived under THIS book's gate). See node_update.
    prior = await canon.get(pid, UUID(rule_id))
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    rule = await canon.archive(pid, UUID(rule_id))
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
        "[Authoring workspace] Write the DRAFT prose of a chapter (NOT publish — that is composition_publish). "
        "You MUST pass `expected_draft_version` from composition_get_prose; a stale "
        "version is rejected (no blind clobber → reversible). EDIT required "
        "(auto-applied; Undo restores the prior draft)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["write prose", "save draft", "edit chapter text", "update prose"],
        # Deprecated: a thin proxy over book_chapter_save_draft (writes the same
        # loreweave_book.chapter_drafts.body row, gated on the same draft_version). Kept
        # callable; hidden from discovery so the catalog has ONE chapter-write tool.
        visibility="legacy", superseded_by="book_chapter_save_draft",
        tool_name="composition_write_prose",
    ),
)
async def composition_write_prose(ctx: MCPContext, args: _WriteProseArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    book: BookClient = get_book_client()
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    chap = UUID(args.chapter_id)
    # Capture the prior draft for a precise Undo (restore the body at its new version).
    try:
        prior = await book.get_draft(meta.book_id, chap, bearer)
    except BookClientError as exc:
        return _book_error_result(exc)
    try:
        updated = await book.patch_draft(
            meta.book_id, chap, bearer,
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
        # Deprecated: canonizes the same book-owned draft as book_chapter_publish (proxies
        # POST /v1/books/.../publish). Kept callable; hidden from discovery so the catalog
        # has ONE chapter-publish tool.
        visibility="legacy", superseded_by="book_chapter_publish",
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
    # Publishing is an authoring (write) action → EDIT.
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    # Surface the publish-gate up front so the LLM/user sees WHY if it isn't
    # publishable (the confirm route re-checks it at execute time).
    outline = OutlineRepo(get_pool())
    chap = UUID(chapter_id)
    gate = await outline.chapter_scene_gate(pid, chap)
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
        "book_id": str(meta.book_id),
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
        async_job=True,
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
    # Generation is a write/spend → EDIT (mirrors the engine's E0-4c pack tier).
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)

    target_kind = "scene" if has_scene else "chapter"
    target_id = args.outline_node_id if has_scene else args.chapter_id
    # Light propose-time validation for the SCENE target: the node must exist + be in
    # the gated Work's project (the same project-scope guard the other by-id
    # handlers apply). The CHAPTER target is validated at confirm by the engine
    # (it needs book-service to resolve the chapter sort/plan).
    if has_scene:
        outline = OutlineRepo(get_pool())
        node = await outline.get_node(UUID(target_id))
        if node is None or node.project_id != pid:
            raise uniform_not_accessible()

    payload = {
        "project_id": args.project_id,
        "book_id": str(meta.book_id),
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
# D-AGENT-MODE §20 — AUTHORING-RUN MCP TOOLS (spec docs/specs/2026-07-01-writing-
# studio/20_agent_mode.md, decisions D5/D6/D7). The autonomous multi-chapter
# drafting run FSM (draft→gated→running→(paused⇄running)→report_ready→closed)
# lives in AuthoringRunService/authoring_runs REST router; these 11 tools are
# the MCP surface (previously zero MCP consumers existed — REST-only). Every
# tool takes an explicit `book_id` (D7 — never inferred from ambient/header
# context, per memory `gateway-drops-xprojectid-envelope`). Spend-triggering
# tools (create/gate/start/resume) + revert_all (destructive+irreversible)
# confirm-gate via the SAME mint_confirm_token → confirm_action pattern as
# composition_generate (D6); list/get/pause/close/accept_unit/reject_unit
# execute directly.
# ══════════════════════════════════════════════════════════════════════════════


def _serialize_authoring_run(run: Any) -> dict[str, Any]:
    """MCP-facing run projection (mirrors routers/authoring_runs.py's
    `_serialize`; kept local — this module doesn't import a router's private
    helper)."""
    return {
        "run_id": str(run.run_id),
        "book_id": str(run.book_id),
        "plan_run_id": str(run.plan_run_id),
        "level": run.level,
        "scope": [str(c) for c in run.scope],
        "budget_usd": str(run.budget_usd),
        "spent_usd": str(run.spent_usd),
        "tool_allowlist": run.tool_allowlist,
        "params": run.params,
        "breaker_state": run.breaker_state,
        "status": run.status,
        "current_unit": run.current_unit,
        "error_message": run.error_message,
        "background": run.background,
        "pause_after_each_unit": run.pause_after_each_unit,
    }


async def _authoring_run_actor(
    tc: ToolContext, svc: Any, book_id: UUID, run_id: UUID, *, allow_book_owner: bool,
) -> UUID:
    """Resolve the acting identity for a run-scoped action, mirroring the
    REST router's `_transition_route` `book_owner_may_act` widening (pause/
    close only — the scope fence is per-BOOK across users, so a collaborator's
    abandoned run would otherwise lock the book owner out forever). The plain
    path (the caller created the run) does no extra book-grant check, matching
    the REST router exactly; a FOREIGN run requires the book's OWNER grant and
    acts as the run's creator (`created_by` — the F9 resolve-to-owner
    precedent, row tenancy preserved). Denial is the uniform H13 refusal
    throughout (no existence oracle)."""
    run = await svc.get(run_id)
    if run is None or run.book_id != book_id:
        raise uniform_not_accessible()
    if run.created_by == tc.user_id:
        return tc.user_id
    if not allow_book_owner:
        raise uniform_not_accessible()
    await _gate(tc, book_id, GrantLevel.OWNER)
    return run.created_by


async def _require_own_run(tc: ToolContext, svc: Any, book_id: UUID, run_id: UUID) -> Any:
    """Creator-only fence for a run mutation, returning the run.

    `svc.get` is bare-id since the 25 re-key: the book grant checked above proves only
    that the caller may edit the book they NAMED, not that `run_id` lives in it. Every
    run mutation must therefore reconcile the run against the gated book AND enforce the
    creator rule the REST router enforces (`_run_for_mutation`) — starting or reverting
    someone else's run spends their BYOK budget and can destroy their drafts.
    Book-owner escalation is pause/close only; those use `_authoring_run_actor`.
    Missing / foreign / not-yours all raise the same uniform refusal (no oracle)."""
    run = await svc.get(run_id)
    if run is None or run.book_id != book_id or run.created_by != tc.user_id:
        raise uniform_not_accessible()
    return run


# ── Tier R — reads ──────────────────────────────────────────────────────────


class _AuthoringRunListArgs(TolerantArgs):
    book_id: str
    limit: int = Field(default=20, ge=1, le=100)


@mcp_server.tool(
    name="composition_authoring_run_list",
    description=(
        "List autonomous authoring runs (Agent Mode / Mission Control) for a book — "
        "run id, scope, status, spend/budget, created-at. VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["list authoring runs", "agent mode runs", "autonomous runs",
                  "mission control", "list agent runs"],
        tool_name="composition_authoring_run_list",
    ),
)
async def composition_authoring_run_list(ctx: MCPContext, args: _AuthoringRunListArgs) -> dict:
    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    await _gate(tc, book_id, GrantLevel.VIEW)
    svc = await get_authoring_run_service()
    # OUT-5 (mcp-tool-io.md): never silently truncate — over-fetch by one to detect
    # a capped result and report it honestly instead of looking like "everything".
    # OQ-3: the read is book-scoped (every collaborator's runs), not owner-keyed.
    runs = await svc.list(book_id, limit=args.limit + 1)
    has_more = len(runs) > args.limit
    return {
        "items": [_serialize_authoring_run(r) for r in runs[: args.limit]],
        "has_more": has_more,
    }


class _AuthoringRunGetArgs(TolerantArgs):
    book_id: str
    run_id: str


@mcp_server.tool(
    name="composition_authoring_run_get",
    description=(
        "Get the full state of one autonomous authoring run, plus its per-unit "
        "(per-chapter) report — status, cost, critic verdict, pre/post revision ids. "
        "VIEW on the book required (the report requires the run to be in "
        "report_ready/failed/paused/closed; other statuses return the run with no "
        "unit report)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["get authoring run", "run report", "mission control detail",
                  "agent run status", "run detail"],
        tool_name="composition_authoring_run_get",
    ),
)
async def composition_authoring_run_get(ctx: MCPContext, args: _AuthoringRunGetArgs) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    # OQ-3: run reads widen to the book grant — gate FIRST (PM-8 ordering), then
    # the un-owner-scoped get; the run must be in THIS book (H13 on a mismatch).
    await _gate(tc, book_id, GrantLevel.VIEW)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    run = await svc.get(run_id)
    if run is None or run.book_id != book_id:
        raise uniform_not_accessible()
    result: dict[str, Any] = {"run": _serialize_authoring_run(run)}
    try:
        result["units"] = await svc.unit_report(run)
    except TransitionConflictError as exc:
        result["units"] = None
        result["units_error"] = str(exc)
    return result


# ── Tier W — create (confirm-gated, D6: budget_usd + pause_after_each_unit
# are REQUIRED args with no default — a missing value is a validation error,
# never a silent default) ────────────────────────────────────────────────────


class _AuthoringRunCreateArgs(TolerantArgs):
    book_id: str
    plan_run_id: str
    scope: list[str] = Field(default_factory=list)   # ordered chapter-id strings
    level: Literal[3, 4] = 3
    budget_usd: Decimal = Field(gt=0)
    # IN-3 (mcp-tool-io.md): closed-set enum, single source of truth =
    # authoring_run_service.ALLOWLISTABLE_TOOLS (gate() re-validates the same set).
    tool_allowlist: list[Literal[ALLOWLISTABLE_TOOLS]] = Field(default_factory=list)
    pause_after_each_unit: bool
    params: dict[str, Any] = Field(default_factory=dict)


@mcp_server.tool(
    name="composition_authoring_run_create",
    description=(
        "PROPOSE creating a new autonomous multi-chapter authoring run (draft state) "
        "over an approved PlanForge plan. Cost-gated: returns a `confirm_token` + "
        "descriptor and creates NOTHING until confirmed via confirm_action. "
        "`budget_usd` and `pause_after_each_unit` are REQUIRED — there is no silent "
        "default for either. `pause_after_each_unit=true` makes the run stop for "
        "human review after every chapter (the safe default for the Studio UI); "
        "`false` drafts the whole scope unattended (only stopping on budget "
        "exhaustion or a severe critic verdict) — pass false explicitly when asked "
        "to 'keep drafting without asking me each chapter'. EDIT on the book "
        "required. Only one run may be gated/running/paused per book at a time."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["start autonomous run", "agent mode", "autonomous authoring",
                  "draft chapters unattended", "mission control", "create authoring run"],
        tool_name="composition_authoring_run_create",
    ),
)
async def composition_authoring_run_create(
    ctx: MCPContext, args: _AuthoringRunCreateArgs,
) -> dict:
    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    await _gate(tc, book_id, GrantLevel.EDIT)
    payload = {
        "book_id": args.book_id,
        "plan_run_id": args.plan_run_id,
        "scope": args.scope,
        "level": args.level,
        "budget_usd": str(args.budget_usd),
        "tool_allowlist": args.tool_allowlist,
        "pause_after_each_unit": args.pause_after_each_unit,
        "params": args.params,
    }
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, book_id, _AUTHORING_RUN_CREATE_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _AUTHORING_RUN_CREATE_DESCRIPTOR,
        "title": (
            f"Create a level-{args.level} autonomous authoring run "
            f"(budget ${args.budget_usd}, {len(args.scope)} chapter(s), "
            f"pause_after_each_unit={args.pause_after_each_unit})"
        ),
        "domain": "composition",
        "requires": "human confirmation via the review surface — no chapters are "
                    "drafted at create time, but the run holds the book's active-run "
                    "slot until closed",
    }


class _AuthoringRunIdArgs(TolerantArgs):
    book_id: str
    run_id: str


@mcp_server.tool(
    name="composition_authoring_run_gate",
    description=(
        "PROPOSE running the start-gate check (draft → gated) on an authoring run — "
        "validates the plan is approved, the scope's chapters all belong to the book, "
        "budget_usd > 0, and the tool_allowlist is non-empty. Cost-gated only in the "
        "sense that it commits the book's one-active-run slot; returns a "
        "`confirm_token` and gates NOTHING until confirmed. A failing check is "
        "reported at confirm time. EDIT on the book required."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["gate authoring run", "start gate check", "validate authoring run",
                  "run start-gate"],
        tool_name="composition_authoring_run_gate",
    ),
)
async def composition_authoring_run_gate(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload = {"book_id": args.book_id, "run_id": args.run_id}
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, run_id, _AUTHORING_RUN_GATE_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _AUTHORING_RUN_GATE_DESCRIPTOR,
        "title": "Run the start-gate check (draft → gated)",
        "domain": "composition",
        "requires": "human confirmation — a failing gate check is reported at confirm time",
    }


class _AuthoringRunStartArgs(TolerantArgs):
    book_id: str
    run_id: str
    # D4b: an explicit override of the run's stored pause_after_each_unit policy
    # (None = leave the policy set at create time untouched).
    pause_after_each_unit: bool | None = None


@mcp_server.tool(
    name="composition_authoring_run_start",
    description=(
        "PROPOSE starting a gated authoring run (gated → running) — spawns the "
        "server-side driver, which starts drafting chapters and SPENDS LLM tokens. "
        "Cost-gated: returns a `confirm_token`; nothing drafts until confirmed. "
        "Optionally pass `pause_after_each_unit` to OVERRIDE the policy set at "
        "create time (omit to leave it as-is). Owner-only — a book OWNER grant does "
        "NOT let you start someone else's run (it spends their budget)."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["start authoring run", "begin autonomous drafting", "run gated run",
                  "kick off agent mode"],
        async_job=True,
        tool_name="composition_authoring_run_start",
    ),
)
async def composition_authoring_run_start(ctx: MCPContext, args: _AuthoringRunStartArgs) -> dict:
    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload: dict[str, Any] = {"book_id": args.book_id, "run_id": args.run_id}
    if args.pause_after_each_unit is not None:
        payload["pause_after_each_unit"] = args.pause_after_each_unit
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, run_id, _AUTHORING_RUN_START_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _AUTHORING_RUN_START_DESCRIPTOR,
        "title": "Start the authoring run (spends LLM tokens)",
        "domain": "composition",
        "requires": "human confirmation via the review surface — this spends LLM "
                    "tokens; nothing drafts until confirmed",
    }


class _AuthoringRunResumeArgs(TolerantArgs):
    book_id: str
    run_id: str
    pause_after_each_unit: bool | None = None


@mcp_server.tool(
    name="composition_authoring_run_resume",
    description=(
        "PROPOSE resuming a paused authoring run (paused → running) — the driver "
        "continues from its current unit and SPENDS MORE LLM tokens. Cost-gated: "
        "returns a `confirm_token`; nothing resumes until confirmed. Optionally pass "
        "`pause_after_each_unit` to override the policy (e.g. `false` to 'keep "
        "drafting without asking me each chapter'; omit to leave it as-is). "
        "Owner-only."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["resume authoring run", "continue autonomous drafting",
                  "unpause agent mode", "keep drafting"],
        async_job=True,
        tool_name="composition_authoring_run_resume",
    ),
)
async def composition_authoring_run_resume(ctx: MCPContext, args: _AuthoringRunResumeArgs) -> dict:
    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload: dict[str, Any] = {"book_id": args.book_id, "run_id": args.run_id}
    if args.pause_after_each_unit is not None:
        payload["pause_after_each_unit"] = args.pause_after_each_unit
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, run_id, _AUTHORING_RUN_RESUME_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _AUTHORING_RUN_RESUME_DESCRIPTOR,
        "title": "Resume the authoring run (spends more LLM tokens)",
        "domain": "composition",
        "requires": "human confirmation via the review surface — this spends more "
                    "LLM tokens; nothing resumes until confirmed",
    }


# ── Tier A — direct writes (pause/close/accept/reject: no new spend, no
# confirm needed per D6) ──────────────────────────────────────────────────────


@mcp_server.tool(
    name="composition_authoring_run_pause",
    description=(
        "Pause a running authoring run (running → paused) at the next unit "
        "boundary — no new spend, executes immediately. The book's OWNER-grant "
        "holder may pause ANY run on their book (not just their own), so a "
        "collaborator's run can always be stopped."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["pause authoring run", "stop agent mode", "halt autonomous drafting",
                  "pause my run"],
        tool_name="composition_authoring_run_pause",
    ),
)
async def composition_authoring_run_pause(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    await _authoring_run_actor(tc, svc, book_id, run_id, allow_book_owner=True)
    try:
        run = await svc.pause(run_id)
    except LookupError:
        raise uniform_not_accessible()
    except TransitionConflictError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "run": _serialize_authoring_run(run)}


@mcp_server.tool(
    name="composition_authoring_run_close",
    description=(
        "Cancel / stop / close an autonomous authoring run (Agent Mode). This is the ONLY "
        "tool that can stop a run — the generic jobs_cancel does NOT work on a run (a run is "
        "not a background job; it silently no-ops). Allowed from every non-running state; "
        "pause a RUNNING run first via composition_authoring_run_pause. No new spend, "
        "executes immediately. Closing a gated/paused run releases the book's active-run "
        "slot for a new one. The book's OWNER-grant holder may close ANY run on their book."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["close authoring run", "end agent mode", "cancel autonomous run",
                  "stop autonomous run", "kill the run", "release run slot"],
        tool_name="composition_authoring_run_close",
    ),
)
async def composition_authoring_run_close(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    await _authoring_run_actor(tc, svc, book_id, run_id, allow_book_owner=True)
    try:
        run = await svc.close(run_id)
    except LookupError:
        raise uniform_not_accessible()
    except TransitionConflictError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "run": _serialize_authoring_run(run)}


class _AuthoringRunUnitArgs(TolerantArgs):
    book_id: str
    run_id: str
    unit_index: int = Field(ge=0)


@mcp_server.tool(
    name="composition_authoring_run_accept_unit",
    description=(
        "Accept a drafted chapter unit (drafted → accepted) — keeps its prose as-is. "
        "Only legal while the run is report_ready/failed/paused (edge #12 — a "
        "partial run's completed units are still reviewable). EDIT on the book "
        "required, no new spend."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["accept chapter draft", "approve unit", "keep this chapter",
                  "accept authoring unit"],
        tool_name="composition_authoring_run_accept_unit",
    ),
)
async def composition_authoring_run_accept_unit(
    ctx: MCPContext, args: _AuthoringRunUnitArgs,
) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    # Grant-tier law (spec 25): unit review is a package WRITE → EDIT on the
    # book, gated FIRST (PM-8 ordering); the run must be in THIS book AND be the
    # caller's own — REST `_run_for_mutation` is creator-only for accept/reject
    # (book-owner escalation is pause/close only), and the two doors must agree.
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    run = await _require_own_run(tc, svc, book_id, run_id)
    try:
        unit = await svc.accept_unit(run_id, args.unit_index)
    except LookupError as exc:
        return {"success": False, "error": str(exc)}
    except TransitionConflictError as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "unit_index": unit.unit_index,
        "status": unit.status,
    }


@mcp_server.tool(
    name="composition_authoring_run_reject_unit",
    description=(
        "Reject a drafted chapter unit (drafted → rejected) — restores the chapter "
        "to its pre-run revision FIRST, then marks rejected (never rejected without "
        "the actual revert). Returns `cascade_warning.downstream_unit_indexes`: "
        "LATER drafted/accepted units threaded on this chapter's prose (v1: advisory "
        "only, not auto-rejected — review or reject those too). Only legal while the "
        "run is report_ready/failed/paused. EDIT on the book required, no new spend."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["reject chapter draft", "discard unit", "undo this chapter",
                  "reject authoring unit", "revert chapter"],
        tool_name="composition_authoring_run_reject_unit",
    ),
)
async def composition_authoring_run_reject_unit(
    ctx: MCPContext, args: _AuthoringRunUnitArgs,
) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    # Grant-tier law (spec 25): unit review is a package WRITE → EDIT on the
    # book, gated FIRST (PM-8 ordering); the run must be in THIS book AND be the
    # caller's own — rejecting a unit RESTORES the chapter's prior revision, so a
    # non-creator EDIT-grantee could destroy another author's draft. REST
    # `_run_for_mutation` is creator-only here; the two doors must agree.
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    run = await _require_own_run(tc, svc, book_id, run_id)
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)

    async def _restore(bid: UUID, chapter_id: UUID, revision_id: UUID) -> None:
        await get_book_client().restore_revision(bid, chapter_id, revision_id, bearer)

    try:
        unit, cascade, reverted = await svc.reject_unit(
            run_id, args.unit_index, restore=_restore,
        )
    except BookClientError as exc:
        return {
            "success": False,
            "error": f"book-service restore failed ({exc}); unit left drafted",
        }
    except LookupError as exc:
        return {"success": False, "error": str(exc)}
    except TransitionConflictError as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "unit_index": unit.unit_index,
        "status": unit.status,
        "reverted": reverted,
        "cascade_warning": {
            "downstream_unit_indexes": cascade,
            "note": (
                "these later drafted/accepted units were threaded on the rejected "
                "chapter's prose — review or reject them too (not auto-rejected)"
            ),
        },
    }


# ── Tier W — revert_all (confirm-gated, D6: destructive + irreversible from
# the UI even though it is not itself new spend) ──────────────────────────────


@mcp_server.tool(
    name="composition_authoring_run_revert_all",
    description=(
        "PROPOSE reverting EVERY drafted/accepted unit of a run, in reverse unit "
        "order (downstream first), restoring each chapter to its pre-run revision; "
        "full success closes the run. Destructive + irreversible from the UI, so "
        "this confirm-gates even though it spends no new LLM tokens. Confirming may "
        "return a PARTIAL result (the effect stops at the first restore failure — "
        "the response reports which units reverted and which failed; the run is "
        "left open for a retry). Only legal while the run is report_ready/failed/"
        "paused. Owner-only."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["revert all chapters", "undo entire run", "roll back authoring run",
                  "discard all drafted chapters"],
        tool_name="composition_authoring_run_revert_all",
    ),
)
async def composition_authoring_run_revert_all(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    tc = _ctx(ctx)
    book_id = UUID(args.book_id)
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = UUID(args.run_id)
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload = {"book_id": args.book_id, "run_id": args.run_id}
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, run_id, _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR,
        "title": "Revert ALL drafted/accepted chapters in this run (destructive)",
        "domain": "composition",
        "requires": "human confirmation — this is destructive and irreversible "
                    "from this surface; nothing reverts until confirmed",
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
    # L1/L2 reference-first (Context Budget Law §6b). Default "full" (versioned
    # migration — federated/legacy callers unchanged); the chat-compiler passes
    # "summary" for a lightweight ref list (no roles/beats/preconditions/effects).
    detail: Literal["summary", "full"] = "full"


@mcp_server.tool(
    name="composition_motif_search",
    description=(
        "Search the narrative motif library — reusable plot patterns, tropes, "
        "situations, hooks, emotion arcs, schemes (e.g. 套路 / 爽点 / 打脸). Filter by "
        "genre, kind, free text (q), language, or status. `scope` narrows the tier: "
        "'mine' (your motifs), 'public' (shared), 'system' (the seeded library), 'all'. "
        "Returns a list projection (no private internals). Pass `detail=summary` "
        "(default `full`) for a lightweight ref list ({id,code,name,kind,summary,...} — "
        "no roles/beats/preconditions/effects) and use composition_motif_get for a "
        "single motif's full detail."
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
    # per-row branch, no embedding/examples leak in a list view. On top of that,
    # apply the L1/L2 reference-first contract: detail=summary drops the heavy
    # structural lists. limit=None here — the repo SELECT already bounded to args.limit,
    # so `total`/`returned` reflect the fetched set (truncated=0; narrow via filters).
    projected, meta = apply_response_contract(
        [_motif_public_projection(m) for m in motifs],
        ref_fields=_MOTIF_REF_FIELDS, detail=args.detail,
    )
    return {"motifs": projected, "count": len(motifs), **meta}


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
    # @small_return: single-object read (the get_by_id sibling) — this IS the
    # full-detail fetch the summary refs point to; no detail arg / SET projection.
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    # get_visible IS the IDOR guard for a non-book resource: it enforces R1.1
    # (system | public | owner), so a foreign PRIVATE id is indistinguishable from a
    # missing one (H13) — no enumeration oracle.
    motif = await repo.get_visible(tc.user_id, UUID(motif_id))
    if motif is None:
        raise uniform_not_accessible()
    return _motif_view(motif, tc.user_id)


def _motif_book_view(motif: Any, caller_id: UUID) -> dict[str, Any]:
    """Projection for the book-context library (D-MOTIF-ADOPT-BOOK-COLLAB-TIER). The caller is a
    VIEW-grantee of the book. Own rows → full dump. A SHARED row owned by another collaborator →
    the B-3 allow-list (roles/beats/etc — enough to read + edit) PLUS book_id + book_shared (so the
    FE can badge it + route an edit through the shared path), but NEVER embedding/examples/owner."""
    if motif.owner_user_id is not None and motif.owner_user_id == caller_id:
        return motif.model_dump(mode="json")
    proj = _motif_public_projection(motif)
    proj["book_id"] = str(motif.book_id) if motif.book_id else None
    proj["book_shared"] = bool(motif.book_shared)
    return proj


@mcp_server.tool(
    name="composition_motif_book_list",
    description=(
        "List the motifs available IN a book: your own library motifs plus the book's SHARED "
        "tier — motifs collaborators adopted/authored into THIS book that everyone with access "
        "can see and (with EDIT) edit. VIEW on the book required. Shared rows are badged "
        "book_shared=true. Pass `detail=summary` (default `full`) for a lightweight ref list "
        "(no roles/beats/preconditions/effects); fetch a full motif via composition_motif_get. "
        "Use composition_motif_adopt target='book_shared' to add one."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["book motifs", "shared motifs", "this book's tropes", "collaborator motifs",
                  "book motif library", "shared library"],
        tool_name="composition_motif_book_list",
    ),
)
async def composition_motif_book_list(
    ctx: MCPContext,
    book_id: Annotated[str, "The book whose motif library to list (you need VIEW on it)."],
    genre: Annotated[str | None, "Filter by genre tag."] = None,
    kind: Annotated[_MotifKind | None, "Filter by motif kind."] = None,
    q: Annotated[str | None, "Free-text filter on name/summary."] = None,
    status: Annotated[Literal["draft", "active", "archived"] | None, "Status filter."] = "active",
    language: Annotated[str | None, "Language filter."] = None,
    limit: Annotated[int, "Max rows."] = 50,
    detail: Annotated[
        Literal["summary", "full"],
        "summary = refs only (id/code/name/kind/summary/badges, no roles/beats); full = every field.",
    ] = "full",
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    # VIEW-gate the book — the grant IS the access control for the shared tier (read).
    await _gate(tc, bid, GrantLevel.VIEW)
    repo = MotifRepo(get_pool())
    motifs = await repo.list_in_book(
        tc.user_id, bid, genre=genre, kind=kind, status=status, q=q,
        language=language, limit=limit,
    )
    # L1/L2 reference-first: keep the shared-tier badges (_MOTIF_BOOK_REF_FIELDS) at
    # summary. limit=None — the repo already bounded to `limit` (truncated=0).
    projected, meta = apply_response_contract(
        [_motif_book_view(m, tc.user_id) for m in motifs],
        ref_fields=_MOTIF_BOOK_REF_FIELDS, detail=detail,
    )
    return {"motifs": projected, "count": len(motifs), "book_id": book_id, **meta}


@mcp_server.tool(
    name="composition_motif_suggest_for_chapter",
    description=(
        "Suggest motifs that fit a specific chapter — ranked candidates with a 'why "
        "this motif' breakdown (tension/genre/precondition/semantic match), so you can "
        "pick a plot pattern grounded in the Work. Pass `detail=summary` (default `full`) "
        "to get each candidate's motif as a lightweight ref (no roles/beats) while keeping "
        "the score + match_reason; fetch a full motif via composition_motif_get. VIEW on "
        "the book required."
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
    detail: Annotated[
        Literal["summary", "full"],
        "summary = each candidate's motif is refs only (no roles/beats); full = every field. "
        "score + match_reason are kept at both levels.",
    ] = "full",
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    meta = await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    outline = OutlineRepo(get_pool())
    node = await outline.get_node(UUID(node_id))
    # Per-tool IDOR: the node must be in the gated Work's project (a node from
    # another Work would otherwise be ranked under THIS book's gate).
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    retriever = MotifRetriever(get_pool())
    # Motif is a USER-tier resource (deps/ registry — untouched by the re-key),
    # so the retriever keeps its caller-visibility predicate on tc.user_id.
    candidates = await retriever.retrieve(
        tc.user_id, book_id=meta.book_id, project_id=pid,
        genre_tags=list(getattr(meta, "genre_tags", []) or []),
        language=getattr(meta, "language", None) or "en",
        beat_role=None, tension=getattr(node, "tension_target", None), limit=limit,
    )
    # L1/L2 reference-first on the ranked candidates: project each candidate's (heavy)
    # motif body through the contract, keeping the score + match_reason wrapper. The
    # retriever already bounded to `limit`, so the contract only does the detail
    # projection (limit=None → truncated=0); `**meta` reports the detail level + count.
    motif_dicts, meta = apply_response_contract(
        [_motif_view(c.motif, tc.user_id) for c in candidates],
        ref_fields=_MOTIF_REF_FIELDS, detail=detail,
    )
    return {
        "candidates": [
            {"motif": motif_dicts[i], "score": c.score, "match_reason": c.match_reason}
            for i, c in enumerate(candidates)
        ],
        **meta,
    }


@mcp_server.tool(
    name="composition_arc_suggest",
    description=(
        "Suggest multi-chapter ARC templates that fit a Work's premise/genre — the "
        "large-scale structures (parallel threads × motifs over a chapter span). Returns "
        "ranked candidates with a match breakdown. Pass `detail=summary` (default `full`) "
        "to get each candidate's arc_template as a lightweight ref (no threads/layout/"
        "pacing) while keeping the score + match_reason. VIEW on the book required."
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
    detail: Annotated[
        Literal["summary", "full"],
        "summary = each candidate's arc_template is refs only (no threads/layout/pacing); "
        "full = every field. score + match_reason are kept at both levels.",
    ] = "full",
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    meta = await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    retriever = MotifRetriever(get_pool())
    # Arc retrieval (D-ARC-RETRIEVE) ranks the caller-visible arc_template set under
    # the read predicate (no target id beyond the book gate; arc_template is a
    # deps/ registry table — untouched by the re-key, so tc.user_id stays): SQL
    # pre-filter → platform-embed query → cosine → match_reason → genre-degrade,
    # with a bounded owner-scoped lazy back-fill of NULL-vector arcs (mirrors the
    # motif retriever).
    candidates = await retriever.retrieve_arcs(
        tc.user_id, book_id=meta.book_id, project_id=pid,
        premise=premise, genre=genre, limit=limit,
    )
    # L1/L2 reference-first on the ranked candidates: project each (heavy) arc_template
    # body through the contract while keeping the score + match_reason wrapper. The
    # retriever already bounded to `limit` (limit=None → truncated=0); `**meta` reports
    # the detail level + count. Owner vs non-owner projection is preserved pre-contract.
    arc_dicts, meta = apply_response_contract(
        [
            c.arc_template.model_dump(mode="json")
            if getattr(c.arc_template, "owner_user_id", None) == tc.user_id
            else _arc_public_projection(c.arc_template)
            for c in candidates
        ],
        ref_fields=_ARC_REF_FIELDS, detail=detail,
    )
    return {
        "candidates": [
            {"arc_template": arc_dicts[i], "score": c.score, "match_reason": c.match_reason}
            for i, c in enumerate(candidates)
        ],
        **meta,
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
    # target='user'        — your private library (owner-stamped, the default).
    # target='book_shared' — author straight into a book's SHARED tier
    #                        (D-MOTIF-ADOPT-BOOK-COLLAB-TIER); requires book_id + EDIT on the book.
    # A system/both-NULL row stays migrate/seed-only (no Literal admits it).
    target: Literal["user", "book_shared"] = "user"
    book_id: str | None = None
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
    # target='book_shared': author straight into a book's SHARED tier — EDIT-gate the book first
    # (the cross-tenant write is safe only behind the grant). A shared row is forced private (the
    # visibility arg is ignored for shared — the CHECK motif_book_shared_shape requires private).
    book_id: UUID | None = None
    book_shared = args.target == "book_shared"
    if book_shared:
        if not args.book_id:
            return {"success": False, "error": "book_id is required when target='book_shared'"}
        book_id = UUID(args.book_id)
        await _gate(tc, book_id, GrantLevel.EDIT)
    from app.db.models import MotifCreateArgs as _RepoCreateArgs
    try:
        create_args = _RepoCreateArgs(
            code=args.code, name=args.name, language=args.language, kind=args.kind,
            summary=args.summary, genre_tags=args.genre_tags, roles=args.roles,
            beats=args.beats, preconditions=args.preconditions, effects=args.effects,
            tension_target=args.tension_target, emotion_target=args.emotion_target,
            examples=args.examples, visibility="private" if book_shared else args.visibility,
        )
    except (ValueError, TypeError) as exc:  # pydantic ValidationError ⊂ ValueError
        return {"success": False, "error": "invalid motif fields", "detail": str(exc)[:300]}
    try:
        motif = await repo.create(
            tc.user_id, create_args, book_id=book_id, book_shared=book_shared,
        )
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
        synonyms=["archive motif", "delete motif", "retire trope", "remove a motif from my library"],
        tool_name="composition_motif_archive",
    ),
)
async def composition_motif_archive(
    ctx: MCPContext,
    motif_id: Annotated[str, "The motif to archive."],
    book_id: Annotated[
        str | None,
        "Set ONLY to archive a SHARED book-tier motif — requires EDIT on that book; any "
        "EDIT-grantee may archive a shared row. Omit for one of YOUR OWN motifs.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    mid = UUID(motif_id)
    if book_id is not None:
        # SHARED tier (D-MOTIF-ADOPT-BOOK-COLLAB-TIER): access is the book grant, not ownership.
        # EDIT-gate the book, confirm the target is a shared row IN this book (else H13), archive.
        bid = UUID(book_id)
        await _gate(tc, bid, GrantLevel.EDIT)
        target = await repo.get_in_book(tc.user_id, mid, bid)
        if target is None or not target.book_shared or target.book_id != bid:
            raise uniform_not_accessible()
        await repo.archive_shared(tc.user_id, mid, bid)
        return {"motif_id": motif_id, "archived": True, "_meta": {"undo_hint": None}}
    # USER scope: you may only archive YOUR OWN motif. The owner-resolver raises the
    # uniform deny for a missing/foreign/system row before any write.
    guard = require_user_scope(_motif_owner_resolver(repo))
    await guard(tc, mid)
    await repo.archive(tc.user_id, mid)
    # archive() flips status='archived'; un-archive is composition_motif_patch(status='active'),
    # but archive() doesn't return the post-write version, so the MCP undo stays honest None here.
    return {"motif_id": motif_id, "archived": True, "_meta": {"undo_hint": None}}


# ── D-MOTIF-MCP-PATCH-SHARED — edit a motif's content (the MCP twin of HTTP PATCH /motifs/{id}).
# Default: edit YOUR OWN motif (owner-keyed). With book_id: edit a SHARED book-tier row — any
# EDIT-grantee may (the book grant is the gate; D-MOTIF-ADOPT-BOOK-COLLAB-TIER). Optimistic-lock
# via expected_version (a stale version → applied_conflict, never a blind clobber). Visibility/
# publish is deliberately NOT editable here (publishing is a separate human flow; a shared row is
# private by CHECK anyway).
class _MotifPatchToolArgs(ForbidExtra):
    motif_id: str
    expected_version: int
    # book_id set → edit the SHARED row in that book (EDIT-gated); omit → edit your own motif.
    book_id: str | None = None
    name: str | None = None
    kind: _MotifKind | None = None
    category: str | None = None
    summary: str | None = None
    genre_tags: list[str] | None = None
    roles: list[dict[str, Any]] | None = None
    beats: list[dict[str, Any]] | None = None
    preconditions: list[dict[str, Any]] | None = None
    effects: list[dict[str, Any]] | None = None
    annotations: dict[str, Any] | None = None
    tension_target: int | None = None
    emotion_target: str | None = None
    status: Literal["draft", "active", "archived"] | None = None


_MOTIF_PATCH_META = {"motif_id", "expected_version", "book_id"}


@mcp_server.tool(
    name="composition_motif_patch",
    description=(
        "Edit a motif's content — name, summary, kind, genres, roles, beats, preconditions, "
        "effects, tension, status. By default edits one of YOUR OWN motifs. Pass `book_id` to edit "
        "a SHARED book-tier motif (any collaborator with EDIT on the book may). Requires "
        "`expected_version` (optimistic concurrency — a stale version is refused, no blind "
        "clobber). To publish, archive, or adopt instead, use those dedicated tools."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["edit motif", "update motif", "rename motif", "change motif summary",
                  "edit trope", "fix motif beats", "edit shared motif"],
        tool_name="composition_motif_patch",
    ),
)
async def composition_motif_patch(ctx: MCPContext, args: _MotifPatchToolArgs) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    mid = UUID(args.motif_id)
    from app.db.models import MotifPatchArgs as _Patch

    # Only the fields the caller actually set become the patch (PATCH semantics — exclude_unset).
    patch_fields = args.model_fields_set - _MOTIF_PATCH_META
    if not patch_fields:
        return {"success": False, "error": "no fields to update"}
    try:
        patch = _Patch(**{f: getattr(args, f) for f in patch_fields})
    except (ValueError, TypeError) as exc:   # pydantic ValidationError ⊂ ValueError
        return {"success": False, "error": "invalid motif fields", "detail": str(exc)[:300]}

    bid: UUID | None = None
    if args.book_id is not None:
        # SHARED-tier edit: the book grant is the gate (not ownership). EDIT-gate, confirm the
        # target is a shared row IN this book (so undo/prior reads the right row), then patch_shared.
        bid = UUID(args.book_id)
        await _gate(tc, bid, GrantLevel.EDIT)
        prior = await repo.get_in_book(tc.user_id, mid, bid)
        if prior is None or not prior.book_shared or prior.book_id != bid:
            raise uniform_not_accessible()
    else:
        # OWNER edit: must be the caller's OWN row (system/public/foreign → deny).
        prior = await repo.get_visible(tc.user_id, mid)
        if prior is None or prior.owner_user_id != tc.user_id:
            raise uniform_not_accessible()

    try:
        if bid is not None:
            motif = await repo.patch_shared(
                tc.user_id, mid, bid, patch, expected_version=args.expected_version)
        else:
            motif = await repo.patch(
                tc.user_id, mid, patch, expected_version=args.expected_version)
    except VersionMismatchError as exc:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "stale expected_version — refetch and retry",
            "current_version": exc.current.version,
        }
    except asyncpg.UniqueViolationError:
        return {"success": False, "outcome": "applied_conflict",
                "error": "a motif with this code + language already exists"}
    if motif is None:
        raise uniform_not_accessible()

    out = motif.model_dump(mode="json")
    # MD-2 honest undo: patch the changed fields BACK to their prior values + the new version.
    prior_dump = prior.model_dump(mode="json")
    undo_values = {f: prior_dump.get(f) for f in patch_fields}
    undo_args: dict[str, Any] = {
        "motif_id": args.motif_id, "expected_version": motif.version, **undo_values,
    }
    if args.book_id is not None:
        undo_args["book_id"] = args.book_id
    out["_meta"] = {"undo_hint": _undo("composition_motif_patch", **undo_args)}
    return out


# ── motif_link edge-walk (D-MOTIF-LINK-EDGEWALK) — traverse + edit the relationship
# graph (composed_of = a pattern's members, precedes = legal succession, variant_of =
# ATU variants). READ over any VISIBLE motif; WRITE only between TWO of YOUR OWN motifs
# (the both-owned gate — a user may never reshape the shared/system graph; the F0
# motif_link_guard trigger also blocks cross-tier + cycles at the DB).
class _MotifLinkCreateArgs(ForbidExtra):
    from_motif_id: str
    to_motif_id: str
    kind: Literal["composed_of", "precedes", "variant_of"]
    ord: int | None = None
    # book_id (D-MOTIF-LINK-SHARED-TIER): set to link two SHARED motifs of that book — requires
    # EDIT on the book; both endpoints must be book_shared in it. Omit for your own user-tier graph.
    book_id: str | None = None


@mcp_server.tool(
    name="composition_motif_link_list",
    description=(
        "List the relationship edges of one motif — its `composed_of` members, "
        "`precedes` successions, and `variant_of` links, with each neighbor's code + "
        "name. Walk the graph by following a neighbor id into another list call. "
        "direction: 'out' (this→neighbor), 'in' (neighbor→this), or 'both' (default)."
    ),
    meta=require_meta(
        "R", "user",
        synonyms=["motif links", "related motifs", "motif graph", "composed of",
                  "what follows this motif", "motif variants", "traverse motifs"],
        tool_name="composition_motif_link_list",
    ),
)
async def composition_motif_link_list(
    ctx: MCPContext,
    motif_id: Annotated[str, "The motif whose edges to list (must be visible to you)."],
    direction: Annotated[str, "'out', 'in', or 'both'."] = "both",
    kinds: Annotated[list[str] | None, "Optional filter, e.g. ['precedes']."] = None,
    book_id: Annotated[
        str | None,
        "Set to walk a SHARED book motif's graph (D-MOTIF-LINK-SHARED-TIER) — requires VIEW on "
        "the book. Omit for your own/system/public motif.",
    ] = None,
) -> dict:
    # @small_return: bounded, lightweight edge rows (each = kind/ord/direction + a
    # {id,code,name} neighbor stub — no motif body). Nothing heavy to project away, so
    # a detail=summary level would equal full; a get_by_id on a neighbor is motif_get.
    tc = _ctx(ctx)
    if direction not in ("out", "in", "both"):
        return {"success": False, "error": "direction must be 'out', 'in', or 'both'"}
    bid: UUID | None = None
    if book_id is not None:
        bid = UUID(book_id)
        await _gate(tc, bid, GrantLevel.VIEW)   # the book grant is the read access for the shared graph
    repo = MotifRepo(get_pool())
    # READPRED: list_links returns [] for a motif you can't see (IDOR-safe — empty is
    # indistinguishable from 'no edges', no existence oracle).
    links = await repo.list_links(
        tc.user_id, UUID(motif_id), direction=direction, kinds=kinds, book_id=bid,
    )
    return {"motif_id": motif_id, "links": links, "count": len(links)}


@mcp_server.tool(
    name="composition_motif_link_create",
    description=(
        "Create a relationship edge between two motifs: `composed_of` (a pattern's member), "
        "`precedes` (legal succession), or `variant_of`. By default both endpoints must be YOUR "
        "OWN motifs (you cannot edit the system graph). Pass `book_id` to link two SHARED motifs "
        "of that book (collaborators co-edit the shared graph — needs EDIT on the book). A "
        "duplicate edge, a self-link, or a cycle (on composed_of/precedes) is refused."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["link motifs", "connect motifs", "add motif edge", "compose pattern",
                  "set succession", "mark variant", "relate tropes"],
        tool_name="composition_motif_link_create",
    ),
)
async def composition_motif_link_create(ctx: MCPContext, args: _MotifLinkCreateArgs) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    bid: UUID | None = None
    if args.book_id is not None:
        # SHARED-tier edge (D-MOTIF-LINK-SHARED-TIER): EDIT on the book is the write gate; the repo
        # then requires both endpoints to be book_shared in this book.
        bid = UUID(args.book_id)
        await _gate(tc, bid, GrantLevel.EDIT)
    try:
        link = await repo.create_link(
            tc.user_id, UUID(args.from_motif_id), UUID(args.to_motif_id), args.kind,
            ord=args.ord, book_id=bid,
        )
    except LookupError:
        # an endpoint isn't in the required scope (your own, or this book's shared tier) → deny.
        raise uniform_not_accessible()
    except asyncpg.UniqueViolationError:
        return {"success": False, "outcome": "applied_conflict",
                "error": "that edge already exists"}
    except asyncpg.CheckViolationError:
        # the motif_link_guard rejected a self-link / cycle / cross-tier edge.
        return {"success": False, "error": "invalid edge (self-link, cycle, or cross-tier)"}
    out = link.model_dump(mode="json")
    undo_args = {"link_id": str(link.id)}
    if args.book_id is not None:
        undo_args["book_id"] = args.book_id   # the reverse delete needs the same book gate
    out["_meta"] = {"undo_hint": _undo("composition_motif_link_delete", **undo_args)}
    return out


@mcp_server.tool(
    name="composition_motif_link_delete",
    description=(
        "Delete a relationship edge (hard delete — edges have no children). By default the edge "
        "must be on one of YOUR motifs; pass `book_id` to delete an edge in that book's SHARED "
        "graph (needs EDIT on the book). A foreign/system/missing/wrong-book edge is refused."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["unlink motifs", "remove motif edge", "delete motif link", "disconnect motifs"],
        tool_name="composition_motif_link_delete",
    ),
)
async def composition_motif_link_delete(
    ctx: MCPContext,
    link_id: Annotated[str, "The motif-link edge id (must be on one of your motifs)."],
    book_id: Annotated[
        str | None,
        "Set to delete an edge in a SHARED book graph (D-MOTIF-LINK-SHARED-TIER) — requires EDIT "
        "on the book. Omit for an edge on one of your own motifs.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    bid: UUID | None = None
    if book_id is not None:
        bid = UUID(book_id)
        await _gate(tc, bid, GrantLevel.EDIT)
    deleted = await repo.delete_link(tc.user_id, UUID(link_id), book_id=bid)
    if not deleted:
        raise uniform_not_accessible()
    # A hard delete has no verified reverse op (the row is gone) → undo unavailable.
    return {"deleted": True, "link_id": link_id, "_meta": {"undo_hint": None}}


class _MotifBindArgs(ForbidExtra):
    project_id: str
    node_id: str
    motif_id: str
    role_bindings: dict[str, str] = {}


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
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    node_id = UUID(args.node_id)
    # IDOR #1: the chapter node is in the gated Work's project.
    node = await outline.get_node(node_id)
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    # IDOR #2: the motif is caller-visible (you can only bind a motif you can see).
    repo = MotifRepo(get_pool())
    motif = await repo.get_visible(tc.user_id, UUID(args.motif_id))
    if motif is None:
        raise uniform_not_accessible()
    # WIRED to W2's engine (engine/motif_select.py) — the one-engine-two-entries seam
    # (RECONCILE §2; D-MOTIF-MCP-BIND-WIRING cleared). The agent supplies role_bindings
    # ({role_key: entity_id}) directly, so the binding is built without the glossary
    # cast-name resolution the HTTP twin does (the agent already chose the entities); the
    # swap runs in ONE transaction exactly like PATCH …/motif.
    from app.db.repositories.motif_application import MotifApplicationRepo
    from app.engine.motif_select import (
        MotifBinding, MotifSwapError, SelectedMotif, _bind_annotations, apply_motif_swap,
    )
    pool = get_pool()
    apps = MotifApplicationRepo(pool)
    sel = SelectedMotif(motif=motif, score=1.0, match_reason={})
    binding = MotifBinding(
        role_bindings=dict(args.role_bindings),
        unresolved_roles=[],
        annotations=_bind_annotations(motif, args.role_bindings),
        warning=None,
    )
    try:
        async with pool.acquire() as c:
            async with c.transaction():
                res = await apply_motif_swap(
                    outline, apps, pid, meta.book_id, node_id,
                    new_motif=sel, binding=binding, cast_names={},
                    created_by=tc.user_id,
                    k_ceiling=settings.compose_diverge_k,
                    high_threshold=settings.plan_high_tension_threshold,
                    min_scenes=settings.plan_min_scenes_per_chapter,
                    max_scenes=settings.plan_max_scenes_per_chapter, conn=c,
                )
    except MotifSwapError:
        # H13 uniform — a swap failure (e.g. node not a chapter) is not an oracle.
        raise uniform_not_accessible()
    return {
        "success": True,
        "chapter_node_id": res.chapter_node_id,
        "archived_scene_ids": res.archived_scene_ids,
        "new_scene_ids": res.new_scene_ids,
        "orphaned_thread_ids": res.orphaned_thread_ids,
        "new_motif_id": res.new_motif_id,
        "undo_token": res.undo_token,
        # A-tier reversible: the verified inverse is composition_motif_unbind(undo_token).
        "_meta": {"undo_hint": {"tool": "composition_motif_unbind",
                                "args": {"project_id": args.project_id, "node_id": args.node_id,
                                         "undo_token": res.undo_token}}},
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
    node_id: Annotated[str, "The chapter node to clear / undo a bind on."],
    undo_token: Annotated[
        dict | None,
        "The undo_token from a prior composition_motif_bind — when present, does the EXACT "
        "inverse (restores the pre-bind scenes + prose). Omit to CLEAR the chapter's motif.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(project_id)
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    nid = UUID(node_id)
    node = await outline.get_node(nid)
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    # WIRED to W2's engine (D-MOTIF-MCP-BIND-WIRING cleared): a token does the exact
    # inverse of a bind (undo_motif_swap); no token CLEARS the chapter's motif
    # (apply_motif_swap with new_motif=None) — the two modes of the HTTP twin.
    from app.db.repositories.motif_application import MotifApplicationRepo
    from app.engine.motif_select import apply_motif_swap, MotifSwapError, undo_motif_swap
    pool = get_pool()
    apps = MotifApplicationRepo(pool)
    if undo_token is not None:
        async with pool.acquire() as c:
            async with c.transaction():
                res = await undo_motif_swap(
                    outline, apps, pid, undo_token, conn=c,
                )
        return {"success": True, "undone": True, **res}
    try:
        async with pool.acquire() as c:
            async with c.transaction():
                res = await apply_motif_swap(
                    outline, apps, pid, meta.book_id, nid,
                    new_motif=None, binding=None, cast_names={},
                    created_by=tc.user_id,
                    k_ceiling=settings.compose_diverge_k,
                    high_threshold=settings.plan_high_tension_threshold,
                    min_scenes=settings.plan_min_scenes_per_chapter,
                    max_scenes=settings.plan_max_scenes_per_chapter, conn=c,
                )
    except MotifSwapError:
        raise uniform_not_accessible()
    return {
        "success": True, "cleared": True,
        "chapter_node_id": res.chapter_node_id,
        "archived_scene_ids": res.archived_scene_ids,
        "new_scene_ids": res.new_scene_ids,
        "undo_token": res.undo_token,
    }


# ── Tier W — motif confirm-token ops (cost/tenancy-gated) ─────────────────────


class _MotifAdoptArgs(ForbidExtra):
    motif_id: str
    # target="book"        — model A: a PRIVATE per-user label (D-MOTIF-ADOPT-PER-BOOK). The clone
    #                        is owner-stamped = the caller; book_id only narrows what the owner sees.
    # target="book_shared" — model B: the book's SHARED tier (D-MOTIF-ADOPT-BOOK-COLLAB-TIER) — the
    #                        clone is visible to the book's VIEW-grantees + writable by EDIT-grantees.
    # Both require book_id AND EDIT on the book (gated at propose + re-gated at confirm). target="user"
    # is the plain private library (no book context).
    target: Literal["user", "book", "book_shared"] = "user"
    book_id: str | None = None
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
    # target="book"/"book_shared": the clone is tied to a book (D-MOTIF-ADOPT-PER-BOOK /
    # D-MOTIF-ADOPT-BOOK-COLLAB-TIER). You may only adopt INTO a book you can EDIT — gate it now
    # and re-gate at confirm (a grant revoked between propose and confirm stops the clone,
    # mirroring motif_mine scope=book).
    book_id: str | None = None
    book_shared = args.target == "book_shared"
    if args.target in ("book", "book_shared"):
        if not args.book_id:
            return {"success": False,
                    "error": f"book_id is required when target='{args.target}'"}
        await _gate(tc, UUID(args.book_id), GrantLevel.EDIT)
        book_id = args.book_id
    payload = {
        "motif_id": args.motif_id,
        "retag_genres": args.retag_genres,
        "book_id": book_id,
        "book_shared": book_shared,
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
            "into": "book_shared" if book_shared else ("book" if book_id else "user"),
        },
    }


class _MotifMineArgs(ForbidExtra):
    scope: Literal["book", "corpus"]
    book_id: str | None = None
    min_support: int = 2
    promote_to: Literal["draft"] = "draft"
    # promote_target='book_shared' lands the mined drafts in the book's SHARED tier
    # (D-MOTIF-ADOPT-BOOK-COLLAB-TIER) instead of your private library — valid ONLY with
    # scope='book' (a corpus mine has no single book). 'user' = your private drafts (default).
    promote_target: Literal["user", "book_shared"] = "user"
    language: str = "en"
    # The BYOK abstraction/judge model the worker runs (provider-gateway invariant: NO
    # platform model literal — the user picks it, same as conformance's deep overlay).
    # Required at run: the worker fails closed if neither this nor the platform fallback
    # (settings.motif_deconstruct_model_ref) resolves a ref.
    model_ref: str | None = None
    model_source: str | None = None


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
        async_job=True,
        tool_name="composition_motif_mine",
    ),
)
async def composition_motif_mine(ctx: MCPContext, args: _MotifMineArgs) -> dict:
    # @small_return: Tier-W PROPOSE card — returns a single {confirm_token, estimate}
    # object (no set, no motif bodies); the mined drafts land via the background job,
    # read back through composition_motif_search/get.
    tc = _ctx(ctx)
    if args.scope == "book":
        if not args.book_id:
            return {"success": False, "error": "book_id is required when scope='book'"}
        # BOOK(EDIT) gate on the named book (mining writes draft motifs informed by it).
        await _gate(tc, UUID(args.book_id), GrantLevel.EDIT)
    # promote_target='book_shared' needs a single book to land in — reject it for a corpus mine.
    if args.promote_target == "book_shared" and (args.scope != "book" or not args.book_id):
        return {"success": False,
                "error": "promote_target='book_shared' requires scope='book' with a book_id"}
    # MD-4: corpus mining has no single resource id → gated by envelope identity only;
    # the worker filters every read on user_id=caller + re-checks each book's grant.
    estimate = _mine_estimate(scope=args.scope)
    payload = {
        "scope": args.scope,
        "book_id": args.book_id,
        "min_support": args.min_support,
        "promote_to": args.promote_to,
        "promote_target": args.promote_target,
        "language": args.language,
        # BYOK abstraction model rides through to the worker (provider-gateway invariant).
        "model_ref": args.model_ref,
        "model_source": args.model_source,
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
    # The SOURCE language (R1.1.3 — a first-class dedup/embed key; an imported zh work
    # tagged 'en' is a re-key migration later). The deconstruct threads this onto the
    # derived arc_template + member motifs.
    language: str = "en"
    # The BYOK deconstruct model the worker runs (provider-gateway invariant: NO platform
    # model literal — the user picks it, same as conformance's deep overlay). Required at
    # run: the worker fails closed if neither this nor settings.motif_deconstruct_model_ref
    # resolves a ref.
    model_ref: str | None = None
    model_source: str | None = None


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
        async_job=True,
        tool_name="composition_arc_import_analyze",
    ),
)
async def composition_arc_import_analyze(ctx: MCPContext, args: _ArcImportArgs) -> dict:
    # @small_return: Tier-W PROPOSE card — returns a single {confirm_token, estimate}
    # object (no set); the derived arc_template lands via the background job and is read
    # back through composition_arc_suggest.
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
        "language": args.language,
        # BYOK deconstruct model rides through to the worker (provider-gateway invariant).
        "model_ref": args.model_ref,
        "model_source": args.model_source,
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
    # BA4 (23): arc-scope conformance diffs the SPEC (structure_node) against the
    # prose — pass `arc_id` (a structure_node id), NOT a template id. "Did the prose
    # realize MY plan" is the question; template drift is the separate
    # composition_arc_template_drift tool. The arc-scope deep overlay
    # (D-W10-ARC-CONFORMANCE-DEEP-JOB) also tags the book's prose with a BYOK
    # classify model, so `model_ref` is required for arc scope.
    arc_id: str | None = None
    model_ref: str | None = None
    model_source: str | None = None


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
        async_job=True,
        tool_name="composition_conformance_run",
    ),
)
async def composition_conformance_run(ctx: MCPContext, args: _ConformanceRunArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    if args.scope == "chapter":
        if not args.chapter_id:
            return {"success": False, "error": "chapter_id is required when scope='chapter'"}
        outline = OutlineRepo(get_pool())
        node = await outline.get_node(UUID(args.chapter_id))
        # IDOR: the chapter is in the gated Work's project.
        if node is None or node.project_id != pid:
            raise uniform_not_accessible()
    else:  # scope == "arc" — the deep overlay job (D-W10-ARC-CONFORMANCE-DEEP-JOB)
        if not args.arc_id:
            return {"success": False, "error": "arc_id is required when scope='arc'"}
        if not args.model_ref:
            return {"success": False,
                    "error": "model_ref is required when scope='arc' (the deep overlay tags prose)"}
        # BA4: the arc is a structure_node in THIS gated book (book-scoped — no
        # user filter; the E0 book grant above IS the access control). A foreign /
        # missing arc is the H13 uniform deny (no existence oracle). NOTE (23 B4↔A4):
        # the confirm-effect dispatch (routers/actions.py) + the arc-conformance
        # worker must read this `arc_id` (a structure_node) via A4's arc_id-keyed
        # reader, replacing the annotations->>'arc_template_id' scan.
        arc_node = await StructureRepo(get_pool()).get(UUID(args.arc_id))
        if arc_node is None or arc_node.book_id != meta.book_id:
            raise uniform_not_accessible()
    estimate = _mine_estimate(scope="book")
    payload = {
        "project_id": args.project_id,
        "book_id": str(meta.book_id),
        "scope": args.scope,
        "chapter_id": args.chapter_id,
        "arc_id": args.arc_id,
        "model_ref": args.model_ref,
        "model_source": args.model_source,
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
    await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    jobs = GenerationJobsRepo(get_pool())
    job = await jobs.get(UUID(job_id))
    # Cross-Work IDOR (exact clone of composition_get_generation_job): the repo
    # fetches by id only — confirm the job is in THIS project (a job_id from
    # another Work can't be read through this one). A miss is uniform.
    if job is None or job.project_id != pid:
        raise uniform_not_accessible()
    return job.model_dump(mode="json")


@mcp_server.tool(
    name="composition_conformance_status",
    description=(
        "Read conformance FRESHNESS for a book's arcs — is each arc's last conformance "
        "report still true of the current canon, or has the book MOVED since (prose "
        "published, spec edited, or the prose index gone stale)? Cheap: no LLM, no "
        "re-extract — compares the stored per-arc snapshot to current chapter markers + "
        "spec fingerprints. Returns per-arc {dirty, dirty_reasons, stale_chapters, "
        "summary, computed_at, deep} + an index.stale_chapter_count rollup; an arc that "
        "never ran conformance is {computed_at:null, dirty:true, dirty_reasons:['never_run']}. "
        "Pass arc_id to scope to one arc. To actually RE-RUN conformance use "
        "composition_conformance_run. VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["conformance status", "is conformance stale", "arc dirty",
                  "conformance freshness", "did the book move since conformance",
                  "stale conformance", "conformance staleness"],
        tool_name="composition_conformance_status",
    ),
)
async def composition_conformance_status(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    arc_id: Annotated[
        str | None,
        "Optional structure_node arc id — scope the response to one arc.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    # IX-14 — book-scoped read; the E0 VIEW gate IS the access control (the internal
    # canon-markers read inside is safe only behind it). H13 uniform on denial.
    await _gate(tc, bid, GrantLevel.VIEW)
    from app.engine.arc_conformance_orchestrate import compute_conformance_status

    return await compute_conformance_status(
        pool=get_pool(), book_client=get_book_client(), book_id=bid,
        arc_id=UUID(arc_id) if arc_id else None,
    )


# ── PlanForge (M4) — plan_* tools ─────────────────────────────────────────────
# Thin MCP wrappers over PlanForgeService (the SAME service the /v1/composition
# .../plan/* router uses). Scope=book, envelope identity only, VIEW reads / EDIT
# writes through the `_gate` chokepoint (mirrors the HTTP router's `_gate_book`).
# The chat plan-forge skill drives the propose→checkpoint→validate→compile HIL flow.


def _plan_svc():
    from app.clients.llm_client import get_llm_client
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.services.plan_forge_service import PlanForgeService

    pool = get_pool()
    return PlanForgeService(
        PlanRunsRepo(pool), GenerationJobsRepo(pool), WorksRepo(pool), llm=get_llm_client(),
    )


def _opt_uuid(v: str | None) -> UUID | None:
    return UUID(v) if v else None


@mcp_server.tool(
    name="plan_propose_spec",
    description=(
        "PlanForge: turn a novel-system source document into a structured "
        "NovelSystemSpec + analysis. Writes a DRAFT proposal — the run lands at "
        "status='proposed' and a human must approve it before anything becomes "
        "canonical; nothing canonical changes at call time. mode='rules' proposes "
        "synchronously; mode='llm' enqueues an async job (poll the run). model_ref is "
        "optional for mode='llm' — omit it to use the author's default planner model "
        "(their pinned 'planner' default, else their best chat model); pass one only "
        "when the author names a specific model. EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["plan a novel", "propose spec", "novel system spec", "planforge", "story plan"],
        async_job=True, paid=True,   # spends the author's LLM budget (planner model)
        tool_name="plan_propose_spec",
    ),
)
async def plan_propose_spec(
    ctx: MCPContext,
    book_id: Annotated[str, "The book to plan (UUID)."],
    source_markdown: Annotated[str, "The novel-system source document (markdown)."],
    mode: Annotated[Literal["rules", "llm"], "rules = sync; llm = async job."] = "rules",
    model_ref: Annotated[
        str | None,
        "optional user_model id for mode='llm' — omit to use the author's default planner model.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    svc = _plan_svc()
    run, is_async, job_id = await svc.create_run(
        tc.user_id, bid, source_markdown=source_markdown, mode=mode,
        model_ref=_opt_uuid(model_ref), force=False,
    )
    detail = await svc.get_run_detail(tc.user_id, bid, run.id)
    return {
        "run_id": str(run.id),
        "async": is_async,
        "job_id": str(job_id) if job_id else None,
        "run": detail,
    }


@mcp_server.tool(
    name="plan_validate",
    description="PlanForge: run the S1–S8 golden linter (+ fidelity report) on a run's spec. VIEW required.",
    meta=require_meta("R", "book", synonyms=["validate plan", "check spec", "golden rules"], tool_name="plan_validate"),
)
async def plan_validate(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)
    report = await _plan_svc().validate(tc.user_id, bid, UUID(run_id))
    if report is None:
        raise uniform_not_accessible()
    return report


@mcp_server.tool(
    name="plan_self_check",
    description="PlanForge: ranked gaps + fidelity score for a run's spec (no user pointing to fields). VIEW required.",
    meta=require_meta("R", "book", synonyms=["self check plan", "plan gaps", "what is missing"], tool_name="plan_self_check"),
)
async def plan_self_check(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)
    out = await _plan_svc().self_check(tc.user_id, bid, UUID(run_id))
    if out is None:
        raise uniform_not_accessible()
    return out


@mcp_server.tool(
    name="plan_interpret_feedback",
    description=(
        "PlanForge: interpret the user's free-text plan feedback into a structured "
        "FeedbackInterpretation (intent + focus paths + suggested revision). "
        "model_ref is optional — omit it to use the author's default planner model. "
        "EDIT required."
    ),
    meta=require_meta("A", "book", synonyms=["interpret feedback", "understand my note", "plan feedback"], tool_name="plan_interpret_feedback"),
)
async def plan_interpret_feedback(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    user_message: Annotated[str, "The user's free-text feedback on the plan."],
    model_ref: Annotated[
        str | None, "optional user_model id — omit to use the author's default planner model.",
    ] = None,
    apply_mode_hint: Annotated[Literal["auto", "confirm", "diagnose_only"] | None, "Optional apply-mode hint."] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    out = await _plan_svc().interpret(
        tc.user_id, bid, UUID(run_id),
        user_message=user_message, model_ref=_opt_uuid(model_ref), apply_mode_hint=apply_mode_hint,
    )
    if out is None:
        raise uniform_not_accessible()
    return out


@mcp_server.tool(
    name="plan_apply_revision",
    description=(
        "PlanForge: apply a draft revision to the spec (refine). Returns applied / "
        "no_change / rejected — an accepted-but-unchanged refine is `no_change`, never "
        "`applied` (D-PF-APPLY-HONESTY). model_ref is optional — omit it to use the "
        "author's default planner model. EDIT required."
    ),
    meta=require_meta("A", "book", synonyms=["apply revision", "refine plan", "update spec"],
                      async_job=True, paid=True,  # spends the author's LLM budget
                      tool_name="plan_apply_revision"),
)
async def plan_apply_revision(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    model_ref: Annotated[
        str | None, "optional user_model id — omit to use the author's default planner model.",
    ] = None,
    draft_revision: Annotated[dict[str, Any] | None, "The revision to apply (fields/paths)."] = None,
    focus_paths: Annotated[list[str] | None, "Optional spec paths to focus the refine."] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        mode, payload = await _plan_svc().refine(
            tc.user_id, bid, UUID(run_id),
            model_ref=_opt_uuid(model_ref), revision=draft_revision, focus_paths=focus_paths,
        )
    except LookupError:
        raise uniform_not_accessible()
    return {"mode": mode, **payload}


@mcp_server.tool(
    name="plan_review_checkpoint",
    description=(
        "PlanForge: approve or hold a checkpoint. Omit pass_id for the SPEC checkpoint "
        "(approved=true marks the run validated-intent). Give pass_id to review one COMPILER "
        "PASS — the only way a blocking pass ('cast', 'beats') is ever accepted, and therefore "
        "the only way the compiler proceeds past it. `edits` deep-merges into that pass's "
        "artifact and saves a NEW one, which stales everything downstream by derivation (that "
        "is intended: scenes planned against the old cast should not survive an edit to the "
        "cast). Accepting 'cast' requires its glossary seed proposal to have been APPLIED. "
        "No LLM. EDIT required."
    ),
    meta=require_meta("A", "book", synonyms=["approve checkpoint", "accept plan", "hold plan", "accept pass", "accept cast"], tool_name="plan_review_checkpoint"),
)
async def plan_review_checkpoint(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    approved: Annotated[bool, "True to advance the checkpoint; False to hold."],
    pass_id: Annotated[
        PlanPassId | None,
        "Which compiler pass to review. Omit for the spec checkpoint.",
    ] = None,
    edits: Annotated[
        dict | None,
        "Optional deep-merge patch into the pass's artifact (pass_id required). Saves a NEW "
        "artifact; downstream passes go stale by derivation.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        out = await _plan_svc().review_checkpoint(
            tc.user_id, bid, UUID(run_id), approved=approved,
            pass_id=pass_id, edits=edits,
        )
    except ValueError as exc:
        # A refusal here is the GATE doing its job (an unaccepted seed proposal, a pass that never
        # completed). The agent gets the REASON, so it can act on it — a bare failure would just be
        # retried blindly, and a silent success would be far worse: the compiler would sail past the
        # one checkpoint the author exists to answer.
        return {"success": False, "error": "checkpoint refused", "detail": str(exc)[:300]}
    if out is None:
        raise uniform_not_accessible()
    return out


@mcp_server.tool(
    name="plan_handoff_autofix",
    description=(
        "PlanForge: batch-apply the top self-check gaps as a bounded refine loop "
        "(max_rounds, default 3). Stops when no gaps remain or a round makes no change. "
        "model_ref is optional — omit it to use the author's default planner model. "
        "EDIT required."
    ),
    meta=require_meta("A", "book", synonyms=["autofix plan", "fix gaps", "handoff autofix", "auto refine"], tool_name="plan_handoff_autofix"),
)
async def plan_handoff_autofix(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    model_ref: Annotated[
        str | None, "optional user_model id — omit to use the author's default planner model.",
    ] = None,
    max_rounds: Annotated[int, "Max refine rounds (1–5, default 3)."] = 3,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    out = await _plan_svc().handoff_autofix(
        tc.user_id, bid, UUID(run_id), model_ref=_opt_uuid(model_ref), max_rounds=max_rounds,
    )
    if out is None:
        raise uniform_not_accessible()
    return out


@mcp_server.tool(
    name="plan_compile",
    description=(
        "PlanForge: compile a validated spec's arc into a PlanningPackage (blocks S1–S8 "
        "failures with 422). run_pipeline=true also kicks the planning pipeline; "
        "model_ref is optional there too — omit it to use the author's default "
        "planner model. EDIT required."
    ),
    meta=require_meta("A", "book", synonyms=["compile plan", "planning package", "build plan"],
                      # `run_pipeline=true` runs the LLM passes. A tool that MAY spend must declare
                      # `paid` — the user is warned on the possibility, not on the outcome.
                      async_job=True, paid=True,
                      tool_name="plan_compile"),
)
async def plan_compile(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    arc_id: Annotated[str, "The arc to compile (e.g. 'arc_2')."],
    run_pipeline: Annotated[bool, "Also start the planning pipeline job."] = False,
    model_ref: Annotated[
        str | None,
        "optional user_model id for run_pipeline=true — omit to use the author's default planner model.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        mode, payload = await _plan_svc().compile(
            tc.user_id, bid, UUID(run_id),
            arc_id=arc_id, run_pipeline=run_pipeline, model_ref=_opt_uuid(model_ref),
        )
    except LookupError:
        raise uniform_not_accessible()
    return {"mode": mode, **payload}


# ── 27 V2-F1 — the COMPILER PASS surface (PF-1..PF-11) ────────────────────────
#
# The agent-facing half of the multi-pass compiler. Three tools, and the contract they share is the
# one thing that makes the whole design safe to hand an LLM: **the agent cannot skip a checkpoint.**
# `plan_run_pass` refuses (with the blockers named) when an upstream is stale or unaccepted, and only
# `plan_review_checkpoint` — which a human drives — can clear a blocking pass. So an agent looping
# "run the next pass" cannot talk its way past the two questions the author alone answers.


@mcp_server.tool(
    name="plan_run_pass",
    description=(
        "PlanForge v2: run ONE compiler pass. The seven passes run in dependency order — "
        "motifs, cast, world, beats, character_arcs, scenes, self_heal. A pass REFUSES (409, with "
        "its blockers named) while an upstream is stale or not yet accepted; `cast` and `beats` are "
        "BLOCKING checkpoints that a human must accept via plan_review_checkpoint before anything "
        "downstream may run. Re-running a pass automatically stales everything below it — no "
        "invalidation call is needed, ever. Compile the run first (the passes read its package). "
        "EDIT required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["run pass", "run compiler pass", "plan cast", "plan the scenes", "next pass"],
        # A pass is a full LLM call. `paid` governs MONEY (orthogonal to `tier`, which governs
        # mutation) — a spender that does not declare it looks free to every consumer that reads the
        # catalog to decide whether a call needs the user's say-so.
        async_job=True, paid=True, tool_name="plan_run_pass",
    ),
)
async def plan_run_pass(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    pass_id: Annotated[PlanPassId, "Which pass to run."],
    model_ref: Annotated[
        str | None, "optional user_model id — omit to use the author's default planner model.",
    ] = None,
    params: Annotated[
        dict | None,
        "Optional per-pass knobs (k_ceiling, max_select…). Fingerprinted WITH the pass: changing "
        "one stales exactly that pass and everything downstream.",
    ] = None,
    # ⚠ THERE IS NO `force` HERE, AND THERE MUST NOT BE.
    #
    # The service and the HTTP route both take `force` — a human, at the GUI, may override the PF-5
    # gate on their own book. The AGENT may not, and the first version of this tool exposed it.
    #
    # That single argument defeated the one guarantee this design makes. The description above tells
    # the model "`cast` and `beats` are BLOCKING checkpoints that a human must accept" — and then
    # handed it the key. An agent that hits a 409 listing its blockers does not stop; being helpful
    # is what it is for, and retrying with `force=true` is the obvious next move. PF-6 exists so the
    # author decides who the characters ARE and what SHAPE the story takes; a bypass the model can
    # reach for on its own is not a checkpoint, it is a speed bump.
    #
    # So the gate is enforced by ABSENCE, not by a prompt asking the model to behave.
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        return await _plan_svc().run_pass(
            tc.user_id, bid, UUID(run_id), pass_id,
            model_ref=_opt_uuid(model_ref), params=params or {}, force=False,
        )
    except UpstreamStale as exc:
        # The gate doing its job. The agent gets the BLOCKERS, not a bare failure — so its next move
        # is "accept the cast" rather than a blind retry that will refuse identically forever.
        return {
            "success": False, "error": "upstream not ready",
            "pass_id": exc.pass_id, "blockers": exc.blockers, "detail": str(exc),
        }
    except ValueError as exc:
        return {"success": False, "error": "cannot run pass", "detail": str(exc)[:300]}


@mcp_server.tool(
    name="plan_pass_status",
    description=(
        "PlanForge v2: the run's pass ledger — per pass: status, decision, whether it is FRESH, and "
        "the artifact it produced; plus `pass_cursor` (how far the compiler can proceed unattended) "
        "and `blocked_at` (the pass a human must accept next). Freshness is DERIVED on read, never "
        "stored, so it is never stale about staleness. Read-only. VIEW required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["pass status", "plan status", "how far is the plan", "what is blocking the plan"],
        tool_name="plan_pass_status",
    ),
)
async def plan_pass_status(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)
    out = await _plan_svc().pass_status(tc.user_id, bid, UUID(run_id))
    if out is None:
        raise uniform_not_accessible()
    return out


@mcp_server.tool(
    name="plan_link",
    description=(
        "PlanForge v2: (re-)link a compiled plan into the book's spec tree — arcs to structure_node, "
        "chapters and scenes to outline_node. Idempotent: a re-link UPDATES the nodes it minted "
        "before, never duplicates them, and it NEVER overwrites a node a human has edited since "
        "(those come back as `preserved_user_edit`). Runs automatically at compile; this tool is for "
        "re-linking after an edit. EDIT required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["link plan", "relink plan", "materialize plan", "push plan to the outline"],
        tool_name="plan_link",
    ),
)
async def plan_link(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    target: Annotated[
        Literal["skeleton", "scene_plan"],
        "'skeleton' = arcs + chapters (from the compiled package). 'scene_plan' = the scenes "
        "beneath them (from pass 6/7's artifact).",
    ] = "skeleton",
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        return await _plan_svc().relink(tc.user_id, bid, UUID(run_id), target=target)
    except LookupError:
        raise uniform_not_accessible()
    except ValueError as exc:
        return {"success": False, "error": "cannot link", "detail": str(exc)[:300]}


# ══════════════════════════════════════════════════════════════════════════════
# 28 AN-2/AN-3/AN-4 — THE AGENT'S THREE READ SURFACES.
#
# The gap layer 28 AN-1 enumerates, and nothing more: an `ls -R`, a find-references, and a problems
# panel. All three are Tier-R and all three COMPOSE — they call the code that already owns each
# number rather than deriving it again (26 IX-14's consumer note is the law: one computation, four
# consumers).
#
# They exist because the agent was stitching 3-6 calls across three services to answer "what is this
# book and what is wrong with it", and a weak model simply did not try. One cheap orientation read
# is the highest-leverage anti-thrash lever there is — and the 146K-token `composition_list_outline`
# incident is what happens when orientation and CONTENT share one tool, so these return counts and
# one-liners, never prose. Drill-down stays with the per-layer list tools.


@mcp_server.tool(
    name="composition_package_tree",
    description=(
        "The book at a glance — the agent's `ls -R`. ONE cheap read that replaces the 3-6 call "
        "stitch across composition, book-service and glossary: the spec tree (arcs, one line each), "
        "the manuscript spine (chapter counts), planning-run state, index/conformance freshness, and "
        "the planned-vs-written coverage gap. Summary-shaped and hard-capped — it is ORIENTATION, "
        "not content. To read an arc's actual nodes use composition_list_outline / "
        "composition_arc_list; for the plan's passes use plan_pass_status. A block that could not be "
        "computed is ABSENT with a warning, never a zero. VIEW required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["package tree", "book overview", "what is in this book", "book structure",
                  "ls", "orient me", "show me the book", "book at a glance"],
        tool_name="composition_package_tree",
    ),
)
async def composition_package_tree(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
) -> dict:
    from app.services.agent_native import Block, arc_line, cap_arcs

    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)

    pool = get_pool()
    # Canonical-Work scoping (PM-3/PM-4, 25 OQ-2) — a DERIVATIVE's rows never merge into the
    # source's tree. `resolve_scope` also tolerates a book whose Work is still PENDING: the spec
    # tree is BOOK-keyed, so it answers regardless, and only the project-keyed blocks go absent.
    work, pid = await resolve_scope(WorksRepo(pool), bid)

    out: dict[str, Any] = {"book_id": str(bid)}
    warnings: list[str] = []
    if work is not None:
        out["work"] = {"project_id": str(pid), "status": work.status}
    else:
        warnings.append("this book has no composition work yet — nobody has planned it")

    # ── spec/ — the arc tree, one line per arc ────────────────────────────────────────────
    try:
        arcs = await StructureRepo(pool).list_tree(bid)
        shown, capped = cap_arcs(arcs)
        spec = Block({
            "arc_count": len(arcs),
            "arcs": [arc_line(a) for a in shown],
            "arcs_capped": capped,
        })
    except Exception:  # noqa: BLE001 — one block degrades; the tree still orients
        logger.warning("package_tree: spec block failed", exc_info=True)
        spec = Block.failed("the spec tree could not be read")
    spec.into(out, "spec", warnings)

    # ── manuscript/ — the chapter spine, from book-service (the pack.py precedent) ─────────
    try:
        from app.clients.book_client import BookClientError, get_book_client

        chapters = await get_book_client().list_chapters(
            bid, mint_service_bearer(tc.user_id, settings.jwt_secret),
            limit=100_000, raise_on_404=True,
        )
        manuscript = Block({"chapter_count": len(chapters)})
    except Exception as exc:  # noqa: BLE001
        # ABSENT, not zero. "0 chapters" and "book-service is unreachable" lead an agent to
        # OPPOSITE actions, and only one of them is true.
        logger.warning("package_tree: manuscript block failed: %s", exc)
        manuscript = Block.failed(
            "the manuscript spine is unavailable (book-service unreachable) — "
            "chapter counts and the coverage gap are OMITTED, not zero",
        )
    manuscript.into(out, "manuscript", warnings)

    # ── .index/ — COMPOSES 26 IX-14's ONE staleness computation, never a re-derivation ─────
    try:
        from app.clients.book_client import get_book_client
        from app.engine.arc_conformance_orchestrate import compute_conformance_status

        status = await compute_conformance_status(
            pool=pool, book_client=get_book_client(), book_id=bid,
        )
        index = Block({
            "stale_chapter_count": status["index"]["stale_chapter_count"],
            "arcs_dirty": sum(1 for a in status["arcs"] if a.get("dirty")),
            "arcs_never_run": sum(
                1 for a in status["arcs"] if "never_run" in (a.get("dirty_reasons") or [])
            ),
        })
    except Exception:  # noqa: BLE001
        logger.warning("package_tree: index block failed", exc_info=True)
        index = Block.failed("index/conformance freshness could not be computed")
    index.into(out, "index", warnings)

    # ── coverage — the SAME diff 24 H1.3 renders in the PH21 tray (one implementation) ─────
    if "manuscript" in out:
        try:
            from app.clients.book_client import get_book_client
            from app.services.coverage import compute_coverage

            cov = await compute_coverage(
                bid, mint_service_bearer(tc.user_id, settings.jwt_secret),
                book=get_book_client(), outline=OutlineRepo(pool),
            )
            if cov.degraded:
                warnings.append(cov.warning or "the coverage diff degraded")
            else:
                out["coverage"] = {
                    "unplanned_chapter_count": cov.unplanned_count,
                    "unplanned_capped": cov.unplanned_capped,
                    "spine_truncated": cov.spine_truncated,
                }
        except Exception:  # noqa: BLE001
            logger.warning("package_tree: coverage block failed", exc_info=True)
            warnings.append("the planned-vs-written coverage diff could not be computed")

    # ── .runs/ — the planning runs ────────────────────────────────────────────────────────
    try:
        from app.db.repositories.plan_runs import PlanRunsRepo

        # `list_for_book` returns (rows, next_cursor) — a TUPLE. Unpacking it as a list gave
        # `'list' object has no attribute 'id'`, which the block caught and turned into an honest
        # warning rather than a fake empty `runs` — the degrade posture doing its job while I had
        # the shape wrong.
        rows, _cursor = await PlanRunsRepo(pool).list_for_book(bid, limit=5)
        # The `.runs/` block is VIEW-scoped, NOT owner-scoped — and getting here took two wrong turns
        # worth recording.
        #
        # AN-2's text says the `.runs/` tables are owner-keyed and a non-owner must get the block
        # "absent + a warning… until 25 OQ-3's VIEW resolution lands". So at C-R I owner-filtered it.
        # That was WRONG: OQ-3 HAS landed — 00B §1.4 records it shipped, in the same breath as "also
        # unblocks 28-AN-2's `runs` block", and OQ-3's decision is *default VIEW*. `list_for_book`
        # has carried no owner predicate ever since.
        #
        # So the sentence I "fixed" against was written BEFORE the thing it was waiting for. Filtering
        # here would re-narrow a scope the spec deliberately widened, and hide a collaborator's
        # legitimate view of the book's own planning history. The E0 VIEW gate above IS the gate.
        #
        # (The lesson is DR-16's, and I walked into it twice: a doc sentence is a claim about the
        # world at the time it was written. Check the world.)
        out["runs"] = {
            "recent": [
                {"id": str(r.id), "status": r.status, "mode": r.mode}
                for r in (rows or [])
            ],
        }
    except Exception:  # noqa: BLE001
        logger.warning("package_tree: runs block failed", exc_info=True)
        warnings.append("the planning-runs block could not be read")

    if warnings:
        out["warnings"] = warnings
    return out


@mcp_server.tool(
    name="composition_find_references",
    description=(
        "Find-references for an entity, across the SPEC layer: which outline nodes have it as POV or "
        "present, which scenes, which arc rosters bind it, which motif applications and canon rules "
        "and narrative threads name it. Returns EXACT counts per source plus a capped sample of rows. "
        "Composition-scope: for the PROSE side also call glossary_list_chapter_links / "
        "glossary_get_entity_evidence, and for the GRAPH side kg_entity_edge_timeline — this tool "
        "does not federate to them. VIEW required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["find references", "where is this character used", "who uses this entity",
                  "backlinks", "usages", "where does X appear"],
        tool_name="composition_find_references",
    ),
)
async def composition_find_references(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    entity_id: Annotated[str, "The glossary entity (UUID)."],
    sources: Annotated[
        list[ReferenceSource] | None,
        "Which sources to search. Omit for all eight.",
    ] = None,
    limit: Annotated[int, "Max rows per source (counts stay exact)."] = 20,
) -> dict:
    from app.services.agent_native import REFERENCE_SOURCES

    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)

    # No Work resolution here: all eight sources are BOOK-scoped, and the E0 gate above is the
    # book gate. Resolving a project we would never use was how a book_id ended up in a project slot.
    pool = get_pool()
    eid = UUID(entity_id)
    want = tuple(sources) if sources else REFERENCE_SOURCES
    cap = max(1, min(int(limit or 20), 100))

    repo = EntityReferencesRepo(pool)
    out_sources: dict[str, Any] = {}
    for src in want:
        try:
            count, refs = await repo.find(src, book_id=bid, entity_id=eid, limit=cap)
        except Exception:  # noqa: BLE001 — one source degrades; the rest still answer
            logger.warning("find_references: source %s failed", src, exc_info=True)
            out_sources[src] = {"error": "this source could not be read"}
            continue
        out_sources[src] = {
            # EXACT — the agent reasons about the number, and only samples the rows.
            "count": count,
            "refs": refs,
            "has_more": count > len(refs),
        }
    return {
        "book_id": str(bid),
        "entity_id": str(eid),
        "sources": out_sources,
        "_meta": {
            "note": (
                "Composition scope only. The prose side is glossary_list_chapter_links + "
                "glossary_get_entity_evidence; the graph side is kg_entity_edge_timeline."
            ),
        },
    }


@mcp_server.tool(
    name="composition_diagnostics",
    description=(
        "The problems panel: everything wrong with this book, ranked error → warn → info. Canon "
        "contradictions, conformance that is dirty or never run, index staleness, chapters written "
        "with no plan, and open thread debt. READ-ONLY and cheap — it never calls an LLM and never "
        "runs conformance. To refresh a dirty arc, call composition_conformance_run (which spends). "
        "Counts are exact; rows are capped. VIEW required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["diagnostics", "problems", "what is wrong", "issues", "what needs fixing",
                  "problems panel", "health check"],
        tool_name="composition_diagnostics",
    ),
)
async def composition_diagnostics(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    limit: Annotated[int, "Max item rows (counts stay exact)."] = 25,
) -> dict:
    from app.services.agent_native import SEVERITY, Diagnostic, Diagnostics

    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)

    pool = get_pool()
    _work, pid = await resolve_scope(WorksRepo(pool), bid)

    # Clamp ONCE. The row slices below used the RAW arg while the ranked cap clamped it — a
    # negative `limit` would have sliced from the end.
    cap = max(1, min(int(limit or 25), 100))

    diag = Diagnostics()
    if pid is None:
        # Absent, not zero. Without a project we cannot read canon issues, thread debt or motif
        # applications — and "no problems found" over sources we never queried is the single most
        # dangerous thing a problems panel can say.
        diag.warnings.append(
            "this book has no composition work — canon issues, thread debt and motif "
            "applications were NOT checked (absent, not zero)",
        )

    # (1) conformance + index staleness — COMPOSES IX-14's one computation
    try:
        from app.clients.book_client import get_book_client
        from app.engine.arc_conformance_orchestrate import compute_conformance_status

        status = await compute_conformance_status(
            pool=pool, book_client=get_book_client(), book_id=bid,
        )
        for arc in status["arcs"]:
            reasons = arc.get("dirty_reasons") or []
            if "never_run" in reasons:
                kind = "conformance_never_run"
            elif arc.get("dirty"):
                kind = "conformance_dirty"
            else:
                continue
            diag.add(Diagnostic(
                kind=kind, severity=SEVERITY[kind],
                title=f'arc "{arc.get("title") or "(untitled)"}" — {", ".join(reasons) or "dirty"}',
                detail="run composition_conformance_run to refresh it",
                node_ref={"kind": "arc", "id": arc["structure_node_id"],
                          "title": arc.get("title")},
                at=arc.get("computed_at"),
            ))
        stale = status["index"]["stale_chapter_count"]
        if stale:
            diag.add(Diagnostic(
                kind="index_stale", severity=SEVERITY["index_stale"],
                title=f"{stale} chapter(s) have a stale prose index",
                detail="the sweeper heals these; re-indexing refreshes the canon windows",
            ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: conformance source failed", exc_info=True)
        diag.warnings.append("conformance + index staleness could not be computed")

    # (2) canon contradictions — F-A5's repo finally gets an agent-reachable caller
    try:
        if pid is None:
            raise LookupError("no project")
        for issue in await OutlineRepo(pool).canon_issues(pid):
            violations = issue.get("violations") or []
            diag.add(Diagnostic(
                kind="canon_contradiction", severity=SEVERITY["canon_contradiction"],
                title=f'{len(violations)} canon violation(s) in "{issue.get("scene_title") or "a scene"}"',
                detail="; ".join(
                    str(v.get("detail") or v.get("rule") or v)[:120] for v in violations[:2]
                ),
                node_ref={"kind": "scene", "id": issue["scene_id"],
                          "title": issue.get("scene_title")},
                at=issue.get("created_at"),
            ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: canon source failed", exc_info=True)
        diag.warnings.append("canon contradictions could not be read")

    # (2b) BROKEN CANON RULES — the critic lane (24 PH18). Source (2) above is the ENTITY lane and
    # carries no rule id, so without this the agent could not see a violated author-declared rule at
    # ALL, while the human's quality-canon panel now can. A problems panel that silently omits a
    # whole class of problem is worse than no panel: the reader believes the count.
    try:
        if pid is None:
            raise LookupError("no project")
        rv = await OutlineRepo(pool).rule_violations(pid)
        for item in rv["items"]:
            rule = item.get("rule_text") or "a rule that no longer exists"
            diag.add(Diagnostic(
                kind="broken_canon_rule", severity=SEVERITY["broken_canon_rule"],
                title=f'canon rule broken: "{rule[:80]}"',
                detail=(item.get("why") or item.get("span") or "")[:120],
                node_ref={"kind": "scene", "id": item["scene_id"],
                          "title": item.get("scene_title")},
                at=item.get("created_at"),
            ))
        if rv["capped"]:
            # OUT-5: never let a truncation read as completeness.
            diag.warnings.append(
                f"showing {len(rv['items'])} of {rv['count']} broken canon rules"
            )
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: rule-violation source failed", exc_info=True)
        diag.warnings.append("broken canon rules could not be read")

    # (3) open thread debt (BA15)
    try:
        if pid is None:
            raise LookupError("no project")
        threads = await NarrativeThreadRepo(pool).list_open(pid, limit=100)
        if threads:
            diag.add(Diagnostic(
                kind="open_thread_debt", severity=SEVERITY["open_thread_debt"],
                title=f"{len(threads)} open promise(s) still unpaid",
                detail="; ".join((t.summary or "")[:60] for t in threads[:3]),
            ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: thread source failed", exc_info=True)
        diag.warnings.append("open thread debt could not be read")

    # (4) prose-deleted spec nodes — 26 IX-13. The INVERSE of the coverage diff: a spec node whose
    # chapter has been deleted. ERROR severity, and it was MISSING from the first cut of this tool —
    # `SEVERITY` declared the kind and nothing ever emitted it, so the panel quietly never checked
    # the highest-severity class it has. A problems panel with a silent hole is worse than no panel:
    # the agent reads "1 problem" and believes it.
    try:
        from app.clients.book_client import get_book_client
        from app.services.coverage import compute_prose_deleted

        pd = await compute_prose_deleted(
            bid, mint_service_bearer(tc.user_id, settings.jwt_secret),
            book=get_book_client(), outline=OutlineRepo(pool),
        )
        if pd.degraded:
            diag.warnings.append(pd.warning)
        else:
            for n in pd.nodes[:cap]:
                diag.add(Diagnostic(
                    kind="prose_deleted_spec_node", severity=SEVERITY["prose_deleted_spec_node"],
                    title=f'"{n.get("title") or "(untitled)"}" points at a chapter that no longer exists',
                    detail=(
                        "the spec SURVIVES a prose delete (IX-13) — re-link it to a chapter, or "
                        "archive it. It is never auto-archived."
                    ),
                    node_ref={"kind": n.get("kind") or "chapter", "id": n["id"],
                              "title": n.get("title")},
                ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: prose-deleted source failed", exc_info=True)
        diag.warnings.append("prose-deleted spec nodes could not be checked")

    # (5) unplanned chapters — the SAME coverage diff 24 H1.3 renders (one implementation)
    try:
        from app.clients.book_client import get_book_client
        from app.services.coverage import compute_coverage

        cov = await compute_coverage(
            bid, mint_service_bearer(tc.user_id, settings.jwt_secret),
            book=get_book_client(), outline=OutlineRepo(pool),
        )
        if cov.degraded:
            # Absent, not zero. "0 unplanned chapters" is a claim we cannot make.
            diag.warnings.append(
                cov.warning or "the planned-vs-written diff degraded — unplanned chapters UNKNOWN",
            )
        else:
            for ch in cov.unplanned[:cap]:
                diag.add(Diagnostic(
                    kind="unplanned_chapter", severity=SEVERITY["unplanned_chapter"],
                    title=f'chapter "{ch.get("title") or "(untitled)"}" is written but not planned',
                    node_ref={"kind": "chapter", "id": str(ch.get("chapter_id") or ""),
                              "title": ch.get("title")},
                ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: coverage source failed", exc_info=True)
        diag.warnings.append("the planned-vs-written diff could not be computed")

    return {"book_id": str(bid), **diag.ranked(cap=cap)}


# ══════════════════════════════════════════════════════════════════════════════
# 23 B1/B2/B3 — STRUCTURE-NODE (the durable SPEC layer) MCP SURFACE.
#
# `structure_node` is the saga→arc→sub-arc spec tree (spec 23, BA1..BA15) — the
# first-class, durable, editable object that STEERS generation (pack.py reads it,
# BA12). It is PER-BOOK (BA8): `book_id` is the scope, gated at the E0 book grant
# BEFORE the repo (never a body-supplied book_id for a by-id MUTATION — a node's
# own book_id IS its scope, resolved from the row via `_arc_or_deny`, the Stage-1
# authoring-run fence pattern). The StructureRepo depth/cycle/cross-book invariant
# lives in the DB trigger `structure_node_depth_guard`; the repo surfaces its
# check_violation as StructureConflictError, which these tools map to a clean tool
# refusal (never a raised 5xx). Namespaces (BA10): composition_arc_* = the SPEC;
# composition_arc_template_* = the library; composition_character_arc_* = the
# entity lens (elsewhere).
# ══════════════════════════════════════════════════════════════════════════════


_ArcStatus = Literal["empty", "outline", "drafting", "done"]


async def _arc_or_deny(
    structures: StructureRepo, tc: ToolContext, node_id: UUID, level: GrantLevel,
):
    """By-id arc access: resolve the structure_node's book from the ROW ITSELF
    (bare-id read — the E0 grant is what authorizes, not row ownership) and gate
    the caller's grant on ITS `book_id` at the operation tier. Mirrors the outline
    `_gate_node` / authoring-run fence shape (`worker-loaded-id-needs-parent-
    scoping`): the gate can never check a different book than the row mutated. A
    missing node raises the SAME H13 uniform deny as a denied grant (no existence
    oracle). Returns the resolved StructureNode."""
    node = await structures.get(node_id)
    if node is None:
        raise uniform_not_accessible()
    await _gate(tc, node.book_id, level)
    return node


def _arc_conflict(exc: StructureConflictError) -> dict[str, Any]:
    """Surface a structure_node depth/cycle/cross-book trigger violation
    (`structure_node_depth_guard`) as a clean tool refusal — never a raised 5xx. A
    saga-with-a-parent, nesting past saga→arc→sub-arc (depth>2), a cycle, or a
    cross-book parent all land here (BA9)."""
    return {
        "success": False,
        "error": (
            "structure constraint violated — a saga cannot have a parent, nesting "
            "is capped at saga→arc→sub-arc (depth 2), no cycles, and a parent must "
            "be in the same book"
        ),
        "detail": str(exc)[:300],
    }


# ── Tier R — arc reads ────────────────────────────────────────────────────────


@mcp_server.tool(
    name="composition_arc_list",
    description=(
        "List a book's SPEC tree in ONE call — the saga→arc→sub-arc structure that "
        "steers generation (parallel plot tracks, cast roster, pacing, provenance). "
        "Returns a flat, deterministically-ordered node list (depth, then rank) the "
        "client assembles into the tree; this is the Chapter Browser's arc group "
        "headers without the per-arc N+1 fetch. VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["list arcs", "arc tree", "story structure", "sagas", "book architecture",
                  "spec tree", "arc grouping"],
        tool_name="composition_arc_list",
    ),
)
async def composition_arc_list(
    ctx: MCPContext,
    book_id: Annotated[str, "The book whose spec tree to list (you need VIEW on it)."],
    include_archived: Annotated[bool, "Include soft-archived arcs."] = False,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)
    structures = StructureRepo(get_pool())
    nodes = await structures.list_tree(bid, include_archived=include_archived)
    return {"nodes": [n.model_dump(mode="json") for n in nodes], "book_id": book_id}


@mcp_server.tool(
    name="composition_arc_get",
    description=(
        "Read ONE arc/saga by id, ENRICHED with everything the arc inspector needs: "
        "the node's own fields + `version` (the OCC token for composition_arc_update), "
        "the CASCADE-RESOLVED `tracks`/`roster`/`roster_bindings` (root saga → this "
        "arc, leaf-shadowed by key), the DERIVED `span` (min/max story_order + "
        "chapter_count + warn-only is_contiguous over member chapters), and the "
        "`open_promises` rollup (narrative threads opened in this arc's chapter "
        "subtree, still unpaid). VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["get arc", "read arc", "arc detail", "arc version", "resolved tracks",
                  "arc span", "saga detail"],
        tool_name="composition_arc_get",
    ),
)
async def composition_arc_get(
    ctx: MCPContext,
    node_id: Annotated[str, "The arc/saga (structure_node) id."],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, UUID(node_id), GrantLevel.VIEW)
    threads_repo = NarrativeThreadRepo(get_pool())
    out = node.model_dump(mode="json")
    # BA7/BA6/BA15 — the derived reads (the whole reason structure_node exists: it
    # is READ to make decisions, not write-only). All go through StructureRepo's
    # single cascade/derivation implementation; the tools never re-derive it.
    out["resolved"] = {
        "tracks": await structures.resolve_tracks(node.id),
        "roster": await structures.resolve_roster(node.id),
        "roster_bindings": await structures.resolve_roster_bindings(node.id),
    }
    out["span"] = await structures.span(node.id)
    out["open_promises"] = [
        t.model_dump(mode="json")
        for t in await structures.open_promises(node.id, narrative_threads_repo=threads_repo)
    ]
    return out


# ── Tier A — arc auto-write + Undo ────────────────────────────────────────────


class _ArcCreateArgs(ForbidExtra):
    book_id: str
    # BA1: two kinds + nesting (a sub-arc is an arc whose parent is an arc) — no
    # third enum. A closed Literal makes `kind:"Saga"` a clean 422, not a DB CHECK 5xx.
    kind: Literal["saga", "arc"] = "arc"
    # A sub-arc's parent (an arc). Omit for a root saga / top-level arc. The DB
    # trigger rejects a cross-book parent, a cycle, and depth>2.
    parent_arc_id: str | None = None
    title: str = ""
    summary: str = ""
    goal: str = ""
    status: _ArcStatus = "outline"
    # BA3: the SPEC owns tracks/roster/roster_bindings. NO `pacing` arg (BPS-3): an
    # arc's curve IS its member scenes' tension — set scene tension, never a stored
    # second copy.
    tracks: list[dict[str, Any]] | None = None
    roster: list[dict[str, Any]] | None = None
    roster_bindings: dict[str, Any] | None = None
    # BA13: provenance is nullable — an arc authored from conversation has none.
    arc_template_id: str | None = None
    template_version: int | None = None


@mcp_server.tool(
    name="composition_arc_create",
    description=(
        "Create a saga or arc in a book's SPEC tree (the durable structure that "
        "steers generation). `kind='saga'` is a root (no parent); `kind='arc'` is an "
        "arc or — with `parent_arc_id` — a sub-arc. Owns `tracks` (parallel plot "
        "lines), `roster` (cast slots), and `roster_bindings` (slot→glossary entity). "
        "There is NO pacing arg — an arc's pacing curve is derived from its member "
        "scenes' tension. EDIT on the book required (auto-applied; Undo archives it)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["create arc", "new saga", "add arc", "author an arc", "start a saga",
                  "add sub-arc", "create story arc"],
        tool_name="composition_arc_create",
    ),
)
async def composition_arc_create(ctx: MCPContext, args: _ArcCreateArgs) -> dict:
    tc = _ctx(ctx)
    bid = UUID(args.book_id)
    # Creating INTO a book is a package WRITE → EDIT on the book (the supplied
    # book_id IS the scope; a cross-book parent_arc_id is caught by the trigger).
    await _gate(tc, bid, GrantLevel.EDIT)
    structures = StructureRepo(get_pool())
    try:
        node = await structures.create_node(
            bid,
            created_by=tc.user_id,
            kind=args.kind,
            title=args.title, summary=args.summary, goal=args.goal, status=args.status,
            parent_id=UUID(args.parent_arc_id) if args.parent_arc_id else None,
            tracks=args.tracks, roster=args.roster, roster_bindings=args.roster_bindings,
            arc_template_id=UUID(args.arc_template_id) if args.arc_template_id else None,
            template_version=args.template_version,
        )
    except StructureConflictError as exc:
        return _arc_conflict(exc)
    out = node.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo("composition_arc_delete", node_id=str(node.id))}
    return out


class _ArcUpdateArgs(ForbidExtra):
    node_id: str
    expected_version: int
    title: str | None = None
    summary: str | None = None
    goal: str | None = None
    status: _ArcStatus | None = None
    tracks: list[dict[str, Any]] | None = None
    roster: list[dict[str, Any]] | None = None
    roster_bindings: dict[str, Any] | None = None
    # re-pin (or set) provenance; None leaves it unchanged (kind/parent/rank are
    # NOT patchable here — reparent+reorder go through composition_arc_move).
    arc_template_id: str | None = None
    template_version: int | None = None


@mcp_server.tool(
    name="composition_arc_update",
    description=(
        "Edit an arc/saga's content — title, summary, goal, status, tracks, roster, "
        "roster_bindings, or provenance. Requires `expected_version` (optimistic "
        "concurrency — a stale version is rejected, no blind clobber; read it via "
        "composition_arc_get). To reparent or reorder use composition_arc_move; to "
        "attach chapters use composition_arc_assign_chapters. EDIT required "
        "(auto-applied; Undo restores the prior values)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit arc", "update arc", "rename saga", "set arc status",
                  "edit tracks", "update roster"],
        tool_name="composition_arc_update",
    ),
)
async def composition_arc_update(ctx: MCPContext, args: _ArcUpdateArgs) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    prior = await _arc_or_deny(structures, tc, UUID(args.node_id), GrantLevel.EDIT)
    patch: dict[str, Any] = {}
    for field, value in {
        "title": args.title, "summary": args.summary, "goal": args.goal,
        "status": args.status, "tracks": args.tracks, "roster": args.roster,
        "roster_bindings": args.roster_bindings, "template_version": args.template_version,
    }.items():
        if value is not None:
            patch[field] = value
    if args.arc_template_id is not None:
        patch["arc_template_id"] = UUID(args.arc_template_id)
    try:
        updated = await structures.update(
            prior.id, patch, expected_version=args.expected_version,
        )
    except VersionMismatchError as exc:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "stale expected_version — refetch and retry",
            "current_version": exc.current.version,
        }
    except StructureConflictError as exc:
        return _arc_conflict(exc)
    if updated is None:
        raise uniform_not_accessible()
    out = updated.model_dump(mode="json")
    # Precise Undo: replay the prior JSON-native values (model_dump normalizes
    # UUID→str) for exactly the fields we changed, at the new version.
    prior_dump = prior.model_dump(mode="json")
    undo_fields = {f: prior_dump[f] for f in patch if f in prior_dump}
    out["_meta"] = {"undo_hint": _undo(
        "composition_arc_update", node_id=args.node_id,
        expected_version=updated.version, **undo_fields,
    )}
    return out


@mcp_server.tool(
    name="composition_arc_delete",
    description=(
        "Soft-archive an arc/saga AND its sub-arc subtree (reversible via "
        "composition_arc_restore). Member chapters are NOT deleted — their "
        "structure_node_id simply points at an archived node. EDIT required "
        "(auto-applied; Undo restores it)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["delete arc", "archive saga", "remove arc", "delete story arc"],
        tool_name="composition_arc_delete",
    ),
)
async def composition_arc_delete(
    ctx: MCPContext,
    node_id: Annotated[str, "The arc/saga to archive."],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, UUID(node_id), GrantLevel.EDIT)
    await structures.archive(node.id)
    return {
        "node_id": str(node.id), "archived": True,
        "_meta": {"undo_hint": _undo("composition_arc_restore", node_id=str(node.id))},
    }


@mcp_server.tool(
    name="composition_arc_restore",
    description=(
        "Un-archive a previously deleted arc/saga (the inverse of "
        "composition_arc_delete) — restores its archived subtree AND reconnects its "
        "archived ancestor chain to a visible root. EDIT required (auto-applied; "
        "Undo re-archives it)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["restore arc", "unarchive saga", "undelete arc"],
        tool_name="composition_arc_restore",
    ),
)
async def composition_arc_restore(
    ctx: MCPContext,
    node_id: Annotated[str, "The arc/saga to restore."],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    # get() returns archived rows too, so _arc_or_deny resolves + gates the archived
    # node before the un-archive.
    node = await _arc_or_deny(structures, tc, UUID(node_id), GrantLevel.EDIT)
    await structures.restore(node.id)
    return {
        "node_id": str(node.id), "archived": False,
        "_meta": {"undo_hint": _undo("composition_arc_delete", node_id=str(node.id))},
    }


class _ArcMoveArgs(ForbidExtra):
    node_id: str
    # None = make it a root (a saga, or a top-level arc). The DB trigger rejects a
    # depth>2 result (the moved node OR any descendant), a cycle, a cross-book
    # parent, and a saga given a parent — the whole move rolls back on any of them.
    new_parent_arc_id: str | None = None
    # place directly AFTER this sibling (None = first under the new parent).
    after_id: str | None = None


@mcp_server.tool(
    name="composition_arc_move",
    description=(
        "Reparent AND reorder an arc in one atomic move — place `node_id` under "
        "`new_parent_arc_id` (None = a root) directly after `after_id` (None = "
        "first). Recomputes the whole moved subtree's depth; a move that would nest "
        "past saga→arc→sub-arc, form a cycle, cross books, or give a saga a parent "
        "is rejected cleanly and rolled back. EDIT required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["move arc", "reparent arc", "reorder arc", "nest arc", "restructure book"],
        tool_name="composition_arc_move",
    ),
)
async def composition_arc_move(ctx: MCPContext, args: _ArcMoveArgs) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, UUID(args.node_id), GrantLevel.EDIT)
    try:
        moved = await structures.move(
            node.id,
            new_parent_id=UUID(args.new_parent_arc_id) if args.new_parent_arc_id else None,
            after_id=UUID(args.after_id) if args.after_id else None,
        )
    except StructureConflictError as exc:
        return _arc_conflict(exc)
    if moved is None:
        raise uniform_not_accessible()
    out = moved.model_dump(mode="json")
    # A reparent+reorder has no single precise inverse token (the prior rank was a
    # fractional string between siblings that may have changed); honest None.
    out["_meta"] = {"undo_hint": None}
    return out


class _ArcAssignChaptersArgs(ForbidExtra):
    book_id: str
    structure_node_id: str
    chapter_node_ids: list[str]


@mcp_server.tool(
    name="composition_arc_assign_chapters",
    description=(
        "Attach CHAPTER-kind outline nodes to an arc (sets their structure_node_id) "
        "— the membership that makes an arc's derived span and open-promise rollup "
        "real. Book-scoped both sides: only chapters in `book_id` are touched, and "
        "only if `structure_node_id` is itself in that book. Returns the count "
        "assigned. EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["assign chapters", "attach chapters to arc", "arc membership",
                  "add chapters to arc", "group chapters under arc"],
        tool_name="composition_arc_assign_chapters",
    ),
)
async def composition_arc_assign_chapters(
    ctx: MCPContext, args: _ArcAssignChaptersArgs,
) -> dict:
    tc = _ctx(ctx)
    bid = UUID(args.book_id)
    await _gate(tc, bid, GrantLevel.EDIT)
    structures = StructureRepo(get_pool())
    count = await structures.assign_chapters(
        bid, UUID(args.structure_node_id), [UUID(c) for c in args.chapter_node_ids],
    )
    return {
        "assigned": count, "structure_node_id": args.structure_node_id,
        "_meta": {"undo_hint": None},
    }


# ── B2 — template ops (composition_arc_template_* CRUD stays REST-only per BA11;
# these three cross the SPEC ↔ LIBRARY seam). apply/extract persist and template_
# drift reads; all three delegate their ENGINE work to 23 A5 (arc_apply/extract)
# and A4 (template_drift split-out). Those slices build in PARALLEL with this one
# (fanout-independent-slices — one serial VERIFY reconciles): the tool SURFACE +
# the gate are wired here now; the engine seam is resolved by getattr so a
# pre-integration call returns an HONEST "pending" refusal (never a silent no-op,
# never a module-import crash of the whole MCP server). ────────────────────────


def _pending_engine(dep: str, module: str, fn: str) -> dict[str, Any]:
    """Honest refusal when an A4/A5 engine seam this tool wires isn't merged yet
    (parallel-build interim state — reconciled at the serial VERIFY). NOT a silent
    success: names the exact missing symbol so the integrator wires it."""
    return {
        "success": False,
        "error": f"arc engine not yet integrated (23 {dep}) — expected {module}.{fn}",
        "pending_dependency": dep,
    }


class _ArcApplyArgs(ForbidExtra):
    project_id: str
    arc_template_id: str
    # bind the arc roster ONCE {role_key: cast_name|entity_id}; propagated to every
    # placement. Unbound roster slots are surfaced, never silently half-bound.
    roster_bindings: dict[str, Any] = {}
    replace: bool = False
    idempotency_key: str | None = None


@mcp_server.tool(
    name="composition_arc_apply",
    description=(
        "Apply an arc TEMPLATE onto this Work's book as durable SPEC — rescale the "
        "template's placements onto the book's chapters, bind the roster once, write "
        "the arc's pacing curve into scene tension, and emit the motif_application "
        "ledger (BA3/BA5). This is the 'instantiate a library arc here' op (was POST "
        ".../arc/materialize). Deterministic (no LLM). EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["apply arc template", "instantiate arc", "materialize arc",
                  "use arc template", "apply library arc"],
        tool_name="composition_arc_apply",
    ),
)
async def composition_arc_apply(ctx: MCPContext, args: _ArcApplyArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    # IDOR: the source template must be visible to the caller (H13 on foreign/missing).
    arc_tmpl = await ArcTemplateRepo(get_pool()).get_visible(tc.user_id, UUID(args.arc_template_id))
    if arc_tmpl is None:
        raise uniform_not_accessible()
    from app.engine import arc_apply as _engine  # 23 A5 (module exists; fn pending)
    fn = getattr(_engine, "apply_arc_to_spec", None)
    if fn is None:
        return _pending_engine("A5", "app.engine.arc_apply", "apply_arc_to_spec")
    result = await fn(
        get_pool(),
        book_id=meta.book_id, project_id=pid, arc_template=arc_tmpl,
        roster_bindings=dict(args.roster_bindings),
        replace=args.replace, idempotency_key=args.idempotency_key,
        created_by=tc.user_id,
    )
    out = dict(result)
    out.setdefault("_meta", {"undo_hint": None})
    return out


class _ArcExtractTemplateArgs(ForbidExtra):
    node_id: str
    code: str
    name: str
    language: str = "en"
    # 'public' is excluded at create — publishing is the separate library flip.
    visibility: Literal["private", "unlisted"] = "private"


@mcp_server.tool(
    name="composition_arc_extract_template",
    description=(
        "Save an authored arc (a structure_node) as a reusable arc TEMPLATE in YOUR "
        "library — 'save my plan as a template' (BA13, the extract half of the "
        "apply↔extract round trip). Reads the arc's tracks/roster and its realized "
        "motif_application rows back into a template `tracks`/`layout`/`pacing`. The "
        "template is owned by you, private by default. VIEW on the arc's book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["extract arc template", "save arc as template", "template from arc",
                  "publish my plan", "make arc template"],
        tool_name="composition_arc_extract_template",
    ),
)
async def composition_arc_extract_template(
    ctx: MCPContext, args: _ArcExtractTemplateArgs,
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    # Reading the spec to extract from it → VIEW on its book; the new template is
    # owner-stamped to the caller (their own library, always writable).
    node = await _arc_or_deny(structures, tc, UUID(args.node_id), GrantLevel.VIEW)
    from app.engine import arc_apply as _engine  # 23 A5 (module exists; fn pending)
    fn = getattr(_engine, "extract_template_from_arc", None)
    if fn is None:
        return _pending_engine("A5", "app.engine.arc_apply", "extract_template_from_arc")
    try:
        result = await fn(
            get_pool(),
            arc_node=node, owner_user_id=tc.user_id,
            code=args.code, name=args.name, language=args.language,
            visibility=args.visibility,
        )
    except asyncpg.UniqueViolationError:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "an arc template with this code + language already exists in your library",
        }
    out = dict(result)
    out.setdefault("_meta", {"undo_hint": None})
    return out


@mcp_server.tool(
    name="composition_arc_template_drift",
    description=(
        "The OPTIONAL provenance question BA4 splits out: how far has an authored arc "
        "(a structure_node) drifted from the TEMPLATE it came from (its pinned "
        "arc_template_id + template_version)? Distinct from composition_conformance_run, "
        "which diffs the arc's SPEC against the PROSE. Returns 'unknown' when the arc "
        "has no provenance. VIEW on the arc's book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["arc template drift", "diff arc vs template", "provenance drift",
                  "how far from the template"],
        tool_name="composition_arc_template_drift",
    ),
)
async def composition_arc_template_drift(
    ctx: MCPContext,
    node_id: Annotated[str, "The arc (structure_node) to compare against its source template."],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, UUID(node_id), GrantLevel.VIEW)
    if node.arc_template_id is None:
        return {"available": False, "reason": "arc has no template provenance (authored directly)"}
    from app.engine import arc_conformance as _engine  # 23 A4 (module exists; fn pending)
    fn = getattr(_engine, "build_template_drift", None)
    if fn is None:
        return _pending_engine("A4", "app.engine.arc_conformance", "build_template_drift")
    return await fn(get_pool(), arc_node=node, user_id=tc.user_id)


# ── B3 — the missing outline reorder (F6): a human has full drag-reorder
# (OutlineTree), the agent could only rename. This closes the gap over the SAME
# merged OutlineRepo.reorder_node the REST /outline/nodes/{id}/reorder uses. NOTE
# (23 B3): the spec shorthand is `(node_id, parent_id, rank)`, but LexoRank is
# COMPUTED from `after_id` (a raw rank risks sibling collisions); this exposes
# `after_id`, matching reorder_node + the OutlineTree precedent. ────────────────


class _OutlineNodeMoveArgs(ForbidExtra):
    project_id: str
    node_id: str
    new_parent_id: str | None = None   # None = top level
    after_id: str | None = None        # place AFTER this sibling; None = first child
    expected_version: int | None = None


@mcp_server.tool(
    name="composition_outline_node_move",
    description=(
        "Drag-reorder + reparent an outline node (chapter/scene) — place `node_id` "
        "under `new_parent_id` (None = top level) directly after `after_id` (None = "
        "first child). Computes the fractional rank + renumbers scene story_order "
        "server-side, atomically. Pass `expected_version` for optimistic concurrency "
        "(a stale version is rejected). EDIT required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["move node", "reorder scene", "reparent chapter", "drag reorder",
                  "reorder outline node"],
        tool_name="composition_outline_node_move",
    ),
)
async def composition_outline_node_move(ctx: MCPContext, args: _OutlineNodeMoveArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = UUID(args.project_id)
    await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    outline = OutlineRepo(get_pool())
    node_id = UUID(args.node_id)
    # Project-scope the target BEFORE mutating (the gate above checked the resolved
    # Work's book, but reorder_node targets by id only) — a node_id from another
    # Work would otherwise be moved under THIS book's gate. See node_update note.
    prior = await outline.get_node(node_id)
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    try:
        moved = await outline.reorder_node(
            node_id,
            new_parent_id=UUID(args.new_parent_id) if args.new_parent_id else None,
            after_id=UUID(args.after_id) if args.after_id else None,
            expected_version=args.expected_version,
        )
    except VersionMismatchError as exc:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "stale expected_version — refetch and retry",
            "current_version": exc.current.version,
        }
    except ReferenceViolationError as exc:
        # A reparent cycle / cross-scope parent / bad after_id is a clean refusal,
        # not a not-found (the node IS the caller's; the MOVE is what's invalid).
        return {"success": False, "error": "invalid move", "detail": exc.message}
    if moved is None:
        raise uniform_not_accessible()
    out = moved.model_dump(mode="json")
    out["_meta"] = {"undo_hint": None}   # a reorder has no single precise inverse token
    return out


# ── ASGI factory ──────────────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``.

    ``FastMCP.streamable_http_app()`` returns a Starlette app whose own lifespan
    runs the StreamableHTTP session manager. Under FastAPI a *mounted* sub-app's
    lifespan is NOT auto-run, so ``main.py`` runs the session manager directly
    inside its own lifespan (``mcp_server.session_manager.run()``)."""
    return mcp_server.streamable_http_app()
