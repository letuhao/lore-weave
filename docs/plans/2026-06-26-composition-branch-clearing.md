# Plan — Clear the Writing-Assistant Composition Debt

- **Status:** CLARIFY ✅ → DESIGN ✅ → **DEFERRED to a new branch (no build on
  `feat/composition-service`).**
- **⚠ BUILD TARGET (PO decision 2026-06-26): a NEW branch, NOT `feat/composition-service`.**
  `feat/composition-service` is cleared/merged **as-is** (its already-committed work);
  **none** of the milestones below build on it. All 9 are deferred to a fresh branch
  (proposed `feat/composition-debt`), branched off `main` after `feat/composition-service`
  merges. The KG extraction-cache (separate, knowledge-service) goes on its own new branch —
  see [`docs/specs/2026-06-26-kg-extraction-cache.md`](../specs/2026-06-26-kg-extraction-cache.md).
- **Date:** 2026-06-26 · **Design branch:** `feat/composition-service` (docs only) ·
  **Build branch:** new (TBD)
- **Goal:** close out the last open composition debt — built on a new branch, not here.
- **PO decisions (LOCKED 2026-06-26):** all five greenlit at the fullest build —
  adapt = **per-scene ghost from source**; chat-hoist = **full SharedWorker hub**;
  WS-B3 = **build both deferrals** (prose-persist + vs-canon delta); WS-F = **build a
  mobile pass now**. `D-T5.2-WINDOWED-MENTIONS` stays **externally blocked** (knowledge
  track `D-P2-PER-SCENE-FANOUT`) — out of scope, recorded as blocked.
- **Grounding:** 3 read-only research passes over the actual code (2026-06-26), refs inline.

This is **one coherent effort, classified XL**, run as **9 milestones** (M0 world-i18n,
M4 delta, M6 canon-at-chapter inspector, M3 prose, M1 adapt, M5a mobile-shell,
M5b mobile-canvases, M7 per-chapter mention frequency, M2 chat) each with its own
BUILD→VERIFY→REVIEW→commit at a risk boundary. **All 9 PO-greenlit 2026-06-26, but
deferred to the new build branch — none build on `feat/composition-service`.**
Order (lightest-risk first, structural/largest last):
**M0 → M4 → M6 → M3 → M1 → M5a → M5b → M7 → M2** (M6 before M1 so the what-if can mount
the canon-at-branch-point inspector).

---

## M1 — `D-DERIVATIVE-ADAPT-FROM-SOURCE` (per-scene ghost from source) · **M–L** · FS

**Problem (verified).** A derivative Work is COW (spec-only, no chapter/scene clone —
`works.py:289-298`); the inherited spine chapters have **no scene plan**, so
`generate_chapter` 400s `NO_CHAPTER_PLAN` (`engine.py:842-844`, precondition = ≥1
`kind='scene'` node). Worse, the derivative pack reads source **knowledge** grounding
(`pack.py:337-342`) but **never source prose** — `gather_recent` (`lenses.py:233-267`)
only ever uses the derivative's own `book_id`/`project_id` (`pack.py:310-312`). So there
is no way today to "adapt this source scene through the divergence."

**Design — a per-scene "Adapt from source" ghost.**
1. **New op `adapt_scene`** in `_OPERATION_INSTRUCTIONS` (`cowrite.py:28-39`): *"Adapt the
   SOURCE scene's prose to this branch: keep its structural function, but rewrite it to
   honour the divergence and entity overrides."* It is plan-free (like `continue`/`rewrite`)
   — it does **not** require a derivative scene node.
2. **New source-prose lens.** Add `gather_source_scene(book_id, source_chapter_id, branch_point)`
   in `lenses.py`, mirroring `gather_recent` but reading `book.get_draft(book_id,
   source_chapter_id, bearer)` on the **shared** `book_id` (COW shares the book —
   `works.py:315,348`). Branch-bound: only adapt scenes at/after `branch_point`.
   Wired into `pack()`'s derivative branch (the `is_derivative` region near
   `pack.py:337-342`), gated to the `adapt_scene` op so the normal pack is untouched.
