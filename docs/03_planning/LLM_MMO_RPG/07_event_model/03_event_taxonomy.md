# 03 — Event Taxonomy (EVT-T*)

> **Status:** LOCKED Phase 1 + Option C redesign 2026-04-25. The closed set of event categories every event in LoreWeave's per-reality stream belongs to. Per [EVT-A1](02_invariants.md#evt-a1--closed-set-event-taxonomy), every event maps to exactly one EVT-T*; no "Other" / "Misc". Adding a category requires a superseding decision.
> **Stable IDs:** EVT-T1..EVT-T11 reserved; **6 active** (T1, T3, T4, T5, T6, T8) + **5 retired** (T2, T7, T9, T10, T11 — `_withdrawn` per foundation I15). Never renumber.
> **Redesign note (Option C, 2026-04-25):** original Phase 1 taxonomy (`ce6ea97`) had 6 mechanism-level + 5 feature-specific categories. Option C redesign collapsed feature-specific categories into mechanism categories via sub-types per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline). T2 NPCTurn, T7 CalibrationEvent, T9 QuestBeat, T10 NPCRoutine, T11 WorldTick withdrawn — their concerns absorbed by T1 Submitted / T3 Derived / T5 Generated as feature-defined sub-types.

---

## How to use this file

For every event your feature emits or consumes:

1. Find the matching EVT-T* row below.
2. Pick or define a **sub-type** within that category (sub-types are feature-defined per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline)).
3. Register your sub-type ownership in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).
4. Cite the EVT-T* + sub-type in your feature design's tier table (DP-R2) + producer table (EVT-P*).

Producer rules + per-category contracts (envelope shape, idempotency, payload limits) live in [`04_producer_rules.md`](04_producer_rules.md) and [`06_per_category_contracts.md`](06_per_category_contracts.md). This file gives the **mechanism identity** of each category — what dimension distinguishes it from others.

---

## Active categories (6) — quick reference

| ID | Name | Origination dimension | Trust model | DP commit primitive |
|---|---|---|---|---|
| **EVT-T1** | **Submitted** | Actor explicitly emits with intent | producer-trusted post-validation | `dp::advance_turn` (TurnBoundary wire format) |
| **EVT-T3** | **Derived** | Side-effect state delta of another event | service-trusted (aggregate owner) | `dp::t2_write` / `dp::t3_write` (NOT advance_turn) |
| **EVT-T4** | **System** | DP-internal lifecycle | DP-trusted by construction | DP-internal emission |
| **EVT-T5** | **Generated** | Rule/aggregator/scheduler emits based on condition + probability | service-trusted; deterministic per [EVT-A9](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) | aggregator runtime / scheduler primitive |
| **EVT-T6** | **Proposal** | Untrusted-origin pre-validation message | untrusted; lifecycle stage | bus-only (Redis Streams via I13 outbox); NOT in event log |
| **EVT-T8** | **Administrative** | Operator-emitted via S5 dispatch | operator-trusted | dedicated admin primitive (e.g., `dp::channel_pause`); often emits T4 System as side-effect |

**Withdrawn IDs (5):** T2 / T7 / T9 / T10 / T11 — see retirement section below.

---

## EVT-T1 — Submitted

**Mechanism:** an authorized actor (PC, NPC orchestrator, quest engine, etc.) explicitly emits an intent-bearing event via `dp::advance_turn`. The event is committed canonical after passing the EVT-V* validator pipeline.

**Producer roles:** Player-Actor (PC submission via gateway → roleplay → trusted commit-service); Orchestrator (NPC reactions, multi-NPC chorus); future quest-engine (quest beat outcomes). See [EVT-A4](02_invariants.md#evt-a4--producer-role-binding-reframed-2026-04-25) producer-role table.

**DP commitment mechanism:** `dp::advance_turn(ctx, &channel, turn_data, causal_refs)` — commits a TurnBoundary wire-format event with the typed payload. (Per Phase 0 B1 decision: TurnBoundary is the wire format; Submitted is the semantic identity.)

**Lifecycle stage:** committed canonical.

**Sub-types** (feature-defined per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline); registered in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md)):

