package pglive

// PG-gated test for the 071 adapters. Gated on PIIKMS_TEST_PG_URL.
//   - PgUserRealityLookup over the meta player_character_index (migration 012).
//   - PgPerRealityScrubber over pc_projection (a minimal create mirroring
//     contracts/migrations/per_reality/0006_projections — the columns the
//     scrubber touches: pc_id/user_id/name/status + the status CHECK).

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	uew "github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer"
)

func pgPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping 071 pglive PG test")
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func exec(t *testing.T, pool *pgxpool.Pool, sql string, args ...any) {
	t.Helper()
	if _, err := pool.Exec(context.Background(), sql, args...); err != nil {
		t.Fatalf("exec %q: %v", sql, err)
	}
}

func TestLive_PgUserRealityLookup_DistinctRealities(t *testing.T) {
	pool := pgPool(t)
	ctx := context.Background()
	sql, _ := os.ReadFile("../../../../../migrations/meta/012_player_character_index.up.sql")
	if _, err := pool.Exec(ctx, string(sql)); err != nil && !strings.Contains(err.Error(), "deadlock") {
		t.Fatalf("apply 012: %v", err)
	}

	userA, userB := uuid.New(), uuid.New()
	r1, r2 := uuid.New(), uuid.New()
	seed := func(user, reality uuid.UUID, name string) {
		exec(t, pool,
			`INSERT INTO player_character_index (pc_index_id, user_ref_id, reality_id, pc_id, pc_name, status)
			 VALUES ($1,$2,$3,$4,$5,'active')`,
			uuid.New(), user, reality, uuid.New(), name)
	}
	// userA: 2 PCs in r1 (same reality) + 1 in r2 → distinct realities {r1, r2}.
	seed(userA, r1, "A-one")
	seed(userA, r1, "A-two")
	seed(userA, r2, "A-three")
	seed(userB, uuid.New(), "B-one") // a different user, different reality

	got, err := NewPgUserRealityLookup(pool).RealitiesForUser(ctx, userA)
	if err != nil {
		t.Fatalf("RealitiesForUser: %v", err)
	}
	set := map[uuid.UUID]bool{}
	for _, r := range got {
		set[r] = true
	}
	if len(set) != 2 || !set[r1] || !set[r2] {
		t.Errorf("want distinct {r1,r2}, got %v", got)
	}
}

func TestLive_PgPerRealityScrubber_ScrubsAndIdempotent(t *testing.T) {
	pool := pgPool(t)
	ctx := context.Background()
	// Minimal pc_projection (the scrubber-touched columns + the real status CHECK).
	exec(t, pool, `
		CREATE TABLE IF NOT EXISTS pc_projection (
			pc_id   UUID PRIMARY KEY,
			user_id UUID NOT NULL,
			name    TEXT NOT NULL,
			status  TEXT NOT NULL DEFAULT 'active',
			CONSTRAINT pc_projection_status_valid CHECK (status IN ('active','inactive','deleted'))
		)`)

	userA, userB := uuid.New(), uuid.New()
	exec(t, pool, `INSERT INTO pc_projection (pc_id, user_id, name, status) VALUES ($1,$2,'Alice','active')`, uuid.New(), userA)
	exec(t, pool, `INSERT INTO pc_projection (pc_id, user_id, name, status) VALUES ($1,$2,'Bob','active')`, uuid.New(), userB)

	reality := uuid.New()
	scrubber := NewPgPerRealityScrubber(func(_ uuid.UUID) (*pgxpool.Pool, error) { return pool, nil })
	intent := uew.ScrubIntent{RealityID: reality, UserID: userA, EventID: uuid.New(), ErasedAt: time.Unix(0, 0), IssuedAt: time.Unix(0, 0)}

	if err := scrubber.ScrubUserRefs(ctx, intent); err != nil {
		t.Fatalf("ScrubUserRefs: %v", err)
	}
	// userA's PC scrubbed.
	var name, status string
	if err := pool.QueryRow(ctx, `SELECT name, status FROM pc_projection WHERE user_id=$1`, userA).Scan(&name, &status); err != nil {
		t.Fatalf("query userA: %v", err)
	}
	if name != "[erased]" || status != "deleted" {
		t.Errorf("userA PC not scrubbed: name=%q status=%q", name, status)
	}
	// userB untouched.
	var bName, bStatus string
	if err := pool.QueryRow(ctx, `SELECT name, status FROM pc_projection WHERE user_id=$1`, userB).Scan(&bName, &bStatus); err != nil {
		t.Fatalf("query userB: %v", err)
	}
	if bName != "Bob" || bStatus != "active" {
		t.Errorf("userB PC must be untouched: name=%q status=%q", bName, bStatus)
	}
	// Idempotent re-run: no error, still scrubbed (the status<>'deleted' guard
	// makes it a 0-row no-op).
	if err := scrubber.ScrubUserRefs(ctx, intent); err != nil {
		t.Fatalf("idempotent re-scrub: %v", err)
	}
}

func TestPgPerRealityScrubber_ResolverError(t *testing.T) {
	// A resolver error (unreachable reality) must surface so the caller NACKs.
	scrubber := NewPgPerRealityScrubber(func(_ uuid.UUID) (*pgxpool.Pool, error) {
		return nil, context.DeadlineExceeded
	})
	err := scrubber.ScrubUserRefs(context.Background(), uew.ScrubIntent{RealityID: uuid.New(), UserID: uuid.New()})
	if err == nil {
		t.Fatal("want error when the pool resolver fails (Q-L5H-1: NACK, don't drop)")
	}
}
