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

    /review-impl(BUILD round 3) H#2 — accepts `body` kwarg for diagnostic
    forwarding from streaming-error paths. 8 call sites across client.py
    pass `body=""` when the upstream gave no error body; previously this
    raised TypeError at runtime.
    """

    code = "LLM_UPSTREAM_ERROR"

    def __init__(
        self,
        message: str,
        *,
        body: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.body = body


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


# ── Phase 5b — audio-specific exceptions ─────────────────────────────


class LLMAudioTooLarge(LLMError):
    """Caller-side audio exceeds the gateway's 25MB cap.

    Fires from TWO places in the gateway:
    - Multipart submit handler — request body exceeds the
      http.MaxBytesReader cap; rejected with HTTP 413 BEFORE the row
      is inserted.
    - Adapter belt-and-suspenders — AudioBytes slice exceeds
      provider.MaxAudioBytes; finalizes the job as failed.

    Either way the caller's audio is bad; not retryable.
    """

    code = "LLM_AUDIO_TOO_LARGE"


class LLMAudioFetchFailed(LLMError):
    """URL-mode STT: gateway couldn't GET the audio_url.

    Covers 4xx/5xx responses from the URL, DNS lookup failures,
    transport timeouts, and parse errors on the URL string itself.
    Distinguishes "we couldn't reach your audio host" from "Whisper
    upstream rejected the audio" (LLMUpstreamError).

    Phase 5a only — bytes-mode (Phase 5b) skips the fetch step entirely.
    """

    code = "LLM_AUDIO_FETCH_FAILED"


class LLMAudioURLDisallowed(LLMError):
    """URL-mode STT: audio_url host resolves to a disallowed IP range.

    SSRF guard rejects loopback (127.0.0.0/8, ::1), private (RFC1918 +
    ULA), link-local (169.254.0.0/16 — AWS IMDS endpoint), unspecified
    (0.0.0.0), and multicast addresses. The audio_url scheme must also
    be http:// or https://.

    Phase 5a only.
    """

    code = "LLM_AUDIO_URL_DISALLOWED"


# ── Phase 5c-α — image-gen-specific exceptions ───────────────────────


class LLMImageContentPolicy(LLMError):
    """Upstream rejected the prompt by content-policy / safety rules
    (DALL-E "your_request_was_rejected", gpt-image-1 safety system,
    local backends with policy filters).

    Distinct from generic LLMUpstreamError so caller's UX can surface
    a "rephrase your prompt" hint rather than a "try again" retry.
    Maps from gateway code: LLM_IMAGE_CONTENT_POLICY_VIOLATION.
    """

    code = "LLM_IMAGE_CONTENT_POLICY_VIOLATION"


class LLMImageGenerationFailed(LLMError):
    """Upstream image generation failed for a non-content-policy reason
    (model loading, backend timeout, ambiguous failure, oversized
    response body). Caller MAY retry once; persistent failures suggest
    a backend issue rather than a caller-side problem.

    Maps from gateway code: LLM_IMAGE_GENERATION_FAILED.
    """

    code = "LLM_IMAGE_GENERATION_FAILED"


# ── Phase 5d — video-gen-specific exceptions ────────────────────────


class LLMVideoContentPolicy(LLMError):
    """Upstream rejected the prompt by content-policy / safety rules
    for video generation (rare for local backends; reserved for
    OpenAI/managed services with safety filters).

    Maps from gateway code: LLM_VIDEO_CONTENT_POLICY_VIOLATION.
    """

    code = "LLM_VIDEO_CONTENT_POLICY_VIOLATION"


class LLMVideoGenerationFailed(LLMError):
    """Upstream video generation failed for a non-content-policy reason
    (model loading, backend timeout, ambiguous failure, oversized
    response body). Caller MAY retry once; persistent failures suggest
    a backend issue.

    Maps from gateway code: LLM_VIDEO_GENERATION_FAILED.
    """

    code = "LLM_VIDEO_GENERATION_FAILED"


# ── Phase 5e-β.2 — audio_gen-specific exceptions ─────────────────────


class LLMAudioGenerationFailed(LLMError):
    """Upstream batch TTS generation failed for a non-content-policy
    reason (model loading, ambiguous backend error, zero-byte response).
    Caller MAY retry but should expect double-bill exposure (TTS is
    char-billed per upstream request).

    Maps from gateway code: LLM_AUDIO_GENERATION_FAILED.
    """

    code = "LLM_AUDIO_GENERATION_FAILED"


class LLMGatewayStorageError(LLMError):
    """Phase 5e-β.2 — gateway-side storage failure (upstream TTS
    succeeded but MinIO staging failed). Distinct from upstream errors
    so callers DON'T auto-retry — the upstream call burned BYOK char-
    billing already; retrying would double-charge. Caller should
    surface the failure to the user and let them decide.

    Maps from gateway code: LLM_GATEWAY_STORAGE_ERROR.
    """

    code = "LLM_GATEWAY_STORAGE_ERROR"


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
    # Phase 5b — audio-specific exceptions (previously fell through to LLMError).
    "LLM_AUDIO_TOO_LARGE": LLMAudioTooLarge,
    "LLM_AUDIO_FETCH_FAILED": LLMAudioFetchFailed,
    "LLM_AUDIO_URL_DISALLOWED": LLMAudioURLDisallowed,
    # Phase 5c-α — image-gen-specific exceptions.
    "LLM_IMAGE_CONTENT_POLICY_VIOLATION": LLMImageContentPolicy,
    "LLM_IMAGE_GENERATION_FAILED": LLMImageGenerationFailed,
    # Phase 5d — video-gen-specific exceptions.
    "LLM_VIDEO_CONTENT_POLICY_VIOLATION": LLMVideoContentPolicy,
    "LLM_VIDEO_GENERATION_FAILED": LLMVideoGenerationFailed,
    # Phase 5e-β.2 — audio_gen-specific exception.
    "LLM_AUDIO_GENERATION_FAILED": LLMAudioGenerationFailed,
    # Phase 5e-β.2 — gateway-side storage failure (TTS succeeded but
    # staging failed). Distinct so callers don't auto-retry double-bill.
    "LLM_GATEWAY_STORAGE_ERROR": LLMGatewayStorageError,
}


def from_code(code: str, message: str, *, status_code: int | None = None, **extra) -> LLMError:
    """Construct the right exception subclass from a server error code."""
    cls = _CODE_TO_EXC.get(code, LLMError)
    if cls is LLMRateLimited:
        return LLMRateLimited(message, status_code=status_code, retry_after_s=extra.get("retry_after_s"))
    return cls(message, code=code, status_code=status_code)
