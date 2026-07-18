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

-- D-NOTIF-I18N (NOTIF-1): i18n columns so a locale-aware client can render
-- per-locale from a stable key + interpolation params. title/body remain the
-- rendered-English FALLBACK for existing consumers (never dropped). Both are
-- nullable — legacy rows and any producer that doesn't supply a key keep
-- working with the text fallback only.
--   message_key    — stable i18n key, e.g. 'notif.llm_job.completed'
--   message_params — interpolation params, e.g. {"operation":"entity_extraction"}
-- ALTER ... IF NOT EXISTS is idempotent: fresh DBs (just created above) and
-- existing DBs both converge to the same shape on every Up().
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message_key    TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message_params JSONB;

-- P2·C (NOTIF dedup): idempotency key for at-least-once producers. The AMQP
-- consumer is at-least-once (a broker redelivery after a committed INSERT but
-- lost ACK would duplicate the row); the key + partial-unique below collapses a
-- redelivery to ONE row via INSERT ... ON CONFLICT DO NOTHING. For llm_job events
-- the key is job_id:status. NULL for producers that don't set one (legacy rows,
-- ad-hoc notifications) — those keep the prior no-dedup behavior (partial index
-- ignores NULLs, so unlimited NULL-key rows are still allowed).
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS dedup_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_dedup
  ON notifications(user_id, dedup_key) WHERE dedup_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_notif_user_unread ON notifications(user_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notif_user_all ON notifications(user_id, created_at DESC);

-- P2·C (opt-out): per-user, per-category delivery preference. Per-user scope tier
-- (PK is the scope key user_id) — a user only ever sees/edits their own rows. A
-- category is delivered by DEFAULT (no row = enabled); a row with enabled=false
-- suppresses storage+push of that category for that user. Categories validate
-- against the same category.Allowed SSOT the ingress paths use.
CREATE TABLE IF NOT EXISTS notification_preferences (
  user_id    UUID    NOT NULL,
  category   TEXT    NOT NULL,
  enabled    BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, category)
);

-- M5 (D-MOB-4 push delivery). One row per DEVICE push subscription. The Web Push endpoint URL IS
-- the device key (a browser mints a distinct endpoint per install), so multi-device = multiple
-- rows; UNIQUE(owner_user_id, endpoint) makes registration an idempotent upsert (§8-S1/H4). Per-user
-- scope tier (owner_user_id) — a user only ever sees/mutates their own subscriptions. p256dh+auth are
-- the subscription's public key material used to ENCRYPT the payload (not secrets — they're the
-- recipient's public keys). fail_count/last_success_at drive the stale-sweep GC; a 404/410 on send
-- hard-deletes the row (the primary GC, §8-B3).
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id   UUID NOT NULL,
  endpoint        TEXT NOT NULL,
  p256dh          TEXT NOT NULL,
  auth            TEXT NOT NULL,
  ua              TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_success_at TIMESTAMPTZ,
  fail_count      INT NOT NULL DEFAULT 0,
  UNIQUE (owner_user_id, endpoint)
);
CREATE INDEX IF NOT EXISTS idx_push_sub_owner ON push_subscriptions(owner_user_id);

-- M5 (§8-H1/H3). The PUSH channel preference, keyed by push_topic (the 7 user-facing toggles, NOT
-- the 9 raw categories — the sender maps category+message_key → topic). Per-user scope tier. A topic
-- with NO row uses its code default (social off, everything else on); a row overrides it. This is a
-- SEPARATE dimension from notification_preferences (which governs in-app storage): a user can keep a
-- category in the feed while silencing its buzz.
CREATE TABLE IF NOT EXISTS push_preferences (
  user_id      UUID    NOT NULL,
  push_topic   TEXT    NOT NULL,
  push_enabled BOOLEAN NOT NULL,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, push_topic)
);
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, schemaSQL)
	if err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
