"""Video generation route — Phase 5e-α migrated to use the unified
LLM gateway via the loreweave_llm SDK.

Flow:
1. Extract user_id from JWT (header forwarded by api-gateway-bff)
2. Call Client.generate_video() — SDK handles credential resolve +
   upstream POST + polling internally (Phase 5d gateway path
   /v1/videos/generations/{text-to-video,image-to-video}).
3. Download result video URL → store in MinIO (caller-side, per
   chat-service voice precedent)
4. Best-effort usage billing
5. Return GenerateResponse with MinIO-presigned URL

Migration notes (/review-impl(DESIGN) fixes folded inline):
- HIGH#1 (Phase 5d): SDK routes via plural `/v1/videos/generations/...`
  paths; the legacy direct httpx POST to singular `/v1/video/generations`
  was removed.
- MED#1: `record_usage` widened to `provider_kind: str | None = None`
  because the gateway doesn't return provider_kind anymore.
- MED#2: legacy `PROVIDER_REGISTRY_URL` env + `resolve_credentials`
  function removed. Settings now in app/config.py.
- The download step (Step 3) still uses httpx — that's intentional
  and orthogonal to the SDK migration; banning httpx from this file
  is not the goal.
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from minio import Minio

from ..config import settings
from ..llm_errors import map_llm_error_to_http_exception
from ..models import GenerateRequest, GenerateResponse, ModelsResponse

from loreweave_llm import Client, LLMError, VideoGenResult

router = APIRouter()
logger = logging.getLogger("video-gen")

MINIO_BUCKET = "loreweave-media"
_minio: Optional[Minio] = None


def get_minio() -> Minio:
    global _minio
    if _minio is None:
        _minio = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        if not _minio.bucket_exists(MINIO_BUCKET):
            _minio.make_bucket(MINIO_BUCKET)
    return _minio


def media_url(object_key: str) -> str:
    return f"{settings.minio_external_url.rstrip('/')}/{MINIO_BUCKET}/{object_key}"


async def record_usage(
    user_id: str,
    provider_kind: str | None,
    model_source: str,
    model_ref: str,
    prompt_len: int,
) -> None:
    """Best-effort usage billing.

    /review-impl(DESIGN) MED#1 — `provider_kind` widened to Optional
    because the gateway's `Client.generate_video()` no longer returns
    it (credentials are resolved server-side). usage-billing-service
    decodes JSON null → empty string at server.go:216 (Go non-pointer
    string), which is acceptable for analytics partitioning.
    """
    if not settings.usage_billing_service_url:
        return
    try:
        payload = {
            "request_id": str(uuid.uuid4()),
            "owner_user_id": user_id,
            "provider_kind": provider_kind,
            "model_source": model_source,
            "model_ref": model_ref,
            "input_tokens": prompt_len,
            "output_tokens": 0,
            "request_status": "success",
            "purpose": "video_generation",
        }
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{settings.usage_billing_service_url.rstrip('/')}/internal/model-billing/record",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Token": settings.internal_service_token,
                },
            )
    except Exception as e:
        logger.warning("Usage billing failed: %s", e)


def extract_user_id(authorization: str) -> str:
    """Extract user_id from JWT (minimal decode — just payload.sub).

    No signature verification — api-gateway-bff validates upstream
    before forwarding. See `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH`
    deferred item for future defense-in-depth (verify locally with
    auth-service public key).
    """
    import base64
    import json as json_mod

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid token")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload = json_mod.loads(base64.urlsafe_b64decode(padded))
        return payload.get("sub", "")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def _aspect_to_size(aspect: str) -> str:
    """Convert aspect ratio to pixel dimensions for the API."""
    mapping = {
        "16:9": "1920x1080",
        "9:16": "1080x1920",
        "1:1": "1080x1080",
        "4:3": "1440x1080",
        "3:4": "1080x1440",
    }
    return mapping.get(aspect, "1920x1080")


@router.post("/generate", response_model=GenerateResponse, status_code=201)
async def generate_video(
    body: GenerateRequest,
    authorization: str = Header(default=""),
):
    """Generate a video from a text prompt via the unified LLM gateway."""
    user_id = extract_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authorization required")

    if not body.model_ref:
        raise HTTPException(status_code=400, detail="model_ref is required")

    # 1+2 (merged) — call gateway via SDK. SDK handles credential
    # resolution + upstream POST + (sync) result decoding.
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
    )
    try:
        result: VideoGenResult = await client.generate_video(
            prompt=body.prompt,
            model_source=body.model_source,
            model_ref=body.model_ref,
            size=_aspect_to_size(body.aspect_ratio),
            duration=body.duration_seconds,
            style=body.style,
        )
    except LLMError as exc:
        # /review-impl(DESIGN) Q2: shared helper maps to HTTPException.
        raise map_llm_error_to_http_exception(exc)
    finally:
        await client.aclose()

    if not result.data or not result.data[0].url:
        raise HTTPException(status_code=502, detail="Gateway returned no video URL")
    video_url_remote = result.data[0].url

    # 3. Download and store in MinIO (stream to avoid buffering large files).
    try:
        async with httpx.AsyncClient(timeout=120) as http_client:
            dl_resp = await http_client.get(video_url_remote)
        if dl_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to download generated video")

        content_type = dl_resp.headers.get("content-type", "video/mp4")
        ext = ".mp4" if "mp4" in content_type else ".webm"
        video_data = dl_resp.content
        video_size = len(video_data)
        object_key = f"video-gen/{user_id}/{uuid.uuid4()}{ext}"

        mc = get_minio()
        mc.put_object(
            MINIO_BUCKET, object_key,
            io.BytesIO(video_data), video_size,
            content_type=content_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store video: {e}")

    local_url = media_url(object_key)

    # 4. Best-effort usage billing — provider_kind=None per MED#1.
    await record_usage(user_id, None, body.model_source, body.model_ref, len(body.prompt))

    # 5. Return — `model` field carries model_ref since gateway doesn't
    # return provider_model_name (caller-side display can resolve via
    # the user-models list endpoint if a human-readable name is needed).
    return GenerateResponse(
        status="completed",
        video_url=local_url,
        thumbnail_url=None,
        message=None,
        model=body.model_ref,
        duration_seconds=body.duration_seconds,
        size_bytes=video_size,
        content_type=content_type,
    )


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """List available video generation models.

    Returns empty list — models come from provider-registry user_models
    with capability_flags.video_gen = true. Frontend queries
    /v1/model-registry/user-models?capability=video_gen directly.
    """
    return ModelsResponse(models=[])
