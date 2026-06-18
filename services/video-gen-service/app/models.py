from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Request to generate a video from a text prompt."""
    prompt: str = Field(..., min_length=1, max_length=10000)
    model_source: str = Field(default="user_model", description="user_model or platform_model")
    model_ref: str | None = Field(default=None, description="Model UUID from provider-registry")
    duration_seconds: int = Field(default=5, ge=1, le=60)
    aspect_ratio: str = Field(default="16:9", pattern=r"^\d+:\d+$")
    style: str | None = Field(default=None, description="Style hint: cinematic, anime, realistic, etc.")


class GenerateResponse(BaseModel):
    """Response from video generation.

    Serves three shapes over one model:
    - inline (flag off): 201 with status='completed' + video_url.
    - decoupled submit (flag on): 202 with status='pending' + job_id (no
      video_url yet — the FE polls GET /jobs/{job_id}).
    - decoupled poll: status in {pending,running,completed,failed,cancelled};
      video_url set on completed, error set on failed/cancelled.
    """
    status: str = Field(description="completed | pending | running | failed | cancelled | not_implemented")
    # LLM re-arch Phase 3 M5 — the decoupled job id (null on the inline path).
    job_id: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    message: str | None = None
    # M5 — error message on a failed/cancelled decoupled job.
    error: str | None = None
    model: str | None = None
    duration_seconds: int | None = None
    size_bytes: int | None = None
    content_type: str | None = None
