# Utility Panels — Fan-out Build Plan

> Executes [`14b_utility_panels.md`](../specs/2026-07-01-writing-studio/14b_utility_panels.md) (Jobs / Books Browser+Reader / Leaderboard dockable migration). PO-approved spec, now in PLAN.

## Size classification (manual — see note)

**XL** by this repo's rubric: ~15 distinct semantic changes (Jobs: 2 panels + injectable-prop refactor + enum ≈5; Books: 2 hook extractions + 2 panels ≈4; Leaderboard: 1 hook extraction + 4 panels + DOCK-8 split ≈6) across ~27 files, with 3 side effects (BE enum change, i18n ×4 locales, a standards-adjacent DOCK-1..11 compliance surface). Per `CLAUDE.md`'s table this needs a written plan (this doc) + spec (already written); subagent fan-out is recommended, not just allowed.

**⚠️ Not tracked via `.workflow-state.json` / `scripts/workflow-gate.py`.** That file is gitignored (shared per-checkout local state, not per-session) and is **currently owned by the concurrent KG-panels effort** (`docs/specs/2026-07-01-writing-studio/14a_kg_panels.md`, confirmed mid-BUILD, phase `build`, size XL). Running `workflow-gate.py size`/`phase` for this task would clobber that in-progress state. This plan tracks phase/evidence manually instead; do not invoke the gate script for this task while the KG effort is active on this same checkout.

## Why fan-out is safe here

Per [[fanout-independent-slices-parallel-build-serial-integrate]]: fan-out works when slices are **provably disjoint files**. Verified:

| Slice | Files touched (feature code) |
|---|---|
| **Phase B — Jobs** | `features/jobs/**` (existing: `JobRow.tsx`, `JobMonitor.tsx`, `components/mobile/JobsMobile.tsx` — prop addition only), new `features/studio/panels/{JobsListPanel,JobDetailPanel}.tsx` |
| **Phase C — Books** | `pages/BooksPage.tsx`, `pages/ReaderPage.tsx`, new `features/books/hooks/{useBooksList,useBookReaderContent}.ts`, new `features/studio/panels/{BooksBrowserPanel,BookReaderPanel}.tsx` |
| **Phase D — Leaderboard** | `pages/LeaderboardPage.tsx`, new `features/leaderboard/hooks/useLeaderboardList.ts`, new `features/studio/panels/Leaderboard{Books,Authors,Translators,Trending}Panel.tsx` |

Zero overlap across the three — different directories, different existing files, different new files. The **only** shared surface is the 4 spine files (`catalog.ts`, 4× `studio.json`, `useStudioEffectReconciler.ts`, `contracts/frontend-tools.contract.json`+`frontend_tools.py`) — per the spec's Coordination section, phase-agents **do not touch these**; a serial integration step applies all spine additions afterward, re-diffing first to avoid clobbering the concurrent Glossary Phase B / Inspector GUI / KG-panels efforts also appending to them.

## Execution shape

```
        ┌─ Agent: Phase B (Jobs)        ─┐
PARALLEL ├─ Agent: Phase C (Books)        ├─→ BARRIER (all 3 done)
        └─ Agent: Phase D (Leaderboard) ─┘
                                             │
                              Integration (serial, this session — the ONLY serial part):
                              1. re-diff catalog.ts / studio.json×4 / frontend_tools.py / contract.json
                              2. apply Phase B's spine additions → run Jobs-scoped tests + tsc → commit
                              3. re-diff again → apply Phase C's spine additions → Books-scoped tests → commit
                              4. re-diff again → apply Phase D's spine additions → Leaderboard-scoped tests → commit
                              5. ONE combined full-suite verify (all 3 phases together)
                                 + dockablePanelHygiene + panelCatalogContract
                              6. /review-impl over the combined 3-commit diff
                              7. POST-REVIEW — present to human, WAIT (never skippable)
                              8. SESSION_HANDOFF.md update + RETRO
```

### Phase-agent contract (all 3 agents get this shape)

