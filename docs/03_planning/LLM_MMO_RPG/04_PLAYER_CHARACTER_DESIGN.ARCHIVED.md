# 04 — Player Character Design

> **Status:** Exploratory — locks fundamental PC semantics. Multiple "big features" identified here are deferred to their own design docs (see §9).
> **Created:** 2026-04-23
> **Prerequisites:** [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md), [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md)

---

## 1. Three-layer identity model (locked)

```
┌────────────────────────────────────────────────────────┐
│  USER  (auth_users)                                    │
│  1 tài khoản thật; 1 user exists across all realities  │
└─────────────────┬──────────────────────────────────────┘
                  │ owns 1..N
                  ▼
┌────────────────────────────────────────────────────────┐
│  PC  (player_characters, reality-scoped)               │
│  1 user có N PCs, mỗi PC thuộc 1 reality duy nhất      │
│  Identity = (user_id, reality_id, pc_id)               │
└─────────────────┬──────────────────────────────────────┘
                  │ controls via
                  ▼
┌────────────────────────────────────────────────────────┐
│  SESSION  (in-memory + event-sourced)                  │
│  1 phiên chơi — user logged-in as PC, realtime active  │
└────────────────────────────────────────────────────────┘
```

Hard rules:
- PC thuộc về đúng 1 reality (until future world-travel feature)
- PC chết/archived ≠ user bị xóa. User owns many PCs.
- Session không persist; events do. Session là runtime abstraction.

## 2. PC vs NPC (locked)

Key principle: **LLM KHÔNG đóng vai PC khi user đang online.** PC's voice = user's voice, literally.

| Aspect | PC (player-active) | PC-as-NPC (player-offline) | NPC (native) |
|---|---|---|---|
| Controlled by | User (type/click) | LLM | LLM |
| Persona source | User's input only — no LLM persona layer | Derived from PC history (see §4) | Glossary entity |
| Canonical in book? | No (L3 reality-local) | No (still L3) | Yes (L2 seeded) |
| Session participation | Active input | Passive, LLM-mediated | LLM-mediated |
| Prompt assembly | PC's state as **context** for NPCs; no PC persona prompt | Full NPC persona prompt derived from PC's recorded behavior | Full NPC persona prompt |

This distinction is critical: PC prompt templates **do not contain** "you are playing Alice with personality X." The LLM is never pretending to be the PC while the player is there. The player IS the PC.

## 3. Creation (locked)

### 3.1 A-PC1 — Full custom + templates

User creates a PC with full authorship:
- **Fully custom**: name, appearance description, backstory, starting attributes
- **Template-assisted**: system offers templates (archetype: "warrior", "scholar", "rogue" — loose guidelines, not rigid classes) that user can start from and modify

Templates are **hints, not classes**. No class system, no skill trees.

### 3.2 A-PC2 — Can play AS existing glossary characters

User may choose to play as a named character from the book's glossary (e.g., "I want to play as Alice"). This is first-class supported:

- PC's `name`, `appearance`, `backstory` can be copied from a glossary entity
- PC stores `derived_from_glossary_entity_id` as optional reference
- The glossary-authored facts become the PC's L2-seeded starting point
- During play, PC can diverge freely from canonical Alice behavior

**Consequence for NPC proxies**: if PC plays as Alice in reality R, then the canonical Alice NPC **is not spawned** in R. Only one Alice per reality — the PC's Alice. If PC later abandons → PC-as-NPC inherits Alice's canonical persona + PC's recorded history (see §4).

### 3.3 A-PC3 — No canon validation at creation (paradox-accepting)

User can create a PC that contradicts canon:
- PC with magic in a no-magic reality
- Human PC in elves-only reality
- Alice-as-PC who is "actually a dragon"

These contradictions are **accepted** by the system. Rationale:
- Reduces friction for creation
- Enables narrative paradox / "what-if" play styles
- Makes world-travel feature easier (traveler may carry paradoxical traits)
- World rules enforcement (if desired per reality) is a separate feature (see §9)

No validation ≠ no consequences — L1 enforcement at *runtime* may still reject paradoxical actions inside canon-strict realities. That's the **World Rule feature** (deferred).

## 4. Lifecycle (locked)

PC lifecycle spans active play, offline, and eventual "NPC-ification":

