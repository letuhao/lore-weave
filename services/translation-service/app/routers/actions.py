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
import secrets
from uuid import UUID

import asyncpg
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from loreweave_mcp import (
    ConfirmTokenExpired,
    ConfirmTokenInvalid,
    verify_confirm_token,
)

from ..book_client import book_owns_chapter
from ..config import settings as app_settings
from ..deps import get_current_user, get_db
from ..grant_client import GrantLevel, get_grant_client
from ..grant_deps import clamp_effort_to_grant
from ..mcp.estimate import (
    SCOPE_CHAPTERS,
    SCOPE_DIRTY,
    estimate_job_cost,
    reprice_exceeds_threshold,
)
from ..models import CreateJobPayload
from .extraction import CreateExtractionJobPayload, _create_extraction_job_core
from .internal_dispatch import _retry_job_core
from .jobs import _resolve_and_create_job, _resume_job_core, _retranslate_dirty_core

log = logging.getLogger(__name__)

# MCP-fanout C-CONFIRM seam fix (live-pass): the confirm spine is reached by the
# FRONTEND confirm card (ConfirmActionCard → POST /v1/<domain>/actions/confirm via
# the gateway) carrying the signed-in user's JWT — NOT a service internal token.
# These routes are therefore JWT-gated like book/glossary/composition; identity
# defence in depth is the user binding in the confirm token (the `u` claim is
# asserted == the JWT caller before any spend), so the token cannot be redeemed by
# a different signed-in user.
router = APIRouter(
    prefix="/v1/translation/actions",
    tags=["translation-actions"],
)

# Descriptors the confirm spine accepts (must match the MCP tool's mint descriptor).
DESC_START_JOB = "translation.start_job"
DESC_RETRANSLATE_DIRTY = "translation.retranslate_dirty"
# job_control re-spend descriptors (resume/retry are Tier-W → confirm).
DESC_JOB_RESUME = "translation.job_resume"
DESC_JOB_RETRY = "translation.job_retry"
# Glossary chapter-extraction (M3) — priced Tier-W, confirm before run.
DESC_START_EXTRACTION = "translation.start_extraction"


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


def _assert_caller(claims, caller_user_id: str) -> None:
    """Bind the confirm token to the proposing user (mirrors book-service's check):
    the token's `u` claim must equal the JWT-authenticated caller, so a different
    signed-in user cannot redeem it even with the token string. Folded into the
    uniform 403 (anti-oracle)."""
    if str(claims.user_id) != caller_user_id:
        raise _forbidden()


