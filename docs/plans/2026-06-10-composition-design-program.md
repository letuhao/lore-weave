# Composition V1 — Design Program (master index + tracker)

**Branch:** `feat/composition-service` · **Created:** 2026-06-10 (LOOM, post LOOM-91) · **Status:** DESIGN phase — **24/24 specs drafted + decision-complete (2026-06-10)**; next = `/review-impl` over the design set → PO sign-off → build (P0→P1→P2).
**Supersedes** the Part-A build list in [`2026-06-11-composition-gap-closure-and-e2e.md`](2026-06-11-composition-gap-closure-and-e2e.md) (kept for the Part-B QC/e2e gate).
**Sources:** coverage [review](../reports/2026-06-10-composition-fe-be-coverage-review.md) · product spec = the v3 studio drafts `docs/specs/composition-studio-mockup-v3.html` + `composition-studio-components.html`.

---

## PO decisions locking this program (2026-06-10)

1. **The v3 studio drafts are the PRODUCT SPEC** — PARTIAL (exists-but-unusable) and MISSING are unfinished work, not roadmap. Branch closes only when every in-scope V1 feature is BUILT + usable. (LOOM-90)
2. **Design-first** — produce a detailed design spec for the whole backlog BEFORE any code. (LOOM-91)
3. **Granularity = 1 spec file per feature** (~24 files), grouped into 6 thematic tracks.
4. **Cadence = design ALL tracks first** → one design-checkpoint commit → one `/review-impl` over the design set → PO sign-off → THEN build per-feature.
5. **Scope = V1 PARTIAL + MISSING + the catalog-LATER items pulled in** (Corkboard, Character Arc, World Map, References, Progress/Stats). **Only V2 drafts remain out:** `composition-doujin-mockup.html` (同人/derivative), `composition-scene-graph-whatif.html` (branch/take sandbox).

---

## Program rules

- **Spec files live in** `docs/specs/composition-v1-design/<TID>-<slug>.md` (one per design task; subfolder keeps the 24 tidy).
- **Each spec follows the template below.** It is a DESIGN artifact — UX + interfaces + contracts + acceptance + test outline. **No implementation.**
- **Build order ≠ design order.** Design proceeds **track by track** (T0→T5). Build (later) proceeds **by phase**: `P0` quick-wins → `P1` finish PARTIALs → `P2` MISSING views.
- **Each built feature** later ships via its own `/loom` cycle (FE±BE + vitest + Playwright spec + 4-locale i18n parity) and adds its e2e spec to the Part-B QC gate.
- **MVC FE rules apply** (CLAUDE.md): `hooks/` controllers · `context/` services · `components/` views · `api.ts` · `types.ts`. Specs name the concrete files.
- **No-defer-drift:** any sub-item a spec consciously postpones gets a row in `docs/sessions/SESSION_HANDOFF.md` Deferred (or DEFERRED.md), never "we'll come back to it."

### Per-feature design-spec template

```
# <TID> <Feature> — design spec
Track · Phase · Type [FE|FS] · Depends-on
1. UX — which mockup section/component; states; empty/loading/error; mobile.
2. FE shape — components (views) · hooks (controllers) · context (if shared) · api.ts · types.ts; reuse existing idioms (name them).
3. BE delta — new/changed endpoints, fields, migrations — OR "none, reuse <endpoint>". Request/response shapes.
4. Data contract — exact JSON in/out; trust/sanitize boundary if it carries untrusted/LLM text.
5. Acceptance criteria — author-facing, testable.
6. Test outline — vitest cases · Playwright path · i18n keys (×4 locales).
7. Open questions — confirm-at-DESIGN / -at-BUILD items.
```

---

## Cross-cutting design decisions (cleared 2026-06-10)

