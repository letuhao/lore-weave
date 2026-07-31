package pgsource

// PG-gated test for the meta_outbox drain SQL: proves the FOR UPDATE SKIP LOCKED
// pending scan, the jsonb/xreality_topic scan, and Mark{Published,DeadLetter}
// against the shipped migration 030. Gated on PIIKMS_TEST_PG_URL.

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/publisher/pkg/retry"
)

// applyMigrationWithRetry tolerates the catalog deadlock (SQLSTATE 40P01) that
// occurs when this gated test and the tests/integration smoke apply the same
// CREATE TABLE/INDEX concurrently (go runs packages in parallel). IF NOT EXISTS
// makes the apply idempotent; the retry handles the concurrent-DDL lock race.
func applyMigrationWithRetry(ctx context.Context, pool *pgxpool.Pool, sql string) error {
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

func TestLive_PgSource_DrainAndMark(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping meta-outbox-relay pgsource PG test")
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
	if eerr := applyMigrationWithRetry(ctx, pool, string(sql)); eerr != nil {
		t.Fatalf("apply 030: %v", eerr)
	}

	// Seed: one cross-reality row (xreality_topic set) + one meta-only row.
	xrealID := uuid.New()
	metaID := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO meta_outbox (event_id, event_name, aggregate_id, payload, xreality_topic, recorded_at_nanos)
		 VALUES ($1,'user.erased','u1','{"table":"pii_kek"}'::jsonb,'xreality.user.erased',1),
		        ($2,'user.consent.revoked','u1','{"table":"user_consent_ledger"}'::jsonb,NULL,2)`,
		xrealID, metaID); err != nil {
		t.Fatalf("seed: %v", err)
	}

	src, err := New(pool, retry.DefaultPolicy())
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	// The drain is FIFO — `ORDER BY enqueued_at ASC LIMIT $1` — so a fixed batch size
	// only contains the rows THIS test seeded while the table holds fewer than that many
	// pending rows. Every `*_pg_test.go` in this repo shares one throwaway DB
	// (PIIKMS_TEST_PG_URL), and sibling suites leave pending rows behind, so the fixed
	// `10` silently drained ten OTHER rows and the two seeded here never appeared.
	//
	// This test had never run in CI (no workflow set the DSN), so the fragility was
	// invisible: on its first real execution it failed with 17 pending rows in the
	// table. Size the batch from the live pending count instead of a constant — no
	// mutation of other suites' rows, and correct on a fresh or a dirty database.
	var pending int
	if qerr := pool.QueryRow(ctx,
		`SELECT count(*) FROM meta_outbox WHERE published = FALSE AND dead_lettered_at IS NULL`,
	).Scan(&pending); qerr != nil {
		t.Fatalf("count pending: %v", qerr)
	}
	batch, err := src.Begin(ctx, pending+10)
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}
	rows := batch.Rows()
	// Filter to just our two seeded rows (the DB may carry rows from other tests).
	// PRESENCE is tracked separately from VALUE: a map lookup alone returns "" both for
	// "row came back with no topic" and for "row never came back", which is what made
	// the original failure message unreadable — and which made the meta-only assertion
	// below pass vacuously when neither row was in the batch.
	got := map[string]string{} // event_id → xreality_topic ("" if none)
	seen := map[string]bool{}
	for _, r := range rows {
		if r.EventID == xrealID.String() || r.EventID == metaID.String() {
			got[r.EventID] = r.XRealityTopic
			seen[r.EventID] = true
			if len(r.Payload) == 0 {
				t.Errorf("row %s payload not parsed", r.EventID)
			}
		}
	}
	if !seen[xrealID.String()] {
		t.Fatalf("cross-reality row never reached the batch (%d pending, batch=%d, got %d rows) "+
			"— the drain did not return the row this test seeded", pending, pending+10, len(rows))
	}
	if !seen[metaID.String()] {
		t.Fatalf("meta-only row never reached the batch (%d pending, batch=%d, got %d rows)",
			pending, pending+10, len(rows))
	}
	if got[xrealID.String()] != "xreality.user.erased" {
		t.Errorf("cross-reality row xreality_topic mismatch: %q", got[xrealID.String()])
	}
	if got[metaID.String()] != "" {
		t.Errorf("meta-only row must have empty xreality_topic, got %q", got[metaID.String()])
	}

	if err := batch.MarkPublished(ctx, xrealID.String()); err != nil {
		t.Fatalf("MarkPublished: %v", err)
	}
	if err := batch.MarkDeadLetter(ctx, metaID.String(), 1, "boom"); err != nil {
		t.Fatalf("MarkDeadLetter: %v", err)
	}
	if err := batch.Commit(ctx); err != nil {
		t.Fatalf("Commit: %v", err)
	}

	var published bool
	if err := pool.QueryRow(ctx, `SELECT published FROM meta_outbox WHERE event_id=$1`, xrealID).Scan(&published); err != nil {
		t.Fatalf("requery published: %v", err)
	}
	if !published {
		t.Error("xreality row must be published after MarkPublished+Commit")
	}
	var deadLettered bool
	if err := pool.QueryRow(ctx, `SELECT dead_lettered_at IS NOT NULL FROM meta_outbox WHERE event_id=$1`, metaID).Scan(&deadLettered); err != nil {
		t.Fatalf("requery dead_lettered: %v", err)
	}
	if !deadLettered {
		t.Error("meta-only row must be dead-lettered after MarkDeadLetter+Commit")
	}

	// The two rows we marked must no longer appear in a fresh pending scan.
	batch2, err := src.Begin(ctx, 10)
	if err != nil {
		t.Fatalf("Begin#2: %v", err)
	}
	defer func() { _ = batch2.Rollback(ctx) }()
	for _, r := range batch2.Rows() {
		if r.EventID == xrealID.String() || r.EventID == metaID.String() {
			t.Errorf("row %s should have left the pending scan (published/dead-lettered)", r.EventID)
		}
	}
}
