import io
import logging
import os
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from minio import Minio

from ..models import GenerateRequest, GenerateResponse, ModelsResponse

router = APIRouter()
logger = logging.getLogger("video-gen")

PROVIDER_REGISTRY_URL = os.getenv("PROVIDER_REGISTRY_URL", "")
INTERNAL_SERVICE_TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
USAGE_BILLING_URL = os.getenv("USAGE_BILLING_SERVICE_URL", "")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
MINIO_EXTERNAL_URL = os.environ["MINIO_EXTERNAL_URL"].rstrip("/")
MINIO_BUCKET = "loreweave-media"

_minio: Optional[Minio] = None


def get_minio() -> Minio:
    global _minio
    if _minio is None:
        _minio = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        if not _minio.bucket_exists(MINIO_BUCKET):
            _minio.make_bucket(MINIO_BUCKET)
    return _minio


def media_url(object_key: str) -> str:
    return f"{MINIO_EXTERNAL_URL}/{MINIO_BUCKET}/{object_key}"


async def resolve_credentials(model_source: str, model_ref: str, user_id: str) -> dict:
    """Resolve provider credentials via provider-registry internal API."""
    if not PROVIDER_REGISTRY_URL or not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="Provider registry not configured")

    url = f"{PROVIDER_REGISTRY_URL}/internal/credentials/{model_source}/{model_ref}?user_id={user_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers={"X-Internal-Token": INTERNAL_SERVICE_TOKEN})

    if resp.status_code == 404:
        raise HTTPException(status_code=402, detail="No active AI provider configured")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Provider registry error")

    return resp.json()


async def record_usage(user_id: str, provider_kind: str, model_source: str, model_ref: str, prompt_len: int):
    """Best-effort usage billing."""
    if not USAGE_BILLING_URL:
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
                f"{USAGE_BILLING_URL.rstrip('/')}/internal/model-billing/record",
                json=payload,
                headers={"Content-Type": "application/json", "X-Internal-Token": INTERNAL_SERVICE_TOKEN},
            )
    except Exception as e:
        logger.warning("Usage billing failed: %s", e)


def extract_user_id(authorization: str) -> str:
    """Extract user_id from JWT (minimal decode — just payload.sub)."""
    import base64
    import json as json_mod

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Decode payload (no signature verification — gateway already validated)
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload = json_mod.loads(base64.urlsafe_b64decode(padded))
        return payload.get("sub", "")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/generate", response_model=GenerateResponse, status_code=201)
async def generate_video(
    body: GenerateRequest,
    authorization: str = Header(default=""),
):
    """
    Generate a video from a text prompt via BYOK provider.

    Flow:
    1. Resolve provider credentials via provider-registry
    2. Call the video generation API (OpenAI Sora-compatible)
    3. Download result → store in MinIO
    4. Record usage billing
    5. Return video URL
    """
    user_id = extract_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authorization required")

    if not body.model_ref:
        raise HTTPException(status_code=400, detail="model_ref is required")

    # 1. Resolve credentials
    creds = await resolve_credentials(body.model_source, body.model_ref, user_id)
    provider_kind = creds.get("provider_kind", "")
    model_name = creds.get("provider_model_name", "")
    base_url = creds.get("base_url", "")
    api_key = creds.get("api_key", "")

    if not base_url:
        if provider_kind == "openai":
            base_url = "https://api.openai.com"
        else:
            raise HTTPException(status_code=502, detail=f"No base_url for provider {provider_kind}")

    # 2. Call video generation API (OpenAI Sora-compatible)
    gen_payload = {
        "model": model_name,
        "prompt": body.prompt,
        "size": _aspect_to_size(body.aspect_ratio),
        "duration": body.duration_seconds,
        "n": 1,
    }
    if body.style:
        gen_payload["style"] = body.style

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            gen_resp = await client.post(
                f"{base_url.rstrip('/')}/v1/video/generations",
                json=gen_payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Video generation timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider request failed: {e}")

    if gen_resp.status_code != 200:
        detail = gen_resp.text[:500]
        raise HTTPException(status_code=502, detail=f"Provider returned {gen_resp.status_code}: {detail}")

    result = gen_resp.json()
    data_list = result.get("data", [])
    if not data_list:
        raise HTTPException(status_code=502, detail="Provider returned empty result")

    video_url_remote = data_list[0].get("url", "")
    if not video_url_remote:
        raise HTTPException(status_code=502, detail="Provider returned no video URL")

    # 3. Download and store in MinIO (stream to avoid buffering large files)
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            dl_resp = await client.get(video_url_remote)
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

    # 4. Best-effort usage billing
    await record_usage(user_id, provider_kind, body.model_source, body.model_ref, len(body.prompt))

    # 5. Return
    return GenerateResponse(
        status="completed",
        video_url=local_url,
        thumbnail_url=None,
        message=None,
        model=model_name,
        duration_seconds=body.duration_seconds,
        size_bytes=video_size,
        content_type=content_type,
    )


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


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """
    List available video generation models.

    Returns empty list — models come from provider-registry user_models
    with capability_flags.video_gen = true.
    """
    return ModelsResponse(items=[])
