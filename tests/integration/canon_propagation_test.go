// canon_propagation_test.go — L5.B + L5.C (RAID cycle 24).
//
// Integration test for the cycle-24 meta-worker canon + user-erased
// consumers wired through the cycle-10 dispatcher.
//
// What this test exercises:
//  1. canon.entry.* event arrives at the meta-worker dispatcher.
//  2. canon_writer.Writer fans out the projection write to ALL subscribed
//     reality_ids and audits each via the AuditSink.
//  3. xreality.user.erased event arrives at the meta-worker dispatcher.
//  4. user_erased_writer.Writer cascades the scrub across all realities
//     where the user has refs, audits each, and re-delivery is idempotent.
//  5. I7 invariant: dispatch.ValidateAllowlist passes with the new
//     registrations.
//
// The test uses the cycle-10 in-process consumer pattern + fake
// MessageSource (no real Redis) so it runs without docker-compose.
//
// Per CLAUDE.md cross-service-live-smoke discipline: this test exercises
// meta-worker dispatch + canon_writer + user_erased_writer + (transitively)
// the projection write contract. The DB layer is faked (no per-reality
// Postgres at unit-test time); a live smoke against a stack-up is deferred
// to cycle 25+ when L5.B + L5.C are wired into the meta-worker main.go.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/meta-worker/pkg/canon_writer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/consumer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
	"github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer"
)

// ─────────────────────────────────────────────────────────────────────────
// Fake MessageSource for consumer drive (cycle-10 pattern).
// ─────────────────────────────────────────────────────────────────────────

type fakeSource struct {
	mu       sync.Mutex
	messages []consumer.Message
	acked    []consumer.Message
}

func (s *fakeSource) push(m consumer.Message) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.messages = append(s.messages, m)
}

func (s *fakeSource) Read(_ context.Context, batchSize int) ([]consumer.Message, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.messages) == 0 {
		return nil, nil
	}
	n := len(s.messages)
	if n > batchSize {
		n = batchSize
	}
	out := append([]consumer.Message(nil), s.messages[:n]...)
	s.messages = s.messages[n:]
	return out, nil
}

func (s *fakeSource) Ack(_ context.Context, m consumer.Message) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.acked = append(s.acked, m)
	return nil
}

func (s *fakeSource) Acked() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.acked)
}

// ─────────────────────────────────────────────────────────────────────────
// Fake canon_writer dependencies.
// ─────────────────────────────────────────────────────────────────────────

type cwFakeSubs struct {
	subs map[uuid.UUID][]uuid.UUID
}

func (f *cwFakeSubs) SubscribersForBook(_ context.Context, bookID uuid.UUID) ([]uuid.UUID, error) {
	return append([]uuid.UUID(nil), f.subs[bookID]...), nil
}

type cwFakeDB struct {
	mu     sync.Mutex
	writes []canon_writer.UpsertIntent
}

func (f *cwFakeDB) UpsertCanon(_ context.Context, in canon_writer.UpsertIntent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.writes = append(f.writes, in)
	return nil
}

func (f *cwFakeDB) Writes() []canon_writer.UpsertIntent {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]canon_writer.UpsertIntent, len(f.writes))
	copy(out, f.writes)
	return out
}

type cwFakeAudit struct {
	mu      sync.Mutex
	entries []canon_writer.AuditEntry
}

func (f *cwFakeAudit) WriteAudit(_ context.Context, e canon_writer.AuditEntry) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.entries = append(f.entries, e)
	return nil
}

func (f *cwFakeAudit) Count() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.entries)
}

// ─────────────────────────────────────────────────────────────────────────
// Fake user_erased_writer dependencies.
// ─────────────────────────────────────────────────────────────────────────

type ueFakeLookup struct {
	byUser map[uuid.UUID][]uuid.UUID
}

func (f *ueFakeLookup) RealitiesForUser(_ context.Context, userID uuid.UUID) ([]uuid.UUID, error) {
	return append([]uuid.UUID(nil), f.byUser[userID]...), nil
}

type ueFakeDB struct {
	mu     sync.Mutex
	scrubs []user_erased_writer.ScrubIntent
}

