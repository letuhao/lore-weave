# FF_001 — Family Foundation

> **Conversational name:** "Family" (FF). Tier 5 Actor Substrate Foundation feature owning per-actor `family_node` aggregate (parent / sibling / spouse / child relations with adoption flag) + per-dynasty `dynasty` aggregate (sparse storage; only declared dynasties). Resolves IDF_004 lineage_id opaque tag per ORG-D12 + POST-SURVEY-Q4. Wuxia critical (sect lineage / family inheritance / dynasty politics). Boundary discipline: FF_001 = biological + adoption only; V1+ FAC_001 owns sect/master-disciple/sworn relationships (per Q4 LOCKED).
>
> **Category:** FF — Family Foundation (Tier 5 Actor Substrate)
> **Status:** DRAFT 2026-04-26 (Phase 0 CONCEPT promoted to DRAFT after Q1-Q8 LOCKED via deep-dive 2026-04-26 user "A" confirmation)
> **Stable IDs in this file:** `FF-A*` axioms · `FF-D*` deferrals · `FF-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) (sibling pattern); [IDF_004 Origin Foundation](../00_identity/IDF_004_origin.md) (lineage_id ref resolution per ORG-D12); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md) (display_name); [WA_006 Mortality](../02_world_authoring/WA_006_mortality.md) (death events propagate to family_node); [07_event_model EVT-A10](../../07_event_model/02_invariants.md) (event log = universal SSOT — no separate family_event_log aggregate per Q5 LOCKED).
> **Defers to:** future PCS_001 (PC creation form selects family / generates orphan); future `NPC_NNN` mortality (NPC death cascades update family_node); V1+ FAC_001 Faction Foundation (sect / master-disciple / sworn brotherhood — NOT FF_001 per Q4 LOCKED); V1+ TIT_001 Title Foundation (heir succession consumes FF_001 graph); V1+ NPC_002 enrichment (family-cascade opinion drift on death); V1+ RAC-D3 + V1+ CULT_001 (bloodline trait inheritance per Q8 LOCKED); V2+ WA_002 Heresy (cross-reality migration per Q7 LOCKED).
> **Event-model alignment:** Family events = EVT-T3 Derived (`aggregate_type=family_node` with delta_kinds AddSpouse / MarkDeceased / AddChild / RemoveSpouse / AddAdoptedParent) + EVT-T4 System sub-type `FamilyBorn` at canonical seed + EVT-T8 Administrative `Forge:EditFamily` + `Forge:RegisterDynasty`. No new EVT-T* category. **No separate `family_event_log` aggregate per Q5 LOCKED — channel event stream IS the audit log per EVT-A10.**

---

## §1 User story (Wuxia + Modern presets)

### V1 Wuxia preset (SPIKE_01 reality)

**Lý clan dynasty (1 dynasty V1; sparse storage):**

```
DynastyDecl {
    dynasty_id: DynastyId("dynasty_ly_yen_vu_lau"),
    display_name: I18nBundle{ default: "Lý Clan", "vi": "Dòng họ Lý", "zh": "李氏" },
    founder_actor_id: None (founder predates reality),
    canon_ref: None,
}
```

**Canonical actors V1 (4 actors with family relations):**

1. **Lý Minh** (PC) — orphan; parent_actor_ids=[] (deceased ancestors not declared as living actors); dynasty_id=Some("dynasty_ly_yen_vu_lau"); is_deceased=false. V1 family_node: 1-node graph (LM01 alone with dynasty membership).

2. **Tiểu Thúy** (NPC, innkeeper daughter) — parent_actor_ids=[(lao_ngu, BiologicalParent)]; sibling_actor_ids=[]; spouse_actor_ids=[]; children_actor_ids=[]; dynasty_id=None (commoner); is_deceased=false.

3. **Lão Ngũ** (NPC, innkeeper) — parent_actor_ids=[]; sibling_actor_ids=[]; spouse_actor_ids=[] (wife deceased pre-reality; not declared as living actor); children_actor_ids=[(tieu_thuy, BiologicalChild)]; dynasty_id=None; is_deceased=false.

4. **Du sĩ** (NPC, wandering scholar) — parent_actor_ids=[]; sibling_actor_ids=[]; spouse_actor_ids=[]; children_actor_ids=[]; dynasty_id=None; is_deceased=false. (Cosmopolitan; family elsewhere.)

**Bidirectional sync verification at canonical seed:**
- Lão Ngũ.children_actor_ids=[(tieu_thuy, BiologicalChild)] ✓
- Tiểu Thúy.parent_actor_ids=[(lao_ngu, BiologicalParent)] ✓
- Both sides consistent → canonical seed validates

### V1 Modern preset (Saigon detective)

PC (detective) — single child, parents alive in different city:
- parent_actor_ids=[(father_actor_id, BiologicalParent), (mother_actor_id, BiologicalParent)]; sibling_actor_ids=[]; spouse_actor_ids=[]; children_actor_ids=[]; dynasty_id=None.
- Father + mother family_node rows with children_actor_ids=[(pc_id, BiologicalChild)].

### V1+ deferred (per FF-D2..D12)

- Cousins / uncles / aunts / in-laws / grandparents — V1+ traversal API
- Cadet dynasty branches — V1+ parent_dynasty_id
- Marriage as faction alliance — V1+ FAC_001 + DIPL_001
- Sworn brotherhood — V1+ FAC_001 (NOT FF_001)
- Master-disciple sect lineage — V1+ FAC_001 (NOT FF_001)
- Title inheritance — V1+ TIT_001
- Family-cascade opinion drift on death — V1+ NPC_002 enrichment
- Bloodline trait inheritance — V1+ RAC-D3 + CULT_001 read FF_001 graph
- V1+ runtime birth/divorce/adoption — V1 ships canonical seed only

**This feature design specifies:** `family_node` aggregate per-(reality, actor_id) with direct relations + dynasty membership; `dynasty` aggregate per-(reality, dynasty_id) sparse storage; 6-variant RelationKind closed enum for adoption flag; 5 family event variants (1 EVT-T4 + 4 EVT-T3); RealityManifest `canonical_dynasties` + `canonical_family_relations` REQUIRED V1; `family.*` namespace 8 V1 rules; bidirectional sync validation at canonical seed.

After this lock: every PC and NPC has deterministic family graph entry (possibly empty); IDF_004 lineage_id opaque tag resolves via FF_001 family_node + dynasty queries; V1+ TIT_001 + V1+ NPC_002 + V1+ RAC-D3 + V1+ CULT_001 read FF_001 graph for downstream features.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **DynastyId** | `pub struct DynastyId(pub String);` typed newtype (e.g., `DynastyId("dynasty_ly_yen_vu_lau".to_string())`) | Opaque per-reality. Sparse storage (only declared dynasties get rows). Pattern matches RaceId / LanguageId / IdeologyId / OriginPackId from IDF folder. |
| **DynastyDecl** | Author-declared per-reality entry (in RealityManifest.canonical_dynasties) | display_name (I18nBundle) + founder_actor_id (Option) + canon_ref (Option<GlossaryEntityId>). |
| **family_node** | T2 / Reality aggregate; per-(reality, actor_id) row | Per-actor family relations + dynasty membership. ActorId source = EF_001 §5.1. **Mutable** via Apply events per Q5 LOCKED. Synthetic actors forbidden V1 (matches IDF discipline). |
| **dynasty** | T2 / Reality aggregate; per-(reality, dynasty_id) sparse row | Per-dynasty metadata + current head ref. Only declared dynasties have rows (sparse). **Mutable** via succession events V1+. |
| **RelationKind** | Closed enum 6-variant: `BiologicalParent / AdoptedParent / Spouse / BiologicalChild / AdoptedChild / Sibling` | V1 closed set per Q6 LOCKED. Symmetric on parent/child sides. Wuxia adoption (clan adopts orphan as heir) flagged distinctly from biological. |
| **FamilyRelationDecl** | Author-declared per-reality entry (in RealityManifest.canonical_family_relations) | Per-actor family relations at canonical seed. Bidirectional sync validated. |

**Cross-feature consumers:**
- IDF_004 Origin lineage_id → resolves via FF_001 family_node.dynasty_id + ancestor traversal V1+ (per ORG-D12 LOCKED)
- WA_006 Mortality death events → emit EVT-T3 MarkDeceased on family_node (V1)
- V1+ NPC_002 enrichment → cascade opinion drift via family_node.children_actor_ids traversal on death
- V1+ TIT_001 Title Foundation → reads dynasty.current_head_actor_id for heir succession
- V1+ RAC-D3 hybrid races → reads parent_actor_ids → race_assignment for parent races
- V1+ CULT_001 cultivation → reads parent_actor_ids → spirit root inheritance
- Future PCS_001 PC creation form → select family / generate orphan / tie to canonical dynasty

---

## §2.5 Event-model mapping (per [`07_event_model`](../../07_event_model/) EVT-T1..T11)

FF_001 emits / consumes events that all map to existing active EVT-T* categories — no new category needed. Per Q5 LOCKED + EVT-A10: channel event stream IS the audit log; no separate `family_event_log` aggregate.

| FF_001 path | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| Family birth at canonical seed | **EVT-T4 System** | `FamilyBorn { actor_id, parent_refs, dynasty_id }` | Bootstrap (RealityBootstrapper) | ✓ V1 |
| Marriage event | **EVT-T3 Derived** | `aggregate_type=family_node`, `delta_kind=AddSpouse` | Aggregate-Owner (FF_001 owner-service in world-service) | ✓ V1 |
| Death event (consumed from WA_006 mortality) | **EVT-T3 Derived** | `delta_kind=MarkDeceased` | Aggregate-Owner | ✓ V1 |
| V1+ runtime birth (PC has child) | **EVT-T3 Derived** | `delta_kind=AddChild` | Aggregate-Owner | V1+ |
| Divorce event | **EVT-T3 Derived** | `delta_kind=RemoveSpouse` | Aggregate-Owner | V1+ |
| Adoption event runtime | **EVT-T3 Derived** | `delta_kind=AddAdoptedParent` | Aggregate-Owner | V1+ |
| Forge admin override family | **EVT-T8 Administrative** | `Forge:EditFamily { actor_id, edit_kind, before, after, reason }` | Forge (WA_003) | ✓ V1 |
| Forge dynasty register | **EVT-T8 Administrative** | `Forge:RegisterDynasty { dynasty_id, display_name, founder, reason }` | Forge (WA_003) | ✓ V1 |

**Closed-set proof for FF_001:** every family-related path produces an active EVT-T* (T3 / T4 / T8). No new EVT-T* row.

---

## §3 Aggregate inventory

**2 aggregates V1** (revised down from 3 per Q5 EVT-A10 alignment).

### 3.1 `family_node` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "family_node", tier = "T2", scope = "reality")]
pub struct FamilyNode {
    pub reality_id: RealityId,
    pub actor_id: ActorId,                                    // EF_001 §5.1 source

    // Direct relations (V1; explicit per Q2 LOCKED)
    pub parent_actor_ids: Vec<(ActorId, RelationKind)>,        // V1 RelationKind: BiologicalParent | AdoptedParent
    pub sibling_actor_ids: Vec<ActorId>,                       // V1 RelationKind=Sibling implicit; explicit refs
    pub spouse_actor_ids: Vec<ActorId>,                        // V1 RelationKind=Spouse implicit; 0-1 V1 (V1+ polygamy)
    pub children_actor_ids: Vec<(ActorId, RelationKind)>,      // V1 RelationKind: BiologicalChild | AdoptedChild

    // Dynasty membership (V1 per Q3 LOCKED)
    pub dynasty_id: Option<DynastyId>,                          // None for non-dynasty actors (most actors V1)

    // Lifecycle (V1 per Q5 LOCKED)
    pub is_deceased: bool,
    pub deceased_at_turn: Option<u64>,
    pub deceased_at_fiction_ts: Option<i64>,

    pub last_modified_at_turn: u64,
    pub schema_version: u32,
}

pub enum RelationKind {
    BiologicalParent,
    AdoptedParent,
    Spouse,
    BiologicalChild,
    AdoptedChild,
    Sibling,
}
```

