//go:build integration

// 152 (D-IC-PGSOURCE-SCAN-LIVE-SMOKE) — live round-trip for the monthly
// full-scan cursor (pgsource.ScanRows) against real Postgres.
//
// scanSQL + the cursor codec are unit-tested in pgsource_test.go; this exercises
// the pgx method body that only runs live: the keyset cursor walks every row
// EXACTLY ONCE across batches, terminates, and the ErrOwnerPruned skip path
// emits a row with nil Owning (instead of aborting the scan) when a projection
// row's owning event is absent from `events` (archived/pruned).
//
// Gated by build tag `integration` AND env LOREWEAVE_TEST_PG_URL (a DISPOSABLE
// per-reality DB — applies 0002+0006+0009 and TRUNCATEs canon_projection, so run it on
// its OWN DB; the foundation db-smoke CI gives it `scan_smoke`). Excluded from
// the normal `go test ./...` by the build tag.
//
//	go test -tags=integration -run TestScanRows ./pkg/pgsource/...
//
// db-safety-gate: file-ok — the destructive statements here (TRUNCATE canon_projection
// and the migration re-applies that recreate tables) run ONLY after
// testsafe.EnsureThrowawayDB(current_database()) refuses a non-throwaway DB; the env
// points at a DISPOSABLE per-reality DB and the file is excluded from normal runs by
// the //go:build integration tag.

package pgsource

import (
	"context"
	"fmt"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/testsafe"
)

func mustReadMigration(t *testing.T, rel string) string {
	t.Helper()
	// cwd for `go test` is the package dir (pkg/pgsource) → repo root is 4 up.
	b, err := os.ReadFile("../../../../" + rel)
	if err != nil {
		t.Fatalf("read migration %s: %v", rel, err)
	}
	return string(b)
}

