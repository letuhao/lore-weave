// Package live is the ROW/PK-centric L3.E orchestrator — the live replacement
// for the skeleton's (aggregate_id, version) daily_loop. For one (reality,
// table) it: samples N projection rows (RowSampler), re-derives each via the
// replay-aggregate bin (Replayer = pkg/replayloader), byte-compares the
// replayed `to_jsonb - meta` payload against the live row's, and persists a
// per-table DriftReport (reusing pkg/state_writer).
//
// Why a new orchestrator (not a reshape of daily_loop): the skeleton keyed
// everything on a single (aggregate_id, version), which cannot address the
// composite PKs of the real projection tables or the cross-aggregate
// npc_session_memory_projection. This package is the row-centric model from
// docs/plans/2026-06-03-l3ef-integrity-checker.md. The pgx RowSampler / Persister
// and the main daemon are slice 2c (they need a live DB); this package is the
// orchestration BRAIN, fully unit-testable with fakes.
package live

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/comparator"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/replayloader"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/tablemap"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// SampledRow is one sampled projection row (the row-centric unit of work).
type SampledRow struct {
	// PK is the row's primary key (column → canonical text value).
	PK map[string]string
	// EventID is the row's VerificationMeta event_id — the replay BOUNDARY.
	EventID uuid.UUID
	// AggregateVersion is the row's VerificationMeta aggregate_version (carried
	// for the report / debugging; the boundary itself is EventID).
	AggregateVersion uint64
	// Payload is the live row's canonical `to_jsonb - meta` (what the projection
	// runner actually wrote).
	Payload []byte
	// Owning is the resolved owning aggregate(s) to replay (see ResolveOwning).
	Owning []tablemap.OwningAggregate
}

// RowSampler samples rows (and resolves each row's owning aggregates) for one
// (reality, table). The pgx implementation lands in slice 2c.
type RowSampler interface {
	SampleRows(ctx context.Context, realityID uuid.UUID, dsn, table string, limit int) ([]SampledRow, error)
}

// Replayer re-derives one row via the replay-aggregate bin. *replayloader.Loader
// satisfies this.
type Replayer interface {
	Replay(ctx context.Context, req replayloader.ReplayRequest) (replayloader.ReplayResult, error)
}

// ModeReader exposes ServiceMode for L1.J degraded-mode gating (integrity
// checking pauses at ModeEssentials+ so it never loads a stressed DB).
type ModeReader interface {
	Mode() lifecycle.ServiceMode
}

// OwnerLookup resolves the (aggregate_type, aggregate_id) that last wrote a row,
// from its event_id. The pgx sampler backs this with
// `SELECT aggregate_type, aggregate_id FROM events WHERE event_id=$1`.
//
// When the row's event_id is no longer in `events` (the owning event was
// archived / pruned by retention), the lookup MUST return an error that wraps
// [ErrOwnerPruned] — such a row cannot be re-derived, so the checker SKIPS it
// rather than failing the whole sweep. This matters acutely for the monthly
// full-scan, which walks every row including old ones whose partitions have been
// detached/archived.
type OwnerLookup func(ctx context.Context, eventID uuid.UUID) (aggType, aggID string, err error)

// ErrOwnerPruned signals that a sampled row's owning event is gone from `events`
// (archived / pruned) so the row is UNVERIFIABLE. [ResolveOwning] returns it (the
// bare sentinel) for single-aggregate tables; the samplers (pgsource) treat it as
// "skip this row" — they emit the row with a nil Owning, and [CheckRow] folds a
// nil-Owning row into `skipped` (it cannot be replayed).
var ErrOwnerPruned = errors.New("live: owning event pruned/archived — row unverifiable")

// ResolveOwning returns the owning aggregate(s) to replay for a sampled row.
// CROSS-aggregate tables (npc_session_memory_projection) derive the SET from the
// PK; SINGLE-aggregate tables resolve the one owner from the row's event_id.
func ResolveOwning(
	ctx context.Context,
	table string,
	pk map[string]string,
	eventID uuid.UUID,
	lookup OwnerLookup,
) ([]tablemap.OwningAggregate, error) {
	spec, ok := tablemap.Lookup(table)
	if !ok {
		return nil, fmt.Errorf("live: unknown projection table %q", table)
	}
	if spec.CrossAggregate {
		return spec.DeriveOwning(pk)
	}
	if lookup == nil {
		return nil, errors.New("live: nil OwnerLookup for a single-aggregate table")
	}
	aggType, aggID, err := lookup(ctx, eventID)
	if err != nil {
		if errors.Is(err, ErrOwnerPruned) {
			// Owning event archived/pruned → row is unverifiable. Propagate the
			// bare sentinel so the sampler can SKIP this row (not fail the sweep).
			return nil, ErrOwnerPruned
		}
		return nil, fmt.Errorf("live: resolve owner for event %s: %w", eventID, err)
	}
	if aggType == "" || aggID == "" {
		return nil, fmt.Errorf("live: empty owner (type=%q id=%q) for event %s", aggType, aggID, eventID)
	}
	return []tablemap.OwningAggregate{{Type: aggType, ID: aggID}}, nil
}

// Checker orchestrates row-centric integrity checks.
type Checker struct {
	sampler  RowSampler
	replayer Replayer
	writer   *state_writer.Writer
	mode     ModeReader
	clock    func() time.Time
}

// Config is the Checker constructor input.
type Config struct {
	Sampler  RowSampler
	Replayer Replayer
	Writer   *state_writer.Writer
	Mode     ModeReader
	Clock    func() time.Time
}

