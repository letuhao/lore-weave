# TVL_002 — Composite Multi-Segment Travel

> **Conversational name:** "Composite Travel" (CTV). V1+30d+ convenience layer over TVL_001 atomic single-segment travel. Player declares a destination cell; system runs Dijkstra over the GEO_004 ROUTE_001 Route graph, freezes the resulting ordered segment list, and auto-traverses the N segments — each segment is a plain TVL_001 atomic journey underneath. Eliminates the manual `Travel:Initiate` micro-management at every intermediate settlement. Smart overnight stops at inn-bearing intermediate settlements (auto-rest where an inn is available; outdoor camp + Exhausted check where not). Whole-journey provisions pre-pay at initiate. Re-plan fallback if a planned segment's route is removed mid-journey; `Stranded` terminal status if re-plan fails. Actor self-cancel (`CompositeTravel:Cancel`) takes effect at the next segment boundary. PC + Tracked NPC parity inherited from TVL_001.
>
> **Category:** TVL — Travel Mechanics (V1+30d+ convenience feature; second TVL feature; layered atop TVL_001 V1+30d atomic travel)
> **Status:** **DRAFT 2026-05-16** (Phase 0 CTV-D1..D7 LOCKED with user `approve all` directive)
> **Catalog refs:** [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — owns `TVL-*` stable-ID namespace (`TVL-A*` axioms · `TVL-D*` deferrals · `TVL-Q*` open questions · `AC-TVL-*` acceptance · `CTV-*` validators per-feature)
> **Builds on:** [`TVL_001`](TVL_001_travel.md) (parent — atomic single-segment travel; `actor_travel_state` aggregate; `Travel:Initiate`/`Scheduled:TravelTick`/`Travel:Arrive`; `TravelMode`/`TravelInitiator`/`TravelDirection`/`TravelStatus` enums; `JourneyId`; hospitality check; provisions cost; selective TDIL clock advancement; TVL-V1..V15 validators) · [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) (Route graph traversed by Dijkstra — `route.distance_units` as edge weight; `route.is_bidirectional`; ROUTE-V8 pair-uniqueness) · [`GEO_003 SET_001`](../00_geography/GEO_003_settlement_generator.md) (Settlement.role for intermediate-stop hospitality / auto-rest) · [`TDIL_001`](../03_actor_substrate/TDIL_001_time_dilation_foundation.md) (per-segment selective clock advancement inherited unchanged) · [`RES_001`](../00_resource/RES_001_resource_foundation.md) (whole-journey provisions pre-pay) · [`PL_006`](../04_play_loop/PL_006_status_effects.md) (Exhausted applied at no-inn intermediate stops) · [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) (Tracked tier discipline inherited) · [`EF_001`](../03_actor_substrate/EF_001_entity_foundation.md) (`entity.travel_journey_id` reused per-segment; no new EF_001 field)
> **Resolves:** Multi-settlement travel UX micro-management (V1+30d atomic travel forces the player to issue `Travel:Initiate` at every intermediate settlement along a multi-hop route — for a Khai Phong → Tương Dương → Lâm An trip that is 2+ manual commands with manual provisioning at each leg; TVL_002 collapses it to one declared destination) · Journey-plan visibility gap (V1+30d atomic travel has no "show me the route to X" preview — the player cannot see total distance / ETA / provisions cost before committing; TVL_002 adds a read-only `composite_travel_plan` query) · Multi-day-journey Exhausted pile-up (V1+30d atomic travel applies Exhausted at every no-inn arrival; a player chaining segments manually accumulates Exhausted with no rest discipline; TVL_002's smart overnight stops model "travel by day, rest at towns")
> **Defers to:** future **TVL_004 Travel Encounters V1+30d+** (encounters during a composite journey attach at the per-segment `actor_travel_state` level — composite is encounter-agnostic; an encounter pausing a segment naturally pauses the composite) · future **TVL_003 Mount/Vehicle Travel V1+30d+** (ByBoat/OnHorseback composite paths — composite inherits TVL_001 `TravelMode`; multi-modal paths mixing OnFoot land segments + ByBoat SeaLane segments deferred CTV-D5) · future **TVL_005 Group/Party Travel V1+30d+** (a party traversing a composite path together; party-formation aggregate) · future **mid-journey re-supply V2+** (composite path passing through market settlements could re-provision — requires V2+ economy substrate; V1+30d+ is whole-journey pre-pay only) · future **weighted-cost path preferences V2+** (Dijkstra V1+30d+ minimizes total `distance_units`; V2+ could weight by safety / road-quality / toll once those substrates exist per CTV-D6)

---

## §1 Why this exists

Three concrete gaps that TVL_002 closes — all UX/convenience, none structural (TVL_001 already ships the load-bearing mechanics).

**Gap 1 — Multi-hop travel is manual micro-management.** TVL_001 V1+30d ships *atomic* single-segment travel: one `Travel:Initiate { route_id }` per Route. A realistic journey crosses several Routes — Khai Phong → Tương Dương is the Imperial Highway Road; Tương Dương → Lâm An is a second Road; a mountain detour adds a MountainPass. Under V1+30d the player issues `Travel:Initiate` at Khai Phong, waits for arrival, manually checks provisions, issues the next `Travel:Initiate` at Tương Dương, and so on. Each leg is a separate command, a separate provisioning decision, a separate UI round-trip. For a Tracked NPC driven by chat-service Chorus this is N separate LLM-intent emissions. TVL_002 collapses the whole trip to one declared destination: the system computes the path and auto-traverses it.

**Gap 2 — There is no journey preview.** Before committing to a multi-day journey the player wants to know: how far is it, how long will it take, how much food and water will it cost, how many segments, which settlements does it pass through. V1+30d atomic travel exposes none of this — `route.distance_units` and `route.default_fiction_duration` exist per-Route but there is no aggregate query that *composes* them across a path. TVL_002 adds the read-only `composite_travel_plan` query: the client surfaces the Dijkstra result (path, total distance, ETA, total provisions cost, segment count, intermediate settlements) and the player confirms before any aggregate mutation.

**Gap 3 — Multi-day journeys pile up Exhausted with no rest discipline.** TVL_001 §5.3 applies `PL_006 StatusFlag::Exhausted` at every arrival cell that lacks an inn when `wakeful_duration > 16h`. A player chaining segments manually has no built-in "rest at the town overnight" behavior — `wakeful_duration` accumulates monotonically across legs and Exhausted stacks. TVL_002's smart overnight stops fix this: at each *intermediate* settlement the composite handler runs the TVL_001 hospitality check, and where an inn is available it auto-rests the actor (resets `wakeful_duration`) before initiating the next segment. The composite journey models the way travelers actually move — by day, resting at towns.

TVL_002 introduces **no new physics**. Every segment is a TVL_001 atomic journey; clocks, provisions-per-league, hospitality, validators, replay-determinism all come from TVL_001 unchanged. TVL_002 is an orchestration aggregate that plans and sequences atomic journeys.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Composite journey** | `composite_journey` aggregate (T2/Reality, sparse per-(actor_id, composite_journey_id)) — NEW V1+30d+ | One row per active composite journey. Sparse: only Tracked-tier actors with an active composite journey have a row. Closed when the actor reaches the declared destination (`Arrived`), self/admin-cancels (`Canceled`), or re-plan fails (`Stranded`). |
| **CompositeJourneyId** | `pub struct CompositeJourneyId(pub(crate) Ulid)` opaque newtype | Module-private constructor; allocated at `CompositeTravel:Initiate` via blake3-derive from `(actor_id, origin_cell_id, destination_cell_id, fiction_clock_at_initiate)` for replay-determinism. |
| **PlannedSegment** | One entry in `composite_journey.plan: Vec<PlannedSegment>` | The frozen Dijkstra result. Ordered origin→destination. Each entry names a `route_id`, a `direction` (Forward/Backward — TVL_001 enum, picked so traversal goes the intended way along the Route), the segment's `from_cell_id`/`to_cell_id`, `distance_units`, `default_fiction_duration`, and a `traversed` flag set true on segment completion. |
| **Plan freeze** | `plan` computed once at `CompositeTravel:Initiate` and stored immutably except by re-plan | Freezing the Dijkstra result gives replay-determinism and a stable ETA. The plan is mutated *only* by the re-plan fallback (CTV-D2), and each re-plan increments `replan_count`. |
| **Re-plan fallback** | Segment-handoff recovery when the next planned segment's route is invalid | TVL-V14 (`route_in_use_by_journey`) blocks `RemoveRoute` only for the *currently-active* segment's route — a *future* planned segment's route is not protected and an admin may remove it. At segment handoff, if the next planned segment fails TVL_001 segment validation, the handler runs Dijkstra once from the current cell to `destination_cell_id` and splices the new tail into `plan`. If re-plan fails (no path) or `replan_count` would exceed the cap → `Stranded`. |
| **Stranded** | Terminal `CompositeJourneyStatus` | The actor sits at its current cell; the composite journey is closed unsuccessfully. Reached when re-plan finds no path, the re-plan cap is hit, or a re-planned longer path needs more provisions than the actor pre-paid. Un-traversed provisions are proportionally refunded (CTV-D4). |
| **Whole-journey provisions** | `composite_journey.total_provisions_consumed` deducted at initiate | Sum of `food_per_league × distance_units` and `water_per_league × distance_units` over *all* planned segments, deducted from `actor.resource_inventory.food`/`.water` (Consumable possessions) at `CompositeTravel:Initiate` — the TVL_001 HIGH-4 semantic (inventory possessions, NOT `vital_pool` body-state). Insufficient → reject `travel.composite_insufficient_provisions`. |
| **Smart overnight stop** | Per-intermediate-settlement hospitality + auto-rest | At each intermediate-cell arrival the composite handler runs the TVL_001 §5.3 hospitality check. Inn available (Settlement.role ∈ {Village, Town, City, Capital}) → auto-rest: `actor.wakeful_duration` reset to 0, narration tag `intermediate-rest-at-inn`, no Exhausted. No inn (Hamlet / Fortress / no settlement) → outdoor camp: standard TVL_001 Exhausted check applies. |
| **Segment handoff** | EVT-T3 cascade fired by a segment's `Travel:Arrive` | When the active segment's `actor_travel_state` transitions `Active → Arrived`, the composite handler advances `current_segment_index`, runs the smart-overnight-stop check, then either: composite `Arrived` (no next segment), `Canceled` (cancel flag set — see CTV-D6), re-plan, or initiate the next segment. |
| **One-composite-per-actor invariant** | `composite_journey` keyed on `(actor_id, composite_journey_id)`, constraint ≤1 row per actor where `status == Active` | A second `CompositeTravel:Initiate` while one is Active → reject `travel.actor_already_in_composite_journey`. A manual TVL_001 `Travel:Initiate` while a composite is Active → reject `travel.actor_in_composite_journey` (new cross-feature gate CTV-V15). |
| **composite_travel_plan query** | Read-only query, NOT an event — surfaced by api-gateway-bff before initiate | Computes the Dijkstra path + total distance + ETA + total provisions cost + segment count + intermediate settlement names for client preview. Mutates no aggregate. The player confirms; only then is `CompositeTravel:Initiate` emitted. |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

TVL_002 introduces no new EVT-T* category. It adds sub-types to existing mechanism-level categories.

| TVL_002 event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Actor declares a composite destination | **EVT-T1 Submitted** | `CompositeTravel:Initiate { actor_id, destination_cell_id, mode }` (NEW V1+30d+ sub-type) | PC via client-app travel UI (after confirming the `composite_travel_plan` preview) / Tracked NPC via chat-service Chorus per NPC_002 | Recorded in `_boundaries/02_extension_contracts.md` §1.4 (the `travel.*` namespace row — there is no separate EVT-T1 sub-type registry table; the EVT-T8 sub-shape registry is §4). |
| Actor self-cancels a composite journey | **EVT-T1 Submitted** | `CompositeTravel:Cancel { composite_journey_id }` (NEW V1+30d+ sub-type) | PC via client-app / Tracked NPC via Chorus | Sets `cancel_requested = true`; takes effect at next segment boundary (CTV-D6). |
| Composite journey state mutation (initiate / segment handoff / re-plan / arrive / cancel / strand) | **EVT-T3 Derived** | `aggregate_type=composite_journey` | Aggregate-Owner role (travel-service) | Causal-ref to the triggering `CompositeTravel:Initiate`, `CompositeTravel:Cancel`, or the segment's `Travel:Arrive` (handoff). |
| Per-segment atomic journey start | **EVT-T3 Derived** | creates an `actor_travel_state` row (TVL_001 aggregate) with `composite_journey_id = Some(..)` | travel-service composite handler | **NOT** a player `Travel:Initiate` EVT-T1 — the composite handler creates the segment's `actor_travel_state` directly via EVT-T3 cascade, re-running TVL_001 segment validators (TVL-V1/V2/V3/V9/V10/V13/V15) inline. Validator failure triggers the re-plan fallback rather than a player-facing reject. |
| Per-segment progress tick | **EVT-T5 Scheduled** | `Scheduled:TravelTick { journey_id }` (TVL_001 sub-type, unchanged) | EVT-G framework Generator at PL_001 turn-boundary | Composite adds no tick mechanism — it observes the segment's `actor_travel_state` reaching `progress_fraction == 1.0`. |
| Admin cancels a composite journey | **EVT-T8 Administrative** | `Forge:CancelCompositeJourney { composite_journey_id, reason }` (NEW V1+30d+ sub-type) | Forge admin via S5/S13 admin tooling | Immediate cancel (vs. the player's next-boundary self-cancel). Requires the standard admin capability per ADMIN_ACTION_POLICY; cancels the active segment + closes the composite. |
| LLM travel narration | **EVT-T6 Proposal** | `Travel:JourneyNarration { journey_id, content }` (TVL_001 sub-type, unchanged) | chat-service S9 LLM | Reused per-segment unchanged. Composite arrival narration reuses `Travel:JourneyNarration` keyed on the final segment's `journey_id`. No new EVT-T6 sub-type. |

**No new GeographyDeltaKind** — composite travel is per-actor runtime state, does not touch `world_geometry`.

**`CompositeTravel:Initiate`/`Cancel` are EVT-T1 Submitted not EVT-T8 Administrative** — regular gameplay actions (PC + Tracked NPC), no capability claim beyond standard PC/NPC action authorization. Only `Forge:CancelCompositeJourney` is EVT-T8 (admin override).

---

## §3 Aggregate inventory

One new aggregate owned by TVL_002. One additive field on TVL_001's `actor_travel_state` (cross-feature; see CTV-Q1).

### 3.1 `composite_journey` (T2/Reality, sparse per-(actor, composite_journey)) — PRIMARY (NEW V1+30d+)

```rust
#[derive(Aggregate)]
#[dp(type_name = "composite_journey", tier = "T2", scope = "reality")]
pub struct CompositeJourney {
    pub composite_journey_id: CompositeJourneyId,           // primary key (sparse — only Tracked actors with an active composite have rows)
    pub actor_id: ActorId,                                  // FK into EF_001 entity registry; composite uniqueness invariant: ≤1 row per actor_id where status == Active
    pub origin_cell_id: CellId,                             // actor.current_cell_id at CompositeTravel:Initiate
    pub destination_cell_id: CellId,                        // declared target cell
    pub plan: Vec<PlannedSegment>,                          // frozen Dijkstra result; ordered origin → destination; mutated only by re-plan
    pub current_segment_index: u32,                         // 0-based; the segment currently active or next to initiate
    pub active_segment_journey_id: Option<JourneyId>,       // the TVL_001 actor_travel_state row for the in-flight segment, if one is active; None between segments
    pub status: CompositeJourneyStatus,                     // Active | Arrived | Canceled | Stranded
    pub mode: TravelMode,                                   // OnFoot V1+30d+ (TVL_001 enum reused); ByBoat / multi-modal deferred CTV-D5
    pub total_distance_units: f32,                          // sum of plan[].distance_units (origin-version; recomputed on re-plan)
    pub total_provisions_consumed: ProvisionsConsumed,      // whole-journey food + water deducted at CompositeTravel:Initiate; grows by any re-plan shortfall top-up per §5.4 (TVL_001 ProvisionsConsumed struct reused)
    pub initiated_at_fiction_time: FictionTime,             // actor_clock at CompositeTravel:Initiate
    pub expected_arrival_fiction_time: FictionTime,         // initiated + Σ(segment default_fiction_duration) × actor.time_flow_rate (no inter-segment gap — HIGH-3 fix; segments chain in-cascade)
    pub cancel_requested: bool,                             // self-cancel flag; set by CompositeTravel:Cancel; honored at next segment boundary
    pub replan_count: u32,                                  // number of re-plans performed; cap CTV-V13 (≤3 V1+30d+); audit + Stranded trigger
    pub initiator: TravelInitiator,                         // Pc | TrackedNpc (TVL_001 enum reused; PC + Tracked NPC parity)
}

pub struct PlannedSegment {
    pub route_id: RouteId,                                  // FK into world_geometry.routes
    pub direction: TravelDirection,                         // Forward | Backward — picked so traversal advances origin → destination
    pub from_cell_id: CellId,                               // segment start cell
    pub to_cell_id: CellId,                                 // segment end cell
    pub distance_units: f32,                                // route.distance_units snapshot at plan time (Dijkstra edge weight)
    pub default_fiction_duration: FictionDuration,          // route.default_fiction_duration snapshot at plan time
    pub traversed: bool,                                    // false at plan time; true when this segment's actor_travel_state reaches Arrived
}

pub enum CompositeJourneyStatus {                           // closed enum 4 V1+30d+
    Active,                                                 // in progress; a segment is active or the next is about to initiate
    Arrived,                                                // actor reached destination_cell_id; all segments traversed
    Canceled,                                               // self-cancel (CompositeTravel:Cancel) or admin (Forge:CancelCompositeJourney)
    Stranded,                                               // re-plan failed / re-plan cap hit / re-planned path under-provisioned; actor sits at current cell
}
```

**Rules:**

- One row per `(actor_id, status=Active)` tuple — ≤1 Active composite journey per actor V1+30d+. Violation → `travel.actor_already_in_composite_journey`.
- `origin_cell_id` MUST equal `actor.current_cell_id` at `CompositeTravel:Initiate` (CTV-V2). `destination_cell_id` MUST differ from `origin_cell_id` (CTV-V6 — degenerate same-cell composite rejected `travel.composite_destination_is_origin`).
- `plan` is non-empty and contiguous: `plan[0].from_cell_id == origin_cell_id`, `plan[last].to_cell_id == destination_cell_id`, and `plan[i].to_cell_id == plan[i+1].from_cell_id` for all `i`. Enforced at initiate (CTV-V5 path-resolves) and after every re-plan.
- `plan.len()` ≤ 20 segments V1+30d+ (CTV-V12 `travel.composite_path_too_long`) — bounds Dijkstra work + tick orchestration; raised V2+ if continent-scale journeys need it.
- `current_segment_index ∈ [0, plan.len())` for the entire journey, including at the `Arrived` transition — §5.3's `Arrived` branch does NOT increment it, so it stays the final-segment index `plan.len() - 1`.
- `mode == OnFoot` V1+30d+ (CTV-V9 `travel.composite_mode_unavailable_v1plus30d`). All segments share one mode; multi-modal paths deferred CTV-D5.
- Whole-journey provisions: actor MUST have ≥ `Σ food_per_league × distance_units` Food units AND ≥ `Σ water_per_league × distance_units` Water units in `resource_inventory` at initiate (CTV-V7 `travel.composite_insufficient_provisions`). Inventory possession check — NOT `vital_pool` (TVL_001 HIGH-4 semantic inherited).
- `replan_count` ≤ 3 V1+30d+ (CTV-V13). Exceeding the cap → `Stranded`.
- `status` transitions are monotone toward a terminal: `Active → {Arrived | Canceled | Stranded}`. No terminal → `Active`.
- `active_segment_journey_id` is `Some(..)` while a segment's `actor_travel_state` is `Active`; transiently `None` within a segment-handoff cascade (between one segment's `Arrived` and the next segment's in-cascade initiation), and permanently `None` once the composite reaches a terminal status.

### 3.2 Cross-feature additive field on `actor_travel_state` (TVL_001 aggregate)

```rust
// added to TVL_001 ActorTravelState — additive Option field per I14
pub composite_journey_id: Option<CompositeJourneyId>,       // Some(..) if this segment belongs to a composite journey; None for a standalone TVL_001 atomic journey
```

Additive `Option` field → bumps `actor_travel_state` aggregate `schema_version` per I14 (default-tolerant readers: pre-bump rows read `composite_journey_id = None`). Cross-feature coordination tracked **CTV-Q1** — added at TVL_002 ship via a TVL_001 closure pass; mirrors TVL_001's own EF_001 `travel_journey_id` precedent (TVL-Q1). The field lets a segment know it is composite-driven (so TVL_001 `Travel:Arrive` defers the arrival cascade to the composite handler for intermediate cells) and lets the composite cross-feature gate CTV-V15 reason about composite ownership.

---

## §4 Closed enums (TVL_002 V1+30d+)

### 4.1 CompositeJourneyStatus (4 V1+30d+; closed)

```rust
pub enum CompositeJourneyStatus {                           // closed; per-composite-journey lifecycle
    Active,                                                 // in progress
    Arrived,                                                // reached destination_cell_id
    Canceled,                                               // self-cancel or admin cancel
    Stranded,                                               // re-plan failed / cap hit / under-provisioned after re-plan
}
```

TVL_002 reuses TVL_001's `TravelMode`, `TravelInitiator`, `TravelDirection`, and `TravelStatus` enums unchanged — no new mode/initiator/direction variants. `PlannedSegment` is a struct, not an enum.

---

## §5 Composite journey lifecycle

### 5.1 `CompositeTravel:Initiate` event flow

```
Actor (PC OR Tracked NPC) issues CompositeTravel:Initiate { destination_cell_id, mode=OnFoot }
(after confirming the read-only composite_travel_plan preview — §5.5):
  ↓ EVT-T1 Submitted validator pipeline:
    AuthorizationGate: actor exists in EF_001 + actor.tracking_tier ≥ Tracked (CTV-V1) → pass.
    SchemaGate: mode == OnFoot V1+30d+ (CTV-V9) + world_geometry.schema_version ≥ 3 (CTV-V11) → pass.
    ReferentialIntegrityGate:
      - actor.current_cell_id resolves in wg.cells; destination_cell_id resolves in wg.cells (CTV-V4)
      - destination_cell_id != actor.current_cell_id (CTV-V6)
      - actor has no Active composite_journey row (CTV-V3 one-composite-per-actor)
      - actor has no Active actor_travel_state row (CTV-V14 — cannot start composite while mid-atomic-travel)
      - actor.bodyorsoul_form != BodyOrSoul::Soul (CTV-V8 — soul-form excluded, mirrors TVL-V7)
      - actor and destination_cell in same continent channel (CTV-V10 — mirrors TVL-V15 atomic-channel discipline)
      → all pass.
  ↓ Dijkstra over wg.routes (edge weight = route.distance_units; bidirectional routes both directions;
    OnFoot-incompatible routes — SeaLane — excluded from the graph V1+30d+):
      - no path origin → destination → REJECT travel.no_route_to_destination (CTV-V5)
      - path resolved → plan: Vec<PlannedSegment> built; plan.len() ≤ 20 (CTV-V12) → pass
  ↓ Whole-journey provisions check (CTV-V7): Σ food_cost / Σ water_cost over plan vs actor.resource_inventory →
    insufficient → REJECT travel.composite_insufficient_provisions.
  ↓ EVT-T3 Derived emitted: composite_journey row created — status=Active, current_segment_index=0,
    plan frozen, total_distance_units + total_provisions_consumed computed,
    initiated_at_fiction_time = actor.actor_clock, expected_arrival_fiction_time computed,
    cancel_requested=false, replan_count=0, active_segment_journey_id=None.
  ↓ EVT-T3 Derived cascade: RES_001 resource_inventory.food/.water deducted by total_provisions_consumed
    (whole-journey pre-pay — Consumable possession deduction, TVL_001 HIGH-4 semantic).
  ↓ EVT-T3 Derived cascade: segment 0 initiated — see §5.2.
```

### 5.2 Segment initiation (composite handler EVT-T3 cascade)

```
Composite handler initiates plan[current_segment_index]:
  ↓ Re-run TVL_001 segment validators inline (TVL-V1 route-exists / TVL-V2 actor-at-from-cell /
    TVL-V3 direction-bidirectional / TVL-V9 mode-route-compat / TVL-V10 route-layer-active /
    TVL-V13 to-cell-resolves / TVL-V15 channel-bound):
      - all pass → EVT-T3 Derived: actor_travel_state row created (status=Active, progress_fraction=0.0,
        composite_journey_id = Some(this composite), initiator inherited).
        NOTE: per-segment provisions are NOT re-deducted — the whole journey was pre-paid at §5.1.
        The segment's actor_travel_state.provisions_consumed records the segment share for audit/refund only.
        composite_journey.active_segment_journey_id = Some(new journey_id).
      - any validator fails (e.g., route removed since plan-freeze) → trigger re-plan (§5.4).
  ↓ Per-turn Scheduled:TravelTick advances the segment exactly as TVL_001 §5.2 (selective TDIL clock
    advancement actor_clock + body_clock; realm_clock PL_001-owned; soul_clock preserved).
```

### 5.3 Segment handoff (fired by a segment's `Travel:Arrive`)

```
When the active segment's actor_travel_state transitions Active → Arrived (progress_fraction reaches 1.0):
  ↓ TVL_001 Travel:Arrive cascade runs — for ANY segment with composite_journey_id = Some(..) the
    cascade defers ALL hospitality/Exhausted handling to the composite handler (TVL_001 closure-pass
    behavior — CTV-Q1); the TVL_001 cascade does NOT branch on intermediate-vs-final (MED-3 fix). The
    composite handler decides below: intermediate cell → smart overnight stop; final cell → standard.
  ↓ Composite handler segment-handoff EVT-T3 cascade:
    plan[current_segment_index].traversed = true.
    actor.current_cell_id = segment.to_cell_id (EF_001 cascade — TVL_001 standard).
    active_segment_journey_id = None.
    ↓ Smart overnight stop at the arrival cell (intermediate only — skipped at destination):
      settlement = wg.settlements.find(s | s.cell_id == arrival_cell_id);
      if settlement.role ∈ {Village, Town, City, Capital}:
        auto-rest — actor.wakeful_duration = 0; narration tag "intermediate-rest-at-inn"; no Exhausted.
      else (Hamlet / Fortress / no settlement):
        outdoor camp — standard TVL_001 §5.3 Exhausted check (wakeful_duration > 16h → magnitude 3;
        > 24h → magnitude 5; PL_006 StackPolicy::Replace); narration tag "intermediate-outdoor-camp".
    ↓ if cancel_requested == true:
        status = Canceled; proportional provisions refund for un-traversed segments (§5.6); STOP.
    ↓ else if current_segment_index + 1 == plan.len():
        status = Arrived; actor reached destination_cell_id; EVT-T6 Travel:JourneyNarration arrival
        narration; STOP.  (Destination-cell hospitality is the standard TVL_001 §5.3 check — the
        destination is a real arrival, not an intermediate stop.)
    ↓ else:
        current_segment_index += 1;
        initiate plan[current_segment_index] immediately within this same handoff cascade (§5.2) —
        no inter-segment turn gap (HIGH-3 fix). The rest beat is the wakeful_duration reset above,
        not a fiction-time delay; per CTV-Q4 the gap was only ever a sequencing artifact.
```

### 5.4 Re-plan fallback

```
Triggered at §5.2 when plan[current_segment_index] fails a TVL_001 segment validator
(dominant cause: admin RemoveRoute on a future planned segment's route — TVL-V14 protects only the
active segment's route, not planned-but-not-yet-active ones):
  ↓ if replan_count >= 3 (CTV-V13 cap) → status = Stranded (informational reason
    travel.composite_replan_cap_exceeded); refund per §5.6; STOP.
  ↓ Dijkstra from actor.current_cell_id → destination_cell_id over the CURRENT wg.routes graph:
      - no path → status = Stranded (informational reason travel.no_route_to_destination — the same
        condition CTV-V5 catches at initiate, re-surfaced here); refund per §5.6; STOP.
      - path found → splice: plan = plan[0..current_segment_index] (traversed prefix) ++ new tail;
        replan_count += 1; recompute total_distance_units + expected_arrival_fiction_time.
  ↓ Re-check provisions (HIGH-1 fix — the actor's on-hand inventory counts, not just pre-pay):
      remaining-needed  = Σ provisions over the un-traversed NEW tail.
      remaining-pre-pay = total_provisions_consumed − Σ(traversed-segment consumption).
      available         = remaining-pre-pay + the food/water still on hand in actor.resource_inventory.
      if available < remaining-needed → status = Stranded (informational reason
        travel.composite_insufficient_provisions); refund per §5.6; STOP.
      else if remaining-needed > remaining-pre-pay → deduct the shortfall from actor.resource_inventory
        (Consumable possession deduction — same cascade kind as §5.1); total_provisions_consumed += shortfall.
  ↓ initiate the new plan[current_segment_index] (§5.2).
```

### 5.5 `composite_travel_plan` read-only preview query

```
Client (PC travel UI) calls GET composite_travel_plan { actor_id, destination_cell_id, mode=OnFoot }
via api-gateway-bff → travel-service:
  ↓ travel-service runs the SAME Dijkstra + validation as §5.1 BUT mutates nothing:
      - returns { reachable: bool, segment_count, total_distance_units, expected_duration,
        total_food_cost, total_water_cost, intermediate_settlement_names: Vec<String>,
        provisions_sufficient: bool, path: Vec<PlannedSegmentPreview> }
  ↓ Client renders the preview; player confirms → client emits CompositeTravel:Initiate (§5.1).
  ↓ The preview is advisory — §5.1 re-runs Dijkstra + all validators authoritatively at initiate
    (the graph may have changed between preview and confirm; the preview never gates correctness).
```

### 5.6 Cancel paths

```
Self-cancel — CompositeTravel:Cancel { composite_journey_id } (EVT-T1, PC or Tracked NPC):
  ↓ CTV-V16 composite-cancelable: composite exists, owned by actor, status == Active → pass.
  ↓ EVT-T3 Derived: cancel_requested = true. The currently-active atomic segment runs to completion
    (you cannot teleport off a road mid-segment); at that segment's handoff (§5.3) the cancel_requested
    check fires BEFORE the next segment is initiated, so status = Canceled and no further segment is
    travelled. Because handoff initiates the next segment in-cascade (HIGH-3 fix — no inter-segment
    turn gap), there is no window in which a cancel could slip past the handoff check and trigger an
    unwanted extra leg (MED-2 — resolved structurally by the HIGH-3 fix, not a separate guard).

Admin cancel — Forge:CancelCompositeJourney { composite_journey_id, reason } (EVT-T8, Forge admin):
  ↓ Standard admin capability per ADMIN_ACTION_POLICY.
  ↓ EVT-T3 Derived: the active segment's actor_travel_state.status = Canceled (immediate); composite
    status = Canceled. Actor remains at its current cell (current segment's last computed position is
    treated as the segment from_cell — no partial-segment teleport).

Provisions refund (self-cancel + admin cancel + Stranded): refund = total_provisions_consumed −
Σ(provisions attributable to traversed segments), where a traversed segment's provisions =
food_per_league × its distance_units (food) and water_per_league × its distance_units (water).
Credited back to actor.resource_inventory food/water. This subtracts the actor's ACTUAL consumption
rather than ratioing un-traversed distance against total_distance_units — correct even after a re-plan
changed total_distance_units (HIGH-2 fix: the pre-pay total and the post-re-plan distance are computed
from different plans, so a ratio would mis-refund). Inherits the proportional spirit of TVL_001 TVL-Q3
but credits resource_inventory (Consumable possessions), not vital_pool — the TVL_001 closure pass
corrects TVL-Q3's stale "vital_pool" wording per CTV-Q1.
```

---

## §6 Multiverse inheritance

TVL_002 V1+30d+ inherits the standard DP-Ch + EVT-T2 snapshot-fork contract:

- At snapshot fork: parent's Active `composite_journey` rows copied bit-exactly into the child — `plan`, `current_segment_index`, `replan_count`, `cancel_requested` all preserved; the child's referenced `actor_travel_state` segment row is copied by TVL_001's own fork contract.
- Child and parent advance segment ticks independently; the child's re-plans do not cascade to the parent and vice-versa.
- L1/L2 cascade: no L2 layer — `composite_journey` is reality-local per-actor runtime state with no canonical-author declaration (same as TVL_001 `actor_travel_state`).
- Determinism: same `(actor_seed, origin_cell, destination_cell, fiction_clock_at_initiate, wg.routes graph state)` → bit-identical `plan` (Dijkstra is deterministic given a stable tie-break — see CTV-Q2) and bit-identical traversal sequence.

Edge case — route removed in only one fork: a `RemoveRoute` applied in the child but not the parent makes the child's next-segment validation fail → child re-plans independently; the parent's composite is unaffected. Both remain replay-deterministic within their own event streams.

---

## §7 Validation pipeline (TVL_002 V1+30d+ additive validators)

| Validator | Stage | Reject rule_id |
|---|---|---|
| **CTV-V1** actor-tracked | `CompositeTravel:Initiate` AuthorizationGate | `travel.actor_untracked_excluded` (reused — actor.tracking_tier ∉ {Pc, TrackedMajor}) |
| **CTV-V2** actor-at-origin | `CompositeTravel:Initiate` ReferentialIntegrityGate | `travel.composite_actor_not_at_origin` (origin_cell_id != actor.current_cell_id) |
| **CTV-V3** one-composite-per-actor | `CompositeTravel:Initiate` ReferentialIntegrityGate | `travel.actor_already_in_composite_journey` (existing Active composite_journey for actor) |
| **CTV-V4** cells-resolve | `CompositeTravel:Initiate` ReferentialIntegrityGate | `travel.composite_cell_unknown` (origin or destination cell ∉ wg.cells) |
| **CTV-V5** path-resolves | `CompositeTravel:Initiate` (Dijkstra) | `travel.no_route_to_destination` (no OnFoot-traversable path origin → destination) |
| **CTV-V6** destination-distinct | `CompositeTravel:Initiate` ReferentialIntegrityGate | `travel.composite_destination_is_origin` (destination_cell_id == origin_cell_id) |
| **CTV-V7** sufficient-provisions | `CompositeTravel:Initiate` ReferentialIntegrityGate | `travel.composite_insufficient_provisions` (resource_inventory food/water < whole-path Σ cost) |
| **CTV-V8** soul-form-excluded | `CompositeTravel:Initiate` ReferentialIntegrityGate | `travel.soul_form_no_physical_travel` (reused — actor.bodyorsoul_form == Soul) |
| **CTV-V9** mode-available-v1plus30d | `CompositeTravel:Initiate` SchemaGate | `travel.composite_mode_unavailable_v1plus30d` (mode != OnFoot V1+30d+) |
| **CTV-V10** destination-channel-bound | `CompositeTravel:Initiate` ChannelScope check | `travel.cross_channel_initiate_forbidden` (reused — destination cell not in actor's continent channel) |
| **CTV-V11** route-layer-activated | `CompositeTravel:Initiate` RealityBootstrapper post-check | `travel.route_layer_not_activated` (reused — world_geometry.schema_version < 3) |
| **CTV-V12** path-length-cap | `CompositeTravel:Initiate` (post-Dijkstra) | `travel.composite_path_too_long` (plan.len() > 20 V1+30d+) |
| **CTV-V13** replan-cap | Segment-handoff re-plan (§5.4) | `travel.composite_replan_cap_exceeded` (replan_count would exceed 3 → Stranded; informational) |
| **CTV-V14** no-active-atomic-journey | `CompositeTravel:Initiate` ReferentialIntegrityGate | `travel.actor_already_traveling` (reused — actor has an Active actor_travel_state from a manual TVL_001 journey) |
| **CTV-V15** manual-travel-blocked-during-composite | TVL_001 `Travel:Initiate` ReferentialIntegrityGate (cross-feature gate) | `travel.actor_in_composite_journey` (actor has an Active composite_journey; manual Travel:Initiate rejected — mirrors TVL-V14 cross-feature gate pattern) |
| **CTV-V16** composite-cancelable | `CompositeTravel:Cancel` ReferentialIntegrityGate | `travel.composite_not_cancelable` (composite_journey_id ∉ rows, not owned by actor, or status != Active) |
| **CTV-V17** plan-contiguity | `CompositeTravel:Initiate` + every re-plan apply (defensive) | `travel.composite_plan_discontinuous` (plan[i].to_cell != plan[i+1].from_cell, or endpoints mismatch — should be impossible per Dijkstra; defensive) |

ContentSafetyGate applied to LLM-generated arrival narration `content` via the TVL_001 `Travel:JourneyNarration` path (PII scrubber + injection scanner) — unchanged, no new surface.

---

## §8 Failure UX — `travel.*` namespace extension

TVL_002 V1+30d+ extends the existing `travel.*` RejectReason namespace owned by TVL_001 (composite travel is within the travel domain — no new namespace). **12 NEW V1+30d+ rule_ids** (10 player-meaningful + 2 defensive) + 5 reused TVL_001 ids.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d+) | English fallback | New? |
|---|---|---|---|---|---|
| `travel.composite_actor_not_at_origin` | user | `CompositeTravel:Initiate` | "Bạn không ở vị trí khởi hành đã khai báo." | "You are not at the declared origin cell." | NEW |
| `travel.actor_already_in_composite_journey` | user | `CompositeTravel:Initiate` | "Bạn đang trong một hành trình ghép. Hãy đến nơi hoặc hủy trước." | "You are already on a composite journey; arrive or cancel first." | NEW |
| `travel.composite_cell_unknown` | schema | `CompositeTravel:Initiate` | "Ô khởi hành hoặc ô đích không tồn tại." | "Origin or destination cell not found." | NEW |
| `travel.no_route_to_destination` | user | `CompositeTravel:Initiate` (Dijkstra) + segment-handoff re-plan (Stranded reason) | "Không có tuyến đường nào dẫn tới đích." | "No route reaches the destination." | NEW |
| `travel.composite_destination_is_origin` | user | `CompositeTravel:Initiate` | "Điểm đích trùng với điểm khởi hành." | "Destination equals the origin." | NEW |
| `travel.composite_insufficient_provisions` | user | `CompositeTravel:Initiate` + segment-handoff re-plan (Stranded reason) | "Không đủ lương thực hoặc nước cho cả hành trình." | "Insufficient food or water for the whole journey." | NEW |
| `travel.composite_mode_unavailable_v1plus30d` | user | `CompositeTravel:Initiate` | "Chế độ du hành ghép này chưa khả dụng (chỉ hỗ trợ đi bộ)." | "Composite travel mode not available (OnFoot only)." | NEW |
| `travel.composite_path_too_long` | user | `CompositeTravel:Initiate` | "Hành trình quá dài (vượt 20 chặng)." | "Journey too long (exceeds 20 segments)." | NEW |
| `travel.composite_replan_cap_exceeded` | schema | Segment-handoff re-plan | "Hành trình mắc kẹt — đã thử tính lại tuyến tối đa." | "Journey stranded — re-plan attempts exhausted." | NEW |
| `travel.actor_in_composite_journey` | user | TVL_001 `Travel:Initiate` (cross-feature gate) | "Bạn đang trong hành trình ghép — không thể bắt đầu chuyến lẻ." | "You are on a composite journey; cannot start a single-segment trip." | NEW |
| `travel.composite_not_cancelable` | user | `CompositeTravel:Cancel` | "Hành trình ghép không thể hủy (không tồn tại hoặc đã kết thúc)." | "Composite journey not cancelable (missing or already ended)." | NEW |
| `travel.composite_plan_discontinuous` | schema | `CompositeTravel:Initiate` / re-plan apply (defensive) | "Kế hoạch tuyến không liền mạch." | "Composite plan is discontinuous (defensive)." | NEW |
| `travel.actor_untracked_excluded` | schema | `CompositeTravel:Initiate` AuthorizationGate | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |
| `travel.soul_form_no_physical_travel` | user | `CompositeTravel:Initiate` | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |
| `travel.cross_channel_initiate_forbidden` | schema | `CompositeTravel:Initiate` | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |
| `travel.route_layer_not_activated` | schema | `CompositeTravel:Initiate` | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |
| `travel.actor_already_traveling` | user | `CompositeTravel:Initiate` (CTV-V14) | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |

(Of the 12 new ids, 10 are player-meaningful; the 2 defensive schema ids — `composite_replan_cap_exceeded` + `composite_plan_discontinuous` — are internal. `composite_replan_cap_exceeded`, `no_route_to_destination`, and `composite_insufficient_provisions` are also surfaced as the informational *Stranded reason* at segment-handoff re-plan, not only as initiate-time rejects — see §5.4.)

i18n: V1+30d+ ships `I18nBundle` per the RES_001 §2 cross-cutting contract from day one.

---

## §9 Cross-service handoff

| Service | Role | V1+30d+ status |
|---|---|---|
| **travel-service** | Authoritative owner of `composite_journey` aggregate; runs Dijkstra; applies `CompositeTravel:Initiate`/`Cancel`; orchestrates per-segment `actor_travel_state` initiation + segment handoff + re-plan. Also owns the `actor_travel_state` aggregate (TVL_001) — composite + atomic travel co-located in one service. | V1+30d+ |
| **world-service** | Reads `world_geometry.routes` (Dijkstra graph) + `world_geometry.settlements` (intermediate-stop hospitality) | V1+30d+ |
| **api-gateway-bff** | Routes `CompositeTravel:Initiate`/`Cancel` POSTs; serves the read-only `composite_travel_plan` preview GET; player composite-travel UI GETs `composite_journey` for in-flight display | V1+30d+ UI |
| **chat-service** (S9) | Read-only — `[TRAVEL_CONTEXT]` already covers in-flight journeys (TVL_001 TVL-20); composite adds `composite_progress` (segment i of N) to the same sub-section; reuses `Travel:JourneyNarration` EVT-T6 | V1+30d+ |
| **auth-service** | No new capability for `CompositeTravel:Initiate`/`Cancel` (regular gameplay action). `Forge:CancelCompositeJourney` uses the existing Forge admin capability per ADMIN_ACTION_POLICY — no new claim | V1+30d+ unchanged |
| **knowledge-service** | Reads composite-journey history for actor travel-pattern knowledge graph (planned V1+ activation per CLAUDE.md two-layer pattern) | Not V1+30d+ |

**No new service.** TVL_002 lives in `travel-service` (the NEW V1+30d service TVL_001 introduced) — composite orchestration and atomic-segment ownership are the same bounded context.

---

## §10 Composition with foundation siblings & TVL_001

| Sibling | Composition with TVL_002 |
|---|---|
| **TVL_001 Travel** | **Parent.** Every composite segment is a TVL_001 atomic journey — `actor_travel_state`, `Scheduled:TravelTick`, selective TDIL clocks, hospitality, validators all inherited. TVL_002 adds: the orchestration aggregate; `actor_travel_state.composite_journey_id` additive field (CTV-Q1); cross-feature gate CTV-V15 on TVL_001 `Travel:Initiate`; intermediate-cell hospitality deferral (CTV-Q1 closure-pass behavior). |
| **GEO_004 ROUTE_001** | **Primary substrate** — the Route graph is the Dijkstra input. Edge weight = `route.distance_units`; `route.is_bidirectional` decides which `TravelDirection` a `PlannedSegment` uses. ROUTE-V8 pair-uniqueness + cell-pair discipline make the graph well-formed. TVL-V14 (`route_in_use_by_journey`) protects only the active segment's route — TVL_002's re-plan fallback (§5.4) handles removal of *planned* segment routes. |
| **GEO_003 SET_001** | Smart overnight stops read `Settlement.role` at each intermediate cell — inn-bearing roles (Village/Town/City/Capital) trigger auto-rest; Hamlet/Fortress/no-settlement trigger outdoor camp + the TVL_001 Exhausted check. |
| **GEO_002 POL_001 / GEO_001** | Journey-narrative grounding only — `[TRAVEL_CONTEXT]` joins the composite path's cells → province/state/culture/biome for arrival + intermediate-stop narration texture. No schema integration. |
| **TDIL_001** | Per-segment clock advancement is TVL_001's unchanged — `actor_clock + body_clock` advance per tick; `realm_clock` PL_001-owned; `soul_clock` preserved. `expected_arrival_fiction_time` sums segment durations + intermediate rest beats. TDIL-A5 atomic-channel discipline enforced at initiate (CTV-V10) — a composite path may not cross continent channels V1+30d+. |
| **RES_001** | Whole-journey provisions pre-paid at `CompositeTravel:Initiate` (Consumable `resource_inventory` deduction — TVL_001 HIGH-4 semantic). Proportional refund on cancel/strand. `vital_pool` body-state never touched by TVL_002 (consistent with TVL_001). |
| **PL_006 Status Effects** | Exhausted applied at no-inn intermediate stops (and at the destination) via TVL_001 §5.3 — `StatusFlag::Exhausted` magnitude 3 (16–24h) / 5 (>24h), `StackPolicy::Replace`. Auto-rest at inn-bearing stops resets `wakeful_duration` so Exhausted does not pile across a multi-day composite journey. |
| **EF_001 Entity Foundation** | `actor.current_cell_id` written at every segment handoff (TVL_001 cascade). `entity.travel_journey_id` reused per-segment unchanged — **no new EF_001 field** (the new field is on `actor_travel_state`, not `entity_binding`). |
| **AIT_001** | Tracked tier discipline inherited — PC + Tracked NPC parity; Untracked NPCs excluded (no `composite_journey` row, no `CompositeTravel:Initiate`). |
| **PL_001 Continuum** | Turn-boundary fire — segment ticks use TVL_001's `Scheduled:TravelTick`; segment handoff initiates the next segment in-cascade with no inter-segment turn gap (HIGH-3 fix /review-impl 2026-05-16 — composite adds no scheduled mechanism of its own). No PL_001 schema change. |
| **NPC_002 Chorus** | Tracked NPC composite travel — Chorus may propose `CompositeTravel:Initiate` (a single high-level intent instead of N atomic `Travel:Initiate` emissions — a strict win for NPC-driven travel). V2+ richer NPC re-plan/cancel autonomy. |

---

## §11 RealityManifest extension

**No new RealityManifest field.** TVL_002 V1+30d+ configuration lives within existing structures:

- Re-plan cap (3) + path-length cap (20 segments) — V1+30d+ hardcoded constants in `travel-service` config; author-tunable V2+ per CTV-D7.
- Provisions cost — inherited entirely from TVL_001 (`food_per_league`/`water_per_league`); TVL_002 only *sums* over the path, adds no new cost knob.
- Dijkstra cost function — V1+30d+ minimizes total `distance_units`; weighted-cost variants (safety/toll/road-quality) deferred V2+ CTV-D6.

Bootstrap order: TVL_002 V1+30d+ activates AFTER TVL_001 V1+30d ships (`actor_travel_state` aggregate must exist + the `composite_journey_id` closure-pass field landed). Realities pre-TVL_001-ship cannot initiate composite travel — the same `route_layer_not_activated` reject covers both (composite requires the Route layer + the atomic-travel substrate).

V1+30d+ feature-flag: `services/travel-service` config `composite_travel_enabled: bool` (default true V1+30d+; false leaves only TVL_001 atomic travel). Mid-life feature-flag flip on an existing reality FORBIDDEN per `generator_pipeline_version` discipline.

---

## §12 Sequences

### 12.1 PC composite-travels Khai Phong → Lâm An (2 segments via Tương Dương)

```
lý_minh at cell:khai_phong. Client calls composite_travel_plan { destination=cell:lam_an, mode=OnFoot }:
  ↓ travel-service Dijkstra → path [khai_phong →(Imperial Highway Road)→ tuong_duong
    →(Southern Road)→ lam_an]; returns segment_count=2, total_distance_units=24+18=42,
    total_food_cost=42, total_water_cost=84, intermediate=[Tương Dương], provisions_sufficient=true.
  ↓ Client renders preview; lý_minh confirms.
lý_minh issues CompositeTravel:Initiate { destination_cell_id=cell:lam_an, mode=OnFoot }:
  ↓ EVT-T1 validators: CTV-V1 (Pc tracked) / CTV-V2 (at khai_phong) / CTV-V3 (no Active composite) /
    CTV-V14 (no Active atomic journey) / CTV-V8 (Body form) / CTV-V10 (same channel) / CTV-V5
    (Dijkstra path resolves, 2 segments) / CTV-V12 (2 ≤ 20) / CTV-V7 (food 50 ≥ 42, water 100 ≥ 84) → pass.
  ↓ EVT-T3: composite_journey created — status=Active, current_segment_index=0, plan=[seg0, seg1],
    total_distance_units=42, total_provisions_consumed={food:42, water:84}, replan_count=0.
  ↓ Cascade RES_001: resource_inventory.food 50→8, water 100→16 (whole-journey pre-pay).
  ↓ Cascade: segment 0 initiated — actor_travel_state row created, composite_journey_id=Some(..),
    progress_fraction=0.0; per-segment provisions NOT re-deducted.
  ↓ Scheduled:TravelTick ×6 → segment 0 progress 1.0 → Travel:Arrive at tuong_duong.
  ↓ Segment handoff (within segment 0's arrival cascade): seg0.traversed=true; current_cell_id=tuong_duong;
    smart overnight stop — Tương Dương is Capital → inn available → auto-rest, wakeful_duration=0, no
    Exhausted. cancel_requested=false; next segment exists → current_segment_index=1; segment 1
    initiates immediately in this same cascade (no turn gap).
  ↓ Scheduled:TravelTick advances segment 1 → Travel:Arrive at lam_an.
  ↓ Segment handoff: seg1.traversed=true; current_cell_id=lam_an; current_segment_index+1==plan.len()
    → composite status=Arrived; EVT-T6 Travel:JourneyNarration arrival narration.
```

### 12.2 Re-plan fallback — admin removes a planned segment's route mid-journey

```
lý_minh's composite (§12.1) is at segment 0 (en route khai_phong → tuong_duong, progress 0.5).
Forge admin emits RemoveRoute { route_id: southern_road_tuong_duong_lam_an } (the planned segment 1):
  ↓ TVL-V14 route_in_use_by_journey: queries actor_travel_state for Active rows on this route_id —
    segment 1 has NOT initiated yet (no Active row) → TVL-V14 does NOT block → RemoveRoute SUCCEEDS.
  ↓ Segment 0 completes; handoff initiates segment 1 (§5.2):
    TVL-V1 route-exists for southern_road_tuong_duong_lam_an → FAILS (route removed) → trigger re-plan.
  ↓ §5.4 re-plan: replan_count 0 < 3 → Dijkstra tuong_duong → lam_an over current graph →
    finds [tuong_duong →(Mountain Detour MountainPass)→ son_trai →(River Road)→ lam_an], distance 30.
  ↓ Splice: plan = [seg0 (traversed)] ++ [new seg1, new seg2]; replan_count=1;
    total_distance_units recomputed 24+30=54; expected_arrival_fiction_time recomputed.
  ↓ Provisions re-check (HIGH-1 — on-hand inventory counts): traversed seg0 consumed food 24 / water 48;
    remaining pre-pay = 42−24=18 food / 84−48=36 water; lý_minh's resource_inventory still holds food 8 /
    water 16 (the surplus left after the §12.1 pre-pay). available food = 18 + 8 = 26; new tail needs 30
    → 26 < 30 → INSUFFICIENT even with the inventory top-up → status=Stranded (composite_insufficient_provisions).
  ↓ Refund per §5.6: total_provisions_consumed (42 food / 84 water) − traversed seg0 consumption
    (24 / 48) = 18 food / 36 water credited back to resource_inventory; lý_minh sits at tuong_duong;
    UI surfaces "Hành trình mắc kẹt — không đủ lương thực cho tuyến thay thế."
```

### 12.3 Self-cancel takes effect at the next segment boundary

```
tieu_long_nu on a 4-segment composite, currently mid-segment-1 (progress 0.3).
She issues CompositeTravel:Cancel { composite_journey_id }:
  ↓ CTV-V16: composite exists, owned, status==Active → pass.
  ↓ EVT-T3: cancel_requested=true. Segment 1 KEEPS RUNNING (cannot teleport off the road).
  ↓ Segment 1 reaches Travel:Arrive at its to_cell; segment handoff sees cancel_requested==true →
    status=Canceled; proportional refund for un-traversed segments 2+3; tieu_long_nu stops at
    segment 1's to_cell. Segments 2 and 3 never initiate.
```

### 12.4 No route to destination — rejected at initiate

```
A PC on an island with no SeaLane-free path to a mainland cell issues CompositeTravel:Initiate:
  ↓ CTV-V5: Dijkstra over OnFoot-traversable routes (SeaLane excluded V1+30d+) → no path →
    REJECT travel.no_route_to_destination. No aggregate created; provisions untouched.
  ↓ UI: "Không có tuyến đường nào dẫn tới đích." — player must use atomic ByBoat travel (TVL_003 V1+30d+).
```

---

## §13 Acceptance criteria

15 V1+30d+-testable acceptance scenarios. LOCK granted when ≥10 pass integration tests against the `travel-service` reference impl + TVL_001 + ROUTE_001 + SET_001 + TDIL_001 fixtures.

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-TVL-16** | PC issues `CompositeTravel:Initiate` to a reachable destination; sufficient provisions → `composite_journey` row created status=Active, plan frozen with N≥2 contiguous segments, whole-journey provisions deducted from `resource_inventory`, segment 0's `actor_travel_state` created with `composite_journey_id=Some(..)`. | — |
| **AC-TVL-17** | Segment ticks advance; segment 0 reaches `Arrived` → handoff sets `traversed=true`, advances `current_segment_index`, initiates segment 1 at the next turn-boundary. | — |
| **AC-TVL-18** | Final segment reaches `Arrived` → composite `status=Arrived`; `actor.current_cell_id == destination_cell_id`. | — |
| **AC-TVL-19** | Intermediate stop at an inn-bearing settlement (Village/Town/City/Capital) → auto-rest: `wakeful_duration` reset to 0, no Exhausted, narration tag `intermediate-rest-at-inn`. | — |
| **AC-TVL-20** | Intermediate stop at a Hamlet (no inn) with `wakeful_duration > 16h` → outdoor camp + `PL_006 StatusFlag::Exhausted` applied (TVL_001 §5.3 path). | — |
| **AC-TVL-21** | `CompositeTravel:Initiate` to an unreachable destination → reject; no aggregate created. | `travel.no_route_to_destination` |
| **AC-TVL-22** | `CompositeTravel:Initiate` with `resource_inventory` short of whole-path provisions → reject; provisions untouched. | `travel.composite_insufficient_provisions` |
| **AC-TVL-23** | Second `CompositeTravel:Initiate` while one is Active → reject. | `travel.actor_already_in_composite_journey` |
| **AC-TVL-24** | Manual TVL_001 `Travel:Initiate` while a composite is Active → reject (cross-feature gate CTV-V15). | `travel.actor_in_composite_journey` |
| **AC-TVL-25** | `CompositeTravel:Initiate` with `destination_cell_id == origin` → reject. | `travel.composite_destination_is_origin` |
| **AC-TVL-26** | Admin `RemoveRoute` on a *future* planned segment's route → at that segment's handoff, re-plan succeeds; the new tail is covered by remaining pre-pay (topped up from `resource_inventory` if the detour is longer, growing `total_provisions_consumed`) → plan spliced, `replan_count=1`, journey continues. | — |
| **AC-TVL-27** | Re-plan triggered; no alternate path exists, OR the new tail's cost exceeds remaining pre-pay + on-hand `resource_inventory`, OR the re-plan cap (3) is hit → composite `status=Stranded`; refund = pre-pay − traversed-segment consumption (§5.6). | `composite_replan_cap_exceeded` / `no_route_to_destination` / `composite_insufficient_provisions` (per strand cause) |
| **AC-TVL-28** | `CompositeTravel:Cancel` mid-segment → `cancel_requested=true`; current segment runs to completion; composite closes `Canceled` at the next handoff; un-traversed provisions refunded proportionally. | — |
| **AC-TVL-29** | `composite_travel_plan` query returns path + total distance + ETA + provisions cost + intermediate settlements; mutates no aggregate (verified by event-log diff). | — |
| **AC-TVL-30** | Snapshot fork mid-composite (segment 1 of 3) → child inherits `composite_journey` + active `actor_travel_state` bit-exactly; child + parent advance segments independently; a `RemoveRoute` in the child re-plans only the child. | — |

---

## §14 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **CTV-D1** | Encounter interaction with composite journeys (an encounter pausing a segment pauses the composite) | V1+30d+ | TVL_004 Travel Encounters attaches at the per-segment `actor_travel_state` level; composite is encounter-agnostic by design. Coordination doc-only at TVL_004 design time. |
| **CTV-D2** | Mid-journey re-supply at market settlements (composite path through a market re-provisions) | V2+ | Requires V2+ economy substrate. V1+30d+ is whole-journey pre-pay only. |
| **CTV-D3** | Composite-journey waypoints (player declares ordered must-visit intermediate cells, not just a destination) | V1+30d+ | Dijkstra-with-waypoints (concatenated shortest paths). V1+30d+ is single-destination only. |
| **CTV-D4** | Actor pause/resume of a composite journey (vs. cancel) | V1+30d+ | V1+30d+ ships cancel only; pause/resume needs a `Paused` status + resume-from-cell semantics. |
| **CTV-D5** | Multi-modal composite paths (OnFoot land segments + ByBoat SeaLane segments in one journey) | V1+30d+ | Requires TVL_003 Mount/Vehicle Travel. V1+30d+ all segments share one `TravelMode`; SeaLane routes excluded from the OnFoot Dijkstra graph. |
| **CTV-D6** | Weighted-cost Dijkstra (minimize safety-risk / toll / travel-time instead of raw distance) | V2+ | Requires V2+ route-safety / economy substrates. V1+30d+ minimizes total `distance_units`. |
| **CTV-D7** | Author-tunable re-plan cap + path-length cap via `creative_seed` | V2+ | V1+30d+ hardcoded (3 re-plans, 20 segments). |
| **CTV-D8** | Group/party composite travel (a party traversing a composite path together) | V1+30d+ | Requires TVL_005 party-formation aggregate. |
| **CTV-D9** | Admin `Forge:RerouteCompositeJourney` (admin forces a specific alternate path) | V2+ | V1+30d+ admin can only cancel; re-plan is automatic. |

---

## §15 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **CTV-Q1** | `actor_travel_state.composite_journey_id: Option<CompositeJourneyId>` additive field — does it bump `actor_travel_state` schema_version, and what else does the TVL_001 closure pass cover? | V1+30d+: YES, bumps `actor_travel_state` schema_version per I14 (default-tolerant readers: pre-bump rows = `None`). The TVL_001 closure pass at TVL_002 ship — mirroring the EF_001 `travel_journey_id` precedent (TVL-Q1) — covers four items: **(1)** the additive `composite_journey_id` field + schema_version bump; **(2)** `Travel:Arrive` defers ALL hospitality/Exhausted handling for any segment with `composite_journey_id = Some(..)` to the composite handler — no intermediate-vs-final branching inside the TVL_001 cascade (MED-3 fix); **(3) TVL-Q3 erratum** — TVL_001 TVL-Q3 still reads "refunded to RES_001 vital_pool", stale since the TVL_001 HIGH-4 fix moved provisions to `resource_inventory`; the closure pass corrects TVL-Q3 to `resource_inventory` (TVL_002 §5.6 already uses the correct target — LOW-3 fix); **(4) Canceled end-position ratification** — TVL_001 leaves an atomic journey's `Canceled` end-position unspecified; the closure pass ratifies snap-to-`from_cell` (TVL_002 §5.6 admin-cancel assumes this — LOW-4 fix). |
| **CTV-Q2** | Dijkstra tie-break — when two paths have equal total `distance_units`, which is chosen? Replay-determinism requires a stable rule. | V1+30d+: deterministic tie-break by lexicographic order of the segment `route_id` sequence (`RouteId` is a stable Ulid-derived newtype). Documented as a CI replay-determinism gate. |
| **CTV-Q3** | Should TVL-V14 (`route_in_use_by_journey`) be *extended* to also block removal of routes in any Active composite's *planned* (not-yet-traversed) segments? | V1+30d+: NO — extending TVL-V14 to planned segments would let a single long composite journey veto admin route edits across a wide swath of the graph (operationally unacceptable). The re-plan fallback (§5.4) is the deliberate trade: admins keep edit freedom; composites self-heal or strand. Re-examine V2+ if stranding proves too frequent in playtest. |
| **CTV-Q4** | Should there be an inter-segment turn gap to model "rest" between segments? | V1+30d+: NO (HIGH-3 fix /review-impl 2026-05-16) — segment N+1 initiates in-cascade at segment N's handoff, with no turn gap. The rest beat is modeled entirely by the `wakeful_duration` reset at inn-bearing intermediate stops (§5.3), not by a fiction-time delay. An earlier draft deferred the next segment "to the next turn-boundary", but that contradicted §2.5 (composite adds no scheduled mechanism) and left the deferral with nothing to fire it — see HIGH-3. V2+ may add a configurable intermediate-stop dwell time, which would then need its own EVT-T5 scheduled mechanism. |
| **CTV-Q5** | `composite_travel_plan` preview staleness — the graph can change between preview and `CompositeTravel:Initiate`. | V1+30d+: accepted — the preview is advisory; §5.1 re-runs Dijkstra + all validators authoritatively at initiate. A stale preview at worst yields a reject or a slightly different (still valid) plan; it never gates correctness. |
| **CTV-Q6** | Storage representation — monolithic `Vec<CompositeJourney>` per reality vs. per-actor SQL table? | V1+30d+: sparse aggregate per `(actor_id, composite_journey_id)`, event-sourced via T2/Reality discipline (same as TVL_001 `actor_travel_state` TVL-Q7). SQL denormalization V2+ if STRAT_001 needs cross-actor composite-journey queries. |
| **CTV-Q7** | Tracked NPC composite travel — does Chorus emit `CompositeTravel:Initiate` directly, or a higher-level "go to X" intent that travel-service lowers? | V1+30d+: Chorus emits `CompositeTravel:Initiate` directly (the destination cell is resolvable from NPC narrative intent). Richer NPC re-plan/cancel autonomy deferred V2+ per NPC_002. |

---

## §16 Cross-references

- [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — catalog; `TVL-*` namespace; TVL_002 sub-section
- [`_index.md`](_index.md) — folder index; TVL_002 row added 2026-05-16
- [`TVL_001 Travel`](TVL_001_travel.md) — parent; atomic single-segment travel
- [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) — Route graph (Dijkstra input)
- [`GEO_003 SET_001`](../00_geography/GEO_003_settlement_generator.md) — Settlement.role for intermediate-stop hospitality
- [`TDIL_001`](../03_actor_substrate/TDIL_001_time_dilation_foundation.md) — per-segment selective clock advancement
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) — whole-journey provisions pre-pay
- [`PL_006`](../04_play_loop/PL_006_status_effects.md) — Exhausted at no-inn intermediate stops
- [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) — Tracked tier discipline
- [`EF_001`](../03_actor_substrate/EF_001_entity_foundation.md) — `entity.travel_journey_id` reused per-segment (no new EF_001 field)
- [`PL_001 Continuum`](../04_play_loop/PL_001_continuum.md) — turn-boundary fire for segment ticks + handoff
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — NEW `composite_journey` aggregate row
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — NEW EVT-T1 sub-types `CompositeTravel:Initiate`/`CompositeTravel:Cancel` + `travel.*` namespace composite rule_ids recorded in §1.4 (no separate EVT-T1 sub-type registry table exists); NEW EVT-T8 sub-shape `Forge:CancelCompositeJourney` registered in §4

---

## §17 Implementation readiness

**Design layer (this commit):** ✅ NEW `composite_journey` aggregate schema + 1 cross-feature additive field on `actor_travel_state` + 1 V1+30d+ closed enum + 17 validator slots (CTV-V1..V17) + 12 `travel.*` rule_ids (10 player-meaningful + 2 defensive) + 9 deferrals + 7 open questions + Dijkstra plan-freeze + re-plan fallback + smart-overnight-stop discipline + whole-journey provisions pre-pay + read-only `composite_travel_plan` preview + cross-feature coordination with TVL_001/ROUTE_001/SET_001/TDIL_001/RES_001/PL_006/EF_001/AIT_001 + 15 acceptance scenarios — all declared.

**Implementation phase (V1+30d+):** 📦 `composite_journey` aggregate + apply_delta logic in `travel-service`; Dijkstra path solver (deterministic tie-break per CTV-Q2); segment-handoff orchestration + re-plan fallback; TVL_001 closure pass (4 items per CTV-Q1 — `actor_travel_state.composite_journey_id` additive field + schema_version bump; `Travel:Arrive` defers all hospitality for composite segments to the composite handler; TVL-Q3 vital_pool→resource_inventory erratum; atomic-journey `Canceled` end-position ratified to snap-to-`from_cell`); cross-feature gate CTV-V15 added to TVL_001 `Travel:Initiate` pipeline; `composite_travel_plan` preview query endpoint; chat-service `[TRAVEL_CONTEXT]` `composite_progress` extension; CI gates: replay-determinism (same seed + origin + destination + graph → byte-identical plan + traversal), apply_delta total-function for `CompositeTravel:Initiate`/`Cancel` + segment handoff + re-plan, Dijkstra tie-break determinism gate, plan-contiguity invariant (CTV-V17).

**Downstream consumer integration (V1+30d+ / V2+):** 📦 TVL_004 Travel Encounters V1+30d+ (encounters attach at per-segment `actor_travel_state`; composite is encounter-agnostic) · TVL_003 Mount/Vehicle V1+30d+ (multi-modal composite paths — CTV-D5) · TVL_005 Group/Party composite travel V1+30d+ (CTV-D8) · STRAT_001 V2+ (composite paths as army-movement plans).

**Status:** DRAFT 2026-05-16. CANDIDATE-LOCK upon §13 acceptance scenarios passing integration tests against the reference `travel-service` implementation + the TVL_001 closure pass landing. LOCK upon downstream consumer integration (TVL_004 encounter coordination CTV-D1 resolves; TVL_003 multi-modal CTV-D5 resolves).

**Second TVL feature; first convenience layer.** TVL_001 ships the atomic-travel physics; TVL_002 ships the orchestration that makes multi-settlement journeys a single declared intent — the same consumer-feature pattern (read locked substrate → produce per-actor runtime state → surface via S9 LLM-context grounding), now layered one level higher (a feature consuming a feature).
