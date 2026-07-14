package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// scheduled_agent_runs (WS-3.1, spec 11 Q3) — the per-user scheduler's only table. One row per
// (owner, job_kind); the tick driver claims due rows under a lease (FOR UPDATE SKIP LOCKED) and
// enqueues the work onto the existing consumers (WS-3.2 posts to the chat distill HTTP trigger).
//
//   - `enabled` is the per-user opt-in (P3-D2: auto-EOD defaults OFF — a row is created only when
//     the user turns a schedule ON, and `enabled=false` pauses it without deleting the cadence).
//   - `next_fire_at` is the local-time-resolved next run (WS-3.3 computes it from `cadence` +
//     the user's tz); the claim query is `enabled AND next_fire_at <= now()`.
//   - `lease_until` + `locked_by` make the claim restart-safe across replicas: a crashed tick's
//     lease expires and another driver re-claims (no double-fire while a lease is live — SKIP LOCKED
//     prevents concurrent claims; the lease covers the post-claim window before re-arm).
//   - `consecutive_failures` + `paused_until` are the circuit breaker (spec 11 Q3): repeated failures
//     back the row off instead of hot-looping a broken job.
const schemaSQL = `
CREATE TABLE IF NOT EXISTS scheduled_agent_runs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id         UUID NOT NULL,
  job_kind              TEXT NOT NULL,              -- 'eod_distill' | 'weekly_rollup' | 'nudge' | ...
  cadence               TEXT NOT NULL,              -- 'daily' | 'weekly' (+ the user's local fire time)
  fire_local_time       TEXT NOT NULL DEFAULT '21:00', -- HH:MM in the user's tz (WS-3.3 resolves next_fire_at)
  enabled               BOOLEAN NOT NULL DEFAULT false, -- P3-D2 opt-in: a row exists only when turned ON
  next_fire_at          TIMESTAMPTZ,               -- the next due instant (UTC); NULL = never armed
  lease_until           TIMESTAMPTZ,               -- a live claim's lease; NULL = unclaimed
  locked_by             TEXT,                       -- the consumer name holding the lease (audit)
  last_fired_at         TIMESTAMPTZ,
  consecutive_failures  INT NOT NULL DEFAULT 0,     -- breaker counter
  paused_until          TIMESTAMPTZ,               -- breaker back-off (skip claims until then)
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, job_kind)
);
-- The tick driver's claim scan: enabled, armed, due, not paused. Partial so the common case is tight.
CREATE INDEX IF NOT EXISTS idx_sar_due
  ON scheduled_agent_runs (next_fire_at)
  WHERE enabled AND next_fire_at IS NOT NULL;
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
