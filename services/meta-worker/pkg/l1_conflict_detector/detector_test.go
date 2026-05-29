package l1_conflict_detector

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeRealities struct {
	out []uuid.UUID
	err error
}

func (f *fakeRealities) RealitiesForBook(_ context.Context, _ uuid.UUID) ([]uuid.UUID, error) {
	return f.out, f.err
}

type fakeScanner struct {
	rows map[uuid.UUID][]L3EventRef
	err  error
}

func (f *fakeScanner) ScanL3EventsForAttribute(_ context.Context, realityID, _ uuid.UUID, _ string) ([]L3EventRef, error) {
	if f.err != nil {
		return nil, f.err
	}
	return f.rows[realityID], nil
}

func TestNew_RejectsMissingDeps(t *testing.T) {
	if _, err := New(Config{Realities: &fakeRealities{}}); err == nil {
		t.Error("missing Scanner not rejected")
	}
	if _, err := New(Config{Scanner: &fakeScanner{}}); err == nil {
		t.Error("missing Realities not rejected")
	}
}

func TestScan_FindsAllConflictsAcrossRealities(t *testing.T) {
	r1 := uuid.New()
	r2 := uuid.New()
	r3 := uuid.New()
	bookID := uuid.New()

	axiomVal := []byte(`"arid"`)
	conflictVal := []byte(`"tropical"`)

	scanner := &fakeScanner{
		rows: map[uuid.UUID][]L3EventRef{
			r1: {
				{EventID: uuid.New(), RealityID: r1, BookID: bookID, AttributePath: "world.climate", RecordedValue: axiomVal, RecordedAt: time.Unix(1779000000, 0).UTC()},     // OK
				{EventID: uuid.New(), RealityID: r1, BookID: bookID, AttributePath: "world.climate", RecordedValue: conflictVal, RecordedAt: time.Unix(1779000500, 0).UTC()}, // CONFLICT
			},
			r2: {
				{EventID: uuid.New(), RealityID: r2, BookID: bookID, AttributePath: "world.climate", RecordedValue: conflictVal, RecordedAt: time.Unix(1779000100, 0).UTC()}, // CONFLICT
			},
			r3: {}, // no events
		},
	}
	d, err := New(Config{Realities: &fakeRealities{out: []uuid.UUID{r1, r2, r3}}, Scanner: scanner})
	if err != nil {
		t.Fatal(err)
	}

	axiom := AxiomRef{
		CanonEntryID:  uuid.New(),
		BookID:        bookID,
		AttributePath: "world.climate",
		AxiomValue:    axiomVal,
	}
	conflicts, err := d.Scan(context.Background(), axiom)
	if err != nil {
		t.Fatal(err)
	}
	if len(conflicts) != 2 {
		t.Fatalf("expected 2 conflicts (r1 + r2 each have one), got %d", len(conflicts))
	}
	// Acceptance: zero false-negatives.
	for _, c := range conflicts {
		if c.Severity != "block" {
			t.Errorf("V1 default severity must be block: %+v", c)
		}
		if c.Reason == "" {
			t.Error("conflict missing reason")
		}
	}
}

func TestScan_NoConflictsWhenAllMatch(t *testing.T) {
	r1 := uuid.New()
	bookID := uuid.New()
	axiomVal := []byte(`"arid"`)
	scanner := &fakeScanner{
		rows: map[uuid.UUID][]L3EventRef{
			r1: {{EventID: uuid.New(), RealityID: r1, BookID: bookID, AttributePath: "world.climate", RecordedValue: axiomVal}},
		},
	}
	d, _ := New(Config{Realities: &fakeRealities{out: []uuid.UUID{r1}}, Scanner: scanner})
	conflicts, err := d.Scan(context.Background(), AxiomRef{BookID: bookID, AttributePath: "world.climate", AxiomValue: axiomVal})
	if err != nil {
		t.Fatal(err)
	}
	if len(conflicts) != 0 {
		t.Errorf("matching values must NOT conflict, got %d", len(conflicts))
	}
}

func TestScan_RealityLookupErrorPropagates(t *testing.T) {
	d, _ := New(Config{
		Realities: &fakeRealities{err: errors.New("lookup-down")},
		Scanner:   &fakeScanner{},
	})
	_, err := d.Scan(context.Background(), AxiomRef{BookID: uuid.New(), AttributePath: "x", AxiomValue: []byte("y")})
	if err == nil {
		t.Error("expected lookup error to propagate")
	}
}

func TestScan_RejectsZeroAxiomBookID(t *testing.T) {
	d, _ := New(Config{Realities: &fakeRealities{}, Scanner: &fakeScanner{}})
	if _, err := d.Scan(context.Background(), AxiomRef{}); err == nil {
		t.Error("expected zero BookID rejection")
	}
}

func TestCanonicalEqualityPredicate(t *testing.T) {
	p := CanonicalEqualityPredicate{}
	if err := p.Compatible([]byte(`"arid"`), []byte(`"arid"`)); err != nil {
		t.Errorf("identical bytes must be compatible: %v", err)
	}
	if err := p.Compatible([]byte(`"arid"`), []byte(`"tropical"`)); err == nil {
		t.Error("different bytes must conflict")
	}
	if err := p.Compatible(nil, nil); err != nil {
		t.Errorf("nil/nil must be compatible: %v", err)
	}
	if err := p.Compatible(nil, []byte(`"x"`)); err == nil {
		t.Error("nil vs non-nil must conflict")
	}
}
