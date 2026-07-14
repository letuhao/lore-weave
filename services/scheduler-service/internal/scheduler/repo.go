package scheduler

import (
	"context"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// UpsertSchedule (WS-3.2 — the opt-in WRITE path) creates or updates a user's schedule for a job_kind.
// This is what a user's "auto end-of-day: ON" toggle drives (P3-D2: a row exists only when enabled;
// toggling OFF sets enabled=false, preserving the cadence). When enabled, `next_fire_at` is armed to
// the next local `fire_local_time` in `tz`; when disabled, it is left as-is (the claim scan skips a
// disabled row). One row per (owner, job_kind) via the unique constraint.
func UpsertSchedule(
	ctx context.Context, pool *pgxpool.Pool,
	owner uuid.UUID, jobKind, cadence, fireLocalTime, tz string, enabled bool, now time.Time,
) (time.Time, error) {
	var nextFire *time.Time
	if enabled {
		nf, err := ComputeNextFireAt(fireLocalTime, tz, now)
		if err != nil {
			return time.Time{}, err
		}
		nextFire = &nf
	}
	// On conflict: update cadence/time/enabled. Re-arm next_fire_at ONLY when enabling (don't clobber a
	// live armed instant on an idempotent re-write; a disable leaves it, the scan ignores it anyway).
	_, err := pool.Exec(ctx, `
INSERT INTO scheduled_agent_runs (owner_user_id, job_kind, cadence, fire_local_time, enabled, next_fire_at)
VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (owner_user_id, job_kind) DO UPDATE SET
  cadence = EXCLUDED.cadence,
  fire_local_time = EXCLUDED.fire_local_time,
  enabled = EXCLUDED.enabled,
  next_fire_at = CASE WHEN EXCLUDED.enabled THEN EXCLUDED.next_fire_at ELSE scheduled_agent_runs.next_fire_at END,
  consecutive_failures = CASE WHEN EXCLUDED.enabled THEN 0 ELSE scheduled_agent_runs.consecutive_failures END,
  paused_until = CASE WHEN EXCLUDED.enabled THEN NULL ELSE scheduled_agent_runs.paused_until END,
  updated_at = now()`,
		owner, jobKind, cadence, fireLocalTime, enabled, nextFire)
	if err != nil {
		return time.Time{}, err
	}
	if nextFire != nil {
		return *nextFire, nil
	}
	return time.Time{}, nil
}
