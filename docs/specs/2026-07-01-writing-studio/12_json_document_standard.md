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
| Scene support (rich) | Navigator scene click → focus chapter AND scroll/highlight the scene (consume the existing-but-unused bus `scene` event); scene boundaries visible in the editor |
| CLARIFY audits (blocking, first step) | (a) **scene→body anchoring**: does the composition stitch emit markers into the Tiptap body, or must a scene-marker node be introduced? (b) scenes read/write API surface on composition-service; (c) whether scene-metadata writes have MCP tools (gate item 2) |
| Lane B | `book_*draft` handler exists; extend for scene-metadata writes |
| LIVE gate | agent: "đổi synopsis scene 2 chương 3" → MCP → DB → navigator + editor + json-editor all reflect it realtime |

## Cycle queue (each = one tool, re-scoped at its own CLARIFY)

Chapter editor (↑cycle 1) → Glossary → Wiki → Knowledge/Ontology → Translation (job-based — gate
needs the job-terminal→refresh path) → Reader/Compare (read-only — gate = display refresh on
agent chapter edits, mostly free via the existing `book_*` handler). Order re-confirmable per
cycle; queue lives here, detail specs land per-cycle (build-while-plan).

## Out of scope (this spec)

Agent-driven json-editor opening (needs a params-bearing ui tool — revisit after two consumers);
diff/merge view in the json-editor (Lane-C render lands with the first agent-diff consumer);
3rd-party provider packaging.
