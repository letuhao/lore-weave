# QST — Quest System V2 Reservation

> **Status:** RESERVED 2026-04-26 — V2 deferred. No design here. Captures namespace reservation + V1 hooks + V2 scope sketch + V1 sandbox alternatives.
>
> **DO NOT design quest system in this file.** When V2 begins, create `QST_001_quest_foundation.md` per pattern of foundation tier features (EF_001 / PF_001 / etc.).

---

## §1 — What quest system is

Player-facing **goal-tracking system**: author or LLM declares an objective, PC actions advance it, completion triggers rewards. Distinct from freeplay sandbox by giving structured direction.

V2 scope (high-level): Quest aggregate + objective state machine + reward declarations + branching paths + multi-step persistence + quest log UX + fail/abandon states + multi-PC group quests.

---

## §2 — Why V2 deferred (not V1)

- **V1 ships RPG foundation tier 5/5** — substrate for trade/combat/dialogue/movement is enough to play
- **Full quest = HUGE feature** — Quest aggregate + state machine + reward triggers + UX + persistence = comparable to PL_001 Continuum scope (~700 lines)
- **V1 alternatives exist** (see §5 below) — light scaffolding can solve "sandbox feels empty" concern without full quest system
- **LLM-driven narrative** — without explicit quest system, LLM can drive emergent stories from NPC goals + reactions if NPCs have direction (see §5 Path A)

---

## §3 — Existing V1 hooks already reserved

Quest system has anchors waiting in V1-locked features:

| Hook | Owner | Reserved as |
|---|---|---|
| `Scheduled:QuestTrigger` | 07_event_model EVT-T5 Generated | "future quest-engine owns" — quest precondition met (calibration / turn / event match) |
| `QuestOutcome` | 07_event_model EVT-T1 Submitted (sub-type) | "future quest-engine owns" — quest completion / failure |
| `Scheduled:QuestAdvance` | 07_event_model EVT-T3 Derived | mentioned in retirement section — quest state advance |
| `interaction.intent_unsupported` | PL_005 §9 reject path | quest-related intent rejection until V2 unblocks |

These hooks mean the event model already knows about quests; QST_001 implementation slots in cleanly without 07_event_model rework.

---

## §4 — V2 scope sketch (no design — bullets only)

When V2 design begins, expect these concerns:

- **Quest aggregate** (T2/Reality scope; per-(reality, quest_id) row)
- **Objective state machine** — Pending → Active → Completed | Failed | Abandoned
- **Reward declarations** — RES_001 ResourceBalance grants (currency/items/SocialCurrency reputation) on completion
- **Quest givers** — NPC declares quest via dialogue or trigger; references NPC_001 ActorId
- **Branching / choice** — author-scripted decision points; LLM-mediated alternative paths
- **Persistence** — quest state survives session reconnect; resumable on travel/sleep
- **Multi-step quests** — N objectives, sequenced or parallel, gating
- **Quest log UX** — player-facing list of active quests + objectives + status
- **Fail conditions** — time expiry / wrong action / NPC death / world-state change
- **Group quests** (multi-PC) — V2+; depends on DF5 Session/Group Chat
- **Radiant quests** (procedurally generated) — V2+; LLM-templated repeat objectives
- **Canonization** — quest outcomes promotable to L2 canon per NAR_004 (V3)

---

## §5 — V1 sandbox-mitigation alternatives (NOT quest system)

User raised "game giống sandbox, chả có gì để làm" concern 2026-04-26. Quest system is V2; but V1 can address direction-feel via lighter mechanisms:

### Path A — NPC desires LIGHT (RECOMMENDED V1)
**~150 lines extension to NPC_001 Cast.** Each NPC author-declares 1-3 desires:
```rust
pub struct NpcDesire {
    pub kind: I18nBundle,         // "expand my tavern" / "find my missing brother"
    pub intensity: u8,            // 1-10; affects how often NPC brings up in dialogue
    pub satisfied: bool,          // toggled by author Forge / LLM-mediated event
}
```
LLM persona prompt assembles desires → NPCs naturally reveal goals in dialogue → PCs can choose to help/oppose. Emergent quest-feel without quest system. NO state machine; NO objective tracking; NO rewards. Just "NPCs want things, talk about them."

