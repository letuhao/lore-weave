package l1_conflict_reporter

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/foundation/services/meta-worker/pkg/l1_conflict_detector"
)

type fakeRealities struct{ out []uuid.UUID }

func (f *fakeRealities) RealitiesForBook(_ context.Context, _ uuid.UUID) ([]uuid.UUID, error) {
	return f.out, nil
}

type fakeScanner struct {
	rows map[uuid.UUID][]l1_conflict_detector.L3EventRef
}

func (f *fakeScanner) ScanL3EventsForAttribute(_ context.Context, realityID, _ uuid.UUID, _ string) ([]l1_conflict_detector.L3EventRef, error) {
	return f.rows[realityID], nil
}

func newDetectorWithConflict(t *testing.T) (*l1_conflict_detector.Detector, uuid.UUID, uuid.UUID) {
	t.Helper()
	r1 := uuid.New()
	bookID := uuid.New()
	axiomVal := []byte(`"arid"`)
	conflictVal := []byte(`"tropical"`)
	scanner := &fakeScanner{
		rows: map[uuid.UUID][]l1_conflict_detector.L3EventRef{
			r1: {{EventID: uuid.New(), RealityID: r1, BookID: bookID, AttributePath: "world.climate", RecordedValue: conflictVal}},
		},
	}
	d, err := l1_conflict_detector.New(l1_conflict_detector.Config{
		Realities: &fakeRealities{out: []uuid.UUID{r1}},
		Scanner:   scanner,
	})
	if err != nil {
		t.Fatal(err)
	}
	_ = axiomVal
	return d, bookID, r1
}

func TestNew_RejectsMissingDeps(t *testing.T) {
	if _, err := New(Config{Store: NewInMemoryStore()}); err == nil {
		t.Error("nil Detector accepted")
	}
	if _, err := New(Config{Detector: &l1_conflict_detector.Detector{}}); err == nil {
		t.Error("nil Store accepted")
	}
}

func TestScanAndPersist_StoresReport(t *testing.T) {
	d, bookID, _ := newDetectorWithConflict(t)
	store := NewInMemoryStore()
	clk := time.Unix(1780000000, 0).UTC()
	r, err := New(Config{Detector: d, Store: store, Clock: func() time.Time { return clk }})
	if err != nil {
		t.Fatal(err)
	}
	axiom := l1_conflict_detector.AxiomRef{
		CanonEntryID:  uuid.New(),
		BookID:        bookID,
		AttributePath: "world.climate",
		AxiomValue:    []byte(`"arid"`),
	}
	rep, err := r.ScanAndPersist(context.Background(), axiom)
	if err != nil {
		t.Fatal(err)
	}
	if len(rep.Conflicts) != 1 {
		t.Errorf("expected 1 conflict, got %d", len(rep.Conflicts))
	}
	if rep.GeneratedAt != clk {
		t.Errorf("clock not honored: %s vs %s", rep.GeneratedAt, clk)
	}
	if store.Count() != 1 {
		t.Errorf("store must hold 1 report, got %d", store.Count())
	}
}

func TestLatestForAxiom_RoundTrip(t *testing.T) {
	d, bookID, _ := newDetectorWithConflict(t)
	store := NewInMemoryStore()
	r, _ := New(Config{Detector: d, Store: store})
	axiom := l1_conflict_detector.AxiomRef{
		CanonEntryID:  uuid.New(),
		BookID:        bookID,
		AttributePath: "world.climate",
		AxiomValue:    []byte(`"arid"`),
	}
	saved, err := r.ScanAndPersist(context.Background(), axiom)
	if err != nil {
		t.Fatal(err)
	}
	fetched, found, err := r.LatestForAxiom(context.Background(), axiom.CanonEntryID)
	if err != nil {
		t.Fatal(err)
	}
	if !found {
		t.Fatal("expected report to exist")
	}
	if fetched.ReportID != saved.ReportID {
		t.Error("ReportID mismatch on round-trip")
	}
}

func TestLatestForAxiom_AbsentReturnsFalse(t *testing.T) {
	d, _, _ := newDetectorWithConflict(t)
	store := NewInMemoryStore()
	r, _ := New(Config{Detector: d, Store: store})
	_, found, err := r.LatestForAxiom(context.Background(), uuid.New())
	if err != nil {
		t.Fatal(err)
	}
	if found {
		t.Error("expected not-found for unsaved axiom")
	}
}
