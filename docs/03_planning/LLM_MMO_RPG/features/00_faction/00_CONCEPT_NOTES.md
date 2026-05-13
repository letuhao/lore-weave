# FAC_001 Faction Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-26 — captures user framing (wuxia priority + V1+ deferral resolution from FF_001 + IDF_005) + 12-dimension gap analysis + 10 critical scope questions Q1-Q10. Awaits user reference materials review + Q-deep-dive before DRAFT promotion.
>
> **Purpose:** Capture brainstorm + gap analysis + open questions for FAC_001 Faction Foundation. NOT a design doc; the seed material for the eventual `FAC_001_faction_foundation.md` design.
>
> **Promotion gate:** When (a) Q1-Q10 locked via deep-dive discussion, (b) `_boundaries/_LOCK.md` free → main session drafts `FAC_001_faction_foundation.md` with locked V1 scope, registers ownership, creates catalog file.

---

## §1 — User framing + priority signal (2026-04-26)

User direction 2026-04-26 picked Option C (FAC_001 deep-dive next; all dependencies CANDIDATE-LOCK — IDF folder + FF_001 closed).

### Inherited V1+ deferral signals

1. **FF_001 Q4 LOCKED + FF-D6 + FF-D7** (commit 2ffd9b1):
   > FF_001 = biological + adoption only. **V1+ FAC_001 owns sect/master-disciple/sworn brotherhood relationships** (rank/role within sect). Wuxia narrative quasi-family treated mechanically as sect membership.

2. **IDF_005 IDL-D2 LOCKED**:
   > Sect / order / giáo phái membership (faction system) → V1+ FAC_001 Faction Foundation

3. **IDF folder closure roadmap** (50d65fa): "FAC_001 = priority 5 post-IDF closure" (after IDF folder + FF_001 + PCS_001 + NPC_NNN)

### User pick (Option C from prior turn) reasoning

