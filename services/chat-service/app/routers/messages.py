from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.client.billing_client import get_billing_client
from app.client.provider_client import get_provider_client
from app.deps import get_current_user, get_db
from app.models import ChatMessage, MessageListResponse, SendMessageRequest
from app.services.stream_service import stream_response

router = APIRouter(prefix="/v1/chat/sessions", tags=["messages"])


def _row_to_message(r: asyncpg.Record) -> ChatMessage:
    return ChatMessage(
        message_id=r["message_id"],
        session_id=r["session_id"],
        owner_user_id=r["owner_user_id"],
        role=r["role"],
        content=r["content"],
        content_parts=r["content_parts"],
        sequence_num=r["sequence_num"],
        input_tokens=r["input_tokens"],
        output_tokens=r["output_tokens"],
        model_ref=r["model_ref"],
        is_error=r["is_error"],
        error_detail=r["error_detail"],
        parent_message_id=r["parent_message_id"],
        created_at=r["created_at"],
    )


@router.get("/{session_id}/messages", response_model=MessageListResponse)
async def list_messages(
    session_id: UUID,
    limit: int = Query(50, le=200),
    before_seq: int | None = None,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> MessageListResponse:
    # Verify ownership
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    if before_seq is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_messages
            WHERE session_id=$1 AND sequence_num < $2
            ORDER BY sequence_num ASC
            LIMIT $3
            """,
            str(session_id), before_seq, limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_messages
            WHERE session_id=$1
            ORDER BY sequence_num ASC
            LIMIT $2
            """,
            str(session_id), limit,
        )
    return MessageListResponse(items=[_row_to_message(r) for r in rows])


@router.post("/{session_id}/messages")
async def send_message(
    session_id: UUID,
    body: SendMessageRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> StreamingResponse:
    # Verify session ownership and get model info
    session = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if session["status"] == "archived":
        raise HTTPException(status_code=409, detail="session is archived")

    model_source = session["model_source"]
    model_ref = str(session["model_ref"])

    # Edit flow: delete branched messages + insert replacement + update count — all atomic.
    # Non-edit flow: simple insert + increment.
    parent_message_id: str | None = None
    deleted_count = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            if body.edit_from_sequence is not None:
                parent_message_id = await conn.fetchval(
                    """
                    SELECT message_id::text FROM chat_messages
                    WHERE session_id=$1 AND sequence_num=$2
                    """,
                    str(session_id), body.edit_from_sequence,
                )
                # asyncpg execute returns "DELETE N" — parse count from status string
                result = await conn.execute(
                    """
                    DELETE FROM chat_messages
                    WHERE session_id=$1 AND sequence_num > $2
                    """,
                    str(session_id), body.edit_from_sequence,
                )
                deleted_count = int(result.split()[-1])

            seq = await conn.fetchval(
                "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages WHERE session_id=$1",
                str(session_id),
            )
            await conn.execute(
                """
                INSERT INTO chat_messages
                  (session_id, owner_user_id, role, content, sequence_num, parent_message_id)
                VALUES ($1,$2,'user',$3,$4,$5)
                """,
                str(session_id), user_id, body.content, seq, parent_message_id,
            )
            # deleted_count=0 on non-edit path → GREATEST(count - 0 + 1, 0) = count + 1
            await conn.execute(
                """
                UPDATE chat_sessions
                SET message_count = GREATEST(message_count - $2 + 1, 0), updated_at = now()
                WHERE session_id = $1
                """,
                str(session_id), deleted_count,
            )

    # Resolve credentials
    try:
        creds = await get_provider_client().resolve(model_source, model_ref, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"credential resolution failed: {exc}")

    billing = get_billing_client()

    headers = {
        "x-vercel-ai-ui-message-stream": "v1",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream_response(
            session_id=str(session_id),
            user_message_content=body.content,
            user_id=user_id,
            model_source=model_source,
            model_ref=model_ref,
            creds=creds,
            pool=pool,
            billing=billing,
            parent_message_id=parent_message_id,
        ),
        media_type="text/event-stream",
        headers=headers,
    )
