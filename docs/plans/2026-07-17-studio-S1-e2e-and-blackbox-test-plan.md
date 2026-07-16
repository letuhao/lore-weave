# S1 · Manuscript & Compose — E2E + Blackbox Usability Test Plan

> Follows the S1 build (scene-compose, chapter-assemble, inline-ghost correction, publish). Build is
> DONE + live-proven (manual Playwright-MCP) + unit-tested, but there are **no committed E2E specs**
> for the studio-dock surface. This plan closes that: (A) automated Playwright coverage of every S1
> capability + §2-bar dimension, and (B) a blackbox user-role usability pass on the REAL app.

## 0 · Where things stand
- **S1 build DONE:** B1 scene-compose, B2 chapter-assemble, B3 inline correction, B4 publish — all
  live-proven on the isolated static build; unit tests green (SceneCompose 6, ChapterAssemble 4,
  useInlineGhost.correction 4, ComposeView/ChapterAssembleView guard tests, effectCoverage 155,
  panelCatalogContract 9, legacyParityContract 3). Completeness audit done; debts cleared/handed off.
- **Gap this plan fills:** the studio-dock compose loop has NO committed `tests/e2e` spec. Existing
  composition specs (`composition-generate/journey/publish-lifecycle/flywheel/...`) test the LEGACY
  ChapterEditorPage, not the dock panels.

## 1 · Repo E2E conventions we MUST match (tests/e2e/CONVENTIONS.md)
- **@playwright/test**, run via `npm run e2e` (config `playwright.config.ts`); specs in `tests/e2e/specs/<scope>-<intent>.spec.ts`.
- **`data-testid` only** (i18n/style-agnostic). Never getByText for assertions of dynamic content.
- **Page Object Model** — no raw selectors in specs; all UI via a PoM in `tests/e2e/pages/`.
- **Web-first waits** — `expect(locator).toBeVisible()`, `expect.poll`, `waitForResponse`; NO `waitForTimeout`.
- **Real LLM, MODEL-GATED** — `test.skip(models.length<n, 'needs LM Studio + N models')`; `test.setTimeout(180_000)`; poll `ghost.innerText().length > 20`. (Mirror `composition-generate.spec.ts`.)
- **Self-contained data** — each test creates its book/chapter/work/scene via `helpers/api.ts` + `trashBook` at the end.
- **Test account** `claude-test@loreweave.dev` / `Claude@Test2026`.

## 2 · Infra to ADD (small)
1. **PoM `pages/StudioComposePanels.ts`** — wraps the S1 dock panels. Reuses `StudioPage` for
   `goto`/`openPanel`/palette. Locators are the panels' existing testids scoped under the panel root:
   - scene-compose: `studio-scene-compose-panel`, `composition-scene-select`, `composition-add-scene`,
     `composition-mark-done`, `composition-model-select`, `compose-generate`, `compose-stop`,
     `compose-ghost`, `compose-accept`, `compose-regenerate`, `compose-discard`, `compose-diverge-toggle`,
     candidates (`candidate-card` / `candidate-use` / `candidate-edit`), `compose-adapt`.
   - chapter-assemble: `studio-chapter-assemble-panel`, `assemble-mode-per_scene|chapter`,
     `assemble-generate-chapter`, `assemble-stitch`, `assemble-preview`, `assemble-accept`,
     `assemble-regenerate`, `assemble-reject`, `assemble-error`, `assemble-degraded`.
   - editor + inline ghost: `studio-editor-panel`, `.tiptap-content`, `inline-continue`, `inline-ghost-text`,
     `inline-accept`, `inline-edit`, `inline-discard`, `publish-button`, `studio-editor-open-*`.
   - Methods: `openSceneCompose()`, `openChapterAssemble()`, `pickModel(id)`, `generate()`,
     `acceptGhost()`, `editorText()`, `continueFromCursor()`, `discardInline()`, etc.
