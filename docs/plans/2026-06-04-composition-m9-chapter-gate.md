# Composition V0 — M9 (OI-1 publish wiring + chapter-gate) — plan

**Milestone:** M9 (final Composition V0). **Size:** L (FS). **Workflow:** v2.2 human-in-loop.
**SSOT:** design §3.1 (canonization gate) + §11 OI-1 (chapter-gate sweep) + plan M9 row.

## Why M9 is small
OI-1 is **already structural** and live-proven (CM live-smoke): accept → `insertAtCursor` → draft autosave (no canonization); review/done → book-service `/publish` (CM1) → `chapter.published` → CM3 extraction on the pinned revision. M9 adds only the **affordance gate** + the **commit telemetry** on top of that working spine. No book-service or knowledge-service change.

## PO decisions (CLARIFY checkpoint, 2026-06-04)
1. **Gate source = BE authoritative endpoint** (not FE-derived).
2. **Zero-scenes chapter = blocked** ("block until ≥1 scene done") — scoped to books that HAVE a composition Work, so Classic-only books keep CM-FE's ungated publish.
3. **Affordance = gate the existing CM-FE `PublishControl`** (new `blockedReason` prop), not a new button.
4. **`scene_committed` fires on `outline_node.status` → `done` transition** (not on prose accept).

## Acceptance criteria (from plan M9 row + §11)
- accept writes **draft**, does NOT publish — already true; verify it stays (no new canon call in compose path).
- publish **blocked while any scene ≠ done**; **all-done → publish enabled**.
- composition emits **`composition.scene_committed`** (txn-local outbox) on a scene committing.
- live: publish → extraction on the pinned revision (CM3) — already live; re-confirm on the M9 stack.
- no composition Work → grounding/gate **verified-skip** (ungated; CM-FE preserved).

## BE changes (composition-service)
1. `db/repositories/outline.py`
   - `get_node(user_id, node_id, *, conn=None)` — thread optional conn.
   - `update_node(..., *, expected_version=None, conn=None)` — thread optional conn (mirrors `create_node`).
   - NEW `chapter_scene_gate(user_id, project_id, chapter_id) -> dict` —
     `SELECT count(*) total, count(*) FILTER (WHERE status='done') done` over
     `kind='scene' AND chapter_id=$ AND NOT is_archived`; `can_publish = total>0 AND done==total`.
2. `routers/outline.py`
   - NEW `GET /works/{project_id}/chapters/{chapter_id}/publish-gate` — `_require_work` then `chapter_scene_gate`.
   - `patch_node`: when `patch['status']=='done'`, run update + emit in ONE `get_pool()` transaction:
     read `old` (conn), `update_node(conn)`, and if `_is_scene_commit(old,new)` →
     `outbox.emit(conn, aggregate_id=project_id, event_type=SCENE_COMMITTED, payload={scene_id,chapter_id,project_id})`.
     Non-done patches keep the existing self-acquiring fast path (unchanged). VersionMismatch/Reference
     exceptions propagate out of the txn (rollback) → mapped to 412/400 as today.
   - NEW pure helper `_is_scene_commit(old, new) -> bool` (scene, was-not-done, now-done) — unit-testable.

## FE changes (frontend)
3. `features/composition/types.ts` — `PublishGate = {chapter_id, scenes_total, scenes_done, can_publish}`.
4. `features/composition/api.ts` — `publishGate(projectId, chapterId, token)`.
5. `features/composition/hooks/usePublishGate.ts` —
   - `usePublishGate(projectId, chapterId, token, enabled)` react-query GET.
   - `useChapterPublishGate(bookId, chapterId, token)` — composes `useWorkResolution` (gated only when
     `status==='found'||'candidates'` ⇒ real composition_work) + the gate query; returns
     `{ blocked: boolean, scenesTotal: number, scenesDone: number }`. No Work / loading / error → `blocked:false`.
6. `features/books/components/PublishControl.tsx` — add `blockedReason?: string`; Publish `disabled` += `!!blockedReason`,
   `title` prefers `blockedReason`. Unpublish stays ungated.
7. `pages/ChapterEditorPage.tsx` — call `useChapterPublishGate`; compute `blockedReason` (editor ns:
   `publish.gate_pending` / `publish.gate_no_scenes`); pass to `PublishControl`.
8. i18n `editor` ns ×4 — `publish.gate_pending` ("{{pending}} of {{total}} scenes not yet done"),
   `publish.gate_no_scenes` ("Create and complete at least one scene to publish"). en populated;
   vi/ja/zh-TW follow existing CM-FE publish.* coverage (these locales already carry publish.*).

## Test plan
- **BE unit** (`tests/unit/test_routers.py` or test_outline_router): gate endpoint — work-404; total/done/can_publish
  (all-done → true; one not-done → false; zero-scenes → false). `_is_scene_commit` truth table
  (scene+drafting→done = true; non-scene = false; done→done = false; old None = false).
- **BE integration** (`tests/integration/`, real PG :5555): patch a scene drafting→done → exactly one
  `outbox_events` row `event_type='composition.scene_committed'` with the right payload; non-scene / done→done →
  no row; **atomicity** — a forced failure after the status write leaves NO event row (rollback).
- **FE unit**: `useChapterPublishGate` — no Work → `blocked:false`; Work + not-all-done → `blocked:true`;
  Work + all-done → `blocked:false`. `PublishControl` — `blockedReason` set ⇒ Publish disabled + tooltip;
  Unpublish unaffected.
- **VERIFY (cross-service live token):** publish a chapter whose composition scenes are all done → CM3 extraction
  fires on the pinned revision (re-confirm the CM3b chain still green on the M9 stack), or
  `LIVE-SMOKE deferred to D-COMP-M9-*` with reason.

## Out of scope (deferred / not M9)
- Rich fact-provenance tiers (V1). Autonomous loop (V1). A consumer for `scene_committed` (V0 = telemetry only;
  emit lands now, analytics/flywheel consumption is future). Per-scene publish (book-service publishes per-chapter).
