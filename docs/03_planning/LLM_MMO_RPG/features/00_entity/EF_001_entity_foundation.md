# EF_001 — Entity Foundation

> **Conversational name:** "Entity Foundation" (EF). The substrate that defines what counts as an addressable thing in the world — a unified `EntityId` taxonomy, spatial presence (`entity_binding`), lifecycle state machine, affordance enum, and the `EntityKind` trait that PC / NPC / Item / EnvObject aggregates implement.
>
> **Category:** EF — Entity Foundation (foundation tier; precedes feature folders)
> **Status:** **CANDIDATE-LOCK 2026-04-26** (DRAFT 2026-04-26 → Phase 3 review cleanup 2026-04-26 → CANDIDATE-LOCK 2026-04-26 closure pass: §14 acceptance criteria walked + 3 rule_id mismatches resolved by §8 namespace expansion 7 → 10 V1 + 1 V1+ reservations + 3 ACs precision-tightened. Option C max scope per user direction "object foundation trước PC/NPC/Item")
> **Catalog refs:** [`cat_00_EF_entity_foundation.md`](../../catalog/cat_00_EF_entity_foundation.md) — owns `EF-*` namespace (`EF-A*` axioms · `EF-D*` deferrals · `EF-Q*` open questions)
> **Builds on:** [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §3.6 (transfers `actor_binding` → `entity_binding` with extended scope), [DP-A1..A19](../../06_data_plane/02_invariants.md) (T2/Reality scope contract), [07_event_model](../../07_event_model/) Option C taxonomy (T3 Derived for entity_binding deltas; T4 System for entity-lifecycle DP-emitted)
> **Resolves:** B2-derived "entity addressability" gap (PL_005 Item deferred-V1 footgun) · ActorId scope-creep (NPC_001 §2 ActorId only covered PC+NPC; Items + EnvObjects unaddressable) · per-feature ad-hoc lifecycle invention (drift trap — WA_006 originally hit) · per-feature ad-hoc reference-safety handling
> **Defers to:** [PCS_001](../06_pc_systems/) (when designed) for `Pc` aggregate body implementing `EntityKind` · future Item feature (`features/04_play_loop/PL_007_item.md` or similar) for `Item` aggregate body · future EnvObject feature for scene-fixture aggregate body. EF_001 owns the **contracts**; consumer features own the **bodies**.

---

## §1 Why this exists

Three concrete gaps in the V1 design surface that EF_001 closes:

**Gap 1 — PL_005 Interaction nợ Item.** PL_005 5 V1 InteractionKinds (Speak / Strike / Give / Examine / Use) all reference `Item` as either `tool` or `target`. PL_005c §V1-scope explicitly defers Item aggregate "refs only V1". Without an Item entity model, Strike with weapon, Give an item, Use a tool — none of these are V1-implementable. Foundation must define what an Item IS before PL_005 can close.

**Gap 2 — ActorId fragmentation.** `actor_binding` (PL_001 §3.6) is "Where is X reality-global lookup, covers PCs + NPCs uniformly". But:
- Items also need spatial presence (in cell, held by actor, in container)
- EnvObjects (door, wall, table, statue) need addressability for Examine
- Each entity type currently invents its own location model → drift

NPC_001 §2 ActorId enum covers `Pc | Npc | Synthetic | Admin` but excludes Item + EnvObject. PL_005 4-role pattern (agent / tool / direct_targets / indirect_targets) needs ALL four to be uniformly addressable.

**Gap 3 — Per-feature lifecycle invention.** WA_006 Mortality originally over-extended into "what happens when PC dies" → relocated to PCS_001. NPC_001 has its own "NPC absent-from-world" semantics. Items will need destruction. EnvObjects will need can-be-broken. Without a unified lifecycle state machine, each feature reinvents `Existing | Gone | Removed` with subtly different semantics → reference-safety drift across feature boundaries.

EF_001 owns the foundation; consumer features (PCS_001 / NPC_001 / Item / EnvObject) implement the contracts.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **EntityId** | Closed sum type — `Pc(PcId) \| Npc(NpcId) \| Item(ItemId) \| EnvObject(EnvObjectId)` | 4 variants V1. Reserved V1+: `Vehicle \| Spirit \| Building \| Quest \| Channel`. Replaces `ActorId` (NPC_001 §2) for cross-entity references; `ActorId` becomes a sub-set with `Pc` + `Npc` only (kept for actor-only contexts like turn submission). |
| **EntityType** | Closed enum discriminator — `Pc \| Npc \| Item \| EnvObject` | Matches EntityId variants 1:1; used as run-time tag when EntityId is opaque. Sub-discriminator for EVT-T3 Derived sub-types of `entity_binding`. |
| **PcId** | Newtype `pub struct PcId(pub Uuid)` | Owned by PCS_001 (when designed); EF_001 declares the variant only. |
| **NpcId** | Newtype `pub struct NpcId(pub Uuid)` | Owned by NPC_001; EF_001 declares the variant only. |
| **ItemId** | Newtype `pub struct ItemId(pub Uuid)` | Owned by future Item feature; EF_001 declares the variant. V1 Item bodies remain stub-references (PL_005c V1 vertical-slice) until Item feature lands. |
| **EnvObjectId** | Newtype `pub struct EnvObjectId(pub Uuid)` | Owned by future EnvObject feature; EF_001 declares the variant. V1: lightweight examine targets only (door, wall, table, statue, fixture). |
| **LifecycleState** | Closed enum 4-state — `Existing \| Suspended \| Destroyed \| Removed` | See §6. PC death routes to `Destroyed` via PCS_001; admin removal (Heresy decanonize) routes to `Removed` via WA_002. |
| **AffordanceSet** | Bit-set over `AffordanceFlag` | See §7. Closed core enum (6 V1 flags); per-entity-type defaults + per-instance overrides. |
| **AffordanceFlag** | Closed enum — `be_spoken_to \| be_struck \| be_examined \| be_given \| be_received \| be_used` | 6 V1 flags map 1:1 with PL_005 5 InteractionKinds (+ Give bidirectional split). V1+ flags reserved: `be_collided_with \| be_shot_at \| be_cast_at \| be_embraced \| be_threatened \| be_traveled_to \| be_contained_in`. |
| **EntityKind trait** | Rust trait with 5 methods (see §4) | Every aggregate body that wants to be addressable as an Entity MUST implement this. EF_001 owns the trait; consumer features implement. |
| **LocationKind** | Closed enum — `InCell \| HeldBy \| InContainer \| Embedded` | 4-state location discriminator on `entity_binding.location`. See §3.1. |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

EF_001 introduces no new EVT-T* category. Maps onto existing mechanism-level taxonomy:

| EF event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Entity binding mutation (move, transfer, contain, embed) | **EVT-T3 Derived** | `aggregate_type=entity_binding` | Aggregate-Owner role (world-service post-validate) | Causal-ref to triggering EVT-T1 Submitted (e.g., PL_005 Interaction Give → entity_binding update). Replaces former PL_001 §3.6 `actor_binding` mutations. |
| Entity birth (canonical seed or runtime spawn) | **EVT-T4 System** | `EntityBorn` | DP-Internal (RealityManifest bootstrap) or world-service (runtime spawn via author Forge / NPC scheduler / Item drop) | Cell membership emitted alongside via DP-A18 `MemberJoined`. |
| Entity lifecycle transition (Existing → Suspended / Destroyed / Removed / restore) | **EVT-T3 Derived** | `aggregate_type=entity_binding` (lifecycle field delta) | Aggregate-Owner role | Causal-ref to trigger: Mortality kill (PCS_001) / NPC scheduler suspend (NPC_001) / admin decanonize (WA_002) / restore. |
| Affordance instance override | **EVT-T3 Derived** | `aggregate_type=entity_binding` (affordance_overrides field delta) | Aggregate-Owner role | Per-entity exception; default affordances declared at type level. |
| Entity proposal (LLM-suggested spawn) | **EVT-T6 Proposal** | `EntitySpawnProposal` | LLM-Originator role | V1+ feature; Forge author-review gate before promotion to EVT-T4. |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. EVT-T3 sub-types row already covers `aggregate_type=entity_binding` per Option C ("each aggregate-owner feature owns its delta-kinds").

---

## §3 Aggregate inventory

Two aggregates owned by EF_001:

### 3.1 `entity_binding` (T2 / Reality) — PRIMARY

Replaces PL_001's `actor_binding` (transferred 2026-04-26) with extended scope: covers all 4 EntityType variants uniformly via `LocationKind` discriminator.

```rust
#[derive(Aggregate)]
#[dp(type_name = "entity_binding", tier = "T2", scope = "reality")]
pub struct EntityBinding {
    pub entity_id: EntityId,                    // primary key — covers Pc/Npc/Item/EnvObject
    pub entity_type: EntityType,                // denormalized discriminator: stored as TEXT col for SQL filter
                                                // (sum-type variant tag isn't directly indexable); validator
                                                // enforces equality with entity_id variant per write
    pub location: EntityLocation,               // see below
    pub owner_node: NodeId,                     // writer-node binding (epoch-fenced; same model as PL_001 §3.6)
    pub lifecycle_state: LifecycleState,        // Existing | Suspended | Destroyed | Removed
    pub affordance_overrides: Option<AffordanceSet>,  // None = use type default; Some = per-instance override
    pub last_moved_fiction_time: FictionTime,   // for movement audit + V1+ proximity computations
    pub last_lifecycle_change_fiction_time: FictionTime,
}

pub enum EntityLocation {
    InCell { cell_id: ChannelId },
    HeldBy { holder: EntityId },                // holder MUST be Pc/Npc with be_received affordance ACTIVE
    InContainer { container: EntityId },        // container MUST be Item with be_contained_in affordance (V1+ flag)
    Embedded { parent: EntityId, slot: String },// parent typically EnvObject; slot is freeform ID (e.g., "lock_keyhole")
}
```

**Rules:**
- One row per `entity_id`. Primary key conflict = invariant violation.
- `entity_type` MUST match `entity_id` variant (validated at write-time per DP-A14). Field is denormalized for SQL indexing only; readers SHOULD prefer the variant tag of `entity_id` over the `entity_type` field.
- `location` transitions are atomic: an entity is in EXACTLY one place at a time.
- `lifecycle_state = Destroyed | Removed` → `location` is FROZEN at last value (audit trail); references to this entity from new EVT-T1 Submitted reject per §8.
- **Scene-roster vs audit-location split:** for `lifecycle_state ∈ {Destroyed, Removed}` the `entity_binding.location` field continues to return last-known cell for AUDIT/forensic queries. UI / scene roster / participant_presence / `who-is-here` queries MUST gate on `lifecycle_state = Existing` BEFORE listing the entity in the cell — DP emits `MemberLeft` on the lifecycle transition (§13.5), so participant_presence already reflects the absence; the binding's frozen location is for audit-only reads (e.g., "where did Lý Minh die?").
- `owner_node` resolution + handoff follows PL_001 §3.6 epoch-fence model unchanged (transferred wholesale).

### 3.2 `entity_lifecycle_log` (T2 / Reality, append-only)

Per-entity audit trail of lifecycle transitions. Separate from main `entity_binding` to preserve append-only semantics + bounded growth.

```rust
#[derive(Aggregate)]
#[dp(type_name = "entity_lifecycle_log", tier = "T2", scope = "reality", append_only)]
pub struct EntityLifecycleLog {
    pub entity_id: EntityId,
    pub events: Vec<LifecycleEvent>,            // append-only; ordered by fiction_time
}

pub struct LifecycleEvent {
    pub state_before: LifecycleState,
    pub state_after: LifecycleState,
    pub fiction_time: FictionTime,
    pub causal_ref: CausalRef,                  // EVT-A6 typed causal-ref to triggering submitted event
    pub reason_kind: LifecycleReasonKind,
}

pub enum LifecycleReasonKind {
    CanonicalSeed,                              // EntityBorn from RealityManifest
    RuntimeSpawn,                               // author Forge create / scheduled spawn
    PcMortalityKill,                            // PCS_001 mortality (Destroyed)
    NpcCold,                                    // NPC_001 R8 cold-decay → Suspended (auto)
    AdminDecanonize,                            // WA_002 Heresy admin removal → Removed (audit'd, double-approval)
    AutoRestoreOnCellLoad,                      // Suspended → Existing on PC arrival / cell-load (auto, no admin)
    AdminRestoreFromRemoved,                    // Removed → Existing via WA_003 Forge admin (RARE; double-approval audit'd)
    InteractionDestructive,                     // PL_005 Interaction Strike Lethal / Use destructive (Destroyed)
    HolderCascade,                              // entity transitioned because its holder/parent transitioned (see §6 cascade rules)
    Unknown,                                    // fallback; should be rare
}
```

**Why split from `entity_binding`:** lifecycle log is append-only audit; `entity_binding` is current-state with frequent location updates. Splitting prevents log growth from inflating snapshot size. Mirrors R8 split pattern (NPC core vs npc_session_memory).

**Bounded growth (V1+ archiving — tracked as EF-D10 §15):** `events: Vec<LifecycleEvent>` grows unboundedly per row in V1. For high-churn entities (V1+ respawning Items, NPC cold-cycling), inflation is real (mirrors R1 event-volume risk inside a snapshot). V1+ archiving rule (deferred): events older than 90 fiction-days OR row size > 100 events split to cold-storage `entity_lifecycle_log_archive` table; current row keeps last 20 events for fast-path audit. Profiling threshold V1+30d.

---

## §4 EntityKind trait specification

The contract every aggregate-owner feature implements to be addressable as an Entity. EF_001 owns the trait definition; consumer features own the implementations.

**Trait scope (Phase 3 cleanup 2026-04-26):** the trait describes properties the aggregate BODY owns — identity, type discriminator, type-level affordance default, display rendering. Lifecycle state and effective affordances are properties of the **binding** (an entity can change cell + lifecycle without the body changing) — they are NOT on the trait. Use `EntityBindingExt` (below) for those reads. This separation keeps the trait composable with `&dyn EntityKind` dyn dispatch (binding-borrowed methods would have forced lifetime parameters into the vtable).

```rust
pub trait EntityKind: Aggregate {
    /// Stable Entity identity (matches the variant tag of self).
    fn entity_id(&self) -> EntityId;

    /// Discriminator (matches entity_id variant 1:1).
    fn entity_type(&self) -> EntityType;

    /// Type-level affordance default. PCS_001 / NPC_001 / Item / EnvObject MUST declare.
    /// `&self` parameter is unused but required to enable `&dyn EntityKind` dynamic dispatch
    /// (associated functions without `&self` cannot be called on trait objects).
    /// No default impl — forces every consumer to declare the default explicitly.
    fn type_default_affordances(&self) -> AffordanceSet;

    /// Human-readable display name in the requested locale. Used by failure UX,
    /// LLM prompt assembly, narrator text. Locale codes: `"vi"` V1; `"en"` V1+.
    /// Caller-allocated return; consumers should cache at AssemblePrompt boundary.
    fn display_name(&self, locale: &str) -> String;
}
```

**Binding-side queries** (read directly from `&EntityBinding`; convenience extension trait):

```rust
pub trait EntityBindingExt {
    /// Current lifecycle state.
    fn lifecycle_state(&self) -> LifecycleState;

    /// Effective affordance set: per-instance override if Some, else type-default.
    /// Caller must supply the type-default (looked up once per entity_type at registry).
    fn effective_affordances(&self, type_default: AffordanceSet) -> AffordanceSet;
}

impl EntityBindingExt for EntityBinding {
    fn lifecycle_state(&self) -> LifecycleState { self.lifecycle_state }
    fn effective_affordances(&self, type_default: AffordanceSet) -> AffordanceSet {
        self.affordance_overrides.unwrap_or(type_default)
    }
}
```

**Why split:** lifecycle and affordance-effective are derivable from a single `&EntityBinding` borrow (no body needed). The body trait stays minimal — body-only properties — which lets world-service hold `Box<dyn EntityKind>` heterogeneous registries cheaply. EVT-V_entity_affordance validator looks up `entity_type → type_default_affordances` from a registry (PCS_001/NPC_001/Item/EnvObject register their concrete impls) then combines with `&binding.effective_affordances(type_default)`.

**Implementation requirement matrix** (locked at EF_001; tracked in feature design docs):

| EntityType | Implementing aggregate | Default affordances V1 | Owner feature |
|---|---|---|---|
| Pc | `pc` (PCS_001 when designed) | `be_spoken_to + be_struck + be_examined + be_given + be_received + be_used` (full set V1 — PCs do everything) | PCS_001 |
| Npc | `npc` (NPC_001 R8-imported) | `be_spoken_to + be_struck + be_examined + be_given + be_received` (no `be_used` — NPCs aren't tools) | NPC_001 |
| Item | `item` (future Item feature) | `be_examined + be_used + be_given + be_received` (no `be_spoken_to` / `be_struck` — items aren't speech targets V1) | Future Item feature |
| EnvObject | `env_object` (future EnvObject feature) | `be_examined + be_used` (V1 minimum: examine + interact) | Future EnvObject feature |

Per-instance overrides via `entity_binding.affordance_overrides`:
- Merchant NPC: NPC_001 base + (no override needed; full default fits)
- Bandit NPC: NPC_001 base − `be_given` (refuses gifts in-fiction)
- Talking Sword (rare): Item base + `be_spoken_to` (override)
- Locked door: EnvObject base − `be_used` (until key applied; lifecycle-modeled via EnvObject feature)

---

## §5 EntityId taxonomy + ID format

```rust
pub enum EntityId {
    Pc(PcId),
    Npc(NpcId),
    Item(ItemId),
    EnvObject(EnvObjectId),
}

pub struct PcId(pub Uuid);
pub struct NpcId(pub Uuid);
pub struct ItemId(pub Uuid);
pub struct EnvObjectId(pub Uuid);
```

**Rules:**
- Variants are **closed V1**. New variants require lock-claim + boundary review (additive per I14, no removals).
- All four variants are **UUID-backed** (UUID v7 V1 for time-ordered insertions; matches PCS_001 brief default).
- IDs are **reality-scoped** at the `entity_binding` row level (composite key `(reality_id, entity_id)` at storage layer; logical `EntityId` is reality-internal). Cross-reality references not supported V1.
- ID **prefix in display/log** (UX only, not in struct): `pc_<uuid>` · `npc_<uuid>` · `itm_<uuid>` · `env_<uuid>`. Helps debugging and narrator text.

**Why sum type over generic ID:** compile-time exhaustiveness — Rust pattern-match on `EntityId` forces every consumer to handle all 4 variants OR explicitly mark `_ => …` as catch-all. Catches new-variant-not-handled bugs at compile time. V1+ adding `Vehicle` will surface every match site that needs updating.

### 5.1 Relationship to `ActorId` (NPC_001 §2)

`ActorId` and `EntityId` are **two distinct types** with overlapping but non-coincident variant sets. They serve different API surfaces and intentionally do NOT collapse into one — collapsing would corrupt either "things in the world" or "agents that submit turns" semantics.

```rust
// EF_001 §5 — addressable things in the world
pub enum EntityId { Pc(PcId), Npc(NpcId), Item(ItemId), EnvObject(EnvObjectId) }

// NPC_001 §2 — actors with turn-submission capability
pub enum ActorId { Pc(PcId), Npc(NpcId), Synthetic { kind: SyntheticActorKind }, Admin(AdminId) }
```

| Variant | In ActorId | In EntityId | Reason |
|---|---|---|---|
| Pc | ✓ | ✓ | PCs are both turn-submitting actors AND addressable entities |
| Npc | ✓ | ✓ | Same as PCs |
| Synthetic (orchestrator, scheduler, BubbleUpAggregator, RealityBootstrapper) | ✓ | ✗ | System actors that emit events but aren't "things in the world" — no `entity_binding` row, no spatial location, no lifecycle |
| Admin | ✓ | ✗ | S5 admin actors emit events but aren't in-fiction entities |
| Item | ✗ | ✓ | Items are addressable (PL_005 tool / target) but don't submit turns — no agency |
| EnvObject | ✗ | ✓ | Same as Items — passive |

**Conversion contract:** `From<ActorId> for Option<EntityId>` (Pc/Npc → Some; Synthetic/Admin → None) and `From<EntityId> for Option<ActorId>` (Pc/Npc → Some; Item/EnvObject → None). Standard library provides infallible conversion only for the Pc + Npc intersection:

```rust
impl From<PcId> for ActorId { ... }     // ActorId::Pc
impl From<PcId> for EntityId { ... }    // EntityId::Pc
impl From<NpcId> for ActorId { ... }
impl From<NpcId> for EntityId { ... }
// no infallible ActorId -> EntityId or vice versa (information loss possible)
```

**API guidance:**
- "submitter of a turn" → use `ActorId` (covers Synthetic + Admin which Items can't do)
- "target of an interaction" / "thing in scene" / "addressable for entity_binding" → use `EntityId`
- "subject of a status effect" (PL_006 actor_status) → uses `ActorId` (only Pc/Npc have status V1; Synthetic/Admin are in-scope as future targets of admin-applied buffs/debuffs but Items/EnvObjects are NOT)

**No drift trap:** the two types describe genuinely different sets, not redundant copies. PL_006 keying on ActorId is correct (statuses apply to actors, not items). EF_001 keying on EntityId is correct (entity_binding tracks all addressable things). The Pc/Npc intersection is handled via explicit `From` impls; mismatched conversions fail at compile time.

---

## §6 LifecycleState state machine

```
                 ┌──────────────────────────────────┐
                 │                                  │
                 ▼                                  │
            ┌─────────┐    suspend       ┌──────────┴──┐
            │Existing │ ───────────────▶ │ Suspended    │
            │         │ ◀─────────────── │              │
            └─────────┘    restore       └──────────────┘
                 │
       destroy   │   admin_remove
            ┌────┴────┐
            ▼         ▼
       ┌──────────┐  ┌──────────┐
       │Destroyed │  │ Removed  │
       │(in-fiction)│  │(out-of-fiction)│
       └──────────┘  └──────────┘
            │             │
            │   admin_restore (RARE; audit'd)
            └──────┬──────┘
                   ▼
              ┌─────────┐
              │Existing │
              └─────────┘
```

**Transitions (allowed):**

| From → To | Trigger | Owner feature | reason_kind | Notes |
|---|---|---|---|---|
| `Existing` → `Suspended` | NPC scheduler cold-decay (NPC at distant cell with no PC for 14 fiction-days) | NPC_001 | `NpcCold` | Reversible without admin; auto-restore on cell-load. **V1 only NPCs go Suspended** — Items + EnvObjects stay `Existing` even at distant cells V1 (cold-loading deferred to future Item/EnvObject feature) |
| `Suspended` → `Existing` | NPC re-loaded on PC arrival at suspended-NPC's cell | NPC_001 | `AutoRestoreOnCellLoad` | No admin; in-fiction-time invisible |
| `Existing` → `Destroyed` | PC mortality (PCS_001) · Item destruction (Strike with sufficient damage; future Item) · NPC death (NPC_001 V1+30d) | PCS_001 / future Item / NPC_001 | `PcMortalityKill` / `InteractionDestructive` / feature-specific | In-fiction; persists in `entity_lifecycle_log` |
| `Suspended` → `Destroyed` | rare V1+: time-decay destruction (rotted food, expired potion) | future Item | `InteractionDestructive` (or dedicated feature variant) | V1+ only |
| `Existing` → `Removed` | admin: WA_002 Heresy decanonize · WA_003 Forge admin remove | WA_002 / WA_003 | `AdminDecanonize` | Out-of-fiction; "this entity never was" semantics |
| `Suspended` → `Removed` | admin removal of suspended entity | WA_002 / WA_003 | `AdminDecanonize` | Audit'd |
| `Destroyed` → `Existing` | rare: PCS_001 V1+ Respawn · Item resurrection (magic) | PCS_001 / future Item | feature-specific (`PcRespawn` / `ItemResurrect`) | NOT `AutoRestoreOnCellLoad` — destruction-restore is feature-specific not auto |
| `Removed` → `Existing` | RARE admin: WA_003 admin restore (regret operation) | WA_003 | `AdminRestoreFromRemoved` | Double-approval workflow (mirrors R9 9-state lifecycle); distinct from `AutoRestoreOnCellLoad` to preserve audit precision |

**Forbidden transitions** (validated at write-time; rejected with `entity.invalid_lifecycle_transition`):
- `Destroyed` → `Suspended` (must restore to `Existing` first)
- `Removed` → `Suspended` (admin restore goes to `Existing`)
- `Removed` → `Destroyed` (a removed-entity has no in-fiction state to destroy)

### 6.1 Cascade rules (holder/parent → held/child propagation)

When an entity transitions, entities REFERENCED by its `EntityLocation` (HeldBy holder, InContainer container, Embedded parent) need cascading transitions to keep the location graph consistent. Cascade is computed in a **single atomic write** alongside the trigger transition; lifecycle_log entries for cascaded entities use `reason_kind = HolderCascade` with `causal_ref` pointing at the trigger event.

| Trigger | Cascade |
|---|---|
| `Existing → Suspended` (holder/container/parent) | All directly-held + contained + embedded entities transition `Existing → Suspended` (composed lifecycle); their `location` fields are NOT updated (still `HeldBy(holder)` etc.) — they're un-loaded together with their holder |
| `Suspended → Existing` (holder cell-load) | Held + contained + embedded entities cascade `Suspended → Existing`; reason_kind `AutoRestoreOnCellLoad` |
| `Existing → Destroyed` (holder mortality / item smashed) | Held items DROP TO GROUND: their `location` flips `HeldBy(holder) → InCell(holder.last_cell_id)` AND lifecycle_state stays `Existing` (the items survive their owner). `InContainer` items behave the same (container destroyed → contents drop to last cell). `Embedded` children CASCADE-DESTROY (`Existing → Destroyed`, reason_kind `HolderCascade`) — embedded keys/inscriptions don't outlive their parent EnvObject. |
| `Existing → Removed` (admin decanonize) | All held + contained + embedded entities CASCADE-REMOVE (`Existing → Removed`, reason_kind `HolderCascade`). Admin removal is "this never existed" — held descendants follow. |

**Why differing semantics** (Destroyed cascades drop, Removed cascades remove): `Destroyed` is in-fiction; corpses leave their inventory behind for narrative/economic continuity. `Removed` is out-of-fiction; the entity and all its descendants must vanish from canon to maintain "never was" semantics.

**Validator enforcement:** EF_001 owns a `cascade_lifecycle_transition()` helper called by transition writers (PCS_001 / NPC_001 / WA_002 / WA_003 / future Item). The helper computes the cascade tree, emits the corresponding `entity_binding` deltas + `entity_lifecycle_log` events as a single atomic batch. Cycles in the holder graph are rejected at write-time (`entity.cyclic_holder_graph` rule_id, V1+ if needed).

---

## §7 AffordanceFlag closed enum + enforcement

```rust
#[bitflags]                     // enumflags2 macro (NOT the bitflags crate; bitflags crate
                                // generates a struct from a non-enum macro and lacks the
                                // `BitFlags<T>` generic ergonomics this design relies on)
#[repr(u8)]                     // 6 V1 + 7 V1+ reserved → fits in u16; u8 only safe V1 (6 bits)
pub enum AffordanceFlag {
    BeSpokenTo  = 0b00000001,   // Speak target — addressee
    BeStruck    = 0b00000010,   // Strike target
    BeExamined  = 0b00000100,   // Examine target
    BeGiven     = 0b00001000,   // Give recipient (active receiver — accepts gifts)
    BeReceived  = 0b00010000,   // Give → received-by-target (passive — can BE the held item)
    BeUsed      = 0b00100000,   // Use target — instrument or toolable thing
}

pub type AffordanceSet = enumflags2::BitFlags<AffordanceFlag>;
// V1+ extension: when reserved flags (§7 V1+ list) are activated, repr widens to u16.
// Migration is non-breaking on disk (u8 zero-pads to u16 cleanly).
```

**Mapping to PL_005 InteractionKind validators:**

| InteractionKind | Required affordance on | Validator slot |
|---|---|---|
| `Speak` | direct_targets — `BeSpokenTo` | EVT-V_entity_affordance (NEW slot — see §11) |
| `Strike` | direct_targets — `BeStruck`; tool (if present) — `BeUsed` | same |
| `Examine` | direct_targets — `BeExamined` | same |
| `Give` | recipient direct_target — `BeGiven`; tool (the gifted item) — `BeReceived` | same |
| `Use` | tool — `BeUsed`; direct_targets (if any) — `BeUsed` (if tool used ON something) | same |

Validator runs at the EVT-V_entity_affordance slot (placement TBD — see EF-Q3 in §18; structural-affordance check ordering relative to EVT-V_lex / EVT-V_heresy is open). Convention follows "structural-before-semantic" — affordance check happens before per-kind business logic (Lex world-rule, Heresy contamination, kind-specific validators). Failure → reject with `entity.affordance_missing { entity_id, required_flag }` per §8.

**V1+ flag reservations** (closed enum extends additively per I14):
- `BeCollidedWith` — Collide kind (V1+ Interaction)
- `BeShotAt` — Shoot kind (V1+ Interaction)
- `BeCastAt` — Cast spell kind (V1+ Interaction)
- `BeEmbraced` — Embrace kind (V1+ Interaction; intimate-context-gated)
- `BeThreatened` — Threaten kind (V1+ Interaction)
- `BeTraveledTo` — Travel destination kind (V1+ explicit travel-to-entity vs travel-to-cell)
- `BeContainedIn` — required for `EntityLocation::InContainer.container` field

---

## §8 Reference safety policy

EF_001 owns the **`entity.*` RejectReason namespace** in PL_001 envelope.

**Hard-reject default + per-interaction-kind soft override.**

| rule_id | Trigger | Vietnamese reject copy V1 | Soft-override eligible |
|---|---|---|---|
| `entity.entity_destroyed` | reference targets `EntityId` with `lifecycle_state = Destroyed` | "Đối tượng đó đã không còn tồn tại trong thực tại này (đã bị phá hủy)." | Yes (Examine soft-fallbacks to "[ruined / destroyed remains]" narrator text) |
| `entity.entity_removed` | reference targets `EntityId` with `lifecycle_state = Removed` | "Đối tượng đó không tồn tại trong thực tại này." | No (admin removal is out-of-fiction; no Examine fallback — narrator must not acknowledge it ever existed) |
| `entity.entity_suspended` | reference targets `EntityId` with `lifecycle_state = Suspended` and current cell ≠ entity's cell | "Đối tượng đó hiện không có mặt ở nơi này." | Maybe (Speak rejects; Examine could narrate "not here" ambiguously) |
| `entity.affordance_missing` | InteractionKind required affordance NOT in target's effective AffordanceSet | "Hành động này không áp dụng được với đối tượng đó." | No (mechanical refusal) |
| `entity.invalid_entity_type` | location_kind requires specific entity_type and target violates (e.g., HeldBy targets EnvObject — holder must be Pc/Npc) | "Cấu trúc vị trí không hợp lệ cho đối tượng đó." | No (write-time validator) |
| `entity.invalid_lifecycle_transition` | aggregate-owner attempts forbidden transition (§6) | "Chuyển đổi trạng thái không hợp lệ." | No (write-time validator) |
| `entity.unknown_entity` | `EntityId` resolves to no `entity_binding` row | "Không tìm thấy đối tượng." | No (always reject; helps debug) |
| `entity.duplicate_binding` | second write attempt for an `entity_id` that already has an `entity_binding` row (primary-key violation; only `EntityBorn` may CREATE a row) | "Đối tượng này đã được đăng ký." | No (write-time invariant) |
| `entity.entity_type_mismatch` | denormalized `entity_type` field doesn't match the variant tag of `entity_id` (e.g., `entity_id: Pc(...)` with `entity_type: Npc`) | "Loại đối tượng không khớp với định danh." | No (write-time validator; distinct from `invalid_entity_type` which is about location_kind constraints) |
| `entity.lifecycle_log_immutable` | attempted in-place mutation or removal of a previously-appended `LifecycleEvent` in `entity_lifecycle_log.events` (DP-A12 append-only contract; rejection bubbles up from DP layer wrapped in `entity.*` namespace for failure UX consistency) | "Nhật ký lịch sử đối tượng không thể sửa." | No (DP append_only enforcement) |

**V1+ rule_id reservations** (additive per I14, declared here for namespace stability):

| rule_id | Trigger | Activation |
|---|---|---|
| `entity.cyclic_holder_graph` | proposed `EntityLocation` change would create a cycle in the holder/container/parent graph (e.g., Item A `HeldBy` B and B `HeldBy` A) | V1+ when container/embedded enforcement lands (EF-D3 / EF-D4); V1 holder graph is shallow (Item `HeldBy` PC/NPC only) so cycle is structurally impossible |
| `entity.cross_reality_reference` | reference targets `EntityId` from a different reality | V1+ when multiverse portals land (EF-D6) |

**Soft-override mechanism:** PL_005 InteractionKind declares per-kind tolerance flags in its kind_spec:
```rust
pub struct InteractionKindSpec {
    pub kind: InteractionKind,
    pub tolerates_destroyed: bool,      // Examine = true; others = false V1
    pub tolerates_suspended: bool,      // Examine = true (with caveat); others = false
}
```
Validator slot consults these flags before rejecting; if soft-override active, narrates per-kind soft text instead of rejecting the whole turn.

---

## §9 DP primitives consumed

EF_001 implements two aggregates against the locked DP contract; no new primitives needed.

| DP primitive | Used for | Pattern |
|---|---|---|
| `t2_read(entity_binding, key=entity_id)` | look up entity location + lifecycle | Hot-path; cached per DP-K6 subscribe |
| `t2_write(entity_binding, key=entity_id, mutation)` | move / suspend / destroy / remove | Aggregate-Owner role; write per DP-K5 |
| `t2_append(entity_lifecycle_log, key=entity_id, event)` | append lifecycle event | Append-only per DP-A12 |
| `subscribe(entity_binding, filter)` | UI invalidation on entity move; PL_005c cascade hooks | DP-K6 durable subscribe; bubble-up to channel-aggregator |
| `t2_scan(entity_binding, filter)` | rare admin queries (find all entities in cell) | NOT hot-path; admin/audit only — DP-A8 prohibits live scan in turn loop |

**No new DP-K* primitives requested.** EF_001 fits within existing kernel surface.

---

## §10 Capability JWT claims

EF_001 declares no new top-level capability claim. Reuses existing claims:

- `produce: ["AggregateMutation"]` — required to write `entity_binding` + `entity_lifecycle_log` (already present for world-service)
- Per-aggregate write capability under `capabilities[]` per DP-K9 — needs `entity_binding:write` + `entity_lifecycle_log:append`

**Service binding:** world-service is the canonical writer for `entity_binding` (mirrors PL_001's `actor_binding` ownership). Aggregate handoff between world-service nodes follows PL_001 §3.6 epoch-fence model unchanged.

---

## §11 Subscribe pattern

UI invalidation + downstream feature consumption via DP-K6 subscribe.

**Subscribers V1:**

| Subscriber | Filter | Purpose |
|---|---|---|
| Frontend (player UI) | `entity_binding WHERE cell_id = current_cell` | "who/what is here" view; auto-refresh on entity_binding deltas |
| NPC_002 Chorus orchestrator | `entity_binding WHERE entity_type=Npc AND cell_id IN cells_orchestrated` | scene-roster context for reaction batching |
| PL_005c Interaction integration | `entity_binding WHERE entity_id IN interaction.targets` | cascade hooks (Strike Lethal → mortality state machine) |
| WA_002 Heresy stability tracker | `entity_binding WHERE lifecycle_state ∈ {Destroyed, Removed}` | aggregate decanonize-rate metric |

**New validator slot:** EVT-V_entity_affordance (between EVT-V_lex/heresy and EVT-V_kind-specific). See `_boundaries/03_validator_pipeline_slots.md` (alignment update needed).

---

## §12 Cross-service handoff

Entity references cross service boundaries via `EntityId` (sum type variant tag carries entity_type info, no separate type tag needed in JSON).

**Handoff serialization:**
```json
{ "entity_id": { "type": "Pc", "id": "550e8400-e29b-41d4-a716-446655440000" } }
{ "entity_id": { "type": "Npc", "id": "..." } }
{ "entity_id": { "type": "Item", "id": "..." } }
{ "entity_id": { "type": "EnvObject", "id": "..." } }
```

**Causality token chain:** entity_binding mutations include CausalityToken (per DP causality model) referencing the triggering EVT-T1 Submitted. Replay-determinism preserved per EVT-A9 (entity moves are deterministic given input event + RNG seed).

**Cross-service consumers:**
- world-service → EF_001 owner (writes)
- roleplay-service → reads via subscribe (LLM context: "what's in this cell")
- knowledge-service → reads via subscribe (per-PC isolation for retrieval)
- frontend → reads via subscribe (UI)

---

## §13 Sequences (5 V1 representative flows)

### 13.1 Canonical entity birth (RealityManifest seed)

```
RealityManifest.canonical_actors[i] = { entity_type: Npc, npc_id: ..., starting_cell: ..., ... }
  ↓ (bootstrap)
RealityBootstrapper (Synthetic actor) emits EVT-T4 System EntityBorn { entity_id, entity_type, cell_id }
  ↓ (atomic with bootstrap transaction)
write entity_binding row { entity_id, entity_type, location: InCell(cell_id), owner_node, lifecycle_state: Existing, ... }
write entity_lifecycle_log event { state_before: ⊥, state_after: Existing, reason_kind: CanonicalSeed }
DP emits MemberJoined for cell channel (per DP-A18)
```

### 13.2 Move via Travel command (PL_002 /travel)

```
Player issues /travel destination=cell:tay_thi_quan
  ↓ EVT-T1 Submitted PCTurn { kind: Travel }
PL_001 §13 travel sequence runs:
  - validates: pc has be_traveled_to capability (V1: always true) + destination accessible
  - on accept: t2_write entity_binding { entity_id: Pc(pc_id), location: InCell(tay_thi_quan), last_moved_fiction_time: now }
  - emit EVT-T3 Derived { aggregate_type: entity_binding, delta: { location: InCell(...) } }
  - DP emits MemberLeft(yen_vu_lau) + MemberJoined(tay_thi_quan)
```

### 13.3 Give item (PL_005 Interaction)

```
PC Lý Minh issues Interaction.Give { tool: ItemId(silver_coin), recipient: NpcId(lao_ngu) }
  ↓ EVT-T1 Submitted Interaction:Give
EF_001 EVT-V_entity_affordance validator runs:
  - check tool=Item(silver_coin): has BeReceived? → yes (default Item set)
  - check recipient=Npc(lao_ngu): has BeGiven? → yes (default NPC set, not overridden)
  - check tool location: HeldBy=Pc(ly_minh)? → yes
  → pass
  ↓ PL_005 Give per-kind validator runs (Lex Forge etc.) → pass
  ↓ on commit:
    t2_write entity_binding { entity_id: Item(silver_coin), location: HeldBy(Npc(lao_ngu)) }
    emit EVT-T3 Derived { aggregate_type: entity_binding, ... }
```

### 13.4 Suspend NPC via cold-decay (NPC_001)

```
NPC scheduler detects: Npc(tieu_thuy) at cell:yen_vu_lau, no PC in cell for 14 fiction-days
  ↓ NPC_001 emits ColdDecaySuspend { npc_id }
EF_001 lifecycle transition:
  - t2_write entity_binding { entity_id: Npc(tieu_thuy), lifecycle_state: Suspended, last_lifecycle_change_fiction_time: now }
  - t2_append entity_lifecycle_log { Existing → Suspended, reason_kind: NpcCold }
  - DP emits MemberLeft(yen_vu_lau) (cell channel sees suspension as "left")
PC arrives later → NPC_001 detects need to load → EF_001 transitions Suspended → Existing
  - t2_write entity_binding { ..., lifecycle_state: Existing }
  - t2_append entity_lifecycle_log { Suspended → Existing, reason_kind: AdminRestore /* or distinct ReasonKind::ColdRestore */ }
```

### 13.5 Destroy via Mortality (PCS_001 future)

```
PC Lý Minh receives Strike Lethal from bandit NPC
  ↓ EVT-T1 Submitted Interaction:Strike (with damage=Lethal flag)
PL_005c §mortality-side-effect-flow runs:
  - PCS_001 mortality state machine: Existing → MortalityTransition → Destroyed (per WA_006 mortality_config)
EF_001 lifecycle transition (cascaded):
  - t2_write entity_binding { entity_id: Pc(ly_minh), lifecycle_state: Destroyed, location: InCell(<frozen_at_death>) }
  - t2_append entity_lifecycle_log { Existing → Destroyed, reason_kind: PcMortalityKill, causal_ref: <strike_event> }
Future EVT-T1 Submitted referencing Pc(ly_minh) as agent reject with `entity.entity_destroyed` (unless PCS_001 V1+ Respawn restores).
```

---

## §14 Acceptance criteria

10 V1-testable scenarios (AC-EF-1..10). Each names the §-rule it tests + the rule_id (for reject scenarios) so closure-pass auditors can verify rule existence.

1. **AC-EF-1 — EntityId variant exhaustiveness (compile-time + lint):** (a) Rust unit test that uses `match entity_id` without a default arm covering all 4 variants compiles; (b) Rust unit test that omits `Item` arm fails to compile with `error[E0004]: non-exhaustive patterns`; (c) CI lint rule (clippy custom or codebase grep) flags any `match … { _ => … }` on `EntityId` outside the 3 designated catch-all sites (logging / serialization / debug-print) — flagged matches block merge until annotated `// EF-EXHAUSTIVE-EXEMPT: <reason>`. Tests rule from §5 "Why sum type over generic ID."
2. **AC-EF-2 — entity_binding primary-key unique:** attempting to `t2_write` a second row for an `entity_id` that already has a row returns reject `entity.duplicate_binding`. Tests §3.1 rule "One row per entity_id" + §8 namespace.
3. **AC-EF-3 — entity_type matches variant:** writing `entity_binding { entity_id: Pc(...), entity_type: Npc, ... }` rejects `entity.entity_type_mismatch`. Tests §3.1 denormalization invariant + §8 namespace.
4. **AC-EF-4 — Lifecycle forbidden transitions reject:** attempting `Removed → Suspended` (or `Destroyed → Suspended` or `Removed → Destroyed`) rejects `entity.invalid_lifecycle_transition`. Tests §6 forbidden-transitions table + §8 namespace.
5. **AC-EF-5 — Affordance hard-reject:** Speak target an Item with default-only AffordanceSet (no `BeSpokenTo`) rejects `entity.affordance_missing { entity_id, required_flag: BeSpokenTo }`. Tests §4 implementation matrix (Item default lacks BeSpokenTo) + §7 enforcement mapping + §8 namespace.
6. **AC-EF-6 — Affordance soft-override Examine on Destroyed:** Examine InteractionKind (which has `tolerates_destroyed=true` per PL_005 InteractionKindSpec implementing §8 contract) targeting a Destroyed entity returns success with narrator text "[còn lại tàn tích]" (or similar Vietnamese soft-text per PL_005), NOT `entity.entity_destroyed` reject. Cross-feature dependency: PL_005 must declare `tolerates_destroyed: true` for Examine kind (DRAFT-stage now). Tests §8 soft-override mechanism.
7. **AC-EF-7 — Reference to Removed always rejects:** any InteractionKind targeting `Removed` entity rejects `entity.entity_removed` regardless of `tolerates_destroyed` flag (no soft-override available for Removed, even Examine). Tests §8 namespace row "Soft-override eligible: No".
8. **AC-EF-8 — Suspended NPC re-load atomically with cell-load:** Suspended NPC at cell C, PC enters cell C → within the SAME `move_entity_to_cell` write transaction (atomic; before turn-validators see the post-move state): (a) NPC transitions `Suspended → Existing` with `reason_kind=AutoRestoreOnCellLoad`; (b) DP emits `MemberJoined` for NPC on cell C; (c) participant_presence row for NPC on cell C is `Active`. PC sees NPC in scene roster on first read after PC's move turn commits. Tests §6 transition + §13.4 sequence; "atomically" = same single write transaction at writer-node, not eventual consistency.
9. **AC-EF-9 — entity_lifecycle_log append-only:** attempting to UPDATE or DELETE a previously-appended `LifecycleEvent` in `events` Vec rejects `entity.lifecycle_log_immutable`. Append-only is enforced at DP-A12 layer (`#[dp(append_only)]` on the aggregate); the rejection wraps DP-emitted error with EF_001's `entity.*` namespace for failure-UX consistency. Tests §3.2 contract + §8 namespace.
10. **AC-EF-10 — Cross-entity Give updates location atomically (single write tx):** PC Gives Item to NPC → exactly ONE `entity_binding` row update for the Item (`HeldBy(Pc) → HeldBy(Npc)`) within the EVT-T1 Submitted commit transaction. No additional row updates required (PC and NPC bodies are NOT touched — Item's new holder is encoded in Item's binding only; "PC's inventory" / "NPC's inventory" are read-views over `entity_binding WHERE location.HeldBy = pc_id` etc., not stored aggregates). Atomicity scope: Postgres transaction guarantees; no intermediate state observable to readers in the same reality (DP-A19 ≤1s projection lag still applies for cross-reality readers but per §5 cross-reality refs not V1). Tests §13.3 sequence + §3.1 atomic-location rule.

---

## §15 Deferrals

| ID | What | Why deferred | Target phase |
|---|---|---|---|
| **EF-D1** | V1+ EntityId variants (Vehicle / Spirit / Building / Quest / Channel) | Not V1-blocking; additive per I14 when needed | When first such feature designed |
| **EF-D2** | V1+ AffordanceFlag extensions (BeCollidedWith / BeShotAt / BeCastAt / BeEmbraced / BeThreatened / BeTraveledTo / BeContainedIn) | Map to V1+ InteractionKind reservations | Each V1+ kind design |
| **EF-D3** | EntityLocation::InContainer enforcement | requires `BeContainedIn` affordance + container Item feature | Future Item feature |
| **EF-D4** | EntityLocation::Embedded full semantics (slot taxonomy, lock/unlock pattern) | needs EnvObject feature for parent type | Future EnvObject feature |
| **EF-D5** | EVT-T6 Proposal `EntitySpawnProposal` (LLM-suggested entity creation with author-review gate) | V1+ Forge author workflow | Future Forge V2 / EntityProposal feature |
| **EF-D6** | Cross-reality entity references (e.g., portal between realities) | not V1; multiverse §multiverse-portal still open | V2+ multiverse expansion |
| **EF-D7** | Hidden / fog-of-war 5th lifecycle state | not V1; current 4-state covers Mortality + R8 + admin | V1+30d if quest/exploration needs |
| **EF-D8** | Entity component registry (full ECS) | concrete-aggregate + EntityKind trait approach chosen V1 (Q5); ECS is V2+ if entity zoo grows beyond manageable concrete types | V2+ when entity zoo exceeds ~6 types |
| **EF-D9** | Per-affordance grant policy (e.g., `be_spoken_to` requires shared language) | V1: affordance is pure boolean; nuance pushed to per-kind validators (PL_005 + WA_001 Lex) | V1+ social/language expansion |
| **EF-D10** | `entity_lifecycle_log` archiving (split events older than 90 fiction-days OR row size > 100 events to `entity_lifecycle_log_archive`) | V1: per-entity Vec grows unboundedly; high-churn entities (V1+ respawning Items, NPC cold-cycle) inflate row size — mirrors R1 event-volume risk inside a snapshot | V1+30d profiling threshold; ops review |

---

## §16 Cross-references

- **PL_001 Continuum** §3.6 — `actor_binding` transferred to EF_001 as `entity_binding` (renamed + scope-grown 2026-04-26). PL_001 reopen: §3.6 now references EF_001 as owner; PL_001's role is referencer.
- **PL_005 Interaction** §3.X — 5 V1 InteractionKinds reference `EntityId` (replacing `ActorId | ItemRef`) for tool / direct_targets / indirect_targets. Affordance validation runs at EF_001 EVT-V_entity_affordance slot before per-kind validator chain.
- **PL_005c Interaction integration** §V1-scope — Item "refs only V1" gap CLOSED by EF_001 owning ItemId variant + `entity_binding` row for Items. Future Item feature owns Item body; PL_005 V1 implementable against EF_001 contract.
- **PL_006 Status Effects** — `actor_status` keyed by `ActorId` is correct and NOT a drift trap (clarified 2026-04-26 review per §5.1): ActorId and EntityId are genuinely different sets — Items/EnvObjects don't have status V1 (they aren't actors), and Synthetic/Admin actors aren't entity-addressable. PL_006 stays as designed; if V1+ Item buffs/debuffs become a thing, that's a PL_006 reopen with explicit scope expansion (not a forced rekey).
- **NPC_001 Cast** — implements `EntityKind for Npc`. ActorId enum (NPC_001 §2) is a SIBLING type to EntityId (NOT a subset — see §5.1): ActorId carries Synthetic + Admin variants which EntityId lacks; EntityId carries Item + EnvObject which ActorId lacks. The Pc + Npc intersection has explicit `From` impls. NPC_001's `ActorId` definition stays in NPC_001 §2 as the canonical actor-context type; EF_001 §5.1 documents the relationship.
- **NPC_002 Chorus** — subscribes to `entity_binding` filtered by entity_type=Npc + cell for scene roster.
- **PCS_001** (when designed) — implements `EntityKind for Pc`; mortality state machine cascades into EF_001 lifecycle transitions; brief at `features/06_pc_systems/00_AGENT_BRIEF.md` updated to require EF_001 reading.
- **WA_002 Heresy** — admin decanonize → EF_001 lifecycle Existing/Suspended → Removed.
- **WA_003 Forge** — admin restore (RARE; double-approval) → Removed → Existing transition.
- **WA_006 Mortality** — `pc_mortality_state` (handed off to PCS_001) feeds into EF_001 lifecycle Destroyed transitions.
- **07_event_model** — EVT-T3 Derived sub-types row covers `aggregate_type=entity_binding` + `aggregate_type=entity_lifecycle_log`. EVT-T4 System sub-type EntityBorn declared by EF_001.
- **06_data_plane** — entity_binding + entity_lifecycle_log aggregates sit in T2/Reality scope per existing DP contract. No new primitives.
- **02_storage R8** — NPC core split unchanged; entity_binding does NOT replace `npc.current_region_id`/`current_session_id` fields (those are NPC-internal); EF_001 binding is the cross-entity authoritative location.

---

## §17 Readiness checklist

- [x] Domain concepts table covers EntityId / EntityType / LifecycleState / AffordanceFlag / EntityKind trait
- [x] Aggregate inventory: 2 aggregates (`entity_binding` primary + `entity_lifecycle_log` audit-only); audit-log archiving deferral logged (EF-D10)
- [x] EntityKind trait specified — body-only methods (id / type / type_default_affordances / display_name); lifecycle + affordance-effective live on `EntityBinding` via `EntityBindingExt`; per-type default-affordance matrix
- [x] LifecycleState 4-state machine with allowed/forbidden transitions; cascade rules for HeldBy/InContainer/Embedded propagation (§6.1)
- [x] AffordanceFlag 6 V1 flags + V1+ reservations + per-kind enforcement mapping; bitflag repr explicit (`enumflags2::BitFlags<AffordanceFlag>` over u8 V1, u16 V1+)
- [x] Reference safety policy: hard-reject + per-kind soft-override; **10 V1 rule_ids** in `entity.*` namespace (entity_destroyed / entity_removed / entity_suspended / affordance_missing / invalid_entity_type / invalid_lifecycle_transition / unknown_entity / duplicate_binding / entity_type_mismatch / lifecycle_log_immutable) + 2 V1+ reservations (cyclic_holder_graph / cross_reality_reference)
- [x] Event-model mapping: EVT-T3 Derived + EVT-T4 System + EVT-T6 Proposal (V1+); no new EVT-T*
- [x] DP primitives: existing surface only (no new DP-K*)
- [x] Capability JWT: existing claims (no new top-level)
- [x] Subscribe pattern: 4 subscribers V1 (Frontend / NPC_002 / PL_005c / WA_002)
- [x] Cross-service handoff: EntityId JSON shape + CausalityToken chain
- [x] ActorId / EntityId relationship documented (§5.1); explicit "no drift" with PL_006 ActorId keying
- [x] 5 representative sequences
- [x] 10 V1-testable acceptance scenarios (AC-EF-1..10)
- [x] 10 deferrals (EF-D1..D10) with target phases
- [x] Cross-references to all 11 affected features + foundation docs
- [x] Phase 3 review cleanup applied 2026-04-26 (Severity 1 + 2 + 3 — Rust correctness on `type_default_affordances` `&self` + `enumflags2` syntax; EntityKind trait shape split; cascade rules; AdminRestore split into AutoRestoreOnCellLoad + AdminRestoreFromRemoved + HolderCascade; ActorId/EntityId relationship; participant_presence reconciliation rule; entity_type denorm justification; EF-D10 archiving deferral)
- [x] Closure-pass walk-through 2026-04-26 — §14 acceptance criteria walked AC-EF-1..10; 3 rule_id mismatches resolved by expanding §8 namespace 7 → 10 V1 + 2 V1+ reservations; 3 ACs (1, 8, 10) precision-tightened with explicit grounding citations
- [x] **CANDIDATE-LOCK 2026-04-26** — downstream rename verification ✓ (10 files, 42 occurrences, mechanical sweep in commit 04607ea); PCS_001 brief update ✓ (§4.4b mandatory EF_001 reading section added 2026-04-26 in commit 04607ea); boundary matrix transfer recorded ✓; extension contracts §1.4 entity.* namespace updated ✓; changelog appended ✓

---

## §18 Open questions (post-DRAFT)

| ID | Question | Resolution path |
|---|---|---|
| **EF-Q1** | Should `entity_lifecycle_log` be a separate aggregate or a column on `entity_binding`? Trade-off: separate = clean append-only + bounded snapshot; column = simpler reads. | Boundary review V1+ if profiling shows pain; current split mirrors R8 precedent |
| **EF-Q2** | Does NPC_001 keep its `npc.current_region_id` field after EF_001 lands, or migrate fully to entity_binding? | NPC_001 reopen + R8 alignment review (CST-D1 watchpoint already tracks this) |
| **EF-Q3** | Validator slot ordering: EVT-V_entity_affordance before or after EVT-V_lex? Lex enforces world-rule physics; affordance is a structural check. | `_boundaries/03_validator_pipeline_slots.md` alignment; structural-before-semantic convention suggests entity_affordance first |
| **EF-Q4** | Should `EntityLocation::HeldBy.holder` be restricted to `EntityType ∈ {Pc, Npc}` at type level, or runtime-validated? | runtime validation V1 (rejected with `entity.invalid_entity_type`); type-level constraint via enum-of-enums = over-engineering V1 |
