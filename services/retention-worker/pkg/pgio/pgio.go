// Package pgio is the pgx-backed implementation of outbox_pruner.Deleter:
// the bounded-batch `events_outbox` prune on each per-reality DB.
//
// SAFETY (mirrors the outbox_pruner package doc + tests): only rows that are
// published=TRUE AND dead_lettered_at IS NULL AND last_attempt_at < cutoff are
// deleted. Pending rows (publisher work) and dead-lettered rows (SRE triage
// queue) are NEVER touched. `events` is NEVER touched (archive-worker's surface).
package pgio

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Deleter runs the bounded DELETE on the reality's events_outbox.
type Deleter struct {
	pools map[string]*pgxpool.Pool
}

// NewDeleter binds the reality_id → pool map.
func NewDeleter(pools map[string]*pgxpool.Pool) *Deleter {
	if pools == nil {
		pools = map[string]*pgxpool.Pool{}
	}
	return &Deleter{pools: pools}
}

// PruneOnce deletes up to batchSize eligible rows (published + un-dead-lettered
// + last_attempt_at < cutoff) in a single statement. Returns (deleted, scanned).
// The inner LIMIT selects only eligible ctids, so scanned == deleted here.
func (d *Deleter) PruneOnce(ctx context.Context, realityID uuid.UUID, cutoff time.Time, batchSize int) (int64, int64, error) {
	pool, ok := d.pools[realityID.String()]
	if !ok {
		return 0, 0, fmt.Errorf("pgio: no pool for reality %s", realityID)
	}
	var deleted int64
	err := pool.QueryRow(ctx, `
		WITH d AS (
		    DELETE FROM events_outbox
		     WHERE published = TRUE
		       AND dead_lettered_at IS NULL
		       AND last_attempt_at < $1
		       AND ctid IN (
		           SELECT ctid FROM events_outbox
		            WHERE published = TRUE
		              AND dead_lettered_at IS NULL
		              AND last_attempt_at < $1
		            LIMIT $2
		       )
		     RETURNING 1
		)
		SELECT count(*) FROM d
	`, cutoff, batchSize).Scan(&deleted)
	if err != nil {
		return 0, 0, fmt.Errorf("pgio: prune outbox reality=%s: %w", realityID, err)
	}
	return deleted, deleted, nil
}
