# S3 — Seeded Workload Generator (build plan)

> **Slice:** S3 of the foundation runtime test plan (`docs/specs/2026-06-04-foundation-runtime-test-plan.md` §5, §10).
> **Status:** PLAN (written; awaiting human review before BUILD).
> **Task size:** **XL** — new Go module, world-state model, per-event-type payload builders, 4 profiles, real-outbox writer, CLI, tests. Full 12 phases, no skips; `/review-impl` before commit (this is the **dependency root** of C/C2/C3/B-shards/D/F/H0 — the most load-bearing slice in the spine).
> **Locked decisions (this session):** Go · **broad** emission surface (all projection-handled event types, 11 tables) · **all 4 profiles** (micro · single-reality · multi-reality · multi-user-session) · location `tests/workload-gen/` (Go module, parallels `tests/conformance/`).
> **Build order context:** S3 is **the gate** — `S1 → S3 → {S2/C2, S2b/C3, S4, S9}`. Nothing in the correctness spine builds before the generator exists.

---

## 1. CLARIFY — scope & acceptance (grounded in the real foundation)

### What S3 is
A **seeded, deterministic** generator that produces **valid event streams** and writes them through the **real Go outbox write path** so the whole base→derived pipeline runs: `events`+`events_outbox` (atomic) → publisher drains → Redis Streams → Rust projections apply → 11 projection tables → integrity-checker verifies. One generator feeds C (structural oracle), C2 (from-spec), C3 (log-integrity), B-shards, D (fault matrix), F (perf), H0 (DST seed).

### Grounded facts (from investigation)
- **Real write path = Go**, atomic in one tx (`tests/integration/outbox_atomicity_test.go:54-70`): `tx.ExecContext(INSERT INTO events …)` + `events.OutboxWrite(ctx, tx, events.OutboxRow{EventID, RealityID})` + `tx.Commit()`. `OutboxWrite` takes any `OutboxExecutor` (`*sql.Tx` satisfies it) — `contracts/events/outbox.go:81`. Reuse it verbatim (no SQL drift).
- **The event store does NOT validate `event_type` against the registry** (`crates/dp-kernel/src/event_store_pg.rs:62-145`; payload is opaque JSON; `envelope.validate()` is structural only) → the generator may emit the **handled-but-unregistered** types the projections need.
- **Emittable+projecting surface (broad)** — the projection `apply_event` arms:
  | event_type | aggregate | projection table(s) | payload fields read | cross-ref / causal |
  |---|---|---|---|---|
  | `npc.created` | npc | npc_projection | glossary_entity_id, spawn_region_id, initial_mood, core_beliefs | spawn_region_id → a `region.created` |
  | `npc.said` | npc | npc_projection (ver bump) + npc_session_memory_projection (interaction++) | — ; `metadata.session_id` | needs prior `npc.created` + `session.started` |
  | `pc.spawned` / `pc.moved` | pc | pc_projection (+ pc_inventory) | (read `crates/projections/pc/src/lib.rs:59-100`) | moved → real `to_region_id` |
  | `region.created` / `region.ambient_changed` | region | region_projection | (read `crates/projections/region/src/lib.rs:33-55`) | ambient → prior `region.created` |
  | `world.kv_set` / `world.kv_unset` | world | world_kv_projection | (read `crates/projections/world_kv/src/lib.rs:31-59`) | unset → prior set |
  | `session.started` / `session.ended` / `session.participant_joined` / `session.participant_left` | session | npc_session_memory_projection, session_participants | npc_id, session_id, aggregate_id | started → real npc; ended → prior started |
  | `canon.entry.created/updated/promoted/decanonized` | canon | canon_projection | (read `crates/projections/canon/src/lib.rs:77-151`) | updated/promoted/decanonized → prior created |
  | `admin.canon.override.compensating` | canon | canon_projection | (read canon arm) | → an existing canon entry |
  > BUILD reads each `apply_event` arm to nail the exact payload fields (the `npc.created`/`npc.said` arm at `crates/projections/npc/src/lib.rs:52-93` is the worked example).
- **Monotonic** `aggregate_version` per `(reality_id, aggregate_type, aggregate_id)`, starting at 1 (`event_store_pg.rs:137` first==current+1). The generator owns versions by construction.
- **PK** `(reality_id, aggregate_type, aggregate_id, aggregate_version, recorded_at)` — uniqueness per aggregate version (`0002_events_table.up.sql`). Outbox PK = `event_id`.

