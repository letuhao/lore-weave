# A4 — Shipped Event Machinery: a measured inventory

Repo: `D:\Works\source\lore-weave-game-foundation`, branch `feat/game-logic`, 2026-08-02.
Scope: CODE and CONTRACTS only. Design docs are covered by sibling agents.

**Method note that changes results.** `.claude/worktrees/` contains three full copies of the
repository (sibling agents' worktrees). Every naive repo-wide grep returns 4× duplicated hits and
inflates "this exists in many places" into a false signal. All counts below exclude
`.claude/`, `target/`, `node_modules/`. Separately, `rg` invoked through the Bash tool returned
**zero hits for tokens that demonstrably exist** (`causation_id` in a file I had just read); every
absence claim in this report was therefore re-established with `grep -rIn`, not `rg`.

---

## PART 1 — THE INVENTORY TABLE

"Production call site" = a non-test, non-example, non-benchmark, non-drill invocation reachable from
a deployed entrypoint.

### Contracts / schema layer

| component | path | LOC | what it does | production call sites | verdict |
|---|---|---|---|---|---|
| Event registry | `contracts/events/_registry.yaml` | 222 | Declares **15 event types / 16 (type,version) pairs**. Per entry: `name`, `aggregate`, `versions`, `active_version`, `go_struct`, `description`, `shipped_cycle`, `owner`, optional `cross_reality`, `deprecations{deprecated_at,retire_after,upcaster_to}` | Loaded by `LoadRegistry` (`registry.go:69`); **0** non-test callers | **built + unwired** |
| Registry loader | `contracts/events/registry.go` | ~200 | `LoadRegistry`/`ParseRegistry`/`Lookup`/`IsDeprecated` | 0 outside `registry_test.go` | built + unwired |
| Go envelope | `contracts/events/envelope.go` | 119 | The canonical wire shape + `Validate()` | struct is mirrored, not called | built + unwired |
| Schema validator (Go) | `contracts/events/validators_go/validator.go` | — | Payload validation against registry | **0**. Grep for `validators_go\|events.Validate\|ValidateEnvelope` over `--include=*.go` returns 2 hits, both **comments** (`doc.go:38`, `envelope.go:90`) | **built + unwired** |
| Upcasters (Go) | `contracts/events/upcasters_go/` | 5 files | `npc_said_v1_to_v2.go` + registry + S4 conformance test | 0 non-test | built + unwired |
| Generated types | `contracts/events/generated/{rust,ts,python}/` + `registry_generated.go` | 16 files × 3 langs | Per-(type,version) structs | **0 importers in any language.** Greps for `events/generated`, `generated::rust`, `events.generated` over crates/services/frontends → 0 | **built + unwired** |
| Snapshot policy | `contracts/events/snapshot_policy.yaml` | 40+ | Opt-in snapshot cadence | `policies:` list is **EMPTY**; grep `snapshot_policy` over rs/go/py/sh → **0 readers** | **inert config** |
| Retention classes | `contracts/retention/event_classes.yaml` | 69 | 4 classes (`canon_events`, `volatile_npc`, `audit`, `broadcast`), 5-entry `event_type_map` | **0 consumers.** Only hits are itself, 3 docs, and one Go *comment* (`retention-worker/pkg/types/types.go:30`) | **inert config** |
| Meta allowlist | `contracts/meta/events_allowlist.yaml` | 228 | **A SECOND event registry** — 21 distinct `event_name`s on the meta/control plane | Consumed by MetaWrite + `scripts/outbox-event-emit-lint.sh` | built + wired |

### Rust kernel — `crates/dp-kernel` (15,095 LOC total, 32 modules)

| component | path | LOC | what it does | production call sites | verdict |
|---|---|---|---|---|---|
| `EventEnvelope` | `src/envelope.rs` | 249 | Wire shape, field-for-field mirror of the Go envelope; `validate()` | used by every module below | built + wired (as a type) |
| `Event` trait | `src/event.rs` | 298 | Domain→envelope conversion | blanket impl only | built + unwired |
| `EventMetadata` | `src/metadata.rs` | 182 | Typed metadata: `actor`, `causation_id`, `correlation_id`, `source`, `occurred_at`, `instance_clock_tick`, `extra` | **0** — see Part 3 | **built + unwired** |
| `EventStore` trait | `src/event_store.rs` | 597 | `append_events`/`read_stream`/`snapshot_write`/`snapshot_read` + shared test suite + `InMemoryEventStore` | trait def + in-memory test impl | built + unwired |
| `PgEventStore` | `src/event_store_pg.rs` | 550 | The Postgres impl; optimistic CC via `MAX(aggregate_version)`; `MetaFreezeGuard` | **0.** Only refs: `examples/g1_append_stmt.rs:193` (bite-test), `tests/integration_event_store.rs:71`, `world-service/src/bin/freeze_drill.rs:82,125` (a drill that **creates its own minimal events table**, `:166`) | **built + unwired** |
| `ChannelWriter` | `src/channel.rs` | 361 | **The real write path.** CAS-fenced allocate + insert event + index + outbox in ONE tx | **1**: `commit-service/src/epoch_commit.rs:243`, via `manager.rs:59`. Others are `bin/spine.rs`, `bin/ceilings.rs` (CLI drill + benchmark) | built + wired *into an undeployed service* |
| Event validator | `src/event_validator.rs` | 381 | `ValidatorRegistry::validate(event_type, version, payload)`, `knows()` | **0.** Only `lib.rs:114` (`pub mod`) and `lib.rs:138` (re-export). **Neither INSERT path calls it** | **built + unwired** |
| `load_aggregate` | `src/load_aggregate.rs` | 607 | Snapshot + delta fold | 0 non-test | built + unwired |
| Snapshots | `src/snapshot.rs` / `src/snapshot_cache.rs` | 201 / 258 | `SnapshotRecord`, `SnapshotCache` | `snapshot_write`/`snapshot_read` appear **only** in `event_store.rs` + `event_store_pg.rs` (trait + impl). 0 callers | **built + unwired** |
| Upcaster | `src/upcaster.rs` | 319 | Version migration chain | **not in the read path** — grep `upcast` over `load_aggregate.rs`, `event_store_pg.rs`, `rebuilder/src/lib.rs`, `world-service/src/rebuild/*.rs` → **0 hits** | built + unwired |
| `Projection` trait | `src/projection.rs` | 459 | `ProjectionRunner`, fold contract | used by projections crates + rebuilder | built + wired |
| Outbox | `src/outbox.rs` | 257 | `insert_sql()` → `INSERT INTO events_outbox (event_id, reality_id)` | 1: `channel.rs` step 4 | built + wired |
| Canon cache | `src/canon_cache.rs` | 1018 | `CanonGuardrail` trait | `crates/contracts-prompt/src/canon_guardrail.rs` | built + wired |

### Fold / replay

| component | path | what it does | production call sites | verdict |
|---|---|---|---|---|
| Projection crates | `crates/projections/{canon,npc,pc,region,session,world_kv}` | 6 fold implementations | declared in `world-service/Cargo.toml:104-109`; driven by `ProjectionRunner` | built + wired into an undeployed service |
| `rebuilder` | `crates/rebuilder/` | Replay driver + checkpoint | `world-service/src/bin/rebuilder.rs`, `bin/replay-aggregate.rs`, `src/rebuild/global.rs` | built + wired into an undeployed service |
| Golden vectors | `crates/projection-golden/tests/golden.rs` | Golden-vector oracle | test-only (that is correct for an oracle) | built + wired (as a test) |
| Reference diff | `crates/projection-reference/tests/diff.rs` | Differential oracle | test-only | built + wired (as a test) |

### Services

| component | path | LOC | what it does | wired? | verdict |
|---|---|---|---|---|---|
| commit-service | `services/commit-service/src/` | 4,882 | Proposal ingress (`bus.rs` Redis Streams consumer), admission/dedup (`admission.rs`), producer identity MAC (`producer.rs`), epoch commit (`epoch_commit.rs`) | `main.rs` is a **POC turn runner**, not a server. **Absent from `infra/docker-compose.yml`** | built + undeployed |
| world-service | `services/world-service/src/main.rs` | 22 | `fn main()` **prints a scaffold message** and exits | absent from compose | **stub main** |
| roleplay-service | `services/roleplay-service/` | — | HTTP router; **deployed** (compose :2018) | grep `dp_kernel\|EventStore\|EventEnvelope\|events` over its `src/` → **0 hits** | deployed, **touches no events** |
| game-server | `services/game-server/src/` | 2,951 | Colyseus 0.17; `ChannelRoom.ts` (492) reads `lw.events.<reality>` via XREAD, folds, broadcasts `turn.outcome`; XADDs proposals | server deployed (compose :2055, `--profile game`); **`ChannelRoom` throws without `LW_CHANNEL_REALITY_ID`, set nowhere** (`grep -rn "LW_CHANNEL" infra/ scripts/ .github/` → 0) | `echo` room wired; **`channel` room built + unconfigured** |
| frontend-game | `frontend-game/src/` | — | `channel-client.ts:64` joins `'channel'` | `ChannelPanel.tsx` has **zero importers**; `play.tsx` mounts `EchoPanel` | built + unmounted |
| publisher | `services/publisher/` | — | Drains `events_outbox` `FOR UPDATE SKIP LOCKED` → Redis Streams | k8s manifest exists; **no Dockerfile**, absent from compose | built + partially wired |
| archive-worker | `services/archive-worker/` | — | Parquet+ZSTD → MinIO, then `DETACH` + `DROP TABLE` partition | k8s manifest; no Dockerfile; absent from compose | built + partially wired |
| retention-worker | `services/retention-worker/` | — | Outbox prune + audit cron; **snapshot pruner returns zeros** (`snapshot_pruner.go:38-40`) | k8s manifest; no Dockerfile; absent from compose | built, one stub step |
| meta-outbox-relay | `services/meta-outbox-relay/` | — | Drains `meta_outbox` → `lw.meta.events` + xreality topic | `grep -rn "meta-outbox-relay" infra/ --include=*.yaml` → **0** | **built + unwired** |

**The headline.** Of 48 services in `infra/docker-compose.yml`, the ones that touch the event store —
`commit-service`, `world-service`, `publisher`, `archive-worker`, `retention-worker`,
`meta-outbox-relay` — are **all absent**. The two deployed Rust game services are `tilemap-service`
and `roleplay-service`, and `roleplay-service` contains zero references to events. **No deployed
process currently writes to or reads from the `events` table.**

---

## PART 2 — THE EVENT RECORD AS IT ACTUALLY EXISTS TODAY

### 2a. The stored row: `events`, 19 columns

Base table `contracts/migrations/per_reality/0002_events_table.up.sql:64-101`, then ALTERed by
`0013`, `0014`, `0016`. `0001_initial.up.sql:38-49` created an **earlier, different** skeleton
(`event_name`, no `reality_id`) which `0002:60-61` explicitly `DROP`s — do not mistake it for the
current shape.

| # | column | type | null? | default | defined at | written by |
|---|---|---|---|---|---|---|
| 1 | `event_id` | `UUID` | NOT NULL | — | `0002:66` | both paths |
| 2 | `reality_id` | `UUID` | NOT NULL | — | `0002:68` | both |
| 3 | `aggregate_type` | `TEXT` | NOT NULL | — | `0002:69` | both |
| 4 | `aggregate_id` | `TEXT` | NOT NULL | — | `0002:70` | both |
| 5 | `aggregate_version` | `BIGINT` | NOT NULL | — | `0002:71` | both |
| 6 | `event_type` | `TEXT` | NOT NULL | — | `0002:73` | both |
| 7 | `event_version` | `INTEGER` | NOT NULL | `1` | `0002:74` | both |
| 8 | `payload` | `JSONB` | NOT NULL | — | `0002:76` | both |
| 9 | `metadata` | `JSONB` | nullable | — | `0002:77` | both |
| 10 | `occurred_at` | `TIMESTAMPTZ` | NOT NULL | — | `0002:79` | both |
| 11 | `recorded_at` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | `0002:80` | both |
| 12 | `audit_ref` | `UUID` | nullable | — | `0002:83` | **NEITHER — always NULL** |
| 13 | `registry_version` | `INTEGER` | nullable | — | `0002:87` | **NEITHER — always NULL** |
| 14 | `content_sha256` | `CHAR(64)` | nullable | — | `0013:41` | both (computed in SQL) |
| 15 | `channel_id` | `BIGINT` | nullable | — | `0014:17` | ChannelWriter only |
| 16 | `channel_event_id` | `BIGINT` | nullable | — | `0014:18` | ChannelWriter only |
| 17 | `writer_epoch` | `BIGINT` | nullable | — | `0014:19` | ChannelWriter only |
| 18 | `causal_refs` | `JSONB` | **NOT NULL** | `'[]'::jsonb` | `0014:20` | ChannelWriter — **always `[]`** |
| 19 | `ruleset_digest` | `CHAR(64)` | nullable | — | `0016:51` | both |

Constraints: `events_payload_is_object`, `events_metadata_is_object_or_null`,
`events_aggregate_version_pos`, `events_event_version_pos` (`0002:89-95`).
PK `(reality_id, aggregate_type, aggregate_id, aggregate_version, recorded_at)` (`0002:100`).
`PARTITION BY RANGE (recorded_at)`, monthly (`0002:101`). `payload`/`metadata` lz4 (`0002:106-114`).

**Two columns are dead.** `audit_ref` and `registry_version` appear in neither INSERT
(`event_store_pg.rs:251-265`, `channel.rs:166-172`). `registry_version` was designed to record which
schema version validated the row — it is NULL for every row because the validator never runs (Part 4 §1).

### 2b. The in-memory shape: 12 fields, mirrored in two languages

Go `contracts/events/envelope.go:45-58` and Rust `crates/dp-kernel/src/envelope.rs:46-76` are
field-for-field identical:

| field | Go type | Rust type | Go line | Rust line |
|---|---|---|---|---|
| `event_id` | `uuid.UUID` | `Uuid` | `envelope.go:46` | `envelope.rs:47` |
| `event_type` | `string` | `String` | `:47` | `:48` |
| `event_version` | `uint32` | `u32` | `:48` | `:49` |
| `aggregate_id` | `string` | `String` | `:49` | `:50` |
| `aggregate_type` | `string` | `String` | `:50` | `:51` |
| `aggregate_version` | `uint64` | `u64` | `:51` | `:52` |
| `reality_id` | `uuid.UUID` | `Uuid` | `:52` | `:53` |
| `occurred_at` | `time.Time` | `Rfc3339Timestamp` (= `String`) | `:53` | `:54` |
| `recorded_at` | `time.Time` | `Rfc3339Timestamp` | `:54` | `:55` |
| `payload` | `map[string]any` | `serde_json::Value` | `:55` | `:56` |
| `metadata` | `map[string]any` (omitempty) | `Option<Value>` | `:56` | `:58` |
| `ruleset_digest` | `string` (omitempty) | `Option<String>` | `:57` | `:75` |

**There is no `channel_id`, `channel_event_id`, `writer_epoch`, `causal_refs`, `content_sha256`,
`audit_ref`, or `registry_version` on the envelope.** Those 7 columns are supplied at the SQL
boundary by the writer, not carried by the event object. The envelope is a strict *subset* of the row.

`Validate()` (`envelope.go:91-118`, `envelope.rs:81-113`) checks 7 presence rules + one format rule
(`ruleset_digest` must be 64 lowercase hex when present — `envelope.go:114`, `envelope.rs:86-90`).
It does **not** consult the registry, so an unregistered `event_type` passes.

### 2c. The typed metadata blob — defined, never populated

`crates/dp-kernel/src/metadata.rs:52-84`: `actor` (`:54`), `causation_id: Option<Uuid>` (`:57`),
`correlation_id: Option<Uuid>` (`:61`), `source` (`:65`), `occurred_at` (`:69`),
`instance_clock_tick` (`:73`), `extra: Map<String,Value>` flattened (`:81`).

### 2d. The wire shape a client actually receives — 4 fields

`services/game-server/src/rooms/ChannelRoom.ts:84-96` (`parseEnvelope`) reads a flat Redis field
array and keeps exactly: `event_type`, `channel_event_id`, `payload`, `metadata`
(type at `src/wire/turnOutcome.ts:57-62`). `reality_id`, `aggregate_*`, `occurred_at`,
`recorded_at`, `ruleset_digest`, `causal_refs` are parsed into a bag and **dropped**. Its only
validation is `if (!bag.event_type) throw` (`:87`).

### 2e. The three write shapes, side by side

| | envelope (Go/Rust) | `PgEventStore::append_events` | `ChannelWriter::append` |
|---|---|---|---|
| fields/columns | 12 | 13 | 17 |
| site | `envelope.go:45` | `event_store_pg.rs:251-265` | `channel.rs:166-172` |
| ordering | `aggregate_version` | `aggregate_version` (CC vs `MAX()`, `:210-234`) | `channel_event_id` from CAS (`:129-140`) |
| outbox row | — | **no** | **yes**, same tx (`channel.rs:212-217`) |
| production callers | n/a | **0** | 1 (`epoch_commit.rs:243`) |

The two paths write **different column sets into the same table**. A row written by `PgEventStore`
has NULL `channel_id`/`channel_event_id`/`writer_epoch` and `causal_refs = '[]'` (the DDL default),
and gets **no outbox row** — so it is never published and never reaches a client.

---

## PART 3 — THE CAUSALITY GAP, MEASURED

**Is there any code path today where committing event A causes event B to be produced? No.**
Not one. The *slots* for causality exist in three places; all three are empty.

### 3.1 `causation_id` — defined, written by nothing

`grep -rIn --exclude-dir=.claude --exclude-dir=target "causation_id" crates services contracts`
returns **5 lines, total**:

```
crates/dp-kernel/src/metadata.rs:16   //!   * `causation_id` — the event id that immediately caused this one
crates/dp-kernel/src/metadata.rs:57       pub causation_id: Option<Uuid>,
crates/dp-kernel/src/metadata.rs:111          && self.causation_id.is_none()
crates/dp-kernel/src/metadata.rs:140          causation_id: Some(Uuid::from_u128(1)),
contracts/migrations/per_reality/0001_initial.up.sql:47   --   correlation_id, causation_id, actor_type/id, etc.
```

Line 57 is the declaration, 111 is `is_empty()`, **140 is inside `mod tests`**, and the SQL line is a
comment in a table that `0002:61` drops. There is **one** assignment of `causation_id` in the entire
repository and it is in the field's own unit test. `correlation_id` is the same story — its 6
non-doc files are `provider-registry-service` LLM-usage relay and `alert-recorder`, unrelated rails.

### 3.2 `causal_refs` — a column, plumbed end to end, always `[]`

This is the one that looks alive. It is not. The column exists
(`0014_channel_ordering.up.sql:20`, `JSONB NOT NULL DEFAULT '[]'::jsonb`), `ChannelWriter::append`
takes it as a parameter (`channel.rs:122`) and binds it (`channel.rs:195`). But **every call site in
the repository passes the empty array**:

```
services/commit-service/src/epoch_commit.rs:243   writer.append(&env, &serde_json::json!([])).await?
services/commit-service/src/bin/spine.rs:308      writer.append(&env, &serde_json::json!([])).await?
services/commit-service/src/bin/spine.rs:396      writer.append(&env, &serde_json::json!([])).await?
services/commit-service/src/bin/ceilings.rs:346   let refs = serde_json::json!([]);   → used :352, :362
services/commit-service/src/bin/ceilings.rs:414   let refs = serde_json::json!([]);   → used :419
```

Establishing grep: `grep -rIn "causal_refs" crates services contracts` → **5 lines** (3 in
`channel.rs`, 2 in the migration up/down). No producer, no reader, no query. Nothing anywhere
*reads* `causal_refs` back — no SELECT in the repo names it.

### 3.3 `IslandMessage.causality` — the closest thing, and it is a test fixture

`crates/sim-core/src/types.rs:259-266` defines a cross-island message carrying
`causality: Seq` (`:263`, "Sender's `Seq` at emission — causal (not total) order for audit").
`Island::deliver` (`island/mod.rs:180`) accepts one. `Realm::send`/`tick_all`
(`crates/sim/src/realm.rs:60`, `:66-89`) route it with +1-tick latency and dead-letter the
undeliverable.

But **`Island::step()` returns `StepStatus` and nothing else** (`island/mod.rs:267-282`) — applying
an input cannot emit a message. An `IslandMessage` must be constructed by an outside caller, and the
only non-test construction in the repo is `crates/sim/src/bin/stress.rs:190`, a stress binary.
`realm.rs:1-12` says so itself: it is "the in-process reference implementation", and
"`commit-service` (S3) owns the production equivalent" — `grep -rIn "Realm" services --include=*.rs`
returns **0 hits in commit-service**. The production router does not exist.
Further, `island/mod.rs:175` notes `from`/`causality` are **not retained** on delivery.

### 3.4 Nothing trigger-shaped exists anywhere else

Token sweep over `crates/` + `contracts/` (files containing, worktrees excluded):
`CausalRef` **0** · `reaction` **0** · `causation_id` 2 · `correlation_id` 6 (all unrelated rails) ·
`cascade` 27 · `trigger` 64 · `dispatch` 47 · `subscribe` 16 · `wave` 2.

The large counts are noise, and I checked them rather than assuming. Every `trigger` identifier in
`crates/` is one of: `scale_trigger` — a Kubernetes autoscaling **config string**
(`dp-kernel/src/capacity.rs:53,191,329`); `invalidation_trigger` — a cache-config string
(`meta-rs/src/cache.rs:71,228`); the enum variant `AdminTriggered` (`dp-kernel/src/prompt.rs:69`);
and one test name (`world-gen/src/flat_climate.rs:1745`). The sibling sweep over `game-server` +
`contracts/{ws,game-wire,notifyevent,turn}` found `trigger` **0**, `causation` **0**,
`cascade` **0**, `reaction` **0**; its 31 `emit` hits are a private structured-logging function
(`game-server/src/log.ts:14`) and an audit sink; `dispatch` has **no identifier at all**, only 3
comments.

`world.tick` — the registered heartbeat that would be the natural autonomous event source — has **no
producer**. Its only occurrences are dp-kernel doc comments and test fixtures
(`aggregate.rs:71,99`, `envelope.rs:179`, `event.rs:156-187`, `projection.rs:265-276`). No
scheduler, no cron, no tick loop emits it.

### 3.5 What the one real chain actually looks like

There *is* a pipeline, and it is worth stating precisely because it is easy to mistake for causality:

```
client turn.submit  (game-server ChannelRoom.ts:250)
  → XADD reality:<r>:cell:<c>:proposals            (ChannelRoom.ts:351-355)
  → commit-service bus.rs XREADGROUP               (Redis Streams consumer)
  → admission.rs (dedup) → epoch_commit.rs
  → ChannelWriter::append → events + channel_event_index + events_outbox  (one tx)
  → publisher drains outbox FOR UPDATE SKIP LOCKED → XADD lw.events.<reality>
  → game-server XREAD → fold → broadcast turn.outcome
```

That is **request → commit → notify**: one external stimulus producing one event and one
notification. It is not event-chaining. No step in it reads a committed event and decides to write a
*new* one. `meta-outbox-relay/pkg/drain/drain.go` only XADDs (grep
`INSERT INTO events` over `services/meta-outbox-relay/` → **0 hits**), and projections write
read-model rows, never events. The single causal relationship in the whole path — submit → outcome —
is **unrepresented on the wire**: `client_request_id` is an idempotency key for the EVT-L3 dedup
triple (`ChannelRoom.ts:326-335`), not a causal pointer, and nothing links the two ends.

**Conclusion: causality chaining in this codebase is entirely a drawing.** The schema has been
prepared for it three times over — `causation_id`, `causal_refs`, `IslandMessage.causality` — and
implemented zero times. That is good news for a design round: the storage slots are already
migrated, unused, and free to define.

---

## PART 4 — THE FIVE THINGS MOST LIKELY TO CONSTRAIN A NEW EVENT DESIGN

### 1. Write-time schema validation is documented as enforced and does not exist

`0002_events_table.up.sql:35-37` states: *"every row's `event_type` + `event_version` MUST exist in
`contracts/events/_registry.yaml`; the L2.I validators_go layer enforces this at write-time before
INSERT."* It does not. The Go validator has **0** non-comment callers (grep in Part 1); the Rust
`ValidatorRegistry` (`event_validator.rs:190-220`) is exported at `lib.rs:138` and called by nothing;
and neither INSERT statement (`event_store_pg.rs:251`, `channel.rs:166`) invokes a validator. The
`registry_version` column that exists to record *which* schema validated a row is NULL for every row.

**Today any string is a valid `event_type`.** The 15 registered types are a documentation
convention, not a constraint. Cheap now: turn on the validator that is already written and stamp
`registry_version`. Expensive later: after arbitrary types are in an append-only, partially-archived
log, you cannot retrofit the invariant without a backfill you cannot perform on dropped partitions.

### 2. A hashed byte layout is already in production over exactly `payload` + `metadata`

`event_store_pg.rs:276-277` and `channel.rs:169-170` both compute, in SQL:

```sql
encode(sha256(convert_to(
    jsonb_build_object('p', $8::jsonb, 'm', $9::jsonb)::text, 'UTF8')), 'hex')
```

Postgres is the sole canonicalizer, deliberately, so Go and Rust producers agree byte-for-byte
(`event_store_pg.rs:269-275`). This fixes two things permanently: **causal data placed anywhere other
than inside `payload` or `metadata` is outside the integrity hash**, and the hash is a plain column,
not `GENERATED` (`0013:28-31`), so it is never recomputed. Put `causation_id` in `metadata` and it is
covered for free; add a new top-level *column* for it and it is unprotected, and harmonising later
means rewriting a checksum across an append-only table.

Related and sharper: `ruleset_digest` is `CHAR(64)` lowercase-hex, validated for **format but not
presence** (`envelope.go:113-116`, `envelope.rs:86-90`), with `NULL` meaning "no pin" and a 64-zero
string explicitly outlawed by `scripts/zero-digest-gate.py`. Any new digest-shaped field should
follow that established convention rather than invent a sentinel.

### 3. Ordinal space: there is no global sequence, and the only real uniqueness lives on a side table

Three ordering notions coexist and none is a global `seq`:

- `aggregate_version BIGINT` — per `(reality, aggregate_type, aggregate_id)`, assigned by the writer
  under optimistic CC against `MAX(aggregate_version)` (`event_store_pg.rs:210-234`).
- `channel_event_id BIGINT` — per `(reality, channel)`, allocated DB-authoritatively by CAS on
  `channel_writer_state.last_event_id` (`channel.rs:129-140`, table at `0014:25-32`).
- `recorded_at` — the partition key.

There is **no `CREATE SEQUENCE`, no `SERIAL`, and no `pg_advisory_lock`** in the per-reality schema.
And the PK `(reality_id, aggregate_type, aggregate_id, aggregate_version, recorded_at)` includes
`recorded_at`, so it does **not** enforce one-version-per-aggregate. `0002:96-99` and `:136-138`
claim a partial unique index closes that hole; **the index is never created** — `grep -rn "UNIQUE"
contracts/migrations/per_reality/*.up.sql` returns exactly one hit, a comment at `0014:4`.
`events.event_id` has no uniqueness constraint at all, only the non-unique `events_event_id_idx`
(`0002:146-147`). The one hard guarantee is
`channel_event_index` PK `(reality_id, channel_id, channel_event_id)` (`0014:35-42`) — on a
**separate table, in a separate row**, because PG forbids a parent unique constraint omitting the
partition key (`0014:4-13`).

A design that assumes "events have a totally ordered global id" has no such thing to build on, and a
design that assumes `event_id` is unique is relying on the writer, not the database.

### 4. Retention will destroy the causal history a fold would need — in three independent ways

The archive path is `DETACH PARTITION` + `DROP TABLE` in one tx
(`archive-worker/pkg/pgio/pgio.go:178-199`), on the oldest partition older than 90 days.

- **The archive is lossy.** It selects **13 of 19 columns** (`pgio.go:124-129`), and restore
  re-inserts the same 13 (`restore.go:76-113`). Dropped forever: `content_sha256`, `channel_id`,
  `channel_event_id`, `writer_epoch`, **`causal_refs`**, `ruleset_digest`. So the field a new design
  would use for causality is, today, **the first thing thrown away** — as is the channel ordering
  and the ruleset pin that `0016`'s own header exists to protect.
- **Class policy is not enforced.** `event_classes.yaml:33` promises canon events are never
  auto-deleted with a CI gate; neither worker has any concept of an event class
  (grep for `canon\|event_class` over both workers → 3 hits, all comments/unrelated). A partition
  holding `canon.promoted` is dropped exactly like one holding `npc.moved`.
- **A backdated write in the read→drop window is lost unarchived**, documented by the code itself at
  `pgio.go:102-110`.

Also: `channel_event_index` and `channel_writer_state` are pruned by nothing, so the ordering index
outlives the events it indexes.

### 5. Two registries, two rails, one overlapping name — and the game rail has no append-only guard

There are **two** authoritative event lists. `contracts/events/_registry.yaml` — 15 types on the
per-reality rail (`events` → `events_outbox` → publisher → `lw.events.<reality>`). And
`contracts/meta/events_allowlist.yaml` — 21 distinct `event_name`s on the meta rail
(`meta_outbox` → `lw.meta.events`), keyed by `(meta_table, op)`. **`reality.created` appears in
both.** `reality.status.changed` and `reality.ruleset.bound` are in the meta allowlist and **absent**
from `_registry.yaml`. A new event type must pick a rail, and the two have different envelopes,
different validators, and different drains.

And the game rail's `events` table, called "append-only" in `COMMENT ON TABLE` (`0002:116-117`) and
its header (`0002:5`), has **no enforcement whatsoever**: greps over
`contracts/migrations/per_reality/` for `REVOKE`, `CREATE RULE`, and `trigger` return **0, 0, 0**.
The repo demonstrably knows how — `migrations/meta/013_meta_write_audit.up.sql:72,80` uses
`REVOKE UPDATE, DELETE`, and `contracts/migrations/glossary/0001_canon_change_history.up.sql:85-101`
ships a 3-layer plpgsql-exception + BEFORE UPDATE/DELETE trigger defense. The canonical event log
gets neither. A causality design that assumes immutability of A when writing B is assuming something
the database does not currently promise.

**Sixth, and free to fix now:** 7 of 16 per-reality migrations are unregistered in
`contracts/migrations/manifest.yaml` (which stops at `0013`). `0014`, `0015`, `0016` are
**not acknowledged anywhere** — so the orchestrator's manifest-driven `migrate` path never creates
`channel_writer_state`, `channel_event_index`, the lease columns, or `events.ruleset_digest` on a
freshly provisioned reality. Every channel-ordering and ruleset-pin guarantee above depends on
migrations production does not apply.

---

## WHAT I DID NOT MANAGE TO MEASURE

- **Runtime behaviour.** Nothing was executed — no stack booted, no query run, no test suite run.
  Every "wired/unwired" verdict is static-analysis of call graphs and deployment config. A code path
  reachable only through reflection, a build script, or an operator's shell history would read as
  unwired to me.
- **Whether `ChannelRoom` ever ran live.** Commit `fc2ba5f8a` and a comment in `turn.schema.json`
  ("LIVE-PROVEN in the committed log 2026-07-27") assert a live run happened. That is a claim in
  text; I could not verify it, and the deployed config would throw today.
- **Whether `ghcr.io/loreweave/{retention,archive}-worker:0.1.0` exist.** No Dockerfile and no CI
  build job for them in-repo.
- **`crates/dp-kernel`'s other ~20 modules** (`turn.rs`, `ws.rs`, `lifecycle.rs`, `capacity.rs`,
  `pii_sdk.rs`, `resilience.rs`, `service_acl.rs`, `supply_chain.rs`, …) were LOC-counted and
  name-scanned for event relevance, not read. I judged them non-event-bearing on module docs and
  greps; `turn.rs` and `ws.rs` are the two most likely to repay a closer look.
- **`services/commit-service/src/domain/`** (649-line stub) — measured for LOC only and, per the
  brief, cited nowhere as evidence.
- **Payload schemas per event type.** I measured the envelope and the row exhaustively but did not
  open the 16 generated structs to catalogue what each event's `payload` contains.
- **The Python/TS generated bindings' drift gate** (`scripts/eventgen-validate.sh`, 5,032 bytes) —
  confirmed to exist, not read, so I cannot say what it would catch.
