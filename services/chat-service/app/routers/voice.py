"""Voice message endpoint — accepts audio, returns SSE stream with STT + LLM + TTS."""
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
