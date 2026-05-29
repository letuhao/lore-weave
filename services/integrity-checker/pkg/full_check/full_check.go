// Package full_check is the L3.F monthly full-scan orchestrator. Same
// binary as L3.E daily mode (`services/integrity-checker`); selected via
// config `mode: monthly`. Different from daily_loop in two ways:
//
//  1. NO sampling. Walks ALL rows of each projection table.
//  2. Cursor batching. Reads rows in batches of cfg.FullScanBatchSize
//     (default 500) so no single SELECT holds a long lock on the
//     projection table. Between batches the loop yields, allowing other
//     queries to interleave.
//
// L1.J degraded-mode gating: at ModeEssentials+ the loop PAUSES (same as
// daily_loop — integrity checking is background work).
//
// CRITICAL: full check is heavier than daily by ~N/SampleSize. With
// N=10K aggregates per reality and SampleSize=20, monthly is ~500× the
// daily load. Hence:
//   - Different cron cadence (30 days vs 1 day)
//   - Different alert SLO (page only on >5 drifts in a monthly run; daily
//     drift = WARN only) — wired in infra/prometheus/alerts/projection.yaml
//   - Configurable scan window (low-traffic only) — wired in
//     infra/k8s/integrity-checker-cronjob.yaml
//
// Reuses the SAME comparator + state_writer as daily_loop. The cursor
// abstraction is the only new piece.
package full_check

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

// CursorSource is the batched row reader for monthly mode. Returns rows
// in batches of `batchSize`, advancing an opaque cursor between calls.
// `cursor == ""` on the first call.
//
// Production wires:
//
//	SELECT aggregate_id, aggregate_type, event_id, aggregate_version,
//	       jsonb_strip_nulls(jsonb_build_object(<non-meta cols>)) AS payload
//	FROM <table>
//	WHERE aggregate_id > $cursor
//	ORDER BY aggregate_id
//	LIMIT $batchSize;
//
// `aggregate_id` as the cursor key guarantees stable pagination — each
// row appears AT MOST ONCE across a full sweep even with concurrent
// INSERTs (new rows with a later id won't disturb the cursor).
//
// Returns:
//   - rows: the batch (≤ batchSize)
//   - nextCursor: opaque continuation token; "" means end-of-table
//   - err: DB error
type CursorSource interface {
	NextBatch(ctx context.Context, realityID uuid.UUID, table, cursor string, batchSize int) (rows []sampler.ProjectionRow, nextCursor string, err error)
}

// ProjectionFetcher fetches the projection-row payload for one aggregate
// (same signature as daily_loop.ProjectionFetcher). Re-declared here
// to keep the package import graph 1-deep instead of cross-importing
// daily_loop (which would create a cycle if daily_loop later wanted to
// share helpers).
type ProjectionFetcher interface {
	FetchPayload(ctx context.Context, realityID uuid.UUID, table, aggregateID string, version uint64) ([]byte, error)
}

// ModeReader exposes ServiceMode for L1.J degraded-mode gating.
type ModeReader interface {
	Mode() lifecycle.ServiceMode
}

// Config is the constructor input.
type Config struct {
	CursorSource          CursorSource
	Comparator            *comparator.Comparator
	Fetcher               ProjectionFetcher
	StateWriter           *state_writer.Writer
	Mode                  ModeReader
	Clock                 func() time.Time
	// FullCheckIntervalDays from contracts/integrity/config.yaml. Used to
	// set `expected_next_sweep_at = NOW() + intervalDays * 24h`.
	FullCheckIntervalDays int
}

// Loop is the monthly orchestrator.
type Loop struct {
	src         CursorSource
	cmp         *comparator.Comparator
	fetcher     ProjectionFetcher
	stateWriter *state_writer.Writer
	mode        ModeReader
	clock       func() time.Time
	intervalDays int
}

// New constructs a Loop.
func New(c Config) (*Loop, error) {
	if c.CursorSource == nil {
		return nil, errors.New("full_check: CursorSource nil")
	}
	if c.Comparator == nil {
		return nil, errors.New("full_check: Comparator nil")
	}
	if c.Fetcher == nil {
		return nil, errors.New("full_check: Fetcher nil")
	}
	if c.StateWriter == nil {
		return nil, errors.New("full_check: StateWriter nil")
	}
	if c.Mode == nil {
		return nil, errors.New("full_check: Mode nil")
	}
	if c.Clock == nil {
		return nil, errors.New("full_check: Clock nil")
	}
	if c.FullCheckIntervalDays <= 0 {
		return nil, errors.New("full_check: FullCheckIntervalDays must be > 0")
	}
	return &Loop{
		src:          c.CursorSource,
		cmp:          c.Comparator,
		fetcher:      c.Fetcher,
		stateWriter:  c.StateWriter,
		mode:         c.Mode,
		clock:        c.Clock,
		intervalDays: c.FullCheckIntervalDays,
	}, nil
}

// IterationStats is the per-Run summary across all tables for one reality.
type IterationStats struct {
	RealityID  uuid.UUID
	Skipped    bool
	SkipReason string
	Reports    []types.DriftReport
}

// Run executes ONE monthly-mode iteration. Walks every row of every
// configured table; aggregates drift; persists per-table report.
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
			return stats, fmt.Errorf("full_check: table=%s reality=%s: %w", tbl.TableName, realityID, err)
		}
		stats.Reports = append(stats.Reports, report)
	}
	return stats, nil
}

