# SPIKE_02 — Reference Games Gap Analysis

> **Status:** DRAFT 2026-04-27 — exploratory cross-category survey. NOT a design doc; NO IDs claimed; NO catalog rows added. Future discussion to triage which gaps graduate to V1+30d / V2 / V3 features.
>
> **Scope:** Survey popular RPG/strategy/simulation/adventure games (offline + online), compare against current `LLM_MMO_RPG/` catalog (474 features across 12 categories + foundation tier 6/6 + AIT + TDIL), surface missing features grouped by domain, propose tiered backlog.
>
> **Graduation path:** Items here are CANDIDATES for future feature design. When user picks a gap to act on, it graduates to:
> - Category subfolder (e.g., `features/05_npc_systems/NPC_NNN_<name>.md`) for category-fit features
> - New `features/NN_<category>/` subfolder + `cat_NN_*.md` if a new category emerges (e.g., `WTH` weather)
> - `DF/DF<NN>_<name>/` if becomes a Big Deferred Feature
> - Stays here as permanent reference if rejected or perpetually deferred
>
> **NOT in scope:** Implementation. Final V-tier assignment. ID minting. Boundary-changes. This file is reading material for future planning conversation.

**Active:** (empty — no agent currently editing)

---

## §1 — Why this spike exists

User asked 2026-04-27:

> "tôi muốn bạn tham khảo các game phổ biến thể loại rpg/strategy/simulating/adventure bao gồm offline/online xem nó có các tính năng gì mà chúng ta đang thiếu để lên brief danh sách các tính năng sẽ implement trong tương lai"

The catalog (474 features) is comprehensive on **substrate** — actor/place/resource/progression/reputation/AI-tier/time-dilation foundation tier is closed 6/6 + architecture-scale features (AIT/TDIL) cover billion-NPC scaling and multi-realm cultivation rate. But the catalog was built bottom-up from **kernel necessity** (what must exist for events to work, for canon to be safe, for LLM I/O to be defended). It has not been audited top-down against **player-facing genre expectations**.

This spike does the top-down pass. Method:
1. Pick reference games covering 6 genre buckets (MMO, single-player RPG, strategy, simulation, sandbox/survival, narrative/adventure)
2. For each, list distinguishing features
3. Compare against catalog + reservations (QST V2 / CFT V2 / ORG V3)
4. Output: gap list grouped by domain (A..N)
5. Output: tiered backlog (V1+30d / V2 / V3 / V4+)

Output is a brief — discussion seeds, not commitment.

---

## §2 — Reference games surveyed

### MMO
- **WoW** — quests, dungeons, raids, talents, professions, AH, mailbox, guild bank, transmog, mounts, achievements, world bosses, world PvP, battlegrounds, arenas, dailies, reputations
- **FFXIV** — housing, retainers, gardening, chocobo raising, gathering nodes, fishing, treasure maps, deep dungeons, eureka, palace of the dead, beast tribes, glamour, levequests, fates, hunts
- **ESO** — skill morphs, antiquities, champion points, alliance war, dungeons, decorating
- **GW2** — dynamic events, hearts, world bosses, jumping puzzles, mastery, fractals, raids, WvW, mount mastery
- **BDO** — knowledge system, lifeskills, node empire, contribution points, AFK farming, sailing
- **Lost Ark** — expedition, life skills, sailing, islands, cards
- **Genshin Impact** — elemental reactions, exploration puzzles, world bosses, daily commissions, weekly bosses, gacha banner, characters as resources
- **Albion / EVE** — full-loot PvP, territory control, GvG / sovereignty, manufacturing, market, corp politics, espionage, mining

