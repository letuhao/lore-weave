# Studio Session S5 — What-If & Divergence — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S5 is DONE when: the what-if canvas is OPERABLE — not a skeleton: detail view, branch audit, judge badges, promote all work — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## SCOPE
- **Persona / files:** features/composition/{divergence,whatif}, WhatIfCanvasPanel, SceneGraphCanvas
- **Panels:** divergence (+ canonview home)
- **Seam / note:** Producer ported (O-11); the PO says it's a skeleton — MAKE IT OPERABLE. Audit-current is the biggest task.

## MANDATE (do this, in order)
1. Role-play a real web-novel author using this tool family — what must they DO?
2. Audit the CURRENT surface against that — what works, what's a skeleton, what's a dead button.
3. Per capability decide PORT / ENHANCE / BUILD — record the call, never silently drop a legacy feature.
4. Write your own detailed design (specs 31–38 are reference; the SOURCE is truth — drift is normal).
5. Build to the §2 bar. `/review-impl` at each panel close, fix what it finds.

## 🔴 PARALLEL-SESSION SAFETY (PO instruction 2026-07-16 — LOCKED, re-read after compaction)
**8 sessions run concurrently on THIS folder + branch `feat/context-budget-law`.** Working tree carries OTHER
sessions' uncommitted files. NEVER do anything that could lose their data:
- Commit DIRECTLY to `feat/context-budget-law` (no new branch, no branch switch — PO forbade switching).
- Stage ONLY my own files by EXPLICIT PATH. NEVER `git add -A`/`git add .`.
- NEVER `git stash` / `git checkout <path>` / `git reset` / `git restore` — they clobber others' uncommitted work.
- `git pull --rebase` only if pushing; check `git status` before any git op and touch only my paths.

## RULES (same-folder)
- Build only under your file subtree. Add catalog rows in your block (catalog.ts, the 8-session section).
- Shared registry (enum/contract/i18n): keep enum == openable == contract; regen `WRITE_FRONTEND_CONTRACT=1 pytest`.
- Never `git add -A`. Commit small + often. `git pull --rebase` before push. Scoped tests during BUILD.
- Stop ONLY for the 4 critical classes: destructive/irreversible · a sealed decision proven wrong ·
  tenancy/security breach · a paid action that charges the user for nothing. Everything else = defer + continue.

