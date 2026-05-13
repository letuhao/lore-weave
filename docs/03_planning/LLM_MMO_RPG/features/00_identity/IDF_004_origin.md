# IDF_004 — Origin Foundation

> **Conversational name:** "Origin" (ORG). Tier 5 Actor Substrate Foundation feature owning per-actor `actor_origin` aggregate (V1 minimal stub: birthplace + lineage_id + native_language ref + default_ideology_refs) + `OriginPackDecl` reality-specific cultural pack (V1+ enrichment). Origin is **immutable birth-context**; distinct from IDF_005 Ideology which is **mutable belief stance**.
>
> **V1+ FF_001 Family Foundation = first priority post-IDF closure** per POST-SURVEY-Q4 LOCKED — IDF_004 V1 lineage_id stays opaque tag (no parent/sibling refs); FF_001 V1+ designs full graph + dynasty.
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** CANDIDATE-LOCK 2026-04-26 (CONCEPT → DRAFT → Phase 3 → closure pass; Q-decisions ORG-Q1..Q10 locked + Q4 family graph LOCKED to V1 opaque only per POST-SURVEY-Q4)
> **Stable IDs:** `ORG-A*` axioms · `ORG-D*` deferrals · `ORG-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types); [PF_001 §3.1 ChannelId](../00_place/PF_001_place_foundation.md); [IDF_001 RaceId](IDF_001_race.md); [IDF_002 LanguageId](IDF_002_language.md); [IDF_005 IdeologyId](IDF_005_ideology_concept.md); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md).
> **Defers to:** future PCS_001 (PC origin at creation); NPC_001/`NPC_NNN` (NPC canonical seed origin); V1+ FF_001 Family Foundation (lineage graph + dynasty; HIGH priority); V1+ cultural_tradition_pack (naming convention + values + arts); V1+ multi-cultural origin V2+.
> **Event-model alignment:** Origin assignment events = EVT-T3 Derived (`aggregate_type=actor_origin`). Bootstrap OriginBorn events = EVT-T4 System (V1+ when origin packs populated). EVT-T8 Forge:EditOrigin admin override.

---

## §1 User story (Wuxia + Modern presets)

A Wuxia reality bootstraps with canonical actors:

1. **Lý Minh** (PC) — birthplace=`yen_vu_lau` (cell-tier ChannelId); lineage_id=Some("lineage_ly_clan_yen_vu_lau") (opaque tag V1; FF_001 V1+ resolves); native_language=`lang_quan_thoai`; default_ideology_refs=[`ideology_dao` Light, `ideology_phat` Light, `ideology_nho` Moderate] (Vietnamese xianxia syncretism); origin_pack_id=None V1.
2. **Tiểu Thúy** (NPC) — birthplace=`yen_vu_lau`; lineage_id=Some("lineage_lao_ngu_family"); native_language=`lang_quan_thoai`; default_ideology_refs=[]; origin_pack_id=None V1.
3. **Du sĩ** (NPC) — birthplace=`tu_zhou_di_qu` (different cell — wandering scholar); lineage_id=None (orphan / no recorded family V1); native_language=`lang_quan_thoai`; default_ideology_refs=[`ideology_dao` Devout]; origin_pack_id=None V1.
4. **Lão Ngũ** (NPC) — birthplace=`yen_vu_lau`; lineage_id=Some("lineage_lao_ngu_family"); native_language=`lang_quan_thoai`; default_ideology_refs=[]; origin_pack_id=None V1.

Modern Saigon reality: birthplace=`saigon_district_1`; native_language=`lang_tieng_viet`; default_ideology_refs=[].

**This feature design specifies:** the per-actor `actor_origin` aggregate with 4-field minimal stub V1; ChannelId birthplace ref to PF_001 cell-tier place; LanguageId native_language ref to IDF_002; IdeologyId default_ideology_refs to IDF_005; opaque LineageId tag (FF_001 V1+ resolves); origin_pack_id Option<OriginPackId> reserved V1+ schema slot; rejection UX with Vietnamese reject copy in `origin.*` namespace.

After this lock: every actor has deterministic origin context; IDF_002 default proficiency seeded; IDF_005 default ideology seeded; FF_001 V1+ can attach lineage graph to existing lineage_id tags.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **OriginPackId** | `pub struct OriginPackId(pub String);` typed newtype | Opaque per-reality. V1+ closed-set declared in RealityManifest.origin_packs. V1 not actively used (empty registry per ORG-Q9 LOCKED). |
| **LineageId** | `pub struct LineageId(pub String);` typed newtype | Opaque V1 tag. V1+ FF_001 Family Foundation populates with parent_lineage_ids + member_actor_ids graph. V1 actor.lineage_id is just a forensic tag. |
| **OriginPackDecl** (V1+ enrichment; V1 schema slot only) | Author-declared per-reality entry | display_name (I18nBundle) + default_birthplace_channel + default_native_language + default_ideology_refs + naming_convention (V1+) + values_list (V1+) + canon_ref. V1 schema slot only. |
| **actor_origin** | T2 / Reality aggregate; per-(reality, actor_id) row | Generic for PC + NPC. V1 4-field stub (birthplace + lineage_id + native_language + default_ideology_refs) + origin_pack_id reserved. ActorId source = EF_001 §5.1. Synthetic actors forbidden V1 (ORG-Q7 LOCKED). |

**Cross-feature consumers:**
- IDF_002 — native_language ref informs default proficiency at canonical seed
- IDF_005 — default_ideology_refs seed actor_ideology_stance at canonical seed (suggestion; may diverge)
- PF_001 — birthplace_channel ChannelId ref (cell-tier; ORG-Q3 LOCKED)
- PCS_001 (V1+) — PC creation form selects origin_pack_id (V1+) or null V1
- NPC_001/`NPC_NNN` — NPC canonical seed declares origin
- V1+ FF_001 Family Foundation — lineage_id graph attachment
- V1+ NPC_002 — origin-conflict opinion modifier (ORG-D8)

---

## §2.5 Event-model mapping

| Path | EVT-T* | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Origin assigned at canonical seed / PC creation / NPC spawn | **EVT-T3 Derived** | `aggregate_type=actor_origin`, delta_kind=`AssignOrigin` | Aggregate-Owner role (IDF_004 owner-service in world-service) | Causal-ref REQUIRED |
| Origin admin override (Forge edit) | **EVT-T8 Administrative** | `Forge:EditOrigin { actor_id, edit_kind, before, after, reason }` | Forge role (WA_003) | AC-ORG-9 atomicity |
| V1+ Origin pack registry seeded | **EVT-T4 System** | (V1+ when origin packs populated; no V1 sub-type) | Bootstrap role | V1+ when first reality with origin packs ships |

**Closed-set proof:** all paths use active EVT-T* (T3 / T4 V1+ / T8). No new EVT-T*.

---

## §3 Aggregate inventory

### 3.1 `actor_origin` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_origin", tier = "T2", scope = "reality")]
pub struct ActorOrigin {
    pub reality_id: RealityId,
    pub actor_id: ActorId,                             // EF_001 §5.1 source

    // V1 minimal stub (4 fields)
    pub birthplace_channel: Option<ChannelId>,         // PF_001 cell-tier; None for "unknown / canonical seed without place"
    pub lineage_id: Option<LineageId>,                 // V1+ FF_001 populates; V1 opaque forensic tag (no parent/sibling refs per ORG-Q4 LOCKED)
    pub native_language: LanguageId,                   // IDF_002 ref (REQUIRED V1)
    pub default_ideology_refs: Vec<IdeologyId>,        // IDF_005 ref (suggestions; may be empty V1)
    pub origin_pack_id: Option<OriginPackId>,          // V1+ optional ref to OriginPackDecl; V1 None typical (per ORG-Q9 LOCKED)

    pub assigned_at_turn: u64,
    pub schema_version: u32,
}
```

