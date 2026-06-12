package integration

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/foundation/contracts/canon/timeline"
	"github.com/loreweave/foundation/services/meta-worker/pkg/canon_history_writer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/force_propagate"
	"github.com/loreweave/foundation/services/meta-worker/pkg/l1_conflict_detector"
	"github.com/loreweave/foundation/services/meta-worker/pkg/l1_conflict_reporter"
)

// Cycle 27 integration test — end-to-end exercise of L5.H + L5.I + L5.J.

// ─── Fakes ──────────────────────────────────────────────────────────────

type fakeSubsForce struct{ out []uuid.UUID }

func (f *fakeSubsForce) SubscribersForBook(_ context.Context, _ uuid.UUID) ([]uuid.UUID, error) {
	return f.out, nil
}

type fakeConsentMap struct {
	decisions map[uuid.UUID]force_propagate.ConsentDecision
}

func (f *fakeConsentMap) Collect(_ context.Context, _ force_propagate.ForcePropagateRequest, realityID uuid.UUID) (force_propagate.ConsentDecision, error) {
	d, ok := f.decisions[realityID]
	if !ok {
		return force_propagate.ConsentDecision{RealityID: realityID}, force_propagate.ErrConsentPending
	}
	d.RealityID = realityID
	if d.DecidedAt.IsZero() {
		d.DecidedAt = time.Unix(1780000000, 0).UTC()
	}
	return d, nil
}

type fakeDB struct{ writes []force_propagate.UpsertIntent }

func (f *fakeDB) UpsertCanon(_ context.Context, in force_propagate.UpsertIntent) error {
	f.writes = append(f.writes, in)
	return nil
}

type fakeFPAudit struct{ entries []force_propagate.AuditEntry }

func (f *fakeFPAudit) WriteAudit(_ context.Context, e force_propagate.AuditEntry) error {
	f.entries = append(f.entries, e)
	return nil
}

type fakeHistoryAudit struct{ entries []canon_history_writer.AuditEntry }

func (f *fakeHistoryAudit) WriteAudit(_ context.Context, e canon_history_writer.AuditEntry) error {
	f.entries = append(f.entries, e)
	return nil
}

type fakeEmitter struct {
	emit []emitRec
}

type emitRec struct {
	EventType string
	Payload   map[string]any
}

func (f *fakeEmitter) Emit(_ context.Context, eventType string, payload map[string]any) error {
	cp := map[string]any{}
	for k, v := range payload {
		cp[k] = v
	}
	f.emit = append(f.emit, emitRec{EventType: eventType, Payload: cp})
	return nil
}

// ─── End-to-end test ─────────────────────────────────────────────────────

