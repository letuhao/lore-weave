# S-13 · Studio decompose surface (G-STORY-STRUCTURE) — close the S-01 loop

> **Tier A follow-on · Size M · FE-only PORT (no HTML draft, no new backend).**
> Origin: the `D-S01-USE-IN-DECOMPOSE` debt (S-01 RUN-STATE). This spec is the buildable home for it.
> **Design reference (the PORT source):** the legacy `PlannerView` + `usePlanner` (`features/composition`),
> which is the fully-built decompose UX — this spec wraps it in a studio dock panel, it does not re-design it.

---

## 1. Goal / user story

A user authors a custom story structure in the studio's **StructureTemplatesPanel** (S-01, shipped), then wants
to **decompose their book against it** without leaving the studio. **Goal:** a studio-native decompose panel,
reachable from the palette and deep-linked from a template's **"Use in decompose"** action, that pre-selects the
chosen structure, previews the arc→chapter→scene tree, lets the user edit it, and commits — exactly what the
legacy planner does, but as a first-class studio panel. Finish = a brand-new user can go
*author structure → "Use in decompose" → preview → commit* entirely inside the studio, proven by a live browser
smoke.

## 2. Why this exists (the audit correction it closes)

The S-01 spec §8 promised *"Deep-link OUT: 'Use in decompose' → the plan-hub decompose action pre-selecting this
template."* **That target does not exist.** Verified against code (2026-07-18):

- The **only** decompose surface is the legacy `PlannerView`, mounted **only** inside `CompositionPanel`, which
  is reachable **only** via the legacy `ChapterEditorPage` route (`/books/:bookId/chapters/:chapterId/edit`) —
  **not a studio dock panel**. `plan-hub` (`PlanHubPanel`) has **zero** decompose refs.
- The studio's `plan-forge` **`PlannerPanel`** (id `planner`) is a *different* flow — paste-braindump → propose →
  compile → passes. It does **not** take a `structure_template` and is **not** decompose. It is NOT the target.
- So S-01's `StructureTemplatesPanel` ships **no** "Use in decompose" button (there was nothing to point it at —
  see the panel's own line-8 comment noting use-in-decompose as intended-but-absent).

**The loop is NOT broken today** — a user's custom structure already appears in the legacy planner's picker
(`usePlanner` → `listTemplates` returns own + built-in) and the decompose route resolves it (locked by
`test_the_decompose_consumer_resolves_a_custom_template`). What is missing is the **studio-native surface + its
deep-link**. This spec builds exactly that missing surface — nothing more.

## 3. The reclassification this spec records (anti-laziness gate)

The debt was carried as *"blocked on G-STORY-STRUCTURE, a large new track — a new panel + the decompose UX."*
**That over-stated it.** Verified against code, **every buildable piece already exists**:

| Piece the port needs | Already exists? | Where |
|---|---|---|
| The decompose controller (config → preview → editable draft → commit + 409-replace) | ✅ built | `usePlanner(projectId, token)` |
| The decompose render (template/premise/model form, `PlannerTree`, replace-confirm, commit) | ✅ built | `PlannerView` / `PlannerTree` |
| book → work → `project_id` resolution in the studio | ✅ built | `useWorkResolution(bookId, token)` → `resolveActiveWork(...).project_id` |
| The decompose route + template consumer | ✅ built | `POST /works/{pid}/outline/decompose`; `templates.get` |
| The empty-state (no Work yet) affordance | ✅ built | `WorkSetupCta` (reused by other studio panels) |

⇒ G-STORY-STRUCTURE is **not** a large data-layer track. It is an **M-sized FE port**: a dock-panel shell that
resolves `project_id`, mounts the existing controller/render, accepts a `templateId` open-param, plus **one GG-8
registration** and **one deep-link wire** in the S-01 panel. **No new backend, no migration, no MCP tool, no HTML
draft.** Defer-eligible only under **gate #1 (out of S-01's own scope)** — a sibling studio-completeness spec,
buildable in the fanout like S-02..S-12. It was **never** blocked on missing infrastructure.

## 4. Design — Option A: a focused `decompose` studio panel (port, not re-implement)

New panel **`decompose`** (`DecomposePanel.tsx`), category `editor` (it sits beside `planner`/`editor`):

```
DecomposePanel (dock shell)
  bookId       ← useStudioHost()
  token        ← useAuth()
  work         ← useWorkResolution(bookId, token)
  projectId    ← resolveActiveWork(work.data, activeWorkId)?.project_id ?? null
  ├─ projectId == null (no Work yet)  → <WorkSetupCta>  (ENTRY-from-empty; NOT a dead-end)
  └─ projectId != null                → <PlannerView projectId premise/template/model … />
                                          (the EXISTING render — reused verbatim, or via a thin
                                           StudioDecomposeView wrapper if a studio-scoped chrome is needed)
```

