package migrate

// 22-A1 — LIVE test of backfillScenesBookID against real Postgres.
//
// migrate_test.go locks the schema STRINGS; it never executes a statement. The
// backfill's real hazards are all runtime ones — the keyset cursor advancing past a
// batch boundary, the `book_id IS NULL` filter interacting with that cursor, the
// UPDATE ... FROM chapters join, marker gating, and crash-retry convergence. None of
// those are observable without a database, and spec 22 explicitly forbids a bare
// full-table UPDATE (10k+ chapter books are real), so the batching is load-bearing.
//
// Gated on BOOK_TEST_DATABASE_URL, a THROWAWAY database (this drops tables).

import (
	"context"
	"fmt"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func scenesTestPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("BOOK_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("BOOK_TEST_DATABASE_URL not set — DB-gated test skipped")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		t.Skipf("BOOK_TEST_DATABASE_URL unreachable (%v) — skipping", err)
	}
	if err := Up(ctx, pool); err != nil {
		pool.Close()
		t.Fatalf("migrate.Up: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

// seedScenes creates one book + one chapter + n scenes whose book_id is forced back
// to NULL, i.e. exactly the pre-migration shape the backfill must repair.
func seedScenes(t *testing.T, ctx context.Context, pool *pgxpool.Pool, n int) (bookID uuid.UUID) {
	t.Helper()
	owner := uuid.New()
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'backfill') RETURNING id`, owner,
	).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	var chID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,'c.txt','en','text/plain',1,'k','active','draft') RETURNING id`, bookID).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	for i := 0; i < n; i++ {
		if _, err := pool.Exec(ctx, `
INSERT INTO scenes(chapter_id,sort_order,path,leaf_text,content_hash,book_id)
VALUES($1,$2,$3,'prose',$4,NULL)`, chID, i, fmt.Sprintf("/s/%d", i), fmt.Sprintf("h%d", i)); err != nil {
			t.Fatalf("seed scene %d: %v", i, err)
		}
	}
	return bookID
}

// resetBackfill clears the marker so the function runs again on an already-migrated DB.
func resetBackfill(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	if _, err := pool.Exec(ctx, `DELETE FROM scenes_book_id_backfill_migration`); err != nil {
		t.Fatalf("reset marker: %v", err)
	}
}

func nullBookIDCount(t *testing.T, ctx context.Context, pool *pgxpool.Pool) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE book_id IS NULL`).Scan(&n); err != nil {
		t.Fatalf("count nulls: %v", err)
	}
	return n
}

// The batch boundary is where a keyset loop actually breaks: 1201 rows exercises two
// full batches plus a partial one, so an off-by-one in the `id > lastID` cursor (or a
// premature `len(ids) < batchSize` break) leaves rows behind and fails here.
func TestBackfillScenesBookID_AcrossBatchBoundaries(t *testing.T) {
	ctx := context.Background()
	pool := scenesTestPool(t)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books`) })

	const n = 2*scenesBookIDBackfillBatchSize + 201 // 1201
	bookID := seedScenes(t, ctx, pool, n)
	resetBackfill(t, ctx, pool)

	if got := nullBookIDCount(t, ctx, pool); got != n {
		t.Fatalf("precondition: want %d NULL book_id rows, got %d", n, got)
	}
	if err := backfillScenesBookID(ctx, pool); err != nil {
		t.Fatalf("backfill: %v", err)
	}
	if got := nullBookIDCount(t, ctx, pool); got != 0 {
		t.Fatalf("backfill left %d rows with NULL book_id (keyset cursor skipped rows)", got)
	}

	var wrong int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM scenes WHERE book_id IS DISTINCT FROM $1`, bookID,
	).Scan(&wrong); err != nil {
		t.Fatalf("verify: %v", err)
	}
	if wrong != 0 {
		t.Fatalf("%d scenes got a book_id that is not their chapter's book", wrong)
	}

	var marked bool
	if err := pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM scenes_book_id_backfill_migration WHERE id='scenes_book_id_backfill_v1')`,
	).Scan(&marked); err != nil {
		t.Fatalf("marker: %v", err)
	}
	if !marked {
		t.Fatal("backfill completed but never stamped its marker — it would rescan every boot")
	}
}

// Crash mid-run: the copy is a pure function of chapters.book_id, so re-running must
// converge, not corrupt. Simulated by clearing the marker and re-running over a set
// that is already PARTIALLY filled (the `book_id IS NULL` filter must skip the rest).
func TestBackfillScenesBookID_CrashRetryConverges(t *testing.T) {
	ctx := context.Background()
	pool := scenesTestPool(t)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books`) })

	const n = 600
	bookID := seedScenes(t, ctx, pool, n)
	resetBackfill(t, ctx, pool)

	// Simulate a crash after the first batch: fill 500, leave 100 NULL.
	if _, err := pool.Exec(ctx, `
UPDATE scenes s SET book_id = c.book_id FROM chapters c
WHERE c.id = s.chapter_id AND s.id IN (SELECT id FROM scenes ORDER BY id LIMIT 500)`); err != nil {
		t.Fatalf("simulate partial: %v", err)
	}
	if got := nullBookIDCount(t, ctx, pool); got != 100 {
		t.Fatalf("precondition: want 100 NULL rows, got %d", got)
	}

	if err := backfillScenesBookID(ctx, pool); err != nil {
		t.Fatalf("retry: %v", err)
	}
	if got := nullBookIDCount(t, ctx, pool); got != 0 {
		t.Fatalf("crash-retry left %d NULL rows", got)
	}
	var wrong int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM scenes WHERE book_id IS DISTINCT FROM $1`, bookID,
	).Scan(&wrong); err != nil {
		t.Fatalf("verify: %v", err)
	}
	if wrong != 0 {
		t.Fatalf("crash-retry produced %d wrong book_id values", wrong)
	}
}

// The marker is the whole point of the gate: a completed install must not rescan.
func TestBackfillScenesBookID_MarkerSkipsSecondRun(t *testing.T) {
	ctx := context.Background()
	pool := scenesTestPool(t)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books`) })

	seedScenes(t, ctx, pool, 3)
	resetBackfill(t, ctx, pool)
	if err := backfillScenesBookID(ctx, pool); err != nil {
		t.Fatalf("first run: %v", err)
	}

	// A new scene arrives with no book_id (the 22-A5 write-path gap). With the marker
	// stamped the backfill is a no-op, so the row stays NULL — this pins the CURRENT,
	// deliberate A1 behavior. 22-A5 wires the parse writers AND re-runs the backfill
	// under a bumped marker (scenes_book_id_backfill_v2); when it lands, this test's
	// expectation flips to 0 and that flip is the proof A5 closed the window.
	var chID uuid.UUID
	if err := pool.QueryRow(ctx, `SELECT id FROM chapters LIMIT 1`).Scan(&chID); err != nil {
		t.Fatalf("chapter: %v", err)
	}
	if _, err := pool.Exec(ctx, `
INSERT INTO scenes(chapter_id,sort_order,path,leaf_text,content_hash,book_id)
VALUES($1,99,'/late','prose','hlate',NULL)`, chID); err != nil {
		t.Fatalf("late scene: %v", err)
	}
	if err := backfillScenesBookID(ctx, pool); err != nil {
		t.Fatalf("second run: %v", err)
	}
	if got := nullBookIDCount(t, ctx, pool); got != 1 {
		t.Fatalf("marker gate not honoured: want the late row still NULL (1), got %d", got)
	}
}
