# LLM Pipeline Phase 6b — Job-Level Retry Policy

> Status: DESIGN. Refactor-plan §6 cycle 6b. Provider-registry only.

## 1. Scope

The worker's transient-error retry is today: a **fixed 1s** backoff, a
**budget of 1** (one retry), **shared across all chunks** of a chunked job,
and **only on the streaming path** — image/video/audio-gen call the provider
exactly once. 6b makes retry consistent and robust:

1. **Exponential backoff** — `1s, 2s, 4s, …` capped, replacing the fixed 1s.
2. **Per-chunk independent budget** — each chunk of a chunked job retries on
   its own budget (today one shared budget=1 is drained by the first chunk to
   fail, leaving none for the rest).
3. **Media retry** — `image_gen` / `video_gen` / `stt` / `audio_gen` gain the
   same transient-retry the streaming path has.
4. **Config-driven budget** — `JOB_MAX_RETRIES` (default 3), no hardcoded `1`.

## 2. CLARIFY decisions

1. **Media retries on ALL transient errors** (429 + 5xx + timeout) — same
   policy as streaming. Accepts that a retry after an *ambiguous* timeout can
   double-generate (double-charge) an expensive image/video call — the user
   chose success-rate over the conservative 429-only option.
2. **`JOB_MAX_RETRIES`** is a config env (default 3); the backoff base/cap
   stay as documented code constants.

## 3. Design

### 3.1 `retryTransient` — the one retry primitive

NEW in `internal/jobs/retry.go`:

```go
func retryTransient(ctx context.Context, maxRetries int,
                    logger *slog.Logger, op func() error) error
```

- Runs `op()`. Returns `nil` on success, the error immediately on a
  **non-transient** error (`provider.IsTransientUpstreamError` is false).
- On a transient error with retries left: sleep, then re-run. Up to
  `maxRetries` retries (so `maxRetries+1` total attempts).
- **Backoff:** attempt *n*'s wait = `min(retryBaseS · 2ⁿ, retryCapS)` —
  `retryBaseS = 1s`, `retryCapS = 30s` (code consts). `provider.RetryAfter(err)`
  **overrides** the computed wait when the error carries a `Retry-After`
  (honor the server). The sleep is `select`-cancellable on `ctx.Done()`.
- Budget exhausted → returns the last transient error.

This is a generic `op func() error` so it wraps **both** the streaming call
and the media `adapter.Generate*` calls (their differing return shapes are
captured in the closure).

### 3.2 Streaming path

`streamWithRetry` is reimplemented as a one-liner over `retryTransient`
(`op` = the `adapter.Stream` call). **`streamWithBudget` is deleted** — its
only reason for existing was the shared `*budget` pointer for cross-chunk
budget; the per-chunk-independent decision removes that need.

### 3.3 Chunked path

`processChunks` today declares `budget := 1` *before* the chunk loop and
shares it. 6b: each chunk calls `retryTransient(ctx, w.maxRetries, …)` — an
independent budget per chunk. One chunk's transient failure no longer starves
the rest. (A pathological N-chunk job is still bounded: N·maxRetries retries
worst case, each capped-backoff, and if every chunk fails the upstream is down
and the job fails anyway.)

**Aggregator reset on a chunked retry.** `agg.StartChunk(i)` resets the
aggregator's per-chunk buffer. Today `processChunks` calls it *once* before
the stream — so a retry after a partial stream would double-accumulate that
chunk's content. 6b moves `StartChunk(i)` *into* the retry op, so every
attempt starts the chunk's buffer fresh; `EndChunk(i)` runs once after the
retry succeeds. The chunked retry is therefore correct-by-construction.

> **Unchunked path — pre-existing limitation.** The single-call path streams
> straight into the aggregator with no `StartChunk`. A retry after a *partial*
> stream (a transient mid-stream drop) double-accumulates — this exists today
> in `streamWithBudget` and is unchanged by 6b. A proper fix means routing the
> unchunked call through `StartChunk(0)`/`EndChunk(0)`, which touches every
> aggregator's unchunked path — out of 6b's scope. Tracked as
> `D-PHASE6B-RETRY-AGG-RESET`.

### 3.4 Media paths

`runImageGenJob` / `runVideoGenJob` / the two `stt` Transcribe paths /
`runAudioGenJob` each wrap their single `adapter.Generate*` / `Transcribe`
call in `retryTransient(ctx, w.maxRetries, …)`. The output value is captured
by the closure. Error classification, finalize, and billing are unchanged —
only the call is now retried.

### 3.5 Config + wiring

- provider-registry `config.go` — `JobMaxRetries int`, env `JOB_MAX_RETRIES`,
  default `3` via the existing `getEnvInt` helper (strictly-positive).
- `Worker` gains a `maxRetries int` field; `NewWorker` gains the parameter;
  `server.go`'s `NewServer` passes `cfg.JobMaxRetries`.
- `infra/docker-compose.yml` — `JOB_MAX_RETRIES` (optional; default applies).

## 4. Files (~10)

| File | Change |
|------|--------|
| `docs/03_planning/LLM_PIPELINE_PHASE6B_DESIGN.md` | NEW (this doc) |
| provider-registry `internal/jobs/retry.go` | NEW — `retryTransient` |
| provider-registry `internal/jobs/retry_test.go` | NEW — backoff / cap / RetryAfter / non-transient / ctx-cancel / budget tests |
| provider-registry `internal/jobs/worker.go` | `streamWithRetry` via `retryTransient`; delete `streamWithBudget`; `processChunks` per-chunk budget; `Worker.maxRetries` + `NewWorker` param |
| provider-registry `internal/jobs/worker_image.go` | wrap `GenerateImage` |
| provider-registry `internal/jobs/worker_video.go` | wrap `GenerateVideo` |
| provider-registry `internal/jobs/worker_audio.go` | wrap `Transcribe` ×2 + `GenerateAudio` |
| provider-registry `internal/jobs/worker_test.go` (+ siblings) | update for the new signatures / per-chunk budget |
| provider-registry `internal/config/config.go` | `JOB_MAX_RETRIES` |
| provider-registry `internal/api/server.go` | `NewWorker` call passes `cfg.JobMaxRetries` |
| `infra/docker-compose.yml` | `JOB_MAX_RETRIES` env |

## 5. Test plan

- **`retryTransient`** — success first try (0 sleeps); transient-then-success;
  non-transient → immediate, no retry; budget exhausted → last error;
  exponential growth (assert the wait sequence via an injectable sleeper);
  cap applied; `provider.RetryAfter` overrides the computed wait;
  `ctx` cancelled mid-backoff → `ctx.Err()`.
- **chunked** — per-chunk independence: a 2-chunk job where chunk 1 transient-
  fails-then-succeeds and chunk 2 transient-fails-then-succeeds both complete
  (shared budget=1 would have failed chunk 2).
- **media** — `runImageGenJob` retries a transient error then succeeds;
  a non-transient fails immediately.
- The existing `TestStreamWithRetry_*` / `TestStreamWithBudget_*` are
  rewritten against `retryTransient`.

## 6. Deferrals

- `D-PHASE6B-MEDIA-DOUBLE-CHARGE` — a media retry after an ambiguous timeout
  can double-charge (CLARIFY-accepted). If provider cost telemetry later
  shows this biting, narrow media retry to 429-only.
- `D-PHASE6B-RETRY-AGG-RESET` — the unchunked single-call path
  double-accumulates into the aggregator on a retry after a partial stream
  (pre-existing; §3.3). Fix = route the unchunked call through
  `StartChunk(0)`/`EndChunk(0)`, which touches every aggregator.
