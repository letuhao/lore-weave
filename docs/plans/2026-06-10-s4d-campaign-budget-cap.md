# S4d — Campaign budget cap + reactive pause (per-slice design)

> Auto-Draft Factory **S4d** — the user-visible budget cap. campaign-service (Python).
> Consumes the S4b `loreweave:events:campaign_usage` stream → accumulates per-campaign
> spend → auto-pauses at the cap. Parent: [`2026-06-09-s4-campaign-budget-cap-design.md`](2026-06-09-s4-campaign-budget-cap-design.md) §5.4.
> Branch `feat/advanced-translation-pipeline`. No AMAW (PO). **After S4d the Auto-Draft
> Factory backend is feature-complete (S0–S4).**

## PO decisions (CLARIFY 2026-06-10)
- **Include a budget-update PATCH** so "raise the cap → resume" works end-to-end via API.
- **Reactive pause** on summed actual spend; overshoot accepted (decided in the S4 CLARIFY).
- No AMAW.

## Acceptance
1. `campaigns.budget_usd` (NULL = uncapped) + `spent_usd` (default 0); `CreateCampaignPayload`
   accepts `budget_usd` (optional, > 0 if set).
2. A consumer on `loreweave:events:campaign_usage` (group `campaign-spend`) adds each event's
   `cost_usd` to `spent_usd`, **idempotent** via a `campaign_usage_seen(request_id PK)` dedup
   ledger (a redelivered event never double-counts).
3. When `spent_usd ≥ budget_usd` and the campaign is `running`, it **auto-pauses** (reuse the
   S3c pause semantics); resume via the existing `/start`.
4. `PATCH /v1/campaigns/{id}` updates `budget_usd` (owner-scoped) so a paused campaign can be
   raised + resumed.
5. No spend is lost on a transient DB blip (reclaim, below) — under-counting weakens a money cap.

## Grounding (verified)
- Gateway proxies `/v1/campaigns` **generically** → the PATCH needs no gateway change.
- The existing `ProjectionConsumer` (group `campaign-collector`) **acks-always** + parses an
  `{event_type, payload}` envelope — but S4b's Go relay writes **flat fields** (`request_id`,
  `campaign_id`, `cost_usd`, …, per `buildUsageFields`). Projections self-heal via the S3
  stuck-timeout; **spend has no self-heal** → a lost event under-counts permanently.
  ⇒ a **separate `SpendConsumer`** (own group, flat-field parsing, reclaim) is the right shape.

## Design

### 1. Migrations (`app/migrate.py`)
```sql
ALTER TABLE campaigns
  ADD COLUMN IF NOT EXISTS budget_usd NUMERIC(16,8),            -- NULL = uncapped
  ADD COLUMN IF NOT EXISTS spent_usd  NUMERIC(16,8) NOT NULL DEFAULT 0;

-- S4d dedup ledger: at-least-once delivery + this PK = exactly-once accumulation
-- (the sum-across-a-boundary bug class). request_id = the provider-registry job_id
-- carried on the usage event.
CREATE TABLE IF NOT EXISTS campaign_usage_seen (
  request_id  UUID PRIMARY KEY,
  campaign_id UUID NOT NULL,
  cost_usd    NUMERIC(16,8),
  seen_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 2. models.py
- `CreateCampaignPayload += budget_usd: Optional[Decimal] = None` (validator: `> 0` when set).
- `Campaign += budget_usd: Optional[Decimal]`, `spent_usd: Decimal` (response/detail).
- `UpdateBudgetPayload { budget_usd: Decimal }` (validator `> 0`) for the PATCH.

### 3. repositories.py — atomic accumulate + pause
```python
async def accumulate_and_maybe_pause(pool, *, request_id, campaign_id, cost_usd) -> bool:
    async with pool.acquire() as conn, conn.transaction():
        fresh = await conn.fetchval(
            "INSERT INTO campaign_usage_seen(request_id,campaign_id,cost_usd) "
            "VALUES($1,$2,$3) ON CONFLICT (request_id) DO NOTHING RETURNING request_id",
            request_id, campaign_id, cost_usd)
        if fresh is None:
            return False                       # duplicate → already counted, no-op
        await conn.execute(
            "UPDATE campaigns SET spent_usd = spent_usd + $2, "
            "  status = CASE WHEN budget_usd IS NOT NULL AND spent_usd + $2 >= budget_usd "
            "                AND status='running' THEN 'paused' ELSE status END, "
            "  error_message = CASE WHEN budget_usd IS NOT NULL AND spent_usd + $2 >= budget_usd "
            "                AND status='running' THEN 'budget cap reached' ELSE error_message END, "
            "  updated_at = now() WHERE campaign_id = $1",
            campaign_id, cost_usd)
        return True
