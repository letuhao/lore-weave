// archive_worker_live_smoke_test.go — L2.J archive-worker live wiring (056+057).
//
// End-to-end on REAL Postgres + REAL MinIO (foundation-dev): the cold-storage
// pipeline + the restore read path.
//
//   seed an old (past-cutoff) events partition with N rows
//     → archive_loop.Run: Parquet+ZSTD encode → MinIO Put → verify
//       → archive_state RecordArchived → DETACH+DROP partition
//   → restore.RestoreMonth: MinIO Get → decode → re-INSERT events_restore_<m>
//   → assert restored rows == archived rows
//
// gated by `integration`; needs LW_INTEGRATION_DB (per-reality) +
// LW_INTEGRATION_MINIO_ENDPOINT/ACCESS/SECRET.
// Bootstrap: scripts/archive-worker-live-smoke.sh.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	_ "github.com/lib/pq"

	"github.com/loreweave/foundation/services/archive-worker/pkg/archive_loop"
	"github.com/loreweave/foundation/services/archive-worker/pkg/miniostore"
	"github.com/loreweave/foundation/services/archive-worker/pkg/object_store"
	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
	"github.com/loreweave/foundation/services/archive-worker/pkg/partition_picker"
	"github.com/loreweave/foundation/services/archive-worker/pkg/pgio"
	"github.com/loreweave/foundation/services/archive-worker/pkg/restore"
	"github.com/loreweave/foundation/services/archive-worker/pkg/state"
)

const archiveBucket = "lw-event-archive"