- T2 + RealityScoped: per-actor across reality lifetime
- One row per `(reality_id, actor_id)` (every PC + NPC MUST have row except Synthetic forbidden V1)
- **MUTABLE V1** via Apply events per Q5 LOCKED (Marriage / Death / Adoption update aggregate)
- Synthetic actors (ChorusOrchestrator / BubbleUpAggregator) don't get rows V1 (matches IDF discipline)
- Bidirectional sync validated at canonical seed + Forge admin events

### 3.2 `dynasty` (T2 / Reality scope — sparse)

```rust
#[derive(Aggregate)]
#[dp(type_name = "dynasty", tier = "T2", scope = "reality")]
pub struct Dynasty {
    pub reality_id: RealityId,
    pub dynasty_id: DynastyId,
    pub display_name: I18nBundle,                              // RES_001 §2.3
    pub founder_actor_id: Option<ActorId>,                      // None if founder predates reality
    pub current_head_actor_id: Option<ActorId>,                 // None if dynasty extinct V1+
    pub member_count: u32,                                      // sparse query helper; computed from family_node count
    pub canon_ref: Option<GlossaryEntityId>,
    // V1+ extensions (additive per I14)
    // pub parent_dynasty_id: Option<DynastyId>,               // cadet branch
    // pub traditions: Vec<TraditionId>,                       // V1+ V2+ enrichment
    // pub perks: Vec<PerkId>,                                  // V1+ V2+ enrichment
    pub schema_version: u32,
}
```

