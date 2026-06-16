package canon_writer

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
)

// ─────────────────────────────────────────────────────────────────────────
// Test doubles.
// ─────────────────────────────────────────────────────────────────────────

type fakeSubs struct {
	subs map[uuid.UUID][]uuid.UUID
	err  error
}

func (f *fakeSubs) SubscribersForBook(_ context.Context, bookID uuid.UUID) ([]uuid.UUID, error) {
	if f.err != nil {
		return nil, f.err
	}
	return append([]uuid.UUID(nil), f.subs[bookID]...), nil
}

type fakeDB struct {
	mu     sync.Mutex
	writes []UpsertIntent
	// failOn: realityID for which UpsertCanon returns err. zero = always succeed.
	failOn  uuid.UUID
	failErr error
}

func (f *fakeDB) UpsertCanon(_ context.Context, in UpsertIntent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failOn != uuid.Nil && in.RealityID == f.failOn {
		return f.failErr
	}
	f.writes = append(f.writes, in)
	return nil
}

func (f *fakeDB) Writes() []UpsertIntent {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]UpsertIntent, len(f.writes))
	copy(out, f.writes)
	return out
}

type fakeAudit struct {
	mu      sync.Mutex
	entries []AuditEntry
	failErr error
}

func (f *fakeAudit) WriteAudit(_ context.Context, e AuditEntry) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failErr != nil {
		return f.failErr
	}
	f.entries = append(f.entries, e)
	return nil
}

func (f *fakeAudit) Entries() []AuditEntry {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]AuditEntry, len(f.entries))
	copy(out, f.entries)
	return out
}

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

// ─────────────────────────────────────────────────────────────────────────
// Helpers.
// ─────────────────────────────────────────────────────────────────────────

func mustUUID(t *testing.T) uuid.UUID {
	t.Helper()
	return uuid.New()
}

