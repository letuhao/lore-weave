# FAC_001 Faction Foundation — Reference Games Survey

> **Purpose:** Survey faction / sect / clan / guild systems in established games. Inform FAC_001 V1 scope decisions (Q1-Q10 in `00_CONCEPT_NOTES.md` §5).
>
> **Status:** DRAFT 2026-04-26 — Phase 0 companion to FAC_001 concept-notes. User may supplement with additional reference materials.
>
> **Heavy Wuxia weighting** — primary V1 use case; survey emphasizes Sands of Salzaar / Path of Wuxia / Sword & Fairy / xianxia novel mechanics. CK3 + Bannerlord + VtM secondary references for grand-strategy + faction politics.

---

## §1 — Methodology

10 reference systems surveyed across 3 priority groups:

**Priority 1 (Wuxia primary V1 use case):**
1. Sands of Salzaar
2. Path of Wuxia / Sword & Fairy
3. Wuxia novel mechanics (Tiên Nghịch / Phong Vân / Kim Dung canon)

**Priority 2 (faction-politics references):**
4. Crusader Kings 3 (vassalage + court + estates)
5. Bannerlord (clan + faction + lord)
6. Vampire: The Masquerade (clans + sects)
7. Total War: Three Kingdoms (sworn brotherhood + faction)

**Priority 3 (additional context):**
8. Europa Universalis IV (estates + religion-as-faction)
9. Stellaris (factions within empire)
10. D&D 5e + Pathfinder (factions: Lords Alliance / Harpers / Zhentarim / etc.)

---

## §2 — Wuxia primary references (V1 priority)

### §2.1 Sands of Salzaar — sect mechanics

**Sect system:**
- ~10 declared sects with distinct ideology + cultivation method binding
- Player joins via story-event or recruitment
- Sect grants: cultivation method (V1+ CULT_001 binding); reputation; sect-leader missions
- Sect-leader role with succession on death

**Sect-faction relations:**
- Static rivalry table (Sect A hostile to Sect B; Sect C neutral; Sect D allied)
- Cross-sect combat triggers reputation drift
- Wulin Meng (martial alliance) = parent faction grouping multiple sects

**Master-disciple:**
- Sect master accepts disciple via formal ceremony
- Disciple inherits cultivation method
- Sect-leader succession via heir-disciple ranking

**Mapping to FAC_001 V1:**

| Sands of Salzaar feature | FAC_001 V1 mapping | Notes |
|---|---|---|
| Sect declarative entity | ✅ V1 (faction aggregate per Q1 (A)) | `faction` aggregate sparse storage |
| Per-actor sect membership | ✅ V1 (actor_faction_membership) | Single-faction V1 (Q2 (A)) matches wuxia common |
| Cultivation method binding | ❌ V1+ CULT_001 | FAC_001 V1 schema-present hook only |
| Sect-faction static rivalry | ⚠️ V1 default_relations (per Q5 (A)) | Per-faction HashMap<FactionId, RelationStance> at canonical seed |
| Master-disciple chain | ✅ V1 (master_actor_id field per Q6 (A)) | Single field; traversal V1+ |
| Sect-leader role | ✅ V1 (role enum or named role per Q3) | Q3 LOCKED decision pending |
| Wulin Meng parent grouping | ❌ V1+ parent_faction_id | V1+ enrichment |

### §2.2 Path of Wuxia / Sword & Fairy — sect role hierarchy

**Sect role hierarchy:**
- Sect Master (掌门 zhǎngmén) — leader
- Elder (长老 zhǎnglǎo) — senior member
- Inner Disciple (内门弟子 nèimén dìzǐ) — core disciple
- Outer Disciple (外门弟子 wàimén dìzǐ) — peripheral disciple
- Recruit (普通弟子 pǔtōng dìzǐ) — V1+ junior

**Rank ordering:**
- "Đại sư huynh" (大师兄 dà shīxiōng) — eldest disciple
- "Nhị sư đệ" (二师弟 èr shīdì) — second-younger disciple
- Numeric rank derived from join-order timestamp

**Mapping to FAC_001 V1:**

