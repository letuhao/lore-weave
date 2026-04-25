# 04 — Producer Rules (EVT-P*)

> **Status:** LOCKED Phase 2a (2026-04-25). Per [EVT-A4](02_invariants.md#evt-a4--producer-category-binding), each EVT-T* category has authorized producers gated by capability JWT (DP-K9). This file specifies them.
> **Stable IDs:** EVT-P1..EVT-P11 (1-to-1 with EVT-T1..EVT-T11). Never renumber. Retired IDs use `_withdrawn` suffix.

---

## How to use this file

When designing a feature that emits events, look up the EVT-T* category in [`03_event_taxonomy.md`](03_event_taxonomy.md), then read the matching EVT-P* row here. For each event your feature emits:

1. **Confirm your service is the authorized producer.** If not, the design is wrong — escalate.
2. **Confirm the capability JWT claim** your service-account already carries (or request it from CP issuance).
3. **Compose idempotency key** per the rule (uniform `(producer_service, client_request_id, target_channel)` shape per Phase 2 D2 decision).
4. **Implement semantic rate-limit** per the rule (independent from DP transport rate-limit DP-R6).
5. **Reject upstream emission** from forbidden producers — surface as `DpError::CapabilityDenied` or `EventModelError::ForbiddenProducer`.

The capability JWT shape (per Phase 2 D1 decision):

```json
{
  "iss": "control-plane",
  "sub": "service:world-service",
  "reality_id": "1256_thien_long_v1",
  "exp": 1745627400,
  "produce": ["PlayerTurn", "NPCTurn", "AggregateMutation", "CalibrationEvent"],
  "can_advance_turn": ["cell"],
  "can_register_aggregator": [],
  "can_pause_channel": []
}
```

`produce: [...]` is a list claim (not per-category boolean). Multi-role services list multiple categories. Revocation = remove an entry + push a fresh JWT to the service. Standard DP-K9 capability rotation rules apply.

---

## EVT-P1 — PlayerTurn

**Allowed producer:** **`world-service`** (Rust). Consumes EVT-T6 LLMProposal from the proposal bus, runs EVT-V* validator pipeline, then commits PlayerTurn via `dp::advance_turn`.

**Originator (informational, NOT producer):** PC submits text → gateway → roleplay-service (Python) emits LLMProposal. Roleplay-service is the **originator** of the proposal but NOT the producer of the committed PlayerTurn.

**Capability JWT (world-service service-account):**
```json
"produce": ["PlayerTurn", "NPCTurn", "AggregateMutation", "CalibrationEvent"],
"can_advance_turn": ["cell"]
```

**Idempotency key:** `(producer_service="world-service", client_request_id=ProposalId, target_channel=cell_channel_id)`. ProposalId originates from roleplay-service's LLMProposal. World-service uses it to dedupe in case bus delivers duplicate proposals after retry.

**Additional uniqueness constraint at commit:** per session-writer R7, the underlying turn allocation is also keyed on `(reality_id, session_id, turn_seq)` — duplicate `turn_seq` for the same session is rejected by Postgres UNIQUE constraint on `event_log`.

**Semantic rate limit:**
- **5 turns/second per session** at world-service consume layer (after roleplay-service rate-limits LLM calls).
- **20 turns/second per reality** aggregate (handles ~100 active sessions × ~0.2/s typical = peak ~20).
- Excess → `EventModelError::SemanticRateLimited { retry_after }`. Never silently drop.

**Forbidden producers:**
- `roleplay-service` (Python) — can ONLY emit LLMProposal per [DP-A6](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) + [EVT-A7](02_invariants.md#evt-a7--llm-proposals-are-pre-validation-only-never-authoritative)
- PC sessions directly — must submit via gateway → bus chain
- `quest-service`, `world-rule-scheduler`, `admin-cli` — wrong category
- Any service without `produce: [PlayerTurn]` claim — JWT denial at SDK layer

**Why these constraints:** PlayerTurn is the gateway-validated PC action. Allowing roleplay-service direct commit would collapse A6 5-layer injection defense. Allowing PC sessions direct commit would bypass capability + intent classification + canon-drift validation.

---

## EVT-P2 — NPCTurn

**Allowed producer:** **`world-service`** (same Rust process as PlayerTurn). Consumes EVT-T6 LLMProposal where `proposal_kind = NPCTurnProposal`, runs validator pipeline, commits via `dp::advance_turn`.

**Originator:** world-service orchestrator decides which NPC reacts (per scene + opinion graph) → calls roleplay-service for LLM-generated dialogue → roleplay-service emits LLMProposal → world-service consumes its own proposal.

**Capability JWT:** same as PlayerTurn (`produce: [..., "NPCTurn", ...]`). World-service service-account covers both.

**Idempotency key:** `(producer_service="world-service", client_request_id=ProposalId, target_channel=cell_channel_id)`. Same shape as EVT-P1.

**Semantic rate limit:**
- **15 NPC turns/second per cell** (handles SPIKE_01 obs#6 multi-NPC reaction patterns where 3+ NPCs react to one PlayerTurn).
- **30 NPC turns/second per reality** aggregate.
- Excess → `EventModelError::SemanticRateLimited { retry_after }`.

**Forbidden producers:** same forbidden list as EVT-P1 minus world-service. Roleplay-service still cannot commit; it only proposes.

**Note on multi-NPC reactions (per SPIKE_01 obs#6):** when one PlayerTurn triggers multiple NPC reactions (e.g., 3 NPCs in a teahouse), world-service emits N NPCTurn events in deterministic ordering (per scene-NPC ordering rule, defined in PL_003 — feature-level, not EVT-P concern). Each NPCTurn carries causal-ref to the same triggering PlayerTurn.

---

## EVT-P3 — AggregateMutation

**Allowed producers:** **multiple feature services**, each restricted to aggregates THEY own:
- **`world-service`** — owns `fiction_clock`, `actor_binding`, `scene_state`, `participant_presence`, `npc_pc_relationship`
- **`quest-service`** (future V1+) — owns `quest_state`, `quest_progress`
- **`pc-service`** (future) — owns `pc_inventory`, `pc_stats`, `pc_currency`
- **`world-rule-scheduler`** (V1+30d) — owns `world_tick_schedule`

**Capability JWT (per service):**
```json
"produce": ["AggregateMutation"],
"write": [
  { "aggregate_type": "fiction_clock", "tier": "T2", "scope": "reality" },
  { "aggregate_type": "actor_binding", "tier": "T2", "scope": "reality" },
  ...
]
```

The `write: [...]` claim is the existing DP-K9 capability per aggregate-type/tier/scope (not Event-Model-introduced; DP enforces at SDK layer). EVT-P3 adds the `produce: [AggregateMutation]` outer gate.

**Idempotency key:** `(producer_service, client_request_id, target_aggregate_id)`. For RealityScoped aggregates, target uses `(reality_id, aggregate_id)`. For ChannelScoped, target uses `(reality_id, channel_id, aggregate_id)`.

**Semantic rate limit (per tier × per scope):**
- T1 (Volatile) — 1000/s per session (high churn allowed; presence updates).
- T2 (Durable-async) — 100/s per aggregate-id (typical state delta rate).
- T3 (Durable-sync) — 10/s per aggregate-id (canon-affecting writes are slow by design).
- Excess → `EventModelError::SemanticRateLimited`.

These are upper bounds; per-aggregate fine-tuning at design review for known-hot aggregates.

**Forbidden producers:**
- `roleplay-service` (Python) — DP-A6
- `admin-cli` — admin uses EVT-T8 AdminAction (which itself may *trigger* AggregateMutation as a follow-up, but the AdminAction is the user-visible producer)
- Any service writing an aggregate it doesn't own — DP-K9 capability denies

---

## EVT-P4 — SystemEvent

**Allowed producer:** **DP itself** (Data Plane internal emission).

**No service-level producer.** Capability JWT does not gate SystemEvent emission — DP is trusted by construction (per [EVT-A4 consequence note](02_invariants.md#evt-a4--producer-category-binding)).

**Capability JWT:** N/A. SystemEvents emit as part of DP operation transactional commits (e.g., `bind_session` emits `MemberJoined`, `channel_pause` emits `ChannelPaused`, `advance_turn` emits `TurnBoundary` carrying the PlayerTurn/NPCTurn/etc. payload).

**Idempotency key:** DP-internal — DP-Ch11 channel_event_id allocation handles uniqueness via the per-channel monotonic counter.

**Semantic rate limit:** N/A — bounded by DP operation rate limits (DP-R6 transport rate limit applies; no separate semantic limit needed because feature services do not produce SystemEvents).

**Forbidden producers:** **ALL feature services.** Reserved discriminators per DP-A18 / DP-Ch52: any feature attempt to commit a SystemEvent payload via `dp::t2_write` etc. is rejected by SDK type system at compile time. Runtime attempts (raw DB write) blocked by DP-R3 (no raw client imports).

**Note on TurnBoundary payload routing:** when world-service calls `dp::advance_turn(turn_data=PlayerTurn{...})`, DP commits a `TurnBoundary` SystemEvent whose payload IS the PlayerTurn. The producer rule for the *payload* is EVT-P1 PlayerTurn; the producer rule for the *wire-format SystemEvent* is EVT-P4 (DP). Both apply: world-service must have `produce: [PlayerTurn]` to call `advance_turn`; DP transparently emits TurnBoundary as the wire format.

---

## EVT-P5 — BubbleUpEvent

**Allowed producer:** registered `BubbleUpAggregator` instance, running on the **parent channel's writer node** per [DP-Ch26 runtime](../06_data_plane/16_bubble_up_aggregator.md#dp-ch26--aggregator-runtime-loop).

**Service that registers the aggregator:** typically the feature owner (e.g., gossip-service registers a `RumorBubble` aggregator at tavern level; reputation-service registers a `FactionReputationDrift` at country level). The registering service holds the JWT claim.

**Capability JWT (registering service):**
```json
"produce": ["BubbleUpEvent"],
"can_register_aggregator": ["tavern", "town", "country"]
```

`can_register_aggregator: [level_name]` is the existing DP-Ch25 claim. EVT-P5 adds the `produce: [BubbleUpEvent]` outer gate.

**Idempotency key:** `(aggregator_id, source_event_refs_hash)` where `source_event_refs_hash = blake3(sorted(causal_refs))`. Multi-source aggregations hash all source `(channel_id, channel_event_id)` tuples to ensure replay produces same emit decision.

**Semantic rate limit:**
- DP enforces structural limits per DP-Ch29: 1 emit/source-event/aggregator + 1MB state cap + 16-level cascade cap.
- EVT-P5 adds: **max 5 emits per parent channel per source-event-window** (semantic limit; aggregator code that exceeds this is a design smell).
- Aggregator's `EmitDecision::Throttle { until }` is the soft alternative.

**Forbidden producers:**
- Non-registered services — only the registered aggregator emits at its parent.
- LLM-driven services (no LLMProposal → BubbleUp path) — bubble-up is feature-deterministic per DP-Ch27.
- PC sessions, admin-cli — never.

**Note on cascading bubble-up:** an aggregator at level L+1 may emit an event that triggers another aggregator at level L+2 (DP-Ch29 cascade). Each cascade level is a separate EVT-P5 emission with its own idempotency key. Cap at 16 levels.

---

## EVT-P6 — LLMProposal

**Allowed producer:** **`roleplay-service`** (Python/FastAPI) and future LLM-driven services. **Never the committed-event services.**

**Capability JWT (roleplay-service service-account):**
```json
"produce": ["LLMProposal"]
```

**Critically:** roleplay-service JWT does NOT carry `produce: [PlayerTurn]`, `produce: [NPCTurn]`, `produce: [AggregateMutation]`, or `can_advance_turn: [...]`. Even compromised roleplay-service code cannot directly commit canonical events — only propose.

**Idempotency key:** `(producer_service="roleplay-service", proposal_id=UUIDv4, target_channel=cell_channel_id)`. Roleplay-service generates `proposal_id` per LLM-completion; world-service uses it to dedupe consume in case bus retries.

**Semantic rate limit:**
- **5 proposals/second per session** (higher than PlayerTurn rate because (a) proposals fail validation often → retry, (b) NPC reactions multiplex per SPIKE_01 obs#6).
- **20 proposals/second per reality** aggregate.
- Excess → bus backpressure (proposals queue with retention timeout 60s) → eventually `Expired` lifecycle terminal state per [EVT-T6](03_event_taxonomy.md#evt-t6--llmproposal).

**Forbidden producers:**
- `world-service` (Rust) — consumes/validates only, never produces proposals
- `admin-cli` — wrong category (admin uses AdminAction)
- `quest-service`, `pc-service`, `world-rule-scheduler` — wrong category
- PC sessions directly — must submit via gateway → roleplay-service chain

**Note on rejection lifecycle:** when a proposal is rejected by validator pipeline, world-service emits a separate audit event (NOT an EVT-T6 — it's an audit-log entry with reject reason). The original proposal is NOT promoted; the PC sees soft-fail UX per A5-D4 fallback ("Elena seems distracted").

---

## EVT-P7 — CalibrationEvent

**Allowed producer:** **`world-service`** (per Phase 0 B4 decision — derives from FictionClock advance).

**Capability JWT (world-service):** same as EVT-P1 — `produce: ["PlayerTurn", "NPCTurn", "AggregateMutation", "CalibrationEvent"]`. World-service service-account already covers Calibration.

**Idempotency key:** `(producer_service="world-service", reality_id, calibration_kind, fiction_ts_boundary)` where:
- `calibration_kind ∈ { day_passes, month_passes, year_passes }`
- `fiction_ts_boundary` is the exact crossed boundary (e.g., `1256-09-30 → 1256-10-01` for month boundary)

This composite ensures exactly-once even if FictionClock T2 write retries cause re-evaluation.

**Semantic rate limit:** N/A — derived from FictionClock advance. Worst case: a `/travel 1 year` PlayerTurn emits ~365 day_passes + 12 month_passes = ~377 calibrations. SDK batches via idempotent commit (the `t2_write` for each is idempotent on the composite key; bulk emit fits within one transaction window).

**Forbidden producers:**
- Any service other than world-service — only the writer of FictionClock can derive crossings
- `quest-service` (observes calibrations as input to QuestBeat triggers, never emits them)
- `world-rule-scheduler` (observes calibrations to fire WorldTick, never emits them)
- `admin-cli` — never

**Note on emission ordering:** when 23 day_passes + 1 month_passes fire in one FictionClock advance (SPIKE_01 turn 16), world-service emits them in **fiction-chronological order**. The exact transactional cluster pattern (atomic vs immediate-follow-up) is deferred to [EVT-Q4](99_open_questions.md#evt-q4--calibrationevent-producer-ordering) and Phase 4 [`08_scheduled_events.md`](08_scheduled_events.md). Default for design: immediate follow-ups in same channel writer's epoch.

---

## EVT-P8 — AdminAction

**Allowed producer:** **`admin-cli`** via S5 dispatch.

**Capability JWT (admin-cli service-account):**
```json
"produce": ["AdminAction"],
"can_pause_channel": ["*"],
"can_dissolve_channel": ["*"],
"can_override_world_rule": true
```

The admin-cli JWT carries **all** admin privileges; access control happens at S5 layer (actor authentication + impact-class gating + cooldowns + dual-actor for Tier 1).

**Idempotency key:** `(producer="admin-cli", admin_command_id, target_id)` where:
- `admin_command_id` = unique per S5-dispatched command (UUIDv4)
- `target_id` = `channel_id` for channel-scoped commands (pause, dissolve), `reality_id` for reality-scoped (force-archive), `quest_id` for quest-scoped, etc.

**Semantic rate limit:** N/A (admin actions are rare; S5 cooldowns enforce — Tier 1 has 24h cooldown per actor; Tier 2 has weekly review; Tier 3 standard auth).

**Forbidden producers:** **ALL non-admin-cli services.** S5 dispatch is the single chokepoint for admin commands per ADMIN_ACTION_POLICY §R4. Service-to-service calls cannot forge AdminAction.

**Note on side-effects:** AdminAction commits often trigger DP-emitted SystemEvent side-effects (e.g., `admin/pause-channel` emits an AdminAction event AND DP emits a ChannelPaused SystemEvent). The AdminAction is the operator-audit-grade record; the SystemEvent is the DP lifecycle record. Both committed; both reference each other via causal-refs.

---

## EVT-P9 — QuestBeat (V1+, gated on quest engine)

**Allowed producer:** **`quest-service`** (feature service, future V1+).

**Capability JWT (quest-service):**
```json
"produce": ["QuestBeat", "AggregateMutation"],
"write": [
  { "aggregate_type": "quest_state", "tier": "T2", "scope": "reality" },
  { "aggregate_type": "quest_progress", "tier": "T2", "scope": "reality" }
]
```

Quest-service produces both QuestBeat (this category) and AggregateMutation (state writes on quest aggregates).

**Idempotency key:** `(producer="quest-service", quest_id, beat_id)`. `quest_id + beat_id` form a stable composite; replay-safe.

**Semantic rate limit:** **1 beat/second per quest instance** (quests are slow by design — typical beat advance is on PC turn cadence). Aggregate per reality bounded by active quest count × beat rate.

**Forbidden producers:**
- Any non-quest-service — quest engine is the single source of truth for quest progression
- `world-service` (observes QuestBeat as causal-ref source for WorldTick triggers, never emits them directly)
- `admin-cli` — admin overrides quests via AdminAction with sub-shape `QuestForceComplete`, not QuestBeat directly

**V1 status:** **placeholder.** Quest engine not implemented in V1 minimum. Capability claim reserved; service unimplemented.

---

## EVT-P10 — NPCRoutine (V1+30d)

**Allowed producer:** **`world-rule-scheduler`** (future V1+30d feature service).

**Capability JWT:**
```json
"produce": ["NPCRoutine", "WorldTick"],
"can_advance_turn": ["cell"]
```

Scheduler covers both NPCRoutine (this category) and WorldTick (EVT-P11). The `can_advance_turn: ["cell"]` claim is required because routines fire as TurnBoundary at cell channels per EVT-T10.

**Idempotency key:** `(producer="world-rule-scheduler", schedule_id, fired_at_fiction_ts)` per [EVT-Q8](99_open_questions.md#evt-q8--idempotency-key-composition-for-worldtick--npcroutine-across-big-jumps) default. `schedule_id` is the routine declaration ID (per NPC sheet); `fired_at_fiction_ts` is the exact fiction-time crossing.

**Semantic rate limit:**
- **1 routine/NPC/fiction-day** default (per NPC routine declaration).
- Per-NPC override allowed via NPC sheet field (e.g., a busy innkeeper might have 3 routines/day).
- **Aggregate per reality** bounded by NPC count × routine density.

**Forbidden producers:**
- `roleplay-service` (Python — DP-A6 violation)
- `world-service` orchestrator (only handles NPC-reacts-to-PC; routines are autonomous)
- Any service without `produce: [NPCRoutine]` claim

**V1 status:** **placeholder.** No NPCRoutine emission in V1 (V1 paused-when-solo per MV12-D4). V1+30d activation alongside scheduler service.

---

## EVT-P11 — WorldTick (V1+30d)

**Allowed producer:** **`world-rule-scheduler`** (same service as NPCRoutine).

**Capability JWT:** same as EVT-P10 plus `can_advance_turn: ["tavern", "town", "district", "country", "continent"]` — scheduler must be authorized to emit at non-cell levels for author-placed beats.

**Idempotency key:** `(producer="world-rule-scheduler", reality_id, world_tick_id)` per [EVT-Q8](99_open_questions.md#evt-q8--idempotency-key-composition-for-worldtick--npcroutine-across-big-jumps). `world_tick_id` is the author-declared beat ID (stable across schedule mutations because mutations create new world_tick_ids, not edit existing).

**Semantic rate limit:**
- Author-placed beats are sparse. **Default 10 fires/fiction-day per reality.**
- Big jumps may cross multiple thresholds in one FictionClock advance — each fires once via idempotency key.
- Excess → audit-log warning, not rejection (operator may have intentionally placed dense beats for a finale arc).

**Forbidden producers:**
- Any non-scheduler service
- `roleplay-service` — DP-A6
- `admin-cli` — admin uses AdminAction sub-shape `ForceWorldTick`, not WorldTick directly

**V1 status:** **placeholder.** No WorldTick emission in V1.

**Recovery on scheduler downtime (per [EVT-Q8](99_open_questions.md)):** if scheduler is down for 6 hours wall-clock and FictionClock advanced past pending thresholds during that window, missed WorldTicks fire on scheduler restart in fiction-chronological order. No skip-on-restart. Idempotency key prevents duplicate fires when scheduler boots and re-evaluates.

---

## Locked-decision summary

| ID | Category | Producer | JWT claim | Idempotency key |
|---|---|---|---|---|
| EVT-P1 | PlayerTurn | world-service | `produce: [PlayerTurn], can_advance_turn: [cell]` | `(world-service, ProposalId, cell_channel)` |
| EVT-P2 | NPCTurn | world-service | same as P1 | `(world-service, ProposalId, cell_channel)` |
| EVT-P3 | AggregateMutation | world-service / quest-service / pc-service / scheduler (per aggregate ownership) | `produce: [AggregateMutation], write: [...]` | `(producer, client_request_id, aggregate_id)` |
| EVT-P4 | SystemEvent | DP itself | N/A — DP-internal | DP-Ch11 channel_event_id |
| EVT-P5 | BubbleUpEvent | registered aggregator instance | `produce: [BubbleUpEvent], can_register_aggregator: [...]` | `(aggregator_id, source_event_refs_hash)` |
| EVT-P6 | LLMProposal | roleplay-service (Python) | `produce: [LLMProposal]` ONLY | `(roleplay-service, proposal_id, cell_channel)` |
| EVT-P7 | CalibrationEvent | world-service | same as P1 | `(world-service, reality_id, calibration_kind, fiction_ts_boundary)` |
| EVT-P8 | AdminAction | admin-cli | `produce: [AdminAction], can_*` | `(admin-cli, admin_command_id, target_id)` |
| EVT-P9 | QuestBeat (V1+) | quest-service | `produce: [QuestBeat, AggregateMutation]` | `(quest-service, quest_id, beat_id)` |
| EVT-P10 | NPCRoutine (V1+30d) | world-rule-scheduler | `produce: [NPCRoutine, WorldTick], can_advance_turn: [cell]` | `(scheduler, schedule_id, fired_at_fiction_ts)` |
| EVT-P11 | WorldTick (V1+30d) | world-rule-scheduler | same as P10 + `can_advance_turn: [tavern, town, ...]` | `(scheduler, reality_id, world_tick_id)` |

---

## Cross-references

- [EVT-A4 Producer-category binding](02_invariants.md#evt-a4--producer-category-binding) — invariant this file implements
- [EVT-A7 LLM proposals pre-validation](02_invariants.md#evt-a7--llm-proposals-are-pre-validation-only-never-authoritative) — explains roleplay-service / world-service split
- [`03_event_taxonomy.md`](03_event_taxonomy.md) — EVT-T1..T11 categories this file gates
- [`06_per_category_contracts.md`](06_per_category_contracts.md) — required/optional fields per category (Phase 2b)
- [DP-K9 Capability tokens](../06_data_plane/04d_capability_and_lifecycle.md#dp-k9--capability-tokens) — capability JWT shape
- [DP-A6 Python event-only](../06_data_plane/02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state) — direction this file makes concrete
- [02_storage R7 single-writer](../02_storage/R07_concurrency_cross_session.md) — additional commit-time uniqueness (turn_seq)
- [05_llm_safety/](../05_llm_safety/) — A3/A5/A6 internals slot into validator pipeline (Phase 3)
- [ADMIN_ACTION_POLICY](../../02_governance/ADMIN_ACTION_POLICY.md) §R4 — S5 admin command registry
