# FF_001 Family Foundation — Reference Games Survey

> **Purpose:** Survey family / dynasty / lineage systems in established grand-strategy + RPG + tabletop games. Inform FF_001 V1 scope decisions (Q1-Q8 in `00_CONCEPT_NOTES.md` §5).
>
> **Status:** DRAFT 2026-04-26 — Phase 0 companion to FF_001 concept-notes. User may supplement with additional reference materials per `00_CONCEPT_NOTES.md` §6 placeholder.
>
> **Reuses:** `_research_character_systems_market_survey.md` (commit `34d5814`) §5.5 family graph + dynasty patterns. This file extends with FF_001-specific deep-dive.

---

## §1 — Methodology

8 reference games surveyed across 4 genres + 2 tabletop systems. Per-system evaluation on FF_001 dimensions:

1. Graph topology (parent/sibling/spouse/child + extended)
2. Dynasty representation (separate aggregate vs derived)
3. Family event log (Birth/Marriage/Death/Divorce/Adoption)
4. Adoption representation
5. Title inheritance interaction
6. Cross-faction marriage politics
7. Death cascade reactions

| System | Genre | Why included |
|---|---|---|
| **Crusader Kings 3** | Grand strategy / character RP | **Most detailed family/dynasty system in mainstream gaming** — gold standard reference |
| **Mount & Blade: Bannerlord** | Action RP / strategy | Clan + family + companion relations; medium complexity |
| **Total War: Three Kingdoms** | RTS / character RP | Wuxia-adjacent (Han China) — sworn brotherhood + family + court |
| **Stellaris** | 4X strategy | Ruler succession + dynasty (less dense than CK3) |
| **Europa Universalis IV** | Grand strategy | Royal marriage = country alliance pattern |
| **Dwarf Fortress** | Colony sim | Full family graph simulation; NPC reproduction; relations tracked |
| **D&D 5e** | Tabletop | Background-driven family (narrative; mechanically minimal) |
| **Vampire: The Masquerade** | Tabletop / RPG | Sire (vampire-parent) + clan (extended bloodline-family) — quasi-family pattern |

---

## §2 — Per-system deep-dive

### §2.1 Crusader Kings 3 — gold standard

**Family graph topology:**
- Direct: parents (mother + father) + siblings + spouse(s) (V1 + concubines optional) + children
- Extended: cousins / uncles / aunts / in-laws — computed via traversal
- Tracked across 1000+ years of game time; multi-generational continuity

**Dynasty system:**
- Explicit Dynasty entity (e.g., "House Plantagenet")
- Dynasty members share genetic markers + traditions + reputation
- Dynasty head (current) tracks succession claims
- Cadet branches = sub-dynasties with shared founder
- Dynasty perks (CK3 mechanic — V1+ for FF_001)

**Family event log:**
- Birth events (per child; with father confirmation rules — bastardy detection)
- Marriage events (alliance + dowry mechanics)
- Death events (succession trigger + grief decisions)
- Divorce events (rare; faith-gated)
- Adoption events (limited; usually for "ward" mechanic — fostering child between dynasties)

**Adoption representation:**
- Wards (children fostered in another house) — quasi-adoption with relations to BOTH biological + foster families
- Bastard recognition vs disownment — flag-based
- Adopted heirs in some succession laws (uncommon)

**Title inheritance:**
- Multiple succession laws (gavelkind / primogeniture / elective / etc.)
- Heir designation per law + dynasty members
- "Pretender" claims trigger civil wars

**Cross-faction marriage:**
- Royal marriages = political alliance currency
- Marriage opens diplomatic options + territorial claims via children

**Death cascade:**
- Family members react (grief negative event for close kin)
- Avenge-quest schemes (V1+ in LoreWeave terminology)
- Inheritance triggers heir's accession events

**Mapping to FF_001 V1:**

| CK3 feature | FF_001 V1 mapping | Notes |
|---|---|---|
| Direct family graph | ✅ V1 essential | parent/sibling/spouse/child Vec<ActorId> |
| Dynasty entity | ✅ V1 (per Q3) | Separate dynasty aggregate proposed |
| Family event log | ✅ V1 (per Q5 hybrid recommendation) | Birth/Marriage/Death V1; Divorce/Adoption variants |
| Cadet branches | ❌ V1+ enrichment | V1+ dynasty.parent_dynasty_id field |
| Dynasty perks | ❌ V1+ V2+ feature | Out of FF_001 scope |
| Bastardy detection | ❌ V1+ (relation_kind enum extension) | V1 simple; V1+ flag |
| Multiple succession laws | ❌ V1+ TIT_001 owns | Inheritance rules out of FF_001 |
| Pretender claims / civil wars | ❌ V1+ FAC_001 + V1+ DIPL_001 | Faction-scale events out of FF_001 |