func TestForcePropagate_EndToEnd_5Realities(t *testing.T) {
	// Setup: 5 realities subscribe to a book.
	// - 3 ACK (one default-consent)
	// - 1 vetoes
	// - 1 pending (still within deadline → ErrConsentPending)
	r1, r2, r3, r4, r5 := uuid.New(), uuid.New(), uuid.New(), uuid.New(), uuid.New()
	bookID := uuid.New()
	canonEntryID := uuid.New()

	consent := &fakeConsentMap{
		decisions: map[uuid.UUID]force_propagate.ConsentDecision{
			r1: {Granted: true, ConsentedBy: uuid.New()},
			r2: {Granted: true, ConsentedBy: uuid.New()},
			r3: {Granted: true, Default: true},
			r4: {Granted: false, VetoReason: "lore conflict"},
			// r5 absent → ErrConsentPending
		},
	}

	db := &fakeDB{}
	audit := &fakeFPAudit{}
	emitter := &fakeEmitter{}
	o, err := force_propagate.New(force_propagate.Config{
		Subscribers: &fakeSubsForce{out: []uuid.UUID{r1, r2, r3, r4, r5}},
		Consent:     consent,
		DB:          db,
		Audit:       audit,
		Emitter:     emitter,
	})
	if err != nil {
		t.Fatal(err)
	}

	req := force_propagate.ForcePropagateRequest{
		OverrideID:    uuid.New(),
		CanonEntryID:  canonEntryID,
		BookID:        bookID,
		AttributePath: "world.climate",
		NewValue:      []byte(`"arid"`),
		CanonLayer:    "L2_seeded",
		Reason:        "governance",
		RequestedBy:   uuid.New(),
		RequestedAt:   time.Unix(1779000000, 0).UTC(),
	}

	outs, _ := o.Apply(context.Background(), req)
	if len(outs) != 5 {
		t.Fatalf("expected 5 per-reality outcomes, got %d", len(outs))
	}

	// 3 db writes (consented), 0 from veto/pending.
	if len(db.writes) != 3 {
		t.Errorf("expected 3 db writes (3 consented), got %d", len(db.writes))
	}

	// Event emissions tally.
	var consented, vetoed, compensating int
	for _, e := range emitter.emit {
		switch e.EventType {
		case force_propagate.EventOverrideConsented:
			consented++
		case force_propagate.EventOverrideVetoed:
			vetoed++
		case force_propagate.EventOverrideCompensating:
			compensating++
		}
	}
	if consented != 3 || vetoed != 1 || compensating != 3 {
		t.Errorf("event tally wrong: consented=%d vetoed=%d compensating=%d", consented, vetoed, compensating)
	}

	// Outcome distribution.
	var ok, skipped int
	for _, oc := range outs {
		if oc.Skipped {
			skipped++
		} else if oc.Compensating {
			ok++
		}
	}
	if ok != 3 {
		t.Errorf("expected 3 successful compensating outcomes, got %d", ok)
	}
	if skipped != 2 {
		t.Errorf("expected 2 skipped outcomes (veto + pending), got %d", skipped)
	}
}

// ─── L5.I conflict detector + reporter integration ──────────────────────

type fakeRealities2 struct{ out []uuid.UUID }

func (f *fakeRealities2) RealitiesForBook(_ context.Context, _ uuid.UUID) ([]uuid.UUID, error) {
	return f.out, nil
}

type fakeScanner2 struct {
	rows map[uuid.UUID][]l1_conflict_detector.L3EventRef
}

func (f *fakeScanner2) ScanL3EventsForAttribute(_ context.Context, realityID, _ uuid.UUID, _ string) ([]l1_conflict_detector.L3EventRef, error) {
	return f.rows[realityID], nil
}

func TestL1ConflictDetectorAndReporter_EndToEnd(t *testing.T) {
	r1, r2 := uuid.New(), uuid.New()
	bookID := uuid.New()
	canonEntryID := uuid.New()
	axiomVal := []byte(`"arid"`)
	conflictVal := []byte(`"tropical"`)

	scanner := &fakeScanner2{
		rows: map[uuid.UUID][]l1_conflict_detector.L3EventRef{
			r1: {
				{EventID: uuid.New(), RealityID: r1, BookID: bookID, AttributePath: "world.climate", RecordedValue: conflictVal},
				{EventID: uuid.New(), RealityID: r1, BookID: bookID, AttributePath: "world.climate", RecordedValue: axiomVal},
			},
			r2: {
				{EventID: uuid.New(), RealityID: r2, BookID: bookID, AttributePath: "world.climate", RecordedValue: conflictVal},
			},
		},
	}
	detector, err := l1_conflict_detector.New(l1_conflict_detector.Config{
		Realities: &fakeRealities2{out: []uuid.UUID{r1, r2}},
		Scanner:   scanner,
	})
	if err != nil {
		t.Fatal(err)
	}

	store := l1_conflict_reporter.NewInMemoryStore()
	reporter, err := l1_conflict_reporter.New(l1_conflict_reporter.Config{Detector: detector, Store: store})
	if err != nil {
		t.Fatal(err)
	}

	axiom := l1_conflict_detector.AxiomRef{
		CanonEntryID:  canonEntryID,
		BookID:        bookID,
		AttributePath: "world.climate",
		AxiomValue:    axiomVal,
	}
	rep, err := reporter.ScanAndPersist(context.Background(), axiom)
	if err != nil {
		t.Fatal(err)
	}
	// Acceptance: zero false negatives — both conflicting L3 events found.
	if len(rep.Conflicts) != 2 {
		t.Errorf("acceptance: expected 2 conflicts found, got %d", len(rep.Conflicts))
	}

	// Round-trip via reporter API.
	fetched, ok, err := reporter.LatestForAxiom(context.Background(), canonEntryID)
	if err != nil || !ok {
		t.Fatal("LatestForAxiom round-trip failed")
	}
	if fetched.ReportID != rep.ReportID {
		t.Error("report mismatch")
	}
}