- T2 + RealityScoped
- One row per `(reality_id, actor_id)`; every actor MUST have origin row (except Synthetic forbidden V1)
- V1 immutable post-canonical-seed
- V1+ FF_001 / cultural pack extends additive fields

### 3.2 `OriginPackDecl` (V1+ enrichment; V1 schema slot only)

```rust
pub struct OriginPackDecl {
    pub origin_pack_id: OriginPackId,
    pub display_name: I18nBundle,
    pub default_birthplace_channel: Option<ChannelId>,
    pub default_native_language: LanguageId,
    pub default_ideology_refs: Vec<IdeologyId>,
    pub naming_convention: Option<NamingConventionDecl>,  // V1+ ORG-D3
    pub values_list: Vec<I18nBundle>,                     // V1+ ORG-D2
    pub canon_ref: Option<GlossaryEntityId>,
}
```

V1 ships schema. V1+ first OriginPackDecl shipped when first reality has author-defined cultural pack content.

---

## §4 Tier+scope (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `actor_origin` | T2 | T2 | Reality | ~0.1 per turn (UI tooltip + V1+ origin-conflict drift) | ~0 V1 (canonical seed only); V1+ rare | Per-actor; eventual consistency OK; V1 immutable |

---

## §5 DP primitives

### 5.1 Reads
- `dp::read_projection_reality::<ActorOrigin>(ctx, actor_id)` — UI tooltip + V1+ origin-conflict drift + IDF_002 default proficiency seed + IDF_005 default ideology seed
- `dp::read_reality_manifest(ctx).origin_packs` — V1+ when populated

