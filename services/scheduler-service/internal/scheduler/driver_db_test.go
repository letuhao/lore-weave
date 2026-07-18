package scheduler

// DB integration tests for the tick driver. Require SCHEDULER_TEST_DB_URL; skip otherwise.

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/scheduler-service/internal/migrate"
)

func testPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("SCHEDULER_TEST_DB_URL")
	if dsn == "" {
		t.Skip("SCHEDULER_TEST_DB_URL not set — skipping DB test")
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Skipf("scheduler DB unreachable: %v", err)
	}
	if err := migrate.Up(context.Background(), pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

// fakeEnq records the (owner, kind) it was handed; can be told to fail.
type fakeEnq struct {
	fired []string
	fail  bool
}

func (f *fakeEnq) Enqueue(_ context.Context, owner uuid.UUID, kind string) error {
	f.fired = append(f.fired, owner.String()+"|"+kind)
	if f.fail {
		return context.DeadlineExceeded
	}
	return nil
}

func seedRow(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID, enabled bool, nextFire *time.Time) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	err := pool.QueryRow(context.Background(), `
INSERT INTO scheduled_agent_runs (owner_user_id, job_kind, cadence, enabled, next_fire_at)
VALUES ($1, 'eod_distill', 'daily', $2, $3) RETURNING id`, owner, enabled, nextFire).Scan(&id)
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM scheduled_agent_runs WHERE owner_user_id=$1`, owner) })
	return id
}

func TestDriver_ClaimsDueRow_Fires_AndReArms(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	owner := uuid.New()
	past := time.Now().UTC().Add(-time.Minute)
	id := seedRow(t, pool, owner, true, &past)

	enq := &fakeEnq{}
	d := NewDriver(pool, enq, "test-1")
	n, err := d.tickOnce(ctx)
	if err != nil {
		t.Fatalf("tickOnce: %v", err)
	}
	if n != 1 || len(enq.fired) != 1 {
		t.Fatalf("expected 1 fire, got n=%d fired=%v", n, enq.fired)
	}
	// Re-armed: next_fire_at advanced into the FUTURE, lease cleared, breaker reset.
	var next time.Time
	var lease *time.Time
	var fails int
	pool.QueryRow(ctx, `SELECT next_fire_at, lease_until, consecutive_failures FROM scheduled_agent_runs WHERE id=$1`, id).
		Scan(&next, &lease, &fails)
	if !next.After(time.Now().UTC()) {
		t.Fatalf("next_fire_at not advanced to the future: %v", next)
	}
	if lease != nil || fails != 0 {
		t.Fatalf("lease/breaker not cleared on success: lease=%v fails=%d", lease, fails)
	}
	// A second tick does NOT re-fire (the row is no longer due).
	n2, _ := d.tickOnce(ctx)
	if n2 != 0 {
		t.Fatalf("re-fired an already-armed row: n=%d", n2)
	}
}

func TestDriver_SkipsDisabledAndNotDue(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	past := time.Now().UTC().Add(-time.Minute)
	future := time.Now().UTC().Add(time.Hour)
	disabledOwner := uuid.New()
	notDueOwner := uuid.New()
	seedRow(t, pool, disabledOwner, false, &past) // due but DISABLED (opt-in off)
	seedRow(t, pool, notDueOwner, true, &future)  // enabled but NOT due yet

	enq := &fakeEnq{}
	d := NewDriver(pool, enq, "test-2")
	nn, err := d.tickOnce(ctx)
	if err != nil {
		t.Fatalf("tickOnce: %v", err)
	}
	if nn != 0 || len(enq.fired) != 0 {
		t.Fatalf("fired a disabled/not-due row: n=%d fired=%v", nn, enq.fired)
	}
}

func TestDriver_EnqueueFailure_BumpsBreaker(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	owner := uuid.New()
	past := time.Now().UTC().Add(-time.Minute)
	id := seedRow(t, pool, owner, true, &past)

	enq := &fakeEnq{fail: true}
	d := NewDriver(pool, enq, "test-3")
	n, _ := d.tickOnce(ctx)
	if n != 0 {
		t.Fatalf("a failed enqueue should not count as fired: n=%d", n)
	}
	var fails int
	var lease *time.Time
	pool.QueryRow(ctx, `SELECT consecutive_failures, lease_until FROM scheduled_agent_runs WHERE id=$1`, id).Scan(&fails, &lease)
	if fails != 1 {
		t.Fatalf("breaker not bumped on failure: fails=%d", fails)
	}
	if lease != nil {
		t.Fatalf("lease must be cleared even on failure (so a retry can re-claim): lease=%v", lease)
	}
}
