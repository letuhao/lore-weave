# PROG_001 Progression Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-26 — captures user core framing + 14-dimension gap analysis + 7 critical scope questions. Awaits user-provided reference materials before §6 reference survey + §5 Q1-Q7 lock.
>
> **Purpose:** Capture brainstorm + gap analysis + open questions for PROG_001 Progression Foundation. NOT a design doc; the seed material for the eventual `PROG_001_progression_foundation.md` design.
>
> **Promotion gate:** When (a) user has provided reference materials, (b) Q1-Q7 are locked via deep-dive discussion, (c) `_boundaries/_LOCK.md` is free → main session (or assigned agent) drafts `PROG_001_progression_foundation.md` with locked V1 scope, registers ownership in matrix + extension contracts, and creates `catalog/cat_00_PROG_progression.md`.

---

## §1 — User's core framing (2026-04-26)

User-stated, in original Vietnamese (preserved verbatim for fidelity):

1. **Game này là kiểu simulation nên không có khái niệm level hay chiến lực.** — This game is simulation-style, NO level / NO power-rating concept. Combat outcomes derive from RELEVANT specific attributes/skills, not aggregate "power level".

2. **Chỉ có hệ thống thuộc tính dynamic tuy reality và cơ chế training cho từng loại.** — Only DYNAMIC attribute system per-reality + per-type training mechanism. Engine doesn't fix attribute set; author declares schema per reality.

3. **Phải build được multiple progression systems động.** — Must build MULTIPLE dynamic progression systems. One reality may have linear-skill curves; another may have tier/stage breakthrough cultivation; another may have D&D-style discrete level-ups. Engine substrate accommodates all.

4. **Game turn-based với thời gian xử lý có độ trễ mỗi turn chênh lệch từ vài trăm ms cho tới vài phút.** — Turn-based with computation latency hundreds-of-ms to several-minutes per turn. Computational complexity is NOT a hard limit; engine can do complex calcs.

5. **Quá bao quát nên việc thiết kế không hề đơn giản.** — Generality makes design non-trivial. User explicitly acknowledges design difficulty.

### Implicit corollaries (from user framing)

- **C1.** No central "level" attribute on actors. No automatic 战力 calculation summing all stats.
- **C2.** Each attribute/skill is independent measurement. Combat formulas reference specific attributes/skills, not level matchup.
- **C3.** Reality declares schema; engine instantiates per actor. NPC_001/PCS_001 reference schema for per-actor values.
- **C4.** Multiple progression systems coexist within ONE reality (e.g., tu tiên reality has cultivation stages AND mundane skills like cooking).

---

## §2 — User's worked examples (2026-04-26)

User provided 3 concrete genre framings:

### Example E1 — Modern social-life game

| Layer | Entries | Notes |
|---|---|---|
| **Attributes** | 体质 (Physical) / 智力 (Intelligence) | Innate; slow-changing |
| **Skills** | 谈判 (Negotiation) / 经商 (Business) / 雄辩 (Oratory) / 钢琴 (Piano) | Action-driven; learned through practice |
| **Progression curve** | Likely linear or log diminishing | Mature character ≠ infinitely better |
| **Caps** | Soft caps (asymptotic) | Realistic limits |
| **Training** | Action-driven (do business → 经商 +) | PL_005 Use kind cascade |

### Example E2 — Tu tiên / xianxia cultivation game

| Layer | Entries | Notes |
|---|---|---|
| **Cultivation systems** | 炼气 (Qi-cultivation) / 炼体 (Body-cultivation) / 炼丹 (Alchemy) / 制符 (Talisman crafting) | Multiple parallel systems per actor |
| **Stage hierarchy** | 练气一层 → 九层 → 筑基 → 金丹 → 元婴 → ... | Tier breakthroughs (qualitative jumps); new caps per stage |
| **Progression curve** | Tier/stage with breakthrough events | NOT linear; breakthroughs require accumulated qi + insight + materials |
| **Caps** | Per-stage hard caps | Cannot exceed 练气九层 max-qi without breakthrough to 筑基 |
| **Training** | Time-driven (meditate) + Item-driven (consume 灵草) + Mentor-driven (cultivate with 师父) | Multiple trigger sources |
| **Author hooks** | Cultivation method registry (luyện khí method 1 vs 2 vs ...) | Different methods → different rates / max stages |

