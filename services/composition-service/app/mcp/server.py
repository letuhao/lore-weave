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
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field, ValidationError, field_validator

from loreweave_mcp import (
    ForbidExtra,
    GrantResolver,
    ToolContext,
    TolerantArgs,
    apply_response_contract,
    build_tool_context,
    make_stateless_fastmcp,
    validation_directive,
    mint_confirm_token,
    require_book_owner,
    require_meta,
    require_user_scope,
    resolve_book_scope,
    resolve_project_scope,
    uniform_not_accessible,
)

from app.clients.book_client import BookClient, BookClientError, get_book_client
from app.clients.glossary_client import GlossaryClientError, get_glossary_client
from app.clients.knowledge_client import (
    KnowledgeClient,
    KnowledgeContractError,
    get_knowledge_client,
)
from app.config import settings
from app.db.models import (
    MAX_DRAFT_BEATS,
    ArcTemplateCreateArgs,
    ArcTemplatePatchArgs,
    LinkKind,
    PlanPassId,
    SceneExitState,
    SceneExitStateIn,
)
from app.services.agent_native import ReferenceSource, resolve_scope
from app.services.plan_pass_service import UpstreamStale
# D-ARC-TRACKS-ROSTER-SCHEMA — reuse the REST door's entry-key validators (one definition,
# no drift across the two doors). routers.arc does not import the MCP server, so no cycle.
from app.routers.arc import validate_track_dicts, validate_roster_dicts
from app.db.pool import get_pool
from app.db.repositories import (
    ReferenceViolationError,
    VersionMismatchError,
)
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.error_blocks import ErrorBlocksRepo
from app.db.repositories.structure_templates import (
    DuplicateStructureTemplateName,
    StructureTemplatesRepo,
    StructureTemplateVersionConflict,
)
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.motif_repo import EndpointsOwnedNotShared, MotifRepo
from app.engine.exit_state import merge_authored_exit_state
from app.engine.library_translate import (
    LANGUAGE_NAMES, MAX_ITEMS_PER_JOB, TRANSLATABLE_KINDS,
)
from app.db.repositories.motif_retrieve import MotifRetriever, node_query_text
from app.db.repositories.entity_references import EntityReferencesRepo
from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.references import ReferencesRepo, reference_embed_model
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.structure import StructureConflictError, StructureRepo
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.works import WorksRepo
from app.deps import get_authoring_run_service, get_bootstrap_service
from app.packer.pack import build_derivative_context
from app.grant_client import GrantLevel, get_grant_client
from app.mcp.service_bearer import mint_service_bearer
from app.services.authoring_run_service import ALLOWLISTABLE_TOOLS
from app.work_resolution import ensure_work, resolve_work

logger = logging.getLogger(__name__)

__all__ = ["mcp_server", "build_mcp_app"]

mcp_server = make_stateless_fastmcp("composition")

# W0 #4b — the one-line validation directive, absorbed into the kit as
# `validation_directive`. THIS SERVICE NEVER HAD IT. Measured across the corpus, raw pydantic
# dumps by owning service: composition 58 across 8 tools and 9 sessions (last 2026-07-30), kg 8,
# translation 3, jobs 1, memory 1 — and every one of those others predates the rewriter shipping
# in their service. Composition was the only producer still emitting them, complete with the
# errors.pydantic.dev URL, which is noise a model cannot act on.
#
# The three siblings each carried a byte-identical copy of this wrapper and the same comment
# saying the kit would absorb it. It did (iteration 65, which also fixed a type clause that was
# false on every call it ever rendered). Installing it here is the fourth consumer of one
# implementation rather than a fourth copy.
def _install_validation_error_rewriter(server) -> None:
    """Wrap the tool manager's dispatch so a ToolError CAUSED BY a pydantic ValidationError
    re-raises as the one-line directive. Anything else passes through untouched."""
    manager = server._tool_manager
    original = manager.call_tool

    async def call_tool(name, arguments, *args, **kwargs):
        try:
            return await original(name, arguments, *args, **kwargs)
        except ToolError as e:
            cause = e.__cause__
            if isinstance(cause, ValidationError):
                raise ToolError(validation_directive(name, cause)) from cause
            raise

    manager.call_tool = call_tool


_install_validation_error_rewriter(mcp_server)

# ext-tasks durable-gate (spec 2026-07-19-mcp-tasks-durable-gate) — makes this
# server task-capable: tasks/get + tasks/cancel handlers, the task_provide_input
# input tool, and the CreateTaskResult wrap so a gate tool emits a wire task. A
# KIND-C tool opens the gate via `gate_or_confirm(ctx, _task_store, …)` — which
# returns a durable task ONLY to a tasks-capable client, else today's confirm_token
# (so non-tasks clients are never stranded). In-memory store for the first cut
# (single-process; a persistent store bound to the confirm/consumed-token layer is
# the T3 hardening). `enable_task_results` is called AFTER all @mcp_server.tool defs
# (bottom of module) so it wraps a handler that sees every tool.
from app.mcp.pg_task_store import PgTaskStore  # noqa: E402
from loreweave_mcp.tasks_wire import (  # noqa: E402
    gate_or_confirm,
    register_task_endpoints,
)

# Defined here (ahead of the other confirm descriptors below) because the durable-gate
# store is constructed at import time and needs the derive descriptor as its resolver key.
_DERIVE_DESCRIPTOR = "composition.derive"
# PlanForge auto-bootstrap MATERIALISE — the confirm-gated apply that turns a compiled
# plan's planned chapters into REAL book chapters (executed in actions.py). Mirrors the
# REST /plan/bootstrap/{id}/apply gate so the agent can drive materialisation via MCP.
_BOOTSTRAP_APPLY_DESCRIPTOR = "composition.bootstrap_apply"


async def _resolve_derive(owner_user_id: str, payload: dict, _inputs: dict):
    """The composition.derive gate ACCEPT effect — the durable-gate resolver (registered
    by descriptor). Runs on accept, RECONSTRUCTED on any replica from {owner_user_id,
    payload} (no closure): the SAME confirm-execute path /v1/composition/actions/confirm
    runs (rebuilds DeriveBody from the signed payload, then perform_derive). Fresh clients
    are built here (pool-backed singletons), so the accept can arrive on any later request."""
    from app.routers.actions import _execute_derive  # lazy — avoid an import cycle

    # WorksRepo / get_pool / get_book_client are module-level imports (top of file).
    return await _execute_derive(payload, owner_user_id, works=WorksRepo(get_pool()), book=get_book_client())


# (The durable-gate store + its FULL resolver registry are constructed below —
# after the confirm-descriptor constants + the sibling `_resolve_*` functions are
# defined — so every migrated KIND-C tool keys the store by its descriptor.)

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
# The user-paid library translate (motif | arc_template): an LLM-spend job like mine, but
# USER-scoped — the payload names ids + kind, and a book_id appears only for the shared tier.
_LIBRARY_TRANSLATE_DESCRIPTOR = "composition.library_translate"
_ARC_IMPORT_DESCRIPTOR = "composition.arc_import"
_CONFORMANCE_RUN_DESCRIPTOR = "composition.conformance_run"
# close-21-28 P-O2a — the arc-decompiler (deterministic, $0) confirm-gated to the agent.
_DECOMPILE_DESCRIPTOR = "composition.decompile"
# D-DIVERGENCE-MCP-TOOLS (S5) — the derive (spawn a dị bản). Tier-W: it MINTS a knowledge
# partition + persists the branch spec (expensive, only archivable, not undoable), so it is
# confirm-gated via the SAME mint_confirm_token → confirm_action spine (executed in actions.py).
# (_DERIVE_DESCRIPTOR is defined earlier — the durable-gate store needs it at import time.)

# ── D-AGENT-MODE §20 — authoring-run confirm descriptors (D5/D6). Book-scoped
# (payload carries book_id, not project_id); the confirm route
# (app/routers/actions.py) dispatches these BEFORE its Work-resolution branch,
# mirroring the motif_adopt per-book gate.
_AUTHORING_RUN_CREATE_DESCRIPTOR = "composition.authoring_run_create"
_AUTHORING_RUN_GATE_DESCRIPTOR = "composition.authoring_run_gate"
_AUTHORING_RUN_START_DESCRIPTOR = "composition.authoring_run_start"
_AUTHORING_RUN_RESUME_DESCRIPTOR = "composition.authoring_run_resume"
_AUTHORING_RUN_REVERT_ALL_DESCRIPTOR = "composition.authoring_run_revert_all"


# ── Durable-gate resolvers for the OTHER migrated KIND-C confirm tools ─────────
# Each mirrors _resolve_derive: reconstruct the confirm-execute effect from
# {owner_user_id, payload} (NO closure, NO token — the durable task IS the
# once-only guard), lazily importing the SAME `_execute_*` the POST /v1/
# composition/actions/confirm route runs. Fresh per-request clients (pool-backed)
# so the accept can land on any replica. owner_user_id → UUID to match the HTTP
# route's `envelope_user` (a real UUID there).


async def _resolve_publish(owner_user_id: str, payload: dict, _inputs: dict):
    """composition.publish ACCEPT effect — canonize the reviewed chapter draft.
    Mirrors the confirm route's Work-scoped branch: re-fetch the Work by the
    payload's project_id (a 400 if it vanished since propose), then run the
    shared `_execute_publish`."""
    from fastapi import HTTPException

    from app.routers.actions import _execute_publish

    pool = get_pool()
    try:
        project_id = UUID(str(payload["project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    work = await WorksRepo(pool).get(project_id)
    if work is None:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    return await _execute_publish(
        payload, project_id, work, UUID(str(owner_user_id)),
        OutlineRepo(pool), get_book_client(),
    )


async def _resolve_generate(owner_user_id: str, payload: dict, _inputs: dict):
    """composition.generate ACCEPT effect — run the grounded cowrite ENGINE
    in-process (the SAME `_execute_generate` the confirm route runs). Re-fetch the
    Work by project_id. Public-key spend attribution is a confirm-ROUTE concern
    (the non-tasks fallback path lifts the MCP-key headers there); the durable
    accept carries no MCP-key header context, consistent with derive/publish."""
    from fastapi import HTTPException

    from app.routers.actions import _execute_generate

    pool = get_pool()
    try:
        project_id = UUID(str(payload["project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    work = await WorksRepo(pool).get(project_id)
    if work is None:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    return await _execute_generate(payload, project_id, work, UUID(str(owner_user_id)))


async def _resolve_authoring_run_create(owner_user_id: str, payload: dict, _inputs: dict):
    """composition.authoring_run_create ACCEPT effect (book-scoped, no ledger —
    the service's guarded OCC transitions make a re-confirm a clean no-op/409)."""
    from app.routers.actions import _execute_authoring_run_create

    book_id = UUID(str(payload["book_id"]))
    return await _execute_authoring_run_create(payload, book_id, UUID(str(owner_user_id)))


async def _resolve_authoring_run_gate(owner_user_id: str, payload: dict, _inputs: dict):
    """composition.authoring_run_gate ACCEPT effect — needs the book client to
    resolve the chapter-id set (a headless service bearer is minted inside the
    effect for the MCP path)."""
    from app.routers.actions import _execute_authoring_run_gate

    book_id = UUID(str(payload["book_id"]))
    return await _execute_authoring_run_gate(
        payload, book_id, UUID(str(owner_user_id)), get_book_client(),
    )


async def _resolve_authoring_run_start(owner_user_id: str, payload: dict, _inputs: dict):
    """composition.authoring_run_start ACCEPT effect (gated → running)."""
    from app.routers.actions import _execute_authoring_run_start

    book_id = UUID(str(payload["book_id"]))
    return await _execute_authoring_run_start(payload, book_id, UUID(str(owner_user_id)))


async def _resolve_authoring_run_resume(owner_user_id: str, payload: dict, _inputs: dict):
    """composition.authoring_run_resume ACCEPT effect (paused → running)."""
    from app.routers.actions import _execute_authoring_run_resume

    book_id = UUID(str(payload["book_id"]))
    return await _execute_authoring_run_resume(payload, book_id, UUID(str(owner_user_id)))


async def _resolve_authoring_run_revert_all(owner_user_id: str, payload: dict, _inputs: dict):
    """composition.authoring_run_revert_all ACCEPT effect — needs the book client
    for the per-chapter restore (headless bearer minted inside the effect)."""
    from app.routers.actions import _execute_authoring_run_revert_all

    book_id = UUID(str(payload["book_id"]))
    return await _execute_authoring_run_revert_all(
        payload, book_id, UUID(str(owner_user_id)), get_book_client(),
    )


# The store persists only DATA ({descriptor, owner_user_id, payload}); resolvers
# are reconstructed by descriptor. PERSISTENT (Postgres `mcp_gate_tasks`) so a
# propose on one replica + its accept on another (or after a restart/deploy)
# resolve the same task exactly once (D-MCPTASKS-GO-STORE / T3c-REMAINING). Built
# with the pool GETTER (the pool doesn't exist yet at import time; PgTaskStore
# calls get_pool() lazily per op).
#
# NOT registered here — the ledger-guarded KIND-C confirms (decompile, motif_adopt,
# motif_mine, arc_import, conformance_run): their `_execute_*` require the confirm
# TOKEN (the consumed-token replay ledger; mine/import/conformance additionally key
# the usage-billing reserve on the token jti via `_billing_job_id(token)`), which a
# durable resolver has no access to. Reusing them cleanly needs an actions.py
# refactor to split the ledger/billing key from the effect — deferred; they keep
# minting a confirm_token (the durable task's own once-only resolve would replace
# the ledger, but the billing-key idempotency is a real design change on spend).
_task_store = PgTaskStore(get_pool, {
    _DERIVE_DESCRIPTOR: _resolve_derive,
    _PUBLISH_DESCRIPTOR: _resolve_publish,
    _GENERATE_DESCRIPTOR: _resolve_generate,
    _AUTHORING_RUN_CREATE_DESCRIPTOR: _resolve_authoring_run_create,
    _AUTHORING_RUN_GATE_DESCRIPTOR: _resolve_authoring_run_gate,
    _AUTHORING_RUN_START_DESCRIPTOR: _resolve_authoring_run_start,
    _AUTHORING_RUN_RESUME_DESCRIPTOR: _resolve_authoring_run_resume,
    _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR: _resolve_authoring_run_revert_all,
})
# tool_prefix="composition" → the input tool is `composition_task_provide_input`
# (gateway-routable + collision-free across task-capable domains; see the routing
# note in the spec / SESSION_HANDOFF).
register_task_endpoints(
    mcp_server, _task_store, tool_prefix="composition",
    internal_token=settings.internal_service_token,  # M2: accept-caller ownership check
)

# The motif kinds + the closed enums the LLM may pass (R1.4 schema). Defined here so
# the arg models below and the tests share one source.
_MotifKind = Literal["sequence", "situation", "hook", "emotion_arc", "trope", "pattern", "scheme"]


# ── shared helpers ────────────────────────────────────────────────────────────


def _ctx(ctx: MCPContext) -> ToolContext:
    """Validate the internal token + lift the envelope identity. A bad token /
    missing header surfaces as a tool error (success=False), not a 5xx."""
    return build_tool_context(ctx, settings.internal_service_token)


def _resolve_bid(tc: ToolContext, book_id: str | None) -> UUID:
    """Studio context binding — resolve a book-scoped tool's book_id from the arg OR the ambient
    X-Book-Id (tc.book_id). A 1-line drop-in for _uuid(book_id, "book_id"); the caller grant-checks it as usual."""
    scope = resolve_book_scope(book_id, tc)
    if scope is None:
        raise ValueError("book_id is required")
    return scope.id


def _resolve_pid(tc: ToolContext, project_id: str | None) -> UUID:
    """Studio context binding (spec 2026-07-22) — resolve a project-scoped tool's project_id from the
    arg OR the ambient X-Project-Id (tc.project_id, which chat-service derives book->Work->project_id
    and forwards). A 1-line drop-in for _uuid(args.project_id, "project_id"). The resolved project is grant-checked by
    the caller (via _book_or_deny) exactly like an explicit arg — the ambient is a scope hint, not authz.
    Only use it on a tool tagged ambient_project (its project_id arg must be Optional)."""
    scope = resolve_project_scope(project_id, tc)
    if scope is None:
        raise ValueError("project_id is required")
    return scope.id


def _grant_resolver() -> GrantResolver:
    """Adapt composition's GrantClient to the kit's GrantResolver shape
    (`(book_id, user_id) -> int`). The client is fail-closed (a book-service
    outage → NONE), so the kit guard denies on any backend error."""
    client = get_grant_client()

    async def resolve(book_id: UUID, user_id: UUID) -> int:
        return int(await client.resolve_grant(book_id, user_id))

    return resolve


def _named_ids(work: dict) -> dict:
    """D-COMPOSITION-ID-TRAP — give the Work's surrogate key an EXPLICIT name on the
    wire, and say which id the other tools want.

    A Work carries three uuids and used to serialize them as `id`, `project_id` and
    `book_id`. To a model, `id` reads as *"the id of the thing I just fetched"* — so it
    passes it to the next tool's `project_id`, and every scoped read answers "not found"
    for a row that exists. Measured live on the Mị Đế book; the agent then reported,
    correctly and uselessly, that Chapter 1 did not exist.

    A bare `id` is a name that means nothing on its own — the exact
    one-name-for-one-concept failure the frontend-tool contract bans. Rename it to
    `work_id`, and hand the caller a one-line map of which id each argument slot wants,
    so the answer is IN the payload rather than in a description it may not re-read.
    (The repo-level resolve accepts a work_id in the project_id slot as well; this is
    the half that stops the mistake being made, that one is the half that survives it.)
    """
    out = dict(work)
    if "id" in out:
        out["work_id"] = out.pop("id")
    out["_ids"] = (
        "work_id = this Work's own key. project_id = what every other composition_* "
        "tool's `project_id` argument wants. book_id = the book. They are DIFFERENT "
        "uuids — do not pass work_id as project_id."
    )
    return out


async def _book_or_deny(works: WorksRepo, tc: ToolContext, project_id: UUID, level: GrantLevel):
    """PM-8 (BPS-8): resolve the Work's ids-only scope (book_id/work_id/
    project_id — `scope_meta`, an un-user-scoped anti-oracle read) and gate the
    caller's E0 grant on the row's `book_id` at the operation's tier. The
    ordering inversion is the whole fix over the old `_work_or_deny`: the grant
    is first-class; row ownership is never consulted for ACCESS. A missing
    project raises the SAME H13 uniform error as a denied grant — no
    enumeration oracle. Returns the ids-only meta (use `meta.book_id`; fetch
    the full Work separately when a tool needs more than ids).

    D-COMPOSITION-ID-TRAP — this is also the CANONICALIZATION point. `scope_meta`
    accepts a `work_id` in the `project_id` slot (a book has three uuids and the
    model mixes them up), so the id the caller handed in may not be the project's.
    **Every caller must therefore re-bind its own `pid` from `meta.project_id`
    before using it again** — a gate that resolves while the subsequent query keeps
    comparing the RAW argument passes the grant and then fails the scope check, which
    is exactly what shipped in the first cut of this fix: `composition_get_outline_node`
    gated fine and still answered "not found or not accessible" for the node it had
    just been granted. Verified against the live MCP endpoint, not by reasoning.
    """
    meta = await works.scope_meta(project_id)
    if meta is None:
        raise uniform_not_accessible()
    await _gate(tc, meta.book_id, level)
    return meta


def _require_project(meta) -> UUID:
    """Re-bind the caller's `pid` from the canonicalized meta AND refuse a Work that has
    no knowledge project bound yet.

    `_book_or_deny` resolves a Work from any of the book's three uuids, but a Work created
    while knowledge-service was unreachable carries `project_id=NULL` and
    `pending_project_backfill=true` (C16/WG-3). Nothing stopped that NULL from being
    re-bound as `pid` and handed to the engines, where it became a dangling reference:
    measured live on composition_arc_apply, the answer was

        {"code": "BAD_REFERENCE", "detail": "project None has no composition_work row"}

    which is false twice over — the composition_work row exists, it is the PROJECT that is
    absent — and it leaks a Python None into a caller-facing string while naming no way
    out. 82 of 516 Works are in this state (TOOLV2 LOOP #142), so it is not a corner.

    This is a helper rather than a check inside `_book_or_deny` because ~27 of the 37
    gate call sites need only `meta.book_id` and are perfectly valid against a pending
    Work; only the sites that re-bind `pid` consume the project.
    """
    pid = meta.project_id
    if pid is None:
        raise ValueError(
            "this book's Work is not bound to a knowledge project yet (it was created "
            "while the knowledge service was unavailable) — call composition_create_work "
            "with this book_id to bind it, then retry"
        )
    return pid


async def _gate(tc: ToolContext, book_id: UUID, level: GrantLevel) -> None:
    """Run the book-ownership guard at the operation's tier (VIEW read / EDIT
    write). Raises the H13 uniform error on denial. A fresh guard per call keeps
    the ~60s positive cache process-local + simple (matches the per-request HTTP
    gate)."""
    guard = require_book_owner(_grant_resolver(), int(level))
    await guard(tc, book_id)


def _uuid(value: Any, field: str) -> UUID:
    """Parse a caller-supplied uuid, naming the FIELD and echoing what arrived.

    Every tool here parsed uuids with a bare `_uuid(args.x, "x")`, so a malformed one surfaced as
    Python's own "badly formed hexadecimal UUID string" — measured identical across 7 of 7
    composition tools, naming no argument at all. composition_arc_edit alone accepts seven uuid
    fields, so the caller could not tell which one to fix.

    Echoing the value is the part that carries information the caller cannot otherwise get. The
    one real occurrence in the corpus was composition_arc_suggest receiving
    "...cb-1bc5-7384-9fb4-9fb4-3435368886d0" — a model that had DUPLICATED a uuid segment. Shown
    its own string back, that is visible; described as badly formed, it is not (TOOLV2 LOOP #148).
    """
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(
            f"{field} must be a UUID — received {value!r}. Compare it against the id you meant "
            "to send; a repeated or dropped group is the usual cause."
        ) from None


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


# A translate is the one Tier-W motif op whose size is known EXACTLY before it runs —
# the input is the motif's own text — so the estimate is measured rather than a scope
# constant. The token count is honest; the $ is still a gate, not a quote (the real
# per-token cost lands when provider-registry bills the user's own model).
_TRANSLATE_USD_PER_1K_TOKENS = 0.01
_CHARS_PER_TOKEN = 3.0          # conservative: CJK sources tokenize far denser than en


def _translate_estimate(
    items: list[dict[str, Any]], target_language: str, kind: str = "motif",
) -> dict[str, Any]:
    """Size-derived $ estimate + an exact-ish token count for the confirm card."""
    from app.motif_i18n import (
        ARC_TEMPLATE_SPEC, MOTIF_SPEC, build_translation_entry, extract_translatable,
        flatten_entry,
    )

    spec = MOTIF_SPEC if kind == "motif" else ARC_TEMPLATE_SPEC
    chars = 0
    for m in items:
        for text in flatten_entry(
                build_translation_entry(extract_translatable(m, spec), spec)).values():
            chars += len(text)
    # in (source + prompt) + out (translation, allow 1.5× — most targets run longer
    # than English), plus a per-motif prompt overhead for the system + context block.
    tokens = int(chars / _CHARS_PER_TOKEN * 2.5) + 400 * len(items)
    return {
        "estimated_usd": round(tokens / 1000 * _TRANSLATE_USD_PER_1K_TOKENS, 4),
        "estimated_tokens": tokens,
        "currency": "USD",
        "basis": f"{len(items)} {kind}(s) → {target_language}",
    }


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
        ambient_book=True,
        ambient_project=True,
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
    # Ambient (studio context binding, spec 2026-07-22): when the model passes NEITHER id, fall
    # back to the envelope — X-Project-Id first (the bound book's Work), else X-Book-Id. So a
    # studio agent needn't hand over any id. Grant-checked below exactly like an explicit arg.
    if not project_id and not book_id:
        pscope = resolve_project_scope(None, tc)
        if pscope is not None:
            project_id = str(pscope.id)
        else:
            bscope = resolve_book_scope(None, tc)
            if bscope is not None:
                book_id = str(bscope.id)
    if project_id:
        pid = _uuid(project_id, "project_id")
        pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
        work = await works.get(pid)
        if work is None:
            raise uniform_not_accessible()
    elif book_id:
        # book→Work resolution (M-E live-caught): the agent naturally knows the book_id
        # (studio context) but every composition tool keys on project_id, and no tool
        # bridged the two — the model retried book_id AS project_id and dead-ended.
        # Gate FIRST (PM-8 — book_id given directly, no lookup needed), then resolve
        # the book's marked Works; 0 → the H13 uniform deny.
        bid = _uuid(book_id, "book_id")
        await _gate(tc, bid, GrantLevel.VIEW)
        marked = await works.resolve_by_book(bid)
        if not marked:
            raise uniform_not_accessible()
        if len(marked) > 1:
            # The book's marked Works (the grant already passed) — return them so
            # the model can pick (e.g. canonical vs a derivative).
            return {"candidates": [_named_ids(w.model_dump(mode="json")) for w in marked]}
        work = marked[0]
    else:
        raise ValueError("pass project_id or book_id")
    return _named_ids(work.model_dump(mode="json"))


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
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    detail: Annotated[
        Literal["summary", "full"],
        "summary = refs only (id/kind/title/status/version, no prose); full = every field.",
    ] = "summary",  # K37 drain: OUT-2 small-shape default
    limit: Annotated[
        int | None,
        "Coarse cap on nodes returned, a flat prefix of the tree (default 25 — may drop "
        "later arcs' scenes; `truncated` reports how many). Raise it, or read ONE node via "
        "composition_get_outline_node.",
    ] = 25,  # K37 drain: OUT-2 bounded default (list_tree fetches all → apply_response_contract caps + signals truncated, never a silent drop)
    include_archived: Annotated[bool, "Include soft-archived nodes."] = False,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
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
        "token you pass back to composition_outline_node_edit (op=\"update\"). Use this instead of "
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
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    node_id: Annotated[str, "The outline node's id. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
    outline = OutlineRepo(get_pool())
    node = await outline.get_node(_uuid(node_id, "node_id"))
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
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    chapter_id: Annotated[str, "The chapter's id. (a UUID)"],
    detail: Annotated[
        Literal["summary", "full"],
        "summary = metadata + draft_version only (drops the chapter body); full = the body too.",
    ] = "full",
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    meta = await _book_or_deny(works, tc, _uuid(project_id, "project_id"), GrantLevel.VIEW)
    book: BookClient = get_book_client()
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    try:
        draft = await book.get_draft(meta.book_id, _uuid(chapter_id, "chapter_id"), bearer)
        revisions = await book.list_revisions(meta.book_id, _uuid(chapter_id, "chapter_id"), bearer, limit=1)
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
    project_id: Annotated[str | None, "The Work's project_id. Optional — pass book_id instead if you only have the book."] = None,
    book_id: Annotated[str | None, "The book to list canon rules for. Resolves the book's composition project for you — pass this when you have the book id (e.g. from the chat context) and not a project id."] = None,
    active_only: Annotated[bool, "Only enforceable (active, non-archived) rules."] = False,
) -> dict:
    # D-S09-CANON-PROJECT-RESOLUTION — the canon-check rail is book-scoped but this tool only took a
    # project_id the agent doesn't have (the chat context supplies a book_id). Passing book_id used
    # to be a hard validation error the model read as "no rules — offer to set some up", so the rail
    # could never reach the conformance run. Accept book_id and resolve the book's composition
    # project (the SAME resolver composition_create_work uses, so it finds rules created there). The
    # returned rules carry their project_id, which the agent then passes to composition_conformance_run.
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    if project_id:
        pid: UUID | None = _uuid(project_id, "project_id")
        pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
    elif book_id:
        bid = _uuid(book_id, "book_id")
        await _gate(tc, bid, GrantLevel.VIEW)  # tenancy: grant-checked on the book itself
        pid = await _resolve_or_create_default_project(tc, bid, works)
        if pid is None:
            return {"rules": [], "note": "the knowledge service is unavailable — cannot resolve this "
                    "book's consistency rules right now; try again shortly"}
    else:
        return {"success": False, "error": "pass either project_id or book_id"}
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
        # "job status" -> "generation job status": jobs_get owns the unqualified phrase.
        synonyms=["generation job", "poll generation", "generate status",
                  "generation job status",
                  "cowrite job", "writing job", "is the chapter done"],
        tool_name="composition_get_generation_job",
    ),
)
async def composition_get_generation_job(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    job_id: Annotated[str, "The generation job id returned by composition_generate. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
    jobs = GenerationJobsRepo(get_pool())
    job = await jobs.get(_uuid(job_id, "job_id"))
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
    same pattern the retired composition prose proxies already used to reach
    book-service).

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
    """C16 (WG-3) greenfield degrade for the MCP composition_create_work path — return THE Work for this
    book, creating a lazy null-project one only if none exists. Now a thin delegate to the shared
    canonical-first `work_resolution.ensure_work` primitive (consolidated 2026-07-20; this was a
    pending-only copy that skipped the canonical check). Reached only when project resolution returned
    None (outage) ⇒ 0 marked Works, so the canonical lookup is a race-safety net. A truly-stuck create
    conflict raises ValueError (unchanged)."""
    try:
        return await ensure_work(works, book_id, created_by=created_by)
    except asyncpg.UniqueViolationError:
        raise ValueError("work create conflict — retry") from None


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
    book_id: Annotated[str, "The book the Work composes. (a UUID)"],
    project_id: Annotated[
        str | None,
        "The knowledge project id to bind the Work to (its PK). Optional — omit "
        "it to auto-resolve or auto-create (idempotently) the book's default "
        "knowledge project.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    works = WorksRepo(get_pool())

    if project_id:
        pid = _uuid(project_id, "project_id")
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
    # TOOLV2 LOOP #142 — adopt this book's PENDING Work before creating a new one.
    #
    # `works.get` keys on project_id, so it cannot see a Work whose project_id is still
    # NULL (C16/WG-3: created while knowledge-service was down). Without this, the create
    # below hits the one-Work-per-book constraint, the re-get by project_id misses for the
    # same reason, and the caller is told "not found or not accessible" — permanently, on
    # every retry, for the tool that is supposed to be the REMEDY for a pending Work.
    #
    # It only bit when the book's knowledge project ALREADY existed: the backfill that
    # `_resolve_or_create_default_project` performs lives on its project-CREATE branch, so
    # a book resolving to an existing project skipped it entirely. Measured: 5 of 80 pending
    # Works are in that state, and for those five the workspace could never be opened.
    pending = await works.get_pending_for_book(bid)
    if pending is not None and pending.id is not None:
        adopted = await works.backfill_project(pending.id, pid, created_by=tc.user_id)
        if adopted is not None:
            out = adopted.model_dump(mode="json")
            out["_meta"] = {"undo_hint": None}  # adopting an existing row is not a create
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
    # project_id OPTIONAL (ambient_project) — omitted inside a studio, resolves from X-Project-Id.
    project_id: str | None = None
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
    # D-SCENE-BEATS — the units this scene is DRAFTED in. Declared on the MCP surface as well
    # as REST because the AGENT is the primary writer of a beat decomposition, and a field the
    # repo accepts but one front door cannot send is the CF-9 "one repo method, two front
    # doors" divergence this file's sibling comment already records — REST lagged MCP last
    # time; this is the same gap mirrored.
    draft_beats: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_DRAFT_BEATS)
    exit_state: SceneExitStateIn | None = None
    # D-SCENE-CREATE-PARITY — the last two fields PlanForge's scene upsert writes and
    # this path could not. Both feed the packer, so their absence is a QUIET grounding
    # loss rather than an error: `present_entity_ids` is the scene's cast, and it is what
    # the packer loads character lore/voices from — without it a scene is drafted with no
    # idea who is in it. `tension` is the beat's charge, read by the pacing lens and the
    # arc-conformance judge. PlanForge fills both; an outline authored through this tool
    # left them empty and every downstream lens silently had less to work with.
    tension: int | None = Field(default=None, ge=0, le=100)
    present_entity_ids: list[str] | None = None


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
        ambient_project=True,
        visibility="legacy", superseded_by="composition_outline_node_edit",  # S3
        tool_name="composition_outline_node_create",
    ),
)
async def composition_outline_node_create(ctx: MCPContext, args: _NodeCreateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _resolve_pid(tc, args.project_id)
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    outline = OutlineRepo(get_pool())
    # K13 (2026-07-23) — idempotency guard against an agent double-fire. LIVE-PROBED: two
    # byte-identical calls made TWO outline nodes; `outline_node`'s uniques only cover the
    # plan-provenance and decompile paths, so a plain agent create had no protection.
    # Keyed on (project, kind, parent, title) so a same-titled node under a DIFFERENT
    # parent — a real outlining case — still creates.
    if (args.title or "").strip():
        dup = await outline.find_node_by_title(
            pid, kind=args.kind, title=args.title.strip(),
            parent_id=_uuid(args.parent_id, "parent_id") if args.parent_id else None,
        )
        if dup is not None:
            out = dup.model_dump(mode="json")
            out["_meta"] = {"undo_hint": _undo(
                "composition_outline_node_delete", project_id=args.project_id, node_id=str(dup.id),
            )}
            out["note"] = "an outline node with this title already exists here — returning it."
            return out
    try:
        node = await outline.create_node(
            pid, kind=args.kind, parent_id=_uuid(args.parent_id, "parent_id") if args.parent_id else None,
            title=args.title, goal=args.goal, synopsis=args.synopsis, status=args.status,
            chapter_id=_uuid(args.chapter_id, "chapter_id") if args.chapter_id else None,
            # 22 SC4/SC8 — the authored intent (schema-validated above).
            location_entity_id=_uuid(args.location_entity_id, "location_entity_id") if args.location_entity_id else None,
            story_time=args.story_time, conflict=args.conflict, outcome=args.outcome,
            value_shift=args.value_shift, stakes=args.stakes, target_words=args.target_words,
            draft_beats=args.draft_beats,
            # D-GENERATED-FACT-HAS-NO-HOME — provenance is stamped SERVER-side (there is no
            # stored envelope to merge onto at create, so `existing` is None). `source` is not
            # on the wire model at all: a caller able to choose it could stamp its own write
            # `author` and permanently block the drafter's write-back.
            exit_state=(
                merge_authored_exit_state(None, args.exit_state.model_dump(mode="json"))
                if args.exit_state is not None else None
            ),
            # D-SCENE-CREATE-PARITY — the scene's cast + beat charge, the two fields
            # PlanForge writes and this path could not (see the args).
            tension=args.tension,
            present_entity_ids=[UUID(e) for e in (args.present_entity_ids or [])] or None,
            created_by=tc.user_id,
        )
    except ReferenceViolationError as exc:
        raise uniform_not_accessible(exc) from exc
    out = node.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo(
        "composition_outline_node_delete", project_id=args.project_id, node_id=str(node.id),
    )}
    # D-SCENE-PROSE-NOWHERE-TO-LAND — say plainly that this node is PLAN-ONLY.
    # A node created here has `chapter_id = NULL` unless the caller supplied one, and
    # NULL is the normal state of a planned node. But the manuscript surfaces key off
    # `chapter_id`: the compose panel lists a chapter's scenes by it, and prose is
    # accepted into a real book chapter. So a caller that creates a chapter node, sees a
    # full row come back, and starts generating into it produces work nobody can reach —
    # which is exactly what happened on the Mị Đế book (783 generated words, compose
    # panel: "Chưa có cảnh"). The row is correct; the SILENCE about what it is not was
    # the defect. An agent reads the result, not the docstring, so it goes in the result.
    if node.chapter_id is None:
        out["_status"] = "plan_only"
        out["_note"] = (
            "Created in the PLAN tree only — there is no manuscript chapter behind it yet "
            "(chapter_id is null), so prose cannot be written into it and the compose "
            "panel will not list it. That is fine while outlining. Before drafting, "
            "materialise the chapter (PlanForge bootstrap: propose → approve → apply), "
            "which creates the book chapter and stamps chapter_id onto its scenes."
        )
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
    # D-SCENE-BEATS — the units this scene is DRAFTED in. Declared on the MCP surface as well
    # as REST because the AGENT is the primary writer of a beat decomposition, and a field the
    # repo accepts but one front door cannot send is the CF-9 "one repo method, two front
    # doors" divergence this file's sibling comment already records — REST lagged MCP last
    # time; this is the same gap mirrored.
    draft_beats: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_DRAFT_BEATS)
    exit_state: SceneExitStateIn | None = None
    # D-SCENE-PROSE-NOWHERE-TO-LAND — BIND a plan node to a manuscript chapter.
    # `chapter_id` used to be create-only, which made a planned node a DEAD END: it is
    # created NULL (the normal state), the compose panel keys off this column, and there
    # was no way to set it afterwards. PlanForge's bootstrap could stamp it via its own
    # SQL, but nothing an author or agent could reach could — so an outline built outside
    # a plan run could never be drafted into, ever. The repo has always listed chapter_id
    # as updatable (`_UPDATABLE_COLUMNS`); only the tool withheld it.
    chapter_id: str | None = None
    # D-SCENE-CREATE-PARITY — editable for the same reason they are creatable: a cast list
    # is the field an author most often gets wrong on the first pass (a character joins the
    # scene late), and it is what the packer loads lore from.
    tension: int | None = Field(default=None, ge=0, le=100)
    present_entity_ids: list[str] | None = None


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
        visibility="legacy", superseded_by="composition_outline_node_edit",  # S3
        tool_name="composition_outline_node_update",
    ),
)
async def composition_outline_node_update(ctx: MCPContext, args: _NodeUpdateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    outline = OutlineRepo(get_pool())
    node_id = _uuid(args.node_id, "node_id")
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
            "draft_beats": args.draft_beats,
        }.items() if v is not None
    }
    # location_entity_id is a UUID column (str arg → UUID); exit_state is the SC12
    # envelope (model → plain dict, ::jsonb serialized by update_node's B2 path).
    if args.location_entity_id is not None:
        patch["location_entity_id"] = _uuid(args.location_entity_id, "location_entity_id")
    if args.exit_state is not None:
        # D-GENERATED-FACT-HAS-NO-HOME — MERGE, do not replace. A write here rewrites the whole
        # JSONB envelope, so an author who edits `plot` on a scene the drafter has already
        # recorded a cast for would wipe that record and the next scene would silently lose its
        # continuity floor. `cast` omitted ⇒ carried forward with its provenance.
        patch["exit_state"] = merge_authored_exit_state(
            prior.exit_state, args.exit_state.model_dump(mode="json"))
    # D-SCENE-PROSE-NOWHERE-TO-LAND — bind the node to a manuscript chapter (see the arg).
    if args.chapter_id is not None:
        patch["chapter_id"] = _uuid(args.chapter_id, "chapter_id")
    # D-SCENE-CREATE-PARITY — cast + beat charge. `tension` rides the sparse-patch dict
    # above's convention (None = leave unchanged); `present_entity_ids` needs the UUID
    # coercion, and an explicit [] is a MEANINGFUL clear ("nobody is in this scene yet"),
    # so it is tested for None rather than falsiness.
    if args.tension is not None:
        patch["tension"] = args.tension
    if args.present_entity_ids is not None:
        patch["present_entity_ids"] = [UUID(e) for e in args.present_entity_ids]
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
    # unchanged" (there is no clear verb) — so a field whose PRIOR was None (the nullable
    # SC4 fields: value_shift, target_words, location_entity_id, story_time, exit_state —
    # and `chapter_id`, whose prior is None on every plan-only node, so BINDING one is
    # correctly un-undoable) cannot be faithfully reversed: emitting `field: null` would silently
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
        visibility="legacy", superseded_by="composition_outline_node_edit",  # S3
        tool_name="composition_outline_node_delete",
    ),
)
async def composition_outline_node_delete(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    node_id: Annotated[str, "The node to archive. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    outline = OutlineRepo(get_pool())
    # Project-scope BEFORE mutating: archive_node targets by id only, so confirm
    # the node is in the gated Work's project (else a node from another Work
    # would be archived under THIS book's gate). See node_update note.
    target = await outline.get_node(_uuid(node_id, "node_id"))
    if target is None or target.project_id != pid:
        raise uniform_not_accessible()
    node = await outline.archive_node(_uuid(node_id, "node_id"))
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
        visibility="legacy", superseded_by="composition_outline_node_edit",  # S3
        tool_name="composition_outline_node_restore",
    ),
)
async def composition_outline_node_restore(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    node_id: Annotated[str, "The node to restore. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    outline = OutlineRepo(get_pool())
    # Project-scope BEFORE mutating: restore_node targets by id only. get_node
    # returns archived rows too, so it confirms the (archived) target is in the
    # gated Work's project before the un-archive. See node_update note.
    target = await outline.get_node(_uuid(node_id, "node_id"))
    if target is None or target.project_id != pid:
        raise uniform_not_accessible()
    node = await outline.restore_node(_uuid(node_id, "node_id"))
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
        visibility="legacy", superseded_by="composition_scene_link_edit",  # S3
        tool_name="composition_scene_link_create",
    ),
)
async def composition_scene_link_create(ctx: MCPContext, args: _SceneLinkCreateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    scene_links = SceneLinksRepo(get_pool())
    try:
        link = await scene_links.create(
            pid, _uuid(args.from_node_id, "from_node_id"), _uuid(args.to_node_id, "to_node_id"),
            kind=args.kind, label=args.label, created_by=tc.user_id,
        )
    except ReferenceViolationError as exc:
        raise uniform_not_accessible(exc) from exc
    except asyncpg.UniqueViolationError:
        # TOOLV2 LOOP #218 — a repeat edge leaked the RAW Postgres error, constraint name
        # and column tuple included: 'duplicate key value violates unique constraint
        # "uq_scene_link_edge" DETAIL: Key (from_node_id, to_node_id, kind)=(...)'. Three
        # siblings in this same service already answer this in the tool's own vocabulary --
        # motif_link_create ("that edge already exists"), motif_create and
        # arc_template_create ("... already exists in your library") -- so this was the one
        # site that missed the pattern, not a missing pattern.
        return {
            "success": False,
            "outcome": "applied_conflict",
            "error": "that scene link already exists (same from, to, and kind)",
        }
    out = link.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo(
        "composition_scene_link_delete", project_id=args.project_id, link_id=str(link.id),
    )}
    return out


