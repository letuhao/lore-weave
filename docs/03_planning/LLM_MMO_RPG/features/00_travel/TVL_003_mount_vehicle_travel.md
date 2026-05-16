# TVL_003 — Mount/Vehicle Travel

> **Conversational name:** "Mount/Vehicle Travel" (TVM). V1+30d+ feature that lets a journey use a mount or vehicle instead of going OnFoot — a horse on the Road, a river boat on a RiverNavigation route, a ship across a SeaLane, a carriage on a built Road. Faster travel (a per-mode speed modifier on `route.default_fiction_duration`) and access to water routes the OnFoot graph excludes. Activates the `ByBoat` `TravelMode` variant TVL_001 left schema-reserved and adds `OnHorseback` / `ByShip` / `ByCarriage` — a closed-enum additive bump (R3) of TVL_001's `TravelMode`. A mount/vehicle is a NEW lightweight `mount` aggregate (instanced, owned, located) — not an EF_001 entity, not a fungible RES_001 resource. The mount must be at the actor's origin cell at `Travel:Initiate`; it travels with the actor and is at the destination on arrival. PC + Tracked NPC parity inherited from TVL_001. Composite-journey travel with a mount (TVL_002) is deferred V1+30d+ — it needs a TVL_002 closure pass (TVM-D5); V1+30d+ TVL_003 ships mounts for atomic TVL_001 journeys only.
>
> **Category:** TVL — Travel Mechanics (V1+30d+ feature; third TVL feature by number, designed after TVL_004; unblocks TVL_002 CTV-D5 multi-modal composite paths)
> **Status:** **DRAFT 2026-05-16** (Phase 0 TVM-D1..D7 LOCKED with user `approve all` directive)
> **Catalog refs:** [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — owns `TVL-*` stable-ID namespace (`TVM-*` validators/deferrals/questions per-feature)
> **Builds on:** [`TVL_001`](TVL_001_travel.md) (parent — `actor_travel_state` journey; the `TravelMode` enum TVL_003 bumps 2 → 5; `Travel:Initiate`/`Scheduled:TravelTick`/`Travel:Arrive`; `route.default_fiction_duration` scaled by the mode speed modifier; the `travel.mode_unavailable_v1plus30d` reject lifted for the activated variants) · [`TVL_002`](TVL_002_composite_travel.md) (composite journeys — a uniform-mode composite may carry one mount across all segments; mixed-mode composite stays deferred CTV-D5) · [`TVL_004`](TVL_004_travel_encounters.md) (encounters — mount-affecting encounter outcomes deferred TVM-D4) · [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) (`RouteKind` 5-variant — the mode↔route compatibility matrix; `route.default_fiction_duration` the speed modifier scales) · [`GEO_003 SET_001`](../00_geography/GEO_003_settlement_generator.md) (settlements are where mounts are stabled/docked between journeys) · [`RES_001`](../00_resource/RES_001_resource_foundation.md) (V2+ mount purchase + mount feed — deferred TVM-D1/D2) · [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) (Tracked-tier discipline — only PC + Tracked NPCs travel, hence own mounts; mounts are NOT AIT entities) · [`EF_001`](../03_actor_substrate/EF_001_entity_foundation.md) (`actor.current_cell_id` — a mount must be at the actor's cell to be mounted)
> **Resolves:** Water-route inaccessibility (TVL_001 V1+30d ships `SeaLane` + `RiverNavigation` routes in the ROUTE_001 graph, but OnFoot cannot traverse `SeaLane` — `travel.mode_route_incompatible` — and TVL_002's OnFoot Dijkstra graph excludes `SeaLane` entirely; without a vessel those routes are dead data, exactly as TVL_001's static-Route-graph problem was before TVL_001 itself) · Uniform-speed travel (TVL_001 V1+30d every actor moves at the OnFoot "1 league/hour" baseline — a courier, a merchant caravan, and a wanderer are mechanically identical; TVL_003 makes the conveyance a meaningful choice) · TVL_002 CTV-D5 blocker (multi-modal composite paths are explicitly blocked on "TVL_003 Mount/Vehicle Travel" — TVL_003 ships the modes, after which CTV-D5 can activate mixed-mode paths)
> **Defers to:** future **RES_001 V2+ mount purchase/rental** (V1+30d+ mounts are acquired only by canonical declaration or Forge admin grant — a market-priced purchase needs an economy + a settlement stable/dock facility substrate; TVM-D1) · future **V2+ mount condition** (stamina, fatigue, injury, mount-feed provisions — V1+30d+ a mount is stateless beyond its location; TVM-D2) · future **V2+ multi-passenger vehicles** (a carriage or ship carrying several actors / a TVL_005 party — V1+30d+ one mount carries its one owner; TVM-D3) · future **mount-affecting encounter outcomes** (a TVL_004 `Combat` encounter stealing or killing a mount — V1+30d+ TVL_004 outcomes do not touch the `mount` aggregate; TVM-D4) · future **composite-journey travel with a mount** (riding a mount on a TVL_002 multi-segment composite — both *uniform-mode* and *mixed-mode*; TVL_002 as shipped rejects every non-OnFoot composite via CTV-V9, so this needs a TVL_002 closure pass relaxing CTV-V9 + adding a `mount_id` to `CompositeTravel:Initiate`/`composite_journey` — TVM-D5; the mixed-mode half is also TVL_002 CTV-D5)

---

## §1 Why this exists

Three concrete gaps that TVL_003 closes.

**Gap 1 — water routes are unreachable.** ROUTE_001 V1+30d ships a Route graph that includes `SeaLane` and `RiverNavigation` routes. But TVL_001 V1+30d ships only `OnFoot`, and `OnFoot` cannot traverse a `SeaLane` (`travel.mode_route_incompatible`) — you cannot walk across the sea. TVL_002's composite Dijkstra graph excludes `SeaLane` outright. So every `SeaLane` route in the world, and the maritime connectivity it represents, is dead data with no consumer — the exact problem TVL_001 §1 Gap 1 described for the *whole* Route graph, now scoped to its water subset. TVL_003 ships `ByShip` (and `ByBoat` for rivers) so vessels can actually use those routes.

**Gap 2 — every traveler moves at the same speed.** TVL_001 V1+30d baselines all travel at the OnFoot "1 league/hour" rate (ROUTE_001 §5.2). A messenger racing a warning to the capital, a merchant caravan, an old monk on pilgrimage — mechanically identical: same `route.default_fiction_duration`, same arrival. TVL_001's `TravelMode` enum was deliberately built 2-variant with `ByBoat` *schema-reserved* precisely so a later feature could activate richer modes. TVL_003 is that feature: a horse gets you there in under half the time, a ship is faster still — the conveyance becomes a real choice with a real trade-off (a mount must be acquired, kept, and be where you are).

**Gap 3 — TVL_002 multi-modal composite is explicitly blocked on this feature.** TVL_002's CTV-D5 deferral reads: "Multi-modal composite paths (OnFoot land segments + ByBoat SeaLane segments in one journey) — Requires TVL_003 Mount/Vehicle Travel." Until the non-OnFoot modes exist, a composite journey can only be a uniform OnFoot walk. TVL_003 ships the `TravelMode` variants; once it lands, the deferred composite-with-mount work (TVM-D5 — both uniform-mode and the mixed-mode CTV-D5) has the modes it needs. V1+30d+ TVL_003 itself ships mounts for *atomic* TVL_001 journeys — a TVL_002 composite stays OnFoot-only until the TVM-D5 closure pass lands.

TVL_003 introduces no new travel physics. The journey, ticks, clocks, provisions, hospitality, encounters all come from TVL_001/TVL_004 unchanged. TVL_003 adds a `mount` aggregate, expands the `TravelMode` enum, applies a per-mode speed modifier, and enforces a mode↔route compatibility matrix.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Mount / vehicle** | `mount` aggregate (T2/Reality, sparse per-mount) — NEW V1+30d+ | One row per owned conveyance. "Mount" covers both ridden animals and vehicles — the aggregate name is generic. Sparse — only declared/granted mounts exist. |
| **MountId** | `pub struct MountId(pub(crate) Ulid)` opaque newtype | Module-private constructor; allocated at canonical seed or `Forge:GrantMount`. |
| **MountKind** | Closed enum 4 V1+30d+ — Horse / RiverBoat / Ship / Carriage | Each `MountKind` maps 1:1 to a non-OnFoot `TravelMode` (§4.2): Horse→OnHorseback, RiverBoat→ByBoat, Ship→ByShip, Carriage→ByCarriage. |
| **MountLocation** | Closed enum 2 V1+30d+ — `AtCell(CellId)` / `InTransit(JourneyId)` | A mount is `AtCell` (stabled/docked, available to mount) or `InTransit` (carrying its owner on the named journey). On `Travel:Arrive` it returns to `AtCell` at the destination. |
| **TravelMode** | TVL_001-owned closed enum — **bumped 2 → 5 by TVL_003** (R3 additive) | `{OnFoot, OnHorseback, ByBoat, ByShip, ByCarriage}`. `OnFoot` is TVL_001 V1+30d; the other four are TVL_003 V1+30d+ (`ByBoat` was schema-reserved in TVL_001, now activated). |
| **Speed modifier** | A per-`TravelMode` multiplier on `route.default_fiction_duration` | `expected_arrival_fiction_time` is computed from `route.default_fiction_duration × speed_modifier(mode) × actor.time_flow_rate`. OnFoot = 1.0 baseline; faster modes < 1.0 (§4.3). Hardcoded V1+30d+; author-tunable V2+ (TVM-D6). |
| **Mode↔route compatibility** | A hardcoded matrix (§5.1) — which `TravelMode` may traverse which `RouteKind` | Enforced by TVM-V7 (extends TVL_001's TVL-V9). A `Horse` cannot ride a `SeaLane`; a `Ship` cannot sail a `Road`. |
| **Provisions under a mount** | Unchanged from TVL_001 — distance-based, not time-based | TVL_001 deducts `food/water_per_league × distance_units`. The mount makes the trip *faster*, not *shorter* — distance is identical — so provisions cost is identical. A faster mount saves fiction-time, not supplies. V2+ mount-feed (TVM-D2) would add a mount's own consumption. |
| **Acquisition** | `MountAcquisition` 2-variant — CanonicalSeed / ForgeGrant | V1+30d+ a mount enters the world only via a RealityManifest `canonical_mounts` declaration or a `Forge:GrantMount` admin event. Market purchase/rental deferred (TVM-D1 — needs an economy + stable/dock facility substrate). |
| **One mount per journey** | `actor_travel_state.mount_id: Option<MountId>` — NEW additive field | A journey uses at most one mount (`Some` for a mounted journey, `None` for OnFoot). The field is the second TVL_001 closure-pass schema addition (after TVL_004's `encounter_schedule`). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

TVL_003 introduces no new EVT-T* category.

| TVL_003 event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| A reality author declares a starting mount | **EVT-T4 System** | `mount` row born from a `canonical_mounts` `MountDecl` | RealityBootstrapper at GeographyBorn / reality seed | Canonical-seed path; one of the two V1+30d+ acquisition routes. |
| An admin grants a mount | **EVT-T8 Administrative** | `Forge:GrantMount { owner_actor_id, kind, cell_id, display_name }` (NEW V1+30d+ sub-type) | Forge admin via S5/S13 admin tooling | Creates a `mount` row, `location = AtCell(cell_id)`. Uses the existing Forge admin capability per ADMIN_ACTION_POLICY. Registered in `_boundaries/02_extension_contracts.md` §4. |
| Actor initiates a mounted journey | **EVT-T1 Submitted** | TVL_001's `Travel:Initiate` — payload gains `mount_id: Option<MountId>` (additive field, TVL_001 closure pass) | PC via client-app travel UI / Tracked NPC via Chorus | No new EVT-T1 sub-type — the mount is selected as part of the existing `Travel:Initiate { route_id, mode, mount_id }`. |
| Mount state mutation (mount → InTransit at initiate; → AtCell at arrive) | **EVT-T3 Derived** | `aggregate_type=mount` | travel-service | Causal-ref to the triggering `Travel:Initiate` (InTransit) or `Travel:Arrive` (AtCell at destination). |
| Journey progress under a mode | **EVT-T5 Scheduled** | `Scheduled:TravelTick` (TVL_001 sub-type, unchanged) | EVT-G framework Generator | The tick advances `progress_fraction` by `tick_duration / (route.default_fiction_duration × speed_modifier(mode))`. TVL_003 adds no tick mechanism — only the speed-modifier factor. |

**No new GeographyDeltaKind** — mounts are per-actor possessions, do not touch `world_geometry`.

**`Travel:Initiate` stays EVT-T1 Submitted** — choosing to ride is regular gameplay. Only `Forge:GrantMount` is EVT-T8.

---

## §3 Aggregate inventory

One new aggregate owned by TVL_003, plus one additive field on TVL_001's `actor_travel_state` and the `TravelMode` enum bump (the TVL_001 closure pass — see §3.2 + TVM-Q1).

### 3.1 `mount` (T2/Reality, sparse per-mount) — PRIMARY (NEW V1+30d+)

```rust
#[derive(Aggregate)]
#[dp(type_name = "mount", tier = "T2", scope = "reality")]
pub struct Mount {
    pub mount_id: MountId,                          // primary key (sparse — only declared/granted mounts exist)
    pub owner_actor_id: ActorId,                    // FK into EF_001 entity registry; the actor who owns + may ride it
    pub kind: MountKind,                            // Horse | RiverBoat | Ship | Carriage
    pub location: MountLocation,                    // AtCell(CellId) | InTransit(JourneyId)
    pub display_name: I18nBundle,                   // "Lý Minh's warhorse" / "the river skiff"
    pub acquired_via: MountAcquisition,             // CanonicalSeed | ForgeGrant
    pub acquired_at_fiction_time: FictionTime,      // owner.actor_clock at acquisition
}

pub enum MountKind {                                // closed enum 4 V1+30d+
    Horse,                                          // → OnHorseback (Road, Trail)
    RiverBoat,                                      // → ByBoat (RiverNavigation)
    Ship,                                           // → ByShip (SeaLane)
    Carriage,                                       // → ByCarriage (Road)
}

pub enum MountLocation {                            // closed enum 2 V1+30d+
    AtCell(CellId),                                 // stabled/docked at a cell; available to mount
    InTransit(JourneyId),                           // carrying its owner on the named journey
}

pub enum MountAcquisition {                         // closed enum 2 V1+30d+
    CanonicalSeed,                                  // born from a RealityManifest canonical_mounts MountDecl
    ForgeGrant,                                     // born from a Forge:GrantMount admin event
}
```

**Rules:**

- `owner_actor_id` MUST reference an actor in EF_001 with `tracking_tier ≥ Tracked` (TVM-V?? — mounts belong only to Tracked actors; Untracked NPCs have no travel state, hence no use for a mount).
- A mount is owned by exactly one actor V1+30d+ (transfer/sale deferred — TVM-D1). Ownership is set at acquisition and immutable V1+30d+.
- `location` is `AtCell(c)` whenever the mount is not on a journey; `InTransit(j)` exactly while the owner's journey `j` is `Active`. At `j`'s `Travel:Arrive` the location returns to `AtCell(destination_cell)`; at a `Canceled` journey it returns to `AtCell` of the journey's resolved end cell.
- A mount may be on at most one journey at a time — a second `Travel:Initiate` naming an `InTransit` mount → reject `travel.mount_in_transit` (TVM-V5). (The owner is already mid-journey too, so TVL-V6 one-journey-per-actor also fires — defense in depth.)
- `kind` is immutable. `display_name` is set at acquisition; V1+30d+ not renamable.

### 3.2 Cross-feature additions to TVL_001 (the `actor_travel_state` aggregate + `TravelMode` enum)

```rust
// 1 — added to TVL_001 ActorTravelState — additive field per I14
pub mount_id: Option<MountId>,                      // Some when the journey uses a mount; None for an OnFoot journey

// 2 — added to TVL_001's Travel:Initiate EVT-T1 payload — additive field per I14
//     Travel:Initiate { actor_id, route_id, mode, mount_id: Option<MountId> }

// 3 — TVL_001's TravelMode closed enum, additive bump 2 → 5 (R3)
pub enum TravelMode {
    OnFoot,                                         // TVL_001 V1+30d
    OnHorseback,                                    // TVL_003 V1+30d+
    ByBoat,                                         // TVL_003 V1+30d+ — activates TVL_001's schema-reserved variant
    ByShip,                                         // TVL_003 V1+30d+
    ByCarriage,                                     // TVL_003 V1+30d+
}
```

The `actor_travel_state.mount_id` additive field bumps `actor_travel_state` `schema_version` per I14 (default-tolerant readers: pre-bump rows = `None` = OnFoot). The `TravelMode` enum bump is an R3 closed-enum additive evolution (default-tolerant readers per R3; pre-bump streams never carry the new variants). Coordination tracked **TVM-Q1** — applied via the TVL_001 closure pass at TVL_003 ship. The TVL_001 closure pass now serves **three** consumer features: TVL_002 (`composite_journey_id`), TVL_004 (`encounter_schedule`), TVL_003 (`mount_id` + `TravelMode` bump + `Travel:Initiate` payload) — three sequential `actor_travel_state` `schema_version` bumps, landed together at `travel-service` implementation.

---

## §4 Closed enums & tables (TVL_003 V1+30d+)

### 4.1 MountKind (4 V1+30d+) · MountLocation (2) · MountAcquisition (2)

See §3.1.

### 4.2 MountKind → TravelMode mapping (1:1, fixed V1+30d+)

| MountKind | TravelMode | RouteKinds it may traverse |
|---|---|---|
| `Horse` | `OnHorseback` | Road · Trail |
| `RiverBoat` | `ByBoat` | RiverNavigation |
| `Ship` | `ByShip` | SeaLane |
| `Carriage` | `ByCarriage` | Road |

A `Travel:Initiate` whose `mode` does not match `mount.kind`'s mapped mode → reject `travel.mount_kind_mode_mismatch` (TVM-V3).

### 4.3 Speed modifiers (hardcoded V1+30d+; author-tunable V2+ per TVM-D6)

| TravelMode | speed_modifier | Effect on `route.default_fiction_duration` |
|---|---:|---|
| `OnFoot` | 1.0 | baseline (TVL_001 unchanged) |
| `OnHorseback` | 0.4 | ~2.5× faster than walking |
| `ByCarriage` | 0.6 | faster than foot; the carriage's road-bound bulk costs some speed vs a lone horse |
| `ByBoat` | 0.5 | river current + paddle |
| `ByShip` | 0.3 | open-water sailing — the fastest V1+30d+ mode |

`expected_arrival_fiction_time = initiated_at + route.default_fiction_duration × speed_modifier(mode) × actor.time_flow_rate`. The per-turn `Scheduled:TravelTick` advances `progress_fraction` by `tick_duration / (route.default_fiction_duration × speed_modifier(mode))` — TVL_001's §5.2 formula with the modifier inserted.

---

## §5 Mount/vehicle travel lifecycle

### 5.1 Mode↔route compatibility matrix (V1+30d+, hardcoded — TVM-V7, extends TVL_001 TVL-V9)

```
              Road   Trail  MountainPass  RiverNavigation  SeaLane
  OnFoot       ✓      ✓        ✓               ✓              ✗   (TVL_001 V1+30d — unchanged)
  OnHorseback  ✓      ✓        ✗               ✗              ✗
  ByCarriage   ✓      ✗        ✗               ✗              ✗
  ByBoat       ✗      ✗        ✗               ✓              ✗
  ByShip       ✗      ✗        ✗               ✗              ✓
```

A mode↔route mismatch → reject `travel.mode_route_incompatible` (TVL_001's existing rule_id; the matrix it checks is the TVL_003-expanded one above). OnFoot's row is exactly TVL_001's V1+30d behavior — TVL_003 only ADDS rows.

### 5.2 Mounted `Travel:Initiate` flow

```
Actor issues Travel:Initiate { route_id, mode = OnHorseback, mount_id = Some(m), direction }:
  ↓ EVT-T1 Submitted validator pipeline — TVL_001 gates (TVL-V1..V15) PLUS TVL_003 gates:
    TVM-V6 mode-requires-mount: mode != OnFoot ⇒ mount_id must be Some (and mode == OnFoot ⇒ None) → pass.
    TVM-V1 mount-exists: m ∈ mount rows → pass.
    TVM-V2 mount-owned: mount(m).owner_actor_id == actor.actor_id → pass.
    TVM-V3 mount-kind-mode-match: mount(m).kind maps to `mode` per §4.2 → pass.
    TVM-V4 mount-at-origin: mount(m).location == AtCell(actor.current_cell_id) → pass.
    TVM-V5 mount-not-in-transit: mount(m).location is not InTransit(..) → pass.
    TVM-V7 mode-route-compatible: (mode, route.kind) ∈ the §5.1 matrix → pass.
      (TVL_001's TVL-V9 is subsumed by the expanded matrix; the reject rule_id stays travel.mode_route_incompatible.)
    TVM-V10 mount-channel-bound: mount, actor, and route share one continent channel (TDIL-A5) → pass.
  ↓ EVT-T3 Derived: actor_travel_state row created (TVL_001 §5.1) with mode = OnHorseback,
    mount_id = Some(m); expected_arrival_fiction_time uses speed_modifier(OnHorseback) = 0.4 (§4.3).
  ↓ EVT-T3 Derived cascade: mount(m).location = InTransit(journey_id).
  ↓ provisions cost (TVL_001 §5.1) is computed distance-based, UNCHANGED by the mount.
```

### 5.3 Per-turn tick + arrival

```
Scheduled:TravelTick advances progress_fraction by tick_duration / (route.default_fiction_duration ×
  speed_modifier(mode)) — the mounted journey reaches 1.0 in fewer ticks than an OnFoot one.
On Travel:Arrive (TVL_001 §5.3):
  ↓ EVT-T3 Derived cascade: mount(m).location = AtCell(arrival_cell_id) — the mount is now stabled/
    docked at the destination, available for the actor's next journey from there.
  ↓ all other arrival behavior (hospitality, EF_001 current_cell_id, narration) is TVL_001 unchanged.
On a Canceled journey (admin Forge:CancelJourney, or a TVL_004 Hazard reroute):
  ↓ mount(m).location = AtCell(the journey's resolved end cell — from_cell on a plain cancel,
    or the divert cell on a TVL_004 reroute).
```

### 5.4 Acquisition flows

```
Canonical — a RealityManifest canonical_mounts MountDecl { owner_actor_ref, kind, spawn_cell,
  display_name }:
  ↓ at reality seed, an EVT-T4 System event creates the mount row, location = AtCell(spawn_cell),
    acquired_via = CanonicalSeed.

Admin — Forge:GrantMount { owner_actor_id, kind, cell_id, display_name } (EVT-T8):
  ↓ TVM-V8 grant-cell-valid: cell_id ∈ wg.cells → pass.
  ↓ EVT-T3 Derived: mount row created, location = AtCell(cell_id), acquired_via = ForgeGrant.

V1+30d+ has NO player-facing mount acquisition — market purchase / rental / stabling fees are
deferred (TVM-D1; they need an economy + a settlement stable/dock facility substrate).
```

### 5.5 Composite journeys with a mount — deferred V1+30d+ (TVM-D5)

Riding a mount on a TVL_002 composite (multi-segment) journey is **deferred V1+30d+** (TVM-D5). This is not merely a documentation gap — TVL_002 *as shipped* actively forbids it: TVL_002 §3.1 plus its **CTV-V9** validator (`composite_mode_unavailable_v1plus30d`) reject every `composite_journey` whose `mode` is anything other than `OnFoot`. Enabling composite-with-mount therefore requires a **TVL_002 closure pass** — not a TVL_003-side change:

- relax CTV-V9 so a composite may carry any *uniform* activated `TravelMode` (mixed-mode composite stays separately deferred — TVL_002 CTV-D5);
- add a `mount_id: Option<MountId>` field to the `CompositeTravel:Initiate` payload and to the `composite_journey` aggregate (so the composite knows which mount it carries);
- a per-segment mode↔route compatibility check at `CompositeTravel:Initiate` (every planned segment's route must suit the mount's mode), plus the InTransit-re-point-at-each-handoff mount lifecycle.

V1+30d+ **TVL_003 ships mounts for atomic TVL_001 journeys only.** A TVL_002 composite remains `OnFoot`-only until the closure pass above lands (TVM-D5).

---

## §6 Multiverse inheritance

TVL_003 V1+30d+ inherits the standard DP-Ch + EVT-T2 snapshot-fork contract:

- At snapshot fork: parent's `mount` rows copy bit-exactly into the child — `mount_id`, `owner_actor_id`, `kind`, `location` all preserved. An `InTransit(j)` mount copies alongside the `actor_travel_state` journey `j` it references (TVL-19 preserves `journey_id` at fork), so the FK stays valid.
- Child and parent advance + stable their mounts independently; a `Forge:GrantMount` in the child does not appear in the parent.
- L1/L2 cascade: no L2 layer — `mount` is reality-local per-actor possession state with no canonical-author L2 declaration (the `canonical_mounts` RealityManifest decl seeds L0/L1 at bootstrap, like every other canonical decl).
- Determinism: a mount changes only the speed modifier — a pure deterministic factor on `route.default_fiction_duration`. Same `(actor_seed, route, mode, time_flow_rate)` → bit-identical `progress_fraction` sequence (TVL_001's TVL-19 determinism, with the modifier folded in).

---

## §7 Validation pipeline (TVL_003 V1+30d+ additive validators)

| Validator | Stage | Reject rule_id |
|---|---|---|
| **TVM-V1** mount-exists | `Travel:Initiate` ReferentialIntegrityGate | `travel.mount_unknown` (mount_id ∉ mount rows) |
| **TVM-V2** mount-owned-by-actor | `Travel:Initiate` AuthorizationGate | `travel.mount_not_owned` (mount.owner_actor_id != the initiating actor) |
| **TVM-V3** mount-kind-mode-match | `Travel:Initiate` SchemaGate | `travel.mount_kind_mode_mismatch` (mount.kind's mapped mode per §4.2 != the chosen `mode`) |
| **TVM-V4** mount-at-origin | `Travel:Initiate` ReferentialIntegrityGate | `travel.mount_not_at_origin` (mount.location != AtCell(actor.current_cell_id) — the mount is elsewhere) |
| **TVM-V5** mount-not-in-transit | `Travel:Initiate` ReferentialIntegrityGate | `travel.mount_in_transit` (mount.location is InTransit(..) — already on a journey) |
| **TVM-V6** mode-requires-mount | `Travel:Initiate` SchemaGate | `travel.mode_requires_mount` (mode ∈ {OnHorseback, ByBoat, ByShip, ByCarriage} but mount_id is None; OR mode == OnFoot but mount_id is Some) |
| **TVM-V7** mode-route-compatible | `Travel:Initiate` SchemaGate (subsumes TVL_001 TVL-V9) | `travel.mode_route_incompatible` (TVL_001 rule_id — the §5.1 matrix rejects the (mode, route.kind) pair) |
| **TVM-V8** grant-cell-valid | `Forge:GrantMount` ReferentialIntegrityGate | `travel.mount_grant_cell_unknown` (Forge:GrantMount cell_id ∉ wg.cells) |
| **TVM-V9** owner-tracked | `Forge:GrantMount` + canonical-seed validation | `travel.mount_owner_untracked` (owner_actor_id is an Untracked actor — mounts belong only to Tracked actors) |
| **TVM-V10** mount-channel-bound | `Travel:Initiate` ChannelScope check | `travel.cross_channel_initiate_forbidden` (TVL_001 reused — mount, actor, route must share one continent channel) |

---

## §8 Failure UX — `travel.*` namespace extension

TVL_003 V1+30d+ extends the existing `travel.*` RejectReason namespace owned by TVL_001 (mount/vehicle travel is within the travel domain — no new namespace). **8 NEW V1+30d+ rule_ids** (5 user-facing + 3 schema-level) + 2 reused TVL_001 ids. This activates the design space TVL_001 reserved as `travel.mount_unavailable` (V2+ reservation) — that placeholder reservation is superseded by the concrete rule_ids below.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d+) | English fallback | New? |
|---|---|---|---|---|---|
| `travel.mount_unknown` | schema | `Travel:Initiate` | "Vật cưỡi được nêu không tồn tại." | "Mount not found." | NEW |
| `travel.mount_not_owned` | user | `Travel:Initiate` | "Đây không phải vật cưỡi của bạn." | "This mount is not yours." | NEW |
| `travel.mount_kind_mode_mismatch` | user | `Travel:Initiate` | "Vật cưỡi không phù hợp với cách di chuyển đã chọn." | "Mount kind does not match the chosen travel mode." | NEW |
| `travel.mount_not_at_origin` | user | `Travel:Initiate` | "Vật cưỡi không ở điểm khởi hành của bạn." | "Your mount is not at your departure cell." | NEW |
| `travel.mount_in_transit` | user | `Travel:Initiate` | "Vật cưỡi đang trong một hành trình khác." | "That mount is already on another journey." | NEW |
| `travel.mode_requires_mount` | user | `Travel:Initiate` | "Lựa chọn vật cưỡi không khớp với cách di chuyển." | "Mount selection does not match the travel mode (a non-OnFoot mode needs a mount; OnFoot must not name one)." | NEW |
| `travel.mount_grant_cell_unknown` | schema | `Forge:GrantMount` | "Ô được nêu để cấp vật cưỡi không tồn tại." | "Mount-grant target cell unknown." | NEW |
| `travel.mount_owner_untracked` | schema | `Forge:GrantMount` + canonical-seed validation | "Chỉ PC và NPC chính mới có thể sở hữu vật cưỡi." | "Only PCs and Tracked NPCs may own a mount (defensive — bootstrap / Forge-grant time)." | NEW |
| `travel.mode_route_incompatible` | user | `Travel:Initiate` | *(TVL_001 copy — matrix expanded by §5.1)* | *(TVL_001 copy)* | reused |
| `travel.cross_channel_initiate_forbidden` | schema | `Travel:Initiate` | *(TVL_001 copy)* | *(TVL_001 copy)* | reused |

Of the 8 new ids: 5 are user-facing (`mount_not_owned` / `mount_kind_mode_mismatch` / `mount_not_at_origin` / `mount_in_transit` / `mode_requires_mount`) and 3 are schema-level (`mount_unknown` / `mount_grant_cell_unknown` / `mount_owner_untracked` — the last two surface only at Forge-grant or reality-bootstrap time, defensive). `mode_requires_mount` (LOW-4 fix /review-impl) covers both directions — a non-OnFoot mode with no `mount_id`, and `OnFoot` with a `mount_id` set — so its copy is phrased neutrally rather than "requires a mount".

i18n: V1+30d+ ships `I18nBundle` per the RES_001 §2 cross-cutting contract from day one.

---

## §9 Cross-service handoff

| Service | Role | V1+30d+ status |
|---|---|---|
| **travel-service** | Authoritative owner of the `mount` aggregate; applies `Forge:GrantMount`; mutates `mount.location` (InTransit / AtCell) as a cascade of TVL_001 `Travel:Initiate` / `Travel:Arrive`. Co-located with `actor_travel_state` / `composite_journey` / `travel_encounter` — one bounded context. | V1+30d+ |
| **world-service** | Reads `world_geometry.routes` for `route.kind` (the §5.1 matrix) + the canonical-mount spawn-cell validation | V1+30d+ |
| **api-gateway-bff** | The player travel UI lists the actor's `AtCell`-at-origin mounts as mode options; routes the `Travel:Initiate { mount_id }` POST | V1+30d+ UI |
| **chat-service** (S9) | `[TRAVEL_CONTEXT]` gains the journey's `mode` + mount `display_name` for narration ("Lý Minh rides hard down the Imperial Highway…") | V1+30d+ |
| **auth-service** | No new capability — `Travel:Initiate` is regular gameplay; `Forge:GrantMount` uses the existing Forge admin capability | V1+30d+ unchanged |
| **knowledge-service** | Reads mount ownership for the actor knowledge graph (planned V1+ activation per CLAUDE.md two-layer pattern) | Not V1+30d+ |

**No new service.** The `mount` aggregate is owned by `travel-service` — mounts, journeys, composites, and encounters are one bounded context.

---

## §10 Composition with foundation siblings & TVL_001/TVL_002/TVL_004

| Sibling | Composition with TVL_003 |
|---|---|
| **TVL_001 Travel** | **Parent.** The TVL_001 closure pass for TVL_003 is **schema + behavioral** (MED-1 fix /review-impl — not "schema-only"). *Schema*: the `TravelMode` enum bumped 2 → 5 (R3); a `mount_id: Option<MountId>` additive field on `actor_travel_state` (`schema_version` bump per I14); a `mount_id` additive field on the `Travel:Initiate` payload. *Behavioral* — three changes: (1) TVL-V5 `mode-available` — the `travel.mode_unavailable_v1plus30d` reject is lifted for the four activated modes; (2) TVL-V9 `mode-route-compatibility` — its check becomes the expanded §5.1 matrix; (3) the `speed_modifier(mode)` factor (§4.3) enters BOTH the `Scheduled:TravelTick` advancement formula and the `expected_arrival_fiction_time` computation (TVL_001's stored formula has no modifier). |
| **TVL_002 Composite Travel** | Riding a mount on a multi-segment composite journey is **deferred V1+30d+** (§5.5 / TVM-D5). TVL_002 as shipped rejects every non-OnFoot composite (CTV-V9 `composite_mode_unavailable_v1plus30d`); enabling composite-with-mount needs a TVL_002 closure pass (relax CTV-V9 to uniform activated modes + add a `mount_id` to `CompositeTravel:Initiate`/`composite_journey`). V1+30d+ TVL_003 ships mounts for atomic TVL_001 journeys only; mixed-mode composite is additionally TVL_002 CTV-D5. |
| **TVL_004 Travel Encounters** | An encounter pauses the journey (TVL_004 §5.2); the mount stays `InTransit` through the pause and resumes with it. V1+30d+ TVL_004 encounter outcomes do **not** touch the `mount` aggregate — mount theft / loss / injury in a `Combat` or `Hazard` encounter is deferred (TVM-D4). A TVL_004 `Hazard` `DivertToCell` reroute that Cancels the journey re-stables the mount at the divert cell (§5.3). |
| **GEO_004 ROUTE_001** | `RouteKind` is the §5.1 compatibility-matrix key; `route.default_fiction_duration` is the value the speed modifier scales. ROUTE_001's `SeaLane` + `RiverNavigation` routes finally get a consumer (`ByShip` / `ByBoat`). |
| **GEO_003 SET_001** | Settlements are where mounts sit `AtCell` between journeys (a stabled horse, a docked ship). No SET_001 schema integration V1+30d+ — a stable/dock *facility* (gating where a mount may be acquired or kept) is deferred with the TVM-D1 economy work. |
| **RES_001** | V1+30d+ provisions cost is TVL_001's distance-based model, UNCHANGED by the mount. V2+: mount purchase price + mount-feed provisions (TVM-D1 / TVM-D2) integrate with RES_001 currency + consumables. |
| **TDIL_001** | The speed modifier shortens the journey's fiction-duration → `actor_clock + body_clock` advance less in total for the same distance (the point of a faster mount). No TDIL schema change; the modifier is a factor in the existing tick formula. |
| **AIT_001** | Tracked-tier discipline — only PC + Tracked NPCs travel, so only they own/ride mounts (TVM-V9). A mount is NOT an AIT entity and NOT an EF_001 entity — it is a lightweight per-mount `mount` aggregate (avoids the entity-count explosion AIT_001 guards against, same reasoning as TVL_004's abstract participants). |
| **NPC_002 Chorus** | A Tracked NPC's choice to ride is Chorus-driven — the LLM picks `mode` + `mount_id` in the `Travel:Initiate` it proposes, same flow as a PC. |
| **EF_001 Entity Foundation** | `actor.current_cell_id` is read by TVM-V4 (the mount must be at the actor's cell). No new EF_001 field — `mount_id` lives on `actor_travel_state`, not `entity_binding`. |

---

## §11 RealityManifest extension

**One new RealityManifest field** — author-declared starting mounts:

```rust
pub canonical_mounts: Option<Vec<MountDecl>>,        // None → the reality starts with no mounts

pub struct MountDecl {
    pub owner_actor_ref: ActorRef,                   // a Tracked actor declared elsewhere in the manifest
    pub kind: MountKind,
    pub spawn_cell: CellId,                          // where the mount sits AtCell at reality seed
    pub display_name: I18nBundle,
}
```

- `canonical_mounts` is **OPTIONAL** V1+30d+ — a reality that omits it simply starts with no mounts; all travel is OnFoot until an admin `Forge:GrantMount`.
- Validated at reality seed: each `owner_actor_ref` resolves to a Tracked actor (TVM-V9); each `spawn_cell ∈ wg.cells`. The system does **not** validate that `spawn_cell` actually has a route compatible with the mount's `kind` (LOW-4 /review-impl — accepted): a `Ship` declared at a landlocked cell, or a `Horse` at a cell with no Road/Trail, is *valid but unusable* until its owner moves it somewhere with a compatible route. Mount-kind ↔ spawn-cell suitability is an author/admin responsibility V1+30d+, not a system-enforced constraint (it would require route-adjacency analysis at seed time; a V2+ refinement could warn).
- `MountKind`, the §4.2 mapping, the §4.3 speed modifiers, and the §5.1 compatibility matrix are all **hardcoded V1+30d+** — not author-tunable. Author-tunable speed modifiers + custom mount kinds are deferred V2+ (TVM-D6).

Bootstrap order: TVL_003 V1+30d+ activates AFTER TVL_001 V1+30d ships (the `TravelMode` enum + `actor_travel_state` must exist to be extended). Realities pre-TVL_001-ship cannot travel, hence cannot mount.

V1+30d+ feature-flag: `services/travel-service` config `mount_travel_enabled: bool` (default true V1+30d+; false leaves only TVL_001 OnFoot travel — `Travel:Initiate` with a non-OnFoot mode then rejects `travel.mode_unavailable_v1plus30d`, exactly as pre-TVL_003). Mid-life flip on an existing reality FORBIDDEN per `generator_pipeline_version` discipline.

---

## §12 Sequences

### 12.1 PC rides Khai Phong → Tương Dương on the Imperial Highway

```
lý_minh owns mount m_warhorse (Horse), location AtCell(khai_phong). lý_minh is at khai_phong.
lý_minh issues Travel:Initiate { route_id: imperial_highway, mode: OnHorseback,
  mount_id: Some(m_warhorse), direction: Forward }:
  ↓ TVL_001 gates pass; TVL_003 gates:
    TVM-V6 (OnHorseback ⇒ mount_id Some) → pass.
    TVM-V1 (m_warhorse exists) / TVM-V2 (owned by lý_minh) → pass.
    TVM-V3 (Horse → OnHorseback per §4.2, matches `mode`) → pass.
    TVM-V4 (m_warhorse.location == AtCell(khai_phong) == lý_minh.current_cell_id) → pass.
    TVM-V5 (not InTransit) → pass.
    TVM-V7 (OnHorseback × Road ∈ §5.1 matrix) → pass.
  ↓ EVT-T3: actor_travel_state created — mode=OnHorseback, mount_id=Some(m_warhorse);
    route.default_fiction_duration = 24h; expected_arrival = initiated + 24h × 0.4 = 9.6h.
  ↓ EVT-T3 cascade: m_warhorse.location = InTransit(journey_id).
  ↓ provisions: distance_units=24 → food 24 / water 48 deducted (TVL_001, UNCHANGED — the horse
    makes the trip faster, not shorter; distance is identical).
  ↓ Scheduled:TravelTick advances progress by tick_duration / (24h × 0.4 = 9.6h) per tick →
    the journey completes in ~40% of the OnFoot tick count.
  ↓ Travel:Arrive at tuong_duong: m_warhorse.location = AtCell(tuong_duong). lý_minh + horse
    are both now at Tương Dương, ready for the next leg.
```

### 12.2 Travel rejected — mount not where the actor is

```
lý_minh (now at tuong_duong) issues Travel:Initiate { mode: OnHorseback, mount_id: Some(m_warhorse) }
for a route onward — but m_warhorse.location is AtCell(tuong_duong), so this is fine. Counter-case:
lý_minh teleported / walked to lam_an WITHOUT the horse; the horse is still AtCell(tuong_duong):
  ↓ TVM-V4 mount-at-origin: m_warhorse.location AtCell(tuong_duong) != AtCell(lý_minh.current_cell_id
    = lam_an) → REJECT travel.mount_not_at_origin.
  ↓ UI: "Vật cưỡi không ở điểm khởi hành của bạn." — lý_minh must travel OnFoot, or retrieve the horse.
```

### 12.3 Ship across a SeaLane — the route that OnFoot could never use

```
A PC at a coastal port cell owns mount m_junk (Ship). A SeaLane route connects the port to an
island settlement. Travel:Initiate { route_id: sealane_x, mode: ByShip, mount_id: Some(m_junk) }:
  ↓ TVM-V3 (Ship → ByShip) / TVM-V7 (ByShip × SeaLane ∈ §5.1 matrix) → pass.
  ↓ journey proceeds; expected_arrival uses speed_modifier(ByShip) = 0.3.
  Contrast: the same Travel:Initiate with mode=OnFoot → TVM-V7 (OnFoot × SeaLane ∉ matrix) →
  REJECT travel.mode_route_incompatible. The SeaLane is reachable ONLY by a vessel.
```

### 12.4 Composite journey + mount — deferred V1+30d+

```
A PC tries to ride a horse on a TVL_002 multi-segment composite journey, issuing
CompositeTravel:Initiate { destination_cell_id, mode: OnHorseback }:
  ↓ TVL_002's CTV-V9 (mode-available-v1plus30d) fires → REJECT composite_mode_unavailable_v1plus30d.
  V1+30d+ a TVL_002 composite is OnFoot-only — composite-with-mount is deferred (§5.5 / TVM-D5);
  it needs a TVL_002 closure pass (relax CTV-V9 + add a mount_id to CompositeTravel:Initiate /
  composite_journey). To ride to a multi-hop destination V1+30d+, the PC issues one mounted atomic
  TVL_001 Travel:Initiate per Route segment, leading the mount along manually (the mount is AtCell
  the destination after each leg, ready for the next).
```

### 12.5 Admin grants a mount

```
A Forge admin issues Forge:GrantMount { owner_actor_id: tieu_long_nu, kind: Horse,
  cell_id: cao_thien_dai, display_name: "Tiểu Long Nữ's white steed" }:
  ↓ TVM-V8 (cao_thien_dai ∈ wg.cells) / TVM-V9 (tieu_long_nu is Tracked) → pass.
  ↓ EVT-T3: mount row created — location AtCell(cao_thien_dai), acquired_via ForgeGrant.
```

---

## §13 Acceptance criteria

15 V1+30d+-testable acceptance scenarios AC-TVL-46..60. LOCK granted when ≥10 pass integration tests against the `travel-service` reference impl + TVL_001 + ROUTE_001 fixtures.

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-TVL-46** | `Travel:Initiate` with `mode=OnHorseback` + a valid owned `Horse` mount at origin → `actor_travel_state` created with `mount_id=Some`, `expected_arrival` scaled by `speed_modifier(OnHorseback)=0.4`; the mount → `InTransit`. | — |
| **AC-TVL-47** | The mounted journey reaches `Travel:Arrive` → the mount → `AtCell(destination)`. | — |
| **AC-TVL-48** | `Travel:Initiate` with `mode=ByShip` on a `SeaLane` route → accepted; the same with `mode=OnFoot` → rejected (a SeaLane is vessel-only). | `travel.mode_route_incompatible` (OnFoot case) |
| **AC-TVL-49** | `Travel:Initiate` `mode=OnHorseback` with `mount_id=None` → reject; `mode=OnFoot` with `mount_id=Some` → reject. | `travel.mode_requires_mount` |
| **AC-TVL-50** | `Travel:Initiate` naming a mount whose `kind` does not map to the chosen `mode` (e.g. a `Ship` with `mode=OnHorseback`) → reject. | `travel.mount_kind_mode_mismatch` |
| **AC-TVL-51** | `Travel:Initiate` naming a mount that is `AtCell` a different cell than the actor → reject. | `travel.mount_not_at_origin` |
| **AC-TVL-52** | `Travel:Initiate` naming a mount that is already `InTransit` on another journey → reject. | `travel.mount_in_transit` |
| **AC-TVL-53** | `Travel:Initiate` naming a mount the actor does not own → reject. | `travel.mount_not_owned` |
| **AC-TVL-54** | `Travel:Initiate` `mode=OnHorseback` on a `MountainPass` route → reject (Horse cannot ride a MountainPass per the §5.1 matrix). | `travel.mode_route_incompatible` |
| **AC-TVL-55** | `Travel:Initiate` `mode=ByCarriage` on a `Trail` route → reject (Carriage is Road-only). | `travel.mode_route_incompatible` |
| **AC-TVL-56** | A mounted journey's provisions cost equals the OnFoot cost for the same route (distance-based, unchanged by the mount). | — |
| **AC-TVL-57** | `Forge:GrantMount` to a Tracked actor at a valid cell → `mount` row created `AtCell`, `acquired_via=ForgeGrant`. | — |
| **AC-TVL-58** | A reality with a `canonical_mounts` `MountDecl` → at seed, the `mount` row exists `AtCell(spawn_cell)`, `acquired_via=CanonicalSeed`. | — |
| **AC-TVL-59** | `CompositeTravel:Initiate` with a non-OnFoot `mode` → reject — composite-with-mount is deferred V1+30d+ (TVM-D5); TVL_002's CTV-V9 is unchanged by TVL_003. | `travel.composite_mode_unavailable_v1plus30d` (TVL_002 rule_id) |
| **AC-TVL-60** | Snapshot fork mid-mounted-journey → child inherits the `mount` row (`InTransit`) + the `actor_travel_state` bit-exactly; child + parent advance the journey independently. | — |

---

## §14 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **TVM-D1** | Market mount purchase / rental + ownership transfer/sale + settlement stable/dock facilities | V2+ | Needs an economy (RES_001 currency at point-of-sale) + a settlement-facility substrate (which settlements have a stable / a dock). V1+30d+ acquisition is canonical + Forge only. |
| **TVM-D2** | Mount condition — stamina, fatigue, injury, mount-feed provisions | V2+ | V1+30d+ a mount is stateless beyond `location`. Mount-feed would add a per-league consumable cost alongside the actor's. |
| **TVM-D3** | Multi-passenger vehicles — a carriage / ship carrying several actors or a TVL_005 travel party | V1+30d+ | Requires TVL_005 Group/Party Travel. V1+30d+ one mount carries its one owner. |
| **TVM-D4** | Mount-affecting encounter outcomes — a TVL_004 `Combat`/`Hazard` encounter stealing, killing, or injuring a mount | V1+30d+ | V1+30d+ TVL_004 `EncounterOutcome` does not touch the `mount` aggregate; a follow-up adds a `mount_loss` outcome field. |
| **TVM-D5** | Composite-journey travel with a mount — *uniform-mode* (one mount, every segment the same non-OnFoot mode) AND *mixed-mode* (an OnFoot segment + a ByShip segment in one composite) | V1+30d+ | Both need a **TVL_002 closure pass** — TVL_002 as shipped rejects every non-OnFoot composite (CTV-V9). The closure pass must: relax CTV-V9 to allow a uniform activated `TravelMode`; add a `mount_id` to the `CompositeTravel:Initiate` payload + the `composite_journey` aggregate; add a per-segment mode↔route check + the InTransit-re-point mount lifecycle. The mixed-mode half is additionally TVL_002 CTV-D5 (the dual-subgraph composite Dijkstra). V1+30d+ TVL_003 ships mounts for atomic TVL_001 journeys only. |
| **TVM-D6** | Author-tunable speed modifiers + custom author-declared `MountKind`s | V2+ | V1+30d+ the 4 kinds, the §4.2 mapping, the §4.3 modifiers, and the §5.1 matrix are hardcoded. |
| **TVM-D7** | Mount death/retirement lifecycle + a `mount` terminal status + **owner-death handling** | V2+ | V1+30d+ a `mount` row, once created, persists for the reality's life with no destroy path; an owner's death simply orphans the mount (it sits `AtCell`, unusable — `owner_actor_id` is immutable and only the owner passes TVM-V2). A future pass adds reassignment/escheat on owner death. NOTE: an owner dying *mid-mounted-journey* is a pre-existing TVL_001 gap (TVL_001 does not spec actor-death-mid-journey) that TVL_003 inherits — resolve it in the TVL_001 closure pass or a mortality-integration pass. |
| **TVM-D8** | Soul-projection / astral mounts + flight (a sword-flight `御剑` cultivation conveyance) | V2+ | Per wuxia/xianxia archetype canon; pairs with TVL_001 TVL-D7 soul-projection travel. A flight mode would need a route layer that doesn't exist (point-to-point over terrain). |
| **TVM-D9** | Stabling fees / mount upkeep over idle time | V2+ | Couples with TVM-D1's facility substrate + TVM-D2 condition. |

---

## §15 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **TVM-Q1** | The TVL_001 closure pass — `TravelMode` enum bump + `actor_travel_state.mount_id` + `Travel:Initiate` payload field. Schema_version coordination? | V1+30d+: YES — `actor_travel_state` `schema_version` bumps per I14 (default-tolerant readers: pre-bump rows = `mount_id` None). The `TravelMode` bump is an R3 closed-enum additive evolution. Applied via the TVL_001 closure pass at TVL_003 ship. The closure pass now serves three consumers (TVL_002 `composite_journey_id` · TVL_004 `encounter_schedule` · TVL_003 `mount_id` + `TravelMode`) — sequence the three `schema_version` bumps; land them in one closure-pass commit. |
| **TVM-Q2** | A mount left `AtCell` far from its owner — is it ever auto-returned, or stranded forever? | V1+30d+: stranded — the mount stays `AtCell` wherever the last journey left it; the owner must physically return to ride it again (TVM-V4 enforces). This is intended friction. V2+ stabling networks / mount-retrieval services pair with TVM-D1. |
| **TVM-Q3** | Can two actors share a mount (sequentially — A rides it, leaves it, B rides it)? | V1+30d+: NO — `owner_actor_id` is immutable; only the owner passes TVM-V2. Ownership transfer is TVM-D1. A shared-use model would also need TVM-D3 multi-passenger. |
| **TVM-Q4** | Does a mount occupy the actor's RES_001 `resource_inventory`, or is it purely the `mount` aggregate? | V1+30d+: purely the `mount` aggregate — a mount is NOT an inventory item (it has location + identity a fungible counter cannot carry). The `owner_actor_id` FK is the only link to the actor. |
| **TVM-Q5** | What if a route is removed (ROUTE_001 `RemoveRoute`) while a mount is `InTransit` on it? | V1+30d+: TVL_001's TVL-V14 (`route_in_use_by_journey`) already blocks `RemoveRoute` on a route with an Active journey — and a mounted journey IS an Active journey. So the mount is protected transitively; no new validator. |
| **TVM-Q6** | Storage — monolithic `Vec<Mount>` per reality vs per-mount rows? | V1+30d+: sparse aggregate per `mount_id`, event-sourced via T2/Reality discipline (same as the other TVL aggregates — TVL-Q7 / CTV-Q6 / CTE-Q7). Typical count is small (a handful of mounts per reality V1+30d+). |
| **TVM-Q7** | Does `ByCarriage` need a built `Road` specifically, or would a `Trail` do at reduced speed? | V1+30d+: `Road`-only (the §5.1 matrix) — a carriage is a wheeled vehicle that needs a built roadbed; a Trail is a footpath. A reduced-speed Trail allowance is a V2+ author-tunable refinement (TVM-D6). |

---

## §16 Cross-references

- [`cat_00_TVL_travel_foundation.md`](../../catalog/cat_00_TVL_travel_foundation.md) — catalog; `TVL-*` namespace; TVL_003 sub-section
- [`_index.md`](_index.md) — folder index; TVL_003 row added 2026-05-16
- [`TVL_001 Travel`](TVL_001_travel.md) — parent; `TravelMode` enum (bumped 2 → 5) + `actor_travel_state` (`mount_id` field) + `Travel:Initiate` payload
- [`TVL_002 Composite Travel`](TVL_002_composite_travel.md) — composite-with-mount deferred V1+30d+ (TVM-D5 — needs a TVL_002 closure pass relaxing CTV-V9)
- [`TVL_004 Travel Encounters`](TVL_004_travel_encounters.md) — mount stays InTransit through an encounter pause; mount-affecting outcomes deferred TVM-D4
- [`GEO_004 ROUTE_001`](../00_geography/GEO_004_route_network_generator.md) — `RouteKind` matrix key; `route.default_fiction_duration`
- [`GEO_003 SET_001`](../00_geography/GEO_003_settlement_generator.md) — settlements as mount stabling/docking cells
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) — V2+ mount purchase + mount-feed (TVM-D1 / TVM-D2)
- [`AIT_001`](../03_actor_substrate/AIT_001_ai_tier_foundation.md) — Tracked-tier discipline; mounts are not AIT entities
- [`TDIL_001`](../03_actor_substrate/TDIL_001_time_dilation_foundation.md) — the speed modifier scales journey fiction-duration
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — NEW `mount` aggregate row
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — `TravelMode` enum bump + `actor_travel_state.mount_id` cross-feature dependency + `travel.*` mount rule_ids (§1.4); NEW EVT-T8 sub-shape `Forge:GrantMount` (§4)

---

## §17 Implementation readiness

**Design layer (this commit):** ✅ NEW `mount` aggregate schema + 3 V1+30d+ closed enums (`MountKind` / `MountLocation` / `MountAcquisition`) + the TVL_001 `TravelMode` enum bump 2 → 5 + 1 cross-feature additive field on `actor_travel_state` (`mount_id`) + the `Travel:Initiate` payload `mount_id` field + the §4.2 kind→mode mapping + the §4.3 speed-modifier table + the §5.1 mode↔route compatibility matrix + 10 validator slots (TVM-V1..V10) + 10 `travel.*` rule_ids (8 new + 2 reused) + 9 deferrals + 7 open questions + RealityManifest `canonical_mounts` extension + cross-feature coordination with TVL_001/TVL_002/TVL_004/ROUTE_001/SET_001/RES_001/TDIL_001/AIT_001 + 15 acceptance scenarios — all declared.

**Implementation phase (V1+30d+):** 📦 `mount` aggregate + apply_delta logic in `travel-service`; the **TVL_001 closure pass — schema + behavioral** (MED-1 fix /review-impl — *schema*: `TravelMode` enum 2 → 5 R3 bump, `actor_travel_state.mount_id` additive field + `schema_version` bump per I14, `Travel:Initiate` payload `mount_id` field; *behavioral*: TVL-V5 `mode-available` lifts the `mode_unavailable_v1plus30d` reject for the four activated modes, TVL-V9 `mode-route-compatibility` becomes the expanded §5.1 matrix, and the `speed_modifier(mode)` factor enters both the `Scheduled:TravelTick` advancement formula and the `expected_arrival_fiction_time` computation); `Forge:GrantMount` handler; the engine speed-modifier + compatibility-matrix tables; chat-service `[TRAVEL_CONTEXT]` `mode` + mount `display_name` extension; CI gates: speed-modifier determinism (a mounted journey's `progress_fraction` sequence is bit-identical given the same seed + mode), the §5.1 matrix is total over `TravelMode × RouteKind`, `mount.location` invariant (`InTransit` ⇔ exactly one Active journey references the mount).

**Downstream consumer integration (V1+30d+ / V2+):** 📦 TVL_002 CTV-D5 mixed-mode composite (consumes the `TravelMode` variants — TVM-D5) · TVL_005 Group/Party Travel (multi-passenger vehicles — TVM-D3) · TVL_004 mount-affecting encounter outcomes (TVM-D4) · RES_001 V2+ mount economy (TVM-D1 / TVM-D2).

**Status:** DRAFT 2026-05-16. CANDIDATE-LOCK upon §13 acceptance scenarios passing integration tests against the reference `travel-service` implementation + the TVL_001 closure pass landing. LOCK upon downstream consumer integration (TVL_002 CTV-D5 activates mixed-mode composite; TVL_005 ships multi-passenger).

**Third TVL feature by number; the conveyance layer.** TVL_001 built `TravelMode` 2-variant with `ByBoat` schema-reserved precisely for this; TVL_003 activates it and adds the rest — the ROUTE_001 water routes finally have vessels, travel speed becomes a real choice, and TVL_002's multi-modal composite (CTV-D5) is unblocked.
