"""FD-2 — internal service-to-service endpoints (X-Internal-Token).

Exposes a chat turn's text so worker-ai can extract chat knowledge into the KG.
The `chat.turn_completed` outbox event carries only ids + content *lengths* (not
the prose), so the extraction worker must fetch the turn text by id from here.
"""

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.deps import get_db

router = APIRouter(prefix="/internal/chat", tags=["internal"])


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    """Guard internal endpoints with the shared service token (same contract the
    chat-service clients use for provider/billing internal calls)."""
    if not settings.internal_service_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(status_code=401, detail="invalid internal token")


class InternalCreateSession(BaseModel):
    """Create a chat session on behalf of a JWT-verified caller (roleplay-service
    start-orchestration). The OWNER is in the body because the caller already
    authenticated the user — the X-Internal-Token gates the trust boundary. The
    `working_memory_seed` is the frozen charter (+ optional rubric sidecar), the
    same shape `/templates/{id}/start` writes."""

    owner_user_id: UUID
    title: str
    model_source: str
    model_ref: UUID
    system_prompt: str | None = None
    working_memory_seed: dict | None = None


@router.post("/sessions", dependencies=[Depends(require_internal_token)], status_code=status.HTTP_201_CREATED)
async def internal_create_session(
    body: InternalCreateSession, db: asyncpg.Pool = Depends(get_db)
) -> dict:
    """Create a `chat_sessions` row carrying a `working_memory_seed`. The exact
    INSERT `/templates/{id}/start` uses — extracted so roleplay-service (the new
    goal authority) can own scripts while chat-service still owns the session +
    turn loop + M3 anchoring + M6 debrief."""
    row = await db.fetchrow(
        """
        INSERT INTO chat_sessions
          (owner_user_id, title, model_source, model_ref, system_prompt,
           project_id, working_memory_seed)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING session_id
        """,
        str(body.owner_user_id),
        body.title,
        body.model_source,
        str(body.model_ref),
        body.system_prompt,
        None,
        json.dumps(body.working_memory_seed) if body.working_memory_seed is not None else None,
    )
    return {"session_id": str(row["session_id"])}


@router.get("/turns/{message_id}/text", dependencies=[Depends(require_internal_token)])
async def get_turn_text(message_id: UUID, db: asyncpg.Pool = Depends(get_db)) -> dict:
    """Return the full turn text for an ASSISTANT `message_id` — the user question
    (the assistant message's parent) joined with the assistant answer, the
    meaningful unit for chat→KG extraction. `found=false` (+ empty text) when the
    message doesn't exist, so the caller can skip gracefully rather than retry."""
    row = await db.fetchrow(
        "SELECT role, content, parent_message_id FROM chat_messages WHERE message_id = $1",
        message_id,
    )
    if row is None:
        return {"found": False, "text": ""}
    parts: list[str] = []
    # The turn-completed event always carries the ASSISTANT message id (its
    # parent is the user question). Only walk to the parent for an assistant
    # message — guards against a caller passing a user-message id (whose parent
    # would be a *prior* assistant turn, which would wrongly prepend unrelated
    # text). A non-assistant message degrades to its own content only.
    parent_id = row["parent_message_id"] if row["role"] == "assistant" else None
    if parent_id is not None:
        parent = await db.fetchrow(
            "SELECT content FROM chat_messages WHERE message_id = $1", parent_id,
        )
        if parent and (parent["content"] or "").strip():
            parts.append(parent["content"].strip())
    if (row["content"] or "").strip():
        parts.append(row["content"].strip())
    return {"found": True, "text": "\n\n".join(parts)}
