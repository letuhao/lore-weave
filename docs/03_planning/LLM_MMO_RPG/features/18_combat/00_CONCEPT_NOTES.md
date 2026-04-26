# COMB_001 Combat Foundation — Concept Notes

> **Status:** CONCEPT 2026-04-27 — Q-LOCKED matrix Q1-Q9 ALL LOCKED via 4-batch deep-dive 2026-04-27 (Batch 1: Q1+Q5+Q9 / Batch 2: Q2+Q3 / Batch 3: Q4+Q6+Q8 / Batch 4: Q7). User approved each batch with "1" approval. Captures user combat V1 framing + market combat survey + LLM-zero-math constraint LOCKED + 3-layer architecture + V1 4-step damage law chain (chaos-backend adoption) + module decomposition map (7-file V1 + 6-bridge pattern) + 9 LOCKED architectural decisions with concrete invariants + 10 closure-pass-extensions surfaced. Ready for COMB_001 DRAFT promotion.
>
> **Purpose:** Capture brainstorm + reference games review + LLM-engine separation discipline + Q-LOCKED architectural decisions for COMB_001 Combat Foundation. NOT a design doc; the seed material for the eventual `COMB_001_combat_foundation.md` design with all critical Qs already locked.
>
> **Promotion gate:** ✅ Met 2026-04-27 — (a) Q1-Q9 ALL LOCKED via 4-batch deep-dive; (b) `_boundaries/_LOCK.md` free (verified at concept-notes phase); (c) closure-pass-extensions identified for PROG_001 / PL_005 / PL_006 / NPC_002 / AIT_001 / WA_006 / WA_001 / PF_001 / ACT_001 / RealityManifest (10 cross-feature revisions). Main session can now schedule COMB_001 DRAFT promotion in single combined `[boundaries-lock-claim+release]` commit.

---

## §1 — User's core framing

### §1.1 Combat V1 + V2+ kickoff 2026-04-27

User-stated 2026-04-27 (post-TDIL_001 DRAFT closure):

> "tiếp theo còn 1 phần nữa cần hoàn thành trong v1 là combat đơn giản, và v2+ combat phức tạp
>
> tôi đang suy nghĩ về cách làm combat kiểu pokemon hay các game hero tương tự nơi các phe phái đứng về các phía các nhau và tiến hành combat
>
> hãy giúp tôi review về hệ thống combat trong các game trên thị trường
> nên làm combat kiểu này hay làm kiểu Fire Emblem hay kiểu gì khác?
> chúng ta đã có cell nên có thể làm combat kiểu tactic nhưng khá là khó"

Translation (preserved verbatim above):
- V1 needs **simple** combat; V2+ extends to complex
- Considering Pokemon-archetype (factions on opposite sides) vs Fire Emblem (grid tactics) vs other
- Cell architecture allows tactic-style but **"khá là khó"** (quite hard)
- Wants market survey before committing to direction

### §1.2 LLM-zero-math constraint LOCKED

User-stated 2026-04-27 (after seeing market survey):

> "đồng ý đề xuất, về phía LLM, tôi muốn nó can thiệp càng ít hoặc không cho can thiếp luôn, chỉ tham gia quyết định cho AI
> chúng ta nên có 1 combat engine đủ mạnh vì trong combat logic tính toán rất nghiêm ngắt mà AI thường rất ngu, nó sẽ bị ảo giác và calculation tầm bậy"

Translation:
- LLM intervention should be **as minimal as possible OR zero**
- LLM **only participates in AI decision-making**
- Need a strong combat engine — combat math is **strict**; LLM **hallucinates and miscalculates**

→ **CRITICAL CONSTRAINT (COMB-A1 candidate):** Engine owns 100% of combat math (damage / hit / initiative / status / win-loss). LLM ONLY:
  - **(a)** selects actions for AI-controlled NPCs (Major tier; Minor tier scripted; Untracked tier engine-bulk)
  - **(b)** narrates POST-resolution prose

LLM **NEVER**:
  - Proposes damage numbers
  - Overrides engine calculation
  - Determines hit/miss
  - Decides win/lose

### §1.3 Cascade: REVERSE PROG_001 §9 V1 Strike formula

**Currently LOCKED in PROG_001 §9 + cat_00_PROG:**
> "Hybrid combat: LLM proposes damage_amount in PL_005 Strike payload; engine validator computes bounds from offense/defense stat sums; clamps silently."

**To be reversed at COMB_001 DRAFT:**
- LLM never proposes `damage_amount`
- Engine computes from attacker/defender stat sums + deterministic seeded RNG
- PL_005 Strike payload drops `damage_amount` field (engine-sourced, not user-sourced)

This is a **closure-pass-extension** PROG_001 §9 + PL_005 Strike + cat_00_PROG when COMB_001 ships. PROG-D24 (V1+ DF7-equivalent damage law chain) → **promote simple form to V1**; full chain remains V1+.

---

## §2 — Architectural anchors (existing LOCKED features that combat must compose with)

Combat does NOT design from scratch; it **composes** existing primitives:

| Anchor | Provides | Combat consumption |
|---|---|---|
| **PL_001 Continuum** | Turn-based engine; per-channel fiction_clock | Combat = sequence of turns within a single channel/cell |
| **PL_005 Interaction** | Strike intent + 5 action verbs (V1: Strike/Defend/Skill/UseItem/Flee proposed) | Combat actions = subset of interaction intents; Strike payload simplified |
| **PL_006 Status Effects** | Engine-driven status apply/dispel/expire | Combat applies buff/debuff via existing status system; ZERO new state machine needed |
| **PROG_001 Progression** | ProgressionInstance per actor (stat values + tier) | Combat reads stats: strike_power / armor / speed / accuracy / dodge / crit_chance |
| **RES_001 vital_pool** | HP/Stamina/Mana (V1+) per actor; body-bound | Combat damage = HP delta; KO at HP=0; stamina cost for skills V1 |
| **FAC_001 RelationStance** | Hostile/Neutral/Allied per faction-pair | Side allegiance auto-assigned at encounter start; Neutral can be recruited V1+ |
| **AIT_001 3-tier NPC** | PC + Major (LLM-driven) + Minor (scripted) + Untracked (ephemeral) | Action selection dispatch: PC=user / Major=LLM / Minor=script / Untracked=bulk-engine |
| **NPC_002 Chorus** | AssemblePrompt LLM persona context | Combat-mode prompt template (extension); structured ActionDecl response |
| **ACT_001 actor_clocks** | actor_clock + soul_clock + body_clock | V1+ reaction speed reads body_clock (TDIL-D9 promotion) |
| **TDIL_001 time_flow_rate** | Per-channel + per-cell time dilation | Combat duration = N rounds × per_round_fiction_duration; rate-aware narration |
| **WA_006 Mortality** | Dying / Dead state transitions | KO at HP=0 → mortality state machine kicks in (permadeath / revival per reality config) |
| **EF_001 entity_lifecycle** | Lifecycle: Active → Suspended → Dead | Combat KO finalize → Dead via mortality cascade |
| **CSC_001 4-layer scene** | Cell scene with zone graph (Layer 1-4) | V1: borrow 2 zones for Front/Back row; V2+: promote zone graph to tactical grid |
| **WA_001 Lex** | Reality-level axioms (anti-grief, no-PvP zones) | Lex hooks at encounter validation (e.g., tier-cap on hostile delta; sect-on-sect scaling) |

→ Combat is a **thin domain layer** over existing primitives. The hard work was already done in foundation tier + AIT/ACT/TDIL substrate.

---

## §3 — Market combat survey

### §3.1 6 archetypes analyzed

| Archetype | Reference games | Mechanical depth | LLM-fit | Token cost | Cell-fit | V1 verdict |
|---|---|---|---|---|---|---|
| **A. Pokemon (side vs side, abstract)** | Pokémon, Honkai Star Rail (HSR), Persona 5 Royal | Trung — type/weakness + ≤4 moves | ⭐⭐⭐⭐⭐ — narration shines; LLM never asked to calculate | Thấp | Mượn cell làm "arena"; ignore zone — OK | ✅ V1 base |
| **B. Fire Emblem (grid tactics)** | FE Three Houses, FFT, Triangle Strategy, Tactics Ogre | Cao — movement + range + terrain | ⭐⭐ — LLM yếu pathfinding; engine làm hộ thì LLM thành dice-roller (đã LOCKED constraint) | Cao | Phá TDIL-A5 nếu battlefield > 1 cell | ❌ V1 too expensive; ✅ V2+ within-cell |
| **C. Action RPG (real-time)** | Diablo, Genshin Impact, Dark Souls, Devil May Cry | N/A — không turn-based | ❌ — đụng PL_001 turn semantic + atomic-per-turn | Cực cao | ❌ | ❌ rejected (architectural mismatch) |
| **D. JRPG line-up (front/back row)** | Dragon Quest, FF1-9, Octopath Traveler, Final Fantasy X | Trung-thấp — 2 row × side; back row safer + ranged | ⭐⭐⭐⭐ — đơn giản; positional narration tốt | Thấp | Mượn 2 zones (Front/Back) — fit perfectly với CSC_001 | ✅ V1 positioning layer |
| **E. Card / deck-builder** | Slay the Spire, Inscryption, Hearthstone, Marvel Snap | Cao — synergy + RNG + draw tempo | ⭐⭐⭐ — LLM kể "rút bài" awkward; mechanic-first paradigm | Trung | Bỏ qua cell completely | ❌ V1 paradigm mismatch (game tu tiên không phải card game) |
| **F. Skill-check narrative** | Disco Elysium, Baldur's Gate 3 dice rolls, Citizen Sleeper | Thấp — d20 + modifier | ⭐⭐⭐⭐⭐ — LLM ƯU thế tuyệt đối; mỗi roll = 1 narration moment | Trung | Cell = scene context | ⚠ V1+30d social skirmish (luận đạo); NOT physical combat |

### §3.2 Detailed reference game analysis

