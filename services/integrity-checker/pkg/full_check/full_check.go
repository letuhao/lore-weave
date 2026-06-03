// Package full_check is the L3.F monthly full-scan orchestrator. Same binary as
// L3.E daily mode (`services/integrity-checker`); selected via config
// `mode: monthly`. Differs from daily in two ways: it does NO sampling (walks
// ALL rows of each projection table), and it cursor-batches the walk in chunks
// of cfg.FullScanBatchSize (default 500) so no single SELECT holds a long lock
// on the table — between batches the loop yields, letting other queries
// interleave.
//
// It is ROW-CENTRIC, same as the daily [live.Checker]: the per-row verdict
// (replay via the replay-aggregate bin → byte-compare `to_jsonb - meta`) is the
// shared [live.CheckRow]; full_check only adds the full-scan cursor walk over the
// daily sampler's random LIMIT. (The pre-row-centric (aggregate_id, version)
// sampler/Comparator model it used to share with the deleted daily_loop is gone.)
//
// L1.J degraded-mode gating: at ModeEssentials+ the loop PAUSES (same as
// [live.Checker] — integrity checking is background work).
//
// CRITICAL: full check is heavier than daily by ~N/SampleSize. With N=10K rows
// per reality and SampleSize=20, monthly is ~500× the daily load. Hence:
//   - Different cron cadence (30 days vs 1 day)
//   - Different alert SLO (page only on >5 drifts in a monthly run; daily drift =
//     WARN only) — wired in infra/prometheus/alerts/projection.yaml
//   - Configurable scan window (low-traffic only) — wired in
//     infra/k8s/integrity-checker-cronjob.yaml
package full_check

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/live"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/metrics"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// CursorSource is the batched row reader for monthly mode. Returns row-centric
// [live.SampledRow]s in batches of `batchSize`, advancing an OPAQUE cursor
// between calls (`cursor == ""` on the first call; `nextCursor == ""` means
// end-of-table). The production pgx implementation (pgsource.ScanRows) orders by
// the table's PK columns and encodes the last row's PK as the cursor, so each row
// appears AT MOST ONCE across a sweep even under concurrent INSERTs.
type CursorSource interface {
	NextBatch(ctx context.Context, realityID uuid.UUID, table, cursor string, batchSize int) (rows []live.SampledRow, nextCursor string, err error)
}

// ModeReader exposes ServiceMode for L1.J degraded-mode gating.
type ModeReader interface {
	Mode() lifecycle.ServiceMode
}

// Config is the constructor input.
type Config struct {
	CursorSource CursorSource
	// Replayer re-derives each row via the replay-aggregate bin
	// (*replayloader.Loader satisfies it). Shared with the daily checker.
	Replayer    live.Replayer
	StateWriter *state_writer.Writer
	Mode        ModeReader
	Clock       func() time.Time
	// FullCheckIntervalDays from the config. Sets the persisted
	// `expected_next_sweep_at = NOW() + intervalDays * 24h`.
	FullCheckIntervalDays int
	// Emitter is OPTIONAL — when nil, no metrics are emitted.
	Emitter metrics.Emitter
}

// Loop is the monthly orchestrator.
type Loop struct {
	src          CursorSource
	replayer     live.Replayer
	stateWriter  *state_writer.Writer
	mode         ModeReader
	clock        func() time.Time
	intervalDays int
	emitter      metrics.Emitter
}

// New constructs a Loop.
func New(c Config) (*Loop, error) {
	switch {
	case c.CursorSource == nil:
		return nil, errors.New("full_check: CursorSource nil")
	case c.Replayer == nil:
		return nil, errors.New("full_check: Replayer nil")
	case c.StateWriter == nil:
		return nil, errors.New("full_check: StateWriter nil")
	case c.Mode == nil:
		return nil, errors.New("full_check: Mode nil")
	case c.Clock == nil:
		return nil, errors.New("full_check: Clock nil")
	case c.FullCheckIntervalDays <= 0:
		return nil, errors.New("full_check: FullCheckIntervalDays must be > 0")
	}
	return &Loop{
		src:          c.CursorSource,
		replayer:     c.Replayer,
		stateWriter:  c.StateWriter,
		mode:         c.Mode,
		clock:        c.Clock,
		intervalDays: c.FullCheckIntervalDays,
		emitter:      c.Emitter,
	}, nil
}

// IterationStats is the per-Run summary across all tables for one reality.
type IterationStats struct {
	RealityID  uuid.UUID
	Skipped    bool
	SkipReason string
	Reports    []types.DriftReport
}

