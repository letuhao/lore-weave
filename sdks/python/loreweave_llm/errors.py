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


# ── Phase 4a-α Step 1 — async-job exceptions ─────────────────────────


class LLMJobNotFound(LLMError):
    """GET / DELETE on a job_id the gateway doesn't know about (404).

    Either the job_id is wrong, the job's result expired (default 7d
    retention per openapi.yaml line 234), or the user_id mismatches.
    """

    code = "LLM_JOB_NOT_FOUND"


class LLMJobTerminal(LLMError):
    """DELETE on a job that's already completed/failed/cancelled (409).

    Idempotent semantic — caller treats this the same as 204 (cancel
    accepted) since the desired state (job not running) is already true.
    """

    code = "LLM_JOB_TERMINAL"


class LLMHttpError(LLMError):
    """Network-level failure during a polling GET that the SDK couldn't
    classify as a domain error. Distinguishes "couldn't reach gateway"
    from "gateway said no". Caller may retry or escalate.
    """

    code = "LLM_HTTP_ERROR"


class LLMTransientRetryNeededError(LLMError):
    """Job terminated with status=failed AND error.code is in the
    transient-retry whitelist (LLM_RATE_LIMITED, LLM_UPSTREAM_ERROR).

    Bridge per ADR §3.3 D3c — the SDK does NOT auto-resubmit because
    inputs aren't retained client-side; the extractor function owns
    resubmission with the same args. The job_id of the FAILED job is
    carried so caller logs can correlate.

    `retry_after_s` is the gateway's hint (parsed from `error.retry_after_s`
    in the failed Job envelope). Caller honors when present.

    Phase 6b's gateway-side per-chunk retry will eventually make this
    rare; until then, this exception is the bridge that preserves
    knowledge-service's K17.3 quality contract.
    """

    code = "LLM_TRANSIENT_RETRY_NEEDED"

    def __init__(
        self,
        message: str,
        *,
        job_id: str,
        underlying_code: str,
        retry_after_s: float | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, code=self.code, status_code=status_code)
        self.job_id = job_id
        self.underlying_code = underlying_code
        self.retry_after_s = retry_after_s


# Codes that represent transient upstream issues — caller-side retry
# budget applies. Mirrors gateway's IsTransientUpstreamError predicate.
TRANSIENT_RETRY_CODES: frozenset[str] = frozenset({
    "LLM_RATE_LIMITED",
    "LLM_UPSTREAM_ERROR",
})


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
    "LLM_JOB_NOT_FOUND": LLMJobNotFound,
    "LLM_JOB_TERMINAL": LLMJobTerminal,
}


def from_code(code: str, message: str, *, status_code: int | None = None, **extra) -> LLMError:
    """Construct the right exception subclass from a server error code."""
    cls = _CODE_TO_EXC.get(code, LLMError)
    if cls is LLMRateLimited:
        return LLMRateLimited(message, status_code=status_code, retry_after_s=extra.get("retry_after_s"))
    return cls(message, code=code, status_code=status_code)
