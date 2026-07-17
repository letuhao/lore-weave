# Studio Structure Origin — clearing the zero-state dead loop

> **Date:** 2026-07-17 · **Status:** SPEC — ready to build
> **Supersedes:** `design-drafts/structure-authoring/` (the "Spine" — ☠ KILLED, 4/4 adversarial review)
> **Evidence:** [`docs/bugs/2026-07-17-studio-first-use-cold-start.md`](../bugs/2026-07-17-studio-first-use-cold-start.md)
> **PO decisions sealed 2026-07-17** — see §2.

---

## 1. The problem

**The Writing Studio has no origin point.** Every surface assumes an upstream surface already ran. A first-time user with a new book faces **four doors, all locked**:

| Door | Locked because |
|---|---|
| Manuscript `+` | `ManuscriptNavigator.tsx:116` `disabled={!onNewChapter}`; `StudioSideBar.tsx:34` never passes it. **Never wired.** |
| Editor · SceneCompose · ChapterAssemble | *"Select a chapter in the manuscript navigator"* → the navigator has none (`EditorPanel.tsx:264`, `SceneComposePanel.tsx:65`, `ChapterAssemblePanel.tsx:57`) |
| plan-hub → **Extract the plan** | The decompiler reads scenes **already parsed from chapters**. New book ⇒ none. `PlanEmptyState.tsx:98` says so itself. |
| plan-hub → **Plan from scratch** | Opens `planner` (`PlanHubPanel.tsx:164`), whose Propose is hard-gated: `PlannerPanel.tsx:120` — `canPropose = … && effectiveMarkdown.trim().length > 0`; placeholder *"Paste the novel-system markdown…"*. **It is not from scratch.** |

The only working door is **outside** the Studio: the book's Chapters tab (`ChaptersTab.tsx:63`).

### 1.1 The empty state violates the law it cites

`PlanEmptyState.tsx:15`:

```ts
// Neither is a dead button (PH7's visible-fallback): both are live today.
```

**False in the exact state this component exists to serve.** At zero both verbs are dead. PH7 (`PlanToolbar.tsx:4`) is *"buttons visible but disabled"* — a capability must never render as a control that does nothing. The empty state is dead in the empty state, and asserts the opposite in a comment.

### 1.2 Nothing is missing from the backend. This is a MOUNTING bug.

| Capability | Exists? | Where |
|---|---|---|
| Create a Work **+ its KG project**, idempotent, race-safe, outage-resilient | ✅ | `POST /books/{book_id}/work` — `works.py:163`. *"Ensures a book-typed knowledge project exists (resolve, else ProjectCreate), then get-or-creates the composition_work row."* Needs only `book_id` + EDIT. **No chapters.** C16: knowledge down ⇒ lazy null-`project_id` Work + `pending_project_backfill`, polled to completion. |
| Create an **arc from nothing** | ✅ | `POST /books/{book_id}/arcs` — `arc.py:590`. Book-scoped (`structure_node` is keyed by `book_id`, **not** `project_id`) ⇒ **works with no Work at all**. |
| A finished, shared **Work-creation GUI** | ✅ | `WorkSetupCta.tsx` — idempotent, handles the C16 pending/backfill poll. |
| FE client `createArc` | ❌ | `plan-hub/api.ts:22` has `getArcs` (read). The only arc POST is `assign-chapters` (`:251`). |
| `create` verb in plan-hub writes | ❌ | `usePlanNodeWrites.ts` — `edit` (`:66`) · `archive` (`:80`) · `restore` (`:86`). No create. |
| `WorkSetupCta` mounted where writers start | ❌ | Mounted **only** in Quality (`QualityHubPanel.tsx:51`, `QualityNoWorkState.tsx:74`). |

**`WorkSetupCta`'s own header documents this exact bug one layer up** — *"was mounted ONLY on the legacy `CompositionPanel`, so a GUI-only user hit `no-work` with no self-service exit."* It was diagnosed, fixed, and then mounted in one place. **We are fixing the same bug a second time. Do not fix it a third: mount it, don't rebuild it.**

---

## 2. Sealed decisions (PO, 2026-07-17)

| # | Decision |
|---|---|
| **D1** | **plan-hub owns the structure origin.** It gets a real create-from-zero. |
| **D2** | **Manuscript `+` opens plan-hub.** Structure authoring is a *spec* act; the rail contract (`StudioSideBar.tsx:42-48`) is Manuscript = prose, Plan = spec. |
| **D3** | The **Spine redesign is dead.** plan-hub already *is* the lane spine (`laneLayout.ts`), and better. Do not build a second canvas. |
| **D4** | **Mount, don't build.** Reuse `WorkSetupCta`, `laneLayout`, `PlanEmptyState`. |

> ⚠️ **D2 only clears the loop because of D1.** Routing `+` to plan-hub while plan-hub is still locked at zero would merely *relocate* the dead end. **D1 and D2 must ship together.**

---

## 3. Design

### 3.1 Manuscript `+` → plan-hub

`StudioSideBar.tsx` already imports the host and already uses this exact seam for the Plan rail (`:24`, `:51`):

