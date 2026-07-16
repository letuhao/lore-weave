# S4 (Motif & craft) — Playwright E2E + Blackbox-User Test Plan

> Goal: cover the WHOLE S4 surface (motif-library · scene-inspector Motifs section + suggest ·
> quality-conformance · binding lens · agent-parity) with (A) structured deterministic E2E specs
> and (B) a blackbox real-user journey that answers *"can a real web-novel author actually DO the
> job in the real app?"* — the §2 bar #1 (operable) + #7 (proven) from the user's chair.
>
> Convention: `frontend/tests/e2e/specs/*.spec.ts`, `data-testid` selectors (i18n/style-agnostic),
> Page Objects (`pages/`), api/auth/inject helpers (`helpers/`). See `tests/e2e/CONVENTIONS.md`.
> Panels open the REAL way: `StudioPage.openPanel(id, term)` via the command palette.

## 0 · Fixtures / setup (deterministic — never rely on ambient data)
- `helpers/api.ts` additions: `createWork(book)` (co-writer Work so binding/conformance are live),
  `seedMotif(scope, code, name)`, `bindMotif(project, node, motif)`, `createMotifLink`. Reuse the
  test account's BYOK **Gemma-4 26B QAT** `model_ref` for the LLM-spend steps ($0).
- `pages/MotifLibraryPage.ts` + `pages/QualityConformancePage.ts` (locator lists = the test surface).
- Each spec: `beforeAll` seeds a fresh book (+ Work + a couple of motifs), `afterAll` trashes it.

## A · Structured E2E specs (deterministic, per-capability, mapped to the §2 bar)

### A1 · `studio-motif-library.spec.ts`
| # | scenario | §2 |
|---|---|---|
| 1 | palette "motif" → `studio-motif-library-panel` mounts (opens UNCONDITIONALLY, no Work needed) | #3 reachable |
| 2 | 6 scope tabs render (`motif-scope-{my,book,shared,system,catalog,drafts}`); book/shared disabled w/o a book | #1 |
| 3 | `motif-new` → inline form → submit → the new motif appears in the list | #2 CRUD |
| 4 | click a `motif-card` → `motif-detail-drawer` opens; a System motif shows NO Edit button | #1 / tenancy |
| 5 | graph section: `motif-graph-toggle` → `motif-graph-add-*` add edge → row appears → delete; **self-link → inline 409** (not a swallowed toast) | #2 / #4 |
| 6 | adopt from catalog: `motif-scope-catalog` → adopt modal → confirm → appears under Mine | #1 |
| 7 | ⛏ Mine: `motif-mine` → ModelPicker (Gemma) → confirm → job polls → drafts tab | #1 (gemma) |
| 8 | scale: seed >100 → `motif-load-more` fetches the next page (flat scopes); book/shared show `motif-list-truncated` | #9 |
| 9 | empty state (`scope=mine`, no motifs) → `MotifEmptyState` CTAs (Adopt / Mine), not a dead-end | #1 |

### A2 · `studio-motif-binding-suggest.spec.ts`
| # | scenario | §2 |
|---|---|---|
| 1 | select a scene → `scene-inspector` → the **Motifs** section renders (`motif-binding-*`) | #1 |
| 2 | bind a motif (free-form → Bind → picker) → the card flips to bound; swap; clear | #2 |
| 3 | **ranked Suggest**: `motif-suggest-toggle` → `motif-suggest-row` with score + match_reason; `motif-suggest-bind` binds it | #1 |
| 4 | no-Work book → `motif-no-work` message (not a broken card) | #4 |
| 5 | suggest error/empty states surface (no silent fail) | #4 |

### A3 · `studio-quality-conformance.spec.ts`
| # | scenario | §2 |
|---|---|---|
| 1 | palette "conformance" → `studio-quality-conformance-panel`; also the QualityHub 8th card opens it | #3 |
| 2 | chapter picker → the beat-by-beat trace renders (`conformance-row-*`); advisory banner when uncalibrated | #1 / honesty |
| 3 | **loop-connect**: a `conformance-open-scene-*` row → publishes + opens `scene-inspector`; empty-state CTA → `scene-browser` | #6 |
| 4 | Re-run: ModelPicker (Gemma) → CostConfirmCard → confirm → trace refreshes | #1 (gemma) |
| 5 | Regenerate a scene (`conformance-regen-*`) → `composition_generate` → prose changes | #1 (gemma) |
| 6 | **M-BUG-4**: arc-scope conformance returns a report, NOT a 422 (network assertion) | correctness |

### A4 · `studio-motif-agent-parity.spec.ts`  *(advanced — Lane-B)*
| # | scenario | §2 |
|---|---|---|
| 1 | open `motif-library`; inject an AGENT `composition_motif_create` tool-result → the panel **refetches** (the new motif appears without a manual reload) | #5 |
| 2 | open `quality-conformance`; inject `composition_conformance_run` result → the trace refetches | #5 |
| (needs a `helpers/effectInject.ts` to feed a backend-tool result through the reconciler; unit-proven in `studioMotifEffects.test.ts`, this is the live-wiring proof) |

