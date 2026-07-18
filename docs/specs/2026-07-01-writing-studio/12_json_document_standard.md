# 12 · JSON Document Standard + per-tool migration cycles

> **Status:** 📐 specced · 2026-07-02 · branch `feat/studio-agent-raid`
> **Supersedes** the "wave 2" batch plan in [`11_dockable_migration.md`](11_dockable_migration.md) §Later waves —
> scope proved larger than a wave: from here on **one cycle = ONE tool**, done end-to-end, serially (no fan-out —
> every cycle touches the shared registries/tool surface, and batch migration loses the middle).

## Why

The studio's tool count keeps growing (user vision). Two recurring needs converge on one substrate:

1. **Users** need a raw power-edit surface for any resource the GUI hasn't fully caught up with
   (AWS-console-JSON / Lens-"Edit YAML" style), with schema validation.
2. **Agents** need ONE standardized document surface: Lane-C diff proposals and Lane-B refreshes
   work on canonical JSON documents instead of a bespoke card per resource type.

Market grounding (researched 2026-07-02): VS Code's custom-editor model (viewType + selector
registration, **model–view split**: one `CustomDocument` per resource shared by N editor views,
provider owns save/revert/dirty; `priority: default|option`), Lens's per-resource "Edit YAML →
apply through the API server (OCC)", Monaco/CodeMirror JSON-Schema language tooling.

## Locked decisions

