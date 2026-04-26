"""K7.3 — Summaries endpoints under /v1/knowledge/.

Three routes:
  - GET   /v1/knowledge/summaries                       → list user's summaries
  - PATCH /v1/knowledge/summaries/global                → upsert L0 (global bio)
  - PATCH /v1/knowledge/projects/{project_id}/summary   → upsert L1 (project)

Empty content is allowed and persisted as an empty row — does NOT
delete. K7d owns user-data deletion; K7c owns content edits only.

Cross-user / nonexistent project_id on the project-summary PATCH
collapses to 404 per KSA §6.4 (don't leak existence). Because
knowledge_summaries has no FK to knowledge_projects, we explicitly
ownership-check the project via ProjectsRepo.get before upserting —
otherwise an attacker could plant orphan summary rows under a
project_id they don't own.
"""

import asyncio
import logging
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from typing import Literal

from app.clients.llm_client import LLMClient
from app.clients.provider_client import ProviderClient, ProviderError
from app.config import settings
from app.db.models import Summary, SummaryContent, SummaryVersion
from app.db.neo4j import neo4j_session
from app.db.pool import get_knowledge_pool
from app.db.repositories import VersionMismatchError
from app.db.repositories.summaries import SummariesRepo
from app.db.repositories.summary_spending import SummarySpendingRepo
from app.deps import (
    get_llm_client,
    get_provider_client,
    get_summaries_repo,
    get_summary_spending_repo,
)
from app.jobs.regenerate_summaries import (
    RegenerationResult,
    regenerate_global_summary,
    regenerate_project_summary,
)
from app.middleware.jwt_auth import get_current_user
from app.routers.public.projects import _etag, _parse_if_match

__all__ = ["router", "close_cooldown_client", "get_cooldown_client"]

logger = logging.getLogger(__name__)


# ── C2 — regen cooldown (D-K20α-02) ──────────────────────────────────────
#
# Redis SETNX guard on the two public regen endpoints. Prevents a
# user from firing regen back-to-back and burning BYOK tokens or
# hammering the LLM provider. Key includes `scope_id` so the cooldown
# is per-target (a user on cooldown for project A can still regen
# project B), matching the "rate-limit the expensive operation, not
# the user" heuristic.
#
# The cooldown is armed at CHECK time (pre-regen). If the regen
# itself fails (ProviderError, guardrail reject, concurrent-edit),
# the cooldown STAYS ARMED — rate-limit spam regardless of outcome.
# This is intentional: a mis-configured BYOK model would otherwise
# let a user retry every 100ms and still log "regen_cooldown"
# never-fires.
#
# Fallback: if `settings.redis_url` is empty OR the Redis call
# raises, the check is skipped (availability > abuse protection for
# a hobby-scale Track 1 deploy). Log + continue.

_REGEN_COOLDOWN_TTL_S = 60
_cooldown_client: aioredis.Redis | None = None
_cooldown_client_lock = asyncio.Lock()


async def _get_cooldown_client_singleton() -> aioredis.Redis | None:
    """Lazy, process-global Redis client for the cooldown SETNX guard.

    Returns None when Redis isn't configured so callers degrade to
    no-cooldown rather than 503. Double-checked locking keeps
    concurrent first-requests from racing to open two connections.
    """
    global _cooldown_client
    if not settings.redis_url:
        return None
    if _cooldown_client is None:
        async with _cooldown_client_lock:
            if _cooldown_client is None:
                _cooldown_client = aioredis.from_url(
                    settings.redis_url, decode_responses=True
                )
    return _cooldown_client


async def get_cooldown_client() -> aioredis.Redis | None:
    """FastAPI ``Depends`` factory. Tests override via
    ``app.dependency_overrides[get_cooldown_client] = lambda: fake``.
    """
    return await _get_cooldown_client_singleton()


async def close_cooldown_client() -> None:
    """Lifespan teardown hook. Idempotent — safe to call when the
    singleton was never initialised (redis_url empty or the module
    was imported but no regen ever ran)."""
    global _cooldown_client
    client = _cooldown_client
    _cooldown_client = None
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            logger.warning(
                "regen cooldown: error closing Redis client (non-fatal)",
                exc_info=True,
            )


