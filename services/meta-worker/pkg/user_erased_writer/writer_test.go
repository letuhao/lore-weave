package user_erased_writer

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

type fakeLookup struct {
	byUser map[uuid.UUID][]uuid.UUID
	err    error
}

func (f *fakeLookup) RealitiesForUser(_ context.Context, userID uuid.UUID) ([]uuid.UUID, error) {
	if f.err != nil {
		return nil, f.err
	}
	return append([]uuid.UUID(nil), f.byUser[userID]...), nil
}

type fakeDB struct {
	mu      sync.Mutex
	scrubs  []ScrubIntent
	failOn  uuid.UUID
	failErr error
	// scrubbed = idempotency tracker; second call for same (reality, user)
	// will return nil but record nothing.
	scrubbed map[string]bool
}

func (f *fakeDB) ScrubUserRefs(_ context.Context, in ScrubIntent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failOn != uuid.Nil && in.RealityID == f.failOn {
		return f.failErr
	}
	if f.scrubbed == nil {
		f.scrubbed = map[string]bool{}
	}
	key := in.RealityID.String() + ":" + in.UserID.String()
	if f.scrubbed[key] {
		// idempotent no-op — record nothing
		return nil
	}
	f.scrubbed[key] = true
	f.scrubs = append(f.scrubs, in)
	return nil
}

func (f *fakeDB) Scrubs() []ScrubIntent {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]ScrubIntent, len(f.scrubs))
	copy(out, f.scrubs)
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

