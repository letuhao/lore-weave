# FAC_001 — Faction Foundation

> **Conversational name:** "Faction" (FAC). Tier 5 Actor Substrate Foundation feature owning per-reality `faction` aggregate (sparse — only declared sects/orders/clans/guilds get rows) + per-actor `actor_faction_membership` aggregate (V1 single-membership cap; V1+ multi). Resolves V1+ deferrals from FF_001 (FF-D7 master-disciple) + IDF_005 (IDL-D2 sect membership ideology binding). Wuxia critical (sect rivalries / master-disciple / Wulin Meng).
>
> **Boundary discipline:** FAC_001 = sect / order / clan-retinue / guild + master-disciple + (V1+) sworn brotherhood. FF_001 = biological + adoption (separated; per FF Q4 LOCKED). V1+ TIT_001 = noble / sect-leader title rank (separated). V1+ REP_001 = per-(actor, faction) reputation projection (separated). V1+ CULT_001 = cultivation method binding via sect_id. V1+ DIPL_001 = inter-faction dynamic relations (separated).
>
> **Category:** FAC — Faction Foundation (Tier 5 Actor Substrate post-IDF + post-FF_001 priority)
> **Status:** DRAFT 2026-04-26 (Phase 0 CONCEPT promoted to DRAFT after Q1-Q10 LOCKED via deep-dive 2026-04-26 user "A" confirmation; 3 REVISIONS noted)
> **Stable IDs in this file:** `FAC-A*` axioms · `FAC-D*` deferrals · `FAC-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) (sibling pattern); [IDF_005 IDL-D2](../00_identity/IDF_005_ideology.md) (sect membership ideology binding RESOLVED here); [FF_001 Q4 + FF-D7](../00_family/FF_001_family_foundation.md) (master-disciple ownership boundary RESOLVED here); [WA_001 Lex AxiomDecl](../02_world_authoring/WA_001_lex.md) (V1+ requires_faction hook); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md) (display_name); [07_event_model EVT-A10](../../07_event_model/02_invariants.md) (event log = universal SSOT).
> **Defers to:** future PCS_001 (PC creation form selects faction); future `NPC_NNN` mortality (sect-leader death cascade); V1+ TIT_001 Title Foundation (sect succession rules); V1+ REP_001 Reputation Foundation (per-(actor, faction) reputation); V1+ CULT_001 Cultivation Foundation (sect cultivation method); V1+ DIPL_001 Diplomacy Foundation (inter-faction dynamic relations); V2+ WA_002 Heresy (cross-reality migration per Q8 LOCKED).
> **Event-model alignment:** Faction events = EVT-T3 Derived (`aggregate_type=actor_faction_membership` with delta_kinds JoinFaction / LeaveFaction / ChangeRole / ChangeRank / SetMaster / RemoveMaster + `aggregate_type=faction` with delta_kind SetCurrentHead) + EVT-T4 System sub-types `FactionBorn` + `FactionMembershipBorn` at canonical seed + EVT-T8 Administrative `Forge:RegisterFaction` + `Forge:EditFaction` + `Forge:EditFactionMembership`. No new EVT-T* category.

---

## §1 User story (Wuxia 5-sect preset + Modern + V1+ runtime)

### V1 Wuxia 5-sect preset (RealityManifest.canonical_factions)

| Sect | Display name | Faction kind | Ideology binding | Default relations |
|---|---|---|---|---|
| 1 | Đông Hải Đạo Cốc | Sect | Đạo Devout+ | Hostile to Ma Tông; Allied to Trung Nguyên Võ Hiệp; Neutral else |
| 2 | Tây Sơn Phật Tự | Sect | Phật Devout+ | Hostile to Ma Tông; Neutral else |
| 3 | Ma Tông | Sect | (deviant; multi-stance) | Hostile to all righteous sects |
| 4 | Trung Nguyên Võ Hiệp | Sect | none required | Neutral all |
| 5 | Tán Tu Đồng Minh | Coalition | flexible | Neutral all |

### V1 canonical actor faction memberships

- **Lý Minh** (PC) — V1 unaffiliated (memberships=[]); V1+ may join via story-event
- **Du sĩ** (NPC, scholar) — member of Đông Hải Đạo Cốc; role_id="outer_disciple"; rank_within_role=3; master_actor_id=Some("old_elder_npc_id")
- **Tiểu Thúy** (NPC, innkeeper daughter) — V1 unaffiliated (memberships=[])
- **Lão Ngũ** (NPC, innkeeper) — V1 unaffiliated (memberships=[])

### V1+ runtime examples (canonical seed only V1; runtime V1+)

- **PC LM01 joins Trung Nguyên Võ Hiệp** mid-story → V1+ JoinFaction event → memberships.push(FactionMembershipEntry { faction_id, role_id="recruit", rank_within_role=1, master_actor_id=None, joined_reason: PcCreation })
- **Du sĩ promoted to inner_disciple** → V1+ ChangeRole event → role_id="inner_disciple"; rank reset
- **Sect master dies** → V1+ TIT_001 cascades → V1+ SetCurrentHead event on faction aggregate (heir_actor_id from master_disciple chain)

**This feature design specifies:** `faction` aggregate sparse storage per-(reality, faction_id) with declarative metadata + 6-variant FactionKind closed enum + author-declared roles taxonomy + 3-variant RelationStance default_relations + ideology binding (RESOLVES IDL-D2) + sect-leader head ref; `actor_faction_membership` aggregate per-(reality, actor_id) with Vec<FactionMembershipEntry> (V1 cap=1 per Q2 REVISION) + numeric u16 rank (Q4 REVISION) + master_actor_id field (RESOLVES FF-D7); 8 V1 reject rule_ids in `faction.*` namespace; bidirectional sync at canonical seed.

After this lock: every actor has deterministic faction membership row (possibly empty); FF-D7 + IDL-D2 resolved; V1+ TIT_001 + V1+ REP_001 + V1+ CULT_001 + V1+ DIPL_001 consume FAC_001 for downstream features.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **FactionId** | `pub struct FactionId(pub String);` typed newtype (e.g., `FactionId("faction_dong_hai_dao_coc")`) | Opaque per-reality. Sparse storage. Pattern matches RaceId / LanguageId / IdeologyId / DynastyId. |
| **RoleId** | `pub struct RoleId(pub String);` typed newtype (e.g., `RoleId("sect_master")` / `RoleId("inner_disciple")`) | Opaque per-faction (each FactionDecl has own role taxonomy per Q3 LOCKED). |
| **SwornBondId** (V1+) | `pub struct SwornBondId(pub String);` typed newtype | V1+ FAC-D10 enrichment (per Q7 REVISION); V1 NOT shipped. |
| **FactionKind** | Closed enum 6-variant: `Sect / Order / Clan / Guild / Coalition / Other` | V1 closed set. Sect = wuxia martial+spiritual; Order = religious; Clan = blood-based; Guild = mercantile; Coalition = multi-faction alliance (Wulin Meng); Other = misc. |
| **RelationStance** | Closed enum 3-variant: `Hostile / Neutral / Allied` | V1 closed set per Q5 LOCKED. Static at canonical seed. Used for opinion modifier baseline (Hostile -10 / Neutral 0 / Allied +5). |
| **JoinReason** | Closed enum 4-variant V1: `CanonicalSeed / PcCreation / NpcSpawn / AdminOverride { reason }` | Audit per join event. V1+ extensions: Defection { from_faction, reason } / Recruitment { recruited_by }. |
| **RoleDecl** | Author-declared per-faction entry (in FactionDecl.roles) | role_id + display_name (I18nBundle) + authority_level (u8 0-100 for ordering); V1+ extensions: max_actors_in_role + allowed_succession_kinds. |
| **FactionDecl** | Author-declared per-reality entry (in RealityManifest.canonical_factions) | faction_id + display_name (I18nBundle) + faction_kind + roles (Vec<RoleDecl>) + requires_ideology (Option<Vec<(IdeologyId, FervorLevel)>>) + default_relations (HashMap<FactionId, RelationStance>) + canon_ref + founder_actor_id + current_head_actor_id. |
| **faction** | T2 / Reality aggregate; per-(reality, faction_id) sparse row | Per-faction metadata + current_head + default_relations. **Mutable V1+** (current_head_actor_id updates on succession). Sparse storage (only declared factions get rows). |
| **actor_faction_membership** | T2 / Reality aggregate; per-(reality, actor_id) row holds `Vec<FactionMembershipEntry>` | Per-actor faction memberships. V1 cap=1 (Q2 REVISION); V1+ relax cap. Synthetic actors forbidden V1 (Q10 LOCKED). |
| **FactionMembershipEntry** | `{ faction_id, role_id, rank_within_role: u16, master_actor_id: Option<ActorId>, joined_at_turn, joined_at_fiction_ts, joined_reason }` | Per-membership state. master_actor_id RESOLVES FF-D7 master-disciple. V1+ additive: sworn_bond_id (FAC-D10) + explicit_rank_name (FAC-D17 / Q4 REVISION enrichment). |

**Cross-feature consumers:**
- IDF_005 IDL-D2 RESOLVED: FactionDecl.requires_ideology validated against actor_ideology_stance at canonical seed
- FF_001 FF-D7 RESOLVED: master_actor_id field (NOT FF_001 family relation)
- WA_001 Lex (V1+ closure) — `AxiomDecl.requires_faction: Option<Vec<FactionId>>` axiom-gate at Stage 4
- V1+ NPC_002 — rival-faction NPC priority Tier 4 modifier; opinion modifier baseline via faction.default_relations
- V1+ TIT_001 Title Foundation — sect-leader heir succession reads faction.current_head_actor_id
- V1+ REP_001 Reputation Foundation — per-(actor, faction) reputation projection separate aggregate
- V1+ CULT_001 Cultivation Foundation — sect cultivation method binding via faction_id
- V1+ DIPL_001 Diplomacy Foundation — dynamic faction-faction relations layer
- Future PCS_001 — PC creation form selects faction or unaffiliated

---

## §2.5 Event-model mapping (per [`07_event_model`](../../07_event_model/) EVT-T1..T11)

FAC_001 emits / consumes events that all map to existing active EVT-T* categories — no new category needed. Per EVT-A10: channel event stream IS the audit log (no separate faction_event_log aggregate).

| FAC_001 path | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| Faction registered at canonical seed | **EVT-T4 System** | `FactionBorn { faction_id, faction_kind, roles_count }` | Bootstrap (RealityBootstrapper) | ✓ V1 |
| Membership at canonical seed | **EVT-T4 System** | `FactionMembershipBorn { actor_id, faction_id, role_id, rank }` | Bootstrap | ✓ V1 |
| Join faction (V1+ runtime) | **EVT-T3 Derived** | `aggregate_type=actor_faction_membership`, `delta_kind=JoinFaction` | Aggregate-Owner (FAC_001 owner-service) | V1+ runtime |
| Leave faction | **EVT-T3 Derived** | `delta_kind=LeaveFaction` | Aggregate-Owner | V1+ runtime |
| Change role | **EVT-T3 Derived** | `delta_kind=ChangeRole` | Aggregate-Owner | V1+ runtime |
| Change rank | **EVT-T3 Derived** | `delta_kind=ChangeRank` | Aggregate-Owner | V1+ runtime |
| Set master (master-disciple bond formed) | **EVT-T3 Derived** | `delta_kind=SetMaster` | Aggregate-Owner | V1+ runtime |
| Remove master (master-disciple bond broken) | **EVT-T3 Derived** | `delta_kind=RemoveMaster` | Aggregate-Owner | V1+ runtime |
| Faction succession (head change) | **EVT-T3 Derived** | `aggregate_type=faction`, `delta_kind=SetCurrentHead` | Aggregate-Owner (V1+ TIT_001 trigger) | V1+ runtime |
| Forge admin register faction | **EVT-T8 Administrative** | `Forge:RegisterFaction { faction_id, faction_decl, reason }` | Forge (WA_003) | ✓ V1 |
| Forge admin edit faction | **EVT-T8 Administrative** | `Forge:EditFaction { faction_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |
| Forge admin edit membership | **EVT-T8 Administrative** | `Forge:EditFactionMembership { actor_id, edit_kind, before, after, reason }` | Forge | ✓ V1 |

**Closed-set proof for FAC_001:** every faction-related path produces an active EVT-T* (T3 / T4 / T8). No new EVT-T* row.

---

## §3 Aggregate inventory

**2 aggregates V1.**

### 3.1 `faction` (T2 / Reality scope — sparse)

```rust
#[derive(Aggregate)]
#[dp(type_name = "faction", tier = "T2", scope = "reality")]
pub struct Faction {
    pub reality_id: RealityId,
    pub faction_id: FactionId,
    pub display_name: I18nBundle,                              // RES_001 §2.3
    pub faction_kind: FactionKind,
    pub roles: Vec<RoleDecl>,                                  // author-declared per Q3 LOCKED
    pub requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>,    // RESOLVES IDL-D2
    pub default_relations: HashMap<FactionId, RelationStance>, // static V1 per Q5 LOCKED
    pub founder_actor_id: Option<ActorId>,                      // None if founder predates reality
    pub current_head_actor_id: Option<ActorId>,                 // None if faction extinct V1+; V1+ TIT_001 succession updates
    pub member_count: u32,                                      // sparse query helper
    pub canon_ref: Option<GlossaryEntityId>,
    pub schema_version: u32,
}

pub enum FactionKind {
    Sect,           // wuxia martial+spiritual
    Order,          // religious
    Clan,           // blood-based
    Guild,          // mercantile
    Coalition,      // multi-faction alliance (Wulin Meng)
    Other,
}

pub struct RoleDecl {
    pub role_id: RoleId,
    pub display_name: I18nBundle,
    pub authority_level: u8,                                    // 0-100 for ordering (sect_master=100; recruit=10)
    // V1+ extensions (additive per I14)
    // pub max_actors_in_role: Option<u32>,                    // sect_master cap=1 V1+
    // pub allowed_succession_kinds: Vec<SuccessionKindId>,    // V1+ TIT_001 hooks
}

pub enum RelationStance {
    Hostile,        // -10 opinion baseline modifier
    Neutral,        // 0 opinion baseline
    Allied,         // +5 opinion baseline
}
```

- T2 + RealityScoped: sparse storage (only declared factions; typically 5 sects per Wuxia preset)
- One row per `(reality_id, faction_id)`
- **Mutable V1+** (current_head_actor_id on succession; V1+ TIT_001)
- V1 minimal fields; V1+ additive enrichment

### 3.2 `actor_faction_membership` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_faction_membership", tier = "T2", scope = "reality")]
pub struct ActorFactionMembership {
    pub reality_id: RealityId,
    pub actor_id: ActorId,                                      // EF_001 §5.1 source
    pub memberships: Vec<FactionMembershipEntry>,               // V1 cap=1 per Q2 REVISION; V1+ relax
    pub last_modified_at_turn: u64,
    pub schema_version: u32,
}

pub struct FactionMembershipEntry {
    pub faction_id: FactionId,
    pub role_id: RoleId,                                        // ref to FactionDecl.roles[*].role_id
    pub rank_within_role: u16,                                  // numeric V1 per Q4 REVISION; ordered ascending (1 = highest authority within role)
    pub master_actor_id: Option<ActorId>,                       // sect lineage chain per Q6 LOCKED; FF-D7 RESOLVED
    pub joined_at_turn: u64,
    pub joined_at_fiction_ts: i64,
    pub joined_reason: JoinReason,
    // V1+ extensions (additive per I14)
    // pub sworn_bond_id: Option<SwornBondId>,                  // V1+ FAC-D10 per Q7 REVISION
    // pub explicit_rank_name: Option<I18nBundle>,              // V1+ FAC-D17 per Q4 REVISION
}

pub enum JoinReason {
    CanonicalSeed,
    PcCreation,
    NpcSpawn,
    AdminOverride { reason: String },
    // V1+ extensions
    // Defection { from_faction: FactionId, reason: String },
    // Recruitment { recruited_by: ActorId },
}
```

- T2 + RealityScoped; per-actor across reality lifetime
- One row per `(reality_id, actor_id)` (every PC + NPC MUST have row except Synthetic forbidden V1)
- **Mutable V1+** via Apply events (JoinFaction / LeaveFaction / ChangeRole / ChangeRank / SetMaster / RemoveMaster)
- V1 ships canonical seed only (V1+ runtime per FAC-D11)
- Synthetic actors forbidden V1 per Q10 LOCKED

---

## §4 Tier+scope (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `faction` | T2 | T2 | Reality | ~0.1 per turn (UI badge + V1+ TIT_001 + V1+ REP_001 + V1+ DIPL_001 reads) | ~0 V1 (canonical seed only); V1+ rare succession events | Sparse storage; mutable but very rare |
| `actor_faction_membership` | T2 | T2 | Reality | ~0.5-1 per turn (UI tooltip + V1+ NPC_002 priority + V1+ Lex gate at Stage 4) | ~0.001 V1 (canonical seed only); V1+ ~0.01/turn (Join/Leave/Promote events) | Per-actor; mutable but rare V1 |

---

## §5 DP primitives

### 5.1 Reads
- `dp::read_projection_reality::<Faction>(ctx, faction_id)` — UI badge + V1+ consumer reads
- `dp::read_projection_reality::<ActorFactionMembership>(ctx, actor_id)` — UI tooltip + V1+ traversal
- `dp::query_scoped_reality::<ActorFactionMembership>(ctx, predicate=field_eq(memberships[0].faction_id, X))` — operator query "all members of Đông Hải Đạo Cốc"
- `dp::read_reality_manifest(ctx).canonical_factions` + `.canonical_faction_memberships`

### 5.2 Writes
- `dp::t2_write::<Faction>(ctx, faction_id, RegisterFactionDelta { ... })` — canonical seed
- `dp::t2_write::<Faction>(ctx, faction_id, SetCurrentHeadDelta { actor_id })` — V1+ succession
- `dp::t2_write::<ActorFactionMembership>(ctx, actor_id, ApplyMembershipDelta { delta_kind, ... })` — Apply events (JoinFaction / LeaveFaction / ChangeRole / ChangeRank / SetMaster / RemoveMaster)
- Forge admin events emitted as EVT-T8 Administrative

### 5.3 Subscriptions
- UI subscribes to faction + actor_faction_membership invalidations via DP-X cache invalidation
- V1+ NPC_002 reads at SceneRoster build time (cached)

### 5.4 Capability + lifecycle
- `produce: [Derived]` + `write: { aggregate_type: faction, tier: T2, scope: reality }` — for FAC_001 owner-service
- `produce: [Derived]` + `write: actor_faction_membership @ T2 @ reality` — same owner
- `produce: [System]` + sub-types `FactionBorn` + `FactionMembershipBorn` — RealityBootstrapper
- `produce: [Administrative]` + sub-shapes `Forge:RegisterFaction` / `Forge:EditFaction` / `Forge:EditFactionMembership` — Forge admin (WA_003)

---

## §6 Capability requirements (JWT claims)

Inherits PL_001 + EF_001 + IDF + FF_001 patterns. No new claim category.

| Claim | Granted to | Why |
|---|---|---|
| `produce: [Derived]` + `write: faction @ T2 @ reality` | world-service backend (FAC_001 owner role) | succession events V1+ |
| `produce: [Derived]` + `write: actor_faction_membership @ T2 @ reality` | world-service backend | Apply events |
| `produce: [System]` + sub-types `FactionBorn` + `FactionMembershipBorn` | RealityBootstrapper service | canonical seed at world-build |
| `produce: [Administrative]` + sub-shapes `Forge:RegisterFaction` + `Forge:EditFaction` + `Forge:EditFactionMembership` | Forge admin (WA_003) | admin override audit |
| `read: faction @ T2 @ reality` + `read: actor_faction_membership @ T2 @ reality` | every PC session + NPC_002 + V1+ TIT_001 + V1+ REP_001 + V1+ DIPL_001 + V1+ CULT_001 + V1+ Lex consumer | UI display + V1+ cross-feature traversals |

---

## §7 Subscribe pattern

UI receives faction + actor_faction_membership updates via DP-X cache invalidation → re-renders sect badge + role tooltip. V1+ NPC_002 reads at SceneRoster build time (cached for batch duration). V1+ TIT_001 reads faction.current_head_actor_id at heir-selection event time.

---

## §8 Pattern choices

### 8.1 2 aggregates V1 (Q1 LOCKED)
faction (sparse) + actor_faction_membership. Lifecycle differs (faction mutable on succession; actor_faction_membership mutable on join/leave); access patterns differ; V1+ TIT_001 + REP_001 + DIPL_001 consumer support.

### 8.2 Vec schema V1 with cap=1 validator (Q2 REVISION LOCKED)
`memberships: Vec<FactionMembershipEntry>` from V1; V1 validator rejects len()>1 with `faction.multi_membership_forbidden_v1`. V1+ relax cap = single-line change; NO schema migration.

### 8.3 Author-declared role taxonomy (Q3 LOCKED)
RoleDecl per-faction (role_id + display_name + authority_level). Wuxia narrative authenticity preserved; engine doesn't lose information.

### 8.4 Numeric u16 rank only V1 (Q4 REVISION LOCKED)
Named rank computed on display layer (LLM/UI uses I18nBundle template). V1+ explicit_rank_name override field via FAC-D17.

### 8.5 Static default_relations V1 (Q5 LOCKED)
HashMap<FactionId, RelationStance> at canonical seed; V1+ DIPL_001 dynamic layer.

### 8.6 master_actor_id field (Q6 LOCKED)
Sect lineage chain via traversal; FF-D7 RESOLVED. Validation: same faction + higher authority + no cycle.

### 8.7 V1+ defer sworn brotherhood (Q7 REVISION LOCKED)
NO sworn_bond_id field V1; FAC-D10 V1+ enrichment activates field + sworn_bonds aggregate when first wuxia content needs.

### 8.8 V1 strict single-reality (Q8 LOCKED)
Inherits IDF + FF discipline; V2+ Heresy migration.

### 8.9 V1+ Lex axiom gate hook (Q9 LOCKED)
AxiomDecl.requires_faction reserved V1+ at WA_001 closure pass; V1 always None.

### 8.10 Synthetic actor forbidden V1 (Q10 LOCKED)
Matches IDF + FF discipline.

### 8.11 Bidirectional sync at canonical seed
faction.current_head_actor_id = X requires actor X has membership in this faction with role authority_level=100 (sect_master). Faction.member_count derived from query.

### 8.12 Ideology binding validated at canonical seed (RESOLVES IDL-D2)
FactionDecl.requires_ideology checked against actor_ideology_stance at canonical seed. Reject `faction.ideology_binding_violation`.

---

## §9 Failure-mode UX

Reject paths split by validator stage owner per [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md).

| Reject reason | Stage | When | Vietnamese reject copy (I18nBundle) |
|---|---|---|---|
| `faction.unknown_faction_id` | 0 schema | faction_id not in canonical_factions + faction aggregate | "Phái không tồn tại trong thế giới này." |
| `faction.unknown_role_id` | 0 schema | role_id not in FactionDecl.roles | "Vai trò không tồn tại trong phái." |
| `faction.multi_membership_forbidden_v1` | 0 schema | Vec.len() > 1 (per Q2 REVISION cap=1) | "V1 không hỗ trợ đa phái; mỗi nhân vật chỉ thuộc một phái." |
| `faction.master_cross_sect_forbidden` | 0 schema | master_actor_id member of different faction | "Sư phụ phải cùng phái với đệ tử." |
| `faction.master_authority_violation` | 0 schema | master.authority_level <= disciple.authority_level | "Sư phụ phải có chức vụ cao hơn đệ tử." |
| `faction.cyclic_master_chain` | 0 schema | LM01 master-of-X master-of-LM01 | "Quan hệ sư phụ-đệ tử không thể tạo vòng lặp." |
| `faction.ideology_binding_violation` | 0 schema | actor's ideology stance doesn't satisfy FactionDecl.requires_ideology | "Tư tưởng không phù hợp để gia nhập phái này." |
| `faction.synthetic_actor_forbidden` | 0 schema | Synthetic actor cannot have faction membership | (Schema check; not user-facing) |

**`faction.*` V1 rule_id enumeration** (8 V1 rules):

1. `faction.unknown_faction_id` — Stage 0
2. `faction.unknown_role_id` — Stage 0
3. `faction.multi_membership_forbidden_v1` — Stage 0 (per Q2 REVISION cap=1)
4. `faction.master_cross_sect_forbidden` — Stage 0
5. `faction.master_authority_violation` — Stage 0
6. `faction.cyclic_master_chain` — Stage 0
7. `faction.ideology_binding_violation` — Stage 0 (RESOLVES IDL-D2)
8. `faction.synthetic_actor_forbidden` — Stage 0

**V1+ reservations:**
- `faction.cross_reality_mismatch` (V2+ Heresy migration per Q8)
- `faction.lex_axiom_forbidden` (V1+ when first faction-gated axiom ships per Q9)
- `faction.sworn_bond_unsupported_v1` (V1+ FAC-D10 enrichment activation)
- `faction.member_role_count_exceeded` (V1+ when RoleDecl.max_actors_in_role enrichment ships)

V1 user-facing rejects: `faction.multi_membership_forbidden_v1` + `faction.ideology_binding_violation` (V1+ Forge admin scenarios trigger). Schema-level rejects unreachable in normal operation (canonical seed validates pre-bootstrap).

---

## §10 Cross-service handoff (canonical seed flow)

Concrete example: Wuxia reality bootstrap with 5 sects + 1 NPC membership (Du sĩ in Đông Hải Đạo Cốc).

```
1. RealityBootstrapper service (Bootstrap role):
   a. Read RealityManifest.canonical_factions:
      [FactionDecl { faction_id: "faction_dong_hai_dao_coc", display_name, faction_kind: Sect,
                     roles: [sect_master, elder, inner_disciple, outer_disciple, recruit],
                     requires_ideology: Some([(ideology_dao, Devout)]),
                     default_relations: { faction_ma_tong: Hostile, faction_trung_nguyen_vo_hiep: Allied },
                     founder_actor_id: None, current_head_actor_id: None, ... },
       ... 4 more sects ...]
      → for each: dp::t2_write::<Faction>(ctx, faction_id, RegisterFactionDelta { ... }) → T0 Derived
      Emit EVT-T4 System: FactionBorn { faction_id, faction_kind, roles_count }
   
   b. Read RealityManifest.canonical_faction_memberships:
      [FactionMembershipDecl { actor_id: du_si, faction_id: faction_dong_hai_dao_coc,
                               role_id: outer_disciple, rank_within_role: 3,
                               master_actor_id: Some(old_elder_npc_id) },
       ... ]
   
   c. Validate (Stage 0 schema):
      - actor_id du_si exists in EF_001 entity_binding ✓
      - faction_id "faction_dong_hai_dao_coc" exists in canonical_factions + faction aggregate ✓
      - role_id "outer_disciple" exists in FactionDecl.roles ✓
      - master_actor_id (old_elder_npc_id) exists; same faction ✓; authority_level higher ✓; no cycle ✓
      - du_si.actor_ideology_stance includes (ideology_dao, Devout) (matches requires_ideology) ✓
   ✓ schema OK
   
   d. For each canonical actor with membership:
      Emit EVT-T4 System: FactionMembershipBorn { actor_id, faction_id, role_id, rank }
      dp::t2_write::<ActorFactionMembership>(ctx, du_si, ApplyMembershipDelta {
        memberships: vec![FactionMembershipEntry {
          faction_id, role_id, rank_within_role: 3,
          master_actor_id: Some(old_elder_npc_id),
          joined_reason: JoinReason::CanonicalSeed, ...
        }]
      }) → T1 Derived
      causal_refs = [reality_bootstrap_event_id]
   
   e. For actors with NO membership (Lý Minh / Tiểu Thúy / Lão Ngũ):
      dp::t2_write::<ActorFactionMembership>(ctx, actor_id, ApplyMembershipDelta {
        memberships: vec![]
      }) → T_n Derived

   f. Update faction.current_head_actor_id (if declared) + member_count

Result: 5 faction rows committed; ~10 actor_faction_membership rows committed; 5 FactionBorn + ~3 FactionMembershipBorn EVT-T4 emitted.

2. V1+ NPC_002 reads at SceneRoster build:
   For each NPC in cell, read actor_faction_membership; rival-faction NPCs Tier 4 priority modifier.

3. V1+ TIT_001 sect succession (V1+ when sect master dies):
   WA_006 mortality death event → V1+ TIT_001 consumer reads faction.current_head + master_disciple chain → emits SetCurrentHead Derived event on faction aggregate.
```

**Token chain:** RegisterFaction (T0 Derived) → FactionBorn (T1 System) → FactionMembershipBorn (T1 System) → ApplyMembership (T1 Derived). Multi-actor canonical seed sequential per DP-A19.

---

## §11 Sequence: Canonical seed (Wuxia 5-sect bootstrap)

```
RealityBootstrapper service @ reality-bootstrap event for Wuxia reality:

  Read RealityManifest.canonical_factions:
    [
      FactionDecl { faction_id: "faction_dong_hai_dao_coc", display_name: I18nBundle{...},
                    faction_kind: Sect, roles: [...5 RoleDecl...],
                    requires_ideology: Some([(ideology_dao, Devout)]),
                    default_relations: { faction_ma_tong: Hostile, faction_trung_nguyen_vo_hiep: Allied } },
      FactionDecl { faction_id: "faction_tay_son_phat_tu", ... requires_ideology: Some([(ideology_phat, Devout)]) },
      FactionDecl { faction_id: "faction_ma_tong", ... requires_ideology: None (deviant; multi-stance allowed) },
      FactionDecl { faction_id: "faction_trung_nguyen_vo_hiep", ... requires_ideology: None },
      FactionDecl { faction_id: "faction_tan_tu_dong_minh", faction_kind: Coalition, ... },
    ]
  
  Validate (Stage 0 schema):
    - 5 faction_id unique ✓
    - All RoleDecl.role_id unique within FactionDecl.roles ✓
    - All RelationStance values valid (3-variant enum) ✓
    - default_relations references exist in canonical_factions ✓
  ✓ schema OK
  
  Register factions:
    For each FactionDecl:
      dp::t2_write::<Faction>(ctx, faction_id, RegisterFactionDelta { ... }) → T0 Derived
      Emit EVT-T4 System: FactionBorn { faction_id, faction_kind, roles_count: 5 }
  
  Read RealityManifest.canonical_faction_memberships (only Du sĩ V1):
    FactionMembershipDecl { actor_id: du_si, faction_id: faction_dong_hai_dao_coc,
                            role_id: outer_disciple, rank_within_role: 3,
                            master_actor_id: Some(old_elder_npc_id) }
  
  Validate:
    - du_si.actor_ideology_stance includes (ideology_dao, Devout) ✓
    - master_actor_id same faction + authority higher + no cycle ✓
  ✓
  
  Apply membership for du_si:
    Emit EVT-T4 System: FactionMembershipBorn { actor_id: du_si, faction_id, role_id: outer_disciple, rank: 3 }
    dp::t2_write::<ActorFactionMembership>(ctx, du_si, ApplyMembershipDelta {
      memberships: vec![FactionMembershipEntry { ... }]
    }) → T1 Derived
  
  For LM01 / Tiểu Thúy / Lão Ngũ (no V1 membership):
    dp::t2_write::<ActorFactionMembership>(ctx, actor_id, ApplyMembershipDelta {
      memberships: vec![]  // empty Vec; cap=1 validator passes
    }) → T_n Derived

UI receives FactionBorn + FactionMembershipBorn + ApplyMembership events; renders 5 sect badges + Du sĩ Đông Hải Đạo Cốc tooltip.
```

---

## §12 Sequence: V1+ JoinFaction (PC defects mid-story)

```
PC LM01 joins Trung Nguyên Võ Hiệp (V1+ when PCS_001 + runtime story-event flow ships):

world-service:
  a. claim_turn_slot
  b. validator stages 0-9 ✓
     Stage 0 schema:
       - faction_id "faction_trung_nguyen_vo_hiep" exists in faction aggregate ✓
       - role_id "recruit" exists in FactionDecl.roles ✓
       - LM01.memberships.len() < 1 (cap=1; current empty Vec) ✓
       - faction_trung_nguyen_vo_hiep.requires_ideology = None (no constraint) ✓
       - master_actor_id = None (recruit role; no master yet) ✓
     Stage 7 world-rule: derive ApplyMembershipDelta
  c. dp.advance_turn → Submitted T1 (JoinFaction event)
  d. FAC_001 owner-service emits EVT-T3 Derived:
     dp.t2_write::<ActorFactionMembership>(ctx, LM01, ApplyMembershipDelta {
       delta_kind: JoinFaction { faction_id, role_id: recruit, rank: 1, joined_reason: PcCreation }
     }) → T2
     causal_refs = [T1]
  e. Update faction.member_count + 1 (faction_trung_nguyen_vo_hiep)
     dp.t2_write::<Faction>(ctx, faction_trung_nguyen_vo_hiep, UpdateMemberCountDelta { delta: +1 }) → T3
  f. release_turn_slot

UI re-renders LM01 faction badge "Recruit at Trung Nguyên Võ Hiệp".
```

---

## §13 Sequence: V1+ Sect succession (sect master dies)

```
NPC sect_master_npc dies via WA_006 mortality (V1+ Strike Lethal scenario):

WA_006 emits death event → mortality_state transition → T1 Derived

V1+ TIT_001 owner-service consumes (V1+ TIT_001 not yet shipped; placeholder flow):
  a. Read sect_master_npc.actor_faction_membership → finds faction_id + role_id="sect_master"
  b. Read faction(faction_id).current_head_actor_id == sect_master_npc.actor_id ✓
  c. Find heir disciple via master-disciple chain:
     - dp.query_scoped_reality::<ActorFactionMembership>(ctx, predicate=master_actor_id == sect_master_npc.actor_id)
     - Returns 5 inner disciples ranked by authority_level + rank_within_role
     - Heir = highest-authority disciple
  d. dp.t2_write::<Faction>(ctx, faction_id, SetCurrentHeadDelta {
       new_head: heir_actor_id
     }) → T2 Derived
     causal_refs = [T1]
  e. dp.t2_write::<ActorFactionMembership>(ctx, heir, ApplyMembershipDelta {
       delta_kind: ChangeRole { new_role_id: "sect_master", new_rank: 1 }
     }) → T3 Derived
  f. UI renders sect succession event narrative (LLM Layer 4)

Note: V1+ TIT_001 ships full succession rules (gavelkind / primogeniture / elective per CK3 pattern); FAC_001 V1 only provides graph for V1+ TIT_001 to consume.
```

---

## §14 Sequence: Forge admin override

```
Admin promotes Du sĩ from outer_disciple to inner_disciple (story-event):

  EVT-T8 Administrative: Forge:EditFactionMembership {
    actor_id: du_si,
    edit_kind: ChangeRole,
    before: FactionMembershipEntry { role_id: outer_disciple, rank: 3, ... },
    after: FactionMembershipEntry { role_id: inner_disciple, rank: 1, ... },
    reason: "Story-event reveals secret sect achievement"
  }

3-write atomic transaction:
  - actor_faction_membership row updated (Du sĩ.memberships[0])
  - EVT-T8 emitted
  - forge_audit_log entry
```

---

## §15 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service can pass these scenarios.

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-FAC-1** | Wuxia canonical bootstrap declares 5 sects + Du sĩ NPC membership in Đông Hải Đạo Cốc | 5 faction rows + ~4 actor_faction_membership rows committed; FactionBorn + FactionMembershipBorn EVT-T4 emitted |
| **AC-FAC-2** | Du sĩ has ideology_dao Devout; Faction.requires_ideology=[(ideology_dao, Devout)] satisfied at canonical seed | bidirectional validation passes; membership committed |
| **AC-FAC-3** | Master-disciple chain validated (Du sĩ.master = old_elder_npc; same faction; authority higher; no cycle) | validation passes; membership committed |
| **AC-FAC-4** | Cyclic master chain rejected (LM01 master-of-X master-of-LM01) | rejected at Stage 0 with `faction.cyclic_master_chain` |
| **AC-FAC-5** | Multi-membership rejected V1 (Vec.len()>1) | rejected at Stage 0 with `faction.multi_membership_forbidden_v1` (per Q2 REVISION cap=1) |
| **AC-FAC-6** | Unknown faction_id rejected | rejected at Stage 0 with `faction.unknown_faction_id` |
| **AC-FAC-7** | Unknown role_id rejected | rejected at Stage 0 with `faction.unknown_role_id` |
| **AC-FAC-8** | Ideology binding violation rejected (actor without required ideology stance) | rejected at Stage 0 with `faction.ideology_binding_violation`; resolves IDL-D2 |
| **AC-FAC-9** | I18nBundle resolves faction display_name + role display_name across locales | display_name correctly localized (vi / en / zh) |
| **AC-FAC-10** | Forge admin register faction (3-write atomic: faction row + EVT-T8 + forge_audit_log) | 3-write atomic transaction; audit log entry committed |

### 15.2 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-FAC-V1+1** | V1+ runtime JoinFaction event (PC defects mid-story) | V1+ FAC-D11 |
| **AC-FAC-V1+2** | V1+ TIT_001 sect succession (sect_master dies → heir takes head) | V1+ TIT_001 + FAC-D6 |
| **AC-FAC-V1+3** | V1+ multi-faction membership (cap relax) | V1+ FAC-D1 + FAC-D16 |
| **AC-FAC-V1+4** | V1+ FAC-D10 sworn brotherhood (sworn_bond_id field activation) | V1+ FAC-D10 |

### 15.3 Status transition criteria

- **DRAFT → CANDIDATE-LOCK:** design complete + boundary registered (`faction` + `actor_faction_membership` aggregates + `faction.*` namespace V1 enumeration + `canonical_factions` + `canonical_faction_memberships` RealityManifest extensions + `FAC-*` stable-ID prefix + EVT-T8 Forge sub-shapes + EVT-T4 System sub-types). All AC-FAC-1..10 specified.
- **CANDIDATE-LOCK → LOCK:** all AC-FAC-1..10 V1-testable scenarios pass integration tests in world-service against Wuxia + Modern reality fixtures. V1+ scenarios (AC-FAC-V1+1..4) deferred per §17.

---

## §16 Boundary registrations (in same commit chain)

DRAFT promotion registers:

1. `_boundaries/01_feature_ownership_matrix.md`:
   - NEW row: `faction` aggregate (T2/Reality sparse, owner=FAC_001)
   - NEW row: `actor_faction_membership` aggregate (T2/Reality, owner=FAC_001)
   - EVT-T4 System sub-type ownership: NEW `FactionBorn` + `FactionMembershipBorn`
   - EVT-T8 Administrative sub-shape ownership: NEW `Forge:RegisterFaction` + `Forge:EditFaction` + `Forge:EditFactionMembership`
   - Stable-ID prefix table: NEW `FAC-*` row
2. `_boundaries/02_extension_contracts.md`:
   - §1.4 RejectReason namespace: NEW `faction.*` row with 8 V1 rule_ids + 4 V1+ reservations
   - §2 RealityManifest: NEW `canonical_factions: Vec<FactionDecl>` + `canonical_faction_memberships: Vec<FactionMembershipDecl>` REQUIRED V1
3. `_boundaries/99_changelog.md`: append DRAFT entry

---

## §17 Open questions deferred + landing point

| ID | Item | Defer to |
|---|---|---|
| **FAC-D1** (Q2 REVISION) | Multi-faction membership V1+ cap relax (cap=1 → cap=N) | V1+ when first reality content needs multi-membership (Modern/D&D pattern) |
| **FAC-D2** | Sect cultivation method binding | V1+ CULT_001 Cultivation Foundation reads faction_id |
| **FAC-D3** (FF-D5) | Marriage as faction alliance | V1+ FAC_001 + V1+ DIPL_001 (resolves jointly with FF-D5) |
| **FAC-D4** | Faction-faction dynamic relations (treaties / wars / alliance changes) | V1+ DIPL_001 Diplomacy Foundation layers on top of FAC_001 static default_relations |
| **FAC-D5** | Wulin Meng parent_faction_id (hierarchical faction; cadet branches) | V1+ enrichment when first content needs parent faction |
| **FAC-D6** (FF-D8) | Sect succession rules (gavelkind / primogeniture / elective) | V1+ TIT_001 Title Foundation reads FAC_001 + FF_001 |
| **FAC-D7** | Per-(actor, faction) reputation projection | V1+ REP_001 Reputation Foundation separate aggregate |
| **FAC-D8** (Q9) | Faction-driven Lex axiom gate ACTIVE | V1+ when first faction-gated axiom ships in WA_001 closure pass |
| **FAC-D9** (Q8) | Cross-reality faction migration | V2+ WA_002 Heresy migration |
| **FAC-D10** (Q7 REVISION; FF-D6) | Sworn brotherhood (sworn_bond_id field + sworn_bonds aggregate) | V1+ when first wuxia content needs (Peach Garden Oath / Lương Sơn Bạc) |
| **FAC-D11** | V1+ runtime defection / join / leave event flows (V1 ships canonical seed only) | V1+ when PCS_001 + life-event simulation features ship |
| **FAC-D12** | Faction cultivation method registry | V1+ CULT_001 |
| **FAC-D13** | Faction treasury / clan-shared inventory | V2+ RES_001 enrichment |
| **FAC-D14** | Hierarchical faction parent_faction_id (cadet branches) | V1+ enrichment |
| **FAC-D15** | Faction-conflict opinion modifier non-member NPCs | V1+ NPC_002 enrichment reads FAC_001 graph |
| **FAC-D16** (Q2 REVISION enrichment) | Multi-faction membership cap relax | Same as FAC-D1 (cap=1 → cap=N V1+) |
| **FAC-D17** (Q4 REVISION enrichment) | Explicit named rank override field (explicit_rank_name: Option<I18nBundle>) | V1+ when first content needs override beyond auto-derived |

---

## §18 Cross-references

**Foundation tier (load-bearing):**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) — source-of-truth for actor_id
- [`PF_001 RealityManifest extension pattern`](../00_place/PF_001_place_foundation.md) — `places` REQUIRED V1 mirror
- [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md) — display_name type
- [`07_event_model EVT-A10`](../../07_event_model/02_invariants.md) — event log = universal SSOT
- [`PROG_001 Progression Foundation`](../00_progression/PROG_001_progression_foundation.md) — separate substrate (no FAC_001 overlap V1)

**Sibling IDF + FF + integration:**
- [`IDF_005 IDL-D2`](../00_identity/IDF_005_ideology.md) — sect membership ideology binding RESOLVED here via FactionDecl.requires_ideology
- [`FF_001 Q4 + FF-D7`](../00_family/FF_001_family_foundation.md) — master-disciple ownership boundary RESOLVED here via master_actor_id
- [`IDF_001 Race`](../00_identity/IDF_001_race.md) — V1+ race-bound sects (Cultivator-only); requires_race hook V1+
- [`IDF_004 Origin`](../00_identity/IDF_004_origin.md) — V1+ origin pack default sect declaration

**Consumers:**
- WA_001 Lex (V1+ closure) — `AxiomDecl.requires_faction` field
- Future PCS_001 — PC creation form
- V1+ TIT_001 — reads dynasty.current_head (FF_001) + sect_master role (FAC_001)
- V1+ REP_001 — per-(actor, faction) reputation projection separate aggregate
- V1+ CULT_001 — sect cultivation method binding
- V1+ DIPL_001 — inter-faction dynamic relations
- V1+ NPC_002 — rival-faction priority + opinion modifier

**Event model + boundaries:**
- [`07_event_model/02_invariants.md`](../../07_event_model/02_invariants.md) EVT-A1..A12 — taxonomy + extensibility + EVT-A10 SSOT
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) EVT-T3 Derived + EVT-T4 System (FactionBorn + FactionMembershipBorn) + EVT-T8 Administrative
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — faction + actor_faction_membership aggregates
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — `faction.*` V1 rule_id enumeration; §2 — RealityManifest extensions

**Spike + research:**
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Wuxia reality (Du sĩ Đông Hải Đạo Cốc affiliation)
- [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) — concept-notes with Q1-Q10 LOCKED rationale
- [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) — 10-system market survey

---

## §19 Implementation readiness checklist

This doc satisfies items per DP-R2 + 22_feature_design_quickstart.md:

- [x] §2 Domain concepts + FactionId / RoleId / RoleDecl / FactionKind 6-variant / RelationStance 3-variant / JoinReason 4-variant / FactionDecl / FactionMembershipDecl
- [x] §2.5 Event-model mapping (T3 Derived + T4 System FactionBorn + FactionMembershipBorn + T8 Forge sub-shapes; no new EVT-T*)
- [x] §3 Aggregate inventory (2 V1: faction sparse + actor_faction_membership)
- [x] §4 Tier+scope (per DP-R2)
- [x] §5 DP primitives by name
- [x] §6 Capability JWT requirements
- [x] §7 Subscribe pattern
- [x] §8 Pattern choices (12 design decisions per Q1-Q10 LOCKED with 3 REVISIONS)
- [x] §9 Failure UX (faction.* V1 namespace 8 rules + 4 V1+ reservations)
- [x] §10 Cross-service handoff (canonical seed + V1+ runtime + Forge admin)
- [x] §11-§14 Sequences (canonical seed Wuxia / V1+ JoinFaction / V1+ Sect succession / Forge admin)
- [x] §15 Acceptance criteria (10 V1-testable AC-FAC-1..10 + 4 V1+ deferred)
- [x] §16 Boundary registrations (in same commit)
- [x] §17 Deferrals FAC-D1..D17 (17 items)
- [x] §18 Cross-references
- [x] §19 Readiness (this section)

**Phase 3 cleanup applied 2026-04-26 (FAC_001 commit 3/4 cycle):**
- S1.1 §2 FactionId + RoleId typed newtypes confirmed (matches IDF foundation pattern)
- S1.2 §3.1 RelationStance Hostile/Neutral/Allied → opinion modifier baseline values explicit (-10 / 0 / +5) for V1+ NPC_002 enrichment
- S2.1 §10 Cross-service handoff bidirectional sync explicit — faction.current_head_actor_id ↔ actor_faction_membership with role authority_level=100 + cap=1 V1
- S2.2 §11 Canonical seed sequence — empty memberships Vec valid for unaffiliated actors (LM01/Tiểu Thúy/Lão Ngũ) explicit
- S2.3 §13 V1+ Sect succession sequence — TIT_001 dependency note (FAC_001 V1 doesn't ship succession rules; just provides graph)
- S3.1 §15.4 LOCK criterion split DRAFT→CANDIDATE-LOCK vs CANDIDATE-LOCK→LOCK (matches established pattern)
- S3.2 §17 deferral cross-references tightened — FAC-D6 ↔ FF-D8 + FAC-D3 ↔ FF-D5 + FAC-D10 ↔ FF-D6 + FAC-D7 ↔ V1+ REP_001 jointly noted

**Status transition:** DRAFT 2026-04-26 (Phase 3 applied) → **CANDIDATE-LOCK** in next commit (4/4) → **LOCK** when AC-FAC-1..10 pass integration tests + V1+ scenarios after TIT_001 / REP_001 / CULT_001 / DIPL_001 ship.

**Next** (when CANDIDATE-LOCK granted): world-service can scaffold faction + actor_faction_membership aggregates; V1+ TIT_001 + V1+ REP_001 + V1+ CULT_001 consumers wire up. WA_001 closure pass V1+ adds AxiomDecl.requires_faction field.