```
        user login as PC                      user logout
USER ────────────────────► [ACTIVE PC] ─────────────────────► [OFFLINE PC]
                                │                                   │
                                │ in-world death (event)            │ hidden by user
                                ▼                                   │
                          [DEAD PC]                                  ▼
                          (reality-dependent                   [HIDDEN PC]
                           semantics)                               │
                                                                    │ time passes
                                                                    │ without user return
                                                                    ▼
                                                            [PC-AS-NPC]
                                                            (LLM takes over,
                                                             leaves hiding spot,
                                                             lives as NPC)
```

### 4.1 B-PC1 — Death is reality-dependent

Death is just an event (`pc.died`). What happens after is **per-reality world rule**:

| Reality's rule | Effect |
|---|---|
| Permadeath reality | PC status = 'dead' permanently, user must create new PC |
| Respawn reality | After T seconds, PC status → 'alive' at respawn point |
| Body-persists reality | PC body remains as lootable object; new PC must be created |
| Resurrect-by-ritual reality | Other PCs/NPCs can restore |

World Rule feature (deferred) decides which applies. Default V1: permadeath (simplest).

### 4.2 B-PC2 — Offline PC defaults to vulnerable

When user logs out, PC remains in world with status = 'offline':
- **Visible to other PCs/NPCs in the region**
- **Can be attacked/affected by others** (potential bad outcomes)
- **LLM does not act on behalf of offline PC** (it just stands there)

User is strongly encouraged to **HIDE** their PC before logout:
- Travel PC to a "safe hub" region
- Use `/hide` command (equivalent to stashing away)
- Hidden PC is invisible to world actions, unattackable

### 4.3 B-PC3 — Prolonged absence → PC-as-NPC conversion

If PC remains hidden for too long (threshold TBC, config), system converts PC to NPC-mode:
- LLM generates a persona from PC's history (and glossary derivation if any)
- PC leaves hiding spot, joins regular NPC population
- PC's state becomes subject to world's NPC simulation rules (Daily Life feature, deferred)
- If user returns, they can "reclaim" their PC → LLM yields control back

**Important**: PC-as-NPC is still L3, still the user's creation. Canon identity preserved. Just control hand-off.

Details of NPC-ification persona generation, thresholds, reclaim UX → **Daily Life feature** (deferred, §9).

## 5. Identity & Agency (locked)

### 5.1 C-PC1 — Max 5 PCs per user (configurable)

```
config: roleplay.pc.max_per_user = 5
```

Total PCs across all realities, not per-reality:
- 1 user × 5 PCs total
- Can distribute as wanted: 5 PCs in 5 realities, or 3 in R1 + 2 in R2, etc.
- Additional slots available via purchase (platform-mode feature, **deferred**)

### 5.2 C-PC2 — PC personality = user (when active); LLM-generated (when NPC)

This is the key identity rule:
- **While player controls PC**: no LLM persona layer for the PC. User's input drives everything. Other NPCs respond to the user's text as if responding to the PC.
- **When PC transitions to NPC mode** (see §4.3): LLM gets a persona, generated from:
  - PC's backstory + description
  - PC's event history (what they did, said)
  - Glossary derivation if any (A-PC2)
  - Reality's current context

The LLM **never** pretends to be PC while player is online. This avoids persona/player mismatch.

### 5.3 C-PC3 — Simple state-based stats (no RPG mechanics)

PC has a stats JSONB with a handful of simple state fields:

```json
{
  "hp": 100,          // or "condition": "healthy" | "injured" | "dying"
  "mood": "neutral",
  "energy": 80,
  "hunger": 40,
  "tags": ["can_swim", "fluent_in_elvish"]    // capability flags, not skill levels
}
```

No XP, no levels, no skill trees, no combat math. "Can Alice swim?" → check `tags` array. "Does Alice feel hungry?" → check `hunger`. Changes happen via events.

Details (what stats, how they update, how they affect prompt context) → **PC Stats feature** (deferred but small, §9).

## 6. Social model — Sessions, not Parties (locked)

No MMO-style parties/raids/guilds. Replace with Facebook-style group chat at the **session** level.

### 6.1 D-PC1 — Session is the social unit

A **session** is a shared interaction context:
- N participants (PCs + NPCs) co-located in a region
- All participants hear each other's speech
- Session is formed implicitly when characters are in same region speaking to same subject
- User-initiated sessions: create a session explicitly ("start a gathering") → invite specific PCs/NPCs

### 6.2 D-PC2 — PvP inside session