// NewChecker constructs a Checker.
func NewChecker(c Config) (*Checker, error) {
	switch {
	case c.Sampler == nil:
		return nil, errors.New("live: Sampler nil")
	case c.Replayer == nil:
		return nil, errors.New("live: Replayer nil")
	case c.Writer == nil:
		return nil, errors.New("live: Writer nil")
	case c.Mode == nil:
		return nil, errors.New("live: Mode nil")
	case c.Clock == nil:
		return nil, errors.New("live: Clock nil")
	}
	return &Checker{c.Sampler, c.Replayer, c.Writer, c.Mode, c.Clock}, nil
}

// Iteration is the per-Run summary across all tables for one reality.
type Iteration struct {
	RealityID  uuid.UUID
	Skipped    bool
	SkipReason string
	Reports    []types.DriftReport
}

// Run executes ONE daily-mode iteration for a reality across the configured
// tables. Skips ENTIRELY (no DB load) when the service is at ModeEssentials+.
func (c *Checker) Run(ctx context.Context, realityID uuid.UUID, dsn string, tables []types.TableConfig) (Iteration, error) {
	it := Iteration{RealityID: realityID}
	if c.mode.Mode() >= lifecycle.ModeEssentials {
		it.Skipped = true
		it.SkipReason = fmt.Sprintf("degraded_mode=%s", c.mode.Mode())
		return it, nil
	}
	for _, tbl := range tables {
		rep, err := c.CheckTable(ctx, realityID, dsn, tbl)
		if err != nil {
			return it, fmt.Errorf("live: table=%s reality=%s: %w", tbl.TableName, realityID, err)
		}
		it.Reports = append(it.Reports, rep)
	}
	return it, nil
}

// CheckTable runs one (reality, table) check: sample → replay each row →
// byte-compare → DriftReport → persist (24h next-sweep). Drift verdict per row:
//
//   - replay hard-error / Skippable (replay error or 0 in-bound events) → SKIP
//   - replay found a row, byte-NOT-equal → DRIFT
//   - replay produced NO row but had events (orphan projection row) → DRIFT
//   - byte-equal → clean
func (c *Checker) CheckTable(ctx context.Context, realityID uuid.UUID, dsn string, tbl types.TableConfig) (types.DriftReport, error) {
	start := c.clock()
	report := types.DriftReport{
		RealityID: realityID,
		TableName: tbl.TableName,
		CheckMode: string(types.CheckModeDaily),
		CheckedAt: start,
	}

	rows, err := c.sampler.SampleRows(ctx, realityID, dsn, tbl.TableName, tbl.SampleSize)
	if err != nil {
		return report, fmt.Errorf("sample: %w", err)
	}
	report.SampleSize = len(rows)

	for _, row := range rows {
		drifted, skipped := CheckRow(ctx, c.replayer, realityID, dsn, tbl.TableName, row)
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

	report.DurationSeconds = c.clock().Sub(start).Seconds()
	if err := c.writer.Persist(ctx, report, 24*time.Hour); err != nil {
		return report, fmt.Errorf("persist: %w", err)
	}
	return report, nil
}

// CheckRow renders the row-centric drift verdict for ONE sampled row: re-derive
// it via the replay-aggregate bin, then byte-compare the replayed `to_jsonb -
// meta` payload against the live row's. SHARED by daily ([Checker.CheckTable])
// and monthly (full_check) so both produce the identical verdict. Per the design
// (docs/plans/2026-06-03-l3ef-integrity-checker.md):
//
//   - replay hard-error / Skippable (replay error or 0 in-bound events) → skipped
//   - replay produced NO row but had events (orphan projection row) → drifted
//   - replay found a row, byte-NOT-equal → drifted
//   - either side unparseable → skipped
//   - byte-equal → clean
//
// A hard replay run error is folded into `skipped` (never drift) — a tool that
// cannot verify a row must not report it as drifted.
func CheckRow(ctx context.Context, replayer Replayer, realityID uuid.UUID, dsn, table string, row SampledRow) (drifted bool, skipped bool) {
	// A row with no resolved owning aggregate(s) is UNVERIFIABLE (its owning
	// event was archived/pruned — the sampler emitted it with nil Owning rather
	// than failing the sweep). Skip BEFORE replay: the bin requires ≥1 aggregate.
	if len(row.Owning) == 0 {
		return false, true
	}
	res, err := replayer.Replay(ctx, replayloader.ReplayRequest{
		RealityID:       realityID,
		DSN:             dsn,
		Projection:      table,
		Owning:          row.Owning,
		BoundaryEventID: row.EventID,
		PK:              row.PK,
	})
	if err != nil {
		return false, true // hard run error → SKIP, not drift
	}
	if skip, _ := res.Skippable(); skip {
		return false, true
	}
	if !res.Found {
		// Replay ran (events > 0) but produced no row at the PK → the live
		// projection holds a row the events do not produce: an orphan DRIFT.
		return true, false
	}
	want, werr := comparator.Canonicalize(res.Payload)
	got, gerr := comparator.Canonicalize(row.Payload)
	if werr != nil || gerr != nil {
		// Either side unparseable — cannot render a verdict → SKIP.
		return false, true
	}
	return !bytes.Equal(want, got), false
}

// driftAggregateUUID is the convenience pointer for SRE (projection_drift_state.
// last_drifted_aggregate_id is a UUID column). Prefer the first owning
// aggregate's id when it is a UUID (pc/npc/region/session); fall back to the
// row's event_id (always a UUID, and SRE can join either way) for the
// non-UUID-keyed owners (e.g. the `world` aggregate behind world_kv).
func driftAggregateUUID(row SampledRow) uuid.UUID {
	if len(row.Owning) > 0 {
		if id, err := uuid.Parse(row.Owning[0].ID); err == nil {
			return id
		}
	}
	return row.EventID
}
