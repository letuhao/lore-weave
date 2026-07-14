package scheduler

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

// WS-3.2 — the opt-in write path: enabling creates an ARMED row a due tick then fires; disabling
// flips enabled=false (the claim scan skips it). Requires SCHEDULER_TEST_DB_URL.
func TestUpsertSchedule_OptInThenFire(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	owner := uuid.New()
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM scheduled_agent_runs WHERE owner_user_id=$1`, owner) })

	// Enable at a local time already PAST today (so next_fire_at lands tomorrow) — prove the write + arm.
	now := time.Now().UTC()
	next, err := UpsertSchedule(ctx, pool, owner, "eod_distill", "daily", "21:00", "UTC", true, now)
	if err != nil {
		t.Fatalf("upsert enable: %v", err)
	}
	if !next.After(now) {
		t.Fatalf("enabled schedule must arm a future next_fire_at, got %v", next)
	}
	var enabled bool
	var armed *time.Time
	pool.QueryRow(ctx, `SELECT enabled, next_fire_at FROM scheduled_agent_runs WHERE owner_user_id=$1 AND job_kind='eod_distill'`, owner).Scan(&enabled, &armed)
	if !enabled || armed == nil {
		t.Fatalf("row not enabled/armed: enabled=%v armed=%v", enabled, armed)
	}

	// Force it due, then a tick fires it.
	past := now.Add(-time.Minute)
	pool.Exec(ctx, `UPDATE scheduled_agent_runs SET next_fire_at=$2 WHERE owner_user_id=$1`, owner, past)
	enq := &fakeEnq{}
	if n, _ := NewDriver(pool, enq, "t").tickOnce(ctx); n != 1 {
		t.Fatalf("enabled+due schedule should fire, n=%d", n)
	}

	// Disable → enabled=false; a due tick no longer fires it.
	if _, err := UpsertSchedule(ctx, pool, owner, "eod_distill", "daily", "21:00", "UTC", false, now); err != nil {
		t.Fatalf("upsert disable: %v", err)
	}
	pool.QueryRow(ctx, `SELECT enabled FROM scheduled_agent_runs WHERE owner_user_id=$1`, owner).Scan(&enabled)
	if enabled {
		t.Fatal("disable did not flip enabled=false")
	}
	pool.Exec(ctx, `UPDATE scheduled_agent_runs SET next_fire_at=$2 WHERE owner_user_id=$1`, owner, past)
	enq2 := &fakeEnq{}
	if n, _ := NewDriver(pool, enq2, "t").tickOnce(ctx); n != 0 {
		t.Fatalf("disabled schedule must not fire, n=%d", n)
	}
}

// WS-3.4 (spec 11 Q7) — a NUDGE is suppressed on a declared away day (re-armed, not sent); a nudge
// OUTSIDE any away period fires. eod_distill is NOT away-gated.
func TestNudge_SuppressedOnAwayDay(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	now := time.Now().UTC()
	past := now.Add(-time.Minute)

	// User A is AWAY today; user B is not.
	awayUser := uuid.New()
	activeUser := uuid.New()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM scheduled_agent_runs WHERE owner_user_id = ANY($1)`, []uuid.UUID{awayUser, activeUser})
		pool.Exec(ctx, `DELETE FROM assistant_away_periods WHERE owner_user_id = ANY($1)`, []uuid.UUID{awayUser, activeUser})
	})
	if err := AddAwayPeriod(ctx, pool, awayUser, now.AddDate(0, 0, -1), now.AddDate(0, 0, 3)); err != nil {
		t.Fatalf("away: %v", err)
	}
	seedNudge := func(owner uuid.UUID) {
		pool.Exec(ctx, `INSERT INTO scheduled_agent_runs (owner_user_id, job_kind, cadence, enabled, next_fire_at)
			VALUES ($1,'nudge','daily',true,$2)`, owner, past)
	}
	seedNudge(awayUser)
	seedNudge(activeUser)

	enq := &fakeEnq{}
	n, err := NewDriver(pool, enq, "t").tickOnce(ctx)
	if err != nil {
		t.Fatalf("tick: %v", err)
	}
	// Only the ACTIVE user's nudge fires; the away user's is suppressed (re-armed).
	if n != 1 || len(enq.fired) != 1 {
		t.Fatalf("expected 1 nudge fired (active only), got n=%d fired=%v", n, enq.fired)
	}
	if enq.fired[0] != activeUser.String()+"|nudge" {
		t.Fatalf("wrong nudge fired: %v", enq.fired)
	}
	// The away user's row is re-armed to the future (suppressed as a no-op, not left due).
	var next time.Time
	pool.QueryRow(ctx, `SELECT next_fire_at FROM scheduled_agent_runs WHERE owner_user_id=$1`, awayUser).Scan(&next)
	if !next.After(now) {
		t.Fatalf("suppressed away nudge should re-arm to the future, got %v", next)
	}
}
