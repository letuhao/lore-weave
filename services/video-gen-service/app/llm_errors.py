"""Map loreweave_llm exceptions → FastAPI HTTPException with the right status.

Phase 5e-α. Centralized so any future video-gen-service endpoint using
the SDK (e.g., image_gen via generate_image, image variations, etc.)
gets consistent caller-facing error semantics.

Specific subclass checks come BEFORE the generic LLMError fallback. This
ordering matters because all LLM*-named classes inherit directly from
LLMError; isinstance(LLMError-instance) matches them all, so the first
match wins. The order also follows the memory
[[specific-sdk-exception-catches-before-generic]] — generic LLMError
catches that don't break out subclasses can silently demote permanent
errors to retry/transient.
"""

from __future__ import annotations

from fastapi import HTTPException

from loreweave_llm import (
    LLMAuthFailed,
    LLMError,
    LLMInvalidRequest,
    LLMJobTerminal,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMUpstreamError,
    LLMVideoContentPolicy,
    LLMVideoGenerationFailed,
)


def map_llm_error_to_http_exception(exc: LLMError) -> HTTPException:
    """Map a loreweave_llm exception to a FastAPI HTTPException.

    Status code conventions:
      - 400 LLM_INVALID_REQUEST → caller-side input issue
      - 400 LLM_VIDEO_CONTENT_POLICY_VIOLATION → caller's prompt rejected
            by upstream safety; FE should surface as "rephrase your prompt"
      - 402 LLM_QUOTA_EXCEEDED → billing
      - 404 LLM_MODEL_NOT_FOUND → user_model doesn't exist
      - 409 LLM_JOB_TERMINAL → job was cancelled
      - 429 LLM_RATE_LIMITED → caller should back off
      - 502 LLM_UPSTREAM_ERROR / LLM_VIDEO_GENERATION_FAILED → backend failed
      - 502 LLM_AUTH_FAILED → upstream rejected our BYOK key (usually
            rotated key — UI should prompt re-register)
    """
    if isinstance(exc, LLMInvalidRequest):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, LLMVideoContentPolicy):
        return HTTPException(status_code=400, detail=f"Content policy: {exc}")
    if isinstance(exc, LLMQuotaExceeded):
        return HTTPException(status_code=402, detail=str(exc))
    if isinstance(exc, LLMModelNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, LLMJobTerminal):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LLMRateLimited):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, LLMVideoGenerationFailed):
        return HTTPException(status_code=502, detail=f"Video generation failed: {exc}")
    if isinstance(exc, LLMUpstreamError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, LLMAuthFailed):
        return HTTPException(status_code=502, detail=f"Provider auth failed: {exc}")
    # Generic LLMError fallback.
    return HTTPException(status_code=502, detail=str(exc))
