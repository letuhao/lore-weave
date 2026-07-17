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
    apply_public_key_attribution_headers,
    verify_confirm_token,
)

from app.config import settings
from app.middleware.jwt_auth import get_optional_current_user
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
# close-21-28 P-O2a — the deterministic arc decompiler (book-scoped, EDIT-gated at confirm).
_DECOMPILE_DESCRIPTOR = "composition.decompile"
# D-DIVERGENCE-MCP-TOOLS (S5) — the derive (spawn a dị bản). BOOK-scoped (payload carries the
# source project_id + book_id), EDIT-gated at confirm. Mints a knowledge partition + persists the
# branch spec via the shared `perform_derive`. No replay ledger (like publish/generate — a re-
# confirmed token would mint a SECOND partition, but the token is single-use by the confirm flow).
_DERIVE_DESCRIPTOR = "composition.derive"

# D-AGENT-MODE §20 D5/D6 — the authoring-run confirm-gated descriptors. Like
# motif_adopt/arc_import, these are BOOK-scoped (a book_id in the payload), NOT
# Work/project_id-scoped — they skip the shared Work re-resolve below and are
# EDIT-gated directly on the payload's book_id (mirrors the motif_adopt
# per-book branch). No replay ledger (mirrors publish/generate, not the W4
# mine/import/conformance jobs — D6 says "same shape as composition_generate").
_AUTHORING_RUN_CREATE_DESCRIPTOR = "composition.authoring_run_create"
_AUTHORING_RUN_GATE_DESCRIPTOR = "composition.authoring_run_gate"
_AUTHORING_RUN_START_DESCRIPTOR = "composition.authoring_run_start"
_AUTHORING_RUN_RESUME_DESCRIPTOR = "composition.authoring_run_resume"
_AUTHORING_RUN_REVERT_ALL_DESCRIPTOR = "composition.authoring_run_revert_all"
_AUTHORING_RUN_DESCRIPTORS = (
    _AUTHORING_RUN_CREATE_DESCRIPTOR, _AUTHORING_RUN_GATE_DESCRIPTOR,
    _AUTHORING_RUN_START_DESCRIPTOR, _AUTHORING_RUN_RESUME_DESCRIPTOR,
    _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR,
)

# The full Tier-W descriptor allowlist this confirm path commits (MD-9 routes each
# to its scope: adopt/arc_import = user-scoped; mine = book/corpus; the rest = Work).
_ALL_DESCRIPTORS = (
    _PUBLISH_DESCRIPTOR, _GENERATE_DESCRIPTOR,
    _MOTIF_ADOPT_DESCRIPTOR, _MOTIF_MINE_DESCRIPTOR,
    _ARC_IMPORT_DESCRIPTOR, _CONFORMANCE_RUN_DESCRIPTOR,
    _DECOMPILE_DESCRIPTOR, _DERIVE_DESCRIPTOR,
    *_AUTHORING_RUN_DESCRIPTORS,
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


def _resolve_envelope_user(
    jwt_user: UUID | None, x_internal_token: str | None, x_user_id: str | None
) -> UUID:
    """Resolve WHO is confirming/previewing, accepting EITHER identity path:

    - **FE path** — a valid Bearer JWT is sufficient identity (mirrors glossary's
      JWT-authed `/actions/confirm`). The signed confirm token is the capability; the
      JWT only proves who is wielding it. This makes the Tier-W confirm reachable
      directly from the FE through the BFF (no internal token, which the BFF never
      injects for `/v1/composition/*`).
    - **Service/MCP path** — the internal service token + an `X-User-Id` envelope (the
      ai-gateway/BFF set these for service-to-service calls).

    The route's identity binding (envelope_user == the token's proposing user) is
    enforced by the caller AFTER this resolves, so neither path can confirm another
    user's token."""
    if jwt_user is not None:
        return jwt_user
    _require_internal_token(x_internal_token)
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id")
    try:
        return UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid X-User-Id") from exc


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


def _billing_job_id(token: str) -> str:
    """usage-billing's guardrail `reserve` keys idempotency by a UUID `job_id`
    (`JobID uuid.UUID`). The natural key is the proposal's jti, but `_jti` is a
    64-char SHA-256 HEX (the ledger key) which is NOT a UUID — sending it makes the
    reserve fail to JSON-decode (400 GUARDRAIL_INVALID) → the fail-closed precheck
    denies EVERY Tier-W LLM-spend (402 quota_exhausted). Derive a deterministic UUID
    from the first 128 bits of the same hash so the reserve stays idempotent per
    proposal (same token → same reservation)."""
    return str(UUID(hex=hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]))


