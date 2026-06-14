# Wave 3 — Oracle / generator completeness — implementation plan

Spec: `docs/specs/2026-06-15-wave3-oracle-generator-completeness.md`. Size **XL**,
6 increments, batch cadence (autonomous → one POST-REVIEW → push-ask).
`/review-impl` plan first, then impl. W3.4 is load-bearing (core-table migration +
kernel hot path) → production-shaped, `/review-impl` before its commit.

## Guiding constraints
- **Locate-first** each touch point before editing (recon gave the map; the exact
  predicate for the schema-derived table list, the publisher high-water source,
  and the verifmeta second copy are confirmed AT BUILD, not assumed).
- **Non-vacuity:** every check ships a bite that can fail. Two items (W3.2 schema
  drift, W3.4 checksum) get a real injected-fault bite; W3.3 is a fixture
  regression-guard; W3.5 builds-or-defers with evidence.
- **No padding:** W3.2 verifmeta-copy + W3.6 fleet-folding + W3.5 recon may be
  partly already-done — close with the real evidence, don't invent work.

## Increment order (dependency-aware)
W3.1 (generator events) **first** — the richer generated data is what W3.2's
schema-derived sweep + W3.4's checksum check run over. Then W3.2 → W3.3 →
**W3.4 (load-bearing)** → W3.5 (conditional) → W3.6 (conformance/CI/SESSION).

## Increment 1 — W3.1 generator NPC rel+embed + persistent world-kv `[BE/Go]`
- `tests/workload-gen/internal/world/world.go`: track enough state to emit causally
  — an npc + pc that exist + a started session (relationship), an npc + session
  (memory). Add deterministic helpers (PickNpcPc pair, etc.).
- `tests/workload-gen/internal/schema/payloads.go`: add `NpcRelationshipChanged`
  (other_entity_id/type, trust_level, familiarity_count, session_id, labels — match
  `crates/projections/npc` `NpcPcRelationshipProjection`) + `NpcMemoryEmbedded`
  (npc_id, session_id, content_hash, dim=1536 embedding — match
  `NpcSessionMemoryEmbeddingProjection`). **Locate-first the exact payload keys**
  the Rust projections read.
- `gen.go`: inside the session loop (after participant_joined + says, where the
  npc+pc+session all exist) emit one `npc.relationship_changed` (npc aggregate) +
  one `npc.memory_embedded` (npc aggregate, session_id in metadata) per the profile.
  Bump versions correctly (these are npc-aggregate events).
- **World-kv variant:** add a profile field (e.g. `PersistentKvKeys int`) OR emit
  one extra `world.kv_set` with NO matching `kv_unset` so `world_kv_projection`
  retains a row. Keep the existing set+unset pair (tests the delete arm) AND add a
  persistent key (tests the row-present arm).
- `gen.Validate` + `schema` registry: register the two new event types so Validate
  doesn't reject them (add validation rules: relationship needs npc+pc created;
  memory needs npc + a started session).
- **Drill + bite** (`scripts/perf/w3-generator.sh`, reuses the rig PG): emit →
  `wg -check-projections` (no-orphan) + assert `npc_pc_relationship_projection`,
  `npc_session_memory_embedding`, `world_kv_projection` each have ≥1 row. **Bite:**
  a `-no-new-arms` env (or the old generator) → those tables have 0 rows → the
  arms were vacuous. Unit-test the new builders + Validate rules.

## Increment 2 — W3.2 schema-derived projection-table list `[BE/Go]`
- `tests/workload-gen/internal/projcheck/load.go`: replace the hardcoded
  `projectionTables` with a query over `information_schema.tables` (public schema)
  selecting projection tables. **Confirm the predicate at build** — the 11 tables
  aren't all `%_projection` (e.g. `session_participants`,
  `npc_session_memory_embedding`); likely use an explicit "projection table"
  marker (a comment-tag, a naming set, or a curated `LIKE` + allowlist). If no
  clean schema signal exists, derive from the known suffix set + document the
  residual. Keep a fallback to the curated list if the query returns empty (safety).
- **D-S4-VERIFMETA-TABLE-SYNC:** grep for a second hardcoded copy (S4 verifmeta /
  verification-meta checker). If none exists → close the row N/A with the grep
  evidence. If one exists → apply the same derivation.
