# TVL_004 — Travel Encounters

> **Conversational name:** "Travel Encounters" (CTE). V1+30d+ feature that generates encounters *during* a journey — a bandit ambush on a remote Trail, a merchant caravan on a Road, a storm on a MountainPass, a herb cache beside a River. Reads the locked V1+30d substrate (GEO_001 biome, GEO_004 ROUTE_001 `route.kind`, GEO_002 POL_001 province) and attaches mechanical encounter events to TVL_001's `actor_travel_state`. An encounter pauses the journey; the actor picks a per-kind approach; chat-service LLM narrates the scene and proposes an outcome; the engine clamps the outcome to author-declared bounds; the journey resumes. Encounter schedule is pre-rolled deterministically at `Travel:Initiate` (replay-stable). Encounter participants are abstract and ephemeral (no persistent EF_001 entities). PC + Tracked NPC parity inherited from TVL_001. Composite journeys are encounter-agnostic — a paused segment pauses the TVL_002 composite with no composite-side change.
>
> **Category:** TVL — Travel Mechanics (V1+30d+ feature; fourth TVL feature; the encounter layer TVL_001 deferred as TVL-D1 and TVL_002 declared composite-agnostic as CTV-D1)
> **Status:** **DRAFT 2026-05-16** (Phase 0 CTE-D1..D7 LOCKED with user `approve all` directive)
> **Catalog refs:** [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — owns `TVL-*` stable-ID namespace (`CTE-*` validators/deferrals/questions per-feature)
> **Builds on:** [`TVL_001`](TVL_001_travel.md) (parent — `actor_travel_state` journey; `Scheduled:TravelTick`; `JourneyId`; selective TDIL clock advancement — the pause/resume hooks into the TVL_001 tick mechanism) · [`TVL_002`](TVL_002_composite_travel.md) (composite journeys — encounter-agnostic; a paused segment pauses the composite, no composite change) · [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) (`route.kind` 5-variant — encounter-table key) · [`GEO_003 SET_001`](../00_geography/GEO_003_settlement_generator.md) (encounters fire between settlements, not at them) · [`GEO_002 POL_001`](../00_geography/GEO_002_political_layer.md) (Province danger modifier shifts encounter weights) · [`GEO_001`](../00_geography/GEO_001_world_geometry.md) (`BiomeKind` 14-variant — encounter-table key) · [`PL_005`](../04_play_loop/PL_005_interaction.md) (Interaction substrate — encounter resolution narration vocabulary) · [`PL_006`](../04_play_loop/PL_006_status_effects.md) (encounter outcomes apply status effects — Wounded on a lost fight, Exhausted from a storm) · [`RES_001`](../00_resource/RES_001_resource_foundation.md) (encounter outcomes adjust `resource_inventory` — loot gained, supplies lost) · [`TDIL_001`](../03_actor_substrate/TDIL_001_time_dilation_foundation.md) (an encounter consumes fiction-time; actor + body clocks advance) · [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) (Tracked-tier discipline; encounter participants are abstract, NOT AIT entities)
> **Resolves:** Static-journey gap (TVL_001 V1+30d ships journeys that are pure progress-bars — nothing *happens* between origin and destination; the Imperial Highway and a bandit-infested mountain trail feel identical mechanically) · Cross-settlement encounter substrate (TVL_001 §1 Gap 3 named this — "V1+30d+ encounter generators need a travel-in-progress state to attach to; TVL_001 provides the state aggregate; encounters layer on top later"; TVL_004 is that layer) · Biome/route texture payoff (the GEO/POL/SET/ROUTE V1+30d activation triangle populates rich biome + route + province data that, without encounters, only ever surfaces as narration flavor — TVL_004 makes the geography mechanically consequential)
> **Defers to:** future **combat feature** (turn-by-turn combat — TVL_004 `Combat` encounters resolve via one abstracted engage/flee outcome V1+30d+; a real combat loop, when designed, replaces the abstraction per CTE-D5) · future **V2+ weather substrate** (TVL_001 TVL-D6 — TVL_004 `Hazard` encounters are discrete weather *events*, not a persistent climate-driven weather model) · future **V2+ encounter-NPC promotion** (a memorable encounter participant promoted to a persistent Tracked NPC via the AIT_001 quantum-observation promotion path — V1+30d+ participants are abstract and ephemeral per CTE-D6) · future **V2+ encounter chains** (a resolved encounter spawning a follow-up quest/encounter — V1+30d+ encounters are independent one-shots)

---

## §1 Why this exists

Three concrete gaps that TVL_004 closes.

**Gap 1 — journeys are mechanically inert.** TVL_001 V1+30d ships travel as a progress-bar: `Travel:Initiate`, per-turn ticks, arrive. Nothing happens *en route*. A 24-hour journey down the Imperial Highway and a 24-hour journey across a lawless MountainPass are mechanically identical — both advance `progress_fraction` and apply provisions cost. The narration may differ (S9 `[TRAVEL_CONTEXT]`), but no *event* ever forces a decision, costs a resource unexpectedly, or rewards exploration. TVL_004 makes the road itself a source of gameplay.

**Gap 2 — TVL_001 explicitly designed the hook and left it empty.** TVL_001 §1 Gap 3 is titled "Cross-settlement encounter substrate is V1+30d+ blocked without travel-state aggregate" and ends: "TVL_001 V1+30d introduces `actor_travel_state` as that anchor (progress_fraction over a Route). V1+30d+ encounter generators attach encounter events to this state. Without TVL_001 V1+30d, V1+30d+ encounter design has no place to land." TVL-D1 deferred the encounter generator; TVL_002's CTV-D1 declared composite journeys encounter-agnostic so that this feature could attach at the per-segment level cleanly. TVL_004 is the deferred feature — the anchor is built, the layer lands.

**Gap 3 — the geography activation triangle has no mechanical payoff.** GEO_001 + POL_001 + SET_001 + ROUTE_001 populate biome, climate, province, state, settlement role, and route kind across every cell. Without encounters, all of that data only ever reaches the player as *narration texture* — the LLM mentions the jungle, the frontier province, the mountain pass. TVL_004 makes the substrate mechanically consequential: a `Combat` encounter is likelier on a `Trail` through a `Jungle` biome in a lawless frontier `Province`; a `Discovery` is likelier near `Mountain` ruins. The geography starts to *matter*, not just *describe*.

TVL_004 introduces no new travel physics. The journey, ticks, clocks, provisions, hospitality all come from TVL_001 unchanged. TVL_004 adds an encounter aggregate, a deterministic pre-rolled trigger schedule, a pause/resume hook into the TVL_001 tick generator, and a choice-based LLM-narrated resolution.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Travel encounter** | `travel_encounter` aggregate (T2/Reality, sparse per-(journey_id, encounter_id)) — NEW V1+30d+ | One row per encounter that fired. Sparse — only journeys that actually hit a pre-rolled encounter point get rows. Closed (`Resolved`/`Skipped`) once handled; the row is retained for audit. |
| **EncounterId** | `pub struct EncounterId(pub(crate) Ulid)` opaque newtype | Module-private constructor; blake3-derived from `(journey_id, encounter_seed, trigger_progress_fraction)` for replay-determinism. |
| **Encounter schedule** | A list of `(progress_fraction, encounter_seed)` points, computed once at `Travel:Initiate` and pinned onto a NEW additive `actor_travel_state.encounter_schedule` field | Pinned at initiate (HIGH-2 fix /review-impl) — the schedule depends on `world_geometry` biome + `route.kind`, both mutable via `GeographyDelta`, so re-deriving it each tick would break determinism on a mid-journey geography edit. Stored, it is immune to later edits and copies bit-exactly at snapshot fork (CTE-Q1). |
| **Encounter trigger** | A `Scheduled:TravelTick` whose advancement crosses a scheduled `progress_fraction` point | The TVL_001 tick generator, extended per the CTE closure pass (§10), checks each tick: did `progress_fraction` cross a scheduled point? If yes → emit the encounter (EVT-T3) and pause the journey. |
| **Journey pause** | Signalled by an *unresolved* `travel_encounter` row (status ∈ {Pending, Resolving}) | While such a row exists for a journey, the TVL_001 `Scheduled:TravelTick` generator SKIPS `progress_fraction` advancement for that journey (CTE closure-pass behavior — no change to TVL_001's `TravelStatus` enum). The journey is not `Canceled` and not `Arrived` — just frozen until the encounter resolves. |
| **EncounterKind** | Closed enum 4 V1+30d+ — Combat / Social / Hazard / Discovery | `Combat` hostile (bandit, beast) · `Social` non-hostile (merchant, traveler, pilgrim) · `Hazard` environmental (storm, rockslide, flood) · `Discovery` beneficial (ruin, herb cache, abandoned supplies). |
| **EncounterApproach** | Closed enum — the actor's chosen way to handle it; valid subset per `EncounterKind` | `Confront` / `Avoid` / `Parley` / `Investigate`. Each `EncounterKind` exposes a 2–3 approach subset (§4.3); `travel_encounter.available_approaches` lists the valid set; `Encounter:Resolve` must pick from it. |
| **Encounter table** | `EncounterTableDecl` — author-declared per-reality, keyed `(BiomeKind × RouteKind)` | Weighted `EncounterKind` list + a danger band + per-kind `OutcomeBounds`. RealityManifest extension `encounter_tables` (§11); engine ships a default table as fallback. Immutable post-bootstrap. |
| **Province danger modifier** | A weight shift applied to the encounter table from POL_001 `Province` data | A lawless / frontier province shifts weight toward `Combat`; a settled core province toward `Social`/`Discovery`. V1+30d+ uses a coarse 3-band `ProvinceDangerBand` derived from province metadata (CTE-Q4). |
| **Encounter outcome** | `EncounterOutcome` — engine-validated consequences after resolution | LLM proposes (`provisions_delta`, PL_006 `status_effects`, RES_001 `resource_grant`, optional `reroute`, `fiction_duration`); the engine clamps every field to the encounter-table entry's `OutcomeBounds` (PROG_001 hybrid-damage Q7 precedent — clamp silently, preserve narrative flow). |
| **Abstract participant** | The "bandit", the "merchant" — described by the encounter, NOT instantiated as EF_001 entities | V1+30d+ participants are ephemeral, scoped to the encounter, gone on resolution. Instantiating a persistent NPC per roadside encounter would explode entity count against AIT_001's billion-NPC discipline. Promotion to a persistent Tracked NPC is deferred V2+ (CTE-D3). |
| **Combat abstraction** | A `Combat` encounter resolved without a turn-by-turn loop | No combat feature exists yet. V1+30d+ `Combat` encounters resolve as ONE abstracted outcome (the LLM proposes win/loss + consequences given the actor's PROG_001 stats; the engine validates). A future combat feature replaces the abstraction (CTE-D5). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

TVL_004 introduces no new EVT-T* category. It adds sub-types to existing mechanism-level categories.

| TVL_004 event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| An encounter fires mid-journey | **EVT-T3 Derived** | creates a `travel_encounter` row (status=Pending) + pauses the journey | travel-service tick handler (encounter detection during `Scheduled:TravelTick`) | NOT a player event — the encounter is system-generated from the deterministic schedule. Causal-ref to the triggering `Scheduled:TravelTick`. |
| LLM narrates the encounter scene | **EVT-T6 Proposal** | `Encounter:SceneNarration { encounter_id, content }` (NEW V1+30d+ sub-type) | chat-service S9 LLM | The situation presented to the actor (Pending → the actor sees it). Ephemeral narration linked to `encounter_id`, NOT canonical state (per EVT-A10). |
| Actor chooses how to handle it | **EVT-T1 Submitted** | `Encounter:Resolve { encounter_id, approach }` (NEW V1+30d+ sub-type) | PC via client-app encounter UI / Tracked NPC via chat-service Chorus per NPC_002 | Recorded in `_boundaries/02_extension_contracts.md` §1.4 (`travel.*` namespace row). |
| Encounter state mutation (resolve / outcome apply / resume) | **EVT-T3 Derived** | `aggregate_type=travel_encounter` | travel-service | Causal-ref to the triggering `Encounter:Resolve`. Cascades to PL_006 (status) + RES_001 (provisions/resources). |
| LLM proposes the outcome | **EVT-T6 Proposal** | `Encounter:SceneNarration` reused with an `outcome_proposal` payload field | chat-service S9 LLM | The LLM-proposed `EncounterOutcome` is carried in the same EVT-T6 narration proposal; the engine validates/clamps it before the EVT-T3 apply. No separate sub-type. |
| Admin skips a stuck encounter | **EVT-T8 Administrative** | `Forge:ResolveEncounter { encounter_id, resolution, reason }` (NEW V1+30d+ sub-type) | Forge admin via S5/S13 admin tooling | `resolution` is **Skip-only V1+30d+** (LOW-4 fix — forcing a bespoke outcome would bypass the LLM-propose + engine-clamp path, out of V1+30d+ scope): sets the encounter `Skipped`, the journey resumes untouched, no outcome applied. Uses the existing Forge admin capability per ADMIN_ACTION_POLICY. |
| Journey progress resumes | **EVT-T5 Scheduled** | `Scheduled:TravelTick` (TVL_001 sub-type, unchanged) | EVT-G framework Generator | Once the `travel_encounter` is `Resolved`/`Skipped`, the next `Scheduled:TravelTick` resumes `progress_fraction` advancement. TVL_004 adds no tick mechanism of its own. |

**No new GeographyDeltaKind** — encounters are per-journey runtime state, do not touch `world_geometry`.

**`Encounter:Resolve` is an EVT-T1 Submitted not EVT-T8 Admin** — choosing how to handle an encounter is regular gameplay (PC + Tracked NPC). Only `Forge:ResolveEncounter` (admin override) is EVT-T8.

---

## §3 Aggregate inventory

One new aggregate owned by TVL_004, **plus one additive field on TVL_001's `actor_travel_state`** — the pinned pre-rolled encounter schedule (HIGH-2 fix /review-impl; see §3.2 + §5.1 + CTE-Q1). The journey *pause* itself is still signalled by the existence of an unresolved `travel_encounter` row, not a stored flag — `TravelStatus` is unchanged.

### 3.1 `travel_encounter` (T2/Reality, sparse per-(journey, encounter)) — PRIMARY (NEW V1+30d+)

```rust
#[derive(Aggregate)]
#[dp(type_name = "travel_encounter", tier = "T2", scope = "reality")]
pub struct TravelEncounter {
    pub encounter_id: EncounterId,                  // primary key (sparse — only fired encounters have rows)
    pub journey_id: JourneyId,                      // FK into TVL_001 actor_travel_state (the journey this paused)
    pub actor_id: ActorId,                          // the traveling actor (denormalized from the journey for query)
    pub kind: EncounterKind,                        // Combat | Social | Hazard | Discovery
    pub status: EncounterStatus,                    // Pending | Resolving | Resolved | Skipped
    pub trigger_progress_fraction: f32,             // the journey progress_fraction at which this fired (∈ (0.0, 1.0))
    pub biome: BiomeKind,                           // GEO_001 — biome at the trigger cell (encounter-table key, snapshot)
    pub route_kind: RouteKind,                      // ROUTE_001 — kind of the route being traversed (encounter-table key, snapshot)
    pub province_danger_band: ProvinceDangerBand,   // POL_001-derived danger band at the trigger cell (Safe | Contested | Lawless)
    pub available_approaches: Vec<EncounterApproach>, // valid resolution approaches for this kind (§4.3)
    pub chosen_approach: Option<EncounterApproach>, // set at Encounter:Resolve; None while Pending
    pub outcome: Option<EncounterOutcome>,          // engine-validated outcome; None until Resolved
    pub encounter_seed: u64,                        // from the deterministic pre-rolled schedule (replay-determinism)
    pub triggered_at_fiction_time: FictionTime,     // actor_clock at trigger
    pub fiction_duration: FictionDuration,          // fiction-time the encounter consumed; added to the journey on resume
}

pub struct EncounterOutcome {
    pub provisions_delta: ProvisionsDelta,          // signed food/water change (Discovery + ; Combat/Hazard −)
    pub status_effects: Vec<StatusEffectDecl>,      // PL_006 effects applied (Wounded on a lost Combat, Exhausted from a Hazard)
    pub resource_grant: Vec<ResourceGrantDecl>,     // RES_001 inventory change (Discovery loot; Combat-loss theft)
    pub reroute: Option<RerouteDecl>,               // optional — Hazard may force a detour OR a journey cancel-to-safety
    pub narration_ref: NarrationRef,                // link to the EVT-T6 Encounter:SceneNarration content
}

pub enum EncounterKind {                            // closed enum 4 V1+30d+
    Combat,                                         // hostile — bandit ambush, predatory beast
    Social,                                         // non-hostile — merchant caravan, fellow traveler, pilgrim
    Hazard,                                         // environmental — storm, rockslide, river flood
    Discovery,                                      // beneficial — roadside ruin, herb cache, abandoned supplies
}

pub enum EncounterStatus {                          // closed enum 4 V1+30d+
    Pending,                                        // fired; journey paused; awaiting the actor's approach choice
    Resolving,                                      // approach chosen; LLM generating scene outcome; engine validating
    Resolved,                                       // outcome applied; journey resumed
    Skipped,                                        // admin Forge:ResolveEncounter skip (journey resumes untouched)
}

pub enum ProvinceDangerBand {                       // closed enum 3 V1+30d+ — coarse POL_001-derived danger
    Safe,                                           // settled core province — weights toward Social / Discovery
    Contested,                                      // mixed — balanced weights
    Lawless,                                        // frontier / stateless province — weights toward Combat
}
```

**Rules:**

- One unresolved `travel_encounter` per journey — ≤1 row with `status ∈ {Pending, Resolving}` per `journey_id` (CTE-V2). The deterministic schedule never places two encounter points so close that a second fires before the first resolves; the journey is paused until resolution.
- `journey_id` MUST reference an `actor_travel_state` row with `status == Active` (CTE-V1). An encounter cannot fire on an `Arrived`/`Canceled` journey.
- `trigger_progress_fraction ∈ (0.0, 1.0)` — strictly interior; encounters never fire exactly at origin (0.0) or destination (1.0).
- `kind` is drawn from the encounter table for `(biome, route_kind)` weighted by `province_danger_band`; `available_approaches` is the fixed per-kind subset (§4.3).
- `chosen_approach` is `Some(..)` exactly when `status ∈ {Resolving, Resolved}`; `Encounter:Resolve` sets it and it must be ∈ `available_approaches` (CTE-V3).
- `outcome` is `Some(..)` exactly when `status == Resolved`; every field is engine-clamped to the encounter-table entry's `OutcomeBounds` before the EVT-T3 apply.
- `fiction_duration` is set at resolution (LLM-proposed, clamped to the table's `max_encounter_duration`); on resume the journey's `expected_arrival_fiction_time` shifts later by exactly this amount — the encounter delayed the trip.
- `status` transitions are monotone toward terminal: `Pending → Resolving → Resolved`, or `Pending → Skipped` (admin), or `Pending → Skipped`/`Resolving → Skipped` (admin override). No terminal → non-terminal.
- `encounter_seed` is the seed the deterministic schedule assigned this point; the encounter's `kind` roll, the LLM prompt seed, and the outcome roll all derive from it — replay-deterministic.

### 3.2 Cross-feature additive field on `actor_travel_state` (TVL_001 aggregate)

```rust
// added to TVL_001 ActorTravelState — additive field per I14
pub encounter_schedule: Vec<EncounterPoint>,        // the pre-rolled encounter schedule, pinned at Travel:Initiate; empty Vec = no encounters / pre-bump rows

pub struct EncounterPoint {
    pub progress_fraction: f32,                     // ∈ (0.0, 1.0) — where along the journey this encounter fires
    pub encounter_seed: u64,                        // seeds the kind roll + LLM prompt + outcome roll for the encounter at this point
}
```

Additive `Vec` field → bumps `actor_travel_state` aggregate `schema_version` per I14 (default-tolerant readers: pre-bump rows read `encounter_schedule = []` = no encounters). **HIGH-2 fix (/review-impl)** — an earlier draft left the schedule un-stored and re-derived it each tick, justified as "a pure function of immutable inputs". That is unsound: the schedule's Poisson rate is keyed on `(biome, route_kind)`, and **both are mutable** via `GeographyDelta` (`SetBiomeOverride`, `ReclassifyRoute`) — a mid-journey geography edit would make a re-derivation diverge. Pinning the schedule at `Travel:Initiate` makes an in-flight journey immune to later geography edits and replay-deterministic. Coordination tracked **CTE-Q1** — added via the TVL_001 closure pass at TVL_004 ship, mirroring TVL_002's `composite_journey_id` precedent (CTV-Q1). The closure pass is therefore **schema + behavioral**, not behavioral-only.

---

## §4 Closed enums (TVL_004 V1+30d+)

### 4.1 EncounterKind (4 V1+30d+; closed)

```rust
pub enum EncounterKind {                            // closed; per-encounter
    Combat,                                         // V1+30d+ resolves via the combat abstraction (CTE-D5) — no turn-by-turn loop
    Social,                                         // V1+30d+ resolves via Parley/Avoid — trade, information, safe passage
    Hazard,                                         // V1+30d+ environmental — discrete weather/terrain events (full weather substrate V2+ TVL-D6)
    Discovery,                                      // V1+30d+ beneficial — Investigate yields a resource_grant
}
```

### 4.2 EncounterStatus (4 V1+30d+; closed) · ProvinceDangerBand (3 V1+30d+; closed)

See §3.1 — `EncounterStatus` {Pending, Resolving, Resolved, Skipped}; `ProvinceDangerBand` {Safe, Contested, Lawless}.

### 4.3 EncounterApproach (4 V1+30d+; closed) — valid subset per EncounterKind

```rust
pub enum EncounterApproach {                        // closed; per-resolution
    Confront,                                       // Combat: fight (abstracted) · Hazard: push through
    Avoid,                                          // Combat: flee · Hazard: wait it out / detour · Social: decline / pass by
    Parley,                                         // Combat: negotiate / bribe · Social: trade / talk
    Investigate,                                    // Discovery: explore the find · Social: approach cautiously
}
```

| EncounterKind | `available_approaches` |
|---|---|
| `Combat` | `Confront` · `Avoid` · `Parley` |
| `Social` | `Parley` · `Avoid` · `Investigate` |
| `Hazard` | `Confront` · `Avoid` |
| `Discovery` | `Investigate` · `Avoid` |

The per-kind subset is fixed V1+30d+ (hardcoded; not author-tunable — CTE-D6 V2+).

TVL_004 reuses TVL_001's `JourneyId`, `BiomeKind` (GEO_001), `RouteKind` (ROUTE_001). `EncounterOutcome` / `ProvisionsDelta` / `ResourceGrantDecl` / `RerouteDecl` are structs, not enums.

---

## §5 Encounter lifecycle

### 5.1 Deterministic pre-roll (at `Travel:Initiate`)

```
At Travel:Initiate the encounter schedule is computed ONCE and PINNED onto the journey:
  seed = blake3(journey_id || route_id);  rng = Rng::from_seed(seed);
  walk a Poisson process over the route's expected duration whose rate = the encounter table's
    danger_base_rate for the route's (biome, route_kind);
  each event → an EncounterPoint { progress_fraction ∈ (0.0, 1.0), encounter_seed = rng.next_u64() }.
  V1+30d+ cap: ≤4 points per journey (CTE-V8 — bounds work + avoids encounter fatigue).
  The result is STORED in actor_travel_state.encounter_schedule (§3.2). It is NOT re-derived each
  tick: the schedule depends on world_geometry biome + route.kind, both mutable via GeographyDelta
  (SetBiomeOverride / ReclassifyRoute), so a re-derivation after a mid-journey geography edit would
  diverge (HIGH-2 fix). Pinning at initiate is also the literal sense of the approved D2 ("pre-rolled
  at Travel:Initiate"). At snapshot fork the pinned schedule copies bit-exactly (§6).

Biome resolution along a route: a ROUTE_001 Route retains the underlying traversed cell sequence
from its generation pass (Road Dijkstra / Trail nearest-connection / SeaLane BFS / etc.); TVL_004
maps a progress_fraction to the cell at that fractional position along that sequence and reads its
GEO_001 biome. If a route kind exposes no cell sequence (an abstract endpoint-only edge), TVL_004
falls back to the biome of the nearer endpoint cell (MED-4 fix — the dependency on ROUTE_001's
cell sequence is made explicit, confirmed at the ROUTE_001 implementation-phase handoff).
```

### 5.2 Encounter trigger (during `Scheduled:TravelTick`)

```
The TVL_001 Scheduled:TravelTick generator, extended per the CTE closure pass (§10):
  ↓ if the journey already has an unresolved travel_encounter (status ∈ {Pending, Resolving}):
    SKIP this tick entirely — no progress_fraction advancement AND no actor_clock/body_clock
    advancement (MED-1 fix — the encounter's own fiction_duration, added at §5.3 resolution, is the
    authoritative clock advance for the paused period; advancing clocks here too would double-count).
    The journey is paused. STOP.
  ↓ else: let p = the lowest unfired point in actor_travel_state.encounter_schedule (§3.2) with
    p.progress_fraction > last_progress. If a normal tick advance would reach or cross p
    (last_progress < p.progress_fraction ≤ would-be new_progress):
      ↓ CLAMP this tick's advancement: progress_fraction = p.progress_fraction exactly (HIGH-1 fix —
        do NOT advance to the would-be new_progress; the actor stops where the encounter happens).
        actor_clock + body_clock advance only by the fraction of the tick actually consumed
        ((p − last_progress) / full-tick-delta); the rest of the turn is absorbed by the encounter.
      ↓ resolve (biome, route_kind, province_danger_band) at the cell nearest p along the route (§5.1).
      ↓ roll EncounterKind from the encounter table for (biome, route_kind), weighted by
        province_danger_band, using p.encounter_seed.
      ↓ EVT-T3 Derived: travel_encounter row created — status=Pending, kind, biome, route_kind,
        province_danger_band, available_approaches (§4.3), trigger_progress_fraction = p.progress_fraction,
        encounter_seed = p.encounter_seed, triggered_at_fiction_time = actor.actor_clock.
      ↓ EVT-T6 Proposal: chat-service generates Encounter:SceneNarration { encounter_id, content } —
        the situation presented to the actor.
      ↓ the journey is now paused (the unresolved row blocks the next tick per the SKIP check above).
      Because the tick clamped to exactly p, the NEXT unfired point — even one a longer tick would
      have covered in the same step — is still ahead of last_progress and fires on a later tick;
      no scheduled point is ever overshot or skipped.
  ↓ else advance progress_fraction normally (TVL_001 §5.2) — no encounter this tick.
```

### 5.3 Resolution (`Encounter:Resolve`)

```
Actor (PC via client-app / Tracked NPC via Chorus) issues Encounter:Resolve { encounter_id, approach }:
  ↓ EVT-T1 Submitted validator pipeline:
    CTE-V4 encounter-exists / CTE-V5 encounter-owned-by-actor / CTE-V6 encounter-resolvable
      (status == Pending) / CTE-V3 approach ∈ available_approaches / CTE-V9 actor-tracked → pass.
  ↓ EVT-T3 Derived: travel_encounter.status = Resolving; chosen_approach = Some(approach).
  ↓ EVT-T6 Proposal: chat-service LLM generates the resolution scene + proposes an EncounterOutcome
    given (kind, approach, biome, province_danger_band, actor PROG_001 stats for Combat). The EVT-T6
    proposal — resolution scene + the proposed outcome — is cached in the event stream per EVT-A10 +
    CTE-Q3 (LOW-5 fix — replay reads the cache + re-clamps deterministically, never re-calls the LLM):
      - provisions_delta, status_effects, resource_grant, optional reroute, fiction_duration.
  ↓ Engine VALIDATES + CLAMPS the proposed outcome to the encounter-table entry's OutcomeBounds
    (CTE-V7 — clamp silently, PROG_001 hybrid-damage Q7 precedent; grossly malformed → reject + retry):
      - provisions_delta clamped to [−max_provisions_loss, +max_provisions_gain]
      - status_effects filtered to the table's allowed_status set; each magnitude clamped to PL_006's
        own 1..=10 range (LOW-2 fix — OutcomeBounds declares WHICH flags, not a magnitude ceiling)
      - resource_grant filtered to the table's grant_pool; quantities clamped
      - fiction_duration clamped to [0, max_encounter_duration]
      - reroute permitted only if the table entry sets reroute_allowed for this kind.
  ↓ EVT-T3 Derived: travel_encounter.status = Resolved; outcome = Some(clamped outcome).
    cascade RES_001: resource_inventory += resource_grant; provisions_delta applied.
    cascade PL_006: apply_set_status for each status_effect (StackPolicy per PL_006).
    cascade TDIL: actor.actor_clock + body_clock += fiction_duration (the encounter took time).
    journey.expected_arrival_fiction_time += fiction_duration (the trip now arrives later).
    if outcome.reroute is Some: see §5.5.
  ↓ the journey is no longer paused — the next Scheduled:TravelTick resumes progress_fraction (§5.2).
```

### 5.4 Combat abstraction (`Combat` kind, `Confront` approach)

```
No combat feature exists yet — V1+30d+ Combat encounters resolve in ONE step (CTE-D5):
  ↓ the LLM proposes a win/loss given the actor's PROG_001 combat-relevant ProgressionInstance
    values vs the encounter-table entry's combat_threat rating (u8 0–100 per §11 — MED-2 fix);
  ↓ the engine validates the proposed win/loss is consistent with the stat comparison
    (mirrors PROG_001 Q7 hybrid damage — LLM narrates, engine bounds);
  ↓ outcome: win → minor provisions_delta + possible resource_grant (loot); loss → PL_006
    Wounded status + resource theft (resource_grant negative) + larger fiction_duration.
  Confront on a Combat encounter NEVER cancels the journey V1+30d+ (no death-on-the-road —
  death/incapacitation routing is a combat-feature concern; the worst V1+30d+ Combat outcome
  is Wounded + theft). A future combat feature replaces this whole step.
```

### 5.5 Reroute outcome (Hazard-driven)

```
If a resolved outcome carries reroute: Some(RerouteDecl) — only Hazard encounters may, and only
when the encounter table entry sets reroute_allowed:
  - RerouteDecl::DivertToCell { cell_id }: the actor is moved to a safe cell off the route (a storm
    forced them to shelter). cell_id MUST be within 2 hops of a cell on the route's traversed cell
    sequence (CTE-V11 — MED-3 fix: a divert is to NEARBY shelter, never an arbitrary teleport). The
    segment's actor_travel_state is Canceled (TVL_001 TravelStatus::Canceled) with proportional
    provisions refund per the TVL-Q3 policy; the actor's current_cell_id is set to cell_id — this
    OVERRIDES the closure-pass default Canceled snap-to-from_cell (the divert cell is the deliberate
    end position). The actor re-initiates travel manually.
    ↓ COMPOSITE INTERACTION (HIGH-3 fix): if the segment has composite_journey_id = Some(..), a bare
      Canceled segment would orphan the TVL_002 composite — no TVL_002 handoff/re-plan path covers
      "segment Canceled by an encounter". The reroute cascade therefore ALSO transitions the
      composite_journey to status = Stranded (the status already exists in TVL_002 — no TVL_002 doc
      change; the actor was forced off the planned path). So composite is encounter-agnostic for the
      PAUSE case (§10), but the reroute-cancel case is composite-aware.
  - RerouteDecl::DelayOnly: no diversion — modeled entirely by the fiction_duration already applied;
    the journey (and any composite it belongs to) continues. This is the common Hazard outcome.
  V1+30d+ does NOT support mid-journey route-switching (the actor staying in-journey but on a
  different route) — that would need TVL_002 composite re-plan machinery; deferred CTE-D8.
```

---

## §6 Multiverse inheritance

TVL_004 V1+30d+ inherits the standard DP-Ch + EVT-T2 snapshot-fork contract:

- At snapshot fork: parent's unresolved `travel_encounter` rows (Pending/Resolving) copied bit-exactly into the child; the child resolves them independently from the parent.
- Resolved/Skipped rows copy as historical audit records.
- L1/L2 cascade: no L2 layer — `travel_encounter` is reality-local per-journey runtime state with no canonical-author declaration.
- Determinism: the encounter schedule is pinned onto `actor_travel_state.encounter_schedule` at `Travel:Initiate` (§5.1 — HIGH-2 fix) and copies bit-exactly at fork, so parent and child share an identical schedule regardless of any post-fork geography edits. The `kind` roll and outcome roll derive from each point's `encounter_seed` — bit-identical given the same seed. An encounter resolved differently in parent vs child only because the actors made different `Encounter:Resolve` choices, or because the child re-ran the LLM scene/outcome generation and cached its own result fresh per CTE-Q3 (replay within either reality reads the cached EVT-T6, never re-calls the LLM) — that is intended divergence, replay-deterministic within each reality's own event stream.

---

## §7 Validation pipeline (TVL_004 V1+30d+ additive validators)

| Validator | Stage | Reject rule_id |
|---|---|---|
| **CTE-V1** journey-active | encounter trigger (EVT-T3, defensive) | `travel.encounter_journey_not_active` (journey status != Active — should be impossible since ticks stop on terminal; defensive) |
| **CTE-V2** one-unresolved-encounter-per-journey | encounter trigger (EVT-T3, defensive) | `travel.encounter_already_pending` (an unresolved travel_encounter already exists for the journey) |
| **CTE-V3** approach-valid-for-kind | `Encounter:Resolve` SchemaGate | `travel.encounter_approach_invalid` (chosen approach ∉ available_approaches for the encounter's kind) |
| **CTE-V4** encounter-exists | `Encounter:Resolve` ReferentialIntegrityGate | `travel.encounter_not_found` (encounter_id ∉ travel_encounter rows) |
| **CTE-V5** encounter-owned-by-actor | `Encounter:Resolve` AuthorizationGate | `travel.encounter_not_owned` (travel_encounter.actor_id != the resolving actor) |
| **CTE-V6** encounter-resolvable | `Encounter:Resolve` ReferentialIntegrityGate | `travel.encounter_already_resolved` (status ∉ {Pending}) |
| **CTE-V7** outcome-within-bounds | `Encounter:Resolve` outcome apply | `travel.encounter_outcome_malformed` (LLM outcome grossly malformed — unknown status flag, negative quantity where forbidden; well-formed-but-extreme is clamped silently, NOT rejected) |
| **CTE-V8** schedule-cap | encounter pre-roll (Travel:Initiate) | `travel.encounter_schedule_overflow` (defensive — pre-roll produced > 4 points; clamp to 4) |
| **CTE-V9** actor-tracked | `Encounter:Resolve` AuthorizationGate | `travel.actor_untracked_excluded` (reused — only Tracked actors travel, hence only they encounter) |
| **CTE-V10** kind-table-resolved | encounter trigger | `travel.encounter_table_unresolved` (defensive — no table entry for (biome, route_kind) AND engine default also missing; should be impossible — the engine default is total) |
| **CTE-V11** reroute-target-valid | `Encounter:Resolve` outcome apply | `travel.encounter_reroute_target_unknown` (RerouteDecl::DivertToCell cell_id ∉ wg.cells, OR cell_id is > 2 hops from any cell on the route's traversed sequence — MED-3 fix: a divert is to nearby shelter, not an arbitrary teleport) |
| **CTE-V12** admin-resolve-resolvable | `Forge:ResolveEncounter` ReferentialIntegrityGate | `travel.encounter_already_resolved` (reused — admin cannot resolve an already-terminal encounter) |

ContentSafetyGate applied to LLM-generated `Encounter:SceneNarration` content + the `outcome_proposal` (PII scrubber + injection scanner) — same path as TVL_001's `Travel:JourneyNarration`.

---

## §8 Failure UX — `travel.*` namespace extension

TVL_004 V1+30d+ extends the existing `travel.*` RejectReason namespace owned by TVL_001 (encounters are within the travel domain — no new namespace). **10 NEW V1+30d+ rule_ids** (6 user/admin-facing + 4 defensive) + 1 reused TVL_001 id.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d+) | English fallback | New? |
|---|---|---|---|---|---|
| `travel.encounter_not_found` | schema | `Encounter:Resolve` | "Sự kiện gặp gỡ không tồn tại." | "Encounter not found." | NEW |
| `travel.encounter_not_owned` | user | `Encounter:Resolve` | "Đây không phải sự kiện gặp gỡ của bạn." | "This is not your encounter to resolve." | NEW |
| `travel.encounter_already_resolved` | user | `Encounter:Resolve` / `Forge:ResolveEncounter` | "Sự kiện gặp gỡ này đã được giải quyết." | "This encounter is already resolved." | NEW |
| `travel.encounter_approach_invalid` | user | `Encounter:Resolve` | "Cách xử lý này không hợp lệ cho tình huống đó." | "That approach is not valid for this encounter." | NEW |
| `travel.encounter_reroute_target_unknown` | schema | `Encounter:Resolve` outcome apply | "Điểm chuyển hướng không xác định." | "Reroute target cell unknown." | NEW |
| `travel.encounter_outcome_malformed` | schema | `Encounter:Resolve` outcome apply (LLM proposal) | "Kết quả sự kiện gặp gỡ không hợp lệ." | "Encounter outcome malformed (LLM proposal rejected; retried)." | NEW |
| `travel.encounter_journey_not_active` | schema | encounter trigger (defensive) | "Hành trình không còn hoạt động." | "Journey no longer active (defensive)." | NEW |
| `travel.encounter_already_pending` | schema | encounter trigger (defensive) | "Đã có một sự kiện gặp gỡ chưa giải quyết." | "An unresolved encounter already exists (defensive)." | NEW |
| `travel.encounter_schedule_overflow` | schema | encounter pre-roll (defensive) | "Lịch sự kiện gặp gỡ vượt giới hạn." | "Encounter schedule exceeded the cap (defensive; clamped)." | NEW |
| `travel.encounter_table_unresolved` | schema | encounter trigger (defensive — CTE-V10) | "Bảng sự kiện gặp gỡ không xác định." | "No encounter table entry and no engine default (defensive — unreachable; the engine default is total over BiomeKind × RouteKind)." | NEW |
| `travel.actor_untracked_excluded` | schema | `Encounter:Resolve` AuthorizationGate | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |

Of the 10 new ids, 4 are defensive schema-level guards (`encounter_journey_not_active`, `encounter_already_pending`, `encounter_schedule_overflow`, `encounter_table_unresolved`) — `encounter_table_unresolved` in particular is unreachable in normal operation since the engine default table is total over `BiomeKind × RouteKind` (LOW-1 fix — it is now counted + carries a copy, rather than being silently excluded).

i18n: V1+30d+ ships `I18nBundle` per the RES_001 §2 cross-cutting contract from day one.

---

## §9 Cross-service handoff

| Service | Role | V1+30d+ status |
|---|---|---|
| **travel-service** | Authoritative owner of `travel_encounter` aggregate; extends its own `Scheduled:TravelTick` handler with encounter detection + pause; applies `Encounter:Resolve` + outcome validation/clamping. Co-located with `actor_travel_state` (TVL_001) + `composite_journey` (TVL_002) — the same bounded context. | V1+30d+ |
| **world-service** | Reads `world_geometry` — biome + route.kind + province at the trigger cell (encounter-table keys) | V1+30d+ |
| **chat-service** (S9) | Generates `Encounter:SceneNarration` (the situation + the resolution scene) and the LLM `EncounterOutcome` proposal; `[TRAVEL_CONTEXT]` gains an `active_encounter` sub-field when a journey is encounter-paused | V1+30d+ |
| **api-gateway-bff** | Routes `Encounter:Resolve` POSTs; the player encounter UI GETs `travel_encounter` for the Pending situation + approach options | V1+30d+ UI |
| **auth-service** | No new capability — `Encounter:Resolve` is regular gameplay; `Forge:ResolveEncounter` uses the existing Forge admin capability | V1+30d+ unchanged |
| **knowledge-service** | Reads encounter history for actor travel-experience knowledge graph (planned V1+ activation per CLAUDE.md two-layer pattern) | Not V1+30d+ |

**No new service.** `travel_encounter` is owned by `travel-service` (the NEW V1+30d service TVL_001 introduced) — encounter generation, journey ticks, and atomic/composite travel are one bounded context.

---

## §10 Composition with foundation siblings & TVL_001/TVL_002

| Sibling | Composition with TVL_004 |
|---|---|
| **TVL_001 Travel** | **Parent.** The TVL_001 closure pass for TVL_004 is **schema + behavioral** (HIGH-2 fix). *Schema*: a NEW additive `actor_travel_state.encounter_schedule: Vec<EncounterPoint>` field (the pinned pre-rolled schedule; schema_version bump per I14 — §3.2). *Behavioral*: the `Scheduled:TravelTick` generator gains (1) while the journey has an unresolved `travel_encounter`, skip BOTH `progress_fraction` and `actor_clock`/`body_clock` advancement (MED-1 — the encounter's `fiction_duration` is the authoritative clock advance for the pause); (2) clamp a tick's advancement to exactly the crossed encounter point and emit the encounter (HIGH-1 — never overshoot, never skip a second point in the same tick). The `TravelStatus` enum is unchanged — the pause is signalled by the unresolved `travel_encounter` row. The journey's `expected_arrival_fiction_time` shifts later by each resolved encounter's `fiction_duration`. |
| **TVL_002 Composite Travel** | **Encounter-agnostic by design (CTV-D1 — confirmed).** Encounters attach to the per-segment `actor_travel_state`; a paused segment is simply a segment whose `progress_fraction` stops advancing, so the TVL_002 composite handler sees no progress and waits — no `composite_journey` change, no TVL_002 closure pass. The composite's segment handoff fires only on the segment's `Travel:Arrive`, which an unresolved encounter defers. |
| **GEO_001 / GEO_004 ROUTE_001** | `BiomeKind` (GEO_001) + `RouteKind` (ROUTE_001) are the encounter-table key. Read-only at trigger time; snapshotted onto the `travel_encounter` row for replay-stable resolution. |
| **GEO_002 POL_001** | The trigger cell's `Province` yields a coarse `ProvinceDangerBand` (Safe/Contested/Lawless — CTE-Q4) that shifts the encounter-table weights. A stateless / frontier province → `Lawless` → more `Combat`. |
| **GEO_003 SET_001** | Encounters fire on the open route (`trigger_progress_fraction` strictly interior), never at a settlement cell — settlements are the safe waypoints; the road between them is where things happen. |
| **PL_005 Interaction** | Resolution narration borrows PL_005's interaction vocabulary; an encounter is NOT a PL_005 `Interaction` (no persistent target entity) but a `Social`/`Combat` encounter's scene reuses the same LLM scene-generation surface. |
| **PL_006 Status Effects** | Encounter outcomes apply PL_006 effects — `Wounded` on a lost `Combat`, `Exhausted` from a `Hazard` storm — via `apply_set_status` per PL_006 `StackPolicy`. The encounter-table entry's `allowed_status` set bounds which effects an outcome may apply. |
| **RES_001** | Outcomes adjust `resource_inventory` — `Discovery` loot (`resource_grant +`), `Combat`-loss theft (`resource_grant −`), `provisions_delta` for food/water found or spoiled. Bounded by the table's `grant_pool` + `max_provisions_*`. |
| **TDIL_001** | An encounter consumes fiction-time — on resolution `actor_clock + body_clock += fiction_duration` (selective advancement per TVL_001's TDIL discipline; `realm_clock` PL_001-owned; `soul_clock` preserved). |
| **AIT_001** | Tracked-tier discipline — only PC + Tracked NPCs travel, so only they encounter. Encounter participants (bandit, merchant) are **abstract** — NOT AIT entities, NOT EF_001 entities; ephemeral, gone on resolution (CTE-D6). V2+ promotion of a memorable participant to a Tracked NPC deferred CTE-D3. |
| **NPC_002 Chorus** | A Tracked NPC's `Encounter:Resolve` choice is Chorus-driven (the LLM picks the approach in character); same flow as a PC. |
| **PL_001 Continuum** | Turn-boundary fire — encounter detection rides the existing `Scheduled:TravelTick`; TVL_004 adds no scheduled mechanism. No PL_001 schema change. |

---

## §11 RealityManifest extension

**One new RealityManifest field** — author-declared encounter tables:

```rust
pub encounter_tables: Option<Vec<EncounterTableDecl>>,   // None → engine default table applies

pub struct EncounterTableDecl {
    pub biome: BiomeKind,
    pub route_kind: RouteKind,
    pub danger_base_rate: f32,                  // Poisson rate for the pre-roll (encounters per unit duration)
    pub kind_weights: Vec<(EncounterKind, f32)>,// weighted draw; shifted at runtime by ProvinceDangerBand
    pub combat_threat: u8,                      // 0–100 — threat rating a Combat encounter's win/loss check compares the actor's PROG_001 combat stats against (§5.4; MED-2 fix)
    pub outcome_bounds: OutcomeBounds,          // per-entry clamp envelope for LLM-proposed outcomes
}

pub struct OutcomeBounds {
    pub max_provisions_loss: f32,
    pub max_provisions_gain: f32,
    pub allowed_status: Vec<StatusFlag>,        // PL_006 flags an outcome of this entry may apply
    pub grant_pool: Vec<ResourceKindRef>,       // RES_001 resource kinds an outcome may grant
    pub max_encounter_duration: FictionDuration,
    pub reroute_allowed: bool,                  // only meaningful for Hazard entries
}
```

- `encounter_tables` is **OPTIONAL** V1+30d+ — a reality that omits it gets the **engine default table**, which is total over `BiomeKind × RouteKind` (14 × 5 = 70 entries) with conservative weights. CTE-V10 (no entry resolvable) is therefore unreachable in practice.
- Author-declared discipline mirrors GEO_001 `continent_geometries` / PROG_001 `progression_kinds` — the engine ships sane defaults; the reality may override per its genre (a wuxia jianghu wants more `Combat` on Trails; a pastoral sim wants more `Social`/`Discovery`).
- **Immutable post-bootstrap** — `encounter_tables` is pinned at `GeographyBorn` per `generator_pipeline_version` discipline; mid-life edits FORBIDDEN. Even so, the §5.1 encounter schedule is **pinned per-journey at `Travel:Initiate`** (stored on `actor_travel_state.encounter_schedule`), NOT re-derived each tick — because the schedule also depends on `world_geometry` biome + `route.kind`, which are NOT immutable (`GeographyDelta` can edit them mid-journey). Pinning at initiate is what makes an in-flight journey's schedule deterministic (HIGH-2 fix — CTE-Q1).

Bootstrap order: TVL_004 V1+30d+ activates AFTER TVL_001 V1+30d ships. Realities pre-TVL_001-ship cannot travel, hence cannot encounter — the same `route_layer_not_activated` reject covers it.

V1+30d+ feature-flag: `services/travel-service` config `travel_encounters_enabled: bool` (default true V1+30d+; false leaves TVL_001/TVL_002 travel encounter-free). Mid-life flip on an existing reality FORBIDDEN per `generator_pipeline_version` discipline.

---

## §12 Sequences

### 12.1 Bandit ambush on a frontier Trail — PC fights it off

```
lý_minh is mid-journey on a Trail through a Forest biome in a stateless frontier province.
The deterministic schedule (pre-rolled at Travel:Initiate) placed an encounter point at
progress_fraction 0.45, encounter_seed = 0x8F3A....
  ↓ Scheduled:TravelTick would advance progress 0.42 → 0.48 but a scheduled point sits at 0.45 →
    CLAMP: progress_fraction = 0.45 exactly (HIGH-1); clocks advance only the consumed fraction.
    biome=Forest, route_kind=Trail, province_danger_band=Lawless.
    encounter table (Forest × Trail, Lawless-shifted) → roll on seed 0x8F3A → kind=Combat.
  ↓ EVT-T3: travel_encounter created — status=Pending, kind=Combat,
    available_approaches=[Confront, Avoid, Parley], trigger_progress_fraction=0.45.
  ↓ EVT-T6: chat-service narrates "Ba kẻ cầm đao chặn đường mòn phía trước..." (three armed men
    block the trail ahead). Journey paused — the next tick SKIPs advancement.
  ↓ lý_minh issues Encounter:Resolve { encounter_id, approach=Confront }:
    CTE-V3 (Confront ∈ [Confront,Avoid,Parley]) / CTE-V5 (owns it) / CTE-V6 (Pending) → pass.
  ↓ status=Resolving; combat abstraction (§5.4): LLM compares lý_minh's PROG_001 martial stats
    vs the Forest×Trail entry's combat_threat rating → proposes WIN; outcome { provisions_delta: −2
    food, status_effects: [], resource_grant: [+ minor loot], fiction_duration: 2h }.
  ↓ engine clamps to the Forest×Trail OutcomeBounds → within bounds → status=Resolved.
    cascade RES_001: resource_inventory loot applied; food −2. cascade TDIL: actor_clock +
    body_clock += 2h. journey.expected_arrival_fiction_time += 2h.
  ↓ next Scheduled:TravelTick resumes progress from 0.45 (where the journey clamped + paused).
```

### 12.2 Storm on a MountainPass — Tracked NPC waits it out

```
tieu_long_nu (Tracked NPC) on a MountainPass; schedule fires an encounter at progress 0.6.
  ↓ biome=Mountain, route_kind=MountainPass, danger=Contested → roll → kind=Hazard (storm).
  ↓ EVT-T3 travel_encounter Pending; available_approaches=[Confront, Avoid].
  ↓ NPC_002 Chorus resolves on her behalf → Encounter:Resolve { approach=Avoid } (shelter, wait).
  ↓ LLM outcome: { provisions_delta: −3 food −3 water, status_effects: [], reroute: DelayOnly,
    fiction_duration: 8h }. Clamped to the MountainPass OutcomeBounds → Resolved.
  ↓ expected_arrival_fiction_time += 8h; journey resumes. (Had she chosen Confront — push
    through the storm — the LLM would likely have proposed Exhausted + a shorter delay.)
```

### 12.3 Roadside ruin — Discovery

```
A PC on a Road past a Hill biome; encounter point fires → kind=Discovery (an old shrine ruin).
  ↓ available_approaches=[Investigate, Avoid]. PC issues Encounter:Resolve { Investigate }.
  ↓ LLM outcome: { resource_grant: [+ a minor herb cache from grant_pool], provisions_delta: 0,
    fiction_duration: 1h }. Clamped → Resolved; resource_inventory += herbs; journey resumes.
```

### 12.4 Admin skips a stuck encounter

```
An encounter is Pending but the PC is offline / unresponsive; a Forge admin issues
Forge:ResolveEncounter { encounter_id, resolution=Skip, reason="player AFK — unblock journey" }:
  ↓ CTE-V12 (encounter resolvable) → pass. EVT-T8 applied.
  ↓ EVT-T3: travel_encounter.status = Skipped (no outcome applied — journey untouched).
  ↓ next Scheduled:TravelTick resumes progress; no provisions/status/clock change.
```

---

## §13 Acceptance criteria

15 V1+30d+-testable acceptance scenarios AC-TVL-31..45. LOCK granted when ≥10 pass integration tests against the `travel-service` reference impl + TVL_001 + ROUTE_001 + GEO_001 + PL_006 + RES_001 fixtures.

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-TVL-31** | A `Scheduled:TravelTick` crosses a pre-rolled encounter point → `travel_encounter` row created status=Pending, journey paused (next tick skips `progress_fraction` advancement). | — |
| **AC-TVL-32** | The encounter schedule is computed once at `Travel:Initiate` and pinned onto `actor_travel_state.encounter_schedule`; a snapshot fork copies it bit-exactly; a mid-journey `GeographyDelta` (`SetBiomeOverride` / `ReclassifyRoute`) does NOT alter an in-flight journey's pinned schedule. | — |
| **AC-TVL-33** | `Encounter:Resolve` with a valid approach → status `Pending → Resolving → Resolved`; outcome applied; journey resumes on the next tick. | — |
| **AC-TVL-34** | `Encounter:Resolve` with an approach ∉ `available_approaches` for the kind → reject. | `travel.encounter_approach_invalid` |
| **AC-TVL-35** | `Encounter:Resolve` by an actor who is not the encounter's `actor_id` → reject. | `travel.encounter_not_owned` |
| **AC-TVL-36** | Second `Encounter:Resolve` on an already-`Resolved` encounter → reject. | `travel.encounter_already_resolved` |
| **AC-TVL-37** | A `Combat` encounter resolved `Confront` (combat abstraction) → one-step win/loss; loss applies PL_006 `Wounded` + resource theft; the journey is never `Canceled` by `Combat`. | — |
| **AC-TVL-38** | An LLM-proposed outcome exceeding the encounter-table `OutcomeBounds` → silently **clamped** (not rejected); the clamped outcome is applied. | — (clamp, no reject) |
| **AC-TVL-39** | A grossly malformed LLM outcome (unknown status flag) → reject + retry. | `travel.encounter_outcome_malformed` |
| **AC-TVL-40** | A `Hazard` encounter resolved with a `reroute: DivertToCell` outcome → segment `Canceled` with proportional refund, actor at the divert cell (within 2 hops of the route); if the segment belonged to a composite, the `composite_journey` is also transitioned to `Stranded`. | — |
| **AC-TVL-41** | A `Discovery` encounter resolved `Investigate` → `resource_grant` from the table `grant_pool` added to `resource_inventory`. | — |
| **AC-TVL-42** | An encounter's `fiction_duration` on resolution shifts the journey's `expected_arrival_fiction_time` later by exactly that amount; `actor_clock + body_clock` advance by it. | — |
| **AC-TVL-43** | A reality with no `encounter_tables` declared → the engine default table applies; encounters still fire. | — |
| **AC-TVL-44** | `Forge:ResolveEncounter` with `resolution=Skip` → status `Skipped`, no outcome applied, journey resumes untouched. | — |
| **AC-TVL-45** | Snapshot fork mid-journey with an unresolved encounter → child inherits the `travel_encounter` row + the pinned `encounter_schedule` bit-exactly; child + parent resolve the encounter independently. | — |

---

## §14 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **CTE-D1** | Turn-by-turn combat loop (replaces the §5.4 combat abstraction) | V1+30d+ | No combat feature is designed yet. When one ships, `Combat` encounters hand off to it instead of the one-step abstraction. |
| **CTE-D2** | Persistent V2+ weather substrate (climate-driven weather model) | V2+ | TVL_001 TVL-D6. TVL_004 `Hazard` encounters are discrete weather *events*, not a continuous weather system. |
| **CTE-D3** | Encounter-NPC promotion (a memorable participant → a persistent Tracked NPC) | V2+ | Via the AIT_001 quantum-observation promotion path. V1+30d+ participants are abstract + ephemeral. |
| **CTE-D4** | Encounter chains (a resolved encounter spawning a follow-up encounter / quest) | V2+ | V1+30d+ encounters are independent one-shots. |
| **CTE-D5** | Mid-journey route-switch reroute (stay in-journey, switch to a different route) | V1+30d+ | Would need TVL_002 composite re-plan machinery. V1+30d+ `reroute` is `DivertToCell` (cancel-to-safety) or `DelayOnly`. |
| **CTE-D6** | Author-tunable per-kind `available_approaches` | V2+ | V1+30d+ the per-kind approach subset (§4.3) is hardcoded. |
| **CTE-D7** | Multi-actor / party encounters (a TVL_005 travel party hits one shared encounter) | V1+30d+ | Requires TVL_005 Group/Party Travel. V1+30d+ encounters are per-journey, hence per-actor. |
| **CTE-D8** | Encounter difficulty scaling by actor PROG_001 tier | V2+ | V1+30d+ the danger band is purely geography-driven (biome × route × province); it does not scale to actor power. |
| **CTE-D9** | Player-declined encounters / "travel safely" mode (lower encounter rate for a provisions premium) | V1+30d+ | A UX convenience layer; V1+30d+ the schedule is fixed by geography. |

---

## §15 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **CTE-Q1** | The encounter schedule — stored on `actor_travel_state` or re-derived each tick? | V1+30d+: **stored** (HIGH-2 fix /review-impl). An earlier draft re-derived it, justified as "a pure function of immutable inputs" — unsound: the schedule's Poisson rate is keyed on `(biome, route_kind)`, both mutable via `GeographyDelta` (`SetBiomeOverride` / `ReclassifyRoute`), so a re-derivation after a mid-journey geography edit would diverge. The schedule is pre-rolled once at `Travel:Initiate` and pinned onto a NEW additive `actor_travel_state.encounter_schedule: Vec<EncounterPoint>` field (schema_version bump per I14 — §3.2). TVL_004 thus carries a cross-feature schema dependency on `actor_travel_state`, like TVL_002's `composite_journey_id`; the TVL_001 closure pass for TVL_004 is **schema + behavioral**, not behavioral-only. |
| **CTE-Q2** | Encounter pre-roll RNG — Poisson process vs fixed N per journey? | V1+30d+: Poisson process at the table's `danger_base_rate`, capped at ≤4 points per journey (CTE-V8). A Poisson process gives a realistic "dangerous roads have more, but variable, encounters" feel while the cap bounds work + avoids encounter fatigue. |
| **CTE-Q3** | When two journeys snapshot-fork, does an in-progress LLM scene generation duplicate? | V1+30d+: the LLM `Encounter:SceneNarration` is an EVT-T6 Proposal cached in the event stream per EVT-A10; at fork the cached content copies; if the encounter was `Pending` (scene shown, not yet resolved) the child re-uses the cached scene and resolves independently. No duplicate LLM call. |
| **CTE-Q4** | `ProvinceDangerBand` derivation — what POL_001 field drives Safe/Contested/Lawless? | V1+30d+: a coarse mapping — a cell in a `Province` with a `State` (governed) → `Safe`; a `Province` with no `State` (stateless/frontier per POL_001 Option<StateId>) → `Lawless`; a contested-border province → `Contested`. Exact POL_001 border-contestation signal is a V1+30d+ implementation-phase detail; the 3-band abstraction is locked. |
| **CTE-Q5** | Should a `Combat` loss ever incapacitate / strand the actor (not just `Wounded`)? | V1+30d+: NO — the worst V1+30d+ `Combat` outcome is `Wounded` + resource theft (§5.4). Death/incapacitation routing belongs to the future combat feature (CTE-D1); a roadside ambush should not be lethal without a real combat loop. Re-examine when the combat feature lands. |
| **CTE-Q6** | Encounter LLM-call cost — how many LLM calls per encounter? | V1+30d+: exactly TWO, inherently sequential — they CANNOT be merged. Call 1 (at trigger) generates the situation scene the actor must SEE before choosing an approach; call 2 (at resolve) generates the resolution scene + the `EncounterOutcome` proposal, which depends on the approach chosen *between* the two calls. Total cost is bounded by the ≤4-encounters-per-journey cap (CTE-V8) + the inherited S6 per-session cost cap. (An earlier draft suggested merging the two into one call — logically impossible: the outcome cannot be proposed before the approach is known — MED-5 fix.) |
| **CTE-Q7** | Storage — monolithic `Vec<TravelEncounter>` per reality vs per-journey rows? | V1+30d+: sparse aggregate per `(journey_id, encounter_id)`, event-sourced via T2/Reality discipline (same as TVL_001 `actor_travel_state` TVL-Q7 + TVL_002 `composite_journey` CTV-Q6). Resolved rows retained for audit; reality-cleanup prunes them with the parent journey. |

---

## §16 Cross-references

- [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — catalog; `TVL-*` namespace; TVL_004 sub-section
- [`_index.md`](_index.md) — folder index; TVL_004 row added 2026-05-16
- [`TVL_001 Travel`](TVL_001_travel.md) — parent; `actor_travel_state` + `Scheduled:TravelTick` (tick-generator closure-pass extension)
- [`TVL_002 Composite Travel`](TVL_002_composite_travel.md) — composite journeys (encounter-agnostic per CTV-D1)
- [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) — `RouteKind` encounter-table key
- [`GEO_002 POL_001`](../00_geography/GEO_002_political_layer.md) — Province → `ProvinceDangerBand`
- [`GEO_001`](../00_geography/GEO_001_world_geometry.md) — `BiomeKind` encounter-table key
- [`PL_006`](../04_play_loop/PL_006_status_effects.md) — encounter outcomes apply status effects
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) — encounter outcomes adjust `resource_inventory`
- [`TDIL_001`](../03_actor_substrate/TDIL_001_time_dilation_foundation.md) — encounter `fiction_duration` advances actor + body clocks
- [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) — Tracked discipline; abstract (non-AIT) participants
- [`PL_001 Continuum`](../04_play_loop/PL_001_continuum.md) — turn-boundary fire for `Scheduled:TravelTick`
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — NEW `travel_encounter` aggregate row
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — NEW EVT-T1 sub-type `Encounter:Resolve` + EVT-T6 `Encounter:SceneNarration` recorded in §1.4; NEW EVT-T8 sub-shape `Forge:ResolveEncounter` in §4; `travel.*` encounter rule_ids in §1.4

---

## §17 Implementation readiness

**Design layer (this commit):** ✅ NEW `travel_encounter` aggregate schema + 1 cross-feature additive field on TVL_001's `actor_travel_state` (`encounter_schedule` — HIGH-2 fix) + 3 V1+30d+ closed enums (`EncounterKind` / `EncounterStatus` / `EncounterApproach`) + `ProvinceDangerBand` 3-variant + 12 validator slots (CTE-V1..V12) + 11 `travel.*` rule_ids (10 new + 1 reused) + 9 deferrals + 7 open questions + deterministic Poisson pre-roll schedule pinned at initiate + tick-generator clamp-to-point encounter detection + pause/resume + choice-based LLM-narrated resolution + engine-clamped outcome + combat abstraction + RealityManifest `encounter_tables` extension + cross-feature coordination with TVL_001/TVL_002/GEO_001/ROUTE_001/POL_001/PL_006/RES_001/TDIL_001/AIT_001 + 15 acceptance scenarios — all declared.

**Implementation phase (V1+30d+):** 📦 `travel_encounter` aggregate + apply_delta logic in `travel-service`; the **TVL_001 closure pass — schema + behavioral** (HIGH-2 fix): *schema* = the additive `actor_travel_state.encounter_schedule` field + schema_version bump per I14; *behavioral* = the `Scheduled:TravelTick` generator gains clamp-to-crossed-point encounter detection + the unresolved-encounter pause that skips both progress AND clock advancement; deterministic Poisson schedule generation pinned at `Travel:Initiate`; the engine default `encounter_tables` (14 × 5 total); outcome validation/clamping against `OutcomeBounds`; `Encounter:Resolve` + `Forge:ResolveEncounter` handlers; chat-service 2-call scene + resolution/outcome generation (CTE-Q6 — the two calls are inherently sequential) + `[TRAVEL_CONTEXT]` `active_encounter` extension; CI gates: schedule-pinning (the pre-rolled schedule is stored at `Travel:Initiate`, copies bit-exactly at fork, and is unaffected by a mid-journey `GeographyDelta`), apply_delta total-function for the encounter trigger + `Encounter:Resolve` + outcome cascade, outcome-clamp invariant (no applied outcome ever exceeds `OutcomeBounds`).

**Downstream consumer integration (V1+30d+ / V2+):** 📦 future combat feature (replaces the §5.4 abstraction — CTE-D1) · TVL_005 Group/Party Travel (party encounters — CTE-D7) · V2+ weather substrate (CTE-D2) · V2+ encounter-NPC promotion (CTE-D3) · knowledge-service encounter-history graph.

**Status:** DRAFT 2026-05-16. CANDIDATE-LOCK upon §13 acceptance scenarios passing integration tests against the reference `travel-service` implementation. LOCK upon downstream consumer integration (the combat feature lands and CTE-D1 resolves; TVL_005 party encounters resolve CTE-D7).

**Fourth TVL feature; the encounter layer the travel arc was built toward.** TVL_001 named the hook (§1 Gap 3), TVL_002 kept the composite layer encounter-agnostic for it (CTV-D1), and TVL_004 lands it — the geography activation triangle (GEO + POL + SET + ROUTE) finally becomes mechanically consequential, not just narration texture.
