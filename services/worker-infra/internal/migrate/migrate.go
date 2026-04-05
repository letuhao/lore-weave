package migrate

import (
	"context"
	"log/slog"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"
)

const ddl = `
-- ── Ensure uuidv7 exists ───────────────────────────────────────
CREATE OR REPLACE FUNCTION uuidv7() RETURNS uuid AS $$
DECLARE
  ts bigint;
  bytes bytea;
BEGIN
  ts := (extract(epoch FROM clock_timestamp()) * 1000)::bigint;
  bytes := decode(lpad(to_hex(ts), 12, '0'), 'hex') || gen_random_bytes(10);
  bytes := set_byte(bytes, 6, (get_byte(bytes, 6) & x'0f'::int) | x'70'::int);
  bytes := set_byte(bytes, 8, (get_byte(bytes, 8) & x'3f'::int) | x'80'::int);
  RETURN encode(bytes, 'hex')::uuid;
END;
$$ LANGUAGE plpgsql VOLATILE;

-- ── Permanent event log ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS event_log (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  source_service TEXT NOT NULL,
  source_outbox_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  stored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(source_service, source_outbox_id)
);

CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_log_aggregate ON event_log (aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_event_log_service ON event_log (source_service, created_at DESC);

-- ── Consumer tracking ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS event_consumers (
  consumer_name TEXT NOT NULL,
  stream_name TEXT NOT NULL,
  last_processed_event_id UUID,
  last_processed_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active',
  error_message TEXT,
  PRIMARY KEY (consumer_name, stream_name)
);

-- ── Dead letter queue ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dead_letter_events (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  event_id UUID NOT NULL REFERENCES event_log(id),
  consumer_name TEXT NOT NULL,
  failure_reason TEXT NOT NULL,
  retry_count INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 5,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_unresolved ON dead_letter_events (created_at)
  WHERE resolved_at IS NULL;
`

func Up(ctx context.Context, pool *pgxpool.Pool) {
	if _, err := pool.Exec(ctx, ddl); err != nil {
		slog.Error("failed to run events schema", "error", err)
		os.Exit(1)
	}
	slog.Info("loreweave_events schema ready")
}