### 5.2 Writes
- `dp::t2_write::<ActorOrigin>(ctx, actor_id, AssignOriginDelta { ... })` — canonical seed / PC creation / NPC spawn
- V1+ `dp::t2_write::<ActorOrigin>(ctx, actor_id, AdminOverrideDelta { ... })` — Forge admin

### 5.3 Subscriptions
- UI invalidation via DP-X

### 5.4 Capability
- `produce: [Derived]` + `write: actor_origin @ T2 @ reality` — IDF_004 owner
- `produce: [Administrative]` + sub-shape `Forge:EditOrigin` — Forge admin

---

## §6 Capability requirements

Standard pattern (matches IDF_001/002/003).

---

## §7 Subscribe pattern

UI invalidation via DP-X. NPC_002 reads at SceneRoster build.

---

## §8 Pattern choices

### 8.1 V1 minimal stub 4 fields (ORG-Q1 LOCKED)
Birthplace + lineage_id + native_language + default_ideology_refs. Sufficient for IDF_002 + IDF_005 wiring. Gender/age/appearance V1+ cosmetic.

### 8.2 OriginPackDecl V1 schema slot empty (ORG-Q2 + Q9 LOCKED)
Origin packs are content; V1 schema-only. Empty registry; first pack shipped V1+ when first reality needs cultural enrichment.

### 8.3 Strict cell-tier birthplace V1 (ORG-Q3 LOCKED)
ChannelId references PF_001 cell-tier place. V1+ extends to non-cell-tier (ORG-D10).

### 8.4 LineageId opaque tag V1 (ORG-Q4 LOCKED per POST-SURVEY-Q4)
**No parent/sibling refs in V1.** V1 just stores opaque ID for forensic. V1+ FF_001 Family Foundation designs full graph + dynasty. **FF_001 = first priority post-IDF closure** per POST-SURVEY-Q4.

### 8.5 default_ideology_refs at actor_origin V1 (ORG-Q5 LOCKED)
Storing direct refs avoids OriginPackDecl lookup V1. V1+ origin packs canonical via OriginPackDecl.default_ideology_refs; actor_origin.default_ideology_refs becomes per-actor override.