**Pokemon (1996, mainline series):**
- Side-vs-side; 1v1 with bench (party size 6, active 1)
- Type matchup grid (18×18 elemental wheel)
- 4 move slots per Pokémon; PP (use count) per move
- Turn order: priority moves > speed stat
- Engine-deterministic: damage = `(((2L/5+2)·P·A/D)/50+2)·STAB·type·crit·rnd(0.85-1.0)`
- **Lesson:** Clean engine math; player picks moves; narration is one-line text. PROVES engine-only-math works at scale (28+ years, billion player-hours).

**Honkai Star Rail (2023, HoYoverse):**
- Side-vs-side; 4 active per side + bench; tag in/out
- **Action Value** initiative system (recommend for V1):
  - Each character has Speed stat (e.g., 100)
  - `action_value = 10000 / speed` (e.g., speed=100 → AV=100)
  - Turn order = ascending AV; lowest AV goes first; reset to baseline + AV after acting
  - Cleaner than DEX-ordered (smooth fractional turns; supports "advance forward 25%" buffs)
- 4 action types per character: Basic / Skill (uses skill points) / Ultimate (charges from damage taken/dealt) / Talent (passive)
- Weakness break system: hit elemental weakness → break gauge → bonus damage + status
- Engine-deterministic; visuals are flavor; 3D animation is post-resolution narration equivalent
- **Lesson:** Action value > DEX order. Skill point economy adds depth without LLM math. Weakness break = engaging player choice without complexity explosion.

**Persona 5 (2016, Atlus):**
- Side-vs-side; 4 active per side
- "1 More" system: hit elemental weakness → extra turn for that character
- "All-Out Attack" when all enemies down: cinematic finisher
- Baton Pass: pass extra turn to teammate (synergy depth)
- **Lesson:** Reward systems for hitting weakness create engagement loop without complex math. "1 More" + Baton Pass are high-impact mechanics with simple state machine — fit LLM-zero-math discipline.

**Fire Emblem Three Houses (2019, Intelligent Systems):**
- Grid tactics; 8×8 to 20×20 maps; 4-12 units per side
- Movement: terrain-cost grid; range: weapon-defined (1 melee, 2 spear, 1-2 axe, 1-3 mage, 1-2 archer)
- Weapon triangle: sword > axe > spear > sword (rock-paper-scissors)
- Permadeath optional toggle
- **Lesson:** Grid tactics is engine-deterministic but **TOKEN-EXPENSIVE for LLM narration** (every unit × every turn × every map cell = explosion). V1 NOT viable; V2+ within-cell zone graph (3-8 zones) is feasible.

**Final Fantasy Tactics (1997) / Tactics Ogre (1995, 2010, 2022):**
- Isometric grid tactics; height/elevation matters; charge time (CT) initiative
- Job system: 20+ classes with ability inheritance
- **Lesson:** Job system depth is too much for V1; CT initiative similar to HSR action value (already proven simpler). Isometric grid in V2+ zone graph CSC_001 = perfect fit.

**Slay the Spire (2017, Mega Crit):**
- Solo card-based; 75+ cards per character; deck-building
- Status effects: Vulnerable / Weak / Strength / Dexterity / Poison
- Block + HP + Energy economy
- **Lesson:** Status effect breadth (PL_006 already has) is the depth source. Card-based paradigm doesn't fit our game (no card metaphor in tu tiên / wuxia). But the **status-effect-as-depth** lesson applies.

**Disco Elysium (2019, ZA/UM):**
- Skill-check narrative; 24 skills × d6 rolls; difficulty thresholds
- "Combat" is essentially heavy skill checks with consequences
- LLM-equivalent narration is the GAME, not the math
- **Lesson:** For SOCIAL conflict / luận đạo / political confrontation, this paradigm wins. NOT for physical combat (engine-driven). V1+30d social skirmish feature.

**Baldur's Gate 3 (2023, Larian Studios):**
- D&D 5e turn-based tactical; grid + d20 + advantage/disadvantage
- LLM-equivalent narration via cinematic camera + voice acting; engine = 5e ruleset
- Reaction system (out-of-turn actions) adds depth
- **Lesson:** Reactions (V1+ COMB-D feature) add depth without breaking turn semantic.

### §3.3 Recommended V1: Hybrid A+D (with F deferred V1+30d)

**"Side-based 2-row abstract combat with engine-owned math + LLM dramaturgy via Layer 3 narration"**

Combine:
- **Pokemon (A)**: side-vs-side, party of 1-6, simple action menu, engine math
- **JRPG (D)**: 2-row positioning (Front/Back); back row reduces incoming damage but range-restricted
- **HSR action value**: clean initiative
- **Persona 1-More-ish**: weakness exploit gives bonus turn (V1+ deferred — keep V1 minimal)
- **Slay the Spire status breadth**: leverage existing PL_006

Skip:
- **FE/FFT grid (B)**: V2+ via CSC_001 zone graph
- **Action RPG (C)**: architectural mismatch
- **Card (E)**: paradigm mismatch
- **Disco Elysium pure narrative (F)**: V1+30d social skirmish only

→ Best 80/20 ratio: 80% from existing systems; 20% new combat-specific layer; minimal token budget impact; clean LLM-engine separation; maps to Pokemon (proven 28-year engine-only-math archetype).

---