### Example E3 — Traditional D&D-style RPG

| Layer | Entries | Notes |
|---|---|---|
| **Attributes** | STR / INT / AGI / DEX / CON / CHA | Discrete numeric (3-18 D&D classic) |
| **Skills** | Fighting / Magic / Stealth / Lore / etc. | Class-bound or open |
| **Progression curve** | Discrete level-ups with point allocation | NOT smooth; gain levels at thresholds |
| **Caps** | Class/race-defined max | Wizards have higher INT cap than barbarians |
| **Training** | XP-driven via combat/quests | XP is intermediate currency |

### What examples cover well

- ✅ Multi-genre support requirement (engine cannot fix one schema)
- ✅ Author-declared per-reality schema
- ✅ Multiple progression systems per actor (one PC could have 4 cultivation lines simultaneously)
- ✅ Different curve types (linear / log / tier-stage / discrete)
- ✅ Multiple training trigger sources

### What examples DO NOT cover

- ❌ NPC progression (do NPCs train? or static?)
- ❌ Skill atrophy / decay (skills weaken without practice?)
- ❌ Cross-reality stat translation (xuyên không scenarios)
- ❌ Combat damage formula integration (DF7 territory)
- ❌ Storage model (where do values live? new aggregate or extend NPC/PC?)
- ❌ Derived stats (skill = f(attribute)?)
- ❌ LLM context integration (how LLM consumes progression for narrative)

---

## §3 — Gap analysis (14 dimensions)

Initial discussion 2026-04-26 surfaced 14 dimensions across 4 grouped concerns. These are the questions the engine substrate must answer.

### Group A — Ontology: attribute vs skill

**A1. Attribute vs Skill semantic boundary.**
- Attribute = innate, slow-changing, foundational (体质 / STR / 智力 / INT)
- Skill = learned, action-driven, specialized (谈判 / 钢琴 / 炼丹)
- Are they ONE unified system with type-flag, or TWO sub-systems with different mechanics?

**A2. Skill-derives-from-attribute relationship.**
- Smart actor (high INT) learns skills FASTER (training rate multiplier)?
- OR: smart actor's SKILL CHECKS get a bonus from INT (derived stat at action time)?
- OR: BOTH?
- OR: independent (no derivation)?

**A3. Reality-specific schema declaration.**
- Author declares attributes + skills per-reality at RealityManifest bootstrap
- Schema includes: kind_id, display_name (I18nBundle), curve_type, caps, training_rules
- Empty schema = sandbox / freeplay reality with no progression

### Group B — Progression curves

**B1. Linear curve.**
- 1 unit practice = 1 unit progress
- Modern social games use this
- Simple validator + author UX

**B2. Log/diminishing returns curve.**
- Practice gets harder at higher values (asymptotic toward cap)
- Realistic mature-character feel
- Common pattern in Mount & Blade Bannerlord, Kenshi

**B3. Tier/stage with breakthrough.**
- Qualitative jumps between tiers (练气九层 → 筑基)
- Breakthrough requires: cumulative qi + author-declared item / insight / event
- NEW cap per tier
- Critical for tu tiên / xianxia genre

**B4. Threshold/binary.**
- Some skills are discrete: know/don't-know (e.g., "speaks Mandarin" / "knows piano sonata X")
- Either-or; no intermediate progress

**B5. Discrete level-up with point allocation.**
- D&D pattern: gain XP → level-up event → distribute points
- Different from B1-B4 in interaction shape (player decision required)

### Group C — Training trigger mechanisms

