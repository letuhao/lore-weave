package pglive

// PG-gated test for the 071 adapters. Gated on PIIKMS_TEST_PG_URL.
//   - PgUserRealityLookup over the meta player_character_index (migration 012).
//
// TestLive_PgPerRealityScrubber_ScrubsAndIdempotent was DELETED on 2026-08-04.
// It created its own minimal `pc_projection`, seeded two users, and asserted the
// scrub tombstoned one and left the other alone. `0017` dropped that table, and
// no per-reality projection carries a user reference any more, so
// PgPerRealityScrubber has nothing to scrub and the test was asserting a
// behaviour that no longer exists — against a table it had brought into being
// itself, which is the tell: a live test that CREATEs its own subject can outlive
// the subject indefinitely. What replaces it is not another live test but
// TestNoPerRealityTableCarriesAUserReference, which reds the day the subject
// comes back.

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

// TestPgPerRealityScrubber_SucceedsWithNothingToScrub pins the no-op's contract:
// a reachable reality is success, not an error. Paired with
// TestPgPerRealityScrubber_ResolverError below, which pins that an UNREACHABLE
// reality still fails — the one thing the leg is still responsible for.
func TestPgPerRealityScrubber_SucceedsWithNothingToScrub(t *testing.T) {
	called := false
	scrubber := NewPgPerRealityScrubber(func(_ uuid.UUID) (*pgxpool.Pool, error) {
		called = true
		return nil, nil
	})
	if err := scrubber.ScrubUserRefs(context.Background(), uew.ScrubIntent{
		RealityID: uuid.New(), UserID: uuid.New(),
		ErasedAt: time.Unix(0, 0), IssuedAt: time.Unix(0, 0),
	}); err != nil {
		t.Fatalf("ScrubUserRefs must succeed when there is nothing to scrub: %v", err)
	}
	if !called {
		t.Error("the reality must still be RESOLVED — an unreachable reality the lookup " +
			"named is a real failure, and dropping the resolve would hide it")
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