func newTestWriter(t *testing.T, bookID uuid.UUID, realities []uuid.UUID) (*Writer, *fakeDB, *fakeAudit) {
	t.Helper()
	subs := &fakeSubs{subs: map[uuid.UUID][]uuid.UUID{bookID: realities}}
	db := &fakeDB{}
	au := &fakeAudit{}
	w, err := New(Config{
		Subscribers: subs,
		DB:          db,
		Audit:       au,
		Clock:       fixedClock{t: time.Unix(1700000000, 0).UTC()},
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return w, db, au
}

// ─────────────────────────────────────────────────────────────────────────
// New / Config validation.
// ─────────────────────────────────────────────────────────────────────────

func TestNew_RequiresDeps(t *testing.T) {
	cases := []struct {
		name string
		cfg  Config
	}{
		{"no subs", Config{DB: &fakeDB{}, Audit: &fakeAudit{}}},
		{"no db", Config{Subscribers: &fakeSubs{}, Audit: &fakeAudit{}}},
		{"no audit", Config{Subscribers: &fakeSubs{}, DB: &fakeDB{}}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := New(c.cfg)
			if err == nil {
				t.Fatalf("expected error, got nil")
			}
		})
	}
}

func TestNew_DefaultClock(t *testing.T) {
	w, err := New(Config{
		Subscribers: &fakeSubs{},
		DB:          &fakeDB{},
		Audit:       &fakeAudit{},
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	if w.clock == nil {
		t.Fatalf("default clock not set")
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Happy path: fan-out across realities + audit per write.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_CanonCreated_FansOutAndAudits(t *testing.T) {
	book := mustUUID(t)
	r1, r2, r3 := mustUUID(t), mustUUID(t), mustUUID(t)
	w, db, au := newTestWriter(t, book, []uuid.UUID{r1, r2, r3})

	entry := mustUUID(t)
	evID := mustUUID(t)
	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonCreated,
		"event_id":       evID.String(),
		"canon_entry_id": entry.String(),
		"book_id":        book.String(),
		"attribute_path": "characters/alice/race",
		"canon_layer":    "L2_seeded",
		"value":          `{"race":"elf"}`,
	})
	if err != nil {
		t.Fatalf("Handle: %v", err)
	}

	writes := db.Writes()
	if len(writes) != 3 {
		t.Fatalf("expected 3 fan-out writes, got %d", len(writes))
	}
	seen := map[uuid.UUID]bool{}
	for _, w := range writes {
		seen[w.RealityID] = true
		if w.CanonEntryID != entry || w.BookID != book {
			t.Errorf("write mismatch entry=%s book=%s", w.CanonEntryID, w.BookID)
		}
		if w.CanonLayer != "L2_seeded" {
			t.Errorf("canon_layer=%s want L2_seeded", w.CanonLayer)
		}
		if w.LockLevel != "soft" {
			t.Errorf("lock_level=%s want soft (default)", w.LockLevel)
		}
		if w.SourceEventID != evID {
			t.Errorf("source_event_id=%s want %s", w.SourceEventID, evID)
		}
		if w.LastSyncedAt.IsZero() {
			t.Errorf("LastSyncedAt zero")
		}
		if string(w.Value) != `{"race":"elf"}` {
			t.Errorf("value=%q want %q", string(w.Value), `{"race":"elf"}`)
		}
	}
	if !(seen[r1] && seen[r2] && seen[r3]) {
		t.Errorf("not all realities written: %v", seen)
	}

	// Q-L1A-3 full audit: one entry per write.
	entries := au.Entries()
	if len(entries) != 3 {
		t.Fatalf("expected 3 audit entries, got %d", len(entries))
	}
	for _, e := range entries {
		if e.EventID != evID || e.CanonEntryID != entry {
			t.Errorf("audit mismatch: %+v", e)
		}
		if e.EventType != EventCanonCreated {
			t.Errorf("audit event_type=%s", e.EventType)
		}
	}
}

func TestHandle_ThreadsAggregateVersion(t *testing.T) {
	book := mustUUID(t)
	r1 := mustUUID(t)
	// aggregate_version arrives as a string after a Redis round-trip, or as a
	// native number from in-memory dispatch. Both must thread to the intent.
	for _, av := range []any{"7", 7, int64(7), float64(7), uint64(7)} {
		w, db, _ := newTestWriter(t, book, []uuid.UUID{r1})
		err := w.Handle(context.Background(), map[string]any{
			"event_type":        EventCanonCreated,
			"event_id":          mustUUID(t).String(),
			"canon_entry_id":    mustUUID(t).String(),
			"book_id":           book.String(),
			"attribute_path":    "x/y",
			"canon_layer":       "L2_seeded",
			"value":             `{"a":1}`,
			"aggregate_version": av,
		})
		if err != nil {
			t.Fatalf("Handle(av=%v): %v", av, err)
		}
		writes := db.Writes()
		if len(writes) != 1 || writes[0].AggregateVersion != 7 {
			t.Errorf("av=%v(%T): AggregateVersion=%d want 7", av, av, writes[0].AggregateVersion)
		}
	}
}

func TestHandle_ValueAsMap_MarshalsToJSON(t *testing.T) {
	// After the Redis round-trip the consumer flattens `value` back into a Go
	// map (not a string). The writer MUST re-marshal it so canon_projection
	// gets the real value, not 'null'. Regression guard for the dropped-value
	// HIGH bug found in /review-impl.
	book := mustUUID(t)
	r1 := mustUUID(t)
	w, db, _ := newTestWriter(t, book, []uuid.UUID{r1})
	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonCreated,
		"event_id":       mustUUID(t).String(),
		"canon_entry_id": mustUUID(t).String(),
		"book_id":        book.String(),
		"attribute_path": "characters/alice/race",
		"canon_layer":    "L2_seeded",
		"value":          map[string]any{"race": "elf"}, // a Go map, not a string
	})
	if err != nil {
		t.Fatalf("Handle: %v", err)
	}
	writes := db.Writes()
	if len(writes) != 1 {
		t.Fatalf("writes=%d want 1", len(writes))
	}
	if string(writes[0].Value) != `{"race":"elf"}` {
		t.Errorf("value=%q want %q (map dropped to null?)", string(writes[0].Value), `{"race":"elf"}`)
	}
}

func TestHandle_CanonUpdated_NewValueOverridesValue(t *testing.T) {
	book := mustUUID(t)
	r1 := mustUUID(t)
	w, db, _ := newTestWriter(t, book, []uuid.UUID{r1})

	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonUpdated,
		"event_id":       uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"book_id":        book.String(),
		"attribute_path": "p",
		"canon_layer":    "L2_seeded",
		"new_value":      `{"v":2}`,
	})
	if err != nil {
		t.Fatalf("Handle: %v", err)
	}
	writes := db.Writes()
	if len(writes) != 1 {
		t.Fatalf("expected 1 write, got %d", len(writes))
	}
	if string(writes[0].Value) != `{"v":2}` {
		t.Errorf("expected new_value carried as Value, got %q", string(writes[0].Value))
	}
}

