<!-- CHUNK-META
source: OPEN_DECISIONS.ARCHIVED.md
chunk: mv5_primitives.md
byte_range: 166601-169510
sha256: 8e72c7e17645042a3e7a5d338bb8634d9911fb2bce27a6862732e8faa712e6a6
generated_by: scripts/chunk_doc.py
-->

## MV5 primitives — what must be locked now to avoid painful retrofit

Cross-reality travel is deferred, but these schema/protocol primitives cannot be added later without migration pain across all reality DBs. Must exist from V1 even if unused:

| # | Primitive | Why can't defer | Status |
|---|---|---|---|
| P1 | **Reality has `locale` field** (`en`, `vi`, `zh`, ...) | Travel between realities of different languages will need locale-aware display. Adding a locale to existing realities later = complex backfill. | **Must add to `reality_registry`** |
| P2 | **All PC/NPC/Item IDs are globally unique UUIDs** | Travel requires disambiguating entities across realities. UUID gives this for free. | Already planned ✓ |
| P3 | **Meta `player_character_index` tracks `(user_id, pc_id, reality_id)`** | One user, multiple PCs across realities. Future travel needs to surface "your PCs across all realities." | Already planned ✓ |
| P4 | **Event metadata has optional `travel_origin_reality_id` + `travel_origin_event_id`** | If a future event is "PC arrived from travel," the origin must be audit-traceable. Reserving the metadata keys now is zero-cost; adding later requires every consumer to handle both old and new formats. | **Must add to event metadata schema (optional fields, ignored in V1)** |
| P5 | **Items have `origin_reality_id` (nullable)** | Future travel carrying an item needs to know where the item was minted. Nullable = non-breaking. Adding later = migration through all projection + events of all realities. | **Must add to inventory projections** |
| P6 | **World clock is per-reality** | Each reality has its own in-world time. Travel crosses "time zones." Already planned but reinforce: do NOT share a global world clock. | Already planned ✓ |
| P7 | **NPC memory is reality-scoped (not global per glossary entity)** | NPC Elena's memory of PC Alice differs per reality (Elena-R1 and Elena-R2 are "same character, different experiences"). Already reality-scoped via DB-per-reality. | Already planned ✓ |
| P8 | **Canon lock level per attribute** | Travel may carry attributes that are L1 (globally fixed) or L2 (reality-local). Future code needs to know which travels, which doesn't. | Already planned via `canon_lock_level` ✓ |

**Not strictly required but highly recommended:**

| # | Primitive | Note |
|---|---|---|
| P9 | Currency / token abstraction | If future travel enables cross-reality trade, separating "in-world currency" from "platform currency" helps. Not critical for V1. |
| P10 | Entity "portability" flags | Per entity type (PC, item, knowledge), mark whether it is "travelable" in principle. Schema-free in V1 — add as JSONB field later. Skip for now. |

These 8 locked primitives (P1–P8) ensure that when world-travel feature is designed later, the schema doesn't need painful ALTERs across every reality DB.

---

---

