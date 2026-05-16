# LLM Pipeline Phase 6a-β — Subsystem B: Platform Resale Ledger

> Status: DESIGN. Implements Subsystem B of
> [BILLING_MODEL_REDESIGN_ADR.md](./BILLING_MODEL_REDESIGN_ADR.md) §3, plus the
> `/record` wiring/idempotency the ADR §3.4 calls for.

## 1. Scope

6a (Subsystem A) + 6a-δ (streaming) protect the **user's** wallet on every
job. Subsystem B protects **LoreWeave's** wallet — what a user owes for
LoreWeave-funded `platform_model` calls: a config-driven free tier plus
prepaid credits, both in USD.

In scope:
1. `platform_balances` ledger; config-seeded free tier.
2. The `platform_model` 402 gate, **reserving** alongside Subsystem A in one
   transaction (CLARIFY decision — not a loose "check").
3. Reconcile that deducts actual USD: free tier first, then credits.
4. Wire the gateway's unwired `recordInvocation` into the worker's
   `settleBilling` (the gateway becomes the model-level biller).
5. Fix `/record`'s `account_balances` double-deduct (idempotency by
   `request_id`).

Out of scope (CLARIFY finding — the ADR's "remove the 3 caller `/record`
calls" contradicts the code: `book-service/media.go:545` records an
**application-level** `purpose` the gateway has no knowledge of). The caller
`/record` calls **stay**; 6a-γ (FE) is unchanged.

## 2. CLARIFY decisions

1. **B reserves, consistent with A.** A `platform_model` job's pre-flight
   reserves against `platform_balances` in the **same transaction** as the
   Subsystem A reservation — one atomic gate, no concurrency hole.
2. **Scope** = Subsystem B core + wire `recordInvocation` + `/record`
   idempotency. Caller `/record` calls kept.

## 3. Design

### 3.1 Schema

```
-- NEW
platform_balances(
  owner_user_id               UUID PRIMARY KEY,
  free_tier_allowance_usd     NUMERIC(16,8) NOT NULL,           -- config-seeded, no DDL default
  free_tier_used_usd          NUMERIC(16,8) NOT NULL DEFAULT 0,
  free_tier_window_month      DATE NOT NULL DEFAULT (now() AT TIME ZONE 'utc')::date,
  credits_balance_usd         NUMERIC(16,8) NOT NULL DEFAULT 0,
  reserved_usd                NUMERIC(16,8) NOT NULL DEFAULT 0, -- held platform reservations
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
)
-- token_reservations gains:
ALTER TABLE token_reservations
  ADD COLUMN model_source TEXT NOT NULL DEFAULT 'user_model'
  CHECK (model_source IN ('user_model','platform_model'));
```

`reserved_usd` on `platform_balances` is **beyond the ADR §3.2 schema** — the
ADR sketched a check-only Subsystem B; the CLARIFY decision to *reserve*
requires a held-amount column, mirroring `spend_guardrails.reserved_usd`.
`token_reservations.model_source` lets reconcile / release / sweep know
whether a reservation also touches `platform_balances`.

Free-tier reset is a **lazy calendar-month** reset (mirroring
`spend_guardrails.monthly_window` exactly) — `free_tier_window_month` advanced
+ `free_tier_used_usd` zeroed inside the `FOR UPDATE` transaction.

### 3.2 Config

usage-billing `config.go` — `PLATFORM_FREE_TIER_USD`, a **required** env
(no DDL default — ADR P5). Seeded into a `platform_balances` row on first
contact. docker-compose sets it (test/UAT: the $-equivalent of ~100M tokens).

### 3.3 Reserve — `guardrailReserve` extended

The request gains `model_source`. The transaction (additions in **bold**):

1. Seed `spend_guardrails` (existing). **If platform: seed `platform_balances`
   from `PLATFORM_FREE_TIER_USD` (`ON CONFLICT DO NOTHING`).**
2. Idempotency check (existing) — a held reservation for `job_id` → return it.
3. `FOR UPDATE` + lazy reset `spend_guardrails` (existing).
4. **If platform: `FOR UPDATE` + lazy free-tier-month reset
   `platform_balances`.**