```
- Dedup-insert + accumulate + pause in **one tx** — a redelivery (dup `request_id`) is a no-op;
  the pause is folded into the same UPDATE (atomic; `running`→`paused` only, idempotent).
- A NULL/0 `cost_usd` still writes the dedup row (so it's not reprocessed) and adds 0.
- `update_budget(pool, campaign_id, owner_user_id, budget_usd)` — owner-scoped UPDATE
  (`WHERE campaign_id=$1 AND owner_user_id=$2`); 0 rows → 404. For the PATCH. (Lowering below
  current spend is allowed — bounds new work; matches the guardrail ADR. Does NOT auto-resume.)

### 4. SpendConsumer (`app/events/spend_consumer.py`, new)
Group `campaign-spend`, stream `loreweave:events:campaign_usage`. Parses **flat** fields
(`request_id`, `campaign_id`, `cost_usd`). Per message:
- parse error / missing campaign_id → **permanent** → log + ack (drop).
- else `accumulate_and_maybe_pause(...)`:
  - success → ack.
  - **transient** DB error → **do NOT ack** → reclaim on next idle/startup (`drainPending`,
    XREADGROUP id `"0"`) — money cap must not under-count on a blip (S4c pattern, Python port).
- `XGroupCreateMkStream` idempotent (BUSYGROUP). Reconnect on ConnectionError (mirror ProjectionConsumer).

### 5. PATCH endpoint (`app/routers/campaigns.py`)
`PATCH /{campaign_id}` (body `UpdateBudgetPayload`) → verify owner → `update_budget` → return the
updated `Campaign`. Resume stays the existing `POST /{id}/start` (re-pauses immediately if spend
still ≥ the new budget — documented; raising above spend then resuming is the happy path).

### 6. Wiring (`app/main.py`)
Add `SpendConsumer(settings.redis_url, pool)` as a 3rd background task (alongside ProjectionConsumer
+ driver); start/stop/close in the lifespan exactly like ProjectionConsumer. Single replica (the
driver-claim singleton note still applies service-wide; the consumer group handles consumer-side HA).

## Edge cases
| Case | Handling |
|---|---|
| redelivered usage event | `campaign_usage_seen` PK → dedup no-op (no double-count). |
| cost_usd "" / 0 | dedup row written, adds 0 (no reprocess, no spend). |
| campaign already paused/cancelled | accumulate still records spend (audit-honest); pause CASE only fires `running`→`paused`. |
| budget_usd NULL (uncapped) | accumulate only; never pauses. |
| transient DB error in consumer | not acked → reclaimed (drainPending) — no lost spend. |
| campaign_id for a deleted campaign | dedup row written; UPDATE affects 0 rows (no-op). |
| lower budget below spent + resume | /start re-pauses on the next event (documented; raise above spend to run). |

## Deferred
- **`D-S4D-LIVE-SMOKE`** — real campaign w/ low `budget_usd` over a multi-chapter run: `spent_usd`
  climbs via `:campaign_usage`, auto-pauses at cap, PATCH-raise + `/start` resumes, redelivery no dup.
- **`D-S4D-CONSUMER-PEL`** — same partial-reclaim residual as S4c (sustained-busy stream defers
  reclaim to the next idle gap).
- ✅ **`D-S4D-RESUME-GUARD`** (CLEARED, review-impl #2) — `/start` now 409s (`CAMPAIGN_OVER_BUDGET`)
  when `spent_usd >= budget_usd`; raise via PATCH first.

## review-impl resolution
- **#1 MED (pause SQL behaviorally untested)** → fixed: added `tests/integration/` (real-PG, skips
  without `TEST_CAMPAIGN_DB_URL`, mirrors knowledge-service) — 6 tests exercising the actual CASE
  (under-cap stays running, at-cap pauses + error_message, dup no-double-count, uncapped never pauses,
  paused-accrues-not-resurrected, update_budget owner-scoped). Full cross-service e2e still `D-S4D-LIVE-SMOKE`.
- **#2 LOW (resume guard)** → fixed (above) + 2 tests.
- **#3 LOW (budget ceiling)** → fixed: `_BUDGET_USD_MAX = 10^8` validator on create + PATCH (numeric(16,8) overflow guard) + 2 tests.

## Test plan
- repo `accumulate_and_maybe_pause`: fresh accumulate; pause-at-cap (running→paused) vs under-cap
  (stays running); uncapped (NULL) never pauses; duplicate request_id → no-op (False) (fake-pool/
  asyncpg-mock, mirror existing campaign tests). `update_budget` owner-scoped (0 rows → 404).
- SpendConsumer: flat-field parse (valid / missing campaign_id → permanent); handle → accumulate
  called; transient error → not acked (reclaim path); permanent → acked.
- API: create with budget_usd persists it; PATCH updates it (owner-scoped); validation (>0).
- VERIFY: campaign-service pytest green. Live-smoke deferred.
