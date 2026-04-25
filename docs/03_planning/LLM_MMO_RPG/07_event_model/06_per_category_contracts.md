# 06 — Per-Category Contracts

> **Status:** LOCKED Phase 2b (2026-04-25). Per [EVT-A1](02_invariants.md#evt-a1--closed-set-event-taxonomy) closed set + [EVT-P*](04_producer_rules.md) producer rules, this file specifies the **payload contract** for each EVT-T* category: envelope fields, sub-shape schemas, idempotency key composition, max payload size, schema version placement, causal-ref policy.
> **Stable IDs:** No new IDs introduced — this file specifies contracts for EVT-T1..T11 already locked in [`03_event_taxonomy.md`](03_event_taxonomy.md).
> **Resolves:** MV12-D8 (narration taxonomy split — EVT-T1 FastForward sub-shape) + MV12-D9 (5 V1 commands locked — EVT-T1 MetaCommand sub-shape).

---

## How to use this file

When implementing a feature:

1. Find the EVT-T* contract row matching the event your feature emits/consumes.
2. Implement payload using **only** the listed fields. Adding a new field requires schema-version bump per I14 additive-first.
3. Honor **required** fields strictly. Optional fields may default to absent/None.
4. Honor **max payload size** — runtime SDK rejects oversized payloads with `EventModelError::PayloadTooLarge`.
5. **Schema version field** lives at the envelope level (per Phase 2 D7 envelope choice). Sub-shape additions are payload-internal additive evolution.

Field types in this file are **abstract** (UUID, String, i64-millis, Vec, etc.) per scope rule O3 (no Rust code in spec). Concrete Rust types land in feature implementation.

---

## Common envelope (ALL EVT-T* events share this)

Every event committed to a per-reality event log carries this envelope. EVT-T8 LLMProposal also carries it (with adjusted commit-related fields — see EVT-T6 contract below).

| Field | Type | Required | Purpose |
|---|---|:---:|---|
| `event_id` | u64 | ✅ | DP-allocated `channel_event_id` per DP-A15 (gapless monotonic per channel). DP fills at commit. |
| `event_category` | EvtCategory enum | ✅ | EVT-T1..T11 discriminator. Closed-set per EVT-A1. |
| `event_sub_shape` | String | ✅ | Per-category sub-shape name (e.g., `"Speak"` for EVT-T1, `"MemberJoined"` for EVT-T4). Closed-set within each category. |
| `event_schema_version` | u32 | ✅ | Envelope-level schema version per Phase 2 D7. Increments on breaking change to envelope; sub-shape additions are payload-internal (no envelope bump). |
| `producer_service` | String | ✅ | Service-account name from JWT `sub` claim per EVT-P*. |
| `wall_clock_committed_at` | timestamp millis | ✅ | When DP committed the event (audit/replay). |
| `fiction_ts_start` | i64 millis | ✅ | Per MV12-D7. The fiction-time when the event begins. |
| `fiction_duration` | i64 millis | ✅ | Per MV12-D7. Duration of the event in fiction-time. Often 0 for instant events. |
| `turn_number` | u64 | ✅ | Per DP-A17. The channel's current turn_number at commit time (0 if channel never advanced). |
| `causal_refs` | Vec\<CausalRef\> | optional | Per [EVT-A6](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free). Required for some categories (EVT-T2, EVT-T5, EVT-T7); see per-category rules. |
| `idempotency_key` | IdempotencyKey | ✅ | Per [EVT-P*](04_producer_rules.md) uniform shape `(producer_service, client_request_id, target)`. |
| `payload` | category-specific | ✅ | Per-category sub-shape payload (rest of this file). |

`CausalRef` shape (per EVT-A6):
```
CausalRef {
  channel_id: ChannelId,
  channel_event_id: u64,
}
```
Both fields required. Validator pipeline enforces same-reality + reference-exists at commit time.

**Envelope max size:** 512 bytes. Payload size limit varies per category (next sections). Total event size ≤ envelope + payload max.

---

## EVT-T1 PlayerTurn

**Sub-shapes:** `Speak` · `Action` · `MetaCommand` · `FastForward` (4 V1 sub-shapes; MV12-D8 + MV12-D9 resolved here).

**Payload max size:** 10 KB committed (envelope + structural fields). Flavor-text overflow goes to audit log per EVT-A8 (separate cap 50 KB).

**Causal-ref policy:** optional. Free-narrative Speak/Action typically have empty `causal_refs`. Chained MetaCommand resolutions reference parent command. FastForward typically empty (it's the *initiation* of a fast-forward, not a reaction).

### Sub-shape: `Speak`

Free-narrative dialogue from PC.

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `actor` | ActorId::Pc { pc_id } | ✅ | Always PC for EVT-T1. |
| `narrator_text` | String (max 2 KB) | ✅ | Post-validation, post-A6 output filter LLM-generated narration. |
| `speech_target` | Option\<ActorId\> | optional | If directed at specific NPC. None = broadcast to scene. |
| `pc_emotion_hint` | Option\<String\> (max 200 chars) | optional | Free-form for LLM-context (e.g., "nervous", "joking"). Player-declared or LLM-inferred. |
| `intent_class` | IntentClass enum | ✅ | Per A5-D1: always `Story` for Speak sub-shape. |

### Sub-shape: `Action`

Physical action narration from PC.

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `actor` | ActorId::Pc { pc_id } | ✅ | |
| `narrator_text` | String (max 2 KB) | ✅ | LLM-generated narration of the action. |
| `physical_target` | Option\<TargetRef\> | optional | Object/NPC/place targeted by the action. |
| `intent_class` | IntentClass enum | ✅ | Per A5-D1: typically `Story`; `Command` if the player used a verb form (which routes to MetaCommand sub-shape instead). |

**Note:** state-mutating Actions MUST come from `MetaCommand` sub-shape (per A5-D3 — state changes from `/verb` only, NEVER from LLM tool calls). `Action` is narration; the structural deltas come from companion EVT-T3 AggregateMutation events.

### Sub-shape: `MetaCommand`

System-recognized commands. **5 V1 command kinds locked per Phase 2 D4** (additive-first per I14 — new kinds add via schema evolution).

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `actor` | ActorId::Pc { pc_id } | ✅ | |
| `command_kind` | CommandKind enum | ✅ | One of: `Sleep` · `Travel` · `Whisper` · `Look` · `Verbatim`. |
| `command_args` | command-specific | ✅ | Typed args per command_kind; see sub-tables below. |
| `narrator_text` | Option\<String\> (max 2 KB) | optional | LLM-generated post-resolution narration. None for `Verbatim`. |
| `intent_class` | IntentClass enum | ✅ | Per A5-D1: always `Command` (or `Meta` for Verbatim — feature-decided). |

**`command_args` per kind:**

| `command_kind = Sleep` | Type | Required |
|---|---|:---:|
| `until` | `SleepUntil::Dawn` \| `Duration { fiction_ms }` \| `NextEvent { kind }` | ✅ |
| `private_safe_required` | bool | ✅ (default true) |

| `command_kind = Travel` | Type | Required |
|---|---|:---:|
| `destination` | PlaceRef (canon-grounded) | ✅ |
| `mode` | `TravelMode::OnFoot` \| `Mounted` \| `Carriage` | ✅ |
| `expected_duration_fiction_ms` | i64 | ✅ (LLM-estimated, world-rule-validated) |

| `command_kind = Whisper` | Type | Required |
|---|---|:---:|
| `target` | ActorId | ✅ |
| `body` | String (max 1 KB) | ✅ |

| `command_kind = Look` | Type | Required |
|---|---|:---:|
| `target` | TargetRef::Place \| Object \| Actor | ✅ |

| `command_kind = Verbatim` | Type | Required |
|---|---|:---:|
| `text` | String (max 4 KB) | ✅ — raw player text without LLM rewriting (for poetry, song lyrics, etc.) |

**Note:** Verbatim still passes through A6 5-layer injection defense as input — it's just not rewritten by LLM. Output is the player's literal text; canon-drift validator runs but the verdict is "literal player intent" not "LLM canon adherence".

### Sub-shape: `FastForward` (resolves MV12-D8)

Long-duration jump triggered by MetaCommand (Sleep / Travel). Carries structural delta (canonical) + flavor text (non-canonical per EVT-A8).

| Field | Type | Required | Canonical? |
|---|---|:---:|:---:|
| `actor` | ActorId::Pc { pc_id } | ✅ | yes |
| `cause` | `FastForwardCause::FromMetaCommand { command_kind, parent_event_id }` | ✅ | yes |
| `structural_delta` | StructuralDelta (typed, canonical) | ✅ | **YES — committed to event log** |
| `flavor_text_audit_id` | Option\<UUID\> | optional | NO — pointer to audit-log entry containing flavor text (async-fillable; null until roleplay-service produces narration) |

**`StructuralDelta` shape:**

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `fiction_clock_advance_ms` | i64 | ✅ | Total fiction-time advanced (= `fiction_duration` envelope field). |
| `pc_state_changes` | Vec\<PcStateChange\> | optional | Money delta, body-memory fade, equipment wear, etc. Each is a typed sub-record. |
| `actor_movements` | Vec\<ActorMovement\> | optional | NPC/PC location changes during the skip. Each carries `actor`, `from`, `to`, `at_fiction_ts`. |

**Flavor text storage:** per [EVT-A8](02_invariants.md#evt-a8--flavor-narration-is-not-events), `flavor_text` itself is **NOT in the event log**. It's stored in a separate audit table `event_flavor_audit` with primary key `flavor_text_audit_id`. World-service emits FastForward with `flavor_text_audit_id = None`; roleplay-service later generates narration via `contracts/prompt/AssemblePrompt(intent=npc_reply, ...)`, writes to audit table, world-service updates FastForward event's audit-id pointer (DP supports this via `dp::update_event_audit_pointer` — Phase 4 EVT-S* primitive, deferred).

**Replay implication:** debug-replay shows structural delta exactly + flavor text best-effort from audit table per EVT-Q6/EVT-Q10 (Phase 4).

---

## EVT-T2 NPCTurn

**Sub-shapes:** mirrors PlayerTurn — `Speak` · `Action` · `MetaCommand` · `Narration` (4 V1 sub-shapes). **NO `FastForward`** — NPCs don't auto-travel in V1; that's V1+30d EVT-T10 NPCRoutine.

**Payload max size:** 10 KB committed.

**Causal-ref policy:** **REQUIRED.** Every NPCTurn must reference at least one of: (a) the triggering PlayerTurn / NPCTurn, or (b) the scene-trigger event (e.g., MemberJoined when PC entered scene). Validator pipeline rejects empty `causal_refs` for EVT-T2.

### Sub-shapes (delta from EVT-T1)

| Sub-shape | Same as EVT-T1 except | Notes |
|---|---|---|
| `Speak` | `actor` is `ActorId::Npc { npc_id }` | NPC dialogue. SPIKE_01 obs#14 — NPC speech becomes L3 canon as side-effect of commit. |
| `Action` | `actor` is `ActorId::Npc` | NPC physical action narration. |
| `MetaCommand` | `actor` is `ActorId::Npc`; only `Whisper` and `Look` kinds available in V1 (NPCs don't `/sleep` or `/travel` autonomously per EVT-A7/A5-D3 — that's NPCRoutine V1+30d) | |
| `Narration` | NPC-only sub-shape: `flavor_text` (max 2 KB), `parent_event_ref` causal-ref | Atmospheric narration emitted by orchestrator (e.g., "Tiểu Thúy đặt khay trà xuống bàn nhẹ nhàng"). Not a command, not a speech. **All flavor — no canonical content; exists only for replay/UI rendering.** Per EVT-A8 framework, but committed as event for UI streaming convenience. |

**Note on Narration:** unlike EVT-T1 FastForward where flavor splits from structural, EVT-T2 Narration is fully flavor. It's still committed (carries event_id, takes up channel_event_id slot) so UI streaming sees it in order, but consumers MUST treat its `flavor_text` as regenerable. Validator pipeline runs only safety checks (A6 output filter) on Narration; no canon-drift / world-rule lint.

---

## EVT-T3 AggregateMutation

**Sub-shapes:** **none formally** — sub-discriminator is the **`aggregate_type`** field. Each aggregate type owned by a feature service has its own delta shape.

**Payload max size:** 5 KB committed. Larger deltas should be split or use t3_write_multi for atomicity.

**Causal-ref policy:** optional but **strongly recommended** when the AggregateMutation is caused by a parent turn (FictionClockAdvance after PlayerTurn, etc.). Rule of thumb: if the mutation makes sense only in context of a parent event, ref it.

### Common payload fields

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `aggregate_type` | String | ✅ | E.g., `"fiction_clock"`, `"actor_binding"`, `"scene_state"`, `"npc_pc_relationship"`. Closed-set per feature (each feature lists its owned types in catalog). |
| `aggregate_id` | aggregate-specific ID | ✅ | E.g., `FictionClockId::SINGLETON`, `ActorId`, `(channel_id, scene_id)`. |
| `delta_kind` | String | ✅ | Sub-discriminator within aggregate_type (e.g., `"AmbientUpdate"` for scene_state, `"MoveTo"` for actor_binding). |
| `delta_payload` | aggregate+delta-specific | ✅ | Typed per `(aggregate_type, delta_kind)` pair. |
| `prior_state_hash` | Option\<blake3 hash\> | optional | Optimistic concurrency check; if set, commit fails on stale write. Feature-level optional. |

### V1 aggregate types covered (PL_001 + PL_002 known)

| aggregate_type | Owner service | Delta kinds |
|---|---|---|
| `fiction_clock` | world-service | `Advance { duration_ms }` |
| `scene_state` | world-service | `AmbientUpdate { ambient }`, `Begin { scene_meta }`, `End { reason }` |
| `actor_binding` | world-service | `MoveTo { new_cell, turn }`, `Spawn { initial_cell }`, `Despawn { reason }` |
| `participant_presence` | world-service (T1) | `Enter { join_method }`, `Leave { leave_reason }`, `Idle { since_turn }`, `Active` |
| `npc_pc_relationship` | world-service | `OpinionDelta { dimension, delta, reason_event_ref }`, `MemoryAppend { text, source_event_ref }` |

V1+ aggregates (quest_state, pc_inventory, pc_stats, world_tick_schedule) lock their delta shapes when their owning feature's design lands.

---

## EVT-T4 SystemEvent

**Sub-shapes:** **closed set, owned by DP per EVT-P4** (this file does NOT redesign — only enumerates for cross-reference).

**Payload max size:** 2 KB committed (DP keeps payloads small; lifecycle facts).

**Causal-ref policy:** N/A — DP-internal events. DP may carry internal references (e.g., `route_session_id` for handoff) but no feature-level causal_refs.

| Sub-shape | Owner | Payload (per DP locked spec) |
|---|---|---|
| `MemberJoined` | DP-A18 / DP-Ch34 | `actor`, `joined_at_wall_clock`, `joined_via: SessionBind \| Migrated{from} \| Reactivated` |
| `MemberLeft` | DP-A18 / DP-Ch34 | `actor`, `left_at_wall_clock`, `reason: Voluntary \| Disconnected \| Migrated{to} \| ChannelDissolved \| TimedOut` |
| `ChannelPaused` | DP-A18 / DP-Ch35 | `reason`, `paused_until: Option<wall_clock>` |
| `ChannelResumed` | DP-A18 / DP-Ch35 | `resumed_at_wall_clock`, `by: Operator \| AutoExpiry` |
| `TurnSlotClaimed` | DP-Ch51 | `actor`, `expected_until_wall_clock`, `reason` |
| `TurnSlotReleased` | DP-Ch51 | `actor`, `release_kind: Normal \| Cancelled \| TimedOut` |
| `TurnSlotTimedOut` | DP-Ch52 | `actor`, `expected_until`, `actual_at_wall_clock` |
| `TurnBoundary` | DP-A17 | `turn_data: TurnEvent` (the actual EVT-T1/T2/T10/T11 payload — per Phase 0 B1 wire-format decision) |

**Note on TurnBoundary:** the `turn_data` field IS the PlayerTurn / NPCTurn / NPCRoutine / WorldTick payload as defined elsewhere in this file. Two lenses, same wire bytes.

---

## EVT-T5 BubbleUpEvent

**Sub-shapes:** feature-defined per registered aggregator (gossip-service registers `RumorBubble`; reputation-service registers `FactionReputationDrift`; etc.).

**Payload max size:** 5 KB committed. Aggregator state itself capped 1 MB per DP-Ch26 (separate from emit payload).

**Causal-ref policy:** **REQUIRED.** Every BubbleUpEvent must reference at least one source event at a descendant channel. Single-source or multi-source supported; multi-source bumps idempotency-key composition to hashed tuple.

### Common payload fields

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `aggregator_id` | UUID | ✅ | The registered aggregator's stable ID per DP-Ch28. |
| `aggregator_type` | String | ✅ | E.g., `"RumorBubble"`, `"CrowdDensity"`. Feature-defined. |
| `emit_payload` | aggregator-specific | ✅ | Typed per aggregator. Aggregator declares schema at registration. |
| `redaction_applied` | RedactionPolicy enum | ✅ | Which DP-Ch43 policy was active at emission (Transparent / SkipPrivate / AnonymizeRefs / Custom). For audit. |
| `source_event_count` | u32 | ✅ | How many descendant events fed into this emit. |

### V1 placeholder aggregator (gossip — PL_002+ feature)

| aggregator_type | emit_payload |
|---|---|
| `RumorBubble` | `rumor_text` (post-redaction), `confidence: f32`, `topic_canon_anchor: Option<CanonAnchorId>` |

Detailed shape locks when gossip feature designs (PL_002 or DF1 emergent).

---

## EVT-T6 LLMProposal

**Lifecycle stage:** pre-validation. Lives on the proposal bus, NOT in the channel event log per [EVT-A7](02_invariants.md#evt-a7--llm-proposals-are-pre-validation-only-never-authoritative).

**Sub-shapes:** `PlayerTurnProposal` · `NPCTurnProposal` (V1). Future LLM-driven categories add new sub-shapes here.

**Payload max size:** 12 KB on bus (slightly larger than committed PlayerTurn to accommodate LLM-generated text before output filter trims it).

**Causal-ref policy:** optional. NPCTurnProposal may reference triggering turn.

### Common envelope (proposal-specific overrides)

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `proposal_id` | UUIDv4 | ✅ | Proposer-generated; idempotency key. |
| `proposed_at_wall_clock` | timestamp millis | ✅ | When roleplay-service emitted to bus. |
| `producer_service` | String | ✅ | Always `"roleplay-service"` (or future LLM service). |
| `lifecycle_stage` | `Proposal` (always) | ✅ | At commit, world-service issues a fresh PlayerTurn/NPCTurn — proposal is not promoted in-place. |
| `target_channel` | ChannelId | ✅ | The cell channel the proposal targets. |
| `bus_retention_until` | timestamp millis | ✅ | Default `proposed_at + 60 s`. After this, proposal expires per Phase 3 [`07_llm_proposal_bus.md`](07_llm_proposal_bus.md). |

### Sub-shape: `PlayerTurnProposal`

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `actor` | ActorId::Pc { pc_id } | ✅ | |
| `proposed_intent_class` | IntentClass | ✅ | Per A5-D1 classifier. |
| `proposed_payload` | TurnPayload (Speak / Action / MetaCommand / FastForward shape) | ✅ | Same shape as the eventual PlayerTurn payload. |
| `prompt_template_version` | String | ✅ | E.g., `"session_turn/v3"`. Per S9 prompt assembly. Audit / debug. |
| `prompt_context_hash` | blake3 hash | ✅ | Hash of assembled prompt context (canon retrieval + memory + history). For determinism audit. |

### Sub-shape: `NPCTurnProposal`

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `actor` | ActorId::Npc { npc_id } | ✅ | |
| `proposed_payload` | NPCTurn payload (Speak / Action / MetaCommand-Whisper-or-Look / Narration) | ✅ | |
| `triggering_event_ref` | CausalRef | ✅ | The PlayerTurn or NPCTurn or scene-trigger this NPC reaction is replying to. |
| `prompt_template_version` | String | ✅ | E.g., `"npc_reply/v2"`. |
| `prompt_context_hash` | blake3 hash | ✅ | |

---

## EVT-T7 CalibrationEvent

**Sub-shapes:** `DayPasses` · `MonthPasses` · `YearPasses` (3 V1 sub-shapes; closed set per MV12-D5).

**Payload max size:** 1 KB committed (small lifecycle markers).

**Causal-ref policy:** **REQUIRED.** Every CalibrationEvent references the parent turn (PlayerTurn / NPCTurn / WorldTick) whose FictionClockAdvance caused the boundary crossing.

### Common payload

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `calibration_kind` | `DayPasses` \| `MonthPasses` \| `YearPasses` | ✅ | |
| `from_fiction_date` | FictionDate | ✅ | Boundary start (e.g., `1256-09-30`). |
| `to_fiction_date` | FictionDate | ✅ | Boundary end (e.g., `1256-10-01`). |
| `parent_advance_event_ref` | CausalRef | ✅ | The triggering FictionClockAdvance AggregateMutation event (or directly the parent turn — feature-decided). |

**Big-jump emission ordering** (per [EVT-Q4](99_open_questions.md#evt-q4--calibrationevent-producer-ordering) default): immediate follow-ups in fiction-chronological order within the same writer's epoch. SPIKE_01 turn 16 example: `/travel 23 days` → 23× `DayPasses` + 1× `MonthPasses`, all emitted before next channel event.

---

## EVT-T8 AdminAction

**Sub-shapes:** `Pause` · `Resume` · `ForceEndScene` · `WorldRuleOverride` (4 V1 sub-shapes; new admin commands add via I14 additivity + ADMIN_ACTION_POLICY §R4 registration).

**Payload max size:** 4 KB committed (admin reasons may be long per S5).

**Causal-ref policy:** optional. Used when admin action targets a specific event (e.g., force-revert turn N — V2+).

### Common payload

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `admin_command_id` | UUID | ✅ | S5-dispatched command's unique ID. |
| `actor_account` | String (admin user account) | ✅ | Per S5 actor authentication. |
| `impact_class` | `Tier1Destructive` \| `Tier2Griefing` \| `Tier3Informational` | ✅ | Per S5. |
| `reason` | String (min length per impact class — Tier1=100 chars, Tier2=50 chars, Tier3=any) | ✅ | Audit-grade. |
| `dual_actor_account` | Option\<String\> | required for Tier 1 | S5 dual-actor confirmation. |
| `target_id` | TargetId (channel \| reality \| quest \| etc.) | ✅ | What the action affects. |
| `cooldown_locked_until_wall_clock` | Option\<timestamp\> | optional | If S5 cooldown applies to actor. |

### Sub-shape payloads (delta from common)

| Sub-shape | Specific fields |
|---|---|
| `Pause` | `paused_until: Option<wall_clock>` |
| `Resume` | (no extra fields) |
| `ForceEndScene` | `end_reason: ForceEndReason` (admin enum) |
| `WorldRuleOverride` | `rule_id`, `override_value`, `expires_at_wall_clock` |

---

## EVT-T9 QuestBeat (V1+)

**Sub-shapes:** `Trigger` · `Advance` · `Outcome` (3 V1 sub-shapes).

**Payload max size:** 3 KB committed.

**Causal-ref policy:** `Trigger` optional (refs calibration/turn that triggered); `Advance` required (refs prior beat); `Outcome` required (refs Trigger).

### Common payload

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `quest_id` | UUID | ✅ | Stable per quest instance. |
| `beat_id` | String | ✅ | Quest-defined beat name (e.g., `"meet_npc_at_tavern"`, `"defeat_bandit"`). |
| `quest_definition_version` | String | ✅ | E.g., `"thien_long_quest_pack/v1.2"`. Audit/debug. |

### Sub-shape payloads

| Sub-shape | Specific fields |
|---|---|
| `Trigger` | `trigger_kind: Calendar \| OnTurn \| OnEvent`, `predicate_satisfied: String` (debug aid) |
| `Advance` | `from_beat_id: String`, `to_beat_id: String`, `outcome_brief: String` (max 500 chars) |
| `Outcome` | `outcome_kind: Success \| Failure \| Abandoned`, `rewards: Vec<Reward>` (optional), `consequences: Vec<Consequence>` (optional) |

**V1 status:** placeholder. Quest engine implementation defers full sub-shape lock; this contract reserves the slot.

---

## EVT-T10 NPCRoutine (V1+30d)

**Sub-shapes:** mirrors NPCTurn — `Speak` · `Action` · `Narration`. **NO `MetaCommand`** — routines are state-flow, not LLM-driven commands. Differ from NPCTurn by producer (scheduler vs orchestrator) and absence of PC trigger.

**Payload max size:** 8 KB committed (smaller than NPCTurn since less LLM-context-heavy).

**Causal-ref policy:** optional. May reference CalibrationEvent (if scheduled by date) or WorldTick.

### Sub-shape payloads (delta from EVT-T2)

Same shape as EVT-T2 sub-shapes with `actor: ActorId::Npc` always set, but with envelope `producer_service = "world-rule-scheduler"` and additional payload field:

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `routine_schedule_id` | UUID | ✅ | The NPC routine declaration ID per scheduler config. |
| `fired_at_fiction_ts` | i64 millis | ✅ | The exact fiction-time the routine fired (used in idempotency key). |
| `pc_observed` | bool | ✅ | Whether any PC was in the cell at fire time. If false, narration is flavor per EVT-A8. |

**V1 status:** placeholder. No emission in V1.

---

## EVT-T11 WorldTick (V1+30d)

**Sub-shapes:** feature-defined per author-placed beat type. Common patterns: `MajorEvent` · `WeatherChange` · `FactionMovement` · custom-author-declared.

**Payload max size:** 8 KB committed.

**Causal-ref policy:** optional. May reference triggering QuestBeat::Outcome (per [EVT-T9 example](03_event_taxonomy.md#evt-t9--questbeat-v1)).

### Common payload

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `world_tick_id` | UUID | ✅ | Author-declared beat ID; stable across schedule mutations. |
| `tick_kind` | String | ✅ | Author-defined sub-type discriminator. |
| `tick_payload` | tick-specific | ✅ | Per author declaration. |
| `narrative_seed` | Option\<String\> (max 2 KB) | optional | Author-provided seed text for LLM downstream narration. |

### V1+30d sub-shape examples

| tick_kind | Common fields |
|---|---|
| `MajorEvent` | `event_id_in_book`, `scope_channel`, `narrative_seed` |
| `WeatherChange` | `new_weather`, `affected_region` |
| `FactionMovement` | `faction`, `action`, `affected_locations` |

**V1 status:** placeholder. No emission in V1.

---

## Schema versioning summary (per Phase 2 D7 — envelope-level)

Per [EVT-A1](02_invariants.md#evt-a1--closed-set-event-taxonomy) closed-set + I14 additive-first:

- **Envelope `event_schema_version`** increments on **breaking change to envelope** — adding a required field, changing a field's type, removing a field.
- **Sub-shape additions** (new sub-shape under existing category) are **payload-internal additive evolution**; envelope version stays the same.
- **Per-sub-shape additions** (new optional field on existing sub-shape) are **fully additive**; consumers ignore unknown fields per I14.
- **Adding a new EVT-T* category** = locked-decision in [`../decisions/locked_decisions.md`](../decisions/locked_decisions.md) + axiom-level update to EVT-A1 + envelope version bump.

Detailed migration protocol — including upcaster shape, dual-read window, schema-version-mismatch resolution — locks in Phase 4 [`11_schema_versioning.md`](11_schema_versioning.md) (resolves DP Q5 + EVT-Q9).

---

## Locked-decision summary

| EVT-T* | Sub-shapes (V1) | Payload max | Causal-ref required? | Special notes |
|---|---|---:|:---:|---|
| EVT-T1 PlayerTurn | Speak / Action / MetaCommand (5 kinds) / FastForward | 10 KB | optional | MV12-D8 split (structural canonical + flavor audit-only); MV12-D9 5 commands locked |
| EVT-T2 NPCTurn | Speak / Action / MetaCommand (Whisper/Look only) / Narration | 10 KB | ✅ required | Multi-NPC reaction allowed; same triggering event ref'd by N reactions |
| EVT-T3 AggregateMutation | per aggregate-type × delta-kind | 5 KB | optional (recommended) | Sub-discriminator is `aggregate_type`, not a sub-shape name |
| EVT-T4 SystemEvent | DP-locked closed set (8 sub-shapes) | 2 KB | DP-internal | TurnBoundary's `turn_data` IS the EVT-T1/T2/T10/T11 payload (wire format) |
| EVT-T5 BubbleUpEvent | feature-defined per aggregator | 5 KB | ✅ required | Aggregator state separately capped 1 MB per DP-Ch26 |
| EVT-T6 LLMProposal | PlayerTurnProposal / NPCTurnProposal | 12 KB on bus | optional | Pre-validation lifecycle; 60s bus retention default |
| EVT-T7 CalibrationEvent | DayPasses / MonthPasses / YearPasses | 1 KB | ✅ required | Big-jump emits in fiction-chronological order |
| EVT-T8 AdminAction | Pause / Resume / ForceEndScene / WorldRuleOverride | 4 KB | optional | Tier 1 dual-actor + reason length per S5 |
| EVT-T9 QuestBeat | Trigger / Advance / Outcome | 3 KB | sub-shape-specific | V1+ placeholder |
| EVT-T10 NPCRoutine | Speak / Action / Narration | 8 KB | optional | V1+30d placeholder |
| EVT-T11 WorldTick | feature-defined (MajorEvent / WeatherChange / FactionMovement / ...) | 8 KB | optional | V1+30d placeholder |

---

## Cross-references

- [EVT-A1 closed-set taxonomy](02_invariants.md#evt-a1--closed-set-event-taxonomy) — invariant this contract serves
- [EVT-A6 typed causal-refs](02_invariants.md#evt-a6--causal-references-are-typed-single-reality-gap-free) — `CausalRef` shape
- [EVT-A8 flavor narration is non-canonical](02_invariants.md#evt-a8--flavor-narration-is-not-events) — basis for FastForward split + Narration sub-shape semantics
- [`03_event_taxonomy.md`](03_event_taxonomy.md) — EVT-T1..T11 definitions
- [`04_producer_rules.md`](04_producer_rules.md) — EVT-P1..P11 producer authorization
- [`11_schema_versioning.md`](11_schema_versioning.md) — Phase 4 EVT-S* migration protocol (resolves DP Q5)
- [PL_001 §3.5 TurnEvent](../features/04_play_loop/PL_001_continuum.md) — PlayerTurn shape this contract formalizes
- [PL_002 Command Grammar](../features/04_play_loop/PL_002_command_grammar.md) — 5 V1 commands lock source
- [SPIKE_01](../features/_spikes/SPIKE_01_two_sessions_reality_time.md) — narrative validation
- [MV12-D5 calibration](../decisions/locked_decisions.md#L570) — EVT-T7 CalibrationEvent backing decision
- [MV12-D7 schema additions](../decisions/locked_decisions.md#L572) — fiction_ts_start + fiction_duration envelope fields
- [DP-A18 SystemEvent canonical](../06_data_plane/02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25) — EVT-T4 sub-shapes
- [DP-Ch43 redaction policy](../06_data_plane/19_privacy_redaction_policies.md) — EVT-T5 BubbleUpEvent redaction_applied field
- [05_llm_safety A5-D1](../05_llm_safety/01_intent_classifier.md) — `intent_class` enum source