| Path of Wuxia feature | FAC_001 V1 mapping | Notes |
|---|---|---|
| 5-rank role hierarchy | ⚠️ Q3 — closed-set (B) vs author-declared (A) | Wuxia-specific role taxonomy suggests author-declared |
| "Đại sư huynh" / "Nhị sư đệ" named rank | ⚠️ Q4 — named (B) vs numeric (A) | Wuxia narrative needs named ranks |
| Join-order timestamp ranking | ✅ V1 (rank derived from membership.joined_at_turn) | |

### §2.3 Wuxia novel mechanics (canon)

**Tiên Nghịch / Phong Vân / Kim Dung references:**

- Sect = ideology binding common (Đạo cốc requires Đạo Devout; Phật tự requires Phật Devout; Ma tông requires animism or deviant Đạo)
- Sect cultivation method UNIQUELY identifies sect ("Quỳ Hoa Bảo Điển" = unique to specific sect)
- Sect rivalry endemic (5 thousand years of wuxia precedent: Đạo vs Ma; Trung Nguyên vs Tây Vực; Chính phái vs Tà phái)
- Sect-master succession: heir-disciple ranks ("Đại sư huynh" inherits unless story-event)
- Sect defection = MAJOR narrative event (months/years; ritual ceremony; opinion penalty all sect members)

**Mapping to FAC_001 V1:**

| Wuxia canon feature | FAC_001 V1 mapping | Notes |
|---|---|---|
| Sect ideology binding | ✅ V1 (FactionDecl.requires_ideology field; resolves IDL-D2 LOCKED) | Validates at join event |
| Sect cultivation method binding | ❌ V1+ CULT_001 | FAC_001 V1 schema-present hook only |
| Static sect rivalry | ✅ V1 (default_relations per Q5 (A)) | Static at canonical seed |
| Heir-disciple succession | ❌ V1+ TIT_001 reads sect_leader role + master_actor_id | FAC_001 V1 doesn't ship succession rules |
| Sect defection event | ⚠️ V1+ runtime event | V1 canonical seed only; V1+ defection ritual |

---

## §3 — Faction-politics references (Priority 2)

### §3.1 Crusader Kings 3 — vassalage + court + estates

**Vassalage system:**
- Per-character vassal tier (count → duke → king → emperor)
- Vassalage = liege-vassal hierarchy
- Distinct from blood family (CK3 dynasty separate)

**Court system:**
- Each character's court has positions (chancellor / steward / marshal / spymaster / chaplain)
- Court membership = political influence
- Distinct from faction-as-organization

**Estates (DLC):**
- Estate = social class (clergy / nobility / burghers / commoners)
- Estate has loyalty + rights
- Country-level mechanic, not character-level

**Mapping to FAC_001:**

CK3 separates VASSALAGE from FACTION:
- Vassalage = liege-vassal hierarchy (LoreWeave equivalent: V1+ TIT_001 + V1+ CRT_001 Court Foundation)
- Faction = political coalition within realm (LoreWeave: FAC_001-equivalent for Modern reality)
- LoreWeave wuxia primary: sect = faction-equivalent (single membership common)

