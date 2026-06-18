-- infra/scale/pgbench-event-insert.sql
--
-- S12 (Inc-1) — the RAW-POSTGRES comparator for the packing sweep.
--
-- This mirrors the spine's T2 write path (one `events` row + its `events_outbox`
-- row, committed together in one transaction) but WITHOUT any of the spine's
-- work: no Go process, no envelope validation, no event-registry check, no
-- referential/causal validation. So `pgbench` TPS here is the RAW-PG ceiling for
-- the exact two INSERTs the spine does; contrasting it against the rig's measured
-- spine emit/s yields "spine overhead over raw Postgres" — a number reviewable
-- against the wider world (spec §3 industry cross-check).
--
-- pgbench wraps each script execution in its own transaction, so the CTE below
-- is one atomic unit: the event is inserted, its generated event_id flows to the
-- outbox insert via RETURNING — identical shape to the spine's transactional
-- emit. Random aggregate_id (gen_random_uuid) keeps the events PK
-- (reality_id, aggregate_type, aggregate_id, aggregate_version, recorded_at)
-- unique across all concurrent pgbench clients with no coordination.
--
-- :rid spreads writes across a handful of reality_ids on the one shard, the way
-- a real shard holds several realities. Drive with, e.g.:
--   pgbench -n -f pgbench-event-insert.sql -c <N> -T <secs> -U foundation <shard_db>

\set rid random(1, 50)

WITH e AS (
    INSERT INTO events (
        event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
        event_type, event_version, payload, occurred_at, recorded_at
    ) VALUES (
        gen_random_uuid(),
        ('00000000-0000-0000-0000-' || lpad(:rid::text, 12, '0'))::uuid,
        'pc',
        gen_random_uuid()::text,
        1,
        'pc.moved',
        1,
        '{"x":1,"y":2}'::jsonb,
        now(),
        now()
    )
    RETURNING event_id, reality_id
)
INSERT INTO events_outbox (event_id, reality_id, published, attempts)
SELECT event_id, reality_id, FALSE, 0 FROM e;