2. **api helper `setWorkDefaultModel(request, token, projectId, modelRef)`** (PATCH `/v1/composition/works/{id}`
   `{settings:{default_model_ref}}`) — needed to ENABLE the editor's inline "Continue from cursor"
   (`canContinue` needs a resolved default model; the test account has no `user_default_models`).
   Mirror the existing `setWorkCriticModel`.
3. (Assert corrections via `page.waitForResponse(/\/jobs\/.+\/correction/)` — no new helper needed.)

## 3 · Part A — automated E2E specs (coverage of every S1 capability + §2-bar dimension)

### A1 · `studio-compose-reachability.spec.ts` — FAST, NO MODEL (always runs, CI-cheap)
The §2-bar #2/#3 regression that does NOT need an LLM:
- scene-compose + chapter-assemble appear in the Command Palette (reachable).
- Opening each mounts the REAL panel (not a skeleton): scene-compose shows the scene selector + model
  picker + Generate; chapter-assemble shows the mode toggle + Generate chapter + Stitch. (guards the
  "cho có" skeleton failure.)
- Both are in the User Guide panel with non-empty guide copy (guideBodyKey).
- Close + reopen a panel (dockview unmount/remount) without crash.

### A2 · `studio-scene-compose.spec.ts` — [model-gated] the scene draft loop
| # | Scenario | §2-bar |
|---|---|---|
| 1 | Generate (V0 stream) → ghost streams (poll >20) → Accept → the accepted prose appears in the Editor panel doc | #1 operable, #6 loop-connected, #7 proven |
| 2 | Diverge ON → candidate cards render → Use/Edit a candidate → prose in editor | #1 |
| 3 | Regenerate / Reject → `waitForResponse(/jobs/.+/correction)` fires (the flywheel — S1 OWNS the seam) | #1, #5 |
| 4 | **GAP-2 guard**: close the Editor tab → Generate → Accept → the ghost is NOT cleared (draft kept) + a toast; reopen Editor → Accept → lands | #1, #4 no-silent-fail |
| 5 | Chapter-mismatch guard: editor on chapter B, scene-compose on chapter A → Accept does NOT write into B (focuses A) | #4 |

### A3 · `studio-chapter-assemble.spec.ts` — [model-gated]
| # | Scenario | §2-bar |
|---|---|---|
| 1 | Generate chapter → editable preview (poll) → Accept → prose in Editor | #1, #6 |
| 2 | Mode toggle per_scene↔chapter persists (patchWork) | #2 |
| 3 | Stitch gate: disabled while a scene is not done → `setSceneStatus(done)` all → Stitch ENABLED → stitch → preview | #1, #4 |
| 4 | Coded error surfaced: assemble with no chapter plan → `assemble-error` shows the NO_CHAPTER_PLAN reason (no silent fail) | #4 |
| 5 | Regenerate / Reject → correction POST fires | #5 |

### A4 · `studio-inline-correction.spec.ts` — [model-gated] the editor's inline flywheel (S1 B3)
Setup: `setWorkDefaultModel(...)` so `inline-continue` enables.
| # | Scenario |
|---|---|
| 1 | Continue from cursor → inline ghost streams at the caret (poll) |
| 2 | Discard → `waitForResponse(/jobs/.+/correction)` with `kind:reject` (201) — the Dead capability, now live |
| 3 | Regenerate → correction `kind:regenerate` fires, then re-streams |
| 4 | Accept / Edit → NO correction request (H2 self-reinforcement guard) — assert none fired within a window |

### A5 · `studio-publish.spec.ts` — publish gate in the dock editor (S1 B4)
No model needed (uses a seeded chapter). Reuses `publishChapterApi`/`setSceneStatus` for setup where useful.
| # | Scenario |
|---|---|
| 1 | Open editor on a chapter whose scene is not done → Publish DISABLED with a visible blocked reason ("N of M scenes not yet done") — no silent fail |
| 2 | `setSceneStatus(done)` → reload → Publish ENABLED (gate transitions) |
| 3 | Publish → status flips to Published (button → "Re-publish") |