```tsx
// StudioSideBar.tsx — the ManuscriptNavigator call site (:34)
<ManuscriptNavigator
  bookId={bookId}
  token={token}
  selectedId={selectedId}
  onSelect={(node) => onSelectNode(node)}
  onCollapseSidebar={onCollapse}
  onNewChapter={() => host.openPanel('plan-hub', { focus: true })}   // ← D2
/>
```

That one prop un-disables the button (`disabled={!onNewChapter}`) **and** routes it to the surface that owns structure. No new component, no new seam.

**Title/tooltip must change.** The control is no longer "New chapter" — it opens the plan. Rename the i18n key `manuscript.newChapter` → `manuscript.openPlan`, label **"Plan this book"**. A button whose name promises the one thing it doesn't do is the bug we just spent a day on.

### 3.2 plan-hub's origin — `PlanEmptyState` v2

Three verbs, **ordered by what actually works at zero**, each with a real enable condition and a stated reason when disabled (PH7, honestly this time).

```
┌──────────────────────────────────────────────────────────────────┐
│                    No plan for this book yet                     │
│  The Plan Hub shows the spec — arcs, chapters, scenes. It will   │
│  never be invented from your manuscript.                         │
│                                                                  │
│   ┌────────────────────────────┐                                 │
│   │  Start with your first arc │  ← PRIMARY. The only one that   │
│   └────────────────────────────┘    works on an empty book.      │
│                                                                  │
│   [ Extract the plan from the manuscript ]   ← disabled at zero  │
│     ⓘ Needs chapters with parsed scenes. This book has none yet. │
│                                                                  │
│   [ Paste a plan you've already written ]    ← relabelled        │
│     ⓘ Opens the Planner. Needs novel-system markdown.            │
└──────────────────────────────────────────────────────────────────┘
```

**Verb 1 — "Start with your first arc" (NEW, primary).** One click, from nothing:

1. **Ensure the Work** — mount **`WorkSetupCta`**'s hooks (`useCreateWork` + `usePendingWorkResolver`). Idempotent; also creates the KG project; C16-resilient. **Do not reimplement.**
2. **Create the arc** — `POST /books/{book_id}/arcs` with `{ kind: 'arc', title }`. Book-scoped, so step 2 does not depend on step 1 completing.
3. Focus the new arc on the canvas.

**Naming:** inline-type the title on the canvas (the one idea worth keeping from the killed draft — *a dialog takes you off the canvas to talk about the canvas*). Default `Untitled arc` if the user just hits ↵. **Never block on a modal.**

**Ordering rationale:** at zero, verb 1 is the *only* live control. Today the primary (`bg-primary`) is **Extract** — the one guaranteed to fail on a new book. Invert it.

**Verb 2 — Extract.** Two tiers, because **the FE can only prove one of them upfront**:

| Condition | Knowable before the click? | Behaviour |
|---|---|---|
| Book has **0 chapters** (the zero-state) | ✅ **Yes** — `useBookChapters` returns `{ chapters }` (`hooks/useBookChapters.ts:64`), so `chapters.length === 0` is known without a call | **`disabled`** + inline reason: *"Needs chapters. This book has none yet."* |
| Book has chapters but **no parsed scenes** | ❌ **No** — `scenes_total` only comes back **in the decompiler's response**. There is no upfront parsed-scene count on any read surface plan-hub holds. | Leave **enabled**; keep the existing post-hoc `nothingParsed` copy (`PlanEmptyState.tsx:98`). |

> **Do not invent an upfront parsed-scene count for this.** It would need a new read surface; the zero-state tier is what clears the dead loop, and it is free. The finer tier stays post-hoc until a real need pays for it.

**Verb 3 — relabel.** *"Plan from scratch"* → **"Paste a plan you've already written"**. It opens `planner`, which cannot start from nothing (`PlannerPanel.tsx:120`). Keep the verb; stop lying about it.

### 3.3 The C16 pending path is not an edge case here

A **greenfield book is exactly the case C16 was built for.** If knowledge-service is down when verb 1 runs, `WorkSetupCta` already: creates a null-`project_id` Work, holds the surrogate id, polls `resolve-project`, and flips the gate on backfill. **The arc create (`POST /books/{id}/arcs`) is book-scoped and unaffected.** So the origin works even with knowledge down — inherit this by mounting the CTA, and it's free.

---

## 4. Contract changes

| Layer | Change |
|---|---|
| `plan-hub/api.ts` | **ADD** `createArc(bookId, body: {kind:'arc', title, …}, token)` → `POST ${COMP}/books/${bookId}/arcs`. Mirror `ArcCreate` (`arc.py:590`). |
| `plan-hub/hooks/usePlanNodeWrites.ts` | **ADD** the missing `create` verb beside `edit`/`archive`/`restore`. |
| `plan-hub/components/PlanEmptyState.tsx` | New primary verb; enable-conditions; relabel verb 3; **delete the false PH7 comment at `:15`**. |
| `studio/panels/PlanHubPanel.tsx` | Wire the new verb; keep `onPlanFromScratch` → `openPanel('planner')`. |
| `studio/components/StudioSideBar.tsx:34` | Pass `onNewChapter` → `host.openPanel('plan-hub', {focus:true})`. |
| i18n `studio` ns | `manuscript.newChapter` → `manuscript.openPlan`; new `planHub.empty.*` keys. **All 18 locales.** |

