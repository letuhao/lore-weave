# Auto-Draft Factory — Architecture Readiness Assessment

> **Status:** DESIGN artifact (PO-reviewed 2026-06-08). Companion to the BYOK pre-req plan ([`2026-06-08-byok-provider-consistency-prereqs.md`](2026-06-08-byok-provider-consistency-prereqs.md)) and the UX draft (`design-drafts/auto-draft-factory.html`).
> **Feature:** a setup **wizard** to run a long, **no-human-in-loop** batch over ~4,000 raw chapters through the full pipeline (ingest → knowledge-extraction [also seeds glossary] → translation → eval), with cost+time review, budget ceiling, resume, and a wake-up report. Human reviews/confirms *after* via the M5/M6/M7 flywheel.
> **Method:** 3-agent code audit + **live scenario runs** on the dev stack (2026-06-08). Findings are grounded with file:line; the highest-risk gaps were reproduced empirically.

---

## Verdict

The per-service **primitives are solid** and reusable — this feature is an *orchestration + idempotency + hardening* layer on top, not a rewrite:
- **Billing** already has per-job cost **estimation** (`provider-registry/internal/billing/estimate.go`, script-aware tokens), **reservation + spend_guardrails** (daily/monthly caps, 402 preflight), and **per-model pricing** (JSONB; local providers = $0).
- **Translation** has a **DLQ** (`translation.chapters.dlq`), a **per-chapter idempotent status guard**, and stale-chapter recovery on worker restart.
- Transactional **outbox → worker-infra relay → Redis Streams** is proven (M7 live-smokes).

But the autonomous-4000-chapter use case **breaks** at four places — two of them reproduced live:

| Severity | Theme | Gap |
|---|---|---|
| 🔴 | **Idempotency** | Translation is imperative ("run this job"), not declarative ("ensure translated") → re-run/resume re-translates successful chapters = double-spend (**G3**, reproduced). |
| 🔴 | **Orchestration** | No cross-service campaign/saga sequencing ingest→knowledge→translation (**G1**); knowledge ignores `chapter_range` so "1 phần"/sample can't be scoped (**G2**). |
| 🔴 | **Reliability** | No global rate-limit governor + no circuit-breaker → a provider outage at 2 a.m. fails thousands of chapters independently with no auto-pause (**G5/G6**). |
| 🟡 | **Cost / progress** | No campaign-level mid-run budget pause (**G4**); no unified per-chapter cross-pipeline status (**G7**); chapter event-stream trim risk at batch scale (**G8**). |

---

## The load-bearing principle (PO 2026-06-08): translation must be IDEMPOTENT

**Re-translating an already-successfully-translated chapter, when the user did not ask for it, is a bug (wasted spend).** The correct model is declarative — *"ensure (chapter, target_lang) is translated"* — not imperative *"run a translate command over these ids."*

```
Before translating chapter X → language L:
  Is there a successful ACTIVE translation of (X, L)?
    ├─ No                              → translate
    └─ Yes:
       ├─ STALE? (glossary changed / source edited)   → re-translate   (input changed)
       ├─ user FORCE re-translate (new model, etc.)   → re-translate   (explicit request)
       └─ otherwise                                   → SKIP           ← this branch is MISSING today
  Previous attempt FAILED / partial                   → translate      (retry)
```

**Only three valid re-translate triggers: (1) never translated · (2) inputs changed (stale) · (3) explicit user request.** Everything else must SKIP.