3. **Overrides already flow** — `build_derivative_context` returns the persisted
   `entity_override[]` (`pack.py:128-165`); the adapt prompt applies them exactly as the
   existing derivative pack does (delta-wins + override).
4. **Output is a ghost** (`persist:false`) — honours the **LOCKED no-auto-insert rule**.
   The writer reviews the adapted ghost and accepts/promotes it manually.
5. **FE.** A "✦ Adapt from source" action on a derivative scene (next to the existing
   co-writer affordances) → `compositionApi.generate(projectId, { operation:'adapt_scene',
   scene_node_id })` → ghost in the existing live-stream surface. New `derive.adapt.*`
   i18n ×4.

**No new endpoint** — reuses `POST /works/{project_id}/generate` (`engine.py:281`) with
the new op. **BE touch:** `cowrite.py` (op), `lenses.py` (lens), `pack.py` (wire),
+tests. **FE touch:** the action + api param + i18n.

**Acceptance.** On a derivative, "Adapt from source" on an inherited scene returns a ghost
generated from the source scene's prose + the branch's overrides (no `NO_CHAPTER_PLAN`);
nothing auto-inserts; a greenfield (non-derivative) Work never offers the action.

**Cross-service:** composition ↔ book-service (`get_draft`) → **live-smoke required**.

---

## M2 — `D-T5.4-CHAT-HOIST` (cowriter chat survives pop-out) · **L / structural** · FE

**Problem (verified).** The cowriter chat SSE is an **inlined** `fetch`+`ReadableStream`
loop inside `useChatMessages.streamPost` (`useChatMessages.ts:198-463`) — **no worker, no
React-free core** (zero `SharedWorker`/`runChatTurn` hits in `features/chat`). A pop-out
unmounts the hook and the **in-flight assistant turn is lost** (history rehydrates via the
remount refetch `:87-101,103-105`, and the post-abort refetch `:444/:451` picks up any
partial the server persisted — so **only the live, not-yet-persisted tokens** are lost).
The fix is the composition Slice-B pattern applied to chat.

**Design — mirror `liveStateHub` for chat (the proven 3-layer template).**
1. **Extract `runChatTurn(args, token, cb, signal)`** — a pure, React-free core lifted
   from `streamPost`: the AG-UI event switch + accumulators (`accumulatedContent`,
   `accumulatedReasoning`, `accumulatedToolCalls`, `accumulatedActivities`,
   `openToolCalls`/`openToolArgs`, `streamUsage`, `streamTiming`, `streamMessageId`,
   suspended-run/`pendingToolCall`) emitting through a `ChatCallbacks` sink. **This is the
   dominant cost** — chat's stream has ~2–3× composition's event surface (reasoning + 3×
   tool-call frames + 4× CUSTOM sub-events + RUN_FINISHED suspend + RUN_ERROR).
2. **`chatStateHub`** (`createChatStateHub(run)`) — port-set + one `AbortController` + a
   single **rich snapshot** (`{ streamingText, streamingReasoning, streamPhase,
   thinkingElapsed, toolCalls, activities, suspendedRun, messageId, error }`), broadcast
   full on every patch, replayed to a newly-connected port. Inbound `start|stop|clear`.
   Unit-testable without a real SharedWorker. Modeled on `liveStateHub.ts:39-82`.
3. **Worker shell** `chatLiveState.shared-worker.ts` (~24 lines) — `const hub =
   createChatStateHub(runChatTurn); onconnect = e => hub.addPort(e.ports[0])`.
4. **`useSharedChatStream(token, enabled)`** consumer hook — mirrors snapshots into local
   state, exposes `{ ...snapshot, start, stop, clear }`, with the **4s ACK-timeout health
   check** (the documented `useSharedCompositionStream.ts:20,41-44` gotcha).
