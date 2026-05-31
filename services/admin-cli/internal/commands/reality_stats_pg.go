package commands

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PgRealityStatsReader reads reality_registry (read-only) for `reality stats`.
type PgRealityStatsReader struct {
	pool *pgxpool.Pool
}

// NewPgRealityStatsReader binds the meta pool (caller-owned).
func NewPgRealityStatsReader(pool *pgxpool.Pool) *PgRealityStatsReader {
	return &PgRealityStatsReader{pool: pool}
}

var _ RealityStatsReader = (*PgRealityStatsReader)(nil)

// ReadRealityStats SELECTs one reality_registry row. ErrRealityNotFound on miss.
func (r *PgRealityStatsReader) ReadRealityStats(ctx context.Context, realityID uuid.UUID) (*RealityStats, error) {
	s := &RealityStats{RealityID: realityID}
	var closeReason *string
	err := r.pool.QueryRow(ctx,
		`SELECT status, status_transition_at, locale, deploy_cohort,
		        session_max_pcs, session_max_npcs, session_max_total,
		        last_stats_updated_at, close_initiated_at, close_reason,
		        archive_verified_at, drop_scheduled_at
		   FROM reality_registry
		  WHERE reality_id = $1`,
		realityID,
	).Scan(&s.Status, &s.StatusTransitionAt, &s.Locale, &s.DeployCohort,
		&s.SessionMaxPCs, &s.SessionMaxNPCs, &s.SessionMaxTotal,
		&s.LastStatsUpdatedAt, &s.CloseInitiatedAt, &closeReason,
		&s.ArchiveVerifiedAt, &s.DropScheduledAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrRealityNotFound
		}
		return nil, fmt.Errorf("read reality_registry %s: %w", realityID, err)
	}
	if closeReason != nil {
		s.CloseReason = *closeReason
	}
	return s, nil
}
