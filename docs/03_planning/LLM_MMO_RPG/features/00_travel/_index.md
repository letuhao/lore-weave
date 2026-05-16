# 00_travel — Index

> **Category:** TVL — Travel Mechanics (V1+ foundation-adjacent consumer feature; first feature consuming V1+30d activation triangle POL + SET + ROUTE)
> **Catalog reference:** [`catalog/cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) (owns `TVL-*` stable-ID namespace)
> **Purpose:** Implements inter-settlement travel via atomic single-segment Route traversal — actor at from_cell issues `Travel:Initiate { route_id }`; system advances TDIL clocks (actor + body + realm; soul preserved unless BodyOrSoul::Soul form) over `route.default_fiction_duration` × per-turn scheduler ticks; actor arrives at to_cell when journey reaches 100%. Composes with SET_001 Settlement.role for hospitality availability at arrival (Hamlet → outdoor camp narration; status effect application via PL_006 Exhausted on overnight no-inn travel); RES_001 food/water consumption per league; AIT_001 Tracked tier discipline (Untracked NPCs excluded). Narrative-only V1+30d (LLM generates journey description via S9 prompt-assembly); mechanical encounter generation deferred V1+30d+. PC + Tracked NPC parity V1+30d.

**Active:** none. _Last released 2026-05-16_ by main session (TVL_002 V1+30d+ Composite Multi-Segment Travel DRAFT — Phase 0 CTV-D1..D7 LOCKED via user `approve all` directive; lock released; ready for /review-impl adversarial pass).

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| TVL_001 | **Travel** (TVL) | V1+ primary consumer of GEO_004 ROUTE_001 V1+30d Route graph. Atomic single-segment travel V1+30d; pure mechanics (encounter generation deferred V1+30d+); on-demand Dijkstra over Route graph at request time; selective TDIL clock advancement (actor + body + realm; soul preserved); narrative-only journey description via S9 prompt-assembly with [TRAVEL_CONTEXT] sub-section; PC + Tracked NPC parity (Untracked excluded per AIT_001 quantum-observation discipline); OnFoot mode V1+30d only (ByBoat V1+30d+ schema-reserved). **NEW aggregate**: `actor_travel_state` (T2/Reality, sparse per-(actor, journey)). **NEW namespace**: `travel.*` (15 V1+30d rule_ids + 2 V2+ reservations). **NEW EVT-T sub-types**: EVT-T1 `Travel:Initiate` (player intent) + EVT-T5 `Scheduled:TravelTick` (per-turn progress) + EVT-T6 `Travel:JourneyNarration` (LLM journey description). **NEW V1+30d service**: `travel-service` (owns actor_travel_state aggregate + apply_delta + per-turn tick generator). **Cross-feature schema dependency**: EF_001 closure pass adds `entity.travel_journey_id: Option<JourneyId>` field (EF_001 schema_version 1 → 2 V1+30d bump per I14). **ROUTE_001 cross-feature gate**: TVL-V14 `route_in_use_by_journey` validator added to ROUTE_001 RemoveRoute pipeline. **Hospitality at arrival**: Settlement.role determines inn-available vs outdoor-camp; if outdoor-camp AND wakeful_duration > 16h → PL_006 StatusFlag::Exhausted applied. **Provisions cost**: food_per_league + water_per_league deducted from RES_001 vital_pool at Travel:Initiate (defaults 1.0/2.0 units/league OnFoot V1+30d). **15 V1+30d-testable acceptance scenarios** AC-TVL-1..15; 12 deferrals TVL-D1..D12 + 7 open questions TVL-Q1..Q7; 15 TVL-V* validators. **Phase 0 TVL-D1..D7 LOCKED via single deep-dive 2026-05-14** with user `continue` directive interpreted as approve all defaults: D1 own `00_travel/` folder / D2 pure mechanics V1+30d / D3 on-demand Dijkstra / D4 selective TDIL clocks / D5 narrative-only / D6 atomic single-segment / D7 PC + Tracked NPC parity. **First feature consuming V1+30d activation triangle** (POL + SET + ROUTE all locked baseline; TVL_001 leverages full geographic substrate). Owns TVL-* sub-prefix in NEW catalog `cat_00_TVL_travel_foundation.md`. | **DRAFT 2026-05-14** | [`TVL_001_travel.md`](TVL_001_travel.md) | (this commit) |
| TVL_002 | **Composite Travel** (CTV) | V1+30d+ convenience layer over TVL_001 atomic travel. Player declares a destination cell; system runs Dijkstra over the ROUTE_001 Route graph, freezes the ordered segment list, and auto-traverses N segments — each segment a plain TVL_001 atomic journey underneath. **NEW aggregate**: `composite_journey` (T2/Reality, sparse per-(actor, composite_journey)). **NEW EVT-T sub-types**: EVT-T1 `CompositeTravel:Initiate` + `CompositeTravel:Cancel` (player intent) + EVT-T8 `Forge:CancelCompositeJourney` (admin). **Cross-feature schema dependency**: `actor_travel_state` gains additive `composite_journey_id: Option<CompositeJourneyId>` field (schema_version bump per I14; TVL_001 closure pass). **Cross-feature gate**: CTV-V15 `actor_in_composite_journey` validator added to TVL_001 `Travel:Initiate` pipeline (manual atomic travel blocked while a composite is Active). **Plan freeze + re-plan fallback**: Dijkstra freezes at initiate; if a future planned segment's route is removed mid-journey, one re-plan from the current cell; re-plan failure / cap-hit / under-provisioned → `Stranded` terminal status. **Smart overnight stops**: at inn-bearing intermediate settlements (Village/Town/City/Capital) auto-rest resets wakeful_duration; no-inn stops apply the TVL_001 Exhausted check. **Whole-journey provisions pre-pay** at `CompositeTravel:Initiate`; proportional refund on cancel/strand. **Read-only `composite_travel_plan` preview query** (path + distance + ETA + provisions + intermediate settlements; mutates nothing). **Self-cancel** takes effect at the next segment boundary; **admin** `Forge:CancelCompositeJourney` is immediate. **15 V1+30d+-testable acceptance scenarios** AC-TVL-16..30; 9 deferrals CTV-D1..D9 + 7 open questions CTV-Q1..Q7; 17 CTV-V* validators; 12 `travel.*` rule_ids (10 player-meaningful + 2 defensive). **Phase 0 CTV-D1..D7 LOCKED via single deep-dive 2026-05-16** with user `approve all` directive: D1 new `composite_journey` aggregate / D2 freeze-at-initiate + re-plan fallback / D3 smart overnight stops / D4 whole-journey provisions pre-pay / D5 destination-cell + reachability check / D6 self-cancel at next segment boundary / D7 read-only preview before commit. **Second TVL feature; first convenience layer** (a feature consuming a feature). No new service — lives in `travel-service`. | **DRAFT 2026-05-16** | [`TVL_002_composite_travel.md`](TVL_002_composite_travel.md) | (this commit) |

---

## Kernel touchpoints

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations (T2/Reality aggregate); DP-Ch reality-channel binding for actor_travel_state
- `06_data_plane/12_channel_primitives.md` — Reality-scoped aggregate scope marker
- `07_event_model/03_event_taxonomy.md` — EVT-T1 Submitted sub-type `Travel:Initiate` + EVT-T5 Scheduled sub-type `Scheduled:TravelTick` + EVT-T6 Proposal sub-type `Travel:JourneyNarration`
- `_boundaries/01_feature_ownership_matrix.md` — `actor_travel_state` aggregate owned by TVL_001 (added 2026-05-14)
- `_boundaries/02_extension_contracts.md` §1 — TurnEvent EVT-T1 sub-types row gains `Travel:Initiate`; EVT-T5 sub-types row gains `Scheduled:TravelTick`; EVT-T6 sub-types row gains `Travel:JourneyNarration`
- `_boundaries/02_extension_contracts.md` §1.4 — NEW `travel.*` RejectReason namespace (15 V1+30d rule_ids + 2 V2+ reservations)

---

## Naming convention

`TVL_<NNN>_<short_name>.md`. Sequence per-category. TVL_001 is the foundation; future TVL_NNN candidates:

- `TVL_002` Composite Multi-Segment Travel (V1+30d+ — Dijkstra over Route graph + auto-traverse N segments)
- `TVL_003` Mount/Vehicle Travel (V1+30d+ — OnHorseback / ByBoat / ByShip / ByCarriage; activates ByBoat mode)
- `TVL_004` Travel Encounters (V1+30d+ — random events / weather / combat during journey; attaches to actor_travel_state)
- `TVL_005` Group/Party Travel (V1+30d+ — multiple actors traversing same Route together; party-formation aggregate)
- `TVL_006` Soul-Projection Travel (V2+ — BodyOrSoul::Soul form astral travel per wuxia/cultivation archetype canon)
- `TVL_007` Off-Camera Background NPC Migration (V2+ — Untracked NPC ambient migration; quantum-observation pattern)

Whether these become separate TVL_NNN files or sub-sections of TVL_001 depends on size at design time.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination notes

TVL_001 V1+30d is the FIRST feature consuming the V1+30d activation triangle (POL + SET + ROUTE). It demonstrates the consumer-feature pattern:
- Geographic substrate features (GEO_001..GEO_004) populate world_geometry layers
- TVL_001 V1+30d consumes those layers (reads routes + settlements + provinces + biome/climate context) and produces per-actor runtime state (actor_travel_state aggregate)
- LLM prompt-assembly extends with `[TRAVEL_CONTEXT]` sub-section grounding journey narration

Future consumer features (encounter generators, strategy gameplay, faction politics) layer atop the V1+30d activation triangle following the same pattern: read locked substrate, produce per-actor or per-faction runtime state, surface via S9 LLM-context grounding.

Cross-feature schema dependency: EF_001 entity_binding gains `travel_journey_id: Option<JourneyId>` field (additive per I14; EF_001 schema_version 1 → 2 bump at TVL_001 V1+30d ship). EF_001 closure pass coordinates the addition; world-service writes the field; travel-service reads it (cross-service-write boundary per DP-A11 single-writer discipline).

NEW V1+30d service: `travel-service`. Owns actor_travel_state aggregate. Cross-service handoff with world-service (reads world_geometry) + chat-service (LLM journey narration) + auth-service (no new capability; standard PC/NPC action authorization).