### Path B — Reality scenario seed (V1+30d)
**~50 lines extension to RealityManifest.** Author declares opening situation:
```rust
pub struct RealityScenario {
    pub premise: I18nBundle,      // "Town X under bandit threat. PC arrives day 1."
    pub starting_beats: Vec<I18nBundle>,  // narrative anchors for first session
}
```
LLM uses scenario as prompt context. PCs feel like they entered a real world with stakes.

### Path C — Author-scripted beats via WA_003 Forge (V1)
Author manually triggers events ("Day 7: bandits arrive at town gate") via existing AdminAction sub-shape. No new feature; just author-tooling pattern. Limited scale (manual trigger per beat).

**Recommended V1 path:** **Path A (NPC desires LIGHT)** — best ROI for solving sandbox feel without quest system.

---

## §6 — Cross-folder relationships when V2 designs

| Touched folder | Concern |
|---|---|
| `05_npc_systems/` (NPC_001) | Quest givers reference NpcId; NPC desires LIGHT (Path A) is natural precursor |
| `04_play_loop/` (PL_005) | Quest objective triggers consume PL_005 InteractionKinds (Speak/Strike/Give/Examine/Use) |
| `00_resource/` (RES_001) | Quest rewards = ResourceBalance grants; reputation rewards via SocialCurrency |
| `08_narrative_canon/` (NAR) | Quest outcomes canonizable to L2 per NAR_004 (V3) |
| `07_social/` (SOC) | Group quests multi-PC V2+; depends on DF5 |
| `06_pc_systems/` (PCS_001) | PC quest log per-PC; quest progress in pc_state |
| `02_world_authoring/` (WA_003 Forge) | Author UI for declaring quests + objectives |
| `12_daily_life/` (DF1) | Quest fixtures may interact with NPC routines |

---

## §7 — Reference games for V2 design

When V2 starts, survey these for patterns:

- **Crusader Kings 3** — schemes (long-term covert objectives with risk + time)
- **Europa Universalis 4** — missions (faction-tier objectives with rewards)
- **Witcher 3** — main + side + contract quests (branching narrative)
- **Skyrim** — radiant quests (procedural objectives)
- **WoW / FFXIV** — quest log + objective UX (player-facing)
- **Dwarf Fortress** — rumors-as-quests (emergent goals from world state)
- **Mount & Blade Bannerlord** — kingdom missions (faction-tier quests for vassals)
- **RimWorld** — events as quests (storyteller-driven; quest = event with choice)

---

## §8 — Boundary lines (when V2 designs)

QST will OWN:
- `Quest` aggregate + state machine
- `QuestObjective` shape + sequencing
- `QuestReward` declarations
- `QuestGiver` association (references NpcId)
- `quest.*` RejectReason namespace
- Quest log UX

QST will NOT own (these stay where they are):
- NPC desires (NPC_001 — Path A handles this V1)
- Resource rewards (RES_001 ResourceBalance)
- Canon enforcement (NAR — quest outcomes may canonize but enforcement is NAR's)
- Action triggers (PL_005 InteractionKind)
- Faction-tier quests (V3 — depends on `15_organization/` ORG)

---

## §9 — Promotion checklist (when V2 design begins)

1. Read NPC_001 (post-Path-A extension, if Path A shipped V1)
2. Read RES_001 §15.2 V2 Economy module (overlap concerns)
3. Survey reference games §7
4. Claim `_boundaries/_LOCK.md`
5. Create `catalog/cat_13_QST_quests.md` (namespace registration)
6. Update `_boundaries/01_feature_ownership_matrix.md` Stable-ID prefix ownership row to add `QST-*`
7. Update `_boundaries/02_extension_contracts.md` §1.4 to add `quest.*` rule_id namespace
8. Promote this file → QST_001_quest_foundation.md DRAFT (~600-800 lines)
9. Update this folder's `_index.md` to reflect DRAFT status
10. Release lock + commit `[boundaries-lock-claim+release]`

---

## §10 — DO NOT design here

Explicit prohibitions for this file:
- ❌ NO Rust struct definitions for Quest aggregate
- ❌ NO state machine diagrams
- ❌ NO RejectReason rule_ids (defer to QST_001 DRAFT)
- ❌ NO acceptance criteria (defer to QST_001 DRAFT)
- ❌ NO RealityManifest extensions (defer to QST_001 DRAFT)

This is a RESERVATION + SCOPE SKETCH document. V2 design lives in `QST_001_quest_foundation.md` when V2 begins.