// runTable walks one table via cursor batching.
func (l *Loop) runTable(ctx context.Context, realityID uuid.UUID, tbl types.TableConfig) (types.DriftReport, error) {
	start := l.clock()
	report := types.DriftReport{
		RealityID: realityID,
		TableName: tbl.TableName,
		CheckMode: string(types.CheckModeMonthly),
		CheckedAt: start,
	}

	cursor := ""
	batchSize := tbl.FullScanBatchSize
	if batchSize <= 0 {
		batchSize = 500 // defensive default; config.Validate enforces > 0 but live safety
	}
	// Cap iterations so a buggy cursor source (returns same cursor)
	// can't infinite-loop us. 10M iters × 500 batchSize = 5B rows
	// upper bound — well above any realistic per-reality table size.
	const maxIters = 10_000_000
	iter := 0
	for {
		// Respect context cancellation between batches (graceful shutdown).
		if err := ctx.Err(); err != nil {
			return report, fmt.Errorf("cancelled mid-scan after %d rows: %w", report.SampleSize, err)
		}
		iter++
		if iter > maxIters {
			return report, fmt.Errorf("full_check: cursor exceeded %d iterations (suspect buggy cursor)", maxIters)
		}
		rows, nextCursor, err := l.src.NextBatch(ctx, realityID, tbl.TableName, cursor, batchSize)
		if err != nil {
			return report, fmt.Errorf("NextBatch cursor=%q: %w", cursor, err)
		}
		if len(rows) == 0 && nextCursor == "" {
			// End-of-table.
			break
		}
		// Guard against cursor stuckness (would have caused infinite loop in
		// production once a bug landed) — same cursor twice = abort.
		if nextCursor != "" && nextCursor == cursor {
			return report, fmt.Errorf("full_check: cursor did not advance (%q)", cursor)
		}
		for _, row := range rows {
			report.SampleSize++
			payload, err := l.fetcher.FetchPayload(ctx, realityID, tbl.TableName, row.AggregateID, row.AggregateVersion)
			if err != nil {
				report.Skipped++
				continue
			}
			ref := types.AggregateRef{
				RealityID:        realityID,
				AggregateType:    row.AggregateType,
				AggregateID:      row.AggregateID,
				EventID:          row.EventID,
				AggregateVersion: row.AggregateVersion,
			}
			res := l.cmp.CompareOne(ctx, ref, payload)
			if res.Skipped {
				report.Skipped++
				continue
			}
			if res.Drifted {
				report.DriftCount++
				if aggUUID, err := uuid.Parse(row.AggregateID); err == nil {
					report.LastDriftedAggregateID = aggUUID
				}
				report.LastDriftedEventID = row.EventID
			}
		}
		if nextCursor == "" {
			break
		}
		cursor = nextCursor
	}

	report.DurationSeconds = l.clock().Sub(start).Seconds()

	// Monthly cadence next-sweep = intervalDays * 24h.
	delay := time.Duration(l.intervalDays) * 24 * time.Hour
	if err := l.stateWriter.Persist(ctx, report, delay); err != nil {
		return report, fmt.Errorf("state_writer: %w", err)
	}
	return report, nil
}

// InMemCursorSource is the test fake.
type InMemCursorSource struct {
	rows map[string][]sampler.ProjectionRow
}

// NewInMemCursorSource returns an empty fake.
func NewInMemCursorSource() *InMemCursorSource {
	return &InMemCursorSource{rows: make(map[string][]sampler.ProjectionRow)}
}

// AddRow appends a row for (realityID, table).
func (f *InMemCursorSource) AddRow(realityID uuid.UUID, table string, row sampler.ProjectionRow) {
	key := realityID.String() + "|" + table
	f.rows[key] = append(f.rows[key], row)
}

// NextBatch returns up to batchSize rows starting after `cursor`. Cursor
// is the aggregate_id of the LAST row returned in the previous batch;
// empty cursor on first call.
func (f *InMemCursorSource) NextBatch(_ context.Context, realityID uuid.UUID, table, cursor string, batchSize int) ([]sampler.ProjectionRow, string, error) {
	key := realityID.String() + "|" + table
	all := f.rows[key]
	startIdx := 0
	if cursor != "" {
		for i, r := range all {
			if r.AggregateID == cursor {
				startIdx = i + 1
				break
			}
		}
	}
	if startIdx >= len(all) {
		return nil, "", nil
	}
	end := startIdx + batchSize
	if end > len(all) {
		end = len(all)
	}
	batch := make([]sampler.ProjectionRow, end-startIdx)
	copy(batch, all[startIdx:end])
	nextCursor := ""
	if end < len(all) {
		nextCursor = all[end-1].AggregateID
	}
	return batch, nextCursor, nil
}

// StaticMode is a test-only ModeReader.
type StaticMode struct{ M lifecycle.ServiceMode }

// Mode returns the static value.
func (s StaticMode) Mode() lifecycle.ServiceMode { return s.M }

// InMemFetcher is the test fake.
type InMemFetcher struct {
	rows map[string][]byte
}

// NewInMemFetcher returns an empty fake.
func NewInMemFetcher() *InMemFetcher {
	return &InMemFetcher{rows: make(map[string][]byte)}
}

// AddRow registers a payload for one aggregate.
func (f *InMemFetcher) AddRow(realityID uuid.UUID, table, aggID string, version uint64, payload []byte) {
	key := fmt.Sprintf("%s|%s|%s|%d", realityID, table, aggID, version)
	f.rows[key] = payload
}

// FetchPayload returns the payload or error.
func (f *InMemFetcher) FetchPayload(_ context.Context, realityID uuid.UUID, table, aggID string, version uint64) ([]byte, error) {
	key := fmt.Sprintf("%s|%s|%s|%d", realityID, table, aggID, version)
	p, ok := f.rows[key]
	if !ok {
		return nil, fmt.Errorf("InMemFetcher: no row for %s", key)
	}
	return p, nil
}