@mcp_server.tool(
    name="composition_scene_link_delete",
    description=(
        "Delete a scene-link edge — a SOFT archive: the row is kept with "
        "is_archived=true and stops being listed, so an accidental unlink has not "
        "destroyed the author's declared connection or its label. EDIT required "
        "(auto-applied; the Undo hint names a real reverse op)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["unlink scenes", "remove scene link", "delete edge"],
        visibility="legacy", superseded_by="composition_scene_link_edit",  # S3
        tool_name="composition_scene_link_delete",
    ),
)
async def composition_scene_link_delete(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    link_id: Annotated[str, "The scene-link edge id. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    scene_links = SceneLinksRepo(get_pool())
    # Project-scope the delete: constrain the repo WHERE clause by the gated
    # Work's project so an edge from another Work (gated on a different book)
    # cannot be deleted under THIS book's gate. See node_update note.
    deleted = await scene_links.delete(pid, _uuid(link_id, "link_id"))
    if not deleted:
        raise uniform_not_accessible()
    # A hard delete has no verified reverse op (the row is gone) → undo unavailable.
    # F3: was `undo_hint: None` — an explicit "no undo" over a HARD delete that destroyed the
    # author's declared connection and its authored label. The delete is now soft, so the hint can
    # name a real reverse op.
    return {"deleted": True, "link_id": link_id, "_meta": {"undo_hint": _undo(
        "composition_scene_link_edit", op="restore", project_id=project_id, link_id=link_id)}}


@mcp_server.tool(
    name="composition_scene_link_restore",
    description=(
        "Restore a soft-deleted scene-link edge — the UNDO the delete promises. Pass the Work's "
        "project_id + the link_id. Fails if that same edge has since been re-declared (restoring "
        "would collide with the newer one). EDIT required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["restore scene link", "undo scene link delete", "bring back scene link"],
        visibility="legacy", superseded_by="composition_scene_link_edit",
        tool_name="composition_scene_link_restore",
    ),
)
async def composition_scene_link_restore(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    link_id: Annotated[str, "The scene-link edge id. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    scene_links = SceneLinksRepo(get_pool())
    if not await scene_links.restore(pid, _uuid(link_id, "link_id")):
        return {"success": False, "error": (
            "that scene link could not be restored — it was never deleted, or the same edge has "
            "since been re-declared")}
    return {"restored": True, "link_id": link_id}


class _CanonRuleCreateArgs(ForbidExtra):
    project_id: str
    text: str
    # K20 — the DB enforces CHECK (scope IN ('world','entity','reveal_gate')), but the arg was
    # a bare `str` with NO description at all: the model had zero signal and any near-miss
    # ("global", "book") became a 23514 check violation it could not have foreseen. The schema
    # now declares exactly what the table already requires.
    scope: Annotated[Literal["world", "entity", "reveal_gate"], "world | entity | reveal_gate"] = "world"
    entity_id: str | None = None
    from_order: int | None = None
    until_order: int | None = None
    kind: str | None = None


# ── D-DIVERGENCE-MCP-TOOLS (S5) — agent parity for the dị bản manage surface. The SAFE
#    verbs (list + archive) ship here; CREATE (derive) is a Tier-W action that mints a
#    knowledge partition and MUST go through the AN-8 confirm spine — spec'd separately in
#    docs/specs/2026-07-17-divergence-mcp-tools.md, not shipped here without its confirm.
class _DerivativeArchiveArgs(ForbidExtra):
    project_id: str
    expected_version: int


@mcp_server.tool(
    name="composition_list_derivatives",
    description=(
        "List a book's what-if derivatives (dị bản): the canonical Work + every branch, "
        "each with its name, branch_point, status and version. Pass book_id — that is the "
        "usual way and the one you will already have. (You may pass ANY Work's project_id "
        "from the book instead; give exactly one.) The entry with is_canonical=false is a "
        "derivative, and its project_id is what the override and derivative tools want. "
        "VIEW required. Read-only — the agent's read side of the divergence manage panel."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["list dị bản", "list what-if branches", "list derivatives", "list divergences", "show branches"],
        tool_name="composition_list_derivatives",
    ),
)
async def composition_list_derivatives(
    ctx: MCPContext,
    book_id: Annotated[str | None, "The book whose Works to list (a UUID). The usual way in."] = None,
    project_id: Annotated[str | None, "Any Work's project_id from the book (a UUID) — an alternative to book_id."] = None,
) -> dict:
    # 🔴 THIS USED TO REQUIRE A WORK'S ID TO ENUMERATE A BOOK'S WORKS, which is a chicken-and-egg
    # the tool imposed on itself: it uses project_id ONLY to find the book and then lists BY BOOK
    # (see resolve_by_book below). The book id is what this function actually wants.
    #
    # MEASURED 2026-08-24 across c-override8/9/10, K=5 each: composition_entity_override_edit is
    # refused NOT_A_DERIVATIVE, its refusal correctly sends the model here, and the model cannot
    # produce a project_id — it tried the turn's BOOK id, the target ENTITY id, and the book's
    # TITLE. book_id is the one id `context_ids` carries on EVERY turn (project_id only on
    # studio/editor turns), so accepting it lets _inject_context_ids fill it with no further
    # change, and gives the cross-wire correction something to substitute rather than only
    # something to drop.
    #
    # The project_id path is kept byte-for-byte so no existing caller changes behaviour.
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    if bool(book_id) == bool(project_id):
        return {"success": False, "error": (
            "give EXACTLY ONE of book_id or project_id — book_id is the usual way in, and "
            "project_id is for when you already hold a Work's id from this book."
        )}
    if book_id:
        bid = _uuid(book_id, "book_id")
        await _gate(tc, bid, GrantLevel.VIEW)
    else:
        meta = await _book_or_deny(works, tc, _uuid(project_id, "project_id"), GrantLevel.VIEW)
        bid = meta.book_id
    rows = await works.resolve_by_book(bid)
    return {
        "works": [
            {
                "project_id": str(w.project_id) if w.project_id else None,
                "is_canonical": w.source_work_id is None,
                "name": (w.settings or {}).get("derivative_name"),
                "branch_point": w.branch_point,
                "status": w.status,
                "version": w.version,
            }
            for w in rows
        ],
    }


@mcp_server.tool(
    name="composition_get_derivative_context",
    description=(
        "Read ONE what-if derivative's DURABLE divergence spec — taxonomy, branch_point, "
        "pov_anchor, canon_rules, and entity overrides (the persisted substrate the packer "
        "applies at retrieval, not the derive-time cache). VIEW required. Read-only. Returns "
        "is_derivative=false for the canonical Work."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["get dị bản spec", "derivative context", "branch spec", "what-if spec", "divergence spec"],
        tool_name="composition_get_derivative_context",
    ),
)
async def composition_get_derivative_context(
    ctx: MCPContext,
    project_id: Annotated[str, "The derivative Work's project_id. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
    work = await works.get(pid)
    if work is None:
        raise uniform_not_accessible()
    if work.source_work_id is None:
        return {"is_derivative": False}
    derivatives = DerivativesRepo(get_pool())
    deriv = await build_derivative_context(work, works_repo=works, derivatives_repo=derivatives)
    spec = await derivatives.get_spec_for_work(work.id) if work.id else None
    return {
        "is_derivative": True,
        "name": (work.settings or {}).get("derivative_name"),
        "source_work_id": str(work.source_work_id),
        "source_project_id": str(deriv.source_project_id) if deriv.source_project_id else None,
        "branch_point": deriv.branch_point,
        "taxonomy": spec.taxonomy if spec else None,
        "pov_anchor": str(spec.pov_anchor) if spec and spec.pov_anchor else None,
        "canon_rules": list(spec.canon_rule) if spec else [],
        "overrides": [
            {"target_entity_id": str(o.target_entity_id), "overridden_fields": o.overridden_fields}
            for o in deriv.overrides
        ],
    }


@mcp_server.tool(
    name="composition_archive_derivative",
    description=(
        "Archive a what-if derivative (dị bản) — a REVERSIBLE soft-delete (its chapters + "
        "knowledge partition survive; restore via composition_derivative_edit op=restore). Requires "
        "`expected_version` (optimistic concurrency; stale → applied_conflict). EDIT "
        "required. Rejects the canonical Work (only a derivative can be archived here)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["archive dị bản", "archive derivative", "delete what-if branch", "remove branch"],
        visibility="legacy", superseded_by="composition_derivative_edit",  # S3
        tool_name="composition_archive_derivative",
    ),
)
async def composition_archive_derivative(ctx: MCPContext, args: _DerivativeArchiveArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    work = await works.get(pid)
    if work is None:
        raise uniform_not_accessible()
    # DERIVATIVE-only: archiving the canonical Work here would orphan the book — reject.
    if work.source_work_id is None:
        return {"success": False, "error": "NOT_A_DERIVATIVE — archive applies only to a dị bản (a DERIVATIVE Work — create one with composition_create_derivative; composition_derivative_edit only UPDATES an existing one), not the canonical Work"}
    try:
        updated = await works.update(pid, {"status": "archived"}, created_by=tc.user_id, expected_version=args.expected_version)
    except VersionMismatchError as exc:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "stale expected_version — refetch and retry", "current_version": exc.current.version,
        }
    if updated is None:
        raise uniform_not_accessible()
    out = updated.model_dump(mode="json")
    # C-ACTIVITY: a STRUCTURED hint to the REAL reverse op (composition_derivative_edit op=restore).
    # The prior value was a bare string ("restore by PATCH status=active") — silently dropped by
    # chat-service tool_undo_hint AND naming an operation no tool exposed (the archive claimed
    # reversibility that was unreachable; op=restore now delivers it).
    out["_meta"] = {"undo_hint": _undo(
        "composition_derivative_edit", op="restore",
        project_id=args.project_id, expected_version=updated.version)}
    return out


class _DeriveOverride(ForbidExtra):
    target_entity_id: str
    overridden_fields: dict[str, Any] = {}


class _DeriveArgs(ForbidExtra):
    project_id: str  # the SOURCE (canonical) Work's project_id
    name: Annotated[str, "The dị bản's human name (1..200 chars)."]
    # TOOLV2 LOOP #178 — the bound is DECLARED, not checked in the handler.
    #
    # branch_point is a 0-based chapter index, and nothing validated it: a propose with -5
    # minted a confirm token and the confirm CREATED the derivative, knowledge partition and
    # all, with branch_point = -5 persisted. Deriving is expensive and only archivable, so a
    # structurally impossible index should never survive to the write.
    #
    # Declared here rather than guarded in the handler because #166 measured the difference:
    # a bound the schema knows about is enforced BEFORE the handler runs and explained for
    # free -- 'Input should be greater than or equal to 0 (you sent -5)' -- while a bound
    # that lives only in a comment is neither. The sibling unit_index already does this.
    branch_point: int | None = Field(default=None, ge=0)
    taxonomy: Literal["pov_shift", "character_transform", "au"] = "au"
    pov_anchor: str | None = None
    canon_rule: list[str] = []
    entity_overrides: list[_DeriveOverride] = []


@mcp_server.tool(
    name="composition_create_derivative",
    description=(
        "PROPOSE spawning a what-if derivative (dị bản) from a SOURCE Work. Deriving MINTS a fresh "
        "knowledge partition + persists the branch spec — expensive, and only archivable (not "
        "undoable) — so it is CONFIRM-GATED: it returns a `confirm_token` + descriptor and creates "
        "NOTHING until the user confirms via confirm_action. Pass the source (canonical) Work's "
        "project_id + a name; optionally branch_point (0-based chapter index), taxonomy, canon_rule[], "
        "pov_anchor, entity_overrides. EDIT on the source's book. Rejects deriving from a derivative."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["derive dị bản", "spawn what-if", "create derivative", "branch the book", "fork the spec", "new divergence"],
        tool_name="composition_create_derivative",
    ),
)
async def composition_create_derivative(ctx: MCPContext, args: _DeriveArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    # Gate EDIT on the source's book — the SAME gate the REST route + the confirm re-check use.
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)
    source = await works.get(pid)
    if source is None:
        raise uniform_not_accessible()
    if source.source_work_id is not None:
        return {"success": False, "error": "CANNOT_DERIVE_FROM_DERIVATIVE — branch from the canonical Work"}
    if source.id is None:
        return {"success": False, "error": "SOURCE_WORK_NOT_BACKED — the source has no knowledge project yet"}
    name = args.name.strip()
    if not 1 <= len(name) <= 200:
        return {"success": False, "error": "name must be 1..200 characters"}
    # The signed payload captures EXACTLY what confirm will execute (the LLM cannot alter the target
    # between propose and confirm). book_id lets the confirm re-gate EDIT without another resolve.
    payload = {
        "source_project_id": str(pid),
        "book_id": str(meta.book_id),
        "name": name,
        "branch_point": args.branch_point,
        "taxonomy": args.taxonomy,
        "pov_anchor": args.pov_anchor,
        "canon_rule": list(args.canon_rule),
        "entity_overrides": [
            {"target_entity_id": o.target_entity_id, "overridden_fields": o.overridden_fields}
            for o in args.entity_overrides
        ],
    }
    _title = f"Spawn a dị bản '{name}' — mints a knowledge partition (cannot be undone, only archived)"

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret, tc.user_id, meta.book_id, _DERIVE_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _DERIVE_DESCRIPTOR,
            "title": _title,
            "domain": "composition",
        }

    # Capability-gated (spec §4.2): a durable ext-tasks gate for a tasks-capable client,
    # else today's confirm_token — a non-tasks client (pre-driver chat-service, the public
    # edge) is NEVER handed a task it can't drive. `payload` is captured so the accept
    # executes EXACTLY what was proposed (the LLM can't alter the target between the two).
    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_DERIVE_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": _title, "descriptor": _DERIVE_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


# ── S-04: post-derive delta EDITING (agent parity). The deltas were frozen at
#    derive-time; these make the spec + overrides mutable. Direct EDIT (like
#    archive) — no confirm spine: they touch only the derivative's own delta rows,
#    mint no knowledge partition. taxonomy is a closed set via Literal (no
#    CLOSED_SET_ARGS registry in composition — Pydantic enforces it at construction).

class _DivergenceSpecUpdateArgs(ForbidExtra):
    project_id: str  # the DERIVATIVE Work's project_id
    taxonomy: Literal["pov_shift", "character_transform", "au"] | None = None
    pov_anchor: str | None = None
    canon_rule: list[str] | None = None


async def _require_derivative(works: WorksRepo, tc, project_id: UUID):
    """Gate EDIT + resolve the derivative Work (source_work_id set). Returns the Work,
    or a sentinel dict via raise for the not-accessible / not-a-derivative cases."""
    project_id = (await _book_or_deny(works, tc, project_id, GrantLevel.EDIT)).project_id
    work = await works.get(project_id)
    if work is None:
        raise uniform_not_accessible()
    return work


@mcp_server.tool(
    name="composition_divergence_spec_update",
    description=(
        "Edit a what-if derivative's (dị bản) divergence spec AFTER derive — change the "
        "taxonomy (pov_shift|character_transform|au), the pov_anchor, or the added canon_rule[]. "
        "Only the fields you pass change; pass pov_anchor=null to clear it. EDIT required "
        "(auto-applied; Undo restores the prior values). Rejects the canonical Work."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit dị bản spec", "update divergence spec", "change branch taxonomy", "edit what-if spec"],
        visibility="legacy", superseded_by="composition_derivative_edit",  # S3
        tool_name="composition_divergence_spec_update",
    ),
)
async def composition_divergence_spec_update(ctx: MCPContext, args: _DivergenceSpecUpdateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _require_derivative(works, tc, _uuid(args.project_id, "project_id"))
    if work.source_work_id is None:
        return {"success": False, "error": "NOT_A_DERIVATIVE — the spec exists only on a dị bản (a DERIVATIVE Work — create one with composition_create_derivative; composition_derivative_edit only UPDATES an existing one)"}
    fs = args.model_fields_set
    kwargs: dict[str, Any] = {}
    if "taxonomy" in fs and args.taxonomy is not None:
        kwargs["taxonomy"] = args.taxonomy
    if "pov_anchor" in fs:  # explicit null clears the anchor
        kwargs["pov_anchor"] = _uuid(args.pov_anchor, "pov_anchor") if args.pov_anchor else None
    if "canon_rule" in fs and args.canon_rule is not None:
        kwargs["canon_rule"] = list(args.canon_rule)
    derivatives = DerivativesRepo(get_pool())
    prior = await derivatives.get_spec_for_work(work.id)  # captured for the Undo hint
    if prior is None:
        raise uniform_not_accessible()
    spec = await derivatives.update_spec(work.id, work.book_id, **kwargs)
    if spec is None:
        raise uniform_not_accessible()
    # Undo re-applies the prior value of exactly the fields this call changed.
    undo_fields: dict[str, Any] = {}
    if "taxonomy" in kwargs:
        undo_fields["taxonomy"] = prior.taxonomy
    if "pov_anchor" in kwargs:
        undo_fields["pov_anchor"] = str(prior.pov_anchor) if prior.pov_anchor else None
    if "canon_rule" in kwargs:
        undo_fields["canon_rule"] = list(prior.canon_rule)
    out = {"success": True, "spec": spec.model_dump(mode="json")}
    out["_meta"] = {"undo_hint": _undo(
        "composition_divergence_spec_update", project_id=args.project_id, **undo_fields,
    ) if undo_fields else None}
    return out


class _EntityOverrideAddArgs(ForbidExtra):
    project_id: str  # the DERIVATIVE Work's project_id
    target_entity_id: str
    overridden_fields: dict[str, Any] = {}


@mcp_server.tool(
    name="composition_entity_override_add",
    description=(
        "Add ONE entity-field override to a what-if derivative (dị bản) AFTER derive — override "
        "another entity's fields later (the delta was otherwise frozen at derive-time). Pass the "
        "derivative's project_id, the target_entity_id, and overridden_fields (field→value JSON). "
        "EDIT required (auto-applied; Undo deletes it). One override per entity — a duplicate is rejected."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["add dị bản override", "override entity", "add entity override", "override another entity"],
        visibility="legacy", superseded_by="composition_entity_override_edit",  # S3
        tool_name="composition_entity_override_add",
    ),
)
async def composition_entity_override_add(ctx: MCPContext, args: _EntityOverrideAddArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _require_derivative(works, tc, _uuid(args.project_id, "project_id"))
    if work.source_work_id is None:
        # 🔴 THIS USED TO SAY ONLY "create one with composition_create_derivative", AND THE BOOK
        # USUALLY ALREADY HAS ONE. Measured c-override8, K=5 on a fixture whose seed creates a
        # derivative: the model is handed the book's ambient (canonical) project, refused here,
        # and told to CREATE — when what it needs is to FIND the derivative that exists. Listing
        # comes first now, and naming the tool also ARMS it (chat-service's _tools_named_in_refusal
        # runs on dispatch results), which a message that named only the create tool never did for
        # the lookup.
        return {"success": False, "error": (
            "NOT_A_DERIVATIVE — this project_id is the book's CANONICAL Work, and an override "
            "exists only on a dị bản (a DERIVATIVE Work, which is a separate Work with its own "
            "project_id). Call composition_list_derivatives and pass it THIS SAME project_id — it "
            "lists every Work of the book — then retry with the project_id of the entry whose "
            "is_canonical is false. Only if that list has no derivative should you create one with "
            "composition_create_derivative."
        )}
    # 🔴 AN OVERRIDE WITH NO FIELDS OVERRIDES NOTHING, and it was being created. Measured
    # 2026-08-23 by direct probe: overridden_fields={} returned {"success": true, "override":
    # {..., "overridden_fields": {}}}. The row then reads as a real override to everything
    # downstream — the derivative's context pack, the undo hint, the list — and resolves to no
    # change at all. Refused here rather than written and puzzled over later.
    #
    # 🔴 THE PARAGRAPH THAT USED TO SIT HERE DEFERRED THE OTHER TWO CASES — a target_entity_id
    # that does not exist, and one belonging to another BOOK — on the grounds that glossary's
    # client is "documented to return [] / None on any failure and never raise", so gating on it
    # would be a fail-open/fail-closed product call. That premise was wrong, and checking it is
    # what closed these: the docstring describes the DEGRADE-SAFE methods, and the same module
    # already carries GlossaryClientError plus `seed_entities_or_raise`, whose own docstring
    # states this exact principle for a gate "which must never record a mutation as applied when
    # it actually failed". The codebase had answered the question before I called it undecidable.
    if not args.overridden_fields:
        return {
            "success": False,
            "error": (
                "EMPTY_OVERRIDE — overridden_fields is required and must name at least one field, "
                'e.g. {"occupation": "cartographer"}. An override with no fields would change '
                "nothing while appearing in the derivative as a real one."
            ),
        }
    # D-AN-OVERRIDE-ACCEPTS-A-TARGET-ENTITY-THAT-IS-NOT-THERE — the target must EXIST in this
    # derivative's own book. The endpoint is book-scoped, so one call answers both open cases:
    # an entity that does not exist and one belonging to ANOTHER book are alike absent from this
    # book's items, and earn the same refusal — which is also what H13 wants, since telling them
    # apart would be an existence oracle for a book the caller may not own.
    _target = _uuid(args.target_entity_id, "target_entity_id")
    try:
        _known = await get_glossary_client().entities_by_ids_or_raise(
            work.book_id, [str(_target)])
    except GlossaryClientError as exc:
        # The THIRD branch, and the reason the raising variant is used instead of the
        # degrade-safe one: "I could not ask" is not "it is not there". Refusing keeps today's
        # bug from surviving an outage, and naming it separately means the caller is never told
        # its argument was invalid when the truth is that the check could not run.
        logger.warning("override target check unavailable (book=%s): %s", work.book_id, exc)
        return {"success": False, "error": (
            "TARGET_UNVERIFIED — could not confirm that this entity exists, because "
            "glossary-service did not answer. NOTHING WAS WRITTEN and the argument may well be "
            "fine; this is an availability failure, not a rejection. Retry shortly."
        )}
    if not any(str(e.get("entity_id")) == str(_target) for e in _known):
        return {"success": False, "error": (
            "TARGET_NOT_IN_THIS_BOOK — no such entity in the book this derivative belongs to. An "
            "override must point at an entity of its own book; find the right id with "
            "glossary_search on that book and pass the entity_id it returns."
        )}
    derivatives = DerivativesRepo(get_pool())
    try:
        ov = await derivatives.add_override(
            work.id, work.book_id, tc.user_id, _target, args.overridden_fields,
        )
    except asyncpg.UniqueViolationError:
        return {"success": False, "error": "OVERRIDE_EXISTS — an override for this entity already exists; update it instead"}
    except ReferenceViolationError as exc:
        raise uniform_not_accessible(exc) from exc
    out = {"success": True, "override": _override_out(ov)}
    out["_meta"] = {"undo_hint": _undo(
        "composition_entity_override_delete", project_id=args.project_id, override_id=str(ov.id),
    )}
    return out


class _EntityOverrideUpdateArgs(ForbidExtra):
    project_id: str  # the DERIVATIVE Work's project_id
    override_id: str
    overridden_fields: dict[str, Any] = {}


@mcp_server.tool(
    name="composition_entity_override_update",
    description=(
        "Replace an entity override's field-set on a what-if derivative (dị bản) — the whole "
        "overridden_fields JSON is replaced (the override IS the delta). Pass the derivative's "
        "project_id + the override_id. EDIT required (auto-applied; Undo restores the prior fields)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit dị bản override", "update entity override", "change override fields"],
        visibility="legacy", superseded_by="composition_entity_override_edit",  # S3
        tool_name="composition_entity_override_update",
    ),
)
async def composition_entity_override_update(ctx: MCPContext, args: _EntityOverrideUpdateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _require_derivative(works, tc, _uuid(args.project_id, "project_id"))
    derivatives = DerivativesRepo(get_pool())
    prior = await derivatives.get_override(work.id, work.book_id, _uuid(args.override_id, "override_id"))  # for Undo
    if prior is None:
        raise uniform_not_accessible()
    ov = await derivatives.update_override(
        work.id, work.book_id, _uuid(args.override_id, "override_id"), args.overridden_fields,
    )
    if ov is None:
        raise uniform_not_accessible()
    out = {"success": True, "override": _override_out(ov)}
    out["_meta"] = {"undo_hint": _undo(
        "composition_entity_override_update", project_id=args.project_id,
        override_id=args.override_id, overridden_fields=prior.overridden_fields,
    )}
    return out


class _EntityOverrideDeleteArgs(ForbidExtra):
    project_id: str  # the DERIVATIVE Work's project_id
    override_id: str


@mcp_server.tool(
    name="composition_entity_override_delete",
    description=(
        "Delete an entity override from a what-if derivative (dị bản) — reverts that entity to "
        "canon (a pure delta, no history preserved). Pass the derivative's project_id + the "
        "override_id. EDIT required (auto-applied; Undo re-adds it)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["remove dị bản override", "delete entity override", "revert override to canon"],
        visibility="legacy", superseded_by="composition_entity_override_edit",  # S3
        tool_name="composition_entity_override_delete",
    ),
)
async def composition_entity_override_delete(ctx: MCPContext, args: _EntityOverrideDeleteArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _require_derivative(works, tc, _uuid(args.project_id, "project_id"))
    derivatives = DerivativesRepo(get_pool())
    prior = await derivatives.get_override(work.id, work.book_id, _uuid(args.override_id, "override_id"))  # for Undo
    if prior is None:
        raise uniform_not_accessible()
    ok = await derivatives.delete_override(work.id, work.book_id, _uuid(args.override_id, "override_id"))
    if not ok:
        raise uniform_not_accessible()
    out = {"success": True, "deleted": True}
    out["_meta"] = {"undo_hint": _undo(
        "composition_entity_override_add", project_id=args.project_id,
        target_entity_id=str(prior.target_entity_id), overridden_fields=prior.overridden_fields,
    )}
    return out


@mcp_server.tool(
    name="composition_entity_override_restore",
    description=(
        "Restore a soft-deleted entity override on a what-if derivative (dị bản) — the UNDO the "
        "delete promises. Pass the derivative's project_id + the override_id. Fails if a newer "
        "override for that same entity now exists. EDIT required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["restore entity override", "undo entity override delete"],
        visibility="legacy", superseded_by="composition_entity_override_edit",
        tool_name="composition_entity_override_restore",
    ),
)
async def composition_entity_override_restore(ctx: MCPContext, args: _EntityOverrideDeleteArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    work = await _require_derivative(works, tc, _uuid(args.project_id, "project_id"))
    derivatives = DerivativesRepo(get_pool())
    if not await derivatives.restore_override(work.id, work.book_id, _uuid(args.override_id, "override_id")):
        return {"success": False, "error": (
            "that override could not be restored — it was never deleted, or a newer override for "
            "the same entity now exists")}
    return {"restored": True, "override_id": args.override_id}


def _override_out(ov) -> dict:
    return {
        "id": str(ov.id),
        "target_entity_id": str(ov.target_entity_id),
        "overridden_fields": ov.overridden_fields,
    }


# ── D-A-REQUIRED-ID-NO-TOOL-CAN-SUPPLY — THE READER THAT WAS MISSING.
#
# 🔴 composition_reference_update REQUIRES `reference_id`, and it was the ONLY tool of the 315 in
# the federated catalogue that mentioned `reference_id` ANYWHERE — schema or description. Nothing
# could produce one, so the tool was unsatisfiable through MCP by construction. Re-verified
# 2026-08-25, still true before this tool existed.
#
# The platform's own refusal said so correctly and completely: "'composition_reference_update' is
# missing required argument(s): ['reference_id'], and this tool does not declare which side
# supplies them — so do NOT guess a value." There WAS no side that supplied them.
#
# This is the STRONGEST form of the supplier-chain class, and the one no declaration can fix: the
# loop has twice repaired a DECLARATION gap (an id whose declaration named no supplier; a chain
# whose middle link was named but not its first). No amount of wording points at a tool that does
# not exist. The data was never missing — GET /works/{project_id}/references has served this
# shelf to the FE all along; it simply had no MCP surface.
#
# READ-ONLY, VIEW-gated, and `content` is deliberately NOT projected: a reference is an external
# passage an author pasted in, so a list that returned bodies would dump a corpus into the turn.
# Title/author/source_url are what `composition_reference_update` edits and what a human names
# when they ask, so they are what a caller needs to pick the right id.
@mcp_server.tool(
    name="composition_reference_list",
    description=(
        "List the reference SOURCES on a Work's shelf — the external passages an author added as "
        "influences (title / author / source_url), newest first. This is where a reference_id "
        "comes from: match the one you want by title, then pass its id to "
        "composition_reference_update. Bodies are never returned, only metadata. VIEW on the "
        "book. NOT the same as composition_find_references, which finds where an ENTITY appears "
        "in the spec."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["list references", "my references", "reference shelf", "what references do I have",
                  "reference sources", "show reference library"],
        tool_name="composition_reference_list",
    ),
)
async def composition_reference_list(
    ctx: MCPContext,
    project_id: Annotated[str, "the Work whose reference shelf to list (UUID)"],
    limit: Annotated[int, "1..100"] = 50,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
    rows = await ReferencesRepo(get_pool()).list(pid)
    capped = max(1, min(100, limit))
    shown = rows[:capped]
    # `total` is EXACT rather than a `more` flag: the repo hands back the whole shelf, so a
    # limit+1 probe would be strictly less information than we already hold. K25's rule is that a
    # capped slice must never read as the whole set — this states the whole set outright.
    return {
        "references": [
            {
                "reference_id": str(r.id),
                "title": r.title,
                "author": r.author,
                "source_url": r.source_url,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                # The body's SIZE, never the body. Enough to tell a stub from a real passage.
                "content_chars": len(r.content or ""),
            }
            for r in shown
        ],
        "returned": len(shown),
        "total": len(rows),
        "guidance": (
            f"showing {len(shown)} of {len(rows)} — raise `limit` to see the rest. Do NOT assume "
            "this is all of them."
            if len(rows) > len(shown)
            else f"complete — all {len(rows)} reference(s) on this Work's shelf."
        ),
    }


# ── S-03: reference-shelf METADATA edit (agent parity). Metadata-only — editing a
#    reference's CONTENT via MCP is deliberately OUT OF SCOPE (an agent re-authoring a
#    whole corpus is not a wanted capability; agents ADD references via create). The
#    `content` field is not on the args model, so ForbidExtra rejects it at construction.
class _ReferenceUpdateArgs(ForbidExtra):
    project_id: str
    reference_id: str
    title: str | None = None
    author: str | None = None
    source_url: str | None = None


@mcp_server.tool(
    name="composition_reference_update",
    description=(
        "Edit a reference's METADATA — title / author / source_url. A cheap column write; "
        "it does NOT re-embed (fixing a typo must not pay for a re-embed). Only the fields you "
        "pass change. EDIT required (auto-applied; Undo restores the prior values). Editing a "
        "reference's CONTENT is not available here (add references via the create path)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit reference", "update reference metadata", "fix reference title", "rename reference source"],
        tool_name="composition_reference_update",
    ),
)
async def composition_reference_update(ctx: MCPContext, args: _ReferenceUpdateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    refs = ReferencesRepo(get_pool())
    rid = _uuid(args.reference_id, "reference_id")
    prior = await refs.get(pid, rid)  # 404 + prior for the Undo
    if prior is None:
        raise uniform_not_accessible()
    fs = args.model_fields_set
    kwargs = {col: (getattr(args, col) or "") for col in ("title", "author", "source_url") if col in fs}
    ref = await refs.update_metadata(pid, rid, **kwargs)
    if ref is None:
        raise uniform_not_accessible()
    undo_fields = {col: getattr(prior, col) for col in kwargs}  # restore prior metadata
    out = {"success": True, "reference": ref.model_dump(mode="json")}
    out["_meta"] = {"undo_hint": _undo(
        "composition_reference_update", project_id=args.project_id, reference_id=args.reference_id,
        **undo_fields,
    ) if undo_fields else None}
    return out


class _SwitchActiveWorkArgs(ForbidExtra):
    book_id: str
    # The Work to make active for this book; null switches back to the canonical Work.
    project_id: str | None = None


@mcp_server.tool(
    name="composition_switch_active_work",
    description=(
        "Set the ACTIVE Work (dị bản) for a book — the per-user, per-book preference the studio "
        "follows (which Work the editor + panels resolve to). Pass project_id = the derivative to "
        "switch onto, or null to switch back to the canonical Work. Reversible + cheap (auto-applied, "
        "no confirm). EDIT on the book. The open studio re-resolves live (Lane-B)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["switch to dị bản", "set active work", "switch branch", "make active", "switch to derivative", "activate branch"],
        tool_name="composition_switch_active_work",
    ),
)
async def composition_switch_active_work(ctx: MCPContext, args: _SwitchActiveWorkArgs) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(args.book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    target: str | None = None
    if args.project_id is not None:
        # Never point active-work at a foreign/nonexistent Work — it must belong to THIS book.
        works = WorksRepo(get_pool())
        w = await works.get(_uuid(args.project_id, "project_id"))
        if w is None or w.book_id != bid:
            return {"success": False, "error": "NOT_A_WORK_OF_THIS_BOOK"}
        target = str(w.project_id) if w.project_id else args.project_id
    from app.clients.auth_prefs_client import (
        AuthPrefsError, get_user_preference, set_user_preference,
    )
    pref_key = f"lw_active_work.{bid}"  # the SAME key the FE's useActiveWorkId reads
    # Capture the PRIOR active-work FIRST so Undo restores exactly it (not always canonical) —
    # best-effort: a read failure just falls back to canonical (project_id=None) in the hint.
    try:
        prior = await get_user_preference(tc.user_id, pref_key)
    except AuthPrefsError:
        prior = None
    try:
        await set_user_preference(tc.user_id, pref_key, target)
    except AuthPrefsError:
        return {"success": False, "error": "PREF_WRITE_UNAVAILABLE"}
    return {
        "success": True, "book_id": str(bid), "active_project_id": target,
        # C-ACTIVITY: a STRUCTURED {tool,args} hint — a bare STRING is silently dropped by
        # chat-service `tool_undo_hint` (isinstance dict check), so the Undo affordance vanished.
        "_meta": {"undo_hint": _undo(
            "composition_switch_active_work", book_id=str(bid),
            project_id=prior if isinstance(prior, str) else None)},
    }


@mcp_server.tool(
    name="composition_canon_rule_create",
    description=(
        "Add a canon rule (an invariant the critic enforces) to a Work. Returns the "
        "rule. EDIT required (auto-applied; Undo deletes the rule)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["add canon rule", "new invariant", "add constraint", "declare lore rule"],
        visibility="legacy", superseded_by="composition_canon_rule_edit",  # S3
        tool_name="composition_canon_rule_create",
    ),
)
async def composition_canon_rule_create(ctx: MCPContext, args: _CanonRuleCreateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    if args.from_order is not None and args.until_order is not None and args.from_order > args.until_order:
        return {"success": False, "error": "from_order must not exceed until_order"}
    canon = CanonRulesRepo(get_pool())
    # K13 (2026-07-23) — idempotency guard against an agent double-fire, same shape as the
    # arc/N6 guards. LIVE-PROBED: two byte-identical calls made TWO canon rules, and
    # `canon_rule` carries no natural-key unique (only the PK). Keyed on the rule TEXT
    # within the project + scope, which is what "the same rule" means here; a
    # deliberately-repeated text under a different scope/entity still creates.
    if (args.text or "").strip():
        dup = await canon.find_by_text(
            pid, args.text.strip(), scope=args.scope,
            entity_id=_uuid(args.entity_id, "entity_id") if args.entity_id else None,
        )
        if dup is not None:
            out = dup.model_dump(mode="json")
            out["_meta"] = {"undo_hint": _undo(
                "composition_canon_rule_delete", project_id=args.project_id, rule_id=str(dup.id),
            )}
            out["note"] = "this canon rule already exists — returning it instead of duplicating."
            return out
    rule = await canon.create(
        pid, args.text, scope=args.scope,
        entity_id=_uuid(args.entity_id, "entity_id") if args.entity_id else None,
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
        visibility="legacy", superseded_by="composition_canon_rule_edit",  # S3
        tool_name="composition_canon_rule_update",
    ),
)
async def composition_canon_rule_update(ctx: MCPContext, args: _CanonRuleUpdateArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    canon = CanonRulesRepo(get_pool())
    rule_id = _uuid(args.rule_id, "rule_id")
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
        visibility="legacy", superseded_by="composition_canon_rule_edit",  # S3
        tool_name="composition_canon_rule_delete",
    ),
)
async def composition_canon_rule_delete(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    rule_id: Annotated[str, "The canon rule id. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    canon = CanonRulesRepo(get_pool())
    # Project-scope BEFORE mutating: canon.archive targets by id only, so
    # confirm the rule is in the gated Work's project first (else a rule from
    # another Work would be archived under THIS book's gate). See node_update.
    prior = await canon.get(pid, _uuid(rule_id, "rule_id"))
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    rule = await canon.archive(pid, _uuid(rule_id, "rule_id"))
    if rule is None:
        raise uniform_not_accessible()
    out = rule.model_dump(mode="json")
    # BE-11c — the reverse op now EXISTS (composition_canon_rule_restore), so the
    # undo_hint is real, not None. The agent gains the same undo the human's
    # "Rule archived · Undo" toast offers.
    out["_meta"] = {
        "undo_hint": {
            "tool": "composition_canon_rule_restore",
            "args": {"project_id": project_id, "rule_id": rule_id},
        }
    }
    return out


@mcp_server.tool(
    name="composition_canon_rule_restore",
    description=(
        "Un-archive a soft-deleted canon rule — the reverse of "
        "composition_canon_rule_delete. EDIT required (auto-applied)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["restore canon rule", "un-archive rule", "undo delete rule"],
        visibility="legacy", superseded_by="composition_canon_rule_edit",  # S3
        tool_name="composition_canon_rule_restore",
    ),
)
async def composition_canon_rule_restore(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    rule_id: Annotated[str, "The canon rule id (from the delete response). (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    canon = CanonRulesRepo(get_pool())
    # restore() is natively project-scoped (WHERE project_id = $1 AND id = $2 AND
    # is_archived), so it can never un-archive a rule under a different book's gate,
    # and returns None (→ not-accessible) for a non-archived or foreign rule.
    rule = await canon.restore(pid, _uuid(rule_id, "rule_id"))
    if rule is None:
        raise uniform_not_accessible()
    return rule.model_dump(mode="json")


# ── S-01 · structure-template authoring (per-USER; agent parity for the human routes) ──


def _st_clean_name(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    if not s:
        raise ValueError("name must not be blank")
    return s[:200]


class _StructTemplateCreateArgs(ForbidExtra):
    name: str
    kind: str = "generic"  # free-text label (S-01 CV-1), NOT an enum
    beats: list[dict[str, Any]] = []

    @field_validator("name")
    @classmethod
    def _v(cls, v: str) -> str:
        return _st_clean_name(v)  # type: ignore[return-value]


class _StructTemplateCloneArgs(ForbidExtra):
    template_id: str
    name: str | None = None

    @field_validator("name")
    @classmethod
    def _v(cls, v: str | None) -> str | None:
        return _st_clean_name(v)


class _StructTemplateUpdateArgs(ForbidExtra):
    template_id: str
    expected_version: int
    name: str | None = None
    kind: str | None = None
    beats: list[dict[str, Any]] | None = None

    @field_validator("name")
    @classmethod
    def _v(cls, v: str | None) -> str | None:
        return _st_clean_name(v)


class _StructTemplateIdArgs(ForbidExtra):
    template_id: str


@mcp_server.tool(
    name="composition_structure_template_create",
    description=(
        "Create a custom STORY STRUCTURE in your library — a named ordered list of beats you can "
        "decompose a book against (like the built-in Save the Cat / Hero's Journey). Owned by you; "
        "built-ins are read-only, clone one to customise it."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["create story structure", "new structure template", "author a beat sheet",
                  "define a custom structure"],
        visibility="legacy", superseded_by="composition_structure_template_edit",  # S3
        tool_name="composition_structure_template_create",
    ),
)
async def composition_structure_template_create(ctx: MCPContext, args: _StructTemplateCreateArgs) -> dict:
    tc = _ctx(ctx)
    repo = StructureTemplatesRepo(get_pool())
    try:
        t = await repo.create(tc.user_id, name=args.name, kind=args.kind, beats=args.beats)
    except DuplicateStructureTemplateName:
        return {"success": False, "outcome": "applied_conflict",
                "error": f"you already have a structure named '{args.name}'"}
    return t.model_dump(mode="json")


@mcp_server.tool(
    name="composition_structure_template_clone",
    description=(
        "Clone a built-in (or any visible) story structure into YOUR library so you can edit it — "
        "a user never edits a built-in in place. Returns the new own copy."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["clone structure", "copy a story structure", "customise a built-in structure"],
        visibility="legacy", superseded_by="composition_structure_template_edit",  # S3
        tool_name="composition_structure_template_clone",
    ),
)
async def composition_structure_template_clone(ctx: MCPContext, args: _StructTemplateCloneArgs) -> dict:
    tc = _ctx(ctx)
    repo = StructureTemplatesRepo(get_pool())
    try:
        t = await repo.clone_builtin(tc.user_id, _uuid(args.template_id, "template_id"), name=args.name)
    except LookupError:
        raise uniform_not_accessible()
    except DuplicateStructureTemplateName:
        return {"success": False, "outcome": "applied_conflict", "error": "name already in your library"}
    return t.model_dump(mode="json")


@mcp_server.tool(
    name="composition_structure_template_update",
    description=(
        "Edit one of YOUR structure templates (name / kind / beats). OCC: pass expected_version; a "
        "stale version is rejected. Built-ins are read-only (clone first)."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["edit story structure", "update structure template", "change beats"],
        visibility="legacy", superseded_by="composition_structure_template_edit",  # S3
        tool_name="composition_structure_template_update",
    ),
)
async def composition_structure_template_update(ctx: MCPContext, args: _StructTemplateUpdateArgs) -> dict:
    tc = _ctx(ctx)
    repo = StructureTemplatesRepo(get_pool())
    patch = {k: v for k, v in (("name", args.name), ("kind", args.kind), ("beats", args.beats)) if v is not None}
    try:
        t = await repo.update(tc.user_id, _uuid(args.template_id, "template_id"), args.expected_version, **patch)
    except StructureTemplateVersionConflict:
        return {"success": False, "outcome": "applied_conflict", "error": "structure was modified; reload"}
    except DuplicateStructureTemplateName:
        return {"success": False, "outcome": "applied_conflict", "error": "name already in your library"}
    if t is None:
        raise uniform_not_accessible()
    return t.model_dump(mode="json")


@mcp_server.tool(
    name="composition_structure_template_archive",
    description="Archive one of YOUR structure templates (soft — restore brings it back).",
    meta=require_meta(
        "A", "user",
        synonyms=["archive structure", "delete story structure", "remove structure template"],
        visibility="legacy", superseded_by="composition_structure_template_edit",  # S3
        tool_name="composition_structure_template_archive",
    ),
)
async def composition_structure_template_archive(ctx: MCPContext, args: _StructTemplateIdArgs) -> dict:
    tc = _ctx(ctx)
    repo = StructureTemplatesRepo(get_pool())
    t = await repo.archive(tc.user_id, _uuid(args.template_id, "template_id"))
    if t is None:
        raise uniform_not_accessible()
    return t.model_dump(mode="json")


@mcp_server.tool(
    name="composition_structure_template_restore",
    description="Restore an archived structure template of YOURS (reverse of archive).",
    meta=require_meta(
        "A", "user",
        synonyms=["restore structure", "unarchive story structure"],
        visibility="legacy", superseded_by="composition_structure_template_edit",  # S3
        tool_name="composition_structure_template_restore",
    ),
)
async def composition_structure_template_restore(ctx: MCPContext, args: _StructTemplateIdArgs) -> dict:
    tc = _ctx(ctx)
    repo = StructureTemplatesRepo(get_pool())
    t = await repo.restore(tc.user_id, _uuid(args.template_id, "template_id"))
    if t is None:
        raise uniform_not_accessible()
    return t.model_dump(mode="json")


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
    pid = _uuid(args.project_id, "project_id")
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)
    book: BookClient = get_book_client()
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    chap = _uuid(args.chapter_id, "chapter_id")
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
    return {"success": False, "error": "book-service unavailable",
            "detail": {"upstream_status": exc.status}}


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
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    chapter_id: Annotated[str, "The chapter to publish (canonize). (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    # Publishing is an authoring (write) action → EDIT.
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)
    # Surface the publish-gate up front so the LLM/user sees WHY if it isn't
    # publishable (the confirm route re-checks it at execute time).
    outline = OutlineRepo(get_pool())
    chap = _uuid(chapter_id, "chapter_id")
    gate = await outline.chapter_scene_gate(pid, chap)
    if not gate.get("can_publish"):
        # TOOLV2 LOOP #216 — the gate rides under `detail`, which is the ONLY structured
        # channel the C4 error body forwards ({message, code, detail}). Returned under its
        # own key it was dropped at the kit boundary, so the comment above -- "surface the
        # publish-gate up front so the LLM/user sees WHY" -- was defeated: the caller got
        # "chapter is not publishable yet" and no counts to act on.
        return {
            "success": False,
            "error": "chapter is not publishable yet",
            "detail": gate,
        }
    # Mint a confirm token binding (user, resource=chapter, descriptor, payload).
    # The payload captures the exact target so confirm executes what was proposed.
    payload = {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "book_id": str(meta.book_id),
    }
    _title = "Publish chapter (canonize the reviewed draft)"

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret,
            tc.user_id, chap, _PUBLISH_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _PUBLISH_DESCRIPTOR,
            "title": _title,
            "domain": "composition",
        }

    # Durable ext-tasks gate for a tasks-capable client, else today's confirm_token
    # (a non-tasks client is never handed a task it can't drive).
    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_PUBLISH_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": _title, "descriptor": _PUBLISH_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


@mcp_server.tool(
    name="composition_decompile_arcs",
    description=(
        "PROPOSE decompiling a flat/imported book into a spec ARC layer: group the book's chapters "
        "into size-aligned arcs (~`chapters_per_arc` each) so a book with no plan gets a browsable "
        "arc structure. Deterministic and $0 (no LLM) — but it MUTATES structure, so it is "
        "confirm-gated: it returns a `confirm_token` + a dry-run count (how many arcs it would "
        "create); nothing is written until the user confirms via confirm_action. Idempotent "
        "(re-running reuses existing decompiled arcs by position). EDIT required."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["decompile arcs", "auto-arc", "group chapters into arcs", "arc layer from chapters"],
        tool_name="composition_decompile_arcs",
    ),
)
async def composition_decompile_arcs(
    ctx: MCPContext,
    book_id: Annotated[str, "The book to decompile (UUID)."],
    chapters_per_arc: Annotated[int, "Target chapters per arc (default 10)."] = 10,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    # Dry-run count so the confirm card is informative (M chapters → ~N arcs). Cheap, and it also
    # gives a clean "nothing to decompile" answer up front for a book with no chapters.
    per = max(1, int(chapters_per_arc))
    n_chapters = await get_pool().fetchval(
        "SELECT count(*) FROM outline_node WHERE book_id=$1 AND kind='chapter' AND NOT is_archived", bid,
    ) or 0
    would_arcs = (int(n_chapters) + per - 1) // per  # integer ceil
    # 🔴 D-EXTRACTION-CONFIRMS-A-NO-OP. The comment above says the dry-run "gives a clean
    # 'nothing to decompile' answer up front for a book with no chapters" — and it did not. The
    # count was computed, found to be 0, and a confirm_token was minted anyway, so the author was
    # asked to approve a card whose own title read "Decompile 0 chapter(s) into ~0 arc(s)".
    #
    # MEASURED 2026-08-14 on a book with 3 chapters where this legitimately reads 0: the chapters
    # were created through book_chapter_create, which does not mint the `outline_node` rows this
    # engine groups (an IMPORTED book gets them from scene_decompile at import time). So the zero
    # was correct and the card was still offered. Whatever the reason for the zero, approving it
    # can only produce the engine's own {"arcs": 0, "reason": "no chapters to decompile"}.
    #
    # Returning that reason WITHOUT a token is the same answer the engine would give, minus a
    # pointless confirmation. It also stops a no-op consuming the confirm surface, which is what
    # made this class worth a name the first time.
    if would_arcs == 0:
        return {
            "outcome": "no_op",
            "descriptor": _DECOMPILE_DESCRIPTOR,
            "domain": "composition",
            "arcs": 0,
            "chapters_assigned": 0,
            "reason": "no chapters to decompile",
            "guidance": (
                "This book has no chapter rows in the spec outline, so there is nothing to group "
                "into arcs and no confirmation is needed. An IMPORTED book gets those rows from "
                "the import pipeline; a book whose chapters were created directly does not have "
                "them yet."
            ),
        }
    payload = {"book_id": book_id, "chapters_per_arc": per}
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, bid, _DECOMPILE_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _DECOMPILE_DESCRIPTOR,
        "title": f"Decompile {int(n_chapters)} chapter(s) into ~{would_arcs} arc(s)",
        "domain": "composition",
        "dry_run": {"chapters": int(n_chapters), "would_create_arcs": would_arcs},
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
    # 🔴 D-UNDECLARED-REF-BECOMES-A-PLACEHOLDER. This was a bare `str` with no description, so
    # the model had nothing telling it what a model_ref IS. Measured 2026-08-14, K=5: it sent
    # `model_ref="default"` on 5 of 5 runs, a Tier-A card was minted for every one, and the
    # confirm effect does `UUID(str(model_ref_raw))` — so approving produced a bare 400
    # `action_error`. Approve-then-fail, on the most expensive tool on the platform.
    #
    # Naming the UUID here is not decoration: it is the only declaration the runtime has. The
    # chat-service argument guard reads exactly this text (no provider emits `format: uuid`), so
    # stating it lets a placeholder be DROPPED before a card is minted, and naming the supplier
    # tells the model where to get the real value instead of inventing one.
    model_ref: Annotated[
        str,
        Field(description=(
            "The model's id (UUID). NOT a name, an alias, or 'default' — list the caller's "
            "models with settings_list_models and pass the `model_ref` from there. Which list "
            "depends on model_source: user_model = the author's own models, platform_model = "
            "the platform's."
        )),
    ]
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
        "book draft). This is DISTINCT from book_chapter_save_draft, which only SAVES "
        "text you wrote yourself: this invokes the canon-grounded drafter+critic engine "
        "and SPENDS LLM tokens, so it is cost-gated — it returns a `confirm_token` + "
        "descriptor and generates NOTHING until the user confirms via confirm_action. "
        "Pass EXACTLY ONE of outline_node_id / chapter_id. EDIT on the book required. "
        "For a chapter, first build its outline (a chapter node + at least one scene "
        "node) with composition_outline_node_edit (op=\"create\")."
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
    pid = _uuid(args.project_id, "project_id")
    # Generation is a write/spend → EDIT (mirrors the engine's E0-4c pack tier).
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)

    target_kind = "scene" if has_scene else "chapter"
    target_id = args.outline_node_id if has_scene else args.chapter_id
    # Light propose-time validation for the SCENE target: the node must exist + be in
    # the gated Work's project (the same project-scope guard the other by-id
    # handlers apply). The CHAPTER target is validated at confirm by the engine
    # (it needs book-service to resolve the chapter sort/plan).
    if not has_scene:
        # 🔴 THE CHAPTER TARGET WAS VALIDATED NOWHERE AT PROPOSE, and the comment that used to sit
        # here said so deliberately: "The CHAPTER target is validated at confirm by the engine (it
        # needs book-service to resolve the chapter sort/plan)." Measured 2026-08-24 over MCP,
        # each of these MINTED A COST-BEARING CARD: a chapter_id that does not exist, and a
        # chapter belonging to a DIFFERENT book. Approve-then-fail on the most expensive tool on
        # the platform — the same sentence D-UNDECLARED-REF wrote about this tool's model_ref.
        #
        # I had filed the fix as an owner decision (DQ-T42) on the grounds that existence needs
        # book-service, which would make it a choice about fail-open vs fail-closed during an
        # outage. That premise was wrong. The engine's own chapter path opens with:
        #
        #     scenes = await outline.scenes_for_chapter(project_id, chapter_id)
        #     if not scenes:
        #         raise HTTPException(400, {"code": "NO_CHAPTER_PLAN", ...})
        #
        # so a chapter with no scene plan cannot be generated AT ALL. Non-empty scenes is a
        # necessary precondition of the operation, the query is LOCAL to this service, and it is
        # scoped by project_id — so there is no cross-service degrade to decide. It refuses
        # exactly what the confirm would refuse, one stage earlier and before the author is asked
        # to approve a spend.
        #
        # Both failing bars fall to the same predicate: a chapter that does not exist has no
        # scenes in this project, and another book's chapter has no scenes in THIS project.
        # Read `args.chapter_id`, not the `target_id` alias: test_uuid_errors_name_the_field
        # asserts every site NAMES the field it READS, and it caught this one naming "chapter_id"
        # while reading target_id. Reading the real argument is both what the guard wants and
        # what makes the error message true for the caller.
        _scenes = await OutlineRepo(get_pool()).scenes_for_chapter(
            pid, _uuid(args.chapter_id, "chapter_id"))
        if not _scenes:
            raise ValueError(
                "chapter has no scene plan in this Work — nothing to generate from. Either the "
                "chapter belongs to a different book, or it has not been decomposed yet: run the "
                "decompose step first, or pass outline_node_id to generate a single scene.")
    if has_scene:
        outline = OutlineRepo(get_pool())
        node = await outline.get_node(_uuid(target_id, "target_id"))
        if node is None or node.project_id != pid:
            raise uniform_not_accessible()
        # D-SCENE-PROSE-NOWHERE-TO-LAND — a scene generate does NOT persist (only the
        # chapter target passes persist=True); it returns candidates for the author to
        # accept in the compose panel. That panel resolves a chapter's scenes by
        # `chapter_id` (`useChapterScenes`, and `outline.scenes_for_chapter` server-side),
        # so a scene with a NULL `chapter_id` can never be shown — and NULL is the NORMAL
        # state of a planned node (the migration notes 7/7 in the live DB). Bootstrap is
        # what stamps it, when it materialises a planned chapter into a real one.
        #
        # Generating anyway spends REAL tokens on prose the author can never reach.
        # Measured on the Mị Đế book: 783 words of good Vietnamese prose generated,
        # job `completed`, and the compose panel said "Chưa có cảnh". Nothing failed
        # loudly; the work simply did not exist. Refuse at PROPOSE — before the confirm
        # gate, before a single token is billed — and name the step that fixes it.
        if node.chapter_id is None:
            # C4 refusal shape: `error` IS the message the model reads (loreweave_mcp's
            # `failure_message` builds `{"message": str(payload["error"])}` and carries
            # `code` alongside). A `message` key would be DROPPED — which is how the
            # first cut of this guard surfaced as a bare "scene_has_no_chapter" with all
            # of its guidance stripped, caught only by calling the live endpoint.
            return {
                "success": False,
                "code": "scene_has_no_chapter",
                "error": (
                    f"'{node.title or target_id}' is a PLANNED scene with no manuscript "
                    "chapter behind it (chapter_id is null), so generated prose would have "
                    "nowhere to go — the compose panel lists a chapter's scenes by "
                    "chapter_id and would not show it. NOT generating, so no tokens are "
                    "spent. Materialise the chapter first (PlanForge bootstrap: propose → "
                    "approve → apply, which creates the book chapter and stamps chapter_id "
                    "onto its scenes), then generate. To draft a whole chapter that IS "
                    "materialised, call this tool with chapter_id instead."
                ),
            }

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
    summary = (f"generate a {target_kind} with the cowrite engine "
               f"(model {args.model_source}/{args.model_ref})")

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret,
            tc.user_id, _uuid(target_id, "target_id"), _GENERATE_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _GENERATE_DESCRIPTOR,
            "title": summary,
            "domain": "composition",
            "requires": "human confirmation via the review surface — this spends LLM "
                        "tokens; nothing is generated until confirmed",
        }

    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_GENERATE_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": summary, "descriptor": _GENERATE_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


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
    book_id = _uuid(args.book_id, "book_id")
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
    book_id = _uuid(args.book_id, "book_id")
    # OQ-3: run reads widen to the book grant — gate FIRST (PM-8 ordering), then
    # the un-owner-scoped get; the run must be in THIS book (H13 on a mismatch).
    await _gate(tc, book_id, GrantLevel.VIEW)
    run_id = _uuid(args.run_id, "run_id")
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
        visibility="legacy", superseded_by="composition_authoring_run_manage",  # S3
        tool_name="composition_authoring_run_create",
    ),
)
async def composition_authoring_run_create(
    ctx: MCPContext, args: _AuthoringRunCreateArgs,
) -> dict:
    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    await _gate(tc, book_id, GrantLevel.EDIT)
    # 🔴 APPROVE-THEN-FAIL. Until 2026-08-24 this minted a confirm-token for ANY plan_run_id and
    # only looked it up in the ACCEPT effect, where a miss becomes LookupError("plan run not
    # found") -> HTTPException(400, {"code": "action_error"}) with the message discarded. So the
    # author was shown a cost-bearing approval card for a run that could not be created, approved
    # it, and got a bare 400. Measured on 5 of 5 runs (batch c-authrun2) and 2 of 2 (c-authrun4).
    #
    # Same class as D-UNDECLARED-REF on composition_generate's model_ref — "Approve-then-fail, on
    # the most expensive tool on the platform" — and the same remedy: refuse at PROPOSE, and name
    # the supplier so the refusal is actionable. This can never block a call that would have
    # worked: the accept does the identical lookup, so a run this rejects is one the accept would
    # have rejected a human decision later.
    from app.db.repositories.plan_runs import PlanRunsRepo

    plan_run_uuid = _uuid(args.plan_run_id, "plan_run_id")
    if await PlanRunsRepo(get_pool()).get_for_book(book_id, plan_run_uuid) is None:
        raise ValueError(
            f"no plan run {args.plan_run_id} on this book — plan_run_id must be a PLAN run of "
            f"this same book. Read the book's existing plan runs from "
            f"composition_package_tree's `runs.recent`; only if the book has no plan at all does "
            f"plan_propose_spec create one. It is not the authoring run's own id and never a "
            f"chapter id."
        )
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
    _title = (
        f"Create a level-{args.level} autonomous authoring run "
        f"(budget ${args.budget_usd}, {len(args.scope)} chapter(s), "
        f"pause_after_each_unit={args.pause_after_each_unit})"
    )

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret,
            tc.user_id, book_id, _AUTHORING_RUN_CREATE_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _AUTHORING_RUN_CREATE_DESCRIPTOR,
            "title": _title,
            "domain": "composition",
            "requires": "human confirmation via the review surface — no chapters are "
                        "drafted at create time, but the run holds the book's active-run "
                        "slot until closed",
        }

    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_AUTHORING_RUN_CREATE_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": _title, "descriptor": _AUTHORING_RUN_CREATE_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


class _AuthoringRunIdArgs(TolerantArgs):
    book_id: str
    # 🔴 A REQUIRED ID WITH NO DESCRIPTION IS AN ID THE REFUSAL CANNOT EXPLAIN. `run_id` was bare,
    # so chat-service's missing-argument refusal fell to its "this tool does not declare which side
    # supplies them" arm, named no supplier, and therefore armed none — measured 2026-08-22:
    # composition_authoring_run_list was advertised on 0 of 5 runs and called 0 of 5. Two of those
    # five turns minted a Tier-A card carrying a run_id matching no run, for a book that had zero.
    # Platform-wide at that date: 105 of 467 required arguments carry an empty description, 75 of
    # them id-shaped.
    run_id: Annotated[str, Field(description=(
            "the authoring run to act on (UUID). NOT a name and NOT yours to invent — list the "
            "book's runs with composition_authoring_run_list and pass the id it returns. A book "
            "may have NONE, and 'there are no runs' is the correct answer when it does: a "
            "structurally valid id that matches no run is the worst outcome, because the card it "
            "mints looks exactly like a real one."
    ))]


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
        visibility="legacy", superseded_by="composition_authoring_run_manage",  # S3
        tool_name="composition_authoring_run_gate",
    ),
)
async def composition_authoring_run_gate(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = _uuid(args.run_id, "run_id")
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload = {"book_id": args.book_id, "run_id": args.run_id}
    _title = "Run the start-gate check (draft → gated)"

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret,
            tc.user_id, run_id, _AUTHORING_RUN_GATE_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _AUTHORING_RUN_GATE_DESCRIPTOR,
            "title": _title,
            "domain": "composition",
            "requires": "human confirmation — a failing gate check is reported at confirm time",
        }

    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_AUTHORING_RUN_GATE_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": _title, "descriptor": _AUTHORING_RUN_GATE_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


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
        visibility="legacy", superseded_by="composition_authoring_run_manage",  # S3
        tool_name="composition_authoring_run_start",
    ),
)
async def composition_authoring_run_start(ctx: MCPContext, args: _AuthoringRunStartArgs) -> dict:
    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = _uuid(args.run_id, "run_id")
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload: dict[str, Any] = {"book_id": args.book_id, "run_id": args.run_id}
    if args.pause_after_each_unit is not None:
        payload["pause_after_each_unit"] = args.pause_after_each_unit
    _title = "Start the authoring run (spends LLM tokens)"

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret,
            tc.user_id, run_id, _AUTHORING_RUN_START_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _AUTHORING_RUN_START_DESCRIPTOR,
            "title": _title,
            "domain": "composition",
            "requires": "human confirmation via the review surface — this spends LLM "
                        "tokens; nothing drafts until confirmed",
        }

    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_AUTHORING_RUN_START_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": _title, "descriptor": _AUTHORING_RUN_START_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


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
        visibility="legacy", superseded_by="composition_authoring_run_manage",  # S3
        tool_name="composition_authoring_run_resume",
    ),
)
async def composition_authoring_run_resume(ctx: MCPContext, args: _AuthoringRunResumeArgs) -> dict:
    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = _uuid(args.run_id, "run_id")
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload: dict[str, Any] = {"book_id": args.book_id, "run_id": args.run_id}
    if args.pause_after_each_unit is not None:
        payload["pause_after_each_unit"] = args.pause_after_each_unit
    _title = "Resume the authoring run (spends more LLM tokens)"

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret,
            tc.user_id, run_id, _AUTHORING_RUN_RESUME_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _AUTHORING_RUN_RESUME_DESCRIPTOR,
            "title": _title,
            "domain": "composition",
            "requires": "human confirmation via the review surface — this spends more "
                        "LLM tokens; nothing resumes until confirmed",
        }

    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_AUTHORING_RUN_RESUME_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": _title, "descriptor": _AUTHORING_RUN_RESUME_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


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
        visibility="legacy", superseded_by="composition_authoring_run_review",  # S3
        tool_name="composition_authoring_run_pause",
    ),
)
async def composition_authoring_run_pause(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    run_id = _uuid(args.run_id, "run_id")
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
        "tool that can stop a run — a run is not a background job, so jobs_cancel cannot "
        "reach it and answers 'not found or not accessible'. Allowed from every "
        "non-running state; "
        "pause a RUNNING run first via composition_authoring_run_pause. No new spend, "
        "executes immediately. Closing a gated/paused run releases the book's active-run "
        "slot for a new one. The book's OWNER-grant holder may close ANY run on their book."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["close authoring run", "end agent mode", "cancel autonomous run",
                  "stop autonomous run", "kill the run", "release run slot"],
        visibility="legacy", superseded_by="composition_authoring_run_review",  # S3
        tool_name="composition_authoring_run_close",
    ),
)
async def composition_authoring_run_close(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    run_id = _uuid(args.run_id, "run_id")
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
        visibility="legacy", superseded_by="composition_authoring_run_review",  # S3
        tool_name="composition_authoring_run_accept_unit",
    ),
)
async def composition_authoring_run_accept_unit(
    ctx: MCPContext, args: _AuthoringRunUnitArgs,
) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    # Grant-tier law (spec 25): unit review is a package WRITE → EDIT on the
    # book, gated FIRST (PM-8 ordering); the run must be in THIS book AND be the
    # caller's own — REST `_run_for_mutation` is creator-only for accept/reject
    # (book-owner escalation is pause/close only), and the two doors must agree.
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = _uuid(args.run_id, "run_id")
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
        visibility="legacy", superseded_by="composition_authoring_run_review",  # S3
        tool_name="composition_authoring_run_reject_unit",
    ),
)
async def composition_authoring_run_reject_unit(
    ctx: MCPContext, args: _AuthoringRunUnitArgs,
) -> dict:
    from app.services.authoring_run_service import TransitionConflictError

    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    # Grant-tier law (spec 25): unit review is a package WRITE → EDIT on the
    # book, gated FIRST (PM-8 ordering); the run must be in THIS book AND be the
    # caller's own — rejecting a unit RESTORES the chapter's prior revision, so a
    # non-creator EDIT-grantee could destroy another author's draft. REST
    # `_run_for_mutation` is creator-only here; the two doors must agree.
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = _uuid(args.run_id, "run_id")
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
        visibility="legacy", superseded_by="composition_authoring_run_manage",  # S3
        tool_name="composition_authoring_run_revert_all",
    ),
)
async def composition_authoring_run_revert_all(ctx: MCPContext, args: _AuthoringRunIdArgs) -> dict:
    tc = _ctx(ctx)
    book_id = _uuid(args.book_id, "book_id")
    await _gate(tc, book_id, GrantLevel.EDIT)
    run_id = _uuid(args.run_id, "run_id")
    svc = await get_authoring_run_service()
    await _require_own_run(tc, svc, book_id, run_id)
    payload = {"book_id": args.book_id, "run_id": args.run_id}
    _title = "Revert ALL drafted/accepted chapters in this run (destructive)"

    def _confirm_fallback():
        confirm_token = mint_confirm_token(
            settings.confirm_token_signing_secret,
            tc.user_id, run_id, _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR, payload,
        )
        return {
            "confirm_token": confirm_token,
            "descriptor": _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR,
            "title": _title,
            "domain": "composition",
            "requires": "human confirmation — this is destructive and irreversible "
                        "from this surface; nothing reverts until confirmed",
        }

    return await gate_or_confirm(
        ctx, _task_store,
        descriptor=_AUTHORING_RUN_REVERT_ALL_DESCRIPTOR,
        owner_user_id=tc.user_id,
        payload=payload,
        input_requests={"title": _title, "descriptor": _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR, "domain": "composition"},
        confirm_fallback=_confirm_fallback,
    )


