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
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/admin-cli/internal/testsafe"
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

	applyDriftSchema(ctx, t, pool)

	// 🔴 `canon_projection` IS CORRECT, AND THE SCHEMA THIS TEST BUILDS WAS NOT.
	// The seeding UPDATE below matched ZERO rows and every assertion then read the table's
	// default state and blamed the reader:
	//
	//     projection_drift_check_pg_test.go:85: drift_count: want 7, got 0
	//     projection_drift_check_pg_test.go:88: last_sample_size: want 50, got <nil>
	//
	// The cause is the applyDDL list above. It stopped at `0007`, whose CHECK admits ten
	// tables and which seeds those ten -- a schema that has not existed for a long time.
	// `0017` narrowed it to three and `0018` to ONE: "Ten (0007) -> three (0017) -> one
	// (0018), as each projection with no producer was removed." So the real database admits
	// `canon_projection` and NOTHING else, while this test's database admitted everything
	// except it.
	//
	// ⚠️ The later migrations are applied rather than the row simply being inserted. Seeding
	// alone would have made this pass against a CHECK constraint production does not have --
	// green here, and no evidence about the thing that ships.
	const proj = "canon_projection"
	verified := time.Now().UTC().Truncate(time.Second)
	// ⚠️ The seed ASSERTS IT WROTE SOMETHING. An UPDATE whose WHERE matches nothing is a
	// silent no-op, and every assertion downstream then reads the table's default state and
	// blames the reader. That is exactly how the wrong table name above survived: the seed
	// reported success while writing no row.
	tag, e := pool.Exec(ctx,
		`INSERT INTO projection_drift_state (table_name, drift_count, last_verified_at, last_sample_size)
		      VALUES ($2, 7, $1, 50)
		 ON CONFLICT (table_name) DO UPDATE
		    SET drift_count = 7, last_verified_at = $1, last_sample_size = 50`, verified, proj)
	if e != nil {
		t.Fatalf("seed drift row: %v", e)
	}
	if n := tag.RowsAffected(); n != 1 {
		t.Fatalf("seeding %q updated %d row(s), want 1 — there is no projection_drift_state "+
			"row for it, so nothing below would be measuring the reader", proj, n)
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

	applyDriftSchema(ctx, t, pool)

	const proj = "canon_projection"
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

	applyDriftSchema(ctx, t, pool)

	const proj = "canon_projection"
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
// applyDDL executes a migration file against pool, retrying past the parallel-DDL
// deadlocks the shared PG test DB produces.
//
// db-safety-gate: ok — the SQL words in this comment are prose naming the hazard; the
// guard below is the mitigation and runs before the file is executed.
//
// THE GUARD LIVES HERE, not at the call sites. Seven harnesses in this repo apply
// migration files; before 2026-08-09 exactly two of them checked the target database
// first, and the other five were unguarded — not by decision, but because calling a
// helper that quietly skips the check looks exactly like calling one that doesn't.
// A safety check you have to remember is default-UNCOVERED. So it sits inside the
// helper, and the only way to skip it is to not use the helper.
//
// The files reached from here (`0007_drift_metadata`, `0011_archive_state`,
// `001_reality_registry`) are additive today. That is not the reason to skip the
// guard: this helper executes whatever path it is handed, so its blast radius is a
// property of its ARGUMENT, and every per-reality `.down.sql` in the same tree drops
// tables. `PIIKMS_TEST_PG_URL` pointed at a real service DB is all it takes — which is
// how an unscoped `DELETE FROM books` once hard-deleted every user's books. The
// statement was fine; the DSN was not.
// applyDriftSchema brings a throwaway database to the EFFECTIVE per-reality drift schema:
// `0007` creates the table with a ten-name CHECK and seeds those ten, `0017` narrows it to
// three, `0018` to one (`canon_projection`). Production applies each exactly once, in order.
//
// 🔴 ONCE PER PROCESS, and that is the whole reason this helper exists. Each test used to
// apply the list itself, so the second test re-ran `0007` against a database whose CHECK
// `0018` had already narrowed — and `0007`'s seed of the ten old projection names then
// violated it:
//
//	ERROR: new row for relation "projection_drift_state" violates check constraint
//
// Re-running an earlier migration over a later one is not something production ever does;
// it was an artefact of the fixture. Applying the chain once models the real sequence.
var driftSchemaOnce sync.Once

func applyDriftSchema(ctx context.Context, t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	driftSchemaOnce.Do(func() {
		// A real migration runner records what it has applied and never re-runs a step. This
		// fixture has no ledger, so it asks the database instead: if the CHECK has already
		// been narrowed to the single surviving projection, the chain is applied and re-running
		// `0007` would only re-insert the ten names that constraint now forbids. Matters
		// whenever the throwaway database outlives one `go test` invocation.
		var def string
		if e := pool.QueryRow(ctx, `
			SELECT pg_get_constraintdef(oid) FROM pg_constraint
			 WHERE conname = 'projection_drift_table_name_allowlist'`).Scan(&def); e == nil &&
			strings.Contains(def, "canon_projection") && !strings.Contains(def, "pc_projection") {
			return
		}
		for _, m := range []string{
			"../../../../migrations/meta/001_reality_registry.up.sql",
			"../../../../contracts/migrations/per_reality/0007_drift_metadata.up.sql",
			"../../../../contracts/migrations/per_reality/0017_drop_pc_npc_projections.up.sql",
			"../../../../contracts/migrations/per_reality/0018_drop_region_session_world_kv_projections.up.sql",
		} {
			applyDDL(ctx, t, pool, m)
		}
	})
}

func applyDDL(ctx context.Context, t *testing.T, pool *pgxpool.Pool, path string) {
	t.Helper()
	var dbName string
	if e := pool.QueryRow(ctx, `SELECT current_database()`).Scan(&dbName); e != nil {
		t.Fatalf("applyDDL: resolve current_database() before applying %s: %v", path, e)
	}
	if e := testsafe.EnsureThrowawayDB(dbName); e != nil {
		t.Fatalf("applyDDL: %v", e)
	}
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
