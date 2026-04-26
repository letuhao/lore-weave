"""Exception hierarchy for the loreweave_llm SDK.

All errors raised by the SDK inherit from `LLMError`. Specific subclasses
mirror the gateway's error code namespace (see openapi spec ErrorBody.code).
"""

from __future__ import annotations


class LLMError(Exception):
    """Base error for the loreweave_llm SDK."""

    code: str = "LLM_ERROR"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.status_code = status_code


class LLMAuthFailed(LLMError):
    code = "LLM_AUTH_FAILED"


class LLMInvalidRequest(LLMError):
    code = "LLM_INVALID_REQUEST"


class LLMQuotaExceeded(LLMError):
    code = "LLM_QUOTA_EXCEEDED"


class LLMModelNotFound(LLMError):
    code = "LLM_MODEL_NOT_FOUND"


class LLMRateLimited(LLMError):
    code = "LLM_RATE_LIMITED"

    def __init__(self, message: str, *, retry_after_s: float | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after_s = retry_after_s


class LLMUpstreamError(LLMError):
    """Upstream provider returned an error during the streaming session.

    Distinguished from `LLMRateLimited` etc. because these surface as
    `event: error` SSE frames, not as HTTP-level errors.
    """

    code = "LLM_UPSTREAM_ERROR"


class LLMStreamNotSupported(LLMError):
    code = "LLM_STREAM_NOT_SUPPORTED"


class LLMDecodeError(LLMError):
    """Gateway emitted a malformed event we could not parse."""

    code = "LLM_DECODE_ERROR"


# Mapping from server-emitted error code to exception class.
_CODE_TO_EXC: dict[str, type[LLMError]] = {
    "LLM_AUTH_FAILED": LLMAuthFailed,
    "LLM_INVALID_REQUEST": LLMInvalidRequest,
    "LLM_QUOTA_EXCEEDED": LLMQuotaExceeded,
    "LLM_MODEL_NOT_FOUND": LLMModelNotFound,
    "LLM_RATE_LIMITED": LLMRateLimited,
    "LLM_UPSTREAM_ERROR": LLMUpstreamError,
    "LLM_STREAM_NOT_SUPPORTED": LLMStreamNotSupported,
    "LLM_DECODE_ERROR": LLMDecodeError,
}


def from_code(code: str, message: str, *, status_code: int | None = None, **extra) -> LLMError:
    """Construct the right exception subclass from a server error code."""
    cls = _CODE_TO_EXC.get(code, LLMError)
    if cls is LLMRateLimited:
        return LLMRateLimited(message, status_code=status_code, retry_after_s=extra.get("retry_after_s"))
    return cls(message, code=code, status_code=status_code)
