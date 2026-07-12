"""K21-C (design D7) — public pending-facts review endpoints.

GET  /v1/knowledge/pending-facts?session_id=   — list the caller's
       pending `memory_remember` facts, optionally one chat session.
POST /v1/knowledge/pending-facts/{id}/confirm  — write the queued fact
       to the graph (merge_fact) then delete the pending row.
POST /v1/knowledge/pending-facts/{id}/reject   — delete the pending row.

A pending fact is created by the memory-tool executor when a project
has `memory_remember_confirm` on (design D4/D6): instead of writing the
`:Fact` straight to Neo4j, the executor queues it here for explicit
user confirmation. These endpoints are the FE's drain path.

Every route is JWT-authenticated via the router-level
`dependencies=[Depends(get_current_user)]` AND each route also takes
`user_id = Depends(get_current_user)` so it can pass the id to the
repo — the same intentional redundancy as `projects.py`.

Cross-user / missing collapses to 404 per KSA §6.4 — the repo filters
on `user_id`, so a cross-user lookup returns None / False which we map
to a uniform 404 (no oracle for whether a pending_fact_id exists).

The stored `fact_text` was injection-neutralized at queue time
(design D6 / REVIEW-DESIGN R1), so confirm writes it through to
`merge_fact` as-is — the confirm path cannot bypass the defense.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.models import PendingFact
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import merge_entity
from app.db.neo4j_repos.facts import Fact, days_since_epoch, merge_fact
from app.db.repositories.pending_facts import PendingFactsRepo
from app.deps import get_pending_facts_repo
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

# K21-C: confirmed facts inherit the same low confidence + distinguishing
# source_type as a directly-written memory_remember fact (executor's
# TOOL_FACT_CONFIDENCE / TOOL_FACT_SOURCE_TYPE). Re-declared here rather
# than imported to keep this public router free of an app.tools import;
# test_pending_facts_api pins the two to the same values.
_TOOL_FACT_CONFIDENCE = 0.7
_TOOL_FACT_SOURCE_TYPE = "llm_tool_call"

__all__ = ["router"]

router = APIRouter(
    prefix="/v1/knowledge/pending-facts",
    tags=["public"],
    dependencies=[Depends(get_current_user)],
)


def _not_found() -> HTTPException:
    """Uniform 404 — does not distinguish 'not yours' from 'not exist'."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="pending fact not found",
    )


@router.get("", response_model=list[PendingFact])
async def list_pending_facts(
    session_id: str | None = Query(
        default=None,
        description="Optional — restrict to one chat session. Omit for all.",
    ),
    user_id: UUID = Depends(get_current_user),
    repo: PendingFactsRepo = Depends(get_pending_facts_repo),
) -> list[PendingFact]:
    """List the caller's pending facts, oldest-first. JWT-scoped — the
    repo filters on `user_id`, so the result is always the caller's own
    queue."""
    return await repo.list_for_user(user_id, session_id=session_id)


@router.post("/{pending_fact_id}/confirm", response_model=Fact)
async def confirm_pending_fact(
    pending_fact_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: PendingFactsRepo = Depends(get_pending_facts_repo),
) -> Fact:
    """Confirm a pending fact: write it to the graph then drop the
    pending row. Returns the created `:Fact`.

    404 if the id is not the caller's (or does not exist). The stored
    `fact_text` is already injection-neutralized (design D6), so it is
    written through to `merge_fact` verbatim at the same low confidence
    + `source_type` a directly-written memory_remember fact uses.
    """
    pending = await repo.get(user_id, pending_fact_id)
    if pending is None:
        raise _not_found()

    async with neo4j_session() as session:
        fact = await _promote_pending_fact(session, user_id, pending)

    # Graph write succeeded — drop the queue row. A delete returning
    # False here would mean a concurrent confirm/reject already drained
    # it; the fact is written either way, so we don't fail the request.
    await repo.delete(user_id, pending_fact_id)
    return fact


# WS-2.4 — the diary subject is materialized as a plain :Entity so the :ABOUT edge exists. Most diary
# subjects are colleagues ("what did <colleague> say"); 'person' is the pragmatic default kind. The kind
# is only a KG label here (recall matches by canonical_name, not kind), so this doesn't touch the
# tenant-scoped codex kinds.
_DIARY_SUBJECT_KIND = "person"


async def _promote_pending_fact(session, user_id: UUID, pending: PendingFact) -> Fact:
    """Write a confirmed pending fact to the graph. A WS-2.2 STRUCTURED diary fact (has a subject +
    event_date) takes the WS-2.4 temporal path: its subject becomes an :Entity, the fact gets an :ABOUT
    edge to it + a NOT-NULL valid_from_ordinal = days_since_epoch(event_date) + event_date_iso, so the
    date-filtered recall read can find it. maintain_chain is NEVER set on this path — the diary key is
    (subject, fact_type) and chain maintenance would blind-close unrelated decisions (spec 07 §Q2).
    A coarse fact (no subject) takes the legacy single-MERGE path unchanged."""
    project_id = str(pending.project_id) if pending.project_id else None

    subject_id: str | None = None
    valid_from_ordinal: int | None = None
    event_date_iso: str | None = None
    if pending.subject and pending.project_id and pending.event_date is not None:
        entity = await merge_entity(
            session,
            user_id=str(user_id),
            project_id=project_id,
            name=pending.subject,
            kind=_DIARY_SUBJECT_KIND,
            source_type=_TOOL_FACT_SOURCE_TYPE,
            confidence=_TOOL_FACT_CONFIDENCE,
            auto_created=True,
            # The diary is the user's own words → the recognized 'human_authored' provenance (NOT an
            # invented 'user_authored', which no downstream provenance filter would recognize).
            provenance="human_authored",
        )
        subject_id = entity.id
        valid_from_ordinal = days_since_epoch(pending.event_date)
        event_date_iso = pending.event_date.isoformat()

    return await merge_fact(
        session,
        user_id=str(user_id),
        project_id=project_id,
        type=pending.fact_type,
        content=pending.fact_text,
        confidence=_TOOL_FACT_CONFIDENCE,
        pending_validation=False,
        source_type=_TOOL_FACT_SOURCE_TYPE,
        subject_id=subject_id,
        valid_from_ordinal=valid_from_ordinal,
        event_date_iso=event_date_iso,
        maintain_chain=False,  # diary path never drives the (subject, type) chain (spec 07 §Q2)
    )


@router.post(
    "/{pending_fact_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reject_pending_fact(
    pending_fact_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: PendingFactsRepo = Depends(get_pending_facts_repo),
) -> None:
    """Reject a pending fact: delete the queue row, write nothing.

    404 if the id is not the caller's (or does not exist)."""
    deleted = await repo.delete(user_id, pending_fact_id)
    if not deleted:
        raise _not_found()