- T2 + RealityScoped: sparse storage (only declared dynasties get rows)
- One row per `(reality_id, dynasty_id)` — typically 0-3 dynasties per reality V1
- **Mutable** via succession events V1+ (current_head_actor_id updates on heir succession)
- V1 minimal fields; V1+ additive enrichment

---

## §4 Tier+scope (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `family_node` | T2 | T2 | Reality | ~0.5-1 per turn (UI tooltip + V1+ NPC_002 cascade traversal + V1+ TIT_001 heir lookup) | ~0.001 per turn V1 (canonical seed only); V1+ rare (Marriage/Death/Adoption events) | Per-actor; mutable but rare; eventual consistency OK |
| `dynasty` | T2 | T2 | Reality | ~0.1 per turn (UI badge + V1+ TIT_001 heir reads) | ~0 per turn V1 (canonical seed only); V1+ rare (head succession) | Per-dynasty sparse; mutable but very rare |

---

## §5 DP primitives this feature calls

By name. No raw `sqlx` / `redis` (DP-R3).

### 5.1 Reads

- `dp::read_projection_reality::<FamilyNode>(ctx, actor_id)` — UI tooltip + V1+ traversal + V1+ TIT_001 heir lookup
- `dp::read_projection_reality::<Dynasty>(ctx, dynasty_id)` — dynasty metadata + current_head ref
- `dp::query_scoped_reality::<FamilyNode>(ctx, predicate=field_eq(dynasty_id, X))` — operator queries ("all members of House Lý")
- `dp::read_reality_manifest(ctx).canonical_dynasties` + `.canonical_family_relations` — RealityManifest extensions

### 5.2 Writes

- `dp::t2_write::<FamilyNode>(ctx, actor_id, ApplyFamilyDelta { delta_kind, ... })` — Apply events (Marriage / MarkDeceased / Adoption)
- `dp::t2_write::<Dynasty>(ctx, dynasty_id, ApplyDynastyDelta { delta_kind, ... })` — V1+ succession events
- `dp::t2_write::<FamilyNode>(ctx, actor_id, AdminOverrideDelta { ... })` — Forge admin (Forge:EditFamily)
- `dp::t2_write::<Dynasty>(ctx, dynasty_id, AdminRegisterDelta { ... })` — Forge admin (Forge:RegisterDynasty)

### 5.3 Subscriptions

- UI subscribes to `family_node` invalidations via DP-X cache invalidation broadcast → re-renders family tooltip
- V1+ NPC_002 reads at SceneRoster build time (cached per batch)
- V1+ TIT_001 reads dynasty at heir-selection event time

### 5.4 Capability + lifecycle

- `produce: [Derived]` + `write: { aggregate_type: family_node, tier: T2, scope: reality }` — for FF_001 owner-service (world-service in V1)
- `produce: [Derived]` + `write: dynasty @ T2 @ reality` — same owner
- `produce: [System]` + sub-type `FamilyBorn` — for RealityBootstrapper at canonical seed
- `produce: [Administrative]` + sub-shapes `Forge:EditFamily` / `Forge:RegisterDynasty` — for Forge admin (WA_003)

