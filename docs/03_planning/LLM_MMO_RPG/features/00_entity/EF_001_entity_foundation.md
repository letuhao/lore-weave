# EF_001 — Entity Foundation

> **Conversational name:** "Entity Foundation" (EF). The substrate that defines what counts as an addressable thing in the world — a unified `EntityId` taxonomy, spatial presence (`entity_binding`), lifecycle state machine, affordance enum, and the `EntityKind` trait that PC / NPC / Item / EnvObject aggregates implement.
>
> **Category:** EF — Entity Foundation (foundation tier; precedes feature folders)
> **Status:** **DRAFT 2026-04-26** (Option C max scope per user direction "object foundation trước PC/NPC/Item")
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
    pub entity_type: EntityType,                // discriminator (matches entity_id variant)
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
- `entity_type` MUST match `entity_id` variant (validated at write-time per DP-A14).
- `location` transitions are atomic: an entity is in EXACTLY one place at a time.
- `lifecycle_state = Destroyed | Removed` → `location` is FROZEN at last value (audit trail); references to this entity from new EVT-T1 Submitted reject per §8.
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
    NpcCold,                                    // NPC_001 R8 cold-decay → Suspended
    AdminDecanonize,                            // WA_002 Heresy admin removal → Removed
    AdminRestore,                               // admin restore Suspended/Destroyed → Existing (audit'd)
    InteractionDestructive,                     // PL_005 Interaction Strike Lethal / Use destructive
    Unknown,                                    // fallback; should be rare
}
```

**Why split from `entity_binding`:** lifecycle log is append-only audit; `entity_binding` is current-state with frequent location updates. Splitting prevents log growth from inflating snapshot size. Mirrors R8 split pattern (NPC core vs npc_session_memory).

---

## §4 EntityKind trait specification

The contract every aggregate-owner feature implements to be addressable as an Entity. EF_001 owns the trait definition; consumer features own the implementations.

```rust
pub trait EntityKind: Aggregate {
    /// Stable Entity identity (matches the variant tag of self).
    fn entity_id(&self) -> EntityId;

    /// Discriminator (matches entity_id variant 1:1).
    fn entity_type(&self) -> EntityType;

    /// Current lifecycle state (sourced from entity_binding row, not the aggregate body itself —
    /// this method delegates to the binding lookup; default impl provided).
    fn lifecycle_state(&self, binding: &EntityBinding) -> LifecycleState {
        binding.lifecycle_state
    }

    /// Affordance set (default declared at TYPE level; per-instance override via
    /// entity_binding.affordance_overrides). Default impl combines:
    fn affordances(&self, binding: &EntityBinding) -> AffordanceSet {
        binding.affordance_overrides.unwrap_or_else(|| Self::type_default_affordances())
    }

    /// Human-readable display name in the requested locale. Used by failure UX,
    /// LLM prompt assembly, narrator text. Locale = "vi" V1; "en" V1+.
    fn display_name(&self, locale: &str) -> String;

    /// Type-level affordance default. PCS_001 / NPC_001 / Item / EnvObject MUST declare.
    /// Required (no default impl) — forces every consumer to think about it.
    fn type_default_affordances() -> AffordanceSet;
}
```

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

| From → To | Trigger | Owner feature | Notes |
|---|---|---|---|
| `Existing` → `Suspended` | NPC scheduler cold-decay; Item dropped + un-loaded | NPC_001 / future Item | Reversible without admin; auto-restore on cell-load |
| `Suspended` → `Existing` | NPC re-loaded on PC arrival; Item picked up | NPC_001 / Item | Auto-restore |
| `Existing` → `Destroyed` | PC mortality (PCS_001) · Item destruction (Strike with sufficient damage) · NPC death | PCS_001 / future Item / NPC_001 | In-fiction; persists in `entity_lifecycle_log` |
| `Suspended` → `Destroyed` | rare: time-decay destruction (rotted food, expired potion) | future Item | Audit'd |
| `Existing` → `Removed` | admin: WA_002 Heresy decanonize · WA_003 Forge admin remove | WA_002 / WA_003 | Out-of-fiction; "this entity never was" semantics |
| `Suspended` → `Removed` | admin removal of suspended entity | WA_002 / WA_003 | Audit'd |
| `Destroyed` → `Existing` | rare: PCS_001 V1+ Respawn · Item resurrection (magic) | PCS_001 / future Item | New `entity_lifecycle_log` event with `reason_kind=AdminRestore` or feature-specific |
| `Removed` → `Existing` | RARE admin: WA_003 admin restore (regret operation) | WA_003 | Double-approval workflow (mirrors R9 9-state lifecycle) |

**Forbidden transitions** (validated at write-time; rejected with `entity.invalid_lifecycle_transition`):
- `Destroyed` → `Suspended` (must restore to `Existing` first)
- `Removed` → `Suspended` (admin restore goes to `Existing`)
- `Removed` → `Destroyed` (a removed-entity has no in-fiction state to destroy)

---

## §7 AffordanceFlag closed enum + enforcement

```rust
pub enum AffordanceFlag {
    BeSpokenTo,    // Speak target — addressee
    BeStruck,      // Strike target
    BeExamined,    // Examine target
    BeGiven,       // Give recipient (active receiver — accepts gifts)
    BeReceived,    // Give → received-by-target (passive — can BE the held item)
    BeUsed,        // Use target — instrument or toolable thing
}

