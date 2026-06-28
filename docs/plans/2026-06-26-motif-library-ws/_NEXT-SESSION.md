# ▶ NEXT SESSION — Narrative Motif Library BUILD (handoff)

## STATUS (2026-06-28 PM-13) — D-W10-FE-PLACE-MOTIF-PICKER CLEARED (the "+ place" picker)

**`D-W10-FE-PLACE-MOTIF-PICKER`** ✅ — the timeline "+ place" affordance no longer authors empty-coded
`—` stubs. Both surfaces now open a **motif picker** (the existing `SwapMotifPopover` + `useMotifCandidates`)
and place a REAL motif (code + id + name) — resolvable by materialize, labelled in the grid. FE-only
(consumes the live `motifApi.list`).
- `MotifCandidateOption` += `motif_code`; `useMotifCandidates` maps it. The frozen `ArcTimelineEdit`
  `place` gained optional `motif_id`/`motif_name` (additive); the reducer stamps them (was hard-null).
  `ArcTimelineContract` += optional `candidates`; `placeEditFromCandidate` builds the edit.
- Mobile list "+ place" → picker (was: emit empty-code immediately). Grid gained a per-thread "+"
  place button (it had NONE) → picker. No candidates ⇒ no place affordance (can only rearrange
  existing — the read-only / no-library degrade). `ArcTimelineEditor` fetches candidates only when editable.
- **VERIFY:** 126 motif FE tests (+5: reducer place-with-id + `placeEditFromCandidate`, grid place +
  no-candidates, mobile picker-flow + no-candidates), 0 tsc errors. a11y: `aria-haspopup`/`expanded` +
  an `aria-label` on the grid "+" button; the picker is `SwapMotifPopover` (focus-trap, Esc-close).

## STATUS (2026-06-28 PM-12) — W10 arc loop CLOSED (FE "Materialize to this book" wired)

The W10 arc feature is now end-to-end from the UI: the apply-preview gained a **"Materialize to
this book"** commit action wiring the PM-11 endpoint. FE-only (consumes the live-verified
`POST …/works/{projectId}/arc/materialize`).
- `arcApi.materialize` + `ArcMaterializeArgs`/`ArcMaterializeResult` types + `useArcMaterialize`
  (mutation; invalidates the planner decompose + motif-bindings queries on success; surfaces 409
  as `conflict`). NEW `ArcMaterializeAction` — commit button → on 409 a "Replace existing" affordance
  re-POSTs `replace:true`; the result summarizes committed scenes/chapters + unresolved + scale-folded
  motifs (§12.6 never silent). `projectId` threaded CompositionPanel(`work.project_id`) → MotifLibraryView
  → ArcTemplateLibraryView → ArcApplyPreview; absent ⇒ preview-only (the C16 pending-work degrade).
- **VERIFY:** 121 motif FE tests (+9), 0 tsc errors project-wide. The BE endpoint was already
  live-smoked (PM-11); this is its FE consumer against the same contract. **FE bundle rebuild needed to
  see it in the browser** (deployment step; `infra-frontend-1`).

## STATUS (2026-06-28 PM-11) — D-W10-APPLY-PLANNER-MATERIALIZE CLEARED (arc apply → committed outline, live)

**`D-W10-APPLY-PLANNER-MATERIALIZE`** ✅ — the arc-apply preview now MATERIALIZES into a committed
arc→chapter→scene outline + a `motif_application` ledger. **DETERMINISTIC (no LLM)** — the key finding
was that `engine/motif_select.scenes_from_motif` already turns a motif's beats → ScenePlans with no LLM
("the motif IS the structure"), so materialize reuses the exact A3 commit primitives
(`commit_decomposed_tree` atomic+idempotent+replace · `MotifApplicationRepo.insert_many`). The richer
per-scene prose stays the EXISTING downstream generate path. Plan doc: `docs/plans/2026-06-28-arc-materialize.md`.

- **NEW `engine/arc_materialize.py` (pure):** `build_materialize_spec` distributes EVERY beat of each
  placement across its chapter span (`beat j → s + floor(j*w/n)`, grouped per chapter — no beat lost,
  §12.6), binds the motif roles to the book cast (`bind_motif` name-hints) with the **arc roster
  (bound once, by name) overriding** any role key it covers, and emits per-chapter scenes + ledger
  payloads (beat_key + arc lineage in annotations). Unresolved placements are SURFACED, never dropped.
- **NEW `MotifRepo.get_by_codes`** (additive): tier-merged code→Motif resolution (caller's own shadows
  system) for placements that carry a `motif_code` but no pinned `motif_id`.
- **NEW endpoint `POST /v1/composition/works/{project_id}/arc/materialize`** (in plan.py, the decompose
  family): maps the arc onto the book's EXISTING chapters (target = book chapter count; `build_apply_plan`
  rescales), resolves motifs, builds the spec, commits via the A3 primitives, ledgers the bindings
  (FK-tolerant, non-atomic — mirrors decompose). Guards: H13 arc 404, NO_CHAPTERS, TOO_MANY_CHAPTERS,
  NO_MATERIALIZABLE_PLACEMENTS (all-unresolved 400), AlreadyPlanned 409, replace + idempotency_key.
- **REVIEW fix-now (§12.6):** the response now includes `drop_merge_report` — when the book has fewer
  chapters than the arc span, placements merge and the folded-away motifs aren't materialized; surfaced.
- **/review-impl fix-now (MED):** the per-chapter scene cap (`max_scenes=6`) was clipping a placement's
  beats when >6 landed in one chapter (e.g. an 8-beat motif on a width-1 span) → silent beat loss,
  contradicting the no-beat-lost invariant. Fixed: materialize passes `max_scenes=len(subset)` so EVERY
  distributed beat becomes a scene (+1 test, 16 total). LOW accepted: N+1 `get_visible` (perf), possible
  duplicate present_entity_ids (display hint).
