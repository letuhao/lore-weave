"""Phase B sub-session C — public relation-correction endpoints.

A user can mark a relation wrong (invalidate) or fix it (invalidate the old
edge + recreate the corrected one). Each emits a `knowledge.relation_corrected`
event for the learning-service corrections log.

Multi-tenant: `user_id` from JWT is threaded into the Cypher; cross-user /
missing collapses to 404 (KSA §6.4).

Relation identity is deterministic on `(user, subject, predicate, object)`, so
a predicate/endpoint fix is structurally a NEW edge — modelled as
invalidate-old + recreate-new (the recreate uses the dedicated
`recreate_relation`, which resurrects `valid_until` without the extraction path
ever being able to, F5).
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.relations import (
    Relation,
    get_relation,
    invalidate_relation,
    recreate_relation,
)
from app.events.outbox_emit import (
    RELATION_CORRECTED,
    emit_correction,
    relation_correction_payload,
    relation_snapshot,
)
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

relations_router = APIRouter(
    prefix="/v1/knowledge",
    tags=["relations"],
    dependencies=[Depends(get_current_user)],
)


@relations_router.get("/relations/{relation_id}", response_model=Relation)
async def get_relation_endpoint(
    relation_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
) -> Relation:
    """Fetch a single relation by id (for the FE correction dialog). 404 on
    cross-user / missing."""
    async with neo4j_session() as session:
        rel = await get_relation(session, user_id=str(user_id), relation_id=relation_id)
    if rel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="relation not found")
    return rel


@relations_router.post("/relations/{relation_id}/invalidate", response_model=Relation)
async def invalidate_relation_endpoint(
    relation_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
) -> Relation:
    """User marks a relation wrong → soft-invalidate (set valid_until). Emits a
    `spurious-drop` correction (after=null). Idempotent."""
    async with neo4j_session() as session:
        before = await get_relation(session, user_id=str(user_id), relation_id=relation_id)
        invalidated = await invalidate_relation(
            session, user_id=str(user_id), relation_id=relation_id,
        )
    if invalidated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="relation not found")
    await emit_correction(
        event_type=RELATION_CORRECTED,
        aggregate_id=relation_id,
        payload=relation_correction_payload(
            user_id=str(user_id),
            project_id=None,
            book_id=None,
            target_id=relation_id,
            op="invalidate",
            before=relation_snapshot(before),
            after=None,
            source_chapter=getattr(before, "source_chapter", None),
            actor_id=str(user_id),
        ),
    )
    logger.info("user invalidated relation user_id=%s relation_id=%s", user_id, relation_id)
    return invalidated


class RelationCorrectRequest(BaseModel):
    """Correct a relation: invalidate `old_relation_id` and (re)create the
    edge described by `(subject_id, predicate, object_id)`."""

    old_relation_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=100)
    object_id: str = Field(min_length=1, max_length=200)


@relations_router.post("/relations/correct", response_model=Relation)
async def correct_relation_endpoint(
    body: RelationCorrectRequest,
    user_id: UUID = Depends(get_current_user),
) -> Relation:
    """Fix a relation: invalidate the old edge, recreate the corrected one
    (resurrecting `valid_until` if that tuple was previously invalidated, F5).
    Emits a `predicate-fix` correction. `after` is read POST-write so it
    reflects the live (resurrected) edge, not the request payload."""
    async with neo4j_session() as session:
        before = await get_relation(
            session, user_id=str(user_id), relation_id=body.old_relation_id,
        )
        if before is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="relation not found"
            )
        # Recreate the corrected edge FIRST. If an endpoint entity is missing
        # we 409 and leave the OLD edge intact — never a half-applied state
        # (old-invalidated-but-no-replacement). Only invalidate once the
        # replacement exists.
        new_rel = await recreate_relation(
            session,
            user_id=str(user_id),
            subject_id=body.subject_id,
            predicate=body.predicate,
            object_id=body.object_id,
        )
        if new_rel is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subject or object entity not found for this user",
            )
        # Replacement exists → now retire the old edge (unless the correction
        # is a no-op that maps onto the same id, in which case skip — recreate
        # already revived it).
        if new_rel.id != body.old_relation_id:
            await invalidate_relation(
                session, user_id=str(user_id), relation_id=body.old_relation_id,
            )
        # Re-read so `after` reflects the live edge (F3 — not the request).
        after = await get_relation(
            session, user_id=str(user_id), relation_id=new_rel.id,
        )
    await emit_correction(
        event_type=RELATION_CORRECTED,
        aggregate_id=new_rel.id,
        payload=relation_correction_payload(
            user_id=str(user_id),
            project_id=None,
            book_id=None,
            target_id=new_rel.id,
            op="predicate_fix",
            before=relation_snapshot(before),
            after=relation_snapshot(after),
            source_chapter=None,
            actor_id=str(user_id),
        ),
    )
    logger.info(
        "user corrected relation user_id=%s old=%s new=%s",
        user_id, body.old_relation_id, new_rel.id,
    )
    return after if after is not None else new_rel