### In scope (S3)
1. **World-state model** — as the stream is generated, track created entities (realities, regions, npcs, pcs, sessions) + each aggregate's current version, so every event references **valid ids** and gets a **monotonic** version.
2. **Per-event-type payload builders** — one builder per handled type, producing payloads the Rust projections apply (fields per the arm).
3. **Causal ordering** — create-before-reference (region before npc-spawn-there; npc+session before npc.said; created before updated).
4. **4 profiles** — `micro` (1 aggregate/1 table, for C unit tests) · `single-reality` (many aggregates/tables) · `multi-reality` (N realities, cross-shard — I5/I7) · `multi-user-session` (many sessions — I6).
5. **Seeded determinism** — `(seed, profile) → byte-identical stream` across runs (required: deterministic replay is C's strongest property).
6. **Real-outbox writer** — `tx → INSERT events + events.OutboxWrite → commit`, batched per aggregate, monotonic.
7. **CLI** — `gen -seed N -profile single-reality [-emit | -dry-run] [-dsn …]`; `-dry-run` emits the stream as JSONL (no DB); `-emit` writes via the real path.
8. **Unit tests** — determinism, per-aggregate monotonicity, referential validity (every ref resolves), causal order (no forward ref), per-profile shape invariants.

### Out of scope (later slices)
- The oracles themselves (C/C2/C3 = S2/S2b), fault injection (S6), perf (S7). S3 only **produces + writes** streams.
- The gateway/WS load surface (wrk2/k6) — plan §5 second paragraph; separate, S7.
- Exhaustive payload coverage of every future domain event — S3 covers the **currently-handled** arms; new arms extend the matrix later.

### Acceptance gate (definition of done) — LOCKED
- All in-scope 1–8.
- `go test ./...` green in `tests/workload-gen/`; `go vet` + `gofmt` clean.
- **Determinism proof:** same `(seed, profile)` → identical JSONL twice (golden or self-compare test).
- **Referential+causal proof:** a validator test asserts every generated stream has no forward/dangling reference and monotonic per-aggregate versions, for all 4 profiles.
- **Live-smoke (the pipeline):** with a stack up, `-emit` a `single-reality` stream → publisher drains → projections populate → integrity-checker verdict clean. **On a dev box without the stack → notrun** (registered as a conformance live-probe, see §4). Live infra unavailable token applies.
- `language-rule-lint` PASS (new `tests/` Go module not misread as a service).

---

## 2. DESIGN

```
tests/workload-gen/
  go.mod                                  # module …/tests/workload-gen (+ contracts/events, google/uuid, lib/pq)
  internal/
    world/    world.go    + _test         # world-state model: entity registries + per-aggregate version cursors
    schema/   payloads.go + _test         # per-event-type payload builders (fields per the projection arms)
    gen/      gen.go      + _test         # the stream generator: seeded, causal, profile-driven → []Envelope
    profiles/ profiles.go + _test         # the 4 profile shapes (entity/reality/session counts + mix)
    emit/     emit.go     + _test         # real-outbox writer: tx → INSERT events + OutboxWrite → commit
  cmd/workload-gen/main.go                # CLI: -seed -profile -emit/-dry-run -dsn
  README.md
```

- **Envelope:** reuse the Go envelope shape (`contracts/events/envelope.go`) so events are byte-compatible with what Rust projections read (the envelope is the cross-language contract).
- **Determinism:** a single `math/rand.New(rand.NewSource(seed))` threaded through generation; **no wall-clock** in IDs/ordering — `occurred_at`/`recorded_at` derived from a logical clock seeded per run (so JSONL is reproducible). UUIDs derived deterministically from `(seed, kind, ordinal)` (e.g. `uuid.NewSHA1` over a namespace) — NOT `uuid.New()` (random).
- **World-state model** (`world/`): maps of created entities per reality + a `map[aggregateKey]uint64` version cursor; `next(reality, aggType, aggID)` returns+bumps the version. Reference helpers: `pickRegion`, `pickNpc`, `pickSession` return only already-created ids (enforces no-forward-ref).
- **Generator** (`gen/`): drives a profile's "script" of weighted steps; each step consults world-state, builds a valid event (payload via `schema/`), appends to the stream, updates world-state. Causal order is structural (you can only reference what's been created).
- **Emit** (`emit/`): groups the stream by `(reality, aggregate)`, writes each aggregate's events in version order, each event = one tx (or batched per aggregate) doing `INSERT events` + `events.OutboxWrite`. Reuses `events.OutboxInsertSQL` / `OutboxWrite` verbatim.

---

## 3. PLAN — build increments (TDD, human-in-loop; stop+report per increment)

