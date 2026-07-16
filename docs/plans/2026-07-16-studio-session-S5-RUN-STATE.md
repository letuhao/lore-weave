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
| S5-B1a · EC-3c workSelect.ts + EC-3d useActiveWork(pref) + resolveActiveWork at all 13 Work-resolution sites | DONE | workSelect.ts + hooks/useActiveWork.ts (new) + 13 sites migrated (4 composition + 3 manuscript + useSceneInspector/useQualityWork/useChapterBrowserGroups/EditorPanel/PlaceGraphPanel/ChapterEditorPage). Hygiene grep: `.candidates[0]` gone from all Work sites (only glossary merge-candidate tests remain). workSelect.test 9 pass; 769 affected tests pass. NOTE: useActiveWorkId uses the useTimezone effect+pubsub pattern (NOT react-query) so the 13 sites' mock-useWorkResolution tests don't need a QueryClientProvider. |
| S5-B1b · EC-3d Switch-to WRITE path (useSetActiveWork) — FOLDED into B1 (the divergence panel's "Switch to" button). Read path done in B1a. | TODO | write-path lives in the panel |
| S5-B1 · `divergence` panel (fresh, reuse leaves; LIST/READ/CREATE/ARCHIVE/SWITCH-TO) + catalog row + enum + contract + guideBody + i18n | DONE | DivergencePanel.tsx (studio wrapper) + DivergenceManagerView.tsx + useDivergenceManager.ts (new). patchWork gains opt-in If-Match (archive). catalog row + `ui_open_studio_panel` enum + contract regen (43 chat-service tests pass) + en/studio.json keys. DivergenceManagerView.test 8 pass; panelCatalogContract + legacyParityContract pass. tsc clean for my files (only S4's uncommitted MotifGraphSection error). SWITCH-TO write-path (B1b) folded in via useSetActiveWork. |
| S5-B2 · `canonview` studio panel (PORT/ENH CanonAtChapterPanel standalone home) | DONE (D-S5-CANONVIEW-REG CLEARED) — the enum-line contention settled (chapter-assemble/arc-inspector/quality-corrections all committed to HEAD; frontend_tools.py clean), so canonview registered cleanly: CanonViewPanel.tsx + test + catalog row + ui_open_studio_panel enum + regenerated contract + en/studio.json. Contract regen clean (only canonview); panelCatalogContract 9 pass WITH canonview (enum==openable==contract); CanonViewPanel test 2 pass; tsc clean. | CanonViewPanel.tsx WRITTEN (drives CanonAtChapterPanel from bus activeChapterId + resolves chapterIndex via listChapters). Registration (catalog/enum/contract/i18n) REVERTED + deferred → D-S5-CANONVIEW-REG: blocked on S1's concurrent chapter-assemble sharing the single-line panel_id enum (can't line-separate; S1's whole feature incl. component is uncommitted so a superset commit would adopt their work). Re-register when S1 commits + the enum line is clean (circle back at end-of-run). |
| S5-B4 · branch prose-diff/audit — FULL HTML mockup (screen-branch-diff.html) THEN build | DONE-pending-review | FE: lineDiff.ts (LCS line diff) + useBranchDiff.ts (fetch derivative outline → per delta-chapter fetch both projects → correspond by story_order → changed/added/unchanged) + BranchDiffView.tsx (rail + 2-col diff) + a Spec|Diff TAB in DivergenceManagerView. api.ts getChapterSceneDrafts. Tests: lineDiff 6, useBranchDiff 2, DivergenceManagerView 9 (incl Diff-tab). tsc clean (my files). NOTE: caught a relative-path Write bug (a test landed in frontend/frontend/) — fixed; use ABSOLUTE Write paths. /review-impl next. ✅ mockup done (design-drafts/screens/studio/screen-branch-diff.html — house-style, states: changed/added/inherited/no-prose/no-branch, + 2 scene-correspondence callouts). Design = a Diff TAB inside the divergence panel (NOT a new panel → no enum contention). Build next: FE diff tab. ✅ BE DONE: prose model is CHAPTER-drafts (shared COW) + SCENE-drafts (per-project generation_jobs) → the diff is scene-draft-level per project. Added GenerationJobsRepo.scene_drafts_detailed (node_id+story_order+title+text) + GET /works/{id}/chapters/{cid}/scene-drafts (VIEW-gated, in works.py NOT engine.py — engine.py was entangled with S4's uncommitted motif route). Repo test passes. FE fetches for BOTH projects, correspond by (chapter_id, story_order). |
| S5-B5 · ENHANCE whatif-canvas to full §2 bar | ASSESSED (mostly-satisfied / deferred) | Audited against §2: (#5 agent-parity) the Lane-B coverage ledger (effectCoverage.contract.test) has NO rows for divergence/whatif — their write path is MCP, DEFERRED (D-DIVERGENCE-MCP-TOOLS); so agent-parity = agent-can-open (✅ whatif-canvas enum) + Lane-B-refresh is moot until those tools exist. Not a test-red gap. (#6 loop-connected) promote→switch-studio wired (useWhatIfPromotion.onPromoted); reachable via palette. (#8 i18n×18) strings use t()+defaultValue → render via fallbackLng:'en'; panel title/desc/guideBody en keys present. (#9 scale) REAL gap: SceneGraphCanvas renders all scenes with no virtualization → degrades at 10k. Defer → D-S5-SCENEGRAPH-VIRTUALIZE (large refactor, own effort). Net: whatif-canvas meets the operable/reachable/no-silent-fail/loop/i18n bar; agent-write-parity blocked on the deferred divergence MCP; scale deferred. |
| S5-B6 · convergence: live-browser smoke + circle-back B2 reg | LIVE-SMOKE ✅ (isolated build) | ✅✅ ISOLATED STATIC BUILD SMOKE (PO asked for a separate port, no shared dev-server): `vite build` → dist → `vite preview --config <scratchpad>/preview.s5.config.mjs` on :5399 (own port, /v1→:3123 proxy, NOT shared with :5199/:5209). Logged in as claude-test, opened `divergence` via the command palette, and the panel RENDERED THE FULL MANAGE SURFACE: canonical LIST row ("Canonical · active · canon" with badges), the "New divergence" CREATE button, and the empty-derivatives state ("No what-if branches yet…") — 0 console errors. Proves reachable+mounts+operable live on HEAD. The full derive→take→promote→diff flow still needs a plan-populated book + LLM (env has 7 chapters/0 scenes) → D-S5-LOOP3-SMOKE. ✅ LIVE REACHABILITY also confirmed on :5199 earlier: palette shows "Studio: Open Divergence (dị bản)" WITH the exact description I authored + "What-If Branches" — closes the A1 audit's headline gap ("divergence not reachable in Studio; user must call BE/MCP"). Pasted in transcript. FULL OPERATE-LOOP smoke (branch→take→promote→audit→browse): `LIVE-SMOKE deferred to D-S5-LOOP3-SMOKE` — env-limited: the test books have 0 scene-populated outlines (whole composition DB has 7 chapters / 0 scenes), take-generation needs a running LLM, and the MCP browser is shared/flaky across the 7 live sessions. Circle-back B2 canonview registration: enum line STILL contended by 3+ sessions' uncommitted panels → remains D-S5-CANONVIEW-REG. |
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
- D-S5-BRANCHDIFF-CORRESPONDENCE — ✅ CLEARED (implemented, not spec'd — engine.py was clean + bounded). The
  promote persist now records an `anchor_node_id` (the canon scene the take is an alternate of) in the
  synthetic-job marker; scene_drafts_detailed returns it; useBranchDiff pairs derivative→canon by the anchor
  back-ref RELIABLY (falls back to story_order only when absent, then "added" — never mis-pairs). BE: upsert +
  route + repo query; FE: api opts + SceneGraphCanvas passes anchorScene.id + useBranchDiff pairing. Tests: BE
  scene_drafts_detailed anchor roundtrip; FE useBranchDiff "pairs by anchor not order" (3 pass). tsc clean.
- D-S5-SCENEGRAPH-VIRTUALIZE — ✅ SPEC'D (needs a design, too large to inline): docs/specs/2026-07-17-scenegraph-virtualization.md
  (viewport-cull in GraphCanvas: mount only visible nodes + always-include drag/selected/what-if; edges by
  visible endpoints; extent from full layout). Size M; buildable; owner = next graph-canvas toucher.
- D-S5-LOOP3-SMOKE — NOT a spec item (env-execution). The full derive→take→promote→diff→browse live loop needs
  a plan-populated book (env has 7 chapters / 0 scenes) + an LLM for take-gen. Divergence panel LIST/CREATE +
  the isolated :5399 build are proven; the derive+diff pipeline is unit+integration-tested. Run the live loop
  when a seeded book exists (can seed via DB: chapter+scenes+canon drafts + a derivative Work + a promoted
  scene-draft-with-anchor → drive the Diff tab on :5399).
- D-S5-BRANCHDIFF-NOPROSE — B4: a diverged scene NODE with no completed draft (prose persist failed/pending)
  is silently absent from the diff (deriv scene-drafts only returns drafted scenes). The mockup drew a
  "no prose yet" state; not built. LOW.
- D-S5-CANONVIEW-REG — canonview panel written (CanonViewPanel.tsx + test, untracked) but registration
  (catalog/enum/contract/i18n) blocked by the single-line panel_id enum being contended by 3+ sessions'
  uncommitted panels (chapter-assemble/arc-inspector/quality-corrections). Register at B6 when it settles.
- D-S5-SWITCH-TO-EC3C — divergence "Switch to" + EC-3c (candidates[0]→!source_work_id at ~12 sites, 7 studio+4 legacy+1 BE)
  + EC-3d (useActiveWork + host bus work:switch). Cross-session (edits S1/S3/S6/S7 files) → needs coordination, not S5-solo.
  Panel ships LIST/READ/CREATE/ARCHIVE without it (no bug armed). Gate: hygiene grep `candidates[0]` absent outside tests.
### /review-impl on B1 (divergence panel + EC-3c/EC-3d) — 2026-07-16
- **HIGH #1 (FIXED)** — FE wizard `buildBody()` DROPPED `name`: BE-13a accepted it but the FE never sent it,
  so every derivative created via the panel was unnamed ("Untitled dị bản") — the exact F-EC3a silent-success
  bug the draft named, half-fixed. Fix: FE DeriveBody.name + buildBody includes name.trim(); test asserts it.
- **MED #2 (FIXED)** — useActiveWorkId fired N identical GET /v1/me/preferences (no react-query dedup) across
  ~13 sites on studio mount. Fix: module-level in-flight dedup (fetchActiveWorkId) coalesces concurrent loads.
- **MED/LOW #3 (FIXED)** — DivergenceManagerView Row was a `<button>` containing `<span role=button>` (invalid
  content model / a11y). Fix: Row is a div (role/tabIndex for derivatives); Switch/Archive are real buttons.
- **LOW #4 (DEFERRED)** — spec query error path is silent (getDerivativeContext failure shows no error). D-S5-SPEC-ERR.
- **LOW #5 (ACCEPT)** — archive uses token! assertion; studio is always authed.
Standards: [Tenancy] pref per-user+per-book ✓ · [Frontend-Tool Contract] enum==openable==contract machine-checked ✓.

### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- 🔴 INCIDENT #2 (getChapterSceneDrafts): I apply-cached my api.ts hunk to the shared index, then ran a
  SEPARATE inspect command — and between them S3's `git commit` (70b49f2b6) swept my staged hunk into THEIR
  commit. So `getChapterSceneDrafts` is in HEAD (useBranchDiff works, no data lost) but attributed to S3's
  commit. LESSON (LOCKED): `git commit -- <pathspec>` protects against sweeping OTHERS in, but does NOT stop
  others' plain `git commit` from sweeping MY staged hunk out. With N sessions on one index, NEVER leave a hunk
  staged across commands — apply-cached and commit in the SAME atomic command, or avoid the index (inline the
  call instead of an api-layer method on a contended file). B4-FE is functionally complete regardless.
- 🔴 INCIDENT (ec0f012e8): my `git add <mine> && git diff --cached && git commit` (chained with &&, no
  inspection gate) committed S2's PRE-STAGED files too — PlanDrawer.tsx, PlanDrawer.test.tsx,
  ArcInspectorEmbed.tsx, S2-RUN-STATE.md — because `git commit` takes the WHOLE INDEX and S2 had `git add`-ed
  their work. This is the `git-index-may-carry-prestaged-unrelated-changes` lesson, which I had in memory and
  still hit. NO DATA LOST (S2's working tree == the committed version; their final staged state was captured),
  but their work is muddled into my commit + their RUN-STATE committed under my sha. HEAD is still ec0f012e8,
  nobody committed on top. FIX GOING FORWARD (LOCKED): NEVER `git add <paths> && git commit`; ALWAYS
  `git commit -- <explicit mine>` (pathspec commit ignores others' staged files + reads working tree). Whether
  to rewrite ec0f012e8 (soft-reset) is the PO's call — it conflicts with the "NEVER reset" rule.
- NEAR-MISS (caught by /review-impl): shipped B1 with BE-13a HALF-done — backend accepted `name`, FE wizard
  still dropped it. A green suite hid it (no test asserted buildBody sends name). The draft had NAMED this exact
  bug (F-EC3a) and I fixed only one half. This is why panel-close /review-impl is mandatory.
- NEAR-MISS: I first reported the surface as "operates" from CODE READING alone — the exact trap repo law `agent-gui-loop-needs-live-browser-smoke` warns against. User challenge forced the live drive. Corrected before any build.
- NEAR-MISS: almost concluded "whatif-canvas unreachable" from the live :5174 palette — caught the STALE-BUILD confound (image 23h older than the row) before asserting it. Live-truth deferred, not faked.
