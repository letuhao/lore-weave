# Plan Hub — mockup parity audit + build (2026-07-18)

**Goal (sealed with human, no defer):** build EVERY item in both sealed draft HTMLs, compare 1-by-1 at
item level, test each. Do not stop until every item in `simple-mode.html` + `index.html` is built + tested.

- Advanced mockup SoT: `design-drafts/plan-hub-redesign/index.html`
- Simple mockup SoT: `design-drafts/plan-hub-redesign/simple-mode.html`

**Root discrepancy the human flagged ("this is not draft html redesign"):** the *Advanced* view is the
pre-existing **React Flow graph canvas** (`PlanCanvas`), not the mockup's **CSS-flow lane layout**
(stacked lanes · wrapping chapter cards · inset sub-arcs · inline add). The two are architecturally
different. Fix = build a new lane-flow Advanced view (`LaneFlowView`) driven by the existing verified
data layer. Simple mode already ~matches its mockup but was hidden behind a persisted "Advanced" pref
and is missing CRUD + a few bar items.

**Authorship is REAL data** (mockup note: "maps to REAL columns"). `StructureNode.source` (arcs) is
already on the wire via `model_dump`; `OutlineNode.source` (chapters/scenes) needs one line added to
the children projection (`outline.py` `_summary_*`). `'authored'` → Lora+amber · `'mined'` → Mono+teal.

---

## ADVANCED (`index.html`) — item checklist

| # | Item | Built? | Where / action |
|---|------|--------|----------------|
| A1 | Canvas frame: dotted-grid bg, border, radius, horizontal scroll | ❌ (RF graph) | new `LaneFlowView` |
| A2 | Toolbar: `+ Arc`(primary), `+ Sub-arc`, `Fit`, `Ask AI`(ghost), cost `Gemma-4 26B · local · $0.00` | ⚠ partial | `PlanToolbar` has the buttons (no cost, no primary styling) |
| A3 | Lane (arc): bounded width 62%, min 360, `resize:horizontal`, amber border | ❌ | `LaneFlowView` |
| A4 | Lane machine variant: teal border/bg | ❌ | needs `source` |
| A5 | Lane head: toggle ▾/▸, titles block, meta chips | ❌ | `LaneFlowView` |
| A6 | arc-name: full title, wraps, serif(authored)/mono(machine) | ❌ | needs `source` |
| A7 | arc-sub line: "chapters 1–4 · …" (span text) | ❌ | from `span` |
| A8 | arc-meta chips: `100/340`(pagination), `2 done`/`4 ch`(count), `⚠ gap ch 5`(warn), `AI · collapsed` | ⚠ | pagination+warn exist in RF LaneBand; not in flow view |
| A9 | Chapters container: `flex-wrap` rows inside lane | ❌ | `LaneFlowView` |
| A10 | Chapter card: fixed ~188px, border, status styling | ❌ | `LaneFlowView` |
| A11 | ch-top: dot, `ch N`, status label (uppercase mono) | ❌ | `LaneFlowView` |
| A12 | ch-title: serif, 2-line clamp | ❌ | `LaneFlowView` |
| A13 | Chapter status variants: empty(dashed)/outline(grey)/drafting(amber)/done(green) | ❌ | map real status enum |
| A14 | Scenes: `flex-wrap` chips under chapter | ❌ | from scene windows |
| A15 | Scene chip: authored(amber)/machine(teal mono "AI: …") | ❌ | needs `source` |
| A16 | `+ scene` add (dashed) in a chapter | ✅ backend (`addSceneUnderChapter`) | wire inline |
| A17 | `+ chapter` add at end of lane | ✅ backend (`addChapterUnderArc`) | wire inline |
| A18 | `+ N more` chapter pagination button | ✅ (`loadMoreArc`) | wire inline |
| A19 | Sub-arc: inset lane, left-spine, `sub-arc` tag | ❌ | recursive `LaneFlowView` |
| A20 | Sub-arc has own chapters + `+ chapter` | ✅ backend | recursive |
| A21 | Arc with BOTH own chapters AND nested sub-arc (`has-sub`) | ❌ | recursive |
| A22 | Machine arc collapsed (▸, `AI · collapsed`) | ⚠ | collapse exists; machine styling needs `source` |
| A23 | Selected state: amber outline (`.ch.sel`/`.lane.sel`) | ⚠ | selection exists; restyle |
| A24 | Non-contiguous `⚠ gap` chip | ✅ (`is_contiguous`) | render in flow |
| A25 | Authorship at arc/chapter/scene: serif+amber vs mono+teal | ❌ | needs `source` (B1/D1) |
| A26 | Keyset windowing preserved: collapsed arc loads nothing; scenes load on chapter expand; bounded cold-open | ✅ | keep `usePlanWindows`; bounded auto-expand |