def _cooldown_key(
    user_id: UUID,
    scope_type: Literal["global", "project"],
    scope_id: UUID | None,
) -> str:
    # "-" suffix for global keeps a stable separator when scope_id is
    # absent so the key parser can always split on ":" and get 4
    # segments — avoids the ambiguity of "{user}:global" (3 segments)
    # vs "{user}:project:{id}" (4 segments).
    return f"knowledge:regen:cooldown:{user_id}:{scope_type}:{scope_id or '-'}"


async def _release_regen_cooldown(
    client: aioredis.Redis | None,
    user_id: UUID,
    scope_type: Literal["global", "project"],
    scope_id: UUID | None,
) -> None:
    """Best-effort cooldown release. Called when regen raises an
    exception (ProviderError, Neo4j down, pool exhausted, any unhandled
    error) so a user isn't rate-limited for a SERVER-side fault or a
    BYOK config they need to fix + retry.

    **Not called** on business outcomes that reach ``_regen_http_envelope``
    (``regenerated``, ``no_op_similarity``, ``no_op_empty_source``,
    ``user_edit_lock``, ``regen_concurrent_edit``, ``no_op_guardrail``)
    — those represent a completed regen attempt and the cooldown should
    stay armed to rate-limit further attempts.

    Redis errors swallowed: the cooldown is best-effort; a failure to
    release just means the user waits 60s instead of being able to
    retry immediately. Preferable to raising over a release error.
    """
    if client is None:
        return
    key = _cooldown_key(user_id, scope_type, scope_id)
    try:
        await client.delete(key)
    except Exception:
        logger.warning(
            "regen cooldown: Redis DELETE errored on release — user "
            "will wait the full %ds window instead",
            _REGEN_COOLDOWN_TTL_S,
            exc_info=True,
        )


async def _check_regen_cooldown(
    client: aioredis.Redis | None,
    user_id: UUID,
    scope_type: Literal["global", "project"],
    scope_id: UUID | None,
) -> None:
    """Raise 429 + Retry-After if this (user, scope) regen'd in the
    last ``_REGEN_COOLDOWN_TTL_S`` seconds. No-op when Redis is
    unavailable or the SET command raises.
    """
    if client is None:
        return
    key = _cooldown_key(user_id, scope_type, scope_id)
    try:
        set_ok = await client.set(key, "1", nx=True, ex=_REGEN_COOLDOWN_TTL_S)
    except Exception:
        logger.warning(
            "regen cooldown: Redis SET errored — degrading to no-cooldown",
            exc_info=True,
        )
        return
    if set_ok:
        return  # first regen in the window — cooldown now armed
    try:
        remaining = await client.ttl(key)
    except Exception:
        # Best-effort Retry-After. A rare Redis hiccup on TTL read
        # shouldn't block the 429 — the caller just sees the full
        # budget instead of the exact remainder.
        remaining = _REGEN_COOLDOWN_TTL_S
    # Redis TTL semantics: -2 = key missing, -1 = no expiry, >=0 = secs.
    # The key was just observed present via SETNX=False, so -2 is a
    # race (expired between SET and TTL); -1 can't happen since our
    # SET always carries EX. Defensive floor at 1 so Retry-After is
    # never 0 (RFC 7231 §7.1.3 says non-negative integer).
    retry_after = max(int(remaining) if remaining and remaining > 0 else 1, 1)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error_code": "regen_cooldown",
            "message": (
                "Regeneration is on cooldown. Retry after the "
                "window elapses."
            ),
        },
        headers={"Retry-After": str(retry_after)},
    )

router = APIRouter(
    prefix="/v1/knowledge",
    tags=["public"],
    dependencies=[Depends(get_current_user)],
)


# ── request / response models ─────────────────────────────────────────────


class SummaryUpdate(BaseModel):
    # SummaryContent is Annotated[str, max_length=50000]. Empty string
    # is intentionally allowed — see module docstring.
    content: SummaryContent


