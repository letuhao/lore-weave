"""Work resolve + CRUD router (composition-service, M3).

GET /books/{book_id}/work wires the M2 `resolve_work` (§6.2) into a real
endpoint — forwarding the caller's JWT to knowledge-service (actor identity;
access is the E0 book grant). GET/PATCH /works/{project_id} expose the
WorksRepo with If-Match optimistic concurrency (412 on a stale version).

Book-package re-key (spec 25 PM-9): Work rows are PER-BOOK — repo calls carry
no user id; every route gates on the caller's E0 grant on the book, and writes
stamp `created_by` = the acting caller (actor, never scope).

POST /books/{book_id}/work (M8) confirm-creates a Work: ensure a book-typed
knowledge project exists (resolve, else ProjectCreate), then get-or-create the
composition_work row (idempotent).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator

from loreweave_mcp.errors import NOT_ACCESSIBLE_MESSAGE
from app.clients.book_client import BookClient, BookClientError
from app.engine.assembly import ASSEMBLY_MODES
from app.clients.knowledge_client import KnowledgeClient, KnowledgeContractError
from app.db.models import DivergenceSpec, DivergenceTaxonomy, EntityOverride, WorkStatus
from app.db.pool import get_pool
from app.db.repositories import VersionMismatchError
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep,
    get_derivatives_repo,
    get_grant_client_dep,
    get_knowledge_client_dep,
    get_works_repo,
)
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError, build_derivative_context
from app.work_resolution import WorkResolution, resolve_work

router = APIRouter(prefix="/v1/composition")


class WorkResolutionResponse(BaseModel):
    status: str
    work: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = []
    book_project_id: UUID | None = None
    book_project_ids: list[UUID] = []


class WorkPatch(BaseModel):
    active_template_id: UUID | None = None
    status: WorkStatus | None = None
    settings: dict[str, Any] | None = None

    @field_validator("settings")
    @classmethod
    def _validate_known_setting_enums(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Settings is a free-form JSONB blob, but a few keys are closed enums the
        engine keys on — validate them at the PATCH boundary so a bad value 422s
        here rather than being stored and silently coerced at read time (B1)."""
        if v is not None and "assembly_mode" in v and v["assembly_mode"] not in ASSEMBLY_MODES:
            raise ValueError(f"assembly_mode must be one of {list(ASSEMBLY_MODES)}")
        return v


def _serialize_resolution(res: WorkResolution) -> WorkResolutionResponse:
    return WorkResolutionResponse(
        status=res.status,
        work=res.work.model_dump(mode="json") if res.work else None,
        candidates=[w.model_dump(mode="json") for w in res.works],
        book_project_id=res.book_project_id,
        book_project_ids=list(res.book_project_ids),
    )


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0-4c book-grant chokepoint → HTTP. none→404 (no oracle), under→403.
    composition_work is PER-BOOK (spec 25 PM-9); this gate is the ONLY access
    decision — the repo never filters on the caller."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        # Anti-oracle: a no-grant caller and a missing Work must be INDISTINGUISHABLE.
        # `works.get` is un-user-scoped since the re-key, so a distinct "work not found"
        # here would let any authenticated user probe project_id existence (PM-8).
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


async def _ensure_pending_work(works: WorksRepo, book_id: UUID, *, created_by: UUID):
    """C16 (WG-3) greenfield degrade: return the (at-most-one) lazy null-project
    Work for this BOOK, creating it if absent (stamped `created_by` = the acting
    caller — actor, not scope; PM-9). Idempotent + race-safe: the partial-unique
    `(book_id) WHERE pending_project_backfill` index (PM-4) caps it at one per
    book, so a concurrent loser — any collaborator — re-gets the existing row
    instead of 500-ing. The catch-and-re-get below matches that index predicate
    exactly (book_id + pending marker; see get_pending_for_book —
    postgres-partial-index-on-conflict-predicate-must-match). Used by both the
    knowledge-DOWN (resolve unavailable) and create_project-OUTAGE paths."""
    existing = await works.get_pending_for_book(book_id)
    if existing is not None:
        return existing
    try:
        return await works.create_pending(created_by, book_id)
    except asyncpg.UniqueViolationError:
        racey = await works.get_pending_for_book(book_id)
        if racey is None:
            raise HTTPException(status_code=409, detail={"code": "WORK_CREATE_CONFLICT"})
        return racey


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