func TestArchiveWorkerLiveSmoke_ArchiveAndRestore(t *testing.T) {
	dsn := os.Getenv("LW_INTEGRATION_DB")
	mendpoint := os.Getenv("LW_INTEGRATION_MINIO_ENDPOINT")
	maccess := os.Getenv("LW_INTEGRATION_MINIO_ACCESS")
	msecret := os.Getenv("LW_INTEGRATION_MINIO_SECRET")
	if dsn == "" || mendpoint == "" || maccess == "" || msecret == "" {
		t.Skip("LW_INTEGRATION_DB / LW_INTEGRATION_MINIO_* not set; live stack unavailable")
	}
	ctx := context.Background()

	db := openSQL(t, dsn)
	mustApply(t, db, "contracts/migrations/per_reality/0002_events_table.up.sql")
	mustApply(t, db, "contracts/migrations/per_reality/0011_archive_state.up.sql")

	realityID := uuid.New()
	const partName = "events_p_2020_01"
	const month = "2020-01"
	const nRows = 5

	// Clean slate: a prior run DROPs the partition on success; recreate fresh.
	_, _ = db.Exec(`DROP TABLE IF EXISTS ` + partName)
	if _, err := db.Exec(`CREATE TABLE ` + partName + ` PARTITION OF events FOR VALUES FROM ('2020-01-01') TO ('2020-02-01')`); err != nil {
		t.Fatalf("create old partition: %v", err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec(`DROP TABLE IF EXISTS ` + partName)
		_, _ = db.Exec(`DROP TABLE IF EXISTS events_restore_202001`)
		_, _ = db.Exec(`DELETE FROM archive_state WHERE reality_id=$1`, realityID)
	})

	// Seed N events into the old partition (recorded_at in 2020-01).
	seedIDs := make([]uuid.UUID, nRows)
	for i := 0; i < nRows; i++ {
		eid := uuid.New()
		seedIDs[i] = eid
		if _, err := db.Exec(`
			INSERT INTO events
			    (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
			     event_type, event_version, payload, metadata, occurred_at, recorded_at)
			VALUES ($1,$2,'npc',$3,1,'npc.said',1,$4::jsonb,NULL,'2020-01-15T10:00:00Z','2020-01-15T10:00:01Z')`,
			eid, realityID, fmt.Sprintf("npc-%d", i), fmt.Sprintf(`{"i":%d}`, i)); err != nil {
			t.Fatalf("seed event %d: %v", i, err)
		}
	}

	// ── MinIO ─────────────────────────────────────────────────────────────
	store, err := miniostore.New(ctx, miniostore.Config{Endpoint: mendpoint, AccessKey: maccess, SecretKey: msecret})
	if err != nil {
		t.Fatalf("miniostore.New: %v", err)
	}
	if err := store.EnsureBucket(ctx, archiveBucket); err != nil {
		t.Fatalf("ensure bucket: %v", err)
	}
	objKey := object_store.ObjectKey(realityID.String(), month)

	// ── archive_loop ──────────────────────────────────────────────────────
	pool := openTestPool(t, ctx, dsn)
	st := state.NewPostgres(pool)
	picker, err := partition_picker.New(partition_picker.Config{
		Catalog: pgio.NewCatalog(pool), State: st, Clock: partition_picker.RealClock{}, Cutoff: 90 * 24 * time.Hour,
	})
	if err != nil {
		t.Fatalf("picker: %v", err)
	}
	loop, err := archive_loop.New(archive_loop.Config{
		Picker: picker, Source: pgio.NewRowSource(pool),
		Encoder: parquet_writer.NewEncoder(), Decoder: parquet_writer.NewDecoder(),
		Store: store, State: st, Dropper: pgio.NewPartitionDropper(pool),
		Mode: modeFull{}, Clock: archive_loop.RealClock{}, BucketName: archiveBucket,
	})
	if err != nil {
		t.Fatalf("loop: %v", err)
	}

	stats, err := loop.Run(ctx, realityID)
	if err != nil {
		t.Fatalf("loop.Run: %v", err)
	}
	if !(stats.Picked && stats.Uploaded && stats.Verified && stats.Recorded && stats.Dropped) {
		t.Fatalf("archive incomplete: %+v", stats)
	}
	if stats.Partition != partName || stats.RowCount != nRows {
		t.Errorf("stats: partition=%s rows=%d want %s/%d", stats.Partition, stats.RowCount, partName, nRows)
	}

	// Partition is gone.
	var exists bool
	if err := db.QueryRow(`SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=$1)`, partName).Scan(&exists); err != nil {
		t.Fatal(err)
	}
	if exists {
		t.Error("partition should have been DROPped")
	}
	// archive_state row present.
	var asRows int
	if err := db.QueryRow(`SELECT count(*) FROM archive_state WHERE reality_id=$1 AND partition_name=$2`, realityID, partName).Scan(&asRows); err != nil {
		t.Fatal(err)
	}
	if asRows != 1 {
		t.Errorf("archive_state rows=%d want 1", asRows)
	}
	// MinIO object present + decodes to N rows.
	blob, err := store.Get(ctx, archiveBucket, objKey)
	if err != nil {
		t.Fatalf("minio get: %v", err)
	}
	decoded, err := parquet_writer.NewDecoder().Decode(blob)
	if err != nil {
		t.Fatalf("decode archived blob: %v", err)
	}
	if len(decoded) != nRows {
		t.Errorf("decoded rows=%d want %d", len(decoded), nRows)
	}

	// ── restore round-trip ────────────────────────────────────────────────
	res, err := restore.RestoreMonth(ctx, pool, store, archiveBucket, realityID, month)
	if err != nil {
		t.Fatalf("RestoreMonth: %v", err)
	}
	if res.RowCount != nRows {
		t.Errorf("restored rows=%d want %d", res.RowCount, nRows)
	}
	var restoredCount int
	if err := db.QueryRow(`SELECT count(*) FROM ` + res.Table).Scan(&restoredCount); err != nil {
		t.Fatalf("count restore table: %v", err)
	}
	if restoredCount != nRows {
		t.Errorf("restore table rows=%d want %d", restoredCount, nRows)
	}
	// A seeded event id is present in the restore table (data integrity).
	var found int
	if err := db.QueryRow(`SELECT count(*) FROM `+res.Table+` WHERE event_id=$1`, seedIDs[0]).Scan(&found); err != nil {
		t.Fatal(err)
	}
	if found != 1 {
		t.Errorf("seeded event %s not found in restore table", seedIDs[0])
	}
}
