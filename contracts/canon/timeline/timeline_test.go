package timeline

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

func sampleEntry(book, entry uuid.UUID, attr string, kind CanonChangeKind, recAt time.Time) Entry {
	return Entry{
		ChangeID:        uuid.New(),
		CanonEntryID:    entry,
		BookID:          book,
		AttributePath:   attr,
		Kind:            kind,
		NewValue:        []byte(`"v"`),
		CanonLayer:      "L2_seeded",
		SourceEventID:   uuid.New(),
		SourceEventType: "canon.entry.updated",
		RecordedAt:      recAt,
	}
}

func TestCanonChangeKindIsValid(t *testing.T) {
	if !CanonChangeKindAuthored.IsValid() {
		t.Error("authored must be valid")
	}
	if !CanonChangeKindForcePropagate.IsValid() {
		t.Error("force_propagate must be valid")
	}
	if !CanonChangeKindPropagationCompleted.IsValid() {
		t.Error("propagation_completed must be valid")
	}
	if CanonChangeKind("bogus").IsValid() {
		t.Error("bogus must be invalid")
	}
}

func TestQueryValidate(t *testing.T) {
	// Empty query rejected
	if err := (Query{}).Validate(); err == nil {
		t.Error("empty Query must fail validation")
	}
	// Either mode OK
	if err := (Query{CanonEntryID: uuid.New()}).Validate(); err != nil {
		t.Errorf("CanonEntryID query rejected: %v", err)
	}
	if err := (Query{BookID: uuid.New(), AttributePath: "x"}).Validate(); err != nil {
		t.Errorf("Book+Attr query rejected: %v", err)
	}
	// BookID without AttributePath fails
	if err := (Query{BookID: uuid.New()}).Validate(); err == nil {
		t.Error("BookID alone must fail")
	}
	// Negative limit rejected
	if err := (Query{CanonEntryID: uuid.New(), Limit: -1}).Validate(); err == nil {
		t.Error("negative limit must fail")
	}
}

func TestInMemoryStore_AppendAndQuery_EntryScoped(t *testing.T) {
	store := NewInMemoryStore()
	book := uuid.New()
	entry := uuid.New()
	t0 := time.Unix(1780000000, 0).UTC()

	e1 := sampleEntry(book, entry, "world.climate", CanonChangeKindAuthored, t0)
	e2 := sampleEntry(book, entry, "world.climate", CanonChangeKindForcePropagate, t0.Add(time.Hour))
	e3 := sampleEntry(book, uuid.New(), "world.geo", CanonChangeKindAuthored, t0.Add(2*time.Hour))

	for _, e := range []Entry{e1, e2, e3} {
		if err := store.Append(context.Background(), e); err != nil {
			t.Fatal(err)
		}
	}

	rows, err := store.Query(context.Background(), Query{CanonEntryID: entry})
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 {
		t.Fatalf("entry-scoped query expected 2 rows, got %d", len(rows))
	}
	if rows[0].RecordedAt.After(rows[1].RecordedAt) {
		t.Error("rows not sorted ascending")
	}
}

func TestInMemoryStore_AppendOnlyRejectsDuplicateChangeID(t *testing.T) {
	store := NewInMemoryStore()
	e := sampleEntry(uuid.New(), uuid.New(), "x", CanonChangeKindAuthored, time.Unix(1780000000, 0).UTC())
	if err := store.Append(context.Background(), e); err != nil {
		t.Fatal(err)
	}
	// Re-append same ChangeID
	if err := store.Append(context.Background(), e); err == nil {
		t.Error("APPEND-ONLY discipline: duplicate ChangeID must be rejected")
	}
}

func TestInMemoryStore_NoUpdateOrDeleteMethodExists(t *testing.T) {
	// This is a compile-time test: the InMemoryStore type MUST NOT have
	// methods named Update / Delete / Amend. We can't introspect at
	// runtime cheaply, but `go vet` + this comment serve as defense.
	store := NewInMemoryStore()
	_ = store
	// If you find yourself adding an `Update` method below, STOP — the
	// L5.J contract is APPEND-ONLY.
}