---

## §6 Capability requirements (JWT claims)

Inherits PL_001 + EF_001 + IDF patterns. No new claim category.

| Claim | Granted to | Why |
|---|---|---|
| `produce: [Derived]` + `write: family_node @ T2 @ reality` | world-service backend (FF_001 owner role) | apply events at canonical seed / runtime Marriage/Death/Adoption |
| `produce: [Derived]` + `write: dynasty @ T2 @ reality` | world-service backend (FF_001 owner role) | dynasty metadata + V1+ succession |
| `produce: [System]` + sub-type `FamilyBorn` | RealityBootstrapper service | canonical seed at world-build |
| `produce: [Administrative]` + sub-shape `Forge:EditFamily` / `Forge:RegisterDynasty` | Forge admin (WA_003) | admin override audit |
| `read: family_node @ T2 @ reality` | every PC session + NPC_002 orchestrator + V1+ TIT_001 + V1+ RAC-D3 + V1+ CULT_001 consumers | UI display + V1+ cross-feature traversals |
| `read: dynasty @ T2 @ reality` | UI session + V1+ TIT_001 | UI badge + heir lookup |

---

## §7 Subscribe pattern

UI receives `family_node` updates via DP-X cache invalidation (DP-A4 pub/sub) → re-renders family tooltip + dynasty badge. No durable channel-event subscription needed (events propagated through normal channel event stream — UI multiplex stream catches them).

WA_006 mortality consumer reads family_node when actor dies → emits MarkDeceased event for FF_001 (one-way: WA_006 emits death; FF_001 owner-service consumes + updates family_node).

V1+ NPC_002 reads at SceneRoster build time (cached for batch duration).

---

## §8 Pattern choices

### 8.1 Separate family_node aggregate (Q1 LOCKED)
T2/Reality, per-(reality, actor_id). Lifecycle differs from IDF_004 actor_origin (mutable vs immutable); access patterns differ; schema growth orthogonal. Matches IDF Origin/Ideology split discipline.

### 8.2 Explicit direct relations V1 (Q2 LOCKED)
parent + sibling + spouse + child stored explicitly with bidirectional sync. Extended (cousins/uncles/etc.) computed V1+ via traversal API. Matches CK3 + Bannerlord + DF.

### 8.3 Separate dynasty aggregate sparse storage (Q3 LOCKED)
Per-(reality, dynasty_id); only declared dynasties get rows. Supports cross-actor query + V1+ TIT_001 heir succession. Minimal V1 schema.

### 8.4 V1+ FAC_001 owns sect lineage (Q4 LOCKED)
FF_001 V1 = biological + adoption only. Master-disciple sect lineage lives in V1+ FAC_001 (rank/role within sect). Wuxia narrative quasi-family treated mechanically as sect membership.

### 8.5 Materialized only; events in channel stream per EVT-A10 (Q5 LOCKED)
NO separate `family_event_log` aggregate. Channel event stream IS the audit log. Matches PL_006 + IDF_005 pattern.

### 8.6 Adoption flag via RelationKind enum (Q6 LOCKED)
6-variant closed enum: BiologicalParent / AdoptedParent / Spouse / BiologicalChild / AdoptedChild / Sibling. Symmetric on parent/child. Future-proofs adoption distinction.

### 8.7 V1 strict single-reality (Q7 LOCKED)
Cross-reality migration V2+ Heresy. Matches IDF discipline.

### 8.8 V1+ deferred bloodline traits (Q8 LOCKED)
FF_001 V1 = pure graph. V1+ RAC-D3 + V1+ CULT_001 consume FF_001 graph for trait inheritance.

### 8.9 RealityManifest extensions REQUIRED V1
`canonical_dynasties: Vec<DynastyDecl>` + `canonical_family_relations: Vec<FamilyRelationDecl>` — sparse storage allowed (empty Vec valid for sandbox / family-less reality).

### 8.10 Synthetic actor forbidden V1
No family_node row for Synthetic actors (matches IDF_001/003/004/005 + RAC-Q1 / PRS-Q11 / ORG-Q7 / IDL-Q12).

### 8.11 Bidirectional sync validated at canonical seed
Author declares parent → engine derives children (or vice versa); validation rejects mismatch with `family.bidirectional_sync_violation` reject.

---

## §9 Failure-mode UX

Reject paths split by validator stage owner per [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md).