5. **`ChatLiveStateProvider`** selects worker-vs-inline (windowing enabled AND
   `SharedWorker` present), mounted **above** the windowing layer (like
   `LiveStateContext`/`CriticStateContext`). `useChatMessages` consumes the snapshot
   instead of owning the stream.

**Re-plumb (the chat-specific extras, not present in composition):**
- **Resume / tool-result path** (`submitToolResult`/`submitToolResolve` `:469-495`) routes
  through the hub `start` (override args), not a second inline loop.
- **`onStreamEnd` ref fan-out** (`ChatStreamContext.tsx:73-75`: session refresh +
  pending-facts refetch) can't cross the worker — re-plumb as a snapshot-terminal effect
  in the provider (watch `streamPhase → done`).
- **Optimistic user-message append** (`send`/`edit`/`regenerate` `:500-562`) stays
  main-thread (it's not stream state).

**Acceptance.** Generate a chat turn, pop the chat panel out mid-stream → the popped
window keeps streaming to completion (worker fan-out); close the opener → the popout
survives; open a popout mid-turn → late-join replay shows the in-flight turn. **Browser
two-window live-smoke required** (the WS-D precedent).

**Hazard.** This is FE-structural and load-bearing → **`/review-impl` mandatory**, and the
core extraction must preserve every AG-UI event path (a dropped event type = a silent
regression). Build **last** (highest risk).

---

## M3 — WS-B3 `prose-persist-on-promote` · **M** · FS

**Problem (verified).** Promote currently seeds **empty** scene nodes (`createNode`,
prose deferred). Scene outline nodes carry **no prose** (`NodeCreate` is structural-only,
`outline.py:29-57`); scene prose lives in **book-service chapter drafts**. But the
derivative shares the source `book_id`, so writing the take prose into
`book.get_draft(book_id, chapter_id)` would **clobber the shared source chapter draft** —
a COW/tenancy violation. The take ghost was generated against the **canon** project (M2
contract) and exists only client-side at promote time.

**Design — persist take prose scene-scoped in the DERIVATIVE project (never the shared book draft).**
- The right store is the **derivative project's own scene-draft layer** — the same
  `prior_scene_drafts` mechanism `gather_recent` already falls back to (`lenses.py:262`),
  keyed by the derivative's fresh `project_id` (scope-clean, no source clobber).
- **New scene-scoped persist endpoint** `POST /works/{project_id}/scenes/{node_id}/prose`
  (composition-service) that writes the supplied prose as a scene draft in the derivative
  project for that node — the **one net-new BE capability** the WS-B3 spec flagged (§6).
  (The existing `jobs/{id}/persist` is chapter-only and 422s per-scene results —
  `engine.py:1348-1354` — so it can't be reused as-is.)
- **Promote flow change** (`SceneGraphCanvas` `onPromoted`): after `createNode` for each
  ready take, call the new scene-prose persist with the chosen take's ghost. Best-effort
  per scene (one failure doesn't abort the promote); surface a count toast.

**Acceptance.** Promote a what-if branch → each derivative scene node carries its take's
prose (readable in the derivative studio); the **source** chapter draft is byte-unchanged
(no clobber); discard still leaves zero residue.

**Cross-service:** composition-only write to its own DB → unit + a derivative live-smoke
(verify source draft untouched). Builds naturally **before** M-ADAPT (shares the
derivative-prose surface).

---

## M4 — WS-B3 `vs-canon judge delta` · **S–M** · FE

**Problem (verified).** The what-if judge badge shows the **take's own** critic dims, not
a delta vs canon. `useCritique` takes an arbitrary `{ jobId, passage }` and returns dims
as **integers 0–5** (`types.ts:288-304`, `critic.py:116-122`) — subtractable.

**Design — delta = critique(take) − critique(canon baseline).**
- Critique the take ghost (already done in M2). Additionally critique the **canon
  baseline** = the anchor scene's chapter draft prose (fetched from book-service via the
  anchor's `chapter_id` — canon prose is **not** in client state, `OutlineNode` has no
  prose field; the studio navigates to the book chapter to see prose).
- Compute per-dim delta (null-guarded: dims are `number | null` on degrade). Badge shows
  ▲/▼/= per dim (coherence/voice/pacing/canon-consistency) vs canon, with the absolute
  take score on hover.
- **Hazard handled:** the critique endpoint **COALESCE-overwrites** the job's `critic`
  column (`engine.py:1470-1476`), so the canon-side call must **read the verdict from the
  mutation response client-side** — never round-trip the same job twice expecting both to
  persist. Use the active job id for both; capture both `data.critic` before either write
  matters.
- **Cost control** (spec §9): judge canon **once per anchor** (memoize client-side by
  `chapter_id`); only the chosen take auto-judges (debounce).
- **Approximation noted:** scene prose isn't isolated from chapter prose in storage, so
  the canon baseline is the anchor scene's **chapter** draft, not a scene-isolated slice.
  Documented as a V1 limitation.

**Acceptance.** A generated take's badge shows a per-dim ▲/▼/= **relative to the canon
anchor**; canon is judged at most once per anchor; the badge null-degrades cleanly if no
distinct critic model is configured (the endpoint skips LLM critique — `engine.py:1447-1454`).

**Cross-service:** composition ↔ book-service (canon prose fetch) — covered by the M-ADAPT
live-smoke stack-up. Lightest item → build **first**.

---

## M5 — WS-F mobile pass (`D-T5.4-MOBILE` + `D-T5.5-MOBILE-SWITCHER`) · **L–XL** · FE

**PO refinement (LOCKED 2026-06-26):** mobile = **one full component at a time + navigate
to switch** (feature-rich studio can't tile on a phone). Two decisions locked:
- **Navigation model = two-level grouped.** A bottom bar with top groups
  (**Editor / Studio / History**); "Studio" opens a switcher (Sheet/Drawer) to pick one of
  the 21 panels. Not a flat 23-item list.
- **Heavy canvases = mobile-tuned per panel** (not best-effort). Scene Graph, Relationship
  Map, World Map, Timeline each get a mobile interaction pass.

Because of the second decision M5 is its **own L/XL effort**, split into **M5a (shell +
nav framework)** and **M5b (heavy-canvas mobile views)**.

**Problem (verified).** The LOOM workspace is **purely desktop** — zero mobile awareness
in the workspace tree (only two incidental `innerWidth`/`touchAction` lines in
`FloatingWindow`). `DockRail` hover-only buttons (`:38,45,52`) and drag-on-the-select-
button (`:33`) are touch-hostile; `FloatingWindow` (`MIN_W=280` ≈ full phone width) and
OS pop-out are unusable on mobile. The studio also mounts **inside** `ChapterEditorPage`'s
desktop `panels.right` side panel (`:1163-1185`), so the **outer** editor shell needs the
single-view treatment too, not just the inner workspace.

### M5a — mobile shell + two-level navigation framework · **L**
- **Reuse `useIsMobile()`** (`features/knowledge/hooks/useIsMobile.ts`,
  `matchMedia('(max-width: 767px)')`, SSR-safe, tested) — hoist to `@/hooks/useIsMobile`
  so composition + knowledge share one source.
- **Outer shell (`ChapterEditorPage`)** — branch on `useIsMobile` (the `KnowledgePage`
  precedent: `if (isMobile) return <Mobile…/>`). Render a **bottom group bar**
  (Editor / Studio / History), each group full-screen, one at a time. The desktop 3-pane
  shell is untouched.
- **Inner workspace (`CompositionPanel`)** — when mobile + group=Studio: **ignore
  `placement`**, force every panel docked, render only `active`'s `DockSlot` visible (the
  21 slots already CSS show/hide — `DockSlot.tsx:13-51`); never render `DockRail`/
  `FloatingWindow`/`PopoutBridge`/`ComponentPicker`. **No layout-schema change** —
  `WorkspaceLayout.active` already models "the one shown panel" (`workspace/types.ts:25-40`)
  and persists across reload.
- **New `MobilePanelSwitcher`** (net-new — no bottom-nav exists) — a shadcn **Sheet/Drawer**
  (precedent: `TrashDrawer`) opened from the Studio group, enumerating
  `visibleDockIds(layout, threadsEnabled)` (the **`threads` gate** at `dock.ts:7-9` must
  apply), labels via `t(id)`, select → existing `selectTab` (`CompositionPanel.tsx:326`)
  → `set-active`. Clamp `active` to a visible panel (desktop already does this `:321-324`).
- **Branch regardless of the `loom.workspace.enabled` flag** — mobile gets the switcher in
  both the flag-ON (DockRail) and flag-OFF (`TabScrollStrip`) paths.
- New `mobile.*` i18n ×4.

### M5b — heavy-canvas mobile views · **M–L**
The four pan/zoom SVG panels need a mobile interaction (the generic `GraphCanvas`/SVG host
assumes a mouse + wide viewport):
- **Scene Graph**, **Relationship Map**, **World Map**, **Timeline** — add a mobile mode:
  fit-to-screen on mount, pinch-zoom / touch-pan, and a simplified control affordance
  (hide hover-only chrome; surface node actions via tap → a bottom Sheet instead of hover).
- Reuse one shared mobile-canvas wrapper where the SVG host is common; per-panel only where
  the interaction genuinely differs (e.g. Timeline is horizontal-scroll, World Map is
  zoomable tilemap).
- Gated on `useIsMobile` so desktop canvases are byte-unchanged.

**Acceptance.** On a ≤767px viewport: the editor page shows one group at a time via the
bottom bar; the Studio group shows one panel at a time via the switcher (no float/popout/
drag/hover-only affordances); the four heavy canvases are usable with touch (fit + pinch +
tap-to-act); `active` + group persist across reload; **desktop is byte-unchanged**.

**Cross-service:** FE-only → browser live-smoke at a mobile viewport (no LLM needed); smoke
each heavy canvas's touch interaction.

---

## M0 — `world` i18n parity (writing-assistant world-building) · **XS** · FE
**Correction (2026-06-26):** the `world` namespace is **part of the writing assistant** — a
world-building *collection of knowledge* (onboarding / campaigns / lore / timeline), **NOT**
the MMO track. So its parity gap is **branch-clearing debt**, not a separate track. Earlier
notes mislabeled it MMO; corrected here.

`compositionWorldParity.test.ts` fails 9 = 3 checks (key-set / placeholder / non-empty) ×
3 locales (vi/ja/zh-TW). The gap is a handful of `en/world.json` keys missing or empty in
the other locales (observed: `graph.loadFailed`, `populate.addFailed`, `timeline.loadFailed`,
and the placeholder/empty checks on a few more). **Fix:** add the missing translations to
vi/ja/zh-TW so all four locales have an identical key set + preserved `{{placeholders}}` +
no empty values. Pure i18n; no code. Build **first** (trivial, unblocks a green parity suite).

## M6 — "Canon at chapter N" inspector (per-chapter presence) · **M** · FS · **buildable now**
**Origin (2026-06-26):** the PO flagged that knowing *exactly what a chapter establishes*
is core to writing — and **especially** to authoring a **what-if canon** (a derivative
must be grounded in *canon-as-of-the-branch-point*, not whole-book). Two read-only research
passes confirmed the data **already exists** and is already windowable; only the mention
*frequency* curve is missing (that's M7). So this is buildable on this branch with **no
upstream dependency**.

**What it surfaces.** A writer panel answering two questions from existing windowed data:
1. **"What does chapter N establish/mention?"** — entities present in a chapter +
   their 3-level relevance (`major`/`appears`/`mentioned`), from glossary
   `chapter_entity_links` (`chapter_id` exact filter).
2. **"What does canon know *as of* chapter N?"** — the windowed union of: glossary
   `known-entities?before_chapter_index=N` (entities established by N, with
   first/last-appearance + coverage from `/entities/stats`), knowledge windowed
   statuses/facts/timeline/lore/canon-rules (`before_chapter_id=N`), and the composition
   `GET /works/{project_id}/scenes/{node_id}/grounding` full windowed pack.

**Wiring (LOCKED — both):** mount the inspector **at the what-if branch point** (the
headline use — the divergence author sees *exactly what canon knows right before the
branch*; everything after is the divergence) **AND** as a general **per-scene** studio
panel for ordinary writing ("canon as of this scene"). Shared component, two mount points.

**BE touch (small).** The glossary windowed views are `/internal/*` (service-to-service) —
FE can't call them directly. Add a **gateway/composition public passthrough** for
`known-entities` + per-chapter links (read-only, VIEW-grant scoped). Everything else
(knowledge windowed endpoints, the grounding endpoint) is already public-reachable. New
`canonview.*` i18n ×4.

**Acceptance.** On a scene/branch-point, the panel lists entities established by that
chapter + canon facts/statuses/timeline as-of that chapter, all correctly windowed (a
post-chapter entity does NOT appear); on a derivative it windows to `branch_point`.

**Cross-service:** composition/gateway ↔ glossary + knowledge → **live-smoke required**.

## M7 — true per-chapter mention *frequency* (windowed heatmap) · **M–L** · FS · cross-service
**Re-scoped (2026-06-26):** `D-T5.2-WINDOWED-MENTIONS` was recorded as blocked on
`D-P2-PER-SCENE-FANOUT`, **but that's per-*scene* (perf) fanout** — the heatmap's
chapter-cutoff windowing only needs per-*chapter* counts, and extraction **already runs
per-chapter** (`pass2_writer.py` one CypherSession per chapter; glossary `extract-entities`
is chapter-scoped). So this is **independently buildable**, not blocked. The deferral
over-scoped its own dependency.

**The change (3 seams):**
1. **glossary schema** — add `mention_count INT` to `chapter_entity_links` (keep
   `UNIQUE(entity_id, chapter_id)`; it's a count *within* that chapter).
2. **producer** — knowledge extraction counts mentions per entity per chapter and emits it
   in the `chapterLinkIn` payload of `/internal/books/{book_id}/extract-entities`; glossary
   persists it (`ON CONFLICT … DO UPDATE`).
3. **FE** — `useMentionHeatmap` windows on per-chapter counts ≤ cutoff instead of the
   whole-book scalar; clear the deferral note.

**PO decision (LOCKED 2026-06-26): build M7 now** (fully clear `D-T5.2-WINDOWED-MENTIONS`).
It is a **schema migration + cross-service contract change** → M–L/structural; it gets its
**own CLARIFY** for one open question — *does extraction count surface forms / CJK aliases
per chapter, or canonical mentions only?* (start canonical-only; CJK alias-per-chapter is
the separate deferred task below). Because it's load-bearing + cross-service, **`/review-impl`
mandatory** + a live-smoke proving the count flows extraction → glossary → FE.

## Still blocked / out of scope (recorded, not built)
- **Per-*scene* mention fanout (`D-P2-PER-SCENE-FANOUT`)** — only needed for *scene*-level
  (not chapter-level) granularity + extraction parallelism; perf-gated
  ("when 1MB+ novel perf becomes an issue", `docs/MILESTONE.md:109`), lives in
  knowledge-service. **Gate 4.** M7 deliberately works at *chapter* granularity to avoid
  this. *(Not MMO — earlier framing corrected.)*
- **Per-chapter alias/surface-form breakdown** (which alias appeared in chapter N, for
  CJK) — no table for it; `chapter_entity_links` links the canonical entity only. Its own
  task if needed.

## Net-new BE surface (the only schema/contract touches)
1. `adapt_scene` op + `gather_source_scene` lens (M1) — additive, no schema change.
2. `POST /works/{project_id}/scenes/{node_id}/prose` scene-draft persist (M3) — new
   endpoint, writes to the derivative project's scene-draft store.

Everything else is FE + orchestration over already-built infra (derive, critic, ghost,
the SharedWorker template, the `useIsMobile` precedent).