**C1. Action-driven training.**
- PL_005 Use kind on tool/skill action → emits ProgressionDelta event
- "Use sword in combat" → 剑术 +1
- "Practice piano" → 钢琴 +1
- Common in M&B Bannerlord, Kenshi

**C2. Time-driven training (cultivation tick).**
- Generator-driven (EVT-G2 FictionTimeMarker) per fiction-day
- "Sit and meditate" or "stay in cultivation cell" → qi accrues over time
- Critical for tu tiên (cultivate without active player input)

**C3. Mentor-driven training.**
- NPC sư phụ accelerates training rate
- Modeled as multiplier on base rate when actor is in mentor's cell + has mentor relationship
- Wuxia trope

**C4. Item/elixir-driven training.**
- Consume Consumable kind (RES_001) → instant progression jump
- Tu tiên: 灵草 / 丹药 / 仙桃
- D&D: tomes / scrolls / training manuals

**C5. Quest-driven training (V2 with QST_001).**
- Quest reward = progression boost
- Defer V2 (QST not yet exists)

### Group D — Storage + integration + edge cases

**D1. Storage model.**
- Option (a): new aggregate `actor_progression` (T2/Reality, scope = Actor only)
- Option (b): extend PCS_001 PC core / NPC_001 NPC core with progression fields
- Option (c): reuse RES_001 resource_inventory with new ResourceKind variant
- Tradeoffs: separation of concerns vs aggregate count vs query patterns

**D2. NPC progression — train or static?**
- Train (M&B Bannerlord pattern): NPCs improve organically through actions; emergent NPC growth
- Static (CK3 pattern): author-declared traits; no automatic growth; mentor effect via narrative
- Hybrid: NPC has progression schema but trains slower / only via narrative beats
- Decision affects: storage size, replay determinism, LLM consumption complexity

**D3. Per-stage caps.**
- Tu tiên: 练气一层 max qi pool < 二层 < ... < 九层 < 筑基初期
- Modern: soft cap with diminishing returns (B2 curve)
- Engine schema: `cap_rule: CapRule` enum with TierBased / SoftCap / HardCap variants

**D4. xuyên không cross-reality stat translation.**
- PC's modern intelligence carries to tu tiên reality? Reset? Translate via mapping rule?
- PCS_001 §S8 covers body-substitution for vital_pool + cell ownership + actor-identity
- Progression: similar pattern? Some carry (soul-bound knowledge), some reset (body-bound skills)?
- Author-declared mapping rule per reality?

**D5. Combat damage formula integration.**
- DF7 PC Stats placeholder owned the original responsibility
- PROG_001 declares attributes/skills schema; DF7 (V1+) declares combat formulas consuming PROG values
- V1: ship combat numerics or defer to V1+ narrative-only?

**D6. LLM context integration.**
- AssemblePrompt persona section reads progression values
- "Smart NPC speaks differently" requires LLM aware of high INT
- "Strong PC succeeds at lifting" requires action validator aware of STR
- I18nBundle for attribute/skill display names (per RES_001 §2 cross-cutting)

---

## §4 — Boundary intersection summary

When PROG_001 DRAFT lands, these boundaries need careful handling:

| Touched feature | Status | PROG_001 owns | Other feature owns | Integration mechanism |
|---|---|---|---|---|
| EF_001 Entity Foundation | CANDIDATE-LOCK | Progression-side per-actor values | EntityRef + entity_binding + cascade | PROG aggregate scope = `Actor only` (PC + NPC); references EntityRef |
| RES_001 Resource Foundation | DRAFT | Numeric attribute/skill values + training rules + curves | Vital pool (HP/Stamina) + Consumable kinds + RealityManifest pattern | Vital ≠ Progression boundary clear; Consumable elixirs trigger progression delta; same i18n pattern |
| PCS_001 PC Substrate | brief | (none — PROG owns PC progression schema) | PC identity (PcId) + xuyên không mechanic + body/soul model | PCS references PROG schema for per-PC values; PROG_001 supersedes DF7 PC Stats placeholder |
| NPC_001 Cast | CANDIDATE-LOCK | Per-NPC progression values | NPC core aggregate + canonical_actor_decl + persona | Schema-driven extension; NPC_001 references PROG values in persona assembly |
| NPC_003 NPC Desires | DRAFT | (none) | Desires field on NPC core | Independent — desires are narrative, not numeric progression |
| PL_005 Interaction | CANDIDATE-LOCK | ProgressionDelta event shape + training rule lookup | InteractionKind + OutputDecl mechanism | PL_005 cascade emits ProgressionDelta when training triggered (Use kind, Strike kind, etc.) |
| PL_006 Status Effects | CANDIDATE-LOCK | (none) | Status flags (Drunk/Wounded/etc.) | Status modifiers TEMPORARY (PL_006); progression PERMANENT (PROG); orthogonal but composable (Drunk reduces 经商 V1+) |
| WA_006 Mortality | CANDIDATE-LOCK | (none) | Death state machine + cause kinds | Death may reset progression (per author-declared mortality mode) — V1+ rule |
| WA_001 Lex | CANDIDATE-LOCK | (none) | Reality physics axioms | Lex declares which progression systems are valid per reality (e.g., "no qi-cultivation in modern reality" rejected by Lex) |
| WA_003 Forge | CANDIDATE-LOCK | (none — PROG declares its own AdminAction sub-shapes) | Forge audit log + AdminAction enum | PROG adds Forge AdminAction sub-shapes (`Forge:GrantProgression` for author boost; `Forge:EditProgressionSchema` for runtime authoring) |
| 07_event_model | LOCKED | EVT-T3 Derived (`aggregate_type=actor_progression`) + EVT-T5 Generated (`Scheduled:CultivationTick` + others) | Event taxonomy + Generator framework | PROG registers sub-types per EVT-A11 |
| DF7 PC Stats placeholder | V1-blocking deferred | **SUPERSEDED — PROG_001 covers all actors not just PC** | (existing placeholder retired) | DF7 placeholder should be retired in favor of PROG_001 (V1) + DF7-V1+ becomes "combat damage formulas" sub-feature |
| RealityManifest envelope | unowned (boundary contract) | `progression_schema: ProgressionSchemaDecl` field declaring attributes/skills/curves/training_rules | Envelope contract per `_boundaries/02_extension_contracts.md` §2 | New OPTIONAL V1 field; engine default = empty schema (no progression in reality) |
| `progression.*` rule_id namespace | not yet registered | All progression RejectReason variants | RejectReason envelope (Continuum) | Per `_boundaries/02_extension_contracts.md` §1.4 — register at PROG_001 DRAFT |

---

## §5 — Q1-Q7 critical scope questions

These 7 questions lock V1 scope. Once user has provided reference materials and answered (or approved recommendations), PROG_001 DRAFT can proceed.

### Q1 — Attribute/Skill ontology: unified or split?

- **(A) Unified system** with type-flag: `ProgressionKind { Attribute, Skill }`. Single aggregate. Validators branch on type-flag. Cleaner schema.
- **(B) Split into 2 sub-systems** with separate aggregates `actor_attributes` + `actor_skills`. Type-system enforced semantics. Cost: 2 aggregates.
- **(C) Hybrid**: Single aggregate but with explicit `derives_from: Option<AttributeRef>` field on Skill entries (Skills know their attribute parent).

**Open** — recommendation pending user reference materials.

### Q2 — Curve types V1: which subset?

User examples implicitly span B1-B5 across genres. V1 minimum:
- (A) **B1 + B2 only** (linear + log) — covers modern + traditional RPG; defers tu tiên to V1+
- (B) **B1 + B2 + B3** (+ tier/stage breakthrough) — covers all three user examples; engine ships Stage Decl with breakthrough conditions
- (C) **All B1-B5** — full coverage; biggest V1 design surface

**Open.** Note: user explicitly mentioned tu tiên — Option B at minimum.

### Q3 — Training trigger sources V1: which subset?