class SummariesListResponse(BaseModel):
    # `global` is a Python keyword; alias lets the JSON field be
    # `global` while the attribute is `global_`. populate_by_name
    # lets test code construct via either spelling.
    model_config = ConfigDict(populate_by_name=True)

    global_: Summary | None = Field(default=None, alias="global")
    projects: list[Summary] = Field(default_factory=list)


class SummaryVersionListResponse(BaseModel):
    # D-K8-01: history panel response. `items` is capped by the
    # repo's VERSIONS_LIST_HARD_CAP so the panel can trust it will
    # never get overwhelmed.
    items: list[SummaryVersion] = Field(default_factory=list)


class RegenerateRequest(BaseModel):
    # K20.4 public edge body. user_id is NOT taken from the body —
    # the JWT dep supplies it so a caller cannot spoof another user.
    model_source: Literal["user_model", "platform_model"] = "user_model"
    model_ref: str = Field(min_length=1, max_length=200)


class RegenerateResponse(BaseModel):
    """Envelope returned on 200 (regenerated / similarity no-op /
    empty-source). FE inspects `status` to decide how to refresh the
    bio field. Edit-lock and concurrent-edit map to 409; guardrail
    failure maps to 422 — those paths use FastAPI's `HTTPException`
    envelope instead."""

    status: Literal["regenerated", "no_op_similarity", "no_op_empty_source"]
    summary: Summary | None = None
    skipped_reason: str | None = None


# ── helpers ───────────────────────────────────────────────────────────────