### Single-player RPG
- **Skyrim / Bethesda** — open world, perks, lockpicking, alchemy, enchanting, sneak/stealth, follower companions, dragon shouts, persuasion/intimidation, mod support
- **Witcher 3** — branching dialogues, choice-and-consequence, witcher senses (investigation), Gwent mini-game, monster hunting contracts, journal, rumors, side quests, multiple endings
- **Baldur's Gate 3** — turn-based combat, party of 4, action economy, rest mechanic (long/short rest), camping, romance, reactivity logging, narrator voiceover, DM-style descriptions
- **Disco Elysium** — skill-based dialogue, internal monologue, thought cabinet, dialogue success/failure rolls, archetypes
- **Persona 5** — calendar simulation, social links, time-based event scheduling, dungeon crawling, day/night phases
- **Mass Effect** — morality/paragon-renegade, codex, war assets
- **Divinity Original Sin 2** — elemental interactions, environmental simulation, source points, multiplayer co-op
- **Pillars of Eternity** — reputation-with-factions, resting at inns, journal phylacteries, custom party

### Strategy / Sim
- **Crusader Kings 3** — dynasty, traits, lifestyle (lifetime perks), schemes, intrigue, marriage, succession, religion, culture, councilors, heir pressure, stress/dread, lovers, rivals
- **EU4 / Vic3** — trade routes, mercantilism, technology, government reforms, monarch points, estates, pop modeling
- **Civilization** — great people, wonders, eureka, religion, espionage, science/culture/domination victory
- **Stellaris** — empire ethics, federations, megastructures, espionage, archaeology, anomalies
- **Total War** — campaign + battles, agents, diplomacy, recruitment, settlements
- **RimWorld** — needs (food/sleep/joy), mood, traits, social interactions, mental breaks, raids, ideoligion, prison
- **Dwarf Fortress** — emergent stories, fortress mode, adventure mode, legends, world generation, engravings
- **Sims 4** — needs, traits, aspirations, careers, relationships, build mode, life stages, deaths, romance arcs
- **Stardew Valley** — farming, fishing, mining, foraging, friendship hearts, marriage, kids, festivals, Junimos, community center bundles, museum
- **Mount & Blade Bannerlord** — kingdom management, claim throne, lord vassals, smithing, tournaments, marriage, troop trees
- **Banished / Anno** — production chains, supply chain, resource flow, settlement growth
- **Frostpunk** — laws, hope, discontent, expedition

### Sandbox / Survival
- **Minecraft** — building, redstone, biomes, mobs, exploration, end/nether
- **Terraria** — bosses, classes, hardmode, NPCs moving in
- **Valheim** — building, vikings, bosses, biomes
- **ARK** — taming, breeding, tribes, territories
- **Don't Starve** — hunger, sanity, seasons
- **Animal Crossing** — villager relationships, fishing tournament, holidays, mail letters, terraforming

### Narrative / Adventure
- **Telltale** — choice & consequence with telegraphed memory ("X will remember this")
- **Detroit / Quantic Dream** — branching narrative, flowchart post-game
- **80 Days** — dynamic narrative based on routes
- **AI Dungeon / NovelAI** — free-form narrative, world memory, story cards, multiplayer scenarios

### LLM-roleplay specific (already surveyed in `References/SillyTavern_Feature_Comparison.md`)
- **SillyTavern** — character cards, lorebooks, group chats, swipes, bookmarks, macros, slash-commands, presets/prompt manager, tool calling, reasoning, image gen, TTS, plugins

---

## §3 — Catalog baseline (what we already cover well)

Quick recap of what's in `LLM_MMO_RPG/catalog/` so the gap analysis is honest about what's NOT a gap:

| Domain | Status | Files |
|---|---|---|
| **Substrate (foundation 6/6 + 2 architecture-scale)** | ✅ Complete | EF + PF + MAP + CSC + RES + PROG + ACT + REP + AIT + TDIL |
| **Infrastructure (350 IF features)** | ✅ Comprehensive | `cat_01_IF_*.md` — auth, network, observability, secrets, schema, deploy, SLO, incident, runbook, supply chain |
| **World authoring (WA)** | ✅ V1 | `cat_02_WA_*.md` |
| **Player onboarding (PO)** | 🟡 Thin | `cat_03_PO_*.md` — mostly placeholders |
| **Play loop (PL)** | ✅ V1 | sessions, turns, oracle, intent classifier, prompt assembly, voice mode, 5-layer injection defense, quest scaffold (Q-1..Q-9 with V1 author-authored only) |
| **NPC systems** | ✅ V1 | persona, R8 memory split, retrieval, mood, tool-calling, NPC desires LIGHT (NPC-12 V1) |
| **PC systems (PCS)** | ✅ V1 | stats, inventory, hide, death (DF7 V1-blocking) |
| **Social (SOC)** | 🟡 Limited | sessions only; **explicitly rejects** parties (SOC-6) and global chat (SOC-7) |
| **Narrative / Canon (NAR)** | ✅ V1-V3 | 4-layer canon model, canonization flow, IP attribution |
| **Emergent (EM)** | ✅ V1-V4 | reality fork, freeze/archive, world travel V4 (DF6), vanish-mystery V3 (DF14) |
| **Cross-cutting (CC)** | ✅ V1 | a11y, i18n, QA tiers, drift dashboard |
| **Daily life (DL = DF1)** | 🟡 V3 | sim tick (V1 frozen / V2 lazy / V3 scheduled); NPC routines V3 |
| **Quests (QST)** | 📦 V2 reserved | namespace + V1 hooks; V1 mitigation = NPC desires LIGHT |
| **Crafting (CFT)** | 📦 V2 reserved | namespace; depends on RES Item-unique kind V1+30d |
| **Organization (ORG)** | 📦 V3 reserved | namespace; factions/sects/guilds; depends on RES Strategy module V3 |
| **AI Tier (AIT)** | ✅ V1 DRAFT | 3-tier NPC architecture for billion-NPC scaling (Major/Minor/Untracked) |
| **Time Dilation (TDIL)** | 🟡 CONCEPT | 4-clock model + Convention B time_flow_rate; awaits Q-deep-dive |

This is **substantial** — the catalog has substrate covered to a degree most games never spec out (event-sourcing + canon + multi-realm time + billion-NPC tiering). The gaps below are all in the **player-facing surface area**, not the engine.

---

## §4 — Gaps by domain

### A. RPG depth — lifestyle / build / tactical
| # | Gap | Reference | Notes |
|---|---|---|---|
| A1 | Lifestyle / lifetime perk system | CK3 lifestyle, BG3 backgrounds | Long-term character growth surviving sessions; PROG covers attributes/skills/stages but not "this PC's life identity." |
| A2 | Talent tree / archetype build | WoW talents, Diablo, POE | PROG-A2 deliberately rejects central level; talent tree fills the "build identity" need without level. |
| A3 | Status-effect lifecycle | All RPGs | PL_006 V1 has temporary status (Drunk/Wounded). Full system = stack/duration/source/dispel/immunity is missing. |
| A4 | Tactical combat (initiative, action economy, AoE, positioning) | BG3, DOS2, XCOM | PROG-A6 hybrid combat is damage-formula only; turn-based tactical layer absent. Open question: does LLM-mediated turn even need it? |
| A5 | Stealth / perception / detection | Skyrim, MGS, Disco | Line-of-sight, sneak, awareness — neither PL nor NPC has this. |
| A6 | Non-combat skill checks (lockpick / persuasion / pickpocket / tracking) | Skyrim, BG3, DE | PROG has skills but no UX/protocol for "make a check." |
| A7 | Resting / camping / time-skip | BG3 long/short rest | Recover resources via fast-forward fiction-time. RES has vital_pool but no recovery protocol beyond fiction-tick. |
| A8 | Encumbrance / carry weight | Skyrim, Bannerlord | PCS-2 has inventory but no constraints. |

### B. Player Identity & Customization
| # | Gap | Reference |
|---|---|---|
| B1 | Character appearance customization (face/body/hair/clothing) | All RPGs |
| B2 | Multi-PC / alts per user | WoW, FFXIV |
| B3 | Fashion / glamour / transmog (visual ≠ stat layer) | FFXIV glamour, WoW transmog |
| B4 | Title / banner cosmetic | WoW, FFXIV |
| B5 | Portrait / avatar / voice | All |
| B6 | Backstory builder (origin packs) | BG3 backgrounds, Pillars origin |
| B7 | Account-level meta-progression (achievements xuyên PC) | All MMOs |

