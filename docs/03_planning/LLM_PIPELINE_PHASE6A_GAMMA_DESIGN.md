# LLM Pipeline Phase 6a-γ — Guardrail FE + Spend Visibility

> Status: DESIGN. The user-facing half of the billing redesign
> ([BILLING_MODEL_REDESIGN_ADR.md](./BILLING_MODEL_REDESIGN_ADR.md) §4 6a-γ):
> let a user view + configure their spend guardrail, see their spend and
> platform balance, and read a clear 402.

## 1. Scope

6a / 6a-δ / 6a-β built the guardrail + resale ledger; until now they run on
config defaults with **no user-facing surface**. 6a-γ adds it.

In scope (full-stack):
1. **BE** — `GET`/`PATCH /v1/model-billing/guardrail` (read + configure the
   Subsystem-A daily/monthly USD limits); `GET /v1/model-billing/platform-balance`
   (Subsystem-B free tier + credits).
2. **BE** — the deferred `D-PHASE6A-BETA-402-MESSAGE`: a `platform_model`
   402 currently propagates a generic "daily/monthly $0" message; make it
   carry the platform-balance figures and a distinct message.
3. **FE** — a budget panel in the existing `usage` feature: daily/monthly
   limit vs spend, reserved, platform free tier + credits; editable limits.

Out of scope: the **per-model pricing form** — that is `D-PHASE6A-PRICING-FE`,
a distinct deferral about `user_models.pricing`, not the guardrail. 6b / 6c
unchanged.

## 2. CLARIFY decisions

1. Full-stack in one cycle (BE endpoints + FE panel + 402 fix).
2. The pricing form is re-scoped OUT — it stays `D-PHASE6A-PRICING-FE`.

## 3. Design — Backend

### 3.1 `GET /v1/model-billing/guardrail`

JWT-auth (`s.auth`), user from the token. Reads `spend_guardrails` for the
user. **Window-aware**: a stale `daily_window_date` / `monthly_window_month`
displays spent as `0` (the next reserve resets it) — the read computes this
with the same `CASE` the reserve uses, but **does not write** (a GET must not
mutate). No row yet ⇒ return the config defaults with `0` spent.

```
200 {
  daily_limit_usd, monthly_limit_usd,
  daily_spent_usd, monthly_spent_usd,     // window-aware (0 if window rolled)
  reserved_usd,
  daily_available_usd, monthly_available_usd   // limit − spent − reserved
}
```

### 3.2 `PATCH /v1/model-billing/guardrail`

JWT-auth. Body `{ daily_limit_usd?, monthly_limit_usd? }` — either or both.
Each, when present, must be `> 0` (else `400`). Seeds the row from config
defaults if absent (`INSERT … ON CONFLICT DO NOTHING`), then `UPDATE`s only
the supplied limit columns inside one `FOR UPDATE` transaction. Returns the
same body as `GET`.

> Lowering a limit below current `spent + reserved` is **allowed** — it does
> not retroactively fail in-flight work; it just means the next reserve 402s.
> Mirrors the ADR's "the guardrail bounds *new* work" rule.

### 3.3 `GET /v1/model-billing/platform-balance`

JWT-auth. Reads `platform_balances`, window-aware on `free_tier_window_month`
(stale ⇒ `free_tier_used` displays `0`). No row ⇒ config free tier, `0` used.

```
200 {
  free_tier_allowance_usd, free_tier_used_usd, free_tier_remaining_usd,
  credits_balance_usd, reserved_usd
}
```

### 3.4 Routing

All three under the existing `/v1/model-billing` group (JWT). `GET guardrail`,
`PATCH guardrail`, `GET platform-balance`.

### 3.5 The 402-message fix (`D-PHASE6A-BETA-402-MESSAGE`)

usage-billing already returns a distinct 402 body for Subsystem B
(`code:"PLATFORM_BALANCE_EXHAUSTED", platform_available, requested`). The gap
is provider-registry:

- `billing.ReserveResult` gains `Code string` and `PlatformAvailable float64`.
- The client's `Reserve` 402 decode reads `code` + `platform_available`
  alongside the existing daily/monthly fields.
- `writeBudget402` (`jobs_handler.go`) branches on `Code`: a
  `PLATFORM_BALANCE_EXHAUSTED` emits "platform free tier + credits exhausted
  (available $X)"; otherwise the existing daily/monthly message.
