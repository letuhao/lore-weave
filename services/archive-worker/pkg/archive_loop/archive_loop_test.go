package archive_loop

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/archive-worker/pkg/object_store"
	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
	"github.com/loreweave/foundation/services/archive-worker/pkg/partition_picker"
	"github.com/loreweave/foundation/services/archive-worker/pkg/state"
	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// ───── test fakes ───────────────────────────────────────────────────────

type fakeCatalog struct{ parts []types.Partition }

func (f *fakeCatalog) ListPartitions(_ context.Context, _ uuid.UUID) ([]types.Partition, error) {
	return f.parts, nil
}

type fakeSource struct{ rows []types.EventRow }

func (f *fakeSource) LoadPartition(_ context.Context, _ types.Partition) ([]types.EventRow, error) {
	return f.rows, nil
}

type recordingDropper struct{ calls []string }

func (d *recordingDropper) Drop(_ context.Context, p types.Partition) error {
	d.calls = append(d.calls, p.Name)
	return nil
}

type failingDropper struct{}

func (failingDropper) Drop(_ context.Context, _ types.Partition) error {
	return errors.New("simulated drop failure")
}

type fakeMode struct{ m lifecycle.ServiceMode }

func (f fakeMode) Mode() lifecycle.ServiceMode { return f.m }

type frozenClock struct{ t time.Time }

func (f frozenClock) Now() time.Time { return f.t }

// ───── helpers ──────────────────────────────────────────────────────────

func mkRow(seed int) types.EventRow {
	return types.EventRow{
		EventID:          uuid.New(),
		RealityID:        uuid.New(),
		AggregateType:    "npc",
		AggregateID:      "npc-1",
		AggregateVersion: uint64(seed),
		EventType:        "npc.said",
		EventVersion:     1,
		Payload:          []byte(`{"k":"v"}`),
		OccurredAt:       time.Date(2025, 11, 1, 12, 0, 0, 0, time.UTC),
		RecordedAt:       time.Date(2025, 11, 1, 12, 0, 1, 0, time.UTC),
	}
}

func mkPart(name string) types.Partition {
	return types.Partition{
		RealityID:  uuid.New(),
		Name:       name,
		LowerBound: time.Date(2025, 11, 1, 0, 0, 0, 0, time.UTC),
		UpperBound: time.Date(2025, 12, 1, 0, 0, 0, 0, time.UTC),
	}
}

