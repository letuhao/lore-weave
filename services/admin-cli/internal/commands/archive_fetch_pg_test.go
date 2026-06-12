package commands

// PG-gated test for PgArchiveMetaReader against a real archive_state (per_reality
// migration 0011). Gated on PIIKMS_TEST_PG_URL. Re-run-safe: a fresh reality_id per
// run, assertions scoped to it; cleanup removes the seeded row.

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestLive_PgArchiveMetaReader(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping archive-fetch meta PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	applyDDL(ctx, t, pool, "../../../../contracts/migrations/per_reality/0011_archive_state.up.sql")

	rid := uuid.New()
	key := "events/" + rid.String() + "/2025-11.parquet"
	if _, e := pool.Exec(ctx,
		`INSERT INTO archive_state (reality_id, partition_name, object_key, byte_size, row_count, format_header)
		 VALUES ($1, 'events_p_2025_11', $2, 2048, 99, '\x4c575031'::bytea)`, // format_header = "LWP1"
		rid, key); e != nil {
		t.Fatalf("seed archive_state: %v", e)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM archive_state WHERE reality_id = $1`, rid) })

	r := NewPgArchiveMetaReader(pool)

	obj, found, err := r.LookupArchive(ctx, rid, key)
	if err != nil {
		t.Fatalf("LookupArchive: %v", err)
	}
	if !found {
		t.Fatalf("expected the seeded archive object to be found")
	}
	if obj.ObjectKey != key || obj.RowCount != 99 || obj.ByteSize != 2048 {
		t.Errorf("manifest fields mismatch: %+v", obj)
	}
	if len(obj.FormatHeader) != 4 {
		t.Errorf("format_header should be the 4-byte LWP1 magic, got %d bytes", len(obj.FormatHeader))
	}

	// A month with nothing archived → (zero, false, nil), not an error.
	_, found2, err := r.LookupArchive(ctx, rid, "events/"+rid.String()+"/2099-01.parquet")
	if err != nil {
		t.Fatalf("LookupArchive (missing): %v", err)
	}
	if found2 {
		t.Errorf("did not expect a row for an un-archived month")
	}
}
