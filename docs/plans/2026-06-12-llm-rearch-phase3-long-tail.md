# Plan — LLM re-arch Phase 3 (long tail), FULL scope

**Goal.** Put the remaining services' LLM/generation jobs onto the durable job-row +
terminal-event pattern (provider-registry `llm_jobs` + `loreweave:events:llm_job_terminal`
resume) that worker-ai (extraction) + translation already use — so they're cancellable,
crash-resumable, and don't pin a worker/request coroutine. PO chose **FULL scope** (incl.
composition's from-scratch worker + the video-gen contract change).

**CLARIFY findings (2026-06-12 investigation):** most of Phase 3 is large-cost/low-value
(the GPU-slot incident was closed by Phases 0-2). FULL scope chosen anyway. Reusable
pattern from translation's `llm_terminal_consumer`: submit_job → persist provider_job_id →
a Redis-group consumer on `loreweave:events:llm_job_terminal` folds the terminal + persists,
idempotent on job_id, with a stuck-resume sweeper.

## Milestones (one continuous run; commit per milestone = risk boundary)

- **M1 — learning-service judges (extraction + translation).** Natural fit (both already
  best-effort background consumers). Add an `llm_judges` job table; modify `eval_runner._maybe_judge`
  (extraction) + `handlers._maybe_judge_translation` to submit + persist provider_job_id (not
  `submit_and_wait`); a new terminal-event consumer folds → `persist_online_judge`/`quality_scores`,
  idempotent. **Wiki judge stays sync** (request-contract — `POST /internal/learning/wiki/judge`
  blocks its caller). Establishes the pattern.
- **M2 — lore-enrichment (profile-suggest + intent-resolve) off the request path.** Reuse the
  EXISTING `lore-enrichment-worker` + `enrichment_runs` + the `lore-enrichment-resume` Redis
  consumer: the two sync endpoints (`book_profile.py:276`, `compose.py:724`) create a job row +
  enqueue + return 202; the worker runs the same `suggest_profile`/`resolve_intent`; FE polls.
  Eval runs (internal, small ensembles) stay sync.
- **M3 — chat disconnect-cancel.** The streaming path (`client.stream()` → provider-registry
  `/internal/llm/stream`) allocates **no job-row**, so explicit cancel-by-id needs a streaming-path
  job-row + a `jobCancels` registry entry. (NB the slot ALREADY frees on disconnect via
  `r.Context().Done()` → `adapter.Stream()`; this adds observability + an explicit chat-side
  cancel.) Provider-registry change + chat `request.is_disconnected()` / `GeneratorExit` → `cancel_job`.
- **M4 — composition worker + queue (from scratch).** composition-service has NO worker — only a
  job reaper. Build a Redis-group consumer + resume pattern (mirror lore-enrichment), move
  `decompose` (`plan.py:150`) + `stitch` (`engine.py:972`) + auto-mode chapter-gen off the request
  path (create job → 202 → worker → poll). Streaming cowrite stays inline (SSE). The big lift.
- **M5 — video-gen job-row + terminal-event + polling.** `generate_video` is request-blocking
  (SDK polls internally). Add a `video_gen_jobs` table + provider_job_id; submit → 202 → terminal
  consumer downloads → MinIO → marks done; new `GET /v1/video-gen/jobs/{id}` poll endpoint.
  **Contract change** (callers must poll).

## Notes
- Each milestone: VERIFY (unit + provider-gate; live-smoke where ≥2 services) + commit. POST-REVIEW
  + /review-impl at the load-bearing ones (M1 consumer, M4 worker, M5 contract).
- Wiki judge + composition streaming-cowrite + (optionally) video-gen contract are the FORCED-fit
  parts — flag at POST-REVIEW.