def _parse_spend_cap(raw: str | None) -> float | None:
    """Tolerant parse of X-Mcp-Spend-Cap-Usd → a float ceiling. Absent/unparseable
    ⇒ None (no per-key cap; the owner USD guardrail still applies downstream). Never
    raises — a malformed header must not 500 a confirm."""
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _resolve_confirm_caller(
    x_internal_token: str | None,
    x_user_id: str | None,
    authorization: str | None,
    x_mcp_key_id: str | None,
    x_mcp_spend_cap_usd: str | None,
) -> tuple[str, str | None, float | None]:
    """Dual-mode confirm auth → (caller_user_id, mcp_key_id, spend_cap_usd).

    - **REPLAY path (public MCP):** ``X-Internal-Token`` (constant-time compare)
      authenticates the trusted auth-service replay; ``X-User-Id`` is the approved
      owner. ONLY this path honors the ``X-Mcp-Key-Id`` / ``X-Mcp-Spend-Cap-Usd``
      attribution headers — a first-party caller must NEVER be able to tag spend to
      an arbitrary key (the SDK merge is server-set; the route is the gate).
    - **FE path:** the signed-in user's JWT (``Authorization: Bearer``). Key headers
      are IGNORED (None) — a first-party translation spends on the user, not a key.

    Cannot use ``Depends(get_current_user)`` (HTTPBearer auto-401s with no header,
    which would break the replay path), so JWT is verified inline here."""
    if x_internal_token:
        if not secrets.compare_digest(x_internal_token, app_settings.internal_service_token):
            raise HTTPException(status_code=401, detail="invalid internal token")
        if not x_user_id:
            raise HTTPException(status_code=401, detail="missing X-User-Id")
        return x_user_id, (x_mcp_key_id or None), _parse_spend_cap(x_mcp_spend_cap_usd)
    # FE / JWT path — attribution headers are deliberately ignored.
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing credentials")
    try:
        data = jwt.decode(authorization[7:], app_settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    return str(data["sub"]), None, None


async def _reauthorize_book(book_id: UUID, user_id: UUID) -> int:
    """Re-resolve the caller's CURRENT grant on the token-bound book at EDIT, at
    confirm time (NOT trusting the mint-time `u`/`r` claims). A grant revoked inside
    the confirm TTL must stop the spend. Fail-CLOSED: any resolver error → no grant
    → refuse (the grant client itself returns NONE on book-service unreachable).
    Returns the resolved grant level (int) so a caller can RE-CLAMP effort-auth
    against the fresh grant (a Manage→Edit downgrade in the TTL window mustn't replay
    a now-too-high reasoning effort baked into the token)."""
    try:
        lvl = await get_grant_client().resolve_grant(book_id, user_id)
    except Exception:  # noqa: BLE001 — fail-closed on any resolver error.
        raise _forbidden()
    if lvl == GrantLevel.NONE or not lvl.at_least(GrantLevel.EDIT):
        raise _forbidden()
    return int(lvl)


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
async def preview_action(
    token: str = Query(...),
    caller_user_id: str = Depends(get_current_user),
) -> PreviewResponse:
    """Re-surface the cost estimate BOUND into a confirm token (no re-price — the
    token already carries the estimate the user is being asked to confirm). The
    agent calls this to render the confirm card before committing."""
    claims = _verify(token)
    _assert_caller(claims, caller_user_id)
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
async def confirm_action(
    body: ConfirmRequest | None = None,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_mcp_key_id: str | None = Header(default=None, alias="X-Mcp-Key-Id"),
    x_mcp_spend_cap_usd: str | None = Header(default=None, alias="X-Mcp-Spend-Cap-Usd"),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """The ONLY start path for a priced translation job. Verify the token, assert
    the caller == the token's bound user, RE-AUTHORIZE the caller's CURRENT grant on
    the bound book + assert the chapter binding (a grant revoked inside the TTL stops
    the spend; a payload cannot retarget another book's chapters), then RE-PRICE the
    bound model (H14) over the accurate to-do/pending scope — either run the action
    or refuse with a re-confirm signal when the cost drifted up past tolerance.

    Dual-mode auth (D-PMCP-WORKER-CARRIER): the FE confirm card carries the user's
    JWT + the token in the body; the public-MCP auth-service replay carries
    X-Internal-Token + X-User-Id + ``?token=`` + (X-Mcp-Key-Id, X-Mcp-Spend-Cap-Usd).
    Only the replay path supplies a key/cap → it rides the job row + message so the
    background chapter worker attributes the spend to the agent's key."""
    caller_user_id, mcp_key_id, spend_cap_usd = _resolve_confirm_caller(
        x_internal_token, x_user_id, authorization, x_mcp_key_id, x_mcp_spend_cap_usd,
    )
    confirm_token = token or (body.confirm_token if body else None)
    if not confirm_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TRANSL_CONFIRM_INVALID", "message": "missing confirmation token"},
        )
    claims = _verify(confirm_token)
    _assert_caller(claims, caller_user_id)
    p = _payload(claims)
    user_id = str(claims.user_id)
    book_id = claims.resource_id  # the token binds the book as the resource (r).

    # ── RE-AUTHORIZE at confirm (review-impl HIGH) ────────────────────────────
    # Re-check the grant on the bound book NOW — never trust the mint-time claim.
    caller_grant_level = await _reauthorize_book(book_id, claims.user_id)

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
            mcp_key_id=mcp_key_id, spend_cap_usd=spend_cap_usd,
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

        job = await _retranslate_dirty_core(
            db, chapter_id, target_language, user_id,
            mcp_key_id=mcp_key_id, spend_cap_usd=spend_cap_usd,
        )
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

    if claims.descriptor == DESC_START_EXTRACTION:
        # Glossary chapter-extraction (M3). The grant was re-authorized above; assert
        # every requested chapter belongs to the bound book (a payload cannot retarget
        # another book's chapters). No H14 re-price: the extraction estimate is a
        # deterministic token-count projection over (chapter count × profile), not a
        # model-priced quote, so confirm-time == mint-time — re-running the core
        # re-computes the SAME estimate and stores it on the job row.
        chapter_ids = [UUID(c) for c in p.get("chapter_ids", [])]
        await _assert_chapters_under_book(book_id, chapter_ids)
        # RE-Q11 (effort-auth) — RE-CLAMP the baked effort against the CURRENT grant.
        # The mint clamped it too, but a grant downgrade inside the confirm TTL
        # (Manage→Edit) must not let a token replay a now-too-high paid effort.
        # Back-compat: a token minted before this field existed carries only the
        # `thinking_enabled` bool → treat True as the medium alias.
        requested_effort = p.get("reasoning_effort")
        if requested_effort is None and p.get("thinking_enabled"):
            requested_effort = "medium"
        effort, _capped = clamp_effort_to_grant(requested_effort, caller_grant_level)
        ext_payload = CreateExtractionJobPayload(
            chapter_ids=chapter_ids,
            extraction_profile=p.get("extraction_profile") or {},
            model_source=p.get("model_source") or "platform_model",
            model_ref=UUID(p["model_ref"]) if p.get("model_ref") else None,
            max_entities_per_kind=int(p.get("max_entities_per_kind", 30)),
            # D-RE-WORKER-GRADED-EFFORT: carry the GRADED effort through (not just the bool) so
            # low/high reach the worker. The core re-clamps (idempotent here). thinking_enabled
            # kept as the back-compat alias.
            reasoning_effort=effort,
            thinking_enabled=effort not in ("none", "off"),
        )
        result = await _create_extraction_job_core(
            db, book_id, claims.user_id, ext_payload,
            mcp_key_id=mcp_key_id, spend_cap_usd=spend_cap_usd,
        )
        return {
            "status": "action_done",
            "job_id": result["job_id"],
            "job_status": result.get("status"),
            "estimate": bound_estimate,
        }

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