**FAC_001 V1 takes only the per-actor membership pattern** (CK3's faction-membership-with-role); leaves vassalage to V1+ TIT_001.

### §3.2 Bannerlord — clan tier + faction + lord

**Clan system:**
- Clan = retinue (family + companions); not pure blood (matches FF_001 + FAC_001 join)
- Clan tier 0-6 (party + lord position capacity)
- Clan owns settlements / armies / parties

**Faction:**
- Major faction (Empire / Khuzait / Vlandia / Battania / Sturgia / Aserai) — country-level
- Clan can be vassal to faction OR independent
- Faction-faction war/peace dynamic

**Lord position:**
- Lord = noble title (V1+ TIT_001 in LoreWeave)
- Distinct from clan / faction membership

**Mapping to FAC_001:**

Bannerlord's clan = FF_001 (blood) + FAC_001 (companion retinue) + V1+ TIT_001 (lord title) join. LoreWeave's separation is cleaner than Bannerlord's hybrid.

### §3.3 Vampire: The Masquerade — clans + sects

**Clan system (13 V1):**
- Clan = bloodline-quasi-family (member shares Discipline genetic-quasi inheritance)
- Sire (parent-vampire) determines clan
- Clan separates from biological family entirely (vampire's mortal family not relevant to clan)

**Sect system:**
- Sect = political alignment (Camarilla / Sabbat / Anarchs / Independents)
- Sect membership orthogonal to clan
- Per-vampire: 1 clan (immutable post-Embrace) + 1 sect (mutable allegiance)

**Mapping to FAC_001:**

VtM's separation of clan (bloodline-quasi) from sect (political alignment) is the cleanest reference for FAC_001 multi-membership pattern:
- Clan = FF_001 + dynasty (LoreWeave: family/dynasty)
- Sect = FAC_001 (political/sect membership)

VtM validates **multi-faction membership V1+ ENRICHMENT** (Q2 (B)+) — V1 single faction is wuxia common; V1+ multi may be needed for VtM-style dual membership.

### §3.4 Total War: Three Kingdoms — sworn brotherhood

**Sworn brotherhood:**
- Peach Garden Oath (Liu Bei + Guan Yu + Zhang Fei)
- Mechanically: bonded relationship + shared death triggers
- Cross-faction (sworn brothers may belong to different factions)
- 3-way max V1; V1+ may extend

**Mapping to FAC_001:**

Sworn brotherhood is **PER FF_001 Q4 LOCKED (FF-D6)**: lives in V1+ FAC_001 (Q7 LOCKED decision pending: within FAC_001 sworn_bond_id field OR separate sworn_bonds aggregate).

Total War 3K precedent confirms sworn-brotherhood-as-mechanic V1+ at minimum.

---

## §4 — Additional context (Priority 3)

### §4.1 Europa Universalis IV — estates + religion-as-faction

**Estates:**
- Per-country Estate loyalty + influence (Burghers / Nobility / Clergy / etc.)
- Country-level mechanic; not actor-level

**Religion-as-faction:**
- Country religion = mass faction (millions of faceless members)
- Player-level: religion gating diplomatic options

**Mapping:** EU4 estates are country-level; LoreWeave actor-level. Religion-as-faction is partially covered by FAC_001 ideology binding (Q5 / IDL-D2 RESOLVED here).

### §4.2 Stellaris — factions within empire

**Factions:**
- Empire-internal political factions (e.g., "Materialist faction" / "Xenophile faction")
- Pop-level membership (not character-level)
- Faction influence affects empire policies

**Mapping:** Stellaris factions = different scope (population-level); FAC_001 actor-level. Limited reference value.

### §4.3 D&D 5e / Pathfinder — faction allegiance system

**5e faction system:**
- 5 V1 factions: Lords Alliance / Harpers / Zhentarim / Order of the Gauntlet / Emerald Enclave
- PC may have multiple faction memberships (rare)
- Faction grants reputation rank (1-5) + access to features
- Mostly narrative, mechanically minimal

**Mapping to FAC_001 V1:**

D&D faction system maps directly:
- 5 V1 factions = closed-set per-reality (matches FAC_001 RealityManifest.canonical_factions REQUIRED V1)
- Reputation rank 1-5 = numeric rank V1 (Q4 (A))
- Multiple faction memberships = multi-faction V1 (Q2 (B))

D&D validates **simple V1 minimal scope** (5 factions / numeric rank / multi-faction allowed).

---

## §5 — Cross-system pattern observations

### §5.1 Pattern: separate faction from family + title

**All references** with both family + faction systems explicitly separate:
- VtM clan (bloodline-quasi-family) + sect (political faction)
- CK3 dynasty + vassalage + estate
- Bannerlord clan-retinue + major-faction + lord-title
- Total War 3K family + sworn brotherhood + faction

**Validates LoreWeave 3-way separation:**
- FF_001 = biological + adoption (blood)
- FAC_001 = sect / order / clan-retinue / guild (faction membership)
- V1+ TIT_001 = noble / sect-leader / lord title (rank)

### §5.2 Pattern: ideology binding for sects

**Wuxia + VtM + EU4** all bind faction to ideology:
- Wuxia: sect requires ideology stance (Đạo Devout / Phật Devout / etc.)
- VtM: sect (Camarilla / Sabbat) has implicit ideology (humanity vs anti-humanity)
- EU4: religion = mass-level faction with ideology
- D&D 5e: factions have alignments (Lords Alliance lawful good leaning)

**Validates Q5 (A) static default_relations + ideology binding at canonical seed.**

### §5.3 Pattern: master-disciple as faction role

**Wuxia + sword & fairy + sands of salzaar** all model master-disciple as RANK within sect:
- Master = sect master role + ranked highest
- Disciple = inner/outer disciple role + numeric rank by joining order
- Master-disciple chain via master_actor_id ref

**Validates Q6 (A) `master_actor_id: Option<ActorId>` field on actor_faction_membership.**

### §5.4 Pattern: V1 single faction; V1+ multi

**Wuxia common = single sect** (deep loyalty); **VtM = dual-membership** (clan + sect orthogonal); **D&D = multi-faction common**.

LoreWeave V1 prioritizes Wuxia → recommends Q2 (A) single faction V1; V1+ extends multi via additive Vec.

### §5.5 Pattern: closed-set per-reality + author-declared

**All references** declare faction list per-reality / per-game-world (closed-set discipline):
- CK3: dynasties + vassal hierarchy declared per scenario
- Bannerlord: 6 major factions declared
- VtM: 13 clans + 4 sects (canon) closed-set
- D&D 5e: 5 factions per setting
- Wuxia: per-novel sect list canon

**Validates RealityManifest.canonical_factions REQUIRED V1 + closed-set per-reality.**

---

## §6 — Recommendations summary

Based on §2-§5 survey, recommendations for FAC_001 Q1-Q10:

| Q | Question | Recommendation | Reasoning |
|---|---|---|---|
| **Q1** | Aggregate model | **(A) 2 aggregates** (faction + actor_faction_membership) | V1+ TIT_001 + V1+ REP_001 + V1+ DIPL_001 consumer support; matches IDF + FF_001 pattern |
| **Q2** | Multi-faction membership V1 | **(A) Single faction V1**; multi V1+ enrichment | Wuxia primary use case = 1 sect per actor; V1+ Vec extension via additive |
| **Q3** | Role taxonomy | **(A) Author-declared per-faction** | Wuxia role hierarchy is sect-specific (Path of Wuxia 5-rank); generic enum too narrow |
| **Q4** | Rank V1 | **(C) Both numeric + named V1** | Numeric rank derived from join-order; named rank ("Đại sư huynh") for wuxia narrative |
| **Q5** | Faction-faction relations V1 | **(A) V1 static default_relations** (HashMap<FactionId, RelationStance>); V1+ DIPL_001 dynamic | Static rivalry at canonical seed enables opinion modifier baseline; dynamic V1+ DIPL_001 |
| **Q6** | Master-disciple V1 | **(A) `master_actor_id: Option<ActorId>`** field on actor_faction_membership | V1 simple; sect lineage chain via traversal V1+; matches Sands of Salzaar pattern |
| **Q7** | Sworn brotherhood V1 | **(A) Within FAC_001 as `sworn_bond_id`** field on actor_faction_membership | V1 lightweight; multi-actor bond via shared sworn_bond_id; matches Total War 3K precedent |
| **Q8** | Cross-reality migration | **(A) V1 strict** | Inherits IDF + FF_001 discipline |
| **Q9** | Faction-driven Lex axiom V1 | **(A) Schema-present hook V1+** | AxiomDecl.requires_faction reserved; V1 always None; matches IDF_001 / IDF_005 pattern |
| **Q10** | Synthetic actor membership | **(A) Forbidden V1** | Matches IDF + FF_001 discipline |

### Survey-derived V1 quantitative scope

- **2 aggregates V1**: `faction` (T2/Reality sparse) + `actor_faction_membership` (T2/Reality; per-(reality, actor_id) — single faction V1)
- **Author-declared role taxonomy** per FactionDecl: `Vec<RoleDecl>` (e.g., sect_master / elder / inner_disciple / outer_disciple)
- **Both numeric (u16) + named (Option<String>) rank** within faction
- **Static default_relations** per faction at canonical seed
- **`master_actor_id: Option<ActorId>`** field for sect lineage chain
- **`sworn_bond_id: Option<SwornBondId>`** field for sworn brotherhood
- **2 RealityManifest extensions**: `canonical_factions` + `canonical_faction_memberships` REQUIRED V1
- **8 V1 reject rule_ids in `faction.*` namespace** (TBD detailed at DRAFT)
- **3 EVT-T8 Forge sub-shapes**: `Forge:RegisterFaction` + `Forge:EditFaction` + `Forge:EditFactionMembership`
- **2 EVT-T4 System sub-types**: `FactionBorn` (per-faction at canonical seed) + `FactionMembershipBorn` (per-actor at canonical seed)
- **EVT-T3 Derived events**: JoinFaction / LeaveFaction / ChangeRole / ChangeRank / SetMaster / SetSwornBond
- **~700-900 line DRAFT spec estimate**
- **10 V1 AC + 4 V1+ deferred**
- **12-15 deferrals (FAC-D1..D15)**:
  - FAC-D1: Multi-faction membership V1+ (additive Vec)
  - FAC-D2: Sect cultivation method binding (V1+ CULT_001)
  - FAC-D3: Marriage as faction alliance (V1+ DIPL_001)
  - FAC-D4: Faction-faction dynamic relations (V1+ DIPL_001)
  - FAC-D5: Wulin Meng parent_faction_id (V1+ enrichment)
  - FAC-D6: Sect succession rules (V1+ TIT_001)
  - FAC-D7: Per-(actor, faction) reputation projection (V1+ REP_001)
  - FAC-D8: Faction-driven Lex axiom gate active (V1+ first axiom uses)
  - FAC-D9: Cross-reality faction migration (V2+ Heresy)
  - FAC-D10: Sworn brotherhood as separate aggregate (V1+ if V1 field-on-membership insufficient)
  - FAC-D11: V1+ runtime defection / join / leave event flows (V1 canonical seed only)
  - FAC-D12: Faction cultivation method registry (V1+ CULT_001)
  - FAC-D13: Faction treasury / clan-shared inventory (V2+ RES_001)
  - FAC-D14: Hierarchical faction (parent_faction_id for cadet branches)
  - FAC-D15: Faction-conflict opinion modifier across non-member NPCs (V1+ NPC_002 enrichment)

---

## §7 — Status

- **Created:** 2026-04-26 by main session (commit this turn alongside `00_CONCEPT_NOTES.md`)
- **Phase:** Reference survey complete — recommendations §6 form basis for Q1-Q10 deep-dive
- **Lock state:** `_boundaries/_LOCK.md` held by PROG_001 agent (parallel session)
- **Next action:** User reviews recommendations + provides additional reference materials if any → Q-deep-dive batch (similar to FF_001 + RES_001 pattern; 6-10 turns) → DRAFT promotion when lock free

---

## §8 — Cross-references

**Foundation tier:**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types)
- [`IDF_005 IDL-D2`](../00_identity/IDF_005_ideology.md) — sect membership V1+ FAC_001 priority signal
- [`FF_001 Q4 + FF-D6 + FF-D7`](../00_family/FF_001_family_foundation.md) — sect/master-disciple/sworn V1+ FAC_001 priority signal

**Companion concept-notes:**
- [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) — user framing + 12-dim gap + Q1-Q10

**Prior art:**
- [`features/00_resource/01_REFERENCE_GAMES_SURVEY.md`](../00_resource/01_REFERENCE_GAMES_SURVEY.md) — RES_001 reference survey precedent
- [`features/00_family/01_REFERENCE_GAMES_SURVEY.md`](../00_family/01_REFERENCE_GAMES_SURVEY.md) — FF_001 reference survey precedent
- [`features/00_identity/_research_character_systems_market_survey.md`](../00_identity/_research_character_systems_market_survey.md) §6.2 — Wuxia sect system reference (Sands of Salzaar)
