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
	tzStore := tz
	if tzStore == "" {
		tzStore = "UTC"
	}
	_, err := pool.Exec(ctx, `
INSERT INTO scheduled_agent_runs (owner_user_id, job_kind, cadence, fire_local_time, timezone, enabled, next_fire_at)
VALUES ($1,$2,$3,$4,$5,$6,$7)
ON CONFLICT (owner_user_id, job_kind) DO UPDATE SET
  cadence = EXCLUDED.cadence,
  fire_local_time = EXCLUDED.fire_local_time,
  timezone = EXCLUDED.timezone,
  enabled = EXCLUDED.enabled,
  next_fire_at = CASE WHEN EXCLUDED.enabled THEN EXCLUDED.next_fire_at ELSE scheduled_agent_runs.next_fire_at END,
  consecutive_failures = CASE WHEN EXCLUDED.enabled THEN 0 ELSE scheduled_agent_runs.consecutive_failures END,
  paused_until = CASE WHEN EXCLUDED.enabled THEN NULL ELSE scheduled_agent_runs.paused_until END,
  updated_at = now()`,
		owner, jobKind, cadence, fireLocalTime, tzStore, enabled, nextFire)
	if err != nil {
		return time.Time{}, err
	}
	if nextFire != nil {
		return *nextFire, nil
	}
	return time.Time{}, nil
}

// ScheduleRow is one (owner, job_kind) schedule as read back for the settings UI (A3 — the effective
// value + source the Settings-and-Config rules require: a toggle must expose whether it is really ON).
type ScheduleRow struct {
	JobKind       string     `json:"job_kind"`
	Cadence       string     `json:"cadence"`
	FireLocalTime string     `json:"fire_local_time"`
	Timezone      string     `json:"timezone"`
	Enabled       bool       `json:"enabled"`
	NextFireAt    *time.Time `json:"next_fire_at,omitempty"`
}

// ListSchedules (A3 — the READ path for the autonomous-layer settings toggle) returns EVERY schedule row
// the user has ever set, so the FE can render each job_kind's effective state (enabled + armed instant).
// Owner-scoped. A job_kind with no row has never been armed ⇒ the FE shows it OFF (fail-closed default).
func ListSchedules(ctx context.Context, pool *pgxpool.Pool, owner uuid.UUID) ([]ScheduleRow, error) {
	rows, err := pool.Query(ctx, `
SELECT job_kind, cadence, fire_local_time, timezone, enabled, next_fire_at
FROM scheduled_agent_runs
WHERE owner_user_id = $1
ORDER BY job_kind`, owner)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]ScheduleRow, 0)
	for rows.Next() {
		var s ScheduleRow
		// Scan EVERY column into a target (nullable next_fire_at → *time.Time) — a discarded/short scan
		// would zero the row (the pgx discarded-scan bug class).
		if err := rows.Scan(&s.JobKind, &s.Cadence, &s.FireLocalTime, &s.Timezone, &s.Enabled, &s.NextFireAt); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

// AddAwayPeriod (WS-3.4) records a declared away span for a user.
func AddAwayPeriod(ctx context.Context, pool *pgxpool.Pool, owner uuid.UUID, startsOn, endsOn time.Time) error {
	_, err := pool.Exec(ctx,
		`INSERT INTO assistant_away_periods (owner_user_id, starts_on, ends_on) VALUES ($1,$2,$3)`,
		owner, startsOn, endsOn)
	return err
}

// IsAway reports whether `day` (a calendar date) falls inside any of the user's away periods. A nudge
// must not fire on an away day (spec 11 Q7); Phase 5's gap detector reads this too.
func IsAway(ctx context.Context, pool *pgxpool.Pool, owner uuid.UUID, day time.Time) (bool, error) {
	var n int
	err := pool.QueryRow(ctx, `
SELECT count(*) FROM assistant_away_periods
WHERE owner_user_id=$1 AND $2::date BETWEEN starts_on AND ends_on`, owner, day).Scan(&n)
	return n > 0, err
}
