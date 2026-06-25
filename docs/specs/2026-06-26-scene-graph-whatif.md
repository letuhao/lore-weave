# Spec — Scene-Graph What-If on Canvas (LOOM composition)

- **Status:** CLARIFY → DESIGN (spec only — **no build** this cycle; WS-B3 of the
  [LOOM debt-clearing plan](../plans/2026-06-25-loom-debt-clearing.md))
- **Date:** 2026-06-26 · **Branch:** `feat/composition-service` · **Size:** L/XL (own cycle)
- **Owner decision needed:** see §8 (one open product call before BUILD is scheduled)

---

## 1. Motivation

The Scene Graph ([`SceneGraphCanvas.tsx`](../../frontend/src/features/composition/components/SceneGraphCanvas.tsx))
shows scenes as a 2-D graph of typed causal edges. Today a writer who wants to explore
"what if this scene went differently" must leave the canvas and run the
**Divergence Wizard** (`useDivergenceWizard` → a persistent derivative Work). That is
heavyweight for a quick *visual* exploration: it mints a fresh knowledge project, a
new Work, and a whole derivative studio — before the writer even knows the branch is
worth keeping.

**The gap:** there is no **ephemeral, on-canvas** branch preview — a dashed alternate
sub-graph drawn *beside* canon, with a judge badge (coherence / tension / pacing vs
canon) per alternate node, that the writer can iterate on and only then **promote**
into the existing persistent derivative flow (or discard with zero residue).

This is the "dashed-branch-beside-canon + judge badge + promote/discard + per-node
alternate takes" feature deferred as **B3** — a genuine feature, not polish.

## 2. Guiding principle (resolves the wizard-overlap question)

The on-canvas what-if is **NOT a second persistence path**. It is an *ephemeral
preview* that **promotes into the SAME derivative flow** the wizard already uses
(`useWhatIfPromotion.promote()` → `compositionApi.deriveWork`). So:

- **Before promote:** nothing is persisted. The branch lives in component/ephemeral
  state only (like the existing `WhatIfDraft` — held in memory until the writer
  decides). Discard = drop the state, no DB write, no orphan nodes.
- **At promote:** reuse the exact `DeriveBody` path (`whatIfToDeriveBody` →
  `deriveWork`) — the branch's `branch_point` + divergence + entity overrides map onto
  the persistent derivative Work, which then owns real outline nodes in its own
  knowledge project. **No new derive contract.**

This keeps the wizard and the canvas as two *entry points* to one persistence model —
the canvas adds a visual, iterative, judged front-end; it does not fork the data model.

## 3. Scope

### V1 (this feature, when built)
1. **"What-if from here"** affordance on a selected scene node → opens an ephemeral
   branch anchored at that scene's `story_order` (the `branch_point`).
2. **Dashed alternate sub-graph** rendered beside canon on the existing `GraphCanvas`
   (reuse `renderNode`/`renderEdge`; alternate nodes get a dashed/tinted style + an
   `is_alternate` flag; they are NOT `OutlineNode`s yet).
3. **Per-alternate-node generation** → an alternate scene draft via the existing
   ghost path (`useGenerateChapter`/co-writer, `persist:false`) — preview, not saved.
4. **Judge badge** per alternate node: coherence / tension / pacing **vs canon**,
   reusing the WS-B1 critic infra (`useCritique` dims + the canon-gate verdict the
   `critic` panel already surfaces). One badge per alternate node + a branch-level roll-up.
5. **Promote** → `useWhatIfPromotion` (materialize the branch into a persistent
   derivative Work; the alternate nodes become real outline nodes in the derivative
   project). **Discard** → drop ephemeral state.
6. **Per-node "alternate takes"** — a node may hold N candidate drafts (the writer
   keeps/cycles); only the chosen take promotes.

### Explicitly OUT (deferred / won't-build-V1)
- **Persisting the ephemeral branch** before promote (no new tables; promote IS the
  persistence). If "save a branch without promoting" is wanted later → its own task.
- **Auto-insert** of alternate prose into the canon draft (honours the LOCKED
  no-auto-insert rule — alternates are ghosts the writer adapts/promotes).
- **Multi-branch diffing** (comparing two what-ifs side by side) — V2.
- **Collaborative/shared** what-ifs — follows the normal grant model once promoted; no
  special sharing for ephemeral branches.

## 4. Data model

**No new persistent tables for V1.** The ephemeral branch is a client-side shape:

