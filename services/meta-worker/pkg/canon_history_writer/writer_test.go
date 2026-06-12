package canon_history_writer

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/foundation/contracts/canon/timeline"
)

type fakeAudit struct {
	mu      sync.Mutex
	entries []AuditEntry
	fail    bool
}

func (f *fakeAudit) WriteAudit(_ context.Context, e AuditEntry) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.fail {
		return errors.New("audit-down")
	}
	f.entries = append(f.entries, e)
	return nil
}

type fixedClock struct{ t time.Time }

func (f fixedClock) Now() time.Time { return f.t }

func newWriter(t *testing.T, store timeline.TimelineAppender, audit AuditSink) *Writer {
	t.Helper()
	w, err := New(Config{Store: store, Audit: audit, Clock: fixedClock{t: time.Unix(1780000000, 0).UTC()}})
	if err != nil {
		t.Fatal(err)
	}
	return w
}

func TestNew_RejectsMissingDeps(t *testing.T) {
	if _, err := New(Config{Audit: &fakeAudit{}}); err == nil {
		t.Error("missing Store accepted")
	}
	if _, err := New(Config{Store: timeline.NewInMemoryStore()}); err == nil {
		t.Error("missing Audit accepted")
	}
}

func TestHandle_AppendsCanonCreated(t *testing.T) {
	store := timeline.NewInMemoryStore()
	audit := &fakeAudit{}
	w := newWriter(t, store, audit)

	bookID := uuid.New()
	entryID := uuid.New()
	if err := w.Handle(context.Background(), map[string]any{
		"event_type":      EventCanonCreated,
		"event_id":        uuid.New().String(),
		"book_id":         bookID.String(),
		"canon_entry_id":  entryID.String(),
		"attribute_path":  "world.climate",
		"canon_layer":     "L2_seeded",
		"value":           "\"arid\"",
	}); err != nil {
		t.Fatal(err)
	}
	if store.Count() != 1 {
		t.Errorf("expected 1 entry stored, got %d", store.Count())
	}
	if len(audit.entries) != 1 {
		t.Errorf("Q-L1A-3: expected 1 audit row, got %d", len(audit.entries))
	}
}

func TestHandle_KindForcePropagateOnCompensating(t *testing.T) {
	store := timeline.NewInMemoryStore()
	w := newWriter(t, store, &fakeAudit{})

	realityID := uuid.New()
	bookID := uuid.New()
	entryID := uuid.New()
	if err := w.Handle(context.Background(), map[string]any{
		"event_type":      EventOverrideCompensating,
		"event_id":        uuid.New().String(),
		"book_id":         bookID.String(),
		"canon_entry_id":  entryID.String(),
		"reality_id":      realityID.String(),
		"attribute_path":  "world.climate",
		"canon_layer":     "L2_seeded",
		"new_value":       "\"arid\"",
		"old_value":       "\"temperate\"",
		"default_consent": false,
	}); err != nil {
		t.Fatal(err)
	}
	// Query the entry to verify kind/reality fields.
	rows, _ := store.Query(context.Background(), timeline.Query{CanonEntryID: entryID})
	if len(rows) != 1 {
		t.Fatalf("expected 1 row, got %d", len(rows))
	}
	if rows[0].Kind != timeline.CanonChangeKindForcePropagate {
		t.Errorf("compensating event kind wrong: %s", rows[0].Kind)
	}
	if rows[0].RealityID != realityID {
		t.Errorf("compensating event reality_id wrong: %s vs %s", rows[0].RealityID, realityID)
	}
}

func TestHandle_AppendsForCanonPromoted(t *testing.T) {
	store := timeline.NewInMemoryStore()
	w := newWriter(t, store, &fakeAudit{})
	if err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonPromoted,
		"event_id":       uuid.New().String(),
		"book_id":        uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"attribute_path": "world.climate",
		"to_layer":       "L1_axiom",
	}); err != nil {
		t.Fatal(err)
	}
	if store.Count() != 1 {
		t.Error("expected 1 entry")
	}
}

func TestHandle_AuditFailureBubblesUp(t *testing.T) {
	store := timeline.NewInMemoryStore()
	audit := &fakeAudit{fail: true}
	w := newWriter(t, store, audit)
	err := w.Handle(context.Background(), map[string]any{
		"event_type":     EventCanonUpdated,
		"event_id":       uuid.New().String(),
		"book_id":        uuid.New().String(),
		"canon_entry_id": uuid.New().String(),
		"attribute_path": "x",
		"canon_layer":    "L2_seeded",
		"new_value":      "\"v\"",
	})
	if err == nil {
		t.Error("audit failure must surface (Q-L1A-3 NACK)")
	}
}

func TestHandle_RejectsUnsupportedEventType(t *testing.T) {
	w := newWriter(t, timeline.NewInMemoryStore(), &fakeAudit{})
	err := w.Handle(context.Background(), map[string]any{"event_type": "reality.created"})
	if err == nil {
		t.Error("unsupported event_type must reject")
	}
}

func TestEventTypesIncludesAll5(t *testing.T) {
	types := EventTypes()
	if len(types) != 5 {
		t.Fatalf("expected 5 event types, got %d", len(types))
	}
	// Ensure compensating is in there.
	found := false
	for _, t := range types {
		if t == EventOverrideCompensating {
			found = true
		}
	}
	if !found {
		t.Error("EventTypes must include compensating event")
	}
}

func TestDispatchAllowlistCovered(t *testing.T) {
	// Cycle 27 dispatch allowlist permits admin.canon.override.* — verify
	// our compensating constant matches the allowlist prefix exactly.
	if !startsWith(EventOverrideCompensating, "admin.canon.override.") {
		t.Errorf("compensating event_type %q does not match dispatch allowlist prefix", EventOverrideCompensating)
	}
}

func startsWith(s, prefix string) bool {
	return len(s) >= len(prefix) && s[:len(prefix)] == prefix
}