Inherited by ALL tracks — later specs assume these:
- **Drag-and-drop = invest now (PO).** Add **dnd-kit** (no DnD lib today). A shared dnd-kit primitive serves reorder (Outline/Corkboard), beat-assign (Beat Sheet), and any later reorder.
- **Corkboard = a layout mode of the Outline panel (PO).** Not a separate tab — the Outline panel gets a **cards ⇄ tree** toggle over the same `useOutline` nodes; **T1.1 + T1.4 share host + hook**.
- **Beat mapping at scene *and* chapter level (PO)** — assign `beat_role` to either node kind; no BE change.
- **Power-views build standalone, then graft into T5.5 (Lead).** Scene Graph (T1.3) / Beat Sheet (T1.2) / Timeline (T2.3) are the views the T5.5 overlay hosts per the mockup.
- **Graph/canvas = hand-rolled SVG (Lead)** — no graph lib added; matches the mockup. `recharts` (already a dep) is the charting primitive for Timeline/Progress.
- **Right-panel docked features = fixed gated sub-tabs in CompositionPanel (Lead)** until the T5.4 windowing model lands.
- **Node edits use `If-Match` optimistic concurrency (Lead)** — 412 → refetch + toast.
- **Spoiler cutoff = `chapter.sort_order × EVENT_ORDER_CHAPTER_STRIDE` (REVIEW-IMPL MED-3)** — the knowledge `before_order`/`event_order` axis is the strided reading axis, NOT raw chapter order; every Track-2 spoiler cutoff (Cast status / Timeline / Character Arc) applies the stride conversion (M4d-1 precedent) + unit-tests it.
- **Shared `<GraphCanvas>` owner = T1.3 (REVIEW-IMPL LOW-8)** — design the SVG node/edge/drag primitive once in T1.3 Scene Graph; T2.2 + T2.5 consume it (don't re-roll three graphs).
- **Power-view interim host (REVIEW-IMPL LOW-9)** — the big views build standalone behind a simple route/overlay toggle during P1/P2; the T5.5 overlay + T5.4 windowing graft them last (reachable before windowing lands).

## New BE work surfaced during design (build-phase)

Design is surfacing real BE additions (PO chose to build, not stub). The build phase must sequence these with their consumers:
- **knowledge-service** `GET /v1/knowledge/entities/{id}/status?before_order=` — spoiler-windowed `:EntityStatus` (active|gone, A2 axis). **CORRECTED from "facts route" (REVIEW-IMPL HIGH-1)**: `:Fact` is closed-type (decision/preference/milestone/negation), no order axis, ≠ state. Optional `/entities/{id}/facts` = known-facts list. Consumers: **T2.1** Cast codex · **T2.4** Character Arc state band.
- **composition-service** world-map store — `work.settings.world_map.positions` PATCH (+ `backdrop_url`). **Backdrop upload reuses book-service media** (composition has no object-storage — REVIEW-IMPL MED-5); composition stores only the URL. Consumer: **T2.5** World Map.
- **composition-service** `/generate` **+ `selection` field** + explicit operation dispatch (rewrite/expand/describe; register + assert per the missing-enum lesson). Consumer: **T3.2** Selection tools.
- **composition-service** `grounding_prefs` store (table keyed by node_id/block/ref) + packer force-includes pins / drops excludes. Consumer: **T3.4** Grounding pin/exclude.
- **composition-service** `work.settings.references` + a **sanitized** `<references>` style-hint block in the packer. Consumer: **T3.6** References.
- **composition-service** ensure `work.settings` style keys (voice/tone/density/structure_pref/source_language) are writable (possible allowed-keys widening). Consumer: **T3.5** Style & Voice.
- **knowledge-service** extend `ExtractionJob` with per-run added counts (entities/relations/events) + new-item refs. Consumer: **T4.1** Flywheel panel.
- **composition-service** `composition_daily_progress` table + `GET/POST …/works/{id}/progress` + `work.settings.daily_goal`. Consumer: **T4.2** Progress & Stats.
- **book-service / shared editor schema** — preserve/allowlist the custom `aiProvenance` Tiptap mark in chapter content (so provenance survives save). Consumer: **T5.3** Provenance highlight.
- **FE dep:** add **dnd-kit** (reorder/assign T1.1/T1.4/T1.2 + windowing dock-rail T5.4). recharts (existing) for Timeline / Progress / Character Arc. **T5.4 OS pop-out** = BroadcastChannel/postMessage (FE, no BE).

## Tracks & design tasks (6 tracks · 24 tasks)

Legend: **Phase** `P0`/`P1`/`P2` (build priority) · **Cur** PARTIAL/MISSING · **Type** FE/FS · **BE today** = what already exists.

### Track 0 — Quick wins (BE done, FE unwired) — design first, smallest
| TID | Feature | Phase | Cur | Type | BE today | Spec |
|---|---|---|---|---|---|---|
| T0.1 | Plot-thread / promise-debt panel (FD-1 surface) | P0 | PARTIAL | FE | `GET /works/{id}/narrative-threads` + `narrative_thread_enabled` | [x] [spec](../specs/composition-v1-design/T0.1-plot-thread-debt-panel.md) |
| T0.2 | suggest-cast wiring | P0 | PARTIAL | FE | `POST /works/{id}/scenes/{node}/suggest-cast` (engine.py:878) | [x] [spec](../specs/composition-v1-design/T0.2-suggest-cast-wiring.md) |

### Track 1 — Structure & Outline (mockup §A)
| TID | Feature | Phase | Cur | Type | BE today | Spec |
|---|---|---|---|---|---|---|
| T1.1 | Outline Tree browser (persistent Act→Chapter→Scene→Beat) | P1 | PARTIAL | FE+BE? | `/outline`, node CRUD (decompose draft) | [x] [spec](../specs/composition-v1-design/T1.1-outline-tree-browser.md) |
| T1.2 | Beat Sheet (template beats ↔ filled scenes) | P2 | MISSING | FS | `/templates`, decompose | [x] [spec](../specs/composition-v1-design/T1.2-beat-sheet.md) |
| T1.3 | Scene Graph canvas (typed-link nodes) | P2 | PARTIAL | FE | `scene-links` CRUD, outline nodes | [x] [spec](../specs/composition-v1-design/T1.3-scene-graph-canvas.md) |
| T1.4 | Corkboard (index cards) — *catalog-LATER, pulled in* | P2 | MISSING | FS | none | [x] [spec](../specs/composition-v1-design/T1.4-corkboard.md) |

### Track 2 — World, Knowledge & Canon (mockup §B)
| TID | Feature | Phase | Cur | Type | BE today | Spec |
|---|---|---|---|---|---|---|
| T2.1 | Cast & Codex story-state (per-entity current state) | P1 | PARTIAL | FS | knowledge `/entities`,`/entities/{id}`,`/timeline` (FE reads direct) | [x] [spec](../specs/composition-v1-design/T2.1-cast-codex-story-state.md) |
| T2.2 | Relationship Map | P2 | MISSING | FE+BE-read | knowledge `/entities/{id}` 1-hop | [x] [spec](../specs/composition-v1-design/T2.2-relationship-map.md) |
| T2.3 | Timeline UI (spoiler-safe chronology) | P2 | MISSING | FS | knowledge **public** `GET /timeline` (ready) | [x] [spec](../specs/composition-v1-design/T2.3-timeline-ui.md) |
| T2.4 | Character Arc — *catalog-LATER, pulled in* | P2 | MISSING | FS | `/timeline?entity_id=` + `/entities/{id}` | [x] [spec](../specs/composition-v1-design/T2.4-character-arc.md) |
| T2.5 | World Map — *catalog-LATER, pulled in* | P2 | MISSING | FS | `/entities?kind=location` + relations (positions local) | [x] [spec](../specs/composition-v1-design/T2.5-world-map.md) |

> Canon Rules (§B) already **COVERED** (CanonRulesPanel + CanonRuleForm, LOOM-84) — not a design task.

### Track 3 — Write surface & AI co-writer (mockup §C)
| TID | Feature | Phase | Cur | Type | BE today | Spec |
|---|---|---|---|---|---|---|
| T3.1 | AI co-writer chat (conversational brainstorm) | P1 | PARTIAL | FS | reuse `features/chat` embed | [x] [spec](../specs/composition-v1-design/T3.1-ai-cowriter-chat.md) |
| T3.2 | Selection tools (rewrite / expand / describe) | P1 | PARTIAL | FS | `/generate` + selection field (new) | [x] [spec](../specs/composition-v1-design/T3.2-selection-tools.md) |
| T3.3 | Classic⇄AI inline mode (in-prose ghost + accept-bar) | P1 | PARTIAL | FE | reuse `useCompositionStream` + Tiptap | [x] [spec](../specs/composition-v1-design/T3.3-classic-ai-inline-mode.md) |
| T3.4 | Grounding pin/exclude (interactive RAG pack) | P1 | PARTIAL | FS | `/grounding` + prefs store + packer (new) | [x] [spec](../specs/composition-v1-design/T3.4-grounding-pin-exclude.md) |
| T3.5 | Style & Voice (editable voice/structure profile) | P2 | MISSING | FS | `BookProfile`/`work.settings` (editable) | [x] [spec](../specs/composition-v1-design/T3.5-style-and-voice.md) |
| T3.6 | References (comps/influences) — *catalog-LATER, pulled in* | P2 | MISSING | FS | `work.settings.references` + sanitize (new) | [x] [spec](../specs/composition-v1-design/T3.6-references.md) |

### Track 4 — Track, Flywheel & Progress (mockup §D)
| TID | Feature | Phase | Cur | Type | BE today | Spec |
|---|---|---|---|---|---|---|
| T4.1 | Flywheel panel ("+N new facts learned") | P1 | MISSING | FE+BE-read | knowledge `/projects/{id}/extraction/jobs` | [x] [spec](../specs/composition-v1-design/T4.1-flywheel-panel.md) |
| T4.2 | Progress & Stats (streak/goals) — *catalog-LATER, pulled in* | P2 | MISSING | FS | new daily-progress store | [x] [spec](../specs/composition-v1-design/T4.2-progress-stats.md) |

> Versions & History (§D) already **COVERED** (RevisionHistory) — not a design task.

### Track 5 — Editor shell, chrome & power-views (v3 shell chrome) — design last (frames the others)
| TID | Feature | Phase | Cur | Type | Notes | Spec |
|---|---|---|---|---|---|---|
| T5.1 | Focus / typewriter mode | P2 | MISSING | FE | editor-shell mode | [x] [spec](../specs/composition-v1-design/T5.1-focus-typewriter-mode.md) |
| T5.2 | Mention heatmap | P2 | MISSING | FE | over existing mention decoration | [x] [spec](../specs/composition-v1-design/T5.2-mention-heatmap.md) |
| T5.3 | AI-provenance highlight (mark-reviewed) | P2 | MISSING | FS | Tiptap mark in chapter content | [x] [spec](../specs/composition-v1-design/T5.3-ai-provenance-highlight.md) |
| T5.4 | Dock/float/pop-out windowing model | P2 | MISSING | FE | replaces the fixed sub-tab strip | [x] [spec](../specs/composition-v1-design/T5.4-dock-float-windowing.md) |
| T5.5 | Story-Map power-view overlay (Scene Graph/Timeline/Beat Sheet full-width) | P2 | MISSING | FE | **depends on T1.3 + T2.3 + T1.2** | [x] [spec](../specs/composition-v1-design/T5.5-story-map-power-view.md) |

---

## Dependencies & sequencing

- **Design order:** T0 → T1 → T2 → T3 → T4 → T5. T5 last because the power-view overlay (T5.5) composes T1.3/T2.3/T1.2 and the windowing model (T5.4) re-frames every panel.
- **Cross-task design dependencies:** T5.5 ⇐ {T1.3 Scene Graph, T2.3 Timeline, T1.2 Beat Sheet}. T2.4 Character Arc ⇐ T2.3 Timeline (shares the chronology axis). T2.1 Cast story-state ⇐ T2.2/knowledge state-read shape.
- **Greenfield / highest unknown (flag at DESIGN):** T2.5 World Map, T3.6 References, T1.4 Corkboard, T4.2 Progress/Stats — no existing BE; decide build-vs-thin-MVP per spec.

## Definition of done — DESIGN phase

- [x] All 24 spec files written (template-complete) under `docs/specs/composition-v1-design/` — **done 2026-06-10**; open questions cleared (Lead + PO forks resolved) per-track.
- [ ] One `/review-impl` pass over the design set; findings folded.
- [ ] PO sign-off at POST-REVIEW.
- [ ] Design-checkpoint commit(s) — docs only, no code.
- [ ] LOOM `SESSION_HANDOFF.md` ▶ NEXT updated to "BUILD phase, per-feature by phase order."

## Then — BUILD phase (after sign-off)

Per-feature `/loom` cycles in phase order **P0 → P1 → P2**, each with vitest + a Playwright spec + 4-locale i18n, each adding its e2e spec to the **Part-B QC/e2e gate** (see the gap-closure plan). Branch closes only when: all features built + usable · all unit/integration green · full Playwright suite (V0 net + every new spec) green · cross-service live-smokes recorded · PO sign-off. **PR #19 stays open until then.**
