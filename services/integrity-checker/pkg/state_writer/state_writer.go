// Package state_writer turns DriftReport values into UPDATE statements
// against the per-reality `projection_drift_state` table (cycle 13
// 0007_drift_metadata.up.sql).
//
// CRITICAL — table allowlist: the migration's CHECK constraint enforces
// that only the 10 L3.A tables can appear in `table_name`. The writer
// pre-validates against types.L3ATables so we get a Go-side error MSG
// instead of an opaque CHECK violation from Postgres.
//
// V1 SKELETON — like sampler / comparator, ships with an in-memory
// Persister fake. Production wires pgx via the same Persister interface.
package state_writer

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// Persister abstracts the UPSERT against projection_drift_state. The
// signature matches the cycle-13 cron skeleton's psql UPDATE shape.
//
// `expectedNextSweepAt` is the time at which the next sweep is expected;
// daily mode passes NOW()+24h, monthly passes NOW()+intervalDays.
type Persister interface {
	UpdateDriftState(
		ctx context.Context,
		realityID uuid.UUID,
		report types.DriftReport,
		expectedNextSweepAt time.Time,
	) error
}

// Writer is the orchestrator helper.
type Writer struct {
	persister Persister
	clock     func() time.Time
}

// Config is the constructor input.
type Config struct {
	Persister Persister
	Clock     func() time.Time
}

// New constructs a Writer.
func New(c Config) (*Writer, error) {
	if c.Persister == nil {
		return nil, errors.New("state_writer: Persister nil")
	}
	if c.Clock == nil {
		return nil, errors.New("state_writer: Clock nil")
	}
	return &Writer{persister: c.Persister, clock: c.Clock}, nil
}

// Persist writes a drift report. `nextSweepDelay` is added to the
// configured clock to set `expected_next_sweep_at` — daily mode passes
// 24h, monthly passes (intervalDays * 24h).
func (w *Writer) Persist(ctx context.Context, report types.DriftReport, nextSweepDelay time.Duration) error {
	if err := w.validateReport(report); err != nil {
		return fmt.Errorf("state_writer: validate: %w", err)
	}
	expectedNext := w.clock().Add(nextSweepDelay)
	if err := w.persister.UpdateDriftState(ctx, report.RealityID, report, expectedNext); err != nil {
		return fmt.Errorf("state_writer: persist table=%s: %w", report.TableName, err)
	}
	return nil
}

// validateReport enforces the table-name allowlist + invariants.
func (w *Writer) validateReport(r types.DriftReport) error {
	allow := map[string]struct{}{}
	for _, t := range types.L3ATables {
		allow[t] = struct{}{}
	}
	if _, ok := allow[r.TableName]; !ok {
		return fmt.Errorf("table %q not in L3.A allowlist (would violate projection_drift_table_name_allowlist CHECK)", r.TableName)
	}
	if r.SampleSize < 0 {
		return fmt.Errorf("table %q: SampleSize=%d (must be >= 0)", r.TableName, r.SampleSize)
	}
	if r.DriftCount < 0 {
		return fmt.Errorf("table %q: DriftCount=%d (must be >= 0; CHECK projection_drift_count_nonneg)", r.TableName, r.DriftCount)
	}
	if r.DriftCount > 0 && r.LastDriftedAggregateID == uuid.Nil {
		return fmt.Errorf("table %q: DriftCount=%d but LastDriftedAggregateID is NIL", r.TableName, r.DriftCount)
	}
	return nil
}

// InMemPersister is the test fake. Records every UpdateDriftState call.
type InMemPersister struct {
	Calls []InMemCall
}

// InMemCall captures one UpdateDriftState invocation.
type InMemCall struct {
	RealityID           uuid.UUID
	Report              types.DriftReport
	ExpectedNextSweepAt time.Time
}

// NewInMemPersister returns an empty fake.
func NewInMemPersister() *InMemPersister { return &InMemPersister{} }

// UpdateDriftState records the call.
func (f *InMemPersister) UpdateDriftState(_ context.Context, realityID uuid.UUID, report types.DriftReport, expectedNext time.Time) error {
	f.Calls = append(f.Calls, InMemCall{RealityID: realityID, Report: report, ExpectedNextSweepAt: expectedNext})
	return nil
}
