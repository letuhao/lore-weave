# Plan — Phase 3 M2: lore-enrichment suggest/intent off the request path

**Parent:** [`2026-06-12-llm-rearch-phase3-long-tail.md`](2026-06-12-llm-rearch-phase3-long-tail.md) (M2). PO chose
**full async refactor** (2026-06-13) after a BUILD-time discovery.

## BUILD-time discovery (why this diverges from the parent plan)

The parent plan assumed M2 reuses the terminal-event decouple like M1. It does **not**:
lore-enrichment's LLM seam ([`generation/complete.py`](../../services/lore-enrichment-service/app/generation/complete.py))
is a **synchronous streaming** `POST /internal/llm/stream` — no `provider_job_id`, no
`loreweave:events:llm_job_terminal` participation. So M2 is a **"move a sync request-path
LLM call into the background worker + poll"** refactor, NOT a terminal-event decouple.

The two targets — `POST …/books/{book_id}/profile/suggest` and
`POST …/projects/{project_id}/compose/resolve-intent` — are one-shot interactive calls that
**don't persist a result today** ("does NOT persist" / "NO job created"). The existing
`enrichment_job` is gap-fill-specific (C8 state machine, technique CHECK, proposal children,
cost-cap pause) — a poor fit. So M2 adds a **dedicated lightweight task table** and reuses the
**resume-worker + Redis-stream pattern** (not the gap-fill job lifecycle).

## Shape

**Backend (lore-enrichment-service):**
1. **Migration** — new additive `enrichment_compose_task` (`task_id`, `kind` ∈
   {profile_suggest,intent_resolve}, `status` ∈ {pending,running,completed,failed},
   `user_id`, `project_id`, `book_id`, `request_json`, `result_json`, `error_message`,
   timestamps; idx `(user_id, book_id, created_at DESC)`). The poll result store.
2. **`app/compose/compose_task.py`** — task store (create/load/mark) + `run_compose_task`
   (idempotent: completed→skip) + the two extracted compute fns
   (`compute_profile_suggest` / `compute_intent_resolve`) holding the LLM orchestration
   moved out of the endpoints (incl. `_sample_chapter_texts`/`_kg_summary`, moved here to
   avoid an api↔service import cycle).
3. **Endpoints → 202.** suggest: owner-check (stays on the request path → fast 403) → create
   task → enqueue `{task_id, kind, user_id, project_id}` on `LORE_ENRICHMENT_RESUME_STREAM`
   → `202 {task_id, status:'pending'}`. resolve-intent: auth-check → create → enqueue → 202.
4. **`app/api/compose_tasks.py`** — `GET /v1/lore-enrichment/compose-tasks/{task_id}` →
   `{task_id, kind, status, result, error}`, user-scoped (404 for a non-owner).
5. **Worker branch** ([`resume_consumer.py`](../../services/lore-enrichment-service/app/worker/resume_consumer.py)):
   message has `task_id` → `run_compose_task`; else existing `redrive_one`. Same ACK/un-ACK
   semantics (business error → mark failed + ACK; infra error → un-ACK → redeliver).

**Frontend (features/enrichment):** `api.ts` suggest/resolveIntent return `{task_id}`; add
`getComposeTask` + a submit-then-poll wrapper (mirrors the existing upload poll); update the
two callers + tests.

## Idempotency / safety
- At-least-once redelivery: `run_compose_task` returns early if status='completed'; a crash
  mid-compute leaves status='running' → redelivery recomputes + overwrites (a duplicate
  LLM call, converges — acceptable for a draft).
- Owner-check stays synchronous at submit (a non-owner never creates a task).
- Unmetered (matches today's suggest/intent — no cost cap).

## VERIFY
Unit (task store idempotency, both compute fns via injected complete-seam, endpoint 202 +
task creation, worker branch dispatch, poll 404/scoping) + provider-gate. Live-smoke →
`D-M2-LORE-ENRICH-ASYNC-LIVE-SMOKE` (submit→worker→poll round-trip on the real stack).
