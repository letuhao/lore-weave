package commands

// PG-gated test for PgProjectionDriftReader against real reality_registry (meta) +
// projection_drift_state (per_reality 0007). Gated on PIIKMS_TEST_PG_URL. The single
// test DB plays BOTH meta and shard roles — the injected dsnFor returns the test DSN
// for every enumerated reality. Re-run-safe: a fresh reality_id per run + assertions
// scoped to it; cleanup removes the seeded reality and resets the drift row.

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestLive_PgProjectionDriftReader(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping projection drift-check PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	applyDDL(ctx, t, pool, "../../../../migrations/meta/001_reality_registry.up.sql")
	applyDDL(ctx, t, pool, "../../../../contracts/migrations/per_reality/0007_drift_metadata.up.sql")

	const proj = "world_kv_projection" // one of the 10 allowlist tables; low-traffic choice
	verified := time.Now().UTC().Truncate(time.Second)
	if _, e := pool.Exec(ctx,
		`UPDATE projection_drift_state
		    SET drift_count = 7, last_verified_at = $1, last_sample_size = 50
		  WHERE table_name = $2`, verified, proj); e != nil {
		t.Fatalf("seed drift row: %v", e)
	}

	rid := uuid.New()
	if _, e := pool.Exec(ctx,
		`INSERT INTO reality_registry
		   (reality_id, db_host, db_name, status, locale,
		    session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
		 VALUES ($1, 'pg-shard-1.internal', 'r_drift_test', 'active', 'en', 4, 4, 8, 0)`,
		rid); e != nil {
		t.Fatalf("seed reality_registry: %v", e)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM reality_registry WHERE reality_id = $1`, rid)
		_, _ = pool.Exec(ctx,
			`UPDATE projection_drift_state
			    SET drift_count = 0, last_verified_at = NULL, last_sample_size = NULL
			  WHERE table_name = $1`, proj)
	})

	// dsnFor ignores the (host, name) and routes every reality back to the test DB.
	reader := NewPgProjectionDriftReader(pool, func(_, _ string) (string, error) { return dsn, nil })
	rows, err := reader.DriftForProjection(ctx, proj)
	if err != nil {
		t.Fatalf("DriftForProjection: %v", err)
	}

	// Scope the assertion to OUR reality (the shared DB may carry other realities).
	var mine *DriftRow
	for i := range rows {
		if rows[i].RealityID == rid {
			mine = &rows[i]
			break
		}
	}
	if mine == nil {
		t.Fatalf("our reality %s not in fleet result (%d rows)", rid, len(rows))
	}
	if mine.ReadErr != "" {
		t.Fatalf("unexpected read error for our reality: %s", mine.ReadErr)
	}
	if mine.DriftCount != 7 {
		t.Errorf("drift_count: want 7, got %d", mine.DriftCount)
	}
	if mine.LastSampleSize == nil || *mine.LastSampleSize != 50 {
		t.Errorf("last_sample_size: want 50, got %v", mine.LastSampleSize)
	}
	if mine.LastVerifiedAt == nil || !mine.LastVerifiedAt.Equal(verified) {
		t.Errorf("last_verified_at: want %s, got %v", verified, mine.LastVerifiedAt)
	}

	// Formatting path over the real rows.
	out, err := RunProjectionDriftCheck(ctx, proj, 100, reader)
	if err != nil {
		t.Fatalf("RunProjectionDriftCheck: %v", err)
	}
	if !strings.Contains(out, "drift=7") {
		t.Errorf("rendered output missing our drift row:\n%s", out)
	}
}

// TestLive_PgProjectionDriftReader_ToleratesDownShard proves D1: when one reality's
// shard is unreachable, the fleet read captures it as ReadErr and still succeeds (the
// other shard reports normally) — the invariant the unit FleetAggregate test only
// proves at the formatter, never at the implementing loop.
func TestLive_PgProjectionDriftReader_ToleratesDownShard(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping down-shard PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	applyDDL(ctx, t, pool, "../../../../migrations/meta/001_reality_registry.up.sql")
	applyDDL(ctx, t, pool, "../../../../contracts/migrations/per_reality/0007_drift_metadata.up.sql")

	const proj = "npc_projection"
	if _, e := pool.Exec(ctx, `UPDATE projection_drift_state SET drift_count = 2 WHERE table_name = $1`, proj); e != nil {
		t.Fatalf("seed drift row: %v", e)
	}
	good, bad := uuid.New(), uuid.New()
	for _, r := range []struct {
		id   uuid.UUID
		name string
	}{{good, "r_good"}, {bad, "r_bad"}} {
		if _, e := pool.Exec(ctx,
			`INSERT INTO reality_registry
			   (reality_id, db_host, db_name, status, locale,
			    session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
			 VALUES ($1, 'pg-shard-1.internal', $2, 'active', 'en', 4, 4, 8, 0)`, r.id, r.name); e != nil {
			t.Fatalf("seed reality %s: %v", r.name, e)
		}
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM reality_registry WHERE reality_id = ANY($1)`, []uuid.UUID{good, bad})
		_, _ = pool.Exec(ctx, `UPDATE projection_drift_state SET drift_count = 0 WHERE table_name = $1`, proj)
	})

	// Route r_bad to an unroutable DSN (connection refused → ReadErr), r_good to the live DB.
	reader := NewPgProjectionDriftReader(pool, func(_, name string) (string, error) {
		if name == "r_bad" {
			return "postgres://x:x@127.0.0.1:1/none?sslmode=disable", nil
		}
		return dsn, nil
	})
	rows, err := reader.DriftForProjection(ctx, proj)
	if err != nil {
		t.Fatalf("fleet read must NOT fail when one shard is down: %v", err)
	}
	var g, b *DriftRow
	for i := range rows {
		switch rows[i].RealityID {
		case good:
			g = &rows[i]
		case bad:
			b = &rows[i]
		}
	}
	if g == nil || b == nil {
		t.Fatalf("expected both seeded realities in fleet result (%d rows)", len(rows))
	}
	if g.ReadErr != "" {
		t.Errorf("good shard should read clean, got ReadErr=%q", g.ReadErr)
	}
	if g.DriftCount != 2 {
		t.Errorf("good shard drift_count: want 2, got %d", g.DriftCount)
	}
	if b.ReadErr == "" {
		t.Errorf("down shard should yield a ReadErr, got none")
	}
}

