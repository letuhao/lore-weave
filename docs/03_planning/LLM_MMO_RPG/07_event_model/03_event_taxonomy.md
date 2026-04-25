# 03 — Event Taxonomy (EVT-T*)

> **Status:** LOCKED. The closed set of event categories every event in LoreWeave's per-reality stream belongs to. Per [EVT-A1](02_invariants.md#evt-a1--closed-set-event-taxonomy), every event maps to exactly one EVT-T*; no "Other" / "Misc". Adding a category requires a superseding decision in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md).
> **Stable IDs:** EVT-T1..EVT-T11. Never renumber. Retired IDs use `_withdrawn` suffix (foundation I15).

---

## How to use this file

For every event your feature emits or consumes:

1. Find the matching EVT-T* row below.
2. If no row matches, **stop** — open an [`99_open_questions.md`](99_open_questions.md) item and propose a new category. Do not proceed by inventing a 12th category locally.
3. Cite the EVT-T* ID in your feature design's tier table (DP-R2) + producer table (EVT-P*, Phase 2).

The producer rules + per-category contract (required fields, idempotency key, max payload size) live in `04_producer_rules.md` and `06_per_category_contracts.md` (Phase 2 deliverables). This file gives the **shape and identity** of each category — semantic + lifecycle + DP commit primitive.

---

## Quick reference table

