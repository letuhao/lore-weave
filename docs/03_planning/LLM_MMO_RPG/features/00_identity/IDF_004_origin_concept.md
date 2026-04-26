# IDF_004 — Origin Foundation (CONCEPT)

> **Conversational name:** "Origin" (ORG). Tier 5 Actor Substrate Foundation feature owning per-actor `actor_origin` aggregate (V1 minimal stub: birthplace + lineage_id + native_language ref + default ideology refs) + `OriginPackDecl` reality-specific cultural pack (V1+ deep). Origin is **immutable birth-context**; distinct from IDF_005 Ideology which is **mutable belief stance**.
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** CONCEPT 2026-04-26 (Q-decisions LOCKED 2026-04-26 per market survey + user "A" confirmation; ready for DRAFT promotion)
> **Stable IDs:** `ORG-A*` axioms · `ORG-D*` deferrals · `ORG-Q*` open questions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md); [PF_001 §3.1 ChannelId](../00_place/PF_001_place_foundation.md) (birthplace ref); [IDF_001 Race](IDF_001_race_concept.md); [IDF_002 Language](IDF_002_language_concept.md) (native_language ref); [IDF_005 Ideology](IDF_005_ideology_concept.md) (default suggestions); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md).
> **Defers to:** PCS_001 (PC origin at creation); NPC_001/003 (NPC canonical seed origin); V1+ family graph + lineage; V1+ cultural_tradition_pack with naming convention + values + arts; V1+ multi-cultural origin (V2+).

---

## §1 Concept summary

Every actor (PC + NPC) has birth-context — birthplace + lineage + native culture + default ideology suggestions. V1 ships **minimal stub** (4 fields); V1+ enriches with cultural_tradition_pack, family graph, naming conventions, etc. The minimal V1 stub is enough to wire IDF_002 Language native_language ref + IDF_005 Ideology default refs; V1+ deep enrichment adds the cultural narrative substrate.

