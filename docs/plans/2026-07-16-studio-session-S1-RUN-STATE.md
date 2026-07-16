# Studio Session S1 — Manuscript & Compose — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S1 is DONE when: the scene draft loop, chapter assemble, and the correction-capture seam are OPERABLE production-ready panels — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## SCOPE
- **Persona / files:** features/studio/panels/Editor*, ComposePanel, features/composition/{compose,assemble}
- **Panels:** scene-compose, chapter-assemble
- **Seam / note:** OWNS the correction-capture seam (S6 only reads the stats).

## MANDATE (do this, in order)
1. Role-play a real web-novel author using this tool family — what must they DO?
2. Audit the CURRENT surface against that — what works, what's a skeleton, what's a dead button.
3. Per capability decide PORT / ENHANCE / BUILD — record the call, never silently drop a legacy feature.
4. Write your own detailed design (specs 31–38 are reference; the SOURCE is truth — drift is normal).
5. Build to the §2 bar. `/review-impl` at each panel close, fix what it finds.

## RULES (same-folder)
- Build only under your file subtree. Add catalog rows in your block (catalog.ts, the 8-session section).
- Shared registry (enum/contract/i18n): keep enum == openable == contract; regen `WRITE_FRONTEND_CONTRACT=1 pytest`.
- Never `git add -A`. Commit small + often. `git pull --rebase` before push. Scoped tests during BUILD.
- Stop ONLY for the 4 critical classes: destructive/irreversible · a sealed decision proven wrong ·
  tenancy/security breach · a paid action that charges the user for nothing. Everything else = defer + continue.

