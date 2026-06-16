package commands

// PG-gated live test for PgRealityStatsReader against a real reality_registry
// (confirms the SELECT column names/types match the schema). Gated on
// PIIKMS_TEST_PG_URL (skips in the normal job).

import (
	"context"
	"errors"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestLive_PgRealityStatsReader(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping reality-stats PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	sql, err := os.ReadFile("../../../../migrations/meta/001_reality_registry.up.sql")
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	if _, err := pool.Exec(ctx, string(sql)); err != nil {
		t.Fatalf("apply 001_reality_registry: %v", err)
	}

	id := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO reality_registry
		   (reality_id, db_host, db_name, status, locale,
		    session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
		 VALUES ($1, 'pg-shard-1.internal', 'reality_test', 'active', 'en', 50, 40, 90, 1)`,
		id); err != nil {
		t.Fatalf("seed reality_registry: %v", err)
	}

	r := NewPgRealityStatsReader(pool)
	s, err := r.ReadRealityStats(ctx, id)
	if err != nil {
		t.Fatalf("ReadRealityStats: %v", err)
	}
	if s.Status != "active" || s.Locale != "en" || s.SessionMaxTotal != 90 || s.DeployCohort != 1 {
		t.Fatalf("round-trip mismatch: %+v", s)
	}
	if s.CloseInitiatedAt != nil || s.DropScheduledAt != nil {
		t.Errorf("fresh reality should have nil lifecycle markers: %+v", s)
	}

	if _, err := r.ReadRealityStats(ctx, uuid.New()); !errors.Is(err, ErrRealityNotFound) {
		t.Errorf("unknown reality must return ErrRealityNotFound, got %v", err)
	}
}
