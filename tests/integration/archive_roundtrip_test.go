//go:build integration

// tests/integration/archive_roundtrip_test.go — L2.J end-to-end coverage.
//
// Cycle 11. NOT a docker-required test (the L2.J production wiring is
// deferred); this test exercises the archive_loop with in-mem fakes to
// guarantee the cross-package contract holds:
//
//   1. Partition picker → row source → parquet encode → object store put →
//      verify-after-upload → archive_state record → partition drop
//   2. Round-trip: archived blob is byte-decodable back to the original
//      EventRow slice
//   3. Re-running the loop on the same reality is a no-op (idempotency)
//   4. Failed upload does NOT DROP the partition (invariant guard)
//
// When the L4 production wiring lands (D-PUBLISHER-LIVE-WIRING shape applied
// to archive-worker), this test gains a `//go:build integration_live` variant
// that drives a real pgx + minio-go stack.

package integration

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/archive-worker/pkg/archive_loop"
	"github.com/loreweave/foundation/services/archive-worker/pkg/object_store"
	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
	"github.com/loreweave/foundation/services/archive-worker/pkg/partition_picker"
	"github.com/loreweave/foundation/services/archive-worker/pkg/state"
	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// ──────────── test fakes ────────────────────────────────────────────────

type stubCatalog struct{ parts []types.Partition }

func (s *stubCatalog) ListPartitions(_ context.Context, _ uuid.UUID) ([]types.Partition, error) {
	return s.parts, nil
}

type stubRowSource struct{ rows []types.EventRow }

func (s *stubRowSource) LoadPartition(_ context.Context, _ types.Partition) ([]types.EventRow, error) {
	return s.rows, nil
}

type recordingDropper struct{ calls []string }

func (d *recordingDropper) Drop(_ context.Context, p types.Partition) error {
	d.calls = append(d.calls, p.Name)
	return nil
}

type fakeMode struct{ m lifecycle.ServiceMode }

func (f fakeMode) Mode() lifecycle.ServiceMode { return f.m }

type frozenClock struct{ t time.Time }

func (f frozenClock) Now() time.Time { return f.t }

type pickerStateAdapter struct{ store state.Store }

func (a *pickerStateAdapter) AlreadyArchived(ctx context.Context, realityID uuid.UUID) (map[string]struct{}, error) {
	return a.store.AlreadyArchived(ctx, realityID)
}

// ──────────── helpers ────────────────────────────────────────────────────

func mkArchiveEvents(n int) []types.EventRow {
	rows := make([]types.EventRow, n)
	for i := 0; i < n; i++ {
		rows[i] = types.EventRow{
			EventID:          uuid.New(),
			RealityID:        uuid.New(),
			AggregateType:    "npc",
			AggregateID:      "npc-1",
			AggregateVersion: uint64(i + 1),
			EventType:        "npc.said",
			EventVersion:     1,
			Payload:          []byte(`{"text":"hello"}`),
			OccurredAt:       time.Date(2025, 11, 1, 12, 0, 0, 0, time.UTC),
			RecordedAt:       time.Date(2025, 11, 1, 12, 0, 1, 0, time.UTC),
		}
	}
	return rows
}

func mkPartition() types.Partition {
	return types.Partition{
		RealityID:  uuid.New(),
		Name:       "events_p_2025_11",
		LowerBound: time.Date(2025, 11, 1, 0, 0, 0, 0, time.UTC),
		UpperBound: time.Date(2025, 12, 1, 0, 0, 0, 0, time.UTC),
	}
}

func newArchiveLoop(t *testing.T, rows []types.EventRow, parts []types.Partition, store object_store.Store, dropper archive_loop.PartitionDropper) (*archive_loop.Loop, state.Store) {
	t.Helper()
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	st := state.NewInMemory()
	picker, err := partition_picker.New(partition_picker.Config{
		Catalog: &stubCatalog{parts: parts},
		State:   &pickerStateAdapter{store: st},
		Clock:   frozenClock{t: now},
	})
	if err != nil {
		t.Fatal(err)
	}
	l, err := archive_loop.New(archive_loop.Config{
		Picker:     picker,
		Source:     &stubRowSource{rows: rows},
		Encoder:    parquet_writer.NewEncoder(),
		Decoder:    parquet_writer.NewDecoder(),
		Store:      store,
		State:      st,
		Dropper:    dropper,
		Mode:       fakeMode{m: lifecycle.ModeFull},
		Clock:      frozenClock{t: now},
		BucketName: "lw-event-archive",
	})
	if err != nil {
		t.Fatal(err)
	}
	return l, st
}

// ──────────── tests ─────────────────────────────────────────────────────

func TestArchiveRoundTrip_DecodedRowsEqualOriginal(t *testing.T) {
	parts := []types.Partition{mkPartition()}
	rows := mkArchiveEvents(50)
	store := object_store.NewInMemory()
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	loop, st := newArchiveLoop(t, rows, parts, store, dropper)
	stats, err := loop.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Picked || !stats.Uploaded || !stats.Verified || !stats.Recorded || !stats.Dropped {
		t.Fatalf("flags: %+v", stats)
	}
	if stats.RowCount != 50 {
		t.Fatalf("RowCount: got %d want 50", stats.RowCount)
	}

	// Round-trip
	manifest, _ := st.List(context.Background(), rid)
	if len(manifest) != 1 {
		t.Fatalf("expected 1 archive_state row, got %d", len(manifest))
	}
	blob, err := store.Get(context.Background(), "lw-event-archive", manifest[0].ObjectKey)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := parquet_writer.NewDecoder().Decode(blob)
	if err != nil {
		t.Fatal(err)
	}
	if len(decoded) != len(rows) {
		t.Fatalf("round-trip row count: got %d want %d", len(decoded), len(rows))
	}
	for i, r := range rows {
		if decoded[i].EventID != r.EventID {
			t.Errorf("row %d EventID mismatch: got=%s want=%s", i, decoded[i].EventID, r.EventID)
		}
	}
}

func TestArchive_Idempotent_SecondRunNoop(t *testing.T) {
	parts := []types.Partition{mkPartition()}
	rows := mkArchiveEvents(10)
	store := object_store.NewInMemory()
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	loop, _ := newArchiveLoop(t, rows, parts, store, dropper)
	if _, err := loop.Run(context.Background(), rid); err != nil {
		t.Fatal(err)
	}
	stats, err := loop.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Picked {
		t.Fatal("INVARIANT VIOLATED: second run re-picked already-archived partition")
	}
	if len(dropper.calls) != 1 {
		t.Fatalf("expected exactly 1 DROP across 2 runs, got %d", len(dropper.calls))
	}
}

func TestArchive_FailedUpload_DoesNotDrop(t *testing.T) {
	parts := []types.Partition{mkPartition()}
	rows := mkArchiveEvents(5)
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	loop, st := newArchiveLoop(t, rows, parts, &object_store.FailingStore{}, dropper)
	_, err := loop.Run(context.Background(), rid)
	if err == nil {
		t.Fatal("expected upload error")
	}
	if len(dropper.calls) != 0 {
		t.Fatalf("INVARIANT VIOLATED: partition dropped despite upload failure: %v", dropper.calls)
	}
	manifest, _ := st.List(context.Background(), rid)
	if len(manifest) != 0 {
		t.Fatal("INVARIANT VIOLATED: archive_state recorded despite upload failure")
	}
}