```ts
type WhatIfBranch = {
  branchPoint: number;                 // anchor scene's story_order (→ DeriveBody.branch_point)
  taxonomy: DivergenceTaxonomy;        // reuses the wizard's taxonomy
  povAnchor: string | null;
  canonRules: string[];
  overrides: Record<string, Record<string, unknown>>;  // glossary_entity_id → field delta
  nodes: WhatIfNode[];                 // the dashed alternate scenes
};
type WhatIfNode = {
  id: string;                          // ephemeral client id (not an OutlineNode id)
  afterCanonSceneId: string;           // where it branches from / attaches
  takes: { id: string; ghost: string | null; jobId: string | null;
           judge: CriticVerdict | null }[];
  chosenTakeId: string | null;
};
```

On **promote**, `WhatIfBranch` → `WhatIfDraft` (`useWhatIfPromotion`) for the
divergence/override/branch_point fields, and the chosen takes → outline-node creates
in the derivative project (the one net-new BE need; see §6).

## 5. UX

- Selecting a scene → a "⑂ What-if from here" action (next to the existing link bar).
- The alternate sub-graph draws with **dashed edges + a tinted node chrome** so canon
  vs branch is unambiguous (reuse `GraphCanvas` `renderEdge`/`renderNode`; add an
  `alternate` style branch, mirroring the `DerivativeBanner` purple language).
- Each alternate node shows a **judge chip** (coherence/tension/pacing vs canon) using
  the WS-B1 badge styling; red/amber/green by threshold.
- A branch toolbar: **Promote** (→ derivative) · **Discard** · per-node **Generate
  take** / **cycle takes**.
- i18n ×4 under a new `scenegraph.whatif.*` namespace.

## 6. Backend touch (minimal)

V1 needs **one** real BE capability beyond what exists: on promote, create the chosen
alternate scenes as outline nodes in the **derivative** project. Two options (decide at
that cycle's CLARIFY):
- **(a)** reuse the existing outline-node create API (`createNode`) against the
  derivative `project_id` after `deriveWork` returns — **no new endpoint** (preferred).
- **(b)** a batched `/works/{id}/whatif/promote` that derives + seeds nodes in one txn
  (only if (a)'s multi-call sequence proves racy).

Everything else (derive, divergence_spec, entity_override, the ghost generate, the
critic/canon-gate) **already exists** — this feature is mostly FE + orchestration.

## 7. Acceptance criteria

1. "What-if from here" on a canon scene opens an ephemeral branch at that scene's
   `story_order`; **nothing is persisted** until promote.
2. Alternate nodes render visually distinct (dashed/tinted) beside canon; canon edges
   unchanged.
3. Generating a take yields a **ghost** (persist:false); a judge badge shows
   coherence/tension/pacing vs canon.
4. **Discard** leaves zero residue (no Work, no outline nodes, no knowledge project).
5. **Promote** produces a persistent derivative Work via the existing `deriveWork`
   path, with the chosen takes as outline nodes in the derivative project, and the
   branch_point/divergence/overrides carried through (parity with the wizard).
6. The on-canvas flow and the Divergence Wizard converge on the **same** derivative
   model (no second persistence path).

## 8. ⚠ Open product call (one decision before BUILD is scheduled)

**Does the on-canvas what-if get built, or is the Divergence Wizard the canonical
what-if and the canvas version a conscious won't-build?** This spec recommends
**build it** as the ephemeral→promote front-end above (it adds real value: visual,
iterative, judged, zero-residue exploration that the wizard can't offer), scheduled as
its **own** L/XL CLARIFY→BUILD cycle. If the answer is *won't-build*, record B3 as a
conscious won't-build (gate 5) with the wizard as the canonical path, and this spec
becomes the rationale.

## 9. Risks / notes

- **Ephemeral-state size** — a branch with many takes holds ghost prose in memory;
  bound the take count + lazy-drop unchosen takes on promote.
- **Judge cost** — judging every take is N critic calls; debounce / judge-on-demand
  (only the chosen take auto-judges) to control spend.
- **Position model** — alternate nodes need layout coords that don't collide with
  canon; extend `sceneGraphLayout.autoLayout` with a branch lane, persisted only at
  promote (into the derivative's `work.settings.scene_graph`).
- This is **FE-heavy, BE-light** — the heavy lifting (derive, critic, ghost) is built;
  the work is the canvas branch model + the promote bridge.
