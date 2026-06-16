package commands

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// shardReadTimeout bounds a single per-shard read so one slow (not down) shard cannot
// stall the serial fleet walk — it becomes a ReadErr instead (D1 tolerance).
const shardReadTimeout = 10 * time.Second

// PgProjectionDriftReader reads projection_drift_state fleet-wide: enumerate
// reality_registry (meta pool) → for each reality open its shard pool (via the
// injected dsnFor builder) → SELECT the projection's drift row. Per-shard read
// errors are captured into the DriftRow's ReadErr (one down shard must not fail a
// fleet-wide informational read — D1). The dsnFor seam lets prod pass buildShardDSN
// while tests inject a closure returning the test DSN.
type PgProjectionDriftReader struct {
	meta   *pgxpool.Pool
	dsnFor func(host, name string) (string, error)
}

// NewPgProjectionDriftReader binds the meta pool + a shard-DSN builder.
func NewPgProjectionDriftReader(meta *pgxpool.Pool, dsnFor func(host, name string) (string, error)) *PgProjectionDriftReader {
	return &PgProjectionDriftReader{meta: meta, dsnFor: dsnFor}
}

var _ ProjectionDriftReader = (*PgProjectionDriftReader)(nil)

type realityRoute struct {
	id   uuid.UUID
	host string
	name string
}

// DriftForProjection enumerates realities then reads each shard's drift row. A shard
// that fails to open/query yields a DriftRow with ReadErr set rather than aborting.
func (r *PgProjectionDriftReader) DriftForProjection(ctx context.Context, projectionName string) ([]DriftRow, error) {
	routes, err := r.enumerate(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]DriftRow, 0, len(routes))
	for _, rt := range routes {
		row, rerr := r.readOne(ctx, rt, projectionName)
		if rerr != nil {
			out = append(out, DriftRow{RealityID: rt.id, TableName: projectionName, ReadErr: rerr.Error()})
			continue
		}
		out = append(out, row)
	}
	return out, nil
}

func (r *PgProjectionDriftReader) enumerate(ctx context.Context) ([]realityRoute, error) {
	rows, err := r.meta.Query(ctx, `SELECT reality_id, db_host, db_name FROM reality_registry`)
	if err != nil {
		return nil, fmt.Errorf("enumerate reality_registry: %w", err)
	}
	defer rows.Close()
	var out []realityRoute
	for rows.Next() {
		var rt realityRoute
		if err := rows.Scan(&rt.id, &rt.host, &rt.name); err != nil {
			return nil, fmt.Errorf("scan reality_registry: %w", err)
		}
		out = append(out, rt)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate reality_registry: %w", err)
	}
	return out, nil
}

func (r *PgProjectionDriftReader) readOne(ctx context.Context, rt realityRoute, projectionName string) (DriftRow, error) {
	dsn, err := r.dsnFor(rt.host, rt.name)
	if err != nil {
		return DriftRow{}, fmt.Errorf("build shard DSN: %w", err)
	}
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return DriftRow{}, fmt.Errorf("open shard pool: %w", err)
	}
	defer pool.Close()

	ctx, cancel := context.WithTimeout(ctx, shardReadTimeout)
	defer cancel()

	row := DriftRow{RealityID: rt.id, TableName: projectionName}
	var notes *string
	err = pool.QueryRow(ctx,
		`SELECT last_verified_at, last_sample_size, drift_count,
		        last_drifted_aggregate_id, last_drifted_event_id,
		        expected_next_sweep_at, notes, updated_at
		   FROM projection_drift_state
		  WHERE table_name = $1`, projectionName).
		Scan(&row.LastVerifiedAt, &row.LastSampleSize, &row.DriftCount,
			&row.LastDriftedAggID, &row.LastDriftedEventID,
			&row.ExpectedNextSweep, &notes, &row.UpdatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			// Shard has no row for this projection — flagged distinctly (not folded
			// into never-verified): a missing row means 0007's seed didn't run here.
			row.MissingRow = true
			return row, nil
		}
		// A wholly-absent table (SQLSTATE 42P01 "relation does not exist" — 0007 never
		// applied on this shard) is deliberately NOT MissingRow: it surfaces as a
		// ReadErr (counted as unreachable), since the verbatim error is the actionable
		// signal and over-counting unreachable is safe for alerting.
		return DriftRow{}, fmt.Errorf("query projection_drift_state: %w", err)
	}
	if notes != nil {
		row.Notes = *notes
	}
	return row, nil
}