User examples imply C1-C4 across genres. V1 minimum:
- (A) **C1 only** (action-driven via PL_005) — minimal; tu tiên cultivation NOT supported V1
- (B) **C1 + C2** (action + time-driven cultivation) — covers tu tiên auto-cultivation; needs Generator
- (C) **C1 + C2 + C4** (+ item/elixir-driven) — covers RES_001 elixir consumption; ties to RES_001
- (D) **All C1-C4** (+ mentor) — covers wuxia mentor trope; needs NPC relationship integration

**Open.** Note: tu tiên primary use case suggests B+ minimum.

### Q4 — NPC progression: train or static V1?

- (A) **Static V1** — NPCs author-declared at bootstrap; no automatic training V1; CK3 pattern
- (B) **Train V1** — NPCs improve organically; M&B Bannerlord pattern; emergent NPC growth
- (C) **Hybrid V1** — NPCs have progression schema but train slower than PCs (e.g., 0.1× rate) or only via narrative beats

**Open.** Tradeoff: emergent feel vs storage size + replay determinism complexity.

### Q5 — Skill atrophy/decay V1?

- (A) **No atrophy V1** — skills only grow; never decay; simpler V1
- (B) **Soft atrophy V1** — skill decays slowly without practice (per fiction-month?); needs Generator
- (C) **No atrophy ever** — skills are permanent; even V2+ doesn't decay

**Open.** Likely defer atrophy to V1+30d / V2.

### Q6 — Storage model: new aggregate or extend?

- (A) **New aggregate `actor_progression`** (T2/Reality, scope = Actor only) — clean separation of concerns
- (B) **Extend PCS_001/NPC_001 cores** with progression fields per actor — embedded; no new aggregate
- (C) **Reuse RES_001 resource_inventory** with new ResourceKind variant `Progression(ProgressionKindRef)` — leverage existing path

**Open.** Recommendation likely (A) for clean separation; matches RES_001 split discipline (Q3 split into vital_pool + resource_inventory).

### Q7 — Combat damage formula integration V1 or V1+?

- (A) **V1** — ship full combat damage formulas using PROG values; DF7 placeholder retired
- (B) **V1 narrative + V1+ mechanical** — V1 combat is narrative-only (LLM describes outcomes); V1+ adds damage formulas
- (C) **V1+ entirely** — V1 progression substrate ships without combat integration; combat formulas come V1+ via DF7-equivalent

**Open.** Tradeoff: V1 playable combat vs V1 design surface size.

---

## §6 — Reference materials placeholder

User stated 2026-04-26: "tôi sẽ cung cấp tiếp nguồn tham khảo để chúng ta đối chiếu" — will provide reference sources for cross-reference.

This section reserved for:
- User-provided reference docs / design notes / external game references
- Main session compares user's references against internal knowledge
- Updates Q1-Q7 recommendations based on combined references

