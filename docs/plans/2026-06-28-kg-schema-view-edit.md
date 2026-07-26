# Plan — #28 KG schema view + self-service edit GUI (L)

Date: 2026-06-28 · branch `fix/critical-ux-bugs`

## Problem
User can only command the AI to set up the KG schema — there is no FE to **view** or
**edit** it themselves. Verified in-code:
- BE edit endpoints all exist; `useGraphSchema` already wires every mutation
  (`addNodeKind`/`addEdgeType`/`deprecateEdgeType`/`addFactType`/`addVocabValue`/`patchMeta`).
- The only schema UI mounted is the read view + one "deprecate edge" button
  (`KnowledgeOntologyTab` → Schema). `AddEdgeTypeForm.tsx` exists but is **never mounted**
  (dead code); no forms exist for node-kinds/fact-types/vocab values.
- The standalone Knowledge GUI (`ProjectDetailShell`) has **no Schema section** at all.
- Schema model is **additive + deprecate-edge-only** (mirror of what the AI does).

## Part A — View (the original #28): read-only inspector in the Knowledge GUI
1. `hooks/useResolvedSchema.ts` — `useQuery` over `ontologyApi.getResolvedSchema(projectId)`
   (`GET /v1/kg/projects/{id}/schema`, always returns the effective system→user→project merge).
2. `components/shell/ProjectSchemaSection.tsx` — fetch resolved schema, adapt → a
   `GraphSchemaTree` shape, render `<SchemaEditor readOnly>` (zero new render code) + an
   "Edit schema" CTA deep-linking to the book's ontology Schema tab (when the project has a book).
3. `ProjectDetailShell.tsx` — add `'schema'` to SECTIONS + SECTION_DEFS (Network/Share icon),
   render the section, i18n label `shell.sections.schema`.

## Part B — Edit (the real ask): authoring forms in the book GUI Schema tab
4. `components/ontology/AddNodeKindForm.tsx` — `kind_code` + `strength` (required/optional).
5. `components/ontology/AddFactTypeForm.tsx` — `code` + `label`.
6. `components/ontology/AddVocabValueForm.tsx` — pick an existing vocab set + `code` + `label`
   (disabled with a hint when the schema has no vocab sets).
7. `components/ontology/SchemaWorkbench.tsx` — composes `SchemaEditor` (read + deprecate edge)
   + `AddEdgeTypeForm` (now mounted) + the 3 new forms + an `allow_free_edges` toggle
   (`patchMeta`), driven by the `useGraphSchema` controller. ≤100-line leaves; the workbench
   only wires.
8. `KnowledgeOntologyTab.tsx` — render `<SchemaWorkbench schema={schema} />` in the Schema view
   instead of the bare `<SchemaEditor>`.
9. i18n `kgOntology.schema.*` — add keys for the 3 forms + the toggle, ×4 locales.

## Out of scope / constraints
- No BE changes, no migration (every endpoint exists). Additive model: no hard-delete of
  node/fact/vocab (only edge-deprecate), matching the AI's capabilities.
- System/user templates stay read-only (BE `_writable_schema_for_caller` gates to project scope);
  the editor only targets the project's active schema.

## Verify
- FE knowledge suite green incl. new tests: `useResolvedSchema`, `ProjectSchemaSection`,
  `SchemaWorkbench` (each form submit → controller callback), `ProjectDetailShell` schema tab.
- tsc clean; 4-locale parity for the new keys.
- Live smoke optional (read path) — `live infra unavailable` acceptable for FE-only.

## Checkpoints
- Commit 1 = Part A (view). Commit 2 = Part B (edit). Both behind the same #28 bug row.
