# 04 — Producer Rules (EVT-P*)

> **Status:** LOCKED Phase 2a thin-rewrite (Option C redesign 2026-04-25). Per [EVT-A4](02_invariants.md#evt-a4--producer-role-binding-reframed-2026-04-25) producer-ROLE binding, this file specifies the **role-level** producer contract for each active EVT-T* category. Specific service-name binding (which Rust service plays which role for V1) lives in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md), NOT here.
> **Stable IDs:** EVT-P1..EVT-P11 reserved; **6 active** (P1, P3, P4, P5, P6, P8) + **5 retired** (P2, P7, P9, P10, P11 — `_withdrawn` per I15, mirroring EVT-T* retirements).
> **Redesign note:** original Phase 2a (commit `25ef117`) named specific services (world-service / quest-service / pc-service / etc.) — that overreached into feature/architecture territory. This rewrite operates at role-class abstraction; service-binding is feature design.

---

## How to use this file

When designing a feature that emits events:

1. Identify the **producer role class** your service plays (EVT-A4 lists 6: Player-Actor / Orchestrator / Aggregate-Owner / Generator / LLM-Originator / Administrative / DP-Internal).
2. For each EVT-T* category your service produces, find the matching EVT-P* row below and confirm:
   - Your role is in the `Authorized producer roles` list
   - Your service-account JWT carries the `produce: [EVT-T*]` claim per the role's capability pattern
3. **Compose idempotency key** per the uniform shape `(producer_service, client_request_id, target)`.
4. **Declare rate-limit defaults** in your feature design; CI lint enforces them at runtime.
5. **Register your service↔role binding** in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).

Specific values like JWT claim shapes, rate-limit numbers, dead-letter topics — those are feature/operational design, not Event Model lock. This file specifies the **mechanism**, not the numbers.

---

## Uniform idempotency key (all EVT-P*)

Every event carries an `idempotency_key` of shape:

```
IdempotencyKey {
  producer_service: String,      // service-account name from JWT `sub` claim
  client_request_id: UUID,       // producer-generated; uniqueness within (producer, target) pair
  target: TargetRef,             // category-specific: channel / aggregate-id / proposal-id
}
```

Categories may add **narrower uniqueness** at commit (e.g., EVT-T1 Submitted enforces `(reality_id, session_id, turn_seq)` per R7 single-writer-per-session in addition to the uniform key). Commit primitive rejects duplicate keys with the existing event's `event_id` returned (idempotent retry).

---

## Capability JWT shape (abstract)

Every producing service's JWT carries a `produce: [EVT-T*]` list claim per [EVT-A4](02_invariants.md#evt-a4--producer-role-binding-reframed-2026-04-25). Role-specific extensions:

