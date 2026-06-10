# glossary_propose_new_entity — P2 plan

- **Date:** 2026-06-10 · **Phase:** P2 · **Size:** L · **PO:** default v2.2; /review-impl at POST-REVIEW (write path). Input = book_id + kind + name + optional attributes.
- **Goal:** first Tier-W write tool — propose a NEW entity as a `draft` + `ai-suggested` + `assistant` suggestion (gateway-routed → AI-suggestions inbox), reusing the pipeline writeback path. INV-1: never canon.

## Reuse (verified)
`findEntityByNameOrAlias`(dedup) · `entityHasTag(ai-rejected)`(tombstone) · `createExtractedEntity`(INSERT draft + name attr + attributes) · `loadKindMap`/`loadAttrDefMap` · `tagAISuggested`/`tagAIRejected` · `checkBookOwnership` (P1). New: `tagAssistant = "assistant"` (provenance H1).

## Design
- **Core** `proposeNewEntity(ctx, bookID, kindID, name, attrs) (uuid.UUID, status, error)` — DB-testable directly (no ownership/ctx-identity):
  1. `existingID = findEntityByNameOrAlias(...)`; if `!= Nil`: `entityHasTag(ai-rejected)` → `skipped_tombstoned` else `skipped_exists` (H9 — never a dup).
  2. else `createExtractedEntity(ent{Name,Attributes}, attrDefMap, "und", [ai-suggested, assistant])` → `created`.
- **Tool wrapper** `toolProposeNewEntity` (mcp_server.go): userID from ctx → parse book_id → `checkBookOwnership` → resolve `kind` code via `loadKindMap` (unknown kind → error) → `proposeNewEntity` → `{entity_id, status}`.
- Registered as `glossary_propose_new_entity` (backend, gateway-routed). Tags carry `assistant` provenance.

## Build steps
1. `tagAssistant` const + `proposeNewEntity` core (extraction_handler.go or mcp_server.go).
2. `toolProposeNewEntity` + AddTool registration + In/Out types.
3. Tests: DB-backed (`openTestDB`, skips locally) — created / skipped_exists / skipped_tombstoned + draft+tags asserted; non-DB — ownership-denied + invalid input (bad book_id, empty name, unknown kind).
4. VERIFY: go build + go test (non-DB run; DB tests skip) + ai-gateway jest unchanged + provider-gate.

## AC (§18)
AC1 propose tool (backend, gateway-routed) · AC2 ownership-checked · AC3 dedup (H9) · AC4 tombstone (H9) · AC5 draft + [ai-suggested, assistant] → inbox · AC6 INV-1 (never canon) · AC7 returns {entity_id, status} · AC8 existing tests unchanged.

## Risks
- Reuse keeps behavior identical to the pipeline writeback (existing extraction_writeback_test guards the methods).
- `original_language` defaulted to "und" for tool-proposed names (human can correct in the inbox) — minor.
- The write/create path's real coverage is the DB-backed test (CI) + the deferred full-stack smoke (068); non-DB tests cover ownership + validation.
