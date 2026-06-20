package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpConsumedTokens — chain step 0030. Backs the single-use guarantee of the
// generalized class-C confirm machinery (action_confirm.go): a confirm-token's
// jti is recorded here the first time it is redeemed, so a replay of the SAME
// token finds the row already present and is rejected (the C2 guarantee, spec
// §13.3/§13.4). `exp` lets a future janitor prune long-expired rows; correctness
// does not depend on pruning (the PK dedup is what enforces single-use).
//
// Idempotent DDL, routed through execGuarded like every other chain step.
func UpConsumedTokens(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "consumed-tokens", `
		CREATE TABLE IF NOT EXISTS consumed_tokens (
		  jti         TEXT PRIMARY KEY,
		  descriptor  TEXT NOT NULL,
		  consumed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
		  exp         TIMESTAMPTZ NOT NULL
		)`)
}