Each phase-agent is briefed with:
- Its exact task rows from `14b_utility_panels.md` (B1-B3/B6-B7 for Jobs; C1-C4 for Books; D1-D2/D5 for Leaderboard) — the catalog/i18n/enum rows (B4-B5, C5-C6, D3-D4) are **excluded**, replaced by an instruction to return a structured manifest instead.
- Explicit list of forbidden files: `features/studio/panels/catalog.ts`, `frontend/src/i18n/locales/*/studio.json`, `services/chat-service/app/services/frontend_tools.py`, `contracts/frontend-tools.contract.json`, `features/studio/agent/useStudioEffectReconciler.ts` — "if your task seems to need one of these, STOP and report it in your manifest instead of editing it."
- Instruction to run its own phase-scoped tests (`vitest run <its new/changed files>` + relevant existing suites) before returning, and to report pass/fail honestly — not to assume they'll pass.
- The DOCK-1..11 checklist reference (`docs/standards/dockable-gui.md`) so it self-checks compliance (register/self-title/route-decoupled/no-fork/no-hand-rolled-overlay) before returning.
- Required return shape: **(a)** a one-paragraph summary of what was built + any deviation from the spec (and why), **(b)** the exact catalog.ts row(s) to add (id, component var name + its import line, titleKey, descKey, hiddenFromPalette), **(c)** the exact i18n key/value sets needed per locale (en authoritative; ja/vi/zh-TW may be machine-translated placeholders the human can refine), **(d)** whether an agent-enum row is needed (only Jobs' `jobs-list` per U5) and its exact enum value, **(e)** test results (command run + pass/fail counts), **(f)** any DOCK-standard deviation found and how it was resolved.

### Isolation choice

Phase-agents run **without** `isolation: 'worktree'` — they touch fully disjoint files in the existing working tree, and worktree isolation would add setup cost for no real benefit here (no shared-file mutation to protect against, unlike the spine-file integration step which stays serial in the main session precisely because it DOES need up-to-the-moment `git diff` state). Each agent still avoids running long-lived dev servers/watchers that could collide on ports.

## Phase order — corrected: all 3 run in parallel, one round

**Original draft staggered Jobs solo before Books+Leaderboard "to de-risk the pattern first" — that reasoning doesn't actually hold up** (caught in review): the injectable-prop convention is Jobs-specific (`JobRow`/`JobMonitor`), Books uses `host.openPanel` directly, Leaderboard has no navigation surface at all — there's no shared pattern that benefits from being proven sequentially. The three slices are already verified file-disjoint. The only genuinely serial part is **integration** (spine-file edits need a fresh `git diff` immediately before each apply) — that constraint applies to *how I merge results*, not to *when the agents build*.

**Corrected shape: launch all 3 phase-agents in parallel, single round.**

1. **Build (parallel):** Phase B + Phase C + Phase D agents launched together.
2. **Integration (serial, after all 3 return):** apply each phase's spine additions in turn (B → C → D, order arbitrary — just not simultaneous), re-diffing the 4 spine files immediately before each apply. 3 separate commits (git hygiene — each stays independently revertable/bisectable), but...
3. **ONE combined verify + `/review-impl` + POST-REVIEW** across all 3 phases' results (per the spec's own C+D combined-gate precedent, extended to include B too since everything lands in the same sitting now) → SESSION → RETRO.

## Phase checkpoints (mapped to the 12-phase workflow)

| Phase | This task's state |
|---|---|
| CLARIFY | Done — 2 rounds of `AskUserQuestion`, PO-approved 2026-07-04 |
| DESIGN | Done — `14b_utility_panels.md`, including the DOCK-12→dropped correction |
| REVIEW (design) | Done — self-review during spec-sealing (structural-mismatch findings, DOCK-7/8 analysis, coordination section) |
| PLAN | This document |
| BUILD | Next — all 3 phase-agents launched together |
| VERIFY | Per-phase tests during build; one combined full-suite verify at integration close. Evidence = actual test command + output, not "should pass" |
| REVIEW (code) | ONE `/review-impl` pass over the combined 3-commit diff |
| QC | Folded into the same self-review pass (no separate QA persona available) |
| POST-REVIEW | **One human checkpoint after all 3 phases integrate — present summary, STOP, WAIT.** Never skipped. |
| SESSION | `SESSION_HANDOFF.md` update after integration closes |
| COMMIT | Per-phase commits (B; C; D) as scoped above, not one giant commit |
| RETRO | `add_lesson` if anything non-obvious surfaces (e.g. the `ReaderPage` hook-extraction shape, the spine-file coordination pattern) |

## Risk notes

- **Spine-file drift risk is real and active** — the KG-panels effort is mid-BUILD *right now* per `.workflow-state.json`. Before each integration step (not just once at plan time), re-run `git diff` on the 4 spine files to see what's already landed from other concurrent work, and append past it rather than assuming this plan's snapshot of those files is still current.
- **`ReaderPage.tsx` extraction (C3) is the single largest unknown** — it's the one task in this plan comparable in size/risk to Glossary Phase A's `useGlossaryEntity` extraction. If the Phase C agent finds the hook boundary is messier than expected (e.g. TTS auto-scroll coupling to content-fetch timing), it should report that honestly in its manifest rather than force a fit — this is exactly the kind of thing the injected review pass exists to catch.
- **No isolation ⇒ no protection against a bad edit outside the stated file list.** Each phase-agent's diff should be spot-checked at integration time to confirm it touched only its declared files before applying spine additions on top.
