from fastapi import APIRouter, Header, HTTPException
from ..models import GenerateRequest, GenerateResponse, ModelsResponse

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse, status_code=201)
async def generate_video(
    body: GenerateRequest,
    authorization: str = Header(default=""),
):
    """
    Generate a video from a text prompt.

    Currently returns a skeleton response. When a real video generation
    provider is integrated, this will:
    1. Resolve provider credentials via provider-registry
    2. Call the video generation API (Sora, Veo, RunwayML, etc.)
    3. Store the result in MinIO
    4. Return the video URL

    The interface is stable — clients can integrate now and get real
    results when the backend is connected to a provider.
    """
    # TODO: validate JWT when real generation logic is added (use JWT_SECRET env)
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")

    return GenerateResponse(
        status="not_implemented",
        video_url=None,
        thumbnail_url=None,
        message=(
            f"Video generation is not yet connected to a provider. "
            f"Prompt received: \"{body.prompt[:80]}{'...' if len(body.prompt) > 80 else ''}\". "
            f"Requested {body.duration_seconds}s at {body.aspect_ratio}."
        ),
        model=None,
        duration_seconds=body.duration_seconds,
        size_bytes=None,
        content_type=None,
    )


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """
    List available video generation models.

    Returns empty list until a provider is connected.
    When integrated, will return models like:
    - OpenAI Sora (text-to-video)
    - Google Veo (text-to-video)
    - Stability AI Stable Video (image-to-video)
    - RunwayML Gen-3 (text/image-to-video)
    """
    return ModelsResponse(items=[])
