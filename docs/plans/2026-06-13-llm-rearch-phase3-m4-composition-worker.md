# Plan — Phase 3 M4: composition worker + queue (from scratch)

**Parent:** [`2026-06-12-llm-rearch-phase3-long-tail.md`](2026-06-12-llm-rearch-phase3-long-tail.md) (M4).
PO chose **all 5 batch ops + build now** (2026-06-13). XL — `/warp` TRIAGED-OUT (single
service; the migration + consumer-dispatch + worker-entrypoint are shared-write magnets) →
`/loom` serial.

## CLARIFY findings (2026-06-13 investigation)

composition-service has **more infra than the parent plan implied**:
- ✅ `generation_jobs` table — status (pending/running/terminal), `llm_job_id`, `input`/`result`/`critic`
  JSONB, idempotency_key, cost_usd, base/target_revision_id. ([db/repositories/generation_jobs.py](../../services/composition-service/app/db/repositories/generation_jobs.py))
- ✅ `GET /jobs/{job_id}` poll endpoint already exists ([routers/engine.py:1053](../../services/composition-service/app/routers/engine.py#L1053)).
- ❌ **NO worker, NO events/consumer, NO queue** — every endpoint runs the engine **inline**
  (request-blocking) and returns the result synchronously.

**The 5 inline operations (heterogeneous shapes):**
| Op | Endpoint | Today |
|----|----------|-------|
| decompose | `plan.py:115` `/outline/decompose` | inline LLM, **NO job row** (interactive preview, NOT persisted) |
| generate (prose) | `engine.py:261` `/generate` | creates job → inline engine + canon-reflect → result |
| selection-edit | `engine.py:544` `/selection-edit` | creates job → inline engine → result |
| chapter-gen | `engine.py:674` `/chapters/{id}/generate` | creates job → inline → result |
| stitch | `engine.py:892` `/chapters/{id}/stitch` | creates job → inline stitch + canon-reflect → result |

**Streaming cowrite stays inline (SSE)** — only the batch ops decouple.

## Design

**Reuse** the `generation_jobs` table (+ its `result`/`status`/`llm_job_id`) + the `GET /jobs/{id}`
poll. **Build from scratch** (mirror lore-enrichment's `resume_consumer`):
1. **Migration** — `generation_jobs += resume_state JSONB` (the request shape the worker re-drives
   from a job_id) IF not already present; reuse `input` JSONB if it already carries the full request.
2. **Queue** — a Redis stream `loreweave:events:composition_jobs` + a consumer group
   `composition-worker` (mirror `LORE_ENRICHMENT_RESUME_STREAM` + `resume_consumer`).
3. **Worker entrypoint** — `app/worker/__main__.py` (`python -m app.worker`) + a compose
   `composition-worker` service (same image, CMD override), flag-gated `COMPOSITION_WORKER_ENABLED`.
4. **Consumer** — `app/worker/job_consumer.py`: XREADGROUP → load job by id → dispatch by
   `operation` → run the extracted engine fn → mark completed(result)/failed; idempotent
   (completed→skip), ack on terminal/poison, leave un-acked on infra error.
5. **Extract** each endpoint's inline engine block into a worker-callable `run_<op>(pool, job)`
   (the endpoint and worker share it; for decompose, create a job row first).
6. **Endpoints → 202** — create job (operation, input=request) + enqueue + return `{job_id, status:'pending'}`;
   the existing `GET /jobs/{id}` polls for `result`.
7. **FE** — the 5 callers flip 200-with-result → 202 + poll (hide submit+poll in the api layer,
   the M2 pattern).

## Idempotency / safety
- At-least-once: `run_job` returns early if status='completed'; a crash mid-run leaves 'running'
  → redelivery recomputes (idempotency_key + base_revision_id guard duplicate side effects).
- Cost/critic: the existing job columns already track these — the worker writes them as today.
- `llm_job_id` links the composition job to the provider-registry LLM job (cancel propagation later).

## Risk-boundary increments (committed)
1. **Foundation** — migration + queue + worker entrypoint + consumer + **decompose** decoupled
   end-to-end (the proven vertical slice). VERIFY + commit.
2. generate + selection-edit (engine.py prose paths).
3. chapter-gen + stitch.
4. FE submit+poll for all 5 + live-smoke (`D-M4-COMPOSITION-WORKER-LIVE-SMOKE`).

## VERIFY
Unit (consumer dispatch + idempotency, each op's run fn, endpoint 202 + job creation, poll) +
provider-gate; live-smoke = a real decompose/stitch via the worker (≥2 services → token).