// ─── L5.J timeline integration: history records both regular + compensating events ──

func TestTimeline_HistoryAppendOnRegularAndForcePropagate(t *testing.T) {
	store := timeline.NewInMemoryStore()
	audit := &fakeHistoryAudit{}
	w, err := canon_history_writer.New(canon_history_writer.Config{Store: store, Audit: audit})
	if err != nil {
		t.Fatal(err)
	}

	bookID := uuid.New()
	canonEntryID := uuid.New()
	realityID := uuid.New()

	// First: a regular canon.entry.updated (Kind=authored).
	if err := w.Handle(context.Background(), map[string]any{
		"event_type":     canon_history_writer.EventCanonUpdated,
		"event_id":       uuid.New().String(),
		"book_id":        bookID.String(),
		"canon_entry_id": canonEntryID.String(),
		"attribute_path": "world.climate",
		"canon_layer":    "L2_seeded",
		"new_value":      "\"temperate\"",
		"old_value":      "\"unknown\"",
	}); err != nil {
		t.Fatal(err)
	}

	// Second: a force-propagate compensating event (Kind=force_propagate).
	if err := w.Handle(context.Background(), map[string]any{
		"event_type":     canon_history_writer.EventOverrideCompensating,
		"event_id":       uuid.New().String(),
		"book_id":        bookID.String(),
		"canon_entry_id": canonEntryID.String(),
		"reality_id":     realityID.String(),
		"attribute_path": "world.climate",
		"canon_layer":    "L2_seeded",
		"new_value":      "\"arid\"",
		"old_value":      "\"temperate\"",
	}); err != nil {
		t.Fatal(err)
	}

	// Verify the timeline holds both events with correct kinds.
	rows, _ := store.Query(context.Background(), timeline.Query{CanonEntryID: canonEntryID})
	if len(rows) != 2 {
		t.Fatalf("expected 2 timeline rows, got %d", len(rows))
	}
	var kinds []timeline.CanonChangeKind
	for _, r := range rows {
		kinds = append(kinds, r.Kind)
	}
	if kinds[0] != timeline.CanonChangeKindAuthored {
		t.Errorf("first row kind wrong: %v", kinds[0])
	}
	if kinds[1] != timeline.CanonChangeKindForcePropagate {
		t.Errorf("second row kind wrong: %v", kinds[1])
	}
	// Q-L1A-3: audit count must match event count.
	if len(audit.entries) != 2 {
		t.Errorf("Q-L1A-3: audit count must equal event count; got %d", len(audit.entries))
	}
}

func TestTimeline_APPEND_ONLY_RejectsDuplicateAppend(t *testing.T) {
	// Same change_id MUST NOT be re-appended.
	store := timeline.NewInMemoryStore()
	entry := timeline.Entry{
		ChangeID:        uuid.New(),
		CanonEntryID:    uuid.New(),
		BookID:          uuid.New(),
		AttributePath:   "x",
		Kind:            timeline.CanonChangeKindAuthored,
		NewValue:        []byte(`"v"`),
		CanonLayer:      "L2_seeded",
		SourceEventID:   uuid.New(),
		SourceEventType: "canon.entry.updated",
		RecordedAt:      time.Now().UTC(),
	}
	if err := store.Append(context.Background(), entry); err != nil {
		t.Fatal(err)
	}
	// Re-append same ChangeID
	if err := store.Append(context.Background(), entry); err == nil {
		t.Error("APPEND-ONLY discipline broken: duplicate accepted")
	}
}
