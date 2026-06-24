# Lane LE — KG ontology UI: C3 integration notes

Lane LE built the **frontend KG customizable-ontology** surface entirely under
`frontend/src/features/knowledge/` (no shared files touched). This note lists the
shared wiring that must happen at **C3 integration** (route table, sidebar, i18n
registry are append-only there).

## Files this lane owns (all new)

| File | Role |
|---|---|
| `types/ontology.ts` | TS types mirroring `contracts/api/knowledge-service/{ontology,views,triage}.yaml` |
| `api/ontology.ts` | `ontologyApi` typed client — relative `/v1/kg/...` via shared `apiJson` |
| `hooks/useGraphSchema.ts` | schema list + one schema's tree + child add / deprecate (schema editor controller) |
| `hooks/useOntologyAdopt.ts` | adopt (copy-down) + **M1 `needs_glossary` 422 → derived `needsGlossary` deep-link state** |
| `hooks/useGraphViews.ts` | per-user view CRUD (list / create / upsert-by-code / delete) |
| `hooks/useOntologySync.ts` | tree-diff + per-node `keep_mine`/`take_theirs` decision state + apply |
| `components/ontology/OntologyChip.tsx` | render-only chip primitive (tier/edge/drive/glossary/temporal/deprecated) |
| `components/ontology/AdoptPicker.tsx` | adopt picker + M1 blocker list + glossary deep-link (mirrors `01-adopt.html`) |
| `components/ontology/SchemaEditor.tsx` | edge/fact/vocab/node-kind list + deprecate (mirrors `02-schema-editor.html`) |
| `components/ontology/AddEdgeTypeForm.tsx` | additive edge-type add form |
| `components/ontology/SyncDiffPanel.tsx` | per-node sync diff + bulk keep/take + apply (mirrors `06-sync.html`) |
| `components/ontology/ViewBuilder.tsx` | edge/node-kind lens builder (mirrors `03-views.html`) |
| `i18n/{en,vi,ja,zh-TW}/kgOntology.json` | locale strings, namespace **`kgOntology`** (4 project locales) |

Tests: `hooks/__tests__/use{Ontology*,GraphSchema,GraphViews}.test.tsx`,
`components/ontology/__tests__/{AdoptPicker,SyncDiffPanel}.test.tsx` — **28 tests, all green**.

## Shared wiring to add at C3 (append-only — do NOT do it in this lane)

1. **i18n registry** — `frontend/src/i18n/index.ts`
   - Import the 4 `kgOntology.json` files (one per locale, matching the existing
     per-feature pattern, e.g. `import enKgOntology from '@/features/knowledge/i18n/en/kgOntology.json'`)
   - Register under the `kgOntology` namespace for each of `en` / `vi` / `ja` / `zh-TW`.
   - Run `npm run i18n:check` after wiring (parity check).

2. **Route table** — wherever the knowledge feature mounts its routes
   (e.g. the app router / a `KnowledgePage` tab host). Add a KG-ontology
   surface that composes the lane components, e.g.:
   - Adopt screen → `AdoptPicker` driven by `useGraphSchemaList` + `useOntologyAdopt`
   - Schema editor → `SchemaEditor` + `AddEdgeTypeForm` driven by `useGraphSchema`
   - Sync → `SyncDiffPanel` driven by `useOntologySync`
   - Views → `ViewBuilder` driven by `useGraphViews`
   A page wrapper supplies the callbacks: `onAdopt(schemaId)` → `adopt({ source_schema_id })`
   inside a try/catch (the gate is surfaced as `needsGlossary` state); `onOpenGlossary(bookId)`
   → navigate to the glossary kinds editor for that book (the M1 deep-link).

3. **Sidebar entry** — add a "Graph schema / Ontology" nav item pointing at the new route.

4. **Mock → real API** — `api/ontology.ts` already targets the live gateway
   (`/v1/kg/...`); no swap needed. Tests mock `ontologyApi` directly. Once the
   real BE (lanes LC/LD/LF) is up, just stack the services and smoke.

## Deferred

- `D-KG-LE-BROWSER-SMOKE` — the dev FE is a baked nginx image (per project memory),
  so a Playwright browser smoke of these screens is deferred to C3 after the
  route/sidebar/i18n are wired and the FE image is rebuilt.

## Contract notes / ambiguities flagged

- **`adopt` ergonomics**: the hook exposes `adopt = mutation.mutateAsync`, so callers
  pass the payload object `{ source_schema_id, acknowledge_optional_gaps }` (matches the
  contract request body). `needsGlossary` is **derived** from `mutation.error` (a 422 with
  a `needs_glossary` body) — onError stays side-effect-free, which avoided a vitest/RQ
  unhandled-rejection artifact (a reused `vi.fn().mockRejectedValue` across reject tests
  leaks; the test uses a fresh `vi.fn()` per test).
- **`ResolvedSchema` / `GraphSchemaTree`** in the contract expose `vocab_sets` (with nested
  `values`) but the schema-children **add** routes only cover edge/fact/vocab-value/node-kind
  (no top-level *vocab-set create* route, and no fact/node-kind/vocab-value *deprecate* route —
  only edge-type deprecate is specced). `SchemaEditor` therefore renders vocab sets read-only
  and only wires edge-type deprecate; the page can add the others when the BE exposes them.
- **Sync `removed_upstream`**: `take_theirs` on a removed-upstream node is a no-op the BE
  ignores (boundary independence keeps your copy). The hook only sends decisions the user
  explicitly set, so an untouched removed-upstream row defaults to `keep_mine`.
- **`as_of_chapter` / graph read + triage** clients are included for completeness (LD/LH own
  the explorer/triage views); LE shipped the four CLARIFY-named surfaces (adopt / schema /
  sync / views) as components.
