<!-- CHUNK-META
source: OPEN_DECISIONS.ARCHIVED.md
chunk: 00_preamble.md
byte_range: 0-1211
sha256: 0c107f76eee5b7ffc5283baed9df1803622eeb906db43319ca0afb3b9f475e22
generated_by: scripts/chunk_doc.py
-->

# Open Decisions — Pending User Confirmation

> **Purpose:** Single place to track all decisions that are pending the user's answer. As the conversation accumulates, questions get parked here so none are lost.
> **Not a decision doc itself.** This file just tracks what needs answering; actual decisions are recorded in their respective design docs.

---

## How to use this file

- **Locked** — user has explicitly confirmed. Moved to "Locked decisions" section at bottom; removed from pending.
- **Default applied, pending confirm** — I proposed a default; user said "default" or was silent; the default is in the relevant doc but user has the right to overturn.
- **Open, no default** — genuinely waiting for user input. No default applied yet.

When the user answers one, I:
1. Update the relevant design doc (02, 03, etc.) to reflect the decision
2. Move the entry from "Pending" to "Locked decisions" below
3. Add a brief rationale/note if the user gave one

---

## Pending decisions

*(All multiverse-model decisions + vision-level decisions + MV5 primitives are **LOCKED** as of 2026-04-23. See Locked decisions table below for V-1, V-2, V-3, MV5-pri entries.)*

---

