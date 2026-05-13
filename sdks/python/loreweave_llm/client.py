"""loreweave_llm.Client — thin async wrapper over the gateway's
`/v1/llm/stream` and `/internal/llm/stream` endpoints.

Phase 1b shipped streaming. Phase 4a-α Step 1 wires async-job APIs
(submit_job + get_job + wait_terminal + cancel_job) so knowledge-service
extractors can route LLM calls through the unified job pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

import httpx

from loreweave_llm.errors import (
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMHttpError,
    LLMInvalidRequest,
    LLMJobNotFound,
    LLMJobTerminal,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMTransientRetryNeededError,
    LLMUpstreamError,
    TRANSIENT_RETRY_CODES,
    from_code,
)
from loreweave_llm.models import (
    AudioChunkEvent,
    AudioFormat,
    DoneEvent,
    ErrorEvent,
    ImageGenResult,
    Job,
    ModelSource,
    ReasoningEvent,
    StreamEvent,
    StreamRequest,
    SttResult,
    SubmitJobRequest,
    SubmitJobResponse,
    TokenEvent,
    TtsInput,
    TtsStreamRequest,
    UsageEvent,
)

logger = logging.getLogger(__name__)

AuthMode = Literal["jwt", "internal"]

# Default per-event read timeout — only the IDLE wait for the next SSE
# frame, NOT a wall-clock cap on the whole stream. The whole-stream
# timeout is None (unbounded) by design (P1 — streaming chat must have
# no wall-clock timeout).
_DEFAULT_IDLE_READ_TIMEOUT_S = 120.0


class Client:
    """SDK client for the LoreWeave LLM gateway.

    Two flavors of auth:
    - `auth_mode="jwt"` — pass `bearer_token` (used by FE / api-gateway-bff)
    - `auth_mode="internal"` — pass `internal_token` AND `user_id` (svc→svc)

    Construct one Client per process (it owns an httpx.AsyncClient
    connection pool). Close via `await client.aclose()` on shutdown.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth_mode: AuthMode = "internal",
        bearer_token: str | None = None,
        internal_token: str | None = None,
        user_id: str | None = None,
        idle_read_timeout_s: float = _DEFAULT_IDLE_READ_TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if auth_mode == "jwt" and not bearer_token:
            raise ValueError("auth_mode='jwt' requires bearer_token")
        if auth_mode == "internal" and not internal_token:
            raise ValueError("auth_mode='internal' requires internal_token")
        # Phase 4a-α Step 1 — user_id is OPTIONAL at construction for
        # multi-tenant services (knowledge-service routes many users
        # through one Client). Per-call methods accept user_id override;
        # constructor user_id is only the default for single-tenant clients.

        self._base_url = base_url.rstrip("/")
        self._auth_mode = auth_mode
        self._bearer_token = bearer_token
        self._internal_token = internal_token
        self._user_id = user_id

        # Whole-stream timeout = None (unbounded). Connect timeout = 5s
        # (fail fast if gateway is unreachable). Per-read timeout =
        # idle_read_timeout_s (longest gap between SSE frames before we
        # treat the stream as stalled — typical providers send at least a
        # keep-alive comment every 30-60s).
        timeout = httpx.Timeout(None, connect=5.0, read=idle_read_timeout_s)
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        if self._http.is_closed:
            return
        await self._http.aclose()

    # ── Streaming (P1) ────────────────────────────────────────────────

    async def stream(
        self,
        request: StreamRequest,
        *,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Open a streaming chat session.

        Yields canonical `StreamEvent` instances (TokenEvent / UsageEvent /
        DoneEvent). On `event: error` from the gateway, raises an
        `LLMError` subclass keyed by the error code.

        **No wall-clock timeout.** The iterator runs until the gateway
        emits `done`, errors, or the consumer cancels via the standard
        async-iter close protocol.

        `user_id` per-call override (multi-tenant pattern, mirrors the
        jobs methods). Required when auth_mode='internal' AND constructor
        user_id was None. Per /review-impl MED#4 — without this, multi-
        tenant services (knowledge-service) couldn't safely call stream()
        even though the constructor accepts user_id=None.

        Usage:
            async for ev in client.stream(StreamRequest(...)):
                if isinstance(ev, TokenEvent):
                    print(ev.delta, end="", flush=True)
                elif isinstance(ev, UsageEvent):
                    metrics.add(ev.input_tokens, ev.output_tokens)
                elif isinstance(ev, DoneEvent):
                    break
        """
        body = request.to_request_body()
        async for ev in self._stream_inner(body, user_id=user_id):
            yield ev

    async def _stream_inner(
        self,
        body: dict,
        *,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Phase 5a — shared SSE iteration machinery used by both
        `stream()` (chat) and `stream_tts()` (audio). Caller builds the
        wire body via {ChatStreamRequest, TtsStreamRequest}.to_request_body().

        Resolves auth + URL identically; the gateway routes on the
        body's `operation` field. Yields canonical StreamEvent (any of
        TokenEvent / ReasoningEvent / UsageEvent / DoneEvent / ErrorEvent /
        AudioChunkEvent — the union widened in Phase 5a). Returns when
        DoneEvent is yielded; raises LLMError on ErrorEvent.
        """
        if self._auth_mode == "jwt":
            url = f"{self._base_url}/v1/llm/stream"
            headers = {"Authorization": f"Bearer {self._bearer_token}"}
            params: dict[str, str] = {}
        else:
            effective_user_id = user_id if user_id is not None else self._user_id
            if not effective_user_id:
                raise LLMInvalidRequest(
                    "internal auth_mode requires user_id (per-call or at construction)"
                )
            url = f"{self._base_url}/internal/llm/stream"
            headers = {"X-Internal-Token": self._internal_token or ""}
            params = {"user_id": effective_user_id}

        async with self._http.stream(
            "POST",
            url,
            params=params,
            headers={**headers, "Accept": "text/event-stream"},
            json=body,
        ) as resp:
            if resp.status_code >= 400:
                # HTTP-level error — read body, classify, raise.
                await self._raise_http_error(resp)
            async for ev in self._iter_sse_events(resp):
                if isinstance(ev, ErrorEvent):
                    # SSE-frame error — translate to exception so the
                    # consumer doesn't have to re-implement error handling.
                    raise from_code(ev.code, ev.message)
                yield ev
                if isinstance(ev, DoneEvent):
                    return

    # ── Audio (Phase 5a) ──────────────────────────────────────────────

    async def stream_tts(
        self,
        text: str,
        *,
        model_source: ModelSource,
        model_ref: str,
        voice: str = "alloy",
        speed: float = 1.0,
        format: AudioFormat = "mp3",
        user_id: str | None = None,
    ) -> AsyncIterator[AudioChunkEvent | DoneEvent]:
        """Stream TTS audio chunks via POST /v1/llm/stream (operation=tts).

        Yields AudioChunkEvent until `final=True`, then a DoneEvent and
        returns. ErrorEvent → raised as LLMError subclass keyed by code.

        Caller decodes each AudioChunkEvent.data from base64 and
        concatenates in `sequence_id` order to reconstruct the full
        audio container (mp3/wav/opus/pcm per `format`).

        Usage:
            async for ev in client.stream_tts(text="hi", model_source=..., model_ref=...):
                if isinstance(ev, AudioChunkEvent):
                    raw = base64.b64decode(ev.data)
                    audio_player.feed(raw)
                    if ev.final:
                        audio_player.flush()
                # DoneEvent ends iteration

        `user_id` per-call override (mirrors `stream()`); required when
        auth_mode='internal' AND constructor user_id was None.
        """
        try:
            model_ref_uuid = UUID(model_ref)
        except (TypeError, ValueError) as exc:
            raise LLMInvalidRequest(
                f"model_ref must be UUID-shaped, got {model_ref!r}",
            ) from exc

        request = TtsStreamRequest(
            model_source=model_source,
            model_ref=model_ref_uuid,
            input=TtsInput(text=text, voice=voice, speed=speed, format=format),
        )
        body = request.to_request_body()
        async for ev in self._stream_inner(body, user_id=user_id):
            if isinstance(ev, (AudioChunkEvent, DoneEvent)):
                yield ev
            # TokenEvent / ReasoningEvent / UsageEvent shouldn't appear on
            # tts streams; if they do, ignore them silently rather than
            # confuse the caller's iterator. Future audio adapters may
            # emit usage events — extend this filter then.

    # ── Async jobs (P2) — Phase 4a-α Step 1 ───────────────────────────

    async def submit_job(
        self,
        request: SubmitJobRequest,
        *,
        user_id: str | None = None,
    ) -> SubmitJobResponse:
        """Submit an async LLM job. Returns the 202 envelope.

        Validates `request.model_ref` is UUID-shaped before hitting the
        wire (per ADR §5.1 MED#5 — extractor signatures stay `str`, SDK
        is the boundary). Raises LLMInvalidRequest on malformed UUID,
        LLMAuthFailed/LLMQuotaExceeded/LLMRateLimited on respective HTTP
        statuses, LLMHttpError on transport-level failures.

        `user_id` overrides the Client's default for this call. Required
        when auth_mode='internal' AND constructor user_id was None
        (multi-tenant pattern).
        """
        try:
            UUID(request.model_ref)
        except (TypeError, ValueError) as exc:
            raise LLMInvalidRequest(
                f"model_ref must be a UUID-shaped string, got {request.model_ref!r}",
            ) from exc

        url, params, headers = self._jobs_endpoint("submit", user_id=user_id)
        body = request.to_request_body()
        try:
            resp = await self._http.post(url, params=params, headers=headers, json=body)
        except httpx.RequestError as exc:
            raise LLMHttpError(f"submit_job transport failure: {exc}") from exc
        if resp.status_code >= 400:
            await self._raise_http_error(resp)
        try:
            return SubmitJobResponse.model_validate(resp.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMDecodeError(f"submit_job response decode failed: {exc}") from exc

    async def get_job(self, job_id: str | UUID, *, user_id: str | None = None) -> Job:
        """Fetch current Job state. Single GET — caller does the polling
        loop (see wait_terminal for a managed loop).

        Per-poll httpx.Timeout is overridden via the shared client's
        timeout policy; for fast pings under load callers should accept
        that a slow poll fails with LLMHttpError and retry from the
        backoff schedule.

        `user_id` per-call override (see submit_job).
        """
        job_id_str = str(job_id)
        url, params, headers = self._jobs_endpoint("get", job_id=job_id_str, user_id=user_id)
        try:
            resp = await self._http.get(url, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise LLMHttpError(f"get_job transport failure: {exc}") from exc
        if resp.status_code == 404:
            raise LLMJobNotFound(f"job {job_id_str} not found", status_code=404)
        if resp.status_code >= 400:
            await self._raise_http_error(resp)
        try:
            return Job.model_validate(resp.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMDecodeError(f"get_job response decode failed: {exc}") from exc

    async def wait_terminal(
        self,
        job_id: str | UUID,
        *,
        user_id: str | None = None,
        poll_interval_s: float = 0.25,
        max_poll_interval_s: float = 5.0,
        poll_backoff: float = 1.5,
        transient_retry_budget: int = 1,
    ) -> Job:
        """Poll get_job until status ∈ {completed, failed, cancelled}.

        Exponential backoff between polls (clamped to max_poll_interval_s).
        NO wall-clock timeout — polling continues until terminal or
        repeated HTTP failure.

        Per ADR §3.3 D3c — when the terminal job has status=failed AND
        error.code is transient (LLM_RATE_LIMITED, LLM_UPSTREAM_ERROR),
        AND transient_retry_budget>0, raises LLMTransientRetryNeededError
        carrying job_id + underlying_code + retry_after_s. Caller owns
        resubmission with the same args; SDK does NOT auto-resubmit
        because inputs aren't retained client-side.

        Per-poll HTTP failures (LLMHttpError) consume transient_retry_budget;
        at zero, propagates the LLMHttpError to caller.

        Returns the terminal Job (status ∈ {completed, cancelled}, OR
        status=failed with non-transient error code) — caller distinguishes
        by inspecting Job.status / Job.error.

        Cancel-race correctness (per ADR §5.5): if the user/UI calls
        DELETE /v1/llm/jobs/{id} while we're polling, the next poll
        returns status=cancelled and we return that Job — caller
        handles the 'cancelled' terminal outcome.
        """
        job_id_str = str(job_id)
        interval = poll_interval_s
        http_failures = 0
        while True:
            try:
                job = await self.get_job(job_id_str, user_id=user_id)
            except LLMHttpError:
                http_failures += 1
                if http_failures > transient_retry_budget:
                    raise
                await asyncio.sleep(interval)
                interval = min(interval * poll_backoff, max_poll_interval_s)
                continue

            if job.is_terminal():
                if (
                    job.status == "failed"
                    and job.error is not None
                    and job.error.code in TRANSIENT_RETRY_CODES
                    and transient_retry_budget > 0
                ):
                    raise LLMTransientRetryNeededError(
                        f"job {job_id_str} failed with transient {job.error.code}: {job.error.message}",
                        job_id=job_id_str,
                        underlying_code=job.error.code,
                        retry_after_s=job.error.retry_after_s,
                    )
                return job

            await asyncio.sleep(interval)
            interval = min(interval * poll_backoff, max_poll_interval_s)

    async def transcribe(
        self,
        audio: str | bytes | bytearray | memoryview,
        *,
        model_source: ModelSource,
        model_ref: str,
        language: str = "auto",
        content_type: str | None = None,
        user_id: str | None = None,
        poll_interval_s: float = 0.25,
        max_poll_interval_s: float = 5.0,
    ) -> SttResult:
        """Submit STT job, wait for terminal, return decoded result.

        Polymorphic in `audio`:
          - `str` → URL mode (Phase 5a). The gateway fetches `audio_url`
            via HTTPS GET (SSRF-guarded, 30s timeout, 25MB cap).
          - `bytes | bytearray | memoryview` → bytes mode (Phase 5b).
            Multipart POST to /v1/llm/jobs carrying the audio inline.
            `content_type` is REQUIRED (e.g. "audio/webm"); raises
            LLMInvalidRequest if missing.

        Reuses submit_job + wait_terminal in URL mode. Bytes mode uses
        a dedicated multipart submit (no SubmitJobRequest pydantic
        validation — wire is form-data, not JSON) then routes through
        wait_terminal. Same backoff, same cancellation, same transient-
        retry semantics. `transient_retry_budget=0` because gateway-side
        audio fetch + Whisper upstream are deterministic; auto-rerunning
        would double-charge BYOK.

        Raises:
          - LLMInvalidRequest on malformed model_ref, bytes-without-content-type,
            or unsupported `audio` type
          - LLMAudioTooLarge on >25MB audio (handler-side or adapter-side)
          - LLMAudioFetchFailed / LLMAudioURLDisallowed on URL-mode fetch issues
          - LLMError subclass keyed by job.error.code on status=failed
          - LLMJobTerminal on status=cancelled

        `user_id` per-call override (mirrors submit_job). Required when
        auth_mode='internal' AND constructor user_id was None.
        """
        try:
            UUID(model_ref)
        except (TypeError, ValueError) as exc:
            raise LLMInvalidRequest(
                f"model_ref must be UUID-shaped, got {model_ref!r}",
            ) from exc

        # Phase 5b — dispatch on audio's runtime type. Accepts the four
        # standard Python buffer-protocol types so callers using
        # numpy/sounddevice/pyaudio's memoryview output don't have to
        # copy bytes manually.
        if isinstance(audio, str):
            submitted = await self._submit_stt_url(
                audio_url=audio,
                model_source=model_source,
                model_ref=model_ref,
                language=language,
                user_id=user_id,
            )
        elif isinstance(audio, (bytes, bytearray, memoryview)):
            if not content_type:
                raise LLMInvalidRequest(
                    "content_type required when audio is bytes-like; "
                    "pass content_type=\"audio/webm\" (or similar)",
                )
            submitted = await self._submit_stt_bytes(
                audio=audio,
                content_type=content_type,
                model_source=model_source,
                model_ref=model_ref,
                language=language,
                user_id=user_id,
            )
        else:
            raise LLMInvalidRequest(
                "audio must be str (URL) or bytes-like (bytes/bytearray/memoryview); "
                f"got {type(audio).__name__}",
            )

        job = await self.wait_terminal(
            submitted.job_id,
            user_id=user_id,
            poll_interval_s=poll_interval_s,
            max_poll_interval_s=max_poll_interval_s,
            transient_retry_budget=0,
        )
        if job.status == "completed":
            if job.result is None:
                raise LLMUpstreamError(
                    "stt job completed but result is empty",
                    status_code=None,
                    body="",
                )
            return SttResult.model_validate(job.result)
        if job.status == "cancelled":
            raise LLMJobTerminal(f"stt job {submitted.job_id} cancelled")
        # status == "failed"
        if job.error is None:
            raise LLMUpstreamError(
                f"stt job {submitted.job_id} failed without error body",
                status_code=None,
                body="",
            )
        raise from_code(job.error.code, job.error.message)

    async def _submit_stt_url(
        self,
        *,
        audio_url: str,
        model_source: ModelSource,
        model_ref: str,
        language: str,
        user_id: str | None,
    ) -> SubmitJobResponse:
        """Phase 5a — JSON-mode STT submit. Wraps submit_job with the
        legacy `{audio_url, language}` input shape.
        """
        request = SubmitJobRequest(
            operation="stt",
            model_source=model_source,
            model_ref=model_ref,
            input={"audio_url": audio_url, "language": language},
        )
        return await self.submit_job(request, user_id=user_id)

    async def _submit_stt_bytes(
        self,
        *,
        audio: bytes | bytearray | memoryview,
        content_type: str,
        model_source: ModelSource,
        model_ref: str,
        language: str,
        user_id: str | None,
    ) -> SubmitJobResponse:
        """Phase 5b — multipart-mode STT submit. Wire shape: multipart/form-data
        with metadata fields + an `audio` file part. Returns 202 envelope
        matching submit_job's response.

        Validates model_ref UUID shape before hitting the wire (per
        ADR §5.1 MED#5 — SDK is the boundary). Maps HTTP errors via
        _raise_http_error so audio-specific codes (LLM_AUDIO_TOO_LARGE,
        LLM_AUDIO_FETCH_FAILED, LLM_AUDIO_URL_DISALLOWED) surface as
        their proper exception classes.
        """
        try:
            UUID(model_ref)
        except (TypeError, ValueError) as exc:
            raise LLMInvalidRequest(
                f"model_ref must be a UUID-shaped string, got {model_ref!r}",
            ) from exc

        url, params, headers = self._jobs_endpoint("submit", user_id=user_id)
        data = {
            "operation": "stt",
            "model_source": model_source,
            "model_ref": model_ref,
            "language": language,
        }
        # httpx's multipart writer (_multipart.py:render_data) only
        # handles str/bytes natively; bytearray/memoryview fall through
        # to its `.read()` branch and AttributeError. Coerce to bytes
        # here so all three input types work — loses zero-copy for
        # memoryview but the alternative is no support at all.
        if isinstance(audio, (bytearray, memoryview)):
            audio = bytes(audio)
        files = {"audio": ("audio.bin", audio, content_type)}
        try:
            resp = await self._http.post(
                url, params=params, headers=headers, data=data, files=files,
            )
        except httpx.RequestError as exc:
            raise LLMHttpError(f"_submit_stt_bytes transport failure: {exc}") from exc
        if resp.status_code >= 400:
            await self._raise_http_error(resp)
        try:
            return SubmitJobResponse.model_validate(resp.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMDecodeError(f"_submit_stt_bytes response decode failed: {exc}") from exc

    # ── Image generation (Phase 5c-α) ────────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        *,
        model_source: ModelSource,
        model_ref: str,
        size: str | None = None,
        n: int | None = None,
        response_format: Literal["url", "b64_json"] = "url",
        quality: str | None = None,
        style: Literal["vivid", "natural"] | None = None,
        background: Literal["auto", "transparent", "opaque"] | None = None,
        user_id: str | None = None,
        poll_interval_s: float = 0.5,
        max_poll_interval_s: float = 10.0,
    ) -> ImageGenResult:
        """Phase 5c-α — submit image-gen job, wait for terminal, return
        decoded result.

        Reuses submit_job + wait_terminal (same backoff, same cancellation,
        same transient-retry semantics as transcribe()).
        transient_retry_budget is fixed at 0 — image generation is
        expensive (real $ + GPU minutes); a silent re-run on transient
        failure could double-charge BYOK.

        Polling defaults are slower than transcribe (0.5s initial, 10s
        max) because image generation runs longer (ComfyUI multi-step
        workflows can take 60-120s; 4-image batches up to 5-8 min).

        Args:
            prompt: Text description of the desired image (1..32000 chars).
            model_source: 'user_model' or 'platform_model'.
            model_ref: UUID-shaped model reference.
            size: Image dimensions, e.g. "1024x1024". `None` → upstream
                default (typically "1024x1024" for DALL-E).
            n: Number of images (1..4). `None` → upstream default (varies
                by backend — DALL-E-3 defaults to 1, DALL-E-2 defaults
                to 1 but accepts up to 10, local-image-generator-service
                varies). Pass an explicit int to override; gateway caps
                at 4.
            response_format: "url" (default) or "b64_json". URL mode
                returns short-lifetime URLs (caller must fetch
                immediately); b64_json embeds bytes inline.
            quality: "standard" | "hd" | "high" | "medium" | "low";
                model-dependent. `None` → omit.
            style: "vivid" | "natural" (DALL-E-3 only). `None` → omit.
            background: "auto" | "transparent" | "opaque" (gpt-image-1
                only). `None` → omit.
            user_id: Per-call override (mirrors submit_job).
            poll_interval_s: Initial polling delay.
            max_poll_interval_s: Max polling delay after exponential
                backoff.

        Returns:
            `ImageGenResult` with 1..n `data` entries.

        Raises:
            LLMInvalidRequest: malformed model_ref, empty prompt, or
                handler-/adapter-side validation failure.
            LLMImageContentPolicy: upstream rejected the prompt by
                content-policy / safety rules. Caller's UX should
                suggest rephrasing.
            LLMImageGenerationFailed: upstream image generation failed
                for a non-policy reason (model loading, ambiguous
                backend error). Caller MAY retry once.
            LLMError subclass keyed by job.error.code on other failures.
            LLMJobTerminal: status=cancelled.
        """
        try:
            UUID(model_ref)
        except (TypeError, ValueError) as exc:
            raise LLMInvalidRequest(
                f"model_ref must be UUID-shaped, got {model_ref!r}",
            ) from exc

        if not prompt or not prompt.strip():
            raise LLMInvalidRequest("prompt must be non-empty")

        input_payload: dict[str, Any] = {"prompt": prompt}
        if size is not None:
            input_payload["size"] = size
        # /review-impl(BUILD) MED#1 — `if n is not None`, NOT `if n != 1`.
        # The prior `n != 1` check silently dropped explicit n=1 requests,
        # falling through to upstream's default (which may be >1 for some
        # backends), surprising callers asking for exactly one image.
        # Explicit values pass through; omission means "use upstream default".
        if n is not None:
            input_payload["n"] = n
        if response_format != "url":
            input_payload["response_format"] = response_format
        if quality is not None:
            input_payload["quality"] = quality
        if style is not None:
            input_payload["style"] = style
        if background is not None:
            input_payload["background"] = background

        request = SubmitJobRequest(
            operation="image_gen",
            model_source=model_source,
            model_ref=model_ref,
            input=input_payload,
        )
        submitted = await self.submit_job(request, user_id=user_id)
        job = await self.wait_terminal(
            submitted.job_id,
            user_id=user_id,
            poll_interval_s=poll_interval_s,
            max_poll_interval_s=max_poll_interval_s,
            transient_retry_budget=0,
        )
        if job.status == "completed":
            if job.result is None:
                raise LLMUpstreamError(
                    "image_gen job completed but result is empty",
                    status_code=None,
                    body="",
                )
            return ImageGenResult.model_validate(job.result)
        if job.status == "cancelled":
            raise LLMJobTerminal(f"image_gen job {submitted.job_id} cancelled")
        # status == "failed"
        if job.error is None:
            raise LLMUpstreamError(
                f"image_gen job {submitted.job_id} failed without error body",
                status_code=None,
                body="",
            )
        raise from_code(job.error.code, job.error.message)

    async def cancel_job(self, job_id: str | UUID, *, user_id: str | None = None) -> None:
        """Cancel an in-flight job. Idempotent: 204 (cancel accepted) and
        409 (already terminal) both return None — caller's desired state
        (job not running) is true in both cases.

        Raises LLMJobNotFound on 404 so callers can distinguish 'never
        existed' from 'already done'.

        `user_id` per-call override (see submit_job).
        """
        job_id_str = str(job_id)
        url, params, headers = self._jobs_endpoint("cancel", job_id=job_id_str, user_id=user_id)
        try:
            resp = await self._http.delete(url, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise LLMHttpError(f"cancel_job transport failure: {exc}") from exc
        if resp.status_code in (204, 409):
            return
        if resp.status_code == 404:
            raise LLMJobNotFound(f"job {job_id_str} not found", status_code=404)
        await self._raise_http_error(resp)

    def _jobs_endpoint(
        self,
        kind: Literal["submit", "get", "cancel"],
        *,
        job_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        """Resolve URL + params + headers for jobs endpoints honoring
        auth_mode (jwt vs internal). Internal-token paths add user_id
        query param per openapi spec.

        `user_id` per-call override > constructor default. Required for
        internal auth when constructor user_id is None (multi-tenant).
        """
        if self._auth_mode == "jwt":
            base = f"{self._base_url}/v1/llm/jobs"
            headers = {"Authorization": f"Bearer {self._bearer_token}"}
            params: dict[str, str] = {}
        else:
            effective_user_id = user_id if user_id is not None else self._user_id
            if not effective_user_id:
                raise LLMInvalidRequest(
                    "internal auth_mode requires user_id (per-call or at construction)"
                )
            base = f"{self._base_url}/internal/llm/jobs"
            headers = {"X-Internal-Token": self._internal_token or ""}
            params = {"user_id": effective_user_id}

        if kind == "submit":
            return base, params, headers
        return f"{base}/{job_id}", params, headers

    # ── Internals ─────────────────────────────────────────────────────

    async def _iter_sse_events(self, resp: httpx.Response) -> AsyncIterator[StreamEvent]:
        """Parse the gateway's SSE wire format (`event: <name>\\ndata: <json>\\n\\n`)
        into typed StreamEvent instances."""
        current_event = ""
        async for line in resp.aiter_lines():
            if line == "":
                current_event = ""
                continue
            if line.startswith(":"):
                # SSE comment — keep-alive, ignore.
                continue
            if line.startswith("event:"):
                current_event = line[len("event:") :].strip()
                continue
            if line.startswith("data:"):
                data = line[len("data:") :].strip()
                if not data:
                    continue
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise LLMDecodeError(
                        f"gateway emitted non-JSON SSE data: {exc}",
                    ) from exc

                # The gateway always includes "event" inside the data
                # payload (matches the discriminator). If a producer ever
                # forgets, fall back to the SSE event-name line.
                if "event" not in parsed and current_event:
                    parsed["event"] = current_event

                yield self._dispatch_event(parsed)

    @staticmethod
    def _dispatch_event(parsed: dict) -> StreamEvent:
        """Build a typed StreamEvent from a parsed JSON payload."""
        kind = parsed.get("event")
        if kind == "token":
            return TokenEvent.model_validate(parsed)
        if kind == "reasoning":
            return ReasoningEvent.model_validate(parsed)
        if kind == "usage":
            return UsageEvent.model_validate(parsed)
        if kind == "done":
            return DoneEvent.model_validate(parsed)
        if kind == "error":
            return ErrorEvent.model_validate(parsed)
        if kind == "audio-chunk":
            # Phase 5a — TTS streamed audio frame.
            return AudioChunkEvent.model_validate(parsed)
        raise LLMDecodeError(f"unknown SSE event kind: {kind!r}")

    async def _raise_http_error(self, resp: httpx.Response) -> None:
        # Body is already partially consumed if streaming response, but
        # a 4xx returned BEFORE the SSE prelude is buffered — we can read
        # it normally.
        body_bytes = await resp.aread()
        try:
            body_json = json.loads(body_bytes.decode("utf-8"))
            code = body_json.get("code", "LLM_ERROR")
            message = body_json.get("message", "")
            retry_after_s = body_json.get("retry_after_s")
        except (UnicodeDecodeError, json.JSONDecodeError):
            code = "LLM_ERROR"
            message = body_bytes.decode("utf-8", errors="replace")[:500]
            retry_after_s = None

        # Phase 5b /review-impl HIGH#3 — consult from_code() for codes
        # outside the status-code → exception map. Audio-specific codes
        # (LLM_AUDIO_TOO_LARGE on 413, LLM_AUDIO_FETCH_FAILED, etc.) need
        # their dedicated exception classes, not a generic LLMInvalidRequest
        # fall-through. from_code is the single source of truth for
        # code→class mapping shared with stream-time errors.
        if resp.status_code == 401:
            raise LLMAuthFailed(message, code=code, status_code=resp.status_code)
        if resp.status_code == 402:
            raise LLMQuotaExceeded(message, code=code, status_code=resp.status_code)
        if resp.status_code == 404:
            raise LLMModelNotFound(message, code=code, status_code=resp.status_code)
        if resp.status_code == 429:
            raise LLMRateLimited(
                message, retry_after_s=retry_after_s, status_code=resp.status_code
            )
        if resp.status_code in (502, 503, 504):
            raise LLMUpstreamError(message, code=code, status_code=resp.status_code)
        if 400 <= resp.status_code < 500:
            # Prefer the body's code over the status-bucket fallback so
            # LLM_AUDIO_TOO_LARGE (413) and similar surface as their
            # dedicated classes.
            mapped = from_code(code, message, status_code=resp.status_code)
            # Defensive: if from_code returned the generic base, fall
            # back to LLMInvalidRequest so 4xx still carries the right
            # "this is a caller problem" semantic for the type system.
            if type(mapped) is LLMError:
                raise LLMInvalidRequest(message, code=code, status_code=resp.status_code)
            raise mapped
        raise LLMError(message, code=code, status_code=resp.status_code)
