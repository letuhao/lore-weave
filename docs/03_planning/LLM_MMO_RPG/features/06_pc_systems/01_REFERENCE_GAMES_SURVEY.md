# PCS_001 PC Substrate — Reference Games Survey

> **Status:** DRAFT 2026-04-27 — companion to `00_CONCEPT_NOTES.md`. Surveys reference games + literature for PC substrate patterns: identity binding, persona, mortality, multi-PC, body-soul split (xuyên không novel design). Augments user-provided references when supplied.
>
> **Method:** Cross-reference market patterns. Highlight insights for V1 scope. Identify defer-V1+/V2 patterns. xuyên không is largely UNIQUE to wuxia/xianxia narrative tradition; mainstream RPG references are sparse — wuxia novel canon is primary reference.

---

## §1 — Pattern taxonomy (5 categories)

| Pattern | Examples | V1 fit |
|---|---|---|
| **Soul-body split (xuyên không / transmigration)** | Wuxia novels (primary) / Persona series partial / RPG ghost-possession tropes | ✅ STRONG V1 (LoreWeave novel design) |
| **Single-PC reality** | Skyrim / Witcher 3 / RPG single-protagonist | ✅ V1 cap=1 |
| **Multi-PC party** | D&D 5e party / Baldur's Gate / Pathfinder: WotR / Dragon Age | ⚠ V1+ charter coauthors |
| **Mortality + Respawn** | WoW respawn / Dark Souls / Permadeath roguelikes | ✅ V1 mortality state machine |
| **PC Creation Form** | D&D character sheet / Baldur's Gate creation / WoW character creation / FFXIV | ✅ V1+ PO_001 onboarding |

---

## §2 — Wuxia / Xianxia novel canon — xuyên không (PRIMARY REFERENCE)

### Core mechanic in wuxia/xianxia literature

Xuyên không (穿越; "cross-pass / crossing-empty") = soul transmigration narrative trope. Modern person's soul finds itself in an ancient/wuxia body after sudden death (car accident, lightning strike, sleep) or unexplained event.

**Common patterns:**

| Variant | Description | LoreWeave mapping |
|---|---|---|
| **Soul-only transmigration** | Modern soul + medieval/ancient body; body's prior soul dies/displaces; body retains motor skills + native language | LeakagePolicy::SoulPrimary { body_blurts_threshold } |
| **Body-only swap** | Soul stays; body swaps to another reality's body (rare) | (V1+ deferred Reincarnation pattern) |
| **Both swap** | Both soul + body migrate (very rare) | (V1+ deferred Cross-reality migration V2+) |
| **Reincarnation** | Same soul + new infant body in same reality; gradual memory recovery | (V1+ PCS-D8 deferred) |
| **Possession** | Temporary occupation by another soul; original soul still exists | (V1+ PCS-D9 deferred) |

### Novel examples (Wuxia / Xianxia transmigration literature)

| Novel | Variant | LoreWeave V1 use case |
|---|---|---|
| **《回到明朝当王爷》** (Back to Ming Dynasty as Lord) | Soul-only; modern student → Ming nobleman | SPIKE_01 Lý Minh prototype |
| **《步步惊心》** (Bu Bu Jing Xin) | Soul-only; modern woman → Qing dynasty consort | Modern → wuxia-period soul transmigration |
| **《择天记》** (Way of Choices) | Reincarnation pattern (V1+ deferred) | (Future PCS-D8) |
| **《凡人修仙传》** (Reverend Insanity) | Cultivation novel; native PC; no xuyên không | Native PC (LeakagePolicy::NoLeakage) |

### SPIKE_01 turn 5 literacy slip (canonical reproducibility scenario)

**Lý Minh xuyên không scenario:**
- **Soul layer**: 2026 Saigon STEM student
  - knowledge_tags: ["modern_stem", "classical_chinese_reading"] (read 《Đạo Đức Kinh chú》in school)
  - native_skills: [academic, vietnamese_native, programming]
- **Body layer**: 1256 Hangzhou peasant
  - knowledge_tags: ["regional_hangzhou_dialect", "manual_labor"] (illiterate)
  - motor_skills: [farming, manual_crafts]
  - native_language: hangzhou_chinese_dialect
- **LeakagePolicy::SoulPrimary { body_blurts_threshold: 0.05 }**