### C. World Simulation
| # | Gap | Reference |
|---|---|---|
| C1 | Weather system | Most | Affects gameplay/mood/encounters |
| C2 | Day/night gameplay effect | Persona 5, Skyrim | Time-of-day NPC behavior; TDIL has 4-clock substrate ready |
| C3 | Seasons / calendar | Stardew, Persona 5 | Spring/summer/autumn/winter; festivals |
| C4 | Economy supply/demand simulation | Vic3, Anno, EVE | Per-region price; market events; RES ready but UX absent |
| C5 | NPC needs simulation (hunger/sleep/joy/social) | RimWorld, Sims | DL-5 ticks NPCs but doesn't simulate needs |
| C6 | Population dynamics (births/deaths/migration/lineage) | CK3, Vic3 | FF_001 covers family but not population flow |
| C7 | Disaster / world events (raid / plague / festival) | RimWorld, GW2 dynamic events | Event hook missing |
| C8 | NPC visible schedules (vendor 9-5, guard rotation) | Skyrim, FFXIV | DL V2 lazy-when-visited reserved but UX absent |

### D. Travel & Exploration
| # | Gap | Reference |
|---|---|---|
| D1 | Fast travel UX | Skyrim, Bannerlord | TDIL substrate ready; UX missing |
| D2 | Mounts / pets / vehicles | All MMOs | Transport modifier; mounted combat V3+ |
| D3 | Travel encounters (random event between cells) | Bannerlord, FFXIV fates | MAP traversal hook |
| D4 | Cartography / fog-of-war / discovery rewards | All open-world | First-explored bonus |
| D5 | Dungeons / instances framework | All MMOs | Bounded area + boss + loot rules |
| D6 | Treasure maps / archeology | ESO antiquities, FFXIV maps | Mini-quest pattern |
| D7 | Environmental puzzles | Genshin, Witcher | Author-authored puzzle scaffold |
| D8 | Mini-games (Gwent / fishing / gambling / racing) | Witcher, Stardew | Framework + N games |

### E. Social Depth
| # | Gap | Reference |
|---|---|---|
| E1 | Marriage / family / dynasty (succession + heir) | CK3, Stardew | FF_001 covers family substrate; dynasty mechanics deeper |
| E2 | Mentorship / apprenticeship (师徒) | Wuxia core trope | FAC_001 covers via master_actor_id; UX/ritual missing |
| E3 | Gift-giving affection | Stardew, Persona | REP delta via item — protocol missing |
| E4 | Faction-tier reputation (separate from per-NPC) | WoW reps, Pillars | REP_001 already covers |
| E5 | Player-to-player trade | All MMOs | DF5 hint; explicit protocol missing |
| E6 | Mail / async messaging | WoW mailbox | Offline communication |
| E7 | Player events / festivals | GW2, Animal Crossing | Group-organized world event |
| E8 | Romance arcs with milestones | BG3, Persona, Stardew | Beyond reputation; explicit dating mechanics |
| E9 | **Reconsider parties / guilds / clans** (SOC-6 rejected) | All MMOs | Framing as "MMO" creates expectation; sessions ≠ persistent guild |

### F. Crafting & Economy (V2 reserved — needs expand)
| # | Gap | Reference |
|---|---|---|
| F1 | Gathering professions (mining/herbalism/fishing/hunting/foraging) | WoW, Stardew, BDO | CFT depends on RES Material V1; gathering hook absent |
| F2 | Production chain visualization (UI) | Anno, Factorio | RES design ready; UI missing |
| F3 | Cooking / alchemy with experimentation | Skyrim, Genshin | Sub-genre crafting |
| F4 | Construction / building (PC builds structures) | Sims, Minecraft, Valheim | Beyond housing — modular block system |
| F5 | Quality tiers (rough / fine / masterwork) | DF, BDO | RES Item-unique V1+30d |
| F6 | Enchantment / socket / upgrade | Skyrim, D3 | Stat infusion layer |

