<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 09_deferred_big_features.md
byte_range: 13167-16446
sha256: fa257be533d91dd5c923dd7b0e218e9604cf8ba43800e75f59974bfa698d16be
generated_by: scripts/chunk_doc.py
-->

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

