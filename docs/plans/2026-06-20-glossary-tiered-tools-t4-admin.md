# Plan — Glossary Tiered MCP Tools · CP-4 + T4 ADMIN (the high-risk auth boundary)

**Date:** 2026-06-20 · **Spec:** [tiered-tools](../specs/2026-06-20-glossary-assistant-tiered-tools.md) §3d/§4b/§4c · **Buildplan:** [§6/§7](2026-06-20-glossary-assistant-tiered-tools-buildplan.md) · **Predecessor:** CP-3 (`72175a27`)

`/review-impl` MANDATORY (auth boundary). PO decisions (CLARIFY): admin confirm = **separate RS256 endpoint**; **T4b runs as a parallel background agent** against the contract below.

---

## CP-4 — pinned contract (the gateway↔glossary admin seam)

### Glossary side (T4a owns)
- **New MCP server at `/mcp/admin`** (separate from `/mcp`). Transport middleware verifies an **RS256 `admin:write` JWT in the `X-Admin-Token` header** via `adminjwt.Verify(token, adminPub, adminKID)` **before `tools/list` or any `tools/call`**. No/invalid token → **401 at the transport** (cannot even enumerate). `adminPub==nil` (admin disabled) → 401/503 fail-closed. Lifts the admin `sub` into ctx for the tools.
- **`/mcp/admin` contains ONLY System-tier admin tools.** No admin tool name/schema appears on `/mcp` (re-verified live at CP-3 ✅; a leak test pins it).
- **Admin propose tools** (class C, collapsed verbs):
  - `glossary_admin_standards_read` (R) — list System genres/kinds/attributes.
  - `glossary_admin_propose_create` / `_patch` / `_delete` with `level=genre|kind|attribute` — mint an `authorityAdmin` confirm token + preview; **no write**. Descriptors: `system_create_{genre,kind,attribute}`, `system_patch_*`, `system_delete_*`.
- **Confirm token (admin):** `authority="admin"`, carries the admin `sub` (`asub`) + descriptor + params + jti + exp. Same HMAC spine, single-use via `consumed_tokens`.
- **Admin confirm endpoint:** `POST /v1/glossary/actions/admin/confirm` (+ `/admin/preview`), gated by `requireAdminScope` (RS256 `Authorization: Bearer`). Order mirrors the user path: verify token → re-check authority (token `asub` must match the confirming admin's `sub`; admin still holds `admin:write`) **before** consuming the jti → claim jti (single-use) → re-validate → execute the System write via the existing `system_admin_handler.go` core logic. The user `/actions/confirm` (HS256) is untouched.
- `authorityAdmin` branch in `action_confirm.go`/`authorizeAction` stops being a blanket 501 — it now serves the admin confirm path.

### Gateway side (T4b — background agent)
- Federate glossary **`/mcp/admin`** as a **distinct upstream** with its own catalog, exposed downstream as the gateway's **`/mcp/admin`** (separate from `/mcp`).
- Forward the admin token to glossary as **`X-Admin-Token`**; **never log it** (redact in any request/debug logging).
- The gateway dials `/mcp/admin` **only** for an admin-token-bearing surface; a normal user/book chat's federation never lists or reaches `/mcp/admin`. Admin tool names **never** appear in the `/mcp` catalog.
- Tests: admin catalog isolated from `/mcp`; no admin token → cannot list/call `/mcp/admin` (401 passthrough); `X-Admin-Token` never logged.

### Security invariants (both sides)
- **INV-T2:** admin authority = RS256 `admin:write`, **never** `X-User-Id`.
- **INV-T6:** three barriers — (1) `/mcp/admin` unreachable without a verified admin token (401 before `tools/list`), (2) admin tools absent from `/mcp`, (3) every System write human-confirm-gated.
- Every System write stays **class C** — the LLM proposes, a human admin confirms.

---

## T4a build steps (glossary, foreground)
1. `admin_mcp_server.go` — `adminMCPHandler()` + RS256 transport middleware (`X-Admin-Token` → `adminjwt.Verify`); mount `r.Handle("/mcp/admin", ...)` in `server.go`.
2. `admin_tools.go` — `RegisterAdminTools(srv)`: read + 3-verb×level propose tools minting `authorityAdmin` cards.
3. Descriptors in `action_confirm_token.go` (`system_*`) + `liveDescriptor`; admin params types.
4. `action_confirm.go` — admin confirm/preview effects (wrap the `system_admin_handler.go` write logic into shared cores so HTTP + confirm agree); `authorizeAction` admin branch (asub match + scope).
5. `server.go` — `POST /v1/glossary/actions/admin/confirm` + `/admin/preview` (requireAdminScope).
6. Tests: admin propose→confirm round-trip (RS256), single-use replay 422, **non-admin `/mcp/admin` → 401 before tools/list (INV-T6)**, admin tools absent from `/mcp`, wrong-admin-sub token rejected, fail-closed when admin disabled.

## CP-5 exit
A raw MCP client with a valid admin token can list+call `/mcp/admin` via the gateway; a non-admin gets 401 before `tools/list`; admin tools absent from `/mcp`; admin confirm executes a System write. Then T4c (chat AdminContext) + T4d (cms panel) follow.
