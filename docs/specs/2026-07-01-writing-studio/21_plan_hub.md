# 21 — Plan Hub (the composition-domain "tech tree")

> **Status:** 📐 CLARIFY roadmap locked, 2026-07-07 · build not started.
> **Type:** FS (new Studio panel + a real capability-porting backlog it depends on).

## ⚠ Amendment 2026-07-10 — wiring superseded by [`24_plan_hub_v2.md`](24_plan_hub_v2.md)

The package model ([`00A_BOOK_PACKAGE_STRUCTURE.md`](00A_BOOK_PACKAGE_STRUCTURE.md) BPS-1..21) and the
`structure_node` spec layer ([`23_book_architecture.md`](23_book_architecture.md) BA1–BA15) landed after
this file. **All Hub wiring — data contracts, render sources, drawer, interactions, phases — now lives
in [`24`](24_plan_hub_v2.md) (decisions PH9–PH26).** This file's 26-item audit and six-category
classification remain valid history and are consumed by `24`'s re-map table, not restated. Specific
supersessions: **PH3** (OutlineTree's arc→chapter→scene(+beat) hierarchy is a dead ontology after
BA2/BPS-4 — its CRUD plumbing is reused, its type contract is not); **PH5** (closed by BPS-4: beats are
attributes, verified dead as tree nodes — no design pass needed); Phase 1's render source
(`composition_list_outline` supplies only chapter/scene layers; lanes come from `composition_arc_list`
over `structure_node`); and every `project_id`/Work-gated assumption (per-book re-key, BPS-1).
PH1, PH2, PH4, PH6, PH7, PH8 stand. G1/G2 (generation-exploitation) remain owned here and are untouched
by `24`.

## Why this exists

The "Cursor-for-novels" register already closed gaps #1 ([`16_chapter_editor_parity_and_retirement.md`](16_chapter_editor_parity_and_retirement.md)) and #4
([`20_agent_mode.md`](20_agent_mode.md)). This is the **real #103-row payoff**: the master spec's
Component Index has carried "Planner/Cast/Timeline/…" as an unscoped `⏳` placeholder since the
track started — this file replaces that placeholder with an actual audited backlog and a phased
plan, per this track's own build-while-plan rule (D: durable decisions + component index now,
each component's own `NN_spec.md` written when its cycle starts).

**User's framing (verbatim intent, 2026-07-06/07):** composition-service's planning domain (arc,
chapter, scene, beat, cast, motif — ~56 MCP tools, 25 legacy UI sub-tabs) is real but **rời rạc**
(scattered) — no single place to see the whole plan, click into any piece, and either edit it
directly or hand it to the AI assistant to edit. Wants a **fancy, modern, graph/tech-tree-style**
hub — not a plain indented list — that becomes the single entry point instead of hunting through
25+ tabs / 56 tools one at a time. Confirmed this is genuinely too large for one pass and must be
**cycled** (matches this track's own #13/#14 shared-foundation-then-fanout precedent).

## Ground-truth audit (2026-07-07)

Two claims turned out to be **false positives** worth flagging explicitly so nobody re-assumes
them: the master spec's row 103 implied `planner`/`quality` were already "ported" analogues of the
legacy tabs of the same name. They are not — verified by reading both sides:

- **Studio's `planner` panel** (`features/plan-forge/`, PlanForge `plan_*` tools — spec-driven
  propose/validate/compile) and **legacy `planner` sub-tab** (`PlannerView.tsx`, template-decompose
  `/outline/decompose`) are **two unrelated backends sharing a label**.
- **Studio's `quality`+4-siblings** (promise ledger / per-chapter critic / coverage / canon-issues)
  and **legacy `QualityPanel`/`ThreadsPanel`/`CriticPanel`/`CanonRulesPanel`** overlap conceptually
  but are different components; at minimum `QualityPanel`'s correction-stats table (accept/edit/
  regenerate/reject rates) has **no Studio equivalent at all**.

**Net: 0 of composition's 25 legacy `CompositionPanel` sub-tabs are ported verbatim to Studio v2.**
Full audit (component file, CRUD-vs-view-only, ported Y/N, LOC):

