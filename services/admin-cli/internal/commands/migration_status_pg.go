package commands

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PgMigrationStatusReader summarizes instance_schema_migrations (read-only),
// one row per reality. failure_reason IS NOT NULL counts a failed application;
// migration_id is zero-padded (NNN_*) so max() is the latest.
type PgMigrationStatusReader struct {
	pool *pgxpool.Pool
}

// NewPgMigrationStatusReader binds the meta pool (caller-owned).
func NewPgMigrationStatusReader(pool *pgxpool.Pool) *PgMigrationStatusReader {
	return &PgMigrationStatusReader{pool: pool}
}

var _ MigrationStatusReader = (*PgMigrationStatusReader)(nil)

// ListMigrationStatus returns the per-reality migration summary.
func (r *PgMigrationStatusReader) ListMigrationStatus(ctx context.Context) ([]MigrationStatusRow, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT reality_id,
		        COUNT(*),
		        COUNT(*) FILTER (WHERE failure_reason IS NOT NULL),
		        MAX(migration_id),
		        MAX(applied_at)
		   FROM instance_schema_migrations
		  GROUP BY reality_id`)
	if err != nil {
		return nil, fmt.Errorf("query instance_schema_migrations: %w", err)
	}
	defer rows.Close()
	var out []MigrationStatusRow
	for rows.Next() {
		var m MigrationStatusRow
		if err := rows.Scan(&m.RealityID, &m.Applied, &m.Failures, &m.LatestMigration, &m.LatestAppliedAt); err != nil {
			return nil, fmt.Errorf("scan migration status: %w", err)
		}
		out = append(out, m)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate migration status: %w", err)
	}
	return out, nil
}
