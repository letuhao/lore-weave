# P1 / DEFERRED 069 (partial) — meta-worker consumer live-wiring

> **Task size:** XL (publisher fanout extension + meta-worker pgx/redis adapters
> + new meta migration + end-to-end live-smoke). **Mode:** full human-in-loop.
> **Branch:** `mmo-rpg/foundation-mega-task`. Advances `DEFERRED.md` row **069**
> (meta-worker portion); builds on the publisher (054, ADDRESSED).

## 1. Goal

Live-wire the **meta-worker** (L2.L sole xreality consumer) so the canon
fan-out path runs end-to-end on docker-compose:

```
glossary canon.entry.* (cross_reality) → events_outbox
  → publisher drain → XADD xreality.book.canon.updated (inner event_type kept)
  → meta-worker XREADGROUP → dispatch by inner event_type → canon_writer
  → UPSERT per-reality canon_projection (for each subscribing reality) + audit
```

Closes the "emit→publish→consume→project" 4/5 of the P1 exit gate. The 5th step
(integrity-checker drift verify) stays deferred (blocked on the AggregateLoader
= Rust `dp_kernel::load_aggregate` rebuild path — its own task).

## 2. Operator decisions (locked 2026-05-30)

- **Ingress = also build the publisher wrapping.** Extend `xreality_fanout` so
  `canon.*` / `admin.canon.override.*` rows map to the topic
  `xreality.book.canon.updated` while the envelope `event_type` field keeps the
  INNER type (`canon.entry.created` …) the dispatcher routes on. True
  publisher→meta-worker→projection smoke (not a stream-injected shortcut).
- **Subscribers = build the book↔reality subscription table.** New meta
  migration `book_reality_subscription (book_id, reality_id)`;
  `SubscribersForBook` reads it (joined to `reality_registry` status
  active/frozen) — precise per-book fan-out, not all-active.

## 3. Existing surface (verified)

- meta-worker has REAL writers behind interfaces: `canon_writer` (4
  `canon.entry.*` → `canon_projection`), `user_erased_writer`,
  `force_propagate`, `canon_history_writer`, `l1_conflict_*` — but `cmd/main.go`
  + dispatcher use SKELETON echo handlers. THIS task wires `canon_writer` only.
- `pkg/consumer` is the XREADGROUP loop behind a `MessageSource` interface
  (`Read`/`Ack`) — needs a real go-redis impl.
- `pkg/dispatch` routes by inner `event_type`; allowlist already permits
  `canon.entry.*` (I7-compliant: only ingress is the xreality.* stream).
- Schema: `canon_projection` (per_reality 0009 — PK canon_entry_id, requires
  VerificationMeta `event_id`+`aggregate_version` NOT NULL, origin XOR
  source_event_id/cascaded_from_reality_id, layer/lock_level CHECKs),
  `reality_registry` (meta 001), events_outbox/events (publisher path).
- `canon_writer.UpsertIntent` lacks `event_id`+`aggregate_version` → must extend
  (canon_projection requires them NOT NULL).

## 4. Design

### 4.1 publisher `xreality_fanout` (re-touch 054 code)
`TopicFor` becomes topic-mapping:
- `xreality.<a>.<b>` → itself (3-part, unchanged — existing tests pass).
- `canon.*`, `admin.canon.override.*`, `canon.change.*` → `xreality.book.canon.updated`.
- else → `ErrInvalidEventType`.
Fields still carry `event_type = row.EventType` (inner). Add the canon fan-out
topic constant; add a registry note. Existing `Fanout` gating
(`row.CrossReality()`) unchanged. Update `xreality_fanout_test.go` +
`xreality_propagation_test.go` accordingly.

### 4.2 meta migration `book_reality_subscription`
`migrations/meta/006_book_reality_subscription.up.sql`:
```sql
CREATE TABLE book_reality_subscription (
  book_id UUID NOT NULL, reality_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (book_id, reality_id));
CREATE INDEX ... ON (book_id);
```

### 4.3 canon_writer `UpsertIntent` extension (pure-lib)
Add `EventID uuid.UUID` + `AggregateVersion uint64`. `decodeCanonPayload` reads
`aggregate_version` from the envelope; `Handle` threads both into the intent.
Keep `SourceEventID` (own-source). Update `writer_test.go`.

### 4.4 meta-worker adapters (new `pkg/pgwrite` + `pkg/redisconsume`)
- `PgCanonDB.UpsertCanon` → `INSERT … ON CONFLICT (canon_entry_id) DO UPDATE`
  on the subscriber reality's pool (source_event_id + event_id +
  aggregate_version + last_synced_at=NOW()).
- `PgSubscribers.SubscribersForBook` → meta pool query on
  `book_reality_subscription ⨝ reality_registry`.
- `PgAudit.WriteAudit` → meta `service_to_service_audit` (Q-L1A-3) — confirm
  table at build; fall back to a focused audit row.
- `RedisSource` → go-redis `XReadGroup` (group `meta-worker`, consumer id) +
  `XAck`; satisfies `consumer.MessageSource`.

### 4.5 meta-worker `cmd/main.go`
Fail-closed env config (META_DB_URL, REDIS_URL, shard creds + override,
CANON_STREAM default `xreality.book.canon.updated`, consumer group/id). Boot:
meta pool → per-reality pools (reused resolver pattern; reuse publisher's
`realityreg` OR a local resolver) → redis (XGROUP CREATE MKSTREAM) → dispatcher
register canon_writer.Handle for the 4 types → consumer loop → graceful
shutdown → /healthz+/readyz+/metrics (dispatch counters + lag).

### 4.6 live-smoke (`tests/integration/metaworker_live_smoke_test.go`)
`//go:build integration`, env `LW_INTEGRATION_DB` (a per-reality DB used as BOTH
the source-reality outbox DB and the subscriber canon_projection DB for the
smoke) + `LW_INTEGRATION_META_DB` + `LW_INTEGRATION_REDIS`. Steps: apply
migrations (per-reality 0002+0005+0009; meta 001+006); seed a `canon.entry.created`
event+outbox row (cross_reality) + a `book_reality_subscription` row; run the
publisher Loop once (drain→XADD `xreality.book.canon.updated`); run the
meta-worker consumer `ProcessOne` (XREADGROUP→canon_writer→UpsertCanon); assert
a `canon_projection` row exists for the subscriber reality with the right
canon_entry_id/book_id/layer/source_event_id. Bootstrap
`scripts/metaworker-live-smoke.sh`.

### 4.7 CI
`foundation-ci.yml` db-smoke: add a meta DB + the meta-worker live-smoke step.

## 5. Risks / follow-ups (track in DEFERRED)
- Other meta-worker writers (user_erased/force_propagate/canon_history/
  l1_conflict) still skeleton — follow-up.
- integrity-checker drift verify still blocked (AggregateLoader) — follow-up.
- canon cascade read-through + L3-override (cascaded_from_reality_id /
  overridden_by_l3_event_id) NOT written by this path — own-source only.
- glossary-service is the real producer of canon.entry.* (Q-L5A-1 separate
  sub-program) — the smoke seeds the outbox directly.

## 6. Exit gate
meta-worker build+vet+test green · end-to-end live-smoke (publisher→meta-worker
→canon_projection) asserts on foundation-dev · CI wired · `DEFERRED.md` 069
annotated (meta-worker canon path done; remainder tracked) · SESSION_PATCH.
