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
from ..models import (
    CreateCampaignPayload,
    Campaign,
    CampaignChapter,
    CampaignDetail,
    UpdateBudgetPayload,
)
from .. import repositories as repo

router = APIRouter(prefix="/v1/campaigns", tags=["campaigns"])


def _campaign_model(row: asyncpg.Record) -> Campaign:
    return Campaign(**dict(row))


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

    # ── verify-once ownership (decision A) ─────────────────────────────────
    # Single try/finally guarantees the httpx client is closed on EVERY path
    # (including the 404/403/502 error branches).
    book = BookClient(
        settings.book_service_internal_url, settings.internal_service_token,
        timeout_s=settings.dispatch_timeout_s,
    )
    try:
        try:
            owner = await book.get_owner_user_id(payload.book_id)
        except BookNotFound:
            raise HTTPException(status_code=404, detail={"code": "CAMPAIGN_BOOK_NOT_FOUND",
                                                         "message": "book not found"})
        except BookServiceError as exc:
            raise HTTPException(status_code=502, detail={"code": "CAMPAIGN_BOOK_SERVICE_ERROR",
                                                         "message": str(exc)})
        if owner != user_id:
            raise HTTPException(status_code=403, detail={"code": "CAMPAIGN_FORBIDDEN",
                                                         "message": "not your book"})

        # Enumerate the in-scope published chapters (the ingest precondition gate).
        try:
            chapters = await book.list_published_chapters(payload.book_id)
        except BookServiceError as exc:
            raise HTTPException(status_code=502, detail={"code": "CAMPAIGN_BOOK_SERVICE_ERROR",
                                                         "message": str(exc)})
    finally:
        await book.aclose()

    if payload.chapter_from is not None:
        chapters = [c for c in chapters if c.sort_order >= payload.chapter_from]
    if payload.chapter_to is not None:
        chapters = [c for c in chapters if c.sort_order <= payload.chapter_to]

    if not chapters:
        raise HTTPException(
            status_code=400,
            detail={"code": "CAMPAIGN_NO_CHAPTERS",
                    "message": "no published chapters in range — ingest first"},
        )

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
            )
            await repo.seed_campaign_chapters(
                conn, row["campaign_id"],
                [(UUID(c.chapter_id), c.sort_order) for c in chapters],
            )
    return _campaign_model(row)


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