1. **Scaffold** `go.mod` + tree + README stub.
2. **`world/`** — entity registries + version cursors + reference pickers. Tests: monotonic `next`, pickers never return an uncreated id, deterministic.
3. **`schema/`** — payload builders for the npc + session arms first (the worked example), then pc/region/world_kv/canon. Tests: each payload has the fields its projection arm reads (table-driven against the arm's required keys).
4. **`gen/`** — seeded stream generator for the `micro` + `single-reality` profiles. Tests: determinism (same seed→identical), monotonicity, referential validity, causal order.
5. **`profiles/`** — add `multi-reality` + `multi-user-session`; profile-shape invariants (≥N realities, ≥M sessions, table coverage). Tests per profile.
6. **`emit/`** — real-outbox writer; unit-test with a fake `OutboxExecutor` + a fake events-insert (assert same-tx ordering, monotonic, OutboxWrite called once per event). Live write behind a build tag / DSN gate.
7. **`cmd/workload-gen`** — CLI wiring (`-dry-run` JSONL, `-emit` real path).
8. **Conformance case** — add `tests/conformance/catalog/generic/workload-gen-pipeline.yaml` (live-probe, `requires:[foundation-stack]`) that emits a stream and asserts the integrity-checker verdict is clean → **closes the loop with S1** (notrun on dev, pass on a stack).

### Test plan
unit: world (monotonic/no-forward/deterministic) · schema (payload-field coverage per arm) · gen (determinism, monotonicity, ref-validity, causal-order) · profiles (shape invariants ×4) · emit (same-tx, OutboxWrite-once, version order) via fakes.
live-smoke: `-emit single-reality` on a stack → publisher → projections → integrity-checker clean (else notrun).

### VERIFY gate
- `go test ./...` + `go vet` + `gofmt -l` clean in `tests/workload-gen/`.
- `go run ./cmd/workload-gen -seed 1 -profile single-reality -dry-run` twice → identical JSONL (determinism).
- Validator over all 4 profiles → no forward/dangling ref, monotonic versions.
- `language-rule-lint` PASS.
- Live-smoke: `-emit` on a stack if bootable, else `live infra unavailable: foundation-dev stack not booted at dev time` (and the conformance case reports notrun).

---

## 4. Risks & open items

**Risks**
- **R1 — payload drift vs projection arms.** The generator's payloads must match what each Rust `apply_event` arm reads; if an arm changes fields, the generator drifts silently. **Mitigation:** schema tests assert the required keys per arm; and the live-smoke (integrity-checker clean) is the end-to-end backstop. (A future C2 from-spec fixture, S2, hardens this further.)
- **R2 — emitting unregistered event types.** Broad surface emits types not in `_registry.yaml` (pc.*, region.*, session.*, world.kv.*). The event store accepts them (no registry check), but a future emit-time validator could reject them. **Mitigation:** document that the generator writes **direct to the event store** (a seeder), bypassing the service-emission governance layer by design; flag if a validator is later added to the store path.
- **R3 — determinism leaks.** `uuid.New()` / wall-clock would break reproducible streams. **Mitigation:** derive UUIDs + timestamps from the seed (logical clock); a determinism test is the guard.
- **R4 — multi-reality sharding.** `multi-reality` writes to N per-reality DBs/schemas; the emit path must target the right shard. **Mitigation:** start with N logical realities in one DB (reality_id-scoped rows) for the dev/unit path; real cross-shard DSN routing is an emit-config concern — see O2.

**Open items (carry into BUILD)**
- **O1** — batch granularity in emit: one-tx-per-event (simple, slow) vs one-tx-per-aggregate-batch (matches `append_events` batch semantics). Recommend per-aggregate batch.
- **O2** — multi-reality shard routing (one DB many reality_ids vs many DBs). Recommend logical-reality-in-one-DB for S3; real shard DSN routing deferred to when the provisioner path (S4/L1) is exercised.
- **O3** — `occurred_at` vs `recorded_at` logical-clock scheme (monotone, reproducible) — pin the format in BUILD.
- **O4** — whether to also emit the **non-projecting** registered events (reality.created, world.tick, xreality.*, canon.change.recorded, admin.canon.override.{requested,consented,vetoed}) for realism/coverage even though they don't project. Recommend: include reality.created (bootstraps a reality) + world.tick (drives time); skip the rest in S3.

## 5. Deferred-Items to add at COMMIT
- **D-WORKLOAD-GEN-VALIDATOR-EMIT** (R2) — if an emit-time registry validator is added to the event-store write path, reconcile the generator (which intentionally bypasses service-emission governance). Target: when L2.I validator wires into the store path.
- **D-WORKLOAD-GEN-REAL-SHARD** (O2) — real multi-DB shard routing for `multi-reality` emit. Target: S4/L1 (provisioner) integration.
