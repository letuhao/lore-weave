"""Public campaign API (gateway proxies /v1/campaigns → here).

create → verify book ownership ONCE (decision A), enumerate the in-scope
published chapters, seed the projection, persist the campaign in `created`.
start → flip to `running` so the saga driver picks it up (the wizard's
cost-review happens before this call — FE, S5/S6). cancel → `cancelling`
(the driver drains in-flight then finalizes).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..deps import get_current_user, get_db
from ..grant_deps import (
    GrantLevel,
    authorize_book,
    get_grant_client_dep,
    not_found as _grant_not_found,
)
from ..clients.book_client import BookClient, BookIsDiary, BookNotFound, BookServiceError
from ..clients.dispatch_clients import (
    KnowledgeDispatchClient,
    DispatchError,
    EmbeddingConflict,
)
from ..clients.model_name import resolve_model_name
from ..clients.provider_registry_client import (
    ProviderRegistryEstimateClient,
    EstimateUnavailable,
)
from ..models import (
    CreateCampaignPayload,
    Campaign,
    CampaignChapter,
    CampaignDetail,
    CampaignListItem,
    ChapterPage,
    CampaignProgress,
    CampaignReport,
    ErrorGroup,
    StageCounts,
    ActivityEntry,
    ActivityPage,
    UpdateCampaignPayload,
    MODEL_PATCH_FIELDS,
    RerunFailedPayload,
    EstimateRequest,
    EstimateResponse,
)
from .. import estimate as est
from ..cause import normalize_error_cause
from .. import repositories as repo

router = APIRouter(prefix="/v1/campaigns", tags=["campaigns"])


def _campaign_model(row: asyncpg.Record) -> Campaign:
    return Campaign(**dict(row))


async def _grant_verified_chapters(gc, *, book_id, caller: str, need: GrantLevel,
                                   chapter_from, chapter_to):
    """E0-4b: authorize the caller's `need` grant on the book (the gate), resolve the
    book OWNER (the knowledge-graph partition + project owner — needed even for a
    collaborator's campaign), and return its in-range published chapters. Shared by
    create (manage) + estimate (view) so both apply the identical gate, range filter,
    and ingest-precondition (no published chapters in range → 400). Returns
    (chapters, book_owner). The single try/finally closes the httpx client on every
    path. Anti-oracle: no grant → 404 (authorize_book), uniform with a missing book."""
    # Gate FIRST (no-grant → 404 before any book existence is revealed).
    await authorize_book(gc, book_id, UUID(caller), need)
    book = BookClient(
        settings.book_service_internal_url, settings.internal_service_token,
        timeout_s=settings.dispatch_timeout_s,
    )
    try:
        try:
            owner = await book.get_owner_user_id(book_id)
        except BookNotFound:
            raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_BOOK_NOT_FOUND",
                                                         "message": "book not found"})
        except BookIsDiary:
            # P-1 / D-R19 — a private diary can never be batch-translated into a campaign.
            raise HTTPException(status_code=403, detail={"code": "CAMPAIGN_DIARY_NOT_ALLOWED",
                                                         "message": "a diary cannot be made into a campaign"})
        except BookServiceError as exc:
            raise HTTPException(status_code=502, detail={"code": "CAMPAIGN_BOOK_SERVICE_ERROR",
                                                         "message": str(exc)})
        try:
            chapters = await book.list_indexed_chapters(book_id)
        except BookServiceError as exc:
            raise HTTPException(status_code=502, detail={"code": "CAMPAIGN_BOOK_SERVICE_ERROR",
                                                         "message": str(exc)})
    finally:
        await book.aclose()

    if chapter_from is not None:
        chapters = [c for c in chapters if c.sort_order >= chapter_from]
    if chapter_to is not None:
        chapters = [c for c in chapters if c.sort_order <= chapter_to]

    if not chapters:
        raise HTTPException(
            status_code=400,
            detail={"code": "CAMPAIGN_NO_CHAPTERS",
                    "message": "no published chapters in range — ingest first"},
        )
    return chapters, owner


async def _grant_campaign(db, gc, campaign_id: UUID, caller: str, need: GrantLevel):
    """E0-4b campaign-id-keyed gate: fetch the campaign by id (no owner predicate),
    bootstrap its book, authorize the caller's `need` grant on that book, and return
    the row. A missing campaign OR a non-grantee → uniform 404 (anti-oracle); a
    grantee under tier → 403. The single chokepoint for every campaign-id route —
    the shared per-book read/write view (D-E0-4-F)."""
    row = await repo.get_campaign(db, campaign_id)
    if row is None:
        raise _grant_not_found()
    await authorize_book(gc, row["book_id"], UUID(caller), need)
    return row


@router.post("", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CreateCampaignPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    uid = UUID(user_id)

    # Knowledge stage needs a target project (decision I — ingest precondition;
    # the project the extraction writes into must exist before launch).
    if payload.knowledge_project_id is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "CAMPAIGN_NO_KNOWLEDGE_PROJECT",
                    "message": "knowledge_project_id is required"},
        )

    # ── E0-4b: gate `manage` on the book + resolve the book OWNER (knowledge-graph
    # partition / project owner) + enumerate in-scope chapters. A manage-collaborator's
    # campaign has owner_user_id = caller (billed), but the project/graph belong to the
    # book owner. (decision A becomes "verify-once grant".)
    chapters, book_owner = await _grant_verified_chapters(
        gc, book_id=payload.book_id, caller=user_id, need=GrantLevel.MANAGE,
        chapter_from=payload.chapter_from, chapter_to=payload.chapter_to,
    )
    is_collab = book_owner != user_id

    # E0-4b caller-pays: a collaborator's knowledge stage bills THEIR key, which
    # requires their own ref for the project's embedding model (the knowledge
    # dispatch 422s without billing_embedding_model). Block at create with a clear
    # error rather than letting every knowledge dispatch fail silently.
    if is_collab and payload.embedding_model_ref is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "CAMPAIGN_NO_BILLING_EMBEDDING",
                    "message": ("embedding_model_ref (your own ref for the project's "
                                "embedding model) is required to run a campaign on a shared book")},
        )

    # D-CAMPAIGN-KPROJECT-OWNERSHIP: the project is owned by the BOOK OWNER (E0-3
    # projects are book-owner-only), so verify ownership against the book owner — NOT
    # the caller, who won't own it. A transient knowledge-service error must NOT block
    # create (the dispatch path re-verifies); only a definitive 404 hard-rejects.
    _kc = KnowledgeDispatchClient(
        settings.knowledge_service_internal_url, settings.internal_service_token,
        timeout_s=settings.dispatch_timeout_s,
    )
    try:
        owned = await _kc.verify_project_owner(
            user_id=book_owner, project_id=str(payload.knowledge_project_id))
    except DispatchError:
        owned = True  # transient — don't block create on a knowledge blip
    finally:
        await _kc.aclose()
    if not owned:
        raise HTTPException(
            status_code=400,
            detail={"code": "CAMPAIGN_PROJECT_NOT_FOUND",
                    "message": "knowledge_project_id not found or not owned by the book owner"},
        )

    # ── S5b: apply the campaign's embedding/reranker picks to its project ───
    # (the project is SSOT for these). Done BEFORE the INSERT so a graph-conflict
    # rejects the whole create. A post-patch INSERT failure leaves the project with
    # the user's chosen model (benign — D-S5B-EMBED-CREATE-ATOMICITY).
    # E0-4b: ONLY the book owner may mutate the project's models — a collaborator's
    # embedding_model_ref is THEIR billing ref (persisted on the campaign), not a
    # project change (a same-model ref-string mismatch would trigger a destructive
    # graph swap on the owner's project). Skip set_campaign_models for a collaborator.
    if not is_collab and (payload.embedding_model_ref is not None or payload.rerank_model_ref is not None):
        kc = KnowledgeDispatchClient(
            settings.knowledge_service_internal_url, settings.internal_service_token,
            timeout_s=settings.dispatch_timeout_s,
        )
        try:
            await kc.set_campaign_models(
                project_id=str(payload.knowledge_project_id), user_id=user_id,
                embedding_model_source=payload.embedding_model_source,
                embedding_model_ref=(str(payload.embedding_model_ref)
                                     if payload.embedding_model_ref else None),
                rerank_model_source=payload.rerank_model_source,
                rerank_model_ref=(str(payload.rerank_model_ref)
                                  if payload.rerank_model_ref else None),
                confirm_embedding_change=payload.confirm_embedding_change,
            )
        except EmbeddingConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "CAMPAIGN_EMBEDDING_CONFLICT",
                        "message": ("changing the project's embedding model deletes its existing "
                                    "knowledge graph; resubmit with confirm_embedding_change=true "
                                    "or pick an empty project"),
                        "detail": str(exc)},
            )
        except DispatchError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "CAMPAIGN_KNOWLEDGE_SERVICE_ERROR", "message": str(exc)},
            )
        finally:
            await kc.aclose()

    # P4 (D-JOBS-P4-CAMPAIGN-MODEL-NAMES) — resolve the per-stage model NAMES OUT-OF-TX
    # (network I/O; H1) so the create event carries the human names for the Jobs GUI.
    # Best-effort: None on failure; the projection's COALESCE keeps them across later events.
    # Run the two resolves CONCURRENTLY so a slow provider-registry adds one 5s timeout to
    # campaign-create latency, not two (review-impl MED-1). resolve_model_name returns None
    # immediately when its ref is None (no HTTP), so a single-stage campaign pays nothing.
    _knowledge_model_name, _translation_model_name = await asyncio.gather(
        resolve_model_name(
            payload.knowledge_model_source,
            str(payload.knowledge_model_ref) if payload.knowledge_model_ref else None,
        ),
        resolve_model_name(
            payload.translation_model_source,
            str(payload.translation_model_ref) if payload.translation_model_ref else None,
        ),
    )

    async with db.acquire() as conn:
        async with conn.transaction():
            row = await repo.create_campaign(
                conn,
                owner_user_id=uid,
                book_owner_user_id=UUID(book_owner),
                book_id=payload.book_id,
                name=payload.name,
                gating_mode=payload.gating_mode,
                target_language=payload.target_language,
                knowledge_project_id=payload.knowledge_project_id,
                embedding_model_ref=payload.embedding_model_ref,
                knowledge_model_source=payload.knowledge_model_source,
                knowledge_model_ref=payload.knowledge_model_ref,
                translation_model_source=payload.translation_model_source,
                translation_model_ref=payload.translation_model_ref,
                chapter_from=payload.chapter_from,
                chapter_to=payload.chapter_to,
                total_chapters=len(chapters),
                budget_usd=payload.budget_usd,
                verifier_model_source=payload.verifier_model_source,
                verifier_model_ref=payload.verifier_model_ref,
                eval_judge_model_source=payload.eval_judge_model_source,
                eval_judge_model_ref=payload.eval_judge_model_ref,
                est_usd_low=payload.est_usd_low,    # G1: persist launch estimate band
                est_usd_high=payload.est_usd_high,
                knowledge_model_name=_knowledge_model_name,
                translation_model_name=_translation_model_name,
            )
            await repo.seed_campaign_chapters(
                conn, row["campaign_id"],
                [(UUID(c.chapter_id), c.sort_order) for c in chapters],
            )
    return _campaign_model(row)


@router.post("/estimate", response_model=EstimateResponse)
async def estimate_campaign(
    payload: EstimateRequest,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
):
    """S5a — pre-launch cost/time estimate for the wizard's review screen.

    E0-4b: grant-gated `view` on the book (a read/preview — any grantee may size a
    campaign). Sizes the in-range published chapters from their real byte_size,
    derives per-stage token counts (app.estimate), prices them via the
    provider-registry oracle, and returns a rough USD band + per-stage breakdown +
    minutes. No campaign is created."""
    chapters, _book_owner = await _grant_verified_chapters(
        gc, book_id=payload.book_id, caller=user_id, need=GrantLevel.VIEW,
        chapter_from=payload.chapter_from, chapter_to=payload.chapter_to,
    )

    source_tokens = est.source_tokens_for([c.byte_size for c in chapters], settings)

    # Normalise the role→pick map: a pick with no model_ref is "unset" (None);
    # a ref without a source defaults to the BYOK user_model space.
    models: dict[str, est.ModelPick] = {}
    for role, ref in payload.models.items():
        if ref.model_ref is None:
            models[role] = None
        else:
            models[role] = (ref.model_source or "user_model", str(ref.model_ref))

    items, metas = est.build_pricing_items(
        source_tokens=source_tokens, chapter_count=len(chapters),
        models=models, cfg=settings,
    )

    priced: list[dict] = []
    if items:
        client = ProviderRegistryEstimateClient(
            settings.provider_registry_internal_url, settings.internal_service_token,
            timeout_s=settings.dispatch_timeout_s,
        )
        try:
            priced = await client.estimate(owner_user_id=user_id, items=items)
        except EstimateUnavailable as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "CAMPAIGN_ESTIMATE_UNAVAILABLE", "message": str(exc)},
            )
        finally:
            await client.aclose()

    result = est.assemble_estimate(
        priced=priced, metas=metas, chapter_count=len(chapters), cfg=settings,
    )
    return EstimateResponse(**result)


@router.patch("/{campaign_id}", response_model=Campaign)
async def update_campaign(
    campaign_id: UUID,
    payload: UpdateCampaignPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """PATCH a campaign (E0-4b: `manage`-gated, partial). `budget_usd` raises/lowers the cap in
    any non-terminal status (does NOT auto-resume — /start once budget > spent). The
    four LLM models (translation/knowledge/verifier/eval-judge) can be re-picked only
    while created/paused (D-FACTORY-SWITCH-MODEL-RESUME — switch to a local model, then
    resume); a model change on a running/terminal campaign is 409. Only fields present
    in the body are applied."""
    provided = payload.model_fields_set
    if not provided:
        raise HTTPException(
            status_code=400,
            detail={"code": "CAMPAIGN_PATCH_EMPTY", "message": "no fields to update"},
        )
    # A model switch is gated to created/paused — load the campaign (grant-gated
    # `manage`, anti-oracle 404) to check status. Only provided fields update.
    row = await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.MANAGE)
    if provided & MODEL_PATCH_FIELDS and row["status"] not in ("created", "paused"):
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_MODELS_LOCKED",
                    "message": f"models can only be changed while created/paused (status is {row['status']}); pause first"},
        )
    fields = payload.model_dump(include=provided)
    updated = await repo.update_campaign_fields(db, campaign_id, fields)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CAMPAIGN_NOT_FOUND", "message": "campaign not found"},
        )
    return _campaign_model(updated)


@router.get("", response_model=list[CampaignListItem])
async def list_campaigns(
    book_id: UUID | None = None,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """E0-4b: `?book_id=` → the shared per-book view (grant-gated `view`, every
    campaign on that book regardless of creator — D-E0-4-F). No `book_id` → the
    caller's own cross-book "my campaigns" dashboard. (A full cross-book shared
    dashboard needs a book-service reverse-grant endpoint → D-E0-4B-LIST-CROSSBOOK-SHARED.)"""
    if book_id is not None:
        await authorize_book(gc, book_id, UUID(user_id), GrantLevel.VIEW)
        rows = await repo.list_campaigns(db, book_id=book_id)
    else:
        rows = await repo.list_campaigns(db, owner_user_id=UUID(user_id))
    return [CampaignListItem(**dict(r)) for r in rows]


@router.get("/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    row = await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.VIEW)
    # D-S6-CHAPTER-PAGING: chapters are no longer embedded here (a 4000-chapter
    # campaign would ship every row each poll) — the monitor fetches them paginated
    # via GET /{id}/chapters. The detail stays lightweight metadata.
    return CampaignDetail(**dict(row))


@router.get("/{campaign_id}/chapters", response_model=ChapterPage)
async def get_campaign_chapters_endpoint(
    campaign_id: UUID,
    status: str = "attention",
    limit: int = 200,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """D-S6-CHAPTER-PAGING — one server-side page of the per-chapter projection +
    total. `status=attention` (default) = rows that aren't fully settled (failed /
    in-progress); `status=inflight` = rows with a stage currently dispatched (the
    processing panel); `status=all` = everything. E0-4b: grant-gated `view` (404 if
    no grant — shared per-book view)."""
    await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.VIEW)
    status = status if status in ("attention", "inflight", "all") else "attention"
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    rows, total = await repo.get_campaign_chapters_page(
        db, campaign_id, status=status, limit=limit, offset=offset,
    )
    return ChapterPage(items=[CampaignChapter(**dict(r)) for r in rows], total=total)


@router.get("/{campaign_id}/activity", response_model=ActivityPage)
async def get_campaign_activity_endpoint(
    campaign_id: UUID,
    limit: int = 50,
    before_id: int | None = None,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """D-FACTORY-INFLIGHT-LOG — the monitor's recent-first activity log (one row per
    stage-status transition, written by the campaign_chapters trigger). Keyset-paged
    via `before_id` (pass back `next_before`). E0-4b: grant-gated `view`."""
    await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.VIEW)
    limit = max(1, min(limit, 200))
    rows = await repo.get_campaign_activity(db, campaign_id, limit=limit, before_id=before_id)
    items = [ActivityEntry(**dict(r)) for r in rows]
    # next_before only when the page is full (more rows may remain); else end-of-log.
    next_before = items[-1].id if len(items) == limit else None
    return ActivityPage(items=items, next_before=next_before)


@router.get("/{campaign_id}/progress", response_model=CampaignProgress)
async def get_campaign_progress_endpoint(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """S6 — lightweight live-progress for the monitor poll (per-stage counts, not the
    full chapters[]). E0-4b: grant-gated `view` (404 if no grant)."""
    row = await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.VIEW)
    agg = await repo.get_campaign_progress(db, campaign_id)

    def _stage(prefix: str) -> StageCounts:
        total = agg["total"]
        done = agg[f"{prefix}_done"]
        failed = agg[f"{prefix}_failed"]
        skipped = agg[f"{prefix}_skipped"]
        return StageCounts(
            total=total, done=done, failed=failed, skipped=skipped,
            in_progress=total - done - failed - skipped,
        )

    return CampaignProgress(
        campaign_id=campaign_id,
        status=row["status"],
        spent_usd=row["spent_usd"],
        budget_usd=row["budget_usd"],
        total_chapters=row["total_chapters"],
        stages={
            "knowledge": _stage("kn"),
            "translation": _stage("tr"),
            "eval": _stage("ev"),
        },
    )


@router.get("/{campaign_id}/report", response_model=CampaignReport)
async def get_campaign_report_endpoint(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """G1 — completion / wake-up report: outcome summary + spend-vs-estimate +
    failure breakdown (grouped by normalized cause). E0-4b: grant-gated `view`.
    Available for any status; most useful once terminal (completed/failed/cancelled)."""
    await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.VIEW)
    row = await repo.get_report_row(db, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND",
                                                     "message": "campaign not found"})
    agg = await repo.get_campaign_progress(db, campaign_id)

    def _stage(prefix: str) -> StageCounts:
        total = agg["total"]
        done, failed, skipped = agg[f"{prefix}_done"], agg[f"{prefix}_failed"], agg[f"{prefix}_skipped"]
        return StageCounts(total=total, done=done, failed=failed, skipped=skipped,
                           in_progress=total - done - failed - skipped)

    # Bucket failed chapters by normalized cause (pure fn) and sum counts.
    buckets: dict[str, dict] = {}
    for er in await repo.get_failed_error_strings(db, campaign_id):
        cause, remediable = normalize_error_cause(er["last_error"])
        b = buckets.setdefault(cause, {"count": 0, "remediable": remediable})
        b["count"] += er["n"]
    error_groups = [
        ErrorGroup(cause=c, count=b["count"], remediable=b["remediable"])
        for c, b in sorted(buckets.items(), key=lambda kv: kv[1]["count"], reverse=True)
    ]

    return CampaignReport(
        campaign_id=campaign_id,
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        duration_seconds=row["duration_seconds"],
        total_chapters=row["total_chapters"],
        stages={"knowledge": _stage("kn"), "translation": _stage("tr"), "eval": _stage("ev")},
        spent_usd=row["spent_usd"],
        budget_usd=row["budget_usd"],
        est_usd_low=row["est_usd_low"],
        est_usd_high=row["est_usd_high"],
        error_groups=error_groups,
    )


@router.post("/{campaign_id}/start", response_model=Campaign)
async def start_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    row = await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.MANAGE)
    if row["status"] not in ("created", "paused"):
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_NOT_STARTABLE",
                    "message": f"cannot start a campaign in status {row['status']}"},
        )
    # S4d (D-S4D-RESUME-GUARD): refuse to resume a campaign that is still at/over
    # its budget — it would re-pause on the next usage event after dispatching a
    # few more jobs (more overspend). Raise the cap via PATCH first.
    if row["budget_usd"] is not None and row["spent_usd"] >= row["budget_usd"]:
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_OVER_BUDGET",
                    "message": "spent_usd is at/over budget_usd; raise the budget (PATCH) before resuming"},
        )
    await repo.set_campaign_status(db, campaign_id, "running", set_started=True)
    updated = await repo.get_campaign(db, campaign_id)
    return _campaign_model(updated)


@router.post("/{campaign_id}/rerun-failed", response_model=Campaign)
async def rerun_failed_campaign(
    campaign_id: UUID,
    payload: RerunFailedPayload | None = None,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """G2 — reset the campaign's failed chapters (or a chosen subset) to `pending`
    (+ zero attempts, clear last_error) and re-arm the campaign to `running` so the
    driver re-dispatches them. The downstream skip-gate prevents re-spend on
    already-completed work. A cancelled/cancelling campaign can't be re-run; the
    over-budget guard applies (re-running dispatches → spends). NOTE: re-arming a
    *paused* campaign to running also resumes its other pending work (re-run implies
    "make progress again"); cancel instead if you only wanted the failed chapters
    inspected (review-impl LOW)."""
    row = await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.MANAGE)
    if row["status"] in ("cancelled", "cancelling"):
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_NOT_RERUNNABLE",
                    "message": f"cannot re-run a {row['status']} campaign"},
        )
    if row["budget_usd"] is not None and row["spent_usd"] >= row["budget_usd"]:
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_OVER_BUDGET",
                    "message": "spent_usd is at/over budget_usd; raise the budget (PATCH) before re-running"},
        )
    ids = payload.chapter_ids if payload else None
    n = await repo.reset_failed_stages(db, campaign_id, ids)
    # Re-arm so the driver picks the reset chapters up; no-op if nothing was failed.
    if n > 0 and row["status"] != "running":
        await repo.set_campaign_status(db, campaign_id, "running", set_started=True)
    updated = await repo.get_campaign(db, campaign_id)
    return _campaign_model(updated)


@router.post("/{campaign_id}/pause", response_model=Campaign)
async def pause_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    """Pause a running campaign (S3c). Stops NEW dispatch — the driver's claim
    only leases running/cancelling campaigns, so a paused one is skipped — while
    in-flight jobs drain and their completions still advance the projection
    (the consumer includes 'paused'). Resume via POST /start (paused → running).
    E0-4b: grant-gated `edit` (less destructive than start/cancel)."""
    row = await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.EDIT)
    if row["status"] != "running":
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_NOT_PAUSABLE",
                    "message": f"only a running campaign can be paused (status={row['status']})"},
        )
    await repo.set_campaign_status(db, campaign_id, "paused")
    updated = await repo.get_campaign(db, campaign_id)
    return _campaign_model(updated)


@router.post("/{campaign_id}/cancel", response_model=Campaign)
async def cancel_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
    gc=Depends(get_grant_client_dep),
):
    row = await _grant_campaign(db, gc, campaign_id, user_id, GrantLevel.MANAGE)
    if row["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_TERMINAL",
                    "message": f"campaign already {row['status']}"},
        )
    # running → cancelling (driver drains in-flight); created/paused → cancelled now.
    new_status = "cancelling" if row["status"] in ("running", "cancelling") else "cancelled"
    await repo.set_campaign_status(
        db, campaign_id, new_status, set_finished=(new_status == "cancelled"),
    )
    updated = await repo.get_campaign(db, campaign_id)
    return _campaign_model(updated)
