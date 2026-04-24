<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 03_creation.md
byte_range: 3206-5147
sha256: 19d518b28a4247312cbc995a1ff234772b61ec8267e573cc4ac62e951a8b6c22
generated_by: scripts/chunk_doc.py
-->

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