PCs can affect each other inside a session:
- Attack, steal, befriend, romance — all legal events
- Consent model TBC (per-reality rule? opt-in flag on PC?)
- Outside a session (different regions) PCs cannot interact

### 6.3 D-PC3 — All interaction via session

There is no "global chat" or "whisper from anywhere." All interaction is scoped to a session. Covers:
- PC ↔ PC: both in same session
- PC ↔ NPC: both in same session
- Private talk: create a private session with 2 participants

Session mechanics (creation, join/leave, turn ordering with N PCs + M NPCs, message fanout, persistence) → **Session / Group Chat feature** (deferred, §9).

## 7. Canon interaction (deferred as big features)

### 7.1 E-PC1 — PC can affect L2 canon (deferred big feature)

PC actions in reality → L3 events. These MAY be promoted to L2 (seeded canon) via canonization. Very hard to design well. Deferred.

### 7.2 E-PC2 — Author notified of canon-worthy actions (deferred)

When PC does something noteworthy (kills final boss, invents new magic, etc.), system flags for author review. Detail in E-PC1's future design.

### 7.3 E-PC3 — Paradox allowed per reality, governed by World Rules (deferred)

Reality can be "strict canon" (rejects paradox at runtime) or "loose canon" (anything goes). **World Rule feature** defines per-reality enforcement. Very hard. Deferred.

## 8. Data model adjustments

Extends [02 §5.1](02_STORAGE_ARCHITECTURE.md) PC projection:

```sql
ALTER TABLE pc_projection
  ADD COLUMN derived_from_glossary_entity_id UUID,   -- A-PC2: optional glossary ref
  ADD COLUMN template_code TEXT,                     -- A-PC1: which template (nullable)
  ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE,  -- B-PC2: user hid PC
  ADD COLUMN hidden_at TIMESTAMPTZ,                  -- for conversion timing
  ADD COLUMN control_mode TEXT NOT NULL DEFAULT 'player',  -- 'player' | 'npc_converted'
  ADD COLUMN npc_converted_at TIMESTAMPTZ;           -- when control_mode flipped

-- Index for NPC-conversion scanner
CREATE INDEX pc_projection_hidden_scan_idx
  ON pc_projection (is_hidden, hidden_at)
  WHERE is_hidden = TRUE AND control_mode = 'player';
```

New event types:
```
pc.created          — initial creation
pc.hidden           — user hid PC
pc.unhidden         — user reclaimed PC (back from hiding or NPC mode)
pc.died             — in-world death (consequence per reality rule)
pc.npc_converted    — automatic transition to NPC mode
pc.canonization_nominated    — author flag (future E-PC1 feature)
```

## 9. Deferred big features (forward links)

Items that surfaced during PC design but need their own design docs. Each listed with what it encompasses:

### DF1. Daily Life / "Sinh hoạt" feature
**Covers:** B-PC2, B-PC3, C-PC2 (NPC persona generation)

