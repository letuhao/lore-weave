package commands

// PG-gated test for PgArchiveListReader against a real archive_state
// (per-reality migration 0011). Gated on PIIKMS_TEST_PG_URL. Re-run-safe: scopes
// every assertion to this test's reality_id (the shared DB may carry others).

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestLive_PgArchiveListReader(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping archive-list PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	sql, rerr := os.ReadFile("../../../../contracts/migrations/per_reality/0011_archive_state.up.sql")
	if rerr != nil {
		t.Fatalf("read migration: %v", rerr)
	}
	for range 5 { // tolerate parallel-DDL deadlock on the shared test DB
		_, e := pool.Exec(ctx, string(sql))
		if e == nil || !strings.Contains(e.Error(), "deadlock") {
			if e != nil {
				t.Fatalf("apply 0011: %v", e)
			}
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	rid, other := uuid.New(), uuid.New()
	seed := func(reality uuid.UUID, part string) {
		if _, e := pool.Exec(ctx,
			`INSERT INTO archive_state (reality_id, partition_name, object_key, byte_size, row_count, format_header)
			 VALUES ($1,$2,$3,1024,42,'\x4c575031'::bytea)`, // format_header = "LWP1" (4 bytes)
			reality, part, "events/"+reality.String()+"/"+part+".parquet"); e != nil {
			t.Fatalf("seed %s: %v", part, e)
		}
	}
	seed(rid, "events_p_2025_10")
	seed(rid, "events_p_2025_11")
	seed(other, "events_p_2025_11") // a different reality — must be excluded

	got, err := NewPgArchiveListReader(pool).ListArchives(ctx, rid)
	if err != nil {
		t.Fatalf("ListArchives: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 archived partitions for this reality, got %d", len(got))
	}
	// Both belong to rid; assert fields round-tripped + scoping held.
	seen := map[string]bool{}
	for _, e := range got {
		seen[e.PartitionName] = true
		if e.RowCount != 42 || e.ByteSize != 1024 {
			t.Errorf("row fields mismatch: %+v", e)
		}
		if !strings.Contains(e.ObjectKey, rid.String()) {
			t.Errorf("object_key not scoped to this reality: %q", e.ObjectKey)
		}
	}
	if !seen["events_p_2025_10"] || !seen["events_p_2025_11"] {
		t.Errorf("missing seeded partitions: %v", seen)
	}
}
