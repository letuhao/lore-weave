# TVL_001 — Travel Mechanics

> **Conversational name:** "Travel" (TVL). V1+ primary consumer of GEO_004 ROUTE_001 V1+30d Route graph. Implements inter-settlement travel via atomic single-segment route traversal — actor at from_cell issues `Travel:Initiate { route_id }`; system advances TDIL clocks (actor + body + realm; soul preserved unless BodyOrSoul::Soul form) over `route.default_fiction_duration` × per-turn scheduler ticks; actor arrives at to_cell when journey reaches 100%. Composes with SET_001 Settlement.role for hospitality availability at arrival (Hamlet has no inn → forced outdoor camp narration); RES_001 food/water consumption per league traveled; PL_006 status-effect application (Exhausted on overnight travel without inn); AIT_001 Tracked tier discipline (Untracked NPCs excluded — no travel state). Narrative-only V1+30d (LLM generates journey description via S9 prompt-assembly with route + biome + culture context already populated by V1+30d activation triangle); mechanical encounter generation deferred V1+30d+. PC + Tracked NPC parity V1+30d.
>
> **Category:** TVL — Travel Mechanics (V1+ foundation-adjacent consumer feature; first feature consuming V1+30d activation triangle POL + SET + ROUTE; unblocked by ROUTE_001 V1+30d shipping)
> **Status:** **DRAFT 2026-05-14** (Phase 0 TVL-D1..D7 LOCKED with user `continue` directive interpreted as approve all defaults)
> **Catalog refs:** [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — owns `TVL-*` stable-ID namespace (`TVL-A*` axioms · `TVL-D*` deferrals · `TVL-Q*` open questions · `AC-TVL-*` acceptance)
> **Builds on:** [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) (primary substrate — Route graph + RouteKind 5-variant + route.distance_units + route.default_fiction_duration + route.is_bidirectional) · [`GEO_003 SET_001`](../00_geography/GEO_003_settlement_generator.md) (Settlement.role for hospitality availability — Hamlet/Village/Town/City/Capital/Fortress) · [`GEO_002 POL_001`](../00_geography/GEO_002_political_layer.md) (Province + State + culture_tag for journey-narrative context) · [`GEO_001`](../00_geography/GEO_001_world_geometry.md) (biome + climate for narrative grounding) · [`TDIL_001`](../03_actor_substrate/TDIL_001_time_dilation_foundation.md) (4-clock model — actor_clock + body_clock + realm_clock advance; soul_clock preserved unless BodyOrSoul::Soul form per TDIL-A2) · [`RES_001`](../00_resource/RES_001_resource_foundation.md) (food + water consumable cost per league traveled; vital_pool Hunger/Thirst advancement) · [`PL_006`](../04_play_loop/PL_006_status_effects.md) (Exhausted status applied on overnight no-inn travel; Wounded status if forced-rest combat) · [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) (Tracked tier discipline — PCs + Major NPCs participate; Untracked NPCs excluded — no travel state) · [`EF_001`](../03_actor_substrate/EF_001_entity_foundation.md) (actor.current_cell_id read at travel-initiate; updated at travel-arrive)
> **Resolves:** Inter-settlement movement V1+ blocker (ROUTE_001 V1+30d ships Route graph; without consumer there's no way to TRAVERSE the graph) · Journey-narrative grounding gap (LLM has biome + climate + culture + settlement context from V1+30d activation triangle but no "actor is moving through this terrain" mechanic to anchor narration to) · Cross-settlement encounter substrate prerequisite (V1+30d+ encounter generator needs travel-in-progress state to attach encounter events to — TVL_001 V1+30d provides the state aggregate; encounters layer on top later) · Per-actor location-update mechanism beyond cell-channel binding (entity.current_cell_id was V1 single-cell-channel-bound via EF_001; multi-settlement travel needs an in-flight intermediate state TVL_001 V1+30d introduces)
> **Defers to:** future **encounter-generator V1+30d+** (mechanical encounters during travel — encounter table per biome × route.kind; combat/parley/discovery events; deferred until encounter substrate designed) · future **mount/vehicle travel V1+30d+** (OnHorseback / ByBoat / ByShip modes; requires RES_001 V2+ mount-as-resource OR new mount aggregate) · future **composite multi-segment travel V1+30d+** (player declares destination via Dijkstra; system auto-traverses N Routes; convenience command layered on atomic V1+30d) · future **off-camera background NPC migration V2+** (Untracked NPCs migrating between cells without explicit Travel:Initiate; quantum-observation pattern via AIT_001 V2+) · future **group/party travel V1+30d+** (multiple actors traversing same Route together; party-formation aggregate; UX for shared travel state) · future **weather/season travel modifiers V2+** (climate × route.kind weather effects on default_fiction_duration; storm-bound delays; seasonal river-impassability) · future **soul-projection travel V2+** (BodyOrSoul::Soul form astral travel; instant or accelerated movement; per wuxia/cultivation archetype canon)

---

## §1 Why this exists

Three concrete gaps that TVL_001 closes.

**Gap 1 — ROUTE_001 V1+30d Route graph has no consumer.** GEO_004 ROUTE_001 V1+30d ships a deterministic, well-structured Route graph (Road / Trail / SeaLane / RiverNavigation / MountainPass routes between settlement cells with `distance_units + default_fiction_duration` pre-computed). But V1+30d-ship of ROUTE_001 alone produces a STATIC graph that no actor can traverse — there's no "actor moves from cell A to cell B along Route X" mechanic. Without TVL_001, the Route graph is dead data. TVL_001 V1+30d activates inter-settlement movement: actor issues `Travel:Initiate { route_id }`; system tracks progress per-turn; arrival updates `entity.current_cell_id` per EF_001. This is the primary V1+ blocker ROUTE_001's §10 named.

**Gap 2 — Journey-narrative grounding has no anchor mechanic.** LLM prompt-assembly per S9 generates rich `[GEOGRAPHIC_CONTEXT]` (biome + climate + culture_tag + province + state + nearest_settlement + nearest_route) once V1+30d activation triangle ships, but the grounding is STATIC ("Lý Minh is in cell yen_vu_lau, Town role, Han-Jiangnan culture, Tống state, Subtropical Plain biome"). There's no "Lý Minh is currently traveling along the Imperial Highway from Khai Phong toward Tương Dương, 60% of the way, has been walking 14 hours" narrative state for the LLM to ground on during multi-turn journey arcs. TVL_001 V1+30d provides `actor_travel_state` aggregate with route_id + progress_fraction + elapsed_duration + remaining_duration; S9 prompt-assembly extends `[GEOGRAPHIC_CONTEXT]` with `[TRAVEL_CONTEXT]` sub-section when actor has in-flight journey.

**Gap 3 — Cross-settlement encounter substrate is V1+30d+ blocked without travel-state aggregate.** The intended V1+30d+ design surface includes random encounter generation during travel (bandit ambush on a remote Trail, weather event on MountainPass, trade caravan meeting on Road). These encounters need an ANCHOR — what is the actor's location DURING travel? V1 model has actors bound to single cells via EF_001 `entity.current_cell_id`. Mid-travel actors are conceptually "on the route" — not in cell A, not in cell B, but somewhere between. TVL_001 V1+30d introduces `actor_travel_state` as that anchor (progress_fraction over a Route). V1+30d+ encounter generators attach encounter events to this state. Without TVL_001 V1+30d, V1+30d+ encounter design has no place to land.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Journey** | `actor_travel_state` aggregate (T2/Reality, sparse per-(actor_id, journey_id)) — NEW V1+30d | One row per active actor-journey. Sparse: only Tracked-tier (PC + Major NPC) actors have rows; Untracked NPCs excluded per AIT-A8 quantum-observation discipline. Closed when journey reaches 100% progress (arrival) or canceled. |
| **JourneyId** | `pub struct JourneyId(pub(crate) Ulid)` opaque newtype | Module-private constructor; allocated at Travel:Initiate via blake3-derive from `(actor_id, route_id, fiction_clock_at_initiate)` for replay-determinism. |
| **TravelMode** | Closed enum 2 V1+30d variants — OnFoot / ByBoat (V1+30d+ activation) | Per TVL-D7 V1+30d ships OnFoot ONLY. OnFoot uses route.default_fiction_duration (already baselined at "1 league/hour OnFoot" per ROUTE_001 §5.2). ByBoat V1+30d+ when mount/vehicle substrate ships; SeaLane + RiverNavigation routes accept ByBoat only. MountainPass routes accept OnFoot only V1+30d (climbing baseline 0.3 league/hour). |
| **TravelInitiator** | Closed enum 2 V1+30d variants — Pc / TrackedNpc | Untracked NPCs excluded per TVL-D7 default + AIT_001 Tracked tier discipline. Travel:Initiate from Untracked actor → reject `travel.actor_untracked_excluded`. |
| **ProgressFraction** | `f32` in `[0.0, 1.0]` — fraction of route.default_fiction_duration elapsed | Advanced per-turn by EVT-T5 Scheduled:TravelTick (or wall-clock equivalent post-PL_001 turn-boundary). 0.0 = at from_cell (just initiated); 1.0 = at to_cell (arrived). Intermediate values = on-route mid-journey. |
| **TravelCost** | Per-league food + water consumption from RES_001 `resource_inventory` Consumable category (HIGH-4 fix /review-impl 2026-05-15 — Consumable possession deduction, NOT vital_pool body-state advancement) | V1+30d: `food_per_league × distance_units` Food UNITS deducted from `actor.resource_inventory.food` (Consumable possession counter — HIGH = lots of supplies, LOW = depleted) + `water_per_league × distance_units` Water UNITS deducted from `actor.resource_inventory.water`. Deducted at Travel:Initiate (pre-pay model — actor must have sufficient food/water possessions at start; insufficient → reject `travel.insufficient_provisions`). Defaults: food=1.0 units/league + water=2.0 units/league per OnFoot (tunable per `creative_seed.travel_cost_per_league` V1+30d additive). **NOTE**: `vital_pool.hunger / thirst` (Vital category body-state counters — HIGH = hungry/thirsty body state) advance via standard RES_001 per-day-boundary semantics INDEPENDENTLY of travel; TVL does NOT touch vital_pool directly. The actor's body becomes hungry/thirsty per RES per-day baseline; the Food/Water consumables in resource_inventory get burned through during travel; eating Food at next meal (via RES_001 standard consumption flow) decreases vital_pool.hunger. |
| **HospitalityAvailability** | Per-arrival-cell hospitality check via Settlement.role | If to_cell hosts a Settlement with role ∈ {Village, Town, City, Capital, Fortress}: arrival narration includes "find an inn / rest at the {role}"; no status effect. If to_cell hosts Hamlet OR no settlement (e.g., MountainPass endpoint mid-wilderness): arrival narration includes "make camp outdoors"; if cumulative wakeful_duration_at_arrival > 16 hours, apply PL_006 Exhausted status per StatusFlag::Exhausted V1 active. |
| **TDIL clock advancement** | Selective per TDIL-A2 BodyOrSoul distinction (TVL-D4); TVL-OWNED clocks: actor_clock + body_clock ONLY (HIGH-3 fix /review-impl 2026-05-15) | At Travel:Initiate AND per Scheduled:TravelTick: **actor_clock + body_clock** advance by tick_duration × time_flow_rate. `realm_clock` is **PL_001 turn-boundary-owned, NOT TVL-owned** — realm_clock is channel-tier resource per TDIL-A1 + PL_001 channel-time discipline; it advances per turn-boundary regardless of travel state to maintain channel-time consistency for ALL actors in the channel. soul_clock UNCHANGED unless actor is in BodyOrSoul::Soul form (xuyên không soul-projection per PCS_001 V1+ S8) — V1+30d simplification: BodyOrSoul::Soul actors cannot Travel:Initiate (reject `travel.soul_form_no_physical_travel`); soul-projection astral travel deferred V2+ per TVL-D7 future. |
| **One-journey-per-actor invariant** | `actor_travel_state` keyed on `(actor_id, journey_id)` but constraint enforced: ≤1 active journey per actor V1+30d | Travel:Initiate while actor already mid-journey → reject `travel.actor_already_traveling`. V1+30d+ parallel-body journeys (BodyOrSoul::Body active travel while soul does something else) deferred per TVL-Q4. |
| **Multi-segment journeys** | V1+30d atomic single-segment only per TVL-D6 | Player issues Travel:Initiate per Route. Arrives at to_cell. Issues NEXT Travel:Initiate manually. Composite multi-segment (auto-traverse Khai Phong → Yên Vũ Lâu → Tương Dương via Dijkstra-shortest-path) deferred V1+30d+ as TVL-D8. |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

TVL_001 introduces no new EVT-T* category. Maps onto existing mechanism-level taxonomy:

| TVL event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Actor initiates journey | **EVT-T1 Submitted** | `Travel:Initiate { actor_id, route_id, mode }` (NEW V1+30d sub-type) | PC actor via client-app player intent / Tracked NPC via LLM-driven intent in chat-service Chorus per NPC_002 | New EVT-T1 sub-type registered in `_boundaries/02_extension_contracts.md` §1 TurnEvent sub-types. PL_005 Interaction taxonomy doesn't cover Travel (it's not an interaction with another entity — it's locomotion); Travel gets its own EVT-T1 sub-type alongside Interaction kinds. |
| Travel state mutation (initiate / progress tick / arrive) | **EVT-T3 Derived** | `aggregate_type=actor_travel_state` (sparse per-(actor, journey)) | Aggregate-Owner role (travel-service / world-service combined per cross-service handoff §13) | Causal-ref to triggering EVT-T1 Travel:Initiate (initiate) OR EVT-T5 Scheduled:TravelTick (progress) OR computed arrival (when progress_fraction reaches 1.0). |
| Per-turn progress advancement | **EVT-T5 Scheduled** | `Scheduled:TravelTick { journey_id }` (NEW V1+30d sub-type per EVT-G2 trigger source kind c FictionTimeMarker) | EVT-G framework Generator at PL_001 turn-boundary (per-turn fire per TDIL closure-pass-extension elapsed-time semantic) | Per active journey: at each turn-boundary, advance progress_fraction by `tick_duration / route.default_fiction_duration × actor.time_flow_rate`. If progress_fraction reaches 1.0, emit terminal arrival event. |
| LLM-derived travel-narrative proposal | **EVT-T6 Proposal** | `Travel:JourneyNarration { journey_id, content }` (V1+30d active) | chat-service S9 LLM via prompt-assembly with [TRAVEL_CONTEXT] sub-section | V1+30d ACTIVE — LLM generates per-turn travel narration during journey (e.g., "Lý Minh walks through the early morning mist, the Imperial Highway stretching ahead..."); content stored as ephemeral narration linked to journey_id, NOT canonical event (per EVT-A10 — narration is decoration not state). |

**No new GeographyDeltaKind** — travel is per-actor state, not geographic substrate edit; doesn't touch world_geometry.

**Travel:Initiate is an EVT-T1 Submitted not EVT-T8 Admin** — per TVL-D2 + S5 ImpactClass: travel is regular gameplay action (PC + NPC players), not Forge admin canonization. No capability claim required beyond standard PC/NPC action authorization.

---

## §3 Aggregate inventory

One new aggregate owned by TVL_001:

### 3.1 `actor_travel_state` (T2/Reality, sparse per-(actor, journey)) — PRIMARY (NEW V1+30d)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_travel_state", tier = "T2", scope = "reality")]
pub struct ActorTravelState {
    pub journey_id: JourneyId,                              // primary key (sparse — only Tracked actors with active journeys have rows)
    pub actor_id: ActorId,                                  // FK into EF_001 entity registry (PC OR Tracked NPC); composite uniqueness invariant: ≤1 row per actor_id where status == Active
    pub route_id: RouteId,                                  // FK into world_geometry.routes (the Route being traversed)
    pub mode: TravelMode,                                   // OnFoot V1+30d; ByBoat V1+30d+ schema-reserved
    pub direction: TravelDirection,                         // Forward (from_cell → to_cell) OR Backward (to_cell → from_cell); requires route.is_bidirectional == true for Backward
    pub status: TravelStatus,                               // Active | Arrived | Canceled
    pub progress_fraction: f32,                             // [0.0, 1.0] — advanced per Scheduled:TravelTick
    pub initiated_at_fiction_time: FictionTime,             // actor_clock at Travel:Initiate (replay-deterministic)
    pub expected_arrival_fiction_time: FictionTime,         // initiated_at_fiction_time + route.default_fiction_duration × actor.time_flow_rate
    pub elapsed_duration: FictionDuration,                  // cumulative tick advancement; equals route.default_fiction_duration at arrival
    pub provisions_consumed: ProvisionsConsumed,            // food_units + water_units deducted at Travel:Initiate; stored for audit/refund-on-cancel
    pub initiator: TravelInitiator,                         // Pc | TrackedNpc; per TVL-D7 PC + Tracked NPC parity
    pub last_tick_event_id: Option<EventId>,                // most-recent EVT-T5 Scheduled:TravelTick that advanced this journey (replay-debug aid)
}

pub struct ProvisionsConsumed {
    pub food_units: f32,                                    // deducted at Travel:Initiate via RES_001 vital_pool Hunger advancement
    pub water_units: f32,                                   // deducted at Travel:Initiate via RES_001 vital_pool Thirst advancement
}

pub enum TravelDirection {                                  // closed enum 2 V1+30d
    Forward,                                                // from_cell → to_cell (route.is_bidirectional any)
    Backward,                                               // to_cell → from_cell (requires route.is_bidirectional == true V1+30d; V1+30d+ one-way routes per ROUTE-D3 reject Backward)
}

pub enum TravelStatus {                                     // closed enum 3 V1+30d
    Active,                                                 // journey in progress; per-turn ticks advance progress_fraction
    Arrived,                                                // journey reached 100%; actor.current_cell_id updated; row retained for audit until reality-cleanup or per-row retention policy
    Canceled,                                               // admin Forge:CancelJourney OR actor self-cancel (V1+30d+ self-cancel deferred per TVL-D9); provisions partial-refund per refund policy (TVL-Q3)
}
```

**Rules:**

- One row per `(actor_id, status=Active)` tuple — ≤1 Active journey per actor V1+30d. Violation → `travel.actor_already_traveling`.
- `route_id` MUST exist in `world_geometry.routes` AND `world_geometry.schema_version` ≥ 3 (post-ROUTE_001 ship — routes activated). Pre-ROUTE-ship realities can't initiate travel; reject `travel.route_layer_not_activated`.
- `mode == OnFoot` V1+30d; ByBoat schema-reserved V1+30d+. Travel:Initiate with mode=ByBoat → reject `travel.mode_unavailable_v1plus30d`.
- `direction == Backward` REQUIRES `route.is_bidirectional == true` per V1+30d default; routes V1+30d are all bidirectional per ROUTE_001 ROUTE-D3, so this rarely fires; defensive for V1+30d+ one-way activation.
- `initiator == Pc OR TrackedNpc`; Untracked actor Travel:Initiate → reject `travel.actor_untracked_excluded` (cross-validator with AIT_001).
- `actor.bodyorsoul_form != BodyOrSoul::Soul` at Travel:Initiate (per TVL-D4 simplification — soul-projection travel V2+). Soul-form actor Travel:Initiate → reject `travel.soul_form_no_physical_travel`.
- Provisions (HIGH-4 fix /review-impl 2026-05-15): actor MUST have ≥ `food_per_league × route.distance_units` Food units in **`actor.resource_inventory.food`** (Consumable possession counter) AND ≥ `water_per_league × route.distance_units` Water units in **`actor.resource_inventory.water`** at Travel:Initiate; insufficient → reject `travel.insufficient_provisions`. NOT a vital_pool check — vital_pool tracks body-state (Hunger/Thirst counters), not possessions.
- Route-mode compatibility: OnFoot mode cannot traverse SeaLane routes (reject `travel.mode_route_incompatible`); SeaLane requires ByBoat V1+30d+. MountainPass + RiverNavigation accept OnFoot V1+30d (climbing + walking-along-bank respectively).
- progress_fraction monotonic non-decreasing while Active (only Scheduled:TravelTick advances; admin Forge:RevertJourneyProgress deferred V2+ per TVL-D10).
- `expected_arrival_fiction_time` set at Travel:Initiate; recomputed if actor's `time_flow_rate` changes mid-journey (TVL-Q5 V1+30d+ resolution — V1+30d treats time_flow_rate as constant per actor for journey duration).

---

## §4 Closed enums (TVL_001 V1+30d)

### 4.1 TravelMode (2 V1+30d; OnFoot active, ByBoat schema-reserved V1+30d+)

```rust
pub enum TravelMode {                                       // closed; per-journey
    OnFoot,                                                 // V1+30d ACTIVE — uses route.default_fiction_duration as-is (Road=1 league/hour / Trail=0.6 / RiverNavigation=walking-along-bank-baseline / MountainPass=0.3)
    ByBoat,                                                 // V1+30d+ SCHEMA-RESERVED — for SeaLane + RiverNavigation when mount/vehicle substrate ships (RES_001 V2+ boat-as-resource OR new mount aggregate); duration = route.default_fiction_duration × boat-speed-modifier; route-mode-compatibility check: ByBoat requires route.kind ∈ {SeaLane, RiverNavigation}
}
```

Per TVL-D7 V1+30d ships OnFoot ONLY; ByBoat reject `travel.mode_unavailable_v1plus30d`.

### 4.2 TravelInitiator (2 V1+30d; closed)

```rust
pub enum TravelInitiator {                                  // closed; per-journey provenance tag
    Pc,                                                     // player-initiated via client-app travel command
    TrackedNpc,                                             // LLM-driven Tracked NPC travel via chat-service Chorus per NPC_002; AIT_001 Tracked tier discipline
}
```

Per TVL-D7 PC + Tracked NPC parity. Untracked NPCs excluded per AIT-A8 quantum-observation pattern (no aggregate; no Travel:Initiate emission).

### 4.3 TravelDirection (2 V1+30d; closed)

```rust
pub enum TravelDirection {                                  // closed; per-journey
    Forward,                                                // from_cell → to_cell (route.is_bidirectional any)
    Backward,                                               // to_cell → from_cell (requires route.is_bidirectional == true)
}
```

### 4.4 TravelStatus (3 V1+30d; closed)

```rust
pub enum TravelStatus {                                     // closed; per-journey lifecycle
    Active,                                                 // journey in progress
    Arrived,                                                // 100% complete; actor.current_cell_id updated
    Canceled,                                               // admin Forge:CancelJourney OR actor self-cancel V1+30d+ deferred TVL-D9
}
```

---

## §5 Per-turn progress tick mechanism

### 5.1 Travel:Initiate event flow

```
Actor (PC OR Tracked NPC) issues Travel:Initiate { route_id, mode=OnFoot, direction=Forward }:
  ↓ EVT-T1 Submitted validator pipeline:
    AuthorizationGate: actor exists in EF_001 + actor.tracking_tier ≥ Tracked (TVL-V4) → pass.
    SchemaGate: route_id ∈ wg.routes (TVL-V1) + mode == OnFoot V1+30d (TVL-V5) + direction valid for route.is_bidirectional (TVL-V3) → pass.
    ReferentialIntegrityGate:
      - actor.current_cell_id == route.from_cell (Forward) OR == route.to_cell (Backward) — actor must be physically at journey start cell (TVL-V2)
      - actor has no Active actor_travel_state row (TVL-V6 one-journey-per-actor)
      - actor.bodyorsoul_form != BodyOrSoul::Soul (TVL-V7 soul-form-no-physical-travel)
      - actor.resource_inventory.food ≥ food_cost AND actor.resource_inventory.water ≥ water_cost (TVL-V8 sufficient-provisions; HIGH-4 fix /review-impl 2026-05-15 — Consumable inventory check, NOT vital_pool)
      - route.kind compatible with mode (TVL-V9 mode-route-compatibility)
      - world_geometry.schema_version ≥ 3 (TVL-V10 route-layer-activated; post-ROUTE_001 ship)
      → all pass.
    OrderingGate + ContentSafetyGate → pass.
  ↓ EVT-T3 Derived emitted: actor_travel_state row created with status=Active, progress_fraction=0.0,
    initiated_at_fiction_time=actor.actor_clock, expected_arrival_fiction_time computed.
  ↓ EVT-T3 Derived cascade: RES_001 vital_pool deductions (hunger += food_cost; thirst += water_cost).
  ↓ EVT-T3 Derived cascade: EF_001 actor.current_cell_id LATCHED (not changed yet; latched as "in-transit" via NEW
    entity.travel_journey_id: Option<JourneyId> additive field on EF_001 entity_binding — bumps EF_001
    aggregate schema_version per I14; cross-feature dependency tracked TVL-Q1).
```

### 5.2 Per-turn tick advancement

```
At each PL_001 turn-boundary (channel-bound per TDIL-A3 per-turn O(1) Generator semantic):
  ↓ EVT-G2 Generator with trigger=FictionTimeMarker fires Scheduled:TravelTick { journey_id } for each
    active actor_travel_state in channel:
    advance: progress_fraction += (tick_duration / route.default_fiction_duration) × actor.time_flow_rate
    advance: elapsed_duration += tick_duration × actor.time_flow_rate
    advance TDIL clocks (TVL-D4 selective; HIGH-3 fix /review-impl 2026-05-15 — TVL advances ONLY actor_clock + body_clock):
      actor.actor_clock += tick_duration × actor.time_flow_rate
      actor.body_clock += tick_duration × actor.time_flow_rate
      **NOTE**: channel.realm_clock is advanced INDEPENDENTLY by PL_001 turn-boundary semantic (channel-tier resource per TDIL-A1; advances regardless of travel state to maintain channel-time consistency). TVL does NOT touch realm_clock to avoid double-advancement (HIGH-3 fix — earlier §2 wording incorrectly listed realm_clock as TVL-advanced; clarified to PL_001-owned).
      actor.soul_clock UNCHANGED (preserved unless actor.bodyorsoul_form == BodyOrSoul::Soul, in which case
        Travel:Initiate was rejected — so during Active journey, actor is always BodyOrSoul::Body)
    ↓ if progress_fraction >= 1.0: clamp to 1.0; transition status Active → Arrived; emit Travel:Arrive cascade.
```

### 5.3 Travel:Arrive cascade

```
When status transitions Active → Arrived (progress_fraction reaches 1.0):
  ↓ EVT-T3 Derived: actor_travel_state.status = Arrived; row retained for audit.
  ↓ EVT-T3 Derived cascade: EF_001 actor.current_cell_id = route.to_cell (Forward) OR route.from_cell
    (Backward); entity.travel_journey_id reverted to None.
  ↓ Hospitality check at arrival cell (HIGH-1 + HIGH-2 fixes /review-impl 2026-05-15):
    settlement = wg.settlements.find(s | s.cell_id == arrival_cell_id);
    if settlement.role ∈ {Village, Town, City, Capital}: narration tag "inn-available"; no status effect.
      (HIGH-1 fix — Fortress REMOVED from inn-available set; Fortress = military barracks per ROUTE_001 §2 SettlementRole semantic; no public inn for civilian travelers).
    if settlement == None OR settlement.role ∈ {Hamlet, Fortress}:
      check actor.wakeful_duration (TDIL_001 tracked field; accumulated since last sleep):
      if wakeful_duration_at_arrival > 16h fiction-time AND ≤ 24h: apply PL_006 status `StatusFlag::Exhausted`
        via OutputDecl on actor with **magnitude=3** (HIGH-2 fix — replaces "Tier 0" with PL_006 actual magnitude semantic; PL_006 magnitude 1..=10 range);
      if wakeful_duration_at_arrival > 24h: apply PL_006 status `StatusFlag::Exhausted` with **magnitude=5** (HIGH-2 fix — replaces "Tier 1"; higher magnitude reflects severe exhaustion);
      cascade to PL_006 apply_set_status per PL_006 StackPolicy (V1+30d StackPolicy::Replace for Exhausted — newer magnitude overrides older).
      narration tag "outdoor-camp" / "no-inn-available".
  ↓ EVT-T6 Proposal: chat-service LLM generates Travel:JourneyNarration { journey_id, arrival_narration } —
    final journey description with arrival context (settlement.role + biome + culture_tag + nearest_route);
    persisted as ephemeral content linked to journey_id (NOT canonical event per EVT-A10).
```

---

## §6 Multiverse inheritance

TVL_001 V1+30d inherits standard DP-Ch + EVT-T2 snapshot-fork contract:

- At snapshot fork: parent's active actor_travel_state rows copied bit-exactly into child (each row's journey_id preserved; progress_fraction frozen at fork-point).
- Child's per-turn ticks advance child rows independently from parent's; parent's continued ticks don't cascade.
- L1/L2 cascade: no L2 layer for travel state (it's reality-local per-actor runtime state; no canonical-author declaration).
- Determinism preserved: same `(actor_seed, route.id, fiction_clock_at_initiate, time_flow_rate at each tick)` → bit-identical progress_fraction sequence.

V1+30d edge case: if a route was REMOVED via RemoveRoute V1 GEO_001 AFTER an actor initiated travel on it (admin emits RemoveRoute while journey Active) — reject the RemoveRoute via NEW cross-feature validator `route_in_use_by_journey` (ROUTE_001 V1+30d+ extension; TVL-Q2 V1+30d resolution: ADD this validator to ROUTE_001 RemoveRoute pipeline as TVL_001 V1+30d cross-feature dependency). V1+30d: ROUTE_001 RemoveRoute checks actor_travel_state for any Active journey on this route_id; if found, reject `route.remove_blocked_by_active_journey`.

---

## §7 Validation pipeline (TVL_001 V1+30d additive validators)

| Validator | Stage | Reject rule_id |
|---|---|---|
| **TVL-V1** route-exists | Travel:Initiate ReferentialIntegrityGate | `travel.route_unknown` (route_id ∉ wg.routes) |
| **TVL-V2** actor-at-journey-start | Travel:Initiate ReferentialIntegrityGate | `travel.actor_not_at_journey_start` (actor.current_cell_id != route's from-cell for direction) |
| **TVL-V3** direction-bidirectional | Travel:Initiate SchemaGate | `travel.backward_one_way_route` (direction == Backward but route.is_bidirectional == false; defensive for V1+30d+ one-way routes per ROUTE-D3) |
| **TVL-V4** actor-tracked | Travel:Initiate AuthorizationGate | `travel.actor_untracked_excluded` (actor.tracking_tier ∉ {Pc, TrackedMajor} per AIT_001 discipline) |
| **TVL-V5** mode-available-v1plus30d | Travel:Initiate SchemaGate | `travel.mode_unavailable_v1plus30d` (mode != OnFoot V1+30d) |
| **TVL-V6** one-journey-per-actor | Travel:Initiate ReferentialIntegrityGate | `travel.actor_already_traveling` (existing actor_travel_state row with status=Active for same actor) |
| **TVL-V7** soul-form-physical-travel | Travel:Initiate ReferentialIntegrityGate | `travel.soul_form_no_physical_travel` (actor.bodyorsoul_form == BodyOrSoul::Soul; soul-projection astral travel V2+ deferred TVL-D7) |
| **TVL-V8** sufficient-provisions | Travel:Initiate ReferentialIntegrityGate | `travel.insufficient_provisions` (actor.resource_inventory.food < food_cost OR actor.resource_inventory.water < water_cost; HIGH-4 fix /review-impl 2026-05-15 — Consumable inventory check, NOT vital_pool body-state) |
| **TVL-V9** mode-route-compatibility | Travel:Initiate SchemaGate | `travel.mode_route_incompatible` (mode=OnFoot on SeaLane V1+30d) |
| **TVL-V10** route-layer-activated | Travel:Initiate at RealityBootstrapper post-check | `travel.route_layer_not_activated` (world_geometry.schema_version < 3; pre-ROUTE_001 ship reality cannot initiate travel) |
| **TVL-V11** journey-id-replay-determinism | EVT-T1 emitter (defensive) | `travel.journey_id_collision` (blake3-derive collision — astronomically improbable but defensive; reject duplicate JourneyId) |
| **TVL-V12** progress-monotonic | EVT-T5 Scheduled:TravelTick apply | `travel.progress_non_monotonic` (Scheduled:TravelTick attempting to DECREASE progress_fraction; defensive against malformed tick events) |
| **TVL-V13** arrival-cell-resolved | Travel:Arrive cascade | `travel.arrival_cell_unknown` (route.to_cell (Forward) OR route.from_cell (Backward) doesn't resolve in wg.cells — should be impossible per ROUTE-V2; defensive) |
| **TVL-V14** route-in-use-by-journey | ROUTE_001 RemoveRoute delta cross-feature gate (TVL_001-extended) | `route.remove_blocked_by_active_journey` (any actor_travel_state with status=Active and route_id matches the route being removed; mirrors POL_001 cross-aggregate validator pattern) |
| **TVL-V15** travel-channel-bound | Travel:Initiate ChannelScope check | `travel.cross_channel_initiate_forbidden` (actor and route must reside in same continent channel; per TDIL-A5 atomic-channel discipline) |

ContentSafetyGate applied to LLM-generated Travel:JourneyNarration `content` field (PII scrubber + injection scanner per §12X.L7 + §12Y.L5; defense in depth).

---

## §8 Failure UX — `travel.*` namespace

TVL_001 V1+30d owns NEW `travel.*` RejectReason namespace (per TVL-D7 — separate from `geography.*`, since travel is a consumer feature with distinct ImpactClass + capability discipline from geography substrate). **15 V1+30d rule_ids:**

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d) | English fallback |
|---|---|---|---|---|
| `travel.route_unknown` | schema | Travel:Initiate | "Tuyến đường được nêu không tồn tại." | "Route not found." |
| `travel.actor_not_at_journey_start` | user | Travel:Initiate | "Bạn không ở điểm khởi hành của tuyến đường này." | "You're not at the starting cell of this route." |
| `travel.backward_one_way_route` | user | Travel:Initiate | "Tuyến đường này không hai chiều — không thể đi ngược." | "Route is one-way; cannot travel backward." |
| `travel.actor_untracked_excluded` | schema | Travel:Initiate AuthorizationGate | "Chỉ PC và NPC chính mới có thể du hành." | "Only PCs and Tracked NPCs can travel." |
| `travel.mode_unavailable_v1plus30d` | user | Travel:Initiate | "Chế độ du hành này chưa khả dụng (V1+30d hỗ trợ đi bộ)." | "Travel mode not available V1+30d (only OnFoot supported)." |
| `travel.actor_already_traveling` | user | Travel:Initiate | "Bạn đang du hành tuyến đường khác. Hãy đến nơi trước khi bắt đầu hành trình mới." | "You're already mid-journey. Arrive first before initiating new travel." |
| `travel.soul_form_no_physical_travel` | user | Travel:Initiate | "Linh hồn không thể du hành vật lý — hãy quay về thể xác trước." | "Soul-form cannot physically travel; return to body first." |
| `travel.insufficient_provisions` | user | Travel:Initiate | "Không đủ lương thực hoặc nước cho hành trình này." | "Insufficient food or water for this journey." |
| `travel.mode_route_incompatible` | user | Travel:Initiate | "Phương thức du hành không phù hợp với loại tuyến đường." | "Travel mode incompatible with route kind (e.g., OnFoot on SeaLane)." |
| `travel.route_layer_not_activated` | schema | Travel:Initiate | "Lớp tuyến đường chưa kích hoạt cho thế giới này." | "Route layer not activated for this reality (pre-ROUTE_001 ship)." |
| `travel.journey_id_collision` | schema | Travel:Initiate (defensive) | "Xung đột định danh hành trình." | "Journey ID collision (defensive; astronomically improbable)." |
| `travel.progress_non_monotonic` | schema | Scheduled:TravelTick apply (defensive) | "Tiến độ hành trình không đơn điệu." | "Travel progress non-monotonic (defensive against malformed ticks)." |
| `travel.arrival_cell_unknown` | schema | Travel:Arrive cascade (defensive) | "Ô đến không xác định." | "Arrival cell unknown (defensive)." |
| `route.remove_blocked_by_active_journey` | user | ROUTE_001 RemoveRoute (cross-feature gate) | "Không thể xóa tuyến đường — có hành trình đang diễn ra trên tuyến này." | "Cannot remove route — active journey in progress on this route." |
| `travel.cross_channel_initiate_forbidden` | schema | Travel:Initiate (channel-scope check) | "Người và tuyến đường phải cùng kênh lục địa." | "Actor and route must be in same continent channel (TDIL-A5 atomic-channel)." |

V1+30d schema-level rejects (8): route_unknown / actor_untracked_excluded / route_layer_not_activated / journey_id_collision / progress_non_monotonic / arrival_cell_unknown / cross_channel_initiate_forbidden / + one defensive cross-feature gate.
V1+30d user-facing rejects (7): the rest.

V2+ reservations: `travel.soul_projection_pending` (V2+ astral-travel activation TVL-D7) + `travel.mount_unavailable` (V1+30d+ when ByBoat / OnHorseback activates TVL-D8).

i18n: V1+30d ships I18nBundle per RES_001 §2 cross-cutting contract from day 1.

---

## §9 Cross-service handoff

| Service | Role | V1+30d status |
|---|---|---|
| **world-service** | Reads `world_geometry.routes` + `world_geometry.settlements` for route validation + arrival hospitality check | V1+30d |
| **travel-service** (NEW V1+30d service) | Authoritative owner of `actor_travel_state` aggregate; applies Travel:Initiate + Scheduled:TravelTick + Travel:Arrive | V1+30d **(new service)** |
| **chat-service** (S9 prompt-assembly) | Read-only consumer — `[TRAVEL_CONTEXT]` sub-section in `[GEOGRAPHIC_CONTEXT]` for journey-narrative LLM grounding; generates Travel:JourneyNarration EVT-T6 Proposal content | V1+30d |
| **api-gateway-bff** | Routes Travel:Initiate POSTs from client-app → travel-service; player travel UI GETs read actor_travel_state for in-flight journey display | V1+30d UI |
| **auth-service** | No new capability claim (travel is regular gameplay action; standard PC/NPC action authorization via existing `can_act_as_actor` pattern) | V1+30d unchanged |
| **knowledge-service** | Reads journey history for actor-travel-pattern knowledge graph (planned V1+ activation per CLAUDE.md two-layer pattern) | Not V1+30d |
| **NPC_002 Chorus / Tracked NPC Generators V2+** | Future consumer — LLM-driven Tracked NPC travel decisions (NPC decides to travel to a settlement based on narrative state); deferred V2+ pending NPC autonomy substrate | V2+ |

**NEW V1+30d service: `travel-service`** — owns `actor_travel_state` aggregate + apply_delta logic + per-turn tick generation. Aggregates roll up via DP-Ch reality-channel binding. EF_001 entity_binding cross-service-write coordination via NEW `entity.travel_journey_id: Option<JourneyId>` additive field (bumps EF_001 schema_version per I14; cross-feature dependency tracked TVL-Q1; world-service writes via standard apply_delta + travel-service reads).

---

## §10 Composition with foundation siblings

| Sibling | Composition with TVL_001 |
|---|---|
| **GEO_004 ROUTE_001** | **Primary substrate dependency** — TVL reads world_geometry.routes for route_id validation + route.distance_units + route.default_fiction_duration + route.is_bidirectional. ROUTE-V8 pair-uniqueness invariant + cell-pair discipline preserved. TVL extends ROUTE_001 RemoveRoute validator pipeline with TVL-V14 cross-feature gate (route_in_use_by_journey). |
| **GEO_003 SET_001** | Hospitality availability lookup at arrival — Settlement.role determines "find an inn" vs "make camp outdoors" narration tag. PL_006 Exhausted status applied if wakeful_duration > 16h AND no-inn-available. SET-V8 RemoveSettlement extension: V1+30d+ cross-feature gate `settlement.remove_blocked_by_active_journey_destination` (deferred — TVL-Q6). |
| **GEO_002 POL_001** | LLM journey-narrative grounding — S9 `[TRAVEL_CONTEXT]` joins route_id → cells along route path → province + state + culture_tag for narrative texture. No POL_001 schema integration; documentation cross-ref only. |
| **GEO_001** | Biome + climate context for journey narration. Mountain biome routes (MountainPass) get climbing-fatigue narrative tone; Desert biome gets heat-exhaustion tone. No GEO_001 schema integration. |
| **TDIL_001** | **Critical sibling coordination** — actor_clock + body_clock + realm_clock advancement per Scheduled:TravelTick (TVL-D4 selective; soul_clock preserved). TDIL-A2 BodyOrSoul distinction gates Travel:Initiate (Soul-form actors blocked V1+30d per TVL-V7). TDIL-A4 actor.time_flow_rate consumed at tick advancement; mid-journey rate changes documented TVL-Q5. TDIL-A5 atomic-channel discipline enforced via TVL-V15 cross-channel-initiate-forbidden. |
| **RES_001** | **Critical sibling coordination** — provisions cost deducted at Travel:Initiate (TVL-V8 sufficient-provisions check); vital_pool Hunger + Thirst advancement; food_per_league + water_per_league defaults V1+30d (tunable per creative_seed.travel_cost_per_league V1+30d+ TVL-D11). |
| **PL_006 Status Effects** | Exhausted status applied at arrival when wakeful_duration > 16h + no-inn-available (Hamlet OR no-settlement arrival); StatusFlag::Exhausted V1 active per PL_006. Wounded status applied if V1+30d+ encounter substrate generates combat events; deferred. |
| **EF_001 Entity Foundation** | **Critical schema dependency** — NEW additive field `entity.travel_journey_id: Option<JourneyId>` (bumps EF_001 schema_version per I14; TVL-Q1 V1+30d schema-coordination tracked). actor.current_cell_id read at Travel:Initiate + WRITTEN at Travel:Arrive. |
| **AIT_001** | Tracked tier discipline — PC + Tracked NPCs participate (TravelInitiator enum); Untracked NPCs excluded (no aggregate; no Travel:Initiate). V2+ off-camera background Untracked-NPC migration deferred TVL-D3. |
| **PCS_001** | Cross-ref: PCS_001 V1+ S8 xuyên không body-substitution interacts with TVL_001 — if PC body is "borrowed" by xuyên không soul during a journey, TVL state stays bound to body (per TDIL-A2 body_clock continuity); soul-projection astral travel V2+ deferred per TVL-D7. |
| **NPC_002 Chorus** | LLM-driven Tracked NPC travel intent — Chorus may propose NPC Travel:Initiate based on narrative state; V1+30d initial implementation uses LLM Generator V1+ activation; V2+ richer NPC travel autonomy. |
| **PL_001 Continuum** | Turn-boundary fire — Scheduled:TravelTick generated per actor_travel_state at each PL_001 turn-boundary per TDIL-A3 per-turn O(1) Generator semantic. No PL_001 schema change. |

---

## §11 RealityManifest extension

**No new RealityManifest field.** TVL_001 V1+30d configuration lives within existing structures:

- Travel cost defaults (`food_per_league + water_per_league`) — V1+30d hardcoded constants in travel-service config; V1+30d+ additive on `creative_seed.travel_cost_per_league: Option<TravelCostConfig>` per TVL-D11.
- Mode-route compatibility matrix — V1+30d hardcoded per §3 rules; not author-tunable V1+30d.

Bootstrap order: TVL_001 V1+30d activates AFTER GEO_001 + GEO_002 + GEO_003 + GEO_004 V1+30d activation triangle. Realities pre-ROUTE-001 ship cannot initiate travel (TVL-V10 reject). Realities post-ROUTE-001 ship can initiate immediately.

V1+30d feature-flag: `services/travel-service` config `travel_enabled: bool` (default true V1+30d; false V1+30d backward-compat for realities NOT wanting travel mechanics). Mid-life feature-flag flip on existing reality FORBIDDEN per generator_pipeline_version discipline.

---

## §12 Sequences

### 12.1 PC travels Khai Phong → Tương Dương on Imperial Highway Road

```
Actor lý_minh at cell:khai_phong (Khai Phong Capital cell); issues Travel:Initiate {
  route_id: imperial_highway_khai_phong_tuong_duong,
  mode: OnFoot,
  direction: Forward
} via client-app player travel command.
  ↓ EVT-T1 validator pipeline:
    AuthorizationGate (lý_minh.tracking_tier == Pc per AIT_001) → pass.
    SchemaGate (route_id exists; mode == OnFoot V1+30d; direction valid) → pass.
    ReferentialIntegrityGate:
      TVL-V2: lý_minh.current_cell_id == route.from_cell (khai_phong) → pass.
      TVL-V6: no Active actor_travel_state for lý_minh → pass.
      TVL-V7: lý_minh.bodyorsoul_form == BodyOrSoul::Body → pass.
      TVL-V8: route.distance_units=24; food_cost=24×1.0=24 units; water_cost=24×2.0=48 units; lý_minh.resource_inventory
        food=50 ≥ 24 + water=80 ≥ 48 → pass. (HIGH-4 fix — Consumable inventory check, not vital_pool body-state)
      TVL-V9: mode=OnFoot + route.kind=Road compatible → pass.
      TVL-V10: world_geometry.schema_version=3 (post-ROUTE_001 ship) → pass.
      TVL-V15: lý_minh.channel_id == route's continent channel → pass.
    OrderingGate + ContentSafetyGate → pass.
  ↓ EVT-T3 Derived: actor_travel_state row created:
    journey_id = blake3-derive (lý_minh.actor_id || route.id || fiction_clock_at_initiate)
    actor_id = lý_minh.actor_id
    route_id = imperial_highway_khai_phong_tuong_duong
    mode = OnFoot
    direction = Forward
    status = Active
    progress_fraction = 0.0
    initiated_at_fiction_time = 2026-05-14T08:00 (lý_minh.actor_clock)
    expected_arrival_fiction_time = 2026-05-14T08:00 + 24h (route.default_fiction_duration at lý_minh.time_flow_rate=1.0)
    elapsed_duration = 0
    provisions_consumed = ProvisionsConsumed { food_units: 24.0, water_units: 48.0 }
    initiator = Pc
  ↓ Cascade RES_001: lý_minh.resource_inventory.food -= 24 (50→26); water -= 48 (80→32). (HIGH-4 fix — Consumable inventory deduction; vital_pool body-state untouched by TVL)
  ↓ Cascade EF_001: lý_minh.travel_journey_id = Some(journey_id); current_cell_id LATCHED (still khai_phong
    until arrival).
  ↓ Per-turn Scheduled:TravelTick fires (assume 4h tick at PL_001 turn-boundary):
    Tick 1: progress_fraction = 4/24 = 0.167; actor_clock + body_clock += 4h.
    Tick 2: progress_fraction = 8/24 = 0.333.
    Tick 3-5: progress_fraction = 0.5, 0.667, 0.833.
    Tick 6: progress_fraction = 24/24 = 1.0 (clamped); status Active → Arrived.
  ↓ Travel:Arrive cascade:
    EVT-T3 Derived: actor_travel_state.status = Arrived; lý_minh.current_cell_id = tuong_duong; travel_journey_id = None.
    Hospitality check: Tương Dương is Capital → inn-available; no Exhausted status.
    EVT-T6 Proposal: chat-service Travel:JourneyNarration "Lý Minh đến Tương Dương sau một ngày trên đường lớn..."
  ↓ Total fiction-clock advancement for lý_minh: actor_clock + body_clock += 24h; soul_clock unchanged.
```

### 12.2 Travel rejected — insufficient provisions

```
Actor tieu_long_nu at cell:cao_thien_dai (high in mountains); issues Travel:Initiate {
  route_id: cao_thien_dai_xa_grade_pass,  // MountainPass route
  mode: OnFoot, direction: Forward }
  ↓ TVL-V8 sufficient-provisions check:
    route.distance_units = 8 (single-edge MountainPass);
    food_cost = 8 × 1.0 = 8; water_cost = 8 × 2.0 = 16;
    tieu_long_nu.vital_pool.hunger = 5 (only 5 units of food) < 8 → REJECT travel.insufficient_provisions.
  ↓ UI surfaces Vietnamese reject copy: "Không đủ lương thực hoặc nước cho hành trình này."
  ↓ Admin/player workflow: actor consumes / acquires food first via RES_001 before retry.
```

### 12.3 Travel rejected — actor already traveling

```
Actor ly_minh (already mid-journey from §12.1 at progress_fraction=0.5); issues Travel:Initiate for different route.
  ↓ TVL-V6 one-journey-per-actor check: existing actor_travel_state.status == Active → REJECT travel.actor_already_traveling.
  ↓ UI surfaces: "Bạn đang du hành tuyến đường khác. Hãy đến nơi trước khi bắt đầu hành trình mới."
```

### 12.4 ROUTE_001 RemoveRoute blocked by active journey

```
Forge admin emits RemoveRoute { route_id: imperial_highway_khai_phong_tuong_duong, reason: ... }
  ↓ ROUTE_001 RemoveRoute validator pipeline (TVL_001-extended):
    TVL-V14 route-in-use-by-journey check: query actor_travel_state for any Active row with route_id matching →
    found lý_minh's journey (§12.1) → REJECT route.remove_blocked_by_active_journey.
  ↓ UI surfaces: "Không thể xóa tuyến đường — có hành trình đang diễn ra trên tuyến này."
  ↓ Admin workflow: wait for lý_minh's journey to Arrive, OR Forge:CancelJourney first (V1+30d admin-only per
    TVL-D9; sets status=Canceled; partial provisions refund per TVL-Q3).
```

### 12.5 Forced outdoor camp at Hamlet arrival

```
Actor tieu_long_nu travels Trail from a City to a remote Hamlet over 18 hours.
  ↓ At arrival: settlement.role == Hamlet → no inn available;
    wakeful_duration_at_arrival = 18h > 16h threshold → apply PL_006 status StatusFlag::Exhausted Tier 0 via OutputDecl.
  ↓ EVT-T3 cascade to PL_006 apply_set_status; tieu_long_nu now Exhausted.
  ↓ Narration: "Tiểu Long Nữ đến bản nhỏ giữa rừng; không có quán trọ; nàng mệt mỏi dựng lán ngủ ngoài trời..."
```

---

## §13 Acceptance criteria

15 V1+30d-testable acceptance scenarios. LOCK granted when ≥10 pass integration tests against travel-service reference impl + ROUTE_001 + SET_001 + TDIL_001 fixtures.

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-TVL-1** | PC at route.from_cell issues Travel:Initiate{OnFoot, Forward}; sufficient provisions; route ∈ wg.routes → actor_travel_state row created with status=Active, progress_fraction=0.0, expected_arrival_fiction_time = initiated + route.default_fiction_duration; RES_001 vital_pool deducted; EF_001 travel_journey_id linked. | — |
| **AC-TVL-2** | Per-turn Scheduled:TravelTick advances progress_fraction proportionally; TDIL clocks advance selectively (actor + body; soul unchanged); progress_fraction reaches 1.0 → status Active → Arrived; actor.current_cell_id updated to route.to_cell. | — |
| **AC-TVL-3** | Tracked NPC initiates travel via Chorus LLM-driven intent → same flow as PC; actor_travel_state initiator=TrackedNpc; participates in per-turn ticks. | — |
| **AC-TVL-4** | Untracked NPC attempts Travel:Initiate → reject. | `travel.actor_untracked_excluded` |
| **AC-TVL-5** | Actor with active journey attempts second Travel:Initiate → reject. | `travel.actor_already_traveling` |
| **AC-TVL-6** | Soul-form actor (BodyOrSoul::Soul per PCS_001) attempts Travel:Initiate → reject. | `travel.soul_form_no_physical_travel` |
| **AC-TVL-7** | Actor at wrong cell (current_cell_id != route.from_cell for Forward) attempts Travel:Initiate → reject. | `travel.actor_not_at_journey_start` |
| **AC-TVL-8** | Actor with insufficient food/water attempts Travel:Initiate → reject; vital_pool unchanged. | `travel.insufficient_provisions` |
| **AC-TVL-9** | Actor attempts OnFoot mode on SeaLane route → reject. | `travel.mode_route_incompatible` |
| **AC-TVL-10** | Actor attempts ByBoat mode V1+30d → reject (mode unavailable V1+30d). | `travel.mode_unavailable_v1plus30d` |
| **AC-TVL-11** | Travel to Hamlet (no inn) with wakeful_duration > 16h at arrival → PL_006 StatusFlag::Exhausted applied via OutputDecl cascade. | — |
| **AC-TVL-12** | Travel to City (inn available) with wakeful_duration > 16h → NO Exhausted status (rest at inn implicit). | — |
| **AC-TVL-13** | ROUTE_001 RemoveRoute on a route with Active journey → reject. | `route.remove_blocked_by_active_journey` |
| **AC-TVL-14** | Travel:Initiate on pre-ROUTE_001-ship reality (world_geometry.schema_version < 3) → reject. | `travel.route_layer_not_activated` |
| **AC-TVL-15** | Snapshot fork at event E mid-journey (progress_fraction=0.5) → child reality inherits actor_travel_state row bit-exactly; child's per-turn ticks advance independently from parent; parent's continued ticks don't cascade. | — |

---

## §14 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **TVL-D1** | Encounter generation during travel (random events; bandit ambush; weather; combat) | V1+30d+ | Per TVL-D2 scope discipline. Encounter substrate is separate design effort layered atop TVL_001 V1+30d state aggregate. |
| **TVL-D2** | Mount/vehicle travel (OnHorseback / ByBoat / ByShip / ByCarriage) | V1+30d+ | Requires RES_001 V2+ mount-as-resource OR new mount aggregate. ByBoat schema-reserved V1+30d for SeaLane + RiverNavigation. |
| **TVL-D3** | Off-camera background NPC migration (Untracked NPCs migrating between cells without explicit Travel:Initiate; quantum-observation pattern) | V2+ | Untracked NPCs have no aggregate per AIT-A8; V2+ feature designs ambient-migration mechanism. |
| **TVL-D4** | Composite multi-segment travel (player declares destination; system auto-traverses N routes via Dijkstra-shortest-path) | V1+30d+ | Convenience command layered atop atomic single-segment V1+30d. |
| **TVL-D5** | Group/party travel (multiple actors traversing same route together) | V1+30d+ | Requires party-formation aggregate. |
| **TVL-D6** | Weather/season travel modifiers (climate × route.kind effects on default_fiction_duration; storm-bound delays) | V2+ | Coupled with V2+ weather substrate. |
| **TVL-D7** | Soul-projection astral travel (BodyOrSoul::Soul form; per wuxia/cultivation archetype canon) | V2+ | Currently TVL-V7 rejects Soul-form Travel:Initiate. |
| **TVL-D8** | One-way routes activation (route.is_bidirectional = false) | V1+30d+ | Per ROUTE-D3; TVL-V3 validator already covers; routes V1+30d all bidirectional. |
| **TVL-D9** | Actor self-cancel of in-flight journey (V1+30d only admin Forge:CancelJourney; self-cancel deferred) | V1+30d+ | UX decision: forced commitment to journey vs. cancel-with-partial-refund. |
| **TVL-D10** | Admin Forge:RevertJourneyProgress (set progress_fraction back; rare edit case) | V2+ | Currently progress monotonic per TVL-V12; admin revert would break monotonicity invariant. |
| **TVL-D11** | Per-reality TravelCostConfig (food_per_league + water_per_league overrides via creative_seed.travel_cost_per_league) | V1+30d+ | Currently hardcoded V1+30d. Author UX tuning V1+30d+. |
| **TVL-D12** | V2+ T6 NarrativeTravelEdit Generator (LLM observes journey state + proposes mid-journey events) | V2+ | Parallel to GEO/POL/SET/ROUTE T6 patterns; layered with encounter generator TVL-D1. |

---

## §15 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **TVL-Q1** | EF_001 additive field `entity.travel_journey_id: Option<JourneyId>` — does this trigger EF_001 schema_version bump? Cross-feature coordination concern. | V1+30d: YES, bumps EF_001 schema_version per I14 + GEO/POL/SET precedent. Coordinate with EF_001 closure pass to add the field at TVL_001 ship; EF_001 schema_version 1 → 2 V1+30d bump. |
| **TVL-Q2** | TVL-V14 route_in_use_by_journey cross-feature validator — owned by ROUTE_001 or TVL_001? | V1+30d: validator slot OWNED BY TVL_001 but REGISTERED in ROUTE_001 RemoveRoute pipeline (cross-feature gate pattern mirrors POL_001 cross-aggregate validator C-rules from TIT-C1 + PO-C1 precedents). |
| **TVL-Q3** | Travel cancel — provisions refund policy (full / proportional-to-remaining / none)? | V1+30d: proportional refund (remaining_distance / total_distance × provisions_consumed) refunded to RES_001 vital_pool at Forge:CancelJourney apply. Defensive: V1+30d+ self-cancel will inherit this policy. |
| **TVL-Q4** | Parallel-body journeys (body active travel while soul does something else) — TDIL-A2 BodyOrSoul split allows this conceptually | V1+30d+: deferred — V1+30d enforces single-journey-per-actor regardless of body/soul state. V1+30d+ may relax for cultivation-archetype scenarios. |
| **TVL-Q5** | Mid-journey actor.time_flow_rate changes (e.g., entering a time-dilated zone mid-route) | V1+30d: time_flow_rate treated as CONSTANT for journey duration (snapshot at Travel:Initiate). V1+30d+: ticks re-derive rate per fire from actor's current time_flow_rate; expected_arrival_fiction_time recomputed at rate-change. |
| **TVL-Q6** | SET_001 RemoveSettlement at journey destination — should that reject if Active journey targets this settlement? | V1+30d+: deferred. V1+30d: RemoveSettlement always proceeds; if it orphans the destination, actor's Travel:Arrive cascade applies cell-only (Settlement gone; "outdoor camp" narration applies regardless of pre-Remove role). |
| **TVL-Q7** | Storage representation: monolithic Vec<ActorTravelState> per reality, OR per-actor SQL table? | V1+30d: sparse aggregate per (actor_id, journey_id); event-sourced via T2/Reality discipline; queries by actor_id (single-actor) common, queries-all-active per reality less common. SQL denormalization V2+ if STRAT_001 needs cross-actor travel-state queries. |

---

## §16 Cross-references

- [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — catalog; owns `TVL-*` namespace
- [`_index.md`](_index.md) — folder index; TVL_001 row added 2026-05-14
- [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) — primary substrate (Route graph)
- [`GEO_003 SET_001`](../00_geography/GEO_003_settlement_generator.md) — hospitality availability
- [`GEO_002 POL_001`](../00_geography/GEO_002_political_layer.md) — journey-narrative grounding
- [`GEO_001`](../00_geography/GEO_001_world_geometry.md) — biome + climate context
- [`TDIL_001`](../03_actor_substrate/TDIL_001_time_dilation_foundation.md) — 4-clock model + BodyOrSoul gating
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) — provisions cost
- [`PL_006`](../04_play_loop/PL_006_status_effects.md) — Exhausted status application
- [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) — Tracked tier discipline
- [`EF_001`](../03_actor_substrate/EF_001_entity_foundation.md) — entity.travel_journey_id additive field (cross-feature dependency)
- [`PL_001 Continuum`](../04_play_loop/PL_001_continuum.md) — turn-boundary fire for Scheduled:TravelTick
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — NEW `actor_travel_state` aggregate row
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — NEW `travel.*` namespace (§1.4); NEW EVT-T1 sub-type `Travel:Initiate` (§1); NEW EVT-T5 sub-type `Scheduled:TravelTick` (§1); NEW EVT-T6 sub-type `Travel:JourneyNarration` (§1)

---

## §17 Implementation readiness

**Design layer (this commit):** ✅ NEW aggregate schema + 4 V1+30d closed enums + 15 validator slots + 15 V1+30d rule_ids + 12 deferrals + 7 open questions + per-turn tick mechanism + selective TDIL clock advancement + hospitality availability at arrival + cross-feature coordination with EF_001/ROUTE_001/SET_001/TDIL_001/RES_001/PL_006/AIT_001 + 15 acceptance scenarios — all declared.

**Implementation phase (V1+30d):** 📦 NEW `services/travel-service` (owns actor_travel_state aggregate + apply_delta logic + per-turn tick generator); EF_001 closure pass adds `travel_journey_id: Option<JourneyId>` field with schema_version 1→2 bump; ROUTE_001 RemoveRoute validator pipeline extended with TVL-V14 cross-feature gate; chat-service S9 prompt-assembly extended with `[TRAVEL_CONTEXT]` sub-section for journey-narrative grounding; CI gates: replay-determinism (same seed + route + initiated_at_fiction_time → byte-identical progress_fraction sequence) + apply_delta total-function for Travel:Initiate + Scheduled:TravelTick + Travel:Arrive + cross-channel-initiate-forbidden gate (TVL-V15).

**Downstream consumer integration (V1+30d+ / V2+):** 📦 encounter generator V1+30d+ (attaches encounter events to actor_travel_state) · mount/vehicle travel V1+30d+ (activates ByBoat mode) · composite multi-segment V1+30d+ (Dijkstra over Route graph) · group/party travel V1+30d+ · NPC_002 V2+ Chorus-driven Tracked NPC travel autonomy.

**Status:** DRAFT 2026-05-14. CANDIDATE-LOCK upon §13 acceptance scenarios passing integration tests against the reference travel-service implementation. LOCK upon downstream consumer integration (encounter generator V1+30d+ design lands consuming actor_travel_state; mount/vehicle V1+30d+ activates ByBoat; SET_001 SET-D14 cross-feature validator coordination resolves TVL-Q6).

**First feature consuming V1+30d activation triangle.** ROUTE_001 V1+30d ships the Route graph; TVL_001 V1+30d ships the consumer that makes it traversable. Strategy substrate readiness extended at consumer layer — travel mechanics now exist that future STRAT_001 V2+ can leverage for army-movement modeling.