# ── S3 catalog-unification (2026-07-25): 2 unified authoring-run op-tools SUPERSEDE the 9
# per-op write tools above (all marked visibility=legacy). The split is by TIER, and the tier
# boundary is BEHAVIORAL, not cosmetic: the W ops (create/start/resume/gate/revert_all) MINT a
# confirm-token (human-gated, cost-bearing), the A ops (pause/close/accept_unit/reject_unit)
# AUTO-APPLY immediately. Merging W+A into one tool would force confirm-gating onto the immediate
# ops OR bypass the cost gate on the gated ops — so two tier-coherent tools is the only safe
# unification. get/list reads stay separate. Delegates to the SAME handlers (no logic moved). ──
class _AuthoringRunManageArgs(ForbidExtra):
    """Flat superset for composition_authoring_run_manage (W/book — each op mints a confirm-token)."""

    op: Annotated[

        Literal["create", "start", "resume", "gate", "revert_all"],

        Field(description=(

            "WHICH OPERATION to perform — the dispatch discriminator: create | start | resume | gate | revert_all. "

            "Every other argument is optional in the schema because this is a flat superset: "

            "each op reads only ITS OWN fields, and this tool's description says which those are. "

            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."

        )),

    ]
    book_id: str
    run_id: str | None = None                 # start, resume, gate, revert_all (NOT create)
    # 🔴 THE THREE `create` REQUIREMENTS CARRIED A TITLE AND NO DESCRIPTION, so the runtime could
    # say nothing useful when one was missing. Measured 2026-08-23: op=create was called 4 of 5
    # runs and refused every time with "op=create requires plan_run_id, budget_usd, and
    # pause_after_each_unit" — while the SCHEMA declares required=['op','book_id'] and all three of
    # these optional-with-default-null, because a flat superset must be. A model that trusts the
    # schema is refused by the handler.
    #
    # The refusal builder's useful branch quotes an argument's OWN declaration back ("The tool DOES
    # declare what this is — <desc>"); with nothing to quote it falls through to "this tool does not
    # declare which side supplies them". So the per-op requirement, which lived only in the comments
    # you are reading, is now IN the wire schema where the model can see it.
    #
    # AND TWO OF THEM HAVE NO SUPPLIER BY NATURE. budget_usd and pause_after_each_unit are the
    # AUTHOR's decisions — how much money, and whether to stop between units. No tool can provide
    # them, the model is correctly forbidden from inventing them, and nothing told it to ASK. Saying
    # so is not a policy change; it is what the handler already enforces, written where it is read.
    # 🔴 THE DESCRIPTION NAMED ONLY THE TOOL THAT MAKES A NEW RUN. Measured 2026-08-24: the book
    # already HAD a compiled plan run, and the only supplier this text offered was
    # plan_propose_spec — which proposes a fresh one. A model that follows it either builds a
    # second plan or, as measured on 2 of 2 runs, reaches for whatever id it already holds (the
    # editor's chapter_id) and the create fails with a bare 400.
    #
    # An EXISTING run is readable and always was: composition_package_tree returns a `.runs/`
    # block — the book's 5 most recent plan runs with id/status/mode, via
    # PlanRunsRepo.list_for_book. Naming it here is not a new capability, it is the supplier the
    # description was missing; the earlier note that "no tool lists an existing run" was wrong.
    plan_run_id: str | None = Field(default=None, description=(
        "op=create REQUIRES this. The PLAN run this authoring run drafts from (a UUID). If the "
        "book ALREADY has a plan, read its id from composition_package_tree's `runs.recent` — "
        "do NOT propose a new plan just to obtain one. Only when the book has no plan at all is "
        "the id the `run_id` returned by plan_propose_spec (the same id plan_compile takes). "
        "Not the authoring run's own id, which is `run_id`, and never a chapter id."))
    scope: list[str] | None = None            # create
    level: Literal[3, 4] | None = None        # create
    budget_usd: Decimal | None = Field(default=None, description=(
        "op=create REQUIRES this. The spend ceiling for the run, in USD. No tool supplies it and it "
        "must not be guessed — it is the author's decision. If you do not have a figure, ASK THEM "
        "for one rather than proposing a default."))
    tool_allowlist: list[Literal[ALLOWLISTABLE_TOOLS]] | None = None  # create
    pause_after_each_unit: bool | None = Field(default=None, description=(
        "op=create REQUIRES this (optional on start/resume). Whether the run stops after each unit "
        "for review. No tool supplies it — it is the author's choice about how much to review, so "
        "ASK THEM if it was not stated."))
    params: dict[str, Any] | None = None      # create