def _check_violation(exc: asyncpg.CheckViolationError) -> HTTPException:
    """DB CHECK constraint hit — Pydantic should have caught it first,
    but defense-in-depth: surface as 422 not 500."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"value out of bounds: {exc.constraint_name}",
    )


# ── endpoints ─────────────────────────────────────────────────────────────


@router.get("/summaries", response_model=SummariesListResponse)
async def list_summaries(
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> SummariesListResponse:
    rows = await repo.list_for_user(user_id)
    global_row: Summary | None = None
    projects: list[Summary] = []
    for row in rows:
        if row.scope_type == "global":
            # Schema invariant: at most one global row per user
            # (UNIQUE on (user_id, scope_type, scope_id) with
            # scope_id IS NULL). Defensive: keep the first.
            if global_row is None:
                global_row = row
        elif row.scope_type == "project":
            projects.append(row)
        # session/entity scopes are Track 2 — silently skipped.
    return SummariesListResponse(global_=global_row, projects=projects)


def _version_mismatch_response(current: Summary) -> JSONResponse:
    """412 envelope for a Summary version conflict. Body is the current
    row so the client can refresh its baseline in one round-trip."""
    return JSONResponse(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        content=current.model_dump(mode="json", by_alias=True),
        headers={"ETag": _etag(current.version)},
    )


@router.patch("/summaries/global", response_model=Summary)
async def update_global_summary(
    body: SummaryUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> Summary:
    # D-K8-03: strict If-Match. The FIRST save (no prior row) is
    # allowed without a version check — INSERT path always succeeds
    # and there's nothing to race against. Subsequent saves MUST
    # send a version. The FE reads summary.version from the GET
    # /v1/knowledge/summaries list body and derives the ETag.
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        # Allow only when there's no prior row (first-save case).
        existing = await repo.get(user_id, "global", None)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail=(
                    "If-Match header required — read summary.version from "
                    "GET /v1/knowledge/summaries and send it back"
                ),
            )
    try:
        result = await repo.upsert(
            user_id, "global", None, body.content, expected_version=expected_version
        )
    except VersionMismatchError as exc:
        assert isinstance(exc.current, Summary)
        return _version_mismatch_response(exc.current)
    except asyncpg.CheckViolationError as exc:
        raise _check_violation(exc)
    response.headers["ETag"] = _etag(result.version)
    return result


@router.patch(
    "/projects/{project_id}/summary",
    response_model=Summary,
)
async def update_project_summary(
    project_id: UUID,
    body: SummaryUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> Summary:
    # Ownership + upsert in a single CTE — atomic, no TOCTOU window,
    # one pool acquisition. Returns None if the user does not own the
    # project (cross-user OR nonexistent), which we collapse to 404
    # per KSA §6.4 don't-leak-existence rule.

    # D-K8-03: same strict-If-Match contract as the global route.
    # First-save is allowed unconditionally; subsequent saves must
    # carry a version.
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        existing = await repo.get(user_id, "project", project_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail=(
                    "If-Match header required — read summary.version from "
                    "GET /v1/knowledge/summaries and send it back"
                ),
            )
    try:
        result = await repo.upsert_project_scoped(
            user_id, project_id, body.content, expected_version=expected_version
        )
    except VersionMismatchError as exc:
        assert isinstance(exc.current, Summary)
        return _version_mismatch_response(exc.current)
    except asyncpg.CheckViolationError as exc:
        raise _check_violation(exc)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    response.headers["ETag"] = _etag(result.version)
    return result


# ── D-K8-01: global summary version history ──────────────────────────────
#
# Only the global scope gets history endpoints in Track 1. The repo
# layer already supports per-project history (same schema, same
# code path), so Track 2 can add matching endpoints without a
# schema migration.


@router.get(
    "/summaries/global/versions",
    response_model=SummaryVersionListResponse,
)
async def list_global_summary_versions(
    limit: int = 50,
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> SummaryVersionListResponse:
    items = await repo.list_versions(user_id, "global", None, limit=limit)
    return SummaryVersionListResponse(items=items)


@router.get(
    "/summaries/global/versions/{version}",
    response_model=SummaryVersion,
)
async def get_global_summary_version(
    version: int,
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> SummaryVersion:
    row = await repo.get_version(user_id, "global", None, version)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="version not found",
        )
    return row


@router.post(
    "/summaries/global/versions/{version}/rollback",
    response_model=Summary,
)
async def rollback_global_summary(
    version: int,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> Summary:
    # D-K8-01 + D-K8-03 cross-reference: rollback is a mutating
    # operation so it honours the same If-Match contract as PATCH.
    # A stale History panel can't accidentally roll forward over a
    # concurrent edit.
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=(
                "If-Match header required — read summary.version from "
                "GET /v1/knowledge/summaries and send it back"
            ),
        )
    try:
        result = await repo.rollback_to(
            user_id,
            "global",
            None,
            target_version=version,
            expected_version=expected_version,
        )
    except VersionMismatchError as exc:
        assert isinstance(exc.current, Summary)
        return _version_mismatch_response(exc.current)
    except LookupError as exc:
        # Repo raises with tag "summary_not_found" or
        # "target_version_not_found" — both collapse to 404 at the
        # router so we don't leak which one it was.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "not found",
        )
    response.headers["ETag"] = _etag(result.version)
    return result


# ── K20α — regeneration endpoints ────────────────────────────────────────


def _regen_http_envelope(result: RegenerationResult) -> RegenerateResponse:
    """Map the regen business outcome onto the right HTTP envelope.

    - ``regenerated`` / ``no_op_similarity`` / ``no_op_empty_source``
      → 200 with ``RegenerateResponse`` payload (FE inspects ``status``).
    - ``user_edit_lock`` / ``regen_concurrent_edit`` → 409.
    - ``no_op_guardrail`` → 422.
    """
    if result.status == "user_edit_lock":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "user_edit_lock",
                "message": result.skipped_reason
                or "Summary is protected by a recent manual edit.",
            },
        )
    if result.status == "regen_concurrent_edit":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "regen_concurrent_edit",
                "message": result.skipped_reason
                or "A concurrent manual edit raced this regeneration.",
            },
        )
    if result.status == "no_op_guardrail":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error_code": "regen_guardrail_failed",
                "message": result.skipped_reason
                or "Regenerated content failed a quality guardrail.",
            },
        )
    # status ∈ {regenerated, no_op_similarity, no_op_empty_source}.
    return RegenerateResponse(
        status=result.status,
        summary=result.summary,
        skipped_reason=result.skipped_reason,
    )


@router.post(
    "/me/summary/regenerate",
    response_model=RegenerateResponse,
)
async def regenerate_global_bio(
    body: RegenerateRequest,
    user_id: UUID = Depends(get_current_user),
    provider_client: ProviderClient = Depends(get_provider_client),
    llm_client: LLMClient = Depends(get_llm_client),
    repo: SummariesRepo = Depends(get_summaries_repo),
    spending_repo: SummarySpendingRepo = Depends(get_summary_spending_repo),
    cooldown: aioredis.Redis | None = Depends(get_cooldown_client),
) -> RegenerateResponse:
    """K20α — regenerate the caller's L0 global bio from raw chat turns.

    JWT-scoped — the body never carries user_id. Response mapping:
    see `_regen_http_envelope`. C2 cooldown: 60s SETNX guard armed at
    check time; subsequent calls within the window → 429.

    C16-BUILD: ``spending_repo`` enables the D-K20α-01 budget pre-check
    + post-success spend recorder. Without it, manual regen would
    bypass the cap entirely.
    """
    await _check_regen_cooldown(cooldown, user_id, "global", None)
    try:
        result = await regenerate_global_summary(
            user_id=user_id,
            model_source=body.model_source,
            model_ref=body.model_ref,
            pool=get_knowledge_pool(),
            session_factory=neo4j_session,
            provider_client=provider_client,
            llm_client=llm_client,
            summaries_repo=repo,
            summary_spending_repo=spending_repo,
            trigger="manual",
        )
    except ProviderError as exc:
        # BYOK-layer error — user needs to fix config + retry. Release
        # cooldown so they don't wait 60s on top of having a broken
        # provider. Surface as 502 so the FE can tell the user their
        # own provider returned an error rather than a bug here.
        await _release_regen_cooldown(cooldown, user_id, "global", None)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "provider_error",
                "message": str(exc),
            },
        ) from exc
    except Exception:
        # Server-side fault (Neo4j down, pool exhausted, etc.). Let
        # FastAPI's default 500 handler surface the error, but release
        # the cooldown first so a legit retry after ops restores
        # service isn't blocked by the 60s window.
        await _release_regen_cooldown(cooldown, user_id, "global", None)
        raise
    return _regen_http_envelope(result)


@router.post(
    "/projects/{project_id}/summary/regenerate",
    response_model=RegenerateResponse,
)
async def regenerate_project_bio(
    project_id: UUID,
    body: RegenerateRequest,
    user_id: UUID = Depends(get_current_user),
    provider_client: ProviderClient = Depends(get_provider_client),
    llm_client: LLMClient = Depends(get_llm_client),
    repo: SummariesRepo = Depends(get_summaries_repo),
    spending_repo: SummarySpendingRepo = Depends(get_summary_spending_repo),
    cooldown: aioredis.Redis | None = Depends(get_cooldown_client),
) -> RegenerateResponse:
    """K20α — regenerate an L1 project summary.

    Ownership is enforced inside `regenerate_project_summary` via the
    `upsert_project_scoped` CTE — cross-user scope_id collapses to
    `no_op_guardrail` (422) rather than leaking existence as 404, per
    KSA §6.4 anti-leak rules. C2 cooldown: keyed on project_id so a
    user on cooldown for one project can still regen a sibling.

    C16-BUILD: ``spending_repo`` ungates the budget pre-check; project
    spend itself records via the existing K16.11 path.
    """
    await _check_regen_cooldown(cooldown, user_id, "project", project_id)
    try:
        result = await regenerate_project_summary(
            user_id=user_id,
            project_id=project_id,
            model_source=body.model_source,
            model_ref=body.model_ref,
            pool=get_knowledge_pool(),
            session_factory=neo4j_session,
            provider_client=provider_client,
            llm_client=llm_client,
            summaries_repo=repo,
            summary_spending_repo=spending_repo,
            trigger="manual",
        )
    except ProviderError as exc:
        await _release_regen_cooldown(cooldown, user_id, "project", project_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "provider_error",
                "message": str(exc),
            },
        ) from exc
    except Exception:
        await _release_regen_cooldown(cooldown, user_id, "project", project_id)
        raise
    return _regen_http_envelope(result)
