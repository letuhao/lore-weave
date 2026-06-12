# Standalone knowledge-service UI — full UX review (the un-reviewed screens)

**Date:** 2026-06-13
**Scope:** The knowledge-service as its **own** surface (`/knowledge`: ProjectsTab + state machine, the
build-graph journey, ExtractionJobs, Entities/Timeline/RawDrawers/GlobalBio, entity edit/merge). Completes the
coverage that the 4-issue QoL plan and the composition review left open.
**Status:** Review. Findings framed as *missing features* (your premise: architecture is sound, features are missing).

> Coverage note: this is the dedicated standalone pass you asked for. The earlier `…knowledge-fe-ux-qol-gaps.md`
> only covered the 4 issues you reported (rerank register/discover, book picker, dialog viewport). This doc
> covers everything else on the knowledge surface.

---

## 0. Headline: the standalone knowledge UI is **mature** — but has 2 hidden hard gates, a dead-end, and one big missing feature

Good news first: this surface is **more built-out than expected.** The project **state machine is excellent**
(13 well-defined states, valid-transition table, no dead-ends within the machine), **polling is smart**
(2s active / 10s history, conditional), **error/empty/loading states exist on nearly every screen**, and
Entities/Timeline/Bio/RawDrawers are **real, production-grade UIs**, not stubs. This is not "FE not wired."

The problems are concentrated and specific:

1. **Two hidden HARD gates on building a graph** — and they, not rerank, are why you couldn't build.
2. **A dead-end after the graph is "Ready"** — no path from a built graph to exploring it.
3. **No visual graph** — the single biggest missing feature for a worldbuilder.

---

## 1. ⭐ The real reason you couldn't build the knowledge graph (correcting the diagnosis)

You said: *"I can't register a reranker and build the knowledge graph."* The standalone review shows the build
blocker is **not rerank** — rerank is **optional and per-project**, never required to build (it's a
`ProjectFormModal` setting; absent → raw-search just skips a step; it's **not even present** in the build
dialog). The actual gates on `BuildGraphDialog` are:

### Gate A — **Embedding model is REQUIRED** (hard), with no in-dialog recovery
- Confirm is disabled unless an embedding model is chosen: `BuildGraphDialog.tsx:254-255`
  (`embeddingModel !== null && embeddingModel !== ''`). The BE returns **422** if `embedding_model` is omitted
  (`api.ts:118-127`). So **no embedding model → cannot build, period.**
- If you have none registered, `EmbeddingModelPicker` says *"No embedding-capable models configured. Add one in
  AI Models → Credentials"* (`EmbeddingModelPicker.tsx:160-163`) — but there's **no link/CTA to add one**; you
  must leave, register, and come back. (Note: embedding **is** a registrable capability flag — unlike rerank —
  so the register form itself works for embedding.)

### Gate B — **The benchmark gate** (the obscure one)
- Even with an embedding model chosen, Confirm stays disabled until that model has a **passing golden-set
  benchmark run**: `BuildGraphDialog.tsx:247-249`; badge *"No benchmark yet — run the golden-set benchmark to
  enable extraction"* (`EmbeddingModelPicker.tsx:197-200`), with an inline "Run benchmark" button.
- This is a **second, non-obvious prerequisite** buried in a sub-picker. A worldbuilder has no way to know
  "register embedding → run benchmark → pass → then build" is the required chain.

**Corrected prerequisite chain to build a graph:** LLM model (required) + **embedding model (required)** +
**passing benchmark (required)** + rerank (*optional*, per-project, for junk-rejection only). Plus the build
dialog is a tall `FormDialog` → **BL-4 viewport overflow** can hide the estimate/Confirm.

So: fixing rerank alone would **not** have unblocked you. Gates A+B are the wall. This reframes priority.

---

## 2. Prioritized findings (the standalone knowledge gaps)

Severity: **P0** = blocks/dead-ends the worldbuilder · **P1** = significant friction / missing core feature ·
**P2** = polish.

### P0

**KN-1 — Build gates have no in-flow recovery (embedding-missing, no-benchmark, chat-model-missing).**
Each gate dead-ends with "go to AI Models" text but **no link**, and the benchmark gate is nearly invisible.
*Fix:* in `BuildGraphDialog`, when embedding/LLM list is empty → inline "**Add a model →**" CTA (deep-link +
return); surface the benchmark requirement as a clear inline step with the Run-benchmark button promoted, not
buried in the picker. Refs: `BuildGraphDialog.tsx:247-258,416-454`, `EmbeddingModelPicker.tsx:154-200`.

