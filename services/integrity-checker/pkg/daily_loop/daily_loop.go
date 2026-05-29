// Package daily_loop is the L3.E orchestrator. One Run() iteration per
// (reality, table) per scheduling tick. Flow:
//
//  1. sampler.SampleTable(table) → []AggregateRef (up to SampleSize)
//  2. for each ref: lookup projection row payload (ProjectionFetcher);
//     comparator.CompareOne(ref, payload) → SampleResult
//  3. aggregate into DriftReport
//  4. state_writer.Persist(report, 24h delay)
//
// L1.J degraded-mode gating: at ModeEssentials+ the loop PAUSES.
// Integrity checking is background work (we'd rather fail to detect drift
// for a window than add load to a stressed DB during incident response).
//
// One-table-at-a-time: the loop SERIALIZES across the 10 L3.A tables to
// bound concurrent load on the per-reality DB. A future optimization
// could parallelize per-table at a small concurrency cap; cycle-15 keeps
// it simple.
package daily_loop

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/comparator"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/sampler"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// ProjectionFetcher fetches the projection-row payload for one sampled
// aggregate. Same shape as sampler.RowSource but keyed by ref instead of
// random pick. Production wires:
//
//	SELECT jsonb_strip_nulls(jsonb_build_object(<all non-meta cols>))
//	FROM <table> WHERE aggregate_id = $1 AND aggregate_version = $2;
//
// Tests inject InMemFetcher.
type ProjectionFetcher interface {
	FetchPayload(ctx context.Context, realityID uuid.UUID, table, aggregateID string, version uint64) ([]byte, error)
}

// ModeReader exposes ServiceMode for L1.J degraded-mode gating.
type ModeReader interface {
	Mode() lifecycle.ServiceMode
}

// Config is the constructor input.
type Config struct {
	Sampler     *sampler.Sampler
	Comparator  *comparator.Comparator
	Fetcher     ProjectionFetcher
	StateWriter *state_writer.Writer
	Mode        ModeReader
	Clock       func() time.Time
}

// Loop is the orchestrator.
type Loop struct {
	sampler     *sampler.Sampler
	comparator  *comparator.Comparator
	fetcher     ProjectionFetcher
	stateWriter *state_writer.Writer
	mode        ModeReader
	clock       func() time.Time
}

// New constructs a Loop.
func New(c Config) (*Loop, error) {
	if c.Sampler == nil {
		return nil, errors.New("daily_loop: Sampler nil")
	}
	if c.Comparator == nil {
		return nil, errors.New("daily_loop: Comparator nil")
	}
	if c.Fetcher == nil {
		return nil, errors.New("daily_loop: Fetcher nil")
	}
	if c.StateWriter == nil {
		return nil, errors.New("daily_loop: StateWriter nil")
	}
	if c.Mode == nil {
		return nil, errors.New("daily_loop: Mode nil")
	}
	if c.Clock == nil {
		return nil, errors.New("daily_loop: Clock nil")
	}
	return &Loop{
		sampler:     c.Sampler,
		comparator:  c.Comparator,
		fetcher:     c.Fetcher,
		stateWriter: c.StateWriter,
		mode:        c.Mode,
		clock:       c.Clock,
	}, nil
}

// IterationStats is the per-Run summary across all tables for one reality.
type IterationStats struct {
	RealityID  uuid.UUID
	Skipped    bool
	SkipReason string
	// Per-table reports (sized by # of tables in cfg.Tables passed to Run).
	Reports []types.DriftReport
}

// Run executes ONE daily-mode iteration for the given reality across the
// configured tables. Skips entirely when mode >= ModeEssentials.
func (l *Loop) Run(ctx context.Context, realityID uuid.UUID, tables []types.TableConfig) (IterationStats, error) {
	stats := IterationStats{RealityID: realityID}

	if l.mode.Mode() >= lifecycle.ModeEssentials {
		stats.Skipped = true
		stats.SkipReason = fmt.Sprintf("degraded_mode=%s", l.mode.Mode())
		return stats, nil
	}

	for _, tbl := range tables {
		report, err := l.runTable(ctx, realityID, tbl)
		if err != nil {
			return stats, fmt.Errorf("daily_loop: table=%s reality=%s: %w", tbl.TableName, realityID, err)
		}
		stats.Reports = append(stats.Reports, report)
	}
	return stats, nil
}

// runTable handles one (reality, table) check.
func (l *Loop) runTable(ctx context.Context, realityID uuid.UUID, tbl types.TableConfig) (types.DriftReport, error) {
	start := l.clock()
	refs, err := l.sampler.SampleTable(ctx, realityID, tbl)
	if err != nil {
		return types.DriftReport{}, fmt.Errorf("sample: %w", err)
	}

	report := types.DriftReport{
		RealityID:  realityID,
		TableName:  tbl.TableName,
		SampleSize: len(refs),
		CheckMode:  string(types.CheckModeDaily),
		CheckedAt:  start,
	}

	for _, ref := range refs {
		payload, err := l.fetcher.FetchPayload(ctx, realityID, tbl.TableName, ref.AggregateID, ref.AggregateVersion)
		if err != nil {
			// Fetch failures count as SKIPPED — the projection row may
			// have been deleted between sample and fetch (transient).
			// Do NOT count as drift to avoid false positives.
			report.Skipped++
			continue
		}
		res := l.comparator.CompareOne(ctx, ref, payload)
		if res.Skipped {
			report.Skipped++
			continue
		}
		if res.Drifted {
			report.DriftCount++
			// Convenience pointer for SRE; overwritten if more drifts —
			// we only keep the LAST as a starting point, the metrics +
			// SRE query into the projection table give the full picture.
			aggID, err := uuid.Parse(ref.AggregateID)
			if err == nil {
				report.LastDriftedAggregateID = aggID
			}
			report.LastDriftedEventID = ref.EventID
		}
	}

	report.DurationSeconds = l.clock().Sub(start).Seconds()

	// Persist with 24h next-sweep delay (daily cadence).
	if err := l.stateWriter.Persist(ctx, report, 24*time.Hour); err != nil {
		return report, fmt.Errorf("state_writer: %w", err)
	}
	return report, nil
}

// InMemFetcher is the test fake.
type InMemFetcher struct {
	rows map[string][]byte
}

// NewInMemFetcher returns an empty fake.
func NewInMemFetcher() *InMemFetcher {
	return &InMemFetcher{rows: make(map[string][]byte)}
}

// AddRow registers a payload for one (reality, table, aggregate, version).
func (f *InMemFetcher) AddRow(realityID uuid.UUID, table, aggID string, version uint64, payload []byte) {
	key := fmt.Sprintf("%s|%s|%s|%d", realityID, table, aggID, version)
	f.rows[key] = payload
}

// FetchPayload returns the registered payload or "not found" error.
func (f *InMemFetcher) FetchPayload(_ context.Context, realityID uuid.UUID, table, aggID string, version uint64) ([]byte, error) {
	key := fmt.Sprintf("%s|%s|%s|%d", realityID, table, aggID, version)
	p, ok := f.rows[key]
	if !ok {
		return nil, fmt.Errorf("InMemFetcher: no row for %s", key)
	}
	return p, nil
}

// StaticMode is a test-only ModeReader.
type StaticMode struct{ M lifecycle.ServiceMode }

// Mode returns the static value.
func (s StaticMode) Mode() lifecycle.ServiceMode { return s.M }
