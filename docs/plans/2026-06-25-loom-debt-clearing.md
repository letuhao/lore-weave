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

### WS-A — Live-smoke sweep · **P0** (cheapest, highest confidence-gain)
The dev stack + browser harness work now (proven 2026-06-25). These rows are *blocked-on-harness*,
not code — clear them by running the smoke against the running stack and recording evidence.
- `D-T3.6-LIVE-SMOKE` — references embed → per-scene semantic search round-trip.
- `D-T4.1-LIVE-SMOKE-FULL-CHAIN` — publish → extract → merge → stamp → flywheel-delta.
- `D-T5.4-POPOUT-SHARED-SSE-BROWSER-SMOKE` — cross-**window** SharedWorker fan-out + survive-opener-close
  + late-join replay. (Playwright tab-reload severs the `window.open` handle, so use a 2-window manual
  harness or `browser_tabs` without reloading the popout.)
- `D-T5.4-POPOUT-WORKER-HEALTHCHECK` — observe worker behaviour live (partial; full degrade is WS-D).

**Design:** a per-item smoke checklist against the stack; expect some to surface bugs (today's did →
fix-now). **Size:** 4 × S (execution). **Already cleared today:** dock/float/popout open+render, no-token-in-URL.

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
- **~32 open**, mapped above. The windowing browser-smoke gap is the cheapest cluster and is *partially
  cleared* already (2026-06-25 live smoke).
- **⚠ Audit correction (from detailed-design research):** **`D-T5.4-CHAT-HOIST` is NOT resolved** — the
  co-writer chat SSE still runs its own `fetch`/`ReadableStream` in `useChatMessages` *below* the windowing
  layer; it survives a float but is **killed by a pop-out**. Re-opened (see WS-D detailed design).

---

# Detailed Design (per workstream)

*Authored from 3 read-only research passes over the actual code (2026-06-25). **PO decisions locked:**
B2c = ghost-generate (no auto-insert) · B3 = its own feature spec · editor-multiwindow = stays open ·
**B2 spec durability = persist to `work.settings`** (survives reload) · **B1 critic = popout-capable**
(re-fetch verdict) · **chat-hoist = its own scheduled task**.*

## WS-B1 — Continuity Critic standing panel · **M**
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
