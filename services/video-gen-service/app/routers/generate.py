"""Video generation route — Phase 5e-α migrated to use the unified
LLM gateway via the loreweave_llm SDK.

Flow:
1. Verify the user JWT (HS256) → user_id (Phase 5f G3)
2. Call Client.generate_video() — SDK handles credential resolve +
   upstream POST + polling internally (Phase 5d gateway path
   /v1/videos/generations/{text-to-video,image-to-video}).
3. Download result video URL → store in MinIO (caller-side, per
   chat-service voice precedent)
4. Best-effort usage billing
5. Return GenerateResponse with the public MinIO URL

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

Phase 5f hardening:
- G2+G4: bucket bootstrap (existence + public-read policy) moved off the
  request hot path into `bootstrap_minio` (lifespan startup) with a
  per-request `ensure_bucket_ready` self-heal.
- G3: incoming JWTs are now signature-verified (HS256), not blind-decoded.
- G1: the dead `/models` endpoint was removed.
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Optional

import httpx
import jwt
from fastapi import APIRouter, Header, HTTPException
from minio import Minio
from minio.error import S3Error

from ..config import settings
from ..llm_errors import map_llm_error_to_http_exception
from ..models import GenerateRequest, GenerateResponse

from loreweave_llm import Client, LLMError, VideoGenResult

router = APIRouter()
logger = logging.getLogger("video-gen")

MINIO_BUCKET = "loreweave-media"
_minio: Optional[Minio] = None
_bucket_ready = False

# Anonymous GET (public-read) policy for the media bucket. Generated
# video URLs are plain static `{minio_external_url}/{bucket}/{key}` links
# rendered in a browser <video> tag, so the bucket MUST allow anonymous
# reads. Mirrors book-service `setBucketPublicRead` (media.go) and
# provider-registry `audio_cache.go`. The bucket name is interpolated
# from MINIO_BUCKET so a rename can't drift the ARN (/review-impl LOW#5).
_PUBLIC_READ_POLICY = (
    '{"Version":"2012-10-17","Statement":[{'
    '"Effect":"Allow","Principal":{"AWS":["*"]},'
    '"Action":["s3:GetObject"],'
    '"Resource":["arn:aws:s3:::' + MINIO_BUCKET + '/*"]}]}'
)


def get_minio() -> Minio:
    """Return the cached MinIO client, creating it on first call.

    Phase 5f G2: bucket existence + policy are NOT handled here — that
    moved off the request hot path into `bootstrap_minio` (lifespan
    startup) + `ensure_bucket_ready` (per-request self-heal).
    """
    global _minio
    if _minio is None:
        _minio = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
    return _minio


def _ensure_bucket() -> None:
    """Ensure the media bucket exists with a public-read policy.

    Idempotent. Sets the module `_bucket_ready` flag on full success so
    callers can cheaply short-circuit. A lost create-race against
    book-service is NOT a failure; a genuine make_bucket failure IS, and
    propagates to the caller.
    """
    global _bucket_ready
    mc = get_minio()
    if not mc.bucket_exists(MINIO_BUCKET):
        try:
            mc.make_bucket(MINIO_BUCKET)
        except S3Error:
            # A concurrent creator (book-service) may have won the race.
            # Re-check: if the bucket now exists, treat as success;
            # otherwise the error was genuine — re-raise it.
            if not mc.bucket_exists(MINIO_BUCKET):
                raise
    # Always (re)assert the public-read policy — whoever created the
    # bucket, the policy ends up public. Idempotent; book-service sets
    # the identical policy. This closes the G4 race (private bucket).
    mc.set_bucket_policy(MINIO_BUCKET, _PUBLIC_READ_POLICY)
    _bucket_ready = True


def bootstrap_minio() -> None:
    """App-startup bucket bootstrap (called from the FastAPI lifespan).

    Best-effort: a MinIO outage at startup is logged, not fatal, so the
    service still starts and `ensure_bucket_ready` self-heals on the
    first request once MinIO is reachable.
    """
    try:
        _ensure_bucket()
    except Exception as e:  # noqa: BLE001 — best-effort startup
        logger.error(
            "MinIO bucket bootstrap failed (will retry on first request): %s", e
        )


def ensure_bucket_ready() -> None:
    """Per-request guard — a cheap no-op after the first success.

    Self-heals if `bootstrap_minio` failed at startup (e.g. MinIO was not
    yet up). Errors propagate to the request error handler.
    """
    if _bucket_ready:
        return
    _ensure_bucket()


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
    """Verify the incoming user JWT (HS256) and return its `sub` claim.

    Phase 5f G3 — replaces the prior unverified base64 decode. The token
    is signed by auth-service with the shared `JWT_SECRET` (HS256);
    `algorithms=["HS256"]` is an allow-list that also blocks the
    `alg:none` downgrade attack. `/v1/video-gen/generate` is reached only
    via api-gateway-bff forwarding the end user's Bearer token — there is
    no svc-to-svc caller (see LLM_PIPELINE_PHASE5F_DESIGN.md §3.3).
    """
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        # Bad signature, malformed, unexpected/`none` alg, non-object payload.
        raise HTTPException(status_code=401, detail="Invalid token")
    sub = payload.get("sub", "")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token")
    return sub


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
    # extract_user_id raises 401 on a missing/invalid token or empty sub.
    user_id = extract_user_id(authorization)

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

    # Ensure the media bucket is ready (self-heals if the startup
    # bootstrap failed). Done before the download so we fail fast, and
    # kept out of the download/store try-block so its error message is
    # accurate (/review-impl(BUILD) COSMETIC#7).
    try:
        ensure_bucket_ready()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Media storage unavailable: {e}")

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