**Why it currently redoes** (precise, not over-claimed):
- `chapter_translations` is keyed by **`job_id`** → a re-run = a NEW job = fresh rows, unrelated to the prior job's completed work.
- The coordinator fans out **every** `chapter_id` unconditionally ([`coordinator.py:25`](../../services/translation-service/app/workers/coordinator.py#L25)) — no skip-completed check (was tracked as `D-TRANSL-RESUME`).
- Nothing consults the existing active translation / staleness to decide whether a chapter *needs* translating.
- **Nuance (corrected):** a pure **worker-process crash** of the *same* job does **not** redo completed chapters — RabbitMQ redelivers only unacked (in-flight) messages; completed ones were acked. The redo-all bites specifically on **re-run / "Resume" / "Re-run failed" as a new job**, which is exactly what the Auto-Draft Monitor's Resume + Failed→Re-run flows need.

**Good news — the signals already exist:** `is_glossary_stale` (M5c/M6b, per-language, live-smoked this session) is the "inputs changed → re-translate" flag; `active_chapter_translation_versions` is the "already translated" check. They exist but the translate flow doesn't yet use them to gate. The fix is to **add the idempotency filter in front of the coordinator** (and as a default in `create_job`), reducing `chapter_ids` to `{never-translated} ∪ {stale} ∪ {failed} ∪ {force}` before fan-out.

**This unifies three gaps into one fix:** G2 (range), G3 (resume), and the Monitor's Resume/Re-run-failed buttons all become consequences of idempotency — "resume" = re-run the campaign with `skip_existing=ON`, which naturally processes only what's missing/failed. No separate "resume engine" needed.

---

## Gap inventory (grounded; file:line)

| # | Gap | Evidence | Severity |
|---|---|---|---|
| **G1** | No cross-service orchestration (no campaign/saga; gateway only proxies; client sequences manually) | audit: `api-gateway-bff/src/gateway-setup.ts`; knowledge uses HTTP-poll (`worker-ai/app/runner.py`), translation uses AMQP — no correlation | 🔴 spine |
| **G2** | Knowledge ignores `chapter_range` (preview-only) → can't extract a subset | code comment `knowledge-service/app/routers/public/extraction.py:97,148` (*"runner does not yet honour chapter_range"*, `D-K16.2-02b`) | 🔴 blocks "1 phần"/sample |
| **G3** | No translation idempotency → re-run/resume re-translates success = double-spend | **reproduced live** (S-CRASH below); `coordinator.py:25` fans out all ids; `chapter_translations` keyed by job_id | 🔴 |
| **G4** | No campaign-level mid-run budget pause (per-job reserve only; streams hard-abort but jobs don't) | audit: `usage-billing/guardrail.go` (preflight reserve), `stream_billing.go` (stream abort) — no job/campaign mid-run check | 🔴 cost screen promises it |
| **G5** | No global rate-limit governor + no circuit-breaker | **reproduced** (S-RATELIMIT: 0 governor keys in Redis); `llm_client.py` per-job retry only | 🔴 #1 overnight risk |
| **G6** | Retry has no exponential backoff (fixed 3, immediate republish) | `translation-service/worker.py` `_MAX_TRANSIENT_RETRIES=3`, manual republish | 🟡 amplifies G5 |
| **G7** | No unified per-chapter cross-pipeline status | **reproduced** (S-PROGRESS: translation = per-chapter rows; knowledge = `items_total/items_processed` counters only) | 🟡 Monitor heatmap has no source |
| **G8** | Chapter event-stream MAXLEN trim (10,000 approx) → event-loss risk at batch scale | **reproduced** (S-STREAM: `XLEN`=1,118; cap 10k in `outbox_relay.go` `streamMaxLen`) | 🟡 drops M7 feedback if consumer lags |
| **G9** | Knowledge throughput: worker-ai polls every 5 s, per-chapter HTTP, single instance | audit `worker-ai`; `POLL_INTERVAL_S=5` | 🟡 scale |
| **G10** | BYOK incomplete: reranker hardcoded; eval judges single-owner-billed | `D-RERANK-NOT-BYOK`, `D-EVAL-JUDGE-PER-USER` (BYOK pre-req plan) | 🟡 tracked |

---

## Empirical scenario evidence (live runs, dev stack, 2026-06-08)

| Scenario | What ran | Result → gap |
|---|---|---|
| **S-CRASH/RESUME** | Two jobs translating the **same 2 chapters** (zh→vi, local model, v2) | **input tokens identical across both runs** (226/236 each time) → 2 jobs · 4 chapter_translations · **924 input tokens (≈2× of 462)**. No skip, no dedup. **→ G3 confirmed.** Test artifacts cleaned up. |
| **S-PROGRESS** | Schema inspection | translation has `chapter_translations(chapter_id,status,job_id)`; knowledge `extraction_jobs(items_total,items_processed,status)` — counters only, no per-chapter status row. **→ G7 confirmed.** |
| **S-STREAM** | `XLEN loreweave:events:chapter` + relay const | length 1,118 / cap 10,000 (approx-trim). 4,000 ch × 2 events + concurrency approaches cap. **→ G8 confirmed.** |
| **S-RANGE** | Code comment | `extraction.py:97/148` — runner honours `chapter_range` only in preview (`D-K16.2-02b`). **→ G2 confirmed.** |
| **S-RATELIMIT** | Redis scan + queue list | `translation.chapters.dlq` exists; **0** rate-limit / provider-concurrency governor keys in Redis; retry fixed-3 no-backoff (code). **→ G5/G6 confirmed.** |

(G1 no-orchestration and G4 no-budget-pause are *absences* — audit-confirmed, not runnable.)

---

## Revised slicing (each slice's "done" is grounded in a gap)

| Slice | Scope | Closes |
|---|---|---|
| **S0 (pre-req)** | BYOK consistency — reranker → adapter-dispatched/per-user; eval judges per-campaign owner | G10 (`D-RERANK-NOT-BYOK`, `D-EVAL-JUDGE-PER-USER`) |
| **S1** | Campaign aggregate + orchestrator (sequence + dependency-gate + fan-out) + unified per-chapter progress projection | G1, G7 |
| **S2** | **Translation idempotency** (`skip_existing` default ON in create_job/orchestrator, using `is_glossary_stale` + `active_chapter_translation_versions`) + knowledge `chapter_range` in the runner | **G3 (+ Resume/Re-run-failed for free)**, G2 |
| **S3** | Reliability: global per-provider rate-limit governor (Redis) + circuit-breaker + exponential backoff + **campaign-level budget pause** | G5, G6, G4 |
| **S4** | Batch cost: per-campaign estimate/spend aggregation (reuse `estimate.go`) + chapter-stream MAXLEN/throughput tuning | G8, (cost screen) |
| **S5 / S6** | Wizard FE + Monitor / Failed&Re-run / Report FE (per `design-drafts/auto-draft-factory.html`) | UX |

**Priority:** S0 first (PO-locked, before any factory build). Then S1→S4 (backend spine + idempotency + reliability), then S5/S6 (FE).

---

## New deferred / tracked rows

- **`D-TRANSL-IDEMPOTENCY`** (🔴, supersedes/reframes `D-TRANSL-RESUME`) — translation must skip (chapter, lang) that has a fresh successful active translation unless stale/failed/forced. Unifies resume + re-run-failed + range.
- **`D-BATCH-RATELIMIT-GOVERNOR`** (🔴, G5) — global per-provider Redis governor (token bucket / semaphore) shared across workers.
- **`D-BATCH-CIRCUIT-BREAKER`** (🔴, G5) — pause a campaign on repeated provider failure instead of failing thousands of chapters.
- **`D-BATCH-BUDGET-PAUSE`** (🔴, G4) — campaign-level cumulative cap that pauses mid-run gracefully (extend reservation/guardrail).
- **`D-BATCH-PROGRESS-PROJECTION`** (🟡, G7) — campaign per-chapter cross-pipeline status (Monitor source).
- **`D-STREAM-MAXLEN-BATCH`** (🟡, G8) — raise/segment the `chapter` stream cap or ensure consumer keeps up under batch load.
- **`D-K16.2-02b`** (🔴 for this feature, G2) — knowledge runner honour `chapter_range` (existing deferral; promote).
- Carried: `D-RERANK-NOT-BYOK`, `D-EVAL-JUDGE-PER-USER`, `D-TRANSL-M7D-INLINE-JUDGE`.

---

## Solutions & design decisions (2026-06-08) — covers G1–G10 + A–G

### Core decision ★: a lightweight `campaign-service` (saga orchestrator + projection)

Not a heavyweight workflow engine (Temporal/Cadence — new infra + lock-in, against the "no platform lock-in" rule) and not the gateway (TS proxy — wrong place for stateful sagas). A small **`campaign-service`** (Python/FastAPI, own Postgres DB):

1. **Owns saga state** — `campaigns` + `campaign_chapters(campaign_id, chapter_id, ingest|knowledge|translation|eval status, attempts, last_error, …)`. This *is* the **unified per-chapter cross-pipeline projection** (solves **G7**) and sidesteps cross-DB FK (**D**) — it **projects** state from events, it does not foreign-key into other services' DBs.
2. **Drives** the EXISTING per-service job APIs (translation `create_job`, knowledge extraction `start`) — paced, with `skip_existing`.
3. **Advances** by consuming the EXISTING outbox event streams (`loreweave:events:{translation,knowledge,…}`) — the same backbone learning-service already consumes. **No new infra**; campaign-service is "just another consumer" + a driver.
4. **Crash-resumable** (**D**): a stateless driver + reconcile loop re-derives "what's next" from `campaign_chapters` on restart → idempotent.

One component is the home for **G1** (orchestration), **G7** (projection), **D** (aggregate + cross-DB + self-resume), and the enforcement point for G3/G4/B/E/F.

### Per-concern solutions

| Concern | Solution | Lives in | Slice |
|---|---|---|---|
| **G1** orchestration | campaign-service saga: drive APIs + consume events | campaign-service | S1 |
| **G3** idempotency | `skip_existing` default ON: to-do = `{never} ∪ {stale} ∪ {failed} ∪ {force}`, via `active_chapter_translation_versions` + `is_glossary_stale` | translation `create_job` + campaign | S2 |
| **B** freshness race | **phase barrier**: knowledge-extract ALL → (glossary stable) → translate. The wizard's "build knowledge first" = this; "cold-start" = the documented lower-quality opt-in | campaign-service | S1/S2 |
| **G2** range | runner honours `chapter_range` (`D-K16.2-02b`) | knowledge runner | S2 |
| **A** identity/authz | verify ownership ONCE at campaign-create (book-service projection, like `create_job` already does) → propagate the **verified** `user_id` over internal-token calls. **No minted user-JWTs** (that was a test hack). New service boundary → `/review-impl` mandatory. | campaign-service | S1 |
| **C** billing exactly-once | route usage recording through the **outbox** (provider-registry → outbox → usage-billing consumer) = at-least-once + idempotent on the existing UNIQUE `request_id` (replaces best-effort fire-and-forget). + periodic reservation sweep/reconcile | provider-registry + usage-billing | S3/S4 |
| **G4** budget pause | campaign tracks cumulative spend (events/reservations); orchestrator gates each dispatch wave vs the cap; pause gracefully on hit (stop dispatch, let in-flight drain), notify | campaign-service | S3 |
| **G5** rate-limit governor | global per-provider **Redis token-bucket / concurrency semaphore**; acquire-before-call (bounds cloud rate-limit AND the single local GPU) | shared llm-client SDK | S3 |
| **G5** circuit-breaker | per-provider failure-rate in Redis; threshold (N 429/5xx in window) → open → campaign **pause + notify**; cooldown auto-retry | llm-client + campaign | S3 |
| **G6** backoff | exponential backoff on retry (RabbitMQ delayed-message / TTL-ladder retry queue) instead of immediate republish | translation worker | S3 |
| **E** fairness | campaign **paces dispatch** (bounded in-flight window per campaign) → a 4000-ch batch never dumps 4000 msgs at once or starves interactive jobs; interactive jobs go direct (higher effective priority). Also fixes the enqueue-burst backpressure note. | campaign-service | S3 |
| **F** cancellation | campaign `status=cancelling` → stop dispatch + propagate cancel to each service's in-flight job + drain. Safe via the per-chapter status guard. | campaign-service | S3 |
| **G8** stream trim | a dedicated `campaign` stream with adequate `MAXLEN`; campaign consumer keeps up — do NOT piggyback the trimmed `chapter` stream (10k) for progress | worker-infra + campaign | S4 |
| **G10** BYOK | reranker → adapter-dispatched + per-user; eval judges → per-campaign owner | knowledge / provider-registry / learning | S0 |
| **G9 / G** capacity | **load-test plan** (post-v1): Neo4j batched writes, embedding index pre-build, glossary upsert already idempotent (`ON CONFLICT`), MinIO read cache, local-GPU serialized by the G5 governor | — | perf slice |

### Locked decisions (PO-confirmed 2026-06-08)

- ✅ **`campaign-service`** (new, Python/FastAPI, own DB) over gateway-module / Temporal. *(PO-confirmed.)*
- ✅ **Gating is a per-campaign user choice** (NOT a forced default): the campaign-service must implement **both** dispatch modes — **phase-barrier** (knowledge-ALL → translate, highest quality) and **cold-start interleaved** (translate immediately, bootstrap glossary via 2-pass). The wizard's "context strategy" step surfaces both; the orchestrator honours whichever the campaign selected. *(PO-confirmed.)* → S1 must build both dispatch modes behind one gating interface.
- **Identity:** verify-once-at-entry + assert-verified-`user_id` over internal-token; no minted user-JWTs.
- **Billing:** usage recording → outbox (exactly-once via `request_id` dedup) — reuse the proven backbone.
- **Reliability:** Redis governor + circuit-breaker (→ campaign pause) + backoff; reuse outbox/streams. **No new infra beyond campaign-service + its DB.**
- **Resume = idempotency** (not a separate engine): re-running a campaign with `skip_existing=ON` naturally processes only missing/stale/failed → Monitor's Resume + Failed→Re-run buttons are thin wrappers over this.

### Revised slicing v2 (solutions baked in)

| Slice | Scope | Closes |
|---|---|---|
| **S0** (pre-req) | BYOK: reranker adapter+per-user · eval judges per-campaign-owner | G10 |
| **S1** | `campaign-service` skeleton: campaign + `campaign_chapters` projection (consume events) · saga driver + reconcile-loop self-resume · ownership verify+propagate (A) · gating interface with **both** modes (phase-barrier + cold-start-interleaved, user-selected per campaign) (B) | G1, G7, D, A, B |
| **S2** | Translation idempotency (`skip_existing` + staleness gate) → unlocks Resume/Re-run-failed · knowledge `chapter_range` | G3, G2 |
| **S3** | Reliability + policy: Redis per-provider governor · circuit-breaker→campaign-pause · backoff · campaign budget-cap pause · paced dispatch (fairness) · unified cancel | G5, G6, G4, E, F |
| **S4** | Cost + events: usage→outbox exactly-once + reconcile · per-campaign estimate/spend aggregation (reuse `estimate.go`) · dedicated `campaign` stream MAXLEN | C, G8 |
| **S5 / S6** | Wizard FE · Monitor / Failed&Re-run / Report FE (per `design-drafts/auto-draft-factory.html`) | UX |
| **Sx** (post-v1) | Capacity load-test + tuning | G9, G |

**Why this ordering is safe:** S1 builds the spine + projection + the two security/consistency decisions (A, B) that are hardest to retrofit. S2 makes the core economic invariant (idempotency) true before any large run. S3 makes it survivable unattended. S4 makes cost exact. FE last.
