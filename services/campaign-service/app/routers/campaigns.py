"""Public campaign API (gateway proxies /v1/campaigns → here).

create → verify book ownership ONCE (decision A), enumerate the in-scope
published chapters, seed the projection, persist the campaign in `created`.
start → flip to `running` so the saga driver picks it up (the wizard's
cost-review happens before this call — FE, S5/S6). cancel → `cancelling`
(the driver drains in-flight then finalizes).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..deps import get_current_user, get_db
from ..clients.book_client import BookClient, BookNotFound, BookServiceError
from ..clients.dispatch_clients import (
    KnowledgeDispatchClient,
    DispatchError,
    EmbeddingConflict,
)
from ..clients.provider_registry_client import (
    ProviderRegistryEstimateClient,
    EstimateUnavailable,
)
from ..models import (
    CreateCampaignPayload,
    Campaign,
    CampaignChapter,
    CampaignDetail,
    CampaignProgress,
    CampaignReport,
    ErrorGroup,
    StageCounts,
    UpdateBudgetPayload,
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


async def _owner_verified_chapters(*, book_id, user_id: str, chapter_from, chapter_to):
    """Verify the caller owns the book (decision A) and return its in-range
    published chapters. Shared by create + estimate so both apply the identical
    ownership gate, range filter, and ingest-precondition (no published chapters
    in range → 400). Raises the same HTTPExceptions on every path. The single
    try/finally guarantees the httpx client closes even on the error branches."""
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
        except BookServiceError as exc:
            raise HTTPException(status_code=502, detail={"code": "CAMPAIGN_BOOK_SERVICE_ERROR",
                                                         "message": str(exc)})
        if owner != user_id:
            raise HTTPException(status_code=403, detail={"code": "CAMPAIGN_FORBIDDEN",
                                                         "message": "not your book"})
        try:
            chapters = await book.list_published_chapters(book_id)
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
    return chapters


@router.post("", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CreateCampaignPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
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

    # D-CAMPAIGN-KPROJECT-OWNERSHIP: fail fast with a clean 400 if the user doesn't
    # own the project, instead of fail-closed mid-dispatch (404 → stage failed). A
    # transient knowledge-service error must NOT block create — the dispatch path is
    # itself owner-verified, so we only hard-reject a definitive not-found (404).
    _kc = KnowledgeDispatchClient(
        settings.knowledge_service_internal_url, settings.internal_service_token,
        timeout_s=settings.dispatch_timeout_s,
    )
    try:
        owned = await _kc.verify_project_owner(
            user_id=user_id, project_id=str(payload.knowledge_project_id))
    except DispatchError:
        owned = True  # transient — don't block create on a knowledge blip
    finally:
        await _kc.aclose()
    if not owned:
        raise HTTPException(
            status_code=400,
            detail={"code": "CAMPAIGN_PROJECT_NOT_FOUND",
                    "message": "knowledge_project_id not found or not owned by you"},
        )

    # ── verify-once ownership (decision A) + enumerate in-scope chapters ────
    chapters = await _owner_verified_chapters(
        book_id=payload.book_id, user_id=user_id,
        chapter_from=payload.chapter_from, chapter_to=payload.chapter_to,
    )

    # ── S5b: apply the campaign's embedding/reranker picks to its project ───
    # (the project is SSOT for these). Done BEFORE the INSERT so a graph-conflict
    # rejects the whole create. A post-patch INSERT failure leaves the project with
    # the user's chosen model (benign — D-S5B-EMBED-CREATE-ATOMICITY).
    if payload.embedding_model_ref is not None or payload.rerank_model_ref is not None:
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

    async with db.acquire() as conn:
        async with conn.transaction():
            row = await repo.create_campaign(
                conn,
                owner_user_id=uid,
                book_id=payload.book_id,
                name=payload.name,
                gating_mode=payload.gating_mode,
                target_language=payload.target_language,
                knowledge_project_id=payload.knowledge_project_id,
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
):
    """S5a — pre-launch cost/time estimate for the wizard's review screen.

    Owner-scoped (same book-ownership gate as create). Sizes the in-range
    published chapters from their real byte_size, derives per-stage token counts
    (app.estimate), prices them via the provider-registry oracle, and returns a
    rough USD band + per-stage breakdown + minutes. No campaign is created."""
    chapters = await _owner_verified_chapters(
        book_id=payload.book_id, user_id=user_id,
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
async def update_campaign_budget(
    campaign_id: UUID,
    payload: UpdateBudgetPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    """S4d — raise/lower the budget cap (owner-scoped). Does NOT auto-resume a
    paused campaign; resume via POST /{id}/start once budget_usd > spent_usd."""
    row = await repo.update_budget(db, campaign_id, UUID(user_id), payload.budget_usd)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CAMPAIGN_NOT_FOUND", "message": "campaign not found"},
        )
    return _campaign_model(row)


@router.get("", response_model=list[Campaign])
async def list_campaigns(
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await repo.list_campaigns(db, UUID(user_id))
    return [_campaign_model(r) for r in rows]


@router.get("/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await repo.get_campaign(db, campaign_id, UUID(user_id))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND",
                                                     "message": "campaign not found"})
    chapter_rows = await repo.get_campaign_chapters(db, campaign_id)
    detail = CampaignDetail(**dict(row))
    detail.chapters = [CampaignChapter(**dict(cr)) for cr in chapter_rows]
    return detail


@router.get("/{campaign_id}/progress", response_model=CampaignProgress)
async def get_campaign_progress_endpoint(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    """S6 — lightweight live-progress for the monitor poll (per-stage counts, not the
    full chapters[]). Owner-scoped via get_campaign (404 if not owned)."""
    row = await repo.get_campaign(db, campaign_id, UUID(user_id))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND",
                                                     "message": "campaign not found"})
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
):
    """G1 — completion / wake-up report: outcome summary + spend-vs-estimate +
    failure breakdown (grouped by normalized cause). Owner-scoped (404 if not owned).
    Available for any status; most useful once terminal (completed/failed/cancelled)."""
    row = await repo.get_report_row(db, campaign_id, UUID(user_id))
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
):
    row = await repo.get_campaign(db, campaign_id, UUID(user_id))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND",
                                                     "message": "campaign not found"})
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
    updated = await repo.get_campaign(db, campaign_id, UUID(user_id))
    return _campaign_model(updated)


@router.post("/{campaign_id}/rerun-failed", response_model=Campaign)
async def rerun_failed_campaign(
    campaign_id: UUID,
    payload: RerunFailedPayload | None = None,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    """G2 — reset the campaign's failed chapters (or a chosen subset) to `pending`
    (+ zero attempts, clear last_error) and re-arm the campaign to `running` so the
    driver re-dispatches them. The downstream skip-gate prevents re-spend on
    already-completed work. A cancelled/cancelling campaign can't be re-run; the
    over-budget guard applies (re-running dispatches → spends). NOTE: re-arming a
    *paused* campaign to running also resumes its other pending work (re-run implies
    "make progress again"); cancel instead if you only wanted the failed chapters
    inspected (review-impl LOW)."""
    row = await repo.get_campaign(db, campaign_id, UUID(user_id))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND",
                                                     "message": "campaign not found"})
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
    updated = await repo.get_campaign(db, campaign_id, UUID(user_id))
    return _campaign_model(updated)


@router.post("/{campaign_id}/pause", response_model=Campaign)
async def pause_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    """Pause a running campaign (S3c). Stops NEW dispatch — the driver's claim
    only leases running/cancelling campaigns, so a paused one is skipped — while
    in-flight jobs drain and their completions still advance the projection
    (the consumer includes 'paused'). Resume via POST /start (paused → running)."""
    row = await repo.get_campaign(db, campaign_id, UUID(user_id))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND",
                                                     "message": "campaign not found"})
    if row["status"] != "running":
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMPAIGN_NOT_PAUSABLE",
                    "message": f"only a running campaign can be paused (status={row['status']})"},
        )
    await repo.set_campaign_status(db, campaign_id, "paused")
    updated = await repo.get_campaign(db, campaign_id, UUID(user_id))
    return _campaign_model(updated)


@router.post("/{campaign_id}/cancel", response_model=Campaign)
async def cancel_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await repo.get_campaign(db, campaign_id, UUID(user_id))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND",
                                                     "message": "campaign not found"})
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
    updated = await repo.get_campaign(db, campaign_id, UUID(user_id))
    return _campaign_model(updated)
