# LOOM Composition — Debt & Drift Clearing Plan

**Date:** 2026-06-25 · **Branch:** `feat/composition-service` · **Author:** composition track close-out

Consolidates every open deferral the LOOM track recorded (in commit messages only — this
doc is now their tracked home) **plus** the draft-vs-implementation drift found at close-out,
and lays out a **design + execution plan** to clear them. Source: the deferral audit + the
mockup-drift review (2026-06-25), after the windowing epic T5.4 (M1–M4) shipped and a live
browser-smoke cleared the windowing smoke-gap + fixed a HIGH pop-out crash (`32de0628`).

**Organizing principle:** group by **shared root cause / design**, not by origin task;
prioritize by *(user value × cheapness)* and unblock-ability.

---

## Workstreams

### WS-A — Live-smoke sweep · **P0** — ✅ **CLEARED 2026-06-25** (all 3 smokes PASS, no bug surfaced)
The dev stack + browser harness work now (proven 2026-06-25). These rows were *blocked-on-harness*,
not code — cleared by running the smoke against the running stack and recording evidence.
- ✅ `D-T3.6-LIVE-SMOKE` — **CLEARED.** Via gateway as the test account on Work `019ef35e-d08f-…`
  (book Dracula `019ef35c-…`, scene "The road to the Borgo Pass"): POST a reference → real
  provider-registry embed (bge-m3, **dim 1024**) stored + first-add write-through set
  `work.settings.reference_embed_model`; per-scene `GET …/scenes/{id}/references` returned the hit
  (**score 0.65**, scene auto-query); a focused in-container one-shot ran the LIVE
  `gather_references → build_segments → render` path and the passage landed inside the rendered
  **`<references>`** block with `[title — author]` attribution. End-to-end embed→retrieve→pack proven.
- ✅ `D-T4.1-LIVE-SMOKE-FULL-CHAIN` — **CLEARED (real production path).** Published Chapter II of the
  test book with novel prose (new entities Magda Petrescu / Cursed Spring of Saint Wenceslas) →
  **worker-ai auto-enqueued a `chapters_pending` drain ~20s later** (the real publish→extract trigger,
  CM3b coalescing drainer) → Pass-2 extraction → Neo4j merge with `created_job_id` stamped → the
  FlywheelPanel endpoint (`GET /v1/knowledge/projects/{pid}/flywheel`) returned a **non-empty delta**:
  `entities_added=2, relations_added=2, events_added=2` with correctly-named `new_items`.
  **Note (not a bug):** the flywheel attributes the delta to the *latest complete* job — a manual
  `extraction/start` run concurrently with the auto-drain split the stamps across two jobs (showed
  "+0 entities" until the clean single-job path was run). The baseline glossary-sync job's 0-delta is
  correct-by-design (non-Pass-2 path, NULL `created_job_id`). Stamping verified working on the deployed image.
- ✅ `D-T5.4-POPOUT-SHARED-SSE-BROWSER-SMOKE` — **CLEARED (Playwright, 2-window).** Editor → Compose →
  Pop out: popout opens as its own OS window/root and renders Compose correctly (**no blank-window
  crash — the `32de0628` HIGH fix holds**); URL carries `book/chapter/panel/scene` but **no token**.
  Generated a real Gothic draft via the SharedWorker (the SSE fetch runs in the worker, NOT the page —
  `performance.getEntries` in the popout shows no generate request). **Survive-close:** regenerated,
  closed the opener tab mid-run → the popout independently completed a fresh draft. **Late-join:** opened
  a 2nd popout (direct nav, NOT a reload) → it inherited the shared ghost draft from the worker on
  connect without generating → also demonstrates **fan-out** (two windows, one worker stream, identical
  state). Did not reload the popout (preserves the `window.open` handle, per the harness caveat).
- 🟡 `D-T5.4-POPOUT-WORKER-HEALTHCHECK` — still WS-D (the worker `onerror` surface ships; the full
  ack-timeout degrade is the WS-D task). Live behaviour observed OK (worker loaded + acked).

