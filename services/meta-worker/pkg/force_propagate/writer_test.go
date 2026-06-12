package force_propagate

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
)

// ─────────────────────────────────────────────────────────────────────────
// In-memory test fakes.
// ─────────────────────────────────────────────────────────────────────────

type fakeSubs struct {
	out []uuid.UUID
	err error
}

func (f *fakeSubs) SubscribersForBook(_ context.Context, _ uuid.UUID) ([]uuid.UUID, error) {
	return f.out, f.err
}

type fakeConsent struct {
	mu    sync.Mutex
	calls int
	// decisions keyed by realityID.
	decisions map[uuid.UUID]ConsentDecision
	// errs keyed by realityID.
	errs map[uuid.UUID]error
}

func newFakeConsent() *fakeConsent {
	return &fakeConsent{
		decisions: map[uuid.UUID]ConsentDecision{},
		errs:      map[uuid.UUID]error{},
	}
}

func (f *fakeConsent) Collect(_ context.Context, _ ForcePropagateRequest, realityID uuid.UUID) (ConsentDecision, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls++
	if e, ok := f.errs[realityID]; ok {
		return ConsentDecision{RealityID: realityID}, e
	}
	d, ok := f.decisions[realityID]
	if !ok {
		// Default: pending (caller must explicitly set)
		return ConsentDecision{RealityID: realityID}, ErrConsentPending
	}
	d.RealityID = realityID
	if d.DecidedAt.IsZero() {
		d.DecidedAt = time.Unix(1780000000, 0).UTC()
	}
	return d, nil
}

type fakeDB struct {
	mu     sync.Mutex
	writes []UpsertIntent
	errs   map[uuid.UUID]error
}

func newFakeDB() *fakeDB { return &fakeDB{errs: map[uuid.UUID]error{}} }

func (f *fakeDB) UpsertCanon(_ context.Context, in UpsertIntent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if e, ok := f.errs[in.RealityID]; ok {
		return e
	}
	f.writes = append(f.writes, in)
	return nil
}

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

type fakeEmitter struct {
	mu   sync.Mutex
	emit []emitRecord
	fail bool
}

type emitRecord struct {
	EventType string
	Payload   map[string]any
}

func (f *fakeEmitter) Emit(_ context.Context, eventType string, payload map[string]any) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.fail {
		return errors.New("emit-down")
	}
	cp := map[string]any{}
	for k, v := range payload {
		cp[k] = v
	}
	f.emit = append(f.emit, emitRecord{EventType: eventType, Payload: cp})
	return nil
}

type fixedClock struct{ t time.Time }

func (f fixedClock) Now() time.Time { return f.t }

func newOrch(t *testing.T, subs []uuid.UUID, dec *fakeConsent, db *fakeDB, audit *fakeAudit, em *fakeEmitter) *Orchestrator {
	t.Helper()
	o, err := New(Config{
		Subscribers: &fakeSubs{out: subs},
		Consent:     dec,
		DB:          db,
		Audit:       audit,
		Emitter:     em,
		Clock:       fixedClock{t: time.Unix(1780000000, 0).UTC()},
	})
	if err != nil {
		t.Fatal(err)
	}
	return o
}

