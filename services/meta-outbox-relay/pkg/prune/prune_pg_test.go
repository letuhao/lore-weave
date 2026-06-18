package prune

// PG-gated test: PruneOnce deletes ONLY spent (published, past-grace) rows —
// never pending, never dead-lettered, never published-but-recent. Gated on
// PIIKMS_TEST_PG_URL.

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func applyMig(ctx context.Context, pool *pgxpool.Pool, sql string) error {
	var err error
	for range 5 {
		if _, err = pool.Exec(ctx, sql); err == nil {
			return nil
		}
		if !strings.Contains(err.Error(), "deadlock") {
			return err
		}
		time.Sleep(50 * time.Millisecond)
	}
	return err
}

func TestLive_PruneOnce_DeletesOnlySpentRows(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping prune PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	sql, rerr := os.ReadFile("../../../../migrations/meta/030_meta_outbox.up.sql")
	if rerr != nil {
		t.Fatalf("read migration: %v", rerr)
	}
	if aerr := applyMig(ctx, pool, string(sql)); aerr != nil {
		t.Fatalf("apply 030: %v", aerr)
	}

	now := time.Now().UTC()
	old := now.Add(-2 * time.Hour)      // past a 1h grace → prunable (if published)
	recent := now.Add(-1 * time.Minute) // within grace → kept

	// id → should-survive
	type seed struct {
		id        uuid.UUID
		published bool
		lastAt    *time.Time
		dead      bool
		survive   bool
	}
	oldT, recentT := old, recent
	seeds := []seed{
		{uuid.New(), true, &oldT, false, false},   // published + old → PRUNED
		{uuid.New(), true, &recentT, false, true}, // published + recent → kept
		{uuid.New(), false, nil, false, true},     // pending → kept
		{uuid.New(), true, &oldT, true, true},     // dead-lettered (old) → kept (triage)
	}
	for _, s := range seeds {
		attempts := 0
		if s.published || s.dead {
			attempts = 1 // CHECK: published/dead ⇒ attempts ≥ 1
		}
		var deadAt *time.Time
		if s.dead {
			deadAt = &oldT
		}
		// A dead-lettered row is published=FALSE (it never published); a published
		// row is published=TRUE. They are mutually exclusive here.
		published := s.published && !s.dead
		if _, err := pool.Exec(ctx,
			`INSERT INTO meta_outbox
			   (event_id, event_name, aggregate_id, payload, recorded_at_nanos,
			    published, attempts, last_attempt_at, dead_lettered_at)
			 VALUES ($1,'user.consent.revoked','agg','{}'::jsonb,1,$2,$3,$4,$5)`,
			s.id, published, attempts, s.lastAt, deadAt); err != nil {
			t.Fatalf("seed %v: %v", s.id, err)
		}
	}

	p, err := New(pool, time.Hour, 1000)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	deleted, err := p.PruneOnce(ctx, now)
	if err != nil {
		t.Fatalf("PruneOnce: %v", err)
	}
	if deleted != 1 {
		t.Errorf("expected exactly 1 pruned row (published+old), got %d", deleted)
	}

	for _, s := range seeds {
		var exists bool
		if err := pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM meta_outbox WHERE event_id=$1)`, s.id).Scan(&exists); err != nil {
			t.Fatalf("exists %v: %v", s.id, err)
		}
		if exists != s.survive {
			t.Errorf("row %v: exists=%v, want survive=%v", s.id, exists, s.survive)
		}
	}
}