// Run executes ONE monthly-mode iteration: walks every row of every configured
// table; aggregates drift; persists a per-table report. `dsn` is the reality's
// shard DSN, threaded to the replay-aggregate bin.
func (l *Loop) Run(ctx context.Context, realityID uuid.UUID, dsn string, tables []types.TableConfig) (IterationStats, error) {
	stats := IterationStats{RealityID: realityID}

	if l.mode.Mode() >= lifecycle.ModeEssentials {
		stats.Skipped = true
		stats.SkipReason = fmt.Sprintf("degraded_mode=%s", l.mode.Mode())
		return stats, nil
	}

	for _, tbl := range tables {
		report, err := l.runTable(ctx, realityID, dsn, tbl)
		live.EmitReport(l.emitter, string(types.CheckModeMonthly), realityID, report, err)
		if err != nil {
			return stats, fmt.Errorf("full_check: table=%s reality=%s: %w", tbl.TableName, realityID, err)
		}
		stats.Reports = append(stats.Reports, report)
	}
	return stats, nil
}

// runTable walks one table via cursor batching, rendering the row-centric verdict
// for each row via [live.CheckRow].
func (l *Loop) runTable(ctx context.Context, realityID uuid.UUID, dsn string, tbl types.TableConfig) (types.DriftReport, error) {
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
		batchSize = 500 // defensive default; config.Validate enforces > 0
	}
	// Cap iterations so a buggy cursor source (returns the same cursor) can't
	// infinite-loop us. 10M iters × 500 batchSize = 5B rows upper bound — well
	// above any realistic per-reality table size.
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
			break // end-of-table
		}
		// Guard against cursor stuckness (same cursor twice = abort).
		if nextCursor != "" && nextCursor == cursor {
			return report, fmt.Errorf("full_check: cursor did not advance (%q)", cursor)
		}
		for _, row := range rows {
			report.SampleSize++
			drifted, skipped := live.CheckRow(ctx, l.replayer, realityID, dsn, tbl.TableName, row)
			if skipped {
				report.Skipped++
				continue
			}
			if drifted {
				report.DriftCount++
				report.LastDriftedAggregateID = driftAggregateUUID(row)
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

// driftAggregateUUID mirrors live's SRE convenience pointer: prefer the first
// owning aggregate's id when it is a UUID; fall back to the row's event_id.
func driftAggregateUUID(row live.SampledRow) uuid.UUID {
	if len(row.Owning) > 0 {
		if id, err := uuid.Parse(row.Owning[0].ID); err == nil {
			return id
		}
	}
	return row.EventID
}

// ─── Test fakes ─────────────────────────────────────────────────────────────

// InMemCursorSource is the test fake. Rows are returned in insertion order with
// an index-based opaque cursor (the real PK-encoded cursor is pgsource's
// concern, tested there); this exercises the LOOP (batching, stuck-guard,
// end-of-table) independent of cursor encoding.
type InMemCursorSource struct {
	rows map[string][]live.SampledRow
}

// NewInMemCursorSource returns an empty fake.
func NewInMemCursorSource() *InMemCursorSource {
	return &InMemCursorSource{rows: make(map[string][]live.SampledRow)}
}

// AddRow appends a row for (realityID, table).
func (f *InMemCursorSource) AddRow(realityID uuid.UUID, table string, row live.SampledRow) {
	key := realityID.String() + "|" + table
	f.rows[key] = append(f.rows[key], row)
}

// NextBatch returns up to batchSize rows starting after `cursor` (the index of
// the last row returned, as a decimal string; empty on the first call).
func (f *InMemCursorSource) NextBatch(_ context.Context, realityID uuid.UUID, table, cursor string, batchSize int) ([]live.SampledRow, string, error) {
	key := realityID.String() + "|" + table
	all := f.rows[key]
	start := 0
	if cursor != "" {
		n, err := strconv.Atoi(cursor)
		if err != nil {
			return nil, "", fmt.Errorf("InMemCursorSource: bad cursor %q: %w", cursor, err)
		}
		start = n
	}
	if start >= len(all) {
		return nil, "", nil
	}
	end := start + batchSize
	if end > len(all) {
		end = len(all)
	}
	batch := make([]live.SampledRow, end-start)
	copy(batch, all[start:end])
	nextCursor := ""
	if end < len(all) {
		nextCursor = strconv.Itoa(end)
	}
	return batch, nextCursor, nil
}

// StaticMode is a test-only ModeReader.
type StaticMode struct{ M lifecycle.ServiceMode }

// Mode returns the static value.
func (s StaticMode) Mode() lifecycle.ServiceMode { return s.M }