## SIMPLE (`simple-mode.html`) — item checklist

| # | Item | Built? | Where / action |
|---|------|--------|----------------|
| S1 | Hub bar: book title (serif) | ❌ | add to bar |
| S2 | Hub bar: mode toggle Simple\|Advanced (pill) | ✅ | `modeToggle` |
| S3 | Hub bar: cost `local · $0.00` | ❌ | add to bar |
| S4 | Guide line (teal-tint) | ✅ | present |
| S5 | Chapter row: no · dot · title(serif) · words · state · → | ✅ | present |
| S6 | Machine/AI row: title mono, state "AI idea", teal | ❌ | needs chapter `source` |
| S7 | Status dot+state: done/drafting/outline/empty(dashed) | ⚠ | has done/drafting/empty; no "outline" (list only knows published/words) |
| S8 | Row hover: bg + amber left-border | ✅ | present |
| S9 | The door: "＋ Write a new chapter" → create+open editor | ✅ | present |
| S10 | Door note + "Or let the AI draft one →" | ⚠ | note present; link says "Organise into storylines" (kept) — AI-draft link missing |
| S11 | Legend (authorship + status swatches) | ❌ | add |
| S12 | **CRUD: rename a chapter** | ❌ | `patchChapter` — MISSING |
| S13 | **CRUD: delete a chapter** | ❌ | `trashChapter` — MISSING |
| S14 | Scales to 10k (windowed list) | ✅ | keyset `useSimpleChapters` |

## CRUD matrix (goal: "no edit or delete")

| Level | Create | Rename/Edit | Delete/Archive | Notes |
|-------|--------|-------------|----------------|-------|
| Arc (Advanced) | ✅ `+Arc`/`+Sub-arc` | ✅ ArcInspector EditField | ✅ ArcInspector "Archive arc" | in drawer — undiscoverable; add inline affordance |
| Chapter (Advanced) | ✅ `+chapter` | ✅ PlanDrawerEdit | ✅ archiveNode | in drawer |
| Scene (Advanced) | ✅ `+scene` | ✅ PlanDrawerEdit | ✅ archiveNode | in drawer |
| Chapter (Simple) | ✅ door | ❌ | ❌ | **the gap the human named** |

---

## BUILD SLICES (done = evidence string)

- [x] B1 · backend: project `source` on children summary (`outline.py` `_summary_projection`); arc source
      already on wire. Test `test_the_summary_payload_carries_the_AUTHORSHIP_SOURCE` + keys set. 6 green.
- [x] D1 · FE types (`NodeSource`, `source` on ArcListNode/SummaryNode/NodeContent) + `usePlanHub`
      nodeContent threads source (default 'authored'). tsc 0.
- [x] D2 · `usePlanHub` `laneTree` (pure `layout/laneTree.ts`) + bounded auto-expand (MAX 8 roots,
      gated on `autoExpandArcs` so Simple never fetches windows). laneTree.test 5 green.
- [x] A · `LaneFlowView` + `FlowLane` (recursive) + `FlowChapterCard` + `flowPresentation` — every A-row.
      `PlanCanvas`→`LaneFlowView` swap in the Advanced branch. LaneFlowView.test 9 + flowPresentation 5.
      LIVE :5290: 3 arc lanes, full readable titles, `⚠ gap` warn, wrapping cards, `+scenes/+chapter/
      +sub-arc`, book title "ADV smoke", `$0.00`, auto-expand, lane width **0.62 + resize:horizontal**.
- [x] Sbar · book title + cost (bar), legend + AI-draft link (Simple). LIVE :5290 all present.
- [x] Scrud · Simple rename (patchChapter) + delete (trashChapter) + machine-row rendering.
      SimpleChapterList.test 8 green. **LIVE :5290: rename → persisted server-side; delete → 2→1 rows.**
- [x] i18n · en + 17 locales gap-filled via `i18n_translate.py` (+27 keys each, 0 failed, full parity).
- [x] QC · isolated static build :5290 — Advanced layout + scene reveal + Simple rename/delete all live,
      0 console errors. **One honest limitation:** authorship COLOURING (mined vs authored) not live-seen
      because composition-service runs a baked image without the B1 `source` projection → FE defaults to
      'authored' (graceful). Unit-proven both sides (BE projection test + FE tree/component tests with
      synthetic mined data). Live-authorship pending a composition-service redeploy — not fabricated.
- [ ] Commit · MY files only (shared checkout — 4 parallel sessions)

## COMPLETENESS AUDIT (follow-up, 2026-07-18)