| Sub-type | Owning feature | Notes |
|---|---|---|
| `PCTurn` (Speak / Action / MetaCommand / FastForward) | PL_001 Continuum + PL_002 Grammar | actor=PC; PL_002 owns command sub-shapes |
| `NPCTurn` (Speak / Action / MetaCommand-Whisper-Look / Narration) | NPC_001 Cast (envelope) + NPC_002 Chorus (multi-NPC ordering) | actor=NPC; **causal-ref required** to triggering event |
| `QuestOutcome` (V1+) | future quest-service | actor=quest-engine synthetic; refs QuestTrigger |

**Causal-ref policy:** per sub-type. PCTurn typically optional; NPCTurn always required (refs the triggering PCTurn or scene-trigger); QuestOutcome required (refs QuestTrigger).

**Validator chain:** schema → capability → A5 intent classify → A5 command dispatch (if MetaCommand) → A6 5-layer (if originated from EVT-T6 Proposal) → world-rule lint → canon-drift → causal-ref integrity → commit. Order locked per `_boundaries/03_validator_pipeline_slots.md`.

**Cross-ref:** [PL_001 §3.5 TurnEvent](../features/04_play_loop/PL_001_continuum.md), [PL_002 §6 commands](../features/04_play_loop/PL_002_command_grammar.md), [NPC_001 §2.5](../features/05_npc_systems/NPC_001_cast.md), [NPC_002 §2.5](../features/05_npc_systems/NPC_002_chorus.md), [DP-A17](../06_data_plane/02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25).

---

## EVT-T3 — Derived

**Mechanism:** a side-effect state delta committed via `dp::t2_write` or `dp::t3_write` (NOT `advance_turn`) by an aggregate-owner feature service, in response to a parent event (typically EVT-T1 Submitted, EVT-T8 Administrative, or EVT-T5 Generated). Causal-refs the parent.

**Producer roles:** Aggregate-Owner per-feature. Each feature owns specific aggregate types listed in [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).

**DP commitment mechanism:** `dp::t2_write::<A>(ctx, id, delta)` for T2 aggregates, `dp::t3_write::<A>(ctx, id, delta)` for T3, `dp::t3_write_multi(ctx, ops)` for atomic multi-aggregate. Each write commits its own channel event with own `channel_event_id` per DP-A15.

**Lifecycle stage:** committed canonical.

**Sub-types:** discriminated by the **`aggregate_type`** field rather than a sub-shape name. Each aggregate-type × delta-kind combination is a sub-type. Feature designs declare their `aggregate_type` + delta-kinds in their own doc and register in the boundary matrix.

V1 aggregate types currently registered (see boundary matrix for full list): `fiction_clock` (PL_001) · `scene_state` (PL_001) · `actor_binding` (PL_001) · `participant_presence` (PL_001) · `npc_pc_relationship_projection` (NPC_001) · `npc_node_binding` (NPC_001) · `tool_call_allowlist` (PL_002) · plus calibration sub-shapes (DayPasses / MonthPasses / YearPasses, derived from FictionClock advance per MV12-D5).

**Causal-ref policy:** optional but **strongly recommended** when caused by a parent turn (FictionClockAdvance after PCTurn refs the PCTurn; ActorBindingDelta after `move_session_to_channel` refs the parent FastForward). Calibration sub-shapes always reference the parent FictionClock advance.

**Note on absorbed `_withdrawn` ID:** EVT-T7 CalibrationEvent (original Phase 1) was withdrawn 2026-04-25 — calibration is mechanically a Derived event from FictionClock T2 commit. It now lives as a Derived sub-type (with its own causal-ref-required policy + envelope shape) rather than a separate category. See retirement section.

**Validator chain:** schema → capability (write to specific aggregate-type/tier/scope) → world-rule lint (does the delta make sense?) → causal-ref integrity → commit. **No A6 injection defense** — Derived is producer-trusted output of a trusted aggregate-owner, not LLM input.

