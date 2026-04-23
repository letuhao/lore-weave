"""K20.4 — Internal summary regeneration endpoint.

POST /internal/summarize

Service-to-service surface for triggering L0/L1 summary regeneration.
Called by:
  - the public-edge handler in `app/routers/public/summaries.py` (manual
    regen from the Global / Project memory tab), and
  - (future) the K20.3 scheduler job.

Authentication: X-Internal-Token. Trusts the caller's ``user_id`` — the
public edge passes the JWT-extracted user_id, and the scheduler supplies
its own.

**Module placement deviation** from the K20.4 plan row in
KNOWLEDGE_SERVICE_TRACK3_IMPLEMENTATION.md: the plan names
`app/api/internal/summarize.py`, but every existing internal router
lives under `app/routers/internal_*.py` (`internal_extraction.py`,
`internal_benchmark.py`). Keeping the convention avoids a one-file
directory split.

The HTTP envelope is **always** 200 with a `status` field carrying the
outcome — this module is the internal API and callers (FE, scheduler)
already branch on the status. The public edge handler does its own
HTTP mapping (200 vs 409 for user_edit_lock, etc.).
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.clients.provider_client import ProviderClient
from app.db.neo4j import neo4j_session
from app.db.pool import get_knowledge_pool
from app.db.repositories.summaries import SummariesRepo
from app.deps import get_provider_client, get_summaries_repo
from app.jobs.regenerate_summaries import (
    RegenTrigger,
    RegenerationResult,
    regenerate_global_summary,
    regenerate_project_summary,
)
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


class SummarizeRequest(BaseModel):
    user_id: UUID
    scope_type: Literal["global", "project"]
    scope_id: UUID | None = None
    model_source: Literal["user_model", "platform_model"] = "user_model"
    model_ref: str = Field(min_length=1, max_length=200)
    # C2 — callers that drive a scheduled regen (e.g. the K20.3
    # scheduler, if/when it routes through this endpoint instead of
    # calling the helpers directly) pass ``trigger="scheduled"`` so
    # the metric counter splits scheduled vs manual cleanly. Defaults
    # to ``"manual"`` to preserve back-compat for human-triggered
    # callers that pre-dated the label.
    trigger: RegenTrigger = "manual"

    @model_validator(mode="after")
    def _require_scope_id_for_project(self) -> "SummarizeRequest":
        if self.scope_type == "project" and self.scope_id is None:
            raise ValueError("scope_id is required when scope_type='project'")
        if self.scope_type == "global" and self.scope_id is not None:
            raise ValueError("scope_id must be omitted when scope_type='global'")
        return self


@router.post("/summarize", response_model=RegenerationResult)
async def summarize(
    req: SummarizeRequest,
    provider_client: ProviderClient = Depends(get_provider_client),
    summaries_repo: SummariesRepo = Depends(get_summaries_repo),
) -> RegenerationResult:
    """K20.4 — regenerate a summary for the given scope.

    Returns 200 in every non-error case; the ``status`` field carries
    the business outcome. The pool + Neo4j session factory come from
    module-level singletons and are not injected so the public-edge
    handler can override ``provider_client`` / ``summaries_repo`` for
    tests without rebuilding the full DI graph.
    """
    try:
        pool = get_knowledge_pool()
    except Exception as exc:
        logger.error("K20.4 summarize: knowledge pool unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="knowledge storage is unavailable",
        ) from exc

    if req.scope_type == "global":
        return await regenerate_global_summary(
            user_id=req.user_id,
            model_source=req.model_source,
            model_ref=req.model_ref,
            pool=pool,
            session_factory=neo4j_session,
            provider_client=provider_client,
            summaries_repo=summaries_repo,
            trigger=req.trigger,
        )
    assert req.scope_id is not None  # validator ensures this
    return await regenerate_project_summary(
        user_id=req.user_id,
        project_id=req.scope_id,
        model_source=req.model_source,
        model_ref=req.model_ref,
        pool=pool,
        session_factory=neo4j_session,
        provider_client=provider_client,
        summaries_repo=summaries_repo,
        trigger=req.trigger,
    )