- PC-as-NPC conversion threshold + mechanics
- What do NPCs (including converted PCs) do when no player is around?
- NPC daily routines (sleep, work, travel, socialize)
- NPC memory decay / summarization when not interacting
- User's reclaim UX (how to bring PC back from NPC mode)
- Ties to [01_OPEN_PROBLEMS §B3](01_OPEN_PROBLEMS.md#b3-world-simulation-tick--open)

### DF2. Monetization / PC slot purchase
**Covers:** C-PC1 (slots > 5)

- Purchase additional PC slots
- Tier-based slot allocation (platform mode: Free=5, Pro=15, Enterprise=unlimited)
- Cross-slot operations (merge, transfer, archive)
- Ties to [103_PLATFORM_MODE_PLAN.md](../103_PLATFORM_MODE_PLAN.md)

### DF3. Canonization / Author Review Flow
**Covers:** E-PC1, E-PC2, MV2 (locked but flow undefined)

- Detection of "canon-worthy" L3 events
- Author notification + review UI with diff
- L3 → L2 promotion mechanics (what happens to other realities with conflicting state)
- IP attribution (player who created the L3 events)
- Ties to [01_OPEN_PROBLEMS §E3](01_OPEN_PROBLEMS.md#e3-ip-ownership--open) and §M3

### DF4. World Rule feature
**Covers:** E-PC3, A-PC3 runtime enforcement, B-PC1 death rules

- Per-reality rule engine
- Rule types: death behavior, paradox tolerance, PvP consent, canon strictness
- Author defines rules when creating a reality
- Rules enforced at event-validation time (pre-append hook)
- L1 canon as a special case of world rule

### DF5. Session / Group Chat feature
**Covers:** D-PC1, D-PC2, D-PC3

- Session lifecycle: create, join, leave, dissolve
- Participant arbitration (turn order with N PCs + M NPCs)
- Message routing: public-to-session, whisper, aside
- Session persistence (how events are logged)
- PvP consent model inside session
- Ties to existing [98_CHAT_SERVICE_DESIGN.md](../98_CHAT_SERVICE_DESIGN.md) but for multi-character scene, not Cursor-style Q&A

### DF6. World Travel feature
**Covers:** MV5 (locked as deferred), A-PC3 (paradox traveler carryover)

- Cross-reality PC travel mechanics
- State transfer policy (what travels, what doesn't)
- Reality locale/language bridging
- Entity identity across realities
- Already mentioned in [OPEN_DECISIONS.md §"MV5 primitives"](OPEN_DECISIONS.md#mv5-primitives--what-must-be-locked-now-to-avoid-painful-retrofit)

### DF7. PC Stats & Capabilities (small)
**Covers:** C-PC3

- Concrete stats schema (what fields, defaults)
- Update semantics (who can change `hp`? `mood`? `tags`?)
- Prompt context injection (how stats surface to LLM)
- This is smaller than the others — could be folded into main design when implementation starts

### DF8. NPC ↔ PC persona generation
**Covers:** C-PC2 (NPC-mode persona), A-PC2 (glossary-derived PC)

- How to generate a coherent LLM persona from a PC's event history
- Handling of glossary-derived PCs (revert to canon Alice? keep user's drift?)
- Consistency with reality's L1/L2 canon
- May be a sub-design of DF1 (Daily Life)

## 10. Decisions status

| Decision | Answer | Status |
|---|---|---|
| A-PC1 PC creation | Full custom + templates | **LOCKED** |
| A-PC2 Play as glossary entity | Supported | **LOCKED** |
| A-PC3 Canon validation at creation | None — paradox allowed | **LOCKED** |
| B-PC1 Death | Per-reality rule (just an event) | **LOCKED** — rule details in DF4 |
| B-PC2 Offline PC | Visible + vulnerable; hide to be safe; LLM does not act | **LOCKED** — details in DF1 |
| B-PC3 Prolonged hidden | Converts to NPC; leaves hiding; LLM takes over | **LOCKED** — details in DF1 |
| C-PC1 Max PCs per user | 5 (configurable); more via purchase | **LOCKED** — purchase in DF2 |
| C-PC2 PC personality | User IS PC when active; LLM persona only when NPC-converted | **LOCKED** — generation in DF8 |
| C-PC3 Stats model | Simple state-based, no RPG mechanics | **LOCKED** — schema in DF7 |
| D-PC1 Party model | None — session replaces parties | **LOCKED** — details in DF5 |
| D-PC2 PvP | Yes, within a session | **LOCKED** — consent in DF4/DF5 |
| D-PC3 Interaction channel | Session only, no global | **LOCKED** — details in DF5 |
| E-PC1 PC affects canon | Yes — deferred big feature | **LOCKED** as deferred (DF3) |
| E-PC2 Author notification | Yes — deferred | **LOCKED** as deferred (DF3) |
| E-PC3 Paradox allowed | Yes, governed by World Rules | **LOCKED** as deferred (DF4) |

### New config keys

```
roleplay.pc.max_per_user = 5
roleplay.pc.npc_conversion_threshold_days = TBC (future DF1 decision)
roleplay.pc.default_death_rule = 'permadeath' (V1 default; per-reality override later)
```

## 11. References

- [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) — reality model this sits on top of
- [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) — PC projection lives here (§5.1); extended in §8 above
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — B3 (world tick), E3 (IP), M3 (canonization contamination) now cross-ref DF1/DF3/DF4
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — PC locks added; new deferred features DF1–DF8 registered
- [98_CHAT_SERVICE_DESIGN.md](../98_CHAT_SERVICE_DESIGN.md) — sibling for Cursor-style chat; DF5 is multi-char scene variant
- [103_PLATFORM_MODE_PLAN.md](../103_PLATFORM_MODE_PLAN.md) — tier/billing home for DF2
