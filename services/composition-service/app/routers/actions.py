"""Tier-W confirm-token routes (S-COMPOSE — NET-NEW per C-CONFIRM / INV-9).

The MCP propose tool `composition_publish` MINTS a confirm token (bound to
user+resource+payload+expiry via the kit's `mint_confirm_token`); these two
routes are the FE-facing pair the generic `confirm_action` frontend tool drives:

  - GET  /v1/composition/actions/preview?token=  → decode + describe (no write)
  - POST /v1/composition/actions/confirm         → verify + EXECUTE (the ONLY
                                                    write path for the canonization)

Both are INTERNAL (X-Internal-Token) — the gateway/BFF calls them on behalf of an
already-authed user; the token itself binds the user identity (claim `u`) so a
token minted for user A can never be confirmed as user B (the confirm re-checks
`claims.user_id == envelope user_id`).

Descriptor namespace: `composition.publish` (C-CONFIRM map → this domain). The
token's `payload` carries the resolved publish spec captured at propose time
(`{project_id, chapter_id, book_id}`), so the confirm executes EXACTLY what was
proposed — the LLM cannot alter the target between propose and confirm.

H13 anti-oracle: a forged/expired/foreign token yields a uniform refusal, never
revealing whether the resource exists.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from loreweave_mcp import (
    ConfirmTokenExpired,
    ConfirmTokenInvalid,
    verify_confirm_token,
)

from app.config import settings
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.deps import get_grant_client_dep, get_outline_repo, get_works_repo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo
from app.db.models import CompositionWork
from app.mcp.service_bearer import mint_service_bearer
from app.clients.book_client import BookClient, BookClientError
from app.deps import get_book_client_dep
from app.packer.pack import OwnershipError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/composition/actions")

# The Tier-W descriptors this domain's confirm path commits. Most writes are
# Tier-A (auto-applied with Undo) and do NOT route through here; the two
# cost/canon-bearing actions are: the canonization (publish) and the grounded
# cowrite engine (generate, which spends LLM tokens).
_PUBLISH_DESCRIPTOR = "composition.publish"
_GENERATE_DESCRIPTOR = "composition.generate"

# W4 motif-library Tier-W descriptors. adopt is a tenancy/quota cross-tier clone;
# mine/import/conformance are LLM-spend 202+poll worker enqueues. All four are
# replay-guarded by the consumed-token ledger (they are NOT idempotent-by-effect
# like publish/generate); mine/import/conformance additionally run a real usage-
# billing precheck (fail-closed) BEFORE enqueue.
_MOTIF_ADOPT_DESCRIPTOR = "composition.motif_adopt"
_MOTIF_MINE_DESCRIPTOR = "composition.motif_mine"
_ARC_IMPORT_DESCRIPTOR = "composition.arc_import"
_CONFORMANCE_RUN_DESCRIPTOR = "composition.conformance_run"

# The full Tier-W descriptor allowlist this confirm path commits (MD-9 routes each
# to its scope: adopt/arc_import = user-scoped; mine = book/corpus; the rest = Work).
_ALL_DESCRIPTORS = (
    _PUBLISH_DESCRIPTOR, _GENERATE_DESCRIPTOR,
    _MOTIF_ADOPT_DESCRIPTOR, _MOTIF_MINE_DESCRIPTOR,
    _ARC_IMPORT_DESCRIPTOR, _CONFORMANCE_RUN_DESCRIPTOR,
)

# The generate effect's service bearer must outlive a multi-minute LLM generation
# AND the subsequent chapter-draft persist (which reuses it). 15 min is generous
# headroom for a slow local model on a long chapter (vs the 60s immediate-call default).
_GENERATE_BEARER_TTL_S = 900


def _require_internal_token(x_internal_token: str | None) -> None:
    """Gate these routes on the internal service token (mirrors the bespoke
    `/internal/*` chokepoint). The confirm TOKEN binds identity; this header
    proves the CALLER is the trusted gateway/BFF, not a random client."""
    if not settings.internal_service_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(status_code=401, detail="invalid or missing internal service token")


def _verify(token: str) -> Any:
    """Decode + verify a confirm token; map the kit's distinct failure modes to
    the C-CONFIRM outcome semantics. Invalid/forged → 400 (re-propose);
    expired → 410 (token_expired, distinct so the UI says 're-propose' not
    'denied')."""
    try:
        return verify_confirm_token(settings.confirm_token_signing_secret, token)
    except ConfirmTokenExpired as exc:
        raise HTTPException(status_code=410, detail={"code": "token_expired"}) from exc
    except ConfirmTokenInvalid as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc


def _jti(token: str) -> str:
    """The replay-ledger jti (W4-MD7). The C-KIT confirm token carries no `jti`
    claim, so synthesize a deterministic id from the signed token string itself: a
    replay of the SAME token reuses the exact bytes → same hash → the ledger's
    ON CONFLICT rejects it. Two distinct proposes (different exp/payload → different
    signature) get distinct jtis."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _exp_dt(claims: Any) -> datetime:
    """The confirm token's `exp` is unix seconds (int); the consumed_tokens.exp
    column is TIMESTAMPTZ. Convert for the ledger insert."""
    return datetime.fromtimestamp(int(claims.exp), tz=timezone.utc)


