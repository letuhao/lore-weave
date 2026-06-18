# Phase 3 M5 — video-gen decouple (job-row + terminal-event + poll)

**Status:** DESIGNED (CLARIFY done, PO decision locked 2026-06-13). Ready to BUILD.
**Size:** L/XL — new persistence layer on a stateless service + contract change + FE.
**Reference implementation:** **M1** (learning-service judges on a generic decoupled
state machine + `loreweave:events:llm_job_terminal` consumer). Mirror it.

## PO decision (CLARIFY)
**Full DB, mirror M1.** Add a Postgres DB to video-gen-service + a `video_gen_jobs`
table + a terminal-event consumer + a poll endpoint + a worker entrypoint. Consistent
with the platform convention (each service owns its Postgres DB) and the /review-impl'd
M1 reference. (Rejected: a near-stateless Redis-cache variant — deviates from the
per-service-DB pattern; and deferring — PO wants Phase 3 finished.)

## The architectural key (why this is M1, not a gateway change)
`Client.generate_video()` is just `submit_job(operation="video_gen")` + `wait_terminal()`
([sdks/python/loreweave_llm/client.py:820](../../sdks/python/loreweave_llm/client.py#L820)).
**The gateway (provider-registry) ALREADY runs video as a job with a `provider_job_id`
and emits `loreweave:events:llm_job_terminal` on terminal** (Phase 1). So video-gen just
needs to: submit (not wait) → persist the provider_job_id → consume the terminal event →
download→MinIO→mark done. Identical to M1's learning-judge consumer.

## Current state (what M5 changes)
[services/video-gen-service/app/routers/generate.py](../../services/video-gen-service/app/routers/generate.py)
`POST /generate` is **request-blocking**: `client.generate_video()` submits + internally
polls `wait_terminal` (5-15 min for Wan/LTX), then downloads the remote URL → MinIO →
returns the local URL (201). video-gen-service is **entirely stateless** (no DB, no Redis
— [config.py](../../services/video-gen-service/app/config.py) has neither).

## BUILD plan (mirror M1, increment order)

1. **Infra — provision the DB.** Add `loreweave_video_gen` to
   [infra/postgres-init/01-databases.sql](../../infra/postgres-init/01-databases.sql) +
   `infra/db-ensure.sh`. Add `VIDEO_GEN_DB_URL` + `REDIS_URL` to the service env in
   [infra/docker-compose.yml](../../infra/docker-compose.yml) (the consumer reads the
   Redis terminal-event stream). Add a `video-gen-worker` compose service (same image,
   `python -m app.worker`, flag-gated `VIDEO_GEN_DECOUPLE_ENABLED:-false`) — mirror
   `composition-worker` / `lore-enrichment-worker`.

2. **Migration + repo.** `video_gen_jobs` table:
   `id` (our job id, PK), `user_id`, `provider_job_id` (the gateway job, UNIQUE — the
   consumer match key), `status` (pending/running/completed/failed/cancelled),
   `request_json` (prompt, model_source, model_ref, aspect_ratio, duration_seconds,
   style, init_image?), `video_url` (the MinIO local URL, null until done),
   `size_bytes`, `content_type`, `error_json`, `created_at`, `updated_at`. Index
   (user_id, created_at DESC) + UNIQUE(provider_job_id). Repo: create / get(user,id) /
   get_by_provider_job_id / update_status(... result/error) — pattern from M1's judge repo.

3. **Submit endpoint (flag-gated).** When `VIDEO_GEN_DECOUPLE_ENABLED`:
   `POST /generate` → `client.submit_job(operation="video_gen", input=...)` (NOT
   generate_video — don't wait) → persist a `video_gen_jobs` row (status=pending,
   provider_job_id) → **202** `{job_id, status:"pending"}`. Flag-off → the existing
   inline 201 path verbatim (zero contract change when off). Reuse `_aspect_to_size`,
   `record_usage` (move billing to the consumer's completion, like the inline path bills
   after the result).

4. **Terminal-event consumer** (`app/worker/`, mirror M1's consumer + composition's
   `job_consumer.py`): XREADGROUP `loreweave:events:llm_job_terminal` → for each event,
   look up `video_gen_jobs` by `provider_job_id` (skip if not ours — other services'
   jobs share the stream) → on `completed`: fetch the job result (VideoGenResult URL via
   the SDK get-job, or the event payload if it carries result) → download → MinIO (reuse
   `ensure_bucket_ready` + `put_object`) → `update_status(completed, video_url=local,
   size_bytes, content_type)` + best-effort `record_usage`. On `failed`/`cancelled` →
   mark accordingly. Idempotent (already-terminal row → skip). ACK semantics +
   stuck-job sweeper backstop (created_at/updated_at) — same as composition.

5. **Poll endpoint.** `GET /v1/video-gen/jobs/{id}` → the row (status + video_url when
   done + error). **Contract change** — callers must poll. 404 cross-user.

6. **FE** ([frontend/src/features/video-gen/api.ts](../../frontend/src/features/video-gen/api.ts)):
   bury submit+poll inside the api method (the M2/M4-FE pattern) — detect 202
   `status:"pending"` → poll `GET /v1/video-gen/jobs/{id}` to terminal → return the
   completed shape; flag-off → inline 201 verbatim. Zero hook/component churn.

## Gotchas (from M1-M4)
- **Shared terminal-event stream**: `loreweave:events:llm_job_terminal` carries ALL
  services' job terminals (LLM, judges, video). The consumer MUST filter to its own
  `provider_job_id`s (a `get_by_provider_job_id` miss → skip + ACK; not an error).
- **Billing**: `record_usage` moves to the consumer's completion (the inline path billed
  after the result; keep that — bill once, on completed).
- **MinIO download in the consumer**, not the request — the whole point (the request
  returns 202 immediately).
- **Provider-gate**: no new provider SDK imports (the SDK Client is the only gateway
  path; download httpx stays — orthogonal, already allowlisted).
- **Live-smoke** `D-M5-VIDEOGEN-LIVE-SMOKE`: flag-on, submit a real (or stub) video job,
  confirm 202 → terminal event → MinIO object → poll returns the local URL.
