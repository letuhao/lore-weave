# FD-22 — Extraction worker push-notify (Redis wake-signal) + FD-5 docstring

> **Roadmap:** [feature-debt roadmap](2026-06-09-feature-debt-roadmap.md) Phase 1 FD-22 (+ FD-5 bundled). **Size:** L (cross-service knowledge↔worker-ai, Redis side-effect). **PO 2026-06-09:** build the push-notify (not just close the seam).

## Goal
Cut extraction-job pickup latency from ≤`poll_interval_s` (5s) to ~immediate, by having knowledge-service emit a Redis **wake signal** when a job starts, which the worker-ai poll loop blocks on. **Polling stays the source-of-truth** — the wake only shortens the sleep. Fully additive; degrades to today's pure-polling on any Redis fault.

## Design — wake-signal over polling (NOT a job-payload queue)

**Why wake-over-poll, not push-the-job:** the poll loop already claims+transitions jobs atomically (the existing race-safe mechanism). If we pushed job payloads the worker would need dedup vs the poll. Instead the wake is a *content-free interrupt*: "something changed, poll now". The poll cycle is unchanged → zero double-process risk, zero new idempotency surface.

**Producer (knowledge-service)** — mirror [`summary_enqueue.py`](../../services/knowledge-service/app/jobs/summary_enqueue.py):
- New `app/jobs/extraction_wake.py`: `EXTRACTION_WAKE_STREAM = "extraction.wake"`; `make_redis_extraction_wake(redis_url) -> ExtractionWakeFn`; XADD with `maxlen≈100, approximate=True` (it's a transient interrupt, not durable). Payload minimal: `job_id`, `project_id`, `epoch` (observability only — worker ignores body).
- `ExtractionWakeFn` Protocol so the route takes an injected fn (test passes a mock; prod wires redis-backed). Mirrors the summary-enqueue DI exactly.
- Wire into [`extraction.py`](../../services/knowledge-service/app/routers/public/extraction.py) start endpoint: **after** the job→running commit, `await wake_fn(...)` wrapped best-effort (try/except + log; NEVER fail the request — the job is already running, the wake is pure optimization).
- Settings: `extraction_wake_enabled: bool` (default true), reuse `redis_url`. Disabled or no redis_url → no-op fn.
- Replace the stale comment at extraction.py:366.

**Consumer (worker-ai)** — interruptible poll-wait:
- New `app/wake.py`: `async wait_for_wake_or_timeout(redis, stream, last_id, timeout_s) -> tuple[bool, str]`. `XREAD BLOCK <timeout_ms> STREAMS <stream> <last_id>`; init `last_id="$"` (new-only, no cold-start replay), then follow the tail by the max id returned (catches wakes that arrive during job processing). Returns `(woke, new_last_id)`.
- [`main.py`](../../services/worker-ai/app/main.py) `_job_poll_loop`: replace `await asyncio.sleep(poll_interval_s)` with the wait. woke → immediate re-poll; timeout → normal poll. The poll body (`poll_and_run`) is untouched.
- Degrade: `redis_url` empty OR any XREAD error → fall back to `asyncio.sleep(poll_interval_s)` (today's behavior). A Redis outage silently reverts to pure polling.
- Settings: `extraction_wake_enabled: bool`, `extraction_wake_stream` (= the producer's const), reuse `redis_url`.

**FD-5 (bundled, trivial):** rewrite the stale `full.py` docstring (lines 18-26 "Commit 1 scaffold scope / builder.py still raises NotImplementedError / K18.8→Commit 3") — verified false: `builder.py:63-64` dispatches `build_full_mode` on `extraction_enabled`, no NotImplementedError remains, full-mode is built+reachable.

## Reliability (production-ready properties)
| Failure | Behavior |
|---|---|
| Wake lost (Redis blip) | worker waits ≤poll_interval → still processes (graceful) |
| Wake duplicated | one extra poll, harmless (atomic claim) |
| N worker replicas | each XREAD independently (fan-out, NO consumer group) → all wake → atomic claim → exactly one processes |
| Redis down (producer) | request unaffected (best-effort try/except) |
| Redis down (consumer) | falls back to plain sleep = today's polling |
| Stream growth | `maxlen≈100 approximate` on XADD |

No consumer group on purpose: a group would split wakes across replicas (we want ALL to wake). The wake is best-effort; the poll is durable.

## Test plan
- knowledge `extraction_wake`: XADD called with right fields + maxlen; best-effort swallows a raised Redis error (returns, doesn't propagate); disabled/no-url → no-op.
- knowledge start-route: the route invokes the injected wake fn AFTER job creation (mock fn records the call); a wake-fn exception does NOT fail the 200.
- worker-ai `wait_for_wake_or_timeout`: (a) message present → `(True, id)`; (b) timeout no message → `(False, last_id)`; (c) redis error / empty url → degrades to sleep, returns `(False, last_id)`.
- Cross-service (knowledge + worker-ai = ≥2 services) → **live-smoke token required at VERIFY**: either a real stack-up (knowledge XADD → worker XREAD wakes < poll_interval) or `live infra unavailable: <reason>` if the full stack isn't bootable at dev time.

## Out of scope
- Replacing polling (it stays the source-of-truth).
- Durable delivery / consumer group / retry of wakes (poll covers misses).
