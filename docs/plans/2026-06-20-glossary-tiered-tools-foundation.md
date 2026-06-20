# Plan — CP-0 + Foundation (F1∥F2∥F3) · Glossary Tiered MCP Tools

**Date:** 2026-06-20 · **Size:** L (top-end; serial, human-in-loop per buildplan §10 — NOT fanned out) · **Branch:** `feat/glossary-assistant-coverage`
**Spec:** [`…tiered-tools.md`](../specs/2026-06-20-glossary-assistant-tiered-tools.md) §13 (CP-0 appendix) · **Buildplan:** [`…tiered-tools-buildplan.md`](../plans/2026-06-20-glossary-assistant-tiered-tools-buildplan.md) §2–3
**PO decisions (CLARIFY):** canary=`book_delete` · migrate legacy schema-confirm during Foundation · token=HMAC+`jti` ledger.

## Goal
Build the generalized class-C confirm spine, prove it on `book_delete` (CP-1), migrate the shipped schema-confirm path onto it, and land the F2 read-tool renames. `/review-impl` on F1 before POST-REVIEW.

## Build order (serial; commit once at CP-1)

### F1 — generalized confirm machinery (glossary Go) — load-bearing
1. **`action_confirm_token.go`** (replaces `schema_confirm_token.go`): `actionClaims{jti,auth,u,asub,b,d,p,exp}`, `mintActionToken`/`verifyActionToken`, domain `gloss-action-confirm:v1|`, TTL reuse. Descriptor enum + validation (§13.1). Keep the constant-time HMAC verify.
2. **`migrate` `0030_consumed_tokens`**: `UpConsumedTokens` (table §13.3) appended to `chain` in `ledger.go`; idempotent DDL via `execGuarded`. New migrate test: fresh→table present, idempotent re-run.
3. **`action_confirm.go`**: `POST /v1/glossary/actions/confirm` (verify → claim jti `ON CONFLICT DO NOTHING` → replay-422 → branch `auth`: grant=`requireUserID==u`+`requireGrant(b,Manage)`; admin=clean 501 stub → re-validate → dispatch by descriptor). `POST /v1/glossary/actions/preview` (non-consuming, recompute preview from current state; `book_delete` cascade enumerated). `consumeToken(jti)` helper.
4. **Descriptor effects:** `book_delete` (wrap existing soft-delete cascade handlers from `book_ontology_patch.go`), `schema_create_kind`→`createKindFromParams`, `schema_create_attribute`→`createAttrDefFromParams`.
5. **Retire** `schema_confirm_token.go`/`schema_confirm_handler.go`/`confirmSchema` route; migrate `schema_confirm_test.go` to the new path.

### F2 — shared helpers (glossary Go)
6. **`tool_helpers.go`**: code→id resolvers (book/user/system scoped — reuse `loadKindMap`, add genre/attr scoped variants as needed by the canary), `baseVersion409` helper (`content_hash` for genres/attrs, `updated_at` for kinds) + unit test, descriptor-param structs.
7. **Read-tool rename/retarget** (`mcp_server.go`/`kinds_handler.go`): `glossary_list_kinds`→`glossary_list_system_standards` (System standards catalogue role, §12.3); new `glossary_book_ontology_read` (book-local genres/kinds/attributes via `getBookOntology`). Update in-tree tool-description references to the old name.

### F3 — reusable FE confirm card (frontend TS + chat-service Py)
8. **chat-service:** `frontend_tools.py` — rename/generalize `glossary_confirm_schema`→`glossary_confirm_action` (`confirm_card` family) in `FRONTEND_TOOL_NAMES` + def; `glossary_skill.py` prompt tool-name updates; `knowledge_client.py`/test comment updates; tests.
9. **frontend:** `SchemaConfirmCard.tsx`→`ConfirmCard.tsx` keyed on `descriptor` (default row-list fallback + book_delete card), `api.ts` `confirmSchema`→`confirmAction`+`previewAction` (→ `/actions/confirm`,`/actions/preview`), `AssistantMessage.tsx` wiring, tests.

### gateway
10. `ai-gateway/src/mcp/handlers.ts` — comment-only ref update (same `/mcp`; no behavior change in Foundation).

## VERIFY (evidence gate)
- glossary: `go test ./... -p 1` green incl. new `action_confirm` tests (mint/verify, single-use replay-422, grant-branch, admin-501 stub, base-version 409 helper) + migrated schema create/attr regression + `0030` migrate test; gofmt/vet/provider-gate clean.
- chat-service: pytest green (frontend_tools rename).
- frontend: vitest green (ConfirmCard) + tsc clean.
- **Cross-service (≥2 services touched):** live-smoke `book_delete` round-trip (chat→gateway→glossary propose→confirm card→preview→confirm→cascade) OR `LIVE-SMOKE deferred to D-GKA-CP1-LIVE-SMOKE` if stack down.

## CP-1 exit (= spec §13.8)
book_delete round-trips · replay→422 · base-version 409 helper proven · read-rename live · migrated schema creates green · `/review-impl` on F1 no-HIGH.

## Risks
- Migrating the shipped schema path widens blast radius → regression test + `/review-impl` (PO-accepted).
- Claim-before-effect burns the token on transient effect failure → fail-closed, documented (§13.4).
- Catalog/curation rename must stay in lockstep across glossary tool names ↔ chat skill prompt ↔ FE tool name (single grep-verified pass).
