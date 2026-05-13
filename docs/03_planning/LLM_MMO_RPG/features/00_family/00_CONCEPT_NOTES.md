# FF_001 Family Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-26 — captures user framing (wuxia priority + IDF_004 lineage_id resolution + ORG-D12 signal) + 12-dimension gap analysis + 8 critical scope questions Q1-Q8. Awaits user reference materials review + Q-deep-dive before DRAFT promotion.
>
> **Purpose:** Capture brainstorm + gap analysis + open questions for FF_001 Family Foundation. NOT a design doc; the seed material for the eventual `FF_001_family_foundation.md` design.
>
> **Promotion gate:** When (a) Q1-Q8 locked via deep-dive discussion, (b) `_boundaries/_LOCK.md` free → main session drafts `FF_001_family_foundation.md` with locked V1 scope, registers ownership in matrix + extension contracts, creates `catalog/cat_00_FF_family_foundation.md`.

---

## §1 — User framing + priority signal (2026-04-26)

User direction 2026-04-26: "đi sâu vào các tính năng liên quan tới background của PC/NPC trước đi" → deep-dive PC/NPC background features.

User picked **A** (FF_001 Family Foundation deep-dive) as next feature after Race Path C V1 light commit (`72a7e77`).

### Inherited priority signals

1. **IDF_004 ORG-D12 LOCKED** (commit `e510b55`):
   > FF_001 Family Foundation V1+ feature — first priority post-IDF closure (BEFORE PCS_001). Owns: family_graph aggregate (parents/siblings/children/cousins/dynasty); BirthEvent / MarriageEvent / DeathEvent / DivorceEvent / AdoptionEvent log; family-driven opinion modifier (CK3 pattern); inheritance-readiness for V1+ TIT_001 Title Foundation.

2. **POST-SURVEY-Q4 LOCKED** (commit `ae7d280`): Family graph V1+ separate FF_001 (NOT V1 mini-stub in IDF_004). Reasoning: mini-stub creates partial design + refactor pain; FF_001 V1+ does it right.

3. **`_research_character_systems_market_survey.md` §5.5** (commit `34d5814`): "Every grand-strategy game tracks family + dynasty as first-class entity. Wuxia REQUIRES family/sect lineage — sect inheritance + family bloodline + dynasty politics are core wuxia narrative drivers."

### Wuxia narrative requirements

Wuxia content (SPIKE_01 reality + future content) NEEDS:

- **Family lineage** (Lý Minh's gia đình at Yến Vũ Lâu — even orphan PCs reference past family)
- **Dynasty politics** (clan rivalries — V1+ FAC_001 + V1+ TIT_001 consume FF_001)
- **Hereditary cultivation** (V1+ RAC-D3 hybrid race traits + V1+ CULT_001 inherited spirit roots)
- **Marriage as faction alliance** (Wuxia common: gia tộc liên hôn để tạo liên minh)
- **Death + grief reactions** (Strike kills family member → cascade opinion drift on relatives)
- **Heir succession** (V1+ TIT_001 — family head dies → heir takes title / sect leadership)
- **Adoption** (Wuxia common: master accepts orphan disciple — but THIS is sect lineage, not family per FF_001 vs FAC_001 boundary)

---

## §2 — Worked examples (across realities)

### Example E1 — Wuxia Yến Vũ Lâu (SPIKE_01 reality)

**Lý Minh** (PC) — orphan or inherited from prior generation?
- V1 simplest: Lý family with deceased parents (lineage_id="lineage_ly_yen_vu_lau"; no living parents)
- Siblings: none V1; V1+ may add elder brother / sister
- V1 family graph: 1-node graph (LM01 alone); lineage_id tag links to deceased ancestors

**Lão Ngũ** (NPC, innkeeper) — extended family at Yến Vũ Lâu
- Wife: deceased (V1 schema-present but Death event past)
- Children: Tiểu Thúy (NPC, daughter)
- V1 family graph: 2-node graph (Lão Ngũ + Tiểu Thúy with parent_actor_ids/children_actor_ids ref)

**Du sĩ** (NPC, wandering scholar) — cosmopolitan; no Yến Vũ Lâu family
- Family elsewhere (canonical seed declares Đông Hải Đạo Cốc parentage)
- V1 family graph: lineage_id tag only (no nodes for parents — deceased / off-stage)

### Example E2 — Modern detective novel (Saigon)

PC (detective) — single child, parents alive in different city
- Family graph: 3-node (PC + father + mother); parent_actor_ids non-empty
- Spouse: maybe (V1+ if PC marries)
- Children: none V1

NPC suspects — varied family configurations (V1+ rich)

### Example E3 — Sci-fi space-opera (V1+ deferred)

PC (House Atreides / Harkonnen archetype) — full dynasty
- Parents + uncle + cousin + potential heirs
- Multi-generational dynasty tracking
- Marriage = political alliance with another house
- V1+ dynasty mechanics

### Example E4 — D&D adventurer party

PCs — adventurers with backstories (orphans common; player-author free-form)
- V1 supports orphan / minimal family
- V1+ rich family for narrative depth

### What examples cover well

- ✅ V1 minimum scope: 1-node + lineage_id tag (covers orphan PC + simple NPC)
- ✅ V1 light scope: 2-3 node family (Lão Ngũ + Tiểu Thúy)
- ✅ V1+ rich scope: multi-generational dynasty
- ✅ Cross-genre support (Wuxia / Modern / Sci-fi / D&D)

### What examples DO NOT cover

- ❌ Sect lineage (master-disciple) — DELIBERATELY out of FF_001 scope (V1+ FAC_001 owns)
- ❌ Cross-reality family (PC moves between realities — V2+ Heresy migration)
- ❌ Bloodline trait inheritance (V1+ RAC-D3 + V1+ CULT_001 consume FF_001 graph)
- ❌ Title inheritance rules (V1+ TIT_001)
- ❌ Marriage as faction alliance (V1+ FAC_001 + V1+ DIPL_001)
- ❌ Adoption representation V1 detail (Q6)

---

## §3 — Gap analysis (12 dimensions across 5 grouped concerns)

Initial discussion 2026-04-26 surfaces 12 dimensions across 5 grouped concerns.

### Group A — Graph topology

**A1. Direct relations (V1 essential).**
- parent_actor_ids: Vec<ActorId> (0-N parents — orphan/single-parent/two-parent/V1+ multi-parent for adoption)
- sibling_actor_ids: Vec<ActorId> (0-N; V1 derived from shared parents OR explicit)
- spouse_actor_ids: Vec<ActorId> (0-N V1; V1+ polygamy via additive)
- children_actor_ids: Vec<ActorId> (0-N; V1 derived from inverse parent OR explicit)

**A2. Indirect relations (V1+ extension).**
- cousins (derived from grandparent shared)
- uncles/aunts (parent's siblings)
- in-laws (spouse's family)
- Computed via traversal V1+ when needed

**A3. Graph normalization.**
- Authoring: author declares parent refs only; engine derives children via inverse
- Risk: authoring inconsistency (parent A says child X but child X says parent B)
- Mitigation: canonical seed validation + Forge admin reconciliation

### Group B — Lineage + Dynasty

**B1. Lineage (continuous bloodline).**
- LineageId (already declared in IDF_004 as opaque tag — FF_001 resolves)
- Lineage = chain of ancestors → descendants sharing bloodline
- May span multiple actors / generations / dynasties

**B2. Dynasty (multi-generational house).**
- DynastyId — explicit clustering (e.g., "House Atreides" / "Lý Clan")
- Dynasty has founder + members + branch lineages
- V1+ TIT_001 inherits via dynasty's heir selection rule

**B3. Lineage vs Dynasty boundary.**
- Lineage = bloodline (genetic chain)
- Dynasty = social house (claims shared ancestry but may include adopted members)
- V1 may collapse them OR keep separate

### Group C — Family events

**C1. Birth events.**
- Creates new actor + assigns parent refs
- Per-event metadata: birth_at_fiction_ts + birthplace + parents
- V1+ ORG-D11 birth event metadata (thiên kiêu chi tử markers)

**C2. Marriage events.**
- Joins two actors' family graphs (spouse refs)
- May trigger faction alliance (V1+ FAC_001 + V1+ DIPL_001)
- V1+ divorce reverses

**C3. Death events.**
- Updates family graph (mark actor deceased; preserve refs)
- Cascade opinion drift on family members (V1+ NPC_002 enrichment)
- Triggers V1+ TIT_001 inheritance flow

**C4. Adoption events.**
- Add parent ref without biological tie
- V1 may treat same as biological (single field) OR V1+ separate adoption flag
- Sect master-disciple is QUASI-adoption but stays in V1+ FAC_001 (boundary discipline)

**C5. Divorce events (V1+).**
- Removes spouse ref; V1+ rare event

### Group D — Storage model

**D1. Per-actor `family_node` aggregate.**
- T2/Reality scope; per-(reality, actor_id) row holds direct relation refs
- Easy to query: "give me LM01's parents" = read family_node(LM01).parent_actor_ids

**D2. Multi-generational `dynasty` aggregate.**
- T2/Reality scope (V1) or T3/Reality (V1+ for multi-cell heir notification)
- Per-(reality, dynasty_id) row holds founder + members + branches

**D3. Append-only `family_event_log`.**
- T2/Reality (append-only)
- Per-event audit trail (Birth/Marriage/Death/Divorce/Adoption)
- Replay-deterministic source-of-truth for graph state derivation

**D4. Materialized vs derived state.**
- Option A: family_node holds materialized refs; events update both
- Option B: family_node DERIVED from event_log replay
- Option C: hybrid — materialized for hot path; event_log as audit

### Group E — Cross-feature integration

**E1. IDF_004 lineage_id resolution.**
- IDF_004 actor_origin.lineage_id is opaque V1 tag
- FF_001 V1+: lineage_id resolves to FF_001 graph entry point
- Integration mechanism: actor_origin.lineage_id → query family_node OR dynasty

**E2. Sect master-disciple boundary.**
- Wuxia: master-disciple is QUASI-family ("sư phụ" = "father-teacher")
- Decision: FF_001 = biological + adoption only; V1+ FAC_001 owns sect membership + master-disciple rank

**E3. Title inheritance (V1+ TIT_001).**
- Family head dies → V1+ TIT_001 heir selection consumes FF_001 graph
- V1 FF_001 doesn't ship title rules; just provides graph

**E4. Family-driven opinion drift (V1+ NPC_002).**
- Kill someone's child → relatives get opinion -X
- V1+ NPC_002 enrichment consumes FF_001 family_node for cascade

---

## §4 — Boundary intersection summary

When FF_001 DRAFT lands, these boundaries need careful handling:

| Touched feature | Status | FF_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|---|
| EF_001 Entity Foundation | CANDIDATE-LOCK | Family-side per-actor relations | EntityRef + entity_binding | family_node aggregate scope = `Actor only` (PC + NPC); references ActorId per EF_001 §5.1 |
| IDF_004 Origin Foundation | CANDIDATE-LOCK | Family graph nodes + lineage resolution | actor_origin.lineage_id opaque tag | FF_001 RESOLVES IDF_004 lineage_id (per ORG-D12 LOCKED) |
| IDF_001 Race Foundation | CANDIDATE-LOCK | (none) | RaceId / race_assignment | V1+ hybrid races (RAC-D3) consume FF_001 lineage for parent-race inheritance |
| IDF_005 Ideology Foundation | CANDIDATE-LOCK | (none) | actor_ideology_stance | V1+ family-default ideology pack (children inherit parent's stance at canonical seed) |
| NPC_001 Cast | CANDIDATE-LOCK | Per-NPC family relations | NPC core + canonical_actor_decl | NPC_001 declares family at canonical seed; FF_001 reads + derives graph |
| NPC_003 NPC Desires | DRAFT | (none) | npc.desires field | Independent — desires are narrative, not family-relation-driven V1 |
| PL_005 Interaction | CANDIDATE-LOCK | Family-cascade reaction trigger | InteractionKind + OutputDecl | V1+ Strike on family member → cascade opinion drift via FF_001 graph traversal |
| WA_006 Mortality | CANDIDATE-LOCK | (none) | Death state machine | Death events update FF_001 family_event_log + propagate to family_node |
| RES_001 Resource Foundation | DRAFT | (none) | resource_inventory + vital_pool | V2+ family-shared inventory (clan treasury); V1 separation |
| WA_003 Forge | CANDIDATE-LOCK | (none — FF_001 declares own AdminAction sub-shapes) | Forge audit log + AdminAction enum | FF_001 adds Forge AdminAction sub-shapes (`Forge:EditFamily` + `Forge:ResolveAdoption` + `Forge:RegisterDynasty`) |
| 07_event_model | LOCKED | EVT-T3 Derived (`aggregate_type=family_node` / `dynasty` / `family_event_log`) + EVT-T4 System sub-types (FamilyBorn at canonical seed); possibly EVT-T8 Forge admin | Event taxonomy + Generator framework | FF_001 registers sub-types per EVT-A11 |
| RealityManifest envelope | unowned (boundary contract) | `canonical_dynasties: Vec<DynastyDecl>` + `canonical_family_relations: Vec<FamilyRelationDecl>` | Envelope contract per `_boundaries/02_extension_contracts.md` §2 | V1+ optional fields; V1 minimal: declared via canonical_actors |
| `family.*` rule_id namespace | not yet registered | All family RejectReason variants | RejectReason envelope (Continuum) | Per `_boundaries/02_extension_contracts.md` §1.4 — register at FF_001 DRAFT |
| Future PCS_001 | brief | (none — FF_001 owns family) | PC identity | PCS_001 PC creation form selects family / generates orphan / ties to canonical dynasty |
| Future TIT_001 Title Foundation | not started | (none — TIT_001 V1+ consumes FF_001 graph) | Title aggregate + heir selection rules | V1+ FF_001 graph traversal feeds TIT_001 inheritance |
| Future FAC_001 Faction Foundation | not started | (none — sect membership separate) | actor_faction_membership + sect role/rank | V1+ FAC_001 covers master-disciple (sect lineage); FF_001 covers biological/adoption only |

---

## §5 — Q1-Q8 critical scope questions — ✅ ALL LOCKED 2026-04-26 (user "A" confirmation)

User confirmed "A" on all 8 Q-decisions 2026-04-26 with deep-dive analysis. Locked decisions below; FF_001 DRAFT promotion ready to proceed.

### Q1 — Aggregate model: separate family_node vs extension to actor_origin?

✅ **LOCKED 2026-04-26: (A) Separate `family_node` aggregate** (T2/Reality, per-(reality, actor_id))

**Reasoning:**
- Lifecycle differs: actor_origin immutable V1; family_node MUTABLE (Marriage/Death/Adoption events)
- Mixing immutable + mutable in one aggregate = anti-pattern (we avoided IDF_005 vs IDF_004 same way)
- Access patterns differ: actor_origin read once at canonical seed; family_node read frequently runtime
- Schema growth differs: orthogonal V1+ enrichment; "god struct" anti-pattern avoided
- Matches IDF Origin/Ideology split discipline established 2026-04-26

### Q2 — Family graph V1 scope: minimal direct vs full extended?

✅ **LOCKED 2026-04-26: (B2) Explicit direct relations V1** (parent + sibling + spouse + child); extended computed V1+

**Reasoning:**
- Direct stored explicit (parent_actor_ids + sibling_actor_ids + spouse_actor_ids + children_actor_ids — Vec<(ActorId, RelationKind)> per Q6 LOCKED)
- Bidirectional sync at canonical seed validation + Forge admin events
- O(1) hot-path lookup matters for NPC_002 reaction priority
- Half-sibling support (Wuxia common: same father different mother) via explicit refs
- Extended V1+ (cousins/uncles/aunts/in-laws/grandparents): computed via `family_node.cousins() = parent.siblings().children()` traversal API
- Matches CK3 + Bannerlord + DF storage pattern

### Q3 — Dynasty representation: separate aggregate vs derived from family graph?

✅ **LOCKED 2026-04-26: (A) Separate `dynasty` aggregate V1** (T2/Reality, per-(reality, dynasty_id)) with minimal fields V1; sparse storage (only declared dynasties)

**Reasoning:**
- V1 minimal schema: `dynasty_id` + `display_name` (I18nBundle) + `founder_actor_id: Option<ActorId>` + `current_head_actor_id: Option<ActorId>` + `member_count: u32` (sparse query helper)
- Cross-actor query "all members of House Lý" needs dynasty-as-entity; tag-only would require O(N) scan
- V1+ TIT_001 heir selection reads `dynasty.current_head_actor_id`
- V1+ enrichment additive (parent_dynasty_id for cadet branches; traditions; perks)
- Sparse storage: SPIKE_01 V1 may have 0-2 dynasties total
- Matches CK3 dynasty entity + Bannerlord clan pattern

### Q4 — Sect lineage (master-disciple): FF_001 V1 or V1+ FAC_001?

✅ **LOCKED 2026-04-26: (A) V1+ FAC_001 owns sect lineage; FF_001 V1 = biological + adoption only**

**Reasoning:**
- Mechanical separation: family = blood/heredity/inheritance; sect = role/rank/ideology
- "Sư phụ" / "sư huynh đệ" = sect ROLE (rank-based), not biological sibling
- Master-disciple inheritance = sect-leadership succession (V1+ TIT_001 + V1+ FAC_001), NOT bloodline
- All references support: CK3 (vassalage ≠ dynasty); Bannerlord (clan-retinue ≠ family); Total War 3K (sworn brotherhood ≠ family); VtM (clan-bloodline ≠ Sire — actually these are quasi-family but in CLAN system not family system)
- SPIKE_01 V1 has NO active master-disciple; V1+ wuxia content (cultivation training) needs FAC_001 V1+ first per roadmap
- Mixing biological + sect in single graph = god-feature anti-pattern; FF_001 V1 schema bloats; coupling to V1+ CULT_001 sect cultivation method

### Q5 — Family event log V1 vs V1+? ⚠ REVISION

✅ **LOCKED 2026-04-26: (B) Materialized `family_node` aggregate only**; events emitted as EVT-T3 Derived + EVT-T4 System sub-types in channel stream (NO separate `family_event_log` aggregate)

**Reasoning (key revision from initial recommendation):**
- Per [EVT-A10](../../07_event_model/02_invariants.md) (event log = universal SSOT), channel event stream IS the append-only audit log
- Separate `family_event_log` aggregate would be REDUNDANT with channel stream
- 5 V1 family event sub-types in channel stream (NOT separate aggregate):
  - **EVT-T4 System `FamilyBorn`** at canonical seed (per actor; emitted alongside EF_001 EntityBorn)
  - **EVT-T3 Derived** `aggregate_type=family_node`, delta_kind=`AddChild` (V1+ runtime birth)
  - **EVT-T3 Derived** delta_kind=`AddSpouse` (Marriage)
  - **EVT-T3 Derived** delta_kind=`MarkDeceased` (Death)
  - **EVT-T3 Derived** delta_kind=`RemoveSpouse` (Divorce V1+)
  - **EVT-T3 Derived** delta_kind=`AddAdoptedParent` (Adoption V1+)
- Pattern matches PL_006 actor_status + IDF_005 actor_ideology_stance (materialized + EVT-T3 events; no separate event log aggregate)
- V1 aggregate count drops 3 → 2 (family_node + dynasty)

### Q6 — Adoption representation V1?

✅ **LOCKED 2026-04-26: (B) Adoption flag V1 via RelationKind enum** on parent_actor_ids + children_actor_ids

**Reasoning:**
- Schema: `parent_actor_ids: Vec<(ActorId, RelationKind)>` with closed-set 6-variant RelationKind enum
- 6-variant `RelationKind`: BiologicalParent / AdoptedParent / Spouse / BiologicalChild / AdoptedChild / Sibling
- Symmetric on parent + child sides (BiologicalParent ↔ BiologicalChild; AdoptedParent ↔ AdoptedChild)
- Future-proofs without V1+ schema migration (vs single-field V1 → tagged-tuple V1+ migration would be expensive)
- Wuxia adoption (clan adopts orphan as heir) narrative-significant; adoption flag preserves history
- Master-disciple sect adoption is V1+ FAC_001 per Q4 boundary (NOT FF_001 adoption)

### Q7 — Cross-reality family migration (V1 vs V2+)?

✅ **LOCKED 2026-04-26: (A) V1 strict single-reality family**; V2+ Heresy migration

**Reasoning:**
- All IDF features locked V2+ for cross-reality (POST-SURVEY-Q6 LOCKED 2026-04-26); FF_001 inherits same discipline
- V2+ WA_002 Heresy migration handles cross-reality remap policy
- No mainstream game does cross-engine family migration; engine doesn't need precedent V1
- V1 reject `family.cross_reality_mismatch` (V2+ reservation; V1 unused)

### Q8 — Bloodline traits (cultivator spirit roots) V1 or V1+?

✅ **LOCKED 2026-04-26: (A) V1+ deferred bloodline traits** (FF-D1 NEW); FF_001 V1 = pure graph

**Reasoning:**
- V1 inclusion would couple FF_001 to V1+ RAC-D3 (hybrid races) + V1+ CULT_001 (spirit roots) — neither feature ships V1
- V1+ trait-inheritance features READ FF_001 graph; FF_001 graph doesn't NEED to know about traits
- Schema impact V1: zero. V1+ RAC-D3 + CULT_001 activation read FF_001 graph without modifying FF_001 schema
- FF_001 V1 = pure graph (parents/siblings/spouse/child + dynasty)
- Trait inheritance V1+ when first feature consumes per FF-D1

---

## §6 — Reference materials placeholder

User stated 2026-04-26 (in earlier RES_001 + IDF context): may provide reference sources for cross-reference. FF_001 follows same pattern.

This section reserved for:
- User-provided reference docs / design notes / external game references for family/dynasty mechanics
- Main session compares user's references against internal knowledge (CK3 / Bannerlord / Total War 3K / Stellaris / xianxia novels / D&D backgrounds / VtM clans)
- Updates Q1-Q8 recommendations based on combined references

**Status:** awaiting user input. When references arrive:
1. Capture verbatim (preserve user's preferred terminology)
2. Cross-reference with main session's known patterns (already in `01_REFERENCE_GAMES_SURVEY.md` companion)
3. Update Q1-Q8 in §5 with revised recommendations + lock LOCKED decisions in §10 (added at promotion time)

---

## §7 — V1 scope ✅ LOCKED 2026-04-26 (post Q1-Q8 deep-dive + user "A" confirmation)

### V1 aggregates (2 — revised down from 3 per Q5)

1. **`family_node`** (T2/Reality, per-(reality, actor_id))
   - Direct relations: parent_actor_ids + sibling_actor_ids + spouse_actor_ids + children_actor_ids — all `Vec<(ActorId, RelationKind)>` per Q2 + Q6
   - dynasty_id: Option<DynastyId> (membership; None for non-dynasty actors)
   - is_deceased: bool + deceased_at_turn / deceased_at_fiction_ts (V1 mark deceased; preserve refs)
   - last_modified_at_turn + schema_version
   - **Mutable** via Apply/MarkDeceased events per Q5

2. **`dynasty`** (T2/Reality, per-(reality, dynasty_id); sparse — only declared dynasties)
   - dynasty_id + display_name (I18nBundle per RES_001) + founder_actor_id (Option) + current_head_actor_id (Option) + member_count (sparse query helper)
   - V1+ enrichment: parent_dynasty_id (cadet branch); traditions; perks
   - **Mutable** via succession events V1+

### V1 closed enums

- **`RelationKind`** (6 variants per Q6): BiologicalParent / AdoptedParent / Spouse / BiologicalChild / AdoptedChild / Sibling

### V1 events (in channel stream per Q5; NOT separate aggregate per EVT-A10)

| Event | EVT-T* | Sub-type / delta_kind | Producer role |
|---|---|---|---|
| Canonical seed family birth | EVT-T4 System | `FamilyBorn { actor_id, parent_refs, dynasty_id }` | Bootstrap (RealityBootstrapper) |
| V1+ runtime birth | EVT-T3 Derived | `aggregate_type=family_node`, `delta_kind=AddChild` | Aggregate-Owner (FF_001 owner-service) |
| Marriage | EVT-T3 Derived | `delta_kind=AddSpouse` | Aggregate-Owner |
| Death | EVT-T3 Derived | `delta_kind=MarkDeceased` | Aggregate-Owner (consumes WA_006 mortality death) |
| Divorce (V1+) | EVT-T3 Derived | `delta_kind=RemoveSpouse` | Aggregate-Owner |
| Adoption (V1+) | EVT-T3 Derived | `delta_kind=AddAdoptedParent` | Aggregate-Owner |
| Forge admin override | EVT-T8 Administrative | `Forge:EditFamily { actor_id, edit_kind, before, after, reason }` | Forge (WA_003) |
| Forge dynasty register | EVT-T8 Administrative | `Forge:RegisterDynasty { dynasty_id, display_name, founder, reason }` | Forge (WA_003) |

### V1 `family.*` reject rule_ids (8 V1 + V1+ reservations)

V1 rules:
1. `family.unknown_actor_ref` — Stage 0 schema (parent/sibling/spouse/child ref not in EF_001 entity_binding)
2. `family.unknown_dynasty_id` — Stage 0 schema (dynasty_id not in RealityManifest.canonical_dynasties + dynasty aggregate)
3. `family.bidirectional_sync_violation` — Stage 0 schema (LM01 says X is parent but X doesn't list LM01 as child)
4. `family.cyclic_relation` — Stage 0 schema (LM01 is parent of X is parent of LM01 — cycle)
5. `family.duplicate_relation` — Stage 0 schema (same actor twice in parent_actor_ids)
6. `family.relation_kind_mismatch` — Stage 0 schema (parent_actor_ids has BiologicalChild variant — wrong side)
7. `family.deceased_target` — Stage 7 world-rule (V1+ Marriage event with deceased target)
8. `family.synthetic_actor_forbidden` — Stage 0 schema (Synthetic actor cannot have family — matches IDF discipline)

V1+ reservations:
- `family.cross_reality_mismatch` (V2+ Heresy migration per Q7)
- `family.cyclic_lineage_traversal` (V1+ when extended traversal API ships)
- `family.dynasty_extinction` (V1+ when no living members; cleanup rule)
- `family.adoption_consent_violation` (V1+ V2+ if consent system ships)

### V1 RealityManifest extensions (REQUIRED V1)

- `canonical_dynasties: Vec<DynastyDecl>` — per-reality declared dynasties (sparse; empty Vec valid for sandbox / family-less reality)
- `canonical_family_relations: Vec<FamilyRelationDecl>` — per-reality declared family relations at canonical seed (sparse; empty Vec valid for orphan-PC reality)

`DynastyDecl` shape:
```rust
pub struct DynastyDecl {
    pub dynasty_id: DynastyId,
    pub display_name: I18nBundle,
    pub founder_actor_id: Option<ActorId>,
    pub canon_ref: Option<GlossaryEntityId>,
}
```

`FamilyRelationDecl` shape:
```rust
pub struct FamilyRelationDecl {
    pub actor_id: ActorId,
    pub parent_actor_ids: Vec<(ActorId, RelationKind)>,    // V1 RelationKind: BiologicalParent | AdoptedParent
    pub sibling_actor_ids: Vec<ActorId>,
    pub spouse_actor_ids: Vec<ActorId>,
    pub children_actor_ids: Vec<(ActorId, RelationKind)>,  // V1 RelationKind: BiologicalChild | AdoptedChild
    pub dynasty_id: Option<DynastyId>,
    pub is_deceased: bool,                                  // for canonical-seed dead ancestors
}
```

### V1 acceptance criteria (10 V1-testable + 4 V1+ deferred)

V1:
- AC-FF-1: Wuxia canonical bootstrap declares 1 dynasty (Lý clan) + 1 actor (Lý Minh) with parent_actor_ids=[] (orphan)
- AC-FF-2: Wuxia canonical bootstrap declares Lão Ngũ (parent of Tiểu Thúy); FF_001 derives bidirectional refs
- AC-FF-3: Bidirectional sync violation rejected at canonical seed (LM01 says Tiểu Thúy is sibling but Tiểu Thúy doesn't list LM01)
- AC-FF-4: Cyclic relation rejected (canonical seed validation)
- AC-FF-5: Duplicate relation rejected
- AC-FF-6: Relation kind mismatch rejected (BiologicalChild on parent side)
- AC-FF-7: Modern reality canonical bootstrap with 1 PC + 2 parents alive + 0 dynasty
- AC-FF-8: Marriage event emits EVT-T3 Derived AddSpouse; spouse_actor_ids updated bidirectionally
- AC-FF-9: Death event emits EVT-T3 Derived MarkDeceased; family_node.is_deceased=true; refs preserved
- AC-FF-10: I18nBundle resolves dynasty display_name across locales

V1+ deferred:
- AC-FF-V1+1: Extended traversal API (cousins / uncles / aunts)
- AC-FF-V1+2: V1+ runtime birth event (PC has child)
- AC-FF-V1+3: V1+ Divorce event flow
- AC-FF-V1+4: V1+ Adoption runtime event flow

### V1 deferrals (12 — FF-D1..D12)

- FF-D1: Bloodline traits inheritance (V1+ RAC-D3 hybrid races + V1+ CULT_001 spirit roots consume FF_001 graph)
- FF-D2: Extended traversal API (cousins / uncles / aunts / in-laws / grandparents)
- FF-D3: Cadet dynasty branches (parent_dynasty_id field)
- FF-D4: Dynasty traditions / perks (V1+ V2+ enrichment matching CK3)
- FF-D5: Marriage as faction alliance currency (V1+ FAC_001 + V1+ DIPL_001)
- FF-D6: Sworn brotherhood (V1+ FAC_001 — NOT FF_001 per Q4)
- FF-D7: Master-disciple sect lineage (V1+ FAC_001 — NOT FF_001 per Q4)
- FF-D8: Title inheritance rules (V1+ TIT_001)
- FF-D9: Cross-reality family migration (V2+ WA_002 Heresy per Q7)
- FF-D10: Family-driven cascade opinion drift (V1+ NPC_002 enrichment)
- FF-D11: V1+ runtime birth/divorce/adoption event flows (V1 canonical seed only V1)
- FF-D12: Family-shared inventory / clan treasury (V2+ RES_001 enrichment)

### V1 quantitative summary

- 2 aggregates (family_node + dynasty)
- 6-variant RelationKind enum
- 5 V1 family event variants (FamilyBorn EVT-T4 System + 4 EVT-T3 Derived: AddChild/AddSpouse/MarkDeceased/RemoveSpouse/AddAdoptedParent — V1 ships 3 actively: AddSpouse + MarkDeceased + canonical FamilyBorn; AddChild/RemoveSpouse/AddAdoptedParent V1+ runtime activation)
- 8 V1 reject rule_ids in `family.*` namespace + 4 V1+ reservations
- 2 RealityManifest extensions (canonical_dynasties + canonical_family_relations)
- 2 EVT-T8 Forge sub-shapes (Forge:EditFamily + Forge:RegisterDynasty)
- 1 EVT-T4 System sub-type (FamilyBorn)
- 10 V1 AC + 4 V1+ deferred
- 12 deferrals (FF-D1..D12)
- ~700-line DRAFT spec estimate
- 4-commit cycle (lock-Qs → DRAFT → Phase 3 → closure+release)

---

## §8 — What this concept-notes file is NOT

- ❌ NOT the formal FF_001 design (no Rust struct definitions, no full §1-§N section structure, no acceptance criteria)
- ❌ NOT a lock-claim trigger (no `_boundaries/_LOCK.md` claim made for this notes file)
- ❌ NOT registered in ownership matrix yet (deferred to FF_001 DRAFT promotion)
- ❌ NOT consumed by other features yet (IDF_004 lineage_id retains opaque V1 status until FF_001 DRAFT supersedes)
- ❌ NOT prematurely V1-scope-locked (Q1-Q8 OPEN; recommendations pending reference materials review)

---

## §9 — Promotion checklist (when Q1-Q8 answered + references reviewed)

Before drafting `FF_001_family_foundation.md`:

1. [ ] User reviews market survey (`01_REFERENCE_GAMES_SURVEY.md` companion) + provides additional references if any
2. [ ] User answers Q1-Q8 (or approves recommendations after deep-dive)
3. [ ] Update §7 V1 scope based on locked decisions
4. [ ] Wait for `_boundaries/_LOCK.md` to be free
5. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL)
6. [ ] Create `FF_001_family_foundation.md` with full §1-§N spec mirroring EF/PF/MAP/CSC/RES/IDF pattern
7. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — add family_node + dynasty + family_event_log aggregates (per Q1+Q3+Q5 decisions)
8. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 — add `family.*` RejectReason prefix
9. [ ] Update `_boundaries/02_extension_contracts.md` §2 — add RealityManifest `canonical_dynasties` + `canonical_family_relations` extensions
10. [ ] Update `_boundaries/99_changelog.md` — append entry
11. [ ] Create `catalog/cat_00_FF_family_foundation.md` — feature catalog
12. [ ] Update `00_family/_index.md` — replace concept row with FF_001 DRAFT row
13. [ ] Coordinate with IDF_004 closure pass extension to update lineage_id resolution mechanism
14. [ ] Coordinate with NPC_001 closure pass to fold NPC family declaration (per Q2 decision)
15. [ ] Update `features/_index.md` to add `00_family/` to layout + table
16. [ ] Release `_boundaries/_LOCK.md`
17. [ ] Commit with `[boundaries-lock-claim+release]` prefix (single commit) OR `[boundaries-lock-claim]` if multi-commit DRAFT cycle

---

## §10 — Status

- **Created:** 2026-04-26 by main session (commit this turn)
- **Phase:** CONCEPT — awaiting Q1-Q8 deep-dive + market survey review
- **Lock state:** `_boundaries/_LOCK.md` free as of this commit (released by IDF folder closure 50d65fa)
- **Estimated time to DRAFT (post-Q-deep-dive):** 3-5 hours focused design work (smaller than RES_001/PROG_001 due to clearer scope; family system has well-established game patterns)
- **Co-design dependencies (when DRAFT):**
  - IDF_004 closure pass extension folds in lineage_id resolution
  - NPC_001 closure pass extension folds in NPC family declaration (per Q2)
  - WA_006 closure cross-ref folds in death event family cascade
  - Future PCS_001 PC creation form will reference FF_001 + dynasty selection
  - Future TIT_001 + FAC_001 V1+ consume FF_001 graph
- **Next action:** User reviews market survey companion + answers Q1-Q8 (or approves recommendations) → DRAFT promotion

---

## §11 — Cross-references

**Foundation tier:**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types) — source-of-truth for actor_id in family_node
- [`IDF_004 ORG-D12`](../00_identity/IDF_004_origin.md) — locks FF_001 as HIGH priority post-IDF closure
- [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md) — display_name for DynastyDecl

**Sibling IDF (consumers):**
- [`IDF_004 Origin`](../00_identity/IDF_004_origin.md) — lineage_id opaque V1; FF_001 V1+ resolves
- [`IDF_001 Race`](../00_identity/IDF_001_race.md) RAC-D3 — V1+ hybrid races consume lineage
- [`IDF_005 Ideology`](../00_identity/IDF_005_ideology.md) — V1+ family-inherited ideology default

**Future consumers (V1+):**
- Future PCS_001 — PC creation form
- Future NPC_NNN_mortality — death cascades
- Future TIT_001 Title Foundation — heir succession
- Future FAC_001 Faction Foundation — clan-as-faction (overlap; sect lineage in FAC_001 not FF_001 per Q4)

**Spike + research:**
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Wuxia content (Lý Minh + Lão Ngũ + Tiểu Thúy family graph)
- [`_research_character_systems_market_survey.md` §5.5](../00_identity/_research_character_systems_market_survey.md) — family graph + dynasty pattern across grand-strategy games
- [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) — FF_001-specific reference games survey (companion to this concept-notes)

**Boundaries (DRAFT registers):**
- `_boundaries/01_feature_ownership_matrix.md` — family_node + dynasty + family_event_log aggregates
- `_boundaries/02_extension_contracts.md` §1.4 — `family.*` namespace
- `_boundaries/02_extension_contracts.md` §2 RealityManifest — canonical_dynasties + canonical_family_relations
- `_boundaries/02_extension_contracts.md` Stable-ID prefix — `FF-*`
