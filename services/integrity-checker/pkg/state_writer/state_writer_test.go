package state_writer

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func frozen(t time.Time) func() time.Time { return func() time.Time { return t } }

func TestNew_RejectsNilDeps(t *testing.T) {
	if _, err := New(Config{Persister: nil, Clock: time.Now}); err == nil {
		t.Error("nil Persister should error")
	}
	if _, err := New(Config{Persister: NewInMemPersister(), Clock: nil}); err == nil {
		t.Error("nil Clock should error")
	}
}

func TestPersist_RecordsCall(t *testing.T) {
	p := NewInMemPersister()
	w, _ := New(Config{Persister: p, Clock: frozen(time.Unix(1700000000, 0).UTC())})
	rid := uuid.New()
	rep := types.DriftReport{
		RealityID:   rid,
		TableName:   "pc_projection",
		SampleSize:  20,
		DriftCount:  0,
		CheckMode:   string(types.CheckModeDaily),
		CheckedAt:   time.Unix(1700000000, 0).UTC(),
	}
	if err := w.Persist(context.Background(), rep, 24*time.Hour); err != nil {
		t.Fatalf("Persist: %v", err)
	}
	if len(p.Calls) != 1 {
		t.Fatalf("expected 1 call, got %d", len(p.Calls))
	}
	want := time.Unix(1700000000, 0).UTC().Add(24 * time.Hour)
	if !p.Calls[0].ExpectedNextSweepAt.Equal(want) {
		t.Errorf("ExpectedNextSweepAt mismatch: got %v want %v", p.Calls[0].ExpectedNextSweepAt, want)
	}
}

func TestPersist_RejectsTableOutsideAllowlist(t *testing.T) {
	w, _ := New(Config{Persister: NewInMemPersister(), Clock: time.Now})
	rep := types.DriftReport{
		RealityID:  uuid.New(),
		TableName:  "rogue_projection",
		SampleSize: 20,
		CheckMode:  string(types.CheckModeDaily),
	}
	err := w.Persist(context.Background(), rep, 24*time.Hour)
	if err == nil {
		t.Fatal("expected error for rogue table name (would violate CHECK)")
	}
}

func TestPersist_RejectsNegativeDrift(t *testing.T) {
	w, _ := New(Config{Persister: NewInMemPersister(), Clock: time.Now})
	rep := types.DriftReport{
		RealityID:  uuid.New(),
		TableName:  "pc_projection",
		DriftCount: -1,
	}
	if err := w.Persist(context.Background(), rep, 24*time.Hour); err == nil {
		t.Fatal("expected error for negative drift count")
	}
}

func TestPersist_RejectsDriftWithNilAggregateID(t *testing.T) {
	w, _ := New(Config{Persister: NewInMemPersister(), Clock: time.Now})
	rep := types.DriftReport{
		RealityID:              uuid.New(),
		TableName:              "pc_projection",
		DriftCount:             3,
		LastDriftedAggregateID: uuid.Nil,
	}
	if err := w.Persist(context.Background(), rep, 24*time.Hour); err == nil {
		t.Fatal("expected error: drift>0 must have aggregate-id")
	}
}

func TestPersist_AcceptsAll10L3ATables(t *testing.T) {
	w, _ := New(Config{Persister: NewInMemPersister(), Clock: time.Now})
	for _, name := range types.L3ATables {
		rep := types.DriftReport{
			RealityID:  uuid.New(),
			TableName:  name,
			SampleSize: 20,
			CheckMode:  string(types.CheckModeDaily),
		}
		if err := w.Persist(context.Background(), rep, 24*time.Hour); err != nil {
			t.Errorf("table %s rejected: %v", name, err)
		}
	}
}
