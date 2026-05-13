# 11 — Schema Versioning Framework (EVT-S*)

> **Status:** LOCKED Phase 4b (Option C discipline 2026-04-25). Per [EVT-A12 extensibility framework](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) extension point (c) "new envelope field" + foundation [I14 additive-first schema evolution](../00_foundation/02_invariants.md), this file specifies the **schema-versioning framework** for events at mechanism level.
> **Stable IDs:** EVT-S1..EVT-S6.
> **Resolves:** [DP Q5 schema migration protocol](../06_data_plane/99_open_questions.md) — at the per-event-type schema layer (DP owns the multi-instance migration choreography per DP-C5; this file owns the per-event-type schema rules). Plus [EVT-Q7](99_open_questions.md) (schema version field placement) + [EVT-Q9](99_open_questions.md) (DP Q5 boundary).

---

## How to use this file

When evolving an event schema (envelope or sub-shape):

1. Determine the **change class** (additive vs breaking — EVT-S1).
2. For additive: add the field as optional, no version bump needed (EVT-S2 forward-compat).
3. For breaking: bump the appropriate schema version (envelope or sub-shape per EVT-S1) + write upcaster (EVT-S3) + plan migration triggers (EVT-S4).
4. Test replay against the migrated schema (EVT-S5).
5. Coordinate with DP-C5 multi-instance migration choreography (EVT-S6 boundary).

This file specifies the **per-event-type schema rules**. Multi-instance migration coordination (rolling out a schema bump across N running services) is owned by DP-C5.

---

## EVT-S1 — Schema version field placement (resolves EVT-Q7)

**Rule:** Schema versions are tracked at **two levels**:

**Envelope level — `event_schema_version: u32` field on the common envelope** (per [`06_per_category_contracts.md` §1](06_per_category_contracts.md)):
- Increments on **breaking envelope changes** (adding required envelope field, changing field type, removing field).
- Single counter shared across all categories (envelope is universal).
- Default V1 starting value: `1`.

**Sub-shape level — implicit schema version per `(event_category, event_sub_shape)` pair**:
- Tracked by feature-owned sub-shape contract (in feature design + `_boundaries/02_extension_contracts.md`).
- Increments on **breaking sub-shape changes** (additive optional fields don't increment).
- Default starting value per new sub-shape: `1`.

**Rationale for two levels:**
- Envelope changes affect ALL events; one global counter avoids per-category drift.
- Sub-shape changes affect only events of that sub-shape; per-(category, sub-shape) counter avoids forcing global bump for feature-local evolution.

**Both versions on every event:** the envelope's `event_schema_version` is canonical; the sub-shape version is implicit (consumers inspect the sub-shape's payload structure to determine version OR features add an explicit `payload_schema_version` field within the payload — feature-level decision).

**Why u32 not semver:** events are append-only canonical records; the "version" is monotonically increasing release counter, not API compatibility designation. u32 keeps it simple.

**Cross-ref:** [`06_per_category_contracts.md` §1 Common envelope](06_per_category_contracts.md), [EVT-Q7 schema version field placement](99_open_questions.md), foundation I14 additive-first.

---

## EVT-S2 — Forward-compat rules (when may producers emit v_n+1 while consumers still on v_n)

**Rule:** Producers MAY emit a new schema version **only after consumers have been deployed with support for the new version** OR the change is purely additive optional fields (which consumers ignore by default per I14). Specifically:

**Pure additive change (new optional field, new sub-shape, new EVT-T* category sub-type):**
- Producers may emit immediately on deployment of new feature code.
- Consumers receiving unknown additive content ignore it (forward-compat by I14 invariant).
- No version bump needed at envelope level; sub-shape-level bump if sub-shape contract changes.

**Breaking change (required field added, field type changed, field removed):**
- **Two-phase rollout** required:
  - Phase A: deploy NEW consumer code that handles BOTH old and new versions (upcaster per EVT-S3 reads old v_n events into new v_n+1 in-memory representation).
  - Phase B: deploy NEW producer code that emits v_n+1.
  - During the deployment window between Phase A and Phase B, consumer reads still hit some old v_n events in the log; upcaster handles them.
- **Forbidden:** producer emitting v_n+1 before consumers support it (would cause `DpError::SchemaVersionMismatch` storms).

**Coordination mechanism:** DP-C5 owns the deployment-orchestration to ensure Phase A precedes Phase B across N service instances. Event Model specifies the per-event-type rule; DP-C5 enforces multi-instance order.

