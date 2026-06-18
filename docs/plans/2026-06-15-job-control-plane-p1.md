# Plan — Unified Job Control Plane **P1**: `loreweave_jobs` SDK + consumer migrations

**Date:** 2026-06-15 · **Branch:** feat/auto-draft-factory-gaps · **Size:** XL
**Spec:** [`docs/specs/2026-06-15-unified-job-control-plane.md`](../specs/2026-06-15-unified-job-control-plane.md)
**PO scope (2026-06-15):** drive full P1 · **migrate ALL ~12 shared-scaffold consumers** ·
**wire `emit_job_event` now** (same-tx outbox) · money-path worker-ai LAST.

## Goal
One shared transport-scaffold consumer (`BaseTerminalConsumer`) that every background
worker is rebuilt on (kills the copy-pasted bug surface), a canonical `JobRecord`/`JobEvent`
contract, and `emit_job_event` writing job-lifecycle events to each producer's outbox →
`loreweave:events:jobs` (consumed by the P2 jobs-service projection).

## DESIGN — the SDK (`sdks/python/loreweave_jobs/`)

Register `loreweave_jobs*` in `sdks/python/pyproject.toml` `[tool.setuptools.packages.find].include`.

### `contract.py` (frozen interface — slices read ONLY this)
- `class JobStatus(str, Enum)`: `pending, running, paused, cancelling, completed, failed, cancelled`.
  - `TERMINAL = {completed, failed, cancelled}`; helper `is_terminal(s)`.
- `class ControlCap(str, Enum)`: `cancel, pause, resume`.
- `@dataclass JobRecord` — the L0 shape (service, job_id, owner_user_id, parent_job_id, kind,
  status, detail_status, progress`{done,total}|None`, control_caps`[]`, title, error`{code,message}|None`,
  created_at, updated_at). `to_dict()`/`from_dict()` (JSON-safe). **NO `provider_job_id`** (H2).
- `class JobEvent` — the outbox/stream payload: `{service, job_id, owner_user_id, parent_job_id,
  kind, status, detail_status, progress, title, error, occurred_at}`. `to_payload()` → JSON dict.
- Stream constants: `JOBS_STREAM = "loreweave:events:jobs"`, `JOBS_AGGREGATE_TYPE = "jobs"`
  (the relay routes `loreweave:events:<aggregate_type>`), `TERMINAL_STREAM =
  "loreweave:events:llm_job_terminal"` (the existing provider-terminal stream).

### `consumer.py` — `BaseTerminalConsumer` (template-method **transport scaffold ONLY**, H4)
Generalises the IDENTICAL transport found in video-gen / translation / worker-ai / learning /
knowledge / composition / lore-enrichment / campaign consumers. **Base owns** (the bug-copy surface):
- `__init__(redis_url, *, consumer_name=None)`; `_ensure_redis()` with **`socket_timeout=None`**
  (REQUIRED — a per-read timeout < block_ms pre-empts BLOCK and crashes the task).
- `_ensure_group()` — `xgroup_create(stream, group, id=start_id, mkstream=True)`, **BUSYGROUP-safe**.
- `run()` — startup connect+`_drain("0")` (PEL recovery) with 5s readiness-retry; main loop
  `xreadgroup(group, name, {stream: ">"}, count, block=block_ms)`; **`except TimeoutError: continue`**
  (redis-py-8 idle), `ConnectionError` reconnect-5s, `CancelledError` clean stop, generic `except`
  sleep-2s (resilient — worker-ai gains this).
- `_process_msg()` — **operation pre-filter** (if `self.operation` set and `fields["operation"]`
  present and ≠ it → ack-ignore, no DB hit; None ⇒ always handle); then `await self.handle(fields)`
  → `xack` on normal return; on exception → bounded retry via Redis `INCR {retry_prefix}:{msg_id}`
  + `expire 3600`; `>= max_retries` → optional DLQ `XADD {stream}:dlq` (default off = current
  behaviour) + `log.error` + `xack` + `delete` retry key; else `log.warning`, leave unacked.
- `run_sweeper(interval_s, timeout_s, batch)` scaffold → calls `self.sweep_once(...)`; `<=0` disabled.
- `stop()`, `close()`.

**Subclass supplies** (class attrs + abstract hooks — the legitimately-divergent business logic):
- attrs: `stream` (default `TERMINAL_STREAM`), `group` (req), `operation: str|None = None`,
  `consumer_name_prefix`, `retry_prefix`, `max_retries=3`, `block_ms=5000`, `start_id="$"`,
  `dlq_stream: str|None = None`.
