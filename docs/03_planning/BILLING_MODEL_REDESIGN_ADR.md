# ADR — LoreWeave Billing Model Redesign

> **Status**: DRAFT — `/review-impl` round 1 complete (3 HIGH + 6 MED + 3 LOW,
> all folded inline). Pending user sign-off.
> **Created**: 2026-05-15 (session 57, cycle C-BILLING-ADR)
> **Supersedes**: the original Phase 6a scope ("quota enforcement at job
> submission") in [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md) §6a.
> **Driver**: scoping Phase 6a surfaced that the current billing model does
> not protect the user, conflates two unrelated concerns, and uses the wrong
> unit. This ADR redesigns it before any 6a implementation.

---

## 1. Context — what exists today

`usage-billing-service` owns one table, `account_balances`:

```
account_balances(
  owner_user_id,
  month_quota_tokens            INT DEFAULT 100000,
  month_quota_remaining_tokens  INT DEFAULT 100000,
  credits_balance               INT DEFAULT 1000,
  billing_policy_version, ...
)
```

`POST /internal/model-billing/record` (`recordInvocation`) is called
**post-hoc** by callers (book-service, video-gen-service, chat-service) after
a provider call completes. It:
1. takes actual `input_tokens + output_tokens`,
2. computes `costUSD = totalTokens * 0.000002` (a **flat** rate),
3. deducts `totalTokens` from `month_quota_remaining_tokens`, overflowing into
   `credits_balance`; if both are insufficient → `decision = "rejected"`,
   `request_status = "billing_rejected"` — **but the provider call already
   happened**.

The gateway's own `recordInvocation` helper (`provider-registry server.go`)
is **unwired** — the gateway does not bill jobs; callers do.

LoreWeave is **BYOK + platform**: `model_source = "user_model"` uses the
user's own registered provider key (the user pays the provider directly);
`model_source = "platform_model"` uses a LoreWeave-funded model.

## 2. Problems

| # | Problem |
|---|---------|
| **P1** | **Wrong unit.** Billing is a token *count*. Models cost 10–30× different per token (gpt-4 vs gpt-4o-mini vs a local model). A flat token quota over-charges cheap models and under-charges expensive ones. The flat `0.000002`/token cost is fiction. |
| **P2** | **Does not protect the user.** For BYOK, the user's money sits at *their own provider account*. A runaway agent loop drains the user's OpenAI/Anthropic balance. LoreWeave imposes no guardrail on that — `account_balances` only meters an internal token count, which for BYOK is meaningless to the user's actual wallet. |
| **P3** | **Two concerns conflated.** A *wallet-protection guardrail* (cap runaway spend, protect the user) and a *platform resale ledger* (what the user owes LoreWeave for LoreWeave-funded models) are jammed into one `account_balances` row. They have different owners, units, and lifecycles. |
| **P4** | **Post-hoc only.** Rejection happens *after* the provider call — the tokens are already spent (the user's money for BYOK, LoreWeave's for platform). There is no pre-flight gate. |
| **P5** | **Hardcoded.** The free-tier allowance is a DDL `DEFAULT 100000`. It must be environment-configurable (test/UAT wants ~100M). |
| **P6** | **`model_source` mis-used as an enforcement switch.** An earlier 6a draft would gate by `platform_model` vs `user_model`. That is the wrong axis — BYOK jobs need wallet protection *more*, not less. |

Industry multi-provider gateways (LiteLLM, Bifrost, OpenRouter, Cloudflare AI
Gateway, any-llm-gateway) converge on: **USD-denominated per-user budgets,
enforced pre-flight by a worst-case cost estimate, with `max_tokens` capped to
the remaining budget so the response cannot overspend.** BYOK keeps spend
controls — it does not remove them.

## 3. Decision — split billing into two independent subsystems

### Subsystem A — Spend Guardrail (protects the user's wallet)

**Purpose:** stop runaway spend, on *any* provider, BYOK or platform.

- A per-user **USD budget** with two windows: a **daily** guardrail and a
  **monthly** ceiling (a single bad session must not drain the month).
- User-configurable; the platform supplies sensible defaults (config-driven,
  not hardcoded — see P5).
- Applies to **every** job — `user_model` and `platform_model` alike. This is
  the fix for P2/P6: BYOK is not exempt.
- **Pre-flight enforcement** (fixes P4): at job submission the gateway
  computes a **worst-case USD estimate** for the job and, if it exceeds the
  available budget, rejects **402 `LLM_QUOTA_EXCEEDED`** *before* the provider
  is called.
  - **Available budget (the invariant):** `available = window_limit −
    window_spent − reserved`. The check is `estimate ≤ available`, evaluated
    against **both** the daily and the monthly window — the tighter one wins.
    `reserved` (sum of currently-`held` reservations) MUST be in the formula
    or concurrent jobs over-commit.
  - **The estimate is a deliberate heuristic upper bound, not an invoice.**
    Token count is approximated (`ceil(chars / 4)` or similar — the gateway
    is Go and has no universal cross-family tokenizer); cost =
    `tokens_in_est × input_price + max_output_tokens × output_price` for
    token-priced operations, or the per-unit estimate of §3.3 for
    image/video/audio. Rounding is always **up**. Precision is recovered by
    post-call reconciliation; the estimate only needs to be a safe ceiling.
- **Concurrency:** the read-check-reserve step MUST run in one transaction
  holding a `SELECT … FOR UPDATE` row lock on the user's `spend_guardrails`
  row. A guardrail that can be raced is not a guardrail.
- **`max_tokens` capping:** for operations that accept it (chat/completion),
  the gateway caps `max_tokens` to what the remaining budget affords, so the
  response physically cannot overspend the window. Non-chat operations
  (image/video/audio) cannot be capped this way — they rely on the §3.3
  per-unit estimate being a true upper bound.
- **Post-call reconciliation:** actual USD cost is recorded against the window
  and the pre-flight reservation released (estimate-based reservation — the
  transient hold from the abandoned 6a, redenominated to USD).
- **Leaked-reservation sweep:** a `held` reservation whose job never reaches a
  terminal state (gateway crash, lost worker) would inflate `reserved` forever
  and permanently shrink the user's budget. A sweeper auto-releases `held`
  reservations past their `expires_at` (set to job-submit time + the maximum
  job runtime — `VideoGenJobTimeout` = 30 min is today's ceiling — plus
  margin).
- Unit is **USD** throughout (fixes P1).

### Subsystem B — Platform Resale Ledger (platform_model only)

**Purpose:** track what a user owes LoreWeave for LoreWeave-funded models.

- Engaged **only** when `model_source = "platform_model"`. BYOK jobs never
  touch Subsystem B (the user pays their provider directly).
- A **free-tier allowance** in **USD**, **config-driven** per environment
  (test/UAT ≈ $ equivalent of 100M tokens; prod set by policy) — never a DDL
  default (fixes P5).
- **Prepaid credits** in USD, on top of the free tier.
- On a `platform_model` job: estimate → if `estimate > free_tier_remaining +
  credits` → **402** (this is a *real* charge to LoreWeave, so the pre-flight
  gate matters here too). Post-call: deduct actual USD from free-tier then
  credits.
- Unit is **USD**, aligned with Subsystem A (fixes P1/P3).

### 3.1 Why two subsystems, not one

| | Subsystem A (guardrail) | Subsystem B (resale) |
|---|---|---|
| Protects | the **user's** wallet | **LoreWeave's** wallet |
| Applies to | every job (BYOK + platform) | platform_model only |
| Set by | the user (their cap) | LoreWeave (free-tier policy + the user's prepaid credits) |
| On exhaustion | 402 — "you set a spend limit" | 402 — "out of free tier / credits" |
| Unit | USD | USD |

A `platform_model` job passes **both** gates (the user's own guardrail *and*
their LoreWeave balance). A `user_model` job passes **only** Subsystem A.

### 3.2 Schema redesign

`account_balances` (token-count) is **superseded**. Current data is test/UAT
placeholder — no production data to preserve, so the migration is a clean
replacement, not a data-preserving transform.

```
-- Subsystem A
spend_guardrails(
  owner_user_id            UUID PRIMARY KEY,
  daily_limit_usd          NUMERIC(16,8),   -- user-configurable; default from config
  monthly_limit_usd        NUMERIC(16,8),
  daily_spent_usd          NUMERIC(16,8) DEFAULT 0,
  monthly_spent_usd        NUMERIC(16,8) DEFAULT 0,
  daily_window_started_at  TIMESTAMPTZ,
  monthly_window_started_at TIMESTAMPTZ,
  reserved_usd             NUMERIC(16,8) DEFAULT 0,   -- sum of 'held' reservations
  updated_at               TIMESTAMPTZ
)
token_reservations(
  reservation_id   UUID PRIMARY KEY,
  owner_user_id    UUID,
  job_id           UUID,
  estimated_usd    NUMERIC(16,8),
  status           TEXT CHECK (status IN ('held','released')),  -- transient hold
  expires_at       TIMESTAMPTZ,    -- sweeper auto-releases 'held' rows past this
  created_at, updated_at
)

-- Subsystem B
platform_balances(
  owner_user_id            UUID PRIMARY KEY,
  free_tier_allowance_usd  NUMERIC(16,8),   -- seeded from env/config, NOT a DDL default
  free_tier_used_usd       NUMERIC(16,8) DEFAULT 0,
  free_tier_period_started_at TIMESTAMPTZ,
  credits_balance_usd      NUMERIC(16,8) DEFAULT 0,
  updated_at               TIMESTAMPTZ
)
```

**`NUMERIC(16,8)` — 8 decimal places ($0.00000001).** 4-decimal "sub-cent" is
**not** enough: a 50-token gpt-4o-mini output (~$0.00003) or a 10-token call
(~$0.0000015) would each round to $0.0000 and accumulate as zero — many small
calls would leak un-metered and the guardrail would never trip. 8dp holds real
per-call LLM cost; each call's cost is rounded **up** to the last
representable unit so no call is ever free-by-rounding.

Free-tier amounts are **seeded by the service from config** (env var / config
file) at account creation, never by a column `DEFAULT` (P5).

**Window reset mechanism — lazy-on-access.** Whenever a guardrail row is read
for a reserve/reconcile, if `now − *_window_started_at` exceeds the window
length, `*_spent_usd` is zeroed and `*_window_started_at` advanced *within the
same `FOR UPDATE` transaction*. No cron. `platform_balances.free_tier_period`
resets identically. (The rolling-vs-calendar *policy* — 24h-rolling vs
midnight-aligned — is still an implementation-phase choice; the *mechanism* is
lazy reset either way.)

### 3.3 Per-model pricing

The USD estimate needs a price per model. Pricing is **per-operation-shaped** —
operations are not all token-priced, so a token-only schema cannot express
"$0.04/image":

| Operation class | Price dimensions |
|---|---|
| chat / completion / embedding / extraction / translation | `input_price_per_mtok`, `output_price_per_mtok` |
| image_gen | `price_per_image` |
| video_gen | `price_per_second` |
| stt / tts / audio_gen | `price_per_kchar` (stt may use `price_per_audio_minute`) |

The model pricing record carries whichever dimensions its operation class
needs (a small JSON `pricing` blob, or nullable columns per dimension);
Subsystem A's estimator selects the dimension by operation. **Without this the
§3 claim "applies to every job" is false for image/video/audio** — the token
columns alone cannot price them.

Price sources:
- **platform_model** — LoreWeave maintains the price (it *is* LoreWeave's
  cost). Stored with the platform-model config.
- **user_model (BYOK)** — the user supplies pricing at model registration
  (provider-registry `user_models` gains the pricing fields above). A
  platform-maintained **default price table** for well-known cloud models
  (OpenAI, Anthropic, …) pre-fills it so the user rarely types prices.

**Unpriced models — fail CLOSED, not open.** If a model's pricing is missing,
the guardrail cannot bound its cost, so the gateway **rejects** the job
(`402`, "set this model's pricing") rather than letting it through
un-guarded. Skipping the gate on an unpriced model would silently disable the
guardrail for exactly the BYOK case this ADR exists to protect (P2). "Unknown
price" and "free" are **different states**: unknown → blocked; a genuinely-free
model (local / self-hosted) is expressed *explicitly* as `price = 0` at
registration — a priced state that is allowed and contributes $0. The default
must never be "treat unknown as 0".

### 3.4 Where enforcement lives

Every external LLM call flows through exactly two gateway surfaces —
`POST /v1/llm/jobs` and `POST /v1/llm/stream` (the unified-gateway invariant,
[LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md)
§3). Covering both is therefore exhaustive.

- **Pre-flight (jobs)** — `provider-registry` gateway, in `doSubmitJob`
  (`jobs_handler.go`): estimate → reserve against Subsystem A + check
  Subsystem B (platform jobs only) → 402 before job creation. The
  read-check-reserve runs in one transaction holding `SELECT … FOR UPDATE` on
  the user's `spend_guardrails` row (§3 Subsystem A, concurrency).
- **Reconciliation (jobs)** — at job terminal (`worker.go finalizeAndNotify`):
  release the reservation; record actual USD to Subsystem A's window and (for
  platform jobs) Subsystem B. This **wires the gateway as the job biller** —
  the currently-unwired `recordInvocation` gets used.
- **Double-bill safety.** `/record` is made **idempotent by `request_id`** —
  a second call with the same `request_id` is a no-op (the field already
  exists in the payload). With idempotency, the gateway and a not-yet-migrated
  caller (book/video/chat-service) can both call `/record` during cutover with
  no double charge — so caller-migration *order* stops being a correctness
  hazard and becomes mere cleanup. This replaces "sequence carefully" with an
  actual mechanism.
- **Pre-flight (streaming).** `POST /v1/llm/stream` is not a job. **Committed
  approach:** a pre-open Subsystem-A check using the request's `max_tokens`
  (or a configured default ceiling) as the worst-case estimate → reject 402
  before the upstream connection opens; while streaming, the gateway keeps a
  running USD tally from the token deltas it already re-frames and
  **hard-aborts the stream** if the tally crosses the available budget. The
  tally *cadence* is an implementation detail; the *approach* is fixed here so
  streaming — the highest-traffic LLM surface — is not left undesigned.

## 4. Implementation phasing (post-ADR, post-sign-off)

| Phase | Deliverable | Effort |
|-------|-------------|--------|
| **6a** (redefined) | Subsystem A — USD spend guardrail: `spend_guardrails` + `token_reservations` tables + migration; per-model pricing fields; gateway USD estimator; pre-flight 402 + `max_tokens` cap; terminal reconciliation; wire the gateway as job biller. | XL |
| **6a-β** | Subsystem B — platform resale ledger: `platform_balances`; config-driven free-tier seeding; platform-job 402 gate; migrate the 3 caller-side `/record` calls. | L |
| **6a-γ** | FE — let the user view/configure their guardrail (daily/monthly USD limits) + see spend; surface 402 clearly. | M |
| 6b, 6c | Retry policy / tracing — unchanged from the refactor plan. | M each |

Until **6a-γ** ships, Subsystem A runs on **config-default** daily/monthly
limits for every user — the guardrail is fully enforced, just not yet
user-tunable. That is an acceptable interim state (defaults protect; tuning is
a refinement), but it means the "user-configurable" property of §3 Subsystem A
is a 6a-γ deliverable, not a 6a one.

## 5. Consequences

**Positive:** the user's wallet is genuinely protected (BYOK included); USD is
the correct, model-accurate unit; guardrail vs resale are cleanly separated;
enforcement is pre-flight, not post-hoc.

**Negative / cost:** schema migration; per-model pricing must be sourced and
maintained for every model class (token / image / video / audio); the gateway
must become the job biller (caller-side `/record` migration — de-risked by
`request_id` idempotency, §3.4); bigger than the original Phase 6a "M"
estimate — it is an XL + L + M program.

**Superseded:** the `account_balances` token-count model; the flat
`0.000002`/token cost; the abandoned 6a "platform-vs-BYOK quota gate".

## 6. Open questions for the implementation phase (not blocking this ADR)

- BYOK per-model pricing **UX**: required at registration vs optional with the
  default price-table pre-fill. (The *fail-closed* behaviour for an unpriced
  model is decided — §3.3; this is only the registration UX.)
- The concrete **per-unit estimate values** for image/video/audio
  (default price-per-image, per-second, per-kchar) — the *schema* supports
  them (§3.3); the default magnitudes need confirming against real backend
  costs.
- Window reset **policy**: rolling 24h/30d vs calendar day/month. (The
  *mechanism* — lazy-on-access — is decided, §3.2.)
- Streaming tally **cadence**: per-token vs per-N-tokens vs per-second. (The
  *approach* — pre-open check + running tally + hard abort — is decided,
  §3.4.)

> Decided by `/review-impl` round 1 and folded above (no longer open):
> unpriced-model fail-closed (§3.3); `NUMERIC(16,8)` precision (§3.2);
> per-operation pricing dimensions (§3.3); the `available =
> limit − spent − reserved` invariant + `FOR UPDATE` concurrency (§3,§3.4);
> `/record` `request_id` idempotency for the migration (§3.4); leaked-
> reservation sweeper (§3); lazy window-reset mechanism (§3.2); streaming
> guardrail approach (§3.4).
