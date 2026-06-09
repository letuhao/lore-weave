# S3a — per-provider governor + circuit-breaker (provider-registry)

> **Slice:** S3a of the Auto-Draft Factory (S3 decomposed). Parent: [`2026-06-08-auto-draft-factory-architecture-readiness.md`](2026-06-08-auto-draft-factory-architecture-readiness.md) (G5).
> **Size:** XL · **Mode:** v2.2 (no AMAW) · **PO (CLARIFY 2026-06-09):** decompose S3; this loom = S3a only.

Closes **G5** (the "#1 overnight risk": a provider outage at 2 a.m. fails thousands of chapters independently with no auto-pause, and nothing bounds concurrency against a single local GPU). S3b (backoff), S3c (campaign pause/claim/cancel), S3d (budget-pause, co-designed w/ S4) are follow-on looms.

---

## Scope (precise)

A **global per-provider-kind governor + circuit-breaker** in `provider-registry-service` (Go), wrapping the **jobs-worker** adapter calls — `processChunks` / `streamWithRetry` in `internal/jobs/worker.go` (the async batch path the factory drives via the SDK `submit_job`; the actual overnight risk). Keyed by `providerKind` (resolved via `CredResolver` before invocation).

- **Governor** = a Redis **concurrency limiter** (bounded in-flight per provider-kind). Cloud kinds (openai/anthropic/cohere/…): `cloud_max` (default e.g. 8). Local kinds (ollama/lm_studio): `1` (serialize the single GPU). Acquire-before-call, release-after. Crash-safe via a lease TTL (stale leases auto-expire so a dead worker never wedges a slot).
- **Circuit-breaker** = per-provider-kind rolling failure tracking (429/5xx via `provider.IsTransientUpstreamError`). `failures ≥ threshold` in window → **open** (fail-fast `LLM_CIRCUIT_OPEN`, don't hit the provider) for `cooldown`; then **half-open** (one probe); probe success → **closed**, failure → re-open. Self-protects (stops hammering a down provider). The campaign keys on repeated `LLM_CIRCUIT_OPEN` to pause in **S3c** — no cross-service event in S3a.

**Out of S3a:** interactive `stream_handler.go` governance (follow-on); media workers (audio/image/video) — wrap later; the breaker→campaign-pause orchestration (S3c).

---

## Design

New package `internal/ratelimit/`:

### `governor.go` — Redis concurrency limiter
A **sorted-set sliding-window** limiter, atomic via a Lua script (go-redis `redis.NewScript`):
- key `gov:conc:<kind>`; members = acquisition tokens, score = lease-expiry epoch-ms.
- **acquire** (Lua, atomic): `ZREMRANGEBYSCORE key 0 now` (prune stale leases) → `ZCARD` → if `< max`: `ZADD key (now+leaseMs) token` return 1, else return 0. Go wrapper polls (acquire→sleep→retry) up to `acquireTimeout`; returns a `release` closure (`ZREM key token`) or an error if it couldn't acquire in time.
- `max_for(kind)` is a **pure function** (`cloud_max`, or `1` for local kinds) — unit-tested.
- Lease TTL > max expected call duration; a crashed worker's slot frees when its lease expires (no permanent wedge). Lua atomicity → live-smoke (no miniredis in-repo).

### `breaker.go` — per-provider circuit-breaker
- **Pure decision** `decide(state, failures, openedAtMs, now, cfg) -> (newState, allow)` — the full state machine (closed/open/half_open) as a pure function, **exhaustively unit-tested**.
- Redis I/O (thin): `Allow(ctx, kind)` reads `breaker:<kind>:{state,failures,opened_at}`, applies `decide`, persists any transition; `Record(ctx, kind, success)` bumps/clears the failure counter (windowed via TTL) and flips state on threshold/probe. Minor races are acceptable (a breaker is a heuristic, not a correctness gate — a slightly-late open is fine), so no Lua needed here.

### `guard.go` — the wrapper used at the call site
`Guard(ctx, gov, brk, kind, call func() error) error`:
1. `brk.Allow(kind)` — if open → return `ErrCircuitOpen` (→ `LLM_CIRCUIT_OPEN`), never touch the provider.
2. `gov.Acquire(kind)` → `release` (deferred).
3. `err := call()`.
4. `brk.Record(kind, success = err==nil || !IsTransientUpstreamError(err))` — only transient/upstream failures count against the breaker (a user's bad-request 400 must not open it).
5. return err.

### Wiring (`worker.go`)
Thread `providerKind` into `processChunks`/`streamWithRetry`; wrap the existing `retryTransient(...)` body's `adapter.Stream(...)` in `Guard(...)`. The retry budget stays outside Guard, so a transient failure still retries (with the breaker counting each). `Worker` gains `gov`/`brk` fields (nil → no-op pass-through, keeping router/unit tests Redis-free). `classifyStreamErrorCode` maps `ErrCircuitOpen` → `LLM_CIRCUIT_OPEN`.

### Config / infra
`config.go`: `RedisURL` (REDIS_URL), `GovernorCloudMax`, `GovernorLeaseMs`, `GovernorAcquireTimeoutMs`, `BreakerThreshold`, `BreakerWindowS`, `BreakerCooldownS`. `cmd/.../main.go`: `redis.ParseURL`→`NewClient` (mirrors worker-infra), construct governor+breaker, pass to `NewWorker` (nil-tolerant if REDIS_URL unset → governance disabled, logged). `docker-compose.yml`: add `REDIS_URL: redis://redis:6379` to provider-registry. `go.mod`: + `github.com/redis/go-redis/v9 v9.7.3`.

---

## Test plan

- **breaker `decide` (pure):** closed→open at threshold; open rejects within cooldown; open→half_open after cooldown; half_open+success→closed; half_open+failure→open; below-threshold stays closed. *(the load-bearing logic — heaviest coverage)*
- **governor `max_for` (pure):** local kinds → 1; cloud kinds → cloud_max; unknown → cloud_max.
- **Guard:** breaker-open → ErrCircuitOpen, call not invoked, slot not acquired; success path acquires+releases+records success; transient failure records failure + propagates + releases; non-transient (400) does NOT count against breaker.
- **Worker nil-governance:** gov/brk nil → behaves exactly as today (no regression) — existing worker tests stay green.
- **classifyStreamErrorCode:** ErrCircuitOpen → LLM_CIRCUIT_OPEN.

## VERIFY

Go build + `go test ./...` for provider-registry. Single-service (provider-registry) — but Redis Lua/atomicity is **live-only** → `LIVE-SMOKE deferred to D-S3A-GOVERNOR-LIVE-SMOKE` (concurrency cap honoured under parallel load; breaker opens on induced 5xx + recovers). Pure decision logic + nil-governance no-regression covered by unit tests.

## Deferred

- `D-S3A-GOVERNOR-LIVE-SMOKE` — live: concurrency cap + breaker open/cooldown/recover under load.
- `D-S3A-INTERACTIVE-GOVERNANCE` — wrap `stream_handler.go` (interactive) + media workers; S3a covers the jobs path only.
- (carried) S3b backoff · S3c campaign pause/claim/cancel (+ breaker→pause) · S3d budget-pause (w/ S4).
