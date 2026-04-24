<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 05_identity_and_agency.md
byte_range: 8299-9954
sha256: e29abe4f079d62c953f0622b81d3c72c2183ac297aa9c88f9d77ccd97bcc2afa
generated_by: scripts/chunk_doc.py
-->

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