### G. Property & Permanent Footprint (entirely missing)
| # | Gap | Reference |
|---|---|---|
| G1 | Housing / property ownership (PC owns place + decorate) | FFXIV housing, Stardew farm | EF + PF substrate ready |
| G2 | Land claim | Albion, ARK | Territory marking |
| G3 | Base building / territory | Valheim, ARK | Persistent footprint outside cell |
| G4 | Furniture & decoration | FFXIV, Animal Crossing | Cosmetic placement |
| G5 | Personal storage / vault / garden | All | Off-PC inventory |

### H. Strategy / Sim Layer (V3 ORG = scratch)
| # | Gap | Reference |
|---|---|---|
| H1 | Empire / territory management UI | CK3, EU4 | UI for ORG faction treasury |
| H2 | Tech / research tree per reality | Civ, Stellaris | Author-declared progression beyond PROG |
| H3 | Tax / treasury simulation | CK3, EU4 | RES-D23 V3 |
| H4 | Diplomacy actions (treaty/alliance/declaration) | All grand strategy | Faction-faction protocol |
| H5 | Espionage / spy | CK3 schemes, Stellaris | Hidden-action genre |
| H6 | Trade routes (caravan/ship) | EU4, Anno | Multi-cell goods flow |
| H7 | War / large-scale conflict resolution | Total War, Bannerlord | Beyond PvP duel |

### I. Adventure / Narrative tools
| # | Gap | Reference |
|---|---|---|
| I1 | Achievement / title system | All | Account-level meta + RP flair |
| I2 | Lore codex / journal / library (in-game wiki) | ME codex, ESO lorebooks | knowledge-service generates data; UX consumer absent |
| I3 | Collectible system (books / notes / recordings) | Skyrim flavor | Discoverable lore items |
| I4 | Discovery rewards (first-explored bonus) | All open-world | Cartography hook |
| I5 | Flowchart / branch viewer (review past choices) | Detroit | Player-facing canon timeline |

