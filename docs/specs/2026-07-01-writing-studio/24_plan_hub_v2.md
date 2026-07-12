# 24 · Plan Hub v2 — the package explorer on the graph canvas

> **Status:** 📐 SEALED (multi-agent authored + adversarially reviewed 2026-07-10; PO ratified all product decisions same day — see 00B §6) — buildable
> **Type:** FS (new Studio panel + navigator rail + 3 new read surfaces). Decision prefix **PH-**, continuing [`21_plan_hub.md`](21_plan_hub.md)'s PH1–PH8.
> **Supersedes:** 21's *wiring* (PH3's data source, PH5's "one more design pass", the Phase-1 render contract). 21's 26-item audit and its six-category classification remain valid history and are consumed, not restated.
> **LAW upstream:** [`00A_BOOK_PACKAGE_STRUCTURE.md`](00A_BOOK_PACKAGE_STRUCTURE.md) (BPS-1..21, DA-1..14) · [`23_book_architecture.md`](23_book_architecture.md) (BA1–BA15) · [`22_scene_model_and_crud.md`](22_scene_model_and_crud.md) (amended SC1–SC13, BPS-13).
> **Ownership boundaries honored:** migration DDL/backfills → `25` · PlanForge link step → `27` · dirty-tracking/staleness/conformance *mechanics* → `26` · `structure_node` MCP CRUD → `23` BA11 · new agent-experience tools → [`28_agent_native_studio.md`](28_agent_native_studio.md) (authored + adversarially reviewed 2026-07-10). This file owns the Hub's **GUI wiring and read contracts** only.
> **Numbering note:** the one-time spec-number collision is resolved — translation-repair was renumbered to `29_translation_repair.md` on 2026-07-10 with links swept ([`00A` §10](00A_BOOK_PACKAGE_STRUCTURE.md)); no `24_` collision exists. Cross-spec citations of THIS file still use the full filename `24_plan_hub_v2.md` (as `21`'s amendment block already does).
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6), [`docs/standards/scope-separation.md`](../../standards/scope-separation.md).

---

## Why

The user asked for one place to see the whole plan of a book, click into any piece, and either edit it directly or hand it to the AI — a graph, not a file tree ([`21`](21_plan_hub.md) PH1). `21` audited the 29 scattered capabilities and classified them; then [`23`](23_book_architecture.md) and [`00A`](00A_BOOK_PACKAGE_STRUCTURE.md) changed the ground under it: the arc became a first-class `structure_node` spec layer, the book became a per-book package, beats stopped being tree nodes, and pacing stopped being a stored attribute. Every one of those decisions lands *on the canvas* — the Hub is where the package model becomes something an author can see.

Plan Hub v2 is therefore not "a graph view of the outline". It is the **package explorer**: `deps/` chips, `book.lock` pins, `spec/` nodes and lanes, `tests/` assertions as a problems layer, `manuscript/`+`.index/` as the actual-state half of every node, and `.runs/` behind the action rail. The terraform relation — desired state ↔ actual state, reconciled — is the Hub's core visual claim: every chapter and scene card shows **both truths**, and the gap between them is rendered, never hidden.

---

## Investigation findings

All claims below were verified against code on 2026-07-10, not inherited from `21` or the drafts.

### F-H1 — the keyset lazy-children machinery exists and is the load pattern to reuse