**Turn 5 dialogue** (NPC Du sĩ presents text; Lý Minh quotes《Đạo Đức Kinh chú》):
- **Body cannot read** — illiterate peasant body should not recognize text
- **Soul recognizes text** — modern student soul recalls reading the book in school
- **Soul leaks knowledge through body** — Lý Minh blurts the quote
- **A6 canon-drift detector** (V1+ 05_llm_safety) reads body_memory.{soul, body}.knowledge_tags + detects body-knowledge mismatch → flags inconsistency

### Key insights for PCS_001 V1

- ✅ **PcBodyMemory schema with explicit SoulLayer + BodyLayer separation** — wuxia novel canon validates dual-layer model
- ✅ **LeakagePolicy 4-variant** matches wuxia narrative spectrum (NoLeakage native PC; SoulPrimary modern-soul-ancient-body; BodyPrimary soul-stays-body-swaps; Balanced both-mix)
- ✅ **knowledge_tags closed-set** for both layers — drives A6 canon-drift detection V1+
- ✅ **Native PC supported** via LeakagePolicy::NoLeakage (most modern + sci-fi realities; no xuyên không)
- ❌ **Reincarnation + Possession deferred V1+** (Wuxia rare V1; complex schema)

### LoreWeave novel adaptation

LoreWeave is unique in computationally modeling xuyên không as a TYPED schema instead of narrative-only. PcBodyMemory enables:
- A6 canon-drift detection (body cannot know what soul knows)
- LLM persona assembly (combine soul knowledge + body skills correctly)
- Cross-reality reference tracking (soul.origin_world_ref)
- xuyên không event flow (PcXuyenKhongCompleted with TDIL_001 clock-split)

---

## §3 — Persona series (multi-persona protagonist; PARTIAL ref)

### Core mechanic

Persona series PCs have **multiple personas** representing different aspects/social bonds. Each persona has own stats + abilities. Player switches active persona during combat.

### Key insights for PCS_001 V1

- ⚠ **Multi-persona** is NOT xuyên không — same soul, different "masks" / "facades" tied to social bonds
- ❌ Persona system is more like NPC_001 personality archetypes (IDF_003) than xuyên không body-memory
- ✅ Hint for V1+ pattern — V1+ PC could have multi-persona via secondary actor_chorus_metadata-like extension (defer)

LoreWeave V1: PC has SINGLE persona (canonical_traits + flexible_state in actor_core). Multi-persona V1+ deferred.

---

## §4 — Mass Effect Shepard (PC creation form pattern)

### Core mechanic

Mass Effect creation form:
- **Background**: Spacer / Earthborn / Colonist (3 backgrounds)
- **Class**: Soldier / Adept / Engineer / Sentinel / Vanguard / Infiltrator (6 classes)
- **Reputation**: Paragon / Renegade global axis (≠ REP_001 per-faction)
- **Appearance**: customizable face/hair/skin
- **Romance arc**: choices over 3-game arc

### Key insights for PCS_001 V1

- ❌ **Background + Class** = IDF_004 Origin + PROG_001 Progression equivalents (already covered)
- ❌ **Paragon/Renegade** = RES_001 SocialCurrency::Reputation (global scalar; per LoreWeave 3-layer separation discipline)
- ❌ **Romance arc** = V1+ ACT_001 actor_actor_opinion bilateral patterns (PC↔NPC drift over time)
- ✅ **PC creation form pattern** validates PO_001 V1+ feature need (separate folder; not PCS_001 V1 scope per Q3)

LoreWeave V1: PCS_001 V1 owns PC PRIMITIVES; PO_001 V1+ owns PC CREATION FORM UI flow.

---

## §5 — D&D 5e party (multi-PC charter coauthors V1+)

### Core mechanic

D&D party = 4-6 PCs each with own character sheet; one player + DM controls each PC (player owns 1; DM controls NPCs + temporary PC handoff). Party adventures together.

### Key insights for PCS_001 V1

- ❌ **Multi-PC party** is V1+ charter coauthors feature (not single-player V1 SPIKE_01)
- ✅ **Per-PC character sheet pattern** — each PC has own pc_user_binding (user_id + body_memory)
- ✅ **Charter coauthor pattern** = LoreWeave Q9 V1+ multi-PC reality unlock
- ✅ **DM mode** (one user controls multiple actors) — could overlap with V1+ AI-controls-PC-offline (ACT-D1) for inactive PCs

LoreWeave V1: PCS_001 cap=1 PC per reality V1; V1+ Vec<PcId> validator relax.

---

## §6 — WoW respawn pattern (mortality + respawn V1)

### Core mechanic

