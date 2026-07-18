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
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import ValidationError

from loreweave_llm.attribution import merge_attribution_into_job_meta
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
    AudioGenResult,
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
    ToolCallEvent,
    TtsInput,
    TtsStreamRequest,
    UsageEvent,
    VideoGenResult,
)

logger = logging.getLogger(__name__)

AuthMode = Literal["jwt", "internal"]

# Default per-event read timeout — only the IDLE wait for the next SSE
# frame, NOT a wall-clock cap on the whole stream. The whole-stream
# timeout is None (unbounded) by design (P1 — streaming chat must have
# no wall-clock timeout). A value <= 0 DISABLES the idle cap too (read=None,
# fully unbounded) — for streaming a slow reasoning model that may think
# silently (no frames) for minutes before emitting a token; an idle cap would
# ReadTimeout mid-thought. Callers that want a cap pass a positive value.
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
        event_redis_url: str | None = None,
        event_stream: str = "loreweave:events:llm_job_terminal",
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

        # Whole-stream timeout = None (unbounded). Connect timeout = 5s (fail fast
        # if the gateway is unreachable). Per-read (idle) timeout = idle_read_timeout_s
        # (longest gap between SSE frames before we treat the stream as stalled). A
        # value <= 0 sets read=None (no idle cap at all) so a slow reasoning model
        # thinking silently for minutes is not cut off mid-thought.
        read_timeout: float | None = (
            idle_read_timeout_s if idle_read_timeout_s and idle_read_timeout_s > 0 else None
        )
        timeout = httpx.Timeout(None, connect=5.0, read=read_timeout)
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

        # LLM re-arch Phase 1 (Commit 2) — optional event-driven resume source.
        # When event_redis_url is set, wait_terminal becomes an
        # event-interruptible poll: it blocks on an XREAD of the terminal stream
        # between polls (woken the instant the job's terminal event lands) and
        # falls back to the poll on any Redis fault or a missed event. None ⇒
        # today's pure-poll behaviour (zero caller impact; services opt in in
        # Phase 2). The redis client is created lazily on first use so the SDK
        # doesn't hard-require redis unless this path is exercised.
        self._event_redis_url = event_redis_url
        self._event_stream = event_stream
        self._event_redis: Any | None = None

    async def aclose(self) -> None:
        if self._event_redis is not None:
            try:
                await self._event_redis.aclose()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        if self._http.is_closed:
            return
        await self._http.aclose()

    def _ensure_event_redis(self) -> Any | None:
        """Lazily build the terminal-event Redis client. Returns None (→ pure
        poll) when no event source is configured or redis isn't importable."""
        if self._event_redis_url is None:
            return None
        if self._event_redis is None:
            try:
                import redis.asyncio as _aioredis  # lazy: optional dependency
            except Exception:  # noqa: BLE001
                logger.warning("loreweave_llm: redis not importable — event resume disabled, polling")
                self._event_redis_url = None
                return None
            self._event_redis = _aioredis.from_url(self._event_redis_url)
        return self._event_redis

    async def _wait_terminal_event(self, job_id: str, last_id: str, timeout_s: float) -> tuple[bool, str]:
        """Block up to timeout_s on an XREAD of the terminal stream. Returns
        (woke_for_this_job, new_last_id). Degrades to asyncio.sleep on any Redis
        fault — a missed event is then caught by the next poll (defense in depth,
        mirrors worker-ai wake.py). The stream is fanned out (no consumer group):
        every waiter sees every terminal event and filters by job_id locally."""
        r = self._ensure_event_redis()
        if r is None:
            await asyncio.sleep(timeout_s)
            return False, last_id
        try:
            resp = await r.xread({self._event_stream: last_id}, block=max(1, int(timeout_s * 1000)), count=50)
        except Exception:  # noqa: BLE001 — degrade to sleep on any Redis fault
            logger.warning("loreweave_llm: terminal XREAD failed — polling", exc_info=True)
            await asyncio.sleep(timeout_s)
            return False, last_id
        woke = False
        new_last = last_id
        for _stream, entries in resp or []:
            for entry_id, fields in entries:
                new_last = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
                jid = fields.get(b"job_id") or fields.get("job_id")
                if jid is not None:
                    jid = jid.decode() if isinstance(jid, bytes) else str(jid)
                if jid == job_id:
                    woke = True
        return woke, new_last

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

        # P4/Wave-C slice D — carrier bridge. A public MCP-key call lost the
        # X-Mcp-Key-Id / cap headers on the hop into us; the contextvar set at the
        # tool handler is the only surviving signal. Fold it into job_meta so
        # provider-registry can per-key-cap (H-K) + attribute the spend (H-C).
        merged_meta = merge_attribution_into_job_meta(request.job_meta)
        if merged_meta is not request.job_meta:
            request = request.model_copy(update={"job_meta": merged_meta})

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
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> Job:
        """Poll get_job until status ∈ {completed, failed, cancelled}.

        Exponential backoff between polls (clamped to max_poll_interval_s).
        NO wall-clock timeout — polling continues until terminal or
        repeated HTTP failure.

        bug #34 — immediate cancel: ``cancel_check`` is an optional async
        predicate the caller passes to mean "is my PARENT job cancelled?".
        Polled once per loop iteration; the first time it returns True the SDK
        issues DELETE /v1/llm/jobs/{id} (``cancel_job``), which aborts the
        in-flight provider call upstream so token spend stops NOW instead of
        running to natural completion. The next get_job then returns
        status=cancelled and we return it — the SAME terminal outcome a
        UI-driven DELETE produces (see "Cancel-race" below), so callers need
        no new handling. A cancel_check fault never breaks the wait (degrades
        to a normal poll); a cancel_job fault is retried on the next poll.

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
        # "$" = only events that arrive AFTER we start reading; the immediate
        # get_job below catches an already-terminal job, and the poll backstops
        # any missed event, so there's no submit↔read gap to worry about.
        last_id = "$"
        event_driven = self._event_redis_url is not None
        cancel_requested = False
        while True:
            # bug #34 — immediate cancel: abort the in-flight provider call the
            # moment the caller's parent job is cancelled, so we don't poll a
            # token-burning call to completion. DELETE once on first fire; a fault
            # in either the check or the DELETE must not break the wait.
            if cancel_check is not None and not cancel_requested:
                fire = False
                try:
                    fire = await cancel_check()
                except Exception:  # noqa: BLE001 — a cancel_check fault degrades to normal poll
                    logger.warning(
                        "loreweave_llm: cancel_check raised for job %s — ignoring", job_id_str,
                        exc_info=True,
                    )
                if fire:
                    try:
                        await self.cancel_job(job_id_str, user_id=user_id)
                        cancel_requested = True  # DELETE accepted — just poll for the cancelled terminal
                    except Exception:  # noqa: BLE001 — retry the DELETE on the next poll
                        logger.warning(
                            "loreweave_llm: cancel_job during wait failed for job %s — will retry",
                            job_id_str, exc_info=True,
                        )
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

            if event_driven:
                # Block on the terminal stream; wake the instant THIS job's event
                # lands (poll immediately) or on timeout (fallback poll). Degrades
                # to sleep on a Redis fault.
                woke, last_id = await self._wait_terminal_event(job_id_str, last_id, interval)
                if not woke:
                    interval = min(interval * poll_backoff, max_poll_interval_s)
            else:
                await asyncio.sleep(interval)
                interval = min(interval * poll_backoff, max_poll_interval_s)

    async def await_job_event(
        self,
        job_id: str | UUID,
        *,
        user_id: str | None = None,
        timeout_s: float | None = None,
    ) -> Job:
        """Wait for a job's terminal event, with an optional overall deadline.

        Explicit event-resume API (LLM re-arch Phase 1 §5.4) for callers that
        prefer "submit then await the event" + a wall-clock cap over the
        unbounded ``wait_terminal``. Event-driven when ``event_redis_url`` is
        configured (XREAD wakes the wait the instant the terminal event lands),
        poll-fallback otherwise — so it's correct with or without a broker.
        Raises ``asyncio.TimeoutError`` if ``timeout_s`` elapses first.
        """
        coro = self.wait_terminal(job_id, user_id=user_id)
        if timeout_s is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=timeout_s)

    async def submit_and_await_event(
        self,
        request: SubmitJobRequest,
        *,
        user_id: str | None = None,
        timeout_s: float | None = None,
    ) -> Job:
        """Submit a job and await its terminal event. The coroutine-releasing
        win (submit → persist job_id → return → resume in a separate consumer)
        is the caller's to take; this convenience binds submit + await for the
        common in-line case while still resuming on the event, not a tight poll.
        """
        resp = await self.submit_job(request, user_id=user_id)
        return await self.await_job_event(resp.job_id, user_id=user_id, timeout_s=timeout_s)

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

    # ── Video generation (Phase 5d) ──────────────────────────────────

    async def generate_video(
        self,
        prompt: str,
        *,
        model_source: ModelSource,
        model_ref: str,
        size: str | None = None,
        duration: int | None = None,
        response_format: Literal["url"] = "url",
        style: str | None = None,
        init_image: str | None = None,
        user_id: str | None = None,
        poll_interval_s: float = 1.0,
        max_poll_interval_s: float = 30.0,
    ) -> VideoGenResult:
        """Phase 5d — submit video-gen job, wait for terminal, return
        decoded result.

        Polling defaults slower than image (1s initial, 30s max) because
        video gen runs longer (ComfyUI Wan/LTX Video typically 5-15 min;
        longer durations push 20+ min).

        Note: `n` is intentionally NOT a parameter — Phase 5d locks to
        n=1. Multi-video support deferred to a follow-up if a caller
        surfaces a real need.

        Note: `response_format` is `Literal["url"]` only — Phase 5d
        rejects b64_json at handler with clear "impractical for video"
        hint (/review-impl(DESIGN) MED#3). b64-encoded video exceeds
        the 8MB MaxImageResponseBytes cap in practice.

        Path dispatch: when `init_image` is provided, gateway routes to
        the upstream image-to-video endpoint; otherwise text-to-video.
        Field name `init_image` (not `image`) matches local-image-generator-
        service's API per /review-impl(DESIGN) HIGH#1.

        SDK signature follows Phase 5c-α /review-impl(BUILD) MED#1
        learning — all optional fields use `None` sentinel with
        `is not None` wire-inclusion checks, so explicit caller values
        are never silently dropped.

        Args:
            prompt: Text description of the desired video (1..32000 chars).
            model_source: 'user_model' or 'platform_model'.
            model_ref: UUID-shaped model reference.
            size: Video dimensions, e.g. "1920x1080". `None` → upstream
                default.
            duration: Video duration in seconds (1..60). `None` → upstream
                default (≈5s typical).
            response_format: Always "url" for video (b64_json rejected).
            style: Optional style hint; `None` → omit.
            init_image: Base64-encoded image for image-to-video mode;
                `None` → text-to-video. Capped at 10MB on the wire.
            user_id: Per-call override (mirrors submit_job).
            poll_interval_s: Initial polling delay.
            max_poll_interval_s: Max polling delay after backoff.

        Returns:
            `VideoGenResult` with exactly 1 `data` entry containing the
            generated video URL.

        Raises:
            LLMInvalidRequest: malformed model_ref, empty prompt, or
                handler-/adapter-side validation failure.
            LLMVideoContentPolicy: upstream rejected the prompt by
                content-policy / safety rules.
            LLMVideoGenerationFailed: upstream video generation failed
                for a non-policy reason.
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
        if duration is not None:
            input_payload["duration"] = duration
        # response_format Literal narrows to "url"; only send when
        # explicitly set (omitting lets upstream pick its default).
        if response_format != "url":
            input_payload["response_format"] = response_format
        if style is not None:
            input_payload["style"] = style
        if init_image is not None:
            input_payload["init_image"] = init_image

        request = SubmitJobRequest(
            operation="video_gen",
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
                    "video_gen job completed but result is empty",
                    status_code=None,
                    body="",
                )
            return VideoGenResult.model_validate(job.result)
        if job.status == "cancelled":
            raise LLMJobTerminal(f"video_gen job {submitted.job_id} cancelled")
        # status == "failed"
        if job.error is None:
            raise LLMUpstreamError(
                f"video_gen job {submitted.job_id} failed without error body",
                status_code=None,
                body="",
            )
        raise from_code(job.error.code, job.error.message)

    # ── Audio generation (Phase 5e-β.2) ──────────────────────────────

    async def generate_audio(
        self,
        texts: list[str],
        *,
        model_source: ModelSource,
        model_ref: str,
        voice: str | None = None,
        speed: float | None = None,
        format: AudioFormat | None = None,
        response_format: Literal["b64_json", "url"] | None = None,
        user_id: str | None = None,
        poll_interval_s: float = 0.5,
        max_poll_interval_s: float = 10.0,
    ) -> AudioGenResult:
        """Phase 5e-β.2 — submit batch audio_gen job, wait for terminal,
        return decoded result.

        Distinct from `stream_tts()` (Phase 5a) which is streaming/realtime;
        this is batch/job-mode for stored audio (e.g. book chapter
        narration). Both use the same upstream (/v1/audio/speech) but
        different gateway operations.

        Polling defaults: 0.5s initial, 10s max, 1.5× backoff.
        transient_retry_budget fixed at 0 — TTS is char-billed; mid-batch
        retries could double-charge up to N × 4096 chars per call.
        Amplified vs generate_image's single-input risk
        (/review-impl(DESIGN) MED#10).

        /review-impl(DESIGN) HIGH#5 — optional fields use `None` sentinel;
        wire inclusion via `if X is not None` (NOT `if X != default`).
        Per memory `feedback_sdk_default_arg_dropped_from_wire` — explicit-
        equal-to-default values must reach the wire.

        Args:
            texts: 1..10 strings, each 1..4096 chars (OpenAI TTS limit;
                batch cap of 10 per /review-impl(DESIGN) MED#1).
            model_source: 'user_model' or 'platform_model'.
            model_ref: UUID-shaped model reference.
            voice: None ⇒ gateway/upstream default ('alloy' for OpenAI).
                Backend-specific.
            speed: None ⇒ default 1.0. Range 0.25..4.0.
            format: None ⇒ default 'mp3'.
            response_format: None ⇒ gateway default ('b64_json').
                'b64_json' inline; 'url' returns public MinIO URL (1d TTL).
            user_id: per-call override.
            poll_interval_s: initial poll delay.
            max_poll_interval_s: max poll delay after backoff.

        Returns:
            AudioGenResult with len(texts) data entries, order-preserving.

        Raises:
            LLMInvalidRequest: SDK pre-flight validation
                (empty texts, batch >10, per-text empty/oversize, malformed
                model_ref).
            LLMAudioGenerationFailed: upstream batch TTS failed.
            LLMError subclass keyed by job.error.code on other failures.
            LLMJobTerminal: status=cancelled.
        """
        try:
            UUID(model_ref)
        except (TypeError, ValueError) as exc:
            raise LLMInvalidRequest(
                f"model_ref must be UUID-shaped, got {model_ref!r}",
            ) from exc

        if not texts:
            raise LLMInvalidRequest("texts must be non-empty")
        if len(texts) > 10:
            raise LLMInvalidRequest(f"texts batch capped at 10 (got {len(texts)})")
        for i, t in enumerate(texts):
            if not isinstance(t, str):
                raise LLMInvalidRequest(f"texts[{i}] must be str (got {type(t).__name__})")
            if not t.strip():
                raise LLMInvalidRequest(f"texts[{i}] must not be empty/whitespace")
            if len(t) > 4096:
                raise LLMInvalidRequest(f"texts[{i}] exceeds 4096-char OpenAI TTS limit (got {len(t)})")

        input_payload: dict[str, Any] = {"texts": texts}
        # /review-impl(DESIGN) HIGH#5 — `is not None` checks preserve
        # explicit-equal-to-default caller intent.
        if voice is not None:
            input_payload["voice"] = voice
        if speed is not None:
            input_payload["speed"] = speed
        if format is not None:
            input_payload["format"] = format
        if response_format is not None:
            input_payload["response_format"] = response_format

        request = SubmitJobRequest(
            operation="audio_gen",
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
                    f"audio_gen job {submitted.job_id} completed but result is empty",
                    status_code=None,
                    body="",
                )
            return AudioGenResult.model_validate(job.result)
        if job.status == "cancelled":
            raise LLMJobTerminal(f"audio_gen job {submitted.job_id} cancelled")
        # status == "failed"
        if job.error is None:
            raise LLMUpstreamError(
                f"audio_gen job {submitted.job_id} failed without error body",
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
            try:
                return ErrorEvent.model_validate(parsed)
            except ValidationError:
                # D-ERROREVENT-MASKS-UPSTREAM — a producer that emits an error
                # event without the required `message` field (or any other
                # schema drift) must not crash the SSE consumer with an opaque,
                # unrelated pydantic ValidationError that hides the ACTUAL
                # upstream failure. Found live 2026-07-08: an LM Studio
                # tool-call-parser crash surfaced this way — the real cause
                # was only recoverable from LM Studio's own server logs,
                # not from this SDK's exception, because the ValidationError
                # itself became the visible error. Degrade to a best-effort
                # ErrorEvent carrying whatever fields ARE present instead.
                return ErrorEvent(
                    event="error",
                    code=str(parsed.get("code") or "LLM_ERROR"),
                    message=str(parsed.get("message") or json.dumps(parsed, ensure_ascii=False)),
                )
        if kind == "audio-chunk":
            # Phase 5a — TTS streamed audio frame.
            return AudioChunkEvent.model_validate(parsed)
        if kind == "tool_call":
            # Phase 0b — tool-call argument fragment.
            return ToolCallEvent.model_validate(parsed)
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
