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
    """Response from video generation."""
    status: str = Field(description="completed | pending | failed | not_implemented")
    video_url: str | None = None
    thumbnail_url: str | None = None
    message: str | None = None
    model: str | None = None
    duration_seconds: int | None = None
    size_bytes: int | None = None
    content_type: str | None = None


class ModelInfo(BaseModel):
    """Available video generation model."""
    id: str
    name: str
    provider: str
    max_duration_seconds: int
    supported_aspect_ratios: list[str]
    supported_styles: list[str] = []


class ModelsResponse(BaseModel):
    items: list[ModelInfo] = []