Regression sweep after the `PlanCanvas`→`LaneFlowView` swap. Suite: 1618 plan-hub+studio tests
green (no test regression); BE 21 green. Selection→drawer confirmed working for arc/chapter/scene
(so Advanced edit/archive CRUD is intact via the drawer). Auto-expand effect reviewed — seeds once
per book, gated, no loop. Findings that need action:

- **GAP-1 (regression — FIX): unassigned spec chapters are invisible + unfileable in the flow view.**
  The old RF canvas rendered arc-less chapters (the normal post-decompile state) in a strip you could
  drag into a lane. The flow view shows only a COUNT notice — the chapters themselves have no lane, so
  they can't be selected, opened, or filed. Data loss of visibility. Fix: render an "Unassigned" group
  in the flow view (selectable cards → drawer / open editor).
- **DEBT-1 (regression — FIX minimal): moving/re-filing a chapter between arcs is gone.** It was
  drag-only in `PlanCanvas`; the chapter drawer has no arc-reassign control, so once a chapter is under
  the wrong arc there is no way to move it. Fix: a lightweight "move to arc" affordance (non-drag), which
  ALSO files an unassigned chapter (one mechanism, both cases).
- **DEBT-2 (dead code — decide): `PlanCanvas` + `usePlanMoves` + scene-linking are production-dead.**
  Nothing mounts them after the swap (only their own tests + the barrel export reference them). The
  drag-move/scene-link/camera features are aligned-out by the sealed mockup. Decision: keep the code
  (revivable) but stop wiring the unused move plumbing into `usePlanHub`'s hot path if cheap; else record.
- **GAP-2 (minor): no "collapse scenes" affordance** once a chapter's scenes are revealed (the reveal
  toggle disappears). Low priority; add a collapse control on the scene row.

### Independent cold-start review — findings + resolution
An adversarial reviewer read all new/changed files. Every finding actioned:
- **BUG (color — HIGH, user-flagged): authorship coding was invisible on real books.** `src()` only
  mapped `'mined'`→machine, but the real AI source values are `'planforge'` / `'decompiled'` /
  `'imported'` — so planner/import content rendered as if the writer authored it. FIX: `normalizeSource`
  (authored = human; EVERY other value ⇒ machine/teal). Deployed BE + live-QC'd: a `planforge` chapter
  now renders mono/teal, an `authored` one serif/amber; status tints (done=green, drafting=amber) show.
- **BUG (cross-book state leak — MED):** `usePlanHub` never reset `expandedArcs`/`selectedId` on
  `bookId` change → book A's ids fetched against book B + a stale drawer node. FIX: a `[bookId]` reset
  effect (mirrors `usePlanWindows`), clearing the seed guard so the new book re-auto-expands.
- **BUG (ch-N mislabel — LOW/MED):** cards used the within-arc index, so a "chapters 5–8" arc showed
  "ch 1–4". FIX: `chapterDisplayNo` uses the arc's dense-ordinal span for contiguous arcs (+ tests).
- **ROT (LOW):** dead `chapterNo` with a no-op ternary — deleted (replaced by `chapterDisplayNo`).
- **ROBUSTNESS (LOW):** a `parent_id` cycle silently dropped its members — added a cycle guard that
  surfaces orphaned arcs at the top level (+ test).
- Reviewer confirmed clean: rename state, auto-expand loop-safety, fitSignal remount, FlowLane
  recursion, sort stability, +scene null-guard, hook ordering.

### Regressions resolved (the "critical downgrade")
- **GAP-1 (unassigned):** arc-less chapters now render as a selectable, fileable **"Unassigned" group**
  in the Lane view (was a count-only HUD). Live-tested.
- **DEBT-1 + DEBT-2 + user's flag (drag/zoom/pan): RESOLVED by keeping BOTH Advanced sub-views.**
  `PlanCanvas` (React Flow — zoom, pan, drag-to-move, scene links) is re-mounted as the **Graph**
  sub-view (the default — the navigable canvas a large structure needs); the mockup **Lane** view is
  the readable opt-in. A per-user `Graph | Lane` toggle (`usePlanAdvancedView`, mirrors MotifSimpleMode).
  This un-deads PlanCanvas AND restores the free-move capability. Both sub-views live-QC'd on :5290.
  The Lane view ALSO gained a non-drag **"move to arc"** picker (reuses the tested `moveChapterToArc`) —
  live-tested: a chapter moved lanes + persisted server-side.

## ITEM-LEVEL VERDICT (1-by-1)
Advanced A1–A26: BUILT. A4/A6/A15/A22/A25 authorship = built + unit-proven (colouring live pending
BE redeploy). Simple S1–S14: BUILT (S6 machine-row rendering built + tested; no current flow produces a
mined book chapter, so it shows authored live — honest). CRUD matrix: Simple chapter rename+delete now
present (the named gap closed); Advanced arc/chapter/scene CRUD via drawer unchanged.