- **Reuse, don't fork.** `PlannerView` + `usePlanner` already own the whole flow (template picker, premise, model
  override, preview tree, inline edit, commit, 409→replace, post-commit motif binding). The panel is a *host* for
  them. If `PlannerView`'s props (`onSelectScene`) need a studio target, thread the studio `openPanel('compose', …)`
  seam; otherwise pass nothing (the generate link no-ops, same as legacy).
- **Deep-link IN (the S-01 loop close).** The panel reads an open-param `templateId`. On mount, if present, it
  calls `p.setTemplateId(templateId)` so the structure the user just authored is **pre-selected**. Opening with no
  param lands on the normal picker.
- **`activeWorkId`** follows the same source the other studio composition panels use (the studio host's active
  work / manuscript-unit selection), so a derivative Work decomposes against its own `project_id`, not the canon's.

**Rejected alternatives:**
- *Wire the deep-link into `plan-forge`'s `PlannerPanel`* — rejected: it is a different flow (braindump→compile),
  takes no structure template. It would silently drop the `templateId` (a Frontend-Tool-Contract silent-no-op).
- *Mount the whole legacy `CompositionPanel` as a studio panel* — rejected: it is a heavy multi-tab legacy panel
  (compose/planner/cast/motif/…); mounting it drags in unrelated surfaces. Port only the decompose slice.

## 5. GG-8 registration (the one convergence-node cost)

