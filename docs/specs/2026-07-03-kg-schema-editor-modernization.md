# KG schema editor modernization — pickers + visual canvas + AI-assist (2026-07-03)

**Origin:** user feedback on the Track-A schema editor — *"cảm giác như nó là mấy cái
text box thông thường để nhập liệu"*. It works (full CRUD, theme-correct, live-proven)
but it's forms-over-fields; a KG schema is a **graph type-system** and deserves a direct,
visual, intelligent editor. User: **"lên spec làm hết đi"** — spec all three, then build.

This SPEC frames three milestones on top of the shipped Track A (A1–A4). Track A stays
the data/contract substrate; this is the UX layer over it.

## Locked principles

1. **Reuse, don't rebuild.** The visual canvas reuses the existing SVG graph primitive
   `features/composition/components/GraphCanvas` (+ `GraphEntityNode`, `RelationEdge`) —
   the same canvas `ProjectGraphView` renders the DATA graph with. No new graph library.
2. **Theme-first.** Every new surface uses theme tokens (`bg-input`, `text-primary-foreground`,
   `bg-card`, `border`, `text-muted-foreground`) — no bare inputs / hardcoded colors (the
   defect just fixed in `d9bcfab09`).
3. **MCP-first for agentic bits (ENFORCED invariant).** Any capability where an **LLM
   proposes a schema** (M3b generate-from-description) MUST be an **MCP tool on
   knowledge-service through ai-gateway**, model resolved via provider-registry — never a
   bespoke raw-prompt HTTP endpoint. Deterministic aggregation (M3a infer-from-graph) is
   NOT agentic → a plain internal read is fine.
4. **Additive over Track A.** All three reuse the A1–A4 mutation routes + the A4 usage
   count. No schema/DB migration expected (validation/canvas/AI are read+existing-write).
5. **`code` stays immutable** (Track A EC-A6). Canvas/pickers edit attributes + wiring,
   never rename a code (rename = delete + create).

---

## M1 — Typed pickers + inline intelligence (cheapest, kills the "text box" feel)

Replace free-text fields with **typed, validated controls** and surface the schema's own
knowledge inline. Enhances the existing `SchemaWorkbench` + row/add components — no new page.

- **Kind pickers (not comma-strings).** An edge type's `source_node_kinds` / `target_node_kinds`
  become **multiselect chips** chosen from the node kinds that ACTUALLY exist in this schema
  (+ a "＋ create kind X" affordance when you want a new one). Kills the "typed a kind that
  doesn't exist" class of error. Same for any kind-referencing field.
- **Toggles, not selects, where binary.** `strength` (required/optional), `cardinality`
  (single/multi), `temporal`, `closed` render as segmented toggles/switches with a one-line
  explanation of what each does.
- **Live validation.** As you edit: duplicate-code check (before submit, not a 409 surprise);
  "edge references node-kind `X` that isn't defined — create it?"; empty-required warnings.
  Surfaced inline (not just a toast).
- **Inline usage badges.** Reuse the A4 `GET …/schema/usage` — each edge type / node kind row
  shows "· used by N" so the author sees impact before editing/deleting (batch the calls, or
  a single `…/schema/usage-summary` endpoint returning counts for all components at once —
  see A-decision).
