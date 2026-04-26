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

## §5 — Q1-Q10 critical scope questions

These 10 questions lock V1 scope. Once user has reviewed market survey + answered (or approved recommendations), FAC_001 DRAFT can proceed.

### Q1 — Aggregate model: 1 or 2 or 3 aggregates V1?

- **(A) 2 aggregates** — `faction` (T2/Reality sparse; per-faction metadata) + `actor_faction_membership` (T2/Reality; per-(actor, faction_id) — possibly multi-faction)
- **(B) 1 aggregate** — `actor_faction_membership` only; faction "data" stays in RealityManifest declarative (no runtime aggregate)
- **(C) 3 aggregates** — add separate `faction_relations` aggregate V1 (faction-faction Hostile/Neutral/Allied table)

**Open** — recommendation likely (A) for V1+ TIT_001 + V1+ REP_001 + V1+ DIPL_001 consumer support; (C) only if V1 ships faction-faction relations.

### Q2 — Multi-faction membership V1?

- **(A) Single faction V1** — each actor 0-1 faction; matches Wuxia common (1 sect per actor)
- **(B) Multi-faction V1** — Vec<FactionMembership>; matches Modern + D&D (multiple guild/faction memberships)
- **(C) Multi-faction with primary flag V1** — Vec but one flagged primary

**Open** — recommendation depends on V1 reality preset priority. Wuxia primary suggests (A); Modern flexibility suggests (B); (C) compromise.

### Q3 — Role taxonomy: closed enum vs author-declared per-faction?

- **(A) Author-declared per-faction** — FactionDecl includes `roles: Vec<RoleDecl>`; sect declares own role taxonomy (sect_master / inner_disciple / etc.)
- **(B) V1 closed enum** — engine ships generic FactionRole closed-set 6-variant (Master / Officer / Member / Recruit / Affiliate / Honorary)
- **(C) Hybrid** — closed-set V1 + author override V1+

**Open** — wuxia complexity suggests (A); V1 simplicity suggests (B). Tradeoff.

### Q4 — Rank within faction: numeric vs named V1?

- **(A) V1 numeric rank u16** — 1, 2, 3... ordered ranks; "sư huynh" = lower number than "sư đệ"; V1 simple
- **(B) V1 named rank Vec<String>** — author declares per-faction rank names; "Đại sư huynh" / "Nhị sư đệ"
- **(C) Both V1** — numeric_rank + named_rank fields

**Open** — wuxia narrative needs named ranks; numeric is simpler V1.

### Q5 — Faction-faction relations: V1 minimal vs V1+ DIPL_001?

- **(A) V1 minimal default_relations** — per-faction HashMap<FactionId, RelationStance> (Hostile/Neutral/Allied) at canonical seed; static V1
- **(B) V1+ DIPL_001 full** — V1 FAC_001 doesn't ship faction-faction relations; V1+ DIPL_001 owns dynamic
- **(C) V1 default + V1+ dynamic override** — static defaults V1 + dynamic relation events V1+ DIPL_001

**Open** — recommendation (A) static V1 for opinion modifier baseline; V1+ DIPL_001 adds dynamic.

### Q6 — Master-disciple representation V1?

- **(A) `master_actor_id: Option<ActorId>` field on actor_faction_membership** — V1 simple; sect lineage chain via traversal
- **(B) Separate `master_disciple_relation` aggregate V1+** — explicit relation aggregate; richer than field
- **(C) Within ActorFactionMembership.role + rank fields V1** — role=disciple + master derived from rank ordering

**Open** — recommendation (A) for V1 simplicity; matches FF-D7 RESOLVED scope.

### Q7 — Sworn brotherhood (FF-D6) representation V1?

- **(A) Within FAC_001 as sworn_bond_id field on actor_faction_membership** — bonded actors share sworn_bond_id; V1 minimal
- **(B) Separate sworn_bonds aggregate V1+** — multi-actor bond entity; richer
- **(C) Defer V1+** — FAC_001 V1 doesn't ship sworn brotherhood; V1+ separate feature OR FAC_001 enhancement

**Open** — recommendation depends on Wuxia content priority. (A) lightweight V1; (C) defers.

### Q8 — Cross-reality faction migration V1 vs V2+?

- **(A) V1 strict single-reality** — matches all IDF + FF discipline
- **(B) V1+ remap policy** — V2+ Heresy migration

**Open** — recommendation (A); inherits IDF/FF pattern.

### Q9 — Faction-driven Lex axiom gate V1 or V1+?

- **(A) V1+ schema-present hook** — AxiomDecl.requires_faction: Option<Vec<FactionId>>; V1 always None
- **(B) V1 active gate** — V1 ships first faction-gated axiom example
- **(C) Defer V1++** — schema later

**Open** — recommendation (A) future-proof hook; V1 reserved.

### Q10 — Synthetic actor faction membership?

- **(A) Forbidden V1** — Synthetic actors don't have faction membership (matches IDF/FF discipline)
- **(B) Allowed V1** — Synthetic actors can be faction members (admin/system entities)

**Open** — recommendation (A) per IDF/FF pattern.

---

## §6 — Reference materials placeholder

User stated 2026-04-26: may provide reference sources (per RES_001 + IDF + FF_001 pattern). FAC_001 follows same template.

When references arrive:
1. Capture verbatim
2. Cross-reference with main session knowledge (already in `01_REFERENCE_GAMES_SURVEY.md` companion)
3. Update Q1-Q10 recommendations + lock LOCKED decisions

**Status:** awaiting user input.

---

## §7 — Provisional V1 scope (placeholder — finalized after Q1-Q10 lock)

INTENTIONALLY EMPTY pending Q1-Q10 + reference materials review. Premature locking risks design churn (RES_001 + IDF folder pattern proven).

When user provides references + answers Q1-Q10, populate with:
- Aggregate count (per Q1) + storage model
- Multi-faction membership decision (per Q2)
- Role taxonomy (per Q3) — closed-set vs author-declared
- Rank representation (per Q4) — numeric vs named
- Faction-faction relations V1 stance (per Q5)
- Master-disciple representation (per Q6)
- Sworn brotherhood representation (per Q7)
- Cross-reality V1 stance (per Q8)
- Faction-driven Lex axiom V1 vs V1+ (per Q9)
- Synthetic actor membership (per Q10)
- RealityManifest extensions (canonical_factions + canonical_faction_memberships)
- Validator chain (`faction.*` namespace)
- EVT-T sub-types (T3 Derived + T4 System + T8 Administrative — V1 mapping)
- Acceptance criteria sketch (10 V1-testable AC)

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
