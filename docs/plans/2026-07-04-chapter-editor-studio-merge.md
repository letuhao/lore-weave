# Chapter Editor → Studio Merge — Phase 1 Build Plan

> Executes [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md) Phase 1 (data-safety parity + one prerequisite architecture fix). CLARIFY+DESIGN are done (user-approved 2026-07-04: retire `ChapterEditorPage`, Studio becomes the sole chapter-editing surface). This document is the PLAN phase output — **no BUILD this session**, per the user's explicit scoping ("spec + plan only, this pass").

## Size classification

**XL** for the whole COHERENCE effort (15+ legacy-only capabilities across 4 phases, a route-ownership change, 1 prerequisite architecture fix to already-shipped code) — per `CLAUDE.md`'s table this requires a written spec (done, #16) + plan (this doc) before BUILD, with subagent fan-out recommended for the larger phases.

**Phase 1 alone is L**: 1 prerequisite fix (P1 Lane-C compliance) + 5 build tasks (1.1–1.5, including the G7 dirty-guard reuse folded into 1.2/1.3), one side effect (a route-ownership change in `ChaptersTab.tsx`), ~6-8 files. Sized and planned independently — Phases 2–4 are deliberately NOT planned in file-level detail here (per the spec's own "roadmap only, spec at kickoff" convention); re-classify each when it starts.

## Why Phase 1 is scoped this way

Per spec #16's Locked Decisions (M2, M4): risk order, not file-count order. The only legacy-only gaps where a user could **lose work or ship broken canon** are Checkpoints, Revision History, and Publish Gate — everything else (Phase 2's grammar/glossary-decoration/heatmap/etc., Phase 3's Translate workmode) is UX polish or a large standalone migration that can safely wait. The prerequisite fix (P1) is debt-paydown on code that **already shipped today** (`fb98f161f`, the APPLY-DIFF fix) — building Checkpoints on top of the current `editorBridge` global-singleton wiring would bake a known landmine deeper, so it gates everything else in this phase. (P2, the G7 dirty-guard, turned out to already exist for the Lane-B reconciler — see the correction below — so it's folded into 1.2/1.3's own scope, not a separate gate.)

## Execution shape

```
Prerequisite (P1 only — see correction below):
  P1. ManuscriptUnitProvider.applyProposedEdit(diff) + retire editorBridge from the STUDIO path only
      (ChapterEditorPage keeps editorBridge unchanged — spec 08 step 5, it's being retired anyway)
  → regression test: applyProposedEdit works end-to-end; no residual registerEditorTarget call
    site left in EditorPanel.tsx/ComposePanel.tsx
  → /review-impl on P1 alone before Phase 1 tasks start (small, self-contained, load-bearing)

Phase 1 build (parallelizable once P1 lands — tasks 1.2/1.3/1.4 touch disjoint new files):
        ┌─ 1.2 Checkpoints        ─┐
PARALLEL ├─ 1.3 Revision History    ├─→ integration (all mount inside EditorPanel.tsx — serial edit)
        └─ 1.4 Publish Gate       ─┘
                                      │
                        1.5 Route switch (ChaptersTab.tsx) — independent, can run any time after 1.1-1.4
                        land (no reason to flip the default route before its replacement works)
                                      │
                        ONE combined verify + dockablePanelHygiene + /review-impl
                        → POST-REVIEW (human checkpoint, never skippable)
                        → SESSION_HANDOFF update + RETRO
```

### Correction (spec #16, 2026-07-04): P2 is not a separate gated prerequisite

The initial audit read the G7 dirty-guard as an unimplemented design hole. Re-checked against code: it's **already implemented** for the Lane-B reconciler (`bookEffects.ts`'s `bookDraftEffect` calls `ctx.isChapterDirty?.(chapterId)` before reloading — confirmed live in the file, not just the spec). So there's no separate "P2 build" step — 1.2 (Checkpoints) and 1.3 (Revision History) each just need to call the *same existing check* before their own restore action, as part of their own task scope and their own tests ("blocked by a dirty hoist"). Only P1 is a true prerequisite with its own gate.

### Why P1 is serial but 1.2/1.3/1.4 can fan out

