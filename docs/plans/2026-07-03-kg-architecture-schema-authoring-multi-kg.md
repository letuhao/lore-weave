# KG architecture — full-CRUD KG-scoped schema authoring + agent multi-KG (2026-07-03)

**Origin:** user architecture review of KG exploitation. Locked principles + the
two tracks to build. This is the PLAN (no build yet) the user asked for.

## Locked principles (user, 2026-07-03)

1. **KG is GENERAL-PURPOSE, not book-bound.** A KG serves many things, not just a
   book — so `UNIQUE(book_id)` is *wrong*, and the KG **project** is the first-class
   unit. A book is one *consumer* of a KG, not its owner. (Confirms: DB already has
   no book-unique constraint; the soft-1-1 assumption in `get_by_book` / the world
   rollup / the schema editor is what must be relaxed, not enforced.)
2. **The schema editor must follow the KG project, not the book.** Today it lives at
   `/books/{id}/kg-ontology` (book tab) and `ProjectDetailShell`'s schema section is
   read-only. Author must be project-scoped.
3. **A human must be able to DEFINE a schema.** Today you can only *adopt a template
   then edit*; there is no create-from-scratch, and the editor is add-mostly (not
   full CRUD — user: "thiếu tùm lum"). Enhance the EXISTING editor to full CRUD +
   clone (do NOT build a new editor).
4. **Agent loading exactly one `project_id` needs improvement** (multi-KG synthesis).

## Audited current state

**Schema authoring surface:** `SchemaWorkbench` (FE), driven by `useGraphSchema`;
mounted only in the BOOK tab `KnowledgeOntologyTab` (`/books/{id}/kg-ontology`), and
read-only in `ProjectDetailShell`'s `ProjectSchemaSection` (deep-links to the book
tab). Schema tab shows `noSchema` until a template is adopted.

**BE CRUD (`routers/public/ontology.py`) — "additive + deprecate-only" (its own §473 comment):**

| Component | Create | Read | Update | Delete |
|---|---|---|---|---|
| Graph schema | ❌ (only `adopt` copy-down; `POST /system/graph-schemas` = **501** admin stub) | ✅ resolve/list/tree | ⚠️ PATCH meta (`allow_free_edges` + name/desc) | ✅ `DELETE /graph-schemas/{id}` |
| Node kind | ✅ `POST …/node-kinds` | ✅ | ❌ | ❌ |
| Edge type | ✅ `POST …/edge-types` | ✅ | ❌ | ⚠️ `DELETE` = **deprecate** (soft) |
| Fact type | ✅ `POST …/fact-types` | ✅ | ❌ | ❌ |
| Vocab value | ✅ `POST …/vocab-sets/{set}/values` | ✅ | ❌ | ❌ |
| Vocab set | ❌ | ✅ | ❌ | ❌ |

**Agent KG loading:** `context/builder.py` selects ONE mode from ONE `project_id`;
every MCP tool (`kg_graph_query`, …) takes ONE optional `project_id`. The `world`
rollup (`world_rollup.resolve_world_project_ids` + `get_world_subgraph`, union of
member-book canon projects + the world bible project) is **read-only, FE-only,
disconnected per-book islands, NOT registered as an MCP tool**.

---

## Track A — full-CRUD, KG-scoped schema authoring

### A1 — complete the CRUD (BE `ontology.py` + `ontology_mutations.py`)

Add the missing verbs so every schema component is fully editable:

- **Node kind:** `PATCH …/node-kinds/{code}` (strength/label) + `DELETE` (deprecate
  on a live schema; hard-delete only on an unused/draft schema — see A4).
- **Edge type:** `PATCH …/edge-types/{code}` (label, source/target kinds, cardinality,
  temporal, provenance, description). (Add + deprecate already exist.)
- **Fact type:** `PATCH …/fact-types/{code}` + `DELETE`.
- **Vocab:** `POST/DELETE …/vocab-sets` (set-level) + `PATCH/DELETE …/vocab-sets/{set}/values/{code}`.
- Keep `DuplicateChildError`→409, `ChildNotFoundError`→404, `_writable_schema_for_caller`
  (MANAGE grant) on every new verb.