pub type AffordanceSet = bitflags::BitFlags<AffordanceFlag>;
```

**Mapping to PL_005 InteractionKind validators:**

| InteractionKind | Required affordance on | Validator slot |
|---|---|---|
| `Speak` | direct_targets — `BeSpokenTo` | EVT-V_entity_affordance (NEW slot — see §11) |
| `Strike` | direct_targets — `BeStruck`; tool (if present) — `BeUsed` | same |
| `Examine` | direct_targets — `BeExamined` | same |
| `Give` | recipient direct_target — `BeGiven`; tool (the gifted item) — `BeReceived` | same |
| `Use` | tool — `BeUsed`; direct_targets (if any) — `BeUsed` (if tool used ON something) | same |

Validator runs BEFORE PL_005's per-kind validator chain (§11 of this doc explains slot ordering). Failure → reject with `entity.affordance_missing { entity_id, required_flag }` per §8.

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
| `entity.invalid_entity_type` | location_kind requires specific entity_type and target violates (e.g., HeldBy targets EnvObject) | "Cấu trúc vị trí không hợp lệ cho đối tượng đó." | No (write-time validator) |
| `entity.invalid_lifecycle_transition` | aggregate-owner attempts forbidden transition (§6) | "Chuyển đổi trạng thái không hợp lệ." | No (write-time validator) |
| `entity.unknown_entity` | `EntityId` resolves to no `entity_binding` row | "Không tìm thấy đối tượng." | No (always reject; helps debug) |

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

10 V1-testable scenarios (AC-EF-1..10):

1. **AC-EF-1 — EntityId variant exhaustiveness:** Rust compile fails if a match on `EntityId` omits any of `Pc/Npc/Item/EnvObject` variants without `_` arm. CI grep for unsafe match patterns.
2. **AC-EF-2 — entity_binding primary-key unique:** attempting to write two rows for same `entity_id` returns invariant violation `entity.duplicate_binding`.
3. **AC-EF-3 — entity_type matches variant:** writing `entity_binding { entity_id: Pc(...), entity_type: Npc, ... }` rejects `entity.entity_type_mismatch`.
4. **AC-EF-4 — Lifecycle forbidden transitions reject:** attempting `Removed → Suspended` rejects `entity.invalid_lifecycle_transition`.
5. **AC-EF-5 — Affordance hard-reject:** Speak target an Item (no `be_spoken_to`) rejects `entity.affordance_missing { required: BeSpokenTo }`.
6. **AC-EF-6 — Affordance soft-override Examine on Destroyed:** Examine of Destroyed entity returns success with narrator text "[còn lại tàn tích]" (or similar), NOT `entity.entity_destroyed` reject.
7. **AC-EF-7 — Reference to Removed always rejects:** any InteractionKind targeting `Removed` entity rejects `entity.entity_removed` (no soft-override, even Examine).
8. **AC-EF-8 — Suspended NPC re-load on cell entry:** Suspended NPC at cell, PC enters cell → NPC transitions Suspended → Existing within same turn-tick; NPC appears in participant_presence.
9. **AC-EF-9 — entity_lifecycle_log append-only:** attempting to mutate a previously-appended event in lifecycle_log fails `entity.lifecycle_log_immutable`.
10. **AC-EF-10 — Cross-entity Give updates location atomically:** PC Gives Item to NPC → entity_binding row for Item flips from `HeldBy(Pc)` → `HeldBy(Npc)` atomically with the EVT-T1 Submitted commit; no intermediate state observable.

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

---

## §16 Cross-references

- **PL_001 Continuum** §3.6 — `actor_binding` transferred to EF_001 as `entity_binding` (renamed + scope-grown 2026-04-26). PL_001 reopen: §3.6 now references EF_001 as owner; PL_001's role is referencer.
- **PL_005 Interaction** §3.X — 5 V1 InteractionKinds reference `EntityId` (replacing `ActorId | ItemRef`) for tool / direct_targets / indirect_targets. Affordance validation runs at EF_001 EVT-V_entity_affordance slot before per-kind validator chain.
- **PL_005c Interaction integration** §V1-scope — Item "refs only V1" gap CLOSED by EF_001 owning ItemId variant + `entity_binding` row for Items. Future Item feature owns Item body; PL_005 V1 implementable against EF_001 contract.
- **PL_006 Status Effects** — `actor_status` row keyed by ActorId, not EntityId — V1 OK (status applies only to PC+NPC, not Items/EnvObjects). V1+ if Item buffs/debuffs designed: extend PL_006 keying to EntityId.
- **NPC_001 Cast** — implements `EntityKind for Npc`. ActorId enum (NPC_001 §2) becomes a sub-set of EntityId (Pc + Npc only) for actor-only contexts (turn submission); cross-entity references use EntityId.
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
- [x] Aggregate inventory: 2 aggregates (`entity_binding` primary + `entity_lifecycle_log` audit-only)
- [x] EntityKind trait specified with 5 methods + per-type default-affordance matrix
- [x] LifecycleState 4-state machine with allowed/forbidden transitions
- [x] AffordanceFlag 6 V1 flags + V1+ reservations + per-kind enforcement mapping
- [x] Reference safety policy: hard-reject + per-kind soft-override; 7 rule_ids in `entity.*` namespace
- [x] Event-model mapping: EVT-T3 Derived + EVT-T4 System + EVT-T6 Proposal (V1+); no new EVT-T*
- [x] DP primitives: existing surface only (no new DP-K*)
- [x] Capability JWT: existing claims (no new top-level)
- [x] Subscribe pattern: 4 subscribers V1 (Frontend / NPC_002 / PL_005c / WA_002)
- [x] Cross-service handoff: EntityId JSON shape + CausalityToken chain
- [x] 5 representative sequences
- [x] 10 V1-testable acceptance scenarios (AC-EF-1..10)
- [x] 9 deferrals (EF-D1..D9) with target phases
- [x] Cross-references to all 11 affected features + foundation docs
- [ ] CANDIDATE-LOCK — pending closure pass + downstream rename verification + PCS_001 brief update

---

## §18 Open questions (post-DRAFT)

| ID | Question | Resolution path |
|---|---|---|
| **EF-Q1** | Should `entity_lifecycle_log` be a separate aggregate or a column on `entity_binding`? Trade-off: separate = clean append-only + bounded snapshot; column = simpler reads. | Boundary review V1+ if profiling shows pain; current split mirrors R8 precedent |
| **EF-Q2** | Does NPC_001 keep its `npc.current_region_id` field after EF_001 lands, or migrate fully to entity_binding? | NPC_001 reopen + R8 alignment review (CST-D1 watchpoint already tracks this) |
| **EF-Q3** | Validator slot ordering: EVT-V_entity_affordance before or after EVT-V_lex? Lex enforces world-rule physics; affordance is a structural check. | `_boundaries/03_validator_pipeline_slots.md` alignment; structural-before-semantic convention suggests entity_affordance first |
| **EF-Q4** | Should `EntityLocation::HeldBy.holder` be restricted to `EntityType ∈ {Pc, Npc}` at type level, or runtime-validated? | runtime validation V1 (rejected with `entity.invalid_entity_type`); type-level constraint via enum-of-enums = over-engineering V1 |