## §4 — 3-layer architecture (LLM-zero-math LOCKED)

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: CombatEngine (DETERMINISTIC; NO LLM CALLS)             │
│  ────────────────────────────────────────────────────────────────│
│  - Initiative queue (HSR action value system)                    │
│  - Damage formula (attacker stats - defender stats ± seeded RNG) │
│  - Hit/dodge roll (deterministic; seed = (turn,actor,action))    │
│  - Status effect tick (delegates to PL_006 — already engine)     │
│  - Critical/elemental modifiers (V1 stub; V1+ DF7 expand)        │
│  - Win/lose detection (HP=0 → WA_006 mortality state)            │
│  - Replay determinism FREE (TDIL-A9 strengthened)                │
│  Output: ResolutionResult { damage, hit, status, ko, ... }       │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2: AIDecisionLayer (LLM PARTICIPATES — Major NPC ONLY)    │
│  ────────────────────────────────────────────────────────────────│
│  - PC actor:                                                     │
│      → input from User UI command (Submit ActionDecl)            │
│  - Major NPC (AIT_001 Tracked tier):                             │
│      → NPC_002 Chorus AssemblePrompt(combat_ctx)                 │
│      → LLM returns structured ActionDecl (Pydantic-validated)    │
│      → engine rejects + fallback Defend if invalid action        │
│  - Minor NPC (AIT_001 scripted tier):                            │
│      → minor_behavior_scripts.reaction_table lookup              │
│      → deterministic; ZERO LLM call                              │
│  - Untracked NPC (AIT_001 ephemeral tier):                       │
│      → engine bulk-resolve as group (stat-summed source)         │
│      → ZERO LLM call                                             │
│  Output: ActionDecl { kind, target, args }                       │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3: NarrationLayer (LLM POST-RESOLUTION ONLY)              │
│  ────────────────────────────────────────────────────────────────│
│  - Input: ResolutionResult batch (entire round's actions)        │
│  - LLM gets "Strike for 47 dmg crit on Hostile #2; Heal +30..."  │
│  - LLM outputs prose narration paragraph (I18nBundle)            │
│  - LLM CANNOT modify damage; ONLY describes                      │
│  - Token cost: 1 batched call per round (not per action)         │
│  - Async non-blocking: round resolves, narration follows         │
│  Output: I18nBundle prose                                        │
└──────────────────────────────────────────────────────────────────┘
```

**Key invariants:**
- LLM NEVER touches Layer 1 — bug = engine bug, not hallucination
- LLM ONLY action-decides (Layer 2 Major) and narrates (Layer 3) — these are LLM's strengths
- Replay is FREE (deterministic Layer 1 + structured Layer 2 outputs in event log)
- Token cost per round: ≤K LLM calls (K = number of Major NPCs needing action select) + 1 narration call

**Token budget per combat round (worst case):**
- 2 sides × 3 Major NPCs × 1 action-select call = 6 calls
- 1 batched narration call = 1 call
- **Total: 7 calls/round**
- 10-round combat = 70 calls
- Well within 30k token context budget; comparable to non-combat LLM-driven turns

---

## §5 — V1 deterministic formula seed (engine-owned)

These are **starting points** for Q-deep-dive — NOT yet locked, just illustrative.

### §5.1 Damage (Strike action) — 4-step law chain LOCKED

**Damage composition law ordering** (adopted from chaos-backend `docs/combat-core/02_Damage_System_Design.md` lines 99-117 — Critical Implementation Requirements: "Damage Composition Law"). Order is **engine-agnostic + turn-based-friendly + extensible to V1+ DF7-equivalent without refactor**:

```
// STEP 1 — base damage (V1 stat-difference; V1+ chaos-backend power_points - defense_points law)
base = max(1, atk.strike_power - def.armor)

// STEP 2 — element multiplier (V1 placeholder = 1.0; V1+ DF7 fills element interaction matrix)
elem_mult = elemental_table[atk.element][def.element]   // V1 always 1.0
elemented = base × elem_mult

// STEP 3 — resistance after penetration (V1 trivial; V1+ DF7 fills resistance + penetration stats)
resistance = max(0, def.resist_pct - atk.penetration_pct)   // V1 always 0
defended = elemented × (1 - resistance)

// STEP 4 — RNG variance + crit (V1 active; deterministic seeded)
roll       = uniform(0.85, 1.15, seed = (reality_id, turn_id, actor_id, action_idx, "damage"))
crit_roll  = uniform(0, 1,        seed = (reality_id, turn_id, actor_id, action_idx, "crit"))
crit_mult  = (crit_roll < atk.crit_chance) ? 2.0 : 1.0
damage     = floor(defended × roll × crit_mult)

// STEP 5 — status apply AFTER damage (chaos-backend invariant; prevents pre-damage stat warp)
if action.applies_status:
    engine.apply_status(target, action.status_id, magnitude, duration)
```

**Why this order locked V1** (per chaos-backend §02 Damage Composition Law invariants):
- **base → element FIRST** (multiplicative scaling — must apply before resistance subtraction)
- **resistance AFTER penetration** (penetration is pre-resistance modifier; if reversed, double-discounts)
- **RNG roll AFTER damage shape** (variance is cosmetic, not corrective; applying RNG before resistance amplifies tail outcomes)
- **status AFTER damage** (status applied pre-damage would warp same-turn defense stat — engine consistency invariant)

**V1 effective collapse** (since V1 element_mult=1.0 + resistance=0 + penetration=0):
```
damage_v1 = floor(max(1, atk.strike_power - def.armor) × roll × crit_mult)
```
But the 4-step **chain ordering is locked V1** even though V1 collapses — so V1+ DF7 promotion (PROG-D24) just fills `elemental_table` + populates `resist_pct/penetration_pct` stat columns; **no refactor of damage_calculator.rs needed**.

**PROG_001 stats consumed (V1):**
- `strike_power` (offense, attribute kind, body-bound)
- `armor` (defense, attribute kind, body-bound)
- `crit_chance` (probability, attribute kind, body-bound; V1 default 0.05)

**PROG_001 stats reserved V1+** (schema-present, V1 always 0):
- `resist_pct` per element kind (HashMap<ElementId, f32>)
- `penetration_pct` per element kind (HashMap<ElementId, f32>)
- `element` per attack source (Option<ElementId>; None = neutral V1)

**"Omni additive-only rule"** (chaos-backend element-core invariant `06_Implementation_Notes.md`): when V1+ DF7 promotion adds Omni stats (universal stat bonus from cultivation/level), Omni MUST be **additive only** — never multiplicative. Multiplicative Omni stacking is forbidden permanently to prevent runaway stat inflation. V1 has no Omni stat; V1+ DF7 promotion respects this constraint.

### §5.2 Hit / dodge

```
hit_chance = clamp(0.50 + atk.accuracy - def.dodge, 0.05, 0.95)
hit_roll   = uniform(0, 1, seed = (turn_id, actor_id, "hit"))
hit        = (hit_roll < hit_chance)
if not hit: damage = 0; emit MissEvent
```

### §5.3 Initiative (HSR action value, V1 recommended)

```
on combat start:
  for each actor: action_value[actor] = 10000 / actor.speed

main loop:
  next_actor = argmin(action_value)
  delta_av = action_value[next_actor]
  for all actor: action_value[actor] -= delta_av
  resolve action of next_actor
  action_value[next_actor] = 10000 / next_actor.speed   // reset
  // status effect "advance forward X%" tweaks: action_value[actor] -= (10000/speed) × X/100
```

**Why HSR action value over DEX-order:**
- Smooth fractional turns (speed=110 vs speed=100 → 110 acts ~10% more often, deterministic)
- Supports "advance forward" / "delay" status effects without state hacks
- Battle-tested at scale (HSR has 80M+ MAU using this system)
- Cleaner replay (single integer queue vs comparator chain)

### §5.4 Status effect (delegates to PL_006)

Combat does NOT invent new status effects; uses existing PL_006:
- Apply: `engine.apply_status(target, status_id, magnitude, duration_turns)`
- Tick: PL_006 schedules expire/dispel via existing tick scheduler
- Display: PL_006 owns the I18n display name + magnitude UI

V1 combat-relevant statuses (subset of PL_006):
- `bleed` (DoT damage per turn)
- `stunned` (skip next turn)
- `defending` (50% incoming damage reduction; expires after 1 turn)
- `poisoned` (DoT magnitude scaling with original cast power)
- `rooted` (cannot Flee)

V1+ deferred (PL_006 reservations already exist):
- Elemental affinity status (Burning / Frozen / Shocked / Wet)
- Charm / Confuse (engine-controlled action)
- Resurrection prevention

### §5.5 Win/lose detection

```
on each ResolutionResult applied:
  if all actors on side X have HP=0:
    side X loses
    side ¬X wins
    all KO'd actors → WA_006 Dying state (per actor mortality config)
    emit CombatEndEvent { winner_side, casualties }
```

V1 does NOT have:
- Time-based victory (run out turn limit)
- Objective-based victory (V1+ for QST_001 quests)
- Surrender mechanic (V1+30d COMB-D5)
- Capture (V1+30d for recruiting hostile NPCs)

---

## §6 — Action set V1 (5 verbs)

Combat actions are a **subset of PL_005 Interaction intents** specialized for combat mode:

| Verb | Cost | Engine resolution | LLM narration template hint |
|---|---|---|---|
| **Strike** | 1 turn; basic stamina cost | engine.compute_damage; engine.apply_hit | "{actor} attacks {target} with {weapon}" |
| **Defend** | 1 turn; no cost | apply `defending` status to self (50% reduction next turn) | "{actor} braces for incoming attacks" |
| **Skill** | 1 turn; skill-defined stamina/mana cost; PROG_001 skill kind unlock-gated | engine.execute_skill (skill_id-defined formula; can be damage / heal / status / movement V2+) | "{actor} channels {skill_name}" |
| **UseItem** | 1 turn; consumes 1 item from RES_001 inventory | engine.apply_item_effect (item-defined: heal / cure / buff / damage) | "{actor} uses {item_name}" |
| **Flee** | 1 turn; speed-vs-speed roll vs hostile fastest | if success: actor exits combat (encounter scope); if fail: actor wastes turn | "{actor} attempts to flee" |

**Notable design choices:**
- **No "Attack" + "Defend" combo on same turn** — each turn = 1 action (clean, simple, low-token)
- **Skill is the depth dimension** — V1 skills come from PROG_001 skill kinds; V1+ adds elemental skills via DF7 promotion
- **Flee is per-actor** — individual NPCs can flee separately; not whole-side
- **No "Move" verb V1** — V1 is abstract (no zone graph movement); V2+ adds via CSC_001 zone tactics

---

## §7 — Side allegiance (FAC_001-derived)

At encounter start, engine auto-assigns sides via FAC_001 RelationStance:

```
on encounter trigger (PC initiates Strike on Hostile NPC):
  side_friendly = [PC, *PC.party_members]
  side_hostile  = [hostile_npc, *hostile_npc.allied_via_FAC_001]
  
  for each NPC in cell:
    stance_to_PC = FAC_001.get_stance(NPC.faction, PC.faction)
    if stance_to_PC == Hostile and NPC is Tracked: → side_hostile
    if stance_to_PC == Allied  and NPC is Tracked: → side_friendly
    if stance_to_PC == Neutral: → noncombatant (excluded from combat)
    if NPC is Untracked: bulk-resolve based on faction default
```

**Edge cases (deferred V1+):**
- Multi-faction free-for-all (3+ sides) — V1 limits to 2 sides per encounter
- Faction defection mid-combat — V1+ COMB-D6
- Neutral civilian caught in crossfire — V1 ignores (excluded); V1+ status injury system

---

## §8 — Encounter mode (state machine)

Combat is an **explicit state** — entering combat changes turn semantic per turn (multi-actor turn order vs single-actor narration turn).

### §8.1 V1 state machine

```
[Idle] ──(Strike intent on Hostile)──> [CombatActive]
[CombatActive] ──(all hostiles HP=0)──> [Resolved:Victory] ──> [Idle]
[CombatActive] ──(all friendlies HP=0)──> [Resolved:Defeat] ──> WA_006 mortality
[CombatActive] ──(all friendlies Flee)──> [Resolved:Disengaged] ──> [Idle]
[CombatActive] ──(all hostiles Flee)──> [Resolved:Routed] ──> [Idle]
```

### §8.2 Trigger conditions (V1)

Combat enters when:
1. PC submits `Strike` intent against an actor with FAC_001 stance != Allied
2. Hostile NPC AI selects `Strike` against PC (Major NPC LLM picks; Minor scripted)
3. Lex axiom triggers ambush (V1+30d COMB-D7)

Combat does NOT enter when:
- Strike against Allied (Lex rejects per existing `lex.faction_violation`)
- Strike against Neutral civilian: V1 rejects with `combat.target_neutral_forbidden` (V1+ allows but triggers reputation/mortality cascade)

### §8.3 Encounter aggregate (T2/Reality, sparse)

`combat_session` aggregate (NEW; sparse — only present during active combat):

```rust
pub struct CombatSession {
    pub session_id: CombatSessionId,
    pub channel_id: ChannelId,                    // single cell per TDIL-A5
    pub started_at_turn: u64,
    pub side_a: Vec<ActorRef>,                    // friendly to initiator
    pub side_b: Vec<ActorRef>,                    // hostile to initiator
    pub round_number: u32,
    pub initiative_queue: Vec<(ActorRef, i32)>,   // (actor, action_value)
    pub resolved_actions_this_round: u32,
    pub state: CombatState,                       // Active / Resolved / Cancelled
}
```

**Lifecycle:**
- Born on encounter start (EVT-T4 CombatSessionBorn)
- Mutated each round (EVT-T3 CombatRoundDelta)
- Removed on encounter end (EVT-T4 CombatSessionResolved)
- Persistence V1: in-memory + checkpoint per round end (replay-recoverable per TDIL-A9)

---

## §9 — AI action selection (Layer 2 detail)

### §9.1 Major NPC action select prompt

Combat-mode AssemblePrompt extension to NPC_002 Chorus:

```
{persona_card}                                  // existing NPC_002

{combat_state_summary}:                         // NEW combat extension
  side_friendly:
    - {NPC.name}: HP {hp_pct}%, SP {sp_pct}%, status: [{status_list}]
    - {ally1.name}: HP {hp_pct}%, ...
  side_hostile:
    - {hostile1.name}: HP {hp_pct}%, status: [{status_list}]
    - ...
  initiative_queue_next_3: [{actor1}, {actor2}, {actor3}]
  
{available_actions}:                            // NEW; engine-supplied; restricts hallucination
  - Strike { target: ActorRef }
  - Defend
  - Skill { skill_id: SkillId, target: Option<ActorRef> }
  - UseItem { item_id: ItemId, target: Option<ActorRef> }
  - Flee
  
{narrative_context}:                            // NEW; engine-supplied recent events
  "Last round: Lão Ngũ was hit for -23 HP and is at 47/100"
  "Trợ thủ Tiểu Thúy used Heal on Lão Ngũ for +20"
  
→ LLM returns STRUCTURED ActionDecl (JSON / function-call):
  { kind: "Skill", skill_id: "self_heal", target: "self" }
  
→ Engine validates:
  - kind ∈ {Strike, Defend, Skill, UseItem, Flee}
  - target valid (alive ActorRef on appropriate side)
  - skill_id ∈ actor's PROG_001 unlocked skills
  - item_id ∈ actor's RES_001 inventory
  - resource cost affordable
  
→ If invalid: log canon_drift_flag (LLM hallucinated); fallback to Defend
```

**Why structured response (not free-text):**
- Eliminates LLM hallucination of non-existent skills/items
- Pydantic / function-call validation = deterministic
- Engine never has to "interpret" LLM intent
- Token cost lower (structured > prose)

### §9.2 Minor NPC scripted action

`minor_behavior_scripts.combat_reaction_table` (V1):

```rust
pub struct CombatReactionEntry {
    pub trigger: CombatTrigger,                   // OnTurnStart / OnHpThreshold / OnAllyKO / ...
    pub action: ActionDecl,                       // pre-canned
    pub priority: u8,                             // higher wins on multi-trigger
}
```

Example:
```yaml
combat_reactions:
  - trigger: OnHpThreshold { below_pct: 30 }
    action: { kind: UseItem, item_id: "healing_pill" }
    priority: 100
  - trigger: OnTurnStart
    action: { kind: Strike, target: "lowest_hp_hostile" }
    priority: 10
```

ZERO LLM call. Deterministic. Replay-perfect.

### §9.3 Untracked bulk resolution

For Untracked NPCs (e.g., 5 bandits ambushing PC):
- Engine treats group as single damage source: `total_damage = sum(individual_damages)`
- Group HP pool (one number); when 0 → group flees or all KO'd
- ZERO LLM call; ZERO per-actor state
- AIT_001 untracked_density already constrains group size ≤12

---

## §10 — Narration layer (LLM Layer 3)

### §10.1 Round narration prompt

After all actions in a round resolve, batch ALL ResolutionResult into one LLM call:

```
{combat_persona_register}                       // tu tiên / wuxia / sci-fi tone

Round {round_number} resolution:

{ResolutionResult_1}: "Lão Ngũ used Strike on Du sĩ → 47 damage (crit)"
{ResolutionResult_2}: "Du sĩ used Defend → +50% reduction next turn"
{ResolutionResult_3}: "Tiểu Thúy used Skill: Heal on Lão Ngũ → +20 HP"
{ResolutionResult_4}: "Du sĩ used Strike on Tiểu Thúy → MISS (dodge)"

Side state after round:
  side_friendly: Lão Ngũ 67/100, Tiểu Thúy 80/80
  side_hostile: Du sĩ 53/100 (defending)

→ LLM outputs prose narration paragraph (I18nBundle):
  default: "Lão Ngũ swings his blade, finding a critical opening in Du sĩ's stance — blood arcs through the air as the strike connects. Du sĩ steadies himself, raising his guard. Tiểu Thúy weaves a quick mending spell, restoring Lão Ngũ's vitality. Du sĩ retaliates, but his blade only cuts the wind as Tiểu Thúy slips aside."
  translations:
    vi: "Lão Ngũ vung đao, tìm được khe hở chí mạng trong thế thủ của Du sĩ..."
```

### §10.2 Constraint discipline

LLM narration MUST NOT:
- Change damage numbers ("47 damage" stays 47, never narrated as "deals devastating blow killing instantly")
- Modify state ("Lão Ngũ HP 67/100" stays; no "Lão Ngũ collapses unconscious" if engine says HP > 0)
- Invent missing actions ("Du sĩ teleports behind" — not in ResolutionResult)
- Skip ResolutionResults ("but Tiểu Thúy didn't act this round" — when she did)

LLM narration CAN:
- Color the prose with cultivation atmosphere / wuxia tone / character personality
- Reference status effect mood ("with poisoned blood weakening her grip")
- Embellish weapon / skill flavor ("the Heaven-Splitting Sword Strike technique unleashes")
- Vary sentence structure between rounds (avoid repetition)

### §10.3 A6 canon-drift discipline

A6 canon-drift detector:
- DOES check narration for engine-state contradictions (engine says HP=67, narration says "fallen")
- DOES NOT flag stylistic embellishment (engine says "Strike for 47", narration says "lethal blow") — reasonable artistic license unless contradicts state
- V1 implementation: detect ResolutionResult outcome inversion (KO claim when alive; alive claim when KO'd); other drift V1+

---

## §11 — Cell + zone integration (V1 minimal; V2+ tactical)

### §11.1 V1 — abstract arena (no zone graph)

V1 combat happens IN a cell (per TDIL-A5 atomic-per-turn travel) but does NOT use the cell's zone graph mechanically. The cell provides:
- Scene context for narration (tavern → "amid overturned tables and shattered glasses")
- 2-row positioning metaphor ONLY (Front / Back; not actual CSC_001 zones)
- Cell occupancy via existing CSC_001 Layer 4 (combat doesn't add new occupancy slots)

### §11.2 V1 — Front/Back row mechanic

Each side has 2 rows (mượn JRPG D archetype):
- **Front row**: melee range; +0 damage modifier given/received
- **Back row**: ranged-only attacks reach; -25% melee damage received from non-pierce attacks; -25% melee damage given (penalty)

```
on Strike resolution:
  if attacker.row == Back and skill.range == Melee:
    damage *= 0.75   // back row penalty for melee
  if defender.row == Back and attack.kind == Melee:
    if attacker.row == Front: damage *= 0.75   // back row protection
    // else attacker also Back → no extra modifier
```

V1 row assignment:
- PC chooses own row (UI button)
- Major NPC: LLM picks via combat AssemblePrompt (or scripted default)
- Minor NPC: scripted default (warrior=Front, mage=Back)

### §11.3 V2+ zone-graph tactics

When CSC_001 zone graph V2+ enrichment ships:
- Battlefield = CSC_001 zones (3-8 zones per cell)
- Movement: 1-2 zones/turn (depending on speed)
- Range: weapon/skill-defined zone reach (1-3 zones)
- Cover/elevation: zone metadata
- AoE: zone-shaped (single zone / line / radius)

V2+ promotes Front/Back row to zone graph naturally; V1 row metaphor is the bridge.

---

## §12 — TDIL_001 integration

### §12.1 V1 — combat duration in fiction time

Combat happens during 1 turn of the channel's fiction_clock (atomic-per-turn travel TDIL-A5):
- Outside combat: 1 turn = N hours/days fiction (per channel time_flow_rate)
- Inside combat: rounds happen "within" the turn (cinematic compression)
- Total combat fiction duration: ~5-15 minutes regardless of round count (V1 simplification)

V1+ refinement (COMB-D8): combat fiction duration scales with round count and time_flow_rate (Dragon Ball chamber combat = years pass while training, but combat itself is brief).

### §12.2 V1+ — body_clock reaction speed (TDIL-D9)

Promoted from TDIL-D9 deferral:
- Initiative speed reads `actor_clocks.body_clock` recent delta
- "Younger body, faster reflexes" — actor with body_clock advanced 100yr but actor_clock 200yr (meditative cultivator) has slow reflexes per body
- Wuxia trope: the elder with young body via cultivation pill is fast despite long actor_clock

V1: speed = PROG_001 stat only; V1+: speed += body_clock_youth_modifier.

### §12.3 V3+ — Lorentz-aware combat (TDIL-D10)

If combat happens at extreme time_flow_rate boundary (Dragon Ball chamber wall fight):
- Relativistic timing: actor on slow-rate side has dilated reflexes vs fast-rate side
- Replay still deterministic (rates static)
- Heavily deferred — gameplay novelty rather than V1 requirement

---

## §13 — V1 minimum delivery (anticipated 9-10 V1 catalog entries)

Anticipated catalog entries for COMB_001 DRAFT (subject to Q-deep-dive lock):

1. `combat_session` aggregate (T2/Reality, sparse, owner=Reality)
2. CombatState enum (Active / Resolved:Victory / Resolved:Defeat / Resolved:Disengaged / Resolved:Routed / Cancelled)
3. ActionDecl variants V1 (5: Strike / Defend / Skill / UseItem / Flee)
4. CombatTrigger conditions for Minor NPC scripted reactions
5. HSR action value initiative system (engine V1)
6. V1 deterministic damage formula (engine V1; PROG_001 §9 closure-pass)
7. V1 hit/dodge/crit roll (engine V1; seeded RNG)
8. Combat-mode NPC_002 Chorus AssemblePrompt extension
9. Combat-mode L3 narration prompt batched per-round
10. Side allegiance auto-assignment via FAC_001 RelationStance

V1+ deferrals (COMB-D1..COMB-D10 anticipated): social skirmish / surrender / capture / multi-faction / movement V2+ / objective-based victory / etc.

---

## §14 — Q-deep-dive LOCKED matrix (Q1-Q9 ALL LOCKED 2026-04-27)

> **All 9 questions LOCKED via 4-batch deep-dive 2026-04-27** (Batch 1: Q1+Q5+Q9 / Batch 2: Q2+Q3 / Batch 3: Q4+Q6+Q8 / Batch 4: Q7). User approved each batch with "1" approval. Original options + lean preserved as Appendix-style headers; LOCKED specifics + invariants in subsection bodies.

### §14.0 — LOCKED summary table

| Q | Topic | LOCK | Key invariants |
|---|---|---|---|
| Q1 | Party size | **(B+) PC + ≤3 Major + ∞ Minor** | Encounter-scoped; co-locked Q3 KO-revivable; no persistent party state V1 |
| Q2 | Encounter mode | **(A) Explicit state machine** | 1 PL_001 turn = 1 combat round; -25% AV initiator bonus; PL_005 closure-pass intent restriction |
| Q3 | Death semantics | **(B+C hybrid) PL_006 status `knocked_out`** | Reality `combat_mortality_config` (Hybrid V1 default); per-actor `mortality_role` (Standard/Bypass) |
| Q4 | Level disparity cap | **(C++) Reality + Lex + PlaceMetadata** | Flat 50% cap when PvP + safe-zone + tier ≥ 3 disparity |
| Q5 | Multi-side | **(A+) 2 sides V1 with `sides: Vec<Side>` cap=2** | Schema future-proofs V1+ 3-side relaxation (FAC_001 Q2 pattern) |
| Q6 | Stat hiding | **(C++) Hybrid: self/party exact; hostile bar % + vague** | 5-tier I18nBundle text label; LLM narration coherence enforced |
| Q7 | Initiative | **(A++) HSR Action Value** | `av = 10000/speed`; AV mutation status integration; CT-as-V1+-extension path |
| Q8 | RNG transparency | **(A++) Hidden seed; atomic encounter** | Action-keyed seed `(reality_id, turn_id, actor_id, action_idx, role)`; event-log-derivable replay |
| Q9 | AI tier prompts | **(B++) Tiered: Trivial/Standard/Boss + IDF_003 archetype** | NEW `combat_role: CombatRoleHint` field on actor_chorus_metadata; boss 3-round memory window |

### §14.1 — Q1 LOCKED · Player party size

**Original options:** (A) Solo PC · (B) PC + ≤3 · (C) PC + ≤5 · (D) Reality-configured

**LOCK: (B+) PC + ≤3 Major companions + ∞ Minor companions V1**

**Invariants:**
- Hard cap: ≤3 Major-tier companions per friendly side (token budget discipline; AIT_001 Major tier dispatch)
- Soft cap: ∞ Minor companions (scripted reaction_table; ZERO LLM call; engine-cheap)
- Encounter-scoped party formation — no persistent party state V1
- Auto-join `side_friendly` rule: actors in cell + Allied-stance-to-PC + alive + within Major cap at encounter trigger
- Token budget worst case: 1 PC + 3 Major friendly + 4 hostile (1 boss + 3 standard) = 7 LLM calls/round + 1 narration

**Co-locked dependencies:**
- **Q3 KO-revivable mandatory** (otherwise named Major companion permadeath = grief vector)
- FAC_001 master-disciple chain produces natural party composition (no new infrastructure)
- PCS_001 V1+ adds persistent party UI + companion persistence across encounters

**V1+ extension path:**
- V1+ persistent party UI (PCS_001 PC Substrate)
- V1+30d party-of-6 reality config option
- V1+30d cross-encounter companion progression sync

### §14.2 — Q2 LOCKED · Encounter mode

**Original options:** (A) Explicit state machine · (B) Emergent

**LOCK: (A) Explicit state machine — confirmed**

**Invariants:**
- 5-state machine: `Idle` ↔ `CombatActive` → `Resolved:Victory` / `Resolved:Defeat` / `Resolved:Disengaged` (+ admin `Cancelled`)
- 1 PL_001 turn = 1 combat round (cinematic compression — multiple actor actions resolve within single fiction_duration step)
- Combat round semantic: "round = until all non-KO actors have acted ≥1 AV pop" (Q7 cross-LOCK)
- Initiator initiative bonus: -25% first-turn AV (HSR-style ambush mechanic)
- 3 trigger paths V1: PC-initiates / NPC-ambush-via-Lex-axiom / mutual-encounter
- `combat_session` aggregate sparse — born on trigger; removed on resolution
- TDIL_001 compatibility: 1 round @ Dragon Ball chamber rate = 365× wall-time fiction; engine still 1 PL_001 turn

**Combat-mode intent restrictions** (PL_005 closure-pass-extension):
- ✅ Allowed during CombatActive: Strike / Defend / Skill / UseItem / Flee
- ❌ Rejected during CombatActive: Speak / non-combat Action / MetaCommand / FastForward → `combat.action_invalid_in_state`
- ⚠ V1+30d: combat-Speak (taunt) becomes valid action

**V1+ extension path:**
- V1+30d aggro escalation trigger (Speak-fail + threat threshold)
- V1+30d ambush stealth detection (surprise round; auto-initiative-win)
- V1+ combat-Speak taunt action

### §14.3 — Q3 LOCKED · Death semantics

**Original options:** (A) Immediate Dying · (B) KO intermediate · (C) Author-configured

**LOCK: (B+C hybrid) — KO via PL_006 status `knocked_out`**

**Invariants:**
- KO implementation: NEW PL_006 status entry `knocked_out` (Option β; cleaner than EF_001 lifecycle variant)
- KO behavior contract:
  - ❌ Cannot select action (Layer 2 skip)
  - ❌ Cannot be targeted by hostile Strike (forces retargeting; prevents corpse-camping)
  - ⚠ CAN be targeted by friendly Skill: Revive / UseItem: revive_pill (V1+)
  - ⚠ Counts as "down" for win-condition (all friendlies KO'd → side defeat)
  - ⏱ Auto-expire after `ko_duration_rounds` → transition to WA_006 Dying state
- Reality config: NEW `combat_mortality_config` on RealityManifest:
  - `mode: PermadeathMode { Hard | Soft | Hybrid }` (V1 default Hybrid)
  - `ko_duration_rounds: u8` (V1 default 5)
  - `combat_end_revive: bool` (V1 default true; KO actors revive at 1 HP on combat end)
- Per-actor override: NEW `mortality_role: MortalityRole { Standard | Bypass }` on CanonicalActorDecl
  - Standard: uses reality config (KO + revive)
  - Bypass: HP=0 → immediate Dying (boss "kill confirmed" semantic)
- Untracked NPC: no KO state V1 (bulk-resolved; group HP=0 → all flee or all die)
- PC = Standard (uses reality config; no PC special-casing)

**KO duration tick semantic** (Q7 cross-LOCK): round = "until all non-KO actors have acted ≥1 AV pop"; KO counter decrements per round increment.

**V1+ extension path:**
- V1+ Skill: Revive ability (PROG_001 skill kind)
- V1+30d Forge:Revive + Forge:CompleteKO admin overrides (COMB-D cluster)
- V1+ KO/Bypass auto-link validator suggestion (declaring CombatRoleHint::Boss → suggests MortalityRole::Bypass; explicit override allowed)

### §14.4 — Q4 LOCKED · Level disparity cap

**Original options:** (A) Pure stat math · (B) Hard-cap Lex · (C) Author-configured

**LOCK: (C++) Reality + Lex + PlaceMetadata composition**

**Invariants:**
- Cap formula V1: flat 50% — `damage = min(damage, target.hp × 0.5)` when conditions met
- Conditions V1 (ALL must hold): `attacker.kind=PC && defender.kind=PC && both_in_safe_zone && tier_disparity ≥ 3`
- Reality config: NEW `combat_disparity_cap: CombatDisparityCapConfig`:
  - `enabled: bool` (V1 default true; tu tiên reality override false for harsh realism)
  - `tier_disparity_threshold: u8` (V1 default 3 progression tiers)
  - `cap_pct_of_target_hp: f32` (V1 default 0.50)
  - `apply_to_pc_vs_pc_only: bool` (V1 default true)
- PF_001 closure-pass-extension: NEW `combat_safety: CombatSafetyLevel { None | NewbieZone | Sanctuary | NoPvP }` field on PlaceDecl
- Auto-default per place_type V1:
  - `town_square` / `marketplace` / `temple` / `inn` → NewbieZone (cap on)
  - `wilderness` / `cave` / `mountain` → None (cap off; harsh)
  - `sect_arena` / `dueling_grounds` → NoPvP-cap-bypass (sect duel rules)
- WA_001 closure-pass-extension: NEW Lex axiom `combat_damage_cap_in_safe_zone` (engine-driven enforcement)
- Asymmetric cap policy:
  - PC ↔ PC PvP in safe zone: ✅ cap (anti-grief)
  - PC ↔ NPC: ❌ no cap (NPC may legitimately be 元嬰)
  - NPC ↔ NPC: ❌ no cap (immersion-first)

**V1+ extension path:**
- V1+30d diminishing-returns formula: `damage × (1 / (1 + tier_disparity × 0.2))`
- V1+ asymptotic formula: `damage × min(1, sqrt(target_tier / attacker_tier))`
- V1+30d faction-specific arena overrides (sect duel rule sets)

### §14.5 — Q5 LOCKED · Multi-side

**Original options:** (A) 2 sides · (B) ≤3 sides · (C) N sides

**LOCK: (A+) 2 sides V1 with future-proof `sides: Vec<Side>` cap=2 schema**

**Invariants:**
- `combat_session.sides: Vec<Side>` (NOT `side_a` + `side_b` discrete fields)
- V1 validator: `sides.len() == 2` (cap=2 enforced)
- Each `Side` = `{ side_id, actor_refs: Vec<ActorRef>, allegiance_origin: AllegianceOrigin }`
- Sides are **encounter-local tactical alliance**, NOT strict FAC_001 stance
  - Multiple FAC-Hostile-to-PC factions auto-bucket into `side_b` together for combat duration
  - Inter-side hostility ignored mid-combat
- Side allegiance auto-assignment via FAC_001 RelationStance at encounter start (already in concept-notes §7)
- Schema future-proofs V1+30d 3-side relaxation: relax validator cap=2 → cap=3; ZERO schema migration (FAC_001 Q2 pattern proven)

**V1+ extension path:**
- V1+30d 3-side activation (COMB-D9 wuxia 三方混战 trope; cap=3)
- V1+30d Q5b sub-question: noncombatant in AOE (currently V1 has no AOE; ships when AOE skill ships)
- V1+30d mid-combat side switching (defection per faction stance change)
- V1+ N-side full free-for-all (V2+; complex AI targeting + balance)

### §14.6 — Q6 LOCKED · Stat hiding

**Original options:** (A) All exact · (B) All vague · (C) Hybrid

**LOCK: (C++) Hybrid with HP bar % + 5-tier vague text label**

**Invariants:**
- Information layer per actor type:
  - Self: exact numbers (HUD shows 47/100 HP, 23/30 SP)
  - Allied party: exact numbers
  - Hostile (Major): HP bar relative % + vague text label; status kind visible; status magnitude vague
  - Hostile (Minor): HP bar relative % + vague text label; status kind visible; status magnitude hidden
  - Untracked group: not individually shown ("4 bandits, 2 wounded")
- 5-tier vague label register (engine-determined from HP%; I18nBundle per RES_001 §2):
  - 100% → "Unhurt"
  - 99-75% → "Lightly bruised"
  - 74-50% → "Wounded"
  - 49-25% → "Bloodied"
  - 24-1% → "Near death"
  - 0% → "Knocked out" / "Slain"
- LLM Layer 3 narration coherence constraint (NPC_002 closure-pass-extension):
  - For self/party actors: narration MAY use exact numbers
  - For hostile actors: narration MUST use 5-tier text register; NEVER reference exact numbers
  - A6 canon-drift detector flags exact-number leaks for hostile narration
- Two information channels for LLM: Layer 2 (Major NPC AI) gets engine-omniscient stats in AssemblePrompt (they're AI, not players); Layer 3 narration uses player-visible asymmetric labels

**V1+ extension path:**
- V1+30d Investigate / Cultivation Sense skill (Pokemon Foresight; PROG_001 skill kind reveals exact hostile stats)
- V1+ reality-customizable label register (wuxia: "skin damaged / bones cracking / qi disrupted / soul flickering"; sci-fi: "shields holding / armor cracked / hull breach"; modern: "lightly hurt / serious / critical")

### §14.7 — Q7 LOCKED · Initiative system

**Original options:** (A) HSR Action Value · (B) DEX-ordered · (C) FFT Charge Time · (D) Persona baton-pass

**LOCK: (A++) HSR Action Value V1 — confirmed (D) is layer not core; A wins on V1-simple-V2-extensible)**

**Invariants:**
- Initial AV: `action_value[actor] = 10000 / actor.speed` per actor at encounter start
- Round loop:
  ```
  next_actor = argmin(action_value)
  delta_av = action_value[next_actor]
  for all actor: action_value[actor] -= delta_av
  resolve action of next_actor
  action_value[next_actor] = 10000 / actor.speed   // reset
  ```
- Status effect AV mutation V1 (3 PL_006 status entries):
  - `slowed`: `action_value[actor] += current_av × 0.20` (delay; immediate-tick)
  - `hasted`: `action_value[actor] -= current_av × 0.20` (advance; immediate-tick)
  - `stunned`: `action_value[actor] += current_av × 1.00` (effectively skip turn)
- Initiator initiative bonus (Q2): `initial_av_first_turn = 10000 / speed × 0.75` (-25%)
- Untracked group: single AV entry; `group_av = 10000 / mean(individual_speeds)`
- V1 all 5 action verbs = unit AV reset (1 turn baseline)
- Round semantic for Q3 KO duration tick: round = "until all non-KO actors have acted ≥1 AV pop OR encounter ends"; KO counter decrements per round increment
- Determinism: AV computation pure-function of speed stat (PROG_001) + logged status events + action selections; replay-reconstructable from event log alone (no AV state stored)
- AV queue display in UI: shows acting order (next 3-5 slots); never reveals AV numbers (aligned with Q6 vague-hostile-stat policy)
- AV queue display in LLM Layer 2 prompt: includes `initiative_queue_next_3` for boss-tier strategic depth (Q9 cross-LOCK)

**V1+ extension path:**
- V1+30d action-cost AV multiplier (CT-system-as-extension: `heavy_strike` action AV reset = `10000 / speed × 1.5` slower recovery)
- V1+ DF7 elemental weakness 1-More: hit weakness → push acting actor's AV to 0 (Persona 5 1-More elegantly maps; doesn't refactor AV core)
- V1+30d Baton Pass extra-turn transfer (pass AV=0 push to ally)
- V1+30d max-consecutive-same-actor-turns cap if balance issues surface (HSR's AV gain cap pattern)

### §14.8 — Q8 LOCKED · RNG transparency

**Original options:** (A) Hidden · (B) Visible · (C) Allow savescum

**LOCK: (A++) Hidden seed V1 + atomic encounter + action-keyed determinism**

**Invariants:**
- Seed scheme: `(reality_id, turn_id, actor_id, action_idx, role)` where `role ∈ {damage, hit, crit, dodge, ko_duration}`
- Hidden by default V1 (player UI never shows seed)
- Combat encounter atomic V1 (no mid-combat save)
- Disconnect/reconnect → replay from current round start (engine state checkpointed at round boundary)
- Classic savescum IMPOSSIBLE by design (deterministic seed + action-keyed → reload + same action = same outcome; reload + change action = different seed = legitimate state-progression NOT re-roll)
- State-prediction abuse defeated: changing action invalidates predicted roll (`action_idx` in seed)
- Event log captures `(turn_id, actor_id, action_idx, action_kind, status_events)`; replay engine reconstructs seed from these inputs
- NO seed-storage in event log (seed is computed; not stored)

**V1+ extension path:**
- V1+30d per-round checkpoint UX feature (mid-combat save/load; doesn't affect determinism)
- V1+ developer-mode `combat_seed_visible: bool` flag (QA tooling + content creator transparency + speedrun verification)
- V2+ replay UI tool (consumes event log; reconstructs combat round-by-round; supports anti-cheat via server-side replay against player-claimed actions)

### §14.9 — Q9 LOCKED · AI tier prompts

**Original options:** (A) Single template · (B) Tiered · (C) Per-NPC reality-configured

**LOCK: (B++) Tiered V1 — 3 templates with IDF_003 archetype constraint**

**Invariants:**
- NEW field on actor_chorus_metadata (ACT_001 closure-pass-extension): `combat_role: CombatRoleHint`
- Three tiers V1:
  - `Trivial` — Major because Tracked, low engagement (named patron, ambient cultivator); cheap prompt ~700t input → ~200t output
  - `Standard` — named NPC mid-importance (Du Sĩ, Tiểu Thúy); default; balanced prompt ~1500t input → ~300t output
  - `Boss` — sect master, named villain, recurring antagonist; expensive prompt ~3000t input → ~500t output
- All tiers consume IDF_003 personality archetype constraint (anti-degeneracy):
  - Hothead → preferentially aggressive Strike (often suboptimal)
  - Cunning → flanking + status setup (sophisticated but predictable)
  - Stoic → defensive opener
  - Loyal → protect allies first
- Boss tier ships V1 with **3-round sliding window combat memory** (last 3 rounds' actions in prompt for multi-turn coherence)
- Tier prompt template diff:
  - Trivial: `{persona_card} + {minimal_combat_state} + {available_actions}`
  - Standard: + `{recent_combat_events_1_round}` + `{ally_state_summary}`
  - Boss: + `{recent_combat_events_3_rounds}` + `{multi_turn_planning_hint}` + `{opponent_profile_cache}`
- All tiers: structured ActionDecl response (Pydantic-validated; reject + fallback Defend on hallucination)
- Default = Standard if not declared
- Token budget worst case (10-round boss fight): 1 boss + 3 standard friendly + 1 boss + 3 standard hostile → `(2×3500 + 6×1800) × 10 = 178k tokens` ≈ $0.18 at $1/M

**V1+ extension path:**
- V1+ `CombatPersonalityDecl` override per named NPC (extension on ChorusMetadataDecl ACT_001) — bespoke combat quirks beyond archetype
- V1+ author-configurable sliding window depth per actor (V1 default 3 rounds boss only)
- V1+30d cross-encounter NPC combat memory (boss remembers PC from previous fight)

### §14.10 — Cross-Q implications (LOCKED dependencies)

| Cross-cut | LOCK consequence |
|---|---|
| Q1 + Q3 | Party Major companion permadeath would be grief vector → Q3 KO-revivable mandatory (LOCKED) |
| Q3 + Q7 | KO duration tick = round increment; round = "all non-KO actors acted ≥1 AV pop"; engine-internal detail (LOCKED) |
| Q4 + PF_001 | NEW `combat_safety: CombatSafetyLevel` field on PlaceDecl (closure-pass-extension at COMB_001 DRAFT) |
| Q4 + WA_001 | NEW Lex axiom `combat_damage_cap_in_safe_zone` (closure-pass-extension at COMB_001 DRAFT) |
| Q3 + WA_006 | KO state via PL_006 status (no WA_006 schema change; on-expire trigger calls WA_006 Dying transition) |
| Q3 + ACT_001 | NEW `mortality_role: MortalityRole` field on CanonicalActorDecl (closure-pass-extension at COMB_001 DRAFT) |
| Q9 + ACT_001 | NEW `combat_role: CombatRoleHint` field on actor_chorus_metadata (closure-pass-extension at COMB_001 DRAFT) |
| Q6 + NPC_002 | LLM Layer 3 narration coherence constraint in combat-mode AssemblePrompt template (closure-pass-extension at COMB_001 DRAFT) |
| Q7 + PL_006 | 3 NEW PL_006 status entries (slowed/hasted/stunned with AV mutation behavior) + 1 NEW status entry (knocked_out with on-expire→Dying) — closure-pass-extension at COMB_001 DRAFT |
| Q1 + Q9 | Token budget worst case = 7 LLM calls/round (1 PC + 3 Major friendly + 1 boss hostile + 2 standard hostile + narration); 10-round boss = ~$0.18 |
| Q5 + FAC_001 | Schema pattern `Vec<Side> cap=2` mirrors FAC_001 Q2 REVISION; relax-cap V1+ activation pattern proven |
| Q8 + TDIL-A9 | Determinism inherent; replay event log derives seed; no seed storage; aligned with TDIL_001 replay determinism FREE V1 |

### §14.11 — Closure-pass-extensions surfaced (will execute at COMB_001 DRAFT)

10 cross-feature mechanical revisions required at COMB_001 DRAFT promotion (single combined `[boundaries-lock-claim+release]` commit):

1. **PROG_001 §9** — REVERSE Strike formula (LLM-proposes-damage → engine-computes-damage); promote PROG-D24 simple form to V1 4-step law chain
2. **PL_005 Strike** — drop `damage_amount` field from payload schema; engine sources damage; combat-mode intent restriction (`combat.action_invalid_in_state` reject)
3. **PL_006 Status Effects** — register 4 NEW status entries: `slowed` / `hasted` / `stunned` (AV mutations Q7) + `knocked_out` (KO on-expire→Dying Q3)
4. **NPC_002 Chorus** — add combat-mode AssemblePrompt template (3 tiers Trivial/Standard/Boss; structured ActionDecl response schema; LLM Layer 3 narration coherence constraint Q6)
5. **AIT_001** — add `minor_behavior_scripts.combat_reaction_table` extension; CombatRoleHint dispatch
6. **WA_006 Mortality** — KO-intermediate semantic via PL_006 (no schema change; doc update only)
7. **WA_001 Lex** — register NEW Lex axiom `combat_damage_cap_in_safe_zone` (Q4)
8. **PF_001 Place Foundation** — NEW field `combat_safety: CombatSafetyLevel` on PlaceDecl (Q4)
9. **ACT_001 Actor Foundation** — NEW field `mortality_role: MortalityRole` on CanonicalActorDecl (Q3) + NEW field `combat_role: CombatRoleHint` on actor_chorus_metadata (Q9)
10. **RealityManifest** — NEW fields: `combat_disparity_cap: CombatDisparityCapConfig` (Q4) + `combat_mortality_config: CombatMortalityConfig` (Q3) + `combat_seed_visible: bool` (Q8 dev-mode V1+)

### §14.12 — Original Q phrasing (Appendix; for traceability)

#### Q1 — Player party size V1
**Question:** What is the V1 cap on PC's combat party (PC + companion NPCs)?
- (A) Solo PC only · (B) PC + ≤3 companion NPCs · (C) PC + ≤5 (Pokemon party of 6 max) · (D) Author-configured per reality
- **My lean:** (B) PC + ≤3 — clean middle ground · **LOCKED:** (B+) PC + ≤3 Major + ∞ Minor

#### Q2 — Encounter mode flag
**Question:** Is combat an explicit state transition or emergent from Strike intent flow?
- (A) Explicit state machine · (B) Emergent
- **My lean:** (A) · **LOCKED:** (A) confirmed with concrete invariants

#### Q3 — Death semantics V1
**Question:** When HP=0 in combat, what happens?
- (A) Immediate WA_006 Dying · (B) KO intermediate revivable · (C) Author-configured
- **My lean:** (B) + (C) · **LOCKED:** (B+C hybrid) via PL_006 status `knocked_out`

#### Q4 — Cultivation level disparity
**Question:** When 元嬰 strikes 練氣, hard cap on damage or pure stat math?
- (A) Pure stat math · (B) Hard-cap Lex axiom · (C) Author-configured
- **My lean:** (C) · **LOCKED:** (C++) Reality + Lex + PlaceMetadata composition

#### Q5 — Multi-side combat V1
**Question:** V1 supports 2 sides or N sides?
- (A) 2 sides · (B) ≤3 sides · (C) N sides
- **My lean:** (A) · **LOCKED:** (A+) with future-proof `Vec<Side>` cap=2 schema

#### Q6 — Stat hiding
**Question:** Does PC see exact HP/SP/stat numbers?
- (A) Exact numbers · (B) Vague labels · (C) Hybrid
- **My lean:** (C) · **LOCKED:** (C++) Hybrid + 5-tier vague + LLM coherence

#### Q7 — Initiative system
**Question:** Which initiative system V1?
- (A) HSR action value · (B) DEX-ordered · (C) FFT Charge Time · (D) Persona baton-pass
- **My lean:** (A) + (D) V1+30d · **LOCKED:** (A++) HSR AV V1 + composable extensions V1+/V1+30d

#### Q8 — RNG transparency
**Question:** Combat RNG visibility / control?
- (A) Hidden · (B) Visible · (C) Allow savescum
- **My lean:** (A) · **LOCKED:** (A++) hidden + atomic encounter + action-keyed determinism

#### Q9 — AI difficulty tiers
**Question:** Major NPC LLM action selection prompt depth scale?
- (A) Single template · (B) Tiered (trivial/standard/boss) · (C) Reality-configured per NPC
- **My lean:** (B) · **LOCKED:** (B++) Tiered + IDF_003 archetype constraint + boss 3-round memory

---

## §15 — Reference materials (for deep-dive prep)

### §15.1 Module decomposition map (chaos-backend `06_Modular_Architecture.md` adoption)

Reviewed chaos-backend-service `crates/combat-core/` 2026-04-27. **Implementation maturity check:** `combat-core` crate has 0 LOC actual code (only `Cargo.toml` + empty `src/`). `effect-core` / `status-core` / `item-core` / `leveling-core` / `race-core` / `event-core` / `generator-core` similarly 0 LOC. Only `actor-core` (41,273 LOC; already PROG-D6 reference), `element-core` (16,052 LOC), and `condition-core` (13,751 LOC) have substantial implementation. **chaos-backend combat-core docs are mature design intent (~330KB across 11 files), NOT battle-tested code.** Reference docs as architectural blueprint; verify all assumptions against actual COMB_001 design phase.

**File decomposition adopted V1** (7 of chaos-backend's 12 files; skip 5 real-time/projectile-coupled):

| COMB_001 V1 file | Maps to chaos-backend | V1 responsibility | V2+ extension path |
|---|---|---|---|
| `action_definition.rs` | `combat-core/action_definition.rs` | 5 ActionDecl variants (Strike/Defend/Skill/UseItem/Flee); resource cost; cooldown stub | +Move (V2+ zone-tactics) / +Summon (V1+30d) — additive enum variants; no refactor |
| `event_trigger.rs` | `combat-core/event_trigger.rs` | Minor NPC scripted CombatTrigger conditions (OnTurnStart / OnHpThreshold / OnAllyKO); AND/OR conditional logic | +turn-phase trigger (Reaction system V1+30d COMB-D); +environmental triggers (V2+) |
| `attack_range.rs` | `combat-core/attack_range.rs` | V1 stub: 2-row Front/Back metaphor (no zone graph); melee/ranged distinction | V2+ promote to CSC_001 zone graph; AOE shapes (single/line/radius); LOS calculations |
| `damage_calculator.rs` | `combat-core/combat_calculator.rs` + `damage_system.rs` | 4-step law chain (§5.1); engine-owned (LLM-zero-math); seeded RNG | +DF7-equivalent damage law chain V1+ (PROG-D24 promotion); fills element_mult + resistance + penetration without changing chain order |
| `combat_validator.rs` | `combat-core/combat_validator.rs` | Action validity (target alive, side ownership, resource affordability, skill unlocked, item in inventory); ActionDecl LLM-hallucination rejection + fallback Defend | +reaction validity (out-of-turn V1+30d); +environmental restriction (V2+) |
| `combat_events.rs` | `combat-core/combat_events.rs` | EVT-T3 CombatRoundDelta + EVT-T4 CombatSessionBorn/Resolved + EVT-T8 Forge:CancelCombat | Additive new EVT-T sub-types; chain trigger system (chaos "Butterfly Effect") V1+30d |
| `constants.rs` | `combat-core/constants.rs` | MAX_PARTY (≤3 V1 lean Q1) / MAX_ROUNDS / MAX_SIDES (=2 V1 lean Q5) / RNG seed scheme | Bound expansion via reality config (TierCapacityCaps pattern from AIT_001) |

**Bridge modules adopted (chaos-backend "Integration Bridges" pattern from `02_Damage_System_Design.md` lines 44-49):**

| COMB_001 bridge | External system | V1 thin pass-through | V2+ extension |
|---|---|---|---|
| `prog_bridge.rs` | PROG_001 ProgressionInstance | Read strike_power/armor/speed/accuracy/dodge/crit_chance | +DF7 stats (resist_pct/penetration_pct per element) |
| `res_bridge.rs` | RES_001 vital_pool + inventory | Read HP/SP; deduct on damage/cost; consume item from inventory | +Mana V1+; +cooldown resource V1+30d |
| `status_bridge.rs` | PL_006 Status Effects | Apply/dispel/expire delegation; combat-relevant subset (bleed/stunned/defending/poisoned/rooted) | +elemental affinity statuses (Burning/Frozen/Shocked/Wet) V1+ DF7; +charm/confuse V1+30d |
| `fac_bridge.rs` | FAC_001 RelationStance | Side allegiance auto-assign at encounter start | +mid-combat defection V1+30d (COMB-D6); +multi-faction free-for-all V1+30d (COMB-D9) |
| `npc_bridge.rs` | NPC_002 Chorus + AIT_001 tier | AssemblePrompt(combat_ctx) for Major; reaction_table for Minor; bulk-resolve for Untracked | +tiered prompt depth Q9; +structured ActionDecl validation; +memory carry-over per encounter V1+ |
| `mortality_bridge.rs` | WA_006 Mortality | KO → Dying state transition (per actor + reality config) | +KO-intermediate state Q3 lock-dependent; +revival item gameplay loop V1+ |

**Skipped V1 chaos-backend files (domain mismatch — real-time bias):**
- `projectile_definition.rs` — no projectile entity in turn-based; range stat suffices V1+ for ranged attacks
- `environment_interactions.rs` — V1 abstract arena; V2+ zone-graph environmental hooks separate file when ready
- `power_level_system.rs` — chaos-backend uses for AI weight-based targeting; we use LLM (Major) + scripted (Minor); no power-level AI heuristic
- `status_definition.rs` (chaos status-as-actor pattern) — PL_006 already owns status; status-as-actor over-engineered for our context
- chaos-backend `damage_system.rs` heavy real-time variant — collapsed into `damage_calculator.rs` 4-step law chain V1

**Pre-calculated combat resources cache (chaos-backend `00_Combat_Core_Overview.md` lines 102-114 adoption):**

V1 in-memory only (NO 3-layer cache L1/L2/L3 like chaos-backend — over-engineered for turn-based encounter scope):
```rust
pub struct CachedCombatStats {
    pub actor_ref: ActorRef,
    pub power_points: f64,            // pre-summed from PROG_001 stat aggregation
    pub defense_points: f64,          // pre-summed from PROG_001 stat aggregation
    pub speed: f64,                   // for HSR action value
    pub crit_chance: f64,
    pub accuracy: f64, pub dodge: f64,
    pub contributing_systems: Vec<SystemRef>,   // for replay audit
    pub computed_at_round: u32,
    pub invalidated_by: Vec<InvalidationTrigger>,    // PL_006 status apply | HP threshold | cross-realm | manual
}
```

Cache invalidation V1:
- PL_006 status apply/expire on actor → invalidate that actor's CachedCombatStats
- HP delta crosses configured threshold (e.g., < 30%) → invalidate (some skills scale with current HP)
- Manual `Forge:RecomputeCombatStats` (admin)

V1+ optional Redis cache for high-actor-count encounters; V2 cross-encounter persistence (party between fights). Pattern is **identical to chaos-backend** — only cache layer count differs.

### §15.2 Likely deep-dive sessions
1. **Q1+Q5+Q9 batch** — encounter participants & scaling (party / multi-side / AI tiers)
2. **Q2+Q3 batch** — state machine & death semantics
3. **Q4+Q6+Q8 batch** — stat asymmetry, info hiding, replay
4. **Q7 batch** — initiative system (single deep-dive; potentially most contentious)

### §15.3 Reference game survey expansion
If user wants `01_REFERENCE_GAMES_SURVEY.md` companion:
- Pokemon Gen 1-9 (mainline) + ROM hacks (difficulty mods)
- HSR + Genshin combat (turn-based vs action-RPG comparison)
- Persona 3-5 + Royal (1-More + Baton Pass evolution)
- FF1-16 (turn-based to action-RPG transition; FF Tactics offshoot)
- FE3H + Engage (modern grid tactics polish)
- Tactics Ogre Reborn (2022 remaster; CT system)
- Slay the Spire (deck-building reference for V1+ skill draft)
- Disco Elysium (skill-check narrative for V1+30d social skirmish)
- Baldur's Gate 3 (5e tactical reference for V2+ zone graph design)
- Triangle Strategy (modern minimalist FE)

### §15.4 Reference materials for engine determinism + architecture
- `GameRand` Rust crate (deterministic PRNG with seeds)
- HSR action value system whitepaper (community-reverse-engineered)
- chaos-backend `actor-core` (41K LOC; production code) — Subsystem→Contribution stat aggregation pipeline; already referenced in PROG_001 PROG-D6
- chaos-backend `element-core` (16K LOC; production code) — element stat provider + Omni stats + elemental mastery; V1+ DF7 promotion source
- chaos-backend `condition-core` (14K LOC; production code) — 25+ status condition functions; V1+ PL_006 enrichment source
- chaos-backend `combat-core/00_Combat_Core_Overview.md` (design only; 0 LOC code) — adopted file decomposition + pre-calc resources pattern (§15.1)
- chaos-backend `combat-core/02_Damage_System_Design.md` (design only) — adopted 4-step damage composition law (§5.1) + Omni additive-only rule
- chaos-backend `combat-core/06_Modular_Architecture.md` (design only) — adopted 7/12 file decomposition (§15.1)

**chaos-backend reference discipline (red flags):**
1. **`combat-core` 0 LOC** — design intent only; no battle-tested invariants. Adopt patterns but verify each at COMB_001 DRAFT.
2. **Real-time bias** — chaos is real-time MMORPG; skip tick-based passives / network delta sync / projectile entities / 3-layer cache / weight-based AI. Already filtered V1.
3. **Cultivation tight coupling** — chaos-backend combat-core docs entangle 修煉/Jindan/灵力/thần thức/thọ nguyên directly. COMB_001 stays **cultivation-agnostic**: cultivation contributes ONLY via PROG_001 progression stat (modern reality + tu tiên reality run identical combat engine).
4. **Vietnamese terminology re-mapping** — chaos docs bilingual; map terms to LoreWeave RES_001 §2 i18n (English stable IDs + I18nBundle): linh lực ↔ stamina/mana progression V1+; thọ nguyên ↔ no V1 equivalent (V2+ AGE feature potential).

---

## §16 — Anticipated V1 acceptance criteria

(To be finalized at COMB_001 DRAFT; preview only)

- AC-COMB-1: Strike resolution determinism (same seed + same stats = same damage on replay)
- AC-COMB-2: HSR action value queue ordering correctness (speed ratios produce expected turn frequency)
- AC-COMB-3: 2-row positioning damage modifier applied
- AC-COMB-4: FAC_001-derived side allegiance auto-assignment
- AC-COMB-5: Major NPC LLM action selection structured response validation (rejects + fallback Defend on hallucinated action)
- AC-COMB-6: Minor NPC scripted reaction lookup (zero LLM call)
- AC-COMB-7: Untracked NPC bulk resolution (group HP pool; group flees)
- AC-COMB-8: KO → WA_006 Dying state transition (per reality config)
- AC-COMB-9: PL_006 status effect application during combat (e.g., bleed DoT correct)
- AC-COMB-10: A6 canon-drift detection on narration that contradicts ResolutionResult

---

## §17 — Coordination notes (anticipated; finalized at COMB_001 DRAFT)

### Closure-pass-extensions required at DRAFT commit
- **PROG_001 §9** REVERSE Strike formula (LLM-proposes → engine-computes); promote PROG-D24 simple form to V1
- **PL_005 Strike** drop `damage_amount` field from payload schema; engine sources damage
- **NPC_002 Chorus** add combat-mode AssemblePrompt template + structured ActionDecl response schema
- **PL_006 Status Effects** — V1 already engine; minor doc update for combat-relevant subset
- **AIT_001 §7** — minor_behavior_scripts.combat_reaction_table extension (V1)
- **WA_006 Mortality** — KO state intermediate (Q3 lock-dependent)
- **WA_001 Lex** — Lex axiom slot for combat anti-grief (Q4 lock-dependent)

### Boundary additions at DRAFT
- `combat.*` rule_id namespace (anticipated 8-12 V1 + 4-6 V1+30d reservations)
- `combat_session` aggregate row in 01_feature_ownership_matrix.md
- RealityManifest extensions in 02_extension_contracts.md §2: combat_config + initiative_system + side_default_setup
- COMB-* stable-ID prefix
- EVT-T4: CombatSessionBorn + CombatSessionResolved
- EVT-T3: CombatRoundDelta (initiative_queue + HP/SP changes)
- EVT-T8: Forge:CancelCombat (admin escape hatch)

### Cross-repository reference (external; non-boundary)
- **chaos-backend-service** (`D:\Works\source\chaos-repositories\chaos-backend-service\`) reviewed 2026-04-27 — adopted patterns:
  - **§5.1 Damage 4-step law chain** ← `docs/combat-core/02_Damage_System_Design.md` lines 99-117 (Damage Composition Law) + Omni additive-only rule from `docs/element-core/06_Implementation_Notes.md`
  - **§15.1 Module decomposition map (7 files V1)** ← `docs/combat-core/06_Modular_Architecture.md` (12 files; we adopt 7, skip 5 real-time-coupled)
  - **§15.1 Bridge module pattern (6 bridges)** ← `docs/combat-core/02_Damage_System_Design.md` lines 44-49 "Integration Bridges"
  - **§15.1 Pre-calculated combat resources cache** ← `docs/combat-core/00_Combat_Core_Overview.md` lines 102-114 (V1 in-memory only; skip 3-layer L1/L2/L3 cache as over-engineered)
  - **§5.3 HSR action value initiative** ← independent reference (HoYoverse Honkai Star Rail; community-RE)
- **chaos-backend impl status as of 2026-04-27** (LOC count):
  - `actor-core` 41K LOC ✅ production code (PROG-D6 reference)
  - `element-core` 16K LOC ✅ production code (V1+ DF7 promotion source)
  - `condition-core` 14K LOC ✅ production code (V1+ PL_006 enrichment source)
  - `combat-core` 0 LOC ⚠️ design docs only (~330KB across 11 docs); no code battle-tested
  - Other crates (effect/status/item/leveling/race/event/generator) 0 LOC ⚠️ design-only or stub
- **chaos-backend usage discipline** at COMB_001 DRAFT:
  - Reference docs as architectural blueprint; **do NOT assume code exists**
  - Verify each adopted pattern against COMB_001 V1 deterministic + LLM-zero-math constraints (some chaos-backend patterns are real-time-biased)
  - Stay cultivation-agnostic at COMB_001 layer (cultivation contributes via PROG_001 stat only — chaos-backend tightly couples; we decouple)
  - Re-map Vietnamese cultivation terminology to RES_001 §2 i18n English stable IDs

---

## §18 — Status

- **2026-04-27**: Concept-notes written post-TDIL_001 DRAFT closure
- **2026-04-27 (iteration 2)**: chaos-backend-service review applied — §5.1 damage 4-step law chain LOCKED + §15.1 module decomposition map (7-file V1 + 6-bridge pattern + pre-calc cache) + §17 cross-repo reference + impl maturity caveat (combat-core 0 LOC docs-only; only actor-core/element-core/condition-core have production code)
- **2026-04-27 (iteration 3)**: Q-deep-dive Q1-Q9 ALL LOCKED via 4-batch (Batch 1: Q1+Q5+Q9 / Batch 2: Q2+Q3 / Batch 3: Q4+Q6+Q8 / Batch 4: Q7); §14 fully restructured with LOCKED matrix + invariants + cross-Q dependencies + 10 closure-pass-extensions surfaced
- **Next**: COMB_001 DRAFT promotion (single combined `[boundaries-lock-claim+release]` commit) — schedule when boundary lock window opens; carries 10 closure-pass-extensions across PROG_001 / PL_005 / PL_006 / NPC_002 / AIT_001 / WA_006 / WA_001 / PF_001 / ACT_001 / RealityManifest
- **After COMB_001 DRAFT**: PCS_001 PC Substrate kickoff (consumes 6 V1 foundations + IDF + FF + FAC + REP + ACT + AIT + TDIL + PROG + COMB; full V1 vertical slice)