| ID | Name | V-tier | Producer (high level) | DP commit primitive | Lifecycle stage | Causal-ref policy |
|---|---|---|---|---|---|---|
| **EVT-T1** | PlayerTurn | V1 | gateway → roleplay-service → world-service | `dp::advance_turn` (TurnBoundary wire format) | committed canonical | optional (none for free narrative; required for chained command resolution) |
| **EVT-T2** | NPCTurn | V1 | world-service orchestrator | `dp::advance_turn` (TurnBoundary wire format) | committed canonical | **required** — must reference triggering turn or scene-trigger |
| **EVT-T3** | AggregateMutation | V1 | world-service / quest-service / feature service | `dp::t2_write` or `dp::t3_write` (NOT advance_turn) | committed canonical | optional (recommended when caused by a parent turn — e.g., FictionClockAdvance refs the PlayerTurn) |
| **EVT-T4** | SystemEvent | V1 | DP itself (canonical, cannot be forged) | DP-internal emission | committed canonical | n/a (DP-internal) |
| **EVT-T5** | BubbleUpEvent | V1 | registered aggregator on parent's writer node | aggregator runtime loop (DP-Ch26) | committed canonical at parent channel | **required** — references one or more source events at descendant channel |
| **EVT-T6** | LLMProposal | V1 | roleplay-service (Python LLM) | bus-only (Redis Streams via I13 outbox); NOT in event log | pre-validation; promoted → PlayerTurn/NPCTurn or rejected | optional (proposal may reference a prior turn it's reacting to) |
| **EVT-T7** | CalibrationEvent | V1 | world-service (derives from FictionClock advance) | `dp::t2_write` on the calibration sub-aggregate | committed canonical | **required** — references the parent turn whose FictionClock advance crossed a date boundary |
| **EVT-T8** | AdminAction | V1 | admin-cli via S5 dispatch | dedicated admin primitive (e.g., `dp::channel_pause`) usually emits SystemEvent as side-effect | committed canonical | optional (refs target event when the action is "force-revert turn N") |
| **EVT-T9** | QuestBeat | V1+ | quest engine (feature service, future) | `dp::t2_write` on quest aggregate | committed canonical | **required for Outcome** (refs Trigger); optional for Trigger |
| **EVT-T10** | NPCRoutine | V1+30d | world-rule-scheduler service | `dp::advance_turn` on the cell channel where 0 PCs present | committed canonical | optional |
| **EVT-T11** | WorldTick | V1+30d | world-rule-scheduler service | `dp::advance_turn` on the channel where the beat fires (typically town/country level) | committed canonical | optional (may reference quest triggers) |

V-tier legend: **V1** = ships in V1 solo-RP (PL_001 / DF5 era); **V1+** = available V1 but feature-gated (depends on quest engine landing); **V1+30d** = enabled after V1 stabilization; **V2+** = coop / MMO-lite phase.

---

## EVT-T1 — PlayerTurn

**Definition:** A canonical event emitted when a Player Character (PC) submits a turn through the gateway. Carries the player's intent (story / command / meta per A5-D1), narrator text (post-validation), and any state-mutation metadata.

**Producer:** gateway → roleplay-service (3-intent classification + LLM prompt assembly + LLM streaming + output filter) → world-service (validators + commit). The PlayerTurn event itself is committed by **world-service**, not roleplay-service. (Roleplay-service emits EVT-T6 LLMProposal; world-service consumes and commits the validated PlayerTurn.)

**Trigger:** PC types text + presses send. WS-arrival in gateway. POST `/v1/turn` with idempotency key.

**DP commitment mechanism:** `dp::advance_turn(ctx, &cell_channel, turn_data: TurnEvent { ... }, causal_refs)`. This commits a TurnBoundary channel event with the TurnEvent struct as payload. (Per Phase 0 B1 decision: TurnBoundary is the wire format; PlayerTurn is the semantic identity.)

**Lifecycle stage:** committed canonical. After commit, durable subscribers (UI, world-service self-loop, bubble-up aggregators, audit-logger) observe via DP-K6.

**Sub-shapes (feature-defined):** PL_001 §3.5 declares the V1 sub-shapes:
- `Speak` — free-narrative dialogue
- `Action` — physical action (move, take, attack — but state-mutation comes from `/verb` per A5-D3, not from LLM)
- `MetaCommand` — system commands (`/sleep`, `/travel`, `/whisper`, `/look`)
- `FastForward` — long-duration jump triggered by MetaCommand (Sleep / Travel) — covers MV12-D5 calibration semantics
- `Narration` — post-fast-forward LLM-generated wakeup or arrival narration. **Marked `flavor=true` per [EVT-A8](02_invariants.md#evt-a8--flavor-narration-is-not-events)** — non-canonical text; only the structural delta of the parent FastForward is canonical.

Future PL_002+ may add sub-shapes; new sub-shapes don't require a new EVT-T* row, just an EVT-S* schema bump on the PlayerTurn payload (additive per I14).

**Causal-ref policy:** Optional. Free narrative typically has none. Chained commands (`/travel` resolving to multi-step move + scene-change) reference the parent /travel command's PlayerTurn from the resolution turns.

**Validator chain (EVT-V*, Phase 3 reference):** schema → capability (`can_advance_turn`) → A5-D1 intent classify (cross-check) → A5 command dispatch (if MetaCommand) → A6 5-layer injection defense → world-rule lint → canon-drift check → causal-ref integrity → commit.

**Cross-ref:** [PL_001 §3.5 TurnEvent](../features/04_play_loop/PL_001_continuum.md), [DP-A17 Turn numbering](../06_data_plane/02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25), [05_llm_safety A5/A6](../05_llm_safety/).

---

## EVT-T2 — NPCTurn

**Definition:** A canonical event emitted when an NPC takes a turn — typically reacting to a previous PlayerTurn within the same scene, but also covers NPC-initiated actions during multi-NPC scenes (per SPIKE_01 obs#6 multi-NPC reaction).

**Producer:** world-service orchestrator. The orchestrator decides which NPC reacts (per scene state + opinion graph + world-rule), assembles a prompt via `contracts/prompt/AssemblePrompt(intent=npc_reply)`, calls the LLM, runs A6 output filter, and commits. The NPC's "session" is the orchestrator's `SessionContext`, not a per-NPC SDK session (per [`../06_data_plane/99_open_questions.md`](../06_data_plane/99_open_questions.md) OOS-1).

**Trigger:** typically a prior PlayerTurn that includes targets the NPC observes (PC speaks to NPC, PC enters scene, PC performs visible action). Can also be triggered by world-rule (NPC challenges PC's claim, NPC attempts to leave the scene).

**DP commitment mechanism:** `dp::advance_turn(ctx, &cell_channel, turn_data: TurnEvent { actor: ActorId::Npc { npc_id }, ... }, causal_refs)`. Same primitive as PlayerTurn; differs by `actor` field.

**Lifecycle stage:** committed canonical.

**Sub-shapes:** mirrors PlayerTurn — Speak / Action / MetaCommand (NPC executes a deterministic command-equivalent like "leave scene") / Narration. Notably **NO FastForward** for NPCs in V1 (NPCs don't `/travel` autonomously; that's V1+30d EVT-T10 NPCRoutine).

**Causal-ref policy:** **REQUIRED.** NPCTurn must reference either (a) the triggering PlayerTurn / NPCTurn, or (b) the scene-trigger event (e.g., MemberJoined when the PC entered the scene). This is enforced by the validator pipeline; missing causal-ref → `DpError::CausalRefMissing`.

**Validator chain:** schema → capability (`can_advance_turn` for actor=Npc category — orchestrator-only) → A5-D3 tool-call allowlist (NPCs cannot emit state-mutation tool calls per A5-D3) → A6 5-layer injection defense → world-rule lint (NPC can-do this action?) → canon-drift check (does NPC speech contradict L1/L2/L3?) → causal-ref integrity → commit.

**SPIKE_01 obs#6 multi-NPC handling:** when a PlayerTurn implicitly demands multiple NPCs react (turn 5 — PC's literacy slip is observed by Du sĩ + Tiểu Thúy + Lão Ngũ), orchestrator emits NPCTurn events in deterministic order (per scene-NPC ordering rule, defined by feature in PL_003). Each NPCTurn references the same triggering PlayerTurn. Rate-limit applies per orchestrator-session, not per-NPC.

**Cross-ref:** [PL_001 §3.5](../features/04_play_loop/PL_001_continuum.md), SPIKE_01 obs#6, [`../05_llm_safety/02_command_dispatch.md`](../05_llm_safety/02_command_dispatch.md).

---

## EVT-T3 — AggregateMutation

**Definition:** A canonical event emitted when a feature service writes to a per-reality aggregate as a **side-effect** of a parent event (PlayerTurn / NPCTurn / WorldTick / AdminAction), but distinct from the parent's commit. Examples: FictionClockAdvance after a turn, ActorBindingDelta::MoveTo after a /travel chain, SceneStateDelta::AmbientUpdate when LLM emits a weather change, NPC-PC opinion update.

**Producer:** world-service (most common) or other feature services that own specific aggregates (quest-service for quest aggregate writes, etc.). The producer must be authorized for the target aggregate's tier+scope per DP-K9.

**Trigger:** explicit decision by the producer following a parent event. The parent event itself may be EVT-T1 / EVT-T2 / EVT-T8 / EVT-T11.

**DP commitment mechanism:** `dp::t2_write::<A>(ctx, id, delta)` for T2 aggregates, `dp::t3_write::<A>(ctx, id, delta)` for T3, `dp::t3_write_multi(ctx, ops)` for atomic multi-aggregate. NOT `dp::advance_turn` — AggregateMutation does not advance turn_number.

**Lifecycle stage:** committed canonical. Each AggregateMutation gets its own `channel_event_id` (per DP-A15) and `causality_token` (per DP-A19).

**Causal-ref policy:** Optional but **strongly recommended** when caused by a parent turn. PL_001's FictionClockAdvance after each turn references the PlayerTurn's `channel_event_id`; this is what enables "what state changed because of turn N?" queries via causal-graph walk.

**Why this is its own category and not a sub-type of the parent:** Per Phase 0 B3 decision. Each `t2_write` commits as a separate channel event with its own ID; treating it as part of the parent collapses information that's actually distinct. Replay must restore each AggregateMutation independently. Validator pipeline runs per-event, not per-cluster.

**Validator chain:** schema → capability (write to specific aggregate-type/tier/scope) → world-rule lint (does this state delta make sense given current state?) → causal-ref integrity → commit. **No A6 injection defense** — AggregateMutation is producer-trusted output, not LLM input.

**Edge case — "implicit" mutations:** if a producer would emit dozens of AggregateMutations per parent turn (e.g., 50 NPCs in a market square each updating their idle_since_turn), this should be either (a) consolidated into a single AggregateMutation with a batched delta, or (b) modeled as a different category if the volume is structural. PL_002 / PL_003 will surface specific cases.

**Cross-ref:** [PL_001 §3.1 / §3.2 / §3.6](../features/04_play_loop/PL_001_continuum.md), [DP-K5 Write primitives](../06_data_plane/04b_read_write.md#dp-k5--write-primitives-tier-typed).

---

## EVT-T4 — SystemEvent

**Definition:** Canonical events emitted by the Data Plane itself, not by any feature service. SystemEvents represent DP-internal lifecycle facts that features observe but cannot forge.

**Producer:** **DP itself.** Cannot be emitted from feature code; SDK rejects attempts (per DP-A18 / DP-Ch52 reserved discriminators).

**Trigger:** specific DP operations — `bind_session`, `move_session_to_channel`, `channel_pause`, `channel_resume`, `dissolve_channel`, `claim_turn_slot`, `release_turn_slot`, scheduler timeouts, `advance_turn`.

**DP commitment mechanism:** DP-internal emission as part of the operation's transactional commit. Always at the channel where the operation occurred.

**Lifecycle stage:** committed canonical, immutable.

**Sub-shapes (locked by DP, NOT redesigned here):**

| Sub-shape | DP source | Trigger |
|---|---|---|
| `MemberJoined { actor, joined_at, joined_via }` | DP-A18 / DP-Ch34 | `bind_session` / `move_session_to_channel` arrival |
| `MemberLeft { actor, left_at, reason }` | DP-A18 / DP-Ch34 | move-away / disconnect / dissolution / timeout |
| `ChannelPaused { reason, paused_until }` | DP-A18 / DP-Ch35 | `channel_pause` |
| `ChannelResumed { resumed_at, by }` | DP-A18 / DP-Ch35 | `channel_resume` or auto-expiry |
| `TurnSlotClaimed { actor, expected_until, reason }` | DP-Ch51 | `claim_turn_slot` |
| `TurnSlotReleased { actor, release_kind }` | DP-Ch51 | `release_turn_slot` or auto-timeout |
| `TurnSlotTimedOut { actor, expected_until, actual_at }` | DP-Ch52 | CP scheduler 30-s auto-timeout |
| `TurnBoundary { turn_number, turn_data }` | DP-A17 / DP-Ch21 | every `advance_turn` call (note: **the `turn_data` payload IS what we semantically call PlayerTurn / NPCTurn / NPCRoutine / WorldTick**) |

**Causal-ref policy:** n/a — DP-internal. SystemEvents don't carry feature-level causal_refs (DP may carry its own internal references like `route_session_id` for handoff events, but those are DP-internal).

**Validator chain:** **none** — SystemEvents are trusted by construction. They are the output of DP operations that have already passed DP's own checks (capability, single-writer, epoch-fence, etc.).

**Note on TurnBoundary:** Per Phase 0 B1 decision, TurnBoundary is the **wire-format SystemEvent** that carries a PlayerTurn / NPCTurn / NPCRoutine / WorldTick as its payload. When you emit `dp::advance_turn(turn_data=X)` where `X: TurnEvent`, DP commits a TurnBoundary SystemEvent with `turn_data=X`. The semantic identity of the event is the EVT-T* category implied by X's actor + producer; the wire format is TurnBoundary. Both are valid lenses: feature designers think "this is a PlayerTurn"; wire-protocol consumers see "TurnBoundary with payload".

**Cross-ref:** [DP-A18 Channel lifecycle + canonical events](../06_data_plane/02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25), [DP-Ch51 Turn slot](../06_data_plane/21_llm_turn_slot.md), [DP-A17 Turn numbering](../06_data_plane/02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25).

---

## EVT-T5 — BubbleUpEvent

**Definition:** A canonical event emitted at a parent channel level by a registered `BubbleUpAggregator` (DP-Ch25), aggregating descendant events probabilistically per the aggregator's policy.

**Producer:** the aggregator implementation, running on the parent channel's writer node (DP-Ch26 in-process trait + runtime loop).

**Trigger:** descendant events match the aggregator's `SourceFilter`; the aggregator's `on_event` returns an `EmitDecision::Emit { ... }`.

**DP commitment mechanism:** aggregator runtime loop calls `dp::t2_write` on the parent channel for the aggregator's emit aggregate-type. Carries `causal_refs` to the source event(s) at the descendant channel.

**Lifecycle stage:** committed canonical at parent channel.

**Causal-ref policy:** **REQUIRED.** Every BubbleUpEvent must reference at least one source event at a descendant channel. Single-source (one rumor → one upper event) and multi-source (10 cell events aggregated → one tavern bubble) both supported.

**Sub-shapes (feature-defined per aggregator):** the aggregator's `register_bubble_up_aggregator` call declares the emit type; PL_002 (gossip aggregator) will define types like `RumorBubble`, `CrowdDensityChange`, `FactionReputationDrift`. Each is its own aggregate type per DP-Ch25.

**Privacy redaction:** per registered `RedactionPolicy` (DP-Ch43). Transparent / SkipPrivate / AnonymizeRefs / Custom. Choice is a per-aggregator-registration parameter.

**Validator chain:** **subset** — aggregator-emitted events bypass A6 injection-defense (no LLM input on the emit path; aggregator code is feature-trusted). Schema + capability + causal-ref integrity remain. World-rule lint optional per aggregator (some bubble-ups are pure stats, some carry narrative).

**Cross-ref:** [DP-A15 Per-channel ordering](../06_data_plane/02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25), [DP-Ch25..Ch30 BubbleUp aggregator](../06_data_plane/16_bubble_up_aggregator.md), [DP-Ch43 Redaction](../06_data_plane/19_privacy_redaction_policies.md).

---

## EVT-T6 — LLMProposal

**Definition:** An event emitted by an LLM-driven service (Python `roleplay-service`) onto the proposal bus, carrying a proposed PlayerTurn or NPCTurn that has NOT yet been validated by the EVT-V* pipeline.

**Producer:** roleplay-service (and future LLM services). Producer JWT carries `produce: [LLMProposal]` only — never direct PlayerTurn/NPCTurn (per [EVT-A4](02_invariants.md#evt-a4--producer-category-binding) + [EVT-A7](02_invariants.md#evt-a7--llm-proposals-are-pre-validation-only-never-authoritative)).

**Trigger:** LLM-generated output post-sanitize from roleplay-service. After `AssemblePrompt(intent=session_turn|npc_reply)` + LLM stream + A6 output filter, the proposal is published to the bus.

**DP commitment mechanism:** **NOT DP.** LLMProposal lives on the proposal bus (Redis Streams via I13 outbox), NOT in any per-reality channel event log. Once validated, the world-service consumer commits a fresh PlayerTurn / NPCTurn via `dp::advance_turn` — the original proposal is referenced from the committed event's metadata but not retained as a canonical event.

**Lifecycle stage:** **pre-validation.** Three terminal states:
- `Validated` — promoted to PlayerTurn or NPCTurn; this is what consumers see in the channel log.
- `Rejected { reason }` — validator rejected; logged + dead-lettered. The proposal is NOT promoted; the original PC turn submission gets a soft-fail UX (see PL_001 §9 and per A5-D4 fallback).
- `Expired` — validator did not consume the proposal within the bus retention window (default 60s).

**Causal-ref policy:** Optional. A proposal may reference a prior turn it's reacting to (NPCReply proposal ref'ing the triggering PlayerTurn). Once validated and promoted to NPCTurn, the causal-ref carries through to the committed event.

**Sub-shapes (Phase 3 contract):** `PlayerTurnProposal { actor: pc_id, intent: TurnIntent, narrator_text: Option<String>, fiction_duration_proposed }` and `NPCTurnProposal { actor: npc_id, intent, narrator_text }`. Schema mirrors the underlying turn types but adds `proposal_id`, `proposed_at`, `producer_service` envelope fields.

**Validator chain:** the FULL EVT-V* pipeline runs ON the proposal as input. Output is `Validated → commit` or `Rejected → dead-letter`.

**Cross-ref:** [EVT-A7](02_invariants.md#evt-a7--llm-proposals-are-pre-validation-only-never-authoritative), [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state), [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) (Phase 3).

---

## EVT-T7 — CalibrationEvent

**Definition:** A canonical event emitted when a fiction-time advancement crosses a date boundary (`day_passes` / `month_passes` / `year_passes`), per MV12-D5. Per Phase 0 B4 decision, the producer is **world-service** (derives from FictionClock advance), not DP — DP must remain content-agnostic.

**Producer:** world-service. After committing a FictionClockAdvance AggregateMutation (per EVT-T3), world-service inspects the before/after `current_fiction_ts` and, if any date boundary was crossed, emits one CalibrationEvent per crossing in the same transactional cluster (or as immediate follow-ups — exact ordering specified in Phase 4 EVT-L*).

**Trigger:** FictionClockAdvance crossing a date boundary. SPIKE_01 turn 16 example: `/travel 23 days` crosses 23 day-boundaries + 1 month-boundary → emits 23 `day_passes` + 1 `month_passes`.

**DP commitment mechanism:** `dp::t2_write::<CalibrationEvent>(ctx, id, delta)` on a dedicated calibration aggregate, OR (alternative under consideration) commit them as channel events tagged with the event-type discriminator `calibration` without a backing aggregate. **Locked: dedicated aggregate** (Phase 2 EVT-S* will specify the aggregate shape) so calibration becomes queryable as state, not just stream.

**Lifecycle stage:** committed canonical.

**Causal-ref policy:** **REQUIRED.** Each CalibrationEvent references the PlayerTurn / NPCTurn / WorldTick whose FictionClockAdvance caused the boundary crossing. This makes "which turn caused day_passes 1256-09-30 → 1256-10-01?" answerable via causal walk.

**Sub-shapes:** `DayPasses { from_date, to_date }` / `MonthPasses { from_month, to_month }` / `YearPasses { from_year, to_year }`. Big jumps emit multiple CalibrationEvents in chronological order.

**Validator chain:** schema → capability (world-service-only producer) → causal-ref integrity → commit. No A6 (no LLM input on this path). World-rule lint optional (could check "year cannot decrease" but FictionClock monotonicity already guarantees).

**Use cases (downstream consumers):** scheduled-event scheduler (EVT-T11 WorldTick) wakes on month_passes / year_passes / specific-day matchers. Bubble-up aggregators may aggregate across day boundaries (gossip half-life). Quest engine triggers beats on time markers.

**Why this is its own category (not a sub-type of AggregateMutation):** SPIKE_01 obs#15 explicitly distinguished `turn.time_advancement` from `turn.player_action`. CalibrationEvents have a fixed shape (no feature-defined sub-types), a fixed producer (world-service only), and a specific downstream consumer pattern (schedulers). Folding them into AggregateMutation would mix structural deltas with calendar markers.

**Cross-ref:** [MV12-D5](../decisions/locked_decisions.md#L570), SPIKE_01 obs#15, [PL_001 §12 fast-forward example](../features/04_play_loop/PL_001_continuum.md).

---

## EVT-T8 — AdminAction

**Definition:** A canonical event emitted when an operator (admin / human / authorized service-account) performs an admin command via the S5 admin-action policy. Examples: pause channel, force-end scene, override world-rule, force-revert turn N (V2+).

**Producer:** `admin-cli` via S5 `AttemptStateTransition` / dispatch. Capability JWT carries `produce: [AdminAction]` exclusive to admin-cli.

**Trigger:** operator-initiated. S5 enforces actor authorization, reason length, dual-actor (Tier 1) or single-actor (Tier 2/3), cooldown.

**DP commitment mechanism:** depends on the admin operation:
- `channel_pause` / `channel_resume` → `dp::channel_pause` / `dp::channel_resume`; DP emits SystemEvent ChannelPaused/Resumed as side effect; AdminAction event committed alongside as audit anchor (EVT-T8 references the SystemEvent).
- `force_end_scene` → admin-cli triggers cell channel dissolve + emits AdminAction.
- `world_rule_override` → admin-cli writes to a world-rule-override aggregate via `dp::t3_write`; AdminAction is the event that commits.
- `force_revert_turn` (V2+) — out of V1 scope; will be designed when DF8 / canon-rollback lands.

**Lifecycle stage:** committed canonical, immutable, audit-grade. `admin_action_audit` table mirrors per S5.

**Causal-ref policy:** Optional. When the action targets a specific event (e.g., force-revert turn N), the AdminAction references that event.

**Sub-shapes:** `Pause { channel, reason, paused_until }` / `Resume { channel }` / `ForceEndScene { channel, reason }` / `WorldRuleOverride { rule_id, override_value, reason, expires_at }` / future sub-types per S5 admin-command registry.

**Validator chain:** schema → capability (S5 actor authentication; impact-class gating) → S5 dual-actor (Tier 1 only) → world-rule lint (optional — the admin may explicitly override, in which case lint becomes audit-only) → causal-ref integrity → commit. **No A6 injection defense** — admin input is operator-authenticated, not adversarial.

**Cross-ref:** S5 [02_storage S05_admin_command_classification.md](../02_storage/S05_admin_command_classification.md), [DP-Ch35 channel_pause](../06_data_plane/17_channel_lifecycle.md#dp-ch35--channel_pause--channel_resume-primitives).

---

## EVT-T9 — QuestBeat

**Definition:** A canonical event emitted by the quest engine when a quest scaffold transitions: trigger fires, beat advances, or outcome resolves. Per catalog Q-1..Q-9.

**Producer:** quest engine (feature service, future). Capability JWT carries `produce: [QuestBeat]`. V1 placeholder; full implementation gated on quest engine landing.

**Trigger:** depends on sub-shape:
- `Trigger` — quest entry condition met (fiction-clock crossed marker; PlayerTurn matched a quest predicate; CalibrationEvent fired). Producer: quest engine evaluates triggers on FictionClock advance and on each turn commit.
- `Advance` — quest beat completed, next beat unlocked. Producer: quest engine on consumer of triggering events.
- `Outcome` — quest resolved (success/failure/abandon). Producer: quest engine on terminal beat completion.

**DP commitment mechanism:** `dp::t2_write` on quest aggregate (per-quest-instance state). Causal-ref to triggering event.

**Lifecycle stage:** committed canonical.

**Causal-ref policy:**
- `Trigger`: optional (may reference the calibration / turn that triggered).
- `Advance`: **required** — references the previous QuestBeat (the last `Advance` or `Trigger` for this quest).
- `Outcome`: **required** — references the `Trigger` for chain provenance.

**Validator chain:** schema → capability → world-rule lint (quest pre-conditions met?) → causal-ref integrity → commit. No A6.

**Note on "QuestBeat causes WorldTick":** when a quest outcome triggers a world-level beat (PC saves Tương Dương → siege outcome reverses), the QuestBeat::Outcome causal-refs a follow-up WorldTick that the scheduler emits. This is the canonical use case the brief §S7 mentioned.

**Cross-ref:** catalog Q-1..Q-9 (when quest engine lands).

---

## EVT-T10 — NPCRoutine (V1+30d)

**Definition:** A canonical event emitted when a scheduler-driven NPC autonomous routine fires — e.g., "Lão Ngũ opens shutters at dawn" / "Tiểu Thúy fetches water at noon". Per MV12-D2 source #2 + SPIKE_01 obs#21.

**Producer:** `world-rule-scheduler` service (feature service, future V1+30d). Capability JWT carries `produce: [NPCRoutine]`.

**Trigger:** fiction-clock matches a pre-declared routine schedule (NPC sheet + routine table). Scheduler polls on FictionClock advance (or subscribes to CalibrationEvent stream).

**DP commitment mechanism:** `dp::advance_turn(ctx, &cell_channel, turn_data: TurnEvent { actor: ActorId::Npc, intent: ... })`. Same as NPCTurn, but with `producer_service = world-rule-scheduler` envelope and no PC trigger.

**Lifecycle stage:** committed canonical.

**Sub-shapes:** mirrors NPCTurn (Speak / Action / Narration). The narration during a routine when no PC observes is **flavor** per [EVT-A8](02_invariants.md#evt-a8--flavor-narration-is-not-events) — only the structural deltas (NPC location, NPC state) are canonical.

**Causal-ref policy:** Optional. May reference a CalibrationEvent (if scheduled by date) or a WorldTick.

**Why a separate category (not NPCTurn):** different producer (scheduler vs orchestrator), different trigger (no PC interaction), different lifecycle (V1+30d, not V1). Conflating with NPCTurn would muddy producer rules + JWT claims.

**Validator chain:** schema → capability (`world-rule-scheduler` only) → world-rule lint (NPC routine consistent?) → canon-drift (does routine contradict canon?) → causal-ref integrity → commit. **No A6** — scheduler is feature-trusted, not LLM-input.

**V1 status:** **placeholder.** No NPCRoutine emission in V1. SPIKE_01 obs#21 explicitly leaves NPCRoutine as V1+30d future work. Taxonomy reserves the slot.

**Cross-ref:** [MV12-D2 source #2](../decisions/locked_decisions.md#L567), SPIKE_01 obs#21, [`08_scheduled_events.md`](08_scheduled_events.md) (Phase 4).

---

## EVT-T11 — WorldTick (V1+30d)

**Definition:** A canonical event emitted when a fiction-time-triggered scheduled author beat fires. Per MV12-D2 source #3 + brief §S6. Author places a beat at design time ("Mongol siege of Tương Dương begins on day 1257-thu-3"); the scheduler fires the WorldTick when the FictionClock crosses that threshold.

**Producer:** `world-rule-scheduler` service (same as NPCRoutine; different sub-type / different aggregate).

**Trigger:** FictionClock crosses an author-placed threshold (stored in a `world_tick_schedule` aggregate at reality creation, mutable via author UI). Scheduler subscribes to CalibrationEvent stream + checks pending threshold list.

**DP commitment mechanism:** `dp::advance_turn` on the channel where the beat fires (typically town/country/continent — the level depends on beat scope). Often emits as side effect a fresh ChannelLifecycle event (e.g., siege spawns a new "battlefield" channel).

**Lifecycle stage:** committed canonical.

**Sub-shapes (feature-defined):** scheduled-events feature (Phase 4) defines the contract — typical shapes are `MajorEvent { event_id, scope_channel, narrative_seed }` / `WeatherChange { weather_kind }` / `FactionMovement { faction, action }`.

**Causal-ref policy:** Optional. May reference a triggering QuestBeat::Outcome (per §EVT-T9 example) or be standalone (author-placed beat).

**Idempotency:** **CRITICAL.** A big-jump fast-forward (PC `/travel` 23 days) may cross multiple WorldTick thresholds in one FictionClock advance. Idempotency key includes `(reality_id, world_tick_id)` so each beat fires exactly once even if the scheduler is replayed. Specified in Phase 4 EVT-S* + `08_scheduled_events.md`.

**Recovery:** if scheduler is down for 6 hours wall-clock, missed beats fire on restart in fiction-chronological order. No skip-on-restart.

**Validator chain:** schema → capability (`world-rule-scheduler` only) → world-rule lint (beat preconditions met given current world state?) → canon-drift (beat consistent with current canon?) → causal-ref integrity → commit. No A6.

**V1 status:** **placeholder.** No WorldTick emission in V1 (V1 paused-when-solo per MV12-D4). V1+30d activation.

**Cross-ref:** [MV12-D2 source #3](../decisions/locked_decisions.md#L567), brief §S6, [`08_scheduled_events.md`](08_scheduled_events.md) (Phase 4).

---

## Closed-set proof

Per [EVT-A1](02_invariants.md#evt-a1--closed-set-event-taxonomy), every event from PL_001 + every observation in SPIKE_01 + every DP-emitted canonical event maps to exactly one EVT-T*. This table is the proof.

| Source | Event | → Category |
|---|---|---|
| PL_001 §3.5 TurnEvent | Speak | **EVT-T1** PlayerTurn (sub-shape Speak) |
| PL_001 §3.5 TurnEvent | Action | **EVT-T1** PlayerTurn (sub-shape Action) |
| PL_001 §3.5 TurnEvent | MetaCommand | **EVT-T1** PlayerTurn (sub-shape MetaCommand) |
| PL_001 §12 / SPIKE_01 turn 11 | FastForward (`/sleep until dawn`) | **EVT-T1** PlayerTurn (sub-shape FastForward) + flavor Narration sub-shape (per EVT-A8) |
| PL_001 §10 / SPIKE_01 turn 16 | FastForward (`/travel to Tương Dương`) | **EVT-T1** PlayerTurn (sub-shape FastForward) |
| PL_001 §11 NPC react | NPC reaction (Lão Ngũ, Tiểu Thúy responding) | **EVT-T2** NPCTurn |
| PL_001 §3.4 / DP-A18 | MemberJoined / MemberLeft | **EVT-T4** SystemEvent |
| DP-A18 / DP-Ch35 | ChannelPaused / ChannelResumed | **EVT-T4** SystemEvent |
| DP-Ch51 | TurnSlotClaimed / TurnSlotReleased / TurnSlotTimedOut | **EVT-T4** SystemEvent |
| DP-A17 | TurnBoundary (wire format only) | **EVT-T4** SystemEvent (payload IS EVT-T1/T2/T10/T11 per Phase 0 B1) |
| PL_001 §5.2 | SceneStateDelta::AmbientUpdate | **EVT-T3** AggregateMutation |
| PL_001 §3.6 | ActorBindingDelta::MoveTo | **EVT-T3** AggregateMutation |
| PL_001 §3.1 | FictionClockAdvance | **EVT-T3** AggregateMutation (with EVT-T7 follow-ups when crossing date boundaries) |
| MV12-D5 / SPIKE_01 obs#15 | day_passes / month_passes / year_passes | **EVT-T7** CalibrationEvent |
| DP-A15 + DP-Ch25 | Bubble-up rumor at parent channel | **EVT-T5** BubbleUpEvent |
| DP-A6 | Python LLM proposal events (pre-validation) | **EVT-T6** LLMProposal |
| brief §S6 / SPIKE_01 obs#15 | "Siege Tương Dương starts day X-thu-1257" | **EVT-T11** WorldTick (V1+30d) |
| SPIKE_01 obs#21 | "Lão Ngũ opens shutters at dawn" routine | **EVT-T10** NPCRoutine (V1+30d) |
| DP-Ch35 + S5 | Admin pause / force-end-scene / world-rule override | **EVT-T8** AdminAction (also emits EVT-T4 SystemEvent as side-effect) |
| catalog Q-1..Q-9 | Quest trigger / beat advance / outcome | **EVT-T9** QuestBeat (V1+) |
| SPIKE_01 obs#9, obs#17 | NPC opinion update (Lão Ngũ trust+1 after turn 7) | **EVT-T3** AggregateMutation (state delta on `npc_pc_relationship` aggregate) |
| SPIKE_01 obs#16 | Long-skip flavor narration ("Hai mươi ba ngày đường sau") | **NOT AN EVENT** per EVT-A8 — non-canonical text, regenerable, audit-log only |
| SPIKE_01 obs#14 turn 14 | NPC speech becomes L3 canon (du sĩ "đi cổng Bắc") | **EVT-T2** NPCTurn (canonical L3-canon emergence is a side-effect of the committed event, not a separate category) |
| SPIKE_01 obs#11 | L2 canon seeding (Dương Quá reference at turn 7) | **EVT-T2** NPCTurn (seeding is a side-effect of NPC speech) |
| SPIKE_01 obs#22 | Player intent vs PC plausibility tension | **NOT A TAXONOMY ITEM** — meta-design concern, not an event |
| SPIKE_01 obs#19 | Weather/ambient state transitions during time-skip | **EVT-T3** AggregateMutation (V1: LLM-improvised per turn, no separate event) |
| SPIKE_01 obs#13 | Session-resume UX choice (continue / sleep / wake) | **NOT AN EVENT** — UX flow generates a PlayerTurn (FastForward sub-shape) once user chooses |
| SPIKE_01 obs#22 / Session-resume | session.action_resolved (per A5 dispatch) | This is implementation detail of EVT-T1 PlayerTurn with command_kind=verb; not separate category |
| Future DF3 (V2+) | L3 → L2 canon promotion | **EXCLUDED from EVT-T*** per Phase 0 B6 — owned by [`../03_multiverse/`](../03_multiverse/) + meta-worker, not Event Model |
| Future DF12 (withdrawn) | Cross-reality coordination | **EXCLUDED** — withdrawn feature; would not be EVT-T* even if reinstated |

**Result:** Every observable event maps to exactly one EVT-T* row. Closed-set property satisfied.

---

## Cross-references

- [EVT-A1..A8 axioms](02_invariants.md) — invariants this taxonomy implements
- [`04_producer_rules.md`](04_producer_rules.md) — EVT-P* per category (Phase 2)
- [`05_validator_pipeline.md`](05_validator_pipeline.md) — EVT-V* validator chain per category (Phase 3)
- [`06_per_category_contracts.md`](06_per_category_contracts.md) — required/optional fields per category (Phase 2)
- [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md) — LLMProposal bus protocol (Phase 3)
- [`08_scheduled_events.md`](08_scheduled_events.md) — NPCRoutine + WorldTick scheduler (Phase 4)
- [`09_causal_references.md`](09_causal_references.md) — causal-ref shape used across categories (Phase 4)
- [PL_001 §3.5](../features/04_play_loop/PL_001_continuum.md) — first feature consuming EVT-T1
- [SPIKE_01 §6 + §9](../features/_spikes/SPIKE_01_two_sessions_reality_time.md) — 22 observations grounding the categories