@mcp_server.tool(
    name="composition_authoring_run_manage",
    description=(
        "Drive the GATED lifecycle of an autonomous authoring run — the unified entry point for "
        "the run actions that mint a confirm-token (human-approved, cost-bearing). "
        "op=create sets up a run (needs plan_run_id + budget_usd + pause_after_each_unit; optional "
        "scope/level/tool_allowlist/params). op=start begins a created run (needs run_id; optional "
        "pause_after_each_unit). op=resume continues a paused run (needs run_id). op=gate runs the "
        "start-gate check draft→gated (needs run_id). op=revert_all rolls back all accepted units "
        "(needs run_id). Each returns a confirm-token to approve. Read with "
        "composition_authoring_run_get / _list; immediate controls are composition_authoring_run_review."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["create authoring run", "start authoring run", "resume run", "run gate check",
                  "revert authoring run", "manage authoring run", "begin autopilot"],
        tool_name="composition_authoring_run_manage",
    ),
)
async def composition_authoring_run_manage(ctx: MCPContext, args: _AuthoringRunManageArgs) -> dict:
    """Unified gated-run dispatch — delegates to the SAME per-op handlers (no logic moved)."""
    if args.op == "create":
        if not args.plan_run_id or args.budget_usd is None or args.pause_after_each_unit is None:
            raise ValueError("op=create requires plan_run_id, budget_usd, and pause_after_each_unit")
        return await composition_authoring_run_create(ctx, _AuthoringRunCreateArgs(
            book_id=args.book_id, plan_run_id=args.plan_run_id, budget_usd=args.budget_usd,
            pause_after_each_unit=args.pause_after_each_unit,
            **_present(scope=args.scope, level=args.level, tool_allowlist=args.tool_allowlist,
                       params=args.params),
        ))
    if not args.run_id:
        raise ValueError(f"op={args.op} requires run_id")
    if args.op == "start":
        return await composition_authoring_run_start(ctx, _AuthoringRunStartArgs(
            book_id=args.book_id, run_id=args.run_id,
            **_present(pause_after_each_unit=args.pause_after_each_unit)))
    if args.op == "resume":
        return await composition_authoring_run_resume(ctx, _AuthoringRunResumeArgs(
            book_id=args.book_id, run_id=args.run_id,
            **_present(pause_after_each_unit=args.pause_after_each_unit)))
    if args.op == "gate":
        return await composition_authoring_run_gate(
            ctx, _AuthoringRunIdArgs(book_id=args.book_id, run_id=args.run_id))
    # op == "revert_all"
    return await composition_authoring_run_revert_all(
        ctx, _AuthoringRunIdArgs(book_id=args.book_id, run_id=args.run_id))


class _AuthoringRunReviewArgs(ForbidExtra):
    """Flat superset for composition_authoring_run_review (A/book — each op applies immediately)."""

    op: Annotated[

        Literal["pause", "close", "accept_unit", "reject_unit"],

        Field(description=(

            "WHICH OPERATION to perform — the dispatch discriminator: pause | close | accept_unit | reject_unit. "

            "Every other argument is optional in the schema because this is a flat superset: "

            "each op reads only ITS OWN fields, and this tool's description says which those are. "

            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."

        )),

    ]
    book_id: str
    run_id: Annotated[str, Field(description=(
            "the authoring run to act on (UUID). NOT a name and NOT yours to invent — list the "
            "book's runs with composition_authoring_run_list and pass the id it returns. A book "
            "may have NONE, and 'there are no runs' is the correct answer when it does: a "
            "structurally valid id that matches no run is the worst outcome, because the card it "
            "mints looks exactly like a real one."
    ))]
    unit_index: int | None = None  # accept_unit, reject_unit (required for those)


@mcp_server.tool(
    name="composition_authoring_run_review",
    description=(
        "Apply an IMMEDIATE control to an authoring run — the unified entry point for the "
        "auto-applied (no confirm-token) actions. op=pause pauses a running run (needs run_id). "
        "op=close ends a run (needs run_id). op=accept_unit accepts a generated unit (needs run_id "
        "+ unit_index ≥ 0). op=reject_unit rejects one (needs run_id + unit_index). Gated actions "
        "(create/start/resume/gate/revert) are composition_authoring_run_manage; read with "
        "composition_authoring_run_get / _list."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["pause authoring run", "close authoring run", "accept unit", "reject unit",
                  "approve draft unit", "review authoring run", "stop run"],
        tool_name="composition_authoring_run_review",
    ),
)
async def composition_authoring_run_review(ctx: MCPContext, args: _AuthoringRunReviewArgs) -> dict:
    """Unified immediate-run-control dispatch — delegates to the SAME per-op handlers."""
    if args.op == "pause":
        return await composition_authoring_run_pause(
            ctx, _AuthoringRunIdArgs(book_id=args.book_id, run_id=args.run_id))
    if args.op == "close":
        return await composition_authoring_run_close(
            ctx, _AuthoringRunIdArgs(book_id=args.book_id, run_id=args.run_id))
    if args.unit_index is None:
        raise ValueError(f"op={args.op} requires unit_index")
    if args.op == "accept_unit":
        return await composition_authoring_run_accept_unit(ctx, _AuthoringRunUnitArgs(
            book_id=args.book_id, run_id=args.run_id, unit_index=args.unit_index))
    # op == "reject_unit"
    return await composition_authoring_run_reject_unit(ctx, _AuthoringRunUnitArgs(
        book_id=args.book_id, run_id=args.run_id, unit_index=args.unit_index))


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
    # 🔴 D-UNDECLARED-ARG-IS-GUESSED. This was a bare `str | None` whose advertised schema was
    # {"anyOf": [...], "default": null, "title": "Q"} — no description at all. A model asked to
    # find a motif BY NAME sees a parameter called "Q" that says nothing, and invents one that
    # sounds right.
    #
    # MEASURED 2026-08-21, batch 19, on TWO scenarios across TWO arms (10 runs, 5/5 each time):
    # the model called this tool with {"name": ["Throwaway Loop Pattern"], "scope": "mine"} and
    # got `args.name`: Extra fields not permitted. It retried, and the retry loop ended in a
    # provider stream error — which is why composition_motif_edit and composition_motif_bind_edit
    # both read 0/5 called with 5/5 errors, and why that looked like a flaky rig for two batches.
    #
    # The tool COULD do what was asked: q="Throwaway Loop" returns the 4 matching motifs. The
    # capability was there and the declaration was not. The DESCRIPTION mentions `q` in prose —
    # "an exact name or code hit sorts first" — but prose on the TOOL is not a declaration on the
    # ARGUMENT, and the argument is what the model fills in.
    q: Annotated[
        str | None,
        Field(description=(
            "Free-text query — THIS is how you search by NAME. An exact name or code match sorts "
            "first, then semantic similarity. There is no separate `name` argument. Unlike genre/"
            "kind/status (which SUBTRACT), q RANKS: it never removes a result."
        )),
    ] = None
    scope: Literal["mine", "public", "system", "all"] = "all"
    status: Literal["draft", "active", "archived"] | None = None
    # The language to READ the motifs in — a re-wording, never a filter. A motif with no
    # translation falls back to the language it was authored in and reports text_fallback.
    display_language: str | None = None
    limit: int = 20
    # L1/L2 reference-first (Context Budget Law §6b). Default "summary" (K38 — OUT-2; a
    # lightweight ref list, no roles/beats/preconditions/effects); "full" is an opt-in.
    detail: Literal["summary", "full"] = "summary"