@router.get("/books/{book_id}/work", response_model=WorkResolutionResponse)
async def get_work_for_book(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> WorkResolutionResponse:
    # E0-4c: read-pack tier → VIEW grant on the book.
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    res = await resolve_work(
        book_id, bearer=bearer, works_repo=works, knowledge_client=knowledge,
    )
    return _serialize_resolution(res)


class WorkCreateBody(BaseModel):
    # C16/C23: `source_work_id` marks a DERIVATIVE (dị bản) Work. A derivative MUST
    # bind a real (NOT NULL) knowledge project_id — it is its own delta partition
    # (G2) and the knowledge timeline endpoint widens to ALL of a user's projects on
    # a null project_id (cross-project grounding leak). So the WG-3 lazy/null-project
    # degradation is GREENFIELD-ONLY; a derivative whose knowledge project can't be
    # created surfaces the failure instead of degrading. (The derivative create flow
    # itself is C23; this field is the forward-compatible guard hook.)
    source_work_id: UUID | None = None


@router.post("/books/{book_id}/work", status_code=201)
async def create_work_for_book(
    book_id: UUID,
    body: WorkCreateBody | None = None,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Confirm-create a Work (idempotent). Ensures a book-typed knowledge
    project exists (resolve, else ProjectCreate), then get-or-creates the
    composition_work row. Returns the Work.

    C16 (WG-3) resilience: for a GREENFIELD work, a knowledge-service OUTAGE
    (down/timeout/5xx) during project creation no longer 502s — the Work is created
    with a lazy null `project_id` + a backfill marker so the writer can keep drafting
    + Generate (grounding degrades to the packer's empty/FTS fallback). A 4xx CONTRACT
    error still surfaces (no silent swallow). A DERIVATIVE work (`source_work_id`) is
    NEVER eligible for the null path (C23 guard)."""
    is_derivative = body is not None and body.source_work_id is not None
    # E0-4c: creating a work is an authoring (write) action → EDIT grant. Then
    # fetch the book for its title (get_book returns the row for any grantee
    # post-E0-2). composition_work is per-book (PM-9); the caller only stamps
    # `created_by` on the create paths below.
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        book_obj = await book.get_book(book_id, bearer)
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})
    if book_obj is None:
        raise HTTPException(status_code=404, detail="book not found")

    res = await resolve_work(
        book_id, bearer=bearer, works_repo=works, knowledge_client=knowledge,
    )
    if res.status == "unavailable":
        # C16 (WG-3): knowledge-service is DOWN, so resolve couldn't even list the
        # book's projects. A DERIVATIVE still 502s (it needs its own real project —
        # C23 guard). For a GREENFIELD work the writer must NOT be wall-blocked by an
        # optional dependency: degrade to a lazy null-project Work (reuse an existing
        # pending row if a prior outage already made one) so drafting + Generate keep
        # working; a later setup retry (once knowledge recovers) backfills the real
        # project. This fully decouples writing from the knowledge-service outage.
        if is_derivative:
            raise HTTPException(status_code=502, detail={"code": "KNOWLEDGE_UNAVAILABLE"})
        return (
            await _ensure_pending_work(works, book_id, created_by=user_id)
        ).model_dump(mode="json")
    # Already a Work → idempotent return (pick the first if several marked).
    if res.status == "found":
        return res.work.model_dump(mode="json")  # type: ignore[union-attr]
    if res.status == "candidates":
        return res.works[0].model_dump(mode="json")

    # Determine the knowledge project to bind to.
    if res.status == "unmarked_single":
        project_id = res.book_project_id
    elif res.status == "unmarked_candidates":
        project_id = res.book_project_ids[0]
    else:  # none → create a book-typed knowledge project
        name = book_obj.get("title") or f"Book {book_id}"
        # C16 (WG-3) error discrimination: a 4xx is a CONTRACT bug → surface it
        # (never degrade an auth/validation failure into a grounding-blind Work);
        # only an OUTAGE (None ← down/timeout/5xx) is eligible for graceful
        # degradation.
        # OQ-1 (ratified): knowledge auto-provision stays OWNER-only — the
        # caller's own bearer is forwarded and knowledge rejects a non-owner
        # (F4), which surfaces below rather than minting an owner-identity
        # token. A grantee's pending Work waits for the owner's next
        # create/resolve to backfill (MED-1-style path, surfaced not silent).
        try:
            created = await knowledge.create_project(book_id, name, bearer)
        except KnowledgeContractError:
            raise HTTPException(status_code=502, detail={"code": "PROJECT_CREATE_FAILED"})

        if created is None or not created.get("project_id"):
            # Knowledge OUTAGE. A DERIVATIVE work MUST NOT take the null path
            # (C23 guard — it needs its own real project partition); surface instead.
            if is_derivative:
                raise HTTPException(status_code=502, detail={"code": "PROJECT_CREATE_FAILED"})
            # GREENFIELD: degrade to a lazy null-project Work so the writer keeps
            # drafting + Generate while knowledge recovers (backfilled by a later
            # setup retry, below).
            return (
                await _ensure_pending_work(works, book_id, created_by=user_id)
            ).model_dump(mode="json")
        project_id = UUID(str(created["project_id"]))

        # C16 backfill seam: if a prior outage left a lazy pending Work for this
        # book (possibly created by a grantee — PM-9/F5), stamp the freshly-created
        # project onto it (clear the marker) instead of spawning a second Work —
        # knowledge has recovered.
        pending = await works.get_pending_for_book(book_id)
        if pending is not None and pending.id is not None:
            backfilled = await works.backfill_project(
                pending.id, project_id, created_by=user_id,
            )
            if backfilled is not None:
                return backfilled.model_dump(mode="json")

    # Get-or-create the composition_work row. The get-then-create is not atomic,
    # so a concurrent same-project POST can lose the PK race — catch the unique
    # violation and re-get (atomic get-or-create). (The duplicate-knowledge-project
    # race — two first-POSTs each creating a book project — was resolved cy6/LOOM-48
    # knowledge-side: create_project now dedupes via ProjectsRepo.create_or_get under
    # a per-(user,book) advisory lock, so both POSTs resolve to the SAME project_id
    # and this unique-violation catch dedupes the work row.)
    existing = await works.get(project_id)  # type: ignore[arg-type]
    if existing is not None:
        return existing.model_dump(mode="json")
    # Seed the Work's source language from the book so the drafter writes in the
    # book's language BY DEFAULT. Without this, BookProfile.source_language stays
    # 'auto' (from_settings) → build_messages adds no language directive → the model
    # defaults to English for a non-English book (the POC's Vietnamese-draft bug).
    # De-bias §2.6: source_language lives in the Work's settings profile.
    _book_lang = (book_obj.get("original_language") or "").strip()
    _init_settings = {"source_language": _book_lang} if _book_lang else None
    try:
        # `user_id` = created_by, the acting caller (plain actor stamp — PM-9).
        work = await works.create(user_id, project_id, book_id, settings=_init_settings)  # type: ignore[arg-type]
    except asyncpg.UniqueViolationError:
        racey = await works.get(project_id)  # type: ignore[arg-type]
        if racey is None:
            raise HTTPException(status_code=409, detail={"code": "WORK_CREATE_CONFLICT"})
        return racey.model_dump(mode="json")
    return work.model_dump(mode="json")


class DivergenceSpecBody(BaseModel):
    """C23 (dị bản M0): the delta declaration for the derivative. M0 override scope =
    entity fields + added canon rules — `canon_rule` here; entity-field overrides are
    `entity_overrides` below. NO relationship/event overrides (deferred)."""

    taxonomy: DivergenceTaxonomy = "au"
    pov_anchor: UUID | None = None
    canon_rule: list[str] = []


class EntityOverrideBody(BaseModel):
    target_entity_id: UUID
    overridden_fields: dict[str, Any] = {}


class DeriveBody(BaseModel):
    # BE-13a: the dị bản's human name. The wizard has ALWAYS collected this
    # (useDivergenceWizard refuses to submit without it) and then DISCARDED it —
    # buildBody() never sent it and composition_work has no name column. It lives
    # in `settings.derivative_name` so candidates[]/GET /works echo it for free
    # (both dump the Work incl. settings) and the divergence manage panel can LIST
    # named derivatives instead of unnamed UUIDs. Optional at the route (non-panel
    # callers / back-compat); the panel enforces presence.
    name: str | None = None
    branch_point: int | None = None
    divergence: DivergenceSpecBody = DivergenceSpecBody()
    entity_overrides: list[EntityOverrideBody] = []

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not 1 <= len(v) <= 200:
            raise ValueError("name must be 1..200 characters")
        return v


@router.post("/works/{project_id}/derive", status_code=201)
async def derive_work(
    project_id: UUID,
    body: DeriveBody | None = None,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """C23 (dị bản M0): create a DERIVATIVE Work that diverges from a SOURCE Work.

    COW (LOCKED): SPEC ONLY — no chapter/scene clone; the source reference spine
    stays read-only and the writer adapts manually. The derivative:
      • links to the source (`source_work_id`) at a chapter-level `branch_point` (G3);
      • gets its OWN freshly-minted knowledge project_id (G2 — its own Neo4j delta
        partition), NEVER the source's;
      • persists its `divergence_spec` + any `entity_override[]` (M0 scope = entity
        fields + added canon rules; relationship/event overrides DEFERRED) — these are
        PERSISTED here and APPLIED at retrieval in C25.

    ARCH-REVIEW GUARD (LOCKED, reconciled with C16's nullable column): a derivative
    MUST carry a NOT-NULL project_id. If knowledge-service can't mint a fresh project
    (outage/None or a 4xx contract error), we REJECT (4xx) rather than degrade to a
    null project — a null project_id widens the knowledge timeline to ALL of a user's
    projects (cross-project grounding leak). The DB CHECK is the belt; this is the
    suspenders.
    """
    body = body or DeriveBody()
    # Source Work resolution is un-user-scoped (PM-9); ACCESS is the EDIT gate on
    # the source's book just below — a no-grant caller gets the same 404 there
    # (anti-oracle preserved; nothing is returned before the gate).
    source = await works.get(project_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source work not found")
    book_id = source.book_id

    # E0-4c: deriving is an authoring (write) action on the source's book → EDIT grant
    # (LOCKED: a derivative of a shared work follows the source's per-book grant).
    # Gated BEFORE the 409 below so a no-grant probe can't tell a backed source
    # from a pending one (no existence/state oracle).
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    if source.id is None:  # a pending/lazy source has no surrogate id to link to
        raise HTTPException(status_code=409, detail={"code": "SOURCE_WORK_NOT_BACKED"})
    try:
        book_obj = await book.get_book(book_id, bearer)
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})
    if book_obj is None:
        raise HTTPException(status_code=404, detail="book not found")

    # GUARD: ALWAYS provision a FRESH knowledge project for the derivative (G2). A 4xx
    # is a contract bug → surface; an outage (None) → REJECT (never a null project on a
    # derivative). The derivative NEVER reuses the source's project_id.
    # C23-fix: force_new=True ⇒ knowledge skips its per-(user,book) dedup and mints a
    # DISTINCT is_derivative project. Without it, a source book that already had a
    # project got the SOURCE's project_id back → uq_composition_work_project 500.
    name = f"{book_obj.get('title') or 'Work'} — dị bản"
    try:
        created = await knowledge.create_project(book_id, name, bearer, force_new=True)
    except KnowledgeContractError:
        raise HTTPException(status_code=502, detail={"code": "PROJECT_CREATE_FAILED"})
    if created is None or not created.get("project_id"):
        raise HTTPException(status_code=503, detail={"code": "PROJECT_CREATE_UNAVAILABLE"})
    derivative_project_id = UUID(str(created["project_id"]))

    # Persist the derivative Work + its divergence_spec + entity_override[] in one
    # transaction (txn-local — partial state never leaks if a later insert fails). The
    # NOT-NULL project_id is enforced both here (provisioned above) and by the DB CHECK.
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # `user_id` = created_by, the acting caller (plain actor stamp — PM-9).
            # BE-13a: seed settings.derivative_name at create so it is durable from
            # the first read (candidates[]/GET /works dump settings). BE-18's merge
            # PATCH then preserves it against later partial settings writes (e.g. a
            # scene-graph drag on the derivative sends only {scene_graph}).
            _derive_settings = {"derivative_name": body.name} if body.name else None
            work = await works.create_derivative(
                user_id, derivative_project_id, book_id, source.id,
                branch_point=body.branch_point, settings=_derive_settings, conn=conn,
            )
            await derivatives.create_spec(
                DivergenceSpec(
                    created_by=user_id, project_id=derivative_project_id, work_id=work.id,
                    taxonomy=body.divergence.taxonomy, pov_anchor=body.divergence.pov_anchor,
                    canon_rule=list(body.divergence.canon_rule),
                ),
                conn=conn,
            )
            for ov in body.entity_overrides:
                await derivatives.create_override(
                    EntityOverride(
                        created_by=user_id, project_id=derivative_project_id, work_id=work.id,
                        target_entity_id=ov.target_entity_id,
                        overridden_fields=ov.overridden_fields,
                    ),
                    conn=conn,
                )
    return work.model_dump(mode="json")


@router.get("/works/{project_id}")
async def get_work(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    # E0-4c/PM-9: the row is per-book — VIEW on its book is the access decision
    # (a no-grant caller 404s at the gate; nothing returned before it).
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    return work.model_dump(mode="json")


class DerivativeContextResponse(BaseModel):
    """WS-B2: the FE read-projection of a derivative Work's DURABLE divergence
    spec. The spec/overrides are already persisted (divergence_spec +
    entity_override) and consumed server-side by `build_derivative_context`; this
    surfaces the SAME persisted state to the studio so the banner chips, POV/spec
    popover, and was→now deltas survive a reload (no longer session-cache-only).
    `is_derivative=False` (everything else empty) for a greenfield Work."""

    is_derivative: bool
    name: str | None = None  # BE-13a: settings.derivative_name (the dị bản's human label)
    source_work_id: UUID | None = None
    source_project_id: UUID | None = None
    branch_point: int | None = None
    taxonomy: DivergenceTaxonomy | None = None
    pov_anchor: UUID | None = None
    canon_rules: list[str] = []
    overrides: list[dict[str, Any]] = []


@router.get("/works/{project_id}/derivative-context")
async def get_derivative_context(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """WS-B2: read the DURABLE divergence spec + entity_override[] for the FE
    derivative studio. Reuses `build_derivative_context` (source project resolution
    + fresh override read) and `get_spec_for_work` (taxonomy/pov/canon_rule) — the
    SAME persisted substrate the packer applies — so the studio reflects real state,
    not the ephemeral derive-time react-query cache. VIEW grant on the Work's book
    (a revoked collaborator can't read a stale derivative)."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    if work.source_work_id is None:
        return DerivativeContextResponse(is_derivative=False).model_dump(mode="json")
    deriv = await build_derivative_context(
        work, works_repo=works, derivatives_repo=derivatives,
    )
    spec = await derivatives.get_spec_for_work(work.id) if work.id else None
    return DerivativeContextResponse(
        is_derivative=True,
        name=(work.settings or {}).get("derivative_name"),
        source_work_id=work.source_work_id,
        source_project_id=deriv.source_project_id,
        branch_point=deriv.branch_point,
        taxonomy=spec.taxonomy if spec else None,
        pov_anchor=spec.pov_anchor if spec else None,
        canon_rules=list(spec.canon_rule) if spec else [],
        overrides=[
            {
                "target_entity_id": str(o.target_entity_id),
                "overridden_fields": o.overridden_fields,
            }
            for o in deriv.overrides
        ],
    ).model_dump(mode="json")


# ── D-C16: id-addressable + self-healing backfill for a pending null-project ──
# Work. A GREENFIELD Work created during a knowledge-service outage has a null
# project_id, so the /works/{project_id} routes can't address it — its only
# handle is the surrogate `id`. These two routes let the FE hold work.id after
# POST /work, poll for backfill, and proceed once a real project is stamped —
# WITHOUT churning the outline/scene model to allow null project_ids.


@router.get("/works/by-id/{work_id}")
async def get_work_by_id(
    work_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """D-C16: address a Work by its surrogate `id` — the ONLY handle a freshly-
    created GREENFIELD null-project Work has (no project_id yet to key the
    /works/{project_id} routes on). Lets the FE hold work.id after POST /work and
    read its backfill status. VIEW grant on the Work's book."""
    work = await works.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    return work.model_dump(mode="json")


@router.post("/works/by-id/{work_id}/resolve-project")
async def resolve_work_project(
    work_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """D-C16: self-healing backfill — turn a pending null-project Work into a
    normal project-backed one WITHOUT a second POST /work. If knowledge has
    recovered, (idempotently) create-or-get the book's project and stamp it onto
    THIS row (clearing the marker); the FE then proceeds on the project_id routes.

    Idempotent: a Work that already carries a project_id (or was backfilled by a
    concurrent POST /work) returns as-is (200). If knowledge is STILL down, 409
    STILL_PENDING so the FE keeps polling. A 4xx contract error surfaces as 502
    (never silently swallowed). EDIT grant — backfilling binds a real grounding
    project, an authoring action."""
    work = await works.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    # Gate BEFORE the idempotent early-return: get_by_id is un-user-scoped now
    # (PM-9), so returning row content pre-gate would be an any-caller oracle
    # (worker-loaded-id-needs-parent-scoping — every by-id load keeps the book
    # gate as its parent scope).
    book_id = work.book_id
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    if work.project_id is not None or not work.pending_project_backfill:
        return work.model_dump(mode="json")

    try:
        book_obj = await book.get_book(book_id, bearer)
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})
    if book_obj is None:
        raise HTTPException(status_code=404, detail="book not found")

    name = book_obj.get("title") or f"Book {book_id}"
    # Idempotent on the knowledge side (create_or_get dedupes per (user, book)),
    # so a repeat resolve resolves to the SAME project.
    try:
        created = await knowledge.create_project(book_id, name, bearer)
    except KnowledgeContractError:
        raise HTTPException(status_code=502, detail={"code": "PROJECT_CREATE_FAILED"})
    if created is None or not created.get("project_id"):
        # Knowledge still unavailable — stay pending; the FE keeps polling.
        raise HTTPException(status_code=409, detail={"code": "STILL_PENDING"})

    project_id = UUID(str(created["project_id"]))
    try:
        backfilled = await works.backfill_project(work.id, project_id, created_by=user_id)
    except asyncpg.UniqueViolationError:
        # Defensive (review #2): the one-Work-per-book invariant makes this
        # unreachable — a pending row exists ONLY when no backed row already
        # holds the book's canonical project_id (the create seam backfills the
        # pending row rather than spawning a second). But if that invariant ever
        # drifts, a concurrent backed row already carries this project; return the
        # resolved state via the re-read below instead of a 500.
        backfilled = None
    if backfilled is not None:
        return backfilled.model_dump(mode="json")
    # Race / collision: a concurrent POST /work already backfilled (our
    # WHERE-pending UPDATE no-op'd, or a unique row already holds the project).
    # Re-read and return the now-backed row.
    current = await works.get_by_id(work_id)
    return (current or work).model_dump(mode="json")


@router.patch("/works/{project_id}")
async def patch_work(
    project_id: UUID,
    patch: WorkPatch,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    # E0-4c: patching the authoring context is a write → EDIT on the work's book.
    # Resolve the (per-book) work first to get its book_id; the gate is the
    # access decision (nothing returned before it).
    existing = await works.get(project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _gate_book(grant, existing.book_id, user_id, GrantLevel.EDIT)
    expected_version = _parse_if_match(if_match)
    patch_dict = patch.model_dump(exclude_unset=True)
    try:
        updated = await works.update(
            project_id, patch_dict, created_by=user_id, expected_version=expected_version,
        )
    except VersionMismatchError as exc:
        raise HTTPException(
            status_code=412,
            detail={"code": "WORK_VERSION_CONFLICT", "current": exc.current.model_dump(mode="json")},
        )
    if updated is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    return updated.model_dump(mode="json")