func TestScanRows_CursorWalksEveryRowOnceAndSkipsPrunedOwners(t *testing.T) {
	url := os.Getenv("LOREWEAVE_TEST_PG_URL")
	if url == "" {
		t.Skip("SKIP pgsource live-smoke: set LOREWEAVE_TEST_PG_URL to run")
	}
	ctx := context.Background()

	// Simple protocol so the multi-statement migration files (BEGIN/COMMIT + DO
	// blocks) execute in one Exec; ScanRows' parameterized queries work under it
	// too (pgx interpolates client-side).
	cfg, err := pgxpool.ParseConfig(url)
	if err != nil {
		t.Fatalf("parse config: %v", err)
	}
	cfg.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeSimpleProtocol
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer pool.Close()

	// SAFETY GUARD — before any destructive statement (this test re-applies migrations
	// that recreate tables, then TRUNCATEs canon_projection). Refuse to proceed unless the
	// target is a recognizable throwaway DB, so a LOREWEAVE_TEST_PG_URL accidentally
	// pointed at a real service DB can never be wiped.
	var dbName string
	if err := pool.QueryRow(ctx, `SELECT current_database()`).Scan(&dbName); err != nil {
		t.Fatalf("current_database: %v", err)
	}
	if err := testsafe.EnsureThrowawayDB(dbName); err != nil {
		t.Fatal(err)
	}

	for _, m := range []string{
		"contracts/migrations/per_reality/0002_events_table.up.sql",
		"contracts/migrations/per_reality/0006_projections.up.sql",
		// 0009 creates canon_projection, the only projection left after `0018`.
		"contracts/migrations/per_reality/0009_canon_projection.up.sql",
	} {
		if _, err := pool.Exec(ctx, mustReadMigration(t, m)); err != nil {
			t.Fatalf("apply %s: %v", m, err)
		}
	}
	// Clean slate so the row count is exactly what we seed (0006 is IF NOT EXISTS;
	// 0002 already recreated events).
	if _, err := pool.Exec(ctx, "TRUNCATE canon_projection"); err != nil {
		t.Fatalf("truncate canon_projection: %v", err)
	}

	// The EMPTY branch of TableLagSeconds, asserted BEFORE the seed. There is
	// only one projection since `0018`, so it can no longer be a different
	// table -- which makes this stronger: the same table proves both branches,
	// so a lag reader that ignored its argument entirely would be caught.
	if emptySampler, e := New(pool); e != nil {
		t.Fatal(e)
	} else if _, ok, e := emptySampler.TableLagSeconds(ctx, "canon_projection"); e != nil || ok {
		t.Errorf("empty canon_projection lag: ok=%v err=%v (want ok=false, no error)", ok, e)
	}

	const n = 7
	realityID := uuid.New()
	prunedIdx := 4 // this row's owning event is intentionally NOT seeded into events
	canonIDs := make([]uuid.UUID, n)
	for i := 0; i < n; i++ {
		canonID := uuid.New()
		canonIDs[i] = canonID
		eventID := uuid.New()
		// The projection row (carries event_id → the owner-resolution boundary).
		if _, err := pool.Exec(ctx,
			"INSERT INTO canon_projection (canon_entry_id, book_id, attribute_path, value, "+
				"canon_layer, source_event_id, event_id, aggregate_version) "+
				"VALUES ($1, $2, $3, to_jsonb($4::text), 'L2_seeded', $5, $5, 1)",
			canonID, uuid.New(), fmt.Sprintf("things/t%d/kind", i), "a value", eventID,
		); err != nil {
			t.Fatalf("seed canon_projection[%d]: %v", i, err)
		}
		if i == prunedIdx {
			continue // no events row → owner lookup must yield ErrOwnerPruned → SKIP
		}
		if _, err := pool.Exec(ctx,
			"INSERT INTO events (event_id, reality_id, aggregate_type, aggregate_id, "+
				"aggregate_version, event_type, event_version, payload, occurred_at, recorded_at) "+
				"VALUES ($1, $2, 'canon', $3, 1, 'canon.entry.created', 1, '{}'::jsonb, "+
				"'2026-06-15T12:00:00Z'::timestamptz, date_trunc('month', now()) + ($4 * interval '1 second'))",
			eventID, realityID, canonID.String(), i,
		); err != nil {
			t.Fatalf("seed events[%d]: %v", i, err)
		}
	}

	sampler, err := New(pool)
	if err != nil {
		t.Fatal(err)
	}

	// Walk with batchSize < n so pagination spans multiple batches.
	const batchSize = 3
	seen := map[string]int{}
	prunedSkips := 0
	cursor := ""
	iters := 0
	for {
		iters++
		if iters > 100 {
			t.Fatal("cursor did not terminate")
		}
		rows, next, err := sampler.NextBatch(ctx, realityID, "canon_projection", cursor, batchSize)
		if err != nil {
			t.Fatalf("NextBatch cursor=%q: %v", cursor, err)
		}
		if len(rows) == 0 && next == "" {
			break
		}
		if len(rows) > batchSize {
			t.Fatalf("batch overran limit: %d > %d", len(rows), batchSize)
		}
		for _, r := range rows {
			pk := r.PK["canon_entry_id"]
			seen[pk]++
			if len(r.Owning) == 0 {
				prunedSkips++ // pruned-owner row emitted with nil Owning (not an error)
			} else if len(r.Owning) != 1 || r.Owning[0].Type != "canon" || r.Owning[0].ID != pk {
				t.Errorf("row %s: unexpected owning %+v", pk, r.Owning)
			}
		}
		if next == "" {
			break
		}
		if next == cursor {
			t.Fatalf("cursor did not advance (%q)", cursor)
		}
		cursor = next
	}

	// Every seeded row visited EXACTLY once.
	if len(seen) != n {
		t.Errorf("distinct rows visited = %d, want %d", len(seen), n)
	}
	for pk, c := range seen {
		if c != 1 {
			t.Errorf("row %s visited %d times (keyset cursor must visit each once)", pk, c)
		}
	}
	// Exactly the one pruned-owner row was emitted with nil Owning (skipped, not
	// erroring the scan) — the MED-1 fix from the 145-slice1 /review-impl.
	if prunedSkips != 1 {
		t.Errorf("pruned-owner skips = %d, want 1", prunedSkips)
	}

	// 153: TableLagSeconds (live.LagReader). The just-seeded canon_projection has
	// rows (applied_at defaulted to NOW()) → ok=true + a small non-negative lag;
	// an untouched table → ok=false (no max(applied_at)).
	if lag, ok, err := sampler.TableLagSeconds(ctx, "canon_projection"); err != nil || !ok || lag < 0 {
		t.Errorf("canon_projection lag: lag=%v ok=%v err=%v (want ok + non-negative)", lag, ok, err)
	}
	// (the ok=false branch is asserted BEFORE the seed, above.)
}