def _exp_dt(claims: Any) -> datetime:
    """The confirm token's `exp` is unix seconds (int); the consumed_tokens.exp
    column is TIMESTAMPTZ. Convert for the ledger insert."""
    return datetime.fromtimestamp(int(claims.exp), tz=timezone.utc)


@router.get("/preview")
async def preview_action(
    token: str = Query(..., min_length=1),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    jwt_user: UUID | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Decode the confirm token and return a human-readable descriptor of what
    confirming would do (NO side effects). The FE's confirm card renders this.

    Accepts EITHER a Bearer JWT (FE) or the internal-token envelope (service). On
    the JWT path the previewing user must own the token (a user can't preview someone
    else's proposal); the internal path is the trusted gateway (no per-user binding,
    historically X-User-Id-free for this read-only describe)."""
    if jwt_user is None:
        # Service path — internal token only (unchanged; preview never required
        # X-User-Id here, the gateway is the trusted caller).
        _require_internal_token(x_internal_token)
    claims = _verify(token)
    if jwt_user is not None and jwt_user != claims.user_id:
        # H13 anti-oracle — uniform refusal, never reveal "this token is someone else's".
        raise HTTPException(status_code=400, detail={"code": "action_error"})
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
    jwt_user: UUID | None = Depends(get_optional_current_user),
    x_mcp_key_id: str | None = Header(default=None, alias="X-Mcp-Key-Id"),
    x_mcp_spend_cap_usd: str | None = Header(default=None, alias="X-Mcp-Spend-Cap-Usd"),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Verify the token and EXECUTE the bound action — the ONLY write path for a
    Tier-W S-COMPOSE action. Returns `{outcome: "action_done", ...}` on success.

    Identity comes from EITHER a Bearer JWT (the FE path — the confirm token is the
    capability, the JWT proves who wields it; mirrors glossary) OR the internal-token
    + `X-User-Id` envelope (the service/MCP path). Re-checks: (1) the token's `u`
    (proposing user) MUST equal the confirming envelope user (a token minted for A
    can't be confirmed as B); (2) the caller still owns the Work + holds EDIT on its
    book at confirm time (a grant revoked between propose and confirm stops the write).

    Public-MCP spend attribution (P4/Wave-C slice A): when this confirm originates
    from an approved public-key action, `X-Mcp-Key-Id` (+ optional cap) is lifted
    into the loreweave_llm contextvar so the IN-PROCESS `composition.generate`
    submit tags its `job_meta` with the agent's key — cost lands on the key, not the
    human session. This route is NOT an MCP tool call, so the kit's universal hook
    (`build_tool_context`) never fires here; we set it explicitly and clear it in a
    `finally` to avoid leaking across pooled requests."""
    envelope_user = _resolve_envelope_user(jwt_user, x_internal_token, x_user_id)
    claims = _verify(token)

    # Identity binding (INV-9): the confirming envelope user must be the proposer.
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
        # D-MOTIF-ADOPT-PER-BOOK: a book-targeted adopt is EDIT-gated on the book — re-check
        # at confirm (a grant revoked since propose stops the clone), mirroring scope=book mine.
        book_target = payload.get("book_id")
        if book_target:
            try:
                book_uuid = UUID(str(book_target))
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
            try:
                await authorize_book(grant, book_uuid, envelope_user, GrantLevel.EDIT)
            except (OwnershipError, InsufficientGrant) as exc:
                raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc
        return await _execute_motif_adopt(payload, envelope_user, token=token, claims=claims)
    if claims.descriptor == _ARC_IMPORT_DESCRIPTOR:
        return await _execute_arc_import(payload, envelope_user, token=token, claims=claims)

    # ── P-O2a: decompile is BOOK-scoped + deterministic ($0, no LLM, no worker). Re-check EDIT on
    # the book at confirm (a grant revoked since propose stops the mutation), then apply the effect
    # synchronously (mirrors the authoring-run per-book re-gate, minus the billing/worker path).
    if claims.descriptor == _DECOMPILE_DESCRIPTOR:
        try:
            book_id = UUID(str(payload["book_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
        try:
            await authorize_book(grant, book_id, envelope_user, GrantLevel.EDIT)
        except (OwnershipError, InsufficientGrant) as exc:
            raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc
        return await _execute_decompile(payload, book_id, envelope_user, token=token, claims=claims)

    # ── D-DIVERGENCE-MCP-TOOLS: derive is BOOK-scoped (payload has the source project_id + book_id).
    # Re-gate EDIT on the book at confirm (a grant revoked since propose stops the mint), then run the
    # shared perform_derive (mint knowledge partition + persist the branch spec in one txn).
    if claims.descriptor == _DERIVE_DESCRIPTOR:
        try:
            book_id = UUID(str(payload["book_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
        try:
            await authorize_book(grant, book_id, envelope_user, GrantLevel.EDIT)
        except (OwnershipError, InsufficientGrant) as exc:
            raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc
        return await _execute_derive(payload, envelope_user, works=works, book=book)

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

    # ── D-AGENT-MODE §20: authoring-run descriptors are BOOK-scoped (no Work/
    # project_id — mirrors motif_adopt's per-book branch). Re-check EDIT on the
    # book at confirm time (a grant revoked since propose stops the write).
    if claims.descriptor in _AUTHORING_RUN_DESCRIPTORS:
        try:
            book_id = UUID(str(payload["book_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
        try:
            await authorize_book(grant, book_id, envelope_user, GrantLevel.EDIT)
        except (OwnershipError, InsufficientGrant) as exc:
            raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc
        if claims.descriptor == _AUTHORING_RUN_CREATE_DESCRIPTOR:
            return await _execute_authoring_run_create(payload, book_id, envelope_user)
        if claims.descriptor == _AUTHORING_RUN_GATE_DESCRIPTOR:
            return await _execute_authoring_run_gate(payload, book_id, envelope_user, book)
        if claims.descriptor == _AUTHORING_RUN_START_DESCRIPTOR:
            return await _execute_authoring_run_start(payload, book_id, envelope_user)
        if claims.descriptor == _AUTHORING_RUN_RESUME_DESCRIPTOR:
            return await _execute_authoring_run_resume(payload, book_id, envelope_user)
        return await _execute_authoring_run_revert_all(payload, book_id, envelope_user, book)

    # ── Work-scoped descriptors (publish / generate / conformance): re-resolve
    # ownership + EDIT at confirm time (the Work is user-scoped → None if not the
    # caller's; the grant may have been revoked since propose).
    try:
        project_id = UUID(str(payload["project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        await authorize_book(grant, work.book_id, envelope_user, GrantLevel.EDIT)
    except (OwnershipError, InsufficientGrant) as exc:
        raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc

    if claims.descriptor == _PUBLISH_DESCRIPTOR:
        return await _execute_publish(payload, project_id, work, envelope_user, outline, book)
    if claims.descriptor == _GENERATE_DESCRIPTOR:
        # Carrier-lift around the IN-PROCESS LLM spend: set the public-key attribution
        # contextvar before _execute_generate submits its LLM job, and clear it in `finally`
        # so it can't leak into the next pooled request (P4/Wave-C slice A). publish/
        # conformance_run don't spend in-process (publish writes; conformance_run enqueues a
        # 202+poll worker job), so they stay outside the lift.
        apply_public_key_attribution_headers(x_mcp_key_id, x_mcp_spend_cap_usd)
        try:
            return await _execute_generate(payload, project_id, work, envelope_user)
        finally:
            apply_public_key_attribution_headers(None, None)
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
    gate = await outline.chapter_scene_gate(project_id, chapter_id)
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
    sweeper re-drives) — consistent with the platform best-effort enqueue rail.

    BE-7c — the PAID-ACTION FIX. This used to stamp a SYNTHETIC `uuid4()` project_id
    when the caller had none (a corpus/book mine is genuinely not Work-bound). But
    `create()` DERIVES book_id from `composition_work` inside its INSERT…SELECT, so a
    synthetic pid matched no row ⇒ zero rows inserted ⇒ ReferenceViolationError ⇒
    /actions/confirm 500'd — AFTER `_claim_or_replay` burnt the confirm token and
    `_precheck_or_402` reserved the billing hold. The user paid and got nothing, and
    there was no job row to poll. A Work-less job now says so: project_id/book_id NULL,
    scoped by `created_by`. NEVER back-fill a phantom composition_work per mine.
    """
    from app.db.pool import get_pool
    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.worker import events as worker_events

    jobs = GenerationJobsRepo(get_pool())
    if project_id is None:
        job = await jobs.create_unbound(
            created_by=envelope_user, operation=operation,
            input={"worker_op": operation, **spec}, status="pending",
        )
    else:
        job, _created = await jobs.create(
            project_id, created_by=envelope_user, operation=operation,
            input={"worker_op": operation, **spec}, status="pending",
        )
    # An unbound job carries no project on the stream. Safe: `run_job`
    # (job_consumer.py:225-237) re-loads the job from the DB by id and never reads the
    # stream's project_id (dispatch_job_message forwards only job_id + user_id).
    await worker_events.enqueue_job(
        settings.redis_url, job_id=str(job.id),
        user_id=str(envelope_user),
        project_id=str(project_id) if project_id is not None else "",
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
    # D-MOTIF-ADOPT-PER-BOOK / -BOOK-COLLAB-TIER: the per-book label or shared-tier flag (the
    # dispatch already re-gated EDIT on the book when book_id is present).
    book_label = payload.get("book_id")
    book_shared = bool(payload.get("book_shared"))
    try:
        book_uuid = UUID(str(book_label)) if book_label else None
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    # book_shared MUST carry a book — a shared clone without a (gated) book is a tenancy defect.
    if book_shared and book_uuid is None:
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
            book_id=book_uuid, book_shared=book_shared,
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
    await _precheck_or_402(owner_user_id=envelope_user, job_id=_billing_job_id(token), estimate_usd=estimate)
    job_id = await _enqueue_motif_job(
        envelope_user=envelope_user, project_id=None, operation="mine_motifs",
        spec={
            "scope": payload.get("scope"),
            "book_id": payload.get("book_id"),
            "min_support": payload.get("min_support"),
            "promote_to": payload.get("promote_to"),
            # D-MOTIF-ADOPT-BOOK-COLLAB-TIER: mined drafts may land in the book's SHARED tier.
            # The mine proposal already EDIT-gated the book (scope='book'); the mine-dispatch
            # below re-checks that BOOK grant at confirm, so a shared promote stays gated.
            "promote_target": payload.get("promote_target"),
            "language": payload.get("language"),
            # BYOK abstraction/judge model rides through (provider-gateway invariant); the
            # worker fails closed if neither this nor the platform fallback resolves a ref.
            "model_ref": payload.get("model_ref"),
            "model_source": payload.get("model_source"),
        },
    )
    return {
        "outcome": "action_accepted",
        "descriptor": _MOTIF_MINE_DESCRIPTOR,
        "job_id": job_id,
        "poll": "composition_get_mine_job",
    }


async def _execute_decompile(
    payload: dict[str, Any], book_id: UUID, envelope_user: UUID, *, token: str, claims: Any,
) -> dict[str, Any]:
    """composition.decompile effect (P-O2a) — the DETERMINISTIC arc decompiler. The grant was
    re-checked at the dispatch above; here we ledger-claim (replay guard) then run the engine
    synchronously ($0, no LLM, idempotent — reuses existing decompiled arcs by position). Returns
    the engine's `{arcs, chapters_assigned, arc_ids, reason?}` so the caller sees exactly what landed."""
    from app.db.pool import get_pool
    from app.engine.arc_decompile import decompile_arcs

    try:
        per = max(1, int(payload.get("chapters_per_arc") or 10))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    # Replay guard: a re-submitted token returns the prior outcome, never a second mutation.
    await _claim_or_replay(token, claims)
    result = await decompile_arcs(
        get_pool(), book_id, created_by=envelope_user, chapters_per_arc=per,
    )
    return {"outcome": "action_accepted", "descriptor": _DECOMPILE_DESCRIPTOR, **result}


async def _execute_derive(
    payload: dict[str, Any], envelope_user: UUID, *, works: WorksRepo, book: BookClient,
) -> dict[str, Any]:
    """composition.derive effect (D-DIVERGENCE-MCP-TOOLS) — mint a fresh knowledge partition +
    persist the derivative Work + divergence_spec + entity_override[] via the SHARED perform_derive
    (the same path the REST /derive route runs). The grant was re-checked at the dispatch above.
    Rebuilds the DeriveBody from the SIGNED payload (the LLM can't alter the target between propose
    and confirm). Mints a user-scoped service bearer for book.get_book + knowledge.create_project."""
    from app.clients.knowledge_client import get_knowledge_client
    from app.db.pool import get_pool
    from app.db.repositories.derivatives import DerivativesRepo
    from app.routers.works import (
        DeriveBody, DivergenceSpecBody, EntityOverrideBody, perform_derive,
    )

    try:
        source_pid = UUID(str(payload["source_project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    source = await works.get(source_pid)
    if source is None or source.source_work_id is not None:
        # gone since propose, or somehow a derivative — uniform refusal (anti-oracle).
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        overrides = [
            EntityOverrideBody(
                target_entity_id=UUID(str(o["target_entity_id"])),
                overridden_fields=o.get("overridden_fields") or {},
            )
            for o in (payload.get("entity_overrides") or [])
        ]
        body = DeriveBody(
            name=payload.get("name"),
            branch_point=payload.get("branch_point"),
            divergence=DivergenceSpecBody(
                taxonomy=payload.get("taxonomy") or "au",
                pov_anchor=(UUID(str(payload["pov_anchor"])) if payload.get("pov_anchor") else None),
                canon_rule=list(payload.get("canon_rule") or []),
            ),
            entity_overrides=overrides,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    bearer = mint_service_bearer(envelope_user, settings.jwt_secret, ttl=120)
    pool = get_pool()
    work = await perform_derive(
        source, body, envelope_user,
        works=works, derivatives=DerivativesRepo(pool),
        knowledge=get_knowledge_client(), book=book, bearer=bearer,
    )
    return {
        "outcome": "action_accepted", "descriptor": _DERIVE_DESCRIPTOR,
        "project_id": work.get("project_id"), "derivative": work,
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
    await _precheck_or_402(owner_user_id=envelope_user, job_id=_billing_job_id(token), estimate_usd=estimate)
    job_id = await _enqueue_motif_job(
        envelope_user=envelope_user, project_id=None, operation="analyze_reference",
        spec={
            "import_source_id": str(import_source_id),
            "use_web": payload.get("use_web"),
            "arc_hint": payload.get("arc_hint"),
            "language": payload.get("language") or "en",
            # BYOK deconstruct model rides through (provider-gateway invariant); the worker
            # fails closed if neither this nor the platform fallback resolves a ref.
            "model_ref": payload.get("model_ref"),
            "model_source": payload.get("model_source"),
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
    await _precheck_or_402(owner_user_id=envelope_user, job_id=_billing_job_id(token), estimate_usd=estimate)
    job_id = await _enqueue_motif_job(
        envelope_user=envelope_user, project_id=project_id, operation="conformance_run",
        spec={
            "book_id": str(work.book_id),
            "scope": payload.get("scope"),
            "chapter_id": payload.get("chapter_id"),
            # D-W10-ARC-CONFORMANCE-DEEP-JOB — the arc deep overlay's inputs (the tagging storm
            # the worker runs); the BYOK classify model rides through (provider-gateway invariant).
            # 23-A4/BA4: the arc axis is a structure_node (`arc_id`), not the template it came from.
            "arc_id": payload.get("arc_id"),
            "model_ref": payload.get("model_ref"),
            "model_source": payload.get("model_source"),
        },
    )
    return {
        "outcome": "action_accepted",
        "descriptor": _CONFORMANCE_RUN_DESCRIPTOR,
        "job_id": job_id,
        "poll": "composition_get_mine_job",
    }


# ══════════════════════════════════════════════════════════════════════════════
# D-AGENT-MODE §20 — authoring-run confirm effects (spec docs/specs/
# 2026-07-01-writing-studio/20_agent_mode.md, decisions D5/D6/D7). Book-scoped
# (no Work/project_id); the dispatch above already re-checked EDIT on the
# book_id at confirm time. No replay ledger (mirrors publish/generate — the
# service's own guarded OCC transitions make a re-confirm a clean no-op/409,
# not a double-effect).
# ══════════════════════════════════════════════════════════════════════════════


def _serialize_authoring_run(run: Any) -> dict[str, Any]:
    """Minimal MCP-facing run projection (mirrors routers/authoring_runs.py's
    `_serialize` field set; kept local so this module doesn't import a router's
    private helper)."""
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


async def _execute_authoring_run_create(
    payload: dict[str, Any], book_id: UUID, envelope_user: UUID,
) -> dict[str, Any]:
    """composition.authoring_run_create effect — create the run in `draft`.
    No chapters are drafted here (create is deliberately permissive — the
    start-gate at `gate()` is the real enforcement point); the confirm-gate is
    about the run holding the book's active-run slot + declaring a budget, per
    D6."""
    from decimal import Decimal, InvalidOperation

    from app.deps import get_authoring_run_service

    try:
        plan_run_id = UUID(str(payload["plan_run_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    scope = payload.get("scope") or []
    if not isinstance(scope, list) or not all(isinstance(s, str) for s in scope):
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    tool_allowlist = payload.get("tool_allowlist") or []
    if not isinstance(tool_allowlist, list):
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        budget_usd = Decimal(str(payload["budget_usd"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    try:
        level = int(payload.get("level", 3))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    if "pause_after_each_unit" not in payload:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    pause_after_each_unit = bool(payload["pause_after_each_unit"])
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    svc = await get_authoring_run_service()
    try:
        run = await svc.create(
            envelope_user, book_id,
            plan_run_id=plan_run_id, level=level, scope=scope,
            budget_usd=budget_usd, tool_allowlist=tool_allowlist,
            params=params, pause_after_each_unit=pause_after_each_unit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    return {
        "outcome": "action_done",
        "descriptor": _AUTHORING_RUN_CREATE_DESCRIPTOR,
        "run": _serialize_authoring_run(run),
    }


async def _execute_authoring_run_gate(
    payload: dict[str, Any], book_id: UUID, envelope_user: UUID, book: BookClient,
) -> dict[str, Any]:
    """composition.authoring_run_gate effect — the start-gate check (draft →
    gated). Headless (MCP has no caller JWT) — mint a service bearer for the
    envelope user to resolve the book's chapter-id set, same as the REST
    router's gate endpoint does with the caller's own bearer."""
    from app.services.authoring_run_service import (
        ActiveRunOverlapError,
        TransitionConflictError,
    )
    from app.deps import get_authoring_run_service

    try:
        run_id = UUID(str(payload["run_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    svc = await get_authoring_run_service()
    await _authoring_run_in_book(svc, run_id, book_id, envelope_user)
    bearer = mint_service_bearer(envelope_user, settings.jwt_secret)
    try:
        chapters = await book.list_chapters(book_id, bearer)
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail={"code": "action_error"}) from exc
    chapter_ids = {str(c["chapter_id"]) for c in chapters if c.get("chapter_id")}
    try:
        run = await svc.gate(run_id, book_chapter_ids=chapter_ids)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    except ActiveRunOverlapError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "action_error", "reason": "active_run_overlap"},
        ) from exc
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "action_error"}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"code": "action_error", "detail": str(exc)},
        ) from exc
    return {
        "outcome": "action_done",
        "descriptor": _AUTHORING_RUN_GATE_DESCRIPTOR,
        "run": _serialize_authoring_run(run),
    }


async def _authoring_run_in_book(
    svc: Any, run_id: UUID, book_id: UUID, envelope_user: UUID,
) -> Any:
    """Reconcile the confirm-gated book with the run's OWN book, then re-assert the
    creator rule (REST `_run_for_mutation` parity).

    The EDIT gate at the dispatch above proves only that the caller may edit the book
    they NAMED in the confirm payload — never that the run they named lives in it.
    Before the 25 re-key the service scoped every transition by the acting owner
    (`svc.start(envelope_user, run_id)`); de-scoping the repos moved that duty here
    (`worker-loaded-id-needs-parent-scoping`). Without it, an EDIT grant on ANY book
    lets a caller start/resume/gate an arbitrary run — spending its creator's BYOK
    budget — or `revert_all` it, destroying their drafted chapters.

    Book-owner escalation is pause/close ONLY (see the REST router); none of the
    confirm-gated descriptors are pause/close, so this fence is creator-only. Missing,
    foreign, and not-yours all raise the SAME `action_error` — no existence oracle.
    """
    run = await svc.get(run_id)
    if run is None or run.book_id != book_id or run.created_by != envelope_user:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    return run


async def _apply_pause_override(
    svc: Any, run_id: UUID, payload: dict[str, Any],
) -> None:
    """D4b: start/resume optionally OVERRIDE the run's pause_after_each_unit
    policy at the same time. `None`/absent = leave the run's existing policy
    untouched (set at create time). Callers MUST have fenced `run_id` against the
    gated book first (`_authoring_run_in_book`) — this itself writes to the run."""
    from app.services.authoring_run_service import TransitionConflictError

    override = payload.get("pause_after_each_unit")
    if override is None:
        return
    try:
        await svc.set_pause_policy(run_id, bool(override))
    except LookupError as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "action_error"}) from exc


async def _execute_authoring_run_start(
    payload: dict[str, Any], book_id: UUID, envelope_user: UUID,
) -> dict[str, Any]:
    """composition.authoring_run_start effect — gated → running (spawns the
    driver). Applies an explicit `pause_after_each_unit` override FIRST (D4b),
    then starts."""
    from app.services.authoring_run_service import TransitionConflictError
    from app.deps import get_authoring_run_service

    try:
        run_id = UUID(str(payload["run_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    svc = await get_authoring_run_service()
    await _authoring_run_in_book(svc, run_id, book_id, envelope_user)
    await _apply_pause_override(svc, run_id, payload)
    try:
        run = await svc.start(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "action_error"}) from exc
    return {
        "outcome": "action_done",
        "descriptor": _AUTHORING_RUN_START_DESCRIPTOR,
        "run": _serialize_authoring_run(run),
    }


async def _execute_authoring_run_resume(
    payload: dict[str, Any], book_id: UUID, envelope_user: UUID,
) -> dict[str, Any]:
    """composition.authoring_run_resume effect — paused → running (resumes the
    driver, spending more money — why resume is confirm-gated, per D6). Same
    optional pause-policy override as start (D4b)."""
    from app.services.authoring_run_service import TransitionConflictError
    from app.deps import get_authoring_run_service

    try:
        run_id = UUID(str(payload["run_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    svc = await get_authoring_run_service()
    await _authoring_run_in_book(svc, run_id, book_id, envelope_user)
    await _apply_pause_override(svc, run_id, payload)
    try:
        run = await svc.resume(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "action_error"}) from exc
    return {
        "outcome": "action_done",
        "descriptor": _AUTHORING_RUN_RESUME_DESCRIPTOR,
        "run": _serialize_authoring_run(run),
    }


async def _execute_authoring_run_revert_all(
    payload: dict[str, Any], book_id: UUID, envelope_user: UUID, book: BookClient,
) -> dict[str, Any]:
    """composition.authoring_run_revert_all effect — reject every drafted/
    accepted unit in reverse order, closing the run on full success (D9: the
    UI must render the partial-failure path, not just success — mirrored here
    by mapping a partial failure to a 502 with the same shape the REST route
    uses). Headless restore bearer (MCP path), mirrors the gate effect."""
    from app.services.authoring_run_service import TransitionConflictError
    from app.deps import get_authoring_run_service

    try:
        run_id = UUID(str(payload["run_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    svc = await get_authoring_run_service()
    await _authoring_run_in_book(svc, run_id, book_id, envelope_user)
    bearer = mint_service_bearer(envelope_user, settings.jwt_secret)

    async def _restore(bid: UUID, chapter_id: UUID, revision_id: UUID) -> None:
        await book.restore_revision(bid, chapter_id, revision_id, bearer)

    try:
        result = await svc.revert_all(run_id, restore=_restore)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "action_error"}) from exc
    if result["failed_unit_index"] is not None:
        raise HTTPException(
            status_code=502,
            detail={"code": "action_error", "reason": "revert_all_partial", **result},
        )
    return {
        "outcome": "action_done",
        "descriptor": _AUTHORING_RUN_REVERT_ALL_DESCRIPTOR,
        **result,
    }
