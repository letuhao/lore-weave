import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_current_user, get_db
from app.models import (
    ChatSession,
    CreateSessionRequest,
    PatchSessionRequest,
    SearchResponse,
    SearchResult,
    SessionListResponse,
)

router = APIRouter(prefix="/v1/chat/sessions", tags=["sessions"])


def _row_to_session(r: asyncpg.Record) -> ChatSession:
    gp = r["generation_params"]
    if isinstance(gp, str):
        gp = json.loads(gp)
    return ChatSession(
        session_id=r["session_id"],
        owner_user_id=r["owner_user_id"],
        title=r["title"],
        model_source=r["model_source"],
        model_ref=r["model_ref"],
        system_prompt=r["system_prompt"],
        generation_params=gp if gp else {},
        is_pinned=r["is_pinned"],
        status=r["status"],
        message_count=r["message_count"],
        last_message_at=r["last_message_at"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ChatSession)
async def create_session(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    gp = json.dumps(body.generation_params.model_dump(exclude_none=True)) if body.generation_params else "{}"
    row = await pool.fetchrow(
        """
        INSERT INTO chat_sessions (owner_user_id, title, model_source, model_ref, system_prompt, generation_params)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        RETURNING *
        """,
        user_id, body.title, body.model_source, str(body.model_ref), body.system_prompt, gp,
    )
    return _row_to_session(row)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    session_status: str = Query("active", alias="status"),
    limit: int = Query(50, le=100),
    cursor: str | None = None,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> SessionListResponse:
    args: list = [user_id, session_status, limit + 1]
    if cursor:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_sessions
            WHERE owner_user_id=$1 AND status=$2 AND last_message_at < $4
            ORDER BY is_pinned DESC, last_message_at DESC NULLS LAST, session_id DESC
            LIMIT $3
            """,
            *args, cursor,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_sessions
            WHERE owner_user_id=$1 AND status=$2
            ORDER BY is_pinned DESC, last_message_at DESC NULLS LAST, session_id DESC
            LIMIT $3
            """,
            *args,
        )
    has_more = len(rows) > limit
    items = [_row_to_session(r) for r in rows[:limit]]
    next_cursor = str(items[-1].last_message_at) if has_more and items else None
    return SessionListResponse(items=items, next_cursor=next_cursor)


@router.get("/search", response_model=SearchResponse)
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, le=50),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> SearchResponse:
    rows = await pool.fetch(
        """
        SELECT m.session_id, s.title AS session_title,
               m.message_id, m.role,
               ts_headline('english', m.content, plainto_tsquery('english', $2),
                 'StartSel=**, StopSel=**, MaxWords=40, MinWords=20') AS snippet,
               m.created_at
        FROM chat_messages m
        JOIN chat_sessions s ON s.session_id = m.session_id
        WHERE m.owner_user_id = $1
          AND to_tsvector('english', m.content) @@ plainto_tsquery('english', $2)
        ORDER BY m.created_at DESC
        LIMIT $3
        """,
        user_id, q, limit,
    )
    return SearchResponse(items=[
        SearchResult(
            session_id=r["session_id"],
            session_title=r["session_title"],
            message_id=r["message_id"],
            role=r["role"],
            snippet=r["snippet"],
            created_at=r["created_at"],
        )
        for r in rows
    ])


@router.get("/{session_id}", response_model=ChatSession)
async def get_session(
    session_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    row = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    return _row_to_session(row)


@router.patch("/{session_id}", response_model=ChatSession)
async def patch_session(
    session_id: UUID,
    body: PatchSessionRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    row = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    # JSONB merge: existing || new (new keys overwrite, existing keys preserved)
    gp_patch = None
    if body.generation_params is not None:
        gp_patch = json.dumps(body.generation_params.model_dump(exclude_none=True))
    row = await pool.fetchrow(
        """
        UPDATE chat_sessions SET
          title             = COALESCE($3, title),
          system_prompt     = COALESCE($4, system_prompt),
          model_source      = COALESCE($5, model_source),
          model_ref         = COALESCE($6, model_ref),
          status            = COALESCE($7, status),
          generation_params = CASE WHEN $8::jsonb IS NOT NULL THEN generation_params || $8::jsonb ELSE generation_params END,
          is_pinned         = COALESCE($9, is_pinned),
          updated_at        = now()
        WHERE session_id=$1 AND owner_user_id=$2
        RETURNING *
        """,
        str(session_id), user_id,
        body.title, body.system_prompt,
        body.model_source, str(body.model_ref) if body.model_ref else None,
        body.status, gp_patch, body.is_pinned,
    )
    return _row_to_session(row)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> None:
    result = await pool.execute(
        "DELETE FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="session not found")
