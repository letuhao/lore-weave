"""S-TRANSL Tier-W action routes — the NET-NEW per-provider confirm spine.

The MCP fan-out plan (§3 C-CONFIRM) requires every Tier-W provider to expose a
`GET /v1/<domain>/actions/preview` + `POST /v1/<domain>/actions/confirm` pair,
token-gated, where the confirm route is the **ONLY** write path. For translation,
the priced Tier-W tools (`translation_start_job`, `translation_retranslate_dirty`)
flow:

    propose (MCP tool)  → estimate cost + mint confirm_token  → return to agent
    preview (this GET)  → re-read the bound estimate from the token (no re-price)
    confirm (this POST) → verify token → RE-AUTHORIZE the grant + chapter binding →
                          RE-PRICE the bound model (H14) → run the bound action,
                          OR refuse with a re-confirm signal if cost drifted up.

H14 (re-price-at-execution): at confirm time we re-estimate the to-do/pending scope
priced against the MODEL BOUND IN THE TOKEN (a settings flip between propose and
confirm must not silently re-price a different model) and, if the fresh cost exceeds
the confirmed estimate by > est×1.25 OR > est+$0.50, we REFUSE (409
`TRANSL_REPRICE_REQUIRED`) rather than silently overspend — the agent re-proposes
against the new number. Within tolerance, the job starts.

Re-authorization (review-impl HIGH): the token's `u`/`r` claims are bound at MINT
time, but a grant revoked inside the confirm TTL must NOT still spend. So BEFORE
spending we re-resolve the caller's grant on `claims.resource_id` (the bound book)
at EDIT through the live grant client, and reject (uniform 403) if not currently
granted. We also assert each requested chapter's `book_id == claims.resource_id`
(via book-service, the single chapter-ownership authority) so a confirm payload
cannot retarget chapters under a DIFFERENT book than the one re-authorized.

These routes are internal-token authed (service-to-service, reached by the MCP tool
handler) and gated by the stateless HMAC confirm token — identity is bound INTO the
token at mint time (the `u` claim), so the confirm cannot be replayed for a
different user. The confirm token is signed with the DEDICATED
`confirm_token_signing_secret` (NOT the `internal_service_token` envelope secret —
key split so a leak of one cannot forge the other).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from loreweave_mcp import (
    ConfirmTokenExpired,
    ConfirmTokenInvalid,
    verify_confirm_token,
)

from ..book_client import book_owns_chapter
from ..config import settings as app_settings
from ..deps import get_db
from ..grant_client import GrantLevel, get_grant_client
from ..mcp.estimate import (
    SCOPE_CHAPTERS,
    SCOPE_DIRTY,
    estimate_job_cost,
    reprice_exceeds_threshold,
)
from ..models import CreateJobPayload
from .internal_dispatch import _retry_job_core, require_internal_token
from .jobs import _resolve_and_create_job, _resume_job_core, _retranslate_dirty_core

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/translation/actions",
    tags=["translation-actions"],
    dependencies=[Depends(require_internal_token)],
)

# Descriptors the confirm spine accepts (must match the MCP tool's mint descriptor).
DESC_START_JOB = "translation.start_job"
DESC_RETRANSLATE_DIRTY = "translation.retranslate_dirty"
# job_control re-spend descriptors (resume/retry are Tier-W → confirm).
DESC_JOB_RESUME = "translation.job_resume"
DESC_JOB_RETRY = "translation.job_retry"


def _verify(token: str):
    """Verify a confirm token → claims, mapping the two distinct failures to HTTP
    so the agent's confirm_action can render `token_expired` vs `action_error`.

    Signed/verified with the DEDICATED confirm secret (key-split from the envelope
    `internal_service_token`)."""
    try:
        return verify_confirm_token(app_settings.confirm_token_signing_secret, token)
    except ConfirmTokenExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "TRANSL_CONFIRM_EXPIRED",
                    "message": "this confirmation has expired — re-propose the action"},
        ) from exc
    except ConfirmTokenInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TRANSL_CONFIRM_INVALID", "message": "invalid confirmation token"},
        ) from exc


def _payload(claims) -> dict:
    p = claims.payload
    if not isinstance(p, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TRANSL_CONFIRM_INVALID", "message": "malformed confirmation payload"},
        )
    return p


def _forbidden() -> HTTPException:
    """Uniform confirm-time refusal — a revoked grant or a chapter that doesn't
    belong to the bound book both collapse to the SAME 403 (H13 anti-oracle: the
    caller can't distinguish "grant revoked" from "that chapter isn't yours")."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "TRANSL_FORBIDDEN",
                "message": "you are not authorized to perform this action"},
    )


