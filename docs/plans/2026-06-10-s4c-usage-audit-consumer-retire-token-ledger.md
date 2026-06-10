# S4c — Usage audit stream consumer + retire the token ledger (per-slice design)

> Auto-Draft Factory **S4c**. usage-billing (Go) + frontend. Consumes the S4b
> `loreweave:events:usage` stream to restore the post-S4b usage audit, and retires
> the deprecated token `account_balances` deduction. Parent: [`2026-06-09-s4-campaign-budget-cap-design.md`](2026-06-09-s4-campaign-budget-cap-design.md).
> Branch `feat/advanced-translation-pipeline`. No AMAW (PO).

## Premise correction (CLARIFY investigation)
The original plan assumed S4c would "deduct real cost". The billing-model map
([`BILLING_MODEL_REDESIGN_ADR.md`](../03_planning/BILLING_MODEL_REDESIGN_ADR.md) §2) shows the **USD wallet already exists** and is debited on **every job**:
- `spend_guardrails` (USD daily/monthly limit, ALL jobs) + `platform_balances` (USD
  free-tier/credits, platform_model) — via the Phase-6a **reserve→reconcile**, and
  **S4b's reconcile already feeds real `actualUSD`**.
- The token `account_balances` (`month_quota_remaining_tokens`/`credits_balance`) is
  the **deprecated legacy** ledger (wrong unit, no monthly reset, post-hoc, "no new
  code should use it"). Its flat `$0.000002/token` only ever populated the audit
  `usage_logs.total_cost_usd`; it never gated USD spend.

⇒ There is **no USD ledger to build and nothing to migrate**. PO-confirmed direction:
**retire the token ledger + add the stream audit consumer** (achieves "everything in
USD" by deletion). The real gap: **S4b removed the jobs-path `RecordUsage`, so completed
jobs currently write NO `usage_logs` audit row** — the consumer restores it.

## Acceptance
1. A Go consumer on `loreweave:events:usage` (group `usage-biller`) writes one
   `usage_logs` audit row per event with the event's **real `cost_usd`** + tokens,
   idempotent on `request_id` (existing UNIQUE + `ON CONFLICT DO NOTHING`), XAck after.
2. The `account_balances` **token deduction is removed** from `recordInvocation`
   (`/record` now writes only the audit row). USD enforcement is the guardrail's job
   (pre-flight reserve), unchanged.
3. The FE no longer shows the deprecated token quota/credits; the USD `BudgetPanel`
   (guardrail + platform balance) stays.
4. No double-write: jobs' usage arrives via the stream (consumer); streaming usage via
   `/record` — disjoint `request_id`s.

## Design

### 1. Shared audit-write core (`internal/api/server.go`)
Extract the `usage_logs` INSERT from `recordInvocation` into
`(s *Server) writeUsageLog(ctx, tx, p usageLogParams) (fresh bool, err error)`:
- `INSERT INTO usage_logs(request_id, owner_user_id, provider_kind, model_source,
  model_ref, input_tokens, output_tokens, total_tokens, total_cost_usd,
  billing_decision, request_status, policy_version, …payload ciphertext…, purpose)
  ON CONFLICT (request_id) DO NOTHING RETURNING usage_log_id` (idempotency gate intact).
- `billing_decision` becomes a constant **`"recorded"`** (audit-only; the token-quota
  decisions quota/credits/rejected are gone — the USD guardrail is the gate now).
- Payload ciphertext: encrypt whatever payloads are supplied; the consumer + the old
  jobs path supply **none** (the stream event carries no payloads — matches the prior
  jobs-path `RecordUsage`, which also sent none). Encrypt empty `{}` so the NOT-NULL
  ciphertext columns stay satisfied (reuse `encryptWithKey` + `s.secretKey`).

### 2. `recordInvocation` (`/record`) — retire the token deduction
- **Remove**: the `account_balances` `SELECT … FOR UPDATE`, the `applyDeduction`
  quota/credits/rejected branching, and the `UPDATE account_balances`.
- Keep: the cost compute (flat — `/record` is the **streaming** path now; it carries no
  cost_usd, so the flat fallback stays for streaming audit only) + delegate the insert to
  `writeUsageLog`. `request_status` no longer flips to `billing_rejected` here.
- The `account_balances` table + `GET /v1/model-billing/account-balance` stay in place
  (deprecated, harmless); a physical drop is deferred (`D-S4C-ACCOUNTBALANCES-DROP`).

### 3. Stream consumer (`internal/consumer/usage_consumer.go`, new — mirrors statistics-service)
```
type UsageConsumer struct { rdb *redis.Client; srv *Server }   // srv for writeUsageLog + pool + secretKey
Run(ctx):
  XGroupCreateMkStream(loreweave:events:usage, "usage-biller", "0")  // idempotent
  loop:
    res = XReadGroup(group, consumer, {stream: ">"}, Count=N, Block=…)
    for msg:
      p = parseUsageEvent(msg.Values)   // request_id, owner_user_id, model_source,
                                        // model_ref, operation->purpose, input/output_tokens,
                                        // cost_usd (""=NULL→flat fallback), request_status
      tx := pool.Begin
      srv.writeUsageLog(ctx, tx, p); tx.Commit
      XAck(stream, group, msg.ID)       // ack only after the durable write
```
- Real `cost_usd` from the event; empty → flat fallback (`totalTokens × 0.000002`) so
  `total_cost_usd` (NOT NULL) always has a value (rare: unpriced model).
- Idempotent: `writeUsageLog`'s `ON CONFLICT DO NOTHING` → a redelivered event is a no-op;
  XAck regardless. At-least-once + dedup = exactly-once effect.
- Bad/unparseable message → log + XAck (drop; do not block the group). No DLQ in S4c
  (matches statistics-service); revisit if needed.

### 4. Wiring + config + compose
- `config.go`: `RedisURL` (`REDIS_URL`), `UsageStream` (`loreweave:events:usage`),
  `UsageConsumerGroup` (`usage-biller`).
- `main.go`: when `RedisURL != ""`, build `redis.NewClient` + `UsageConsumer`, `go
  consumer.Run(ctx)` (mirrors `go srv.StartSweeper(...)`). Empty → no consumer (dev/test).
- compose: add `REDIS_URL: redis://redis:6379` (+ stream/group overrides) to usage-billing.
- new dep: `go-redis/v9` (first Redis use in usage-billing; mirror provider-registry/statistics).

### 5. Frontend (retire token display) — surface mapped at design-review
- `StatCards.tsx`: remove the quota_remaining + credits cards (use `balance`), drop the
  `balance` prop. Keep the `summary`-based stats.
- `UsagePage.tsx`: stop calling `usageApi.getBalance` + stop passing `balance` to StatCards.
- `api.ts`: remove `getBalance`. `types.ts`: remove `AccountBalance`.
- `billing_decision` becomes `"recorded"` → extend the FE `BillingDecision` union to
  `'quota' | 'credits' | 'rejected' | 'recorded'` (KEEP the 3 legacy values — historical
  `usage_logs` rows still carry them) so `ExpandedRow.tsx` renders the new value without a
  type break; add its label/badge.
- `BudgetPanel.tsx` (USD guardrail + platform balance) unchanged — already the USD view.

## Edge cases
| Case | Handling |
|---|---|
| redelivered event | `ON CONFLICT DO NOTHING` → no-op; XAck. |
| cost_usd "" (unpriced) | flat fallback for `total_cost_usd` (audit only). |
| unparseable message | PERMANENT failure → log + XAck (drop); never reprocessable. |
| transient DB failure during consume | NOT acked → stays pending → reprocessed by drainPending (startup + each idle gap) — audit row recovered, not lost (review-impl #1 fix). |
| REDIS_URL unset (dev/test) | no consumer started; `/record` still works for streaming. |
| streaming /record | still writes audit via `writeUsageLog` (flat cost — real-cost for streaming → deferred). |
| consumer crash mid-batch | unacked → redelivered → idempotent. |

## Deferred
- **`D-S4C-CONSUMER-LIVE-SMOKE`** — real Redis: a completed job → S4b outbox → relay →
  `:usage` → consumer writes the `usage_logs` row with real `cost_usd`; redelivery = no dup.
- **`D-S4C-ACCOUNTBALANCES-DROP`** — physically drop `account_balances` + its GET endpoint
  once nothing reads it (this slice stops writing + removes the FE; table left inert).
- **`D-S4C-STREAMING-REALCOST`** — the streaming `/record` path still uses the flat cost for
  its audit; give it real per-model cost later (it carries no cost_usd today).
- **`D-S4C-CONSUMER-PEL`** (review-impl #1, PARTIAL) — transient failures now recover via
  drainPending on startup + idle gaps. Residual: during a sustained-busy stream (never idle) a
  transient-failed entry waits for an idle gap; a periodic forced reclaim or XAUTOCLAIM (for
  multi-consumer/dead-consumer) is a follow-on if the volume warrants.
- **`D-S4B-S4C-DEPLOY-PAIR` (cleared by this slice)** — once S4c ships, the post-S4b audit
  gap closes; note the audit (not USD enforcement) was what paused.

## Test plan
- usage-billing (Go): `writeUsageLog` idempotency (fresh vs ON CONFLICT) + billing_decision
  constant via pgxmock (reuse the S4b harness pattern); `parseUsageEvent` (field map →
  params, cost_usd ""→fallback, missing fields); consumer wiring (XReadGroup→writeUsageLog→
  XAck) via redismock + pgxmock; `recordInvocation` no longer touches account_balances
  (assert no UPDATE account_balances — spy/pgxmock). `go build`+`vet`+`test ./...`.
- FE: vitest for StatCards (token cards gone, remaining render) + tsc clean + i18n parity.
- Live-smoke deferred (D-S4C-CONSUMER-LIVE-SMOKE).
