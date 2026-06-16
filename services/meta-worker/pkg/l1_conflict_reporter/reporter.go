// Package l1_conflict_reporter is L5.I.2 — the reporter shim that
// returns the L1ConflictDetector output to authoring UI (glossary-service)
// via either a synchronous in-process call or an out-of-band store.
//
// RAID cycle 27 DPS 2.
//
// # Design
//
// The reporter is a thin layer over the detector that:
//
//   - Persists conflict reports to a `ReportStore` (production binds a
//     meta-DB `l1_conflict_reports` table; foundation ships InMemory).
//   - Supports the polling API expected by the authoring UI:
//     `LatestForAxiom(ctx, canonEntryID) → []Conflict`.
//   - Supports an HTTP/RPC adapter (downstream cycle binds it to
//     `contracts/api/glossary-service/canon_conflicts.yaml`).
//
// # Why a separate package
//
// Detector is pure scan logic; reporter handles persistence + retrieval
// (different concerns, different blast radii). Splitting also lets the
// detector be reused by L5.J change-timeline aggregation without the
// reporter's persistence baggage.
package l1_conflict_reporter

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/foundation/services/meta-worker/pkg/l1_conflict_detector"
)

// Report bundles the detector output with a stable report_id + timestamp
// so authoring UI can re-poll deterministically.
type Report struct {
	ReportID    uuid.UUID
	AxiomEntry  uuid.UUID
	GeneratedAt time.Time
	Conflicts   []l1_conflict_detector.Conflict
}

// ReportStore is the persistence interface. Production binds a meta-DB
// table; tests + V1 ship InMemoryStore.
type ReportStore interface {
	Save(ctx context.Context, r Report) error
	LatestForAxiom(ctx context.Context, canonEntryID uuid.UUID) (Report, bool, error)
}

// Reporter wraps a Detector + ReportStore.
type Reporter struct {
	detector *l1_conflict_detector.Detector
	store    ReportStore
	clock    func() time.Time
}

// Config bundles deps.
type Config struct {
	Detector *l1_conflict_detector.Detector
	Store    ReportStore
	Clock    func() time.Time
}

// New constructs a Reporter. Detector + Store required.
func New(cfg Config) (*Reporter, error) {
	if cfg.Detector == nil {
		return nil, errors.New("l1_conflict_reporter: Detector nil")
	}
	if cfg.Store == nil {
		return nil, errors.New("l1_conflict_reporter: Store nil")
	}
	clk := cfg.Clock
	if clk == nil {
		clk = func() time.Time { return time.Now().UTC() }
	}
	return &Reporter{detector: cfg.Detector, store: cfg.Store, clock: clk}, nil
}

// ScanAndPersist runs the detector + persists the report. Returns the
// stored Report.
func (r *Reporter) ScanAndPersist(ctx context.Context, axiom l1_conflict_detector.AxiomRef) (Report, error) {
	conflicts, err := r.detector.Scan(ctx, axiom)
	if err != nil {
		return Report{}, err
	}
	rep := Report{
		ReportID:    uuid.New(),
		AxiomEntry:  axiom.CanonEntryID,
		GeneratedAt: r.clock(),
		Conflicts:   conflicts,
	}
	if err := r.store.Save(ctx, rep); err != nil {
		return Report{}, err
	}
	return rep, nil
}

// LatestForAxiom returns the most recent report for `canonEntryID`.
// Returns (Report{}, false, nil) when no report has been generated yet.
func (r *Reporter) LatestForAxiom(ctx context.Context, canonEntryID uuid.UUID) (Report, bool, error) {
	return r.store.LatestForAxiom(ctx, canonEntryID)
}

// ─────────────────────────────────────────────────────────────────────────
// InMemoryStore — V1 default impl + test scaffolding.
// ─────────────────────────────────────────────────────────────────────────

// InMemoryStore is the foundation-V1 ReportStore. Production swaps to
// a meta-DB-backed impl.
type InMemoryStore struct {
	mu    sync.Mutex
	byKey map[uuid.UUID]Report // keyed by AxiomEntry; keeps LATEST only
}

// NewInMemoryStore constructs an InMemoryStore.
func NewInMemoryStore() *InMemoryStore {
	return &InMemoryStore{byKey: map[uuid.UUID]Report{}}
}

// Save stores the report under its AxiomEntry. Overwrites any prior
// report for the same axiom (LatestForAxiom semantics).
func (s *InMemoryStore) Save(_ context.Context, r Report) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.byKey[r.AxiomEntry] = r
	return nil
}

// LatestForAxiom returns the latest report for `canonEntryID`.
func (s *InMemoryStore) LatestForAxiom(_ context.Context, canonEntryID uuid.UUID) (Report, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	r, ok := s.byKey[canonEntryID]
	return r, ok, nil
}

// Count returns the number of stored reports (test helper).
func (s *InMemoryStore) Count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.byKey)
}