- **`code` auto-slug from label** on the add-forms (mirrors create-blank's `_slugify_code`),
  editable, with the uniqueness check.
- **Empty-state coaching.** A brand-new blank schema shows a 2-line "start by adding a node
  kind (a character, a place…), then connect them with an edge type" instead of empty tables.

**Deliverables:** `KindMultiSelect` component; validation hooks in `useGraphSchema` /
local; a `schema/usage-summary` read (optional perf); enhanced Add*/Row components. FE-only
except the optional usage-summary endpoint.

---

## M2 — Visual type-graph canvas (the flagship "modern" leap)

A canvas where the schema IS the picture: **node kinds are draggable nodes, edge types are
labeled arrows between them.** Reuses `GraphCanvas` (SVG, node-drag, zoomable).

- **Render the type graph.** Map the schema tree → canvas: one node per node-kind; one arrow
  per edge-type drawn from each of its `source_node_kinds` to each `target_node_kinds`
  (an edge-type with no kinds sits as a floating labeled arrow / a "loose types" tray).
  Fact-types + vocab-sets live in a side rail (they aren't node↔node relations).
- **Draw-to-create (the killer interaction).** Drag from node-kind A's handle to node-kind B
  → opens a tiny inline "new edge type" popover (code+label, source/target pre-filled A→B) →
  `POST …/edge-types`. Add a node kind by clicking empty canvas → "new node kind" popover.
- **Direct manipulation edits.** Click a node/arrow → the M1 inspector (reused) in a side
  panel; drag re-parents an arrow's endpoint → PATCH `source/target_node_kinds`; delete via
  the arrow/node context action → the A4-guarded delete.
- **Layout + affordances.** Auto-layout on load (simple force/grid from GraphCanvas), manual
  drag persists per-user (localStorage, per-device UI state — allowed by the persistence
  rules); pan/zoom; a "fit" button; node-kind color by tier (system/user/project).
- **New canvas capability needed:** GraphCanvas today is READ-ONLY (ProjectGraphView never
  mutates). M2 adds an **edit layer**: connect-drag (A→B), empty-click-to-add, endpoint
  re-drag. Build this as an opt-in editable mode on a thin wrapper so ProjectGraphView stays
  read-only. This is the bulk of M2's effort.
- **Toggle with the form view.** A "Canvas / List" switch on the schema surface — the canvas
  is the default modern view; the M1 list stays for dense bulk editing + a11y fallback.

**Deliverables:** `SchemaCanvas` (editable wrapper over GraphCanvas), type-graph mapping,
connect/add/re-drag interactions + popovers, layout persistence, the Canvas/List toggle.
FE-only (reuses A1 mutation routes). Biggest slice → its own sub-track.

---

## M3 — AI-assisted authoring (the on-brand differentiator)

Two independent features; **M3a is cheap + not agentic, M3b is agentic → MCP tool.**

### M3a — Infer schema from the book's extracted graph (deterministic, no LLM)
The extraction pipeline already populated Neo4j with entities (`e.kind`) + relations
(`r.predicate`). Offer: **"Your book already has these kinds + relations — add them to the
schema?"**
- New read: aggregate DISTINCT `e.kind` (+ count) and `r.predicate` (+ count, + observed
  source/target kinds) for the project (Neo4j `GROUP BY`, mirrors the A4 `schema_usage`
  count pattern). `GET …/schema/observed`.
- FE: a review list (kind/edge · count · "already in schema?" ✓/＋) → user ticks → bulk
  `POST` the missing ones through the A1 add routes. Pre-fills source/target kinds from the
  OBSERVED endpoints of each predicate.
- Not agentic (pure aggregation) → plain internal read, no MCP.

### M3b — Generate schema from a description (agentic → MCP tool, ENFORCED)
**"Tả thế giới một câu → sinh node kinds + edges."**
- New **MCP tool on knowledge-service**: `kg_schema_propose` (name TBD) — takes a NL premise
  (+ optional genre) → the LLM proposes `{node_kinds[], edge_types[](source/target), fact_types[],
  vocab_sets[]}` as a STRUCTURED proposal (propose-pattern; nothing is written until the human
  confirms). Model resolved via provider-registry (user's chat model); no hardcoded model.
  Federated through ai-gateway like the other kg_* tools. LLM-client-first schema (enums for
  strength/cardinality, self-describing, tolerate-extras).
- FE: a "Generate with AI" entry on the CreateSchemaEntry + a "suggest additions" action on a
  live schema → renders the proposal as a review/diff (reuse the M3a review list / the
  SyncDiffPanel visual language) → user edits/ticks → adopt selected via A1 routes.
- Anti-spend: prefer a local chat model (test account has lm_studio models); the tool is
  cost-gated like other agentic kg tools.

---

## Sequencing (recommended)

Value-front-loaded, cheap→expensive:

1. **M1** — pickers + validation + usage badges + empty-state. Fastest visible win; FE-only.
2. **M3a** — infer-from-graph (`…/schema/observed` + review list). Cheap, high value, reuses
   the extraction people already ran.
3. **M3b** — `kg_schema_propose` MCP tool + generate/suggest FE (propose→confirm).
4. **M2** — the editable SchemaCanvas (flagship, biggest; its own sub-track). Canvas/List toggle.

Each milestone ships + live-smokes independently (vite→gateway→knowledge; M3b also through
ai-gateway). Track A's routes/usage are the substrate for all four.

## Open decisions (confirm before building contracts)

- **A — usage badges:** per-row `…/schema/usage` calls (N requests) vs one
  `…/schema/usage-summary` (all counts in one) — I lean summary (one Neo4j round-trip).
- **B — M2 default view:** canvas-first (list behind a toggle) vs list-first (canvas opt-in).
  I lean canvas-first once M2 lands, list always available.
- **C — M3b model:** force a local chat model (anti-spend) by default vs let the user pick in
  the generate dialog (mirrors GenerateWikiDialog). I lean: default to the user's chat default,
  local-preferred, explicit pick allowed.
- **D — M3b placement:** a brand-new `kg_schema_propose` tool vs extend an existing kg tool.
  New tool (single responsibility, LLM-client-first).