- `runGuardrailPreflight` — the `max_tokens` cap is a Subsystem-A
  affordability tool; for a `PLATFORM_BALANCE_EXHAUSTED` 402 it does **not**
  apply (the A-side `daily/monthly_available` are absent ⇒ 0 ⇒ the cap math
  already declines). Make this explicit: a B-402 propagates immediately, no
  cap attempt. (`preflightStream` has no cap — unaffected.)

## 4. Design — Frontend

The `usage` feature is flat (`api.ts`, `types.ts`, component `.tsx` files),
rendered by `pages/UsagePage.tsx`, calling `apiJson<T>(path,{token})`. Match
that structure.

- **`usage/types.ts`** — `+ Guardrail`, `+ PlatformBalance`.
- **`usage/api.ts`** — `usageApi.getGuardrail(token)`,
  `patchGuardrail(token, body)`, `getPlatformBalance(token)`.
- **`usage/BudgetPanel.tsx`** (NEW) — renders:
  - Subsystem A: daily + monthly, each a limit-vs-(spent+reserved) progress
    bar with the USD figures; an **Edit** affordance (a shadcn dialog or
    inline form) that `PATCH`es the limits.
  - Subsystem B: free tier used / allowance + credits balance (read-only —
    LoreWeave sets these).
  - Logic (data fetch, the edit form's state, the PATCH mutation) lives in a
    `useBudget` hook colocated in the feature; `BudgetPanel` renders only.
    (CLAUDE.md FE rule — components render, hooks own logic.)
- **`UsagePage.tsx`** — mount `BudgetPanel` above the existing usage tables.
- shadcn components already in the repo (Card, Progress, Dialog, Input,
  Button); no new dependency.

## 5. Files (~14)

| File | Change |
|------|--------|
| `docs/03_planning/LLM_PIPELINE_PHASE6A_GAMMA_DESIGN.md` | NEW (this doc) |
| usage-billing `internal/api/guardrail.go` | + `getGuardrail`, `patchGuardrail`, `getPlatformBalance` handlers |
| usage-billing `internal/api/server.go` | + 3 routes |
| usage-billing `internal/api/guardrail_test.go` | + GET/PATCH/platform-balance handler tests |
| provider-registry `internal/billing/client.go` (+test) | `ReserveResult` + `Code`/`PlatformAvailable`; 402 decode |
| provider-registry `internal/api/jobs_handler.go` (+test) | `writeBudget402` branches on code; B-402 skips the cap |
| `contracts/api/llm-gateway/v1/openapi.yaml` | document the 3 model-billing endpoints |
| frontend `features/usage/types.ts` | + `Guardrail`, `PlatformBalance` |
| frontend `features/usage/api.ts` | + 3 calls |
| frontend `features/usage/useBudget.ts` | NEW — fetch + edit logic |
| frontend `features/usage/BudgetPanel.tsx` | NEW — render |
| frontend `pages/UsagePage.tsx` | mount `BudgetPanel` |
| frontend `features/usage/BudgetPanel.stories.tsx` | NEW — if the feature has Storybook (match siblings) |

## 6. Test plan

- **BE** — `GET guardrail`: no row → config defaults; existing row → figures;
  stale window → spent shows 0. `PATCH`: sets one / both limits; rejects
  `≤ 0`; seeds-then-updates. `GET platform-balance`: defaults / row /
  stale-window. The 402-message: a `PLATFORM_BALANCE_EXHAUSTED` reserve
  result → `writeBudget402` emits the platform message; a chat B-402 does
  not attempt the cap.
- **FE** — `useBudget` fetch + PATCH; `BudgetPanel` renders limits/spend/
  platform; the edit form validates `> 0`; a Storybook story per the
  feature's convention.
- **Browser smoke** (Playwright, the `claude-test@loreweave.dev` account) —
  open the usage page, see the budget panel, edit a limit, confirm it
  persists. Deferred to QC as `D-PHASE6A-GAMMA-SMOKE` if the dev stack is not
  running.

## 7. Build order

1. usage-billing — `getGuardrail` / `patchGuardrail` / `getPlatformBalance`
   + routes + tests.
2. provider-registry — the 402-message fix + tests.
3. openapi — document the endpoints.
4. FE — `types.ts` → `api.ts` → `useBudget.ts` → `BudgetPanel.tsx` →
   `UsagePage.tsx` → story.
5. VERIFY — Go build/vet/test; FE typecheck + lint + the component test.

## 8. Deferrals

- `D-PHASE6A-PRICING-FE` (carried, unchanged) — the per-model pricing form.
- `D-PHASE6A-GAMMA-SMOKE` — the manual/Playwright budget-edit smoke if the
  dev stack is unavailable at QC.