User chose FAC_001 over PCS_001/NPC_NNN because:
- All dependencies CANDIDATE-LOCK now (IDF + FF_001 + RES_001 closed; PROG_001 in flight by parallel agent)
- PCS_001 BLOCKED on PROG_001 (parallel agent's work)
- FAC_001 enables wuxia sect mechanics directly (highest narrative leverage)
- NPC_NNN mortality is independent but mirrors PCS_001 mortality pattern → easier post-PCS_001

### Wuxia narrative requirements (primary V1 use case)

Wuxia content (SPIKE_01 + future) NEEDS:

- **Sect membership** (Lý Minh's sect affiliation; Du sĩ's sect affiliation; Ma đạo cult membership)
- **Sect rivalry** (Đông Hải Đạo Cốc vs Tây Sơn Ma Tông; opinion baseline -X for rival NPCs)
- **Master-disciple** (sư phụ ↔ đệ tử rank/role; sư huynh / sư đệ ranking)
- **Wulin Meng** (martial alliance; cross-sect coalition V1+)
- **Sect succession** (sect-leader death → heir disciple takes position; consumes V1+ TIT_001)
- **Sect cultivation method** (V1+ CULT_001 binding — "Đông Hải Đạo Cốc teaches Phong Vân Quyết" cultivation method; non-members can't learn)
- **Sect ideology binding** (most sects have implicit ideology — Daoist sect requires Đạo stance; Buddhist sect requires Phật stance)

---

## §2 — Worked examples (across realities)

### Example E1 — Wuxia 5-sect preset (SPIKE_01 reality + V1+ expansion)

**Wuxia V1 sects (5 declared in RealityManifest):**

| Sect | Display name | Ideology binding | Lex axiom tags |
|---|---|---|---|
| 1 | Đông Hải Đạo Cốc (Eastern Sea Daoist Valley) | ideology_dao Devout+ | qigong + spirit_sense |
| 2 | Tây Sơn Phật Tự (Western Mountain Buddhist Temple) | ideology_phat Devout+ | mind_body_cultivation |
| 3 | Ma Tông (Demonic Sect) | ideology_dao Zealous (deviant path) OR animism | demonic_arts + blood_arts |
| 4 | Trung Nguyên Võ Hiệp (Central Plains Martial Society) | none required | none (mundane martial) |
| 5 | Tán Tu Đồng Minh (Wandering Cultivator Alliance) | none required | flexible per member |

**Canonical actors V1 + their faction memberships:**

- **Lý Minh** (PC) — V1: unaffiliated (orphan; no sect yet); V1+ may join Trung Nguyên Võ Hiệp via story-event
- **Du sĩ** (NPC, scholar) — V1: member of Đông Hải Đạo Cốc; rank=outer_disciple; role=traveling_emissary
- **Tiểu Thúy** (NPC, innkeeper daughter) — V1: unaffiliated (commoner; no sect)
- **Lão Ngũ** (NPC, innkeeper) — V1: unaffiliated (commoner)
- **Hypothetical Ma Tông cult leader** (V1+ NPC) — sect=Ma Tông; rank=sect_master; role=current_head
- **Hypothetical Đông Hải Đạo Cốc leader** (V1+ NPC) — Du sĩ's master; rank=elder; role=cultivation_master

### Example E2 — Modern detective novel (Saigon)

PC (detective) — member of "Saigon Police Department" faction; rank=detective; role=investigator
NPC suspects — varied faction memberships (criminal organization vs civilian vs police)

### Example E3 — Sci-fi corporate house (V1+)

PC + NPCs — member of "House Atreides" faction (corporate-house pattern); rank=heir/lord/retainer

### Example E4 — D&D adventurer party

PC + NPCs — guild membership ("Adventurers Guild") + faction allegiance ("Lords Alliance" / "Harpers" / etc.); rank/role per faction

### What examples cover well

- ✅ Multi-genre support (Wuxia sects / Modern police / Sci-fi corporate / D&D guild)
- ✅ Faction declarative entity per-reality
- ✅ Per-actor membership with role + rank
- ✅ Ideology-bound sects (Wuxia common; Modern less so)
- ✅ V1+ master-disciple (sư phụ/đệ tử) within sect

### What examples DO NOT cover

- ❌ Faction-faction relations (rivalry/alliance/war) — V1+ DIPL_001 boundary
- ❌ Sect cultivation method binding (V1+ CULT_001)
- ❌ Marriage as faction alliance (V1+ FAC_001 + V1+ DIPL_001)
- ❌ Cross-reality faction migration (V2+ Heresy)
- ❌ Faction-driven Lex axiom gating concrete examples (V1+ when first axiom uses)
- ❌ Multi-faction membership (PC member of 2 factions simultaneously)

---

## §3 — Gap analysis (12 dimensions across 5 grouped concerns)

### Group A — Faction declarative entity

**A1. Faction-as-entity vs faction-as-tag.**
- Option: separate `faction` aggregate (T2/Reality, sparse) vs tag on actor_faction_membership
- Considerations: cross-actor query "all members of Đông Hải Đạo Cốc" + V1+ TIT_001 sect-leader heir reads + V1+ REP_001 reputation projection per faction

**A2. Faction kind taxonomy.**
- Sect (wuxia martial+spiritual) / Order (religious) / Clan (family-based) / Guild (mercantile) / Coalition (multi-faction alliance) / etc.
- Closed enum FactionKind?
- Considerations: V1 minimal vs V1+ rich taxonomy

**A3. Faction declarative metadata.**
- display_name (I18nBundle) + ideology binding (Vec<IdeologyId>) + Lex axiom tags + canon_ref + sect-cultivation-method (V1+ CULT_001) + faction-kind

### Group B — Per-actor membership

**B1. Membership shape: single faction vs multi-faction V1?**
- Wuxia common: 1 sect per actor (deep loyalty)
- Modern common: multiple memberships (guild + political party + nationality)
- D&D: multiple faction allegiances normal
- Decision impact: Vec<FactionMembership> vs Option<FactionMembership>

**B2. Role within faction.**
- Sect master / inner disciple / outer disciple / elder / etc.
- V1: closed-set RoleKind enum per FactionKind?
- V1+: per-faction-author-declared role taxonomy

**B3. Rank within faction.**
- "Sư huynh / sư đệ" — rank-ordering among disciples
- V1 numeric rank (1, 2, 3...) vs V1+ named ranks (Đại sư huynh / Nhị sư đệ)?

**B4. Hierarchical position (master-disciple chain).**
- Master ref: parent actor in master-disciple chain
- V1+ extended traversal (master's master = "sư tổ")
- Wuxia common: 5+ generations of master lineage

### Group C — Faction-faction relations

**C1. Rivalry / Alliance / War — V1 vs V1+ DIPL_001?**
- V1 minimal: per-faction `default_relations: HashMap<FactionId, RelationStance>` (Hostile/Neutral/Allied)
- V1+ rich: dynamic relation events; treaties; wars

**C2. Master-faction (parent of sub-sects).**
- "Wulin Meng" = parent faction of multiple sects
- V1+ parent_faction_id field

### Group D — Storage model

**D1. Aggregate model.**
- Option A: 2 aggregates — `faction` (per-faction; sparse) + `actor_faction_membership` (per-actor; possibly 0-N V1+ multi)
- Option B: 1 aggregate — `actor_faction_membership` only; faction "data" is RealityManifest declarative
- Option C: 3 aggregates — faction + faction_relations + actor_faction_membership

**D2. Materialized vs derived state.**
- Per FF_001 Q5 + EVT-A10: materialized aggregate + EVT-T3 Derived events; NO separate faction_event_log

### Group E — Cross-feature integration

**E1. Ideology binding (IDL-D2 RESOLVED here).**
- FactionDecl declares `requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>` — actor must have ideology stance to join sect
- Validation: at join event, check actor_ideology_stance has matching entry

**E2. Master-disciple chain (FF-D7 RESOLVED here).**
- ActorFactionMembership stores `master_actor_id: Option<ActorId>` for master ref
- "Sư huynh" rank from joining order timestamp
- V1+ traversal API to find sư tổ (master's master)

**E3. Sworn brotherhood (FF-D6 RESOLVED here).**
- V1+ separate sworn_bond aggregate? OR stored within faction membership?
- Wuxia "kết nghĩa huynh đệ" = bonded oath; multi-actor bond
- Decision: V1+ separate from FAC_001? OR within FAC_001 as separate-faction-kind?

**E4. Marriage as faction alliance (FF-D5 RESOLVED here).**
- Marriage event triggers faction-alliance update? V1+ DIPL_001
- V1 FF_001 marriage doesn't trigger FAC_001 V1+

**E5. V1+ TIT_001 Title Foundation integration.**
- Sect-leader role/title inheritance via dynasty.current_head + faction_membership.role=sect_leader
- V1+ TIT_001 reads BOTH FF_001 dynasty + FAC_001 faction_membership

**E6. V1+ REP_001 Reputation Foundation integration.**
- Per-(actor, faction) reputation projection (separate aggregate per IDF folder closure roadmap priority 6)
- FAC_001 V1 doesn't ship reputation; V1+ REP_001 reads FAC_001 + adds rep value

---

## §4 — Boundary intersection summary

When FAC_001 DRAFT lands, these boundaries need careful handling:

| Touched feature | Status | FAC_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|---|
| EF_001 Entity Foundation | CANDIDATE-LOCK | (none) | EntityRef + entity_binding | actor_faction_membership references ActorId per EF_001 §5.1 |
| FF_001 Family Foundation | CANDIDATE-LOCK | Sect/master-disciple/sworn (per FF_001 Q4 LOCKED + FF-D6/D7) | family_node + dynasty | FAC_001 RESOLVES FF-D6/D7; FAC_001 master-disciple ≠ FF_001 family |
| IDF_004 Origin | CANDIDATE-LOCK | (none) | actor_origin + origin_pack_id | V1+ origin pack default sect declaration; FAC_001 reads at canonical seed |
| IDF_005 Ideology | CANDIDATE-LOCK | Sect membership ideology binding (per IDL-D2 LOCKED) | actor_ideology_stance | FAC_001 RESOLVES IDL-D2; FactionDecl.requires_ideology validated against actor_ideology_stance at join |
| IDF_001 Race | CANDIDATE-LOCK | (none) | RaceId / race_assignment | V1+ race-bound sects (Cultivator-only sects); requires_race hook V1+ |
| RES_001 Resource | DRAFT | (none) | resource_inventory + vital_pool | V2+ faction treasury (clan-shared inventory) |
| NPC_001 Cast | CANDIDATE-LOCK | Per-NPC faction membership | NPC core + canonical_actor_decl | NPC_001 declares faction at canonical seed; FAC_001 reads + creates membership row |
| NPC_002 Chorus | CANDIDATE-LOCK | (none) | priority algorithm | V1+ rival-faction NPCs Tier 4 priority modifier |
| NPC_003 Desires | DRAFT | (none) | npc.desires field | Independent — V1+ rival-faction desires V2+ |
| PL_005 Interaction | CANDIDATE-LOCK | Faction-cascade reaction trigger | InteractionKind + OutputDecl | V1+ Strike on rival-faction member triggers cascade opinion drift via FAC_001 traversal |
| WA_001 Lex | CANDIDATE-LOCK | (none) | LexConfig axioms | V1+ AxiomDecl.requires_faction hook; FAC_001 V1 schema-present None |
| WA_006 Mortality | CANDIDATE-LOCK | (none) | Death state machine | Sect-leader death → V1+ TIT_001 succession via FAC_001 faction_membership.role=sect_leader |
| WA_003 Forge | CANDIDATE-LOCK | (none — FAC_001 declares own AdminAction sub-shapes) | Forge audit log + AdminAction enum | FAC_001 adds Forge AdminAction (`Forge:EditFaction` + `Forge:RegisterFaction` + `Forge:EditFactionMembership`) |
| 07_event_model | LOCKED | EVT-T3 Derived (`aggregate_type=actor_faction_membership` + `faction`) + EVT-T4 System (FactionBorn + FactionMembershipBorn) + EVT-T8 Administrative | Event taxonomy + Generator framework | Per EVT-A11 sub-type ownership |
| RealityManifest envelope | unowned | `canonical_factions: Vec<FactionDecl>` + `canonical_faction_memberships: Vec<FactionMembershipDecl>` | Envelope contract per `_boundaries/02_extension_contracts.md` §2 | REQUIRED V1; sparse storage allowed |
| `faction.*` rule_id namespace | not yet registered | All faction RejectReason variants | RejectReason envelope (Continuum) | Per `_boundaries/02_extension_contracts.md` §1.4 — register at FAC_001 DRAFT |
| Future PCS_001 PC substrate | brief (BLOCKED on PROG_001) | (none) | PC identity | PCS_001 PC creation form selects faction or unaffiliated |
| Future TIT_001 Title Foundation | not started | (none — FAC_001 V1 doesn't ship title rules) | Title aggregate + heir selection | V1+ TIT_001 reads dynasty.current_head (FF_001) + sect_leader_role (FAC_001) |
| Future REP_001 Reputation Foundation | not started | (none — REP_001 V1+ separate aggregate) | actor_faction_reputation per-(actor, faction) | V1+ REP_001 reads FAC_001 faction_membership + adds reputation value |
| Future CULT_001 Cultivation Foundation | not started | (none — CULT_001 binds method to faction_id) | Cultivation method registry | V1+ CULT_001 reads FAC_001 sect_id for cultivation_method ref |
| Future DIPL_001 Diplomacy Foundation | not started | (none — DIPL_001 owns inter-faction relations dynamic) | Treaties + war + alliance dynamics | V2+ DIPL_001 reads FAC_001 faction list |

---

## §5 — Q1-Q10 critical scope questions — ✅ ALL LOCKED 2026-04-26 (user "A" confirmation; 3 REVISIONS noted)

User confirmed "A" on all 10 Q-decisions 2026-04-26 with deep-dive analysis. **3 REVISIONS** from initial survey recommendations:
- Q2 REVISION: Vec schema V1 with cap=1 validator (vs Option<T> single)
- Q4 REVISION: Numeric u16 only V1; named computed display (vs both fields)
- Q7 REVISION: Defer sworn brotherhood entirely V1+ FAC-D10 (vs V1 schema slot)

Locked decisions below; FAC_001 DRAFT promotion ready when `_LOCK.md` free.

### Q1 — Aggregate model: 1 or 2 or 3 aggregates V1?

✅ **LOCKED 2026-04-26: (A) 2 aggregates** — `faction` (T2/Reality sparse) + `actor_faction_membership` (T2/Reality)

**Reasoning:**
- faction.current_head_actor_id is MUTABLE on succession events (V1+ TIT_001 sect-leader heir); RealityManifest declarative bootstrap-only — needs runtime aggregate
- V1+ REP_001 reputation projection per-(actor, faction) needs faction-as-entity for query keys
- Cross-actor query "all members of Đông Hải Đạo Cốc" requires sparse faction aggregate
- Q5 LOCKED static V1 default_relations → embed as field on faction aggregate (no separate faction_relations aggregate needed V1)
- Matches FF_001 pattern (family_node + dynasty)

### Q2 — Multi-faction membership V1? ⚠ REVISION

✅ **LOCKED 2026-04-26: REVISION — Vec<FactionMembershipEntry> schema V1; V1 validator cap=1; V1+ relax cap**

**Reasoning (REVISION from initial single Option<T>):**
- Schema V1 ships `actor_faction_membership.memberships: Vec<FactionMembershipEntry>` (Vec from day 1)
- V1 validator rule: `memberships.len() > 1` rejects with `faction.multi_membership_forbidden_v1`
- V1+ cap relax = single-line validator change; NO schema migration
- Wuxia common single-sect semantics preserved V1 (cap=1 enforced)
- Modern + D&D multi-faction unblocked V1+ via cap relax
- Trade-off: 1 extra capacity field vs Option; minimal cost; significant V1+ migration savings

### Q3 — Role taxonomy: closed enum vs author-declared per-faction?

✅ **LOCKED 2026-04-26: (A) Author-declared per-faction** — RoleDecl with role_id + display_name (I18nBundle) + authority_level (u8 0-100)

**Reasoning:**
- Wuxia narrative authenticity REQUIRES sect-specific naming (sect_master / elder / inner_disciple / outer_disciple ≠ Master / Officer / Member generic)
- Engine doesn't lose information via generic enum
- Authoring cost ~25 RoleDecl entries V1 Wuxia (5 sects × 5 roles); small content cost
- Matches D&D 5e per-faction-rank pattern (each faction has own reputation rank semantics)
- V1+ extensions additive: max_actors_in_role + allowed_succession_kinds

### Q4 — Rank within faction: numeric vs named V1? ⚠ REVISION

✅ **LOCKED 2026-04-26: REVISION — (A) Numeric u16 only V1**; named computed on display layer; V1+ explicit name override

**Reasoning (REVISION from initial both-fields):**
- Wuxia named rank IS DERIVED from numeric ordering ("Đại" = 1; "Nhị" = 2; "Tam" = 3; etc.)
- Named rank is presentation layer (LLM/UI computes from numeric + RoleDecl + locale)
- V1 storage minimal: 1 u16 field per membership
- V1+ enrichment: explicit_rank_name: Option<I18nBundle> field for narrative override (sect declares specific names beyond auto-derived)
- Numeric encodes ordering for traversal queries (find disciple senior to LM01 = numeric_rank < LM01.rank)

### Q5 — Faction-faction relations: V1 minimal vs V1+ DIPL_001?

✅ **LOCKED 2026-04-26: (A) V1 static default_relations** — per-faction HashMap<FactionId, RelationStance> at canonical seed; V1+ DIPL_001 dynamic

**Reasoning:**
- V1 use case: rival-sect NPCs Tier 4 priority modifier + opinion baseline (-5 / 0 / +5 per Hostile/Neutral/Allied)
- V1+ DIPL_001 layers dynamic events (treaties / wars / alliance changes) without schema migration
- 3-variant RelationStance enum: Hostile / Neutral / Allied
- Authoring cost Wuxia preset: 5 sects × ~3 declared relations = 15 entries (sparse HashMap; default Neutral implicit)
- Self-relation faction.default_relations[self.faction_id] not declared (implicit Allied)

### Q6 — Master-disciple representation V1?

✅ **LOCKED 2026-04-26: (A) `master_actor_id: Option<ActorId>` field on actor_faction_membership** — V1 simple; sect lineage chain via traversal V1+

**Reasoning:**
- **FF-D7 RESOLVED:** Master-disciple = FAC_001 actor_faction_membership.master_actor_id (NOT FF_001 family relation)
- Sect lineage chain via traversal: LM01.master = du_si → du_si.master = some_elder → some_elder.master = founder
- V1 validation:
  - master_actor_id MUST be member of same faction (not cross-sect master)
  - master_actor_id MUST have higher authority_level (master ranks above disciple)
  - Cyclic master chain rejected with `faction.cyclic_master_chain`
- V1+ extended traversal API (find sư tổ = master's master)
- Matches Sands of Salzaar + Path of Wuxia + wuxia novel canon pattern

### Q7 — Sworn brotherhood (FF-D6) representation V1? ⚠ REVISION

✅ **LOCKED 2026-04-26: REVISION — (C) Defer V1+ via FAC-D10**; V1 doesn't ship sworn_bond_id field

**Reasoning (REVISION from initial sworn_bond_id field V1):**
- V1 SPIKE_01 has NO sworn brotherhood (Lý Minh + canonical actors no Peach Garden Oath)
- Adding field to V1 schema without V1 use case = schema bloat
- V1+ activation can add field via additive I14 (no schema migration; new optional field)
- V1+ FAC-D10 enrichment scope:
  - Add `sworn_bond_id: Option<SwornBondId>` field on actor_faction_membership (additive)
  - Add separate `sworn_bonds` aggregate (per-bond metadata: founding_at_turn + member_actor_ids + oath_text I18nBundle)
  - Multi-actor bond traversal: scan actor_faction_memberships for matching sworn_bond_id
- Discipline: V1 ships what's actively consumed; defer schema otherwise
- Cleaner V1 (focused on sect membership + master-disciple)
- **FF-D6 partially deferred:** V1+ FAC-D10 owns sworn brotherhood (NOT V1 FAC_001)

### Q8 — Cross-reality faction migration V1 vs V2+?

✅ **LOCKED 2026-04-26: (A) V1 strict single-reality**; V2+ Heresy migration

**Reasoning:**
- All IDF features locked V2+ for cross-reality (POST-SURVEY-Q6 + ORG-Q8 + IDL); FF_001 Q7 LOCKED V2+; FAC_001 inherits same discipline
- V1 reject `faction.cross_reality_mismatch` (V2+ reservation; V1 unused)

### Q9 — Faction-driven Lex axiom gate V1 or V1+?

✅ **LOCKED 2026-04-26: (A) Schema-present hook V1+**; V1 always None

**Reasoning:**
- Pattern matches IDF_001 RAC-Q5 + IDF_005 (`requires_race` / `requires_ideology` reserved V1+; V1 always None)
- WA_001 closure pass extension (V1+) adds 3 companion fields uniformly: requires_race + requires_ideology + requires_faction
- V1+ first faction-gated axiom example: "Đông Hải Đạo Cốc Phong Vân Quyết — only sect members can invoke"
- V1 schema cost: tiny (Option<Vec<FactionId>> field on AxiomDecl); V1 always None

### Q10 — Synthetic actor faction membership?

✅ **LOCKED 2026-04-26: (A) Forbidden V1** — Synthetic actors don't have faction membership

**Reasoning:**
- Inherits IDF + FF discipline (RAC-Q1 + PRS-Q11 + ORG-Q7 + IDL-Q12 + FF_001 synthetic exclusion)
- Synthetic actors (ChorusOrchestrator / BubbleUpAggregator / mechanical entities) have no narrative faction allegiance V1
- V1+ may relax if admin/system faction needed

---

## §6 — Reference materials placeholder

User stated 2026-04-26: may provide reference sources (per RES_001 + IDF + FF_001 pattern). FAC_001 follows same template.

When references arrive:
1. Capture verbatim
2. Cross-reference with main session knowledge (already in `01_REFERENCE_GAMES_SURVEY.md` companion)
3. Update Q1-Q10 recommendations + lock LOCKED decisions

**Status:** awaiting user input.

---

## §7 — V1 scope ✅ LOCKED 2026-04-26 (post Q1-Q10 deep-dive + user "A" confirmation; 3 REVISIONS noted)

### V1 aggregates (2)

1. **`faction`** (T2/Reality, sparse — only declared factions get rows)
   - faction_id + display_name (I18nBundle) + faction_kind (closed-set: Sect / Order / Clan / Guild / Coalition / Other) + roles: Vec<RoleDecl> per Q3 + requires_ideology (Option<Vec<(IdeologyId, FervorLevel)>> per IDL-D2 RESOLVED) + default_relations: HashMap<FactionId, RelationStance> per Q5 + canon_ref + founder_actor_id (Option) + current_head_actor_id (Option) + member_count (sparse query helper)
   - **Mutable** via succession events V1+ (current_head_actor_id) + V1+ DIPL_001 dynamic relation overlay
   - Sparse storage (5 sects per Wuxia preset; 1-2 per Modern; 0 V1 sandbox)

2. **`actor_faction_membership`** (T2/Reality, per-(reality, actor_id))
   - memberships: Vec<FactionMembershipEntry> per Q2 REVISION (V1 cap=1 validator; V1+ relax)
   - **Mutable** via Apply events (JoinFaction / LeaveFaction / ChangeRole / ChangeRank / SetMaster / RemoveMaster)
   - Synthetic actors forbidden V1 per Q10

### FactionMembershipEntry V1 schema

```rust
pub struct FactionMembershipEntry {
    pub faction_id: FactionId,
    pub role_id: RoleId,                       // ref to FactionDecl.roles[*].role_id
    pub rank_within_role: u16,                 // numeric V1 per Q4 REVISION; ordered ascending (1 = highest authority within role)
    pub master_actor_id: Option<ActorId>,      // sect lineage chain per Q6; FF-D7 RESOLVED
    pub joined_at_turn: u64,
    pub joined_at_fiction_ts: i64,
    pub joined_reason: JoinReason,
    // V1+ extensions (additive per I14)
    // pub sworn_bond_id: Option<SwornBondId>,           // V1+ FAC-D10 per Q7 REVISION
    // pub explicit_rank_name: Option<I18nBundle>,        // V1+ override per Q4 enrichment
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

### V1 closed enums

- **`FactionKind`** (6 variants V1): Sect / Order / Clan / Guild / Coalition / Other
- **`RelationStance`** (3 variants V1): Hostile / Neutral / Allied
- **`JoinReason`** (4 variants V1): CanonicalSeed / PcCreation / NpcSpawn / AdminOverride

### V1 events (in channel stream per EVT-A10; NOT separate aggregate)

| Event | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| Faction registered at canonical seed | **EVT-T4 System** | `FactionBorn { faction_id, faction_kind, roles_count }` | Bootstrap (RealityBootstrapper) | ✓ V1 |
| Membership at canonical seed | **EVT-T4 System** | `FactionMembershipBorn { actor_id, faction_id, role_id, rank }` | Bootstrap | ✓ V1 |
| Join faction | **EVT-T3 Derived** | `aggregate_type=actor_faction_membership`, `delta_kind=JoinFaction` | Aggregate-Owner (FAC_001 owner-service) | V1+ runtime |
| Leave faction | **EVT-T3 Derived** | `delta_kind=LeaveFaction` | Aggregate-Owner | V1+ runtime |
| Change role | **EVT-T3 Derived** | `delta_kind=ChangeRole` | Aggregate-Owner | V1+ runtime |
| Change rank | **EVT-T3 Derived** | `delta_kind=ChangeRank` | Aggregate-Owner | V1+ runtime |
| Set master (master-disciple bond formed) | **EVT-T3 Derived** | `delta_kind=SetMaster` | Aggregate-Owner | V1+ runtime |
| Remove master (master-disciple bond broken) | **EVT-T3 Derived** | `delta_kind=RemoveMaster` | Aggregate-Owner | V1+ runtime |
| Faction succession (head change) | **EVT-T3 Derived** | `aggregate_type=faction`, `delta_kind=SetCurrentHead` | Aggregate-Owner (V1+ TIT_001 trigger) | V1+ runtime |
| Forge admin register faction | **EVT-T8 Administrative** | `Forge:RegisterFaction` | Forge (WA_003) | ✓ V1 |
| Forge admin edit faction | **EVT-T8 Administrative** | `Forge:EditFaction` | Forge | ✓ V1 |
| Forge admin edit membership | **EVT-T8 Administrative** | `Forge:EditFactionMembership` | Forge | ✓ V1 |

### V1 `faction.*` reject rule_ids (8 V1 + V1+ reservations)

V1 rules:
1. `faction.unknown_faction_id` — Stage 0 schema (faction_id not in RealityManifest.canonical_factions + faction aggregate)
2. `faction.unknown_role_id` — Stage 0 schema (role_id not in FactionDecl.roles)
3. `faction.multi_membership_forbidden_v1` — Stage 0 schema (Vec.len() > 1; per Q2 REVISION cap=1)
4. `faction.master_cross_sect_forbidden` — Stage 0 schema (master_actor_id member of different faction)
5. `faction.master_authority_violation` — Stage 0 schema (master.authority_level <= disciple.authority_level)
6. `faction.cyclic_master_chain` — Stage 0 schema (LM01 master-of-X master-of-LM01)
7. `faction.ideology_binding_violation` — Stage 0 schema (actor's ideology stance doesn't satisfy FactionDecl.requires_ideology)
8. `faction.synthetic_actor_forbidden` — Stage 0 schema (Synthetic actor cannot have faction membership per Q10)

V1+ reservations:
- `faction.cross_reality_mismatch` (V2+ Heresy migration per Q8)
- `faction.lex_axiom_forbidden` (V1+ when first faction-gated axiom ships per Q9)
- `faction.sworn_bond_unsupported_v1` (V1+ FAC-D10 enrichment activation reject)
- `faction.member_role_count_exceeded` (V1+ when RoleDecl.max_actors_in_role enrichment ships)

### V1 RealityManifest extensions (REQUIRED V1)

- `canonical_factions: Vec<FactionDecl>` — per-reality declared factions (sparse; empty Vec valid for sandbox)
- `canonical_faction_memberships: Vec<FactionMembershipDecl>` — per-actor declared faction memberships at canonical seed (sparse; empty Vec valid)

`FactionDecl` shape:
```rust
pub struct FactionDecl {
    pub faction_id: FactionId,
    pub display_name: I18nBundle,
    pub faction_kind: FactionKind,
    pub roles: Vec<RoleDecl>,
    pub requires_ideology: Option<Vec<(IdeologyId, FervorLevel)>>,
    pub default_relations: HashMap<FactionId, RelationStance>,
    pub canon_ref: Option<GlossaryEntityId>,
    pub founder_actor_id: Option<ActorId>,
    pub current_head_actor_id: Option<ActorId>,
}
```

`FactionMembershipDecl` shape:
```rust
pub struct FactionMembershipDecl {
    pub actor_id: ActorId,
    pub faction_id: FactionId,
    pub role_id: RoleId,
    pub rank_within_role: u16,
    pub master_actor_id: Option<ActorId>,
}
```

### V1 acceptance criteria (10 V1-testable + 4 V1+ deferred)

V1:
- AC-FAC-1: Wuxia canonical bootstrap declares 5 sects + ~10 NPC memberships (Du sĩ in Đông Hải Đạo Cốc as outer_disciple rank=1)
- AC-FAC-2: Faction.requires_ideology validated against actor's ideology stance at canonical seed (Du sĩ has ideology_dao Devout → meets Đông Hải Đạo Cốc requires_ideology=[(ideology_dao, Devout)])
- AC-FAC-3: Master-disciple chain validated (Du sĩ.master = old_elder_npc; old_elder_npc same faction; authority_level higher)
- AC-FAC-4: Cyclic master chain rejected (`faction.cyclic_master_chain`)
- AC-FAC-5: Multi-membership rejected V1 (`faction.multi_membership_forbidden_v1` on Vec.len()>1)
- AC-FAC-6: Unknown faction_id rejected (`faction.unknown_faction_id`)
- AC-FAC-7: Unknown role_id rejected (`faction.unknown_role_id`)
- AC-FAC-8: Ideology binding violation rejected (`faction.ideology_binding_violation`)
- AC-FAC-9: I18nBundle resolves faction display_name + role display_name across locales
- AC-FAC-10: Forge admin register faction (3-write atomic: faction row + EVT-T8 + forge_audit_log)

V1+:
- AC-FAC-V1+1: V1+ runtime JoinFaction event (PC defects mid-story)
- AC-FAC-V1+2: V1+ TIT_001 sect succession (sect_master dies → heir disciple becomes head)
- AC-FAC-V1+3: V1+ multi-faction membership (cap relax)
- AC-FAC-V1+4: V1+ FAC-D10 sworn brotherhood (sworn_bond_id field activation)

### V1 deferrals (17 — FAC-D1..D17)

- FAC-D1: Multi-faction membership V1+ cap relax (Q2 REVISION; cap=1 → cap=N)
- FAC-D2: Sect cultivation method binding (V1+ CULT_001)
- FAC-D3: Marriage as faction alliance (V1+ DIPL_001 — FF-D5 deferred jointly)
- FAC-D4: Faction-faction dynamic relations (V1+ DIPL_001)
- FAC-D5: Wulin Meng parent_faction_id (V1+ enrichment for hierarchical faction)
- FAC-D6: Sect succession rules (V1+ TIT_001 — FF-D8 jointly)
- FAC-D7: Per-(actor, faction) reputation projection (V1+ REP_001)
- FAC-D8: Faction-driven Lex axiom gate ACTIVE (V1+ when first axiom uses; Q9)
- FAC-D9: Cross-reality faction migration (V2+ WA_002 Heresy per Q8)
- **FAC-D10: Sworn brotherhood (Q7 REVISION; sworn_bond_id field + sworn_bonds aggregate; V1+ enrichment)**
- FAC-D11: V1+ runtime defection / join / leave event flows (V1 ships canonical seed only)
- FAC-D12: Faction cultivation method registry (V1+ CULT_001)
- FAC-D13: Faction treasury / clan-shared inventory (V2+ RES_001)
- FAC-D14: Hierarchical faction parent_faction_id (cadet branches)
- FAC-D15: Faction-conflict opinion modifier non-member NPCs (V1+ NPC_002 enrichment)
- **FAC-D16: Multi-faction membership cap relax (Q2 REVISION enrichment; same as FAC-D1)**
- **FAC-D17: Explicit named rank override (Q4 REVISION enrichment; explicit_rank_name field)**

### V1 quantitative summary

- 2 aggregates (faction sparse + actor_faction_membership)
- 6-variant FactionKind enum + 3-variant RelationStance enum + 4-variant JoinReason enum
- Vec<FactionMembershipEntry> with V1 validator cap=1 per Q2 REVISION
- Author-declared roles per FactionDecl (RoleDecl) per Q3
- Numeric u16 rank only V1 per Q4 REVISION
- master_actor_id field per Q6
- NO sworn_bond_id field V1 per Q7 REVISION (FAC-D10)
- Static default_relations HashMap<FactionId, RelationStance> per Q5
- 8 V1 reject rule_ids in `faction.*` namespace + 4 V1+ reservations
- 2 RealityManifest extensions (canonical_factions + canonical_faction_memberships)
- 3 EVT-T8 Forge sub-shapes (Forge:RegisterFaction + Forge:EditFaction + Forge:EditFactionMembership)
- 2 EVT-T4 System sub-types (FactionBorn + FactionMembershipBorn)
- 7 EVT-T3 delta_kinds (JoinFaction / LeaveFaction / ChangeRole / ChangeRank / SetMaster / RemoveMaster / SetCurrentHead — V1+ runtime; V1 ships canonical seed only)
- 10 V1 AC + 4 V1+ deferred
- 17 deferrals (FAC-D1..D17)
- ~700-900 line DRAFT spec estimate
- 4-commit cycle (lock-Q this commit + DRAFT + Phase 3 + closure+release)

---

## §8 — What this concept-notes file is NOT

- ❌ NOT the formal FAC_001 design (no Rust struct definitions, no full §1-§N section structure, no acceptance criteria)
- ❌ NOT a lock-claim trigger
- ❌ NOT registered in ownership matrix yet
- ❌ NOT consumed by other features yet (FF-D6/D7 + IDL-D2 retain V1+ deferred status until FAC_001 DRAFT)
- ❌ NOT prematurely V1-scope-locked (Q1-Q10 OPEN; recommendations pending)

---

## §9 — Promotion checklist (when Q1-Q10 answered + references reviewed)

Before drafting `FAC_001_faction_foundation.md`:

1. [ ] User reviews market survey + provides additional references if any
2. [ ] User answers Q1-Q10 (or approves recommendations after deep-dive)
3. [ ] Update §7 V1 scope based on locked decisions
4. [ ] Wait for `_boundaries/_LOCK.md` to be free (currently PROG_001 agent claim)
5. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL)
6. [ ] Create `FAC_001_faction_foundation.md` with full §1-§N spec
7. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — add faction + actor_faction_membership aggregates (per Q1 decision)
8. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 — add `faction.*` RejectReason prefix
9. [ ] Update `_boundaries/02_extension_contracts.md` §2 — add RealityManifest `canonical_factions` + `canonical_faction_memberships` extensions
10. [ ] Update `_boundaries/99_changelog.md` — append entry
11. [ ] Create `catalog/cat_00_FAC_faction_foundation.md` — feature catalog
12. [ ] Update `00_faction/_index.md` — replace concept row with FAC_001 DRAFT row
13. [ ] Coordinate with FF_001 closure pass extension to mark FF-D6 + FF-D7 RESOLVED via FAC_001
14. [ ] Coordinate with IDF_005 closure pass extension to mark IDL-D2 RESOLVED via FAC_001
15. [ ] Update `features/_index.md` to add `00_faction/` to layout + table
16. [ ] Release `_boundaries/_LOCK.md`
17. [ ] Commit cycle (lock-Q + DRAFT + Phase 3 + closure+release; ~4-5 commits)

---

## §10 — Status

- **Created:** 2026-04-26 by main session (commit this turn)
- **Phase:** CONCEPT — awaiting Q1-Q10 deep-dive + market survey review
- **Lock state:** `_boundaries/_LOCK.md` held by PROG_001 agent (parallel session). FAC_001 DRAFT blocked until lock free; concept-notes phase NOT blocked.
- **Estimated time to DRAFT (post-Q-deep-dive):** 3-5 hours focused design work; ~700-1000 line spec
- **Co-design dependencies (when DRAFT):**
  - FF_001 closure pass extension marks FF-D6 + FF-D7 RESOLVED via FAC_001
  - IDF_005 closure pass extension marks IDL-D2 RESOLVED via FAC_001
  - Future PCS_001 PC creation form references FAC_001 for sect selection
  - Future TIT_001 + V1+ REP_001 + V1+ CULT_001 + V1+ DIPL_001 consume FAC_001 graph
- **Next action:** User reviews market survey + answers Q1-Q10 (or approves recommendations) → DRAFT promotion when lock free