[`migrate.py:188`](../../../services/composition-service/app/db/migrate.py#L188) defines `idx_outline_node_children_keyset ON outline_node(parent_id, rank COLLATE "C", id) WHERE NOT is_archived` — built for the manuscript navigator's lazy tree. The route is [`routers/outline.py:124`](../../../services/composition-service/app/routers/outline.py#L124) (`GET /works/{project_id}/outline/children`, keyset-paged by `(rank, id)` via the opaque cursor codec at [`:105`](../../../services/composition-service/app/routers/outline.py#L105), limit clamped 1..200, malformed cursor → 400 never a silent page-1 reset). This is the proven 10k-chapter shape; the Hub extends it rather than inventing a second one.

**But its root semantics break under `23`.** The route's contract reads *"`parent_id` omitted → top-level arcs"*. After `23`'s migration Phase 1/4, chapter nodes get `parent_id = NULL` and attach via `structure_node_id` — so "omitted parent" would suddenly return *every chapter in the book*, and the arc level would return nothing. The route needs a **structure axis** (`structure_node_id` param + a matching keyset index), and the Manuscript Navigator's existing calls need re-pointing. Neither `23`'s migration table nor `25`'s draft ordering names this route-semantics flip — **recorded in Open Questions for the integrator.**

### F-H2 — the L1 ref projection exists but lacks every badge field the Hub needs

[`mcp/server.py:321`](../../../services/composition-service/app/mcp/server.py#L321) defines `_OUTLINE_REF_FIELDS = (id, kind, parent_id, title, status, version, story_order, chapter_id)` — the `detail=summary` projection built after the 146K-token `composition_list_outline` incident. It deliberately drops `goal`/`synopsis` prose. It also drops `tension`, `beat_role`, `pov_entity_id`, `present_entity_ids` — exactly the fields the Hub's badges and the pacing sparkline render. The REST children route ([`routers/outline.py:152`](../../../services/composition-service/app/routers/outline.py#L152)) has no projection at all — it returns `model_dump()` full rows including synopsis prose, which at 10k chapters is wire bloat the Hub must not pay.

### F-H3 — the GUI mutation surface is REST, and reorder already exists there

[`features/composition/api.ts`](../../../frontend/src/features/composition/api.ts): `createNode` (`:201`, `POST /works/{pid}/outline/nodes`), `patchNode` (`:223`, `PATCH /outline/nodes/{id}` — the node `version` rides the **`If-Match` header** → 412 `NODE_VERSION_CONFLICT`; no `expected_version` field exists anywhere in `api.ts`, that name is the MCP-tool arg of `23` BA11), archive/restore (`:231`/`:236`), and **`reorderNode` (`:243`, `POST /outline/nodes/{id}/reorder` — drag-reorder + reparent, same `If-Match` convention)**. So the human GUI writes through REST; the MCP tools (`23` B3's `composition_outline_node_move` etc.) are the *agent's* surface over the same repo methods. `23`'s current text settles the GUI transport in the same paragraph it defines the mirrors: *"Writes stay MCP-first **for agents** — MCP-first governs agent logic, not human GUIs … Phase B therefore also ships REST write mirrors over the same repo methods — one repo method, two front doors"* ([`23:356`](23_book_architecture.md), which cites this spec's PH20/OQ-3 by name). The Hub's drag-and-drop therefore has its arc write path: `23` Phase B's REST mirrors. OQ-3 records the resolution.

### F-H4 — the undo/OCC pattern is uniform and reusable

Tier-A tool results carry `_meta.undo_hint` built by the helper at [`mcp/server.py:165`](../../../services/composition-service/app/mcp/server.py#L165); `composition_motif_bind` returns a verified-inverse `undo_token` consumed by `composition_motif_unbind` ([`:2684`](../../../services/composition-service/app/mcp/server.py#L2684), [`:2691`](../../../services/composition-service/app/mcp/server.py#L2691)). OCC is version-checked writes → 412 (`expected_version` arg on the MCP surface, `If-Match` header on REST — F-H3), and `SceneRail` already implements the 412 → *"changed elsewhere — reloaded"* recovery. The Hub adds **no new undo machinery**.

### F-H5 — the lockfile is already renderable per node; the lane hook comes from 23

`motif_application` ([`migrate.py:718`](../../../services/composition-service/app/db/migrate.py#L718)) carries `book_id`, `motif_id`, **`motif_version`** (the pin), `outline_node_id` (indexed at `:731`), `role_bindings`. `23` adds `structure_node_id` so a chip can hang on an arc lane. The per-chapter REST read exists ([`api.ts:185`](../../../frontend/src/features/composition/api.ts#L185), `GET …/outline/motif-bindings?chapter_id=`) but is an N+1 at book scale — the Hub needs one book-wide read (§Overlay).

### F-H6 — thread debt is a query, and the index for it already exists

`narrative_thread` ([`migrate.py:275`](../../../services/composition-service/app/db/migrate.py#L275)) has `opened_at_node`/`payoff_node` FKs (`ON DELETE SET NULL`) and the hot partial index `idx_narrative_thread_open … WHERE status IN ('open','progressing')` (`:299`). BA15 ("promise rollup is a query, not storage") is directly implementable for the problems layer with zero schema.

### F-H7 — scene_link edges are sparse and closed-kind

[`migrate.py:192`](../../../services/composition-service/app/db/migrate.py#L192): `kind IN ('setup_payoff','custom')`, `UNIQUE(from,to,kind)`, self-loop CHECK, indexed by project and `from_node_id`. MCP create/delete exist ([`server.py:924`](../../../services/composition-service/app/mcp/server.py#L924), `:957`). Sparse by design ("ONLY non-derivable edges") — a whole-book fetch is cheap, which settles the edge-loading strategy (PH13).

### F-H8 — the host primitives and the catalog shape are exactly as `08`/`11` promise

[`StudioHostProvider.tsx`](../../../frontend/src/features/studio/host/StudioHostProvider.tsx): `openPanel(panelId, {focus?, title?, params?, component?})` (`:52`,`:77`), `focusManuscriptUnit(chapterId, panelId='editor')` (`:116`), `registerStudioTool`/`useRegisterStudioTool` (`:35`,`:203`), `useStudioBusSelector` (`:161`). The outbound-link resolver exists ([`studioLinks.ts`](../../../frontend/src/features/studio/host/studioLinks.ts)). The catalog ([`catalog.ts:110`](../../../frontend/src/features/studio/panels/catalog.ts#L110)) shows the exact row shape + the hub-launcher precedent (`knowledge`, `quality`) and the params-singleton precedent (`json-editor`).

### F-H9 — cast-badge name resolution has an endpoint, but its real contract is narrower than the Hub needs

Glossary already serves a book-wide name map: `GET /books/{bookId}/entity-names` ([`glossary/api.ts:243`](../../../frontend/src/features/glossary/api.ts#L243)), consumed via TanStack Query by [`useBookEntities.ts`](../../../frontend/src/features/enrichment/hooks/useBookEntities.ts). **But the handler is not filter-free:** [`entity_handler.go:1519-1521`](../../../services/glossary-service/internal/api/entity_handler.go#L1519) selects `status = 'active'` only, skips any entity whose resolved `name` attribute is empty, and **silently truncates at `LIMIT 500`** — no pagination, no truncation flag. Against this spec's own 10k-chapter hard requirement, a book with >500 named entities (or a `pov_entity_id`/roster ref pointing at a non-active entity) would render an "unresolved" chip for an entity that exists — the exact `mocked-client-hides-server-side-default-filters` bug class. So the endpoint is **reused, not reused as-is**: H1.6 widens its contract (keyset pagination + `truncated` flag + all non-deleted statuses) and PH26 specs the client-side degradation. No per-page glossary batching is needed either way (the drafts' "batched per page" note stays simplified).

---

## Reconciliation with the draft HTML

[`screen-plan-hub-panel.html`](../../../design-drafts/screens/studio/screen-plan-hub-panel.html) and [`screen-plan-navigator.html`](../../../design-drafts/screens/studio/screen-plan-navigator.html) predate `23`/`00A`. Explicit disposition of every load-bearing element:

| Draft element | Verdict | Why |
|---|---|---|
| Horizontal **arc lanes**, chapters as trunk cards, scenes as branch cards; NOT force-directed | ✅ **survives** — now rendered from `structure_node`, with nesting | The lanes metaphor maps 1:1 onto `structure_node` depth 0–2; sub-arcs render as nested sub-bands / collapsible super-nodes (`23:362`). Lane *captions* ("ch 1–40") become **derived** span text (BA6) and may show the `is_contiguous` warn. |
| **Collapsed-run nodes** ("Chapters 0005–0040 · 36 chapters · 2 canon issues") + collapsed Arc II | ✅ **survives, upgraded** | Now backed by *server rollups* (PH11), not client-side folding of loaded nodes — the virtualization analogue becomes the actual loading strategy. |
| 280px **detail drawer** (kind/title/status/synopsis/cast/motifs/canon-banner/actions) | ✅ **survives** | Becomes PH16's drawer; the arc variant embeds `23`'s arc-inspector sections. |
| Badges: cast chips, purple motif chips, **beat-dot + `beat_role` label** | ✅ **survives** | BPS-4 confirmed beats are attributes — the draft's beat-dot rendering was accidentally already correct. |
| Hover **action rail** incl. "Open Cast Codex (legacy tab · not yet ported)" | ✅ **survives** | PH7's visible-fallback made concrete. |
| Canon-issue red ring + plain-sentence canon banner | ✅ **survives** | Feeds from the problems overlay (PH18). |
| `ai-pending` dashed-gold node state | ⏸ **survives as Phase-4 preview only** (its own note 6 already says so) | Still gated on PH8's `resource_ref` convention — unchanged. |
| **3-level tree (arc→chapter→scene) from `composition_list_outline`** | ❌ **invalidated** | Arcs come from `composition_arc_list` over `structure_node` (up to 5 levels: saga→arc→sub-arc→chapter→scene); `composition_list_outline`/the children route supply only chapter/scene layers (F-H1/F-H2). |
| Lanes keyed by legacy `outline_node kind='arc'`; `project_id`/Work keying anywhere | ❌ **invalidated** | BPS-1/BA8: everything keys on `book_id`; no Work gate (PH9). |
| Clean contiguous era-band per arc | ⚠ **weakened** | BA6 spans are derived and may be non-contiguous (warn-only). PH14 defines the rendering: a lane renders one band per contiguous chapter run, tied by a thin lane spine. |
| Navigator: same fetch as Manuscript Navigator, row click focuses **the Hub graph, not the Editor** | ✅ **survives** (PH25) | The VS-Code Explorer-vs-Source-Control analogy holds; the fetch re-points to the book-keyed children route + `composition_arc_list`. |
| No representation of `tracks`/`roster`/`roster_bindings` | ❌ **gap, filled here** | PH16 (arc drawer Structure/Roster sections) + PH19's role-binding chips. Tracks get a lane-legend treatment, not per-node paint (PH23). |

---

## Locked decisions

Numbering continues `21` (PH1–PH8). Of those: **PH1, PH2, PH4, PH6, PH7, PH8 stand**. **PH3 is amended** (the CRUD engine is reused, the 3-level type contract is not — F-H3, recon caution set). **PH5 is closed** by BPS-4 (no design pass needed; consume `23` Phase 0).

| # | Decision | Why |
|---|---|---|
| **PH9** | **The Hub keys on `book_id` and renders from the seven read surfaces of the contract table (§Read surfaces) — and nothing else.** Three are composition node/decoration surfaces: (1) `composition_arc_list` — the whole `structure_node` shell in one call, (2) the keyset children route for chapter/scene windows, (3) one `plan-overlay` aggregate for canon/thread problems, chips, tension. Four complete the picture: (4) the whole-book `scene-links` fetch (PH13), (5) the book-service actual-state join (PH12, lazy per loaded window), (6) the glossary entity-names map (PH26), (7) `26` IX-14's `GET /conformance/status` — per-arc dirty badges + the stale-chapter rollup (PH18), fetched on open and re-fetched on focus. **No Work gate anywhere. The cold-open budget is stated ONCE, here, and enforced by H8.1: ≤ 5 requests (shell + overlay + scene-links + entity names + conformance status) before the lane structure paints** — chapter/scene windows and actual-state joins load lazily, after paint. | BPS-1/BA8. F4's N+1 died in `23` (C5); the Hub must not resurrect it. A closed, enumerated read set is the guard: a fetch that is not in the table is a new decision to review, never an incremental "just this once". |
| **PH10** | **Canvas node payload = L1 ref + badge scalars; prose never ships to the canvas.** The children route gains `detail: summary\|full` (default `full` for back-compat; the Hub always passes `summary`), where summary = `_OUTLINE_REF_FIELDS` + `structure_node_id, beat_role, tension, pov_entity_id, present_entity_ids (server-truncated to the first 3 — the PH23 chip cap, mirrored on the wire), present_entity_count`. The count stays exact; the capped ids are exactly what the canvas may render (PH23's 3 cast chips) — the full roster loads with the drawer's per-node full fetch, on selection, like `goal`/`synopsis`. | F-H2. The 146K lesson (OUT-1) applied to the GUI wire: a canvas renders thousands of nodes; the drawer renders one. Without the capped ids, PH23's cast chips would have no data source on any locked read surface — a COUNT can render `+N`, never a chip. **✏️ AMENDED 2026-07-13 (SC11 amendment Phase 3):** the summary payload gains **`written`** (a bool). PH10's field list is CLOSED, so this is a deliberate amendment — and it is admissible precisely because it costs nothing at the read budget: it is a field on a request the Hub already makes, not a sixth call. It in fact **REFUNDS** one against PH9/H8.1, because `useActualState`'s per-chapter page-walk of book-service's scene index is deleted. `written` is read from `outline_node.written_scene_id`, a MAINTAINED column reconciled from `scenes.source_scene_id` — a column read, NOT the cross-service join SC11 forbids. A BOOL, not the scene id: the canvas renders a STATE, and PH10's own discipline is refs-and-scalars-never-content; the drawer's `detail=full` carries the id for the one node that needs it. See [`docs/specs/2026-07-13-sc11-amendment-written-verdict.md`](../2026-07-13-sc11-amendment-written-verdict.md). |
| **PH11** | **Lazy loading is expand-on-demand keyset windows; collapsed anything renders server rollups.** Arc shell first (one call, includes derived span + `chapter_count` + problem counts per arc). Expanding an arc pages its chapters (`structure_node_id` axis, new index below); expanding a chapter pages its scenes (`parent_id` axis, existing index). A collapsed run/arc renders its rollup card from the shell/overlay data — **never** from loaded child nodes. | F-H1 precedent; 10k-chapter books are a stated hard requirement. The draft's collapsed-run affordance becomes the loading model itself. |
| **PH12** | **Two truths per node, joined client-side.** Spec = composition nodes (PH10). Actual = book-service: the chapter spine (Chapter Browser's existing list) for chapter nodes; `GET /v1/books/{book_id}/scenes` (`22`) joined on `scenes.source_scene_id` for scene nodes. The three row shapes of `22`'s browser union render on the canvas as node states: **planned+written** (normal), **spec-only** ("not yet written", hollow card), **index-only** (appears ONLY in the Unplanned tray, PH21). NULL anchors are surfaced per BPS-13 — *"not yet written"* ≠ *"anchor lost"*, with the ⚓ re-anchor action in the drawer. | SC11 locked client-side joins (BPS-11); a cross-service server join is explicitly rejected. The terraform duality is the Hub's core claim (§Why) — hiding either truth blurs the seam the architecture exists to enforce. |
| **PH13** | **`scene_link` edges are native graph edges, loaded whole-book in one call.** Edge kinds render distinctly (`setup_payoff` solid directional, `custom` dashed + label). An edge whose other endpoint is not loaded/collapsed renders as a **stub connector** into the collapsed node, which carries an edge-count badge — never silently dropped. | F-H7: sparse by design, so whole-book fetch is cheap and windowed edge-fetch is complexity without payoff. OUT-5's no-silent-truncation spirit applied to rendering. `21` already classified #6 as Core. |
| **PH14** | **Layout is deterministic custom positioning; React Flow supplies mechanics only** (pan/zoom/minimap/hit-testing, `onlyRenderVisibleElements`). `y` = lane band derived from the `structure_node` tree (depth-nested sub-bands, rank-ordered); `x` = position of `story_order` within the loaded window with collapsed-run compression. A non-contiguous arc renders one band per contiguous chapter run joined by a thin lane spine + the BA6 warn chip. **No force/stock layout (dagre/elk) — an insert must shift, never reshuffle.** | The draft's own notes lock this; recon names it the pillar's biggest custom surface. Deterministic (lane, order) → (x, y) is memoizable, stable under insert/reorder, and testable without a browser. |
| **PH15** | **The 29-item re-map table (§Package re-map) is normative.** Every item from `21`'s audit gets a package path + a Hub seat; the story arc (`structure_node`) is Core; the character arc stays a cross-ref lens (DA-10, `23:362` confirms `21`'s row #10). | `21`'s six categories survive; only the *addresses* changed. One table stops the next agent re-deriving 29 placements. |
| **PH16** | **The drawer is a detail pane over the selection, not a second capability** (SC10 precedent). Arc/saga selected → embeds `23`'s arc-inspector sections **as-is** (Structure · Roster · Chapters · Conformance · Provenance — `23` C3, DOCK-2 no fork). Chapter/scene selected → facet tabs: **Overview** (intent fields incl. the two-truths block + anchor state) · **Beats** · **Canon here** · **References** · **Critic** (`21`'s four node facets + overview). Drawer header always shows the desired-vs-actual pair: spec `status` chip + prose state chip, and the click contract is fixed: **drawer edits the desired state; "Open in Editor" (→ `focusManuscriptUnit`) goes to the actual.** | DOCK-8: the drawer never swaps the panel's subtree; it decorates a selection. The seam rule comes from `00A` §1 — nobody edits `dist/`, everybody edits chapter 12. |
| **PH17** | **Pacing renders as a derived sparkline and is edited only through scenes.** Each expanded arc lane shows `[scene.tension for scene ∈ span(arc)]`; for unloaded regions the sparkline falls back to the overlay's per-chapter `tension` rollup, visually marked as coarser. There is **no arc-level pacing edit affordance anywhere** — clicking a sparkline point focuses that scene; the edit is `outline_node.tension` via the widened update (SC8). "Apply a template's curve" is exactly `composition_arc_apply` writing into scene `tension` (BA3). | BPS-3/DA-7. A stored/editable arc curve is the drift bug this register deleted; the GUI must not reintroduce it as a widget. |
| **PH18** | **The problems layer has three sources and two reads.** Conformance drift/staleness arrives via `26` IX-14's `GET /conformance/status` (read surface #7): per-arc `dirty` + `dirty_reasons` + `stale_chapters` + the `index.stale_chapter_count` rollup, fetched on Hub open and re-fetched on focus — exactly the consumer contract `26` names for the Hub. Canon findings and open `narrative_thread` debt (BA15 query) arrive as `{node_ref → counts + refs}` in the `plan-overlay` call. Badges deep-link (canon badge → `quality-canon` filtered to the rule; thread badge → `quality-promises` filtered; drift badge → the arc drawer's Conformance tab). Counts roll up onto collapsed runs/arcs. **The *mechanics* of drift/staleness computation are `26`'s** — the Hub consumes refs and counts, it never computes conformance. | `21` classified canon as a lens reached from a badge; threads as a Quality duplicate — the Hub adds the *debt overlay*, not a threads panel (no reopening of `21`'s #18 verdict). **Transport adjudication (integration 2026-07-10, revised):** `26`'s IX-14 route is the ONE staleness contract for every surface (`26`'s GUI table: "no surface computes its own staleness"), so the Hub consumes it directly rather than duplicating the block into `plan-overlay` — one computation, one route, one consumer contract; the cold-open budget rises to ≤ 5 (PH9) to carry it. `plan-overlay` never carries drift. |
| **PH19** | **Lockfile chips.** `motif_application` chips hang on scene/chapter nodes (`outline_node_id`) and on arc lanes (`structure_node_id`, `23`). A chip shows the motif title + pinned `motif_version`; when the registry's live version is newer, a small "pin ⋯ vN→vM" indicator appears — **informational only** (DA-5: the lockfile pins; drift is a fact, not an error). Chip click → motif lens (reusing `MotifDetailDrawer`/`ChapterMotifBindings`); bind/unbind from the drawer via the **existing** `composition_motif_bind`/`_unbind` (undo via `undo_token`, F-H4/F-H5). Roster-binding chips on an arc's drawer resolve via `roster_bindings` + the entity-names map (F-H9). | The lockfile view is the piece of the package model the old UI never showed. Everything needed already exists; the Hub only renders it in place. |
| **PH20** | **Every canvas mutation maps to the Interactions table (§Interactions), OCC'd and undoable.** GUI interactions call the **REST mirrors** of the same repo methods (OutlineTree precedent, F-H3); the MCP tools of `23` BA11 are the agent's equivalent surface — one repo method, two front doors. Every write is OCC'd on the node `version`, transport-precise: **the MCP tools take an `expected_version` arg (`23` BA11); the REST mirrors reuse the existing `If-Match: <version>` header convention (F-H3)** — one OCC concept, one name per surface, never a second convention on either (DA-10). 412 → reload node + toast (SceneRail recovery). Tier-A-shaped results surface undo toasts via the `_meta.undo_hint` pattern. | F-H3/F-H4. Also resolves `23`'s "writes stay MCP-first" ambiguity for the GUI case — see OQ-3. |
| **PH21** | **Work-less / imported books:** the Hub renders the spec if **any** `structure_node`/`outline_node` rows exist for the book. Empty spec + non-empty manuscript → the empty state offers exactly two CTAs: **"Extract the plan from the manuscript"** (the decompiler — `22` SC6 `materialize-scenes`, then `composition_arc_import_analyze` for arc-level structure) and **"Plan from scratch"** (opens the `planner` PlanForge panel; the link step is `27`). The Hub **never** synthesizes a fake graph from chapters or `parts` — inferring structure is the decompiler's *explicit* job (DA-12's spirit). Chapters that exist in the manuscript but not in the spec surface as a collapsed **"Unplanned chapters" tray** fed by the overlay's coverage diff — drift made visible, not auto-planned. **Transport caveat (OQ-9):** as specced today, `materialize-scenes` is an internal-token route (`22` B4) and `composition_arc_import_analyze` is an MCP tool — a human GUI can call neither, so the extract CTA ships only with OQ-9's /v1 trigger; until that lands it renders disabled with a "coming" tooltip (PH7's visible-fallback), never a dead button. | BPS-1 removed the Work gate; SC6 named the decompiler precisely so this empty state has a truthful verb. Silent auto-planning would be `silent-success` inverted: work done that nobody asked for. |
| **PH22** | **Timeline and worldmap are axis re-layouts of the SAME loaded node set** (a toolbar view-switch, `21` 2c — not panels, not capability swaps). Selection, drawer state, expansion state, and the problems overlay survive a mode switch. Data contracts locked here (§View modes); visual treatment ✅ **ratified P-10 (PO 2026-07-10): v1 ships narrative mode only** — timeline/worldmap each ship in a later phase, buttons visible but disabled. | `21`'s classification stands; recon problem 3 demands state preservation be a rule, not an accident. DOCK-8 note: a view-mode switch re-lays one capability's data on another axis — it is NOT the GlossaryTab unrelated-capability page swap. |
| **PH23** | **Badge economy: one ring, capped chips, everything else in the drawer.** A node shows at most **one** status ring by fixed precedence: `canon-issue` > `conformance-drift` > `anchor-lost` > `ai-pending` (Phase 4); remaining problems appear as a count chip. Chips cap at 3 cast + 2 motif + `+N` overflow. `tracks` are **not** painted per node — they render as the lane legend + the arc drawer's Structure section; per-node track paint returns as a PO-reviewable enhancement only if users ask. | Recon problem 2: 4–5 status vocabularies at 118px is unreadable without a precedence law. Fixed order is testable; "designer's choice per node" is not. |
| **PH24** | **Compliance package.** Catalog row `plan-hub` (category `editor`, i18n `panels.plan-hub.*`); joins the `ui_open_studio_panel` enum + contract regen (DOCK-6); params `{focusNodeRef?: {kind:'structure'\|'outline', id}, view?}` in via F1 (DOCK-7); outbound via `resolveStudioLink`/`openPanel`/`focusManuscriptUnit` — zero `navigate()`. Bus: publishes `planHub.selection` snapshots; subscribes the editor's active-chapter signal for a "you are here" highlight (verify the editor publishes it; add if absent — task H2.6). Dialogs via `FormDialog`/`ConfirmDialog` (DOCK-9). Layout/expansion state is panel-local (per-device, Tier-1); selection is bus; domain data is TanStack Query (Tier-5) — no new hoist needed since drawer edits commit per-field. | DOCK-1..11 applied; the catalog precedents (`quality` hub, `json-editor` singleton) are cited in F-H8. |
| **PH25** | **The Plan navigator is an Activity Bar rail, not a dock panel.** Same host surface as the Manuscript Navigator (not in `catalog.ts`, not in the agent enum), second Activity Bar tab. It reuses the *same* keyset children fetch + `composition_arc_list`, only the row decoration differs (cast chip stacks, motif dots, beat tag, canon warn, footer stat strip). **Row click focuses the node on the Hub canvas (opening `plan-hub` if closed) — never the Editor** — the Explorer-vs-Source-Control click contract from the draft survives verbatim. | The rail and the canvas are two densities of one dataset; giving the rail the editor-focus click would overload Manuscript Navigator's contract and make the two rails ambiguous. |
| **PH26** | **Cast badges resolve from the glossary book-wide entity-names map.** `GET /books/{bookId}/entity-names` (F-H9) via one cached TanStack query; canvas chips and drawer roster rows read the map. **The endpoint's real contract today is narrower than the Hub needs (F-H9: active-only, named-only, silent `LIMIT 500`), so H1.6 widens it:** keyset pagination past 500 (the client follows the cursor until exhausted — still ONE logical load, cached once), a `truncated` flag on every page (OUT-5: a cap is reported, never silent), and the status filter widened to all non-deleted entities (a `pov_entity_id`/roster ref that exists must resolve, whatever its status). The FE distinguishes the two absence cases: map complete + id absent → **"missing entity"** unresolved chip deep-linking to the glossary panel; map truncated + id absent → one per-id lazy resolve before declaring it unresolved. Never a silent blank. | The 10k-chapter requirement makes >500 entities a normal book, not an edge case. This is the `mocked-client-hides-server-side-default-filters` bug class exactly — this spec's own first draft repeated it by asserting the endpoint had no filters. |

---

## The canvas data contract

### Read surfaces

| # | Call | Supplies | Shape notes |
|---|---|---|---|
| 1 | `composition_arc_list(book_id)` — `23` B1 (REST mirror `GET /v1/composition/books/{book_id}/arcs`) | The whole `structure_node` shell: every saga/arc/sub-arc | Per node: `{id, kind, parent_id, depth, rank, title, status, goal, summary, tracks, roster (keys only), roster_bindings, arc_template_id, template_version, version}` **plus the derived block `{span: {from_order,to_order}\|null, is_contiguous, chapter_count}`** — the Hub's requirement on B1's response (coordination note → OQ-2). One call; arcs are tens, not thousands. |
| 2 | `GET /v1/composition/books/{book_id}/outline/children` (the F-H1 route, re-keyed + extended) | One page of chapters (`structure_node_id=<arc>`) or scenes (`parent_id=<chapter>`) | Keyset `(rank, id)`, cursor codec unchanged, limit 1..200. New `detail=summary` (PH10): `{id, kind, parent_id, structure_node_id, chapter_id, title, status, version, story_order, rank, beat_role, tension, pov_entity_id, present_entity_ids[≤3], present_entity_count}`. |
| 3 | `GET /v1/composition/books/{book_id}/plan-overlay` (new, this spec) | The decorations layer | See below. |
| 4 | `GET /v1/composition/books/{book_id}/scene-links` (book-keyed list; today `list_by_project`) | All edges, one call (PH13) | `{id, from_node_id, to_node_id, kind, label}`. |
| 5 | `GET /v1/books/{book_id}/scenes` + the chapter spine (book-service, `22`) | The **actual-state** half (PH12) | Client-side join on `source_scene_id` / `chapter_id` — SC11. |
| 6 | `GET /v1/glossary/books/{book_id}/entity-names` (existing; contract widened by H1.6 — F-H9/PH26) | Badge name map (PH26) | Cached once per book; the client follows keyset pages until exhausted; every page carries `truncated`. |
| 7 | `GET /v1/composition/books/{book_id}/conformance/status` (`26` IX-14; MCP sibling `composition_conformance_status`) | Per-arc dirty badges + stale-chapter rollup (PH18) | `{arcs: [{structure_node_id, dirty, dirty_reasons, stale_chapters, computed_at, summary}], index: {stale_chapter_count}}` — `26`'s shape, consumed as-is. Fetched on open, re-fetched on focus; `never_run` arcs arrive `computed_at: null, dirty: true` and render as such, never defaulted. |

All composition routes gate `_book_or_deny` VIEW for reads, EDIT for writes (BPS-8). Read routes are GUI surfaces; [`28`](28_agent_native_studio.md) (authored) specs the agent-facing aggregates over the same repo methods — `composition_package_tree` and `composition_diagnostics` (AN-2/AN-4), which compose `26`'s conformance helper and share H1.3's coverage-diff helper (28 OQ-4 resolution) rather than duplicating either.

### The new keyset index (shape specced here; **lands via `25`'s migration ordering**)

```sql
-- Plan Hub v2 (24 PH11): chapters-under-arc window. After 23's migration, chapter nodes have
-- parent_id NULL and attach via structure_node_id — the existing children keyset cannot serve
-- this axis. Same collation discipline as idx_outline_node_children_keyset (migrate.py:188).
-- QUERY-SIDE REQUIREMENT: a partial index matches only when the query implies its predicate —
-- Postgres does NOT infer `kind = 'chapter'` from the outline_structure_kind CHECK. The H1.1
-- structure-axis query MUST repeat `AND kind = 'chapter'` (and `AND NOT is_archived`) VERBATIM,
-- or the 10k-chapter window silently degrades to scan+sort. Asserted by an EXPLAIN test in H8.1
-- (lesson family: postgres-partial-index-on-conflict-predicate-must-match).
CREATE INDEX IF NOT EXISTS idx_outline_node_structure_keyset
  ON outline_node(structure_node_id, rank COLLATE "C", id)
  WHERE NOT is_archived AND kind = 'chapter';
```

### `plan-overlay` response (bounded, partiality-flagged)

```jsonc
{
  "problems": {                       // PH18 — canon + thread-debt refs + counts ONLY;
                                      // drift/staleness rides read surface #7 (26 IX-14), never here
    "by_node": {                      // key: outline_node.id OR structure_node.id
      "<uuid>": { "canon": 2, "threads_open": 3,
                   "refs": [{ "kind": "canon", "id": "<rule_id>", "line": "Ha cannot fly before ch 40" }] }
    },
    "refs_capped": true               // OUT-5 spirit: caps are reported, never silent
  },
  "tension_rollup": [                 // PH17 — per-chapter derived aggregate for unloaded regions
    { "chapter_node_id": "<uuid>", "story_order": 12, "tension": 65 }
  ],
  "motif_chips": [                    // PH19 — book-wide lockfile chips (kills the F-H5 N+1)
    { "node_ref": "<uuid>", "motif_id": "<uuid>", "title": "The red thread",
      "pinned_version": 3, "live_version": 4 }
  ],
  "unplanned_chapters": [             // PH21 tray — manuscript chapters with no spec node
    { "chapter_id": "<uuid>", "title": "Chương 41", "sort_order": 41 }
  ]
}
```

### Load sequence (cold open, 10k-chapter book)

1. Arc shell (call 1) + overlay (3) + edges (4) + entity names (6, first page — remaining pages trail after paint, PH26) + conformance status (7) in parallel — five small responses, the PH9 budget; the whole lane structure, every rollup, every problem count and dirty badge render **before any chapter loads**.
2. The initial camera's arcs (P-11 ✅: from an editing context, the active chapter's arc; else whole-book collapsed) expand → chapter windows (call 2) page in keyset order; scenes page in only for expanded chapters.
3. Actual-state joins (5) fetch lazily per loaded window.
4. Everything off-viewport stays a rollup card. React Flow renders only visible elements; our windows bound what exists at all.

---

## Package re-map — all 29 items, package path + Hub seat (PH15)

`21`'s categories, re-addressed onto [`00A` §2](00A_BOOK_PACKAGE_STRUCTURE.md). ✱ = seat changed vs `21`'s assumption.

| # (`21`) | Item | Package path | Hub seat |
|---|---|---|---|
| — ✱ | **Story arc / saga (`structure_node`)** | `spec/structure/` | **Core** — the lanes/super-nodes themselves (`23:362`). The seat `21` couldn't have (F8: the root didn't exist). |
| 26 | Outline navigator | `spec/outline/` | **Core** — chapter/scene cards; CRUD plumbing reused from OutlineTree, type contract replaced (PH3 amended). |
| 6 | Scene graph / what-if | `spec/links/` | **Core** — native edges (PH13); what-if stays a branch-preview mode on edges. |
| 5 | Beats | `spec/outline/` (`beat_role`) + `deps/` (`motif.beats`, `structure_template.beats`) | **Node facet** — drawer Beats tab; beat-dot badge on canvas (BPS-4 closed PH5). |
| 13 | Canon-as-of-chapter | `tests/` (`canon_rule`) | **Node facet** — drawer "Canon here" tab. |
| 14 | References / lore pins | `spec/divergence/` (`reference_source`) | **Node facet** — drawer tab. |
| 17 | Critic | `.runs/` (`generation_correction` + critic results) | **Node facet** — drawer tab. |
| 7 | Cast | glossary (outside pkg); bindings in `spec/` (`pov`, `present_entity_ids`, `roster_bindings`) | **Cross-ref lens** — cast chip → lens (PH26 resolve). |
| 8 | Relationship map | glossary-derived | **Cross-ref lens** — from a cast chip's lens. |
| 10 | Character arc | entity lens (`composition_character_arc_*`, DA-10) | **Cross-ref lens** — confirmed correct in `21`, stays. |
| 23 | Motif library | `deps/` (`motif`) | **Cross-ref lens** — motif chip → `MotifDetailDrawer` lens. |
| 16 | Canon rules | `tests/` (`canon_rule`) | **Cross-ref lens** — canon badge deep-links to the fired rule (PH18). |
| — ✱ | **Lockfile pins (`motif_application`)** | `book.lock` | **Core decoration** — chips per node + lane (PH19). `21` folded this under #23; the package model splits registry (lens) from pin (chip). |
| 9 | Timeline | `spec/outline/` (`story_time`, SC4) | **View mode** (PH22). |
| 11 | Worldmap | `spec/outline/` (`location_entity_id`, SC4) | **View mode** (PH22). |
| 1 | Compose | `.runs/` (`generation_job`) | **Action** — node rail. |
| 3 | Assemble | `.runs/` | **Action** — chapter node rail. |
| 4 | Planner (template decompose) | `deps/` (`structure_template`) → `.runs/` (`decompose_commit`) | **Action** — Hub toolbar / arc rail. |
| 21 | Polish (self-heal) | `.runs/` | **Action** — node rail. |
| 24 | Conformance | `tests/` runner (`arc_conformance`) | **Action** — arc rail, **takes `arc_id`** (BA4 ✱); results feed PH18. |
| — | `arc_suggest` | `deps/`→`spec/` proposal | **Action** — Hub toolbar ("Suggest an arc"). |
| — | `motif_suggest_for_chapter` | `book.lock` proposal | **Action** — chapter node rail. |
| 2 | Cowriter | — | **Not-a-Hub** — Compose chat (unchanged). |
| 12 | Grounding | `spec/grounding/` | **Not-a-Hub** — Agent Context Rack owns the surface; the drawer's References tab links to it. |
| 15 | Style / voice | `spec/style/` | **Not-a-Hub** — steering/book-settings home. |
| 18 | Threads panel | `tests/` (`narrative_thread`) | **Not-a-Hub as a panel** (duplicate of `quality-promises`) — but the *debt* joins the Hub as the PH18 overlay ✱. |
| 19 | Progress | outside pkg (per-user) | **Not-a-Hub** — unchanged. |
| 20 | Correction stats | `.runs/` (`generation_correction`) | **Not-a-Hub** — Quality hub. |
| 22 | Flywheel | KG (outside pkg) | **Not-a-Hub** — knowledge panels. |
| 25 | Work settings | `book.manifest` (`composition_work.settings`) | **Not-a-Hub** — book-settings panel. |
| — | `arc_import_analyze` | `.runs/` (import) | **Not-a-Hub as a toolbar item** — but it IS the PH21 empty-state decompiler CTA ✱. |

---

## Interactions → mutations (PH20)

Canonical semantics named by the MCP tool (`23` BA11 / existing); the GUI calls the REST mirror of the same repo method (F-H3). Every write: OCC on the node `version` (MCP `expected_version` arg / REST `If-Match` header — PH20) → 412 reload+toast; undo per F-H4.

| Interaction | Mutation | OCC / undo |
|---|---|---|
| Drag chapter card into another lane | `composition_arc_assign_chapters` (sets `outline_node.structure_node_id`) | version on each node; undo = inverse assign (undo_hint) |
| Drag arc band (reorder / nest under saga or arc) | `composition_arc_move` (reparent + reorder; subtree depth recompute, BA9) | arc `version`; undo = inverse move |
| Drag chapter within a lane / scene within a chapter | `composition_outline_node_move` (`23` B3; REST `reorder` exists — F-H3) | node `version`; undo = inverse move |
| Drag scene to another chapter | `composition_outline_node_move` (reparent) | ″ |
| Inline rename / status change (node) | `composition_outline_node_update` (status `Literal`, SC8/F6) | `expected_version`; undo = prior value patch |
| Inline rename / status / tracks / roster edit (arc, in drawer) | `composition_arc_update` | ″ |
| Add chapter / scene (canvas "+") | `composition_outline_node_create` (`kind: Literal['chapter','scene']`, BPS-4) | — ; undo = archive |
| Add arc / saga (lane "+") | `composition_arc_create` | — ; undo = `_delete` (soft) |
| Archive / restore node or arc | `_delete` / `_restore` (soft) | undo = the paired inverse |
| Draw edge scene→scene | `composition_scene_link_create` — `kind` is closed-set (`'setup_payoff'\|'custom'`) but the shipped tool takes a free `str` guarded only by the DB CHECK ([`server.py:919`](../../../services/composition-service/app/mcp/server.py#L919), [`migrate.py:198`](../../../services/composition-service/app/db/migrate.py#L198)); H5 adds the `Literal` + `CLOSED_SET_ARGS` entry (IN-2) | undo = `composition_scene_link_delete` |
| Delete edge | `composition_scene_link_delete` | `undo_hint: None` (recreate manually — matches today, [`server.py:986`](../../../services/composition-service/app/mcp/server.py#L986)) |
| Bind motif chip (drawer) | `composition_motif_bind` | undo = `composition_motif_unbind(undo_token)` — verified inverse |
| Unbind motif chip | `composition_motif_unbind` | per existing tool |
| Edit `tension` on a sparkline-focused scene | `composition_outline_node_update` (range-validated at schema, SC8) | `expected_version` |
| ⚓ Re-anchor (index-only scene) | the existing re-anchor action (`22` F6/BPS-13) | — |
| Run conformance (arc rail) | `composition_conformance_run(scope='arc', arc_id)` (BA4) | read-only run |
| Apply template curve (arc drawer, Provenance) | `composition_arc_apply` | `23` A5 semantics (idempotent via commit primitives) |
| Compose / Assemble / Polish rail buttons | existing engines; priced ops keep the propose→confirm token pattern (`CostConfirmCard` reuse) | per existing flows |
| "Suggest an arc" / "Suggest motifs" | `composition_arc_suggest` / `composition_motif_suggest_for_chapter` | read-only proposals; accepting one routes through the create/bind rows above |

---

## View modes — data contracts only (PH22; visuals per P-10 ✅ — v1 is narrative-only)

| Mode | Axis field | Contract | Unplottable nodes |
|---|---|---|---|
| **Narrative** (default, v1) | `story_order` × lanes | PH14 layout | n/a |
| **Timeline** | `story_time` (SC4, free-text) | Nodes keep `story_order` as the *sort* (free-text `story_time` is not reliably orderable); `story_time` renders as axis captions/groups. The knowledge-graph event timeline stays in `kg-timeline` — this mode re-lays **spec nodes**, nothing else. | "Undated" tray — visible, never dropped |
| **Worldmap** | `location_entity_id` (SC4) | Nodes cluster by location (names via PH26 map); edges = scene transitions between clusters. | "Unlocated" tray |

Mode switches preserve selection, drawer, expansion, overlay toggles (PH22). Each mode is a renderer over the already-loaded window set — no mode triggers a reload.

---

## Panel registration, i18n, tests (PH24/PH25)

- **Catalog** ([`catalog.ts`](../../../frontend/src/features/studio/panels/catalog.ts)): `{ id: 'plan-hub', component: PlanHubPanel, titleKey: 'panels.plan-hub.title', descKey: 'panels.plan-hub.desc', category: 'editor', guideBodyKey: 'panels.plan-hub.guideBody', tourAnchor: 'studio-plan-hub-panel' }`.
- **Agent enum:** add `'plan-hub'` to chat-service `ui_open_studio_panel` `panel_id` enum → `WRITE_FRONTEND_CONTRACT=1 pytest` regen → `panelCatalogContract.test.ts` green. The navigator rail is NOT a panel — no catalog row, no enum entry (PH25).
- **i18n** (`i18n/locales/*/studio.json`): `panels.plan-hub.{title,desc,guideBody}` · `planHub.legend.{saga,arc,chapter,scene,motif,canonIssue,drift,anchorLost}` · `planHub.toolbar.{search,askAi,fit,problems,viewNarrative,viewTimeline,viewWorldmap}` · `planHub.node.{notYetWritten,anchorLost,unplannedTray,undatedTray,unlocatedTray,collapsedRun}` · `planHub.drawer.{overview,beats,canonHere,references,critic,openInEditor,askAiFix,structure,roster,chapters,conformance,provenance}` · `planHub.empty.{title,extractCta,planCta}` · `planNav.{title,jump,stats}`.
- **Tests:** `dockablePanelHygiene` (DOCK-7/9 greps) picks the panel up automatically; layout unit tests (PH14 determinism: insert → no reshuffle; non-contiguous arc → two bands); union-state tests (PH12 three shapes); badge-precedence test (PH23); live browser smoke per DOCK-11/Part-3 (agent opens `plan-hub` via `ui_open_studio_panel` → canvas renders a seeded book → drag chapter across lanes → DB row's `structure_node_id` changed → overlay badge updates).

---

## Task breakdown

**Prerequisites (not this spec's work):** `23` Phases 0/A/B (`structure_node`, re-key, arc tools) via `25`'s migration ordering · `22` Phase A (book-service scene routes) for the actual-state join. The Hub builds against those surfaces; H1 can start once `23` A1–A3 exist in a branch.

### Phase H1 — read surfaces (BE — composition, plus one glossary task)
| # | Task | File(s) |
|---|---|---|
| H1.1 | Children route: `book_id` keying, `structure_node_id` axis param, `detail=summary` projection (PH10). The structure-axis query repeats `AND kind = 'chapter'` verbatim so the partial index matches (§index note) | `app/routers/outline.py`, `app/db/repositories/outline.py` |
| H1.2 | `idx_outline_node_structure_keyset` (shape §above; **lands in `25`'s ordering**) | `app/db/migrate.py` via `25` |
| H1.3 | `GET /books/{book_id}/plan-overlay` — canon + thread-debt problems (drift/staleness is NOT in this payload — it rides `26` IX-14's route, read surface #7 — PH18/OQ-8), tension rollup, motif chips, unplanned tray | `app/routers/plan_overlay.py` (new), repos |
| H1.4 | Book-keyed `scene-links` list | `app/routers/outline.py` |
| H1.5 | Coordination: `composition_arc_list` derived block (span/contiguity/chapter_count) — implemented under `23` B1, asserted by an H1 contract test here | `app/mcp/server.py` (23's file), `tests/` |
| H1.6 | Glossary `entity-names` contract widened for PH26 (F-H9): keyset pagination past the current `LIMIT 500`, a `truncated` flag on every page, status filter widened to all non-deleted entities. The one H1 task outside composition-service | `services/glossary-service/internal/api/entity_handler.go`, `frontend/src/features/glossary/api.ts` |

### Phase H2 — canvas core (FE)
| # | Task | File(s) |
|---|---|---|
| H2.1 | `plan-hub` panel shell: catalog row, enum + contract regen, i18n, self-title | `features/studio/panels/PlanHubPanel.tsx`, `catalog.ts`, chat-service `frontend_tools.py`, locales |
| H2.2 | Deterministic lane layout engine (PH14) — pure function `(shell, windows, collapse) → positions`, unit-tested headless | `features/plan-hub/layout/laneLayout.ts` |
| H2.3 | Keyset window loader + collapsed-run rollup cards (PH11) | `features/plan-hub/hooks/usePlanWindows.ts` |
| H2.4 | Node/edge React Flow components (chapter/scene cards, lane bands, stub edges) | `features/plan-hub/components/` |
| H2.5 | Two-truths client join (PH12) + three node states | `features/plan-hub/hooks/useActualState.ts` |
| H2.6 | Bus wiring: selection publish; editor active-chapter subscribe (verify the editor publishes it; add the publication if absent) | `PlanHubPanel.tsx`, editor feature |

### Phase H3 — drawer
| # | Task | File(s) |
|---|---|---|
| H3.1 | Drawer shell + arc variant embedding `23` C3's arc-inspector sections (DOCK-2) | `features/plan-hub/components/PlanDrawer.tsx` |
| H3.2 | Chapter/scene facet tabs (Overview/Beats/Canon-here/References/Critic) reusing the legacy components' hooks per `21` 2a | ″ |
| H3.3 | Per-node full fetch on selection (`composition_get_outline_node` REST mirror) | `features/plan-hub/api.ts` |

### Phase H4 — decorations
| # | Task |
|---|---|
| H4.1 | Problems layer: overlay (canon/threads) + the IX-14 conformance-status consumption (dirty badges + stale rollup, read surface #7) + badge precedence (PH18/PH23) + deep links via `resolveStudioLink` |
| H4.2 | Motif chips + stale-pin indicator + bind/unbind drawer actions (PH19) |
| H4.3 | Pacing sparkline: window tension + rollup fallback; point-click → scene focus (PH17) |
| H4.4 | Cast chips via entity-names map (PH26) |

### Phase H5 — interactions (PH20 table, wired one row at a time, each with its OCC/undo test)

The edge-draw row carries one BE one-liner found during this spec's investigation: `composition_scene_link_create.kind` ships today as a free `str` (default `"setup_payoff"`) with the closed set (`'setup_payoff','custom'`) enforced only by the DB CHECK — the exact mcp-tool-io IN-2 violation class (`panel_id` bug). H5's edge-draw task makes it `kind: Literal['setup_payoff','custom']` + a `CLOSED_SET_ARGS` registration (`app/mcp/server.py`; mirrors `23` B3's Literal work on the outline-node tools).

### Phase H6 — Plan navigator rail (PH25) — Activity Bar tab, shared fetch, hub-focus click contract

### Phase H7 — view modes (PH22) — deferred per P-10 ✅ (v1 narrative-only); timeline then worldmap, each its own later cycle

### Phase H8 — verification
| # | Task |
|---|---|
| H8.1 | 10k-chapter fixture perf pass: cold open ≤ 5 requests before first paint of the lane structure (the PH9 budget); scroll paging stays keyset (no OFFSET anywhere); EXPLAIN asserts the structure-axis children query uses `idx_outline_node_structure_keyset` — i.e. the `kind = 'chapter'` predicate is repeated (§index note) |
| H8.2 | **Live browser smoke** (DOCK-11 / mcp-tool-io Part 3): agent `ui_open_studio_panel('plan-hub')` → drag → DB assert → overlay refresh. Per `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`. |
| H8.3 | Amendment check: `21`'s amendment block present; `00_OVERVIEW.md` row 21 points here |

**Ordering.** H1 → H2 → {H3, H4, H5 in parallel on disjoint files, per `fanout-independent-slices-parallel-build-serial-integrate`} → H6 any time after H2 → H7 last. One serial VERIFY per milestone.

---

## Open questions

| # | Question | Disposition |
|---|---|---|
| OQ-1 | **Timeline/worldmap visual treatment** (mandated PO-DECIDE). | ✅ **RATIFIED (PO 2026-07-10)** — decision: v1 ships narrative mode only; the two mode buttons render disabled with a "coming" tooltip (visible, honest — PH7's spirit). When built: timeline = per-track swimlanes with `story_time` captions; worldmap = location clusters with transition edges. Data contracts are locked either way (PH22). |
| OQ-2 | `composition_arc_list`'s response shape is `23` B1's to define — the Hub needs the derived block (span/contiguity/chapter_count) and roster keys in it. | **Decided (coordination):** the derived block is a stated requirement on B1, asserted by H1.5's contract test. If `23`'s build puts derivations in a sibling call instead, the Hub consumes that — the *requirement* (shell + rollups ≤ 2 calls) is what's locked, per PH9. |
| OQ-3 | `23`'s earlier draft read *"writes stay MCP-first"* with no GUI carve-out — but a human GUI cannot call MCP tools, and every existing panel writes REST (F-H3: `createNode`/`patchNode`/`reorderNode`). Did the Hub's drag-and-drop have a write transport? | **RESOLVED —** [`23:356`](23_book_architecture.md) (amended at integration 2026-07-10) commits Phase B to shipping **REST write mirrors over the same repo methods** — *"one repo method, two front doors"* — citing this spec's PH20/OQ-3 by name, and scopes MCP-first to *agent* logic (CLAUDE.md's invariant is about agent capabilities, not human GUIs). The Hub's GUI writes go through those mirrors (PH20). Nothing remains for the integrator here. |
| OQ-4 | The children route's *"omitted `parent_id` → top-level arcs"* contract silently inverts after `23`'s migration (chapters become `parent_id NULL` roots) — it would return every chapter in the book. Affects the Manuscript Navigator too, not just the Hub. | **Decided (H1.1) + flagged:** the route gains the `structure_node_id` axis and its "omitted" semantics must be re-defined at re-key time. **`25` must sequence this route flip with migration Phase 1/4** — recorded for the integrator; neither `23`'s migration table nor `25` currently names it. |
| OQ-5 | Initial camera on open — whole-book fit vs the working scope? | ✅ **RATIFIED (PO 2026-07-10)** — decision: when opened from an editing context, focus + expand the arc containing the editor's active chapter (the `m1b-working-scope-boost` lesson applied to the canvas — the author's working set is where attention goes); otherwise fit-whole-book with all arcs collapsed. |
| OQ-6 | Does OutlineTree's indented-list view survive as a toggle inside the Hub? (`21` explicitly deferred this to ask the user.) | ✅ **RATIFIED (PO 2026-07-10)** — decision: **no toggle in v1** — the Plan navigator rail (PH25) *is* the list rendering of the same data; a third in-panel list duplicates it. `OutlineTree.tsx` stays where it is until its retirement cycle. |
| OQ-7 | What does the toolbar's primary **"Ask AI about this plan"** button do in v1? | ✅ **RATIFIED (PO 2026-07-10)** — decision: opens the Compose chat with the current selection's ref pre-filled as context (existing surface, zero new contract). The dedicated plan-agent affordance (highlight-my-pending-edit on the canvas) remains Phase 4 / PH8 — it needs the `resource_ref` convention, which [`28`](28_agent_native_studio.md) (authored 2026-07-10) does **not** yet spec — that convention remains open contract work gating Phase 4 — and after `27` links PlanForge output the button finally has a real spec object to talk about (BPS-17/18). |
| OQ-8 | Where does the Hub's drift/staleness signal come from before `26` ships? | **Decided (revised at integration 2026-07-10):** drift/staleness never rides `plan-overlay` at all — the Hub reads it from `26` IX-14's `GET /conformance/status` (read surface #7, PH18). Until `26` ships, that route does not exist and the FE renders **no drift badge** — absent ≠ zero (an honest "not computed" per OUT-5's spirit), never a green-looking 0. Canon + thread-debt sources ship in H1.3 unconditionally (both are plain queries today, F-H6). |
| OQ-9 | PH21's "Extract the plan from the manuscript" CTA is wired to `materialize-scenes` — specced as `POST /internal/books/{book_id}/materialize-scenes` behind the internal service token (`22` B4) — followed by `composition_arc_import_analyze`, an MCP tool. A human GUI can call neither (the gateway exposes /v1 only; MCP is the agent's surface) — the same gap class OQ-3 names for arc writes, here on the decompiler. | **Decided, flagged to the integrator (mirrors OQ-3):** the CTA needs a user-facing /v1 trigger. Recommended shape: `22` B4 — which builds the internal route — also ships an EDIT-gated (BPS-8) `/v1` mirror of `materialize-scenes`; the arc-level analysis step is LLM work and reuses the existing propose→confirm token pattern (`CostConfirmCard`, per `cost-gated-mcp-tool-confirm-runs-engine`) rather than a bare priced endpoint. `25` must sequence both before H2's empty state ships. Until the trigger exists the CTA renders disabled with a "coming" tooltip (PH21) — visible-fallback, never a dead button. |

---

## Risks

| Risk | Mitigation (lesson) |
|---|---|
| The lane layout drifts into a second implementation of "where does a node go" duplicated between canvas and navigator | PH14's layout is ONE pure function consumed by both; the navigator renders order, not positions (`css-var-duplicated-across-two-consumers-drifts`) |
| The Hub re-introduces a stored pacing curve as "just some FE state" | PH17: no arc-level edit affordance exists to bind state to; derivation tests live in `23` D4 (`context-budget-law` discipline: assert the EFFECT) |
| Whole-tree loads sneak back in via "just this once" (search, fit-to-view) | PH9/PH11: fit-to-view uses the arc shell + rollups only; the jump box reuses the existing `outline/search` route (title-only) then focuses via keyset window — asserted in H8.1 (`extraction-over-extracts-4x-and-eager-wholebook`) |
| Client-side two-truths join shows stale actual-state after an edit in the Editor | The bus active-chapter signal (H2.6) invalidates the affected window's actual-state query; verify by the live smoke, not unit mocks (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`) |
| A collapsed-run rollup lies (counts ≠ loaded reality) after mutations | Rollups re-fetch on any mutation touching their subtree (TanStack invalidation keyed by arc id); a mismatch is a bug, not eventual consistency (`silent-success-is-a-bug-not-environment`) |
| Drag-drop mutation lands but the canvas shows the old position (fire-and-forget) | Every PH20 row awaits the server response and re-renders from it; optimistic moves roll back on 412 (`cross-window-fire-and-forget-relay-needs-ack`) |
| The `plan-overlay` aggregate grows unbounded refs on a pathological book | Caps + `refs_capped` flag (OUT-5); counts stay exact, refs page in via the drawer |
| Panel forks motif/arc components instead of reusing (deadline pressure) | DOCK-2 + PH16/PH19 name the exact reuse targets (`ArcTimelineEditor`, `MotifDetailDrawer`, `ChapterMotifBindings`, arc-inspector); a fork is a review-red (`dock2-fork-risk-in-parallel-panel-fanout`) |
| Live smoke passes against stale images | Rebuild before H8.2 (`live-smoke-rebuild-stale-images-first`) |
| The route-semantics flip (OQ-4) ships out of order with the migration and the Manuscript Navigator breaks | Flagged to `25` with a named sequencing requirement; H1.1 carries a test that fails if `parent_id`-omitted returns chapter-kind rows (`new-cross-service-contract-needs-consumer-live-smoke`) |
