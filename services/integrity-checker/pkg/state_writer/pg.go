// pg.go — the production [Persister]: a pgx UPDATE against the per-reality
// `projection_drift_state` table (0007_drift_metadata). The migration seeds one
// row per L3.A table, so every sweep is an UPDATE keyed by table_name (no
// INSERT-first probe). projection_drift_state lives in the per-reality shard DB,
// so the pool IS the reality scope — realityID is used only for diagnostics.

package state_writer

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// updateDriftSQL is the per-table summary UPDATE. The nullable drift pointers
// ($5,$6) are NULL when drift_count = 0 (the schema allows NULL there). notes
// records which sweep wrote the row (daily / monthly). updated_at = NOW().
const updateDriftSQL = `
UPDATE projection_drift_state SET
    last_verified_at          = $2,
    last_sample_size          = $3,
    drift_count               = $4,
    last_drifted_aggregate_id = $5,
    last_drifted_event_id     = $6,
    expected_next_sweep_at    = $7,
    notes                     = $8,
    updated_at                = NOW()
WHERE table_name = $1`

// PgPersister UPSERTs drift summaries via pgx. Implements [Persister].
type PgPersister struct {
	pool *pgxpool.Pool
}

// NewPgPersister binds the per-reality shard pool.
func NewPgPersister(pool *pgxpool.Pool) *PgPersister { return &PgPersister{pool: pool} }

var _ Persister = (*PgPersister)(nil)

// UpdateDriftState writes one table's drift summary. A drift count of 0 stores
// NULL drift pointers; > 0 stores the convenience aggregate/event ids.
func (p *PgPersister) UpdateDriftState(
	ctx context.Context,
	realityID uuid.UUID,
	report types.DriftReport,
	expectedNextSweepAt time.Time,
) error {
	// Nullable drift pointers: nil → SQL NULL when there is no drift.
	var aggID, evID any
	if report.DriftCount > 0 {
		aggID = report.LastDriftedAggregateID
		evID = report.LastDriftedEventID
	}
	tag, err := p.pool.Exec(ctx, updateDriftSQL,
		report.TableName,    // $1
		report.CheckedAt,    // $2 last_verified_at
		report.SampleSize,   // $3
		report.DriftCount,   // $4
		aggID,               // $5 (nil when no drift)
		evID,                // $6 (nil when no drift)
		expectedNextSweepAt, // $7
		report.CheckMode,    // $8 notes
	)
	if err != nil {
		return fmt.Errorf("state_writer: update projection_drift_state table=%s reality=%s: %w", report.TableName, realityID, err)
	}
	if tag.RowsAffected() == 0 {
		// The migration seeds all 10 rows; 0 rows means the table_name is not in
		// the seeded set (a drift between types.L3ATables and 0007's allowlist).
		return fmt.Errorf("state_writer: no projection_drift_state row for table=%q (0007 seed drift?)", report.TableName)
	}
	return nil
}
