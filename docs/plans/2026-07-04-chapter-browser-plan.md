# Chapter Browser — Build Plan

> Executes [`15b_chapter_browser.md`](../specs/2026-07-01-writing-studio/15b_chapter_browser.md). PO-approved design draft + spec, now in PLAN.

## Size classification (manual — `.workflow-state.json` still off-limits, see note)

**XL.** ~18 distinct semantic changes across two services: BE (word_count migration+backfill+trigger, sort param, bulk-status endpoint, bulk-zip endpoint, search.go offset fix ≈ 8) + FE (panel shell, 2 mode-view components, arc-grouping hook, bulk-action wiring, spine wiring ≈ 6) + cross-cutting (multilingual word-count port, per-id-outcome discipline, keyset-vs-offset sort split ≈ 4). Side effects: a **DB migration + backfill** (the heaviest floor-setter — this alone would clear the L floor on its own), 2 new BE endpoints, an FE contract/enum change. First cross-service (FE+BE) task in this session's series — the prior 4 (Jobs/Books/Leaderboard/KG) were FE-only.

**`.workflow-state.json` note stands from the prior plan** — still owned by whichever concurrent effort is using it (was the KG-panels track; may have moved on by now, don't assume). Track this task's phase/evidence manually in this doc, don't invoke `workflow-gate.py` for it.

## Why BE is serial and FE fans out (asymmetric from the last plan)

The Jobs/Books/Leaderboard plan fanned out all 3 slices because they were provably file-disjoint AND none of them touched a heavily-shared, single-file surface the way this task's BE half does. Here:

- **BE (Phase A) stays ONE serial builder.** All 5 BE tasks (A1-A5) touch `services/book-service/internal/api/server.go` (new routes, `sort` param, `word_count` exposure) and/or `migrate.go` — a much smaller, more tightly-coupled codebase than the FE monorepo's spread-out panel files. Parallel agents editing the same Go file's route-registration block is a self-inflicted collision with no offsetting benefit (book-service isn't externally contended by any other known concurrent session right now, unlike the FE spine files).
- **FE (Phase B) fans out**, same shape as the prior plan: B1 (Title-view + panel shell), B2 (Content-view), B3 (arc-grouping hook) are genuinely disjoint files (per spec CB2's file-split decision) and can build in parallel. B4 (bulk-action wiring) and B5 (spine wiring) come after, since B4 needs A3/A4's real endpoints and B5 is the same serial spine-file discipline as before.

## Execution shape

```
Phase A (BE, ONE serial agent, no fan-out):
  A1 word_count migration+backfill+trigger → A2 sort param + expose word_count →
  A3 bulk-status endpoint → A4 bulk-zip endpoint → A5 search.go offset fix → A6 FE api.ts client methods
  → Go test suite (DB-gated, real Postgres per this repo's --dist loadgroup convention) → commit

Phase B (FE, parallel where independent):
  ┌─ Agent: B1 ChapterBrowserPanel + ChapterBrowserTitleView (needs A done for word_count/sort col)
  ├─ Agent: B2 ChapterBrowserContentView (independent of Phase A entirely)
  └─ Agent: B3 useChapterBrowserGroups (independent of Phase A entirely)
  → BARRIER (all 3 done) → integrate (this session, serial):
     re-diff spine files → B5 catalog/i18n/enum → B4 bulk-action wiring (needs A3/A4 client methods from A6)
  → combined FE verify (unit + tsc + dockablePanelHygiene + panelCatalogContract)
  → LIVE BROWSER E2E (this task's DOCK-11 debt from the prior 3 panels — don't skip again)
  → /review-impl → POST-REVIEW → SESSION → RETRO
```

**B2 and B3 can start immediately, in parallel with Phase A** (zero dependency). **B1 can start on its non-word-count/non-sort parts** (basic title search/filter/paging migration from `ChapterListBrowser`) but its word-count column + word-count/status sort option need A2/A6 to land first — the B1 agent should build everything else first and slot those two pieces in once A lands, rather than blocking entirely.

## Phase-agent contracts

**Phase A (single agent, foreground or long-running background — this is the critical path):**
- Full spec section "Phase A — Backend" as its task list.
- Explicit instruction: run the FULL book-service Go test suite (this repo's `-n auto --dist loadgroup` convention, DB-gated tests marked `xdist_group("pg")`) before returning — not just the new tests.
- Explicit instruction on the migration: idempotent SQL (`IF NOT EXISTS`/`OR REPLACE`, matching every existing migration in `migrate.go`), batched backfill (loop by id range, not one giant `UPDATE chapters SET word_count = ...` across a 10k+-row table), and a real multilingual test fixture (a CJK chapter + a Latin chapter) proving the char-vs-word split ports correctly from `computeReadingStats`'s TS heuristic to Go.
- Report back: exact new route paths + request/response shapes for A3/A4 (the FE agents need these to build against), confirmation the migration is backward-compatible (existing rows get `word_count=0` until backfill runs, never a NULL/error), and full test results (command + pass/fail counts, not "should pass").

**Phase B agents (3 parallel, same contract shape as the Jobs/Books/Leaderboard fan-out):**
- Each gets ONLY its file(s) from the B1/B2/B3 task rows, explicit forbidden-file list (`catalog.ts`, i18n `studio.json`×4, `frontend_tools.py`, `contracts/frontend-tools.contract.json`, `useStudioEffectReconciler.ts`), DOCK-1..11 self-check instruction, and the required structured return (catalog row, i18n keys, enum decision, test results, DOCK deviations).
- B1 additionally gets Phase A's reported route/response shapes (once available) so its word-count column can be wired without waiting for a second round-trip.
- **No worktree isolation** — same reasoning as the prior plan (disjoint files, no shared-mutation risk to protect against).

## Phase checkpoints

| Phase | State |
|---|---|
| CLARIFY | Done — design draft approved, 2 scoping questions answered (word_count IN, bulk-export zip IN) |
| DESIGN | Done — `15b_chapter_browser.md`, including the DOCK-8 analysis for why Title/Content stay one panel |
| REVIEW (design) | Done — self-review during spec-writing (investigation findings table, CB1-CB8 decisions) |
| PLAN | This document |
| BUILD | Next — Phase A (serial) → Phase B (parallel B1/B2/B3) → integrate → B4/B5 |
| VERIFY | Phase A: Go suite. Phase B: FE suite + **live browser E2E** (explicitly not skipped this time) |
| REVIEW (code) | `/review-impl` after Phase A commits, again after Phase B's combined integration commit |
| QC | Folded into the same self-review pass |
| POST-REVIEW | Human checkpoint after Phase A, and again after Phase B — never skipped |
| SESSION | `SESSION_HANDOFF.md` update at close |
| COMMIT | Phase A as its own commit(s); Phase B as B1/B2/B3 commits + one integration commit (B4+B5) |
| RETRO | `add_lesson`-worthy: the word_count trigger pattern (mirrors `fn_extract_chapter_blocks`), and the BE-serial/FE-fanout asymmetry reasoning if it proves out |

## Risk notes

- **Backfill on a real large book is the one genuinely risky operation here** — batch it, and if this repo has a live dev-DB book with thousands of chapters (check before running), test the backfill against it (or a clone) rather than only small fixtures, per this repo's own "verify against real scale, not just unit fixtures" pattern (the Manuscript Navigator spec was built the same way).
- **Bulk-status and bulk-zip are genuinely new attack/blast-radius surface** (an endpoint that mutates or reads N chapters in one call) — apply the same tenancy checks single-chapter endpoints already have (owner/collaborator-scoped), not a new looser check "because it's bulk."
- **search.go's OFFSET fix must not silently claim full pagination stability** — CB6's honesty requirement (documented caveat) is a real design decision, not a nice-to-have; verify the comment + FE copy both land, not just the code fix.
