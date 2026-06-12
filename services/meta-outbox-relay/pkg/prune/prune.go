// Package prune is the meta-outbox-relay's published-row pruner (P2/112,
// D-META-OUTBOX-PRUNE).
//
// meta_outbox is @retention_class: ephemeral (7d hot) — once the relay has
// XADDed an event and marked the row published=TRUE, the row is spent and only
// adds storage + PII residency (114). This pruner DELETEs published rows past a
// grace window. It NEVER touches:
//   - pending rows (published=FALSE, dead_lettered_at IS NULL) — the drain owns them;
//   - dead-lettered rows (dead_lettered_at IS NOT NULL) — kept for SRE triage.
//
// The DELETE is bounded by a ctid sub-select + LIMIT so each pass holds short
// locks (mirrors retention-worker's events_outbox pruner). The relay runs
// PruneOnce on its own ticker; a prune failure is logged and retried next tick.
package prune

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Pruner DELETEs spent (published) meta_outbox rows past a grace window.
type Pruner struct {
	pool  *pgxpool.Pool
	grace time.Duration
	batch int
}

// New constructs a Pruner. grace<=0 defaults to 7d (the table's @retention_hot);
// batch<=0 defaults to 1000.
func New(pool *pgxpool.Pool, grace time.Duration, batch int) (*Pruner, error) {
	if pool == nil {
		return nil, errors.New("prune: nil pool")
	}
	if grace <= 0 {
		grace = 7 * 24 * time.Hour
	}
	if batch <= 0 {
		batch = 1000
	}
	return &Pruner{pool: pool, grace: grace, batch: batch}, nil
}

// pruneSQL deletes up to $2 published rows whose last_attempt_at (the publish
// instant) is older than the cutoff $1. ctid sub-select keeps locks bounded.
// last_attempt_at IS NOT NULL is implied by published=TRUE (the row's CHECK),
// but stated for clarity + index friendliness.
const pruneSQL = `
DELETE FROM meta_outbox
WHERE ctid IN (
    SELECT ctid FROM meta_outbox
    WHERE published = TRUE
      AND last_attempt_at IS NOT NULL
      AND last_attempt_at < $1
    ORDER BY last_attempt_at
    LIMIT $2
)
`

// PruneOnce deletes one bounded batch of spent rows, returning the row count.
// now is injected so tests are deterministic; production passes time.Now().
func (p *Pruner) PruneOnce(ctx context.Context, now time.Time) (int64, error) {
	cutoff := now.Add(-p.grace)
	tag, err := p.pool.Exec(ctx, pruneSQL, cutoff, p.batch)
	if err != nil {
		return 0, fmt.Errorf("prune: delete published meta_outbox: %w", err)
	}
	return tag.RowsAffected(), nil
}