| # | Capability | Component | CRUD? | Ported? | LOC |
|---|---|---|---|---|---|
| 1 | `compose` AI draft/generate | `ComposeView.tsx` | CRUD | No (name-collides w/ Studio `compose`, different UI) | 257 |
| 2 | `cowriter` brainstorm chat | `CoWriterChat.tsx` | view-only | No | 31 |
| 3 | `assemble` chapter stitch | `ChapterAssembleView.tsx` | CRUD | No | 165 |
| 4 | `planner` template decompose | `PlannerView.tsx` | CRUD | **No** (see false-positive above) | 150 |
| 5 | `beats` beat sheet | `BeatSheetView.tsx` | CRUD | No | 158 |
| 6 | `graph` scene graph / what-if | `SceneGraphCanvas.tsx` | CRUD | No | 449 |
| 7 | `cast` Cast & Codex | `CastCodexPanel.tsx` | view-only | No | 112 |
| 8 | `relmap` relationship map | `RelationshipMap.tsx` | view-only (localStorage drag only) | No | 119 |
| 9 | `timeline` chronology | `TimelineView.tsx` | view-only | No | 155 |
| 10 | `arc` character arc | `CharacterArcView.tsx` | view-only | No | 139 |
| 11 | `worldmap` world/places | `WorldMap.tsx` | CRUD | No | 212 |
| 12 | `grounding` pin/exclude context | `GroundingPanel.tsx` | CRUD | No | 151 |
| 13 | `canonview` canon-as-of-chapter | `CanonAtChapterPanel.tsx` | view-only | No | 111 |
| 14 | `references` lore pins | `ReferencesPanel.tsx` | CRUD | No | 176 |
| 15 | `style` voice profile | `StyleVoicePanel.tsx` | CRUD | No | 172 |
| 16 | `canon` canon rules | `CanonRulesPanel.tsx` | CRUD | No (`quality-canon` is a different, read-only report) | 104 |
| 17 | `critic` inline critic | `CriticPanel.tsx` | CRUD-ish (recheck/dismiss) | No (`quality-critic` is different + read-only) | 91 |
| 18 | `threads` promise debt | `ThreadsPanel.tsx` | view-only (documented advisory) | No (`quality-promises` is a different component) | 112 |
| 19 | `progress` word-count goal | `ProgressPanel.tsx` | CRUD | No | 143 |
| 20 | `quality` correction-stats | `QualityPanel.tsx` | view-only | **No equivalent anywhere** | 96 |
| 21 | `polish` self-heal proposals | `PolishPanel.tsx` | CRUD | No | 161 |
| 22 | `flywheel` extraction stats | `FlywheelPanel.tsx` | view-only | No | 90 |
| 23 | `motifs` motif library | `MotifLibraryView.tsx` | CRUD | No | 185 |
| 24 | `conformance` motif/arc trace | `ConformanceTraceView.tsx` | CRUD/action | No | 76 |
| 25 | `settings` per-Work settings | `CompositionSettingsView.tsx` | CRUD | No | 99 |
| 26 | **Outline navigator** (arc/chapter/scene tree, full CRUD incl. drag-reorder) | `OutlineTree.tsx` (rendered directly by `ChapterEditorPage.tsx`, not inside `CompositionPanel`) | **CRUD** | No | — |

**Tool-only, zero UI anywhere** (checked, not assumed): `composition_arc_suggest`,
`composition_arc_import_analyze`, `composition_motif_suggest_for_chapter` — no frontend caller
exists for any of the three. These are net-new UI, not ports.