### 8.6 Strict immutable V1 (ORG-Q6 LOCKED)
With AdminOverride audit-only edit. Matches IDF_001/003.

### 8.7 Synthetic actor forbidden V1 (ORG-Q7 LOCKED)
Matches IDF_001/003/005 discipline.

### 8.8 V1 strict cross-reality immobility (ORG-Q8 LOCKED)
V2+ Heresy migration handles cross-reality remap.

### 8.9 Birthplace must exist at canonical seed time (ORG-Q10 LOCKED)
Channels declared in RealityManifest.places before actor refs; canonical seed validation enforces.

---

## §9 Failure-mode UX

| Reject reason | Stage | When | Vietnamese reject copy (I18nBundle) |
|---|---|---|---|
| `origin.unknown_native_language` | 0 schema | actor_origin.native_language not in RealityManifest.languages | "Ngôn ngữ mẹ đẻ không tồn tại trong thế giới này." |
| `origin.unknown_birthplace` | 0 schema | actor_origin.birthplace_channel not in RealityManifest.places (cell-tier) | "Nơi sinh không tồn tại trong thế giới này." |
| `origin.assignment_immutable` | 7 world-rule | V1 mutation rejected | "Nguồn gốc đã định và không thể thay đổi." |
| `origin.unknown_ideology_ref` | 0 schema | default_ideology_refs entry not in RealityManifest.ideologies | "Tư tưởng không tồn tại trong thế giới này." |

**`origin.*` V1 rule_id enumeration** (4 V1 rules):

1. `origin.unknown_native_language` — Stage 0
2. `origin.unknown_birthplace` — Stage 0
3. `origin.assignment_immutable` — Stage 7
4. `origin.unknown_ideology_ref` — Stage 0

V1+ reservations: `origin.lineage_graph_invalid` (V1+ FF_001); `origin.pack_not_in_registry` (V1+ when origin packs populated).

---

## §10 Cross-service handoff

```
1. Canonical seed: RealityBootstrapper assigns origin per actor with 4 fields.
2. IDF_002 default proficiency seed: reads actor_origin.native_language; pre-fills proficiency Native all axes (override per-actor for literacy slip).
3. IDF_005 default ideology seed: reads actor_origin.default_ideology_refs; auto-creates Light fervor stances (canonical seed may override).
4. UI tooltip: displays birthplace + native_language + ideology badges.
5. V1+ FF_001: attaches family graph to lineage_id existing tags.
```

---

## §11-§14 Sequences

### §11 Canonical seed (Wuxia bootstrap)

```
For each canonical actor:
  Determine origin from canonical actor declaration:
    LM01: birthplace=yen_vu_lau; lineage_id=Some(lineage_ly_clan); native_language=lang_quan_thoai; default_ideology_refs=[ideology_dao Light, ideology_phat Light, ideology_nho Moderate]
  dp::t2_write::<ActorOrigin>(ctx, LM01, AssignOriginDelta { ... }) → T1 Derived
  causal_refs=[reality_bootstrap_event_id]
  
Validate at Stage 0 schema:
  - birthplace_channel exists in RealityManifest.places ✓
  - native_language exists in RealityManifest.languages ✓
  - All default_ideology_refs in RealityManifest.ideologies ✓
```

### §12 IDF_002 default proficiency seed (cross-feature)

```
After IDF_004 actor_origin committed, IDF_002 owner-service reads:
  origin = read_projection_reality::<ActorOrigin>(LM01)
  origin.native_language = lang_quan_thoai
  
Auto-generate ProficiencyMatrix::native() for that language:
  proficiencies[lang_quan_thoai] = ProficiencyMatrix { read: Native, write: Native, speak: Native, listen: Native }

Override at canonical seed for literacy slip (per SPIKE_01 turn 5):
  Author override: LM01.proficiencies[lang_quan_thoai].read = None (rural illiterate peasant)
  LM01.proficiencies[lang_quan_thoai].write = None
```

