# Plan — Clear the Writing-Assistant Composition Debt

## ✅ COMPLETE — all 9 milestones shipped on `feat/composition-debt` (2026-06-26)

Built in the locked order `M0 → M4 → M6 → M3 → M1 → M5a → M5b → M7 → M2`, each through the
12-phase v2.2 `/loom` workflow with grouped PO checkpoints. Commits:

| M | What | Commit |
|---|---|---|
| M0 | world i18n parity | (earlier) |
| M4 | vs-canon judge delta | (earlier) |
| M6 | canon-at-chapter inspector (+`/review-impl`: knowledge-project HIGH) | `c27b57e7` |
| M3 | prose-persist-on-promote (+`/review-impl` HIGH: seed `story_order`) | `12cc1044`, `8f52ef2b` |
| M1 | adapt-from-source (+`/review-impl` HIGH: branch_point=null) | `d633fff9`, `93890d4d` |
| M5a | mobile shell + two-level nav | `117b5367` |
| M5b | heavy-canvas mobile (pinch + fit-on-mount) | `f05d89c3` |
| M7 | per-chapter mention heatmap windowing (cross-service) | `992290e5` |
| M2 | chat-hoist finalize (worker engagement + single-writer) | _this commit_ |

**Live-smokes:** M1/M3/M6/M7 cross-service PASS; **M7 bulk `mention_backfill` run across all 7
books with chapter links** (Dracula ×4 scenario + 万古神帝 ×2 — the large CJK book: 5495 alive
entities paged, 436 links counted). **M2 browser two-window PASS** — a real lm_studio turn ran
in the popped-out cowriter, and an initiator-window token mirrored into a second window mid-stream
then cleared on the observer refetch (single-writer split, live).

**Recently cleared:**
- **`D-M3-PROSEJOB-PUBLISHGATE`** (MED) — **FIXED** (commit follows). The publish-gate's
  latest-canon-verdict pick (`db/repositories/outline.py` `chapter_scene_gate`) took the most
  recent completed job per scene *regardless of operation*, so an M3 synthetic
  `promoted_scene_prose` job (no canon verdict) could shadow an earlier auto-gen's confirmed
  `canon.resolved=false` and silently un-block publish. Fix: exclude
  `operation='promoted_scene_prose'` from the subquery — keeps the gate conservative-for-canon
  (only a real re-generation can clear a block). Real-PG integration test proves it before/after
  (masking test FAILS on the old image, PASSES with the fix; 9/9 prose+gate tests green). It was
  a one-line root-cause fix surfaced *by* M3 (M3 creates the synthetic job) → fixed now, not
  deferred to a separate track.

- **`D-T5.4-CHAT-MULTIWINDOW-ORPHAN`** — **FIXED** (commit follows). Re-graded from LOW: an
  orphaned turn leaving a session untracked/unresumable is a real failure, not cosmetic. Root
  cause was a mis-scoped gate: `onStreamEnd` was fired only in the initiator window, but it does
  nothing but two **idempotent reads** — `refreshSessions()` (debounced) + `pendingFacts.refetch()`
  — which are EACH window's own derived state. Single-writer gating both orphaned the refresh when
  the initiator closed AND left every observer's sidebar/pending-facts stale. Fix: fire
  `onStreamEnd` **per-window** (each refreshes its own tracking); only the message *append* stays
  writer-scoped (initiator appends seamlessly, observers refetch). No hub leader-election needed —
  a surviving window self-serves, so the turn is always tracked + resumable. Unit-proven (the
  observer test now asserts it fires its own fan-out while NOT blind-appending).

**Open deferrals (tracked):** _none._

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
- **PO decisions (LOCKED 2026-06-26):** all greenlit at the fullest build —
  adapt = **per-scene ghost from source**; chat-hoist = **full SharedWorker hub**;
  WS-B3 = **build both deferrals** (prose-persist + vs-canon delta); WS-F = **mobile pass
  now** (two-level nav + heavy-canvas mobile views); **M6** canon-at-chapter inspector
  (both branch-point + per-scene); **M7** per-chapter mention frequency **build now**
  (re-scoped: needs per-*chapter* counts, NOT the per-*scene* `D-P2-PER-SCENE-FANOUT`, so
  it is NOT blocked). Only per-*scene* fanout + CJK alias-per-chapter stay out of scope.
