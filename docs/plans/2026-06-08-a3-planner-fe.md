# DESIGN + PLAN — A3 Decompose-Planner FE (Cycle 13, D-A3-PLANNER-FE)

- **Date:** 2026-06-08 · **Branch:** `feat/composition-service` · **Size:** L `[FE]` · **Status:** DESIGN-checkpoint (no code; BUILD = a focused follow-up session, per XL discipline)
- **Clears:** `D-A3-PLANNER-FE` + `D-A3-REPLACE-ORPHAN-ARC-NODES`.
- **Why a checkpoint commit:** locks the api/types interfaces + the slice plan so the BUILD session inherits them and doesn't re-litigate (`feedback_design_checkpoint_commit_separates_design_from_implementation`).

## 1. Context — what exists

The A3 decompose planner shipped **BE + eval** (LOOM-22/A3); only the FE was deferred. The BE contract is live + cycle-1-hardened (idempotency + true-replace, LOOM-43):

| Endpoint | Shape |
|---|---|
| `GET /v1/composition/templates` ([canon.py:137](../../services/composition-service/app/routers/canon.py#L137)) | built-in + user structure templates `{id, name, beats[…]}` |
| `POST /v1/composition/works/{project_id}/outline/decompose` ([plan.py:115](../../services/composition-service/app/routers/plan.py#L115)) | req `{structure_template_id, premise, model_source, model_ref}` → **DecomposeResult** (preview, NOT persisted): `{arc_title, chapters:[{chapter_id, title, beat_role, scenes:[{title, synopsis, tension(0..100), present_entities:[{entity_id,name}]}]}]}` |
| `POST …/outline/decompose/commit` ([plan.py:162](../../services/composition-service/app/routers/plan.py#L162)) | req `{arc_title, chapters:[{chapter_id, title, intent, beat_role, scenes:[{title, synopsis, tension, present_entity_ids:[uuid]}]}], replace, idempotency_key}` → 201; **409 `CHAPTER_ALREADY_PLANNED`** (`{chapter_ids}` — resend `replace=true`); **400 `BAD_CHAPTER`/`BAD_ENTITY`/`NO_CHAPTERS`/`TOO_MANY_CHAPTERS`** |

**FE today** (`frontend/src/features/composition/`): `api.ts` has outline CRUD (`getOutline`/`addOutlineNode`/`patchOutlineNode`) + B2 chapter-generate, but **no decompose/commit/templates** methods. `CompositionPanel` already hosts always-mounted CSS-hidden sub-tabs (cycle-9). So the planner is a **net-new sub-tab + hook + api**.

## 2. UI design

A new **"Planner"** sub-tab in `CompositionPanel` (always-mounted, CSS-`hidden` toggled — NEVER ternary-unmount, per CLAUDE.md + the cycle-9 rule; a half-edited tree must survive a tab switch).

**Flow:**
1. **Configure** — pick a structure template (from `GET /templates`) + write a premise + pick the model (reuse the existing generation model-selection; same `model_source`/`model_ref` the compose/generate flow already resolves). → **Preview** button.
2. **Preview** — `POST …/decompose` → render the proposed **arc → chapter → scene** tree (read-only LLM output). Each chapter shows its book chapter + beat_role; each scene shows title / synopsis / tension / present-cast. **Preview-step errors** (review-impl on design): the preview itself can 400 `NO_CHAPTERS` (book has no chapters — guide the user to create chapters first) or `TOO_MANY_CHAPTERS` (over `plan_max_chapters` — surface the count/max); surface these inline on the config form, not just the commit errors.
3. **Edit** — inline-edit per scene (title, synopsis, tension slider 0..100, cast multi-select from the book roster) + per chapter (intent, beat_role). Add/remove a scene within a chapter. All edits are **local** (the preview is a draft; nothing persists until commit).
4. **Commit** — `POST …/commit` with the edited tree + a generated `idempotency_key`. On **409 `CHAPTER_ALREADY_PLANNED`** → a `ConfirmDialog` ("these chapters already have scenes — replace them?") → resend with `replace=true`. On 400 `BAD_ENTITY`/`BAD_CHAPTER` → surface which ids. On 201 → success toast + refresh the outline.

**MVC (per CLAUDE.md FE rules):**
```
features/composition/
  hooks/usePlanner.ts        ← controller: template/premise/model state, preview+commit+edit logic, 409→replace flow
  components/PlannerView.tsx  ← view shell (config + preview tree); ≤100 lines → split sub-views
  components/PlannerTree.tsx  ← the arc→chapter→scene tree render
  components/PlannerSceneRow.tsx ← one editable scene (title/synopsis/tension/cast)
  api.ts (+listTemplates, +decomposePreview, +commitDecompose)
  types.ts (+the planner types below)
```
- **State frequency split:** the edit-draft (changes per keystroke) lives in `usePlanner`/local component state; do NOT push it into a context that stable consumers read (CLAUDE.md "split context by update frequency").
- **No `useEffect` for actions** — preview/commit are explicit callback handlers, not effect-reactions.

## 3. Locked interfaces (the checkpoint's contract)

`types.ts`:
```ts
export interface StructureTemplate { id: string; name: string; beats: { name: string; purpose?: string }[]; }
export interface PlannerCastRef { entity_id: string; name: string; }
export interface PlannerScene { title: string; synopsis: string; tension: number | null; present: PlannerCastRef[]; }   // preview shape
export interface PlannerChapter { chapter_id: string; title: string; beat_role: string | null; intent?: string; scenes: PlannerScene[]; }
export interface DecomposePreview { arc_title: string; chapters: PlannerChapter[]; }
// commit payload mirrors the BE CommitRequest (present → present_entity_ids):
export interface CommitScenePayload { title: string; synopsis: string; tension: number | null; present_entity_ids: string[]; }
export interface CommitChapterPayload { chapter_id: string; title: string; intent: string; beat_role: string | null; scenes: CommitScenePayload[]; }
export interface CommitDecomposePayload { arc_title: string; chapters: CommitChapterPayload[]; replace: boolean; idempotency_key: string; }
```
`api.ts`:
```ts
listTemplates(token): Promise<StructureTemplate[]>
decomposePreview(projectId, body: {structure_template_id, premise, model_source, model_ref}, token): Promise<DecomposePreview>
commitDecompose(projectId, payload: CommitDecomposePayload, token): Promise<{...}>   // 409 → typed error carrying chapter_ids
```

## 4. Slices (BUILD session)

- **S1 — api + types.** Add the 3 api methods + the types. A typed 409 error (`ChapterAlreadyPlannedError{chapter_ids}`) so the hook can branch to the replace-confirm. Unit-test the api error mapping.
- **S2 — preview view + hook.** `usePlanner` (template list, premise, model, `preview()`), `PlannerView` + `PlannerTree` render the returned tree read-only. Wire the Planner sub-tab into `CompositionPanel` (CSS-hidden). vitest: renders a previewed tree; tab-switch preserves it (the visibility-transition regression test `/review-impl` repeatedly asks for).
- **S3 — inline edit + commit.** Editable scene rows (title/synopsis/tension/cast) + chapter intent/beat; add/remove scene; `commit()` with idempotency_key; **409 → ConfirmDialog → replace=true** resend; 400 surfacing. vitest: edit a scene → commit payload carries the edit (non-default regression-lock, not happy-path); 409→replace path.
- **S4 — orphan-node handling (`D-A3-REPLACE-ORPHAN-ARC-NODES`) + i18n + polish.** After a replace-commit, the prior arc/chapter outline nodes whose scenes were archived may be left childless — the FE filters/archives them from the outline view (confirm the BE leaves them vs the FE prunes the display; **confirm-at-BUILD** whether `replace` already archives the arc node or only the scenes). i18n ×4 locales. a11y: tension slider labelled, tree keyboard-navigable, ConfirmDialog focus-trap.

## 5. Acceptance criteria

- Pick template + premise + model → Preview renders the arc→chapter→scene tree from the live BE.
- Edit a scene's tension/synopsis/cast + a chapter's intent → Commit persists exactly the edited tree (verified by re-reading the outline).
- A second commit on already-planned chapters → 409 → confirm → replace succeeds; no duplicate scenes (the BE cycle-1 guard + the FE confirm).
- Tab-switch mid-edit preserves the draft (no unmount).
- Orphan prior arc/chapter nodes don't linger in the outline after replace.
- vitest green + tsc clean; 4-locale i18n.

## 6. Confirm-at-BUILD

- The exact `GET /templates` response shape (beats sub-fields) + the `DecomposeResult` field names (`synopsis` vs `intent`; `present` vs `present_entities`) — re-read `plan.py` + `engine/plan.py` dataclasses at BUILD.
- How `model_source`/`model_ref` are resolved in the existing compose/generate FE (reuse, don't reinvent the model picker).
- Whether `replace` already archives the **arc node** or only the scenes (decides if S4 prunes nodes or just the display) — read `outline.commit_decomposed_tree`.
- The book roster source for the cast multi-select (glossary list — likely an existing FE hook).

## 7. Risks

- **R-unmount:** sub-tab ternary-render would lose the edit draft → CLAUDE.md violation. Mitigation: CSS-hidden always-mounted (S2 AC + a regression test).
- **R-409-replace:** an accidental replace archives real scenes. Mitigation: explicit ConfirmDialog naming the affected chapters; `replace=false` default.
- **R-edit-state-size:** a large tree edited per-keystroke could re-render heavily. Mitigation: per-row local state; memoize rows.
