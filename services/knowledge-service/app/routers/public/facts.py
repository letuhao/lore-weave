"""S-05 — public fact-correction endpoint.

A user can mark a committed fact wrong (invalidate). This closes the asymmetry the
studio-completeness audit named: relations already had `/relations/{id}/invalidate`,
facts did not — even though `invalidate_fact` existed and the agent side
(`memory_forget`) already used it. This adds the HUMAN route only (CV-2: no new MCP
tool — agent parity already exists).

By design there is NO in-place fact UPDATE (bitemporal — correct = invalidate + the
`POST /entities/{id}/facts` re-assert), mirroring relations' invalidate-then-recreate.

Multi-tenant: `user_id` from the JWT is threaded into the Cypher; a cross-user /
missing fact collapses to 404 (KSA §6.4, no existence oracle). Each invalidate emits
a `knowledge.fact_corrected` event for the corrections log, matching the
relation-correction pattern so the audit trail stays uniform across target types.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.facts import Fact, get_fact, invalidate_fact
from app.events.outbox_emit import (
    FACT_CORRECTED,
    emit_correction,
    fact_correction_payload,
    fact_snapshot,
)
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

facts_router = APIRouter(
    prefix="/v1/knowledge",
    tags=["facts"],
    dependencies=[Depends(get_current_user)],
)


@facts_router.post("/facts/{fact_id}/invalidate", response_model=Fact)
async def invalidate_fact_endpoint(
    fact_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
) -> Fact:
    """User marks a fact wrong → soft-invalidate (set `valid_until`). Emits a
    `spurious-drop` correction (after=null). Idempotent — re-invalidating an
    already-invalidated fact is a no-op that still returns the fact.

    404 on cross-user / missing (the repo filters on `user_id`, so a fact that
    isn't the caller's returns None → 404, no existence oracle)."""
    async with neo4j_session() as session:
        before = await get_fact(session, user_id=str(user_id), fact_id=fact_id)
        invalidated = await invalidate_fact(
            session, user_id=str(user_id), fact_id=fact_id,
        )
    if invalidated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="fact not found"
        )
    await emit_correction(
        event_type=FACT_CORRECTED,
        aggregate_id=fact_id,
        payload=fact_correction_payload(
            user_id=str(user_id),
            project_id=invalidated.project_id,
            book_id=None,
            target_id=fact_id,
            op="invalidate",
            before=fact_snapshot(before),
            after=None,
            actor_id=str(user_id),
        ),
    )
    logger.info("user invalidated fact user_id=%s fact_id=%s", user_id, fact_id)
    return invalidated