WoW PC dies → ghost form at graveyard → walk back to corpse OR resurrect at spirit healer (durability cost). Permanent death (Permadeath) only in special hardcore mode.

### Mortality state machine (WoW)

```
Alive → (Damage > HP) → Dying → (Death) → Ghost → (Walk to corpse OR resurrect) → Alive
                                                  → (Spirit healer) → Alive (durability cost)
```

### Key insights for PCS_001 V1

- ✅ **4-state pattern** matches PCS_001 brief §S4 (Alive / Dying / Dead / Ghost)
- ✅ **Respawn pathway** = V1+ enrichment (Q7 — V1 ships state machine; respawn flow V1+ when mortality_config defines it)
- ⚠ **WoW ghost is interactive** — PC controls ghost form; LoreWeave V1 Ghost = narrative state (NPC interactions limited)
- ❌ **Durability cost** = WoW item-decay; V1+ enrichment if needed (item degradation feature V2+)

LoreWeave V1: 4-state machine (Alive / Dying / Dead / Ghost); respawn V1+ per Q7.

---

## §7 — Permadeath genre (Dwarf Fortress / Dark Souls / Roguelikes)

### Core mechanic

Permadeath = single-life PC; death is permanent; no respawn. Roguelike (Dwarf Fortress / NetHack / Caves of Qud) common.

### Key insights for PCS_001 V1

- ✅ **WA_006 mortality_config Permadeath mode** (per WA_006 closure) maps directly to roguelike pattern
- ✅ **MortalityConfig Permadeath** = state stuck at Dead; no Respawn transition possible
- ✅ Wuxia narrative supports both Permadeath (heroic sacrifice) and Respawn (cultivator cheat death)

LoreWeave V1: WA_006 mortality_config dictates which Mortality mode; PCS_001 pc_mortality_state state machine supports both modes via Respawn V1+ activation only when config allows.

---

## §8 — CRPG character creation forms (Baldur's Gate / Pathfinder: WotR)

### Core mechanic

CRPG creation forms typically include:
- **Race / Background / Class** (combinatorial start point)
- **Stats** (point-buy or roll)
- **Skills** + **feats** (initial picks)
- **Appearance** (portrait / 3D model)
- **Backstory** (optional narrative)
- **Voice / personality dropdowns**

### Key insights for PCS_001 V1

- ✅ Race + Background + Class → IDF_001 + IDF_004 + (V1+ class system) covered
- ✅ Stats → PROG_001 actor_progression covered (V1 stub via Forge admin)
- ✅ Appearance / portrait → V1+ UI feature (not V1 PCS_001 scope)
- ✅ Voice / personality → IDF_003 personality + ACT_001 voice_register covered
- ✅ PC creation form spec → PO_001 V1+ feature

LoreWeave V1: PCS_001 owns PC PRIMITIVES (PcId + pc_user_binding + body_memory + pc_mortality_state); PO_001 V1+ owns CRPG-style PC creation form UI.

---

## §9 — Diablo / Path of Exile (single-PC roguelite)

### Core mechanic

PC = single character; multiple "characters" per account possible (each is separate PC in own playthrough). Solo / co-op modes; Hardcore mode = Permadeath.

### Key insights for PCS_001 V1

- ⚠ **Multi-character per account** ≠ Multi-PC per reality. In Diablo, each character has own playthrough/world; not co-op multi-PC in same world.
- ✅ **Hardcore = Permadeath** matches WA_006 mortality_config V1
- ❌ Multi-character account pattern = LoreWeave V1+ multi-reality user (each user can have N realities; each reality V1 cap=1 PC)

LoreWeave V1: One user, N realities, cap=1 PC per reality; user can switch between realities (each separate PC) — matches Diablo multi-character pattern indirectly.

---

## §10 — FFXIV (MMO multi-character + multi-realm)

### Core mechanic

FFXIV PCs = single user account, multiple characters across multiple realms (servers). Each character = separate world identity. Cross-realm party V1+ via Crystal Tower / Duty Finder.

### Key insights for PCS_001 V1

- ⚠ Cross-realm = LoreWeave cross-reality V2+ Heresy (per Q8 LOCKED universal discipline)
- ✅ **Realm = Reality** mapping; PCS_001 V1 strict per-reality
- ✅ Multi-realm account pattern = user has accounts; each reality has 1 PC; V1+ cross-reality via Heresy

LoreWeave V1: Single reality strict; V2+ Heresy permits PC migration via WA_002.

---

