"""Voice endpoints — voice message + audio segment replay."""
from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.client.billing_client import get_billing_client
from app.client.provider_client import get_provider_client
from app.deps import get_current_user, get_db
from app.services.voice_stream_service import voice_stream_response
from app.storage.minio_client import delete_object, generate_presigned_url

router = APIRouter(prefix="/v1/chat/sessions", tags=["voice"])

_MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/{session_id}/voice-message")
async def send_voice_message(
    session_id: UUID,
    audio: UploadFile = File(...),
    config: str = Form("{}"),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> StreamingResponse:
    """Send a voice message: audio → STT → LLM → TTS → SSE stream."""
    # Parse voice config
    try:
        voice_config = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid config JSON")

    # Verify session ownership (same as send_message)
    session = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session["status"] == "archived":
        raise HTTPException(status_code=409, detail="session is archived")

    # Read and validate audio file
    audio_bytes = await audio.read()
    if len(audio_bytes) > _MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="audio file too large (max 10MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="audio file is empty")
    ct = (audio.content_type or "").lower()
    if ct and not ct.startswith("audio/") and ct != "application/octet-stream":
        raise HTTPException(status_code=400, detail=f"unsupported content type: {ct}")

    # Resolve provider credentials (same as send_message)
    model_source = session["model_source"]
    model_ref = str(session["model_ref"])
    try:
        creds = await get_provider_client().resolve(model_source, model_ref, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="credential resolution failed")

    billing = get_billing_client()

    return StreamingResponse(
        voice_stream_response(
            session_id=str(session_id),
            audio_bytes=audio_bytes,
            audio_content_type=audio.content_type or "audio/webm",
            user_id=user_id,
            model_source=model_source,
            model_ref=model_ref,
            creds=creds,
            pool=pool,
            billing=billing,
            voice_config=voice_config,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_PRESIGN_EXPIRY = 900  # 15 minutes


@router.get("/{session_id}/messages/{message_id}/audio-segments")
async def get_audio_segments(
    session_id: UUID,
    message_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Get audio segments for a message, with lazily-signed S3 URLs."""
    # Verify session ownership
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    # Verify message belongs to session
    msg_exists = await pool.fetchval(
        "SELECT 1 FROM chat_messages WHERE message_id=$1 AND session_id=$2",
        str(message_id), str(session_id),
    )
    if not msg_exists:
        raise HTTPException(status_code=404, detail="message not found")

    rows = await pool.fetch(
        """
        SELECT segment_index, sentence_text, duration_s, object_key
        FROM message_audio_segments
        WHERE message_id=$1
        ORDER BY segment_index ASC
        """,
        str(message_id),
    )

    segments = []
    for r in rows:
        url = await generate_presigned_url(r["object_key"], expiry=_PRESIGN_EXPIRY)
        segments.append({
            "index": r["segment_index"],
            "text": r["sentence_text"],
            "durationS": r["duration_s"],
            "url": url,
        })

    return {"segments": segments}


voice_mgmt_router = APIRouter(prefix="/v1/chat/voice", tags=["voice"])


@voice_mgmt_router.post("/cleanup")
async def cleanup_expired_audio(
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Delete expired audio segments (48h+). Called by cron/scheduler.

    Two-layer cleanup:
    1. DB rows deleted first (returns object keys)
    2. S3 objects deleted (if fails, S3 lifecycle is safety net)
    """
    rows = await pool.fetch(
        """
        DELETE FROM message_audio_segments
        WHERE created_at < now() - interval '48 hours'
        RETURNING object_key
        """,
    )
    deleted = 0
    for r in rows:
        try:
            await delete_object(r["object_key"])
            deleted += 1
        except Exception:
            pass  # S3 lifecycle will catch orphans
    return {"deletedSegments": len(rows), "deletedObjects": deleted}


@voice_mgmt_router.delete("/data")
async def delete_user_voice_data(
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """GDPR erasure — delete all voice audio for this user."""
    rows = await pool.fetch(
        """
        DELETE FROM message_audio_segments
        WHERE user_id = $1
        RETURNING object_key
        """,
        user_id,
    )
    deleted = 0
    for r in rows:
        try:
            await delete_object(r["object_key"])
            deleted += 1
        except Exception:
            pass
    return {"deletedSegments": len(rows), "deletedObjects": deleted}
