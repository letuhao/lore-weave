# RUN-STATE — S-02b + S-02c build (parts GUI: reachability + polish)

> Re-read FIRST after compaction. Shared checkout: NO `git add -A`; stage only my files; check
> `git diff --cached --name-only` before every commit (index has carried other sessions' work).
> ManuscriptNavigator.tsx + useManuscriptTree.ts + partsTree.ts + partsApi.ts + ManuscriptNavigator.parts.test.tsx
> are MINE/clean. `ManuscriptNavigator.test.tsx` is FOREIGN — do NOT touch; put my tests in the .parts.test file.

## GOAL
Evaluate + CLARIFY-seal Spec A (S-02b reachability) & Spec B (S-02c polish), then BUILD both in slices, QC each.
Done = both specs built, unit tests green (pasted), tsc clean, live smoke on the running stack (book-service :8205 + FE :5199).

## SEALED DECISIONS (do not re-litigate)

### Spec A — reachability
- **A1** Reorder = **↑/↓ move buttons only**. Drag-to-reorder acts = DEFERRED (rows already own drag-chapter-into-act; avoid drop ambiguity).
- **A2** Hook `moveAct(partId, 'up'|'down')`: swap with neighbour in active `parts`, call `partsApi.reorder`, `reload()`. ↑/↓ render only with **≥2 acts**, disabled at the boundary.
- **A3** Restore = **undo toast** (sonner, action "Undo" → `restoreAct`, **duration 10s**) **+** a **"Trashed acts" collapsible section** shown ONLY when `trashedActs.length>0`.
- **A4** Trash → **instant + undoable**; **drop `window.confirm`** (shared with B4). Toast copy notes chapters stayed / act un-filed.
- **A5** Hook adds `restoreAct(partId)` + `trashedActs: Part[]` (parallel `list({includeTrashed})`, filtered trashed, refreshed on `reload`). Restored act returns **EMPTY** (chapters NOT re-homed — S-02 sealed); UI copy says so.
- **A6** **create-into-act = DEFERRED (folded out).** Not a dead-end (create via Plan + drag works); `booksApi.createChapter` is file-upload-based, and a text-create affordance overlaps the Plan-rail contract. Conscious won't-build-now.

### Spec B — polish
- **B1** `partsMode` footer/count says **"act(s)"** (new `statActs`), never "arc".
- **B2** Create act → **inline input row** at top of act list. **Enter or blur commits** (blank = no-op), **Esc cancels**. Drops `window.prompt`.
- **B3** Rename act → **in-place inline edit** (✎ or dbl-click title → input seeded with current). **Enter/blur commits, Esc reverts.** Drops `window.prompt`. Blank rename clears title → shows "(untitled act)".
- **B4** Trash → toast (A4). No `window.confirm`, no `window.prompt` anywhere in the parts GUI after B.
- **B5** Affordances **touch/keyboard reachable**: reveal on `focus-within` + always-visible `@media (pointer:coarse)`; keep hover-reveal for fine pointer.
- **B6** **Empty-act "Drop chapters here"** muted hint row + **drag-over highlight** (`dragOverPartId` set on dragenter/over, cleared on drop/leave).
- **B7** New-act = compact **"＋ Act"** labeled button + a divider before the Plan `+`.

## SLICES (build + QC each: tsc + unit + commit)
- [ ] **S1 · reorder** — `moveAct` + ↑/↓ buttons (A1/A2). Tests: hook order math + boundary; navigator ↑/↓ gated on ≥2 acts + call.
- [ ] **S2 · restore** — `restoreAct` + `trashedActs` + Trashed-acts section + undo-toast trash (A3/A4/A5, drops confirm). Tests: toast action → restore; section lists+restores; window.confirm untouched.
- [ ] **S3 · terminology + inline dialogs** — `statActs` + inline create + inline rename (B1/B2/B3, drops prompt). Tests: footer "act"; inline commit/cancel; window.prompt untouched.
- [ ] **S4 · touch + cues + button** — focus-within/coarse visibility + empty-act hint + drag-over highlight + ＋Act (B5/B6/B7). Tests: dragOver state; empty hint; button.
- [ ] **S5 · QC/live smoke** — rebuild FE static, exercise all flows on :5199, re-score. Screenshots.

## Evidence log
- (pending)

## Registers
### Decisions: A1–A6, B1–B7 sealed above.
### Parked: create-into-act (A6) — folded, not built this run.
### Debt: (none yet)
### Evidence
- **S1 reorder (2026-07-18):** `moveAct` hook + ↑/↓ buttons. tsc=0; manuscript 123/123. Commit 4b5be039e.
- **S2 restore (2026-07-18):** `restoreAct` + `trashedActs` + Trashed section + undo-toast trash (dropped confirm).
  tsc=0; manuscript 126/126. Commit 3611eb77f.
- **S3 terminology+inline (2026-07-18):** `statActs` + inline create/rename (dropped prompt). tsc=0; 128/128. Commit a7d8d8ddc.
- **S4 touch+cues+button (2026-07-18):** focus-within/coarse affordances + empty-act hint + drag-over ring + ＋Act.
  tsc=0; 131/131. Commit b25d8448f.
- **S5 LIVE SMOKE (2026-07-18):** rebuilt book-service :8205 + isolated FE :5199, operated by hand:
  - Restore → Act I came back, Trashed section vanished, footer "2 act". ✅
  - ↑/↓ reorder → [Act I, Act II] → [Act II, Act I] (real reorder→DB→reload). ✅
  - Inline "＋Act" → typed "Act III — Aftermath" + Enter → created, input auto-closed, footer "3 act". ✅
  - Live-confirmed: "ACT" labeled button, "drag chapters here" empty-act hint, footer says **"act" not "arc"**. ✅

### RE-SCORE (post-build, live-verified)
| Metric | Audit | Now |
|---|---:|---:|
| Usability | 6.5 | **8.5** (reorder+restore reachable) |
| Completeness (CRUD) | 6 | **9** (create/read/rename/move/reorder/trash/restore all reachable) |
| Ease-of-use | 7 | **8.5** (inline edit, labeled button, undo toast) |
| Beauty | 6 | **8** (no OS dialogs, drop cues) |
| Consistency | 6.5 | **8.5** ("act" terminology, in-app dialogs) |
| Accessibility/touch | 5 | **8** (focus-within + coarse-pointer visible) |
| Robustness | 8 | **8.5** (live-verified, no console errors from S-02) |
| **Overall** | **~6.4** | **~8.4** (hit the spec's ~8.3 target) |
Deferred (conscious, A6): create-chapter-INTO-act (folded — create via Plan + drag works; booksApi.createChapter is file-based).
### Drift
- **DRIFT (2026-07-18):** concurrent commit `95e3f3b28` (plan-hub redesign) SWEPT my uncommitted
  ManuscriptNavigator.tsx ↑/↓ edits into itself (shared working tree; `git commit <file>` reads worktree).
  My code wasn't lost (HEAD has it) but Slice-1's navigator half is attributed to their commit; my hook+tests
  land in my own commit. Also: my navigator reading the new `parts` field CRASHED the FOREIGN
  ManuscriptNavigator.test.tsx (its mock omits `parts`) → fixed defensively with `parts = []` default (no edit
  to their test). Lesson reaffirmed: on a shared checkout, commit each slice's files IMMEDIATELY after QC.