func mkLoop(t *testing.T, parts []types.Partition, rows []types.EventRow,
	store object_store.Store, dropper PartitionDropper) (*Loop, state.Store, *fakePickerState) {
	t.Helper()
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	st := state.NewInMemory()
	pickerState := &fakePickerState{store: st}
	picker, err := partition_picker.New(partition_picker.Config{
		Catalog: &fakeCatalog{parts: parts},
		State:   pickerState,
		Clock:   frozenClock{t: now},
	})
	if err != nil {
		t.Fatal(err)
	}
	l, err := New(Config{
		Picker:     picker,
		Source:     &fakeSource{rows: rows},
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
	return l, st, pickerState
}

// fakePickerState bridges partition_picker.StateReader to state.Store.
type fakePickerState struct {
	store state.Store
}

func (f *fakePickerState) AlreadyArchived(ctx context.Context, realityID uuid.UUID) (map[string]struct{}, error) {
	return f.store.AlreadyArchived(ctx, realityID)
}

// ───── tests ────────────────────────────────────────────────────────────

func TestRun_HappyPath(t *testing.T) {
	parts := []types.Partition{mkPart("events_p_2025_11")}
	rows := []types.EventRow{mkRow(1), mkRow(2)}
	store := object_store.NewInMemory()
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	loop, st, _ := mkLoop(t, parts, rows, store, dropper)

	stats, err := loop.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Picked || !stats.Uploaded || !stats.Verified || !stats.Recorded || !stats.Dropped {
		t.Fatalf("happy-path flags: %+v", stats)
	}
	if stats.RowCount != 2 {
		t.Fatalf("expected RowCount=2, got %d", stats.RowCount)
	}
	if len(dropper.calls) != 1 || dropper.calls[0] != "events_p_2025_11" {
		t.Fatalf("expected one DROP call for events_p_2025_11, got %v", dropper.calls)
	}
	// archive_state recorded
	rows2, _ := st.List(context.Background(), rid)
	if len(rows2) != 1 {
		t.Fatalf("expected 1 archive_state row, got %d", len(rows2))
	}
	// Round-trip: read back from store, decode, count rows.
	blob, _ := store.Get(context.Background(), "lw-event-archive", rows2[0].ObjectKey)
	decoded, err := parquet_writer.NewDecoder().Decode(blob)
	if err != nil {
		t.Fatal(err)
	}
	if len(decoded) != 2 {
		t.Fatalf("round-trip rows: got %d want 2", len(decoded))
	}
}

func TestRun_NothingEligible_NoOp(t *testing.T) {
	store := object_store.NewInMemory()
	dropper := &recordingDropper{}
	rid := uuid.New()
	// No partitions at all.
	loop, _, _ := mkLoop(t, nil, nil, store, dropper)
	stats, err := loop.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Picked {
		t.Fatal("expected Picked=false when nothing eligible")
	}
	if len(dropper.calls) != 0 {
		t.Fatalf("expected zero drops, got %v", dropper.calls)
	}
}

func TestRun_Idempotent_SecondRunSkipsArchivedPartition(t *testing.T) {
	parts := []types.Partition{mkPart("events_p_2025_11")}
	rows := []types.EventRow{mkRow(1)}
	store := object_store.NewInMemory()
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	loop, _, _ := mkLoop(t, parts, rows, store, dropper)

	// First run archives.
	if _, err := loop.Run(context.Background(), rid); err != nil {
		t.Fatal(err)
	}
	// Second run finds nothing (picker filters via archive_state).
	stats, err := loop.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Picked {
		t.Fatalf("second run MUST NOT re-pick already-archived partition, got %+v", stats)
	}
	// And the dropper was only called ONCE.
	if len(dropper.calls) != 1 {
		t.Fatalf("expected exactly 1 DROP across both runs (idempotent), got %v", dropper.calls)
	}
}

func TestRun_DegradedMode_Skipped(t *testing.T) {
	parts := []types.Partition{mkPart("events_p_2025_11")}
	rows := []types.EventRow{mkRow(1)}
	store := object_store.NewInMemory()
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	loop, _, _ := mkLoop(t, parts, rows, store, dropper)
	// Re-mode the loop to ModeEssentials.
	loop.mode = fakeMode{m: lifecycle.ModeEssentials}

	stats, err := loop.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Skipped {
		t.Fatal("expected Skipped=true under ModeEssentials")
	}
	if len(dropper.calls) != 0 {
		t.Fatal("expected no DROP under degraded mode")
	}
}

func TestRun_FailedUpload_DoesNotDrop(t *testing.T) {
	parts := []types.Partition{mkPart("events_p_2025_11")}
	rows := []types.EventRow{mkRow(1)}
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	loop, st, _ := mkLoop(t, parts, rows, &object_store.FailingStore{Err: errors.New("network down")}, dropper)

	_, err := loop.Run(context.Background(), rid)
	if err == nil {
		t.Fatal("expected upload error")
	}
	if len(dropper.calls) != 0 {
		t.Fatalf("INVARIANT VIOLATED: partition dropped despite upload failure: %v", dropper.calls)
	}
	rows2, _ := st.List(context.Background(), rid)
	if len(rows2) != 0 {
		t.Fatalf("INVARIANT VIOLATED: archive_state recorded despite upload failure: %v", rows2)
	}
}

func TestRun_FailedDrop_StatePreservedForRecovery(t *testing.T) {
	parts := []types.Partition{mkPart("events_p_2025_11")}
	rows := []types.EventRow{mkRow(1)}
	store := object_store.NewInMemory()
	rid := parts[0].RealityID

	loop, st, _ := mkLoop(t, parts, rows, store, failingDropper{})

	_, err := loop.Run(context.Background(), rid)
	if err == nil {
		t.Fatal("expected drop error")
	}
	// archive_state SHOULD be recorded (data safe in MinIO; operator can
	// finish the DROP per runbook).
	rows2, _ := st.List(context.Background(), rid)
	if len(rows2) != 1 {
		t.Fatalf("expected archive_state recorded even on DROP failure (data safe), got %d", len(rows2))
	}
}

func TestRun_VerifyHeaderRejectsCorruptUpload(t *testing.T) {
	// Use a store that mutates the blob between Put and Get to simulate
	// a corrupted upload (S3 silent corruption is the real-world risk).
	parts := []types.Partition{mkPart("events_p_2025_11")}
	rows := []types.EventRow{mkRow(1)}
	dropper := &recordingDropper{}
	rid := parts[0].RealityID

	store := newCorruptingStore()
	loop, st, _ := mkLoop(t, parts, rows, store, dropper)

	_, err := loop.Run(context.Background(), rid)
	if err == nil {
		t.Fatal("expected verify error")
	}
	if len(dropper.calls) != 0 {
		t.Fatalf("INVARIANT VIOLATED: partition dropped despite verify failure: %v", dropper.calls)
	}
	rows2, _ := st.List(context.Background(), rid)
	if len(rows2) != 0 {
		t.Fatal("INVARIANT VIOLATED: archive_state recorded despite verify failure")
	}
}

func TestNew_RejectsNilDeps(t *testing.T) {
	_, err := New(Config{})
	if err == nil {
		t.Fatal("expected nil-Picker error")
	}
}

// corruptingStore tampers the returned blob to simulate S3 silent corruption.
type corruptingStore struct {
	inner *object_store.InMemory
}

func newCorruptingStore() *corruptingStore { return &corruptingStore{inner: object_store.NewInMemory()} }

func (c *corruptingStore) Get(ctx context.Context, bucket, k string) ([]byte, error) {
	b, err := c.inner.Get(ctx, bucket, k)
	if err != nil {
		return nil, err
	}
	if len(b) > 0 {
		b[0] = 'X'
	}
	return b, nil
}

func (c *corruptingStore) Put(ctx context.Context, bucket, k string, blob []byte) error {
	return c.inner.Put(ctx, bucket, k, blob)
}

func (c *corruptingStore) Exists(ctx context.Context, bucket, k string) (bool, error) {
	return c.inner.Exists(ctx, bucket, k)
}