func TestHandle_CanonPromoted_UsesToLayer(t *testing.T) {
	book := mustUUID(t)
	r1 := mustUUID(t)
	w, db, _ := newTestWriter(t, book, []uuid.UUID{r1})

	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonPromoted,
		"event_id":       uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"book_id":        book.String(),
		"from_layer":     "L2_seeded",
		"to_layer":       "L1_axiom",
	})
	if err != nil {
		t.Fatalf("Handle promoted: %v", err)
	}
	writes := db.Writes()
	if len(writes) != 1 {
		t.Fatalf("expected 1 write, got %d", len(writes))
	}
	if writes[0].CanonLayer != "L1_axiom" {
		t.Errorf("canon_layer=%s want L1_axiom (to_layer)", writes[0].CanonLayer)
	}
}

func TestHandle_CanonDecanonized_ArchivedLockLevel(t *testing.T) {
	book := mustUUID(t)
	r1 := mustUUID(t)
	w, db, _ := newTestWriter(t, book, []uuid.UUID{r1})

	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonDecanonized,
		"event_id":       uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"book_id":        book.String(),
	})
	if err != nil {
		t.Fatalf("Handle decanonized: %v", err)
	}
	writes := db.Writes()
	if len(writes) != 1 {
		t.Fatalf("expected 1 write, got %d", len(writes))
	}
	if writes[0].LockLevel != "archived" {
		t.Errorf("lock_level=%s want archived", writes[0].LockLevel)
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Q-L5-3 enum CHECK: only L1_axiom / L2_seeded accepted.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_InvalidCanonLayer_Rejected(t *testing.T) {
	book := mustUUID(t)
	r1 := mustUUID(t)
	w, _, _ := newTestWriter(t, book, []uuid.UUID{r1})

	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonCreated,
		"event_id":       uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"book_id":        book.String(),
		"attribute_path": "p",
		"canon_layer":    "L7_evil",
	})
	if err == nil {
		t.Fatalf("expected error for invalid canon_layer; got nil")
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Cycle 7 L1.J degraded mode: per-reality DB unreachable → NACK.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_PerRealityDB_Failure_NACKs(t *testing.T) {
	book := mustUUID(t)
	r1, r2 := mustUUID(t), mustUUID(t)
	subs := &fakeSubs{subs: map[uuid.UUID][]uuid.UUID{book: {r1, r2}}}
	dbErr := errors.New("connection refused")
	db := &fakeDB{failOn: r1, failErr: dbErr}
	au := &fakeAudit{}
	w, err := New(Config{Subscribers: subs, DB: db, Audit: au, Clock: fixedClock{}})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	herr := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonCreated,
		"event_id":       uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"book_id":        book.String(),
		"attribute_path": "p",
		"canon_layer":    "L1_axiom",
	})
	if herr == nil {
		t.Fatalf("expected error on per-reality DB failure (NACK), got nil")
	}
	// r2 write SHOULD have proceeded (we tolerate per-reality partial fanout;
	// re-delivery via NACK is idempotent on canon_entry_id PK upsert).
	writes := db.Writes()
	if len(writes) != 1 || writes[0].RealityID != r2 {
		t.Errorf("expected exactly r2 write, got %d writes", len(writes))
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Q-L1A-3 full audit V1: audit failure also NACKs.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_AuditFailure_NACKs(t *testing.T) {
	book := mustUUID(t)
	r1 := mustUUID(t)
	subs := &fakeSubs{subs: map[uuid.UUID][]uuid.UUID{book: {r1}}}
	au := &fakeAudit{failErr: errors.New("audit sink down")}
	w, err := New(Config{Subscribers: subs, DB: &fakeDB{}, Audit: au, Clock: fixedClock{}})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	herr := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonCreated,
		"event_id":       uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"book_id":        book.String(),
		"attribute_path": "p",
		"canon_layer":    "L2_seeded",
	})
	if herr == nil {
		t.Fatalf("Q-L1A-3: expected NACK on audit failure; got nil")
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Envelope validation.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_MissingBookID(t *testing.T) {
	w, _, _ := newTestWriter(t, uuid.Nil, nil)
	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonCreated,
		"event_id":       uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"attribute_path": "p",
		"canon_layer":    "L1_axiom",
	})
	if err == nil {
		t.Fatalf("expected error on missing book_id, got nil")
	}
}

