# S4b — Usage Outbox + Relay + Dual Redis Streams (per-slice design)

> Auto-Draft Factory **S4b** (provider-registry, Go). Parent design:
> [`2026-06-09-s4-campaign-budget-cap-design.md`](2026-06-09-s4-campaign-budget-cap-design.md) §5.2/§7a.
> Implements **decision C** (usage→outbox exactly-once) + **G8** (dedicated bounded campaign stream).
> Branch `feat/advanced-translation-pipeline`. Single service.

## PO decisions (CLARIFY 2026-06-09)
- **REPLACE** the fire-and-forget `RecordUsage` HTTP call with the transactional outbox **now** (not
  additive). ⇒ quota/credit recording moves to the event path; **S4c (usage-billing consumer) is a hard
  pre-prod prerequisite** — between an S4b-only deploy and S4c, `loreweave:events:usage` accumulates
  unconsumed and quota billing is paused. Flag in SESSION; treat S4b+S4c as a deploy pair.
- **No AMAW** — default v2.2 self-review + POST-REVIEW checkpoint.

## Scope precision (design-review)
`RecordUsage` has **two** callers: `jobs/worker.go settleBilling` (the **batch/job path** — what
campaigns use via `submit_job`) and `api/stream_billing.go` (the **interactive streaming path**). S4b
replaces it **only in the jobs-worker path**. The streaming path is interactive chat (editor/chat-service),
is never campaign-tagged, and keeps its HTTP `/record` call. ⇒ usage-billing (S4c) must consume the
`:usage` stream (jobs) **and keep** the `/record` endpoint (streaming). All campaign LLM calls flow through
the jobs path, so jobs-path-only fully captures campaign spend.

## Acceptance
1. On a **completed** job, a `usage_outbox` row is written **in the same DB tx** as the `llm_jobs`
   finalize (atomic; only when the `WHERE status='running'` transition takes effect).
2. The row carries: `request_id` (=job_id), `owner_user_id`, `campaign_id` (from `job_meta`, nullable),
   `model_source`/`model_ref`, `operation`, `input_tokens`/`output_tokens`, `cost_usd` (real per-model,
   nullable when unresolvable).
3. A relay publishes each unpublished row to **`loreweave:events:usage`** (all) and, when
   `campaign_id` is set, **`loreweave:events:campaign_usage`** (G8, bounded), then marks it published.
4. At-least-once delivery; downstream consumers (S4c/S4d) dedup on `request_id`.
5. `RecordUsage` HTTP call removed; the guardrail reserve/reconcile/release path is **unchanged**.

## Design

### 1. Schema (`internal/migrate/migrate.go`, append to `schemaSQL`)
```sql
CREATE TABLE IF NOT EXISTS usage_outbox (
  id             BIGSERIAL PRIMARY KEY,
  request_id     UUID NOT NULL,              -- = job_id; consumer idempotency key
  owner_user_id  UUID NOT NULL,
  campaign_id    UUID,                       -- from job_meta.campaign_id; NULL = non-campaign
  model_source   TEXT NOT NULL,
  model_ref      UUID NOT NULL,
  operation      TEXT NOT NULL,              -- → consumer `purpose`
  input_tokens   INT  NOT NULL,
  output_tokens  INT  NOT NULL,
  cost_usd       NUMERIC(16,8),              -- real per-model; NULL when unresolvable (media)
  published_at   TIMESTAMPTZ,                -- relay stamps after XADD
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- relay scan: oldest-unpublished first.
CREATE INDEX IF NOT EXISTS idx_usage_outbox_unpublished
  ON usage_outbox(id) WHERE published_at IS NULL;
```

### 2. `Repo.FinalizeWithUsageOutbox` (`internal/jobs/repo.go`) — replaces the `Finalize` call on the worker's terminal path
One tx:
```
BEGIN
UPDATE llm_jobs SET status,completed_at,result,error_code,error_message,finish_reason
  WHERE job_id=$1 AND status='running' RETURNING job_meta   -- QueryRow
  ├─ pgx.ErrNoRows → COMMIT, return rows=0 (cancel raced; no outbox)   [gate preserved]
  └─ row → rows=1
IF status=='completed' AND usage!=nil:
    campaign_id := parseJobMetaCampaignID(job_meta)          -- nil-tolerant
    INSERT INTO usage_outbox(request_id,owner_user_id,campaign_id,model_source,model_ref,
                             operation,input_tokens,output_tokens,cost_usd) VALUES(...)
COMMIT
return rows
```
- `parseJobMetaCampaignID`: `json.Unmarshal` job_meta → read `"campaign_id"` string → `uuid.Parse`; any
  failure ⇒ nil (a malformed/absent tag must never fail the finalize — billing-critical path).
- The existing plain `Finalize` stays for non-worker callers (none today carry usage); the worker switches
  to `FinalizeWithUsageOutbox`.

### 3. Worker change (`internal/jobs/worker.go finalizeAndNotify` + `settleBilling`)
- On the **completed** path, compute `cost := actualUSD(...)` **once** (read pricing + result tokens),
  build a `UsageOutboxRow{tokens, cost, modelSource, modelRef, operation}`, pass to
  `FinalizeWithUsageOutbox`. Non-completed → `usage=nil` (no outbox row).
- Reuse the same `cost` for the guardrail `Reconcile` (thread it in; avoids a 2nd pricing read).
- **Remove** the `RecordUsage` block from `settleBilling` (the outbox now carries usage). Reconcile/release
  stays exactly as-is.
- Notifier `PublishTerminal` still gated on `rows>0`, ordering unchanged.