**V1 must-ship (minimal stub):**
- Per-actor `actor_origin` aggregate (T2/Reality scope) with 4 fields:
  - `birthplace: ChannelId` (cell-tier reference per PF_001)
  - `lineage_id: Option<LineageId>` (opaque; V1+ family graph populates)
  - `native_language: LanguageId` (per IDF_002)
  - `default_ideology_refs: Vec<IdeologyId>` (per IDF_005; suggestion only — actor's actual `actor_ideology_stance` may differ)
- Immutable post-canonical-seed V1
- RealityManifest extension `origin_packs: Vec<OriginPackDecl>` (V1+ enrichment; V1 OPTIONAL — empty Vec valid)
- 0 reality presets ship V1 (origin packs are content; V1 schema-only)

**V1+ deferred (cultural pack deep):**
- `OriginPackDecl` full schema (cultural_tradition_pack with naming convention + values + arts + customs)
- Family graph (FF_001 future — Family Foundation?)
- Bloodline traits (cultivator lineages with inherited spirit roots)
- Per-culture naming convention generator
- Mixed cultural origin (V2+)
- Origin-driven default appearance hints (V1+ cosmetic)
- Cultural ritual events (V1+ scheduler)

---

## §2 Domain concepts (proposed)

| Concept | Maps to | Notes |
|---|---|---|
| **OriginPackId** | Stable-ID newtype `String` (e.g., `origin_yen_vu_lau_villager`, `origin_eastern_sect_disciple`) | Opaque per-reality. V1+ closed-set declared in RealityManifest.origin_packs. V1 not actively used (empty registry). |
| **LineageId** | Stable-ID newtype `String` | Opaque V1; V1+ FF_001 Family Foundation populates with parent_lineage_ids + member_actor_ids graph. V1 actor.lineage_id is just a tag for forensic. |
| **OriginPackDecl** (V1+ enrichment) | Author-declared per-reality entry | display_name (I18nBundle) + default_birthplace_channel_ref + default_native_language + default_ideology_refs + naming_convention + values_list + canon_ref. V1 schema slot only; populated V1+. |
| **actor_origin** | T2 / Reality aggregate; per-(reality, actor_id) row | Generic for PC + NPC. V1 4-field stub; V1+ extends. |

**Cross-feature consumers:**
- IDF_002 Language — native_language ref informs default proficiency at canonical seed
- IDF_005 Ideology — default_ideology_refs seed `actor_ideology_stance` at canonical seed (suggestion; may diverge)
- PCS_001 (V1+) — PC creation form selects origin_pack_id (or null V1)
- NPC_001/003 — NPC canonical seed declares origin
- PF_001 — birthplace cell-channel ref
- V1+ NPC_002 priority — origin-conflict opinion modifier (NPC from rival sect → -opinion)

---

## §3 Aggregate inventory (proposed)

### 3.1 `actor_origin` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_origin", tier = "T2", scope = "reality")]
pub struct ActorOrigin {
    pub reality_id: RealityId,
    pub actor_id: ActorId,

    // V1 minimal stub
    pub birthplace_channel: Option<ChannelId>,         // PF_001 cell-tier; None for "unknown / canonical seed without place"
    pub lineage_id: Option<LineageId>,                 // V1+ FF_001 populates; V1 opaque tag
    pub native_language: LanguageId,                   // IDF_002 ref (REQUIRED V1)
    pub default_ideology_refs: Vec<IdeologyId>,        // IDF_005 ref (suggestions; may be empty V1)
    pub origin_pack_id: Option<OriginPackId>,          // V1+ optional ref to OriginPackDecl; V1 None typical

    pub assigned_at_turn: u64,
    pub schema_version: u32,
}
```

- T2 + RealityScoped
- One row per `(reality_id, actor_id)` (every actor MUST have origin row even if all fields min)
- V1 immutable post-canonical-seed
- V1+ FF_001 / V1+ deep cultural pack extends additive fields

### 3.2 `OriginPackDecl` (V1+ enrichment; V1 schema slot only)

```rust
pub struct OriginPackDecl {
    pub origin_pack_id: OriginPackId,
    pub display_name: I18nBundle,
    pub default_birthplace_channel: Option<ChannelId>,
    pub default_native_language: LanguageId,           // IDF_002 ref
    pub default_ideology_refs: Vec<IdeologyId>,        // IDF_005 ref
    // V1+ deep
    pub naming_convention: Option<NamingConventionDecl>,  // V1+
    pub values_list: Vec<I18nBundle>,                     // V1+ cultural values
    pub canon_ref: Option<GlossaryEntityId>,
}
```

V1 ships schema. V1+ first OriginPackDecl shipped when first reality has author-defined cultural pack content.

---

## §4 Tier+scope (DP-R2 — proposed)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `actor_origin` | T2 | T2 | Reality | ~0.1 per turn (UI tooltip + V1+ origin-conflict drift) | ~0 per turn V1 (canonical seed only); V1+ rare (bio events) | Per-actor across reality lifetime; eventual consistency OK; V1 immutable. |

---

## §5 Cross-feature integration (proposed)

### 5.1 IDF_002 Language native default

PC creation: pre-fills `actor_language_proficiency.proficiencies[native_language] = ProficiencyMatrix::native()` (Native across all 4 axes — Read may be Basic/None for illiterate origins).

V1 simplification: ProficiencyMatrix::native() = Native/Native/Native/Native; literacy slip overrides explicitly per actor (LM01 has Cổ ngữ Read=None despite Quan thoại Native).

### 5.2 IDF_005 Ideology default seeding

Origin pack proposes default ideologies; actor's `actor_ideology_stance` may diverge per personal choice/canonical seed. V1: actor_origin.default_ideology_refs is ADVISORY only — IDF_005 actor_ideology_stance is the canonical truth.

### 5.3 PF_001 birthplace ref

birthplace_channel: ChannelId (cell-tier per PF_001). Validation at canonical seed: ChannelId MUST exist in reality's RealityManifest.places (cell-tier place declared).

V1+: birthplace may also reference non-cell-tier (born in Country X without specific cell) — V1 strict cell-tier only.

### 5.4 Reject UX (origin.* namespace — proposed V1)

| rule_id | Stage | When |
|---|---|---|
| `origin.unknown_native_language` | 0 schema | actor_origin.native_language not in RealityManifest.languages |
| `origin.unknown_birthplace` | 0 schema | actor_origin.birthplace_channel not in RealityManifest.places (cell-tier) |
| `origin.assignment_immutable` | 7 world-rule | V1 attempt to mutate actor_origin rejected |
| `origin.unknown_ideology_ref` | 0 schema | default_ideology_refs entry not in RealityManifest.ideologies |

V1+ reservations: `origin.lineage_graph_invalid` (V1+ FF_001); `origin.pack_not_in_registry` (V1+ when origin_packs registry populated).

---

## §6 RealityManifest extension (proposed)

```rust
pub struct RealityManifest {
    // ... existing fields ...
    pub origin_packs: Vec<OriginPackDecl>,    // NEW V1+ from IDF_004 (V1 OPTIONAL — empty Vec valid)
}
```

OPTIONAL V1 (empty Vec valid; V1+ enrichment populates).

V1: schema slot present so V1+ doesn't need migration. `actor_origin.origin_pack_id: Option<OriginPackId>` always None V1.

---

## §7 V1 acceptance criteria (preliminary)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-ORG-1** | LM01 created with birthplace=yen_vu_lau, native_language=lang_quan_thoai, default_ideology_refs=[ideology_dao] | actor_origin row committed; UI tooltip shows "Yến Vũ Lâu / Quan thoại / Đạo" |
| **AC-ORG-2** | NPC tieu_thuy declared at canonical seed with origin: birthplace=yen_vu_lau, native_language=quan_thoai, default_ideology_refs=[] | row committed |
| **AC-ORG-3** | Actor created with native_language=`lang_unknown` (not in RealityManifest) | rejected with `origin.unknown_native_language` |
| **AC-ORG-4** | Actor created with birthplace=channel_id_outside_reality | rejected with `origin.unknown_birthplace` |
| **AC-ORG-5** | Mutate actor_origin V1 | rejected with `origin.assignment_immutable` |
| **AC-ORG-6** | IDF_002 reads actor_origin.native_language for default proficiency seed | LM01.proficiencies["lang_quan_thoai"] = Native (all axes) at canonical seed; Cổ ngữ override explicit |
| **AC-ORG-7** | IDF_005 reads actor_origin.default_ideology_refs as suggestion at canonical seed | LM01.ideology_stance defaults to [(ideology_dao, FervorLevel::Light)] but may be overridden |
| **AC-ORG-8** | I18nBundle resolves origin_pack display_name (V1+ when populated) | (V1+ acceptance — origin_packs registry empty V1) |

---

## §8 Open questions (CONCEPT — user confirm before DRAFT)

| ID | Question | Default proposal |
|---|---|---|
| **ORG-Q1** | V1 scope — minimal stub (4 fields current) vs slightly richer (add gender + age + appearance hints)? | **Minimal stub V1** — 4 fields sufficient for IDF_002 + IDF_005 wiring; gender/age/appearance V1+ cosmetic enrichment |
| **ORG-Q2** | OriginPackDecl V1 — schema slot empty (current) vs ship 2-3 example packs for SPIKE_01? | **Schema slot empty V1** — origin packs are content (Wuxia: Yến Vũ Lâu villager / Đông Hải sect disciple / etc.) — content authoring V1+; V1 schema-only |
| **ORG-Q3** | birthplace ref — strict cell-tier ChannelId (current) vs allow non-cell-tier? | **Strict cell-tier V1** — V1+ extends to non-cell ("born in Country X without specific village") |
| **ORG-Q4** | LineageId — opaque tag V1 (current) vs structured graph V1? vs mini-stub with parent/sibling refs? | ✅ **LOCKED 2026-04-26 per POST-SURVEY-Q4:** **Opaque tag V1 ONLY** (no parent_actor_id / mother_actor_id / sibling refs in V1). All family graph access deferred to V1+ FF_001 Family Foundation. Mini-stub with parent refs WAS considered + rejected — partial design creates refactor pain when FF_001 ships. FF_001 is **first priority post-IDF closure** (before PCS_001) per `_index.md` V1+ roadmap. |
| **ORG-Q5** | default_ideology_refs at actor_origin (current) vs at OriginPackDecl only (look up via origin_pack_id)? | **At actor_origin V1** — V1 origin_pack_id often None; storing direct refs avoids lookup. V1+ when origin packs populated, OriginPackDecl.default_ideology_refs is canonical and actor_origin.default_ideology_refs is per-actor override. |
| **ORG-Q6** | Mutation V1 — strict immutable (current) vs allow Admin override V1? | **Strict immutable** with AdminOverride audit-only (matches IDF_001 RAC-Q1 pattern) |
| **ORG-Q7** | actor_origin REQUIRED for every actor (current) vs OPTIONAL for Synthetic actors? | **Forbidden for Synthetic V1** — Synthetic actors don't have origin (matches IDF_003 PRS-Q11) |
| **ORG-Q8** | Cross-reality origin migration — V1 strict (PC bound to one reality) vs V2+ remap policy? | **V1 strict** — same as IDF_001 RAC-Q7; V2+ Heresy migration remaps |
| **ORG-Q9** | Origin pack vs origin minimal stub — V1 ships actor_origin only (no OriginPackDecl populated) (current) vs ship 1 example pack to validate schema? | **No populated packs V1** — minimal stub validates by AC-ORG-1..7 sufficiently; first pack shipped V1+ when first reality needs cultural enrichment |
| **ORG-Q10** | Birthplace must exist at canonical seed time vs may reference future-dynamic-spawned cell? | **Must exist at canonical seed** V1 — birthplace channels declared in RealityManifest.places before actors reference them |

---

## §9 Deferrals (V1+ landing point)

| ID | Item | Defer to |
|---|---|---|
| **ORG-D1** | Family graph (parents / siblings / children / lineages) | Future FF_001 Family Foundation feature |
| **ORG-D2** | cultural_tradition_pack (naming convention + values + arts + customs) | V1+ first reality with author cultural content |
| **ORG-D3** | Per-culture naming convention generator (Wuxia Daoist names: 李道明 / Western names: John Smith) | V1+ origin enrichment |
| **ORG-D4** | Bloodline traits (Cultivator inherited spirit roots) | V1+ combat + cultivation feature |
| **ORG-D5** | Mixed cultural origin (PC born in Wuxia world to Modern parents — exotic V2+) | V2+ |
| **ORG-D6** | Origin-driven default appearance | V1+ cosmetic / IDF_005 Appearance V1+ feature |
| **ORG-D7** | Cultural ritual events (annual festivals, rites of passage) | V1+ scheduler V1+30d |
| **ORG-D8** | Origin-conflict opinion modifier (rival-sect NPCs baseline -opinion) | V1+ NPC personality enrichment |
| **ORG-D9** | Origin lifecycle events (migration / exile / cultural drift) | V2+ |
| **ORG-D10** | Birthplace non-cell-tier ref (born in Country X) | V1+ when first author content needs |
| **ORG-D11** (NEW Phase 0 survey) | Birth event metadata — wuxia narrative tags like "thiên kiêu chi tử" (heavenly-talented offspring), born-during-eclipse, born-of-virgin, born-during-cataclysm | V1+ origin enrichment when first reality content needs narrative birth markers; CK3 traits like "Born in the Purple" precedent |
| **ORG-D12** (NEW Phase 0 survey — V1+ FF_001 priority signal) | FF_001 Family Foundation V1+ feature — first priority post-IDF closure (BEFORE PCS_001). Owns: family_graph aggregate (parents/siblings/children/cousins/dynasty); BirthEvent / MarriageEvent / DeathEvent / DivorceEvent / AdoptionEvent log; family-driven opinion modifier (CK3 pattern); inheritance-readiness for V1+ TIT_001 Title Foundation | V1+ FF_001 Family Foundation feature spec — per POST-SURVEY-Q4 + `_index.md` V1+ roadmap. Wuxia content REQUIRES this (sect lineage / family inheritance / dynasty politics). Locked HIGH priority. |

---

## §10 Cross-references

**Foundation tier:**
- [`EF_001`](../00_entity/EF_001_entity_foundation.md) §5.1 — ActorId
- [`PF_001`](../00_place/PF_001_place_foundation.md) §3.1 — ChannelId for birthplace
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) §2.3 — I18nBundle

**Sibling IDF:**
- [`IDF_001 Race`](IDF_001_race_concept.md) — race may correlate with origin (Wuxia Cultivators typically from sect-affiliated origins) but independent V1
- [`IDF_002 Language`](IDF_002_language_concept.md) — native_language ref REQUIRED V1
- [`IDF_003 Personality`](IDF_003_personality_concept.md) — independent V1; V1+ origin pack may suggest default archetype
- [`IDF_005 Ideology`](IDF_005_ideology_concept.md) — default_ideology_refs suggestion ref

**Consumers:**
- Future PCS_001 — PC creation form
- NPC_001/003 — NPC canonical seed
- V1+ NPC_002 — origin-conflict opinion drift (ORG-D8)

**Boundaries (DRAFT registers):**
- `_boundaries/01_feature_ownership_matrix.md` — `actor_origin` aggregate
- `_boundaries/02_extension_contracts.md` §1.4 — `origin.*` namespace (4 V1 rules + 2 V1+ reservations)
- `_boundaries/02_extension_contracts.md` §2 RealityManifest — `origin_packs` extension (OPTIONAL V1)

---

## §11 CONCEPT → DRAFT promotion checklist

Same pattern as IDF_001/002/003. Boundary registrations: `actor_origin` aggregate; `origin.*` namespace (4 V1 rules); `origin_packs: Vec<OriginPackDecl>` RealityManifest extension (V1 OPTIONAL); Stable-ID prefix `ORG-*`.
