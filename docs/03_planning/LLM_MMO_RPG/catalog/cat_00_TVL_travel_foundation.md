<!-- CHUNK-META
source: design-track manual seed 2026-05-14
chunk: cat_00_TVL_travel_foundation.md
namespace: TVL-*
generated_by: hand-authored (V1+ foundation-adjacent consumer catalog seed)
-->

## TVL — Travel Mechanics (V1+ foundation-adjacent consumer; first feature consuming V1+30d activation triangle POL + SET + ROUTE)

> Owns `TVL-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `TVL-A*` | Axioms (locked invariants) |
> | `TVL-D*` | Per-feature deferrals |
> | `TVL-Q*` | Open questions |

### TVL_001 Travel Mechanics (V1+ consumer feature — added 2026-05-14 DRAFT)

> Phase 0 TVL-D1..D7 LOCKED via single deep-dive 2026-05-14 with user `continue` directive interpreted as approve all defaults (D1 own `00_travel/` folder / D2 pure mechanics V1+30d / D3 on-demand Dijkstra / D4 selective TDIL clocks / D5 narrative-only / D6 atomic single-segment / D7 PC + Tracked NPC parity).

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| TVL-1 | `actor_travel_state` aggregate (T2/Reality, sparse per-(actor, journey)) — NEW V1+30d aggregate; primary state for in-flight journeys | 📦 DRAFT | V1+30d | GEO-1, ROUTE-1, EF-1 | [TVL_001 §3.1](../features/00_travel/TVL_001_travel.md#31-actor_travel_state-t2reality-sparse-per-actor-journey--primary-new-v130d) |
| TVL-2 | JourneyId opaque newtype (blake3-derive from `(actor_id, route_id, fiction_clock_at_initiate)` for replay-determinism) | 📦 DRAFT | V1+30d | TVL-1 | [TVL_001 §2 + §3.1](../features/00_travel/TVL_001_travel.md#2-domain-concepts) |
| TVL-3 | TravelMode 2-variant closed enum (OnFoot V1+30d active; ByBoat V1+30d+ schema-reserved for SeaLane + RiverNavigation) | 📦 DRAFT | V1+30d (OnFoot only) | TVL-1 | [TVL_001 §4.1](../features/00_travel/TVL_001_travel.md#41-travelmode-2-v130d-onfoot-active-byboat-schema-reserved-v130d) |
| TVL-4 | TravelInitiator 2-variant closed enum (Pc / TrackedNpc); Untracked NPCs excluded per AIT_001 Tracked tier discipline | 📦 DRAFT | V1+30d | TVL-1, AIT-1 | [TVL_001 §4.2](../features/00_travel/TVL_001_travel.md#42-travelinitiator-2-v130d-closed) |
| TVL-5 | TravelDirection 2-variant closed enum (Forward / Backward); requires route.is_bidirectional == true for Backward V1+30d | 📦 DRAFT | V1+30d | TVL-1, ROUTE-1 | [TVL_001 §4.3](../features/00_travel/TVL_001_travel.md#43-traveldirection-2-v130d-closed) |
| TVL-6 | TravelStatus 3-variant closed enum (Active / Arrived / Canceled) | 📦 DRAFT | V1+30d | TVL-1 | [TVL_001 §4.4](../features/00_travel/TVL_001_travel.md#44-travelstatus-3-v130d-closed) |
| TVL-7 | Per-turn Scheduled:TravelTick mechanism (per PL_001 turn-boundary; advances progress_fraction by `tick_duration / route.default_fiction_duration × actor.time_flow_rate`; selective TDIL clock advancement actor + body + realm; soul preserved unless BodyOrSoul::Soul form which is rejected at Travel:Initiate per TVL-V7) | 📦 DRAFT | V1+30d | TVL-1, TDIL-1, PL-1 | [TVL_001 §5.2](../features/00_travel/TVL_001_travel.md#52-per-turn-tick-advancement) |
| TVL-8 | Hospitality availability at arrival (Settlement.role determines inn-available vs outdoor-camp; if outdoor-camp AND wakeful_duration > 16h → PL_006 StatusFlag::Exhausted applied via OutputDecl) | 📦 DRAFT | V1+30d | TVL-1, SET-1, PL_006 | [TVL_001 §5.3](../features/00_travel/TVL_001_travel.md#53-travelarrive-cascade) |
| TVL-9 | Provisions cost at Travel:Initiate (food_per_league × distance_units Hunger + water_per_league × distance_units Thirst deducted via RES_001 vital_pool; defaults 1.0/2.0 units/league OnFoot V1+30d; hardcoded V1+30d, author-tunable V1+30d+ per TVL-D11) | 📦 DRAFT | V1+30d | TVL-1, RES-1 | [TVL_001 §2 + §5.1](../features/00_travel/TVL_001_travel.md#2-domain-concepts) |
| TVL-10 | One-journey-per-actor invariant V1+30d (≤1 Active actor_travel_state row per actor_id; TVL-V6 enforces); V1+30d+ parallel body/soul journeys deferred TVL-Q4 | 📦 DRAFT | V1+30d | TVL-1 | [TVL_001 §2 + §3.1](../features/00_travel/TVL_001_travel.md#2-domain-concepts) |
| TVL-11 | TDIL_001 selective clock advancement per TVL-D4 (actor_clock + body_clock + realm_clock advance per Scheduled:TravelTick; soul_clock preserved unless BodyOrSoul::Soul form per TDIL-A2; Soul-form actors rejected Travel:Initiate per TVL-V7) | 📦 DRAFT | V1+30d | TVL-1, TDIL-A2 | [TVL_001 §5.2](../features/00_travel/TVL_001_travel.md#52-per-turn-tick-advancement) |
| TVL-12 | EVT-T1 sub-type `Travel:Initiate` (player intent action) + EVT-T5 sub-type `Scheduled:TravelTick` (per-turn progress per EVT-G2 trigger source kind c FictionTimeMarker) + EVT-T6 sub-type `Travel:JourneyNarration` (LLM journey description V1+30d active) | 📦 DRAFT | V1+30d | EVT-A11 | [TVL_001 §2.5](../features/00_travel/TVL_001_travel.md#25-event-model-mapping-per-07_event_model-option-c-taxonomy) |
| TVL-13 | apply_delta total-function for Travel:Initiate + Scheduled:TravelTick + Travel:Arrive cascade — replay-deterministic + validator-gated | 📦 DRAFT | V1+30d | TVL-1, TVL-12 | [TVL_001 §5.1 + §5.2 + §5.3](../features/00_travel/TVL_001_travel.md#51-travelinitiate-event-flow) |
| TVL-14 | Validation pipeline V1+30d (15 TVL-V* sub-validators across Travel:Initiate + Scheduled:TravelTick + Travel:Arrive + cross-feature ROUTE_001 RemoveRoute gate) | 📦 DRAFT | V1+30d | TVL-1, TVL-13 | [TVL_001 §7](../features/00_travel/TVL_001_travel.md#7-validation-pipeline-tvl_001-v130d-additive-validators) |
| TVL-15 | NEW `travel.*` RejectReason namespace (15 V1+30d rule_ids + 2 V2+ reservations); per TVL-D7 separate from `geography.*` since travel is consumer feature with distinct ImpactClass discipline | 📦 DRAFT | V1+30d | TVL-14 | [TVL_001 §8](../features/00_travel/TVL_001_travel.md#8-failure-ux--travel-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| TVL-16 | NEW V1+30d service `travel-service` — owns actor_travel_state aggregate + apply_delta + per-turn tick generator | 📦 DRAFT | V1+30d | TVL-1, TVL-13 | [TVL_001 §9](../features/00_travel/TVL_001_travel.md#9-cross-service-handoff) |
| TVL-17 | Cross-feature schema dependency: EF_001 entity_binding additive field `entity.travel_journey_id: Option<JourneyId>` (EF_001 schema_version 1 → 2 bump per I14 + GEO precedent); coordinated via EF_001 closure pass at TVL ship | 📦 DRAFT | V1+30d | TVL-1, EF-1 | [TVL_001 §10 + §15 TVL-Q1](../features/00_travel/TVL_001_travel.md#10-composition-with-foundation-siblings) |
| TVL-18 | Cross-feature validator: ROUTE_001 RemoveRoute pipeline gains TVL-V14 `route_in_use_by_journey` check; mirrors POL_001 cross-aggregate validator C-rule pattern (TIT-C1 + PO-C1 precedent) | 📦 DRAFT | V1+30d | TVL-1, ROUTE-1 | [TVL_001 §6 + §7](../features/00_travel/TVL_001_travel.md#6-multiverse-inheritance) |
| TVL-19 | Multiverse snapshot fork inheritance (inherits standard DP-Ch + EVT-T2 contracts; actor_travel_state rows copied bit-exactly at fork-point; child + parent advance independently; replay-deterministic per `(actor_seed, route.id, fiction_clock_at_initiate, time_flow_rate)`) | 📦 DRAFT | V1+30d | TVL-1, GEO-17 | [TVL_001 §6](../features/00_travel/TVL_001_travel.md#6-multiverse-inheritance) |
| TVL-20 | LLM-context grounding enrichment: S9 prompt-assembly `[GEOGRAPHIC_CONTEXT]` extended with `[TRAVEL_CONTEXT]` sub-section when actor has in-flight journey (journey progress + remaining duration + route_kind + origin/destination); EVT-T6 `Travel:JourneyNarration` Proposal V1+30d active | 📦 DRAFT | V1+30d | TVL-12, S9 | [TVL_001 §1 Gap 2 + §10 Composition](../features/00_travel/TVL_001_travel.md#1-why-this-exists) |
| TVL-21 | 15 V1+30d-testable acceptance scenarios AC-TVL-1..15 (Travel:Initiate happy + reject paths + capability check + per-turn tick mechanism + Arrived cascade + hospitality status application + ROUTE_001 cross-feature gate + fork inheritance) | 📦 DRAFT | V1+30d | TVL-1..TVL-20 | [TVL_001 §13](../features/00_travel/TVL_001_travel.md#13-acceptance-criteria) |
| TVL-22 | Channel-bound atomic-channel discipline per TDIL-A5 (TVL-V15 cross_channel_initiate_forbidden — actor and route MUST reside in same continent channel for journey duration; cross-continent travel V2+ via multi-continent GEO-D11 or SeaLane bridges) | 📦 DRAFT | V1+30d | TVL-1, TDIL-A5 | [TVL_001 §7 TVL-V15](../features/00_travel/TVL_001_travel.md#7-validation-pipeline-tvl_001-v130d-additive-validators) |
| TVL-23 | V1+30d+ Travel Encounters (random events / weather / combat during journey; attaches encounter events to actor_travel_state) — deferred per TVL-D1 + TVL-D6 weather; substrate landing prerequisite for V1+30d+ encounter design | 📦 | V1+30d+ | TVL-1 | [TVL_001 §14 TVL-D1](../features/00_travel/TVL_001_travel.md#14-deferrals) |
| TVL-24 | V1+30d+ Mount/Vehicle Travel (OnHorseback / ByBoat / ByShip / ByCarriage; activates ByBoat mode for SeaLane + RiverNavigation routes; requires RES_001 V2+ mount-as-resource OR new mount aggregate) | 📦 | V1+30d+ | TVL-3 | [TVL_001 §14 TVL-D2](../features/00_travel/TVL_001_travel.md#14-deferrals) |
| TVL-25 | V1+30d+ Composite Multi-Segment Travel (Dijkstra over Route graph; player declares destination; system auto-traverses N segments — convenience command layered atop atomic V1+30d) | 📦 | V1+30d+ | TVL-1 | [TVL_001 §14 TVL-D4](../features/00_travel/TVL_001_travel.md#14-deferrals) |
| TVL-26 | V2+ Soul-Projection Astral Travel (BodyOrSoul::Soul form astral travel per wuxia/cultivation archetype canon; currently TVL-V7 rejects Soul-form Travel:Initiate V1+30d) | 📦 | V2+ | TVL-3 | [TVL_001 §14 TVL-D7](../features/00_travel/TVL_001_travel.md#14-deferrals) |
| TVL-27 | V2+ Off-Camera Background NPC Migration (Untracked NPCs ambient migration without explicit Travel:Initiate; quantum-observation pattern via AIT_001 V2+ feature) | 📦 | V2+ | AIT-1 | [TVL_001 §14 TVL-D3](../features/00_travel/TVL_001_travel.md#14-deferrals) |