async def _reauthorize_book(book_id: UUID, user_id: UUID) -> None:
    """Re-resolve the caller's CURRENT grant on the token-bound book at EDIT, at
    confirm time (NOT trusting the mint-time `u`/`r` claims). A grant revoked inside
    the confirm TTL must stop the spend. Fail-CLOSED: any resolver error → no grant
    → refuse (the grant client itself returns NONE on book-service unreachable)."""
    try:
        lvl = await get_grant_client().resolve_grant(book_id, user_id)
    except Exception:  # noqa: BLE001 — fail-closed on any resolver error.
        raise _forbidden()
    if lvl == GrantLevel.NONE or not lvl.at_least(GrantLevel.EDIT):
        raise _forbidden()


async def _assert_chapters_under_book(book_id: UUID, chapter_ids: list[UUID]) -> None:
    """Assert every requested chapter belongs to the token-bound book (book-service
    is the single chapter-ownership authority). Stops a confirm payload from
    retargeting chapters under a DIFFERENT book than the one re-authorized above.
    Fail-CLOSED: `book_owns_chapter` raises on transport/5xx (don't spend on an
    unverifiable binding); a definitive 'not bound' → uniform 403."""
    for cid in chapter_ids:
        if not await book_owns_chapter(book_id, cid):
            raise _forbidden()


class PreviewResponse(BaseModel):
    descriptor: str
    title: str | None = None
    estimate: dict


@router.get("/preview", response_model=PreviewResponse)
async def preview_action(token: str = Query(...)) -> PreviewResponse:
    """Re-surface the cost estimate BOUND into a confirm token (no re-price — the
    token already carries the estimate the user is being asked to confirm). The
    agent calls this to render the confirm card before committing."""
    claims = _verify(token)
    p = _payload(claims)
    return PreviewResponse(
        descriptor=claims.descriptor,
        title=p.get("title"),
        estimate=p.get("estimate") or {},
    )


class ConfirmRequest(BaseModel):
    confirm_token: str


def _bound_model(bound_estimate: dict) -> tuple[str | None, str | None]:
    """The model the user APPROVED, echoed into the estimate at propose time and
    bound in the token. The confirm re-price MUST price this model — not whatever
    effective settings now resolve to (a settings flip between propose and confirm
    must not silently re-price a different model)."""
    return bound_estimate.get("model_source"), bound_estimate.get("model_ref")