## §11 — Comparison table (10 dimensions)

| Game / Source | Soul-body split | Multi-PC | Respawn | PC creation form | V1 fit |
|---|---|---|---|---|---|
| **Wuxia novels** (primary) | ✓ (xuyên không novel design) | ✗ | ⚠ (cultivator cheat death narrative) | ✗ | ★★★★★ V1 anchor |
| **Persona** | ⚠ (multi-persona NOT xuyên không) | ✗ | ✗ | minimal | ★★ partial ref |
| **Mass Effect** | ✗ | ✗ (Shepard solo) | ✗ (loadout reload) | ✓ rich form | ★★★ creation form ref |
| **D&D 5e** | ✗ | ✓ party of 4-6 | ⚠ (Resurrection spell) | ✓ rich form | ★★★ multi-PC V1+ ref |
| **WoW** | ✗ | ✗ (single PC) | ✓ ghost + spirit healer | ✓ form | ★★★★ mortality 4-state ref |
| **Dark Souls** | ✗ | ✗ | ✓ (bonfire respawn) | minimal | ★★ Permadeath alt |
| **Roguelikes (DF/NetHack)** | ✗ | ✗ | ✗ Permadeath | minimal | ★★★ Permadeath ref |
| **Baldur's Gate** | ✗ | ✓ party | ⚠ (rest restore) | ✓ rich form | ★★★ creation form |
| **Pathfinder: WotR** | ✗ | ✓ party | ⚠ | ✓ rich form | ★★★ creation form |
| **Diablo** | ✗ | ✗ (multi-char per account) | ✗ Permadeath in HC mode | ✓ form | ★★ HC ref |
| **FFXIV** | ✗ | ✗ (multi-char per account) | ✓ respawn | ✓ rich form | ★★★ multi-realm V2+ ref |
| **Skyrim** | ⚠ (Sheogorath body-snatch trope) | ✗ | ✓ load-save | ✓ form | ★★ body-swap minor ref |

PCS_001 V1 = Wuxia transmigration novel canon (primary anchor) + WoW mortality 4-state + WA_006 mortality_config Permadeath/Respawn mode + (V1+ PO_001 CRPG-style creation form).

---

## §12 — Recommendations summary (feeds Q1-Q10 §4 of CONCEPT_NOTES)

| Question | Recommendation | Reference anchor |
|---|---|---|
| Q1 PcId newtype | (A) Uuid; mirror NpcId | NpcId pattern; DP-A12 module-private constructor |
| Q2 pc_user_binding shape | (A) Single aggregate V1 | FAC_001 simple aggregate pattern |
| Q3 PC creation pathway | (C) Both V1 — canonical seed + runtime login binding | D&D party + WoW pattern + LoreWeave SPIKE_01 Lý Minh canonical |
| Q4 pc_stats_v1_stub | (B) Defer V1+ — PROG_001 supersedes | PROG_001 DRAFT note SUPERSEDED |
| Q5 body_memory full V1 schema | (A) Full per brief §S3 | Wuxia novel canon (xuyên không primary) |
| Q6 LeakagePolicy 4-variant | (A) Full 4-variant V1 | SPIKE_01 Lý Minh = SoulPrimary; brief §S3 designed |
| Q7 pc_mortality_state 4-state | (A) Full Alive/Dying/Dead/Ghost | WoW mortality + Wuxia ghost narrative |
| Q8 cross-reality V1 | (A) V1 strict; V2+ Heresy | Universal discipline (IDF + FF + FAC + REP + ACT) |
| Q9 multi-PC reality cap=1 V1 | (C) Vec + cap=1 validator V1 | FAC_001 Q2 REVISION pattern; future-proof |
| Q10 xuyên không clock-split | (A) PcXuyenKhongCompleted EVT-T1 → TDIL_001 actor_clocks consume | TDIL_001 §10 clock-split contract |

All 10 recommendations align with established discipline + market patterns + Wuxia novel canon. Q-deep-dive may revise.

---

## §13 — Status

- **Created:** 2026-04-27 by main session (commit 1/4 this turn)
- **Phase:** REFERENCE — companion to `00_CONCEPT_NOTES.md`
- **Coverage:** 10 game references + Wuxia novel canon + 12-dimension comparison table
- **Augmentation slot:** awaits user-provided references if any
- **Next action:** Feed §12 recommendations into Q-deep-dive discussion → user "approve" (or revisions) → §7 V1 scope LOCKED in CONCEPT_NOTES → DRAFT promotion
