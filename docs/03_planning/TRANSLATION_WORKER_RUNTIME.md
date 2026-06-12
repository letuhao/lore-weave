# Translation Worker — Runtime Findings & Verification

> **Status source-of-truth = the running stack, NOT this or any doc.** This file
> records what was *empirically observed* on the live local stack on
> **2026-05-31**, plus the exact commands to re-verify. The MVP debt tracker had
> claimed the translator pipeline "SHIPPED / works" while the worker was in fact
> dead — so always confirm against `docker ps` + worker logs + a real job, never
> against a status column.

---

## 1. Pipeline topology (verified by code + live logs)

```
FE TranslateModal → translationApi  (/v1/translation/*)
  → api-gateway-bff proxy            (gateway-setup.ts: pathFilter /v1/translation)
  → translation-service:8087         (routers/jobs.py → publishes to RabbitMQ)
  → RabbitMQ queue "translation.jobs"
  → [translation-worker container]   (services/translation-service/worker.py)
       coordinator.handle_job_message → fan-out per chapter
  → RabbitMQ queue "translation.chapters"
       chapter_worker.handle_chapter_message
         → book-service   GET /internal/.../chapters/{id}        (fetch source body)
         → provider-registry GET .../context-window               (model resolve)
         → glossary-service GET .../translation-glossary           (glossary context)
         → provider-registry POST /internal/llm/jobs              (the LLM call)
         → write chapter_translations version (status, tokens, body)
         → emit chapter_done event → notification-service POST /internal/notifications
```

- **Message bus = RabbitMQ (AMQP / aio_pika)**, not Redis Streams. (Redis exists
  but is cache / rate-limit / ephemeral only.) CLAUDE.md was corrected (DOC-1).
- The worker consumes **three** queues on startup: `translation.jobs`,
  `translation.chapters`, `extraction.jobs`.
- Retry/DLQ: transient errors republish with `x-retry-count` (max 3); permanent
  errors ack + leave DB `failed`. Startup `_recover_stale_chapters` resets
  chapters stuck `running` > 2h.

## 2. Runtime gaps found live (2026-05-31)

### GAP-W1 — worker had no restart policy → silently dead (FIXED)
- **Observed:** `infra-translation-worker-1` = `Exited (255)` ~4h, while
  `infra-translation-service-1` (the API) stayed `healthy`. Net effect:
  `POST /jobs` returns 201, the job row is created, but **nothing consumes
  `translation.chapters`** → chapters never progress. The API looking healthy
  masks a fully-broken feature.
- **Root cause:** the `translation-worker` compose service had **no `restart:`
  policy**, unlike its sibling background workers `worker-infra` and `worker-ai`
  (both `restart: unless-stopped`). A stack restart exited it and it never came
  back. It was **not** a code crash — it boots clean.
- **Fix:** added `restart: unless-stopped` to `translation-worker` in
  `infra/docker-compose.yml` + applied to the live container via
  `docker update --restart=unless-stopped infra-translation-worker-1`.
- **Verified after fix:** boots clean ("Worker ready — consuming
  translation.jobs, translation.chapters, extraction.jobs"); a fresh vi job went
  `pending → completed` in ~2s with the full pipeline running.

### GAP-W2 — LLM returns 402 "pricing not configured" → fallback, no real output (OPEN, config)
- **Observed:** `POST provider-registry-service:8085/internal/llm/jobs` →
  `402 Payment Required` → SDK `LLMQuotaExceeded`. The block translator then
  fails/zeroes the batch and **falls back to the original text** (chapter still
  marked `completed`, but `0 translated, in=0 out=0`).
- **Meaning:** auth + model resolve + the whole cross-service chain WORK (402 is
  returned by the billing/pricing layer, i.e. the request got all the way to the
  provider gateway). The blocker is purely **the configured `model_ref` has no
  pricing/quota set** (or the BYOK/local model path isn't wired to bypass
  pricing). This is config, **not** pipeline code.
- **Not yet fixed** — needs the provider/BYOK setup decision (local LM-Studio
  free path vs. configuring pricing for a platform model). This is the one real
  remaining blocker to *actual* translated output (debt item TR-4).

## 3. How to verify live (do this, don't trust docs)

```powershell
# 1. Is the worker actually running (not just the API)?
docker ps -a --filter "name=translation" --format "{{.Names}}  {{.Status}}"
docker inspect -f '{{.Name}} restart={{.HostConfig.RestartPolicy.Name}} state={{.State.Status}}' infra-translation-worker-1

# 2. Is it consuming queues? (look for "Worker ready — consuming ...")
docker logs --tail 20 infra-translation-worker-1

# 3. End-to-end job (token from /v1/auth/login):
#    POST /v1/translation/books/{bookId}/jobs  { chapter_ids, target_language, model_source, model_ref }
#    then poll GET /v1/translation/jobs/{jobId} → expect pending→running→completed/partial/failed in seconds
#    then read the version: GET /v1/translation/chapters/{chapterId}/versions
#    A "completed" job with in=0/out=0 tokens = LLM no-op (GAP-W2), NOT a real translation.

# 4. Watch the LLM call result in the worker log during the job:
docker logs --since 30s infra-translation-worker-1   # look for the POST /internal/llm/jobs status
```

**Acceptance is GREEN only when:** worker running + a job reaches `completed`
with `output_tokens > 0` and the version body is actually in the target language
(not the original). As of 2026-05-31: worker ✅ running, pipeline ✅ live, LLM
output ❌ (GAP-W2 / 402).