### 4. Relay (`internal/jobs/usage_relay.go`, new)
```
type UsageRelay struct { rdb *redis.Client; pool *pgxpool.Pool; cfg RelayConfig }
func (r *UsageRelay) Run(ctx):
  ticker every cfg.PollInterval
  each tick → drainOnce(ctx)
drainOnce:
  tx := pool.Begin
  rows := SELECT id,request_id,owner_user_id,campaign_id,model_source,model_ref,operation,
                 input_tokens,output_tokens,cost_usd
          FROM usage_outbox WHERE published_at IS NULL
          ORDER BY id LIMIT cfg.BatchSize FOR UPDATE SKIP LOCKED      -- multi-replica safe
  for row in rows:
     fields := {request_id, owner_user_id, campaign_id|"", model_source, model_ref,
                operation, input_tokens, output_tokens, cost_usd|"", request_status:"success"}
     rdb.XAdd(usage_stream, MAXLEN ~ cfg.UsageMaxLen, fields)
     if row.campaign_id != nil:
         rdb.XAdd(campaign_stream, MAXLEN ~ cfg.CampaignMaxLen, fields)
     tx.Exec(UPDATE usage_outbox SET published_at=now() WHERE id=$1)
  tx.Commit
```
- `FOR UPDATE SKIP LOCKED` + per-batch tx ⇒ two relay replicas grab disjoint rows; the row lock is held
  across XADD+mark so no double-publish in the normal case. A crash between XADD and COMMIT → re-publish
  on the next tick (lock released by the aborted tx) → **at-least-once**, deduped downstream (request_id).
- XADD is a side-effect outside the DB commit; that's the at-least-once seam (acceptable, by design).
- Empty batch → no tx churn (check len before mark) / short-circuit.

### 5. Wiring (`internal/api/server.go NewServer`)
Inside the existing `if cfg.RedisURL != ""` block (reuses the S3a `rdb`): construct
`UsageRelay{rdb, pool, relayCfg}` and `go relay.Run(context.Background())`. Mirrors how S3a governance is
wired in the constructor. (Graceful-shutdown of the goroutine is not wired — process-exit stops it; minor,
noted as deferred. The poll loop is idempotent/resumable so an abrupt stop is safe.)

### 6. Config (`internal/config/config.go`) + compose
- `UsageStream` (default `loreweave:events:usage`), `CampaignUsageStream` (`loreweave:events:campaign_usage`).
- `UsageStreamMaxLen` (e.g. 100000), `CampaignUsageStreamMaxLen` (e.g. 50000) — `XADD MAXLEN ~`.
- `UsageRelayPollMs` (e.g. 500), `UsageRelayBatch` (e.g. 100).
- compose: add the four to provider-registry env (REDIS_URL already present from S3a).

### 7. Stream field contract (consumed by S4c/S4d — freeze the keys)
`request_id, owner_user_id, campaign_id, model_source, model_ref, operation, input_tokens,
output_tokens, cost_usd, request_status`. All string-encoded (Redis stream values are strings); empty
string for a null `campaign_id`/`cost_usd`. S4c reads this for the quota deduction; S4d reads
`campaign_id`+`cost_usd` off the campaign stream.

## Edge cases
| Case | Handling |
|---|---|
| cancel raced finalize (rows=0) | RETURNING ErrNoRows → no outbox row (matches notifier gate). |
| failed job | `usage=nil` → no outbox row; reservation released as before. |
| media / unpriced (cost nil) | row written with `cost_usd=NULL`; S4c falls back to reservation estimate. |
| malformed/absent job_meta | `parseJobMetaCampaignID` → nil; outbox row still written (campaign_id NULL). |
| relay crash mid-batch | uncommitted rows stay unpublished → re-published next tick; dedup downstream. |
| 2 relay replicas | SKIP LOCKED → disjoint batches; no double-publish normally. |
| REDIS_URL unset (dev/test) | no relay started; outbox rows accumulate unpublished (no consumer in dev) — acceptable; **but note the finalize still WRITES outbox rows even without Redis** (DB-only, harmless). |

## Deferred
- **`D-S4B-RELAY-LIVE-SMOKE`** — real Redis: finalize a completed job → row appears in `usage_outbox` →
  relay XADDs to both streams (campaign-tagged only to `:campaign_usage`) → `published_at` stamped; MAXLEN
  trims; 2-replica SKIP-LOCKED disjointness.
- **`D-S4B-RELAY-SHUTDOWN`** — graceful goroutine stop on SIGTERM (today: process-exit; idempotent loop so safe).
- **`D-S4B-S4C-DEPLOY-PAIR`** — S4c must ship before/with S4b in prod (quota billing moved to the stream).

## Test plan (unit, no live infra)
- `FinalizeWithUsageOutbox`: completed+usage → UPDATE + outbox INSERT in one tx (pgxmock/spy); rows=0 path
  (status≠running) → no INSERT; failed → no INSERT; campaign_id parsed from job_meta (set + absent + malformed).
- `parseJobMetaCampaignID`: valid / absent / non-object / bad-uuid → nil-tolerant.
- relay `drainOnce`: maps a row → correct XADD fields on `:usage`; campaign-tagged row → ALSO `:campaign_usage`;
  null campaign_id → only `:usage`; marks published; empty batch → no XADD. (spy redis + fake pool)
- worker: completed path calls FinalizeWithUsageOutbox with cost+tokens; RecordUsage no longer invoked
  (spy guardrail — `RecordUsage` asserted NOT called); reconcile still called.