**Already Studio-only, no legacy equivalent** (a win, not debt): authoring-run lifecycle
(`composition_authoring_run_*`, 11 tools) shipped straight into `AgentModePanel` (#20) — skip.

## Wiring architecture — classify by relationship to the graph, not 1:1 port

**2026-07-07 follow-up finding.** Porting each of the 25+1 legacy sub-tabs into its own DOCK-1..11
panel with a fallback link (the original Phase 2 shape) would still leave every capability
**rời rạc** — same problem, new location. `timeline` is the sharpest example: it doesn't need a
panel of its own floating in the catalog, it needs an actual **seat in the Hub's information
architecture**. The real fix is classifying each capability by its relationship to the graph, then
wiring it accordingly — most capabilities turn out to need far less new work than "build a panel":

| Category | Meaning | Wired as |
|---|---|---|
| **Core** | Literally the graph's own nodes/edges | Rendered directly on the canvas — no separate panel at all |
| **Node facet** | Belongs to ONE node | A tab inside that node's detail drawer (already in the Phase 1 mockup) |
| **Cross-ref lens** | Belongs to an ENTITY that recurs across many nodes | Opens from clicking that entity's badge on any node — never a blind catalog entry |
| **Alternate view mode** | Same node set, different AXIS (not narrative order) | A toolbar view-switch on the Hub itself (`timeline` = story-time axis; `worldmap` = spatial axis) |
| **Action** | A workflow that produces a result, not a view | A button in a node's action rail or the Hub toolbar |
| **Not-a-Hub-concern** | Cross-cutting, doesn't attach to the graph | Explicitly reassigned to its real home (never silently dropped) |

Full reclassification of every item from the audit table above + the 3 zero-UI tool groups:

| Category | Items |
|---|---|
| **Core** (2) | #26 Outline navigator (already PH3) · #6 `graph` scene-graph/what-if — **`scene_links` become native graph EDGES**, not a separate panel; "what-if" is a branch-preview mode on those edges |
| **Node facet** (4) | #5 `beats` (post-Phase-0) · #13 `canonview` · #14 `references` · #17 `critic` |
| **Cross-ref lens** (5) | #7 `cast` · #8 `relmap` · #10 `arc` (character arc, entity-scoped) · #23 `motifs` · #16 `canon` (a canon-issue badge deep-links to the specific rule that fired) |
| **Alternate view mode** (2) | #9 `timeline` (story-time axis) · #11 `worldmap` (spatial axis) — same nodes, re-laid-out |
| **Action** (7) | #1 `compose` · #3 `assemble` · #4 `planner` (template decompose) · #21 `polish` · #24 `conformance` · `arc_suggest` · `motif_suggest_for_chapter` |
| **Not-a-Hub-concern** (9) | #2 `cowriter` (already served by Compose chat) · #12 `grounding` (belongs to Agent Context Rack #07a, already exists) · #15 `style` (per-Work settings) · #18 `threads` (**duplicate** — already served by Quality tab's `quality-promises`, flag for consolidation not new work) · #19 `progress` · #20 `quality` correction-stats (belongs under the Quality hub, not Plan Hub) · #22 `flywheel` · #25 `settings` · `arc_import_analyze` (import-wizard territory) |

**What this actually changes:** of 29 total items, only **11** (4 node-facet + 5 cross-ref-lens + 2
view-mode) need genuinely new Hub-integrated UI design. **7** are action buttons (small, mostly
wiring an existing mutation to a rail button). **2** are already absorbed into the Hub's core.
**9** are explicitly NOT Plan Hub's problem — reassigned to their real home so they stop reading as
"forgotten," one (`threads`) flagged as a likely duplicate worth deleting rather than porting.

## Generation-exploitation gaps (2026-07-07 follow-up) — the deeper problem behind the GUI one

**The GUI wiring above is necessary but not sufficient.** A user's sharper follow-up: even a
perfect Plan Hub is just a pretty viewer if the data it shows never actually *steers* generation.
Traced the real prompt-assembly code (not the GUI) for all 3 generation entry points — the
finding is genuinely mixed, not "everything is disconnected":

**Already well-exploited (no work needed):** composition-service has ONE real context-assembly
chokepoint, `app/packer/pack.py`, shared by `ComposeView`'s draft, `ChapterAssembleView`'s stitch,
AND Agent Mode's autonomous drafting (`authoring_run_service.py`'s `EngineDraftingSeam` calls the
exact same handler in-process). It genuinely injects, pre-generation: cast present at the scene
(`gather_present`), canon rules (`gather_canon` — steers the draft, THEN a separate post-draft
`canon_reflect` pass re-checks/revises it, the richest-wired source of the three), grounding pins
(`_apply_grounding_pins`), prior-chapter/timeline context (`gather_recent`/`gather_timeline`), and
even the outline's other unwritten scene titles/synopses (`gather_structural`). This is real,
already-working exploitation — nothing here needs fixing.

**Confirmed gap G1 — motif is write-only.** `motif_application` rows are bound by the planner
(`engine/motif_select.py`) but **`pack()` never reads them back**. There is no `<motif>` prompt
block. The only two places motif rows get read are a display/audit trace (`routers/conformance.py`)
and a POST-generation conformance judge over the already-finished text
(`engine/motif_conformance_producer.py`) — scoring whether a motif happened to show up, never
telling the drafter to make it show up. `composition_motif_suggest_for_chapter` (the zero-UI tool
from the earlier audit) is never called by any generation code path either — a second symptom of
the same root gap.

**Confirmed gap G2 — PlanForge propose is blind to the book's existing state.** `plan_propose_spec`
(both rules-mode `engine/plan_forge/propose.py` and LLM-mode `propose_llm.py`) reads ONLY the
caller-supplied markdown document. Neither ever queries `outline_node`, existing cast, or existing
motifs — `plan_forge_service.py` imports `WorksRepo`/`PlanRunsRepo`/`GenerationJobsRepo` but no
`OutlineRepo`/`GlossaryClient`/`MotifRepo`. Proposing a new spec for a 40-chapter-in-progress book
today is architecturally identical to proposing for a blank one.

