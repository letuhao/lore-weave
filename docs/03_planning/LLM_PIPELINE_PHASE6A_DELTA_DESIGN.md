# LLM Pipeline Phase 6a-δ — Streaming Spend Guardrail

> Status: DESIGN. Extends Phase 6a Subsystem A
> ([LLM_PIPELINE_PHASE6A_DESIGN.md](./LLM_PIPELINE_PHASE6A_DESIGN.md)) to the
> streaming surface. Closes `D-PHASE6A-STREAMING-GUARDRAIL`.

## 1. Scope

Phase 6a guarded the **job path** (`POST /v1/llm/jobs`). `POST /v1/llm/stream`
— interactive chat + tts — currently bypasses the spend guardrail entirely. A
user can run unbounded streaming chat against their BYOK provider with no
budget check. 6a-δ closes that hole.

In scope: pre-flight reservation + 402 on `/v1/llm/stream` (chat + tts), a
mid-stream running-tally hard-abort for chat, terminal reconciliation.
`/internal/llm/stream` shares the same handler so it is covered too.

Out of scope: Subsystem B (6a-β), the FE (6a-γ).

## 2. CLARIFY decisions (settled with the user)

1. **Reserve, don't just check.** A stream reuses the 6a
   reserve/reconcile/release machinery: it is allocated a synthetic `job_id`
   (`uuid.NewV7`), reserves its worst-case estimate via `GuardrailClient`, and
   reconciles at stream end. Concurrent streams each hold their own
   reservation — no concurrency hole. The `token_reservations` row is
   identical in shape to a job's; the sweeper covers a crashed stream.
2. **Implement the mid-stream hard-abort now** (ADR §3.4). Even though the
   reservation already caps budget exposure, the running tally + abort is the
   defense-in-depth against a provider that ignores `max_tokens`.

## 3. Design

### 3.1 Where the pre-flight sits

`doLlmStream` order today: decode → validate `operation` → resolve creds →
`ResolveAdapter` → flusher check → **SSE prelude (`WriteHeader(200)`)** →
branch to `streamChat` / `streamTts`.

The guardrail pre-flight is inserted **after the flusher check, immediately
before the SSE prelude** — the last thing that can still return an HTTP
status. Once `WriteHeader(200)` ships, a 402 is impossible; every rejection
(404 unknown model, 402 unpriced / over-budget) must land before it.

Placing it last-before-prelude also means: once the reservation is taken, the
handler *always* proceeds to stream and *always* settles — there is no
code path between reserve and stream that can fail and orphan the hold.

### 3.2 Pricing lookup

The inline credential-resolution query in `doLlmStream` already `SELECT`s from
`user_models` / `platform_models`. Add the `pricing` column to both branches
(it exists since the 6a migration) and decode it into `billing.Pricing` — no
extra round-trip.

### 3.3 The estimate (worst case)

Reuse `s.estimator.EstimateUSD`:

- **chat** — `EstimateUSD("chat", inputMap, pricing, 1)`. `inputMap` is the
  adapter input (`messages`, `temperature`, `max_tokens`, `tools`). Worst-case
  output = the request `max_tokens`, or `MAX_OUTPUT_TOKENS_DEFAULT` when
  omitted (the estimator's `chatOutputTokens` already does this). `nchunks=1`
  — a stream is never chunked.
- **tts** — `EstimateUSD("tts", inputMap, pricing, 1)`. tts cost is
  `per_kchar × chars`, and the text is fully known at submit time, so the
  estimate is **exact**, not a worst case. No running tally is needed for tts.

`ErrUnpriced` → `402 LLM_QUOTA_EXCEEDED` ("model pricing not configured").

### 3.4 Reserve

`jobID := uuid.NewV7()` (synthetic — there is no `llm_jobs` row for a stream).
`s.guardrail.Reserve(ctx, userID, jobID, estimate)`:

- `200` → carry `reservationID` **and the available-budget figures** into the
  stream (see §3.5 — the abort threshold needs them).
- `402` (insufficient) → `writeBudget402` before the SSE prelude.
- transport error → `503` fail-closed (mirrors `doSubmitJob`).

No `llm_jobs` row is created — `token_reservations.job_id` is just a UUID
column with no cross-DB FK (design 6a §3.5), so a synthetic id is fine. A
crashed stream's hold is swept after `RESERVATION_TTL` like any other.

**`reserve` 200 must return availability.** Today `guardrailReserve` returns
`daily_available` / `monthly_available` **only on the 402** path. The
streaming abort threshold (§3.5) needs them on success too. Change: the `200`
body also carries `daily_available` / `monthly_available`, computed at the
same step-5 point as the 402 (`limit − spent − reserved`, *before* this
reservation's bump) — i.e. how much this caller may still spend in total.
`billing.ReserveResult` already has the two fields; populate them on the 200
branch. The job path ignores them — no behavior change there.

### 3.5 The running tally + hard-abort (chat only)

A `streamGuard` value threads through `streamChat`:

```
type streamGuard struct {
    guardrail      *billing.GuardrailClient
    reservationID  uuid.UUID
    pricing        billing.Pricing
    abortUSD       float64   // hard-abort threshold (see below)
    inputCostUSD   float64   // fixed: estimated input tokens × input price
    outChars       int       // accumulated content+reasoning delta chars
    outNonASCII    int       // for the script-aware token estimate
    finalUsage     *provider.StreamChunk // last StreamChunkUsage seen, if any
}
```

**The abort threshold is the user's available budget, NOT the reservation.**
If the stream aborted at its reserved estimate, every chat stream that omits
`max_tokens` would be silently truncated at `MAX_OUTPUT_TOKENS_DEFAULT` worth
of output — a bad UX regression. The job path already *tolerates* an actual
that overshoots the estimate (6a §3.4: `*_spent` may surpass `*_limit` by one
job's overshoot, reconciled at the real figure). Streaming does the same: the
estimate sizes the *reservation*; the hard-abort exists only to stop a
genuine **runaway** — a provider streaming without end — before the user's
wallet actually goes negative.

So `abortUSD = min(daily_available, monthly_available)` from the `reserve` 200
response (§3.4) — the total this caller may still spend. A stream may consume
up to that; beyond it the wallet would go negative, so abort.

`observe(chunk)` is called for every chunk the adapter emits, **before** it is
written to the wire:

- `StreamChunkToken` / `StreamChunkReasoning` → accumulate `Delta` chars
  (reasoning tokens bill as output). Recompute running USD = `inputCostUSD +
  estimateOutputTokens(outChars, outNonASCII) × outputPricePerTok`. If running
  USD `> abortUSD` → return `abort=true`.
- `StreamChunkUsage` → store as `finalUsage` (authoritative counts for
  reconcile).
- other kinds → no-op.

On `abort=true` the emit wrapper stops: it emits one
`event: error` SSE frame (`LLM_QUOTA_EXCEEDED`, "stream aborted — budget
exceeded") and returns an error so `adapter.Stream` short-circuits and closes
the upstream connection. The token estimate reuses the 6a estimator's
script-aware divisor (a package-level helper extracted for reuse, or
`Estimator` exposes it) so CJK output is not under-counted.

### 3.6 Reconcile (stream end)

`settle(ctx)` runs unconditionally after the adapter returns (deferred, so it
runs on success, upstream error, abort, *and* client disconnect):

- **chat** — if `finalUsage != nil`, `actual = (InputTokens + OutputTokens +
  ReasoningTokens) / 1e6 × …` from the authoritative usage chunk. Else
  `actual = inputCostUSD + delta-estimated output cost` (the running tally).
  `Reconcile(reservationID, &actual)`.
- **tts** — `Reconcile(reservationID, nil)` → usage-billing charges the
  reservation's stored estimate, which is exact for tts.

There is no release path: the reservation is taken last-before-stream, so
every reserved stream reaches `settle`. A client disconnect mid-chat-stream
reconciles the partial tally — the user consumed those tokens. A tts
disconnect still reconciles the full estimate: the provider was asked to
synthesize the whole text regardless of how much audio the client received.

### 3.7 Files (~8)

| File | Change |
|------|--------|
| `docs/03_planning/LLM_PIPELINE_PHASE6A_DELTA_DESIGN.md` | NEW (this doc) |
| provider-registry `internal/api/stream_billing.go` | NEW — `streamGuard`, `preflightStream`, `observe`, `settle` |
| provider-registry `internal/api/stream_handler.go` | pricing in cred query; pre-flight call; guard threaded into `streamChat`/`streamTts`; emit wraps `observe`; deferred `settle` |
| provider-registry `internal/billing/estimate.go` | export the script-aware token helper for the tally (`EstimateOutputTokens` or similar) |
| provider-registry `internal/billing/client.go` | `Reserve` populates `ReserveResult.Daily/MonthlyAvailable` on the 200 branch, not only 402 |
| usage-billing `internal/api/guardrail.go` | `guardrailReserve` 200 body returns `daily_available` / `monthly_available` |
| usage-billing `internal/api/guardrail_test.go` | assert the 200 body carries the availability figures |
| provider-registry `internal/api/stream_billing_test.go` | NEW — tally/abort unit tests, estimate selection |
| provider-registry `internal/api/stream_guardrail_integration_test.go` | NEW — DB-integration: 404 / 402-unpriced / 402-over-budget / happy + reservation, mirrors `jobs_guardrail_integration_test.go` |
| provider-registry `internal/api/stream_handler_test.go` | MOD — existing tests adjusted for the pre-flight |
| `contracts/api/llm-gateway/v1/openapi.yaml` | + `402` on `/v1/llm/stream` + `/internal/llm/stream`; document the guardrail |

## 4. Test plan

- **tally/abort (unit)** — `observe` accumulates chars; running USD crosses
  `estimateUSD` → `abort=true`; a CJK-heavy delta stream aborts at the right
  point (not 4× late); `StreamChunkUsage` captured as `finalUsage`.
- **estimate selection** — chat uses `max_tokens` / default ceiling; tts is
  exact.
- **reconcile** — chat with a final usage chunk → authoritative actual; chat
  without → tally estimate; tts → stored estimate (nil actual); disconnect →
  partial tally still reconciled.
- **doLlmStream (DB-integration)** — unknown model → 404; unpriced → 402;
  over-budget → 402, all **before** the SSE prelude (assert no `event:` frame
  in the body); happy → 200 + SSE + a `token_reservations` row exists.
- **abort end-to-end** — a stub adapter that emits more than `max_tokens`
  worth of deltas → the SSE body ends with an `LLM_QUOTA_EXCEEDED` error
  frame.

## 5. Build order

1. usage-billing — `guardrailReserve` 200 body returns `daily_available` /
   `monthly_available`; `guardrail_test.go` asserts it.
2. provider-registry `billing` — `client.go` `Reserve` populates
   `ReserveResult` availability on the 200 branch (+ test); `estimate.go`
   exports the script-aware output-token helper (+ test).
3. provider-registry — `stream_billing.go` NEW: `streamGuard`,
   `preflightStream`, `observe`, `settle` + `stream_billing_test.go`.
4. provider-registry — `stream_handler.go`: `pricing` in the cred query;
   `preflightStream` call before the SSE prelude; guard threaded into
   `streamChat` (tally) + `streamTts`; deferred `settle`.
5. `openapi.yaml` — `402` on `/v1/llm/stream` + `/internal/llm/stream`.
6. `stream_guardrail_integration_test.go` NEW + fix `stream_handler_test.go`.
7. VERIFY → REVIEW → QC → /review-impl → SESSION → COMMIT.

## 6. Deferrals

- `D-PHASE6A-DELTA-LIVE-SMOKE` — manual: a real over-budget stream returns
  402 before the prelude; a real runaway stream aborts mid-flight.