| Reject reason | Stage | When | Vietnamese reject copy (I18nBundle) |
|---|---|---|---|
| `family.unknown_actor_ref` | 0 schema | parent/sibling/spouse/child ref not in EF_001 entity_binding | "Tham chiếu thành viên gia đình không tồn tại." |
| `family.unknown_dynasty_id` | 0 schema | dynasty_id not in RealityManifest.canonical_dynasties + dynasty aggregate | "Dòng họ không tồn tại trong thế giới này." |
| `family.bidirectional_sync_violation` | 0 schema | Asymmetric refs (LM01 says X is parent but X doesn't list LM01 as child) | "Quan hệ gia đình không nhất quán." |
| `family.cyclic_relation` | 0 schema | LM01 is parent of X is parent of LM01 — cycle | "Quan hệ gia đình không thể tạo vòng lặp." |
| `family.duplicate_relation` | 0 schema | Same actor twice in parent_actor_ids | "Trùng lặp quan hệ gia đình." |
| `family.relation_kind_mismatch` | 0 schema | parent_actor_ids has BiologicalChild variant — wrong side | (Schema check; not user-facing) |
| `family.deceased_target` | 7 world-rule | Marriage / Adoption event with deceased target | "Không thể kết hôn / nhận con nuôi với người đã khuất." |
| `family.synthetic_actor_forbidden` | 0 schema | Synthetic actor cannot have family_node | (Schema check; not user-facing) |

**`family.*` V1 rule_id enumeration** (8 V1 rules):

1. `family.unknown_actor_ref` — Stage 0
2. `family.unknown_dynasty_id` — Stage 0
3. `family.bidirectional_sync_violation` — Stage 0
4. `family.cyclic_relation` — Stage 0
5. `family.duplicate_relation` — Stage 0
6. `family.relation_kind_mismatch` — Stage 0
7. `family.deceased_target` — Stage 7
8. `family.synthetic_actor_forbidden` — Stage 0

**V1+ reservations:**
- `family.cross_reality_mismatch` (V2+ Heresy migration per Q7)
- `family.cyclic_lineage_traversal` (V1+ when extended traversal API ships)
- `family.dynasty_extinction` (V1+ when no living members; cleanup rule)
- `family.adoption_consent_violation` (V1+ V2+ if consent system ships)

V1 user-facing rejects: `family.deceased_target` (Marriage/Adoption attempts on deceased) only. Schema-level rejects unreachable in normal operation (canonical seed validates pre-bootstrap).

---

## §10 Cross-service handoff (canonical seed flow)

Concrete example: Wuxia reality bootstrap with Lý dynasty + 4 canonical actors (Lý Minh + Tiểu Thúy + Du sĩ + Lão Ngũ).

```
1. RealityBootstrapper service (Bootstrap role):
   a. Read RealityManifest.canonical_dynasties:
      [DynastyDecl { dynasty_id: "dynasty_ly_yen_vu_lau", display_name, founder_actor_id: None }]
      → for each: dp::t2_write::<Dynasty>(ctx, dynasty_id, RegisterDynastyDelta { ... }) → T0 Derived
   b. Read RealityManifest.canonical_family_relations:
      [FamilyRelationDecl { actor_id: lao_ngu, children_actor_ids: [(tieu_thuy, BiologicalChild)], ... },
       FamilyRelationDecl { actor_id: tieu_thuy, parent_actor_ids: [(lao_ngu, BiologicalParent)], ... },
       FamilyRelationDecl { actor_id: ly_minh, dynasty_id: Some("dynasty_ly_yen_vu_lau"), ... },
       FamilyRelationDecl { actor_id: du_si, ... }]
   c. Validate bidirectional sync (Stage 0 schema):
      - lao_ngu.children includes tieu_thuy ✓ AND tieu_thuy.parents includes lao_ngu ✓ → consistent
      - All actor_ids exist in EF_001 entity_binding ✓
      - dynasty_id in canonical_dynasties ✓
      - No cycles ✓
   d. For each actor:
      Emit EVT-T4 System: FamilyBorn { actor_id, parent_refs, dynasty_id }
      dp::t2_write::<FamilyNode>(ctx, actor_id, ApplyFamilyDelta {
        ...full FamilyRelationDecl content...
      }) → T1 Derived
      causal_refs = [reality_bootstrap_event_id]
   e. Update dynasty.member_count + current_head_actor_id (Lý Minh as sole living member of Lý clan)

Result: 4 family_node rows committed; 1 dynasty row committed; FamilyBorn events emitted.

2. WA_006 death event flow (V1+ runtime):
   When actor dies via WA_006 mortality:
   a. WA_006 emits death event
   b. FF_001 owner-service consumes:
      dp::t2_write::<FamilyNode>(ctx, actor_id, ApplyFamilyDelta {
        delta_kind: MarkDeceased { died_at_turn, died_at_fiction_ts }
      }) → T_n Derived
   c. family_node.is_deceased = true; refs preserved; deceased_at_turn updated
   d. V1+ NPC_002 reads family_node.children_actor_ids → cascade opinion drift on relatives

3. PC creation flow (V1+ when PCS_001 ships):
   PC selects family from existing or generates orphan:
   a. PC creation form reads RealityManifest.canonical_family_relations to display options
   b. PC commits creation → emits ApplyFamilyDelta for new actor + bidirectional sync update on selected parents
```

**Token chain:** RegisterDynasty (T0 Derived) → FamilyBorn (T1 System) → ApplyFamily (T1 Derived). Multi-actor canonical seed sequential per DP-A19.

---

## §11 Sequence: Canonical seed (Wuxia Lý dynasty + 4 actors)

```
RealityBootstrapper service @ reality-bootstrap event for Wuxia reality:

  Read RealityManifest:
    canonical_dynasties: [
      DynastyDecl { dynasty_id: "dynasty_ly_yen_vu_lau", display_name: "Lý Clan" / "vi": "Dòng họ Lý" / "zh": "李氏", founder_actor_id: None, canon_ref: None }
    ]
    canonical_family_relations: [
      FamilyRelationDecl { actor_id: ly_minh, parent_actor_ids: [], sibling_actor_ids: [], spouse_actor_ids: [], children_actor_ids: [], dynasty_id: Some("dynasty_ly_yen_vu_lau"), is_deceased: false },
      FamilyRelationDecl { actor_id: tieu_thuy, parent_actor_ids: [(lao_ngu, BiologicalParent)], sibling_actor_ids: [], spouse_actor_ids: [], children_actor_ids: [], dynasty_id: None, is_deceased: false },
      FamilyRelationDecl { actor_id: lao_ngu, parent_actor_ids: [], sibling_actor_ids: [], spouse_actor_ids: [], children_actor_ids: [(tieu_thuy, BiologicalChild)], dynasty_id: None, is_deceased: false },
      FamilyRelationDecl { actor_id: du_si, parent_actor_ids: [], sibling_actor_ids: [], spouse_actor_ids: [], children_actor_ids: [], dynasty_id: None, is_deceased: false },
    ]
  Validate (Stage 0 schema):
    - All actor_ids exist in EF_001 entity_binding ✓
    - dynasty_id "dynasty_ly_yen_vu_lau" exists in canonical_dynasties ✓
    - Bidirectional sync: lao_ngu.children includes tieu_thuy AND tieu_thuy.parents includes lao_ngu ✓
    - No cycles ✓
    - No duplicate relations ✓
    - RelationKind variants on correct side (BiologicalParent on parent_actor_ids; BiologicalChild on children_actor_ids) ✓
  ✓ schema OK

  Register dynasty:
    dp::t2_write::<Dynasty>(ctx, "dynasty_ly_yen_vu_lau", RegisterDynastyDelta {
      display_name: I18nBundle{...},
      founder_actor_id: None,
      current_head_actor_id: Some(ly_minh),  // Lý Minh sole living member
      member_count: 1,
      canon_ref: None,
    }) → T0 Derived

  For each canonical actor (e.g., Lý Minh):
    Emit EVT-T4 System: FamilyBorn { actor_id: ly_minh, parent_refs: [], dynasty_id: Some("dynasty_ly_yen_vu_lau") }
    dp::t2_write::<FamilyNode>(ctx, ly_minh, ApplyFamilyDelta {
      parent_actor_ids: [],
      sibling_actor_ids: [],
      spouse_actor_ids: [],
      children_actor_ids: [],
      dynasty_id: Some("dynasty_ly_yen_vu_lau"),
      is_deceased: false,
      reason: AssignmentReason::CanonicalSeed,
    }) → T1 Derived
    causal_refs = [reality_bootstrap_event_id]

  Repeat for Tiểu Thúy / Lão Ngũ / Du sĩ.

UI receives FamilyBorn + RegisterDynasty + ApplyFamily events → renders family tooltip per actor + dynasty badge for Lý Minh.
```

---

## §12 Sequence: Marriage event (V1+ runtime)

```
PC LM01 marries NPC ABC (V1+ when PCS_001 marriage flow ships):

world-service:
  a. claim_turn_slot
  b. validator stages 0-9 ✓
     Stage 0 schema: ABC exists in EF_001 entity_binding ✓; ABC.is_deceased=false ✓
     Stage 7 world-rule: Marriage event derivation
       ActualOutputs:
         OutputDecl { target: Actor(LM01), aggregate: family_node,
                      delta: AddSpouse { spouse_actor_id: ABC } }
         OutputDecl { target: Actor(ABC), aggregate: family_node,
                      delta: AddSpouse { spouse_actor_id: LM01 } }  // bidirectional sync
  c. dp.advance_turn → Submitted T1 (Marriage event)
  d. FF_001 owner-service emits 2 EVT-T3 Derived:
     dp.t2_write::<FamilyNode>(ctx, LM01, ApplyFamilyDelta { delta_kind: AddSpouse(ABC) }) → T2
     dp.t2_write::<FamilyNode>(ctx, ABC, ApplyFamilyDelta { delta_kind: AddSpouse(LM01) }) → T3
     causal_refs = [T1]
  e. release_turn_slot

UI re-renders both family tooltips with spouse refs.
```

---

## §13 Sequence: Death event (consumed from WA_006 mortality)

```
NPC tieu_thuy dies via WA_006 mortality (V1+ Strike Lethal scenario):

WA_006 emits death event → T1 Derived (mortality_state transition)

FF_001 owner-service consumes:
  dp.t2_write::<FamilyNode>(ctx, tieu_thuy, ApplyFamilyDelta {
    delta_kind: MarkDeceased {
      died_at_turn: <current>,
      died_at_fiction_ts: <current>,
    }
  }) → T2 Derived
  causal_refs = [T1]

family_node.is_deceased = true; refs preserved (lao_ngu still has tieu_thuy in children_actor_ids — historical).

V1+ NPC_002 cascade (when enrichment ships):
  Read tieu_thuy.children_actor_ids = []  (Tiểu Thúy has no children)
  Read tieu_thuy parent_actor_ids = [(lao_ngu, BiologicalParent)]
  → Lão Ngũ gets opinion drift -10 toward killer (V1+ NPC_002 family-cascade enrichment)

UI re-renders Lão Ngũ family tooltip with deceased child marker.
```

---

## §14 Sequence: Forge admin override

```
Admin reveals Lý Minh's secret biological parent (story-event):
  EVT-T8 Administrative: Forge:EditFamily {
    actor_id: ly_minh,
    edit_kind: AddParent { parent_actor_id: secret_father, relation_kind: BiologicalParent },
    before: parent_actor_ids: [],
    after: parent_actor_ids: [(secret_father, BiologicalParent)],
    reason: "Story-event reveals secret parentage"
  }

3-write atomic transaction:
  - family_node row updated (LM01.parent_actor_ids)
  - family_node row updated (secret_father.children_actor_ids — bidirectional sync)
  - forge_audit_log entry
```

---

## §15 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service can pass these scenarios.

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-FF-1** | Wuxia canonical bootstrap declares 1 dynasty (Lý clan) + 1 actor (Lý Minh) with parent_actor_ids=[] (orphan) | dynasty row + family_node row committed; dynasty.member_count=1; LM01.dynasty_id=Some("dynasty_ly_yen_vu_lau") |
| **AC-FF-2** | Wuxia canonical bootstrap declares Lão Ngũ (parent of Tiểu Thúy); FF_001 derives bidirectional refs | Both family_node rows committed; lao_ngu.children includes tieu_thuy AND tieu_thuy.parents includes lao_ngu |
| **AC-FF-7** | Modern reality canonical bootstrap with 1 PC + 2 parents alive + 0 dynasty | 3 family_node rows; PC.parent_actor_ids has 2 entries with BiologicalParent variant; bidirectional sync verified; 0 dynasty rows |
| **AC-FF-8** | Marriage event emits EVT-T3 Derived AddSpouse; spouse_actor_ids updated bidirectionally | 2 EVT-T3 Derived events committed; both family_node rows updated with spouse_actor_ids |
| **AC-FF-9** | Death event emits EVT-T3 Derived MarkDeceased; family_node.is_deceased=true; refs preserved | family_node row updated; is_deceased=true; deceased_at_turn populated; refs to other actors preserved |
| **AC-FF-10** | I18nBundle resolves dynasty display_name across locales | display_name.translations["vi"]="Dòng họ Lý"; default="Lý Clan"; translations["zh"]="李氏" |

### 15.2 V1 failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-FF-3** | Bidirectional sync violation rejected at canonical seed (LM01 says Tiểu Thúy is sibling but Tiểu Thúy doesn't list LM01) | Rejected at Stage 0 with `family.bidirectional_sync_violation`; canonical seed bootstrap fails |
| **AC-FF-4** | Cyclic relation rejected (LM01 parent of X parent of LM01) | Rejected at Stage 0 with `family.cyclic_relation` |
| **AC-FF-5** | Duplicate relation rejected (same actor twice in parent_actor_ids) | Rejected at Stage 0 with `family.duplicate_relation` |
| **AC-FF-6** | Relation kind mismatch rejected (BiologicalChild on parent side) | Rejected at Stage 0 with `family.relation_kind_mismatch` |

### 15.3 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-FF-V1+1** | Extended traversal API (cousins / uncles / aunts) | V1+ FF-D2 |
| **AC-FF-V1+2** | V1+ runtime birth event (PC has child) | V1+ FF-D11 |
| **AC-FF-V1+3** | V1+ Divorce event flow | V1+ FF-D11 |
| **AC-FF-V1+4** | V1+ Adoption runtime event flow (post-canonical-seed) | V1+ FF-D11 |

### 15.4 Status transition criteria

- **DRAFT → CANDIDATE-LOCK:** design complete + boundary registered (`family_node` + `dynasty` aggregates + `family.*` namespace V1 enumeration + `canonical_dynasties` + `canonical_family_relations` RealityManifest extensions + `FF-*` stable-ID prefix + EVT-T8 Forge sub-shapes + EVT-T4 FamilyBorn). All AC-FF-1..10 specified with concrete fixtures.
- **CANDIDATE-LOCK → LOCK:** all AC-FF-1..10 V1-testable scenarios pass integration tests in world-service against Wuxia + Modern reality fixtures. V1+ scenarios (AC-FF-V1+1..4) deferred per §17.

---

## §16 Boundary registrations (in same commit chain)

DRAFT promotion registers:

1. `_boundaries/01_feature_ownership_matrix.md`:
   - NEW row: `family_node` aggregate (T2/Reality, owner=FF_001 Family Foundation)
   - NEW row: `dynasty` aggregate (T2/Reality sparse, owner=FF_001)
   - EVT-T4 System sub-type ownership row: add `FamilyBorn` (FF_001 owns)
   - EVT-T8 Administrative sub-shape rows: add `Forge:EditFamily` + `Forge:RegisterDynasty` (FF_001 owns)
2. `_boundaries/02_extension_contracts.md`:
   - §1.4 RejectReason namespace: NEW `family.*` row with 8 V1 rule_ids + 4 V1+ reservations
   - §2 RealityManifest: NEW `canonical_dynasties: Vec<DynastyDecl>` + `canonical_family_relations: Vec<FamilyRelationDecl>` REQUIRED V1
   - Stable-ID prefix table: NEW `FF-*` row (axioms / deferrals / decisions)
3. `_boundaries/99_changelog.md`: append DRAFT entry

---

## §17 Open questions deferred + landing point

| ID | Item | Defer to |
|---|---|---|
| **FF-D1** (Q8 LOCKED) | Bloodline traits inheritance (cultivator spirit roots / hybrid races / heritable curses) | V1+ RAC-D3 hybrid races + V1+ CULT_001 spirit roots consume FF_001 graph |
| **FF-D2** (Q2 LOCKED) | Extended family traversal API (cousins / uncles / aunts / in-laws / grandparents) | V1+ when first cross-feature consumer needs (V1+ NPC_002 family-cascade enrichment / V1+ TIT_001 succession traversal) |
| **FF-D3** | Cadet dynasty branches (parent_dynasty_id field) | V1+ when first reality has multi-generational dynasty split |
| **FF-D4** | Dynasty traditions / perks (CK3-style) | V1+ V2+ enrichment matching CK3 |
| **FF-D5** | Marriage as faction alliance currency | V1+ FAC_001 + V1+ DIPL_001 (NOT FF_001) |
| **FF-D6** | Sworn brotherhood (Total War 3K pattern) | V1+ FAC_001 (NOT FF_001 per Q4) |
| **FF-D7** | Master-disciple sect lineage (Wuxia) | V1+ FAC_001 (NOT FF_001 per Q4) |
| **FF-D8** | Title inheritance rules + heir succession | V1+ TIT_001 Title Foundation reads FF_001 dynasty.current_head_actor_id |
| **FF-D9** | Cross-reality family migration | V2+ WA_002 Heresy migration per Q7 LOCKED |
| **FF-D10** | Family-driven cascade opinion drift on death | V1+ NPC_002 enrichment reads FF_001 graph at NPC reaction priority |
| **FF-D11** | V1+ runtime birth/divorce/adoption event flows (V1 ships canonical seed only V1) | V1+ when PCS_001 + life-event simulation features ship |
| **FF-D12** | Family-shared inventory / clan treasury | V2+ RES_001 enrichment |

---

## §18 Cross-references

**Foundation tier (load-bearing):**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) — source-of-truth for actor_id in family_node
- [`PF_001 RealityManifest extension pattern`](../00_place/PF_001_place_foundation.md) — `places: Vec<PlaceDecl>` REQUIRED V1 mirror
- [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md) — display_name type for DynastyDecl
- [`07_event_model EVT-A10`](../../07_event_model/02_invariants.md) — event log = universal SSOT (justifies Q5 LOCKED no separate family_event_log)