@router.post("/confirm")
async def confirm_action(body: ConfirmRequest, db: asyncpg.Pool = Depends(get_db)) -> dict:
    """The ONLY start path for a priced translation job. Verify the token,
    RE-AUTHORIZE the caller's CURRENT grant on the bound book + assert the chapter
    binding (a grant revoked inside the TTL stops the spend; a payload cannot
    retarget another book's chapters), then RE-PRICE the bound model (H14) over the
    accurate to-do/pending scope — either run the action or refuse with a re-confirm
    signal when the cost drifted up past tolerance."""
    claims = _verify(body.confirm_token)
    p = _payload(claims)
    user_id = str(claims.user_id)
    book_id = claims.resource_id  # the token binds the book as the resource (r).

    # ── RE-AUTHORIZE at confirm (review-impl HIGH) ────────────────────────────
    # Re-check the grant on the bound book NOW — never trust the mint-time claim.
    await _reauthorize_book(book_id, claims.user_id)

    bound_estimate = (p.get("estimate") or {})
    bound_cost = bound_estimate.get("cost_usd")
    bound_model_source, bound_model_ref = _bound_model(bound_estimate)

    if claims.descriptor == DESC_START_JOB:
        chapter_ids = [UUID(c) for c in p.get("chapter_ids", [])]
        target_language = p.get("target_language")
        force_retranslate = bool(p.get("force_retranslate", False))

        # Chapter→book binding: every requested chapter must belong to the bound book.
        await _assert_chapters_under_book(book_id, chapter_ids)

        # Accurate quote: re-price ONLY the chapters execution will actually spend on.
        # Without force_retranslate, the create path's idempotency skip-gate drops any
        # chapter that already has a fresh completed translation — quoting the FULL set
        # would over-quote. force_retranslate re-does everything → full set.
        to_do = chapter_ids if force_retranslate else await _start_job_todo(
            db, chapter_ids, target_language, user_id, book_id,
        )

        # H14 — re-price the to-do scope against the MODEL BOUND in the token.
        fresh = await estimate_job_cost(
            db, owner_user_id=user_id, book_id=book_id,
            chapter_ids=to_do, scope=SCOPE_CHAPTERS,
            target_language=target_language,
            bound_model_source=bound_model_source, bound_model_ref=bound_model_ref,
        )
        if reprice_exceeds_threshold(bound_cost, fresh.cost_usd):
            return _reprice_refusal(bound_cost, fresh)

        job = await _resolve_and_create_job(
            db, book_id,
            CreateJobPayload(
                chapter_ids=chapter_ids,
                target_language=target_language,
                force_retranslate=force_retranslate,
            ),
            user_id,
        )
        return {
            "status": "action_done",
            "job_id": str(job.job_id),
            "job_status": job.status,
            "estimate": fresh.as_dict(),
        }

    if claims.descriptor == DESC_RETRANSLATE_DIRTY:
        chapter_id = UUID(p["chapter_id"])
        target_language = p["target_language"]

        # Chapter→book binding (single-chapter scope).
        await _assert_chapters_under_book(book_id, [chapter_id])

        # scope=dirty already prices ONLY the needs-set (source-dirty ∪ glossary-stale)
        # — the EXACT segments retranslate-dirty re-runs, so this quote is accurate.
        fresh = await estimate_job_cost(
            db, owner_user_id=user_id, book_id=book_id,
            chapter_ids=[chapter_id], scope=SCOPE_DIRTY,
            chapter_id=chapter_id, target_language=target_language,
            bound_model_source=bound_model_source, bound_model_ref=bound_model_ref,
        )
        if reprice_exceeds_threshold(bound_cost, fresh.cost_usd):
            return _reprice_refusal(bound_cost, fresh)

        job = await _retranslate_dirty_core(db, chapter_id, target_language, user_id)
        return {
            "status": "action_done",
            "job_id": str(job.job_id),
            "job_status": job.status,
            "estimate": fresh.as_dict(),
        }

    if claims.descriptor in (DESC_JOB_RESUME, DESC_JOB_RETRY):
        # resume/retry re-drive an EXISTING job's chapters → re-spend. H14: re-price
        # the chapters that will ACTUALLY run and refuse if it drifted up.
        #   - resume: only the job's still-'pending' chapters run (an accurate quote
        #             needs the pending subset, NOT the full set).
        #   - retry:  re-submits a FRESH job over the job's FULL stored chapter set
        #             (force_retranslate) — so the full bound scope IS what runs.
        job_id = UUID(p["job_id"])
        bound_chapter_ids = [UUID(c) for c in (p.get("chapter_ids") or [])]
        if claims.descriptor == DESC_JOB_RESUME:
            run_ids = await _resume_pending_scope(db, job_id)
        else:
            run_ids = bound_chapter_ids
        if run_ids:
            fresh = await estimate_job_cost(
                db, owner_user_id=user_id, book_id=book_id,
                chapter_ids=run_ids, scope=SCOPE_CHAPTERS,
                bound_model_source=bound_model_source, bound_model_ref=bound_model_ref,
            )
            if reprice_exceeds_threshold(bound_cost, fresh.cost_usd):
                return _reprice_refusal(bound_cost, fresh)
        # Owner-scoped cores (re-verify the owner against the row). The user binding
        # in the token (claims.user_id) is the verified owner.
        if claims.descriptor == DESC_JOB_RESUME:
            res = await _resume_job_core(db, job_id, claims.user_id)
        else:
            res = await _retry_job_core(db, job_id, claims.user_id)
        out = dict(res)
        out["job_status"] = out.pop("status", None)
        out["status"] = "action_done"
        return out

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "TRANSL_CONFIRM_UNKNOWN_DESCRIPTOR",
                "message": f"unsupported confirm descriptor {claims.descriptor!r}"},
    )


