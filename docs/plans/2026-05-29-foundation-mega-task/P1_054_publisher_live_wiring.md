# P1 / DEFERRED 054 — Publisher Live-Wiring (D-PUBLISHER-LIVE-WIRING)

> **Task size:** XL (10+ files, refactors pure-lib API + new meta-DB client, side effects: Postgres + Redis).
> **Mode:** full human-in-loop (v2.2). **Branch:** `mmo-rpg/foundation-mega-task`.
> **Created:** 2026-05-30. **Spec+plan** per XL gate. Closes/advances `DEFERRED.md` row **054**.

## 1. Goal

Turn `services/publisher` from an exit-0 skeleton into a **functional, locally
live-smoked** outbox→Redis-Streams publisher: drain each per-reality
`events_outbox`, XADD the joined event envelope to the per-reality stream
`lw.events.<reality_id>`, mark the outbox row published/retry/dead-letter, and
fan cross-reality rows out to `xreality.<type>`. Verified end-to-end on
`infra/foundation-dev` (Postgres :55432 + Redis :56379) and wired into CI.

## 2. Operator decisions (locked 2026-05-30)

- **D-TX = Correct-now.** Refactor the `poll_loop` pure-lib from separate
  `Fetcher` + `StateWriter` interfaces into a transactional **`Source` → `Batch`**
  API so the `SELECT … FOR UPDATE SKIP LOCKED` and the row `UPDATE`s share ONE
  transaction per reality (honors the 0005 migration contract; correct at V2
  multi-replica, not just V1). Accept at-least-once delivery (XADD before commit;
  consumers idempotent on `event_id`) — the standard outbox semantic.
- **D-DSN = Full reality_registry client.** Implement a meta-DB
  `reality_registry` client + a **shard-host→DSN resolver** (the registry's
  `db_host` is `pg-shard-N.{internal|prod|staging}`, never `localhost`, so a
  resolver maps logical shard host → physical DSN; dev overrides all shard hosts
  to the foundation-dev Postgres).

## 3. Existing surface (verified)

- Pure-libs (tested, unchanged except poll_loop): `retry`, `heartbeat`,
  `xreality_fanout`, `leader_election`, `types`.
- Schema: `events_outbox` (per_reality 0005), `events` (0002, partitioned, join
  on `events_event_id_idx`), `publisher_heartbeats` (meta 003), `reality_registry`
  (meta 001).
- Lint: `dependency-registry-lint.sh` is **warn-mode**; flags `redis.NewClient`
  but NOT `pgxpool.NewWithConfig`. Precedent: `worker-infra` + `statistics-service`
  call `redis.NewClient` in `cmd/main.go`. Follow that.
- Test harness: `//go:build integration` + env DSN, `lib/pq`, `mustApply`
  (`tests/integration/`).
- Idiom: `pgxpool.ParseConfig`+tuning (auth/worker-infra main), `redis.ParseURL`
  + `NewClient` + `Ping` + `XAdd(redis.XAddArgs{})` (worker-infra).

## 4. Design

### 4.1 poll_loop refactor (pure-lib, `services/publisher/pkg/poll_loop`)
Replace `Fetcher` + `StateWriter` with:
```go
type Source interface {
    // Begin opens a tx for reality, runs SELECT … FOR UPDATE SKIP LOCKED,
    // returns a Batch bound to that tx. Caller MUST Commit or Rollback.
    Begin(ctx, realityID string, batchSize int) (Batch, error)
}
type Batch interface {
    Rows() []types.OutboxRow
    MarkPublished(ctx, eventID string) error
    MarkRetry(ctx, eventID string, attempts int, lastErr string, next time.Time) error
    MarkDeadLetter(ctx, eventID string, attempts int, lastErr string) error
    Commit(ctx) error
    Rollback(ctx) error
}
```
`Loop.Run`: per reality → `Begin` → drain rows (Emit→Classify→Mark + fanout
after MarkPublished) → `Commit`; on any Mark/drain error → `Rollback` + return.
`Emitter`, `XRealityFanout`, `ModeReader`, `IterationStats`, skip-gates
unchanged. Rewrite `poll_loop_test.go` fakes (`fakeSource`/`fakeBatch`)
preserving every existing assertion.

### 4.2 pgx adapter (`services/publisher/pkg/pgsource`)
- `New(pools map[string]*pgxpool.Pool, policy retry.Policy)` — pool per reality.
- `Begin`: pick pool → `pool.Begin` → `tx.Query` the join with backoff-aware
  WHERE; scan into `[]types.OutboxRow`; return `*pgBatch{tx, rows}`.
- SELECT:
  ```sql
  SELECT o.event_id, o.reality_id, o.attempts, o.enqueued_at, o.last_attempt_at,
         e.event_type, e.event_version, e.aggregate_type, e.aggregate_id,
         e.aggregate_version, e.occurred_at, e.recorded_at, e.payload, e.metadata
  FROM events_outbox o JOIN events e ON e.event_id = o.event_id
  WHERE o.published = FALSE AND o.dead_lettered_at IS NULL
    AND (o.last_attempt_at IS NULL
         OR o.last_attempt_at + LEAST(
              make_interval(secs => $2 * power(2, GREATEST(o.attempts-1,0))),
              make_interval(secs => $3)) <= NOW())
  ORDER BY o.enqueued_at ASC
  LIMIT $1
  FOR UPDATE OF o SKIP LOCKED
  ```
  ($2=base secs, $3=cap secs from policy — honors exponential backoff using
  existing columns, no new migration.)