**Sibling IDF (consumers + integrations):**
- [`IDF_004 Origin`](../00_identity/IDF_004_origin.md) ORG-D12 — lineage_id opaque V1; FF_001 V1+ resolves via family_node.dynasty_id + ancestor traversal V1+
- [`IDF_001 Race`](../00_identity/IDF_001_race.md) RAC-D3 — V1+ hybrid races consume FF_001 parent_actor_ids → race_assignment lookup
- [`IDF_005 Ideology`](../00_identity/IDF_005_ideology.md) — V1+ family-inherited ideology default (children inherit parent's stance)
- [`IDF_003 Personality`](../00_identity/IDF_003_personality.md) — independent V1; V1+ family-conflict opinion modifier

**Consumers:**
- WA_006 Mortality — death events consumed by FF_001 (one-way: WA_006 emits; FF_001 updates family_node)
- Future PCS_001 PC creation form
- Future `NPC_NNN` mortality — death cascade
- V1+ NPC_002 enrichment (family-cascade opinion drift FF-D10)
- V1+ TIT_001 Title Foundation — heir succession (FF-D8)
- V1+ FAC_001 Faction Foundation — sect/sworn brotherhood (NOT FF_001 per Q4 + FF-D5/D6/D7)
- V1+ RAC-D3 + V1+ CULT_001 — bloodline trait inheritance (FF-D1)

**Event model + boundaries:**
- [`07_event_model/02_invariants.md`](../../07_event_model/02_invariants.md) EVT-A1..A12 — taxonomy + extensibility + EVT-A10 SSOT
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) EVT-T3 Derived + EVT-T4 System (FamilyBorn) + EVT-T8 Administrative
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — family_node + dynasty aggregates + sub-type ownership
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — `family.*` V1 rule_id enumeration; §2 — RealityManifest extensions

