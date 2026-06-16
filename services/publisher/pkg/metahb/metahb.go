// Package metahb is the pgx-backed implementation of heartbeat.Writer.
//
// It upserts the publisher's liveness row into the meta DB
// `publisher_heartbeats` table (L1.A-1 §1.3). meta-worker is the sole reader;
// a stale row (no heartbeat > 30s) is flipped to 'dead' by meta-worker so the
// V2+ failover path can pick up.
package metahb

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Writer upserts the publisher heartbeat into the meta DB.
type Writer struct {
	pool *pgxpool.Pool
}

// New binds the writer to the meta DB pool.
func New(pool *pgxpool.Pool) (*Writer, error) {
	if pool == nil {
		return nil, fmt.Errorf("metahb: nil meta pool")
	}
	return &Writer{pool: pool}, nil
}

// WriteHeartbeat upserts (publisher_id, shard_host, last_heartbeat_at,
// status='active'). On every tick the row is refreshed; status returns to
// 'active' even if meta-worker had flipped it to 'dead' after a stale gap.
func (w *Writer) WriteHeartbeat(ctx context.Context, publisherID, shardHost string, now time.Time) error {
	_, err := w.pool.Exec(ctx, `
		INSERT INTO publisher_heartbeats (publisher_id, shard_host, last_heartbeat_at, status)
		VALUES ($1, $2, $3, 'active')
		ON CONFLICT (publisher_id) DO UPDATE
		SET shard_host        = EXCLUDED.shard_host,
		    last_heartbeat_at  = EXCLUDED.last_heartbeat_at,
		    status             = 'active'
	`, publisherID, shardHost, now.UTC())
	if err != nil {
		return fmt.Errorf("metahb: upsert heartbeat %s: %w", publisherID, err)
	}
	return nil
}