- `MarkPublished`: `UPDATE events_outbox SET published=TRUE, attempts=attempts+1,
  last_attempt_at=NOW() WHERE event_id=$1` (satisfies published⇒attempts≥1 CHECK).
- `MarkRetry`: `SET attempts=$2, last_error=$3, last_attempt_at=NOW()`.
- `MarkDeadLetter`: `SET attempts=$2, last_error=$3, last_attempt_at=NOW(),
  dead_lettered_at=NOW()`.

### 4.3 redis adapters (`services/publisher/pkg/redisemit`)
- `Emitter.Emit(row)` → `XAdd(stream="lw.events."+row.RealityID, values=envelope)`.
- `StreamEmitter.XAdd(stream, fields)` → satisfies `xreality_fanout.StreamEmitter`.
- Both serialize `payload`/`metadata` maps as JSON strings (Redis stream field
  values must be scalar) — matches the meta-worker consumer's `Fields` decode.

### 4.4 heartbeat writer (`services/publisher/pkg/metahb`)
`WriteHeartbeat` → upsert into meta `publisher_heartbeats`
(`ON CONFLICT (publisher_id) DO UPDATE SET shard_host, last_heartbeat_at, status='active'`).

### 4.5 reality registry (`services/publisher/pkg/realityreg`)
- `Resolver`: shard-host→DSN. Prod: `postgres://{user}:{pass}@{db_host}:{port}/{db_name}?sslmode={mode}`.
  Dev override: `PUBLISHER_SHARD_HOST_OVERRIDE=pg-shard-0.internal=localhost:55432,…`
  remaps host:port; a `*` key remaps ALL hosts (dev convenience).
- `Registry.ActiveRealities(ctx)` → query meta `reality_registry`
  `WHERE status IN (drainable set)`; returns `[]Reality{ID, DBHost, DBName}`.
  Drainable = NOT IN ('provisioning','archived','archived_verified','soft_deleted','dropped').

### 4.6 cmd/publisher/main.go
Config from env (fail-closed on missing): `PUBLISHER_ID`, `SHARD_HOST`,
`META_DB_URL`, `REDIS_URL`, shard creds + override, `POLL_INTERVAL` (def 1s),
`HEARTBEAT_INTERVAL` (def 10s), `BATCH_SIZE` (def 100). Boot: meta pool → load
active realities → per-reality pools → redis client (+Ping) → build pgsource +
emitters + heartbeat + Loop → ticker goroutines (poll + heartbeat) →
`/healthz`+`/readyz`+`/metrics` HTTP → graceful shutdown on SIGINT/SIGTERM.
Prom metrics: `lw_publisher_published_total`, `_retried_total`,
`_dead_lettered_total`, `_fanout_total{result}`, `_iteration_errors_total`,
`_heartbeat_failures`. Keep `cmd/publisher/main_test.go` green (or adapt).

### 4.7 live-smoke (`tests/integration/publisher_live_smoke_test.go`)
`//go:build integration`, env `LW_INTEGRATION_DB` (per-reality DB) +
`LW_INTEGRATION_REDIS`. Apply 0001+0002+0005; seed one normal + one
cross_reality event+outbox row; build pgsource(pool)+real redis emitters; run
ONE `Loop.Run`; assert: (a) both outbox rows `published=TRUE`; (b)
`XLEN lw.events.<reality>` ≥ 2; (c) `XLEN xreality.<type>` ≥ 1; (d) failure path:
point emitter at a closed redis → row stays unpublished, attempts incremented.
Bootstrap script `scripts/publisher-live-smoke.sh` brings up the stack, creates a
`publisher_smoke` per-reality DB, prints the two env lines, runs the test.

### 4.8 CI (`.github/workflows/foundation-ci.yml`)
Add `go build ./...` + `go vet` + unit tests for `services/publisher` to the Go
job; add the publisher live-smoke to the existing `db-smoke` job (stack already
up there) behind `-tags=integration`.

## 5. Risks / non-goals
- **Non-goal:** V2 multi-replica leader election (still no-op, Q-L2-5) — the tx
  API now makes the SKIP-LOCKED lock load-bearing, so V2 is unblocked but not built.
- **Non-goal:** outbox prune (row 055 ADDRESSED elsewhere), archive/retention
  (056-058), embedding (059/060) — separate P1 items.
- **Risk:** holding the per-reality tx open across N XADDs lengthens lock hold;
  bounded by BATCH_SIZE (100) — acceptable at V1.
- **Risk:** at-least-once duplicates on commit-after-XADD failure — accepted
  outbox semantic; consumers idempotent on `event_id`.

## 6. Exit gate
Unit suites green (publisher + integration build) · live-smoke asserts the
round-trip on foundation-dev · CI wired green · `DEFERRED.md` 054 flipped to
`(ADDRESSED …)` + moved to Recently cleared · SESSION_PATCH updated.
