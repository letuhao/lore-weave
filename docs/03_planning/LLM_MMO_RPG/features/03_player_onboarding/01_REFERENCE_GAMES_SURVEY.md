# PO_001 Player Onboarding — Reference Games Survey

> **Status:** DRAFT 2026-04-27 — Phase 0 reference materials capture; informs Q-deep-dive batched decisions.
> **Companion docs:** [`_index.md`](_index.md) (folder index) + [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (concept brainstorm + Q1-Q10) + [`wireframes/`](wireframes/) (FE-first HTML mockup)
> **Methodology:** Surveyed 9 popular contemporary RPGs/MMOs/text-adventure platforms during wireframes Phase 0 (commits 19855a5b + 4c4fd6d7); identified anchor patterns + LoreWeave-specific applications. This document formalizes findings as PO_001 design references.

---

## §1 — Anchor pattern (locked V1)

**"BG3 Origin/Custom dual-mode + Disco Elysium amnesia framing + AI Dungeon custom prompt freedom"**

Validated against 9 reference games. 3 V1 onboarding modes:
- **Mode A** — Canonical PC (BG3 Origin Character pattern)
- **Mode B** — Custom PC (BG3 Custom + Cyberpunk lifepath; 3-level UX progression: Basic Wizard → Advanced Settings → AI Assistant)
- **Mode C** — Xuyên Không Arrival (Disco Elysium amnesia + wuxia transmigration; LoreWeave-unique)

---

## §2 — Game-by-game survey (9 systems)

### §2.1 Baldur's Gate 3 (BG3) — PRIMARY ANCHOR

**Genre:** AAA single-player RPG (2023; D&D 5e ruleset)
**Why primary:** BG3's Origin Character vs Custom dual-mode is the gold standard for narrative-rich + creative-freedom hybrid onboarding. Most popular RPG of 2023 (Game of the Year).

**Onboarding flow:**
1. Origin selection — Custom OR Origin Character (Astarion / Karlach / Lae'zel / Shadowheart / Wyll / Gale / Dark Urge)
2. Race + Subrace (11 races × 31 subraces)
3. Class (12 classes; some unlock subclass at level 3)
4. Background (Acolyte / Criminal / Sage / Soldier / etc. — narrative + skill proficiencies; no stat boost)
5. Skills selection (proficiency picks based on race/background/class)
6. Ability Scores (27-point buy with Recommended preset button)
7. Appearance customization (extensive — body type / face / skin / hair / tattoos / voice)

**What we KEEP for PO_001 V1:**
- ✅ **Dual-mode (Canonical PC vs Custom PC)** — directly matches Mode A vs Mode B
- ✅ **Origin Character preset** — narrative-rich; appeals to new users; reduces decision fatigue
- ✅ **Recommended/Default button** — M7 progressive disclosure CTA "Skip → use defaults" in Mode B
- ✅ **Race + body type LOCKED post-creation** — matches PCS_001 body_memory immutable post-bootstrap
- ✅ **Background = narrative + minor mechanical** — IDF_004 origin pack with default_ideology + native_language presets
- ✅ **Tutorial post-creation** — Nautiloid escape; LoreWeave V1 inline tooltips minimal (Q10) + V1+30d richer overlay

**What we DEFER:**
- ❌ Extensive visual sliders (V2+; LoreWeave V1 text-only physical description)
- ❌ Full point-buy stat allocation (PROG_001 per-reality kinds; not standard 6-attribute system)
- ❌ Class respec (V1+ via Forge admin; PROG_001 supports adjustment)

### §2.2 Cyberpunk 2077

**Genre:** Open-world action RPG (2020/2023 Phantom Liberty)
**Why surveyed:** Lifepath system — narrative branching with no mechanical advantage. Directly maps to LoreWeave's IDF_004 origin pack pattern.

**Onboarding flow:**
1. Difficulty selection
2. Life Path (Nomad / Streetkid / Corpo) — branches first ~30 minutes of game
3. Character creation (face / body / voice / pronouns / nudity)
4. Attributes (7 points across Body / Intelligence / Reflexes / Technical / Cool; Recommended button)
5. Tutorial integrated into life path opening chapter

**What we KEEP for PO_001 V1:**
- ✅ **Lifepath = narrative-only branching** — IDF_004 origin pack (Đông Hải coastal village vs Imperial capital vs Northwest frontier) provides narrative variation without mechanical advantage
- ✅ **Recommended attributes preset** — M7 default values per origin pack
- ✅ **Tutorial baked into opening chapter** — Mode C xuyên không "wake up amnesiac" doubles as tutorial via LLM-narrated discovery

**What we DEFER:**
- ❌ Visual character sliders (V2+; LoreWeave text-driven)
- ❌ Locked-in attribute commitment V1+ (PROG_001 supports respec via Forge admin)

### §2.3 Disco Elysium

**Genre:** Narrative-heavy detective RPG (2019; Final Cut 2021)
**Why surveyed:** Amnesia framing — character built through play, not creation. Direct inspiration for Mode C Xuyên Không Arrival.

**Onboarding flow:**
1. 4 archetype templates (Thinker / Sensitive / Physical / Custom point distribution) — sets narrative tone
2. Character wakes up amnesiac with no recollection of identity
3. Roleplay-driven character build through dialogue choices, skill checks, "thoughts" cabinet
4. Identity + skills emerge gradually through gameplay

**What we KEEP for PO_001 V1:**
- ✅ **Amnesia framing** — perfect match for wuxia xuyên không trope; LoreWeave Mode C uses PCS_001 PcBodyMemory SoulLayer + BodyLayer + LeakagePolicy for "soul carries memory; body inherits muscle memory; player discovers what's still there"
- ✅ **Predetermined backstory + emergent identity** — Mode C uses canonical body (host_body_ref) + soul (origin_world_ref); player rediscovers via gameplay
- ✅ **Minimal explicit character creation** — Mode C is 5 steps minimum; LLM-narrated reveal Step 5
- ✅ **Archetype templates as starting point** — IDF_003 12 personality archetypes serve same role
- ✅ **Dramatic narrative onboarding** — Mode C "wake up in body of recently deceased disciple" is dramatic hook

**What we DEFER:**
- ❌ "Thoughts cabinet" UI for skill emergence (V2+; complex narrative-mechanical loop)
- ❌ Skill checks as identity reveal mechanic (V2+; integrates with PROG_001 skill checks runtime)

### §2.4 AI Dungeon

**Genre:** AI-powered text adventure platform (2019)
**Why surveyed:** Custom prompt freedom — players write their own scenarios. Direct inspiration for AI Character Assistant.

**Onboarding flow:**
1. Pick pre-made prompt OR write custom prompt
2. Direct text input — AI generates story on the fly
3. No fixed plot or outcome; player drives narrative

**What we KEEP for PO_001 V1:**
- ✅ **Custom prompt freedom** — AI Character Assistant (06_ai_assistant.html) lets user describe character in natural language; AI suggests structured field values
- ✅ **AI-driven narrative** — chat-service + LiteLLM provides LLM backbone; LoreWeave matches AI-driven approach
- ✅ **No fixed plot** — Mode B + Mode C onboarding doesn't lock player into specific story; emergent narrative via gameplay

**What we DEFER:**
- ❌ Pure unstructured text input (LoreWeave V1 needs structured field assignment for backend cascade)
- ❌ "Continue" action without world model (LoreWeave has rich Tier 5 substrate; not pure text generation)

### §2.5 NovelAI

**Genre:** AI-powered storytelling platform for writers (2021)
**Why surveyed:** Writer-focused mode + Lorebook for worldbuilding. Reference for AI Assistant constraint awareness.

**Onboarding flow:**
1. Story creation
2. Prompt + Lorebook (named entities, places, events with descriptions)
3. Text Adventure mode (caret-based commands)

**What we KEEP for PO_001 V1:**
- ✅ **Lorebook = constraint awareness** — AI Character Assistant reads RealityManifest declarations (races/factions/titles/progression_kinds/places) as constraints; only suggests valid values
- ✅ **Custom prompt as starting point** — natural-language input that AI elaborates

**What we DEFER:**
- ❌ Caret-based command system (LoreWeave uses 5-action grammar Speak/Action/MetaCommand/FastForward/Narration via PL_002)

### §2.6 Final Fantasy XIV

**Genre:** MMORPG (2010 → 2023 Endwalker)
**Why surveyed:** Class fluidity — one character can change classes in-game. Reference for LoreWeave's per-reality progression flexibility.

**Onboarding flow:**
1. New Character button
2. Race (8 races × 2 clans each)
3. Class (10 starting classes; can change in-game)
4. Appearance customization (extensive sliders)
5. Name + free trial / paid sub

**What we KEEP for PO_001 V1:**
- ✅ **Race + Class separation** — IDF_001 race + PROG_001 progression_kinds are independent
- ✅ **Class fluidity in-game** — PROG_001 supports respec via Forge admin; user can pivot cultivation method via Forge:GrantProgression

**What we DEFER:**
- ❌ Extensive visual sliders (V2+ visual portrait feature)
- ❌ Free trial + paid sub model (LoreWeave platform business model V1+ separate concern)

### §2.7 Lost Ark

**Genre:** MMO action RPG (2018 KR / 2022 EN)
**Why surveyed:** Class-first onboarding — class defines identity more than race in action MMORPGs.

**Onboarding flow:**
1. Class (Warrior / Mage / Martial Artist / Gunner / Assassin) → advanced subclass
2. Appearance customization (extensive)
3. Name

**What we KEEP for PO_001 V1:**
- ✅ **Class-first Q1 LOCKED rejected** — LoreWeave V1 picks REALITY first (which determines available races/classes/factions), then mode (Canonical/Custom/XuyenKhong), then class-equivalent (faction membership in Mode B Step 5)
- ✅ **Subclass concept** — Could map to FAC_001 role within faction (e.g., Faction = "Đông Hải Đạo Cốc" + Role = "nội môn đệ tử" / "ngoại môn đệ tử" / "trưởng lão")

**What we DEFER:**
- ❌ Class-locked progression (LoreWeave PROG_001 supports flexibility via Forge admin)

### §2.8 Pathfinder: Wrath of the Righteous

**Genre:** Deep CRPG (2021; Pathfinder 1e ruleset)
**Why surveyed:** Extreme depth in character customization — niche power-user onboarding pattern.

**Onboarding flow:**
1. Mythic Path (V1+) preview
2. Race + Heritage (subraces)
3. Class (25 classes + multiclass system)
4. Skills + Feats (extensive build complexity)
5. Spells (for casters)
6. Mythic origin
7. Background
8. Appearance

**What we KEEP for PO_001 V1:**
- ✅ **Power-user mode** — Advanced Settings (03b2_advanced.html) caters to BG3/Pathfinder-style power users; Basic Wizard caters to mainstream

**What we DEFER:**
- ❌ Multiclass system (LoreWeave PROG_001 supports multi-progression via per-reality declared kinds; not class-restricted)
- ❌ Extreme build complexity V1 (overwhelming for new users; AI Assistant covers complexity via natural language)

### §2.9 Persona series (Persona 5 Royal / Strikers)

**Genre:** JRPG with social simulation (2017+)
**Why surveyed:** Cinematic intro — character is fixed; player drives social bonds.

**Onboarding flow:**
1. Cinematic intro (no character creation)
2. Character is fixed (Joker for P5)
3. Tutorial integrated into Day 1 of game (school day)
4. Player customizes via SP/SL system (social bonds + persona fusion)

**What we KEEP for PO_001 V1:**
- ✅ **Mode A canonical PC** — equivalent to Persona's fixed protagonist; pre-written narrative
- ✅ **Cinematic intro** — Mode C Xuyên Không Step 5 LLM-narrated reveal serves same purpose
- ✅ **Customization through play** — LoreWeave PROG_001 + ACT_001 flexible_state evolves via gameplay (turn-by-turn)

**What we DEFER:**
- ❌ No character creation V1 (LoreWeave needs creation for Custom PC + Xuyên Không modes)

---

## §3 — Cross-genre patterns identified

### Pattern 1: Dual-mode onboarding (preset vs custom)

Validated by: BG3, Cyberpunk lifepaths, Persona fixed protagonist, AI Dungeon prompts, Disco Elysium templates.

LoreWeave application: **Mode A Canonical PC vs Mode B Custom PC** — directly matches BG3.

### Pattern 2: Lifepath/Background as narrative-only

Validated by: Cyberpunk lifepaths, BG3 backgrounds, FFXIV race lore.

LoreWeave application: **IDF_004 origin pack** — provides defaults (language, ideology, birthplace) without mechanical advantage. Confirmed current design.

### Pattern 3: Recommended defaults (M7 progressive disclosure)

Validated by: BG3 Recommended button, Cyberpunk default attribute distribution.

LoreWeave application: **Mode B "Skip → use defaults" CTA** — origin pack defaults; new users bypass advanced customization.

### Pattern 4: Amnesia / discovery trope

Validated by: Disco Elysium primary; many JRPGs.

LoreWeave application: **Mode C Xuyên Không Arrival** — perfect match for wuxia transmigration; PCS_001 SoulLayer + BodyLayer + LeakagePolicy already supports this architecturally.

### Pattern 5: Reality-first vs class-first

Validated by: FFXIV (race-first), Lost Ark (class-first), BG3 (race-first D&D tradition).

LoreWeave application: **Reality-first** — pick reality at landing (determines available races/classes/factions/titles), then mode, then character. This matches LoreWeave's per-reality declaration discipline (PROG-A1 + REP_001 + FAC_001 + ...).

### Pattern 6: Locked-in vs respec-able

Validated by: BG3 (race + body locked; class respec V1+), Cyberpunk (locked V1; respec 1.5+), FFXIV (class fluid; race locked).

LoreWeave application: **PCS_001 body_memory immutable post-bootstrap** (matches BG3 lock pattern) + **PROG_001 progression respec via Forge admin** (matches FFXIV class fluidity).

### Pattern 7: Tutorial integration

Validated by: BG3 Nautiloid escape, Cyberpunk lifepath opening, Disco Elysium amnesia, Persona Day 1.

LoreWeave application: **SR11 first turn UX visible from turn 1** + **Mode C amnesia framing doubles as tutorial** + V1 inline tooltips minimal + V1+30d richer overlay.

### Pattern 8: AI-driven natural language input

Validated by: AI Dungeon (custom prompt), NovelAI (story prompts + Lorebook).

LoreWeave application: **AI Character Assistant** — natural-language input → structured field suggestions via chat-service; constraint-aware via knowledge-service; iterative tweak; 6 quick actions.

### Pattern 9: Extensive visual customization

Validated by: FFXIV, Lost Ark, Black Desert Online, BG3.

LoreWeave application: **DEFER V2+** — text-driven novel-RPG V1; visual portrait generation feature V2+ via AI image generation (image-gen service deferred).

---

## §4 — Anchor pattern for PO_001 V1

Synthesizing all 9 references:

**LoreWeave PO_001 V1 = BG3 dual-mode + Disco Elysium amnesia + AI Dungeon freedom hybrid**

3 V1 modes:
- **Mode A** Canonical PC — BG3 Origin Character pattern
- **Mode B** Custom PC — BG3 Custom + Cyberpunk lifepath + Pathfinder depth (3-level UX: Basic Wizard / Advanced Settings / AI Assistant)
- **Mode C** Xuyên Không Arrival — Disco Elysium amnesia + wuxia transmigration (LoreWeave-unique)

V1 visual style:
- Wuxia ink-wash + reality-themed dynamic accent (paper cream / ink black / jade green wuxia base; per-reality skin)
- Typography: Source Serif Pro (headings) + Inter (body) — Vietnamese-friendly serif
- Component base: shadcn/ui-compatible (matches frontend Vite + React + Tailwind + shadcn convention)
- Desktop V1 primary; mobile V1+30d responsive

V1 backend integration:
- chat-service (Python/FastAPI) — AI Assistant LLM via LiteLLM
- auth-service (Go/Chi) — email + password account creation; JWT issuance
- world-service (Go/Chi) — Forge:RegisterPc + Forge:BindPcUser cascade
- knowledge-service (Python/FastAPI) — RealityManifest constraint awareness for AI

**Out of V1 scope (per references):**
- ❌ Extensive visual sliders (BG3/FFXIV/Lost Ark style) — V2+ visual portrait feature
- ❌ OAuth (Google/Discord) — V1+ (PO-D1) when auth-service ships OAuth
- ❌ Multi-PC roster — V1+ when PCS-D3 cap relaxed
- ❌ Mobile-first responsive — V1+30d (PO-D4)
- ❌ Reality switcher mid-session — V2+ (PO-D5)
- ❌ Auto-save per step + draft resume — V1+30d (PO-D3)
- ❌ Richer tutorial overlay — V1+30d (PO-D10)
- ❌ Class-locked progression (Lost Ark style) — LoreWeave per-reality flexibility via PROG_001
- ❌ Multiclass system (Pathfinder style) — LoreWeave multi-progression via PROG_001 per-reality kinds

---

## §5 — Cross-references

- [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) — concept brainstorm + Q1-Q10 critical questions
- [`_index.md`](_index.md) — folder index
- [`wireframes/index.html`](wireframes/index.html) — FE-first HTML mockup navigation hub
- [`wireframes/ACTOR_SETTINGS_AUDIT.md`](wireframes/ACTOR_SETTINGS_AUDIT.md) — 46 V1 actor settings × 14 features comprehensive inventory
- `features/00_pc_systems/01_REFERENCE_GAMES_SURVEY.md` — PCS_001 reference survey (xuyên không + body memory pattern lifted to Mode C)
- `features/00_titles/01_REFERENCE_GAMES_SURVEY.md` — TIT_001 reference survey (BG3 origin pattern adjacent to PO_001 Mode A)
