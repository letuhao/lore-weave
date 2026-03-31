package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
CREATE TABLE IF NOT EXISTS sharing_policies (
  book_id UUID PRIMARY KEY,
  owner_user_id UUID NOT NULL,
  visibility TEXT NOT NULL DEFAULT 'private',
  unlisted_access_token TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sharing_visibility ON sharing_policies(visibility);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sharing_unlisted_token ON sharing_policies(unlisted_access_token) WHERE unlisted_access_token IS NOT NULL;
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