### J. Cultivation / Wuxia / Xianxia depth (user-specific genre)
| # | Gap | Reference |
|---|---|---|
| J1 | Tribulation / heaven trial (天劫) at certain stages | Tiên Nghịch, all xianxia | Extends PROG-7 breakthrough; cataclysmic event |
| J2 | Spirit beasts / 灵宠 companion | All xianxia | Bond with monster as companion (overlaps D2) |
| J3 | Inheritance items (师门传承 — old master's manual / divine items) | All xianxia | Quest-rewarded knowledge transfer |
| J4 | Dual cultivation / 双修 | Many xianxia | Paired training mechanic |
| J5 | Pill / elixir consumables | All xianxia | RES Material likely covers; needs explicit kind |
| J6 | Sect / 门派 ritual (sect entry / expulsion / rank advance) | All wuxia | FAC_001 base ready; ritual mechanics absent |
| J7 | 走火入魔 (cultivation deviation on failed breakthrough) | Tiên Nghịch, all xianxia | ✅ Already PROG-D2 V1+30d |

### K. Live-service / Longevity
| # | Gap | Reference |
|---|---|---|
| K1 | Daily login rewards | All free-to-play | Habit-formation |
| K2 | Seasons / battle pass | Genshin, Lost Ark | Rotating content |
| K3 | Time-limited events (Halloween / Lunar New Year) | All MMOs | Calendar bind |
| K4 | Dailies / weekly resets | All MMOs | Bounded engagement loop |
| K5 | Leaderboards / rankings | All MMOs | Competitive meta |
| K6 | NG+ replayability | Many RPGs | Character carry-over to fresh reality |

### L. AI-native opportunities (LoreWeave's unique advantage)
| # | Gap | Reference |
|---|---|---|
| L1 | Director / DM mode (player authors scene live) | AI Dungeon | Player tự generate beat |
| L2 | Multiplayer DM mode (1 = DM, others = players) | Tabletop, Foundry VTT | AI-native opportunity |
| L3 | LLM director — global narrative arc tracking | None — novel | Pacing oversight; could prevent "sandbox feels empty" |
| L4 | Subgenre presets (wuxia / xianxia / scifi / modern bundle) | None — novel | Author-onboarding scaffolding |
| L5 | NPC-NPC emergent gossip when PC absent | RimWorld social, Sims | NPC-8 V3 partial; explicit gossip propagation absent |
| L6 | Auto-generated wiki / lore codex (consumer of knowledge-service) | None — novel | Data ready; consumer absent |
| L7 | Per-turn image generation (SD/ComfyUI) | SillyTavern, NovelAI | Immersion 10× |
| L8 | Voice / TTS output + STT input | SillyTavern | Accessibility + immersion |
| L9 | Vision-model image input (player describes scene via photo) | SillyTavern caption | World-building shortcut |

### M. UX / Quality-of-life
| # | Gap | Reference |
|---|---|---|
| M1 | Search / filter past events (find a turn) | All chat tools | Event log read UX |
| M2 | Bookmark NPC / place to dashboard | All MMOs | Quick access surface |
| M3 | Notifications when world event happens | All MMOs | Push surface |
| M4 | Mobile companion app (out-of-session passive) | FFXIV, Genshin | Habit-formation |
| M5 | Tutorial wizard (first-time experience) | All games | PO mỏng |
| M6 | Contextual help / tips | All games | Discover game systems |

### N. Persistence / Modding
| # | Gap | Reference |
|---|---|---|
| N1 | Mod / extension framework | SillyTavern plugins, Skyrim mods | Community content longevity |
| N2 | Marketplace / asset store | FAB, Workshop | Author monetization |
| N3 | Permadeath rule mode (opt-in hardcore) | Diablo, POE | Self-imposed challenge |
| N4 | Co-op narrative editing (multi-author per book) | Wikis | Collaborative authoring |

---

## §5 — Brief proposed backlog (tiered)

> **Disclaimer:** Tier guesses below are heuristic — final tier depends on dependency analysis (which V1 substrate it consumes) + scope estimate + user priority. ALL items here need user triage before catalog claim.

### V1+30d (fast-follow after V1 ship — low risk, high value)
| Theme | Proposed scope | Domain | Why fast-follow |
|---|---|---|---|
| Backstory builder | 4-6 origin presets per reality genre; bonuses on PC create | B6 | BG3 pattern; reuses PROG + RES start grants; fixes PO mỏng |
| Subgenre presets | wuxia / xianxia / scifi / modern RealityManifest bundle | L4 | Reality Scenario seed (Path B 13_quests §5) already reserved |
| Achievement / title | account-level meta + per-PC milestones | I1, B4 | LTV + retention; reuses event sourcing |
| Day/night gameplay effect | time-of-day NPC behavior gating | C2 | TDIL substrate ready; cheap layer on top |
| NPC visible schedules | vendor 9-5; UX surface for DL V2 lazy | C8 | Reuses DL_001 sim tick |
| Status-effect lifecycle | stack/duration/source/dispel for PL_006 | A3 | Combat depth missing; small scope |
| Encumbrance | weight cap on PCS inventory | A8 | RES inventory_cap likely already supports |

### V2 (substantial — same tier as QST/CFT)
| Proposed feature | Domain | Why V2 |
|---|---|---|
| Weather + Seasons foundation (per-cell weather/season clock) | C1, C3 | Enables CFT gathering windows + DL needs + festival hook |
| Mounts/pets/companions (follower system separate from session) | D2, J2 | RPG genre core; reuses ACT_001 substrate |
| Property/housing (PC owns Place + decorate + storage) | G1, G4, G5 | FFXIV/Stardew retention; reuses PF + EF |
| Marriage/family/dynasty (CK3 + 师徒) | E1, E2, J6 | Wuxia core (sect 师徒); reuses FF_001 + FAC_001 |
| Stealth/perception/detection (line-of-sight, sneak, awareness) | A5 | RPG depth; integrates with combat formula |
| Mini-game framework (fishing/gambling/board/racing) | D8 | Witcher/Stardew loops — 1 framework, N games |
| Per-turn image generation (SD/ComfyUI integration) | L7 | SillyTavern parity; immersion 10× |
| Voice/TTS output + STT input | L8 | SillyTavern parity; a11y boost |
| Auto-generated lore codex (knowledge-service consumer) | I2, L6 | Data ready; UX absent |
| Romance arcs with milestones | E8 | Beyond reputation; dating mechanic |
| Gift-giving affection protocol | E3 | REP delta via item; small scope |
| Player-to-player trade protocol | E5 | DF5 hint formalized |
| Travel encounters (random event between cells) | D3 | MAP_001 traversal hook |
| Achievement / title system (full) | I1, B4 | If V1+30d slim version doesn't ship |
| Treasure maps / archeology mini-quest | D6 | Mini-quest pattern atop MAP + EF |

### V3 (strategic / long-tail)
| Proposed feature | Domain | Why V3 |
|---|---|---|
| Economy supply/demand simulation (per-region pricing, market events) | C4 | Vic3/Anno layer; needed for ORG treasury |
| Faction war/diplomacy/treaty (large-scale on top of ORG) | H4, H7 | Completes ORG V3 reservation |
| Tech/research tree per reality (Civ/Stellaris) | H2 | Author-declared progression beyond PROG |
| Dungeons/instances framework (bounded area + boss + loot) | D5 | MMO core; needs FAC + QST |
| World events/festivals/disasters (cell raid / plague / Lunar NY) | C7, K3, E7 | Live-service hook + emergent narrative |
| Tribulation / 天劫 (PROG breakthrough heaven trial) | J1 | Wuxia core; extends PROG-7 |
| Multiplayer DM mode (1 player = DM) | L2 | AI-native differentiator |
| Mod/extension framework (SillyTavern plugin spec) | N1 | Community longevity |
| Espionage / spy schemes | H5 | CK3 hidden-action genre |
| Trade routes (caravan/ship multi-cell goods flow) | H6 | Anno/EU4 layer; needs ECON |
| LLM director — global narrative arc tracking | L3 | Pacing oversight |
| Population dynamics (births/migration beyond family) | C6 | CK3/Vic3 pop modeling |

### V4+ (vision / paired with EM-8 World Travel)
| Proposed feature | Domain | Why V4 |
|---|---|---|
| Territory/empire management UI | H1 | Needs ECON + WAR + ORG done |
| Author asset/content marketplace | N2 | PLT business; needs IP + tax done |
| Mobile companion app (offline passive interaction) | M4 | Habit; needs streaming infra mature |
| Co-op narrative editing | N4 | Multi-author conflict resolution non-trivial |
| Inheritance items (师门传承) cross-reality | J3 | Needs world travel DF6 |

---

## §6 — Discussion seeds (open questions for future)

1. **Genre framing.** RES survey already established LoreWeave is "simulation/strategy with RPG core, not pure RPG" (RES `01_REFERENCE_GAMES_SURVEY.md` §1). Does that framing extend to user-facing positioning? E.g., should V1 marketing emphasize "play inside your novel" (RPG framing) vs "simulate your world" (strategy framing)? Choice affects which V2 priorities the table should pull forward.

2. **Reconsider SOC-6 / SOC-7 rejection.** The catalog explicitly rejects parties (PC-D1) and global chat (PC-D3). Rejection rationale: "sessions replace parties." But the player-facing expectation for "MMO" includes persistent guilds. Two options:
   - Keep rejection; reframe product as "shared narrative platform" not "MMO RPG"
   - Revisit at V3 when ORG ships; allow guild-shaped sessions distinct from session-as-scene
   - Note: gap E9 lists this as a real gap. User decision needed.

3. **AI-native vs genre-parity.** L1..L9 are unique opportunities (no other product can offer them at this depth). C1..C8, D1..D8, E1..E9 are genre-parity (every MMO has them). Resource priority: balance "do the unique stuff well" vs "match player expectations for the genre." V2 table above leans 70% genre-parity / 30% AI-native; want to flip that?

4. **Live-service tier (K1..K6).** All tied to retention/business model. PLT track owns this. Should K-features be pulled into PLT design, or stay in the gameplay catalog? Currently scattered.

5. **Mod framework (N1) timing.** SillyTavern's plugin success suggests modding is a force multiplier. But platform-mode (`103_PLATFORM_MODE_PLAN.md`) tier policy may conflict with "anyone can add code." Decision: gated marketplace (PLT) vs unrestricted mods (N1) vs both?

6. **Wuxia/xianxia bundle as a single feature.** J1..J7 are tightly coupled (all consume cultivation system). Could ship as one DF (e.g., `DF_WUXIA_BUNDLE`) instead of N small features. Aligns with PROG_001 cultivation framing.

7. **Crafting / gathering / production chain unbundling.** F1 (gathering) + F2 (production chain UI) + F3 (cooking) + F4 (construction) + F5 (quality) + F6 (enchantment) is currently bundled into `CFT V2`. That bundle is too large. Should split into:
   - CFT_001 — recipe + skill check + tool requirement (V2)
   - CFT_002 — gathering profession (V2)
   - CFT_003 — production chain visualization (V3)
   - CFT_004 — quality + enchantment (V3)

   Decision: when CFT_001 design begins, scope cut accordingly.

8. **Day/night & weather as one foundation feature.** C1 (weather) + C2 (day/night) + C3 (seasons) all share the "per-cell time-bound state" pattern. Could unify into `WTH_001 Weather + Calendar Foundation` (V2). Alternatively: TDIL extends to cover this. Need to decide ownership.

9. **Property / housing (G1..G5) as foundation tier.** Property is consumed by economy (rent, tax), social (visiting, hosting), longevity (decoration, persistence). Smells like a foundation-tier feature similar to EF/PF. Promote to foundation tier when designed?

---

## §7 — Recommended next moves (when this resumes)

In order of low-friction first:

1. **Triage V1+30d table** — pick 2-3 items (suggest: backstory builder + subgenre presets + achievement) to graduate to category subfolders BEFORE V1 ship. These are slot-reservations: agreed scope before V1 prevents schema migration debt.
2. **Decide question 2 (SOC-6/SOC-7 reconsideration)** — affects E5/E6/E9 + ORG V3 design.
3. **Decide question 7 (CFT unbundle)** — informs CFT_001 design when V2 begins.
4. **Decide question 8 (WTH ownership)** — TDIL extension vs new foundation feature; affects boundary contracts.
5. **Open question 1 (genre framing)** — shapes V2 priority order; should be discussed before any V2 design starts.

Items 1-4 are mechanical and can be triaged in one session; item 5 is strategic and may want its own dedicated discussion.

---

## §8 — File hygiene

- **Author:** main session (this conversation, 2026-04-27)
- **Locks:** none claimed; this file is exploratory and does NOT touch boundary files / catalog / ownership matrix
- **Catalog impact:** zero — no IDs claimed, no rows added
- **Tests / verification:** none required (research artifact)
- **Graduation triggers:** when user picks a gap to act on, that item migrates per §1 graduation path. This file remains as permanent reference per `_spikes/_index.md` policy.

---

## §9 — References

- `LLM_MMO_RPG/catalog/_index.md` + all `cat_*.md` files (474 features baseline)
- `LLM_MMO_RPG/features/00_resource/01_REFERENCE_GAMES_SURVEY.md` (precedent for genre-survey methodology — feature-specific scope)
- `LLM_MMO_RPG/features/13_quests/00_V2_RESERVATION.md` §5 (V1 sandbox-mitigation alternatives — Path A NPC desires LIGHT shipped as NPC-12)
- `LLM_MMO_RPG/features/14_crafting/00_V2_RESERVATION.md` (CFT V2 reservation)
- `LLM_MMO_RPG/features/15_organization/00_V2_RESERVATION.md` (ORG V3 reservation)
- `LLM_MMO_RPG/features/16_ai_tier/AIT_001_ai_tier_foundation.md` (billion-NPC scaling)
- `LLM_MMO_RPG/features/17_time_dilation/00_CONCEPT_NOTES.md` (4-clock multi-realm time)
- `docs/03_planning/References/SillyTavern_Feature_Comparison.md` (LLM-roleplay prior art)
- `docs/03_planning/103_PLATFORM_MODE_PLAN.md` (PLT business tier — relevant for K* live-service items)