func TestHandle_UnsupportedEventType(t *testing.T) {
	w, _, _ := newTestWriter(t, uuid.Nil, nil)
	err := w.Handle(context.Background(), map[string]any{
		"event_type": "canon.entry.wat",
	})
	if err == nil {
		t.Fatalf("expected error for unknown event_type")
	}
}

func TestHandle_NilFields(t *testing.T) {
	w, _, _ := newTestWriter(t, uuid.Nil, nil)
	err := w.Handle(context.Background(), nil)
	if err == nil {
		t.Fatalf("expected error for nil fields")
	}
}

// ─────────────────────────────────────────────────────────────────────────
// EventTypes() coverage — must include all 4 canon.entry.*.
// ─────────────────────────────────────────────────────────────────────────

func TestEventTypes_AllFourCovered(t *testing.T) {
	got := EventTypes()
	want := map[string]bool{
		EventCanonCreated:     false,
		EventCanonUpdated:     false,
		EventCanonPromoted:    false,
		EventCanonDecanonized: false,
	}
	for _, et := range got {
		want[et] = true
	}
	for k, v := range want {
		if !v {
			t.Errorf("EventTypes missing %s", k)
		}
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Idempotency: re-deliver same event → same UPSERT shape (writer is
// stateless; UPSERT in DB layer handles dedup on canon_entry_id PK).
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_RepeatedDelivery_IdempotentShape(t *testing.T) {
	book := mustUUID(t)
	r1 := mustUUID(t)
	w, db, _ := newTestWriter(t, book, []uuid.UUID{r1})

	entry := mustUUID(t)
	evID := mustUUID(t)
	env := map[string]any{
		"event_type":     EventCanonCreated,
		"event_id":       evID.String(),
		"canon_entry_id": entry.String(),
		"book_id":        book.String(),
		"attribute_path": "p",
		"canon_layer":    "L1_axiom",
	}
	for i := 0; i < 3; i++ {
		if err := w.Handle(context.Background(), env); err != nil {
			t.Fatalf("Handle iter %d: %v", i, err)
		}
	}
	writes := db.Writes()
	if len(writes) != 3 {
		t.Fatalf("expected 3 writes (re-delivery), got %d", len(writes))
	}
	// All three writes carry the SAME canon_entry_id → real DB UPSERT
	// collapses to one row. This test guards the WRITER shape only.
	for _, w := range writes {
		if w.CanonEntryID != entry || w.SourceEventID != evID {
			t.Errorf("idempotent shape violated: %+v", w)
		}
	}
}
