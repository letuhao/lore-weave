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