**Related, tracked separately (not this epic — belongs to #20 Agent Mode):** `EngineCriticSeam.
_critique`'s own docstring admits it passes `active_rules`/`present_facts` empty
(`authoring_run_service.py:513-518`) — so Agent Mode's continuity JUDGE scores blind to canon even
though the DRAFT it's judging was canon-steered. Flag for `20_agent_mode.md`'s own debt list, not
duplicated here (gate #1 out-of-scope — different track).

- **Phase G1 — Feed motif into `pack()`.** New `gather_motifs` lens (mirrors `gather_canon`'s
  shape) reads `motif_application` for the current node, renders a `<motif>` block naming the
  motif + its established meaning/prior appearances, added to `_BLOCK_ORDER`
  (`packer/assemble.py:25`). Backend-only, composition-service; no new UI required beyond what
  Phase 1's motif badge already shows. This is the fix that makes a motif badge on the Plan Hub
  graph mean something beyond decoration — the generator will actually try to honor it.
- **Phase G2 — Give PlanForge propose real book-state awareness.** `plan_propose_spec` gains an
  optional existing-state context pass (existing arcs/cast/motifs summarized, analogous to
  `gather_structural`/`gather_present`) so proposing against an in-progress book produces a spec
  that's coherent with what's already there, not a blind rewrite proposal. Needs its own short
  CLARIFY on exactly what existing-state summary an LLM proposal step should see (full detail vs.
  a compact digest) before sizing the build.

These two phases are **orthogonal to Phases 0-4** (GUI) — G1/G2 fix generation architecture and
would matter even if Plan Hub's GUI never shipped; they can build in parallel, not strictly after.

## Locked decisions (from 2026-07-06/07 CLARIFY)

| # | Decision | Why |
|---|---|---|
| PH1 | **Graph-canvas visual style**, not an indented list | User explicitly wants the tech-tree/game feel, not a file-tree. |
| PH2 | **React Flow** (`@xyflow/react`, MIT) is the rendering library | Nodes are literal React components (full custom styling — icons, status rings, badges for cast/motif overlays), built-in pan/zoom/minimap, no license cost (fits no-platform-lock-in). Alternatives considered: Reagraph (WebGL, faster at huge scale but far less per-node customization — wrong tradeoff for a "fancy" hand-styled tree at book scale, which is hundreds not millions of nodes); react-d3-tree (D3 layout, plainer default look, less control over free-form edges); Cytoscape.js (graph-theory analysis tool, wrong aesthetic target); ReGraph (commercial license — rejected, hobby project). |
| PH3 | **Hub = reused OutlineTree CRUD engine, re-rendered as a graph**, not a rebuild | `OutlineTree.tsx` already has the exact arc→chapter→scene(+beat) hierarchy with full CRUD (rename/status/reorder/archive) proven live. Phase 1 ports its data+mutations into a new DOCK-1..11 `plan-hub` panel and swaps the renderer from indented-list to React Flow nodes — not a new backend, not new mutation logic. |
| PH4 | **Cast/motif render as node badges/overlays, not tree branches** | Confirmed by the DB model: `pov_entity_id`/`present_entity_ids` are per-node glossary refs (not children); `motif_application.outline_node_id` is a nullable ledger FK (not a parent/child edge). A tech-tree metaphor still works — badges hanging off a node read naturally as "this scene carries these threads," closer to a real tech-tree's icon overlays than a literal child node would. |
| PH5 | **Beat gets ONE canonical representation before Phase 1 ships** | Today `kind='beat'` (real child node) and `beat_role` (attribute on scene/chapter, from the Beat Sheet feature) coexist — rendering both today would show duplicate/conflicting beat info on the same graph. Phase 0 below resolves this; blocks Phase 1's beat rendering specifically (not the whole hub). |
| PH6 | **Hub v1 scope = overview + click-through**, not a mega-editor | Matches DOCK-8 (hub launches, doesn't internally re-implement 25 capabilities). The one exception is PH3 — outline CRUD ships IN the hub because it's the hub's own native data, not a foreign capability being crammed in. |
| PH7 | **Legacy-tab fallback while porting is incomplete** | The hub does not block on all 11 real UI items (2b/2c above) being built first. A node facet tab, a badge click, or a view-mode switch routes to the real Studio surface if it exists yet, else deep-links to the legacy `ChapterEditorPage` tab as an interim fallback — visibly and explicitly (never a silent dead click), removed item-by-item as Phase 2's waves ship. Does not apply to the 7 Actions (wire directly, no legacy detour needed) or the 9 not-a-Hub-concern items (already have or get a real home elsewhere). |
| PH8 | **AI-edit highlighting on the graph is a LATER phase**, not v1 | Requires locking a `resource_ref = {project_id, node_id}` convention for `propose_record_edit` in the composition domain — real new contract work, not reuse. Sequenced after the hub itself exists and after enough capability panels exist for it to matter. |

## Phased roadmap (each phase = its own future `NN_component.md` spec + build cycle)

Numbering continues this track's own scheme; sub-phases get letter suffixes like #13/#14 did.

- **Phase 0 — Beat canonicalization.** Pick the single canonical beat model (child node vs.
  `beat_role` attribute — needs one more short design pass weighing: does anything already query
  beats as tree nodes that would break if it became attribute-only, and vice versa), migrate/
  reconcile existing data, update `OutlineTree.tsx`'s own `PARENT_KIND` map + Beat Sheet's writer to
  agree. **Blocks:** Phase 1's beat rendering only.
- **Phase 1 — Plan Hub v1**: new `plan-hub` DOCK panel. React Flow graph of arc→chapter→scene(+beat
  post-Phase-0), rendered from `composition_list_outline` (summary mode); cast badges from
  `pov_entity_id`/`present_entity_ids` (resolved via glossary-service, batched not per-node);
  motif badges from `motif_application` list. Reuses `OutlineTree`'s mutation hooks for
  rename/status/reorder/add-child/archive directly on graph nodes (PH3). Click → open ported
  Studio panel or PH7 legacy-tab fallback link. This is the component that actually needs the
  design-drafts → CLARIFY → draft-HTML step (per this repo's usual process for a new visual
  surface) before BUILD — not skipped, just sequenced after this roadmap doc.
- **Phase 2 — Wire by category, not by legacy tab list.** Per the Wiring architecture section
  above, this phase is now 4 much smaller waves instead of "port 25 panels":
  - **2a Node facets** (4 items: beats/canonview/references/critic) — each becomes a tab in the
    Phase-1 detail drawer. Small per-item, same drawer shell reused every time.
  - **2b Cross-ref lenses** (5 items: cast/relmap/arc/motifs/canon) — each becomes a real DOCK-1..11
    panel, but reached ONLY by clicking the matching badge on a node (never a bare catalog entry
    with no context) — group by shared data (cast+relmap+arc all read glossary entities; motifs+canon
    both read composition's own tables) for fanout waves the way #13/#14 did.
  - **2c Alternate view modes** (2 items: timeline/worldmap) — a toolbar view-switch on the Hub
    itself that re-lays-out the SAME loaded nodes on a different axis; not a new panel, a new
    renderer mode for Phase 1's existing canvas.
  - **2d Actions** (7 items) — wire each as a button in a node's action rail or the Hub toolbar,
    calling the mutation the legacy component already proved works. The smallest category per-item.
  Each wave clears its items off the PH7 fallback-link list. The 9 "not-a-Hub-concern" items are
  explicitly OUT of this phase — closed by a one-line note pointing to their real home (Quality hub,
  Agent Context Rack, settings gear, or a dedup ticket for `threads`), never silently dropped.
- **Phase 3 — Net-new UI for the 3 zero-UI tool groups** (`arc_suggest`, `arc_import_analyze`,
  `motif_suggest_for_chapter`) — smaller, independent scope; can interleave with Phase 2 waves
  rather than strictly sequence after.
- **Phase 4 — AI-edit highlighting on the hub** (PH8): lock `resource_ref` convention for
  composition `propose_record_edit`, wire `StudioContextBus` so a pending proposal highlights its
  matching graph node. Sequenced last — needs Phase 1's hub to exist and benefits from Phase 2
  having ported enough panels that "click through to fix" is usually possible.

## Explicitly not decided here (deferred to each phase's own kickoff)

- Exact fanout grouping inside Phase 2 (waves above are illustrative, not a contract).
- Whether `OutlineTree.tsx`'s existing indented-list view stays available as a toggle alongside the
  new graph canvas (precedent: Corkboard already does a cards⇄tree toggle for the legacy component)
  — worth asking the user again once Phase 1 is actually being designed, not now.
- Full component index row numbering for each Phase-2 panel — assigned when that wave starts.

## Update to master spec

`00_OVERVIEW.md` row 103's "Planner/Cast/Timeline/…" fragment is superseded by this file; see the
row edit in that file's Component Index (row `21`).