**Size:** 4 × S (execution) — done in one continuous pass. **Already cleared earlier:** dock/float/popout
open+render, no-token-in-URL.

### WS-B — Drift feature gaps (drafted but not built as designed) · **P1**
The substantive "real" debt — features the mockups promised that diverged in the build.

- **B1 · Continuity Critic standing panel** — **M.** The capability already exists as `CriticFlags`
  inline in `ComposeView` (Coherence/Voice/Pacing/Canon, advisory). Surface it as a dockable `critic`
  SubTab: render the latest generation's verdict + a "re-check current draft" action; reuse `CriticFlags`
  + the canon-gate verdict. Slots into the existing dock/float/popout system for free. *Mostly relocating
  existing logic, not new scoring.*
- **B2 · Doujin / derivative completeness** — **M** (3 parts; data already exists in the derivative ctx):
  - **B2a** richer `DerivativeBanner`: override-summary chip + POV chip + a "⚙ Divergence spec" popover
    (Source / Branch point / POV / Overrides / Inherits / +Add transform).
  - **B2b** grounding "**was X → now Y**" deltas in `DerivativeGroundingLayers` (override stores old+new;
    surface the diff next to the OVERRIDDEN badge).
  - **B2c** the "**✦ Adapt with overrides / Write fresh**" AI-retell card. ⚠ **DECISION NEEDED** — this was
    *deliberately* LOCKED off ("no-auto-insert"). **Recommendation:** keep manual adapt as default; add
    "Adapt with overrides" as an explicit action that generates into the **ghost** (not auto-insert),
    honouring the existing accept-gate. This delivers the drafted affordance *without* breaking the lock.
- **B3 · Scene-graph what-if on canvas** — **L/XL, its own spec.** The dashed-branch-beside-canon +
  judge badge (coherence/tension/pacing vs canon) + promote/discard + per-node "alternate takes". This is
  a genuine feature, not polish. It overlaps the existing `DivergenceWizard`/derivative path: design the
  on-canvas version as an **ephemeral branch preview** that can *promote* into the existing persistent
  derivative flow. **Recommend a dedicated CLARIFY→spec**, not lumped with debt.

### WS-C — ProseMirror position/mark remapping (one root cause) · **P2**
`D-T3.2-SELECTION-RANGE-MAP`, `D-T3.3-GHOST-POS-MAP`, `D-T5.3-SPLIT-ON-EDIT` all stem from the same
thing: positions/marks captured against a doc snapshot drift when the doc is edited *during* a stream or
selection-edit. **Design:** one shared remap utility over PM's `Transform.mapping`/`StepMap` to map stored
positions through intervening transactions; apply at all 3 sites + the existing provenance mark split.
**Size:** M–L (PM mapping is subtle — needs a careful design + tests). One coherent change, not three.

### WS-D — Multi-window robustness · **P2**
- `D-T5.4-PANEL-STREAM-HOIST` — **S–M.** Hoist remaining un-hoisted panel async (e.g. an in-flight Assemble
  stitch) into `LiveStateContext`/the worker, mirroring M1 + Slice B.
- `D-T5.4-SERVER-SYNC` — **M.** Workspace layout → server prefs (`/v1/me/preferences`) so it follows the user
  across devices (currently per-device localStorage).
- `D-T5.4-POPOUT-WORKER-HEALTHCHECK` — **S.** Ack-timeout degrade if the worker loads-but-never-acks (the
  `onerror` surface ships; this is the full fallback).
- `D-T5.4-EDITOR-MULTIWINDOW` — **L.** A fully independent 2nd editor view. Likely **won't-fix for V1**
  (the studio panels pop out; the manuscript itself staying single-window is acceptable).

