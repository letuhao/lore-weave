# Plan — D-KG-TL-PARTICIPANT-ANCHOR (Option A: store participant entity anchors at extraction + backfill)

**Date:** 2026-06-26 · **Size:** L · **Spec:** [2026-06-26-kg-timeline-localization.md](../specs/2026-06-26-kg-timeline-localization.md) §(c) Option A, line 166-171, 181-184, 251.

## Goal
Replace the timeline localizer's **read-time** participant name→entity resolution (Option B, shipped in M2) with a **stored anchor** resolved at extraction time. Each `:Event` node gains a `participant_entity_ids` list parallel to `participants`; the read path prefers it and only re-resolves residual names from un-backfilled events. A backfill populates existing events.

## Key design decisions
- **Stored value = the glossary `entity_id`** (what the localization join `fetch_entity_display_names(book_id, entity_ids, language)` consumes directly), or the empty-string sentinel `""` when a participant can't be anchored. (Neo4j lists cannot contain nulls → `""` sentinel, never a real UUID.)
- **Parallel + aligned** to the *deduped* `participants` (merge_event dedups via `dict.fromkeys`). The array is built from the deduped list so index i of `participant_entity_ids` ↔ index i of `participants`.
- **Read-path length guard:** the localizer trusts stored ids only when `len(participant_entity_ids) == len(participants)`; otherwise (legacy / partially-migrated) it falls back to read-time resolution for that event. Backfill normalizes legacy events to full aligned arrays.
- **Resolution reuses the existing surface** — `find_entities_by_name` (canonical+aliases, anchor_score-first) → `ent.glossary_entity_id`, identical to the localizer's current `_resolve_names_to_entity_ids`. One shared helper, three callers (write, read-fallback, backfill).
- **Anchor stored ≠ API field:** `participant_entity_ids` is `Field(exclude=True)` — populated from the node into the `Event` model for the localizer to read, but NOT serialized into the timeline API response (keeps the wire contract unchanged; it's an internal anchor, not FE-facing).
- **AC-T3 preserved:** an unanchored or untranslated participant keeps its source name + `participants_translated=False` marker — never a silent mix.

## Changes (by file)
1. **`app/db/neo4j_repos/entities.py`** — new `resolve_participant_anchors(session, *, user_id, project_id, names) -> dict[str, str]` (name→glossary_entity_id for anchored names; reuses `find_entities_by_name` + anchored-first pick). The canonical home for the logic currently inlined in the localizer.
2. **`app/db/neo4j_repos/events.py`**
   - `Event` model: add `participant_entity_ids: list[str] | None = Field(default=None, exclude=True)`.
   - `merge_event`: new optional `participant_anchors: dict[str,str] | None` param → build `participant_entity_ids` aligned to `deduped_participants` (`anchors.get(p, "")`; `[]` when no map → read fallback). Thread into Cypher.
   - `_MERGE_EVENT_CYPHER`: ON CREATE `e.participant_entity_ids = $participant_entity_ids`; ON MATCH append the new slots by **index filter** (same `range(0,size-1) WHERE NOT $participants[i] IN e.participants` used for both participants and ids → guaranteed alignment), `coalesce(e.participant_entity_ids, [])` for legacy nodes.
3. **`app/extraction/pass2_writer.py`** — before `merge_event`, resolve the sanitized participant names via `resolve_participant_anchors(session, ...)` and pass `participant_anchors=...`.
4. **`app/labels/timeline_localizer.py`** — `localize_participants`: build `name_to_eid` from stored aligned arrays (anchored slots), track known names, and resolve only the **residual** names (events lacking aligned ids) via the existing `_resolve_names_to_entity_ids` fallback. `_resolve_names_to_entity_ids` delegates to the shared `resolve_participant_anchors` (opens its own session).
5. **`app/db/migrations/backfill_participant_anchors.py`** (new) — per-project: read events, resolve each event's participants → aligned id array, `SET e.participant_entity_ids`. Result counters. Mirrors `backfill_orders.py`.
6. **`app/routers/internal_backfill.py`** — new `POST /internal/projects/{project_id}/backfill-participant-anchors` (X-Internal-Token, resolve user_id from `knowledge_projects`, Neo4j-optional skip). Mirrors `backfill-orders`.

## Tests
- `resolve_participant_anchors`: anchored name → glossary_entity_id; unanchored → absent (caller maps to `""`).
- `merge_event`: ON CREATE stores aligned array; ON MATCH append keeps alignment; no map → `[]`.
- `localize_participants`: prefers stored ids (skips resolver when fully backfilled); falls back on absent/misaligned; mixed page resolves only residual; unanchored `""` stays source + flag False (AC-T3).
- backfill: resolves + overwrites; counters; idempotent re-run.

## Out of scope
- Event `title` localization (free text, no anchor — rides the summary path).
- Switching the stored anchor to the knowledge canonical_id (robust-to-reanchor variant) — glossary_entity_id is directly consumable; re-extraction/backfill refreshes staleness.

## Verify
py_compile clean; knowledge-service unit suite green (new tests); cross-service note: backfill→(book/glossary none) is single-service; live-smoke optional (`D-KG-TL-PA-LIVE-SMOKE`) on the rebuilt stack against the 万古神帝 project (Chinese participants).
