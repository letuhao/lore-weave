# 06 — Per-Category Contracts

> **Status:** LOCKED Phase 2b thin-rewrite (Option C redesign 2026-04-25). Per [EVT-A1](02_invariants.md#evt-a1--closed-set-event-taxonomy) closed-set + [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) sub-type ownership + [EVT-A12](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) extensibility framework, this file specifies the **envelope contract** for each active EVT-T* category and the **extensibility framework** for sub-types. Specific sub-shape enumerations live in feature design docs + [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md), NOT here.
> **Stable IDs:** No new IDs introduced — this file specifies contracts for active EVT-T1/T3/T4/T5/T6/T8.
> **Redesign note:** original Phase 2b (commit `2c35837`) enumerated specific sub-shapes (5 V1 commands, V1 aggregate types, AdminAction sub-shapes) that belong to feature designs and `_boundaries/02_extension_contracts.md`. This rewrite operates at envelope + extensibility framework abstraction; sub-shape enumeration is feature/boundary territory.

---

## How to use this file

When implementing a feature emitting events:

1. Find the EVT-T* category your feature uses in [`03_event_taxonomy.md`](03_event_taxonomy.md).
2. Implement the **common envelope** (§1 below) — every event carries it.
3. Pick or define a **sub-type** within that category. Sub-types live in **feature design docs** + are registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25).
4. Honor **per-category constraints** (§2-§7 below) — causal-ref policy, lifecycle stage, validator subset.
5. **Payload sizes + specific field types** are feature-declared with default guidance — CI lint enforces declared limits.

This file specifies the **mechanism**. Concrete sub-shape schemas (which fields each sub-type carries) live in feature docs (e.g., PL_001 §3.5 `TurnEvent` shape; PL_002 §6 command_args per CommandKind; `_boundaries/02_extension_contracts.md` §4 EVT-T8 sub-shape union).

---

## §1 Common envelope (ALL EVT-T* events share this)

Every event committed to a per-reality channel event log (or, for EVT-T6 Proposal, emitted onto the proposal bus) carries this envelope. Field types are abstract per scope rule O3 (no Rust code in spec).

| Field | Type | Required | Purpose |
|---|---|:---:|---|
| `event_id` | u64 | ✅ | DP-allocated `channel_event_id` per DP-A15 (gapless monotonic per channel). DP fills at commit. |
| `event_category` | EvtCategory enum | ✅ | EVT-T1..T11 discriminator. Closed-set per EVT-A1. Active values: T1/T3/T4/T5/T6/T8. |
| `event_sub_shape` | String | ✅ | Per-category sub-type discriminator (feature-defined per EVT-A11; closed-set within each category). |
| `event_schema_version` | u32 | ✅ | Envelope-level schema version. Increments on breaking envelope changes; sub-type additions are payload-internal additive. |
| `producer_service` | String | ✅ | Service-account name from JWT `sub` claim. Cross-references `_boundaries/01_feature_ownership_matrix.md` for current role binding. |
| `wall_clock_committed_at` | timestamp millis | ✅ | When DP committed (audit/replay). |
| `fiction_ts_start` | i64 millis | ✅ | Per MV12-D7. The fiction-time when the event begins. |
| `fiction_duration` | i64 millis | ✅ | Per MV12-D7. Duration in fiction-time. Often 0 for instant events. |
| `turn_number` | u64 | ✅ | Per DP-A17. Channel's current turn_number at commit (0 if channel never advanced). |
| `causal_refs` | Vec\<CausalRef\> | per-category | Per [EVT-A6](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free). Required policy varies by category — see §§ below. |
| `idempotency_key` | IdempotencyKey | ✅ | Uniform shape per [EVT-P*](04_producer_rules.md) — `(producer_service, client_request_id, target)`. |
| `payload` | category + sub-type-specific | ✅ | Feature-defined per sub-type. Schema declared in feature doc + extension contract. |

**Envelope max size:** ~512 bytes. Payload max size is **feature-declared** per sub-type with guidance defaults documented in `_boundaries/02_extension_contracts.md` §1 (TurnEvent envelope) for the most common case (EVT-T1 Submitted).

`CausalRef` shape (per [EVT-A6](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free)):
```
CausalRef {
  channel_id: ChannelId,
  channel_event_id: u64,
}
```
Both fields required. Validator pipeline enforces same-reality + reference-exists at commit time.

**TurnEvent envelope (subset of common envelope, used by EVT-T1 Submitted + sub-types):** authoritative shape lives in [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §1 — specifies Continuum-owned core fields (actor / intent / fiction_duration_proposed / narrator_text / canon_drift_flags / outcome / idempotency_key / causal_refs) + feature-extended fields per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25). This file does NOT duplicate that contract.