@mcp_server.tool(
    name="composition_motif_search",
    description=(
        "Search the narrative motif library — reusable plot patterns, tropes, "
        "situations, hooks, emotion arcs, schemes (e.g. 套路 / 爽点 / 打脸). Filter by "
        "genre, kind, language or status — these SUBTRACT. `q` is different: it RANKS "
        "rather than filters (an exact name or code hit sorts first, then semantic "
        "similarity), so a query that matches nothing literally still returns rows, "
        "ordered by how close they are. Read the top of the list, not its length. "
        "`scope` narrows the tier: "
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
        status=args.status, q=args.q, display_language=args.display_language, limit=args.limit,
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
    motif_id: Annotated[str, "The motif's id. (a UUID)"],
) -> dict:
    # @small_return: single-object read (the get_by_id sibling) — this IS the
    # full-detail fetch the summary refs point to; no detail arg / SET projection.
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    # get_visible IS the IDOR guard for a non-book resource: it enforces R1.1
    # (system | public | owner), so a foreign PRIVATE id is indistinguishable from a
    # missing one (H13) — no enumeration oracle.
    motif = await repo.get_visible(tc.user_id, _uuid(motif_id, "motif_id"))
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
    book_id: Annotated[str, "The book whose motif library to list (you need VIEW on it). (a UUID)"],
    genre: Annotated[str | None, "Filter by genre tag."] = None,
    kind: Annotated[_MotifKind | None, "Filter by motif kind."] = None,
    q: Annotated[str | None, "Free-text filter on name/summary."] = None,
    status: Annotated[Literal["draft", "active", "archived"] | None, "Status filter."] = "active",
    display_language: Annotated[str | None, "Language to read the motifs in (re-words them; never filters)."] = None,
    limit: Annotated[int, "Max rows (a small default page; raise for more)."] = 25,
    detail: Annotated[
        Literal["summary", "full"],
        "summary = refs only (id/code/name/kind/summary/badges, no roles/beats); full = every field.",
    ] = "summary",  # K37 drain: OUT-2 small-shape default
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    # VIEW-gate the book — the grant IS the access control for the shared tier (read).
    await _gate(tc, bid, GrantLevel.VIEW)
    repo = MotifRepo(get_pool())
    motifs = await repo.list_in_book(
        tc.user_id, bid, genre=genre, kind=kind, status=status, q=q,
        display_language=display_language, limit=limit,
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
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    node_id: Annotated[str, "The chapter outline node to rank motifs against. (a UUID)"],
    limit: Annotated[int, "Max candidates."] = 5,
    detail: Annotated[
        Literal["summary", "full"],
        "summary = each candidate's motif is refs only (no roles/beats); full = every field. "
        "score + match_reason are kept at both levels.",
    ] = "summary",  # K37 drain: OUT-2 small-shape default
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    meta = await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    pid = _require_project(meta)
    outline = OutlineRepo(get_pool())
    node = await outline.get_node(_uuid(node_id, "node_id"))
    # Per-tool IDOR: the node must be in the gated Work's project (a node from
    # another Work would otherwise be ranked under THIS book's gate).
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    retriever = MotifRetriever(get_pool())
    # Motif is a USER-tier resource (deps/ registry — untouched by the re-key), so the
    # retriever keeps its caller-visibility predicate on tc.user_id. Two-space (2026-07-17):
    # the caller's STRICTLY-PRIVATE motifs rank in their OWN BYOK space (section='mine'),
    # shared in the platform space (section='library'). The embed model comes from the Work
    # settings; None ⇒ private motifs degrade to genre (the platform never embeds private).
    work = await works.get(pid)
    user_model = reference_embed_model(getattr(work, "settings", None)) if work is not None else None
    candidates = await retriever.retrieve(
        tc.user_id, book_id=meta.book_id, project_id=pid,
        genre_tags=list(getattr(meta, "genre_tags", []) or []),
        display_language=getattr(meta, "language", None) or "en",
        # The node's OWN text + beat_role seed the query (see `node_query_text`); passing
        # None here forced every candidate onto the degrade path with cosine=0.0.
        beat_role=getattr(node, "beat_role", None),
        tension=getattr(node, "tension_target", None), limit=limit,
        user_model=user_model, query=node_query_text(node),
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
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    premise: Annotated[str | None, "Optional premise text to seed the rank."] = None,
    genre: Annotated[str | None, "Optional genre filter."] = None,
    limit: Annotated[int, "Max candidates."] = 5,
    detail: Annotated[
        Literal["summary", "full"],
        "summary = each candidate's arc_template is refs only (no threads/layout/pacing); "
        "full = every field. score + match_reason are kept at both levels.",
    ] = "summary",  # K37 drain: OUT-2 small-shape default
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    meta = await _book_or_deny(works, tc, pid, GrantLevel.VIEW)
    pid = _require_project(meta)
    retriever = MotifRetriever(get_pool())
    # Arc retrieval (D-ARC-RETRIEVE) ranks the caller-visible arc_template set under the
    # read predicate (book gate only; arc_template is a deps/ registry table, so tc.user_id
    # stays). Two-space (2026-07-17 tenancy re-design): the caller's STRICTLY-PRIVATE arcs
    # rank in their OWN BYOK space (section='mine'), shared arcs in the platform space
    # (section='library'). The caller's embed model comes from the Work settings; None ⇒
    # their private arcs degrade to genre ranking (the platform never embeds private content).
    work = await works.get(pid)
    user_model = reference_embed_model(getattr(work, "settings", None)) if work is not None else None
    candidates = await retriever.retrieve_arcs(
        tc.user_id, book_id=meta.book_id, project_id=pid,
        premise=premise, genre=genre, limit=limit, user_model=user_model,
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
    out: dict[str, Any] = {
        "candidates": [
            {"arc_template": arc_dicts[i], "score": c.score, "match_reason": c.match_reason}
            for i, c in enumerate(candidates)
        ],
        **meta,
    }
    # R4 already degrades honestly PER CANDIDATE (`match_reason.degraded`, cosine 0.0), but
    # nothing said so at the top level — and a caller reads `candidates`, not each candidate's
    # match_reason. Measured live: five suggestions, every score 0.0, and the only signal that
    # the semantic rank never ran was nested two levels down. That reads as a ranked answer.
    #
    # Its siblings already put this at the top (`memory_search` / `story_search` both return a
    # top-level `degraded`), so this is the house convention, not a new one — and C-24's rule
    # is that a partially-executed declaration says which part did not run.
    #
    # DERIVED from the candidates rather than from `user_model is None`: the retriever degrades
    # for more than one reason (no BYOK model for private arcs, OR the embedder being down),
    # and re-deriving the cause here would be a second implementation that can disagree.
    _degraded = sorted({
        c.match_reason.get("section") or "unknown"
        for c in candidates
        if isinstance(c.match_reason, dict) and c.match_reason.get("degraded")
    })
    if _degraded:
        out["degraded"] = {"rank": "not_semantic", "sections": _degraded}
        out["note"] = (
            "semantic ranking did not run for " + ", ".join(_degraded) + " — these candidates "
            "are ordered by genre and tension only, and their scores are not comparable. "
            "Private arcs rank semantically only once the Work has an embedding model set; "
            "shared arcs need the platform embedder."
        )
    return out


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
    # The language YOU are authoring in. Your motifs are never machine-translated on the
    # platform's dime — exactly like your book.
    original_language: str = "en"
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
        visibility="legacy", superseded_by="composition_motif_edit",  # S3 2026-07-25
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
        book_id = _uuid(args.book_id, "book_id")
        await _gate(tc, book_id, GrantLevel.EDIT)
    from app.db.models import MotifCreateArgs as _RepoCreateArgs
    try:
        create_args = _RepoCreateArgs(
            code=args.code, name=args.name, original_language=args.original_language, kind=args.kind,
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
            "error": "a motif with this code already exists in your library",
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
        visibility="legacy", superseded_by="composition_motif_edit",  # S3 2026-07-25
        tool_name="composition_motif_archive",
    ),
)
async def composition_motif_archive(
    ctx: MCPContext,
    motif_id: Annotated[str, "The motif to archive. (a UUID)"],
    book_id: Annotated[
        str | None,
        "Set ONLY to archive a SHARED book-tier motif — requires EDIT on that book; any "
        "EDIT-grantee may archive a shared row. Omit for one of YOUR OWN motifs.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    mid = _uuid(motif_id, "motif_id")
    if book_id is not None:
        # SHARED tier (D-MOTIF-ADOPT-BOOK-COLLAB-TIER): access is the book grant, not ownership.
        # EDIT-gate the book, confirm the target is a shared row IN this book (else H13), archive.
        bid = _uuid(book_id, "book_id")
        await _gate(tc, bid, GrantLevel.EDIT)
        target = await repo.get_in_book(tc.user_id, mid, bid)
        if target is None or not target.book_shared or target.book_id != bid:
            raise uniform_not_accessible()
        await repo.archive_shared(tc.user_id, mid, bid)
        return {"motif_id": motif_id, "archived": True,
                "_meta": {"undo_hint": _undo("composition_motif_restore", motif_id=motif_id, book_id=book_id)}}
    # USER scope: you may only archive YOUR OWN motif. The owner-resolver raises the
    # uniform deny for a missing/foreign/system row before any write.
    guard = require_user_scope(_motif_owner_resolver(repo))
    await guard(tc, mid)
    await repo.archive(tc.user_id, mid)
    # archive() flips status='archived'; the honest reverse verb is now composition_motif_restore
    # (S-08 — a clean status-only un-archive, no OCC dance), so the undo hint points there.
    return {"motif_id": motif_id, "archived": True,
            "_meta": {"undo_hint": _undo("composition_motif_restore", motif_id=motif_id)}}


@mcp_server.tool(
    name="composition_motif_restore",
    description=(
        "Restore an ARCHIVED motif of YOURS (the reverse of composition_motif_archive). Returns the "
        "restored motif. A system/public/foreign or not-archived id is not restorable (uniform deny)."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["restore motif", "unarchive motif", "un-retire trope", "bring back a motif"],
        visibility="legacy", superseded_by="composition_motif_edit",  # S3 2026-07-25
        tool_name="composition_motif_restore",
    ),
)
async def composition_motif_restore(
    ctx: MCPContext,
    motif_id: Annotated[str, "The archived motif to restore. (a UUID)"],
    book_id: Annotated[
        str | None,
        "Set ONLY to restore a SHARED book-tier motif — requires EDIT on that book; any "
        "EDIT-grantee may. Omit for one of YOUR OWN motifs.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    mid = _uuid(motif_id, "motif_id")
    if book_id is not None:
        # SHARED tier: access is the book grant, not ownership. EDIT-gate the book, then restore_shared
        # matches only an ARCHIVED book_shared row in this book (None → uniform deny, no oracle).
        bid = _uuid(book_id, "book_id")
        await _gate(tc, bid, GrantLevel.EDIT)
        motif = await repo.restore_shared(tc.user_id, mid, bid)
    else:
        # USER scope: only YOUR OWN archived motif (restore()'s predicate is owner + status='archived').
        motif = await repo.restore(tc.user_id, mid)
    if motif is None:
        raise uniform_not_accessible()
    out = motif.model_dump(mode="json")
    undo_args = {"motif_id": motif_id, "book_id": book_id} if book_id is not None else {"motif_id": motif_id}
    out["_meta"] = {"undo_hint": _undo("composition_motif_archive", **undo_args)}
    return out


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
    # Correct which language the motif was AUTHORED in. Not identity (MOTIF-I18N took it
    # out of every unique index) — a claim, and a wrong one hands the wrong language to a
    # prompt while reporting no fallback.
    original_language: str | None = None
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
        visibility="legacy", superseded_by="composition_motif_edit",  # S3 2026-07-25
        tool_name="composition_motif_patch",
    ),
)
async def composition_motif_patch(ctx: MCPContext, args: _MotifPatchToolArgs) -> dict:
    tc = _ctx(ctx)
    repo = MotifRepo(get_pool())
    mid = _uuid(args.motif_id, "motif_id")
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
        bid = _uuid(args.book_id, "book_id")
        await _gate(tc, bid, GrantLevel.EDIT)
        prior = await repo.get_in_book(tc.user_id, mid, bid)
        if prior is None or not prior.book_shared or prior.book_id != bid:
            raise uniform_not_accessible()
        # F3 — the read boundary IS the write boundary. `examples` is redacted from a non-owner
        # (imported source prose), and a redacted read hands back `[]`, indistinguishable from
        # genuinely empty, so a whole-object patch from a grantee would wipe it for everyone
        # including the owner. REST needs a runtime guard for that (`_reject_redacted_writes`);
        # this surface is safe by CONSTRUCTION — `_MotifPatchToolArgs` has no redacted field and
        # ForbidExtra rejects one. That is incidental rather than designed, so it is pinned by
        # `test_the_agent_patch_surface_cannot_EXPRESS_a_redacted_field`; add a redacted field
        # here and it reds, rather than quietly re-opening the hole.
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
                "error": "a motif with this code already exists"}
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
    motif_id: Annotated[str, "The motif whose edges to list (must be visible to you). (a UUID)"],
    # K20 — see the Literal note on composition_arc_template_list: a runtime-checked closed
    # set must be declared in the schema, not only enforced after the call arrives.
    direction: Annotated[Literal["out", "in", "both"], "'out', 'in', or 'both'."] = "both",
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
        bid = _uuid(book_id, "book_id")
        await _gate(tc, bid, GrantLevel.VIEW)   # the book grant is the read access for the shared graph
    repo = MotifRepo(get_pool())
    # READPRED: list_links returns [] for a motif you can't see (IDOR-safe — empty is
    # indistinguishable from 'no edges', no existence oracle).
    links = await repo.list_links(
        tc.user_id, _uuid(motif_id, "motif_id"), direction=direction, kinds=kinds, book_id=bid,
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
        visibility="legacy", superseded_by="composition_motif_link_edit",  # S3 2026-07-25
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
        bid = _uuid(args.book_id, "book_id")
        await _gate(tc, bid, GrantLevel.EDIT)
    try:
        link = await repo.create_link(
            tc.user_id, _uuid(args.from_motif_id, "from_motif_id"), _uuid(args.to_motif_id, "to_motif_id"), args.kind,
            ord=args.ord, book_id=bid,
        )
    except EndpointsOwnedNotShared:
        # D-AN-OPTIONAL-ARG-SWITCHES-THE-MODE-AND-THE-REFUSAL-HIDES-IT — the ONE miss with a
        # remedy, so name it. `book_id` silently switches this tool from "two motifs you own" to
        # "two motifs shared into that book", and a caller that passed the ambient book over its
        # own motifs cannot tell that from H13's "not found or not accessible" — measured
        # 2026-08-24, the model had just listed both ids and had nowhere to go from that message.
        # Ordered BEFORE the LookupError arm it subclasses; every other miss still falls through
        # to the uniform refusal, so the no-existence-oracle property is unchanged.
        return {"success": False, "error": (
            "both motifs are YOUR OWN and are not shared into this book, so the book-scoped form "
            "cannot link them. Call composition_motif_link_edit again WITHOUT book_id to link two "
            "motifs you own."
        )}
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
        visibility="legacy", superseded_by="composition_motif_link_edit",  # S3 2026-07-25
        tool_name="composition_motif_link_delete",
    ),
)
async def composition_motif_link_delete(
    ctx: MCPContext,
    link_id: Annotated[str, "The motif-link edge id (must be on one of your motifs). (a UUID)"],
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
        bid = _uuid(book_id, "book_id")
        await _gate(tc, bid, GrantLevel.EDIT)
    deleted = await repo.delete_link(tc.user_id, _uuid(link_id, "link_id"), book_id=bid)
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
        visibility="legacy", superseded_by="composition_motif_bind_edit",  # S3 2026-07-25
        tool_name="composition_motif_bind",
    ),
)
async def composition_motif_bind(ctx: MCPContext, args: _MotifBindArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)
    outline = OutlineRepo(get_pool())
    node_id = _uuid(args.node_id, "node_id")
    # IDOR #1: the chapter node is in the gated Work's project.
    node = await outline.get_node(node_id)
    if node is None or node.project_id != pid:
        raise uniform_not_accessible()
    # IDOR #2: the motif is caller-visible (you can only bind a motif you can see).
    repo = MotifRepo(get_pool())
    motif = await repo.get_visible(tc.user_id, _uuid(args.motif_id, "motif_id"))
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
        visibility="legacy", superseded_by="composition_motif_bind_edit",  # S3 2026-07-25
        tool_name="composition_motif_unbind",
    ),
)
async def composition_motif_unbind(
    ctx: MCPContext,
    project_id: Annotated[str, "The Work's project_id. (a UUID)"],
    node_id: Annotated[str, "The chapter node to clear / undo a bind on. (a UUID)"],
    undo_token: Annotated[
        dict | None,
        "The undo_token from a prior composition_motif_bind — when present, does the EXACT "
        "inverse (restores the pre-bind scenes + prose). Omit to CLEAR the chapter's motif.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(project_id, "project_id")
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)
    outline = OutlineRepo(get_pool())
    nid = _uuid(node_id, "node_id")
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


# ── S3 catalog-unification (2026-07-25): 3 unified motif op-tools SUPERSEDE the 8 per-op
# motif write tools above (all marked visibility=legacy). Grouped by TIER+SCOPE (an op tool
# is single-tier): motif_edit (A/user CRUD ×4), motif_link_edit (A/user link ×2),
# motif_bind_edit (A/book chapter-binding ×2). adopt (W/user) + mine (W/book) stay separate
# (different tier), as do all reads. Delegates to the SAME handlers (no logic moved); mirrors
# the arc-family S3·arc pattern + KG's op-dispatch. ────────────────────────────────────────
class _MotifEditArgs(ForbidExtra):
    """Flat superset for composition_motif_edit (A/user); each op reads only its own fields."""

    op: Annotated[

        Literal["create", "patch", "archive", "restore"],

        Field(description=(

            "WHICH OPERATION to perform — the dispatch discriminator: create | patch | archive | restore. "

            "Every other argument is optional in the schema because this is a flat superset: "

            "each op reads only ITS OWN fields, and this tool's description says which those are. "

            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."

        )),

    ]
    motif_id: str | None = None          # patch, archive, restore
    book_id: str | None = None           # all (shared-tier variant)
    expected_version: int | None = None  # patch (required)
    target: Literal["user", "book_shared"] | None = None  # create
    code: str | None = None              # create (required)
    name: str | None = None              # create (required), patch
    original_language: str | None = None  # create
    kind: _MotifKind | None = None       # create, patch
    category: str | None = None          # patch
    summary: str | None = None           # create, patch
    genre_tags: list[str] | None = None  # create, patch
    roles: list[dict[str, Any]] | None = None         # create, patch
    beats: list[dict[str, Any]] | None = None         # create, patch
    preconditions: list[dict[str, Any]] | None = None  # create, patch
    effects: list[dict[str, Any]] | None = None       # create, patch
    examples: list[dict[str, Any]] | None = None      # create
    annotations: dict[str, Any] | None = None         # patch
    tension_target: int | None = None    # create, patch
    emotion_target: str | None = None    # create, patch
    visibility: Literal["private", "unlisted"] | None = None       # create
    status: Literal["draft", "active", "archived"] | None = None   # patch


@mcp_server.tool(
    name="composition_motif_edit",
    description=(
        "Create, edit, archive, or restore a motif in YOUR library (a reusable plot pattern — "
        "sequence/situation/hook/emotion_arc/trope/pattern/scheme) — the unified motif-CRUD entry point. "
        "op=create mints a PRIVATE motif (needs code + name; optional kind/summary/roles/beats/"
        "preconditions/effects/genre_tags/tension_target/emotion_target/examples; target='book_shared'+"
        "book_id authors into a book's shared tier). op=patch edits your own (needs motif_id + "
        "expected_version — optimistic concurrency; only the fields you pass change; book_id edits a "
        "shared row). op=archive soft-archives yours (needs motif_id; reversible via op=restore; book_id "
        "for a shared row). op=restore un-archives yours (needs motif_id). Auto-applied with an Undo hint. "
        "To publish/adopt/bind use composition_motif_adopt / composition_motif_bind_edit; read with "
        "composition_motif_get / composition_motif_search."
    ),
    meta=require_meta(
        "A", "user",
        synonyms=["edit motif", "create motif", "new trope", "author a motif", "define pattern",
                  "update motif", "rename motif", "archive motif", "restore motif", "manage motif"],
        tool_name="composition_motif_edit",
    ),
)
async def composition_motif_edit(ctx: MCPContext, args: _MotifEditArgs) -> dict:
    """Unified motif-CRUD dispatch — delegates to the SAME per-op handlers (no logic moved)."""
    if args.op == "create":
        if not args.code or not args.name:
            raise ValueError("op=create requires code and name")
        return await composition_motif_create(ctx, _MotifCreateArgs(
            code=args.code, name=args.name,
            **_present(
                target=args.target, book_id=args.book_id,
                original_language=args.original_language, kind=args.kind,
                summary=args.summary, genre_tags=args.genre_tags, roles=args.roles, beats=args.beats,
                preconditions=args.preconditions, effects=args.effects, examples=args.examples,
                tension_target=args.tension_target, emotion_target=args.emotion_target,
                visibility=args.visibility,
            ),
        ))
    if args.op == "patch":
        if not args.motif_id or args.expected_version is None:
            raise ValueError("op=patch requires motif_id and expected_version")
        # PATCH semantics: motif_patch builds its SET clause from model_fields_set +
        # model_dump(exclude_unset=True), so an EXPLICIT null clears the column. Forward by the
        # caller's own model_fields_set (`_passed`), NOT _present — else an explicit
        # `emotion_target=null` (clear) is dropped and the unified tool can't clear a nullable
        # field the legacy motif_patch can. (S3 null-clear fix, 2026-07-25.)
        return await composition_motif_patch(ctx, _MotifPatchToolArgs(
            motif_id=args.motif_id, expected_version=args.expected_version,
            **_passed(
                args, "book_id", "original_language", "name", "kind", "category", "summary",
                "genre_tags", "roles", "beats", "preconditions", "effects", "annotations",
                "tension_target", "emotion_target", "status",
            ),
        ))
    if args.op == "archive":
        if not args.motif_id:
            raise ValueError("op=archive requires motif_id")
        return await composition_motif_archive(ctx, motif_id=args.motif_id, book_id=args.book_id)
    # op == "restore"
    if not args.motif_id:
        raise ValueError("op=restore requires motif_id")
    return await composition_motif_restore(ctx, motif_id=args.motif_id, book_id=args.book_id)


class _MotifLinkEditArgs(ForbidExtra):
    """Flat superset for composition_motif_link_edit (A/user)."""

    op: Annotated[

        Literal["create", "delete"],

        Field(description=(

            "WHICH OPERATION to perform — the dispatch discriminator: create | delete. "

            "Every other argument is optional in the schema because this is a flat superset: "

            "each op reads only ITS OWN fields, and this tool's description says which those are. "

            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."

        )),

    ]
    # 🔴 REQUIRED-IN-PRACTICE IDS WITH NO DESCRIPTION. op=create refuses without these, and a bare
    # annotation gave chat-service nothing to quote: its refusal fell to the "this tool does not
    # declare which side supplies them" arm, named no tool, and so armed none. Measured 2026-08-22:
    # composition_motif_search advertised 0/5, called 0/5, and the turn died on the blank-args cap.
    from_motif_id: Annotated[str | None, Field(default=None, description=(
        "the motif the edge starts FROM (UUID). NOT a name — search motifs by name with "
        "composition_motif_search and pass the id it returns."
    ))] = None  # create
    to_motif_id: Annotated[str | None, Field(default=None, description=(
        "the motif the edge points TO (UUID). NOT a name — search motifs by name with "
        "composition_motif_search and pass the id it returns."
    ))] = None  # create
    kind: Literal["composed_of", "precedes", "variant_of"] | None = None  # create
    ord: int | None = None            # create
    link_id: str | None = None        # delete
    # 🔴 LEFT BARE BESIDE THE TWO IDS ABOVE, AND IT SELECTS A DIFFERENT ENDPOINT RULE. The comment
    # on from/to_motif_id says a bare annotation gives the model nothing to read; this one is worse
    # than silent, because supplying it CHANGES WHAT THE TOOL ACCEPTS. Measured 2026-08-24:
    # the model resolved both motifs correctly, passed the ambient book_id out of habit, and the
    # call was refused because its own private motifs are not book_shared.
    book_id: Annotated[str | None, Field(default=None, description=(
        "OMIT THIS to link two motifs YOU OWN — that is the usual case, and passing a book_id you "
        "were merely given will refuse the call. Supply it ONLY to link two motifs that are "
        "already SHARED into that book's graph: with book_id, BOTH endpoints must be shared in "
        "that same book, and your own private motifs do not qualify."
    ))] = None  # both (shared-tier variant)


@mcp_server.tool(
    name="composition_motif_link_edit",
    description=(
        "Create or delete a relationship edge between two motifs — the unified motif-link entry point. "
        "op=create adds an edge (needs from_motif_id + to_motif_id + kind ∈ composed_of|precedes|"
        "variant_of; optional ord; both endpoints must be YOUR own motifs, or pass book_id to link two "
        "SHARED motifs of that book). op=delete removes an edge (needs link_id; book_id for a shared "
        "edge). A duplicate/self-link/cycle is refused. Read with composition_motif_link_list."
    ),
    meta=require_meta(
        "A", "user",
        # D-THE-RUNTIME-INJECTS-THE-ARG-THAT-SWITCHES-THE-MODE — `book_id` here is NOT a scope,
        # it selects a different endpoint rule (own motifs vs this book's shared graph). A
        # consumer that backfills a missing context id must leave it alone: measured 2026-08-24,
        # chat-service filled the omitted id, this tool refused, its refusal said to call again
        # WITHOUT book_id, and the runtime put it back — the remedy was unfollowable.
        no_context_fill=["book_id"],
        synonyms=["link motifs", "connect motifs", "add motif edge", "unlink motifs",
                  "remove motif edge", "compose pattern", "set succession", "mark variant"],
        tool_name="composition_motif_link_edit",
    ),
)
async def composition_motif_link_edit(ctx: MCPContext, args: _MotifLinkEditArgs) -> dict:
    """Unified motif-link dispatch — delegates to the SAME per-op handlers (no logic moved)."""
    if args.op == "create":
        if not args.from_motif_id or not args.to_motif_id or not args.kind:
            raise ValueError("op=create requires from_motif_id, to_motif_id, and kind")
        return await composition_motif_link_create(ctx, _MotifLinkCreateArgs(
            from_motif_id=args.from_motif_id, to_motif_id=args.to_motif_id, kind=args.kind,
            **_present(ord=args.ord, book_id=args.book_id),
        ))
    # op == "delete"
    if not args.link_id:
        raise ValueError("op=delete requires link_id")
    return await composition_motif_link_delete(ctx, link_id=args.link_id, book_id=args.book_id)


class _MotifBindEditArgs(ForbidExtra):
    """Flat superset for composition_motif_bind_edit (A/book — chapter binding)."""

    op: Annotated[

        Literal["bind", "unbind"],

        Field(description=(

            "WHICH OPERATION to perform — the dispatch discriminator: bind | unbind. "

            "Every other argument is optional in the schema because this is a flat superset: "

            "each op reads only ITS OWN fields, and this tool's description says which those are. "

            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."

        )),

    ]
    project_id: str | None = None   # both
    node_id: str | None = None      # both
    motif_id: str | None = None     # bind
    role_bindings: dict[str, str] | None = None  # bind
    undo_token: dict | None = None  # unbind


@mcp_server.tool(
    name="composition_motif_bind_edit",
    description=(
        "Bind a motif to a chapter or unbind it — the unified chapter-motif-binding entry point. "
        "op=bind instantiates the motif's beats as scene nodes + maps roles to glossary entities "
        "(needs project_id + node_id + motif_id; optional role_bindings {role_key: entity_id}; "
        "re-binding archives the prior scenes, reversible). op=unbind archives the binding + derived "
        "scenes (needs project_id + node_id; pass the bind's undo_token to do the EXACT inverse, omit "
        "to CLEAR the chapter's motif). EDIT on the book required; auto-applied with an Undo hint."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["bind motif", "apply motif", "attach pattern to chapter", "set chapter motif",
                  "unbind motif", "remove motif", "clear chapter motif", "swap motif",
                  "bind", "bind it to", "attach the motif", "use this motif here",
                  "tie the motif to"],
        tool_name="composition_motif_bind_edit",
    ),
)
async def composition_motif_bind_edit(ctx: MCPContext, args: _MotifBindEditArgs) -> dict:
    """Unified chapter-motif-binding dispatch — delegates to the SAME per-op handlers."""
    if args.op == "bind":
        if not args.project_id or not args.node_id or not args.motif_id:
            raise ValueError("op=bind requires project_id, node_id, and motif_id")
        return await composition_motif_bind(ctx, _MotifBindArgs(
            project_id=args.project_id, node_id=args.node_id, motif_id=args.motif_id,
            **_present(role_bindings=args.role_bindings),
        ))
    # op == "unbind"
    if not args.project_id or not args.node_id:
        raise ValueError("op=unbind requires project_id and node_id")
    return await composition_motif_unbind(
        ctx, project_id=args.project_id, node_id=args.node_id, undo_token=args.undo_token)


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
    mid = _uuid(args.motif_id, "motif_id")
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
        await _gate(tc, _uuid(args.book_id, "book_id"), GrantLevel.EDIT)
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
        await _gate(tc, _uuid(args.book_id, "book_id"), GrantLevel.EDIT)
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
    resource_id = _uuid(args.book_id, "book_id") if args.scope == "book" and args.book_id else tc.user_id
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


class _LibraryTranslateArgs(ForbidExtra):
    """Flat args for composition_library_translate (W/user — the user-paid translate)."""

    # ONE tool, two libraries. Motifs and arc templates differ in nothing this tool cares
    # about — same tier (W), same confirm-token flow, same fields, same tenancy rule — so
    # CAT-2's "merge only when the safety behaviour matches" is satisfied and two tools
    # would just be two places for the policy to drift apart. Which is exactly what
    # happened to their identity keys.
    kind: Literal["motif", "arc_template"] = "motif"
    # CAT-3: batch is `items[]`, 1..N, bounded, with PER-ITEM results. A single item is a
    # 1-element array; there is no separate singular shape to maintain.
    ids: list[str]
    # CLOSED SET — the platform's supported reading languages, so the value can only be
    # one a reader could actually be reading in. A free string here would let `auto`
    # into the write path (`language='auto'` matched zero rows and zeroed the whole
    # library once already — D-MOTIF-AUTO-LANGUAGE-ZEROES-RETRIEVAL), and would let a
    # weak model invent a locale that no read ever asks for, so the user pays for a row
    # nobody can ever see.
    target_language: Literal[
        "en", "vi", "ja", "ko", "zh-CN", "zh-TW", "es", "pt-BR", "fr", "de",
        "ru", "id", "ms", "th", "tr", "ar", "hi",
    ]
    # Set ONLY when the targets are that book's SHARED tier — EDIT-gated. Omit for your
    # own motifs.
    book_id: str | None = None
    # Re-translate one that already exists and is still fresh. Off by default: charging
    # again for wording that has not moved is the thing this whole path exists to avoid.
    force: bool = False
    # The BYOK translate model (provider-gateway invariant). Required — the engine fails
    # closed rather than reaching for a platform model, because the point of this path is
    # that the USER's model spends the USER's money.
    model_ref: str
    model_source: str = "user_model"


@mcp_server.tool(
    name="composition_library_translate",
    description=(
        "PROPOSE translating YOUR OWN library items into another language — set "
        "kind='motif' (default) or kind='arc_template'. The item keeps its original "
        "language and GAINS a translation, so it reads in the reader's language with "
        "per-leaf fallback; nothing is overwritten. The platform's built-in motifs "
        "already ship in every supported language for free and cannot be translated "
        "here; this is for items you authored or adopted. Spends LLM tokens with YOUR "
        "model, so it is cost-gated: it returns a confirm_token + a $ estimate; nothing "
        "runs until you confirm via confirm_action, then it runs as a background job you "
        "poll with composition_get_mine_job. An existing, still-current translation is "
        "skipped rather than re-charged unless force=true, and a hand-written "
        "translation is never overwritten. Results are PER ITEM."
    ),
    meta=require_meta(
        "W", "user",
        synonyms=["translate motif", "translate my motifs", "translate arc template",
                  "localize motif", "localize my library", "motif in Vietnamese",
                  "dịch motif", "dịch thư viện", "翻译motif",
                  "make my motifs readable in another language"],
        # `paid` is not decoration: the _meta Completeness Law exists because an
        # undeclared spender runs without the approval card. This one spends the
        # user's own BYOK budget, per item.
        async_job=True, paid=True,
        tool_name="composition_library_translate",
    ),
)
async def composition_library_translate(ctx: MCPContext, args: _LibraryTranslateArgs) -> dict:
    # @small_return: Tier-W PROPOSE card — a single {confirm_token, estimate} object.
    tc = _ctx(ctx)
    if not args.ids:
        return {"success": False, "error": "ids is required"}
    if len(args.ids) > MAX_ITEMS_PER_JOB:
        return {"success": False,
                "error": f"at most {MAX_ITEMS_PER_JOB} items per translate job"}
    try:
        item_ids = [UUID(m) for m in args.ids]
    except (ValueError, TypeError):
        return {"success": False, "error": "ids must be UUIDs"}
    if args.book_id:
        # SHARED-tier targets: EDIT on the book. Re-checked at confirm AND per-item in
        # the engine — a proposal is not a standing authorization.
        await _gate(tc, _uuid(args.book_id, "book_id"), GrantLevel.EDIT)

    repo = (MotifRepo if args.kind == "motif" else ArcTemplateRepo)(get_pool())
    allowed = await repo.list_translatable(
        tc.user_id, item_ids, book_id=_uuid(args.book_id, "book_id") if args.book_id else None)
    if not allowed:
        # Uniform refusal — it does not distinguish "does not exist" from "is a system
        # row" from "is not yours" (no enumeration oracle). The message names the one
        # thing a user can act on.
        noun = "motifs" if args.kind == "motif" else "arc templates"
        return {
            "success": False,
            "error": f"none of those {noun} are yours to translate — the built-in "
                     f"library already ships in every supported language, and a public "
                     f"item must be adopted into your library first",
        }

    estimate = _translate_estimate(allowed, args.target_language, args.kind)
    payload = {
        "kind": args.kind,
        "ids": [str(m["id"]) for m in allowed],
        "target_language": args.target_language,
        "book_id": args.book_id,
        "force": args.force,
        "model_ref": args.model_ref,
        "model_source": args.model_source,
        "estimate_usd": estimate["estimated_usd"],
    }
    # resource_id binds the token: the named book for a shared-tier translate, else the
    # user (both libraries are user-scoped).
    resource_id = _uuid(args.book_id, "book_id") if args.book_id else tc.user_id
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret,
        tc.user_id, resource_id, _LIBRARY_TRANSLATE_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _LIBRARY_TRANSLATE_DESCRIPTOR,
        "title": f"Translate {len(allowed)} {args.kind.replace(chr(95), chr(32))}(s) to "
                 f"{LANGUAGE_NAMES.get(args.target_language, args.target_language)}",
        "domain": "composition",
        "requires": "human confirmation — this spends LLM tokens",
        "estimate": estimate,
        "skipped": len(item_ids) - len(allowed),
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
                  # "extract arc template" belongs to composition_arc_extract_template;
                  # this one deconstructs an IMPORTED reference work.
                  "reverse-engineer arc", "deconstruct an imported work",
                  "analyze reference"],
        async_job=True,
        tool_name="composition_arc_import_analyze",
    ),
)
async def composition_arc_import_analyze(ctx: MCPContext, args: _ArcImportArgs) -> dict:
    # @small_return: Tier-W PROPOSE card — returns a single {confirm_token, estimate}
    # object (no set); the derived arc_template lands via the background job and is read
    # back through composition_arc_suggest.
    tc = _ctx(ctx)
    isid = _uuid(args.import_source_id, "import_source_id")
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
                  "whether the prose", "what the plan promised", "does the prose deliver",
                  "arc conformance", "beat realized", "drift check"],
        async_job=True,
        tool_name="composition_conformance_run",
    ),
)
async def composition_conformance_run(ctx: MCPContext, args: _ConformanceRunArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)
    if args.scope == "chapter":
        if not args.chapter_id:
            return {"success": False, "error": "chapter_id is required when scope='chapter'"}
        outline = OutlineRepo(get_pool())
        node = await outline.get_node(_uuid(args.chapter_id, "chapter_id"))
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
        arc_node = await StructureRepo(get_pool()).get(_uuid(args.arc_id, "arc_id"))
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
        "Poll an async motif job — the mining / arc-import / conformance / translate job a "
        "confirmed Tier-W motif action returns. Returns the job's status, its result once "
        "complete, and cost. Use to wait for a mine/import/conformance/translate to finish. "
        "Your own job only."
    ),
    meta=require_meta(
        "R", "user",
        synonyms=["mining job", "import job", "conformance job", "translate job",
                  "poll mining", "is mining done", "is the translation done",
                  "motif job status"],
        tool_name="composition_get_mine_job",
    ),
)
async def composition_get_mine_job(
    ctx: MCPContext,
    job_id: Annotated[str, "The motif job id returned by a confirmed Tier-W motif action. (a UUID)"],
) -> dict:
    """BE-7c — OWNER-scoped poll of an async motif job.

    This used to demand a `project_id` the caller COULD NEVER KNOW: a corpus/book mine
    and an arc-import are Work-LESS (project_id IS NULL), and the confirm response names
    THIS tool in its own `poll` field — so it advertised a tool that could not be called.
    The row's scope key is its OWNER (`created_by`), so gate on that. Uniform deny for
    both missing and not-yours — no enumeration oracle.
    """
    tc = _ctx(ctx)
    jobs = GenerationJobsRepo(get_pool())
    job = await jobs.get(_uuid(job_id, "job_id"))
    if job is None or job.created_by != tc.user_id:
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
                  "stale conformance", "conformance staleness",
                  "conformance check", "has the book moved", "since it last ran",
                  "is the check stale"],
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
    bid = _uuid(book_id, "book_id")
    # IX-14 — book-scoped read; the E0 VIEW gate IS the access control (the internal
    # canon-markers read inside is safe only behind it). H13 uniform on denial.
    await _gate(tc, bid, GrantLevel.VIEW)
    from app.engine.arc_conformance_orchestrate import compute_conformance_status

    return await compute_conformance_status(
        pool=get_pool(), book_client=get_book_client(), book_id=bid,
        arc_id=_uuid(arc_id, "arc_id") if arc_id else None,
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
        "canonical; nothing canonical changes at call time. mode='llm' (the DEFAULT) READS "
        "the document and enqueues an async job (poll the run); mode='rules' is a synchronous "
        "HEADING MATCHER that only fits documents whose headings use its vocabulary — pass it "
        "only when the author explicitly asks for the fast deterministic pass. model_ref is "
        "optional — omit it to use the author's default planner model "
        "(their pinned 'planner' default, else their best chat model); pass one only "
        "when the author names a specific model. Set ground_on_existing=true to CONTINUE "
        "the book — the proposer reads its existing cast/arcs/recent chapters and references "
        "them instead of re-inventing (effective only when the deploy ceiling allows it). "
        "EDIT on the book required."
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
    mode: Annotated[
        Literal["rules", "llm"],
        "llm (default) = reads the document, async job. rules = heading matcher, sync, "
        "only fits documents written in its vocabulary.",
    ] = "llm",
    model_ref: Annotated[
        str | None,
        "optional user_model id for mode='llm' — omit to use the author's default planner model.",
    ] = None,
    ground_on_existing: Annotated[
        bool,
        "CONTINUE the book: ground the proposer in its existing cast/arcs/recent chapters so it "
        "references them instead of re-inventing. Effective only when the deploy ceiling allows it "
        "(AND); a cold-start book is a no-op. Agent-parity with the planner GUI's 'Continue this book'.",
    ] = False,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    svc = _plan_svc()
    run, is_async, job_id = await svc.create_run(
        tc.user_id, bid, source_markdown=source_markdown, mode=mode,
        model_ref=_opt_uuid(model_ref), force=False,
        ground_on_existing=ground_on_existing,
    )
    detail = await svc.get_run_detail(tc.user_id, bid, run.id)
    out: dict = {
        "run_id": str(run.id),
        "async": is_async,
        "job_id": str(job_id) if job_id else None,
        "run": detail,
    }
    # A rules-mode parse that matched NOTHING is not a proposal — it is a run holding an empty
    # spec, and every downstream step (compile, the chapters that hang off it) has nothing to
    # build from. `validate.py` already knows this ("spec_has_arc" → "no arcs parsed"), but it
    # lives behind `plan_validate`, a SEPARATE tool the model has to think to call. So the
    # propose returned a plain success dict and the agent told the author their plan was ready.
    #
    # Measured 2026-08-02 (Mị Đế): the co-writer proposed a well-formed 4-chapter outline
    # headed `# Arc 1: …` / `## Chapter 1: …`, got ok=true, and the spec parsed 0 arcs — the
    # matcher wants the literal `# 1. Arc Overview` section, and NOTHING on the path told it so.
    # The `co_write` skill names this tool without the shape requirement; only the rail's notes
    # carry it, and the rail was not driving. A constraint documented in one place and enforced
    # in none is how the whole chain stayed silent.
    if not is_async and isinstance(detail, dict) and not (detail.get("arcs") or []):
        out["problem"] = "no_arcs_parsed"
        out["guidance"] = (
            "The run was created but its spec parsed ZERO arcs, so there is nothing to compile "
            "and the book gained no structure — do NOT tell the author the plan is ready. "
            "mode='rules' is a literal heading matcher: `source_markdown` must open with the "
            "line '# 1. Arc Overview' (that number and dot are required), then one '## ' "
            "heading per ARC, and under each arc one '### ' heading per beat. Re-send with that "
            "shape, or use mode='llm', which reads a document written any way."
        )
    return out


@mcp_server.tool(
    name="plan_validate",
    description="PlanForge: run the S1–S8 golden linter (+ fidelity report) on a run's spec. `passed` "
        "reflects the HARD rules only, so it can be true while advisory rules fail — read "
        "`rules[]` before telling the author the plan is clean. Each rule also carries "
        "`applicable`: false means the rule had nothing to check here (a rule about a named "
        "entity says nothing about a book without one), so neither its ✓ nor its ✗ is a "
        "verdict. VIEW required.",
    meta=require_meta("R", "book", synonyms=["validate plan", "check spec", "golden rules"], tool_name="plan_validate"),
)
async def plan_validate(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.VIEW)
    report = await _plan_svc().validate(tc.user_id, bid, _uuid(run_id, "run_id"))
    if report is None:
        raise uniform_not_accessible()
    return report


@mcp_server.tool(
    name="plan_find_missing_material",
    description=(
        "PlanForge: for everything the plan is MISSING, look for it in the author's own document "
        "first. Returns FOUR buckets. recovered = the plan already has this, from the read — "
        "nothing to do, but say so rather than reporting it as a gap. review = verbatim lines found in their document — SHOW these "
        "and let the author keep or drop each one; they are candidates, not answers (measured: a "
        "search's three offered lines were all the wrong kind). ask = the search ran and honestly "
        "found nothing, so this genuinely needs a question — the question text is included. "
        "unavailable = the search could not run; do NOT turn these into questions, you would be "
        "asking the author to rewrite what they may already have written. Costs one LLM call per "
        "missing kind. Read-only, settles nothing. EDIT on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["what is my plan missing", "find missing material", "did I already write this"],
        paid=True, tool_name="plan_find_missing_material",
    ),
)
async def plan_find_missing_material(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    model_ref: Annotated[
        str | None,
        "optional user_model id — omit to use the author's default planner model.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    # EDIT rather than VIEW: this spends the author's LLM budget, which a read grant does not entitle.
    await _gate(tc, bid, GrantLevel.EDIT)
    out = await _plan_svc().find_missing_material(
        tc.user_id, bid, _uuid(run_id, "run_id"), model_ref=_opt_uuid(model_ref),
    )
    if out is None:
        raise uniform_not_accessible()
    return out


@mcp_server.tool(
    name="plan_get_missing_material",
    description=(
        "PlanForge: the LAST material packet for a run, without running a new search — free, and it "
        "spends nothing. Use this before plan_find_missing_material so the author does not pay twice "
        "for the same answer. Returns null if none was ever computed. `stale: true` means the plan "
        "has changed since; the lines are still the author's own words, but say so before acting. "
        "VIEW on the book required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["last material check", "what did we find before"],
        tool_name="plan_get_missing_material",
    ),
)
async def plan_get_missing_material(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.VIEW)
    rid = _uuid(run_id, "run_id")
    out = await _plan_svc().get_material_review(tc.user_id, bid, rid)
    if out is None:
        # `get_material_review` reads the artifact and never looks the RUN up, so None meant two
        # different things and this handler reported both as "no material check has been run for
        # this plan yet" — asserting the plan exists. Measured: a fabricated run_id got that
        # sentence, while plan_find_missing_material and plan_bootstrap_propose answer "not found
        # or not accessible" for the same id. Three tools, one namespace, one run, two stories —
        # and an agent that believes this one goes on to call the search, which then refuses.
        if await _plan_svc().get_run_detail(tc.user_id, bid, rid) is None:
            raise uniform_not_accessible()
        return {"packet": None, "note": "no material check has been run for this plan yet"}
    return out


@mcp_server.tool(
    name="plan_keep_material",
    description=(
        "PlanForge: write the lines the author KEPT from plan_find_missing_material into the run's "
        "spec, verbatim. Pass kept as {kind: [exact quote, ...]} using ONLY quotes the author "
        "explicitly kept — never a line they dropped, and never one you wrote. No model runs; the "
        "text goes in unchanged. writing_principles and open_questions land in their spec slot; the "
        "other kinds are filed under author_notes (a raw line is not a structured variable or arc, "
        "and guessing the missing fields would stop it being the author's words) — the reply's "
        "applied_to_slot vs carried_as_author_notes says which happened. EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["keep this line", "yes add that to the plan", "accept material",
                  "keep the material", "add that to the plan", "keep what we found",
                  "hold on to that"],
        tool_name="plan_keep_material",
    ),
)
async def plan_keep_material(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
    kept: Annotated[
        dict[str, list[Any]],
        "{planning kind: [entry, ...]}. An entry is either the exact quote as a string, or "
        "{quote, label} — copy the quote from plan_find_missing_material character for character. "
        "A LABEL is the one field a structured kind needs and you must NOT invent it: ask the "
        "author what to call the character / rule / variable / arc. With a label the line becomes a "
        "real row in the plan; without one it is filed as an author note (which does reach the "
        "planning prompts, but is not a row).",
    ],
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    out = await _plan_svc().keep_material(tc.user_id, bid, _uuid(run_id, "run_id"), kept=kept)
    if out is None:
        raise uniform_not_accessible()
    return out


@mcp_server.tool(
    name="plan_self_check",
    description=(
        "PlanForge: what a run's spec is MISSING. Returns coverage_board — for each planning kind "
        "(cast, mechanics, variables, arcs, writing principles, open questions) whether the read "
        "recovered it, up to six examples of what it found, and status 'present'/'absent'/'unknown'. "
        "'unknown' means the read itself failed or left sections unclassified, so absence cannot be "
        "claimed — do NOT report an 'unknown' kind to the author as missing. Also returns gaps + "
        "fidelity_score. `gaps` is ALWAYS computed — from the run's own document when it has one, "
        "otherwise from a consistency audit + rule check of the spec itself — because an empty "
        "list would read as 'your plan is fine' when it actually means 'nothing was computed'. "
        "`fidelity_score` IS None unless the run has its own rubric; a gap whose detail cites a "
        "threshold as 'the POC fixture's, not a standard' is telling you the same thing about "
        "itself. VIEW required."
    ),
    meta=require_meta("R", "book", synonyms=["self check plan", "plan gaps", "what is missing"], tool_name="plan_self_check"),
)
async def plan_self_check(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.VIEW)
    out = await _plan_svc().self_check(tc.user_id, bid, _uuid(run_id, "run_id"))
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
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    out = await _plan_svc().interpret(
        tc.user_id, bid, _uuid(run_id, "run_id"),
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
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        mode, payload = await _plan_svc().refine(
            tc.user_id, bid, _uuid(run_id, "run_id"),
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
        "the only way the compiler proceeds past it. `edits` revises that pass's artifact and "
        "saves a NEW one, which stales everything downstream by derivation (that is intended: "
        "scenes planned against the old cast should not survive an edit to the cast). For 'cast' "
        "(cast/roster) and 'beats' the list you send REPLACES the whole list — a shorter list "
        "DELETES members; other fields deep-merge. `approved=false` WITH `edits` HOLDS the pass "
        "with your revision (does not reject it). Accepting 'cast' requires its glossary seed "
        "proposal to have been APPLIED. No LLM. EDIT required."
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
        "Optional revision to the pass's artifact (pass_id required). For cast/beats the list "
        "you send REPLACES the list wholesale (a shorter list deletes); other fields deep-merge. "
        "Saves a NEW artifact; downstream passes go stale by derivation. approved=false + edits "
        "holds the pass with your revision rather than rejecting it.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        out = await _plan_svc().review_checkpoint(
            tc.user_id, bid, _uuid(run_id, "run_id"), approved=approved,
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
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    out = await _plan_svc().handoff_autofix(
        tc.user_id, bid, _uuid(run_id, "run_id"), model_ref=_opt_uuid(model_ref), max_rounds=max_rounds,
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
        "planner model. `structure_template_id` picks the STORY STRUCTURE (the ordered beats the "
        "'beats' pass maps chapters onto — Save the Cat, Hero's Journey, Story Circle, Web Novel "
        "Arc, Kishōtenketsu, Three-Act, or the author's own); omit it to keep the run's current "
        "choice, or the platform default if none was made. The compiled package reports which "
        "structure was used and why under `structure`. EDIT required."
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
    arc_id: Annotated[str, "The arc to compile (e.g. 'arc_2'). (a UUID)"],
    run_pipeline: Annotated[bool, "Also start the planning pipeline job."] = False,
    model_ref: Annotated[
        str | None,
        "optional user_model id for run_pipeline=true — omit to use the author's default planner model.",
    ] = None,
    structure_template_id: Annotated[
        str | None,
        "optional structure_template id — the ordered story beats this plan is shaped by. Omit to "
        "keep the run's current choice (or the recorded platform default). List the available "
        "structures with composition_structure_template_edit(op='list').",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        mode, payload = await _plan_svc().compile(
            tc.user_id, bid, _uuid(run_id, "run_id"),
            arc_id=arc_id, run_pipeline=run_pipeline, model_ref=_opt_uuid(model_ref),
            structure_template_id=_opt_uuid(structure_template_id),
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
        synonyms=["run pass", "run compiler pass", "plan cast", "plan the scenes", "next pass",
                  "run the next pass", "do the cast pass", "next compiler pass",
                  "run the pass on my plan"],
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
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        return await _plan_svc().run_pass(
            tc.user_id, bid, _uuid(run_id, "run_id"), pass_id,
            model_ref=_opt_uuid(model_ref), params=params or {}, force=False,
        )
    except UpstreamStale as exc:
        # The gate doing its job. The agent gets the BLOCKERS, not a bare failure — so its next move
        # is "accept the cast" rather than a blind retry that will refuse identically forever.
        # TOOLV2 LOOP #216 — the blockers must ride under `detail` to survive the C4 body.
        # Under their own keys they were dropped, which made the comment above false: the
        # agent got "upstream not ready" and nothing to act on, i.e. exactly the blind
        # retry it was written to prevent.
        return {
            "success": False, "error": "upstream not ready",
            "detail": {"pass_id": exc.pass_id, "blockers": exc.blockers,
                       "message": str(exc)},
        }
    except ValueError as exc:
        return {"success": False, "error": "cannot run pass", "detail": str(exc)[:300]}


@mcp_server.tool(
    name="plan_pass_status",
    description=(
        "PlanForge v2: the run's pass ledger — per pass: status, decision, whether it is FRESH, and "
        "the artifact it produced; plus `runnable_now` (the passes whose dependencies are already "
        "satisfied — start here), `pass_cursor` (how far the compiler can proceed unattended) "
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
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.VIEW)
    out = await _plan_svc().pass_status(tc.user_id, bid, _uuid(run_id, "run_id"))
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
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    try:
        return await _plan_svc().relink(tc.user_id, bid, _uuid(run_id, "run_id"), target=target)
    except LookupError:
        raise uniform_not_accessible()
    except ValueError as exc:
        return {"success": False, "error": "cannot link", "detail": str(exc)[:300]}


# ── PlanForge auto-bootstrap MATERIALISE — the MCP half of the REST bootstrap gate ─────────────
#
# `plan_compile` + the passes build the composition spec tree (structure_node + outline_node), but
# the manuscript chapters the drafting subagent writes into are BOOK-service rows the compiler never
# creates. The bootstrap gate (BootstrapService.propose→approve→apply) is what turns a compiled
# plan's planned chapters into real book chapters (and stamps outline_node.chapter_id so the scenes
# hang off them). It shipped REST-only, so an AGENT could not drive it — which broke the "chat builds
# the foundation, then hands compile+draft to the subagent" handoff (MCP-first invariant). These two
# tools are the agent surface: PREVIEW (propose, writes nothing) then a CONFIRM-gated CREATE (apply).


def _missing_run_message(run_id: Any, rows: list[Any]) -> str:
    """The refusal for a run_id that names nothing on this book — ANSWERING ITS OWN QUESTION.

    Split out of the tool so it can be tested for what it SAYS rather than grepped for how it is
    written: a source-grep guard goes red on a harmless rewrite and stays green on a message that
    consulted nothing, which is the wrong way round.

    `rows` is the book's own plan runs (book-scoped; the caller has already passed the EDIT gate).
    """
    if rows:
        found = "; ".join(f"{r.id} (status={r.status})" for r in rows)
        remedy = (
            f" This book's plan run(s): {found}. Pass a `compiled` one as run_id."
        )
    else:
        remedy = (
            " This book has NO plan runs yet — call plan_propose_spec to create one and pass the "
            "run id it returns."
        )
    return (
        f"no plan run {run_id} on this book — that id does not name a plan run here (a run is "
        "book-scoped, so one from another book, or an id belonging to something else entirely, "
        "will not resolve)." + remedy
        + " A run must be compiled with plan_compile before this can preview it."
    )


@mcp_server.tool(
    name="plan_bootstrap_propose",
    description=(
        "PlanForge: PREVIEW the real book chapters (and any glossary seeds) a COMPILED plan would "
        "create — the bridge from a compiled plan to draftable chapters. Deterministic, no LLM, and "
        "writes NOTHING to the book: it diffs the plan's chapters against the ones that already exist "
        "and records the gap as a proposal. The run must be compiled first (plan_compile). Follow with "
        "plan_bootstrap_apply (using the returned proposal_id) to actually create the chapters. Returns "
        "proposal_id + the chapter titles it would create. EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["preview chapters from plan", "materialize plan chapters", "what chapters will this make",
                  "bridge plan to chapters"],
        tool_name="plan_bootstrap_propose",
    ),
)
async def plan_bootstrap_propose(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The compiled plan run (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    svc = await get_bootstrap_service()
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    # 🔴 SHAPE BEFORE STATE, and the sibling already does this: `plan_bootstrap_apply` validates
    # `_uuid(proposal_id, "proposal_id")` OUTSIDE its try with the comment "validate shape before
    # minting". Here `_uuid` sat INSIDE the try, so a malformed id raised ValueError and was caught
    # by the not-yet-compiled arm below — reporting a BAD ARGUMENT as a STATE problem.
    #
    # MEASURED LIVE 2026-08-12: the model called this with run_id="arc_1" (an arc id, not a run id)
    # and was told "cannot preview", the sentence that means "run has no compiled package yet —
    # call compile() first". The run in question WAS compiled and had three package artifacts, so
    # the one hint it got pointed at the one thing that was not wrong.
    rid = _uuid(run_id, "run_id")
    try:
        rec = await svc.propose(tc.user_id, bid, rid, bearer)
    except LookupError:
        # 🔴 THE SIBLING ONE STEP LATER IN THIS RAIL ALREADY MADE THIS ARGUMENT, and this step was
        # left on the uniform error. `plan_bootstrap_apply` says it in its own comment: the lookup
        # is book-scoped (`get_for_book`) and the caller has ALREADY passed the EDIT gate above, so
        # naming a missing run "reveals nothing they could not already read". It is not an ownership
        # oracle; it is a wrong-argument condition.
        #
        # MEASURED LIVE 2026-08-12 (journey `autonomous-drafting`, book 019ff497): the model called
        # this with the correct book_id and a run_id of 019ff497-e068-77db-89f7-9d8c298fe8cd — the
        # book's KNOWLEDGE PROJECT id, a well-formed UUID of the wrong entity. It got "not found or
        # not accessible", which names neither which id was wrong nor where a real one comes from,
        # and the journey stopped there. Note D-FJ-11 deliberately does NOT catch this upstream: a
        # syntactically valid id is accepted because "whether it is the RIGHT row is the tool's
        # question, not ours" — this is the tool answering that question.
        #
        # 🔴 AND THE REFUSAL ANSWERS ITS OWN QUESTION. Measured live 2026-08-12 with the message
        # below in its first form (which named `plan_propose_spec` and nothing else): the model
        # replied "I'll find your plan: I'll look for the most recent plan we've worked on" and
        # then stopped and asked the author. Its instinct was RIGHT and the sentence sent it the
        # wrong way — this book already holds a COMPILED run, so "create a run" means re-planning
        # a planned book, and the model correctly declined to do that on its own.
        #
        # The ids are one book-scoped read away, on a caller who has already passed the EDIT gate
        # one line above — the same argument the sibling `plan_bootstrap_apply` makes for naming a
        # missing proposal. So NAME THEM. This is the D-FJ-3/D-FJ-5 shape one more time: the
        # information was available at the moment of the refusal and thrown away, leaving the
        # caller to guess at what the tool could simply have said.
        try:
            from app.db.repositories.plan_runs import PlanRunsRepo

            rows, _ = await PlanRunsRepo(get_pool()).list_for_book(bid, limit=5)
        except Exception:  # noqa: BLE001 — the listing is an ENRICHMENT; never mask the real error
            logger.warning("bootstrap_propose: could not list this book's plan runs", exc_info=True)
            rows = []
        raise ToolError(_missing_run_message(run_id, rows))
    except ValueError as exc:
        # e.g. "run has no compiled package yet — call compile() first"
        #
        # 🔴 THE REASON GOES IN THE ERROR, not only beside it. Measured live 2026-08-12: the caller
        # received `error: "cannot preview"` with `result: null` and the `detail` nowhere in sight —
        # the envelope carried the label and dropped the explanation, which is the same
        # discard-the-signal shape as a failure emitted with no message. Putting it in the string
        # makes it unlosable by any envelope between here and the model.
        return {
            "success": False,
            "error": f"cannot preview — {str(exc)[:300]}",
            "detail": str(exc)[:300],
        }
    diff = rec.diff or {}
    chapters = diff.get("new_chapters", [])
    return {
        "proposal_id": str(rec.id),
        "status": rec.status,
        "new_chapters_count": len(chapters),
        "new_chapters": [{"title": c.get("title"), "ordinal": c.get("ordinal")} for c in chapters],
        "new_glossary_entities_count": len(diff.get("new_glossary_entities", [])),
    }


@mcp_server.tool(
    name="plan_bootstrap_apply",
    description=(
        "PlanForge: CREATE the real book chapters a plan_bootstrap_propose previewed (and seed any "
        "proposed glossary entities), turning the compiled plan into chapters the drafting subagent can "
        "write into. This WRITES to the book (new chapters), so it is CONFIRM-GATED: it returns a "
        "`confirm_token` + descriptor and creates nothing until confirmed. Deterministic, no LLM. Pass "
        "the proposal_id from plan_bootstrap_propose. EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["create the chapters", "make the plan real", "apply materialize", "build the chapters"],
        tool_name="plan_bootstrap_apply",
    ),
)
async def plan_bootstrap_apply(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    proposal_id: Annotated[str, "The proposal from plan_bootstrap_propose (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    pid = _uuid(proposal_id, "proposal_id")  # validate shape before minting
    # ...and validate that it EXISTS. Shape-only was the whole check: a fabricated but
    # well-formed UUID minted a token, the confirm card rendered it as a normal action, and only
    # the confirm failed — with `{"code": "action_error"}` and no message, so nobody could tell
    # why. For a tool that CREATES REAL CHAPTERS that is the worst place to discover it. The
    # lookup is book-scoped (get_for_book) and the caller has already passed the EDIT gate above,
    # so this reveals nothing they could not already read.
    svc = await get_bootstrap_service()
    rec = await svc.get(bid, pid)
    if rec is None:
        raise ToolError(
            f"no bootstrap proposal {pid} on this book — run plan_bootstrap_propose first and "
            "pass the proposal_id it returns (a proposal is book-scoped, so one from another "
            "book will not resolve here)"
        )
    diff = rec.diff or {}
    chapters = diff.get("new_chapters", [])
    payload = {"book_id": str(bid), "proposal_id": str(pid)}
    confirm_token = mint_confirm_token(
        settings.confirm_token_signing_secret, tc.user_id, bid, _BOOTSTRAP_APPLY_DESCRIPTOR, payload,
    )
    return {
        "confirm_token": confirm_token,
        "descriptor": _BOOTSTRAP_APPLY_DESCRIPTOR,
        "book_id": str(bid),
        "proposal_id": str(pid),
        # The mint returned nothing but the ids it was handed, so the agent had nothing to tell
        # the human it was asking to approve. These are the same numbers plan_bootstrap_propose
        # already computes from the same diff — one computation, two consumers.
        "summary": (
            f"create {len(chapters)} chapter(s)"
            + (f" + seed {len(diff.get('new_glossary_entities', []))} glossary entit(ies)"
               if diff.get("new_glossary_entities") else "")
        ),
        "new_chapters_count": len(chapters),
        "new_glossary_entities_count": len(diff.get("new_glossary_entities", [])),
    }


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
                  # "ls" -> "ls -R": book_list is the unified "ls"; this is the recursive
                  # whole-book read, which its own description already calls `ls -R`.
                  "ls -R", "orient me", "show me the book", "book at a glance"],
        tool_name="composition_package_tree",
    ),
)
async def composition_package_tree(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
) -> dict:
    from app.services.agent_native import Block, arc_line, cap_arcs

    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
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
        "Composition-scope: for the PROSE side also call glossary_get_entity (it carries the "
        "chapter links + evidence), and for the GRAPH side kg_entity_edge_timeline — this tool "
        "does not federate to them. VIEW required."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["find references", "where is this character used", "who uses this entity",
                  "parts of the book use", "which parts use", "where does this character appear",
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
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.VIEW)

    # No Work resolution here: all eight sources are BOOK-scoped, and the E0 gate above is the
    # book gate. Resolving a project we would never use was how a book_id ended up in a project slot.
    pool = get_pool()
    eid = _uuid(entity_id, "entity_id")
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
                "Composition scope only. The prose side is glossary_get_entity (chapter links + "
                "evidence); the graph side is kg_entity_edge_timeline."
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
    from app.services.agent_native import build_book_diagnostics

    tc = _ctx(ctx)
    bid = _uuid(book_id, "book_id")
    await _gate(tc, bid, GrantLevel.VIEW)

    pool = get_pool()
    _work, pid = await resolve_scope(WorksRepo(pool), bid)

    # Clamp ONCE. The row slices below used the RAW arg while the ranked cap clamped it — a
    # negative `limit` would have sliced from the end.
    cap = max(1, min(int(limit or 25), 100))

    diag = await build_book_diagnostics(
        pool, book_id=bid, project_id=pid, user_id=tc.user_id, cap=cap,
    )
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
        # "story structure" -> "arc structure": the outline tool owns the plain phrase.
        # "arc structure" DROPPED, not re-homed: composition_arc_suggest already declared
        # it, and this tool has six other phrasings. My first de-dup swapped one tie for
        # another by not checking the REPLACEMENT was free.
        synonyms=["list arcs", "arc tree", "sagas", "book architecture",
                  "spec tree", "arc grouping"],
        ambient_book=True,
        tool_name="composition_arc_list",
    ),
)
async def composition_arc_list(
    ctx: MCPContext,
    book_id: Annotated[str | None, "The book whose spec tree to list. Omit inside a book studio — the current book is used."] = None,
    include_archived: Annotated[bool, "Include soft-archived arcs."] = False,
) -> dict:
    tc = _ctx(ctx)
    bid = _resolve_bid(tc, book_id)
    await _gate(tc, bid, GrantLevel.VIEW)
    structures = StructureRepo(get_pool())
    nodes = await structures.list_tree(bid, include_archived=include_archived)
    return {"nodes": [n.model_dump(mode="json") for n in nodes], "book_id": book_id}


@mcp_server.tool(
    name="composition_arc_get",
    description=(
        "Read ONE arc/saga by id, ENRICHED with everything the arc inspector needs: "
        "the node's own fields + `version` (the OCC token for composition_arc_edit), "
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
    node_id: Annotated[str, "The arc/saga (structure_node) id. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, _uuid(node_id, "node_id"), GrantLevel.VIEW)
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
    # BE-A1: the agent door read the SAME raw strided span() the REST detail door did — a
    # different unit than the list route (ordinals). Serve the dense-ranked derived block so
    # the agent and the Hub agree; leave span() (the packer's raw axis) untouched. Archived
    # node ⇒ absent ⇒ NULL block (not a computed 0).
    _block = (await structures.derived_blocks(node.book_id)).get(node.id)
    out["span"] = _block["span"] if _block else None
    out["chapter_count"] = _block["chapter_count"] if _block else None
    out["is_contiguous"] = _block["is_contiguous"] if _block else None
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
    # D-ARC-TRACKS-ROSTER-SCHEMA — the SAME key invariant as the REST door (spec 32a §A):
    # a missing/empty/duplicate entry key corrupts the cascade merge. FastMCP may strip the
    # nested schema from the advertised tool JSON, but the validator still fires at call time.
    _v_tracks = field_validator("tracks")(validate_track_dicts)
    _v_roster = field_validator("roster")(validate_roster_dicts)
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
        visibility="legacy", superseded_by="composition_arc_edit",  # S3 2026-07-25
        tool_name="composition_arc_create",
    ),
)
async def composition_arc_create(ctx: MCPContext, args: _ArcCreateArgs) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(args.book_id, "book_id")
    # Creating INTO a book is a package WRITE → EDIT on the book (the supplied
    # book_id IS the scope; a cross-book parent_arc_id is caught by the trigger).
    await _gate(tc, bid, GrantLevel.EDIT)
    structures = StructureRepo(get_pool())
    # K13 (2026-07-23) — idempotency guard against the agent double-firing this Tier-A
    # create. LIVE-PROBED: two byte-identical calls made TWO arcs. The agent loop was
    # measured re-issuing an identical Tier-A write across iterations even after an
    # explicit success result, and Tier-A auto-commits are bounded only by
    # TIER_A_SAME_OP_CAP (5/turn) — so one intent could mint five arcs. Same shape as
    # book-service's N6 chapter guard: sequential tool calls make a pre-insert lookup on
    # the non-empty natural key sufficient, and a DB unique is avoided because two arcs
    # legitimately sharing a title (different parents/tracks) is a real authoring case.
    if (args.title or "").strip():
        existing = await structures.find_node_by_title(
            bid, args.kind, args.title.strip(),
            parent_id=_uuid(args.parent_arc_id, "parent_arc_id") if args.parent_arc_id else None,
        )
        if existing is not None:
            out = existing.model_dump(mode="json")
            out["_meta"] = {"undo_hint": _undo("composition_arc_delete", node_id=str(existing.id))}
            out["note"] = (
                "an arc with this title already exists at this level — returning it "
                "instead of creating a duplicate."
            )
            return out
    try:
        node = await structures.create_node(
            bid,
            created_by=tc.user_id,
            kind=args.kind,
            title=args.title, summary=args.summary, goal=args.goal, status=args.status,
            parent_id=_uuid(args.parent_arc_id, "parent_arc_id") if args.parent_arc_id else None,
            tracks=args.tracks, roster=args.roster, roster_bindings=args.roster_bindings,
            arc_template_id=_uuid(args.arc_template_id, "arc_template_id") if args.arc_template_id else None,
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
    _v_tracks = field_validator("tracks")(validate_track_dicts)   # D-ARC-TRACKS-ROSTER-SCHEMA
    _v_roster = field_validator("roster")(validate_roster_dicts)
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
        visibility="legacy", superseded_by="composition_arc_edit",  # S3 2026-07-25
        tool_name="composition_arc_update",
    ),
)
async def composition_arc_update(ctx: MCPContext, args: _ArcUpdateArgs) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    prior = await _arc_or_deny(structures, tc, _uuid(args.node_id, "node_id"), GrantLevel.EDIT)
    patch: dict[str, Any] = {}
    for field, value in {
        "title": args.title, "summary": args.summary, "goal": args.goal,
        "status": args.status, "tracks": args.tracks, "roster": args.roster,
        "roster_bindings": args.roster_bindings, "template_version": args.template_version,
    }.items():
        if value is not None:
            patch[field] = value
    if args.arc_template_id is not None:
        patch["arc_template_id"] = _uuid(args.arc_template_id, "arc_template_id")
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
        "composition_arc_restore). Member chapters are NOT deleted, but they DO leave the "
        "arc: each one's structure_node_id is cleared into a recovery slot, so the "
        "chapters read as unplanned until composition_arc_restore puts them back. EDIT "
        "required (auto-applied; Undo restores it)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["delete arc", "archive saga", "remove arc", "delete story arc"],
        visibility="legacy", superseded_by="composition_arc_edit",  # S3 2026-07-25
        tool_name="composition_arc_delete",
    ),
)
async def composition_arc_delete(
    ctx: MCPContext,
    node_id: Annotated[str, "The arc/saga to archive. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, _uuid(node_id, "node_id"), GrantLevel.EDIT)
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
        visibility="legacy", superseded_by="composition_arc_edit",  # S3 2026-07-25
        tool_name="composition_arc_restore",
    ),
)
async def composition_arc_restore(
    ctx: MCPContext,
    node_id: Annotated[str, "The arc/saga to restore. (a UUID)"],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    # get() returns archived rows too, so _arc_or_deny resolves + gates the archived
    # node before the un-archive.
    node = await _arc_or_deny(structures, tc, _uuid(node_id, "node_id"), GrantLevel.EDIT)
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
        visibility="legacy", superseded_by="composition_arc_edit",  # S3 2026-07-25
        tool_name="composition_arc_move",
    ),
)
async def composition_arc_move(ctx: MCPContext, args: _ArcMoveArgs) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, _uuid(args.node_id, "node_id"), GrantLevel.EDIT)
    # TOOLV2 LOOP #150 — diagnose a CYCLE before the depth guard misattributes it.
    #
    # The DB trigger enforces both, and correctly refuses either. But it checks depth BEFORE it
    # walks for a cycle, and the cap is depth 2 — so moving a node under its own descendant
    # almost always trips the depth branch first. Measured: A (depth 1) under its own child B
    # (depth 2) was refused with "structure_node depth 3 exceeds saga→arc→sub-arc", which sends
    # the caller looking for a shallower parent when the real problem is that the target sits
    # BENEATH the node being moved. Advice that cannot succeed is worse than none.
    #
    # The trigger stays the integrity SSOT — this only names the cause, and only for the case
    # its ordering hides. Walking up from the proposed parent is bounded by the depth cap.
    if args.new_parent_arc_id:
        walker = _uuid(args.new_parent_arc_id, "new_parent_arc_id")
        seen: set = set()
        while walker is not None and walker not in seen:
            if walker == node.id:
                return {
                    "success": False,
                    "error": (
                        "that parent is inside the arc you are moving — an arc cannot become its "
                        "own descendant. Move it under an arc outside this subtree, or move the "
                        "child out first (composition_arc_list shows the tree)."
                    ),
                    "detail": f"cycle: {args.new_parent_arc_id} is below {node.id}",
                }
            seen.add(walker)
            ancestor = await structures.get(walker)
            walker = ancestor.parent_id if ancestor is not None else None
    try:
        moved = await structures.move(
            node.id,
            new_parent_id=_uuid(args.new_parent_arc_id, "new_parent_arc_id") if args.new_parent_arc_id else None,
            after_id=_uuid(args.after_id, "after_id") if args.after_id else None,
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
    # BE-A3: null UNASSIGNS (returns the chapters to the unplanned pool). Add-only assign left
    # a state the ?unassigned read could show but no writer could produce (GG-2).
    structure_node_id: str | None = None
    chapter_node_ids: list[str]


@mcp_server.tool(
    name="composition_arc_assign_chapters",
    description=(
        "Attach CHAPTER-kind outline nodes to an arc (sets their structure_node_id) "
        "— the membership that makes an arc's derived span and open-promise rollup "
        "real — OR pass `structure_node_id: null` to UNASSIGN them (return to the "
        "unplanned pool). Book-scoped both sides: only chapters in `book_id` are "
        "touched, and an assign only if `structure_node_id` is itself in that book. "
        "Returns the count. EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["assign chapters", "attach chapters to arc", "arc membership",
                  "add chapters to arc", "group chapters under arc"],
        visibility="legacy", superseded_by="composition_arc_edit",  # S3 2026-07-25
        tool_name="composition_arc_assign_chapters",
    ),
)
async def composition_arc_assign_chapters(
    ctx: MCPContext, args: _ArcAssignChaptersArgs,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(args.book_id, "book_id")
    await _gate(tc, bid, GrantLevel.EDIT)
    structures = StructureRepo(get_pool())
    target = _uuid(args.structure_node_id, "structure_node_id") if args.structure_node_id else None
    count = await structures.assign_chapters(
        bid, target, [UUID(c) for c in args.chapter_node_ids],
    )
    if count == 0 and args.chapter_node_ids:
        # TOOLV2 LOOP #143 — a zero here used to be reported as a success.
        #
        # Measured on the first ever invocation: an unknown arc id, an unknown chapter id and
        # an empty list all returned {"assigned": 0} with no error and no way to tell them
        # apart. The caller mistypes one uuid out of two and is told the write succeeded,
        # having changed nothing. The repo is right to no-op (its EXISTS guard stops an arc
        # adopting another book's chapters); what was missing is saying so.
        #
        # The empty-list case is deliberately NOT an error — asking to move no chapters is
        # satisfied by doing nothing — so this branch only fires when the caller named some.
        if target is not None:
            node = await structures.get(target)
            if node is None or node.book_id != bid:
                raise ValueError(
                    "structure_node_id is not an arc in this book — an arc never adopts "
                    "chapters from another book (call composition_arc_list for this book's "
                    "arc ids)"
                )
        raise ValueError(
            "none of those chapter_node_ids is an active CHAPTER-kind outline node in this "
            "book, so nothing was assigned — check the ids (call composition_list_outline "
            "for the book's chapter nodes); note these are OUTLINE NODE ids, not book "
            "chapter ids"
        )
    return {
        "assigned": count, "structure_node_id": args.structure_node_id,
        "_meta": {"undo_hint": None},
    }


# ── S3 catalog-unification (2026-07-25): composition_arc_edit (op=create|update|delete|
# restore|move|assign_chapters) SUPERSEDES the 6 per-op arc-CRUD tools above (kept,
# visibility:legacy — still callable for cached workflows/schemas, hidden from the default
# discovery surface). Same tier (A/book), same cores: it DELEGATES to the legacy handlers
# (NO logic moved), so every guard, Undo hint, and conflict shape is preserved verbatim.
# Mirrors KG's kg_view_edit / kg_ontology_propose op-dispatch. Reads stay separate
# (composition_arc_get / composition_arc_list) — different response contracts. ──────────
def _present(**kwargs: Any) -> dict[str, Any]:
    """Keep only the args the caller actually supplied (drop None) so each sub-Args model
    applies its OWN defaults. A flat-superset op tool must never force None onto a field
    whose default is a non-None value (e.g. _ArcCreateArgs.status='outline' — passing None
    would fail the Literal validation). Use for CREATE and for updates whose handler treats
    None as 'unchanged' (the `if value is not None` pattern)."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _passed(args: Any, *names: str) -> dict[str, Any]:
    """Forward only the fields the caller EXPLICITLY set (via `model_fields_set`), INCLUDING an
    explicit None. Unlike `_present` (drop-None), this PRESERVES null-as-clear semantics for a
    PATCH handler that builds its SET clause from `model_fields_set` / `model_dump(exclude_unset=
    True)` — e.g. `motif_patch` clears `emotion_target` on an explicit null. A flat op superset
    otherwise collapses absent-vs-null (both arrive None); routing the caller's own
    `model_fields_set` is what keeps the two distinguishable through the wrapper."""
    fs = args.model_fields_set
    return {n: getattr(args, n) for n in names if n in fs}


class _ArcEditArgs(ForbidExtra):
    """Flat superset for composition_arc_edit; each op reads only its own fields. Wrapped
    (like KgOntologyProposeArgs) so Pydantic stays the single validation truth; FastMCP
    flattens it on the wire (K16)."""

    op: Annotated[

        Literal["create", "update", "delete", "restore", "move", "assign_chapters"],

        Field(description=(

            "WHICH OPERATION to perform — the dispatch discriminator: create | update | delete | restore | move | assign_chapters. "

            "Every other argument is optional in the schema because this is a flat superset: "

            "each op reads only ITS OWN fields, and this tool's description says which those are. "

            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."

        )),

    ]
    book_id: str | None = None          # create, assign_chapters
    node_id: str | None = None          # update, delete, restore, move
    kind: Literal["saga", "arc"] | None = None   # create
    parent_arc_id: str | None = None    # create
    title: str | None = None            # create, update
    summary: str | None = None          # create, update
    goal: str | None = None             # create, update
    status: _ArcStatus | None = None    # create, update
    tracks: list[dict[str, Any]] | None = None          # create, update
    roster: list[dict[str, Any]] | None = None          # create, update
    roster_bindings: dict[str, Any] | None = None       # create, update
    arc_template_id: str | None = None  # create, update
    template_version: int | None = None  # create, update
    expected_version: int | None = None  # update (required)
    new_parent_arc_id: str | None = None  # move
    after_id: str | None = None         # move
    structure_node_id: str | None = None  # assign_chapters (null unassigns)
    chapter_node_ids: list[str] | None = None  # assign_chapters


@mcp_server.tool(
    name="composition_arc_edit",
    description=(
        "Create, edit, delete, restore, move, or (re)assign chapters to a saga/arc in a "
        "book's SPEC tree — the unified arc-CRUD entry point. "
        "op=create mints a saga/arc (needs book_id; optional kind + title/summary/goal/"
        "status/parent_arc_id/tracks/roster/roster_bindings/arc_template_id/template_version). "
        "op=update edits its content (needs node_id + expected_version — optimistic "
        "concurrency, a stale version is rejected). op=delete soft-archives it + its subtree "
        "(needs node_id; reversible via op=restore). op=restore un-archives it (needs node_id). "
        "op=move reparents+reorders it (needs node_id; new_parent_arc_id=null → root, "
        "after_id=null → first). op=assign_chapters attaches CHAPTER nodes to an arc (needs "
        "book_id + chapter_node_ids; structure_node_id=null UNASSIGNS them). EDIT on the book "
        "required; auto-applied with an Undo hint. Read with composition_arc_get / composition_arc_list."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit arc", "create arc", "new saga", "delete arc", "archive arc",
                  "restore arc", "move arc", "reparent arc", "reorder arc",
                  "assign chapters to arc", "manage arc", "author an arc"],
        tool_name="composition_arc_edit",
    ),
)
async def composition_arc_edit(ctx: MCPContext, args: _ArcEditArgs) -> dict:
    """Unified arc-CRUD dispatch — delegates to the SAME per-op handlers (no logic moved).
    Per-op required fields are validated here with a clear ValueError (→ isError)."""
    if args.op == "create":
        if not args.book_id:
            raise ValueError("op=create requires book_id")
        return await composition_arc_create(ctx, _ArcCreateArgs(
            book_id=args.book_id,
            **_present(
                kind=args.kind, parent_arc_id=args.parent_arc_id, title=args.title,
                summary=args.summary, goal=args.goal, status=args.status, tracks=args.tracks,
                roster=args.roster, roster_bindings=args.roster_bindings,
                arc_template_id=args.arc_template_id, template_version=args.template_version,
            ),
        ))
    if args.op == "update":
        if not args.node_id or args.expected_version is None:
            raise ValueError("op=update requires node_id and expected_version")
        return await composition_arc_update(ctx, _ArcUpdateArgs(
            node_id=args.node_id, expected_version=args.expected_version,
            **_present(
                title=args.title, summary=args.summary, goal=args.goal, status=args.status,
                tracks=args.tracks, roster=args.roster, roster_bindings=args.roster_bindings,
                arc_template_id=args.arc_template_id, template_version=args.template_version,
            ),
        ))
    if args.op == "delete":
        if not args.node_id:
            raise ValueError("op=delete requires node_id")
        return await composition_arc_delete(ctx, node_id=args.node_id)
    if args.op == "restore":
        if not args.node_id:
            raise ValueError("op=restore requires node_id")
        return await composition_arc_restore(ctx, node_id=args.node_id)
    if args.op == "move":
        if not args.node_id:
            raise ValueError("op=move requires node_id")
        return await composition_arc_move(ctx, _ArcMoveArgs(
            node_id=args.node_id, new_parent_arc_id=args.new_parent_arc_id,
            after_id=args.after_id))
    # op == "assign_chapters"
    if not args.book_id or args.chapter_node_ids is None:
        raise ValueError("op=assign_chapters requires book_id and chapter_node_ids")
    return await composition_arc_assign_chapters(ctx, _ArcAssignChaptersArgs(
        book_id=args.book_id, structure_node_id=args.structure_node_id,
        chapter_node_ids=args.chapter_node_ids))


# ── B2 — template ops. ⚠ CORRECTION (O-3, close-21-28): the prior comment here said
# "composition_arc_template_* CRUD stays REST-only PER BA11". That MISQUOTES BA11 — a
# comment that turned an audit FINDING into a false decision. BA11 ("Full MCP surface",
# 23:170) MANDATES the five CRUD tools (composition_arc_template_create/patch/list/get/
# adopt); 23:113 lists REST-only as the GAP, not the design. So the agent cannot create/
# edit/adopt an arc template by any means today — a GG-2 inverse gap. Building those five
# thin wrappers over the live REST routes (routers/arc.py) is orphan-slice O-3, deferred
# to the continuous run (RUN-STATE §6 D-DEFER). The three tools below (apply/extract/
# template_drift) cross the SPEC ↔ LIBRARY seam and delegate their ENGINE work to 23 A5
# (arc_apply/extract)
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
        "detail": {"pending_dependency": dep, "expected": f"{module}.{fn}"},
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
    pid = _uuid(args.project_id, "project_id")
    meta = await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
    pid = _require_project(meta)
    # IDOR: the source template must be visible to the caller (H13 on foreign/missing).
    arc_tmpl = await ArcTemplateRepo(get_pool()).get_visible(tc.user_id, _uuid(args.arc_template_id, "arc_template_id"))
    if arc_tmpl is None:
        raise uniform_not_accessible()
    # BA3 — the SHARED apply engine (the SAME path the REST route POST /works/{id}/arc/materialize
    # runs). The MCP envelope has no JWT, so we mint a short-lived service bearer for the cross-service
    # book-chapter + KAL-cast reads (the established MCP→JWT-route seam). Typed failures → error dicts.
    from app.engine.arc_apply import apply_arc_to_spec, ArcApplyError, ArcApplyConflict
    from app.clients.kal_client import get_kal_client
    bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
    try:
        result = await apply_arc_to_spec(
            get_pool(), book_id=meta.book_id, project_id=pid, arc_template=arc_tmpl,
            roster_bindings=dict(args.roster_bindings), replace=args.replace,
            idempotency_key=args.idempotency_key, created_by=tc.user_id,
            book_client=get_book_client(), kal_client=get_kal_client(),
            motifs_repo=MotifRepo(get_pool()), outline_repo=OutlineRepo(get_pool()), bearer=bearer,
        )
    except ArcApplyConflict as exc:
        return {"success": False, "outcome": "applied_conflict",
                "error": "member chapters already have scenes — retry with replace=true",
                "chapter_ids": exc.chapter_ids}
    except ArcApplyError as exc:
        return {"success": False, "error": exc.message, **exc.detail}
    out = dict(result)
    out["success"] = True
    out.setdefault("_meta", {"undo_hint": None})
    return out


class _ArcExtractTemplateArgs(ForbidExtra):
    node_id: str
    code: str
    name: str
    original_language: str = "en"
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
    node = await _arc_or_deny(structures, tc, _uuid(args.node_id, "node_id"), GrantLevel.VIEW)
    from app.engine import arc_apply as _engine  # 23 A5 (module exists; fn pending)
    fn = getattr(_engine, "extract_template_from_arc", None)
    if fn is None:
        return _pending_engine("A5", "app.engine.arc_apply", "extract_template_from_arc")
    try:
        result = await fn(
            get_pool(),
            arc_node=node, owner_user_id=tc.user_id,
            code=args.code, name=args.name, original_language=args.original_language,
            visibility=args.visibility,
        )
    except asyncpg.UniqueViolationError:
        return {
            "success": False, "outcome": "applied_conflict",
            "error": "an arc template with this code already exists in your library",
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
    node_id: Annotated[str, "The arc (structure_node) to compare against its source template. (a UUID)"],
    project_id: Annotated[str, "The Work whose realized prose the drift is measured against — its "
                               "book MUST be the arc's book (no cross-book oracle)."],
) -> dict:
    tc = _ctx(ctx)
    structures = StructureRepo(get_pool())
    node = await _arc_or_deny(structures, tc, _uuid(node_id, "node_id"), GrantLevel.VIEW)
    if node.arc_template_id is None:
        return {"available": False, "reason": "arc has no template provenance (authored directly)"}
    # SHARED path with the REST scope=arc_template_drift (conformance.py): resolve the Work (project
    # is the prose axis; a structure_node is book-scoped, so the caller names which Work), gate that
    # it is the arc's OWN book, resolve the source template, then run the SAME coarse arc report by
    # the legacy annotation key (by_structure=False). No confirm token — it is a $0 read.
    works = WorksRepo(get_pool())
    work = await works.get(_uuid(project_id, "project_id"))
    if work is None or work.book_id != node.book_id:
        raise uniform_not_accessible()
    arc_tmpl = await ArcTemplateRepo(get_pool()).get_visible(tc.user_id, node.arc_template_id)
    if arc_tmpl is None:
        return {"available": False, "reason": "the source template is no longer available"}
    from app.engine.arc_conformance_orchestrate import compute_arc_report
    from app.routers.conformance import ConformanceTraceReader
    report = await compute_arc_report(
        reader=ConformanceTraceReader(get_pool()), mrepo=MotifRepo(get_pool()),
        knowledge=get_knowledge_client(), user_id=tc.user_id, project_id=_uuid(project_id, "project_id"),
        book_id=node.book_id, arc=arc_tmpl, by_structure=False, deep=False,
    )
    return {"available": True, "report": report}


# ── BA11 — the 5 arc-template CRUD MCP tools (O-3). A comment once claimed this CRUD
# "stays REST-only per BA11" — but BA11 (23:170) is titled "Full MCP surface" and MANDATES
# these five; REST-only was the GAP it named (23:113), never the decision. They are thin
# wrappers over the SAME owner-scoped ArcTemplateRepo the REST routes use. arc_template is
# USER-tier (owner_user_id = caller), so there is NO book gate — the repo filters
# owner_user_id=caller, and a foreign/system row is a 404/no-op (the clone-to-edit
# affordance). visibility/status are closed sets via the pydantic Literal on the arg models.
# ────────────────────────────────────────────────────────────────────────────


@mcp_server.tool(
    name="composition_arc_template_list",
    description=(
        "List the caller's arc templates (reusable arc skeletons). scope=mine (yours), "
        "system (the seeded library), all (yours + system; NOT other users' public — that is "
        "the public catalog, a separate discovery surface). Owner view; embedding never projected."
    ),
    meta=require_meta("R", "book",
                      synonyms=["list arc templates", "my arc templates", "arc skeleton library"],
                      tool_name="composition_arc_template_list"),
)
async def composition_arc_template_list(
    ctx: MCPContext,
    # K20 — Literal, not `str`. These were runtime-checked closed sets advertised as bare
    # strings: the handler rejected anything else, but the model was never TOLD the set, so a
    # near-miss ("user", "published") was a hard error it had no way to avoid. A Literal makes
    # FastMCP emit a real `enum`, which is the only form the validator reads.
    scope: Annotated[Literal["mine", "system", "all"], "mine | system | all"] = "all",
    genre: Annotated[str | None, "filter by genre tag"] = None,
    status: Annotated[Literal["draft", "active", "archived"], "draft | active | archived"] = "active",
    q: Annotated[str | None, "text search over name/summary"] = None,
    # ARC-I18N: a READ preference, never a filter. It RE-WORDS the result with per-leaf
    # fallback; as a filter it could only subtract, so asking for a language nothing was
    # authored in returned an empty library instead of a translated one.
    display_language: Annotated[
        str | None, "read the library in this language (falls back per leaf; never filters)"
    ] = None,
    limit: Annotated[int, "1..100"] = 50,
) -> dict:
    tc = _ctx(ctx)
    if scope not in ("mine", "system", "all"):
        return {"error": "scope must be one of: mine, system, all"}
    if status not in ("draft", "active", "archived"):
        return {"error": "status must be one of: draft, active, archived"}
    repo = ArcTemplateRepo(get_pool())
    # K25 (2026-07-24) — OUT-5: this returned ONLY the capped slice, no total/more flag, so a
    # caller with 31 templates asking limit=5 read "you have 5 templates" — a silent
    # truncation. Fetch limit+1 and report `more` (the same signal kg_project_list uses:
    # "the repo fetches limit+1 to signal more"), which is honest without a second COUNT.
    capped = max(1, min(100, limit))
    rows = await repo.list_for_caller(
        tc.user_id, scope=("user" if scope == "mine" else scope), genre=genre,
        status=status, q=q, display_language=display_language, limit=capped + 1,
    )
    more = len(rows) > capped
    rows = rows[:capped]
    return {
        "arc_templates": [a.model_dump(mode="json") for a in rows],
        "scope": scope,
        "returned": len(rows),
        "more": more,
        "guidance": (
            f"showing {len(rows)} — more exist; raise `limit` or narrow with "
            "scope/genre/status/q. Do NOT assume this is all of them."
            if more else f"complete — all {len(rows)} matching templates returned."
        ),
    }


@mcp_server.tool(
    name="composition_arc_template_get",
    description="Read one arc template the caller can see (own or system). 404 if not visible.",
    meta=require_meta("R", "book",
                      synonyms=["get arc template", "read arc template", "show arc template"],
                      tool_name="composition_arc_template_get"),
)
async def composition_arc_template_get(
    ctx: MCPContext,
    arc_id: Annotated[str, "The arc_template id (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    arc = await ArcTemplateRepo(get_pool()).get_visible(tc.user_id, _uuid(arc_id, "arc_id"))
    if arc is None:
        raise uniform_not_accessible()
    return arc.model_dump(mode="json")


@mcp_server.tool(
    name="composition_arc_template_create",
    description=(
        "Create a PRIVATE arc template owned by the caller (a reusable arc skeleton — threads, "
        "layout, pacing, roster). Publishing/sharing a template is a deliberate human action in "
        "the studio (it runs a quota gate), so this tool creates PRIVATE only; pass visibility "
        "other than private and it is refused with that guidance. A duplicate code → 409."
    ),
    meta=require_meta("W", "book",
                      synonyms=["create arc template", "new arc template", "save arc skeleton"],
                      visibility="legacy", superseded_by="composition_arc_template_edit",  # S3
                      tool_name="composition_arc_template_create"),
)
async def composition_arc_template_create(ctx: MCPContext, args: ArcTemplateCreateArgs) -> dict:
    tc = _ctx(ctx)
    # Publish path (public/unlisted) runs a quota pre-check the agent surface should not carry —
    # keep template SHARING a deliberate studio action, not an agent side-effect.
    if args.visibility != "private":
        return {"error": "create makes a PRIVATE template; publish or share it from the studio UI"}
    try:
        arc = await ArcTemplateRepo(get_pool()).create(tc.user_id, args)
    except asyncpg.UniqueViolationError:
        return {"error": "an arc template with this code already exists"}
    return arc.model_dump(mode="json")


class _ArcTemplateUpdateArgs(ArcTemplatePatchArgs):
    arc_id: str
    expected_version: int | None = None  # optimistic concurrency; None = last-writer-wins


@mcp_server.tool(
    name="composition_arc_template_update",
    description=(
        "Edit the caller's OWN arc template (a system/foreign row never matches → 404, the "
        "clone-to-edit affordance). Optional expected_version for optimistic concurrency (→ a "
        "409-style conflict with the current row). Only fields you pass change. Flipping "
        "visibility to a shareable state is refused here — share from the studio (quota gate)."
    ),
    meta=require_meta("W", "book",
                      synonyms=["update arc template", "edit arc template", "patch arc template"],
                      visibility="legacy", superseded_by="composition_arc_template_edit",  # S3
                      tool_name="composition_arc_template_update"),
)
async def composition_arc_template_update(ctx: MCPContext, args: _ArcTemplateUpdateArgs) -> dict:
    tc = _ctx(ctx)
    if args.visibility is not None and args.visibility != "private":
        return {"error": "share/publish from the studio UI (it runs the quota gate), not here"}
    # TOOLV2 LOOP #155 — `exclude_unset` is the whole update path.
    #
    # ArcTemplateRepo.patch builds its SET list from `args.model_dump(exclude_unset=True)`, so a
    # field the caller never mentioned is meant to stay untouched. A plain model_dump() here
    # materialised EVERY optional field as an explicit None first, so the repo saw them all as set
    # and emitted `visibility = NULL` — which the NOT NULL constraint rejected. Measured: every
    # update failed, on both this tool and composition_arc_template_edit(op=update), whatever
    # fields were supplied. The op had never worked.
    #
    # The unified tool already drops unset fields with _present() before delegating here; without
    # this flag that care was undone one line later.
    patch = ArcTemplatePatchArgs(
        **args.model_dump(exclude={"arc_id", "expected_version"}, exclude_unset=True)
    )
    try:
        arc = await ArcTemplateRepo(get_pool()).patch(
            tc.user_id, _uuid(args.arc_id, "arc_id"), patch, expected_version=args.expected_version,
        )
    except VersionMismatchError as exc:
        return {"error": "version conflict", "current": exc.current.model_dump(mode="json")}
    except asyncpg.UniqueViolationError:
        return {"error": "an arc template with this code already exists"}
    if arc is None:
        raise uniform_not_accessible()
    return arc.model_dump(mode="json")


@mcp_server.tool(
    name="composition_arc_template_archive",
    description=(
        "Soft-archive the caller's OWN arc template (status='archived'). Archiving one you have "
        "already archived is a success (the end state is what you asked for); an id that is not "
        "yours is refused with the same 'not found or not accessible' its sibling ops use."
    ),
    meta=require_meta("W", "book",
                      synonyms=["archive arc template", "delete arc template", "remove arc template"],
                      visibility="legacy", superseded_by="composition_arc_template_edit",  # S3
                      tool_name="composition_arc_template_archive"),
)
async def composition_arc_template_archive(
    ctx: MCPContext,
    arc_id: Annotated[str, "The arc_template id (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    # 🔴 D-ARCHIVE-FABRICATES-SUCCESS. This discarded the repo's result and returned
    # `archived: True` unconditionally, so archiving an id that does not exist reported success
    # AND handed back an undo_hint for a row that was never there. Measured 2026-08-14 with a
    # random UUID: {"id": "<the uuid I invented>", "archived": true}, 0 rows in arc_template.
    #
    # The old description called that "no existence oracle" and that was the honest intent — but
    # the anti-oracle is already defeated by this tool's OWN siblings. Same tool, same nonexistent
    # arc_id: op=archive succeeded while op=restore and op=update both returned "not found or not
    # accessible". Anyone probing existence calls op=update, so the silence protected nothing and
    # only cost the author the truth about their own library.
    #
    # Idempotency is preserved deliberately: archiving a row you own that is ALREADY archived is
    # still a success, because the end state is the one that was asked for. Only a row that is not
    # yours refuses, which is exactly what restore and update already do.
    outcome = await ArcTemplateRepo(get_pool()).archive(tc.user_id, _uuid(arc_id, "arc_id"))
    if outcome == "not_found":
        raise uniform_not_accessible()
    # honest undo (S-08): the reverse verb is composition_arc_template_restore.
    return {"id": arc_id, "archived": True, "already_archived": outcome == "already_archived",
            "_meta": {"undo_hint": _undo("composition_arc_template_restore", arc_id=arc_id)}}


@mcp_server.tool(
    name="composition_arc_template_restore",
    description=(
        "Restore an ARCHIVED arc template of YOURS (the reverse of composition_arc_template_archive). "
        "Returns the restored template; a foreign/system/not-archived id is not restorable (uniform deny)."
    ),
    meta=require_meta("W", "book",
                      synonyms=["restore arc template", "unarchive arc template"],
                      visibility="legacy", superseded_by="composition_arc_template_edit",  # S3
                      tool_name="composition_arc_template_restore"),
)
async def composition_arc_template_restore(
    ctx: MCPContext,
    arc_id: Annotated[str, "The archived arc_template id (UUID)."],
) -> dict:
    tc = _ctx(ctx)
    arc = await ArcTemplateRepo(get_pool()).restore(tc.user_id, _uuid(arc_id, "arc_id"))
    if arc is None:
        raise uniform_not_accessible()
    out = arc.model_dump(mode="json")
    out["_meta"] = {"undo_hint": _undo("composition_arc_template_archive", arc_id=arc_id)}
    return out


# ── S3 catalog-unification (2026-07-25): composition_arc_template_edit (op=create|update|
# archive|restore) SUPERSEDES the 4 per-op arc-TEMPLATE-CRUD tools above (kept,
# visibility:legacy). Same tier (W/book), delegates to the SAME handlers (no logic moved).
# Reads stay separate (composition_arc_template_get / composition_arc_template_list). ───────
class _ArcTemplateEditArgs(ForbidExtra):
    """Flat superset for composition_arc_template_edit; each op reads only its own fields.
    Wrapped so Pydantic validates/coerces the rich sub-models (threads/layout/pacing/
    arc_roster from plain dicts); FastMCP flattens on the wire (K16)."""

    op: Annotated[

        Literal["create", "update", "archive", "restore"],

        Field(description=(

            "WHICH OPERATION to perform — the dispatch discriminator: create | update | archive | restore. "

            "Every other argument is optional in the schema because this is a flat superset: "

            "each op reads only ITS OWN fields, and this tool's description says which those are. "

            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."

        )),

    ]
    # Described for the same reason the motif ids above are: chat-service quotes a required
    # argument's OWN declaration in its refusal, and arms the catalogue tools that text names.
    arc_id: Annotated[str | None, Field(default=None, description=(
        "the arc template to act on (UUID). NOT a name — list the caller's templates with "
        "composition_arc_template_list and pass the id it returns."
    ))] = None  # update, archive, restore
    expected_version: int | None = None  # update (optional optimistic concurrency)
    code: str | None = None             # create (required)
    name: str | None = None             # create (required), update
    original_language: str | None = None   # create
    summary: str | None = None          # create, update
    genre_tags: list[str] | None = None  # create, update
    chapter_span: int | None = None     # create, update
    threads: list[dict[str, Any]] | None = None   # create, update
    layout: list[dict[str, Any]] | None = None    # create, update
    pacing: list[dict[str, Any]] | None = None    # create, update
    arc_roster: list[dict[str, Any]] | None = None  # create, update
    visibility: str | None = None       # create, update (only 'private' accepted here)
    status: str | None = None           # update


@mcp_server.tool(
    name="composition_arc_template_edit",
    description=(
        "Create, edit, archive, or restore one of YOUR arc templates (reusable arc "
        "skeletons — threads, layout, pacing, roster) — the unified template-CRUD entry point. "
        "op=create mints a PRIVATE template (needs code + name; optional original_language/summary/"
        "genre_tags/chapter_span/threads/layout/pacing/arc_roster; a duplicate code → "
        "409). op=update edits your own (needs arc_id; optional expected_version for optimistic "
        "concurrency; only the fields you pass change; a foreign/system row → 404). op=archive "
        "soft-archives yours (needs arc_id; reversible via op=restore). op=restore un-archives "
        "yours (needs arc_id). Publishing/sharing (visibility other than private) is a deliberate "
        "studio action — refused here. Read with composition_arc_template_get / composition_arc_template_list."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["edit arc template", "create arc template", "new arc template",
                  "update arc template", "archive arc template", "restore arc template",
                  "save arc skeleton", "manage arc template"],
        tool_name="composition_arc_template_edit",
    ),
)
async def composition_arc_template_edit(ctx: MCPContext, args: _ArcTemplateEditArgs) -> dict:
    """Unified arc-template CRUD dispatch — delegates to the SAME per-op handlers (no logic
    moved). Per-op required fields validated here with a clear ValueError (→ isError)."""
    if args.op == "create":
        if not args.code or not args.name:
            raise ValueError("op=create requires code and name")
        return await composition_arc_template_create(ctx, ArcTemplateCreateArgs(
            code=args.code, name=args.name,
            **_present(
                original_language=args.original_language, summary=args.summary,
                genre_tags=args.genre_tags,
                chapter_span=args.chapter_span, threads=args.threads, layout=args.layout,
                pacing=args.pacing, arc_roster=args.arc_roster, visibility=args.visibility,
            ),
        ))
    if args.op == "update":
        if not args.arc_id:
            raise ValueError("op=update requires arc_id — NOT a name. Call composition_arc_template_list to get the id, then call this again")
        return await composition_arc_template_update(ctx, _ArcTemplateUpdateArgs(
            arc_id=args.arc_id, expected_version=args.expected_version,
            **_present(
                name=args.name, summary=args.summary, genre_tags=args.genre_tags,
                chapter_span=args.chapter_span, threads=args.threads, layout=args.layout,
                pacing=args.pacing, arc_roster=args.arc_roster, visibility=args.visibility,
                status=args.status,
            ),
        ))
    if args.op == "archive":
        if not args.arc_id:
            raise ValueError("op=archive requires arc_id — NOT a name. Call composition_arc_template_list to get the id, then call this again")
        return await composition_arc_template_archive(ctx, arc_id=args.arc_id)
    # op == "restore"
    if not args.arc_id:
        raise ValueError("op=restore requires arc_id — NOT a name. Call composition_arc_template_list to get the id, then call this again")
    return await composition_arc_template_restore(ctx, arc_id=args.arc_id)


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
        visibility="legacy", superseded_by="composition_outline_node_edit",  # S3
        tool_name="composition_outline_node_move",
    ),
)
async def composition_outline_node_move(ctx: MCPContext, args: _OutlineNodeMoveArgs) -> dict:
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    pid = _uuid(args.project_id, "project_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    outline = OutlineRepo(get_pool())
    node_id = _uuid(args.node_id, "node_id")
    # Project-scope the target BEFORE mutating (the gate above checked the resolved
    # Work's book, but reorder_node targets by id only) — a node_id from another
    # Work would otherwise be moved under THIS book's gate. See node_update note.
    prior = await outline.get_node(node_id)
    if prior is None or prior.project_id != pid:
        raise uniform_not_accessible()
    try:
        moved = await outline.reorder_node(
            node_id,
            new_parent_id=_uuid(args.new_parent_id, "new_parent_id") if args.new_parent_id else None,
            after_id=_uuid(args.after_id, "after_id") if args.after_id else None,
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


# NOTE (T1c(3) simplification): we DELIBERATELY do NOT call `enable_task_results`
# here. That wraps a gate tool's result into a wire `CreateTaskResult`
# (resultType:"task"), which is protocol-pure but forces polymorphic result handling
# at EVERY hop (chat-service `call_tool`, the ai-gateway federation client). Instead
# the gate tool returns the task HANDLE as normal content (`open_gate`'s dict) — so
# the gateway forwards it as an ordinary `CallToolResult` (no change) and chat-service
# detects the handle in content (`task_detect.task_envelope_from_content`). The input
# step is the `task_provide_input` TOOL, which the gateway already forwards and which
# returns the completed result synchronously — so no `tasks/get` polling is needed for
# the confirm gate. `enable_task_results` stays available for a future protocol-pure /
# external-MCP-tasks-client path.


# ══════════════════════════════════════════════════════════════════════════════
# S3 catalog-unification (2026-07-25): 5 clean single-tier CRUD families → 5 unified
# op-tools. Each SUPERSEDES its per-op write tools (all marked visibility=legacy above,
# still callable, hidden from tool_list default). Same tier per family; delegates to the
# SAME handlers (no logic moved); per-op required-field guards raise ValueError→isError;
# _present() drops omitted None so each sub-Args applies its own defaults. Mirrors S3·arc.
# ══════════════════════════════════════════════════════════════════════════════


class _StructTemplateEditArgs(ForbidExtra):
    # `list` added with D-PLANFORGE-BEATS-UNWIRED. The family had five WRITE ops and no read, so the
    # agent could author a structure but never DISCOVER one — and `plan_compile`'s new
    # `structure_template_id` would have been un-callable without guessing a UUID. An affordance
    # the agent cannot reach is the same silent no-op as a tool that does nothing.
    op: Annotated[
        Literal["list", "create", "update", "clone", "archive", "restore"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: list | create | update | clone | archive | restore. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    template_id: str | None = None       # update, clone, archive, restore
    expected_version: int | None = None  # update
    name: str | None = None              # create (req), update, clone
    kind: str | None = None              # create, update
    beats: list[dict[str, Any]] | None = None  # create, update


@mcp_server.tool(
    name="composition_structure_template_edit",
    description=(
        "List, create, edit, clone, archive, or restore structure templates (the reusable ordered "
        "story beats a plan is shaped by — Save the Cat, Hero's Journey, Story Circle, Web Novel "
        "Arc, Kishōtenketsu, Three-Act, plus your own) — the unified template entry point. "
        "op=list returns the built-ins + your own with their beats; use it to find the "
        "template_id to pass to plan_compile. op=create (needs name; optional kind/beats). "
        "op=update your own (needs template_id + expected_version; only passed fields change). "
        "op=clone copies one (needs template_id; optional new name) — clone a built-in to customise "
        "it, built-ins are never edited in place. op=archive soft-archives (needs template_id; "
        "reversible via op=restore). op=restore un-archives (needs template_id)."
    ),
    meta=require_meta("A", "user",
                      # "story structure" -> "story structure templates": this tool edits
                      # the reusable TEMPLATES, not this book's structure.
                      synonyms=["list structure templates", "story structure templates",
                                "beat sheet",
                                "edit structure template", "create structure template",
                                "clone template", "archive structure template", "manage structure template"],
                      tool_name="composition_structure_template_edit"),
)
async def composition_structure_template_edit(ctx: MCPContext, args: _StructTemplateEditArgs) -> dict:
    if args.op == "list":
        tc = _ctx(ctx)
        repo = StructureTemplatesRepo(get_pool())
        rows = await repo.list_for_user(tc.user_id)
        return {"templates": [
            {
                "template_id": str(t.id),
                "name": t.name,
                "kind": t.kind,
                # The tier, stated plainly: a built-in is READ-ONLY and must be cloned before it can
                # be customised (the System-tier write rule). Leaving the agent to infer that from a
                # null owner is how a user ends up trying to edit a shared row.
                "builtin": t.owner_user_id is None,
                "beat_count": len(t.beats or []),
                "beats": [
                    {"key": b.get("key"), "label": b.get("label"), "purpose": b.get("purpose")}
                    for b in (t.beats or []) if isinstance(b, dict)
                ],
            }
            for t in rows
        ]}
    if args.op == "create":
        if not args.name:
            raise ValueError("op=create requires name")
        return await composition_structure_template_create(ctx, _StructTemplateCreateArgs(
            name=args.name, **_present(kind=args.kind, beats=args.beats)))
    if args.op == "update":
        if not args.template_id or args.expected_version is None:
            raise ValueError("op=update requires template_id and expected_version")
        return await composition_structure_template_update(ctx, _StructTemplateUpdateArgs(
            template_id=args.template_id, expected_version=args.expected_version,
            **_present(name=args.name, kind=args.kind, beats=args.beats)))
    if args.op == "clone":
        if not args.template_id:
            raise ValueError("op=clone requires template_id")
        return await composition_structure_template_clone(ctx, _StructTemplateCloneArgs(
            template_id=args.template_id, **_present(name=args.name)))
    if args.op == "archive":
        if not args.template_id:
            raise ValueError("op=archive requires template_id")
        return await composition_structure_template_archive(
            ctx, _StructTemplateIdArgs(template_id=args.template_id))
    # op == "restore"
    if not args.template_id:
        raise ValueError("op=restore requires template_id")
    return await composition_structure_template_restore(
        ctx, _StructTemplateIdArgs(template_id=args.template_id))


class _OutlineNodeEditArgs(ForbidExtra):
    op: Annotated[
        Literal["create", "update", "delete", "restore", "move"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: create | update | delete | restore | move. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    project_id: str | None = None        # all (create: optional)
    node_id: str | None = None           # update, delete, restore, move
    expected_version: int | None = None  # update (req), move (opt)
    kind: Literal["chapter", "scene"] | None = None  # create (req)
    parent_id: str | None = None         # create
    title: str | None = None             # create, update
    goal: str | None = None              # create, update
    synopsis: str | None = None          # create, update
    status: Literal["empty", "outline", "drafting", "done"] | None = None  # create, update
    chapter_id: str | None = None        # create, update (bind a plan node to a chapter)
    # D-SCENE-CREATE-PARITY — the scene's cast + beat charge (PlanForge writes both).
    tension: int | None = None           # create, update
    present_entity_ids: list[str] | None = None  # create, update
    location_entity_id: str | None = None  # create, update
    story_time: str | None = None        # create, update
    conflict: str | None = None          # create, update
    outcome: str | None = None           # create, update
    value_shift: int | None = None       # create, update
    stakes: str | None = None            # create, update
    target_words: int | None = None      # create, update
    exit_state: SceneExitStateIn | None = None  # create, update
    new_parent_id: str | None = None     # move
    after_id: str | None = None          # move


@mcp_server.tool(
    name="composition_outline_node_edit",
    description=(
        "Create, edit, delete, restore, or move an outline node (chapter/scene) — the unified "
        "outline-CRUD entry point. op=create (needs kind ∈ chapter|scene; optional parent_id/title/"
        "goal/synopsis/status/chapter_id/scene fields). op=update (needs project_id + node_id + "
        "expected_version; only passed fields change). op=delete soft-archives (needs project_id + "
        "node_id; reversible via op=restore). op=restore un-archives. op=move reparents+reorders "
        "(needs project_id + node_id; new_parent_id/after_id, optional expected_version). EDIT required."
    ),
    meta=require_meta("A", "book",
                      synonyms=["edit outline node", "create chapter", "create scene", "delete scene",
                                "move scene", "reorder outline", "restore scene", "manage outline node"],
                      tool_name="composition_outline_node_edit"),
)
async def composition_outline_node_edit(ctx: MCPContext, args: _OutlineNodeEditArgs) -> dict:
    if args.op == "create":
        if not args.kind:
            raise ValueError("op=create requires kind")
        return await composition_outline_node_create(ctx, _NodeCreateArgs(
            kind=args.kind,
            **_present(project_id=args.project_id, parent_id=args.parent_id, title=args.title,
                       goal=args.goal, synopsis=args.synopsis, status=args.status,
                       chapter_id=args.chapter_id, location_entity_id=args.location_entity_id,
                       story_time=args.story_time, conflict=args.conflict, outcome=args.outcome,
                       value_shift=args.value_shift, stakes=args.stakes,
                       target_words=args.target_words, exit_state=args.exit_state,
                       # D-SCENE-CREATE-PARITY — cast + beat charge.
                       tension=args.tension, present_entity_ids=args.present_entity_ids)))
    if args.op == "update":
        if not args.project_id or not args.node_id or args.expected_version is None:
            raise ValueError("op=update requires project_id, node_id, and expected_version")
        return await composition_outline_node_update(ctx, _NodeUpdateArgs(
            project_id=args.project_id, node_id=args.node_id, expected_version=args.expected_version,
            **_present(title=args.title, goal=args.goal, synopsis=args.synopsis, status=args.status,
                       location_entity_id=args.location_entity_id, story_time=args.story_time,
                       conflict=args.conflict, outcome=args.outcome, value_shift=args.value_shift,
                       stakes=args.stakes, target_words=args.target_words, exit_state=args.exit_state,
                       # D-SCENE-PROSE-NOWHERE-TO-LAND — bind a plan node to a manuscript
                       # chapter. The unified tool already accepted `chapter_id` on create;
                       # forwarding it on update is what makes a plan-only node recoverable.
                       chapter_id=args.chapter_id,
                       # D-SCENE-CREATE-PARITY — cast + beat charge.
                       tension=args.tension, present_entity_ids=args.present_entity_ids)))
    if args.op == "delete":
        if not args.project_id or not args.node_id:
            raise ValueError("op=delete requires project_id and node_id")
        return await composition_outline_node_delete(ctx, project_id=args.project_id, node_id=args.node_id)
    if args.op == "restore":
        if not args.project_id or not args.node_id:
            raise ValueError("op=restore requires project_id and node_id")
        return await composition_outline_node_restore(ctx, project_id=args.project_id, node_id=args.node_id)
    # op == "move"
    if not args.project_id or not args.node_id:
        raise ValueError("op=move requires project_id and node_id")
    return await composition_outline_node_move(ctx, _OutlineNodeMoveArgs(
        project_id=args.project_id, node_id=args.node_id,
        **_present(new_parent_id=args.new_parent_id, after_id=args.after_id,
                   expected_version=args.expected_version)))


class _CanonRuleEditArgs(ForbidExtra):
    op: Annotated[
        Literal["create", "update", "delete", "restore"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: create | update | delete | restore. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    project_id: str | None = None        # all
    rule_id: str | None = None           # update, delete, restore
    expected_version: int | None = None  # update
    text: str | None = None              # create (req), update
    scope: Literal["world", "entity", "reveal_gate"] | None = None  # create
    entity_id: str | None = None         # create
    from_order: int | None = None        # create
    until_order: int | None = None       # create
    kind: str | None = None              # create
    active: bool | None = None           # update


@mcp_server.tool(
    name="composition_canon_rule_edit",
    description=(
        "Create, edit, delete, or restore a canon rule (a constraint the generator must honor) — "
        "the unified canon-rule-CRUD entry point. op=create (needs project_id + text; optional scope ∈ "
        "world|entity|reveal_gate, entity_id, from_order/until_order, kind). op=update (needs project_id + "
        "rule_id + expected_version; text/active). op=delete soft-deletes (needs project_id + rule_id; "
        "reversible via op=restore). op=restore un-deletes. EDIT required."
    ),
    meta=require_meta("A", "book",
                      synonyms=["edit canon rule", "add canon rule", "delete canon rule",
                                "restore canon rule", "set constraint", "manage canon rule"],
                      tool_name="composition_canon_rule_edit"),
)
async def composition_canon_rule_edit(ctx: MCPContext, args: _CanonRuleEditArgs) -> dict:
    if args.op == "create":
        if not args.project_id or not args.text:
            raise ValueError("op=create requires project_id and text")
        return await composition_canon_rule_create(ctx, _CanonRuleCreateArgs(
            project_id=args.project_id, text=args.text,
            **_present(scope=args.scope, entity_id=args.entity_id, from_order=args.from_order,
                       until_order=args.until_order, kind=args.kind)))
    if args.op == "update":
        if not args.project_id or not args.rule_id or args.expected_version is None:
            raise ValueError("op=update requires project_id, rule_id, and expected_version")
        return await composition_canon_rule_update(ctx, _CanonRuleUpdateArgs(
            project_id=args.project_id, rule_id=args.rule_id, expected_version=args.expected_version,
            **_present(text=args.text, active=args.active)))
    if args.op == "delete":
        if not args.project_id or not args.rule_id:
            raise ValueError("op=delete requires project_id and rule_id")
        return await composition_canon_rule_delete(ctx, project_id=args.project_id, rule_id=args.rule_id)
    # op == "restore"
    if not args.project_id or not args.rule_id:
        raise ValueError("op=restore requires project_id and rule_id")
    return await composition_canon_rule_restore(ctx, project_id=args.project_id, rule_id=args.rule_id)


class _ErrorBlockEditArgs(ForbidExtra):
    op: Annotated[
        Literal["list", "resolve", "dismiss", "reopen"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: list | resolve | dismiss | reopen. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    project_id: str | None = None    # all
    chapter_id: str | None = None    # list
    block_id: str | None = None      # resolve, dismiss
    status: Literal["open", "proposed", "resolved", "dismissed", "orphaned"] | None = None  # list
    resolution: str | None = None    # resolve, dismiss
    proposal_id: str | None = None   # resolve
    limit: int | None = None         # list


@mcp_server.tool(
    name="composition_error_block_edit",
    description=(
        "Read and close the AUTHOR'S MARKED ERROR BLOCKS — passages of a chapter the author "
        "flagged as wrong, each with a note saying what is wrong with it. "
        "op=list (needs chapter_id; project_id is optional inside a book/editor session — omit it and it resolves from the open book; optional status ∈ open|proposed|resolved|"
        "dismissed|orphaned, default = everything still open) returns each block's quoted text, "
        "its note, and where it sits. READ THE BLOCKS BEFORE REWRITING ANYTHING — they are the "
        "author telling you exactly what to fix. To fix one, propose the replacement for its "
        "quoted span with propose_edit; then op=resolve (needs block_id; optional "
        "resolution, proposal_id) once the author applies it, or op=dismiss if it should not be "
        "changed after all. op=reopen re-opens a block you closed by mistake — it is the reverse "
        "of resolve/dismiss. A block with status=orphaned means the prose it pointed at has since "
        "changed — ask the author rather than guessing. EDIT required to close a block."
    ),
    meta=require_meta("A", "book",
                      synonyms=["list error blocks", "author marked problems", "marked passages",
                  "flagged as problems", "passages i flagged", "what have i flagged",
                                "what did the author flag", "resolve error block",
                                "dismiss error block", "reopen error block",
                                "reported prose errors"],
                      # LIVE-RUN FIX. The editor surface hands the model book_id + chapter_id and
                      # nothing else, so a REQUIRED project_id was an argument it had no way to
                      # populate — and Gemma-4 26B duly passed the chapter_id AS the project_id.
                      # The ambient binding (X-Project-Id, which chat-service derives
                      # book -> Work -> project and forwards) is precisely the primitive for this;
                      # the tool only had to opt in. Same affordance-gap class as E3.
                      ambient_project=True,
                      tool_name="composition_error_block_edit"),
)
async def composition_error_block_edit(ctx: MCPContext, args: _ErrorBlockEditArgs) -> dict:
    """The author's marks, for the co-writer.

    `op=list` is the affordance gate: without a read the agent could never discover a block_id to
    close, which is exactly the defect `composition_structure_template_edit` shipped with (five
    write ops, no read). It is also the point of the whole feature — the agent has to be able to
    SEE what the author flagged.

    Creating a block is deliberately NOT here. A mark is the author's statement about their own
    prose; an agent minting its own would need its own dedup and volume rules, and the sealed
    scope is human-marks → agent-fixes. The `source` column already admits it later.
    """
    tc = _ctx(ctx)
    works = WorksRepo(get_pool())
    # Ambient-resolved: omitted inside a studio turn, it comes from X-Project-Id.
    pid = _resolve_pid(tc, args.project_id)
    blocks = ErrorBlocksRepo(get_pool())

    if args.op == "list":
        if not args.chapter_id:
            raise ValueError("op=list requires chapter_id")
        pid = (await _book_or_deny(works, tc, pid, GrantLevel.VIEW)).project_id
        items, open_count = await blocks.list_for_chapter(
            pid, _uuid(args.chapter_id, "chapter_id"), status=args.status,
            limit=max(1, min(args.limit or 50, 200)),
        )
        return {
            "blocks": [
                {
                    "block_id": str(b.id), "status": b.status, "kind": b.kind,
                    "quote": b.quote, "note": b.note, "desired": b.desired,
                    "start_offset": b.start_offset, "end_offset": b.end_offset,
                }
                for b in items
            ],
            "open_count": open_count,
            "note": (
                "Fix a block by proposing a replacement for its `quote` via propose_edit, then "
                "op=resolve it." if items else
                "The author has not marked anything on this chapter."
            ),
        }

    # resolve / dismiss / reopen
    if not args.block_id:
        raise ValueError(f"op={args.op} requires block_id")
    pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
    bid = _uuid(args.block_id, "block_id")
    prior = await blocks.get(pid, bid)
    # Project-scope the target: `get` is already project-keyed, but check explicitly so a block
    # from another Work can never be closed under THIS book's gate (the node_update precedent).
    if prior is None or prior.project_id != pid:
        return {"success": False, "error": f"error block {args.block_id} not found in this project"}
    target = {"resolve": "resolved", "dismiss": "dismissed", "reopen": "open"}[args.op]
    updated = await blocks.set_status(
        pid, bid, target, proposal_id=args.proposal_id, resolution=args.resolution,
    )
    if updated is None:
        return {"success": False, "error": f"error block {args.block_id} could not be updated"}
    out = updated.model_dump(mode="json")
    # The undo hint must name a REAL REVERSE op. It previously pointed at op="list", which reads
    # and reverts nothing — the FE activity strip would have offered an Undo button that appeared
    # to work and left the block closed. Worse than offering no undo at all, and the exact
    # silent-no-op class the tool contract forbids. `reopen` exists so this hint can be honest.
    out["_meta"] = {"undo_hint": _undo(
        "composition_error_block_edit",
        op="reopen" if args.op in ("resolve", "dismiss") else "resolve",
        project_id=args.project_id, block_id=args.block_id,
    )}
    return out


class _EntityOverrideEditArgs(ForbidExtra):
    op: Annotated[
        Literal["add", "update", "delete", "restore"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: add | update | delete | restore. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    # 🔴 THE AMBIENT project_id IS THE WRONG ONE FOR THIS TOOL, and nothing said so. A book's
    # ambient project is its CANONICAL Work; an override exists only on a DERIVATIVE, which is a
    # DIFFERENT Work with its own project_id. Measured 2026-08-23, K=5 with a derivative seeded: the
    # model sent the canonical project_id every run and got NOT_A_DERIVATIVE, then called
    # composition_list_derivatives afterwards — it had the right instinct in the wrong order,
    # because nothing told it the id it already held was the wrong Work.
    project_id: str | None = Field(default=None, description=(
        "The DERIVATIVE Work's project_id — NOT the book's canonical/ambient project. An override "
        "exists only on a derivative (dị bản), which is a separate Work with its own project_id: "
        "get it from composition_list_derivatives, whose entry has is_canonical=false. Passing the "
        "ambient project is the common mistake and is refused with NOT_A_DERIVATIVE."))
    # 🔴 THESE CARRIED A TITLE AND NO DESCRIPTION, and the model paid for it. Measured 2026-08-23,
    # K=5: the tool was called on 5 of 5 runs and FOUR of them failed with
    # "`args.overridden_fields`: Input should be a valid dictionary (you sent a list of 107 ...)".
    # The schema said `object` and nothing said WHAT object — so the model sent the entity's fields
    # as a list. A flat-superset tool declares everything optional, which means the per-op
    # requirement and the SHAPE both have to live in the descriptions or they live nowhere.
    target_entity_id: str | None = Field(default=None, description=(
        "op=add REQUIRES this. The glossary entity to override, by its entity_id — get it from "
        "glossary_search or glossary_get_entity. Not the override's own id, which is override_id."))
    override_id: str | None = None       # update, delete
    overridden_fields: dict[str, Any] | None = Field(default=None, description=(
        "op=add and op=update REQUIRE this. A MAPPING of field name to its new value for this Work "
        'only — e.g. {"occupation": "cartographer"}. Not a list, and not the whole entity: send only '
        "the fields you are changing."))


@mcp_server.tool(
    name="composition_entity_override_edit",
    description=(
        "Add, update, or delete a per-Work entity override (book-local field changes on a glossary "
        "entity) — the unified entity-override-CRUD entry point. op=add (needs project_id + "
        "target_entity_id; overridden_fields). op=update (needs project_id + override_id; "
        "overridden_fields). op=delete (needs project_id + override_id) SOFT-deletes — the override stops applying immediately but is recoverable. op=restore (needs project_id + override_id) brings it back; it FAILS if a newer override for that same entity now exists, which is honest rather than clobbering the newer one. EDIT required."
    ),
    meta=require_meta("A", "book",
                      # 🔴 no_context_fill=["project_id"] WAS TRIED HERE AND TAKEN BACK OUT. The
                      # ambient project IS the wrong Work for this tool — measured c-override7,
                      # NOT_A_DERIVATIVE 5/5 — but suppressing the backfill is too blunt a remedy:
                      # composition_list_derivatives requires a project_id and takes nothing else
                      # ("Pass ANY Work's project_id from the book"), so the canonical id is a
                      # perfectly good input to the very lookup this tool wants. Removing it left
                      # the model with no project id at all, and c-override8 measured what it did
                      # then — put the target_entity_id into project_id AND book_id on three
                      # different tools, all refused "not found or not accessible".
                      # The remedy is the refusal below, not starving the argument.
                      synonyms=["add entity override", "edit entity override", "delete entity override",
                                "restore entity override", "undo entity override delete",
                                "override entity field", "manage entity override"],
                      tool_name="composition_entity_override_edit"),
)
async def composition_entity_override_edit(ctx: MCPContext, args: _EntityOverrideEditArgs) -> dict:
    if args.op == "add":
        if not args.project_id or not args.target_entity_id:
            raise ValueError("op=add requires project_id and target_entity_id")
        return await composition_entity_override_add(ctx, _EntityOverrideAddArgs(
            project_id=args.project_id, target_entity_id=args.target_entity_id,
            **_present(overridden_fields=args.overridden_fields)))
    if args.op == "update":
        if not args.project_id or not args.override_id:
            raise ValueError("op=update requires project_id and override_id")
        return await composition_entity_override_update(ctx, _EntityOverrideUpdateArgs(
            project_id=args.project_id, override_id=args.override_id,
            **_present(overridden_fields=args.overridden_fields)))
    if args.op == "delete":
        if not args.project_id or not args.override_id:
            raise ValueError("op=delete requires project_id and override_id")
        return await composition_entity_override_delete(ctx, _EntityOverrideDeleteArgs(
            project_id=args.project_id, override_id=args.override_id))
    # op == "restore" — the UNDO the soft delete now promises (F3).
    if not args.project_id or not args.override_id:
        raise ValueError("op=restore requires project_id and override_id")
    return await composition_entity_override_restore(ctx, _EntityOverrideDeleteArgs(
        project_id=args.project_id, override_id=args.override_id))


class _SceneLinkEditArgs(ForbidExtra):
    op: Annotated[
        Literal["create", "delete", "restore"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: create | delete | restore. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    project_id: str | None = None       # both
    from_node_id: str | None = None     # create
    to_node_id: str | None = None       # create
    kind: LinkKind | None = None        # create
    label: str | None = None            # create
    link_id: str | None = None          # delete


@mcp_server.tool(
    name="composition_scene_link_edit",
    description=(
        "Create or delete a scene-link edge (setup_payoff / foreshadow / callback between outline "
        "nodes) — the unified scene-link entry point. op=create (needs project_id + from_node_id + "
        "to_node_id; optional kind, label). op=delete (needs project_id + link_id) SOFT-deletes — the edge stops applying immediately but is recoverable. op=restore (needs project_id + link_id) brings it back; it FAILS if that same edge has since been re-declared. EDIT required."
    ),
    meta=require_meta("A", "book",
                      synonyms=["link scenes", "connect scenes", "add scene link", "delete scene link",
                                "restore scene link", "undo scene link delete",
                                "set setup payoff", "manage scene link"],
                      tool_name="composition_scene_link_edit"),
)
async def composition_scene_link_edit(ctx: MCPContext, args: _SceneLinkEditArgs) -> dict:
    if args.op == "create":
        if not args.project_id or not args.from_node_id or not args.to_node_id:
            raise ValueError("op=create requires project_id, from_node_id, and to_node_id")
        return await composition_scene_link_create(ctx, _SceneLinkCreateArgs(
            project_id=args.project_id, from_node_id=args.from_node_id, to_node_id=args.to_node_id,
            **_present(kind=args.kind, label=args.label)))
    if args.op == "delete":
        if not args.project_id or not args.link_id:
            raise ValueError("op=delete requires project_id and link_id")
        return await composition_scene_link_delete(
            ctx, project_id=args.project_id, link_id=args.link_id)
    # op == "restore" — the UNDO the soft delete now promises (F3).
    if not args.project_id or not args.link_id:
        raise ValueError("op=restore requires project_id and link_id")
    return await composition_scene_link_restore(
        ctx, project_id=args.project_id, link_id=args.link_id)


# ── S3 catalog-unification (2026-07-25): the derivative CRUD pair. Surfaced by the deep-dive
# of the "leave separate" calls — my prefix-based survey missed it because these two ops don't
# share a name prefix (`archive_derivative` + `divergence_spec_update`), yet both are A/book,
# both keyed by the derivative's own project_id, both reject the canonical Work: they are
# soft-DELETE + UPDATE on the SAME entity (a derivative). op=update_spec uses `_passed` so the
# documented `pov_anchor=null` clear survives (the same null-clear the motif fix preserved).
# create_derivative stays separate (W/confirm-gated); switch_active_work stays separate (a
# per-user active-work PREF keyed by book_id, over any Work, not derivative-CRUD). ─────────────
class _DerivativeEditArgs(ForbidExtra):
    op: Annotated[
        Literal["archive", "restore", "update_spec"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: archive | restore | update_spec. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    project_id: str                      # all (the derivative's project_id)
    expected_version: int | None = None  # archive (required) / restore (optional OCC)
    taxonomy: Literal["pov_shift", "character_transform", "au"] | None = None  # update_spec
    pov_anchor: str | None = None        # update_spec (explicit null CLEARS it)
    canon_rule: list[str] | None = None  # update_spec


@mcp_server.tool(
    name="composition_derivative_edit",
    description=(
        "Update, archive, or restore a what-if derivative (dị bản) — the unified derivative-CRUD entry "
        "point. op=update_spec edits the divergence spec AFTER derive (taxonomy ∈ pov_shift|"
        "character_transform|au, pov_anchor, canon_rule[]; only the fields you pass change; pass "
        "pov_anchor=null to CLEAR it). op=archive soft-deletes the derivative (needs expected_version; "
        "its chapters + knowledge survive). op=restore un-archives it (sets status active; optional "
        "expected_version). All reject the canonical Work. To CREATE a derivative use "
        "composition_create_derivative; to switch which is active use composition_switch_active_work. "
        "EDIT on the book required."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=["edit derivative", "update divergence spec", "archive derivative",
                  "delete derivative", "restore derivative", "unarchive derivative",
                  "edit dị bản", "manage derivative"],
        tool_name="composition_derivative_edit",
    ),
)
async def composition_derivative_edit(ctx: MCPContext, args: _DerivativeEditArgs) -> dict:
    """Unified derivative-CRUD dispatch. archive/update_spec delegate to the SAME legacy handlers;
    op=restore is NEW behavior (there was no un-archive tool — the archive advertised a
    reversibility no path delivered), implemented here over the same WorksRepo.update the archive
    uses (status→active), EDIT-gated + derivative-only + OCC, mirroring the archive."""
    if args.op == "archive":
        if args.expected_version is None:
            raise ValueError("op=archive requires expected_version")
        return await composition_archive_derivative(ctx, _DerivativeArchiveArgs(
            project_id=args.project_id, expected_version=args.expected_version))
    if args.op == "restore":
        tc = _ctx(ctx)
        works = WorksRepo(get_pool())
        pid = _uuid(args.project_id, "project_id")
        pid = (await _book_or_deny(works, tc, pid, GrantLevel.EDIT)).project_id
        work = await works.get(pid)
        if work is None:
            raise uniform_not_accessible()
        if work.source_work_id is None:
            return {"success": False,
                    "error": "NOT_A_DERIVATIVE — restore applies only to a dị bản, not the canonical Work"}
        try:
            updated = await works.update(
                pid, {"status": "active"}, created_by=tc.user_id,
                expected_version=args.expected_version)
        except VersionMismatchError as exc:
            return {"success": False, "outcome": "applied_conflict",
                    "error": "stale expected_version — refetch and retry",
                    "current_version": exc.current.version}
        if updated is None:
            raise uniform_not_accessible()
        out = updated.model_dump(mode="json")
        out["_meta"] = {"undo_hint": _undo(
            "composition_derivative_edit", op="archive",
            project_id=args.project_id, expected_version=updated.version)}
        return out
    # op == "update_spec" — _passed preserves the documented pov_anchor=null clear
    return await composition_divergence_spec_update(ctx, _DivergenceSpecUpdateArgs(
        project_id=args.project_id,
        **_passed(args, "taxonomy", "pov_anchor", "canon_rule")))


# ── glossary-build pipeline (spec 2026-07-27) ─────────────────────────────────
#
# The DELEGATION surface. The Mị Đế dogfood proved a weak model cannot reliably
# CHOOSE tools for world building (it kept picking the entity-EDIT tool to
# CREATE); the fix is not a better prompt, it is removing the choice: one tool,
# a closed-set `op`, and the FSM makes every downstream call itself.
# Frontend-Tool-Contract discipline: `op` is a Literal (closed set) — a typo'd
# op is a clean 422 at the schema, never a silent no-op.


async def _resolve_build_lang(tc: Any, book_id: UUID, supplied: str | None) -> str:
    """The glossary is written in the BOOK's language, not in a language this file picked.

    `glossary_build/prompts.py` already states the intent — "language adapts to the book's source
    language via `lang` (the POC ran 'vi')" — but the MCP boundary carried the POC's value as its
    default and the handler passed it through unresolved. Since `lang` also had no description, no
    model ever set it, so every build wrote Vietnamese whatever the book was.

    An explicitly supplied `lang` still wins. "vi" remains only as the LAST-RESORT fallback when
    the book cannot be read: that keeps the error path's behaviour exactly as it is today rather
    than swapping in a different guess, and the warning records when it happened.
    """
    if supplied:
        return supplied
    try:
        bearer = mint_service_bearer(tc.user_id, settings.jwt_secret)
        book_obj = await get_book_client().get_book(book_id, bearer)
        lang = (book_obj or {}).get("original_language")
        if lang:
            return str(lang)
        logger.warning("glossary_build: book %s carries no original_language", book_id)
    except Exception:
        logger.warning("glossary_build: book language unreadable for %s", book_id, exc_info=True)
    return "vi"


class _GlossaryBuildArgs(ForbidExtra):
    op: Annotated[
        Literal["start", "approve_plan", "status", "project_kg", "approve_edges", "cancel"],
        Field(description=(
            "WHICH OPERATION to perform — the dispatch discriminator: start | approve_plan | status | project_kg | approve_edges | cancel. "
            "Every other argument is optional in the schema because this is a flat superset: "
            "each op reads only ITS OWN fields, and this tool's description says which those are. "
            "Picking the wrong op is the whole failure mode — it is not a hint, it selects the code path."
        )),
    ]
    # book_id OPTIONAL (ambient_book) — omitted inside a studio, resolves from X-Book-Id.
    book_id: str | None = None
    run_id: Annotated[str | None, Field(description=(
        "The run this call belongs to, from op=start's result. Required by every op EXCEPT "
        "`start`. Never invent one: if you have no run_id, the op you want is `start`."
    ))] = None
    # 🔴 THESE THREE CARRIED NO DESCRIPTION AT ALL, and op=start REQUIRES two of them.
    # Measured 2026-08-25: once the tool finally started being selected (6 of 15 runs), every
    # single call failed with "model_ref is required for op=start" — the model chose the right
    # tool, chose the right op, invented no run_id, and could not complete, because the argument
    # it was missing described neither what it is nor where to get one. IN-4: a constraint lives
    # in the schema, not only in the tool's prose.
    source_text: Annotated[str | None, Field(description=(
        "The story, notes or premise to build FROM — paste the user's prose here. Required for "
        "op=start. This tool reads what you hand it; it does not read the book's chapters."
    ))] = None
    model_ref: Annotated[str | None, Field(description=(
        "REQUIRED for op=start: the UUID of a model to build with. Get one from "
        "`settings_list_models` and pass its `user_model_id` — that field IS this value. Never "
        "pass a name or the string 'default'; it must be UUID-shaped."
    ))] = None
    model_source: Annotated[str, Field(description=(
        "Where model_ref comes from. Leave as 'user_model' — that is what settings_list_models "
        "returns."
    ))] = "user_model"
    # OMIT to write in the BOOK's own language. The default was "vi" — the POC's language,
    # hardcoded at this boundary — so every build wrote Vietnamese into every book (measured
    # 2026-08-25 against an original_language='en' fixture). It must be None, not another
    # string: with a string default there is no way to tell "the caller asked for Vietnamese"
    # from "the caller said nothing".
    lang: Annotated[str | None, Field(description=(
        "OPTIONAL language code for the glossary content (e.g. 'en', 'vi'). Omit it and the "
        "book's own source language is used — pass one only to override that deliberately."
    ))] = None
    max_items: int = 30
    # op=approve_plan / approve_edges — the HUMAN-trimmed list. Omitted ⇒ take
    # the stored one as-is (the agent must NOT invent entries here; the planner
    # produced them and the human reviews them).
    worklist: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None


@mcp_server.tool(
    name="composition_build_cast_and_graph",
    description=(
        # RENAMED + REWRITTEN 2026-08-25. Measured: surfaced 5/5, called 0/5 — not hidden and
        # not broken (a direct probe drives it end to end), just INDISTINCT. The old name led
        # with `glossary`, a different noun from the "knowledge graph" the caller asks for, and
        # the old description opened with a category tag before reaching their words. Both now
        # lead with the caller's phrasing and with the one thing no sibling can claim: this is
        # the WHOLE chain in a single call.
        "Build the KNOWLEDGE GRAPH and the CAST for a book from a story you have been given — "
        "in ONE call. USE THIS WHEN the user gives you their story, notes or premise and wants "
        "the CAST or the GRAPH built — 'build the knowledge graph', 'extract the cast from "
        "my story', 'set up my world'. That includes when they paste the prose inline: this tool "
        "takes it as source_text. You do NOT pick per-entity tools: this ONE tool runs the whole "
        "pipeline — it plans WHAT to build (a worklist), builds each entity in its own focused "
        "step (rich attributes; major entities get a deep multi-section profile), files them as "
        "review drafts, then projects them into the graph and proposes their relationships. "
        "Ops: 'start' (needs source_text + model_ref — returns the proposed worklist for the "
        "user to approve), 'approve_plan' (the user approved — begins building; pass a trimmed "
        "worklist if they cut items), 'status' (poll progress: per-item built/skipped), "
        "'project_kg' (after the user reviews the drafts), 'approve_edges' (the user approved "
        "the relationships — writes them), 'cancel'. Always show the user the worklist before "
        "approving it, and report per-item results honestly (some items may be skipped)."
    ),
    meta=require_meta(
        "A", "book",
        synonyms=[
            # 2026-08-25 — "build the knowledge graph" REMOVED: kg_build declared the
            # identical string, which is a tie answerability cannot break. This tool's
            # input is prose the caller hands over, so its phrasing says so.
            "build my world", "set up the glossary", "create the cast",
            "build the knowledge graph from this story", "world building",
            "glossary build", "build the cast and the graph",
            "add all the characters", "extract the cast from my story",
        ],
        ambient_book=True,
        # _meta Completeness Law (Track D CD1): `approve_plan` starts a BACKGROUND
        # build — the call returning is not the work finishing, so a step-runner must
        # poll op=status rather than assume completion. And every build phase spends
        # real money on LLM calls, so the money gate must see it.
        async_job=True,
        paid=True,
        tool_name="composition_build_cast_and_graph",
    ),
)
async def composition_build_cast_and_graph(ctx: MCPContext, args: _GlossaryBuildArgs) -> dict:
    tc = _ctx(ctx)
    from app.deps import get_glossary_build_service
    from app.services.glossary_build.service import GlossaryBuildError

    svc = await get_glossary_build_service()
    owner = UUID(str(tc.user_id))

    def _need(field: str, value: Any) -> Any:
        if not value:
            raise ValueError(f"{field} is required for op={args.op}")
        return value

    try:
        if args.op == "start":
            bid = _resolve_bid(tc, args.book_id)
            await _gate(tc, bid, GrantLevel.EDIT)
            run = await svc.create_run(owner=owner, book_id=bid, params={
                "model_source": args.model_source,
                "model_ref": _need("model_ref", args.model_ref),
                "source_text": _need("source_text", args.source_text),
                "lang": await _resolve_build_lang(tc, bid, args.lang),
                "max_items": args.max_items,
            })
            planned = await svc.plan(run["run_id"], owner)
            return {
                "run_id": str(planned["run_id"]), "status": planned["status"],
                "worklist": planned.get("worklist") or [],
                "next": "Show the user this worklist; call op=approve_plan when they agree.",
            }

        run_id = UUID(str(_need("run_id", args.run_id)))
        current = await svc.get(run_id, owner)
        await _gate(tc, current["book_id"],
                   GrantLevel.VIEW if args.op == "status" else GrantLevel.EDIT)

        if args.op == "status":
            return {
                "run_id": str(run_id), "status": current["status"],
                "items": [{"name": i["name"], "kind": i["kind"], "depth": i["depth"],
                           "status": i["status"], "skip_reason": i.get("skip_reason")}
                          for i in current.get("items", [])],
                "edges": current.get("edges") or [],
                "error_message": current.get("error_message"),
            }
        if args.op == "approve_plan":
            out = await svc.approve_plan(run_id, owner, worklist=args.worklist)
            return {"run_id": str(run_id), "status": out["status"],
                    "next": "Building has started — poll op=status."}
        if args.op == "cancel":
            out = await svc.cancel(run_id, owner)
            return {"run_id": str(run_id), "status": out["status"]}

        # KG ops need a user bearer for the knowledge-service JWT routes; mint the
        # short-lived service bearer for the ENVELOPE user (same pattern the draft
        # routes use from the MCP path).
        bearer = mint_service_bearer(owner, settings.jwt_secret)
        if args.op == "project_kg":
            out = await svc.project_kg(run_id, owner, bearer)
            return {"run_id": str(run_id), "status": out["status"],
                    "edges": out.get("edges") or [],
                    "next": "Show the user these relationships; call op=approve_edges to write them."}
        out = await svc.approve_edges(run_id, owner, bearer, edges=args.edges)
        return {"run_id": str(run_id), "status": out["status"],
                "edges_applied": (out.get("params") or {}).get("edges_applied"),
                "edges_failed": (out.get("params") or {}).get("edges_failed")}
    except GlossaryBuildError as exc:
        # Honest failure surface: the FSM's code+message reach the model (never a
        # silent success) so it can tell the user exactly what is blocked.
        raise ValueError(f"{exc.code}: {exc.message}") from exc


# ── ASGI factory ──────────────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``.

    ``FastMCP.streamable_http_app()`` returns a Starlette app whose own lifespan
    runs the StreamableHTTP session manager. Under FastAPI a *mounted* sub-app's
    lifespan is NOT auto-run, so ``main.py`` runs the session manager directly
    inside its own lifespan (``mcp_server.session_manager.run()``)."""
    return mcp_server.streamable_http_app()