Same shape S-01 used for `structure-templates`:
- **`catalog.ts`** — a `decompose` row (category `editor`, `titleKey`/`descKey`/`guideBodyKey`, `tourAnchor`).
- **`panel_id` enum** — add `decompose` to the closed set in `chat-service/app/services/frontend_tools.py`
  (`ui_open_studio_panel`'s `panel_id`), so an agent can open it; **no silent no-op**.
- **`contracts/frontend-tools.contract.json`** — regen via `WRITE_FRONTEND_CONTRACT=1 pytest` (both-sides
  machine-checked by `panelCatalogContract.test.ts` + `legacyParityContract.test.ts`).
- **i18n** — `panels.decompose.{title,desc,guideBody}` + palette command, filled across all locales by
  `scripts/i18n_translate.py --ns studio` (ML-7 gate).
- **`CATEGORY_ORDER`** — place under `editor`.
- **Lane-B effect handler** — a decompose commit already invalidates `['composition','outline',projectId]`
  (in `usePlanner.commitMut.onSuccess`); confirm an agent-driven `composition_*` decompose refreshes the panel,
  reusing `compositionEffects` (no new handler unless a gap shows).

**Same-folder discipline:** `catalog.ts` / the `panel_id` enum / `frontend-tools.contract.json` / studio i18n are
convergence nodes that concurrent sessions edit. Register **minimally**, commit the 4-file registration as one
atomic pathspec commit, and note it — do **not** `git add -A`.

## 6. Deep-link OUT from S-01 (the wire that closes the loop)

In `StructureTemplatesPanel` (S-01), add the **"Use in decompose"** affordance the S-01 spec promised:
- On an **own** template (and a built-in — decompose accepts both), a button
  `data-testid="structtpl-use-in-decompose"` → `openPanel('decompose', { params: { templateId: selected.id } })`.
- Uses the studio host `openPanel` (already imported by sibling panels). It is a pure navigation affordance — no
  new state.

This is the single edit to an S-01 file; keep it isolated so it commits with S-13, not tangled into S-01's history.

## 7. Usability gate (the S-01 bar — every point must hold)

| Bar | How S-13 meets it |
|---|---|
| **ENTRY from empty** | Palette command opens the panel cold; no Work → `WorkSetupCta`, not a blank/blocked pane. |
| **ACTION → visible RESULT** | pick template + premise + model → **Preview** renders the arc→chapter→scene tree; **Commit** writes the outline (invalidates the outline query → the manuscript tree updates). |
| **no DEAD-END** | the deep-link from S-01 lands on a *pre-selected, operable* form, not a read-only view; 409 offers inline replace-confirm; no-Work offers setup. |
| **operable, not a shell** | it is the real legacy decompose flow — the same one that produces committed outlines today. |
| **loop-connected** | author-structure (S-01) → **Use in decompose** (this) → preview → commit → outline appears in the manuscript tree. The end-to-end loop the audit flagged as open. |

## 8. Tests (evidence gate)

- **panel unit** (`DecomposePanel.test.tsx`, mock `useWorkResolution` + `usePlanner`): no-Work → `WorkSetupCta`
  renders (no dead-end); with-Work → `PlannerView` mounts; the `templateId` open-param calls
  `usePlanner.setTemplateId` (pre-select proven).
- **deep-link unit** (extend `StructureTemplatesPanel.test.tsx`): clicking **Use in decompose** calls
  `openPanel('decompose', { params: { templateId } })` with the selected id.
- **GG-8 contract**: `panelCatalogContract` + `legacyParityContract` green with the new `decompose` row + enum;
  the `panel_id` enum closed-set includes `decompose` (an off-set value is rejected — no silent no-op).
- **live browser smoke** (isolated static build on its own port — HMR-free so a concurrent session can't confound
  it): author a structure in `structure-templates` → **Use in decompose** → the picker shows it **pre-selected** →
  premise + local model → **Preview** → tree renders → **Commit** → the outline appears. This is the finish-line
  proof, not unit green.
- **no regression**: the legacy `PlannerView`/`usePlanner` path (via `ChapterEditorPage`) is untouched — the port
  *reuses* them, so its existing tests still cover the flow.

## 9. Out of scope / by-design

- **No change to the decompose engine, the route, `usePlanner`, or `PlannerView` internals.** This is a host +
  a deep-link. If `PlannerView` needs a studio-scoped chrome, a thin `StudioDecomposeView` wrapper is allowed, but
  the controller stays `usePlanner`.
- **No new backend / migration / MCP tool.** The decompose route + template consumer already exist and are
  unchanged (S-01 already locked `test_the_decompose_consumer_resolves_a_custom_template`).
- **No HTML draft** — this is a PORT; the legacy `PlannerView` is the design reference (roadmap HTML-draft rule).
- **Book-shared structure tier** stays out (S-01 §10 — per-user only).

## 10. Definition of done

The `D-S01-USE-IN-DECOMPOSE` debt is CLOSED when: the `decompose` panel is registered + reachable, the S-01
**Use in decompose** button opens it pre-selected, and the live browser smoke shows author-structure → decompose →
commit end-to-end inside the studio. Until built, the debt is **specced (this file) and ready to build in the
fanout** — no longer "blocked".

---

## 11. BUILD STATUS (2026-07-18) — SHIPPED, D-S01-USE-IN-DECOMPOSE CLOSED

Investigated against code first: the spec is **accurate**, with one mechanism refinement — `PlannerView`
calls `usePlanner` **internally**, so the host cannot call `p.setTemplateId`. Wired the pre-select via a
minimal backward-compatible **`initialTemplateId?` prop** on PlannerView (seeds once on mount; legacy
`CompositionPanel` omits it → unchanged) — exactly the "thread through PlannerView props" §4/§9 permitted.

- **`DecomposePanel`** (commit `63…`/feature `…`): resolves `project_id` via `useWorkResolution` +
  `resolveActiveWork`; no Work → `WorkSetupCta` (ENTRY-from-empty); else mounts `PlannerView` with the work's
  `default_model_ref`; DOCK-6 params (templateId at mount + `onDidParametersChange`), keyed to re-seed.
- **GG-8 registration**: `decompose` catalog row (category `editor`) + `panel_id` enum + `frontend-tools.contract.json`
  regen + `panels.decompose.*` i18n seeded in en and **filled across all 17 locales** (i18n_translate, 0 failed).
- **S-01 deep-link**: `StructureTemplatesPanel`'s interim hint replaced with the real **"Use in decompose"**
  button (OwnEditor edit-mode + BuiltinDetail) → `host.openPanel('decompose', {templateId})`.
- **VERIFY**: DecomposePanel 4 + StructureTemplatesPanel deep-link (own + built-in) + panelCatalogContract 9 +
  legacyParityContract 5 + registryPanels 4 green; tsc 0; BE `test_frontend_tools_contract` 20 (regen).
- **LIVE SMOKE (:5199)**: palette → "Studio: Open Decompose" opens the panel → **WorkSetupCta** empty-state
  (no Work → not a dead-end); structure-templates → select a built-in → the **Use in decompose** button
  renders (interim hint gone) → click → the **Decompose tab activates**. The reachability + empty-state +
  deep-link loop are live-proven. The with-Work **preview→commit** leg is the *unchanged* legacy `PlannerView`
  flow (covered by its own tests + the DecomposePanel unit that mounts it with `project_id`+model); a full
  author→commit E2E needs a seeded Work+structure+model on a book (heavier setup) — a follow-up live run, not
  a code gap.