// TestLive_PgProjectionDriftReader_MissingRowFlagged proves the ErrNoRows path sets
// MissingRow (distinct from never-verified) when a shard has no row for the projection.
func TestLive_PgProjectionDriftReader_MissingRowFlagged(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping missing-row PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	applyDDL(ctx, t, pool, "../../../../migrations/meta/001_reality_registry.up.sql")
	applyDDL(ctx, t, pool, "../../../../contracts/migrations/per_reality/0007_drift_metadata.up.sql")

	const proj = "session_participants"
	// Remove the migration-seeded row so readOne hits ErrNoRows for this projection.
	if _, e := pool.Exec(ctx, `DELETE FROM projection_drift_state WHERE table_name = $1`, proj); e != nil {
		t.Fatalf("delete drift row: %v", e)
	}
	rid := uuid.New()
	if _, e := pool.Exec(ctx,
		`INSERT INTO reality_registry
		   (reality_id, db_host, db_name, status, locale,
		    session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
		 VALUES ($1, 'pg-shard-1.internal', 'r_missing_test', 'active', 'en', 4, 4, 8, 0)`, rid); e != nil {
		t.Fatalf("seed reality_registry: %v", e)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM reality_registry WHERE reality_id = $1`, rid)
		_, _ = pool.Exec(ctx, `INSERT INTO projection_drift_state (table_name) VALUES ($1) ON CONFLICT (table_name) DO NOTHING`, proj)
	})

	reader := NewPgProjectionDriftReader(pool, func(_, _ string) (string, error) { return dsn, nil })
	rows, err := reader.DriftForProjection(ctx, proj)
	if err != nil {
		t.Fatalf("DriftForProjection: %v", err)
	}
	var mine *DriftRow
	for i := range rows {
		if rows[i].RealityID == rid {
			mine = &rows[i]
			break
		}
	}
	if mine == nil {
		t.Fatalf("our reality %s not in fleet result", rid)
	}
	if !mine.MissingRow {
		t.Errorf("expected MissingRow=true for a shard with no drift row, got %+v", mine)
	}
	if mine.ReadErr != "" {
		t.Errorf("a missing row is not a read error, got ReadErr=%q", mine.ReadErr)
	}
}

// applyDDL applies a migration file, tolerating parallel-DDL deadlocks on the shared
// test DB (mirrors archive_list_pg_test.go).
func applyDDL(ctx context.Context, t *testing.T, pool *pgxpool.Pool, path string) {
	t.Helper()
	sql, rerr := os.ReadFile(path)
	if rerr != nil {
		t.Fatalf("read migration %s: %v", path, rerr)
	}
	for range 5 {
		_, e := pool.Exec(ctx, string(sql))
		if e == nil {
			return
		}
		if !strings.Contains(e.Error(), "deadlock") {
			t.Fatalf("apply %s: %v", path, e)
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("apply %s: still deadlocking after retries", path)
}