| Role | Required claims |
|---|---|
| Player-Actor | (handled at gateway authentication; PCs don't have direct produce claim — gateway forwards to commit-service) |
| Orchestrator | `produce: [Submitted]` + role-specific generation claims |
| Aggregate-Owner | `produce: [Derived]` + DP-K9 `write: [{aggregate_type, tier, scope}]` per aggregate owned |
| Generator | `produce: [Generated]` + DP-Ch25 `can_register_aggregator: [level]` for BubbleUp generators OR scheduler-specific claim for Scheduled generators |
| LLM-Originator | `produce: [Proposal]` ONLY — never canonical categories (per [EVT-A7](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25)) |
| Administrative | `produce: [Administrative]` + S5 admin command registry claims |
| DP-Internal | N/A — DP itself; no service-level JWT |

Concrete JWT shape (field names, encoding, signing key rotation) is owned by [DP-K9](../06_data_plane/04d_capability_and_lifecycle.md#dp-k9--capability-tokens). Event Model only specifies the `produce` claim and its enforcement.

---

## EVT-P1 — Submitted (EVT-T1)

**Authorized producer roles:** Player-Actor (via gateway-trusted commit-service) · Orchestrator (multi-NPC reactions, batch coordination) · future quest-engine (QuestOutcome sub-type).

**Originator vs producer:** Originator may differ from producer. PC submission originates from gateway → roleplay-service (Python LLM may rewrite text); commit-service (Rust) is the **producer** that holds the `produce: [Submitted]` claim and commits the validated event. NPC reaction proposal originates from roleplay-service per Orchestrator's request; same commit-service is the producer. The originator → producer split is the realization of [EVT-A7](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25): untrusted originators emit Proposals; trusted producers commit Submitted.

**Idempotency key target:** typically `(channel_id, session_id)` for PCTurn; `(channel_id, npc_id)` for NPCTurn. Feature design declares.

**Rate-limit policy:** per-session + per-channel + per-reality semantic limits, **declared by feature, lint-checked at runtime**. No specific numbers locked here. Default guidance: per-session ≤ X turns/sec where X is feature-tuned (PL_001 may default to 2-5/sec; high-traffic features adjust). Excess → `EventModelError::SemanticRateLimited { retry_after }` (never silently drop).

**Forbidden producer roles:** LLM-Originator (cannot commit canonical Submitted directly; must propose) · Administrative (uses EVT-T8 Administrative for admin-initiated changes) · DP-Internal · Generator.

**Service-binding (V1, see boundary matrix for current):** typically a single Rust commit-service plays the Player-Actor + Orchestrator roles for both PCTurn and NPCTurn sub-types (per `_boundaries/01_feature_ownership_matrix.md`).

**Cross-ref:** [EVT-T1 Submitted](03_event_taxonomy.md#evt-t1--submitted), [EVT-A7 untrusted-origin proposal](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25), [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).

---

## EVT-P2_withdrawn (was NPCTurn)

**Reason:** EVT-T2 NPCTurn `_withdrawn` per Option C redesign — NPCTurn is a sub-type of EVT-T1 Submitted. Producer rule subsumed by EVT-P1.

---

## EVT-P3 — Derived (EVT-T3)

**Authorized producer roles:** Aggregate-Owner per-feature. Each feature owns specific aggregate types listed in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).

**Idempotency key target:** typically `(reality_id, aggregate_id)` for RealityScoped or `(reality_id, channel_id, aggregate_id)` for ChannelScoped.

**Rate-limit policy:** per tier × scope, feature-declared. T1 (Volatile) tolerates high-frequency per-session writes; T3 (Durable-sync) is design-time-bounded. Specific defaults locked in feature designs that own each aggregate type.

**Forbidden producer roles:** LLM-Originator (per DP-A6 + EVT-A7) · Administrative (uses EVT-T8 with side-effects on aggregates derived through EVT-T3 by the same commit-service) · DP-Internal.

**Cross-ref:** [EVT-T3 Derived](03_event_taxonomy.md#evt-t3--derived), [DP-K5 Write primitives](../06_data_plane/04b_read_write.md#dp-k5--write-primitives-tier-typed), aggregate ownership matrix.

---

## EVT-P4 — System (EVT-T4)

**Authorized producer roles:** **DP-Internal only.** Cannot be emitted from any service.

**Capability JWT:** N/A — DP-internal. Reserved discriminators (per DP-A18 / DP-Ch52) reject feature emission attempts at SDK type system.

**Idempotency:** DP-internal (DP-Ch11 channel_event_id allocation handles uniqueness via per-channel monotonic counter).

**Rate-limit:** N/A — bounded by DP operation rates (DP-R6 transport rate-limit).

**Forbidden producer roles:** **ALL feature roles.** This is a defense-in-depth axiom — even compromised services cannot forge System events.

**Cross-ref:** [EVT-T4 System](03_event_taxonomy.md#evt-t4--system), [DP-A18](../06_data_plane/02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25).

---

## EVT-P5 — Generated (EVT-T5)

**Authorized producer roles:** Generator (Synthetic actor — registered aggregator instances per DP-Ch25; future scheduler instances; future probabilistic-RNG-based emitters).

**Idempotency key target:** `(generator_id, source_event_refs_hash)` for BubbleUp aggregators; `(scheduler_id, fired_at_fiction_ts)` for Scheduled generators. Feature design declares.

**Rate-limit policy:** structural limits enforced by DP-Ch29 (1 emit/source-event/aggregator + 1 MB state cap + 16-level cascade cap). Semantic limits feature-declared per Generator type.

**Critical constraint:** [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) — every Generator MUST use `dp::deterministic_rng(channel_id, channel_event_id)` (or equivalent SDK-provided seed). Wall-clock + non-deterministic sources forbidden at lint time. Replay tests verify.

**Forbidden producer roles:** Player-Actor (cannot self-generate as PC) · LLM-Originator (no LLM Proposal → Generated path; Generators are deterministic-feature-trusted) · DP-Internal.

**Cross-ref:** [EVT-T5 Generated](03_event_taxonomy.md#evt-t5--generated), [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25), [DP-Ch25..Ch30](../06_data_plane/16_bubble_up_aggregator.md), [`08_scheduled_events.md`](08_scheduled_events.md) (Phase 4).

---

## EVT-P6 — Proposal (EVT-T6)

**Authorized producer roles:** LLM-Originator (current V1: Python LLM-driven service; future: any untrusted-origin agentic/plugin service).

**Capability JWT:** `produce: [Proposal]` ONLY. **Critically:** no `produce: [Submitted | Derived | Generated | Administrative]`, no `can_advance_turn`, no `can_register_aggregator`. Even compromised LLM-Originator code cannot directly commit canonical events.

**Idempotency key target:** `(producer_service, proposal_id, target_channel)`. Producer generates `proposal_id` per LLM-completion; trusted commit-service uses it to dedupe consume.

**Rate-limit policy:** per-session bus admission, feature-declared. Bus retention default 60s (proposal expires if validator doesn't consume). Excess → bus backpressure → producer-side backpressure to upstream (gateway → user toast "system busy, retry").

**Forbidden producer roles:** any role with `produce: [<canonical category>]` claim — they cannot also produce Proposals (would defeat the trust separation).

**Lifecycle terminals:** `Validated` (promoted to EVT-T1 Submitted; original proposal not retained as event) · `Rejected { reason }` (logged + dead-lettered; producer/originator sees soft-fail UX) · `Expired` (bus retention elapsed without validator consume).

**Cross-ref:** [EVT-T6 Proposal](03_event_taxonomy.md#evt-t6--proposal), [EVT-A7 untrusted-origin lifecycle](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25), [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state), [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) (Phase 3).

---

## EVT-P7_withdrawn (was CalibrationEvent)

**Reason:** EVT-T7 CalibrationEvent `_withdrawn` per Option C redesign — calibration is an EVT-T3 Derived sub-type (DayPasses / MonthPasses / YearPasses are derived from FictionClock advance). Producer rule subsumed by EVT-P3.

---

## EVT-P8 — Administrative (EVT-T8)

**Authorized producer roles:** Administrative (admin-cli via S5 dispatch).

**Capability JWT:** `produce: [Administrative]` + S5 admin command registry claims (per ADMIN_ACTION_POLICY §R4).

**Idempotency key target:** `(producer="admin-cli", admin_command_id, target_id)`.

**Rate-limit policy:** N/A semantic-rate; S5 cooldowns enforce per-actor (Tier 1: 24h cooldown; Tier 2: weekly review; Tier 3: standard auth).

**Forbidden producer roles:** **ALL non-admin-cli services.** S5 dispatch is the single chokepoint; service-to-service calls cannot forge Administrative events.

**Cross-ref:** [EVT-T8 Administrative](03_event_taxonomy.md#evt-t8--administrative), S5 ADMIN_ACTION_POLICY, [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §4 (sub-shape ownership).

---

## EVT-P9_withdrawn (was QuestBeat)

**Reason:** EVT-T9 QuestBeat `_withdrawn` per Option C redesign — split into EVT-P1 (QuestOutcome → Submitted) + EVT-P3 (QuestAdvance → Derived) + EVT-P5 (QuestTrigger → Generated). Producer rule split across P1/P3/P5.

---

## EVT-P10_withdrawn (was NPCRoutine)

**Reason:** EVT-T10 NPCRoutine `_withdrawn` per Option C redesign — NPCRoutine is an EVT-T5 Generated sub-type (Scheduled:NPCRoutine emitted by world-rule-scheduler). Producer rule subsumed by EVT-P5.

---

## EVT-P11_withdrawn (was WorldTick)

**Reason:** EVT-T11 WorldTick `_withdrawn` per Option C redesign — WorldTick is an EVT-T5 Generated sub-type (Scheduled:WorldTick emitted by world-rule-scheduler). Producer rule subsumed by EVT-P5.

---

## Locked-decision summary

| ID | Status | Producer role(s) | Forbidden roles |
|---|---|---|---|
| EVT-P1 (T1 Submitted) | active | Player-Actor / Orchestrator / future quest-engine | LLM-Originator / Administrative / DP-Internal / Generator |
| EVT-P2 (was T2 NPCTurn) | `_withdrawn` | merged into P1 | — |
| EVT-P3 (T3 Derived) | active | Aggregate-Owner per-feature | LLM-Originator / Administrative direct (uses T8 with side-effects) / DP-Internal |
| EVT-P4 (T4 System) | active | DP-Internal only | ALL feature roles |
| EVT-P5 (T5 Generated) | active | Generator (Synthetic actor variants) — MUST honor EVT-A9 | Player-Actor / LLM-Originator / DP-Internal |
| EVT-P6 (T6 Proposal) | active | LLM-Originator (untrusted-origin) | any role with canonical-category produce claim |
| EVT-P7 (was T7 CalibrationEvent) | `_withdrawn` | merged into P3 | — |
| EVT-P8 (T8 Administrative) | active | Administrative (admin-cli via S5) | ALL non-admin-cli services |
| EVT-P9 (was T9 QuestBeat) | `_withdrawn` | split across P1+P3+P5 | — |
| EVT-P10 (was T10 NPCRoutine) | `_withdrawn` | merged into P5 | — |
| EVT-P11 (was T11 WorldTick) | `_withdrawn` | merged into P5 | — |

---

## Cross-references

- [EVT-A4 Producer-role binding](02_invariants.md#evt-a4--producer-role-binding-reframed-2026-04-25) — invariant this file implements
- [EVT-A7 Untrusted-origin pre-validation](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25) — explains LLM-Originator vs canonical-producer split
- [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) — applies to all Generator role
- [EVT-A11 Sub-type ownership](02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) — service-binding lives in `_boundaries/`
- [`03_event_taxonomy.md`](03_event_taxonomy.md) — EVT-T* categories this file gates
- [`06_per_category_contracts.md`](06_per_category_contracts.md) — envelope + per-category contracts
- [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) — current service↔role bindings (SSOT)
- [DP-K9 Capability tokens](../06_data_plane/04d_capability_and_lifecycle.md#dp-k9--capability-tokens) — JWT shape
- [DP-A6 Python event-only](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) — direction this file makes concrete
- ADMIN_ACTION_POLICY §R4 — S5 admin command registry
