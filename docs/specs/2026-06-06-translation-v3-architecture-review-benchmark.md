# Translation Pipeline — Architecture Review & Benchmark-Readiness

> **Status:** Review note · feeds [V3 design](./2026-06-06-translation-pipeline-v3-multi-agent.md) + [market research](./2026-06-06-translation-llm-market-research.md)
> **Date:** 2026-06-06 · **Branch:** `feat/translation-pipeline-v3`
> **Purpose:** Deep-review the CURRENT architecture, list what to improve **before** benchmarking, and define the benchmark scenario matrix.

---

## 0. Why this note

Before we benchmark the architecture across many scenarios, we need (a) an honest map of the current architecture's limits, and (b) the *instrumentation* to make a benchmark produce comparable numbers at all. Today the pipeline has **no metrics module** ([llm_client.py](../../services/translation-service/app/llm_client.py) admits "translation-service has no metrics module yet") — so a benchmark right now would yield logs, not measurements. That is the gating fix.

## 1. Architecture as built (the runtime shape)

```
POST /v1/translation/books/{id}/jobs  (jobs.py)
  → verify ownership · resolve effective settings (job>book>user>default) · snapshot to translation_jobs
  → INSERT job + N chapter rows (loop, no txn)        ← see W7
  → publish ONE "translation.job" {chapter_ids:[…all…], prompts, model, chunk_size}
        │  loreweave.jobs (DIRECT, durable)
        ▼
  coordinator (worker.py on_job, prefetch=1)
  → UPDATE job running · publish N × "translation.chapter"   ← floods queue, no backpressure (W4)
        │  translation.chapters (durable, DLQ via TTL 24h)
        ▼
  chapter_worker (worker.py on_chapter, prefetch=1)         ← ONE chapter at a time / worker (W1)
  → fetch body (book-service) · fetch ctx-window (provider-registry, per chapter, W9)
  → block pipeline OR text pipeline → translate batches SEQUENTIALLY (W3)
  → persist chapter_translations + outbox event + notification
  → atomic job-finalize (UPDATE…WHERE completed+failed=total RETURNING)   ← good, no TOCTOU
```