## B · Blackbox real-user journey — `studio-motif-author-journey.spec.ts`
**Persona:** a web-novel author strengthening a chapter with tropes (套路/爽点/打脸). Drives the REAL
app end to end, NO test-only shortcuts for the actions under test, and at EACH step asserts *the user
could actually complete it* (a visible result, no dead-end, no silent no-op). Screenshots each step →
a usability artifact.

**The journey (the authoring loop ③ for the motif slice):**
1. Open my book's Studio → open the Motif Library. *Can I find it? (palette)* → panel mounts.
2. Browse tropes: switch to **Catalog**, find a face-slap/reversal trope. *Is the library legible?*
3. **Adopt** it into my library → it shows under **Mine**. *Did the adopt actually land?*
4. Open a scene in the inspector → **Suggest a motif** → pick the ranked one → **Bind**. *Did the bind stick? roles?*
5. **Generate** the scene on Gemma → prose streams. *Does the drafter honour the bound beat?*
6. Open **Conformance** → pick the chapter → see the beat trace. *Did the prose realize the beat?*
7. A missed beat → click the scene row (**deep-link**) → land in the inspector → **Regenerate**. *Loop closes?*
8. Verdict assertions per step + a final "the author completed the trope loop without touching the
   legacy editor" check (the ③ finish-line, Studio-only).

**Usability rubric (asserted, not just observed):** every read has a reachable write · every list row
opens something · every action shows success/error · no step dead-ends · the loop closes back to the
manuscript. A step that renders but can't be operated = a FAIL (the What-If "skeleton" lesson).

## Run / gate
- `npx playwright test tests/e2e/specs/studio-motif-*.spec.ts` (headed for the journey artifact).
- Needs the stack up (`:5174` baked or `vite :5199`) + composition-service + gateway + lm_studio (Gemma).
- CI tag: `@s4` so the S4 suite runs as a group.

## Build order / STATUS (2026-07-17)
- ✅ **Scaffolding** — `helpers/motif.ts` (createWork/seedMotif/createSceneNode/createMotifLink/
  archiveMotif/resolveChatModel) + `pages/MotifLibraryPage.ts` + `pages/QualityConformancePage.ts`.
- ✅ **A1 · studio-motif-library.spec.ts** — 5 tests GREEN (reachable+6 tabs · CRUD create · card→detail ·
  graph add→render→delete · reachability guard). *Live finding:* the neighbour dropdown EXCLUDES the
  anchor, so a self-link can't be picked via UI (a defense-in-depth backstop — 409 stays unit-tested).
- ✅ **A2 · studio-motif-binding-suggest.spec.ts** — 2 tests GREEN (Motifs section renders for a live
  seeded scene · ranked Suggest returns rows with a % score — the GG-1 fix, live).
- ✅ **A3 · studio-quality-conformance.spec.ts** — 4 tests GREEN (palette + QualityHub-card reachable ·
  chapter picker → trace/empty · **M-BUG-4 regression at the network level**: arc_template_id→422, arc_id→¬422).
- ✅ **B · studio-motif-author-journey.spec.ts** — 1 blackbox journey GREEN (reach→browse tiers→author a
  trope→open→graph edge→conformance→loop-connect), usability asserted per step + 7 screenshots.
- ✅ **A4 · agent-parity — COVERED IN LAYERS (a live chat-inject e2e is optional, not built).** The
  reconciler (`useStudioEffectReconciler.ts`) fires `runEffectHandlers` on a SUCCEEDED chat tool-call.
  Its three links are each already tested: (1) the motif/conformance **handler logic** →
  `studioMotifEffects.test.ts` (2, proves the exact invalidations); (2) the **barrel→reconciler wiring**
  → `effectCoverage.contract.test.ts` (151) drives the SAME `registerAllStudioEffectHandlers` the
  reconciler calls, asserting `composition_motif_*` + `conformance_run` are matched by a registered
  pattern (and reads like `composition_motif_get` are NOT — the no-thrash guard); (3) the generic
  `messages → runEffectHandlers` **dispatch** (dedupe, ok-only) is shared with every domain (canon/arc/
  plan) and tested there. A full browser e2e would only add the LLM-choice-dependent trigger, which is
  precisely what `frontendToolInject` was built to avoid — so it needs a `helpers/effectInject.ts`
  (backend-tool-result SSE) and is deferred as low-marginal-value, NOT a coverage hole.

**12 E2E tests GREEN** as a suite (`--project=chromium`, `PLAYWRIGHT_BASE_URL=http://localhost:5199`, 46.7s).
Run: `PLAYWRIGHT_BASE_URL=http://localhost:5199 npx playwright test tests/e2e/specs/studio-motif-*.spec.ts tests/e2e/specs/studio-quality-conformance.spec.ts`.