5. Subsystem A availability check (existing) → 402 `INSUFFICIENT_BUDGET` if
   over. **If platform: B availability = `(free_tier_allowance −
   free_tier_used − reserved) + credits_balance`; if `estimate > b_available`
   → 402 `PLATFORM_BALANCE_EXHAUSTED`.** A zero-cost job is never gated by
   either.
6. Insert `token_reservations` (**with `model_source`**); bump
   `spend_guardrails.reserved_usd`. **If platform: bump
   `platform_balances.reserved_usd`.**

Both gates in one tx — a `platform_model` job must pass **both**; a
`user_model` job only Subsystem A. The 402 body names which gate failed
(distinct `code`), so the FE can show the right message.

### 3.4 Reconcile / release / sweep — extended

`settleReservation` loads the reservation row, which now carries
`model_source`. After the Subsystem A settlement:

- **reconcile, platform** — lazy free-tier-month reset; then deduct `actual`:
  `from_free = min(actual, free_tier_allowance − free_tier_used)`;
  `free_tier_used += from_free`; `credits_balance_usd −= (actual − from_free)`.
  Drop `platform_balances.reserved_usd` by the reservation's `estimated_usd`
  (by `0` if the row was `swept` — mirrors the Subsystem A swept rule).
  `credits_balance_usd` may go slightly negative on an actual-exceeds-estimate
  overshoot — accepted, identical to Subsystem A's `*_spent` overshoot rule.
- **release, platform** — drop `platform_balances.reserved_usd` by
  `estimated_usd`; no spend.
- **sweeper, platform** — a swept `held` platform reservation also drops
  `platform_balances.reserved_usd`.

`user_model` reservations skip all of the above — unchanged from 6a.

### 3.5 Gateway integration

- `billing.GuardrailClient.Reserve` gains a `modelSource` argument; the
  reserve JSON body carries `model_source`. `Reconcile`/`Release` are
  unchanged — `settleReservation` reads `model_source` from the row.
- The four reserve call sites already have `model_source` in hand:
  `doSubmitJob` → `runGuardrailPreflight`; `doLlmStream` → `preflightStream`.
  Thread it through. No new logic at the call sites — the platform gate lives
  entirely in usage-billing.
- The 402 mapping: `PLATFORM_BALANCE_EXHAUSTED` → `402 LLM_QUOTA_EXCEEDED`
  with a "platform free tier / credits exhausted" message.

### 3.6 Wire `recordInvocation` (gateway as model-level biller)

The gateway's `recordInvocation` helper (`server.go`) is currently unwired.
The worker's `settleBilling`, on a `completed` job, also records model-level
usage to `/internal/model-billing/record`:

- `request_id = job_id` — the natural idempotency key (one job → one model-
  level record; a settle retry is a no-op once `/record` is idempotent).
