package commands

// PG-gated live test for PgMigrationStatusReader against a real
// instance_schema_migrations (confirms the aggregation SELECT matches the
// schema). Gated on PIIKMS_TEST_PG_URL (skips in the normal job).

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestLive_PgMigrationStatusReader(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping migration-status PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	// 002 FKs to reality_registry, so apply 001 first + seed a reality.
	for _, f := range []string{
		"../../../../migrations/meta/001_reality_registry.up.sql",
		"../../../../migrations/meta/002_instance_schema_migrations.up.sql",
	} {
		sql, rerr := os.ReadFile(f)
		if rerr != nil {
			t.Fatalf("read %s: %v", f, rerr)
		}
		if _, eerr := pool.Exec(ctx, string(sql)); eerr != nil {
			t.Fatalf("apply %s: %v", f, eerr)
		}
	}
	rid := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO reality_registry
		   (reality_id, db_host, db_name, status, locale,
		    session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
		 VALUES ($1,'pg-shard-1.internal','reality_test','active','en',50,40,90,1)`, rid); err != nil {
		t.Fatalf("seed reality: %v", err)
	}
	for _, m := range []struct {
		id     string
		failed bool
	}{{"001_a", false}, {"002_b", false}, {"003_c", true}} {
		var fail any
		if m.failed {
			fail = "boom"
		}
		if _, err := pool.Exec(ctx,
			`INSERT INTO instance_schema_migrations (reality_id, migration_id, applied_by, failure_reason)
			 VALUES ($1,$2,'orchestrator',$3)`, rid, m.id, fail); err != nil {
			t.Fatalf("seed migration %s: %v", m.id, err)
		}
	}

	r := NewPgMigrationStatusReader(pool)
	rows, err := r.ListMigrationStatus(ctx)
	if err != nil {
		t.Fatalf("ListMigrationStatus: %v", err)
	}
	// Re-run-safe: ListMigrationStatus aggregates ALL realities, and the shared
	// PG-gated test DB may carry realities seeded by prior runs / other tests.
	// Locate THIS test's reality instead of asserting a global count.
	found := false
	for _, g := range rows {
		if g.RealityID != rid {
			continue
		}
		found = true
		if g.Applied != 3 || g.Failures != 1 || g.LatestMigration != "003_c" {
			t.Fatalf("aggregation mismatch for seeded reality: %+v", g)
		}
	}
	if !found {
		t.Fatalf("seeded reality %s not found among %d summaries", rid, len(rows))
	}
}
