# glossary EDIT-ATOMIC — multi-field atomic edit — plan

- **Date:** 2026-06-10 · **Phase:** enhancement (post P0–P6) · **Size:** L · **PO:** default v2.2; `/review-impl` at POST-REVIEW; no `/amaw`.
- **Goal:** one glossary diff-card proposes changes to MULTIPLE fields (name/aliases/short_description/attributes) and Applies them in ONE transaction with ONE version check — lifting P3's one-PATCH-target-per-proposal limit. Was D-GLOSSARY-EDIT-ATOMIC (now a feature, not debt).

## Decisions (CLARIFY/DESIGN)
- **New atomic endpoint** `POST /v1/glossary/books/{book}/entities/{entity}/apply-edit` (new `apply_edit_handler.go` — don't bloat patchEntity). Body `{base_version, short_description?, attributes:[{attr_value_id, original_value}]}`.
- **One tx, one version gate (H5):** `SELECT updated_at FROM glossary_entities WHERE entity_id=$ AND book_id=$ FOR UPDATE` → 404 if gone, **412 GLOSS_VERSION_CONFLICT** if `updated_at != base_version` (parses base as `::timestamptz`, same as P3). Then apply short_description (entity UPDATE) + each attribute (EAV UPDATE, each scoped `attr_value_id + entity_id`), bump `updated_at = now()` once, capture before/after + emit ONE `glossary.entity_updated` (transactional outbox, mirror patchEntity), commit. Any error → rollback (no partial write).
- **Triggers/parity:** cached_name (K2a) + snapshot recalc fire on the EAV writes automatically; short_description auto-regen kept at `patchAttributeValue` parity (only when the `description` attr is among the changes AND `short_description_auto` still true — i.e. user didn't also set short_description).
- **Tool schema replaced:** `glossary_propose_entity_edit` drops `target`/`attr_value_id`/`field_label`/`old_value`/`new_value`, gains `changes:[{target, attr_value_id?, field_label, old_value, new_value}]`. Single edit = 1-element array. Resume/outcome enum unchanged (H6).
- **P3 single-PATCH endpoints stay** (manual UI uses patchEntity/patchAttributeValue + If-Match) — AC6.

## Build steps
### 1. glossary-service (Go)
- `apply_edit_handler.go`: `applyEntityEdit` handler. Reuse `loadEntityEventFields`/`buildEntityEventPayload`/`emitEntityUpdatedTx` (patchEntity's helpers) + `verifyAttrValueInEntity` semantics in-tx (scope the EAV UPDATE by `attr_value_id AND entity_id`, RowsAffected guards). short_description handling mirrors patchEntity (trim, 500-rune cap, `_auto=false`). regen short_desc after attr writes if a description attr changed.
- `server.go`: route `r.Post("/books/{book_id}/entities/{entity_id}/apply-edit", s.applyEntityEdit)`.
- Tests (`apply_edit_test.go`, DB-backed real-PG): multi-field apply (short_desc + name attr) → 200, both written, updated_at bumped once, ONE outbox event; stale base_version → 412 (NO field written — rollback); unknown attr_value_id → 4xx (no partial); no-If-Match-equiv (base required). Non-DB: ownership-denied + missing base.

### 2. chat-service (Python)
- `frontend_tools.py`: `GLOSSARY_PROPOSE_EDIT_TOOL` → `changes[]` array schema (item: target/attr_value_id?/field_label/old_value/new_value); description updated (propose N changes atomically). Required = book_id, entity_id, base_version, changes.
- Tests: schema wire-standard (changes is array; item required keys); drift-guard test still finds the tool name.

### 3. frontend (React)
- `GlossaryDiffCard`: read `args.changes[]`; render one old→new row per change (label + strike-old/highlight-new). Apply: build `{base_version, short_description?, attributes:[{attr_value_id, original_value}]}` from the changes, ONE `glossaryApi.applyEntityEdit(...)` call → 200→applied_saved / 412|409→applied_conflict / else→applied_error → resume.
- `glossary/api.ts`: `applyEntityEdit(bookId, entityId, body, token)` → POST apply-edit.
- Tests: card renders N rows; Apply posts one atomic body + resumes applied_saved; 412 → applied_conflict; cancel → dismissed.

### 4. VERIFY
- glossary `go build` + `go test` (atomic apply DB-backed real PG); chat `pytest`; FE `vitest` + `tsc`.
- provider-gate.
- Cross-service (chat→FE→glossary apply-edit): browser/Playwright → folds into `D-GLOSSARY-LIVE-SMOKE-BROWSER` (the server tx is real-PG-verified).

## AC
AC1 atomic endpoint · AC2 one-tx one-version-gate 412 no-partial · AC3 changes[] tool · AC4 multi-row card + single Apply (H6) · AC5 trigger/regen parity · AC6 P3 single-PATCH endpoints unchanged.

## Risks
- Partial write on mid-apply error → mitigated: single tx, rollback on any error (the whole point).
- short_description auto-regen interaction (name+desc+explicit short_desc in one card) → match patchAttributeValue parity; test the description-attr case.
- Tool-schema replace is LLM-facing → the skill prompt (P5) already says "propose an edit"; update wording to "one or more changes".
- attr_value_id not belonging to the entity → scope the UPDATE + RowsAffected guard → 4xx, rollback.
