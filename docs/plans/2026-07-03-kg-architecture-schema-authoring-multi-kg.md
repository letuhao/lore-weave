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

## Edge cases + folded decisions (spec review 2026-07-03 — LOCKED)

A grounded spec review against the code surfaced edge cases the naive plan missed;
all four original open decisions are resolved here as the recommended path.

### 🔴 must-honor invariants

- **EC-A1 (schema-level) — child tables have a NON-partial `UNIQUE(schema_id, code)`**
  (`kg_edge_types`/`kg_fact_types`/`kg_schema_node_kinds`/`kg_vocab_sets` +
  `UNIQUE(vocab_set_id, code)` on `kg_vocab_values`; migrate.py ~1161–1203). A
  deprecated row keeps occupying the slot, so **deprecate-then-recreate the same
  code → 409 forever** (already a latent bug today; full-CRUD makes it central).
  `kg_graph_schemas` was already fixed to a PARTIAL unique (`WHERE deprecated_at IS
  NULL`, migrate.py ~1141) for exactly this. **DECISION:** ship **A0** — a partial-
  unique migration on all 5 child tables, mirroring the schema-table fix. The
  migration MUST use the serialized-DDL guard (`execGuarded` / `pg_advisory_xact_lock`)
  or the shared-DB parallel test suite deadlocks (40P01). This makes deprecate-then-
  recreate work and lets `add_*` INSERT cleanly after a soft-delete.
- **EC-A2 — create-blank upholds replace-on-adopt + `_lock_project`.** `POST
  /v1/kg/projects/{id}/schema` deprecates any active project schema under the same
  advisory lock adopt uses, then inserts, so the one-active invariant holds (else
  `resolve_for_project`'s `ORDER BY updated_at DESC LIMIT 1` silently orphans a row).
  Note the semantic asymmetry with the existing `GET /projects/{id}/schema` (GET =
  resolved/merged; POST = create a blank project row) — documented, acceptable.
- **EC-A3 — clone reuses the adopt visibility gate.** `POST /v1/kg/graph-schemas`
  (clone) MUST run `_assert_source_adoptable` on the source (System / caller's own
  user template / a project the caller can read) — else clone becomes the exact
  cross-tenant read oracle that gate was added to close. Clone target is
  **user-scoped reusable** (original A2 decision, locked). A same-code collision on
  the user tier auto-suffixes the name/code ("general (copy)", "…(copy 2)"), never a
  bare 409.
- **EC-B1 — world-rollup MCP tool takes `world_id` as an EXPLICIT body arg** (the
  ai-gateway MCP federation drops `X-Project-Id`-style envelope scope), and reads
  `user_id` from the tool context (`resolve_world_project_ids` needs it +
  book-service `/internal/worlds/{id}/books`).
- **EC-B2 — world rollup is OWNER-ONLY (skips `bp.user_id != user_id`, M0).** For a
  collaborator on a shared world the union silently returns only their own
  partitions. **DECISION (phase 1):** keep owner-only, but the tool MUST report
  "N of M partitions unreadable" rather than drop silently. Cross-owner grant-gated
  rollup is a separate later epic (gate #2 structural).

### 🟡 build-shaping rules

- **EC-A4 — the live-delete guard is NOT a mirror of adopt-preview.** Adopt-preview
  is schema-vs-schema; "how many graph nodes use kind X" is a NEW count query against
  the derived graph (Neo4j) / Postgres entity store. Scope it as new work in A4.
- **EC-A5 — "draft" doesn't exist as a flag; use tier as the predicate.** Hard-delete
  is allowed ONLY on a **user-tier template** (never adopted into a project);
  **project-tier is always deprecate-only** (its project can extract at any time).
  This is the original A4 decision, refined to a predicate that needs no new column.
- **EC-A6 — `code` is IMMUTABLE; PATCH edits attributes only** (label/strength/
  cardinality/target-kinds/…). A rename = deprecate + create-new (a rename would
  orphan graph data keyed by the old code). Build A1's PATCH on the existing
  attribute mutators (`widen_edge_target_kinds`, `set_edge_cardinality`).
- **EC-A7 — every new PATCH/DELETE verb calls `_bump_and_rehash`** (skipping it
  desyncs `content_hash`/`source_hash` → phantom Sync `has_updates`).
- **EC-B3/B4 — multi-project union is real work, not a wrapper.** Member books can
  carry different adopted schemas → structured graph queries across the union must
  tolerate an edge-code present in one schema and absent in another. B1(2)
  multi-project context needs a cross-project ranker + dedup (world-bible vs member
  overlap) under a shared token budget; Track-4 salience/rerank is per-project today.

### 🟢 low / documented

- **EC-X1** — create-blank on an already-adopted project warns "discards template link
  + customizations" (symmetric with the re-adopt loss gate).
- **EC-A8** — System templates stay seed-only (501); create-blank authors project/user
  tiers, which is the correct System=admin-only boundary.
- **EC-B5** — the MCP tool maps `WorldNotFound`/`BookServiceUnavailable` to a
  self-correcting `result.error` string (LLM-client-first), never a 500.

## Sequencing (folded)

**Build order — Track A first, starting with the migration:**

- **A0** — partial-unique migration on the 5 child tables (EC-A1), serialized-DDL guard.
- **A1** — complete CRUD (PATCH attribute-only + DELETE) on every schema component,
  reusing `_writable_schema_for_caller` + `_bump_and_rehash`; project-tier
  deprecate-only, user-tier hard-delete (EC-A5/A6/A7).
- **A2** — create-blank (`POST /projects/{id}/schema`, EC-A2/X1) + clone
  (`POST /graph-schemas`, user-scoped, gated, auto-suffix — EC-A3).
- **A3** — move authoring to `ProjectSchemaSection` (project surface), enhance
  `SchemaWorkbench` to full CRUD; **book tab `/books/{id}/kg-ontology` redirects** to
  the project surface (original A3 decision, locked).
- **A4** — live-delete orphan-count guard (EC-A4) as its own slice.

**Then Track B:** B1(1) world-rollup MCP tool (EC-B1/B2/B5) → B1(2) multi-project
context (EC-B3/B4) → B1(3) arbitrary project-id set. Defer B1(4) cross-partition merge.