- `async def handle(self, fields: dict) -> None` — the fold; return ⇒ ack (incl. no-op/ignore),
  raise ⇒ retry/poison. (Wraps each service's existing `complete_job`/`_resume`/`_handle` body.)
- `async def sweep_once(self, *, timeout_s, batch) -> int` — optional; default returns 0
  (sweeper no-op unless overridden).

Deliberately does **NOT** unify `handle`/`sweep_once` bodies (they legitimately differ) — over-
unifying re-introduces the bugs we're deduping. Codifies: PEL-reclaim, redis-py-8 idle, operation
pre-filter, `FOR UPDATE SKIP LOCKED` sweep discipline, CAS finalize/bill-once.

### `emit.py` — `emit_job_event(conn, *, service, job_id, owner_user_id, kind, status, ...)`
- Writes a `JobEvent` row to the producer's **`outbox_events`** in the **SAME tx** as the job-row
  status change (H1 — transactional outbox; relayed exactly-once by worker-infra):
  `INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
   VALUES ('jobs', $job_id::uuid, 'job.'||$status, $payload::jsonb)`.
- `conn` is the caller's asyncpg connection/tx (NOT a global pool) so it's atomic with the status write.
- Idempotency: documented dedup key `(service, job_id, status)` — the P2 projection upserts on it;
  emit is append-only (relay dedups re-emission via `outbox_id`).
- Best-effort variant `emit_job_event_safe(pool, ...)` for non-transactional callsites (logs+swallows).

### worker-infra relay
- Add `"jobs": 50000` to `streamMaxLen` (lifecycle events are frequent). Additive.
- Each emitting service must be an `OUTBOX_SOURCES` relay source (env in compose) **and** own an
  `outbox_events` table — see per-service checklist.

## Migration order (each: refactor onto base · wire emit · unit tests green · live-smoke · flag+fallback)

| # | Service · consumer | outbox exists? | live-smoke |
|---|---|---|---|
| 1 | video-gen `worker/consumer.py` (pattern-proof) | ➕ add table+source | transport (no ComfyUI) |
| 2 | translation `events/llm_terminal_consumer.py` | ✅ | transport + real chapter |
| 3 | translation `events/glossary_consumer.py` | ✅ | transport |
| 4 | learning `events/llm_judge_consumer.py` | ➕ | transport (needs eval opt-in) |
| 5 | learning `events/consumer.py` | ➕ | transport |
| 6 | learning `events/eval_runner.py` | ➕ | transport |
| 7 | knowledge `events/consumer.py` | ✅ | transport |
| 8 | composition `worker/job_consumer.py` | ✅ | transport + real decompose |
| 9 | campaign `events/consumer.py` + `spend_consumer.py` | ➕ | transport |
| 10 | lore-enrichment `worker/resume_consumer.py` | ➕ | transport |
| 11 | worker-ai `summary_consumer.py` | (shares?) | transport |
| 12 | **worker-ai `llm_extract_consumer.py` (MONEY-PATH — LAST)** | ✅(extraction_jobs) | **full extraction E2E** |

Each migration is behavior-preserving + **flag-gated with the old consumer as fallback**; flip only
after live-smoke. `➕` = service needs a new `outbox_events` table migration + `OUTBOX_SOURCES` entry
+ relay MAXLEN already covered by the `jobs` default.

## Verify
- SDK: `pytest sdks/python/tests/test_jobs_*` (contract round-trip; base consumer via fakeredis /
  a fake redis: group-create idempotent, PEL drain, idle TimeoutError, operation pre-filter, ack on
  success, bounded-retry-then-poison-ack, sweeper scaffold; emit writes the outbox row in-tx + safe-swallow).
- Each migration: the service's existing consumer suite stays green (fold unchanged) + new wiring test.
- Cross-service (≥2 services) per migration → **live-smoke token** (transport-level boot+group+idle+
  ack-foreign on a real Redis; worker-ai gets the full extraction E2E). Defer with a token when a
  backend is unavailable.

## Checkpoints (continuous flow — commit at risk boundaries)
1. **SDK foundation** (contract+consumer+emit+tests+pyproject+relay MAXLEN) — frozen-interface commit.
2. Each consumer migration (or a small batch of same-service ones) — commit after its live-smoke.
3. worker-ai money-path — its own commit + POST-REVIEW + `/review-impl`.

## Migration checklist (per consumer — from /review-impl findings)
- **Strip the old internal `xack`/`incr`/retry from the migrated `handle`** — the base now
  owns ack + bounded-retry + poison-ack (LOW-2). The `handle` body returns to ack, raises to retry.
- **Verify the service's domain job id is UUID-coercible before wiring `emit_job_event`** —
  the outbox `aggregate_id` is `uuid`; a non-UUID id makes the in-tx INSERT raise + roll back the
  status change (MED-3). Use `emit_job_event_safe` / map to a UUID otherwise.
- Keep the subclass `operation` set for terminal-stream consumers that share the stream
  (video-gen etc.) to preserve the no-DB-hit pre-filter; leave `operation=None` for
  worker-ai/translation (they fall through to the row lookup, as today).
- The P2 jobs-service projection consumer must NOT use the default `start_id="$"` (it would
  miss events emitted before its group existed) — read from `"0"`/a checkpoint (LOW-1).

## Out of scope (P1)
- The jobs-service projection, `/v1/jobs` API, SSE, control routing → **P2**.
- Per-service cancel/pause/resume control endpoints → **P3**. GUI → **P4**.
</content>
</invoke>
