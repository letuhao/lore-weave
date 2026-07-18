# Spec — Studio Onboarding Door & Structure Coherence

**Status:** `CLARIFY` — grounded in code; **one architectural fork (Part C) needs the PO's call** before PLAN.
**Origin:** the deferral left by the round-2 newcomer-polish build (M9/F10) —
> *"the deeper 'one shared door across Plan + Divergence + Reference shelf' unification stays with F6's
> hierarchy-unify track (gate #2, structural)."*
The PO's direction (2026-07-18): **clear all of it, don't leave a permanent defer.** This spec turns
that deferral into a buildable, honestly-sized plan.

**Companion:** [round-2-feedback.md](../2026-07-18-writing-studio-newcomer-polish/round-2-feedback.md)
(F8–F10, shipped) and the round-1 spec's **F6/C** ("unify into one spine", scoped XL).

---

## The problem, grounded in code

Two independent facts, both verified:

1. **Empty-state affordances are inconsistent (a UI problem).** The Studio has **~19 gated empty
   states**. After M7/M9 they use **four different patterns** for the identical job "this book isn't
   ready — help the user make it ready":
   | Pattern | Where | Quality |
   |---|---|---|
   | Inline create (`WorkSetupCta`) | Quality family (`QualityWorkGate`), Decompose, Reference-shelf, Style-voice | ✅ good |
   | Redirect to Compose | `PlaceGraphPanel` → `openPanel('compose')`, copy *"Set up the co-writer in Compose"* | ⚠️ punts; stale jargon |
   | Open plan-hub | Plan rail (M7) | ✅ ok |
   | Bare dead text | `DivergenceManagerView`, `WhatIfCanvasPanel` "no plan yet" | ❌ dead end |
   Plus vocabulary drift: "Set up writing" (M9) vs "Set up co-writer" (PlaceGraph/comments).

2. **There are genuinely two prerequisites, and they live in two services (a data problem).**
   - A **plan** = `structure_node` arcs, **book-scoped** (composition-service). Created by `createArc`.
   - A **Work** = a composition Work + a knowledge `project_id`. Created by idempotent `POST /books/{id}/work`.
   - Manuscript **parts/acts** = a book-service grouping over chapters (`part_id` + `structural_path`,
     `book-service/internal/migrate/migrate.go:268`), a **third** structure concept.
   - **There is NO link between book-service parts and composition arcs.** They are two hierarchies in
     two services, related only in the user's head. This is F6/C's structural core.

A book can therefore be "Work but no plan" or "plan but no Work" or "parts but neither" — so one surface
lights up while its neighbour still gates, which is exactly the incoherence the newcomer hit.

`usePlanOrigin.start()` already creates **arc + Work together, idempotently, outage-safe**
([usePlanOrigin.ts](../../../frontend/src/features/plan-hub/hooks/usePlanOrigin.ts)) — the seam the
onboarding half reuses.

---

## Scope — three parts, sequenced cheapest-first

### Part A — The unified onboarding door  *(buildable now · ~M · FE-only)*
Replace the four ad-hoc patterns with ONE component and ONE readiness signal.

- **A1 · `useBookReadiness(bookId)`** — one hook returning `{ hasWork, hasPlan }` (composes the existing
  `useWorkResolution` + `getArcs`). Every gated surface reads the same truth; no surface re-derives it.
- **A2 · `<BookNotReadyDoor prerequisite="work"|"plan"|"either">`** — a shared empty-state component:
  guided copy (why it's empty) + a **primary** button for the surface's own need (`WorkSetupCta` for
  work-gated; "Plan this book" → `openPanel('plan-hub')` for plan-gated) + an **optional secondary**
  "Set up everything" (Part B). One vocabulary, one look, degrade-safe.
- **A3 · Mount it everywhere**, retiring the ad-hoc variants: Reference-shelf, Style-voice, Quality
  family, Places (drop the redirect-to-Compose), Flywheel, Progress, WhatIf, Divergence, Plan rail.
- **Acceptance:** no gated Studio empty state is a dead end, a redirect-instead-of-create, or off-vocab;
  all read one readiness signal.

### Part B — One "Set up this book" primitive  *(buildable now · ~S–M · FE + reuse)*
Kill the "Work-but-no-plan" incoherence by offering a single action that satisfies **both** families.

- **B1 · "Set up this book"** = idempotent create-Work **+** minimal-plan, reusing `usePlanOrigin.start()`.
  Surfaced as A2's secondary ("Set up everything") and as the first-run primary. After one click every
  Story-Bible surface lights up together.
- **B2 · Decision (sealed in this spec):** do NOT auto-onboard every book on Studio open — a prose-first
  writer who only wants to draft shouldn't be forced an arc. Onboarding stays an **explicit** action;
  each surface still offers its own single-prerequisite door too (via A2's primary).
- **Acceptance:** from any gated surface, one "Set up this book" click makes the book satisfy every
  Studio prerequisite; the narrow single-prerequisite door remains available for users who want only it.

### Part C — Structure coherence (the real F6/C)  *(the architectural fork — see below)*
The two structure hierarchies (book-service **parts** ↔ composition **arcs**) have no relationship.
Round-1 M5 already fixed the *naming* confusion (Part vs Arc + explainer). Part C decides whether/how to
make them **navigably coherent**. **This is the one decision the PO must make** — it swings the size 5×.

---

## The Part-C fork (PO decision required)

| Option | What it does | Size / risk | Recommendation |
|---|---|---|---|
| **C-merge** | Rip out one hierarchy; make parts *be* arcs (or vice-versa). One structure model. | **XL+**, destructive cross-service migration, rewrites S-02 parts + composition plan + both UIs + contracts. High regression risk. | ❌ **Against.** They serve different purposes (parts = manuscript reading-grouping; arcs = generation spec). Merging conflates two real concepts to remove a naming smell already fixed in M5. |
| **C-bridge** (rec) | Keep both models; add an **additive, nullable link** parts↔arcs + a coherent cross-referencing UI. Nothing is ripped out. | **L**: one additive migration (nullable FK, NULL-safe backfill), one cross-service read, UI cross-links. Additive ⇒ low regression risk. | ✅ **Recommended.** Delivers the coherence ("this Part maps to this Arc", navigate between) without a destructive migration. |
| **C-presentation-only** | No data link at all; the Manuscript and Plan rails just cross-reference by naming/'⌘P' jump, and an explainer. | **S–M**, FE-only. | Fallback if the PO wants minimal structural work — but without a link it stays "two things shown side by side", not truly coherent. |

**Recommended: C-bridge**, decomposed so it's buildable, not "structural ⇒ defer":
- **C1** · additive nullable `arc_id` on `book_parts` (book-service) — or a `part_id` on the arc
  `structure_node` (composition); NULL-safe, no backfill required, contract-first (glossary-style route
  conformance applies to book-service). *BE, one migration.*
- **C2** · a cross-service read (`api-gateway-bff`) so the Studio can resolve "Part → its Arc" and back.
  *BE/gateway.*
- **C3** · UI coherence: the Manuscript rail's Part header shows its linked Arc (and the Plan rail's Arc
  shows its Parts), with a click to jump between; a "link this Part to an Arc" affordance. *FE.*
- **C4** · conscious record: whether a *full* merge (C-merge) is ever wanted is left as an **explicit,
  documented decision**, not a silent defer — the bridge makes it unnecessary for the known pain.

---

## Sizing & sequencing

Whole track ≈ **L–XL** (A: M · B: S–M · C-bridge: L). Multi-milestone, **not** one BUILD. Cross-service
live-smoke mandatory for C (FE ↔ gateway ↔ book-service ↔ composition). Build order:

1. **Part A** (door + readiness hook) — highest user value, FE-only, no dependency. Ships the visible fix.
2. **Part B** (one "Set up this book") — small, reuses `usePlanOrigin`; layers onto A's secondary slot.
3. **Part C-bridge** — the structural remainder, only after the PO picks the C option. C1→C2→C3, each
   its own slice with contract-first + live-smoke.

Each milestone follows the established QC-per-slice discipline: tsc 0, unit green, i18n gap-fill,
**live QC on the isolated static build (`vite build` → `vite preview`, never `vite dev`)**, `review-impl`
on the cross-service (C) slices.

## What "clear all" means here (honest)
- **A + B fully clear** the user-visible incoherence (dead ends, redirects, "Work-but-no-plan"). Buildable now.
- **C-bridge clears** the F6/C structural deferral *without* a destructive merge — the deferral is
  retired, not re-parked.
- The only thing that remains a *conscious* decision (C4) is whether to ever fully MERGE the two
  hierarchies — recommended against, recorded, not silently deferred.

## PO decision (sealed 2026-07-18): **C-merge (full)** — one structure hierarchy, no bridge.
The PO chose the full unification over the recommended bridge: there should be **one** structure for a
book, not two related ones.

### What C-merge MUST resolve (the architect's constraint)
Parts and Arcs are on **opposite sides of the LOCKED language rule (I3)** and in **two services**:
- **Parts** → `book-service` (Go, domain/meta) — manuscript grouping over chapters (`part_id`, `structural_path`).
- **Arcs** → `composition-service` (Python, AI/plan) — the saga→arc→sub-arc generation spec.

So the merge cannot be "pick a table and migrate" — it must be **one structure SSOT, the other
reconceived**, and *which side wins* is the design's central decision:
- **Arcs win (SSOT → composition):** richer model, already drives generation; parts become a
  derived/migrated read-view. Cost: book structure shifts into the AI service (boundary justification needed).
- **Parts win (SSOT → book-service):** structure stays in the Go domain with chapters; arcs rebuilt on
  top. Cost: large rewrite of composition's plan ownership.

This is a **destructive, cross-service data migration touching a LOCKED invariant** — the highest-risk
class of change here. **Gate: a dedicated C-merge DESIGN (SSOT choice · migration · cutover sequence ·
contract changes · rollback) + `/review-impl` on every slice, signed off by the PO BEFORE any data is
touched.** Non-negotiable per the repo's debugging/quality discipline.

### Revised sequencing under C-merge
1. **Part A** (onboarding door) — build now; independent of C, survives the merge (the door pattern
   persists; only the readiness computation adapts).
2. **Part B** (one "Set up this book") — after A; note its plan+Work distinction **collapses** once
   C-merge lands (one structure ⇒ one prerequisite), so keep B thin and expect simplification.
3. **Part C-merge** — DESIGN first (blast-radius map across book-service · composition · gateway · FE →
   SSOT choice → migration → cutover), PO sign-off, THEN build additive→migrate→cutover→remove, each
   slice contract-first + cross-service live-smoke + `/review-impl`.

## Next artifact
`docs/specs/2026-07-18-studio-onboarding-and-structure-coherence/c-merge-design.md` — the blast-radius
map + SSOT decision, authored before any Part-C build.
