# REP_001 Reputation Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-26 — captures user framing (post-FAC_001 priority + 3-layer separation discipline) + 10-dimension gap analysis + Q1-Q10 critical scope questions. Awaits user reference materials review + Q-deep-dive before DRAFT promotion.
>
> **Purpose:** Capture brainstorm + gap analysis + open questions for REP_001 Reputation Foundation. NOT a design doc; the seed material for the eventual `REP_001_reputation_foundation.md` design.
>
> **Promotion gate:** When (a) Q1-Q10 locked via deep-dive discussion, (b) `_boundaries/_LOCK.md` free → main session drafts `REP_001_reputation_foundation.md` with locked V1 scope, registers ownership, creates catalog file.

---

## §1 — User framing + priority signal (2026-04-26)

User direction 2026-04-26 picked REP_001 as next deep-dive (post-FAC_001 closure 9d8f94c).

### Inherited V1+ deferral signal

1. **FAC_001 FAC-D7 LOCKED** (commit 9d8f94c):
   > Per-(actor, faction) reputation projection → V1+ REP_001 Reputation Foundation separate aggregate

2. **FAC_001 §1 boundary discipline statement:**
   > V1+ REP_001 = per-(actor, faction) reputation projection (separated)

3. **15_organization V2 RESERVATION:**
   > V1 has individual NPC reputation only — RES_001 SocialCurrency Reputation V1 covers per-NPC standing; faction-tier reputation is REP_001

4. **IDF folder closure roadmap** (50d65fa): "REP_001 = priority 6 post-IDF closure" (after FAC_001)

### Why now (post-FAC_001 closure)

