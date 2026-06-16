// Package migrate applies breach-notifier's schema (its OWN database — not meta, not
// per-reality). The single migration creates breach_dpo_delivery, the durable
// delivery-confirmed record. The SQL is embedded so the binary is self-contained;
// UpSQL is exported for the PG-gated store test to apply the same schema.
package migrate

import (
	"context"
	_ "embed"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed 0001_breach_dpo_delivery.up.sql
var UpSQL string

// Up applies the schema (idempotent — CREATE TABLE IF NOT EXISTS).
func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, UpSQL); err != nil {
		return fmt.Errorf("migrate: apply 0001_breach_dpo_delivery: %w", err)
	}
	return nil
}
