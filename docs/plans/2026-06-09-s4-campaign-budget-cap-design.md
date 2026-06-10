# S4 — Campaign Budget Cap + Cost Attribution (DESIGN PASS)

> Auto-Draft Factory slice **S4**. Closes **G4** (per-campaign cumulative budget cap → auto-pause),
> **decision C** (usage→outbox exactly-once), the **flat-cost-source** bug, and **G8** (dedicated
> bounded usage stream). Design-only this session (PO: "don't rush a money-feature"); BUILD gated on
> approval of this doc + the proposed sub-slicing.
>
> **Status:** DESIGN. CLARIFY checkpoint passed 2026-06-09 (3 forking decisions locked, below).
> Branch: `feat/advanced-translation-pipeline`.

---

## 1. Problem

An autonomous campaign fans ~4,000 chapters through knowledge-extraction + translation (+ eval),
each chapter spawning many provider-registry LLM jobs. There is **no per-campaign spend ceiling**:
an overnight run can burn far past any intended budget before a human sees it. The factory needs a
`budget_usd` cap that the campaign enforces by **auto-pausing** itself when cumulative spend crosses it.

Three things block this today (verified in code, §3):

- **G4 — no campaign-level spend tracking or cap.** The `campaigns` table has no budget/spent columns.
- **🔴 Attribution is broken for campaigns.** Spend is keyed on the **provider-registry job_id**
  (`token_reservations.job_id`, `usage_logs.request_id`). The campaign only knows the
  **translation/knowledge** job_id (a different id; S3c-2a), and one translation job → many
  provider-registry jobs (one per chunk). The campaign cannot sum its own spend by anything it stores.
- **Usage recording is fire-and-forget + flat-priced.** `RecordUsage` is a best-effort HTTP POST to
  `/internal/model-billing/record`; a failed call is logged and dropped (lost usage → under-billing).
  usage-billing then recomputes cost at a flat **$0.000002/token** ([server.go:258]), not per-model.

## 2. Acceptance criteria

1. A campaign created with `budget_usd = B` accumulates the **real USD cost** of every LLM job it
   spawns (knowledge + translation), correlated by a `campaign_id` threaded to provider-registry.
2. When cumulative spend `≥ B`, the campaign **auto-pauses** (reusing the S3c pause path); a human
   resumes via `/start` after raising the cap or accepting the spend.
3. Usage delivery is **exactly-once-effect** (transactional outbox + at-least-once relay + idempotent
   consumers) — no usage is lost on a transient failure, none double-counted.
4. The quota/credits deduction uses **real per-model cost**, not the flat $0.000002/token.
5. The campaign usage stream is **bounded** (MAXLEN) and does not amplify the trimmed chapter stream (G8).
6. Non-campaign jobs (interactive chat, etc.) are unaffected; `budget_usd = null` ⇒ no cap, no behavior change.

## 3. Architecture grounding (what exists — verified)

| Component | Reality |
|---|---|
| **Accurate USD** | provider-registry `jobs/worker.go actualUSD()` already computes `tokIn/tokOut × model pricing` on every completed job. `billing/estimate.go` is script-aware per-model pricing. **The accurate cost already exists at the settle point.** |
| **Settle chokepoint** | `worker.go finalizeAndNotify` → `Repo.Finalize` (transactional, rowsAffected gate) → `notifier.PublishTerminal` (direct RabbitMQ, best-effort) → `settleBilling`: (1) guardrail reconcile/release (idempotent HTTP, sweeper-backstopped), (2) `RecordUsage` (**fire-and-forget HTTP**, tokens only). |
| **Flat cost** | usage-billing `/record` (`recordInvocation`) computes `costUSD = totalTokens × 0.000002` then deducts month-quota→credits. Idempotent on `request_id` (UNIQUE in `usage_logs`); deduction deferred until the insert is confirmed fresh. |
| **USD guardrail** | Separate Phase-6a system: `spend_guardrails` (per-user **daily/monthly** USD limit + reserved_usd), reserve→reconcile(actual_usd). **Per-user, not per-campaign** — orthogonal to S4; left untouched. |
| **`job_meta`** | `llm_jobs.job_meta` JSONB is persisted (carries caller passthrough + the max_tokens cap). SDK `submit_job(job_meta=…)` flows it through. **The correlation vehicle.** |
| **Campaign event spine** | `campaign-collector` consumer reads **Redis Streams** `loreweave:events:{knowledge,chapter,translation}` via `xreadgroup` (consumer group). Convergent/idempotent (sets status=done) — at-least-once safe. |
| **Outbox→relay→Redis precedent** | translation `chapter_worker._insert_outbox_event(db, "chapter.translated", …)` writes the outbox row **in the same tx** as the result persist; a worker-infra **relay** XADDs to `loreweave:events:*`. provider-registry does **not** have this pattern (RabbitMQ direct + fire-and-forget HTTP only). |
| **Pause** | Campaign pause (`POST /v1/campaigns/{id}/pause`, S3c) + breaker→pause (S3c-2b, `pause_campaigns_for_dispatched_chapter`) already implemented. Resume = `/start`. |

