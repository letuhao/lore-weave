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
- **Phase:** CONCEPT — Q1+Q6 LOCKED 2026-04-26 (see §11); Q2-Q5 + Q7 still open + chaos-backend reference doc landed
- **Lock state:** `_boundaries/_LOCK.md` held by IDF agent (parallel session, IDF folder Phase 1 — 5 features DRAFT). PROG_001 DRAFT promotion blocked until lock free.
- **Reference materials landed:**
  - [`02_CHAOS_BACKEND_REFERENCE.md`](02_CHAOS_BACKEND_REFERENCE.md) — chaos-backend repo analysis 2026-04-26 (10 sections / ~2400 words). Key finding: `actor-core` aggregation pipeline (Subsystem → Vec<Contribution> + bucket-processor → Snapshot + CapContribution AcrossLayerPolicy) is the load-bearing pattern; chaos-backend is mostly placeholder (5 of 17 crates have real Rust code).
- **Estimated time to DRAFT (post-Q2-Q7 lock):** 4-6 hours focused design work (likely larger than RES_001 due to multi-genre coverage — modern + tu tiên + traditional RPG + sandbox simultaneously)
- **Co-design dependencies (when DRAFT):**
  - PCS_001 brief §S5 stats stub → PROG_001 reference (downstream)
  - NPC_001 closure pass folds NPC progression (per Q4)
  - DF7 PC Stats placeholder retired in favor of PROG_001 (V1) + DF7-equivalent V1+ "combat damage formulas" sub-feature
  - RealityManifest extension (lock-coordinated commit)
  - 07_event_model registers PROG sub-types
- **Next action:** Q2 Curves deep-dive (next priority per dependency tree — Q2 needs Q1+Q6 locked which is now done)

---

## §11 — Q1+Q6 LOCKED decisions (2026-04-26 deep-dive paired)

> **Note:** §5 original Q1+Q6 recommendations are SUPERSEDED by this section. Q2-Q5 + Q7 in §5 remain open pending subsequent deep-dives.
>
> **Reference materials cited:** [`02_CHAOS_BACKEND_REFERENCE.md`](02_CHAOS_BACKEND_REFERENCE.md) §2 (actor-core aggregation pipeline) + §7 (Q1+Q6 mapping). Cross-reference with locked LoreWeave precedent: RES_001 Q3 split discipline (different invariants → split) + PL_006 unified discipline (same invariants → unified).

### Q1 LOCKED — Unified ProgressionKind with type discriminator + optional `derives_from`

| Sub | Decision |
|---|---|
| Q1a | Ontology architecture | **Unified (Option A)** — single aggregate with type discriminator. Reasoning: invariants giống nhau across Attribute/Skill/Stage (non-transferable + growth-driven + capped + actor-scoped + author-declared). Pattern matches PL_006 unified actor_status. RES_001 split discipline does NOT apply (vital_pool body-bound type-system enforced — different invariant). chaos-backend actor-core 12k LOC uses unified Subsystem→Contribution→Snapshot pattern. |
| Q1b | ProgressionType variants V1 | 3 variants: `Attribute` / `Skill` / `Stage`. V1+ reserved: `ResourceBound` (mana-pool-like progression with resource consumption per use). |
| Q1c | `derives_from` field V1 ship | YES — lightweight optional field; modern + D&D + xianxia genres benefit. Cost: ~5 lines schema. |
| Q1d | Derivation direction V1 | **Skill ← Attribute only** (no circular references). 智 (INT) → 谈判 (Negotiation) ✓; reverse forbidden V1. |
| Q1e | Derivation effect V1 | `training_rate_factor: f32` only (simpler) — INT high → negotiation grows faster. V1+30d may extend to query-value bonus (INT high → negotiation check bonus directly). |

### Q6 LOCKED — NEW T2/Reality aggregate `actor_progression` (owner=Actor only V1)