User pick reasoning:
- FAC_001 just closed (9d8f94c) — the dependency is CANDIDATE-LOCK; faction_id is stable
- Wuxia narrative needs sect standing (sect "thanh dự" / Wulin reputation is core wuxia)
- Resolves FAC-D7 single-deferral (clean separation discipline)
- Smaller scope than FAC_001 (~1 aggregate vs FAC_001's 2)
- Unblocks NPC_002 Chorus V1+ Tier 4 priority modifier (rival-faction NPCs)
- Unblocks WA_001 V1+ AxiomDecl.requires_reputation hook
- Sandwich-design opportunity: REP_001 + future TIT_001 + future CULT_001 all consume FAC_001; closing REP_001 first sharpens the consumer pattern

### Wuxia narrative requirements (primary V1 use case)

Wuxia content (SPIKE_01 + future) NEEDS:

- **Sect standing** (Du sĩ Đông Hải Đạo Cốc rep ≥ Friendly tier — outer disciple standing)
- **Rival sect rep** (Lý Minh accidentally helps Đông Hải member → +rep with Đông Hải, -rep with Tây Sơn rival sect; cascade V1 vs V1+)
- **Wulin reputation per sect** (Lý Minh kills demonic-sect cultivator → +rep with mortal sects, -rep with demonic sect)
- **Sect-quest gating** (Đông Hải teaches advanced qigong only at Honored+ rep; V1+ via WA_001 requires_reputation hook)
- **Trade discount per faction** (V1+ V2 — merchant guild discount at Friendly+; V2+ ECON feature)
- **Reputation as social barter** (V2+ — burn rep to call in faction favor)

### Post-FAC_001 gap analysis (what FAC_001 locked NOT having)

FAC_001 V1 ships:
- ✓ faction aggregate + actor_faction_membership (membership state)
- ✓ Static default_relations (Hostile/Neutral/Allied tier per faction-pair)
- ✓ Per-actor max 1 faction (cap=1 V1 validator)
- ✗ NO per-actor reputation with each faction (FAC-D7 → REP_001)
- ✗ NO opinion baseline modifier from rival-sect membership (V1+ via REP_001 + NPC_002 V1+)
- ✗ NO sect-quest gating (V1+ via WA_001 + REP_001)

REP_001 fills the gap between membership (what faction you're in) and standing (what each faction thinks of you).

---

## §2 — Worked examples (across realities)

### Example E1 — Wuxia 5-sect preset (SPIKE_01 reality + V1+ expansion)

**Wuxia V1 sects (5 declared per FAC_001):**

| Sect | Display name | Rival sect (FAC_001 default_relations Hostile) |
|---|---|---|
| 1 | Đông Hải Đạo Cốc (Eastern Sea Daoist Valley) | Ma Tông |
| 2 | Tây Sơn Phật Tự (Western Mountain Buddhist Temple) | Ma Tông |
| 3 | Ma Tông (Demonic Sect) | Đông Hải Đạo Cốc + Tây Sơn Phật Tự |
| 4 | Trung Nguyên Võ Hiệp (Central Plains Martial Society) | (Neutral all) |
| 5 | Tán Tu Đồng Minh (Wandering Cultivator Alliance) | (Neutral all) |

**Canonical actors V1 + their reputation declarations (proposed sparse rows):**

| Actor | Faction | Rep score | Tier | Comment |
|---|---|---|---|---|
| Du sĩ | Đông Hải Đạo Cốc | +250 | Friendly | Outer disciple standing |
| Du sĩ | Ma Tông | -100 | Hostile | Demonic-sect rival baseline |
| Du sĩ | Tây Sơn Phật Tự | +25 | Neutral | Daoist+Buddhist friendly cooperation |
| Lý Minh | (all) | (no rows V1) | Neutral default | PC unaffiliated; no rep history |
| Tiểu Thúy | (all) | (no rows V1) | Neutral default | Commoner; no faction interaction |
| Lão Ngũ | (all) | (no rows V1) | Neutral default | Commoner; no faction interaction |

**SPARSE storage discipline:** Only ~3 declared rows V1. Most (actor, faction) pairs have NO row → "Neutral default" implied.

### Example E2 — Modern detective novel (Saigon)

PC (detective) — rep with "Saigon Police Department" = +500 Honored (good cop standing); rep with "Triad Criminal Org" = -800 Hated (years of busting them); rep with "Saigon Citizens Civic" = +300 Friendly (community-friendly cop)

### Example E3 — Sci-fi corporate house (V1+)

PC + NPCs — rep with each Great House (Atreides / Harkonnen / Corrino) per Dune pattern; sandbox-tier political balance

### Example E4 — D&D adventurer party

PC + NPCs — rep with each faction (Lords Alliance / Harpers / Zhentarim / Order of Gauntlet); 6-tier D&D 5e Faction Renown progression (Hated/Disliked/Neutral/Friendly/Honored/Revered)

### What examples cover well

- ✅ Multi-genre support (Wuxia sect / Modern faction / Sci-fi house / D&D 5e renown)
- ✅ Per-(actor, faction) sparse storage (most pairs empty)
- ✅ Bounded numeric range with tier mapping for display
- ✅ Mid-game rep changes (V1+) via runtime events
- ✅ Initial rep declared in canonical seed (sparse opt-in)
- ✅ Rival-faction baseline (-X for sworn-rival relationships per FAC_001 default_relations)

### What examples DO NOT cover

- ❌ Cross-faction rep cascade (helping faction A → -rep with rival B; V1 vs V1+)
- ❌ Decay over time (rep drift toward 0; V1+ V2)
- ❌ Multi-axis rep (CK3 Prestige + Piety; V2+ RES_001 already reserved as future kinds)
- ❌ Cross-reality rep migration (V2+ Heresy)
- ❌ Author-declared per-faction tier thresholds (V1+ enrichment)
- ❌ Rep as currency (burn rep for favor; V2+)

---

## §3 — Gap analysis (10 dimensions across 4 grouped concerns)

### Group A — Storage model

**A1. Aggregate vs projection.**
- "Projection" terminology used across FAC_001 docs (e.g., "per-(actor, faction) reputation projection")
- Projection = derived read model from events (see NPC_001 `npc_pc_relationship_projection` pattern)
- Aggregate = materialized owned state with direct mutation
- Decision impact: storage cost + event flow + V1+ runtime activation pattern

**A2. Sparse vs dense storage.**
- Wuxia V1: ~3 declared rep rows (most actors have no rep history)
- Dense: every (actor, faction) pair gets row default 0 → millions of rows for billion-NPC scaling
- Sparse: only declared / actively-touched pairs get rows → few rows V1; default Neutral implicit
- Decision impact: query patterns + write amplification + AI Tier scaling

### Group B — Numeric model

**B1. Score range and signedness.**
- D&D 5e: 0-30 unsigned, with -10 to -1 special "negative" tier
- WoW: -42000 to +42000 (15 tier × 6000 each)
- Fallout: NV: -100 to +100 (faction reputation; 7 tiers)
- Bounded vs unbounded: Bounded enables clear tier mapping; unbounded mirrors RES_001 SocialCurrency::Reputation Sum policy

**B2. Tier mapping (engine-fixed vs author-declared).**
- D&D 5e: 6 tiers Hated/Disliked/Neutral/Friendly/Honored/Revered
- WoW: 8 tiers Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted
- Fallout: NV: 7 tiers Vilified/Hated/Mixed/Neutral/Accepted/Liked/Idolized
- Engine-fixed tier set = simpler V1; author-declared per-faction = more authoring power V1+

**B3. Default initial value.**
- Always 0 (Neutral) on first contact: simple; matches D&D pattern
- Declared in canonical seed: sparse opt-in for narrative initial state
- Computed from FAC_001 membership: members start at +Friendly, rivals at -Hostile (via FAC_001 default_relations)
- Hybrid: declared overrides + computed-from-membership default + 0 for non-members fallback

### Group C — Event model + V1 runtime scope

**C1. V1 runtime events vs canonical seed only.**
- FAC_001 V1 ships canonical seed only; V1+ runtime events (per FAC-D11)
- REP_001 inherits same discipline? V1 ships canonical declarations only?
- Counter: V1 SPIKE_01 narrative may need rep delta from PL_005 Strike-on-faction-member; if so REP_001 V1 needs runtime event

**C2. Reputation source taxonomy.**
- Strike on faction member (PL_005) → -rep with that faction
- Help faction member (V1+ NPC_002 reaction) → +rep with that faction
- Quest reward (V2+ quest features) → +rep granted
- Forge admin override (WA_003 Forge) → SetReputation
- Decision: 0 V1 (canonical seed only) vs 1-2 V1 (Forge admin + canonical seed) vs all V1+ runtime active

**C3. Cascade reputation (rival-faction's enemy bonus).**
- Wuxia trope: kill Ma Tông member → +rep with Đông Hải (their rival) automatic
- Read FAC_001 default_relations for rival/ally lookup; cascade rep delta
- V1 simple (per-event single-target) vs V1+ cascade (per-event N-targets via FAC graph)

### Group D — Cross-feature integration

**D1. RES_001 SocialCurrency::Reputation reconciliation (CRITICAL).**
- RES_001 V1 already ships SocialCurrency::Reputation as per-actor SUM-style scalar
- REP_001 is per-(actor, faction) — DIFFERENT SHAPE
- 3-layer separation discipline:
  - **NPC_001 NpcOpinion** (per-NPC, PC) personal feeling
  - **RES_001 SocialCurrency::Reputation** (per-actor) global "danh tiếng" sum
  - **REP_001 actor_faction_reputation** (per-actor, faction) bounded standing
- Need explicit boundary statement: REP_001 is NOT an alias for SocialCurrency::Reputation

**D2. NPC_001 NpcOpinion reconciliation.**
- NPC_001 is per-(NPC, PC) per-Cell read at session-end
- REP_001 is per-(actor, faction) at canonical seed; V1+ runtime
- Both consumed by NPC_002 Chorus priority resolution (Tier 2 NPC opinion + Tier 4 V1+ faction rep)
- Need explicit boundary statement

**D3. NPC_002 Tier 4 priority modifier integration.**
- NPC_002 V1+ Tier 4 = rival-faction NPCs prioritize attention; reads REP_001 + FAC_001
- V1+ enrichment (NPC_002 V1+ Tier 4 enrichment scope)

**D4. WA_001 Lex AxiomDecl.requires_reputation hook.**
- V1+ AxiomDecl.requires_reputation: Option<(FactionId, MinTier)> field
- Pattern matches FAC-D8 (V1+ AxiomDecl.requires_faction); WA_001 closure pass V1+ extension adds 4 companion fields uniformly: requires_race + requires_ideology + requires_faction + requires_reputation
- V1 schema-present None V1; V1+ activation cheap

---

## §4 — Boundary intersection summary

When REP_001 DRAFT lands, these boundaries need careful handling:

| Touched feature | Status | REP_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|---|
| EF_001 Entity Foundation | CANDIDATE-LOCK | (none) | EntityRef + entity_binding | actor_faction_reputation references ActorId per EF_001 §5.1 |
| FAC_001 Faction Foundation | CANDIDATE-LOCK | Per-(actor, faction) reputation (FAC-D7 RESOLVED here) | faction + actor_faction_membership | REP_001 references FactionId; CANNOT exist without FAC_001 faction declared |
| RES_001 Resource Foundation | DRAFT | (none) | SocialCurrency::Reputation per-actor scalar | DISTINCT shape; REP_001 ≠ RES_001; explicit boundary statement at DRAFT |
| IDF features | CANDIDATE-LOCK | (none) | actor identity (race/lang/persona/origin/ideology) | (no direct integration V1; V1+ origin pack may declare default rep with sect) |
| NPC_001 Cast | CANDIDATE-LOCK | (none) | npc_pc_relationship_projection (per-NPC, PC) | DISTINCT shape; REP_001 ≠ NPC opinion; explicit boundary statement at DRAFT |
| NPC_002 Chorus | CANDIDATE-LOCK | (none) | priority algorithm | V1+ Tier 4 reads REP_001 for rival-faction NPCs |
| NPC_003 Desires | DRAFT | (none) | npc.desires field | (no direct integration V1) |
| PL_005 Interaction | CANDIDATE-LOCK | (none) | InteractionKind + OutputDecl | V1+ Strike on faction member → REP_001 delta event (cascade per FAC_001 graph) |
| WA_001 Lex | CANDIDATE-LOCK | (none) | LexConfig axioms | V1+ AxiomDecl.requires_reputation hook; REP_001 V1 schema-present None |
| WA_006 Mortality | CANDIDATE-LOCK | (none) | Death state machine | V1+ sect-leader death → cascade rep change for sect members; killer takes -rep |
| WA_003 Forge | CANDIDATE-LOCK | (none — REP_001 declares own AdminAction sub-shapes) | Forge audit log + AdminAction enum | REP_001 adds Forge AdminAction (`Forge:SetReputation` + `Forge:ResetReputation`) |
| 07_event_model | LOCKED | EVT-T3 Derived (`aggregate_type=actor_faction_reputation`) + EVT-T4 System (ReputationBorn) + EVT-T8 Administrative | Event taxonomy + Generator framework | Per EVT-A11 sub-type ownership |
| RealityManifest envelope | unowned | `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` | Envelope contract per `_boundaries/02_extension_contracts.md` §2 | OPTIONAL V1 (sparse opt-in; empty Vec valid) |
| `reputation.*` rule_id namespace | not yet registered | All reputation RejectReason variants | RejectReason envelope (Continuum) | Per `_boundaries/02_extension_contracts.md` §1.4 — register at REP_001 DRAFT |
| Future PCS_001 PC substrate | brief (BLOCKED on PROG_001) | (none) | PC identity | PCS_001 PC creation form may set initial rep (default 0 V1; V1+ origin pack pre-set) |
| Future TIT_001 Title Foundation | not started | (none) | Title aggregate + heir selection | V1+ TIT_001 grants require min REP_001 rep (Honored+) with faction |
| Future CULT_001 Cultivation Foundation | not started | (none) | Cultivation method registry | V1+ CULT_001 sect cultivation method requires min REP_001 rep |
| Future DIPL_001 Diplomacy Foundation | not started | (none) | Treaties + war + alliance dynamics | V2+ DIPL_001 inter-faction war affects REP_001 member-with-rival cascade |
| Future quest features (V2+ 13_quests) | V2 reservation | (none) | Quest declaration + reward | V2+ quest reward = REP_001 rep delta event |

---

## §5 — Q1-Q10 critical scope questions (PENDING — for user deep-dive)

These determine V1 scope. NOT yet locked. User confirmation needed before DRAFT promotion.

### Q1 — Aggregate vs projection (storage model)?

**Question:** Should REP_001 be a materialized aggregate (direct mutation) or a projection (derived read model from events)?

**Options:**
- (A) **Materialized aggregate** `actor_faction_reputation` (per-(actor, faction) row; mutated by events) — matches FAC_001 pattern
- (B) **Projection** `actor_faction_reputation_projection` (derived from EVT-T3 events; session-end derived) — matches NPC_001 NpcOpinion pattern
- (C) **Hybrid** — materialized aggregate + projection view (for AI Tier billion-NPC scaling)

**Recommendation:** (A) Materialized aggregate, **NOT projection**. Reasoning:
- FAC_001 V1 already chose materialized over projection (Q1 LOCKED) — same trade-off applies
- Projection works for NPC_001 (per-NPC, PC) because opinion is high-volume from session-end derivation; reputation is rare event (canonical seed V1; V1+ runtime sparse)
- Direct mutation keeps event flow simple V1; AI Tier projection optimization is V1+30d if needed
- Term "projection" in FAC_001 docs was loose — actual implementation will be materialized aggregate per pattern

### Q2 — Sparse vs dense storage?

**Question:** Should every (actor, faction) pair have a row, or only declared/actively-touched pairs?

**Options:**
- (A) **Sparse** — only declared canonical seed + V1+ events create rows; default Neutral implied for missing rows
- (B) **Dense** — every (actor, faction) pair gets row at canonical seed default 0
- (C) **On-demand sparse** — sparse storage; lazy-create row at first touch event (V1+ runtime)

**Recommendation:** (A) **Sparse**. Reasoning:
- Wuxia V1 has ~3 declared rep rows; dense would create N×F rows (1000s) for SPIKE_01 → wasteful
- AI Tier billion-NPC scaling: dense = O(NPC × Faction) storage = catastrophic
- Sparse + Neutral default = cheap; matches FAC_001 sparse storage discipline
- V1+ on-demand row creation when first delta event fires for unseen (actor, faction)

### Q3 — Numeric range and tier mapping?

**Question:** Bounded score range with engine-fixed tier mapping, or unbounded with author-declared tiers?

**Options:**
- (A) **Bounded engine-fixed** — score: i16 in [-1000, +1000]; engine maps to 8-tier (Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted) — WoW pattern
- (B) **Bounded engine-fixed simpler** — score: i16 in [-100, +100]; 6-tier D&D 5e (Hated/Disliked/Neutral/Friendly/Honored/Revered)
- (C) **Unbounded sum-style** — i64 raw score; matches RES_001 SocialCurrency::Reputation Sum policy; tier computed by display rules
- (D) **Author-declared per-faction tier thresholds** — FactionDecl.rep_tiers HashMap<i64, TierName>; max flexibility V1+

**Recommendation:** (A) Bounded i16 [-1000, +1000] + engine-fixed 8-tier (Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted). Reasoning:
- Bounded prevents inflation (CK3-style runaway prestige); narrative authenticity holds
- 8-tier WoW pattern most expressive for wuxia (Hated→Exalted maps to 江湖恩怨 spectrum)
- i16 range fits 8 tiers cleanly: -1000..-501 Hated / -500..-251 Hostile / -250..-101 Unfriendly / -100..+100 Neutral / +101..+250 Friendly / +251..+500 Honored / +501..+900 Revered / +901..+1000 Exalted
- Tier mapping engine-fixed (display layer) means LLM/UI computes label; storage minimal
- V1+ author-declared tiers via FactionDecl extension (REP-D-N enrichment)

### Q4 — Default initial value (no row case)?

**Question:** What's the implicit value when no actor_faction_reputation row exists?

**Options:**
- (A) **Always Neutral (0)** — no row = Neutral; simple
- (B) **Computed from FAC_001 membership + default_relations** — member of faction A starts +250 (Friendly); rival of faction B (per FAC_001 default_relations Hostile) starts -250 (Unfriendly); non-members start 0
- (C) **Hybrid** — declared in canonical seed overrides; otherwise computed-from-membership; otherwise 0
- (D) **Origin-pack-driven** — IDF_004 origin pack declares default rep with starting sect

**Recommendation:** (C) Hybrid (declared override → computed-from-membership → 0). Reasoning:
- (A) too simple — Wuxia member of Đông Hải should start Friendly with their own sect, not Neutral
- (B) reasonable but loses canonical-seed authoring flexibility (e.g., outer disciple +250 vs elder +500)
- (D) too coupled to IDF_004; origin packs are V1+ activation
- Hybrid: canonical seed wins (most explicit) → fall back to FAC_001-derived (member +250 / rival -250 / Neutral 0) → fall back to 0

### Q5 — V1 runtime events vs canonical seed only?

**Question:** Does REP_001 V1 ship runtime delta events, or only canonical seed declarations?

**Options:**
- (A) **Canonical seed only V1** (matches FAC_001 V1 discipline FAC-D11); V1+ runtime events
- (B) **Forge admin V1 only** — Forge:SetReputation V1 active; runtime gameplay events V1+
- (C) **PL_005 Strike → rep delta V1 active** — single runtime event V1; full taxonomy V1+
- (D) **Full runtime taxonomy V1** — all event sources active V1

**Recommendation:** (B) Forge admin V1 + canonical seed V1; runtime gameplay V1+. Reasoning:
- (A) too narrow — admin override is needed V1 for narrative authoring (admin "Lý Minh insults Đông Hải elder" → SetReputation)
- (D) too broad — runtime cascade design needs Q6 + Q7 lock first; expand V1+
- (B) middle ground: admin can set rep V1; runtime delta V1+ Single source of truth via Forge V1
- Matches FAC_001 V1 pattern (Forge:RegisterFaction V1 active)

### Q6 — Cascade reputation (rival-faction's enemy bonus)?

**Question:** Does -rep with faction A automatically grant +rep with faction A's rival per FAC_001 default_relations?

**Options:**
- (A) **No cascade V1** — single-target only; cascade is V1+ enrichment
- (B) **Cascade via FAC_001 default_relations V1** — rep delta with A triggers inverse delta with default_relations[A] = Hostile factions
- (C) **Cascade with attenuation V1** — primary delta full strength; cascade delta scaled (e.g., 25% of primary)

**Recommendation:** (A) No cascade V1; V1+ via REP-D-N enrichment. Reasoning:
- Cascade design is wide (cascade depth limit / attenuation factor / loop prevention) → V1+ scope
- V1 simple: rep changes only for explicitly-targeted (actor, faction) pair
- V1+ cascade enrichment: scope cascade attenuation factor, loop prevention via visited-set, cascade depth limit
- Authoring discipline: V1 author declares each rep change explicitly; V1+ engine derives cascades

### Q7 — Reputation decay over time?

**Question:** Does reputation decay toward Neutral (0) over fiction-time without explicit events?

**Options:**
- (A) **No decay V1** — rep static between explicit events; V1+ decay
- (B) **Linear decay V1** — rep moves toward 0 by N points per fiction-week; configurable per faction
- (C) **Tier-anchored decay V1** — Honored+ decays slower; Hated+ decays faster

**Recommendation:** (A) No decay V1; V1+ via REP-D-N enrichment. Reasoning:
- Decay design is wide (linear vs exponential / per-faction config / fiction-time scaling) → V1+ scope
- V1 narrative: rep persists explicitly until explicitly changed
- V1+ decay activation = additive enrichment (FactionDecl.rep_decay_per_week field)
- Bannerlord Renown decays; CK3 Prestige doesn't — design space is wide; defer

### Q8 — Cross-reality reputation migration (V1 vs V2+)?

**Question:** Can reputation transfer when actor migrates across realities?

**Options:**
- (A) **V1 strict single-reality**; V2+ Heresy migration
- (B) **V1 reset on migration** — actor enters new reality with no rep rows
- (C) **V1 migrate by default** — actor carries rep rows (subject to faction_id collision)

**Recommendation:** (A) V1 strict single-reality. Reasoning:
- Inherits IDF + FF + FAC discipline (RAC-Q1 + IDL-Q12 + FF-Q7 + FAC-Q8 all LOCKED V2+ Heresy)
- V1 reject `reputation.cross_reality_mismatch` (V2+ reservation)

### Q9 — Synthetic actor reputation?

**Question:** Can synthetic actors (ChorusOrchestrator / BubbleUpAggregator / mechanical entities) have reputation rows?

**Options:**
- (A) **Forbidden V1** — Synthetic actors don't have faction reputation
- (B) **Permitted V1** — admin/system reputation reserved for engine entities

**Recommendation:** (A) Forbidden V1 (consistent with IDF + FF + FAC discipline). Reasoning:
- IDF + FF + FAC all forbid synthetic actor V1 (RAC-Q1 + PRS-Q11 + ORG-Q7 + IDL-Q12 + FF synthetic exclusion + FAC-Q10)
- V1+ may relax if admin-faction reputation needed

### Q10 — Reconciliation with RES_001 SocialCurrency::Reputation?

**Question:** RES_001 already ships SocialCurrency::Reputation as per-actor SUM scalar. Does REP_001 supersede, coexist, or merge?

**Options:**
- (A) **Coexist (3-layer separation discipline)** — both ship V1; explicit boundary statement
  - RES_001 SocialCurrency::Reputation = per-actor *global* "danh tiếng" sum scalar (wuxia's broader reputation)
  - REP_001 actor_faction_reputation = per-(actor, faction) bounded standing per faction
  - NPC_001 npc_pc_relationship_projection = per-(NPC, PC) personal opinion
- (B) **REP_001 supersedes** — deprecate RES_001 SocialCurrency::Reputation; REP_001 owns all rep V1
- (C) **Merge into RES_001** — REP_001 just adds faction_id index to existing SocialCurrency::Reputation Sum

**Recommendation:** (A) Coexist with explicit 3-layer separation. Reasoning:
- RES_001 SocialCurrency::Reputation has different semantics (global "danh tiếng" sum that NPCs accumulate from heroic deeds)
- REP_001 has different semantics (per-faction standing tier; bounded; cascade-aware V1+)
- (B) breaks RES_001 V1 lock — too disruptive
- (C) breaks RES_001 SUM stack policy — bounded i16 ≠ i64 sum
- Three layers serve different gameplay loops:
  - "How does this NPC personally feel about you?" → NPC_001 NpcOpinion
  - "How famous are you in the wuxia world overall?" → RES_001 SocialCurrency::Reputation
  - "What's your standing with Đông Hải Đạo Cốc specifically?" → REP_001 actor_faction_reputation
- REP_001 DRAFT must include §-boundary-discipline section explicitly distinguishing these three

---

## §6 — Reference materials placeholder

User stated 2026-04-26: may provide reference sources (per RES_001 + IDF + FF_001 + FAC_001 pattern). REP_001 follows same template.

When references arrive:
1. Capture verbatim
2. Cross-reference with main session knowledge (already in `01_REFERENCE_GAMES_SURVEY.md` companion)
3. Update Q1-Q10 recommendations + lock LOCKED decisions

**Status:** awaiting user input.

---

## §7 — V1 scope (PROVISIONAL — pending Q-deep-dive)

This section will be LOCKED after Q1-Q10 confirmed. Provisional V1 scope below assuming recommendations approved as-is:

### V1 aggregates (1)

1. **`actor_faction_reputation`** (T2/Reality, sparse — per Q2)
   - actor_id + faction_id + score: i16 (in [-1000, +1000] per Q3) + last_updated_at_turn: u64 + last_event_id: Option<EventId>
   - **Mutable** via Apply events (canonical seed + Forge V1 active per Q5; runtime delta V1+)
   - Synthetic actors forbidden V1 per Q9
   - Cross-reality forbidden V1 per Q8

### Tier mapping (engine-fixed; display layer)

```rust
pub enum ReputationTier {
    Hated,        // -1000..=-501
    Hostile,      // -500..=-251
    Unfriendly,   // -250..=-101
    Neutral,      // -100..=+100
    Friendly,     // +101..=+250
    Honored,      // +251..=+500
    Revered,      // +501..=+900
    Exalted,      // +901..=+1000
}

impl ReputationTier {
    pub fn from_score(score: i16) -> Self { /* engine-fixed thresholds */ }
}
```

### V1 events (in channel stream per EVT-A10; NOT separate aggregate)

| Event | EVT-T* | Sub-type / delta_kind | Producer role | V1 active? |
|---|---|---|---|---|
| Reputation declared at canonical seed | **EVT-T4 System** | `ReputationBorn { actor_id, faction_id, initial_score }` | Bootstrap (RealityBootstrapper) | ✓ V1 |
| Reputation Forge admin set | **EVT-T8 Administrative** | `Forge:SetReputation { actor_id, faction_id, new_score, reason }` | Forge (WA_003) | ✓ V1 |
| Reputation Forge admin reset | **EVT-T8 Administrative** | `Forge:ResetReputation { actor_id, faction_id }` | Forge | ✓ V1 |
| Reputation gameplay delta | **EVT-T3 Derived** | `aggregate_type=actor_faction_reputation`, `delta_kind=Delta { score_change, source }` | Aggregate-Owner (REP_001 owner-service) | V1+ runtime per Q5 |
| Reputation cascade delta | **EVT-T3 Derived** | `delta_kind=CascadeDelta { score_change, source_event, source_faction }` | Aggregate-Owner | V1+ enrichment per Q6 |
| Reputation decay tick | **EVT-T3 Derived** | `delta_kind=DecayTick { score_change }` | Aggregate-Owner (V1+ scheduled tick) | V1+ enrichment per Q7 |

### V1 `reputation.*` reject rule_ids (6 V1 + V1+ reservations)

V1 rules:
1. `reputation.unknown_actor_id` — Stage 0 schema (actor_id not in EF_001)
2. `reputation.unknown_faction_id` — Stage 0 schema (faction_id not in FAC_001 canonical_factions + faction aggregate)
3. `reputation.score_out_of_range` — Stage 0 schema (score outside [-1000, +1000])
4. `reputation.synthetic_actor_forbidden` — Stage 0 schema (Synthetic actor cannot have reputation row per Q9)
5. `reputation.cross_reality_mismatch` — Stage 0 schema (actor reality ≠ faction reality per Q8)
6. `reputation.duplicate_row` — Stage 0 schema (multiple rows for same (actor, faction) pair)

V1+ reservations:
- `reputation.runtime_delta_unsupported_v1` — V1+ when first runtime delta source ships (per Q5)
- `reputation.cascade_unsupported_v1` — V1+ when cascade rep ships (per Q6)
- `reputation.decay_unsupported_v1` — V1+ when decay ships (per Q7)
- `reputation.tier_threshold_violation` — V1+ when author-declared per-faction tiers ship (per Q3 enrichment)

### V1 RealityManifest extensions (OPTIONAL V1)

- `canonical_actor_faction_reputations: Vec<ActorFactionReputationDecl>` — per-(actor, faction) declared reputation rows at canonical seed (sparse opt-in; empty Vec valid for V1 sandbox)

`ActorFactionReputationDecl` shape:
```rust
pub struct ActorFactionReputationDecl {
    pub actor_id: ActorId,
    pub faction_id: FactionId,
    pub score: i16,            // bounded [-1000, +1000]
    pub canon_ref: Option<GlossaryEntityId>,
}
```

### V1 acceptance criteria (8 V1-testable + 4 V1+ deferred)

V1:
- AC-REP-1: Wuxia canonical bootstrap declares ~3 actor_faction_reputation rows (Du sĩ Đông Hải +250 Friendly; Du sĩ Ma Tông -100 Hostile; Du sĩ Tây Sơn +25 Neutral)
- AC-REP-2: Tier mapping computed correctly (score=+250 → Friendly; score=-100 → Hostile; score=0 → Neutral)
- AC-REP-3: Sparse storage validated (PC Lý Minh has NO rep rows V1; default Neutral implied for unread (actor, faction) pairs)
- AC-REP-4: Score-out-of-range rejected (`reputation.score_out_of_range` for score=+1500 or -1500)
- AC-REP-5: Unknown faction_id rejected (`reputation.unknown_faction_id`)
- AC-REP-6: Unknown actor_id rejected (`reputation.unknown_actor_id`)
- AC-REP-7: Synthetic actor rejected (`reputation.synthetic_actor_forbidden`)
- AC-REP-8: Forge admin SetReputation (3-write atomic: actor_faction_reputation row + EVT-T8 + forge_audit_log)

V1+:
- AC-REP-V1+1: V1+ runtime delta event (PL_005 Strike on Đông Hải member → -100 rep with Đông Hải)
- AC-REP-V1+2: V1+ cascade rep (Strike Ma Tông member → -rep with Ma Tông + +rep with Đông Hải via FAC_001 default_relations)
- AC-REP-V1+3: V1+ decay tick (linear decay toward 0 per fiction-week)
- AC-REP-V1+4: V1+ author-declared per-faction tier thresholds (FactionDecl.rep_tiers extension)

### V1 deferrals (placeholder count — finalized at Q-lock)

(REP-D1..REP-D-N to be enumerated post Q-deep-dive)

Anticipated:
- REP-D1: V1+ runtime gameplay delta events (per Q5)
- REP-D2: V1+ cascade rep via FAC_001 default_relations (per Q6)
- REP-D3: V1+ decay over fiction-time (per Q7)
- REP-D4: V1+ author-declared per-faction tier thresholds (per Q3)
- REP-D5: V1+ multi-axis reputation (CK3 Prestige + Piety; deferred to V2+ via RES_001 SocialCurrency expansion)
- REP-D6: V2+ cross-reality migration (per Q8)
- REP-D7: V1+ NPC_002 Tier 4 priority modifier integration (rival-faction NPCs)
- REP-D8: V1+ WA_001 AxiomDecl.requires_reputation hook
- REP-D9: V1+ TIT_001 title-grant requires min rep
- REP-D10: V1+ CULT_001 sect cultivation method requires min rep
- REP-D11: V2+ DIPL_001 inter-faction war affects member rep cascade
- REP-D12: V2+ quest reward = REP_001 rep delta
- REP-D13: V1+ rep as currency (burn rep for favor; V2+ ECON feature)
- REP-D14: V1+ origin-pack default rep declaration (IDF_004 enrichment)
- REP-D15: V1+ rep history audit trail (separate aggregate vs event log query)

### V1 quantitative summary (provisional)

- 1 aggregate (actor_faction_reputation sparse)
- 1 enum (ReputationTier 8-variant — display layer; not stored)
- score: i16 in [-1000, +1000] per Q3 (bounded)
- Sparse storage per Q2; default Neutral implicit per Q4 hybrid
- 6 V1 reject rule_ids in `reputation.*` namespace + 4 V1+ reservations
- 1 RealityManifest extension (canonical_actor_faction_reputations OPTIONAL)
- 2 EVT-T8 Forge sub-shapes (Forge:SetReputation + Forge:ResetReputation)
- 1 EVT-T4 System sub-type (ReputationBorn)
- 3 EVT-T3 delta_kinds (Delta + CascadeDelta + DecayTick — V1+ runtime; V1 ships canonical seed + Forge only per Q5)
- 8 V1 AC + 4 V1+ deferred
- ~15 deferrals (REP-D1..REP-D15)
- ~500-700 line DRAFT spec estimate (smaller than FAC_001's ~870 — single aggregate)
- 4-commit cycle (lock-Q + DRAFT + Phase 3 + closure+release)

---

## §8 — What this concept-notes file is NOT

- ❌ NOT the formal REP_001 design (no Rust struct definitions, no full §1-§N section structure, no acceptance criteria)
- ❌ NOT a lock-claim trigger
- ❌ NOT registered in ownership matrix yet
- ❌ NOT consumed by other features yet (FAC-D7 retains V1+ deferred status until REP_001 DRAFT)
- ❌ NOT prematurely V1-scope-locked (Q1-Q10 OPEN; recommendations pending)

---

## §9 — Promotion checklist (when Q1-Q10 answered + references reviewed)

Before drafting `REP_001_reputation_foundation.md`:

1. [ ] User reviews market survey + provides additional references if any
2. [ ] User answers Q1-Q10 (or approves recommendations after deep-dive)
3. [ ] Update §7 V1 scope based on locked decisions
4. [ ] Wait for `_boundaries/_LOCK.md` to be free
5. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL)
6. [ ] Create `REP_001_reputation_foundation.md` with full §1-§N spec
7. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — add actor_faction_reputation aggregate (per Q1 decision)
8. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 — add `reputation.*` RejectReason prefix
9. [ ] Update `_boundaries/02_extension_contracts.md` §2 — add RealityManifest `canonical_actor_faction_reputations` extension
10. [ ] Update `_boundaries/99_changelog.md` — append entry
11. [ ] Create `catalog/cat_00_REP_reputation_foundation.md` — feature catalog
12. [ ] Update `00_reputation/_index.md` — replace concept row with REP_001 DRAFT row
13. [ ] Coordinate with FAC_001 closure pass extension to mark FAC-D7 RESOLVED via REP_001
14. [ ] Update `features/_index.md` to add `00_reputation/` to layout + table
15. [ ] Release `_boundaries/_LOCK.md`
16. [ ] Commit cycle (lock-Q + DRAFT + Phase 3 + closure+release; ~4 commits)

---

## §10 — Status

- **Created:** 2026-04-26 by main session (commit this turn)
- **Phase:** CONCEPT — awaiting Q1-Q10 deep-dive + market survey review
- **Lock state:** `_boundaries/_LOCK.md` FREE (released at FAC_001 closure 9d8f94c). REP_001 DRAFT NOT blocked when ready.
- **Estimated time to DRAFT (post-Q-deep-dive):** 2-3 hours focused design work; ~500-700 line spec
- **Co-design dependencies (when DRAFT):**
  - FAC_001 closure pass extension marks FAC-D7 RESOLVED via REP_001
  - Future PCS_001 PC creation form may set initial rep
  - Future TIT_001 + V1+ CULT_001 + V1+ DIPL_001 + V1+ NPC_002 Tier 4 + V1+ WA_001 requires_reputation consume REP_001
- **Next action:** User reviews market survey + answers Q1-Q10 (or approves recommendations) → DRAFT promotion when lock free