func newTestWriter(t *testing.T, user uuid.UUID, realities []uuid.UUID) (*Writer, *fakeDB, *fakeAudit) {
	t.Helper()
	lk := &fakeLookup{byUser: map[uuid.UUID][]uuid.UUID{user: realities}}
	db := &fakeDB{}
	au := &fakeAudit{}
	w, err := New(Config{
		Lookup: lk,
		DB:     db,
		Audit:  au,
		Clock:  fixedClock{t: time.Unix(1700000000, 0).UTC()},
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return w, db, au
}

// ─────────────────────────────────────────────────────────────────────────
// New validation.
// ─────────────────────────────────────────────────────────────────────────

func TestNew_RequiresDeps(t *testing.T) {
	cases := []Config{
		{DB: &fakeDB{}, Audit: &fakeAudit{}},
		{Lookup: &fakeLookup{}, Audit: &fakeAudit{}},
		{Lookup: &fakeLookup{}, DB: &fakeDB{}},
	}
	for i, cfg := range cases {
		if _, err := New(cfg); err == nil {
			t.Errorf("case %d: expected error", i)
		}
	}
}

func TestNew_DefaultClock(t *testing.T) {
	w, err := New(Config{Lookup: &fakeLookup{}, DB: &fakeDB{}, Audit: &fakeAudit{}})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	if w.clock == nil {
		t.Fatalf("default clock not set")
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Happy path: cascade across N realities.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_Cascade_AllRealitiesScrubbed(t *testing.T) {
	user := uuid.New()
	r1, r2, r3 := uuid.New(), uuid.New(), uuid.New()
	w, db, au := newTestWriter(t, user, []uuid.UUID{r1, r2, r3})

	evID := uuid.New()
	erasedAt := time.Unix(1699999000, 0).UTC()
	err := w.Handle(context.Background(), map[string]any{
		"event_type": EventTypeUserErased,
		"event_id":   evID.String(),
		"user_id":    user.String(),
		"erased_at":  erasedAt.Format(time.RFC3339Nano),
		"request_id": "erasure-ticket-42",
	})
	if err != nil {
		t.Fatalf("Handle: %v", err)
	}

	scrubs := db.Scrubs()
	if len(scrubs) != 3 {
		t.Fatalf("expected 3 cascade writes, got %d", len(scrubs))
	}
	seen := map[uuid.UUID]bool{}
	for _, s := range scrubs {
		seen[s.RealityID] = true
		if s.UserID != user || s.EventID != evID {
			t.Errorf("scrub mismatch: %+v", s)
		}
		if s.RequestID != "erasure-ticket-42" {
			t.Errorf("RequestID=%q", s.RequestID)
		}
	}
	if !(seen[r1] && seen[r2] && seen[r3]) {
		t.Errorf("not all realities scrubbed: %v", seen)
	}

	entries := au.Entries()
	if len(entries) != 3 {
		t.Fatalf("Q-L1A-3 full audit: expected 3 entries, got %d", len(entries))
	}
	for _, e := range entries {
		if e.Outcome != "scrubbed" {
			t.Errorf("Outcome=%s", e.Outcome)
		}
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Q-L5H-1 INVERTED: lookup uncertainty → NACK (never silently skip).
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_LookupError_NACKs(t *testing.T) {
	user := uuid.New()
	lk := &fakeLookup{err: errors.New("registry unreachable")}
	w, err := New(Config{Lookup: lk, DB: &fakeDB{}, Audit: &fakeAudit{}, Clock: fixedClock{}})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	herr := w.Handle(context.Background(), map[string]any{
		"event_type": EventTypeUserErased,
		"event_id":   uuid.New().String(),
		"user_id":    user.String(),
		"erased_at":  time.Now().UTC().Format(time.RFC3339Nano),
	})
	if herr == nil {
		t.Fatalf("Q-L5H-1 inverted: lookup error MUST NACK (got nil)")
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Cycle 7 L1.J: per-reality DB unreachable → NACK.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_PerRealityDB_Failure_NACKs(t *testing.T) {
	user := uuid.New()
	r1, r2 := uuid.New(), uuid.New()
	lk := &fakeLookup{byUser: map[uuid.UUID][]uuid.UUID{user: {r1, r2}}}
	db := &fakeDB{failOn: r1, failErr: errors.New("db down")}
	au := &fakeAudit{}
	w, err := New(Config{Lookup: lk, DB: db, Audit: au, Clock: fixedClock{}})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	herr := w.Handle(context.Background(), map[string]any{
		"event_type": EventTypeUserErased,
		"event_id":   uuid.New().String(),
		"user_id":    user.String(),
		"erased_at":  time.Now().UTC().Format(time.RFC3339Nano),
	})
	if herr == nil {
		t.Fatalf("expected NACK on per-reality DB failure (Q-L5H-1 inverted)")
	}
	// r2 still attempted (idempotent on re-delivery).
	scrubs := db.Scrubs()
	if len(scrubs) != 1 || scrubs[0].RealityID != r2 {
		t.Errorf("expected exactly r2 scrub on partial fanout, got %d", len(scrubs))
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Q-L1A-3 full audit: audit failure NACKs.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_AuditFailure_NACKs(t *testing.T) {
	user := uuid.New()
	r1 := uuid.New()
	lk := &fakeLookup{byUser: map[uuid.UUID][]uuid.UUID{user: {r1}}}
	au := &fakeAudit{failErr: errors.New("audit down")}
	w, err := New(Config{Lookup: lk, DB: &fakeDB{}, Audit: au, Clock: fixedClock{}})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	herr := w.Handle(context.Background(), map[string]any{
		"event_type": EventTypeUserErased,
		"event_id":   uuid.New().String(),
		"user_id":    user.String(),
		"erased_at":  time.Now().UTC().Format(time.RFC3339Nano),
	})
	if herr == nil {
		t.Fatalf("audit failure MUST NACK (Q-L1A-3 = no sampling)")
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Idempotency: re-delivery against already-scrubbed realities is safe.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_RedeliveryIdempotent(t *testing.T) {
	user := uuid.New()
	r1, r2 := uuid.New(), uuid.New()
	w, db, au := newTestWriter(t, user, []uuid.UUID{r1, r2})

	env := map[string]any{
		"event_type": EventTypeUserErased,
		"event_id":   uuid.New().String(),
		"user_id":    user.String(),
		"erased_at":  time.Now().UTC().Format(time.RFC3339Nano),
	}
	for i := 0; i < 3; i++ {
		if err := w.Handle(context.Background(), env); err != nil {
			t.Fatalf("Handle iter %d: %v", i, err)
		}
	}
	// fakeDB dedup: only 2 scrubs recorded across 3 deliveries.
	if got := len(db.Scrubs()); got != 2 {
		t.Errorf("expected 2 effective scrubs (idempotent), got %d", got)
	}
	// Audit captures every attempt (writer-level), which is fine — audit
	// trail SHOULD record all attempts. fakeDB only records new scrubs;
	// audit fires on each successful (writer-call) ScrubUserRefs return
	// nil — so audit count is 2 (first delivery hits both, subsequent
	// re-deliveries hit ScrubUserRefs which returns nil but skips
	// recording → audit fires on every success).
	// 6 audit entries = 2 scrubs × 3 deliveries (each success audits).
	if got := len(au.Entries()); got != 6 {
		t.Errorf("expected 6 audit entries across 3 idempotent deliveries, got %d", got)
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Envelope validation.
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_MissingUserID(t *testing.T) {
	w, _, _ := newTestWriter(t, uuid.Nil, nil)
	err := w.Handle(context.Background(), map[string]any{
		"event_type": EventTypeUserErased,
		"event_id":   uuid.New().String(),
	})
	if err == nil {
		t.Fatalf("expected error on missing user_id")
	}
}

func TestHandle_NilFields(t *testing.T) {
	w, _, _ := newTestWriter(t, uuid.Nil, nil)
	if err := w.Handle(context.Background(), nil); err == nil {
		t.Fatalf("expected error on nil fields")
	}
}

func TestEventTypes_OneEntry(t *testing.T) {
	got := EventTypes()
	if len(got) != 1 || got[0] != EventTypeUserErased {
		t.Errorf("EventTypes=%v want [%s]", got, EventTypeUserErased)
	}
}

// ─────────────────────────────────────────────────────────────────────────
// No realities scope: zero-fanout is a clean no-op (lookup returned [],
// not an error — user existed in no per-reality scope).
// ─────────────────────────────────────────────────────────────────────────

func TestHandle_NoRealities_NoOp(t *testing.T) {
	user := uuid.New()
	w, db, au := newTestWriter(t, user, []uuid.UUID{})
	err := w.Handle(context.Background(), map[string]any{
		"event_type": EventTypeUserErased,
		"event_id":   uuid.New().String(),
		"user_id":    user.String(),
		"erased_at":  time.Now().UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("Handle: %v", err)
	}
	if len(db.Scrubs()) != 0 {
		t.Errorf("expected 0 scrubs, got %d", len(db.Scrubs()))
	}
	if len(au.Entries()) != 0 {
		t.Errorf("expected 0 audit entries, got %d", len(au.Entries()))
	}
}