**KN-2 — Dead-end after "Ready": a built graph has no path to explore it.**
The `complete` state card shows stats (entities/facts/events/passages) but they're **not clickable** and there's
**no "Browse entities / View graph" action** — only Extract-new / Rebuild / Change-model / Delete / Disable.
The user must independently discover the Entities/Timeline tabs and re-pick the project from a filter.
*Fix:* make the stats line link to `/knowledge/entities?project=…`; add a primary "**Explore graph**" CTA on
the complete card. Refs: `state_cards/CompleteCard.tsx:25-32`.

**KN-3 — Build dialog is a tall `FormDialog` → viewport overflow (instance of BL-4).**
7 fieldsets + cost estimate, no `max-h`/scroll → on short/mobile viewports the estimate and Confirm can fall
below the fold. *Fix:* the shared `FormDialog` `max-h`+scroll fix (BL-4) resolves this and BuildGraph together.

### P1

**KN-4 — No visual graph / relationship visualization anywhere.**
Confirmed: **no** d3/cytoscape/canvas/SVG network view exists. Relations are **flat in/out lists** in the entity
detail panel; Timeline is a text table; "BuildGraphDialog" is misleadingly named (it *starts extraction*, it
doesn't visualize). For a *worldbuilder*, relationships ARE the world — forcing them to mind-model the graph
from text lists is the headline missing feature. *Fix (new feature):* a graph/relationship canvas (entities as
nodes, relations as edges, multi-hop navigation), reusing the composition `RelationshipMap`/`SceneGraphCanvas`
patterns if present. Refs: `EntityDetailPanel.tsx:311-355` (flat lists).

**KN-5 — No feedback after build submit.**
`handleConfirm` closes the dialog with no toast/scroll; the job appears in the Jobs tab only on the next 2s
poll. User may not realize the build started. *Fix:* success toast + route/scroll to the running job.
Refs: `BuildGraphDialog.tsx:279-280`.

**KN-6 — Destructive actions under-communicated.**
`ChangeModelDialog` warns the graph will be deleted but **omits the re-extraction cost** (`ChangeModelDialog.tsx:127-139`);
`ModelChangePendingCard` confirm button says only *"Confirm"* for a destructive delete-and-rebuild
(`state_cards/ModelChangePendingCard.tsx:27-29`). *Fix:* state the cost ("re-extracting the whole graph"); rename
to "Delete & rebuild".

**KN-7 — `building_paused_budget` says "raise the cap and resume" but offers no UI to raise it.**
User must leave to change the cap, then return. *Fix:* inline "Raise budget cap" action.
Refs: `state_cards/BuildingPausedBudgetCard.tsx:22-35`.

**KN-8 — Errors are shown but not actionable from where they appear.**
`ErrorViewerDialog` is copy-for-bug-report only; Retry lives elsewhere (`JobDetailPanel`). *Fix:* add Retry to
the error viewer, or fold the viewer into the detail panel. Refs: `ErrorViewerDialog.tsx:20-95`.

### P2 (polish / scale)

- **KN-9 "Ready" label is ambiguous** for the `complete` state — prefer "Complete / Graph built". (`CompleteCard`)
- **KN-10 No ETA for first ~7s** of a running job (EMA needs samples) → show "Calculating…". (`useJobProgressRate.ts:53`)
- **KN-11 Indeterminate bar** ("250 / ?") when `items_total` null — label "total unknown". (`JobProgressBar.tsx:96-103`)
- **KN-12 Stale "Ignore" is client-only** → reappears on reload; clarify or persist. (`StaleCard`)
- **KN-13 Projects list >100 is a silent dead-end** ("full pagination lands with Track 2", no Load-more). (`ProjectsTab`)
- **KN-14 No live refresh** of the projects list (manual only); no "last refreshed" stamp. (`useProjects.ts`)
- **KN-15 Mobile hides Entities/Timeline/Raw** behind a "use desktop" banner — discovery gap. (`MobileKnowledgePage`)
- **KN-16 Entity merge is non-reversible**, no unmerge; tight `max-h-48` candidate scroll. (`EntityMergeDialog`)
- **KN-17 Truncated relations** ("N/M") with no in-panel search/filter to see the rest. (`EntityDetailPanel:318-328`)
- **KN-18 Glossary-conflict on merge** surfaces an error with no guidance on the two-layer glossary↔knowledge model. (`EntityMergeDialog:78`)
- **KN-19 Timeline has no spoiler handling** — raw summaries rendered as-is (relevant to the N-L reader-spoiler gap).

### P1 (added 2026-06-13 — verified directly)

**KN-20 — The Projects screen is a state-dashboard, not a CRUD browser; and there's no project detail view.**
The projects list (`ProjectsTab`) is a flat card-stack with **no search, no sort, no real pagination** (single
`limit:100` fetch — the existing backend cursor is unused; `hasMore` only renders a static "first 100" note,
`useProjects.ts:10-30`), and **filter = only a "Show archived" toggle** (`ProjectsTab.tsx:99-107`). There is
**no project detail page/panel** — a row isn't clickable; "detail" is the inline state card + the edit *form*,
and the graph's contents (entities/timeline/raw) live in **separate top-level tabs** filtered by a dropdown,
not a drill-in. Built for "a handful of projects" (hook comment) → won't scale for a worldbuilder; and the
missing detail compounds **KN-2** (no path from a Ready project into its graph). *Fix (RAID C6+C7):* a project
**detail view** (state+stats+links into entities/graph) + list **search/sort/filter-by-state/real-pagination**.
*Refs:* `ProjectsTab.tsx`, `ProjectRow.tsx`, `useProjects.ts`.

---

## 3. What's genuinely solid (don't touch)
- **Project state machine** (13 states, transition table, per-state cards with clear actions) — `types/projectState.ts`.
- **Polling strategy** (2s active / 10s history, conditional, stale-on-error) — `useExtractionJobs.ts`, `useProjectState.ts`.
- **Cost transparency at build time** (estimate range + item breakdown + duration, debounced) — `BuildGraphDialog.tsx:493-537`.
- **Entities / Timeline / GlobalBio / RawDrawers** — real, filterable, paginated, with empty/error/loading states.
- **Version-conflict (412) handling** on entity/bio edits.

---

## 4. Updated blocker picture (for the register in the use-cases doc)

New rows to add to `2026-06-13-writer-persona-use-cases-scenarios.md §5A`:

| # | Missing capability | Type | Who | Ref |
|---|--------------------|:----:|-----|-----|
| BL-16 | **Build gates need in-flow recovery + visible benchmark step** (embedding required + golden-set benchmark required; both dead-end) | **B** | N-B, P2 | KN-1; `BuildGraphDialog.tsx:247-258` |
| BL-17 | **"Explore graph" path from a Ready project** (built graph → entities/timeline is a dead-end) | **B** | N-B, P2 | KN-2; `CompleteCard.tsx:25-32` |
| BL-18 | **Visual graph / relationship view** (only flat lists exist) | **B** (feature) | N-B, P1, P2 | KN-4; `EntityDetailPanel.tsx:311-355` |

**Diagnosis correction for the register:** BL-1/BL-2 (rerank) are **not** the build blocker — **BL-16 (embedding
+ benchmark gate)** is. Rerank is optional/per-project. Re-rank the worldbuilder unblock order accordingly:
**BL-16 → BL-17 → BL-3 (book picker) → BL-4 (viewport)**, then BL-1/BL-2 (rerank, for junk-rejection quality),
then BL-18 (graph viz, the big feature).

---

## 5. Recommended next actions
1. **Verify the build gates live** with the test account: open Build graph with **no embedding model** → expect
   Confirm disabled + the "add in AI Models" dead-end (KN-1); register an embedding model → expect the
   **benchmark gate** (KN-1/Gate B). This confirms the corrected diagnosis end-to-end.
2. **Bundle the worldbuilder unblock**: KN-1 (in-flow model add + visible benchmark), KN-2 (explore-graph CTA),
   KN-3/BL-4 (dialog scroll) — one FE pass; this is what actually lets you build *and then use* a graph.
3. Treat **KN-4 (visual graph)** as a scoped feature, not a fix — it's the worldbuilder's headline want.