### WS-E — Small polish + a11y batch · **P3** (quick wins, one cycle)
Batch the LOWs: `D-T3.1-SCENE-HINT`/`GUIDE-APPEND`, `D-T3.3-SLASH-CONTINUE`/`CHAPTER-CONTINUE`,
`D-T3.4-CHAPTER-MODE-PINS`/`EXTRA-CANON`/`LORE-CHUNK-ID`, `D-T5.1-*` (focus-mode toggles),
`D-T5.3-COUNT-SEMANTICS`/`VISIBILITY-DOM-CLASS`, `D-T5.5-ESC-PROPAGATION`/`FOCUS-TRAP`.
**Highest value in here: the a11y pair** (`ESC-PROPAGATION`, `FOCUS-TRAP`) on the power-view/float overlays.
**Size:** M (a sweep).

### WS-F — Blocked / deferred-by-design · **P4** (no action now)
- `D-T5.2-WINDOWED-MENTIONS` — **blocked** on `D-P2-PER-SCENE-FANOUT` (knowledge track: no per-chapter
  mention edges exist yet). Re-evaluate when that lands.
- `D-T5.4-MOBILE`, `D-T5.5-MOBILE-SWITCHER` — desktop-first by design; a dedicated mobile pass later.

---

## Recommended execution order

| # | Workstream | Why here | Size |
|---|---|---|---|
| 1 | **WS-A** live-smokes | cheapest, highest confidence, may surface bugs → flush first | 4×S |
| 2 | **WS-B1** Critic panel + **WS-B2** doujin completeness | real user-facing gaps, mostly surfacing existing logic | 2×M |
| 3 | **WS-E** polish + a11y batch | quick wins; a11y matters for the new overlays | M |
| 4 | **WS-C** PM position-mapping | robustness; one design fixes three rows | M–L |
| 5 | **WS-B3** scene-graph what-if | biggest feature; its own CLARIFY→spec | L/XL |
| 6 | **WS-D** multi-window hardening | as the multi-window usage proves out | mixed |
| — | **WS-F** | leave blocked / mobile pass later | — |

## Open decisions for the PO
1. **B2c** — build "Adapt with overrides" as a ghost-generating action (recommended), or keep the
   no-auto-insert lock and drop the drafted card?
2. **B3 scene-graph what-if** — schedule as a dedicated feature spec, or accept the wizard-based
   derivative flow as the canonical "what-if" and record the on-canvas version as a conscious won't-build?
3. **WS-D editor-multiwindow** — confirm won't-fix for V1.

## Status
- **4 deferrals resolved** (D-C16-NULL-WORK-ROUTE explicit; THREADS-GATE / POPOUT-SHARED-SSE /
  POPOUT-SURVIVE-CLOSE within the T5.4 chain).
- ✅ **WS-A live-smoke sweep CLEARED 2026-06-25** — all 3 smokes (`D-T3.6-LIVE-SMOKE`,
  `D-T4.1-LIVE-SMOKE-FULL-CHAIN`, `D-T5.4-POPOUT-SHARED-SSE-BROWSER-SMOKE`) PASS on the running stack;
  **no code bug surfaced** (the flywheel "+0 entities" was a concurrent-manual-job test artifact, not a
  defect). `D-T5.4-POPOUT-WORKER-HEALTHCHECK` rolls into WS-D.
- ✅ **WS-B1 SHIPPED** (`b4eaef5a`) — Continuity Critic standing panel (popout-capable via re-fetch).
- ✅ **WS-B2 SHIPPED 2026-06-26** — doujin/derivative completeness. **Durability via a READ ENDPOINT**
  (`GET /works/{project_id}/derivative-context`), NOT `work.settings` (PO-approved deviation: the spec is
  ALREADY durably stored in `divergence_spec`/`entity_override` + read server-side by
  `build_derivative_context`; duplicating into settings = a 2nd SSOT). `useDerivativeContext` now reads the
  durable endpoint (survives reload). B2a banner chips+popover; **B2b fixed a latent id-space bug** (badges
  classified by knowledge node `e.id` while overrides key on `glossary_entity_id` → every row read INHERITED)
  + durable `now:` delta. 498 FE + 42 BE-works tests green.