### §2.2 Mount & Blade: Bannerlord — clan-driven

**Family graph topology:**
- Per-actor: parents + siblings + spouse + children + companions
- Clan = small dynasty; ~10 members typical (including non-blood companions)
- Clan members move together (party formation)

**Clan = quasi-family:**
- Clan members share clan tier + reputation
- Clan tier 0-6 (capacity for parties + lord positions)
- Clan can include non-blood retainers (companions formally NOT clan-blood but loyalty-sworn)

**Family events:**
- Marriage (faction alliance via daughter's marriage to another lord's son)
- Birth (children grow over game years; become eligible for parties at adulthood)
- Death (battlefield + age + execution)
- Inheritance of clan leadership

**Cross-clan marriage:**
- Player can negotiate marriages for sister/daughter to ally lord
- Marriage = clan-faction alliance proxy

**Mapping to FF_001 V1:**

| Bannerlord feature | FF_001 V1 mapping | Notes |
|---|---|---|
| Per-actor family relations | ✅ V1 (similar to CK3) | Direct refs |
| Clan = retinue / quasi-family | ⚠️ Partial — V1+ FAC_001 owns clan-as-faction | FF_001 = blood-only; FAC_001 = clan retinue |
| Companion non-blood loyalty | ❌ V1+ FAC_001 | Companions are sect/retinue not family |
| Marriage as faction alliance | ❌ V1+ DIPL_001 + V1+ FAC_001 | Out of FF_001 V1 |

### §2.3 Total War: Three Kingdoms — Wuxia-adjacent

**Family + sworn brotherhood:**
- 桃园三结义 (Peach Garden Oath) sworn brothers — quasi-family
- Han China context; family + sworn brotherhood + court politics
- Family graph similar to CK3 but smaller scale (~20 characters per faction)

**Sworn brotherhood:**
- Three Kingdoms tropé: Liu Bei + Guan Yu + Zhang Fei sworn brothers
- Mechanically: bonded relationship (loyalty + shared death triggers)
- NOT biological family but treated similar (mechanic-wise)

**Mapping to FF_001 V1 (key takeaway):**
- Sworn brotherhood is QUASI-family but mechanically lives in V1+ FAC_001 or V1+ relationship aggregate
- FF_001 stays biological/adoption only per Q4 boundary
- Wuxia "kết nghĩa huynh đệ" maps to V1+ FAC_001 sworn-bond mechanic (not FF_001)

### §2.4 Stellaris — ruler succession

**Lite family system:**
- Empire ruler with successor designation
- Ruler personality + traits inherited (loosely)
- Death/abdication triggers heir accession

**Mapping to FF_001 V1:**
- Stellaris depth too shallow for direct FF_001 reference
- Confirms: succession-as-event pattern (V1+ TIT_001)

### §2.5 Europa Universalis IV — royal marriage as alliance

**Pattern:**
- Royal marriage between two countries = diplomatic alliance proxy
- Marriage opens trade + military access
- Inheritance claims via marriage (lapse to descendant)

**Mapping to FF_001 V1:**
- Confirms: marriage event is alliance currency (V1+ DIPL_001 + V1+ FAC_001)
- FF_001 V1 doesn't ship faction politics; just the marriage event itself

### §2.6 Dwarf Fortress — full simulation

**Highest-resolution family simulation:**
- Per-dwarf full family graph + extended (cousins / uncles / aunts / etc.)
- NPCs reproduce + age + die organically
- Relations tracked across multiple cells / sites

**Mapping to FF_001 V1:**
- DF is "rich V1+ vision" — confirms full graph viable
- FF_001 V1 narrows: minimal V1 + extended computed V1+ (per Q2 (B) recommendation)

### §2.7 D&D 5e — narrative family (background-driven)

**Pattern:**
- Family declared in PC background (e.g., "Folk Hero" background mentions parents)
- Mechanically minimal (no auto-generated graph)
- Player + DM author family freely

**Mapping to FF_001 V1:**
- Confirms: V1 minimal stub + author-declared canonical seeds
- LoreWeave's reality canonical_actors declaration is similar pattern

### §2.8 Vampire: The Masquerade — sire + clan-as-bloodline

