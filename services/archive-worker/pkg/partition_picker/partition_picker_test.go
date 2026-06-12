package partition_picker

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

type fakeCatalog struct {
	parts []types.Partition
	err   error
}

func (f *fakeCatalog) ListPartitions(_ context.Context, _ uuid.UUID) ([]types.Partition, error) {
	return f.parts, f.err
}

type fakeState struct {
	already map[string]struct{}
	err     error
}

func (f *fakeState) AlreadyArchived(_ context.Context, _ uuid.UUID) (map[string]struct{}, error) {
	return f.already, f.err
}

type frozenClock struct{ t time.Time }

func (f frozenClock) Now() time.Time { return f.t }

func mkPart(name string, lower, upper time.Time) types.Partition {
	return types.Partition{
		RealityID:  uuid.New(),
		Name:       name,
		LowerBound: lower,
		UpperBound: upper,
	}
}

func TestPickOldest_HappyPath(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	// Build 3 partitions: 2025-11 (eligible, oldest), 2025-12 (eligible),
	// 2026-04 (NOT eligible — only 1 month old).
	parts := []types.Partition{
		mkPart("events_p_2025_12", date(2025, 12, 1), date(2026, 1, 1)),
		mkPart("events_p_2025_11", date(2025, 11, 1), date(2025, 12, 1)),
		mkPart("events_p_2026_04", date(2026, 4, 1), date(2026, 5, 1)),
	}
	p, err := New(Config{
		Catalog: &fakeCatalog{parts: parts},
		State:   &fakeState{already: map[string]struct{}{}},
		Clock:   frozenClock{t: now},
	})
	if err != nil {
		t.Fatal(err)
	}
	got, err := p.PickOldest(context.Background(), uuid.New())
	if err != nil {
		t.Fatal(err)
	}
	if got == nil {
		t.Fatal("expected oldest=2025_11, got nil")
	}
	if got.Name != "events_p_2025_11" {
		t.Fatalf("expected events_p_2025_11, got %s", got.Name)
	}
}

func TestPickOldest_FiltersAlreadyArchived(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	parts := []types.Partition{
		mkPart("events_p_2025_11", date(2025, 11, 1), date(2025, 12, 1)),
		mkPart("events_p_2025_12", date(2025, 12, 1), date(2026, 1, 1)),
	}
	p, _ := New(Config{
		Catalog: &fakeCatalog{parts: parts},
		State:   &fakeState{already: map[string]struct{}{"events_p_2025_11": {}}},
		Clock:   frozenClock{t: now},
	})
	got, _ := p.PickOldest(context.Background(), uuid.New())
	if got == nil || got.Name != "events_p_2025_12" {
		t.Fatalf("expected events_p_2025_12 (2025_11 already archived), got %v", got)
	}
}

func TestPickOldest_NoEligible(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	// Only a partition from current month — not eligible.
	parts := []types.Partition{
		mkPart("events_p_2026_05", date(2026, 5, 1), date(2026, 6, 1)),
	}
	p, _ := New(Config{
		Catalog: &fakeCatalog{parts: parts},
		State:   &fakeState{already: map[string]struct{}{}},
		Clock:   frozenClock{t: now},
	})
	got, err := p.PickOldest(context.Background(), uuid.New())
	if err != nil {
		t.Fatal(err)
	}
	if got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
}

func TestPickOldest_AllAlreadyArchived(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	parts := []types.Partition{
		mkPart("events_p_2025_11", date(2025, 11, 1), date(2025, 12, 1)),
		mkPart("events_p_2025_12", date(2025, 12, 1), date(2026, 1, 1)),
	}
	p, _ := New(Config{
		Catalog: &fakeCatalog{parts: parts},
		State: &fakeState{already: map[string]struct{}{
			"events_p_2025_11": {},
			"events_p_2025_12": {},
		}},
		Clock: frozenClock{t: now},
	})
	got, _ := p.PickOldest(context.Background(), uuid.New())
	if got != nil {
		t.Fatalf("expected nil (all archived), got %v", got)
	}
}

func TestPickOldest_RejectsNilDeps(t *testing.T) {
	if _, err := New(Config{}); err == nil {
		t.Fatal("expected nil Catalog error")
	}
	if _, err := New(Config{Catalog: &fakeCatalog{}}); err == nil {
		t.Fatal("expected nil State error")
	}
	if _, err := New(Config{Catalog: &fakeCatalog{}, State: &fakeState{}}); err == nil {
		t.Fatal("expected nil Clock error")
	}
}

func TestPickOldest_CutoffDefault90d(t *testing.T) {
	// Cutoff defaults to 90d; partition whose UpperBound is 89d ago must
	// NOT be eligible; 91d ago MUST be.
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	parts := []types.Partition{
		mkPart("events_p_recent", now.Add(-100*24*time.Hour), now.Add(-89*24*time.Hour)),
		mkPart("events_p_old", now.Add(-200*24*time.Hour), now.Add(-91*24*time.Hour)),
	}
	p, _ := New(Config{
		Catalog: &fakeCatalog{parts: parts},
		State:   &fakeState{already: map[string]struct{}{}},
		Clock:   frozenClock{t: now},
	})
	got, _ := p.PickOldest(context.Background(), uuid.New())
	if got == nil || got.Name != "events_p_old" {
		t.Fatalf("expected events_p_old, got %v", got)
	}
}

func date(y int, m time.Month, d int) time.Time {
	return time.Date(y, m, d, 0, 0, 0, 0, time.UTC)
}