- **B2c (adapt-with-overrides) DEFERRED → `D-DERIVATIVE-ADAPT-FROM-SOURCE`** (gate reason 2 — needs a real
  design): `generate_chapter` requires a scene plan in the DERIVATIVE project, but the inherited spine
  chapters have none (COW, no clone), so a naive generate call mostly 400s `NO_CHAPTER_PLAN`; and re-generating
  *inherited* (read-only, pre-branch) chapters is semantically muddy. A true "adapt from source" feature must
  generate FROM the source chapter's content + overrides (or gate to chapters with a derivative plan) — its
  own task, not a generate-call.
- ✅ **WS-E (a11y pair) SHIPPED 2026-06-26** — the substantive items were `D-T5.5-FOCUS-TRAP` (new
  `useModalFocusTrap` hook: focus the switcher on open, trap Tab/Shift+Tab, restore to the trigger on close)
  and `D-T5.5-ESC-PROPAGATION` (Escape now `stopPropagation`s on the dialog element, so a sibling
  window-level Esc consumer can't double-fire), both wired into `PowerViewOverlay` (the modal; `FloatingWindow`
  is non-modal → trap N/A). Also fixed an intermittent BroadcastChannel timing flake in `popoutChannel.test`
  (await delivery, not `setTimeout(0)`). +4 tests; 499 FE green ×3, tsc clean.
  - **The rest of the named WS-E LOWs stay deferred (correctly):** `D-T3.1/3.3/3.4-*`, `D-T5.1-*`,
    `D-T5.3-COUNT-SEMANTICS`/`VISIBILITY-DOM-CLASS` are all **gate-5 conscious-won't-fix-until-trigger** or
    by-design ("add X *if* Y appears", "*if* a flash is observed", feature flags) — implementing them now would
    be speculative work for triggers that don't exist. Not silently skipped; they earn their rows.
- ✅ **WS-C (PM position-remap) SHIPPED 2026-06-26** — new `TrackedPositions` PM plugin + extension
  (`trackPosition`/`trackRange` handles with `.current()`/`.release()`), the position analogue of
  `GrammarPlugin`'s `decorations.map`. Wired into **SelectionToolbar** (selection range) + **useInlineGhost**
  (ghost caret): a saved insert point/range is now remapped through any mid-stream edit instead of the crude
  `pos > doc.size` check that silently inserted at the wrong offset after an edit BEFORE the range. Site 3
  (provenance mark) stays OUT (native PM mark mapping is already position-safe). Added inert-when-empty to the
  shared `TiptapEditor` (like FocusLine/Grammar). 7-test real-editor unit suite + SelectionToolbar tests; tsc
  clean. **Also fixed a surfaced pre-existing composition-i18n parity gap** (3 `derive.anchor*` keys were
  en-only → added to ja/vi/zh-TW).
  - **⚠ Pre-existing (out of scope, NOT mine):** the full FE suite has **9 `world i18n` parity failures**
    (`world` / MMO-track namespace — e.g. `graph.loadFailed`, `populate.addFailed` missing in non-en locales).
    Untouched by this work; a separate track's i18n debt. Track there, not here.
- ✅ **WS-B3 LIVE SMOKE 2026-06-26 (real stack, test account on Dracula).** **WS-B2 derivative-context
  endpoint VERIFIED end-to-end** — `POST /derive` (au + canon_rule + an entity_override) → `GET
  /works/{deriv}/derivative-context` returned exactly the persisted spec (is_derivative, resolved
  source_project_id, branch_point, taxonomy, canon_rules, overrides). **WS-B3 M3 seed BUG CAUGHT + FIXED** —
  `createNode({kind:'scene', chapter_id:null})` violates the DB CHECK `outline_chapter_required` (a scene
  requires a chapter); the unit test had mocked `createNode` so it missed this. Fix: seed take-scenes with the
  **anchor scene's `chapter_id`** (a book chapter, shared by the COW derivative) — proven live (201 CREATED).
  Residue: one "Dracula — dị bản" derivative Work + knowledge project + 1 scene node (harmless smoke leftovers).