**Distinctive pattern:**
- Sire = vampire-parent (who turned you)
- Clan = vampire bloodline (extended sire chain — quasi-family)
- 13 V1 clans; each clan member shares Discipline (genetic-quasi inheritance)

**Mapping to FF_001 V1:**
- Sire = quasi-parent (lives in V1+ FAC_001 sect-membership-with-creator-rank — separate from biological)
- Clan = quasi-dynasty (lives in V1+ FAC_001 faction; matches IDF_001 race tier indirectly)
- Confirms: separation discipline (biological in FF_001; quasi-family in FAC_001)

---

## §3 — Cross-system pattern observations

### §3.1 Pattern: separate family-graph from faction/clan

**All major references** that have BOTH biological + sworn/clan/sect relations explicitly separate them mechanically:
- CK3: dynasty (blood) + court (sworn / vassalage)
- Bannerlord: family (blood) + clan retinue (companions sworn)
- Total War 3K: family (blood) + sworn brotherhood (bonded)
- VtM: clan (bloodline-quasi) + coterie (sworn)

**Validates FF_001 vs FAC_001 boundary:**
- FF_001 = biological + adoption (continuous bloodline)
- FAC_001 = sect / order / sworn relationships (V1+ when designed)

### §3.2 Pattern: Direct relations + computed extended

**CK3 + Bannerlord + DF** all store direct relations explicitly + compute extended on-demand:
- Per-actor: parents (mother + father) + spouse + children — explicit
- Cousins / uncles / etc. — computed via traversal

**Validates Q2 (B):** V1 stores direct; computes extended via traversal V1+ (no upfront cost).

### §3.3 Pattern: Event log as audit + state derivation

**CK3 + DF** have implicit / explicit event log for family changes:
- Birth events + Marriage events + Death events recorded
- Replay-deterministic graph derivation

**Validates Q5 (C) hybrid:** V1 family_node materialized for hot-path + family_event_log append-only audit.

### §3.4 Pattern: Adoption flag (relation_kind enum)

**CK3 + DF** distinguish biological vs adopted via flag:
- Wards (CK3) marked separately from biological children
- Adoption events explicit (rare but present)

**Validates Q6 (B):** V1 ships parent_actor_ids: Vec<(ActorId, RelationKind)> with BiologicalParent / AdoptedParent variants. Wuxia common: master accepts orphan disciple — but per Q4 boundary, that's V1+ FAC_001 (sect) not FF_001 (family).

### §3.5 Pattern: Cross-reality migration absent

**No mainstream game** does cross-engine family migration:
- CK3 / EU4 / Bannerlord — all single-engine; family stays in one game session
- DF — colony-bound

**Validates Q7 (A):** V1 strict single-reality family; V2+ Heresy migration when first cross-reality mechanic ships.

---

## §4 — Wuxia-specific patterns (SPIKE_01 context)

### §4.1 Sect lineage (master-disciple)

Wuxia common: 师父 (sư phụ — master) + 弟子 (đệ tử — disciple).

**Mechanically distinct from biological family:**
- Master accepts disciple (acceptance event ≠ adoption)
- Disciple inherits master's martial style (V1+ CULT_001 cultivation method) — NOT bloodline
- Sect-leader succession follows sect rules (V1+ TIT_001 + V1+ FAC_001 sect leadership)
- "Sư huynh" / "sư đệ" = elder/younger disciple-brother — RANK within sect (not biological sibling)

**Decision per Q4 (A):** FF_001 = biological + adoption only. Master-disciple lives in V1+ FAC_001 sect-membership with role/rank. This matches CK3 court (vassalage) + VtM clan-as-bloodline (sire) patterns.

### §4.2 Clan rivalry (gia tộc liên hôn)

Wuxia common: clan A daughter marries clan B son → political alliance.

**Mapping:**
- FF_001 V1 ships marriage event
- V1+ DIPL_001 + V1+ FAC_001 use marriage as alliance currency
- V1+ NPC_002 enrichment: clan rival NPCs get baseline opinion modifier

### §4.3 Hereditary cultivation (V1+)

Wuxia common: 灵根 (linh căn — spirit root) inherited from parents.

**Mapping:**
- FF_001 V1 provides graph
- V1+ RAC-D3 hybrid races + V1+ CULT_001 cultivation spirit roots consume FF_001 lineage
- Inheritance rule per V1+ feature (not FF_001)

### §4.4 Heritable bloodline curse (V1+)

Wuxia common: 血脉诅咒 (huyết mạch trù chú — bloodline curse) inherited.

