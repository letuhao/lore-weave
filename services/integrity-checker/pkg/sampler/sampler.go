// Package sampler picks N random aggregate rows per projection table for
// daily-mode integrity checks (L3.E).
//
// CRITICAL: this is the L3.E sampling path ONLY. Monthly mode (L3.F) does
// NOT use a sampler — it walks ALL rows via cursor batching in pkg/full_check.
//
// Production sampler runs:
//
//	SELECT aggregate_id, aggregate_type, event_id, aggregate_version
//	FROM <table>
//	TABLESAMPLE BERNOULLI (k) REPEATABLE (random_seed)
//	LIMIT N;
//
// Cycle-15 ships an in-memory fake (RowSource interface) so the orchestrator
// can be unit-tested without a live DB. Live wiring uses pgx via the
// same RowSource interface — see D-PUBLISHER-LIVE-WIRING (deferred row).
package sampler

import (
	"context"
	"errors"
	"fmt"
	"math/rand"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// ProjectionRow is the minimal view of a projection table row that the
// sampler / comparator need. Production wires SELECTs in the per-reality
// DB to populate these; tests inject a slice via InMemRowSource.
//
// All 5 fields are populated from the row's VerificationMeta columns
// (cycle-13 0006_projections.up.sql).
type ProjectionRow struct {
	AggregateID      string
	AggregateType    string
	EventID          uuid.UUID
	AggregateVersion uint64
	// PayloadJSON is the canonical-JSON view of the projection state for
	// the comparator's byte-equal diff. Production builds this by
	// SELECTING all non-meta cols and applying jsonb_build_object; tests
	// inject directly.
	PayloadJSON []byte
}

// RowSource abstracts the projection-row reader. Implementations:
//   - InMemRowSource (tests)
//   - pgxRowSource (production, deferred to D-PUBLISHER-LIVE-WIRING)
type RowSource interface {
	// SampleRows returns up to `limit` random rows from `table` in the
	// per-reality DB identified by `realityID`. ORDER is randomized;
	// caller should not depend on stable ordering across runs.
	SampleRows(ctx context.Context, realityID uuid.UUID, table string, limit int) ([]ProjectionRow, error)
}

// Sampler is the orchestrator helper for daily mode.
type Sampler struct {
	src RowSource
	rng *rand.Rand
}

// New constructs a Sampler. `rng` is exposed so tests can pin a seed for
// determinism; production passes `rand.New(rand.NewSource(time.Now().UnixNano()))`.
func New(src RowSource, rng *rand.Rand) (*Sampler, error) {
	if src == nil {
		return nil, errors.New("sampler: RowSource nil")
	}
	if rng == nil {
		return nil, errors.New("sampler: rng nil")
	}
	return &Sampler{src: src, rng: rng}, nil
}

// SampleTable returns up to `cfg.SampleSize` AggregateRef values for
// the given table. Bounded by what the RowSource actually returns;
// if the table has fewer than SampleSize rows, returns all of them.
func (s *Sampler) SampleTable(ctx context.Context, realityID uuid.UUID, cfg types.TableConfig) ([]types.AggregateRef, error) {
	if cfg.SampleSize <= 0 {
		return nil, fmt.Errorf("sampler: SampleSize=%d for table %s (must be > 0)", cfg.SampleSize, cfg.TableName)
	}
	rows, err := s.src.SampleRows(ctx, realityID, cfg.TableName, cfg.SampleSize)
	if err != nil {
		return nil, fmt.Errorf("sampler: SampleRows table=%s: %w", cfg.TableName, err)
	}
	// Defensive: if the source doesn't shuffle (e.g. fake test source),
	// shuffle here so the daily sample isn't degenerate. Use Fisher-Yates.
	// This is a no-op extra cost on prod (rows already random).
	s.rng.Shuffle(len(rows), func(i, j int) { rows[i], rows[j] = rows[j], rows[i] })
	if len(rows) > cfg.SampleSize {
		rows = rows[:cfg.SampleSize]
	}
	out := make([]types.AggregateRef, 0, len(rows))
	for _, r := range rows {
		out = append(out, types.AggregateRef{
			RealityID:        realityID,
			AggregateType:    r.AggregateType,
			AggregateID:      r.AggregateID,
			EventID:          r.EventID,
			AggregateVersion: r.AggregateVersion,
		})
	}
	return out, nil
}

// InMemRowSource backs unit tests. Maps (reality_id, table) → all rows.
// SampleRows respects the limit but does not shuffle (Sampler.SampleTable
// shuffles); this makes the fake's behavior deterministic per-test.
type InMemRowSource struct {
	rows map[string][]ProjectionRow
}

// NewInMemRowSource returns an empty fake.
func NewInMemRowSource() *InMemRowSource {
	return &InMemRowSource{rows: make(map[string][]ProjectionRow)}
}

// AddRow appends a row for (realityID, table).
func (f *InMemRowSource) AddRow(realityID uuid.UUID, table string, row ProjectionRow) {
	key := realityID.String() + "|" + table
	f.rows[key] = append(f.rows[key], row)
}

// SampleRows returns up to `limit` rows from the fake; order is insertion.
func (f *InMemRowSource) SampleRows(_ context.Context, realityID uuid.UUID, table string, limit int) ([]ProjectionRow, error) {
	key := realityID.String() + "|" + table
	all := f.rows[key]
	if limit > len(all) {
		limit = len(all)
	}
	out := make([]ProjectionRow, limit)
	copy(out, all[:limit])
	return out, nil
}
