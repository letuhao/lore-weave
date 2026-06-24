# feat/composition-service — Branch Recall (anti-drift snapshot)

> **Purpose:** a fast, consolidated recall of what this branch has DONE / NOT-DONE, plus the
> file surface to PRESERVE across the upcoming large merge from `main`. Snapshot taken at
> **HEAD `b05b104f`** (2026-06-11), **PR #32 → main** open. Authoritative live state stays in
> `SESSION_HANDOFF.md` (▶ NEXT block); this file is the at-a-glance index.

## Branch state
- HEAD `b05b104f` · PR **#32 → main** open · just merged `origin/integration/e0-collaboration`
  (grant/billing/collaboration) — **clean, no conflicts**.
- Branch is **NOT closeable** (PO): finish ALL drafted V1 composition features to a USABLE
  state before final close. Intermediate merges to main are fine (PR #29 already did one).

## ✅ DONE — LOOM composition V1

| Track | Features | Commits |
|---|---|---|
| 0 | T0.1 ThreadsPanel | (pre-session) |
| 1 | T1.1a–d Outline (browser / CRUD+restore / dnd-reorder / Corkboard) · T1.2 Beat Sheet · T1.3 Scene Graph | …32727390 · ae406de1 · 4d2097dd |
| **2 — COMPLETE** | T2.1 Cast&Codex · T2.2 RelationshipMap(+GraphCanvas extraction) · T2.3 Timeline · T2.4 Character Arc · T2.5 World Map | 27f525b4 · 8db1110b · a5061bf5 · 065bbe94 · aad9cbbf |
| 3 — in progress | T3.1 Co-writer Chat · T3.2 Selection Tools · T3.3 Classic/AI Inline Mode | 72a53541 · d340c051 · 86100ef6 |

### New BE surface added by this branch (easy to lose in a merge — protect it)
- **knowledge-service** — `POST /v1/knowledge/entities` + `POST /v1/knowledge/relations`
  (T2.5; thin wrappers over `merge_entity` / `recreate_relation`). T2.1 also changed
  `neo4j_repos/facts.py` (`(:Fact)-[:ABOUT]->(:Entity)`, `subject_id`/`from_order` forward),
  `entity_status.py`, `extraction/pass2_writer.py`, `neo4j_schema.cypher` (ABOUT + Fact index).
- **composition-service** — `POST /v1/composition/works/{pid}/selection-edit` (T3.2 SSE;
  `routers/engine.py` + `engine/cowrite.py::build_selection_messages` explicit op-dispatch).
  `db/repositories/generation_corrections.py` excludes selection edits from `correction_stats`.

### /review-impl fixes baked in (must survive any merge)
- T3.2 **HIGH** — selection-edit job sets `outline_node_id=None` (NOT the scene), so it can't
  masquerade as the scene's latest draft in `chapter_scene_drafts` (stitch) / `prior_scene_drafts`
  (S1 reinjection) / publish-gate canon count. Scene id lives in `input.scene_context`.
- T3.2 **MED** — `correction_stats` filters `NOT (input->>'selection_edit')::boolean`.
- T2.5 **MED** — `useWorldMap` merges positions+backdrop via one `wmRef` (no clobber).

## ⬜ NOT DONE — remaining V1 (~10–11 features → T5.5)
**NEXT = T3.4** Grounding Pin/Exclude. Then: T3.5 Style & Voice · T3.6 References · T4.1 Flywheel
Panel · T4.2 Progress Stats · T5.1 Focus/Typewriter · T5.2 Mention Heatmap · T5.3 AI Provenance
Highlight · T5.4 Dock/Float Windowing · T5.5 Story Map Power-view.
**Verify status of:** T0.2 suggest-cast-wiring, T1.4 corkboard (not in the BUILD list — may be
folded into T1.1d or pending).

### Deferred (tracked, intentional — 14 rows)
`D-T2.4-{ARC-ENTITY-BOOK-RESET, ARC-PAGING}` · `D-T2.5-{MANUAL-GLOSSARY-SYNC, AUTHORING-EVENTS,
PLACE-DETAIL-FANOUT, BACKDROP-INSTANT, LINK-DIRECTION}` · `D-T3.1-{SCENE-HINT, GUIDE-APPEND}` ·
`D-T3.2-{SELECTION-INLINE-GHOST, SELECTION-RANGE-MAP}` · `D-T3.3-{SLASH-CONTINUE, CHAPTER-CONTINUE,
GHOST-POS-MAP}`.

## ⚠️ MERGE-WATCH — files this branch uniquely owns (preserve on the big merge)
User confirmed **no conflict expected** — this list is the "don't let it silently drift" checklist.

- **knowledge-service:** `app/routers/public/entities.py`, `app/routers/public/relations.py`,
  `app/db/neo4j_repos/{facts,entity_status,entities}.py`, `app/extraction/pass2_writer.py`,
  `app/db/neo4j_schema.cypher`.
- **composition-service:** `app/routers/engine.py`, `app/engine/cowrite.py`,
  `app/db/repositories/generation_corrections.py`.
- **frontend:** all of `features/composition/*`; `components/editor/TiptapEditor.tsx` (two additive
  slots: `selectionMenu` + `aiLayer` — do NOT let a main version drop them);
  `pages/ChapterEditorPage.tsx` (work-resolution + lifted `activeSceneId`);
  `i18n/locales/{en,vi,ja,zh-TW}/composition.json` (namespaces: `chrono, chararc, wmap, cw, sel,
  inline, relations`, key `codex.viewArc`).
- **Reusable primitives** (don't fork — extend via slots): `GraphCanvas` (background slot),
  `TiptapEditor` (selectionMenu/aiLayer), `CompositionPanel` (sceneId controlled-or-internal).

## 🧭 Recommended order (avoid drift / rework)
1. **Merge PR #32 → main first** if possible, so the big merge/refactor rebases onto a base that
   already contains this work (no manual reconcile of 546 diverged commits).
2. If main → branch must come first: keep everything in MERGE-WATCH, then re-run the intersection
   suites to catch *semantic* breaks (the e0-collaboration merge already surfaced one stale test):
   - `composition-service` unit (was 412) · `knowledge-service` unit (was 2354) · FE composition
     vitest (was 230). Run from each service dir / `frontend`.

## Post-merge sanity (commands)
```
# composition + knowledge unit (intersection services)
cd services/composition-service && python -m pytest tests/unit -q
cd services/knowledge-service  && python -m pytest tests/unit -q
# frontend composition
cd frontend && npx tsc --noEmit && npx vitest run src/features/composition
```