- ✅ **WS-B3 BUILD COMPLETE 2026-06-26 — M1 + M2 + M3.** **M3 (promote → derivative):** a Promote button
  (enabled once ≥1 take is ready) runs `useWhatIfPromotion` → `deriveWork` (branch_point = the anchor scene's
  **chapter** sort_order, taxonomy:'au', no overrides) and seeds each ready take as a scene node in the
  derivative (`createNode`, prose-persist deferred), then switches the studio (`onPromoted` wired through
  CompositionPanel's graph slot + PowerViewOverlay) and discards the branch. **Self-review caught + fixed** a
  branch_point bug (was the scene `story_order`; corrected to the anchor's chapter `sort_order`, matching the
  wizard contract). 4-locale i18n; +1 canvas promote test; composition + parity green, tsc clean. **The
  on-canvas what-if feature (spec V1) is now functionally complete** (prose-persist-on-promote + a true
  vs-canon judge delta remain as explicit deferrals in the spec).
- 🟡 **WS-B3 BUILD — M1 + M2 BUILT 2026-06-26.** **M2 (generate-take + judge badge):** `useWhatIfTakes`
  orchestrates per-alt generation via the existing auto (diverge→converge) path on the **canon** project
  (`operation:'diverge'`, non-persisting) → ghost → the existing critic dims as the judge badge (vs-canon delta
  deferred, per the locked M2 contract spec §2b). `WhatIfAltNode` gained the lifecycle (✦ Generate → generating
  → judge badge C/V/P + View); SceneGraphCanvas got a self-contained model picker + a read-only take preview
  strip (ghost + full dims). 4-locale i18n. +20 tests (hook orchestration, node states, canvas generate-flow);
  composition + parity green, tsc clean. **M3 (promote → derivative bridge) remains.**
- 🟡 **WS-B3 BUILD STARTED 2026-06-26 — M1 (on-canvas scaffold) BUILT** (§8 resolved: build). The ephemeral
  what-if branch on the Scene Graph: `useSceneWhatIf` (branch model — start/addAlt/removeAlt/discard, **zero
  residue**, nothing persisted), `WhatIfAltNode` (dashed/tinted alt beside canon), and `SceneGraphCanvas`
  integration (a "⑂ What-if from here" entry on a selected scene → dashed alt nodes + branch edges merged into
  the canvas; +alternate / discard). 4-locale i18n. +8 tests (hook + canvas render incl. zero-residue discard);
  composition suite + parity green, tsc clean. **M2 (per-node generate-take ghost + judge badge) + M3 (promote
  → derivative bridge) remain** — see the spec's V1 §3.
- ✅ **WS-B3 SPEC AUTHORED 2026-06-26** — code-grounded feature spec
  [2026-06-26-scene-graph-whatif.md](../specs/2026-06-26-scene-graph-whatif.md): the on-canvas what-if is an
  **ephemeral branch preview that PROMOTES into the existing derivative flow** (`useWhatIfPromotion` →
  `deriveWork`), NOT a second persistence path — which resolves the wizard-overlap question. Dashed branch +
  per-node judge badge (reuse WS-B1 critic/canon-gate) + generate-take ghosts + promote/discard (zero residue
  before promote). Mostly FE + orchestration; the only net-new BE is seeding outline nodes in the derivative
  project at promote (prefer reusing `createNode`, no new endpoint). **§8 carries the one open product call**
  (build it as its own L/XL cycle vs. record on-canvas as conscious won't-build with the wizard canonical).
- ✅ **WS-D (multi-window hardening) BUILT 2026-06-26** (chat-hoist stays its own task, as locked):
  - **WORKER-HEALTHCHECK** (S) — `useSharedCompositionStream` arms a 4s ack-timeout on connect (cleared by
    the hub's connect-replay); fires → degrade with a clear error instead of a silent hang.
  - **SERVER-SYNC** (M) — `loom_workspace` pref `{enabled, layout}` via `syncPrefs`: synchronous localStorage
    paint, hydrate-from-server on login (LWW + forward-merge), debounced echo-guarded write-through. +3 tests.
  - **PANEL-STREAM-HOIST** (reclassified **L** — cross-window, not the plan's S–M) — new cross-window
    `AssembleStateProvider`: the Assemble draft `{result,edited,last}` syncs over the per-(book,chapter)
    BroadcastChannel (request→reply hydration on pop-out mount + debounced broadcast + **value-compare
    echo-guard**, no loop), mounted in both roots (WorkspaceShell + PopoutHost); `ChapterAssembleView` consumes
    it via an optional hook (local fallback for bare mounts). +4 cross-window tests. **Self-review fixed** a
    per-keystroke broadcast write-storm (debounced) + a batching-fragile echo guard (→ value-compare). Also
    **hardened 3 pre-existing BroadcastChannel delivery-timing flakes** (PopoutHost/PopoutBridge: await delivery
    vs `setTimeout(0)`). 532 composition+editor green (stable ×3), tsc clean.
- **~22 open** — all workstreams (A, B1, B2, B3-spec, C, D, E) cleared or specced; remaining open items are
  the deferred-by-design (WS-F blocked/mobile) + the newly-tracked `D-DERIVATIVE-ADAPT-FROM-SOURCE` + the
  scheduled chat-hoist + the world-i18n parity (separate track).
- **⚠ Audit correction (from detailed-design research):** **`D-T5.4-CHAT-HOIST` is NOT resolved** — the
  co-writer chat SSE still runs its own `fetch`/`ReadableStream` in `useChatMessages` *below* the windowing
  layer; it survives a float but is **killed by a pop-out**. Re-opened (see WS-D detailed design).

---

# Detailed Design (per workstream)

*Authored from 3 read-only research passes over the actual code (2026-06-25). **PO decisions locked:**
B2c = ghost-generate (no auto-insert) · B3 = its own feature spec · editor-multiwindow = stays open ·
**B2 spec durability = persist to `work.settings`** (survives reload) · **B1 critic = popout-capable**
(re-fetch verdict) · **chat-hoist = its own scheduled task**.*

## WS-B1 — Continuity Critic standing panel · **M** — ✅ **SHIPPED 2026-06-25**
**Built as designed.** New `CriticStateContext` (mounted by WorkspaceShell, inside the book-keyed
`LiveStateProvider`) holds `{critic, canon, jobId}`; ComposeView `accept()`/`acceptText()` +
ChapterAssembleView `onResult` write it via explicit `onSuccess` handlers (no useEffect). Inline
`CriticFlags` extracted to `components/CriticFlags.tsx` (handlers optional). New `components/CriticPanel.tsx`
reads the shared verdict (dock/float) OR re-fetches `getJob(jobId).critic` (popout — jobId from the
SharedWorker-backed `useLiveStreamOptional()`, no URL plumbing) + a "re-check current draft" action.
`CanonGatePanel.onRevise` made optional (view-only in the panel). Registered `critic` in
`workspace/types.ts` (union+PANEL_IDS+DOCK_ORDER) + `CompositionPanel` (SubTab+strip+DockSlot) + i18n ×4.
**VERIFY:** tsc clean; **495 composition tests green ×3** (new `CriticPanel.test` 4 cases; ComposeView
accept-onSuccess updated). **Fixed a surfaced pre-existing flake:** PopoutHost/PopoutBridge BroadcastChannel
tests used generic `'b1'/'c1'` channel names → cross-talk across vitest workers; gave them file-unique ids
(the `popoutChannel.test` `PCHAN_` precedent). Decision deviation (verified vs plan): the shared verdict's
`critic` is **nullable** so the chapter-assemble path (which yields a canon-gate result but no per-dimension
critique) can contribute its canon verdict.

<details><summary>original design</summary>

**Crux:** the verdict lives **only in ComposeView's local `useCritique` state** (`ComposeView.tsx:49,111`)
— a sibling dock panel can't read it. The work is **lifting the verdict**, not the panel.
- **Shared store:** add a `CriticStateContext` (or extend `LiveStateContext`) mounted by `WorkspaceShell`
  (above the windowing layer, like `LiveStateProvider`), holding `{ critic: Critic, canon: CanonResult|null,
  jobId }` + `setVerdict`. Plain react-query data (not streamed) → a React context suffices for dock/float;
  **no SharedWorker needed**.
- **Writers:** ComposeView `accept()`/`acceptText()` and ChapterAssembleView `onResult` call `setVerdict`
  in addition to their local use.
- **Extract** the inline `CriticFlags` (ComposeView.tsx:220-293) into `components/CriticFlags.tsx` (exported);
  ComposeView keeps rendering it inline (immediate feedback); the new `CriticPanel` renders the same
  `CriticFlags` + a `CanonGatePanel` from the shared store.
- **Register `critic`:** `workspace/types.ts` (WorkspacePanelId union + PANEL_IDS + DOCK_ORDER),
  `CompositionPanel.tsx` (SubTab + fixed-strip array + a `<DockSlot {...slot('critic')}>`), i18n ×4 (reuse
  existing critic/coherence/voice_match/pacing/canon_consistency/dismiss keys). `dock.ts` is generic → no change.
- **Verdict shape** (`types.ts:272-288` `Critic`): coherence/voice_match/pacing/canon_consistency + violations +
  the C26 override-gate (needs_regeneration/regen_*/derivative_findings). Canon verdict is a *separate*
  `CanonResult` (only on the Diverge/chapter paths today — surface it for the latest generation).
- **DECISION (locked): popout-capable.** The CriticPanel re-fetches the latest verdict via
  `GET /jobs/{id}/critique` on mount (the `jobId` passed via the popout URL/channel), so it works docked,
  floated, AND popped-out — not just the in-memory-context dock/float case.
- **Tests:** verdict-survives-tab-switch (shared store); CriticPanel renders the shared verdict; ComposeView's
  override-gate still blocks accept (regression). **Size: M.**

</details>

## WS-B2 — Doujin / derivative completeness · **M**
**Crux:** the derivative spec/overrides are **write-only** (`POST /derive`, never read back; only a session
react-query cache stashes override *ids* — `useDerivativeContext.ts:6-11,24-27`). **DECISION (locked):
durable** — persist the full divergence spec (override values, POV anchor, taxonomy, canon rules) into
**`work.settings`** at derive/promote time, and **read it back on Work resolution** so `useDerivativeContext`
exposes the spec from the resolved Work (not just the session cache). The banner chips, spec popover, and
was→now deltas then survive a page reload / new session. Touches: the derive/promote write (stash into
settings), the resolution read (surface `settings.divergence_spec` through `DerivativeContext`), and
`useDerivativeContext` (expose `overrides`/`povAnchor`/`taxonomy`/`canonRules` from settings instead of the
ephemeral cache). *(This supersedes the session-cache-only approach — small composition-service settings
round-trip, no new endpoint.)*
- **B2a banner** (`DerivativeBanner.tsx`): override-summary chip + POV chip (`povAnchor`) + a "⚙ Divergence
  spec" popover (Source = resolve `sourceWorkId`→title from CompositionPanel's `allResolved`; Branch =
  `branchPoint`; POV; Overrides; Inherits). "+Add transform" opens `DivergenceWizard` **Step3Overrides**
  (reuse the exported step).
- **B2b was→now deltas** (`DerivativeGroundingLayers.tsx`): old = source canon entity field (already fetched
  via `knowledgeApi.listEntities`); new = stashed `overrides[entityId][field]` (usually `description`). Render
  `was {old} → now {new}` on OVERRIDDEN rows. **Verify the id-space** — overrides are keyed by
  `glossary_entity_id` but `classify()` uses node `e.id` (possible existing mismatch — confirm in build).
- **B2c adapt-with-overrides (ghost-generate, decided):** a button per reference-spine chapter
  (`DerivativeGroundingLayers.tsx:77-91`) → `useGenerateChapter(persist:false)` on the **derivative
  `projectId`** (overrides apply **server-side** via the derivative's delta partition — FE passes no overrides
  per-call) → land in `ChapterAssembleView`'s existing ghost preview (result/edited/onAccept). No auto-insert.
- **Tests:** banner chips+popover from the stash; was→now from a stashed override; adapt-button calls
  generateChapter(persist:false) on the derivative project → ghost. **Size: M** (+S–M if durable).

## WS-C — ProseMirror position-remap util · **M** *(down from M–L: 2 sites, not 3)*
- **Build** a small `trackedPositions` PM plugin/hook (`PluginKey`) whose `apply(tr, prev)` runs
  `prev.positions.map(p => tr.mapping.map(p, bias))` on `tr.docChanged` — the position analogue of
  `GrammarPlugin.ts:49`'s `decorations.map(tr.mapping, tr.doc)`. Expose `trackPosition(view,pos,bias)` /
  `trackRange(view,from,to)` → a handle with `.current()` (live mapped pos/range, or `null` via
  `mapResult().deleted`) + `.release()`.
- **Site 1 (selection range, `SelectionToolbar.tsx:57-89`):** capture via `trackRange` at run(); apply
  delete+insert at `handle.current()`; replace the crude `>content.size` toast with the precise `deleted` signal.
- **Site 2 (ghost point, `useInlineGhost.ts`):** EITHER `trackPosition` for the commit insert, OR (cleaner)
  migrate the fixed overlay to a `Decoration.widget(pos)` — PM remaps it for free + gives `coordsAtPos`,
  eliminating the manual `reposition()`.
- **Site 3 (provenance mark) — OUT:** native PM mark mapping is already position-safe. **`D-T5.3-SPLIT-ON-EDIT`
  re-scopes** to a separate mark-attribute/boundary-semantics task (not position remap).
- **Tests:** edit-before-range remaps; delete-the-range → `deleted` (no corruption); ghost widget follows a
  concurrent edit. **Size: M.**

## WS-D — Multi-window hardening
**Float keeps state (re-parent); only POP-OUT destroys it (unmount + fresh root)** — so all of these only
matter for *popped* panels.
- **Chat hoist (`D-T5.4-CHAT-HOIST`, RE-OPENED, headline, structural):** the cowriter chat SSE runs its own
  `fetch`+`ReadableStream` in `useChatMessages` (`useChatMessages.ts:198-400`) below `DockSlot` → a pop-out
  unmounts it and the new root starts an empty chat (an in-flight assistant turn is lost; history rehydrates via
  refetch). Needs its **own hub** — a `chatStateHub` SharedWorker + `ChatLiveStateProvider` modeled on Slice B:
  extract a React-free `runChatTurn(args,token,cb,signal)` core (like `runCompositionGeneration`) + a worker
  shell; session-keyed; AG-UI event protocol. **Schedule as its own L/structural task.**
- **Assemble (`D-T5.4-PANEL-STREAM-HOIST`, lighter):** at-risk state is `{result, edited, last}` + a
  *non-streaming* mutation (`ChapterAssembleView.tsx:38-48`). Pop-out mid-assemble loses an un-accepted
  draft+edits. Cheapest: hoist `{result, edited, last}` into a context mounted in both roots, or fold
  chapter-generate into the existing hub as a job-type (it already 202-polls). **Size: S–M.**
- **Server-sync (`D-T5.4-SERVER-SYNC`):** reuse `@/lib/syncPrefs` (`loadPrefFromServer`/`syncPrefsToServer`
  over `/v1/me/preferences`); canonical consumer to copy = `useGlossaryDisplayLanguage.ts`. Add a
  `loom_workspace` pref `{enabled, layout}`. In `WorkspaceLayoutContext.tsx`: keep the synchronous localStorage
  load (instant paint), add a `[accessToken]` effect → `loadPrefFromServer` → forward-merge (reuse `loadLayout`'s
  merge as a shared `mergeLayout(parsed)`) → hydrate + write back to localStorage; write-through (debounced,
  fire-and-forget) in the existing `[layout]` persist effect + `setEnabled`. **LWW** conflict; opt-in/additive
  (localStorage stays the per-device cache). Add token via prop or `useAuth`. **Size: M.**
- **Worker-healthcheck (`D-T5.4-POPOUT-WORKER-HEALTHCHECK`):** ack-timeout degrade (the `onerror` surface
  already ships). **Size: S.**
