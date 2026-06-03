package realityreg

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
)

// Reality is one routable per-reality database the publisher drains.
type Reality struct {
	ID     string // reality_id (UUID text)
	DBHost string // logical shard host (pg-shard-N.{env})
	DBName string // per-reality database name
}

// Querier is the subset of *pgxpool.Pool the registry needs. Lets tests
// inject a fake without a live meta DB.
type Querier interface {
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
}

// DrainableStatuses are the reality_registry statuses whose physical DB is
// live and may still hold pending outbox rows. Excluded: 'provisioning'
// (DB not migrated yet) and the terminal/archived states whose DB is gone
// ('archived','archived_verified','soft_deleted','dropped').
//
// Kept as a function (not a var) so callers can't mutate the shared slice.
func DrainableStatuses() []string {
	return []string{"seeding", "active", "pending_close", "frozen", "migrating"}
}

// ActiveRealities returns every reality whose status is drainable. Ordered
// by reality_id for deterministic iteration.
func ActiveRealities(ctx context.Context, q Querier) ([]Reality, error) {
	rows, err := q.Query(ctx, `
		SELECT reality_id::text, db_host, db_name
		FROM reality_registry
		WHERE status = ANY($1)
		ORDER BY reality_id
	`, DrainableStatuses())
	if err != nil {
		return nil, fmt.Errorf("realityreg: query reality_registry: %w", err)
	}
	defer rows.Close()

	var out []Reality
	for rows.Next() {
		var r Reality
		if err := rows.Scan(&r.ID, &r.DBHost, &r.DBName); err != nil {
			return nil, fmt.Errorf("realityreg: scan: %w", err)
		}
		out = append(out, r)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("realityreg: rows: %w", err)
	}
	return out, nil
}