**Status:** awaiting user input. When references arrive:
1. Capture verbatim (preserve user's preferred terminology)
2. Cross-reference with main session's known patterns (M&B / DF / Kenshi / CK3 / RimWorld / Vic3 / xianxia / D&D)
3. Create `01_REFERENCE_GAMES_SURVEY.md` companion doc (mirror RES_001 pattern)
4. Update Q1-Q7 in §5 with revised recommendations + lock LOCKED decisions in §10 (added at promotion time)

---

## §7 — Provisional V1 scope (placeholder — finalized after Q1-Q7 lock)

This section is INTENTIONALLY EMPTY pending Q1-Q7 + reference materials. Premature V1 scope locking before deep-dive risks RES_001-pattern issues (original recommendations changed significantly during Q1-Q5 batch deep-dive).

When user provides references + answers Q1-Q7, populate with:
- Schema declarations (AttributeKindDecl + SkillKindDecl shapes)
- Aggregate(s) decision (per Q6)
- Curve types ship list (per Q2)
- Training trigger sources (per Q3)
- NPC progression mode (per Q4)
- Atrophy decision (per Q5)
- Combat formula scope (per Q7)
- RealityManifest extensions
- Generator bindings (if C2/C3 train sources ship)
- Validator chain
- Acceptance criteria sketch

---

## §8 — What this concept-notes file is NOT

- ❌ NOT the formal PROG_001 design (no Rust struct definitions, no full §1-§N section structure, no acceptance criteria)
- ❌ NOT a lock-claim trigger (no `_boundaries/_LOCK.md` claim made for this notes file — IDF agent currently holds lock anyway)
- ❌ NOT registered in ownership matrix yet (deferred to PROG_001 DRAFT promotion)
- ❌ NOT consumed by other features yet (DF7 placeholder retains its existing status until PROG_001 DRAFT supersedes)
- ❌ NOT prematurely V1-scope-locked (Q1-Q7 OPEN; recommendations pending reference materials)

---

## §9 — Promotion checklist (when Q1-Q7 answered + references reviewed)

Before drafting `PROG_001_progression_foundation.md`:

1. [ ] User provides reference materials (design notes / external game references / preferred terminology)
2. [ ] Main session creates `01_REFERENCE_GAMES_SURVEY.md` companion (cross-references user materials with internal knowledge — Mount & Blade / DF / Kenshi / CK3 / RimWorld / Vic3 / D&D / xianxia)
3. [ ] User answers Q1-Q7 (or approves recommendations after deep-dive)
4. [ ] Update §7 V1 scope based on locked decisions
5. [ ] Wait for `_boundaries/_LOCK.md` to be free (currently held by IDF agent)
6. [ ] Claim `_boundaries/_LOCK.md` (4-hour TTL)
7. [ ] Create `PROG_001_progression_foundation.md` with full §1-§N spec
8. [ ] Update `_boundaries/01_feature_ownership_matrix.md` — add `actor_progression` aggregate ownership row (per Q6 decision); update DF7 placeholder status to "SUPERSEDED by PROG_001"
9. [ ] Update `_boundaries/02_extension_contracts.md` §1.4 — add `progression.*` RejectReason prefix
10. [ ] Update `_boundaries/02_extension_contracts.md` §2 — add RealityManifest `progression_schema` extension
11. [ ] Update `_boundaries/99_changelog.md` — append entry
12. [ ] Create `catalog/cat_00_PROG_progression.md` — feature catalog
13. [ ] Update `00_progression/_index.md` — replace concept row with PROG_001 DRAFT row
14. [ ] Coordinate with PCS_001 brief (parallel agent) to update §S5 stats stub → PROG_001 reference
15. [ ] Coordinate with NPC_001 closure pass to fold in NPC progression (per Q4 decision)
16. [ ] Update `features/_index.md` to add `00_progression/` to layout + table
17. [ ] Release `_boundaries/_LOCK.md`
18. [ ] Commit with `[boundaries-lock-claim+release]` prefix

---

## §10 — Status

- **Created:** 2026-04-26 by main session
- **Phase:** CONCEPT — awaiting user reference materials + Q1-Q7 deep-dive
- **Lock state:** `_boundaries/_LOCK.md` held by IDF agent (parallel session, IDF folder Phase 1 — 5 features DRAFT). PROG_001 DRAFT promotion blocked until lock free.
- **Estimated time to DRAFT (post-references-Q-deep-dive):** 4-6 hours focused design work (likely larger than RES_001 due to multi-genre coverage — modern + tu tiên + traditional RPG + sandbox simultaneously)
- **Co-design dependencies (when DRAFT):**
  - PCS_001 brief §S5 stats stub → PROG_001 reference (downstream)
  - NPC_001 closure pass folds NPC progression (per Q4)
  - DF7 PC Stats placeholder retired in favor of PROG_001 (V1) + DF7-equivalent V1+ "combat damage formulas" sub-feature
  - RealityManifest extension (lock-coordinated commit)
  - 07_event_model registers PROG sub-types
- **Next action:** User reviews this concept-notes file → provides reference materials → Q-deep-dive begins