## SLICE BOARD  (status: TODO / DOING / DONE — DONE requires an EVIDENCE string, not a checkbox)
| slice | status | evidence (test count / live-smoke line / commit sha) |
|---|---|---|
| S1-A1 · audit current surface (role-play user) | DONE | Audit 2026-07-16: rich compose loop (ComposeView/CandidatesView/ChapterAssembleView + correction seam) lives ONLY on legacy ChapterEditorPage/CompositionPanel; studio dock `compose`=thin Chat host, `editor` inline ghost never captures correction. BE seam real+transactional (generation_corrections.py + learning-service). Publish already in studio editor. |
| S1-A2 · PORT/ENHANCE/BUILD decisions per capability | DONE | Decisions sealed below (DECISIONS register). PORT scene-compose + chapter-assemble as 2 dock panels; ENHANCE inline-ghost correction; verify publish; keep `compose`=chat; BUILD cross-panel accept→editor handoff. |
| S1-B0 · LIVE baseline (role-play author, current dock) | DONE | Live @ :5199, Claude Test, book 019f6553 (18ch): clicked Studio "Compose" → renders the CHAT box only ("Start New Chat" + model/persona), NO scene-draft loop (no scene select / Generate / candidates / accept / correction). Proves the dock author must use legacy page OR agent-via-MCP to draft. Evidence: s1-compose-is-chat-only.png. This is the §2-bar gap S1-B1 closes. |
| S1-B1 · `scene-compose` dock panel (PORT ComposeView loop) | DONE | Built+registered (catalog/enum/contract/i18n). tsc clean (only unrelated S4 MotifScopeTabs err in shared tree). Unit 6/6 (SceneComposePanel.test.tsx) + panelCatalogContract 9/9 + contract 43. **CLEAN live-smoke on ISOLATED STATIC build :5209 (no HMR): palette-open → real compose loop → Qwen ghost (1590→2066 chars) → Accept → INSERTED into Editor via editorBridge (editor 1728→3794 chars, right chapter). Tab stable, state survives tab-switch.** Bugs caught+fixed: S1-D3 forceShared (worker broke ghost on prod build), S1-D4 chapter-mismatch + false "accept again" toast. D1/D2 were HMR artifacts (8-session shared :5199). NOT committed (shared tree has other sessions' staged files — commit is PO-coordinated). Evidence: s1-accept-inserted-into-editor.png. |
| S1-B2 · `chapter-assemble` dock panel (PORT ChapterAssembleView) | DONE | Built ChapterAssemblePanel (reuse CompositionPanel soloPanel='assemble'; provider stack = PopoutHost minus forceShared). Extracted shared `useAcceptIntoEditor` hook (scene-compose refactored onto it, still 6/6). Registered (catalog/enum/contract 21/i18n). Unit 4/4 + panelCatalogContract 9/9. tsc clean (mine). **CLEAN live-smoke :5209: reachable via palette → real ChapterAssembleView (mode/generate/stitch/model, no provider crash) → 'Generate chapter' → REAL 2350-char chapter preview → Accept → inserted into Editor (3794→6144 chars).** Review (delta): shared hook pre-reviewed at B1; 1 LOW (LiveStateProvider maybe unneeded for non-streaming assemble — kept for proven popout-stack parity, accept+document). |
| S1-B3 · inline-ghost correction capture (ENHANCE useInlineGhost) | DONE | Wired `useInlineGhost` discard→correction{reject} + regenerate→correction{regenerate} (capture BEFORE re-stream mints a new jobId); accept/edit NOT captured (H2, mirrors ComposeView cowrite gate). Closes the ONE Dead capability from the audit. Unit 4/4 (useInlineGhost.correction.test.tsx), tsc clean (mine). **LIVE-PROVEN :5209: set the Work's default_model_ref (test-account has no default — CLAUDE.md caveat) → 'Continue from cursor' enabled → streamed a 1622-char inline ghost at the caret → Discard → `POST /v1/composition/jobs/…/correction => 201 Created` fired. The flywheel is closed for the editor's inline surface.** |
| S1-B4 · verify publish-chapter meets §2 bar | DONE | Publish already lives in the studio EditorPanel (EditorPublishGate). **VERIFIED live :5209: reachable (editor toolbar) → gated with a VISIBLE reason ("1 of 1 scenes not yet done", no silent fail) → marked the scene done → Publish ENABLED (gate transitions correctly) → clicked → chapter PUBLISHED (button → "Re-publish").** Meets §2 bar (operable/reachable/no-silent-fail/live). Test-data mutations on the fixture book: Work.default_model_ref set (was empty), scene marked done, chapter published — all benign + reversible on the test account. |

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
- 2026-07-16 · **Running S1 SOLO, not the 8-session parallel model.** PO chose: skip S0 scaffold
  (StubPanel + 19 pre-reserved slots) — the multi-session conflict-avoidance mechanism is moot for a
  solo run. S1 still must register its OWN panels properly (catalog row + `panel_id` enum + contract +
  `guideBodyKey`). No stubbing the other 7 sessions' slots.
- 2026-07-16 · **Cadence: STOP after audit (S1-A1) + PORT/ENHANCE/BUILD decisions (S1-A2), present to
  PO, wait for approval before building anything.** (PO: "we'll discuss what to do.")
- 2026-07-16 · **Live-browser smoke is IN PLAY** — PO confirms the stack is up (gateway :3123, FE
  :5174/:5199, LM Studio). §2 bar #7 must be met live, not deferred, for each panel close.
- 2026-07-16 · **PORT/ENHANCE/BUILD sealed (S1-A2):**
  1. **PORT** scene-compose loop (`ComposeView`+`CandidatesView`+`CandidateCard`) → new dock panel `scene-compose`. Reuse components as-is (DOCK-2).
  2. **PORT** `ChapterAssembleView` → new dock panel `chapter-assemble`.
  3. **ENHANCE** — wire `useInlineGhost` discard/regenerate → `useCorrection` so the studio editor's inline "Continue from cursor" ghost feeds the flywheel (today it generates but never posts a correction — the one Dead capability).
  4. **VERIFY** publish-chapter (already in studio `editor` via `EditorPublishGate`) against §2 bar.
  5. **KEEP** `compose` panel = thin `<Chat>` co-writer (do NOT conflate chat with the draft loop).
  6. **BUILD (small)** cross-panel handoff: `scene-compose` accept → insert into the `editor` doc via the studio host channel (loop-connected, §2 bar #6).
- 2026-07-16 · **Homing architecture:** 2 first-class sibling dock panels (`scene-compose`, `chapter-assemble`), NOT internal subtabs (DOCK-8). accept→editor via shared studio host, not co-mount.
- 2026-07-16 · **Build order:** S1-B1 scene-compose → S1-B2 chapter-assemble → S1-B3 inline-correction → S1-B4 verify publish. `/review-impl` + live-smoke at each panel close.
### PARKED  (blocker -> defer row + continue)
- 2026-07-16 · **`bookEffects.ts:60` read-thrash (NOT S1's file — flag for the book/editor track).**
  `/^composition_.*(prose|draft)/` matches the READ tool `composition_get_prose` → the effect handler
  fires on a chatty read = query-cache thrash (the exact class the ledger's READ_TOOLS assertion
  guards, but get_prose isn't listed there so it's uncaught). Fix belongs to the bookEffects owner:
  tighten the pattern to the write tools (e.g. `/^composition_write_prose|_draft/`) OR add
  composition_get_prose to READ_TOOLS to red it. I did NOT touch it (not S1's subtree). Continue.
### DEBT — post-audit triage (2026-07-17)
**No open S1 debt requires a NEW detailed spec.** Every audit finding is either FIXED, cheap-fixed, or
a legitimate CROSS-TRACK defer that belongs to another track's scope (D-5 mobile-shell / S5 what-if /
book-editor). Triage below.

#### ✅ RECENTLY CLEARED (fixed; in HEAD)
- **S1-D1 / S1-D2** — "tab jumps to Welcome" + "panel state lost" were **HMR ARTIFACTS** of the shared
  :5199 dev server (proven on the isolated static build); no code change needed.
- **S1-D3** — `forceShared` mis-borrowed from PopoutHost broke the ghost on a prod build → removed to
  match the legacy docked `LiveStateProvider`.
- **S1-D4** — accept could insert into the WRONG chapter → chapterId-match guard + honest no-editor toast.
- **GAP-2 (audit)** — accept before the Editor was open LOST the draft → `onAccept` returns boolean;
  views clear/critique/capture ONLY on a real insert; +2 guard tests. (commit f80248b19)
- **legacy-parity mapping (audit)** — compose/assemble were mapped to Chat/agent-mode → remapped to
  scene-compose/chapter-assemble (the real homes). (commit f80248b19)
- **Lane-B "blocker" (audit)** — REFUTED: the outline/scene family is already covered by `bookEffects.ts`
  (`/^composition_(outline_node|scene_link)_/`). Verified before "fixing" — nearly added a double-firer.
- **create_work/generate Lane-B (audit)** — the one REAL residual → added `compositionWorkEffect`
  (`/^composition_(create_work|generate)/` → invalidate work+outline) + ledger rows. Ledger 151 green.

#### 🔵 OPEN — cross-track defers (tracked; NOT S1 spec work)
- **Mobile (§2-bar #8) → D-5 mobile-shell track.** The panels render at 390px with no horizontal
  overflow, but the DESKTOP studio shell squishes the dock to ~100px (it doesn't collapse the nav on
  mobile — affects EVERY dock panel, not just S1). §2-bar #8 explicitly gates mobile on the D-5
  decision. Gate #3 (naturally-next-phase) + external track — the mobile-shell track owns the shell.
- **derivative adapt→Accept routing → S5 (What-If).** `useAcceptIntoEditor` keys on chapterId only;
  adapting a derivative scene + Accept may write into the canon chapter's book-scoped editor draft
  (derivatives share book_id/chapter_id under COW). UNVERIFIED — needs a live derivative-work check.
  S5 owns derivative correctness; S1 only reuses the adapt affordance. Gate #1 + gate #4. Hand to S5.
- **bookEffects read-thrash → book/editor track.** `bookEffects.ts:60` `/^composition_.*(prose|draft)/`
  matches the READ `composition_get_prose` → cache-thrash. Not S1's file (see PARKED). Gate #1.

#### ⚪ CONSCIOUS WON'T-FIX (gate #5)
- **cowriter "Use as guide" micro-integration.** The legacy CoWriterChat could seed the compose guide
  from a chat line. In the dock the `compose` Chat panel + scene-compose are separate, and
  scene-compose's guide textarea is DIRECTLY editable — a convenience, not a capability gap. The
  cowriter sub-tab itself IS homed (Chat, per the parity contract). Not worth a cross-panel bus bridge
  for a directly-typeable field. Recorded so it stops re-surfacing.
- **S1-D4 · ✅ FIXED (review-impl, fix-now) — accept could insert into the WRONG chapter.**
  onAccept trusted `getEditorTarget()` without checking `target.chapterId === activeChapterId`; a
  floated/separately-opened editor on a different chapter would receive this scene's draft. Added
  the guard + a mismatch→focusManuscriptUnit(thisChapter) path. Also fixed the no-editor toast which
  falsely said "Accept again" (ComposeView clears the ghost unconditionally, so there is nothing to
  re-accept) → now focuses the right chapter + "Generate again". Unit test added (6/6). tsc clean.
- **S1-D1 · ✅ RESOLVED — was an HMR ARTIFACT, not a real bug.** On the isolated STATIC build
  (:5209, no HMR) the dock `onReady` fired exactly ONCE (instrumented + confirmed) and the active
  tab stayed on Scene Compose across model-pick + generate. The "jump to Welcome" only happened on
  the shared HMR :5199 where a concurrent session's file edit pushed an HMR update that remounted
  the dock → onReady re-fired → `setActive('welcome')`. No code change needed. Lesson: never
  state-test on the shared HMR server with 8 sessions live. [superseded finding kept for audit]
- **S1-D3 · ✅ FIXED — `forceShared` was wrong for the in-dock panel (real bug, live-caught).** I
  had put `forceShared` on scene-compose's LiveStateProvider (mis-borrowed from PopoutHost). The
  legacy DOCKED path (WorkspaceShell.tsx:35) uses plain `LiveStateProvider` — forceShared routes the
  turn through the co-writer SharedWorker, which on a PRODUCTION build made the ghost silently never
  render (worked on dev :5199, failed on static :5209 — exactly why a prod-build smoke matters).
  Fixed: removed forceShared to match legacy. Re-verifying on rebuild.
- ~~**S1-D1 · Dock remounts→forces Welcome active on compose mutations (live-caught).**~~ (see resolution above) After a
  compose mutation (createWork / regenerate+correction) the active dock tab jumps to Welcome,
  yanking the writer out of scene-compose mid-draft. Root cause: `useStudioLayout.ts:42` calls
  `getPanel('welcome').api.setActive()` on any dock (re)mount that has a saved layout; something in
  the compose-mutation flow is remounting the dock. Blocks S1-B1 production-ready. Fix candidates:
  (a) don't force Welcome active on restore when another panel is already active; (b) stop the dock
  remount. Touches shared shell (`useStudioLayout`/`StudioFrame`) — SOLO run, so editable, but
  verify no regression to D-STUDIO-DEFAULT-WELCOME.
- **S1-D2 · CompositionPanel state (model pick + FE-local ghost) lost when the dock disposes the
  inactive panel.** dockview default `renderer:onlyWhenVisible` unmounts a hidden tab; ComposeView's
  ghost is a FE-LOCAL buffer (by design, until Accept) + modelRef is CompositionPanel session state,
  so a tab-switch mid-draft loses both. `forceShared` keeps the STREAM in the worker but NOT the
  ghost buffer. Legacy avoids this by hoisting state above the dock (WorkspaceLayout keeps all
  DockSlots mounted w/ CSS hidden). Fix candidates: keep the panel mounted (dockview keep-alive) or
  hoist the compose stream/ghost above the dock. Related to CLAUDE.md "never conditionally unmount
  stateful components".
### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- 2026-07-16 · **COMMIT RACE (shared index, no lost work).** I `git add`-ed only S1's clean files
  intending a pathspec commit, but before my `git commit` ran, S6's `git commit` (no pathspec) SWEPT
  the shared index and committed my staged files under **9c6a6d695** (studio-s6 quality-corrections).
  My own commit **420d008d8** ended up with just ja/studio.json + the NOTE message. **Net: nothing
  lost — HEAD has all my components + registration (catalog/enum/contract) + all 18 locales, and
  panelCatalogContract 9/9 passes.** The "clean partial commit" strategy is FUTILE on a shared index
  when other sessions commit without pathspec — any session's commit co-commits everyone's staged
  work. Attribution is cross-wired but functionally correct; NOT worth rebasing shared history to fix.
  Reinforces [[git-index-may-carry-prestaged-unrelated-changes]].
- 2026-07-16 · **CONFOUND: 8 sessions share the `:5199` vite dev server w/ HMR.** The S1-D1/D2
  "blockers" (dock jumps to Welcome / panel state lost) were observed on that shared HMR server — a
  concurrent session's file edit pushes an HMR update that REMOUNTS the dock (onReady re-fires →
  setActive('welcome')), which can masquerade as a compose-mutation bug. **D1/D2 are UNCONFIRMED
  until re-tested on an ISOLATED STATIC build.** Test protocol (PO directive): `vite build --outDir
  dist-s1-iso` then `vite preview --config <scratchpad>/vite.preview.s1.mjs` on **:5209** (no HMR).
  Do NOT trust :5199 for state-survival testing. `catalog.ts`/`frontend_tools.py` were seen mutating
  mid-session = other sessions' commits landing → `git pull --rebase` + no-clobber before commit.
- 2026-07-16 · Live-smoke was almost skipped in favor of "tsc+vitest green ⇒ done". It was NOT —
  the unit gate was fully green while the LIVE panel had two state-survival blockers (S1-D1/D2).
  Exactly the `agent-gui-loop-needs-live-browser-smoke` law. Bar held.
