# Glossary-Service Canon Outbox Emission Contract (L5.A)

> **Status:** DRAFT (foundation contract — RAID cycle 23 L5.A.3)
> **Owner:** glossary-service (LoreWeave novel-platform team)
> **Consumer:** Publisher (L2.D) → Redis Streams `xreality.book.canon.updated` → meta-worker canon writer (cycles 24+ L5.B + L5.D)
> **Q-IDs:** Q-L5A-1 (LOCKED — separate sub-program), Q-L5-3 (LOCKED — single-table layer enum), Q-L1A-2 (LOCKED — canon tables in glossary DB)

---

## §1. What this document is

Foundation does NOT modify `services/glossary-service/`. Per Q-L5A-1 LOCKED:

> **Q-L5A-1**: glossary-service outbox migration is a SEPARATE sub-program before L5 push activates; foundation owns CONTRACT + test fixture.

This document is the **contract** glossary-service must implement so that foundation-shipped consumers (meta-worker in cycle 24+) can read its outbox emissions.

The contract has three parts:

1. **Wire schema** — the JSON-encoded event payload glossary-service writes into its outbox row's payload column (defined in `contracts/events/canon.go`, polyglot codegen in `contracts/events/generated/`).
2. **Outbox table shape** — the schema glossary-service must add to its `glossary` Postgres DB (per Q-L1A-2 LOCKED canon tables live in glossary DB).
3. **Emission timing** — when in the authoring API request glossary-service must write to the outbox (atomically in the same TX as the canon mutation).

---

## §2. Authoritative event schemas

See `contracts/events/canon.go`. Four event types (cycle 23 L5.A.1):

| Event type | Go struct | When emitted | Carries |
|---|---|---|---|
| `canon.entry.created` | `CanonEntryCreatedV1` | Author creates a canon entry (POST to canonization endpoint) | `canon_entry_id`, `book_id`, `attribute_path`, `value`, `canon_layer`, `lock_level`, `author_user_id`, `created_at` |
| `canon.entry.updated` | `CanonEntryUpdatedV1` | Author updates an existing canon entry (PATCH) | `canon_entry_id`, `book_id`, `attribute_path`, `old_value`, `new_value`, `canon_layer`, `editor_user_id`, `updated_at` |
| `canon.entry.promoted` | `CanonEntryPromotedV1` | Author promotes `L2_seeded` → `L1_axiom` (M4 §9.7.4 harder gate) | `canon_entry_id`, `book_id`, `from_layer`, `to_layer`, `promoted_by`, `promoted_at` |
| `canon.entry.decanonized` | `CanonEntryDecanonizedV1` | Author retracts a canon entry | `canon_entry_id`, `book_id`, `reason`, `decanonized_by`, `decanonized_at` |

### canon_layer enum (Q-L5-3 LOCKED)

The `canon_layer` payload field MUST be one of:

- `"L1_axiom"` — author-locked, immutable, governs ALL realities (L5.I runtime guardrail rejects conflicting future L3 writes)
- `"L2_seeded"` — author canonical default, per-reality L3 events MAY override

Any other value is a contract violation. Foundation contract test (`contracts/events/canon_test.go::TestCanonLayer_IsValid`) demonstrates the validator.

---

## §3. Outbox table contract