- **Bite:** create a throwaway `zzz_projection` with an orphan row (event_id not in
  events) → the schema-derived sweep flags it; assert the OLD hardcoded list would
  have missed it (the table isn't in the 11). Drop the table after.

## Increment 3 — W3.3 meta fake-DB UUID actor fixtures `[BE/Go]`
- `contracts/meta/*_test.go`: replace non-UUID actor_id literals (`"user-1"`,
  `"world-service"`, `"op"`, …) with deterministic UUIDs (a small set of named
  consts, or `fakeUUIDGen`). Keep ActorType strings (those are enums, not UUIDs).
- **Bite/guard:** this is a fixture-correctness regression guard (the live I9 probe
  is the real catcher). Add a tiny assertion/test that the fixture actor_ids parse
  as UUIDs so a future string literal trips CI. Run the full `contracts/meta` suite
  to confirm green.

## Increment 4 — W3.4 ledger stored checksum `[FS]` (LOAD-BEARING)
- **Migration** `contracts/migrations/per_reality/0002b_events_payload_sha256.up.sql`
  (NEW, additive): `ALTER TABLE events ADD COLUMN payload_sha256 CHAR(64)` (nullable
  → existing rows unaffected; partitioned-table ALTER ADD is metadata-only). Down
  migration drops it. (A new migration, NOT editing 0002 — 0002 is `breaking` +
  already applied everywhere.)
- **Canonicalization (the crux, review hard):** the hash MUST match between the Go
  emit path and the Rust kernel append. Define ONE canonical byte form — the
  payload's RAW stored JSONB bytes are NOT stable cross-language. Use SHA-256 over
  the **compact/sorted-key JSON serialization** computed identically on both sides
  (Go `json.Marshal` of a canonicalized map vs Rust `serde_json` to_vec with sorted
  keys) — OR hash the bytes the writer already has before they hit JSONB. Pin the
  canonical form + add a cross-language equality test (a fixed payload → the same
  64-hex on both). If a stable cross-lang canonical JSON is too fragile, scope the
  write to ONE writer first (the kernel append) + document the emit-path follow-up.
- **Write path:** `event_store_pg.rs` append computes + writes `payload_sha256`;
  `emit.go` `writeEvent` does the same.
- **Check:** `ledger` gains `CheckStoredChecksum(log)` — rehash each event's payload
  (canonical form) and compare to the stored `payload_sha256` (skip NULL = pre-
  migration rows). New `-check-checksum` CLI (or fold into `-verify`).
- **Drill + bite** (`scripts/perf/w3-checksum.sh`): emit (rows now carry
  payload_sha256) → `-check-checksum` PASS. **Bite:** `UPDATE events SET
  payload = payload || '{"rot":1}'` on one row (leaving payload_sha256 stale) →
  `-check-checksum` FAILS (rehash ≠ stored). NULL-checksum rows don't false-fail.
- **R-checksum:** if the Go/Rust canonical forms can't be made identical cheaply,
  the honest fallback is: store the checksum from the WRITER's own canonical bytes
  + verify with the SAME language's rehash (the seeded drill uses emit.go's form;
  the production kernel uses Rust's form; the check rehashes per-writer). Document
  whichever path is taken.

## Increment 5 — W3.5 ledger published-recon `[BE/Go]` (conditional)
- **Locate-first** the publisher high-water source: `publisher_heartbeats`
  (last_delivered?), a progress row, or the Redis stream XLEN per reality. If a
  crisp source exists → add `CheckPublishedRecon(log, highwater)`:
  `count(events_outbox WHERE published) == high-water delivered count` (or the
  published set ⊆ delivered). **Bite:** a published row absent at the high-water →
  flagged. If NO crisp source exists → **DEFER** with the rationale (the
  count-recon + W3.4 already cover outbox↔events; recon needs the publisher in the
  standing gate) and record the row as remaining-open. Decide at build, don't pad.

## Increment 6 — W3.6 conformance hygiene + CI + SESSION `[FS]`
- **Audit** the deferred ledger for the REAL count of un-folded lints/live-smokes
  (recon: catalog already ~58). Fold the genuine remainder (1 `w3-*`/lint case
  each); if substantially folded already, close D-CONFORMANCE-FLEET-MIGRATION with
  the real number as evidence.
- **Container-churn:** add the assume-up + notrun helper convention to any sibling
  live-probe that `compose up`s (confirm which at build); else close N/A.
- New `w3-*` conformance cases (generator-arms, schema-derived-sweep,
  stored-checksum, + recon if built) `requires:`-gated; CI `scale-build` build/vet/
  `bash -n` + `scale-nightly` live sweep. SESSION + memory + prune. Close the Wave-3
  rows (or N/A-with-evidence); check the cleardown Wave-3 box.

## Risks
- **R1 cross-language checksum (W3.4).** Go-emit vs Rust-append hashing the "same"
  payload is the hard part (JSONB byte form isn't stable cross-lang). Mitigation:
  pin ONE canonical JSON form + a cross-lang equality test BEFORE wiring the check;
  if too fragile, fall back to per-writer canonical bytes + document. Never ship a
  check that green-passes only because both sides are the same language by accident.
- **R2 core-table migration (W3.4).** Additive nullable column on the partitioned
  `events` table — metadata-only ALTER, back-compat. Apply as a NEW migration
  (0002b), not an edit to the already-applied breaking 0002. Drill uses throwaway
  DBs.
- **R3 schema-derived predicate (W3.2).** The 11 projection tables don't share one
  clean suffix. Mitigation: confirm the real signal (tag/allowlist) at build; keep
  the curated list as a safety fallback if the query returns empty; the bite proves
  a NEW table is caught.
- **R4 over-claiming closure (W3.2 verifmeta / W3.5 recon / W3.6 fleet).** Some
  rows may already be done or have no in-repo target. Close them N/A WITH grep/
  count evidence, never silently.
- **R5 generator causality (W3.1).** The new npc events must reference an npc+pc+
  session that exist earlier (Validate enforces). Mitigation: emit them inside the
  session loop where all three are live; extend Validate's rules + test.
