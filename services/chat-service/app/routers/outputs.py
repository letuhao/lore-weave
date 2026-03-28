from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from app.deps import get_current_user, get_db
from app.models import ChatOutput, OutputListResponse, PatchOutputRequest

router = APIRouter(prefix="/v1/chat", tags=["outputs"])


def _row_to_output(r: asyncpg.Record) -> ChatOutput:
    return ChatOutput(
        output_id=r["output_id"],
        message_id=r["message_id"],
        session_id=r["session_id"],
        owner_user_id=r["owner_user_id"],
        output_type=r["output_type"],
        title=r["title"],
        content_text=r["content_text"],
        language=r["language"],
        storage_key=r["storage_key"],
        mime_type=r["mime_type"],
        file_name=r["file_name"],
        file_size_bytes=r["file_size_bytes"],
        metadata=r["metadata"],
        created_at=r["created_at"],
    )


@router.get("/sessions/{session_id}/outputs", response_model=OutputListResponse)
async def list_session_outputs(
    session_id: UUID,
    output_type: str | None = Query(None, alias="type"),
    limit: int = Query(50, le=200),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> OutputListResponse:
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    if output_type:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_outputs
            WHERE session_id=$1 AND output_type=$2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            str(session_id), output_type, limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_outputs
            WHERE session_id=$1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            str(session_id), limit,
        )
    return OutputListResponse(items=[_row_to_output(r) for r in rows])


@router.get("/outputs/{output_id}", response_model=ChatOutput)
async def get_output(
    output_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatOutput:
    row = await pool.fetchrow(
        "SELECT * FROM chat_outputs WHERE output_id=$1 AND owner_user_id=$2",
        str(output_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="output not found")
    return _row_to_output(row)


@router.patch("/outputs/{output_id}", response_model=ChatOutput)
async def patch_output(
    output_id: UUID,
    body: PatchOutputRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatOutput:
    row = await pool.fetchrow(
        "SELECT * FROM chat_outputs WHERE output_id=$1 AND owner_user_id=$2",
        str(output_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="output not found")
    row = await pool.fetchrow(
        """
        UPDATE chat_outputs SET title = COALESCE($3, title)
        WHERE output_id=$1 AND owner_user_id=$2
        RETURNING *
        """,
        str(output_id), user_id, body.title,
    )
    return _row_to_output(row)


@router.delete("/outputs/{output_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output(
    output_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> None:
    result = await pool.execute(
        "DELETE FROM chat_outputs WHERE output_id=$1 AND owner_user_id=$2",
        str(output_id), user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="output not found")


@router.get("/outputs/{output_id}/download")
async def download_output(
    output_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> PlainTextResponse:
    row = await pool.fetchrow(
        "SELECT * FROM chat_outputs WHERE output_id=$1 AND owner_user_id=$2",
        str(output_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="output not found")
    if row["content_text"] is not None:
        filename = row["file_name"] or "output.txt"
        return PlainTextResponse(
            content=row["content_text"],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    raise HTTPException(status_code=501, detail="binary download not implemented in phase 1")


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: UUID,
    fmt: str = Query("markdown", alias="format"),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> PlainTextResponse:
    exists = await pool.fetchval(
        "SELECT title FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    rows = await pool.fetch(
        """
        SELECT role, content, created_at FROM chat_messages
        WHERE session_id=$1 AND is_error=false
        ORDER BY sequence_num ASC
        """,
        str(session_id),
    )

    if fmt == "json":
        import json
        content = json.dumps([dict(r) for r in rows], default=str)
        mime = "application/json"
        filename = "chat_export.json"
    else:
        lines = [f"# Chat Export\n"]
        for r in rows:
            prefix = "**User**" if r["role"] == "user" else "**Assistant**"
            lines.append(f"{prefix}\n\n{r['content']}\n\n---\n")
        content = "\n".join(lines)
        mime = "text/markdown"
        filename = "chat_export.md"

    return PlainTextResponse(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