- **VERIFY:** 15 new unit tests (10 pure engine + 5 route, fakes) + 41 regression (plan-router/scene-bind/
  arc-apply) green; 1011 collected; provider-gate clean. **Live cross-service smoke** (rebuilt
  composition-service): throwaway book(2 ch) + work + arc(2 system motifs, 4 beats each) → materialize →
  **chapters=2, scenes=8, applications=8, beats_distributed=8, unresolved=0**; the ledger reads back via
  the FE `motif-bindings` endpoint (4 bound scenes on ch1, beat_key='surface', motif='Auction-House
  Treasure'). Cleaned up (arc archived, book deleted; orphan work inert — no work-DELETE route, 405).

**▶ Remaining motif defers:** `D-W10-ARC-CONFORMANCE` (blocked on W5 arc-diff), `D-W10-FE-PLACE-MOTIF-PICKER`
(mobile place-empty-motif, needs a picker), `D-MOTIF-PGVECTOR-TRIGGER` (perf), conformance activation
(human config), scene `rebindRole`/`chainIt` routes (low-reach). A natural NEXT-NEXT: a thin FE
"materialize this arc" button wiring the new endpoint (the editor's apply-preview already exists).

## STATUS (2026-06-28 PM-10) — D-W10-FE-TIMELINE CLEARED (the arc-timeline FE subtree, full-stack-verified)

**`D-W10-FE-TIMELINE`** ✅ — the FE thread×chapter arc-timeline editor (spec §10 / W6 §5.4) is built
against the frozen `ArcTimelineContract` + the `ArcApplyPlan` data contract. **FE-only** (0 backend /
0 cross-service — it consumes the already-shipped W10 `arc-templates` CRUD + apply routes). **43 new
unit tests** (motif folder 69→112), **0 tsc errors project-wide**, and a **live cross-service contract
smoke** (below). Surfaced inside the motif dock panel via a `Motifs | Arc templates` kind-toggle.

- **Data brain (M1):** `arcTypes.ts` (wire DTOs mirrored from `app/db/models.py`), `arcApi.ts`
  (list/get/create/patch/archive/adopt/apply, mirrors `motifApi` + If-Match), `applyArcEdit.ts` — the
  PURE reducer both surfaces drive (place/move/resize/remove, all clamped) + layout↔placement mapping
  + `dragEndToMoveEdit` pointer geometry, and `useArcTimeline` (fetch → working copy → optimistic edit
  → DEBOUNCED If-Match PATCH → adopt server version; owner-gated `canEdit`; 412 → reconcile).
- **Editor (M2):** `ArcTimelineGrid` (desktop) — the audit-mandated **keyboard model** (Tab→Enter
  grab→Arrow move / Shift+Arrow resize / Arrow↑↓ thread / Enter drop / Esc release; `aria-grabbed` +
  `aria-describedby` "combat thread, chapters 2-3" + a polite live-region) **plus** dnd-kit pointer
  drag (studio idiom). `ArcTimelineEditor` — responsive shell swapping grid (≥md) ↔ the existing
  `ArcTimelineMobileList` (<md) via `useIsMobile`; the stateful hook is hoisted ABOVE the swap so a
  breakpoint change never loses edit state. Read-only (adopt-to-edit) for system/foreign arcs.
- **Apply-preview (M3):** `useArcApplyPreview` + `ArcApplyPreview` — target chapters + roster-bind →
  POST …/apply → renders the deterministic plan (rescaled placements, the §12.6 drop/merge report,
  unbound roster slots). PREVIEW-ONLY by design (committing to outline rows stays
  `D-W10-APPLY-PLANNER-MATERIALIZE`). `useArcLibrary` + `ArcTemplateLibraryView` (list → select →
  editor + apply-preview), wired into `MotifLibraryView` via the kind-toggle.
- **Live contract smoke (cross-service):** logged in (test acct) → `POST/GET/POST apply/DELETE` against
  the running `infra-composition-service-1` (:8217). `ArcTemplate`, `ArcApplyPlan`, `ResolvedPlacement`
  JSON keys match the TS types **exactly**; rescale+merge worked live (source 10→target 2 merged
  `ambush` into `duel`, `unbound:[mentor]`). Throwaway arc archived; test account only.
- **/review-impl (adversarial) — 1 HIGH + 1 MED FIXED (@ this commit's follow-up), 3 LOW documented:**
  - **HIGH (data loss):** `placementsToLayout` dropped the backend `role_hints`+`triggers` (§15.3) →
    the layout PATCH (full-array replace) wiped them for ALL placements on the first edit. FIXED:
    carry them as opaque optional passthrough on the contract `ArcPlacement`, mapped both directions;
    the reducer's `{...p}` preserves them. **Live-verified**: a layout PATCH (span 2-3→4-5) now keeps
    `role_hints`/`triggers` intact on GET.
  - **MED (double-write):** the debounce timer never nulled its ref → an unmount AFTER the timer fired
    but BEFORE the PATCH resolved re-fired `persist()` (duplicate write + 412 + post-unmount setState).
    FIXED: null `timerRef` as the timer fires; +2 tests (flush-on-unmount persists once; no double).
  - **LOW (accept+document):** refetch-time external version bump silently re-seeds over unsaved local
    edits ("server wins"); `placementsToLayout` renumbers `ord` 0..n per thread (apply re-sorts, benign);
    `arcApi.create/archive/adopt` exported but unwired (future surface).

**▶ Remaining motif defers are all large/structural, blocked, perf, or config:**
`D-W10-APPLY-PLANNER-MATERIALIZE` (arc apply → committed outline — large BE, commit-path),
`D-W10-ARC-CONFORMANCE` (blocked on W5 arc-diff), `D-MOTIF-PGVECTOR-TRIGGER` (perf, fix-when-profiling),
conformance activation (human config), and the scene `rebindRole`/`chainIt` routes (low-reach). Each is
its own focused effort — pick one explicitly.

## STATUS (2026-06-28 PM-9) — D-MOTIF-CONFORMANCE-PRODUCER-LIVE-SMOKE CLEARED (full loop, live)

**`D-MOTIF-CONFORMANCE-PRODUCER-LIVE-SMOKE`** ✅ — the conformance loop is now proven end-to-end on
the real stack, unblocked by PM-8's per-scene bind. No code change (a verification); no shared
container config mutated (conformance was enabled IN-PROCESS in a throwaway script).
- **Method:** bound the Auction-House-Treasure motif to a committed scene via the PM-8 PATCH route,
  then ran `maybe_conformance_patch` directly in `infra-composition-service-1` against a real
  **Qwen2.5** judge (lighter than a full worker generate; the producer is the deferred slice).
- **Producer (real LLM) discriminates:** REALIZED auction prose → `beat_realized:true,
  tension_band_match:true` ("Intent enacted; tension fits band."); a quiet unrelated scene →
  `false,false` ("No auction, no tension."). Band derived `[65,95]` (tension 80 ± 15).
- **Persist → trace:** persisted the REALIZED verdict to a COMPLETED `generation_job.critic`
  (the exact `job_consumer` path: `update_status(result=…, critic=patch)`), then `GET /conformance`
  surfaced it on the scene: `planned.motif_id`=the bound motif, `realized.has_prose:true`,
  `conformance`={beat_realized:true, tension_band_match:true, calibrated:false,
  planned_tension_band:[65,95], …} — the EXACT PM-7 nested `ConformanceDim` shape. The PM-7
  `ConformanceSceneRow` renders this as "✓ On beat · Advisory — unverified self-report".
- **Closes the loop:** PM-8 bind → producer (real judge) → persist → trace → PM-7 FE shape, all live.
- **Cleanup:** the smoke binding (DELETE → removed:1) + the smoke `generation_job` (DELETE 1) were
  removed; the scene is back to free-form/null. Test account only.
- **Activation is STILL a human config decision:** `motif_conformance_enabled` stays **false** in
  the containers (the smoke flipped it in-process only); `motif_conformance_calibrated` stays false
  (single-local-judge → the dim ships honest 'unverified'). Flip both in env to turn it on for real.
- **Infra note:** a Docker restart (session resume) had left `infra-postgres-1` / `redis` /
  `api-gateway-bff` exited (composition-service was crash-looping on DB DNS) — brought them back with
  `docker compose up -d postgres redis api-gateway-bff`; stack healthy again.

**▶ Remaining motif defers are all large/structural, blocked, perf, or config:** `D-W10-FE-TIMELINE`
(thread×chapter arc-timeline editor — large FE), `D-W10-APPLY-PLANNER-MATERIALIZE` (arc apply →
committed outline — large BE, commit-path), `D-W10-ARC-CONFORMANCE` (blocked on W5 arc-diff),
`D-MOTIF-PGVECTOR-TRIGGER` (perf, fix-when-profiling), conformance activation (human config), and the
scene `rebindRole`/`chainIt` routes (low-reach: manual binds leave roles unresolved + succession
isn't surfaced). Each is its own focused effort — pick one explicitly.

## STATUS (2026-06-28 PM-8) — D-MOTIF-FE-SWAP-NODE-GRANULARITY CLEARED (per-scene bind, new BE)

**`D-MOTIF-FE-SWAP-NODE-GRANULARITY`** ✅ (decision: *per-scene bind, new BE*). Shape A presents a
per-SCENE binding surface, but W2's `apply_motif_swap` REQUIRES a chapter node (a motif's beats
*become* the chapter's scenes) — so a scene-node swap 404'd. Added a real per-scene bind path:
- **BE `routers/plan.py`** — the PATCH `…/outline/{node_id}/motif` route is now **node-kind-aware**:
  a **chapter** node → the existing heavy `apply_motif_swap` (unchanged); a **scene** node → the
  new `_bind_scene_motif` — a lightweight ledger write (one `motif_application` replacing the node's
  prior binding via `delete_for_nodes`+`insert_many`, motif-level so `beat_key` null, `annotations.
  bound_via="manual_scene"`), NO scene regeneration. Roles resolve via `bind_motif` (cast name-hint;
  partial bind is fine). `motif_id=null` clears. NEW **DELETE** `…/outline/{node_id}/motif` route
  (was missing entirely — the FE's `clearMotif`/`rebindRole`/`chainIt` all 404'd): scene → drop the
  ledger row; chapter → motif-less `apply_motif_swap`. H13 uniform 404 on missing/cross-project node
  or non-visible motif; no write on a rejected motif.
- **FE** — `MotifBindingCard`'s FREE-FORM branch gained a **"Bind motif"** affordance (the gap that
  made the surface read-only post-commit): opens the same `SwapMotifPopover` → `onSwap` → PATCH. New
  `useMotifCandidates(token)` lists the user's visible motifs (scope=all, ≤100) as the picker
  options; `ChapterMotifBindings` fetches once + passes to every card.
- **Tests:** 7 new BE (`test_scene_motif_bind.py` — `_bind_scene_motif` clear/bind/404 + route
  node-kind dispatch scene/chapter/missing + DELETE) + the existing chapter-swap test updated
  (`StubOutline.get_node`); +1 FE (free-form bind → PATCH `…/n2/motif`). **599 composition FE +
  7 BE green; tsc clean; provider-gate clean.**
- **LIVE-VERIFIED** (rebuilt composition-service + frontend, authed gateway calls): scene **bind**
  → 200 `bound:true` (the node that 404'd in PM-6); **re-read** shows it bound while siblings stay
  free-form; **DELETE clear** → 200 `removed:1`; **re-read** back to null (replace left no dup). The
  FE bind affordance is unit-verified (the browser click-through hit unrelated dock/modal harness
  friction; the bind/swap/clear path itself is live-proven through the gateway).
- **Still deferred (scene-scoped refinements):** `rebindRole` (PATCH `…/motif/role`) and `chainIt`
  (POST `…/motif/chain`) routes still don't exist for ANY node (pre-existing) — a bound scene's
  role-rebind / chain buttons remain inert. Out of scope for the bind/swap/clear core; track if a
  user hits them.

## STATUS (2026-06-28 PM-7) — D-MOTIF-CONFORMANCE-CONTRACT CLEARED (FE↔reader reconciled, live)

**`D-MOTIF-CONFORMANCE-CONTRACT`** ✅ — the W6 conformance FE panel now mirrors its W5 reader.
Aligned the FE to the reader's NESTED shape (`routers/conformance.py _assemble_conformance` +
the `build_conformance_dim` dim) instead of the old flat `SceneConformance`:
- `motif/types.ts`: new `ConformanceDim` (`beat_realized|tension_band_match: bool|null`, `reason`,
  `motif_id`, `beat_key`, `planned_tension_band`, `calibrated`, `error?`); `SceneConformance` is now
  `{outline_node_id, title, beat_role, planned{motif_id,motif_version,beat_key,tension,role_bindings},
  realized{job_id,has_prose}, conformance: dim|null}`; `ChapterConformance` = `{scope?, chapter_id,
  calibrated, scenes}`. **Dropped** `conform_count` + `motif_name` (the reader never sent them; a
  single chapter motif_name is ill-defined — a chapter holds per-scene motifs).
- `ConformanceSceneRow.tsx`: reads the nested shape; 3 verdict states — judged (✓/⚠/✗ + advisory
  when `!calibrated`, R2.1), `null` verdict → neutral "Not checked yet", degraded judge (null
  booleans + `error`) → "Couldn't check". Realized is presence-only ("Written"/"Not written yet" —
  the trace never carries prose).
- `ConformanceTraceView.tsx`: DERIVES the `[conforming/judged]` header count from the per-scene
  verdicts (the reader emits no `conform_count`).
- Tests reshaped: `ConformanceSceneRow` (5, +null/degraded), `contract.test` (nested fixture, asserts
  no `conform_count`), `ConformanceTraceView` (derived-count). **598 composition FE green; tsc clean.**
- **LIVE-VERIFIED:** `GET …/conformance?scope=chapter` returns exactly the new shape (`{scope,
  chapter_id, calibrated, scenes:[{…planned,realized,conformance:null}]}`); the panel — which
  WHITE-SCREENED in PM-6 — now renders 3 real scene rows ("Planned setup T20 / Realized Not written
  yet / Conformance Not checked yet"), no boundary fallback, no crash. (Conformance dim is null
  because the producer is OFF by default — populating it is `D-MOTIF-CONFORMANCE-PRODUCER-LIVE-SMOKE`,
  separate.) The PM-6 `MotifPanelBoundary` stays as defense-in-depth.

**Still open from PM-6:** `D-MOTIF-FE-SWAP-NODE-GRANULARITY` (per-scene surface vs per-chapter W2
bind engine — needs the binding-granularity decision before building).

## STATUS (2026-06-28 PM-6) — D-MOTIF-FE browser smoke RUN · 2 crashes FIXED · 2 new defers

Ran the deferred Playwright smoke for `D-MOTIF-FE-PLANNERVIEW-WIRING` (Shape A) on the **real
stack** (frontend `infra-frontend-1` + composition-service rebuilt from this branch, live Qwen2.5
decompose). It **passed the read-side end-to-end AND surfaced 3 real bugs the mocked unit tests
hid** (2 now fixed, 1 deferred).

**PROVEN live (book 万古神帝 `019eb60e…`, project `019eb683…`, chapter 1 `019eb60f-3b81…`):**
- New FE bundle deploys; the planner panel renders `PlannerView` (Shape A).
- Plan (real Qwen2.5 decompose) → editable draft tree; commit → **409 replace-confirm flow** →
  replace → success.
- **Shape-A committed-binding surface renders: 25 per-scene `MotifBindingCard`s**, scene titles
  from the committed-outline read ("The Reborn Prince" …), all correctly `free-form` (nothing
  auto-bound post-commit).
- **Read endpoint live 200 + correct shape**: `GET …/works/{proj}/outline/motif-bindings?chapter_id=`
  → `{chapter_id, bindings:{node→null}}` (3 nodes for ch.1). Verified via authed gateway call.

**FIXED NOW (2 app-crashing white-screens — `CompositionPanel` mounts ALL ~22 sub-panels at once,
CSS-hidden, with NO error isolation, so one panel throw blanks the whole studio):**
1. **`ConformanceTraceView` `conform_count[0]` crash** — the chapter reader (`GET …/conformance`)
   does NOT emit `conform_count`; the header dereferenced `conf.conform_count[0]` unguarded →
   white-screen on every chapter. Guarded (`Array.isArray`) + made the two summary fields optional
   in the type. +2 regression tests.
2. **`ConformanceSceneRow` `scene.flags.length` crash** — the reader's scene rows are NESTED
   (`{planned,realized,conformance}`) but the FE `SceneConformance` type is FLAT; every field is
   `undefined` → crash whenever a chapter has committed scenes. Contained by a new
   **`MotifPanelBoundary`** (React error boundary) wrapping the two W6 dock panels (motifs +
   conformance) in `CompositionPanel` → a motif-panel throw now degrades to an in-panel fallback,
   never the studio. +3 boundary tests. (596 composition FE tests green; tsc clean.)
- **Deployment note:** the read 404'd at first because the running `infra-composition-service`
  image predated BE commit `83a07b79`; rebuilt + recreated (`--no-deps composition-service
  composition-worker`) → route live. SHARED env: another track can recreate it from a cached
  pre-`83a07b79` image — re-`build` if `/openapi.json` lacks `outline/motif-bindings`.

**NEW DEFERS (both gate-2 large/structural):**
- **`D-MOTIF-CONFORMANCE-CONTRACT`** — the W6 conformance FE panel is unreconciled with its W5
  reader: (a) the reader omits `conform_count` + `motif_name`; (b) its scene rows are NESTED
  (`{planned,realized,conformance}`) while `SceneConformance`/`ConformanceSceneRow` expect a FLAT
  shape — so the panel can render NOTHING correctly (currently shows the boundary fallback when a
  chapter has scenes). Fix = reconcile the FE types + `ConformanceSceneRow` to the reader shape
  (and decide whether the reader should compute `conform_count`/`motif_name`). Needs a contract
  pass across `routers/conformance.py` ⋈ `motif/types.ts` + `ConformanceSceneRow.tsx`.
- **`D-MOTIF-FE-SWAP-NODE-GRANULARITY`** — Shape A presents a per-SCENE binding surface, but W2's
  bind engine is per-CHAPTER: `PATCH …/outline/{node}/motif` → `apply_motif_swap` REQUIRES a
  **chapter** node (`MotifSwapError` → 404 on a scene node; confirmed live). And
  `MotifBindingCard` shows the Swap/clear affordance ONLY for an already-BOUND scene — a free-form
  scene has NO bind entry point. So post-commit (all free-form) the surface is effectively
  read-only: you cannot bind/swap a scene's motif from it. The per-scene READ is correct
  (motif_application is per-scene `outline_node_id`); the WRITE path needs either a real per-scene
  bind endpoint or the surface re-targeted to chapter-node swaps + a free-form→bind affordance.
  Decide the binding granularity (the PM-5 "scene-level" decision collides with the chapter-level
  W2 engine) before building.
- **Smoke side-effect (benign):** the commit REPLACED the test project's planned outline for ch.1–7
  with the smoke premise's scenes (old scenes ARCHIVED, not deleted, per R2.6; book PROSE in
  book-service is untouched — only the composition planning layer changed). Test account, expected
  smoke surface.

## STATUS (2026-06-28 PM-5) — D-MOTIF-CONFORMANCE-ENGINE-WIRING done · D-MOTIF-FE scoped (XL)

**`D-MOTIF-CONFORMANCE-ENGINE-WIRING`** ✅ `1466215c` (decision: *wire it, keep 'unverified'*).
New `engine/motif_conformance_producer.py`: the per-scene `run_generate` producer now resolves a
node's bound `motif_application` (tenant-scoped, read-only over W2's table) → motif + the specific
beat → `should_judge_conformance` (sampled) → `judge_motif_conformance` → `build_conformance_dim`
(`calibrated` from config = **false**) → `merge_conformance`. The patch rides `result['_critic']`;
the consumer pops it onto the job's `critic` column (COALESCE-safe `update_status`). Advisory +
degrade-safe (gated OFF by default via `motif_conformance_enabled`; never raises/fails a generate;
prefers the distinct critic). 7 producer unit tests + 137 related green; provider-gate clean.
**ACTIVATION = config:** flip `motif_conformance_enabled=true` to run it; `calibrated` stays false
(single-local-judge panel-safety) → FE labels the dim 'unverified self-report'. Judge path was
live-proven in D-MOTIF-CONFORMANCE-GOLD-SET (gemma-4-26b). Deferred: a full producer→persist→trace
**e2e** live-smoke (`D-MOTIF-CONFORMANCE-PRODUCER-LIVE-SMOKE`, gate-4 — run when enabled + a bound
scene exists; the slices are unit+live proven).

**`D-MOTIF-FE-PLANNERVIEW-WIRING`** ✅ BUILT (Shape A, scene-level, full-stack) — only a Playwright
browser smoke remains (needs the FE container rebuilt to deploy the new bundle). Commits:
- BE `83a07b79`: GAP-1 fix (persist plan-time `match_reason` into `motif_application.annotations`)
  + `GET …/outline/motif-bindings?chapter_id=` → `{node_id: BoundMotif|null}` (pure
  `_assemble_motif_bindings`, tenant-scoped, null=free-form). 8 unit tests.
- FE layer `d72699ad`: `compositionApi.getMotifBindings` + types + `useMotifBindings` +
  `ChapterMotifBindings` (per-scene card; each child owns its `useMotifBinding(nodeId)`). 5 vitest.
- FE mount `2102fb56`: `usePlanner.committedChapterIds` (set on commit, cleared on preview) +
  `PlannerView` conditionally renders `CommittedSceneBindings` (owns the lazy committed-outline read).
  tsc clean; **591 composition FE tests green**.
**▶ ONLY REMAINING:** rebuild `infra-frontend-1` to deploy the bundle, then a Playwright smoke
(plan → commit → see per-scene cards → swap a motif → verify the PATCH + re-read). Optionally wire
`onSelectScene` in `CompositionPanel` (selectTab('compose')+setSceneId) so the commit→generate link
routes — currently a no-op when the prop is absent (the bind/swap core works without it).

<details><summary>(historical) the two gaps found while scoping — now fixed</summary>

It was an XL full-stack feature, not an FE wire, with TWO real gaps found while tracing it:
- **GAP-1 (BE): `match_reason` is not persisted.** W2's `bind_motif`/`_bind_annotations`
  (`engine/motif_select.py`) stores only `info_asymmetry` into `motif_application.annotations`
  (+ `role_bindings`, `beat_key`). `match_reason` is a PLAN-TIME artifact (`SelectedMotif.match_reason`
  — `{tension,genre,precond,cosine}`) that is NOT written to the application row. So a post-commit
  binding read returns `match_reason: {}` and `MatchReasonChip` degrades. Fix options: persist
  `match_reason` into `annotations` at bind time (small `motif_select` + binder delta), OR accept the
  empty chip on a post-hoc read.
- **GAP-2 (FE): no committed-scene surface exists.** `PlannerView` renders the pre-commit
  `usePlanner.preview` only; after commit it navigates away. There is NO "committed outline with
  per-scene cards" view to hang `MotifBindingCard` on — that surface must be BUILT (read `GET
  …/outline` for committed scene nodes + a new per-node binding read).
- **Building blocks that DO exist** (so the build is bounded): `BoundMotif`/`DecomposeSceneMotif`
  types, `useMotifBinding` (swap/rebind/clear/chain/regenerate over a nodeId), `MotifBindingCard`,
  `GET …/works/{project_id}/outline` (committed nodes), the `motif_application` table + the
  `ConformanceTraceReader.apps_by_nodes` query to copy.
- **Build steps:** (BE) a `GET …/outline/motif-bindings` (or extend the outline read) returning
  `{node_id: BoundMotif}` via `motif_application ⋈ motif.get_visible` (+ GAP-1 decision); (FE) a
  committed-scene binding section rendering `MotifBindingCard` per node wired to `useMotifBinding`;
  tests both sides + a **Playwright browser smoke** (load-bearing planner UI). Est. L. Start here.

</details>

---

## STATUS (2026-06-28 PM-4) — D-MOTIF-CONFORMANCE-GOLD-SET — gate CALIBRATED

**`D-MOTIF-CONFORMANCE-GOLD-SET`** ✅ `575d79af` — the W5 conformance judge now has a real
Source-A gold set. Replaced the 4 scaffolding rows in `scripts/motif_conformance_gold/po_seed.jsonl`
with **25 curated author-written scenes** (ground-truth-by-construction, abstract §12.6, over the
real seeded motifs), balanced + decorrelated so both binary sub-flags see both classes
(T/T 9 · F/F 8 · T/F 4 · F/T 4 → each flag 13T/12F).
**Live calibration** (composition → provider-registry → lm_studio `gemma-4-26b`, cross-service
live-smoke): **GATE = CALIBRATED** — `beat_realized` kappa=1.000/bacc=1.000; `tension_band_match`
kappa=0.762/bacc=0.885 (the harder axis, 3 fn). Both clear kappa≥0.4 & bacc≥0.75.
**NOT activated:** `motif_conformance_calibrated` stays false — the gate says a HUMAN may flip it,
and the single-local-judge panel-safety caveat (no ≥2 disjoint judges) makes activation a human
call, tied to the still-open `D-MOTIF-CONFORMANCE-ENGINE-WIRING`. The dim ships honest 'unverified'.
Re-run anytime: `python scripts/calibrate_motif_conformance.py` (live) / `--offline` (shape only).

---

## STATUS (2026-06-28 PM-3) — D-W7-VI-PACK BUILT (vi seed packs) · ⏳ awaiting PO genre sign-off

**`D-W7-VI-PACK`** ✅ engineering done + verified — ⏳ **PO genre-faithfulness review OUTSTANDING**
(`D-W7-PO-REVIEW`). The Vietnamese SOURCE-OF-TRUTH sibling packs are authored + loading:
- 5 new packs `app/db/seed_motif_packs/{cultivation,revenge,intrigue,hooks,emotion_arcs}_vi.json`
  — SAME codes as en, `language:"vi"` → distinct ids via `_motif_id(code, language)` (R1.1.3 key).
  44 vi rows mirror the 44 en rows 1:1 (identical code/kind/category/genre_tags/role keys/beat
  keys+orders+tensions); only the human-readable fields (name/summary/labels/intents/precond/
  effects/examples/emotion_target, + intrigue `gap`) are natural genre-faithful Vietnamese
  (tu-tiên / báo-thù / cung-đấu register). Authored by 5 parallel subagents, structure-verified.
- **Loader** `seed_motifs.py`: `_MOTIF_PACKS` += the 5 vi packs; **`load_link_edges` is now
  multi-language** — links.json is ONE manifest, emitted once PER language whose endpoints both
  exist (the old `by_code` dict collided on shared codes). en + vi chains both wired.
- **Tests**: `test_seed_motifs.py` inventory → 88 rows / 24 precedes / 14 composed_of; the kind-
  per-pack check is `_vi`-suffix aware. **12 unit pass + 5 DB-integration pass** (real Postgres:
  88-row idempotent double-seed, system-tier count, NULL-embed, same-tier links). Provider-gate clean.

**PO REVIEW DONE** (`D-W7-PO-REVIEW` ✅, edits @`86ed6ec9`) — the PO reviewed the rendered packs +
made the one systemic call: **`emotion_target` is a stable English taxonomy token** (matches en +
`genre_tags`) across all 44 vi rows, so it's a shared cross-language axis (display text stays vi).
Also: POV role term unified to "nhân vật điểm nhìn" (hooks↔emotion_arcs parallel-authoring drift);
one wording fix (`life_and_death_duel`). NOT changed: intrigue I1/I6 `emotion_target:"dread"` is
FAITHFUL to en (not a vi defect) → kept for parity. Per-row spot-edits remain welcome later (data-
only + `reseed=True`). Genre register verdict: authentic tu-tiên/báo-thù/cung-đấu; fit to seed.

---

## STATUS (2026-06-28 PM-2) — D-W8-MINE-LIVE-SMOKE PASSING (full cross-service mine→draft)

**`D-W8-MINE-LIVE-SMOKE`** ✅ — the LAST big W8 gap is closed end-to-end on the real stack.
- **knowledge-service REBUILT** (`docker compose build` + `up -d --force-recreate --no-deps
  knowledge-service`) to deploy the `motif_beat` extractor route @73004c33. Verified live:
  `POST /internal/extraction/motif-beats` returns `event_order`-ordered `{beat,thread,tension,
  role_mentions}` sequences. (Container `infra-knowledge-service-1`.)
- **Seeded a mineable `:Event` corpus** for the test account: 4 book-projects (4 PrefixSpan
  sequences) — 3 revenge books sharing a SHORT core `humiliation→exile→face slap` (support 3,
  with book-unique padding beats at support 1 so PrefixSpan yields a tight 4-pattern set, not a
  2^n blow-up) + 1 romance negative control. `chapter_id=None` → the miner symbol is the bare
  beat label (cross-book shape match). **Seeded via knowledge-service's own `merge_event`** (exact
  `:Event` shape) — NOT raw Cypher.
- **Ran the real mine** (`run_mine_motifs`, scope=corpus): composition → the live motif-beats route
  → Neo4j corpus → PrefixSpan (4 patterns) → **Qwen2.5** abstraction + binary judge (provider-registry
  → lm_studio) → **mined=4 draft motifs**, `below_gate=0`, `reason=None` (NO `beat_extractor_unavailable`
  degrade). The shared revenge core surfaced as a pattern; judge scores 0.6–0.8 all passed the 0.60 gate.
- **Cleaned up** — the 4 seeded projects + their `:Event` nodes removed from the shared test account;
  the mined draft motifs deleted; throwaway smoke/seed scripts removed from both containers.

This proves the W8 cross-service seam the unit tests could only mock (the `mined:0` degrade path is
unit-proven; the LIVE mine needed the route + corpus + LLM, now all real). `D-W8-MOTIF-BEAT-EXTRACTOR`
was already built @73004c33; this is its end-to-end validation.

---

## STATUS (2026-06-28 PM) — D-W9-WEBSEARCH BUILT + LIVE-SMOKE PASSING (real searxng)

**`D-W9-WEBSEARCH`** ✅ BUILT — the import/deconstruct `use_web` augment is now real, not a
prompt stub. New `app/clients/web_search_client.py` (singleton, mirrors `embedding_client`):
`POST {provider-registry}/internal/web-search?user_id=` (X-Internal-Token) → the user's BYOK
`web_search` credential, resolved server-side (provider-gateway invariant — NO search SDK/key in
composition). INV-6: every title/url/snippet is neutralized (control/ws collapsed, capped) and
**non-http(s) URLs dropped**. Wired into `deconstruct_reference`: when `use_web`, ONE search runs
up front for the work's PUBLIC arc conventions; the neutralized block is injected on chunk 0 as
untrusted DATA (§12.6 output scrub remains the copyright backstop). Degrades honestly via
`websearch_status` (`off|no_client|not_configured|unavailable|no_results|ok:N`) — a web outage or
a missing credential NEVER fails the import. **+13 tests** (`test_web_search_client.py` 8 incl.
404→not_configured / non-http drop / transport-degrade; deconstruct web path 5). **Full unit suite
975 passed, 0 fail** (was 962). Provider-gate clean.
**LIVE-SMOKE** ✅ `D-W9-WEBSEARCH-LIVE-SMOKE` — real searxng (`019eeb08-3819-…`) via
provider-registry returned **5 neutralized http hits**; the deconstruct augment fired end-to-end
(`websearch_status=ok:5`, 3 motifs). model_source=`user_model`.

---

## STATUS (2026-06-28) — WAVE 2 COMPLETE + 8 DEFERS CLEARED + 4 LIVE-SMOKES PASSING + motif_beat extractor built

**LIVE-SMOKES (real stack — container REBUILT from this branch; lm_studio + provider-registry):** the
test account's models drive 4 passing end-to-end smokes (scripts in scratchpad, evidence below):
- **`D-W9-DECONSTRUCT-LIVE-SMOKE`** ✅ — Qwen2.5 deconstructed a revenge-cultivation text → 2 abstract
  motifs + arc (source='imported', imported_derived=True, B-3 taint). model_source=`user_model`.
- **`D-WSTITCH-LIVE-SMOKE`** ✅ — real stitch DEDUPED a deliberate cross-scene seam echo ("breath
  clouding in the dark / sealed letter" → rewritten) while preserving content — W-STITCH on a real model.
- **`D-MOTIF-RETRIEVE-LIVE-SMOKE`** ✅ — real bge-m3 (1024-dim) embed + cosine **0.638**, degraded=False
  (real cosine path). model_source=`user_model`, ref=bge-m3 local.
- **`D-MOTIF-CONFORMANCE-LIVE-SMOKE`** ✅ — the binary judge discriminated realized (True/True) vs
  not-realized (False/False) passages via Qwen2.5.
- **Model refs (test account `019d5e3c-…`):** chat `019eb620-…` (Qwen2.5 7B), embed `019e7f71-…`
  (bge-m3 local), web_search `019eeb08-3819-…` (searxng). Container `infra-composition-service-1` rebuilt
  `--no-cache` + force-recreated → migrations applied (adopted_base col + arc publish-strip trigger live).

**`D-W8-MOTIF-BEAT-EXTRACTOR`** ✅ built `73004c33` (knowledge-service) — `POST /internal/extraction/motif-beats`
(Option A: derives beat sequences from existing `:Event` nodes ordered by `event_order`, no new LLM call;
matches the frozen `knowledge_client.get_motif_beat_sequences` contract). 23 + 57 tests. **NEXT for mine:**
rebuild knowledge-service to deploy the route + seed a `:Event` corpus for the test account, then run
`D-W8-MINE-LIVE-SMOKE` (the pipeline + degrade are unit-proven; the real mine needs that corpus).

**Defer-clearing pass (2026-06-28) — 8 code-only defers cleared + DB-verified on real Postgres:**
- **`D-W9-ARC-PUBLISH-STRIP`** `8577c17b` — arc_template B-3 parity: `imported_derived` column +
  publish-strip trigger (opaque-ize source_ref on imported/derived publish) + clone taint
  propagation. DB-verified (`test_arc_publish_strip_trigger`).
- **`D-MOTIF-MCP-BIND-WIRING`** `ce7b0e42` — composition_motif_bind/_unbind now call W2's
  apply_motif_swap/undo_motif_swap (no more `pending_bind_wiring` degrade); 3 real tests.
- **`D-W9-IMPORT-LANGUAGE-ARG`** `ce7b0e42` — `composition_arc_import_analyze` gains `language`,
  stamped envelope→arc+motifs (R1.1.3 re-key risk closed).
- **`D-MOTIF-FE-CATALOG-ENDPOINT`** `e51d7a52` — catalog tab uses `motifApi.catalog` (the B-3
  allow-list), not `list({scope:'public'})`; the wrong `CatalogMotif` FE type fixed to the real
  `_CATALOG_COLS`. tsc clean, 56+585 FE tests.
- **`D-WAVE2-DB-ROUNDTRIP-TEST`** `12a9728c` — real-Postgres mined/imported create-column round-trip
  (the serially-edited 23-col INSERT) + arc `list_for_caller` every-scope (the scope=system 500 class).
- **`D-MOTIF-SYNC-REPIN-ATOMICITY`** `045e6d40` — the source_version re-pin rides the SAME patch
  UPDATE (`repin_source_version=`) → no partial-write window.
- **`D-MOTIF-SYNC-3WAY-BASE`** `83388add` — TRUE 3-way merge: `adopted_base` JSONB snapshot captured
  at clone time → diff reports base/ours/theirs + conflict; re-baselined atomically on apply. Pre-feature
  clones degrade to honest 2-way. DB-verified.

- **`D-W2-MCP-SESSION-ISOLATION`** `d1888a2a`+`3376021a` — FULLY CLEARED. Two root causes: (1) the MCP
  confirm-route fixtures patched `app.db.pool.create_pool` but not the SEPARATE `app.main.create_pool`
  binding → the lifespan hit the real DB host (getaddrinfo) in a batch; (2) FastMCP
  `StreamableHTTPSessionManager.run()` is once-per-instance and app.main's lifespan runs it, so every
  `TestClient(app.main)` consumed the global manager → test_mcp_server's loopback then failed. Fixed both:
  patched the app.main.* bindings in the fixtures + an autouse conftest fixture that stubs ONLY
  `app.main.mcp_server` (test_mcp_server uses build_mcp_app's separate binding, stays real).
  **VERIFY: full unit suite 962 passed, 0 errors in ONE batch run** (was 916 + 18 errors). The Wave-1 flake is gone.

**Kept deferred (consciously, with cause):**
- **`D-MOTIF-FE-PLANNERVIEW-WIRING`** — RECLASSIFIED (was "1-line wiring"; the FE agent found it's a
  cross-layer FEATURE): the FE preview types carry no per-scene `motif`/`BoundMotif` field, the
  `MotifBindingCard` is per-scene but the preview is per-chapter, and `outline_node_id` exists only
  post-commit. Needs a FE contract change (add `motif` to `PlannerChapterPreview`) + chapter-vs-scene
  binding decision — gate-2, a real feature not a wiring.

---

## (historical) STATUS (2026-06-27 PM) — WAVE 2 BACKEND COMPLETE · all 6 WS landed · only LLM/FE live-smoke deferred

**Wave-2 foundation + Batch A are built, verified, committed on `feat/narrative-pattern-library`:**
- **W2-F0 worker-seam freeze** `1330b1b4` — the three Tier-W motif ops (`mine_motifs`/
  `analyze_reference`/`conformance_run`) already enqueue via the confirm effects
  (`routers/actions.py`); the gap was the worker handler. Froze the 3-way collision zone
  (`worker/constants.py` + `worker/job_consumer.py`) once: each op dispatches to a WS-owned
  stub engine module (`engine/motif_mine.py` W8 · `motif_deconstruct.py` W9 ·
  `motif_conformance_run.py` W5-wiring) with frozen signatures + input envelopes; stubs raise
  a terminal `ValueError` until filled. All Wave-2 config knobs pre-added. Freeze test +
  `Wave2-RECONCILE.md`. (23 green.)
- **W-STITCH** `94bc3aeb` (§17.2 R2.7) — seam repetition signal + overlapping-window +
  dial-respect + ≤2-scene over-resolve fix + no-flatten eval-gate on `engine/stitch.py`. (43 green.)
- **W11 sync** `6485017e` — `routers/motif_sync.py`: upstream-diff + apply-merge. HONEST
  **2-way** (not 3-way): the motif table keeps only the current row (no history), so the
  pinned-version base text is unrecoverable → `diff_mode="two_way"`, never a fabricated base.
  Owner-scoped patch + re-pin (H13). (42 green; 1074 collected.)

**⚠️ WORKTREE-BASE HAZARD (lesson — carry forward):** `isolation:"worktree"` agents in this
repo intermittently branch off the **concurrent `feat/composition-debt` track HEAD `0cc8ff6c`**
(merged PR #47), which **predates the entire motif library** (no `motif_repo.py`, no motif
schema, no W2-F0 seam) — NOT off `feat/narrative-pattern-library`. A branch-merge would drag the
whole other track in. **Mitigation in force:** build Wave-2 WSs with **non-isolated agents in the
main tree** (correct base, commit directly); if a worktree must be used, add a **base-guard**
(assert `motif_repo.py` + `mine_motifs` seam exist, else STOP) and reconcile by **cherry-picking
the WS's own commit**, never merging its branch.

**W10 arc — BACKEND LANDED** (`feat/narrative-pattern-library`): `db/repositories/arc_template_repo.py`
(CRUD + clone/adopt + `list_public` allow-list + `count_shared_by_owner`, mirrors `motif_repo`
verbatim — same 2-tier read predicate, same conditional-param binding that does NOT bind an unused
`$1` for scope=system/public, optimistic-lock patch), `routers/arc.py` (`/v1/composition/arc-templates`
list/catalog/get/create/patch/archive/adopt **+ `apply`-preview**), `engine/arc_apply.py` (PURE
deterministic apply: R2.5 proportional placement-rescale into [1..target] with endpoints anchored +
arc_roster bound ONCE → propagated to every placement + a §12.6 drop/merge report that is NEVER
silent), `deps.get_arc_template_repo()`, `main.py` +1 include, models `ArcTemplateCreateArgs`/
`ArcTemplatePatchArgs`/`ArcThread`/`ArcRosterEntry`/`ArcApplyArgs`/`ArcApplyPlan`/`ResolvedPlacement`/
`DropMergeEntry`. Tests: `tests/unit/test_arc_template_repo.py` (18) + `test_arc_apply.py` (16) = 34
green; 1108 collected; provider-gate clean. NO migration (arc_template F0-frozen). NO LLM/DB in apply.

**W9 import — BACKEND LANDED** `08895083`: `db/repositories/import_source_repo.py` (per-user CRUD,
no public path §12.6), `routers/import_source.py` (NOT `import.py` — `import` is a keyword; owner-scoped
HTTP CRUD, H13 404), filled `engine/motif_deconstruct.py` `run_analyze_reference` (chunk → LLM-direct
abstract deconstruct MAP → reduce → §12.6 `scrub_verbatim` POST-CHECK → arc_template `source='imported'`
+ motifs `source='imported',imported_derived=True`), `deps.get_import_source_repo`, config knobs.
**Load-bearing test proves a verbatim source passage does NOT survive** into beats/summary/examples.
Additive: `motif_repo.create`/`arc_template_repo.create` gained `source`/`imported_derived`/`status`
kwargs (all defaulted → existing callers unchanged). 25 green; 1133 collected; provider-gate clean.

**W8 mine — BACKEND LANDED** `cc3dee40`: filled `engine/motif_mine.py` `run_mine_motifs` (PrefixSpan
frequent-sequential miner over `event_order` beat sequences → LLM abstraction → binary judge →
`MotifRepo.create(source='mined',status='draft',judge_score,mining_support)`), `knowledge_client.get_motif_beat_sequences`
(thin cross-service wrapper; server route deferred). **No-silent-drop (§11):** result lists EVERY
candidate with `judge_score`+`passed_gate`; below-gate shown not persisted. Degrades cleanly
(`mined:0, reason:'beat_extractor_unavailable'`) until the extractor ships. Additive: `motif_repo.create`
gained `judge_score`/`mining_support` (defaulted; coexists with W9's additive set). 11 green; 1144 collected;
motif_router 23 (no regression); worker-seam 5 (stub test updated to W8's real terminal-fail contract).

**▶ NEXT — only deferred slices remain (no new WS): the R-NODE-P3/P4 LLM+cross-service live-smoke**
(W8 mine→draft→promote→reuse · W9 deconstruct→arc_template · W5 conformance extract-diff), the
knowledge-service `motif_beat` extractor (W8 server piece), and the FE slices (W10 arc-timeline,
the W6 catalog-endpoint fix). All need an lm_studio + platform-embedding-credential stack-up
(mirrors the R-NODE-P1 LLM-slice deferral). See the full deferred ledger below.

**Deferred — W10 (NEW, gate-passing):**
- ~~**`D-W10-FE-TIMELINE`**~~ ✅ **CLEARED PM-10** — the FE thread×chapter arc-timeline subtree
  (editor + apply-preview, built against the frozen `ArcTimelineContract` + `ArcApplyPlan`), surfaced
  via the motif-panel `Motifs | Arc templates` kind-toggle. 43 tests, live contract smoke. See PM-10.
- ~~**`D-W10-FE-PLACE-MOTIF-PICKER`**~~ ✅ **CLEARED PM-13** — both surfaces' "+ place" now open a motif
  picker (`SwapMotifPopover` + `useMotifCandidates`) and place a real motif (code+id+name); no candidates
  ⇒ no place affordance. The empty-`—`-stub path is gone. See PM-13.
- ~~**`D-W10-APPLY-PLANNER-MATERIALIZE`**~~ ✅ **CLEARED PM-11** — `POST …/works/{id}/arc/materialize`
  turns the rescaled placements into a committed arc→chapter→scene outline + a `motif_application`
  ledger, DETERMINISTICALLY (no LLM — `scenes_from_motif`). 15 tests + a live cross-service smoke
  (book+work+arc → 8 scenes/8 ledger rows, read back via motif-bindings). See PM-11.
- **`D-W10-ARC-CONFORMANCE`** (gate 3 naturally-next · target P4 with W5 arc-diff): coarse
  arc-conformance (thread-progress / pacing / succession diff of realized arc vs template, §14.4 altitude 3)
  depends on the import/extract path (W9) + W5's deferred arc-diff dimension — implementable only once
  those land. Master-plan §5 W10 lists it; not in the backend-CRUD/apply slice.

**Deferred — W9 (NEW, gate-passing):**
- **`D-W9-DECONSTRUCT-LIVE-SMOKE`** (gate 4 blocked-on-infra · target R-NODE-P4): real end-to-end
  import→LLM-deconstruct→arc_template+motifs on a stack-up (needs lm_studio).
- **`D-W9-DECONSTRUCT-DEEP-RAIL`** (gate 2 large/structural · target P4): this slice does a single
  LLM-direct deconstruct over chunked text; the deep §12.4 rail (the 5th `motif_beat` map-extractor +
  semantic arc segmentation) is the harder cross-service piece — shared with `D-W8-MOTIF-BEAT-EXTRACTOR`.
- **`D-W9-WEBSEARCH`** (gate 1 out-of-scope · target P4): `use_web` is a prompt flag stub
  (`websearch_status:"deferred:D-W9-WEBSEARCH"`); the real web-search arc-boundary augment is unbuilt.

**Deferred — W8 (NEW, gate-passing):**
- **`D-W8-MOTIF-BEAT-EXTRACTOR`** (gate 2 large/structural, cross-service · target P3): the
  knowledge-service SERVER `motif_beat` extractor — a 5th map-extractor in `loreweave_extraction`
  (§12.4) keyed by `motif_mine_extractor_version` (`motif_beat@v1`). CONTRACT (frozen on
  `KnowledgeClient.get_motif_beat_sequences`): `POST /internal/extraction/motif-beats` (X-Internal-Token),
  `{user_id, book_id|corpus, language?, extractor_version}` → `{sequences:[[{beat,thread,tension,role_mentions},…],…]}`
  ordered by `event_order`. The composition-side mining path is fully wired against it (degrades to
  `mined:0` until it lands). Needs the running service + corpus + LLM.
- **`D-W8-MINE-LIVE-SMOKE`** (gate 4 blocked-on-infra · target R-NODE-P3): real mine→draft→promote→reuse;
  needs the extractor above + lm_studio + the platform embedding credential.

**Deferred — /review-impl (2026-06-27, 3 adversarial reviewers; HIGH + fix-now MEDs already FIXED @ `e35510d1`):**
- **`D-W9-ARC-PUBLISH-STRIP`** (gate 2 schema-migration · defense-in-depth): the §12.6 leak HIGH was
  fixed by extending the scrub to every persisted field (incl. arc envelope) — but `arc_template`
  still has no `imported_derived` column + no publish-strip trigger (motif has both). Add them so an
  imported arc gets the same DB-level belt-and-suspenders the motif gets, not scrub-only.
- **`D-W9-IMPORT-LANGUAGE-ARG`** (gate 1 small-UX): the deconstruct now THREADS `language` end-to-end
  (envelope→arc+motifs), but the PRODUCER (the `composition_arc_import_analyze` MCP tool arg + the
  `_execute_arc_import` confirm spec) doesn't yet capture the user's source language, so it defaults
  'en'. Add the tool arg + stamp it (the plumbing is ready).
- **`D-WAVE2-DB-ROUNDTRIP-TEST`** (gate 1 coverage): the serially-edited `motif_repo.create` (W9+W8
  additive cols) + `ArcTemplateRepo`/`ImportSourceRepo` have NO DB-backed test — a future column
  misalignment or the `scope=system` placeholder bug (R-NODE-P1 class) would stay green. Add a
  Postgres round-trip for the mined/imported columns + an arc `list_for_caller` every-scope test
  (mirror the motif one). Needs infra-postgres.
- **`D-MOTIF-SYNC-REPIN-ATOMICITY`** (gate 5 accept/document): W11 sync's patch + source_version
  re-pin are two statements/connections — a crash between leaves version bumped + source_version
  stale (self-heals on the next diff; not corruption). Wrap in one txn if it ever bites.
- Accept+document (no row): HIGH-2 short-phrase/lone-proper-noun residue (the scrub is long-run-only
  by design; residue held by the abstraction prompt + role-slot model per §12.6 — now stated honestly
  in the `scrub_verbatim` docstring); L1 mine `promote_to` stamped-but-unused; L2 mine synthetic
  `project_id`; L8 deconstruct tension-range.

Carried: `D-MOTIF-SYNC-3WAY-BASE` (W11 schema), `D-WSTITCH-LIVE-SMOKE`. Plus the Wave-1 carries
(`D-MOTIF-MCP-BIND-WIRING`, `D-MOTIF-CONFORMANCE-ENGINE-WIRING`, `D-MOTIF-FE-PLANNERVIEW-WIRING`,
`D-MOTIF-FE-CATALOG-ENDPOINT`, `D-W2-MCP-SESSION-ISOLATION` test-infra flake, the W7/conformance PO items).

---

## (historical) STATUS (2026-06-27 AM) — WAVE 1 BUILT + MERGED + RECONCILED · Wave 2 is next

**All 7 Wave-1 workstreams (W1–W7) built in parallel worktrees, merged into
`feat/narrative-pattern-library`, and reconciled.** Merge was clean (only `main.py`
touched by 2 branches — W1+W5 router includes, union-resolved). Merged-branch VERIFY:
**843 unit + 130 DB-integration + contracts green**; the 26 MCP-loopback errors are the
pre-existing `StreamableHTTPSessionManager` test-infra flake (69 pass in isolation),
tracked as `D-W2-MCP-SESSION-ISOLATION`. Provider-gate clean.

**Per-WS commits (pre-merge):** W1 `420b82a0` · W2 `6a7e456d` · W3 `402ade85` ·
W4 `c8b06df4` · W5 `73674b49` · W6 `5d66136d` · W7 `210f4305`. Merged via 7 merge
commits + the reconcile commit on `feat/narrative-pattern-library`.

**Reconcile actions taken:**
- F0 additive follow-ups applied (deps/config were frozen during the wave): `deps.py`
  `get_motif_application_repo()` (W2/W5 need it); `config.py` `motif_connective_floor_margin=0.08` (W2 MD-3).
- W2↔W5 seams verified CLEAN: W2 writes `beat_key` into `motif_application.annotations`
  (W5 reads `annotations->>'beat_key'`); W2 never touches `generation_job.critic` (no clobber).
- W1↔W3 seam CLEAN: adopt copies the vector + `embedded_summary_hash` (no re-embed).
- W1↔W6 library CRUD paths MATCH (`/v1/composition/motifs*`); W6 adopt/conformance use the
  Tier-W `/actions/{op}/estimate|confirm` flow (adopt=Tier-W per RECONCILE §3).

**Deferred — Wave-1 reconcile seams (NEW; fix in a focused follow-up or Wave 2):**
- **`D-MOTIF-MCP-BIND-WIRING`** (gate #2 structural): W4's MCP `composition_motif_bind`/
  `_unbind` were authored against a `bind_motif(...)→dict` / application_id-undo contract;
  W2's engine landed exposing `apply_motif_swap`/`undo_motif_swap` (token-based undo). The
  tools now VALIDATE (work/gate/IDOR) then degrade cleanly (`reason: pending_bind_wiring`)
  pointing at the working HTTP twin. Reconcile the response-shape + undo model (token vs
  application_id) + rewrite the 2 bind tests. **HTTP bind/swap + planner auto-bind work now.**
- **`D-MOTIF-CONFORMANCE-ENGINE-WIRING`** (gate #3 naturally-next): W5's `judge_motif_conformance`
  functions exist + are unit-tested; the `engine.py` producer call-site is unwired. Conformance
  is advisory + OFF by default + uncalibrated, so it's intentionally dormant — wire when it
  graduates (needs `D-MOTIF-CONFORMANCE-GOLD-SET` first). The trace READ endpoint works.
- **`D-MOTIF-FE-PLANNERVIEW-WIRING`** (gate #3): W6 ships `useMotifBinding`+`MotifBindingCard`;
  the 1-line `selectTab`/`setSceneId` wiring in `PlannerView.tsx` (W2's FE seam) is unwired.
  The W6 dock panel provides the motif UI; this is the inline-in-planner enhancement (H-8 path).
- **`D-MOTIF-FE-CATALOG-ENDPOINT`** (HIGH, gate #2 — found by /review-impl): the W6 library's
  `catalog` tab calls `motifApi.list({scope:'public'})` → `GET /motifs`, which (a) 422s (the router
  accepts only `mine|system|all`) and (b) would BYPASS the B-3 allow-list (`list_for_caller` returns
  full rows). The catalog tab must call `motifApi.catalog` (`GET /motifs/catalog` = `list_public`,
  the `_CATALOG_COLS` allow-list) and the hook must handle the `CatalogMotif` shape (the tier facet
  reads `owner_user_id`/`visibility`, which the allow-list omits). Fix in the FE-integration pass
  (`D-MOTIF-FE-LIVE-SMOKE`). The companion `limit: 200 → 100` 422 (every list call) was fixed in-commit.
  NOTE: W7 seed packs now live in `app/db/seed_motif_packs/` (not `scripts/`); the W7 design doc's
  path refs are stale — code + this handoff are authoritative.

**Deferred — WS-reported (carried; many target R-NODE-P1):** `D-MOTIF-RETRIEVE-LIVE-SMOKE`,
`D-MOTIF-PGVECTOR-TRIGGER` (perf, ceiling=500), `D-W4-MINE-WORKER-LIVE-SMOKE` (Wave-2 compute),
`D-MOTIF-CONFORMANCE-GOLD-SET` (PO ~25-scene labeling), `D-MOTIF-CONFORMANCE-LIVE-SMOKE`,
`D-MOTIF-FE-LIVE-SMOKE`, `D-W7-VI-PACK` (vi seed packs — additive data), `D-W7-PO-REVIEW`
(genre-faithfulness sign-off), plus W5's P2/P4 scope-fenced dims (arc-diff, fine-anchor,
plot-density, act-rate).

**R-NODE-P1 — VERIFIED (data plane + live HTTP) ✅.** Two layers proven:
1. **Data plane** (committed guard `tests/integration/db/test_rnode_p1_dataplane.py`): all 7 WSs'
   code against a real seeded DB — W7 seeds (44/19) → W1 create → W3 retrieve (R4 degrade) → W2
   motif_application (beat_key in annotations) → W5 trace → W2 anti-repetition.
2. **Live HTTP** (composition-service REBUILT from this branch, ran against shared `loreweave_composition`):
   - W1 surface: `GET /motifs?scope=system` (44 seeds), create/get, `/motifs/catalog` (B-3 allow-list,
     no leaked examples/embedding/source_ref), `POST /motifs/{seed}/adopt` (clone, lineage set).
   - W2 bind: `PATCH .../outline/{node}/motif` → derived scenes + motif_application written + undo_token.
   - W5 trace: `GET .../conformance?scope=chapter` → references the bound motif.

**R-NODE-P1 caught 3 real DEPLOYMENT/RUNTIME bugs the 843+130 tests could NOT (all fixed + committed):**
- **Container boot crash** — W7 seed JSON lived in `scripts/` but the prod Dockerfile COPYs only
  `app/`; moved the packs into `app/db/seed_motif_packs/` (commit on branch).
- **HIGH: `GET /motifs?scope=system` 500** — `list_for_caller` bound `caller_id` as an UNUSED `$1`
  for system/public scopes → asyncpg `IndeterminateDatatypeError`; the default `all` scope masked it
  in every test. Fixed + a real-DB regression test over all scopes (`87004a8d`).
- **Stale-image gotcha** — a normal `docker compose build` reused a cached pre-Wave-1 image; needed
  `build --no-cache` + `up -d --force-recreate`. NB: this is a SHARED env — another track can recreate
  `infra-composition-service` from cache; re-`--no-cache` if `/openapi.json` lacks `/v1/composition/motifs`.

**▶ NEXT — only the LLM/semantic slice of R-NODE-P1 remains (optional, not a blocker):** real
LLM-decompose auto-bind (needs lm_studio up) + W3 semantic cosine (needs `motif_embed_model_ref`/
`_owner_id` → a provider-registry embedding credential, e.g. bge-m3) + the W4 MCP envelope path + W6 FE.
The data flow they exercise is already proven via the swap-bind path. **Wave 2 is unblocked:**
W8 mine · W9 import · W10 arc · W-STITCH · W11 sync. The `ws/w*` refs remain as per-WS history pointers.

---

## (historical) STATUS (2026-06-26) — F0 BUILD COMPLETE + FROZEN · Wave 1 is next

**F0 is built, verified, and committed.** The shared contract is frozen. Wave 1
(W1–W7) may now fan out in worktrees (disjoint per `00-RECONCILE §4`).

**F0 delivered** (`services/composition-service`): `db/migrate.py` (5 tables —
`motif`/`motif_link`/`motif_application`/`arc_template`/`import_source` — + `consumed_tokens`,
2×2 tenancy partials, the `motif_user_owned` CHECK, and 3 triggers: cycle/same-tier,
cross-project scope, publish-strip); `db/models.py` (row + `ForbidExtra` arg models);
`db/repositories/motif_repo.py` (CRUD + the real `clone`); `db/repositories/motif_retrieve.py`
(frozen stub, W3 impls); `config.py` + `deps.py`; `tests/contracts/` + `tests/integration/db/test_motif_migrate.py` + `test_motif_repo.py`.

**6 reconcile deltas folded:** D1 `motif.annotations`; D2 `motif_embed_owner_id` +
`motif_candidate_ceiling`; D3 `consumed_tokens` + `usage_billing_service_url`; D4 seeds
embed NULL (retriever tolerates NULL); D5 no-extension lineage (`'lineage:'||id`); D6
system seeds `unlisted`.

**`/review-impl` ran on F0 — 4 findings, all fixed in-commit (none deferred):**
- #1 no write-method behavior tests → added `test_motif_repo.py` (create/patch/archive/clone).
- #2 `clone` NULLed `embedded_summary_hash`, forcing W3 to redundantly re-embed → now copies it.
- #3 **B-3 bypass**: publish-strip keyed on `source='imported'` only, so an *adopted* clone
  of an imported motif would leak source passages on publish — matched W1 §1's documented
  expectation of `('imported','adopted'-from-imported)`. **Fixed** with an `imported_derived`
  lineage-taint column that `clone()` propagates and the trigger checks (adopted-from-AUTHORED
  stays false, so the strip is not over-broad). **W1's publish test should assert this path.**
- #4 foreign-`unlisted` IDOR not covered → added to the behavior test.

**Frozen-contract note for Wave 1:** the `Motif` model + `motif` table now carry
`imported_derived BOOLEAN` (B-3 taint) and `annotations JSONB` (D1) — additive; consume them,
do not re-add. `MotifRepo.patch` returns `Motif | None` (None = not-found/not-owned) and raises
`VersionMismatchError` on stale version (house convention).

**VERIFY:** `27 passed` on a throwaway DB (`infra-postgres-1`, PG18) — existing migrate (3, no
regression) + motif migrate risk-guards (6) + motif repo behavior (10) + contracts (8). Guards
green: B-1/B-2/B-3/H-2/H-5/N-1 + `get_visible` IDOR.

---

Paste the block below into the new session. Design+plan phase is COMPLETE + committed; next is BUILD (F0 first).

---

```
Continue the Narrative Motif Library build on branch `feat/narrative-pattern-library`
(repo d:\Works\source\lore-weave-mcp-fanout). The DESIGN + PLAN phase is COMPLETE and
committed (HEAD ~f4458bda, 6 motif-library commits). Nothing is built yet — the next
step is BUILD, starting with F0.

READ FIRST (in order; do NOT re-litigate locked decisions):
- Spec §R1 + §R2 (locked decisions + resolutions): docs/specs/2026-06-26-narrative-motif-library.md
- Master plan (parallel structure + DAG): docs/plans/2026-06-26-motif-library-master-plan.md
- Reconciliation (the 6 F0 contract deltas to fold + the cross-WS seams):
  docs/plans/2026-06-26-motif-library-ws/00-RECONCILE.md
- F0 detailed design: docs/plans/2026-06-26-motif-library-ws/F0-foundation.md
  (and W1-W7 *.md in that folder for the workstreams)

LOCKED (do not reopen): 2-tier + clone-to-customize (NO book tier; motif.book_id removed;
per-book customization = clone into a user-variant); ONE platform embedding model for all
motif vectors; `language` axis on motif (P1); motif_application per-book/project scope.
CORRECTIONS already folded: the flywheel causal-event graph does NOT exist (mining = scalar
event_order + a new motif_beat extractor, drop subgraph mining); STITCH already ships
(engine/stitch.py — §17 is a delta, not new); "the calibrated judge" scores extraction not
narrative (motif_conformance is binary-first, advisory, needs its own small gold set).

NEXT ACTION — BUILD F0 (serial; lands first, then FROZEN as the shared contract):
1. Fold the 6 deltas from 00-RECONCILE §1 into F0: D1 add motif.annotations JSONB; D2
   config motif_embed_model + motif_embed_owner_id; D3 consumed_tokens table + billing
   precheck; D4 seeds embed NULL + W3 lazy back-fill (retriever tolerates NULL-embedding);
   D5 no-extension lineage default ('lineage:'||id); D6 system seeds visibility='unlisted'.
2. Build F0 per F0-foundation.md: db/migrate.py (5 tables motif/motif_link/motif_application/
   arc_template/import_source + the cycle/same-tier/cross-project/publish-strip triggers),
   db/models.py (Pydantic + ForbidExtra), db/repositories/motif_repo.py (CRUD + clone),
   db/repositories/motif_retrieve.py (stub), config.py, deps.py, tests/contracts/.
3. VERIFY on a throwaway DB: migration idempotent; the 2 tenancy partials + motif_user_owned
   CHECK reject a both-NULL private insert; get_visible IDOR test (system/public/owner
   returned, another user's private NOT). This is F0's risk-boundary checkpoint + commit.
4. F0 is then the FROZEN contract → fan out Wave 1 (W1 W2 W3 W4 W5 W6 W7), each in its own
   git worktree (files are provably disjoint per 00-RECONCILE §4 → parallel-safe), each per
   its W*.md detailed design.
5. R-NODE-P1 live-smoke (create a user motif → seed pack present → decompose a chapter that
   binds a seed motif → motif_application written + match_reason → conformance trace), then
   Wave 2 (W8 mine · W9 import · W10 arc · W-STITCH · W11 sync).

WORKFLOW: this is XL; F0 is the first milestone. Run the loom/v2.2 gates per workstream
(VERIFY evidence, 2-stage review, live-smoke ≥2 services). Use worktrees for Wave-1
parallelism. Every audit blocker is a failing-test-first guard inside its WS doc — write the
RED test first.

PO RESIDUAL (does NOT block F0/Wave-1): label ~25 scenes for motif_conformance calibration
(per W5-conformance.md) OR ship conformance as pure-advisory and label later.

CONSTRAINTS: stage only the exact files you changed (NEVER git add -A — shared-tree hazard);
do NOT touch docs/sessions/SESSION_HANDOFF.md (it belongs to the concurrent
feat/composition-service track). Provider-gateway invariant (every LLM/embed/rerank call via
provider-registry) + MCP-first invariant (agentic logic as MCP tools) apply.

START: read the docs above, fold the 6 F0 deltas, then build F0 (schema → models → repo →
config → contract tests → VERIFY), and stop at the F0 checkpoint for review before Wave 1.
```

---

**Quick map of what's committed on this branch (design+plan, all docs):**
- `docs/research/2026-06-26-narrative-control-formalisms.md` · `…-motif-prompt-control-poc.md` (5 POCs)
- `docs/specs/2026-06-26-narrative-motif-library.md` (§R1/§R2 authoritative)
- `docs/reports/2026-06-26-motif-library-audit.md` (8 reviews)
- `docs/plans/2026-06-26-motif-library-master-plan.md`
- `docs/plans/2026-06-26-motif-library-ws/{00-RECONCILE, F0-foundation, W1…W7}.md`
- `design-drafts/motif-library/*.html` (8 mockups)
- POC scripts in scratchpad (throwaway, NOT committed).