| Sub | Decision |
|---|---|
| Q6a | Storage architecture | **New aggregate (Option A)** `actor_progression` (T2/Reality scope). Reject (B) extend PCS/NPC cores (modifies locked aggregates; bloats; I14 stress at scale). Reject (C) reuse RES_001 (semantic mismatch — progression is non-transferable, RES axiom #1 is transferability). |
| Q6b | `actor_ref` type V1 | `Actor only` (PC + NPC). V1+30d reserved for `Item` (weapon's own progression — sword's "kill count" or sentient-weapon cultivation). |
| Q6c | Subsystem stacking V1 ship | **NO** — V1 stores `raw_value` only. V1+30d adds chaos-backend Subsystem→Contribution pattern for Race/Item/Mentor/Status modifiers. Schema reservation V1 cost: zero (added at V1+30d as additive evolution per I14). |
| Q6d | Snapshot caching V1 | **NO** — V1 query-time computation acceptable (turn-based latency budget hundreds-of-ms-to-minutes per turn; computation cheap). V1+30d may add Snapshot cache when subsystem stacking ships. |

### Q1+Q6 NEW: `BodyOrSoul` field for xuyên không cross-reality stat translation

Surfaced 2026-04-26 deep-dive — D4 gap from §3 gap analysis. Per RES_001 Q9c body-substitution semantics (vital follows body; resource_inventory.owner=Actor follows actor identity), progression needs analogous declaration:

```rust
pub enum BodyOrSoul {
    Body,      // martial / body-cultivation / motor skills (e.g., 炼体, 剑术, athletic)
    Soul,      // academic / social / cognitive (e.g., 智力 INT, 谈判, language fluency)
    Both,      // hybrid — rare, mostly authorial choice
}
```

Field added to `ProgressionKindDecl`:
```rust
pub struct ProgressionKindDecl {
    // ... fields above ...
    pub body_or_soul: BodyOrSoul,         // V1 default: Body (most progressions are physical)
}
```

xuyên không event behavior (PCS_001 mechanic):
- **Body progressions** stay with body (new soul inherits martial skills)
- **Soul progressions** travel with soul (academic knowledge follows soul to new body)
- **Both progressions** keep on both — author choice (rare)

V1 author default: `Body`. Soul-bound = explicit author declaration for cognitive/academic/social kinds.

### Concrete V1 Rust struct sketch

```rust
// ─── Q6 storage: NEW T2/Reality aggregate ───

#[derive(Aggregate)]
#[dp(type_name = "actor_progression", tier = "T2", scope = "reality")]
pub struct ActorProgression {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,                          // PC + NPC V1; Item V1+30d reserved (Q6b)
    pub values: Vec<ProgressionInstance>,
    pub last_modified_at_turn: u64,
    pub schema_version: u32,                          // V1 = 1
}

pub struct ProgressionInstance {
    pub kind_id: ProgressionKindId,                   // matches RealityManifest schema
    pub raw_value: u64,                               // base accrued; subsystem bonuses ADDED at query V1+30d (Q6c)
    pub current_tier: Option<TierIndex>,              // None for Attribute/Skill; Some(N) for Stage type
    pub last_trained_at_fiction_ts: i64,
    pub training_log_window: VecDeque<TrainingRecord>, // bounded ring buffer for replay determinism (per EVT-A9)
}

// ─── Q1 ontology: UNIFIED with type discriminator ───

pub enum ProgressionType {
    Attribute,    // V1 active — innate, slow-changing, soft cap
    Skill,        // V1 active — learned, action-driven, soft cap (V1+ tier-locked)
    Stage,        // V1 active — tier-based with breakthrough (tu tiên 练气九层 → 筑基)
    // V1+ reserved: ResourceBound (mana-pool style with consumption-per-use)
}

pub enum BodyOrSoul {
    Body,    // V1 default — martial / body-cultivation / motor skills
    Soul,    // academic / social / cognitive
    Both,    // hybrid — author choice
}

pub struct ProgressionKindDecl {                      // RealityManifest declaration
    pub kind_id: ProgressionKindId,
    pub display_name: I18nBundle,                     // i18n per RES_001 §2
    pub description: I18nBundle,
    pub progression_type: ProgressionType,
    pub body_or_soul: BodyOrSoul,                     // xuyên không inheritance hint (default Body)
    pub curve: CurveDecl,                             // Q2 — TBD
    pub cap_rule: CapRule,                            // Q2 — TBD
    pub training_rules: Vec<TrainingRuleDecl>,        // Q3 — TBD
    pub initial_value: u64,
    pub derives_from: Option<DerivationDecl>,         // Q1c hybrid — skill ← attribute scaling
}

pub struct DerivationDecl {
    pub source_kind_id: ProgressionKindId,            // typically Attribute kind
    pub training_rate_factor: f32,                    // training rate multiplier; e.g., 1.0 + INT*0.05
    // V1: derivation only affects training rate (Q1e)
    // V1+30d: may extend to query-value bonus
}

pub struct ProgressionKindId(pub String);             // e.g., "physical_strength" / "negotiation" / "qi_cultivation"

// ─── chaos-backend Subsystem pattern (V1+30d schema reservation only) ───

// V1 NOT shipping but pattern documented in 02_CHAOS_BACKEND_REFERENCE.md §2
// V1+30d will add:
// - Subsystem registry (Race / Class / Element / Item-equip / Status / Mentor)
// - Vec<Contribution> { source: SubsystemId, kind: ProgressionKindId, bucket: Bucket, value: f64 }
// - Bucket enum { Flat, Mult, PostAdd, Override }
// - bucket-processor: query-time merge; deterministic order
// - CapContribution + AcrossLayerPolicy for multi-source caps
```

### RealityManifest extension (V1)

```rust
RealityManifest {
    // ... existing fields per `_boundaries/02_extension_contracts.md` §2 ...

    /// PROG_001 Progression Foundation extensions (will register at PROG_001 DRAFT).
    /// Empty default = NO progression in reality (sandbox/freeplay realities valid V1).
    /// (Different from RES_001 which ships engine defaults — PROG schema inherently genre-specific;
    /// modern game ≠ tu tiên ≠ D&D — no universal default.)
    pub progression_kinds: Vec<ProgressionKindDecl>,

    /// Per-actor-class default initial values (overrides ProgressionKindDecl.initial_value per class).
    /// E.g., "warrior" actor-class STR=15 default; "scholar" INT=15 default.
    pub progression_class_defaults: HashMap<ActorClassRef, Vec<ClassDefaultDecl>>,

    /// Optional per-actor override (rare V1; common in V1+ for protagonist NPCs).
    pub progression_actor_overrides: HashMap<ActorRef, Vec<ActorOverrideDecl>>,
}

pub struct ClassDefaultDecl {
    pub kind_id: ProgressionKindId,
    pub initial_value: u64,
    pub initial_tier: Option<TierIndex>,
}

pub struct ActorOverrideDecl {
    pub kind_id: ProgressionKindId,
    pub override_value: u64,
    pub override_tier: Option<TierIndex>,
}
```

### Boundary clarifications (per Q1+Q6 sketch)

| Touched feature | PROG_001 owns | Other feature owns | Boundary |
|---|---|---|---|
| **EF_001** | (none) | EntityRef + entity_binding + cell_owner | PROG references EntityRef (Actor variant only V1) |
| **RES_001** | (none) | vital_pool (HP/Stamina) + resource_inventory + Consumable kinds | Vital ≠ Progression — vital is transient state, progression is permanent growth |
| **PCS_001 brief** | (none) | PC identity + xuyên không mechanic + body/soul model | PCS_001 §S8 body-substitution applies BodyOrSoul rule (PROG owns rule decl; PCS owns mechanic) |
| **NPC_001** | (none) | NPC identity + persona + flexible_state | NPC_001 references PROG values in persona assembly |
| **PL_005** | (none yet — Q3 deferred) | InteractionKind + OutputDecl mechanism | PL_005 cascade emits ProgressionDelta event when training triggered (Q3 specifies which interactions train what) |
| **PL_006** | (none) | actor_status (TEMPORARY modifiers — Drunk/Wounded) | Status modifiers TEMPORARY (PL_006); progression PERMANENT (PROG); orthogonal but composable (Drunk reduces 经商 effective skill V1+) |
| **WA_006** | (none) | Death state machine | Death may reset progression V1+ (per author-declared mortality mode); V1 progression unaffected by death |
| **WA_001 Lex** | (none) | Reality physics axioms | Lex declares which progression systems are valid per reality (e.g., "no qi-cultivation in modern reality" rejected by Lex schema validation) |
| **DF7 PC Stats placeholder** | **SUPERSEDED** | (existing placeholder retired) | DF7 placeholder retired; PROG_001 covers all actors not just PC. DF7-V1+ becomes "combat damage formulas" sub-feature (Q7) |
| **RealityManifest envelope** | `progression_kinds` + `progression_class_defaults` + `progression_actor_overrides` | Envelope contract | New OPTIONAL V1 fields per `_boundaries/02_extension_contracts.md` §2 additive evolution |

### §11.1 — Q2 LOCKED 2026-04-26 (Curves V1)

| Sub | Decision |
|---|---|
| Q2a | V1 curve types | **3 types**: `Linear` / `Log` / `Stage`. Discrete-levelup deferred V1+30d (PROG-D1). |
| Q2b | Threshold (B4) separate variant | NO — collapsed into `Stage` 1-tier degenerate case (saves engine surface; author wraps via macro V1+) |
| Q2c | Breakthrough trigger V1 | **Automatic check at training-tick + author-Forge override**. `Forge:TriggerBreakthrough` AdminAction (WA_003 closure folds in). |
| Q2d | Failed breakthrough V1 | **Silent** — raw_value clamped at tier_max; no narrative event V1. V1+30d (PROG-D2) adds 走火入魔 deviation narrative |
| Q2e | CapRule V1 types | **4 types**: `SoftCap` / `HardCap` / `TierBased` / `Unbounded` |
| Q2f | Within-tier curve for Stage | **Per-tier override allowed** — `TierDecl` carries `WithinTierCurve { Linear / Log }`. Tu tiên scenarios may want different rate per realm. |
| Q2g | Initial-value-on-advance | **Author-declared per TierDecl** `initial_value_on_advance: u64` (typically 0; rare carry-over) |
| Q2h | Per-class caps | **Via RealityManifest `progression_class_defaults`** (Q1+Q6 sketch) — NOT in CurveDecl |
| Q2i | Stage tier hierarchy | **Flat tier list** (chaos-backend ElementMasteryLevel pattern — concept reused, hardcoding rejected). Author NAMES tiers via I18nBundle. |
| Q2j | Validity matrix | **Enforced at RealityManifest bootstrap**: Linear allows SoftCap/HardCap/Unbounded; Log allows SoftCap/HardCap; Stage REQUIRES TierBased |

### Concrete V1 Rust shape (Q2)

```rust
pub enum CurveDecl {
    Linear {
        rate_per_train_unit: f32,                     // 1.0 standard; <1 slow; >1 fast
    },
    Log {
        base_rate: f32,                               // initial gain per unit
        difficulty_factor: f32,                       // higher = sharper diminishing approach to cap
    },
    Stage {
        tiers: Vec<TierDecl>,                         // author-declared ordered; flat list (no realm-stage nesting)
    },
}

pub struct TierDecl {
    pub tier_index: TierIndex,                        // 0-based
    pub name: I18nBundle,                             // "练气一层" / "Apprentice" — i18n per RES_001 §2
    pub tier_max: u64,                                // raw_value cap at this tier
    pub within_tier_curve: WithinTierCurve,           // Q2f per-tier override
    pub breakthrough_condition: BreakthroughCondition,
    pub initial_value_on_advance: u64,                // typically 0
}

pub enum WithinTierCurve {
    Linear { rate_per_train_unit: f32 },
    Log { base_rate: f32, difficulty_factor: f32 },
}

pub enum BreakthroughCondition {
    AtMax,                                            // raw_value == tier_max alone is enough (auto-advance)
    AtMaxPlus {
        item_consumption: Option<ResourceCost>,        // e.g., 灵丹 (RES_001 Consumable)
        location_required: Option<PlaceTypeRef>,       // e.g., CultivationChamber (PF_001 PlaceType)
        mentor_required: Option<MentorRequirement>,    // V1+30d (PROG-D3)
        fiction_time_window: Option<FictionTimeWindow>, // V1+30d (PROG-D4)
    },
    AuthorOnly,                                       // author must trigger via Forge (no auto-advance)
}

pub enum CapRule {
    SoftCap { cap: u64 },                             // training accrues with diminishing returns
    HardCap { cap: u64 },                             // training rejected past cap
    TierBased,                                        // cap = current_tier.tier_max; advances on breakthrough
    Unbounded,                                        // no cap (rare; V1+ Knowledge kind)
}
```

### CapRule × CurveDecl validity matrix

| CurveDecl | Valid CapRule(s) |
|---|---|
| `Linear` | `SoftCap` / `HardCap` / `Unbounded` (NOT `TierBased`) |
| `Log` | `SoftCap` / `HardCap` (Log inherently bounded; not `Unbounded`) |
| `Stage` | **`TierBased` only** (cap derives from tiers) |

### Tu tiên xianxia hierarchy worked example

```rust
// 24-tier flat list spanning 练气一层 → 化神
ProgressionKindDecl {
    kind_id: "qi_cultivation",
    progression_type: ProgressionType::Stage,
    body_or_soul: BodyOrSoul::Body,
    curve: CurveDecl::Stage {
        tiers: vec![
            // 练气 (9 tiers)
            TierDecl { tier_index: 0, name: I18nBundle::en("Qi Refining 1").with_zh("练气一层"),
                       tier_max: 100, within_tier_curve: WithinTierCurve::Linear { rate_per_train_unit: 1.0 },
                       breakthrough_condition: BreakthroughCondition::AtMax,
                       initial_value_on_advance: 0 },
            // ... 练气二层 .. 九层 ...
            // 筑基 (4 stages)
            TierDecl { tier_index: 9, name: I18nBundle::en("Foundation Building").with_zh("筑基"),
                       tier_max: 500,
                       within_tier_curve: WithinTierCurve::Log { base_rate: 1.5, difficulty_factor: 1.2 },
                       breakthrough_condition: BreakthroughCondition::AtMaxPlus {
                           item_consumption: Some(ResourceCost {
                               kind: ResourceKind::Consumable("foundation_pill".into()),
                               amount: 1,
                           }),
                           location_required: Some(PlaceTypeRef("cultivation_chamber".into())),
                           mentor_required: None,
                           fiction_time_window: None,
                       },
                       initial_value_on_advance: 0 },
            // ... 金丹, 元婴, 化神 ...
        ],
    },
    cap_rule: CapRule::TierBased,
    // ... derives_from / training_rules (Q3) etc. ...
}
```

### §11.2 — V1+ deferrals from Q2

| ID | Deferral | Trigger to revisit |
|---|---|---|
| **PROG-D1** | DiscreteLevelup curve (D&D-style player point allocation) | V1+30d if D&D-faithful realities requested |
| **PROG-D2** | Failed breakthrough narrative event (走火入魔 cultivation deviation) | V1+30d when narrative integration designed |
| **PROG-D3** | `mentor_required` BreakthroughCondition active | V1+30d (depends on Q3 mentor training source) |
| **PROG-D4** | `fiction_time_window` BreakthroughCondition active (full-moon-only breakthrough) | V1+30d when scheduler-Generator integration designed |
| **PROG-D5** | Skill atrophy/decay (Q5) | V1+30d (likely; user can override Q5) |
| **PROG-D6** | Subsystem stacking (chaos-backend Contribution pattern) | V2 — multi-source stat modifier merging |
| **PROG-D7** | Realm-stage nested hierarchy | V2 — only if flat tier list proves limiting (unlikely; chaos-backend used flat) |

### §11.3 — Q3 LOCKED 2026-04-26 (Training triggers V1)

| Sub | Decision |
|---|---|
| Q3a | V1 training sources | **Action + Time** (2 sources). Item collapses into Action with `target_match=ResourceKindMatch(Consumable)`. |
| Q3b | C3 Mentor V1 | NO — V1+30d (PROG-D8). Requires NPC relationship + Subsystem stacking (PROG-D6). |
| Q3c | C5 Quest V1 | NO — V2 (QST_001 dependency PROG-D14). |
| Q3d | TrainingAmount V1 variants | **`Fixed` only V1**. Variable + Random V1+30d (PROG-D9). |
| Q3e | TrainingCondition V1 variants | **3 V1**: `LocationMatch` + `StatusRequired` + `StatusForbidden`. ActorClassMatch + TimeWindow + RelationshipRequired V1+30d (PROG-D10/D11/D12). |
| Q3f | Time-cultivation tick period V1 | **Day-boundary** (matches RES_001 4 V1 Generators pattern). Hourly + custom V1+30d (PROG-D13). |
| Q3g | Item training architecture | Collapsed into Action `target_match` (saves engine surface — Use Consumable already auto-consumes via PL_005 §9.1) |
| Q3h | ProgressionDelta event shape | EVT-T3 Derived sub-shape with 4 variants: `RawValueIncrement` (V1) / `TierAdvance` (V1) / `TierRegress` (V1+30d) / `DirectSet` (V1 author-Forge) |
| Q3i | Action training validator location | PL_005 cascade **post-validation** — hot-path indexed by InteractionKind for O(1) lookup |
| Q3j | Failure handling | **Silent skip** for both Action + Time when conditions unmet (consistent; no rejection) |

### Concrete V1 Rust shape (Q3)

```rust
pub struct TrainingRuleDecl {
    pub rule_id: TrainingRuleId,                  // diagnostic / Forge reference
    pub source: TrainingSource,
    pub amount: TrainingAmount,
    pub conditions: Vec<TrainingCondition>,       // ALL must match (AND-semantic)
}

pub enum TrainingSource {
    Action {
        interaction_kind: InteractionKind,        // PL_005 enum
        target_match: Option<TargetMatch>,
        instrument_match: Option<InstrumentMatch>,
    },
    Time {
        period: TickPeriod,                       // V1: DailyBoundary only
    },
    // V1+30d reserved: Mentor (PROG-D8) / Quest (PROG-D14)
}

pub enum TickPeriod {
    DailyBoundary,                                // V1 active
    // HourlyBoundary, Custom { fiction_seconds } — V1+30d (PROG-D13)
}

pub enum TargetMatch {
    Any,
    EntityKind(EntityType),
    ResourceKindMatch(ResourceKind),              // for Item training (Use Consumable)
    PlaceTypeMatch(PlaceTypeRef),
    Specific(EntityId),
}

pub enum InstrumentMatch {
    Any,
    Specific(ResourceKind),                       // training Sword skill requires Sword item
    // InstrumentClass V1+30d (PROG-D15)
}

pub enum TrainingAmount {
    Fixed { amount: u32 },                        // V1 active
    // Variable / Random V1+30d (PROG-D9)
}

pub enum TrainingCondition {
    LocationMatch(PlaceTypeRef),                  // V1
    StatusRequired(StatusFlag),                   // V1
    StatusForbidden(StatusFlag),                  // V1 — Drunk reduces 经商
    // ActorClassMatch / TimeWindow / RelationshipRequired V1+30d
}

// ─── ProgressionDelta event (EVT-T3 Derived sub-shape PROG_001-owned) ───

pub struct ProgressionDelta {
    pub actor_ref: ActorRef,
    pub kind_id: ProgressionKindId,
    pub delta_kind: ProgressionDeltaKind,
    pub source_event_id: u64,                     // causal-ref per EVT-A6
}

pub enum ProgressionDeltaKind {
    RawValueIncrement { amount: u32 },            // V1 — Action or Time training accrual
    TierAdvance { from: TierIndex, to: TierIndex }, // V1 — breakthrough event (Q2)
    TierRegress { from: TierIndex, to: TierIndex }, // V1+30d — 走火入魔 deviation (PROG-D2)
    DirectSet { new_value: u64 },                 // V1 — author Forge override
}
```

### Generator binding (Q3 NEW)

NEW EVT-T5 Generated sub-type owned by PROG_001:
- **`Scheduled:CultivationTick`** (day-boundary trigger via EVT-G2 FictionTimeMarker)

Coordinator sequencing per EVT-G6 — PROG_001 CultivationTick is **5th and last** in day-boundary chain:

1. `Scheduled:CellProduction` (RES_001)
2. `Scheduled:NPCAutoCollect` (RES_001)
3. `Scheduled:CellMaintenance` (RES_001)
4. `Scheduled:HungerTick` (RES_001)
5. **`Scheduled:CultivationTick` (PROG_001)** — last, reads end-of-day actor state (post-status-applied)

Determinism per EVT-A9: RNG seed `blake3(reality_id || day_marker || "cultivation")` — deterministic for replay.

### NEW cascade-trigger sub-shape (Q3)

**`BreakthroughAdvance { actor_ref, kind_id, from_tier, to_tier }`** — EVT-T3 Derived cascade-trigger (mentioned earlier in Q2 §11 boundary). Emitted on tier advance for downstream consumers (NPC reaction / quest gate V2 / narrative beat V1+).

### Worked examples (in §11.3 — kept brief; full examples in earlier discussion)

**Tu tiên cultivation** — combines Time training (passive in cultivation_chamber) + Action training (Use spirit_pill burst) with LocationMatch condition.

**Modern social** — Action training (Speak to NPC) with StatusForbidden(Drunk) condition + Q1 derives_from(INT) for rate scaling.

### §11.4 — V1+ deferrals from Q3

| ID | Deferral | Trigger to revisit |
|---|---|---|
| **PROG-D8** | TrainingSource::Mentor — NPC mentor multiplier | V1+30d (depends Subsystem stacking PROG-D6) |
| **PROG-D9** | TrainingAmount Variable / Random | V1+30d when fairness/RNG needed |
| **PROG-D10** | TrainingCondition::ActorClassMatch | V1+30d when class-locked training needed |
| **PROG-D11** | TrainingCondition::FictionTimeWindow | V1+30d (full-moon-only cultivation; PROG-D4 same scope) |
| **PROG-D12** | TrainingCondition::RelationshipRequired | V1+30d (depends NPC relationship V1+ extension) |
| **PROG-D13** | TickPeriod::HourlyBoundary / Custom | V1+30d when finer cultivation period needed |
| **PROG-D14** | TrainingSource::Quest | V2 (QST_001 dependency) |
| **PROG-D15** | InstrumentMatch::InstrumentClass (broader category) | V1+30d when item categorization V1+ ships |

### §11.5 — Q3 rule_ids (V1 namespace registration)

`progression.*` V1 rule_ids — registered at PROG_001 DRAFT:

- `progression.training.kind_unknown` — invalid kind_id reference in TrainingRuleDecl (RealityManifest validator)
- `progression.training.rule_invalid` — malformed TrainingRuleDecl (e.g., empty TrainingRuleDecl.rule_id, or InteractionKind not in PL_005 closed set)
- `progression.breakthrough.condition_unmet` — Forge-triggered breakthrough failed condition check
- `progression.breakthrough.invalid_tier` — invalid tier_index for actor's current state
- `progression.cap.exceeded` — value would exceed HardCap (Linear/Log curves)

V1+ reservations:
- `progression.atrophy.no_practice` (Q5; likely V1+30d)
- `progression.deviation.cultivation_failed` (PROG-D2 走火入魔)
- `progression.training.prereq_unmet` (Q3j V1+30d if action-rejection enabled — currently silent V1)

### §11.6 — Q4 REVISED LOCKED 2026-04-26 (Hybrid observation-driven NPC model)

**User correction 2026-04-26:** Initial Q4 attempt (Train V1 eager) was REJECTED. Key insight: at scale (billions of NPCs vision), eager Generator iteration doesn't work. Quantum-observation principle applies — NPC state stale-until-observed (Schrödinger pattern; reference Stellaris pops / CK3 background characters / Skyrim distance culling).

#### 3-tier NPC architecture (future AI Tier feature scope)

| Tier | Storage V1 | Update model | V1 owner |
|---|---|---|---|
| **PC** | `ActorProgression` aggregate (full) | **Eager** — daily Generator iterates | PROG_001 V1 |
| **Tracked NPC (Major)** | `ActorProgression` aggregate (full) | **Lazy** — materialize on observation | PROG_001 V1 ships hooks; future AI Tier feature owns tier-tracking semantics |
| **Untracked NPC (Background)** | NO aggregate | LLM/RNG-generated per session; discarded | **future AI Tier feature** (out of PROG_001 scope V1; PROG_001 silently skips) |

PROG_001 V1 ships PC eager + Tracked NPC lazy hooks. Untracked NPC = absence of aggregate (clean default).

**Future AI Tier feature** (`16_ai_tier/` placeholder reserved; not creating V2_RESERVATION now — defer to user's explicit kickoff after PROG_001 DRAFT):
- `NpcTrackingTier` enum (Major / Minor / etc.)
- Tier promotion mechanics (Untracked → Tracked when significance threshold reached)
- Untracked NPC procedural generation (LLM persona + stat synthesis on-demand)
- Discard policies (session-end / cell-leave / etc.)

#### Q4 LOCKED sub-decisions (revised)

| Sub | Decision |
|---|---|
| Q4a Generator iteration | **PC only eager** (daily Generator iterates all PCs); **Tracked NPCs lazy** (no Generator participation) |
| Q4b Tracked NPC update trigger | **Observation events**: PC enters cell with NPC / PL_005 interaction targets NPC / LLM-driven NPC action initiates / Forge edit references NPC |
| Q4c Untracked NPC progression | **NO aggregate stored** — future AI Tier feature owns; PROG_001 silently skips actors without ActorProgression |
| Q4d Tracked NPC materialization | **Lazy compute on observation** — apply elapsed-day training accrual + breakthrough checks at observation moment |
| Q4e Cascade events from NPC progression | Emit at materialization moment (deferred from "real" fiction-time); causal-ref includes `materialized_at` annotation |
| Q4f Materialization optimization V1 | **Conservative** — assume NPC in last-known location/status for entire elapsed period (no intermediate-state tracking) |
| Q4g Tier promotion (Untracked → Tracked) | **NOT V1** — future AI Tier feature owns. V1 tracking_tier is author-declared at NPC creation (RealityManifest) or via Forge V1+ |

#### NEW V1 schema fields (Q4 revised)

```rust
pub struct ProgressionInstance {
    pub kind_id: ProgressionKindId,
    pub raw_value: u64,
    pub current_tier: Option<TierIndex>,
    pub last_trained_at_fiction_ts: i64,                  // existing
    pub last_observed_at_fiction_ts: i64,                 // ⭐ NEW Q4 revised — quantum-observation reference
    pub training_log_window: VecDeque<TrainingRecord>,
}

pub struct ActorProgression {
    pub reality_id: RealityId,
    pub actor_ref: ActorRef,
    pub values: Vec<ProgressionInstance>,
    pub last_modified_at_turn: u64,
    pub schema_version: u32,
    pub tracking_tier: Option<NpcTrackingTier>,           // ⭐ NEW Q4 revised — None V1; future AI Tier populates V1+
}

// Reserved for future AI Tier feature (NOT defined in PROG_001):
// pub enum NpcTrackingTier {
//     Major,   // full progression + LLM-driven decisions
//     Minor,   // progression but rule-based actions
//     // Untracked NPCs don't have ActorProgression at all
// }
```

PCs: tracking_tier=None always (PCs implicitly "always tracked"; eager Generator).
Tracked NPCs: tracking_tier=Some(...) declared by future AI Tier feature; lazy materialization.
Untracked NPCs: NO ActorProgression aggregate.

#### Generator behavior V1 (revised)

```pseudo
Scheduled:CultivationTick (day-boundary; sequenced 5th per EVT-G6):
  for each actor in reality where ActorProgression exists AND actor_type == PC:
    // PC eager — same as Q3 original design
    apply training rules + auto-breakthrough check
    emit ProgressionDelta events
  
  // Tracked NPCs SKIPPED at Generator (lazy)
  // Untracked NPCs absent from store (no aggregate)
```

#### Materialization computation (Q4 revised observation-driven)

```pseudo
on observation_event(npc, current_fiction_ts):
  if npc.actor_progression is None: return  // untracked; no progression
  
  for each ProgressionInstance in npc.actor_progression:
    elapsed_days = current_fiction_ts.day_count() - instance.last_observed_at.day_count()
    if elapsed_days <= 0: continue  // already up-to-date
    
    // Conservative V1: replay each day applying Time-source training rules
    for day in 0..elapsed_days:
      simulated_ts = instance.last_observed_at + (day + 1) * fiction_day
      
      for rule in npc_kind.training_rules where rule.source matches Time:
        if all rule.conditions match (using NPC's last-known location/status):
          apply rule.amount to instance.raw_value
          // Auto-breakthrough check (Q2 mechanic)
          if at-tier-max + breakthrough_condition met:
            advance tier; emit ProgressionDelta::TierAdvance with materialized_at=current_fiction_ts
    
    instance.last_observed_at_fiction_ts = current_fiction_ts
    emit aggregated ProgressionDelta::RawValueIncrement event with materialized_at causal-ref
```

V1 simplification: NPC stays in last-known state for entire elapsed period. V1+30d adds intermediate-state interpolation (PROG-D20).

#### NEW EVT-T3 sub-shape (Q4 revised)

**`ActorProgressionMaterialized { actor_ref, materialized_at_fiction_ts, deltas: Vec<ProgressionDelta> }`** — EVT-T3 Derived sub-shape capturing lazy-materialization batch as single audit-able event. Cascade-ref: triggering observation event.

Distinguished from per-day ProgressionDelta events (which are emitted PER day during materialization replay). ActorProgressionMaterialized is the "wrapper" event for batch correlation.

#### RES_001 alignment concern (downstream V1+30d)

**RES_001 NPC owner auto-collect Generator** (`Scheduled:NPCAutoCollect` daily for ALL NPCs) is architecturally inconsistent with quantum-observation principle for the same reason original Q4 was wrong.

**Decision:** RES_001 keeps eager V1 (already CANDIDATE-LOCK; not modifying). V1+30d closure pass migrates RES_001 NPC economy to lazy materialization (matches PROG_001 pattern). Tracked as **NEW deferral PROG-D19** and downstream RES_001 closure-pass concern.

### §11.7 — Q5 REVISED LOCKED 2026-04-26 (Lazy atrophy at materialization)

**User correction:** Initial Q5 LOCKED mechanism (Generator-based atrophy V1+30d) was wrong locality. In observation model, atrophy applies at materialization time (lazy), not Generator. V1 still NO atrophy ships, but mechanism shape revised.

| Sub | Decision |
|---|---|
| Q5a V1 atrophy | **NO V1** — confirmed defer V1+30d (PROG-D5) |
| Q5b V1+ atrophy mechanism | **Lazy at materialization** — NOT Generator. At materialization, compute time-since-last-trained; apply atrophy delta if `atrophy_rule` declared. PCs eager-apply at daily Generator (since PCs eager); Tracked NPCs lazy-apply at observation. |
| Q5c V1 schema reservation | **`last_trained_at_fiction_ts`** (existing) distinguished from **`last_observed_at_fiction_ts`** (Q4 revised). Atrophy uses last-trained (skill-specific decay); observation uses last-observed (NPC-scope refresh). Both fields V1 active. |
| Q5d TierRegress vs Atrophy distinction | **YES distinct mechanisms**: TierRegress (PROG-D2 V1+30d) = failed breakthrough deviation (走火入魔); Atrophy (PROG-D5 V1+30d) = gradual no-practice decay. Different triggers; both V1+30d. |
| Q5e Atrophy applies to PCs too? | **YES** — both PCs and Tracked NPCs subject. PCs: applied at daily Generator. Tracked NPCs: applied at observation materialization. Untracked NPCs: not applicable (no aggregate). |

#### Lazy atrophy computation V1+30d

```pseudo
on observation_event(npc, current_fiction_ts):
  // Q4 revised materialization first applies training accrual:
  apply_training_materialization(npc, current_fiction_ts)
  
  // V1+30d adds atrophy:
  for each ProgressionInstance in npc.actor_progression:
    if instance.kind has atrophy_rule:
      days_since_last_trained = current_fiction_ts.day_count() - instance.last_trained_at.day_count()
      if days_since_last_trained > atrophy_rule.threshold_days:
        decay_amount = (days_since_last_trained - threshold) * atrophy_rule.daily_decay
        apply RawValueDecrement(decay_amount) clamped to floor
```

For PCs (eager daily Generator): same logic but runs at Generator instead of observation.

### §11.8 — V1+ deferrals NEW from Q4+Q5 revised

| ID | Deferral | Trigger to revisit |
|---|---|---|
| **PROG-D19** | RES_001 NPC eager → lazy materialization alignment | V1+30d when AI Tier feature ships; RES_001 closure pass aligns with quantum-observation pattern |
| **PROG-D20** | Intermediate-state interpolation (NPC "had" cultivation visits during elapsed period) | V1+ for richer realism; V1 conservative single-state assumption acceptable |
| **PROG-D21** | NPC-to-NPC cascade during un-observed period | V2 — complex determinism concern; multi-NPC observation chains |
| **PROG-D22** | Untracked → Tracked tier promotion logic | **Future AI Tier feature** owns (out of PROG_001 scope) |
| **PROG-D23** | Materialization computation closed-form math (skip per-day replay for simple training rules) | V1+30d optimization; only matters when elapsed_days > 100 |

### §11.9 — Future AI Tier feature reservation

User noted: "kiến trúc phân tầng AI mà chúng ta chưa design, sẽ có design sau progression system".

**Future placeholder:** `features/16_ai_tier/` — V2_RESERVATION pattern (mirror QST/CFT/ORG). Not creating now; defer to user's explicit kickoff after PROG_001 DRAFT lands.

**AI Tier feature responsibilities (sketch only):**
- Define `NpcTrackingTier` enum (Major / Minor / Generated / etc.)
- Tier promotion mechanics (Untracked NPC becomes Tracked when significance threshold)
- Untracked NPC procedural generation (LLM-driven persona + stat synthesis at first observation)
- Discard policies (session-end / cell-leave / N-day no-observation)
- Integration with PROG_001's `tracking_tier` field
- Integration with NPC_001 ActorId (which subset is tracked)
- Integration with billion-NPC scaling vision

PROG_001 V1 ships READY for AI Tier integration:
- `tracking_tier: Option<NpcTrackingTier>` field reserved (None V1)
- `last_observed_at_fiction_ts` field active V1
- Materialization computation function (testable V1)
- "Untracked NPC = absence of aggregate" semantic clean

### §11.10 — Q7 still open

After Q1+Q6+Q2+Q3+Q4+Q5 LOCKED, only **Q7 remains**:

- **Q7 — Combat damage formula V1 vs V1+**: chaos-backend damage law direct lift candidate (per `02_CHAOS_BACKEND_REFERENCE.md` §4); defines DF7-equivalent reading ProgressionInstance.raw_value for combat outcomes.

Q4+Q5 revised LOCKED unblocks Q7 (combat formula now reads "current materialized" ProgressionInstance values; observation event triggers materialization before formula reads value).