---

## §2 EVT-T1 Submitted

**Mechanism:** actor explicitly emits with intent (per [EVT-T1 taxonomy](03_event_taxonomy.md#evt-t1--submitted)).

**Lifecycle:** committed canonical via `dp::advance_turn`.

**Causal-ref policy:**
- PCTurn sub-types: optional (free narrative typically empty; chained commands may reference parent)
- NPCTurn sub-types: **REQUIRED** (refs the triggering Submitted event or scene-trigger)
- QuestOutcome (V1+): **REQUIRED** (refs QuestTrigger)

**Sub-types** (feature-defined; registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md)): see TurnEvent envelope at [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §1 for current Continuum-owned core + feature-extended fields. Specific sub-type contracts live in:
- PL_001 §3.5 + PL_002 §6 (PCTurn variants)
- NPC_001 §2.5 + NPC_002 §2.5 (NPCTurn variants — note NPC_002 covers multi-NPC orchestration ordering)
- Future quest-service design (QuestOutcome)

**Validator subset (per `_boundaries/03_validator_pipeline_slots.md`):** schema → capability → A5 intent classify → A5 command dispatch (if MetaCommand sub-type) → A6 5-layer (if originated from EVT-T6 Proposal) → world-rule lint → canon-drift → causal-ref integrity → commit.

**Payload size guidance:** ~10 KB envelope+payload typical for narrative sub-types; feature-tuned. **Flavor content (per [EVT-A8](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25))** is excluded from event payload — pointer-only via `flavor_text_audit_id`.

**Cross-ref:** [`03_event_taxonomy.md` EVT-T1](03_event_taxonomy.md#evt-t1--submitted), [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §1.

---

## §3 EVT-T3 Derived

**Mechanism:** side-effect state delta of another event (per [EVT-T3 taxonomy](03_event_taxonomy.md#evt-t3--derived)).

**Lifecycle:** committed canonical via `dp::t2_write` / `dp::t3_write` / `dp::t3_write_multi` (atomic).

**Causal-ref policy:** optional but **strongly recommended** when the Derived event is caused by a parent (FictionClockAdvance after PCTurn, calibration sub-shapes after FictionClock advance, etc.). Default for design: include causal-ref to parent for replay-graph completeness.

**Sub-types:** discriminated by **`aggregate_type` field**, not by sub-shape name. Each `(aggregate_type, delta_kind)` pair is a sub-type. Aggregate-type ownership is registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) "Aggregate ownership" section.

**Validator subset:** schema → capability (DP-K9 `write:` claim per aggregate-type/tier/scope) → world-rule lint → causal-ref integrity → commit. **No A6 injection defense** — Derived is producer-trusted output of an Aggregate-Owner role, not LLM input.

**Payload size guidance:** ~5 KB envelope+payload typical for state deltas; feature-tuned. Larger deltas should split into multiple commits or use `t3_write_multi` for atomicity.

**Cross-ref:** [`03_event_taxonomy.md` EVT-T3](03_event_taxonomy.md#evt-t3--derived), [DP-K5 Write primitives](../06_data_plane/04b_read_write.md#dp-k5--write-primitives-tier-typed), aggregate ownership matrix.

---

## §4 EVT-T4 System

**Mechanism:** DP-internal lifecycle (per [EVT-T4 taxonomy](03_event_taxonomy.md#evt-t4--system)).

**Lifecycle:** committed canonical, immutable, DP-internal emission.

**Causal-ref policy:** N/A — DP-internal.

**Sub-types:** **closed set, locked by DP** — see [`03_event_taxonomy.md` EVT-T4 sub-types table](03_event_taxonomy.md#evt-t4--system). Event Model classifies; does NOT redesign.

**Validator subset:** **none** — SystemEvents are trusted by construction.

**Payload size:** typically <2 KB; bounded by DP operation context (member info, lifecycle state, slot timestamps).

**Note on TurnBoundary:** the `turn_data` field of TurnBoundary IS the EVT-T1 Submitted payload (Phase 0 B1 wire-format decision). Two lenses, same wire bytes.

**Cross-ref:** [`03_event_taxonomy.md` EVT-T4](03_event_taxonomy.md#evt-t4--system), [DP-A18](../06_data_plane/02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25), [DP-A17](../06_data_plane/02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25), [DP-Ch51](../06_data_plane/21_llm_turn_slot.md).

---

## §5 EVT-T5 Generated

**Mechanism:** rule/aggregator/scheduler emits based on condition + probability + deterministic RNG (per [EVT-T5 taxonomy](03_event_taxonomy.md#evt-t5--generated) + [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25)).

**Lifecycle:** committed canonical via aggregator runtime (DP-Ch26) or scheduler primitive (Phase 4).

**Causal-ref policy:** **REQUIRED.** Every Generated event references at least one source event (the trigger). For BubbleUp: descendant source events. For Scheduled: the CalibrationEvent or fiction-time-marker that crossed threshold.

**Sub-types:** feature-defined per Generator (BubbleUp:* aggregator type; Scheduled:* scheduler type). Registered in `_boundaries/01_feature_ownership_matrix.md` Generator-rows.

**Validator subset:** schema → capability → causal-ref integrity → world-rule lint (optional per Generator) → commit. **No A6** (no LLM input on emit path; Generator code is feature-trusted). **EVT-A9 RNG determinism enforced at lint time** + replay test.

**Payload size guidance:** feature-tuned per Generator; typically 5 KB. Aggregator state separately capped 1 MB per DP-Ch26 (distinct from emit payload).

**Cross-ref:** [`03_event_taxonomy.md` EVT-T5](03_event_taxonomy.md#evt-t5--generated), [EVT-A9](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25), [DP-Ch25..Ch30](../06_data_plane/16_bubble_up_aggregator.md), [`08_scheduled_events.md`](08_scheduled_events.md) (Phase 4).

---

## §6 EVT-T6 Proposal

**Mechanism:** untrusted-origin pre-validation message on the proposal bus (per [EVT-T6 taxonomy](03_event_taxonomy.md#evt-t6--proposal) + [EVT-A7](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25)).

**Lifecycle stages:** `Proposal` (pre-validation, on bus) → `Validated` (promoted to EVT-T1 Submitted, fresh event committed; original proposal not retained) | `Rejected { reason }` (logged + dead-lettered) | `Expired` (bus retention elapsed).

**Causal-ref policy:** optional (NPCTurnProposal typically references the triggering Submitted event).

**Sub-types:** feature-defined based on which Submitted shape they propose (e.g., PCTurnProposal → PCTurn after validation; NPCTurnProposal → NPCTurn). Registered in `_boundaries/`.

**Validator subset:** **FULL EVT-V* pipeline** runs ON the proposal as input. Output is `Validated → commit fresh Submitted` or `Rejected → dead-letter`.

**Payload size guidance:** ~12 KB on bus (slightly larger than committed Submitted to accommodate LLM-generated text before output filter trims).

**Bus retention default:** ~60s (operational tunable, not Event Model lock); detailed protocol in [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) (Phase 3).

**Cross-ref:** [`03_event_taxonomy.md` EVT-T6](03_event_taxonomy.md#evt-t6--proposal), [EVT-A7](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25), [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state), [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) (Phase 3).

---

## §7 EVT-T8 Administrative

**Mechanism:** operator-emitted via S5 admin-action policy (per [EVT-T8 taxonomy](03_event_taxonomy.md#evt-t8--administrative)).

**Lifecycle:** committed canonical, immutable, audit-grade. `admin_action_audit` table mirrors per S5.

**Causal-ref policy:** optional. Used when the action targets a specific event.

**Sub-types:** feature-defined per admin command. Authoritative union locked in [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §4 — currently 16+ sub-shapes across core-admin (Pause/Resume/ForceEndScene/WorldRuleOverride), Forge (ForgeEdit), Charter (Charter*), Succession (Succession*), Mortality (provisional MortalityAdminKill).

**Validator subset:** schema → capability (S5 actor authentication + impact-class gating) → S5 dual-actor (Tier 1 only) → world-rule lint (optional — admin may override) → causal-ref integrity → commit. **No A6** — admin input is operator-authenticated, not adversarial.

**Payload size guidance:** ~4 KB (admin reasons may be long per S5 — Tier 1 requires 100+ char reason).

**Cross-ref:** [`03_event_taxonomy.md` EVT-T8](03_event_taxonomy.md#evt-t8--administrative), S5 ADMIN_ACTION_POLICY, [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §4 (sub-shape ownership).

---

## §8 Schema versioning summary

Per [EVT-A12](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) extensibility framework + I14 additive-first:

- **Envelope `event_schema_version`** increments on **breaking envelope changes** — adding a required field, changing field type, removing a field.
- **Sub-type additions** (new sub-shape under existing category, registered in `_boundaries/`) are **payload-internal additive evolution** — envelope version stays the same.
- **Per-sub-shape additions** (new optional field on existing sub-shape) are **fully additive** — consumers ignore unknown fields per I14.
- **Adding a new EVT-T* category** = locked-decision in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md) + axiom-level update to EVT-A1 + envelope version bump (per EVT-A12 extension point (b)).

Detailed migration protocol — including upcaster shape, dual-read window, schema-version-mismatch resolution — locks in Phase 4 [`11_schema_versioning.md`](11_schema_versioning.md) (resolves DP Q5 + EVT-Q9).

---

## §9 Extension contract summary

Per [EVT-A12](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25), events extend along 6 well-defined points. Quick reference:

| # | Extension point | Mechanism | Where coordinated |
|---|---|---|---|
| (a) | New sub-type within existing category | Additive per I14 + register in boundary matrix per EVT-A11 | `_boundaries/01_feature_ownership_matrix.md` |
| (b) | New EVT-T* category | Axiom-level decision; user sign-off → add row to `03_event_taxonomy.md` | This folder + locked decisions |
| (c) | New envelope field | Schema bump per Phase 4 EVT-S* | [`11_schema_versioning.md`](11_schema_versioning.md) |
| (d) | New validator stage | Coordinated via boundary slot ordering | `_boundaries/03_validator_pipeline_slots.md` |
| (e) | New producer role class | Update EVT-A4 + JWT capability schema | EVT-A4 + DP-K9 |
| (f) | New generation rule (under EVT-T5) | Register aggregator/scheduler; MUST honor EVT-A9 RNG determinism | `_boundaries/01_feature_ownership_matrix.md` aggregator rows |

Extensions outside these 6 points are FORBIDDEN per EVT-A12.

---

## Locked-decision summary

| EVT-T* | Sub-types live | Causal-ref | Validator subset | Sub-shape SSOT |
|---|---|---|:---:|---|
| T1 Submitted | feature docs (PL_001/PL_002/NPC_001/NPC_002) + boundary matrix | per sub-type | full pipeline | `_boundaries/02_extension_contracts.md` §1 |
| T3 Derived | aggregate-type per feature; sub-discriminator = aggregate_type | recommended | no A6 | `_boundaries/01_feature_ownership_matrix.md` aggregate rows |
| T4 System | DP-locked closed set | N/A | none | DP-A18 / DP-Ch51 / DP-A17 |
| T5 Generated | per-Generator feature; BubbleUp:* / Scheduled:* | required | no A6; EVT-A9 RNG | `_boundaries/01_feature_ownership_matrix.md` Generator rows |
| T6 Proposal | feature-defined per target Submitted shape | optional | full pipeline as input | feature originator docs + Phase 3 bus protocol |
| T8 Administrative | feature docs + boundary matrix; 16+ sub-shapes | optional | S5 + capability + world-rule (no A6) | `_boundaries/02_extension_contracts.md` §4 |

---

## Cross-references

- [EVT-A1 closed-set taxonomy](02_invariants.md#evt-a1--closed-set-event-taxonomy) — invariant this contract serves
- [EVT-A6 typed causal-refs](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free) — `CausalRef` shape
- [EVT-A8 non-canonical regenerable content](02_invariants.md#evt-a8--non-canonical-regenerable-content-is-not-events-reframed-2026-04-25) — flavor exclusion rule
- [EVT-A11 sub-type ownership](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) — enforces feature-level sub-type ownership
- [EVT-A12 extensibility framework](02_invariants.md#evt-a12--extensibility-framework-new-2026-04-25) — 6 extension points
- [`03_event_taxonomy.md`](03_event_taxonomy.md) — EVT-T* definitions
- [`04_producer_rules.md`](04_producer_rules.md) — EVT-P* producer authorization
- [`11_schema_versioning.md`](11_schema_versioning.md) — Phase 4 EVT-S* migration protocol (resolves DP Q5)
- [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) — sub-type + aggregate ownership SSOT
- [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) — TurnEvent envelope §1 + AdminAction sub-shapes §4 (authoritative)
- [`../_boundaries/03_validator_pipeline_slots.md`](../_boundaries/03_validator_pipeline_slots.md) — current validator pipeline ordering
- [PL_001 §3.5](../features/04_play_loop/PL_001_continuum.md) — TurnEvent envelope + Continuum-owned core
- [PL_002 §6](../features/04_play_loop/PL_002_command_grammar.md) — PCTurn::MetaCommand sub-types (5 V1 commands)
- [NPC_001 §2.5](../features/05_npc_systems/NPC_001_cast.md) — NPCTurn sub-shapes + ActorId enum
- [NPC_002 §2.5](../features/05_npc_systems/NPC_002_chorus.md) — multi-NPC orchestration
- [DP-A18](../06_data_plane/02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25) — System sub-types
- [DP-Ch43 redaction policy](../06_data_plane/19_privacy_redaction_policies.md) — Generated::BubbleUp redaction
- [05_llm_safety A5-D1](../05_llm_safety/01_intent_classifier.md) — `intent_class` enum