- payload: `owner_user_id`, `model_source`, `model_ref`, `input_tokens` /
  `output_tokens` (from the result `usage` block), `request_status="success"`,
  `purpose = operation`, `provider_kind=""` (the worker does not resolve it —
  same `D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS` gap the callers accept),
  empty payloads (the encrypted-payload audit is the callers' concern).
- Best-effort, logged — never blocks the job's terminal state.

> **DESIGN-review finding — the `usage_logs.provider_kind` CHECK is stale.**
> `usage_logs` has `CHECK (provider_kind IN ('openai','anthropic','ollama',
> 'lm_studio'))`. provider-registry's migrate v3 already dropped the *same*
> CHECK on its own tables to allow custom providers (`gemini`, …) — the
> usage-billing copy was never updated. Consequences today: a `provider_kind`
> of `''` or `gemini` makes `/record` 500, so **`book-service`'s app-level
> `/record` calls (which post `provider_kind:""`) are silently failing
> already** (best-effort → warning logged → ignored). The gateway's wired
> `/record` would hit the identical wall. Fix (in the usage-billing
> migration): `ALTER TABLE usage_logs DROP CONSTRAINT … provider_kind_check`
> — consistent with provider-registry v3, and it un-breaks book-service as a
> side effect.

To avoid an `api → jobs` import, the worker calls a new
`billing.UsageClient.RecordUsage` (same package as `GuardrailClient`,
constructed in `NewServer`, injected into `NewWorker`). Streaming
(`streamGuard.settle`) does **not** record — interactive streams are
out of the `/record` model-level scope for this cycle (tracked deferral).

### 3.7 Fix `/record` idempotency

`recordInvocation` in usage-billing inserts `usage_logs` with
`ON CONFLICT (request_id) DO UPDATE` but the `account_balances` deduction runs
**unconditionally** — a retry with the same `request_id` double-deducts.
Fix: `INSERT … ON CONFLICT (request_id) DO NOTHING RETURNING usage_log_id`.
An empty result ⇒ this `request_id` was already recorded ⇒ skip the balance
deduction + the detail write, re-`SELECT` the existing `usage_log_id`, and
return it. The balance mutation now runs exactly once per `request_id`.

### 3.8 Files (~18)

| File | Change |
|------|--------|
| `docs/03_planning/LLM_PIPELINE_PHASE6A_BETA_DESIGN.md` | NEW (this doc) |
| usage-billing `internal/migrate/migrate.go` | + `platform_balances`; + `token_reservations.model_source`; **drop the stale `usage_logs.provider_kind` CHECK** |
| usage-billing `internal/config/config.go` (+test) | + `PLATFORM_FREE_TIER_USD` |
| usage-billing `internal/api/guardrail.go` | reserve/reconcile/release extended for platform |
| usage-billing `internal/api/sweeper.go` | sweep drops `platform_balances.reserved_usd` |
| usage-billing `internal/api/guardrail_test.go` | platform reserve/reconcile/release/sweep/free-tier-reset/credits tests |
| usage-billing `internal/api/server.go` | `/record` idempotency fix |
| usage-billing `internal/api/*_test.go` | `/record` idempotency regression test |
| provider-registry `internal/billing/client.go` (+test) | `Reserve` + `model_source`; NEW `UsageClient.RecordUsage` |
| provider-registry `internal/jobs/worker.go` (+test) | `settleBilling` records model-level usage on completed |
| provider-registry `internal/api/server.go` | construct `UsageClient`; inject into `NewWorker` |
| provider-registry `internal/api/jobs_handler.go` | `runGuardrailPreflight` passes `model_source` |
| provider-registry `internal/api/stream_billing.go` | `preflightStream` passes `model_source` |
| provider-registry `internal/api/*guardrail_integration_test.go` | platform-job 402 + happy |
| `infra/docker-compose.yml` | + `PLATFORM_FREE_TIER_USD` |

## 4. Test plan

- **reserve, platform** — happy (holds in both `spend_guardrails` AND
  `platform_balances`); 402 when over the free-tier+credits pool
  (`PLATFORM_BALANCE_EXHAUSTED`); 402 when over Subsystem A even with B room
  (both gates enforced); `user_model` reserve never touches `platform_balances`.
- **reconcile, platform** — actual within free tier → `free_tier_used`
  only; actual exceeding free tier → remainder hits `credits_balance_usd`;
  swept platform reservation → spend recorded, `reserved_usd` untouched;
  free-tier-month lazy reset.
- **release / sweep, platform** — `platform_balances.reserved_usd` dropped.
- **`/record` idempotency** — two calls, same `request_id` → `account_balances`
  deducted once (regression-lock the double-deduct).
- **estimator-side** — unchanged; reuse 6a coverage.
- DB-integration: a `platform_model` job submit → both ledgers move;
  reconcile → free-tier/credits move.

## 5. Deferrals

- `D-PHASE6A-BETA-STREAM-RECORD` — `streamGuard.settle` does not call
  `/record`; streaming model-level usage logging is a follow-up.
- `D-PHASE6A-BETA-ACCOUNT-BALANCES-RETIRE` — `account_balances` is ADR-
  superseded but `/record` still deducts it; a later cleanup removes that
  deduction once nothing reads `account_balances`.
- `D-PHASE6A-BETA-LIVE-SMOKE` — manual: a real platform job over free tier +
  credits returns 402.

## 6. Build order

1. usage-billing: migrate (`platform_balances` + `model_source`) → config →
   `guardrailReserve` platform branch → `settleReservation` platform branch →
   `sweeper` → tests.
2. usage-billing: `/record` idempotency fix + regression test.
3. provider-registry: `client.go` (`Reserve` + `model_source`,
   `UsageClient.RecordUsage`) → `worker.go settleBilling` record hook →
   `server.go`/`NewWorker` wiring → `jobs_handler.go` / `stream_billing.go`
   pass `model_source` → tests.
4. openapi note + docker-compose env.
5. VERIFY — both services build/vet/test.