### A2 — create-from-scratch + clone (BE)

- **`POST /v1/kg/projects/{id}/schema`** — create a BLANK project schema (empty
  edge/kind/fact/vocab, `allow_free_edges=true`, name/desc), becoming the project's
  active schema. Removes the "must adopt a template first" requirement. Idempotent /
  replace-on-create per the one-active invariant.
- **`POST /v1/kg/graph-schemas` (clone)** — copy any readable schema (a template, or
  another project's) into a NEW **user-scoped** editable schema the caller owns
  (distinct from `adopt`, which is a project-scoped replace). The user then edits it
  freely and adopts/attaches it. (This is the "clone a template into MY schema"
  the user asked for.)
- Unblocks the `POST /system/graph-schemas` 501 only when the admin-identity epic
  lands (leave as-is; out of scope).

### A3 — KG-scoped authoring surface (FE)

- **Move authoring to the KG project:** make `ProjectSchemaSection` (in
  `ProjectDetailShell`, route `/knowledge/projects/{id}/schema`) the FULL authoring
  surface — mount the enhanced `SchemaWorkbench` + adopt/create/clone, scoped to the
  project. The book tab (`/books/{id}/kg-ontology`) redirects here (or stays as a
  thin deep-link) so KG editing lives with the KG, not the book.
- **Enhance `SchemaWorkbench` to full CRUD:** edit + delete controls on every node
  kind / edge type / fact type / vocab value + vocab-set management; a "New blank
  schema" and "Clone template" entry point (replacing the adopt-only start). Wire the
  new mutations in `useGraphSchema`.
- Keep it an ENHANCEMENT of the existing components (user directive: no new editor).

### A4 — safety / tenancy

- Authoring = **MANAGE** grant (existing `_writable_schema_for_caller`).
- **Live-schema destructive edits** (delete a node-kind/edge-type an extracted graph
  uses) need a guard: default to **deprecate** for a live schema; allow **hard-delete**
  only on a draft/never-extracted schema, or behind a "would-orphan N nodes" warning
  (mirror the adopt would-lose preview). This keeps extraction integrity.

---

## Track B — agent multi-KG (load / aggregate)

### B1 — options (ranked by effort)

1. **World-rollup as an MCP tool (recommended first).** Register a `kg_world_query`
   (or extend `kg_graph_query` with an optional `world_id`) that reuses
   `resolve_world_project_ids` + `get_world_subgraph` — an app-side UNION across a
   world's member-book KGs. Agent-callable, minimal new logic (the rollup exists).
   Gives "agent loads every KG in a world to synthesize" cheaply. Islands (no
   cross-partition edges) are acceptable for synthesis.
2. **Multi-project context.** A chat session carries a SET of `project_id`s; the
   context builder unions their L2 facts + L3 passages (shared token budget, dedup).
   Deeper (touches the context builder + the session model), the real "load/unload
   multiple KGs" the user asked for.
3. **Arbitrary project-id set (not just a world).** Generalize (1)/(2) to any set of
   `project_id`s the caller owns, not only a world grouping — for ad-hoc "canon KG +
   fan-theory KG" comparisons.
4. **True cross-partition merge** (edges spanning books). Deepest; likely a separate
   epic — union-of-islands covers most synthesis first.

### B2 — recommended sequence

B1(1) world-rollup MCP tool → B1(2) multi-project context → B1(3) arbitrary set.
Defer B1(4).

---

## Sequencing + open decisions

**Build order:** Track A first (the concrete, user-painful gap: humans can't author
schemas; also realizes the KG-first principle), then Track B (agent multi-KG),
starting with the world-rollup MCP tool.

**Open decisions to confirm before building the contracts:**
- A2 clone target: **user-scoped reusable** schema (recommended) vs project-scoped one-off.
- A4 delete semantics: hard-delete on draft only + deprecate on live (recommended) vs
  always-deprecate.
- B scope unit: **world** (grouping exists) vs **arbitrary project-id set**.
- A3 book tab: redirect to the project surface vs keep both.