### Coverage matrix (every §2-bar dimension is hit by ≥1 spec)
1 operable A2/A3/A4/A5 · 2 CRUD A1/A3 · 3 reachable A1 · 4 no-silent-fail A2#4/A3#4/A5#1 · 5 agent-parity
(covered by unit effectCoverage; an E2E agent-drive is out of scope — chat-agent E2E is a separate rack) ·
6 loop-connected A2#1/A3#1 · 7 proven (all model-gated specs) · 8 i18n+responsive (unit + SETTLED desktop-first) ·
9 scale (N/A — scene-scoped).

## 4 · Part B — BLACKBOX user-role usability pass (real app, judgment not just assertions)
**Not pass/fail scripts** — a structured exploratory pass where the tester ROLE-PLAYS a real web-novel
author on the running app (:5174 baked, or an isolated static build) and renders a **usability verdict**
per scenario: `usable` / `friction (describe)` / `broken`. The point is "can a real author actually DO
the job", the exact bar S1 exists to satisfy ("cho có và rời rạc" is the failure).

**Persona:** an author mid-novel — "I'm writing chapter 3; I want the AI to help me draft, I accept/
revise, and I publish when it's ready." Not a developer; discovers the UI as it is.

| BB | Scenario (author's words) | What to JUDGE (usability, not just "it works") |
|---|---|---|
| BB-1 | "Let me draft the next scene with AI." | Discoverability: from the studio, can the author FIND the draft loop? Is the `compose` (Chat) vs `scene-compose` (draft loop) distinction obvious, or confusing? How many steps/dead-ends to a first ghost? |
| BB-2 | "Accept this draft into my chapter." | Does the accepted prose land WHERE the author expects? Is the 2-panel handoff (scene-compose→editor) coherent or jarring? If the editor isn't open, is the guidance clear + non-destructive? |
| BB-3 | "This draft is wrong — try again / assemble the whole chapter." | Regenerate/reject + chapter-assemble: is the per_scene/chapter/stitch model understandable? Do the gate messages ("scenes not done") HELP or block confusingly? |
| BB-4 | "My edits should teach the AI." | Is there ANY signal that corrections are captured (the flywheel)? Or is it invisible? (Honest: is this a felt feature or a silent backend?) |
| BB-5 | "Publish my chapter." | From blocked→published: is the reason clear, and can the author self-serve to unblock without hunting? |
| BB-6 | "Do the whole loop in the Studio." | import→plan→draft→revise→publish WITHOUT touching the legacy page — does any step force the author out of the Studio? (the ③ loop-closes goal.) |

**Output:** a usability report (per-BB verdict + concrete friction list + severity + screenshots), stored in
`docs/plans/2026-07-17-studio-S1-blackbox-usability-report.md` (dated report, per the store-reports lesson).
Friction that is a real defect → fix-now or a tracked row; friction that is a design opinion → note for PO.

## 5 · Execution + acceptance
- **Order:** add PoM + api helper → A1 (fast, proves reachability without a model) → A2–A5 (model-gated)
  → run the full `npm run e2e` for the studio specs on a stack-up (LM Studio + gateway + FE) → Part B
  blackbox pass → usability report.
- **Model-gating is honest, not a skip-to-green:** the LLM specs `test.skip` (not pass) when models are
  absent; A1 + A5 (no-model) always run, so CI has real S1 coverage even without LM Studio.
- **Acceptance:** A1–A5 green on a stack-up (or cleanly skipped where model-gated), pasted run output;
  Part B report written with an explicit "is S1 genuinely usable by an author?" verdict.
- **Not in scope:** agent-drives-the-panel E2E (Lane-A/B via chat) — that's the agent-rack test surface,
  a separate track; S1's §2-bar-#5 is unit-covered by effectCoverage.