## 4. PO decisions (CLARIFY checkpoint — locked 2026-06-09)

1. **Aggregation = usage→outbox event stream (decision C).** Event-driven (matches the campaign
   projection design); bundles exactly-once + the flat-cost fix + G8.
2. **Enforcement = reactive pause** on summed **actual** spend. Overshoot by in-flight jobs is
   accepted (bounded by the driver's in-flight ceiling; consistent with the "lower a limit, bounds
   NEW work, never aborts in-flight" billing ADR).
3. **Flat-cost fix is in scope for S4.** Replace $0.000002/token with real per-model cost on the
   quota/credits deduction path.

## 5. Design

### 5.1 Correlation threading (campaign_id → provider-registry job)

```
campaign driver
  → TranslationDispatchClient.dispatch_job(..., campaign_id)         [body field]
  → /internal/translation/dispatch-job stores campaign_id on the translation job
  → chapter_worker / session_translator submit_job(job_meta={"campaign_id": …})
  → provider-registry persists llm_jobs.job_meta.campaign_id
(symmetric for knowledge: dispatch-extraction → worker-ai runner → submit_job job_meta)
```

- `job_meta` already merges (`mergeJobMeta`) — add `campaign_id` as a reserved key; the existing
  max_tokens-cap merge must not clobber it (and vice-versa). One shared constant
  `JOB_META_CAMPAIGN_ID = "campaign_id"`.
- The translation/knowledge jobs persist `campaign_id` so **every** chunk-level provider job they spawn
  inherits it via `job_meta` — this is what bridges the "1 translation job → N provider jobs" gap.
- **Intra-service hop (non-trivial):** in translation the id must flow `job row → chapter_worker →
  session_translator job_meta_base` (the existing `job_meta_base` dict at `session_translator.py:889/1159`
  is spread into every per-chunk/per-attempt `submit_and_wait` — add `campaign_id` there). In worker-ai,
  the runner threads it into its `submit_and_wait(job_meta=…)`. Verified: provider-registry `mergeJobMeta`
  preserves caller keys, so the max_tokens-cap merge will not clobber `campaign_id`.

### 5.2 Transactional usage outbox (provider-registry, decision C)

New table `usage_outbox` in provider-registry DB:

| col | type | note |
|---|---|---|
| `id` | bigserial PK | relay cursor |
| `request_id` | uuid | = job_id; idempotency key for consumers |
| `owner_user_id` | uuid | |
| `campaign_id` | uuid NULL | from `job_meta.campaign_id`; NULL ⇒ non-campaign job |
| `model_source` / `model_ref` | text / uuid | |
| `operation` | text | → `purpose` |
| `input_tokens` / `output_tokens` | int | |
| `cost_usd` | numeric(16,8) NULL | from `actualUSD()`; NULL only when unresolvable (media) |
| `published_at` | timestamptz NULL | relay marks after XADD |
| `created_at` | timestamptz | |

**Atomicity:** the outbox row is inserted **in the same DB tx as `Repo.Finalize`** (the job→terminal
transition). `finalizeAndNotify` changes to: on `status == completed`, compute cost_usd + read
`job_meta.campaign_id`, then `Repo.FinalizeWithUsageOutbox(...)` does the UPDATE + INSERT atomically
(rowsAffected gate preserved — no outbox row when the cancel raced). This **replaces** the fire-and-forget
`RecordUsage` HTTP call. Guardrail reconcile/release stays as-is (separate, backstopped lifecycle).

**Relay** (new goroutine in provider-registry, mirrors the Python relay): poll
`SELECT … WHERE published_at IS NULL ORDER BY id LIMIT N`, for each:
- XADD to `loreweave:events:usage` (**all** usage — for the billing consumer), `MAXLEN ~ <cfg>`.
- if `campaign_id IS NOT NULL`: also XADD to `loreweave:events:campaign_usage` (**G8 dedicated,
  bounded** — only campaign-tagged, so the campaign consumer never scans platform-wide chat usage).
- mark `published_at = now()`.

At-least-once (a crash between XADD and mark → re-publish) + idempotent consumers = exactly-once effect.

### 5.3 usage-billing consumer (real-cost quota deduction — fixes #3 + #4)

usage-billing (Go) gains a **Redis stream consumer** on `loreweave:events:usage` (group
`usage-biller`). Per event it runs the **existing `recordInvocation` deduction logic refactored into a
shared core**, but deducts using the event's **`cost_usd`** (real per-model) instead of
`totalTokens × 0.000002`. Idempotent on `request_id` (existing `usage_logs` UNIQUE + deferred-deduction
pattern is reused unchanged).

- The HTTP `/record` endpoint stays for any non-job caller / back-compat, but **job usage now flows via
  the event** (provider-registry no longer calls it from settle). The flat constant is removed from the
  shared core; a NULL `cost_usd` (media) falls back to the reservation estimate path (no token-flat).
- **Quota model note:** `account_balances` is token-denominated (`month_quota_remaining_tokens`). The
  deduction still debits tokens for the quota window; `cost_usd` drives the **credits** (USD) leg and the
  audit `usage_logs.cost_usd`. (Confirm the exact column semantics at BUILD — see open item O-1.)

### 5.4 campaign-service spend accumulation + cap (G4, #1, #2)

Schema (campaign DB):
- `campaigns.budget_usd numeric(16,8) NULL` (NULL ⇒ uncapped), `campaigns.spent_usd numeric(16,8) NOT NULL DEFAULT 0`.
- `campaign_usage_seen(request_id uuid PRIMARY KEY, campaign_id uuid, cost_usd numeric, seen_at)` —
  **dedup ledger** so at-least-once redelivery never double-counts (the sum-across-a-boundary bug class).

New consumer on `loreweave:events:campaign_usage` (extends the existing `ProjectionConsumer` infra /
same group machinery, new group `campaign-spend`):
```
on usage event (has campaign_id, cost_usd):
  INSERT INTO campaign_usage_seen(request_id, …) ON CONFLICT DO NOTHING   -- idempotent guard
  if inserted 0 rows: ack, skip (already counted)
  else: UPDATE campaigns SET spent_usd = spent_usd + cost_usd WHERE campaign_id=…
        if budget_usd IS NOT NULL AND spent_usd >= budget_usd AND status='running':
            pause the campaign (reuse S3c pause: status→paused, driver stops new dispatch)
```
- **Reactive** (PO decision 2): the pause fires after the crossing event is consumed; in-flight jobs
  drain. Overshoot ≈ (in-flight provider jobs) × per-job cost — bounded by the driver in-flight ceiling.
- `cost_usd` NULL (media — not on the campaign path today) ⇒ skip accumulation (dedup row still written).
- Pause is **idempotent** (`WHERE status='running'`) — composes with breaker-pause (S3c-2b) and manual pause.

### 5.5 Wizard pre-launch estimate (out of S4)

The wizard's cost+time review screen (heuristic→sampling) is **S5/S6 FE**. S4 provides only the
runtime cap + tracking. The cap default may later be seeded from the estimate; not required here.

## 6. Failure modes / edge cases

| Case | Handling |
|---|---|
| Relay crash mid-publish | outbox row not marked → re-published; consumers idempotent (request_id). |
| Duplicate Redis delivery | `usage_logs` UNIQUE (billing) + `campaign_usage_seen` PK (campaign) dedup. |
| `cost_usd` NULL (media/unpriced) | billing → reservation-estimate fallback; campaign → skip sum. |
| Job completes after campaign cancelled | usage still recorded (billing correct); campaign accumulation harmless (paused/cancelled campaign ignores cap re-trigger). |
| campaign_id present but campaign gone | `UPDATE … WHERE campaign_id` affects 0 rows — no-op, ack. |
| Overshoot past cap | accepted (PO); bounded by in-flight ceiling; documented. |
| Two relay/consumer replicas | Redis consumer-group gives exclusive delivery per message; outbox relay needs single-writer or `FOR UPDATE SKIP LOCKED` claim (mirror S3c claim pattern). |

## 7. Proposed BUILD sub-slicing (PO to confirm)

S4 is XL across 4 services + migrations + a new money path. Recommend decomposing like S3:

- **S4a — correlation threading.** `campaign_id` through dispatch → job_meta → `llm_jobs`. No behavior
  change yet (campaign_id just rides along). Small, independently verifiable.
- **S4b — usage outbox + relay + dual Redis streams** (provider-registry). Replaces fire-and-forget
  RecordUsage; `loreweave:events:usage` + `:campaign_usage` flowing. No consumer yet.
- **S4c — usage-billing consumer + real-cost deduction** (fixes #3/#4). Exactly-once billing.
- **S4d — campaign spend accumulation + cap pause** (G4, #1, #2). The user-visible feature.
- (FE budget field on create + monitor spend display → folds into **S5/S6**.)

Each slice gets its own loom + live-smoke. **AMAW recommended** for S4b–S4d (money path, multi-system
contract, schema changes) — raise at the per-slice BUILD checkpoint.

## 7a. Build plan (file-level, per slice)

**S4a — correlation threading** (no behavior change; campaign_id rides along)
- campaign: `clients/dispatch_clients.py` (+`campaign_id` in both dispatch bodies), `saga/driver.py` (pass it).
- translation: `routers/internal_dispatch.py` (accept `campaign_id`), job-create core + `translation_jobs`
  migration (`campaign_id` column), `chapter_worker.py`→`session_translator.py` thread into `job_meta_base`.
- knowledge/worker-ai: `dispatch-extraction` accept `campaign_id` → extraction job row → runner
  `submit_and_wait(job_meta={…,"campaign_id"})`.
- provider-registry: `mergeJobMeta` add reserved `campaign_id` key constant (preserve on cap-merge).
- Verify: unit (id present in job_meta at each hop) + a focused multi-hop test.

**S4b — usage outbox + relay + dual streams** (provider-registry, Go)
- migration: `usage_outbox` table (§5.2). `jobs/repo.go`: `FinalizeWithUsageOutbox` (UPDATE+INSERT one tx).
- `jobs/worker.go finalizeAndNotify`: compute cost_usd + read job_meta.campaign_id, call the new finalize;
  **remove** the fire-and-forget `RecordUsage` call. New `jobs/usage_relay.go` (poll→XADD `:usage` +
  conditional `:campaign_usage`, MAXLEN; claim via `FOR UPDATE SKIP LOCKED` per O-3). config: stream names
  + MAXLEN + relay interval. compose: REDIS already present.
- Verify: outbox-row-written-in-finalize-tx test; relay XADD + mark-published; campaign_usage only when tagged.

**S4c — usage-billing consumer + real-cost deduction** (Go; fixes #3/#4)
- Refactor `recordInvocation` deduction into a shared core taking `cost_usd`. New Redis consumer on
  `loreweave:events:usage` (group `usage-biller`) → shared core, idempotent on request_id. Remove flat
  constant from the core; NULL cost_usd → reservation-estimate fallback. Resolve O-1/O-2 first.
- Verify: consumer idempotency (same request_id twice → one deduction); real-cost vs flat; live cross-service.

**S4d — campaign spend accumulation + cap pause** (campaign-service, Python; G4/#1/#2)
- migration: `campaigns.budget_usd`/`spent_usd`, `campaign_usage_seen`. `models.py`+`CreateCampaignPayload`
  (`budget_usd`). New consumer on `loreweave:events:campaign_usage` (group `campaign-spend`) → dedup-insert
  → accumulate → pause-at-cap (reuse S3c pause repo fn). `repositories.py` accumulate+pause query.
- Verify: dedup (no double-count), pause-at-cap (idempotent, composes w/ breaker-pause), live-smoke (D-S4-LIVE-SMOKE).

## 8. Open items for BUILD

- **O-1** — exact `account_balances` token-vs-USD column semantics; confirm how `cost_usd` maps to the
  credits leg without breaking the existing token-quota window. (Read usage-billing migrate + the rest of
  `recordInvocation` before S4c.)
- **O-2** — Go Redis-stream consumer in usage-billing: no Go consumer precedent in this service yet;
  confirm a shared lib or write a minimal `xreadgroup` loop (book/auth services are Go — check for one).
- **O-3** — outbox relay singleton vs claim (`FOR UPDATE SKIP LOCKED`) — reuse the S3c driver-claim
  pattern if provider-registry runs >1 replica.
- **O-4** — `cost_usd` for **knowledge** jobs: confirm worker-ai's provider jobs carry `usage` tokens so
  `actualUSD()` resolves (else campaign under-counts extraction spend).
- **O-5** — does the guardrail reconcile also want the campaign correlation for per-user reporting? Out
  of scope; note only.

## 9. Deferred rows (seed for SESSION)

- `D-S4-LIVE-SMOKE` — real campaign with a low `budget_usd` over a multi-chapter run: usage events flow
  end-to-end, `spent_usd` climbs, campaign auto-pauses at the cap, resume works.
- `D-S4-REVERSE-EST` (G8 follow) — tune `loreweave:events:campaign_usage` MAXLEN under a 4000-chapter
  all-skip re-run (S2 skip-event amplification interaction).
