package scheduler

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
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

// C7 (SD-C7) — proactive_nudge is away-gated like nudge (don't proactively ping someone on holiday);
// weekly_reflection (content generation) is NOT away-gated. Proven: an away user's proactive_nudge is
// suppressed+re-armed while an active user's fires.
func TestProactiveNudge_SuppressedOnAwayDay(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	now := time.Now().UTC()
	past := now.Add(-time.Minute)

	awayUser := uuid.New()
	activeUser := uuid.New()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM scheduled_agent_runs WHERE owner_user_id = ANY($1)`, []uuid.UUID{awayUser, activeUser})
		pool.Exec(ctx, `DELETE FROM assistant_away_periods WHERE owner_user_id = ANY($1)`, []uuid.UUID{awayUser, activeUser})
	})
	if err := AddAwayPeriod(ctx, pool, awayUser, now.AddDate(0, 0, -1), now.AddDate(0, 0, 3)); err != nil {
		t.Fatalf("away: %v", err)
	}
	seed := func(owner uuid.UUID) {
		pool.Exec(ctx, `INSERT INTO scheduled_agent_runs (owner_user_id, job_kind, cadence, enabled, next_fire_at)
			VALUES ($1,'proactive_nudge','daily',true,$2)`, owner, past)
	}
	seed(awayUser)
	seed(activeUser)

	enq := &fakeEnq{}
	n, err := NewDriver(pool, enq, "t").tickOnce(ctx)
	if err != nil {
		t.Fatalf("tick: %v", err)
	}
	if n != 1 || len(enq.fired) != 1 || enq.fired[0] != activeUser.String()+"|proactive_nudge" {
		t.Fatalf("expected only the ACTIVE user's proactive_nudge to fire (away-gated), got n=%d fired=%v", n, enq.fired)
	}
	var next time.Time
	pool.QueryRow(ctx, `SELECT next_fire_at FROM scheduled_agent_runs WHERE owner_user_id=$1`, awayUser).Scan(&next)
	if !next.After(now) {
		t.Fatalf("suppressed away proactive_nudge should re-arm to the future, got %v", next)
	}
}

// review H1 — the RECURRING re-arm must land on the next LOCAL fire time (fire_local_time in tz), not
// a raw firedAt+24h (which drifts + breaks on DST). Proven: after firing, next_fire_at's wall-clock is
// exactly fire_local_time (here 21:00 UTC), regardless of the (earlier) tick instant that claimed it.
func TestReArm_UsesLocalFireTime_NotRawInterval(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	owner := uuid.New()
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM scheduled_agent_runs WHERE owner_user_id=$1`, owner) })

	now := time.Now().UTC()
	if _, err := UpsertSchedule(ctx, pool, owner, "eod_distill", "daily", "21:00", "UTC", true, now); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	// tz persisted?
	var tz string
	pool.QueryRow(ctx, `SELECT timezone FROM scheduled_agent_runs WHERE owner_user_id=$1`, owner).Scan(&tz)
	if tz != "UTC" {
		t.Fatalf("timezone not persisted: %q", tz)
	}
	// Force it due at an arbitrary mid-day instant (10:37), then fire.
	claimAt := time.Date(now.Year(), now.Month(), now.Day(), 10, 37, 0, 0, time.UTC)
	pool.Exec(ctx, `UPDATE scheduled_agent_runs SET next_fire_at=$2 WHERE owner_user_id=$1`, owner, claimAt.Add(-time.Minute))
	// recordSuccess re-arms off `claimAt`; the result must be the next 21:00 UTC, NOT claimAt+24h (10:37).
	d := NewDriver(pool, &fakeEnq{}, "t")
	d.recordSuccess(ctx, mustID(t, pool, owner), claimAt)

	var next time.Time
	pool.QueryRow(ctx, `SELECT next_fire_at FROM scheduled_agent_runs WHERE owner_user_id=$1`, owner).Scan(&next)
	nu := next.UTC()
	if nu.Hour() != 21 || nu.Minute() != 0 {
		t.Fatalf("re-arm landed at %02d:%02d UTC, want 21:00 (the local fire time, not firedAt+24h)", nu.Hour(), nu.Minute())
	}
}

// A3 — the settings READ path: ListSchedules returns every job_kind's effective state, owner-scoped, so
// the FE toggle can show enabled/armed truthfully (and a job_kind with no row reads OFF, fail-closed).
func TestListSchedules_PerJobKindStateOwnerScoped(t *testing.T) {
	pool := testPool(t)
	ctx := context.Background()
	owner := uuid.New()
	other := uuid.New()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM scheduled_agent_runs WHERE owner_user_id = ANY($1)`, []uuid.UUID{owner, other})
	})

	now := time.Now().UTC()
	if _, err := UpsertSchedule(ctx, pool, owner, "eod_distill", "daily", "21:00", "UTC", true, now); err != nil {
		t.Fatalf("enable eod: %v", err)
	}
	if _, err := UpsertSchedule(ctx, pool, owner, "weekly_reflection", "weekly", "09:00", "UTC", false, now); err != nil {
		t.Fatalf("disable reflection: %v", err)
	}
	// A DIFFERENT user's row must never appear in owner's list.
	if _, err := UpsertSchedule(ctx, pool, other, "eod_distill", "daily", "21:00", "UTC", true, now); err != nil {
		t.Fatalf("other user: %v", err)
	}

	rows, err := ListSchedules(ctx, pool, owner)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("want 2 rows for owner (never other's), got %d: %+v", len(rows), rows)
	}
	byKind := map[string]ScheduleRow{}
	for _, r := range rows {
		byKind[r.JobKind] = r
	}
	if !byKind["eod_distill"].Enabled || byKind["eod_distill"].NextFireAt == nil {
		t.Fatalf("eod_distill must be enabled + armed, got %+v", byKind["eod_distill"])
	}
	if byKind["weekly_reflection"].Enabled {
		t.Fatalf("weekly_reflection must read disabled, got %+v", byKind["weekly_reflection"])
	}
	if byKind["weekly_reflection"].Cadence != "weekly" {
		t.Fatalf("cadence not read back: %+v", byKind["weekly_reflection"])
	}

	// A user with no rows → empty (never nil), so the FE renders every toggle OFF (fail-closed).
	empty, err := ListSchedules(ctx, pool, uuid.New())
	if err != nil {
		t.Fatalf("list empty: %v", err)
	}
	if empty == nil || len(empty) != 0 {
		t.Fatalf("no-rows user must be empty slice, got %+v", empty)
	}
}

func mustID(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	pool.QueryRow(context.Background(), `SELECT id FROM scheduled_agent_runs WHERE owner_user_id=$1`, owner).Scan(&id)
	return id
}
