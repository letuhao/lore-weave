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

## §5 — Q1-Q8 critical scope questions

These 8 questions lock V1 scope. Once user has reviewed market survey + answered (or approved recommendations), FF_001 DRAFT can proceed.

### Q1 — Aggregate model: separate family_node vs extension to actor_origin?

- **(A) Separate family_node aggregate** (T2/Reality, per-actor) — clean separation; matches IDF discipline
- **(B) Extend actor_origin** (IDF_004) with family_relations field — embedded; no new aggregate
- **(C) Hybrid** — family_node aggregate for graph; lineage_id stays in actor_origin as legacy ref

**Open** — recommendation likely (A) for clean separation; matches IDF_005 ideology vs IDF_004 origin discipline.

### Q2 — Family graph V1 scope: minimal direct vs full extended?

- **(A) Minimal V1** — parent / sibling / spouse / child only (4 direct relations); cousins/uncles/in-laws V1+
- **(B) Direct + computed extended V1** — store direct; compute extended on-demand traversal
- **(C) Full V1** — store all relation kinds explicit; expensive but no traversal cost

**Open** — likely (A) or (B). (A) is narrowest; (B) is reasonable hybrid.

### Q3 — Dynasty representation: separate aggregate vs derived from family graph?

- **(A) Separate `dynasty` aggregate** (T2/Reality, per-dynasty_id) — explicit clustering; supports cross-actor dynasty queries
- **(B) Derived from family graph traversal** — no dynasty aggregate; clustering computed
- **(C) Tag on family_node** — dynasty_id field per family_node; no separate aggregate

**Open** — likely (A) for V1+ TIT_001 + V1+ FAC_001 consumers; (C) defensible if V1 dynasty mechanics are minimal.

### Q4 — Sect lineage (master-disciple): FF_001 V1 or V1+ FAC_001?

- **(A) V1+ FAC_001** — sect membership lives in FAC_001; master-disciple = sect role/rank; FF_001 = biological/adoption only (cleanest separation)
- **(B) FF_001 V1 with relation_kind enum** — Family relation includes BiologicalParent / AdoptedParent / SpiritualParent (sect master); unified graph
- **(C) FF_001 V1 with sect_lineage_id field** — separate sect lineage tag; biological in family_node; sect in sect_lineage

**Open** — recommendation (A) per separation discipline (IDF_004 origin vs IDF_005 ideology pattern). Wuxia narrative treats master-disciple as quasi-family but mechanics differ (rank progression vs heredity).

### Q5 — Family event log V1 vs V1+?

- **(A) V1 append-only event_log** (Birth/Marriage/Death/Divorce/Adoption) — full audit + replay-deterministic graph derivation
- **(B) V1 materialized only** (family_node holds direct refs; no event log) — V1+ adds event log
- **(C) V1 hybrid** — family_node for hot-path reads + event_log for audit (matches actor_status / actor_ideology_stance pattern)

**Open** — recommendation (C) per established pattern. V1 materialized + event_log audit; V1+ scheduler reads event_log for derivative analytics.

### Q6 — Adoption representation V1?

- **(A) Same as biological V1** — single parent_actor_ids field; no flag (hides adoption fact V1)
- **(B) Adoption flag V1** — parent_actor_ids: Vec<(ActorId, RelationKind)> with BiologicalParent / AdoptedParent variants
- **(C) Defer V1+** — V1 biological only; adoption V1+ enrichment

**Open** — recommendation (B) for clarity (wuxia adoption is narrative-significant). V1+ may add full adoption-event flow.

### Q7 — Cross-reality family migration (V1 vs V2+)?

- **(A) V1 strict** — actor's family is bound to one reality; cross-reality migration V2+ Heresy
- **(B) V1+ remap policy** — when actor moves realities, family graph remap rules

**Open** — recommendation (A) per IDF folder discipline (POST-SURVEY-Q6 LOCKED V2+ for cross-reality migration).

### Q8 — Bloodline traits (cultivator spirit roots) V1 or V1+?

- **(A) V1+ deferred** — RAC-D3 hybrid races + V1+ CULT_001 cultivation spirit roots; FF_001 V1 just provides graph for V1+ traits to consume
- **(B) V1 minimal trait** — one inherited trait field (e.g., `inherited_traits: Vec<String>`) for V1+ activation
- **(C) V1 full** — bloodline trait system shipped V1 with race + cultivation hooks

**Open** — recommendation (A) per "narrow V1 + define NOW for V+" philosophy. FF_001 V1 = pure graph; trait inheritance V1+ when first feature needs.

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

## §7 — Provisional V1 scope (placeholder — finalized after Q1-Q8 lock)

This section is INTENTIONALLY EMPTY pending Q1-Q8 + reference materials review. Premature V1 scope locking before deep-dive risks RES_001-pattern issues (original recommendations changed during Q1-Q5 batch deep-dive).

When user provides references + answers Q1-Q8, populate with:
- Aggregate decision (per Q1) + storage model (per Q5)
- Family graph V1 scope (per Q2) — minimal direct vs full extended
- Dynasty representation (per Q3)
- Master-disciple boundary (per Q4) — FF_001 V1 vs V1+ FAC_001
- Family event taxonomy V1 (per Q5)
- Adoption representation (per Q6)
- Cross-reality V1 stance (per Q7)
- Bloodline trait inheritance V1 vs V1+ (per Q8)
- RealityManifest extensions (canonical_dynasties + canonical_family_relations)
- Validator chain (`family.*` namespace)
- EVT-T sub-types (T3 Derived family_node + T4 System FamilyBorn / Marriage / Death — V1 mapping per Q5)
- Acceptance criteria sketch (10 V1-testable AC)

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