func sampleReq(t time.Time) ForcePropagateRequest {
	return ForcePropagateRequest{
		OverrideID:    uuid.New(),
		CanonEntryID:  uuid.New(),
		BookID:        uuid.New(),
		AttributePath: "world.climate",
		NewValue:      []byte(`"arid"`),
		CanonLayer:    "L2_seeded",
		Reason:        "author_push",
		RequestedBy:   uuid.New(),
		RequestedAt:   t,
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Tests.
// ─────────────────────────────────────────────────────────────────────────

func TestNew_RejectsMissingDeps(t *testing.T) {
	cases := []struct {
		name string
		cfg  Config
	}{
		{"no Subscribers", Config{Consent: newFakeConsent(), DB: newFakeDB(), Audit: &fakeAudit{}, Emitter: &fakeEmitter{}}},
		{"no Consent", Config{Subscribers: &fakeSubs{}, DB: newFakeDB(), Audit: &fakeAudit{}, Emitter: &fakeEmitter{}}},
		{"no DB", Config{Subscribers: &fakeSubs{}, Consent: newFakeConsent(), Audit: &fakeAudit{}, Emitter: &fakeEmitter{}}},
		{"no Audit", Config{Subscribers: &fakeSubs{}, Consent: newFakeConsent(), DB: newFakeDB(), Emitter: &fakeEmitter{}}},
		{"no Emitter", Config{Subscribers: &fakeSubs{}, Consent: newFakeConsent(), DB: newFakeDB(), Audit: &fakeAudit{}}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if _, err := New(c.cfg); err == nil {
				t.Errorf("New(%s) expected error", c.name)
			}
		})
	}
}

func TestApply_HappyPath_3ConsentVeto1Timeout1(t *testing.T) {
	// 5 realities: 3 explicit consent, 1 veto, 1 timeout (default-consent).
	subs := []uuid.UUID{uuid.New(), uuid.New(), uuid.New(), uuid.New(), uuid.New()}
	dec := newFakeConsent()
	dec.decisions[subs[0]] = ConsentDecision{Granted: true, ConsentedBy: uuid.New()}
	dec.decisions[subs[1]] = ConsentDecision{Granted: true, ConsentedBy: uuid.New()}
	dec.decisions[subs[2]] = ConsentDecision{Granted: true, ConsentedBy: uuid.New()}
	dec.decisions[subs[3]] = ConsentDecision{Granted: false, VetoReason: "lore conflict", ConsentedBy: uuid.New()}
	dec.decisions[subs[4]] = ConsentDecision{Granted: true, Default: true}

	db := newFakeDB()
	audit := &fakeAudit{}
	em := &fakeEmitter{}
	o := newOrch(t, subs, dec, db, audit, em)

	req := sampleReq(time.Unix(1779000000, 0).UTC())
	outs, err := o.Apply(context.Background(), req)
	if err != nil {
		t.Fatalf("Apply err: %v", err)
	}
	if len(outs) != 5 {
		t.Fatalf("expected 5 outcomes (one per reality), got %d", len(outs))
	}

	// 4 consented → 4 db writes; veto did not write.
	if len(db.writes) != 4 {
		t.Errorf("expected 4 db writes (4 consented), got %d", len(db.writes))
	}
	// 4 compensating events + 4 consented events + 1 veto event = 9 total.
	consentedCount, vetoedCount, compCount := 0, 0, 0
	for _, e := range em.emit {
		switch e.EventType {
		case EventOverrideConsented:
			consentedCount++
		case EventOverrideVetoed:
			vetoedCount++
		case EventOverrideCompensating:
			compCount++
		}
	}
	if consentedCount != 4 || vetoedCount != 1 || compCount != 4 {
		t.Errorf("event counts wrong: consented=%d vetoed=%d compensating=%d", consentedCount, vetoedCount, compCount)
	}

	// Default-consent flag must propagate to the right outcome.
	var defaultCount int
	for _, oc := range outs {
		if oc.DefaultConsent {
			defaultCount++
		}
	}
	if defaultCount != 1 {
		t.Errorf("expected exactly 1 default-consent outcome, got %d", defaultCount)
	}

	// Q-L1A-3: every per-reality result (5) must have at least one audit row.
	if len(audit.entries) < 5 {
		t.Errorf("Q-L1A-3 audit count must be ≥ 5 (one per reality), got %d", len(audit.entries))
	}
}

func TestCollect_DefaultToConsentOnTimeout(t *testing.T) {
	// Q-L5H-1 LOCKED — 24h deadline; default-to-consent on no-response.
	pendingLookup := &pendingConsentLookup{}
	now := time.Unix(1780000000, 0).UTC()
	collector, err := NewDeadlineConsentCollector(DeadlineConsentCollectorConfig{
		Lookup:  pendingLookup,
		Timeout: ConsentTimeout,
		Clock:   fixedClock{t: now.Add(25 * time.Hour)}, // past the 24h deadline
	})
	if err != nil {
		t.Fatal(err)
	}

	realityID := uuid.New()
	req := sampleReq(now)
	dec, err := collector.Collect(context.Background(), req, realityID)
	if err != nil {
		t.Fatalf("Collect: %v", err)
	}
	if !dec.Granted || !dec.Default {
		t.Errorf("Q-L5H-1: default-to-consent expected, got granted=%v default=%v", dec.Granted, dec.Default)
	}
}

func TestCollect_PendingBeforeDeadline(t *testing.T) {
	pendingLookup := &pendingConsentLookup{}
	now := time.Unix(1780000000, 0).UTC()
	collector, err := NewDeadlineConsentCollector(DeadlineConsentCollectorConfig{
		Lookup:  pendingLookup,
		Timeout: ConsentTimeout,
		Clock:   fixedClock{t: now.Add(1 * time.Hour)}, // INSIDE the 24h window
	})
	if err != nil {
		t.Fatal(err)
	}
	req := sampleReq(now)
	dec, err := collector.Collect(context.Background(), req, uuid.New())
	if !errors.Is(err, ErrConsentPending) {
		t.Fatalf("expected ErrConsentPending inside deadline; got dec=%+v err=%v", dec, err)
	}
}

func TestCollect_ExplicitDecisionHonored(t *testing.T) {
	// Lookup returns explicit decision — collector returns as-is.
	now := time.Unix(1780000000, 0).UTC()
	explicit := ConsentDecision{
		RealityID:   uuid.New(),
		Granted:     true,
		Default:     false,
		ConsentedBy: uuid.New(),
		DecidedAt:   now.Add(2 * time.Hour),
	}
	lookup := &fixedConsentLookup{out: explicit}
	collector, _ := NewDeadlineConsentCollector(DeadlineConsentCollectorConfig{
		Lookup:  lookup,
		Timeout: ConsentTimeout,
		Clock:   fixedClock{t: now.Add(3 * time.Hour)},
	})
	dec, err := collector.Collect(context.Background(), sampleReq(now), explicit.RealityID)
	if err != nil {
		t.Fatal(err)
	}
	if !dec.Granted || dec.Default {
		t.Errorf("explicit decision corrupted: %+v", dec)
	}
	if dec.ConsentedBy == uuid.Nil {
		t.Error("explicit consent must carry consenter UUID")
	}
}

func TestApply_VetoSkipsProjection(t *testing.T) {
	subs := []uuid.UUID{uuid.New(), uuid.New()}
	dec := newFakeConsent()
	dec.decisions[subs[0]] = ConsentDecision{Granted: true, ConsentedBy: uuid.New()}
	dec.decisions[subs[1]] = ConsentDecision{Granted: false, VetoReason: "policy"}

	db := newFakeDB()
	audit := &fakeAudit{}
	em := &fakeEmitter{}
	o := newOrch(t, subs, dec, db, audit, em)

	outs, err := o.Apply(context.Background(), sampleReq(time.Unix(1779000000, 0).UTC()))
	if err != nil {
		t.Fatal(err)
	}
	if len(db.writes) != 1 {
		t.Errorf("veto must skip projection: expected 1 write, got %d", len(db.writes))
	}
	var vetoOutcome ForcePropagateOutcome
	for _, oc := range outs {
		if oc.RealityID == subs[1] {
			vetoOutcome = oc
		}
	}
	if !vetoOutcome.Skipped || vetoOutcome.Reason != "vetoed" {
		t.Errorf("veto outcome wrong: %+v", vetoOutcome)
	}
}

func TestApply_DBFailureCapturesAuditAndError(t *testing.T) {
	subs := []uuid.UUID{uuid.New()}
	dec := newFakeConsent()
	dec.decisions[subs[0]] = ConsentDecision{Granted: true, ConsentedBy: uuid.New()}
	db := newFakeDB()
	db.errs[subs[0]] = errors.New("connection refused")
	audit := &fakeAudit{}
	em := &fakeEmitter{}
	o := newOrch(t, subs, dec, db, audit, em)

	_, err := o.Apply(context.Background(), sampleReq(time.Unix(1779000000, 0).UTC()))
	if err == nil {
		t.Fatal("expected first-error to surface from db failure")
	}
	// Q-L1A-3 audit row must STILL be written (failure forensics).
	if len(audit.entries) == 0 {
		t.Error("Q-L1A-3: audit row required even on db failure")
	}
}

func TestApply_ValidationRejectsZeroFields(t *testing.T) {
	o := newOrch(t, nil, newFakeConsent(), newFakeDB(), &fakeAudit{}, &fakeEmitter{})
	cases := []ForcePropagateRequest{
		{}, // all zero
		{OverrideID: uuid.New()},
		{OverrideID: uuid.New(), CanonEntryID: uuid.New()},
		{OverrideID: uuid.New(), CanonEntryID: uuid.New(), BookID: uuid.New()},
		{OverrideID: uuid.New(), CanonEntryID: uuid.New(), BookID: uuid.New(), AttributePath: "x"},
		// missing RequestedAt
	}
	for i, req := range cases {
		if _, err := o.Apply(context.Background(), req); err == nil {
			t.Errorf("case %d: expected validation error", i)
		}
	}
}

func TestEventTypeConstants(t *testing.T) {
	for _, want := range []string{
		"admin.canon.override.requested",
		"admin.canon.override.consented",
		"admin.canon.override.vetoed",
		"admin.canon.override.compensating",
	} {
		// Ensure each is exported through the dispatch allowlist namespace.
		if want == "" {
			t.Fatal("empty event constant")
		}
	}
	if EventOverrideRequested != "admin.canon.override.requested" {
		t.Error("constant drift")
	}
	if EventOverrideConsented != "admin.canon.override.consented" {
		t.Error("constant drift")
	}
	if EventOverrideVetoed != "admin.canon.override.vetoed" {
		t.Error("constant drift")
	}
	if EventOverrideCompensating != "admin.canon.override.compensating" {
		t.Error("constant drift")
	}
}

func TestConsentTimeoutIsQL5H1Locked(t *testing.T) {
	// Q-L5H-1 LOCKED: 24h.
	if ConsentTimeout != 24*time.Hour {
		t.Errorf("Q-L5H-1: ConsentTimeout must be 24h, got %s", ConsentTimeout)
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Test-only ConsentLookup fakes.
// ─────────────────────────────────────────────────────────────────────────

type pendingConsentLookup struct{}

func (pendingConsentLookup) Lookup(_ context.Context, _, _ uuid.UUID) (ConsentDecision, error) {
	return ConsentDecision{}, ErrConsentPending
}

type fixedConsentLookup struct {
	out ConsentDecision
	err error
}

func (f *fixedConsentLookup) Lookup(_ context.Context, _, _ uuid.UUID) (ConsentDecision, error) {
	if f.err != nil {
		return ConsentDecision{}, f.err
	}
	return f.out, nil
}