**No backend change. No schema change. No new panel.**

---

## 5. What NOT to build

- ❌ **A second lane canvas.** `laneLayout.ts:3` is law: *"never a second 'where does a node go' impl"*. plan-hub already renders lanes, spans (`span:{from_order,to_order}`), `is_contiguous` segmentation, collapse, windowing.
- ❌ **An overlap band.** `outline_node.structure_node_id` is a **scalar FK** (`migrate.py:1242`, `CHECK (… OR kind='chapter')`); `assign_chapters` is `UPDATE … SET structure_node_id = $1` — a **destructive re-home** (`structure.py:635`). **One chapter → one arc.** Overlap is not renderable. Changing that is a backend epic (join table + rewrite assign/`derived_blocks`/decompiler/conformance/MCP contract) and is **not in scope**.
- ❌ **A four-lane arc/chapter/scene/beat UI.** Post-lift `outline_node.kind IN ('chapter','scene')` (`arc_lift.py:287`); the service refuses to boot otherwise (`_assert_lift_applied`, `migrate.py:1891`). `arc`/`saga` live in `structure_node`; `beat` is a **`beat_role` badge** on a scene/chapter (`migrate.py:214`), not a node.
- ❌ **Reimplementing Work creation.** Mount `WorkSetupCta`.
- ❌ **A modal for naming.** Inline-type on the canvas.

---

## 6. Acceptance criteria

**The bar: a first-time user, on a clean account, creates a book and reaches a named structure without leaving the Studio and without pasting anything.**

| # | Criterion |
|---|---|
| **AC-1** | New book → Studio → the Manuscript `+` is **enabled** and its tooltip reads *"Plan this book"*. |
| **AC-2** | Clicking it opens **plan-hub**, focused. |
| **AC-3** | plan-hub on an empty book shows **"Start with your first arc"** as the **primary**, enabled. |
| **AC-4** | Clicking it creates the Work (+KG project) **and** an arc, and focuses it on the canvas — **no modal, no paste, no chapters required**. |
| **AC-5** | **Extract** is `disabled` with a visible reason when the book has **0 chapters** (provable from `useBookChapters`). With chapters but no parsed scenes it stays enabled and reports post-hoc — that tier is not knowable upfront and is **not** in scope. No dead button at zero (PH7, for real). |
| **AC-6** | Verb 3 is labelled to say it needs a written plan. |
| **AC-7** | **C16:** with knowledge-service stopped, AC-4 still yields an arc and a pending Work that backfills on recovery. |
| **AC-8** | Clicking "Start with your first arc" twice never mints a second Work (idempotent) and never a duplicate arc from one click. |

### 6.1 The tests must mount the caller, not the component

The bug shipped because `ManuscriptNavigator.test.tsx:165` **injected its own `onNewChapter`** and asserted it fired — proving the mechanism, never the wiring, while asserting `disabled===true` was correct.

| Test | Requirement |
|---|---|
| **T-1** | **Delete** `ManuscriptNavigator.test.tsx:165`. Replace with a test that renders **`StudioSideBar`** — the real consumer — and asserts the `+` is **enabled** and calls `host.openPanel('plan-hub', …)`. Only a test that mounts the chokepoint's *caller* catches this class. |
| **T-2** | A `PlanEmptyState` test asserting the primary verb is **enabled with zero data**, and that Extract is disabled **with a reason**. |
| **T-3** | **Live smoke on a CLEAN account** (not the 20-fixture test account — one finding in the audit was contamination from a veteran account). Drive AC-1→AC-4 in a real browser on the baked build. Unit-green is what let this ship. |

---

## 7. Out of scope / deferred

- **Should arcs overlap?** Open PO question. Today the schema forbids it. "Yes" ⇒ backend epic, rendered in plan-hub, never a rival canvas.
- **BUG-7 — `NodeKind` drift.** `app/db/models.py:37` and `types.ts:195` still advertise 4 kinds while the DB enforces 2 ⇒ `kind:'arc'` passes Pydantic and 400s at the DB. Fix alongside, but it is not the origin bug.
- **The prose door.** This spec routes `+` to the *spec*. A discovery writer who just wants a blank page still has only the Chapters tab. Worth a follow-up: a "just start writing" verb that creates a chapter via `booksApi.createChapterEditor` and opens the editor.

---

## 8. Process rules carried forward

1. **Quote the DDL, not the endpoint name.** The killed draft read `assign-chapters` and inferred many-to-many span semantics; the column is a scalar FK. It also quoted `migrate.py:196`'s `CREATE TABLE` text while a later `ALTER` superseded it. **Read every CHECK block.**
2. **Cold-start audits run on a clean account.**
3. **A shared affordance must be mounted everywhere its gate appears** — or it will be rebuilt, badly, by the next person. This is now the second time.
