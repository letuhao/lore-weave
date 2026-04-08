package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- uuidv7 function (same as other services)
CREATE OR REPLACE FUNCTION uuidv7() RETURNS uuid AS $$
DECLARE
  ts bigint;
  bytes bytea;
BEGIN
  ts := (extract(epoch from clock_timestamp()) * 1000)::bigint;
  bytes := decode(lpad(to_hex(ts), 12, '0'), 'hex') || gen_random_bytes(10);
  bytes := set_byte(bytes, 6, (get_byte(bytes, 6) & 15) | 112);  -- version 7
  bytes := set_byte(bytes, 8, (get_byte(bytes, 8) & 63) | 128);  -- variant 10
  RETURN encode(bytes, 'hex')::uuid;
END;
$$ LANGUAGE plpgsql VOLATILE;

CREATE TABLE IF NOT EXISTS notifications (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id    UUID NOT NULL,
  category   TEXT NOT NULL DEFAULT 'system',
  title      TEXT NOT NULL,
  body       TEXT,
  metadata   JSONB NOT NULL DEFAULT '{}',
  read_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_user_unread ON notifications(user_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notif_user_all ON notifications(user_id, created_at DESC);
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, schemaSQL)
	if err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
