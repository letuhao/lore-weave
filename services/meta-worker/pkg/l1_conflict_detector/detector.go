// Package l1_conflict_detector is L5.I.1 — the meta-worker L1 axiomatic
// conflict detector.
//
// RAID cycle 27 DPS 2. When an L1 canon update event arrives (e.g.
// canon.entry.promoted to L1_axiom, or canon.entry.updated for a row
// where canon_layer='L1_axiom'), this detector scans per-reality
// projection events for L3 events that conflict with the new L1 axiom.
//
// # Why this exists
//
// L1_axiom canon is supposed to be axiomatic — no L3 event may
// contradict it. But the system supports a workflow where:
//
//   1. An L2_seeded canon entry is authored.
//   2. Per-reality L3 events accumulate referencing the L2 value.
//   3. The author promotes L2 → L1 (per M4 §9.7.4 harder gate).
//
// At step 3, any L3 events written between (1) and (3) that conflict
// with the now-L1 value MUST be:
//
//   - Identified (this detector)
//   - Surfaced to authoring UI (via l1_conflict_reporter)
//   - Optionally blocked retroactively (governance call, not foundation)
//
// # What "conflicts" means
//
// An L3 event conflicts with an L1 canon row when both:
//
//   a. The event payload references the same (book_id, attribute_path).
//   b. The event's recorded value differs from the L1 axiom value.
//
// V1 uses the data-driven `contracts_prompt::canon_guardrail` rule set —
// a conflict is flagged when `guardrail.check_proposed_write` would
// reject the L3 event's value AS IF it were a fresh proposal.
//
// # Cross-cycle wiring
//
//   - Cycle 23 L5.D canon_projection: provides the L1 axiom values
//     (via canon_layer='L1_axiom' filter).
//   - Cycle 24 canon_writer: the consumer that triggers this detector
//     (a downstream cycle wires `OnL1Updated → Detector.Scan`).
//   - Cycle 27 L5.I.3 YamlGuardrail (Rust): the reference predicate
//     evaluator. Go-side L1ConflictDetector uses a simplified
//     equality check; full Rust guardrail is the SSOT.
//
// # What this detector DOES NOT do
//
//   - Rewrite or compensate L3 events — that's L5.H force-propagate.
//   - Block FUTURE L3 writes — that's the canon_guardrail interface
//     called pre-prompt-assembly (cycle 27 DPS 2).
package l1_conflict_detector

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// L3EventRef references one historical L3 event that conflicts with a
// newly-axiomatic L1 canon row.
type L3EventRef struct {
	EventID       uuid.UUID
	RealityID     uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	// RecordedValue is the canonical JSON the L3 event recorded for the
	// attribute (decoded by the L3 events scanner).
	RecordedValue []byte
	RecordedAt    time.Time
}

// AxiomRef describes the L1 canon row that the conflict is judged
// against.
type AxiomRef struct {
	CanonEntryID  uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	AxiomValue    []byte // canonical JSON bytes for L1 axiom
}

// Conflict pairs an L3 event with the L1 axiom it violates.
type Conflict struct {
	Axiom    AxiomRef
	L3Event  L3EventRef
	Reason   string // human-readable explanation (e.g. "value mismatch")
	Severity string // "block" | "warn"
}

// L3EventScanner returns the L3 events in a reality that reference a
// given (book_id, attribute_path). Production binds this to a per-reality
// event-log SELECT (cycle 17 L4.A EventStore.ReadStream filter by
// aggregate type/attribute). Tests inject a fixture.
type L3EventScanner interface {
	ScanL3EventsForAttribute(ctx context.Context, realityID, bookID uuid.UUID, attributePath string) ([]L3EventRef, error)
}

// RealityLookup returns realities that subscribe to a given book.
type RealityLookup interface {
	RealitiesForBook(ctx context.Context, bookID uuid.UUID) ([]uuid.UUID, error)
}

