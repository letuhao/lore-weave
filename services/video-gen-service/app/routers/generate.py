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
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Header, HTTPException, Path, Response
from minio import Minio
from minio.error import S3Error

from ..config import settings
from ..db.pool import get_pool
from ..db.repository import VideoGenJobsRepo
from ..llm_errors import map_llm_error_to_http_exception
from ..models import GenerateRequest, GenerateResponse

from loreweave_llm import Client, LLMError, VideoGenResult
from loreweave_llm.models import SubmitJobRequest

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


class VideoDownloadError(RuntimeError):
    """The remote video URL could not be fetched (→ 502 on the inline path)."""


class VideoStorageError(RuntimeError):
    """MinIO bucket/put failed (→ 500 on the inline path)."""


async def download_and_store(user_id: str, video_url_remote: str) -> tuple[str, int, str]:
    """Download the gateway's remote video URL → store in MinIO → return
    ``(local_url, size_bytes, content_type)``.

    Shared by the inline 201 path AND the M5 decoupled terminal-event consumer
    (the whole point of the decouple is to run THIS off the request path). The
    inline path maps the two error classes to its historical 502/500 statuses;
    the consumer treats either as a failed terminal. Streams to MinIO; bucket
    readiness is self-healed first so we fail fast before the download.
    """
    try:
        ensure_bucket_ready()
    except Exception as e:  # noqa: BLE001 — surfaced as storage-unavailable
        raise VideoStorageError(f"Media storage unavailable: {e}") from e

    try:
        async with httpx.AsyncClient(timeout=120) as http_client:
            dl_resp = await http_client.get(video_url_remote)
    except Exception as e:  # noqa: BLE001 — transport failure on the download
        raise VideoDownloadError(f"Failed to download generated video: {e}") from e
    if dl_resp.status_code != 200:
        raise VideoDownloadError("Failed to download generated video")

    content_type = dl_resp.headers.get("content-type", "video/mp4")
    ext = ".mp4" if "mp4" in content_type else ".webm"
    video_data = dl_resp.content
    video_size = len(video_data)
    object_key = f"video-gen/{user_id}/{uuid.uuid4()}{ext}"
    try:
        get_minio().put_object(
            MINIO_BUCKET, object_key,
            io.BytesIO(video_data), video_size,
            content_type=content_type,
        )
    except Exception as e:  # noqa: BLE001 — MinIO put failed
        raise VideoStorageError(f"Failed to store video: {e}") from e

    return media_url(object_key), video_size, content_type


def _build_video_input(body: GenerateRequest) -> dict:
    """The ``video_gen`` job ``input`` payload — mirrors the SDK's
    ``generate_video`` (size from aspect, optional duration/style). Used by the
    M5 decoupled submit so the gateway sees the identical shape the inline SDK
    call produced."""
    payload: dict = {"prompt": body.prompt, "size": _aspect_to_size(body.aspect_ratio)}
    if body.duration_seconds is not None:
        payload["duration"] = body.duration_seconds
    if body.style is not None:
        payload["style"] = body.style
    return payload


@router.post("/generate", response_model=GenerateResponse, status_code=201)
async def generate_video(
    body: GenerateRequest,
    response: Response,
    authorization: str = Header(default=""),
):
    """Generate a video from a text prompt via the unified LLM gateway.

    Two paths, gated by ``VIDEO_GEN_DECOUPLE_ENABLED`` (LLM re-arch Phase 3 M5):
    - flag OFF (default): inline — submit + wait + download + store, return 201
      ``completed`` verbatim (unchanged contract).
    - flag ON: decoupled — submit the gateway job (don't wait), persist a
      ``video_gen_jobs`` row, return 202 ``pending`` ``{job_id}``. The worker
      consumes the terminal event, downloads → MinIO, marks the row done; the FE
      polls ``GET /v1/video-gen/jobs/{job_id}``.
    """
    # extract_user_id raises 401 on a missing/invalid token or empty sub.
    user_id = extract_user_id(authorization)

    if not body.model_ref:
        raise HTTPException(status_code=400, detail="model_ref is required")

    if settings.video_gen_decouple_enabled:
        return await _submit_decoupled(body, user_id, response)

    # ── Inline path (flag off) — submit + wait + download + store ─────────────
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

    # 3. Download and store in MinIO (shared helper — preserves the historical
    # 502 download / 500 storage status split via the two error classes).
    try:
        local_url, video_size, content_type = await download_and_store(user_id, video_url_remote)
    except VideoDownloadError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except VideoStorageError as e:
        raise HTTPException(status_code=500, detail=str(e))

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


async def _submit_decoupled(
    body: GenerateRequest, user_id: str, response: Response
) -> GenerateResponse:
    """M5 decoupled submit — submit the gateway job (NOT wait), persist a
    pending ``video_gen_jobs`` row, return 202 ``{job_id, status:'pending'}``.
    Billing + download move to the worker's terminal-event completion."""
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
    )
    try:
        submitted = await client.submit_job(
            SubmitJobRequest(
                operation="video_gen",
                model_source=body.model_source,  # type: ignore[arg-type]
                model_ref=body.model_ref,
                input=_build_video_input(body),
            ),
            user_id=user_id,
        )
    except LLMError as exc:
        raise map_llm_error_to_http_exception(exc)
    finally:
        await client.aclose()

    # request_json keeps prompt + model refs for the worker's billing
    # (prompt_len) and for replay/debug.
    repo = VideoGenJobsRepo(get_pool())
    job = await repo.create(
        user_id=UUID(user_id),
        provider_job_id=UUID(str(submitted.job_id)),
        request_json={
            "prompt": body.prompt,
            "model_source": body.model_source,
            "model_ref": body.model_ref,
            "duration_seconds": body.duration_seconds,
            "aspect_ratio": body.aspect_ratio,
            "style": body.style,
        },
    )
    response.status_code = 202
    return GenerateResponse(
        status="pending",
        job_id=str(job.id),
        model=body.model_ref,
        duration_seconds=body.duration_seconds,
    )


@router.get("/jobs/{job_id}", response_model=GenerateResponse)
async def get_video_job(
    job_id: UUID = Path(...),
    authorization: str = Header(default=""),
):
    """Poll a decoupled video-gen job (LLM re-arch Phase 3 M5). 404 cross-user.

    Returns the same ``GenerateResponse`` shape as the inline path once the job
    completes (status='completed' + video_url), so the FE renders both paths
    identically. Available only when the decouple flag is on (the inline path
    never creates a row → always 404)."""
    user_id = extract_user_id(authorization)
    if not settings.video_gen_decouple_enabled:
        # No job rows exist on the inline path; the pool isn't even initialised.
        raise HTTPException(status_code=404, detail="Job not found")
    repo = VideoGenJobsRepo(get_pool())
    job = await repo.get(UUID(user_id), job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    req = job.request_json or {}
    err = job.error_json or {}
    return GenerateResponse(
        status=job.status,
        job_id=str(job.id),
        video_url=job.video_url,
        error=err.get("message") if err else None,
        model=req.get("model_ref"),
        duration_seconds=req.get("duration_seconds"),
        size_bytes=job.size_bytes,
        content_type=job.content_type,
    )
