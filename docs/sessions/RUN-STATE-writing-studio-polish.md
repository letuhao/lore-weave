# RUN-STATE — Writing Studio Newcomer Polish build

> Re-read this FIRST after any compaction, then `git log`, then continue. The commitment + slice board.

## GOAL (sealed with the human, 2026-07-18)
Evaluate the spec, clear edge cases, seal open questions → then BUILD all milestones, run **review-impl**
on load-bearing slices, and **QC each slice** on an **isolated static FE build served on a dedicated
port (5290)** — never `vite dev` (4 parallel sessions' HMR cross-contaminates a shared dev server).

## HARD CONSTRAINTS (invariants — do not violate)
1. **NEVER QC on `vite dev`.** Build static (`npx vite build`) → serve `npx vite preview --port 5290
   --strictPort` (has the `/v1`→:3123 proxy). Port **5290** is THIS session's. Rebuild before each QC.
2. **QC every slice on the static build** before moving on. Unit-green is not proof.
3. **Shared checkout:** commit only THIS track's files by explicit pathspec; grep-verify nothing foreign
   is staged. 4 parallel sessions edit i18n + studio files concurrently.
4. **i18n:** any new/changed user-facing string → `en` + `scripts/i18n_translate.py` gap-fill 18 locales.
5. Backend is complete for the newcomer path — the fixes are FE-heavy; only M1's optional BE safety-net
   touches book-service (dropped — see M1 seal). No schema/route changes.

## DESIGN SOURCE OF TRUTH
- Spec + plan: `docs/specs/2026-07-18-writing-studio-newcomer-polish/{spec,plan}.md`
- Diary (symptoms): `docs/dogfood/2026-07-18-newcomer-first-book.md`
- Sealed decisions: Part/Arc rename · "Chapter {n}" default title · add real rail "New chapter".

## SLICE BOARD (done = an evidence string)
- [x] EDGE — sealed in plan.md appendix + this doc
- [x] M1 · Chapter {n} title — commit 502fdbee8. chapterDisplayTitle() shared by both mappers; 18
      locales gap-filled; 386 tests; QC :5290 'editor-<uuid>.txt' → 'Chapter 1' live.
- [x] M2 · bus manuscriptChanged → navigator reload — commit 9d62865d3. useOptionalStudioBusSelector;
      emit on write/rename/delete/childCreate; reducer+navigator tests; QC :5290 '1 ch'→'2 ch' no reload.
- [x] M3 · create doors — commit 6b02d4ec4. useChapterDoor (one home) on Editor empty / rail ＋Chapter /
      empty-rail / Plan Hub; stubbed in SideBar+Editor chrome tests; SideBar wiring assertion. QC :5290:
      rail 2→3ch+editor open; empty book editor-door → Chapter 1. F5 sealed NO-CODE (default already Simple).
- [x] M4 · auth 'Reconnecting…' chip — commit 8a74acb09. Additive lw-auth-refreshing events (api.ts,
      control flow untouched) + separate-state chip; review-impl added pointer-events-none; 34 auth+api
      tests; QC :5290 chip toggles. Sealed: transient-401 suppression needs NO code (apiJson never toasts
      a recovered 401).
- [x] M5 · Act→Part rename (EN-only; homophone is EN-specific) + Plan-tab missing-key fix + explainer
      tooltip — code commit 339a28115; i18n keys landed via parallel session's b65cec317 (they swept my
      keys — mirror hazard, no loss). QC :5290: all activity titles Title-case; rail 'Part'/'PART'.
- [x] M6 · F7b VERIFIED no-code: the "99+" badge reflects the shared test account's real seeded unread
      count (bus-driven off /v1/notifications/unread-count). A genuinely new account starts at 0 — test
      data, not a bug. F7c FLAGGED as a context-budget-law deferred row (below).

## DELIVERED (2026-07-18) — all 6 milestones shipped + QC'd on the isolated static build :5290
M1 502fdbee8 · M2 9d62865d3 · M3 6b02d4ec4 · M4 8a74acb09 · M5 339a28115 (+ i18n b65cec317). Every
newcomer-diary finding resolved or honestly sealed. Each slice: tsc 0, unit tests green, live QC on the
static build. Auth slice (M4) got the review-impl pass (found+fixed the pointer-events chip bug).

## ROUND 2 — post-fix dogfood → F8–F10 (feedback 98d6f7fb1 · design sealed ce3100a92)
Second newcomer pass on the fixed :5290 build. F1–F7 verified resolved live. Three new findings, all
FE-only, all composing around existing plumbing (usePlanOrigin, WorkSetupCta, host.openPanel):
- **F9 → "What-if versions"** (human-sealed): retire baked `Divergence (dị bản)` bilingual label.
- **F8**: Plan rail empty state is a dead door — add guided copy + "Plan this book" button.
- **F10 → "Writing setup"** (human-sealed): mount existing WorkSetupCta on noWork empty states + reword.
Spec: docs/specs/2026-07-18-writing-studio-newcomer-polish/round-2-feedback.md (M7–M9 plan at bottom).