## SLICE BOARD  (status: TODO / DOING / DONE — DONE requires an EVIDENCE string, not a checkbox)
| slice | status | evidence (test count / live-smoke line / commit sha) |
|---|---|---|
| S5-A1 · audit current surface (role-play user) | DONE | code-trace + live drive :5174. Findings below. whatif-canvas registered (catalog.ts:217) but files live FLAT in features/composition/{components,hooks}, NOT a divergence/whatif folder. |
| S5-A2 · PORT/ENHANCE/BUILD decisions per capability | DONE | table below (PO-approved scope: FULL 5 + full prose-diff) |
| S5-B0 · BE-13a (persist derivative_name on derive; echo on /derivative-context + candidates[]) + BE-18 (settings merge patch) | DONE | works.py DeriveBody.name→settings.derivative_name + DerivativeContextResponse.name; repositories/works.py:311 `||` merge. test_repositories 115 pass (+new be18 merge test); unit routers 42 pass; validator confirmed. 1 fail (compile_run_pipeline global-pool) proven pre-existing via stash. NOT yet committed. |
| S5-B1a · EC-3c workSelect.ts (selectCanonicalWork/selectDerivatives) + fix candidates[0] at ~12 sites (hygiene grep DoD) | TODO | CROSS-SESSION per PO override 2026-07-16 |
| S5-B1b · EC-3d useActiveWork + host bus work:switch + activeWorkProjectId (per-user per-book server pref) | TODO | enables Switch-to |
| S5-B1 · `divergence` panel (fresh, reuse leaves; LIST/READ/CREATE/ARCHIVE/SWITCH-TO) + catalog row + enum + contract + guideBody + i18n | TODO | draft screen-divergence.html ①–⑥ |
| S5-B2 · `canonview` studio panel (PORT/ENH CanonAtChapterPanel standalone home) | TODO | light design, no draft |
| S5-B4 · branch prose-diff/audit — FULL HTML mockup (screen-branch-diff.html) THEN build (per-scene prose diff derivative↔source) | TODO | PO chose full mockup-first |
| S5-B5 · ENHANCE whatif-canvas to full §2 bar (Lane-B agent parity, deep-links, i18n×18, scale) | TODO | divergence create-MCP stays deferred (D-DIVERGENCE-MCP-TOOLS, Tier-W) |
| S5-B6 · convergence: live-browser smoke branch→take→promote→audit→browse; /review-impl per panel | TODO | seed scenes first |
(NOTE: B3 derivative-browser MERGED into B1 — the draft's manage list IS the browser.)

## A1 AUDIT FINDINGS (role-play: "explore an alt branch, see what's different, compare, audit, promote one")
**Surface is FAR richer than the PO "skeleton" note — that note is STALE (pre-O-11).** SceneGraphCanvas (449 LOC)
operates: start-branch → add-alt → ModelPicker → generate-take → preview ghost+judge → canon-at-branch → Promote
→ derivative (seed scenes + persist prose). Jobs 1,2,3,4,7 have working logic.
**BUT reachability is the real hole (the user's challenge, confirmed):**
- `divergence` (spawn what-if): DivergenceWizardButton mounts ONLY in CompositionPanel → only in ChapterEditorPage
  (LEGACY, dimension-② deletes it). NO catalog row / palette command / ui_open_studio_panel enum. A Studio-only
  user CANNOT create a branch via GUI — must call BE deriveWork / MCP. **Build-independent fact.**
- `canonview`: no catalog row; lives only inline in the what-if bar. Not a reachable standalone panel.
- `whatif-canvas`: IS registered on HEAD (catalog.ts:217, category 'editor', no hiddenFromPalette). Palette builds
  from catalog (useStudioCommands.ts:75-85) ⇒ WILL appear on HEAD. Live :5174 palette did NOT show it, but the
  :5174 image was built 2026-07-15 10:51 — ~23h BEFORE the row (commit e3023c775, 2026-07-16 10:15). **Stale-build
  confound, NOT a code defect.** Live-confirm pending on :5199/rebuild (deferred to B5/B6 live-smoke; needs seeded scenes).
- Backend is rich: DerivativesRepo, create_derivative, build_derivative_context, persistScenePromoteProse,
  composition_get_prose (per-scene prose = prose-diff raw material). GAP: no "list derivatives of a book" surface
  (DerivativesRepo only lists spec/overrides FOR a work) → B3 must add it (WorksRepo query + REST + MCP tool).
- Env note (NOT S5): book-list + chapter-list 502 intermittently on live; composition DB has 0 scene nodes across
  ALL projects (7 chapters total) → no fixture book is plan-populated; B6 live-smoke must SEED scenes first.

## A2 · PORT/ENHANCE/BUILD decisions (PO-approved: full scope, full prose-diff)
| capability | decision | why |
|---|---|---|
| what-if canvas (SceneGraphCanvas) | ENHANCE/verify | logic operates; must prove §2 bar #5 Lane-B, #6 deep-link, #7 live, #8 i18n×18, #9 scale → B5 |
| divergence wizard | PORT | exists+operates, only legacy-reachable → home in studio (B1) |
| canon-at-branch | PORT/ENH | CanonAtChapterPanel exists inline → standalone panel home (B2) |
| branch prose-diff/audit | BUILD | PO's core "audit" ask; no view today; full prose diff per PO (B4) |
| derivative browser | BUILD | job 6 "explore…audit…promote one" has no list surface; needs BE list route (B3) |

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
- 2026-07-16 · Scope = FULL production-ready (all 5 capabilities), branch-audit = FULL per-scene prose diff. (PO-approved via discussion.)
- 2026-07-16 · Live baseline via `vite dev :5199` on HEAD (a dev server is already up there) + reuse existing fixture books, not fresh-plan.
- 2026-07-16 · Divergence design = existing draft screen-divergence.html + spec 36 (no new spec). Only B4 prose-diff gets a NEW full HTML mockup (screen-branch-diff.html).
- 2026-07-16 · PO OVERRIDE of §5: Switch-to + EC-3c (candidates[0] fix at ~12 cross-session sites) + EC-3d are IN S5 scope. Accepts touching S1/S3/S6/S7 files. Mitigation: mechanical edits, commit small+often, hygiene-grep DoD.
- 2026-07-16 · OUT of S5: draft's ⑦ (book-settings Composition section) + ⑧ (plan-hub Beats facet) + BE-21 — other sessions' files. Divergence create-MCP stays deferred (D-DIVERGENCE-MCP-TOOLS).
### PARKED  (blocker -> defer row + continue)
- Live-smoke of whatif-canvas OPERATE path (start-branch→generate→promote): blocked on (a) 0 seeded scenes in env, (b) MCP browser profile lock at audit time. NOT a code blocker — reproduce at B6 by seeding scenes + resetting the browser profile. Continue building B1-B5 meanwhile.
### RECONCILIATION (draft screen-divergence.html + spec 36 ↔ HEAD, checked 2026-07-16)
The divergence draft is authoritative + detailed (1163 lines) but written pre-O-11 (HEAD 9262ed53e). Verified NONE of its
prereqs are built at current HEAD:
- EC-3c UNBUILT: no workSelect.ts / selectCanonicalWork / selectDerivatives. `candidates[0]` still at 28 occ / 19 files
  (draft's "12 real sites" + tests + unrelated glossary merge-candidates).
- EC-3d UNBUILT: no useActiveWork / activeWorkProjectId / work:switch on the studio bus (host/types.ts has no active-Work).
- BE-13a UNBUILT: no derivative_name anywhere (FE or BE). The wizard still collects a name and DISCARDS it.
- `divergence` panel: not built; DivergenceWizardButton mounts only in CompositionPanel (legacy).
SCOPE BOUNDARY: draft's ⑦ (Composition section in book-settings) + ⑧ (Beats facet in plan-hub) touch OTHER sessions' files
→ OUT of S5. BE-21 (model-role resolver) is ⑦'s prereq → also OUT of S5.
KEY SPLIT: LIST/READ/CREATE(+BE-13a)/ARCHIVE are safe WITHOUT EC-3c (canonical stays candidates[0] under ORDER BY created_at).
Only SWITCH-TO needs EC-3c+EC-3d, which edit ~12 cross-session files (§5 violation) → deferred as a coordinated slice.
Draft callout #4/EC-6: build a FRESH `divergence` panel reusing leaves (DivergenceWizard/DerivativeBanner/useDerivativeContext/
useWhatIfPromotion), NEVER mount CompositionPanel shell.

### DEBT
- D-S5-SWITCH-TO-EC3C — divergence "Switch to" + EC-3c (candidates[0]→!source_work_id at ~12 sites, 7 studio+4 legacy+1 BE)
  + EC-3d (useActiveWork + host bus work:switch). Cross-session (edits S1/S3/S6/S7 files) → needs coordination, not S5-solo.
  Panel ships LIST/READ/CREATE/ARCHIVE without it (no bug armed). Gate: hygiene grep `candidates[0]` absent outside tests.
### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- NEAR-MISS: I first reported the surface as "operates" from CODE READING alone — the exact trap repo law `agent-gui-loop-needs-live-browser-smoke` warns against. User challenge forced the live drive. Corrected before any build.
- NEAR-MISS: almost concluded "whatif-canvas unreachable" from the live :5174 palette — caught the STALE-BUILD confound (image 23h older than the row) before asserting it. Live-truth deferred, not faked.