**Cross-ref:** [PL_001 §3](../features/04_play_loop/PL_001_continuum.md), [DP-K5](../06_data_plane/04b_read_write.md#dp-k5--write-primitives-tier-typed), [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md).

---

## EVT-T4 — System

**Mechanism:** events emitted by the Data Plane itself, not by any feature service. SystemEvents represent DP-internal lifecycle facts that features observe but cannot forge.

**Producer roles:** **DP-Internal only.** Cannot be emitted from feature code; SDK rejects attempts (per DP-A18 / DP-Ch52 reserved discriminators).

**DP commitment mechanism:** DP-internal emission as part of the operation's transactional commit.

**Lifecycle stage:** committed canonical, immutable.

**Sub-types** (locked by DP, NOT redesigned here — Event Model classifies, does NOT redesign):

| Sub-type | DP source | Emits when |
|---|---|---|
| `MemberJoined` | DP-A18 / DP-Ch34 | `bind_session` / `move_session_to_channel` arrival |
| `MemberLeft` | DP-A18 / DP-Ch34 | move-away / disconnect / dissolution / timeout |
| `ChannelPaused` | DP-A18 / DP-Ch35 | `channel_pause` |
| `ChannelResumed` | DP-A18 / DP-Ch35 | `channel_resume` or auto-expiry |
| `TurnSlotClaimed` | DP-Ch51 | `claim_turn_slot` |
| `TurnSlotReleased` | DP-Ch51 | `release_turn_slot` or auto-timeout |
| `TurnSlotTimedOut` | DP-Ch52 | CP scheduler 30-s auto-timeout |
| `TurnBoundary` | DP-A17 | every `advance_turn` call (carries the EVT-T1 Submitted payload as `turn_data`) |

**Causal-ref policy:** N/A — DP-internal. SystemEvents don't carry feature-level causal_refs (DP may carry its own internal references; out of EVT scope).

**Validator chain:** **none** — SystemEvents are trusted by construction.

**Note on TurnBoundary:** `turn_data` IS the EVT-T1 Submitted payload as defined in PL_001 / PL_002 / NPC_001 / NPC_002. Two lenses, same wire bytes: feature designers think "this is a Submitted event"; wire-protocol consumers see "TurnBoundary with payload".

**Cross-ref:** [DP-A18](../06_data_plane/02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25), [DP-Ch51](../06_data_plane/21_llm_turn_slot.md), [DP-A17](../06_data_plane/02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25).

---

## EVT-T5 — Generated

**Mechanism:** events emitted by a registered rule/aggregator/scheduler based on **condition + probability + deterministic RNG** (per [EVT-A9](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25)). The producer is a feature-registered Generator (Synthetic actor); the trigger is some upstream event or fiction-time threshold.

**Producer roles:** Generator (Synthetic actor — `BubbleUpAggregator`, `Scheduler`, `RealityBootstrapper`, plus future Generator types). The registering feature service holds the JWT claim; the runtime emit happens via DP aggregator runtime (DP-Ch26) or scheduler primitive.

**DP commitment mechanism:** depends on Generator sub-type:
- BubbleUp aggregator → `dp::t2_write` on parent channel for the aggregator's emit aggregate-type (DP-Ch25..Ch30)
- Scheduler beat → `dp::advance_turn` on the target channel for the beat (Phase 4 [`08_scheduled_events.md`](08_scheduled_events.md))
- Future probabilistic generators (combat damage RNG, loot drop RNG, weather drift) → `dp::t2_write` typically

**Lifecycle stage:** committed canonical.

**Sub-types** (feature-defined; registered in boundary matrix):

| Sub-type pattern | Owning feature | Trigger |
|---|---|---|
| `BubbleUp:RumorBubble` | future gossip aggregator (PL_002+) | descendant events match aggregator filter + RNG threshold |
| `BubbleUp:CrowdDensity` | future ambient aggregator | descendant member-count changes |
| `Scheduled:NPCRoutine` (V1+30d) | future world-rule-scheduler | fiction-clock matches NPC routine schedule |
| `Scheduled:WorldTick` (V1+30d) | future world-rule-scheduler | fiction-clock crosses author-placed beat threshold |
| `Scheduled:QuestTrigger` (V1+) | future quest-engine | quest precondition met (calibration / turn / event) |

**Note on absorbed `_withdrawn` IDs:** EVT-T9 QuestBeat (original Phase 1) was withdrawn — QuestBeat:Trigger is a Generated sub-type (rule-based); QuestBeat:Outcome is a Submitted sub-type (quest-engine actor). Splitting clarifies the mechanism. EVT-T10 NPCRoutine and EVT-T11 WorldTick were withdrawn — both are Generated by scheduler (different sub-types). See retirement section.

**Causal-ref policy:** **REQUIRED.** Every Generated event must reference at least one source event (the trigger). For BubbleUp: source events at descendant channels. For Scheduled: the CalibrationEvent (Derived sub-type) or other fiction-time-marker that crossed threshold.

**Validator chain:** **subset** — Generated bypasses A6 injection-defense (no LLM input on emit path; aggregator/scheduler code is feature-trusted). Schema + capability + causal-ref integrity remain. World-rule lint optional per Generator type. **EVT-A9 RNG determinism** enforced at lint time + replay test.

**Cross-ref:** [EVT-A9 RNG determinism](02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25), [DP-A15](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25), [DP-Ch25..Ch30 BubbleUp aggregator](../06_data_plane/16_bubble_up_aggregator.md), [DP-Ch43 Redaction](../06_data_plane/19_privacy_redaction_policies.md).

---

## EVT-T6 — Proposal

**Mechanism:** a pre-validation message emitted by an **untrusted-origin** producer (LLM-driven service today; future agentic/plugin services) onto the proposal bus. Carries a proposed Submitted event that has NOT yet been validated. The trusted commit-service consumes the proposal, runs EVT-V* validator pipeline, and either commits a fresh EVT-T1 Submitted (proposal "Validated") or rejects + dead-letters (proposal "Rejected").

**Producer roles:** LLM-Originator (V1: Python `roleplay-service`; future LLM/agentic services). Producer JWT carries `produce: [Proposal]` ONLY — never canonical categories. Per [EVT-A7](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25).

**DP commitment mechanism:** **NOT DP** — Proposal lives on the proposal bus (Redis Streams via I13 outbox), NOT in any per-reality channel event log. Once validated, the trusted commit-service commits a fresh EVT-T1 Submitted via `dp::advance_turn` — the original proposal is referenced from the committed event's metadata but not retained as a canonical event.

**Lifecycle stages (3 terminal):**
- `Validated` — promoted to EVT-T1 Submitted; consumers see the committed event.
- `Rejected { reason }` — validator rejected; logged + dead-lettered. Producer/PC sees soft-fail UX.
- `Expired` — bus retention window elapsed (default 60s) without validator consume.

**Sub-types** (feature-defined; based on which Submitted shape they're proposing):

| Sub-type | Promoted to | Owning feature |
|---|---|---|
| `PCTurnProposal` | EVT-T1 Submitted/PCTurn | roleplay-service (originator) + PL_002 (envelope shape) |
| `NPCTurnProposal` | EVT-T1 Submitted/NPCTurn | roleplay-service (originator) + NPC_001 (envelope) + NPC_002 (orchestration) |

**Causal-ref policy:** optional. NPCTurnProposal typically references the triggering Submitted event.

**Validator chain:** the FULL EVT-V* pipeline runs ON the proposal as input. Output is `Validated → commit` or `Rejected → dead-letter`.

**Cross-ref:** [EVT-A7](02_invariants.md#evt-a7--untrusted-origin-events-require-pre-validation-lifecycle-reframed-2026-04-25), [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state), [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) (Phase 3).

---

## EVT-T8 — Administrative

**Mechanism:** events emitted by an operator (admin / human / authorized service-account) via S5 admin-action policy dispatch. Different validator chain than EVT-T1 Submitted (S5 dual-actor + impact-class gating; no A6 since admin input is operator-authenticated).

**Producer roles:** Administrative (admin-cli via S5 dispatch).

**DP commitment mechanism:** depends on the admin operation:
- `channel_pause` / `channel_resume` → `dp::channel_pause` / `dp::channel_resume`; emits EVT-T4 System (ChannelPaused/Resumed) as side-effect; Administrative event committed alongside as audit anchor (refs the System event)
- `force_end_scene` → admin-cli triggers cell channel dissolve + emits Administrative
- `world_rule_override` → `dp::t3_write` on world-rule-override aggregate
- `force_revert_turn` (V2+) — out of V1 scope

**Lifecycle stage:** committed canonical, immutable, audit-grade. `admin_action_audit` table mirrors per S5.

**Sub-types** (feature-defined; registered in `_boundaries/02_extension_contracts.md` §4 — already locked for Charter / Succession / Forge / Mortality features):

| Sub-type | Owning feature |
|---|---|
| `Pause` / `Resume` / `ForceEndScene` / `WorldRuleOverride` | core admin (V1) |
| `ForgeEdit { editor, action, before, after }` | WA_003 Forge |
| `Charter*` (Invite/Accept/Decline/Cancel/Revoke/Resign) | PLT_001 Charter |
| `Succession*` (Initiate/RecipientAccept/etc., 8 sub-shapes) | PLT_002 Succession |
| `MortalityAdminKill` (provisional) | WA_006 Mortality |

See `_boundaries/02_extension_contracts.md` §4 for the full union.

**Causal-ref policy:** optional. Used when admin action targets a specific event (e.g., force-revert turn N).

**Validator chain:** schema → capability (S5 actor authentication; impact-class gating) → S5 dual-actor (Tier 1 only) → world-rule lint (optional — admin may explicitly override) → causal-ref integrity → commit. **No A6 injection defense** — admin input is operator-authenticated.

**Cross-ref:** S5 [02_storage S05_admin_command_classification.md](../02_storage/S05_admin_command_classification.md), [DP-Ch35](../06_data_plane/17_channel_lifecycle.md#dp-ch35--channel_pause--channel_resume-primitives), [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) §4.

---

## Retired IDs (5)

Per foundation I15 stable-ID retirement rule: retired IDs use `_withdrawn` suffix, never reused. The original Phase 1 categories (commit `ce6ea97`) were redesigned 2026-04-25 (Option C) to mechanism-level. Five IDs withdrawn.

### EVT-T2_withdrawn — was "NPCTurn"

**Reason for retirement:** mechanically identical to EVT-T1 Submitted with `actor=ActorId::Npc` sub-type. Maintaining T2 as a separate category embedded the assumption that "PC vs NPC" is a category-level distinction; in reality, they share the same envelope, validator chain, and DP commit primitive — only the actor variant differs. Per Option C redesign, "NPCTurn" is now a sub-type of EVT-T1 Submitted.

**Migration:** features that cited EVT-T2 NPCTurn now cite EVT-T1 Submitted (sub-type=NPCTurn). NPC_001 + NPC_002 §2.5 mapping rows updated to new ID. Stable ID `EVT-T2` permanently retired — never reused.

**See:** [EVT-T1 Submitted sub-types](#evt-t1--submitted) for current home.

### EVT-T7_withdrawn — was "CalibrationEvent"

**Reason for retirement:** mechanically identical to EVT-T3 Derived with sub-type discriminator `calibration_kind`. Calibration is a side-effect of FictionClock T2 commit when a date boundary is crossed — same producer (Aggregate-Owner of FictionClock), same DP primitive (`t2_write`), same validator chain. Maintaining T7 as a separate category embedded the assumption that fiction-time was a category-level concern; in reality, it's a feature-level concern (PL_001 / 03_multiverse).

**Migration:** features that cited EVT-T7 CalibrationEvent now cite EVT-T3 Derived (sub-type=DayPasses / MonthPasses / YearPasses). PL_002 §2.5 updated. Stable ID `EVT-T7` permanently retired.

**See:** [EVT-T3 Derived sub-types](#evt-t3--derived).

### EVT-T9_withdrawn — was "QuestBeat"

**Reason for retirement:** QuestBeat had three sub-shapes (Trigger / Advance / Outcome) with distinct mechanisms — Trigger fires from rule-condition (Generated), Advance is internal quest-engine state delta (Derived), Outcome is quest-engine actor-submitted decision (Submitted). Maintaining T9 as a single category papered over the mechanism difference. Per Option C redesign, the three sub-shapes split:

- `QuestTrigger` → EVT-T5 Generated sub-type (Scheduled:QuestTrigger)
- `QuestAdvance` → EVT-T3 Derived sub-type (aggregate_type=quest_state)
- `QuestOutcome` → EVT-T1 Submitted sub-type

**Migration:** when quest engine feature lands (V1+), it cites the three new homes. Stable ID `EVT-T9` permanently retired.

**See:** [EVT-T1](#evt-t1--submitted), [EVT-T3](#evt-t3--derived), [EVT-T5](#evt-t5--generated).

### EVT-T10_withdrawn — was "NPCRoutine"

**Reason for retirement:** NPCRoutine fires from a scheduler matching fiction-time + per-NPC routine declaration with optional probability. Mechanically a Generated event (Scheduler kind, not BubbleUp). Maintaining T10 as a separate category split the Generated mechanism into two redundant categories.

**Migration:** when world-rule-scheduler lands (V1+30d), NPC routines emit as EVT-T5 Generated sub-type `Scheduled:NPCRoutine`. Stable ID `EVT-T10` permanently retired.

**See:** [EVT-T5 Generated](#evt-t5--generated).

### EVT-T11_withdrawn — was "WorldTick"

**Reason for retirement:** WorldTick fires from author-placed beats when fiction-clock crosses threshold, optionally with probability gate. Same Generator mechanism as NPCRoutine — only differs in sub-type (Scheduled:WorldTick vs Scheduled:NPCRoutine).

**Migration:** when world-rule-scheduler lands (V1+30d), author-placed beats emit as EVT-T5 Generated sub-type `Scheduled:WorldTick`. Stable ID `EVT-T11` permanently retired.

**See:** [EVT-T5 Generated](#evt-t5--generated).

---

## Closed-set proof

Per [EVT-A1](02_invariants.md#evt-a1--closed-set-event-taxonomy), every event from PL_001 + PL_002 + NPC_001 + NPC_002 + every observation in SPIKE_01 + every DP-emitted canonical event maps to exactly one **active** EVT-T*. This table is the proof under the redesigned (6-active-category) taxonomy.

| Source | Event | → Category | Sub-type |
|---|---|---|---|
| PL_001 §3.5 / PL_002 §6 | TurnEvent::Speak (PC) | **EVT-T1** Submitted | PCTurn::Speak |
| PL_001 / PL_002 | TurnEvent::Action (PC) | **EVT-T1** Submitted | PCTurn::Action |
| PL_002 §6 | TurnEvent::MetaCommand (Verbatim/Prose/Sleep/Travel/Help) | **EVT-T1** Submitted | PCTurn::MetaCommand |
| PL_001b §12 / SPIKE_01 turn 11/16 | TurnEvent::FastForward (`/sleep`, `/travel`) | **EVT-T1** Submitted | PCTurn::FastForward |
| PL_001 §11 / NPC_002 | NPC reaction (Lão Ngũ, Tiểu Thúy responding) | **EVT-T1** Submitted | NPCTurn (per NPC_001/NPC_002) |
| Future quest engine | Quest outcome decision | **EVT-T1** Submitted | QuestOutcome |
| PL_001 §3.4 / DP-A18 | MemberJoined / MemberLeft | **EVT-T4** System | (DP-locked) |
| DP-A18 / DP-Ch35 | ChannelPaused / ChannelResumed | **EVT-T4** System | (DP-locked) |
| DP-Ch51 | TurnSlot* | **EVT-T4** System | (DP-locked) |
| DP-A17 | TurnBoundary (wire format) | **EVT-T4** System | (payload IS EVT-T1 Submitted) |
| PL_001 §5.2 | SceneStateDelta::AmbientUpdate | **EVT-T3** Derived | aggregate_type=scene_state |
| PL_001 §3.6 | ActorBindingDelta::MoveTo | **EVT-T3** Derived | aggregate_type=actor_binding |
| PL_001 §3.1 | FictionClockAdvance | **EVT-T3** Derived | aggregate_type=fiction_clock |
| MV12-D5 / SPIKE_01 obs#15 | day_passes / month_passes / year_passes | **EVT-T3** Derived | calibration sub-shapes (was T7) |
| NPC_001 §2.5 | NPC opinion update on `npc_pc_relationship_projection` | **EVT-T3** Derived | aggregate_type=npc_pc_relationship_projection |
| DP-A15 + DP-Ch25 | Bubble-up rumor at parent channel | **EVT-T5** Generated | BubbleUp::RumorBubble |
| Future scheduler | Author-placed siege beat | **EVT-T5** Generated | Scheduled:WorldTick (was T11) |
| Future scheduler | NPC daily routine fire | **EVT-T5** Generated | Scheduled:NPCRoutine (was T10) |
| Future quest engine | Quest precondition met | **EVT-T5** Generated | Scheduled:QuestTrigger (was T9 Trigger sub-shape) |
| Future combat / loot | Damage RNG / loot RNG roll | **EVT-T5** Generated | per-feature sub-type |
| DP-A6 / EVT-A7 | Python LLM proposal events | **EVT-T6** Proposal | PCTurnProposal / NPCTurnProposal |
| DP-Ch35 + S5 | Admin pause / force-end-scene / world-rule override | **EVT-T8** Administrative | Pause / Resume / ForceEndScene / WorldRuleOverride |
| WA_003 / Charter / Succession / Mortality | Author edits via Forge | **EVT-T8** Administrative | ForgeEdit / Charter* / Succession* / MortalityAdminKill |
| SPIKE_01 obs#16 | Long-skip flavor narration | **NOT AN EVENT** per EVT-A8 — non-canonical, audit-log only |
| SPIKE_01 obs#22 | Player intent vs PC plausibility tension | **NOT A TAXONOMY ITEM** — meta-design concern |
| SPIKE_01 obs#13 | Session-resume UX choice | **NOT AN EVENT** — UX flow generates a Submitted/PCTurn::FastForward once user chooses |
| Future DF3 (V2+) | L3 → L2 canon promotion | **EXCLUDED from EVT-T*** per Phase 0 B6 — multiverse-scoped |
| Future DF12 (withdrawn) | Cross-reality coordination | **EXCLUDED** — withdrawn feature |

**Result:** every observable event maps to exactly one active EVT-T* (T1 / T3 / T4 / T5 / T6 / T8). Closed-set property satisfied under the redesigned taxonomy.

---

## Cross-references

- [EVT-A1..A12 axioms](02_invariants.md) — invariants this taxonomy implements
- [`../_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md) — sub-type ownership SSOT (per [EVT-A11](02_invariants.md#evt-a11--sub-type-ownership-discipline))
- [`../_boundaries/02_extension_contracts.md`](../_boundaries/02_extension_contracts.md) — TurnEvent envelope §1, AdminAction sub-shapes §4
- [`04_producer_rules.md`](04_producer_rules.md) — EVT-P* per category
- [`06_per_category_contracts.md`](06_per_category_contracts.md) — envelope + extensibility framework
- [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) — Proposal lifecycle protocol (Phase 3)
- [`08_scheduled_events.md`](08_scheduled_events.md) — Generated::Scheduled mechanics (Phase 4)
- [`09_causal_references.md`](09_causal_references.md) — `CausalRef` shape (Phase 4)
- [PL_001 §3](../features/04_play_loop/PL_001_continuum.md) — Submitted/PCTurn sub-types + Derived aggregates
- [PL_002 §6](../features/04_play_loop/PL_002_command_grammar.md) — PCTurn::MetaCommand sub-types (5 V1 commands)
- [NPC_001 §2.5](../features/05_npc_systems/NPC_001_cast.md) — Submitted/NPCTurn + ActorId enum + producer roles
- [NPC_002 §2.5](../features/05_npc_systems/NPC_002_chorus.md) — Submitted/NPCTurn batch ordering
- [SPIKE_01 §6 + §9](../features/_spikes/SPIKE_01_two_sessions_reality_time.md) — 22 observations grounding the categories
