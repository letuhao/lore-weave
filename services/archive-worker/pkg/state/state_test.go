package state

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

func TestInMemory_RecordAndQuery(t *testing.T) {
	s := NewInMemory()
	rid := uuid.New()
	obj := types.ArchivedObject{
		RealityID:    rid,
		Partition:    "events_p_2025_11",
		ObjectKey:    "events/" + rid.String() + "/2025-11.parquet",
		ByteSize:     1024,
		RowCount:     100,
		ArchivedAt:   time.Now(),
		FormatHeader: [4]byte{'L', 'W', 'P', '1'},
	}
	if err := s.RecordArchived(context.Background(), obj); err != nil {
		t.Fatal(err)
	}
	got, _ := s.AlreadyArchived(context.Background(), rid)
	if _, ok := got["events_p_2025_11"]; !ok {
		t.Fatal("expected partition recorded")
	}
}

func TestInMemory_RecordIdempotent(t *testing.T) {
	s := NewInMemory()
	rid := uuid.New()
	obj := types.ArchivedObject{RealityID: rid, Partition: "events_p_2025_11"}
	if err := s.RecordArchived(context.Background(), obj); err != nil {
		t.Fatal(err)
	}
	// Second write with a different RowCount must NOT overwrite.
	obj2 := obj
	obj2.RowCount = 999
	if err := s.RecordArchived(context.Background(), obj2); err != nil {
		t.Fatal(err)
	}
	list, _ := s.List(context.Background(), rid)
	if len(list) != 1 {
		t.Fatalf("expected 1 row, got %d", len(list))
	}
	if list[0].RowCount != 0 {
		t.Fatalf("idempotency broken: expected first writer wins, got RowCount=%d", list[0].RowCount)
	}
}

func TestInMemory_PerRealityIsolation(t *testing.T) {
	s := NewInMemory()
	r1 := uuid.New()
	r2 := uuid.New()
	_ = s.RecordArchived(context.Background(), types.ArchivedObject{RealityID: r1, Partition: "events_p_2025_11"})
	_ = s.RecordArchived(context.Background(), types.ArchivedObject{RealityID: r2, Partition: "events_p_2025_12"})
	got1, _ := s.AlreadyArchived(context.Background(), r1)
	got2, _ := s.AlreadyArchived(context.Background(), r2)
	if len(got1) != 1 || len(got2) != 1 {
		t.Fatalf("per-reality isolation broken: r1=%d r2=%d", len(got1), len(got2))
	}
	if _, ok := got1["events_p_2025_12"]; ok {
		t.Fatal("r1 sees r2's partition — isolation broken")
	}
}

func TestInMemory_EmptyReality(t *testing.T) {
	s := NewInMemory()
	got, err := s.AlreadyArchived(context.Background(), uuid.New())
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Fatalf("expected empty, got %d", len(got))
	}
}