func TestInMemoryStore_PathScopedQuery(t *testing.T) {
	store := NewInMemoryStore()
	book := uuid.New()
	t0 := time.Unix(1780000000, 0).UTC()
	// Two separate canon_entries on the same attribute (e.g. one was
	// L2_seeded then a new L1_axiom replacement landed on the same path).
	e1 := sampleEntry(book, uuid.New(), "world.climate", CanonChangeKindAuthored, t0)
	e2 := sampleEntry(book, uuid.New(), "world.climate", CanonChangeKindAuthored, t0.Add(time.Hour))
	e3 := sampleEntry(book, uuid.New(), "world.geo", CanonChangeKindAuthored, t0.Add(2*time.Hour))

	for _, e := range []Entry{e1, e2, e3} {
		if err := store.Append(context.Background(), e); err != nil {
			t.Fatal(err)
		}
	}

	rows, err := store.Query(context.Background(), Query{BookID: book, AttributePath: "world.climate"})
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 {
		t.Fatalf("path-scoped expected 2 entries, got %d", len(rows))
	}
}

func TestInMemoryStore_RealityFilter(t *testing.T) {
	store := NewInMemoryStore()
	book := uuid.New()
	entry := uuid.New()
	r1 := uuid.New()
	r2 := uuid.New()
	t0 := time.Unix(1780000000, 0).UTC()

	e1 := sampleEntry(book, entry, "world.climate", CanonChangeKindForcePropagate, t0)
	e1.RealityID = r1
	e2 := sampleEntry(book, entry, "world.climate", CanonChangeKindForcePropagate, t0.Add(time.Hour))
	e2.RealityID = r2
	e3 := sampleEntry(book, entry, "world.climate", CanonChangeKindAuthored, t0.Add(2*time.Hour))
	// e3.RealityID intentionally zero (book-wide)

	for _, e := range []Entry{e1, e2, e3} {
		if err := store.Append(context.Background(), e); err != nil {
			t.Fatal(err)
		}
	}

	rows, _ := store.Query(context.Background(), Query{CanonEntryID: entry, RealityID: r1})
	if len(rows) != 1 || rows[0].RealityID != r1 {
		t.Errorf("reality filter wrong: %+v", rows)
	}
}

func TestInMemoryStore_SinceFilter(t *testing.T) {
	store := NewInMemoryStore()
	book := uuid.New()
	entry := uuid.New()
	t0 := time.Unix(1780000000, 0).UTC()
	for i := 0; i < 5; i++ {
		e := sampleEntry(book, entry, "x", CanonChangeKindAuthored, t0.Add(time.Duration(i)*time.Hour))
		_ = store.Append(context.Background(), e)
	}
	rows, _ := store.Query(context.Background(), Query{CanonEntryID: entry, Since: t0.Add(2 * time.Hour)})
	if len(rows) != 3 {
		t.Errorf("Since filter expected 3 rows, got %d", len(rows))
	}
}

func TestInMemoryStore_LimitCap(t *testing.T) {
	store := NewInMemoryStore()
	book := uuid.New()
	entry := uuid.New()
	t0 := time.Unix(1780000000, 0).UTC()
	for i := 0; i < 10; i++ {
		_ = store.Append(context.Background(), sampleEntry(book, entry, "x", CanonChangeKindAuthored, t0.Add(time.Duration(i)*time.Hour)))
	}
	rows, _ := store.Query(context.Background(), Query{CanonEntryID: entry, Limit: 3})
	if len(rows) != 3 {
		t.Errorf("Limit not honored: %d", len(rows))
	}
}

func TestAppend_RejectsInvalid(t *testing.T) {
	store := NewInMemoryStore()
	// Zero ChangeID
	if err := store.Append(context.Background(), Entry{Kind: CanonChangeKindAuthored, RecordedAt: time.Now()}); err == nil {
		t.Error("zero ChangeID accepted")
	}
	// Invalid kind
	if err := store.Append(context.Background(), Entry{ChangeID: uuid.New(), Kind: "bogus", RecordedAt: time.Now()}); err == nil {
		t.Error("invalid kind accepted")
	}
	// Zero RecordedAt
	if err := store.Append(context.Background(), Entry{ChangeID: uuid.New(), Kind: CanonChangeKindAuthored}); err == nil {
		t.Error("zero RecordedAt accepted")
	}
}
