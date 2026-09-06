<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 02_pc_vs_npc.md
byte_range: 2265-3206
sha256: afeb2c30598301f8907452e0ba152459c7d72d6dd9ba01c30ac326f998d46ad2
generated_by: scripts/chunk_doc.py
-->

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