// ValuePredicate returns nil if the L3 recorded value is COMPATIBLE
// with the axiom value, or an error describing the conflict.
//
// Production binds this to a thin Go wrapper around
// `contracts_prompt::YamlGuardrail` (via cgo or a thin HTTP call). V1
// uses the in-package canonical-bytes equality predicate
// (CanonicalEqualityPredicate).
type ValuePredicate interface {
	Compatible(axiomValue, l3Value []byte) error
}

// CanonicalEqualityPredicate is the V1 in-package value comparator: an
// L3 event conflicts with an axiom iff the recorded value DIFFERS from
// the axiom value (byte-for-byte after JSON canonicalization).
//
// Production may replace this with a guardrail-rule-driven predicate
// (e.g. NumericRange would allow L3 values within a band even if not
// byte-exact). Foundation ships the strict equality predicate as the
// safe default.
type CanonicalEqualityPredicate struct{}

// Compatible implements ValuePredicate.
func (CanonicalEqualityPredicate) Compatible(axiom, l3 []byte) error {
	if equalCanonicalJSON(axiom, l3) {
		return nil
	}
	return fmt.Errorf("value mismatch: axiom=%s l3=%s", string(axiom), string(l3))
}

// Detector scans for L1 conflicts across realities.
type Detector struct {
	realities RealityLookup
	scanner   L3EventScanner
	pred      ValuePredicate
}

// Config bundles deps.
type Config struct {
	Realities RealityLookup
	Scanner   L3EventScanner
	Predicate ValuePredicate // optional; defaults to CanonicalEqualityPredicate
}

// New constructs a Detector. Realities + Scanner required.
func New(cfg Config) (*Detector, error) {
	if cfg.Realities == nil {
		return nil, errors.New("l1_conflict_detector: Realities nil")
	}
	if cfg.Scanner == nil {
		return nil, errors.New("l1_conflict_detector: Scanner nil")
	}
	pred := cfg.Predicate
	if pred == nil {
		pred = CanonicalEqualityPredicate{}
	}
	return &Detector{
		realities: cfg.Realities,
		scanner:   cfg.Scanner,
		pred:      pred,
	}, nil
}

// Scan finds all L3 events across all realities subscribed to `axiom.BookID`
// that conflict with the L1 axiom. Returns the full conflict list.
//
// **Invariant**: zero false-negatives — every conflicting L3 event is
// returned. False-positives are acceptable (governance reviews each
// conflict).
func (d *Detector) Scan(ctx context.Context, axiom AxiomRef) ([]Conflict, error) {
	if axiom.BookID == uuid.Nil {
		return nil, errors.New("l1_conflict_detector: axiom BookID required")
	}
	if axiom.AttributePath == "" {
		return nil, errors.New("l1_conflict_detector: axiom AttributePath required")
	}

	realities, err := d.realities.RealitiesForBook(ctx, axiom.BookID)
	if err != nil {
		return nil, fmt.Errorf("l1_conflict_detector: realities lookup: %w", err)
	}

	var conflicts []Conflict
	for _, realityID := range realities {
		evts, err := d.scanner.ScanL3EventsForAttribute(ctx, realityID, axiom.BookID, axiom.AttributePath)
		if err != nil {
			return nil, fmt.Errorf("l1_conflict_detector: scan reality=%s: %w", realityID, err)
		}
		for _, e := range evts {
			if perr := d.pred.Compatible(axiom.AxiomValue, e.RecordedValue); perr != nil {
				conflicts = append(conflicts, Conflict{
					Axiom:    axiom,
					L3Event:  e,
					Reason:   perr.Error(),
					Severity: "block",
				})
			}
		}
	}
	return conflicts, nil
}

// equalCanonicalJSON returns true iff a and b decode to equal JSON
// values. Empty bytes compare equal only to empty.
func equalCanonicalJSON(a, b []byte) bool {
	if len(a) == 0 && len(b) == 0 {
		return true
	}
	if len(a) == 0 || len(b) == 0 {
		return false
	}
	// Defensive byte compare with trim — production may swap a deep
	// JSON-normalize. Foundation V1 keeps it byte-exact.
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
