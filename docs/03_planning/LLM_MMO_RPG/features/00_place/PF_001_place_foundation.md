# PF_001 — Place Foundation

> **Conversational name:** "Place Foundation" (PF). The semantic substrate that defines what counts as a meaningful in-fiction location — a `place` aggregate per cell channel, a closed `PlaceType` taxonomy, an explicit connection graph for Travel, structural state machine for in-fiction degradation, fixture seed declarations for canonical EnvObjects, RealityManifest extension for bootstrap, and time-lapse evolution hooks (author-edit + in-fiction-event V1; scheduled decay V1+30d).
>
> **Category:** PF — Place Foundation (foundation tier; sibling of EF_001 Entity Foundation)
> **Status:** **DRAFT 2026-04-26** (Option C max scope per user direction "place foundation trước spawn PC/NPC")
> **Catalog refs:** [`cat_00_PF_place_foundation.md`](../../catalog/cat_00_PF_place_foundation.md) — owns `PF-*` namespace (`PF-A*` axioms · `PF-D*` deferrals · `PF-Q*` open questions)
> **Builds on:** [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §16 RealityManifest (extends with `places: Vec<PlaceDecl>`) + §3.2 scene_state (PF_001 owns semantic identity; PL_001 keeps runtime ambient), [EF_001 Entity Foundation](../00_entity/EF_001_entity_foundation.md) (`entity_binding.location.InCell { cell_id }` cross-references PlaceId; fixture-seed declarations instantiate EnvObject entities; §6.1 cascade rules apply when Place→Destroyed), [DP-Ch1..Ch53](../../06_data_plane/) channel hierarchy (Place sits 1:1 with cell channels), [07_event_model](../../07_event_model/) Option C taxonomy (T3 Derived for place deltas; T4 System for PlaceBorn; T8 Administrative for Forge edits)
> **Resolves:** Spawn-empty-place gap (PL_001 cells had no semantic identity beyond ambient; LLM lacked context for scene narration when actors arrived) · EnvObject orphan gap (EF_001 declared `EnvObject(EnvObjectId)` variant but no feature pre-seeded EnvObjects into realities) · Time-lapse undefined (no feature owned "places evolve when fiction-time advances or in-fiction events propagate")
> **Defers to:** future EnvObject feature for `env_object` body aggregate (PF_001 owns fixture-seed declarations + canonical instantiation; EnvObject body deferred) · future Item feature for Item bodies at places · PCS_001 / NPC_001 for actor spawn rules (PF_001 provides the semantic place context; spawn-into-place is consumer responsibility) · WA_002 Heresy V1+ if per-place contamination rules needed (currently per-actor only)

---

## §1 Why this exists

Three concrete gaps in the V1 design surface that PF_001 closes:

**Gap 1 — Spawn mechanically possible, narratively empty.** PL_001 §16 RealityManifest has `root_channel_tree` (continent/country/district/town/cell hierarchy) + `canonical_actors`. Bootstrap can place an actor at a cell — but a cell is just a channel + scene_state (ambient: weather, crowd, freeform `notable_props` strings). There's no semantic identity: PlaceType (tavern? forest? throne room?), canon-grounded description, fixture inventory (EnvObjects), or connection graph for Travel destinations. When PC arrives, LLM has insufficient context for scene narration.

**Gap 2 — EF_001 EnvObject variant orphaned.** EF_001 declared `EnvObject(EnvObjectId)` as a V1 EntityId variant (door, wall, table, statue addressable for Examine). But no feature owned the entry point: who declares "this tavern has a door, a counter, a fireplace at canonical seed time"? PL_001 RealityManifest didn't have `canonical_env_objects`. EnvObjects must originate somewhere V1 — PF_001 fixture-seed declarations are that origin.

**Gap 3 — Time-lapse undefined.** PL_001 fiction_clock advances but no feature owned "places evolve when fiction-time advances OR in-fiction events propagate". Three real V1 scenarios untouched:
- Author-edit (Forge): "the tavern is now boarded up" — needs a write path
- In-fiction event: PC Strikes the wall enough times → tavern damaged → references to fixtures behind that wall now fail → cascade into EF_001 lifecycle
- V1+30d scheduled decay: forest grows back after fire; market crowds peak at midday — Generator framework was built but no feature consumed it for places

PF_001 owns the semantic foundation; consumer features (PCS_001 / NPC_001 / future EnvObject / future Item / future Quest) inherit place context.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **PlaceId** | Newtype `pub struct PlaceId(pub ChannelId)` — V1 1:1 with cell channels | Place identity = the cell channel ID. Higher-tier channels (continent/country/district/town) DO NOT have place rows V1 (aggregation tiers, not in-fiction places). V1+ multi-place-per-cell deferred (PF-D4). |
| **PlaceType** | Closed enum 10 V1 kinds (see §4) | `Residence \| Tavern \| Marketplace \| Temple \| Workshop \| OfficialHall \| Road \| Crossroads \| Wilderness \| Cave`. V1+ reservations (PF-D1): `Dungeon \| Battlefield \| Vehicle \| ShipDeck \| DreamRealm \| etc.` |
| **StructuralState** | Closed enum 4-state — `Pristine \| Damaged \| Destroyed \| Restored` | "Restored" explicitly distinct from Pristine — preserves audit precision (rebuilt-after-destruction differs from original-untouched). Forbidden transitions enforced at write-time (§7). |
| **NarrativeDrift** | Freeform `serde_json::Value` field on `place` | Per-reality drift accumulator: "the front door is now red", "scratch marks on table". Distinguished from StructuralState (closed enum) for queryability — operators ask "is tavern operational?" via StructuralState; LLM ingests drift JSON for descriptive flavor. |
| **ConnectionDecl** | Per-place `Vec<ConnectionDecl>` declaring horizontal edges to other places | DP channel hierarchy gives parent↔child connections implicitly; ConnectionDecl is for HORIZONTAL/non-hierarchy edges (back door of tavern to alley; secret tunnel between two unrelated cells; one-way magical portal). |
| **ConnectionKind** | Closed enum — `Public \| Private \| Locked \| Hidden \| OneWay` | Public = anyone can pass. Private = canonical residents only. Locked = requires key/permit Embedded keyhole (V1: reject with `place.connection_locked`; V1+ key-matching deferred). Hidden = discoverable via Examine; visible only after first discovery. OneWay = enter but not exit (e.g., one-way portal). |
| **EnvObjectSeedDecl** | Fixture-seed declaration owned by Place | `{ seed_uid, envobject_kind, slot_id, default_affordances, initial_state }`. Canonical bootstrap deterministically instantiates EnvObject entities from these seeds. Future EnvObject feature owns the body; PF_001 only declares which fixtures exist where. |
| **EnvObjectKind** | Closed enum — `Door \| Wall \| Table \| Statue \| Fountain \| Bed \| Chest \| Throne \| Altar \| Window \| Sign` | 11 V1 kinds covering common fixture taxonomy. V1+ extensions per future EnvObject feature design. |
| **PlaceDecl** | RealityManifest extension element — see §9 | Author-supplied bootstrap input declaring all V1 places at reality creation. Required: every cell channel must have a PlaceDecl at bootstrap; cells without decl reject `place.missing_decl`. |
| **CanonRef on Place** | `place.canon_ref: BookCanonRef` — book-grounded source | Same canon-ref pattern as NPC_001 / WA_001 — every place anchored to book source unless author-created (then canon_ref = `BookCanonRef::AuthorCreated { reality_id, fiction_time }`). |
| **PlaceTransitionEvent** | The lifecycle envelope for place mutations | Captures structural-state changes + narrative-drift edits + author-edits — emitted as EVT-T3 Derived for state changes; EVT-T8 Administrative for author edits (§2.5). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

PF_001 introduces no new EVT-T* category. Maps onto existing mechanism-level taxonomy:

| PF event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Place birth (canonical seed at RealityManifest bootstrap) | **EVT-T4 System** | `PlaceBorn` | DP-Internal RealityBootstrapper (Synthetic actor) | Emitted alongside cell-channel `MemberJoined` for canonical actors who start at this cell |
| Place runtime spawn (V1+: Forge author creates new place at runtime) | **EVT-T8 Administrative** | `Forge:CreatePlace` | world-service | V1+: Author-edit feature; PF-D7 procedural generation deferred |
| Place structural-state transition (Pristine ↔ Damaged ↔ Destroyed ↔ Restored) | **EVT-T3 Derived** | `aggregate_type=place` (structural_state field delta) | Aggregate-Owner role (world-service post-validate) | Causal-ref to triggering EVT-T1 Submitted (PL_005 Strike Destructive) or EVT-T8 Administrative (Forge edit) |
| Place narrative-drift edit | **EVT-T3 Derived** | `aggregate_type=place` (narrative_drift field delta) | Aggregate-Owner role | Triggered by author-edit OR V1+ in-fiction LLM proposal |
| Author-edit place (rename / change type / update connections / edit fixtures) | **EVT-T8 Administrative** | `Forge:EditPlace { place_id, edit_kind, before, after }` | WA_003 Forge | Audit-grade; same pattern as ForgeEdit for other aggregates |
| Place destruction cascade (Place → Destroyed propagates into embedded EnvObjects + Items at cell) | **EVT-T3 Derived** (multiple `aggregate_type=entity_binding` deltas via EF_001 §6.1) | (multiple) | Aggregate-Owner role | Emitted as a single atomic batch with the place transition; per EF_001 §6.1 cascade contract |
| V1+ scheduled place decay (forest regrowth, market crowd cycle) | **EVT-T5 Generated** | `Scheduled:PlaceDecay` | Future world-rule-scheduler (V1+30d) | Generator framework EVT-G* ready; PF-D3 reserves the slot |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. EVT-T4 System sub-types row gains `PlaceBorn` (PF_001-owned alongside EF_001's `EntityBorn`); EVT-T3 Derived sub-types row gains `aggregate_type=place`.

---

## §3 Aggregate inventory

One aggregate owned by PF_001:

### 3.1 `place` (T2 / Channel-cell scope) — PRIMARY

```rust
#[derive(Aggregate)]
#[dp(type_name = "place", tier = "T2", scope = "channel")]  // bound to cell channel via PlaceId = ChannelId
pub struct Place {
    pub place_id: PlaceId,                            // V1: PlaceId(ChannelId) — 1:1 with cell channel
    pub place_type: PlaceType,                        // closed enum (§4)
    pub canon_ref: BookCanonRef,                      // book-grounded source; AuthorCreated for runtime-created
    pub display_name: LocalizedName,                  // multi-locale per LX (vi V1; en V1+)
    pub structural_state: StructuralState,            // closed enum 4-state (§7)
    pub narrative_drift: serde_json::Value,           // freeform per-reality drift
    pub connections: Vec<ConnectionDecl>,             // explicit horizontal edges (§6)
    pub fixture_seed: Vec<EnvObjectSeedDecl>,         // canonical EnvObjects at this place (§8)
    pub last_structural_change_fiction_time: FictionTime,
    pub last_narrative_drift_fiction_time: FictionTime,
}

pub struct PlaceId(pub ChannelId);                    // V1 invariant: PlaceId.0 IS the cell channel id

pub struct LocalizedName {
    pub vi: String,                                   // required V1 (project primary locale)
    pub en: Option<String>,                           // V1+ optional
}

pub struct ConnectionDecl {
    pub to_place: PlaceId,
    pub kind: ConnectionKind,                         // §6
    pub bidirectional: bool,                          // false → reverse connection must be declared on to_place separately
    pub canon_ref: Option<BookCanonRef>,              // book-grounded path; None for author-added
    pub gate_seed_uid: Option<SeedUid>,               // for Locked: which fixture (door/keyhole) gates this connection — references fixture_seed[].seed_uid
}

pub struct EnvObjectSeedDecl {
    pub seed_uid: SeedUid,                            // deterministic ID stable across reality clones (UUID v5 from place_id + slot_id)
    pub envobject_kind: EnvObjectKind,                // closed enum (§2)
    pub slot_id: String,                              // stable position descriptor ("front_door", "main_counter", "fireplace_north_wall")
    pub default_affordances: AffordanceSet,           // EF_001 AffordanceFlag bitset; future EnvObject feature uses for entity_binding override
    pub initial_state: serde_json::Value,             // future EnvObject feature interprets per-kind state schema
}
```

**Rules:**
- One row per `place_id` (= one row per cell channel V1). Primary key conflict = `place.duplicate_place`.
- Every cell channel MUST have a `place` row at bootstrap. Cells without place reject runtime ops with `place.missing_decl` (validated at first-use, not at channel creation — channel can exist briefly during bootstrap before place lands).
- Higher-tier channels (continent/country/district/town) MUST NOT have place rows V1. Validated by `place_id.0` resolving to a cell-tier channel per DP channel-tree query.
- `canon_ref` is REQUIRED. Author-created places use `BookCanonRef::AuthorCreated { reality_id, fiction_time }`.
- `connections[].to_place` MUST resolve to existing place row (validated at write); orphan connections reject `place.connection_target_unknown`.
- `fixture_seed[].seed_uid` MUST be unique within the place's seed list; duplicate uids reject `place.fixture_seed_uid_collision`.
- `structural_state` transitions follow §7 state machine; forbidden transitions reject `place.invalid_structural_transition`.

---

## §4 PlaceType closed enum

```rust
pub enum PlaceType {
    Residence,      // private home, apartment, dwelling
    Tavern,         // inn, bar, restaurant, public-meeting commercial
    Marketplace,    // bazaar, shop, trade ground
    Temple,         // religious / spiritual gathering site
    Workshop,       // smith, tailor, alchemist, craft production
    OfficialHall,   // government, court, magistrate, throne room
    Road,           // path, street, highway between places
    Crossroads,     // junction with multiple connections (special routing)
    Wilderness,     // forest, meadow, mountain, generic outdoor
    Cave,           // underground, dungeon precursor
}
```

**Why closed:** compile-time exhaustiveness — every consumer (PL_005 Examine narration, NPC routine scheduler, LLM prompt assembly) MUST handle each PlaceType OR explicitly mark `_ =>`. Catches missing-handler bugs at compile time.

**Per-type defaults V1** (used by Examine narrator + LLM context assembly):

| PlaceType | Default ambient cues | Default fixture-kinds expected | LLM scene-prompt anchor |
|---|---|---|---|
| Residence | Quiet; private; sparse | Door · Bed · Table · Window | "interior of a private dwelling" |
| Tavern | Lively; smell of food/drink; chatter | Door · Table · Counter (sign as Door subtype if signage) · Fireplace (Wall) | "interior of a tavern; patrons + staff" |
| Marketplace | Bustling; merchants calling; multi-stall | Sign · Table (stall) · Door (gate) | "open-air market; stalls and traders" |
| Temple | Reverent; incense/candles; quiet voices | Altar · Statue · Door · Window | "religious sanctuary; devotional fixtures" |
| Workshop | Tools clinking; smoke/heat; concentration | Table (workbench) · Wall (tool rack) · Door · Chest | "production workshop; tools and materials" |
| OfficialHall | Formal; echoing; protocol | Throne · Table · Door · Statue | "seat of authority; ceremonial fixtures" |
| Road | Open; weather-exposed; transient | Sign (waypost) · Statue (milestone) | "thoroughfare between locations" |
| Crossroads | Multiple paths visible; landmark | Sign · Statue · Fountain | "junction of multiple paths" |
| Wilderness | Natural; weather; sparse | (sparse — usually no fixtures or only Statue/Sign for landmarks) | "natural outdoor location" |
| Cave | Echoing; damp/cold; limited light | Wall · (rare) Altar / Throne for Lair-type caves | "subterranean space" |

These defaults are HINTS for LLM prompt assembly + scene narration; they don't constrain what fixture_seed CAN declare (a Tavern with a Throne is unusual but valid — author override).

---

## §5 Place ↔ Channel mapping

**V1 strict 1:1 invariant:** every cell-tier channel has exactly one place row; every place row references exactly one cell-tier channel.

```
DP channel tree (cell-tier and below):
  cell:yen_vu_lau          ← place row exists (PlaceId = cell:yen_vu_lau)
  cell:tay_thi_quan        ← place row exists
  cell:hangzhou_market     ← place row exists
```

```
DP channel tree (above cell-tier):
  continent:asia           ← NO place row (aggregation tier)
  country:song_china       ← NO place row
  district:lin_an          ← NO place row
  town:hangzhou            ← NO place row
```

**Why 1:1 V1:** simplest mental model. "What place is X at?" = "what cell channel is X in?" (via EF_001 entity_binding.location.InCell). Multi-place-per-cell (apartment building with multiple internal rooms at same DP channel) is V1+ deferred (PF-D4) — would require sub-place hierarchy + secondary addressing.

**Bootstrap order at RealityManifest ingestion:**
1. DP creates channel hierarchy from `root_channel_tree` (existing PL_001 §16)
2. PF_001 creates `place` rows from `places: Vec<PlaceDecl>` (RealityManifest extension §9)
3. Validation: every cell-tier channel from step 1 has a corresponding place from step 2; mismatch rejects bootstrap with `place.missing_decl` listing offending channel ids
4. EnvObject canonical instantiation: for each place's `fixture_seed`, RealityBootstrapper creates EnvObject entities (deterministic ids via UUID v5 from `(place_id, seed_uid)`) and writes `entity_binding` rows with `location: InCell { cell_id: place_id.0 }` (or `Embedded { parent: <gate_seed_uid envobject>, slot }` for sub-fixtures)
5. NPC + PC canonical seeds (PL_001 §16 + NPC_001) place actors at cells whose place rows are now valid

---

## §6 Connection graph

DP channel hierarchy implicitly provides parent↔child traversal. PF_001 connections add HORIZONTAL edges (peer-to-peer at cell tier, possibly cross-tree).

```rust
pub enum ConnectionKind {
    Public,    // door, road, public path — anyone can pass
    Private,   // canonical residents only — Travel reject for non-residents (V1: residency = canonical_actor home_cell match)
    Locked,    // gated by Embedded fixture (door with keyhole) — V1: reject `place.connection_locked`; V1+ key-matching
    Hidden,    // discoverable via Examine — visible only after `place_discovery` event for this PC (V1+30d; V1: visible to all)
    OneWay,    // enter but not exit — Travel from `to_place` back to source rejects `place.no_reverse_connection`
}
```

**Bidirectional flag:** if `bidirectional: true`, connection is added at both ends automatically by DP-internal validator. `bidirectional: false` requires explicit reverse declaration on `to_place` (e.g., OneWay connections, asymmetric private/public access).

**Travel resolution V1** (consumed by PL_001 §13 travel sequence):
1. PC issues `/travel destination=cell:tay_thi_quan` (PL_002 Grammar)
2. PL_001 §13 calls PF_001 connection-resolution helper: is current_cell connected to destination via Public / accessible Private / unlocked Locked / discovered Hidden / non-OneWay-reverse?
3. If yes → Travel proceeds. If no → reject with appropriate `place.*` rule_id (`connection_locked` / `connection_private` / `connection_hidden` / `no_reverse_connection`)
4. ConnectionDecl `canon_ref` propagates into Travel narrator text ("you walk down the cobbled main street described in chapter 4")

**Why explicit V1:** book canon often specifies non-obvious connections (secret tunnel, magical portal). Implicit-only-hierarchy connections would force every Travel through parent-channel routing which is artificial. Explicit Vec<ConnectionDecl> lets author declare canonical paths.

---

## §7 StructuralState state machine

```
                    ┌──────────────────────────────┐
                    ▼                              │
              ┌─────────┐  damage      ┌──────────────┐
              │Pristine │ ───────────▶│  Damaged     │
              │         │ ◀──────────│              │
              └─────────┘  repair     └──────────────┘
                    │                          │
                    │ destroy                  │ destroy
                    ▼                          ▼
              ┌─────────────────────────────────┐
              │  Destroyed                      │
              └─────────────────────────────────┘
                    │
                    │ rebuild (RARE; author-edit only V1)
                    ▼
              ┌──────────────┐
              │  Restored    │ ──────────┐
              │              │           │ damage
              │              │ ◀──────────┘
              └──────────────┘
                    │
                    │ destroy
                    ▼
              (back to Destroyed)
```

**Transitions (allowed):**

| From → To | Trigger | Owner | reason_kind |
|---|---|---|---|
| `Pristine` → `Damaged` | PL_005 Strike Destructive (sub-lethal damage) · author-edit (Forge) | PL_005 / WA_003 | `InteractionDestructive` / `Forge:EditPlace` |
| `Damaged` → `Pristine` | author-edit (Forge "repair") · V1+ scheduled regrowth (PF-D3) | WA_003 / scheduler | `Forge:EditPlace` / `ScheduledRegrowth` |
| `Pristine` → `Destroyed` | PL_005 Strike with sufficient cumulative damage · author-edit · V1+ scheduled catastrophe | PL_005 / WA_003 / scheduler | `InteractionDestructive` / `Forge:EditPlace` |
| `Damaged` → `Destroyed` | additional damage; lower threshold than Pristine→Destroyed | PL_005 | `InteractionDestructive` |
| `Destroyed` → `Restored` | author-edit (Forge "rebuild") | WA_003 | `Forge:EditPlace` |
| `Restored` → `Damaged` | new damage post-rebuild | PL_005 | `InteractionDestructive` |
| `Restored` → `Destroyed` | enough new damage | PL_005 | `InteractionDestructive` |

**Forbidden transitions** (validated at write-time; rejected with `place.invalid_structural_transition`):
- `Destroyed` → `Pristine` (must go via Restored to preserve audit precision)
- `Destroyed` → `Damaged` (can't partially un-destroy)
- `Restored` → `Pristine` (Restored is a distinct state; degrades to Damaged or Destroyed only)

**Cascade into EF_001 §6.1** (when `Existing → Destroyed` for the place):
- All EnvObjects with `entity_binding.location ∈ { InCell { cell_id: place_id.0 }, Embedded { parent: <any envobject in this cell> } }` cascade `Existing → Destroyed` with `reason_kind = HolderCascade` per EF_001 §3.2 (EntityLifecycleLog reason kind added in Phase 3 cleanup)
- All Items with `location.InCell { cell_id: place_id.0 }` cascade `Existing → Destroyed` (canonical destruction semantics; Items don't survive a place-destruction event V1)
- PCs/NPCs at the cell at destruction-time face mortality cascade per PCS_001 / NPC_001 rules (out of PF_001 scope)
- Cascade emitted as a single atomic batch with the place state transition

**V1+ deferral PF-D3:** scheduled time-decay (forest regrows after fire over fiction-time months; market crowd density cycles diurnally) — Generator framework EVT-G* ready; awaiting feature design.

---

## §8 Fixture seed model

Place declares its canonical EnvObjects at bootstrap. RealityBootstrapper instantiates EnvObject entities deterministically from the seeds; future EnvObject feature owns the body.

**EnvObjectSeedDecl repeated from §3.1 for clarity:**

```rust
pub struct EnvObjectSeedDecl {
    pub seed_uid: SeedUid,                  // deterministic ID stable across reality clones
    pub envobject_kind: EnvObjectKind,      // closed enum (Door/Wall/Table/Statue/...)
    pub slot_id: String,                    // stable position descriptor
    pub default_affordances: AffordanceSet, // EF_001 AffordanceFlag bitset
    pub initial_state: serde_json::Value,   // future EnvObject feature interprets
}

pub struct SeedUid(pub Uuid);  // deterministic — UUID v5 from (place_id, slot_id)

pub enum EnvObjectKind {
    Door,       // gateway between cells; can be Locked
    Wall,       // boundary; usually non-interactive but Examine target
    Table,      // surface; supports Items via V1+ container affordance
    Statue,     // landmark; often book-canon-grounded for Examine flavor
    Fountain,   // water feature; flavor + V1+ Use (drink/bathe)
    Bed,        // residence fixture; rest/sleep affordance V1+
    Chest,      // V1+ container (PF-D-via-EF-D3 dependency)
    Throne,     // OfficialHall fixture; ceremonial
    Altar,      // Temple fixture; ritual focus
    Window,     // boundary; visible-from-outside V1+
    Sign,       // text-bearing; Examine returns sign content
}
```

**Canonical instantiation flow (at RealityManifest bootstrap):**
1. For each place, iterate `fixture_seed[]`
2. For each seed: deterministic EnvObjectId = UUID v5 `(reality_id, place_id.0, seed_uid)` — same reality clone produces same EnvObjectIds (replay-safe per EVT-A9)
3. Write `entity_binding` row per EF_001 §3.1: `{ entity_id: EnvObject(...), entity_type: EnvObject, location: InCell { cell_id: place_id.0 }, lifecycle_state: Existing, affordance_overrides: Some(seed.default_affordances), ... }`
4. Future EnvObject feature owns body row (deferred V1; binding alone covers Examine + connection-gating V1)
5. Emit EVT-T4 System `EntityBorn { entity_id, entity_type: EnvObject, cell_id, reason_kind: CanonicalSeed }` per EF_001 §13.1 sequence

**Affordance defaults by EnvObjectKind** (V1; future EnvObject feature may extend):

| EnvObjectKind | Default AffordanceSet V1 | Notes |
|---|---|---|
| Door | `BeExamined + BeUsed` | "Use door" = open/close; Locked variant adds gate flag |
| Wall | `BeExamined` | passive-only |
| Table | `BeExamined + BeUsed` | "Use table" = sit/place item (V1+ container) |
| Statue | `BeExamined` | passive landmark |
| Fountain | `BeExamined + BeUsed` | "Use fountain" = drink/bathe (V1+ effects) |
| Bed | `BeExamined + BeUsed` | "Use bed" = rest/sleep (V1+ status effects) |
| Chest | `BeExamined + BeUsed` | "Use chest" = open/close; V1+ container |
| Throne | `BeExamined + BeUsed` | "Use throne" = sit (status effect: PerceivedAuthority V1+) |
| Altar | `BeExamined + BeUsed` | "Use altar" = ritual (V1+ Temple-bound) |
| Window | `BeExamined` | view-only V1; V1+ climb-through |
| Sign | `BeExamined` | examine returns text content from `initial_state` |

Per-instance overrides via `entity_binding.affordance_overrides` (e.g., a magical talking statue gains `BeSpokenTo`).

---

## §9 RealityManifest extension + `place.*` RejectReason namespace

**Extension to RealityManifest** (per `_boundaries/02_extension_contracts.md` §2):

```rust
pub struct RealityManifest {
    // ... existing Continuum-owned + WA + NPC fields ...

    // ─── PF_001 Place Foundation extension (added 2026-04-26) ───
    pub places: Vec<PlaceDecl>,           // REQUIRED V1; one per cell-tier channel
}

pub struct PlaceDecl {
    pub place_id: PlaceId,                // = cell ChannelId
    pub place_type: PlaceType,
    pub canon_ref: BookCanonRef,
    pub display_name: LocalizedName,
    pub initial_structural_state: StructuralState,  // typically Pristine; book-canonical override possible
    pub initial_narrative_drift: serde_json::Value, // typically {} at canonical seed
    pub connections: Vec<ConnectionDecl>,
    pub fixture_seed: Vec<EnvObjectSeedDecl>,
}
```

**`place.*` RejectReason namespace V1** (owned by PF_001; registered in `_boundaries/02_extension_contracts.md` §1.4):

| rule_id | Trigger | Vietnamese reject copy V1 | Soft-override eligible |
|---|---|---|---|
| `place.missing_decl` | cell-tier channel exists without `place` row at runtime | "Vị trí chưa được định nghĩa." | No (bootstrap invariant) |
| `place.duplicate_place` | second write attempt for `place_id` that already has a row | "Vị trí này đã được đăng ký." | No (write-time invariant) |
| `place.invalid_structural_transition` | aggregate-owner attempts forbidden transition (§7) | "Chuyển đổi trạng thái cấu trúc không hợp lệ." | No (write-time validator) |
| `place.unknown_place` | `PlaceId` resolves to no `place` row | "Không tìm thấy vị trí." | No (always reject) |
| `place.connection_target_unknown` | ConnectionDecl `to_place` references non-existent place | "Đích kết nối không tồn tại." | No (write-time validator) |
| `place.connection_locked` | Travel attempt through Locked connection without satisfying gate (V1: always reject; V1+ key-matching) | "Lối đi đã khoá." | No (V1; soft-override may activate V1+ if Examine-the-lock is needed) |
| `place.connection_private` | Travel attempt through Private connection without canonical residency match | "Lối đi riêng tư, không được phép." | No |
| `place.connection_hidden` | Travel attempt through undiscovered Hidden connection (V1: visible to all so does not fire; V1+30d when discovery flags land) | "Không nhìn thấy lối đi nào ở đây." | Yes (Examine-the-area can hint per V1+ discovery feature) |
| `place.no_reverse_connection` | Travel attempt to reverse a OneWay connection | "Không thể quay lại đường này." | No |
| `place.fixture_seed_uid_collision` | duplicate `seed_uid` in same place's fixture_seed list | "Trùng định danh thiết bị nội thất." | No (bootstrap invariant) |
| `place.invalid_place_type_for_channel_tier` | place row attempted on non-cell-tier channel (continent/country/district/town) | "Loại kênh không hợp lệ cho vị trí." | No (V1 cell-only invariant) |

**V1+ rule_id reservations** (additive per I14):
- `place.scheduled_decay_collision` — V1+30d scheduler conflict on same place
- `place.cross_reality_connection` — V1+ multiverse portal connection between realities (PF-D6)
- `place.procedural_generation_rejected` — V1+ Forge author-review rejects LLM-proposed place (PF-D7)

---

## §10 DP primitives consumed

PF_001 implements one aggregate against the locked DP contract; no new primitives needed.

| DP primitive | Used for | Pattern |
|---|---|---|
| `t2_read(place, key=place_id)` | look up place semantics + structural state + connections + fixtures | Hot-path for Examine + Travel; cached per DP-K6 subscribe |
| `t2_write(place, key=place_id, mutation)` | structural state transition · narrative drift edit · author-edit | Aggregate-Owner role per DP-K5 |
| `subscribe(place, filter)` | UI invalidation on place change; LLM context refresh; PL_005c cascade hooks | DP-K6 durable subscribe |
| `t2_scan(place, filter)` | rare admin queries (find all places of type X) | NOT hot-path; admin/audit only — DP-A8 |

**No new DP-K* primitives requested.** PF_001 fits within existing kernel surface.

---

## §11 Capability JWT claims

PF_001 declares no new top-level capability claim. Reuses existing claims:

- `produce: ["AggregateMutation", "AdminAction"]` — required to write `place` aggregate + Forge admin edits (already present for world-service)
- Per-aggregate write capability under `capabilities[]` per DP-K9 — needs `place:write`

**Service binding:** world-service is the canonical writer for `place`. Aggregate handoff between world-service nodes follows PL_001 §3.6 epoch-fence model unchanged (places are channel-bound; channel writer-binding extends naturally).

---

## §12 Subscribe pattern

UI invalidation + downstream feature consumption via DP-K6 subscribe.

**Subscribers V1:**

| Subscriber | Filter | Purpose |
|---|---|---|
| Frontend (player UI) | `place WHERE place_id = current_cell.place_id` | scene description display; auto-refresh on structural state change |
| LLM prompt assembly (`AssemblePrompt`) | same | `[PLACE_CONTEXT]` section in prompt: place_type + canon_ref content + structural_state + narrative_drift |
| PL_005c Interaction integration | `place WHERE place_id ∈ examine.targets` | Examine of place returns combined narrator text |
| WA_003 Forge author UI | `place WHERE reality_id = current` | author scene editor; shows places hierarchy |
| Future quest-engine | `place` | quest triggers on PlaceType / structural state |

**Validator slot considerations:** EVT-V_place_structural runs as part of PL_005's structural-affordance check (`EVT-V_entity_affordance` at EF_001 §11) — when target is a place via PL_005 ExamineTarget::Place, this validator confirms place exists + structural_state allows examine. Slot ordering deferred to `_boundaries/03_validator_pipeline_slots.md` alignment review (PF-Q1 watchpoint).

---

## §13 Cross-service handoff

PlaceId is just a newtype over ChannelId, so cross-service serialization reuses existing channel-id JSON shape:

```json
{ "place_id": { "channel_id": "cell:yen_vu_lau" } }
```

Causality token chain unchanged: place mutations include CausalityToken referencing the triggering EVT-T1 Submitted (or EVT-T8 Administrative for Forge edits). Replay-determinism preserved per EVT-A9.

---

## §14 Sequences (5 V1 representative flows)

### 14.1 Canonical place birth at RealityManifest bootstrap

```
RealityManifest.places[i] = PlaceDecl { place_id: cell:yen_vu_lau, place_type: Tavern, ... }
  ↓ (bootstrap step 2 per §5)
RealityBootstrapper emits EVT-T4 System PlaceBorn { place_id, place_type, parent_channel: town:hangzhou }
  ↓ (atomic with bootstrap transaction)
write place row { place_id: cell:yen_vu_lau, place_type: Tavern, structural_state: Pristine, ... }
  ↓ (bootstrap step 4)
For each fixture_seed[i]: deterministic EnvObjectId via UUID v5; write entity_binding row per EF_001 §13.1
emit EVT-T4 System EntityBorn (per fixture) — these are cascaded with PlaceBorn in the same atomic batch
```

### 14.2 Travel through public connection (PL_002 /travel)

```
PC at cell:yen_vu_lau issues /travel destination=cell:tay_thi_quan
  ↓ EVT-T1 Submitted PCTurn { kind: Travel, destination: cell:tay_thi_quan }
PL_001 §13 travel sequence calls PF_001 connection-resolver:
  - read place row for cell:yen_vu_lau
  - check connections[]: any with to_place=cell:tay_thi_quan?
    → found: ConnectionDecl { to_place: cell:tay_thi_quan, kind: Public, bidirectional: true, canon_ref: <book_chapter_4_path> }
  - kind=Public → pass; canon_ref propagates into Travel narrator
  → resolved
  ↓ PL_001 §13 travel proceeds: t2_write entity_binding (EntityId::Pc) location InCell(cell:tay_thi_quan)
DP emits MemberLeft(yen_vu_lau) + MemberJoined(tay_thi_quan); narrator includes book-canonical path description
```

### 14.3 In-fiction structural transition via PL_005 Strike Destructive

```
PC issues Interaction.Strike { target: EnvObject(stone_wall_north), tool: Item(war_hammer), damage: HighDestructive }
  ↓ EVT-T1 Submitted Interaction:Strike commits
PL_005c integration cascade (per its §V1-scope):
  - EnvObject(stone_wall_north) lifecycle Existing → Destroyed (EF_001 §6.1)
  - PF_001 cascade hook: place row for cell containing wall checks structural_state
    → Pristine + significant fixture destroyed → transition Pristine → Damaged
    → emit EVT-T3 Derived { aggregate_type: place, delta: { structural_state: Damaged, last_structural_change_fiction_time: now } }
  - reason_kind=InteractionDestructive; causal_ref=<strike_event>
LLM next-turn AssemblePrompt includes updated structural_state + narrative_drift hint
```

### 14.4 PL_005 Examine of place (ExamineTarget::Place)

```
PC issues Interaction.Examine { target: ExamineTarget::Place(cell:yen_vu_lau) }
  ↓ EVT-T1 Submitted Interaction:Examine commits (Examine has no destructive output; pure perception)
PF_001 EVT-V_place_structural validator (ordered before per-kind):
  - place exists? ✓
  - structural_state ∈ {Pristine, Damaged, Restored}? ✓ (Destroyed soft-overrides per EF_001 §8 tolerates_destroyed)
PL_005 Examine narrator combines:
  - place.canon_ref content (book description chunk)
  - place.structural_state hint ("the tavern is in good repair" / "scratched up" / "burnt-out shell")
  - place.narrative_drift JSON (per-reality flavor)
  - PL_001 scene_state ambient (weather, crowd, time-of-day)
  - visible EnvObjects at cell (entity_binding query) with their default_affordances names
LLM produces narrator_text combining all
```

### 14.5 Author-edit place via Forge (WA_003)

```
Author issues Forge:EditPlace { place_id: cell:yen_vu_lau, edit_kind: UpdateNarrativeDrift, before: {...}, after: {"front_door_color": "red"} }
  ↓ EVT-T8 Administrative Forge:EditPlace commits
WA_003 Forge writes:
  - t2_write place: narrative_drift = after; last_narrative_drift_fiction_time = now
  - emit EVT-T3 Derived { aggregate_type: place, delta: { narrative_drift: ... } }
  - emit ForgeEdit audit log (forge_audit_log per WA_003)
LLM next-turn AssemblePrompt sees updated drift; players in cell observe changed scene description
```

---

## §15 Acceptance criteria

10 V1-testable scenarios (AC-PF-1..10):

1. **AC-PF-1 — RealityManifest places extension required:** RealityManifest with `places: []` (empty) but cell-tier channels declared in `root_channel_tree` rejects bootstrap with `place.missing_decl { offending_channels: [...] }`. Tests §5 invariant + §9 bootstrap order.
2. **AC-PF-2 — Cell-tier 1:1 invariant:** RealityManifest with `places[i].place_id = town:hangzhou` (non-cell-tier channel) rejects bootstrap with `place.invalid_place_type_for_channel_tier`. Tests §5.
3. **AC-PF-3 — PlaceType variant exhaustiveness (compile-time):** Rust unit test that uses `match place_type` without arms for all 10 V1 variants fails to compile with `error[E0004]: non-exhaustive patterns`. CI lint (mirroring AC-EF-1 pattern) flags `_ =>` arms outside designated catch-all sites with `// PF-EXHAUSTIVE-EXEMPT: <reason>` annotation.
4. **AC-PF-4 — Forbidden StructuralState transitions reject:** attempting `Destroyed → Pristine` (or `Destroyed → Damaged` or `Restored → Pristine`) rejects `place.invalid_structural_transition`. Tests §7.
5. **AC-PF-5 — Connection target validation:** writing place row with `connections[i].to_place` pointing to non-existent PlaceId rejects `place.connection_target_unknown`. Bootstrap-time validation; runtime author-edit also validates.
6. **AC-PF-6 — Locked connection blocks Travel V1:** PC at place A attempts /travel to place B via ConnectionKind::Locked → reject `place.connection_locked` (V1 always; V1+ key-matching deferred).
7. **AC-PF-7 — Place destruction cascades EnvObjects:** Place transition `Pristine → Destroyed` emits a single atomic batch including (a) place row state delta + (b) all EnvObjects at cell `Existing → Destroyed` per EF_001 §6.1 with `reason_kind = HolderCascade` + (c) all Items at cell `Existing → Destroyed`. No intermediate state observable.
8. **AC-PF-8 — Forge author-edit emits EVT-T8:** Forge:EditPlace updates place row AND emits EVT-T8 Administrative `Forge:EditPlace { before, after }` AND appends to `forge_audit_log` per WA_003 — all in a single transaction. Reading place after commit returns the new state.
9. **AC-PF-9 — PL_005 Examine of place returns combined narrator:** Examine target `ExamineTarget::Place(cell:yen_vu_lau)` returns narrator text containing (a) canon_ref content (or pointer), (b) structural_state hint, (c) at-least-one EnvObject default_affordances reference (visible fixtures), (d) scene_state ambient cue. All four components present means LLM has full context.
10. **AC-PF-10 — Fixture seed deterministic instantiation:** two reality clones from same RealityManifest produce identical EnvObjectIds for fixtures (UUID v5 from `(reality_id, place_id, seed_uid)`). Replay across clone reproduces same seed-to-id mapping (per EVT-A9 determinism contract).

---

## §16 Deferrals

| ID | What | Why deferred | Target phase |
|---|---|---|---|
| **PF-D1** | V1+ PlaceType extensions (Dungeon / Battlefield / Vehicle / ShipDeck / DreamRealm) | Not V1-blocking; additive per I14 | When first such genre feature designed |
| **PF-D2** | V1+ ConnectionKind extensions (TimePortal / PocketDimension / Resonance) | V1+ supernatural travel kinds | V1+ supernatural feature design |
| **PF-D3** | V1+30d scheduled place decay (forest regrowth, market crowd cycle) | Generator framework EVT-G* ready; no V1 use case has named cadence | V1+30d scheduler design |
| **PF-D4** | Multi-place per cell (apartment building with multiple internal rooms at same DP channel) | adds sub-place hierarchy + secondary addressing complexity; V1 strict 1:1 covers covers SPIKE_01 + most book-canon scenarios | V1+ if author content needs |
| **PF-D5** | Place-level Heresy contamination rules (currently per-actor only per WA_002) | V1: contamination is per-(actor, kind). V1+: places themselves can become contaminated (e.g., a temple becomes heretical) | V1+ Heresy expansion |
| **PF-D6** | Cross-reality place references (multiverse portal between two realities) | V2+ multiverse expansion; current `cross_reality_reference` reservation in `entity.*` namespace | V2+ |
| **PF-D7** | Procedural place generation (LLM-suggested places with author-review gate) | V1+ Forge author workflow + EVT-T6 Proposal generator | Future Forge V2 |
| **PF-D8** | Place-level audio/visual asset references for V1+ rendering | V1: text-only narration. V1+ multimedia rendering layer hooks | V1+ frontend rendering V2 |
| **PF-D9** | Place-level economy (Marketplace pricing, Workshop crafting tables) | V1: places have type + state but no economic semantics | V1+ economy feature |
| **PF-D10** | Hidden connection discovery flags (per-PC discovered_connections set) | V1: Hidden connections visible to all (effectively Public). V1+ per-PC progress + discovery via Examine | V1+30d quest/exploration |
| **PF-D11** | V1+ container EnvObject affordance (BeContainedIn) cross-reference | requires EF_001 EF-D3; PF_001 declares EnvObjectKind::Chest with placeholder affordance V1 | Future Item + EnvObject features |

---

## §17 Cross-references

- **PL_001 Continuum** §16 — RealityManifest extended with `places: Vec<PlaceDecl>` (this commit; light reopen). PL_001 §3.2 scene_state stays under PL_001 ownership; runtime ambient is play-loop concern. PL_001 §3.2 `notable_props` semantics light-clarified: V1 freeform strings still supported; V1+ may reference EnvObjectIds for addressable fixtures.
- **EF_001 Entity Foundation** §6.1 — Place destruction cascade integrates with EF_001 cascade rules; PF_001 owns the trigger (StructuralState → Destroyed) and EF_001 owns the per-entity propagation (HolderCascade reason_kind).
- **EF_001 §3.1** — `entity_binding.location.InCell { cell_id }` cross-references PlaceId via `cell_id == place_id.0` invariant; EnvObject fixtures bind via `Embedded { parent: <gate envobject>, slot }` for sub-fixtures.
- **PL_002 Grammar** §V1-commands — `/travel destination=<cell_id>` consumes PF_001 connection-resolver. Travel rejects map to `place.connection_*` rule_ids.
- **PL_005 Interaction** §V1-kinds — Examine kind extended with `ExamineTarget = Entity(EntityId) | Place(PlaceId)` discriminator (cross-feature dependency on PL_005 still DRAFT; PL_005 closure-pass should add this extension).
- **PL_005c Interaction integration** §V1-scope — Strike Destructive cascade includes PF_001 hook for place structural-state transition.
- **PL_006 Status Effects** — places do NOT have actor_status V1 (only PC+NPC do; V1+ if "the temple is blessed/cursed" status needed, that's PF-D5 expansion not PL_006 expansion).
- **NPC_001 Cast** — `npc.current_region_id: ChannelId` cross-references the cell-tier channel hosting the NPC; EF-Q2 watchpoint (npc.current_region_id may migrate to entity_binding) compatible with PF_001 1:1 mapping.
- **NPC_002 Chorus** — scene-roster context for NPC_002 reaction batching gains place_type + structural_state hints; NPC behavior may diverge by PlaceType (NPC in Tavern more talkative; NPC in Wilderness more cautious).
- **PCS_001** (when designed) — PC spawn cell MUST reference valid PlaceId (canonical place row exists). Brief at `features/06_pc_systems/00_AGENT_BRIEF.md` requires update post PF_001 LOCK to add §4.4d mandatory PF_001 reading.
- **WA_001 Lex** — Lex axioms can reference PlaceType (e.g., "magic strength varies by place: Wilderness +20%, Cave +10%, Temple −10%"); V1+ if needed; PF_001 provides the queryable PlaceType enum.
- **WA_002 Heresy** — V1+ place-level contamination per PF-D5.
- **WA_003 Forge** — Forge:EditPlace AdminAction registered (§2.5 + §14.5).
- **07_event_model** — EVT-T4 System sub-type `PlaceBorn` + EVT-T3 Derived `aggregate_type=place` registered.
- **06_data_plane** — `place` aggregate sits in T2/Channel-cell scope per existing DP contract. No new primitives.
- **03_multiverse (MV12)** — fiction-time advancement triggers V1+ scheduled decay (PF-D3); current V1 time-lapse via author-edit + in-fiction event only.

---

## §18 Readiness checklist

- [x] Domain concepts table covers PlaceId / PlaceType / StructuralState / NarrativeDrift / ConnectionDecl / ConnectionKind / EnvObjectSeedDecl / EnvObjectKind / PlaceDecl
- [x] Aggregate inventory: 1 aggregate (`place` primary; T2/Channel-cell scope)
- [x] PlaceType 10 V1 closed enum + per-type ambient cue + fixture-kind hints
- [x] Place ↔ Channel 1:1 invariant explicit (cell-tier only)
- [x] Connection graph: hybrid (DP hierarchy implicit + Vec<ConnectionDecl> explicit horizontal); 5 V1 ConnectionKinds
- [x] StructuralState 4-state machine with allowed/forbidden transitions; cascade into EF_001 §6.1
- [x] Fixture seed model: deterministic UUID v5 instantiation; 11 V1 EnvObjectKinds + per-kind affordance defaults
- [x] RealityManifest extension `places: Vec<PlaceDecl>` (registered in `_boundaries/02_extension_contracts.md` §2)
- [x] Reference safety policy: 11 V1 rule_ids in `place.*` namespace + 3 V1+ reservations
- [x] Event-model mapping: EVT-T3 Derived (`aggregate_type=place`) + EVT-T4 System (`PlaceBorn`) + EVT-T8 Administrative (`Forge:EditPlace`); no new EVT-T*
- [x] DP primitives: existing surface only (no new DP-K*)
- [x] Capability JWT: existing claims (no new top-level)
- [x] Subscribe pattern: 5 subscribers V1 (Frontend / LLM AssemblePrompt / PL_005c / WA_003 / future quest-engine)
- [x] Cross-service handoff: PlaceId JSON shape (newtype over ChannelId)
- [x] 5 representative sequences
- [x] 10 V1-testable acceptance scenarios (AC-PF-1..10)
- [x] 11 deferrals (PF-D1..D11) with target phases
- [x] Cross-references to all 13 affected features + foundation docs
- [ ] Phase 3 review cleanup pending
- [ ] CANDIDATE-LOCK pending closure pass + downstream updates (PCS_001 brief §4.4d / PL_005 ExamineTarget extension confirm)

---

## §19 Open questions (post-DRAFT)

| ID | Question | Resolution path |
|---|---|---|
| **PF-Q1** | Validator slot ordering: EVT-V_place_structural relative to EVT-V_entity_affordance + EVT-V_lex? Place check is structural like entity check; should they be the same slot or sequential? | `_boundaries/03_validator_pipeline_slots.md` alignment review (extends EF-Q3 from EF_001) |
| **PF-Q2** | Should `place.canon_ref` be required for AuthorCreated places (current spec uses `BookCanonRef::AuthorCreated`) or optional? | V1: required as `AuthorCreated` variant; if author resists author-creation friction, V1+ make optional with fallback to reality-default canon_ref |
| **PF-Q3** | Multi-locale `display_name` — V1 only `vi`, but PL_001 LocalizedName pattern not yet established. Should LocalizedName live in PF_001, EF_001, or a shared 00_foundation layer? | Boundary review V1+ when `en` locale lands (probably 00_foundation for cross-cutting) |
| **PF-Q4** | Should Place be addressable as 5th EntityId variant (Pc/Npc/Item/EnvObject/Place) instead of separate ExamineTarget discriminator? Trade-off: EntityId extension is invasive across all entity machinery; ExamineTarget is local to PL_005 | V1: separate ExamineTarget — places are containers not things; reconsider V1+ if Place ends up being struck/used (currently no V1 use case beyond Examine) |
| **PF-Q5** | Connection bidirectional default — should bidirectional default to true (most paths are two-way) to reduce author-decl burden, or false for safety? | V1: default true; explicit false for OneWay/asymmetric — matches book-canon expectation |