**Mapping:**
- FF_001 V1 provides graph
- V1+ Status Effect (PL_006 extension) + V1+ tenet system handle curse mechanic

---

## §5 — Recommendations summary

Based on §2-§4 survey, recommendations for FF_001 Q1-Q8:

| Q | Question | Recommendation |
|---|---|---|
| **Q1** | Aggregate model | **(A) Separate family_node aggregate** (T2/Reality, per-actor) — clean separation; matches IDF discipline |
| **Q2** | Family graph V1 scope | **(B) Direct + computed extended V1** — store direct (parent/sibling/spouse/child); compute cousins/uncles on-demand traversal V1+ |
| **Q3** | Dynasty representation | **(A) Separate dynasty aggregate** (T2/Reality, per-dynasty_id) — explicit clustering matches CK3 + V1+ TIT_001 + V1+ FAC_001 consumers |
| **Q4** | Sect lineage (master-disciple) | **(A) V1+ FAC_001** — sect membership lives in FAC_001; FF_001 = biological/adoption only (matches CK3 + VtM patterns) |
| **Q5** | Family event log V1 | **(C) Hybrid** — family_node materialized for hot-path + family_event_log append-only audit (matches actor_status / actor_ideology_stance pattern) |
| **Q6** | Adoption representation | **(B) Adoption flag V1** — parent_actor_ids: Vec<(ActorId, RelationKind)> with BiologicalParent / AdoptedParent variants; matches CK3 wards |
| **Q7** | Cross-reality migration | **(A) V1 strict** — single-reality family; V2+ Heresy migration |
| **Q8** | Bloodline traits | **(A) V1+ deferred** — FF_001 V1 = pure graph; V1+ RAC-D3 + V1+ CULT_001 consume |

**V1 minimum scope (per recommendations):**

- 3 aggregates: `family_node` (per-actor) + `dynasty` (per-dynasty_id) + `family_event_log` (append-only)
- 5 V1 family event variants: Birth / Marriage / Death / Divorce / Adoption
- RelationKind enum: BiologicalParent / AdoptedParent / Spouse / BiologicalChild / AdoptedChild / Sibling
- RealityManifest extensions: `canonical_dynasties: Vec<DynastyDecl>` + `canonical_family_relations: Vec<FamilyRelationDecl>` (REQUIRED V1; empty Vec valid for sandbox)
- 8 V1 reject rule_ids in `family.*` namespace
- 1 EVT-T8 sub-shape: `Forge:EditFamily` (admin override)

**V1+ deferrals (declared NOW):**

- Cousins / uncles / aunts / in-laws traversal API
- Cadet dynasty branches (parent_dynasty_id)
- Hereditary bloodline traits (FF-D-NEW; consume V1+ RAC-D3 + V1+ CULT_001)
- Cross-reality family migration (V2+)
- Master-disciple sect lineage (V1+ FAC_001)
- Marriage-as-alliance currency (V1+ DIPL_001 + V1+ FAC_001)
- Sworn brotherhood (V1+ FAC_001)
- Title inheritance (V1+ TIT_001)

**Quantitative V1 estimate:**
- ~600-800 line DRAFT spec (smaller than RES_001 or PROG_001 due to clearer scope)
- 10 V1 acceptance scenarios + 4 V1+ deferred
- 12-15 deferrals (FF-D1..D15)
- 5-8 commit cycle (DRAFT + Phase 3 + closure mirror PL/IDF pattern)

---

## §6 — Status

- **Created:** 2026-04-26 by main session (commit this turn alongside `00_CONCEPT_NOTES.md`)
- **Phase:** Reference survey complete — recommendations §5 form basis for Q1-Q8 deep-dive
- **Next action:** User reviews recommendations + provides additional reference materials if any → Q-deep-dive batch (similar to RES_001 Q1-Q5 + Q6-Q12 batches; estimated 6-10 turns) → DRAFT promotion

---

## §7 — Cross-references

**Foundation tier:**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types)
- [`IDF_004 ORG-D12`](../00_identity/IDF_004_origin.md) — V1+ FF_001 priority signal

**Companion concept-notes:**
- [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) — user framing + 12-dim gap + Q1-Q8

**Prior art:**
- [`_research_character_systems_market_survey.md` §5.5`](../00_identity/_research_character_systems_market_survey.md) — character + society systems survey (cross-references multiple games)
- [`features/00_resource/01_REFERENCE_GAMES_SURVEY.md`](../00_resource/01_REFERENCE_GAMES_SURVEY.md) — RES_001 reference survey precedent
