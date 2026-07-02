"""Chat-turn feedback endpoint (track phase Q3 — Production Eval Flywheel).

``POST /v1/chat/messages/{message_id}/feedback`` captures explicit thumbs (+1/-1)
and implicit regenerate-as-negative on a chat turn. The feedback row + an outbox
event are written transactionally; the existing relay ships the event to
``loreweave:events:chat`` -> learning-service, which records a quality_score.

Owner-scoped: the message must belong to the caller (via owner_user_id).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user, get_db
from app.models import MessageFeedbackRequest, MessageFeedbackResponse

router = APIRouter(prefix="/v1/chat/messages", tags=["feedback"])

_VALID_RATINGS = (1, -1)


@router.post(
    "/{message_id}/feedback",
    response_model=MessageFeedbackResponse,
    status_code=201,
)
async def submit_feedback(
    message_id: UUID,
    body: MessageFeedbackRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> MessageFeedbackResponse:
    if body.rating not in _VALID_RATINGS:
        raise HTTPException(status_code=422, detail="rating must be +1 or -1")
    owner = UUID(user_id)

    async with pool.acquire() as conn:
        # P3b (Track 4): join the session's project_id + carry the message's
        # created_at so knowledge-service can attribute the thumbs to the
        # entities surfaced for THAT turn (time-window + session scoped).
        # Additive payload keys — consumers that ignore them are unaffected.
        msg = await conn.fetchrow(
            """
            SELECT m.session_id, m.created_at, s.project_id
            FROM chat_messages m
            JOIN chat_sessions s ON s.session_id = m.session_id
            WHERE m.message_id = $1 AND m.owner_user_id = $2
            """,
            message_id, owner,
        )
        if msg is None:
            raise HTTPException(status_code=404, detail="message not found")
        session_id = msg["session_id"]

        # feedback row + outbox event are atomic (the event must not ship
        # without the row, nor vice-versa).
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO message_feedback
                  (message_id, session_id, user_id, rating, reason,
                   regenerated_from_message_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, created_at
                """,
                message_id, session_id, owner, body.rating, body.reason,
                body.regenerated_from_message_id,
            )
            payload = {
                "user_id": str(owner),
                "session_id": str(session_id),
                "message_id": str(message_id),
                "rating": body.rating,
                "reason": body.reason,
                "regenerated_from_message_id": (
                    str(body.regenerated_from_message_id)
                    if body.regenerated_from_message_id
                    else None
                ),
                "feedback_id": str(row["id"]),
                # P3b — entity-attribution keys (additive): knowledge-service scopes
                # the salience boost by (user, project, session) + the turn's time.
                "project_id": str(msg["project_id"]) if msg["project_id"] else None,
                "message_created_at": msg["created_at"].isoformat(),
            }
            await conn.execute(
                """
                INSERT INTO outbox_events
                  (event_type, aggregate_type, aggregate_id, payload)
                VALUES ('chat.message_feedback', 'chat', $1, $2::jsonb)
                """,
                message_id, json.dumps(payload),
            )

    return MessageFeedbackResponse(
        id=str(row["id"]),
        message_id=str(message_id),
        rating=body.rating,
        created_at=row["created_at"],
    )