- **Grounding:** 5 read-only research passes over the actual code (2026-06-26), refs inline.

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
3. Gateway/composition public passthrough for glossary `known-entities` + per-chapter
   links (M6) — read-only, VIEW-grant scoped.
4. `chapter_entity_links.mention_count INT` column + `chapterLinkIn` payload field +
   producer count pass (M7) — glossary migration + knowledge→glossary contract.

Everything else is FE + orchestration over already-built infra (derive, critic, ghost,
the SharedWorker template, the `useIsMobile` precedent).

---

# Edge-case hardening (adversarial pass, 2026-06-26)

Decided handling for each edge case found per milestone. These are **design requirements**,
not options — fold into the detailed design. Cross-cutting rules first, then per-milestone.

## Cross-cutting (apply to every milestone)
- **Tenancy/grants** — every new read/write endpoint (M3 prose, M6 passthrough, M7 count)
  filters by `owner_user_id`/`book_id` and is grant-gated (VIEW for reads, EDIT for writes).
  No endpoint returns another tenant's data; no shared-row write. (CLAUDE.md tenancy tiers.)
- **Idempotency** — every write (M3 persist, M7 backfill, M1 ghost-accept) is idempotent on a
  natural key (node_id+version / entity_id+chapter_id) so a double-click / retry / concurrent
  promote is a no-op, never a duplicate or clobber.
- **Degrade-safe** — every LLM-dependent surface (M4 critic, M1 adapt, M2 chat) renders a
  clear "unavailable / not yet analyzed" state on null/empty/degrade — never a broken value
  or a silent empty that reads as "nothing here".
- **Derivative/COW scope** — any derivative write (M3) targets the **derivative** `project_id`,
  never the shared `book_id` draft (would clobber source). Any derivative read windows to
  `branch_point` against the **source** project (the derivative's own project is empty
  pre-promote).

## M0 — world i18n parity
- **Empty-string keys fail too** — the suite checks key-set AND non-empty AND placeholder
  parity. Fill **real translations**, not English copies or blanks.
- **Preserve `{{placeholders}}` verbatim** — translating the placeholder *name* (e.g.
  `{{count}}`→`{{số}}`) fails the placeholder check. Keep tokens identical across locales.
- **Plural/nested keys** — i18next `_plural`/`_zero` suffix keys and nested objects must match
  shape, not just leaf count.
- **zh-TW = Traditional** (not Simplified); **regression guard** is the existing parity test in
  CI — a future en-only key re-breaks it, by design.

## M4 — vs-canon judge delta
- **No canon baseline** — anchor scene's chapter draft is empty/absent → show "no canon
  baseline to compare" (not a 0-delta). Don't fabricate a baseline.
- **Null dims on degrade** — critic down / no distinct critic model configured
  (`engine.py:1447-1454` skips LLM) → per-dim delta null-guards → show absolute take score +
  "vs-canon unavailable".
- **Canon-judge cache key = `(chapter_id, draft_version)`**, NOT `chapter_id` alone — a chapter
  edit changes canon prose; keying on id alone serves a stale delta.
- **Scope mismatch (documented)** — baseline = anchor scene's *chapter* draft (scene prose
  isn't isolated in storage); on a multi-scene/long chapter the critic may truncate. Note as a
  V1 limitation; if scene offsets are known, slice the relevant span.
- **Cost** — judge canon once per `(chapter_id, draft_version)`; only the **chosen** take
  auto-judges; debounce rapid take cycling.

## M6 — canon-at-chapter inspector
- **Not-yet-extracted chapter** — windowed endpoints return empty because extraction is
  pending/never-run → show "chapter not yet analyzed" with the extraction status, not "empty
  canon".
- **`before_chapter_id` unresolvable** (chapter deleted/reordered/not in book) — endpoints
  **fail-closed** (per `timeline.py`); the panel surfaces "window unavailable", never an
  unwindowed whole-book leak.