### SLICE BOARD — ROUND 2 (done = an evidence string)
- [x] M8 · F9 kill bilingual label → "What-if versions" — en studio+composition + 6 component
      defaultValues (Divergence/SpecEditor/BranchDiff/CriticFlags/EditorPanel); deleted 5 stale keys ×
      17 locales, gap-filled via gemma-4-26b (0 failed); grep-verified no rendered "dị bản" except the
      Vietnamese locale (correct native word) + 1 code comment; tsc 0; 435 unit green; parity OK. QC
      :5290: Story Bible tab + dock panel + tab all read "What-if versions"; empty state clean.
- [x] M7 · F8 Plan rail door — PlanNavigatorRail gets `onOpenPlan` + guided empty state + "Plan this
      book" CTA (degrades to copy-only without the prop); StudioSideBar wires it to the same
      host.openPanel('plan-hub') door the Manuscript `+` uses. New planNav.emptyGuided/planCta keys,
      18-locale gap-fill. tsc 0; PlanNavigatorRail 9 tests (7+2), StudioSideBar 11. QC :5290: empty
      Plan rail shows guided copy + CTA; clicking it opens the Plan Hub dock tab (real origin flow).
- [x] M9 · F10 mounted the existing idempotent WorkSetupCta on ReferenceShelf + StyleVoice noWork
      states + de-jargoned copy ("No writing project yet — set up a Work" → "Writing isn't set up for
      this book yet — set it up…"). WorkSetupCta vocab unified "co-writer"→"writing" (button + the two
      toasts, via review-impl below). AI "Co-writer Chat" deliberately untouched (sealed: distinct
      concept). 3+2 keys gap-filled 18 locales. tsc 0; 2128 studio+plan-hub+composition tests green;
      parity OK. QC :5290 VERIFY-BY-EFFECT: Reference shelf noWork → "Set up writing" → clicked →
      Work created → empty state replaced by the real shelf ("No references yet — add influences"),
      0 console errors. review-impl: found+fixed the button/toast vocab drift.
Build order: M8 → M7 → M9 — ALL SHIPPED. Each: tsc 0, unit green, live QC on the static build.

## DELIVERED — ROUND 2 (2026-07-18)
M8 9d7911bb5 · M7 baaa30bd8 · M9 8fbf76c02. All three round-2 findings fixed, each QC'd on the
isolated static build :5290. F8/F9/F10 resolved; the divergence/whatif "no plan → plan door" nicety
deferred (below).

## DEFERRED (gate-eligible — carry forward)
- **F7c — chat co-writer context bloat** (gate #2 structural / belongs to another track). A 2-sentence
  creative ask sent ~22.6k input tokens (48 tools + 5 skills + ~12.9k tok preloaded for EVERY message).
  Free on local models; a money-burner on paid BYOK. Fix = a "light" context mode for plain creative
  chat, or lazy tool/skill-schema load. **Target track: `context-budget-law`.** Not built here.
- **Non-EN Act→Part**: EN renamed to "Part"; other locales keep their concept translation (the homophone
  is EN-specific). Conscious won't-fix (gate #5) unless a locale reviewer flags a real collision.
- **Divergence/WhatIf "no plan yet" → plan door** (gate #1 out-of-scope of F10's Work-gate + gate #2
  needs prop-threading through DivergencePanel): the M9 plan floated giving these a "Plan this book"
  door like M7/F8, but DivergenceManagerView is a `{bookId,token}`-only render component with no host
  access, and its copy is ALREADY guided ("lay out its arcs and chapters first…") — a real dead-end
  fix (M7) it is not. Folded into F6's unify-the-hierarchies "one shared plan door" track. Not built.

## REGISTERS (append as you go — an empty drift log at the end is dishonest)
### Decisions
- (EDGE) M1 is FE-ONLY: the `editor-<uuid>.txt` leak is `title || original_filename` in two pure mappers
  (`useManuscriptTree.chapterToNode:23`, `partsTree.chapterTitle:20`). Fix → `title || "Chapter {n}"`
  (localized via the i18n singleton). BE default-title change DROPPED (no need; avoids injecting a
  non-localized English title for MCP callers — the display layer owns the fallback).
### Parked / blocked
- (none yet)
### Debt
- (none yet)
### Drift / near-misses
- FLAKE (M2): `panelCatalogContract.test.ts` red once in a combined run (reads en/studio.json from
  disk mid-parallel-session-write), green in isolation (9/9). Not mine — shared-checkout timing.
- CAUGHT EARLY: F5 ("Advanced default") is NOT a code bug — code default is `simple=true`; the shared
  test account carried a persisted `plan_hub_mode_simple=false`. Reframed as a planless-book hardening
  nicety (M3), not a bug fix. Recorded so it isn't "fixed" as if it were broken.
- CLOBBER (M9): a parallel session ran a working-tree restore (right before committing their
  `a43947f97` completeness-audit) that WIPED my uncommitted M9 edits to StyleVoiceStudioPanel +
  WorkSetupCta (ReferenceShelf survived — was mid-edit). Caught by the file-changed system reminders +
  `git status`. Re-applied all three, tsc-verified they stuck (one-time cleanup, not a loop), staged
  early to shrink the window, then committed. Lesson reinforced: on this shared checkout, commit each
  slice promptly — uncommitted work is fair game for another session's `git restore`.
- review-impl (M9): the WorkSetupCta button rename "co-writer"→"writing" left its own error/pending
  TOASTS still saying "co-writer" — same-component vocab drift. Fixed both toasts + gap-filled.