**Spike + research:**
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Wuxia reality canonical content (Lý Minh + Lão Ngũ + Tiểu Thúy + Du sĩ)
- [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) — concept-notes with Q1-Q8 LOCKED rationale
- [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) — 8-system market survey (CK3/Bannerlord/Total War 3K/Stellaris/EU4/DF/D&D/VtM)
- [`00_identity/_research_character_systems_market_survey.md`](../00_identity/_research_character_systems_market_survey.md) §5.5 — family + dynasty cross-system patterns

---

## §19 Implementation readiness checklist

This doc satisfies items per DP-R2 + 22_feature_design_quickstart.md:

- [x] §2 Domain concepts + DynastyId / DynastyDecl / family_node / dynasty / RelationKind 6-variant / FamilyRelationDecl
- [x] §2.5 Event-model mapping (T3 Derived + T4 System FamilyBorn + T8 Forge:EditFamily + Forge:RegisterDynasty; no new EVT-T*; no separate family_event_log per Q5 EVT-A10)
- [x] §3 Aggregate inventory (2 aggregates V1: family_node + dynasty)
- [x] §4 Tier+scope (per DP-R2)
- [x] §5 DP primitives by name
- [x] §6 Capability JWT requirements
- [x] §7 Subscribe pattern (UI invalidation + V1+ NPC_002 / TIT_001 / RAC-D3 / CULT_001 reads)
- [x] §8 Pattern choices (Q1-Q8 LOCKED — separate aggregate / explicit direct / sparse dynasty / V1+ FAC_001 owns sect / materialized + EVT-A10 / RelationKind enum / V1 strict / V1+ deferred bloodline / RealityManifest REQUIRED / Synthetic forbidden / bidirectional sync)
- [x] §9 Failure UX (family.* V1 namespace 8 rules + 4 V1+ reservations)
- [x] §10 Cross-service handoff (canonical seed + V1+ runtime + Forge admin)
- [x] §11-§14 Sequences (canonical seed Wuxia / Marriage V1+ / Death from WA_006 / Forge admin)
- [x] §15 Acceptance criteria (10 V1-testable AC-FF-1..10 + 4 V1+ deferred AC-FF-V1+1..4)
- [x] §16 Boundary registrations (in same commit)
- [x] §17 Deferrals FF-D1..D12 (12 items)
- [x] §18 Cross-references
- [x] §19 Readiness (this section)

**Status transition:** DRAFT 2026-04-26 → **CANDIDATE-LOCK** when all AC-FF-1..10 pass integration tests against Wuxia + Modern reality fixtures → **LOCK** when V1+ scenarios pass after WA_002 / FAC_001 / TIT_001 ship.

**Next** (when CANDIDATE-LOCK granted): world-service can scaffold family_node + dynasty aggregates; WA_006 mortality wires up death cascade; future PCS_001 PC creation form references FF_001.