func (f *ueFakeDB) ScrubUserRefs(_ context.Context, in user_erased_writer.ScrubIntent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.scrubs = append(f.scrubs, in)
	return nil
}

func (f *ueFakeDB) Scrubs() []user_erased_writer.ScrubIntent {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]user_erased_writer.ScrubIntent, len(f.scrubs))
	copy(out, f.scrubs)
	return out
}

type ueFakeAudit struct {
	mu      sync.Mutex
	entries []user_erased_writer.AuditEntry
}

func (f *ueFakeAudit) WriteAudit(_ context.Context, e user_erased_writer.AuditEntry) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.entries = append(f.entries, e)
	return nil
}

func (f *ueFakeAudit) Count() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.entries)
}

// ─────────────────────────────────────────────────────────────────────────
// Test 1: L5.B canon.entry.created event flows publisher → dispatcher →
// canon_writer → per-reality projection write.
// ─────────────────────────────────────────────────────────────────────────

func TestCanonPropagation_CycleC24_CanonCreatedFanOut(t *testing.T) {
	book := uuid.New()
	r1, r2, r3 := uuid.New(), uuid.New(), uuid.New()

	subs := &cwFakeSubs{subs: map[uuid.UUID][]uuid.UUID{book: {r1, r2, r3}}}
	db := &cwFakeDB{}
	au := &cwFakeAudit{}
	cw, err := canon_writer.New(canon_writer.Config{
		Subscribers: subs,
		DB:          db,
		Audit:       au,
	})
	if err != nil {
		t.Fatalf("canon_writer.New: %v", err)
	}

	// Dispatcher wired with canon_writer handlers (REPLACES skeletons).
	d := dispatch.New()
	for _, et := range canon_writer.EventTypes() {
		d.Register(et, cw.Handle)
	}
	// Also register user_erased to keep allowlist valid; we won't drive
	// it in this test.
	d.Register(user_erased_writer.EventTypeUserErased, func(_ context.Context, _ map[string]any) error { return nil })
	if err := d.ValidateAllowlist(); err != nil {
		t.Fatalf("I7 ALLOWLIST violated: %v", err)
	}

	// Drive one canon.entry.created event through the consumer.
	src := &fakeSource{}
	src.push(consumer.Message{
		Stream: "xreality.book.canon.updated",
		ID:     "1700000000000-0",
		Fields: map[string]any{
			"event_type":     canon_writer.EventCanonCreated,
			"event_id":       uuid.New().String(),
			"canon_entry_id": uuid.New().String(),
			"book_id":        book.String(),
			"attribute_path": "characters/alice/race",
			"canon_layer":    "L2_seeded",
			"value":          `{"race":"elf"}`,
		},
	})
	c, err := consumer.New(src, d)
	if err != nil {
		t.Fatalf("consumer.New: %v", err)
	}
	stats, err := c.ProcessOne(context.Background(), 10)
	if err != nil {
		t.Fatalf("ProcessOne: %v", err)
	}
	if stats.Dispatched != 1 {
		t.Fatalf("dispatched=%d want 1; stats=%+v", stats.Dispatched, stats)
	}
	if stats.HandlerErr != 0 {
		t.Fatalf("HandlerErr=%d want 0", stats.HandlerErr)
	}
	if src.Acked() != 1 {
		t.Fatalf("acked=%d want 1", src.Acked())
	}

	writes := db.Writes()
	if len(writes) != 3 {
		t.Fatalf("expected 3 fan-out projection writes, got %d", len(writes))
	}
	seen := map[uuid.UUID]bool{}
	for _, w := range writes {
		seen[w.RealityID] = true
		if w.CanonLayer != "L2_seeded" {
			t.Errorf("canon_layer=%s", w.CanonLayer)
		}
	}
	if !(seen[r1] && seen[r2] && seen[r3]) {
		t.Errorf("fan-out incomplete: %v", seen)
	}

	if au.Count() != 3 {
		t.Errorf("Q-L1A-3 full audit: expected 3 entries, got %d", au.Count())
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Test 2: L5.C xreality.user.erased cascades across N realities;
// idempotent on re-delivery.
// ─────────────────────────────────────────────────────────────────────────

func TestCanonPropagation_CycleC24_UserErasedCascade(t *testing.T) {
	user := uuid.New()
	rA, rB := uuid.New(), uuid.New()

	lk := &ueFakeLookup{byUser: map[uuid.UUID][]uuid.UUID{user: {rA, rB}}}
	db := &ueFakeDB{}
	au := &ueFakeAudit{}
	uw, err := user_erased_writer.New(user_erased_writer.Config{
		Lookup: lk,
		DB:     db,
		Audit:  au,
	})
	if err != nil {
		t.Fatalf("user_erased_writer.New: %v", err)
	}

	d := dispatch.New()
	// Register canon types as no-ops so allowlist is full.
	for _, et := range canon_writer.EventTypes() {
		d.Register(et, func(_ context.Context, _ map[string]any) error { return nil })
	}
	d.Register(user_erased_writer.EventTypeUserErased, uw.Handle)
	if err := d.ValidateAllowlist(); err != nil {
		t.Fatalf("I7 ALLOWLIST violated: %v", err)
	}

	src := &fakeSource{}
	// Push the SAME message THREE times (simulating Redis re-delivery).
	evID := uuid.New().String()
	env := map[string]any{
		"event_type": user_erased_writer.EventTypeUserErased,
		"event_id":   evID,
		"user_id":    user.String(),
		"erased_at":  time.Unix(1700000000, 0).UTC().Format(time.RFC3339Nano),
		"request_id": "ticket-7",
	}
	for i := 0; i < 3; i++ {
		src.push(consumer.Message{
			Stream: "xreality.user.erased",
			ID:     "1700000000000-" + string(rune('0'+i)),
			Fields: env,
		})
	}
	c, err := consumer.New(src, d)
	if err != nil {
		t.Fatalf("consumer.New: %v", err)
	}
	for i := 0; i < 3; i++ {
		if _, err := c.ProcessOne(context.Background(), 10); err != nil {
			t.Fatalf("ProcessOne %d: %v", i, err)
		}
	}

	// Writer-level scrub calls = 3 deliveries × 2 realities = 6
	// (DB layer is responsible for idempotency on canon side; fakeDB
	// here is non-dedup so we observe writer call shape).
	scrubs := db.Scrubs()
	if len(scrubs) != 6 {
		t.Errorf("expected 6 scrub calls (3 deliveries × 2 realities), got %d", len(scrubs))
	}
	// Every scrub MUST carry the SAME UserID + EventID (idempotent shape).
	for _, s := range scrubs {
		if s.UserID != user {
			t.Errorf("UserID mismatch: %s vs %s", s.UserID, user)
		}
	}
	if au.Count() != 6 {
		t.Errorf("Q-L1A-3 full audit: expected 6 entries, got %d", au.Count())
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Test 3: I7 invariant — cycle 24 extended dispatcher allowlist permits
// canon.entry.* (the inner event_type for canon fanout) AND xreality.*
// (original cycle-10 cross-reality events). Allowlist MUST reject
// arbitrary other types (e.g., "book.created", "reality.created").
// ─────────────────────────────────────────────────────────────────────────

func TestCanonPropagation_CycleC24_DispatcherAllowlist(t *testing.T) {
	// Positive case: canon.entry.* + xreality.* allowed.
	d := dispatch.New()
	for _, et := range canon_writer.EventTypes() {
		d.Register(et, func(_ context.Context, _ map[string]any) error { return nil })
	}
	d.Register(user_erased_writer.EventTypeUserErased, func(_ context.Context, _ map[string]any) error { return nil })
	if err := d.ValidateAllowlist(); err != nil {
		t.Fatalf("expected canon.entry.* + xreality.user.erased to be allowlisted; got %v", err)
	}

	// Negative case: a forbidden prefix (e.g., reality.created — NOT
	// xreality.*) MUST fail. Defense against accidental cross-tenant
	// handler registration.
	dBad := dispatch.New()
	dBad.Register("reality.created", func(_ context.Context, _ map[string]any) error { return nil })
	if err := dBad.ValidateAllowlist(); err == nil {
		t.Fatalf("expected I7 violation for non-allowlisted event_type, got nil")
	}
}