@router.get("/preview")
async def preview_action(
    token: str = Query(..., min_length=1),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict[str, Any]:
    """Decode the confirm token and return a human-readable descriptor of what
    confirming would do (NO side effects). The FE's confirm card renders this."""
    _require_internal_token(x_internal_token)
    claims = _verify(token)
    payload = claims.payload if isinstance(claims.payload, dict) else {}
    return {
        "descriptor": claims.descriptor,
        "resource_id": str(claims.resource_id),
        "payload": payload,
        "expires_at": claims.exp,
    }


@router.post("/confirm")
async def confirm_action(
    token: str = Query(..., min_length=1),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Verify the token and EXECUTE the bound action — the ONLY write path for a
    Tier-W S-COMPOSE action. Returns `{outcome: "action_done", ...}` on success.

    Re-checks: (1) the token's `u` (proposing user) MUST equal the envelope
    `X-User-Id` (a token minted for A can't be confirmed as B); (2) the caller
    still owns the Work + holds EDIT on its book at confirm time (a grant revoked
    between propose and confirm stops the write)."""
    _require_internal_token(x_internal_token)
    claims = _verify(token)

    # Identity binding (INV-9): the confirming envelope user must be the proposer.
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id")
    try:
        envelope_user = UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid X-User-Id") from exc
    if envelope_user != claims.user_id:
        # H13 anti-oracle — uniform refusal, never reveal "this token is someone else's".
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    if claims.descriptor not in _ALL_DESCRIPTORS:
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    payload = claims.payload if isinstance(claims.payload, dict) else {}

    # ── adopt + arc_import are USER-scoped (no Work/book — R1.1 / §12.6): they SKIP
    # the shared Work re-resolve and re-check their own user-scope owner inside the
    # effect (MD-9). Both are replay-guarded by the consumed-token ledger.
    if claims.descriptor == _MOTIF_ADOPT_DESCRIPTOR:
        return await _execute_motif_adopt(payload, envelope_user, token=token, claims=claims)
    if claims.descriptor == _ARC_IMPORT_DESCRIPTOR:
        return await _execute_arc_import(payload, envelope_user, token=token, claims=claims)

    # ── mine is BOOK/CORPUS-scoped, NOT Work-scoped (its payload has no project_id —
    # it binds book_id for scope='book', user for 'corpus'). Re-check the BOOK grant
    # directly for scope='book' (a grant revoked since propose stops the spend); a
    # corpus mine is envelope-identity-gated (the worker re-checks each book touched).
    if claims.descriptor == _MOTIF_MINE_DESCRIPTOR:
        if str(payload.get("scope")) == "book":
            try:
                book_id = UUID(str(payload["book_id"]))
            except (KeyError, ValueError, TypeError) as exc:
                raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
            try:
                await authorize_book(grant, book_id, envelope_user, GrantLevel.EDIT)
            except (OwnershipError, InsufficientGrant) as exc:
                raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc
        return await _execute_motif_mine(payload, envelope_user, token=token, claims=claims)

    # ── Work-scoped descriptors (publish / generate / conformance): re-resolve
    # ownership + EDIT at confirm time (the Work is user-scoped → None if not the
    # caller's; the grant may have been revoked since propose).
    try:
        project_id = UUID(str(payload["project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    work = await works.get(envelope_user, project_id)
    if work is None:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        await authorize_book(grant, work.book_id, envelope_user, GrantLevel.EDIT)
    except (OwnershipError, InsufficientGrant) as exc:
        raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc

    if claims.descriptor == _PUBLISH_DESCRIPTOR:
        return await _execute_publish(payload, project_id, work, envelope_user, outline, book)
    if claims.descriptor == _GENERATE_DESCRIPTOR:
        return await _execute_generate(payload, project_id, work, envelope_user)
    return await _execute_conformance_run(payload, project_id, work, envelope_user,
                                          token=token, claims=claims)


async def _execute_publish(
    payload: dict[str, Any], project_id: UUID, work: CompositionWork,
    envelope_user: UUID, outline: OutlineRepo, book: BookClient,
) -> dict[str, Any]:
    """composition.publish effect — canonize a reviewed chapter draft (CM1)."""
    try:
        chapter_id = UUID(str(payload["chapter_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    # Canonization gate (CM1 / OI-1): a chapter is publishable ONLY when all its
    # composition scenes are 'done' and no unresolved canon contradiction survives
    # (the SAME gate the FE's Publish affordance reads). Re-check at execute time.
    gate = await outline.chapter_scene_gate(envelope_user, project_id, chapter_id)
    if not gate.get("can_publish"):
        raise HTTPException(
            status_code=409,
            detail={"code": "action_error", "reason": "not_publishable", "gate": gate},
        )

    # Execute the publish against book-service (canonize the chapter draft). The MCP
    # path has no JWT, so mint a short-lived service bearer for the envelope user
    # (see service_bearer.py); book-service re-checks ownership in SQL on `sub`.
    bearer = mint_service_bearer(envelope_user, settings.jwt_secret)
    try:
        result = await book.publish_chapter(work.book_id, chapter_id, bearer)
    except BookClientError as exc:
        # Surface book-service's client errors as a uniform action_error; a 5xx is
        # an upstream failure (the action did not complete).
        logger.warning("composition.publish book-service error: %s", exc)
        raise HTTPException(status_code=502, detail={"code": "action_error"}) from exc

    return {
        "outcome": "action_done",
        "descriptor": _PUBLISH_DESCRIPTOR,
        "project_id": str(project_id),
        "chapter_id": str(chapter_id),
        "book": result,
    }


async def _execute_generate(
    payload: dict[str, Any], project_id: UUID, work: CompositionWork, envelope_user: UUID,
) -> dict[str, Any]:
    """composition.generate effect — run the grounded cowrite ENGINE (the only
    spend path for the MCP `composition_generate` tool). Calls the engine router
    coroutine IN-PROCESS (the deps are trivial per-request factories) in auto
    (non-stream) mode, so the full canon-grounded drafter+critic pipeline runs and
    returns JSON. The MCP path has no JWT → mint a short-lived service bearer for
    the envelope user (book-service still enforces ownership in SQL on `sub`)."""
    # Imported here (not at module top) to avoid an import cycle: the engine router
    # imports the action confirm helpers' siblings; deferring keeps actions.py light.
    from app.routers import engine as engine_router
    from app.clients.book_client import get_book_client
    from app.clients.glossary_client import get_glossary_client
    from app.clients.knowledge_client import get_knowledge_client
    from app.clients.llm_client import get_llm_client
    from app.db.pool import get_pool
    from app.db.repositories.canon_rules import CanonRulesRepo
    from app.db.repositories.derivatives import DerivativesRepo
    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.db.repositories.narrative_thread import NarrativeThreadRepo
    from app.db.repositories.scene_links import SceneLinksRepo

    target_kind = str(payload.get("target_kind") or "")
    target_id_raw = payload.get("target_id")
    model_source = str(payload.get("model_source") or "")
    model_ref_raw = payload.get("model_ref")
    if target_kind not in ("scene", "chapter") or not target_id_raw or not model_ref_raw:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        target_id = UUID(str(target_id_raw))
        model_ref = UUID(str(model_ref_raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    guide = str(payload.get("guide") or "")
    reasoning = str(payload.get("reasoning") or "auto")
    max_out = payload.get("max_output_tokens")
    operation = payload.get("operation")

    # Generation can run for MINUTES (a slow local model + a long chapter), and the
    # chapter path REUSES this bearer to persist the draft AFTER generation — so a
    # 60s token (the default) would be expired by the persist, silently dropping the
    # draft write. Mint a generous TTL covering the worst-case generation+persist.
    bearer = mint_service_bearer(envelope_user, settings.jwt_secret, ttl=_GENERATE_BEARER_TTL_S)
    pool = get_pool()
    deps = dict(
        works=WorksRepo(pool), outline=OutlineRepo(pool),
        scene_links=SceneLinksRepo(pool), canon=CanonRulesRepo(pool),
        jobs=GenerationJobsRepo(pool), book=get_book_client(),
        glossary=get_glossary_client(), knowledge=get_knowledge_client(),
        llm=get_llm_client(), narrative_threads=NarrativeThreadRepo(pool),
        derivatives=DerivativesRepo(pool),
    )
    # Build the engine body from the (signed, tamper-proof) payload. The propose
    # tool already constrains the enums, but guard the construction so a malformed
    # payload is a clean 400 rather than a pydantic 500.
    try:
        if target_kind == "scene":
            body_kwargs: dict[str, Any] = dict(
                outline_node_id=target_id, model_source=model_source, model_ref=model_ref,
                mode="auto", guide=guide, reasoning=reasoning,
                operation=operation or "draft_scene",
            )
            if max_out is not None:
                body_kwargs["max_output_tokens"] = int(max_out)
            body = engine_router.GenerateBody(**body_kwargs)
        else:
            body_kwargs = dict(
                model_source=model_source, model_ref=model_ref, guide=guide,
                reasoning=reasoning, operation=operation or "draft_chapter",
                persist=True,
            )
            if max_out is not None:
                body_kwargs["max_output_tokens"] = int(max_out)
            body = engine_router.GenerateChapterBody(**body_kwargs)
    except (ValueError, TypeError) as exc:  # pydantic ValidationError ⊂ ValueError
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    try:
        if target_kind == "scene":
            resp = await engine_router.generate(
                project_id, body, user_id=envelope_user, bearer=bearer, **deps)
        else:
            resp = await engine_router.generate_chapter(
                project_id, target_id, body, user_id=envelope_user, bearer=bearer, **deps)
    except HTTPException:
        # The engine's own HTTPExceptions (404 not found / 403 insufficient / 413
        # too-large / 409 use-chapter-endpoint / 502 upstream) are already
        # meaningful — let them propagate to the FE confirm card unchanged.
        raise

    # The engine returns a JSONResponse in auto mode; surface its body verbatim.
    try:
        result = json.loads(resp.body)
    except (ValueError, AttributeError, TypeError):
        result = {}
    return {
        "outcome": "action_done",
        "descriptor": _GENERATE_DESCRIPTOR,
        "project_id": str(project_id),
        "target_kind": target_kind,
        "target_id": str(target_id),
        "generation": result,
    }


# ══════════════════════════════════════════════════════════════════════════════
# W4 — Tier-W motif confirm effects. adopt = tenancy/quota cross-tier clone (no
# LLM spend, ledger-guarded); mine/import/conformance = LLM-spend 202+poll worker
# enqueues (ledger-claim → real usage-billing precheck → enqueue). The compute for
# mine/import/conformance is owned by W8/W9/W5 (Wave 2); W4 owns the enqueue + poll
# + ledger + precheck SEAM — until those WSs land the job sits `pending` and the
# poll returns `pending` (the contract is the enqueue, not the compute).
# ══════════════════════════════════════════════════════════════════════════════


async def _claim_or_replay(token: str, claims: Any) -> None:
    """Consume-first replay guard (W4 §3.2). Claim the jti BEFORE the effect; a
    replay of the same token hits the ledger PK → 409 already_consumed. A spent
    token never re-applies (fail-closed) — the human re-proposes."""
    from app.db.pool import get_pool
    from app.db.repositories.consumed_tokens import ConsumedTokenRepo

    ledger = ConsumedTokenRepo(get_pool())
    won = await ledger.consume(jti=_jti(token), descriptor=claims.descriptor, exp=_exp_dt(claims))
    if not won:
        raise HTTPException(status_code=409, detail={"code": "action_error", "reason": "already_consumed"})


async def _precheck_or_402(*, owner_user_id: UUID, job_id: str, estimate_usd: float) -> None:
    """Real usage-billing precheck (W4 §3.3, MD-8 fail-CLOSED). Runs BEFORE the
    enqueue so an over-budget caller never queues spend; a billing outage denies the
    new spend (billing_unavailable) rather than letting it through."""
    from app.clients.billing_client import get_billing_client

    billing = get_billing_client()
    ok = await billing.precheck(
        owner_user_id=str(owner_user_id), job_id=job_id, estimate_usd=estimate_usd,
    )
    if not ok:
        raise HTTPException(
            status_code=402,
            detail={"code": "action_error", "reason": "quota_exhausted"},
        )


async def _enqueue_motif_job(
    *, envelope_user: UUID, project_id: UUID | None, operation: str, spec: dict[str, Any],
) -> str:
    """Create a pending generation_job + best-effort enqueue the worker trigger.
    Returns the job id. The job row persists even if the Redis XADD blips (the
    sweeper re-drives) — consistent with the platform best-effort enqueue rail."""
    from uuid import uuid4

    from app.db.pool import get_pool
    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.worker.events import enqueue_job

    jobs = GenerationJobsRepo(get_pool())
    # mine/import/conformance are not Work-bound for the corpus case; generation_job
    # requires a project_id (NOT NULL). For a book/corpus mine with no Work, stamp a
    # synthetic project_id from the user so the row is valid + user-scoped. (The
    # Wave-2 worker reads worker_op from input, not project_id.) Where a real Work
    # project_id exists (conformance), use it.
    pid = project_id if project_id is not None else uuid4()
    job, _created = await jobs.create(
        envelope_user, pid, operation=operation,
        input={"worker_op": operation, **spec}, status="pending",
    )
    await enqueue_job(
        settings.redis_url, job_id=str(job.id),
        user_id=str(envelope_user), project_id=str(pid),
    )
    return str(job.id)


async def _execute_motif_adopt(
    payload: dict[str, Any], envelope_user: UUID, *, token: str, claims: Any,
) -> dict[str, Any]:
    """composition.motif_adopt effect — clone a public/system motif into the caller's
    library (the ONE clone primitive). Ledger-claim → quota → clone. No LLM spend, so
    no billing precheck; the quota ceiling (motif_max_adopt) is the tenancy guard."""
    from app.db.pool import get_pool
    from app.db.repositories.motif_repo import MotifRepo

    try:
        motif_id = UUID(str(payload["motif_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    retag = payload.get("retag_genres")
    if retag is not None and not isinstance(retag, list):
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    # Replay guard FIRST (a replayed adopt past the quota would double-add).
    await _claim_or_replay(token, claims)

    repo = MotifRepo(get_pool())
    # Re-check visibility at confirm (you may adopt only what you can still see).
    src = await repo.get_visible(envelope_user, motif_id)
    if src is None:
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    # Quota (B-4): count the caller's library; 0 = unlimited (dev default off).
    ceiling = int(getattr(settings, "motif_max_adopt", 0) or 0)
    if ceiling > 0:
        owned = await repo.list_for_caller(envelope_user, scope="user", status=None, limit=10_000)
        if len(owned) >= ceiling:
            raise HTTPException(
                status_code=402,
                detail={"code": "action_error", "reason": "quota_exhausted"},
            )

    try:
        clone = await repo.clone(
            envelope_user, motif_id, target_owner=envelope_user, retag_genres=retag,
        )
    except LookupError as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    except Exception as exc:  # noqa: BLE001 — code collision etc. → uniform action_error
        # A UniqueViolation (the source code already exists in the caller's tier) is a
        # benign idempotency outcome; surface a clean conflict rather than a 500.
        logger.info("motif adopt clone conflict/error: %s", exc)
        raise HTTPException(
            status_code=409,
            detail={"code": "action_error", "reason": "already_adopted"},
        ) from exc

    return {
        "outcome": "action_done",
        "descriptor": _MOTIF_ADOPT_DESCRIPTOR,
        "motif_id": str(clone.id),
    }


async def _execute_motif_mine(
    payload: dict[str, Any], envelope_user: UUID, *, token: str, claims: Any,
) -> dict[str, Any]:
    """composition.motif_mine effect — ledger-claim → usage-billing precheck →
    enqueue a `mine_motifs` worker job (202+poll). The compute is owned by W8."""
    await _claim_or_replay(token, claims)
    estimate = float(payload.get("estimate_usd") or 0.0)
    # job_id for the idempotent precheck reserve = the jti (one hold per proposal).
    await _precheck_or_402(owner_user_id=envelope_user, job_id=_jti(token), estimate_usd=estimate)
    job_id = await _enqueue_motif_job(
        envelope_user=envelope_user, project_id=None, operation="mine_motifs",
        spec={
            "scope": payload.get("scope"),
            "book_id": payload.get("book_id"),
            "min_support": payload.get("min_support"),
            "promote_to": payload.get("promote_to"),
            "language": payload.get("language"),
        },
    )
    return {
        "outcome": "action_accepted",
        "descriptor": _MOTIF_MINE_DESCRIPTOR,
        "job_id": job_id,
        "poll": "composition_get_mine_job",
    }


async def _execute_arc_import(
    payload: dict[str, Any], envelope_user: UUID, *, token: str, claims: Any,
) -> dict[str, Any]:
    """composition.arc_import effect — re-check the import_source owner (user-scoped,
    un-shareable §12.6), then ledger-claim → precheck → enqueue `analyze_reference`
    (202+poll). The compute is owned by W9."""
    from app.db.pool import get_pool

    try:
        import_source_id = UUID(str(payload["import_source_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    # Re-check ownership at confirm (the import_source row is per-user, no visibility
    # column — a foreign id is a uniform action_error, never an oracle).
    owner = await get_pool().fetchval(
        "SELECT owner_user_id FROM import_source WHERE id = $1", import_source_id
    )
    if owner is None or owner != envelope_user:
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    await _claim_or_replay(token, claims)
    estimate = float(payload.get("estimate_usd") or 0.0)
    await _precheck_or_402(owner_user_id=envelope_user, job_id=_jti(token), estimate_usd=estimate)
    job_id = await _enqueue_motif_job(
        envelope_user=envelope_user, project_id=None, operation="analyze_reference",
        spec={
            "import_source_id": str(import_source_id),
            "use_web": payload.get("use_web"),
            "arc_hint": payload.get("arc_hint"),
        },
    )
    return {
        "outcome": "action_accepted",
        "descriptor": _ARC_IMPORT_DESCRIPTOR,
        "job_id": job_id,
        "poll": "composition_get_mine_job",
    }


async def _execute_conformance_run(
    payload: dict[str, Any], project_id: UUID, work: CompositionWork, envelope_user: UUID,
    *, token: str, claims: Any,
) -> dict[str, Any]:
    """composition.conformance_run effect — ledger-claim → precheck → enqueue a
    `conformance_run` job (202+poll). The compute is owned by W5."""
    await _claim_or_replay(token, claims)
    estimate = float(payload.get("estimate_usd") or 0.0)
    await _precheck_or_402(owner_user_id=envelope_user, job_id=_jti(token), estimate_usd=estimate)
    job_id = await _enqueue_motif_job(
        envelope_user=envelope_user, project_id=project_id, operation="conformance_run",
        spec={
            "book_id": str(work.book_id),
            "scope": payload.get("scope"),
            "chapter_id": payload.get("chapter_id"),
        },
    )
    return {
        "outcome": "action_accepted",
        "descriptor": _CONFORMANCE_RUN_DESCRIPTOR,
        "job_id": job_id,
        "poll": "composition_get_mine_job",
    }
