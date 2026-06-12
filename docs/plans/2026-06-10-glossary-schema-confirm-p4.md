# glossary Tier-S schema tools — confirm-token — P4 plan

- **Date:** 2026-06-10 · **Phase:** P4 · **Size:** XL · **PO:** default v2.2; `/review-impl` at POST-REVIEW (security-critical). PO: no `/amaw`; scope = both new_kind + new_attribute.
- **Goal:** the assistant can *propose* a new kind/attribute; glossary mints a server-signed **`confirm_token`** (INV-9, H8); a human confirms; the create happens only via a **token-gated `/v1` path with no MCP/gateway route** → a compromised consumer can never create schema (threat S12). Spec §17.4 / §18 P4 DoD.

## Decisions (CLARIFY/DESIGN)
- **No MCP create route** = the un-bypassable property. Propose (MCP) only mints a token; create is `/v1` (JWT, browser-only). chat/gateway reach glossary via MCP (X-Internal-Token+X-User-Id), never JWT → can mint, never create.
- **Stateless HMAC token**: `base64url(json{u,b,op,p,exp}) + "." + base64url(HMAC_SHA256(JWT_SECRET, "gloss-schema-confirm:v1|"+payload))`. Key = existing `JWT_SECRET` (≥32, required) + domain-separator (no new env, no hardcoded secret, not JWT-confusable). 10-min expiry. Replay bounded by code-uniqueness (409). *Single-use-via-DB = deferred hardening (D-GLOSSARY-SCHEMA-SINGLEUSE).*
- **Verify at confirm**: constant-time sig · `exp>now` · `u==JWT-user` · re-check `verifyBookOwner(b)` (defense-in-depth). 
- **Kinds are global** (no book/owner column — pre-existing; manual createKind has no ownership check beyond auth). The token's `book_id` binds the *propose-time ownership gate* only; created kind/attr is global (same blast radius as the existing manual path). Documented.
- **Manual `/v1` createKind/createAttrDef stay token-free** (human-UI path unchanged).
- Confirm UX reuses P3 machinery: `glossary_confirm_schema` frontend tool (suspend) → `SchemaConfirmCard` → POST confirm → resume (H6).

## Build steps
### 1. glossary-service (Go)
- `schema_confirm_token.go` — `mintSchemaToken(cfg, userID, bookID, op, paramsJSON) string` + `verifySchemaToken(cfg, token) (claims, error)` (sig/exp/decode; `ErrTokenInvalid`/`ErrTokenExpired`). Uses `cfg.JWTSecret` + domain sep. Unit-testable, no DB.
- Extract `createKindFromParams(ctx, params) (domain.EntityKind, error)` + `createAttrDefFromParams(ctx, kindID, params) (domain.AttrDef, error)` cores from `createKind`/`createAttrDef`; the existing handlers call them (behavior preserved).
- `glossary_propose_new_kind` + `glossary_propose_new_attribute` MCP tools (mcp_server.go): ownership-check → validate (code/name non-empty; attr: resolve kind_code→kind_id via loadKindMap) → mint token → return `{confirm_token, expires_at, preview}`. NO write.
- `POST /v1/glossary/schema/confirm` handler + route: requireUserID → verify token → `u==userID` → re-check ownership → dispatch op → create core → 201 with the created kind/attr. Errors: token invalid/expired → 422 `GLOSS_SCHEMA_TOKEN`; code dup → 409.
- Tests: token mint/verify (valid / expired / tampered-sig / wrong-user) non-DB; propose tools (ownership-denied + mint shape) non-DB; confirm endpoint DB-backed (create kind + attr; bad/expired token → 422; replay dup → 409).

### 2. chat-service (Python)
- `frontend_tools.py`: add `glossary_confirm_schema` to FRONTEND_TOOL_NAMES + `GLOSSARY_CONFIRM_SCHEMA_TOOL` def (args: `confirm_token`, `op`, `summary`, `code`, `name`; description encodes H6 outcomes + that it's a 2-step confirm). Advertise on book-scoped surfaces (book_scoped group). 
- Resume outcomes pass-through (already verbatim): `schema_created|token_expired|error|cancelled`.
- Tests: tool is frontend + advertised when book_scoped; schema wire-standard.

### 3. frontend (React)
- `SchemaConfirmCard.tsx` (shared): renders op + preview (code/name/summary) + Confirm/Cancel. Confirm → `glossaryApi.confirmSchema(token)` → POST `/v1/glossary/schema/confirm`; map 201→`schema_created`, 422→`token_expired`, else→`error`; Cancel→`cancelled`; then `submitToolResult`.
- `glossary/api.ts`: `confirmSchema(token)` POST.
- `AssistantMessage.tsx`: route `glossary_confirm_schema`→SchemaConfirmCard (H15).
- `useChatMessages` FrontendToolOutcome: add `schema_created|token_expired|cancelled`.
- Tests: SchemaConfirmCard confirm→POST+resume(schema_created); 422→token_expired; cancel→cancelled.

### 4. VERIFY
- glossary `go build` + `go test` (token unit + DB-backed confirm on real PG).
- chat `pytest`; FE `vitest` + `tsc`.
- provider-gate.
- Cross-service live-smoke token (≥3 services) — attempt real propose→mint→confirm on a stack-up; else `LIVE-SMOKE deferred to D-GLOSSARY-SCHEMA-LIVE-SMOKE`.

## AC (§18 P4 DoD)
AC1 propose tools mint token+preview, no write · AC2 INV-9/H8 create needs valid token + no MCP create route · AC3 INV-5 two-step human confirm · AC4 H15 card routing · AC5 H6 real outcome · AC6 manual /v1 path unchanged.

## Risks
- Token forgery needs JWT_SECRET = full compromise (out of scope; same as any /v1 write).
- Reusing JWT_SECRET for HMAC — domain-separated, never fed to the JWT verifier; rotating JWT_SECRET invalidates pending confirm tokens (acceptable, short-lived).
- Core extraction could drift manual-path behavior → existing createKind/createAttrDef tests guard.
- Kinds-global blast radius (pre-existing) — documented, not widened by this phase.
- Single-use not enforced (replay bounded by code-uniqueness) → D-GLOSSARY-SCHEMA-SINGLEUSE.