- **Derivative pre-promote** — window against `source_project_id` at `branch_point` (the
  derivative's own project is empty until promote). Reuse the grounding endpoint's derivative
  branch.
- **glossary vs knowledge skew** — presence (glossary `chapter_entity_links`) and
  facts/statuses (knowledge) are two stores that can disagree; label each by source, don't
  silently merge into one "truth".
- **Large cast** — "entities as of chapter N" can be hundreds → paginate + sort by relevance
  (`major`/`appears`/`mentioned` then coverage); cap the default view.
- **`chapter_index` consistency** — resolve `chapter_id`→order **live** (`resolve_before_order`)
  so a reorder doesn't silently shift the window.

## M3 — prose-persist-on-promote
- **Empty/failed take ghost** — skip persistence for that scene (don't write an empty draft);
  report it in the result count.
- **Source-clobber guard (critical)** — write to the **derivative** project's scene-draft
  store, never `book.get_draft(shared_book_id, chapter_id)`. Add a test asserting the source
  chapter draft is byte-identical after promote.
- **Direct write (no job)** — the take was generated on the canon project pre-promote and
  exists client-side; the new endpoint persists prose **without** a generation_job (the
  existing `jobs/persist` is chapter-only). Provide a job-less scene-draft write.
- **Partial promote** — derive succeeds, some scene persists fail → best-effort per scene,
  surface "N of M scenes got prose"; the empty nodes are valid (acceptance allows it).
- **Idempotent on `node_id`** — a re-promote / double-submit overwrites the same scene draft,
  never duplicates.
- **Format** — convert ghost plain-text → the scene-draft store's expected doc shape
  (Tiptap/JSON) at the boundary.

## M1 — adapt-from-source
- **Pre-branch scene = read-only** — gate the "Adapt from source" action to scenes at/after
  `branch_point`; a pre-divergence inherited scene must NOT be adaptable (it's canon).
- **New derivative scene (no source counterpart)** — a scene added post-branch has no source
  prose → fall back to `draft_scene`, not `adapt_scene`; only offer adapt where a source scene
  exists for that position.
- **Empty source prose** — source chapter draft empty → clear "nothing to adapt" message (or
  fall back to draft), not a silent weak generation.
- **Overrides flow** — an entity-renaming override must reach the adapt prompt so the adapted
  ghost uses the new name (verify the override merge feeds `adapt_scene`).
- **Spoiler-bound the source lens** — `gather_source_scene` reads ≤ the scene's position; it
  must not pull post-branch source prose into the adapt context.
- **Token budget** — long source scene → respect the pack token budget like `gather_recent`
  (truncate/window), don't blow the context.

## M5a — mobile shell + nav
- **Desktop↔mobile breakpoint flip mid-session** — the `useIsMobile` branch swaps shells
  (unmount). Keep workspace/draft state in providers mounted **above** the branch
  (`WorkspaceLayoutProvider`, draft context) so a resize/rotate doesn't lose state. (CLAUDE.md:
  never conditionally unmount stateful state — hoist it.)
- **Persisted `active` is a desktop-only/hidden panel** — clamp to a visible panel on mobile
  (the desktop path already clamps `:321-324`); apply the `threads` gate.
- **Popout deep-link on mobile** — `/composition/popout` is desktop-only → redirect to the
  in-shell panel; never `window.open` on mobile.
- **Soft-keyboard viewport resize** — the bottom group bar must not obscure the editor input
  when the mobile keyboard opens (use `visualViewport`/safe-area, not a fixed bottom that
  overlaps).

## M5b — heavy-canvas mobile views
- **Pinch-zoom vs page-scroll** — set `touch-action` on the canvas so pinch zooms the graph
  and doesn't scroll the page (and vice-versa outside it).
- **Tap vs pan disambiguation** — a tap selects (→ bottom-sheet actions), a drag pans;
  threshold like the desktop dnd distance.
- **Huge graph perf** — cap rendered nodes / virtualize on mobile; fit-to-screen must handle
  1 node and thousands without NaN transforms.
- **Overlapping hit targets** — tap on overlapping nodes → disambiguation (nearest / a small
  picker), with finger-sized hit areas.
- **Timeline horizontal-scroll vs vertical page-scroll** — lock axes so the timeline pans
  horizontally without fighting the page.

## M7 — per-chapter mention frequency
- **CJK counting** — count surface forms with a CJK-aware matcher (longest-match over
  canonical + aliases), NOT a space tokenizer (`feedback_space_tokenizer_degrades_on_cjk`).
- **Alias overlap double-count** — "Harker" inside "Jonathan Harker" → longest-match + span
  dedup so one mention isn't counted twice.
- **Presence-gated frequency** — count only within chapters the entity is **linked** to
  (`chapter_entity_links`); a raw string match in an *unlinked* chapter may be a homonym/other
  entity → don't count it (avoids false positives).
- **Migration default + backfill** — new `mention_count` column defaults 0; backfill is a
  **deterministic recount job** over existing books (no LLM), batched + idempotent.
- **Staleness on edit** — a chapter edit invalidates its counts → recount via the chapter-update
  event consumer (don't serve stale counts).
- **Heatmap windowing** — FE sums counts ≤ cutoff (replacing the whole-book scalar); guard the
  cutoff resolution like M6.

## M2 — chat-hoist
- **Preserve every AG-UI event** — the `runChatTurn` extraction must handle reasoning + 3×
  tool-call frames + 4× CUSTOM sub-events + RUN_FINISHED(suspend) + RUN_ERROR; a dropped type
  is a silent regression → enumerate + test each. **`/review-impl` mandatory.**
- **Single-writer side-effects** — the `onStreamEnd` fan-out (session refresh + pending-facts
  refetch) must fire **once**, not per-window. Elect the originating window or make the effect
  idempotent (dedupe on turn id).
- **Optimistic append dedupe** — two windows appending the same optimistic user message →
  dedupe on a client message id (or append only in the worker snapshot).
- **Resume/tool-result across windows** — a tool result submitted in one window routes through
  the worker `start`; other windows see the resumed turn via the snapshot.
- **SharedWorker absent** (some mobile/embedded browsers) — fall back to the in-process hook
  (the `LiveStateContext` selector pattern); ACK-timeout degrades on script-load failure.
- **Token refresh mid-stream** — the worker holds the bearer; on refresh, plumb the new token
  to the worker (or re-`start` with it) so a long turn doesn't 401.
- **Abort propagation** — stop from any window aborts the worker's single controller → all
  windows see the stop.

## KG extraction-cache (separate spec) — edge cases
See [`docs/specs/2026-06-26-kg-extraction-cache.md`](../specs/2026-06-26-kg-extraction-cache.md) §8.

---

# Parallelization plan (for fan-out build)

Goal: build several milestones concurrently. The blocker is **file overlap** — a few hot FE
files are touched by multiple milestones and cannot be edited by parallel agents without merge
conflicts. The plan = (1) freeze shared contracts, (2) run the genuinely-isolated lanes in
parallel, (3) serialize the canvas cluster under one owner.

## Conflict matrix — which milestone touches which HOT file
| Hot file | M0 | M1 | M3 | M4 | M5a | M5b | M6 | M7 | M2 |
|---|---|---|---|---|---|---|---|---|---|
| `SceneGraphCanvas.tsx` | | | ✔ promote | ✔ judge | | ✔ canvas | ✔ mount | | |
| `CompositionPanel.tsx` | | | | | ✔ mobile | | ✔ register | | |
| what-if hooks (`useWhatIf*`) | | | ✔ | ✔ | | | ✔ | | |
| composition `api.ts` (additive) | | ✔ | ✔ | ✔ | | | ✔ | ✔ | |
| `composition.json` i18n (additive) | | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | |
| chat feature (`useChatMessages` …) | | | | | | | | | ✔ |
| `world.json` i18n | ✔ | | | | | | | | |
| BE composition (`cowrite/lenses/pack`) | | ✔ | ✔ ep | | | | | | |
| glossary + knowledge (cross-svc) | | | | | | | | ✔ | |

**Bottleneck = `SceneGraphCanvas.tsx`** (M3, M4, M5b, M6 — 4-way). Secondary =
`CompositionPanel.tsx` (M5a, M6). `api.ts`/i18n are *additive* (append-only → low conflict if
each milestone uses its own namespace/functions).

## Step 1 — FREEZE these contracts first (single short pass, before any fan-out)
A frozen interface lets BE and FE lanes build against stubs in parallel
(`feedback_run_parallel_tasks_when_possible`):
1. **M1** `adapt_scene` op name + `generate` body param shape.
2. **M3** `POST /works/{project_id}/scenes/{node_id}/prose` request/response + idempotency key.
3. **M6** gateway/composition passthrough endpoints (known-entities, per-chapter links) shapes
   + grant scope.
4. **M7** `chapter_entity_links.mention_count` column + `chapterLinkIn.mention_count` payload
   field.
5. **SceneGraphCanvas extension points** — declare WHERE M4 (judge badge), M3 (promote prose),
   M5b (mobile wrapper), M6 (branch-point mount) each plug in, so the single canvas owner
   sequences them without re-architecting.

## Step 2 — LANES (parallel-safe owners)
| Lane | Milestones | Scope (non-overlapping) | Parallel? |
|---|---|---|---|
| **L-i18n** | M0 | `world.json` ×4 | ✅ anytime, isolated |
| **L-chat** | M2 | chat feature only (`runChatTurn`/hub/worker/provider) | ✅ isolated |
| **L-kg** | KG cache | knowledge-service/worker-ai — **separate branch** | ✅ isolated |
| **L-be** | M1-BE, M3-BE | composition-service Python (`cowrite/lenses/pack`, new prose ep) | ✅ no FE overlap |
| **L-xsvc** | M7-BE | glossary Go migration + knowledge producer + contract | ✅ own services |
| **L-mobileshell** | M5a | `ChapterEditorPage`, `CompositionPanel` mobile branch, new `MobilePanelSwitcher`, hoist `useIsMobile` | ⚠ shares `CompositionPanel` with M6 (see coord) |
| **L-canvas** | M4, M3-FE, M5b, M6-mount | **single owner** of `SceneGraphCanvas.tsx` + what-if hooks; does these 4 **sequentially** | 🔁 serialized internally |
| **L-m6panel** | M6 panel + M6-BE-FE-wire | new `CanonAtChapterPanel` (isolated new file) + per-scene mount + passthrough client | ⚠ panel registration in `CompositionPanel` (coord with L-mobileshell) |

**Coordination points (the only cross-lane edits):**
- `CompositionPanel.tsx` — **L-m6panel registers the panel** (additive: PANEL_IDS + DockSlot),
  then **L-mobileshell** consumes the panel list. Sequence: m6 registration → mobileshell, or
  let L-mobileshell own the file and m6panel hands it the registration diff.
- `SceneGraphCanvas.tsx` branch-point mount — owned by **L-canvas**; L-m6panel provides the
  panel component as a prop/slot, L-canvas wires the mount.

## Step 3 — WAVES (dependency order)
- **Wave A (parallel, immediately):** L-i18n (M0), L-chat (M2), L-kg, L-be (M1/M3 BE),
  L-xsvc (M7 BE) — five lanes, zero file overlap. Plus the **contract freeze** (Step 1) gating
  the FE lanes.
- **Wave B (parallel, after contracts + relevant BE stubs):** L-mobileshell (M5a),
  L-m6panel (M6 panel+wire). Coordinate the `CompositionPanel` touch.
- **Wave C (serialized lane, runs alongside A/B):** L-canvas does M4 → M3-FE → M6-mount → M5b
  in order (all on `SceneGraphCanvas`).
- **Integration:** M6-mount (needs M6 panel from L-m6panel) and M3-FE (needs M3-BE ep) join at
  the end of their dependency.

## Step 4 — Fan-out mechanics
- Each parallel lane = **its own worktree** (`isolation: worktree`) so concurrent file writes
  don't collide; merge per-lane at a green checkpoint.
- **Per-lane gate** stays full: VERIFY evidence, 2-stage REVIEW, `/review-impl` for the
  load-bearing lanes (L-chat/M2, L-xsvc/M7, L-be/M1, L-kg), live-smoke for cross-service
  (M1, M3, M6, M7, KG) + browser two-window (M2, M5).
- **Order of merge** to minimize rebase: L-be + L-xsvc (BE contracts land) → L-m6panel →
  L-canvas → L-mobileshell → L-chat → L-i18n. KG-cache merges to its own branch independently.

## Detailed design — next step (itself fan-out-able)
Per-milestone detailed design (file-level change lists, test plans, exact signatures) is the
natural next fan-out: **one design agent per lane**, each producing its milestone's detailed
design against the frozen contracts above. That is the recommended "fan out" entry point for
the next session.
