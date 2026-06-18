# Wave 3 — Oracle / generator completeness (spec)

**Status:** CLARIFY → DESIGN. Size **XL** (bundled). One task per the batch cadence:
spec+plan once, `/review-impl` plan + impl, autonomous through increments → one
POST-REVIEW → push-ask.

## Why

The S1–S14 batteries + Waves 1–2 are in place, but several oracles/generators are
**partially vacuous** — they pass because the input never exercises the arm, not
because the arm is proven. Wave 3 (Category A from
`docs/plans/2026-06-14-post-S14-deferred-cleardown.md`) un-vacuums them: emit the
missing events, leave a row to verify, derive the checked-table list from the live
schema, give byte-rot a stored baseline, reconcile delivery, and tidy fixtures.
All dev-doable (no Linux-only infra).

## Items

### W3.1 — Generator: emit `npc.relationship_changed` + `npc.memory_embedded` + a persistent world-kv (closes D-WORKLOAD-GEN-NPC-REL-EMBED, D-S5-WORLDKV-NETS-EMPTY)
- **Recon-confirmed:** the npc projection arms are READY —
  `NpcPcRelationshipProjection` consumes `npc.relationship_changed` →
  `npc_pc_relationship_projection`; `NpcSessionMemoryEmbeddingProjection` consumes
  `npc.memory_embedded` → `npc_session_memory_embedding`. The generator emits
  NEITHER, so both arms get 0 coverage.
- Add the two emissions to `gen.go` (causally: a relationship/memory event for an
  npc+pc that already exist + a started session), the missing `schema` payload
  builders, and the minimal `world` state to keep them deterministic + valid.
- **World-kv:** add a generator variant that emits `world.kv_set` WITHOUT the
  matching `kv_unset` so `world_kv_projection` ends with a row to verify (today
  set+unset net-zeroes → no row).
- **Bite:** drop the new emissions → the projection arms have 0 rows (the B/C2
  coverage of those two tables + world_kv is vacuous); with them → rows present +
  verify. (The non-vacuity is that the arms now actually carry data.)

### W3.2 — Schema-derived projection-table list (closes D-PROJCHECK-TABLE-DRIFT, D-S4-VERIFMETA-TABLE-SYNC)
- `projcheck/load.go` hard-codes 11 projection tables (`projectionTables`); a new
  projection table added by a migration is **silently unchecked** by the no-orphan
  sweep. Derive the list from the live schema
  (`information_schema.tables` … `LIKE '%_projection%'` + the known non-`_projection`
  projections — confirm the exact predicate at build).
- **D-S4-VERIFMETA-TABLE-SYNC:** recon found NO `verifmeta` checker in-repo — confirm
  at build; if the second hardcoded copy doesn't exist, close the row as N/A with
  evidence (don't invent one).
- **Bite:** add a throwaway `zzz_projection` table with an orphan row → the
  schema-derived sweep CATCHES it (a hardcoded list would miss it) → proves the
  derivation closed the drift.

### W3.3 — Meta fake-DB UUID actor fixtures (closes D-META-FAKEDB-UUID-ACTOR)
- `contracts/meta` unit fixtures use non-UUID `actor_id`s (`"user-1"`,
  `"world-service"`); the real `*_audit.actor_id` columns are UUID. The fake-DB is
  type-blind JSON so the tests pass — a mock-only blind spot (S4 review caught it).
- Replace the string literals with deterministic UUIDs (or `fakeUUIDGen`).
- **Bite:** the I9 live probe (already exists) is what catches the real-schema
  type; this increment makes the UNIT fixtures match so they can't drift back —
  the "bite" is that the fixtures now use real-shaped ids (regression guard).

### W3.4 — Ledger stored checksum (closes D-LEDGER-STORED-CHECKSUM) — LOAD-BEARING
- Byte-rot is only detectable today against the seeded generator (re-hash in
  `against.go`); **production data has no baseline**. Add a stored checksum:
  - **Migration:** `events.payload_sha256 CHAR(64)` (nullable, back-compat) on the
    per-reality `events` table (a real migration on a core table).
  - **Write path:** the kernel append (`event_store_pg.rs`) computes
    SHA-256(payload canonical bytes) and writes it in the same INSERT; the emit
    path (`emit.go`) does the same so seeded + production rows both carry it.
  - **Check:** a ledger check that re-hashes each stored payload and compares to
    the stored `payload_sha256` — catching byte-rot WITHOUT a seed baseline.
- **Bite:** mutate a stored payload (leave `payload_sha256` stale) → the check
  FAILS (rehash ≠ stored); a row whose payload + checksum agree → passes. The
  production VALUE is post-go-live, but the build + bite are do-now.
- **Care:** core-table migration + spine hot-path change → production-shaped,
  `/review-impl` this increment hard (canonicalization must be stable; nullable so
  existing rows don't break; the hash must match between Go emit + Rust append).

### W3.5 — Ledger published-recon (closes D-LEDGER-PUBLISHED-RECON) — conditional
- Reconcile `events_outbox.published=true` against the publisher high-water. Build
  it IF a high-water source exists (`publisher_heartbeats` / a progress row /
  Redis stream length) — **locate-first at build.** If no crisp high-water source
  exists yet, DEFER with a sharp rationale (like W2 clock-skew) rather than ship a
  vacuous recon — the W3.4 + existing count-recon already cover the outbox↔events
  1:1.
- **Bite (if built):** mark a published row's delivery missing at the high-water →
  the recon flags the gap; aligned → passes.

### W3.6 — Conformance hygiene + SESSION (closes D-CONFORMANCE-FLEET-MIGRATION, D-CONFORMANCE-LIVEPROBE-CONTAINER-CHURN)
- **Audit-first:** recon shows ~58 catalog cases already; the "remaining ~26 lints
  + ~4 live-smokes" count is stale. Audit the deferred ledger + the actual lints/
  live-smokes NOT yet folded; fold the genuine remainder (1 case each). If the
  fleet is already substantially folded, close D-CONFORMANCE-FLEET-MIGRATION with
  the evidence (the real remaining count) rather than padding.
- **Container-churn:** sibling live-probe scripts that `compose up` cause churn;
  add an assume-up + notrun helper convention where missing (confirm scope at build).
- New `w3-*` conformance cases for the W3 runtime checks (generator-arms,
  schema-derived sweep, stored-checksum) `requires:`-gated; CI build/vet.

## Out of scope (→ later)
- The automated partition-manager (Wave 2 note). HA/multi-host. Wave 4 (model/perf
  refinements). The post-go-live VALUE of the stored checksum (the build is do-now).

## Acceptance
Each item: the un-vacuumed oracle/generator + a non-vacuity bite + a `w3-*`
conformance case (where runtime) + CI. W3.4 ships a core-table migration +
hot-path write reviewed hard. W3.5 builds or defers with evidence. SESSION
updated; the Wave-3 deferred rows closed (or closed-as-N/A with evidence); the
cleardown Wave-3 box checked.
