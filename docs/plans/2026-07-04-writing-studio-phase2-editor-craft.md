# Writing Studio Phase 2 — Editor-Craft UX Build Plan

> Executes [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md) Phase 2. CLARIFY done 2026-07-04 (2 parallel Explore audits + 3 rounds of `AskUserQuestion` resolving M7, the upload-context redesign, and popout scope). DESIGN is folded into the spec's Phase 2 section (task breakdown + the two architecture-redesign write-ups). This document is PLAN — build starts same session.

## Size classification

**L** — 11 tasks (2.1–2.11), logic count squarely in the 7-12 band; risk floor crosses into L regardless of file count because two tasks (2.7 upload-context, 2.8 popout) are genuine architecture changes, not ports: 2.7 changes a shared module's storage model (`ImageBlockNode.tsx`/`VideoBlockNode.tsx`, also used by the still-live legacy page) and 2.8 introduces a new cross-window contract (`ProposeEditCard`'s Apply path branches on popout-vs-docked). Per CLAUDE.md's L row: no skips, write a plan file (this doc) before BUILD.

## Why this ordering

Per CLAUDE.md sizing rule (risk over file-count) and the spec's own M2 precedent (data-safety before UX polish) — within Phase 2 itself, order by **shared-file convergence**, not by feature importance: most tasks (2.1-2.6, 2.9-2.10) all touch the *same two files* (`EditorPanel.tsx`'s single toolbar row and `<TiptapEditor>` call, `ManuscriptUnitProvider.tsx`'s `save()`/`loadChapter()`). Building these in parallel subagents would produce N conflicting diffs on the same lines — the opposite of Phase 1's checkpoints/revision-history/publish-gate, which were genuinely disjoint new files. So the convergent tasks are sequential, single-owner; only the genuinely disjoint tasks (2.7's new panel, 2.8's new popout subtree, 2.11's new panel) are fan-out-eligible, and only *after* the shared files have stabilized.

## Execution shape

```
Sequential (single owner, same-file convergence — EditorPanel.tsx / ManuscriptUnitProvider.tsx):
  2.1  Grammar toggle
  2.2  Focus/typewriter mode
  2.3  Mention heatmap
  2.4  Glossary decoration + [[ autocomplete (+ replace execCommand hack with insertAtCursor)
  2.5  AI-provenance review UI (ProvenanceToolbar + ProvenanceTag)
  2.6  Selection Toolbar + Inline AI layer (projectId/scene/model resolution)
  2.9  Auto-save timer (ManuscriptUnitProvider.tsx)
  2.10 Progress-reporting + baseline (ManuscriptUnitProvider.tsx)
  → one combined unit-test pass across 2.1-2.6/2.9-2.10 (shared-file changes verified together)

Fan-out eligible once the above lands (disjoint new files, no shared-line risk):
       ┌─ 2.7  Upload-context storage redesign + MediaVersionHistoryPanel ─┐
PARALLEL├─ 2.8  Popout Compose window (route + bridge + cross-window Apply) ├→ serial integration
       └─ 2.11 Original-source viewer panel                               ─┘
                                      │
                        ONE combined verify + DOCK-1..11 compliance + /review-impl
                        → live browser smoke (all 7 smoke checks from the spec's Phase 2 gate)
                        → POST-REVIEW (human checkpoint, never skippable)
                        → SESSION_HANDOFF update + RETRO
```

### Why 2.1–2.6/2.9–2.10 are sequential, not fanned out

All eight sit on `EditorPanel.tsx`'s ~40-line toolbar row and its single `<TiptapEditor>` call, or `ManuscriptUnitProvider.tsx`'s `save()`/`loadChapter()`. Most are individually small (prop-thread an existing hook, add one toolbar control) — the cost of serializing them is low, and the cost of parallel-agent collision on the same render block is high (Phase 1's lesson: even genuinely-planned-disjoint work needs a combined review when it touches shared domain state; here the files themselves aren't even disjoint). Build order within the sequential block follows the task table order (2.1→2.10) for no reason other than simplicity — none of these 8 tasks depend on each other's output.

### Why 2.7/2.8/2.11 fan out

- **2.7** touches `components/editor/ImageBlockNode.tsx`, `VideoBlockNode.tsx`, and a new `MediaVersionHistoryPanel.tsx` — none of which the sequential block above touches.
- **2.8** is an entirely new subtree (`features/studio/popout/*`) plus one new toolbar button in `ComposePanel.tsx` (different file from `EditorPanel.tsx`) and a new branch in `ProposeEditCard.tsx` (touched today in this session's #2 APPLY-DIFF fix, but that work is committed and stable — re-diff before editing per shared-file discipline).
- **2.11** is a wholly new panel file + a `catalog.ts` registration row (shared spine file — re-diff immediately before adding the row, per [[shared-file-collision-safe-staging-multi-agent-checkout]] and the coordination note already in spec #16).

### Phase-agent contract (2.7/2.8/2.11, if fanned out to subagents)

Each gets:
- Its exact task row + the architecture-redesign write-up from spec #16's Phase 2 section (2.7 and 2.8 have significant design prose there — read it, don't re-derive).
- Explicit instruction: **do not edit `EditorPanel.tsx`/`ComposePanel.tsx` directly** for anything beyond the one integration point named in its own task row — return new files + the exact import/JSX/registration snippet for serial integration.
- For 2.7: the exact storage-key convention to use on `editor.storage` (mirror `editor.storage.mediaGuard.editorMode`'s existing shape in `TiptapEditor.tsx:199-220`) and an explicit requirement to verify `ChapterEditorPage.tsx` (legacy) still works unchanged after the change (single-instance behavior is a strict subset of per-instance — should need zero legacy-page edits, but the task must prove it, not assume it).
- For 2.8: the full existing `PopoutHost.tsx`/`PopoutBridge.tsx`/`popoutChannel.ts` read (already done this session, summarized in spec #16) as the pattern to mirror — reuse `openPopoutChannel` as-is, do not fork the channel primitive; the new/hard part is *only* the popout-aware branch in `ProposeEditCard.tsx` and the new Studio popout route.
- For 2.11: `booksApi.getOriginalContent` signature (confirmed present, `features/books/api.ts:284`) and DOCK-8 (own panel, no internal tab-swap inside `EditorPanel`).
- DOCK-1..11 self-check reference for 2.7 (new panel) and 2.11 (new panel) — 2.8's popout route is not a dockable panel (it's a separate window/root), DOCK rules don't apply to it directly, but `ComposePanel.tsx`'s new toolbar button does live inside a dockable panel.

## Phase checkpoints (mapped to the 12-phase workflow)

| Phase | State |
|---|---|
| CLARIFY | Done — 2 parallel Explore audits + 3 `AskUserQuestion` rounds (M7 dropped, upload-context redesign confirmed, popout = real OS window confirmed), 2026-07-04 |
| DESIGN | Done — spec #16's Phase 2 section (task table + 2.7/2.8 architecture write-ups) |
| REVIEW (design) | Self-review folded into the spec-writing pass (shared-file convergence analysis, fan-out eligibility split) |
| PLAN | This document |
| BUILD | Same session — sequential block first, then 2.7/2.8/2.11 fan-out |
| VERIFY | Per-task tests; one combined suite run + live browser smoke (7 checks from spec's Phase 2 gate) at close |
| REVIEW (code) | `/review-impl` on the full integrated Phase 2 diff (not per-task — same-file convergence means cross-task interaction bugs are the real risk, per Phase 1's precedent) |
| QC | Folded into `/review-impl` |
| POST-REVIEW | Human checkpoint after Phase 2 integrates — present summary, STOP, WAIT |
| SESSION | `SESSION_HANDOFF.md` update after Phase 2 closes |
| COMMIT | Sequential block as one commit; 2.7/2.8/2.11 as a second commit (or per-task if diffs are large) |
| RETRO | `add_lesson` if the `editor.storage`-scoping pattern (2.7) or the popout-aware Apply branch (2.8) generalizes to other future per-instance-state bugs |

## Risk notes

- **2.8 is the highest-risk single task in this phase** — a new cross-window contract with no legacy precedent (legacy's popout never had a human-gated diff-review card to relay). Give it its own focused `/review-impl` pass before folding into the combined one, and a dedicated live smoke (actually open a second OS window, not just a mocked BroadcastChannel test).
- **2.7's `editor.storage` migration must not regress the legacy page** — `ChapterEditorPage.tsx` is still the default surface for most users until Phase 4; a live smoke on the legacy route (image upload still works) is required, not just a Studio-side smoke.
- **2.4's autocomplete fix (execCommand → insertAtCursor) is a behavior change, not just a port** — verify cursor position and undo-stack behavior match or improve on the legacy hack; don't assume `insertAtCursor` is a drop-in replacement without testing at the exact autocomplete-trigger call site.
- **Toolbar real-estate**: 2.1/2.2/2.3 each add one more control to `EditorPanel.tsx`'s single `flex h-7` row (already has 4 controls per the audit). Watch for overflow on narrow panels — may need a "more" overflow menu; not blocking, but worth a visual check during live smoke.
- Re-diff `EditorPanel.tsx`, `ManuscriptUnitProvider.tsx`, and `catalog.ts` immediately before each edit — this checkout runs concurrent sessions (see [[shared-file-collision-safe-staging-multi-agent-checkout]]).