| # | Decision | Why |
|---|---|---|
| S1 | **`registerJsonDocumentProvider` — the studio's 4th registry** (after tools, status-bar items, effect handlers). `type` is a versioned envelope id: `loreweave.<resource>.v1` | Same proven pattern; extension-like growth = add a provider (~30–50 lines wrapping an existing API) |
| S2 | **Model–view split**: `open(resourceId)` returns a shared, refcounted `DocumentHandle` per (type, id); panels (GUI panel, json-editor, future diff view) are THIN VIEWS on the handle. `save/revert/dirty/onDidChange` live on the HANDLE, not the panel | VS Code `supportsMultipleEditorsPerDocument` lesson — two views of one resource must never be two divergent fetches. Mirrors the Tier-4 hoist (D4/D13); the manuscript provider WRAPS the existing hoist, never duplicates it |
| S3 | **Save always wraps the domain API** (OCC via etag/version); NEVER a generic DB write. **The agent's write path stays MCP** (MCP-first invariant) — the json-editor is a USER surface + a render surface for agent-proposed diffs, not an agent write channel | Tenancy/validation stay server-side; no invariant bypass |
| S4 | **One generic `json-editor` dock panel**, opened via F1 `params {docType, resourceId}` (palette, cross-panel "Open as JSON", resolver). GUI panel = `default` editor; JSON = `option` (VS Code priority duality, Lens UX) | JSON never competes with the GUI — it's the second view on the same document |
| S5 | **CodeMirror 6 + `codemirror-json-schema`** (validate + autocomplete from the provider's JSON Schema); format + validate + ⌘S per 04b UX | ~50–300KB modular vs Monaco's 2–5MB; schema tooling is the only Monaco feature we need and CM6's port covers it |
| S6 | Runtime registry only — **no manifest/lazy-activation layer** | That's for 3rd-party ecosystems; YAGNI at our scale |

### Provider interface (S1+S2)

```ts
interface JsonDocumentProvider {
  type: string;                       // 'loreweave.manuscript-unit.v1'
  schema?: JSONSchema;                // CM6 validate + autocomplete
  open(ctx, resourceId): Promise<DocumentHandle>;   // shared + refcounted
}
interface DocumentHandle {
  doc: unknown;                       // canonical JSON document
  etag: string | number;              // OCC token (draft_version, updated_at, …)
  dirty: boolean;
  onDidChange(listener): Unsubscribe; // all views re-render from here
  update(next): void;                 // view → handle (marks dirty)
  save(): Promise<void>;              // wraps the DOMAIN API; conflict → surfaced state
  revert(): void;
  release(): void;                    // refcount down; dispose at zero
}
```

## The per-tool cycle (replaces waves) — gate is MANDATORY

Each cycle migrates exactly ONE tool, serially. A cycle is DONE only when ALL of:

1. **Panel** passes the W1 8-point checklist (spec 11 §standard — catalog, thin-view, register,
   bus, self-title, contract, route-decoupling, tests).
2. **MCP audit** — the domain has DB-writing MCP tools reachable from studio chat; missing ⇒
   create them on the owning service (MCP-first invariant), never a bespoke HTTP path.
3. **Lane-B effect handler** registered for the tool family (extract IDs from structured results
   → invalidate the panel's query keys; G5/G7 rules).
4. **Realtime-ready data layer** — the panel reads through invalidatable queries (refactor raw
   `useState` fetches where needed).
5. **JSON provider** registered for the tool's resource (S1–S5).
6. **LIVE gate (the user-mandated pass/fail):** chat agent → MCP call → DB change → the panel
   updates in realtime WITHOUT a manual reload — proven by a live browser smoke, judged by
   EFFECT (Frontend-Tool-Contract discipline).

## Cycle 1 — Chapter editor (the first standard consumer)

The current rich editor doesn't support scenes; the manuscript navigator renders arc→chapter→scene
but a scene click degrades to chapter focus — the scene layer is dead UI. Cycle 1 rebuilds the
chapter-editing unit ON the standard:

| Piece | Content |
|---|---|
| Provider #1 | `loreweave.manuscript-unit.v1` — the 04b document: `{ body (Tiptap JSON), scenes[] (outline metadata: synopsis/status/beat_role — D17: prose stays in body) }`. `open()` WRAPS the Tier-4 `ManuscriptUnitProvider` (one owner store — D13); `save()` = draft PATCH (`draft_version` = etag) + scene-metadata writes. Clears Debt #6 (04b raw editor) as a provider of the generic panel |
| Hoist extension | `ManuscriptUnitState` gains `scenes[]` (loaded with the unit; composition outline is the source) |
| Scene support (rich) | **Scene Rail** (see R1 below): navigator scene click → focus chapter + open/highlight the scene's row in a metadata rail beside the editor (consume the existing-but-unused bus `scene` event); synopsis/status editable in the rail |
| MCP tools (gate item 2) | **Already exist** (corrected at build): `composition_outline_node_update` + siblings cover scene metadata with OCC/tenancy/undo — no new BE tool this cycle |
| Lane B | `book_*draft` handler exists; add an `outline_*`/scene handler → invalidate outline queries + reload hoist `scenes[]` |
| LIVE gate | agent: "đổi synopsis scene 2 chương 3" → MCP → DB → navigator + Scene Rail + json-editor all reflect it realtime |

### CLARIFY audit results (2026-07-02 — resolved against code, pre-build)

- **(a) Scene→body anchoring: DOES NOT EXIST and is not recoverable retroactively.** The final
  chapter body is either LLM-stitched (`per_scene_stitch` — seams are *smoothed*, boundaries
  destroyed) or one-shot (`chapter`); no marker survives into the Tiptap body. Per-scene prose
  exists only PRE-stitch (`promoted_scene_prose` artifacts).
  **R1 (resolution):** cycle-1 scene support is **metadata-first — no prose anchoring**: the
  Scene Rail + json-editor `scenes[]` make the navigator's scene layer real without touching
  prose. Prose anchoring (a `sceneMarker` Tiptap node emitted by the compose/assembly path)
  is a **future composition-pipeline change**, tracked, out of cycle-1 scope.
- **(b) Scenes R/W API: EXISTS** — composition `PATCH /outline/nodes/{node_id}` (+ create /
  reorder / restore / children / search / stats). The navigator already consumes the reads.
- **(c) Scene-metadata MCP tools: ~~MISSING~~ EXIST** — corrected at build (the audit grep missed
  the naming): `composition_outline_node_update` (+create/delete/restore, scene_link_*) already
  covers title/goal/synopsis/status with OCC `expected_version`, tenancy project-scoping and undo
  hints. Cycle 1 therefore adds NO BE tool — only the Lane-B handler wiring.

### Spec-review resolutions (adversarial pass 2026-07-02)

| # | Gap found | Resolution |
|---|---|---|
| R1 | Scene anchoring absent (audit a) | Metadata-first Scene Rail; prose markers = future pipeline work |
| R2 | **Hoist is a single-unit singleton but `open(resourceId)` implies any chapter** — a json-editor on a non-active chapter would need a second document store, breaking D13 | v1: the manuscript provider serves the **ACTIVE unit only**; `open(otherChapter)` first `focusManuscriptUnit(otherChapter)` (single-unit studio semantics). Multi-unit handles = future, revisit with split-editor demand |
| R3 | **json-editor multi-instance collides with dockview `id === component`** (openPanel maps id→component 1:1) | v1: `json-editor` is a **singleton panel that retargets via `updateParameters`** (VS Code settings-tab UX). Multi-instance needs an `openPanel` `component` opt — deferred until two-docs-side-by-side is a real ask |
| R4 | **`panelCatalogContract` enforces enum == palette-openable set** — cataloguing json-editor would force it into the agent enum, but agent-open needs params (out of scope) | json-editor ships `hiddenFromPalette: true`; opened only via "Open as JSON" affordances + F1 params. No enum change, no contract regen this cycle |
| R5 | **Composite etag** — body (`draft_version`) and scenes (node `updated_at`) are two save paths with independent OCC | `save()` is sequential two-phase (draft PATCH → changed-node PATCHes); conflicts surface PER PART on the handle (`conflict: 'body' \| 'scenes'`); no fake atomicity claimed |
| R6 | **G7 × scenes[]**: may Lane-B reload scenes while the body buffer is dirty? | Yes — body and scenes are separate buffers on the handle; a scenes-only reload never touches the dirty body (G7 applies per-buffer) |

## Cycle queue (each = one tool, re-scoped at its own CLARIFY)

Chapter editor (↑cycle 1, ✅ built) → **Glossary (✅ built — re-scoped as shared-foundation-then-fanout,
see [`13_glossary_panels.md`](13_glossary_panels.md); Phase A serial + Phase B 8-way parallel fanout)**
→ Wiki → Knowledge/Ontology (underway, see `14a_kg_panels.md`) → Translation (job-based — gate needs the job-terminal→refresh path) →
Reader/Compare (read-only — gate = display refresh on agent chapter edits, mostly free via the
existing `book_*` handler). Order re-confirmable per cycle; queue lives here, detail specs land
per-cycle (build-while-plan).

## Agent search & ambient context (research-locked 2026-07-02, mid-cycle-1)

The first live-gate attempt was invalidated by methodology: the prompt hand-fed UUIDs no human
knows. Root causes + market research (GitHub Blackbird, Sourcegraph/Zoekt, Cursor/Claude-Code
tooling, MCP Roots, LangChain ToolRuntime) locked these:

| # | Decision | Why |
|---|---|---|
| AS1 | **ONE universal search tool `story_search`** on knowledge-service (`{query, mode: hybrid\|exact\|semantic, granularity: chapter\|block, limit}`) wrapping the existing `run_hybrid_search` (book-service FTS/trigram + Neo4j CJK fulltext + passage vectors + RRF + CE rerank, per-leg degrade) | Tool sprawl confuses agents (user rule). The Cursor/Claude model: simple schema, powerful engine. Granularity mirrors Claude-Code's grep funnel — `chapter` ≈ `files_with_matches`, `block` ≈ `content`; `book_get_chapter` = Read |
| AS2 | **NO temp filesystem workspace** for search — the DB indexes ARE the search engine | Market: nobody greps raw content at query time at scale (GitHub: grep = 0.01 QPS → Blackbird n-gram index = 640 QPS; Zoekt trigram). A disk mirror = IO disaster + stale-vs-DB truth + tenancy bypass. pg_trgm's "one giant index" caveat doesn't bite: every query is book-scoped |
| AS3 | **Zero required location args** — project resolves from the ambient ToolContext (envelope `X-Project-Id`), book from the project link; `project_id` stays optional+ownership-checked | Users don't know ids (MCP Roots / ToolRuntime server-side injection pattern). knowledge tools already had the seam; story_search rides it. Extending the same ambient default to composition/book tool args = chat-service work — **RAID-coordinated (their C2 territory), tracked, not this cycle** |
| AS4 | **Gate methodology: natural-language prompts only** — the agent must locate targets via the context pointer + story_search; hand-feeding ids voids the gate | The user-mandated realism rule |

## Out of scope (this spec)

Agent-driven json-editor opening (needs a params-bearing ui tool — revisit after two consumers);
diff/merge view in the json-editor (Lane-C render lands with the first agent-diff consumer);
3rd-party provider packaging.