async def _start_job_todo(
    db: asyncpg.Pool, chapter_ids: list[UUID], target_language: str | None,
    user_id: str, book_id: UUID,
) -> list[UUID]:
    """The chapters a (non-force) start_job will ACTUALLY translate — the create
    path's idempotency skip-gate set. A chapter is SKIPPED iff a fresh completed,
    non-glossary-stale translation already exists for the resolved target language.
    Mirrors `_resolve_and_create_job`'s gate so the confirm quote prices the real
    to-do set, not the full (over-quoted) request."""
    if not chapter_ids:
        return []
    # Resolve the effective target language the create path will use (a confirm
    # payload may omit it → the book's setting). Reuse estimate's resolver seam.
    from ..effective_settings import resolve_effective_settings
    eff, _is_default, _u = await resolve_effective_settings(UUID(user_id), book_id, db)
    lang = target_language or eff.get("target_language") or "en"
    skip_rows = await db.fetch(
        """
        SELECT DISTINCT ct.chapter_id
        FROM chapter_translations ct
        WHERE ct.target_language = $1
          AND ct.chapter_id = ANY($2::uuid[])
          AND ct.status = 'completed'
          AND ct.is_glossary_stale = false
        """,
        lang, list(chapter_ids),
    )
    skip_set = {r["chapter_id"] for r in skip_rows}
    return [c for c in chapter_ids if c not in skip_set]


async def _resume_pending_scope(db: asyncpg.Pool, job_id: UUID) -> list[UUID]:
    """The chapters a resume will ACTUALLY re-spend on (for an accurate re-price):
    only this job's still-'pending' `chapter_translations` rows — the same set
    `_resume_job_core` re-publishes. Quoting the job's FULL chapter set would
    over-quote (completed/failed chapters are NOT re-driven on resume). retry is
    NOT routed here — it re-submits the full stored set, so its bound scope is the
    real run scope."""
    rows = await db.fetch(
        "SELECT chapter_id FROM chapter_translations WHERE job_id=$1 AND status='pending'",
        job_id,
    )
    return [r["chapter_id"] for r in rows]


def _reprice_refusal(bound_cost, fresh) -> dict:
    """H14 refusal body — NOT a 5xx: a structured re-confirm signal the agent reads
    and re-proposes from. Returned with the FRESH estimate so the new confirm card
    shows the real, higher number."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "TRANSL_REPRICE_REQUIRED",
            "message": (
                "the cost of this job has increased since it was estimated — "
                "please re-confirm against the new estimate"
            ),
            "status": "reprice_required",
            "confirmed_cost_usd": bound_cost,
            "actual_cost_usd": fresh.cost_usd,
            "estimate": fresh.as_dict(),
        },
    )