### §13 IDF_005 default ideology seed (cross-feature)

```
After IDF_004 actor_origin committed, IDF_005 owner-service reads:
  origin = read_projection_reality::<ActorOrigin>(LM01)
  origin.default_ideology_refs = [ideology_dao, ideology_phat, ideology_nho]
  
Auto-create stances at Light fervor (per IDL-Q9 LOCKED):
  actor_ideology_stance.stances = [
    (ideology_dao, FervorLevel::Light),
    (ideology_phat, FervorLevel::Light),
    (ideology_nho, FervorLevel::Light),
  ]

Canonical seed may override fervor explicitly:
  Lý Minh: ideology_nho upgraded Light → Moderate (Confucian-leaning)
```

### §14 Forge admin override

Admin updates LM01.lineage_id from None → Some("lineage_ly_clan") (story-event reveals true family):
- EVT-T8 Administrative `Forge:EditOrigin { actor_id, edit_kind: UpdateLineage, before, after }`
- 3-write atomic transaction

---

## §15 Acceptance criteria

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-ORG-1** | LM01 bootstrap with 4-field stub | actor_origin row committed; UI tooltip "Yến Vũ Lâu / Quan thoại / Đạo + Phật + Nho" |
| **AC-ORG-2** | Tiểu Thúy NPC declared birthplace=yen_vu_lau | row committed |
| **AC-ORG-3** | Unknown LanguageId | Stage 0 reject `origin.unknown_native_language` |
| **AC-ORG-4** | Unknown ChannelId | Stage 0 reject `origin.unknown_birthplace` |
| **AC-ORG-5** | Mutation rejected V1 | `origin.assignment_immutable` |
| **AC-ORG-6** | IDF_002 default proficiency seed: LM01.native_language → IDF_002 auto-creates Native matrix; canonical override applies literacy slip | Cross-feature flow |
| **AC-ORG-7** | IDF_005 default ideology seed: LM01.default_ideology_refs → IDF_005 auto-creates Light fervor stances; canonical override applies | Cross-feature flow |
| **AC-ORG-8** | I18nBundle resolution (V1+ when origin packs populated) | (V1+ AC; empty registry V1) |

### 15.2 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-ORG-V1+1** | OriginPackDecl populated; PC selects origin_pack_id at creation | V1+ origin pack content |
| **AC-ORG-V1+2** | FF_001 attaches family graph to lineage_id | V1+ FF_001 ship |
| **AC-ORG-V1+3** | Birth event metadata (thiên kiêu chi tử markers per ORG-D11) | V1+ origin enrichment |

### 15.3 Failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-ORG-9** | Forge admin override LM01.lineage_id None → Some | EVT-T8 audit emitted; 3-write atomic |
| **AC-ORG-10** | Unknown IdeologyId in default_ideology_refs | Stage 0 reject `origin.unknown_ideology_ref` |

### 15.4 Status transition

- DRAFT → CANDIDATE-LOCK: boundary registered.
- CANDIDATE-LOCK → LOCK: all AC-ORG-1..10 V1-testable scenarios pass.

---

## §16 Boundary registrations

DRAFT promotion registers:

1. `_boundaries/01_feature_ownership_matrix.md`:
   - NEW row: `actor_origin` aggregate (T2/Reality, IDF_004 DRAFT)
   - EVT-T8: NEW `Forge:EditOrigin` (IDF_004 owns)
   - Stable-ID prefix: NEW `ORG-*` row
2. `_boundaries/02_extension_contracts.md`:
   - §1.4 `origin.*` namespace: 4 V1 rule_ids + 2 V1+ reservations
   - §2 RealityManifest: NEW `origin_packs: Vec<OriginPackDecl>` OPTIONAL V1
3. `_boundaries/99_changelog.md`: append IDF folder 10/15 entry

---

## §17 Deferrals