P1 (the hoist action) is a genuine prerequisite — `applyProposedEdit` must exist before anything else in this phase touches `ManuscriptUnitProvider`'s write surface, and it's the exact code path today's `fb98f161f` commit touched, so it deserves its own isolated review. Once it lands, 1.2/1.3/1.4 are genuinely disjoint new files (`useManuscriptCheckpoints.ts`, `useRevisionHistory.ts`, `EditorPanel.tsx` toolbar extension for Publish Gate) per [[fanout-independent-slices-parallel-build-serial-integrate]] — EXCEPT all three mount inside `EditorPanel.tsx`'s render tree, so the final "wire the section into the panel" edit is a serial integration step (small — each task's agent returns its component + hook; one pass adds three imports + three render calls), not a 3-way collision on the same lines.

### Phase-agent contract (if fanned out to subagents)

Each of 1.2/1.3/1.4 gets:
- Its exact task row from spec #16's Phase 1 table.
- Explicit instruction: **do not edit `EditorPanel.tsx` directly** — return the new hook + component, and the exact JSX snippet + import line to add, for the orchestrating session to integrate serially (avoids 3 agents editing the same file simultaneously).
- The API surface each task needs as GIVEN context: `applyProposedEdit` (new, from P1 — must land first) and `isChapterDirty` (already exists, same one `bookEffects.ts` already calls) — each restore path calls `isChapterDirty` itself as part of its own task, not a separate prerequisite.
- Instruction to port the **legacy hook's test assertions**, not copy the legacy hook verbatim — Studio's save/apply seams differ from `ChapterEditorPage`'s three seams (`onAccept`/`applyPolish`/popout-relay), which don't exist in Studio.
- DOCK-1..11 self-check reference (`docs/standards/dockable-gui.md`) — these are panel-section additions, not new panels, so most DOCK rules are N/A, but DOCK-2 (no fork) and DOCK-10 (hoist ownership) apply.

## Phase checkpoints (mapped to the 12-phase workflow)

| Phase | State |
|---|---|
| CLARIFY | Done — audit + `AskUserQuestion` (2 rounds), user-approved 2026-07-04 |
| DESIGN | Done — [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md) |
| REVIEW (design) | Self-review folded into the spec-writing pass (prerequisite-fix framing, phase-order rationale) |
| PLAN | This document |
| BUILD | **Not this session** — next session/continuation, starting with P1 |
| VERIFY | Per-task tests during build; one combined suite run + live browser smoke at Phase 1 close |
| REVIEW (code) | `/review-impl` twice — once on P1 alone (small, load-bearing), once on the combined Phase 1 diff |
| QC | Folded into the second `/review-impl` pass |
| POST-REVIEW | Human checkpoint after Phase 1 integrates — present summary, STOP, WAIT |
| SESSION | `SESSION_HANDOFF.md` update after Phase 1 closes |
| COMMIT | P1 as one commit (load-bearing, wants its own bisectable point); 1.2/1.3/1.4/1.5 as a second commit (or per-task if the diffs are large) |
| RETRO | `add_lesson` — the editorBridge→hoist migration pattern is reusable for any future Lane-C-violating shortcut found elsewhere |

## Risk notes

- **P1 touches the exact code this session already modified today** (`ComposePanel.tsx`, `ProposeEditCard.tsx`, `fb98f161f`) — re-read the current state of both files at build start, don't assume this plan's snapshot is still accurate after any intervening concurrent-session edits.
- **`ChaptersTab.tsx`'s exact path/structure is unconfirmed** — the audit found it under `BookDetailPage` but didn't pin the file path precisely. Confirm at build start before writing 1.5.
- **Checkpoints/Revision-History UI placement inside `EditorPanel.tsx`** is a judgment call (spec #16 says "mounted as a section", matching legacy's placement) — if `EditorPanel.tsx` has grown significantly by build time (multiple concurrent sessions touch Studio panels), re-check it's still under the repo's "~100 lines per component" guidance and consider extracting a wrapper if not.
- **No isolation needed for 1.2/1.3/1.4 fan-out** — genuinely disjoint new files; only the `EditorPanel.tsx` integration step needs a fresh `git diff` immediately before editing (standard shared-file discipline on this checkout, see [[shared-file-collision-safe-staging-multi-agent-checkout]]).
