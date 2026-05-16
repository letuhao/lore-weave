# LLM Pipeline Phase 6a — Subsystem A: USD Spend Guardrail

> **Status**: DESIGN — `/review-impl` round 1 complete (3 HIGH + 8 MED + 4 LOW,
> all folded inline). Ready for BUILD.
> **Created**: 2026-05-16 (session 57, cycle C-LLM-PHASE-6A)
> **Implements**: Subsystem A of [BILLING_MODEL_REDESIGN_ADR.md](./BILLING_MODEL_REDESIGN_ADR.md).
> **Driver**: protect the user's wallet — a pre-flight USD spend guardrail on
> every background LLM job, BYOK and platform alike.

---

## 1. Scope

This cycle implements **Subsystem A (spend guardrail) for the job path only** —
`POST /v1/llm/jobs`. It delivers: USD per-user budgets with calendar
daily/monthly windows; per-model USD pricing; a pre-flight worst-case estimate
that rejects **402** before the provider is called; `max_tokens` capping;
estimate-based reservation with terminal reconciliation.

**Explicitly deferred (not this cycle):**
- **`6a-δ` — streaming guardrail.** `POST /v1/llm/stream` is a distinct
  mechanism (no job row, per-chunk tally, hard mid-stream abort). The ADR §3.4
  committed the *approach*; implementing it is its own sub-cycle so 6a stays a
  coherent ~22-file XL. The job path is the bulk of the spend surface
  (extraction, translation, media gen are all jobs).
  **Known interim gap (/review-impl MED#9):** between 6a and 6a-δ,
  `/v1/llm/stream` — interactive chat, the busiest LLM surface — has **no
  spend guardrail at all**. This is an accepted, time-boxed exposure;
  **6a-δ should be scheduled immediately after 6a**, not left open-ended.
- **`6a-β`** — Subsystem B (platform resale ledger). `account_balances` and
  the legacy `/internal/model-billing/record` are left untouched this cycle.
- **`6a-γ`** — the FE for users to view/configure their guardrail. Until then
  the guardrail runs on **config-default** limits for every user.

## 2. CLARIFY decisions (settled with the user)

| # | Decision |
|---|----------|
| 1 | **Text-model pricing** is pre-filled from a platform-maintained default price table at model registration, editable; an unknown text model with no price is **fail-closed** (its jobs 402 until priced). |
| 2 | **Image/video/audio pricing** is per-model, user-entered at registration — no default table, fail-closed (consistent with text fail-closed). |
| 3 | Windows reset on **calendar** boundaries — daily 00:00 UTC, monthly on day 1. |
| 4 | The streaming USD tally (6a-δ) updates **per re-framed chunk**. |

## 3. Design

### 3.1 Schema

**usage-billing-service** `internal/migrate/migrate.go` — two new tables
(idempotent `CREATE TABLE IF NOT EXISTS`, following the repo pattern):

```sql
CREATE TABLE IF NOT EXISTS spend_guardrails (
  owner_user_id             UUID PRIMARY KEY,
  daily_limit_usd           NUMERIC(16,8) NOT NULL,
  monthly_limit_usd         NUMERIC(16,8) NOT NULL,
  daily_spent_usd           NUMERIC(16,8) NOT NULL DEFAULT 0,
  monthly_spent_usd         NUMERIC(16,8) NOT NULL DEFAULT 0,
  reserved_usd              NUMERIC(16,8) NOT NULL DEFAULT 0,
  daily_window_date         DATE NOT NULL DEFAULT (now() AT TIME ZONE 'utc')::date,
  monthly_window_month      DATE NOT NULL DEFAULT date_trunc('month', now() AT TIME ZONE 'utc'),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS token_reservations (
  reservation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id    UUID NOT NULL,
  job_id           UUID,
  estimated_usd    NUMERIC(16,8) NOT NULL,
  status           TEXT NOT NULL DEFAULT 'held'
                     CHECK (status IN ('held','reconciled','released','swept')),
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_token_reservations_sweep
  ON token_reservations(expires_at) WHERE status = 'held';
CREATE UNIQUE INDEX IF NOT EXISTS idx_token_reservations_job
  ON token_reservations(job_id) WHERE status = 'held' AND job_id IS NOT NULL;
```

- Calendar windows are a `DATE` / month-`DATE` — lazy reset compares the
  stored date to *now*; no `_started_at` timestamp needed (ADR's lazy-reset
  mechanism, calendar policy).
- Partial unique index on `job_id WHERE status='held'` makes `reserve`
  idempotent per job (a retried submit cannot double-hold).

**provider-registry-service** `internal/migrate/migrate.go` — one ALTER:

```sql
ALTER TABLE user_models ADD COLUMN IF NOT EXISTS pricing JSONB NOT NULL DEFAULT '{}'::jsonb;
```

`platform_models` already has `pricing_policy JSONB` — reused, no migration.

### 3.2 Pricing model

Pricing is a JSONB object; the estimator reads only the dimensions an
operation needs (ADR §3.3):

```json
{ "input_per_mtok": 0.15, "output_per_mtok": 0.60,   // text ops
  "per_image": 0.04, "per_second": 0.05, "per_kchar": 0.015 }
```

- **Empty `{}` or a missing required dimension ⇒ unpriced ⇒ fail closed** —
  the job is rejected `402` (`LLM_QUOTA_EXCEEDED`, message "model pricing not
  configured"). Never treated as 0.
- **Explicit `0` is a priced state** — a genuinely-free local model is
  registered with the dimension set to `0`; it passes the gate and
  contributes $0.
- **Default price table** — `internal/billing/default_pricing.go`: a static
  map keyed by `(provider_kind, model_name)` for well-known cloud text models
  (OpenAI, Anthropic, Gemini). Consulted **at user-model registration** to
  pre-fill `user_models.pricing` (CLARIFY #1). Media models are not in the
  table (CLARIFY #2).

### 3.3 The estimator — `internal/billing/estimate.go` (provider-registry)

`EstimateUSD(operation string, input map[string]any, pricing Pricing,
nchunks int) (float64, error)` — a **worst-case upper bound**. "Upper bound"
is load-bearing: an estimate that can be *below* the real cost is not a
guardrail. Every rule below is chosen to over-, never under-, estimate.

**Token estimation must be multilingual-safe (/review-impl HIGH#1).**
LoreWeave is a multilingual novel platform (CLAUDE.md) — `chars/4` is the
English *average* and is **not** an upper bound: CJK / Thai / Devanagari text
tokenizes at roughly **1 token per character**, so `chars/4` would
under-estimate a Chinese chapter ~4×. The estimator therefore detects the
dominant script and picks a **conservative** divisor:

```
non-ASCII-heavy input (CJK/Thai/…)  → tokens_in = ceil(chars / 1.0)
predominantly ASCII/Latin input     → tokens_in = ceil(chars / 3.5)
```

Both divisors sit at or *below* the real average chars-per-token ratio for
their script, so the estimate stays an upper bound. The "non-ASCII-heavy" test
is a cheap byte ratio (share of multibyte runes above a threshold). When in
doubt, fall to the CJK divisor — over-estimating is safe, under-estimating is
the bug.

> **BUILD correction.** An earlier draft of this section used a CJK divisor of
> `1.1`. That is wrong: `ceil(chars / 1.1) ≈ 0.91·chars`, which UNDER-bounds a
> script that tokenizes at ~1 token per character — the exact guardrail
> failure HIGH#1 set out to fix. Corrected to `1.0` with the user during the
> Phase 6a BUILD (`estimate.go cjkDivisor`).

| Operation | Estimate |
|-----------|----------|
| chat / completion | `tokens_in` (above) + `tokens_out = max_tokens` (or `MAX_OUTPUT_TOKENS_DEFAULT` if omitted); `usd = tokens_in/1e6·input_per_mtok + tokens_out/1e6·output_per_mtok` |
| translation | `tokens_in` + `tokens_out = ceil(tokens_in · 1.5)` — translation output **scales with input** and carries no request `max_tokens`; a flat ceiling would under-bound a chapter-sized job (/review-impl MED#4) |
| entity/relation/event/fact extraction | `tokens_in` + `tokens_out = EXTRACTION_OUTPUT_CEILING` (a generous per-op constant — extraction output is a bounded JSON list, not input-proportional) |
| embedding | `tokens_in` only |
| image_gen | `n · per_image` |
| video_gen | `duration_seconds · per_second` |
| tts / audio_gen | `total_chars/1000 · per_kchar` |
| stt | audio bytes → char-equivalent `bytes/CHAR_BYTES` then per_kchar; flat fallback if unknown |

- **Chunked jobs (/review-impl MED#5):** the extraction/translation pipeline
  re-sends the system prompt + KNOWN_ENTITIES context on **every** chunk. The
  estimate adds `(nchunks − 1) · system_prompt_tokens` on top of the raw-input
  token count — a 10-chunk job sends the prompt 10×. `nchunks` is derived from
  the submission's `chunking` config; absent ⇒ `nchunks = 1`.
- Returns an **error** if a required pricing dimension is absent → caller
  maps to 402 (fail closed). "Model not found" is a *different* error — see
  §3.5 (/review-impl MED#7).
- All arithmetic rounds **up** to the last `NUMERIC(16,8)` unit — no job is
  ever free-by-rounding.

### 3.4 usage-billing endpoints

All under `/internal/billing/guardrail`, `X-Internal-Token` auth (mirrors the
existing `/internal/model-billing` group).

All window-date comparisons below use the **DB clock**
(`(now() AT TIME ZONE 'utc')::date`) inside the transaction — never an
app-supplied date — so clock skew near midnight cannot double-reset or skip a
reset (/review-impl MED#8).

**`POST …/reserve`** — `{ owner_user_id, job_id, estimated_usd }`
→ `200 { reservation_id }` or `402 { code:"INSUFFICIENT_BUDGET",
daily_available, monthly_available, requested }`.

Transaction:
1. `INSERT INTO spend_guardrails(owner_user_id, daily_limit_usd,
   monthly_limit_usd) VALUES (...) ON CONFLICT DO NOTHING` — seed from
   **config defaults** if first time.
2. **Idempotency check first:** `SELECT reservation_id FROM token_reservations
   WHERE job_id = $1 AND status = 'held'`. If a row exists, **return it
   immediately** — do not insert, do not touch `reserved_usd`. This is the
   duplicate-submit path; the `reserved_usd +=` of step 6 MUST be skipped
   (/review-impl HIGH#3 — the `+=` is a separate statement from the INSERT, so
   `ON CONFLICT DO NOTHING` alone would still double-count the hold).
3. `SELECT … FOR UPDATE` the guardrail row (ADR concurrency).
4. **Lazy calendar reset:** if `daily_window_date < (now() AT TIME ZONE
   'utc')::date` → `daily_spent_usd = 0, daily_window_date = <db today>`;
   likewise `monthly_window_month`.
5. `daily_available = daily_limit − daily_spent − reserved_usd`; same for
   monthly. (`reserved_usd` is a single column shared across both windows — a
   held amount will land in both `daily_spent` and `monthly_spent` at
   reconcile, so subtracting it from both availabilities is consistent.)
6. If `estimated_usd > min(daily_available, monthly_available)` → **402**.
7. Else, **as one atomic unit**: `INSERT token_reservations(status='held',
   expires_at = now + RESERVATION_TTL)` **and** `UPDATE spend_guardrails SET
   reserved_usd = reserved_usd + estimated_usd`. Both run only on the
   non-duplicate path (step 2 already returned for duplicates).
   `RESERVATION_TTL` is set comfortably above the longest job timeout
   (`VideoGenJobTimeout` = 30 min) — see the reconcile note on swept jobs.

**`POST …/reconcile`** — `{ reservation_id, actual_usd }` → `200`. Tx,
`FOR UPDATE` the guardrail row; branch on the reservation's stored `status`:
- `held` → lazy-reset windows; `daily_spent += actual_usd`,
  `monthly_spent += actual_usd`; `reserved_usd -= reservation.estimated_usd`
  (the **reservation row's** stored estimate, not a request field); status
  → `reconciled`.
- `swept` → the sweeper already released the hold; **still record the spend**
  — `daily_spent += actual_usd`, `monthly_spent += actual_usd`; do **not**
  touch `reserved_usd`; status → `reconciled`. (/review-impl HIGH#2 — a long
  job whose hold timed out and was swept mid-run still completed and spent
  real money; dropping that spend would leak. Reconcile records spend
  regardless of a prior sweep.)
- `reconciled` → true no-op (idempotent — covers a retried reconcile call).
- `released` → no-op (a `released` job failed; it should not be reconciled —
  defensive).

Actual may exceed estimate — `*_spent` can surpass `*_limit` by one job's
overshoot. That is acceptable: the guardrail bounds *new* work (the next
reserve 402s), it does not abort in-flight work.

**`POST …/release`** — `{ reservation_id }` → `200`. Tx, `FOR UPDATE`: if
status is not `held` → no-op (idempotent); else `reserved_usd -=
reservation.estimated_usd`, status → `released`. For failed/cancelled jobs —
the hold is freed, no spend recorded.

**Sweeper** — a background goroutine in usage-billing (ticker, e.g. every
5 min): for every `held` reservation past `expires_at`, `FOR UPDATE` the
guardrail row, `reserved_usd -= estimated_usd`, status → **`swept`** (a
distinct state from `released` so a later `reconcile` knows to still record
the spend — see reconcile above). Crash-leak safety (ADR §3).

### 3.5 Gateway hooks (provider-registry)

`llm_jobs` gains `reservation_id UUID` (migration) so the worker can
reconcile/release.

**Pre-flight — `jobs_handler.go doSubmitJob`** (after input validation, before
job insert):
1. Look up the model by `model_ref` — `user_models` (when
   `model_source='user_model'`) or `platform_models`. **If no such model
   exists → 404 `LLM_MODEL_NOT_FOUND`** — a bad `model_ref` is a not-found
   error, not a pricing error (/review-impl MED#7). Only a model that *exists*
   but whose `pricing` JSONB lacks a required dimension takes the fail-closed
   402 path.
2. `EstimateUSD(operation, input, pricing, nchunks)` — on the unpriced error
   → **402 `LLM_QUOTA_EXCEEDED`** ("model pricing not configured").
3. `max_tokens` cap (chat/completion **only**): affordable output =
   `(min(daily_available, monthly_available) − estimated_input_cost) /
   output_price_per_tok` — the **input cost is subtracted first**
   (/review-impl LOW#12). If the request's `max_tokens` exceeds the affordable
   count, cap it in the stored input **and surface the cap** — set
   `max_tokens_capped:{requested,applied,reason:"budget"}` on the job's
   `job_meta` so the result is not *silently* truncated (/review-impl MED#6).
   If even a usable-minimum output is unaffordable, step 4's reserve 402s.
   Non-chat operations are **never** capped — they 402 instead (truncating a
   translation/extraction artifact is corruption, not degradation).
4. Call usage-billing `…/reserve`. 402 → propagate 402 to the caller (no job
   row created). 200 → carry `reservation_id` onto the job row.

> **Orphaned-reservation note (/review-impl LOW#13):** `reserve` succeeds
> *before* the `INSERT llm_jobs`. If the job insert then fails, the
> reservation is `held` with no job to reconcile it — **accepted**: the
> `expires_at` sweeper releases it. The window is bounded by `RESERVATION_TTL`.

**Reconcile — `worker.go finalizeAndNotify`** (the single terminal hook):
- terminal `completed` → actual USD computed from the job's real
  `Usage{InputTokens,OutputTokens}` × the model pricing → `…/reconcile`.
- terminal `failed` / `cancelled` → `…/release`.
- Both are best-effort with logging — a billing-service blip must not change
  the job's terminal state; the `expires_at` sweeper is the backstop.

**A usage-billing client** — `internal/billing/client.go` in provider-registry
(reserve / reconcile / release), short-timeout `http.Client`, mirrors the
existing `recordInvocation` HTTP pattern.

### 3.6 Config

usage-billing `config.go` — `GUARDRAIL_DEFAULT_DAILY_USD`,
`GUARDRAIL_DEFAULT_MONTHLY_USD` (required envs, no hardcoded literal — ADR P5);
`RESERVATION_TTL` (sweeper horizon — **must exceed the longest job timeout**;
default ≥ 45 min against `VideoGenJobTimeout` = 30 min, so a normal job is
never swept mid-run). docker-compose seeds them. provider-registry
`config.go` — `MAX_OUTPUT_TOKENS_DEFAULT` (estimate ceiling when a
chat/completion request omits `max_tokens`) + `EXTRACTION_OUTPUT_CEILING` (the
per-op output-token estimate for extraction jobs, §3.3).

## 4. Files (~22 — 4 NEW + 18 MOD)

| File | Change |
|------|--------|
| `docs/03_planning/LLM_PIPELINE_PHASE6A_DESIGN.md` | NEW (this doc) |
| usage-billing `internal/migrate/migrate.go` | + 2 tables |
| usage-billing `internal/api/guardrail.go` | NEW — reserve/reconcile/release handlers |
| usage-billing `internal/api/guardrail_test.go` | NEW — handler + window-reset + concurrency tests |
| usage-billing `internal/api/server.go` | + route group; mount sweeper |
| usage-billing `internal/billing/sweeper.go` | NEW — leaked-reservation sweeper |
| usage-billing `internal/config/config.go` (+test) | + default-limit envs |
| provider-registry `internal/migrate/migrate.go` | + `user_models.pricing`; + `llm_jobs.reservation_id` |
| provider-registry `internal/billing/estimate.go` (+test) | NEW — `EstimateUSD` |
| provider-registry `internal/billing/default_pricing.go` (+test) | NEW — default price table |
| provider-registry `internal/billing/client.go` (+test) | NEW — guardrail client |
| provider-registry `internal/api/jobs_handler.go` (+test) | pre-flight estimate + reserve + 402 + max_tokens cap |
| provider-registry `internal/jobs/worker.go` (+test) | reconcile/release in `finalizeAndNotify` |
| provider-registry `internal/jobs/repo.go` | + `reservation_id` on the Job row |
| provider-registry user-model registration handler (+test) | accept `pricing`; pre-fill from default table |
| provider-registry `internal/config/config.go` | + `MAX_OUTPUT_TOKENS_DEFAULT` |
| `contracts/api/llm-gateway/v1/openapi.yaml` | + 402 on `/v1/llm/jobs`; guardrail internal endpoints |
| `infra/docker-compose.yml` | + guardrail default-limit envs |

## 5. Test plan

- **estimator** — per-operation upper-bound correctness; unpriced dimension →
  error; explicit-`0` → $0; rounds up. **Multilingual (/review-impl MED#10):**
  a CJK input case asserting `estimate ≥ real token count` — would FAIL under a
  `chars/4` divisor; locks the §3.3 script-aware divisor. Translation
  output-scales-with-input case; chunked-job per-chunk-overhead case.
- **reserve** — happy; 402 over daily; 402 over monthly (tighter window wins);
  lazy daily reset; lazy monthly reset; **duplicate `job_id` → same
  reservation AND `reserved_usd` unchanged on the 2nd call** (/review-impl
  HIGH#3 regression-lock); a `FOR UPDATE` source grep-lock + a pure
  available-budget-formula unit test (/review-impl LOW#14 — a real
  two-connection race test is flaky; lock the formula + the lock instead).
- **reconcile** — `held` → adds actual to both windows + frees the hold;
  **`swept` → still adds actual to both windows, does NOT touch
  `reserved_usd`** (/review-impl HIGH#2 regression-lock); `reconciled` → true
  no-op; actual > estimate tolerated.
- **release** — frees the hold; idempotent; failure path records no spend.
- **sweeper** — a `held` past `expires_at` → status `swept` + `reserved_usd`
  decremented.
- **doSubmitJob** — non-existent `model_ref` → **404** not 402 (/review-impl
  MED#7); existing-but-unpriced model → 402; over-budget → 402 (no job row);
  happy → job carries `reservation_id`; budget-tight chat → `max_tokens`
  capped AND `job_meta.max_tokens_capped` present, not silent (/review-impl
  MED#6).
- **finalizeAndNotify** — completed → reconcile with actual; failed → release;
  billing-blip → job still finalised.
- **default pricing** — known model pre-fills; unknown → empty (fail-closed).
- DML-level FK bypass for cross-table test setup (memory
  `feedback_test_ddl_vs_dml_bypass`).

## 6. Build order

1. usage-billing: migrate (2 tables) → config envs → `guardrail.go` handlers
   → route → `sweeper.go` → tests.
2. provider-registry: migrate (pricing col + reservation_id) → `estimate.go`
   → `default_pricing.go` → `client.go` → tests for each.
3. provider-registry: `doSubmitJob` pre-flight + `max_tokens` cap → user-model
   registration pricing pre-fill → `worker.go finalizeAndNotify` reconcile/
   release → `repo.go` → tests.
4. openapi + docker-compose.
5. VERIFY — both services `go build/vet/test`.

## 7. Deferrals (intentional)

- `D-PHASE6A-STREAMING-GUARDRAIL` — Subsystem A for `/v1/llm/stream` (6a-δ);
  ADR §3.4 approach stands.
- `D-PHASE6A-LIVE-SMOKE` — manual: a real over-budget job returns 402.
- `D-PHASE6A-PRICING-FE` — the model-registration pricing form (6a-γ).
- Carry-forward: 6a-β (Subsystem B), 6c (OTel).