| ID | Item | Defer to |
|---|---|---|
| **ORG-D1** | Family graph (parents / siblings / children / lineages) | V1+ FF_001 Family Foundation |
| **ORG-D2** | cultural_tradition_pack (naming convention + values + arts + customs) | V1+ first reality with author cultural content |
| **ORG-D3** | Per-culture naming convention generator | V1+ origin enrichment |
| **ORG-D4** | Bloodline traits (Cultivator inherited spirit roots) | V1+ combat + cultivation feature |
| **ORG-D5** | Mixed cultural origin (PC born in Wuxia world to Modern parents) | V2+ |
| **ORG-D6** | Origin-driven default appearance | V1+ cosmetic (NOT IDF folder per IDF-FOLDER-Q4) |
| **ORG-D7** | Cultural ritual events | V1+ scheduler V1+30d |
| **ORG-D8** | Origin-conflict opinion modifier (rival-sect NPCs baseline -opinion) | V1+ NPC personality enrichment |
| **ORG-D9** | Origin lifecycle events (migration / exile / cultural drift) | V2+ |
| **ORG-D10** | Birthplace non-cell-tier ref (born in Country X) | V1+ when first author content needs |
| **ORG-D11** (Phase 0 survey) | Birth event metadata (thiên kiêu chi tử / born-during-eclipse / born-of-virgin / born-during-cataclysm — wuxia narrative tags) | V1+ origin enrichment when first reality content needs narrative birth markers; CK3 traits like "Born in the Purple" precedent |
| **ORG-D12** (Phase 0 survey) | FF_001 Family Foundation V1+ feature — first priority post-IDF closure (BEFORE PCS_001). Owns family_graph + dynasty + Birth/Marriage/Death/Divorce/Adoption events + family-driven opinion modifier (CK3 pattern) + inheritance-readiness for V1+ TIT_001 | V1+ FF_001 Family Foundation. **HIGH PRIORITY** post-IDF closure per POST-SURVEY-Q4 + folder _index.md V1+ roadmap. Wuxia content REQUIRES (sect lineage / family inheritance / dynasty politics). |

---

## §18 Cross-references

**Foundation tier:**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types)
- [`PF_001 §3.1 ChannelId`](../00_place/PF_001_place_foundation.md) — birthplace
- [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md)

**Sibling IDF:**
- [`IDF_001 Race`](IDF_001_race.md) — race may correlate with origin (V1+ ORG-D6)
- [`IDF_002 Language`](IDF_002_language.md) — native_language ref REQUIRED V1
- [`IDF_003 Personality`](IDF_003_personality.md) — independent V1
- [`IDF_005 Ideology`](IDF_005_ideology_concept.md) — default_ideology_refs ref

**Consumers:**
- Future PCS_001 — PC creation form
- NPC_001/`NPC_NNN` — NPC canonical seed
- V1+ NPC_002 — origin-conflict opinion drift (ORG-D8)
- **V1+ FF_001 Family Foundation — first priority post-IDF closure (ORG-D12)**

---

## §19 Implementation readiness checklist

Complete per EF_001 pattern. 10 V1-testable AC + 3 V1+ deferred. 12 deferrals (ORG-D1..D12).

**Phase 3 cleanup applied 2026-04-26 (IDF_004 commit 11/15):**
- S1.1 §2 OriginPackId + LineageId typed newtypes confirmed
- S1.2 §3.1 Synthetic actor exclusion confirmed (ORG-Q7 LOCKED)
- S2.1 §10 Cross-feature seed flow explicit (IDF_002 + IDF_005 read at canonical seed)
- S2.2 §15.4 LOCK criterion split
- S3.1 §17 ORG-D12 FF_001 priority signal confirmed (HIGH; first post-IDF closure)

**Status transition:** DRAFT 2026-04-26 (Phase 3 applied) → **CANDIDATE-LOCK** in next commit (12/15) → LOCK after AC-ORG-1..10 pass.