**Cross-ref:** [DP-C5 schema migration coordination](../06_data_plane/05_control_plane_spec.md), foundation I14, [EVT-S3 upcasters](#evt-s3--backward-compat--upcasters-when-may-consumer-drop-fields).

---

## EVT-S3 — Backward-compat + upcasters (when may consumer drop fields)

**Rule:** Consumers MAY drop a field only after **all event-log retention windows that may contain events with that field have expired** OR the consumer code path doesn't read that field. Specifically:

**Reading old events:**
- Consumer code MUST handle ALL retained schema versions readable from event log.
- **Upcaster pattern**: a function `fn upcast_v_n_to_v_n_plus_1(v_n: VnPayload) -> VnPlus1Payload` that translates older payload to current in-memory representation. Consumer code reads via upcasters; only the latest in-memory representation appears in business logic.
- Upcasters are **append-only** — if v1 → v2 → v3 upcaster chain exists, removing v1→v2 mid-chain breaks v1 event reads.

**Removing field support:**
- Field that's no longer read by any consumer code path MAY be considered "deprecated" — but the field still appears in old events.
- Removing the field from the **codebase** (i.e., upcaster no longer translates it) is safe ONLY after **event log retention** for events containing that field has elapsed (per S8-D3 retention tiers).
- For canonical events with `Forever` retention tier (canon_entries, etc.), upcasters MUST be retained indefinitely.

**Why upcasters indefinitely for forever-retained:** event log is canonical; old events with old fields exist forever; consumer code reading from old positions must handle them. Removing upcasters would break replay (per EVT-A10 universal SSOT).

**Forbidden:** dropping upcaster code while events with that schema version remain in retention; reading old events via heuristic field-detection (must use explicit version-keyed dispatch).

**Cross-ref:** [EVT-A10 universal SSOT](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25), foundation I14, [DP Q5 schema migration](../06_data_plane/99_open_questions.md), S8-D3 retention tiers.

---

## EVT-S4 — Migration triggers (when to bump)

**Rule:** Schema version bumps are **deliberate** — every bump requires:

1. **Justification** in feature design or boundary review: why the change can't be additive.
2. **Upcaster prepared** for previous version (mandatory before deploy).
3. **Two-phase rollout plan** per EVT-S2 (Phase A consumer deploy, Phase B producer deploy).
4. **DP-C5 coordination** for multi-instance migration choreography.
5. **Replay test** against migrated schema per EVT-S5.

**Specific triggers that warrant a bump:**
- Field type incompatibility (e.g., `i32` → `i64` is fine via upcaster widening; `String` → typed enum may need bump if old strings can't all be parsed).
- Required field added (consumers MUST receive a value, so old events lacking it need an upcaster default).
- Field semantics changed (same name + type but different meaning — RARE; should split into different field if possible).
- Sub-shape discriminator removed (changes pattern matching — breaking).

**Not requiring a bump:**
- New optional field (additive per I14).
- New sub-shape under existing category (registered in `_boundaries/`; no envelope bump per EVT-A12 extension point (a)).
- New EVT-T* category (axiom-level decision per EVT-A12 (b); affects taxonomy + envelope `event_category` enum extension; **does** bump envelope version).

**Frequency expectation:** envelope bumps should be **rare** (once per year or less once V1 stable). Sub-shape bumps may be more frequent during V1 evolution but should still be deliberate.

**Cross-ref:** [EVT-A12 extensibility framework](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25), [EVT-S5 replay testing](#evt-s5--replay-against-migrated-schemas), DP-C5 migration coordination.

---

## EVT-S5 — Replay against migrated schemas

**Rule:** When schema bumps occur, **replay correctness MUST be verified** by running the time-travel debug replay (per [EVT-L18](10_replay_semantics.md#evt-l18--time-travel-debug-replay-resolves-evt-q10)) against representative event log segments containing both old and new versions. The replay's structural-only mode MUST produce bit-identical projection state pre-migration vs post-migration (modulo intentional semantic changes).

**Test harness pattern:**
- Capture a representative event log segment from a staging reality (e.g., last 1000 events).
- Run replay with v_n consumer → projection state P_n.
- Apply schema bump: deploy v_n+1 consumer with upcaster.
- Run replay with v_n+1 consumer over the SAME event log → projection state P_n+1.
- Assert: P_n+1 ≡ P_n for all unchanged fields. New fields default per upcaster spec.

**CI integration:** replay tests run as part of release gate. Schema-bump PRs MUST include test-segment captures + assertion of replay invariance. Gate fails if invariance broken.

**Why replay testing is critical:** schema bumps are the most error-prone operation in event-sourced systems — a bad upcaster silently corrupts state on replay. Testing forces the producer of the bump to demonstrate replay-correctness BEFORE merge.

**Bound on replay-test segment size:** segment must cover all sub-types affected by the bump. For envelope bumps, segment should sample from all categories (typically 10-50 events per category sufficient).

**Cross-ref:** [EVT-L18 time-travel debug replay](10_replay_semantics.md#evt-l18--time-travel-debug-replay-resolves-evt-q10), [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25), CI integration patterns (DP-C5 + foundation I14).

---

## EVT-S6 — DP Q5 boundary + EVT-S* / DP-C5 split

**Rule:** Schema migration is a **two-layer concern**:

**Layer 1 — Per-event-type schema rules** (this file, EVT-S*):
- Envelope vs sub-shape version field placement (EVT-S1).
- Forward-compat + backward-compat rules (EVT-S2 + EVT-S3).
- Upcaster contract (EVT-S3).
- Migration triggers (EVT-S4).
- Replay-correctness testing (EVT-S5).

**Layer 2 — Multi-instance migration choreography** (DP-C5, owned by DP):
- Rolling deployment of consumer code first, then producer.
- Service-instance discovery + version-mismatch detection.
- Rollback mechanism if migration fails.
- Coordination across DP cluster instances.

**Boundary rule:** EVT-S* defines "what shape is the data + how does it evolve". DP-C5 defines "how do replicas reconcile during the rollout". A schema bump goes through BOTH:
1. Author EVT-S contracts (this file rules) → upcaster + replay tests.
2. DP-C5 orchestrates the rollout (Phase A consumer deploy → Phase B producer deploy).

**Resolves DP Q5** ("schema migration protocol — actually belongs here") — at the per-event-type contract layer. DP Q5 deferred the "how" of migration; this file owns the per-event-type "how"; DP-C5 owns the multi-instance "how".

**Forbidden:** schema bumps that go through ONE layer only. A bump without DP-C5 coordination causes mid-rollout `SchemaVersionMismatch` storms. A DP-C5 rollout without EVT-S contract causes silent data corruption (no upcaster, consumer reads garbage).

**Cross-ref:** [DP-C5 schema migration coordination](../06_data_plane/05_control_plane_spec.md), [DP Q5 in DP open questions](../06_data_plane/99_open_questions.md), [EVT-Q9 DP Q5 boundary](99_open_questions.md).

---

## Locked-decision summary

| ID | Short name | One-line |
|---|---|---|
| EVT-S1 | Schema version field placement (EVT-Q7 resolved) | Envelope-level `event_schema_version: u32` (universal); sub-shape-level implicit per (category, sub-shape); both monotonic |
| EVT-S2 | Forward-compat rules | Pure additive: emit immediately. Breaking: two-phase rollout (Phase A consumer + upcaster, then Phase B producer) |
| EVT-S3 | Backward-compat + upcasters | Append-only upcaster chain; consumers handle ALL retained versions; field removal only after retention expiry |
| EVT-S4 | Migration triggers | Bumps require justification + upcaster + two-phase plan + DP-C5 coordination + replay test |
| EVT-S5 | Replay against migrated schemas | Bumps run replay tests; CI gate enforces invariance for unchanged fields |
| EVT-S6 | DP Q5 boundary (EVT-Q9 resolved) | EVT-S* owns per-event-type schema rules; DP-C5 owns multi-instance migration choreography; bumps go through BOTH |

---

## Cross-references

- [EVT-A12 extensibility framework](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) — extension point (c) "new envelope field"
- [EVT-A10 universal SSOT](02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25) — drives EVT-S3 upcaster permanence
- [`06_per_category_contracts.md` §1 Common envelope](06_per_category_contracts.md) — envelope field placement
- [`10_replay_semantics.md` EVT-L18](10_replay_semantics.md#evt-l18--time-travel-debug-replay-resolves-evt-q10) — replay testing harness
- [DP-C5 schema migration coordination](../06_data_plane/05_control_plane_spec.md) — multi-instance migration choreography
- [DP-K3 SchemaVersionMismatch error variant](../06_data_plane/04a_core_types_and_session.md#dp-k3--dperror-enum) — runtime detection
- [DP Q5 schema migration protocol](../06_data_plane/99_open_questions.md) — resolved by this file at per-event-type layer
- foundation I14 additive-first schema evolution
- [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §1 — TurnEvent envelope evolution rules
- S8-D3 retention tiers — bounds upcaster lifecycle