glossary-service must add an outbox table to its `glossary` Postgres DB. Recommended schema (mirroring foundation's L2.C `events_outbox` shape — `contracts/migrations/per_reality/0005_events_outbox_table.up.sql`):

```sql
CREATE TABLE IF NOT EXISTS canon_outbox (
    outbox_id       UUID NOT NULL PRIMARY KEY,
    event_type      TEXT NOT NULL,        -- one of canon.entry.{created,updated,promoted,decanonized}
    event_version   INTEGER NOT NULL DEFAULT 1,
    aggregate_id    UUID NOT NULL,        -- canon_entry_id
    aggregate_type  TEXT NOT NULL DEFAULT 'canon',
    payload         JSONB NOT NULL,       -- matches contracts/events/canon.go wire shape
    metadata        JSONB,                -- MUST include "cross_reality": true so publisher fan-out routes to xreality.book.canon.updated (cycle 10 protocol)
    enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ,          -- NULL until publisher drains
    published_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (published_status IN ('pending', 'sent', 'dead_letter')),
    last_error      TEXT
);
CREATE INDEX canon_outbox_pending_idx ON canon_outbox (enqueued_at) WHERE published_status = 'pending';
```

### Cross-reality fan-out flag

Per cycle-10 xreality protocol, the publisher only fans out events to the `xreality.<entity>.<verb>` Redis Stream when `metadata.cross_reality = true`. glossary-service **MUST** set this flag on every canon outbox row — without it, meta-worker (the sole xreality consumer per I7) never receives the event and per-reality `canon_projection` rows are never written.

Recommended metadata shape:

```json
{
  "cross_reality": true,
  "correlation_id": "<author-request-uuid>",
  "source_service": "glossary-service"
}
```

---

## §4. Emission timing — atomic TX requirement

The outbox write MUST happen in the SAME transaction as the canon table mutation. This is the standard outbox pattern (R06 §12F) — partial failures must either rollback both or commit both. Pseudocode:

```sql
BEGIN;
-- 1. Mutate the canonical table (canon_entries, canonization_audit, etc.)
INSERT INTO canon_entries (...) VALUES (...);
INSERT INTO canonization_audit (...) VALUES (...);
-- 2. Append to outbox in the same TX
INSERT INTO canon_outbox (outbox_id, event_type, aggregate_id, payload, metadata)
    VALUES (gen_random_uuid(), 'canon.entry.created', $canon_entry_id, $payload, $metadata);
COMMIT;
```

If the canonization TX rolls back, the outbox row never appears — no phantom event.

If the outbox INSERT fails, the canon mutation rolls back — no silently-dropped event.

---

## §5. Publisher drain expectations

The foundation Publisher (cycle 9/10 L2.D) drains outbox tables on its standard poll loop. For glossary-service to participate it MUST:

1. Run a Publisher instance (or have the existing foundation Publisher connect to its `glossary` DB).
2. Register the `canon_outbox` table with the Publisher's source list.
3. Allow the Publisher's SVID/service role SELECT + UPDATE on `canon_outbox` (UPDATE to flip `published_status` after successful XADD).

Publisher mechanics (XADD to main stream `events.canon` + xreality fan-out to `xreality.book.canon.updated`, retry, dead-letter) are foundation-owned — glossary-service only writes the row.

---

## §6. Test fixture — what foundation ships

`contracts/events/canon_test.go::TestGlossaryOutboxEmissionFixture` mocks the full glossary-outbox emission pipeline so the sub-program can develop against a real, runnable schema:

1. Mock "author canonization" call constructs a `CanonEntryCreatedV1`.
2. Marshals to JSON (this is what goes into `canon_outbox.payload`).
3. Unmarshals on the consumer side — verifies schema parity.
4. Acceptance: `canon_entry_id` nonzero, `canon_layer` ∈ Q-L5-3 set, `attribute_path` non-empty.

The sub-program is expected to extend this fixture as it implements the emitter — adding integration tests that exercise the actual `canon_outbox` INSERT path.

---

## §7. Versioning + breaking-change policy

The schemas in `contracts/events/canon.go` carry version suffix `V1` (per R03 §12C.5 cooldown protocol). Additive changes:

- New optional field → bump version (V2), provide upcaster `1→2`, V1 still parseable for 6-month cooldown.
- New event type → add struct + `_registry.yaml` entry + extend this contract doc.

Breaking changes:

- DO NOT mutate `V1` field names or types. Add `V2` and deprecate `V1`.
- Removing a field → V2 emission + V1 readability preserved during cooldown.

The foundation contract test fixture **freezes the V1 JSON wire field names** (`TestCanonEntryCreatedV1_WireFieldNames`). Any rename breaks the test — intentional gate.

---

## §8. Sign-off

| Party | Role | Status |
|---|---|---|
| Foundation team (RAID cycle 23) | Owns this contract + test fixture + registry entry | DRAFT (cycle-23 commit) |
| glossary-service team | Implements outbox table + emission + Publisher integration | NOT STARTED (Q-L5A-1 separate sub-program) |
| meta-worker team (cycle 24+) | Implements consumer (L5.B) + canon_projection writer (L5.D) | NOT STARTED (cycle 24 scope) |

When glossary-service team commits its outbox emitter, this doc moves to **SIGNED-OFF** with sign-off date + commit hash.

---

## §9. Related artifacts

| Path | Purpose |
|---|---|
| `contracts/events/canon.go` | Authoritative Go struct definitions (V1) |
| `contracts/events/canon_test.go` | Contract test fixture (Q-L5A-1 foundation deliverable) |
| `contracts/events/_registry.yaml` | Event type registry entries (4 new in cycle 23) |
| `contracts/events/generated/rust/canon_*.rs` | Rust mirror (auto-generated) |
| `contracts/events/generated/python/canon_*.py` | Python mirror (auto-generated) |
| `contracts/events/generated/ts/canon-*.ts` | TS mirror (auto-generated) |
| `contracts/migrations/per_reality/0009_canon_projection.up.sql` | Per-reality `canon_projection` table (L5.D foundation deliverable) |
| `contracts/migrations/per_reality/0010_canon_projection_indexes.sql` | Indexes (L5.D foundation deliverable) |
| `crates/projections/canon/` | Rust Projection trait impl (L5.D.3 foundation deliverable) |
| `docs/plans/2026-05-29-foundation-mega-task/L5_inbound_canon.md` | Parent layer plan |