Scaling unit = **one chapter**, via competing-consumer `translation-worker` replicas. Default compose runs **one** worker ([docker-compose.yml:413](../../infra/docker-compose.yml#L413), `restart: unless-stopped`, no `deploy.replicas`).

## 2. Strengths (keep — don't regress in V3)

- Clean **fan-out** (coordinator) + chapter-level **competing-consumer** scaling.
- **Durable** queues + persistent messages; **outbox** events for statistics; **atomic** job finalize (no TOCTOU) ([chapter_worker.py:276](../../services/translation-service/app/workers/chapter_worker.py#L276)).
- **Startup stale-recovery** for crashed-after-ack chapters ([worker.py:38](../../services/translation-service/worker.py#L38)) and stuck pending jobs ([main.py:24](../../services/translation-service/app/main.py#L24)).
- **Effective-settings layering** with per-job snapshot ([jobs.py:62](../../services/translation-service/app/routers/jobs.py#L62)); model_ref resolved server-side scoped to user (authz can't be forged).
- **Cooperative cancel** checked before each chapter.
- **Graceful degradation** on glossary fetch.

## 3. Weaknesses & risks (severity · why it matters for the benchmark)

| ID | Area | Issue | Sev | Benchmark impact |
|----|------|-------|-----|------------------|
| **W1** | Concurrency | `prefetch_count=1` + single consumer ⇒ 1 chapter at a time per worker process; no intra-process parallelism ([worker.py:107](../../services/translation-service/worker.py#L107)) | **High** | Primary throughput axis — must be a knob to benchmark |
| **W2** | Scaling | Default = **one** worker container (no `deploy.replicas`) ⇒ out-of-box throughput is 1 chapter system-wide | **High** | Benchmark must vary replica count; confirm prod scaling config |
| **W3** | Latency | Batches within a chapter run sequentially (needed for rolling context) — V3's verify-loop multiplies this ×(1+rounds) | **High** | Per-chapter latency axis; independent batches may parallelize |
| **W4** | Fairness | One shared queue, no per-user/per-job concurrency cap or priority lane ⇒ a 2000-ch job head-of-line-blocks every other user | **High** | Multi-tenant scenario will show starvation without this |
| **W5** | Failure | DLQ declared but worker **acks all** outcomes (even permanent) ⇒ DLQ only catches TTL-expired msgs, never failed chapters; no poison capture/reprocess ([worker.py:164](../../services/translation-service/worker.py#L164)) | **Med** | Failure-injection scenarios can't be inspected/replayed |
| **W6** | Cost | No per-job/per-user **cost ceiling** (knowledge-service has `user_budgets`; translation has none); V3 loop multiplies spend | **Med-High** | Cost-bound scenarios run unbounded; benchmark needs a cap |
| **W7** | Correctness | Job + chapter-row inserts not wrapped in a txn ([jobs.py:102](../../services/translation-service/app/routers/jobs.py#L102)) ⇒ crash mid-loop ⇒ `total_chapters` mismatch ⇒ job never finalizes | **Med** | Skews completion metrics; baseline correctness fix |
| **W8** | Resilience | No circuit breaker on book-service / provider-registry / glossary; each chapter re-fetches ⇒ a flapping dep ⇒ per-chapter transient storm | **Med** | Dependency-failure scenarios over-amplify |
| **W9** | Cost | Context-window fetched per chapter (fallback 8192), not cached per job ([chapter_worker.py:250](../../services/translation-service/app/workers/chapter_worker.py#L250)) | **Low** | N extra HTTP calls; minor latency noise |
| **W10** | Observability | **No metrics module**; per-stage timing/token/outcome only in logs; no `translation_quality_log` table | **High (gate)** | **Blocks** quantitative benchmarking entirely |
| **W11** | Observability | Block pipeline writes **no** `chapter_translation_chunks` rows ⇒ no per-batch trace, no resume; V6 quality columns unused on main path | **Med** | Can't measure per-batch or test resume |
| **W12** | Correctness | Markdown round-trip ([block_classifier.py](../../services/translation-service/app/workers/block_classifier.py)) is regex-based — nested/adjacent marks, links with parens, CJK-punct adjacency can mis-serialize | **Low-Med** | Rich-formatting scenarios expose this |
| **W13** | Dup work | Concurrent same-chapter jobs both compute; "last version wins", no dedupe/lock | **Low** | Concurrency scenarios waste compute |
| **W14** | Divergence | Sync `/translate-text` block mode lacks glossary/validation/retry ([translate.py:75](../../services/translation-service/app/routers/translate.py#L75)) | **Med** | A 2nd code path — benchmark or retire (TD2) |
| **W15** | Scaling | DB pool `max_size=10`/process ([database.py:9](../../services/translation-service/app/database.py#L9)); N replicas × 10 ⇒ Postgres connection pressure | **Low** | Watch at high replica counts |

## 4. Improvements to land BEFORE benchmarking (the readiness gate)

These make the benchmark *possible and meaningful* — and they largely **are M0/M1** of the V3 plan, so no extra scope:

1. **Instrumentation (W10) — the gate.** Add a metrics layer (Prometheus or structured stage events): per-chapter & per-batch latency, tokens in/out, calls, retries, outcome; plus the `translation_quality_log` / `translation_quality_issues` table (already in V3 §5). *Without this, stop — there is nothing to benchmark.*
2. **Concurrency knob (W1/W2).** Make worker concurrency configurable — `prefetch_count=K` and/or an asyncio task pool — and document/parametrize replica scaling. This is the benchmark's primary independent variable.
3. **Job-level caps + fairness (W4/W6).** A per-job `max_concurrent_chapters` and a per-job/user token/cost ceiling, so a scenario is bounded and one run can't starve another.
4. **Block-pipeline chunk rows + resume (W11).** Persist per-batch rows (also feeds quality + resume scenarios).
5. **Txn around job+chapters insert (W7).** Baseline correctness so completion metrics aren't skewed.

Defer to V3 build (not pre-benchmark): DLQ reprocessing (W5), circuit breakers (W8), markdown hardening (W12), sync-path convergence (W14).

> **Alignment:** items 1, 4, 5 = V3 **M0**; items 2, 3 are a small **M0.5** (concurrency + caps). Do these, then benchmark V2 as the baseline before building M1+.

## 5. Benchmark scenario matrix

### 5.1 Axes to vary
| Axis | Levels |
|------|--------|
| **Book scale** | 1 · 50 · 500 · 2000 chapters |
| **Chapter size / type** | tiny (media-only) · normal (10–40 blocks) · huge (500+ blocks); raw-text vs Tiptap-JSON |
| **Language pair** | zh→vi (primary, CJK→Latin expansion) · zh→en · ja→vi · en→vi (Latin→Latin) · zh→ja (CJK→CJK) |
| **Data state** (§11 of design) | rich glossary+knowledge · partial · **stale** (draft + pending_validation + lagging graph) · **cold** (none) |
| **Pipeline / QA** | V2 baseline vs V3; qa_depth rule_only / standard / thorough; max_qa_rounds 0 / 1 / 2 / 3 |
| **Models** | cheap local 7B (Sakura-class) · mid · strong; translator==verifier vs split; small vs large context window |
| **Concurrency** | worker replicas 1 / 2 / 4 / 8; prefetch 1 / 4 |
| **Failure injection** | provider 5xx / timeout · glossary down · book-service slow · model truncation · malformed `[BLOCK]` output · cancel mid-job |
| **Content stress** | heavy dialogue · dense proper-nouns · numbers/dates · rich markdown · mixed media · code blocks |

### 5.2 Metrics to capture per scenario
- **Quality:** omission rate · wrong-name rate · glossary-compliance % · source-script leak % · block-integrity % (scored by the Verifier itself **plus a held-out gold set** of seeded errors — don't trust the verifier to grade itself).
- **Cost:** tokens in/out per chapter · calls/chapter · $/chapter (· $/1k source chars).
- **Latency:** per-chapter p50/p95 · end-to-end job wall-clock.
- **Throughput:** chapters/min at each replica count.
- **Reliability:** fail/partial rate · retry count · resume correctness · DLQ depth.

### 5.3 Method notes
- **Gold set first.** Build a small fixed corpus with *seeded* known errors (dropped sentence, wrong name vs glossary, CJK leak, number drift) so quality metrics are ground-truthed, not self-graded (the LiTransProQA/TransAgents lesson: automatic metrics mislead — anchor on seeded truth + occasional human A/B).
- **Baseline V2 before V3.** Run the matrix on V2 first (post-instrumentation) to get the delta V3 must beat.
- **Isolate the axis.** Vary one axis at a time from a fixed baseline cell (e.g. 50-ch / normal / zh→vi / rich-data / strong-model / 2-replicas) to attribute effects.
- **Cost guard.** Run behind the per-job cost ceiling (item 3) so a 2000-ch × strong-model × thorough cell can't run away.

## 6. Open question for PO
Benchmark **harness location**: (a) a `services/translation-service/bench/` script suite (like knowledge-service's `app/benchmark/`), reusing the gold set + metrics; or (b) drive real jobs through a stack-up and scrape the new metrics. Recommend **(a) for quality/cost** (deterministic, mockable) + **(b) for throughput/latency/reliability** (needs the real queue + workers). Confirm before we build the harness.
