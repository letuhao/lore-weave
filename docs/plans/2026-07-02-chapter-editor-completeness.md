# Chapter Editor Completeness — cycle-1 M-F…M-I (2026-07-02)

**Goal:** the studio chapter editor becomes a COMPLETE component: scenes are navigable
into the prose (real markers, not heuristics), CRUD-able from the GUI, and the editor
chrome stops lying (word count, dirty state). Continues spec
[`12_json_document_standard.md`](../specs/2026-07-01-writing-studio/12_json_document_standard.md)
cycle-1; PO sign-off 2026-07-02: sceneMarker NOW (no wait-for-pipeline), ▲/▼ reorder, all 4 milestones.

**Size:** L (logic ~10, files ~15, side effects: draft-body writes via backfill). One
continuous run, checkpoint per milestone.

## M-F · sceneMarker — scene→prose anchoring (the big one)

**Representation (LOCKED):** the marker is a `sceneId` attribute ON the existing heading
node (`attrs: {level, sceneId}`), NOT a new node type. Rationale: zero visual change,
survives book-service opaquely (chapter_blocks tolerates non-text/unknown attrs), and
the platform's de-facto convention already puts scene-title headings in composed bodies
(POC Chương 1 has `### Cuộc Truy Sát Trong Đêm`). A custom invisible node would need
render/UX + trigger-tolerance work everywhere.

- **F1 `SceneAnchorExtension`** (FE, TiptapEditor): GlobalAttributes on `heading` —
  `sceneId` (default null, `data-scene-id` HTML round-trip). REQUIRED so Tiptap's schema
  does not STRIP the attr on load→save (without this, opening a marked chapter would
  silently erase every marker).
- **F2 Jump seam:** `jumpToScene(sceneId)` on the manuscript unit hoist (uses
  `editorRef` + a doc walk for `heading[sceneId]`): scrollIntoView + cursor. Wire: Scene
  Rail click, navigator scene click, ⌘P scene hit (all already publish the `scene` bus
  slice — the rail's existing highlight subscription gains the jump). Marker absent →
  today's behavior (rail highlight only). No new seams.
- **F3 Backfill (existing books):** explicit rail action "Neo cảnh ⚓" shown when
  scenes exist AND ≥1 heading lacks `sceneId`: normalize-match heading text ↔ scene
  titles (trim/casefold/diacritics-preserving exact, then unique-substring), set attrs
  via ONE editor transaction → normal dirty → user ⌘S saves. EXPLICIT, never auto-write
  on open (multi-device safety). Ambiguous/unmatched headings are left unmarked and
  reported in the rail notice.
- **F4 Emit-at-generation (contract, deferred wiring):** whichever path persists a
  generated chapter (accept flow / RAID authoring-run driver) SHOULD emit
  `heading{sceneId}` per scene at assembly time; stitch degrade-to-concat knows exact
  boundaries, the stitched path anchors by the same title-match as F3. **Deferred row
  `D-SCENEMARKER-EMIT`** (gate #1/#4: the persist seam is RAID D-wave's actively-moving
  code today) — the F1 attr + F3 matcher are the reusable pieces.

## M-G · Scene CRUD on the rail

- **G0 (BE, tiny):** `GET …/chapters/{cid}/scenes` response gains `chapter_node_id`
  (the outline CHAPTER node) so Create works when the chapter has zero scenes.
- **G1 (FE api):** `deleteNode`, `restoreNode`, `reorderNode` wrappers (BE routes exist:
  DELETE soft-archive, POST /restore, POST /reorder with after_id + If-Match).
- **G2 Create:** rail ＋ → inline title input → `createNode{kind:'scene', parent_id:
  chapter_node_id, chapter_id, title, status:'empty'}` → reloadScenes.
- **G3 Delete:** per-scene ✕ → archive → toast with Hoàn tác (restore) → reloadScenes.
- **G4 Reorder:** ▲/▼ per scene → reorder(after_id from current order, If-Match
  version); 412 → stale notice + reload (same pattern as the rail's synopsis save).

## M-H · Word count (status bar)

`EditorPanel` registers an F2 status-bar item: word count from the hoist
`state.textContent` (unicode word regex, CJK-aware fallback to chars), debounced.
Replaces the "— words" placeholder.

## M-I · Warts

- **Dirty-on-mount:** hoist `setBody` gains a cheap equality guard (incoming ==
  savedBody → don't mark dirty) — kills the Tiptap mount-normalize false-dirty that
  forced the json-editor empty-buffer workaround.
- **Max-update-depth warning** (seen in live smoke, console): root-cause investigation,
  timeboxed; fix if small, else deferral row with the trace.

## Verify

Per-milestone unit tests + one live browser pass at the end: ⌘P → scene → prose jump;
rail ＋/✕/▲▼ round-trip vs DB; backfill on Chương 1 (2 headings match 2 scenes); word
count live. Cross-service surface = G0 only (composition) → live smoke covers it.
